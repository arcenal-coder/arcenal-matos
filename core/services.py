import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import (
    AgentCommand,
    Allocation,
    Asset,
    Event,
    Intervention,
    License,
    Loan,
    Notification,
    Outbox,
    Reservation,
    SupplierRequest,
    Transfer,
    User,
)
from .permissions import manage, require, sites


def fail(message):
    raise ValidationError(message)


def audit(actor, action, asset=None, details=None, site=None):
    Event.objects.create(actor=actor, action=action, asset=asset,
                         site=site or (asset.site if asset else None), details=details or {})


def notify(users, title, body, key):
    for user in users:
        if not user.is_active or user.role == "agent":
            continue
        notification, created = Notification.objects.get_or_create(
            key=f"{key}:{user.pk}", defaults={"user": user, "title": title, "body": body})
        if created and user.email:
            Outbox.objects.get_or_create(key=f"notification:{notification.pk}", defaults={
                "recipient": user.email, "subject": title, "body": body})


def managers(site):
    return User.objects.filter(role="manager", managed_sites=site, is_active=True).distinct()


def available(asset, start, end, exclude=None):
    if asset.blocked or asset.assigned_to_id:
        return False
    if asset.control_required and asset.control_due and asset.control_due < end:
        return False
    transfers = getattr(asset, "active_transfers", None)
    if transfers is not None:
        transferring = bool(transfers)
    else:
        transferring = asset.transfers.filter(status__in=("planned", "transit")).exists()
    if transferring:
        return False
    cached = getattr(asset, "active_reservations", None)
    if cached is not None:
        return not any(item.pk != exclude and (item.status == "out" or (item.start <= end and item.end >= start)) for item in cached)
    reservations = asset.reservations.filter(status__in=("approved", "out"))
    if exclude:
        reservations = reservations.exclude(pk=exclude)
    return not reservations.filter(Q(status="out") | Q(start__lte=end, end__gte=start)).exists()


def availability_queryset(queryset):
    return queryset.select_related("category", "site").prefetch_related(
        Prefetch("reservations", queryset=Reservation.objects.filter(status__in=("approved", "out")), to_attr="active_reservations"),
        Prefetch("transfers", queryset=Transfer.objects.filter(status__in=("planned", "transit")), to_attr="active_transfers"))


def locally_available(actor, asset, start, end):
    candidates = Asset.objects.filter(site=actor.site, category=asset.category)
    if asset.model:
        candidates = candidates.filter(model=asset.model)
    return any(available(item, start, end) for item in candidates.select_related("category"))


@transaction.atomic
def reserve(actor, asset_id, start, end, reason=""):
    require(actor, ("member",))
    if not actor.site_id:
        fail("Votre site de rattachement n'est pas configuré.")
    if end < start or start < timezone.localdate():
        fail("Les dates de réservation sont invalides.")
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category", "site").get(pk=asset_id)
    if asset.site_id != actor.site_id and locally_available(actor, asset, start, end):
        fail("Un matériel équivalent est disponible sur votre site : réservez-le en priorité.")
    if not available(asset, start, end):
        fail("Ce matériel n'est pas disponible aux dates demandées.")
    reservation = Reservation.objects.create(asset=asset, borrower=actor, start=start, end=end, reason=reason)
    audit(actor, "reservation.created", asset, {"reservation": reservation.pk})
    notify(managers(asset.site), "Demande de réservation", f"{actor} demande {asset} du {start} au {end}.",
           f"reservation:{reservation.pk}:created")
    notify([actor], "Demande enregistrée", f"Votre demande pour {asset} attend une validation humaine.",
           f"reservation:{reservation.pk}:receipt")
    return reservation


@transaction.atomic
def approve_reservation(actor, pk, approve=True):
    # Lock the asset first in every loan operation to keep a consistent lock order.
    snapshot = Reservation.objects.get(pk=pk)
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=snapshot.asset_id)
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    manage(actor, asset.site_id, human_manager=True)
    if reservation.status != "pending":
        fail("La demande a déjà été traitée.")
    if approve and not available(asset, reservation.start, reservation.end, pk):
        fail("Le matériel est devenu indisponible.")
    if approve and reservation.end < timezone.localdate():
        fail("La période demandée est passée.")
    reservation.status = "approved" if approve else "rejected"
    reservation.approved_by = actor
    reservation.approved_at = timezone.now()
    reservation.save()
    audit(actor, f"reservation.{reservation.status}", asset, {"reservation": pk})
    notify([reservation.borrower], f"Réservation {reservation.get_status_display().lower()}",
           f"Votre demande pour {asset} a été traitée par {actor}.", f"reservation:{pk}:{reservation.status}")
    return reservation


