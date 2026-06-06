from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Contributor(Base):
    __tablename__ = "contributors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # github|gitlab
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    login: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_contributor_source"),)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_repo_source"),)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_team_id: Mapped[str | None] = mapped_column(String(64))


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    contributor_id: Mapped[int] = mapped_column(ForeignKey("contributors.id"), primary_key=True)


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), index=True)
    title: Mapped[str] = mapped_column(String(1024), default="")
    url: Mapped[str | None] = mapped_column(String(1024))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    base_branch: Mapped[str] = mapped_column(String(128), default="main")
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ai_tool: Mapped[str | None] = mapped_column(String(32))

    repo: Mapped[Repository] = relationship()
    author: Mapped[Contributor | None] = relationship()

    __table_args__ = (UniqueConstraint("repo_id", "number", name="uq_pr_repo_number"),)


class PRReview(Base):
    __tablename__ = "pr_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False, index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"))
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (UniqueConstraint("pr_id", "source_id", name="uq_review_source"),)


class PRCommit(Base):
    __tablename__ = "pr_commits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pr_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False, index=True)
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("pr_id", "sha", name="uq_commit_pr_sha"),)


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False, index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)  # tag | branch_merge
    ref: Mapped[str] = mapped_column(String(256), nullable=False)

    __table_args__ = (UniqueConstraint("repo_id", "signal_type", "ref", name="uq_dep_ref"),)


class ContributorMonthSnapshot(Base):
    __tablename__ = "contributor_month_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contributor_id: Mapped[int | None] = mapped_column(ForeignKey("contributors.id"), index=True)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), index=True)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # 2026-05
    prs_merged: Mapped[int] = mapped_column(Integer, default=0)
    prs_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_p50_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    lead_time_p75_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    deployment_count: Mapped[int] = mapped_column(Integer, default=0)
    median_pr_size_lines: Mapped[float | None] = mapped_column(Numeric(10, 2))
    review_coverage_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    median_time_to_first_review_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_pr_cycle_time_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_pickup_time_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_review_time_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    median_merge_time_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "contributor_id", "repo_id", "year_month", name="uq_snapshot_contrib_repo_month"
        ),
    )


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repos_synced: Mapped[int] = mapped_column(Integer, default=0)
    prs_synced: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|completed|failed
    error: Mapped[str | None] = mapped_column(String(2048))
