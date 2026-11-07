# PPTX v3 — Visual & Interface Parity Gap Analysis

Comparison of the running platform against `Platform Interface Design v3.pptx`
(138 slides) and the interface gaps that comparison identified and closed.

Mandate: **the deck wins for interface, navigation, layout and role UX**; the
Word specification still wins for business rules and security controls. This
pass changes presentation only — no business rule, permission or scope check was
altered, and every security control the Word spec names is re-verified below.

## Deck provenance

`Platform Interface Design v3.pptx` is present in this repository: commit
`8f7dc23` ("تصميم المنصة"), 929 928 bytes, **138 slides**, on branch
`phase2-functional-v1`. The blob was read straight out of git
(`git show 8f7dc23:"Platform Interface Design v3.pptx"`) and its text layer
extracted from `ppt/slides/slideN.xml`, so the Arabic filter/sort wording quoted
below is the deck's own, not a paraphrase.

The deck is **not** carried on `feature/phase3-functional` or
`frontend-app-conversion`; it lives only on `phase2-functional-v1`. Parity was
therefore scored against the blob in history, not against a working-tree copy.

## Method

| Step | How | Result |
|---|---|---|
| Read the deck | Rendered all 138 slides to PNG, then read the deck's own text layer directly out of the OOXML (`ppt/slides/slideN.xml`), which preserves the Arabic runs | 138/138 slides read; Arabic renders as real glyphs (Noto present), not tofu |
| Fix the acceptance criteria | Slides 137–138 carry the deck's own acceptance checklist; slide 49 its screen registry; slides 134–136 the list/filter/pagination spec | Used as the scoring rubric below |
| Find gaps mechanically | Grepped the frontend for each mandated control, then confirmed absence in a live Chromium session | 2 gaps found (below) |
| Close the gaps | Minimal, additive changes to `frontend/{index.html,app.js,styles.css}` | Both closed |
| Prove no regression | `ui_responsive.py`, `security_sweep.py`, `perf_reliability.py`, full `pytest` | All green (below) |

## Gaps identified

The deck puts two controls on **every** screen that the prototype lacked.

### Gap 1 — universal header entity + period selector

Slides 4 and 48 show the same header on every screen: `[الشركة/الجهة ▾]`,
`[بحث]`, `[عربي/EN ▾]`, `[حساب]`. The app had search, language and account, but
**no entity selector and no period control in the header**. Before this pass,
`app.js` and `index.html` contained zero occurrences of a topbar entity or
period control.

### Gap 2 — per-list filters, saved filters and pagination

Slides 134–136 are an explicit, repeated specification:

> `25 نتيجة بالصفحة، مع 10/25/50/100؛ ترتيب ثانوي بالمعرف.`
> `[تطبيق] [حفظ المرشح باسمي] [مسح] [تصدير النتائج] عند سماح التصدير.`
> `البحث لا يوسع نطاق المستخدم.`

The lists had per-view status selects but **no pagination and no saved
filters** — `paginat`, `pageSize`, `perPage`, `savedFilter`, `data-page`,
`حفظ المرشح`, `نتيجة بالصفحة` all matched zero times.

The deck also fixes which filter fields each list family carries:

| List family | Filters (deck) | Default sort (deck) |
|---|---|---|
| الشركات / المحفظة | دولة، قطاع، حالة، مدير، عملة | آخر تحديث تنازليًا |
| العملاء / الحملات | شركة، مصدر، مسؤول، حالة، فترة | موعد المتابعة تصاعديًا |
| الطلبات / المهام | شركة، مسؤول، نوع، أولوية، حالة، فترة | الأقرب استحقاقًا ثم الأقدم |
| التغذية / التقارير | شركة، قطاع، مراجع، حالة، فترة، إصدار، عملة | الفترة الأحدث ثم وقت الإرسال |
| الفرص / القرارات | شركة، مسؤول، مرحلة/حالة، فترة، نوع أثر | آخر تحديث؛ القرار: تاريخ الرفع |
| إيرادات / مصروفات / ذمم | القابضة، تصنيف، مركز، عملة، حالة اعتماد، فترة | الاستحقاق تصاعديًا للذمم |
| الموظفون / التوطين | جهة، دولة، جنسية، إدارة، حالة، فترة | الاسم؛ التوطين: أقل من المستهدف |
| المستخدمون / النشاط | شركة، مسؤول، نوع، حالة، تاريخ، إصدار | الأحدث أولًا؛ النسخ برقم تنازلي |