@transaction.atomic
def cancel_reservation(actor, pk):
    snapshot = Reservation.objects.get(pk=pk)
    asset = Asset.objects.select_for_update().get(pk=snapshot.asset_id)
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    if actor.pk != reservation.borrower_id:
        manage(actor, asset.site_id, human_manager=True)
    if reservation.status not in ("pending", "approved"):
        fail("Ce prêt ne peut plus être annulé.")
    reservation.status = "cancelled"
    reservation.save()
    audit(actor, "reservation.cancelled", asset, {"reservation": pk})
    notify([reservation.borrower, *managers(asset.site)], "Réservation annulée",
           f"La demande #{pk} a été annulée.", f"reservation:{pk}:cancelled")


@transaction.atomic
def checkout(actor, pk, condition, comment=""):
    snapshot = Reservation.objects.get(pk=pk)
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=snapshot.asset_id)
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    manage(actor, asset.site_id)
    if reservation.status != "approved" or not reservation.approved_by_id:
        fail("Une validation humaine du prêt est nécessaire.")
    if not reservation.start <= timezone.localdate() <= reservation.end:
        fail("La sortie doit avoir lieu pendant la période validée.")
    if not condition.strip() or not available(asset, reservation.start, reservation.end, pk):
        fail("État du matériel manquant ou matériel indisponible.")
    loan = Loan.objects.create(reservation=reservation, checked_out_by=actor,
                               checkout_condition=condition, comment=comment)
    reservation.status = "out"
    reservation.save()
    audit(actor, "loan.checkout", asset, {"loan": loan.pk, "reservation": pk, "condition": condition})
    notify([reservation.borrower], "Matériel remis", f"{asset} est prêté jusqu'au {reservation.end}.", f"loan:{loan.pk}:checkout")
    return loan


@transaction.atomic
def return_loan(actor, pk, condition, comment="", damaged=False):
    snapshot = Reservation.objects.get(pk=pk)
    asset = Asset.objects.select_for_update().get(pk=snapshot.asset_id)
    reservation = Reservation.objects.select_for_update().get(pk=pk)
    manage(actor, asset.site_id)
    if reservation.status != "out" or not condition.strip():
        fail("Prêt non sorti ou état au retour manquant.")
    loan = Loan.objects.select_for_update().get(reservation=reservation)
    if loan.returned_at:
        fail("Le retour a déjà été enregistré.")
    loan.returned_at = timezone.now()
    loan.returned_by = actor
    loan.return_condition = condition
    loan.comment = "\n".join(filter(None, [loan.comment, comment]))
    loan.save()
    reservation.status = "returned"
    reservation.save()
    if damaged:
        asset.state = "damaged"
        asset.save()
    audit(actor, "loan.return", asset, {"loan": loan.pk, "condition": condition, "damaged": damaged})
    notify([reservation.borrower, *managers(asset.site)], "Matériel retourné",
           f"Le retour de {asset} est enregistré.", f"loan:{loan.pk}:return")
    return loan


@transaction.atomic
def update_asset(actor, asset_id, values):
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=asset_id)
    manage(actor, asset.site_id)
    allowed = {"name", "brand", "model", "serial", "location", "custom_fields"}
    if actor.role != "agent":
        allowed |= {"category", "purchase_date", "purchase_cost", "control_required", "last_control",
                    "next_control", "interval_days", "state"}
    if set(values) - allowed:
        fail("Un champ protégé ou non modifiable a été demandé.")
    if "state" in values and values["state"] == "available" and asset.state != "available":
        fail("Utilisez l'action humaine de remise en service.")
    before = {key: str(getattr(asset, key)) for key in values}
    if asset.control_required and (not asset.control_due or asset.control_due < timezone.localdate()):
        asset.control_hold = True
    for key, value in values.items():
        setattr(asset, key, value)
    asset.full_clean()
    asset.save()
    audit(actor, "asset.updated", asset, {"before": before, "after": {key: str(value) for key, value in values.items()}})
    return asset


@transaction.atomic
def assign_asset(actor, asset_id, user):
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=asset_id)
    manage(actor, asset.site_id)
    if user and (not user.is_active or user.role != "member" or user.site_id != asset.site_id):
        fail("L'affectation nécessite un collaborateur actif du site.")
    if user and (asset.blocked or asset.assigned_to_id or
                 asset.reservations.filter(status__in=("approved", "out")).exists() or
                 asset.transfers.filter(status__in=("planned", "transit")).exists()):
        fail("Le matériel est bloqué, affecté ou engagé dans une réservation.")
    asset.assigned_to = user
    asset.save()
    audit(actor, "asset.assigned", asset, {"user": user.pk if user else None})
    return asset


