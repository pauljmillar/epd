from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def iso_week_start(d: datetime | date) -> date:
    """Monday of the ISO week containing d."""
    if isinstance(d, datetime):
        d = d.date()
    return d - timedelta(days=d.weekday())


def year_month(d: datetime | date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile, p in [0, 100]. Returns None for empty input."""
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def ensure_utc(d: datetime) -> datetime:
    if d.tzinfo is None:
        return d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)
