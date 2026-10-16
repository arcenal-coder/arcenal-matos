from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.intake import assistance_enabled
from core.models import Notification, User, reference_key
from core.modules import enabled, require_enabled
from core.permissions import require, sites

from .models import AssistanceTask, Badge, Laboratory, Movement, Period, Shipment


def fail(message):
    raise ValidationError(message)


def manage(actor, site_id):
    require_enabled("dosimeters")
    require(actor, ("admin", "manager"))
    if not sites(actor).filter(pk=site_id).exists():
        fail("Ce site ne vous est pas attribué.")


def people(site_id):
    return User.objects.filter(is_active=True, role__in=("admin", "manager", "member")).filter(
        Q(role="admin") | Q(site_id=site_id) | Q(role="manager", managed_sites=site_id)).distinct()


def person_allowed(person, site_id):
    require(person, ("admin", "manager", "member"))
    if not sites(person).filter(pk=site_id).exists():
        fail("L’équipier n’est pas rattaché à ce site.")


def staff(site_id):
    return User.objects.filter(is_active=True).filter(Q(role="admin") | Q(role="manager", managed_sites=site_id)).distinct()


def notify(users, title, body, key):
    for user in users:
        if user and user.is_active and user.role in ("admin", "manager", "member"):
            Notification.objects.get_or_create(key=f"dosimetry:{key}:{user.pk}", defaults={"user": user, "title": title, "body": body})


def record(actor, action, badge=None, site_id=None, period=None, shipment=None, **details):
    return Movement.objects.create(actor=actor, action=action, badge=badge, site_id=site_id or (badge.site_id if badge else None),
        period=period or (badge.period if badge else None), shipment=shipment, details=details)


def physical_date(value, after=None):
    if not value or value > timezone.localdate() or (after and value < after):
        fail("La date doit être passée ou actuelle et respecter l’ordre réception, distribution, collecte puis expédition.")


@transaction.atomic
def save_laboratory(actor, values, pk=None):
    require_enabled("dosimeters")
    require(actor, ("admin",))
    item = Laboratory.objects.select_for_update().get(pk=pk) if pk else Laboratory()
    for key in ("name", "address", "contact"):
        if key in values:
            setattr(item, key, values[key])
    item.full_clean()
    item.save()
    record(actor, "Laboratoire enregistré", laboratory=item.pk)
    return item


@transaction.atomic
def save_period(actor, values, pk=None):
    require_enabled("dosimeters")
    require(actor, ("admin",))
    item = Period.objects.select_for_update().get(pk=pk) if pk else Period()
    if pk and item.badges.exists() and any(values.get(key, getattr(item, key)) != getattr(item, key) for key in ("laboratory", "start_on", "end_on")):
        fail("Le laboratoire et la période de port ne peuvent plus changer après réception de badges.")
    before = {key: str(getattr(item, key, "")) for key in ("start_on", "end_on", "return_due_on")}
    for key in ("name", "laboratory", "start_on", "end_on", "return_due_on"):
        if key in values:
            setattr(item, key, values[key])
    item.full_clean()
    item.save()
    record(actor, "Période enregistrée", period=item, before=before)
    return item


@transaction.atomic
def receive(actor, site, period, codes, received_on, kind="personal", wear_location="Corps entier", assigned_to=None, replacement_for=None):
    manage(actor, site.pk)
    physical_date(received_on)
    period = Period.objects.select_for_update().get(pk=period.pk)
    numbers = [value.strip() for value in codes if value.strip()]
    keys = [reference_key(value) for value in numbers]
    if not numbers or any(len(value) > 100 for value in numbers) or any(len(value) > 200 for value in keys):
        fail("Indiquez au moins un numéro de badge, limité à 100 caractères.")
    if len(set(keys)) != len(keys) or Badge.objects.filter(period=period, key__in=keys).exists():
        fail("Un numéro de badge est déjà présent dans cette période et ce laboratoire.")
    if kind not in ("personal", "witness") or len(wear_location) > 80:
        fail("Nature ou emplacement du badge invalide.")
    if assigned_to:
        if kind == "witness":
            fail("Un badge témoin n’est pas attribué à une personne.")
        person_allowed(assigned_to, site.pk)
    if assigned_to and len(numbers) > 1:
        fail("Pour une préaffectation nominative, réceptionnez un badge à la fois.")
    items = [Badge(code=code, key=key, period=period, site=site, kind=kind, wear_location=wear_location,
        assigned_to=assigned_to, received_on=received_on, received_by=actor, replacement_for=replacement_for) for code, key in zip(numbers, keys)]
    Badge.objects.bulk_create(items)
    Movement.objects.bulk_create([Movement(actor=actor, action="Badge reçu", badge=item, site=site, period=period,
        details={"code": item.code, "received_on": str(received_on)}) for item in items])
    return items


