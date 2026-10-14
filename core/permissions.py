from django.core.exceptions import PermissionDenied

from .models import Asset


def require(actor, roles):
    if not actor.is_authenticated or not actor.is_active or actor.role not in roles:
        raise PermissionDenied("Cette opération n'est pas autorisée pour votre profil.")


def sites(actor):
    require(actor, ("admin", "manager", "member", "agent"))
    if actor.role in ("admin", "agent"):
        from .models import Site
        return Site.objects.all()
    if actor.role == "manager":
        return actor.managed_sites.all()
    from .models import Site
    return Site.objects.filter(pk=actor.site_id)


def manage(actor, site_id, human_manager=False):
    require(actor, ("manager",) if human_manager else ("admin", "manager", "agent"))
    if not sites(actor).filter(pk=site_id).exists():
        raise PermissionDenied("Ce site ne vous est pas attribué.")


def assets(actor):
    return Asset.objects.filter(site__in=sites(actor)).select_related("site", "category", "assigned_to")


def can_read_asset(actor, asset):
    if sites(actor).filter(pk=asset.site_id).exists():
        return True
    return actor.role == "member" and asset.reservations.filter(borrower=actor).exists()
