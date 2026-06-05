"""Lead Time for Changes — first commit to merge, in hours.

Per BRD §9.2: median (P50) and P75, weekly. Falls back to PR open time when no commits.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import ensure_utc, iso_week_start, percentile


class PRForLeadTime(TypedDict, total=False):
    opened_at: datetime
    merged_at: datetime
    first_commit_at: datetime | None


def lead_time_hours(pr: PRForLeadTime) -> float | None:
    merged = pr.get("merged_at")
    if merged is None:
        return None
    start = pr.get("first_commit_at") or pr.get("opened_at")
    if start is None:
        return None
    delta = ensure_utc(merged) - ensure_utc(start)
    return max(delta.total_seconds() / 3600.0, 0.0)


def per_week(
    prs: list[PRForLeadTime], start: date, end: date
) -> list[tuple[date, float | None, float | None]]:
    """Return [(week_start, p50_hours, p75_hours), ...] keyed by merge week."""
    buckets: dict[date, list[float]] = defaultdict(list)
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if not (start <= w <= end):
            continue
        lt = lead_time_hours(pr)
        if lt is None:
            continue
        buckets[w].append(lt)

    out: list[tuple[date, float | None, float | None]] = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        vals = buckets.get(cur, [])
        out.append((cur, percentile(vals, 50), percentile(vals, 75)))
        cur = cur + timedelta(days=7)
    return out


def aggregate(prs: list[PRForLeadTime]) -> tuple[float | None, float | None]:
    vals = [v for v in (lead_time_hours(p) for p in prs) if v is not None]
    return percentile(vals, 50), percentile(vals, 75)
