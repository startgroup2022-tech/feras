# SAFIR Holding — Owner Decisions D01–D11: Register & Implementation Blueprint

**Document received:** "SAFIR HOLDING — Owner Decisions D01–D11 / مسودة اعتماد القرارات
التنفيذية" (proposal draft), 2026-10-11.
**Baseline branch:** `feature/safir-executions-04-11` → target `frontend-app-conversion`.
**Status of the received document:** **DRAFT — NOT YET BINDING.**
**Recorded by:** development agent (OpenHands), on behalf of the platform owner.

---

## 1. Approval status — READ FIRST

The received document labels itself, verbatim:

> **الحالة:** بانتظار اعتماد مالك المنصة
> ("Status: awaiting the platform owner's approval")

> **الاعتماد:** هذه الوثيقة مسودة ولا تصبح ملزمة للتطوير إلا بعد موافقة مالك المنصة
> **ومطابقتها مع المواصفات الأصلية.**
> ("Approval: this document is a draft and does not become binding for development
> until the platform owner approves it **and it is matched against the original
> specifications**.")

Therefore **two preconditions remain unmet**:

1. **Explicit owner approval** of this document has not been recorded here.
2. **Match against the original specification** (`Platform_Executive_Specifications_v1.docx`)
   cannot be performed — that document is still absent from the repository (see
   `SAFIR_EXECUTIONS_04_11_STATUS.md` §1).

Consistent with the specification's own rule §20 (*"any effective open D-decision is
recorded as open and its part is never marked complete"*) and with D01 itself (*"إعداد
الضرائب والسنة المالية وسياسات الفواتير والأصول يتم من خلال إعدادات معتمدة من المحاسب،
وليس بافتراضات برمجية"* — tax/fiscal-year/invoice/asset setup is done through
**approved accountant settings, not programmatic assumptions**), **no module gated by
D01–D11 was implemented from this draft.**

**To proceed, the owner must confirm in writing:** *“I approve decisions D01–D11 as
binding, and they match the original specifications.”* A short reply stating approval
(date + reference) is sufficient; no re-typing of the document is needed.

---

## 2. Decision register (as proposed) + unblocked screens

| ID | Approved rule (as proposed) | Unblocks spec screens | Coding workstream |
|---|---|---|---|
| **D01** | Standalone holding accounting: manageable chart of accounts, double-entry journals, fiscal periods, cost centres, financial reports. Approved entries are never edited in place — correction by reversal or a documented adjustment. Tax, fiscal year, invoice and asset policy come from accountant-approved settings, not code assumptions. | S26, S27, S28 (+ S05/S06/S08 financial parts) | Holding accounting module: `Account`, `Journal`, `JournalLine`, `FiscalPeriod`, `CostCentre`; no in-place edit; reversal/adjustment only. |
| **D02** | Manageable KPIs per company with defined data source, calculation method and period. Weekly report ≤ 5 core questions, customisable by admin permission. | S09, S10, S14, S18, S21 | KPI definitions registry; weekly-report template with ≤5 questions; five-axis management brief. |
| **D03** | Lifecycle: New → In-Progress → Awaiting Review → Complete, plus Return / Cancel / Reopen. Executor updates progress; the authorised manager approves closure; every change is audit-logged. | S13, S16, S17, S20 | First-class `Task`/`ServiceRequest` lifecycle states; audit on every transition. |
| **D04** | Per-company data isolation. Confidential complaints and leadership assessments visible to the owner only by default. The owner may delegate access to a specific record and permission, with an expiry and an audit trail. External consultant sees only explicitly authorised data. | S12, S13, S15, S19, S23 | Record-level delegated access (owner grant → record + permission + expiry + audit); `external_consultant` role with explicit scope; secret entities excluded from counters/search/logs. |
| **D05** | Employee & leadership assessment: 1–5 scale per criterion, weights approvable. An assessment missing mandatory evidence cannot be approved; drafts are saved and gaps shown. Historical assessments retained. | S12, S23 | `Assessment` + `Criterion` (weights), evidence-gap rule, immutable history. |
| **D06** | v1: balances and movements entered by authorised users, with a movement log and approvals. No automatic payroll link and no accounting entries until a linking policy is approved. | S11 | `Employee`, `Position`, leave/advance balances as manual entries + approval log. |
| **D07** | Numbered owner decisions with an owner/executor, due date, follow-up status, attachments and history. Budgets approved by the owner or delegate, preserving source and version; approved values are not replaced without a documented procedure. | S22, S28 (budget) | `OwnerTopic`/`Decision`/`Directive`; `Budget` with source + version; no silent overwrite. |
| **D08** | Opening balance entered by the authorised user, optionally guided by the last approved financial summary. December balance is **not** auto-carried before the new opening balance is reviewed and approved. | S04 | `OpeningBalance`; balances (not revenue); no auto carry-forward. |
| **D09** | Each company has one approved base currency. Amounts kept in their original currency; summing different currencies is blocked without a documented conversion (rate + date + source). Changing the base currency requires a special procedure that preserves historical data. | S03 (currency change), S06, S10 | Multi-currency guard (already partly present in EXECUTION 02 calc); base-currency-change procedure; conversion record. |
| **D10** | Encrypted backups, periodic restore test in an isolated environment, restricted permissions, and documented retention + restore objectives before go-live. No production restore without explicit approval and a recent backup. | technical layer (T17) | Ops/documentation; does not touch production DB from this workspace. |
| **D11** | In-platform notification centre as the base. Email optional per event type and user preference. Sensitive notifications never leak confidential detail in subject/body. Additional channels need separate approval and integration. | S01, S25 | Notification preferences; per-event channel selection; sensitive-payload minimisation. |

