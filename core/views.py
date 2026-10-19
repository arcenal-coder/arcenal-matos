import io
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import qrcode
import yaml
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode import createBarcodeDrawing

from matos.version import RELEASE_LABEL, VERSION

from . import agent_links, branding, forms, modules, services
from .import_export import HEADERS, csv_bytes, import_csv, report
from .models import (
    Allocation,
    Asset,
    AssistanceSettings,
    Category,
    Document,
    Event,
    Intervention,
    License,
    Notification,
    Outbox,
    Reservation,
    Site,
    Supplier,
    SupplierRequest,
    Transfer,
    User,
)
from .permissions import assets, can_read_asset, manage, require, sites


def context(request):
    page = getattr(request.resolver_match, "url_name", "")
    navigation = {
        "asset": "inventory", "asset-new": "inventory", "asset-edit": "inventory", "assign": "inventory",
        "reserve": "reservations", "reservation": "reservations", "movement": "reservations",
        "transfer-create": "transfers", "maintenance-create": "maintenance", "supplier-request-create": "suppliers",
        "license-new": "licenses", "license-edit": "licenses", "license-allocate": "licenses",
        "setup-new": "settings", "setup-edit": "settings",
    }
    data = {"app_version": VERSION, "release_label": RELEASE_LABEL, "active_navigation": navigation.get(page, page),
            "has_company_logo": branding.has_logo(), "company_logo_version": branding.logo_version()}
    if not request.user.is_authenticated:
        return data
    preferences = modules.preferences()
    return data | {"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count(),
                   "is_assistance_user": request.user.role in ("admin", "manager", "member"),
                   "is_epi_user": request.user.role in ("admin", "manager", "member") and preferences.epi_enabled,
                   "is_dosimeter_user": request.user.role in ("admin", "manager", "member") and preferences.dosimeters_enabled,
                   "is_staff_profile": request.user.role in ("admin", "manager"),
                   "is_manager": request.user.role == "manager", "is_admin_profile": request.user.role == "admin"}


def validation_message(request, exc):
    messages.error(request, " · ".join(exc.messages))


def login_view(request):
    if settings.DEV_LOGIN and request.META.get("REMOTE_ADDR") in ("127.0.0.1", "::1"):
        users = User.objects.filter(is_active=True).exclude(role="agent")
        if request.method == "POST":
            user = get_object_or_404(users, pk=request.POST.get("user"))
            login(request, user, backend="core.auth.DisabledPasswordBackend")
            return redirect("dashboard")
        return render(request, "login.html", {"users": users, "development": True})
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "login.html", {"development": False}, status=401)


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login" if settings.DEV_LOGIN else "/yunohost/sso/?action=logout")


def company_logo(request):
    if not branding.has_logo():
        return HttpResponse(status=404)
    response = HttpResponse(branding.dark_logo(), content_type="image/png") if request.GET.get("mode") == "dark" else FileResponse(branding.logo_path().open("rb"), content_type="image/png")
    response["Cache-Control"] = "public, max-age=300"
    return response


@login_required
def dashboard(request):
    if request.user.role == "unassigned":
        return render(request, "unassigned.html", status=403)
    queryset = assets(request.user).order_by("code")
    reservations = visible_reservations(request.user)
    return render(request, "dashboard.html", {"total": queryset.count(),
        "blocked": sum(item.blocked for item in queryset), "pending": reservations.filter(status="pending").count(),
        "out": reservations.filter(status="out").count(),
        "recent": queryset.order_by("-updated_at")[:6],
        "requests": reservations.filter(status="pending").select_related("asset", "borrower")[:6],
        "supplier_pending": SupplierRequest.objects.filter(asset__site__in=sites(request.user), status="draft").count()
            if request.user.role in ("admin", "manager") else 0})


def visible_reservations(actor):
    require(actor, ("admin", "manager", "member"))
    if actor.role == "member":
        return Reservation.objects.filter(borrower=actor)
    return Reservation.objects.filter(asset__site__in=sites(actor))


def requested_dates(request):
    try:
        start = date.fromisoformat(request.GET.get("start", str(timezone.localdate())))
        end = date.fromisoformat(request.GET.get("end", str(start + timedelta(days=7))))
        if end < start:
            raise ValueError
        return start, end
    except ValueError as exc:
        raise ValidationError("Les dates demandées sont invalides.") from exc


