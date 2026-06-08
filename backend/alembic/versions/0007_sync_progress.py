"""add per-repo progress + cancel + event buffer to sync_log

Lets the dashboard show "Syncing 12/51 — astral-sh/ruff" plus a tail of recent events,
and lets the user cancel a long-running sync mid-flight.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Same Supabase pooler timeout workaround as 0006 — the ALTER TABLE can trip an ~8s
    # statement timeout otherwise.
    op.execute("SET LOCAL statement_timeout = 0")
    with op.batch_alter_table("sync_log") as b:
        b.add_column(sa.Column("total_repos", sa.Integer, server_default="0", nullable=False))
        b.add_column(sa.Column("repos_done", sa.Integer, server_default="0", nullable=False))
        b.add_column(sa.Column("current_source_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("current_repo", sa.String(512), nullable=True))
        b.add_column(
            sa.Column(
                "cancel_requested", sa.Boolean, server_default=sa.false(), nullable=False
            )
        )
        b.add_column(
            sa.Column("events", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("sync_log") as b:
        b.drop_column("events")
        b.drop_column("cancel_requested")
        b.drop_column("current_repo")
        b.drop_column("current_source_id")
        b.drop_column("repos_done")
        b.drop_column("total_repos")
