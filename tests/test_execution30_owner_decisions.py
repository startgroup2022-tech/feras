"""Execution 30: owner-approved decisions D01, D03, D04, D09, D11.

Exercised end-to-end against the real service + API + persistence path (no
mocks), including RBAC denials and the append-only / no-retroactive-change
safety properties that make these decisions safe to deploy.

* **D01** -- a financial-policy change is proposed (with a mandatory reason and
  the previous value shown), and only a decision by a role holding
  ``accounting_policy.approve`` activates the version. A rejected proposal
  changes nothing; a draft never influences a calculation.
* **D03** -- lead assignment/reassignment records an immutable history row and a
  reassignment requires a reason.
* **D04** -- history reads are scoped: a company manager never sees another
  company's history.
* **D09** -- a base-currency change is request -> review -> owner approval ->
  scheduled -> applied, and can never be applied before its effective period.
* **D11** -- TOTP enrolment, single-use codes, recovery codes and login
  enforcement; 2FA cannot be bypassed by omitting the code.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.db.models.enums import (
    CurrencyChangeStatus,
    PolicyKind,
    PolicyProposalStatus,
    PolicyStatus,
)
from backend.db.models.website import WebsiteLead
from backend.services import accounting_service, two_factor_service

POLICIES = "/api/v1/accounting/policies"
CURRENCY = "/api/v1/accounting/currency-changes"
LEADS = "/api/v1/leads"


@pytest.fixture
def gov_world(world, make_user):
    """The shared world plus an owner-wide user, an accountant and a lead.

    Holding-wide roles read across companies but still need an explicit
    ``user_company_access`` row to *write* (see ``can_write_company``), so the
    owner and accountant are granted write access to both companies here.
    """
    both = [world["alpha"], world["beta"]]
    owner = make_user("owner.gov@corp.sa", "holding_owner", both)
    accountant = make_user("acc.gov@corp.sa", "accountant", both)
    bd = make_user("bd.gov@corp.sa", "business_development")
    data = dict(world)
    data["owner_all"] = owner
    data["accountant"] = accountant
    data["bd"] = bd
    return data


def _make_lead(db, *, market: str = "saudi") -> WebsiteLead:
    lead = WebsiteLead(
        reference=f"SAF-GOV-{market}-{id(object())}",
        source="website",
        market=market,
        service_type="general_contact",
        locale="ar",
        full_name="عميل محتمل",
        email="lead@example.com",
        consent_given=True,
        status="new",
        priority="normal",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


# ==========================================================================
# D01: financial-policy governance
# ==========================================================================
def _propose(client, auth, user, **overrides):
    body = {"kind": "tax", "reason": "تحديث النسبة الضريبية", "value": "0.15"}
    body.update(overrides)
    return client.post(f"{POLICIES}/proposals", json=body, headers=auth(user))


def test_accountant_proposal_is_inert_until_decided(client, gov_world, auth, db):
    """D01: a proposal is a documented change request; only a decision activates it."""
    accountant = gov_world["accountant"]
    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"].id

    created = _propose(client, auth, accountant, company_id=alpha)
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert proposal["status"] == PolicyProposalStatus.PENDING.value
    assert proposal["previous_value"] is None  # nothing effective yet

    # The draft version the proposal created is inert -- no calculation sees it.
    assert accounting_service.effective_policy(
        db, company_id=alpha, kind=PolicyKind.TAX.value
    ) is None

    # The owner (accounting_policy.approve) approves -> the version is effective.
    approved = client.post(
        f"{POLICIES}/proposals/{proposal['id']}/decide",
        json={"approve": True, "note": "معتمد"},
        headers=auth(owner),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == PolicyProposalStatus.APPROVED.value
    assert approved.json()["decided_at"] is not None

    resolved = accounting_service.effective_policy(
        db, company_id=alpha, kind=PolicyKind.TAX.value
    )
    assert resolved is not None
    assert Decimal(resolved.value) == Decimal("0.15")


def test_a_role_without_policy_approve_cannot_decide_a_proposal(
    client, gov_world, auth, db, make_user
):
    """Only a role holding ``accounting_policy.approve`` may decide a proposal."""
    from backend.services import role_service

    owner = gov_world["owner_all"]
    proposal = _propose(
        client, auth, owner, company_id=gov_world["alpha"].id
    ).json()

    role_service.create_role(
        db,
        actor=owner,
        payload={
            "code": "policy_drafter_only",
            "name_ar": "مُسوِّد فقط",
            "name_en": "Drafter only",
            "permissions": ["accounting_policy.read", "accounting_policy.manage"],
        },
    )
    drafter = make_user("drafter.only@corp.sa", "policy_drafter_only", [gov_world["alpha"]])

    denied = client.post(
        f"{POLICIES}/proposals/{proposal['id']}/decide",
        json={"approve": True}, headers=auth(drafter),
    )
    assert denied.status_code == 403, denied.text


def test_rejected_proposal_leaves_the_policy_unchanged(client, gov_world, auth, db):
    accountant = gov_world["accountant"]
    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"].id

    first = _propose(client, auth, accountant, company_id=alpha, value="0.15").json()
    client.post(
        f"{POLICIES}/proposals/{first['id']}/decide",
        json={"approve": True}, headers=auth(owner),
    )

    second = _propose(client, auth, accountant, company_id=alpha, value="0.30").json()
    assert Decimal(second["previous_value"]) == Decimal("0.15")  # side-by-side
    rejected = client.post(
        f"{POLICIES}/proposals/{second['id']}/decide",
        json={"approve": False, "note": "مرفوض"}, headers=auth(owner),
    )
    assert rejected.json()["status"] == PolicyProposalStatus.REJECTED.value

    # The effective policy is still the first, approved value.
    resolved = accounting_service.effective_policy(
        db, company_id=alpha, kind=PolicyKind.TAX.value
    )
    assert Decimal(resolved.value) == Decimal("0.15")


def test_a_decided_proposal_cannot_be_decided_again(client, gov_world, auth):
    accountant = gov_world["accountant"]
    owner = gov_world["owner_all"]
    proposal = _propose(
        client, auth, accountant, company_id=gov_world["alpha"].id
    ).json()
    client.post(
        f"{POLICIES}/proposals/{proposal['id']}/decide",
        json={"approve": True}, headers=auth(owner),
    )
    again = client.post(
        f"{POLICIES}/proposals/{proposal['id']}/decide",
        json={"approve": False}, headers=auth(owner),
    )
    assert again.status_code == 409, again.text


def test_a_manager_cannot_propose_a_policy(client, gov_world, auth):
    manager = gov_world["alpha_mgr"]
    response = _propose(client, auth, manager, company_id=gov_world["alpha"].id)
    assert response.status_code == 403, response.text


def test_proposal_requires_a_reason(client, gov_world, auth):
    accountant = gov_world["accountant"]
    response = _propose(
        client, auth, accountant, company_id=gov_world["alpha"].id, reason=""
    )
    assert response.status_code == 422, response.text


# ==========================================================================
# D03: lead assignment history
# ==========================================================================
def test_lead_assignment_is_recorded_with_history(client, gov_world, auth, db):
    owner = gov_world["owner_all"]
    bd = gov_world["bd"]
    lead = _make_lead(db)

    assigned = client.post(
        f"{LEADS}/{lead.id}/assign",
        json={"assignee_id": bd.id, "reason": "توزيع أولي"},
        headers=auth(owner),
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_id"] == bd.id

    history = client.get(
        f"{LEADS}/{lead.id}/assignments", headers=auth(owner)
    ).json()
    assert len(history) == 1
    assert history[0]["action"] == "assign"
    assert history[0]["new_assignee_id"] == bd.id
    assert history[0]["reason"] == "توزيع أولي"


def test_reassignment_requires_a_reason(client, gov_world, auth, db):
    owner = gov_world["owner_all"]
    bd = gov_world["bd"]
    alpha_mgr = gov_world["alpha_mgr"]
    lead = _make_lead(db)

    client.post(
        f"{LEADS}/{lead.id}/assign",
        json={"assignee_id": bd.id, "reason": "أول توزيع"},
        headers=auth(owner),
    )
    # Reassigning to a different person without a reason is refused.
    denied = client.post(
        f"{LEADS}/{lead.id}/assign",
        json={"assignee_id": alpha_mgr.id},
        headers=auth(owner),
    )
    assert denied.status_code == 422, denied.text

    ok = client.post(
        f"{LEADS}/{lead.id}/assign",
        json={"assignee_id": alpha_mgr.id, "reason": "نقل لمدير الشركة"},
        headers=auth(owner),
    )
    assert ok.status_code == 200, ok.text

    history = client.get(f"{LEADS}/{lead.id}/assignments", headers=auth(owner)).json()
    # Newest first; both events are retained (history is never rewritten).
    assert [h["action"] for h in history] == ["reassign", "assign"]
    assert history[0]["previous_assignee_id"] == bd.id
    assert history[0]["new_assignee_id"] == alpha_mgr.id
    assert history[0]["reason"] == "نقل لمدير الشركة"


def test_marketing_cannot_assign_a_lead(client, gov_world, auth, db, make_user):
    marketing = make_user("mkt.gov@corp.sa", "marketing")
    lead = _make_lead(db)
    response = client.post(
        f"{LEADS}/{lead.id}/assign",
        json={"assignee_id": gov_world["bd"].id},
        headers=auth(marketing),
    )
    assert response.status_code == 403, response.text


# ==========================================================================
# D09: base-currency change workflow
# ==========================================================================
def _request_change(client, auth, user, company_id, **overrides):
    body = {
        "company_id": company_id,
        "requested_currency": "USD",
        "justification": "التوسع الدولي",
    }
    body.update(overrides)
    return client.post(CURRENCY, json=body, headers=auth(user))


def test_currency_change_full_workflow(client, gov_world, auth, db):
    accountant = gov_world["accountant"]
    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"]

    created = _request_change(client, auth, accountant, alpha.id)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["status"] == CurrencyChangeStatus.REQUESTED.value
    assert row["current_currency"] == alpha.currency

    reviewed = client.post(
        f"{CURRENCY}/{row['id']}/review", json={"note": "تمت المراجعة"},
        headers=auth(accountant),
    )
    assert reviewed.json()["status"] == CurrencyChangeStatus.REVIEWED.value

    # The accountant cannot approve (owner-only).
    denied = client.post(
        f"{CURRENCY}/{row['id']}/decide",
        json={"approve": True, "effective_year": 2027, "effective_month": 11},
        headers=auth(accountant),
    )
    assert denied.status_code == 403, denied.text

    approved = client.post(
        f"{CURRENCY}/{row['id']}/decide",
        json={"approve": True, "effective_year": 2027, "effective_month": 11},
        headers=auth(owner),
    )
    assert approved.json()["status"] == CurrencyChangeStatus.SCHEDULED.value

    # The company's currency is unchanged until the change is applied.
    db.refresh(alpha)
    assert alpha.currency != "USD"

    # A future period cannot be applied early.
    early = client.post(f"{CURRENCY}/{row['id']}/apply", headers=auth(owner))
    assert early.status_code == 409, early.text


def test_currency_change_cannot_be_applied_before_its_period(client, gov_world, auth, db):
    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"]
    row = _request_change(client, auth, owner, alpha.id).json()
    client.post(
        f"{CURRENCY}/{row['id']}/decide",
        json={"approve": True, "effective_year": 2099, "effective_month": 1},
        headers=auth(owner),
    )
    response = client.post(f"{CURRENCY}/{row['id']}/apply", headers=auth(owner))
    assert response.status_code == 409, response.text
    db.refresh(alpha)
    assert alpha.currency != "USD"  # nothing changed retroactively


def test_currency_approval_requires_an_effective_period(client, gov_world, auth):
    owner = gov_world["owner_all"]
    row = _request_change(client, auth, owner, gov_world["alpha"].id).json()
    response = client.post(
        f"{CURRENCY}/{row['id']}/decide", json={"approve": True}, headers=auth(owner)
    )
    assert response.status_code == 422, response.text


def test_only_one_open_currency_request_per_company(client, gov_world, auth):
    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"].id
    first = _request_change(client, auth, owner, alpha)
    assert first.status_code == 201, first.text
    second = _request_change(client, auth, owner, alpha, requested_currency="EUR")
    assert second.status_code == 409, second.text


def test_currency_change_is_company_scoped(client, gov_world, auth, make_user):
    """A manager with access to one company cannot request a change elsewhere."""
    manager = gov_world["alpha_mgr"]  # company manager: no currency permission
    response = _request_change(client, auth, manager, gov_world["beta"].id)
    assert response.status_code == 403, response.text


# ==========================================================================
# D04: history access is scoped
# ==========================================================================
def test_history_read_is_company_scoped(client, gov_world, auth, db, make_user):
    """A company-confined role sees its own company's proposals plus holding-wide.

    Holding roles (owner/accountant) read across companies by design; the scope
    filter is exercised with a custom role confined to ``alpha``.
    """
    from backend.services import role_service

    owner = gov_world["owner_all"]
    alpha = gov_world["alpha"]
    beta = gov_world["beta"]

    _propose(client, auth, owner, company_id=alpha.id)
    _propose(client, auth, owner, company_id=beta.id, kind="fiscal_year", value_text="Jan")
    _propose(client, auth, owner, company_id=None, kind="invoice", value_text="INV")

    rows_owner = client.get(f"{POLICIES}/proposals", headers=auth(owner)).json()
    assert len(rows_owner) == 3

    role_service.create_role(
        db,
        actor=owner,
        payload={
            "code": "policy_reader_alpha",
            "name_ar": "قارئ السياسات",
            "name_en": "Policy reader",
            "permissions": ["accounting_policy.read"],
        },
    )
    scoped = make_user("scoped.reader@corp.sa", "policy_reader_alpha", [alpha])

    rows_scoped = client.get(f"{POLICIES}/proposals", headers=auth(scoped)).json()
    # Only the alpha-scoped and the holding-wide proposals are visible.
    assert {r["company_id"] for r in rows_scoped} == {None, alpha.id}


# ==========================================================================
# D11: two-factor authentication
# ==========================================================================
def _enrol_and_confirm(client, auth, user):
    enrol = client.post("/api/v1/auth/2fa/enrol", headers=auth(user))
    assert enrol.status_code == 200, enrol.text
    secret = enrol.json()["secret"]
    code = two_factor_service.totp_now(secret)
    confirm = client.post(
        "/api/v1/auth/2fa/confirm", json={"code": code}, headers=auth(user)
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


def test_two_factor_enrolment_and_login_enforcement(client, gov_world, auth, login):
    owner = gov_world["owner_all"]
    secret, codes = _enrol_and_confirm(client, auth, owner)
    assert len(codes) == 8

    status = client.get("/api/v1/auth/2fa", headers=auth(owner)).json()
    assert status["enabled"] is True

    # Login without a code is refused (2FA cannot be bypassed by omission).
    no_code = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": "TestPass!2027"},
    )
    assert no_code.status_code == 401, no_code.text

    # Login with a wrong code is refused.
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": "TestPass!2027", "code": "000000"},
    )
    assert bad.status_code == 401, bad.text

    # Login with a valid TOTP code succeeds.
    good = client.post(
        "/api/v1/auth/login",
        json={
            "email": owner.email,
            "password": "TestPass!2027",
            "code": two_factor_service.totp_now(secret),
        },
    )
    assert good.status_code == 200, good.text


def test_recovery_code_is_single_use(client, gov_world, auth):
    owner = gov_world["owner_all"]
    _, codes = _enrol_and_confirm(client, auth, owner)

    first = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": "TestPass!2027", "code": codes[0]},
    )
    assert first.status_code == 200, first.text
    # The same recovery code cannot be used twice.
    second = client.post(
        "/api/v1/auth/login",
        json={"email": owner.email, "password": "TestPass!2027", "code": codes[0]},
    )
    assert second.status_code == 401, second.text


def test_two_factor_disable_requires_a_valid_code(client, gov_world, auth):
    owner = gov_world["owner_all"]
    secret, _ = _enrol_and_confirm(client, auth, owner)

    denied = client.post(
        "/api/v1/auth/2fa/disable", json={"code": "000000"}, headers=auth(owner)
    )
    assert denied.status_code == 422, denied.text

    ok = client.post(
        "/api/v1/auth/2fa/disable",
        json={"code": two_factor_service.totp_now(secret)},
        headers=auth(owner),
    )
    assert ok.status_code == 204, ok.text
    assert client.get("/api/v1/auth/2fa", headers=auth(owner)).json()["enabled"] is False