def assign_locked(actor, badge, recipient):
    manage(actor, badge.site_id)
    person_allowed(recipient, badge.site_id)
    if badge.kind != "personal" or badge.status != "stock":
        fail("Seul un badge personnel en stock peut être préaffecté.")
    if badge.assigned_to_id and badge.assigned_to_id != recipient.pk:
        fail("Ce badge est déjà préaffecté à un autre équipier. Vérifiez l’étiquette du laboratoire.")
    badge.assigned_to = recipient
    badge.save(update_fields=["assigned_to"])
    record(actor, "Préaffectation confirmée", badge=badge, recipient=recipient.pk)


@transaction.atomic
def preassign(actor, badge_id, recipient):
    require_enabled("dosimeters")
    badge = Badge.objects.select_for_update(of=("self",)).select_related("period").get(pk=badge_id)
    assign_locked(actor, badge, recipient)
    return badge


@transaction.atomic
def issue(actor, badge_id, issued_on, recipient=None):
    require_enabled("dosimeters")
    badge = Badge.objects.select_for_update(of=("self",)).select_related("period").get(pk=badge_id)
    manage(actor, badge.site_id)
    physical_date(issued_on, badge.received_on)
    if badge.status != "stock":
        fail("Ce badge n’est plus en stock.")
    if issued_on > badge.period.end_on:
        fail("La période de port est terminée à la date de distribution.")
    if badge.kind == "personal":
        recipient = recipient or badge.assigned_to
        if not recipient:
            fail("Choisissez l’équipier bénéficiaire.")
        person_allowed(recipient, badge.site_id)
        if badge.assigned_to_id and badge.assigned_to_id != recipient.pk:
            fail("Le badge est préaffecté à une autre personne.")
    elif recipient:
        fail("Un témoin reste rattaché au site, sans bénéficiaire individuel.")
    badge.assigned_to, badge.issued_on, badge.issued_by, badge.status = recipient, issued_on, actor, "issued"
    badge.save(update_fields=["assigned_to", "issued_on", "issued_by", "status"])
    record(actor, "Badge distribué" if badge.kind == "personal" else "Témoin mis en période", badge=badge, date=str(issued_on))
    notify([recipient], "Dosimètre remis", f"Badge {badge.code} · {badge.period.name}, retour attendu au {badge.period.return_due_on}.", f"badge:{badge.pk}:issued")
    return badge


def locked_badges(badge_ids):
    try:
        ids = [UUID(str(value)) for value in badge_ids]
    except (ValueError, TypeError, AttributeError):
        fail("Sélection de badges invalide.")
    if not ids or len(ids) != len(set(ids)):
        fail("Sélectionnez des badges distincts.")
    result = list(Badge.objects.select_for_update(of=("self",)).select_related("period__laboratory", "site", "assigned_to").filter(pk__in=ids).order_by("pk"))
    if len(result) != len(ids):
        fail("Un badge sélectionné n’existe plus.")
    return result


def task_for_operation(actor, task_id, kind, site_id, period_id):
    if not task_id:
        return None
    task = AssistanceTask.objects.select_for_update().get(pk=task_id)
    manage(actor, task.site_id)
    if task.status != "ready" or task.kind != kind or task.site_id != site_id or task.period_id != period_id:
        fail("La préparation IA ne correspond pas à cette opération.")
    return task


@transaction.atomic
def collect(actor, badge_ids, collected_on, not_worn=False, task_id=None):
    require_enabled("dosimeters")
    task = AssistanceTask.objects.select_for_update().get(pk=task_id) if task_id else None
    badges = locked_badges(badge_ids)
    first = badges[0]
    if task:
        task_for_operation(actor, task.pk, "collection", first.site_id, first.period_id)
    for badge in badges:
        manage(actor, badge.site_id)
        if badge.site_id != first.site_id or badge.period_id != first.period_id:
            fail("Une collecte groupée concerne un seul site et une seule période.")
        if badge.status not in ("issued", "stock") or (badge.status == "stock" and not not_worn):
            fail("Le badge doit être distribué, ou déclaré non porté s’il est encore en stock.")
        physical_date(collected_on, badge.issued_on or badge.received_on)
    for badge in badges:
        badge.status, badge.collected_on, badge.collected_by, badge.not_worn = "collected", collected_on, actor, bool(not_worn)
        badge.save(update_fields=["status", "collected_on", "collected_by", "not_worn"])
        record(actor, "Badge collecté", badge=badge, date=str(collected_on), not_worn=bool(not_worn))
        notify([badge.assigned_to], "Retour du dosimètre enregistré", f"Le badge {badge.code} a été collecté le {collected_on}.", f"badge:{badge.pk}:collected")
    if task:
        task.status = "applied"
        task.save(update_fields=["status"])
    return badges


