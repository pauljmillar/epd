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

## Phase B — Drill-down pages ✅ DONE

- [x] B1. `react-router-dom` v7. Routes: `/`, `/teams/*`, `/metrics/:metricKey`,
      `/contributors/:login`. Vercel SPA rewrites in place for deep links.
- [x] B2. Team Detail page (scoped Org Overview + per-author contributor table).
- [x] B3. Metric Detail page (single-metric chart + team breakdown + notable PRs
      for lead-time view).
- [x] B4. Contributor page with prominent BRD §12 "context, not evaluation" banner +
      stats-vs-team-median + last 20 PRs (with AI tool badges).
- [x] B5. Sidebar populates with the top 30 teams (by 90-day PR count) from `/metrics/teams`.

**Carried forward (didn't fit Phase B):**

- [ ] Notable PRs for the other 7 metrics (currently only `lead_time_p50` has them). Add
      `notable_prs_by_size`, `notable_prs_by_cycle_time`, etc.
- [ ] Sortable table headers on the team table.
- [ ] Pagination on lists >20 rows (BRD §12 design constraint).
- [ ] Trend sparklines in the team table (currently empty placeholders).

---

## Phase B+ — Manual team grouping ✅ DONE

- [x] Schema: migration 0004 finally creates `teams` + `team_members` (they were specced in
      BRD §13 but missing from migration 0001).
- [x] Admin UI at `/teams`: two-pane create/delete on left, member-chip + filterable picker
      on right.
- [x] Conceptual rename: repo-scoped routes/endpoints/labels renamed `team→repo`; "Teams"
      now means a group of contributors, not a repo.
- [x] Multi-team membership works (a contributor can be added to multiple teams; team
      metrics just filter PRs by `author IN (team members)`).
- [x] Sidebar split into 4 sections: Overview · Repos · Teams · Contributors. Each has its
      own index page and collapsible inline list.

**Carried forward:**

- [ ] Contributor page's "vs team median" still uses repo-as-team math (since it pre-dates
      real teams). Switch to "vs any EPD team this person belongs to" once we have the
      data structures in place.
- [ ] Per-member AI-assisted % on the Team Detail page (the per-repo breakdown shows lead
      time and PR count but not AI%).
- [ ] Inline rename of a team (currently only create/delete).

---

## Phase C — GitLab collector ✅ DONE

- [x] `backend/app/collectors/gitlab.py` mirrors the GitHub collector's dataclass interface
      using GitLab REST v4. Group → projects (recursive, archived excluded), merged MRs,
      MR detail, first-commit lead time, notes-as-reviews, tag-or-branch deployments.
- [x] `sync.py` refactored source-agnostic: persist helpers take `source` arg. `run_sync()`
      iterates over every configured source. Both can run.
- [x] Per-source `is_tracked` filtering carries through (toggle a gitlab.com/x/y repo off
      independently of github.com/a/b).
- [x] 3 GitLab collector tests via respx. 41 total passing.
- [x] README "GitLab limitations" section honestly documents v1 gaps.
- [x] `.env.example` shows both source blocks.

**Carried forward:**

- [ ] Merge-commit body for GitLab MRs (one extra `/commits/{sha}` call per MR; would
      improve AI-attribution recall for GitLab).
- [ ] GitLab GraphQL alternative — could batch the per-MR detail/commits/notes calls into
      a single request, cutting backfill time for large orgs.
- [ ] Self-hosted GitLab instance support (currently hardcoded to `gitlab.com`; add
      `GITLAB_URL` env var to override).

---

## Phase C+ — Admin: repo + contributor include/exclude UI ✅ DONE

- [x] Migration 0005: `is_tracked` BOOLEAN on `repositories` AND `contributors`.
- [x] PATCH `/api/v1/admin/repos/{full_name}` and `/api/v1/admin/contributors/{login}`.
- [x] Admin lists at `/api/v1/admin/repos` and `/api/v1/admin/contributors` return
      everything with current toggle state + lifetime PR counts.
- [x] Every metric query filters by both flags; round-trip verified live (toggle ruff
      off → org count drops by exactly 1,107).
- [x] Sync skips untracked repos to save GitHub API rate-limit budget.
- [x] Frontend ReposIndex and ContributorsIndex render the admin toggles with a
      "show untracked" filter; untracked rows show at 50% opacity.

**Carried forward (nice-to-have):**

- [ ] Bulk-toggle ("untrack all dependabot/renovate bots in one click").
- [ ] Sync log shows how many repos were skipped on each run.

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
