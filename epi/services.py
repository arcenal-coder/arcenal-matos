from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.intake import assistance_enabled
from core.models import Notification, User
from core.modules import enabled, require_enabled
from core.permissions import require, sites

from .models import (
    Allocation,
    Destruction,
    Lot,
    Movement,
    Reference,
    Request,
    Sequence,
    Unit,
    ValidityProposal,
    earliest,
)


def fail(message):
    raise ValidationError(message)


def manage(actor, site_id):
    require_enabled("epi")
    require(actor, ("admin", "manager"))
    if not sites(actor).filter(pk=site_id).exists():
        fail("Ce site ne vous est pas attribué.")


def staff(site_id):
    from django.db.models import Q
    return User.objects.filter(is_active=True).filter(Q(role="admin") | Q(role="manager", managed_sites=site_id)).distinct()


def notify(users, title, body, key):
    # EPI notifications are internal; no unsolicited e-mail is queued here.
    for user in users:
        if user.is_active and user.role not in ("agent", "unassigned"):
            Notification.objects.get_or_create(key=f"epi:{key}:{user.pk}", defaults={"user": user, "title": title, "body": body})


def record(actor, reference, action, site_id=None, **details):
    return Movement.objects.create(actor=actor, reference=reference, action=action, site_id=site_id, details=details)


def check_date(value, earliest_date=None):
    if not value or value > timezone.localdate() or (earliest_date and value < earliest_date):
        fail("La date doit être passée ou actuelle et cohérente avec la réception / remise.")