@transaction.atomic
def send(actor, badge_ids, sent_on, tracking="", task_id=None):
    require_enabled("dosimeters")
    task = AssistanceTask.objects.select_for_update().get(pk=task_id) if task_id else None
    badges = locked_badges(badge_ids)
    first = badges[0]
    if task:
        task_for_operation(actor, task.pk, "shipment", first.site_id, first.period_id)
    if len(tracking) > 160:
        fail("La référence de suivi est limitée à 160 caractères.")
    for badge in badges:
        manage(actor, badge.site_id)
        if badge.site_id != first.site_id or badge.period_id != first.period_id:
            fail("Un envoi concerne un seul site, une seule période et son laboratoire.")
        if badge.status != "collected" or badge.shipment_id:
            fail("Seuls les badges collectés et non encore expédiés peuvent être envoyés.")
        physical_date(sent_on, badge.collected_on)
    shipment = Shipment.objects.create(site=first.site, period=first.period, sent_on=sent_on, tracking=tracking, actor=actor, assistance=task)
    for badge in badges:
        badge.status, badge.shipment = "sent", shipment
        badge.save(update_fields=["status", "shipment"])
        record(actor, "Badge envoyé au laboratoire", badge=badge, shipment=shipment, date=str(sent_on))
    if task:
        task.status = "applied"
        task.save(update_fields=["status"])
    return shipment


@transaction.atomic
def close_badge(actor, badge_id, status, closed_on, reason):
    require_enabled("dosimeters")
    badge = Badge.objects.select_for_update(of=("self",)).select_related("period").get(pk=badge_id)
    manage(actor, badge.site_id)
    if status not in ("lost", "cancelled") or not reason.strip():
        fail("Indiquez une perte ou une annulation avec son motif.")
    if badge.status in ("sent", "lost", "cancelled") or (status == "cancelled" and badge.status != "stock"):
        fail("Ce changement d’état n’est pas autorisé. Seul un badge encore en stock peut être annulé.")
    physical_date(closed_on, badge.collected_on or badge.issued_on or badge.received_on)
    badge.status, badge.closed_on, badge.reason = status, closed_on, reason.strip()
    badge.save(update_fields=["status", "closed_on", "reason"])
    record(actor, "Badge déclaré perdu" if status == "lost" else "Badge annulé", badge=badge, reason=reason, date=str(closed_on))
    notify([badge.assigned_to], "Suivi du dosimètre", f"Badge {badge.code} : {badge.get_status_display()}. {reason}", f"badge:{badge.pk}:{status}")
    return badge


@transaction.atomic
def replace(actor, badge_id, new_code, received_on):
    require_enabled("dosimeters")
    original = Badge.objects.select_for_update(of=("self",)).select_related("period", "site", "assigned_to").get(pk=badge_id)
    manage(actor, original.site_id)
    if original.status not in ("lost", "cancelled"):
        fail("Un remplacement est lié à un badge perdu ou annulé.")
    physical_date(received_on, original.closed_on)
    result = receive(actor, original.site, original.period, [new_code], received_on, original.kind, original.wear_location, original.assigned_to, original)[0]
    record(actor, "Remplacement reçu", badge=result, replaced=str(original.pk), old_number=original.code)
    return result


@transaction.atomic
def request_assistance(actor, site, period, kind, question=""):
    manage(actor, site.pk)
    if not assistance_enabled():
        fail("Activez d’abord l’assistance de l’agent dans Paramètres → Agent & MCP.")
    if kind not in dict(AssistanceTask.KINDS):
        fail("Aide logistique inconnue.")
    item = AssistanceTask.objects.create(site=site, period=period, kind=kind, question=question, requester=actor)
    record(actor, "Assistance logistique demandée", site_id=site.pk, period=period, task=str(item.pk), kind=kind)
    return item


