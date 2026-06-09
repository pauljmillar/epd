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

export function useOrgMetrics(period: string, teamId?: number | null) {
  const suffix = teamId != null ? `&team=${teamId}` : "";
  return useQuery({
    queryKey: ["org", period, teamId ?? null],
    queryFn: () => get<OrgMetrics>(`/api/v1/metrics/org?period=${period}${suffix}`),
  });
}

export function useRepoMetrics(
  repoFullName: string | undefined,
  period: string,
  teamId?: number | null,
) {
  const suffix = teamId != null ? `&team=${teamId}` : "";
  return useQuery({
    queryKey: ["repo", repoFullName, period, teamId ?? null],
    enabled: !!repoFullName,
    queryFn: () =>
      get<import("./types").RepoMetrics>(
        `/api/v1/metrics/repo/${repoFullName}?period=${period}${suffix}`,
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

// --- Admin: is_tracked toggles -----------------------------------------------

export interface AdminRepo {
  full_name: string;
  is_tracked: boolean;
  prs_merged_total: number;
}

export interface AdminContributor {
  login: string;
  display_name: string;
  is_tracked: boolean;
  prs_merged_total: number;
}

export function useAdminRepos() {
  return useQuery({
    queryKey: ["admin-repos"],
    queryFn: () => get<{ repos: AdminRepo[] }>("/api/v1/admin/repos"),
  });
}

export function useAdminContributors() {
  return useQuery({
    queryKey: ["admin-contributors"],
    queryFn: () =>
      get<{ contributors: AdminContributor[] }>("/api/v1/admin/contributors"),
  });
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const t = getToken();
  const r = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export async function setRepoTracked(fullName: string, isTracked: boolean) {
  // fullName may contain a slash; the backend route is :path
  return patchJson<{ full_name: string; is_tracked: boolean }>(
    `/api/v1/admin/repos/${fullName}`,
    { is_tracked: isTracked },
  );
}

export async function setContributorTracked(login: string, isTracked: boolean) {
  return patchJson<{ login: string; is_tracked: boolean }>(
    `/api/v1/admin/contributors/${encodeURIComponent(login)}`,
    { is_tracked: isTracked },
  );
}

// --- Admin: data_sources -----------------------------------------------------

export interface DataSource {
  id: number;
  source: "github" | "gitlab";
  org_or_group: string;
  is_active: boolean;
  created_at: string | null;
  last_synced_at: string | null;
  repo_count: number;
  pr_count: number;
  token_preview: string;
}

export function useDataSources() {
  return useQuery({
    queryKey: ["data-sources"],
    queryFn: () => get<{ sources: DataSource[] }>("/api/v1/admin/sources"),
  });
}

export async function createDataSource(input: {
  source: "github" | "gitlab";
  org_or_group: string;
  token: string;
}): Promise<DataSource> {
  return postJson("/api/v1/admin/sources", input);
}

export async function updateDataSource(
  id: number,
  patch: { token?: string; is_active?: boolean },
): Promise<DataSource> {
  return patchJson(`/api/v1/admin/sources/${id}`, patch);
}

export async function softRemoveDataSource(id: number): Promise<void> {
  await del(`/api/v1/admin/sources/${id}`);
}

export async function purgeDataSource(id: number): Promise<{ deleted_repos: number }> {
  return postJson(`/api/v1/admin/sources/${id}/purge`, {});
}

export async function syncDataSource(id: number): Promise<{ status: string; repos_synced?: number; prs_synced?: number }> {
  return postJson(`/api/v1/admin/sources/${id}/sync`, {});
}

export async function replaceDataSources(input: {
  source: "github" | "gitlab";
  org_or_group: string;
  token: string;
}): Promise<DataSource & { soft_removed_source_ids: number[] }> {
  return postJson("/api/v1/admin/sources/replace", input);
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: () => get<SyncStatus>("/api/v1/sync/status"),
    // Tight cadence while a sync is in progress so the UI feels live; relax to 30s when
    // idle.
    refetchInterval: (q) => (q.state.data?.status === "running" ? 3_000 : 30_000),
  });
}

export async function cancelSync(): Promise<{
  ok: boolean;
  sync_log_id: number;
  already_requested?: boolean;
}> {
  return postJson("/api/v1/sync/cancel", {});
}