**Closed already (do not reopen):** Appendix A — Dec. 1 (correction handling), Dec. 2
(included vs added item), Dec. 3 (currency / no aggregation). These are reflected in the
EXECUTION 02 financial engine.

**Review note (owner's attention):** D05 proposes a **1–5 scale**, whereas the earlier
audit noted the spec's grade scale was undefined. D11 allows **optional email**, whereas
the earlier assumption was internal-only. Both are fine as decisions, but they should be
confirmed as matching the original specification, since the spec cannot be re-read here.

---

## 3. Implementation blueprint (ready to execute on approval)

This follows `SAFIR_SCREEN_IMPLEMENTATION_PLAN.md` conventions exactly: new permission
codes (never role-name branching), company scope in `repositories/scoped.py`, additive
Alembic migrations on the single linear head, bilingual labels, and tests mirroring
`test_isolation.py`. Sequence is D01 first (largest unblock).

### 3.1 Cross-cutting foundation (first PR after approval)
- **Permission codes** (new, danger-flagged where appropriate):
  `holding_account.read/manage`, `journal.read/create/post/reverse`, `invoice.read/manage`,
  `asset.read/manage`, `budget.read/approve`, `opening_balance.read/manage`,
  `kpi.definition.manage`, `campaign.read/manage`, `complaint.create/read_own/decide`,
  `task.read_own/read_all/create/update/status_change`, `weekly_report.read_own/submit`,
  `employee.read/manage`, `assessment.read/manage/approve`, `advisor.session.*`,
  `owner_decision.read/manage`, `leadership_assessment.manage`, `notification.pref.manage`.
- **Delegated confidential access** (D04): table `ConfidentialAccessGrant`
  (`subject_type`, `subject_id`, `grantee_user_id`, `permission_code`, `expires_at`,
  `created_by`, audit trail). Enforced in the scope layer so secret records are invisible
  to everyone but owner + explicit grantees — and excluded from global counters/search.
- **`external_consultant` role** (D04): holding-non-wide; scope = only explicitly granted
  employees/records; no financial ledger, no approvals, no other employees.
- **Portability**: use `sa.false()`/`sa.true()` for Boolean server defaults (already the
  pattern in `58ef167fa236`).

### 3.2 Per-execution slices
- **EXEC 04 (D08, D01-financial):** `OpeningBalance` (company, date, bank, cash, debts,
  receivables, currency, source_summary_version_id) + service + endpoints + S04 view;
  balances are never revenue; no auto December carry.
- **EXEC 05 (D06, D05, D04):** `Position`, `Employee`, `EmployeeAction` (leave/advance as
  manual entries), `Assessment`, `Criterion` (weights), `AssessmentEvidence`; 1–5 scale;
  block approval when evidence missing; immutable history; visibility per D04.
- **EXEC 06 (D03, D02):** `Task` (lifecycle New→In-Progress→Awaiting Review→Complete +
  Return/Cancel/Reopen) with audit on every transition; `WeeklyReport` (≤5 configurable
  questions); no duplicate counting of the same work.
- **EXEC 07 (D02, D03, D04):** `Campaign` (name, company, platform, goal, period, budget,
  spend, lead_count, currency, status) + results; leads redistribution + history;
  manager-note vs marketing-note authorship separation.
- **EXEC 08 (D04):** `Complaint` (marketing submits; owner decides route/handle/postpone);
  owner-only visibility via the grant table; never in counters/search/public log.
- **EXEC 09 (D03):** extend `SupportRequest` for design (sizes, platform, reference link),
  direct-to-specialist delivery, external delivery link, lifecycle states.
- **EXEC 10 (D04):** `AdvisorAssignment`, `AdvisorySession`, `Recommendation`; advisor UI
  with per-advisor explicit scope; monthly report to BD.
- **EXEC 11 (D07, D05, D04):** `OwnerTopic`/`Decision`/`Directive` (numbered, executor, due
  date, follow-up status, attachments, history); confidential **leadership assessment**
  (owner-only, AI evidence with gap display, no fabricated score on outage).
- **EXEC 12 (D01, D07):** holding accounting — `Account`, `Journal`, `JournalLine`,
  `FiscalPeriod`, `CostCentre`, `Party`, `Invoice`, `InvoiceLine`, `Settlement`, `Asset`,
  `Budget`; double-entry balance validation; **no in-place edit** (reversal/adjustment);
  **no bank-transfer endpoint**; trial balance / statements.
- **EXEC 13 (D02, D11):** KPI definitions registry; five-axis management brief; notification
  preferences + per-event optional email with sensitive-payload minimisation.
- **EXEC 14:** i18n/responsive verification matrix for every new screen; full suite green.

### 3.3 Test strategy (per module)
RBAC deny/allow, company isolation (404 on out-of-scope), workflow transitions incl.
return/cancel/reopen, exactly-one-effective where relevant, confidential invisibility
(counters/search/logs), D04 delegated-grant expiry, D05 evidence-gap block, and AR/EN RTL.

---

## 4. What is needed to start

1. **Owner approval line**, e.g.: *“أعتمد القرارات D01–D11 كملزمة ومطابقة للمواصفات
   الأصلية.”* (one line is enough).
2. **The original specification**, if the approval is conditional on matching it.

On receipt, EXEC 04 begins immediately and continues sequentially through EXEC 12, each
committed with tests on the `feature/safir-executions-04-11` branch and the open PR #4.

> **Nothing in this register changes application code, schema, migrations or production.**
