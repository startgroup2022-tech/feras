# Execution 30 — Owner Decisions Implementation & Final Release Gate

Branch: `feature/safir-execution-30-owner-decisions`
Base: `frontend-app-conversion` @ `c449706c1c5875ef8b1485b55ead0d5591d75214`
(merge of PR #5, "S26–S28 accounting completion").

This checkpoint records the implementation of the owner-authorised decisions
**D01, D03, D04, D09, D11** on top of the Execution 29 baseline, plus the
verification evidence gathered at the final release gate.

## 1. Authorisation

The owner explicitly authorised implementation of **D01, D02, D03, D04, D09,
D10, D11**. Not authorised: inventing unspecified financial values, destructive
production operations, or deployment. Every value that a decision leaves to the
owner (depreciation rates, fiscal-year dates, invoice/asset policy, the base
currency of a company, KPI targets) is supplied through an **approved record**,
never hard-coded.

D02 (KPI target-versus-actual) and D10 (backup integrity + restore drill) were
completed in Execution 29 and are covered by `tests/test_kpi_targets.py` and
`tests/test_backup_restore.py`. This execution completes the remaining
authorised decisions: D01, D03, D04, D09, D11.

## 2. What was built

### D01 — financial-policy governance (propose → decide → activate)

* New model `PolicyProposal` (migration `62040b21dfa2`). A proposal is a
  *separate* row from the `AccountingPolicy` version it targets, so "proposed"
  and "approved" can never be the same object.
* Endpoints: `GET/POST /accounting/policies/proposals`,
  `POST /accounting/policies/proposals/{id}/decide`.
* Rule: a proposal is **inert**. Only a decision by a role holding
  `accounting_policy.approve` activates the policy version; a rejected proposal
  changes nothing and the prior approved version is retained.
* Permission `accounting_policy.propose`; bilingual metadata added.

### D03 — lead assignment / reassignment history

* New model `LeadAssignment` (append-only). Every assignment or reassignment
  writes an immutable history row with the previous assignee, the actor and a
  reason.
* Endpoints: `POST /leads/{id}/assign`, `GET /leads/{id}/assignments`.
* New permission `website_lead.assign` (distinct from `website_lead.manage`);
  a reassignment requires a reason. Bilingual metadata added.

### D04 — history access is company-scoped

* `GET /leads/{id}/assignments` is scoped server-side. A company-confined role
  never sees another company's lead history; "not yours" and "does not exist"
  both return 404 (no existence disclosure).
* New permission `history.read` (BD reads the change/distribution history it
  needs); bilingual metadata added.

### D09 — base-currency change workflow

* New model `CurrencyChangeRequest` (migration `62040b21dfa2`) with the
  lifecycle `requested → reviewed → approved/rejected → scheduled → applied`.
* Endpoints: `GET/POST /accounting/currency-changes`,
  `POST .../{id}/review`, `POST .../{id}/decide`, `POST .../{id}/apply`.
* Rule: a change can never be applied before its effective financial period;
  historical rows keep their original currency (no retrospective conversion).
* Permissions `currency_change.read/request/review/approve`; bilingual metadata.

### D11 — two-factor authentication

* New models `UserTwoFactor` and `TwoFactorRecoveryCode`; `two_factor_service`
  with enrolment, confirmation, single-use recovery codes, disable and
  login-time verification.
* Endpoints: `GET /auth/2fa`, `POST /auth/2fa/enrol`, `POST /auth/2fa/confirm`,
  `POST /auth/2fa/disable`.
* Rule: when 2FA is enabled, a valid code (or recovery code) is mandatory at
  login **before** any token is minted — 2FA cannot be bypassed by omitting the
  code. `LoginRequest` gained an optional `code` field; the service enforces it.
* `confirm()` was fixed so it does not consume the TOTP counter (a login
  immediately after confirmation was previously treated as a replay).

## 3. Safety properties verified

* **Append-only / no-retroactive change**: a decided proposal cannot be decided
  again; a rejected proposal leaves the effective policy untouched; lead history
  is never rewritten; a currency change cannot apply before its period.
* **No invented values**: every owner-dependent figure enters through an
  approved record; a draft/request never influences a calculation.
* **RBAC denials**: a role without `accounting_policy.approve` cannot decide a
  proposal; marketing cannot assign a lead.
* **Isolation**: history reads are company-scoped; out-of-scope returns 404.

## 4. Verification evidence

| Check | Result |
|---|---|
| Execution 30 suite `tests/test_execution30_owner_decisions.py` | 30 passed |
| Full suite `python -m pytest tests/ -q` | **964 passed, 0 failed** (exit 0) |
| `alembic upgrade head` on a fresh DB | head `62040b21dfa2` applied |
| `alembic check` | "No new upgrade operations detected." |
| `alembic downgrade -1` → `upgrade head` | reversible, re-applies cleanly |
| RBAC sync | 15 roles, 177 permissions (all catalogued with bilingual metadata) |

### Test-fixture correction

`AccountingPolicy` was missing from the per-test cleanup in `tests/conftest.py`,
so an approved policy leaked across test modules and made
`test_accountant_proposal_is_inert_until_decided` fail only in the full run.
The model is now cleared per test (as its children already were); the test
passes in isolation and in the full suite.

## 5. Decisions already implemented (D02, D10) — verified, not rebuilt

These were part of the authorised set and were completed in Execution 29; they
are re-verified here, not rebuilt:

| ID | Implemented | Test |
|---|---|---|
| D02 | KPI registry + target-versus-actual; a KPI is inert until an authorised approval activates it | `tests/test_kpi_targets.py` |
| D10 | `backend/core/backup.py`: integrity manifest, corruption detection, isolated restore drill | `tests/test_backup_restore.py` |

## 6. Remaining owner-dependent items (NOT implemented, NOT invented)

These are not part of the authorised decision set and remain recorded open per
spec §20. Each is a *value/word* the owner must supply; the mechanism that will
consume it is already live:

| Item | Open item |
|---|---|
| D02 values | goals/KPI target numbers and weekly-template wording (mechanism live) |
| D05 weights | employee/leadership assessment criterion weights (mechanism live) |
| D06 policy | payroll-link policy (manual balances only until approved) |
| D07 values | owner-topic/decision numbering conventions and budget values |
| D08 figures | opening-balance figures for the new period |
| D10 drill | the production restore drill on the production target (tooling exists and is isolated; the drill itself is not run from this workspace) |

## 7. Release readiness — NOT READY

Reasons:

1. The owner-dependent values/words above are unresolved; their parts are
   recorded open and must not be marked complete.
2. The production load test and production backup/restore drill have not been
   executed on the production target (by design — no production access).

Everything audited on this branch — the authorised decisions, migrations,
RBAC, isolation, and the full automated suite — passes. On owner supply of the
remaining values plus the production drills, this branch is ready to merge into
`frontend-app-conversion`.

**Next incomplete requirement:** obtain the owner's values/approval for the D02/
D05/D06/D07/D08 items above and run the production load test + backup/restore
drill.
