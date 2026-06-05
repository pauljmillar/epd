from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "EPD"
    secret_key: str = "change-me"
    database_url: str = "postgresql+psycopg://epd:epd@localhost:5432/epd"

    # Source control
    github_token: str | None = None
    github_org: str | None = None
    gitlab_token: str | None = None
    gitlab_group: str | None = None

    # Collection
    backfill_months: int = 3
    excluded_repos: str = ""
    excluded_users: str = "dependabot[bot],renovate[bot],github-actions[bot]"
    deployment_branch: str = "main"
    deployment_tag_pattern: str | None = None
    large_pr_threshold: int = 400

    # Optional auth
    admin_password: str | None = None

    @property
    def excluded_repo_set(self) -> set[str]:
        return {r.strip() for r in self.excluded_repos.split(",") if r.strip()}

    @property
    def excluded_user_set(self) -> set[str]:
        return {u.strip() for u in self.excluded_users.split(",") if u.strip()}


settings = Settings()
