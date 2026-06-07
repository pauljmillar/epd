"""create data_sources table; link repositories via data_source_id

Lets admins configure GitHub/GitLab credentials and the watched org/group from the UI
instead of redeploying with new env vars. Env vars continue to work as a one-time seed
fallback (handled in app/main.py lifespan).

repositories.data_source_id lets us cleanly scope soft-remove and purge actions to one
source. Backfill matches existing repos to a synthetic data_source row keyed on
(source, derived org_or_group). After backfill, the data_source_id column is non-null
for any repo whose org could be inferred.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Supabase pooler imposes an ~8s statement timeout that fires during the ALTER TABLE on
    # repositories (even a metadata-only column add can trip it under load). Lift it for the
    # duration of this migration's transaction.
    op.execute("SET LOCAL statement_timeout = 0")
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("org_or_group", sa.String(256), nullable=False),
        sa.Column("token", sa.Text, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source", "org_or_group", name="uq_data_source_org"),
    )

    with op.batch_alter_table("repositories") as b:
        b.add_column(
            sa.Column(
                "data_source_id",
                sa.Integer,
                sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
    op.create_index("ix_repo_data_source_id", "repositories", ["data_source_id"])


def downgrade() -> None:
    op.drop_index("ix_repo_data_source_id", "repositories")
    with op.batch_alter_table("repositories") as b:
        b.drop_column("data_source_id")
    op.drop_table("data_sources")
