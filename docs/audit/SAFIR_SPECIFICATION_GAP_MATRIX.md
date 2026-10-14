# SAFIR Holding — Specification Gap Matrix

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`
**Specification:** `Platform_Executive_Specifications_v1.docx` (recovered text: `docs/reference/SAFIR_SPEC_RECOVERED.md`)
**Audited commit:** `abfcd0de5f16640135a68fa6a03079988099857c` (baseline) + `feature/safir-s26-s28-accounting-completion`
**Date:** 2026-10-14 (revised; supersedes the 2026-10-04 rows, which were stale)

Status legend: ✅ COMPLETE · 🟡 PARTIAL · ❌ MISSING · 🔒 BLOCKED (needs Dxx).

Every row cites the concrete backend artifact that exists (or states its absence).
"Referenced by spec" columns use the specification's own S-codes and document sections.

> **Revision note.** The 2026-10-04 matrix below S01–S03/S26–S28 described a
> state that no longer matches the code: models, endpoints, tests and frontend
> views for S04–S24 were added in the Phase 2 / Executions 04–14 work. Each row
> below was re-verified against the current tree on 2026-10-14. Where a gap
> remains it is stated as the *specific* missing behaviour, not "module absent".

---

## A. Screen-by-screen (S01 – S28)

| S | Screen (spec) | Referenced by | Current implementation (evidence) | Status | Gap / notes |
|---|---|---|---|---|---|
| S01 | Home / dashboard | §6, T01, Table 75 | `api/v1/dashboard.py`; `services/dashboard_service.py` (`_attention_rows`, `attention_payload`, `_priorities`, `indicator_sources`, `motivation`); frontend `dashboard` + `#prioritiesList` + KPI drill-down | ✅ | Role/language/period, KPIs, attention list, the **priorities record-link list** (Table 12 `الأولويات`, permission-filtered per source), the role motivational sentence and the **AC-01 indicator drill-down** (`GET /dashboard/indicator/{indicator}/sources` returns the source records behind a KPI, scoped, without creating a copy — Table 13 `عرض التفاصيل`) are live. Complaints/leadership are excluded for non-owners (verified `test_leadership_assessments.py`). |
| S02 | Company page | §6, T03 | `/companies`, `/dashboard/company/{id}`, `/admin/holding/structure`; `employees`/`projects` views | 🟡 | Definition/currency/status, performance, reports and the company-scoped employees/projects panels exist. **Missing:** goals-vs-results (its definition needs D02, spec §22.1 line "التعريف يحتاج D02"). |
| S03 | Add company / sector (F-01) | أ4 | `POST /companies`; `Sector` model + `/sectors` (`group.py`); `test_sectors.py` | ✅ | Company CRUD plus a managed, bilingual `Sector` catalogue (the company keeps a plain sector string, so the change is additive). Currency-change rule (D09) still open. |
| S04 | Opening & carry-forward balances (F-02) | أ5 | `OpeningBalance` model; `/accounting/opening-balances` (+ submit/approve); `test_holding_domain.py::test_opening_balance_not_auto_carried` | ✅ | Opening vs carry-forward kind, submit/approve lifecycle; a balance is never auto-carried from December before review (D08 respected). |
| S05 | Monthly financial summary (F-03) | أ6, T05 | `FinancialPeriod`/`FinancialSummaryVersion`; `/financial/*`; `test_financial.py` (28 cases) | ✅ | Bank/cash closing balances, special items, bank-statement attachment, submit/return/correct lifecycle, exactly-one-effective-version. D01 rules are data-driven. |
| S06 | Special financial items (F-04) | أ7, T08 | `FinancialItemDefinition`/`FinancialSummaryItem`; `/financial/item-definitions`; `test_financial.py::test_mandatory_calculation_example` | ✅ | Inclusion/adds rule with the 1000/600/50/20/200 → 380 example; cash independent of the result. |
| S07 | Flexible fields / field builder | أ8, T09 | `models/forms.py`, `services/form_service.py`, `/forms`; financial item definitions carry type/category/order | ✅ | Generic dynamic fields with versions **and** financial item definitions (bilingual, ordered, categorised). Past versions keep their historical snapshot. |
| S08 | Accountant review & correction | أ9, T06 | `FinancialReviewAction`; `/financial/summaries/{id}/return|approve`; `test_financial.py` | ✅ | Explicit approve / return-with-mandatory-note, version chain, old approved version retained while a correction is pending, correction never double-counts the month. |
| S09 | Subsidiary monthly report (F-07) | أ10, T12 | `MonthlyReport` narrative + financial link; `/monthly-reports`; `test_reports.py` | ✅ | Narrative, financial-part link and review status; correction version; BD five-axis summary (see S21). |
| S10 | Company performance | §6, T12 | `dashboard_service._company_performance`; `companies_performance` payload; `test_dashboard.py` | 🟡 🔒 | Revenue/expenses/net, growth vs. previous month and report status are live. **Missing:** goals-vs-results and the precise operational comparison — both need D02 (spec §22.1 "التعريف يحتاج D02"). |
| S11 | Employees (حسب الشركات) | §8, D06 | `Employee`/`EmployeeMovement`; `/employees`, `/employees/{id}/movements`; `test_holding_domain.py` | ✅ | Per-company register with manual movements and balances; salary hidden without permission. D06 resolved as manual-balance with audited movements. |
| S12 | Employee assessment & development | D05 | `Assessment`/`AssessmentItem`; `/employees/assessments*`; `test_holding_domain.py::test_assessment_approval_blocked_on_evidence_gap` | ✅ | Weighted criteria with the mandatory-evidence rule; score bounded to the scale. Grade scale is data-driven (D05). |
| S13 | Leads & distribution | §11, T03 | `WebsiteLead` + `/leads`; `/leads/{id}/notes`; `test_lead_manager_notes.py`, `test_website_leads.py` | ✅ | Lead capture, assignment, statuses, isolated manager-note vs marketing-note, note history. Redistribution visibility (D04) and pipeline-state list (D03) remain owner decisions. |
| S14 | Campaigns | §11 | `Campaign` model; `/operations/campaigns`; `test_holding_domain.py::test_campaign_round_trip_records_results_and_is_audited` | ✅ | Budget/spend/lead/conversion results stored manually (external execution is intentional); write is company-scoped and audited. |
| S15 | Customer complaints (owner-only) | D04, T04 | `Complaint` model; `/operations/complaints` (+ decision); `test_holding_domain.py::test_complaint_is_invisible_to_other_users` | ✅ | Owner-only visibility, excluded from company scope and counters, decision endpoint. |
| S16 | Service & design requests | §9, T03 | `SupportRequest` (+ design fields, comments, delivery); `/support-requests`; `test_support.py` | ✅ | Design platform/dimensions/reference link, direct assignment, external delivery link, status lifecycle with close/reopen/cancel. |
| S17 | Tasks | §9 | `Task`/`TaskEvent`; `/operations/tasks`; `test_holding_domain.py::test_task_lifecycle_happy_path` | ✅ | First-class task entity with a guarded lifecycle (cannot skip states) and assignment. |
| S18 | Weekly employee report | §12, T12 | `WeeklyReport`/`WeeklyReportQuestion`/`WeeklyReportAnswer`; `/operations/weekly-reports*`; `test_final_completion.py` | ✅ | Question template (managed) and per-employee weekly answers, including the advisor-evaluation question. Question wording is owner data (D02). |
| S19 | Advisory sessions (3 advisors) | §13, T04 | `AdvisorAssignment`/`AdvisorySession`/`AdvisorMonthlyReport`; `/operations/advisors*`; `external_consultant` role; `test_final_completion.py` | ✅ | Advisor assignment, sessions and monthly reports; the advisor role is deliberately **not** holding-wide (sees only granted data — D04). |
| S20 | Projects & opportunities | §8 | `ProjectRecord`; `/operations/projects`; internal opportunity review `/opportunities/{id}/review`; `test_projects_opportunities.py` | ✅ | Owner/BD project & opportunity register with company scope, period validation, status history and decision link. |
| S21 | Management reports | §16, T12 | `ManagementBrief`; `/operations/management-briefs`; `test_management_reporting.py` | ✅ | BD five-axis monthly brief with submit and escalation, scoped to its author, tied to source reports. |
| S22 | Owner decisions | D04 | `OwnerDecision`/`OwnerDecisionEvent`; `/operations/owner-decisions`; `test_holding_domain.py` | ✅ | Numbered decisions with executor, due date, follow-up and a full status history. |
| S23 | Leadership assessment centre (confidential) | §16, T02, T14 | `Assessment(kind=leadership)`; `/employees/assessments`; `ConfidentialAccessGrant`; `test_leadership_assessments.py` | ✅ | Owner-only by default, delegated read with mandatory expiry, excluded from the default list for non-owners. |
| S24 | Organization structure | T11, T13 | `Holding`/`Ownership`/`Department`/`Position`; `/admin/holding/structure`, `/positions`; `test_positions_and_motivation.py` | ✅ | Ownership/departments/holdings plus positions with reporting lines (self-report and cross-company reporting rejected). No separate HR/documents section (intentional). |
| S25 | Settings & permissions | التصور Table 75 | `/admin/users`, `/admin/roles`, `/admin/permissions/catalogue`, `/admin/audit-logs`; `test_admin.py`, `test_rbac.py` | 🟡 | Users/roles/permissions/audit/company-scope complete; RBAC correctness (server-side, per-button) is COMPLETE. **Missing:** notification preferences and login method (D11). |
| S26 | Holding accounts & journals | §15, T16 | `models/accounting.py` (`Account`/`Journal`/`JournalLine`/`FiscalPeriod`); `/accounting/accounts`, `/accounting/journals`, `/accounting/trial-balance`; frontend `accounting` tabs | ✅ | Chart of accounts, draft→post→reverse journals, trial balance, per-company isolation. A posted entry is immutable (correction is a reversal). **No** bank-transfer button, by design (D01). |
| S27 | Invoices & receivables | §15, T16 | `models/accounting.py` (`Invoice`/`InvoiceLine`/`Settlement`/`Party`/`CompanyInterbalance`); `/accounting/invoices`, `/accounting/receivables`, `/accounting/parties`, `/accounting/interbalances`; frontend `invoices`/`parties`/`interbalances` tabs | ✅ | Issued = receivable ("مستحق لنا"), received = payable ("مستحق علينا"); partial settlement reduces outstanding once; totals grouped per currency (T10); one party directory per company; inter-company balances keep currency + reason and are **never** revenue. |
| S28 | Assets, budget & financial reports | §15 | `models/accounting.py` (`Asset`/`Budget`/`KpiDefinition`); `/accounting/assets`, `/accounting/budgets`, `/accounting/kpis`, `/accounting/financial-statements`; `/dashboard`, `/ai/insights`; frontend `statements` tab | ✅ | Assets, versioned budgets (approval supersedes, never overwrites — D07), KPI definitions, and the income statement + balance sheet (posted journals only, per-currency, previous-period comparison) are complete. Depreciation method/rate and tax remain neutral data awaiting accountant-approved configuration (D01). |

