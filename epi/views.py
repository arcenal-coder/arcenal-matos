from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.agent_links import destination as assistance_destination
from core.intake import assistance_enabled
from core.modules import enabled
from core.permissions import require, sites

from . import forms, services
from .models import (
    Allocation,
    Destruction,
    Lot,
    Movement,
    Reference,
    Request,
    Unit,
    ValidityProposal,
)


def human(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not enabled("epi"):
            raise Http404("Module EPI désactivé.")
        require(request.user, ("admin", "manager", "member"))
        return view(request, *args, **kwargs)
    return wrapped


def is_staff(user):
    return user.role in ("admin", "manager")


def page(request, template, section, **context):
    return render(request, f"epi/{template}.html", {"epi_page": section, "epi_staff": is_staff(request.user),
        "agent_sso_ready": bool(assistance_destination()), **context})


def lots(user):
    return Lot.objects.filter(site__in=sites(user)).select_related("reference", "site")


def allocations(user):
    query = Allocation.objects.select_related("lot__reference", "lot__site", "unit__lot__reference", "recipient")
    return query.filter(lot__site__in=sites(user)) if is_staff(user) else query.filter(recipient=user)


def proposals(user):
    query = ValidityProposal.objects.select_related("reference", "lot__site", "unit", "requester")
    return query if user.role == "admin" else query.filter(Q(lot__site__in=sites(user)) | Q(lot__isnull=True, requester=user))


def error(form, exc):
    form.add_error(None, " · ".join(exc.messages))


def related_id(request, name):
    try:
        value = int(request.GET[name])
        if value < 1:
            raise ValueError
        return value
    except (ValueError, KeyError):
        raise Http404("Référence invalide.") from None


def form_page(request, title, form, cancel_url, **context):
    return page(request, "form", context.pop("section", "stock"), title=title, form=form, cancel_url=cancel_url, **context)


def money(items, quantity_field):
    total = sum(getattr(item, quantity_field) * item.unit_price for item in items if item.unit_price is not None)
    unknown = sum(1 for item in items if item.unit_price is None)
    return {"total": total, "unknown": unknown}


@human
def index(request):
    if not is_staff(request.user):
        return redirect("epi:my-equipment")
    stock = list(lots(request.user).filter(available_quantity__gt=0))
    distributed = list(allocations(request.user))
    destroyed = list(Destruction.objects.filter(lot__site__in=sites(request.user)))
    return page(request, "index", "overview", stock_lots=len(stock), active_allocations=sum(item.active_quantity > 0 for item in distributed),
        pending_requests=Request.objects.filter(site__in=sites(request.user), status="pending").count(),
        expired_allocations=sum(item.active_quantity > 0 and item.expired for item in distributed),
        stock_value=money(stock, "available_quantity"), issued_value=money(distributed, "quantity"), destroyed_value=money(destroyed, "quantity"))


@human
def catalogue(request):
    query = Reference.objects.order_by("kind", "name", "size")
    if request.GET.get("q"):
        query = query.filter(Q(name__icontains=request.GET["q"]) | Q(kind__icontains=request.GET["q"]) | Q(size__icontains=request.GET["q"]))
    return page(request, "catalogue", "catalogue", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def reference_edit(request, pk=None):
    require(request.user, ("admin",) if pk else ("admin", "manager"))
    item = get_object_or_404(Reference, pk=pk) if pk else None
    form = forms.ReferenceForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_reference(request.user, form.cleaned_data, item.pk if item else None)
            return redirect("epi:catalogue")
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, "Modifier une référence EPI" if item else "Ajouter une référence EPI", form, reverse("epi:catalogue"), section="catalogue")


@human
def stock(request):
    require(request.user, ("admin", "manager"))
    query = lots(request.user).order_by("reference__name", "received_on")
    if request.GET.get("q"):
        query = query.filter(Q(reference__name__icontains=request.GET["q"]) | Q(number__icontains=request.GET["q"]))
    return page(request, "stock", "stock", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def receipt(request):
    require(request.user, ("admin", "manager"))
    form = forms.ReceiptForm(request.POST or None, actor=request.user, initial={"reference": request.GET.get("reference")})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            lot = services.receive(request.user, data["reference"], data["site"], data["number"], data["received_on"], data["received_quantity"],
                data["manufacturer_expiry"], data["unit_price"], data["supplier"], [value.strip() for value in data["serials"].splitlines() if value.strip()])
            return redirect("epi:lot", pk=lot.pk)
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, "Réceptionner des EPI", form, reverse("epi:stock"))


@human
def lot_detail(request, pk):
    require(request.user, ("admin", "manager"))
    lot = get_object_or_404(lots(request.user), pk=pk)
    units = lot.units.select_related("lot__reference").order_by("code")
    return page(request, "lot", "stock", lot=lot, units=Paginator(units, 100).get_page(request.GET.get("page")))


@human
def validity_edit(request, pk, individual=False):
    require(request.user, ("admin", "manager"))
    if individual:
        unit = get_object_or_404(Unit.objects.select_related("lot__reference"), pk=pk, lot__site__in=sites(request.user))
        lot, target, form_class = unit.lot, unit, forms.UnitValidityForm
    else:
        lot = get_object_or_404(lots(request.user), pk=pk)
        unit, target, form_class = None, lot, forms.LotValidityForm
    form = form_class(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        try:
            services.set_validity(request.user, lot.pk, form.cleaned_data, unit.pk if unit else None)
            return redirect("epi:lot", pk=lot.pk)
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, f"Renseigner la validité · {unit or lot.number}", form, reverse("epi:lot", args=[lot.pk]), lot=lot,
        help_text="Les dates renseignées sont tracées. Le prix, les quantités, l’identifiant et la première mise en service restent conservés.")


@human
def request_list(request):
    query = Request.objects.select_related("reference", "requester", "site").order_by("-created_at")
    query = query.filter(site__in=sites(request.user)) if is_staff(request.user) else query.filter(requester=request.user)
    return page(request, "requests", "requests", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def request_create(request):
    form = forms.RequestForm(request.POST or None, actor=request.user, initial={"reference": request.GET.get("reference")})
    if request.method == "POST" and form.is_valid():
        try:
            item = services.request_epi(request.user, **form.cleaned_data)
            return redirect("epi:request", pk=item.pk)
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, "Demander un EPI", form, reverse("epi:requests"), section="requests")


@human
def request_detail(request, pk):
    query = Request.objects.select_related("reference", "requester", "site")
    query = query.filter(site__in=sites(request.user)) if is_staff(request.user) else query.filter(requester=request.user)
    item = get_object_or_404(query, pk=pk)
    form = forms.DecisionForm(request.POST or None)
    if request.method == "POST":
        require(request.user, ("admin", "manager"))
        if form.is_valid():
            try:
                services.decide(request.user, item.pk, form.cleaned_data["decision"] == "approve", form.cleaned_data["reason"])
                return redirect("epi:request", pk=item.pk)
            except ValidationError as exc:
                error(form, exc)
    possible_lots = lots(request.user).filter(reference=item.reference, site=item.site, available_quantity__gt=0) if is_staff(request.user) else []
    return page(request, "request", "requests", item=item, form=form, possible_lots=possible_lots,
        can_cancel=item.requester_id == request.user.pk and item.status in ("pending", "approved"))


@human
@require_POST
def cancel(request, pk):
    try:
        services.cancel_request(request.user, pk)
    except Request.DoesNotExist:
        return HttpResponse(status=404)
    except ValidationError as exc:
        return HttpResponse(" · ".join(exc.messages), status=403)
    return redirect("epi:requests")


@human
def issue(request, pk):
    require(request.user, ("admin", "manager"))
    lot = get_object_or_404(lots(request.user), pk=pk)
    item = None
    if request.GET.get("request"):
        item = get_object_or_404(Request, pk=related_id(request, "request"), site=lot.site, reference=lot.reference, status__in=("approved", "partial"))
    form = forms.IssueForm(request.POST or None, lot=lot, request_item=item)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.issue(request.user, lot.pk, data["recipient"], data["quantity"], data["issued_on"], data["first_use_on"],
                data["unit"].pk if data.get("unit") else None, item.pk if item else None)
            return redirect("epi:request", pk=item.pk) if item else redirect("epi:distributed")
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, f"Remettre {lot.reference}", form, reverse("epi:stock"), lot=lot,
        help_text="La remise décrémente le stock. Pour une remise ancienne, indiquez sa date réelle et une réception antérieure.")


