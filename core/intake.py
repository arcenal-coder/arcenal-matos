"""Human intake references and asynchronous assistance through the existing MCP."""
import io
from difflib import SequenceMatcher

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps

from . import branding, services
from .models import AssistanceSettings, Brand, Category, DeviceModel, IntakeRequest, reference_key
from .permissions import require


def assistance_enabled():
    return bool(settings.MCP_TOKEN) and AssistanceSettings.objects.filter(pk=1, enabled=True).exists()


def reference_options(kind, brand=""):
    if kind == "category":
        return [{"value": str(item.pk), "label": item.name} for item in Category.objects.order_by("name")]
    queryset = Brand.objects.all() if kind == "brand" else DeviceModel.objects.filter(brand__key=reference_key(brand))
    return [{"value": item.name, "label": item.name} for item in queryset.order_by("name")]


@login_required
def references(request, kind):
    require(request.user, ("admin", "manager"))
    if kind not in ("category", "brand", "model"):
        return JsonResponse({"error": "Référentiel inconnu."}, status=404)
    brand = request.POST.get("brand", "") if request.method == "POST" else request.GET.get("brand", "")
    if request.method == "GET":
        return JsonResponse({"options": reference_options(kind, brand)})
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée."}, status=405)
    name = " ".join(request.POST.get("name", "").split())
    if not name or len(name) > (120 if kind == "category" else 100):
        return JsonResponse({"error": "Renseignez un nom valide."}, status=400)
    options = reference_options(kind, brand)
    exact = next((item for item in options if reference_key(item["label"]) == reference_key(name)), None)
    if exact:
        return JsonResponse(exact)
    similar = [item for item in options if SequenceMatcher(None, reference_key(name), reference_key(item["label"])).ratio() >= .75]
    if similar and request.POST.get("confirm_distinct") != "1":
        return JsonResponse({"error": "Un nom proche existe déjà. Voulez-vous le réutiliser ?", "suggestions": similar}, status=409)
    try:
        with transaction.atomic():
            if kind == "category":
                item = Category.objects.create(name=name)
                result = {"value": str(item.pk), "label": item.name}
            elif kind == "brand":
                item, _ = Brand.objects.get_or_create(key=reference_key(name), defaults={"name": name})
                result = {"value": item.name, "label": item.name}
            else:
                parent = Brand.objects.filter(key=reference_key(brand)).first()
                if not parent:
                    return JsonResponse({"error": "Choisissez d’abord une marque."}, status=400)
                item, _ = DeviceModel.objects.get_or_create(brand=parent, key=reference_key(name), defaults={"name": name})
                result = {"value": item.name, "label": item.name}
            services.audit(request.user, f"reference.{kind}.saved", details=result)
        return JsonResponse(result, status=201)
    except IntegrityError:
        # A concurrent form may have added the same reference.
        exact = next((item for item in reference_options(kind, brand) if reference_key(item["label"]) == reference_key(name)), None)
        return JsonResponse(exact or {"error": "Cette référence existe déjà. Rechargez la liste."}, status=200 if exact else 409)


def image_file(uploaded):
    uploaded = forms.ImageField(max_length=200).clean(uploaded)
    if uploaded.size > 10 * 1024 * 1024:
        raise ValidationError("La photo est limitée à 10 Mo.")
    with Image.open(uploaded) as image:
        if image.width * image.height > 16000000:
            raise ValidationError("La photo est trop grande (16 mégapixels maximum).")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((2000, 2000))
        output = io.BytesIO()
        image.convert("RGBA").save(output, format="PNG")
    return ContentFile(output.getvalue(), name="photo.png")


@login_required
@require_POST
def upload_logo(request):
    require(request.user, ("admin",))
    try:
        content = image_file(request.FILES.get("logo"))
        branding.directory().mkdir(parents=True, exist_ok=True)
        temporary = branding.directory() / "company.tmp"
        temporary.write_bytes(content.read())
        temporary.replace(branding.directory() / "company.png")
        services.audit(request.user, "branding.saved")
        messages.success(request, "Logo société enregistré.")
    except ValidationError as exc:
        messages.error(request, " · ".join(exc.messages))
    return redirect("settings")


@login_required
@require_POST
def request_assistance(request):
    require(request.user, ("admin", "manager"))
    if not assistance_enabled():
        return JsonResponse({"error": "L’assistance de l’agent n’est pas activée dans Paramètres → Agent & MCP."}, status=409)
    try:
        category = Category.objects.get(pk=request.POST.get("category"))
        photo = image_file(request.FILES["photo"]) if request.FILES.get("photo") else None
        item = IntakeRequest.objects.create(requested_by=request.user, category=category,
            name=request.POST.get("name", "")[:200], brand=request.POST.get("brand", "")[:100],
            model=request.POST.get("model", "")[:100], photo=photo or "")
        services.audit(request.user, "intake.requested", details={"request": str(item.pk)})
        return JsonResponse({"id": str(item.pk), "status": item.status}, status=201)
    except (Category.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"error": "Choisissez le type d’appareil."}, status=400)
    except ValidationError as exc:
        return JsonResponse({"error": " · ".join(exc.messages)}, status=400)


@login_required
def assistance_result(request, pk):
    require(request.user, ("admin", "manager"))
    queryset = IntakeRequest.objects.all()
    if request.user.role != "admin":
        queryset = queryset.filter(requested_by=request.user)
    item = get_object_or_404(queryset, pk=pk)
    return JsonResponse({"status": item.status, "serial": item.serial,
                         "interval_days": item.interval_days, "explanation": item.explanation})
