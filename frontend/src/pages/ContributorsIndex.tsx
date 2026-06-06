import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { setContributorTracked, useAdminContributors } from "../api/client";
import { PageHeader } from "../components/PageHeader";
import { Toggle } from "../components/Toggle";

export function ContributorsIndex() {
  const { data, isLoading } = useAdminContributors();
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [showUntracked, setShowUntracked] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const visible = useMemo(
    () =>
      (data?.contributors ?? [])
        .filter((c) => (showUntracked ? true : c.is_tracked))
        .filter((c) => c.login.toLowerCase().includes(filter.toLowerCase())),
    [data, filter, showUntracked],
  );

  const tracked = (data?.contributors ?? []).filter((c) => c.is_tracked).length;
  const total = data?.contributors.length ?? 0;

  async function toggle(login: string, next: boolean) {
    setBusy(login);
    try {
      await setContributorTracked(login, next);
      qc.invalidateQueries({ queryKey: ["admin-contributors"] });
      qc.invalidateQueries({ queryKey: ["contributors-list"] });
      qc.invalidateQueries({ queryKey: ["org"] });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader title="Contributors" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-4">
        {tracked}/{total} contributors tracked. Untracked contributors' PRs are excluded from
        every metric.
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
              <th className="text-left px-4 py-2 font-semibold">Contributor</th>
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
            {visible.map((c) => (
              <tr
                key={c.login}
                className={`border-t border-border-subtle hover:bg-active ${
                  c.is_tracked ? "" : "opacity-50"
                }`}
              >
                <td className="px-4 py-2.5 text-center">
                  <Toggle
                    checked={c.is_tracked}
                    disabled={busy === c.login}
                    onChange={(next) => toggle(c.login, next)}
                    label={`Toggle ${c.login}`}
                  />
                </td>
                <td className="px-4 py-2.5 text-text">
                  <Link to={`/contributors/${c.login}`}>{c.login}</Link>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary">
                  {c.prs_merged_total.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
