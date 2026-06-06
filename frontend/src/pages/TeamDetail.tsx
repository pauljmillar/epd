import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTeamMetrics } from "../api/client";
import type { TeamMetrics } from "../api/types";
import { MetricsBody } from "../components/MetricsBody";
import { PageHeader } from "../components/PageHeader";

export function TeamDetail() {
  const location = useLocation();
  // /teams/astral-sh/uv → teamName = "astral-sh/uv"
  const teamName = location.pathname.replace(/^\/teams\//, "") || undefined;
  const [period, setPeriod] = useState("90d");
  const { data, isLoading, error } = useTeamMetrics(teamName, period);

  return (
    <div>
      <div className="text-text-tertiary text-xs mb-2">
        <Link to="/" className="hover:text-text">Overview</Link>
        <span className="mx-2">›</span>
        <span className="text-text">{teamName}</span>
      </div>
      <PageHeader title={teamName ?? "Team"} period={period} onPeriodChange={setPeriod} />

      {error && (
        <div className="bg-card border border-alert text-alert p-4 rounded mb-4 text-sm">
          {String(error)}
        </div>
      )}
      {isLoading && <div className="text-text-secondary text-sm">Loading…</div>}
      {data && <TeamBody data={data} />}
    </div>
  );
}

function TeamBody({ data }: { data: TeamMetrics }) {
  return (
    <>
      <MetricsBody data={data} linkPrefix={`/metrics`} />

      <div className="bg-card border border-border rounded mb-6">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="text-text font-medium text-[13px]">
            Contributor context — {data.team.name}
          </div>
          <div className="text-text-tertiary text-xs">
            ⓘ This view is for context, not evaluation.
          </div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-semibold">Contributor</th>
              <th className="text-right px-4 py-2 font-semibold">PRs</th>
              <th className="text-right px-4 py-2 font-semibold">Lead Time</th>
              <th className="text-right px-4 py-2 font-semibold">Cycle Time</th>
              <th className="text-right px-4 py-2 font-semibold">PR Size</th>
              <th className="text-right px-4 py-2 font-semibold">Coverage</th>
              <th className="text-right px-4 py-2 font-semibold">1st Review</th>
              <th className="text-right px-4 py-2 font-semibold">AI %</th>
            </tr>
          </thead>
          <tbody>
            {data.contributors.map((c) => (
              <tr key={c.login} className="border-t border-border-subtle hover:bg-active">
                <td className="px-4 py-3 text-text">
                  <Link to={`/contributors/${c.login}`} className="block">
                    {c.login}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right text-text-secondary">{c.prs_merged}</td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(c.lead_time_p50_hours)}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(c.pr_cycle_time_hours)}
                </td>
                <td
                  className={`px-4 py-3 text-right ${
                    c.median_pr_size_lines !== null &&
                    c.median_pr_size_lines > data.config.large_pr_threshold
                      ? "text-alert"
                      : "text-text"
                  }`}
                >
                  {c.median_pr_size_lines === null
                    ? "—"
                    : `${Math.round(c.median_pr_size_lines)} L`}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {c.review_coverage_pct === null ? "—" : `${c.review_coverage_pct.toFixed(0)}%`}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(c.time_to_first_review_hours)}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {c.ai_assisted_pct === null ? "—" : `${c.ai_assisted_pct.toFixed(0)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function fmtHours(v: number | null): string {
  if (v === null) return "—";
  if (v >= 48) return `${(v / 24).toFixed(1)}d`;
  return `${v.toFixed(1)}h`;
}
