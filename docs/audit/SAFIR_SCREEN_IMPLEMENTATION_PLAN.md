# SAFIR Holding — Screen Implementation Plan (gap remediation map)

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`, `SAFIR_SPECIFICATION_GAP_MATRIX.md`
**Specification:** `Platform_Executive_Specifications_v1.docx`
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

> **Purpose:** for every specification screen, name the exact existing artifacts to
> *preserve* and the exact artifacts to *add*, so remediation work is mechanical and
> auditable. This is a **plan**, not implementation — no code was changed in EXECUTION 01.
> Each screen is gated by its `Dxx` decision where applicable.

Conventions to follow when building (mandatory, per repository rules):
- Add a **permission code** in `backend/rbac/permissions.py` + `permission_metadata.py`;
  never branch on a role name.
- Enforce company scope in `backend/repositories/scoped.py` (SQL filter), and use
  `require_company_access`; out-of-scope ⇒ 404.
- Add an **Alembic migration** maintaining a single linear head.
- Add **tests** under `tests/` mirroring `test_isolation.py` patterns.
- Preserve AR/EN + RTL/LTR via `dual()` and `role_permissions` bilingual metadata.

---

## S01 — Home / dashboard
- **Preserve:** `api/v1/dashboard.py`, `services/dashboard_service.py`, `app.js` board.
- **Add:** role-aware short summary + alerts block; owner priorities/decision deep-links;
  motivational sentence for scoped roles; per-metric drill-down targets.
- **Guard:** never surface complaints or leadership to non-owner (already true).

## S02 — Company page
- **Preserve:** `/companies`, `/dashboard/company/{id}`, structure endpoints.
- **Add:** company-scoped employees panel, projects panel, owner notes panel.
- **Gate:** D03 (project states).

## S03 — Add company / sector (F-01)
- **Preserve:** `Company` model + `/companies` CRUD, `admin_service`.
- **Add:** `Sector` entity (AR/EN label, status) + CRUD; F-01 field set; currency-change
  rule (D09).

## S04 — Opening & carry-forward balances (F-02) 🔒 D08
- **Add:** `OpeningBalance` model (type, date, bank, cash, debts, receivables, currency,
  company_id) + service + endpoints; S04 view.
- **Rule:** opening balances are **balances**, not revenue.

## S05 — Monthly financial summary (F-03) + bank statement 🔒 D01/D10
- **Preserve:** `MonthlyReport`, `MonthlyReportFinancialReview`, attachments, dashboard feed.
- **Add:** `FinancialPeriod` (company, year, month, effective_version_id),
  `FinancialSummaryVersion` (number, previous_version_id, status, entered/effective values,
  balances, currency), `BankAttachment`; submit-with-bank-statement; versioned views.

## S06 — Special financial items (F-04) 🔒 D01/D09
- **Add:** `FinancialItemValue` (amount, reason, note, snapshot of name/category/calc rule)
  linked to a summary version; classification + inclusion rule engine (adds / included).

## S07 — Financial field builder 🔒 D01
- **Preserve:** generic `forms.py` field/version machinery.
- **Add:** `FieldDefinition` + `FieldRevision` (type, category, calc rule, scope, mandatory,
  order, status, AR/EN) with **historical snapshot** semantics for the financial summary.
- **UI:** admin → field configuration under “ماليات الشركات” without adding a sixth section
  for the accountant.

## S08 — Accountant review & correction 🔒 D01
- **Preserve:** `review_financially` verified-figures feed.
- **Add:** explicit decisions **approve / return** (mandatory note); version chain; keep the
  previously approved version retained and not double-counted; correction-for-review state.

## S09 — Subsidiary monthly report (F-07)
- **Preserve:** narrative fields on `MonthlyReport`.
- **Add:** link to the financial part + its review status; correction version; BD analysis
  summary; archive view.

## S10 — Company performance
- **Preserve:** `_company_performance`.
- **Add:** goals vs results, comparison, period/currency filters (multi-currency guard).

## S11 — Employees 🔒 D06
- **Add:** `Position`, `Employee` (company, name, number, position, manager, status, salary,
  allowances), `EmployeeAction`, `Leave`, `Advance`.
- **Rules:** adding an employee does **not** auto-create a login; BD cannot edit a
  subsidiary employee’s salary; holding separation cannot exceed an owner decision.

## S12 — Employee assessment / development 🔒 D05
- **Add:** `Assessment`, `Criterion` (weights per Table 72), evidence, gaps; visibility per D04.

## S13 — Leads & distribution 🔒 D03/D04
- **Preserve:** `WebsiteLead` + `/leads`.
- **Add:** separate manager vs marketing note authorship; redistribution + history;
  approved pipeline states.

## S14 — Campaigns 🔒 D02
- **Add:** `Campaign` (name, company, platform, goal, period, budget, spend, lead count,
  currency, status); external execution noted; no ad API.

## S15 — Complaints (owner-only)
- **Add:** `Complaint` + submission (marketing) and owner decision (route/handle/postpone);
  notify owner only; exclude from counters/search/public log.

## S16 — Service & design requests 🔒 D03
- **Preserve:** `SupportRequest` + comments/attachments.
- **Add:** design fields (sizes, platform, reference link), direct-to-specialist delivery,
  external delivery link, close/reopen/cancel once approved.

## S17 — Tasks 🔒 D03
- **Add:** first-class `Task` entity (assignee, status, due/overdue, completion).

## S18 — Weekly employee report 🔒 D02
- **Add:** weekly report with ≤5 questions incl. advisor-utilisation; draft/submit; previous
  periods; reuse existing task/request data (do not duplicate counts).

## S19 — Advisory sessions 🔒 D04
- **Add:** role `external_consultant`; `AdvisorAssignment`, `Session`, `Recommendation`;
  monthly report to BD; unified advisor UI with per-advisor data scope; no approve/edit.

## S20 — Projects & opportunities 🔒 D03
- **Add:** `Opportunity`, `Project` (type, company, description, period, results, resources,
  states); owner decision linkage.

## S21 — Management reports
- **Preserve:** `analytics/*`, `/monthly-reports`.
- **Add:** BD monthly five-axis brief (≤½ page) with escalation; owner company-report archive.

## S22 — Owner decisions 🔒 D04/D07
- **Add:** `OwnerTopic`, `Decision`, `Directive` (recipient, text, status, execution log,
  archive); decision notifies only the designated recipient; no auto-approval chain.

## S23 — Leadership assessment (confidential) 🔒 D05
- **Add:** `Assessment`/`OwnerNote` for leaders; AI evidence analysis;
  **owner-only** access; excluded from counters, search, public log; AI outage must not
  fabricate a score. Custom role deny-list so a custom all-buttons role still cannot reach it.

## S24 — Organization structure
- **Preserve:** holdings/ownership/departments.
- **Add:** legal-function node, `Position` + reporting lines; keep accounting scope bounds.

## S25 — Settings & permissions
- **Preserve:** users/roles/permissions/audit/company-scope.
- **Add:** notification preferences; login/recovery method (D11); activity log view.

## S26 — Holding accounts & journals 🔒 D01
- **Add:** `Account` (chart), `Journal`, `JournalLine` (debit/credit/date/reference/currency);
  balance validation; single-source posting; no duplicate posting. **No bank-transfer button.**

## S27 — Invoices & receivables 🔒 D01
- **Add:** `Party`, `Invoice`, `InvoiceLine`, `Settlement`, `CompanyInterbalance`; one source
  reference per invoice/entry; settlements recorded after external execution; no bank action.

## S28 — Assets, budget & financial reports 🔒 D01/D07
- **Add:** `Asset`, `Budget`, internal statements/trial balance; group report distinguishes
  holding vs subsidiary summaries without claiming consolidation; over-budget ⇒ explicit
  escalation, no automatic payment approval.

---

## Cross-cutting workstreams

| Workstream | Deliverable |
|---|---|
| Financial core | `FinancialPeriod` + `FinancialSummaryVersion` + `FinancialItemValue` + field snapshots; exactly-one-effective-version; no-duplicate-post constraints. |
| Notifications | New event types for each module; secret entities never notified to unauthorized recipients (spec Table 73). |
| Audit | Extend `AuditAction` for every new mutation; before/after for sensitive changes (spec §17). |
| i18n | Bilingual labels for every new role/permission/field; RTL/LTR tested. |
| Tests | Per-screen: RBAC, isolation, workflow transitions, acceptance criteria; keep the suite green. |
| Migrations | One linear chain; update `tests/test_postgres.py` head assertion. |
| Portability | Replace `server_default=sa.text("0")` / `"0"` with `sa.false()` for Boolean columns. |

## Definition of “complete” (spec §20)

A screen is complete only when its AC passes **and** the related cross-cutting tests pass.
An open `Dxx` decision leaves the affected part **open**, never marked complete.
