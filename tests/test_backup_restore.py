"""D10: encrypted-backup integrity and the restore drill.

These exercise the real backup/verify/restore path against a real SQLite
database and a real uploads directory (no mocks):

* a backup writes an integrity manifest with a SHA-256 per file;
* verification detects a corrupted dump and a tampered uploads file;
* the restore drill restores into an isolated scratch directory, matches every
  table's row count, and never touches the source database.
"""

from __future__ import annotations

import sqlite3

from backend.core import backup


def _make_source_db(path) -> None:
    connection = sqlite3.connect(str(path))
    connection.executescript(
        """
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);
        CREATE TABLE monthly_reports (id INTEGER PRIMARY KEY);
        CREATE TABLE support_requests (id INTEGER PRIMARY KEY);
        """
    )
    connection.execute("INSERT INTO companies (id, name) VALUES (1, 'ألفا')")
    connection.execute("INSERT INTO companies (id, name) VALUES (2, 'بيتا')")
    connection.execute("INSERT INTO users (id, email) VALUES (1, 'a@corp.sa')")
    connection.execute("INSERT INTO monthly_reports (id) VALUES (1)")
    connection.execute("INSERT INTO monthly_reports (id) VALUES (2)")
    connection.execute("INSERT INTO support_requests (id) VALUES (1)")
    connection.commit()
    connection.close()


def _fixture(tmp_path):
    db_path = tmp_path / "safir.db"
    _make_source_db(db_path)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "cv_1.pdf").write_bytes(b"%PDF-1.4 attachment one")
    (uploads / "note.txt").write_bytes(b"a supporting note")
    return db_path, uploads


def test_backup_records_row_counts_and_upload_digests(tmp_path):
    db_path, uploads = _fixture(tmp_path)
    dest = tmp_path / "backup"
    manifest = backup.create_backup(
        database_url=f"sqlite:///{db_path}", upload_dir=str(uploads), dest_dir=dest
    )

    assert manifest.database_url_kind == "sqlite"
    assert manifest.row_counts == {
        "companies": 2, "users": 1, "monthly_reports": 2, "support_requests": 1,
    }
    assert len(manifest.uploads) == 2
    assert (dest / backup.DB_DUMP_NAME).exists()
    assert (dest / backup.MANIFEST_NAME).exists()


def test_verification_passes_then_detects_a_corrupted_dump(tmp_path):
    db_path, uploads = _fixture(tmp_path)
    dest = tmp_path / "backup"
    backup.create_backup(
        database_url=f"sqlite:///{db_path}", upload_dir=str(uploads), dest_dir=dest
    )

    assert backup.verify_backup(dest)["ok"] is True

    # Corrupt the dump: verification must fail, not silently pass.
    with (dest / backup.DB_DUMP_NAME).open("ab") as handle:
        handle.write(b"tampered")
    result = backup.verify_backup(dest)
    assert result["ok"] is False
    assert any("checksum" in p for p in result["problems"])


def test_verification_detects_a_tampered_upload(tmp_path):
    db_path, uploads = _fixture(tmp_path)
    dest = tmp_path / "backup"
    backup.create_backup(
        database_url=f"sqlite:///{db_path}", upload_dir=str(uploads), dest_dir=dest
    )

    (dest / backup.UPLOADS_DIR_NAME / "note.txt").write_bytes(b"changed")
    result = backup.verify_backup(dest)
    assert result["ok"] is False
    assert any("note.txt" in p for p in result["problems"])


def test_restore_drill_proves_the_restore_in_isolation(tmp_path):
    db_path, uploads = _fixture(tmp_path)
    dest = tmp_path / "backup"
    backup.create_backup(
        database_url=f"sqlite:///{db_path}", upload_dir=str(uploads), dest_dir=dest
    )

    scratch = tmp_path / "scratch"
    result = backup.run_restore_drill(dest, scratch)

    assert result["ok"] is True, result["problems"]
    assert result["restored_row_counts"] == {
        "companies": 2, "users": 1, "monthly_reports": 2, "support_requests": 1,
    }
    assert result["uploads_restored"] == 2
    # The scratch location holds the restored copy; the source is untouched.
    assert (scratch / backup.DB_DUMP_NAME).exists()
    assert (scratch / backup.UPLOADS_DIR_NAME / "cv_1.pdf").exists()
    assert db_path.exists()
    assert (uploads / "cv_1.pdf").read_bytes() == b"%PDF-1.4 attachment one"


def test_drill_reports_a_failed_restore_when_the_source_is_corrupt(tmp_path):
    db_path, uploads = _fixture(tmp_path)
    dest = tmp_path / "backup"
    backup.create_backup(
        database_url=f"sqlite:///{db_path}", upload_dir=str(uploads), dest_dir=dest
    )

    # A corrupt dump cannot pass the drill's integrity check.
    (dest / backup.DB_DUMP_NAME).write_bytes(b"not a database")
    result = backup.run_restore_drill(dest, tmp_path / "scratch")
    assert result["ok"] is False
    assert result["problems"]