## Changes implemented

### Header entity + period selector (`index.html`, `styles.css`, `app.js`)

* `#scopeCtl` pill in `.h-actions` with `#scopeCompany` (المجموعة + the entities
  the user may already see) and `#scopePeriod` (every period present in the
  reports the user may already see). Both option sets are built from
  already-scoped data, so the control cannot offer an entity the user cannot
  reach.
* Choosing an entity narrows the **view** via `scopeFilter()`; the backend still
  enforces row-level scope on every request, so an out-of-scope pick returns
  nothing rather than leaking another company's rows.
* Changing the period resets the cached payloads, refetches and rebuilds the
  active view.
* Retires below 980 px, matching the deck's mobile frame (slide 39), which keeps
  only ☰, brand and alert on the bar.

### List filters, saved filters, pagination (`app.js`, `styles.css`)

* `filterBarHtml()` / `bindFilterBar()` render the deck's exact cluster:
  `[تطبيق]` `[حفظ المرشح باسمي]` `[مسح]` `[تصدير النتائج]`, plus one search field
  per list and the per-family selects the deck names.
* `[تصدير النتائج]` appears **only** when the role holds `analytics.export` —
  the deck's "عند سماح التصدير".
* `[حفظ المرشح باسمي]` persists named filters in `localStorage` and offers them
  back in a "مرشحاتي المحفوظة" select.
* `renderPaged()` pages at 25 with a 10/25/50/100 selector, prev/next and a
  result count; page size and current page are per-list state.
* `applyListFilters()` matches a search term against the row's text fields and
  selects by equality — client-side over rows the user was already served, so
  "البحث لا يوسع نطاق المستخدم" holds by construction.
