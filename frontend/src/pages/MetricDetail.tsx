import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useOrgMetrics } from "../api/client";
import type { OrgMetrics } from "../api/types";
import { CycleTimeBreakdown } from "../components/CycleTimeBreakdown";
import { ChartCard, METRIC_DEFS, METRIC_LABELS, type MetricKey } from "../components/MetricsBody";
import { MetricLineChart } from "../components/MetricLineChart";
import { PageHeader } from "../components/PageHeader";

export function MetricDetail() {
  const { metricKey } = useParams<{ metricKey: MetricKey }>();
  const [period, setPeriod] = useState("90d");
  const { data, isLoading, error } = useOrgMetrics(period);

  if (!metricKey || !(metricKey in METRIC_DEFS)) {
    return (
      <div className="text-alert text-sm">Unknown metric: {String(metricKey)}</div>
    );
  }

  return (
    <div>
      <div className="text-text-tertiary text-xs mb-2">
        <Link to="/" className="hover:text-text">Overview</Link>
        <span className="mx-2">›</span>
        <span className="text-text">{METRIC_LABELS[metricKey]}</span>
      </div>
      <PageHeader
        title={METRIC_LABELS[metricKey]}
        period={period}
        onPeriodChange={setPeriod}
      />
      <p className="text-text-secondary text-sm -mt-4 mb-6">{METRIC_DEFS[metricKey]}</p>

      {error && (
        <div className="bg-card border border-alert text-alert p-4 rounded mb-4 text-sm">
          {String(error)}
        </div>
      )}
      {isLoading && <div className="text-text-secondary text-sm">Loading…</div>}
      {data && <DetailBody data={data} metricKey={metricKey} />}
    </div>
  );
}

function DetailBody({
  data,
  metricKey,
}: {
  data: OrgMetrics;
  metricKey: MetricKey;
}) {
  return (
    <>
      <ChartCard title={`${METRIC_LABELS[metricKey]} — weekly`}>
        <MainChart data={data} metricKey={metricKey} />
      </ChartCard>

      <div className="mt-6">
        <TeamTable data={data} metricKey={metricKey} />
      </div>

      {data.notable_prs?.lead_time && metricKey === "lead_time_p50" && (
        <div className="mt-6">
          <NotablePRs prs={data.notable_prs.lead_time} title="Longest lead-time PRs this period" />
        </div>
      )}
    </>
  );
}

function MainChart({ data, metricKey }: { data: OrgMetrics; metricKey: MetricKey }) {
  const s = data.series;
  switch (metricKey) {
    case "deployment_frequency":
      return (
        <MetricLineChart
          data={s.deployment_frequency.map((p) => ({ week: p.week, Deploys: p.value }))}
          series={[{ key: "Deploys", label: "Deploys" }]}
          yLabel="per week"
        />
      );
    case "lead_time_p50":
      return (
        <MetricLineChart
          data={s.lead_time.map((p) => ({ week: p.week, P50: p.p50, P75: p.p75 }))}
          series={[
            { key: "P50", label: "P50" },
            { key: "P75", label: "P75", dashed: true },
          ]}
          yLabel="hours"
        />
      );
    case "pr_cycle_time":
      return <CycleTimeBreakdown data={s.pr_cycle_time} />;
    case "pr_throughput":
      return (
        <MetricLineChart
          data={s.pr_throughput.map((p) => ({ week: p.week, PRs: p.value }))}
          series={[{ key: "PRs", label: "PRs" }]}
          yLabel="per week"
        />
      );
    case "pr_size":
      return (
        <MetricLineChart
          data={s.pr_size.map((p) => ({ week: p.week, Lines: p.value }))}
          series={[{ key: "Lines", label: "Median lines" }]}
          yLabel="lines"
        />
      );
    case "review_coverage":
      return (
        <MetricLineChart
          data={s.review_coverage.map((p) => ({ week: p.week, Pct: p.value }))}
          series={[{ key: "Pct", label: "% reviewed" }]}
          yLabel="%"
        />
      );
    case "time_to_first_review":
      return (
        <MetricLineChart
          data={s.time_to_first_review.map((p) => ({ week: p.week, Hours: p.value }))}
          series={[{ key: "Hours", label: "Hours" }]}
          yLabel="hours"
        />
      );
    case "ai_assisted":
      return (
        <MetricLineChart
          data={s.ai_assisted.map((p) => ({ week: p.week, Pct: p.value }))}
          series={[{ key: "Pct", label: "% AI-assisted" }]}
          yLabel="%"
        />
      );
  }
}

