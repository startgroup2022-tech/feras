# Master execution checkpoint — D01 / D02 / D10 / D11 + BI authorization

Branch: `feature/safir-s26-s28-accounting-completion` (PR #5, base
`frontend-app-conversion` @ `abfcd0de5f16640135a68fa6a03079988099857c`).

This checkpoint records the batches delivered on top of the S26–S28 accounting
completion. Every item below was implemented, migrated, and covered by
automated tests that exercise the real persistence and API paths.

## D02 — KPI target-versus-actual (complete)

* Migration `b1c2d3e4f5a6` adds `metric_key`, `direction` and the approval
  columns to `kpi_definitions` (additive, SQLite batch mode).
* A KPI carries its data source, calculation method and period so a metric is
  always reproducible; a definition is **inert until an authorised approval**
  activates it (`POST /accounting/kpis/{id}/active`).
* `GET /accounting/kpis/evaluations` computes target-versus-actual from source
  records; `GET /accounting/kpis/{id}/sources` returns the source records.
* Tests: `tests/test_kpi_targets.py` (10 cases).

## D11 — notification preferences & delivery log (complete)

* Models `NotificationPreference` and `NotificationDeliveryLog`; migration
  `c3d4e5f6a7b8`.
* `notification_service` consults the per-user/per-event-type preference and
  records each delivery in the log; a muted event type is skipped.
* Endpoints in `backend/api/v1/notifications.py`; request schema
  `NotificationPreferenceRequest`.
* Tests: `tests/test_notification_preferences.py` (12 cases).

## D01 — accountant-approved accounting policy registry (complete)

The S26–S28 work left D01's *policy* half as "stored as neutral data and waits
for accountant-approved configuration". That gap is now closed with a real
registry:

* Model `AccountingPolicy` (migration `d4e5f6a7b8c9`). A policy is versioned
  **data**; tax, fiscal-year, invoice, asset and currency policy are the
  `PolicyKind` values.
* A newly recorded policy is a **draft** and is inert — `effective_policy` never
  returns a draft, so an unapproved rule cannot influence a calculation.
* Approval (`POST /accounting/policies/{id}/approve`) is the only way a value
  becomes effective; it stamps who/when and **supersedes** the prior approved
  version, which is retained (never edited or deleted) so history survives.
* Resolution order: a company-specific approved policy wins over the
  holding-wide default (`GET /accounting/policies/effective`).
* Permissions `accounting_policy.read/manage/approve` (draft, approve and read
  are distinct); granted to the accountant and holding finance. Bilingual
  metadata added.
* Tests: `tests/test_accounting_policies.py` (9 cases).

## D10 — backup integrity and restore drill (complete)

D10 was documentation-only prose. It now has verifiable tooling that never
touches production:

* `backend/core/backup.py` writes a backup (database dump + uploads snapshot)
  with a SHA-256 integrity manifest per file and per-table row counts.
* `verify_backup` detects a corrupted dump or a tampered uploads file.
* `run_restore_drill` restores into an isolated scratch directory and proves the
  restore by matching every recorded table's row count; it cannot restore over a
  live database.
* `scripts/backup.py` exposes `create` / `verify` / `drill` for ops.
* Tests: `tests/test_backup_restore.py` (5 cases).

## BI authorization consistency (complete)

`GET /api/v1/ai/insights` returns dashboard data, so it is gated by
`dashboard.*`; the frontend view is gated on the same permission. A role granted
only `ai.holding` cannot reach the insights endpoint. Regression test in
`tests/test_insights.py`.

## Still owner-dependent (do not invent approvals)

* The remaining `D01`–`D11` decisions that require an explicit written owner
  approval remain open. D01's registry now *stores* the policy; the accountant
  still supplies and approves the values.
* **The original Word specification (`Platform_Executive_Specifications_v1(2).docx`)
  was not available in this workspace.** The requirement matrix is therefore
  derived from the recovered specification notes
  (`docs/reference/SAFIR_SPEC_RECOVERED.md`) and cannot be claimed as a verbatim
  reading of the source document. The source file must be supplied to certify
  specification completeness.

## Frontend wiring for the above (verified in a browser)

The four decisions above are not only backend-complete; each has a live UI path:

* **D01** — `frontend/app.js` `renderPolicies()` (tab `policies`, gated on
  `accounting_policy.read`); draft form needs `accounting_policy.manage`,
  approve button needs `accounting_policy.approve`.
* **D11** — `renderNotificationPreferences()` (inbox "Channel preferences"),
  reads `GET /notifications/preferences` and writes each toggle through
  `PUT /notifications/preferences/{event_type}`.
* **S02/S10** — `goalsHtml(r.goals)` inside `biCompanyTable()` shows each
  company's approved target-versus-actual goals.
* **D02** — KPI evaluations/targets surface through the accounting `kpis` tab.

Browser evidence (accountant account, seeded demo database): the accounting
policies tab rendered the draft form and the approved tax policy v1; the
notification preferences panel rendered one row per event type and a toggle
click issued `PUT /notifications/preferences/%2A` returning 200; `report.submitted`
showed Email ✓ exactly as written through the API. Server log confirms every
call.

## Test evidence

* `python -m pytest tests/ -q` — 817 passed (2026-10-14; exit 0).
* `tests/test_frontend_domain_views.py` — 33 passed (contract tests for the new
  views, plus an i18n scan that fails on any untranslated literal `dual(ar,en)`).
* `alembic check` — "No new upgrade operations detected."
* Migration head: `d4e5f6a7b8c9` (single linear chain).

## Still owner-gated after this batch (do not invent)

* **D09** base-currency-change *procedure* (a documented rate + date + source and
  a history-preserving switch) is not built; the guard that blocks mixing
  currencies without an approved rule is already live.
* **D01** depreciation method/rate and tax values are stored as neutral data; the
  accountant supplies and approves the actual values through the new registry.
* The original Word specification was not present in this workspace, so the
  matrix is derived from `docs/reference/SAFIR_SPEC_RECOVERED.md` and cannot be
  certified as a verbatim reading of the source document.

## D02 investigation — company-scoped KPI creation (resolved, 2026-10-15)

Symptom: creating a KPI bound to a company returned 403
("You do not have access to this company's data.") for the seeded owner.

Root cause: **seed-data gap, not an authorization defect.** `can_write_company`
deliberately requires an explicit `user_company_access` row with `can_write`;
being holding-wide widens *reads* only. The seed granted that row to the company
managers and BD but to *no* holding-staff account — so the owner and accountant,
the two roles whose job is company-scoped accounting, were refused every write.

A first attempt to "fix" `can_write_company` by letting holding-wide users write
any company was **reverted**: it broke two deliberate isolation tests
(`test_campaign_write_requires_company_access`,
`test_bd_cannot_write_a_project_for_another_company`) and would have weakened
company isolation. The model is correct; the seed was wrong.

Fix (`scripts/seed_demo.py`): grant the owner, accountant, marketing and design
roles every company; make `ensure_user` idempotent so re-seeding backfills a
missing grant. Regression coverage in `tests/test_seed_demo.py` (3 tests; all
fail against the unpatched seed).

Verified end to end against the live API: the accountant now creates a chart of
accounts entry and an opening balance (201/200), both persist on re-read, and a
company manager writing another company still receives 403 for accounts, opening
balances and KPI drill-down.
