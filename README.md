# EPD — Engineering Productivity Dashboard

A self-hosted, open-source engineering productivity dashboard for VPs of Engineering.
Connects to GitHub and/or GitLab, derives accurate metrics from PR/commit data alone, and
renders a clean, executive-ready view.

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
   - **GitHub** (optional): `GITHUB_TOKEN` (PAT with `read:org` + `repo`) + `GITHUB_ORG`.
   - **GitLab** (optional): `GITLAB_TOKEN` (PAT with `read_api` + `read_repository`) +
     `GITLAB_GROUP`. At least one of GitHub or GitLab must be configured; both can be set
     and the dashboard merges them.
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

## Managing sources from the UI

Once the dashboard is up and you've logged in, **Sources** (bottom of the sidebar) is the
canonical place to add or remove orgs/groups. You can:

- Add a new GitHub org or GitLab group (paste a PAT, click Add, click Sync).
- **Soft-remove** a source: its repos disappear from the dashboard but stay in the DB
  in case you change your mind.
- **Purge** a source: hard-deletes every PR, review, commit, deployment, and snapshot
  tied to it. Irreversible.
- Rotate the token for an existing source.
- Trigger a one-off sync for a single source (rather than waiting for the nightly job).

Env-var credentials (`GITHUB_TOKEN`/`GITHUB_ORG`, `GITLAB_TOKEN`/`GITLAB_GROUP`) still
work — on first boot, EPD seeds matching rows into the `data_sources` table from those
vars. After the first run, the DB is the source of truth and env-var changes are ignored.

## Security model

- `ADMIN_PASSWORD` (env var, **strongly recommended** in production) gates every
  `/api/v1/*` route except `/health`. Anyone with the password can read/write source
  credentials via the API. Set it before exposing the dashboard publicly.
- Source PATs are stored **plain-text** in the `data_sources.token` column. Lock down DB
  access (Supabase does this for you by default). Token rotation is a single API call.
- `SECRET_KEY` (env var) is reserved for session signing; it's not yet used to encrypt
  tokens at rest — that's a planned upgrade.

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

## GitLab limitations (vs GitHub)

GitLab support is best-effort and a step behind GitHub in a few specific areas. The cause
is GitLab's REST API surface, not a deliberate feature gate:

- **PR Size (lines changed)**: GitLab's MR detail endpoint populates `additions` /
  `deletions` only on recent versions of GitLab.com. Older self-hosted instances may
  return 0. Repos showing `0 L` here are likely affected.
- **AI-tool attribution via merge commit body**: GitLab requires a separate `/commits/{sha}`
  call to fetch the merge-commit message body. v1 reads only the MR description for AI
  attribution; signals appearing only in the merge commit will be missed for GitLab.
- **Review state**: GitLab's free tier doesn't expose formal approvals. We treat any
  non-system, non-author note as a "review event" (state COMMENTED). Notes containing
  "lgtm" or "approved" are upgraded to APPROVED. Same treatment of cycle-time pickup as
  GitHub.
- **Sub-groups**: `GITLAB_GROUP=parent/child` works. Project discovery uses
  `include_subgroups=true` so a top-level group sees everything.

## Roadmap

See [`BACKLOG.md`](BACKLOG.md) for the prioritized roadmap.

## Development

```bash
cd backend && uv run pytest -q       # 28 tests
cd frontend && npm run typecheck     # type check
cd frontend && npm run build         # production build
```

CI runs all of the above plus `docker compose build`.

## License

MIT — see [LICENSE](LICENSE).
