from django import forms
from django.db.models import Q
from django.utils import timezone

from core.forms import DateInput
from core.models import User
from core.permissions import sites

from .models import AssistanceTask, Badge, Laboratory, Period
from .services import people


class LaboratoryForm(forms.ModelForm):
    class Meta:
        model = Laboratory
        fields = ["name", "address", "contact"]


class PeriodForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = ["name", "laboratory", "start_on", "end_on", "return_due_on"]
        widgets = {name: DateInput() for name in ("start_on", "end_on", "return_due_on")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.badges.exists():
            for name in ("laboratory", "start_on", "end_on"):
                self.fields[name].disabled = True


class ReceiptForm(forms.Form):
    site = forms.ModelChoiceField(label="Site", queryset=None)
    period = forms.ModelChoiceField(label="Période / laboratoire", queryset=Period.objects.select_related("laboratory").order_by("-start_on"))
    codes = forms.CharField(label="Numéros des badges", widget=forms.Textarea, max_length=100000,
        help_text="Un numéro par ligne. Un même numéro sur une autre période reste un badge distinct.")
    received_on = forms.DateField(label="Date de réception", widget=DateInput(), initial=timezone.localdate)
    kind = forms.ChoiceField(label="Nature", choices=Badge.KINDS)
    wear_location = forms.CharField(label="Emplacement de port", max_length=80, required=False, initial="Corps entier")
    assigned_to = forms.ModelChoiceField(label="Équipier préaffecté (un seul badge personnel)", queryset=User.objects.none(), required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        scope = sites(actor)
        self.fields["site"].queryset = scope
        if scope.count() == 1:
            self.fields["site"].initial = scope.first().pk
        self.fields["assigned_to"].queryset = User.objects.filter(is_active=True, role__in=("admin", "manager", "member")).filter(
            Q(role="admin") | Q(site__in=scope) | Q(role="manager", managed_sites__in=scope)).distinct()


class AssignForm(forms.Form):
    recipient = forms.ModelChoiceField(label="Équipier", queryset=User.objects.none())

    def __init__(self, *args, badge, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = people(badge.site_id)
        if badge.assigned_to_id:
            self.fields["recipient"].initial = badge.assigned_to_id
            self.fields["recipient"].disabled = True


class IssueForm(AssignForm):
    issued_on = forms.DateField(label="Date de distribution / mise en période", widget=DateInput(), initial=timezone.localdate)

    def __init__(self, *args, badge, **kwargs):
        super().__init__(*args, badge=badge, **kwargs)
        if badge.kind == "witness":
            self.fields.pop("recipient")


class ScopeForm(forms.Form):
    site = forms.ModelChoiceField(label="Site", queryset=None)
    period = forms.ModelChoiceField(label="Période / laboratoire", queryset=Period.objects.select_related("laboratory").order_by("-start_on"))

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = sites(actor)


class BadgeSelection(forms.ModelMultipleChoiceField):
    def label_from_instance(self, badge):
        return f"{badge.code} · {badge.assigned_to or badge.get_kind_display()} · {badge.period.name} · {badge.site} · {badge.get_status_display()}"


class OperationForm(forms.Form):
    badges = BadgeSelection(label="Badges concernés", queryset=Badge.objects.none(), widget=forms.CheckboxSelectMultiple)
    operation_on = forms.DateField(label="Date de collecte", widget=DateInput(), initial=timezone.localdate)
    not_worn = forms.BooleanField(label="Badges non portés / retour de badges restés en stock", required=False)
    tracking = forms.CharField(label="Référence de suivi / bordereau", max_length=160, required=False)

    def __init__(self, *args, actor, operation, site=None, period=None, **kwargs):
        super().__init__(*args, **kwargs)
        query = Badge.objects.filter(site__in=sites(actor)).select_related("period", "site", "assigned_to").order_by("code")
        query = query.filter(status="collected") if operation == "shipment" else query.filter(status__in=("stock", "issued"))
        if site:
            query = query.filter(site=site)
        if period:
            query = query.filter(period=period)
        self.fields["badges"].queryset = query
        if operation == "shipment":
            self.fields.pop("not_worn")
            self.fields["operation_on"].label = "Date d’expédition réelle"
        else:
            self.fields.pop("tracking")


class CloseForm(forms.Form):
    status = forms.ChoiceField(label="État à enregistrer", choices=[("lost", "Perdu"), ("cancelled", "Annulé (enregistrement erroné en stock)")],
        help_text="Pour retourner un badge resté en stock au laboratoire, utilisez plutôt Retourner non porté.")
    closed_on = forms.DateField(label="Date réelle", widget=DateInput(), initial=timezone.localdate)
    reason = forms.CharField(label="Motif", widget=forms.Textarea)


class ReplacementForm(forms.Form):
    new_code = forms.CharField(label="Numéro du badge de remplacement", max_length=100)
    received_on = forms.DateField(label="Date de réception du remplacement", widget=DateInput(), initial=timezone.localdate)


class AssistanceForm(ScopeForm):
    kind = forms.ChoiceField(label="Aide souhaitée", choices=AssistanceTask.KINDS)
    question = forms.CharField(label="Précisions logistiques", widget=forms.Textarea, required=False, max_length=4000)
