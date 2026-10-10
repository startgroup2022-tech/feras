# SAFIR Holding — Role & Permission Matrix (current vs specification)

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`, `SAFIR_SPECIFICATION_GAP_MATRIX.md`
**Specification:** `Platform_Executive_Specifications_v1.docx` §4, §6, §22.1, Tables 74/76/79–85
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

Legend: ✅ present · 🟡 partial · ❌ absent · 🔒 blocked by an unresolved decision.

---

## 1. Role comparison

| Spec operational role | Codebase `RoleCode` | Present | Notes |
|---|---|---|---|
| Holding Owner | `holding_owner` | ✅ | Full permission set incl. `is_holding_wide` + `is_superuser`. |
| Business Development Manager | `business_development` | ✅ | Holding-wide; owns lead pipeline + opportunity review. |
| Subsidiary (Company) Manager | `company_manager` (+ `company_owner`, `ceo`) | ✅ | Company-scoped via `user_company_access`. |
| Accountant | `accountant` | ✅ | Holding-wide; `financial_review.*`. |
| Marketing Specialist | `marketing` | ✅ | Holding-wide; CMS draft powers. |
| Designer | `designer` | ✅ | Holding-wide. |
| **External Consultant** | — | ❌ | **No role exists.** All advisor screens (S19) and the advisor data scope (D04) are absent. |

**Extra roles beyond the 7** (Phase-2 administration): `super_admin`, `holding_finance`,
`company_owner`, `ceo`, `finance_manager`, `hr_manager`, `department_manager`, `employee`.
These are additive and do not conflict with the spec; they are **not** a substitute for the
missing external-consultant role.

---

## 2. Permission catalogue (86 codes) — grouped

Source: `backend/rbac/permissions.py`. UI metadata: `backend/rbac/permission_metadata.py`.

| Group | Codes (representative) | Danger-flagged |
|---|---|---|
| Identity / admin | `user.read`, `user.manage`, `user.read_all`, `user.create`, `user.update`, `user.assign_company`, `company.read/manage/create/update/archive`, `company.access.manage`, `audit.read` | deletes/deactivation |
| Group | `group.manage`, `ownership.read/manage`, `department.read/manage` | `group.manage`, `ownership.manage` |
| Roles / permissions | `role.read`, `role.manage`, `permission.read`, `permission.assign` | `role.manage`, `permission.assign` |
| Monthly reports | `monthly_report.read_own/read_all/create/update/submit/delete` | `delete` |
| Financial review | `financial_review.read`, `financial_review.write` | `write` |
| Support | `support_request.read_own/read_all/create/comment/assign/status_change` | `status_change` |
| Dashboard / AI | `dashboard.holding/company`, `ai.holding/company` | — |
| Dynamic forms | `form.read/create/update/publish/archive/submit` | `publish`, `archive` |
| Requirements | `requirement.read/manage` | `manage` |
| Submissions | `form_submission.read_own/read_company/read_all/cancel` | `cancel` |
| Workflows | `workflow.read/create/update/publish/archive` | `publish`, `archive` |
| Approvals | `approval.act`, `approval.read_own/read_all`, `approval.override` | `override` |
| Documents | `document.read/upload/update/archive`, `document.category.manage` | `archive`, `category.manage` |
| Notifications | `notification.read_own`, `notification.manage` | `manage` |
| Analytics | `analytics.holding/company/operations/compliance/export` | `export` |
| Integrations | `integration.read/manage` | `manage` |
| Website leads | `website_lead.read/manage/status_change`, `website_opportunity.review/publish` | `publish` |
| Website CMS | `website.manage`, `website.content.read/write/publish`, `website.media.manage`, `website.settings.manage` | `publish`, `media.manage`, `settings.manage` |

**Spec-aligned gaps in the catalogue:** there are **no** permission codes for holding
accounting, invoices, assets, budgets, campaigns, complaints, advisory sessions, employee
assessment, leadership assessment, owner decisions, opening balances, or financial-item
configuration. Those modules are unbuilt, so the catalogue correctly has no phantom codes
yet — but any new module must add codes here (not branch on role names).

**Spec-sensitive actions lacking explicit codes:** the spec forbids a **bank-transfer**
button, **salary editing by BD**, **auto-login-on-add-employee**, and **payment/legal/ads**
activation. These are absent by construction today; they must remain absent and, where
relevant, be enforced by explicit permission codes when built (e.g. no `bank.transfer`
code should ever be added).

---

## 3. Per-role authority vs spec (authority boundaries)

The specification defines authority *by relation type* (Table 76): direct administrative,
administrative, consultative (no executive authority), service, financial review-only,
leadership (evidence-read → secret result). Mapping:

| Spec authority statement | Current enforcement | Status |
|---|---|---|
| Owner has direct authority over BD + company managers | `is_holding_wide` + full perms | ✅ |
| BD has authority over accountant/marketing/designer | `business_development` perms are broad but not "authority" | 🟡 (no hierarchy model) |
| Advisors = coordination with **no executive authority** | no advisor role | ❌ |
| Manager → central specialist is a direct request + BD notified | support requests notify role; no design flow | 🟡 |
| Manager → accountant is review-only of the form | `financial_review` exists | 🟡 |
| Leadership: evidence read → result secret to owner only | absent | ❌ |
| BD **cannot** edit a subsidiary employee's salary | no employee model → not applicable | ❌ (unbuilt) |
| Adding an employee does **not** auto-create a login | no employee model | ❌ (unbuilt) |
| Holding separation cannot exceed the owner's decision | no termination flow | ❌ (unbuilt) |

---

## 4. Isolation & anti-escalation (verified controls)

| Control | Mechanism | Tests |
|---|---|---|
| Company read confinement | `accessible_company_ids` → SQL scope in `scoped.py` | `test_isolation.py` |
| Out-of-scope id indistinguishable from missing | 404 via repository miss / `require_company_access` | `test_isolation.py` |
| Query params cannot widen scope | scope applied unconditionally, then intersected | `test_isolation.py` |
| Role editing cannot escalate | `role_service._assert_no_escalation` (grant ⊆ actor's perms) | `test_rbac.py` |
| Role grant cannot escalate | `admin_service.assert_can_grant_role` | `test_admin.py`, `test_group_admin.py` |
| Server-side per-request checks | `require_permission` / `require_any_permission` on services | suite-wide |
| Deactivation takes effect immediately | user re-read per request | `test_auth.py` |
| Secret entity never leaks via counters/search | N/A (no secret module yet) | — |

`HOLDING_WIDE_ROLES = {holding_owner, super_admin, holding_finance, accountant,
business_development, marketing, designer}`. Company governance roles are deliberately
**not** holding-wide.

**Risk to track:** when campaigns/complaints/leadership are built, `HOLDING_WIDE_ROLES`
must **not** be used to grant access to confidential entities (complaints → owner only;
leadership → owner only). Access must be mediated by dedicated permission codes and the
scope filter must exclude them from global counters, search, and the public activity log
(spec §17, AC-15, AC-25).

---

## 5. Missing role → required permission codes (forward plan, not implemented)

If/when S19 is built, the following codes and grants would be needed (subject to D04):

- `advisor.session.read_own`, `advisor.session.record`, `advisor.recommendation.create`,
  `advisor.report.monthly.submit`.
- Role `external_consultant`: only the assigned employee's necessary data; **no** financial
  ledger, no other employee, no leadership assessment, no approve/edit of records.

No such codes or grants were added in this audit (read-only).
