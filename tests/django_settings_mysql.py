from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_ROOT = ROOT / "repairshopr_sync"

if str(SYNC_ROOT) not in sys.path:
    sys.path.insert(0, str(SYNC_ROOT))

SECRET_KEY = "mysql-test-secret"
DEBUG = False
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
        "ENGINE": "django.db.backends.mysql",
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "PORT": int(os.environ.get("MYSQL_PORT", "3306")),
        "NAME": os.environ.get("MYSQL_DATABASE", "repairshopr_test"),
        "USER": os.environ.get("MYSQL_USER", "root"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", "root"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}
