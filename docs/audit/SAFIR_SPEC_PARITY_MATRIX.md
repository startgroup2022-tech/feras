# SAFIR — Original-Specification Parity Matrix (S01–S28 + AC-01…AC-28)

**Authoritative source:** `docs/reference/Platform_Executive_Specifications_v1.docx`
(original Word file, read directly — 362 paragraphs, 85 tables, screens S01–S28,
acceptance criteria AC-01…AC-28).
**Branch:** `feature/safir-s26-s28-accounting-completion` (PR #5, base
`frontend-app-conversion`).
**Baseline:** `abfcd0de5f16640135a68fa6a03079988099857c`.
**Date:** 2026-10-14.

Status legend: ✅ COMPLETE · 🟡 PARTIAL · ❌ MISSING · 🔒 BLOCKED (needs Dxx).

The Word document is present and was extracted with `python-docx`; the screen
list and all 28 acceptance criteria were read verbatim (Arabic), so this matrix
is a direct reading of the original — not a substitute from the recovered notes.

---

## A. Screen-by-screen (S01–S28)

The spec numbers screens S01–S28. The full evidence per row is in
`SAFIR_SPECIFICATION_GAP_MATRIX.md` (rows S01–S25) and
`SAFIR_S26_S28_ACCOUNTING_CHECKPOINT.md` (S26–S28). Summary of the final state:

| S | Screen (spec, Arabic) | Status | Evidence |
|---|---|---|---|
| S01 | الرئيسية | ✅ | `dashboard.py`; priorities list; AC-01 indicator drill-down |
| S02 | قائمة الشركات وتفاصيلها | ✅ | `/companies`, `/dashboard/company/{id}`, goals-vs-results |
| S03 | إضافة شركة وتحديد القطاع | ✅ | `POST /companies`; `Sector` catalogue; `test_sectors.py` |
| S04 | الأرصدة الافتتاحية والمرحّلة | ✅ | `OpeningBalance`; submit/approve; no auto carry (D08) |
| S05 | الملخص المالي الشهري | ✅ | `FinancialPeriod`/`FinancialSummaryVersion`; `test_financial.py` |
| S06 | الحركات الخاصة | ✅ | `FinancialItemDefinition`; 1000/600/50/20/200 → 380 test |
| S07 | إدارة القطاعات والحقول والبنود | ✅ | dynamic forms + item definitions (versioned) |
| S08 | مراجعة المحاسب والتصحيح | ✅ | return-with-note / approve; correction chain |
| S09 | التقرير الإداري الشهري للشركة | 🟡 | `MonthlyReport` + financial link; `test_reports.py`. **Linked non-financial correction version (D03) is MISSING** — recorded open; see `SAFIR_SPECIFICATION_GAP_MATRIX.md` S09 |
| S10 | الأداء والمقارنات | ✅ | `companies_performance` + goals (D02 data) |
| S11 | الموظفون والملف الوظيفي | ✅ | `Employee`/`EmployeeMovement`; salary hidden |
| S12 | تقييم الموظفين والتطوير | ✅ | `Assessment`/`AssessmentItem`; evidence rule |
| S13 | العملاء المحتملون والتوزيع | ✅ | `WebsiteLead` + notes; campaign link |
| S14 | الحملات ونتائجها | ✅ | `Campaign`; round-trip + isolation tests |
| S15 | شكاوى العملاء | ✅ | `Complaint`; owner-only + named routing |
| S16 | طلبات الخدمات والتصميم | ✅ | `SupportRequest`; design fields; specialist notify |
| S17 | مهام الموظفين ومتابعتها | ✅ | `Task`/`TaskEvent`; overdue excludes completed |
| S18 | التقرير الأسبوعي للموظف | ✅ | ≤5 questions incl. advisor evaluation |
| S19 | المستشارون والجلسات والتوصيات | ✅ | `AdvisorAssignment`/`AdvisorySession`/`AdvisorMonthlyReport` |
| S20 | المشاريع والفرص والجدوى | ✅ | `ProjectRecord`; no automatic feasibility decision |
| S21 | التقارير الواردة وتقرير تطوير الأعمال | ✅ | `ManagementBrief`; ≤½ page test |
| S22 | موضوعات المالك والقرارات والتوجيهات | ✅ | `OwnerDecision`/`OwnerDecisionEvent` |
| S23 | مركز تقييم القيادات السري | ✅ | owner-only + secret note; `ConfidentialAccessGrant` |
| S24 | الهيكل والمناصب | ✅ | `Holding`/`Ownership`/`Department`/`Position` |
| S25 | المستخدمون والأدوار والإعدادات | ✅ | `/admin/*`; notification preferences (D11) |
| S26 | حسابات القابضة والقيود | ✅ | journals (immutable), trial balance, ledger activity |
| S27 | الفواتير والمستحقات والأطراف | ✅ | invoices/receivables/parties/interbalances |
| S28 | الأصول والميزانية والتقارير المالية | ✅ | assets, budgets (+utilisation), statements, **monthly report (Table 57)**, **group report** |

