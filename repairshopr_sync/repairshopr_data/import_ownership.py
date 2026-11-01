from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256

from django.core.management.base import CommandError
from django.db import connection


@contextmanager
def exclusive_import() -> Iterator[None]:
    if connection.vendor != "mysql":
        raise CommandError("Exclusive imports require the MySQL/MariaDB sync database")
    database_name = str(connection.settings_dict["NAME"])
    lock_name = f"repairshopr-import:{sha256(database_name.encode()).hexdigest()[:40]}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT IS_FREE_LOCK(%s)", [lock_name])
        if cursor.fetchone() != (1,):
            raise CommandError("Another importer owns the database; retry on the next sync interval")
        cursor.execute("SELECT GET_LOCK(%s, 0)", [lock_name])
        if cursor.fetchone() != (1,):
            raise CommandError("Could not obtain exclusive import ownership; retry on the next sync interval")
        try:
            yield
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", [lock_name])
