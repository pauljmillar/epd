"""Deployment Frequency — count of deployments per week.

Inputs are plain dicts so this can be unit-tested without the DB.
A deployment is: {"triggered_at": datetime}.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import TypedDict

from .common import iso_week_start


class Deployment(TypedDict):
    triggered_at: datetime


def per_week(
    deployments: list[Deployment], start: date, end: date
) -> list[tuple[date, int]]:
    """Return [(week_start_monday, count), ...] covering [start, end] inclusive of weeks touched."""
    buckets: dict[date, int] = defaultdict(int)
    for d in deployments:
        w = iso_week_start(d["triggered_at"])
        if start <= w <= end:
            buckets[w] += 1

    out: list[tuple[date, int]] = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        out.append((cur, buckets.get(cur, 0)))
        from datetime import timedelta
        cur = cur + timedelta(days=7)
    return out


def per_week_average(series: list[tuple[date, int]]) -> float:
    if not series:
        return 0.0
    return sum(c for _, c in series) / len(series)
