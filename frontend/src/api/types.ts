export type BadDirection = "up" | "down" | null;

export interface Kpi {
  value: number | null;
  unit: string;
  delta_pct: number | null;
  bad_direction: BadDirection;
  p75?: number | null;
}

export interface OrgMetrics {
  period: string;
  range: { start: string; end: string };
  kpis: {
    deployment_frequency: Kpi;
    lead_time_p50: Kpi;
    pr_throughput: Kpi;
  };
  series: {
    deployment_frequency: { week: string; value: number }[];
    lead_time: { week: string; p50: number | null; p75: number | null }[];
    pr_throughput: { week: string; value: number }[];
  };
  teams: {
    name: string;
    prs_merged: number;
    throughput_per_week: number;
    deploy_per_week: number;
    lead_time_p50_hours: number | null;
  }[];
}

export interface SyncStatus {
  status: string;
  started_at?: string;
  completed_at?: string | null;
  repos_synced?: number;
  prs_synced?: number;
  error?: string | null;
}
