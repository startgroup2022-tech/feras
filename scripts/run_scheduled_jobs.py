"""Scheduled jobs entry point.

Two policies need to run on a timer rather than on a request:

* **CV retention** (``site-integration.md``): a careers CV is deleted after six
  months. The Holding promises this on the public website, so it must actually
  happen without anyone clicking a button.
* **Report deadline scan** (``business-rules.md`` rule 1): the expected period's
  report is due on the 5th of the following month; once the deadline passes, the
  companies still late are flagged by a notification.

Both jobs are idempotent, so running them more often than strictly necessary is
harmless. The script is the production trigger (see ``deploy/systemd``); the
same functions are reachable through the admin API for a manual run.

Usage::

    python -m scripts.run_scheduled_jobs            # run both
    python -m scripts.run_scheduled_jobs --dry-run  # report, change nothing
    python -m scripts.run_scheduled_jobs --only cv
    python -m scripts.run_scheduled_jobs --only deadlines
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.config import settings  # noqa: E402
from backend.db.session import session_scope  # noqa: E402
from backend.services import report_deadline, retention_service  # noqa: E402


def _run_cv(dry_run: bool) -> dict:
    with session_scope() as db:
        return retention_service.purge_expired_cvs(db, dry_run=dry_run)


def _run_deadlines() -> dict:
    with session_scope() as db:
        return report_deadline.scan_report_deadlines(db)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Safir scheduled jobs.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what the retention job would remove; change nothing.",
    )
    parser.add_argument(
        "--only",
        choices=["cv", "deadlines"],
        default=None,
        help="Run a single job instead of both.",
    )
    args = parser.parse_args(argv)

    print(f"APP_ENV={settings.APP_ENV}")

    if args.only in (None, "cv"):
        result = _run_cv(args.dry_run)
        print(
            "cv-retention:"
            f" cutoff={result['cutoff'].isoformat()}"
            f" retention_months={result['retention_months']}"
            f" removed={result['removed_count']}"
            f" dry_run={result['dry_run']}"
        )

    if args.only in (None, "deadlines") and not args.dry_run:
        result = _run_deadlines()
        print(
            "report-deadlines:"
            f" period={result['period_year']}-{result['period_month']:02d}"
            f" deadline={result['deadline'].isoformat()}"
            f" late={result['late_count']}"
            f" notifications={result['notifications']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
