"""The demo seed must grant holding staff the company access their roles need.

Being holding-wide widens *reads* only: a write always needs an explicit
``user_company_access`` row with ``can_write``. The seed therefore has to grant
the owner and accountant every company -- they are the roles that post
journals, invoices and opening balances. Regression: the seed once created
those users with no grants at all, so ``require_company_access(write=True)``
refused every company-scoped write the owner or accountant attempted.
"""

from __future__ import annotations

from backend.db.models.identity import Company, User, UserCompanyAccess
from backend.db.session import SessionLocal
from backend.rbac.authorization import can_write_company
from scripts import seed_demo


def _writable_company_ids(db, email: str) -> set[int]:
    user = db.query(User).filter(User.email == email).one()
    return {
        a.company_id
        for a in db.query(UserCompanyAccess).filter(
            UserCompanyAccess.user_id == user.id, UserCompanyAccess.can_write.is_(True)
        )
    }


def test_seed_grants_holding_staff_write_access_to_every_company(db):
    seed_demo.seed(reset=False)

    db.expire_all()
    all_ids = {c.id for c in db.query(Company).all()}
    assert len(all_ids) == len(seed_demo.COMPANIES)

    for role_email in (
        f"owner@{seed_demo.DEMO_EMAIL_DOMAIN}",
        f"accountant@{seed_demo.DEMO_EMAIL_DOMAIN}",
    ):
        assert _writable_company_ids(db, role_email) == all_ids, role_email

    # A company manager stays confined to its own company.
    tech = db.query(Company).filter(Company.code == "SAF-TECH").one()
    assert _writable_company_ids(
        db, f"manager.tech@{seed_demo.DEMO_EMAIL_DOMAIN}"
    ) == {tech.id}


def test_seeded_owner_can_write_every_company(db):
    """The seeded owner passes the very check the accounting service runs."""
    seed_demo.seed(reset=False)

    db.expire_all()
    owner = (
        db.query(User)
        .filter(User.email == f"owner@{seed_demo.DEMO_EMAIL_DOMAIN}")
        .one()
    )
    for company in db.query(Company).all():
        assert can_write_company(owner, company.id) is True, company.code


def test_reseeding_backfills_a_missing_grant(db):
    """Re-seeding repairs a user whose grant row went missing."""
    seed_demo.seed(reset=False)

    owner = (
        db.query(User)
        .filter(User.email == f"owner@{seed_demo.DEMO_EMAIL_DOMAIN}")
        .one()
    )
    db.query(UserCompanyAccess).filter(
        UserCompanyAccess.user_id == owner.id
    ).delete()
    db.commit()

    with SessionLocal() as fresh:
        assert _writable_company_ids(fresh, owner.email) == set()

    seed_demo.seed(reset=False)

    db.expire_all()
    assert _writable_company_ids(db, owner.email) == {
        c.id for c in db.query(Company).all()
    }


def test_seed_installs_the_weekly_report_question_template(db):
    """AC-18: the S18 template has at most five questions, includes the advisor
    evaluation, and never re-asks the task count."""
    from backend.db.models.operations import (
        WEEKLY_REPORT_MAX_QUESTIONS,
        WeeklyReportQuestion,
    )

    seed_demo.seed(reset=False)
    db.expire_all()

    questions = (
        db.query(WeeklyReportQuestion)
        .filter(WeeklyReportQuestion.is_active.is_(True))
        .order_by(WeeklyReportQuestion.order_index)
        .all()
    )
    assert 0 < len(questions) <= WEEKLY_REPORT_MAX_QUESTIONS

    codes = {q.code for q in questions}
    assert "weekly_advisor_evaluation" in codes, "advisor evaluation question missing"
    assert not any("task" in code for code in codes), "template re-asks the task count"

    # Idempotent: a second seed must not duplicate the template.
    seed_demo.seed(reset=False)
    db.expire_all()
    assert db.query(WeeklyReportQuestion).count() == len(questions)
