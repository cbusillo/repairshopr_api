from pathlib import Path

from django.conf import settings as django_settings
from django.core.management.commands.flush import Command as FlushCommand

from repairshopr_api.config import settings


class Command(FlushCommand):
    def handle(self, *args, **options) -> None:
        super().handle(**options)

        settings.django.last_updated_at = None
        settings.save()

        if (
            django_settings.DATABASES["default"]["ENGINE"]
            == "django.db.backends.sqlite3"
        ):
            Path(django_settings.DATABASES["default"]["NAME"]).unlink()

        # Keep migration files intact. Removing them during runtime breaks
        # subsequent `migrate` executions in long-lived containers.
