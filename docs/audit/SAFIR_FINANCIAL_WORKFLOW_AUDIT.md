# SAFIR Holding — Financial Workflow Audit

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`
**Specification:** `Platform_Executive_Specifications_v1.docx` §14.1 (Table 68), §15 (Table 70),
§15.1 (subsidiary summary calculation), S05/S06/S08/S26/S27/S28, Dec. 1–3
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

Legend: ✅ present · 🟡 partial · ❌ absent · 🔒 blocked by Dxx.

---

## 1. What exists today

| Artifact | Location | Purpose |
|---|---|---|
| `MonthlyReport` | `backend/db/models/report.py` | One row per (company, year, month); `revenue`, `expenses`, `net_result`, `outstanding_receivables` as `NUMERIC(18,2)`; narrative fields; status `draft/submitted/under_review/reviewed`. |
| `MonthlyReportFinancialReview` | same | One row per report; `approved/flagged`; verified figures; reviewer; notes. |
| `MonthlyReportAttachment` | same | Metadata + opaque `storage_key`; bytes outside DB. |
| Service | `backend/services/report_service.py` | `create/update/submit/review_financially/add_attachment/remove_attachment`. |
| API | `backend/api/v1/reports.py` | `/monthly-reports` CRUD, `POST /{id}/submit`, `POST /{id}/financial-review`, attachments. |
| Permissions | `backend/rbac/permissions.py` | `monthly_report.*`, `financial_review.read/write`. |
| Tests | `tests/test_reports.py` (23) | Lifecycle, review, attachments, isolation. |

**Verified:** the accountant’s original figures are never overwritten — a separate review
row holds `verified_*`, and `dashboard_service` prefers approved verified figures via
`coalesce(verified, submitted)` joined on `status = approved`. Money is exact (NUMERIC),
never float (`test_postgres.py`).

---

## 2. Specification state machine vs current behaviour

| # | Transition (Table 68) | Current | Status |
|---|---|---|---|
| 1 | no version → manager creates F-03 → draft linked to company+period | `create_report` (unique company+period) | 🟡 single report, not a *version* |
| 2 | draft → manager sends with **bank statement** | `submit_report` requires revenue+expenses; no bank-statement requirement | 🟡 |
| 3 | for-review → accountant returns with **specific note** | **no return transition** | ❌ |
| 4 | correction-required → manager corrects & resends | **no correction transition** | ❌ |
| 5 | for-review → accountant **approves** → approved & closed | accurate → `reviewed` | 🟡 (no explicit closed/effective stamp) |
| 6 | approved → manager creates **linked correction version** | absent | ❌ |
| 7 | correction-for-review → accountant approves → correction effective; original retained, not double-counted | absent | ❌ |
| 8 | one period identity links all versions; one effective approved version | absent | ❌ |
| 9 | no deletion of the original; historical values immutable | attachments frozen when reviewed; but no original/version split | 🟡 |
| 10 | resend/approve the same request does not create an independent version or duplicate notice | submit blocked once non-draft | 🟡 |

---

## 3. Structural data-model gap

Spec (§18, Table 74):

```
FinancialPeriod(company, month, year, effective_version_id)
   1:N FinancialSummaryVersion(number, previous_version_id, status, entered, effective, balances, currency)
       N:1 FieldDefinition/FieldRevision   (via FinancialItemValue snapshot)
       N:1 FinancialReview (decision, note, actor, time)
       N:1 BankAttachment
