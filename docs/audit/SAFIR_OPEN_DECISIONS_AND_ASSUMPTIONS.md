# SAFIR Holding — Open Owner Decisions (D01–D11) & Audit Assumptions

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`
**Specification:** `Platform_Executive_Specifications_v1.docx` §21 (نقاط تحتاج قرارًا قبل البرمجة)
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

> These items are **not approved requirements**. Each has a cause, a non-approved
> recommendation and an affected part. Per the specification, the programmer may estimate
> the rest of the screens but **must not invent an answer**; an owner decision is recorded
> with a date and reference before the affected rule is implemented.

---

## 1. Decision register

| ID | Title | Cause (unresolved) | Non-approved recommendation | Affected | Blocked build items |
|---|---|---|---|---|---|
| **D01** | Holding accounting setup | Currency, fiscal year, chart of accounts, invoice timing, settlements, tax, assets unspecified | Accountant setup card; post each source once; correct postings by reversal/adjustment; owner approves rules | S26–S28 + report calc | S05, S06, S07(fin), S08, S26, S27, S28, AC-06/08/26/27/28, T08/T16 |
| **D02** | Report forms & indicators | Axes/frequency fixed; the 5 questions, indicator definitions, goals, campaign lead count incomplete | Approve the 5 questions + indicator definitions (source/numerator/denominator/period); pull existing data, don’t re-enter | S09–S10, S14, S18, S21 | S14, S18, S21, T12 |
| **D03** | Non-financial work states | Closure/return/cancel authority; customer/project states; non-financial report correction undefined | Executor delivers, requester receives or requests change (suggestion only); non-financial reports get a linked correction version **after** the rule is approved | S13, S16–S22; F-06 fixed, not reopened | S13, S16, S17, S20, AC-13/14/16 |
| **D04** | Employee & advisor visibility | Who sees monthly assessment, employee reports, lead redistribution; what data an advisor gets | Restrict issuance to named roles; advisor sees only their assigned employee’s necessary data; approve an explicit display list | S12, S13, S19; does not touch leadership secrecy | S12, S19, lead redistribution |
| **D05** | Assessment grades & AI data | Weights fixed; grade scale, evidence-gap handling, external data undefined | Documented scale per criterion with sources; show evidence gaps; minimal data with no identity/salary beyond need | S12, S23; no service/subscription chosen in advance | S12, S23, T14 |
| **D06** | Employee balances & actions | Whether advances/leaves are manual admin values or computed balances; financial impact link | Admin records in v1; accountant records the holding impact when it happens; no automated payroll | S11 | S11, employee/leave/advance |
| **D07** | Budget source & update | Who records the budget/its reference/who changes it; whether over-budget detection is manual or automatic | Accountant records an approved budget with the owner’s reference; BD & owner read; explicit escalation without blocking payment | S22, S28 | S28 budget, S22 |
| **D08** | Annual carry-forward source | Company manager is the approved executor but automatic December copy & year-end settlements unspecified | Manager records the balance showing the last approved summary for comparison; no automatic copy until approved | S04 | S04, opening balances |
| **D09** | Currency change & calc details | Base currency & no-mixing approved; changing a company’s currency, handling an item added under another classification or negative values undefined | Preserve historical currency; no conversion before an approved rule/rate/date; accounting effect of other classification needs explicit definition | S03, S06, S07, S10 | S03 currency change, S06, T10 |
| **D10** | Bank attachment, protection & restore | File size/type, encryption, retention, backup frequency, restore time undefined; a company without a bank account has no approved exception | Clear upload limits and per-company protection; backup + restore test plan; any attachment exception goes to the owner with no automatic exemption | S05, S08, technical layer | S05 bank attachment, T17 |
| **D11** | Login & notification channels & timing | Login method/recovery, multi-assignment users, time zone, external notification mechanism undefined | Simple login + role scope; internal notifications first; no WhatsApp/email without a request; store UTC and display a defined zone | S01, S25, all events | S25 notifications prefs/login |

---

## 2. Decisions already closed (do not reopen)

The specification states the three **Appendix A** decisions are closed: Dec. 1 (correction
handling), Dec. 2 (included vs added item), Dec. 3 (currency / no aggregation). These are
reflected in the financial audit as fixed rules, not open items.

---

## 3. Audit assumptions & limitations

1. **Read-only audit.** No schema, service, API, frontend or data change was made.
2. **No VPS deployment.** Nothing was deployed, restarted or migrated on any server.
3. **Dependencies reinstalled locally** (FastAPI/SQLAlchemy/pytest) because the prior
   sandbox was lost; no repository dependency files were modified.
4. **Test evidence:** full suite ran locally with **575 passed, 0 failed** at commit
   `cebde88`. This confirms the existing platform is not broken; it does **not** validate
   the unbuilt modules.
5. **Spec is in Arabic** and was extracted programmatically. Screen codes (S01–S28),
   acceptance criteria (AC-01…AC-28) and tests (T01–T18) are cited from the source text.
6. **Company isolation and RBAC were verified by reading code and tests**, not by
   penetration testing against production.
7. **Boolean-default discrepancy** (`sa.text("0")` vs `sa.false()`) is reported but **not
   fixed** here; it is a portability follow-up, not a functional blocker on SQLite/PG tests.

---

## 4. Recommended sequencing (advisory only)

1. **Close D01 first** — it unblocks the entire accounting surface (S26–S28, S05–S08).
2. Close D02/D03 — unblocks S14/S16–S21.
3. Close D04/D05 — unblocks advisor and assessment screens.
4. Close D06/D07/D08 — unblocks employees, budget, opening balances.
5. Close D09/D10/D11 — unblocks currency change, protection/restore, auth/notifications.
6. Only then implement the corresponding modules, each with new permission codes,
   server-side scope filters, migrations and tests, preserving the existing RBAC/APIs,
   Phase 10 website and Phase 11 CMS.

No module should be marked complete while its governing decision remains open
(spec §20: “أي قرار D مؤثر غير محسوم يسجل مفتوحًا ولا توضع علامة مكتمل لجزئه”).
