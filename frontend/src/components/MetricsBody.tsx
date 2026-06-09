/**
 * Reusable "KPI grid + charts" body shared by Org Overview, Team Detail, Contributor pages.
 * Accepts any object with the OrgMetrics-shaped kpis/series/config fields.
 */
import { useLocation } from "react-router-dom";
import type { OrgMetrics } from "../api/types";
import { CycleTimeBreakdown } from "./CycleTimeBreakdown";
import { KpiCard } from "./KpiCard";
import { MetricLineChart } from "./MetricLineChart";

export const METRIC_DEFS = {
  deployment_frequency:
    "Number of deployments per week. Source: tags matching DEPLOYMENT_TAG_PATTERN, or merges to DEPLOYMENT_BRANCH.",
  lead_time_p50:
    "Median hours from the first commit in a PR to the PR being merged. Falls back to PR open time if commits are unavailable.",
  pr_cycle_time:
    "Median hours from PR open to merge, broken into pickup (open→first review), review (first review→last approval), and merge phases.",
  pr_throughput: "Number of merged PRs per week, excluding configured bots.",
  pr_size:
    "Median lines changed (additions + deletions) per merged PR. Red when above LARGE_PR_THRESHOLD.",
  review_coverage:
    "Percent of merged PRs that received at least one review from a non-author.",
  time_to_first_review:
    "Median hours from PR open to first review event from a non-author.",
  ai_assisted:
    "Percent of merged PRs detected as AI-assisted. Detection looks for Co-Authored-By trailers on the merge commit and known markers in the PR body (Claude, Cursor, Copilot, Codex, Windsurf). LOWER BOUND — devs who use AI but strip the trailers will not be counted.",
} as const;

const LABELS = {
  deployment_frequency: "Deployment Frequency",
  lead_time_p50: "Lead Time",
  pr_cycle_time: "PR Cycle Time",
  pr_throughput: "PR Throughput",
  pr_size: "PR Size",
  review_coverage: "Review Coverage",
  time_to_first_review: "Time to First Review",
  ai_assisted: "AI-Assisted",
} as const;

type MetricKey = keyof typeof METRIC_DEFS;

const ORDER: MetricKey[] = [
  "deployment_frequency",
  "lead_time_p50",
  "pr_cycle_time",
  "pr_throughput",
  "pr_size",
  "review_coverage",
  "time_to_first_review",
  "ai_assisted",
];

export function MetricsBody({
  data,
  linkPrefix,
}: {
  data: Pick<OrgMetrics, "kpis" | "series">;
  /** If provided, each KPI card links to `${linkPrefix}/${metricKey}`. Pass undefined for static. */
  linkPrefix?: string;
}) {
  const search = useLocation().search;
  const s = data.series;
  const sparkFor = (k: MetricKey): (number | null)[] => {
    switch (k) {
      case "deployment_frequency":
        return s.deployment_frequency.slice(-8).map((p) => p.value);
      case "lead_time_p50":
        return s.lead_time.slice(-8).map((p) => p.p50);
      case "pr_cycle_time":
        return s.pr_cycle_time
          .slice(-8)
          .map((p) =>
            p.pickup === null && p.review === null && p.merge === null
              ? null
              : (p.pickup ?? 0) + (p.review ?? 0) + (p.merge ?? 0),
          );
      case "pr_throughput":
        return s.pr_throughput.slice(-8).map((p) => p.value);
      case "pr_size":
        return s.pr_size.slice(-8).map((p) => p.value);
      case "review_coverage":
        return s.review_coverage.slice(-8).map((p) => p.value);
      case "time_to_first_review":
        return s.time_to_first_review.slice(-8).map((p) => p.value);
      case "ai_assisted":
        return s.ai_assisted.slice(-8).map((p) => p.value);
    }
  };

  return (
    <>
      <div className="grid grid-cols-4 gap-3 mb-6">
        {ORDER.map((k) => {
          const kpi = data.kpis[k];
          return (
            <KpiCard
              key={k}
              label={LABELS[k]}
              definition={METRIC_DEFS[k]}
              value={kpi.value}
              unit={kpi.unit}
              deltaPct={kpi.delta_pct}
              badDirection={kpi.bad_direction}
              spark={sparkFor(k)}
              redWhenAbove={kpi.red_when_above}
              to={linkPrefix ? `${linkPrefix}/${k}${search}` : undefined}
            />
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        <ChartCard title="Deployment Frequency (weekly)">
          <MetricLineChart
            data={s.deployment_frequency.map((p) => ({ week: p.week, Deploys: p.value }))}
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
    </>
  );
}

export function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-card border border-border rounded p-4">
      <div className="text-text font-medium text-[13px] mb-3">{title}</div>
      {children}
    </div>
  );
}

export { LABELS as METRIC_LABELS };
export type { MetricKey };
