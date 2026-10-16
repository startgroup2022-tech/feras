"""S07 / Table 18 / AC-07 -- configurable-field visibility scope.

Table 18 lists ``نطاق الظهور`` (visibility scope) with the values الكل (all),
قطاع (sector) and شركة (company). AC-07 requires that a sector-scoped field
appears *only* for the companies of that sector, and that a financial item
cannot be defined without a calculation rule. These tests prove the scope is
enforced server-side, not merely hidden in the UI, and that the rule survives
persistence.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

FORMS = "/api/v1/forms"


@pytest.fixture
def scoped_world(ops_world, db):
    """ops_world plus a managed sector catalogue and companies tagged with it.

    ``alpha``/``beta`` share the ``Technology`` sector; ``gamma`` is in
    ``Logistics``. The sector-scoped field must reach only the first two.
    """
    from backend.db.models.enums import DepartmentStatus
    from backend.db.models.group import Sector

    tech = Sector(
        code="TECH", name_ar="التقنية", name_en="Technology",
        status=DepartmentStatus.ACTIVE.value, sort_order=1,
    )
    logistics = Sector(
        code="LOG", name_ar="اللوجستيات", name_en="Logistics",
        status=DepartmentStatus.ACTIVE.value, sort_order=2,
    )
    db.add_all([tech, logistics])
    ops_world["alpha"].sector = "Technology"
    ops_world["beta"].sector = "Technology"
    ops_world["gamma"].sector = "Logistics"
    db.commit()
    ops_world.update({"tech": tech, "logistics": logistics})
    return ops_world


def _publish(client, auth, owner, form_id):
    r = client.post(f"{FORMS}/{form_id}/publish", headers=auth(owner))
    assert r.status_code == 200, r.text
    return r.json()["published_version_id"]


def _field(client, auth, owner, form_id, **payload):
    body = {
        "key": payload.pop("key"),
        "field_type": payload.pop("field_type", "short_text"),
        "label_ar": payload.pop("label_ar", "حقل"),
        "label_en": payload.pop("label_en", "Field"),
    }
    body.update(payload)
    return client.post(f"{FORMS}/{form_id}/fields", json=body, headers=auth(owner))


def test_field_defaults_to_all_scope(client, scoped_world, auth):
    owner = scoped_world["owner"]
    form_id = scoped_world["form"].id
    created = _field(client, auth, owner, form_id, key="note")

    assert created.status_code == 201, created.text
    assert created.json()["scope"] == "all"
    assert created.json()["scope_sector"] is None
    assert created.json()["scope_company_id"] is None


def test_sector_scoped_field_is_returned_only_for_its_sector(
    client, scoped_world, auth
):
    """AC-07: a sector field appears only for the companies of that sector."""
    owner = scoped_world["owner"]
    form_id = scoped_world["form"].id

    created = _field(
        client, auth, owner, form_id,
        key="tech_only", scope="sector", scope_sector="Technology",
    )
    assert created.status_code == 201, created.text
    assert created.json()["scope"] == "sector"
    assert created.json()["scope_sector"] == "Technology"

    version_id = _publish(client, auth, owner, form_id)

    def keys_for(company_id):
        r = client.get(
            f"{FORMS}/{form_id}/versions/{version_id}?company_id={company_id}",
            headers=auth(owner),
        )
        assert r.status_code == 200, r.text
        return {f["key"] for f in r.json()["fields"]}

    assert "tech_only" in keys_for(scoped_world["alpha"].id)
    assert "tech_only" in keys_for(scoped_world["beta"].id)
    assert "tech_only" not in keys_for(scoped_world["gamma"].id)

    # The definition view (no company context, used by the builder) still shows
    # every field, so an administrator can see and edit the whole definition.
    definition = client.get(
        f"{FORMS}/{form_id}/versions/{version_id}", headers=auth(owner)
    ).json()
    assert "tech_only" in {f["key"] for f in definition["fields"]}


def test_sector_scoped_field_must_name_an_existing_sector(client, scoped_world, auth):
    owner = scoped_world["owner"]
    form_id = scoped_world["form"].id

    missing = _field(client, auth, owner, form_id, key="a", scope="sector")
    unknown = _field(
        client, auth, owner, form_id, key="b", scope="sector", scope_sector="Nope"
    )

    assert missing.status_code == 422, missing.text
    assert unknown.status_code == 422, unknown.text


def test_company_scoped_field_is_returned_only_for_that_company(
    client, scoped_world, auth
):
    owner = scoped_world["owner"]
    form_id = scoped_world["form"].id
    alpha_id = scoped_world["alpha"].id

    created = _field(
        client, auth, owner, form_id,
        key="alpha_only", scope="company", scope_company_id=alpha_id,
    )
    assert created.status_code == 201, created.text
    assert created.json()["scope_company_id"] == alpha_id

    version_id = _publish(client, auth, owner, form_id)
    other = client.get(
        f"{FORMS}/{form_id}/versions/{version_id}?company_id={scoped_world['beta'].id}",
        headers=auth(owner),
    ).json()
    assert "alpha_only" not in {f["key"] for f in other["fields"]}

    own = client.get(
        f"{FORMS}/{form_id}/versions/{version_id}?company_id={alpha_id}",
        headers=auth(owner),
    ).json()
    assert "alpha_only" in {f["key"] for f in own["fields"]}


def test_switching_scope_back_to_all_clears_the_qualifier(client, scoped_world, auth):
    """The unused qualifier never survives a scope change (no stale sector)."""
    owner = scoped_world["owner"]
    form_id = scoped_world["form"].id

    created = _field(
        client, auth, owner, form_id,
        key="switch", scope="sector", scope_sector="Technology",
    ).json()

    back = client.patch(
        f"{FORMS}/{form_id}/fields/{created['id']}",
        json={"scope": "all"},
        headers=auth(owner),
    )
    assert back.status_code == 200, back.text
    assert back.json()["scope"] == "all"
    assert back.json()["scope_sector"] is None
    assert back.json()["scope_company_id"] is None


def test_company_scoped_field_is_not_required_for_another_company(
    client, scoped_world, auth, db
):
    """AC-07: the scope governs validation, not just display.

    A required company-scoped field must not block a submission for a company
    it does not apply to. Proven at the validator level (``partial=False`` is
    what ``submit`` uses) so the assertion is not masked by the fixture's
    document requirement.
    """
    from backend.db.models.forms import FormVersion
    from backend.services import submission_service

    owner = scoped_world["owner"]
    alpha = scoped_world["alpha"]
    beta = scoped_world["beta"]
    form_id = scoped_world["form"].id

    _field(
        client, auth, owner, form_id,
        key="alpha_required", is_required=True, scope="company", scope_company_id=alpha.id,
    )
    _publish(client, auth, owner, form_id)

    version = db.execute(
        select(FormVersion)
        .where(FormVersion.form_id == form_id)
        .order_by(FormVersion.version_number.desc())
    ).scalars().first()

    base = {"amount": "100", "purpose": "test"}

    # Beta does not see the field, so a submission without it is complete.
    beta_values = submission_service.validate_values(
        db, version, base, partial=False, company=beta
    )
    assert "alpha_required" not in beta_values

    # Alpha does see it, so the same values are incomplete.
    with pytest.raises(Exception):
        submission_service.validate_values(db, version, base, partial=False, company=alpha)

    # Supplying it for alpha is accepted.
    ok = submission_service.validate_values(
        db, version, {**base, "alpha_required": "ok"}, partial=False, company=alpha
    )
    assert ok["alpha_required"] == "ok"


def test_forging_a_scoped_value_for_the_wrong_company_is_rejected(
    client, scoped_world, auth
):
    owner = scoped_world["owner"]
    alpha_id = scoped_world["alpha"].id
    beta_id = scoped_world["beta"].id
    form_id = scoped_world["form"].id

    _field(
        client, auth, owner, form_id,
        key="alpha_only", scope="company", scope_company_id=alpha_id,
    )
    _publish(client, auth, owner, form_id)

    draft = client.post(
        "/api/v1/form-submissions",
        json={"form_id": form_id, "company_id": beta_id, "title": "b", "values": {}},
        headers=auth(scoped_world["beta_mgr"]),
    ).json()

    forged = client.patch(
        f"/api/v1/form-submissions/{draft['id']}",
        json={"values": {"alpha_only": "sneak"}},
        headers=auth(scoped_world["beta_mgr"]),
    )
    assert forged.status_code == 422, forged.text


def test_scoped_field_isolation_between_companies(client, scoped_world, auth):
    """A company-scoped caller cannot ask for another company's scoped fields."""
    form_id = scoped_world["form"].id
    version_id = _publish(client, auth, scoped_world["owner"], form_id)

    foreign = client.get(
        f"{FORMS}/{form_id}/versions/{version_id}?company_id={scoped_world['gamma'].id}",
        headers=auth(scoped_world["alpha_mgr"]),
    )
    # Not yours and does not exist both return 404.
    assert foreign.status_code == 404, foreign.text
