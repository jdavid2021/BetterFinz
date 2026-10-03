export const authRoutes = {
  signup: "/api/v1/auth/signup",
  resendVerification: "/api/v1/auth/resend-verification",
  verifyEmail: "/api/v1/auth/verify-email",
  forgotPassword: "/api/v1/auth/forgot-password",
  resetPassword: "/api/v1/auth/reset-password",
} as const;

export const onboardingRoutes = {
  status: "/api/v1/onboarding/status",
  dismiss: "/api/v1/onboarding/dismiss",
} as const;
