# Safir Holding 2027 — Backup & Restoration

Staging backup procedures for the two stateful stores:

1. **PostgreSQL database** — all business data and metadata.
2. **Uploads directory** — attachment files. Only metadata (an opaque storage
   key) lives in the database, so the database and the uploads directory must be
   captured **together** and **consistently**. A dump without a matching uploads
   snapshot references files that no longer exist, and vice versa.

These are procedures only. No scheduled jobs against production are created
here.

---

## 1. Consistency

Take the database dump and the uploads snapshot at the same point in time. The
simplest reliable ordering:

1. Put the app in a quiet state (low traffic) or briefly stop writes.
2. Snapshot the uploads directory.
3. Immediately take the database dump.
4. Resume.

For a fully consistent pair under load, snapshot the uploads volume
first, then dump the database — a file written after the snapshot but before the
dump will appear in neither, which is safe; the reverse order could reference a
file that is missing from the snapshot.

---

## 2. Database backup

Custom-format dump (compressed, restorable selectively):

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
pg_dump -Fc -U safir_staging -h 127.0.0.1 safir_staging \
    > /backup/safir_staging_${STAMP}.dump
```

Retention and encryption (example):

```bash
gpg --symmetric --cipher-algo AES256 /backup/safir_staging_${STAMP}.dump
find /backup -name 'safir_staging_*.dump*' -mtime +30 -delete
```

Store copies off-host. Never store backups next to the database they protect.

---

## 3. Uploads backup

```bash
rsync -a --delete /var/lib/safir/uploads/ /backup/uploads/
# or, for a point-in-time snapshot on a filesystem that supports it:
sudo lvcreate --size 1G --snapshot --name safir_up_snap /dev/vg0/safir
```

---

## 4. Restoration drill (into a scratch database)

Always rehearse restoration into a **separate scratch database**, never over the
live staging database.

```bash
# 1) Create the scratch database.
sudo -u postgres psql -c "CREATE DATABASE safir_restore OWNER safir_staging;"

# 2) Restore the dump.
sudo -u postgres pg_restore -U safir_staging -h 127.0.0.1 \
    -d safir_restore --clean --if-exists /backup/safir_staging_<STAMP>.dump

# 3) Restore uploads into a scratch directory.
sudo mkdir -p /var/lib/safir/uploads_restore
sudo rsync -a /backup/uploads/ /var/lib/safir/uploads_restore/

# 4) Verify row counts match the source.
psql -U safir_staging -h 127.0.0.1 -d safir_restore -c \
    "SELECT 'companies' t, count(*) FROM companies
     UNION ALL SELECT 'users', count(*) FROM users
     UNION ALL SELECT 'monthly_reports', count(*) FROM monthly_reports
     UNION ALL SELECT 'support_requests', count(*) FROM support_requests;"

# 5) Optional: point a throwaway app instance at the scratch DB + uploads dir
#    with DATABASE_URL=...safir_restore and UPLOAD_DIR=/var/lib/safir/uploads_restore
#    and confirm /ready returns 200.

# 6) Clean up.
sudo -u postgres psql -c "DROP DATABASE safir_restore;"
sudo rm -rf /var/lib/safir/uploads_restore
```

A restoration is only proven once the scratch instance answers `/ready` with
`{"status":"ready"}` and a login against a restored user succeeds.

---

## 5. Schedule (operational, not created here)

| What | Frequency | Retention |
|---|---|---|
| Database dump | Daily | 30 days |
| Uploads snapshot | Daily | 30 days |
| Restore drill | Monthly | — |

Use `systemd` timers or cron. The jobs must run as a user with read access to
the uploads directory and database-dump privileges. Backups must be encrypted
at rest and stored off-host.
