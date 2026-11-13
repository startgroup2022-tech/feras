# Phase 4 — Verification and Audit

Evidence-based verification of the Phase 3 "Full Functional Implementation"
against a live instance, an isolated database, and a real Chromium session.
Phase 4 changes no feature behaviour; it **verifies** the platform and fixes the
handful of defects the verification surfaced.

Branch `feature/phase3-functional`. Worktree `/workspace/project/wt-impl`.
Baseline for comparison: Phase 3 closed at **994 passing tests**;
Phase 4 closes at **1002** (three reverse-proxy guards plus the earlier
regression tests).

## Method

| Section | Question | Harness | Result |
|---|---|---|---|
| P4-A | What is the API surface and which workflow does each op belong to? | OpenAPI + `scripts/audit/view_audit.py` | 254 paths / 333 operations mapped |
| P4-B | Do the end-to-end workflows actually complete? | Phase 3 workflow suites | 21/21 pass |
| P4-C | Can a role reach data or an action it should not? | `scripts/acceptance/security_sweep.py` | 23/23 pass |
| P4-D | Is the data safe — migrations, integrity, backup, rollback? | `scripts/backup.py`, `alembic`, SQLite pragmas | pass (below) |
| P4-E | Does the UI hold up across views, languages and widths? | `scripts/acceptance/ui_responsive.py` | 168/168 pass |
| P4-F | Is it fast and does it stay up? | `scripts/acceptance/perf_reliability.py` | 97 endpoints, p95 21 ms, 0 5xx |

Everything ran against `http://127.0.0.1:12099` with the demo seed loaded, and
against isolated scratch databases for the destructive checks.

## Mandate status — the two binding references

Two mandates govern this work. One is fully verifiable here; the other is not.

| Mandate | Source | Status |
|---|---|---|
| Business rules and security controls | `Platform_Executive_Specifications_v1.docx` | **Verified.** All 28 screens (S01–S28) and all 28 acceptance criteria (AC-01…AC-28) are ✅ in `docs/audit/SAFIR_SPEC_PARITY_MATRIX.md`, each with a proving test. |
| Interface, navigation, layout, role UX | `Platform Interface Design v3.pptx` | **Unverifiable — the deck is not present.** No `.pptx` exists anywhere on this machine, in the repository, or in any of the 11 remote refs. No slide has been seen. |

The Word mandate is met: the specification matrix has no 🟡/❌/🔒 rows, and the
security controls it names (isolation, role boundaries, immutability,
auditability) are re-proved independently in P4-C below rather than taken on
trust from the matrix.

The PPTX mandate **cannot be discharged in this environment**, and no visual
parity is claimed. What has been done instead is to make the comparison
mechanical the moment the deck arrives:

* `scripts/extract_pptx.py` reads the OOXML directly (a `.pptx` is a zip of XML
  parts) with no third-party dependency, emitting per-slide text in z-order,
  tables cell-by-cell, embedded images and speaker notes. **Exercised** against
  a synthetic deck built for the purpose: it recovered the Arabic RTL runs, the
  two-row table, the embedded image and the note correctly.
* `scripts/compare_screens.py` builds side-by-side reference/implementation
  images from a slide→screen mapping. **Exercised** end-to-end with a synthetic
  slide/implementation pair; it wrote `compare-S01.png` as documented.
* `scripts/render_pptx.sh` (deck → one PNG per slide via LibreOffice + poppler)
  is present on that branch with dependency and input guards. It was **not**
  exercised here: LibreOffice and poppler are not installed in this
  environment, and the script fails cleanly with a clear message when they are
  absent (`apt-get install -y libreoffice-impress poppler-utils`).
* `docs/POWERPOINT-SCREEN-MATRIX.md` on branch `docs/powerpoint-parity-v3`
  holds the owner decisions and an intentionally **empty** slide→screen table,
  to be filled only from slides actually seen.

The deck must be supplied as a file in the repository (or its contents pasted)
before any parity claim can be made or refuted. Until then the six-section
navigation implements the module list the brief names; it does **not** assert a
visual match to unseen slides.

## P4-A — API surface and workflow map

* **254 OpenAPI paths, 333 operations.** The 333 operations were grouped into
  the business workflows they serve (reporting, financial summary lifecycle,
  approvals, accounting, admin/RBAC, support, documents, AI, public website).
* Largest groups: accounting 41, admin 22, operations 22, financial 15,
  forms 14, monthly-reports 14, employees 10, public 10.
* Auth surface enumerated and exercised: `login`, `refresh`, `logout`, `me`,
  `2fa`.