@transaction.atomic
def transfer_asset(actor, asset_id, destination, comment=""):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    manage(actor, asset.site_id)
    if destination.pk == asset.site_id:
        fail("Choisissez un autre site.")
    if asset.assigned_to_id or asset.reservations.filter(status="out").exists() or asset.transfers.filter(status__in=("planned", "transit")).exists():
        fail("Le matériel est affecté, prêté ou déjà en transfert.")
    transfer = Transfer.objects.create(asset=asset, source=asset.site, destination=destination, comment=comment)
    audit(actor, "transfer.planned", asset, {"transfer": transfer.pk, "destination": destination.pk})
    notify([*managers(asset.site), *managers(destination)], "Transfert prévu", f"{asset} vers {destination}.", f"transfer:{transfer.pk}:planned")
    return transfer


@transaction.atomic
def advance_transfer(actor, pk):
    snapshot = Transfer.objects.get(pk=pk)
    asset = Asset.objects.select_for_update().get(pk=snapshot.asset_id)
    transfer = Transfer.objects.select_for_update().get(pk=pk)
    if transfer.status == "planned":
        manage(actor, transfer.source_id)
        transfer.status = "transit"
    elif transfer.status == "transit":
        manage(actor, transfer.destination_id)
        transfer.status = "received"
        asset.site = transfer.destination
        asset.save()
    else:
        fail("Ce transfert est terminé.")
    transfer.save()
    audit(actor, f"transfer.{transfer.status}", asset, {"transfer": pk})
    notify([*managers(transfer.source), *managers(transfer.destination)], "Transfert mis à jour",
           f"{asset} : {transfer.get_status_display()}.", f"transfer:{pk}:{transfer.status}")
    return transfer


@transaction.atomic
def plan_intervention(actor, asset_id, values):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    manage(actor, asset.site_id)
    if asset.reservations.filter(status="out").exists():
        fail("Le matériel doit être retourné avant sa mise en maintenance.")
    item = Intervention(asset=asset, **values)
    item.full_clean()
    item.save()
    asset.state = "maintenance"
    asset.save()
    audit(actor, "maintenance.planned", asset, {"intervention": item.pk})
    notify(managers(asset.site), "Maintenance planifiée", f"{asset} : {item.scheduled_date}.", f"maintenance:{item.pk}:planned")
    return item


@transaction.atomic
def complete_intervention(actor, pk, date, cost=None, description=None):
    snapshot = Intervention.objects.get(pk=pk)
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=snapshot.asset_id)
    item = Intervention.objects.select_for_update().get(pk=pk)
    manage(actor, asset.site_id)
    if item.completed_date or date > timezone.localdate():
        fail("Intervention déjà terminée ou date future.")
    item.completed_date = date
    if cost is not None:
        item.cost = cost
    if description is not None:
        item.description = description
    item.full_clean()
    item.save()
    if item.is_control:
        asset.last_control = date
        interval = asset.interval_days or asset.category.interval_days
        asset.next_control = date + timedelta(days=interval) if interval else None
        asset.save()
    audit(actor, "maintenance.completed", asset, {"intervention": pk})
    return item


@transaction.atomic
def restore_asset(actor, asset_id):
    asset = Asset.objects.select_for_update(of=("self",)).select_related("category").get(pk=asset_id)
    manage(actor, asset.site_id, human_manager=True)
    if asset.interventions.filter(completed_date__isnull=True).exists():
        fail("Des interventions ne sont pas terminées.")
    if asset.control_required and (not asset.control_due or asset.control_due < timezone.localdate()):
        fail("Le contrôle obligatoire doit être régularisé.")
    asset.state = "available"
    asset.control_hold = False
    asset.save()
    audit(actor, "asset.restored", asset)
    return asset


@transaction.atomic
def prepare_supplier_request(actor, asset_id, supplier, subject, body):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    manage(actor, asset.site_id)
    item = SupplierRequest(asset=asset, supplier=supplier, subject=subject, body=body, created_by=actor)
    item.full_clean()
    item.save()
    audit(actor, "supplier_request.prepared", asset, {"request": item.pk})
    notify(managers(asset.site), "Demande fournisseur à valider", f"{subject} — {asset}.", f"supplier:{item.pk}:draft")
    return item


