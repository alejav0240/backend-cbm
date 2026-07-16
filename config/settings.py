from pathlib import Path
import os
from dotenv import load_dotenv

# Monkeypatch to bypass database version checks (PostgreSQL 10.23 vs Django 4.2 requirement of 12+)
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.check_database_version_supported = lambda self: None

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-#hp^*p*3sd(2p3d)75%a(-f9rpyy72k0!mr#w8qift&-6+v0%&")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "api.musicoterapiabolivia.com",
    "plataform.musicoterapiabolivia.com",
    "plataforma.musicoterapiabolivia.com",
]

if DEBUG:
    ALLOWED_HOSTS = ["*"]

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Application definition

INSTALLED_APPS = [
    "unfold",                      # before django.contrib.admin
    "unfold.contrib.filters",      # special filters
    "unfold.contrib.forms",        # special form elements
    "unfold.contrib.inlines",      # special inlines

    "config.apps.CBMAdminConfig",  # replaced django.contrib.admin
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # externas
    'graphene_django',
    'graphql_jwt.refresh_token',
    'corsheaders',

    # propias
    'users',
    'institutions',
    'clinical',
    'therapeutic_sessions',
    'finance',
    'marketing',
    'evaluations',
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("POSTGRES_DB"),
        'USER': os.getenv("POSTGRES_USER"),
        'PASSWORD': os.getenv("POSTGRES_PASSWORD"),
        'HOST': os.getenv("DB_HOST"),
        'PORT': os.getenv("DB_PORT"),
    }
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

GRAPHENE = {
    "SCHEMA": "config.schema.schema",
    "MIDDLEWARE": [
        "graphql_jwt.middleware.JSONWebTokenMiddleware",
    ],
}

AUTHENTICATION_BACKENDS = [
    "graphql_jwt.backends.JSONWebTokenBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_USER_MODEL = "users.User"

import datetime

JWT_EXPIRATION_DELTA = datetime.timedelta(minutes=5)
JWT_REFRESH_EXPIRATION_DELTA = datetime.timedelta(days=7)

GRAPHQL_JWT = {
    "JWT_VERIFY_EXPIRATION": True,
    "JWT_LONG_RUNNING_REFRESH_TOKEN": True,
    "JWT_REUSE_REFRESH_TOKENS": True,
    "JWT_COOKIE_NAME": "access_token",
    "JWT_REFRESH_TOKEN_COOKIE_NAME": "refresh_token",
    "JWT_COOKIE_HTTPONLY": True,
    "JWT_COOKIE_SECURE": not DEBUG,
    "JWT_COOKIE_SAMESITE": "Lax",
}

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_DOMAIN = ".musicoterapiabolivia.com"
SESSION_COOKIE_SAMESITE = "Lax"

# Tell Django the original request was HTTPS (Apache proxy terminates SSL)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://plataform.musicoterapiabolivia.com",
    "https://plataforma.musicoterapiabolivia.com",
    "https://api.musicoterapiabolivia.com",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://plataform.musicoterapiabolivia.com",
    "https://plataforma.musicoterapiabolivia.com",
    "https://api.musicoterapiabolivia.com",
]

CORS_ALLOW_CREDENTIALS = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Internationalization

LANGUAGE_CODE = 'es-bo'
TIME_ZONE = 'America/La_Paz'
USE_I18N = True
USE_TZ = True

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Unfold Admin

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": "CBM Admin",
    "SITE_HEADER": "CBM Plataforma",
    "SITE_SYMBOL": "medical_services",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "COLORS": {
        "primary": {
            "50": "250 245 255",
            "100": "243 232 255",
            "200": "233 213 255",
            "300": "216 180 254",
            "400": "192 132 252",
            "500": "168 85 247",
            "600": "147 51 234",
            "700": "126 34 206",
            "800": "107 33 168",
            "900": "88 28 135",
            "950": "59 7 100",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Administración y Usuarios"),
                "separator": True,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                    {
                        "title": _("Usuarios"),
                        "icon": "people",
                        "link": reverse_lazy("admin:users_user_changelist"),
                    },
                    {
                        "title": _("Grupos y Roles"),
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
            {
                "title": _("Gestión Clínica"),
                "separator": True,
                "items": [
                    {
                        "title": _("Pacientes"),
                        "icon": "person",
                        "link": reverse_lazy("admin:clinical_patient_changelist"),
                    },
                    {
                        "title": _("Planes de Intervención"),
                        "icon": "assignment",
                        "link": reverse_lazy("admin:clinical_interventionplan_changelist"),
                    },
                    {
                        "title": _("Reportes Terapéuticos"),
                        "icon": "analytics",
                        "link": reverse_lazy("admin:clinical_therapyreport_changelist"),
                    },
                ],
            },
            {
                "title": _("Sesiones y Recursos"),
                "separator": True,
                "items": [
                    {
                        "title": _("Sesiones"),
                        "icon": "event",
                        "link": reverse_lazy("admin:therapeutic_sessions_session_changelist"),
                    },
                    {
                        "title": _("Inventario"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:therapeutic_sessions_inventoryitem_changelist"),
                    },
                    {
                        "title": _("Recursos Digitales"),
                        "icon": "cloud_download",
                        "link": reverse_lazy("admin:therapeutic_sessions_digitalresource_changelist"),
                    },
                ],
            },
            {
                "title": _("Gestión Financiera"),
                "separator": True,
                "items": [
                    {
                        "title": _("Pagos"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:finance_payment_changelist"),
                    },
                    {
                        "title": _("Gastos"),
                        "icon": "money_off",
                        "link": reverse_lazy("admin:finance_expense_changelist"),
                    },
                    {
                        "title": _("Cursos"),
                        "icon": "school",
                        "link": reverse_lazy("admin:finance_course_changelist"),
                    },
                ],
            },
        ],
    },
    "TABS": [
        {
            "models": [
                "users.user",
                "auth.group",
            ],
            "items": [
                {
                    "title": _("Usuarios"),
                    "link": reverse_lazy("admin:users_user_changelist"),
                },
                {
                    "title": _("Grupos y Roles"),
                    "link": reverse_lazy("admin:auth_group_changelist"),
                },
            ],
        },
        {
            "models": [
                "clinical.patient",
                "clinical.interventionplan",
                "clinical.therapyreport",
            ],
            "items": [
                {
                    "title": _("Pacientes"),
                    "link": reverse_lazy("admin:clinical_patient_changelist"),
                },
                {
                    "title": _("Planes"),
                    "link": reverse_lazy("admin:clinical_interventionplan_changelist"),
                },
                {
                    "title": _("Reportes"),
                    "link": reverse_lazy("admin:clinical_therapyreport_changelist"),
                },
            ],
        },
    ],
    "DASHBOARD": {
        "navigation": [
            {
                "title": _("Atajos Rápidos"),
                "items": [
                    {
                        "title": _("Pacientes"),
                        "icon": "person",
                        "link": reverse_lazy("admin:clinical_patient_changelist"),
                    },
                    {
                        "title": _("Sesiones"),
                        "icon": "event",
                        "link": reverse_lazy("admin:therapeutic_sessions_session_changelist"),
                    },
                ],
            },
        ],
        "widgets": [
            {
                "wrapper_class": "col-span-full",
                "template": "admin/widgets/dashboard.html",
            },
        ],
    },
}
