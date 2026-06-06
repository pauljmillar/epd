import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { setRepoTracked, useAdminRepos } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { Toggle } from "../components/Toggle";

export function ReposIndex() {
  const { data, isLoading } = useAdminRepos();
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [showUntracked, setShowUntracked] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const visible = useMemo(
    () =>
      (data?.repos ?? [])
        .filter((r) => (showUntracked ? true : r.is_tracked))
        .filter((r) => r.full_name.toLowerCase().includes(filter.toLowerCase())),
    [data, filter, showUntracked],
  );

  const tracked = (data?.repos ?? []).filter((r) => r.is_tracked).length;
  const total = data?.repos.length ?? 0;

  async function toggle(fullName: string, next: boolean) {
    setBusy(fullName);
    try {
      await setRepoTracked(fullName, next);
      qc.invalidateQueries({ queryKey: ["admin-repos"] });
      qc.invalidateQueries({ queryKey: ["repos"] });
      // Dashboard data changes too — every metric query needs a refetch
      qc.invalidateQueries({ queryKey: ["org"] });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader title="Repos" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-4">
        {tracked}/{total} repos tracked. Untracked repos are hidden from the dashboard and
        skipped on subsequent syncs. Click into a repo for its detail view.
      </p>

      <div className="flex gap-3 mb-4 items-center">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search…"
          className="border border-border rounded px-3 py-2 text-sm w-72"
        />
        <label className="text-sm text-text-secondary flex items-center gap-2">
          <input
            type="checkbox"
            checked={showUntracked}
            onChange={(e) => setShowUntracked(e.target.checked)}
          />
          Show untracked
        </label>
      </div>

      <div className="bg-card border border-border rounded">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-center px-4 py-2 font-semibold w-20">Tracked</th>
              <th className="text-left px-4 py-2 font-semibold">Repo</th>
              <th className="text-right px-4 py-2 font-semibold">PRs merged (total)</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-6 text-text-tertiary text-sm" colSpan={3}>
                  Loading…
                </td>
              </tr>
            )}
            {visible.map((r) => (
              <tr
                key={r.full_name}
                className={`border-t border-border-subtle hover:bg-active ${
                  r.is_tracked ? "" : "opacity-50"
                }`}
              >
                <td className="px-4 py-2.5 text-center">
                  <Toggle
                    checked={r.is_tracked}
                    disabled={busy === r.full_name}
                    onChange={(next) => toggle(r.full_name, next)}
                    label={`Toggle ${r.full_name}`}
                  />
                </td>
                <td className="px-4 py-2.5 text-text">
                  <Link to={`/repos/${r.full_name}`}>{r.full_name}</Link>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary">
                  {r.prs_merged_total.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
