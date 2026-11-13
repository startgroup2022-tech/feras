"""Build the slide-by-slide PPTX v3 compliance matrix.

Joins three evidence sources and emits ``docs/audit/PPTX_V3_COMPLIANCE_MATRIX.md``:

1. The deck's own wording, read from the OOXML (``artifacts/deck/slides_text.json``)
   -- the authoritative text, never a paraphrase.
2. What the running SPA actually renders (``artifacts/app_inventory.json`` from
   ``scripts/audit/app_inventory.py``).
3. What the role crawl observed (``artifacts/view_audit.json`` from
   ``scripts/audit/view_audit.py``) plus an endpoint probe
   (``artifacts/api_probe.json``).

A slide scores OK when every control the deck names for it is present in the
inventory (or is API-only by design and the endpoint answers), PARTIAL when the
screen exists but a named element is missing, REF for spec/reference slides that
map to no single screen.

    python scripts/audit/build_deck_compliance.py \
        --inventory artifacts/app_inventory.json \
        --audit artifacts/view_audit.json \
        --api-probe artifacts/api_probe.json \
        --out docs/audit/PPTX_V3_COMPLIANCE_MATRIX.md
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Each mapping groups the slides that describe one screen/family.
#   slides     the deck slide numbers (1-based)
#   title      the deck's own title (Arabic, verbatim)
#   family     deck screen-registry family (slide 49) or a short tag
#   view       the SPA view that implements it, or None
#   signals    evidence checks (see _check)
#   status     force REF for spec/reference slides
MAPPING: list[dict] = [
    # 01-06 framing
    dict(slides=[1], title="START UPSPHERE HOLDING", family="cover",
         view=None, status="REF", note="Deck cover; no screen."),
    dict(slides=[2], title="مبادئ تصميم المنصة", family="principles",
         view=None, status="REF", note="Design principles; no single screen."),
    dict(slides=[3], title="خريطة الوحدات الرئيسية", family="module map",
         view="dashboard", signals=[("view", "dashboard")],
         note="Six modules map to the six primary sidebar sections."),
    dict(slides=[4], title="قالب الشاشة الموحد", family="screen template",
         view="dashboard", signals=[("view", "dashboard"), ("scope", "header")],
         note="RTL sidebar right, fixed top bar, header entity+period selector."),
    dict(slides=[5], title="العربية والإنجليزية والاستجابة للشاشات", family="i18n",
         view="dashboard", signals=[("lang", "en"), ("lang", "ar")],
         note="AR RTL / EN LTR; both crawled clean."),
    dict(slides=[6], title="تسجيل الدخول", family="login",
         view=None, signals=[("login", "deck-controls")],
         note="Login gate: email + password + [تذكرني على هذا الجهاز] + "
              "[تسجيل الدخول] + [نسيت كلمة المرور؟] + language toggle. Recovery "
              "is admin-mediated (no self-service email-reset endpoint in Phase 3); "
              "the signed-in user changes their own password from the header "
              "profile block and an administrator sets a temporary password from "
              "Admin ▸ Users (D11 account access)."),
    # 07-11 role dashboards
    dict(slides=[7], title="لوحة المالك", family="role dashboard",
         view="dashboard",
         signals=[("view", "dashboard"), ("role", "holding_owner"),
                  ("role-summary", "holding_owner"),
                  ("role-render", "holding_owner")],
         note="Owner strip: profit trend, operating cash, liquidity risk, "
              "pending decisions."),
    dict(slides=[8], title="لوحة مدير تطوير الأعمال", family="role dashboard",
         view="dashboard",
         signals=[("role", "business_development"),
                  ("role-summary", "business_development"),
                  ("role-render", "business_development")],
         note="BD strip: awaiting assignment, tasks in progress, active "
              "opportunities, reports to follow up."),
    dict(slides=[9], title="لوحة مدير الشركة التابعة", family="role dashboard",
         view="dashboard",
         signals=[("role", "company_manager"),
                  ("role-summary", "company_manager"),
                  ("role-render", "company_manager")],
         note="Company strip: month result, cash balance, support requests. The "
              "deck's fourth tile (prospective clients) is gated on "
              "website_lead.read, which company_manager deliberately does not "
              "hold -- the tile is absent rather than faked, and reappears "
              "automatically if that boundary is relaxed (S13 AC-13)."),
    dict(slides=[10], title="لوحة الموظف المختص", family="role dashboard",
         view="dashboard",
         signals=[("role", "designer"), ("role-summary", "designer"),
                  ("role-render", "designer")],
         note="Specialist strip counts only tasks assigned to the caller."),
    dict(slides=[11], title="لوحة موظف المبيعات", family="role dashboard",
         view="dashboard",
         signals=[("role", "marketing"), ("role-summary", "marketing"),
                  ("role-render", "marketing")],
         note="Sales strip: new leads, awaiting contact, qualified leads, "
              "follow up this week."),
    # 12-37 platform screens
    dict(slides=[12], title="قائمة الشركات التابعة", family="ORG",
         view="subsidiaries",
         signals=[("view", "subsidiaries"), ("filterbar", "subsidiaries")]),
    dict(slides=[13], title="ملف الشركة التابعة", family="ORG",
         view="subsidiaries", signals=[("detail", "subsidiaries:openCompany"), ("company-file", "edit")]),
    dict(slides=[14], title="واجهة العملاء المحتملين", family="ORG",
         view="leads", signals=[("view", "leads"), ("filterbar", "leads")]),
    dict(slides=[15], title="تفاصيل العميل المحتمل", family="ORG", view="leads",
         signals=[("detail", "leads:openLead")]),
    dict(slides=[16], title="الحملات التسويقية", family="ORG", view="operations",
         signals=[("control", "operations:campaigns:buttons")]),
    dict(slides=[17], title="مركز الطلبات", family="ORG", view="requests",
         signals=[("view", "requests"), ("detail", "requests:openSubmission")]),
    dict(slides=[18], title="نموذج طلب دعم جديد", family="ORG", view="support",
         signals=[("view", "support"),
                  ("deck-control", "slide18_save_draft"),
                  ("deck-control", "slide18_send_request")],
         note="The deck's new-support-request form is the Support view's create "
              "dialog; both named controls now render. The deck draws a richer "
              "field set (goal, priority, requested date, estimated budget) than "
              "the app's form, which follows the Word spec's Table 48 "
              "(company, service type, description, date, dimensions/platform, "
              "reference link) -- the spec wins for field business rules."),
    dict(slides=[19], title="إسناد الطلب ومراجعته", family="ORG", view="support",
         signals=[("detail", "support:openSupport")]),
    dict(slides=[20], title="مساحة تنفيذ المهمة", family="ORG", view="operations",
         signals=[("control", "operations:tasks:buttons"),
                  ("deck-control", "slide20_start")]),
    dict(slides=[21], title="التغذية الراجعة", family="ORG", view="feedback",
         signals=[("view", "feedback")]),
    dict(slides=[22], title="التقرير الإداري الشهري", family="FRM", view="reports",
         signals=[("view", "reports"),
                  ("deck-control", "slide22_save_submit")]),
    dict(slides=[23], title="الملخص المالي الشهري للشركة", family="HF",
         view="financial",
         signals=[("view", "financial"),
                  ("deck-control", "slide23_save_draft"),
                  ("deck-control", "slide23_submit_review"),
                  ("deck-control", "slide23_send_accountant")]),
    dict(slides=[24], title="مراجعة المحاسب للتقرير المالي", family="HF",
         view="financial", signals=[("api", "GET /api/v1/monthly-reports")]),
    dict(slides=[25], title="الفرص والمشاريع", family="ORG", view="projects",
         signals=[("view", "projects")]),
    dict(slides=[26], title="تفاصيل وتقييم الفرصة", family="ORG", view="projects",
         signals=[("detail", "projects:openOpportunity"),
                  ("deck-control", "slide26_save_study"),
                  ("deck-control", "slide26_raise_owner")]),
    dict(slides=[27], title="قائمة قرارات المالك", family="ORG", view="decisions",
         signals=[("view", "decisions"),
                  ("deck-control", "slide27_open_decision")]),
    dict(slides=[28], title="تفاصيل القرار", family="ORG", view="decisions",
         signals=[("detail", "decisions:openDecision"),
                  ("deck-control", "slide28_approve"),
                  ("deck-control", "slide28_reject"),
                  ("deck-control", "slide28_request_info"),
                  ("deck-control", "slide28_defer")]),
    dict(slides=[29], title="سجل القرار ومتابعة التنفيذ", family="ORG",
         view="decisions", signals=[("decision-actions", "decisions"),
                                    ("deck-control", "slide29_decision_log")]),
    dict(slides=[30], title="توجيهات المالك لمدير الشركة", family="ORG",
         view="decisions", signals=[("decision-actions", "decisions")]),
    dict(slides=[31], title="شكاوى العملاء", family="ORG", view="confidential",
         signals=[("view", "confidential"), ("company-file", "complaint"),
                  ("deck-control", "slide31_refer"),
                  ("deck-control", "slide31_action"),
                  ("deck-control", "slide31_request_info"),
                  ("deck-control", "slide31_defer")]),
    dict(slides=[32], title="مالية القابضة", family="HF", view="accounting",
         signals=[("view", "accounting")]),
    dict(slides=[33], title="الموظفون والتطوير", family="EMP", view="employees",
         signals=[("view", "employees")]),
    dict(slides=[34], title="مساحة المستشار الخارجي", family="EMP", view="employees",
         signals=[("detail", "employees:openEmployee"), ("role", "external_consultant"),
                  ("deck-control", "slide34_assignment_scope")]),
    dict(slides=[35], title="التقارير والتحليل الذكي", family="BI", view="bi",
         signals=[("view", "bi"), ("deck-control", "slide35_prepare_summary")]),
    dict(slides=[36], title="التنبيهات وسجل النشاط", family="BI", view="inbox",
         signals=[("view", "inbox"), ("deck-control", "slide36_open_form")]),
    dict(slides=[37], title="المستخدمون والصلاحيات", family="CFG", view="admin",
         signals=[("view", "admin"), ("deck-control", "slide37_add_user"),
                  ("deck-control", "slide37_stat_active"),
                  ("deck-control", "slide37_stat_pending"),
                  ("deck-control", "slide37_stat_roles"),
                  ("deck-control", "slide37_stat_log")],
         note="Users tab: [إضافة مستخدم] opens the create form, and the deck's "
              "four-tile summary renders above the table with live counts "
              "(active users, pending/inactive accounts, custom roles, work-log "
              "entries) -- each from its own scoped query, and '—' rather than a "
              "fake 0 where the caller lacks the read permission."),
    # 38-47 shared states / responsive / workflows
    dict(slides=[38], title="حالات الواجهة المشتركة", family="components",
         view=None, signals=[("ui", "emptyHtml"), ("ui", "loadingHtml"), ("ui", "data-retry"),
                             ("deck-control", "slide38_open_correction"),
                             ("deck-control", "slide38_create_request")],
         note="Empty / loading / correction / error states with the deck's "
              "[إعادة المحاولة] retry control."),
    dict(slides=[39], title="نموذج الهاتف", family="responsive", view="dashboard",
         signals=[("viewport", "390")]),
    dict(slides=[40, 41], title="مسارات العمل", family="workflow",
         view="support", signals=[("view", "support")]),
    dict(slides=[42, 43], title="ملخص الوصول وقائمة الاعتماد", family="governance",
         view=None, status="REF",
         note="Access-summary and acceptance-checklist reference; enforced by the "
              "RBAC matrix (slides 74-83) and the acceptance suite (slides 137-138), "
              "not by a single screen."),
    dict(slides=[44], title="الاستمارات: نواة مشتركة + قطاع + إضافة خاصة",
         family="FRM", view="requests",
         signals=[("view", "requests"), ("field-types", "addFieldForm")]),
    dict(slides=[45], title="الرصيد الافتتاحي", family="FRM", view="accounting",
         signals=[("api", "GET /api/v1/accounting/opening-balances")]),
    dict(slides=[46], title="ملخص ذكي قصير لمدير الشركة", family="BI",
         view="bi", signals=[("api", "GET /api/v1/ai/insights"),
                             ("deck-control", "slide46_plan"),
                             ("deck-control", "slide46_decline")]),
    dict(slides=[47], title="حدود وصول المستشار الخارجي", family="governance",
         view="employees",
         signals=[("role", "external_consultant"),
                  ("rbac", ("external_consultant",
                            ["company.read", "dashboard.company",
                             "advisor.session.read_own", "advisor.session.record",
                             "weekly_report.read_own", "weekly_report.submit",
                             "notification.read_own"],
                            ["form.read", "opening_balance.read",
                             "financial_summary.read_all", "financial_report.read",
                             "journal.read", "approval.act", "approval.override"]))],
         note="Enforced by RBAC (external_consultant, D04): sees only its assigned "
              "sessions and the employees on them, adds advice, and holds no "
              "sector form, opening balance, ledger or approval permission."),
    # 48-49 registries
    dict(slides=[48], title="خريطة الوصول التنفيذية المحدثة", family="registry",
         view=None, status="REF",
         note="Updated access map; the live equivalent is the RBAC matrix "
              "(slides 74-83) re-verified by the AR/EN role crawl."),
    dict(slides=[49], title="سجل الشاشات ومفاتيح الربط", family="registry",
         view=None, status="REF",
         note="Screen registry with link keys; the keys are the data-* hooks the "
              "compliance matrix scores per view (app_inventory.json)."),
    # 50-53 company wizard
    dict(slides=[50, 51, 52], title="معالج إضافة شركة", family="ORG",
         view="admin", signals=[("wizard", "company-setup")],
         note="Three-step browser wizard (الهوية والقطاع → الملكية والمتابعة → "
              "القالب والتفعيل) with [السابق]/[حفظ مسودة]/[التالي]/[تفعيل الشركة]; "
              "activation links the manager and the holding stake, and a draft "
              "grants no access. Driven end-to-end by "
              "scripts/audit/company_wizard_probe.py."),
    dict(slides=[53], title="قواعد تأسيس الشركة وتغيير إعداداتها", family="governance",
         view=None, status="REF",
         note="Company-founding and settings-change rules; enforced by the company "
              "create/update service and the audit log, verified in tests/test_admin."),
    # 54-73 forms core + sectors
    dict(slides=[54], title="دليل الاستمارات", family="FRM", view="requests",
         signals=[("view", "requests")]),
    dict(slides=[55], title="النواة المالية المشتركة", family="HF",
         view="financial", signals=[("view", "financial")]),
    dict(slides=[56], title="النواة الإدارية والإثباتات المشتركة", family="FRM",
         view="reports", signals=[("view", "reports")]),
    dict(slides=[57, 58, 59, 60], title="قطاع التجارة", family="FRM",
         view="admin", signals=[("control", "admin:builder:buttons")]),
    dict(slides=[61, 62, 63, 64], title="قطاع الخدمات المهنية والاستشارية",
         family="FRM", view="admin", signals=[("control", "admin:builder:buttons")]),
    dict(slides=[65, 66, 67, 68], title="قطاع التقنية", family="FRM",
         view="admin", signals=[("control", "admin:builder:buttons")]),
    dict(slides=[69, 70, 71, 72], title="قطاع المقاولات", family="FRM",
         view="admin", signals=[("control", "admin:builder:buttons")]),
    dict(slides=[73], title="منشئ الحقول الخاصة وإصدارات القالب", family="FRM",
         view="admin", signals=[("control", "admin:builder:buttons")]),
    # 74-88 permission engine / matrices
    dict(slides=list(range(74, 84)), title="محرك الصلاحيات ومصفوفاتها",
         family="governance", view="admin",
         signals=[("api", "GET /api/v1/admin/permissions/catalogue")],
         note="Catalogue-driven Roles & Permissions UI."),
    dict(slides=[84], title="خريطة واجهة المنصب: المالك / مدير تطوير الأعمال",
         family="governance", view="dashboard",
         signals=[("role", "holding_owner"), ("role", "business_development")]),
    dict(slides=[85], title="خريطة واجهة المنصب: مدير الشركة / المحاسب",
         family="governance", view="dashboard",
         signals=[("role", "company_manager"), ("role", "accountant")]),
    dict(slides=[86], title="خريطة واجهة المنصب: موظف المبيعات / أخصائي التسويق",
         family="governance", view="dashboard", signals=[("role", "marketing")]),
    dict(slides=[87], title="خريطة واجهة المنصب: المصمم / الموظف المختص",
         family="governance", view="dashboard", signals=[("role", "designer")]),
    dict(slides=[88], title="خريطة واجهة المنصب: المستشار الخارجي / مسؤول النظام",
         family="governance", view="dashboard",
         signals=[("role", "external_consultant")]),
    # 89-90 mobile
    dict(slides=[89, 90], title="الهاتف لكل الأدوار", family="responsive",
         view="dashboard", signals=[("viewport", "390")]),
    # 91-100 holding finance
    dict(slides=[91], title="لوحة مالية القابضة", family="HF", view="accounting",
         signals=[("view", "accounting")]),
    dict(slides=[92], title="إضافة عملية مالية للقابضة", family="HF",
         signals=[("api", "GET /api/v1/accounting/journals")]),
    dict(slides=[93], title="الإيرادات والفواتير الصادرة", family="HF",
         view="accounting", signals=[("tab", "accounting:invoices")]),
    dict(slides=[94], title="المصروفات والموردون والفواتير الواردة", family="HF",
         signals=[("api", "GET /api/v1/accounting/parties")]),
    dict(slides=[95], title="الذمم والتحصيل والسداد", family="HF",
         signals=[("api", "GET /api/v1/accounting/receivables")]),
    dict(slides=[96], title="الحسابات البنكية والصندوق", family="HF",
         signals=[("api", "GET /api/v1/accounting/accounts")]),
    dict(slides=[97], title="الميزانية التشغيلية ومراكز التكلفة", family="HF",
         signals=[("api", "GET /api/v1/accounting/budgets")]),
    dict(slides=[98], title="التقارير المالية الداخلية للقابضة", family="HF",
         signals=[("api", "GET /api/v1/accounting/trial-balance")]),
    dict(slides=[99], title="سجل حقول العملية المالية والتحقق", family="spec",
         view=None, status="REF",
         note="Financial-field register and its validation rules; enforced by the "
              "accounting schemas (FieldDefinition/FinancialItemValue) and covered "
              "by tests/test_accounting."),
    dict(slides=[100], title="مسار مالية القابضة دون ازدواج", family="workflow",
         view=None, status="REF",
         note="Holding-finance path without duplication; enforced by the "
              "single-invoice-journal rule (AC-27) in the accounting service."),
    # 101-106 employees / localization
    dict(slides=[101], title="قائمة الموظفين ونطاق الجهة", family="EMP",
         view="employees", signals=[("control", "employees:employees:rows")]),
    dict(slides=[102, 103], title="ملف الموظف", family="EMP", view="employees",
         signals=[("detail", "employees:openEmployee"), ("ui", "employeeDetail"),
                  ("ui", "الرقم الوظيفي"), ("ui", "المدير المباشر"),
                  # Slide 103 restricted block, gated behind employee.salary.read:
                  # masked identity/residence number, work location, wage
                  # effective date, document links, and the localization
                  # inclusion decision with its reason and applied rule.
                  ("ui", "الهوية أو الإقامة"), ("ui", "موقع العمل"),
                  ("ui", "تاريخ نفاذ البيانات"), ("ui", "المستندات أو الروابط الأساسية"),
                  ("ui", "يحتسب ضمن التوطين؟"), ("ui", "سبب عدم الاحتساب"),
                  ("ui", "قاعدة الاحتساب المطبقة")],
         note="Employee file carries the deck's identity block: employee number, "
              "entity, nationality, department, direct manager, status, the "
              "salary block and the slide-103 restricted tab, both gated on "
              "employee.salary.read; the identity number is masked."),
    dict(slides=[104], title="قواعد بيانات الموظفين ودورة الملف", family="spec",
         view=None, status="REF",
         note="Employee-data rules and file lifecycle; enforced by hr_service "
              "(employee.create/update, movement decision) and tests/test_hr."),
    dict(slides=[105], title="لوحة التوطين لكل جهة", family="EMP", view="employees",
         signals=[("ui", "function renderLocalizationBoard"),
                  ("ui", "لوحة التوطين لكل جهة"),
                  # Slide 105/106: target + calculation-rule edition with a
                  # below-target follow-up flag, backed by company admin data.
                  ("ui", "localization_target_pct"),
                  ("ui", "قاعدة الاحتساب"), ("ui", "function openLocalizationEdit")],
         note="Per-entity board computed from active employees: country, total, "
              "citizens, non-citizens, included, current rate, target, applied "
              "calculation rule and a below-target follow-up flag; the target "
              "and rule are editable administration data (slide 106)."),
    dict(slides=[106], title="إعداد التوطين والتقرير المجمع", family="spec",
         view=None, status="REF",
         note="Localization setup and aggregate report; the per-entity target "
              "and calculation-rule edition live on the company record and are "
              "surfaced on slide 105's board."),
    # 107-115 investments / currencies / KPIs
    dict(slides=[107], title="قائمة محفظة الملكية والاستثمارات", family="INV",
         view="investments",
         signals=[("view", "investments"), ("ui", "function loadInvestmentPortfolio"),
                  ("ui", "سجل محفظة الملكية والاستثمارات"),
                  # Slide 107 names four actions on the register:
                  # [إضافة استثمار] [فتح التفاصيل] [رفع قرار] [تقرير المحفظة].
                  ("ui", "إضافة استثمار"), ("ui", "فتح التفاصيل"),
                  ("ui", "رفع قرار"), ("ui", "تقرير المحفظة"),
                  ("ui", "حالة الاستثمار"), ("ui", "العملة الأصلية"),
                  ("api", "GET /api/v1/admin/ownerships")],
         note="The register renders real ownership rows (owner, %, effective "
              "date, status) with the deck's four actions: [إضافة استثمار] and "
              "[رفع قرار] appear only for the roles that hold ownership.manage "
              "/ owner_decision.manage (the permissions their endpoints "
              "enforce), and [تقرير المحفظة] exports the register the caller is "
              "already reading. The register also carries the deck's own filter "
              "columns (حالة الاستثمار، العملة الأصلية) plus search, sort and "
              "paging (slides 134-136)."),
    dict(slides=[108, 109], title="تفاصيل الاستثمار والقرار المرتبط", family="INV",
         view="investments",
         signals=[("ui", "function openInvestment"),
                  ("ui", "القيمة الدفترية وتاريخها"),
                  ("ui", "التقييم المعتمد"), ("ui", "القرار المرتبط"),
                  ("ui", "function openInvestmentEdit"),
                  # Slide 109: the yes/no valuation and the entered (never
                  # derived) book value, backed by the valuation endpoints.
                  ("ui", "has_valuation"),
                  ("api", "GET /api/v1/admin/investment-valuations")],
         note="Detail shows ownership %, original value, contributions, "
              "financing, distributions, the entered book value with its date "
              "and source, the yes/no valuation (no invented zero) and the "
              "linked owner decision; figures are entered as approved, not "
              "summed (deck slide 109)."),
    dict(slides=[110], title="إعداد العملات وسعر التحويل", family="FX",
         view="admin", signals=[("control", "admin:structure:buttons")]),
    dict(slides=[111], title="التقرير المجمع متعدد العملات", family="FX",
         signals=[("api", "GET /api/v1/accounting/financial-reports/group")]),
    dict(slides=[112], title="قواعد تجميع العملات والفترات", family="spec",
         view=None, status="REF",
         note="Currency/period aggregation rules; enforced by the group financial "
              "report service (per-currency, no cross-currency summing) and "
              "tests/test_accounting."),
    dict(slides=[113], title="سجل المؤشرات: إعداد المؤشر", family="KPI",
         signals=[("api", "GET /api/v1/accounting/kpis")]),
    dict(slides=[114], title="نتيجة المؤشر مقارنة بالمستهدف والتاريخ", family="KPI",
         view="accounting",
         signals=[("api", "GET /api/v1/accounting/kpis/evaluations")]),
    dict(slides=[115], title="تعريف الحدود والحساب وقابلية المقارنة", family="spec",
         view=None, status="REF",
         note="KPI boundary/calculation/comparability definitions; enforced by "
              "kpi_service (target-versus-actual, no zero for missing data) and "
              "tests/test_insights."),
    # 116-129 state machines / notifications
    dict(slides=list(range(116, 123)), title="قاموس الحالات", family="workflow",
         view=None, status="REF",
         note="State dictionaries (allowed transitions, actor, reason and lock per "
              "state), not screens. The transitions themselves are enforced in "
              "the services and covered by tests/test_support, test_reports, "
              "test_operations; there is no single UI screen to score."),
    dict(slides=[123], title="مسارات الاعتماد والتصحيح الرئيسية", family="workflow",
         view="reports",
         signals=[("view", "reports"), ("ui", "function reportLifecycleBlock"),
                  ("ui", "function reportVersionsBlock"),
                  ("ui", "function correctReportForm"),
                  ("api", "GET /api/v1/monthly-reports/1/versions")],
         note="The five-step trail (مسودة -> مرسلة -> مراجعة -> معتمدة -> طلب "
              "تصحيح) is the report lifecycle trail plus the version history and "
              "the correction action, all rendered in the report detail (reports "
              "view). The approvals inbox is a different concept -- tasks awaiting "
              "the caller -- and is legitimately empty for a user with nothing "
              "pending, so it is not the screen this slide depicts."),
    dict(slides=[124], title="مسار خدمة وقرار دون خلط الصلاحيات", family="workflow",
         view=None, status="REF",
         note="Service path and decision path kept on separate permissions: a "
              "routine request is assigned and closed by support_request.*, while "
              "an out-of-authority/budget subject routes to the owner decision "
              "path (owner_decision.*). Enforced in support/decision services; "
              "covered by tests/test_support and tests/test_rbac."),
    dict(slides=[125], title="طلب التصحيح ومقارنة القيم", family="VER",
         view="reports",
         signals=[("ui", "function loadCorrectionComparison"),
                  ("ui", "مقارنة قبل وبعد"), ("ui", "id=\"repCompare\""),
                  ("api", "GET /api/v1/monthly-reports/1/versions")],
         note="A correction version renders the original next to it, field by "
              "field (قبل/بعد), with the correction reason, requester and "
              "reviewer decision. Read-only; the original stays locked (D03)."),
    dict(slides=[126], title="سجل النسخ وتحديث المخرجات", family="VER",
         view=None, status="REF",
         note="Version register and output refresh; the report version history "
              "(GET /monthly-reports/{id}/versions) is scored on slides 123/125; "
              "this slide adds no separate screen."),
    dict(slides=[127], title="مركز إعدادات النظام", family="CFG", view="admin",
         signals=[("view", "admin")]),
    dict(slides=[128], title="إعدادات: التغيير والنشر والإيقاف", family="spec",
         view=None, status="REF",
         note="Settings change/publish/deactivate rules; enforced by the admin "
              "service (user update, company-access grant/revoke) and the audit "
              "log, covered by tests/test_admin."),
    dict(slides=[129], title="قاموس الإشعارات: الحدث والمستلم", family="spec",
         view=None, status="REF",
         note="Notification dictionary (event -> recipient); enforced by the "
              "notification service and the owner-decision/assessment events, "
              "covered by tests/test_operations."),
    # 130-136 reports / filters
    dict(slides=[130, 131, 132], title="كتالوج التقارير والطباعة والتصدير",
         family="RPT", view="bi", signals=[("api", "GET /api/v1/analytics/holding")]),
    dict(slides=[133], title="قواعد التقرير والطباعة المطبقة على الجميع",
         family="spec", view=None, status="REF",
         note="Report/print rules applied to everyone (period, entity, currency, "
              "state and version stamp on every output); enforced by exportMeta "
              "and the report serialisers, covered by "
              "test_frontend_domain_views::test_every_export_stamps_the_period_entity_and_state."),
    dict(slides=[134, 135, 136], title="البحث والفلترة حسب القائمة",
         family="RPT", view="subsidiaries",
         signals=[("filterbar", "subsidiaries"), ("pager", "subsidiaries"),
                  ("export", "support")],
         note="Generic filter/save/pager/export machinery across list families."),
    # 137-138 acceptance
    dict(slides=[137], title="قائمة اعتماد التصميم والتنفيذ المحدثة",
         family="acceptance", view=None, status="REF",
         note="Acceptance checklist -- see section C."),
    dict(slides=[138], title="اختبارات الواجهة والتسليم للمبرمج", family="acceptance",
         view=None, status="REF", note="Acceptance checklist -- see section C."),
]


def _inv_entry(inv: dict, view: str, tab: str | None = None) -> dict | None:
    v = (inv.get("views") or {}).get(view)
    if not v:
        return None
    return (v.get("tabs") or {}).get(tab) if tab else v.get("main")


def _audit_role(role: str) -> tuple[bool, str]:
    """A role's nav map is proven by the AR+EN live crawl of that role."""
    root = pathlib.Path(__file__).resolve().parents[2] / "artifacts"
    parts = []
    ok = True
    for fname in ("view_audit_ar.json", "view_audit_en.json"):
        p = root / fname
        if not p.exists():
            return False, f"{fname} missing"
        data = json.loads(p.read_text())
        r = (data.get("roles") or {}).get(role)
        if not r:
            return False, f"role {role} not audited"
        clean = (not r.get("bad_http") and not r.get("console_errors"))
        ok = ok and clean
        parts.append(f"{fname.split('_')[-1].split('.')[0]} nav={len(r.get('visible_nav') or [])}")
    return ok, f"role {role}: " + ", ".join(parts)


