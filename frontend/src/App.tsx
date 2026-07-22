import { useEffect, useState } from "react";

import { fetchDashboard } from "./api";
import { BackendTable } from "./components/BackendTable";
import { RecentRequests } from "./components/RecentRequests";
import { SummaryCards } from "./components/SummaryCards";
import type { DashboardSnapshot } from "./types";

const REFRESH_INTERVAL_MS = 5_000;

export function App() {
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
    const interval = window.setInterval(refresh, REFRESH_INTERVAL_MS);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  return (
    <main>
      <header className="masthead">
        <div>
          <h1>Traffic, at a glance.</h1>
        </div>
        <div className={`connection ${error ? "connection-error" : ""}`}>
          <span className="pulse" aria-hidden="true" />
          <span>{error ? "Connection interrupted" : "Live"}</span>
        </div>
      </header>

      {error && !snapshot ? (
        <section className="empty-state" role="alert">
          <p className="eyebrow">Unable to reach the read API</p>
          <h2>Start the load balancer on port 8080.</h2>
          <code>load-balancer</code>
        </section>
      ) : snapshot ? (
        <>
          {error && <p className="stale-warning">Showing the last successful snapshot.</p>}

          <SummaryCards summary={snapshot.summary} />
          <BackendTable
            activeRequests={snapshot.summary.active_requests}
            backends={snapshot.backends}
          />
          <RecentRequests
            generatedAt={snapshot.generated_at}
            requests={snapshot.recent_requests}
          />
        </>
      ) : (
        <section className="loading" aria-live="polite">
          Reading current traffic…
        </section>
      )}
    </main>
  );
}
