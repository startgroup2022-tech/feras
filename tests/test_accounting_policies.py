"""D01: accountant-approved accounting policy registry.

Exercised against the real service + API + persistence path (no mocks):

* a newly recorded policy is a **draft** and is inert — ``effective_policy``
  never returns it, so an unapproved rule cannot influence a calculation;
* approval is the only way a value becomes effective, and it stamps who/when;
* approving a newer version supersedes the prior one and preserves it (history
  is never overwritten or deleted);
* a company-specific approved policy wins over the holding-wide default;
* draft and approval are separate permissions: the accountant may do both, but
  a role without ``accounting_policy.approve`` cannot approve.
"""

from __future__ import annotations

import pytest

from backend.db.models.enums import PolicyKind, PolicyStatus
from backend.services import accounting_service


@pytest.fixture
def policy_world(world, make_user):
    owner_all = make_user(
        "owner.pol@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    accountant = make_user("acc.pol@corp.sa", "accountant", [world["alpha"]])
    data = dict(world)
    data["owner_all"] = owner_all
    data["accountant_all"] = accountant
    return data


POLICIES = "/api/v1/accounting/policies"


def _draft(client, auth, user, **overrides):
    body = {"kind": PolicyKind.TAX.value, "value": "0.15"}
    body.update(overrides)
    return client.post(POLICIES, json=body, headers=auth(user))


# --------------------------------------------------------------------------
# draft is inert
# --------------------------------------------------------------------------
def test_new_policy_is_a_draft_and_inert(client, policy_world, auth, db):
    accountant = policy_world["accountant_all"]
    created = _draft(client, auth, accountant, company_id=policy_world["alpha"].id)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == PolicyStatus.DRAFT.value

    resolved = accounting_service.effective_policy(
        db, company_id=policy_world["alpha"].id, kind=PolicyKind.TAX.value
    )
    assert resolved is None  # a draft is never effective (D01)


def test_approval_makes_a_policy_effective(client, policy_world, auth, db):
    accountant = policy_world["accountant_all"]
    alpha = policy_world["alpha"].id
    policy = _draft(client, auth, accountant, company_id=alpha).json()

    approved = client.post(
        f"{POLICIES}/{policy['id']}/approve", headers=auth(accountant)
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == PolicyStatus.APPROVED.value
    assert approved.json()["approved_at"] is not None

    resolved = accounting_service.effective_policy(
        db, company_id=alpha, kind=PolicyKind.TAX.value
    )
    assert resolved is not None
    assert resolved.id == policy["id"]


def test_unknown_kind_is_rejected(client, policy_world, auth):
    accountant = policy_world["accountant_all"]
    response = _draft(client, auth, accountant, kind="not_a_kind")
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# versioning preserves history
# --------------------------------------------------------------------------
def test_new_version_supersedes_and_preserves_the_prior(client, policy_world, auth, db):
    accountant = policy_world["accountant_all"]
    alpha = policy_world["alpha"].id

    v1 = _draft(client, auth, accountant, company_id=alpha, value="0.15").json()
    client.post(f"{POLICIES}/{v1['id']}/approve", headers=auth(accountant))

    v2 = _draft(client, auth, accountant, company_id=alpha, value="0.20").json()
    assert v2["version"] == 2
    client.post(f"{POLICIES}/{v2['id']}/approve", headers=auth(accountant))

    rows = client.get(
        f"{POLICIES}?company_id={alpha}&kind=tax", headers=auth(accountant)
    ).json()
    by_id = {r["id"]: r for r in rows}
    # The prior version is retained, marked superseded, not overwritten.
    assert by_id[v1["id"]]["status"] == PolicyStatus.SUPERSEDED.value
    assert by_id[v2["id"]]["status"] == PolicyStatus.APPROVED.value
    assert by_id[v2["id"]]["supersedes_id"] == v1["id"]

    resolved = accounting_service.effective_policy(db, company_id=alpha, kind="tax")
    assert resolved.id == v2["id"]


def test_double_approval_is_rejected(client, policy_world, auth):
    accountant = policy_world["accountant_all"]
    policy = _draft(client, auth, accountant, company_id=policy_world["alpha"].id).json()
    client.post(f"{POLICIES}/{policy['id']}/approve", headers=auth(accountant))
    again = client.post(f"{POLICIES}/{policy['id']}/approve", headers=auth(accountant))
    assert again.status_code == 409, again.text


# --------------------------------------------------------------------------
# resolution precedence
# --------------------------------------------------------------------------
def test_company_policy_overrides_the_holding_default(client, policy_world, auth, db):
    accountant = policy_world["accountant_all"]
    owner = policy_world["owner_all"]
    alpha = policy_world["alpha"].id

    # Holding-wide default (company_id None), approved.
    default = _draft(client, auth, owner, company_id=None, value="0.15").json()
    client.post(f"{POLICIES}/{default['id']}/approve", headers=auth(owner))

    # Company-specific override, approved.
    override = _draft(client, auth, accountant, company_id=alpha, value="0.05").json()
    client.post(f"{POLICIES}/{override['id']}/approve", headers=auth(accountant))

    resolved = accounting_service.effective_policy(db, company_id=alpha, kind="tax")
    assert resolved.id == override["id"]
    assert str(resolved.value) == override["value"]

    # A company without its own policy falls back to the holding default.
    resolved_beta = accounting_service.effective_policy(
        db, company_id=policy_world["beta"].id, kind="tax"
    )
    assert resolved_beta.id == default["id"]


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------
def test_company_manager_cannot_draft_a_policy(client, policy_world, auth):
    manager = policy_world["alpha_mgr"]
    response = _draft(client, auth, manager, company_id=policy_world["alpha"].id)
    assert response.status_code == 403, response.text


def test_policy_approve_is_a_distinct_permission(client, policy_world, auth, db, make_user):
    # A custom role with draft-only rights must not be able to approve.
    from backend.services import role_service

    role_service.create_role(
        db,
        actor=policy_world["owner_all"],
        payload={
            "code": "policy_drafter",
            "name_ar": "مُسوِّد السياسات",
            "name_en": "Policy drafter",
            "permissions": ["accounting_policy.read", "accounting_policy.manage"],
        },
    )
    user = make_user("drafter@corp.sa", "policy_drafter", [policy_world["alpha"]])
    alpha = policy_world["alpha"].id

    draft = client.post(
        POLICIES, json={"kind": "tax", "value": "0.15", "company_id": alpha},
        headers=auth(user),
    )
    assert draft.status_code == 201, draft.text
    denied = client.post(f"{POLICIES}/{draft.json()['id']}/approve", headers=auth(user))
    assert denied.status_code == 403, denied.text


def test_effective_endpoint_returns_none_for_an_unapproved_kind(client, policy_world, auth):
    accountant = policy_world["accountant_all"]
    response = client.get(
        f"{POLICIES}/effective?company_id={policy_world['alpha'].id}&kind=asset",
        headers=auth(accountant),
    )
    assert response.status_code == 200, response.text
    assert response.json() is None
