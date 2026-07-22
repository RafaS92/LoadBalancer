import { useEffect, useState } from "react";

import { fetchDashboard } from "./api";
import type {
  BackendSnapshot,
  DashboardSnapshot,
  RecentRequest,
} from "./types";

const REFRESH_INTERVAL_MS = 5_000;

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function backendState(backend: BackendSnapshot): string {
  if (!backend.enabled) return "disabled";
  if (backend.draining) return backend.drained ? "drained" : "draining";
  return backend.healthy ? "healthy" : "unhealthy";
}

function BackendRow({ backend }: { backend: BackendSnapshot }) {
  const state = backendState(backend);

  return (
    <tr>
      <td>
        <div className="backend-name">
          <span className={`state-dot state-${state}`} aria-hidden="true" />
          <span>{backend.name}</span>
        </div>
        <span className="backend-url">{backend.url}</span>
      </td>
      <td>
        <span className={`state-label state-${state}`}>{state}</span>
      </td>
      <td className="numeric">{formatNumber(backend.active_requests)}</td>
      <td className="numeric">{formatNumber(backend.requests_total)}</td>
      <td className="numeric">{backend.average_latency_ms.toFixed(1)} ms</td>
      <td className="numeric">{formatNumber(backend.failures_total)}</td>
    </tr>
  );
}

function RequestRow({ request }: { request: RecentRequest }) {
  const successful = request.status < 400;

  return (
    <li className="request-row">
      <time dateTime={request.occurred_at}>{formatTime(request.occurred_at)}</time>
      <span className="method">{request.method}</span>
      <span className="request-path" title={request.path}>
        {request.path}
      </span>
      <span className={successful ? "status-ok" : "status-error"}>
        {request.status}
      </span>
      <span className="request-backend">{request.backend ?? "load balancer"}</span>
      <span className="numeric">{request.duration_ms.toFixed(1)} ms</span>
    </li>
  );
}

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
          <p className="eyebrow">Relay / operations surface</p>
          <h1>Traffic, at a glance.</h1>
        </div>
        <div className={`connection ${error ? "connection-error" : ""}`}>
          <span className="pulse" aria-hidden="true" />
          <span>{error ? "Connection interrupted" : "Live · 5s refresh"}</span>
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

          <section className="summary-grid" aria-label="Traffic summary">
            <article className="metric metric-primary">
              <span>Requests</span>
              <strong>{formatNumber(snapshot.summary.requests_total)}</strong>
              <small>Total observed</small>
            </article>
            <article className="metric">
              <span>Available</span>
              <strong>
                {snapshot.summary.available_backends}
                <i>/{snapshot.summary.backends_total}</i>
              </strong>
              <small>Backends accepting work</small>
            </article>
            <article className="metric">
              <span>Mean latency</span>
              <strong>{snapshot.summary.average_latency_ms.toFixed(1)}</strong>
              <small>Milliseconds</small>
            </article>
            <article className="metric">
              <span>Failures</span>
              <strong>{formatNumber(snapshot.summary.failures_total)}</strong>
              <small>{formatNumber(snapshot.summary.retries_total)} retries</small>
            </article>
          </section>

          <section className="panel backend-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Fleet state</p>
                <h2>Backends</h2>
              </div>
              <span>{snapshot.summary.active_requests} active now</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Backend</th>
                    <th>State</th>
                    <th className="numeric">Active</th>
                    <th className="numeric">Requests</th>
                    <th className="numeric">Latency</th>
                    <th className="numeric">Failures</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.backends.map((backend) => (
                    <BackendRow key={backend.name} backend={backend} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel requests-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Most recent first</p>
                <h2>Request stream</h2>
              </div>
              <time dateTime={snapshot.generated_at}>
                Updated {formatTime(snapshot.generated_at)}
              </time>
            </div>
            {snapshot.recent_requests.length ? (
              <ol className="request-list">
                {snapshot.recent_requests.map((request) => (
                  <RequestRow key={request.request_id} request={request} />
                ))}
              </ol>
            ) : (
              <p className="no-requests">Waiting for the first proxied request.</p>
            )}
          </section>
        </>
      ) : (
        <section className="loading" aria-live="polite">
          Reading current traffic…
        </section>
      )}
    </main>
  );
}
