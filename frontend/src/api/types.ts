export type BadDirection = "up" | "down" | null;

export interface Kpi {
  value: number | null;
  unit: string;
  delta_pct: number | null;
  bad_direction: BadDirection;
  p75?: number | null;
  red_when_above?: number;
  phases?: {
    pickup_p50: number | null;
    review_p50: number | null;
    merge_p50: number | null;
  };
  /** AI tool name → PR count (only on the ai_assisted KPI). */
  tools?: Record<string, number>;
}

export interface OrgMetrics {
  period: string;
  range: { start: string; end: string };
  config: { large_pr_threshold: number };
  counts: { merged_prs: number; deployments: number; large_prs: number };
  kpis: {
    deployment_frequency: Kpi;
    lead_time_p50: Kpi;
    pr_throughput: Kpi;
    pr_cycle_time: Kpi;
    pr_size: Kpi;
    review_coverage: Kpi;
    time_to_first_review: Kpi;
    ai_assisted: Kpi;
  };
  series: {
    deployment_frequency: { week: string; value: number }[];
    lead_time: { week: string; p50: number | null; p75: number | null }[];
    pr_throughput: { week: string; value: number }[];
    pr_cycle_time: {
      week: string;
      pickup: number | null;
      review: number | null;
      merge: number | null;
    }[];
    pr_size: { week: string; value: number | null }[];
    review_coverage: { week: string; value: number | null }[];
    time_to_first_review: { week: string; value: number | null }[];
    ai_assisted: { week: string; value: number | null }[];
  };
  repos: {
    full_name: string;
    prs_merged: number;
    throughput_per_week: number;
    deploy_per_week: number;
    lead_time_p50_hours: number | null;
    pr_cycle_time_hours: number | null;
    median_pr_size_lines: number | null;
    review_coverage_pct: number | null;
    time_to_first_review_hours: number | null;
    ai_assisted_pct: number | null;
  }[];
  notable_prs?: { lead_time: NotablePR[] };
}

export interface SyncStatus {
  status: string;
  started_at?: string;
  completed_at?: string | null;
  repos_synced?: number;
  prs_synced?: number;
  error?: string | null;
}

export interface NotablePR {
  number: number;
  title: string;
  url: string;
  repo: string;
  author: string | null;
  lead_time_hours: number;
}

export interface BaseMetrics {
  period: string;
  range: { start: string; end: string };
  config: { large_pr_threshold: number };
  counts: { merged_prs: number; deployments: number; large_prs: number };
  kpis: OrgMetrics["kpis"];
  series: OrgMetrics["series"];
  notable_prs?: { lead_time: NotablePR[] };
}

export interface RepoMetrics extends BaseMetrics {
  repo: { full_name: string };
  contributors: {
    login: string;
    prs_merged: number;
    throughput_per_week: number;
    lead_time_p50_hours: number | null;
    pr_cycle_time_hours: number | null;
    median_pr_size_lines: number | null;
    review_coverage_pct: number | null;
    time_to_first_review_hours: number | null;
    ai_assisted_pct: number | null;
  }[];
}

export interface TeamSummary {
  id: number;
  name: string;
  members: number;
}

export interface TeamMember {
  login: string;
  display_name: string;
}

export interface TeamMetrics extends BaseMetrics {
  team: { id: number; name: string; members: TeamMember[] };
  repos: { full_name: string; prs_merged: number; throughput_per_week: number; lead_time_p50_hours: number | null }[];
  members_breakdown: {
    login: string;
    prs_merged: number;
    throughput_per_week: number;
    lead_time_p50_hours: number | null;
  }[];
}

export interface ContributorListItem {
  login: string;
  display_name: string;
  prs_merged_90d: number;
}

export interface RecentPR {
  number: number;
  title: string;
  url: string;
  repo: string;
  merged_at: string | null;
  additions: number;
  deletions: number;
  lead_time_hours: number | null;
  ai_assisted: boolean;
  ai_tool: string | null;
}

export interface ContributorMetrics extends BaseMetrics {
  contributor: { login: string };
  team_median: {
    lead_time_p50_hours: number | null;
    pr_cycle_time_hours: number | null;
    median_pr_size_lines: number | null;
    review_coverage_pct: number | null;
    time_to_first_review_hours: number | null;
    prs_merged: number;
  };
  recent_prs: RecentPR[];
}
