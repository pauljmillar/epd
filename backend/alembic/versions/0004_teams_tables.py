"""create teams + team_members tables

The schema was specified in BRD §13 but never created. Migration 0001 only created the raw
event tables. Adding now to support real Teams (B+ in BACKLOG.md).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-06

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source_team_id", sa.String(64), nullable=True),
        sa.UniqueConstraint("name", name="uq_team_name"),
    )
    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column(
            "contributor_id",
            sa.Integer,
            sa.ForeignKey("contributors.id"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("team_members")
    op.drop_table("teams")