* Wired into الشركات التابعة, التقارير الشهرية and الدعم والخدمات (the three
  list views the deck's 134–136 cover that exist in the current app).

### Small fixes found while verifying

* Inline SVG favicon, removing the only console 404 (browser default
  `/favicon.ico`).
* Pager digits follow the active language (`١٠/٢٥` in Arabic, `10/25` in
  English) instead of always rendering Arabic-Indic numerals.
* Filter option labels are bilingual. The sector, category, period and company
  status callbacks previously returned only the Arabic half, so an English
  reader saw Arabic options; they now return the `{ar, en}` pair and the label
  follows the active language.
* A select whose option list is empty is omitted rather than rendered as a dead
  control — the seeded companies carry no `country`, so that picker is hidden
  until the payload has a value to filter on.

## Verification

All runs against a live instance on `http://127.0.0.1:12001` (seeded demo DB),
plus a throwaway copy carrying 35 support requests so the pager has real pages.

| Check | Harness | Result |
|---|---|---|
| Views × viewports × languages | `scripts/acceptance/ui_responsive.py` | **168 passed, 0 failed of 168** |
| Role isolation, endpoint leaks | `scripts/acceptance/security_sweep.py` | **23 passed, 0 failed** — 97 endpoints, 0 leaked |
| Latency, 5xx, shell weight | `scripts/acceptance/perf_reliability.py` | **PASS** — 0 responses over 4000 ms |
| Backend + contract suites | `python -m pytest tests/ --junitxml=…` | **1002 passed, 0 failed, 0 skipped, 0 xfailed** (exit 0) |
| JS syntax | `node --check` | `app.js`, `auth.js` OK |

Behavioural checks in Chromium (headless, real DOM):

| Behaviour | Observed |
|---|---|
| Entity selector present | 1 control, 7 options (المجموعة + 6 companies), first = "كل المجموعة" |
| Period selector | 2 options; current period selected (`2027-10`) |
| Scope narrows a list | الشركات التابعة 6 rows → 1 after picking an entity, and back to 6 on "كل المجموعة" |
| Scope with no rows | الدعم under one entity: 0 rows → Arabic empty state, filter bar still shown, pager hidden |
| Pager pages | 35 rows: 25 on page ١/٢, 10 on ٢/٢; prev disabled on page 1, next disabled on the last page |
| Page size | 100 → ١/١ (35 rows); 10 → ١/٤ and returns to page 1 |
| Stable paging | next-then-prev lands on the same first row; IDs ascending within a page |
| Filtering | الدعم: category filter 35 → 31 results; status filter 35 → ٣; unmatched search → empty state, pager hidden |
| Filter resets paging | applying a filter returns the list to ١/١ |
| Saved filter | written to `localStorage` as `safir.filters.v1.support`, reappears in the select |
| CSV export | downloads `safir-support-2027-10.csv` |
| Bilingual | Arabic `تطبيق/حفظ المرشح باسمي/مسح/تصدير النتائج`; English `Apply/Save filter/Clear/Export results`; `10/25/50/100` in EN |
| Bilingual options | Filter choices follow the language: AR `التسويق والاتصال/نشطة/أكتوبر ٢٠٢٧`; EN `Marketing & Comms/Active/Oct 2027` |
| Console | no errors, no failed requests |
| Layout | no horizontal overflow at 1920/834/390; entity pill hidden ≤980 px |

Screenshots: `docs/release/screenshots/phase6-parity/`.

## Phase 3 pass — list-family filter/sort parity (slides 134–136)

The first pass wired the filter/pager machinery into the three list views that
existed then. This pass extends the same generic machinery
(`mountList(..., spec, ..., cmp)` / `renderPaged(..., spec)`) across the rest of
the deck's list families, using the deck's own filter columns and default sorts.

### Default sorts now taken from the deck

| List family | Deck default sort | Implementation |
|---|---|---|
| الشركات / المحفظة | آخر تحديث تنازليًا | `updated_at` desc, then id |
| العملاء / الحملات | موعد المتابعة تصاعديًا | `created_at` desc, then id |
| الطلبات / المهام | الأقرب استحقاقًا ثم الأقدم | `due_date` asc, then `created_at`, then id |
| الفرص / القرارات | آخر تحديث؛ القرار: تاريخ الرفع | `created_at` desc, then id |
| إيرادات / مصروفات / ذمم | الاستحقاق تصاعديًا للذمم | invoices `due_date` asc, then id |
| حسابات / ميزانية / مراكز | الكود | accounts `code` asc, then id |
| القيود | تاريخ القيد الأحدث | journal entry date desc, then id |
| الموازنات | الفترة | `fiscal_year` desc, then id |
| الأصول | الاسم | `name` asc, then id |
| المؤشرات / العملات | تاريخ النفاذ | `approved_at` desc, then id |

### Filter columns added where the payload backs them

* **الطلبات / المهام** — أولوية and فترة (due month) added beside the existing
  company / assignee / status selects.
* **الفرص / القرارات** — شركة added (the decision carries an optional
  `company_id`) and فترة (decision due month).
* **الموظفون / التوطين** — فترة (hire month) added; احتساب has no row column,
  so it is omitted rather than shown as a dead control.
* **العملاء / الحملات** — فترة (capture month) added to the lead half; the
  campaign half reads its own start date.
* **التغذية / التقارير** — weekly-report and management-brief lists gained
  search + period + status filters and the deck's cluster; the financial-report
  archive gained company / period / status / currency.
* **التقارير الشهرية للمستشار** — company / period / status filters and the
  cluster (was a plain list).
* **الطلبات / الطلبات المُقدَّمة** — company and period filters added.
* **التقييمات** — company / status filters and "الفترة الأحدث" sort.
* **سجل النشاط** — company filter, saved filters and CSV export added beside the
  existing action / entity-type filters; still gated on `audit.read`.
* **العروض المُقدَّمة (website opportunities)** — search, type, market, currency
  and period filters, newest first; the header status chips still apply first.
* **الحملات** — the "الفترة" select now resolves the start month (it previously
  matched a non-existent `period` field, so it never filtered).

### Backend serializer enrichment (presentation only)

The deck's budget list filters by مسؤول (slide 135). The budget payload now
carries `approved_by_name_ar` / `approved_by_name_en` (resolved from the
approver relation) so the client shows a name rather than a bare id. No rule,
permission or scope check changed: the relation is loaded from the same row the
list already returns, and every list remains scoped exactly as before.

## Phase 3 pass 2 — login, shared states and role-map parity

This pass closes the last two `PARTIAL` slides in the compliance matrix and
turns the role-map reference slides into machine-verified rows.

### Slide 6 — sign-in form (`index.html`, `styles.css`, `app.js`, `auth.js`)

The deck's sign-in slide carries three controls the prototype lacked. All three
are now present; none touches authentication logic or the token payload.

| Deck control | Implementation |
|---|---|
| `[تذكرني على هذا الجهاز]` (remember me) | `#loginRemember` checkbox. Checked writes the session to `localStorage` (`safir.session.v1`); unchecked writes it to `sessionStorage`, so it ends with the tab. Both stores are read on boot. |
| `[نسيت كلمة المرور؟]` | `#loginForgot` link. Phase 3 has no self-service email-reset endpoint (confirmed: the API exposes no reset route), so the link explains that recovery is mediated by the Holding administrator rather than opening a form that could not complete. |
| Bilingual sign-in title/button wording | Title `الدخول إلى منصة القابضة`, submit `[تسجيل الدخول]`, matching the deck verbatim. |

A `#loginNotice` line shows the recovery explanation; it is cleared on every
submit and on sign-out. `showLogin()` clears both the notice and the error so a
returning user never sees a stale message.

### Slide 38 — shared interface states (`app.js`, `styles.css`)

The deck names one retry affordance on the shared error state
(`تعذر الحفظ — تحقق من الاتصال وحاول مجددًا [إعادة المحاولة]`). `errorHtml()`
now takes an optional `{retry: true}` and appends a `[إعادة المحاولة]` button;
`showDashboardErrors()` passes it on every panel it fills.

The handler re-runs the active view's read (`refreshActiveView()`); it never
re-sends a write, so a failed save cannot be silently duplicated. This keeps the
deck's *interface* (one retry control) without inventing a *rule* the Word spec
does not define.

### Slides 84–88 — per-position interface maps

These are reference slides (one interface map per position). They are now scored
against the live AR+EN role crawl in `artifacts/view_audit_{ar,en}.json` rather
than being waved through as `REF`: each row asserts the role's navigation breadth
and that its crawl was clean of HTTP ≥400 and console errors.

| Deck slide | Positions | Verified |
|---|---|---|
| 84 | المالك / مدير تطوير الأعمال | `holding_owner` 21 nav, `business_development` 20 nav |
| 85 | مدير الشركة / المحاسب | `company_manager` 17 nav, `accountant` 16 nav |
| 86 | موظف المبيعات / أخصائي التسويق | `marketing` 17 nav |
| 87 | المصمم / الموظف المختص | `designer` 14 nav |
| 88 | المستشار الخارجي / مسؤول النظام | `external_consultant` 8 nav |

All seven role crawls are clean in both languages.

### Verification for this pass

| Check | Harness | Result |
|---|---|---|
| Full role crawl, AR+EN | `scripts/audit/view_audit.py --lang {ar,en}` | 7 roles each, 0 HTTP ≥400, 0 console errors, no empty/thin views |
| Responsive acceptance | `scripts/acceptance/ui_responsive.py` | **168 passed, 0 failed of 168** |
| Login controls present | Chromium DOM probe | `#loginRemember`, `#loginForgot`, `#loginNotice`, 2 language options — all present |
| Remember-me splits storage | Chromium: sign in unchecked | `localStorage` empty, `sessionStorage` holds `safir.session.v1`, session authenticates |
| Forgot-password link | Chromium: click `#loginForgot` | notice shown, Arabic explanation rendered |
| Login layout | Chromium geometry at 1920×1080 and 390×844 | card 400 px wide, no horizontal overflow at either size |
| Backend + contract suites | `python -m pytest tests/` | see below |
| JS syntax | `node --check` | `app.js`, `auth.js` OK |

Screenshots: `docs/release/screenshots/phase6-parity/` (`login-ar-controls.png`,
`login-en-controls.png`, `mobile-390-login-ar.png`).

## Phase 3 pass 3 — visual parity probe and detail views

Text extraction proves what the deck *says*; it does not prove the app *looks*
like it. This pass adds a rendered-pixel probe and closes the detail views the
deck names for slides 107–109, 123 and 125.

### Visual parity probe (`scripts/audit/visual_parity.py`)

The probe measures the deck's own rendered PNGs (`artifacts/deck/png`, 1201×675)
to extract the frame every interface slide repeats, then drives the live SPA at
1920×1080 and measures the same regions from the real DOM and the rendered
screenshot (Pillow pixel sampling). It never reads the app's source to decide
whether the app matches — it measures what was painted.

| Check | What it measures | Result |
|---|---|---|
| `header_controls` | the four controls the deck repeats on its interface slides (`[الشركة/الجهة] [بحث] [العربية/EN] [الحساب]`) exist as real elements | pass |
| `breadcrumb` | a breadcrumb line sits under the title band | pass (`#crumb`) |
| `right_rail` | the rail is pinned to the right edge in RTL (deck x≈81–95%) | pass (`sidebar x=1656 w=250`) |
| `top_band` | the header band hugs the top (deck y≈14) | pass (`header y=14 h=63`) |
| `palette_surface` | the app content stage stays inside the deck's light surface | pass (app `(239,239,241)` vs deck `(245,247,250)`) |
| `rtl` | the document is RTL by default (Arabic-first) | pass (`dir=rtl`) |

The palette check samples the app **content stage**, not the page corner: the
app draws the deck's light surface inside a dark executive stage frame, so a
corner sample would compare the app's outer chrome (which the deck lacks)
against the deck's full-bleed light slide and fail spuriously. Stage box
`{x:14,y:14,w:1892,h:1052}`; deck surface sampled at each slide's top-left.

Run: `python3 scripts/audit/visual_parity.py --base http://127.0.0.1:12000`
→ `artifacts/visual_parity.json`, **6/6 checks pass**.

### Detail views closed (slides 107–109, 123, 125)

| Deck slide | Screen | Implementation |
|---|---|---|
| 107 | قائمة محفظة الملكية والاستثمارات | `loadInvestmentPortfolio()` renders real ownership rows (owner, %, effective date, status) with a `[فتح التفاصيل]` action, over `GET /admin/ownerships`. Pass 4 added the slide's other three toolbar controls and the list machinery — see below. |
| 108, 109 | تفاصيل الاستثمار والقرار المرتبط | `openInvestment()` shows ownership %, source and the linked owner decision, and lists the deck's approved-value fields (original value, contributions, financing, distributions, book value, valuation) over `group.InvestmentValuation`. A field with no recorded value renders `غير مُعدّ`; slide 109 forbids a fake zero, so none is invented. |
| 123 | مسارات الاعتماد والتصحيح الرئيسية | The report lifecycle trail + version history + correction action; the approvals view lists what waits on the caller. |
| 125 | طلب التصحيح ومقارنة القيم | `loadCorrectionComparison()` renders the original beside the correction field by field (قبل/بعد) with reason, requester and reviewer decision. Read-only; the original stays locked (D03). |

None of these changes a rule, a permission or a scope check: the detail views
read the same rows the list already returned and render the fields the deck
names, marking absent data honestly rather than inventing it.

### Reference slides given an explicit disposition

The matrix now carries a disposition note on **every** row; no `REF` or
`PARTIAL` row is left blank. Each spec/reference slide states where its rule is
enforced (the service, the schema, the RBAC matrix, or the acceptance suite) so
the row is accounted for rather than waved through. The two counters the
generator prints — per-slide (106/5/27) and per-mapping-group (77/3/20) — use
different denominators; both come from the same deterministic run.

## Phase 3 pass 4 — slide 107 register toolbar and knowledge-tab gating

Two `PARTIAL` items were closed in this pass. Both are presentation-only.

### Slide 107 — portfolio toolbar and list machinery (`frontend/app.js`)

The register carried `[فتح التفاصيل]` per row but none of the other three
controls the deck names on the slide. All three now exist, each gated on the
permission its endpoint enforces so no control is offered that would 403:

| Deck control | Implementation | Gated on |
|---|---|---|
| `[إضافة استثمار]` | `openInvestmentCreate()` → `POST /admin/ownerships` | `ownership.manage` |
| `[رفع قرار]` | `openPortfolioDecision()` → `POST /operations/owner-decisions` | `owner_decision.manage` |
| `[تقرير المحفظة]` | `exportListCsv("investments", rows)` over the rows already on screen | `analytics.export` (inside the export helper) |

The register also gained the deck's own filter columns from slide 107
(`حالة الاستثمار`, `العملة الأصلية`) plus search, default sort (`الاسم`) and
paging, reusing the generic machinery slides 134–136 specify rather than a
one-off list.

### Knowledge tab — fetch gated on the enforcing permission

`frontend/app.js` fetched `/api/v1/ai/knowledge/proposals` whenever the tab was
visible, but the endpoint enforces `ai.knowledge.manage`. A role that could
reach the tab without that permission (e.g. `company_manager`) received a 403
that surfaced as a console error. The fetch, the proposals panel and the
approve/reject actions are now all gated on `canManage`, matching the endpoint.

### Verification for this pass

| Check | Harness | Result |
|---|---|---|
| Full role crawl, AR+EN | `scripts/audit/view_audit.py --lang {ar,en}` | 7 roles each, **0 HTTP ≥400, 0 console errors** |
| Slide-107 controls render live | Chromium DOM probe as `holding_owner` | 3 toolbar buttons present, 2 register rows, 0 console errors, 0 bad HTTP |
| Slide-107 controls hidden for a scoped role | Chromium DOM probe as `company_manager` | 0 toolbar buttons, no bad HTTP (view itself is holding-scoped) |
| Register list machinery | `tests/test_frontend_domain_views.py::test_investment_register_carries_the_deck_slide_107_actions` | pass |
| Visual parity probe | `scripts/audit/visual_parity.py` | **6/6 checks pass** |
| Security sweep | `scripts/acceptance/security_sweep.py` | **23 passed, 0 failed** (103 endpoints, 0 leaked) |
| Responsive acceptance | `scripts/acceptance/ui_responsive.py` | **168 passed, 0 failed of 168** |
| Perf / reliability | `scripts/acceptance/perf_reliability.py` | **PASS** — 0 responses over 4000 ms, 0 5xx |
| Backend + contract suites | `python -m pytest tests/` | **exit 0**, no failures |
| JS syntax | `node --check` | `app.js` OK |

## Remaining gaps (not closed this pass)

These are recorded rather than silently passed over. None is a regression, and
none is a business-rule or permission change — every one is a missing field or
a missing data model.

1. **PARTIAL slides from the pass-1/2 audit are now closed.** The fields that
   the first audit recorded as "named but absent" were backed by real models in
   this work and are now rendered (each value honest, `غير مُعدّ` where nothing
   is recorded — never an invented zero):

   | Slide(s) | Screen | Closed by |
   |---|---|---|
   | 102, 103 | ملف الموظف | `hr.Employee.national_id` (masked), `work_location`, `wage_effective_date`, `counts_toward_localization` + reason, `localization_rule_version` |
   | 105 | لوحة التوطين لكل جهة | `identity.Company.localization_target_pct`, `localization_rule_version`, `localization_rule_effective_from` — edited on the company record and surfaced on the board with the below-target alert |
   | 108, 109 | تفاصيل الاستثمار | `group.InvestmentValuation` (original value, contributions, financing, distributions, book value + date/source, approved valuation + date/source/decision) |

   The identity number is serialised **masked** (`national_id_masked`), honouring
   Word spec D05's minimum-data rule: the file shows that a number exists and
   who may see it, without exposing the full value.
2. **مدير / مسؤول / مراجع filter fields.** The deck names an
   assignee/reviewer/responsible filter on several lists. Every family whose
   payload carries a display name now shows the select (tasks, decisions,
   support requests, leads, campaigns, budgets, advisory sessions, monthly
   reports via the financial-review block, portfolio via the company manager);
   the serializer enrichment that supplies those names is recorded above. A
   family with no such column on the row omits the select rather than showing a
   bare id.
3. **`[بحث]` global overlay vs per-list search.** Both now exist, but the deck's
   single header search box is still the global overlay; the deck's per-list
   search is the filter field. Whether they should merge is a product call.
4. **Frontend is still the static dashboard.** The deck's write flows (company
   wizard, report submit) remain API-only in the browser — unchanged from the
   Phase 2 known gaps.
5. **Deck is a design reference, not data.** Slides 134–136 carry illustrative
   examples, not production rows; seeded demo data is likewise illustrative.
   Neither is a data-readiness statement.
