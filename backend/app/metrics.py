from prometheus_client import Counter, Gauge, Histogram


API_REQUESTS = Counter(
    "finleash_api_requests_total",
    "API requests grouped by route and outcome.",
    ("method", "route", "status"),
)
API_LATENCY = Histogram(
    "finleash_api_request_duration_seconds",
    "API request latency grouped by route.",
    ("method", "route"),
)
API_ERRORS = Counter(
    "finleash_api_errors_total",
    "Unhandled and server-side API errors.",
    ("method", "route"),
)
CELERY_TASKS = Counter(
    "finleash_celery_tasks_total",
    "Celery task outcomes.",
    ("task", "outcome"),
)
CELERY_TASK_LATENCY = Histogram(
    "finleash_celery_task_duration_seconds",
    "Celery task run time.",
    ("task",),
)
SIMPLEFIN_SYNCS = Counter(
    "finleash_simplefin_sync_total",
    "SimpleFIN synchronization outcomes.",
    ("outcome",),
)
SIMPLEFIN_CONNECTIONS = Gauge(
    "finleash_simplefin_connections",
    "SimpleFIN connections by current health state.",
    ("state",),
)
SCHEDULER_HEARTBEAT_AGE = Gauge(
    "finleash_scheduler_heartbeat_age_seconds",
    "Age of the last scheduler heartbeat.",
)
