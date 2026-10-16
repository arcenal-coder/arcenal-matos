import unicodedata
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify


def reference_key(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class Site(models.Model):
    name = models.CharField("Nom", max_length=120, unique=True)
    address = models.TextField("Adresse", blank=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLES = [("unassigned", "À configurer"), ("admin", "Administrateur"),
             ("manager", "Gestionnaire"), ("member", "Collaborateur"), ("agent", "Agent logisticien")]
    role = models.CharField("Rôle", max_length=20, choices=ROLES, default="unassigned")
    site = models.ForeignKey(Site, verbose_name="Site de rattachement", null=True, blank=True, on_delete=models.PROTECT)
    managed_sites = models.ManyToManyField(Site, verbose_name="Sites gérés", blank=True, related_name="managers")

    def save(self, *args, **kwargs):
        if self.has_usable_password():
            self.set_unusable_password()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username


class Category(models.Model):
    name = models.CharField("Nom", max_length=120, unique=True)
    interval_days = models.PositiveIntegerField("Contrôle tous les (jours)", null=True, blank=True,
                                               validators=[MinValueValidator(1)])

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = Category.objects.filter(pk=self.pk).first() if self.pk else None
            if previous and previous.interval_days != self.interval_days:
                affected = Asset.objects.filter(category_id=self.pk, control_required=True).select_related("category")
                expired = [item.pk for item in affected if not item.control_due or item.control_due < timezone.localdate()]
                Asset.objects.filter(pk__in=expired).update(control_hold=True)
            super().save(*args, **kwargs)


class AssetSequence(models.Model):
    category = models.OneToOneField(Category, primary_key=True, on_delete=models.CASCADE)
    last_number = models.PositiveBigIntegerField(default=0)


class Brand(models.Model):
    name = models.CharField("Marque", max_length=100)
    key = models.CharField(max_length=200, unique=True, editable=False)

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())
        self.key = reference_key(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DeviceModel(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="models")
    name = models.CharField("Modèle", max_length=100)
    key = models.CharField(max_length=200, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["brand", "key"], name="unique_brand_model")]

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())
        self.key = reference_key(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class AssistanceSettings(models.Model):
    enabled = models.BooleanField("Activer l’assistance à la saisie par l’agent MCP", default=False)


class ModuleSettings(models.Model):
    epi_enabled = models.BooleanField("Activer le module EPI", default=True)
    dosimeters_enabled = models.BooleanField("Activer le module Dosimètres passifs", default=False)


class IntakeRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    name = models.CharField(max_length=200, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(upload_to="intake/%Y/%m/", blank=True)
    status = models.CharField(max_length=16, default="pending", choices=[("pending", "En attente"), ("done", "Traitée")])
    serial = models.CharField(max_length=120, blank=True)
    interval_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Asset(models.Model):
    STATES = [("available", "Disponible"), ("maintenance", "En maintenance"),
              ("damaged", "Endommagé"), ("lost", "Perdu"), ("retired", "Retiré du parc")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField("Identifiant", max_length=64, unique=True, validators=[
        RegexValidator(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", "Utilisez lettres, chiffres, points, tirets ou underscores.")])
    name = models.CharField("Nom", max_length=200)
    category = models.ForeignKey(Category, verbose_name="Catégorie", on_delete=models.PROTECT)
    brand = models.CharField("Marque", max_length=100, blank=True)
    model = models.CharField("Modèle", max_length=100, blank=True)
    serial = models.CharField("Numéro de série", max_length=120, blank=True)
    site = models.ForeignKey(Site, verbose_name="Site", on_delete=models.PROTECT)
    location = models.CharField("Emplacement", max_length=200, blank=True)
    state = models.CharField("État", max_length=20, choices=STATES, default="available")
    assigned_to = models.ForeignKey(User, verbose_name="Personne affectée", null=True, blank=True, on_delete=models.PROTECT)
    purchase_date = models.DateField("Date d'achat", null=True, blank=True)
    purchase_cost = models.DecimalField("Coût d'achat (€)", max_digits=12, decimal_places=2, null=True, blank=True,
                                       validators=[MinValueValidator(0)])
    control_required = models.BooleanField("Contrôle obligatoire", default=False)
    control_hold = models.BooleanField("Remise en service humaine requise", default=False, editable=False)
    last_control = models.DateField("Dernier contrôle", null=True, blank=True)
    next_control = models.DateField("Prochain contrôle", null=True, blank=True)
    interval_days = models.PositiveIntegerField("Périodicité personnalisée (jours)", null=True, blank=True,
                                               validators=[MinValueValidator(1)])
    custom_fields = models.JSONField("Champs personnalisés (JSON)", default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.code:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            category = Category.objects.select_for_update().get(pk=self.category_id)
            sequence, _ = AssetSequence.objects.get_or_create(category=category)
            # The category id disambiguates identical/truncated type labels.
            prefix = (slugify(category.name).upper().replace("-", "")[:12] or "MAT") + f"-{category.pk}"
            while True:
                sequence.last_number += 1
                self.code = f"{prefix}-{sequence.last_number:06d}"
                if not Asset.objects.filter(code=self.code).exists():
                    break
            sequence.save(update_fields=["last_number"])
            return super().save(*args, **kwargs)

    @property
    def control_due(self):
        if self.next_control:
            return self.next_control
        interval = self.interval_days or self.category.interval_days
        return self.last_control + timedelta(days=interval) if self.last_control and interval else None

    @property
    def blocked(self):
        return self.control_hold or self.state != "available" or (self.control_required and (
            not self.control_due or self.control_due < timezone.localdate()))

    def __str__(self):
        return f"{self.code} · {self.name}"

    def clean(self):
        if not isinstance(self.custom_fields, dict):
            raise ValidationError({"custom_fields": "Un objet JSON est nécessaire (exemple : {\"couleur\": \"bleu\"})."})


class Reservation(models.Model):
    STATES = [("pending", "En attente"), ("approved", "Validée"), ("rejected", "Refusée"),
              ("cancelled", "Annulée"), ("out", "En cours"), ("returned", "Retournée")]
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="reservations")
    borrower = models.ForeignKey(User, on_delete=models.PROTECT, related_name="reservations")
    start = models.DateField("Début")
    end = models.DateField("Retour prévu")
    reason = models.TextField("Motif", blank=True)
    status = models.CharField(max_length=20, choices=STATES, default="pending")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="approvals")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(end__gte=models.F("start")), name="reservation_dates")]

    def __str__(self):
        return f"Prêt #{self.pk} · {self.asset}"


class Loan(models.Model):
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name="loan")
    checked_out_at = models.DateTimeField(default=timezone.now)
    checked_out_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="checkouts")
    checkout_condition = models.TextField("État à la sortie")
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="returns")
    return_condition = models.TextField("État au retour", blank=True)
    comment = models.TextField("Commentaire", blank=True)


