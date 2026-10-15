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

## Test evidence

* `python -m pytest tests/ -q` — 809 passed.
* `alembic check` — "No new upgrade operations detected."
* Migration head: `d4e5f6a7b8c9` (single linear chain).
