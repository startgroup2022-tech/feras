# SAFIR Holding 2027 — Final Production-Readiness Audit & Release Acceptance

**Execution:** 29 — final production readiness audit & release acceptance.
**Repository:** `github.com/startgroup2022-tech/feras`
**Audited branch:** `feature/safir-s26-s28-accounting-completion` (PR #5)
**Integration branch:** `frontend-app-conversion`
**Baseline (integration HEAD):** `abfcd0de5f16640135a68fa6a03079988099857c`
**Audit HEAD:** `c52557a0e38656b3b3cc7172226bf426627d55ea`
**Authoritative source:** `docs/reference/Platform_Executive_Specifications_v1.docx`
(original Word file — 451 paragraphs, 85 tables, screens S01–S28, AC-01…AC-28).
**Date:** 2026-10-14.
**Verdict:** **NOT READY** for production deployment — see §G. Two classes of
defect block go-live: an unpatched dependency set (real CVEs) and owner-dependent
decisions still open (D01–D11). The application logic itself is in good shape.

---

## A. Method

Every claim below is backed by a command that was run in this audit, or by a
source file at a cited path. Where a claim could not be proven, it is marked
**UNVERIFIED** rather than assumed. The audit was performed against a
**disposable** SQLite database (`/tmp/audit_*.db`) and a locally launched server;
no production database and no VPS was touched.

## B. Baseline verification

| Item | Evidence | Result |
|---|---|---|
| Remote HEAD == local HEAD | `git rev-parse HEAD` → `5273cd04…` | ✅ |
| Integration HEAD | `git rev-parse origin/frontend-app-conversion` → `abfcd0de…` | ✅ |
| Working tree | `git status --short` | clean at start |
| PR #5 | `gh pr view 5` | OPEN, draft, base `frontend-app-conversion`, `mergeStateStatus=CLEAN` |
| Shallow clone | `git rev-parse --is-shallow-repository` | `true` (history truncated — noted) |

## C. Specification coverage

The Word document is present and was read directly. Its structure was confirmed:
451 paragraphs, 85 tables. Authoritative tables extracted and used:

* **Table 3** — the seven roles (Holding Owner, BD Manager, Company Manager,
  Accountant, Marketing, Designer, + Phase 2 group-admin roles).
* **Table 77** — the acceptance-criteria table, 26 rows.
* **Table 78** — the ten Holding-Owner sections.
* **Table 81** — the accountant's **five** approved grouped sections.

The screen-by-screen (S01–S28) and criterion-by-criterion (AC-01…AC-28) matrices
are maintained in `docs/audit/SAFIR_SPEC_PARITY_MATRIX.md` and
`docs/audit/SAFIR_SPECIFICATION_GAP_MATRIX.md`. During this audit one matrix
claim was found **unsupported** and has now been corrected and implemented
(see §F).

## D. Functional verification performed in this audit

### D1. Automated suite

```
python -m pytest tests/ -q          # baseline pins
→ 926 passed in 785.24s (0:13:05)   exit 0
```

### D2. Migration integrity

```
APP_ENV=development DATABASE_URL=sqlite:////tmp/audit_dev.db alembic check
→ "No new upgrade operations detected."                (no schema drift)
alembic upgrade head  (fresh DB)   → reaches d6e7f8a9b0c1
alembic downgrade base             → unwinds to initial
alembic upgrade head               → returns to head    (clean cycle)
```
Single linear head: `d6e7f8a9b0c1` (S28 monthly financial report, Table 57).

### D3. Financial arithmetic reconciliation (live API, from scratch)

Scenario built through the real endpoints (accounts → opening balances →
journals → invoices → budgets → reports):

| Check | Result |
|---|---|
| Opening balances bank 120 / cash 30 stored exactly, **no auto revenue**, **no auto journals** (AC-04, D08) | ✅ |
| Unbalanced journal (debit 100 / credit 90) refused at **post** time with 422 (AC-26) | ✅ |
| Re-posting a posted journal refused (409) — no duplication (AC-26) | ✅ |
| Trial balance debits == credits (100.00 == 100.00) (AC-26) | ✅ |
| Invoice → journal link is **single reference**: second link returns 409 (AC-27) | ✅ |
| Partial settlement 400 of 1000 → outstanding 600, status `partially_settled` (AC-27) | ✅ |
| Budget over-run reports `over_budget` + `auto_payment_approval: false` (AC-28) | ✅ |
| Group report returns `is_consolidated: false` with an explicit disclaimer note; holding and subsidiaries kept distinct (AC-28) | ✅ |

### D4. Security posture

| Check | Evidence | Result |
|---|---|---|
| Unauthenticated protected endpoint | `GET /api/v1/dashboard/holding` → 401 | ✅ |
| Invalid bearer token | → 401, generic body (no internal detail) | ✅ |
| Rate limiting | 11 rapid failed logins → ten `401`, then `429` | ✅ |
| Security headers (app) | `x-content-type-options`, `x-frame-options: DENY`, `referrer-policy`, `x-robots-tag` | ✅ |
| Security headers (edge) | nginx adds HSTS, CSP (`frame-ancestors 'none'`), TLSv1.2/1.3 only | ✅ |
| CSRF | Auth is `Authorization: Bearer`; no cookie session → not applicable | ✅ |
| Upload guard | content-type allow-list, size caps (5/10 MiB), path-traversal guard in `backend/core/storage.py` | ✅ |
| SQL injection | SQLAlchemy ORM parameterises all queries; no string SQL in services | ✅ |
| Secret handling | `SECRET_KEY` has no usable production default and is validated at startup (`backend/core/config.py`) | ✅ |

### D5. Performance (single dev worker, SQLite — indicative only)

`GET /dashboard/holding` p50 ≈ 13 ms; `/companies` ≈ 7 ms; `/ai/insights` ≈ 13 ms.
20 concurrent dashboard reads p50 ≈ 247 ms — the limit is the single-worker
SQLite dev setup, **not** representative of the production Postgres + nginx +
systemd topology. No production load test has been run (**UNVERIFIED**).

### D6. Browser / UI

Arabic RTL dashboard, accounting view, and the AR↔EN toggle were exercised in a
live browser; screenshots captured under `docs/release/screenshots/`.
Responsive breakpoints at 1180/560/480 px are present in `frontend/styles.css`.

## E. Dependency vulnerabilities — FOUND, NOW PATCHED IN THIS BRANCH

`pip-audit -r requirements.txt` reported three affected packages on the pinned set:

| Package | Was | Advisory class | Patched to |
|---|---|---|---|
| `pyjwt` | 2.10.1 | multiple JWT handling advisories | 2.15.1 |
| `python-multipart` | 0.0.20 | multipart/urlencoded DoS, parser differential | 0.0.32 |
| `starlette` | 0.41.3 (via fastapi 0.115.6) | Range-header DoS, form-limit bypass, path/authority confusion | 1.8.0 (via fastapi 0.143.3) |

These are real and reachable in principle (the app accepts multipart uploads and
serves files), so the original pinned set must not ship. `requirements.txt` is
updated to `fastapi==0.143.3`, `PyJWT==2.15.1`, `python-multipart==0.0.32`
(pulling `starlette==1.8.0`). After the change:

```
pip-audit -r requirements.txt --format json   → vulnerable packages: NONE
```

The upgrade produced deprecation warnings only; `backend/core/errors.py` was
moved from the deprecated `HTTP_422_UNPROCESSABLE_ENTITY` to
`HTTP_422_UNPROCESSABLE_CONTENT`. The full suite result on the patched set is
recorded in §I.

## F. Functional gap found and fixed in this audit

**AC-28 / Table 81 (accountant's five sections).** The specification requires the
accountant's area to be grouped into exactly five approved sections:

1. Holding Accounts (S26, S28)
2. Invoices and Dues (S27)
3. Subsidiary Finance (S02, S08, S07, S10)
4. Financial Reports (S28, S18)
5. Tasks and Requests (S16, S17)

The delivered UI rendered **14 flat chips** with no grouping, and the parity
matrix claimed this criterion complete with a proof that did not exist
(`nav sections` — no such artifact). This is a genuine, spec-level defect, now
implemented:

* `frontend/index.html` — a new `#acctSections` toolbar of exactly five
  permission-gated section buttons; every fine-grained chip carries a
  `data-acct-section` mapping into one of the five.
* `frontend/app.js` — `ACCT_SECTIONS`, `ACCT_SECTION_PERM`, `ACCT_TAB_SECTION`,
  `canAcctSection`, `syncAcctSections`, `firstTabInSection`; selecting a section
  shows only its chips and renders its first permitted tab.
* Two new grouped tabs fill the remaining sections: **Subsidiary finance**
  (company financial reports + group summary, holding-gated) and **Tasks &
  requests registry**.
* Tests added in `tests/test_accounting_s28.py`: the section list and order are
  asserted, every tab must map to an approved section, and every section button
  must be permission-gated. A regression to flat chips now fails the suite.

## G. Verdict — NOT READY

Reasons, in priority order:

1. **Owner-dependent decisions remain open (H, below).** D01–D11 are not
   approved; per spec §20 their parts are recorded open and must not be marked
   complete. No approval has been invented. This alone holds the release.
2. **Non-blocking but required before go-live.** Production load test,
   production-DB backup/restore drill, and a signed release checklist. The
   tooling and docs exist; the drill has not been executed on the production
   target from this workspace, by design.
3. **Dependency CVEs — resolved in this branch (E).** The pinned set carried
   known CVEs; the branch now pins the patched set and `pip-audit` is clean. This
   must be merged and re-verified as part of the release.

Everything else audited — baseline integrity, migrations, financial arithmetic,
authorization, isolation, security headers, rate limiting, upload guards,
health endpoint — passes with the evidence in §B–D.

## H. Owner-dependent decisions carried forward

Per spec §20, none is invented; each remains open:

| ID | Open item | Affected |
|---|---|---|
| D01 | depreciation/tax/fiscal-year/invoice values (supplied via the approved policy registry) | S05/S06/S08, S26–S28 |
| D02 | goals definition and weekly-template wording | S02, S09, S10, S14, S18, S21 |
| D03 | lead redistribution / pipeline-state visibility | S13, S16, S17, S20 |
| D04 | redistribution-history visibility | S12, S13, S15, S19, S23 |
| D09 | base-currency-change procedure (mixing guard is live) | S03, S06, S10 |
| D10 | production restore policy (tooling live and isolated) | T17 |
| D11 | login method (SSO); additional notification channels | S01, S25 |

## I. Release checklist

- [x] Baseline commit verified
- [x] Original Word specification read and tables extracted
- [x] S01–S28 and AC-01…AC-28 matrices reviewed; one false claim corrected
- [x] Automated suite green on the pinned set (926 passed)
- [x] Automated suite green on the **patched** dependency set — **928 passed,
      0 failed, 0 skipped** (926 baseline + 2 new AC-28 tests), 778.94s
- [x] Migrations drift-free (`alembic check` → "No new upgrade operations
      detected.") and reversible
- [x] Financial arithmetic reconciles (AC-04/26/27/28)
- [x] Authorization, isolation, rate limiting, headers, upload guards verified
      on the patched stack (401 unauth, 429 after 10 failed logins)
- [x] `pip-audit -r requirements.txt` → no vulnerable packages
- [ ] Production load test (not run)
- [ ] Production backup/restore drill (not run)
- [ ] Owner approval of D01–D11 (not recorded)
- [ ] Patched dependency set merged into `frontend-app-conversion` (PR open)

**Next incomplete requirement:** obtain owner approval of D01–D11 (§H), then run
the production load test and the production-DB backup/restore drill. None of
these can be completed without the owner; no approval has been invented.
