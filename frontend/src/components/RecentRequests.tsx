import { formatTime } from "../formatters";
import type { RecentRequest } from "../types";

interface RecentRequestsProps {
  generatedAt: string;
  requests: RecentRequest[];
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

export function RecentRequests({ generatedAt, requests }: RecentRequestsProps) {
  return (
    <section className="panel requests-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Most recent first</p>
          <h2>Request stream</h2>
        </div>
        <time dateTime={generatedAt}>Updated {formatTime(generatedAt)}</time>
      </div>
      {requests.length ? (
        <ol className="request-list">
          {requests.map((request) => (
            <RequestRow key={request.request_id} request={request} />
          ))}
        </ol>
      ) : (
        <p className="no-requests">Waiting for the first proxied request.</p>
      )}
    </section>
  );
}
