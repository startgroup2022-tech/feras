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
* Permissions `party.read/manage`, `interbalance.read/manage` (granted to the
  accountant, read to the owner/finance-manager/BD), with bilingual metadata and
  audit actions `party.created`, `party.updated`, `interbalance.recorded`.
* Frontend: `parties` and `interbalances` accounting tabs, a receivable/payable
  summary on the invoices tab, and a direction selector on the invoice form.
* Migration `a2b3c4d5e6f7` (additive; batch mode for the SQLite `invoices`
  ALTER). `alembic check` reports no drift.
* Tests: `tests/test_accounting_s27.py` (13 cases) covering the above plus RBAC
  and the frontend wiring.

## What remains (not done on this branch)

These are **not** blocked by a technical gap; they are owner-dependent and were
deliberately left alone (do not invent approvals for D01–D11):

* D01 — depreciation method/rate, tax rate, invoice policy are stored as neutral
  data and wait for accountant-approved configuration.
* D07 — budget source is stored, approval supersedes a version (never overwrites).
* S28 financial statements — a formal income-statement/balance-sheet report with
  prior-period columns and currency filters is not built; the trial balance plus
  the dashboard totals are the current evidence. This is the next candidate if
  the owner wants a formal statement layout.

## Continuation

If work resumes: check out `feature/safir-s26-s28-accounting-completion`, run
`python -m pytest tests/ -q`, then pick up "S28 financial statements" above. The
next incomplete requirement is the formal financial-statement layout (S28).
