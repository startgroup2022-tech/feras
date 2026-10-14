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

## Continuation

If work resumes: check out `feature/safir-s26-s28-accounting-completion`, run
`python -m pytest tests/ -q`, then pick the next ❌/🟡 row in
`SAFIR_SPECIFICATION_GAP_MATRIX.md`. The next incomplete requirement is the
D02-dependent goals-vs-results view (S02/S10); it cannot be finished without the
owner's D02 decision.