@transaction.atomic
def answer_assistance(actor, task_id, response, assignments=None, badge_ids=None):
    require_enabled("dosimeters")
    require(actor, ("agent",))
    if not assistance_enabled():
        fail("Assistance désactivée.")
    task = AssistanceTask.objects.select_for_update().get(pk=task_id)
    if task.status != "pending":
        return task
    if not response.strip() or len(response) > 8000:
        fail("Une réponse logistique concise est requise.")
    assignments, badge_ids = assignments or [], badge_ids or []
    if not isinstance(assignments, list) or not isinstance(badge_ids, list) or len(assignments) > 300 or len(badge_ids) > 300:
        fail("Proposez au maximum 300 éléments par préparation.")
    if assignments and task.kind != "assignment" or badge_ids and task.kind not in ("collection", "shipment"):
        fail("La proposition ne correspond pas à l’aide demandée.")
    cleaned, seen = [], set()
    for proposal in assignments:
        try:
            badge = Badge.objects.get(pk=proposal["badge_id"], site_id=task.site_id, period_id=task.period_id, kind="personal", status="stock")
            person = User.objects.get(pk=proposal["user_id"])
        except (Badge.DoesNotExist, User.DoesNotExist, KeyError, TypeError, ValueError):
            fail("Affectation proposée invalide.")
        person_allowed(person, task.site_id)
        if badge.pk in seen or badge.assigned_to_id and badge.assigned_to_id != person.pk:
            fail("Affectation doublonnée ou incompatible avec la préaffectation du laboratoire.")
        seen.add(badge.pk)
        cleaned.append({"badge_id": str(badge.pk), "user_id": person.pk, "badge": badge.code, "person": str(person), "reason": str(proposal.get("reason", ""))[:1000]})
    selected = []
    for value in badge_ids:
        try:
            badge = Badge.objects.get(pk=value, site_id=task.site_id, period_id=task.period_id, status="issued" if task.kind == "collection" else "collected")
        except (Badge.DoesNotExist, ValueError, TypeError):
            fail("Badge proposé indisponible pour cette collecte / cet envoi.")
        if str(badge.pk) in selected:
            fail("Badge proposé en double.")
        selected.append(str(badge.pk))
    task.response, task.assignments, task.badge_ids, task.status = response.strip(), cleaned, selected, "ready"
    task.save(update_fields=["response", "assignments", "badge_ids", "status"])
    notify([task.requester], "Préparation dosimètres disponible", f"L’agent a préparé une aide pour {task.period.name}.", f"assistance:{task.pk}")
    return task


@transaction.atomic
def decide_assistance(actor, task_id, apply=False):
    require_enabled("dosimeters")
    task = AssistanceTask.objects.select_for_update().get(pk=task_id)
    manage(actor, task.site_id)
    if task.status != "ready":
        fail("Cette préparation n’est plus en attente de décision.")
    if apply and task.kind == "assignment":
        if not task.assignments:
            fail("Aucune préaffectation proposée.")
        locked = {str(item.pk): item for item in locked_badges([item["badge_id"] for item in task.assignments])}
        for proposal in task.assignments:
            badge = locked[proposal["badge_id"]]
            if badge.site_id != task.site_id or badge.period_id != task.period_id:
                fail("Le contexte du badge a changé.")
            assign_locked(actor, badge, User.objects.get(pk=proposal["user_id"]))
    elif apply and task.kind != "overview":
        fail("Utilisez le formulaire de collecte ou d’expédition pour confirmer l’opération réelle.")
    task.status = "applied" if apply else "dismissed"
    task.save(update_fields=["status"])
    record(actor, "Préparation IA confirmée" if apply else "Préparation IA écartée", site_id=task.site_id, period=task.period, task=str(task.pk))
    return task


def reminders():
    if not enabled("dosimeters"):
        return
    today = timezone.localdate()
    query = Badge.objects.filter(period__return_due_on__lt=today, status__in=("stock", "issued", "collected")).select_related("period", "assigned_to")
    for badge in query:
        if badge.status == "issued":
            users, title = [badge.assigned_to, *staff(badge.site_id)], "Dosimètre attendu au retour"
        elif badge.status == "collected":
            users, title = staff(badge.site_id), "Dosimètre à envoyer au laboratoire"
        else:
            users, title = staff(badge.site_id), "Badge non porté à retourner"
        notify(users, title, f"Badge {badge.code} · {badge.period.name}, échéance {badge.period.return_due_on}.",
            f"badge:{badge.pk}:{badge.period.return_due_on}:{badge.status}")