class Transfer(models.Model):
    STATES = [("planned", "Prévu"), ("transit", "En transit"), ("received", "Reçu")]
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="transfers")
    source = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="outgoing")
    destination = models.ForeignKey(Site, verbose_name="Destination", on_delete=models.PROTECT, related_name="incoming")
    status = models.CharField(max_length=20, choices=STATES, default="planned")
    comment = models.TextField("Commentaire", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Supplier(models.Model):
    name = models.CharField("Nom", max_length=200)
    email = models.EmailField("E-mail")
    phone = models.CharField("Téléphone", max_length=50, blank=True)

    def __str__(self):
        return self.name


class Intervention(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="interventions")
    supplier = models.ForeignKey(Supplier, verbose_name="Prestataire", on_delete=models.PROTECT, null=True, blank=True)
    scheduled_date = models.DateField("Date prévue")
    completed_date = models.DateField("Date réalisée", null=True, blank=True)
    description = models.TextField("Description")
    cost = models.DecimalField("Coût (€)", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    is_control = models.BooleanField("Contrôle périodique", default=False)


class SupplierRequest(models.Model):
    STATES = [("draft", "À valider"), ("approved", "Validée"), ("sent", "Envoyée"), ("rejected", "Refusée")]
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    subject = models.CharField("Objet", max_length=200)
    body = models.TextField("Message")
    status = models.CharField(max_length=20, choices=STATES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="supplier_drafts")
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="supplier_approvals")
    approved_at = models.DateTimeField(null=True, blank=True)


class License(models.Model):
    name = models.CharField("Logiciel / abonnement", max_length=200)
    site = models.ForeignKey(Site, verbose_name="Site", on_delete=models.PROTECT)
    kind = models.CharField("Type", max_length=20, choices=[("license", "Licence"), ("subscription", "Abonnement")])
    seats = models.PositiveIntegerField("Places", default=1, validators=[MinValueValidator(1)])
    cost = models.DecimalField("Coût (€)", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    renewal_date = models.DateField("Renouvellement", null=True, blank=True)
    notes = models.TextField("Notes", blank=True)

    @property
    def available_seats(self):
        return self.seats - self.allocations.count()

    def __str__(self):
        return self.name


class Allocation(models.Model):
    license = models.ForeignKey(License, on_delete=models.PROTECT, related_name="allocations")
    user = models.ForeignKey(User, verbose_name="Personne", on_delete=models.PROTECT, null=True, blank=True)
    asset = models.ForeignKey(Asset, verbose_name="Équipement", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(user__isnull=False, asset__isnull=True) |
                                                        models.Q(user__isnull=True, asset__isnull=False)), name="allocation_one_target")]


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="documents")
    intervention = models.ForeignKey(Intervention, null=True, blank=True, on_delete=models.PROTECT)
    loan = models.ForeignKey(Loan, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/%Y/%m")
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Event(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    site = models.ForeignKey(Site, null=True, blank=True, on_delete=models.PROTECT)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def action_label(self):
        labels = {
            "asset.created": "Fiche créée", "asset.updated": "Fiche modifiée", "asset.imported": "Fiche importée",
            "asset.assigned": "Affectation mise à jour", "asset.restored": "Remise en service humaine",
            "reservation.created": "Demande de prêt", "reservation.approved": "Prêt validé",
            "reservation.rejected": "Demande refusée", "reservation.cancelled": "Demande annulée",
            "loan.checkout": "Sortie du matériel", "loan.return": "Retour du matériel",
            "maintenance.planned": "Intervention planifiée", "maintenance.completed": "Intervention terminée",
            "transfer.planned": "Transfert prévu", "transfer.transit": "Transfert expédié", "transfer.received": "Transfert reçu",
            "supplier_request.prepared": "Demande fournisseur préparée", "supplier_request.approved": "Demande fournisseur validée",
            "supplier_request.rejected": "Demande fournisseur refusée", "document.uploaded": "Document ajouté",
            "license.saved": "Licence enregistrée", "license.allocated": "Place affectée", "license.unallocated": "Place libérée",
            "report.generated": "Rapport généré", "reminders.generated": "Rappels préparés", "agent.yaml_exported": "Liaison YAML exportée",
            "site.saved": "Site enregistré", "category.saved": "Catégorie enregistrée", "user.saved": "Profil attribué",
            "supplier.saved": "Fournisseur enregistré",
            "modules.configured": "Activation des modules modifiée",
        }
        return labels.get(self.action, self.action)


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    body = models.TextField()
    key = models.CharField(max_length=200, unique=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Outbox(models.Model):
    key = models.CharField(max_length=200, unique=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    supplier_request = models.OneToOneField(SupplierRequest, null=True, blank=True, on_delete=models.PROTECT)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AgentCommand(models.Model):
    key = models.CharField(max_length=100, unique=True)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
