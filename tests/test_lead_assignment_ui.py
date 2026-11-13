"""Frontend contract tests for the D04 lead assignment UI.

There is no JS test runner in the image, so these assert the *contract* between
``frontend/app.js`` and the assignment API instead of executing the DOM:

* the assignment block is gated on the permission the endpoint enforces,
* the assignee/company pickers come from the real user/company directories,
* the save action posts to the assignment endpoint and sends only real changes,
* the API's ``{"error": {"message"}}`` envelope is read, so a service's own
  wording reaches the user instead of a bare "Request failed (422)".
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.rbac.permissions import ALL_PERMISSIONS

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
AUTH_JS = (ROOT / "frontend" / "auth.js").read_text(encoding="utf-8")


def _assignment_block() -> str:
    m = re.search(r"function assignmentBlock\(lead, assignments\) \{(.*?)\n  \}", APP_JS, re.S)
    assert m, "assignmentBlock not found"
    return m.group(1)


def test_assignment_block_is_gated_on_the_assign_permission():
    body = _assignment_block()
    assert 'has("website_lead.assign")' in body
    assert "website_lead.assign" in ALL_PERMISSIONS


def test_assignee_picker_uses_the_user_directory_and_company_picker_the_companies():
    body = _assignment_block()
    assert "STATE.users" in body, "assignee options must come from /users"
    assert "STATE.companies" in body, "company options must come from /companies"


def test_modal_loads_assignments_and_users_before_painting():
    opener = re.search(r"function openLead\(id\) \{(.*?)\n  \}", APP_JS, re.S)
    assert opener, "openLead not found"
    body = opener.group(1)
    assert '"/api/v1/leads/" + id + "/assignments"' in body
    assert '"/api/v1/users"' in body
    # assignments are read only where the permission is held; the request must
    # not be issued otherwise (the endpoint would 403).
    assert 'has("website_lead.read")' in body


def test_save_posts_only_real_changes_to_the_assign_endpoint():
    save = re.search(r'var assignBtn = byId\("leadAssignSave"\);(.*?)\n  \}', APP_JS, re.S)
    assert save, "leadAssignSave handler not found"
    body = save.group(1)
    assert '"/api/v1/leads/" + id + "/assign"' in body
    # a value equal to the current one is dropped, so no no-op history row and
    # no spurious manager notification is produced.
    assert "!== lead.assigned_to_id" in body
    assert "!== lead.routed_company_id" in body


def test_empty_picker_options_mean_no_change_not_unassign():
    # The API treats an omitted field as "unchanged" and has no unassign
    # operation, so an empty option must not read as "Unassigned".
    body = _assignment_block()
    assert "بدون تغيير" in body and "No change" in body


def test_assignment_history_is_escaped():
    body = _assignment_block()
    assert "escapeHtml(what)" in body
    assert "escapeHtml(a.reason)" in body
    # fmtDateTime returns dual() markup; escaping it would leak <span> tags.
    assert "escapeHtml(stampText(a.created_at))" in body
    assert "escapeHtml(fmtDateTime(" not in APP_JS


def test_api_error_envelope_is_read_by_the_request_helper():
    body = re.search(r"function messageFor\(status, data\) \{(.*?)\n  \}", AUTH_JS, re.S)
    assert body, "messageFor not found"
    assert "data.error" in body.group(1)
    assert "e.message" in body.group(1)
    assert "e.fields" in body.group(1)


def test_outcome_block_reads_the_closed_out_fields():
    body = re.search(r"function outcomeBlock\(lead\) \{(.*?)\n  \}", APP_JS, re.S)
    assert body, "outcomeBlock not found"
    for field in ("lead.final_result", "lead.internal_notes", "lead.closed_at"):
        assert field in body.group(1), field
    # closed_at is escaped, so it must not carry dual() markup.
    assert "escapeHtml(stampText(lead.closed_at))" in body.group(1)


def test_update_form_exposes_the_outcome_fields_and_posts_changes():
    save = re.search(r'var saveBtn = byId\("leadSave"\);(.*?)\n  \}', APP_JS, re.S)
    assert save, "leadSave handler not found"
    body = save.group(1)
    assert 'byId("leadFinalResult")' in body
    assert 'byId("leadInternalNotes")' in body
    # Only a changed value is sent; the API reads null as "unchanged".
    assert "payloadOut.final_result" in body
    assert "payloadOut.internal_notes" in body
    assert 'id="leadFinalResult"' in APP_JS and 'id="leadInternalNotes"' in APP_JS
