import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
DEBUG = os.environ.get("MATOS_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("MATOS_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("MATOS_SECRET_KEY est obligatoire en production")
    SECRET_KEY = "local-development-only-never-use-in-production"
ALLOWED_HOSTS = os.environ.get("MATOS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
PUBLIC_URL = os.environ.get("MATOS_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
YNH_PORTAL_URL = os.environ.get("MATOS_YNH_PORTAL_URL", "")
DEV_LOGIN = DEBUG and os.environ.get("MATOS_DEV_LOGIN", "0") == "1"
TRUST_YNH_HEADERS = os.environ.get("MATOS_TRUST_YNH_HEADERS", "0") == "1"
DEV_LOGIN = DEV_LOGIN and not TRUST_YNH_HEADERS
MCP_TOKEN = os.environ.get("MATOS_MCP_TOKEN", "")
MCP_ALLOWED_HOSTS = os.environ.get("MATOS_MCP_ALLOWED_HOSTS", "127.0.0.1,localhost,127.0.0.1:*,localhost:*").split(",")
MCP_ALLOWED_ORIGINS = os.environ.get("MATOS_MCP_ALLOWED_ORIGINS", "http://127.0.0.1,http://localhost,http://127.0.0.1:*,http://localhost:*").split(",")
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "core", "epi", "dosimetry",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "core.auth.YunoHostMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "matos.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
              "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
              "OPTIONS": {"context_processors": [
                  "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages", "core.views.context",
              ]}}]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": os.environ.get("PGDATABASE", "arcenal_matos"),
    "USER": os.environ.get("PGUSER", os.environ.get("USER", "matos")),
    "PASSWORD": os.environ.get("PGPASSWORD", ""), "HOST": os.environ.get("PGHOST", "127.0.0.1"),
    "PORT": os.environ.get("PGPORT", "55432"), "CONN_MAX_AGE": 0,
}}
AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["core.auth.DisabledPasswordBackend"]
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("MATOS_DATA_DIR", str(BASE_DIR / ".local" / "data")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
EMAIL_BACKEND = os.environ.get("MATOS_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("MATOS_EMAIL_HOST", "127.0.0.1")
EMAIL_PORT = int(os.environ.get("MATOS_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("MATOS_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("MATOS_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("MATOS_EMAIL_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("MATOS_FROM_EMAIL", "matos@localhost")
EMAIL_TIMEOUT = 20
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_YNH_HEADERS else None
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_SSL_REDIRECT = not DEBUG
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
LOGIN_URL = "/login/"
