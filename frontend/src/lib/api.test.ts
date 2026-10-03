import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("always sends the browser session cookie", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/auth/me");

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/me"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("uses the API error message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "Email or password is incorrect." } }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    ));

    await expect(api("/api/v1/auth/login", { method: "POST" })).rejects.toThrow(
      "Email or password is incorrect.",
    );
  });
});