@login_required
def inventory(request):
    queryset = assets(request.user).order_by("code")
    intersite = request.GET.get("intersite") == "1" and request.user.role == "member"
    try:
        start, end = requested_dates(request)
    except ValidationError:
        return HttpResponse("Dates invalides", status=400)
    if intersite:
        local_types = {}
        local = services.availability_queryset(Asset.objects.filter(site=request.user.site))
        for item in local:
            if services.available(item, start, end):
                local_types.setdefault(item.category_id, set()).add(item.model)
        candidates = services.availability_queryset(Asset.objects.exclude(site=request.user.site).order_by("code"))
        queryset = [item for item in candidates if services.available(item, start, end)
                    and not (local_types.get(item.category_id) and (not item.model or item.model in local_types[item.category_id]))]
        query = request.GET.get("q", "").lower()
        if query:
            queryset = [item for item in queryset if query in f"{item.code} {item.name} {item.model}".lower()]
    elif request.GET.get("q"):
        query = request.GET["q"]
        queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(serial__icontains=query))
    if not intersite and request.GET.get("site"):
        try:
            queryset = queryset.filter(site_id=int(request.GET["site"]))
        except ValueError:
            return HttpResponse("Site invalide", status=400)
    from django.core.paginator import Paginator
    page = Paginator(queryset, 40).get_page(request.GET.get("page"))
    return render(request, "inventory.html", {"items": page, "sites": sites(request.user),
                                               "agent_sso_ready": bool(agent_links.destination()),
                                               "intersite": intersite, "start": start, "end": end})


def readable_asset(request, pk):
    item = get_object_or_404(Asset.objects.select_related("site", "category", "assigned_to"), pk=pk)
    if can_read_asset(request.user, item):
        return item
    if request.user.role == "member" and request.user.site_id:
        try:
            start, end = requested_dates(request)
        except ValidationError as exc:
            raise PermissionDenied("Dates invalides") from exc
        if services.available(item, start, end) and not services.locally_available(request.user, item, start, end):
            return item
    raise PermissionDenied("Cette fiche n'est pas accessible.")


@login_required
def asset_detail(request, pk):
    item = readable_asset(request, pk)
    staff = request.user.role in ("admin", "manager")
    try:
        start, end = requested_dates(request)
    except ValidationError:
        return HttpResponse("Dates invalides", status=400)
    return render(request, "asset.html", {"asset": item, "reservation_start": start, "reservation_end": end,
        "reservations": visible_reservations(request.user).filter(asset=item).select_related("borrower"),
        "interventions": item.interventions.select_related("supplier").order_by("-scheduled_date") if staff else [],
        "documents": item.documents.all() if staff else item.documents.filter(loan__reservation__borrower=request.user),
        "history": Event.objects.filter(asset=item).select_related("actor").order_by("-created_at")[:30] if staff else [],
        "can_manage": staff and sites(request.user).filter(pk=item.site_id).exists()})


@login_required
def asset_edit(request, pk=None):
    require(request.user, ("admin", "manager"))
    item = get_object_or_404(assets(request.user), pk=pk) if pk else None
    form = forms.AssetForm(request.POST or None, instance=item, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if item:
                    values = {key: value for key, value in form.cleaned_data.items() if key not in ("code", "site")}
                    services.update_asset(request.user, pk, values)
                else:
                    item = form.save()
                    services.audit(request.user, "asset.created", item)
            messages.success(request, "Fiche enregistrée")
            return redirect("inventory")
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, "Une autre fiche vient d’être enregistrée avec cette référence. Réessayez l’enregistrement.")
    return render(request, "asset_form.html", {"form": form, "asset": item,
        "assistance_enabled": bool(settings.MCP_TOKEN) and AssistanceSettings.objects.filter(pk=1, enabled=True).exists(),
        "title": "Modifier le matériel" if pk else "Ajouter du matériel"})


@login_required
def reserve_view(request, pk):
    require(request.user, ("member",))
    item = readable_asset(request, pk)
    try:
        start, end = requested_dates(request)
    except ValidationError:
        return HttpResponse("Dates invalides", status=400)
    form = forms.ReservationForm(request.POST or None, initial={"start": start, "end": end})
    if request.method == "POST" and form.is_valid():
        try:
            services.reserve(request.user, pk, **form.cleaned_data)
            messages.success(request, "Demande transmise au gestionnaire du site propriétaire")
            return redirect("reservations")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": f"Demander {item.name}"})


