# EPD — Engineering Productivity Dashboard

A self-hosted, open-source engineering productivity dashboard for VPs of Engineering.
Connects to GitHub (GitLab planned), derives accurate metrics from PR/commit data alone,
and renders a clean black-and-white executive view.

> **Status: walking skeleton (v0).** Three of the six target metrics are implemented end-to-end:
> Deployment Frequency, Lead Time for Changes, and PR Throughput. The remaining metrics, the
> Team/Metric/Contributor detail pages, and GitLab support are tracked in the [BRD](docs/brd.md)
> and will land in subsequent iterations.

## Why this exists

Commercial tools (LinearB, DX, Jellyfish) start at hundreds of dollars per contributor per year
and demand many integrations. Open-source alternatives (Google Four Keys, Apache DevLake,
Middleware) are either archived, complex to operate, or DORA-only. EPD aims to be the minimal,
opinionated, self-hosted option: one PAT and one org, and you get a dashboard.

The design philosophy is **accuracy over breadth**: a small set of metrics that are reliably
calculable from git and PR data alone, rather than a large set requiring CI/CD, issue trackers,
and HRIS data many teams don't have.

## Quickstart (Docker)

```bash
git clone https://github.com/pauljmillar/epd
cd epd
cp .env.example .env
# Edit .env: set GITHUB_TOKEN and GITHUB_ORG
docker compose up -d
open http://localhost:3000
```

The first run does a backfill of `BACKFILL_MONTHS` (default 3) of PR history. Watch progress at
`http://localhost:8000/api/v1/sync/status`.

## Local dev (no Docker, Supabase Postgres)

Useful when you want to iterate on the code on a machine without Docker.

1. Create a Supabase project; copy the connection pooler URL.
2. Backend:
   ```bash
   cd backend
   uv sync
   export DATABASE_URL="postgresql+psycopg://postgres.PROJECT:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
   export GITHUB_TOKEN=ghp_xxx
   export GITHUB_ORG=astral-sh
   export BACKFILL_MONTHS=3
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```
3. Frontend (in another terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:5173.

## Demo recipe (no PR history of your own)

If you're trying this out on your own GitHub account and don't have PRs to show, point EPD at a
real public org:

```env
GITHUB_TOKEN=ghp_xxxx        # any PAT with read:org, public_repo
GITHUB_ORG=astral-sh         # uv, ruff, rye — lots of PR activity at a manageable scale
BACKFILL_MONTHS=3
EXCLUDED_USERS=dependabot[bot],renovate[bot],github-actions[bot]
```

Other good demo orgs: `pola-rs`, `denoland`, `vercel` (set `EXCLUDED_REPOS=next.js` — that
repo alone has thousands of PRs).

## Metrics in v0

| Metric                 | Source                                          | Reference          |
| ---------------------- | ----------------------------------------------- | ------------------ |
| Deployment Frequency   | tags matching pattern, or merges to main branch | BRD §9.1           |
| Lead Time for Changes  | first commit → merge, P50 and P75               | BRD §9.2           |
| PR Throughput          | merged PRs per week                             | BRD §9.4           |

Planned for follow-up iterations: PR Cycle Time breakdown, PR Size, Review Coverage,
Time to First Review (see [BRD §9](docs/brd.md)).

## What EPD does NOT do

- **No individual scoring or rankings.** Per BRD §10, EPD does not produce composite
  productivity scores. Individual metrics are shown as context, never as performance review
  inputs.
- **No external integrations required.** No Jira/Linear, no PagerDuty, no Slack, no HRIS.
- **No MTTR / Change Failure Rate** in v1 — these require incident data we don't ingest.
- **Not a SaaS.** Self-hosted only.

## Configuration

See [`.env.example`](.env.example). Every opinionated default is overridable via environment
variable. Notable knobs:

- `BACKFILL_MONTHS` — initial history depth.
- `EXCLUDED_REPOS` / `EXCLUDED_USERS` — comma-separated.
- `DEPLOYMENT_BRANCH` (default `main`) vs `DEPLOYMENT_TAG_PATTERN` — the deployment signal.
- `LARGE_PR_THRESHOLD` — lines-changed threshold (used in later iterations).

## Architecture

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + APScheduler (in-process; no Celery/Redis).
- **Frontend:** React 18 + TypeScript + Vite + Tailwind + Tremor + Recharts.
- **Database:** PostgreSQL 16.
- **GitHub API:** GraphQL for PR+reviews+first-commit in one round trip; REST for repo and tag
  listings.
- **Snapshots:** Per-contributor-per-month rows. Prior months are finalized on the 1st of each
  month and never recalculated.

## Development

```bash
cd backend && uv run pytest -q       # backend unit tests
cd frontend && npm run typecheck     # frontend type check
cd frontend && npm run build         # production build
```

CI runs all of the above plus `docker compose build`.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Bug reports and PRs welcome. See the [BRD](docs/brd.md) for the long-term roadmap, then open
an issue before non-trivial work so we can sanity-check scope against the design philosophy
(accuracy over breadth, no individual scoring, no required integrations).
