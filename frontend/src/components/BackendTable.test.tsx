import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BackendSnapshot } from "../types";
import { BackendTable } from "./BackendTable";

const backends: BackendSnapshot[] = [
  {
    name: "backend-a",
    url: "http://127.0.0.1:9001",
    healthy: true,
    enabled: true,
    draining: false,
    drained: false,
    active_requests: 2,
    requests_total: 1_240,
    failures_total: 3,
    retries_total: 1,
    average_latency_ms: 12.46,
  },
  {
    name: "backend-b",
    url: "http://127.0.0.1:9002",
    healthy: true,
    enabled: false,
    draining: false,
    drained: false,
    active_requests: 0,
    requests_total: 800,
    failures_total: 4,
    retries_total: 2,
    average_latency_ms: 22,
  },
];

describe("BackendTable", () => {
  it("renders backend traffic and operator state", () => {
    render(<BackendTable activeRequests={2} backends={backends} />);

    expect(screen.getByText("2 active now")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();

    const healthyRow = screen.getByRole("row", { name: /backend-a/ });
    expect(within(healthyRow).getByText("backend-a")).toBeInTheDocument();
    expect(
      within(healthyRow).getByText("http://127.0.0.1:9001"),
    ).toBeInTheDocument();
    expect(within(healthyRow).getByText("healthy")).toBeInTheDocument();
    expect(within(healthyRow).getByText("2")).toBeInTheDocument();
    expect(within(healthyRow).getByText("1,240")).toBeInTheDocument();
    expect(within(healthyRow).getByText("12.5 ms")).toBeInTheDocument();
    expect(within(healthyRow).getByText("3")).toBeInTheDocument();

    const disabledRow = screen.getByRole("row", { name: /backend-b/ });
    expect(within(disabledRow).getByText("backend-b")).toBeInTheDocument();
    expect(within(disabledRow).getByText("disabled")).toBeInTheDocument();
    expect(within(disabledRow).getByText("0")).toBeInTheDocument();
    expect(within(disabledRow).getByText("800")).toBeInTheDocument();
    expect(within(disabledRow).getByText("22.0 ms")).toBeInTheDocument();
    expect(within(disabledRow).getByText("4")).toBeInTheDocument();
  });
});
