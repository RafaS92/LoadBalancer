import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchDashboard } from "../api";
import type { DashboardSnapshot } from "../types";
import {
  DASHBOARD_REFRESH_INTERVAL_MS,
  useDashboard,
} from "./useDashboard";

vi.mock("../api", () => ({
  fetchDashboard: vi.fn(),
}));

const fetchDashboardMock = vi.mocked(fetchDashboard);

function snapshot(requestsTotal: number): DashboardSnapshot {
  return {
    generated_at: "2026-07-22T18:00:00Z",
    summary: {
      backends_total: 3,
      healthy_backends: 3,
      available_backends: 3,
      active_requests: 0,
      requests_total: requestsTotal,
      failures_total: 0,
      retries_total: 0,
      average_latency_ms: 12,
    },
    backends: [],
    recent_requests: [],
  };
}

async function flushRequest(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useDashboard", () => {
  beforeEach(() => {
    fetchDashboardMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads the initial dashboard snapshot", async () => {
    const initialSnapshot = snapshot(10);
    fetchDashboardMock.mockResolvedValue(initialSnapshot);

    const { result } = renderHook(() => useDashboard());

    await waitFor(() => expect(result.current.snapshot).toBe(initialSnapshot));
    expect(result.current.error).toBeNull();
    expect(fetchDashboardMock).toHaveBeenCalledTimes(1);
    expect(fetchDashboardMock.mock.calls[0][0]).toBeInstanceOf(AbortSignal);
  });

  it("reports an API failure", async () => {
    fetchDashboardMock.mockRejectedValue(new Error("Dashboard offline"));

    const { result } = renderHook(() => useDashboard());

    await waitFor(() =>
      expect(result.current.error).toBe("Dashboard offline"),
    );
    expect(result.current.snapshot).toBeNull();
  });

  it("refreshes the snapshot on the configured interval", async () => {
    vi.useFakeTimers();
    const initialSnapshot = snapshot(10);
    const refreshedSnapshot = snapshot(25);
    fetchDashboardMock
      .mockResolvedValueOnce(initialSnapshot)
      .mockResolvedValueOnce(refreshedSnapshot);

    const { result } = renderHook(() => useDashboard());
    await flushRequest();
    expect(result.current.snapshot).toBe(initialSnapshot);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DASHBOARD_REFRESH_INTERVAL_MS);
    });

    expect(fetchDashboardMock).toHaveBeenCalledTimes(2);
    expect(result.current.snapshot).toBe(refreshedSnapshot);
  });

  it("clears an error after a later refresh succeeds", async () => {
    vi.useFakeTimers();
    const recoveredSnapshot = snapshot(30);
    fetchDashboardMock
      .mockRejectedValueOnce(new Error("Temporary failure"))
      .mockResolvedValueOnce(recoveredSnapshot);

    const { result } = renderHook(() => useDashboard());
    await flushRequest();
    expect(result.current.error).toBe("Temporary failure");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DASHBOARD_REFRESH_INTERVAL_MS);
    });

    expect(result.current.snapshot).toBe(recoveredSnapshot);
    expect(result.current.error).toBeNull();
  });

  it("cancels the request and interval when unmounted", () => {
    vi.useFakeTimers();
    fetchDashboardMock.mockReturnValue(new Promise(() => undefined));

    const { unmount } = renderHook(() => useDashboard());
    const signal = fetchDashboardMock.mock.calls[0][0];

    expect(signal?.aborted).toBe(false);
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
