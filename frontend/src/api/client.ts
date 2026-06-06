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

export function useRepoMetrics(repoFullName: string | undefined, period: string) {
  return useQuery({
    queryKey: ["repo", repoFullName, period],
    enabled: !!repoFullName,
    queryFn: () =>
      get<import("./types").RepoMetrics>(
        `/api/v1/metrics/repo/${repoFullName}?period=${period}`,
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

export function useReposList() {
  return useQuery({
    queryKey: ["repos"],
    queryFn: () =>
      get<{ repos: { full_name: string; prs_merged_90d: number }[] }>(
        "/api/v1/metrics/repos",
      ),
  });
}

export function useContributorsList() {
  return useQuery({
    queryKey: ["contributors-list"],
    queryFn: () =>
      get<{ contributors: import("./types").ContributorListItem[] }>(
        "/api/v1/metrics/contributors?limit=200",
      ),
  });
}

export function useTeamsList() {
  return useQuery({
    queryKey: ["teams-list"],
    queryFn: () =>
      get<{ teams: import("./types").TeamSummary[] }>("/api/v1/teams"),
  });
}

export function useTeamMetrics(teamId: number | undefined, period: string) {
  return useQuery({
    queryKey: ["team", teamId, period],
    enabled: teamId !== undefined,
    queryFn: () =>
      get<import("./types").TeamMetrics>(
        `/api/v1/teams/${teamId}/metrics?period=${period}`,
      ),
  });
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const t = getToken();
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

async function del(path: string): Promise<void> {
  const t = getToken();
  const r = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: t ? { Authorization: `Bearer ${t}` } : {},
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
}

export async function createTeam(name: string) {
  return postJson<{ id: number; name: string; members: number }>("/api/v1/teams", { name });
}

export async function deleteTeam(id: number) {
  await del(`/api/v1/teams/${id}`);
}

export async function addTeamMember(teamId: number, login: string) {
  return postJson<{ ok: true }>(`/api/v1/teams/${teamId}/members`, { login });
}

export async function removeTeamMember(teamId: number, login: string) {
  await del(`/api/v1/teams/${teamId}/members/${encodeURIComponent(login)}`);
}

export async function getTeamMembers(teamId: number) {
  const r = await fetch(`${API_BASE}/api/v1/teams/${teamId}/members`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()!}` } : {},
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{
    team: { id: number; name: string };
    members: import("./types").TeamMember[];
  }>;
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: () => get<SyncStatus>("/api/v1/sync/status"),
    refetchInterval: 30_000,
  });
}
