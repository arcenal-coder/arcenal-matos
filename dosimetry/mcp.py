from django.utils import timezone

from core.intake import assistance_enabled
from core.modules import enabled

from . import services
from .models import AssistanceTask, Badge


def register_tools(tool, agent):
    @tool
    def list_dosimetry_assistance() -> dict:
        """Préparations logistiques de badges passifs en attente. Aucun résultat de dose ni confirmation physique."""
        agent()
        if not enabled("dosimeters") or not assistance_enabled():
            return {"enabled": False, "items": []}
        items = AssistanceTask.objects.filter(status="pending").select_related("site", "period").order_by("created_at")[:50]
        return {"enabled": True, "items": [{"id": str(item.pk), "kind": item.kind, "site": str(item.site), "period": item.period.name} for item in items]}

    @tool
    def read_dosimetry_assistance(task_id: str, offset: int = 0) -> dict:
        """Lire badges, équipiers éligibles et échéances du site/période demandés. Paginer les badges par 200. Ne pas inventer de numéro ni d'affectation."""
        agent()
        if not enabled("dosimeters") or not assistance_enabled():
            raise ValueError("Module ou assistance désactivé.")
        task = AssistanceTask.objects.select_related("site", "period__laboratory").get(pk=task_id)
        query = Badge.objects.filter(site_id=task.site_id, period_id=task.period_id).select_related("assigned_to").order_by("code", "pk")
        offset = max(0, offset)
        return {"id": str(task.pk), "kind": task.kind, "question": task.question, "site": str(task.site), "as_of": str(timezone.localdate()),
            "period": {"name": task.period.name, "start": str(task.period.start_on), "end": str(task.period.end_on), "return_due": str(task.period.return_due_on)},
            "laboratory": {"name": str(task.period.laboratory), "shipping_address": task.period.laboratory.address},
            "total_badges": query.count(), "offset": offset,
            "badges": [{"id": str(item.pk), "code": item.code, "kind": item.kind, "wear_location": item.wear_location,
                "assigned_to_id": item.assigned_to_id, "assigned_to": str(item.assigned_to) if item.assigned_to_id else None,
                "status": item.status, "overdue": item.overdue, "not_worn": item.not_worn} for item in query[offset:offset + 200]],
            "eligible_people": [{"id": person.pk, "name": str(person)} for person in services.people(task.site_id)],
            "instructions": "Préparer seulement. Affectation : badge personnel en stock et équipier éligible, sans contredire une préaffectation existante. Ne pas inventer la correspondance numéro/porteur ; demander les informations manquantes. L'éligibilité au site ne présume pas une obligation de port. Collecte : badge distribué. Envoi : badge déjà collecté. Aucun changement de distribution, collecte, expédition, perte ou annulation ; un humain confirme. Aucun résultat de dose à produire."}

    @tool
    def propose_dosimetry_logistics(task_id: str, response: str, assignments: list[dict] | None = None, badge_ids: list[str] | None = None) -> dict:
        """Renvoyer conseils et préparation. assignments=[{badge_id,user_id,reason}] pour préaffectation, ou badge_ids pour collecte/envoi. Ne confirme aucun mouvement physique."""
        item = services.answer_assistance(agent(), task_id, response, assignments, badge_ids)
        return {"id": str(item.pk), "status": item.status}
