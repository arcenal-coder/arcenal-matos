from django import forms
from django.db.models import Q
from django.utils import timezone

from core.forms import DateInput
from core.models import User
from core.permissions import sites

from .models import Lot, Reference, Request, Unit


class ReferenceForm(forms.ModelForm):
    class Meta:
        model = Reference
        fields = ["name", "kind", "size", "tracking", "unit", "brand", "model", "usage_days", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.lots.exists():
            self.fields["tracking"].disabled = True
            self.fields["unit"].disabled = True
            self.fields["tracking"].help_text = "Le mode et l’unité sont conservés après la première réception."


class ReceiptForm(forms.ModelForm):
    serials = forms.CharField(label="Numéros de série (suivi individuel, facultatif)", required=False, widget=forms.Textarea,
        help_text="Un numéro par ligne, dans l’ordre des exemplaires reçus. Les identifiants EPI sont automatiques.")

    class Meta:
        model = Lot
        fields = ["reference", "site", "number", "received_on", "received_quantity", "manufacturer_expiry", "unit_price", "supplier"]
        widgets = {name: DateInput() for name in ("received_on", "manufacturer_expiry")}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = sites(actor)
        self.fields["reference"].queryset = Reference.objects.order_by("name", "size")
        self.fields["unit_price"].help_text = "Prix par pièce, paire ou boîte selon la référence. Laissez vide si le prix est inconnu."
        if self.fields["site"].queryset.count() == 1:
            self.fields["site"].initial = self.fields["site"].queryset.first().pk


class RequestForm(forms.ModelForm):
    class Meta:
        model = Request
        fields = ["reference", "site", "quantity", "reason"]

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference"].queryset = Reference.objects.order_by("name", "size")
        self.fields["site"].queryset = sites(actor)
        if actor.role == "member":
            self.fields["site"].initial = actor.site_id
            self.fields["site"].disabled = True


class LotValidityForm(forms.ModelForm):
    usage_days = forms.IntegerField(label="Durée retenue pour ce lot (jours)", min_value=1, max_value=36500, required=False,
        help_text="Laissez vide pour utiliser la durée de la référence. Les quantités et prix historiques ne sont pas modifiés.")

    class Meta:
        model = Lot
        fields = ["manufacturer_expiry", "assessed_expiry", "usage_days"]
        widgets = {name: DateInput() for name in ("manufacturer_expiry", "assessed_expiry")}


class UnitValidityForm(forms.ModelForm):
    assessed_expiry = forms.DateField(label="Date de validité retenue pour cet exemplaire", widget=DateInput(), required=False)
    usage_days = forms.IntegerField(label="Durée retenue pour cet exemplaire (jours)", min_value=1, max_value=36500, required=False,
        help_text="Laissez vide pour hériter du lot / de la référence. La première mise en service déjà connue reste inchangée.")

    class Meta:
        model = Unit
        fields = ["serial", "assessed_expiry", "usage_days"]


class IssueForm(forms.Form):
    recipient = forms.ModelChoiceField(label="Équipier bénéficiaire", queryset=User.objects.none())
    quantity = forms.IntegerField(label="Quantité remise", min_value=1, initial=1)
    unit = forms.ModelChoiceField(label="Exemplaire identifié", queryset=Unit.objects.none(), required=False)
    issued_on = forms.DateField(label="Date de remise", widget=DateInput(), initial=timezone.localdate)
    first_use_on = forms.DateField(label="Première mise en service (facultative)", widget=DateInput(), required=False,
        help_text="À défaut, la date de remise est utilisée. Une première date déjà connue reste conservée.")

    def __init__(self, *args, lot, request_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = User.objects.filter(is_active=True, role__in=["admin", "manager", "member"]).filter(
            Q(role="admin") | Q(site_id=lot.site_id) | Q(role="manager", managed_sites=lot.site_id)).distinct()
        self.fields["quantity"].max_value = lot.available_quantity
        if lot.reference.tracking == "individual":
            self.fields["unit"].queryset = lot.units.filter(state="stock").order_by("code")
            self.fields["unit"].required = True
        else:
            self.fields.pop("unit")
        if request_item:
            self.fields["recipient"].initial = request_item.requester_id
            self.fields["recipient"].disabled = True
            self.fields["quantity"].initial = 1 if lot.reference.tracking == "individual" else min(request_item.remaining, lot.available_quantity)


class DestructionForm(forms.Form):
    quantity = forms.IntegerField(label="Quantité détruite", min_value=1, initial=1)
    unit = forms.ModelChoiceField(label="Exemplaire identifié", queryset=Unit.objects.none(), required=False)
    destroyed_on = forms.DateField(label="Date de destruction", widget=DateInput(), initial=timezone.localdate)
    reason = forms.CharField(label="Motif de destruction", widget=forms.Textarea)

    def __init__(self, *args, lot, allocation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if lot.reference.tracking == "individual":
            self.fields["unit"].required = True
            self.fields["unit"].queryset = lot.units.filter(pk=allocation.unit_id) if allocation else lot.units.filter(state="stock")
            if allocation:
                self.fields["unit"].initial = allocation.unit_id
                self.fields["unit"].disabled = True
        else:
            self.fields.pop("unit")


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(label="Décision", choices=[("approve", "Accepter la demande"), ("reject", "Refuser la demande")])
    reason = forms.CharField(label="Motif / commentaire", required=False, widget=forms.Textarea)


class ProposalForm(forms.Form):
    reference = forms.ModelChoiceField(label="Référence / type d’EPI", queryset=Reference.objects.all())
    lot = forms.ModelChoiceField(label="Lot concerné (facultatif)", queryset=Lot.objects.none(), required=False)
    unit = forms.ModelChoiceField(label="Exemplaire (facultatif)", queryset=Unit.objects.none(), required=False)
    first_use_on = forms.DateField(label="Première mise en service connue (facultative)", widget=DateInput(), required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.filter(site__in=sites(actor)).select_related("reference", "site")
        self.fields["unit"].queryset = Unit.objects.filter(lot__site__in=sites(actor)).exclude(state="destroyed").order_by("code")
        self.fields["lot"].help_text = "Sans lot, l’agent propose une durée commune à la référence ; application réservée à l’administrateur."
