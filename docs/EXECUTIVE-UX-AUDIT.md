# Phase 1 Audit — Executive UX Redesign

**Branch:** `feature/executive-ux-redesign` (off `frontend-app-conversion` @ `91c3c13`)
**Date:** 2026-10-27

This is the Phase 1 (AUDIT) deliverable of the master implementation brief:
what exists today, what is missing, and the specific UI/UX problems to fix.

---

## 1. What exists

### 1.1 Stack

| Layer | Reality |
|---|---|
| Backend | FastAPI, 22 routers, PostgreSQL (SQLite for tests), strict layering: `api/v1/*` → `services/*` → `repositories/scoped.py` → `db/models/*` |
| Frontend | Dependency-free vanilla-JS SPA: `frontend/index.html` (747 lines), `app.js` (11 405 lines), `styles.css` (946 lines), `auth.js` (235 lines). No bundler, no framework. |
| Auth | JWT; RBAC enforced server-side via `Depends(require(Perm.X))` and `require_*_permission(...)` inside services |
| i18n | AR (RTL, default) + EN (LTR) via paired `<span class="ar">` / `<span class="en">` and an `html.lang-en` switch |
| Audit | `services/audit_service.py` writes an `AuditLog` on every mutating action and AI call |

### 1.2 Design tokens (already on-brand)

`styles.css` already defines the palette the brief asks for — this is an asset,
not a gap:

```css
--navy-900:#060E1F … --navy-500:#1B3D7A   /* dark navy */
--gold-500:#C9A54E  --gold-400:#DCBE72    /* gold accents */
--paper:#FFFFFF     --bg:#F4F6FA          /* white / light */
--f-display:'Alexandria'  --f-body:'IBM Plex Sans Arabic'
```

### 1.3 Implemented views (20)

`dashboard · subsidiaries · reports · financial · investments · support ·
requests · approvals · documents · bi · analytics · inbox · leads · employees ·
operations · decisions · projects · accounting · confidential · admin`

Each has: a `[data-view]` section in `index.html`, an entry in `app.js` `VIEWS`
and `NAV_PERM`, and a `render*()` function dispatched by `loadView()`.

### 1.4 Backend endpoints the brief's six sections map onto

| Brief section | Backing API |
|---|---|
| Dashboard | `GET /api/v1/dashboard/holding`, `/dashboard/company/{id}`, `/dashboard/indicator/{k}/sources` |
| Leads | `GET/PATCH /api/v1/leads`, `/leads/stats`, `/leads/{id}/assign`, `/leads/{id}/notes`, `/leads/opportunities` |
| Requests | `/api/v1/support-requests`, `/api/v1/operations/tasks`, `/operations/complaints`, `/operations/management-briefs` |
| Feedback | *(no dedicated API — see §2.1)* |
| Opportunities | `/api/v1/operations/projects` (`record_type=opportunity`), `/leads/opportunities`, `/operations/campaigns` |
| Decisions | `/api/v1/operations/owner-decisions`, `/operations/owner-decisions/{id}/respond`, `/api/v1/submissions/approvals` |
| AI assistant | `POST /api/v1/ai/ask`, `GET /api/v1/ai/insights` |

---

## 2. What is missing / inconsistent

### 2.1 No "Feedback" module exists anywhere

`grep -rni feedback backend/ frontend/` → **zero hits**. The brief's section 8
(Feedback & Reporting) has no table, no endpoint, no view.

**The data already exists under different names**, so this is a *presentation*
gap, not a data-model gap:

| Brief requirement | Existing source |
|---|---|
| submit feedback / updates / reports | `POST /operations/weekly-reports`, `POST /operations/management-briefs`, `POST /monthly-reports` |
| review & classification | `POST /operations/complaints/{id}/decision`, management-brief submit |
| responsible-person assignment | `POST /support-requests/{id}/assign`, task assignee |
| resolution tracking | task lifecycle, complaint decision, brief status |
| reporting history | the list endpoints above |
| management insights | `GET /ai/insights` |

**Decision:** build Feedback as a **read-first aggregating view** over those
existing endpoints. No new tables, no new business rules. This honours the
brief's "reuse existing backend APIs" and "do not modify the database unless
necessary".

### 2.2 Navigation is the core UX problem

The header carries a **20-item horizontal nav bar** that wraps across two rows
on desktop and becomes a horizontal scroller on phones. This is precisely the
"complicated ERP" impression the brief forbids. There is **no sidebar at all**,
yet §2 explicitly requires a *dark navy sidebar on the right*.

### 2.3 Dashboard lacks the named "ماذا يحتاج اهتمامك اليوم؟" section

A priorities list exists (`#prioritiesList`, `hydratePriorities`) but it is
titled `الأولويات` / "Priorities" and renders as a plain row list. The brief
requires a **prominent** section with that exact Arabic title and a **direct
action** on every row.

### 2.4 Other UI/UX problems

| # | Problem | Evidence |
|---|---|---|
| U1 | 20 top-level items — no hierarchy, no grouping | `index.html` `.nav` has 20 `.nav-item` |
| U2 | No right-hand navy sidebar | no sidebar markup in `index.html` |
| U3 | Priority rows have no visible action affordance | `hydratePriorities` emits a bare `.av-row` |
| U4 | Mobile nav is a horizontal scroller | `@media(max-width:560px) .nav{flex-wrap:nowrap;overflow-x:auto}` |
| U5 | No loading/empty/error states on some domain views | `av-empty` used inconsistently |
| U6 | Dashboard is a dense 3-column grid with fixed rows | `.board{grid-template-rows:74px 124px … 272px}` |
| U7 | "Feedback" has no entry point at all | §2.1 |

---

## 3. Permission inconsistencies