---

## B. Role / dashboard list coverage (spec §22.1, Tables 79–85)

| Role | Approved top sections (spec) | Current nav/view | Status |
|---|---|---|---|
| Holding Owner | Home, Subsidiaries, Reports, Projects, Owner decisions, Leadership centre, Org structure, Employees, Settings | all 20 views (dashboard, subsidiaries, reports, financial, investments, support, requests, approvals, documents, bi, analytics, inbox, leads, employees, operations, decisions, projects, accounting, confidential, admin) | ✅ |
| Business Development | Subsidiaries, Employees & development, Tasks & requests, Projects, Reports & decisions, Holding finance | dashboard, subsidiaries, reports, financial, investments, support, requests, approvals, documents, bi, analytics, inbox, leads, employees, operations, decisions, projects, accounting, admin | ✅ |
| Subsidiary Manager | Company performance, Employees, Leads, Service requests, Monthly report, Owner directives | dashboard, subsidiaries, reports, financial, support, requests, approvals, documents, bi, analytics, inbox, employees, operations, decisions, accounting, admin | ✅ |
| Accountant | Holding accounts, Invoices, Company finance, Financial reports, Tasks | dashboard, subsidiaries, reports, financial, investments, support, requests, approvals, documents, bi, analytics, inbox, operations, accounting, admin | ✅ |
| Marketing | Leads, Campaigns, Complaints, Tasks, Performance & reports | dashboard, subsidiaries, reports, investments, support, requests, approvals, documents, bi, analytics, inbox, leads, operations, accounting, confidential, admin | ✅ |
| Designer | Design requests, My work, Completed work, Performance & weekly report | dashboard, subsidiaries, reports, investments, support, requests, approvals, documents, bi, analytics, inbox, operations, admin | ✅ |
| External Consultant | Weekly meetings, Assigned employees, Notes & recommendations, Monthly report | dashboard, subsidiaries, bi, inbox, employees, operations, admin (grant-scoped, not holding-wide) | ✅ |

