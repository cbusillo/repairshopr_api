import os
from pathlib import Path

from repairshopr_api.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = settings.django.secret_key

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "repairshopr_data.apps.RepairshoprDataConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# noinspection PyUnresolvedReferences
ROOT_URLCONF = "repairshopr_sync.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "repairshopr_sync.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": f"django.db.backends.{os.getenv('SYNC_DB_ENGINE') or settings.django.db_engine}",
        "HOST": os.getenv("SYNC_DB_HOST") or settings.django.db_host,
        "NAME": os.getenv("SYNC_DB_NAME") or settings.django.db_name,
        "USER": os.getenv("SYNC_DB_USER") or settings.django.db_user,
        "PASSWORD": os.getenv("SYNC_DB_PASSWORD") or settings.django.db_password,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
