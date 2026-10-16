from datetime import date

from core.intake import assistance_enabled
from core.modules import enabled

from . import services
from .models import ValidityProposal


def register_tools(tool, agent):
    @tool
    def list_epi_validity_requests() -> dict:
        """Demandes EPI en attente : proposer une validité à partir du type et des données fabricant, sans rien inventer."""
        agent()
        if not enabled("epi") or not assistance_enabled():
            return {"enabled": False, "items": []}
        items = ValidityProposal.objects.filter(status="pending").select_related("reference").order_by("created_at")[:50]
        return {"enabled": True, "items": [{"id": str(item.pk), "reference": str(item.reference), "type": item.reference.kind} for item in items]}

    @tool
    def read_epi_validity_request(proposal_id: str) -> dict:
        """Lire type EPI, caractéristiques, limites fabricant et première mise en service. Aucun droit de distribution/destruction."""
        agent()
        if not enabled("epi") or not assistance_enabled():
            raise ValueError("Assistance désactivée.")
        item = ValidityProposal.objects.select_related("reference", "lot__reference", "unit__lot__reference").get(pk=proposal_id)
        reference = item.reference
        first_use = (item.unit.first_use_on if item.unit_id else None) or item.first_use_on
        expiry = item.unit.valid_until if item.unit_id else item.lot.valid_until if item.lot_id else None
        return {"id": str(item.pk), "name": reference.name, "type": reference.kind, "brand": reference.brand,
            "model": reference.model, "size": reference.size, "manufacturer_information": reference.notes,
            "known_reference_usage_days": reference.usage_days,
            "known_target_usage_days": item.unit.effective_usage_days if item.unit_id else item.lot.effective_usage_days if item.lot_id else reference.usage_days,
            "lot": item.lot.number if item.lot_id else None,
            "manufacturer_expiry": str(item.lot.manufacturer_expiry) if item.lot_id and item.lot.manufacturer_expiry else None,
            "current_expiry": str(expiry) if expiry else None,
            "first_use_on": str(first_use) if first_use else None,
            "instructions": "Citer la source fabricant et expliquer le calcul. Ne jamais prolonger une limite fabricant connue. Si les données manquent, les lister ; ne pas inventer une date ou certifier la conformité. La proposition doit ensuite être appliquée par un humain."}

    @tool
    def propose_epi_validity(proposal_id: str, explanation: str, source: str = "", proposed_date: str = "", usage_days: int | None = None, missing_information: str = "") -> dict:
        """Répondre avec date ISO et/ou durée en jours, explication et source ; sinon préciser les données manquantes. Ne modifie aucun stock ni date sans décision humaine."""
        item = services.answer_proposal(agent(), proposal_id, date.fromisoformat(proposed_date) if proposed_date else None,
            usage_days, explanation, source, missing_information)
        return {"id": str(item.pk), "status": item.status}
