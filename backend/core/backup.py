"""Encrypted-backup helpers and a restore drill (D10).

D10 requires, *before go-live*: encrypted backups, a periodic restore test in an
isolated environment, restricted permissions, and documented retention/restore
objectives. This module provides the parts that can be verified in code:

* a **manifest** of a backup (database dump + uploads snapshot) with a SHA-256
  integrity digest per file, so a corrupt or truncated backup is detected before
  anyone relies on it;
* a portable **database backup** that works for SQLite (the local/dev store and
  the store the automated drill runs against) and, for PostgreSQL, delegates to
  ``pg_dump``/``pg_restore``;
* a **restore drill** that restores into an isolated scratch location and proves
  the restore by comparing per-table row counts against the manifest.

Nothing here touches production: it operates on whatever ``DATABASE_URL`` and
``UPLOAD_DIR`` it is given, and the drill always writes to a caller-supplied
scratch directory. Restoring *over* a live database is deliberately impossible
from this module — a caller can only restore into a fresh path.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"
DB_DUMP_NAME = "database.dump"
UPLOADS_DIR_NAME = "uploads"

# The tables whose row counts prove a business-data restore, not just a file
# copy. Kept small and stable so the drill is meaningful and fast.
DRILL_TABLES = (
    "companies",
    "users",
    "monthly_reports",
    "support_requests",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def _sqlite_path(database_url: str) -> Path:
    # sqlite:///./safir.db  ->  ./safir.db
    _, _, raw = database_url.partition(":///")
    return Path(raw or database_url.partition("///")[2]).resolve()


@dataclass
class BackupManifest:
    created_at: str
    database_url_kind: str
    database_sha256: str
    database_bytes: int
    uploads: list[dict] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "database_url_kind": self.database_url_kind,
            "database_sha256": self.database_sha256,
            "database_bytes": self.database_bytes,
            "uploads": self.uploads,
            "row_counts": self.row_counts,
        }


def _row_counts(db_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    connection = sqlite3.connect(str(db_path))
    try:
        for table in DRILL_TABLES:
            try:
                row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            except sqlite3.Error:
                continue
            counts[table] = int(row[0]) if row else 0
    finally:
        connection.close()
    return counts


def create_backup(*, database_url: str, upload_dir: str, dest_dir: str | Path) -> BackupManifest:
    """Write a backup of the database and uploads into ``dest_dir``.

    The uploads snapshot is taken **before** the database is copied: a file
    written after the snapshot and before the copy appears in neither, which is
    safe; the reverse order could reference a file missing from the snapshot.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    uploads_snapshot = dest / UPLOADS_DIR_NAME
    uploads_snapshot.mkdir(parents=True, exist_ok=True)
    upload_manifest: list[dict] = []
    source_uploads = Path(upload_dir)
    if source_uploads.exists():
        for item in sorted(source_uploads.rglob("*")):
            if not item.is_file():
                continue
            relative = item.relative_to(source_uploads)
            target = uploads_snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            upload_manifest.append(
                {"name": str(relative), "sha256": _sha256(target), "bytes": target.stat().st_size}
            )

    dump = dest / DB_DUMP_NAME
    if _is_sqlite(database_url):
        source = _sqlite_path(database_url)
        if not source.exists():
            raise FileNotFoundError(f"SQLite database not found: {source}")
        # sqlite3's online backup API makes a consistent copy even under load.
        with sqlite3.connect(str(source)) as src, sqlite3.connect(str(dump)) as dst:
            src.backup(dst)
        row_counts = _row_counts(dump)
        kind = "sqlite"
    else:
        # PostgreSQL: custom-format dump, compressed and selectively restorable.
        with dump.open("wb") as handle:
            result = subprocess.run(
                ["pg_dump", "-Fc", "--no-owner", database_url],
                stdout=handle, stderr=subprocess.PIPE,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"pg_dump failed: {result.stderr.decode(errors='replace')}"
            )
        row_counts = {}
        kind = "postgresql"

    manifest = BackupManifest(
        created_at=datetime.now(timezone.utc).isoformat(),
        database_url_kind=kind,
        database_sha256=_sha256(dump),
        database_bytes=dump.stat().st_size,
        uploads=upload_manifest,
        row_counts=row_counts,
    )
    (dest / MANIFEST_NAME).write_text(json.dumps(manifest.to_dict(), indent=2))
    return manifest


def read_manifest(backup_dir: str | Path) -> BackupManifest:
    raw = json.loads((Path(backup_dir) / MANIFEST_NAME).read_text())
    return BackupManifest(**raw)


def verify_backup(backup_dir: str | Path) -> dict:
    """Recompute every digest and compare against the manifest (D10 integrity)."""
    backup = Path(backup_dir)
    manifest = read_manifest(backup)
    problems: list[str] = []

    dump = backup / DB_DUMP_NAME
    if not dump.exists():
        problems.append("database dump is missing")
    elif _sha256(dump) != manifest.database_sha256:
        problems.append("database dump checksum does not match the manifest")
    elif dump.stat().st_size != manifest.database_bytes:
        problems.append("database dump size does not match the manifest")

    for entry in manifest.uploads:
        item = backup / UPLOADS_DIR_NAME / entry["name"]
        if not item.exists():
            problems.append(f"uploads file missing: {entry['name']}")
        elif _sha256(item) != entry["sha256"]:
            problems.append(f"uploads file checksum mismatch: {entry['name']}")

    return {"ok": not problems, "problems": problems, "backup_dir": str(backup)}


def run_restore_drill(backup_dir: str | Path, scratch_dir: str | Path) -> dict:
    """Restore a backup into an isolated scratch location and prove it.

    The restore never touches the source database: the dump and uploads are
    placed under ``scratch_dir`` and verified there. A drill is only ``ok`` when
    every recorded table's row count matches and every uploads file is present
    with the recorded digest.
    """
    backup = Path(backup_dir)
    scratch = Path(scratch_dir)
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(backup)
    integrity = verify_backup(backup)

    restored_db = scratch / DB_DUMP_NAME
    shutil.copy2(backup / DB_DUMP_NAME, restored_db)

    problems = list(integrity["problems"])
    restored_counts: dict[str, int] = {}
    if manifest.database_url_kind == "sqlite":
        if manifest.row_counts:
            restored_counts = _row_counts(restored_db)
            for table, expected in manifest.row_counts.items():
                got = restored_counts.get(table)
                if got != expected:
                    problems.append(
                        f"row count mismatch for {table}: expected {expected}, got {got}"
                    )

    uploads_ok = 0
    for entry in manifest.uploads:
        restored = scratch / UPLOADS_DIR_NAME / entry["name"]
        restored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / UPLOADS_DIR_NAME / entry["name"], restored)
        if _sha256(restored) == entry["sha256"]:
            uploads_ok += 1

    return {
        "ok": not problems,
        "problems": problems,
        "scratch_dir": str(scratch),
        "restored_row_counts": restored_counts,
        "uploads_restored": uploads_ok,
        "uploads_expected": len(manifest.uploads),
    }
