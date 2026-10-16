from functools import wraps
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.intake import assistance_enabled
from core.modules import enabled
from core.permissions import require, sites

from . import forms, services
from .models import AssistanceTask, Badge, Laboratory, Movement, Period, Shipment


def human(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled("dosimeters"):
            raise Http404("Module Dosimètres désactivé.")
        require(request.user, ("admin", "manager", "member"))
        return view(request, *args, **kwargs)
    return wrapped


def staff(user):
    return user.role in ("admin", "manager")


def badges(user):
    query = Badge.objects.select_related("site", "period__laboratory", "assigned_to", "shipment", "replacement_for")
    return query.filter(site__in=sites(user)) if staff(user) else query.filter(assigned_to=user)


def tasks(user):
    return AssistanceTask.objects.filter(site__in=sites(user)).select_related("site", "period__laboratory", "requester")


def page(request, template, section, **context):
    return render(request, f"dosimetry/{template}.html", {"dosimetry_page": section, "dosimetry_staff": staff(request.user), **context})


def form_page(request, title, form, section, cancel, **context):
    return page(request, "form", section, title=title, form=form, cancel_url=cancel, **context)


def show_error(form, error):
    form.add_error(None, " · ".join(error.messages))


def query_uuid(request, name):
    try:
        return UUID(request.GET[name])
    except (ValueError, TypeError, KeyError):
        raise Http404("Référence invalide.") from None


@human
def index(request):
    if not staff(request.user):
        return redirect("dosimetry:mine")
    query = badges(request.user)
    return page(request, "index", "overview", stock=query.filter(status="stock").count(), issued=query.filter(status="issued").count(),
        overdue=query.filter(status="issued", period__return_due_on__lt=timezone.localdate()).count(), collected=query.filter(status="collected").count(),
        sent=query.filter(status="sent").count(), lost=query.filter(status="lost").count())


@human
def badge_list(request, mine=False):
    if not mine:
        require(request.user, ("admin", "manager"))
    query = badges(request.user)
    if mine:
        query = query.filter(assigned_to=request.user)
    if request.GET.get("q"):
        query = query.filter(Q(code__icontains=request.GET["q"]) | Q(assigned_to__username__icontains=request.GET["q"]) | Q(period__name__icontains=request.GET["q"]))
    if request.GET.get("status") in dict(Badge.STATES):
        query = query.filter(status=request.GET["status"])
    return page(request, "badges", "mine" if mine else "badges", items=Paginator(query.order_by("-period__start_on", "code"), 50).get_page(request.GET.get("page")), mine=mine, states=Badge.STATES)


@human
def badge_detail(request, pk):
    item = get_object_or_404(badges(request.user), pk=pk)
    return page(request, "badge", "badges" if staff(request.user) else "mine", badge=item,
        history=Movement.objects.filter(badge=item).select_related("actor").order_by("created_at") if staff(request.user) else [])


@human
def receive(request):
    require(request.user, ("admin", "manager"))
    form = forms.ReceiptForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data.copy()
        data["codes"] = data["codes"].splitlines()
        try:
            items = services.receive(request.user, **data)
            messages.success(request, f"{len(items)} badge(s) reçu(s).")
            return redirect("dosimetry:badges")
        except ValidationError as error:
            show_error(form, error)
    return form_page(request, "Réceptionner des dosimètres passifs", form, "badges", reverse("dosimetry:badges"))


@human
def badge_action(request, pk, operation):
    require(request.user, ("admin", "manager"))
    badge = get_object_or_404(badges(request.user), pk=pk)
    mapping = {
        "assign": (forms.AssignForm, "Préaffecter le badge"), "issue": (forms.IssueForm, "Distribuer le badge / mettre le témoin en période"),
        "close": (forms.CloseForm, "Déclarer une perte ou une annulation"), "replace": (forms.ReplacementForm, "Réceptionner un badge de remplacement"),
    }
    if operation not in mapping:
        raise Http404
    form_class, title = mapping[operation]
    kwargs = {"badge": badge} if operation in ("assign", "issue") else {}
    form = form_class(request.POST or None, **kwargs)
    if request.method == "POST" and form.is_valid():
        try:
            if operation == "assign":
                services.preassign(request.user, badge.pk, **form.cleaned_data)
            elif operation == "issue":
                services.issue(request.user, badge.pk, **form.cleaned_data)
            elif operation == "close":
                services.close_badge(request.user, badge.pk, **form.cleaned_data)
            else:
                replacement = services.replace(request.user, badge.pk, **form.cleaned_data)
                return redirect("dosimetry:badge", pk=replacement.pk)
            return redirect("dosimetry:badge", pk=badge.pk)
        except ValidationError as error:
            show_error(form, error)
    return form_page(request, title, form, "badges", reverse("dosimetry:badge", args=[badge.pk]), badge=badge)


@human
def configuration(request, kind, pk=None):
    require(request.user, ("admin",))
    if kind not in ("laboratories", "periods"):
        raise Http404
    model, form_class, title, save = (Laboratory, forms.LaboratoryForm, "Laboratoires", services.save_laboratory) if kind == "laboratories" else (Period, forms.PeriodForm, "Périodes de port", services.save_period)
    item = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            save(request.user, form.cleaned_data, pk)
            return redirect("dosimetry:configuration", kind=kind)
        except ValidationError as error:
            show_error(form, error)
    query = model.objects.all()
    if kind == "periods":
        query = query.select_related("laboratory").order_by("-start_on")
    else:
        query = query.order_by("name")
    return page(request, "configuration", kind, kind=kind, title=title, form=form, editing=item, items=query)


@human
def operation(request, kind):
    require(request.user, ("admin", "manager"))
    if kind not in ("collection", "shipment"):
        raise Http404
    task = get_object_or_404(tasks(request.user), pk=query_uuid(request, "assistance"), kind=kind, status="ready") if request.GET.get("assistance") else None
    scope_form = forms.ScopeForm(request.GET if request.GET.get("site") or request.GET.get("period") else None, actor=request.user)
    site, period = (task.site, task.period) if task else (None, None)
    if scope_form.is_bound and scope_form.is_valid() and not task:
        site, period = scope_form.cleaned_data["site"], scope_form.cleaned_data["period"]
    initial = {"badges": task.badge_ids} if task else {}
    if request.GET.get("badge") and not task:
        badge = get_object_or_404(badges(request.user), pk=query_uuid(request, "badge"))
        site, period = badge.site, badge.period
        initial = {"badges": [badge.pk], "not_worn": badge.status == "stock"}
    form = forms.OperationForm(request.POST or None, actor=request.user, operation=kind, site=site, period=period, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        ids = list(data["badges"].values_list("pk", flat=True))
        try:
            if kind == "collection":
                services.collect(request.user, ids, data["operation_on"], data["not_worn"], task.pk if task else None)
                return redirect("dosimetry:badges")
            result = services.send(request.user, ids, data["operation_on"], data["tracking"], task.pk if task else None)
            return redirect("dosimetry:shipment", pk=result.pk)
        except ValidationError as error:
            show_error(form, error)
    return page(request, "operation", kind, title="Enregistrer une collecte / restitution" if kind == "collection" else "Confirmer un envoi au laboratoire",
        form=form, scope_form=scope_form, task=task, site=site, period=period, cancel_url=reverse("dosimetry:badges"))


@human
def shipment_list(request):
    require(request.user, ("admin", "manager"))
    query = Shipment.objects.filter(site__in=sites(request.user)).select_related("site", "period__laboratory", "actor").order_by("-sent_on", "-pk")
    return page(request, "shipments", "shipments", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def shipment_detail(request, pk):
    require(request.user, ("admin", "manager"))
    item = get_object_or_404(Shipment.objects.filter(site__in=sites(request.user)).select_related("site", "period__laboratory", "actor"), pk=pk)
    return page(request, "shipment", "shipments", shipment=item, items=item.badges.select_related("assigned_to").order_by("code"))


@human
def history(request):
    require(request.user, ("admin", "manager"))
    query = Movement.objects.select_related("actor", "badge", "site", "period").order_by("-created_at")
    if request.user.role != "admin":
        query = query.filter(site__in=sites(request.user))
    return page(request, "history", "history", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def assistance(request):
    require(request.user, ("admin", "manager"))
    form = forms.AssistanceForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            services.request_assistance(request.user, **form.cleaned_data)
            return redirect("dosimetry:assistance")
        except ValidationError as error:
            show_error(form, error)
    return page(request, "assistance", "assistance", form=form, assistance_enabled=assistance_enabled(),
        items=Paginator(tasks(request.user).order_by("-created_at"), 30).get_page(request.GET.get("page")))


@human
@require_POST
def assistance_decide(request, pk):
    require(request.user, ("admin", "manager"))
    get_object_or_404(tasks(request.user), pk=pk)
    if request.POST.get("decision") not in ("apply", "dismiss"):
        return HttpResponse("Décision invalide.", status=400)
    try:
        services.decide_assistance(request.user, pk, request.POST["decision"] == "apply")
    except ValidationError as error:
        messages.error(request, " · ".join(error.messages))
    return redirect("dosimetry:assistance")
