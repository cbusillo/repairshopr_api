import json

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


def main() -> None:
    sections = (
        ("Repairshopr", settings.repairshopr, {"url_store_name"}),
        (
            "Django",
            settings.django,
            {"last_updated_at", "db_engine", "db_host", "db_name", "db_user"},
        ),
    )
    output = [
        {
            "section": name,
            "fields": {
                key: value if key in public_fields else "[REDACTED]"
                for key, value in section.to_dict().items()
            },
        }
        for name, section, public_fields in sections
    ]
    print(json.dumps(output, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
