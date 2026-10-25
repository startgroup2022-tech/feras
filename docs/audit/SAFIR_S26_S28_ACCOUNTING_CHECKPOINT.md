# S26–S28 accounting completion — checkpoint

Branch: `feature/safir-s26-s28-accounting-completion` (off the integration
baseline `frontend-app-conversion` @ `abfcd0de5f16640135a68fa6a03079988099857c`).

## What this branch closes

The gap matrix marked S26/S27/S28 as ❌ 🔒. S26 (accounts, journals, trial
balance) and most of S28 (assets, budgets, KPIs) were already built; the genuine
holes were in S27:

1. **No receivable/payable distinction.** An invoice had no direction, so a
   customer invoice and a supplier invoice could not be told apart and an
   "outstanding" total could not be computed without guessing.
2. **No party directory.** The invoice carried a free-text `party_name`; the
   same counterparty could be typed differently on each document.
3. **No inter-company balance register.** Spec §15 requires a holding↔company
   balance that keeps its currency and reason and is never revenue. Nothing
   recorded it.

## What was added

* `InvoiceDirection` enum (`issued` = "مستحق لنا", `received` = "مستحق علينا").
* `Party` model + `POST/GET /accounting/parties` — one directory per company,
  unique name within the company.
* `CompanyInterbalance` model + `POST/GET /accounting/interbalances` — currency
  and reason are stored; the balance is never posted and never becomes revenue.
* `Invoice.direction` + `Invoice.party_id`; `POST/GET /accounting/invoices`
  accepts a direction and validates that an attached party belongs to the
  invoice's company.
* `GET /accounting/receivables` — outstanding receivables and payables, grouped
  by currency so two currencies are never added together (T10); a partial
  settlement reduces the outstanding amount exactly once.
* `GET /accounting/financial-statements` — income statement (revenue, expenses,
  net) and balance sheet (assets, liabilities, equity) from **posted** journals
  only, per currency, with an optional `compare_previous` period. A loss is a
  negative net; an imbalance is reported, never hidden.
* Permissions `party.read/manage`, `interbalance.read/manage` (granted to the
  accountant, read to the owner/finance-manager/BD), with bilingual metadata and
  audit actions `party.created`, `party.updated`, `interbalance.recorded`.
* Frontend: `parties`, `interbalances` and `statements` accounting tabs, a
  receivable/payable summary on the invoices tab, and a direction selector on the
  invoice form.
* Migration `a2b3c4d5e6f7` (additive; batch mode for the SQLite `invoices`
  ALTER). `alembic check` reports no drift.
* Tests: `tests/test_accounting_s27.py` (18 cases) covering the above plus RBAC
  and the frontend wiring.

## What remains (not done on this branch)

These are **not** blocked by a technical gap; they are owner-dependent and were
deliberately left alone (do not invent approvals for D01–D11):

* D01 — depreciation method/rate, tax rate, invoice policy are stored as neutral
  data and wait for accountant-approved configuration.
* D07 — budget source is stored, approval supersedes a version (never overwrites).

The S26–S28 accounting surface is now feature-complete against the recovered
gap matrix.

## 2026-10-14 matrix reconciliation

While closing S28 the whole S01–S28 matrix was re-verified against the tree
because its 2026-10-04 rows below S03 were stale (they described modules that
had since been built). Outcome:

* S03–S09 and S11–S24 are now ✅ (evidence per row in the matrix).
* Still 🟡: S01 (owner-priority ordering / drill-down), S02 and S10
  (goals-vs-results — definition needs **D02**), S25 (notification prefs /
  login method — **D11**).
* Still 🔒: T17 (backup/restore — **D10**).
* S14 campaigns had endpoints and frontend wiring but no behavioural test; two
  real tests were added (`test_campaign_round_trip_records_results_and_is_audited`,
  `test_campaign_write_requires_company_access`).

## S01 priorities field

Table 12 lists ``الأولويات`` as "record links, per access" — it was the one
dashboard field still missing. It is now a real, permission-filtered list
(`dashboard_service._priorities`): open owner decisions (overdue flagged), open
support requests, and companies needing attention, each as a link to its record.
A source is only included when the caller holds its read permission, so a role
never receives a link it cannot open. Rendered in `#prioritiesList`
(`frontend/app.js::hydratePriorities`). Covered by three dashboard tests plus a
frontend-wiring test.

## S01 AC-01 indicator drill-down

AC-01 requires "فتح تفصيل مؤشر يعرض سجلات مصدره" (opening an indicator shows its
source records) and Table 13 defines ``عرض التفاصيل`` as opening the linked
source **without creating a copy**. It is now live:

* `GET /api/v1/dashboard/indicator/{indicator}/sources` →
  `dashboard_service.indicator_sources`, covering `total_revenue`,
  `total_expenses`, `total_net_result`, `reports_submitted`, `reports_missing`,
  `companies_count`/`sector_count`/`structure_count`,
  `companies_requiring_attention`, `open_support_requests` and
  `pending_financial_reviews`. An unknown indicator is 404.
* Every record is read through a scoped repository, so a caller only ever sees
  records inside its own company scope; a report is labelled by company so rows
  are distinguishable.
* Frontend: each KPI tile carries `data-drill` and opens a read-only modal
  (`app.js::openIndicatorSources`, bound at boot by `bindIndicatorDrills`);
  clicking a row navigates to the company, the request or the report.
* Tests: `test_dashboard.py` (source records, no-copy, company scoping, 404,
  attention links) and `test_frontend_domain_views.py::test_s01_indicator_drilldown_is_wired`.

