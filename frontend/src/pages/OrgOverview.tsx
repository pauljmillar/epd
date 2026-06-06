import { useState } from "react";
import { useOrgMetrics } from "../api/client";
import type { OrgMetrics } from "../api/types";
import { CycleTimeBreakdown } from "../components/CycleTimeBreakdown";
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
    "Median hours from PR open to merge, broken into pickup (open→first review), review (first review→last approval), and merge phases.",
  throughput:
    "Number of merged PRs per week, excluding configured bots.",
  prSize:
    "Median lines changed (additions + deletions) per merged PR. Red when above LARGE_PR_THRESHOLD.",
  reviewCoverage:
    "Percent of merged PRs that received at least one review from a non-author.",
  firstReview:
    "Median hours from PR open to first review event from a non-author.",
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

      {data && <OverviewBody data={data} />}
    </div>
  );
}

function OverviewBody({ data }: { data: OrgMetrics }) {
  const s = data.series;

  const cards: Array<{
    label: string;
    definition: string;
    kpiKey: keyof OrgMetrics["kpis"];
    spark: (number | null)[];
  }> = [
    {
      label: "Deployment Frequency",
      definition: DEFS.deployFreq,
      kpiKey: "deployment_frequency",
      spark: s.deployment_frequency.slice(-8).map((p) => p.value),
    },
    {
      label: "Lead Time",
      definition: DEFS.leadTime,
      kpiKey: "lead_time_p50",
      spark: s.lead_time.slice(-8).map((p) => p.p50),
    },
    {
      label: "PR Cycle Time",
      definition: DEFS.cycleTime,
      kpiKey: "pr_cycle_time",
      spark: s.pr_cycle_time
        .slice(-8)
        .map((p) =>
          p.pickup === null && p.review === null && p.merge === null
            ? null
            : (p.pickup ?? 0) + (p.review ?? 0) + (p.merge ?? 0),
        ),
    },
    {
      label: "PR Throughput",
      definition: DEFS.throughput,
      kpiKey: "pr_throughput",
      spark: s.pr_throughput.slice(-8).map((p) => p.value),
    },
    {
      label: "PR Size",
      definition: DEFS.prSize,
      kpiKey: "pr_size",
      spark: s.pr_size.slice(-8).map((p) => p.value),
    },
    {
      label: "Review Coverage",
      definition: DEFS.reviewCoverage,
      kpiKey: "review_coverage",
      spark: s.review_coverage.slice(-8).map((p) => p.value),
    },
    {
      label: "Time to First Review",
      definition: DEFS.firstReview,
      kpiKey: "time_to_first_review",
      spark: s.time_to_first_review.slice(-8).map((p) => p.value),
    },
  ];

  return (
    <>
      <div className="grid grid-cols-4 gap-3 mb-6">
        {cards.map((c) => {
          const k = data.kpis[c.kpiKey];
          return (
            <KpiCard
              key={c.kpiKey}
              label={c.label}
              definition={c.definition}
              value={k.value}
              unit={k.unit}
              deltaPct={k.delta_pct}
              badDirection={k.bad_direction}
              spark={c.spark}
              redWhenAbove={k.red_when_above}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        <ChartCard title="Deployment Frequency (weekly)">
          <MetricLineChart
            data={s.deployment_frequency.map((p) => ({
              week: p.week,
              Deploys: p.value,
            }))}
            series={[{ key: "Deploys", label: "Deploys" }]}
            yLabel="per week"
          />
        </ChartCard>
        <ChartCard title="Lead Time for Changes (weekly)">
          <MetricLineChart
            data={s.lead_time.map((p) => ({ week: p.week, P50: p.p50, P75: p.p75 }))}
            series={[
              { key: "P50", label: "P50" },
              { key: "P75", label: "P75", dashed: true },
            ]}
            yLabel="hours"
          />
        </ChartCard>
      </div>

      <div className="mb-6">
        <ChartCard title="PR Cycle Time breakdown (weekly)">
          <CycleTimeBreakdown data={s.pr_cycle_time} />
        </ChartCard>
      </div>

      <TeamTable teams={data.teams} largePrThreshold={data.config.large_pr_threshold} />
    </>
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

function fmtHours(v: number | null): string {
  if (v === null) return "—";
  if (v >= 48) return `${(v / 24).toFixed(1)}d`;
  return `${v.toFixed(1)}h`;
}

function TeamTable({
  teams,
  largePrThreshold,
}: {
  teams: OrgMetrics["teams"];
  largePrThreshold: number;
}) {
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
            <th className="text-right px-4 py-2 font-semibold">Lead Time</th>
            <th className="text-right px-4 py-2 font-semibold">Cycle Time</th>
            <th className="text-right px-4 py-2 font-semibold">PR Size</th>
            <th className="text-right px-4 py-2 font-semibold">Coverage</th>
            <th className="text-right px-4 py-2 font-semibold">1st Review</th>
            <th className="text-right px-4 py-2 font-semibold">Throughput</th>
            <th className="text-right px-4 py-2 font-semibold">PRs</th>
            <th className="text-left px-4 py-2 font-semibold">Trend</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((t) => {
            const sizeIsLarge =
              t.median_pr_size_lines !== null && t.median_pr_size_lines > largePrThreshold;
            return (
              <tr key={t.name} className="border-t border-border-subtle">
                <td className="px-4 py-3 text-text">{t.name}</td>
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
