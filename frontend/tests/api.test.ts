import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchDashboard } from "../src/api";
import type { DashboardSnapshot } from "../src/types";

const fetchMock = vi.fn<typeof fetch>();

const dashboardSnapshot: DashboardSnapshot = {
  generated_at: "2026-07-22T18:00:00Z",
  summary: {
    backends_total: 1,
    healthy_backends: 1,
    available_backends: 1,
    active_requests: 0,
    requests_total: 10,
    failures_total: 0,
    retries_total: 0,
    average_latency_ms: 12,
  },
  backends: [],
  recent_requests: [],
};

function jsonResponse(
  body: DashboardSnapshot,
  { ok = true, status = 200 }: { ok?: boolean; status?: number } = {},
): Response {
  return {
    json: vi.fn().mockResolvedValue(body),
    ok,
    status,
  } as unknown as Response;
}

describe("fetchDashboard", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests the dashboard endpoint with GET", async () => {
    fetchMock.mockResolvedValue(jsonResponse(dashboardSnapshot));

    await fetchDashboard();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/dashboard",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("requests a JSON response", async () => {
    fetchMock.mockResolvedValue(jsonResponse(dashboardSnapshot));

    await fetchDashboard();

    expect(fetchMock.mock.calls[0][1]?.headers).toEqual({
      Accept: "application/json",
    });
  });

  it("passes the provided abort signal to fetch", async () => {
    fetchMock.mockResolvedValue(jsonResponse(dashboardSnapshot));
    const controller = new AbortController();

    await fetchDashboard(controller.signal);

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it("returns the parsed dashboard snapshot", async () => {
    fetchMock.mockResolvedValue(jsonResponse(dashboardSnapshot));

    await expect(fetchDashboard()).resolves.toBe(dashboardSnapshot);
  });

  it("throws a useful error for an unsuccessful response", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(dashboardSnapshot, { ok: false, status: 503 }),
    );

    await expect(fetchDashboard()).rejects.toThrow(
      "Dashboard request failed with status 503",
    );
  });

  it("propagates request cancellation", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation((_input, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(init.signal?.reason),
          { once: true },
        );
      });
    });

    const request = fetchDashboard(controller.signal);
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
});
