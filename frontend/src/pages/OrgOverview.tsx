import { useState } from "react";
import { useOrgMetrics } from "../api/client";
import { KpiCard } from "../components/KpiCard";
import { MetricLineChart } from "../components/MetricLineChart";
import { PageHeader } from "../components/PageHeader";
import { Sparkline } from "../components/Sparkline";

const DEFS = {
  deployFreq:
    "Number of deployments per week. Source: tags matching DEPLOYMENT_TAG_PATTERN, or merges to DEPLOYMENT_BRANCH.",
  leadTime:
    "Median hours from the first commit in a PR to the PR being merged. Falls back to PR open time if commits are unavailable.",
  cycleTime:
    "Total hours from PR open to merge. (Not yet implemented in v0.)",
  throughput:
    "Number of merged PRs per week, excluding configured bots.",
  reviewCoverage:
    "% of merged PRs that received at least one review from a non-author. (Not yet implemented in v0.)",
  firstReview:
    "Median hours from PR open to first review event from a non-author. (Not yet implemented in v0.)",
};

export function OrgOverview() {
  const [period, setPeriod] = useState("90d");
  const { data, isLoading, error } = useOrgMetrics(period);

  return (
    <div>
      <PageHeader title="Overview" period={period} onPeriodChange={setPeriod} />

      {error && (
        <div className="bg-card border border-alert text-alert p-4 rounded mb-4 text-sm">
          Failed to load metrics: {String(error)}
        </div>
      )}
      {isLoading && <div className="text-text-secondary text-sm">Loading…</div>}

      {data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-6">
            <KpiCard
              label="Deployment Frequency"
              definition={DEFS.deployFreq}
              value={data.kpis.deployment_frequency.value}
              unit={data.kpis.deployment_frequency.unit}
              deltaPct={data.kpis.deployment_frequency.delta_pct}
              badDirection={data.kpis.deployment_frequency.bad_direction}
              spark={data.series.deployment_frequency.slice(-8).map((p) => p.value)}
            />
            <KpiCard
              label="Lead Time"
              definition={DEFS.leadTime}
              value={data.kpis.lead_time_p50.value}
              unit={data.kpis.lead_time_p50.unit}
              deltaPct={data.kpis.lead_time_p50.delta_pct}
              badDirection={data.kpis.lead_time_p50.bad_direction}
              spark={data.series.lead_time.slice(-8).map((p) => p.p50)}
            />
            <KpiCard
              label="PR Throughput"
              definition={DEFS.throughput}
              value={data.kpis.pr_throughput.value}
              unit={data.kpis.pr_throughput.unit}
              deltaPct={data.kpis.pr_throughput.delta_pct}
              badDirection={data.kpis.pr_throughput.bad_direction}
              spark={data.series.pr_throughput.slice(-8).map((p) => p.value)}
            />
            <PlaceholderCard label="PR Cycle Time" definition={DEFS.cycleTime} />
            <PlaceholderCard label="Review Coverage" definition={DEFS.reviewCoverage} />
            <PlaceholderCard label="Time to First Review" definition={DEFS.firstReview} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-6">
            <ChartCard title="Deployment Frequency (weekly)">
              <MetricLineChart
                data={data.series.deployment_frequency.map((p) => ({
                  week: p.week,
                  Deploys: p.value,
                }))}
                series={[{ key: "Deploys", label: "Deploys" }]}
                yLabel="per week"
              />
            </ChartCard>
            <ChartCard title="Lead Time for Changes (weekly)">
              <MetricLineChart
                data={data.series.lead_time.map((p) => ({
                  week: p.week,
                  P50: p.p50,
                  P75: p.p75,
                }))}
                series={[
                  { key: "P50", label: "P50" },
                  { key: "P75", label: "P75", dashed: true },
                ]}
                yLabel="hours"
              />
            </ChartCard>
          </div>

          <TeamTable teams={data.teams} />
        </>
      )}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded p-4">
      <div className="text-text font-medium text-[13px] mb-3">{title}</div>
      {children}
    </div>
  );
}

function PlaceholderCard({ label, definition }: { label: string; definition: string }) {
  return (
    <div className="bg-card border border-border rounded p-4">
      <div className="flex items-start justify-between">
        <span className="text-text-secondary text-[11px] font-semibold uppercase tracking-wider">
          {label}
        </span>
        <span className="text-text-tertiary text-xs" title={definition}>
          ?
        </span>
      </div>
      <div className="text-text-tertiary font-semibold text-[32px] leading-tight mt-3">—</div>
      <div className="text-text-tertiary text-[13px] mt-2">Not yet implemented in v0</div>
    </div>
  );
}

function TeamTable({ teams }: { teams: { name: string; prs_merged: number; throughput_per_week: number; deploy_per_week: number; lead_time_p50_hours: number | null }[] }) {
  if (!teams.length) {
    return (
      <div className="bg-card border border-border rounded p-6 text-text-secondary text-sm">
        No team data yet — waiting on first sync.
      </div>
    );
  }
  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="text-text font-medium text-[13px]">Repository breakdown</div>
        <div className="text-text-tertiary text-xs">
          ⓘ v0 uses repos as teams. Configure GitHub teams in v1.
        </div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
            <th className="text-left px-4 py-2 font-semibold">Repo</th>
            <th className="text-right px-4 py-2 font-semibold">Deploy Freq</th>
            <th className="text-right px-4 py-2 font-semibold">Lead Time (P50)</th>
            <th className="text-right px-4 py-2 font-semibold">Throughput</th>
            <th className="text-right px-4 py-2 font-semibold">PRs Merged</th>
            <th className="text-left px-4 py-2 font-semibold">Trend</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((t) => (
            <tr key={t.name} className="border-t border-border-subtle">
              <td className="px-4 py-3 text-text">{t.name}</td>
              <td className="px-4 py-3 text-right text-text">
                {t.deploy_per_week.toFixed(1)}/wk
              </td>
              <td className="px-4 py-3 text-right text-text">
                {t.lead_time_p50_hours === null
                  ? "—"
                  : t.lead_time_p50_hours >= 48
                  ? `${(t.lead_time_p50_hours / 24).toFixed(1)}d`
                  : `${t.lead_time_p50_hours.toFixed(1)}h`}
              </td>
              <td className="px-4 py-3 text-right text-text">
                {t.throughput_per_week.toFixed(1)}/wk
              </td>
              <td className="px-4 py-3 text-right text-text-secondary">{t.prs_merged}</td>
              <td className="px-4 py-3">
                <Sparkline values={[]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
