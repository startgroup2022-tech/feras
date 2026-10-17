# Execution 30 — Owner Decisions Implementation & Final Release Gate

Branch: `feature/safir-execution-30-owner-decisions`
Base: `frontend-app-conversion` @ `c449706c1c5875ef8b1485b55ead0d5591d75214`
(merge of PR #5, "S26–S28 accounting completion").

**Authoritative source:** `docs/reference/Platform_Executive_Specifications_v1.docx`
(original Word file, present in the repository and read directly for this
checkpoint — 76 227 characters of body text; §21 lists the D01–D11 open points,
§20 the acceptance criteria, §14–§17 the workflows). This supersedes any earlier
note that the Word file was missing: it is committed on
`frontend-app-conversion` and was re-read here.

## 1. Authorisation and the spec's own rule

The owner authorised implementation of **D01, D02, D03, D04, D09, D10, D11**.
Not authorised: inventing unspecified financial values, destructive production
operations, or deployment.

Spec §21 is explicit that each D-item is an *unresolved point*, not an approved
requirement, and that "the owner's decision is fixed with a date and reference
before the affected rule is implemented" (`يثبت قرار المالك بتاريخ ومرجع قبل
تنفيذ القاعدة المتأثرة`). Accordingly every value the decision leaves to the
owner (depreciation method/rate, fiscal year, tax, invoice/asset policy, the
base currency of a company, KPI targets and goal numbers) enters through an
**approved record** — never hard-coded. What this execution builds is the
*governance mechanism* (proposal → owner decision → activation) plus the
audit/append-only safety properties, not any financial value.

## 2. Authoritative D01–D11 mapping (spec §21) vs. this branch

| ID | Spec §21 subject (authoritative) | Screens | On this branch |
|---|---|---|---|
| D01 | Holding accounting setup: currency, fiscal year, chart of accounts, invoice timing, settlements, tax, assets | S26–S28 (+ S05/S06/S08) | **Mechanism built**: `PolicyProposal` governance (accountant proposes, owner decides, inert until decided); chart of accounts / journals / fiscal periods exist. **Values open.** |
| D02 | Report forms & indicators: the 5 questions, indicator definitions, goals, campaign lead count | S09–S10, S14, S18, S21 | **Mechanism built** (Execution 29): KPI registry + target-vs-actual, inert until an authorised approval. **Values/wording open.** |
| D03 | **Non-financial work states**: authority to close/return/cancel a request, customer/project states, **correction of the non-financial (management) report** | S13, S16–S22 | **COMPLETE (Execution 31).** Task and support lifecycles (New→In-Progress→Awaiting Review→Complete + Return/Cancel/Reopen), project/opportunity states, **and the post-submission management-report correction (S09) now exist** as a linked, versioned workflow. See `SAFIR_EXECUTION_31_D03_REPORT_CORRECTION.md`. |
| D04 | **Employee & advisor visibility**, including **lead redistribution** and who sees the distribution history | S12, S13, S19, S23 | **Mechanism built**: append-only `LeadAssignment` history + `website_lead.assign` + scoped history reads (`history.read`); `ConfidentialAccessGrant` for delegated confidential access. |
| D05 | Assessment grades & AI data: 1–5 scale, evidence-gap handling | S12, S23 | Mechanism exists (Execution 29): `Assessment`/`AssessmentItem`, evidence-gap rule. Weights/scales are owner data. |
| D06 | Employee balances & actions: manual vs computed, payroll link | S11 | Manual admin records only; no automatic payroll link (as recommended). |
| D07 | Budget source & update: who records it, reference, over-budget detection | S22, S28 | `Budget` preserves source + version; explicit escalation without blocking payment. |
| D08 | Annual carry-forward source | S04 | `OpeningBalance` submit/approve; no automatic December copy. |
| D09 | **Currency change & calc details**: preserve historical currency, no conversion before an approved rule/rate/date | S03, S06, S07, S10 | **Mechanism built**: `CurrencyChangeRequest` (requested→reviewed→approved/rejected→scheduled→applied), cannot apply before its effective period; the no-mixing guard is live. |
| D10 | Bank attachment, protection & restore | S05, S08, technical | `backend/core/storage.py` upload limits + per-company protection; `backend/core/backup.py` integrity + isolated restore drill (Execution 29). Production drill open. |
| D11 | **Login & notification channels & timing**: login method, multi-assignment, time zone, external channels | S01, S25 | **Mechanism built**: internal notification centre (base) + per-event preferences; **2FA (TOTP) with recovery codes and login enforcement**. External channels (WhatsApp/email) not added without a request. |

## 3. What this execution added

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

### D04 — lead redistribution history + scoped visibility

* New model `LeadAssignment` (append-only). Every assignment or reassignment
  writes an immutable history row with the previous assignee, the actor and a
  reason; a reassignment **requires** a reason.
* Endpoints: `POST /leads/{id}/assign`, `GET /leads/{id}/assignments`.
* New permission `website_lead.assign` (distinct from `website_lead.manage`).
* `GET /leads/{id}/assignments` is scoped server-side: a company-confined role
  never sees another company's lead history; "not yours" and "does not exist"
  both return 404 (no existence disclosure). New permission `history.read` (BD
  reads the change/distribution history it needs); bilingual metadata added.

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

## 4. Safety properties verified

* **Append-only / no-retroactive change**: a decided proposal cannot be decided
  again; a rejected proposal leaves the effective policy untouched; lead history
  is never rewritten; a currency change cannot apply before its period.
* **No invented values**: every owner-dependent figure enters through an
  approved record; a draft/request never influences a calculation.
* **RBAC denials**: a role without `accounting_policy.approve` cannot decide a
  proposal; a role without `website_lead.assign` cannot assign a lead.
* **Isolation**: history reads are company-scoped; out-of-scope returns 404.

## 5. Verification evidence

| Check | Result |
|---|---|
| Execution 30 suite `tests/test_execution30_owner_decisions.py` | **18 passed** (corrected from an earlier "30") |
| Full suite `python -m pytest tests/ -q` | **946 collected, exit 0** (corrected from an earlier "964") |
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

## 6. Functional gap found (correction of an earlier claim)

> **Resolved in Execution 31** — the missing D03 linked correction version of the
> non-financial management report (S09) is now implemented. See
> `SAFIR_EXECUTION_31_D03_REPORT_CORRECTION.md`. The paragraph below is kept for
> the record.

An earlier version of this checkpoint labelled lead assignment as "D03". Per the
authoritative spec §21, lead redistribution belongs to **D04**, and **D03 is the
non-financial work states**. The label has been corrected in the models,
services, schemas, API, permissions and tests. The substantive consequence is
that D03 is **PARTIAL**, not complete:

* Present: task lifecycle (New → In-Progress → Awaiting Review → Complete, plus
  Return / Cancel / Reopen, each audited via `TaskEvent`); support-request
  lifecycle (New → In-Progress → Completed → Closed + reopen); project/opportunity
  record types.
* **Missing: the linked correction version of the non-financial monthly
  management report** (S09). The spec says correcting the management report
  after submission "needs D03" and must be a correction version *linked to the
  original*, with the original preserved. Today `MonthlyReport` is
  one-per-company-per-period (`uq_report_company_period`) with a short status
  lifecycle and no correction link; editing is blocked once submitted. Building
  this properly requires a schema change (relaxing the per-period uniqueness to
  allow a linked correction version) and is the next incomplete requirement.

This gap is recorded rather than papered over, consistent with spec §20 ("any
effective open D-decision is recorded as open and its part is never marked
complete").

## 7. Release readiness — NOT READY

Reasons:

1. **D03 is partial** (non-financial report correction missing — §6).
2. The remaining owner-dependent *values/words* are unresolved (D01 values, D02
   goal numbers + template wording, D05 scales, D06 policy, D07 numbering/budget
   values, D08 opening figures, D09 approved conversion rule, D11 external
   channels). Their mechanisms are live; only the owner's data is outstanding.
3. The production load test and production backup/restore drill have not been
   executed on the production target (by design — no production access).

Everything audited on this branch — the authorised mechanisms, migrations,
RBAC, isolation, and the automated suite — passes. It is **not** release-ready.

**Next incomplete requirement:** implement the D03 linked correction version for
the non-financial management report (S09), then obtain the owner's values for the
items in §7.2 and run the production load test + backup/restore drill.
