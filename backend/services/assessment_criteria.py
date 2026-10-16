"""Role assessment criteria and their fixed weights (S12, Table 72, AC-12).

The specification fixes the criterion list and the weights for each assessed
role -- for example the accountant is 35/20/20/15/10 and the designer is
35/25/25/15 -- and states explicitly that the weights are settled and are not
modified automatically (AC-12: "لا تعديل تلقائي للأوزان").

They are kept here as a single data catalogue rather than scattered literals so
an owner-approved change is one deliberate edit. A criterion drawn from this
catalogue is namespaced with a ``tmpl:`` prefix on its code, which is what lets
the write path refuse a silent weight change (see ``hr_service.set_assessment_item``).
"""

from __future__ import annotations

from decimal import Decimal

# (criterion_code, name_ar, name_en, weight) -- ordered as the specification lists.
_ROLE_CRITERIA: dict[str, list[tuple[str, str, str, Decimal]]] = {
    # المحاسب: الدقة 35؛ الالتزام بالتقارير 20؛ كشف وتصحيح الأخطاء 20؛ التوثيق 15؛ التعلم 10
    "accountant": [
        ("accuracy", "الدقة", "Accuracy", Decimal("35")),
        ("reporting_compliance", "الالتزام بالتقارير", "Reporting compliance", Decimal("20")),
        ("error_detection", "كشف وتصحيح الأخطاء", "Error detection and correction", Decimal("20")),
        ("documentation", "التوثيق", "Documentation", Decimal("15")),
        ("learning", "التعلم", "Learning", Decimal("10")),
    ],
    # التسويق: جودة العملاء 35؛ أهداف الحملات 25؛ الالتزام 20؛ دقة البيانات 10؛ التعلم 10
    "marketing": [
        ("lead_quality", "جودة العملاء", "Lead quality", Decimal("35")),
        ("campaign_goals", "أهداف الحملات", "Campaign goals", Decimal("25")),
        ("commitment", "الالتزام", "Commitment", Decimal("20")),
        ("data_accuracy", "دقة البيانات", "Data accuracy", Decimal("10")),
        ("learning", "التعلم", "Learning", Decimal("10")),
    ],
    # المصمم: الجودة والهوية 35؛ الالتزام 25؛ الإنجاز والتعديلات 25؛ المبادرة والتطور 15
    "designer": [
        ("quality_identity", "الجودة والهوية", "Quality and identity", Decimal("35")),
        ("commitment", "الالتزام", "Commitment", Decimal("25")),
        ("delivery_revisions", "الإنجاز والتعديلات", "Delivery and revisions", Decimal("25")),
        ("initiative_growth", "المبادرة والتطور", "Initiative and growth", Decimal("15")),
    ],
    # قيادة تطوير الأعمال: الفرص والمشاريع 30؛ الموظفون 25؛ متابعة الشركات 20؛ الموارد والميزانية 15؛ التقارير والقضايا 10
    "business_development_lead": [
        ("opportunities_projects", "الفرص والمشاريع", "Opportunities and projects", Decimal("30")),
        ("employees", "الموظفون", "Employees", Decimal("25")),
        ("company_follow_up", "متابعة الشركات", "Company follow-up", Decimal("20")),
        ("resources_budget", "الموارد والميزانية", "Resources and budget", Decimal("15")),
        ("reports_issues", "التقارير والقضايا", "Reports and issues", Decimal("10")),
    ],
    # قيادة الشركة: المالي والنمو 30؛ العمليات 25؛ الموظفون 20؛ التطوير والعملاء 15؛ الالتزام والتقارير 10
    "company_lead": [
        ("financial_growth", "المالي والنمو", "Financial and growth", Decimal("30")),
        ("operations", "العمليات", "Operations", Decimal("25")),
        ("employees", "الموظفون", "Employees", Decimal("20")),
        ("development_clients", "التطوير والعملاء", "Development and clients", Decimal("15")),
        ("compliance_reporting", "الالتزام والتقارير", "Compliance and reporting", Decimal("10")),
    ],
}

# Map a platform role to the criterion template the specification defines for it.
ROLE_TEMPLATE: dict[str, str] = {
    "accountant": "accountant",
    "marketing": "marketing",
    "designer": "designer",
    "business_development": "business_development_lead",
    "company_manager": "company_lead",
    "company_owner": "company_lead",
    "ceo": "company_lead",
}

TEMPLATE_CODE_PREFIX = "tmpl:"


def template_keys() -> list[str]:
    """The template keys a caller may request (e.g. ``accountant``)."""
    return sorted(_ROLE_CRITERIA)


def template_for_role(role_code: str) -> str | None:
    """The template key for a platform role, if one is defined."""
    return ROLE_TEMPLATE.get(role_code)


def criteria_for_template(template_key: str) -> list[dict]:
    """The ordered criteria (with fixed weights) for a template key.

    Raises ``KeyError`` for an unknown key so a caller cannot silently get an
    empty template.
    """
    rows = _ROLE_CRITERIA[template_key]
    return [
        {
            "criterion_code": f"{TEMPLATE_CODE_PREFIX}{template_key}:{code}",
            "criterion_name_ar": name_ar,
            "criterion_name_en": name_en,
            "weight": weight,
        }
        for code, name_ar, name_en, weight in rows
    ]


def fixed_weight_for_code(criterion_code: str) -> Decimal | None:
    """The catalogue weight for a ``tmpl:`` criterion code, else ``None``."""
    if not criterion_code.startswith(TEMPLATE_CODE_PREFIX):
        return None
    for template_key, rows in _ROLE_CRITERIA.items():
        for code, _ar, _en, weight in rows:
            if criterion_code == f"{TEMPLATE_CODE_PREFIX}{template_key}:{code}":
                return weight
    return None
