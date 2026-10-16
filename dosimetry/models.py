import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Laboratory(models.Model):
    name = models.CharField("Laboratoire", max_length=160, unique=True)
    address = models.TextField("Adresse d’envoi", blank=True)
    contact = models.CharField("Contact logistique", max_length=200, blank=True)

    def __str__(self):
        return self.name


class Period(models.Model):
    name = models.CharField("Nom de la période", max_length=120)
    laboratory = models.ForeignKey(Laboratory, verbose_name="Laboratoire", on_delete=models.PROTECT)
    start_on = models.DateField("Début du port")
    end_on = models.DateField("Fin du port")
    return_due_on = models.DateField("Date limite de collecte / retour")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(end_on__gte=models.F("start_on")), name="dosi_period_dates"),
            models.CheckConstraint(condition=models.Q(return_due_on__gte=models.F("end_on")), name="dosi_return_after_wear"),
            models.UniqueConstraint(fields=["laboratory", "start_on", "end_on"], name="dosi_unique_laboratory_period"),
        ]

    def __str__(self):
        return f"{self.name} · {self.laboratory}"


class AssistanceTask(models.Model):
    KINDS = [("overview", "Faire le point"), ("assignment", "Proposer des préaffectations"),
             ("collection", "Préparer une collecte"), ("shipment", "Préparer un envoi au laboratoire")]
    STATES = [("pending", "En attente de l’agent"), ("ready", "Proposition reçue"), ("applied", "Préparation utilisée"), ("dismissed", "Écartée")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT)
    period = models.ForeignKey(Period, on_delete=models.PROTECT)
    kind = models.CharField("Aide souhaitée", max_length=16, choices=KINDS, default="overview")
    question = models.TextField("Précisions utiles à l’agent", blank=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=STATES, default="pending")
    response = models.TextField(blank=True)
    assignments = models.JSONField(default=list)
    badge_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Shipment(models.Model):
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT)
    period = models.ForeignKey(Period, on_delete=models.PROTECT)
    sent_on = models.DateField("Date d’expédition", default=timezone.localdate)
    tracking = models.CharField("Référence de suivi / bordereau", max_length=160, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assistance = models.OneToOneField(AssistanceTask, on_delete=models.PROTECT, null=True, blank=True)


class Badge(models.Model):
    KINDS = [("personal", "Badge personnel"), ("witness", "Badge témoin")]
    STATES = [("stock", "En stock / à retirer"), ("issued", "Distribué / en période"), ("collected", "Collecté"),
              ("sent", "Envoyé au laboratoire"), ("lost", "Perdu"), ("cancelled", "Annulé")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField("Numéro du badge", max_length=100)
    key = models.CharField(max_length=200, editable=False)
    period = models.ForeignKey(Period, verbose_name="Période / laboratoire", on_delete=models.PROTECT, related_name="badges")
    site = models.ForeignKey("core.Site", verbose_name="Site", on_delete=models.PROTECT)
    kind = models.CharField("Nature", max_length=16, choices=KINDS, default="personal")
    wear_location = models.CharField("Emplacement de port", max_length=80, default="Corps entier", blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Équipier préaffecté (facultatif)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="passive_badges")
    status = models.CharField(max_length=16, choices=STATES, default="stock")
    received_on = models.DateField("Date de réception", default=timezone.localdate)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_badges")
    issued_on = models.DateField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="issued_badges")
    collected_on = models.DateField(null=True, blank=True)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="collected_badges")
    not_worn = models.BooleanField(default=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, null=True, blank=True, related_name="badges")
    closed_on = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True)
    replacement_for = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="replacements")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["period", "key"], name="dosi_unique_number_in_period"),
            models.CheckConstraint(condition=models.Q(kind="personal") | models.Q(assigned_to__isnull=True), name="dosi_witness_not_personal"),
        ]

    def __str__(self):
        return f"{self.code} · {self.period.name} · {self.site}"

    @property
    def overdue(self):
        return self.status == "issued" and self.period.return_due_on < timezone.localdate()


class Movement(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dosimetry_movements")
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT, null=True, blank=True, related_name="dosimetry_movements")
    badge = models.ForeignKey(Badge, on_delete=models.PROTECT, null=True, blank=True)
    period = models.ForeignKey(Period, on_delete=models.PROTECT, null=True, blank=True)
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=120)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
