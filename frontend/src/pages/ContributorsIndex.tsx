import { useState } from "react";
import { Link } from "react-router-dom";
import { useContributorsList } from "../api/client";
import { PageHeader } from "../components/PageHeader";

export function ContributorsIndex() {
  const { data, isLoading } = useContributorsList();
  const [filter, setFilter] = useState("");
  const filtered = (data?.contributors ?? []).filter((c) =>
    c.login.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div>
      <PageHeader title="Contributors" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-4">
        Authors of merged PRs in the last 90 days, ordered by PR volume.
      </p>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search…"
        className="border border-border rounded px-3 py-2 text-sm mb-4 w-72"
      />
      <div className="bg-card border border-border rounded">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-semibold">Contributor</th>
              <th className="text-right px-4 py-2 font-semibold">PRs merged (90d)</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-6 text-text-tertiary text-sm" colSpan={2}>
                  Loading…
                </td>
              </tr>
            )}
            {filtered.map((c) => (
              <tr key={c.login} className="border-t border-border-subtle hover:bg-active">
                <td className="px-4 py-2.5 text-text">
                  <Link to={`/contributors/${c.login}`}>{c.login}</Link>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary">
                  {c.prs_merged_90d}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
