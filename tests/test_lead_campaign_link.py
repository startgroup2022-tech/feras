"""S13/S14 — a lead is *linked* to its campaign and company, never copied.

Spec §18 lists ``Lead ... campaign_id``; AC-13 requires "the customer is linked
to the campaign and the company without copying it"; AC-14 requires that the
customer count "is not doubled between manual and linked registration". These
tests pin the three rules down end to end:

* the link is a foreign key on the *existing* lead row (one record, not two),
* a campaign link outside the caller's scope is rejected like a missing one,
* ``lead_count`` (manual) and ``linked_lead_count`` (linked) are reported side
  by side and never summed,
* routing a lead to a company notifies that company's manager (Table 58).
"""

from __future__ import annotations

import pytest

from backend.db.models.notifications import Notification
from backend.db.models.website import WebsiteLead

PUBLIC = "/api/v1/public"


@pytest.fixture
def domain_world(world, make_user):
    """``world`` plus holding users granted write access to both companies.

    Mirrors ``test_holding_domain.domain_world``: the security model requires an
    explicit ``user_company_access`` row before any write.
    """
    owner_all = make_user(
        "owner_all@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    marketer = make_user("marketing@corp.sa", "marketing", [world["alpha"]])
    # Business development owns the lead pipeline; this one is scoped to alpha
    # only, which is what the isolation test needs.
    bd_alpha = make_user("bd_alpha@corp.sa", "business_development", [world["alpha"]])
    world = dict(world)
    world["owner_all"] = owner_all
    world["marketer"] = marketer
    world["bd_alpha"] = bd_alpha
    return world


def _make_lead(client, *, email: str = "sara@example.com") -> int:
    response = client.post(
        f"{PUBLIC}/leads/contact",
        json={
            "market": "bahrain",
            "locale": "ar",
            "full_name": "سارة أحمد",
            "email": email,
            "phone": "+9731111222",
            "consent": True,
            "inquiry_type": "general",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["reference"]


def _lead_id(db) -> int:
    return db.query(WebsiteLead).order_by(WebsiteLead.id.desc()).first().id


def _make_campaign(client, headers, company_id: int, name: str = "حملة الإطلاق") -> int:
    response = client.post(
        "/api/v1/operations/campaigns",
        json={"company_id": company_id, "name": name, "budget": "5000.00"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --------------------------------------------------------------------------
# the link itself (AC-13: linked, not copied)
# --------------------------------------------------------------------------
def test_lead_links_to_campaign_by_foreign_key(client, db, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    campaign_id = _make_campaign(client, auth(domain_world["marketer"]), domain_world["alpha"].id)

    patched = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"campaign_id": campaign_id},
        headers=auth(domain_world["owner_all"]),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["campaign_id"] == campaign_id

    # Persisted on the same row -- no second lead record was created.
    db.expire_all()
    assert db.query(WebsiteLead).count() == 1
    assert db.query(WebsiteLead).one().campaign_id == campaign_id


def test_campaign_view_shows_the_same_linked_lead_not_a_copy(client, db, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    campaign_id = _make_campaign(client, auth(domain_world["marketer"]), domain_world["alpha"].id)
    client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"campaign_id": campaign_id},
        headers=auth(domain_world["owner_all"]),
    )

    linked = client.get(
        f"/api/v1/operations/campaigns/{campaign_id}/leads",
        headers=auth(domain_world["marketer"]),
    )
    assert linked.status_code == 200, linked.text
    # The *same* lead id, from the one website_leads row.
    assert [lead["id"] for lead in linked.json()] == [lead_id]
    assert db.query(WebsiteLead).count() == 1


# --------------------------------------------------------------------------
# AC-14: manual vs linked counts never double
# --------------------------------------------------------------------------
def test_manual_and_linked_lead_counts_are_reported_side_by_side(client, db, domain_world, auth):
    _make_lead(client, email="a@example.com")
    _make_lead(client, email="b@example.com")
    campaign_id = _make_campaign(client, auth(domain_world["marketer"]), domain_world["alpha"].id)

    # Manual external result recorded by marketing.
    client.patch(
        f"/api/v1/operations/campaigns/{campaign_id}",
        json={"lead_count": 37},
        headers=auth(domain_world["marketer"]),
    )
    # Two leads are linked to the same campaign.
    for lead_id in [row.id for row in db.query(WebsiteLead).all()]:
        client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"campaign_id": campaign_id},
            headers=auth(domain_world["owner_all"]),
        )

    listed = client.get(
        f"/api/v1/operations/campaigns?company_id={domain_world['alpha'].id}",
        headers=auth(domain_world["marketer"]),
    )
    assert listed.status_code == 200, listed.text
    row = next(c for c in listed.json() if c["id"] == campaign_id)
    # Two distinct figures, never added into one.
    assert row["lead_count"] == 37
    assert row["linked_lead_count"] == 2


# --------------------------------------------------------------------------
# isolation (AC-13 / T02): an out-of-scope campaign is a 404, not a leak
# --------------------------------------------------------------------------
def test_linking_an_out_of_scope_campaign_is_not_found(client, db, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    # A campaign on beta, created by a user who may write beta.
    beta_campaign = _make_campaign(
        client, auth(domain_world["owner_all"]), domain_world["beta"].id, name="حملة بيتا"
    )

    # The BD user only has alpha access, so the beta campaign must look absent.
    denied = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"campaign_id": beta_campaign},
        headers=auth(domain_world["bd_alpha"]),
    )
    assert denied.status_code == 404
    db.expire_all()
    assert db.query(WebsiteLead).one().campaign_id is None


def test_linking_a_missing_campaign_is_not_found(client, db, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    missing = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"campaign_id": 999999},
        headers=auth(domain_world["owner_all"]),
    )
    assert missing.status_code == 404


# --------------------------------------------------------------------------
# routing notifies the company's manager (Table 58: توزيع على الشركة)
# --------------------------------------------------------------------------
def test_routing_a_lead_to_a_company_notifies_its_manager(client, db, world, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    manager = domain_world["alpha_mgr"]

    response = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"routed_company_id": domain_world["alpha"].id},
        headers=auth(domain_world["owner_all"]),
    )
    assert response.status_code == 200, response.text

    notices = db.query(Notification).filter(Notification.recipient_id == manager.id).all()
    assert any(n.entity_type == "website_lead" and n.entity_id == lead_id for n in notices)


def test_routing_does_not_notify_a_company_the_manager_does_not_own(
    client, db, world, domain_world, auth
):
    _make_lead(client)
    lead_id = _lead_id(db)
    beta_manager = world["beta_mgr"]

    client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"routed_company_id": domain_world["alpha"].id},
        headers=auth(domain_world["owner_all"]),
    )
    notices = db.query(Notification).filter(Notification.recipient_id == beta_manager.id).all()
    assert notices == []


def test_re_saving_the_same_company_does_not_re_notify(client, db, world, domain_world, auth):
    _make_lead(client)
    lead_id = _lead_id(db)
    manager = domain_world["alpha_mgr"]

    for _ in range(2):
        client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"routed_company_id": domain_world["alpha"].id},
            headers=auth(domain_world["owner_all"]),
        )
    notices = [
        n
        for n in db.query(Notification).filter(Notification.recipient_id == manager.id).all()
        if n.entity_type == "website_lead"
    ]
    assert len(notices) == 1
