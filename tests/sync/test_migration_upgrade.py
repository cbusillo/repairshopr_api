from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import override_settings
from pytest_django.plugin import DjangoDbBlocker
from repairshopr_data.models import Customer, SyncStatus


def test_recorded_squash_history_upgrades_without_recreating_tables(
    monkeypatch: pytest.MonkeyPatch, django_db_blocker: DjangoDbBlocker, tmp_path: Path
) -> None:
    history = json.loads((Path(__file__).parents[1] / "fixtures" / "recorded_squashed_migration_history.json").read_text())
    database_settings = deepcopy(connection.settings_dict)
    database_settings.update(ENGINE="django.db.backends.sqlite3", NAME=str(tmp_path / "migration.sqlite3"))
    alias = "migration_upgrade"
    monkeypatch.setitem(connections.databases, alias, database_settings)
    isolated = connections[alias]
    try:
        with django_db_blocker.unblock(), override_settings(MIGRATION_MODULES={}):
            executor = MigrationExecutor(isolated)
            app_label = Customer._meta.app_label
            squash = (app_label, history["squash"])
            executor.migrate([squash])
            customer = cast(type[Customer], executor.loader.project_state([squash]).apps.get_model(app_label, Customer.__name__))
            customer.objects.using(alias).create(id=42, firstname="Retained")
            recorder = MigrationRecorder(isolated)
            for name in history["replaced"]:
                recorder.record_applied(app_label, name)
            executor = MigrationExecutor(isolated)
            leaves = executor.loader.graph.leaf_nodes()
            assert all((migration.app_label, migration.name) != squash for migration, _ in executor.migration_plan(leaves))
            executor.migrate(leaves)
            executor = MigrationExecutor(isolated)
            executor.loader.check_consistent_history(isolated)
            assert executor.migration_plan(leaves) == []
            assert SyncStatus._meta.db_table in isolated.introspection.table_names()
            assert customer.objects.using(alias).get(id=42).firstname == "Retained"
    finally:
        isolated.close()
        del connections[alias]
