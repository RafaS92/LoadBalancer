import { BackendTable } from "./components/BackendTable";
import { RecentRequests } from "./components/RecentRequests";
import { SummaryCards } from "./components/SummaryCards";
import { useDashboard } from "./hooks/useDashboard";

export function App() {
  const { snapshot, error } = useDashboard();

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
