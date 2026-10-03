export type SentryRuntimeConfig = {
  dsn?: string;
  environment?: string;
  release?: string;
  tracesSampleRate: number;
};

export function validateSentryConfig(
  values: Omit<SentryRuntimeConfig, "tracesSampleRate"> & {
    tracesSampleRate?: string;
  },
): SentryRuntimeConfig {
  const tracesSampleRate = Number(values.tracesSampleRate || "0");
  if (!Number.isFinite(tracesSampleRate) || tracesSampleRate < 0 || tracesSampleRate > 1) {
    throw new Error("Sentry trace sample rate must be between 0 and 1.");
  }
  if (values.dsn) {
    const dsn = new URL(values.dsn);
    if (dsn.protocol !== "https:" || !dsn.hostname) {
      throw new Error("Sentry DSN must be an HTTPS URL.");
    }
    if (!values.environment?.trim() || !values.release?.trim()) {
      throw new Error("Sentry environment and release are required when a DSN is configured.");
    }
  }
  return { ...values, tracesSampleRate };
}
