"""add is_tracked toggle to repositories and contributors

Lets admins switch a repo or contributor on/off without touching env vars or re-syncing.
EXCLUDED_REPOS / EXCLUDED_USERS env vars still seed the initial state on first sync but
the DB flag is the runtime source of truth from that point on.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-06

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repositories") as b:
        b.add_column(
            sa.Column("is_tracked", sa.Boolean, server_default=sa.true(), nullable=False)
        )
    op.create_index("ix_repo_is_tracked", "repositories", ["is_tracked"])

    with op.batch_alter_table("contributors") as b:
        b.add_column(
            sa.Column("is_tracked", sa.Boolean, server_default=sa.true(), nullable=False)
        )
    op.create_index("ix_contributor_is_tracked", "contributors", ["is_tracked"])


def downgrade() -> None:
    op.drop_index("ix_contributor_is_tracked", "contributors")
    op.drop_index("ix_repo_is_tracked", "repositories")
    with op.batch_alter_table("contributors") as b:
        b.drop_column("is_tracked")
    with op.batch_alter_table("repositories") as b:
        b.drop_column("is_tracked")
