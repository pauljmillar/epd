import { useEffect, useRef, useState } from "react";
import { useTeamsList } from "../api/client";
import { useTeamFilter } from "../lib/teamFilter";

/**
 * Global team filter — sits in PageHeader on Org Overview / Metric Detail / Repo Detail.
 * Reads/writes the URL `?team=N` param via useTeamFilter.
 */
export function TeamFilterSelect() {
  const { teamId, setTeamId } = useTeamFilter();
  const { data } = useTeamsList();
  const teams = data?.teams ?? [];
  const selected = teams.find((t) => t.id === teamId);

  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Active = team filter applied. Style: pill with team name + clear (×).
  if (teamId !== null && selected) {
    return (
      <span className="inline-flex items-center gap-1.5 border border-text rounded px-2.5 py-1 text-xs">
        <span className="text-text-tertiary uppercase tracking-wider">Viewing</span>
        <span className="text-text font-medium">{selected.name}</span>
        <button
          type="button"
          onClick={() => setTeamId(null)}
          className="text-text-tertiary hover:text-text"
          aria-label="Clear team filter"
        >
          ×
        </button>
      </span>
    );
  }

  // Stale team id (URL has ?team=N but team is gone): treat as "no team" and clear.
  if (teamId !== null && !selected && teams.length > 0) {
    // Defer to a microtask so we don't setState during render.
    queueMicrotask(() => setTeamId(null));
  }

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="border border-border rounded px-3 py-1.5 text-xs text-text-secondary hover:text-text"
        aria-expanded={open}
      >
        All teams ▾
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 bg-card border border-border rounded shadow-lg z-50">
          <ul className="max-h-72 overflow-y-auto">
            <li>
              <button
                type="button"
                onClick={() => {
                  setTeamId(null);
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-xs text-text-secondary hover:bg-active hover:text-text"
              >
                All teams
              </button>
            </li>
            {teams.length === 0 && (
              <li className="px-3 py-2 text-xs text-text-tertiary">
                No teams configured.
              </li>
            )}
            {teams.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => {
                    setTeamId(t.id);
                    setOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-xs text-text hover:bg-active"
                >
                  {t.name}
                  <span className="ml-2 text-text-tertiary">
                    ({t.members} member{t.members === 1 ? "" : "s"})
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
