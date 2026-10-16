# Toronto Ward Facts — Pre-Release Audit Report

**Date:** 2026-10-16  
**Auditor:** Claude (automated), reviewed for Phase 1 only — no edits made  
**Branch:** main @ e27df69  
**Scope:** /docs (25 ward pages, 25 councillor detail pages, index, about, style.css)

---

## Summary Table

| Area | Pass | Issues | Severity |
|------|------|--------|----------|
| A1 · Data pipeline (validate.py) | ✓ | 0 | — |
| A2 · Regression values | 24/25 | 1 test-script bug (not a data error) | Low |
| A3 · 3-ward spot-check (4, 13, 25) | ✓ | 0 | — |
| A4 · Consistency (index/ward/detail/about) | ✓ | 0 | — |
| A5 · By-election wards (15, 20, 25) | ✓ | 0 | — |
| A6 · Source attribution and period labels | ✓ | 0 | — |
| B1 · Loaded words | ✓ | 0 actual issues* | — |
| B2 · Party labels | ✓ | 0 | — |
| B3 · Structure consistency | ✓ | 0 | — |
| B4 · Abbreviations / jargon | ✓ | 1 minor note | Low |
| C1 · WCAG 2.1 AA (axe-core) | FAIL | 3 violation types, all pages | **High** |
| C2 · Internal links | ✓ | 0 | — |
| C3 · Meta tags / OG / canonical | FAIL | Missing on all pages | Medium |
| C4 · Page weight | ✓ | 0 (avg 61 KB, max 80 KB) | — |
| C5 · Readability | ✓ | 0 real prose issues | — |

\* "Margin of victory" is standard election terminology (see B1 detail below).

---

## Issues

---

### ISSUE 1 — color-contrast (WCAG 2.1 AA)

**Severity:** High  
**Pages:** All pages (index, all 25 ward pages, all 25 councillor pages, about.html)  
**What's wrong:** Footer attribution links (#8ebcd8 on #1a4a7a background) have a contrast ratio of **4.48:1**, just below the WCAG AA minimum of 4.5:1 for normal text.  
**Elements:**
- `<a href="https://open.toronto.ca/dataset/elections-voter-statistics/">City of Toronto Open Data</a>`
- `<a href="https://open.toronto.ca/open-data-licence/">Open Government Licence – Toronto</a>`

