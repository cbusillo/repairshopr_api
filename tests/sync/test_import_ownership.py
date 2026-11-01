from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.core.management.base import CommandError
from repairshopr_data.management.commands import import_from_repairshopr as importer
from repairshopr_data.models import SyncStatus
from repairshopr_data.sync_health import build_health_payload


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.Client", MagicMock)


@pytest.mark.parametrize("lock_results", [[(0,)], [(1,), (0,)], [(1,), (None,)]])
def test_lock_refusal_stops_import(monkeypatch: pytest.MonkeyPatch, lock_results: list[tuple[int | None]]) -> None:
    database = MagicMock(vendor="mysql", settings_dict={"NAME": "test"})
    database.cursor.return_value.__enter__.return_value.fetchone.side_effect = lock_results
    monkeypatch.setattr("repairshopr_data.import_ownership.connection", database)
    command = importer.Command()
    run = MagicMock()
    monkeypatch.setattr(command, "_run_import", run)
    with pytest.raises(CommandError):
        command.handle()
    run.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("previous_status", ["running", "failed"])
def test_failure_survives_retries(monkeypatch: pytest.MonkeyPatch, previous_status: str, tmp_path: Path) -> None:
    startup = tmp_path / "started"
    startup.touch()
    monkeypatch.setenv("SYNC_STARTUP_COMPLETE_FILE", str(startup))
    SyncStatus.objects.create(id=1, cycle_id="interrupted", mode="full", status=previous_status)
    monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.exclusive_import", nullcontext)
    command = importer.Command()
    command._mark_sync_cycle_started(full_sync=False)
    command._mark_sync_cycle_finished()
    row: SyncStatus = SyncStatus.objects.get(id=1)
    assert row.status == "success"
    assert row.unrecovered_full_cycle_id == "interrupted"
    payload, code = build_health_payload(900)
    assert code == 503
    assert payload["sync"]["unrecovered_full_cycle_id"] == "interrupted"
    assert "full_sync_recovery_required" in payload["not_ready_reasons"]

    command._mark_sync_cycle_started(full_sync=True)
    command._mark_sync_cycle_finished(error_message="retry failed")
    command._mark_sync_cycle_started(full_sync=True)
    row.refresh_from_db()
    assert row.status == "running"
    assert row.unrecovered_full_cycle_id == "interrupted"
    command._mark_sync_cycle_finished()
    row.refresh_from_db()
    assert row.status == "success"
    assert row.unrecovered_full_cycle_id is None
    assert build_health_payload(900)[1] == 200


@pytest.mark.django_db
def test_caught_full_failure_retained_but_normal_completion_and_incremental_interruption_are_not() -> None:
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
