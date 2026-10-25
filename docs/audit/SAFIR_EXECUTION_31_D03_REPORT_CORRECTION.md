# Execution 31 — D03 versioned management report (S09) & Release Acceptance

Branch: `feature/safir-execution-30-owner-decisions`
Base (integration): `frontend-app-conversion` @
`c449706c1c5875ef8b1485b55ead0d5591d75214` (merge of PR #5, S26–S28 accounting).
Feature commits: `3ea9030` (D03 backend), `71c9f60` (D03 frontend).

**Authoritative source:** `docs/reference/Platform_Executive_Specifications_v1.docx`
(the original Word file, present in the repository and read directly for this
checkpoint — screens S01–S28, acceptance criteria AC-01…AC-28, §21 lists the
D01–D11 open points). This document is a *direct* reading of the original, not a
substitute from recovered notes.

---

## 1. What Execution 31 changed

Execution 30 closed every authorised owner decision except **D03**, and recorded
the remaining D03 gap rather than papering over it (§6 of
`SAFIR_EXECUTION_30_OWNER_DECISIONS.md`). The gap: the spec says correcting the
*non-financial* (management) monthly report after submission **"needs D03"** and
must be a correction version *linked to the original* with the original
preserved. `MonthlyReport` was one-per-company-per-period (`uq_report_company_period`)
with a short status lifecycle, no correction link, and edits blocked once
submitted. That gap is now closed.

| Area | Change |
|---|---|
| Schema | `MonthlyReport` + `version_number`, `corrects_report_id`, `is_live`, `approval_status`, return/approve/cancel metadata; new `ReportLifecycleEvent` |
| Uniqueness | `uq_report_company_period` → `uq_report_company_period_version` (company, period, version) **+** partial unique index `uq_report_company_period_live` (exactly one live version per company/period) |
| Service | `return_report` (BD, mandatory reason), `create_correction` (linked new version), `approve_report` / `cancel_report` (owner-only), `list_versions`, `list_lifecycle` |
| RBAC | `monthly_report.review` (BD), `monthly_report.approve` (owner); bilingual metadata |
| API | `POST /monthly-reports/{id}/return\|correction\|approve\|cancel`; `GET /monthly-reports/{id}/versions\|lifecycle`; detail embeds chain + trail |
| Frontend | Report modal renders version chain + workflow trail; permission-gated Return / Create-correction / Approve / Cancel |
| Migration | `3473d285d919` (revises `62040b21dfa2`), reversible, drift-free |
| Tests | `tests/test_execution31_d03_report_correction.py` (21 cases) |

### 1.1 Spec traceability (S09 / AC-09)

| Spec requirement (verbatim) | Implementation | Test |
|---|---|---|
| «تصحيح التقرير الإداري بعد الإرسال يحتاج D03» — correction of the management report after submission needs D03 | Versioned correction workflow; owner decision D03 authorised | `test_correction_creates_a_linked_new_version`, `test_resubmitting_a_correction_records_resubmitted` |
| Correction is a version *linked to the original*; the original is preserved | `corrects_report_id` + `is_live` supersession; the original row is never deleted or edited | `test_correction_creates_a_linked_new_version` (asserts `original.major_problems is None`) |
| «لا يمكن لتطوير الأعمال تعديل النص الأصلي» — BD cannot edit the original text | Return only sets status/reason; the narrative is edited only by creating a new version | `test_company_manager_cannot_return_a_report`; `create_correction` copies, never mutates |
| «الأرقام سحب من F-03» — figures are drawn from F-03 | Correction carries the financial figures over; the financial side stays with the accountant (F-03) | `test_correction_creates_a_linked_new_version` (revenue carried) |
| «لا انتظار خفي لاعتماد الجزء المالي؛ يظهر قيد المراجعة صراحة» — no hidden wait for the financial part | The report status and the separate financial review are both shown explicitly | `test_report_detail_embeds_lifecycle_and_versions`; unchanged financial-review tests |
| Access: company manager, owner, BD; owner/BD access to another's asset is read-only | Company-scoped reads; owner/BD act through their permissions | `test_correction_is_company_scoped`, `test_versions_are_company_scoped` |

---

## 2. S01–S28 requirements & acceptance matrix

Full per-screen evidence is in `SAFIR_SPECIFICATION_GAP_MATRIX.md` (S01–S25) and
`SAFIR_S26_S28_ACCOUNTING_CHECKPOINT.md` (S26–S28). Summary of the final state
after Execution 31:

| S | Screen | Status | Notes |
|---|---|---|---|
| S01 | الرئيسية | ✅ | dashboard, priorities, AC-01 drill-down |
| S02 | قائمة الشركات وتفاصيلها | ✅ | companies, company dashboard, goals-vs-results |
| S03 | إضافة شركة وتحديد القطاع | ✅ | company CRUD + managed sectors (D09 procedure open) |
| S04 | الأرصدة الافتتاحية والمرحّلة | ✅ | opening balances, no auto carry (D08) |
| S05 | الملخص المالي الشهري | ✅ | versioned financial summary (F-03) |
| S06 | الحركات الخاصة | ✅ | special financial items (F-04) |
| S07 | إدارة القطاعات والحقول والبنود | ✅ | dynamic fields + item definitions |
| S08 | مراجعة المحاسب والتصحيح | ✅ | accountant review / correction chain (F-06) |
| **S09** | **التقرير الإداري الشهري للشركة** | **✅** | **D03 linked correction version now implemented (Execution 31)** |
| S10 | الأداء والمقارنات | ✅ | performance + goals (D02 values owner data) |
| S11 | الموظفون والملف الوظيفي | ✅ | employees; salary hidden (D06) |
| S12 | تقييم الموظفين والتطوير | ✅ | assessments; evidence rule (D05) |
| S13 | العملاء المحتملون والتوزيع | ✅ | leads + notes; campaign link |
| S14 | الحملات ونتائجها | ✅ | campaigns; round-trip + isolation |
| S15 | شكاوى العملاء | ✅ | complaints; owner-only |
| S16 | طلبات الخدمات والتصميم | ✅ | support requests; design fields |
| S17 | مهام الموظفين ومتابعتها | ✅ | tasks; overdue excludes completed |
| S18 | التقرير الأسبوعي للموظف | ✅ | ≤5 questions |
| S19 | المستشارون والجلسات والتوصيات | ✅ | advisor assignments/sessions/reports |
| S20 | المشاريع والفرص والجدوى | ✅ | project records; no auto decision |
| S21 | التقارير الواردة وتقرير تطوير الأعمال | ✅ | management briefs; ≤½ page |
| S22 | موضوعات المالك والقرارات والتوجيهات | ✅ | owner decisions/topics |
| S23 | مركز تقييم القيادات السري | ✅ | owner-only + secret note |
| S24 | الهيكل والمناصب | ✅ | holding/ownership/departments/positions |
| S25 | المستخدمون والأدوار والإعدادات | ✅ | admin; notification prefs (D11) |
| S26 | حسابات القابضة والقيود | ✅ | journals (immutable), trial balance |
| S27 | الفواتير والمستحقات والأطراف | ✅ | invoices/receivables/parties |
| S28 | الأصول والميزانية والتقارير المالية | ✅ | assets, budgets, statements, group report |

All 28 acceptance criteria AC-01…AC-28 are ✅ with named proving tests (see
`SAFIR_SPEC_PARITY_MATRIX.md` §B).

---

## 3. Functional gaps found and their disposition

| Gap | Disposition |
|---|---|
| D03 linked non-financial correction version (S09) | **Closed** in Execution 31 (this document) |
| D02 goal numbers / weekly-template wording (S02, S09, S10, S14, S18, S21) | Mechanism live; **owner data outstanding** — not invented |
| D01 depreciation/tax/fiscal-year/invoice/asset values | Policy registry live; **owner values outstanding** |
| D05 assessment scale/weights | Mechanism live; **owner data outstanding** |
| D06 manual-vs-computed balances policy | Manual balances implemented; policy confirmation outstanding |
| D07 owner-decision numbering / budget values | Mechanism live; **owner values outstanding** |
| D08 opening figures | Submit/approve implemented; **owner figures outstanding** |
| D09 base-currency-change procedure | Mixing guard live; **approved conversion rule outstanding** |
| D10 production restore drill | Tooling live and isolated; **production drill not executed** (no production access by design) |
| D11 login method (SSO) / external channels | Internal centre + 2FA live; **owner choice outstanding** |

No owner-dependent value was invented. Each enters through an approved record.

---

## 4. Verification evidence

| Check | Result |
|---|---|
| `python -m pytest tests/ -q` | **967 passed**, exit 0 (946 baseline + 21 new) |
| `alembic upgrade head` (fresh DB) | head `3473d285d919` applied |
| `alembic check` | "No new upgrade operations detected." |
| `alembic downgrade -1` → `upgrade head` | reversible, re-applies cleanly |
| RBAC sync | 15 roles, **179** permissions, all with bilingual metadata |
| `node --check frontend/app.js` | passes |

---

## 5. Owner-dependent decisions still open (do not invent)

Carried forward from Execution 30 §7.2, unchanged except that D03's *workflow*
is now built. What remains for D03 is only the pipeline-state visibility wording
(S13/S16/S17/S20), which is a display decision, not a missing workflow.

D01, D02, D05, D06, D07, D08, D09, D10, D11 values/wording as listed in §3.

---

## 6. Release readiness — NOT READY

Reasons:

1. The remaining owner-dependent *values/words* are unresolved (§3, §5). Their
   mechanisms are live; only the owner's data is outstanding. Per spec §20 these
   are recorded open, not marked complete.
2. The production load test and the production backup/restore drill have not
   been executed on the production target (by design — no production access).

Everything audited on this branch — the authorised mechanisms, the new D03
workflow, migrations, RBAC, isolation, and the automated suite — passes.

**Next incomplete requirement:** none in code for the authorised, unblocked
scope. The remaining work is (a) the owner's data for D01/D02/D05–D09/D11, and
(b) the production load test + backup/restore drill once production access and
owner values are provided.
