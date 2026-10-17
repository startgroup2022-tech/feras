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

## Acceptance-criteria completion batch — notifications & overdue (2026-10-15)

Closing the AC rows that had no dedicated coverage, without reopening the
already-complete modules. Each item below is a real business workflow wired
through service → API → persistence, with a test that exercises the API path.

### AC-16 — a design/service request reaches the specialist directly

* `notification_service.notify_support_created(...)` notifies the **owning
  specialist role** (the category's `CATEGORY_OWNER_ROLE`) as `support.assigned`
  and **informs business development** as `support.created`.
* BD receives an *informational* notification only: the request stays `new`, so
  there is no hidden BD approval step (spec AC-16 / T03).
* `notification_service.users_with_role(db, *, role_code)` resolves the active
  holders of a role; the acting user is never notified of their own action.
* Tests: `tests/test_support.py::test_new_request_notifies_the_owning_specialist`,
  `..._informs_bd_without_gating_it`, `..._requester_is_not_notified_of_its_own_request`.

### AC-17 — task follow-up, overdue list, and no double entry

* `notification_service.notify_task_assigned(...)` tells the assignee a task was
  put on their desk; `notify_task_status_changed(...)` surfaces an assignee's
  progress to the creator/reviewer (no penalty, per S17).
* `list_tasks(..., overdue=True)` and `serialise_task(...)["is_overdue"]` expose a
  server-side overdue verdict that **excludes completed and cancelled** tasks
  (AC-17: "المهمة المنجزة لا تظهر في قائمة المتأخر"); the frontend prefers it.
* A task is a first-class record that references a company/project, so a task
  raised from a request does not create a second register (the single-entity
  design already enforces AC-17's "no double entry").
* Tests: `tests/test_holding_domain.py::test_assigning_a_task_notifies_the_assignee`,
  `..._task_status_change_notifies_the_creator`, `..._overdue_list_excludes_a_completed_task`.

### AC-15 — a complaint never notifies a manager

* `operations_service._notify_complaint_route(...)` notifies **only** the person
  the owner explicitly names on `routed_to_id`, and the notification carries no
  subject or body (the complaint stays confidential). Logging a complaint
  notifies nobody.
* Test: `tests/test_holding_domain.py::test_complaint_decision_notifies_only_the_named_person`.

### Verification

* `python -m pytest tests/ -q` — full suite green (exit 0) on this branch.
* No schema change was required for this batch (notifications are data rows), so
  the alembic head is unchanged and `alembic check` stays clean.

### Still owner-dependent (do not invent)

* D01–D11 remain open where they need an explicit written owner decision (see
  `SAFIR_OPEN_DECISIONS_AND_ASSUMPTIONS.md`); nothing here presumes an approval.
* The original Word specification must still be supplied to certify a verbatim
  reading; the matrix continues to cite the recovered text.

## S22 directive execution reply + S11/AC-11 holding termination (2026-10-15)

Two genuinely missing business workflows, each wired through service → API →
persistence with automated acceptance tests.

### S22 — the named executor replies to a directive

The specification makes the owner the *issuer* of a decision or a binding
directive and the named person the *executor*. Previously only the owner could
touch a decision; the executor had no way to report execution.

* `POST /api/v1/operations/owner-decisions/{id}/respond` accepts a note from the
  named `executor_user_id`. It records an `OwnerDecisionEvent`, advances an
  `open` decision to `in_progress`, and **can never** reach `done`/`cancelled`
  (only the owner closes a decision).
* A stranger receives **404**, never a 403 that would reveal the decision
  exists (isolation rule preserved).
* The issuer (owner) is notified of the reply; the reply never widens the
  audience.
* Audit action `owner_decision.responded`.
* Frontend: `frontend/app.js` `renderDecisionsView()` offers the reply control
  only to `d.executor_user_id === USER.id` and posts to `/respond`.
* Tests: `tests/test_owner_decisions.py` (4 new cases) and
  `tests/test_frontend_domain_views.py::test_s22_directive_reply_is_wired_to_the_respond_endpoint`.

### S11 / AC-11 — terminating a Holding employee never bypasses the owner

S11 separates the manager's authority over *subsidiary* employees from the
owner's approval over *Holding* employees ("فصل القابضة لا يتجاوز قرار المالك").

* `hr_service.update_employee` refuses a `status=terminated` change on an
  employee whose company is `company_type == holding` unless the caller is the
  owner (or delegated super admin). The check reads the company row, so it
  holds even when the manager carries a write grant on the Holding company.
* Tests: `tests/test_employee_termination.py` (5 cases): manager may terminate a
  subsidiary employee, may **not** terminate a Holding employee (403), the owner
  may; BD cannot edit a subsidiary salary; creating an employee mints no login.

### Verification

* `python -m pytest tests/ -q` — full suite green (exit 0); 870 tests collected.
* No schema change was required (the reply is a row in `owner_decision_events`,
  the audit action is an enum value), so `alembic check` stays clean and the
  head is unchanged (`f2b3c4d5e6a7`).


## S23 / AC-23 — the owner's secret note on a confidential leadership assessment (2026-10-15)

The specification's confidential leadership centre (S23) carries an owner-only
secret note ("ملاحظات المالك — نص سري") that is context for later periods. The
assessment module already existed; the note itself was the missing piece.

* `Assessment.owner_note` / `owner_note_at` columns (migration `a3b4c5d6e7f8`,
  revises `f2b3c4d5e6a7`).
* `POST /api/v1/employees/assessments/{id}/owner-note` — owner-only. A non-owner
  receives 403/404 and can never learn the note exists; the endpoint refuses any
  assessment that is not a leadership assessment.
* `hr_service.serialise_assessment(..., include_owner_note=False)` gates the note
  behind a flag. The API passes `include_owner_note=is_confidential_owner(user)`,
  so the field is **absent** for a delegated reader (AC-23: the secret must not
  leak through a link, an export or search).
* The note text is deliberately **not** written to the audit payload, so a secret
  never reaches a shared activity log. The action is still audited
  (`assessment.owner_note_saved`).
* Frontend: the assessment detail renders the secret-note panel only for
  `isConfidentialOwner()` on a `leadership` assessment, and posts to the
  dedicated endpoint.
* Tests: `tests/test_leadership_assessments.py` (3 new cases — owner save +
  audit-without-secret, grantee never receives the note, non-owner denied) and
  `tests/test_frontend_domain_views.py::test_s23_owner_secret_note_is_wired_to_the_owner_note_endpoint`.

### Verification

* `python -m pytest tests/ -q` — full suite green (exit 0); **875 tests collected**.
* `alembic check` — "No new upgrade operations detected." Single linear head
  `a3b4c5d6e7f8` (`tests/test_postgres.py` head assertion updated).


## Execution 31 — D03: the versioned non-financial management report (S09) (2026-10-17)

Execution 30 closed every authorised owner decision except **D03**, whose
remaining gap was recorded rather than papered over: the spec says the
correction of the *non-financial* (management) monthly report after submission
"needs D03" and must be a correction version *linked to the original*, but
`MonthlyReport` was one-per-company-per-period with no correction link and edits
blocked once submitted. That gap is now closed.

* `MonthlyReport` gains `version_number`, `corrects_report_id`, `is_live`, an
  owner `approval_status`, and return/approve/cancel metadata
  (`return_reason`, `returned_by_id/at`, `approved_by_id/at`,
  `cancelled_by_id/at`, `cancel_reason`).
* The per-period uniqueness `uq_report_company_period` becomes
  `uq_report_company_period_version` (company, period, version) plus a **partial
  unique index** `uq_report_company_period_live` that allows exactly one live
  version per company/period. A correction therefore never overwrites the
  original.
* New append-only `ReportLifecycleEvent` trail
  (`submitted`/`resubmitted`/`returned`/`approved`/`cancelled`).
* `report_service`: `return_report` (BD, mandatory reason), `create_correction`
  (linked new version, original superseded and preserved), `approve_report` and
  `cancel_report` (owner-only), plus `list_versions` / `list_lifecycle`.
* New permissions `monthly_report.review` (BD) and `monthly_report.approve`
  (owner), with bilingual metadata; the accountant's *financial* review stays a
  separate, unchanged concern (F-03).
* Endpoints: `POST /monthly-reports/{id}/return|correction|approve|cancel`,
  `GET /monthly-reports/{id}/versions|lifecycle`. The report detail embeds the
  chain and trail.
* Frontend: the report modal renders the version chain + workflow trail and
  offers permission-gated Return / Create-correction / Approve / Cancel actions.
* Migration `3473d285d919` (revises `62040b21dfa2`), reversible and drift-free.

### Verification

* `python -m pytest tests/ -q` — full suite green (exit 0); **967 tests**
  (946 baseline + 21 new in `test_execution31_d03_report_correction.py`).
* `alembic check` — "No new upgrade operations detected." Single linear head
  `3473d285d919` (`tests/test_postgres.py` head assertion updated).
* `alembic downgrade -1` → `upgrade head` — reversible, re-applies cleanly.
* RBAC sync — 15 roles, **179** permissions, all catalogued with bilingual
  metadata (`test_holding_domain.py` count updated).
* `node --check frontend/app.js` — passes.
