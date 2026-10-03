import * as Sentry from "@sentry/nextjs";

import { validateSentryConfig } from "@/lib/sentry-config";
import { scrubSentryEvent } from "@/lib/sentry-scrub";

const config = validateSentryConfig({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT,
  release: process.env.SENTRY_RELEASE,
  tracesSampleRate: process.env.SENTRY_TRACES_SAMPLE_RATE,
});

Sentry.init({
  ...config,
  sendDefaultPii: false,
  beforeSend: scrubSentryEvent,
});
