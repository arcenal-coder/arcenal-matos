import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def earliest(*dates):
    known = [value for value in dates if value is not None]
    return min(known) if known else None


class Reference(models.Model):
    MODES = [("bulk", "Quantités et lots"), ("individual", "Chaque exemplaire identifié")]
    UNITS = [("piece", "Pièce"), ("pair", "Paire"), ("box", "Boîte")]
    name = models.CharField("Nom de la référence", max_length=160)
    kind = models.CharField("Type d’EPI", max_length=100, help_text="Exemple : gants, chaussures, casque ou harnais.")
    brand = models.CharField("Marque", max_length=100, blank=True)
    model = models.CharField("Modèle", max_length=100, blank=True)
    size = models.CharField("Taille / pointure", max_length=40, blank=True)
    tracking = models.CharField("Suivi", max_length=16, choices=MODES, default="bulk")
    unit = models.CharField("Unité de stock", max_length=16, choices=UNITS, default="piece")
    usage_days = models.PositiveIntegerField("Durée après première mise en service (jours)", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(36500)])
    notes = models.TextField("Indications du fabricant", blank=True)

    def __str__(self):
        return f"{self.name} · {self.size}" if self.size else self.name


class Sequence(models.Model):
    reference = models.OneToOneField(Reference, primary_key=True, on_delete=models.CASCADE)
    last_number = models.PositiveBigIntegerField(default=0)


class Lot(models.Model):
    reference = models.ForeignKey(Reference, verbose_name="Référence EPI", on_delete=models.PROTECT, related_name="lots")
    site = models.ForeignKey("core.Site", verbose_name="Site", on_delete=models.PROTECT)
    number = models.CharField("Numéro / nom du lot", max_length=100)
    received_on = models.DateField("Date de réception", default=timezone.localdate)
    received_quantity = models.PositiveIntegerField("Quantité reçue", validators=[MinValueValidator(1)])
    available_quantity = models.PositiveIntegerField(default=0)
    manufacturer_expiry = models.DateField("Date limite fabricant", null=True, blank=True)
    assessed_expiry = models.DateField("Date de validité retenue", null=True, blank=True)
    usage_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(36500)])
    unit_price = models.DecimalField("Prix d’achat unitaire HT (€)", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)])
    supplier = models.CharField("Fournisseur (facultatif)", max_length=200, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(available_quantity__lte=models.F("received_quantity")), name="epi_lot_available_lte_received")]

    def __str__(self):
        return f"{self.reference} · lot {self.number} · {self.site}"

    @property
    def valid_until(self):
        return earliest(self.manufacturer_expiry, self.assessed_expiry)

    @property
    def expired(self):
        return bool(self.valid_until and self.valid_until < timezone.localdate())

    @property
    def stock_value(self):
        return self.unit_price * self.available_quantity if self.unit_price is not None else None

    @property
    def effective_usage_days(self):
        return self.usage_days or self.reference.usage_days


class Unit(models.Model):
    STATES = [("stock", "En stock"), ("issued", "Distribué"), ("destroyed", "Détruit")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="units")
    code = models.CharField("Identifiant EPI", max_length=64, unique=True)
    serial = models.CharField("Numéro de série", max_length=120, blank=True)
    state = models.CharField(max_length=16, choices=STATES, default="stock")
    first_use_on = models.DateField(null=True, blank=True)
    assessed_expiry = models.DateField(null=True, blank=True)
    usage_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(36500)])

    def __str__(self):
        return self.code + (f" · {self.serial}" if self.serial else "")

    @property
    def valid_until(self):
        duration = self.effective_usage_days
        service_end = self.first_use_on + timedelta(days=duration) if self.first_use_on and duration else None
        return earliest(self.lot.valid_until, self.assessed_expiry, service_end)

    @property
    def expired(self):
        return bool(self.valid_until and self.valid_until < timezone.localdate())

    @property
    def effective_usage_days(self):
        return self.usage_days or self.lot.effective_usage_days


class Request(models.Model):
    STATES = [("pending", "À traiter"), ("approved", "Acceptée, à remettre"), ("partial", "Partiellement remise"),
              ("fulfilled", "Remise effectuée"), ("rejected", "Refusée"), ("cancelled", "Annulée")]
    reference = models.ForeignKey(Reference, verbose_name="EPI souhaité / taille", on_delete=models.PROTECT)
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="epi_requests")
    quantity = models.PositiveIntegerField("Quantité souhaitée", default=1, validators=[MinValueValidator(1)])
    fulfilled_quantity = models.PositiveIntegerField(default=0)
    reason = models.TextField("Motif / besoin", blank=True)
    status = models.CharField(max_length=16, choices=STATES, default="pending")
    decision_reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="epi_decisions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(fulfilled_quantity__lte=models.F("quantity")), name="epi_request_fulfilled_lte_requested")]

    @property
    def remaining(self):
        return self.quantity - self.fulfilled_quantity


class Allocation(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="allocations")
    unit = models.OneToOneField(Unit, on_delete=models.PROTECT, null=True, blank=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="epi_allocations")
    request = models.ForeignKey(Request, on_delete=models.PROTECT, null=True, blank=True, related_name="allocations")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    active_quantity = models.PositiveIntegerField()
    issued_on = models.DateField(default=timezone.localdate)
    first_use_on = models.DateField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="epi_issues")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(active_quantity__lte=models.F("quantity")), name="epi_allocation_active_lte_issued")]

    @property
    def valid_until(self):
        duration = self.unit.effective_usage_days if self.unit_id else self.lot.effective_usage_days
        service_end = self.first_use_on + timedelta(days=duration) if duration else None
        return earliest(self.lot.valid_until, self.unit.valid_until if self.unit_id else None, service_end)

    @property
    def expired(self):
        return bool(self.valid_until and self.valid_until < timezone.localdate())

    @property
    def cost(self):
        return self.unit_price * self.quantity if self.unit_price is not None else None


class Destruction(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT)
    allocation = models.ForeignKey(Allocation, on_delete=models.PROTECT, null=True, blank=True)
    unit = models.OneToOneField(Unit, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    destroyed_on = models.DateField(default=timezone.localdate)
    reason = models.TextField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    @property
    def cost(self):
        return self.unit_price * self.quantity if self.unit_price is not None else None


class Movement(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    site = models.ForeignKey("core.Site", on_delete=models.PROTECT, null=True, blank=True)
    reference = models.ForeignKey(Reference, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ValidityProposal(models.Model):
    STATES = [("pending", "En attente de l’agent"), ("ready", "Proposition reçue"), ("applied", "Appliquée"), ("dismissed", "Écartée")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.ForeignKey(Reference, on_delete=models.PROTECT)
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    first_use_on = models.DateField(null=True, blank=True)
    proposed_date = models.DateField(null=True, blank=True)
    proposed_usage_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(36500)])
    explanation = models.TextField(blank=True)
    source = models.TextField(blank=True)
    missing_information = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
