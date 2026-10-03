import * as Sentry from "@sentry/nextjs";

import { validateSentryConfig } from "@/lib/sentry-config";
import { scrubSentryEvent } from "@/lib/sentry-scrub";

const config = validateSentryConfig({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
  release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
  tracesSampleRate: process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE,
});

Sentry.init({
  ...config,
  sendDefaultPii: false,
  beforeSend: scrubSentryEvent,
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
