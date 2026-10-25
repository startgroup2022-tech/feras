"""S13: the independent manager note on a website lead.

The spec (Table 58 / AC-13) draws a hard line: *the manager writes and
marketing reads*. These tests pin that line down end to end:

* the manager note lives in its own table, so marketing can never overwrite it,
* writing needs ``website_lead.manager_note`` -- marketing does not hold it,
* reading only needs ``website_lead.read``,
* every write is audited.
"""

from __future__ import annotations

import pytest

from backend.db.models.ai import AuditLog
from backend.db.models.website import LeadNote, WebsiteLead
from backend.rbac.permissions import MARKETING, Perm, ROLE_PERMISSIONS

PUBLIC = "/api/v1/public"


def _make_lead(client) -> int:
    response = client.post(
        f"{PUBLIC}/leads/contact",
        json={
            "market": "bahrain",
            "locale": "ar",
            "full_name": "سارة أحمد",
            "email": "sara@example.com",
            "phone": "+9731111222",
            "consent": True,
            "inquiry_type": "general",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["reference"]


def _lead_id(db) -> int:
    return db.query(WebsiteLead).one().id


# --------------------------------------------------------------------------
# permission gates
# --------------------------------------------------------------------------
def test_note_endpoints_require_authentication(client):
    assert client.get("/api/v1/leads/1/notes").status_code == 401
    assert client.post("/api/v1/leads/1/notes", json={"body": "x"}).status_code == 401


def test_marketing_role_does_not_hold_the_manager_note_permission():
    assert Perm.LEAD_MANAGER_NOTE in ROLE_PERMISSIONS["company_manager"]
    assert Perm.LEAD_MANAGER_NOTE in ROLE_PERMISSIONS["company_owner"]
    assert Perm.LEAD_MANAGER_NOTE not in MARKETING
    assert Perm.LEAD_MANAGER_NOTE not in ROLE_PERMISSIONS["marketing"]
    assert Perm.LEAD_MANAGER_NOTE not in ROLE_PERMISSIONS["business_development"]


def test_manager_can_write_and_marketing_can_only_read(client, db, world, make_user, login):
    _make_lead(client)
    lead_id = _lead_id(db)

    owner = login("owner@corp.sa")  # holding_owner
    response = client.post(
        f"/api/v1/leads/{lead_id}/notes",
        json={"body": "  متابعة مع العميل الأسبوع القادم.  "},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    note = response.json()
    assert note["body"] == "متابعة مع العميل الأسبوع القادم."
    assert note["lead_id"] == lead_id
    assert note["author_name_ar"]

    # Marketing can read the same note (website_lead.read is holding-level).
    make_user("mkt@corp.sa", "marketing")
    marketer = login("mkt@corp.sa")
    listing = client.get(f"/api/v1/leads/{lead_id}/notes", headers=marketer)
    assert listing.status_code == 200
    assert [n["body"] for n in listing.json()] == ["متابعة مع العميل الأسبوع القادم."]

    # ...but cannot write it.
    blocked = client.post(
        f"/api/v1/leads/{lead_id}/notes",
        json={"body": "التسويق يحاول التعديل"},
        headers=marketer,
    )
    assert blocked.status_code == 403


def test_company_manager_can_write_the_note(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    manager = login("alpha@corp.sa")  # company_manager holds the new permission
    response = client.post(
        f"/api/v1/leads/{lead_id}/notes",
        json={"body": "ملاحظة مدير الشركة"},
        headers=manager,
    )
    assert response.status_code == 201, response.text


def test_lead_detail_exposes_manager_notes(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    owner = login("owner@corp.sa")
    client.post(
        f"/api/v1/leads/{lead_id}/notes",
        json={"body": "ملاحظة أولى"},
        headers=owner,
    )
    detail = client.get(f"/api/v1/leads/{lead_id}", headers=owner)
    assert detail.status_code == 200
    assert [n["body"] for n in detail.json()["manager_notes"]] == ["ملاحظة أولى"]


# --------------------------------------------------------------------------
# the note is independent of the marketing-authored lead notes
# --------------------------------------------------------------------------
def test_manager_note_is_separate_from_internal_notes(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    owner = login("owner@corp.sa")  # holds website_lead.manage

    patched = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"internal_notes": "ملاحظة التسويق الداخلية"},
        headers=owner,
    )
    assert patched.status_code == 200
    assert patched.json()["internal_notes"] == "ملاحظة التسويق الداخلية"

    client.post(
        f"/api/v1/leads/{lead_id}/notes",
        json={"body": "ملاحظة المدير المستقلة"},
        headers=owner,
    )

    # Marketing edits its own internal note; the manager note is untouched.
    again = client.patch(
        f"/api/v1/leads/{lead_id}",
        json={"internal_notes": "تحديث التسويق"},
        headers=owner,
    )
    assert again.status_code == 200
    assert again.json()["internal_notes"] == "تحديث التسويق"
    assert [n["body"] for n in again.json()["manager_notes"]] == ["ملاحظة المدير المستقلة"]
    assert db.query(LeadNote).count() == 1


# --------------------------------------------------------------------------
# validation, ordering and audit
# --------------------------------------------------------------------------
def test_empty_note_is_rejected(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    owner = login("owner@corp.sa")
    response = client.post(
        f"/api/v1/leads/{lead_id}/notes", json={"body": ""}, headers=owner
    )
    assert response.status_code == 422


def test_note_on_missing_lead_is_404(client, world, login):
    owner = login("owner@corp.sa")
    assert (
        client.get("/api/v1/leads/999999/notes", headers=owner).status_code == 404
    )


def test_notes_are_returned_newest_first(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    owner = login("owner@corp.sa")
    for body in ("أولاً", "ثانياً", "ثالثاً"):
        client.post(
            f"/api/v1/leads/{lead_id}/notes", json={"body": body}, headers=owner
        )
    rows = client.get(f"/api/v1/leads/{lead_id}/notes", headers=owner).json()
    assert [r["body"] for r in rows] == ["ثالثاً", "ثانياً", "أولاً"]


def test_note_write_is_audited(client, db, world, login):
    _make_lead(client)
    lead_id = _lead_id(db)
    owner = login("owner@corp.sa")
    client.post(
        f"/api/v1/leads/{lead_id}/notes", json={"body": "ملاحظة"}, headers=owner
    )
    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "website_lead.note_added")
        .one()
    )
    assert entry.entity_type == "website_lead"
    assert entry.entity_id == str(lead_id)
