"""Time to First Review — median hours from PR open to first non-author review event.

Per BRD §9.7. Only PRs with ≥1 non-author review are counted.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import ensure_utc, iso_week_start, percentile


class ReviewEvent(TypedDict, total=False):
    submitted_at: datetime
    reviewer_login: str | None


class PRForFirstReview(TypedDict, total=False):
    opened_at: datetime
    merged_at: datetime | None
    author_login: str | None
    reviews: list[ReviewEvent]


def hours_to_first_review(pr: PRForFirstReview) -> float | None:
    opened = pr.get("opened_at")
    if opened is None:
        return None
    author = pr.get("author_login")
    times = []
    for rv in pr.get("reviews", []):
        rl = rv.get("reviewer_login")
        sub = rv.get("submitted_at")
        if rl and rl != author and sub is not None:
            times.append(ensure_utc(sub))
    if not times:
        return None
    return max((min(times) - ensure_utc(opened)).total_seconds() / 3600.0, 0.0)


def aggregate(prs: list[PRForFirstReview]) -> float | None:
    vals = [
        v
        for v in (hours_to_first_review(p) for p in prs if p.get("merged_at") is not None)
        if v is not None
    ]
    return percentile(vals, 50)


def per_week(
    prs: list[PRForFirstReview], start: date, end: date
) -> list[tuple[date, float | None]]:
    buckets: dict[date, list[float]] = defaultdict(list)
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if not (start <= w <= end):
            continue
        v = hours_to_first_review(pr)
        if v is not None:
            buckets[w].append(v)
    out = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        out.append((cur, percentile(buckets.get(cur, []), 50)))
        cur = cur + timedelta(days=7)
    return out
