import { describe, expect, it } from "vitest";

import { validateSentryConfig } from "./sentry-config";
import { scrubSentryEvent } from "./sentry-scrub";

describe("scrubSentryEvent", () => {
  it("removes authentication, identity, and account data", () => {
    const event = scrubSentryEvent(
      {
        type: undefined,
        request: {
          cookies: { session: "secret-cookie" },
          headers: { authorization: "Bearer secret-token" },
          data: { token: "secret-token" },
        },
        user: {
          id: "8c50d55b-5541-438e-a0b6-b4b7c7d3f875",
          email: "person@example.test",
        },
        extra: {
          household_id: "315d65fd-5db4-4ea2-a8f0-412e67ba3451",
          account_number: "123456789012",
          params: ["private"],
        },
      },
      {},
    );
    const encoded = JSON.stringify(event);
    expect(encoded).not.toContain("secret");
    expect(encoded).not.toContain("person@example.test");
    expect(encoded).not.toContain("315d65fd-5db4-4ea2-a8f0-412e67ba3451");
    expect(encoded).not.toContain("123456789012");
    expect(event.request?.headers?.authorization).toBe("[Filtered]");
  });
});

describe("validateSentryConfig", () => {
  it("rejects unsafe or incomplete monitoring settings", () => {
    expect(() => validateSentryConfig({ tracesSampleRate: "1.1" })).toThrow();
    expect(() =>
      validateSentryConfig({
        dsn: "http://example.test/1",
        environment: "test",
        release: "release",
      }),
    ).toThrow();
    expect(() =>
      validateSentryConfig({
        dsn: "https://example.test/1",
        environment: "test",
      }),
    ).toThrow();
  });
});
