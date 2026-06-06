"""PR Size — median lines changed (additions + deletions) per PR."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import iso_week_start, percentile


class PRForSize(TypedDict, total=False):
    merged_at: datetime
    additions: int
    deletions: int


def lines_changed(pr: PRForSize) -> int:
    return int(pr.get("additions", 0)) + int(pr.get("deletions", 0))


def aggregate(prs: list[PRForSize]) -> float | None:
    sizes = [lines_changed(pr) for pr in prs if pr.get("merged_at") is not None]
    return percentile(sizes, 50)


def per_week(prs: list[PRForSize], start: date, end: date) -> list[tuple[date, float | None]]:
    buckets: dict[date, list[int]] = defaultdict(list)
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if not (start <= w <= end):
            continue
        buckets[w].append(lines_changed(pr))
    out = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        out.append((cur, percentile(buckets.get(cur, []), 50)))
        cur = cur + timedelta(days=7)
    return out


def count_large(prs: list[PRForSize], threshold: int) -> int:
    """How many merged PRs were over the large-PR threshold."""
    return sum(
        1
        for pr in prs
        if pr.get("merged_at") is not None and lines_changed(pr) > threshold
    )
