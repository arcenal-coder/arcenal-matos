from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.backends import BaseBackend

from .models import User


class DisabledPasswordBackend(BaseBackend):
    def authenticate(self, request, **credentials):
        return None

    def get_user(self, user_id):
        return User.objects.filter(pk=user_id, is_active=True).first()


class YunoHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        username = request.META.get("HTTP_YNH_USER") if settings.TRUST_YNH_HEADERS else None
        if username:
            user, _ = User.objects.get_or_create(username=username)
            if user.is_active and user.role != "agent":
                if not request.user.is_authenticated or request.user.pk != user.pk:
                    login(request, user, backend="core.auth.DisabledPasswordBackend")
            else:
                logout(request)
        elif not (settings.DEV_LOGIN and request.META.get("REMOTE_ADDR") in ("127.0.0.1", "::1")):
            if request.user.is_authenticated:
                logout(request)
        return self.get_response(request)