@login_required
def reservations(request):
    queryset = visible_reservations(request.user).select_related("asset__site", "borrower").order_by("-created_at")
    if request.GET.get("status"):
        queryset = queryset.filter(status=request.GET["status"])
    return render(request, "reservations.html", {"items": queryset[:300]})


@login_required
def reservation_detail(request, pk):
    item = get_object_or_404(visible_reservations(request.user).select_related("asset", "borrower", "approved_by"), pk=pk)
    return render(request, "reservation.html", {"item": item, "loan": getattr(item, "loan", None)})


@login_required
def movement(request, pk, action):
    require(request.user, ("admin", "manager"))
    item = get_object_or_404(visible_reservations(request.user), pk=pk)
    if action not in ("checkout", "return"):
        raise PermissionDenied
    form = forms.MovementForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            photo = form.cleaned_data.get("photo")
            validate_upload(photo)
            if action == "checkout":
                loan = services.checkout(request.user, pk, form.cleaned_data["condition"], form.cleaned_data["comment"])
            else:
                loan = services.return_loan(request.user, pk, form.cleaned_data["condition"], form.cleaned_data["comment"], form.cleaned_data["damaged"])
            if photo:
                save_document(request.user, item.asset, photo, loan=loan)
            messages.success(request, "Mouvement enregistré")
            return redirect("reservation", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": "Sortie de matériel" if action == "checkout" else "Retour de matériel"})


@login_required
@require_POST
def action(request, kind, pk):
    try:
        pk = UUID(pk) if kind == "restore" else int(pk)
        if kind in ("approve", "reject"):
            services.approve_reservation(request.user, pk, kind == "approve")
        elif kind == "cancel":
            services.cancel_reservation(request.user, pk)
        elif kind == "restore":
            services.restore_asset(request.user, pk)
        elif kind in ("supplier-approve", "supplier-reject"):
            services.approve_supplier_request(request.user, pk, kind == "supplier-approve")
        elif kind == "transfer-next":
            services.advance_transfer(request.user, pk)
        elif kind == "maintenance-done":
            services.complete_intervention(request.user, pk, timezone.localdate())
        elif kind == "allocation-remove":
            item = get_object_or_404(Allocation.objects.select_related("license"), pk=pk)
            manage(request.user, item.license.site_id)
            services.audit(request.user, "license.unallocated", item.asset, {"allocation": item.pk}, site=item.license.site)
            item.delete()
        elif kind == "read":
            Notification.objects.filter(user=request.user, pk=pk).update(read_at=timezone.now())
        else:
            raise PermissionDenied("Action inconnue")
        messages.success(request, "Action enregistrée")
    except ValidationError as exc:
        validation_message(request, exc)
    except ValueError:
        return HttpResponse("Identifiant invalide", status=400)
    except (Reservation.DoesNotExist, Asset.DoesNotExist, Intervention.DoesNotExist, SupplierRequest.DoesNotExist, Transfer.DoesNotExist):
        return HttpResponse("Objet introuvable", status=404)
    target = {"restore": "inventory", "maintenance-done": "maintenance", "transfer-next": "transfers",
              "supplier-approve": "suppliers", "supplier-reject": "suppliers", "allocation-remove": "licenses", "read": "notifications"}
    return redirect(target.get(kind, "reservations"))


@login_required
def assign(request, pk):
    item = get_object_or_404(assets(request.user), pk=pk)
    manage(request.user, item.site_id)
    class AssignForm(forms.forms.Form):
        user = forms.forms.ModelChoiceField(label="Collaborateur (vide pour libérer)", required=False,
                                            queryset=User.objects.filter(role="member", site=item.site, is_active=True))
    form = AssignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.assign_asset(request.user, pk, form.cleaned_data["user"])
            return redirect("asset", pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": "Affecter le matériel"})


@login_required
def transfers(request):
    require(request.user, ("admin", "manager"))
    queryset = Transfer.objects.filter(Q(source__in=sites(request.user)) | Q(destination__in=sites(request.user))).select_related("asset", "source", "destination").order_by("-created_at")
    return render(request, "transfers.html", {"items": queryset[:300]})


@login_required
def transfer_create(request, pk):
    item = get_object_or_404(assets(request.user), pk=pk)
    manage(request.user, item.site_id)
    class TransferForm(forms.forms.Form):
        destination = forms.forms.ModelChoiceField(label="Site destinataire", queryset=Site.objects.exclude(pk=item.site_id))
        comment = forms.forms.CharField(label="Commentaire", required=False, widget=forms.forms.Textarea)
    form = TransferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.transfer_asset(request.user, pk, **form.cleaned_data)
            return redirect("transfers")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": f"Transférer {item.name}"})


@login_required
def maintenance(request):
    require(request.user, ("admin", "manager"))
    queryset = Intervention.objects.filter(asset__site__in=sites(request.user)).select_related("asset", "supplier").order_by("-scheduled_date")
    return render(request, "maintenance.html", {"items": queryset[:300]})


@login_required
def maintenance_create(request, pk):
    item = get_object_or_404(assets(request.user), pk=pk)
    manage(request.user, item.site_id)
    form = forms.InterventionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.plan_intervention(request.user, pk, form.cleaned_data)
            return redirect("maintenance")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": f"Intervention · {item.name}"})


@login_required
def suppliers(request):
    require(request.user, ("admin", "manager"))
    return render(request, "suppliers.html", {"suppliers": Supplier.objects.all(),
        "items": SupplierRequest.objects.filter(asset__site__in=sites(request.user)).select_related("asset", "supplier", "approved_by").order_by("-pk")[:300],
        "outbox": Outbox.objects.filter(supplier_request__asset__site__in=sites(request.user)).order_by("-created_at")[:50]})


@login_required
def supplier_request_create(request, pk):
    item = get_object_or_404(assets(request.user), pk=pk)
    manage(request.user, item.site_id)
    class RequestForm(forms.forms.Form):
        supplier = forms.forms.ModelChoiceField(label="Fournisseur", queryset=Supplier.objects.all())
        subject = forms.forms.CharField(label="Objet", max_length=200)
        body = forms.forms.CharField(label="Message", widget=forms.forms.Textarea)
    form = RequestForm(request.POST or None, initial={"subject": f"Demande de contrôle · {item.code}",
        "body": f"Bonjour,\nNous souhaitons organiser le contrôle de {item.name} ({item.code}), site {item.site}.\nMerci de nous proposer vos disponibilités."})
    if request.method == "POST" and form.is_valid():
        services.prepare_supplier_request(request.user, pk, **form.cleaned_data)
        messages.success(request, "Brouillon préparé ; validation humaine nécessaire avant envoi")
        return redirect("suppliers")
    return render(request, "form.html", {"form": form, "title": "Préparer une demande fournisseur"})


@login_required
def licenses(request):
    require(request.user, ("admin", "manager"))
    return render(request, "licenses.html", {"items": License.objects.filter(site__in=sites(request.user)).select_related("site").prefetch_related("allocations__user", "allocations__asset")})


@login_required
def license_edit(request, pk=None):
    require(request.user, ("admin", "manager"))
    item = get_object_or_404(License.objects.filter(site__in=sites(request.user)), pk=pk) if pk else None
    form = forms.LicenseForm(request.POST or None, actor=request.user, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if item:
                current = License.objects.select_for_update().get(pk=item.pk)
                if form.cleaned_data["seats"] < current.allocations.count():
                    form.add_error("seats", "Le nombre de places est inférieur aux affectations existantes.")
                else:
                    item = form.save()
            else:
                item = form.save()
            if not form.errors:
                services.audit(request.user, "license.saved", details={"license": item.pk}, site=item.site)
                return redirect("licenses")
    return render(request, "form.html", {"form": form, "title": "Licence / abonnement"})


@login_required
def license_allocate(request, pk):
    require(request.user, ("admin", "manager"))
    item = get_object_or_404(License.objects.filter(site__in=sites(request.user)), pk=pk)
    class AllocationForm(forms.forms.Form):
        user = forms.forms.ModelChoiceField(label="Personne", required=False, queryset=User.objects.filter(site=item.site, role__in=("member", "manager", "admin"), is_active=True))
        asset = forms.forms.ModelChoiceField(label="Ou équipement", required=False, queryset=Asset.objects.filter(site=item.site))
    form = AllocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.allocate_license(request.user, pk, **form.cleaned_data)
            return redirect("licenses")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "form.html", {"form": form, "title": f"Affecter une place · {item.name}"})


@login_required
def setup(request, kind, pk=None):
    require(request.user, ("admin", "manager") if kind == "supplier" else ("admin",))
    mapping = {"site": (Site, forms.SiteForm, "Site"), "category": (Category, forms.CategoryForm, "Catégorie"),
               "supplier": (Supplier, forms.SupplierForm, "Fournisseur"), "user": (User, forms.UserForm, "Profil utilisateur")}
    if kind not in mapping:
        raise PermissionDenied
    model, form_type, title = mapping[kind]
    if kind == "user" and not pk:
        raise PermissionDenied("Les identités sont importées depuis YunoHost.")
    item = get_object_or_404(model, pk=pk) if pk else None
    if kind == "user" and item.role == "agent":
        raise PermissionDenied("L'identité technique n'est pas un profil humain.")
    form = form_type(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        if kind == "user" and item.pk == request.user.pk and form.cleaned_data["role"] != "admin":
            form.add_error("role", "Conservez votre rôle administrateur ; un autre administrateur peut le modifier.")
        else:
            item = form.save()
            services.audit(request.user, f"{kind}.saved", details={"id": item.pk})
            if kind == "supplier":
                return redirect("suppliers")
            return redirect("settings-section", section={"user": "users", "site": "sites", "category": "categories"}[kind])
    return render(request, "form.html", {"form": form, "title": title,
        "cancel_url": reverse("suppliers") if kind == "supplier" else reverse("settings-section", args=[{"user": "users", "site": "sites", "category": "categories"}[kind]])})


@login_required
def settings_view(request, section=None):
    require(request.user, ("admin",))
    if section not in (None, "users", "sites", "categories"):
        return HttpResponse(status=404)
    titles = {None: "Paramètres", "users": "Gestion des utilisateurs", "sites": "Sites", "categories": "Catégories & périodicités"}
    return render(request, "settings.html", {"section": section, "title": titles[section],
                                            "users": User.objects.exclude(role="agent").select_related("site").prefetch_related("managed_sites"),
                                            "sites": Site.objects.all(), "categories": Category.objects.all()})


@login_required
def module_settings(request):
    require(request.user, ("admin",))
    config = modules.preferences()
    form = forms.ModuleSettingsForm(request.POST if request.method == "POST" else None, instance=config)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            config = form.save()
            services.audit(request.user, "modules.configured", details={"epi": config.epi_enabled, "dosimeters": config.dosimeters_enabled})
        messages.success(request, "Activation des modules enregistrée. Les données existantes sont conservées.")
        return redirect("module-settings")
    return render(request, "modules.html", {"form": form})


@login_required
def csv_import(request):
    require(request.user, ("admin", "manager"))
    if request.GET.get("template"):
        response = HttpResponse(csv_bytes([]), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="modele-inventaire.csv"'
        return response
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            messages.error(request, "Choisissez un fichier CSV")
        else:
            try:
                count = import_csv(request.user, uploaded.read())
                messages.success(request, f"{count} équipement(s) importé(s)")
                return redirect("inventory")
            except ValidationError as exc:
                validation_message(request, exc)
    return render(request, "import.html", {"columns": HEADERS})


@login_required
def reports(request):
    require(request.user, ("admin", "manager"))
    kind = request.GET.get("format")
    if kind in ("csv", "pdf"):
        try:
            site_id = int(request.GET["site"]) if request.GET.get("site") else None
            data, mime = report(request.user, kind, site_id)
        except ValueError:
            return HttpResponse("Site invalide", status=400)
        response = HttpResponse(data, content_type=mime)
        response["Content-Disposition"] = f'attachment; filename="inventaire-audit.{kind}"'
        return response
    return render(request, "reports.html", {"sites": sites(request.user)})


def validate_upload(uploaded):
    if not uploaded:
        return
    if uploaded.size > 10 * 1024 * 1024:
        raise ValidationError("Une pièce jointe est limitée à 10 Mo.")
    if Path(uploaded.name).suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".csv", ".txt"):
        raise ValidationError("Formats autorisés : PDF, PNG, JPG, CSV, TXT.")


def save_document(actor, asset, uploaded, intervention=None, loan=None):
    validate_upload(uploaded)
    item = Document.objects.create(asset=asset, file=uploaded, name=Path(uploaded.name).name[:255],
                                   uploaded_by=actor, intervention=intervention, loan=loan)
    services.audit(actor, "document.uploaded", asset, {"document": str(item.pk)})
    return item


@login_required
@require_POST
def upload_document(request, pk):
    item = get_object_or_404(assets(request.user), pk=pk)
    manage(request.user, item.site_id)
    uploaded = request.FILES.get("file")
    try:
        if not uploaded:
            raise ValidationError("Aucun fichier fourni")
        intervention = get_object_or_404(item.interventions, pk=request.POST["intervention"]) if request.POST.get("intervention") else None
        save_document(request.user, item, uploaded, intervention=intervention)
        messages.success(request, "Document ajouté")
    except ValidationError as exc:
        validation_message(request, exc)
    return redirect("asset", pk=pk)


@login_required
def download_document(request, pk):
    item = get_object_or_404(Document.objects.select_related("asset", "loan__reservation"), pk=pk)
    if request.user.role == "member":
        if not item.loan_id or item.loan.reservation.borrower_id != request.user.pk:
            raise PermissionDenied
    else:
        manage(request.user, item.asset.site_id)
    return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.name)


@login_required
def label(request, pk, kind):
    item = readable_asset(request, pk)
    if kind == "qr":
        image = qrcode.make(settings.PUBLIC_URL + reverse("asset", args=[pk]))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return HttpResponse(output.getvalue(), content_type="image/png")
    if kind == "barcode":
        drawing = createBarcodeDrawing("Code128", value=item.code, humanReadable=True, barHeight=40, barWidth=1)
        return HttpResponse(renderSVG.drawToString(drawing), content_type="image/svg+xml")
    raise PermissionDenied


@login_required
def scan(request):
    require(request.user, ("admin", "manager", "member"))
    if request.GET.get("code"):
        item = Asset.objects.filter(code=request.GET["code"]).first()
        if item:
            readable_asset(request, item.pk)
            return redirect("asset", pk=item.pk)
        messages.error(request, "Identifiant inconnu")
    return render(request, "scan.html")


@login_required
def notifications(request):
    return render(request, "notifications.html", {"items": Notification.objects.filter(user=request.user).order_by("-created_at")[:100]})


@login_required
def journal(request):
    require(request.user, ("admin", "manager"))
    queryset = Event.objects.all() if request.user.role == "admin" else Event.objects.filter(site__in=sites(request.user))
    return render(request, "journal.html", {"items": queryset.select_related("actor", "asset", "site").order_by("-created_at")[:300]})


def agent_yaml():
    from mcp.types import LATEST_PROTOCOL_VERSION
    preferences = modules.preferences()
    instructions = ["Gérer la logistique sur tous les sites. Utiliser les outils MCP. Traiter list_intake_requests avec read_intake_request et complete_intake_request pour photo/série/périodicité, en expliquant la source. Ne rien inventer si l'image est illisible ou la périodicité inconnue. Réservations, demandes fournisseurs et remises en service : validation humaine obligatoire."]
    capabilities = ["assets.read", "assets.update_allowed_fields", "assignments.manage", "loans.record_approved_checkout", "loans.record_return", "transfers.manage", "maintenance.plan_and_record", "supplier_requests.prepare", "reminders.send", "reports.generate", "intake.assist"]
    human_only = ["reservations.approve", "supplier_requests.approve", "assets.return_to_service"]
    if preferences.epi_enabled:
        instructions.append("Traiter list_epi_validity_requests, lire read_epi_validity_request, proposer via propose_epi_validity avec source fabricant. Ne jamais prolonger une limite fabricant ; indiquer les données manquantes. Application de validité, validation, remise et destruction EPI restent humaines.")
        capabilities.append("epi.validity.propose")
        human_only.extend(["epi.requests.approve", "epi.issue", "epi.destroy", "epi.validity.apply"])
    if preferences.dosimeters_enabled:
        instructions.append("Assister le gestionnaire des dosimètres PASSIFS : list_dosimetry_assistance, read_dosimetry_assistance puis propose_dosimetry_logistics. Repérer retards et badges manquants, proposer préaffectations ou listes de collecte/envoi. Ne pas inventer de badge ou personne. Un humain confirme toute préaffectation et toute opération physique. Aucun résultat de dose.")
        capabilities.append("dosimetry.logistics.prepare")
        human_only.extend(["dosimetry.preassign", "dosimetry.issue", "dosimetry.collect", "dosimetry.send", "dosimetry.close"])
    return {"schema": "arcenal-agent-link", "schema_version": 1, "application": "arcenal-matos",
        "agent_profile": {"name": "logisticien-arcenal-matos", "role": "logisticien", "instructions": " ".join(instructions)},
        "mcp": {"endpoint": settings.PUBLIC_URL + "/mcp", "transport": "streamable-http", "protocol_version": LATEST_PROTOCOL_VERSION,
                 "authentication": {"mode": "bearer", "credential_ref": "MATOS_MCP_TOKEN", "header": "Authorization"}},
        "access": {"sites": "all", "capabilities": capabilities, "human_only": human_only}}


@login_required
@require_POST
def agent_assistance(request, agent):
    # No user-supplied context, action, reference, target or identity is trusted.
    if request.GET or set(request.POST) - {"csrfmiddlewaretoken"}:
        return HttpResponse("Cette liaison est réservée à l’assistance en lecture seule ; aucun contexte client ou action centrale n’est accepté.", status=400)
    try:
        context = agent_links.context_for(request.user, agent)
    except KeyError:
        raise Http404("Assistance inconnue ou module désactivé.") from None
    from . import agent_pairing
    if agent_pairing.configuration():
        try:
            target = agent_pairing.open_assistance(request.user, agent)
        except agent_pairing.PairingUnavailable as exc:
            return HttpResponse(str(exc), status=409)
    else:
        target = agent_links.destination()
    if not target:
        return HttpResponse("Activez la liaison d’assistance dans Paramètres → Agent & MCP.", status=409)
    # Business context stays server-side; only the verified opaque reference may leave.
    services.audit(request.user, "agent.assistance_opened", details={"application": context.application,
        "intention": context.intention, "resource_type": context.resource_type, "module": context.resource_id,
        "delivery": "server_verified_reference" if agent_pairing.configuration() else "sso_navigation_without_context"})
    response = HttpResponseRedirect(target, status=303)
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


@login_required
def integration(request):
    from . import agent_pairing
    require(request.user, ("admin",))
    config = AssistanceSettings.objects.filter(pk=1).first() or AssistanceSettings(pk=1)
    sso_form = forms.AgentSSOForm(instance=config)
    if request.method == "POST":
        kind = request.POST.get("form", "mcp")
        if kind == "sso":
            sso_form = forms.AgentSSOForm(request.POST, instance=config)
            if sso_form.is_valid():
                config, _ = AssistanceSettings.objects.update_or_create(pk=1, defaults={"sso_url": sso_form.cleaned_data["sso_url"]})
                services.audit(request.user, "agent.sso_configured", details={"configured": bool(config.sso_url)})
                messages.success(request, "Destination SSO de l’assistance enregistrée.")
                return redirect("integration")
            # Do not echo a rejected destination that might contain credentials.
            sso_form.data = sso_form.data.copy()
            sso_form.data["sso_url"] = ""
        elif kind == "mcp":
            config, _ = AssistanceSettings.objects.get_or_create(pk=1)
            config.enabled = bool(settings.MCP_TOKEN) and request.POST.get("assistance_enabled") == "on"
            config.save(update_fields=["enabled"])
            services.audit(request.user, "agent.assistance_configured", details={"enabled": config.enabled})
            messages.success(request, "Paramètres de l’agent enregistrés.")
            return redirect("integration")
        else:
            return HttpResponse("Formulaire inconnu.", status=400)
    data = agent_yaml()
    if request.GET.get("download"):
        services.audit(request.user, "agent.yaml_exported")
        response = HttpResponse(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), content_type="application/yaml")
        response["Content-Disposition"] = 'attachment; filename="arcenal-matos-logisticien.yaml"'
        return response
    return render(request, "integration.html", {"yaml": yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        "agent_cards": agent_links.agent_cards(),
        "pairing_state": agent_pairing.status(),
        "pairing_manage_url": agent_pairing.management_url(),
        "sso_form": sso_form,
        "endpoint": data["mcp"]["endpoint"], "mcp_configured": bool(settings.MCP_TOKEN),
        "assistance_enabled": AssistanceSettings.objects.filter(pk=1, enabled=True).exists()})
