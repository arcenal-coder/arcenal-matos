import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import agent_pairing, services
from .permissions import require


@login_required
@require_POST
def pairing(request):
    require(request.user, ("admin",))
    if request.GET or set(request.POST) - {"csrfmiddlewaretoken", "operation", "confirmed"}:
        return HttpResponse("Confirmation invalide.", status=400)
    operation = request.POST.get("operation")
    try:
        if operation == "pair":
            if request.POST.get("confirmed") != "on":
                return HttpResponse("Confirmez la liaison en lecture seule dans Matos.", status=409)
            target = agent_pairing.pair()
            services.audit(request.user, "agent.pairing_requested", details={"intention": "read_only_help"})
            response = HttpResponseRedirect(target, status=303)
            response["Referrer-Policy"] = "no-referrer"
            response["Cache-Control"] = "private, no-store"
            return response
        if operation == "revoke":
            agent_pairing.revoke()
            services.audit(request.user, "agent.pairing_revoked")
            messages.success(request, "Liaison révoquée dans Matos.")
        elif operation != "status":
            return HttpResponse("Opération inconnue.", status=400)
    except agent_pairing.PairingUnavailable as exc:
        messages.error(request, str(exc))
    return redirect("integration")


@csrf_exempt
@require_POST
def verify(request):
    # Service-to-service only, with a dedicated per-application credential.
    if request.GET or len(request.body) > 4096:
        return HttpResponse(status=400)
    try:
        result = agent_pairing.verify(request.headers.get("Authorization", ""), json.loads(request.body))
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    response = JsonResponse(result)
    response["Cache-Control"] = "private, no-store"
    return response