@transaction.atomic
def approve_supplier_request(actor, pk, approve=True):
    item = SupplierRequest.objects.select_for_update().select_related("asset", "supplier").get(pk=pk)
    manage(actor, item.asset.site_id, human_manager=True)
    if item.status != "draft":
        fail("Cette demande a déjà été traitée.")
    item.status = "approved" if approve else "rejected"
    item.approved_by = actor
    item.approved_at = timezone.now()
    item.save()
    if approve:
        Outbox.objects.create(key=f"supplier:{pk}:send", recipient=item.supplier.email,
                              subject=item.subject, body=item.body, supplier_request=item)
    audit(actor, f"supplier_request.{item.status}", item.asset, {"request": pk})
    return item


@transaction.atomic
def allocate_license(actor, license_id, user=None, asset=None):
    item = License.objects.select_for_update().get(pk=license_id)
    manage(actor, item.site_id)
    if bool(user) == bool(asset):
        fail("Choisissez une personne ou un équipement.")
    if user and (not user.is_active or user.role in ("agent", "unassigned")):
        fail("La personne doit être un utilisateur humain actif configuré.")
    if item.available_seats < 1:
        fail("Toutes les places sont affectées.")
    target_site = user.site_id if user else asset.site_id
    if target_site != item.site_id:
        fail("La cible doit appartenir au site de la licence.")
    if item.allocations.filter(user=user, asset=asset).exists():
        fail("Cette affectation existe déjà.")
    allocation = Allocation.objects.create(license=item, user=user, asset=asset)
    audit(actor, "license.allocated", asset, {"license": license_id, "allocation": allocation.pk}, site=item.site)
    return allocation


def reminders(actor):
    require(actor, ("admin", "manager", "agent"))
    today = timezone.localdate()
    permitted = sites(actor)
    for loan in Loan.objects.filter(returned_at__isnull=True, reservation__end__lt=today, reservation__asset__site__in=permitted).select_related("reservation__asset", "reservation__borrower"):
        asset = loan.reservation.asset
        notify([loan.reservation.borrower, *managers(asset.site)], "Retour en retard",
               f"{asset} était attendu le {loan.reservation.end}.", f"overdue:{loan.pk}:{today}")
    for asset in Asset.objects.filter(site__in=permitted).select_related("category"):
        if asset.control_hold:
            notify(managers(asset.site), "Remise en service à valider", f"{asset} attend une décision humaine.", f"restore:{asset.pk}:{today}")
        if asset.control_required and (not asset.control_due or asset.control_due <= today + timedelta(days=14)):
            notify(managers(asset.site), "Contrôle à prévoir", f"{asset} : échéance {asset.control_due or 'non définie'}.", f"control:{asset.pk}:{today}")
    for item in Intervention.objects.filter(asset__site__in=permitted, completed_date__isnull=True, scheduled_date__lte=today + timedelta(days=7)).select_related("asset"):
        notify(managers(item.asset.site), "Intervention à prévoir", f"{item.asset} : {item.scheduled_date}.", f"intervention:{item.pk}:{today}")
    for item in License.objects.filter(site__in=permitted, renewal_date__lte=today + timedelta(days=30)):
        notify(managers(item.site), "Renouvellement logiciel", f"{item.name} : {item.renewal_date}.", f"license:{item.pk}:{today}")
    audit(actor, "reminders.generated")


def send_outbox():
    sent = 0
    # A lock prevents competing workers from sending the same row simultaneously.
    for pk in Outbox.objects.filter(sent_at__isnull=True, attempts__lt=5).values_list("pk", flat=True):
        with transaction.atomic():
            item = Outbox.objects.select_for_update(skip_locked=True).filter(pk=pk, sent_at__isnull=True).first()
            if not item:
                continue
            item.attempts += 1
            try:
                if item.supplier_request and not item.supplier_request.approved_by_id:
                    fail("Validation fournisseur absente.")
                accepted = send_mail(item.subject, item.body, settings.DEFAULT_FROM_EMAIL, [item.recipient])
                if accepted != 1:
                    fail("Le transport e-mail n'a pas accepté le message.")
                item.sent_at = timezone.now()
                item.error = ""
                if item.supplier_request:
                    SupplierRequest.objects.filter(pk=item.supplier_request_id).update(status="sent")
                sent += 1
            except Exception as exc:
                item.error = str(exc)[:1000]
            item.save()
    return sent


@transaction.atomic
def agent_command(key, payload, operation):
    if not key or len(key) > 100:
        fail("Une clé d'idempotence de 1 à 100 caractères est obligatoire.")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    command, _ = AgentCommand.objects.get_or_create(key=key, defaults={"fingerprint": fingerprint})
    command = AgentCommand.objects.select_for_update().get(pk=command.pk)
    if command.fingerprint != fingerprint:
        fail("Cette clé a déjà été utilisée avec une autre commande.")
    if not command.result:
        command.result = operation()
        command.save()
    return command.result
