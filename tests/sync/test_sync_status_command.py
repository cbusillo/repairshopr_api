from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from repairshopr_data.management.commands import sync_status as sync_status_module


def _status_manager(status_row: object) -> SimpleNamespace:
    return SimpleNamespace(
        filter=lambda **_kwargs: SimpleNamespace(first=lambda: status_row)
    )


def test_sync_status_outputs_single_line_json(monkeypatch: pytest.MonkeyPatch) -> None:
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    status_row = SimpleNamespace(
        status="running",
        mode="full",
        cycle_id="cycle-123",
        current_model="invoice",
        current_page=55,
        records_processed=4321,
        cycle_started_at=current_time - timedelta(minutes=4),
        cycle_finished_at=None,
        last_heartbeat=current_time - timedelta(seconds=20),
        last_error=None,
        updated_at=current_time - timedelta(seconds=4),
    )

    monkeypatch.setattr(sync_status_module, "now", lambda: current_time)
    monkeypatch.setattr(
        sync_status_module,
        "SyncStatus",
        SimpleNamespace(objects=_status_manager(status_row)),
    )

    command = sync_status_module.Command()
    output_lines: list[str] = []
    monkeypatch.setattr(command.stdout, "write", output_lines.append)

    command.handle(stale_threshold_seconds=60, fail_on_stale=False)

    assert len(output_lines) == 1
    payload = json.loads(output_lines[0])
    assert payload["status"] == "running"
    assert payload["current_model"] == "invoice"
    assert payload["cycle_age_seconds"] == 240
    assert payload["heartbeat_age_seconds"] == 20
    assert payload["is_stale"] is False


def test_sync_status_exits_when_fail_on_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    current_time = datetime(2026, 2, 12, 18, tzinfo=timezone.utc)
    status_row = SimpleNamespace(
        status="running",
        mode="incremental",
        cycle_id="cycle-456",
        current_model="ticket",
        current_page=12,
        records_processed=99,
        cycle_started_at=current_time - timedelta(minutes=6),
        cycle_finished_at=None,
        last_heartbeat=current_time - timedelta(minutes=3),
        last_error=None,
        updated_at=current_time,
    )

    monkeypatch.setattr(sync_status_module, "now", lambda: current_time)
    monkeypatch.setattr(
        sync_status_module,
        "SyncStatus",
        SimpleNamespace(objects=_status_manager(status_row)),
    )

    command = sync_status_module.Command()
    monkeypatch.setattr(command.stdout, "write", lambda _line: None)

    with pytest.raises(SystemExit) as exit_info:
        command.handle(stale_threshold_seconds=30, fail_on_stale=True)

    assert exit_info.value.code == 2
