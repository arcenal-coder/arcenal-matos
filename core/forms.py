from django import forms

from .agent_links import validate_destination
from .models import (
    Asset,
    AssistanceSettings,
    Brand,
    Category,
    DeviceModel,
    Intervention,
    License,
    ModuleSettings,
    Site,
    Supplier,
    User,
)
from .permissions import sites


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class ModuleSettingsForm(forms.ModelForm):
    class Meta:
        model = ModuleSettings
        fields = ["epi_enabled", "dosimeters_enabled"]


class AgentSSOForm(forms.ModelForm):
    class Meta:
        model = AssistanceSettings
        fields = ["sso_url"]
        help_texts = {"sso_url": "Chemin public du service s’il est publié sous le même domaine, sinon son URL HTTPS. Sans paramètre ni identifiant. Localhost désigne le poste de l’utilisateur dans son navigateur."}

    def clean_sso_url(self):
        return validate_destination(self.cleaned_data["sso_url"])


class AssetForm(forms.ModelForm):
    brand = forms.ChoiceField(label="Marque", required=False)
    model = forms.ChoiceField(label="Modèle", required=False)

    class Meta:
        model = Asset
        fields = ["name", "category", "brand", "model", "serial", "site", "location", "state",
                  "purchase_date", "purchase_cost", "control_required", "last_control", "next_control", "interval_days"]
        widgets = {key: DateInput() for key in ("purchase_date", "last_control", "next_control")}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = sites(actor)
        brands = list(Brand.objects.order_by("name").values_list("name", flat=True))
        if self.instance.brand and self.instance.brand not in brands:
            brands.append(self.instance.brand)
        self.fields["brand"].choices = [("", "Choisir une marque (facultatif)")] + [(name, name) for name in brands]
        brand = self.data.get("brand", self.instance.brand) if self.is_bound else self.instance.brand
        models = list(DeviceModel.objects.filter(brand__name=brand).order_by("name").values_list("name", flat=True))
        if self.instance.model and brand == self.instance.brand and self.instance.model not in models:
            models.append(self.instance.model)
        self.fields["model"].choices = [("", "Choisir un modèle (facultatif)")] + [(name, name) for name in models]
        self.fields["category"].label = "Type d’appareil / catégorie"
        self.fields["interval_days"].label = "Contrôle tous les (jours)"
        self.fields["interval_days"].help_text = "Laissez vide pour utiliser la périodicité de la catégorie. L’agent peut la renseigner s’il est activé."
        if not self.is_bound and self.instance._state.adding and self.fields["site"].queryset.count() == 1:
            self.fields["site"].initial = self.fields["site"].queryset.first().pk
        if self.instance.pk and not self.instance._state.adding:
            self.fields["site"].disabled = True
        self.primary_fields = [self[name] for name in ("name", "category", "brand", "model", "serial", "site", "location", "state")]
        self.detail_fields = [self[name] for name in ("purchase_date", "purchase_cost", "control_required", "last_control", "next_control", "interval_days")]


class ReservationForm(forms.Form):
    start = forms.DateField(label="Date de début", widget=DateInput())
    end = forms.DateField(label="Retour prévu", widget=DateInput())
    reason = forms.CharField(label="Motif", widget=forms.Textarea, required=False)


class MovementForm(forms.Form):
    condition = forms.CharField(label="État du matériel", widget=forms.Textarea)
    comment = forms.CharField(label="Commentaire", widget=forms.Textarea, required=False)
    damaged = forms.BooleanField(label="Matériel endommagé au retour", required=False)
    photo = forms.FileField(label="Photo / document (facultatif)", required=False)


class InterventionForm(forms.ModelForm):
    class Meta:
        model = Intervention
        fields = ["supplier", "scheduled_date", "description", "cost", "is_control"]
        widgets = {"scheduled_date": DateInput()}


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["role", "site", "managed_sites"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [choice for choice in User.ROLES if choice[0] != "agent"]


class LicenseForm(forms.ModelForm):
    class Meta:
        model = License
        fields = ["name", "site", "kind", "seats", "cost", "renewal_date", "notes"]
        widgets = {"renewal_date": DateInput()}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = sites(actor)
        if self.instance.pk:
            self.fields["site"].disabled = True


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["name", "address"]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "interval_days"]


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "email", "phone"]
