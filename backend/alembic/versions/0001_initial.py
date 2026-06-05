"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-05

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contributors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("login", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256)),
        sa.Column("avatar_url", sa.String(512)),
        sa.UniqueConstraint("source", "source_id", name="uq_contributor_source"),
    )
    op.create_index("ix_contributors_login", "contributors", ["login"])

    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("default_branch", sa.String(128), server_default="main"),
        sa.UniqueConstraint("source", "source_id", name="uq_repo_source"),
    )
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"])

    op.create_table(
        "pull_requests",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("contributors.id")),
        sa.Column("title", sa.String(1024), server_default=""),
        sa.Column("url", sa.String(1024)),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("additions", sa.Integer, server_default="0"),
        sa.Column("deletions", sa.Integer, server_default="0"),
        sa.Column("base_branch", sa.String(128), server_default="main"),
        sa.Column("is_draft", sa.Boolean, server_default=sa.false()),
        sa.UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),
    )
    op.create_index("ix_pull_requests_repo_id", "pull_requests", ["repo_id"])
    op.create_index("ix_pull_requests_author_id", "pull_requests", ["author_id"])
    op.create_index("ix_pull_requests_opened_at", "pull_requests", ["opened_at"])
    op.create_index("ix_pull_requests_merged_at", "pull_requests", ["merged_at"])

    op.create_table(
        "pr_reviews",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("pr_id", sa.BigInteger, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("contributors.id")),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.UniqueConstraint("pr_id", "source_id", name="uq_review_source"),
    )
    op.create_index("ix_pr_reviews_pr_id", "pr_reviews", ["pr_id"])

    op.create_table(
        "pr_commits",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("pr_id", sa.BigInteger, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("pr_id", "sha", name="uq_commit_pr_sha"),
    )
    op.create_index("ix_pr_commits_pr_id", "pr_commits", ["pr_id"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_type", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(256), nullable=False),
        sa.UniqueConstraint("repo_id", "signal_type", "ref", name="uq_dep_ref"),
    )
    op.create_index("ix_deployments_repo_id", "deployments", ["repo_id"])
    op.create_index("ix_deployments_triggered_at", "deployments", ["triggered_at"])

    op.create_table(
        "contributor_month_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("contributor_id", sa.Integer, sa.ForeignKey("contributors.id")),
        sa.Column("repo_id", sa.Integer, sa.ForeignKey("repositories.id")),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column("prs_merged", sa.Integer, server_default="0"),
        sa.Column("prs_reviewed", sa.Integer, server_default="0"),
        sa.Column("lead_time_p50_hours", sa.Numeric(10, 2)),
        sa.Column("lead_time_p75_hours", sa.Numeric(10, 2)),
        sa.Column("deployment_count", sa.Integer, server_default="0"),
        sa.Column("is_finalized", sa.Boolean, server_default=sa.false()),
        sa.UniqueConstraint(
            "contributor_id", "repo_id", "year_month", name="uq_snapshot_contrib_repo_month"
        ),
    )
    op.create_index("ix_snapshot_year_month", "contributor_month_snapshots", ["year_month"])
    op.create_index("ix_snapshot_is_finalized", "contributor_month_snapshots", ["is_finalized"])

    op.create_table(
        "sync_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("repos_synced", sa.Integer, server_default="0"),
        sa.Column("prs_synced", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(32), server_default="running"),
        sa.Column("error", sa.String(2048)),
    )


def downgrade() -> None:
    for table in [
        "sync_log",
        "contributor_month_snapshots",
        "deployments",
        "pr_commits",
        "pr_reviews",
        "pull_requests",
        "repositories",
        "contributors",
    ]:
        op.drop_table(table)
