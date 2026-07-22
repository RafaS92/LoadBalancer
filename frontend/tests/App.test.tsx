import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { useDashboard } from "../src/hooks/useDashboard";
import type { DashboardSnapshot } from "../src/types";

vi.mock("../src/hooks/useDashboard", () => ({
  useDashboard: vi.fn(),
}));

const useDashboardMock = vi.mocked(useDashboard);

const dashboardSnapshot: DashboardSnapshot = {
  generated_at: "2026-07-22T18:00:00Z",
  summary: {
    backends_total: 1,
    healthy_backends: 1,
    available_backends: 1,
    active_requests: 2,
    requests_total: 250,
    failures_total: 3,
    retries_total: 1,
    average_latency_ms: 14.2,
  },
  backends: [
    {
      name: "backend-a",
      url: "http://127.0.0.1:9001",
      healthy: true,
      enabled: true,
      draining: false,
      drained: false,
      active_requests: 2,
      requests_total: 250,
      failures_total: 3,
      retries_total: 1,
      average_latency_ms: 14.2,
    },
  ],
  recent_requests: [
    {
      occurred_at: "2026-07-22T17:59:58Z",
      method: "GET",
      path: "/api/items",
      status: 200,
      backend: "backend-a",
      outcome: "completed",
      duration_ms: 12.5,
      request_id: "request-1",
    },
  ],
};

describe("App", () => {
  beforeEach(() => {
    useDashboardMock.mockReset();
  });

  it("renders a loading state before the first snapshot arrives", () => {
    useDashboardMock.mockReturnValue({ snapshot: null, error: null });

    render(<App />);

    expect(screen.getByText("Reading current traffic…")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("renders the initial error state when no snapshot is available", () => {
    useDashboardMock.mockReturnValue({
      snapshot: null,
      error: "Dashboard offline",
    });

    render(<App />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to reach the read API",
    );
    expect(screen.getByText("Connection interrupted")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Traffic summary" }),
    ).not.toBeInTheDocument();
  });

  it("assembles the summary, backend table, and request stream", () => {
    useDashboardMock.mockReturnValue({
      snapshot: dashboardSnapshot,
      error: null,
    });

    render(<App />);

    expect(
      screen.getByRole("region", { name: "Traffic summary" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Request stream" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("backend-a")).toHaveLength(2);
    expect(screen.getByText("/api/items")).toBeInTheDocument();
  });

  it("keeps the last snapshot visible when a refresh fails", () => {
    useDashboardMock.mockReturnValue({
      snapshot: dashboardSnapshot,
      error: "Temporary failure",
    });

    render(<App />);

    expect(
      screen.getByText("Showing the last successful snapshot."),
    ).toBeInTheDocument();
    expect(screen.getByText("Connection interrupted")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Traffic summary" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("/api/items")).toBeInTheDocument();
  });
});
