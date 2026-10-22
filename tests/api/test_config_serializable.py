from __future__ import annotations

from repairshopr_api.config.base import AppSettings
from repairshopr_api.config.sections.django import Django


def test_serializable_uses_class_annotations_for_to_dict_and_from_dict() -> None:
    django = Django()

    django.from_dict(
        {
            "last_updated_at": "2026-10-01T12:00:00",
            "secret_key": "secret",
        }
    )

    assert django.to_dict() == {"last_updated_at": "2026-10-01T12:00:00"}


def test_app_settings_persists_nested_section_values(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("REPAIRSHOPR_CONFIG_FILE", str(config_path))

    app_settings = AppSettings()
    app_settings.debug = True
    app_settings.django.last_updated_at = "2026-10-01T12:00:00"
    app_settings.repairshopr.token = "token-value"
    app_settings.repairshopr.url_store_name = "store-name"
    app_settings.save()

    reloaded = AppSettings()
    assert reloaded.debug is True
    assert reloaded.django.last_updated_at == "2026-10-01T12:00:00"
    assert reloaded.repairshopr.token == "token-value"
    assert reloaded.repairshopr.url_store_name == "store-name"
