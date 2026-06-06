import { NavLink } from "react-router-dom";
import { useSyncStatus, useTeamsList } from "../api/client";

export function Sidebar({ appName }: { appName: string }) {
  const { data: sync } = useSyncStatus();
  const { data: teams } = useTeamsList();
  const synced = sync?.completed_at ? new Date(sync.completed_at) : null;
  const status = sync?.status ?? "never_run";
  const failed =
    status === "failed" ||
    (synced && Date.now() - synced.getTime() > 25 * 60 * 60 * 1000);

  return (
    <aside className="w-[220px] shrink-0 bg-card border-r border-border h-screen flex flex-col">
      <div className="px-5 pt-5 pb-6">
        <div className="text-text font-bold text-base tracking-tight">{appName}</div>
      </div>

      <nav className="flex-1 px-2 overflow-y-auto">
        <NavItem to="/">Overview</NavItem>

        <div className="text-text-tertiary text-[10px] font-semibold uppercase tracking-wider px-3 mt-6 mb-2">
          Teams
        </div>
        {(teams?.teams ?? []).slice(0, 30).map((t) => (
          <NavItem key={t.name} to={`/teams/${t.name}`}>
            {t.name.split("/").pop()}
          </NavItem>
        ))}
        {teams && teams.teams.length === 0 && (
          <div className="text-text-tertiary text-xs px-3 py-2">
            (waiting on first sync)
          </div>
        )}
      </nav>

      <div className="border-t border-border p-3 text-xs text-text-secondary">
        <SyncIndicator status={status} synced={synced} failed={!!failed} />
      </div>
    </aside>
  );
}

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `block px-3 py-1.5 text-sm rounded ${
          isActive
            ? "bg-active text-text border-l-2 border-text"
            : "text-text-secondary hover:text-text"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

function SyncIndicator({
  status,
  synced,
  failed,
}: {
  status: string;
  synced: Date | null;
  failed: boolean;
}) {
  let label = "Never synced";
  if (status === "running") label = "Syncing…";
  else if (synced) label = `Synced ${relTime(synced)}`;
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-block w-2 h-2 rounded-full ${
          failed ? "bg-alert" : "bg-text-tertiary"
        }`}
      />
      <span className={failed ? "text-alert" : ""}>{label}</span>
    </div>
  );
}

function relTime(d: Date): string {
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