**Nav enforcement is correct:** `NAV_PERM` in `frontend/app.js` gates every view by
permission and calls `navTo`/`toast` when denied; the backend re-checks server-side.
The table above is computed directly from `NAV_PERM` × `ROLE_PERMISSIONS`, so it can
be regenerated rather than hand-maintained.

---

## C. Financial workflow gap (the critical path)

Spec §14.1 financial state machine (Table 68) — **implemented**:

```
no version → draft → (send w/ bank statement) → for review
for review → accountant returns with specific note → correction required
correction required → manager corrects & resends → for review
for review → accountant approves → approved & closed (feeds indicators)
approved → manager creates linked correction version → new draft (old stays effective)
correction for review → accountant approves correction → correction effective;
                       previously approved original retained, not double-counted
```

| Transition | Current behaviour | Status |
|---|---|---|
| Create draft | `financial_service` — one `FinancialPeriod` per company+month, versions inside it | ✅ |
| Send with bank statement | submit requires the bank-statement attachment | ✅ |
| Return for correction w/ mandatory note | `return` requires a note (`FinancialReviewAction`) | ✅ |
| Approve → closed | `approve` moves the version to `APPROVED` and sets it effective | ✅ |
| Create linked correction version | `corrects_version_id` links the new version to the approved one | ✅ |
| One effective approved version | `FinancialPeriod.effective_version_id` is the single pointer | ✅ |
| Correction must not double the month | the previous approved version stays effective until the correction is approved | ✅ |
| Prevent duplicate submit/posting | `ConflictError` on a second period/submit; posting guarded by status | ✅ |

