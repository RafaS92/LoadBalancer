import { formatNumber } from "../formatters";
import type { DashboardSummary } from "../types";

interface SummaryCardsProps {
  summary: DashboardSummary;
}

export function SummaryCards({ summary }: SummaryCardsProps) {
  return (
    <section className="summary-grid" aria-label="Traffic summary">
      <article className="metric metric-primary">
        <span>Requests</span>
        <strong>{formatNumber(summary.requests_total)}</strong>
        <small>Total observed</small>
      </article>
      <article className="metric">
        <span>Available</span>
        <strong>
          {summary.available_backends}
          <i>/{summary.backends_total}</i>
        </strong>
        <small>Backends accepting work</small>
      </article>
      <article className="metric">
        <span>Mean latency</span>
        <strong>{summary.average_latency_ms.toFixed(1)}</strong>
        <small>Milliseconds</small>
      </article>
      <article className="metric">
        <span>Failures</span>
        <strong>{formatNumber(summary.failures_total)}</strong>
        <small>{formatNumber(summary.retries_total)} retries</small>
      </article>
    </section>
  );
}
