from __future__ import annotations

import json
import runpy
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

DISPLAY_SCRIPT = Path(__file__).resolve().parents[2] / "repairshopr_api" / "config" / "display_settings.py"


@pytest.fixture
def synthetic_settings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Bypass the initializer before importing config classes: it can write TOML.
    package = ModuleType("repairshopr_api.config")
    package.__path__ = [str(DISPLAY_SCRIPT.parent)]
    monkeypatch.setitem(sys.modules, "repairshopr_api.config", package)

    from repairshopr_api.config.sections import Django, Repairshopr

    settings = SimpleNamespace(repairshopr=Repairshopr(), django=Django())
    settings.repairshopr.token = "synthetic-api-token"
    settings.repairshopr.url_store_name = "example-store"
    settings.django.last_updated_at = datetime(2026, 10, 4, tzinfo=UTC)

    initializer = ModuleType("repairshopr_api.config.initialize")
    initializer.__dict__["settings"] = settings
    monkeypatch.setitem(sys.modules, "repairshopr_api.config.initialize", initializer)
    return settings


def test_direct_execution_displays_settings_without_credentials(
    synthetic_settings: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {
        "Repairshopr": synthetic_settings.repairshopr.to_dict(),
        "Django": synthetic_settings.django.to_dict(),
    }

    runpy.run_path(str(DISPLAY_SCRIPT), run_name="__main__")

    stdout = capsys.readouterr().out
    sections = {entry["section"]: entry["fields"] for entry in json.loads(stdout)}
    assert sections["Repairshopr"]["url_store_name"] == "example-store"
    assert sections["Django"]["last_updated_at"] == str(synthetic_settings.django.last_updated_at)
    assert sections["Repairshopr"]["token"] == "[REDACTED]"
    assert before["Repairshopr"]["token"] not in stdout
    assert synthetic_settings.repairshopr.to_dict() == before["Repairshopr"]
    assert synthetic_settings.django.to_dict() == before["Django"]


def test_import_preserves_callable_contract_without_printing(
    synthetic_settings: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    namespace = runpy.run_path(str(DISPLAY_SCRIPT))

    result = namespace["display_settings"]()

    assert capsys.readouterr().out == ""
    assert [entry["section"] for entry in result] == ["Repairshopr", "Django"]
    assert result[0]["fields"] is synthetic_settings.repairshopr.__dict__
    assert result[1]["fields"] is synthetic_settings.django.__dict__
    assert result[0]["fields"]["token"] == synthetic_settings.repairshopr.token


def test_additional_fields_are_redacted(synthetic_settings: SimpleNamespace, capsys: pytest.CaptureFixture[str]) -> None:
    synthetic_settings.django.extra_password = "synthetic-extra-secret"

    runpy.run_path(str(DISPLAY_SCRIPT), run_name="__main__")

    stdout = capsys.readouterr().out
    sections = {entry["section"]: entry["fields"] for entry in json.loads(stdout)}
    assert sections["Django"]["extra_password"] == "[REDACTED]"
    assert synthetic_settings.django.extra_password not in stdout
