from typing import Any

from repairshopr_api.config.initialize import settings


def display_settings() -> list[dict[str, Any]]:
    return [
        {
            "section": "Repairshopr",
            "fields": settings.repairshopr.__dict__,
        },
        {
            "section": "Django",
            "fields": settings.django.__dict__,
        },
    ]
