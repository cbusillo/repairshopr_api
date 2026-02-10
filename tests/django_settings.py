from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_ROOT = ROOT / "repairshopr_sync"

if str(SYNC_ROOT) not in sys.path:
    sys.path.insert(0, str(SYNC_ROOT))

SECRET_KEY = "test-secret-key"
DEBUG = True
USE_TZ = True
TIME_ZONE = "UTC"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "repairshopr_data.apps.RepairshoprDataConfig",
]

MIDDLEWARE: list[str] = []
ROOT_URLCONF = "tests.empty_urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

MIGRATION_MODULES = {"repairshopr_data": None}
