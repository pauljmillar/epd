import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useOrgMetrics } from "../api/client";
import type { OrgMetrics } from "../api/types";
import { ChartCard, MetricsBody } from "../components/MetricsBody";
import { PageHeader } from "../components/PageHeader";
import { Sparkline } from "../components/Sparkline";
import { useTeamFilter, withTeamSearch } from "../lib/teamFilter";

export function OrgOverview() {
  const [period, setPeriod] = useState("90d");
  const { teamId } = useTeamFilter();
  const { data, isLoading, error } = useOrgMetrics(period, teamId);

  return (
    <div>
      <PageHeader title="Overview" period={period} onPeriodChange={setPeriod} showTeamFilter />

      {error && (
        <div className="bg-card border border-alert text-alert p-4 rounded mb-4 text-sm">
          Failed to load metrics: {String(error)}
        </div>
      )}
      {isLoading && <div className="text-text-secondary text-sm">Loading…</div>}

      {data && <OverviewBody data={data} />}
    </div>
  );
}

function OverviewBody({ data }: { data: OrgMetrics }) {
  const aiTools = data.kpis.ai_assisted.tools ?? {};
  const aiToolsTotal = Object.values(aiTools).reduce((a, b) => a + b, 0);

  return (
    <>
      <MetricsBody data={data} linkPrefix="/metrics" />

      <div className="mb-6">
        <ChartCard title="AI tool breakdown (period total)">
          <AiToolsBreakdown tools={aiTools} total={aiToolsTotal} />
        </ChartCard>
      </div>

      <RepoTable repos={data.repos} largePrThreshold={data.config.large_pr_threshold} />
    </>
  );
}

function AiToolsBreakdown({
  tools,
  total,
}: {
  tools: Record<string, number>;
  total: number;
}) {
  if (total === 0) {
    return (
      <div className="h-[180px] flex items-center justify-center text-text-secondary text-sm text-center px-6">
        No AI-assisted PRs detected in this period.
        <br />
        <span className="text-text-tertiary text-xs mt-2 block">
          Detection relies on commit trailers and PR body markers; this is a lower bound.
        </span>
      </div>
    );
  }
  const sorted = Object.entries(tools).sort((a, b) => b[1] - a[1]);
  const max = sorted[0][1];
  return (
    <div className="flex flex-col gap-2">
      {sorted.map(([tool, count]) => {
        const pct = (count / total) * 100;
        const width = (count / max) * 100;
        return (
          <div key={tool}>
            <div className="flex justify-between text-xs text-text-secondary mb-1">
              <span className="capitalize">{tool}</span>
              <span>
                {count} PR{count === 1 ? "" : "s"} ({pct.toFixed(0)}%)
              </span>
            </div>
            <div className="h-2 bg-border-subtle rounded">
              <div className="h-2 bg-text rounded" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmtHours(v: number | null): string {
  if (v === null) return "—";
  if (v >= 48) return `${(v / 24).toFixed(1)}d`;
  return `${v.toFixed(1)}h`;
}

function RepoTable({
  repos,
  largePrThreshold,
}: {
  repos: OrgMetrics["repos"];
  largePrThreshold: number;
}) {
  const search = useLocation().search;
  if (!repos.length) {
    return (
      <div className="bg-card border border-border rounded p-6 text-text-secondary text-sm">
        No repo data yet — waiting on first sync.
      </div>
    );
  }
  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="text-text font-medium text-[13px]">Repository breakdown</div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
            <th className="text-left px-4 py-2 font-semibold">Repo</th>
            <th className="text-right px-4 py-2 font-semibold">Deploy Freq</th>
            <th className="text-right px-4 py-2 font-semibold">Lead Time</th>
            <th className="text-right px-4 py-2 font-semibold">Cycle Time</th>
            <th className="text-right px-4 py-2 font-semibold">PR Size</th>
            <th className="text-right px-4 py-2 font-semibold">Coverage</th>
            <th className="text-right px-4 py-2 font-semibold">1st Review</th>
            <th className="text-right px-4 py-2 font-semibold">AI %</th>
            <th className="text-right px-4 py-2 font-semibold">Throughput</th>
            <th className="text-right px-4 py-2 font-semibold">PRs</th>
            <th className="text-left px-4 py-2 font-semibold">Trend</th>
          </tr>
        </thead>
        <tbody>
          {repos.map((t) => {
            const sizeIsLarge =
              t.median_pr_size_lines !== null && t.median_pr_size_lines > largePrThreshold;
            return (
              <tr
                key={t.full_name}
                className="border-t border-border-subtle hover:bg-active cursor-pointer"
              >
                <td className="px-4 py-3 text-text">
                  <Link
                    to={withTeamSearch(`/repos/${t.full_name}`, search)}
                    className="block"
                  >
                    {t.full_name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {t.deploy_per_week.toFixed(1)}/wk
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(t.lead_time_p50_hours)}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(t.pr_cycle_time_hours)}
                </td>
                <td
                  className={`px-4 py-3 text-right ${
                    sizeIsLarge ? "text-alert" : "text-text"
                  }`}
                >
                  {t.median_pr_size_lines === null
                    ? "—"
                    : `${Math.round(t.median_pr_size_lines)} L`}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {t.review_coverage_pct === null
                    ? "—"
                    : `${t.review_coverage_pct.toFixed(0)}%`}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {fmtHours(t.time_to_first_review_hours)}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {t.ai_assisted_pct === null
                    ? "—"
                    : `${t.ai_assisted_pct.toFixed(0)}%`}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {t.throughput_per_week.toFixed(1)}/wk
                </td>
                <td className="px-4 py-3 text-right text-text-secondary">{t.prs_merged}</td>
                <td className="px-4 py-3">
                  <Sparkline values={[]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