The RBAC architecture is **sound and must be preserved** (brief §12). Findings:

- Client-side gating is `NAV_PERM[view]` → `canView()` → `has(perm)`, used
  **only** to hide unusable nav items. The real boundary is server-side.
- Every `data-perm` token in `index.html` is validated against
  `backend.rbac.permissions.ALL_PERMISSIONS` by
  `tests/test_frontend_domain_views.py` — a typo cannot silently hide or expose
  a screen.
- One documented trap: the BI view must gate on `dashboard.*` (what
  `GET /ai/insights` enforces), not `ai.*`, or a custom role sees the view then
  gets a 403. A regression test guards this.

**No permission changes are needed for this work.** The redesign must keep every
existing `data-perm` gate intact.

---

## 4. Constraints discovered (must not break)

| Constraint | Where |
|---|---|
| `tests/test_frontend_domain_views.py` asserts every new view has a gated `<section data-view="…">` and a gated `.nav-item` | static contract test |
| `VIEWS` and `NAV_PERM` must stay in sync with the markup | same test |
| `test_platform_nav_is_responsive_and_never_clipped` asserts `.nav{flex-wrap:wrap}` and `.header-inner{min-height}` with `flex-wrap:wrap` | same test |
| Every domain renderer name and every domain endpoint string must remain in `app.js` | same test |
| `.board` grid areas drive the dashboard layout | `styles.css` |
| `.app-view{position:absolute;inset:0}` — routed views overlay the board | `styles.css` |

**Implication:** the nav can be *restructured* (moved into a sidebar) only if the
contract test's assertions still hold. The test pins CSS rules on `.nav` and
`.header-inner`; those rules must remain present (they can be re-scoped, but the
selectors and properties the test greps for must exist). This is addressed in
Phase 2 by keeping `.nav` / `.header-inner` and adding the sidebar as an
additional container.

---

## 5. Phase 2 scope derived from this audit

1. **Design system** — extend the existing tokens; add sidebar, section, and
   priority-card primitives. Reuse the palette; do not replace it.
2. **Executive shell** — dark navy sidebar on the right (RTL), white content
   area, gold accents, brand block, user block, language switch.
3. **Simplified navigation** — six primary sections; the other 14 views move
   into a grouped "المزيد" (More) region, still permission-gated and reachable.
4. **Executive dashboard** — KPI strip, "ماذا يحتاج اهتمامك اليوم؟" with direct
   actions, charts, recent activity.
5. **Feedback view** — aggregating, read-first, over existing endpoints.

All while keeping the existing tests green and every `data-perm` gate intact.

---

## 6. Phase 2 implementation — delivered

**Status: DONE.** Everything below is on `feature/executive-ux-redesign`, all
967 baseline tests still green plus 11 new contract tests (978 total).

### 6.1 Shell

- The 20-item horizontal top nav is gone from the header; the header keeps a
  breadcrumb (`#crumb`) that `applyDocTitle`/`navTo` keep in sync.
- A dark-navy RTL sidebar (`<aside class="sidebar">`, `.sb-*`) sits on the right
  beside the white board. `.sidebar{order:-1}` places it rightmost in RTL; the
  same rule mirrors it to the left under `dir="ltr"`, verified in the browser.
- Sidebar carries brand, the six primary sections, the "المزيد" group, and the
  user block.

### 6.2 Navigation

- Six primary sections, matching the brief and the earlier prompt's module list:
  `dashboard · leads · requests · feedback · projects · decisions`.
- The other 14 views stay present and reachable inside a collapsible
  `#sbMore` group (`#sbMoreToggle`, `aria-expanded`). `syncMoreGroup(view)`
  auto-opens the group when the active view lives inside it, so a deep link is
  never hidden. Every item keeps its `data-perm`.

### 6.3 Dashboard

- New prominent **"ماذا يحتاج اهتمامك اليوم؟"** panel (`section.attention`,
  `#prioritiesList`, `#attnCount`) replaces the old small priorities card.
- Each row renders an `.attn-card` with a direct action button
  (`.attn-act`), routed via `PRIORITY_ACTION`/`priorityAction()` — a company row
  opens the company, a request row opens Support, and so on.
- The board grid gained an `attention` area (desktop) and stacks first on
  narrow screens.

### 6.4 Feedback view

- New gated `section[data-view="feedback"]` (`#feedbackList`, `#fbSummary`)
  aggregating existing endpoints only: weekly reports, management briefs and
  monthly reports — no new data access.
- Its gate is exactly the union of those endpoints' read permissions
  (`weekly_report.read_own/read_all`, `management_brief.read`,
  `monthly_report.read_own/read_all`) so a role can never see the section and
  then get a 403 from one of its calls.
- Server strings are escaped (`fbRowHtml` → `escapeHtml`).

### 6.5 Responsive

- ≤1180px: the rail becomes a horizontal, wrapping bar above the content;
  `.sidebar .nav-item{width:auto}` stops the rail's full-width items from each
  claiming a row. All 21 nav items remain visible.
- ≤560px: the breadcrumb hides.
- Verified at 1920 / 1024 / 390 px: no horizontal overflow at any width, in
  both AR (RTL) and EN (LTR).

### 6.6 Preserved rules

No `data-perm` token was dropped, `VIEWS`/`NAV_PERM` stay in sync with the
markup, and no backend rule or security control was touched. The Word-spec
conflict register (C1–C9) is unaffected — the redesign is UI-only.

> **PPTX parity still not claimed.** `Platform Interface Design v3.pptx` has
> not reached the environment (see `docs/POWERPOINT-SCREEN-MATRIX.md` on
> `docs/powerpoint-parity-v3`). This phase implements the six-module navigation
> named in the brief; it does **not** assert a visual match to unseen slides.
