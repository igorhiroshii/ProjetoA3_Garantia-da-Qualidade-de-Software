"""Settings minimos para subir o Django-Helpdesk com a massa de dados do SAC.

Uso:  DJANGO_SETTINGS_MODULE=sac_settings python seed_sac_omnichannel.py --migrate --reset
O banco e um SQLite local (SAC_DB_PATH, padrao ./sac_seed.sqlite3).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEBUG = True
SECRET_KEY = "somente-para-teste-nao-usar-em-producao-0123456789abcdef0123456789"
ALLOWED_HOSTS = ["*"]
SITE_ID = 1
USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"      # fuso real da operacao; o comando de escalonamento usa UTC (ver relatorio)
LANGUAGE_CODE = "pt-br"
STATIC_URL = "/static/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": os.environ.get("SAC_DB_PATH", str(BASE_DIR / "sac_seed.sqlite3")),
}}

INSTALLED_APPS = (
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.humanize", "django.contrib.messages", "django.contrib.sessions",
    "django.contrib.sites", "django.contrib.staticfiles", "rest_framework", "helpdesk",
)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.contrib.auth.context_processors.auth", "django.template.context_processors.request",
        "django.contrib.messages.context_processors.messages", "django.template.context_processors.i18n",
        "django.template.context_processors.media", "django.template.context_processors.static",
        "django.template.context_processors.tz", "django.template.context_processors.debug"]},
}]
ROOT_URLCONF = "sac_urls"
LOGIN_URL = "/login/"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"   # nada sai da maquina
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # rapido; so para teste

# --- Django-Helpdesk ---
HELPDESK_TEAMS_MODEL = "auth.User"
HELPDESK_TEAMS_MIGRATION_DEPENDENCIES = []
HELPDESK_KBITEM_TEAM_GETTER = lambda _: None
# Isolamento entre filas (Varejo nao ve Ouvidoria/Banco). Sem isto, todo is_staff ve tudo.
HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION = True
HELPDESK_VIEW_A_TICKET_PUBLIC = True
