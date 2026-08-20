from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import repairshopr_data.management.commands.flush as command_module


@dataclass
class DjangoConfigStub:
    last_updated_at: str | None = "previous-checkpoint"


class AppSettingsStub:
    def __init__(self, events: list[str]) -> None:
        self.django = DjangoConfigStub()
        self._events = events

    def save(self) -> None:
        self._events.append("save")


@dataclass
class DjangoSettingsStub:
    BASE_DIR: Path
    DATABASES: dict[str, dict[str, str]]


@dataclass
class FlushTestContext:
    app_settings: AppSettingsStub
    database_path: Path
    migration_path: Path
    events: list[str]


def _prepare_flush(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    database_engine: str,
) -> FlushTestContext:
    database_path = tmp_path / "database"
    database_path.touch()
    migration_path = tmp_path / "repairshopr_data" / "migrations" / "0001_initial.py"
    migration_path.parent.mkdir(parents=True)
    migration_path.write_text("# migration\n")
    events: list[str] = []
    app_settings = AppSettingsStub(events)
    django_settings = DjangoSettingsStub(
        BASE_DIR=tmp_path,
        DATABASES={
            "default": {
                "ENGINE": database_engine,
                "NAME": str(database_path),
            }
        },
    )
    monkeypatch.setattr(
        "repairshopr_data.management.commands.flush.settings", app_settings
    )
    monkeypatch.setattr(
        "repairshopr_data.management.commands.flush.django_settings", django_settings
    )
    return FlushTestContext(
        app_settings=app_settings,
        database_path=database_path,
        migration_path=migration_path,
        events=events,
    )


@pytest.mark.parametrize(
    ("database_engine", "database_deleted"),
    [
        pytest.param("django.db.backends.sqlite3", True, id="sqlite"),
        pytest.param("django.db.backends.mysql", False, id="mysql"),
    ],
)
def test_flush_resets_checkpoint_after_parent_and_preserves_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    database_engine: str,
    database_deleted: bool,
) -> None:
    context = _prepare_flush(tmp_path, monkeypatch, database_engine)

    def parent_handle(_command: object, **_options: object) -> None:
        context.events.append("parent")

    monkeypatch.setattr(command_module.FlushCommand, "handle", parent_handle)

    command_module.Command().handle(interactive=False)

    assert context.events == ["parent", "save"]
    assert context.app_settings.django.last_updated_at is None
    assert context.database_path.exists() is not database_deleted
    assert context.migration_path.read_text() == "# migration\n"


def test_flush_does_not_cleanup_when_django_flush_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _prepare_flush(tmp_path, monkeypatch, "django.db.backends.sqlite3")

    def parent_handle(_command: object, **_options: object) -> None:
        context.events.append("parent")
        raise RuntimeError("django flush failed")

    monkeypatch.setattr(command_module.FlushCommand, "handle", parent_handle)

    with pytest.raises(RuntimeError, match="django flush failed"):
        command_module.Command().handle()

    assert context.events == ["parent"]
    assert context.app_settings.django.last_updated_at == "previous-checkpoint"
    assert context.database_path.exists()
    assert context.migration_path.exists()
