import { useQuery } from "@tanstack/react-query";
import type { OrgMetrics, SyncStatus } from "./types";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export function useOrgMetrics(period: string) {
  return useQuery({
    queryKey: ["org", period],
    queryFn: () => get<OrgMetrics>(`/api/v1/metrics/org?period=${period}`),
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: () => get<SyncStatus>("/api/v1/sync/status"),
    refetchInterval: 30_000,
  });
}