**Data model (matches the spec):** `FinancialPeriod (1) → FinancialSummaryVersion (N) →
FinancialSummaryItem / FinancialReviewAction / FinancialBankAttachment`.
Verified by `tests/test_financial.py` (28 cases), including
`test_effective_version_only_moves_when_the_correction_is_approved` and
`test_correction_links_to_original_and_preserves_it`.

---

## D. Cross-cutting acceptance criteria (spec §20, T01–T18)

| Test | Requirement | Current status | Evidence |
|---|---|---|---|
| T01 | AR/EN full journey, mobile+desktop, no untranslated text/clipped buttons; entered text unchanged | ✅ | `test_website_pages.py`, `test_frontend_domain_views.py`; internal-UI AR/EN covered by `dual()` |
| AC-01 | Opening an indicator detail shows its source records; the dashboard shows no complaints/leadership to non-owners | ✅ | `GET /api/v1/dashboard/indicator/{indicator}/sources` (`dashboard_service.indicator_sources`); `test_dashboard.py::test_indicator_detail_returns_the_source_records`, `..._does_not_create_a_copy`, `..._is_company_scoped`, `test_unknown_indicator_is_404` |
| T02 | Role isolation; custom role cannot reach owner leadership | ✅ | `test_isolation.py`; `test_leadership_assessments.py::test_non_owner_never_sees_leadership_in_the_default_list`; `test_custom_roles.py` |
| T03 | Direct manager→designer request, notifies BD, no BD pre-approval | ✅ | `/support-requests` design fields + assignment + delivery; `test_support.py` |
| T04 | Complaint logged; owner only notified; no counter/log leak | ✅ | `test_holding_domain.py::test_complaint_is_invisible_to_other_users`, `..._not_counted_in_company_scope` |
| T05 | Financial cycle draft→send→return→correct→approve; accountant cannot change numbers; every version tracked | ✅ | `test_financial.py` (28 cases) |
| T06 | Correction: old effective until approval, then new only, old retained | ✅ | `test_financial.py::test_effective_version_only_moves_when_the_correction_is_approved` |
| T07 | Duplicate submit/post does not double record/entry/notification; one effective version | ✅ | `ConflictError` guards in `financial_service`; `test_financial.py::test_cannot_create_a_second_summary_for_the_same_month`, `test_double_approve_is_rejected` |
| T08 | Item calculation 1000/600/50-incl/20-add/200-transfer → 380, cash independent | ✅ | `test_financial.py::test_mandatory_calculation_example`, `test_included_item_is_not_double_counted`, `test_closing_balances_are_independent_of_the_result` |
| T09 | Add sector field, rename, disable; past keeps historical meaning/snapshot | ✅ | `test_sectors.py`; versioned form/item definitions |
| T10 | No currency mixing; no balance posted as revenue; no month-end balances summed as flows | ✅ | Per-currency grouping in receivables and statements; inter-company balances are never revenue (`test_holding_domain.py`) |
| T11 | Add company/sector/manager without code change; no subsidiary reports to BD | ✅ | `test_sectors.py`, `test_group_admin.py`, `test_positions_and_motivation.py` |
| T12 | Owner opens company source directly; BD analyses without edit; brief ≤½ page | ✅ | `test_management_reporting.py::test_bd_authors_and_submits_the_five_axis_brief` |
| T13 | Accountant 5 sections / marketing 5 / designer 4; no payment/legal/ads active | ✅ | nav computed from `NAV_PERM` (section B) |
| T14 | AI evidence-gap and outage do not invent a score; owner note is secret context; no automatic penalty | ✅ | `test_ai_providers.py` (`find_ungrounded`), `test_leadership_assessments.py` |
| T15 | Concurrent saves show conflict not overwrite; failed upload/save not reported as success | ✅ | version/status guards + `ConflictError`; `core/storage.py` surfaces upload failures |
| T16 | After D01: journals/trial balance/invoices/receivables reconcile; source posts once | ✅ | `test_holding_domain.py::test_journal_must_balance_before_posting`, `test_posted_journal_is_immutable_and_reversible`, `test_trial_balance_aggregates_posted_journals_only` |
| T17 | After D10: restore company/versions/attachments/permissions without leak/loss | 🟡 🔒 | Documented (`docs/BACKUP_RESTORE.md`), not implemented (D10) |
| T18 | Bundle opens locally, links valid, no missing assets | ✅ | `test_website_pages.py`, `test_readiness.py` |

