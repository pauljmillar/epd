"""DataSource helpers shared between sync, the admin API, and the lifespan seed."""
from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select

from .config import settings
from .db import session_scope
from .models import DataSource

log = logging.getLogger(__name__)


def get_active_sources() -> Sequence[DataSource]:
    """All is_active=true data_sources. Detached copies safe to use after session close."""
    with session_scope() as s:
        rows = s.execute(select(DataSource).where(DataSource.is_active.is_(True))).scalars().all()
        # Detach so callers can read attributes after the session closes.
        for r in rows:
            s.expunge(r)
        return rows


def seed_from_env_vars() -> int:
    """Idempotent: if env vars define credentials and no matching data_source exists,
    create one. Logs each row created. Returns count created.

    Subsequent runs are no-ops because of the unique (source, org_or_group) constraint
    and the explicit existence check below."""
    created = 0
    candidates: list[tuple[str, str, str | None]] = []
    if settings.github_token and settings.github_org:
        candidates.append(("github", settings.github_org, settings.github_token))
    if settings.gitlab_token and settings.gitlab_group:
        candidates.append(("gitlab", settings.gitlab_group, settings.gitlab_token))

    if not candidates:
        return 0

    with session_scope() as s:
        for source, org, token in candidates:
            existing = s.execute(
                select(DataSource).where(
                    DataSource.source == source, DataSource.org_or_group == org
                )
            ).scalar_one_or_none()
            if existing:
                # If the env-var token changed, refresh it — operator may rotate this way.
                if token and existing.token != token:
                    existing.token = token
                    log.info("Refreshed token for existing data_source %s/%s", source, org)
                continue
            s.add(DataSource(source=source, org_or_group=org, token=token, is_active=True))
            created += 1
            log.info("Seeded data_source from env vars: %s/%s", source, org)

    return created
