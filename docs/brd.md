# Business Requirements Document

# Engineering Productivity Dashboard (EPD)

**Version:** 1.0  
**Date:** June 2026  
**Status:** Draft for Implementation  
**Target Reader:** Claude Code (implementer)

---

## 1\. Executive Summary

EPD is a self-hosted, open-source engineering productivity dashboard that connects to GitHub and/or GitLab and gives VPs of Engineering accurate, at-a-glance visibility into team health and delivery performance. It is designed to be dropped into any organization with minimal configuration — a `.env` file and `docker compose up` is the target setup experience.

The design philosophy is accuracy over breadth. EPD tracks a small set of metrics that are reliably calculable from git and PR data alone, rather than a large set that requires external integrations (CI/CD pipelines, incident trackers, HRIS) that many teams don't have or won't configure.

### Why build this?

The market leaders — LinearB ($420–549/contributor/year), DX (Atlassian-acquired, enterprise-only), and Jellyfish (undisclosed enterprise pricing) — are expensive SaaS tools that require many integrations to unlock value. Google's Four Keys project, the main open-source alternative, was archived in January 2024\. Apache DevLake and Middleware exist but are complex to operate. There is no well-maintained, minimal, self-hosted option.

---

## 2\. Goals and Non-Goals

### Goals

- Zero-to-dashboard in under 15 minutes with a GitHub or GitLab PAT and an org/group name  
- Accurate metrics derived exclusively from git \+ PR/MR data  
- VPE-level views: org roll-up → team breakdown → individual contributor context  
- Monthly pre-calculated snapshots that never need recalculation; quarterly and YTD are roll-ups  
- Open-source and configurable for organizations of different sizes and workflows

### Non-Goals

- Does not require CI/CD integration (optional in Phase 2\)  
- Does not require Jira, Linear, or any issue tracker  
- Does not require HRIS or calendar data  
- Does not calculate MTTR (requires incident data not present in git)  
- Does not score or rank individual engineers (metrics are context, not performance reviews)  
- Is not a SaaS product; there is no hosted version

---

## 3\. Competitive Context

| Tool | Price | Deployment | Requires |
| :---- | :---- | :---- | :---- |
| LinearB | $420–549/user/yr | SaaS | GitHub \+ Jira |
| DX (Atlassian) | Enterprise | SaaS | Many integrations \+ surveys |
| Jellyfish | Enterprise | SaaS | GitHub/GitLab \+ HRIS \+ Finance |
| Apache DevLake | Free | Self-hosted | Complex config, many plugins |
| Middleware | Free | Self-hosted | Focused only on DORA 4 |
| **EPD** | **Free** | **Self-hosted** | **PAT \+ org/group name** |

Key differentiator: EPD is the only self-hosted tool that works out-of-the-box from a single credential, produces accurate metrics, and presents them in a clean executive dashboard.

---

## 4\. Primary Audience

**VP of Engineering / Head of Engineering** (primary)

- Wants org-level health trends, not individual scorecards  
- Cares about delivery throughput, review health, and team bottlenecks  
- Shares dashboard with executive leadership; needs clean, presentation-ready views

**Engineering Managers** (secondary)

- Team-level drill-down to identify specific bottlenecks  
- Compare teams to org baseline

**Individual Contributors** (tertiary, read-only)

- Can see their own contribution context  
- Must never feel the tool is being used for surveillance or performance review

---

## 5\. Deployment Architecture

### Runtime

- **Backend:** Python 3.12 \+ FastAPI  
- **Frontend:** React 18 \+ TypeScript \+ Vite  
- **Database:** PostgreSQL 16  
- **Job runner:** APScheduler (embedded in backend process; no Celery/Redis required)  
- **Container:** Docker Compose (single `docker-compose.yml`)

### Deployment target

A single `docker compose up -d` command starts three containers: `db`, `backend`, `frontend`. The frontend proxies API calls to the backend. No ingress controller, no Kubernetes, no load balancer.

### Minimum hardware

2 vCPUs, 2 GB RAM, 10 GB disk. Works on a $10/month VPS or a developer laptop.

---

## 6\. Configuration

All configuration is via environment variables in a `.env` file. There is no database-stored configuration in v1.

### Required variables

\# Source control (at least one required)

GITHUB\_TOKEN=ghp\_xxxx              \# GitHub PAT with read:org, repo scopes

GITHUB\_ORG=my-org                  \# GitHub organization slug

GITLAB\_TOKEN=glpat-xxxx            \# GitLab PAT with read\_api scope

GITLAB\_GROUP=my-group              \# GitLab top-level group

\# App

SECRET\_KEY=change-me               \# Used to sign session tokens

