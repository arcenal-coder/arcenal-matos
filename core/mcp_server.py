import base64
import json
from datetime import date
from decimal import Decimal
from functools import wraps
from typing import Literal

from asgiref.sync import sync_to_async
from django.db import close_old_connections, connections
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ImageContent, TextContent

from . import services
from .import_export import report
from .intake import assistance_enabled
from .models import Asset, IntakeRequest, Site, Supplier, User
from .permissions import require


def agent():
    close_old_connections()
    user, _ = User.objects.get_or_create(username="__hermes_logisticien__", defaults={"role": "agent"})
    require(user, ("agent",))
    return user


def serialize_asset(item):
    return {"id": str(item.pk), "code": item.code, "name": item.name, "site_id": item.site_id,
            "site": item.site.name, "category": item.category.name, "state": item.state,
            "blocked": item.blocked, "control_due": str(item.control_due) if item.control_due else None,
            "assigned_to": item.assigned_to_id, "custom_fields": item.custom_fields}


def build_server(hosts, origins):
    server = FastMCP("ARCenal Matos", instructions="Logisticien sur tous les sites. Les validations de réservation, demandes fournisseur et remises en service restent humaines.",
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins))

    def tool(function):
        @wraps(function)
        async def invoke(*args, **kwargs):
            def execute():
                try:
                    return function(*args, **kwargs)
                finally:
                    connections.close_all()
            return await sync_to_async(execute, thread_sensitive=True)()
        return server.tool()(invoke)

    @tool
    def list_intake_requests() -> dict:
        """Demandes de saisie à traiter : reconnaissance photo et périodicité, si assistance activée."""
        agent()
        if not assistance_enabled():
            return {"enabled": False, "items": []}
        return {"enabled": True, "items": [{"id": str(item.pk), "name": item.name, "category": item.category.name,
            "brand": item.brand, "model": item.model, "has_photo": bool(item.photo)}
            for item in IntakeRequest.objects.filter(status="pending").select_related("category").order_by("created_at")[:50]]}

    @tool
    def read_intake_request(request_id: str) -> list:
        """Lire contexte et image privée pour reconnaître la série et rechercher la périodicité. Ne rien inventer."""
        agent()
        if not assistance_enabled():
            raise ValueError("Assistance désactivée.")
        item = IntakeRequest.objects.select_related("category").get(pk=request_id)
        content = [TextContent(type="text", text=json.dumps({"id": str(item.pk), "name": item.name,
            "category": item.category.name, "brand": item.brand, "model": item.model,
            "category_interval_days": item.category.interval_days}, ensure_ascii=False))]
        if item.photo:
            with item.photo.open("rb") as photo:
                content.append(ImageContent(type="image", mimeType="image/png", data=base64.b64encode(photo.read()).decode()))
        return content

    @tool
    def complete_intake_request(request_id: str, explanation: str, serial: str = "", interval_days: int | None = None) -> dict:
        """Répondre à une demande de saisie. Série vide si illisible, période nulle si inconnue ; citer source/contexte."""
        from django.db import transaction
        actor = agent()
        if not assistance_enabled():
            raise ValueError("Assistance désactivée.")
        with transaction.atomic():
            item = IntakeRequest.objects.select_for_update().get(pk=request_id)
            if item.status == "done":
                return {"id": str(item.pk), "status": item.status}
            if not explanation.strip() or len(explanation) > 4000 or len(serial) > 120 or (interval_days is not None and not 1 <= interval_days <= 36500):
                raise ValueError("Réponse invalide : justification requise, série <= 120 caractères, période entre 1 et 36500 jours.")
            item.serial, item.interval_days, item.explanation, item.status = serial.strip(), interval_days, explanation, "done"
            item.save(update_fields=["serial", "interval_days", "explanation", "status"])
            services.audit(actor, "intake.completed", details={"request": str(item.pk)})
        return {"id": str(item.pk), "status": item.status}

    @tool
    def list_assets(query: str = "", site_id: int | None = None, offset: int = 0) -> dict:
        """Rechercher les équipements et leurs états ; pagination de 100 éléments."""
        agent()
        queryset = Asset.objects.select_related("category", "site")
        if query:
            from django.db.models import Q
            queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        offset = max(offset, 0)
        return {"total": queryset.count(), "items": [serialize_asset(item) for item in queryset.order_by("code")[offset:offset + 100]]}

    @tool
    def read_asset(asset_id: str) -> dict:
        """Lire une fiche, les réservations et l'historique des interventions."""
        agent()
        item = Asset.objects.select_related("category", "site").get(pk=asset_id)
        data = serialize_asset(item)
        data["reservations"] = list(item.reservations.values("id", "borrower_id", "start", "end", "status"))
        data["interventions"] = list(item.interventions.values("id", "scheduled_date", "completed_date", "supplier_id", "description", "cost"))
        return data

    @tool
    def logistics_directory() -> dict:
        """Lire sites, collaborateurs et fournisseurs nécessaires aux opérations."""
        agent()
        return {"sites": list(Site.objects.values("id", "name")),
                "users": list(User.objects.filter(role="member", is_active=True).values("id", "username", "site_id")),
                "suppliers": list(Supplier.objects.values("id", "name", "email"))}

    @tool
    def update_asset(asset_id: str, fields: dict, operation_key: str) -> dict:
        """Modifier nom, marque, modèle, numéro de série, emplacement ou champs personnalisés."""
        actor = agent()
        return services.agent_command(operation_key, {"tool": "update_asset", "asset": asset_id, "fields": fields},
            lambda: serialize_asset(services.update_asset(actor, asset_id, fields)))

    @tool
    def assign_asset(asset_id: str, user_id: int | None, operation_key: str) -> dict:
        """Affecter à un collaborateur du site ou libérer une affectation ; ne contourne pas un prêt."""
        actor = agent()
        user = User.objects.get(pk=user_id) if user_id else None
        return services.agent_command(operation_key, {"tool": "assign_asset", "asset": asset_id, "user": user_id},
            lambda: serialize_asset(services.assign_asset(actor, asset_id, user)))

    @tool
    def record_checkout(reservation_id: int, condition: str, operation_key: str, comment: str = "") -> dict:
        """Enregistrer une sortie, exclusivement après validation humaine du prêt."""
        actor = agent()
        return services.agent_command(operation_key, {"tool": "checkout", "reservation": reservation_id, "condition": condition, "comment": comment},
            lambda: {"loan_id": services.checkout(actor, reservation_id, condition, comment).pk, "status": "out"})

    @tool
    def record_return(reservation_id: int, condition: str, operation_key: str, comment: str = "", damaged: bool = False) -> dict:
        """Enregistrer un retour et son état, sans remise en service autonome."""
        actor = agent()
        return services.agent_command(operation_key, {"tool": "return", "reservation": reservation_id, "condition": condition, "comment": comment, "damaged": damaged},
            lambda: {"loan_id": services.return_loan(actor, reservation_id, condition, comment, damaged).pk, "status": "returned"})

    @tool
    def plan_transfer(asset_id: str, destination_id: int, operation_key: str, comment: str = "") -> dict:
        """Planifier un transfert entre sites."""
        actor = agent()
        destination = Site.objects.get(pk=destination_id)
        return services.agent_command(operation_key, {"tool": "plan_transfer", "asset": asset_id, "destination": destination_id, "comment": comment},
            lambda: {"transfer_id": services.transfer_asset(actor, asset_id, destination, comment).pk, "status": "planned"})

    @tool
    def advance_transfer(transfer_id: int, operation_key: str) -> dict:
        """Enregistrer l'expédition puis la réception d'un transfert."""
        actor = agent()
        def operation():
            item = services.advance_transfer(actor, transfer_id)
            return {"transfer_id": item.pk, "status": item.status}
        return services.agent_command(operation_key, {"tool": "advance_transfer", "transfer": transfer_id}, operation)

    @tool
    def plan_maintenance(asset_id: str, scheduled_date: str, description: str, operation_key: str, supplier_id: int | None = None, cost: float = 0, is_control: bool = False) -> dict:
        """Planifier une intervention et rendre le matériel indisponible."""
        actor = agent()
        values = {"scheduled_date": date.fromisoformat(scheduled_date), "description": description,
                  "supplier_id": supplier_id, "cost": Decimal(str(cost)), "is_control": is_control}
        return services.agent_command(operation_key, {"tool": "plan_maintenance", "asset": asset_id, "values": values},
            lambda: {"intervention_id": services.plan_intervention(actor, asset_id, values).pk})

    @tool
    def complete_maintenance(intervention_id: int, completed_date: str, operation_key: str, cost: float | None = None) -> dict:
        """Enregistrer une intervention terminée ; la remise en service reste humaine."""
        actor = agent()
        return services.agent_command(operation_key, {"tool": "complete_maintenance", "id": intervention_id, "date": completed_date, "cost": cost},
            lambda: {"intervention_id": services.complete_intervention(actor, intervention_id, date.fromisoformat(completed_date), Decimal(str(cost)) if cost is not None else None).pk})

    @tool
    def prepare_supplier_request(asset_id: str, supplier_id: int, subject: str, body: str, operation_key: str) -> dict:
        """Préparer une demande fournisseur pour validation par un gestionnaire avant envoi."""
        actor = agent()
        supplier = Supplier.objects.get(pk=supplier_id)
        return services.agent_command(operation_key, {"tool": "prepare_supplier_request", "asset": asset_id, "supplier": supplier_id, "subject": subject, "body": body},
            lambda: {"request_id": services.prepare_supplier_request(actor, asset_id, supplier, subject, body).pk, "status": "draft"})

    @tool
    def send_reminders(operation_key: str) -> dict:
        """Produire les rappels internes et mettre les e-mails en file d'envoi."""
        actor = agent()
        def operation():
            services.reminders(actor)
            return {"status": "queued"}
        return services.agent_command(operation_key, {"tool": "reminders"}, operation)

    @tool
    def generate_report(format: Literal["pdf", "csv"] = "csv", site_id: int | None = None) -> dict:
        """Générer un rapport d'inventaire/audit ; fichier renvoyé en base64."""
        data, mime = report(agent(), format, site_id)
        return {"filename": f"inventaire-audit.{format}", "mime_type": mime,
                "encoding": "base64", "data": base64.b64encode(data).decode()}

    from epi.mcp import register_tools
    register_tools(tool, agent)
    from dosimetry.mcp import register_tools as register_dosimetry_tools
    register_dosimetry_tools(tool, agent)
    return server
