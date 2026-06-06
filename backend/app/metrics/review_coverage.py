"""Review Coverage — % of merged PRs with at least one non-author review.

Per BRD §9.6.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import iso_week_start


class ReviewEvent(TypedDict, total=False):
    reviewer_login: str | None


class PRForCoverage(TypedDict, total=False):
    merged_at: datetime
    author_login: str | None
    reviews: list[ReviewEvent]


def is_reviewed(pr: PRForCoverage) -> bool:
    author = pr.get("author_login")
    for rv in pr.get("reviews", []):
        rl = rv.get("reviewer_login")
        if rl and rl != author:
            return True
    return False


def aggregate(prs: list[PRForCoverage]) -> float | None:
    merged = [pr for pr in prs if pr.get("merged_at") is not None]
    if not merged:
        return None
    reviewed = sum(1 for pr in merged if is_reviewed(pr))
    return round(100.0 * reviewed / len(merged), 1)


def per_week(prs: list[PRForCoverage], start: date, end: date) -> list[tuple[date, float | None]]:
    buckets: dict[date, list[bool]] = defaultdict(list)
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if not (start <= w <= end):
            continue
        buckets[w].append(is_reviewed(pr))
    out = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        vals = buckets.get(cur, [])
        if vals:
            out.append((cur, round(100.0 * sum(vals) / len(vals), 1)))
        else:
            out.append((cur, None))
        cur = cur + timedelta(days=7)
    return out
