import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecentRequests } from "../../src/components/RecentRequests";
import type { RecentRequest } from "../../src/types";

const generatedAt = "2026-07-22T18:00:00Z";
const requests: RecentRequest[] = [
  {
    occurred_at: "2026-07-22T17:59:58Z",
    method: "GET",
    path: "/api/items",
    status: 200,
    backend: "backend-a",
    outcome: "completed",
    duration_ms: 14.27,
    request_id: "request-1",
  },
  {
    occurred_at: "2026-07-22T17:59:54Z",
    method: "GET",
    path: "/api/failure",
    status: 502,
    backend: null,
    outcome: "backend_response_failed",
    duration_ms: 80.04,
    request_id: "request-2",
  },
];

describe("RecentRequests", () => {
  it("renders the latest requests and their outcomes", () => {
    render(<RecentRequests generatedAt={generatedAt} requests={requests} />);

    const updatedAt = screen.getByText(/^Updated /);
    expect(updatedAt).toHaveAttribute("datetime", generatedAt);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("/api/items")).toBeInTheDocument();
    expect(screen.getByText("200")).toHaveClass("status-ok");
    expect(screen.getByText("backend-a")).toBeInTheDocument();
    expect(screen.getByText("/api/failure")).toBeInTheDocument();
    expect(screen.getByText("502")).toHaveClass("status-error");
    expect(screen.getByText("load balancer")).toBeInTheDocument();
  });

  it("renders an empty state when no requests have completed", () => {
    render(<RecentRequests generatedAt={generatedAt} requests={[]} />);

    expect(
      screen.getByText("Waiting for the first proxied request."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
