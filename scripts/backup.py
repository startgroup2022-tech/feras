"""Backup / verify / restore-drill CLI (D10).

Usage::

    # 1) Take a backup (database + uploads) with an integrity manifest.
    python scripts/backup.py create --dest /backup/safir_20261015

    # 2) Verify a backup before trusting it.
    python scripts/backup.py verify --source /backup/safir_20261015

    # 3) Restore into an isolated scratch location and prove the drill.
    python scripts/backup.py drill --source /backup/safir_20261015 \\
        --scratch /tmp/safir_restore

Never restores over a live database: ``drill`` always writes to a fresh scratch
directory. Read ``DATABASE_URL`` and ``UPLOAD_DIR`` from the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core import backup  # noqa: E402
from backend.core.config import settings  # noqa: E402


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safir backup / restore drill (D10)")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="take a database + uploads backup")
    create.add_argument("--dest", required=True)
    create.add_argument("--uploads", default=None)

    verify = sub.add_parser("verify", help="verify a backup's integrity manifest")
    verify.add_argument("--source", required=True)

    drill = sub.add_parser("drill", help="restore into an isolated scratch location")
    drill.add_argument("--source", required=True)
    drill.add_argument("--scratch", required=True)

    args = parser.parse_args(argv)

    if args.command == "create":
        database_url = _database_url()
        if not database_url:
            print("DATABASE_URL is required to create a backup.", file=sys.stderr)
            return 2
        manifest = backup.create_backup(
            database_url=database_url,
            upload_dir=args.uploads or settings.UPLOAD_DIR,
            dest_dir=args.dest,
        )
        print(json.dumps(manifest.to_dict(), indent=2))
        return 0

    if args.command == "verify":
        result = backup.verify_backup(args.source)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    if args.command == "drill":
        result = backup.run_restore_drill(args.source, args.scratch)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
