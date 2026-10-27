from __future__ import annotations

from copy import deepcopy

import pytest
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings


@pytest.mark.django_db
@pytest.mark.parametrize("existing_squash", [False, True])
def test_fresh_and_recorded_squash_databases_upgrade_without_recreating_tables(
    existing_squash: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_settings = deepcopy(connection.settings_dict)
    database_settings.update(ENGINE="django.db.backends.sqlite3", NAME=":memory:")
    monkeypatch.setitem(connections.databases, "migration_upgrade", database_settings)
    isolated = connections["migration_upgrade"]
    try:
        with override_settings(MIGRATION_MODULES={}):
            executor = MigrationExecutor(isolated)
            roots = executor.loader.graph.root_nodes("repairshopr_data")
            if existing_squash:
                executor.migrate(roots)
                with isolated.cursor() as cursor:
                    cursor.execute("INSERT INTO repairshopr_data_customer (id, firstname) VALUES (%s, %s)", [42, "Retained"])
                executor = MigrationExecutor(isolated)
                assert all(
                    migration.name != roots[0][1] for migration, _ in executor.migration_plan(executor.loader.graph.leaf_nodes())
                )
            executor.migrate(executor.loader.graph.leaf_nodes())
            executor = MigrationExecutor(isolated)
            executor.loader.check_consistent_history(isolated)
            assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
            assert "repairshopr_data_syncstatus" in isolated.introspection.table_names()
            if existing_squash:
                with isolated.cursor() as cursor:
                    cursor.execute("SELECT firstname FROM repairshopr_data_customer WHERE id = %s", [42])
                    assert cursor.fetchone() == ("Retained",)
    finally:
        if isolated.connection is not None:
            isolated.connection.close()
        del connections["migration_upgrade"]
