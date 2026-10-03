import { describe, expect, it } from "vitest";
import { shouldEnterSetup } from "./onboarding";

describe("onboarding handoff", () => {
  it("sends incomplete OAuth and magic-link arrivals from Today to setup", () => {
    expect(shouldEnterSetup("/today", {
      complete: false,
      dismissed: false,
      account_complete: false,
      income_complete: false,
      plan_complete: false,
    })).toBe(true);
  });

  it("does not interrupt completed, dismissed, or non-Today routes", () => {
    expect(shouldEnterSetup("/today", { complete: true, dismissed: false })).toBe(false);
    expect(shouldEnterSetup("/today", { complete: false, dismissed: true })).toBe(false);
    expect(shouldEnterSetup("/accounts", { complete: false, dismissed: false })).toBe(false);
  });
});
