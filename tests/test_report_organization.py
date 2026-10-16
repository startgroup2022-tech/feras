"""S09 -- AI text organization ("تنظيم النص بالذكاء الاصطناعي").

Spec: the subsidiary monthly report offers an AI action that *organises* the
manager's narrative and shows a suggestion **while the original stays**
("يعرض اقتراح تنظيم مع بقاء الأصل", "لا إشعار").

The tests below prove the two guarantees from the spec, through the real API and
database, plus the scoping and audit rules:

* the suggestion is returned but the stored report is byte-for-byte unchanged,
* the manager can then *explicitly* apply a suggestion through the normal PATCH,
* an out-of-scope report is a 404 (no existence leak),
* the action is audited, and the deterministic fallback never invents a number.
"""

from __future__ import annotations

from backend.ai.organize import ORGANIZABLE_FIELDS, organize_text
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import ReportStatus
from backend.db.models.report import MonthlyReport


def _draft_with_text(client, world, auth, *, text: str) -> int:
    created = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "500000",
            "expenses": "300000",
            "net_result": "200000",
            "important_developments": text,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


# --------------------------------------------------------------------------
# the suggestion never modifies the original
# --------------------------------------------------------------------------
def test_organization_returns_a_proposal_without_touching_the_report(
    client, world, auth, db
):
    text = "  أطلقنا خط إنتاج جديد .  أطلقنا خط إنتاج جديد .  وزدنا الطاقة."
    report_id = _draft_with_text(client, world, auth, text=text)

    response = client.post(
        f"/api/v1/monthly-reports/{report_id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fields_considered"] == 1
    proposal = body["proposals"][0]
    assert proposal["field"] == "important_developments"
    # The original is echoed back exactly as stored, and the suggestion differs.
    assert proposal["original"] == text
    assert proposal["organized"] != text
    assert proposal["grounded"] is True
    assert proposal["ungrounded_numbers"] == []

    # Nothing was persisted by the read-only suggestion call.
    db.expire_all()
    stored = db.get(MonthlyReport, report_id)
    assert stored.important_developments == text


def test_the_manager_can_then_apply_a_suggestion_explicitly(client, world, auth, db):
    text = "نص غير منظم   بمسافات .  سطر ثانٍ بدون نقطة"
    report_id = _draft_with_text(client, world, auth, text=text)

    proposal = client.post(
        f"/api/v1/monthly-reports/{report_id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    ).json()["proposals"][0]["organized"]

    applied = client.patch(
        f"/api/v1/monthly-reports/{report_id}",
        headers=auth(world["alpha_mgr"]),
        json={"important_developments": proposal},
    )
    assert applied.status_code == 200, applied.text

    db.expire_all()
    assert db.get(MonthlyReport, report_id).important_developments == proposal


def test_only_fields_with_text_are_proposed(client, world, auth):
    report_id = _draft_with_text(client, world, auth, text="تطور واحد فقط.")

    body = client.post(
        f"/api/v1/monthly-reports/{report_id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    ).json()

    assert [p["field"] for p in body["proposals"]] == ["important_developments"]


# --------------------------------------------------------------------------
# isolation and permissions
# --------------------------------------------------------------------------
def test_out_of_scope_report_is_not_found(client, world, auth):
    # alpha_mgr may not reach beta's report at all.
    response = client.post(
        f"/api/v1/monthly-reports/{world['beta_report'].id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    )
    assert response.status_code == 404


def test_reader_without_update_permission_is_denied(client, world, auth):
    report_id = _draft_with_text(client, world, auth, text="نص.")
    # The accountant reads every report but does not update a company draft.
    response = client.post(
        f"/api/v1/monthly-reports/{report_id}/organize-narrative",
        headers=auth(world["accountant"]),
    )
    assert response.status_code == 403


def test_submitted_report_cannot_be_organized(client, world, auth):
    # The shared fixture's alpha report is already submitted (locked).
    response = client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------
# audit + deterministic grounding
# --------------------------------------------------------------------------
def test_organization_is_audited(client, world, auth, db):
    report_id = _draft_with_text(client, world, auth, text="نص للتدقيق.")
    client.post(
        f"/api/v1/monthly-reports/{report_id}/organize-narrative",
        headers=auth(world["alpha_mgr"]),
    )

    from backend.db.models import AuditLog

    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == AuditAction.AI_TEXT_ORGANIZED,
            AuditLog.entity_id == report_id,
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].entity_type == "monthly_report"


def test_deterministic_organization_is_grounded_by_construction():
    text = "إيرادات 100 والمصروفات 40. إيرادات 100 والمصروفات 40. صافي 60"
    organised = organize_text(text)
    # A number present in the source may be kept; a new one may never appear.
    assert "100" in organised and "40" in organised and "60" in organised
    assert organised.count("إيرادات 100") == 1  # duplicates collapsed


def test_organize_text_handles_empty_input():
    assert organize_text("") == ""
    assert organize_text("   ") == ""
    assert organize_text(None) == ""


def test_organizable_fields_are_real_report_columns():
    from backend.db.models.report import MonthlyReport

    for name in ORGANIZABLE_FIELDS:
        assert hasattr(MonthlyReport, name), name