DATABASE\_URL=postgresql://...      \# Auto-populated in docker-compose

### Optional variables

\# Data collection

BACKFILL\_MONTHS=6                  \# How many months of history to load on first run (default: 6\)

EXCLUDED\_REPOS=repo1,repo2         \# Comma-separated repos to ignore

EXCLUDED\_USERS=bot1,dependabot\[bot\] \# Comma-separated authors to exclude from metrics

DEPLOYMENT\_BRANCH=main             \# Branch whose merges count as deployments (default: main)

DEPLOYMENT\_TAG\_PATTERN=v\*.\*.\*      \# Regex for deployment tags (overrides branch if set)

\# Auth (optional; if not set, no login required — appropriate for internal networks)

ADMIN\_PASSWORD=changeme            \# If set, enables simple password protection

### Setup experience (target)

git clone https://github.com/yourorg/epd

cd epd

cp .env.example .env

\# Edit .env: add GITHUB\_TOKEN and GITHUB\_ORG

docker compose up \-d

\# Open http://localhost:3000

\# Initial backfill runs automatically and takes 2–10 minutes depending on repo size

---

## 7\. Data Collection Strategy

### Source of truth

GitHub REST API v3 and GraphQL API v4 for GitHub; GitLab REST API v4 for GitLab. Both are accessed via PAT. A GitHub App credential can be used in place of a PAT for higher rate limits — this is an optional configuration, not required.

### What is collected

For each repository, EPD collects:

- All merged pull requests / merge requests (including all reviews, comments, commits, and timeline events)  
- Repository metadata (name, default branch, topics)  
- User/contributor metadata (login, display name, teams/groups if accessible)  
- Tags matching `DEPLOYMENT_TAG_PATTERN` if configured

EPD does **not** collect: issue content, commit message content beyond timestamps, file diffs beyond line-count stats, or any data from CI/CD pipelines, Jira, Slack, or other external tools.

### Rate limit handling

GitHub GraphQL API: 5,000 points/hour (PAT), up to 15,000 points/hour (GitHub App). GitLab REST API: 2,000 requests/minute authenticated.

EPD uses cursor-based pagination, batches queries to minimize round trips, and includes exponential backoff. The nightly incremental sync only fetches PRs updated since the last run, so steady-state API consumption is minimal.

### Storage model

Raw PR/review/commit events are stored in PostgreSQL in a normalized schema. Metric snapshots are calculated from raw data and stored separately. Raw data is retained for the configured backfill window; snapshot data is retained indefinitely.

---

## 8\. Metric Calculation

### Design principles

1. **Immutable monthly snapshots.** On the 1st of each month, the previous month's snapshots are finalized and never recalculated. This makes the system cheap to operate and the data stable for trend analysis.  
2. **Rolling current-month calculation.** The current (incomplete) month's metrics are recalculated nightly from raw data.  
3. **Roll-up arithmetic.** Quarterly \= sum of 3 monthly snapshots (for counts) or average (for latency medians). Team \= aggregate of member snapshots. Org \= aggregate of all team snapshots.  
4. **Per-entity snapshots.** Snapshots are stored at the individual contributor \+ month grain. Everything else is a derived roll-up.

### Snapshot schema (conceptual)

