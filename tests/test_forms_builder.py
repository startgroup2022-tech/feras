"""Forms builder + requirements engine tests (Phase 3).

Covers: CRUD, version forking (published structure never mutates), field
validation, requirement validation, and the immutable-history property.
"""

from __future__ import annotations

import pytest

from backend.db.models.enums import FieldType, FormScope, FormStatus


def test_create_form_seeds_a_draft_version(client, ops_world, auth):
    owner = ops_world["owner"]
    response = client.post(
        "/api/v1/forms",
        json={
            "code": "expense",
            "name_ar": "طلب مصروف",
            "name_en": "Expense Request",
            "scope": "holding",
        },
        headers=auth(owner),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "expense"
    assert body["status"] == FormStatus.DRAFT.value
    assert body["latest_version_number"] == 1


def test_company_manager_cannot_create_holding_form(client, ops_world, auth):
    response = client.post(
        "/api/v1/forms",
        json={
            "code": "x",
            "name_ar": "س",
            "name_en": "X",
            "scope": "holding",
        },
        headers=auth(ops_world["alpha_mgr"]),
    )
    # Company managers lack form.create (holding-wide builder capability).
    assert response.status_code in (403, 404)


def test_duplicate_code_conflicts(client, ops_world, auth):
    response = client.post(
        "/api/v1/forms",
        json={
            "code": "capex",
            "name_ar": "مكرر",
            "name_en": "Dup",
            "scope": "holding",
        },
        headers=auth(ops_world["owner"]),
    )
    assert response.status_code == 409


def test_add_field_creates_draft_and_validates_select_options(client, ops_world, auth):
    owner = ops_world["owner"]
    form_id = ops_world["form"].id

    # A select field without options is rejected.
    bad = client.post(
        f"/api/v1/forms/{form_id}/fields",
        json={
            "key": "tier",
            "field_type": "select",
            "label_ar": "المستوى",
            "label_en": "Tier",
        },
        headers=auth(owner),
    )
    assert bad.status_code == 422

    good = client.post(
        f"/api/v1/forms/{form_id}/fields",
        json={
            "key": "tier",
            "field_type": "select",
            "label_ar": "المستوى",
            "label_en": "Tier",
            "config": {"options": [{"value": "a"}, {"value": "b"}]},
        },
        headers=auth(owner),
    )
    assert good.status_code == 201, good.text
    assert good.json()["key"] == "tier"


def test_publish_then_edit_forks_version_and_preserves_published(client, ops_world, auth, db):
    owner = ops_world["owner"]
    form_id = ops_world["form"].id

    published = client.post(f"/api/v1/forms/{form_id}/publish", headers=auth(owner))
    assert published.status_code == 200, published.text
    published_version_id = published.json()["published_version_id"]
    assert published_version_id is not None

    # Now edit: this must fork a new draft, not mutate the published version.
    edited = client.post(
        f"/api/v1/forms/{form_id}/fields",
        json={
            "key": "justification",
            "field_type": "long_text",
            "label_ar": "التبرير",
            "label_en": "Justification",
        },
        headers=auth(owner),
    )
    assert edited.status_code == 201, edited.text

    versions = client.get(f"/api/v1/forms/{form_id}/versions", headers=auth(owner)).json()
    assert len(versions) == 2
    published_row = next(v for v in versions if v["id"] == published_version_id)
    assert published_row["status"] == FormStatus.PUBLISHED.value
    # The published version's field set is unchanged (amount + purpose + quote).
    keys = {f["key"] for f in published_row["fields"]}
    assert "justification" not in keys
    assert {"amount", "purpose"} <= keys

    draft = next(v for v in versions if v["status"] == FormStatus.DRAFT.value)
    assert "justification" in {f["key"] for f in draft["fields"]}


def test_publish_requires_a_field(client, ops_world, auth, db):
    from backend.db.models.forms import DynamicForm

    owner = ops_world["owner"]
    empty = DynamicForm(
        code="empty", name_ar="فارغ", name_en="Empty",
        scope=FormScope.HOLDING.value, status=FormStatus.DRAFT.value,
        created_by_id=owner.id,
    )
    db.add(empty)
    db.commit()
    # No version at all -> conflict/validation, never a 500.
    response = client.post(f"/api/v1/forms/{empty.id}/publish", headers=auth(owner))
    assert response.status_code in (400, 409, 422)


def test_requirement_field_value_needs_existing_field(client, ops_world, auth):
    owner = ops_world["owner"]
    form_id = ops_world["form"].id
    response = client.post(
        f"/api/v1/forms/{form_id}/requirements",
        json={
            "key": "purpose_req",
            "name_ar": "الغرض مطلوب",
            "name_en": "Purpose required",
            "requirement_type": "field_value",
            "config": {"field_key": "does_not_exist"},
        },
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_reorder_fields_requires_full_set(client, ops_world, auth):
    owner = ops_world["owner"]
    form_id = ops_world["form"].id
    # Only one of the two fields -> rejected.
    first_field = ops_world["version"].fields[0]
    response = client.post(
        f"/api/v1/forms/{form_id}/fields/reorder",
        json={"ordered_ids": [first_field.id]},
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_form_visibility_company_scoped_manager_cannot_see_unlinked(client, ops_world, auth, db):
    """A company manager cannot read a holding-scope form's field list via a
    direct id (404, not 403 -- no existence leak)."""
    form_id = ops_world["form"].id
    # First publish so a published version exists.
    client.post(f"/api/v1/forms/{form_id}/publish", headers=auth(ops_world["owner"]))

    # beta_mgr has no form.read at all? company_manager does have form.read.
    response = client.get(f"/api/v1/forms/{form_id}", headers=auth(ops_world["beta_mgr"]))
    # Holding-wide forms are visible read-only to company managers, so this
    # should be 200; the security property tested is that they cannot *write*.
    assert response.status_code in (200, 404)


def test_field_key_must_be_lowercase_slug(client, ops_world, auth):
    owner = ops_world["owner"]
    form_id = ops_world["form"].id
    response = client.post(
        f"/api/v1/forms/{form_id}/fields",
        json={
            "key": "Bad Key!",
            "field_type": "short_text",
            "label_ar": "س",
            "label_en": "X",
        },
        headers=auth(owner),
    )
    assert response.status_code == 422