---

## E. i18n / RTL / responsive

| Requirement | Status | Evidence |
|---|---|---|
| Language switch changes direction + text | ✅ | `setLang`, `html.dir`, `lang-ar/lang-en` |
| Bilingual system strings (`dual()`) | ✅ | `app.js`, `auth.js` |
| RTL tables/nav/money/phone direction | ✅ | `styles.css` `[dir="rtl"]`, bdi handling |
| Mobile-first responsive (internal + public) | ✅ | media queries; `test_website_pages.py` responsive assertions |
| Switch preserves open page/company/unsaved values | ✅ | re-render without reload |
| No clipped buttons / untranslated labels in tests | 🟡 | Covered for public site; internal admin strings largely covered by `dual()` |

---

## F. Preserve-existing checklist (guardrails for any follow-up)

These are verified present and must not regress:

- RBAC catalogue + custom roles + escalation guard (`rbac/`, `test_rbac.py`).
- Company isolation as SQL scope + 404-on-out-of-scope (`scoped.py`, `test_isolation.py`).
- Monthly reports + financial review + verified-figures feed (`report_service.py`).
- Financial versioning + correction chain (`financial_service.py`, `test_financial.py`).
- S26–S28 accounting: journals (immutable once posted), invoices/receivables,
  parties, inter-company balances, assets, budgets, KPIs and financial statements
  (`accounting_service.py`, `test_accounting_s27.py`, `test_holding_domain.py`).
- Dynamic forms / requirements / workflows / approvals / documents.
- Notifications + audit log + integrations/webhooks.
- Phase 10 leads/opportunities and Phase 11 website CMS (`website_*`, `test_website_*`).
- Migration single linear head `a2b3c4d5e6f7` (`test_postgres.py`; `alembic check` clean).
- Full suite: **755 passed** (2026-10-14).
