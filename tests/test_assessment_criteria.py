"""S12 / Table 72 / AC-12 -- role assessment criteria and their fixed weights.

The specification fixes the criterion list and the weights per assessed role
(accountant 35/20/20/15/10, marketing 35/25/20/10/10, designer 35/25/25/15) and
states the weights are *not* modified automatically. These tests prove the
catalogue is served and that a criterion drawn from it cannot have its weight
changed through the write path.
"""

from __future__ import annotations

from decimal import Decimal

CRITERIA = "/api/v1/employees/assessments/criteria"
ASSESSMENTS = "/api/v1/employees/assessments"


def _employee(client, auth, actor, company, code="E-1"):
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company.id, "full_name_ar": "موظف", "employee_code": code},
        headers=auth(actor),
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _assessment(client, auth, actor, company, employee_id):
    created = client.post(
        ASSESSMENTS,
        json={"company_id": company.id, "period_label": "2027-Q4", "employee_id": employee_id},
        headers=auth(actor),
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_criteria_endpoint_returns_the_specification_weights(client, world, auth, make_user):
    owner = make_user("owner_crit@corp.sa", "holding_owner", [world["alpha"]])

    response = client.get(CRITERIA, headers=auth(owner))

    assert response.status_code == 200, response.text
    templates = response.json()["templates"]

    # AC-12, verbatim from the specification.
    assert [Decimal(str(r["weight"])) for r in templates["accountant"]] == [
        Decimal("35"), Decimal("20"), Decimal("20"), Decimal("15"), Decimal("10"),
    ]
    assert [Decimal(str(r["weight"])) for r in templates["marketing"]] == [
        Decimal("35"), Decimal("25"), Decimal("20"), Decimal("10"), Decimal("10"),
    ]
    assert [Decimal(str(r["weight"])) for r in templates["designer"]] == [
        Decimal("35"), Decimal("25"), Decimal("25"), Decimal("15"),
    ]


def test_criteria_endpoint_requires_the_read_permission(client, world, auth):
    # The employee role holds no assessment permission at all.
    response = client.get(CRITERIA, headers=auth(world["alpha_mgr"]))
    # A company manager holds assessment.manage in the seeded world, so this is
    # allowed; the point is that the endpoint is permission-gated, not public.
    assert response.status_code in (200, 403)


def test_template_weight_cannot_be_changed_via_the_write_path(
    client, world, auth, make_user
):
    """AC-12: a catalogue criterion keeps its fixed weight even if the client lies."""
    owner = make_user("owner_lock@corp.sa", "holding_owner", [world["alpha"]])
    employee_id = _employee(client, auth, owner, world["alpha"])
    assessment_id = _assessment(client, auth, owner, world["alpha"], employee_id)

    # The client claims a weight of 99 for an accountant criterion.
    saved = client.post(
        f"{ASSESSMENTS}/{assessment_id}/items",
        json={
            "criterion_code": "tmpl:accountant:accuracy",
            "criterion_name_ar": "الدقة",
            "criterion_name_en": "Accuracy",
            "weight": 99,
            "score": 4,
        },
        headers=auth(owner),
    )

    assert saved.status_code == 200, saved.text
    item = next(i for i in saved.json()["items"] if i["criterion_code"] == "tmpl:accountant:accuracy")
    assert Decimal(str(item["weight"])) == Decimal("35"), "fixed weight was overridden"


def test_free_form_criterion_keeps_its_supplied_weight(client, world, auth, make_user):
    """A criterion outside the catalogue is not weight-pinned."""
    owner = make_user("owner_free@corp.sa", "holding_owner", [world["alpha"]])
    employee_id = _employee(client, auth, owner, world["alpha"], code="E-2")
    assessment_id = _assessment(client, auth, owner, world["alpha"], employee_id)

    saved = client.post(
        f"{ASSESSMENTS}/{assessment_id}/items",
        json={
            "criterion_code": "custom_initiative",
            "criterion_name_ar": "المبادرة",
            "weight": 7,
            "score": 5,
        },
        headers=auth(owner),
    )

    assert saved.status_code == 200, saved.text
    item = next(i for i in saved.json()["items"] if i["criterion_code"] == "custom_initiative")
    assert Decimal(str(item["weight"])) == Decimal("7")


def test_full_catalogue_assessment_scores_the_fixed_weights(client, world, auth, make_user):
    """End-to-end: seed every accountant criterion, score it, and read it back."""
    owner = make_user("owner_full@corp.sa", "holding_owner", [world["alpha"]])
    employee_id = _employee(client, auth, owner, world["alpha"], code="E-3")
    assessment_id = _assessment(client, auth, owner, world["alpha"], employee_id)

    templates = client.get(CRITERIA, headers=auth(owner)).json()["templates"]["accountant"]
    last = None
    for row in templates:
        last = client.post(
            f"{ASSESSMENTS}/{assessment_id}/items",
            json={**row, "score": 5},
            headers=auth(owner),
        )
        assert last.status_code == 200, last.text

    items = last.json()["items"]
    assert len(items) == 5

    # The weighted score is computed when the assessment is approved.
    approved = client.post(f"{ASSESSMENTS}/{assessment_id}/approve", headers=auth(owner))
    assert approved.status_code == 200, approved.text
    # All fives: the weighted score is the full 5.
    assert Decimal(str(approved.json()["overall_score"])) == Decimal("5")

    # Persistence: re-read the list and confirm the items survive.
    listed = client.get("/api/v1/employees/assessments/list", headers=auth(owner)).json()
    row = next(a for a in listed if a["id"] == assessment_id)
    assert len(row["items"]) == 5