## P4-B — End-to-end workflows

The 21 Phase 3 workflow scenarios (report submission → review → approval,
financial-summary versioning and correction, support-request lifecycle,
employee movement, document upload, AI insight generation, and the rest) pass
end to end against an isolated database: **21/21**.

## P4-C — Security and permissions

`scripts/acceptance/security_sweep.py` — **23/23 pass**.

* **Unauthenticated sweep.** All 97 parameterless `GET`s were requested with no
  token. Two answered `200` and both are `GET /api/v1/public/*` — the marketing
  website's surface, which is public **by design**. Every other endpoint
  refused. Zero authenticated-only reads leaked.
* **Public surface stays narrow.** `GET /api/v1/public/opportunities` returns no
  internal identifiers (`company_id`, `lead_id`, `owner_id`, `created_by`).
* **Cross-company isolation.** A company manager reaches exactly one company;
  every other company id returns **404**, never 403 — so a response never
  confirms that an out-of-scope record exists. A foreign company's monthly
  reports are likewise 404.
* **Privilege boundaries.** Eight probes across all seven roles: no non-owner
  role can list users or sync RBAC; a company manager cannot read
  holding-wide analytics (`403`).
* **Token hygiene.** Garbage, empty and badly-signed tokens all yield `401`.
  A forged token with `"alg":"none"` is rejected too (the verifier pins the
  algorithm rather than trusting the header).
* **Attachment storage.** Four filename-traversal payloads
  (`../../../../etc/passwd`, `..\..\win.ini`, `....//....//x.txt`, `/etc/passwd`)
  are refused; only allow-listed types are accepted (`application/pdf` and
  `image/png` succeed, `text/x-php`, `image/svg+xml`, `application/x-executable`
  and `application/x-msdownload` do not). Stored files are content-addressed
  hashes under the upload root — no request-supplied name ever reaches the
  filesystem, so nothing escaped during the probe.
* **Login rate limiting.** Eleven consecutive failed logins return `401`; the
  twelfth and every one after returns `429`. The limiter is keyed per client.
* **Public form abuse controls.** The contact form requires `consent`, validates
  email, and bounds field lengths (`message` ≤ 4000 chars). A filled honeypot
  returns a plausible `201` with a reference but stores **nothing** — verified by
  reading the table back. Extra unknown keys (`company_id`, `role`,
  `is_verified`) are ignored rather than honoured.
* **Audit coverage.** A support-request assignment writes
  `support_request.assigned` with the acting user; an AI call writes
  `ai.message_sent`. Both were confirmed by counting `audit_logs` before and
  after the request and reading the newest row.
* **Immutability.** A `reviewed` report refuses modification with `409` — the
  report lifecycle is enforced, not merely displayed.

## P4-D — Database and data safety

* **Schema drift:** `alembic check` → *"No new upgrade operations detected."*
* **Migration cycle:** on a scratch database, `upgrade head` → `downgrade base`
  → `upgrade head` completes cleanly. After `downgrade base` only
  `alembic_version` remains; re-upgrade returns to head `3473d285d919` with no
  drift.
* **Integrity:** `PRAGMA integrity_check` → `ok`; `PRAGMA foreign_key_check` →
  0 violations across 103 tables.
* **Referential and uniqueness invariants:** zero orphan `user → role` or
  `report → company` rows; zero audit rows without an action; no duplicate
  company codes; no duplicate user emails.
* **Backup / verify / restore drill:** `create` → `verify` (`problems: []`) →
  `drill` into an isolated scratch directory restores identical row counts
  (companies 6, users 9, monthly_reports 10, support_requests 5). The drill
  never writes over a live database.
* **Seed safety:** the demo reset is scoped to demo rows only. Real rows survive
  `--reset`; only demo companies and users are rebuilt.
* **Production guards:** the app refuses to start in production without a strong
  `SECRET_KEY`; the seed refuses to run against a production database without
  `--force`.

## P4-E — UI, responsiveness and RTL/LTR

`scripts/acceptance/ui_responsive.py` — **168/168 pass** across **21 views × 2
languages × 4 viewports** (1920×1080, 1440×900, 834×1112, 390×844).

Per cell the harness asserts the view rendered real content, the document
direction matches the language (`rtl` for Arabic, `ltr` for English), the page
does not overflow horizontally, navigation is present, and no console error was
raised. All 168 cells pass.

Complementing this, Phase 3's `scripts/audit/view_audit.py` walked all 21 views
as all 7 roles at 1920×1080: **0 failed HTTP responses** across 263 rendered
panels. The only console error was a `404` for a missing `/favicon.ico`, which
is cosmetic and listed under findings.

