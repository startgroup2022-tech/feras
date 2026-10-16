# SAFIR Holding — i18n / RTL / UX Audit

**Companion to:** `SAFIR_CURRENT_SYSTEM_AUDIT.md`
**Specification:** `Platform_Executive_Specifications_v1.docx` §5 (two languages / RTL / LTR), §19, T01, T18
**Commit audited:** `cebde883fd5d1061e20fe70d756fbc61e6047633`
**Date:** 2026-10-04

Legend: ✅ present · 🟡 partial · ❌ absent.

---

## 1. Internationalisation

| Requirement | Evidence | Status |
|---|---|---|
| Arabic + English system strings | `dual()` in `frontend/app.js`; bilingual `ROLE_DEFINITIONS` in `rbac/permissions.py`; `description_ar`/`description_en` on `Role` | ✅ |
| Language switch changes text without reload | `setLang` re-renders current view; `html.lang-ar` / `html.lang-en` classes | ✅ |
| Language switch changes direction | `document.documentElement.dir = "rtl" \| "ltr"`; server-rendered public pages set `dir` | ✅ |
| Switch preserves user input / entered text | app re-renders from `STATE` without discarding forms where feasible | ✅ (T01 “entered text does not change”) |
| Backend messages localised | API returns structured error codes; UI maps to bilingual text | 🟡 (some English-only internal errors) |
| Public website bilingual content | Phase 11 CMS stores AR/EN per page/section/slide/service; `test_website_pages.py` | ✅ |
| RTL number/phone/email direction | `bdi`/`unicode-bidi` handling in `styles.css`; money formatted per locale | ✅ |
| No clipped buttons at RTL/mobile | responsive + RTL rules; asserted for public site | 🟡 (internal admin largely covered; a full T01 screenshot matrix is manual) |

---

## 2. Roles & Permissions UX (the brief’s focus)

| Feature | Evidence | Status |
|---|---|---|
| Bilingual role names + descriptions | `Role.name_ar/name_en`, `description/_ar`; `RoleOut`; migration `c4a9e1f2b3d7` | ✅ |
| Permission catalogue with clear names | `ALL_PERMISSIONS` human strings; `permission_metadata` grouping | ✅ |
| Permission descriptions | `permission_metadata` + `Permission.description` | ✅ |
| Categories / groups | `permission_metadata` groups codes | ✅ |
| Search / filter permissions | Roles view (`renderAdminRoles`) + `renderPermGroups` | ✅ |
| Grouped permissions | same | ✅ |
| Select-all per category | same | ✅ |
| Counters | same | ✅ |
| Sensitive-action indicators | `danger` flags in `permission_metadata` | ✅ |
| Correct RTL/LTR in the editor | `[dir="rtl"]` rules | ✅ |
| Dynamic admin UI switches AR/EN correctly | `setLang` + `dual()` in roles/perm views | ✅ |
| Custom role support | `role_service.create_role`, `/admin/roles` | ✅ |
| Escalation guard limits grants | `_assert_no_escalation` | ✅ |
| Custom role cannot reach leadership (AC-25) | leadership module absent; **no deny-list** | 🟡/❌ |

**Verdict:** the Roles & Permissions UX/i18n work requested previously **exists and is
bilingual, grouped, searchable, counted and danger-flagged**. It is not rebuilt in this
audit. The only residual items relate to the still-missing leadership module and
notification-preferences UI.

---

## 3. Responsive / mobile-first

| Requirement | Evidence | Status |
|---|---|---|
| Mobile-first layout (internal app) | `styles.css` media queries, collapsible nav | ✅ |
| Public site mobile-first | `website/assets/styles.css`; `test_website_pages.py` | ✅ |
| Tables scroll / reflow on small screens | responsive table rules | ✅ |
| Touch targets / nav drawer | mobile header + drawer | ✅ |
| Desktop layout unchanged (approved) | no regressions; desktop rules retained | ✅ |

---

## 4. Accessibility & consistency notes

- ✅ Keyboard activation on nav items (`keydown` Enter/Space) and focus handling.
- ✅ Permission-gated nav hides sections a user cannot use, and `navTo` toasts a denial.
- 🟡 Consider `aria-live` on the toast region and `aria-current` on the active nav item.
- 🟡 Some confirm dialogs use native `confirm`; a styled bilingual modal would be more
  consistent with the rest of the admin UI.
- 🟡 Language switch should also update `<title>` and any static page header on the
  internal app (currently view-local).

These are cosmetic/consistency recommendations, not functional defects.
