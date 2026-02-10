from repairshopr_api.config.initialize import settings
from repairshopr_api.type_defs import JsonObject


def display_settings() -> list[dict[str, str | JsonObject]]:
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
