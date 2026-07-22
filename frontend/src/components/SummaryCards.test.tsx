import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DashboardSummary } from "../types";
import { SummaryCards } from "./SummaryCards";

describe("SummaryCards", () => {
  it("renders the dashboard traffic totals", () => {
    const summary: DashboardSummary = {
      backends_total: 3,
      healthy_backends: 2,
      available_backends: 2,
      active_requests: 5,
      requests_total: 1_234,
      failures_total: 7,
      retries_total: 4,
      average_latency_ms: 18.37,
    };

    render(<SummaryCards summary={summary} />);

    const cards = screen.getByRole("region", { name: "Traffic summary" });
    expect(within(cards).getAllByRole("article")).toHaveLength(4);
    expect(within(cards).getByText("1,234")).toBeInTheDocument();
    expect(within(cards).getByText("2")).toBeInTheDocument();
    expect(within(cards).getByText("/3")).toBeInTheDocument();
    expect(within(cards).getByText("18.4")).toBeInTheDocument();
    expect(within(cards).getByText("7")).toBeInTheDocument();
    expect(within(cards).getByText("4 retries")).toBeInTheDocument();
  });
});
