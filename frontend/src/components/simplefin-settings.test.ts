import { describe, expect, it } from "vitest";
import { Connection, syncDetail } from "./simplefin-settings";

const connection: Connection = {
  id: "connection-id",
  status: "active",
  sync_health: "healthy",
  last_sync_at: null,
  last_successful_sync_at: null,
  sync_started_at: null,
  next_sync_at: null,
  consecutive_failures: 0,
  automatic_sync_enabled: true,
  sync_interval_minutes: 360,
  last_error: "",
};

describe("SimpleFIN synchronization status", () => {
  it("explains a synchronization in progress", () => {
    expect(syncDetail({ ...connection, sync_health: "syncing" })).toContain(
      "Fetching read-only",
    );
  });

  it("shows safe error details and the next retry", () => {
    const detail = syncDetail({
      ...connection,
      status: "error",
      sync_health: "error",
      last_error: "SimpleFIN is temporarily unavailable.",
      next_sync_at: "2026-08-24T06:00:00Z",
    });
    expect(detail).toContain("temporarily unavailable");
    expect(detail).toContain("Next automatic attempt");
  });
});