```

Current codebase: `MonthlyReport` (≈ summary) + one `MonthlyReportFinancialReview` +
`MonthlyReportAttachment`. There is **no** period/version layer, no
`FinancialItemValue`, no field-definition snapshot with inclusion rules, no bank/cash
balances, no budget, no `Asset`, no `Journal/JournalLine`, no `Party/Invoice`.

**Consequence:** S05, S06, S07 (financial part), S08, S26, S27, S28 and AC-05/06/08/26/27/28
cannot pass until the version model is introduced. This is the single largest build item.

---

## 4. Subsidiary summary calculation (§15.1) — not implemented

Spec formula:

```
effective revenue   = entered revenue + Σ(items classified revenue, rule = ADD)
effective expenses  = entered expenses + Σ(items classified expense, rule = ADD)
result              = effective revenue − effective expenses
included items must not be added twice; unclassified items do not change the result.
bank + cash are period-end balances, independent of result.
```

Test vector (spec, synthetic): entered revenue 1000, expenses 600, service-expense 50
(*included*), added expense 20, holding transfer 200 → **result 380**; service not added;
transfer is not revenue; if bank 700 + cash 30 → cash 730 independent of result.

**Current:** absent. `net_result` is a plain stored/derived field; no inclusion rule, no
traceable entered/additions/result breakdown (spec requires the UI show entered totals,
additions and final result traceably). **BLOCKED on D01.**

---

## 5. Multi-currency / balance-vs-flow rules (§15.1, T10)

| Rule | Current | Status |
|---|---|---|
| Money exact, per-currency | `NUMERIC(18,2)`; `Company.currency`, `currency` fields | ✅ |
| No aggregation of different currencies without an approved conversion rule | no conversion rule exists; **no guard preventing naive summation either** | ❌ |
| Period result/revenue/expense are *flows*; bank/cash/debts/receivables are *period-end balances* | single report stores all four without flow/balance typing | ❌ |
| No posting a balance as revenue | no posting engine | N/A |

---

## 6. Accounting card dependencies (D01, D07, D08, D09, D10)

| Decision | Blocks | Spec location |
|---|---|---|
| D01 accounting setup (currency, fiscal year, chart of accounts, invoice timing, settlements, tax, assets) | S26–S28 and all financial calculations | §21 D01 |
| D07 budget source/owner | S22, S28 | §21 D07 |
| D08 annual carry-forward source | S04 | §21 D08 |
| D09 currency change details | S03, S06, S07, S10 | §21 D09 |
| D10 bank attachment/protection/restore | S05, S08 | §21 D10 |

The specification is explicit: *“قبل التنفيذ المالي التفصيلي تُعتمد بطاقة D01؛ يمكن للمبرمج
تقدير الشاشات الآن لكنه لا يضع قواعد ضريبة أو ترحيل من عنده.”*
**Recommendation:** build the version/period scaffolding and screen shells now, but do
**not** invent posting, tax or carry-forward rules before D01/D07/D08 are signed.

---

## 7. Acceptance criteria status

| AC | Requirement | Status |
|---|---|---|
| AC-05 | F-03 summary + bank attachment; versioned submit | 🟡/❌ |
| AC-06 | F-04 special items/tax classification | ❌ 🔒 |
| AC-08 | accountant cannot edit financial fields via UI or direct request; return without note rejected; approved correction does not double the month | ❌ |
| AC-26 | debit 100 / credit 90 posting rejected; re-posting does not duplicate; revenue list shows one operation | ❌ 🔒 |
| AC-27 | invoice and entry keep one reference; settlement does not run a bank; partial receivable not counted twice | ❌ 🔒 |
| AC-28 | accountant has five sections; asset under holding accounts; summary matches trial balance; over-budget creates no automatic payment approval | ❌ 🔒 |

---

## 8. Recommendation summary (no code changed in this audit)

1. Introduce `FinancialPeriod` + `FinancialSummaryVersion` + `FinancialItemValue` +
   `FieldDefinition/FieldRevision` (snapshot) + `BankAttachment`, with
   **exactly-one-effective-version** and **no-duplicate-post** integrity constraints.
2. Add explicit reviewer transitions **approve / return-for-correction (mandatory note)**;
   keep the returned/corrected history; never overwrite an approved version.
3. Implement the §15.1 inclusion/adds calculation with a traceable breakdown, behind D01.
4. Defer tax/posting/carry-forward/budget rules until D01/D07/D08 are approved; mark any
   affected screen as **not complete** until then.
5. Add a multi-currency guard (reject cross-currency aggregation without an approved rule).
6. Keep the no-bank-transfer-button invariant.
