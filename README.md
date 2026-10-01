# سفير القابضة ٢٠٢٧ — Safir Holding 2027

Executive Holding Management & Business Intelligence platform — a high-fidelity UI concept.

Arabic-first, RTL, built as a fixed **1920×1080 (16:9)** executive board that scales to any viewport.

## Concept

The interface tells one story end to end:

> subsidiary monthly data → Holding visibility → AI business intelligence → management support & decisions

It is deliberately **not** an ERP. There are no HR, inventory, payroll, procurement, project
management, contracts, meetings, OKR or approval-matrix modules — only the lightweight executive
layer a holding company needs.

## Design language

| Token | Value | Use |
|---|---|---|
| Deep navy | `#060E1F` → `#1B3D7A` | header, AI orb, hub, primary actions |
| Gold | `#8A6820` → `#F7EFDC` | accents, AI identity, dividers, focus |
| Soft gray | `#F4F6FA` / `#EDF1F7` | canvas, secondary surfaces |
| White | `#FFFFFF` | cards, content surfaces |
| Status | green / amber / red | health, alerts, deltas |

Typography pairs **Alexandria** (display, headings, numerals) with **IBM Plex Sans Arabic**
(body) — both fully support Arabic, with tabular numerals for financial figures.

## Layout

```
┌────────────────────────── header: brand · nav · notifications · profile · عربي/EN ──────────────────────────┐
├──────────────────────────────── page title · live chip · export action ─────────────────────────────────────┤
├───────── 6 executive KPI cards ──────────────────────────────────────────────────────────────────────────────┤
│                     │                                              │                                       │
│  Holding AI         │  Monthly Company Reports (6 subsidiary cards) │  Group Structure (hub → subsidiaries) │
│  · NL ask box       │  · status · revenue · expenses · net          │  · central holding entity             │
│  · suggested prompts│  · growth vs last month · last update         │  · 6 connected company nodes          │
│  · AI answer        │  · "View Report"                              ├───────────────────────────────────────┤
│  · business analysis│                                              │  Companies Overview                   │
│  · investment opp.  ├──────────────────────────────────────────────┤  · health pills                       │
│  · important alerts │  Support Requests                            │  · mini sparklines                    │
│  · projection       │  company · type · date · dept · status        │  · revenue + growth                   │
└─────────────────────┴──────────────────────────────────────────────┴───────────────────────────────────────┘
```

## Features

- **Holding AI** — natural-language question box with the example insight
  «ملخص أداء المجموعة هذا الشهر», suggested prompts, an AI-generated executive summary,
  business performance analysis, investment opportunity detection, important alerts and a
  next-month projection.
- **Executive KPIs** — عدد الشركات · إجمالي الإيرادات · صافي النتائج ·
  الشركات التي أرسلت التقرير الشهري · الشركات التي تحتاج متابعة · الطلبات المفتوحة.
- **Monthly Company Reports** — six subsidiary cards with report status, revenue, expenses,
  net result, month-over-month change, last update and a *View Report* action.
- **Companies Overview** — health/status indicators with small trend charts.
- **Support Requests** — business development, marketing, design and accounting/financial
  support requests with company, type, date, responsible department and status.
- **Group Structure** — the Holding rendered as the central entity with subsidiary cards
  connected beneath it.

## Language switching

The `عربي / EN` switch in the header toggles language **and** direction in place
(`dir="rtl"` ↔ `dir="ltr"`), swapping every label, including the AI input placeholder.
Both directions are verified to fit the 16:9 canvas without clipping or overflow.

## Files

| File | Purpose |
|---|---|
| `index.html` | Dashboard markup, bilingual content, language + scaling behaviour |
| `styles.css` | Design system, 16:9 stage grid, all components |
| `preview-16x9.png` | 1920×1080 presentation screenshot |
| `preview-16x9@2x.png` | 3840×2160 high-resolution screenshot |

## Running

Open `index.html` directly, or serve the folder:

```bash
python3 -m http.server 8000
```

Append `?export=1` to render the board 1:1 (no viewport scaling) — used for the
presentation screenshots.
