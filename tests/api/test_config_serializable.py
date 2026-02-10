from __future__ import annotations

from repairshopr_api.config.base import AppSettings
from repairshopr_api.config.sections.django import Django


def test_serializable_uses_class_annotations_for_to_dict_and_from_dict() -> None:
    django = Django()

    django.from_dict(
        {
            "secret_key": "secret",
            "db_host": "db.internal",
            "db_name": "repairshopr",
        }
    )

    serialized = django.to_dict()
    assert serialized["secret_key"] == "secret"
    assert serialized["db_host"] == "db.internal"
    assert serialized["db_name"] == "repairshopr"
    assert "db_engine" in serialized
    assert "db_name" in serialized


def test_app_settings_persists_nested_section_values(
    tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("REPAIRSHOPR_CONFIG_FILE", str(config_path))

    app_settings = AppSettings()
    app_settings.debug = True
    app_settings.django.secret_key = "django-secret"
    app_settings.django.db_host = "sync-db"
    app_settings.repairshopr.token = "token-value"
    app_settings.repairshopr.url_store_name = "store-name"
    app_settings.save()

    reloaded = AppSettings()
    assert reloaded.debug is True
    assert reloaded.django.secret_key == "django-secret"
    assert reloaded.django.db_host == "sync-db"
    assert reloaded.repairshopr.token == "token-value"
    assert reloaded.repairshopr.url_store_name == "store-name"
