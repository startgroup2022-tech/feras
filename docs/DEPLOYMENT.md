# Safir Holding 2027 — Staging Deployment Guide

This guide prepares the approved Phase 2 application (`phase2-functional-v1`,
commit `ec77588`) for a staging environment. It does not itself deploy
anything, and it never touches production.

> **Never run `scripts/seed_demo.py` on staging.** Demo data is for local
> development only. Use `scripts/bootstrap_owner.py` for the first real owner.

---

## 1. Prerequisites

| Component | Version |
|---|---|
| OS | Debian 12 / Ubuntu 22.04 LTS |
| Python | 3.11–3.13 (verified on 3.13) |
| PostgreSQL | 15 or 16 |
| nginx | 1.18+ |
| TLS | Let's Encrypt (certbot) or an equivalent certificate |

The app ships with the `psycopg` 3 driver (`psycopg[binary]==3.3.6`) so no
system `libpq` build step is required.

---

## 2. Provision the host

```bash
sudo useradd --system --home /opt/safir --shell /usr/sbin/nologin safir
sudo mkdir -p /opt/safir/app /var/lib/safir/uploads /etc/safir /backup
sudo chown -R safir:safir /opt/safir /var/lib/safir
sudo chmod 750 /var/lib/safir/uploads
```

---

## 3. Obtain the code (pinned to the approved commit)

```bash
sudo -u safir git clone https://github.com/startgroup2022-tech/feras.git /opt/safir/app
cd /opt/safir/app
sudo -u safir git checkout phase2-functional-v1
sudo -u safir git rev-parse HEAD        # expect ec77588...
```

---

## 4. Python environment

```bash
python3 -m venv /opt/safir/venv
/opt/safir/venv/bin/pip install --upgrade pip
/opt/safir/venv/bin/pip install -r /opt/safir/app/requirements.txt
```

Do **not** install `requirements-dev.txt` on staging.

---

## 5. Database

Create a dedicated staging database and role. Never reuse production
credentials.

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE safir_staging LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
CREATE DATABASE safir_staging OWNER safir_staging ENCODING 'UTF8';
SQL
```

---

## 6. Environment file

```bash
sudo install -m 600 deploy/env/staging.env.example /etc/safir/staging.env
sudo editor /etc/safir/staging.env          # fill in real values
sudo chown safir:safir /etc/safir/staging.env
```

Generate the secret key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Rules:

* `SECRET_KEY` must be unique to staging and never the dev default.
* `DATABASE_URL` must point at the staging database.
* `UPLOAD_DIR=/var/lib/safir/uploads`.
* The file is mode `600` and is **never** committed.

See `deploy/env/staging.env.example` for the full list.

---

## 7. Migrations (deliberate, reviewed step)

Alembic reads `DATABASE_URL` from the environment — `alembic.ini` intentionally
carries no URL.

```bash
cd /opt/safir/app
export $(grep -v '^#' /etc/safir/staging.env | xargs)   # or: set -a; . /etc/safir/staging.env; set +a

# 1) Inspect the SQL preview first (no database writes).
/opt/safir/venv/bin/python -m alembic upgrade head --sql

# 2) Confirm you are pointing at the staging database.
/opt/safir/venv/bin/python -c "from backend.core.config import settings; print(settings.DATABASE_URL)"

# 3) Apply.
/opt/safir/venv/bin/python -m alembic upgrade head

# 4) Verify.
/opt/safir/venv/bin/python -m alembic current   # expect 55d2d244bc1b
/opt/safir/venv/bin/python -m alembic check      # expect "No new upgrade operations detected."
```

**Do not run any migration against production.** Stop and request approval
before applying to staging.

---

## 8. First Holding Owner

```bash
sudo -u safir /opt/safir/venv/bin/python -m scripts.bootstrap_owner \
    --email owner@holding.example \
    --name-ar "الاسم بالعربية" \
    --name-en "Owner Name"
```

* Prompts for a strong password (never echoed), or reads
  `SAFIR_OWNER_PASSWORD` from the environment for non-interactive runs.
* Refuses demo passwords, demo email domains and weak passwords.
* Refuses to run twice (no second initial owner).
* Initialises the RBAC catalogue first.

The password is never printed.

---

## 9. Service

```bash
sudo install -m 644 deploy/systemd/safir-staging.service /etc/systemd/system/safir-staging.service
sudo systemctl daemon-reload
sudo systemctl enable --now safir-staging
sudo systemctl status safir-staging
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

Exactly **one** uvicorn worker is used. Do not add gunicorn or multiple workers
until the in-process rate limiter is replaced with a shared store.

---

## 10. Reverse proxy and HTTPS

```bash
sudo cp deploy/nginx/safir-staging.conf /etc/nginx/sites-available/safir-staging
sudo ln -s /etc/nginx/sites-available/safir-staging /etc/nginx/sites-enabled/safir-staging
# edit server_name and certificate paths, then obtain a certificate:
sudo certbot --nginx -d staging.example.com
sudo nginx -t && sudo systemctl reload nginx
```

The proxy adds HSTS and CSP, forwards client IP (`X-Forwarded-For`), and
**denies `/api/docs` and `/api/openapi.json` by default**. To allow authorized
users, enable the basic-auth or IP-allow block in the config.

---

## 11. Verification

```bash
curl -fsS https://staging.example.com/health
curl -fsS https://staging.example.com/ready
curl -fsS -o /dev/null -w '%{http_code}\n' https://staging.example.com/api/docs   # expect 403
```

---

## 12. Rollback

Application rollback (no database change):

```bash
cd /opt/safir/app
sudo -u safir git fetch --all
sudo -u safir git checkout <previous-good-commit-or-tag>
sudo systemctl restart safir-staging
curl -fsS http://127.0.0.1:8000/ready
```

Database rollback (only if a migration must be reverted):

```bash
# DESTRUCTIVE: inspect the SQL first and take a backup beforehand.
/opt/safir/venv/bin/python -m alembic downgrade -1 --sql
/opt/safir/venv/bin/python -m alembic downgrade -1
```

Because the initial migration is `down_revision = None`, a full downgrade
removes all tables. Prefer restoring from backup (see
[BACKUP_RESTORE.md](BACKUP_RESTORE.md)) over downgrading in staging.

---

## 13. Security checklist

* [ ] `SECRET_KEY` is unique to staging (not the dev default).
* [ ] `DEBUG=false`.
* [ ] Staging database is separate from production.
* [ ] `UPLOAD_DIR` is a persistent, writable volume outside the repo.
* [ ] `/api/docs` is denied or auth-gated at the proxy.
* [ ] HSTS and CSP are present on HTTPS responses.
* [ ] Upload limits (allowed types, 10 MiB) are unchanged.
* [ ] No `.env` file or credential is committed.
* [ ] Exactly one uvicorn worker.
