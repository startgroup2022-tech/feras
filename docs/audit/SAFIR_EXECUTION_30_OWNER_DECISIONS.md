# Execution 30 — Owner Decisions Implementation & Final Release Gate

Branch: `feature/safir-execution-30-owner-decisions`
Base: `frontend-app-conversion` @ `c449706c1c5875ef8b1485b55ead0d5591d75214`
(merge of PR #5, "S26–S28 accounting completion").

This checkpoint records the implementation of the owner-authorised decisions
**D01, D03, D04, D09, D11** on top of the Execution 29 baseline, plus the
verification evidence gathered at the final release gate.

## 1. Authorisation

The owner explicitly authorised implementation of **D01, D03, D04, D09, D11**.
Not authorised: inventing unspecified financial values, destructive production
operations, or deployment. Every value that a decision leaves to the owner
(depreciation rates, fiscal-year dates, invoice/asset policy, the base currency
of a company, KPI targets) is supplied through an **approved record**, never
hard-coded.

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

## 5. Remaining owner-dependent decisions (NOT implemented, NOT invented)

These are outside the authorised set and remain recorded open per spec §20:

| ID | Open item |
|---|---|
| D02 | goals/KPI target values and weekly-template wording (the *mechanism* is live: KPI registry + target-vs-actual; only the owner's numbers are open) |
| D05 | employee/leadership assessment weights (mechanism exists; weights are owner-set) |
| D06 | payroll-link policy (manual balances only until approved) |
| D07 | owner-topic/decision numbering conventions and budget values |
| D08 | opening-balance figures for the new period |
| D10 | production restore drill on the production target (tooling exists and is isolated; the drill itself is not run from this workspace) |

## 6. Release readiness — NOT READY

Reasons:

1. The owner-dependent decisions above are unresolved; their parts are recorded
   open and must not be marked complete.
2. The production load test and production backup/restore drill have not been
   executed on the production target (by design — no production access).

Everything audited on this branch — the authorised decisions, migrations,
RBAC, isolation, and the full automated suite — passes. On owner approval of the
remaining decisions plus the production drills, this branch is ready to merge
into `frontend-app-conversion`.

**Next incomplete requirement:** obtain owner values/approval for D02/D05/D06/
D07/D08 and run the production load test + backup/restore drill.
