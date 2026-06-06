"""Tests for the four metrics added in the v1 batch."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.metrics import (
    pr_cycle_time as ct,
    pr_size as sz,
    review_coverage as rc,
    time_to_first_review as ttfr,
)


def _utc(y, m, d, h=12, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# ---------- Cycle Time ----------

def test_cycle_time_phases_with_review_and_approval():
    pr = {
        "opened_at": _utc(2026, 6, 1, 10),
        "merged_at": _utc(2026, 6, 2, 18),
        "author_login": "alice",
        "reviews": [
            {"submitted_at": _utc(2026, 6, 1, 14), "state": "COMMENTED", "reviewer_login": "bob"},
            {"submitted_at": _utc(2026, 6, 2, 14), "state": "APPROVED", "reviewer_login": "bob"},
        ],
    }
    pickup, review, merge = ct.phases_hours(pr)
    assert pickup == 4.0
    assert review == 24.0
    assert merge == 4.0
    assert ct.total_hours(pr) == 32.0


def test_cycle_time_no_reviews_collapses_to_merge_phase():
    pr = {
        "opened_at": _utc(2026, 6, 1),
        "merged_at": _utc(2026, 6, 2),
        "author_login": "alice",
        "reviews": [],
    }
    assert ct.phases_hours(pr) == (0.0, 0.0, 24.0)


def test_cycle_time_ignores_self_reviews():
    pr = {
        "opened_at": _utc(2026, 6, 1),
        "merged_at": _utc(2026, 6, 2),
        "author_login": "alice",
        "reviews": [
            {"submitted_at": _utc(2026, 6, 1, 6), "state": "COMMENTED", "reviewer_login": "alice"},
        ],
    }
    # Only the author "reviewed" — should fall back to no-review treatment.
    assert ct.phases_hours(pr) == (0.0, 0.0, 24.0)


def test_cycle_time_aggregate_returns_phase_medians():
    prs = [
        {"opened_at": _utc(2026, 6, 1), "merged_at": _utc(2026, 6, 2),
         "author_login": "a", "reviews": []},  # 0/0/24
        {"opened_at": _utc(2026, 6, 1), "merged_at": _utc(2026, 6, 3),
         "author_login": "a", "reviews": []},  # 0/0/48
    ]
    agg = ct.aggregate(prs)
    assert agg["pickup_p50"] == 0.0
    assert agg["review_p50"] == 0.0
    assert agg["merge_p50"] == 36.0
    assert agg["total_p50"] == 36.0


# ---------- PR Size ----------

def test_pr_size_lines_changed_sums():
    assert sz.lines_changed({"additions": 100, "deletions": 23}) == 123


def test_pr_size_median_only_counts_merged():
    prs = [
        {"merged_at": _utc(2026, 6, 1), "additions": 100, "deletions": 0},
        {"merged_at": _utc(2026, 6, 2), "additions": 300, "deletions": 100},
        {"merged_at": None, "additions": 9999, "deletions": 9999},  # ignored
    ]
    assert sz.aggregate(prs) == 250.0


def test_pr_size_count_large():
    prs = [
        {"merged_at": _utc(2026, 6, 1), "additions": 100, "deletions": 0},
        {"merged_at": _utc(2026, 6, 2), "additions": 500, "deletions": 0},
        {"merged_at": _utc(2026, 6, 3), "additions": 0, "deletions": 401},
    ]
    assert sz.count_large(prs, 400) == 2


# ---------- Review Coverage ----------

def test_review_coverage_is_pct_of_reviewed():
    prs = [
        {"merged_at": _utc(2026, 6, 1), "author_login": "a", "reviews": []},
        {"merged_at": _utc(2026, 6, 2), "author_login": "a",
         "reviews": [{"reviewer_login": "b"}]},
        {"merged_at": _utc(2026, 6, 3), "author_login": "a",
         "reviews": [{"reviewer_login": "a"}]},  # self-review only — doesn't count
        {"merged_at": _utc(2026, 6, 4), "author_login": "a",
         "reviews": [{"reviewer_login": "c"}]},
    ]
    # 2 of 4 reviewed → 50.0%
    assert rc.aggregate(prs) == 50.0


def test_review_coverage_none_for_empty():
    assert rc.aggregate([]) is None


# ---------- Time to First Review ----------

def test_first_review_uses_earliest_non_author_review():
    pr = {
        "opened_at": _utc(2026, 6, 1, 10),
        "merged_at": _utc(2026, 6, 2),
        "author_login": "alice",
        "reviews": [
            {"submitted_at": _utc(2026, 6, 1, 11), "reviewer_login": "alice"},  # self
            {"submitted_at": _utc(2026, 6, 1, 13), "reviewer_login": "bob"},    # 3h
            {"submitted_at": _utc(2026, 6, 1, 15), "reviewer_login": "carol"},  # 5h (ignored — later)
        ],
    }
    assert ttfr.hours_to_first_review(pr) == 3.0


def test_first_review_none_when_no_non_author_reviewer():
    pr = {
        "opened_at": _utc(2026, 6, 1),
        "merged_at": _utc(2026, 6, 2),
        "author_login": "alice",
        "reviews": [{"submitted_at": _utc(2026, 6, 1, 1), "reviewer_login": "alice"}],
    }
    assert ttfr.hours_to_first_review(pr) is None


def test_first_review_per_week():
    prs = [
        {"opened_at": _utc(2026, 6, 1, 0), "merged_at": _utc(2026, 6, 2),
         "author_login": "a", "reviews": [
             {"submitted_at": _utc(2026, 6, 1, 4), "reviewer_login": "b"}
         ]},  # 4h, week of 6/1
        {"opened_at": _utc(2026, 6, 2, 0), "merged_at": _utc(2026, 6, 3),
         "author_login": "a", "reviews": [
             {"submitted_at": _utc(2026, 6, 2, 8), "reviewer_login": "b"}
         ]},  # 8h, week of 6/1
    ]
    series = ttfr.per_week(prs, date(2026, 6, 1), date(2026, 6, 1))
    assert series == [(date(2026, 6, 1), 6.0)]
