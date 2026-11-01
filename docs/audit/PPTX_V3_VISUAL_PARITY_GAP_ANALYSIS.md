# PPTX v3 — Visual & Interface Parity Gap Analysis

Comparison of the running platform against `Platform Interface Design v3.pptx`
(138 slides) and the interface gaps that comparison identified and closed.

Mandate: **the deck wins for interface, navigation, layout and role UX**; the
Word specification still wins for business rules and security controls. This
pass changes presentation only — no business rule, permission or scope check was
altered, and every security control the Word spec names is re-verified below.

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

## Remaining gaps (not closed this pass)

These are recorded rather than silently passed over. None is a regression.

1. **Deck screen families not present in the app.** Slides 134–136 also spec
   filter sets for العملاء/الحملات, المؤشرات/العملات, المستخدمون/النشاط and
   جلسات المستشار — screens that exist only partially. The filter/pager
   machinery added here is generic (`renderPaged(..., spec)`), so wiring each is
   a per-view spec entry once the view exists.
2. **مدير / مسؤول / مراجع filter fields.** The deck names assignee and reviewer
   filters; the list payloads do not carry the assignee's display name, so those
   selects were left out rather than showing a bare id. Closing this needs the
   payload to include the name (a backend change, out of scope for a visual
   pass).
3. **`[بحث]` global overlay vs per-list search.** Both now exist, but the deck's
   single header search box is still the global overlay; the deck's per-list
   search is the new filter field. Whether they should merge is a product call.
4. **Frontend is still the static dashboard.** The deck's write flows (company
   wizard, report submit) remain API-only in the browser — unchanged from the
   Phase 2 known gaps.
5. **Deck is a design reference, not data.** Slides 134–136 carry illustrative
   examples, not production rows; seeded demo data is likewise illustrative.
   Neither is a data-readiness statement.