## S26 Table 53 revenue/expense source-line view

Table 53 (`عرض الإيرادات أو المصروفات | يعرض سطور المصدر لا تسجيلًا إضافيًا`)
requires that opening revenue or expenses shows the **source** lines and adds
**no** record. It is now live:

* `GET /api/v1/accounting/ledger-activity?company_id=&account_type=&fiscal_year=&fiscal_month=`
  → `accounting_service.ledger_activity`. It reads the posted `JournalLine`s
  (joined to `Journal` and `Account`), filtered to `revenue`/`expense` accounts,
  and **never writes**. Only `POSTED` journals count, matching the trial balance
  and the financial statements, so the totals reconcile (Table 53 / AC-28).
* Each row carries its source journal (`journal_number`, `entry_date`),
  account code/name, description, signed `amount` and `currency`; the sign is
  derived (credit-normal revenue, debit-normal expense) so the sum of the lines
  equals the statement figure for that account. An unknown `account_type` is 422.
* Frontend: the `ledger` accounting tab (`renderLedgerActivity`) with a
  company/type/year/month picker; rows point back at their source journal.
* Tests: `test_accounting_s27.py` — source lines are returned and add no record,
  totals reconcile with the income statement, the view is company-scoped,
  unknown type is rejected, `journal.read` is required, and the tab is wired.

## Continuation

If work resumes: check out `feature/safir-s26-s28-accounting-completion`, run
`python -m pytest tests/ -q`, then pick the next ❌/🟡 row in
`SAFIR_SPECIFICATION_GAP_MATRIX.md`. The next incomplete requirement is the
D02-dependent goals-vs-results view (S02/S10); it cannot be finished without the
owner's D02 decision.

---

## 2026-10-14 final parity batch — S28 monthly & group financial reports

Re-verified against the *original* Word specification
(`docs/reference/Platform_Executive_Specifications_v1.docx`, now present and
read directly: 28 screens S01–S28 and all 28 acceptance criteria AC-01…AC-28).
The S28 gaps below were genuinely missing and are now closed.

### S28 Table 57 — monthly financial report (``التقرير المالي الشهري``)

"إعداد التقرير المالي الشهري | يسحب الحسابات ويضيف التحليل" — draws the accounts
and adds the analysis, notifying the business-development manager and the owner.

* Model `MonthlyFinancialReport` + migration `d6e7f8a9b0c1` (additive; unique
  company+year+month; provenance to `FinancialSummaryVersion`).
* `accounting_service.generate_monthly_financial_report` draws the **posted**
  journals only (a draft journal is not drawn), keeps figures **per currency**,
  and reconciles with the trial balance (AC-28). Regeneration updates the draft
  in place (one row per period), never a second report.
* `update_report_analysis` (accountant's added analysis), `finalise` (immutable;
  notifies BD + owner; audited), `archive` (read-only history).
* `_scoped_report` returns **404** for an out-of-scope report — "not yours" and
  "does not exist" are indistinguishable.
* API: `GET/POST /accounting/financial-reports`, `PATCH .../{id}/analysis`,
  `POST .../{id}/finalise`, `POST .../{id}/archive`.
* RBAC: `financial_report.read/manage/finalise`, bilingual metadata; the
  company manager reads its own company's report; BD/owner/finance read.

### S28 Table 56 / AC-28 — budget versus actual, no automatic payment approval

"عرض ملخص أو ميزانية | يفتح المصدر والفروق دون اعتماد صرف" and AC-28
"ميزانية متجاوزة لا تنشئ موافقة صرف تلقائية".

* `accounting_service.budget_utilisation` compares the **approved** budget with
  the **posted** expenses for the year, per currency; reports the variance and an
  `over_budget` flag, and always returns `auto_payment_approval: false`.
* API: `GET /accounting/budgets/utilisation` (company-scoped).

### S28 scope — group report (holding vs subsidiary summaries)

"تقرير المجموعة يميز القابضة عن الملخصات التابعة ولا يدعي إلغاء التعاملات للتوحيد".

* `accounting_service.group_financial_report` lists the holding's own posted
  accounts and each subsidiary's **approved** summary separately, per currency,
  and never merges them; `is_consolidated` is `false` with a bilingual
  distinguishing note.
* Holding-wide only: a company-scoped caller is refused (403).
* API: `GET /accounting/financial-reports/group`.

### Frontend

The accounting `reports` tab (`renderFinancialReports`) gained the group-report
panel (gated on `dashboard.holding`); the `budgets` tab gained a "view variances"
action and the variance panel. `node --check frontend/app.js` passes.

### Test evidence

* `python -m pytest tests/test_accounting_s28.py` — 17 cases (generation from
  posted journals, per-currency figures, regeneration, analysis/finalise/archive,
  immutability, company scoping, budget utilisation without approval, group
  separation, holding-wide-only, frontend wiring).
* `python -m pytest tests/ -q` — **926 passed** (2026-10-14).
* `alembic check` — "No new upgrade operations detected." Migration head
  `d6e7f8a9b0c1`.

### Remaining owner-dependent (do not invent)

* **D01** depreciation method/rate, tax/fiscal-year/invoice values are stored as
  neutral data; the accountant supplies and approves the values through the
  policy registry. No assumption is coded.
* **D09** base-currency-change *procedure* (documented rate + date + source and a
  history-preserving switch) is not built; the guard that blocks mixing
  currencies without an approved rule is live.
* **D02** goals-vs-results for S02/S10 and the weekly-template wording are owner
  data.

