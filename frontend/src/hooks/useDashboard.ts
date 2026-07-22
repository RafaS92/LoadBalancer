import { useEffect, useState } from "react";

import { fetchDashboard } from "../api";
import type { DashboardSnapshot } from "../types";

export const DASHBOARD_REFRESH_INTERVAL_MS = 5_000;

interface DashboardState {
  error: string | null;
  snapshot: DashboardSnapshot | null;
}

export function useDashboard(): DashboardState {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function refresh() {
      try {
        const nextSnapshot = await fetchDashboard(controller.signal);
        setSnapshot(nextSnapshot);
        setError(null);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Dashboard unavailable");
      }
    }

    void refresh();
    const interval = window.setInterval(
      refresh,
      DASHBOARD_REFRESH_INTERVAL_MS,
    );

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  return { snapshot, error };
}
