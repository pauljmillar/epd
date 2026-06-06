# EPD — Engineering Productivity Dashboard

A self-hosted, open-source engineering productivity dashboard for VPs of Engineering.
Connects to GitHub (GitLab coming soon), derives accurate metrics from PR/commit data alone,
and renders a clean, executive-ready view.

🌐 **Live demo:** [epd-eta.vercel.app](https://epd-eta.vercel.app) — pointed at the
[`astral-sh`](https://github.com/astral-sh) org (uv, ruff, rye, etc.)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/epd)
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/pauljmillar/epd&root-directory=frontend&env=VITE_API_URL&envDescription=URL%20of%20the%20Railway%20backend)

---

## Why this exists

Commercial tools (LinearB, DX, Jellyfish) start at hundreds of dollars per contributor per
year and require many integrations. Open-source alternatives are archived (Google Four Keys),
complex (Apache DevLake), or DORA-only (Middleware). EPD aims to be the minimal, opinionated,
self-hosted option: one PAT and one org, and you get a dashboard.

The design philosophy is **accuracy over breadth** — a small set of metrics that are reliably
calculable from git and PR data alone, rather than a large set requiring CI/CD, issue
trackers, and HRIS data that many teams don't have.

## What's in the dashboard

Seven metrics, all from GitHub PR/commit data, no integrations required:

| Metric | What it shows | BRD |
|---|---|---|
| **Deployment Frequency** | Tags matching `DEPLOYMENT_TAG_PATTERN`, or merges to main | §9.1 |
| **Lead Time for Changes** | Median hours, first commit → merge (P50 + P75) | §9.2 |
| **PR Cycle Time** | Open → merge, broken into pickup / review / merge phases | §9.3 |
| **PR Throughput** | Merged PRs per week, bots excluded | §9.4 |
| **PR Size** | Median lines changed per merged PR; red above `LARGE_PR_THRESHOLD` | §9.5 |
| **Review Coverage** | % of merged PRs with at least one non-author review | §9.6 |
| **Time to First Review** | Median hours, PR open → first non-author review | §9.7 |

Plus a repository breakdown table showing all of the above per repo. Org Overview is the only
page in v0; Team / Metric / Contributor detail pages are tracked in [`BACKLOG.md`](BACKLOG.md).

## Three ways to deploy

### Path A — Vercel + Railway + Supabase (the live demo path)

For developers who already use these platforms. Three managed services, no servers to operate.

1. Fork this repo on GitHub.
2. Provision a [Supabase](https://supabase.com) project (free tier is fine for demos). Copy
   the **Transaction pooler** connection string from Project Settings → Database.
3. [Deploy backend to Railway](https://railway.app/new). Point it at your fork. Set env vars:
   - `DATABASE_URL` — the Supabase pooler URL with `?sslmode=require`. Use the
     `postgresql+psycopg://` scheme.
   - `GITHUB_TOKEN` — a GitHub PAT with `read:org` and `repo` scopes.
   - `GITHUB_ORG` — the org slug (e.g. `astral-sh`).
   - `BACKFILL_MONTHS=3`
   - `CORS_ORIGINS` — your Vercel URL once it exists.
   - `ADMIN_PASSWORD` — optional. If set, the dashboard requires this password to view.
4. [Deploy frontend to Vercel](https://vercel.com/new) pointing at your fork, root directory
   `frontend`. Set `VITE_API_URL` to the Railway backend URL.
5. Open the Vercel URL. First sync runs automatically; takes 2–10 min depending on org size.

**Cost at corporate scale (500 repos):** ~$30/mo total (Supabase Pro $25 + Railway Hobby $5 +
Vercel Hobby free). Free tier across all three works for demos.

### Path B — Docker Compose on any host

For users who want a single host with no managed services.

```bash
git clone https://github.com/pauljmillar/epd
cd epd
cp .env.example .env
# Edit .env: set GITHUB_TOKEN and GITHUB_ORG
docker compose up -d
open http://localhost:3000
```

Bundled Postgres 16, single command, runs on a $10/month VPS or your laptop.

### Path C — Local dev (no Docker, no Postgres)

For working on the code.

```bash
# Backend
cd backend
uv sync
export DATABASE_URL="<your Supabase pooler URL with ?sslmode=require>"
export GITHUB_TOKEN=ghp_xxx
export GITHUB_ORG=astral-sh
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (another terminal)
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Demo recipe (no PR history of your own)

If your own GitHub account doesn't have PRs to show:

```env
GITHUB_TOKEN=ghp_xxxx
GITHUB_ORG=astral-sh         # uv, ruff, rye, etc. — lots of PR activity at manageable scale
BACKFILL_MONTHS=3
```

Other good demo orgs: `pola-rs`, `denoland`, `vercel` (set `EXCLUDED_REPOS=next.js` —
that repo alone has thousands of PRs).

## What EPD does NOT do

- **No individual scoring or rankings.** Per BRD §10, EPD does not produce composite
  productivity scores. Individual metrics are shown as context, never as performance review
  inputs.
- **No external integrations required.** No Jira/Linear, no PagerDuty, no Slack, no HRIS.
- **No MTTR or Change Failure Rate** — these require incident data we don't ingest.
- **Not a SaaS.** Self-hosted only.

## Configuration

See [`.env.example`](.env.example). Every opinionated default is overridable via env var:

| Variable | Default | Purpose |
|---|---|---|
| `BACKFILL_MONTHS` | `3` | Initial history depth |
| `EXCLUDED_REPOS` | (none) | Comma-separated repo names or full names to ignore |
| `EXCLUDED_USERS` | bot patterns | Comma-separated logins to exclude from PR metrics |
| `DEPLOYMENT_BRANCH` | `main` | Merges here count as deployments |
| `DEPLOYMENT_TAG_PATTERN` | (none) | If set, tag matches override the branch signal |
| `LARGE_PR_THRESHOLD` | `400` | Median PR size over this lights up red |
| `ADMIN_PASSWORD` | (none) | If set, dashboard requires bearer-token auth |
| `CORS_ORIGINS` | localhost | Comma-separated allowed frontend origins |

## Architecture

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + APScheduler (in-process, no Celery/Redis)
- **Frontend:** React 18 + TypeScript + Vite + Tailwind + Tremor + Recharts
- **Database:** PostgreSQL 16
- **GitHub API:** GraphQL for PRs + reviews + first-commit in one round trip; REST for repo
  listings and tag-based deployments
- **Snapshots:** per-contributor-per-month rows; prior months are finalized on the 1st and
  never recalculated
- **Response cache:** 5-min in-process TTL on `/api/v1/metrics/org`, invalidated after each
  successful sync

## Roadmap

See [`BACKLOG.md`](BACKLOG.md) for the prioritized roadmap. Highlights coming next:

- AI-tool attribution (detect Claude / Cursor / Copilot / Codex via commit trailers)
- Team / Metric / Contributor drill-down pages
- Manual team grouping
- GitLab collector

## Development

```bash
cd backend && uv run pytest -q       # 28 tests
cd frontend && npm run typecheck     # type check
cd frontend && npm run build         # production build
```

CI runs all of the above plus `docker compose build`.

## License

MIT — see [LICENSE](LICENSE).