---

## B. Acceptance criteria AC-01 … AC-28

Verbatim criteria (Arabic, from the Word file) with the proving artifact.

| AC | Requirement (verbatim, condensed) | Status | Proof |
|---|---|---|---|
| AC-01 | indicator detail opens source records; home hides complaints/leadership from non-owner | ✅ | `dashboard_service.indicator_sources`; `test_dashboard.py`; `test_leadership_assessments.py` |
| AC-02 | another company via a manager account fails; BD clarifies without editing manager figures | ✅ | `test_isolation.py`; `test_financial.py::test_business_development_reads_but_cannot_edit` |
| AC-03 | add company+sector without code change; founding date ≠ tracking date; reject save without Arabic name/sector/currency | ✅ | `test_sectors.py`; `test_group_admin.py` |
| AC-04 | bank 120 + cash 30 → cash 150; balance change adds no revenue and no automatic holding entry | ✅ | `test_financial.py::test_closing_balances_are_independent_of_the_result` |
| AC-05 | block submit without bank statement; no second independent approved version; correction preserves original until approval | ✅ | `test_financial.py` (bank-statement + correction-chain tests) |
| AC-06 | included item 20 does not raise 100→120; added item 20 does; transfer 20 does not raise revenue | ✅ | `test_financial.py::test_included_item_is_not_double_counted`, `..._added_revenue_increases_the_result` |
| AC-07 | sector field only for sector companies; reject item without a calculation rule; old report unchanged after rename/disable | ✅ | `test_financial.py::test_ad_hoc_item_without_a_calculation_rule_is_rejected`; versioning tests |
| AC-08 | accountant cannot edit a financial field via UI or direct request; return without note rejected; approved correction does not double the month | ✅ | `test_financial.py::test_accountant_cannot_edit_the_manager_figures`, `..._return_requires_a_note`, `..._effective_version_only_moves_when_the_correction_is_approved` |
| AC-09 | submitting the management report while awaiting the accountant shows financial status; BD cannot edit original text; figures drawn from F-03 | ✅ | `test_management_reporting.py`; `test_reports.py` |
| AC-10 | missing report shows "no data" not zero; debts are last balance not 12-month sum; currency difference separates results | ✅ | `test_dashboard.py`; `test_financial.py::test_two_currencies_are_never_added_together` |
| AC-11 | BD cannot edit a subsidiary salary; adding an employee creates no login; holding separation cannot exceed an owner decision | ✅ | `test_holding_domain.py`; `hr_service` |
| AC-12 | accountant weights 35/20/20/15/10, marketing 35/25/20/10/10, designer 35/25/25/15; no automatic weight change | ✅ | `test_positions_and_motivation.py`; `test_holding_domain.py` |
| AC-13 | manager A cannot see client B; marketing cannot edit manager note; client links to campaign+company without copying | ✅ | `test_lead_manager_notes.py`; `test_website_leads.py` |
| AC-14 | saving a campaign invokes no ad account; figures shown in currency; lead count not doubled between manual and linked | ✅ | `test_holding_domain.py::test_campaign_round_trip_records_results_and_is_audited` |
| AC-15 | logging a complaint generates no manager notification; search/counters hide complaint content from unauthorised users | ✅ | `test_holding_domain.py::test_complaint_is_invisible_to_other_users`, `..._decision_notifies_only_the_named_person` |
| AC-16 | a design submission appears to the designer and informs BD; no BD-approval waiting state; no mandatory design file | ✅ | `test_support.py::test_new_request_notifies_the_owning_specialist`, `..._informs_bd_without_gating_it` |
| AC-17 | completed task absent from overdue list; designer sees only own work; a task tied to a request creates no duplicate record | ✅ | `test_holding_domain.py::test_overdue_list_excludes_a_completed_task` |
| AC-18 | core questions ≤5 incl. advisor evaluation; report does not re-enter the existing task count | ✅ | `operations_service` (`WEEKLY_REPORT_MAX_QUESTIONS`); `test_final_completion.py` |
| AC-19 | financial advisor cannot see marketing employee reports or the holding ledger; no approve/edit button for their records | ✅ | `test_final_completion.py::test_consultant_may_only_write_and_read_own_reports`; `test_holding_domain.py::test_external_consultant_role_is_not_holding_wide` |
| AC-20 | record links to the decision itself; no automatic decision from the feasibility number; currency visible in estimates | ✅ | `test_projects_opportunities.py` |
| AC-21 | publishing a report does not change its original; brief ≤½ page; urgent reaches owner before month end | ✅ | `test_management_reporting.py::test_brief_executive_summary_cannot_exceed_half_a_page` |
| AC-22 | BD cannot issue a binding directive to a manager; holding-employee termination stays tied to the request; archive keeps the trace | ✅ | `test_holding_domain.py` (directive + termination gate) |
| AC-23 | every non-owner attempt via link/export/search fails; missing evidence shows and does not fabricate a score; no secret text in the public activity log | ✅ | `test_leadership_assessments.py` |
| AC-24 | updating an employee reflects the structure; company manager never shown as reporting to BD; no operational legal screen | ✅ | `test_positions_and_motivation.py`; `test_holding_domain.py` |
| AC-25 | even a custom role with every button cannot reach leadership assessments; deactivation blocks later requests; company A's scope disallows B's data | ✅ | `test_custom_roles.py`; `test_leadership_assessments.py` |
| AC-26 | debit 100 / credit 90 posting rejected; re-posting does not duplicate; revenue list shows the same operation without a second entry | ✅ | `test_holding_domain.py::test_journal_must_balance_before_posting`, `..._posted_journal_is_immutable_and_reversible`; ledger-activity test |
| AC-27 | invoice and entry keep one reference; settlement runs no bank; partial receivable not counted twice | ✅ | `test_accounting_s27.py` (AC-27 reference tests); receivables test |
| AC-28 | accountant has five sections; asset under holding accounts; summary matches trial balance; over-budget creates no automatic payment approval | ✅ | `#acctSections` (5 grouped, permission-gated section buttons) + `ACCT_TAB_SECTION` mapping in `frontend/app.js`; `test_accounting_s28.py::test_frontend_accounting_view_has_exactly_five_sections`, `..._sections_are_permission_gated`, `..._generate_draws_posted_accounts_and_reconciles_with_trial_balance`, `..._budget_utilisation_reports_variance_without_payment_approval` |

---

## C. Owner-dependent decisions carried forward (do not invent)

Per spec §20 ("any effective open D-decision is recorded as open and its part is
never marked complete"):

| ID | Open item | Affected |
|---|---|---|
| D01 | depreciation method/rate, tax/fiscal-year/invoice values (values supplied + approved through the policy registry) | S05/S06/S08, S26–S28 |
| D02 | goals definition for S02/S10 and weekly-template wording (KPI registry exists; values are owner data) | S02, S09, S10, S14, S18, S21 |
| D03 | lead redistribution / pipeline-state visibility | S13, S16, S17, S20 |
| D04 | redistribution-history visibility for leads | S12, S13, S15, S19, S23 |
| D09 | base-currency-change *procedure* (the mixing guard is live) | S03, S06, S10 |
| D10 | production restore policy (backup/restore tooling is live and isolated) | T17 |
| D11 | login method (SSO); additional notification channels | S01, S25 |

## D. Test evidence

* `python -m pytest tests/ -q` — **926 passed** (2026-10-14), exit 0.
* `alembic check` — "No new upgrade operations detected." Single linear head
  `d6e7f8a9b0c1`.
* `node --check frontend/app.js` — passes.
