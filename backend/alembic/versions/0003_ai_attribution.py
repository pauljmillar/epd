"""add AI attribution columns to pull_requests

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-06

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pull_requests") as b:
        b.add_column(
            sa.Column("ai_assisted", sa.Boolean, server_default=sa.false(), nullable=False)
        )
        b.add_column(sa.Column("ai_tool", sa.String(32), nullable=True))
    op.create_index("ix_pr_ai_assisted", "pull_requests", ["ai_assisted"])


def downgrade() -> None:
    op.drop_index("ix_pr_ai_assisted", table_name="pull_requests")
    with op.batch_alter_table("pull_requests") as b:
        b.drop_column("ai_tool")
        b.drop_column("ai_assisted")
