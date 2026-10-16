"""Schema validation, including a regression test for the flagged_reason bug.

The original bug: ``flagged_reason`` was checked with a ``field_validator``.
Pydantic v2 skips field validators for fields left at their default, so
``is_financially_accurate=False`` with no reason was silently accepted. The fix
moved the check to a ``model_validator``. These tests pin that behaviour so it
cannot regress.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.models import (
    AIAskRequest,
    CreateUserRequest,
    FinancialReviewRequest,
    MonthlyReportCreateRequest,
    SupportRequestCreateRequest,
)


# --------------------------------------------------------------------------
# flagged_reason cross-field rule
# --------------------------------------------------------------------------
def test_inaccurate_review_without_a_reason_is_rejected():
    with pytest.raises(ValidationError):
        FinancialReviewRequest(is_financially_accurate=False)


def test_inaccurate_review_with_a_blank_reason_is_rejected():
    with pytest.raises(ValidationError):
        FinancialReviewRequest(is_financially_accurate=False, flagged_reason="   ")


def test_inaccurate_review_with_a_reason_is_accepted():
    model = FinancialReviewRequest(
        is_financially_accurate=False, flagged_reason="أرقام غير مكتملة"
    )

    assert model.flagged_reason == "أرقام غير مكتملة"


def test_accurate_review_needs_no_reason():
    model = FinancialReviewRequest(is_financially_accurate=True)

    assert model.flagged_reason is None


def test_accurate_review_may_still_carry_notes():
    model = FinancialReviewRequest(
        is_financially_accurate=True, financial_notes="تم التحقق من الأرقام"
    )

    assert model.financial_notes == "تم التحقق من الأرقام"


# --------------------------------------------------------------------------
# AI question
# --------------------------------------------------------------------------
@pytest.mark.parametrize("question", ["", " ", "  ", "a", "?"])
def test_ai_question_must_have_content(question):
    with pytest.raises(ValidationError):
        AIAskRequest(question=question)


def test_ai_question_is_trimmed():
    model = AIAskRequest(question="  ملخص الأداء  ")

    assert model.question == "ملخص الأداء"


# --------------------------------------------------------------------------
# monthly report
# --------------------------------------------------------------------------
@pytest.mark.parametrize("month", [0, 13, -1])
def test_report_month_must_be_within_range(month):
    with pytest.raises(ValidationError):
        MonthlyReportCreateRequest(company_id=1, period_year=2027, period_month=month)


@pytest.mark.parametrize("year", [1999, 2101])
def test_report_year_must_be_within_range(year):
    with pytest.raises(ValidationError):
        MonthlyReportCreateRequest(company_id=1, period_year=year, period_month=1)


def test_report_rejects_negative_revenue():
    with pytest.raises(ValidationError):
        MonthlyReportCreateRequest(
            company_id=1, period_year=2027, period_month=1, revenue="-1"
        )


def test_report_accepts_a_negative_net_result():
    """A loss is legitimate and must not be blocked by validation."""
    model = MonthlyReportCreateRequest(
        company_id=1, period_year=2027, period_month=1, net_result="-5000"
    )

    assert model.net_result == -5000


# --------------------------------------------------------------------------
# support request
# --------------------------------------------------------------------------
def test_support_title_minimum_length():
    with pytest.raises(ValidationError):
        SupportRequestCreateRequest(company_id=1, title="ab")


def test_support_category_defaults_to_general():
    model = SupportRequestCreateRequest(company_id=1, title="طلب دعم")

    assert model.category.value == "general"


def test_support_rejects_unknown_category():
    with pytest.raises(ValidationError):
        SupportRequestCreateRequest(company_id=1, title="طلب دعم", category="hr")


# --------------------------------------------------------------------------
# email validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "email",
    ["user@holding.sa", "first.last@sub.example.com", "ops@safir.local", "a@b.co"],
)
def test_valid_internal_emails_are_accepted(email):
    model = CreateUserRequest(
        email=email,
        password="StrongPass!2027",
        full_name_ar="مستخدم",
        role_code="company_manager",
    )

    assert model.email == email


@pytest.mark.parametrize("email", ["plain", "@nohost.com", "no-at.com", "spaces in@mail.com"])
def test_invalid_emails_are_rejected(email):
    with pytest.raises(ValidationError):
        CreateUserRequest(
            email=email,
            password="StrongPass!2027",
            full_name_ar="مستخدم",
            role_code="company_manager",
        )
