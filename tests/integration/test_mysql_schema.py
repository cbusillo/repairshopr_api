from __future__ import annotations

import os

import pytest
from django.db import connection

pytestmark = [pytest.mark.integration]


@pytest.mark.skipif(
    os.environ.get("RUN_MYSQL_INTEGRATION") != "1", reason="MySQL integration job only"
)
def test_ticket_comment_body_collation_matches_table_default(django_db_blocker) -> None:
    table_name = "repairshopr_data_ticketcomment"
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_COLLATION
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                """,
                [table_name],
            )
            table_collation_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT COLLATION_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = 'body'
                """,
                [table_name],
            )
            body_collation_row = cursor.fetchone()

    assert table_collation_row is not None
    assert body_collation_row is not None
    assert body_collation_row[0] == table_collation_row[0]
