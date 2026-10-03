import { describe, expect, it } from "vitest";
import { authRoutes, onboardingRoutes } from "./frontend-routes";

describe("frontend API contracts", () => {
  it("uses the production account lifecycle endpoints", () => {
    expect(authRoutes).toEqual({
      signup: "/api/v1/auth/signup",
      resendVerification: "/api/v1/auth/resend-verification",
      verifyEmail: "/api/v1/auth/verify-email",
      forgotPassword: "/api/v1/auth/forgot-password",
      resetPassword: "/api/v1/auth/reset-password",
    });
  });

  it("uses the onboarding status and dismissal endpoints", () => {
    expect(onboardingRoutes).toEqual({
      status: "/api/v1/onboarding/status",
      dismiss: "/api/v1/onboarding/dismiss",
    });
  });
});