@human
def distributed(request, mine=False):
    if not mine:
        require(request.user, ("admin", "manager"))
    query = allocations(request.user)
    if mine:
        query = query.filter(recipient=request.user)
    return page(request, "allocations", "mine" if mine else "distributed", items=Paginator(query.order_by("-issued_on", "-pk"), 50).get_page(request.GET.get("page")), mine=mine)


@human
def destroy(request, pk):
    require(request.user, ("admin", "manager"))
    lot = get_object_or_404(lots(request.user), pk=pk)
    allocation = get_object_or_404(allocations(request.user), pk=related_id(request, "allocation"), lot=lot, active_quantity__gt=0) if request.GET.get("allocation") else None
    form = forms.DestructionForm(request.POST or None, lot=lot, allocation=allocation)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.destroy(request.user, lot.pk, data["quantity"], data["destroyed_on"], data["reason"],
                allocation.pk if allocation else None, data["unit"].pk if data.get("unit") else None)
            return redirect("epi:destroyed")
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, f"Enregistrer une destruction · {lot.reference}", form, reverse("epi:distributed") if allocation else reverse("epi:stock"),
        lot=lot, help_text=f"Depuis la dotation de {allocation.recipient}." if allocation else "Depuis le stock non distribué.")


@human
def destroyed(request):
    require(request.user, ("admin", "manager"))
    query = Destruction.objects.filter(lot__site__in=sites(request.user)).select_related("lot__reference", "lot__site", "allocation__recipient", "unit", "actor").order_by("-destroyed_on", "-pk")
    return page(request, "destroyed", "destroyed", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def history(request):
    require(request.user, ("admin", "manager"))
    query = Movement.objects.select_related("actor", "reference", "site").order_by("-created_at")
    if request.user.role != "admin":
        query = query.filter(Q(site__in=sites(request.user)) | Q(site__isnull=True, actor=request.user))
    return page(request, "history", "history", items=Paginator(query, 50).get_page(request.GET.get("page")))


@human
def proposal_list(request):
    require(request.user, ("admin", "manager"))
    return page(request, "proposals", "validity", items=Paginator(proposals(request.user).order_by("-created_at"), 50).get_page(request.GET.get("page")), assistance=assistance_enabled())


@human
def proposal_create(request):
    require(request.user, ("admin", "manager"))
    initial = {name: request.GET.get(name) for name in ("reference", "lot", "unit")}
    form = forms.ProposalForm(request.POST or None, actor=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.create_proposal(request.user, **form.cleaned_data)
            return redirect("epi:proposals")
        except ValidationError as exc:
            error(form, exc)
    return form_page(request, "Demander une proposition de validité à l’agent", form, reverse("epi:proposals"), section="validity",
        help_text="L’agent propose une durée et/ou une date avec sa source ; aucune date existante ne sera remplacée sans application humaine.")


@human
@require_POST
def proposal_decide(request, pk):
    require(request.user, ("admin", "manager"))
    get_object_or_404(proposals(request.user), pk=pk)
    try:
        if request.POST.get("decision") not in ("apply", "dismiss"):
            return HttpResponse("Décision invalide.", status=400)
        services.apply_proposal(request.user, pk, apply=request.POST["decision"] == "apply")
    except ValidationError as exc:
        from django.contrib import messages
        messages.error(request, " · ".join(exc.messages))
    return redirect("epi:proposals")
