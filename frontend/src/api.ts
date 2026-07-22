import type { DashboardSnapshot } from "./types";

const DASHBOARD_ENDPOINT = "/api/v1/dashboard";

export async function fetchDashboard(
  signal?: AbortSignal,
): Promise<DashboardSnapshot> {
  const response = await fetch(DASHBOARD_ENDPOINT, {
    headers: { Accept: "application/json" },
    method: "GET",
    signal,
  });

  if (!response.ok) {
    throw new Error(`Dashboard request failed with status ${response.status}`);
  }

  return (await response.json()) as DashboardSnapshot;
}