function fmt(unit: string, v: number | null): string {
  if (v === null) return "—";
  switch (unit) {
    case "hours":
      return v >= 48 ? `${(v / 24).toFixed(1)}d` : `${v.toFixed(1)}h`;
    case "per_week":
      return `${v.toFixed(1)}/wk`;
    case "pct":
      return `${v.toFixed(0)}%`;
    case "lines":
      return `${Math.round(v)} L`;
    default:
      return String(v);
  }
}

function TeamTable({ data, metricKey }: { data: OrgMetrics; metricKey: MetricKey }) {
  const repoField: Record<MetricKey, keyof OrgMetrics["repos"][0]> = {
    deployment_frequency: "deploy_per_week",
    lead_time_p50: "lead_time_p50_hours",
    pr_cycle_time: "pr_cycle_time_hours",
    pr_throughput: "throughput_per_week",
    pr_size: "median_pr_size_lines",
    review_coverage: "review_coverage_pct",
    time_to_first_review: "time_to_first_review_hours",
    ai_assisted: "ai_assisted_pct",
  };
  const field = repoField[metricKey];
  const unit = data.kpis[metricKey].unit;
  const sorted = [...data.repos].sort((a, b) => {
    const av = a[field] as number | null;
    const bv = b[field] as number | null;
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return bv - av;
  });

  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
        Repo breakdown
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
            <th className="text-left px-4 py-2 font-semibold">Repo</th>
            <th className="text-right px-4 py-2 font-semibold">
              {METRIC_LABELS[metricKey]}
            </th>
            <th className="text-right px-4 py-2 font-semibold">PRs merged</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => (
            <tr key={t.full_name} className="border-t border-border-subtle hover:bg-active">
              <td className="px-4 py-3 text-text">
                <Link to={`/repos/${t.full_name}`}>{t.full_name}</Link>
              </td>
              <td className="px-4 py-3 text-right text-text">
                {fmt(unit, t[field] as number | null)}
              </td>
              <td className="px-4 py-3 text-right text-text-secondary">{t.prs_merged}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NotablePRs({
  prs,
  title,
}: {
  prs: import("../api/types").NotablePR[];
  title: string;
}) {
  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
        {title}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
            <th className="text-left px-4 py-2 font-semibold">PR</th>
            <th className="text-left px-4 py-2 font-semibold">Repo</th>
            <th className="text-left px-4 py-2 font-semibold">Author</th>
            <th className="text-right px-4 py-2 font-semibold">Lead Time</th>
          </tr>
        </thead>
        <tbody>
          {prs.map((p) => (
            <tr key={`${p.repo}-${p.number}`} className="border-t border-border-subtle">
              <td className="px-4 py-3 text-text">
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:underline"
                >
                  #{p.number} {p.title}
                </a>
              </td>
              <td className="px-4 py-3 text-text-secondary">
                <Link to={`/repos/${p.repo}`}>{p.repo}</Link>
              </td>
              <td className="px-4 py-3 text-text-secondary">
                {p.author ? <Link to={`/contributors/${p.author}`}>{p.author}</Link> : "—"}
              </td>
              <td className="px-4 py-3 text-right text-text">
                {p.lead_time_hours >= 48
                  ? `${(p.lead_time_hours / 24).toFixed(1)}d`
                  : `${p.lead_time_hours.toFixed(1)}h`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
