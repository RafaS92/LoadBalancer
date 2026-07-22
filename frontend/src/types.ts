export interface DashboardSummary {
  backends_total: number;
  healthy_backends: number;
  available_backends: number;
  active_requests: number;
  requests_total: number;
  failures_total: number;
  retries_total: number;
  average_latency_ms: number;
}

export interface BackendSnapshot {
  name: string;
  url: string;
  healthy: boolean;
  enabled: boolean;
  draining: boolean;
  drained: boolean;
  active_requests: number;
  requests_total: number;
  failures_total: number;
  retries_total: number;
  average_latency_ms: number;
}

export interface RecentRequest {
  occurred_at: string;
  method: string;
  path: string;
  status: number;
  backend: string | null;
  outcome: string;
  duration_ms: number;
  request_id: string;
}

export interface DashboardSnapshot {
  generated_at: string;
  summary: DashboardSummary;
  backends: BackendSnapshot[];
  recent_requests: RecentRequest[];
}
