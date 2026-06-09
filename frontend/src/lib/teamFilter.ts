import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Reads and writes the global `?team=N` URL query param. Returns:
 *  - teamId: number | null  (null = "All teams")
 *  - setTeamId(id | null)   (writes/removes the param, preserves other search params)
 *
 * The URL is the single source of truth — no sessionStorage, no React context.
 */
export function useTeamFilter(): {
  teamId: number | null;
  setTeamId: (id: number | null) => void;
} {
  const [params, setParams] = useSearchParams();
  const raw = params.get("team");
  const parsed = raw && /^\d+$/.test(raw) ? Number(raw) : null;

  const setTeamId = useCallback(
    (id: number | null) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === null) next.delete("team");
          else next.set("team", String(id));
          return next;
        },
        { replace: false },
      );
    },
    [setParams],
  );

  return { teamId: parsed, setTeamId };
}

/**
 * Helper for building Link destinations that preserve the current ?team= param. Use this
 * when constructing in-app `<Link to={{...}}>` targets so the global team scope follows
 * the user across navigation.
 */
export function withTeamSearch(pathname: string, search: string): {
  pathname: string;
  search: string;
} {
  const incoming = new URLSearchParams(search);
  const team = incoming.get("team");
  const out = new URLSearchParams();
  if (team) out.set("team", team);
  return { pathname, search: out.toString() ? `?${out.toString()}` : "" };
}
