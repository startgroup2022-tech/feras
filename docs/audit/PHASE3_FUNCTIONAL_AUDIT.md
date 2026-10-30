# Phase 3 — Functional View Audit

**Scope:** all 21 platform views across all 7 specification roles.
**Method:** headless Chromium drives the real SPA against the running backend,
signs in as each role, walks every navigation entry, opens every tab (including
the two-level accounting section → sub-tab nesting), and records HTTP status,
console errors and rendered text for each panel.
**Harness:** `scripts/audit/view_audit.py`
**Raw output:** `artifacts/view_audit.json` (generated; not committed),
screenshots in `artifacts/shots/`.

```
python3 scripts/audit/view_audit.py                       # ar, 1920x1080
python3 scripts/audit/view_audit.py --lang en             # en, LTR
python3 scripts/audit/view_audit.py --viewport 390x844    # mobile
python3 scripts/audit/view_audit.py --roles accountant    # one role
```

## Result

| run | language | viewport | roles | tab crawls | HTTP ≥400 | console errors |
|---|---|---|---|---|---|---|
| 1 | ar (RTL) | 1920×1080 | 7 | 250 | 0 | 0 |
| 2 | en (LTR) | 1920×1080 | 7 | 250 | 0 | 0 |
| 3 | ar (RTL) | 390×844 | 3 | — | 0 | 0 |

Navigation breadth per role matches the RBAC matrix exactly:

| role | nav entries |
|---|---|
| `holding_owner` | 21 |
| `business_development` | 20 |
| `company_manager` | 17 |
| `marketing` | 17 |
| `accountant` | 16 |
| `designer` | 14 |
| `external_consultant` | 8 |

## Per-view matrix

`OK` renders content · `E` renders an honest empty state · `·` not in that
role's navigation.

| view | owner | BD | mgr | acct | mktg | dsgn | consult |
|---|---|---|---|---|---|---|---|
| dashboard | OK | OK | OK | OK | OK | OK | OK |
| leads | OK | OK | · | · | OK | · | · |
| requests | OK | OK | OK | OK | OK | OK | · |
| feedback | OK | OK | OK | OK | OK | OK | OK |
| projects | OK | OK | · | · | · | · | · |
| decisions | OK | OK | OK | · | · | · | · |
| subsidiaries | OK | OK | OK | OK | OK | OK | OK |
| reports | OK | OK | OK | OK | OK | OK | · |
| financial | OK | OK | OK | OK | · | · | · |
| investments | OK | OK | · | OK | OK | OK | · |
| support | OK | OK | OK | OK | OK | OK | · |
| approvals | OK | OK | OK | OK | OK | OK | · |
| documents | OK | OK | OK | OK | OK | OK | · |
| bi | OK | OK | OK | OK | OK | OK | OK |
| analytics | OK | OK | OK | OK | OK | OK | · |
| inbox | OK | OK | OK | OK | OK | OK | OK |
| employees | OK | OK | OK | · | · | · | OK |
| operations | OK | OK | OK | OK | OK | OK | OK |
| accounting | OK | OK | OK | OK | OK | · | · |
| confidential | OK | · | · | · | OK | · | · |
| admin | OK | OK | OK | OK | OK | OK | OK |

## Defects found and fixed

### B1 — accounting › subsidiary finance 403 for marketing

`marketing` reaches the section through `dashboard.holding` (the group
summary), but the report archive it embeds needs `financial_report.read`.
The fetch 403'd and the panel rendered as "no data".

**Fix:** `renderCompanyFinanceComparison` now gates the archive call on
`financial_report.read` and explains the omission instead of showing an empty
table. (`frontend/app.js`)

### B2 — accounting › tasks 403 for business_development

`business_development` reaches the tab through `support_request.read_all` (the
tab lists support-derived tasks) but holds no `task.read_*`, so
`/operations/tasks` 403'd.

**Fix:** `renderTasksRegistry` only fetches when `has("task.read_own") ||
has("task.read_all")`, and otherwise renders an honest "no tasks" panel.
(`frontend/app.js`)

### B4 — silent error swallowing

52 call sites read `get(path).catch(function () { return []; })`. Any 5xx or
dropped connection therefore rendered as a legitimately empty section — the
same symptom as an authorisation failure, with nothing in the UI to tell them
apart.

**Fix:** new `softGet(path)` helper stays quiet only for the expected
`401`/`403`/`404` (the caller simply has no access to that slice) and raises a
toast for anything else. All 52 call sites migrated; the pattern no longer
appears in `app.js`. (`frontend/app.js`)

### B3 — missing `external_consultant` demo user

The role existed in the RBAC catalogue with no way to sign in, so its eight
grant-scoped views could not be exercised.

**Fix:** `scripts/seed_demo.py` now seeds `consultant@demo.safir.local`; the
demo reset path covers it through the demo-domain match. Seed now creates
9 demo users covering all 7 specification roles.

## Remaining empty panels — demo-data gaps, not bugs

Four panels render an honest empty state because the demo seed has no rows for
them. Each was confirmed to render fully for a role that holds the read
permission:

| panel | rows in seed | rendered for owner |
|---|---|---|
| `accounting` › assets | 0 | yes — full register |
| `operations` › tasks | 1 | yes — full registry |
| `accountant` / `designer` / `marketing` › tasks | (scoped) | yes (owner) |

The single seeded task is unassigned and belongs to company 1, so
non-owner roles correctly see nothing. No code change is warranted; adding
demo rows is a seed-content decision.

## Cross-checked false alarms

Two endpoints returned `422` during earlier manual probing. Both were faults
in the probe payload, not the platform: the frontend sends
`{company_id, title, category, description, dimensions, platform,
reference_link}` for support requests and a multipart body for document
upload, matching the routers exactly. A corrected request returns `201`.

## Regression coverage added

* `tests/test_frontend_domain_views.py` — asserts both panels keep their
  permission gate, that `softGet` surfaces non-401/403/404 failures, that no
  silent-catch pattern remains, and (data-driven over `ROLE_PERMISSIONS`) that
  any role able to open a gated section either holds the endpoint permission
  or the renderer guards the fetch.
* `tests/test_seed_demo.py` — asserts a demo user exists for each of the seven
  specification roles.

Full suite: **994 passed**.
