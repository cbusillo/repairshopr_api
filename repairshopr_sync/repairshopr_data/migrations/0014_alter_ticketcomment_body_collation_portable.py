"""Align TicketComment.body collation on already-migrated MySQL databases.

This migration performs an explicit MySQL database operation because the
historical migration state was made backend-agnostic for portability.
"""

import re

from django.db import migrations


_SAFE_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z_]+$")


def _safe_identifier(value: str) -> str:
    if not value or not _SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"Unsafe identifier: {value!r}")
    return value


def _mysql_align_column_collation_to_table(apps, schema_editor) -> None:
    if schema_editor.connection.vendor != "mysql":
        return

    ticket_comment = apps.get_model("repairshopr_data", "TicketComment")
    table_name = ticket_comment._meta.db_table
    column_name = "body"

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT TABLE_COLLATION
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            [table_name],
        )
        table_row = cursor.fetchone()
        if not table_row or not table_row[0]:
            return
        table_collation = table_row[0]

        cursor.execute(
            """
            SELECT
                c.COLLATION_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                cca.CHARACTER_SET_NAME
            FROM information_schema.COLUMNS c
            JOIN information_schema.COLLATION_CHARACTER_SET_APPLICABILITY cca
                ON cca.COLLATION_NAME = %s
            WHERE
                c.TABLE_SCHEMA = DATABASE()
                AND c.TABLE_NAME = %s
                AND c.COLUMN_NAME = %s
            """,
            [table_collation, table_name, column_name],
        )
        column_row = cursor.fetchone()

    if not column_row:
        return

    column_collation, data_type, is_nullable, table_charset = column_row
    if column_collation == table_collation:
        return

    data_type = (data_type or "").upper()
    if data_type not in {"TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT"}:
        return

    null_sql = "NULL" if (is_nullable or "").upper() == "YES" else "NOT NULL"
    table_charset = _safe_identifier(table_charset)
    table_collation = _safe_identifier(table_collation)

    schema_editor.execute(
        " ".join(
            [
                f"ALTER TABLE {schema_editor.quote_name(table_name)}",
                "MODIFY COLUMN",
                schema_editor.quote_name(column_name),
                data_type,
                null_sql,
                f"CHARACTER SET {table_charset}",
                f"COLLATE {table_collation}",
            ]
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ("repairshopr_data", "0013_add_api_fields"),
    ]

    operations = [
        migrations.RunPython(
            _mysql_align_column_collation_to_table,
            reverse_code=migrations.RunPython.noop,
        )
    ]

