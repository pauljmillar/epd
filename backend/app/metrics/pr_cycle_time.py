"""PR Cycle Time — total open→merge, broken into pickup / review / merge phases.

Per BRD §9.3:
  - Pickup time:  PR opened → first review event (any non-author review)
  - Review time:  first review event → last approval
  - Merge time:   last approval → merge

PRs merged with no reviews: pickup=0, review=0, merge=total cycle time.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from .common import ensure_utc, iso_week_start, percentile


class ReviewEvent(TypedDict):
    submitted_at: datetime
    state: str  # APPROVED | CHANGES_REQUESTED | COMMENTED
    reviewer_login: str | None


class PRForCycleTime(TypedDict, total=False):
    opened_at: datetime
    merged_at: datetime | None
    author_login: str | None
    reviews: list[ReviewEvent]


def _non_author_reviews(pr: PRForCycleTime) -> list[ReviewEvent]:
    author = pr.get("author_login")
    out = []
    for rv in pr.get("reviews", []):
        if rv.get("reviewer_login") and rv["reviewer_login"] != author:
            out.append(rv)
    return sorted(out, key=lambda r: ensure_utc(r["submitted_at"]))


def phases_hours(pr: PRForCycleTime) -> tuple[float, float, float] | None:
    """Return (pickup, review, merge) in hours, or None if PR isn't merged."""
    merged = pr.get("merged_at")
    opened = pr.get("opened_at")
    if merged is None or opened is None:
        return None

    opened_u = ensure_utc(opened)
    merged_u = ensure_utc(merged)
    total_h = max((merged_u - opened_u).total_seconds() / 3600.0, 0.0)

    reviews = _non_author_reviews(pr)
    if not reviews:
        return (0.0, 0.0, total_h)

    first_review_at = ensure_utc(reviews[0]["submitted_at"])
    approvals = [ensure_utc(r["submitted_at"]) for r in reviews if r.get("state") == "APPROVED"]
    last_approval_at = max(approvals) if approvals else first_review_at

    pickup_h = max((first_review_at - opened_u).total_seconds() / 3600.0, 0.0)
    review_h = max((last_approval_at - first_review_at).total_seconds() / 3600.0, 0.0)
    merge_h = max((merged_u - last_approval_at).total_seconds() / 3600.0, 0.0)
    return (pickup_h, review_h, merge_h)


def total_hours(pr: PRForCycleTime) -> float | None:
    p = phases_hours(pr)
    return None if p is None else sum(p)


def aggregate(prs: list[PRForCycleTime]) -> dict[str, float | None]:
    totals: list[float] = []
    pickups: list[float] = []
    reviews_l: list[float] = []
    merges: list[float] = []
    for pr in prs:
        p = phases_hours(pr)
        if p is None:
            continue
        pickups.append(p[0])
        reviews_l.append(p[1])
        merges.append(p[2])
        totals.append(sum(p))
    return {
        "total_p50": percentile(totals, 50),
        "pickup_p50": percentile(pickups, 50),
        "review_p50": percentile(reviews_l, 50),
        "merge_p50": percentile(merges, 50),
    }


def per_week_phases(
    prs: list[PRForCycleTime], start: date, end: date
) -> list[tuple[date, float | None, float | None, float | None]]:
    """Return [(week_start, pickup_p50, review_p50, merge_p50), ...] keyed by merge week."""
    buckets: dict[date, dict[str, list[float]]] = defaultdict(
        lambda: {"pickup": [], "review": [], "merge": []}
    )
    for pr in prs:
        merged = pr.get("merged_at")
        if merged is None:
            continue
        w = iso_week_start(merged)
        if not (start <= w <= end):
            continue
        p = phases_hours(pr)
        if p is None:
            continue
        buckets[w]["pickup"].append(p[0])
        buckets[w]["review"].append(p[1])
        buckets[w]["merge"].append(p[2])

    out = []
    cur = iso_week_start(start)
    last = iso_week_start(end)
    while cur <= last:
        b = buckets.get(cur)
        if b:
            out.append(
                (
                    cur,
                    percentile(b["pickup"], 50),
                    percentile(b["review"], 50),
                    percentile(b["merge"], 50),
                )
            )
        else:
            out.append((cur, None, None, None))
        cur = cur + timedelta(days=7)
    return out
