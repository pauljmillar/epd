import { Link } from "react-router-dom";
import { useReposList } from "../api/client";
import { PageHeader } from "../components/PageHeader";

export function ReposIndex() {
  const { data, isLoading } = useReposList();
  return (
    <div>
      <PageHeader title="Repos" period="" onPeriodChange={() => {}} />
      <p className="text-text-secondary text-sm -mt-4 mb-6">
        Tracked repositories from the configured GitHub org. Click into one for repo-scoped
        metrics.
      </p>
      <div className="bg-card border border-border rounded">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-semibold">Repo</th>
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
            {data?.repos.map((r) => (
              <tr key={r.full_name} className="border-t border-border-subtle hover:bg-active">
                <td className="px-4 py-2.5 text-text">
                  <Link to={`/repos/${r.full_name}`}>{r.full_name}</Link>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary">
                  {r.prs_merged_90d}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
