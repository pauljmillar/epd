"""add v1 metric columns to contributor_month_snapshots

Per BRD §8 snapshot schema. Read path is still live-compute in v0; these columns let the
snapshot builder pre-materialize them so the API can later switch to snapshot reads.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-06

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contributor_month_snapshots") as b:
        b.add_column(sa.Column("median_pr_size_lines", sa.Numeric(10, 2)))
        b.add_column(sa.Column("review_coverage_pct", sa.Numeric(5, 2)))
        b.add_column(sa.Column("median_time_to_first_review_hours", sa.Numeric(10, 2)))
        b.add_column(sa.Column("median_pr_cycle_time_hours", sa.Numeric(10, 2)))
        b.add_column(sa.Column("median_pickup_time_hours", sa.Numeric(10, 2)))
        b.add_column(sa.Column("median_review_time_hours", sa.Numeric(10, 2)))
        b.add_column(sa.Column("median_merge_time_hours", sa.Numeric(10, 2)))


def downgrade() -> None:
    with op.batch_alter_table("contributor_month_snapshots") as b:
        for col in [
            "median_pr_size_lines",
            "review_coverage_pct",
            "median_time_to_first_review_hours",
            "median_pr_cycle_time_hours",
            "median_pickup_time_hours",
            "median_review_time_hours",
            "median_merge_time_hours",
        ]:
            b.drop_column(col)