def positive(quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        fail("La quantité doit être un nombre entier supérieur à zéro.")


@transaction.atomic
def save_reference(actor, values, reference_id=None):
    require_enabled("epi")
    require(actor, ("admin",) if reference_id else ("admin", "manager"))
    reference = Reference.objects.select_for_update().get(pk=reference_id) if reference_id else Reference()
    if reference_id and reference.lots.exists() and any(values.get(key, getattr(reference, key)) != getattr(reference, key) for key in ("tracking", "unit")):
        fail("Le mode de suivi et l'unité ne peuvent plus changer après une réception.")
    for key in ("name", "kind", "brand", "model", "size", "tracking", "unit", "usage_days", "notes"):
        if key in values:
            setattr(reference, key, values[key])
    reference.full_clean()
    reference.save()
    record(actor, reference, "Référence EPI enregistrée")
    return reference


@transaction.atomic
def receive(actor, reference, site, number, received_on, quantity, manufacturer_expiry=None, unit_price=None, supplier="", serials=None):
    manage(actor, site.pk)
    positive(quantity)
    check_date(received_on)
    reference = Reference.objects.select_for_update().get(pk=reference.pk)
    lot = Lot(reference=reference, site=site, number=number, received_on=received_on, received_quantity=quantity,
        available_quantity=quantity, manufacturer_expiry=manufacturer_expiry, unit_price=unit_price, supplier=supplier, received_by=actor)
    lot.full_clean()
    serials = serials or []
    if serials and (reference.tracking != "individual" or len(serials) != quantity or any(len(value) > 120 for value in serials)):
        fail("Pour le suivi individuel, renseignez un numéro de série par exemplaire ou laissez la liste vide.")
    lot.save()
    if reference.tracking == "individual":
        sequence, _ = Sequence.objects.get_or_create(reference=reference)
        units = []
        for index in range(quantity):
            sequence.last_number += 1
            units.append(Unit(lot=lot, code=f"EPI-{reference.pk:04d}-{sequence.last_number:06d}", serial=serials[index] if serials else ""))
        Unit.objects.bulk_create(units)
        sequence.save(update_fields=["last_number"])
    record(actor, reference, "Réception de stock", site.pk, lot=lot.pk, quantity=quantity,
        unit_price=str(unit_price) if unit_price is not None else None)
    return lot


@transaction.atomic
def set_validity(actor, lot_id, values, unit_id=None):
    require_enabled("epi")
    lot = Lot.objects.select_for_update(of=("self",)).select_related("reference").get(pk=lot_id)
    manage(actor, lot.site_id)
    target = Unit.objects.select_for_update().get(pk=unit_id) if unit_id else lot
    if unit_id and target.lot_id != lot.pk:
        fail("Cet exemplaire n'appartient pas au lot.")
    allowed = {"serial", "assessed_expiry", "usage_days"} if unit_id else {"manufacturer_expiry", "assessed_expiry", "usage_days"}
    if set(values) - allowed:
        fail("Les identifiants, quantités, prix et premières mises en service sont protégés.")
    before = {key: str(getattr(target, key)) for key in values}
    for key, value in values.items():
        setattr(target, key, value)
    limit = lot.manufacturer_expiry if unit_id else target.manufacturer_expiry
    if target.assessed_expiry and limit and target.assessed_expiry > limit:
        fail("La date retenue ne peut pas dépasser la date limite fabricant.")
    target.full_clean()
    target.save(update_fields=list(values))
    record(actor, lot.reference, "Validité EPI renseignée", lot.site_id, lot=lot.pk, unit=str(unit_id) if unit_id else None,
        before=before, after={key: str(value) for key, value in values.items()})
    return target


@transaction.atomic
def request_epi(actor, reference, quantity, reason, site):
    require_enabled("epi")
    require(actor, ("admin", "manager", "member"))
    if not sites(actor).filter(pk=site.pk).exists():
        fail("Ce site ne vous est pas attribué.")
    positive(quantity)
    item = Request.objects.create(reference=reference, site=site, requester=actor, quantity=quantity, reason=reason)
    record(actor, reference, "Demande EPI", site.pk, request=item.pk, quantity=quantity)
    notify(staff(site.pk), "Nouvelle demande EPI", f"{actor} demande {quantity} × {reference} sur {site}.", f"request:{item.pk}:created")
    return item


@transaction.atomic
def decide(actor, request_id, approve, reason=""):
    require_enabled("epi")
    item = Request.objects.select_for_update().select_related("reference", "requester").get(pk=request_id)
    manage(actor, item.site_id)
    if item.status != "pending":
        fail("Cette demande a déjà été traitée.")
    if not approve and not reason.strip():
        fail("Indiquez le motif du refus.")
    item.status = "approved" if approve else "rejected"
    item.decided_by, item.decision_reason = actor, reason.strip()
    item.save(update_fields=["status", "decided_by", "decision_reason"])
    record(actor, item.reference, "Demande acceptée" if approve else "Demande refusée", item.site_id, request=item.pk, reason=reason)
    notify([item.requester], "Demande EPI traitée", f"{item.reference} : {item.get_status_display()}. {reason}", f"request:{item.pk}:decided")
    return item


@transaction.atomic
def cancel_request(actor, request_id):
    require_enabled("epi")
    item = Request.objects.select_for_update().select_related("reference").get(pk=request_id)
    require(actor, ("admin", "manager", "member"))
    if item.requester_id != actor.pk or item.status not in ("pending", "approved") or item.fulfilled_quantity:
        fail("Seule une demande personnelle non remise peut être annulée.")
    item.status = "cancelled"
    item.save(update_fields=["status"])
    record(actor, item.reference, "Demande annulée", item.site_id, request=item.pk)
    return item


@transaction.atomic
def issue(actor, lot_id, recipient, quantity, issued_on, first_use_on=None, unit_id=None, request_id=None):
    require_enabled("epi")
    request = Request.objects.select_for_update().get(pk=request_id) if request_id else None
    lot = Lot.objects.select_for_update(of=("self",)).select_related("reference").get(pk=lot_id)
    manage(actor, lot.site_id)
    positive(quantity)
    check_date(issued_on, lot.received_on)
    require(recipient, ("admin", "manager", "member"))
    if not sites(recipient).filter(pk=lot.site_id).exists():
        fail("Le bénéficiaire n'est pas rattaché à ce site.")
    if quantity > lot.available_quantity:
        fail("Stock insuffisant.")
    if request and (request.status not in ("approved", "partial") or request.reference_id != lot.reference_id
                    or request.site_id != lot.site_id or request.requester_id != recipient.pk or quantity > request.remaining):
        fail("La remise ne correspond pas à une quantité restant à fournir sur cette demande acceptée.")
    unit = None
    if lot.reference.tracking == "individual":
        if not unit_id or quantity != 1:
            fail("Choisissez un exemplaire identifié ; une remise correspond à un exemplaire.")
        unit = Unit.objects.select_for_update().get(pk=unit_id)
        if unit.lot_id != lot.pk or unit.state != "stock":
            fail("Cet exemplaire n'est pas disponible dans ce lot.")
        if unit.first_use_on and first_use_on and first_use_on != unit.first_use_on:
            fail("La première mise en service est déjà connue et ne peut pas être réinitialisée.")
        first_use_on = unit.first_use_on or first_use_on
    elif unit_id:
        fail("Ce lot est suivi en quantités.")
    first_use_on = first_use_on or issued_on
    check_date(first_use_on)
    if first_use_on > issued_on:
        fail("La première mise en service ne peut pas être postérieure à la remise.")
    duration = unit.effective_usage_days if unit else lot.effective_usage_days
    service_end = first_use_on + timedelta(days=duration) if duration else None
    deadline = earliest(lot.valid_until, unit.assessed_expiry if unit else None, service_end)
    if deadline and deadline < issued_on:
        fail("Cet EPI est expiré à la date de remise.")
    allocation = Allocation.objects.create(lot=lot, unit=unit, recipient=recipient, request=request, quantity=quantity,
        active_quantity=quantity, issued_on=issued_on, first_use_on=first_use_on, unit_price=lot.unit_price, issued_by=actor)
    lot.available_quantity -= quantity
    lot.save(update_fields=["available_quantity"])
    if unit:
        unit.state, unit.first_use_on = "issued", first_use_on
        unit.save(update_fields=["state", "first_use_on"])
    if request:
        request.fulfilled_quantity += quantity
        request.status = "fulfilled" if request.remaining == 0 else "partial"
        request.save(update_fields=["fulfilled_quantity", "status"])
    record(actor, lot.reference, "Remise EPI", lot.site_id, allocation=allocation.pk, recipient=recipient.pk,
        quantity=quantity, issued_on=str(issued_on), first_use_on=str(first_use_on), cost=str(allocation.cost) if allocation.cost is not None else None)
    notify([recipient], "EPI remis", f"{quantity} × {lot.reference} remis le {issued_on}. Validité : {deadline or 'non renseignée'}.", f"allocation:{allocation.pk}")
    return allocation


@transaction.atomic
def destroy(actor, lot_id, quantity, destroyed_on, reason, allocation_id=None, unit_id=None):
    require_enabled("epi")
    allocation = Allocation.objects.select_for_update(of=("self",)).select_related("unit").get(pk=allocation_id) if allocation_id else None
    lot = Lot.objects.select_for_update(of=("self",)).select_related("reference").get(pk=lot_id)
    manage(actor, lot.site_id)
    positive(quantity)
    if not reason.strip():
        fail("Indiquez le motif de destruction.")
    check_date(destroyed_on, allocation.issued_on if allocation else lot.received_on)
    if allocation and (allocation.lot_id != lot.pk or quantity > allocation.active_quantity):
        fail("La quantité à détruire dépasse la dotation encore détenue.")
    if not allocation and quantity > lot.available_quantity:
        fail("La quantité à détruire dépasse le stock disponible.")
    unit = allocation.unit if allocation else None
    if unit_id:
        if unit and str(unit.pk) != str(unit_id):
            fail("L'exemplaire ne correspond pas à cette dotation.")
        unit = Unit.objects.select_for_update().get(pk=unit_id)
    elif unit:
        unit = Unit.objects.select_for_update().get(pk=unit.pk)
    if lot.reference.tracking == "individual":
        if not unit or unit.lot_id != lot.pk or quantity != 1 or unit.state != ("issued" if allocation else "stock"):
            fail("Choisissez un exemplaire non détruit dans le stock ou la dotation concernés.")
    elif unit:
        fail("Ce lot est suivi en quantités.")
    price = allocation.unit_price if allocation else lot.unit_price
    item = Destruction.objects.create(lot=lot, allocation=allocation, unit=unit, quantity=quantity,
        destroyed_on=destroyed_on, reason=reason.strip(), unit_price=price, actor=actor)
    if allocation:
        allocation.active_quantity -= quantity
        allocation.save(update_fields=["active_quantity"])
        notify([allocation.recipient], "Destruction EPI enregistrée", f"{quantity} × {lot.reference} : {reason}", f"destruction:{item.pk}")
    else:
        lot.available_quantity -= quantity
        lot.save(update_fields=["available_quantity"])
    if unit:
        unit.state = "destroyed"
        unit.save(update_fields=["state"])
    record(actor, lot.reference, "Destruction EPI", lot.site_id, destruction=item.pk, quantity=quantity,
        allocation=allocation.pk if allocation else None, reason=reason, cost=str(item.cost) if item.cost is not None else None)
    return item


@transaction.atomic
def create_proposal(actor, reference, lot=None, unit=None, first_use_on=None):
    require_enabled("epi")
    require(actor, ("admin", "manager"))
    if not assistance_enabled():
        fail("Activez d'abord l'assistance dans Paramètres → Agent & MCP.")
    if lot:
        manage(actor, lot.site_id)
        if lot.reference_id != reference.pk or (unit and unit.lot_id != lot.pk):
            fail("Le lot ou l'exemplaire ne correspond pas à cette référence.")
    elif unit:
        fail("Sélectionnez le lot de l'exemplaire.")
    if unit and unit.first_use_on:
        first_use_on = unit.first_use_on
    if first_use_on:
        check_date(first_use_on)
    item = ValidityProposal.objects.create(reference=reference, lot=lot, unit=unit, requester=actor, first_use_on=first_use_on)
    record(actor, reference, "Validité demandée à l’agent", lot.site_id if lot else None, proposal=str(item.pk))
    return item


@transaction.atomic
def answer_proposal(actor, proposal_id, proposed_date=None, usage_days=None, explanation="", source="", missing_information=""):
    require_enabled("epi")
    require(actor, ("agent",))
    if not assistance_enabled():
        fail("Assistance désactivée.")
    item = ValidityProposal.objects.select_for_update(of=("self",)).select_related("lot").get(pk=proposal_id)
    if item.status != "pending":
        return item
    if usage_days is not None and (isinstance(usage_days, bool) or not isinstance(usage_days, int) or not 1 <= usage_days <= 36500):
        fail("La durée proposée doit être comprise entre 1 et 36500 jours.")
    if not explanation.strip() or len(explanation) > 4000 or len(source) > 2000 or len(missing_information) > 2000:
        fail("Une explication est requise et les textes doivent rester concis.")
    if proposed_date or usage_days:
        if not source.strip():
            fail("Indiquez la source fabricant de la proposition.")
    elif not missing_information.strip():
        fail("Indiquez les informations manquantes si aucune validité ne peut être proposée.")
    if proposed_date and not item.first_use_on and not (item.lot_id and item.lot.manufacturer_expiry):
        fail("Une date précise nécessite une première mise en service ou une date fabricant connue. Proposez une durée ou précisez les données manquantes.")
    if proposed_date and item.lot and item.lot.manufacturer_expiry and proposed_date > item.lot.manufacturer_expiry:
        fail("La proposition dépasse la date limite du fabricant.")
    item.proposed_date, item.proposed_usage_days = proposed_date, usage_days
    item.explanation, item.source, item.missing_information, item.status = explanation, source, missing_information, "ready"
    item.full_clean()
    item.save()
    record(actor, item.reference, "Proposition de validité reçue", item.lot.site_id if item.lot_id else None, proposal=str(item.pk))
    notify([item.requester], "Proposition IA pour un EPI", f"La proposition de validité pour {item.reference} est disponible dans EPI → Validités IA.", f"proposal:{item.pk}")
    return item


@transaction.atomic
def apply_proposal(actor, proposal_id, apply=True):
    require_enabled("epi")
    require(actor, ("admin", "manager"))
    item = ValidityProposal.objects.select_for_update(of=("self",)).select_related("reference", "lot", "unit").get(pk=proposal_id)
    if item.lot_id:
        manage(actor, item.lot.site_id)
    elif actor.role != "admin":
        fail("Seul un administrateur peut appliquer une durée commune à une référence.")
    if item.status != "ready":
        fail("Cette proposition n'est plus en attente de décision.")
    if apply:
        if not item.proposed_date and not item.proposed_usage_days:
            fail("L'agent demande des précisions ; aucune date ou durée n'est applicable.")
        if item.proposed_usage_days and not item.lot_id:
            Reference.objects.filter(pk=item.reference_id).update(usage_days=item.proposed_usage_days)
        if item.proposed_usage_days and item.lot_id:
            target = Unit.objects.select_for_update().get(pk=item.unit_id) if item.unit_id else Lot.objects.select_for_update().get(pk=item.lot_id)
            target.usage_days = item.proposed_usage_days
            target.save(update_fields=["usage_days"])
        if item.proposed_date:
            if not item.lot_id:
                fail("Pour appliquer une date précise, demandez une proposition pour un lot ou un exemplaire.")
            if item.lot.manufacturer_expiry and item.proposed_date > item.lot.manufacturer_expiry:
                fail("La date limite fabricant ne peut pas être prolongée.")
            target = Unit.objects.select_for_update().get(pk=item.unit_id) if item.unit_id else Lot.objects.select_for_update().get(pk=item.lot_id)
            target.assessed_expiry = item.proposed_date
            target.save(update_fields=["assessed_expiry"])
    item.status = "applied" if apply else "dismissed"
    item.save(update_fields=["status"])
    record(actor, item.reference, "Validité IA appliquée" if apply else "Proposition IA écartée", item.lot.site_id if item.lot_id else None, proposal=str(item.pk))
    return item


def reminders():
    if not enabled("epi"):
        return
    today = timezone.localdate()

    def remind(deadline, users, label, key):
        if not deadline or deadline > today + timedelta(days=30):
            return
        bucket = "expired" if deadline < today else "due"
        title = "EPI expiré" if bucket == "expired" else "EPI : échéance proche"
        notify(users, title, f"{label} : validité au {deadline}.", f"{key}:{deadline}:{bucket}")

    for lot in Lot.objects.filter(available_quantity__gt=0, reference__tracking="bulk").select_related("reference", "site"):
        remind(lot.valid_until, staff(lot.site_id), str(lot), f"lot:{lot.pk}")
    for unit in Unit.objects.filter(state="stock").select_related("lot__reference", "lot__site"):
        remind(unit.valid_until, staff(unit.lot.site_id), str(unit), f"unit:{unit.pk}")
    for allocation in Allocation.objects.filter(active_quantity__gt=0).select_related("lot__reference", "unit__lot__reference", "recipient"):
        remind(allocation.valid_until, [allocation.recipient, *staff(allocation.lot.site_id)],
            f"{allocation.lot.reference} remis à {allocation.recipient}", f"allocation:{allocation.pk}")
