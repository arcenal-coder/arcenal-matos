from django import forms

from .models import Asset, Category, Intervention, License, Site, Supplier, User
from .permissions import sites


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ["code", "name", "category", "brand", "model", "serial", "site", "location", "state",
                  "purchase_date", "purchase_cost", "control_required", "last_control", "next_control", "interval_days", "custom_fields"]
        widgets = {key: DateInput() for key in ("purchase_date", "last_control", "next_control")}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = sites(actor)
        if self.instance.pk and not self.instance._state.adding:
            self.fields["site"].disabled = True
            self.fields["code"].disabled = True


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
