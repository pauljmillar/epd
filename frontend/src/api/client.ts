import { useQuery } from "@tanstack/react-query";
import type { OrgMetrics, SyncStatus } from "./types";

// In dev (no VITE_API_URL), use the Vite proxy ("/api/..."). In production builds, prefix
// every request with the absolute backend URL (Railway, etc.).
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

const TOKEN_KEY = "epd.bearer";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(t: string | null): void {
  try {
    if (t === null) sessionStorage.removeItem(TOKEN_KEY);
    else sessionStorage.setItem(TOKEN_KEY, t);
  } catch {
    /* sessionStorage unavailable — fine, user'll re-enter */
  }
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (r.status === 401) {
    setToken(null);
    throw new AuthError();
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export class AuthError extends Error {
  constructor() {
    super("Authentication required");
    this.name = "AuthError";
  }
}

export interface Health {
  status: string;
  app_name: string;
  github_configured: boolean;
  auth_required: boolean;
}

export async function fetchHealth(): Promise<Health> {
  const r = await fetch(`${API_BASE}/api/v1/health`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function verifyToken(token: string): Promise<boolean> {
  const r = await fetch(`${API_BASE}/api/v1/auth/check`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.ok;
}

export function useOrgMetrics(period: string) {
  return useQuery({
    queryKey: ["org", period],
    queryFn: () => get<OrgMetrics>(`/api/v1/metrics/org?period=${period}`),
  });
}

export function useTeamMetrics(teamName: string | undefined, period: string) {
  return useQuery({
    queryKey: ["team", teamName, period],
    enabled: !!teamName,
    queryFn: () =>
      get<import("./types").TeamMetrics>(
        `/api/v1/metrics/team/${encodeURIComponent(teamName!)}?period=${period}`,
      ),
  });
}

export function useContributorMetrics(login: string | undefined, period: string) {
  return useQuery({
    queryKey: ["contributor", login, period],
    enabled: !!login,
    queryFn: () =>
      get<import("./types").ContributorMetrics>(
        `/api/v1/metrics/contributor/${encodeURIComponent(login!)}?period=${period}`,
      ),
  });
}

export function useTeamsList() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: () => get<{ teams: { name: string; prs_merged_90d: number }[] }>(
      "/api/v1/metrics/teams",
    ),
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: () => get<SyncStatus>("/api/v1/sync/status"),
    refetchInterval: 30_000,
  });
}
