import sys

from app.health import scheduler_is_healthy


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "scheduler":
        try:
            return 0 if scheduler_is_healthy() else 1
        except Exception:
            return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
