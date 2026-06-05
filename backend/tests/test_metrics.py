from __future__ import annotations

from datetime import date, datetime, timezone

from app.metrics import deployment_frequency as df
from app.metrics import lead_time as lt
from app.metrics import throughput as tp
from app.metrics.common import iso_week_start, percentile, year_month


def _utc(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_percentile_basic():
    assert percentile([], 50) is None
    assert percentile([5], 50) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4], 75) == 3.25


def test_iso_week_start_monday():
    # 2026-06-05 is a Friday; Monday is 2026-06-01
    assert iso_week_start(date(2026, 6, 5)) == date(2026, 6, 1)


def test_year_month_format():
    assert year_month(date(2026, 1, 9)) == "2026-01"


def test_deployment_per_week_buckets_and_fills_zeros():
    deps = [
        {"triggered_at": _utc(2026, 6, 2)},  # week of 2026-06-01
        {"triggered_at": _utc(2026, 6, 4)},  # week of 2026-06-01
        {"triggered_at": _utc(2026, 6, 9)},  # week of 2026-06-08
    ]
    series = df.per_week(deps, date(2026, 6, 1), date(2026, 6, 15))
    assert series == [
        (date(2026, 6, 1), 2),
        (date(2026, 6, 8), 1),
        (date(2026, 6, 15), 0),
    ]
    assert df.per_week_average(series) == 1.0


def test_lead_time_uses_first_commit_over_open():
    pr = {
        "opened_at": _utc(2026, 6, 4),
        "merged_at": _utc(2026, 6, 5),
        "first_commit_at": _utc(2026, 6, 1),
    }
    # 96 hours from first commit to merge
    assert lt.lead_time_hours(pr) == 96.0


def test_lead_time_falls_back_to_opened_at():
    pr = {
        "opened_at": _utc(2026, 6, 4),
        "merged_at": _utc(2026, 6, 5),
        "first_commit_at": None,
    }
    assert lt.lead_time_hours(pr) == 24.0


def test_lead_time_per_week_p50_p75():
    prs = [
        {"opened_at": _utc(2026, 6, 1), "merged_at": _utc(2026, 6, 2), "first_commit_at": _utc(2026, 6, 1)},  # 24h
        {"opened_at": _utc(2026, 6, 1), "merged_at": _utc(2026, 6, 3), "first_commit_at": _utc(2026, 6, 1)},  # 48h
        {"opened_at": _utc(2026, 6, 1), "merged_at": _utc(2026, 6, 5), "first_commit_at": _utc(2026, 6, 1)},  # 96h
    ]
    series = lt.per_week(prs, date(2026, 6, 1), date(2026, 6, 1))
    assert series[0][0] == date(2026, 6, 1)
    assert series[0][1] == 48.0  # P50
    assert series[0][2] == 72.0  # P75


def test_throughput_per_week_and_per_author():
    prs = [
        {"merged_at": _utc(2026, 6, 2), "author_login": "alice"},
        {"merged_at": _utc(2026, 6, 3), "author_login": "alice"},
        {"merged_at": _utc(2026, 6, 9), "author_login": "bob"},
        {"merged_at": None, "author_login": "carol"},
    ]
    series = tp.per_week(prs, date(2026, 6, 1), date(2026, 6, 8))
    assert series == [(date(2026, 6, 1), 2), (date(2026, 6, 8), 1)]
    assert tp.per_author_total(prs) == {"alice": 2, "bob": 1}
