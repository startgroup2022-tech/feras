# SAFIR Holding — Specification Gap Matrix

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`
**Specification:** `Platform_Executive_Specifications_v1.docx`
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

Status legend: ✅ COMPLETE · 🟡 PARTIAL · ❌ MISSING · 🔒 BLOCKED (needs Dxx).

Every row cites the concrete backend artifact that exists (or states its absence).
"Referenced by spec" columns use the specification's own S-codes and document sections.

---

## A. Screen-by-screen (S01 – S28)

| S | Screen (spec) | Referenced by | Current implementation (evidence) | Status | Gap / notes |
|---|---|---|---|---|---|
| S01 | Home / dashboard | §6, T01, Table 75 | `api/v1/dashboard.py`; `services/dashboard_service.py`; frontend `board` | 🟡 | Role/language/period + short summary + alerts present for holding/company. **Missing:** owner priorities/decision links, motivational sentence for scoped roles, drill-down to each metric target. Explicitly must **not** show complaints/leadership to non-owner. |
| S02 | Company page | §6, T03 | `/companies`, `/dashboard/company/{id}`, `/admin/holding/structure` | 🟡 | Definition/currency/status + performance/reports present. **Missing:** company-scoped employees and projects panels; owner notes. |
| S03 | Add company / sector (F-01) | أ4 | `POST /companies`, `admin_service`; `Company.sector` string | 🟡 | Company CRUD exists. **Missing:** managed `Sector` entity/list, F-01 exact field set, currency-change rule (D09). |
| S04 | Opening & carry-forward balances (F-02) | أ5 | — | ❌ 🔒 | No `OpeningBalance` model. BLOCKED on D08 (annual carry-forward source). |
| S05 | Monthly financial summary (F-03) | أ6, T05 | `MonthlyReport` (`report.py`), `/monthly-reports` | 🟡 🔒 | Revenue/expenses/net/receivables + attachments exist. **Missing:** bank/cash balances, special items, bank statement attachment type, version identity, submit/return/correct lifecycle, exactly-one-effective-version. BLOCKED on D01/D09/D10. |
| S06 | Special financial items (F-04) | أ7, T08 | — | ❌ 🔒 | No `FinancialItemValue` / inclusion-rule model. BLOCKED on D01 (example 1000/600/50/20/200 = 380 is test-only). |
| S07 | Flexible fields / field builder | أ8, T09 | `models/forms.py`, `services/form_service.py`, `/forms` | 🟡 | Generic dynamic fields with versions exist. **Missing:** *financial* field definitions (type, category, calc rule, scope, mandatory, order, bilingual) with historical snapshots feeding the summary. |
| S08 | Accountant review & correction | أ9, T06 | `review_financially` in `report_service.py`, `/monthly-reports/{id}/financial-review` | 🟡 🔒 | Accurate/flagged + verified figures exist and feed the dashboard. **Missing:** explicit approve / return-for-correction with **mandatory note**, version chain, old approved version retained while a correction is pending, correction does not double the month. BLOCKED on D01. |
| S09 | Subsidiary monthly report (F-07) | أ10, T12 | `MonthlyReport` narrative fields + `/reports` | 🟡 | Narrative fields present. **Missing:** link to the financial part + its review status; correction version; BD five-axis analysis summary. |
| S10 | Company performance | §6, T12 | `dashboard_service._company_performance` | 🟡 | Performance metrics exist. **Missing:** goals vs results, comparison view, period/currency filters. |
| S11 | Employees (حسب الشركات) | §8, D06 | — | ❌ 🔒 | No `Position`/`Employee`/`EmployeeAction`/`Leave`/`Advance`. BLOCKED on D06 (manual vs computed balances). |
| S12 | Employee assessment & development | D05 | — | ❌ 🔒 | Weights are in the spec (Table 72) but no `Assessment`/`Criterion`. Grade scale BLOCKED on D05. |
| S13 | Leads & distribution | §11, T03 | `models/website.py` `WebsiteLead` + `/leads` | 🟡 🔒 | Lead capture, assignment, statuses, notes, isolation exist. **Missing:** manager-note vs marketing-note separation, redistribution + history visibility (D04), pipeline state list (D03). |
| S14 | Campaigns | §11 | — | ❌ | No `Campaign` model. External execution is intentional; the platform must store budget/results manually. |
| S15 | Customer complaints (owner-only) | D04, T04 | — | ❌ | No `Complaint` model/endpoint. Must notify owner only, never appear in counters/search/public log. |
| S16 | Service & design requests | §9, T03 | `models/support.py` `SupportRequest` + `/support-requests` | 🟡 🔒 | Generic requests with category/comment/attachment exist. **Missing:** design fields (sizes, platform, reference link), direct send to specialist, delivery external link, close/reopen/cancel (D03). |
| S17 | Tasks | §9 | (approvals engine only) | ❌ 🔒 | No first-class `Task` entity for BD-assigned work. Cancellation/reopen/acceptance BLOCKED on D03. |
| S18 | Weekly employee report | §12, T12 | — | ❌ 🔒 | No weekly report, no ≤5-question set incl. advisor evaluation. Question wording BLOCKED on D02. |
| S19 | Advisory sessions (3 advisors) | §13, T04 | — | ❌ 🔒 | No `AdvisorAssignment`/`Session`/`Recommendation`; no `external_consultant` role. Advisor data scope BLOCKED on D04. |
| S20 | Projects & opportunities | §8 | (public opportunities only) | ❌ 🔒 | Public opportunity listing exists; owner/BD project & opportunity tracking does not. Transition/closure states BLOCKED on D03. |
| S21 | Management reports | §16, T12 | `/analytics/*`, `/reports` | 🟡 | Reporting/analytics exist. **Missing:** BD monthly five-axis brief (≤½ page) with escalation, tied to source reports. |
| S22 | Owner decisions | D04 | — | ❌ | No `OwnerTopic`/`Decision`/`Directive`. |
| S23 | Leadership assessment centre (confidential) | §16, T02, T14 | — | ❌ 🔒 | No model; AI leadership assessment + owner notes missing. Grade/evidence rules BLOCKED on D05. Must be owner-only and excluded from public counters/logs. |
| S24 | Organization structure | T11, T13 | `/admin/holding/structure`, `Department`, `Ownership`, `Holding` | 🟡 | Ownership/departments/holdings exist. **Missing:** legal function node, positions & reporting lines; no separate HR/documents section (intentional). |
| S25 | Settings & permissions | التصور Table 75 | `/admin/users`, `/admin/roles`, `/admin/permissions/catalogue`, `/admin/audit-logs` | 🟡 | Users/roles/permissions/audit/company-scope complete. **Missing:** notification preferences, login method (D11). RBAC correctness (server-side, per-button) is COMPLETE. |
| S26 | Holding accounts & journals | §15, T16 | — | ❌ 🔒 | No chart of accounts, journal, journal line. **Must not** add a bank-transfer button. BLOCKED on D01. |
| S27 | Invoices & receivables | §15, T16 | — | ❌ 🔒 | No `Party`/`Invoice`/`InvoiceLine`/`Settlement`. BLOCKED on D01. |
| S28 | Assets, budget & financial reports | §15 | — | ❌ 🔒 | No `Asset`/`Budget`. BLOCKED on D01 (accounting) and D07 (budget source). |

---

## B. Role / dashboard list coverage (spec §22.1, Tables 79–85)

| Role | Approved top sections (spec) | Current nav/view | Status |
|---|---|---|---|
| Holding Owner | Home, Subsidiaries, Reports, Projects, Owner decisions, Leadership centre, Org structure, Employees, Settings | dashboard, subsidiaries, reports, analytics, admin | 🟡 partial (no decisions/leadership/projects/employees) |
| Business Development | Subsidiaries, Employees & development, Tasks & requests, Projects, Reports & decisions, Holding finance | dashboard, subsidiaries, reports, support, requests, approvals, leads, analytics, admin(partial), bi, inbox | 🟡 partial |
| Subsidiary Manager | Company performance, Employees, Leads, Service requests, Monthly report, Owner directives | dashboard, subsidiaries, reports, support, requests, approvals, inbox, leads | 🟡 partial |
| Accountant | Holding accounts, Invoices, Company finance, Financial reports, Tasks | dashboard, reports, analytics, support, requests, approvals, documents, inbox | 🟡 partial (holding finance entirely missing) |
| Marketing | Leads, Campaigns, Complaints, Tasks, Performance & reports | dashboard, leads, support, requests, approvals, admin→website, analytics, inbox | 🟡 partial (campaigns/complaints missing) |
| Designer | Design requests, My work, Completed work, Performance & weekly report | dashboard, support, requests, approvals, inbox | 🟡 partial |
| External Consultant | Weekly meetings, Assigned employees, Notes & recommendations, Monthly report | — | ❌ missing |

**Nav enforcement is correct:** `NAV_PERM` in `frontend/app.js` gates every view by
permission and calls `navTo`/`toast` when denied; the backend re-checks server-side.

---

## C. Financial workflow gap (the critical path)

Spec §14.1 financial state machine (Table 68):

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
| Create draft | `create_report` (one per company+month) | ✅ (as single report, not versioned) |
| Send with bank statement | `submit_report` requires revenue+expenses; no bank-statement requirement | 🟡 |
| Return for correction w/ mandatory note | **absent** — review is accurate/flagged only | ❌ |
| Approve → closed | review sets `reviewed` when accurate | 🟡 (no explicit close/effective marker) |
| Create linked correction version | **absent** | ❌ |
| One effective approved version | **absent** — one report + one review row | ❌ |
| Correction must not double the month | not applicable (no versions) | ❌ |
| Prevent duplicate submit/posting | no idempotency guard on submit (re-submit blocked only by status != draft) | 🟡 |

**Data-model divergence:** the specification’s `FinancialPeriod (1) → FinancialSummaryVersion (N) →
FinancialItemValue/Review/Attachment` is not implemented. The current model is a single
`MonthlyReport` + single `MonthlyReportFinancialReview`. This is the largest structural gap
and it gates S05, S06, S08, S26–S28 and AC-05/06/08/26/27/28.

---

## D. Cross-cutting acceptance criteria (spec §20, T01–T18)

| Test | Requirement | Current status | Evidence |
|---|---|---|---|
| T01 | AR/EN full journey, mobile+desktop, no untranslated text/clipped buttons; entered text unchanged | ✅ | `test_website_pages.py`, frontend i18n; internal-UI AR/EN covered |
| T02 | Role isolation; custom role cannot reach owner leadership | 🟡 | Isolation ✅ (`test_isolation.py`); leadership module absent so the "cannot reach" half is unverifiable; no custom-role deny-list |
| T03 | Direct manager→designer request, notifies BD, no BD pre-approval | 🟡 | Support requests notify assigned role; design-specific flow missing |
| T04 | Complaint logged; owner only notified; no counter/log leak | ❌ | No complaints module |
| T05 | Financial cycle draft→send→return→correct→approve; accountant cannot change numbers; every version tracked | ❌ | Versioning/correction absent |
| T06 | Correction: old effective until approval, then new only, old retained | ❌ | Absent |
| T07 | Duplicate submit/post does not double record/entry/notification; one effective version | 🟡 | Support/report duplicate-create guarded; no posting engine |
| T08 | Item calculation 1000/600/50-incl/20-add/200-transfer → 380, cash independent | ❌ 🔒 | No inclusion/adds rule (D01) |
| T09 | Add sector field, rename, disable; past keeps historical meaning/snapshot | 🟡 | Generic form field versioning exists; financial field snapshots absent |
| T10 | No currency mixing; no balance posted as revenue; no month-end balances summed as flows | 🟡 | Money is `NUMERIC(18,2)` ✅; multi-currency aggregation guard absent |
| T11 | Add company/sector/manager without code change; no subsidiary reports to BD | 🟡 | Company/sector dynamic; manager creation ✅; org hierarchy rules partial |
| T12 | Owner opens company source directly; BD analyses without edit; brief ≤½ page | 🟡 | Read/analysis paths exist; brief generation absent |
| T13 | Accountant 5 sections / marketing 5 / designer 4; no payment/legal/ads active | 🟡 | Nav shows fewer; holding-account sections missing entirely |
| T14 | AI evidence-gap and outage do not invent a score; owner note is secret context; no automatic penalty | 🟡 🔒 | AI available; assessment module absent |
| T15 | Concurrent saves show conflict not overwrite; failed upload/save not reported as success | 🟡 | Version/optimistic-lock not on financial summary; storage errors surfaced |
| T16 | After D01: journals/trial balance/invoices/receivables reconcile; source posts once | ❌ 🔒 | Module absent |
| T17 | After D10: restore company/versions/attachments/permissions without leak/loss | 🟡 🔒 | Documented, not implemented (D10) |
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
- Dynamic forms / requirements / workflows / approvals / documents.
- Notifications + audit log + integrations/webhooks.
- Phase 10 leads/opportunities and Phase 11 website CMS (`website_*`, `test_website_*`).
- Migration single linear head `d1e2f3a4b5c6` (`test_postgres.py`).
- Full suite: **575 passed**.
