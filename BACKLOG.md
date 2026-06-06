# EPD Backlog

Roadmap beyond the walking skeleton (v0, shipped). The list is roughly ordered by priority,
but items inside a phase can be done in any order. Items reference the BRD ([`docs/brd.md`](docs/brd.md))
where applicable.

---

## Phase A — Production-credible ✅ DONE

- [x] A1. Suppress bogus % deltas at the backfill horizon — `null` deltas now shown as
      "— no prior data".
- [x] A2. Snapshot builder populates every column from migration 0002. **Read path still
      live-computes;** snapshot reads remain a TODO for the 500-repo perf path.
- [x] A3. 5-min in-process TTL cache on `/metrics/org`, invalidated by sync.
- [x] A4. Optional `ADMIN_PASSWORD` bearer-token auth on `/metrics` and `/sync`.
- [x] A5. README rewrite + Deploy buttons for Vercel/Railway.

**Carried forward (didn't fit Phase A):**

- [ ] **A2-followup. Read snapshots for closed months.** Snapshot table is now populated but
      `/metrics/org` still loads raw PRs every request. At 500-repo scale (~1M rows) this
      should switch: closed months read from `contributor_month_snapshots`, current month does
      live compute. The cache (A3) takes the edge off until then.

---

## Phase B-prep — AI-assisted change attribution ✅ DONE

Shipped. Detection via merge-commit `Co-Authored-By:` trailers + PR body markers for Claude,
Cursor, Copilot, Codex, Windsurf. Tooltip honestly calls out that this is a lower bound.

Possible future improvements (not blocking anything):

- [ ] Expand detection to scan all commit messages in a PR (currently only the merge commit
      body + PR body). Catches merge-commit-style repos.
- [ ] Per-PR tag in a future Contributor detail view ("This PR was AI-assisted with Claude").
- [ ] Tool-vs-no-tool comparison on cycle time / size / coverage. Useful but loaded — handle
      with care so it doesn't become "AI users are faster, fire everyone else."

---

## Phase B — Drill-down pages (BRD §12)

Adds React Router and the three pages specified by the BRD beyond Org Overview.

- [ ] **B1. Routing.** Add `react-router-dom`. Routes:
      `/`, `/teams/:teamName`, `/metrics/:metricKey`, `/contributors/:login`.
- [ ] **B2. Team Detail page.** Mirror of Org Overview scoped to one team, plus cycle-time
      breakdown chart and contributor context table. Reuses existing components.
- [ ] **B3. Metric Detail page.** Full-screen single metric with team breakdown table and
      "notable PRs" list (longest lead times in period, links to GitHub/GitLab PR).
- [ ] **B4. Individual Contributor page.** Per BRD §12: prominent "this view is for context,
      not evaluation" banner. Shows the contributor's stats next to team medians + last 20 PRs.
- [ ] **B5. Sidebar populates with teams.** Replace the static "(auto-populated after first
      sync)" with the actual team list from the API.

---

## Phase B+ — Manual team grouping

Most orgs don't expose GitHub teams to a PAT. Today EPD falls back to "one team per repo,"
which the UI labels honestly. This phase adds true teams managed in EPD itself.

- [ ] **BP1. Schema is already there.** `teams` and `team_members` tables exist (migration 0001).
- [ ] **BP2. Admin UI: list contributors, assign to teams.** Two-pane: contributor list on the
      left, team management on the right. Drag-and-drop or checkbox-based.
- [ ] **BP3. Replace repo-as-team fallback** when at least one EPD-defined team exists.
- [ ] **BP4. Contributor can belong to multiple teams** (engineering managers sit on multiple
      squads). Decide aggregation rule for stats (sum vs avg vs primary team).

---

## Phase C — GitLab collector

EPD's schema is already source-agnostic (`source: github|gitlab` everywhere). This phase adds
the GitLab implementation.

- [ ] **C1. GitLab REST v4 client** in `backend/app/collectors/gitlab.py`. Mirrors the GitHub
      collector's interface (`list_org_repos`, `list_merged_prs`, `list_deployments`).
- [ ] **C2. Merge request → PR mapping.** GitLab uses different terminology, same shape.
- [ ] **C3. Deployments via tags or merges to `default_branch`.** Same logic as GitHub.
- [ ] **C4. Sync orchestrator picks GitHub or GitLab** based on which env vars are set; runs
      both if both configured.
- [ ] **C5. README + `.env.example` updated** for GitLab credentials.

---

## Phase C+ — Admin: repo include/exclude UI

Currently `EXCLUDED_REPOS` is an env var (comma-separated). For 500-repo corporate accounts
this needs to be a real UI.

- [ ] **CP1. DB-backed include/exclude.** `repository.is_tracked: bool` column; defaults to
      include. Env var continues to work as a default for first sync.
- [ ] **CP2. Admin page: "Repositories"** lists every repo discovered in the org with a
      toggle for inclusion. Persists to DB. Re-sync respects the new list.
- [ ] **CP3. Optional: similar for users.** Toggle to exclude specific contributors from
      metrics (e.g., interns whose PRs would skew junior-pool stats; bot accounts not caught
      by the bot-name patterns).

---

## Phase D — OSS polish

- [ ] **D1. README rewrite** post-v1: 7 metrics, live demo URL, architecture diagram,
      one-click deploy buttons.
- [ ] **D2. Architecture diagram** (Mermaid) — sync flow, snapshot lifecycle.
- [ ] **D3. Empty/loading states** per BRD §12: first-run progress indicator, "month in
      progress" subtitle, sync-failed sidebar red dot.
- [ ] **D4. Mobile responsive** — BRD §17 punts to v2; revisit.
- [ ] **D5. CONTRIBUTING.md** with metric-design philosophy guardrails.

---

## Known follow-ups carried forward from earlier sessions

- [ ] When cycle time is less than lead time (squash-merge orgs), tooltip should explain why.
- [ ] Pagination on the team table (>20 rows triggers it per BRD §12).
- [ ] `vercel.json` install command kludge (`echo 'install handled in buildCommand'`) — find
      a cleaner way.

---

## Out of scope for the foreseeable future (per BRD §10, §17)

These are intentionally excluded so the decision isn't relitigated:

- MTTR (requires incident data)
- Change Failure Rate (requires reliable revert/rollback signal)
- Code Churn (expensive, marginal signal)
- Test coverage, bug escape rate, sprint velocity (require external tools)
- Individual scoring / rankings / "top performers" lists (philosophically opposed)
- SSO/OAuth, multi-tenant, Slack notifications, CSV/PDF export (BRD §17)
