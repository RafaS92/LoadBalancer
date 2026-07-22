import { formatNumber } from "../formatters";
import type { BackendSnapshot } from "../types";

interface BackendTableProps {
  activeRequests: number;
  backends: BackendSnapshot[];
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

export function BackendTable({ activeRequests, backends }: BackendTableProps) {
  return (
    <section className="panel backend-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Fleet state</p>
          <h2>Backends</h2>
        </div>
        <span>{activeRequests} active now</span>
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
            {backends.map((backend) => (
              <BackendRow key={backend.name} backend={backend} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