contributor\_month\_snapshot:

  \- user\_id

  \- repo\_id (nullable; NULL \= all repos for that user)

  \- year\_month (e.g., 2026-05)

  \- prs\_merged

  \- prs\_reviewed (distinct PRs reviewed by this user)

  \- median\_pr\_cycle\_time\_hours

  \- median\_time\_to\_first\_review\_hours  (for PRs authored by this user)

  \- median\_pickup\_time\_hours           (for PRs where this user was reviewer)

  \- median\_pr\_size\_lines

  \- review\_coverage\_pct                (% of this user's PRs that had \>= 1 review)

  \- deployment\_count                   (if user's PRs were the deployment trigger)

  \- lead\_time\_p50\_hours                (median first commit to merge)

  \- lead\_time\_p75\_hours

  \- is\_finalized                       (false until month closes)

---

## 9\. Core Metrics

These are the **v1 metrics** — all derivable from PR/commit data alone, all accurate without external integrations.

### 9.1 Deployment Frequency

**Definition:** Number of deployments per week (or per day for high-frequency teams), trended over time.

**Calculation:** EPD identifies deployments via one of two configurable signals, in priority order:

1. Tags matching `DEPLOYMENT_TAG_PATTERN` (e.g., `v*.*.*`) — most accurate  
2. Merges to `DEPLOYMENT_BRANCH` (e.g., `main`) — good proxy if no tag discipline

Deployments are counted per calendar week and displayed as a trend line. The DORA classification thresholds (Elite: multiple per day; High: daily; Medium: weekly; Low: monthly) are shown as reference bands.

**Why it's accurate:** Deployment events are discrete, timestamped, and unambiguous once the signal is configured. The only setup required is deciding which signal to use.

**Limitation:** If the team has no tag discipline and merges to main don't represent deployments (e.g., a mono-repo with per-service deploy pipelines), this metric will overcount. The configuration documentation must make this clear.

---

### 9.2 Lead Time for Changes

**Definition:** Median time from the first commit in a PR to the PR being merged. Measured in hours, trended by week/month.

**Calculation:** For each merged PR, find the earliest commit timestamp associated with that PR. Lead time \= merge timestamp − earliest commit timestamp. Take the P50 (median) and P75 per team per week.

**Why it's more accurate than PR open time:** Developers often create a branch and commit days before opening the PR. Using PR open time systematically undercounts true lead time. Using first commit time is the standard approach taken by GitLab's native DORA implementation.

**Limitation:** GitHub's API does not always return the full commit history for a PR if the branch has been rebased or the commits squashed. EPD handles this gracefully by falling back to PR open time if no commits are found, and flagging the metric as "estimated" in the UI.

---

### 9.3 PR Cycle Time (with breakdown)

**Definition:** Total time from PR open to PR merge, broken into three phases:

- **Pickup time:** PR opened → first review event (first comment, approve, or request-changes)  
- **Review time:** First review event → last approval  
- **Merge time:** Last approval → merge

Reported as medians per person per month, and as team medians.

**Why it matters:** Cycle time breakdown pinpoints where delays live. A long pickup time means reviewers are unavailable or PRs aren't being assigned. A long review time means back-and-forth or complex PRs. A long merge time (post-approval) is often a process or tooling issue.

**Calculation:** GitHub and GitLab timeline events provide the timestamps needed for each phase transition. For PRs with no reviews (merged without review), pickup time and review time are both 0, and merge time \= open-to-merge.

---

### 9.4 PR Throughput

**Definition:** Number of PRs merged per engineer per week, trended over time.

**Calculation:** Count of merged PRs per author per calendar week, across all tracked repos. Exclude bots (configured via `EXCLUDED_USERS`). Report team total and per-engineer breakdown.

**Why it matters for VPE:** Throughput trends reveal whether teams are shipping consistently or have high variance. Cross-team comparison identifies outliers worth investigating. Do not present this as a performance score — the UI should always show throughput alongside PR size and cycle time so context is visible.

---

### 9.5 PR Size

**Definition:** Median lines changed (additions \+ deletions) per PR, per author per month.

**Calculation:** GitHub and GitLab APIs return additions and deletions per PR. Store both; display sum as "lines changed." Exclude auto-generated files (e.g., lockfiles, generated protobuf) if file patterns are configured.

**Why it matters:** Large PRs correlate with longer review times, higher defect rates, and review fatigue. Trending PR size over time shows whether a team is adopting smaller-PR practices. Flagging PRs over a configurable threshold (default: 400 lines) gives teams actionable data.

**Configurable:**

LARGE\_PR\_THRESHOLD=400    \# Lines changed; default 400

---

### 9.6 Review Coverage

**Definition:** Percentage of merged PRs that received at least one review (non-author review event) before merge.

**Calculation:** For each merged PR, check whether any review event exists from a user other than the PR author. Count reviewed PRs / total PRs. Report per team per month.

**Why it matters:** Review coverage below \~85% is a quality signal. Very low coverage (\< 50%) often indicates a team is shipping under time pressure or has a weak review culture. This is a directional metric, not a precise quality measure.

---

### 9.7 Time to First Review

**Definition:** Median time (hours) between a PR being opened and the first review event from any non-author reviewer.

**Calculation:** For each merged PR with at least one review, time\_to\_first\_review \= first\_review\_timestamp − pr\_opened\_timestamp. Report as team median per week.

**Why it matters:** This is the strongest signal of reviewer availability and team responsiveness. Long pickup times often mean reviewers are context-switching, the PR isn't being assigned, or the team doesn't have a defined review SLA.

---

## 10\. Intentionally Excluded Metrics

The following metrics are **not included in v1** for the reasons stated. They are documented here so the decision is explicit and not relitigated.

| Metric | Reason excluded |
| :---- | :---- |
| MTTR (Mean Time to Restore) | Requires incident data (PagerDuty, OpsGenie, etc.) not present in git |
| Change Failure Rate | Requires reliable incident-to-deployment linkage; proxy signals (revert commits, rollback tags) produce too many false positives |
| Code Churn | Calculable but expensive; requires comparing commit diffs over a rolling window; adds significant API cost and complexity for marginal signal |
| Test Coverage | Requires CI artifact data, not present in git |
| Bug Escape Rate | Requires issue tracker with label discipline |
| Sprint Velocity | Requires issue tracker with story points |
| Individual productivity scores | Philosophically opposed; EPD does not produce composite scores |

**Phase 2 candidates:** Change Failure Rate (with explicit rollback tag convention), Code Churn, optional CI/CD integration for deployment signal.

---

## 11\. Relation to GitLab's Built-In Dashboard

GitLab offers a **Value Streams Dashboard** (Premium/Ultimate tier only) that covers DORA metrics, VSA flow metrics, vulnerabilities, and AI/Duo usage. It is well-designed — sparkline trend columns, MoM change %, DORA Performers score bar chart, and sortable project tables — and EPD deliberately draws on its best ideas.

EPD differs in four important ways:

1. **It works on free tiers.** GitLab's dashboard requires Premium or Ultimate. EPD requires only a PAT.  
2. **It requires no CI/CD.** GitLab's DORA metrics require production deployment environments configured in CI/CD pipelines and issues cross-linked from commits. EPD derives what it can from PR/MR data alone.  
3. **It works on GitHub too.** GitLab's dashboard is GitLab-only.  
4. **It presents the VPE view.** GitLab's dashboard is project/group-scoped. EPD is org-scoped with a team drill-down model designed for engineering leadership.

When an organization already has GitLab Premium/Ultimate, EPD provides a complementary cross-platform view and a more opinionated VPE-first layout.

---

## 12\. UI Design

### Design philosophy

Strictly black, white, and gray. No color except red for genuinely bad states (threshold breaches, sync failures). The aesthetic target is [Linear.app](https://linear.app) and [Vercel's dashboard](https://vercel.com) — information-dense but visually quiet. Every pixel of color must earn its place.

The interface is desktop-only in v1 (minimum viewport: 1280px). No mobile responsive required.

Component library: **Tremor v3** (open-source post-Vercel acquisition) for layout primitives, cards, and tables. **Recharts** for all charts. No other UI or charting libraries.

---

### Color system

Background page:    \#F9F9F9

Background card:    \#FFFFFF

Border default:     \#E5E5E5

Border subtle:      \#F0F0F0

Text primary:       \#111111

Text secondary:     \#666666

Text tertiary:      \#999999

Chart line primary: \#111111   (solid, 2px)

Chart line secondary: \#AAAAAA (dashed, 1.5px — used for P75 or prior-period comparison)

Chart area fill:    \#F5F5F5   (very light gray, used sparingly for area charts)

Chart grid lines:   \#F0F0F0

Chart axis labels:  \#999999

Positive delta:     \#111111 with ↑ arrow — no green

Negative delta / alert: \#CC0000 with ↓ arrow — only when metric crosses a bad threshold

Neutral delta:      \#666666 with → arrow

Sidebar background: \#FFFFFF

Sidebar border:     \#E5E5E5

Active sidebar item background: \#F0F0F0

---

### Typography

Single font family: **Inter** (system fallback: \-apple-system, BlinkMacSystemFont, sans-serif).

Stat number (KPI card):     32px, weight 600, \#111111

Stat label:                 11px, weight 500, \#666666, letter-spacing 0.05em, uppercase

Delta text:                 13px, weight 500

Card title:                 13px, weight 500, \#111111

Table header:               11px, weight 600, \#999999, uppercase, letter-spacing 0.05em

Table cell primary:         14px, weight 400, \#111111

Table cell secondary:       12px, weight 400, \#666666

Section heading:            16px, weight 600, \#111111

Page title:                 20px, weight 600, \#111111

Chart axis:                 11px, \#999999

Tooltip:                    12px, \#111111 on \#FFFFFF, 1px border \#E5E5E5, 4px shadow

---

### Global chrome

┌──────────────────────────────────────────────────────────┐

│ SIDEBAR (220px)      │ MAIN CONTENT (fills remainder)    │

│                      │                                   │

│ \[EPD\]                │ \[Page Title\]    \[Period Selector\] │

│                      │ ─────────────────────────────────│

│ Overview             │                                   │

│                      │  (page content)                   │

│ TEAMS                │                                   │

│  ↳ Platform          │                                   │

│  ↳ Growth            │                                   │

│  ↳ Data              │                                   │

│                      │                                   │

│ Contributors         │                                   │

│ ──────────────       │                                   │

│ Settings             │                                   │

│ Sync: 2h ago ●       │                                   │

└──────────────────────────────────────────────────────────┘

**Sidebar details:**

- 220px fixed width, `#FFFFFF` background, 1px right border `#E5E5E5`  
- "EPD" wordmark at top-left (16px, weight 700, \#111111), with configurable `APP_NAME` env var  
- "TEAMS" section header: 10px, weight 600, \#999999, uppercase  
- Team names listed below, each a clickable nav item  
- Active item: `#F0F0F0` background, left border 2px `#111111`  
- Sync status at bottom: "Synced 2h ago" with a gray dot (●), turns red if last sync failed or is \> 25 hours ago  
- No icons — text-only navigation in v1

**Main content area:**

- Background `#F9F9F9`  
- 32px padding on all sides  
- Page title left-aligned, period selector right-aligned, same horizontal row  
- Content below a 1px `#E5E5E5` divider

**Period selector:**

- Segmented control: `Last 30d` | `Last 90d` (default) | `Last 6m` | `Custom`  
- Custom triggers a date-range picker (start/end date, calendar popover)  
- Selected state: dark background (`#111111`), white text; unselected: white background, `#666666` text

---

### Visualization type reference

| Metric | Primary display | In KPI card | In detail page |
| :---- | :---- | :---- | :---- |
| Deployment Frequency | Line chart (weekly, 90d) | deployments/week \+ sparkline | Full trend \+ DORA band annotations |
| Lead Time P50 | Line chart (weekly, dual lines) | hours or days \+ sparkline | P50 \+ P75 lines, 90d–12m range |
| PR Cycle Time | Stacked bar (breakdown phases) | total hours \+ sparkline | Breakdown bars \+ phase table |
| PR Throughput | Line chart (weekly) | PRs/week \+ sparkline | Trend \+ contributor table |
| PR Size | Histogram (distribution) | median lines \+ sparkline | Distribution histogram \+ large-PR flag |
| Review Coverage | Line chart (weekly %) | % \+ sparkline | Trend \+ team/contributor table |
| Time to First Review | Line chart (weekly) | hours \+ sparkline | Trend \+ team breakdown |

**Sparklines** inside KPI cards are 60×20px, no axes, no labels, single gray line, drawn from the prior 8 weeks of weekly data.

---

### KPI stat card spec

Every KPI metric renders as a card. Six cards appear on the Org Overview and Team Detail pages, displayed in a 3-column × 2-row grid (or 6-across on wide viewports ≥ 1600px).

┌─────────────────────────────┐

│ METRIC NAME            \[?\]  │  ← label (uppercase, 11px, gray) \+ tooltip icon

│                             │

│  4.2d                       │  ← stat value (32px, bold, black)

│                             │

│  ↑ \+12% vs prior 30d        │  ← delta line (13px; black arrow/text normally,

│                \[sparkline\]  │    red if metric is in a "bad" direction)

└─────────────────────────────┘

**Delta direction logic** (metric-aware — "up" is not always good):

| Metric | Bad direction (shows red ↓) |
| :---- | :---- |
| Lead Time | Increasing |
| PR Cycle Time | Increasing |
| Time to First Review | Increasing |
| Review Coverage | Decreasing |
| Deployment Frequency | Decreasing |
| PR Throughput | No automatic red (context-dependent; shown in black always) |
| PR Size | Increasing above threshold (red when median \> `LARGE_PR_THRESHOLD`) |

**Card is fully clickable** → navigates to the metric's dedicated detail page.

Tooltip (shown on `[?]` hover): one-sentence definition of the metric \+ "How it's calculated" link to docs.

---

### Org Overview page layout

\[EPD\]                               \[Overview\]         \[Last 30d | Last 90d ● | Last 6m | Custom\]

──────────────────────────────────────────────────────────────────────────────────────────────────

┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐

│Deploy Freq│ │Lead Time │ │Cycle Time│ │Throughput│ │Review    │ │Time to   │

│          │ │          │ │          │ │          │ │Coverage  │ │1st Review│

│  3.1/wk  │ │  2.8d    │ │  18h     │ │  4.2/wk  │ │  91%     │ │  6.2h    │

│↑+8%      │ │↓+15% \[\!\] │ │→ flat    │ │↑+5%      │ │→ \-1%     │ │↓+22% \[\!\] │

└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘

┌────────────────────────────────────┐  ┌────────────────────────────────────┐

│ Deployment Frequency (weekly)      │  │ Lead Time for Changes (weekly)     │

│                                    │  │                                    │

│  \[line chart, 90d, with            │  │  \[dual-line chart: P50 solid,      │

│   faint DORA band labels on        │  │   P75 dashed gray; 90d window;     │

│   right y-axis: Elite / High /     │  │   y-axis in hours or days          │

│   Medium / Low\]                    │  │   depending on scale\]              │

└────────────────────────────────────┘  └────────────────────────────────────┘

Team comparison                                                  \[Sort ▼\]

──────────────────────────────────────────────────────────────────────────────

Team          Deploy Freq  Lead Time   Cycle Time  Throughput  Coverage  1st Review

Platform      3.8/wk       1.9d        14h         5.1/wk      96%       4.1h

              ↑+5%         → flat      ↑+8%\[\!\]     ↑+12%       ↑+1%      → flat

              \[spark\]      \[spark\]     \[spark\]     \[spark\]     \[spark\]   \[spark\]

Growth        2.1/wk       4.2d\[\!\]     24h\[\!\]      3.6/wk      84%\[\!\]    9.8h\[\!\]

              → flat       ↓+20%\[\!\]    ↓+10%\[\!\]    ↓-8%        ↓-6%\[\!\]  ↑+31%\[\!\]

              \[spark\]      \[spark\]     \[spark\]     \[spark\]     \[spark\]   \[spark\]

──────────────────────────────────────────────────────────────────────────────

Org median    3.1/wk       2.8d        18h         4.2/wk      91%       6.2h

**Table details:**

- Each team name is a clickable link → Team Detail page  
- Each cell shows: metric value (14px, black) \+ delta vs prior period (12px, below, black or red) \+ 8-week sparkline (40×14px)  
- `[!]` in the mockup above \= red text; shown when the delta crosses a bad threshold or the absolute value is below an alert threshold (configurable)  
- "Org median" pinned row at the bottom of the table  
- Table is sortable by any column header click; default sort \= team name alphabetical  
- No row color backgrounds — the red deltas are the only color signal

---

### Team Detail page layout

Accessible via sidebar team link or clicking a team name in the comparison table.

Breadcrumb at top: `Overview › Platform`

Layout is identical to Org Overview above, scoped to one team, with two additions:

**1\. Cycle time phase breakdown chart** (below the two line charts):

┌─────────────────────────────────────────────────────────────┐

│ Cycle Time Breakdown — by week                              │

│                                                             │

│  \[Horizontal stacked bar chart, one bar per week\]           │

│  Segments: Pickup time | Review time | Merge time           │

│  Colors: 3 shades of gray (dark / medium / light)          │

│  Hover: tooltip shows exact hours for each phase            │

│  Legend below chart: ■ Pickup  ■ Review  ■ Merge           │

└─────────────────────────────────────────────────────────────┘

**2\. Contributor context table** (below cycle time chart):

Contributor context — Platform team                       \[i This view is for context, not evaluation\]

────────────────────────────────────────────────────────────────────────────────────────────

Contributor    PRs merged  Lead Time   Cycle Time  PR Size  Coverage  1st Review

alice          18          2.1d        12h         210 L    100%      3.8h

               \[spark\]     \[spark\]     \[spark\]     \[spark\]  \[spark\]   \[spark\]

bob            12          3.4d        22h         480 L\[\!\] 92%       8.2h

               \[spark\]     \[spark\]     \[spark\]     \[spark\]  \[spark\]   \[spark\]

Team median    15          2.8d        18h         310 L    96%       6.2h

────────────────────────────────────────────────────────────────────────────────────────────

- Contributor names are clickable → Individual Contributor page  
- Red `[!]` only for absolute threshold breaches (PR size \> `LARGE_PR_THRESHOLD`; first-review \> configurable alert threshold). Never red for being below team median.  
- `[i]` icon expands to: *"Individual metrics are context, not performance scores. Differences reflect team structure, project complexity, and seniority — not individual worth."*

---

### Metric Detail page layout

Accessible by clicking any KPI stat card.

← Back          Lead Time for Changes                                \[Last 90d ▼\]

──────────────────────────────────────────────────────────────────────────────────────

Definition: Median time from first commit in a PR to merge. \[How it's calculated ↗\]

Current: 2.8d  |  Prior 30d: 2.4d  |  Change: ↑ \+17% \[\!\]  |  P75: 4.1d

┌─────────────────────────────────────────────────────────────────────────────────┐

│ \[Full-width line chart\]                                                         │

│  • X-axis: weeks (default 90d; range selector below: 30d | 90d | 6m | 12m)    │

│  • Two lines: P50 (solid black, 2px) and P75 (dashed gray, 1.5px)             │

│  • Hover: vertical crosshair; tooltip shows week, P50 value, P75 value         │

│  • DORA reference lines: faint horizontal dashed lines at 1d and 7d cutoffs   │

│    with small right-aligned labels: "High performer" / "Medium"                │

└─────────────────────────────────────────────────────────────────────────────────┘

Team breakdown — last 30d                            \[Sort by: Lead Time P50 ▼\]

────────────────────────────────────────────────────────────────

Team          P50        P75        MoM change    Trend (8wk)

Platform      1.9d       3.1d       → flat        \[sparkline\]

Growth        4.2d       7.8d       ↓ \+20% \[\!\]    \[sparkline\]

Data          2.3d       3.8d       ↑ \-8%         \[sparkline\]

Org median    2.8d       4.1d       ↑ \+17% \[\!\]    \[sparkline\]

────────────────────────────────────────────────────────────────

Notable PRs — longest lead times this period

────────────────────────────────────────────────────────────────

PR                                Repo        Author    Lead Time

\[\#1204\] Refactor auth middleware   platform    alice     18.2d

\[\#892\]  Add payment webhooks       growth      bob       14.6d

\[\#1301\] Migrate to new ORM         data        carol     12.1d

────────────────────────────────────────────────────────────────

PR titles are clickable links to the source PR in GitHub/GitLab.

---

### Individual Contributor page layout

Accessible via contributor table in Team Detail page.

← Platform      alice                                           \[Last 90d ▼\]

──────────────────────────────────────────────────────────────────────────────────

┌──────────────────────────────────────────────────────────────────────────────┐

│  ⓘ  This view is for context, not evaluation. Metrics reflect project        │

│     complexity and team structure as much as individual contribution.        │

└──────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────┐  ┌────────────────────────────────────┐

│ PRs merged: 18    Team median: 15  │  │ Cycle Time trend — alice vs team   │

│ Lead Time:  2.1d  Team: 2.8d       │  │                                    │

│ Cycle Time: 12h   Team: 18h        │  │  \[Line chart: alice (solid black)  │

│ PR Size:    210L  Team: 310L       │  │   vs team median (dashed gray)\]    │

│ Coverage:   100%  Team: 96%        │  │                                    │

│ 1st Review: 3.8h  Team: 6.2h      │  └────────────────────────────────────┘

└────────────────────────────────────┘

Recent PRs — last 30d

────────────────────────────────────────────────────────────────────────────

PR                              Merged      Size    Cycle Time  1st Review

\[\#1198\] Fix session expiry       Jun 1       82L     8h          2.1h

\[\#1187\] Add rate limiting        May 28      340L    21h         6.4h

\[\#1175\] Upgrade auth library     May 22      120L    11h         3.2h

────────────────────────────────────────────────────────────────────────────

PR titles link to the source PR. Table shows last 20 PRs; older PRs load on scroll.

---

### Empty and loading states

- **First run (backfill in progress):** Full-page message: *"EPD is syncing your repositories for the first time. This usually takes 5–15 minutes. Check back soon."* with a progress indicator showing repos synced / total.  
- **No data for period:** Card shows "—" instead of a value, no sparkline, no delta.  
- **Partial data (current month):** Subtle indicator below any current-month stats: *"Month in progress — figures update nightly."*  
- **Sync failed:** Sidebar sync indicator turns red with tooltip: *"Last sync failed \[timestamp\]. Check Settings for details."*  
- **Chart loading:** Skeleton placeholder (gray rectangle) fills the chart area while data loads; no spinner overlays on the entire page.

---

### Tooltip standard

Every metric name, wherever it appears (card, table header, chart title), shows a `?` icon on hover that reveals:

┌──────────────────────────────────────────────────┐

│ Time to First Review                             │

│                                                  │

│ Median hours between a PR being opened and the  │

│ first review event from a non-author reviewer.  │

│                                                  │

│ Calculated from: PR timeline events (GitHub /   │

│ GitLab API). Only includes merged PRs.          │

│                                                  │

│ Note: excludes draft PRs and bot reviewers.     │

└──────────────────────────────────────────────────┘

---

### Design constraints (non-negotiable)

- No color except `#CC0000` (red), used exclusively for threshold-breaching metrics and system alerts. No green, no amber, no blue.  
- No metric is displayed without a tooltip. This is enforced: every `<MetricCard>` and `<TableHeader>` component must accept a `definition` prop; failing to pass it is a type error.  
- DORA tier bands (Elite/High/Medium/Low) appear only on Deployment Frequency and Lead Time charts. Not applied to any other metric.  
- Red deltas on contributor rows are limited to absolute threshold breaches (e.g., PR size \> 400L). Never shown because someone is below team median.  
- No data tables longer than 20 rows without pagination.  
- No composite scores, no rankings, no "top performers" lists anywhere in the UI.

---

## 13\. Database Schema (high-level)

\-- Source entities

contributors    (id, login, display\_name, avatar\_url, source \[github|gitlab\])

repositories    (id, name, full\_name, source, default\_branch)

teams           (id, name, source\_team\_id)

team\_members    (team\_id, contributor\_id)

\-- Raw events

pull\_requests   (id, repo\_id, number, author\_id, opened\_at, merged\_at, 

                 closed\_at, additions, deletions, base\_branch, is\_draft)

pr\_reviews      (id, pr\_id, reviewer\_id, submitted\_at, state \[approved|changes\_requested|commented\])

pr\_commits      (id, pr\_id, sha, authored\_at, committed\_at)

deployments     (id, repo\_id, triggered\_at, signal\_type \[tag|branch\_merge\], ref)

\-- Calculated snapshots

contributor\_month\_snapshots  (see Section 8\)

sync\_log        (id, started\_at, completed\_at, repos\_synced, prs\_synced, errors)

---

## 14\. API Design (backend)

All endpoints return JSON. Auth via bearer token derived from `ADMIN_PASSWORD` (if configured); otherwise no auth.

GET /api/v1/health

GET /api/v1/metrics/org?period=30d|90d|6m

GET /api/v1/metrics/team/:team\_id?period=...

GET /api/v1/metrics/contributor/:contributor\_id?period=...

GET /api/v1/teams

GET /api/v1/contributors

GET /api/v1/repos

GET /api/v1/sync/status

POST /api/v1/sync/trigger   (manual trigger; rate-limited to 1/hour)

---

## 15\. Data Sync Schedule

| Job | Schedule | Description |
| :---- | :---- | :---- |
| Incremental sync | Nightly 2am (configurable) | Fetches PRs updated since last sync for all tracked repos |
| Snapshot recalculation | Nightly after sync | Recalculates current month's snapshots for all contributors |
| Month finalization | 1st of each month, 6am | Marks prior month's snapshots as finalized; no further recalculation |
| Initial backfill | On first startup | Fetches `BACKFILL_MONTHS` of PR history; runs once, idempotent |

---

## 16\. Open-Source Considerations

### License

MIT License. All configuration, schema, and code must be fully open.

### Configurability requirements

Every opinionated default must be overridable via environment variable. This includes: deployment signal type, deployment branch, large-PR threshold, excluded repos, excluded users, backfill window, sync schedule.

### Privacy

EPD stores contributor logins and display names from the SCM API. It does not store email addresses, commit message content, or code content. Organizations must ensure their use of EPD complies with applicable employment and privacy law (noted in README, not enforced in code).

### README requirements

The README must include:

- A 3-step quickstart (clone → configure → run)  
- A metric definitions table linking to this BRD  
- An explicit "what EPD does NOT do" section (no scoring, no surveillance, no external integrations required)  
- Docker Compose setup instructions  
- Instructions for using a GitHub App credential instead of PAT (for higher rate limits)  
- A contributing guide

---

## 17\. Out of Scope for v1

- SSO / OAuth login (basic password protection only)  
- Multi-tenant mode (one instance \= one org)  
- Slack or email notifications  
- Exported reports (CSV/PDF)  
- CI/CD integration  
- Issue tracker integration  
- Mobile responsive design (desktop-only in v1; responsive in v2)  
- GitHub App marketplace listing

---

## 18\. Acceptance Criteria

EPD v1 is complete when:

1. `docker compose up -d` with a valid `.env` starts all services and the frontend is accessible at `http://localhost:3000`  
2. Initial backfill completes for an org with 10 repos and 6 months of history in under 15 minutes without hitting GitHub rate limits  
3. All six core metrics render correctly on the Org Overview page for a real GitHub org  
4. Monthly snapshots for closed months are immutable (verified by confirming no DB writes to finalized rows on a nightly run)  
5. Adding a second GitHub org (via a second PAT) or a GitLab group requires only `.env` changes, no code changes  
6. A new user can reach a working dashboard following only the README quickstart, with no prior knowledge of the codebase

---

## 19\. Implementation Notes for Claude Code

- Use `PyGithub` or raw `httpx` async client for GitHub API calls; avoid SDKs that wrap GraphQL in ways that obscure rate limit handling  
- Use `alembic` for database migrations from day one; schema will evolve  
- The frontend should use `Tremor` v3 (fully open-source post-Vercel acquisition) for UI components and `Recharts` for all charts; do not introduce other charting libraries  
- All metric calculation logic must be unit-testable in isolation from the database; use pure functions that accept lists of PR/event dicts and return metric values  
- The sync job must be idempotent — running it twice for the same period must produce the same result  
- Store raw API responses in the `pull_requests` and related tables, not as JSON blobs; this makes metric logic straightforward and debuggable  
- Do not use Celery or Redis in v1; APScheduler running inside the FastAPI process is sufficient for a single-instance deployment

---

*End of BRD v1.0*  