**Proposed fix:** Lighten the footer link color. Change `#8ebcd8` → `#9ecde4` (calculated contrast ≥4.5:1 against #1a4a7a). Update in `build.py` CSS block for `.page-footer a` (or wherever the footer link colour is defined in style.css).

---

### ISSUE 2 — aria-hidden-focus (WCAG 2.1 AA)

**Severity:** High  
**Pages:** index.html, ward-1.html through ward-25.html (all ward pages)  
**What's wrong:** The map container div (`class="home-hero__map"` / `class="ward-hero__map"`) has `aria-hidden="true"` but the SVG elements inside it are still keyboard-focusable. Screen readers can tab into hidden content.  
**Element:** `<div class="home-hero__map" aria-hidden="true">` (contains focusable SVG paths)  
**Proposed fix:** Add `focusable="false"` to the inline SVG element and/or `tabindex="-1"` to any `<a>` or interactive element inside the aria-hidden container. In `build.py`, update the map SVG template to include `focusable="false"` on the `<svg>` tag.

---

### ISSUE 3 — nested-interactive (WCAG 2.1 AA)

**Severity:** High  
**Pages:** index.html only  
**What's wrong:** The turnout bar chart SVG has `role="img"` and `aria-label="…"` but contains focusable child elements (likely `<a>` or `<rect>` with event handlers). Interactive controls inside a `role="img"` landmark are illegal in WCAG.  
**Element:** `<svg … class="turnout-chart" role="img" aria-label="2022 voter turnout by ward …">`  
**Proposed fix:** Either (a) remove `role="img"` so the SVG is treated as decorative — but then add a visible text data table below it — or (b) keep `role="img"` and add `tabindex="-1"` and `aria-hidden="true"` to all interactive children of the SVG. Simplest: add `focusable="false"` to every `<a>` inside the chart SVG.

---

### ISSUE 4 — Missing meta description, OG tags, and canonical URL

**Severity:** Medium  
**Pages:** All pages  
**What's wrong:** Every page is missing:
- `<meta name="description" content="…">` — used by search engines and social previews
- `<meta property="og:title">`, `<meta property="og:description">`, `<meta property="og:url">` — used when sharing links
- `<link rel="canonical">` — prevents search engines from indexing duplicate paths
- `<meta name="robots">` — no indexing control at all (relevant before public launch)

**Proposed fix:** In `build.py`, add per-page meta tags to the `<head>` template. Suggested descriptions:
- index.html: "Toronto Ward Facts — an independent, non-partisan guide to City Council's record for the 2026 municipal election."
- ward-N.html: "Ward N [Ward Name] — voter turnout, council voting record, and neighbourhood data for the 2026 Toronto election."
- councillor-ward-N.html: "Councillor [Name]'s voting record, attendance, and close decisions — Ward N, Toronto City Council 2022–2026."
- about.html: "How Toronto Ward Facts works — data sources, methodology, and corrections."

---

### ISSUE 5 — Regression test expected value incorrect (test script bug, not a data error)

**Severity:** Low  
**Pages:** docs/ward-4.html (Parkdale–High Park)  
**What's wrong:** A pre-audit regression check expected Ward 4 2018 turnout = 46.57%. The value in wards.json is 46.53%, and independent recalculation from the raw file (`2018_Voter_Turnout_Statistics_FINAL.XLSX`) confirms **46.53% is correct**:
- Total Eligible Electors (subdivisions 1–96): 83,919
- Number Voted (all subdivisions): 39,051
- Turnout: 39,051 / 83,919 × 100 = **46.53%**

The page correctly displays "46.5%" (rounded to 1 decimal). The regression test script had the wrong expected value.  
**Proposed fix:** Update the regression test expected value from 46.57 to 46.53. No change needed to wards.json or the HTML.

---

### ISSUE 6 — "OLT" unexpanded abbreviation in close-vote card titles

**Severity:** Low  
**Pages:** councillor-ward-*.html (pages where OLT agenda items appear in close-vote cards)  
**What's wrong:** Some agenda item titles from the City's voting CSV include "OLT" (Ontario Land Tribunal) and "OPA" (Official Plan Amendment) as bare abbreviations. These appear verbatim in the vote card titles. Toronto staff will know these, but for a grade-8 audience these are unexplained.  
**Proposed fix (light touch):** In `build.py`'s `build_councillor_page()` function, add an `_expand_abbreviations()` helper that replaces known acronyms with "Ontario Land Tribunal (OLT)" and "Official Plan Amendment (OPA)" on first use per page. Or add a tooltip/abbr HTML element around each occurrence. The summaries generated by `generate_summaries.py` can be updated to expand the abbreviations in the summary sentence.

---

## What was checked and did NOT fail

- **validate.py re-run:** 815 checks, 0 failures.
- **3-ward spot-check (Wards 4, 13, 25):** All displayed values (registered voters, ballots cast, turnout %, winner vote share, margin of votes, change vs 2018) traced to raw source files and match.
- **By-election wards (15, 20, 25):** All three pages carry a by-election note; all three councillor detail pages carry the low-n caution note (Shan n=49, Chernos Lin n=85).
- **Party labels:** None found across all 77 HTML files.
- **Loaded language:** "Margin of victory" appears on all 25 ward pages — this is standard election-results terminology and is not an editorial judgement. "Declined ballots" refers to the official ballot category under the Municipal Elections Act. No loaded words were found.
- **Strong-mayor footnote (Footnote 2):** Reads accurately: "Under Ontario's strong-mayor rules, the Mayor's budget takes effect without a Council vote to adopt it. Council votes on amendments and on tax rates and fees." — factual and neutral.
- **TTC abbreviation:** Expanded in context as "Toronto Transit Commission (TTC)" on all ward pages.
- **Internal links:** All 77 pages — zero broken internal links.
- **Page weights:** Average 61 KB, maximum 80 KB. Well under the 500 KB threshold.
- **Readability:** No actual prose sentences over 25 words. The long-sentence detections were navigation lists, not body text.
- **GeoJSON:** Appears only in the data-sources attribution table, not in reader-facing prose.

---

## Screenshots

Playwright screenshots taken (read-only, not committed):
- `/tmp/ward4-mobile.png` — Ward 4 at 375 × 812 px (iPhone SE)
- `/tmp/ward4-desktop.png` — Ward 4 at 1280 × 900 px

---

## Recommended fix priority for Phase 2

1. **Issues 1–3** (WCAG — colour contrast, aria-hidden, nested-interactive): fix in `build.py` / style.css. Fast changes, broad impact.
2. **Issue 4** (meta tags): add per-page description/OG/canonical. Also add `<meta name="robots" content="noindex,nofollow">` for the staff-preview edition (Phase 4).
3. **Issue 5** (regression test): update the expected value in the test script.
4. **Issue 6** (OLT abbreviation): low priority; address only if time permits before staff preview.

---

*End of Phase 1 audit. No files were modified during this audit.*
