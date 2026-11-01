from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.management.base import CommandError
from django.utils.timezone import now
from repairshopr_data.management.commands import import_from_repairshopr as importer
from repairshopr_data.models import SyncStatus
from repairshopr_data.sync_health import build_health_payload


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.get_model.return_value = []
    client.fetch_ticket_settings.return_value = {}
    monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.Client", lambda: client)
    return client


@pytest.mark.parametrize("lock_result", [0, None])
def test_lock_refusal_stops_import(monkeypatch: pytest.MonkeyPatch, lock_result: int | None) -> None:
    database = MagicMock(vendor="mysql", settings_dict={"NAME": "test"})
    database.cursor.return_value.__enter__.return_value.fetchone.return_value = (lock_result,)
    monkeypatch.setattr("repairshopr_data.import_ownership.connection", database)
    command = importer.Command()
    run = MagicMock()
    monkeypatch.setattr(command, "_run_import", run)
    with pytest.raises(CommandError):
        command.handle()
    run.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["running", "failed"])
def test_full_recovery(monkeypatch: pytest.MonkeyPatch, status: str, tmp_path: Path, fake_client: MagicMock) -> None:
    startup = tmp_path / "started"
    startup.touch()
    monkeypatch.setenv("SYNC_STARTUP_COMPLETE_FILE", str(startup))
    config = SimpleNamespace(django=SimpleNamespace(last_updated_at=now()), save=lambda: None)
    monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.settings", config)
    SyncStatus.objects.create(id=1, cycle_id="interrupted", mode="full", status=status)
    monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.exclusive_import", nullcontext)
    command = importer.Command()
    command.model_mapping = {"Product": command.model_mapping["Product"]}
    validation = MagicMock(side_effect=RuntimeError("retry failed"))
    monkeypatch.setattr(command, "validate_sync_completeness", validation)
    with pytest.raises(RuntimeError, match="retry failed"):
        command.handle()
    validation.assert_called_once_with(full_sync=True)
    assert fake_client.get_model.call_args.args[1:3] == (None, None)
    row: SyncStatus = SyncStatus.objects.get(id=1)
    assert row.status == "failed"
    assert row.unrecovered_full_cycle_id == "interrupted"
    payload, code = build_health_payload(900)
    assert code == 503
    assert payload["sync"]["unrecovered_full_cycle_id"] == "interrupted"

    validation.side_effect = None
    command.handle()
    row.refresh_from_db()
    assert row.mode == "full"
    assert row.status == "success"
    assert row.unrecovered_full_cycle_id is None
    assert build_health_payload(900)[1] == 200


@pytest.mark.django_db
def test_incremental_success_cannot_clear_full_failure() -> None:
    SyncStatus.objects.create(id=1, unrecovered_full_cycle_id="interrupted", mode="incremental", status="running")
    command = importer.Command()
    command._cycle_mode = "incremental"
    command._mark_sync_cycle_finished()
    row: SyncStatus = SyncStatus.objects.get(id=1)
    assert row.unrecovered_full_cycle_id == "interrupted"


@pytest.mark.django_db
def test_empty_error_is_failure_and_normal_completion_is_not_interruption() -> None:
    command = importer.Command()
    command._mark_sync_cycle_started(full_sync=True)
    command._mark_sync_cycle_finished(error_message="")
    row: SyncStatus = SyncStatus.objects.get(id=1)
    assert row.status == "failed"
    assert row.unrecovered_full_cycle_id == row.cycle_id
    command._mark_sync_cycle_started(full_sync=True)
    command._mark_sync_cycle_finished()
    command._mark_sync_cycle_started(full_sync=False)
    command._mark_sync_cycle_started(full_sync=False)
    row.refresh_from_db()
    assert row.unrecovered_full_cycle_id is None
