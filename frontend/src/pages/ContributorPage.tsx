import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useContributorMetrics } from "../api/client";
import type { ContributorMetrics } from "../api/types";
import { PageHeader } from "../components/PageHeader";

function fmtHours(v: number | null): string {
  if (v === null) return "—";
  if (v >= 48) return `${(v / 24).toFixed(1)}d`;
  return `${v.toFixed(1)}h`;
}

function fmtPct(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(0)}%`;
}

function fmtLines(v: number | null): string {
  return v === null ? "—" : `${Math.round(v)} L`;
}

export function ContributorPage() {
  const { login } = useParams<{ login: string }>();
  const [period, setPeriod] = useState("30d");
  const { data, isLoading, error } = useContributorMetrics(login, period);

  return (
    <div>
      <div className="text-text-tertiary text-xs mb-2">
        <Link to="/" className="hover:text-text">Overview</Link>
        <span className="mx-2">›</span>
        <span className="text-text">{login}</span>
      </div>
      <PageHeader title={login ?? ""} period={period} onPeriodChange={setPeriod} />

      <div className="bg-card border border-border rounded p-4 mb-6 text-sm text-text-secondary">
        ⓘ <strong className="text-text">This view is for context, not evaluation.</strong>{" "}
        Individual metrics reflect project complexity, team structure, and seniority — not
        individual worth. Per BRD §12, EPD does not produce composite productivity scores or
        rankings.
      </div>

      {error && (
        <div className="bg-card border border-alert text-alert p-4 rounded mb-4 text-sm">
          {String(error)}
        </div>
      )}
      {isLoading && <div className="text-text-secondary text-sm">Loading…</div>}
      {data && <Body data={data} />}
    </div>
  );
}

function Body({ data }: { data: ContributorMetrics }) {
  const k = data.kpis;
  const tm = data.team_median;
  const rows = [
    {
      label: "PRs merged",
      cur: data.counts.merged_prs,
      team: tm.prs_merged,
      fmt: (v: number) => String(v),
    },
    {
      label: "Lead Time (P50)",
      cur: k.lead_time_p50.value,
      team: tm.lead_time_p50_hours,
      fmt: fmtHours,
    },
    {
      label: "PR Cycle Time",
      cur: k.pr_cycle_time.value,
      team: tm.pr_cycle_time_hours,
      fmt: fmtHours,
    },
    {
      label: "PR Size",
      cur: k.pr_size.value,
      team: tm.median_pr_size_lines,
      fmt: fmtLines,
    },
    {
      label: "Review Coverage",
      cur: k.review_coverage.value,
      team: tm.review_coverage_pct,
      fmt: fmtPct,
    },
    {
      label: "Time to First Review",
      cur: k.time_to_first_review.value,
      team: tm.time_to_first_review_hours,
      fmt: fmtHours,
    },
  ];

  return (
    <>
      <div className="bg-card border border-border rounded mb-6">
        <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
          Stats vs team median (period: {data.period}, {tm.prs_merged} team PRs)
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-semibold">Metric</th>
              <th className="text-right px-4 py-2 font-semibold">{data.contributor.login}</th>
              <th className="text-right px-4 py-2 font-semibold">Team median</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-border-subtle">
                <td className="px-4 py-3 text-text">{r.label}</td>
                <td className="px-4 py-3 text-right text-text">
                  {r.cur === null ? "—" : r.fmt(r.cur as number)}
                </td>
                <td className="px-4 py-3 text-right text-text-secondary">
                  {r.team === null ? "—" : r.fmt(r.team as number)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-card border border-border rounded mb-6">
        <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
          Recent PRs — last {data.recent_prs.length}
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              <th className="text-left px-4 py-2 font-semibold">PR</th>
              <th className="text-left px-4 py-2 font-semibold">Repo</th>
              <th className="text-left px-4 py-2 font-semibold">Merged</th>
              <th className="text-right px-4 py-2 font-semibold">Lines</th>
              <th className="text-right px-4 py-2 font-semibold">Lead Time</th>
              <th className="text-center px-4 py-2 font-semibold">AI</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_prs.map((p) => (
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
                  {p.merged_at ? p.merged_at.slice(0, 10) : "—"}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {p.additions + p.deletions}
                </td>
                <td className="px-4 py-3 text-right text-text">
                  {p.lead_time_hours === null ? "—" : fmtHours(p.lead_time_hours)}
                </td>
                <td className="px-4 py-3 text-center text-text-secondary">
                  {p.ai_assisted ? (p.ai_tool ?? "yes") : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