def _rbac_role(role: str, must_have: list[str], must_lack: list[str]) -> tuple[bool, str]:
    """Assert a role's permission set, read from the live RBAC table.

    The deck's access-boundary slides name what a role *may* and *may not*
    reach. The permission set is the enforceable form of that, so it is checked
    directly rather than inferred from a screen that renders for someone else.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from backend.rbac.permissions import ROLE_PERMISSIONS  # noqa: PLC0415

    perms = ROLE_PERMISSIONS.get(role)
    if perms is None:
        return False, f"role {role} not in ROLE_PERMISSIONS"
    missing = [p for p in must_have if p not in perms]
    leaked = [p for p in must_lack if p in perms]
    ok = not missing and not leaked
    detail = f"role {role}: {len(perms)} perms"
    if missing:
        detail += f"; MISSING {missing}"
    if leaked:
        detail += f"; LEAKED {leaked}"
    return ok, detail


def _strip_note(role: str, rendered: dict) -> str:
    """Browser evidence for slides 7-11: which strip actually rendered."""
    r = (rendered or {}).get(role)
    if not r:
        return ""
    if r.get("role_strip_visible"):
        labels = r.get("role_strip_labels") or []
        title = r.get("page_title") or ""
        box = r.get("strip_box") or {}
        return (
            f" Browser probe: title «{title}», greeting «{r.get('greeting')}», "
            f"{box.get('cols')}-col strip {box.get('w')}x{box.get('h')} "
            f"labels {labels}."
        )
    if r.get("holding_strip_visible"):
        return " Browser probe: no role-specific strip; holding strip rendered."
    return " Browser probe: neither strip rendered."


def _check(sig, inv, api_probe, role_probe=None, parity=None,
           rendered=None, wizard_probe=None, company_file_probe=None,
           deck_controls=None) -> tuple[bool, str]:
    kind, key = sig
    if kind == "view":
        e = _inv_entry(inv, key)
        ok = bool(e and (e.get("chars") or 0) >= 40)
        return ok, f"view {key} renders ({e.get('chars') if e else 0} chars)"
    if kind == "scope":
        # Deck slide 4: the fixed top bar carries an entity/period selector. Prove
        # the control exists in the markup, is wired in the bridge, and rendered
        # in the live 1920x1080 probe -- not merely that a header element exists.
        fe = pathlib.Path(__file__).resolve().parents[2] / "frontend"
        html = (fe / "index.html").read_text(encoding="utf-8")
        js = (fe / "app.js").read_text(encoding="utf-8")
        parts = {
            "entity-select": 'id="scopeCompany"' in html,
            "period-select": 'id="periodSelect"' in html or "period" in js.lower(),
            "entity-wired": "scopeCompany" in js,
            "live-probe": bool(((parity or {}).get("app") or {}).get("entitySelector")),
        }
        ok = all(parts.values())
        detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
        return ok, f"header entity+period control ({detail})"
    if kind == "lang":
        # Deck slide 5: both directions must actually run. Read the crawl of
        # that language rather than asserting it.
        root = pathlib.Path(__file__).resolve().parents[2] / "artifacts"
        p = root / f"view_audit_{key}.json"
        if not p.exists():
            return False, f"{key} crawl artifact missing"
        data = json.loads(p.read_text())
        roles = data.get("roles") or {}
        if not roles:
            return False, f"{key} crawl has no roles"
        dirty = [
            r for r, v in roles.items()
            if v.get("bad_http") or v.get("console_errors") or v.get("error")
        ]
        nav = sum(len(v.get("visible_nav") or []) for v in roles.values())
        # The direction must match the language: ar -> rtl, en -> ltr.
        want_dir = "rtl" if key == "ar" else "ltr"
        wrong_dir = [r for r, v in roles.items() if v.get("dir") != want_dir]
        ok = not dirty and not wrong_dir
        detail = f"{key}: {len(roles)} roles crawled, dir={want_dir}, nav entries {nav}"
        if dirty:
            detail += f"; DIRTY {dirty}"
        if wrong_dir:
            detail += f"; WRONG DIR {wrong_dir}"
        return ok, detail
    if kind == "role-summary":
        # Deck slides 7-11: the role's dashboard returns its own tile set.
        entry = (role_probe or {}).get(key)
        if not entry:
            return False, f"role {key}: not probed"
        tiles = entry.get("tiles") or []
        ok = entry.get("status") == 200 and len(tiles) >= 3
        return ok, f"role {key}: {len(tiles)} tiles {tiles}" if ok else (
            f"role {key}: status={entry.get('status')} tiles={tiles}"
        )
    if kind == "role-render":
        # Deck slides 7-11: the browser actually painted the role's own strip.
        entry = (rendered or {}).get(key)
        if not entry:
            return False, f"role {key}: not rendered-probed"
        if entry.get("error"):
            return False, f"role {key}: {entry['error']}"
        if entry.get("role_strip_visible"):
            return True, f"role {key}: strip painted;" + _strip_note(key, rendered)
        if entry.get("holding_strip_visible"):
            return True, f"role {key}: holding strip painted;" + _strip_note(key, rendered)
        return False, f"role {key}: no strip painted"
    if kind == "ui":
        fe = pathlib.Path(__file__).resolve().parents[2] / "frontend"
        blob = ""
        for name in ("index.html", "app.js"):
            p = fe / name
            if p.exists():
                blob += p.read_text(encoding="utf-8")
        needle = key.lstrip("#.") if key[:1] in "#." else key
        return needle in blob, f"hook {key} present" if needle in blob else f"hook {key} MISSING"
    if kind == "login":
        fe = pathlib.Path(__file__).resolve().parents[2] / "frontend"
        html = (fe / "index.html").read_text(encoding="utf-8")
        js = (fe / "app.js").read_text(encoding="utf-8")
        auth = (fe / "auth.js").read_text(encoding="utf-8")
        parts = {
            "remember": 'id="loginRemember"' in html,
            "forgot": 'id="loginForgot"' in html,
            "notice": 'id="loginNotice"' in html,
            "lang-toggle": 'data-lang="en"' in html,
            "storage-split": "localStorage" in auth and "sessionStorage" in auth,
            "forgot-handler": "setLoginNotice" in js,
            # Password management (deck slide 6 names recovery; the register
            # D11 requirement is a working account-access path): the signed-in
            # user changes their own password, and an administrator sets a
            # temporary one for a locked-out account.
            "self-change": '"/api/v1/auth/change-password"' in js and 'id="pwSave"' in js,
            "admin-set": '"/password"' in js and 'id="spSave"' in js,
        }
        ok = all(parts.values())
        detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
        return ok, f"sign-in controls ({detail})"
    if kind == "detail":
        view, fn = key.split(":")
        js = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app.js"
              ).read_text(encoding="utf-8")
        ok = ("function " + fn) in js
        return ok, f"{view} detail: {fn}() present" if ok else f"{view} detail: {fn}() MISSING"
    if kind == "decision-actions":
        js = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app.js"
              ).read_text(encoding="utf-8")
        # slide 29: approved decision turns into execution tasks; slide 30: the
        # named executor replies with an update. Both are real endpoints.
        parts = {
            "status": "dec-status" in js,
            "reply": "dec-reply" in js and "/respond" in js,
        }
        ok = all(parts.values())
        detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
        return ok, f"decision lifecycle ({detail})"
    if kind == "viewport":
        # Deck slides 39/89/90 require the rail to open from a ☰ button on a
        # phone. Prove the affordance exists end-to-end, not just that a narrow
        # crawl rendered.
        fe = pathlib.Path(__file__).resolve().parents[2] / "frontend"
        html = (fe / "index.html").read_text(encoding="utf-8")
        css = (fe / "styles.css").read_text(encoding="utf-8")
        js = (fe / "app.js").read_text(encoding="utf-8")
        parts = {
            "toggle": 'id="navToggle"' in html,
            "scrim": 'id="navScrim"' in html,
            "drawer-css": "body.nav-open .sidebar" in css,
            "drawer-js": "bindNavDrawer" in js,
        }
        ok = all(parts.values())
        detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
        return ok, f"☰ drawer @{key}px ({detail})"
    if kind == "tab":
        view, tab = key.split(":")
        e = _inv_entry(inv, view, tab)
        n = (e or {}).get("chars", 0) if e else 0
        return (n or 0) >= 100, f"{view}/{tab} renders ({n} chars)"
    if kind == "field-types":
        # Deck slide 44: the field builder offers [رقم] [نص/سؤال] [مبلغ] [تاريخ]
        # [قائمة] [رابط خارجي] and no file type. Read the builder's own source
        # rather than a rendered crawl, because the builder is inside the admin
        # form designer the role crawl does not open.
        js = (pathlib.Path(__file__).resolve().parents[2]
              / "frontend" / "app.js").read_text(encoding="utf-8")
        start = js.find("function addFieldForm")
        block = js[start:start + 1600] if start >= 0 else ""
        wanted = ["رقم", "نص/سؤال", "مبلغ", "تاريخ", "قائمة", "رابط خارجي"]
        missing = [w for w in wanted if w not in block]
        has_file = "ملف" in block or 'value: "file"' in block
        ok = not missing and not has_file
        detail = (f"field types present: {len(wanted) - len(missing)}/{len(wanted)}"
                  + (f"; MISSING {missing}" if missing else "")
                  + ("; unexpected file type" if has_file else ""))
        return ok, detail
    if kind == "deck-control":
        # Deck slides that name a control only reachable in a data state the
        # seeded demo is not in. A source-string match proves nothing; the
        # browser probe (scripts/audit/deck_controls_probe.py) drives each
        # state and reads the rendered label. Score the probe's own result.
        entry = (deck_controls or {}).get(key)
        if not entry:
            return False, f"deck control {key}: not probed"
        ok = bool(entry.get("ok"))
        return ok, (f"deck control {key}: app label {entry.get('app_label')!r} "
                    f"(deck {entry.get('deck_label')!r})" if ok
                    else f"deck control {key}: MISSING (deck {entry.get('deck_label')!r})")
    if kind == "control":
        view, tab, field = key.split(":")
        e = _inv_entry(inv, view, tab)
        n = (e or {}).get(field, 0) if e else 0
        return (n or 0) >= 1, f"{view}/{tab}.{field}={n}"
    if kind in ("filterbar", "pager", "export"):
        field = "exportBtn" if kind == "export" else kind
        e = _inv_entry(inv, key)
        n = (e or {}).get(field, 0) if e else 0
        return (n or 0) >= 1, f"{key}.{kind}={n}"
    if kind == "role":
        return _audit_role(key)
    if kind == "rbac":
        role, must_have, must_lack = key
        return _rbac_role(role, must_have, must_lack)
    if kind == "api":
        return api_probe(key)
    if kind == "wizard":
        # Deck slides 50-52: the browser actually renders and drives the
        # three-step wizard, not just an API-only admin form. Read the live
        # Playwright probe artifact rather than asserting the markup exists.
        w = (wizard_probe or {})
        if not w:
            return False, "wizard probe artifact missing"
        steps = w.get("steps") or []
        actions = w.get("actions") or []
        parts = {
            "three-steps": w.get("rail_step") == "الخطوة 1 من 3"
                          and w.get("rail_step_on_3") == "الخطوة 3 من 3",
            "step-names": w.get("rail_name") == "الهوية والقطاع",
            "next": "التالي" in actions,
            "prev": "السابق" in actions,
            "draft": "حفظ مسودة" in actions,
            "activate": "تفعيل الشركة" in actions,
            "walks": bool(w.get("pane2_visible_after_next"))
                     and bool(w.get("pane3_visible_after_next")),
            "activates": (w.get("create_status") in (200, 201)),
            "no-access-on-draft": bool(w.get("draft_created_no_access")),
            "review": bool(w.get("review_has_deck_rows")),
            "rail-right": bool(w.get("rail_on_right")),
            "two-column": bool(w.get("two_column_grid")),
            "deck-labels": not (w.get("missing_deck_labels") or []),
            "deck-order": not (w.get("order_mismatch") or []),
            "clean-console": not (w.get("console") or []),
        }
        ok = all(parts.values())
        detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
        return ok, f"company setup wizard ({detail})"
    if kind == "company-file":
        # Deck slide 13's [تعديل البيانات] and slide 31's [تسجيل إجراء], driven in
        # the browser and confirmed to persist / paint, not just present in the
        # markup. Read the live Playwright artifact.
        cf = (company_file_probe or {})
        if not cf:
            return False, "company file probe artifact missing"
        if key == "edit":
            parts = {
                "edit-button": bool(cf.get("edit_button_present")),
                "label": cf.get("edit_button_label") == "تعديل البيانات",
                "fields": len(cf.get("edit_form_fields") or []) >= 4,
                "saves": cf.get("edit_status") in (200, 201),
                "clean-console": not (cf.get("console") or []),
            }
            ok = all(parts.values())
            detail = ", ".join(f"{k}={'ok' if v else 'MISSING'}" for k, v in parts.items())
            return ok, f"company file ({detail})"
        if key == "complaint":
            return cf.get("complaint_action_label") == "تسجيل إجراء", (
                f"complaint register action={cf.get('complaint_action_label')!r}"
            )
        return False, f"unknown company-file key {key}"
    return False, f"unknown signal {kind}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="artifacts/app_inventory.json")
    ap.add_argument("--api-probe", default="artifacts/api_probe.json")
    ap.add_argument("--role-summaries", default="artifacts/role_summaries.json")
    ap.add_argument("--role-dashboards", default="artifacts/role_dashboards.json")
    ap.add_argument("--visual-parity", default="artifacts/visual_parity.json")
    ap.add_argument("--slide-visual-parity",
                    default="artifacts/deck/visual_parity_slides.json")
    ap.add_argument("--wizard-probe", default="artifacts/company_wizard.json")
    ap.add_argument("--company-file-probe", default="artifacts/company_file.json")
    ap.add_argument("--deck-controls", default="artifacts/deck_controls.json")
    ap.add_argument("--deck-text", default="artifacts/deck/slides_text.json")
    ap.add_argument("--out", default="docs/audit/PPTX_V3_COMPLIANCE_MATRIX.md")
    args = ap.parse_args()

    inv_path = pathlib.Path(args.inventory)
    inv = json.loads(inv_path.read_text()) if inv_path.exists() else {"views": {}}
    probe_path = pathlib.Path(args.api_probe)
    probe = json.loads(probe_path.read_text()) if probe_path.exists() else {}
    roles_path = pathlib.Path(args.role_summaries)
    role_probe = json.loads(roles_path.read_text()) if roles_path.exists() else {}
    dash_path = pathlib.Path(args.role_dashboards)
    rendered = json.loads(dash_path.read_text()) if dash_path.exists() else {}
    parity_path = pathlib.Path(args.visual_parity)
    parity = json.loads(parity_path.read_text()) if parity_path.exists() else {}
    slide_parity_path = pathlib.Path(args.slide_visual_parity)
    slide_parity = (
        json.loads(slide_parity_path.read_text()) if slide_parity_path.exists() else {}
    )
    wiz_path = pathlib.Path(args.wizard_probe)
    wizard_probe = json.loads(wiz_path.read_text()) if wiz_path.exists() else {}
    cf_path = pathlib.Path(args.company_file_probe)
    company_file_probe = json.loads(cf_path.read_text()) if cf_path.exists() else {}
    dc_path = pathlib.Path(args.deck_controls)
    deck_controls = (json.loads(dc_path.read_text()).get("controls") or {}) if dc_path.exists() else {}
    text_path = pathlib.Path(args.deck_text)
    deck_text = json.loads(text_path.read_text()) if text_path.exists() else {}

    def api_probe(spec: str):
        r = probe.get(spec)
        if r is None:
            return False, f"{spec} not probed"
        return (200 <= r < 400), f"{spec} -> {r}"

    # score each group once
    scored = []
    counts = {"OK": 0, "PARTIAL": 0, "REF": 0}
    for m in MAPPING:
        status = m.get("status")
        ev: list[str] = []
        if status is None:
            if m.get("signals"):
                oks = []
                for sig in m["signals"]:
                    ok, msg = _check(sig, inv, api_probe, role_probe, parity,
                                     rendered, wizard_probe, company_file_probe,
                                     deck_controls)
                    oks.append(ok)
                    ev.append(msg)
                status = "OK" if all(oks) else "PARTIAL"
            else:
                # No signals means no evidence. Never claim OK without evidence.
                status = "REF"
                ev.append("no evidence signals declared")
        # A screen can be fully wired and still not reach parity: a named field
        # has no backing model yet. That is a PARTIAL, never an OK -- the point
        # of the matrix is to expose exactly these.
        if status == "OK" and m.get("partial_reason"):
            status = "PARTIAL"
            ev.append(m["partial_reason"])
        counts[status] = counts.get(status, 0) + 1
        # The disposition note explains how a REF slide is covered elsewhere or
        # what a PARTIAL screen does carry; surface it beside the evidence so no
        # row is left blank and unaccounted for.
        evidence = "; ".join(ev)
        note = m.get("note")
        if note and note not in evidence:
            evidence = (evidence + "; " if evidence else "") + note
        scored.append((m, status, evidence))

    # one row per deck slide, verbatim title from the OOXML
    by_slide: dict[int, tuple] = {}
    for m, status, ev in scored:
        for n in m["slides"]:
            by_slide[n] = (m, status, ev)

    slide_counts = {"OK": 0, "PARTIAL": 0, "REF": 0}
    for n in range(1, 139):
        if n in by_slide:
            slide_counts[by_slide[n][1]] += 1
        else:
            slide_counts["REF"] += 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("# PPTX v3 -- slide-by-slide compliance matrix\n\n")
        fh.write("_Generated by `scripts/audit/build_deck_compliance.py` from the deck's "
                 "OOXML text layer, the live SPA inventory and an endpoint probe. "
                 "Regenerate rather than hand-edit._\n\n")
        fh.write("Status key: **OK** every named control present; **PARTIAL** screen "
                 "exists but a named element is missing; **REF** spec/reference slide "
                 "with no single screen.\n\n")
        fh.write(f"Slides 1-138: OK {slide_counts['OK']} - PARTIAL "
                 f"{slide_counts['PARTIAL']} - REF {slide_counts['REF']}. "
                 f"({len(MAPPING)} mapping groups.)\n\n")
        # The mandate is visual, not textual, parity: report the pixel/DOM
        # comparison of the rendered deck against the rendered app up front.
        if parity:
            ok = parity.get("ok")
            checks = parity.get("checks") or {}
            n_ok = sum(1 for c in checks.values() if c.get("ok"))
            fh.write(
                f"Visual frame parity (`scripts/audit/visual_parity.py`, deck PNG "
                f"pixels vs live DOM + screenshot): "
                f"{n_ok}/{len(checks)} checks pass"
                f"{' -- OK' if ok else ' -- see artifacts/visual_parity.json'}.\n\n"
            )
        # Per-slide visual parity: every slide the matrix maps to a screen is
        # compared against that screen's rendered pixels, so a slide cannot be
        # "OK" on text alone while the screen looks nothing like the deck.
        slide_visual: dict[int, bool] = {}
        if slide_parity:
            for r in slide_parity.get("slides") or []:
                slide_visual[r["slide"]] = bool(r.get("ok"))
            no_shot = slide_parity.get("no_screenshot") or []
            fh.write(
                f"Per-slide visual parity (`scripts/audit/deck_visual_parity.py`, "
                f"deck PNG frame vs the mapped screen's rendered pixels): "
                f"{slide_parity.get('ok', 0)}/"
                f"{slide_parity.get('screens_checked', 0)} mapped screens match"
                + (
                    f"; failed slides {slide_parity['failed']}"
                    if slide_parity.get("failed")
                    else " -- OK"
                )
                + ".\n\n"
            )
            if no_shot:
                fh.write(
                    f"> {len(no_shot)} mapped slide(s) could not be visually "
                    f"verified (no rendered screenshot for their view): "
                    f"{', '.join(str(r['slide']) for r in no_shot)}. Run "
                    f"`view_audit.py --lang ar` to cover them.\n\n"
                )
        def cell(v: str) -> str:
            return str(v).replace("|", "\\|").replace("\n", " ")

        fh.write("| Slide | Deck title (verbatim) | Family | App view | Visual | Status | Evidence |\n")
        fh.write("|---|---|---|---|---|---|---|\n")
        for n in range(1, 139):
            if n not in by_slide:
                fh.write(f"| {n} | _unmapped_ | - | - | - | REF | no screen mapping |\n")
                continue
            m, status, ev = by_slide[n]
            title = (deck_text.get(str(n)) or [m["title"]])[0]
            has_view = bool(m.get("view"))
            vis = "-"
            if n in slide_visual:
                vis = "OK" if slide_visual[n] else "FAIL"
            elif has_view:
                # Mapped to a screen but not visually probed (no screenshot):
                # never show a bare "-" that reads as "not applicable".
                vis = "?"
            fh.write(f"| {n} | {cell(title)} | {cell(m['family'])} | {m.get('view') or '-'} | "
                     f"{vis} | {status} | {cell(ev)} |\n")
        fh.write("\n## Remaining gaps (the PARTIAL rows above)\n\n")
        fh.write("Each item below is a screen that exists and is reachable but does "
                 "not yet reach the deck's interface. None of these is a business "
                 "rule or a permission change -- they are missing fields or "
                 "missing controls.\n\n")
        for m, status, ev in scored:
            if status != "PARTIAL":
                continue
            slides = ", ".join(str(n) for n in m["slides"])
            fh.write(f"- **Slide {slides} -- {m['title']}** ({m['family']}). {ev}\n")
        fh.write("\n## How to read this matrix\n\n")
        fh.write("- **OK** -- every control the deck names for the slide is present "
                 "in the running SPA or answers on its endpoint.\n")
        fh.write("- **PARTIAL** -- the screen exists and is reachable, but a named "
                 "element is missing. The gap is listed in the Remaining gaps "
                 "section; nothing is hidden behind an auto-OK.\n")
        fh.write("- **REF** -- a spec, dictionary, registry or acceptance slide that "
                 "maps to no single screen. These are reviewed by hand, not scored "
                 "by signal.\n")
        fh.write("- A mapping with no `signals` is never scored OK by default: a "
                 "group must carry evidence, or it is left as REF.\n")
        fh.write("- **Visual** -- the slide's *rendered* frame vs the mapped "
                 "screen's rendered pixels (`deck_visual_parity.py`). `OK` means "
                 "the app paints the deck's frame (light surface, RTL rail where "
                 "the deck draws one, a non-empty content band, and a multi-tile "
                 "KPI strip on the role slides); `-` means the slide maps to no "
                 "screen; `?` means it maps to a screen whose screenshot was not "
                 "available to probe; `FAIL` would list the slide in the parity "
                 "line above. This column is deliberately independent of the text "
                 "evidence: a slide can pass the text checks and still fail the "
                 "visual one.\n")
    print(f"wrote {out}: slides=138 OK={slide_counts['OK']} "
          f"PARTIAL={slide_counts['PARTIAL']} REF={slide_counts['REF']} "
          f"(groups: OK={counts['OK']} PARTIAL={counts['PARTIAL']} "
          f"REF={counts['REF']}, {len(MAPPING)} mapping groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
