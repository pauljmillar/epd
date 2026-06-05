"""PR Throughput — merged PRs per week, optionally by author.

Per BRD §9.4: count of merged PRs per calendar week, excluding bots (handled upstream by
EXCLUDED_USERS filter — this module just counts).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import iso_week_start


class PRForThroughput(TypedDict, total=False):
    merged_at: datetime
    author_login: str | None


def per_week(prs: list[PRForThroughput], start: date, end: date) -> list[tuple[date, int]]:
    buckets: dict[date, int] = defaultdict(int)
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if start <= w <= end:
            buckets[w] += 1

    out: list[tuple[date, int]] = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        out.append((cur, buckets.get(cur, 0)))
        cur = cur + timedelta(days=7)
    return out


def per_author_total(prs: list[PRForThroughput]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for pr in prs:
        if pr.get("merged_at") is None:
            continue
        login = pr.get("author_login")
        if login:
            out[login] += 1
    return dict(out)
