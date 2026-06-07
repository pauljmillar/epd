import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  useContributorsList,
  useReposList,
  useSyncStatus,
  useTeamsList,
} from "../api/client";

type SectionKey = "repos" | "teams" | "contributors";

function getStoredOpen(): Record<SectionKey, boolean> {
  try {
    const raw = sessionStorage.getItem("epd.sidebar-sections");
    if (raw) return JSON.parse(raw);
  } catch {
    /* */
  }
  return { repos: true, teams: true, contributors: false };
}

export function Sidebar({ appName }: { appName: string }) {
  const { data: sync } = useSyncStatus();
  const { data: repos } = useReposList();
  const { data: teams } = useTeamsList();
  const { data: contributors } = useContributorsList();
  const [open, setOpen] = useState<Record<SectionKey, boolean>>(getStoredOpen);

  const toggle = (k: SectionKey) => {
    const next = { ...open, [k]: !open[k] };
    setOpen(next);
    try {
      sessionStorage.setItem("epd.sidebar-sections", JSON.stringify(next));
    } catch {
      /* */
    }
  };

  const synced = sync?.completed_at ? new Date(sync.completed_at) : null;
  const status = sync?.status ?? "never_run";
  const failed =
    status === "failed" ||
    (synced && Date.now() - synced.getTime() > 25 * 60 * 60 * 1000);

  return (
    <aside className="w-[240px] shrink-0 bg-card border-r border-border h-screen flex flex-col">
      <div className="px-5 pt-5 pb-6">
        <div className="text-text font-bold text-base tracking-tight">{appName}</div>
      </div>

      <nav className="flex-1 px-2 overflow-y-auto">
        <NavItem to="/">Overview</NavItem>

        <SectionHeader
          label="Repos"
          count={repos?.repos.length}
          open={open.repos}
          onToggle={() => toggle("repos")}
          indexHref="/repos"
        />
        {open.repos &&
          (repos?.repos ?? []).slice(0, 30).map((r) => (
            <NavItem key={r.full_name} to={`/repos/${r.full_name}`} indent>
              {r.full_name.split("/").pop()}
            </NavItem>
          ))}

        <SectionHeader
          label="Teams"
          count={teams?.teams.length}
          open={open.teams}
          onToggle={() => toggle("teams")}
          indexHref="/teams"
        />
        {open.teams && (
          <>
            {(teams?.teams ?? []).map((t) => (
              <NavItem key={t.id} to={`/teams/${t.id}/view`} indent>
                {t.name}
              </NavItem>
            ))}
            {teams && teams.teams.length === 0 && (
              <div className="text-text-tertiary text-xs px-5 py-1">
                None yet —{" "}
                <NavLink to="/teams" className="underline">
                  create one
                </NavLink>
              </div>
            )}
          </>
        )}

        <SectionHeader
          label="Contributors"
          count={contributors?.contributors.length}
          open={open.contributors}
          onToggle={() => toggle("contributors")}
          indexHref="/contributors"
        />
        {open.contributors &&
          (contributors?.contributors ?? []).slice(0, 50).map((c) => (
            <NavItem key={c.login} to={`/contributors/${c.login}`} indent>
              {c.login}
            </NavItem>
          ))}

        <div className="mt-5 mb-1 px-3">
          <NavLink
            to="/sources"
            end
            className={({ isActive }) =>
              `text-[10px] font-semibold uppercase tracking-wider ${
                isActive ? "text-text" : "text-text-tertiary hover:text-text"
              }`
            }
          >
            Sources
          </NavLink>
        </div>
      </nav>

      <div className="border-t border-border p-3 text-xs text-text-secondary">
        <SyncIndicator status={status} synced={synced} failed={!!failed} />
      </div>
    </aside>
  );
}

function SectionHeader({
  label,
  count,
  open,
  onToggle,
  indexHref,
}: {
  label: string;
  count: number | undefined;
  open: boolean;
  onToggle: () => void;
  indexHref: string;
}) {
  return (
    <div className="mt-5 mb-1 flex items-center justify-between px-3">
      <NavLink
        to={indexHref}
        end
        className={({ isActive }) =>
          `text-[10px] font-semibold uppercase tracking-wider ${
            isActive ? "text-text" : "text-text-tertiary hover:text-text"
          }`
        }
      >
        {label}
        {count !== undefined && (
          <span className="ml-1.5 text-text-tertiary normal-case tracking-normal">
            {count}
          </span>
        )}
      </NavLink>
      <button
        onClick={onToggle}
        className="text-text-tertiary text-xs hover:text-text px-1"
        aria-label={open ? `Collapse ${label}` : `Expand ${label}`}
      >
        {open ? "−" : "+"}
      </button>
    </div>
  );
}

function NavItem({
  to,
  children,
  indent,
}: {
  to: string;
  children: React.ReactNode;
  indent?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `block py-1 text-sm rounded ${indent ? "px-5" : "px-3"} ${
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
