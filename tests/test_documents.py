"""Document management tests (Phase 3).

Focus: scope enforcement on list/get/download (IDOR), upload validation
(forbidden extensions, size), metadata editing, and archive-not-delete.

Documents are company-owned; uploading follows the platform's standard rule
(``require_company_access(write=True)``). GAMMA is a company with a single
Company Owner used here so the extra builder account does not perturb the
approval workflow's company-manager resolution in other tests.
"""

from __future__ import annotations

import io

import pytest


def _upload(client, auth, user, company_id, filename="doc.pdf", content_type="application/pdf", **form):
    data = {"company_id": str(company_id), "title_ar": "مستند", "title_en": "Doc"}
    data.update(form)
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 hello"), content_type)},
        data=data,
        headers=auth(user),
    )


def test_company_owner_can_upload_and_list(client, auth, ops_world, db):
    gamma = ops_world["gamma"]
    response = _upload(client, auth, ops_world["gamma_owner"], gamma.id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["company_id"] == gamma.id
    # The storage key / path must never be exposed.
    assert "storage_key" not in body
    assert "original_filename" in body

    listing = client.get("/api/v1/documents", headers=auth(ops_world["gamma_owner"])).json()
    assert listing["total"] == 1


def test_owner_sees_all_companies_documents(client, auth, ops_world, db):
    _upload(client, auth, ops_world["gamma_owner"], ops_world["gamma"].id)
    _upload(client, auth, ops_world["alpha_mgr"], ops_world["alpha"].id)
    listing = client.get("/api/v1/documents", headers=auth(ops_world["owner"])).json()
    assert listing["total"] == 2


def test_manager_sees_only_own_company_documents(client, auth, ops_world, db):
    _upload(client, auth, ops_world["gamma_owner"], ops_world["gamma"].id)
    _upload(client, auth, ops_world["alpha_mgr"], ops_world["alpha"].id)

    listing = client.get("/api/v1/documents", headers=auth(ops_world["gamma_owner"])).json()
    assert listing["total"] == 1
    assert listing["items"][0]["company_id"] == ops_world["gamma"].id


def test_manager_cannot_download_other_company_document(client, auth, ops_world, db):
    alpha_doc = _upload(client, auth, ops_world["alpha_mgr"], ops_world["alpha"].id).json()
    response = client.get(
        f"/api/v1/documents/{alpha_doc['id']}/download",
        headers=auth(ops_world["gamma_owner"]),
    )
    # 404, not 403 -- existence is not leaked.
    assert response.status_code == 404


def test_manager_can_download_own_company_document(client, auth, ops_world, db):
    doc = _upload(client, auth, ops_world["gamma_owner"], ops_world["gamma"].id).json()
    response = client.get(
        f"/api/v1/documents/{doc['id']}/download", headers=auth(ops_world["gamma_owner"])
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_upload_rejects_forbidden_extension(client, auth, ops_world, db):
    response = _upload(
        client, auth, ops_world["gamma_owner"], ops_world["gamma"].id,
        filename="payload.svg", content_type="image/svg+xml",
    )
    assert response.status_code == 422


def test_upload_rejects_disallowed_content_type(client, auth, ops_world, db):
    response = _upload(
        client, auth, ops_world["gamma_owner"], ops_world["gamma"].id,
        filename="note.xyz", content_type="application/x-msdownload",
    )
    assert response.status_code == 422


def test_upload_requires_company_write_access(client, auth, ops_world, db):
    response = _upload(client, auth, ops_world["gamma_owner"], ops_world["alpha"].id)
    assert response.status_code in (403, 404)


def test_archive_is_not_delete(client, auth, ops_world, db):
    doc = _upload(client, auth, ops_world["gamma_owner"], ops_world["gamma"].id).json()

    archived = client.post(
        f"/api/v1/documents/{doc['id']}/archive", headers=auth(ops_world["gamma_owner"])
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    # Still retrievable by id (archived, not deleted).
    fetched = client.get(
        f"/api/v1/documents/{doc['id']}", headers=auth(ops_world["gamma_owner"])
    )
    assert fetched.status_code == 200


def test_issue_and_expiry_dates_validated(client, auth, ops_world, db):
    response = _upload(
        client, auth, ops_world["gamma_owner"], ops_world["gamma"].id,
        issue_date="2027-06-01", expiry_date="2027-01-01",
    )
    assert response.status_code == 422


def test_expiry_summary_and_filter(client, auth, ops_world, db):
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=5)).isoformat()
    response = _upload(
        client, auth, ops_world["gamma_owner"], ops_world["gamma"].id, expiry_date=soon
    )
    assert response.status_code == 201, response.text

    summary = client.get(
        "/api/v1/documents/expiry-summary", headers=auth(ops_world["gamma_owner"])
    ).json()
    assert summary["expiring_soon"] == 1

    filtered = client.get(
        "/api/v1/documents?expiry=expiring_soon", headers=auth(ops_world["gamma_owner"])
    ).json()
    assert filtered["total"] == 1


def test_default_categories_are_seeded(db):
    from sqlalchemy import select

    from backend.db.models.documents import DocumentCategory
    from backend.services.document_service import seed_default_categories

    seed_default_categories(db)
    seed_default_categories(db)  # idempotent
    codes = {c.code for c in db.execute(select(DocumentCategory)).scalars()}
    assert {"commercial_registration", "contract", "other"} <= codes


def test_path_traversal_in_storage_key_is_refused():
    from backend.core import document_storage
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError):
        document_storage.resolve_document_path("../../etc/passwd")
