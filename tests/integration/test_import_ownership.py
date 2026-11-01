import os
from unittest.mock import MagicMock

import pytest
from django.core.management.base import CommandError
from django.db import connection
from pytest_django.plugin import DjangoDbBlocker
from repairshopr_data import import_ownership
from repairshopr_data.management.commands import import_from_repairshopr as importer
from repairshopr_data.models import SyncStatus

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("RUN_MARIADB_INTEGRATION") != "1", reason="MariaDB integration job only"),
]


def abort_import() -> None:
    raise RuntimeError("interrupted")


def test_database_overlap_and_recovery(monkeypatch: pytest.MonkeyPatch, django_db_blocker: DjangoDbBlocker) -> None:
    with django_db_blocker.unblock():
        monkeypatch.setattr("repairshopr_data.management.commands.import_from_repairshopr.Client", MagicMock)
        owner = connection.copy(alias="import_owner")
        contender = connection.copy(alias="import_contender")
        try:
            SyncStatus.objects.filter(id=1).delete()
            command = importer.Command()
            monkeypatch.setattr("repairshopr_data.import_ownership.connection", owner)
            with pytest.raises(RuntimeError, match="interrupted"):
                with import_ownership.exclusive_import():
                    command._mark_sync_cycle_started(full_sync=True)
                    interrupted: SyncStatus = SyncStatus.objects.get(id=1)
                    interrupted_id = interrupted.cycle_id
                    monkeypatch.setattr("repairshopr_data.import_ownership.connection", contender)
                    with pytest.raises(CommandError):
                        importer.Command().handle()
                    interrupted.refresh_from_db()
                    assert interrupted.cycle_id == interrupted_id
                    abort_import()

            with import_ownership.exclusive_import():
                command._mark_sync_cycle_started(full_sync=True)
                row: SyncStatus = SyncStatus.objects.get(id=1)
                assert row.unrecovered_full_cycle_id == interrupted_id
                command._mark_sync_cycle_finished()
                row.refresh_from_db()
                assert row.unrecovered_full_cycle_id is None
        finally:
            owner.close()
            contender.close()
            SyncStatus.objects.filter(id=1).delete()
