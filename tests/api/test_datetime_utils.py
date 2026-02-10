from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from repairshopr_api.utils import coerce_datetime, parse_datetime, relative_cutoff


def test_parse_datetime_handles_inconsistent_formats() -> None:
    assert parse_datetime("2026-01-01T00:00:00Z") == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert parse_datetime("2026-01-01T00:00:00+0000") == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert parse_datetime("2026-01-01 00:00:00+00:00") == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert parse_datetime("2026-01-01T00:00:00.123456789Z") == datetime(
        2026, 1, 1, microsecond=123456, tzinfo=timezone.utc
    )
    assert parse_datetime("not-a-datetime") is None


def test_coerce_datetime_supports_date_strings_and_epoch_values() -> None:
    assert coerce_datetime(date(2026, 1, 1)) == datetime(2026, 1, 1)
    assert coerce_datetime("2026-01-01T00:00:00Z") == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert coerce_datetime(1_704_067_200) == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert coerce_datetime(1_704_067_200_000) == datetime(
        2024, 1, 1, tzinfo=timezone.utc
    )
    assert coerce_datetime(object()) is None


def test_relative_cutoff_uses_reference_timezone() -> None:
    aware_reference = datetime.now(tz=timezone.utc)
    aware_cutoff = relative_cutoff(aware_reference, delta=timedelta(days=1))
    assert aware_cutoff.tzinfo is not None

    naive_reference = datetime.now()
    naive_cutoff = relative_cutoff(naive_reference, delta=timedelta(days=1))
    assert naive_cutoff.tzinfo is None