## P4-F — Performance and reliability

`scripts/acceptance/perf_reliability.py` against the running instance:

* **97 parameterless GETs** swept, each run twice (the second run is the
  reported figure, so a cold-cache cost is not mistaken for a slow endpoint).
* **median 8.8 ms, p95 20.6 ms, max 34.5 ms.** No endpoint approached the
  4 s outlier budget.
* **0 server errors** — no `5xx` in the sweep, and no traceback in the server
  log for the whole run.
* **Frontend shell** served in ~3–4 ms each: `index.html` 67 KB, `app.js`
  562 KB, `styles.css` 68 KB.

## Findings and fixes

Six defects were found and fixed during Phase 4. Each fix carries a regression
test.

### F-1 — Missing platform asset returned the HTML shell (`200 text/html`)

`/platform/{rest:path}` answered *every* unknown path with the shell document,
so `/platform/typo.js` returned `200 text/html`. A browser then tried to execute
HTML as JavaScript, and — more importantly — the miss was invisible to any
uptime or error monitor because it looked like a successful request.

**Fix:** only an extensionless path is treated as an in-app hash route; a path
carrying a file extension is an asset request and returns a real `404`. Deep
links keep working.
`tests/test_website_pages.py::test_missing_platform_asset_is_404_not_the_html_shell`

### F-2 — Production accepted a weak `SECRET_KEY`

The production guard rejected only the exact dev placeholder, so
`APP_ENV=production SECRET_KEY=abc` started normally with a 3-character HMAC
key — every session token forgeable by brute force.

**Fix:** production now requires at least 32 characters and rejects the
placeholder values that ship in the repo. Development and test keep the
permissive default.
`tests/test_staging_security.py` (three new cases)

### F-3 — Seed reset could delete real data

The demo reset deleted rows by table, not by demo scope, so a `--reset` against
a database that also held real data removed the real rows too.

**Fix:** the reset is scoped to demo rows (demo company codes and the demo email
domain); real rows survive. A regression test proves a real company, user and
document outlive `--reset`.
`tests/test_seed_demo.py`

### F-4 — Harness selector bugs (false alarms, not product defects)

The first UI pass reported every English cell as `dir=rtl`. The cause was the
harness clicking the login screen's hidden language buttons instead of the
platform's toggle. Corrected to `.lang-switch [data-lang=...]` and to drive
navigation via `.nav-item[data-view]`. All 168 cells pass.

### F-5 — Static assets served uncompressed and uncached

`app.js` is 562 KB and the app ships no compression and no cache header, so
every cold page load moved 562 KB + 68 KB of CSS over the wire.

**Fix (deployment configuration):** `deploy/nginx/safir-staging.conf` now turns
on `gzip` for the text types (`app.js` → 116 KB, a 79% reduction, measured) and
adds a short `expires 5m` to the platform's `app.js`/`auth.js`/`styles.css`.
The cache is deliberately **not** `immutable`: those filenames carry no content
hash, so a long immutable cache would pin a stale shell across deploys.

### F-6 — A location's `add_header` silently dropped the security headers

nginx *replaces* rather than merges `add_header` across levels. The existing
`location /website/assets/` set a `Cache-Control`, which therefore removed
HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`
from those responses — a silent regression invisible in a browser.

**Fix:** the five headers now live in one snippet,
`deploy/nginx/safir-security-headers.conf`, `include`d at server level and
re-`include`d inside every location that sets its own `add_header`.
`tests/test_staging_security.py` asserts the invariant and fails if a future
location forgets the include.

## Residual findings — cosmetic, not fixed

* **No `/favicon.ico` at the site root.** A browser requests it, gets a `404`,
  and logs one console line. Cosmetic; the platform path serves its own
  favicon.

## Result

| Suite | Result |
|---|---|
| Full pytest suite | **1002 passed, 0 failed, 0 errors, 0 skipped** (861 s) |
| Security sweep | 23/23 |
| UI/responsive matrix | 168/168 |
| Performance sweep | 97 endpoints, p95 20.6 ms, 0 5xx |
| Backup verify / drill | problems `[]`, rows restored identical |
| Migration cycle | clean, no drift |
| Production guards | refuse weak secret and non-forced prod seed |

Phase 4 confirms the Phase 3 implementation is functionally complete, isolated
by role and company, safe to migrate and restore, responsive and correctly
directed in both languages, and fast enough on a demo-class instance. The six
defects above are fixed and regression-covered.
