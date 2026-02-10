from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone


_TZ_WITHOUT_COLON_RE = re.compile(r"([+-]\d{2})(\d{2})$")
_EXCESS_MICROS_RE = re.compile(r"(\.\d{6})\d+")


def _normalize_datetime_string(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    normalized = normalized.replace(" UTC", "+00:00")
    normalized = normalized.replace(" GMT", "+00:00")

    if _TZ_WITHOUT_COLON_RE.search(normalized):
        normalized = _TZ_WITHOUT_COLON_RE.sub(r"\1:\2", normalized)

    # Python supports microseconds up to 6 digits. RepairShopr occasionally
    # returns higher precision, so trim instead of rejecting the timestamp.
    normalized = _EXCESS_MICROS_RE.sub(r"\1", normalized)
    return normalized


def parse_datetime(value: str) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized = _normalize_datetime_string(value)
    candidates = [normalized]
    if " " in normalized:
        candidates.append(normalized.replace(" ", "T", 1))

    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        return parse_datetime(value)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return None


def relative_cutoff(reference: datetime, *, delta: timedelta) -> datetime:
    if reference.tzinfo is None:
        return datetime.now() - delta
    return datetime.now(tz=reference.tzinfo) - delta

