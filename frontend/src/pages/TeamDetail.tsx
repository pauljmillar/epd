import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTeamMetrics } from "../api/client";
import type { TeamMetrics } from "../api/types";
import { MetricsBody } from "../components/MetricsBody";
import { PageHeader } from "../components/PageHeader";

export function TeamDetail() {
  const { teamId } = useParams<{ teamId: string }>();
  const id = teamId ? Number(teamId) : undefined;
  const [period, setPeriod] = useState("90d");
  const { data, isLoading, error } = useTeamMetrics(id, period);

  return (
    <div>
      <div className="text-text-tertiary text-xs mb-2">
        <Link to="/" className="hover:text-text">Overview</Link>
        <span className="mx-2">›</span>
        <Link to="/teams" className="hover:text-text">Teams</Link>
        <span className="mx-2">›</span>
        <span className="text-text">{data?.team.name ?? `#${teamId}`}</span>
      </div>
      <PageHeader
        title={data?.team.name ?? `Team #${teamId}`}
        period={period}
        onPeriodChange={setPeriod}
      />

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

function Body({ data }: { data: TeamMetrics }) {
  return (
    <>
      <div className="bg-card border border-border rounded p-4 mb-6 text-sm">
        <div className="text-text-secondary mb-2">
          {data.team.members.length} members:
        </div>
        <div className="flex flex-wrap gap-1.5">
          {data.team.members.map((m) => (
            <Link
              key={m.login}
              to={`/contributors/${m.login}`}
              className="inline-block px-2 py-0.5 text-xs bg-active text-text rounded hover:border hover:border-text-tertiary"
            >
              {m.login}
            </Link>
          ))}
          {data.team.members.length === 0 && (
            <span className="text-text-tertiary text-xs">
              No members yet — add some from{" "}
              <Link to="/teams" className="underline">Teams admin</Link>.
            </span>
          )}
        </div>
      </div>

      <MetricsBody data={data} linkPrefix="/metrics" />

      <div className="grid grid-cols-2 gap-3 mb-6">
        <ListCard
          title="Repos touched"
          headers={["Repo", "PRs", "Lead Time"]}
          rows={data.repos.map((r) => ({
            key: r.full_name,
            href: `/repos/${r.full_name}`,
            cells: [
              r.full_name,
              String(r.prs_merged),
              fmtHours(r.lead_time_p50_hours),
            ],
          }))}
        />
        <ListCard
          title="Members breakdown"
          headers={["Contributor", "PRs", "Lead Time"]}
          rows={data.members_breakdown.map((m) => ({
            key: m.login,
            href: `/contributors/${m.login}`,
            cells: [m.login, String(m.prs_merged), fmtHours(m.lead_time_p50_hours)],
          }))}
        />
      </div>
    </>
  );
}

function ListCard({
  title,
  headers,
  rows,
}: {
  title: string;
  headers: string[];
  rows: { key: string; href: string; cells: string[] }[];
}) {
  return (
    <div className="bg-card border border-border rounded">
      <div className="px-4 py-3 border-b border-border text-text font-medium text-[13px]">
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="p-4 text-text-tertiary text-sm">No data</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-tertiary text-[11px] uppercase tracking-wider">
              {headers.map((h, i) => (
                <th
                  key={h}
                  className={`px-4 py-2 font-semibold ${i === 0 ? "text-left" : "text-right"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-border-subtle hover:bg-active">
                {r.cells.map((c, i) => (
                  <td
                    key={i}
                    className={`px-4 py-3 ${i === 0 ? "text-text" : "text-right text-text-secondary"}`}
                  >
                    {i === 0 ? <Link to={r.href}>{c}</Link> : c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function fmtHours(v: number | null): string {
  if (v === null) return "—";
  if (v >= 48) return `${(v / 24).toFixed(1)}d`;
  return `${v.toFixed(1)}h`;
}
