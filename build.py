#!/usr/bin/env python3
"""
build.py — Toronto Ward Facts site generator.
Reads data/wards.json + data/raw/city-wards-4326.geojson
Writes docs/style.css, docs/index.html, docs/about.html, docs/ward-N.html (25 pages).
Run: python3 build.py

PREVIEW = True  → adds preview banner + noindex to every page.
Set to False before public launch.
"""

# ── Preview mode ───────────────────────────────────────────────────────────────
PREVIEW = False  # flip to True to re-enable staff preview mode

import csv
import json
import os
import math
import re
import html as html_lib

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE         = os.path.dirname(os.path.abspath(__file__))
DATA_JSON    = os.path.join(BASE, 'data', 'wards.json')
METRICS_CSV  = os.path.join(BASE, 'data', 'councillor_metrics.csv')
GEOJSON      = os.path.join(BASE, 'data', 'raw', 'city-wards-4326.geojson')
DOCS         = os.path.join(BASE, 'docs')
os.makedirs(DOCS, exist_ok=True)

# ── Councillor metrics (from data/councillor_metrics.csv) ─────────────────────
def _load_councillor_metrics():
    metrics = {}
    with open(METRICS_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            for k in ('attendance_pct', 'council_avg_att', 'with_majority_pct',
                      'with_mayor_pct', 'majority_n', 'mayor_n', 'contested_cast',
                      'votes_eligible', 'votes_cast', 'votes_missed', 'votes_ai',
                      'sessions_present', 'sessions_total'):
                v = row.get(k, '')
                try:
                    row[k] = float(v) if '.' in v else (int(v) if v else None)
                except ValueError:
                    row[k] = None
            metrics[row['fullname']] = row
    return metrics

COUNCILLOR_METRICS = _load_councillor_metrics()

# Range of with_mayor_pct among current members (pre-verified: 22.7%–95.2%)
_current_mayor_pcts = [
    m['with_mayor_pct']
    for m in COUNCILLOR_METRICS.values()
    if m.get('is_current') == 'Y' and m['with_mayor_pct'] is not None
]
COUNCIL_MAYOR_RANGE = (min(_current_mayor_pcts), max(_current_mayor_pcts))
COUNCIL_AVG_ATT     = next(iter(COUNCILLOR_METRICS.values()))['council_avg_att']

# ── Vote summaries (from data/vote_summaries.csv — edit then rebuild) ─────────
SUMMARIES_CSV = os.path.join(BASE, 'data', 'vote_summaries.csv')

def _load_vote_summaries():
    if not os.path.exists(SUMMARIES_CSV):
        return {}
    out = {}
    with open(SUMMARIES_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            out[row['item_num']] = row
    return out

VOTE_SUMMARIES = _load_vote_summaries()

# ── Close-vote / councillor-page helpers ──────────────────────────────────────
MOTION_TYPE_PLAIN = {
    'Adopt Item':             'Final decision',
    'Adopt Item as Amended':  'Final decision (as amended)',
    'Amend Item':             'Proposed amendment',
    'Amend Item (Additional)':'Additional proposed amendment',
    'Amend Item (Two-Thirds)':'Proposed amendment (two-thirds required)',
    'Amend Motion':           'Proposed change to a motion',
    'Refer Item':             'Refer back to committee',
    'Defer Item':             'Defer the decision',
}

VOTE_IN_WORDS = {
    'Yes':                     'Voted yes',
    'No':                      'Voted no',
    'Absent':                  'Was absent',
    'Absent(Interest Declared)':'Declared an interest and did not vote',
}

FINAL_MOTION_TYPES = {'Adopt Item', 'Adopt Item as Amended'}

def _result_words(result_str, two_thirds):
    carried = 'Carried' in result_str
    m = re.search(r'(\d+)-(\d+)', result_str)
    label = 'Passed' if carried else 'Did not pass'
    if m:
        label += f' ({m.group(1)} yes, {m.group(2)} no)'
    if two_thirds:
        label += ' — required two-thirds majority'
    return label


def _dot_strip_svg(cur_name):
    """SVG dot chart: where cur_name sits among current councillors on with_mayor_pct."""
    W, H = 600, 90
    TY   = 52            # track y
    X0, X1 = 20, 580
    TL = X1 - X0

    dots = []
    for fname, m in COUNCILLOR_METRICS.items():
        if m.get('is_current') == 'Y' and m['with_mayor_pct'] is not None:
            pct = m['with_mayor_pct']
            x   = round(X0 + (pct / 100) * TL)
            dots.append((pct, x, fname, fname == cur_name))

    lines = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'class="dot-strip-svg" role="img" '
        f'aria-label="Council range chart for voted with the Mayor, {h(cur_name)} highlighted">',
        f'  <desc>Each dot is one current ward councillor. '
        f'Blue dot is {h(cur_name)}. Left = less often with Mayor, right = more often.</desc>',
        f'  <line x1="{X0}" y1="{TY}" x2="{X1}" y2="{TY}" stroke="#dddddd" stroke-width="2"/>',
    ]
    for tick in (0, 25, 50, 75, 100):
        tx = round(X0 + (tick / 100) * TL)
        lines.append(f'  <line x1="{tx}" y1="{TY-4}" x2="{tx}" y2="{TY+4}" stroke="#cccccc" stroke-width="1"/>')
        lines.append(f'  <text x="{tx}" y="{TY+18}" text-anchor="middle" font-size="9" fill="#666">{tick}%</text>')

    # Others first (drawn underneath)
    for pct, x, name, is_cur in dots:
        if not is_cur:
            lines.append(
                f'  <circle cx="{x}" cy="{TY}" r="5" fill="#d0d8e8" stroke="#a0b0c8" stroke-width="1">'
                f'<title>{h(name)}: {pct}%</title></circle>'
            )
    # Highlighted dot on top with label
    for pct, x, name, is_cur in dots:
        if is_cur:
            lx = max(30, min(x, W - 30))   # keep label inside canvas
            lines.append(f'  <line x1="{x}" y1="{TY-8}" x2="{lx}" y2="{TY-22}" stroke="#0047FF" stroke-width="1"/>')
            lines.append(
                f'  <text x="{lx}" y="{TY-25}" text-anchor="middle" '
                f'font-size="10" font-weight="bold" fill="#0047FF">{pct}%</text>'
            )
            lines.append(
                f'  <circle cx="{x}" cy="{TY}" r="8" fill="#0047FF" stroke="#0030bb" stroke-width="1.5">'
                f'<title>{h(name)}: {pct}%</title></circle>'
            )
    lines.append('</svg>')
    return '\n'.join(lines)


def _close_vote_cards(w, cur):
    """Build the 'Closest decisions' section for a councillor detail page."""
    from collections import defaultdict
    cvs = [cv for cv in (w.get('close_votes') or []) if cv.get('voted_by') == cur]
    if not cvs:
        return '<p>No close votes recorded for this councillor.</p>'

    by_item = defaultdict(list)
    for cv in cvs:
        by_item[cv['item']].append(cv)

    # Sort items most-recent-first using the first vote's date for that item
    item_dates = {k: min(v['date'] for v in vs) for k, vs in by_item.items()}
    sorted_items = sorted(by_item, key=lambda i: item_dates[i], reverse=True)

    def _vote_row(cv):
        mt   = cv.get('motion_type', '')
        mt_p = MOTION_TYPE_PLAIN.get(mt, mt)
        vote = cv.get('vote', '')
        vi   = VOTE_IN_WORDS.get(vote, vote)
        res  = _result_words(cv.get('result', ''), cv.get('two_thirds_required', False))
        vd   = cv.get('vote_description', '')
        vd_h = f'<div class="cv-desc">{h(vd)}</div>' if vd else ''
        return (
            f'<div class="vote-row">'
            f'<span class="vote-row__type">{h(mt_p)}</span>'
            f'<span class="vote-row__cast">{h(vi)}</span>'
            f'<span class="vote-row__result">{h(res)}</span>'
            f'{vd_h}</div>'
        )

    cards = []
    for item_num in sorted_items:
        votes   = by_item[item_num]
        title   = votes[0]['title']
        date    = item_dates[item_num]
        si      = VOTE_SUMMARIES.get(item_num, {})
        summary = si.get('summary', '')
        url     = si.get('official_url',
                         f'https://secure.toronto.ca/council/agenda-item.do?item={item_num}')

        finals  = [v for v in votes if v['motion_type'] in FINAL_MOTION_TYPES]
        others  = [v for v in votes if v['motion_type'] not in FINAL_MOTION_TYPES]

        if finals:
            final_h = ''.join(_vote_row(v) for v in finals)
            other_h = ''
            if others:
                rows = ''.join(_vote_row(v) for v in others)
                s    = '' if len(others) == 1 else 's'
                other_h = (f'<details class="other-votes"><summary>{len(others)} '
                           f'other vote{s} on this item</summary>{rows}</details>')
        else:
            # No final decision among the close votes for this item — show all prominently
            final_h = ''.join(_vote_row(v) for v in others)
            other_h = ''

        sum_h = f'<p class="vote-card__summary">{h(summary)}</p>' if summary else ''
        cards.append(
            f'<div class="vote-card">'
            f'<div class="vote-card__meta"><span class="vote-card__date">{h(date)}</span>'
            f'<span class="vote-card__item">{h(item_num)}</span></div>'
            f'<h3 class="vote-card__title">{h(title)}</h3>'
            f'{sum_h}'
            f'<div class="vote-card__votes">{final_h}{other_h}</div>'
            f'<p class="vote-card__link"><a href="{h(url)}">Read the official record &#8594;</a></p>'
            f'</div>'
        )

    n_items = len(sorted_items)
    return (
        f'<section class="closest-decisions" aria-labelledby="h-decisions">'
        f'<h2 id="h-decisions">Closest decisions, 2022–2026</h2>'
        f'<p class="note">City Council votes where the margin between Yes and No was 3 or fewer, '
        f'with at least 10 members voting. Procedural motions excluded. '
        f'{n_items} items, most recent first. Expand items to see amendment votes.</p>'
        f'<div class="vote-cards">{"".join(cards)}</div>'
        f'</section>'
    )


def build_councillor_page(w, ward_paths, bounds):
    wn  = w['ward_num']
    cur = f"{w['councillor_first']} {w['councillor_last']}"
    m   = COUNCILLOR_METRICS.get(cur, {})
    bye = w.get('by_election')

    att_pct  = m.get('attendance_pct')
    sess_pre = m.get('sessions_present')
    sess_tot = m.get('sessions_total')
    mayor_pct= m.get('with_mayor_pct')
    mayor_n  = m.get('mayor_n') or 0
    maj_pct  = m.get('with_majority_pct')
    maj_n    = m.get('majority_n') or 0
    elig     = m.get('votes_eligible') or 0
    cast_n   = m.get('votes_cast') or 0
    missed   = m.get('votes_missed') or 0
    ai       = m.get('votes_ai') or 0
    contested_cast = m.get('contested_cast') or 0
    first_vote     = m.get('first_vote') or ''

    bv_list = [bv for bv in (w.get('budget_votes') or []) if bv.get('voted_by') == cur]
    bv_str  = ' · '.join(f'{bv["year"]} {h(bv.get("vote","—"))}' for bv in bv_list) or 'Not available'

    mayor_str = (f'{fmt_pct(mayor_pct)} of contested final decisions '
                 f'<span class="stat-sub">(based on {mayor_n} votes · '
                 f'council range: {COUNCIL_MAYOR_RANGE[0]}%–{COUNCIL_MAYOR_RANGE[1]}%)</span>'
                 if mayor_pct is not None else 'Not calculated')

    maj_str = (f'{fmt_pct(maj_pct)} of contested final decisions '
               f'<span class="stat-sub">(based on {maj_n} votes)</span>'
               if maj_pct is not None else 'Not available')

    ai_txt  = f' · {ai} interest declared' if ai else ''
    votes_str = f'{fmt_num(elig)} eligible · {fmt_num(cast_n)} cast · {missed} absent{ai_txt}'

    low_n_html = ''
    if 0 < contested_cast < 100 and first_vote:
        low_n_html = (f'<p class="note">Based on {contested_cast} contested votes '
                      f'since {h(first_vote)}.</p>')

    bye_html = (f'<p class="by-election-note"><strong>Note:</strong> {h(bye)}</p>'
                if bye else '')

    dot_svg = _dot_strip_svg(cur)

    return '\n'.join([
        page_open(
            f'{cur} — Ward {wn} Councillor Record',
            description=(f'{cur}\'s attendance, voting record, and close decisions '
                         f'on Toronto City Council 2022–2026. Ward {wn} — {h(w["ward_name"])}.'),
            og_url=f'councillor-ward-{wn}.html',
        ),
        f'''<div class="councillor-detail">
  <p class="breadcrumb"><a href="ward-{wn}.html">&#8592; Ward {wn} — {h(w["ward_name"])}</a></p>
  <h1>{h(cur)}</h1>
  <p class="detail-subtitle">Ward {wn} councillor &middot; City Council record, 2022–2026 term</p>
  {bye_html}

  <div class="record-card">
    <dl class="record-metrics">
      <div class="record-metric">
        <dt>Attendance</dt>
        <dd>{fmt_pct(att_pct)} of Council sessions
          <span class="stat-sub">({fmt_num(sess_pre)} of {fmt_num(sess_tot)} sessions &middot; council average: {fmt_pct(COUNCIL_AVG_ATT)})</span></dd>
      </div>
      <div class="record-metric">
        <dt>Voted with the Mayor <sup class="record-sup">1</sup></dt>
        <dd>{mayor_str}</dd>
      </div>
      <div class="record-metric">
        <dt>On the winning side</dt>
        <dd>{maj_str}</dd>
      </div>
      <div class="record-metric">
        <dt>Property tax and fee votes <sup class="record-sup">2</sup></dt>
        <dd>{bv_str}</dd>
      </div>
      <div class="record-metric">
        <dt>Votes recorded</dt>
        <dd>{votes_str}</dd>
      </div>
    </dl>
    {low_n_html}
    <p class="note record-footnotes">
      <sup>1</sup> Contested final decisions are final votes on an item where at least 3 councillors voted No (191 votes). Mayor Olivia Chow joined Council in July 2023; only votes she took part in are counted.<br>
      <sup>2</sup> Under Ontario&#x27;s strong-mayor rules, the Mayor&#x27;s budget takes effect without a Council vote to adopt it. Council votes on amendments and on tax rates and fees.
    </p>
  </div>

  <div class="dot-strip-block">
    <h2>Where {h(cur)} sits on &#8220;voted with the Mayor&#8221;</h2>
    <p class="note">Each dot is one current ward councillor. Blue = {h(cur)}. Left = voted with Mayor less often, right = more often.
       Only contested final decisions where both the councillor and Mayor Chow cast a Yes or No vote are counted.</p>
    {dot_svg}
  </div>

  {_close_vote_cards(w, cur)}

</div>''',
        page_close(),
    ])

# ── Constants ──────────────────────────────────────────────────────────────────
ELECTION_DATE = 'Monday, October 26, 2026'
CHECKED       = '2026-10-15'
LAT_CENTER    = 43.715
LAT_SCALE     = 1 / math.cos(math.radians(LAT_CENTER))   # ~1.387; corrects Mercator squish

# Official toronto.ca links only — each verified to load
LINKS = {
    'candidates':    'https://www.toronto.ca/city-government/elections/candidate-list/',
    'myvote':        'https://myvote.toronto.ca/home',
    'voter_info':    'https://www.toronto.ca/city-government/elections/voter-information/',
    'advance':       'https://www.toronto.ca/city-government/elections/voter-information/voting-options/',
    'id_req':        'https://www.toronto.ca/city-government/elections/voter-information/acceptable-identification/',
    'voter_stats':   'https://open.toronto.ca/dataset/elections-voter-statistics/',
    'results_22':    'https://open.toronto.ca/dataset/election-results-official/',
    'officials':     'https://open.toronto.ca/dataset/elected-officials-contact-information/',
    'by_election':   'https://open.toronto.ca/dataset/elections-official-by-election-results/',
    'census':        'https://open.toronto.ca/dataset/ward-profiles-2011-2021-census/',
    'voting_rec':    'https://open.toronto.ca/dataset/members-of-toronto-city-council-voting-record/',
    'attendance':    'https://open.toronto.ca/dataset/members-of-toronto-city-council-meeting-attendance/',
    'wards_geo':     'https://open.toronto.ca/dataset/city-wards/',
    'licence':       'https://open.toronto.ca/open-data-licence/',
    'crime_mci':     'https://open.toronto.ca/dataset/major-crime-indicators/',
    'ksi':           'https://open.toronto.ca/dataset/motor-vehicle-collisions-involving-killed-or-seriously-injured-persons/',
    'three11':       'https://open.toronto.ca/dataset/311-service-requests-customer-initiated/',
}

CANDIDATE_QUESTIONS = [
    'What are your three priorities for this ward in the next term?',
    'Roads and sidewalks are a top concern for many Toronto residents. What is your plan for road maintenance and pedestrian safety in this ward?',
    'Housing costs are a significant concern. What policies would you support at City Council to make housing more affordable?',
    'How will you approach property tax decisions at City Council, and what would you change about the city budget?',
    'What is your approach to public safety in this ward, and how would you work with the Toronto Police Services Board?',
    'How will you stay in contact with residents throughout the term?',
    'How will you work with other councillors and the Mayor to get things done for this ward?',
]

# Nanos/CTV/CP24 poll — Sept 30–Oct 4 2026
POLL_ITEMS = [
    ('Traffic and roads',     26),
    ('Housing costs',         18),
    ('Public safety / crime', 16),
    ('Property taxes',        12),
]
POLL_SOURCE = ('Nanos Research for CTV News/CP24, Sept 30–Oct 4, 2026. '
               'n=755 Toronto residents, MOE ±3.6 percentage points, 19 times out of 20.')

COUNCIL_CAN = [
    'Property taxes and most City fees',
    'Toronto Transit Commission (TTC) — routes, fares, and service levels',
    'City roads, traffic signals, and sidewalks',
    'Garbage collection, recycling, and composting',
    'Parks, arenas, and community centres',
    'Building permits, zoning, and land-use planning',
    'Toronto Public Library',
    'City-funded affordable-housing programs',
    'Toronto Public Health programs',
    'Toronto Police Service budget',
    'Toronto Water and wastewater services',
]
COUNCIL_CANNOT = [
    'Provincial highways (400, 401, 404, QEW) — managed by Ontario',
    'School boards and education funding — set by the province',
    'Hospitals — funded and regulated by Ontario',
    'GO Transit and regional rail (Metrolinx) — a provincial Crown agency',
    'Federal programs such as immigration and employment insurance',
]


# ── Text helpers ───────────────────────────────────────────────────────────────

def h(val):
    """HTML-escape a value for safe insertion."""
    return html_lib.escape(str(val)) if val is not None else ''

def fmt_pct(v, d=1):
    if v is None:
        return 'Not available'
    return f'{v:.{d}f}%'

def fmt_num(v):
    if v is None:
        return 'Not available'
    return f'{int(v):,}'

def fmt_dollar(v):
    if v is None:
        return 'Not available'
    return f'${int(v):,}'

def display_name(raw):
    """Reverse 'LastName FirstName' → 'FirstName LastName' for display."""
    parts = str(raw).strip().split()
    if len(parts) <= 1:
        return raw
    return parts[-1] + ' ' + ' '.join(parts[:-1])


# ── GeoJSON / SVG map helpers ─────────────────────────────────────────────────

def load_geojson():
    with open(GEOJSON, encoding='utf-8') as f:
        return json.load(f)

def compute_bounds(gj):
    mn_lon = mn_lat =  float('inf')
    mx_lon = mx_lat = -float('inf')
    for feat in gj['features']:
        for poly in feat['geometry']['coordinates']:
            for ring in poly:
                for lon, lat in ring:
                    if lon < mn_lon: mn_lon = lon
                    if lon > mx_lon: mx_lon = lon
                    if lat < mn_lat: mn_lat = lat
                    if lat > mx_lat: mx_lat = lat
    return mn_lon, mx_lon, mn_lat, mx_lat

def _project(lon, lat, w, bounds):
    mn_lon, mx_lon, mn_lat, mx_lat = bounds
    scale = w / (mx_lon - mn_lon)
    x = (lon - mn_lon) * scale
    y = (mx_lat - lat) * LAT_SCALE * scale
    return x, y

def _svg_height(w, bounds):
    mn_lon, mx_lon, mn_lat, mx_lat = bounds
    return round(w * (mx_lat - mn_lat) * LAT_SCALE / (mx_lon - mn_lon), 1)

def _ward_path_d(feat, w, bounds):
    parts = []
    for poly in feat['geometry']['coordinates']:
        for ring in poly:
            pts = [_project(lon, lat, w, bounds) for lon, lat in ring]
            if not pts:
                continue
            # Round to integers — sufficient precision for a 480px context map
            d = f'M{round(pts[0][0])},{round(pts[0][1])}'
            prev = (round(pts[0][0]), round(pts[0][1]))
            for x, y in pts[1:]:
                rx, ry = round(x), round(y)
                if (rx, ry) != prev:   # skip duplicate pixels
                    d += f'L{rx},{ry}'
                    prev = (rx, ry)
            parts.append(d + 'Z')
    return ' '.join(parts)

MAP_W = 480

def build_ward_paths(gj, bounds):
    paths = {}
    for feat in gj['features']:
        wn = int(feat['properties']['AREA_SHORT_CODE'])
        paths[wn] = _ward_path_d(feat, MAP_W, bounds)
    return paths

def city_map_svg(ward_paths, bounds, highlight=None, link_all=True, tab_stop=True):
    """Full-city outline SVG. highlight=ward_num draws that ward in dark blue.
    tab_stop=False adds tabindex="-1" to all links (use in aria-hidden containers)."""
    h_val = _svg_height(MAP_W, bounds)
    has_hl = highlight is not None
    lines = [
        f'<svg viewBox="0 0 {MAP_W} {h_val}" xmlns="http://www.w3.org/2000/svg" '
        f'class="city-map" role="img" aria-label="Map of Toronto\'s 25 wards'
        + (f', ward {highlight} highlighted' if has_hl else '') + '">',
        '  <desc>Outline map showing all 25 Toronto municipal wards.</desc>',
    ]
    a_attrs = ' tabindex="-1" aria-hidden="true"' if not tab_stop else ''
    for wn in sorted(ward_paths):
        d    = ward_paths[wn]
        fill = '#0047FF' if wn == highlight else ('#d0d8f0' if has_hl else '#6b8ccc')
        path = (f'<path d="{d}" fill="{fill}" stroke="#fff" stroke-width="0.7" '
                f'stroke-linejoin="round"><title>Ward {wn}</title></path>')
        if link_all or wn == highlight:
            lines.append(f'  <a href="ward-{wn}.html"{a_attrs}>{path}</a>')
        else:
            lines.append(f'  {path}')
    lines.append('</svg>')
    return '\n'.join(lines)


# ── HTML chrome ────────────────────────────────────────────────────────────────

def page_open(title, is_home=False, description=None, og_url=None):
    pt = 'Toronto Ward Facts' if is_home else f'{h(title)} | Toronto Ward Facts'
    base_url = 'https://pravikant23.github.io/toronto-ward-accountability'
    canonical = f'{base_url}/{og_url}' if og_url else None
    desc_tag = (f'\n  <meta name="description" content="{h(description)}">'
                if description else '')
    og_tags = ''
    if description and og_url:
        og_tags = (
            f'\n  <meta property="og:type" content="website">'
            f'\n  <meta property="og:title" content="{h(pt)}">'
            f'\n  <meta property="og:description" content="{h(description)}">'
            f'\n  <meta property="og:url" content="{canonical}">'
        )
    canonical_tag = f'\n  <link rel="canonical" href="{canonical}">' if canonical else ''
    noindex_tag   = '\n  <meta name="robots" content="noindex,nofollow">' if PREVIEW else ''
    preview_banner = (
        '\n<div class="preview-banner" role="alert">'
        '<strong>Staff preview</strong> — not for public distribution. '
        'This site is under review before public release. '
        '<a href="for-city-staff.html">Staff briefing →</a>'
        '</div>'
    ) if PREVIEW else ''
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">{desc_tag}{og_tags}{canonical_tag}{noindex_tag}
  <title>{pt}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>{preview_banner}
<a class="skip-link" href="#main">Skip to main content</a>
<header class="site-header">
  <a class="site-logo" href="index.html">Toronto Ward Facts</a>
  <div class="site-header__right">
    <nav class="site-nav" aria-label="Site navigation">
      <a href="index.html">Home</a>
      <a href="about.html">About</a>
    </nav>
    <span class="site-credit">A civic project by
      <a href="https://perimtr.ca" class="perimtr-link" rel="noopener">
        <img src="perimtr-logo.png" alt="Perimtr" class="perimtr-logo-img">
      </a>
    </span>
  </div>
</header>
<main id="main">'''

def page_close():
    return f'''</main>
<footer class="site-footer">
  <div class="site-footer__inner">
    <div class="footer-data">
      <p>Data from <a href="{LINKS["voter_stats"]}">City of Toronto Open Data</a> under the
         <a href="{LINKS["licence"]}">Open Government Licence – Toronto</a>.
         Numbers last checked {CHECKED}. Corrections: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a></p>
      <p><a href="about.html">About &amp; Sources</a></p>
    </div>
    <aside class="footer-independence" aria-label="Independence statement">
      <p class="independence-label">Editorial independence</p>
      <p>Toronto Ward Facts is a civic project by
         <a href="https://perimtr.ca" rel="noopener">Perimtr</a>, an independent
         research and software company. This site is non-partisan and is not affiliated
         with any candidate, political party, or the City of Toronto.
         Editorial decisions are made independently.</p>
    </aside>
  </div>
</footer>
</body>
</html>'''


# ── Inline SVG turnout bar chart (index page) ──────────────────────────────────

def turnout_chart_svg(wards, city_pct):
    """Horizontal bars sorted lowest → highest, city avg as dashed black line."""
    sorted_w = sorted(wards, key=lambda w: w.get('turnout_pct') or 0)
    bar_h    = 22
    label_w  = 192
    chart_w  = 260
    pad_r    = 50
    total_w  = label_w + chart_w + pad_r
    total_h  = len(sorted_w) * bar_h + 44

    max_pct = max(w.get('turnout_pct') or 0 for w in sorted_w)
    city_x  = label_w + round(city_pct / max_pct * chart_w)

    lines = [
        f'<svg viewBox="0 0 {total_w} {total_h}" xmlns="http://www.w3.org/2000/svg" '
        f'class="turnout-chart" aria-hidden="true">',
    ]
    for i, ward in enumerate(sorted_w):
        y     = i * bar_h + 8
        tp    = ward.get('turnout_pct') or 0
        bw    = max(2, round(tp / max_pct * chart_w))
        wn    = ward['ward_num']
        label = f"W{wn}"
        lines.append(
            f'  <a href="ward-{wn}.html" tabindex="-1" aria-hidden="true">'
            f'<text x="{label_w - 6}" y="{y + 14}" text-anchor="end" '
            f'class="tc-label">{h(label)}</text>'
            f'<rect x="{label_w}" y="{y + 3}" width="{bw}" height="{bar_h - 8}" '
            f'fill="#0047FF" rx="0"><title>Ward {wn}: {tp}%</title></rect>'
            f'<text x="{label_w + bw + 4}" y="{y + 14}" class="tc-pct">{tp:.1f}%</text>'
            f'</a>'
        )
    lines.append(
        f'  <line x1="{city_x}" y1="6" x2="{city_x}" y2="{total_h - 20}" '
        f'stroke="#000000" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'  <text x="{city_x + 3}" y="{total_h - 6}" class="tc-avg" fill="#000000">'
        f'City avg {city_pct:.1f}%</text>'
    )
    lines.append('</svg>')
    return '\n'.join(lines)


# ── Vote badge helper ──────────────────────────────────────────────────────────

def vote_badge(vote):
    if not vote or vote == 'Not recorded':
        return '<span class="vote-na">Not recorded</span>'
    cls = {'Yes': 'vote-yes', 'No': 'vote-no',
           'Absent': 'vote-absent',
           'Absent(Interest Declared)': 'vote-absent'}.get(vote, 'vote-na')
    return f'<span class="{cls}">{h(vote)}</span>'


# ── Ward page sections ─────────────────────────────────────────────────────────

def sec_glance(w, city_census):
    reg     = fmt_num(w['registered_voters'])
    bc      = fmt_num(w['ballots_cast'])
    tp22    = fmt_pct(w['turnout_pct'])
    tp18    = fmt_pct(w.get('turnout_2018_pct'))
    chg     = w.get('change_vs_2018')
    city_tp = fmt_pct(w.get('city_turnout_pct'))
    chg_txt = (f'+{chg:.2f} percentage points' if chg and chg >= 0 else
               f'{chg:.2f} percentage points') if chg is not None else 'Not available'

    winner   = next((c for c in w['candidates_2022'] if c.get('is_winner')), None)
    w_name   = display_name(winner['name']) if winner else 'Not available'
    w_pct    = fmt_pct(winner.get('vote_pct')) if winner else 'Not available'
    w_share  = w.get('winner_share_of_registered')
    in_n     = (f' ({w_share * 100:.1f}% of registered voters)'
                if w_share else '')

    margin_v  = fmt_num(w.get('margin_votes'))
    margin_pp = fmt_pct(w.get('margin_pct_points'), 2) if w.get('margin_pct_points') is not None else '—'
    runner    = display_name(w['runner_up_name']) if w.get('runner_up_name') else '—'
    open_seat = w.get('open_seat')
    open_txt  = ('Yes — the 2018 councillor did not run in 2022.' if open_seat is True
                 else 'No — the 2018 councillor ran again in 2022.' if open_seat is False else '—')

    tp_raw  = w['turnout_pct'] or 0

    return f'''<section id="at-a-glance" aria-labelledby="h-glance">
  <h2 id="h-glance">At a glance — 2022 election</h2>
  <dl class="stat-grid">
    <div class="stat-item">
      <dt>Registered voters</dt>
      <dd>{reg}</dd>
    </div>
    <div class="stat-item">
      <dt>Ballots cast</dt>
      <dd>{bc}</dd>
    </div>
    <div class="stat-item">
      <dt>Voter turnout 2022</dt>
      <dd>{tp22}
        <div class="bar-wrap" role="meter" aria-valuenow="{tp_raw}" aria-valuemin="0"
             aria-valuemax="100" aria-label="Turnout gauge">
          <div class="bar-fill" style="width:{min(tp_raw,100):.1f}%"></div>
        </div>
        <span class="stat-sub">City-wide average: {city_tp}</span>
      </dd>
    </div>
    <div class="stat-item">
      <dt>Turnout 2018 (change)</dt>
      <dd>{tp18} <span class="stat-sub">{chg_txt}</span></dd>
    </div>
    <div class="stat-item">
      <dt>2022 winner</dt>
      <dd>{h(w_name)}, {w_pct} of valid votes{in_n}</dd>
    </div>
    <div class="stat-item">
      <dt>Margin of victory</dt>
      <dd>{margin_v} votes ({margin_pp}) over {h(runner)}</dd>
    </div>
    <div class="stat-item">
      <dt>Open seat in 2022?</dt>
      <dd>{open_txt}</dd>
    </div>
  </dl>
</section>'''

def sec_results(w):
    cands       = w['candidates_2022']
    total_valid = fmt_num(w.get('total_valid_votes_2022'))
    num_cands   = w.get('num_candidates', 0)

    rows = []
    for c in cands:
        name   = h(display_name(c['name']))
        votes  = fmt_num(c['votes'])
        pct_v  = c.get('vote_pct') or 0
        winner = c.get('is_winner', False)
        cls    = ' class="winner-row"' if winner else ''
        badge  = ' <span class="winner-badge" aria-label="Winner">Won</span>' if winner else ''
        rows.append(f'''    <tr{cls}>
      <td class="cand-name">{name}{badge}</td>
      <td class="cand-votes">{votes}</td>
      <td class="cand-bar-cell" aria-label="{pct_v:.1f} percent">
        <div class="cand-bar-wrap" role="presentation">
          <div class="cand-bar" style="width:{pct_v:.1f}%"></div>
          <span class="cand-pct">{pct_v:.1f}%</span>
        </div>
      </td>
    </tr>''')

    rows_html = '\n'.join(rows)
    return f'''<section id="results" aria-labelledby="h-results">
  <h2 id="h-results">2022 election results</h2>
  <p>{num_cands} candidates. {total_valid} valid votes counted.</p>
  <div class="table-scroll">
  <table class="cand-table" aria-label="2022 election results by candidate">
    <thead>
      <tr>
        <th scope="col">Candidate</th>
        <th scope="col">Votes</th>
        <th scope="col">Share of valid votes</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
  </div>
  <p class="note">Candidate names as listed in the official City of Toronto results file
  (format varies by name). Vote percentages are of valid votes only.</p>
</section>'''

def sec_census(w, city_census):
    cen     = w.get('census', {})
    pop     = fmt_num(cen.get('population_2021'))
    med_age = cen.get('median_age_2021')
    c_age   = city_census.get('median_age_2021')
    income  = fmt_dollar(cen.get('median_household_income_2020'))
    c_inc   = fmt_dollar(city_census.get('median_household_income_2020'))
    pct_own = fmt_pct(cen.get('pct_owned'))
    pct_rnt = fmt_pct(cen.get('pct_rented'))
    c_own   = fmt_pct(city_census.get('pct_owned'))
    c_rnt   = fmt_pct(city_census.get('pct_rented'))

    age_s   = str(med_age) if med_age is not None else 'Not available'
    c_age_s = str(c_age) if c_age is not None else '—'

    langs   = cen.get('top_non_official_languages', [])
    if langs:
        lang_items = ''.join(f'<li>{h(lg["language"])}: {fmt_num(lg["speakers"])} speakers</li>'
                             for lg in langs)
        lang_html  = f'<ol>{lang_items}</ol>'
    else:
        lang_html  = '<p>Not available</p>'

    return f'''<section id="census" aria-labelledby="h-census">
  <h2 id="h-census">2021 Census — ward profile</h2>
  <p class="note">Source: Statistics Canada 2021 Census, City of Toronto Ward Profiles custom tabulation.</p>
  <dl class="stat-grid">
    <div class="stat-item">
      <dt>Population (2021)</dt>
      <dd>{pop}</dd>
    </div>
    <div class="stat-item">
      <dt>Median age</dt>
      <dd>{age_s} <span class="stat-sub">City: {c_age_s}</span></dd>
    </div>
    <div class="stat-item">
      <dt>Median household income (2020)</dt>
      <dd>{income} <span class="stat-sub">City: {c_inc}</span></dd>
    </div>
    <div class="stat-item">
      <dt>Housing tenure</dt>
      <dd>Owned: {pct_own} / Rented: {pct_rnt}
        <span class="stat-sub">City: owned {c_own} / rented {c_rnt}</span>
      </dd>
    </div>
  </dl>
  <div class="census-langs">
    <h3>Top languages spoken at home (other than English and French)</h3>
    {lang_html}
    <p class="note">Language spoken most often at home (2021 Census, 25% sample). English and French not included.</p>
  </div>
</section>'''

def sec_what_matters(w, city_census):
    issues = w.get('issues', {})
    pop    = (w.get('census') or {}).get('population_2021') or 0

    # Poll bars — proportional to max
    max_pct = max(pct for _, pct in POLL_ITEMS)
    poll_rows = []
    for label, pct in POLL_ITEMS:
        bw = round(pct / max_pct * 100)
        poll_rows.append(
            f'<div class="poll-bar-row">'
            f'<span class="poll-bar-label">{h(label)}</span>'
            f'<div class="poll-bar-wrap">'
            f'<div class="poll-bar" style="width:{bw}%" title="{pct}%"></div>'
            f'<span class="poll-bar-pct">{pct}%</span>'
            f'</div></div>'
        )
    poll_html = '\n    '.join(poll_rows)

    # Traffic/roads card
    three11_yr  = (issues.get('three11') or {}).get('years', {}).get('2025') or {}
    road311     = three11_yr.get('road_related')
    ksi_issues  = issues.get('ksi') or {}
    ksi_yr25    = ksi_issues.get('years', {}).get('2025') or {}
    ksi_yr26    = ksi_issues.get('years', {}).get('2026') or {}
    ksi_ytd25   = ksi_issues.get('ytd_jan_sep_2025') or {}
    ksi_cnt25   = ksi_yr25.get('collisions')   # full year 2025
    ksi_ped25   = ksi_yr25.get('pedestrian', 0)
    ksi_cyc25   = ksi_yr25.get('cyclist', 0)
    ksi_cnt26   = ksi_yr26.get('collisions')   # Jan-Sep 2026
    ksi_ytd25_n = ksi_ytd25.get('collisions')  # Jan-Sep 2025 (for comparison)

    if road311 is not None and pop:
        road_rate = round(road311 / pop * 1000, 1)
        road_line = f'{fmt_num(road311)} road and sidewalk service requests in 2025 ({road_rate} per 1,000 residents)'
    else:
        road_line = 'Not available'

    if ksi_cnt25 is not None:
        ped_cyc_parts = []
        if ksi_ped25: ped_cyc_parts.append(f'{ksi_ped25} pedestrian-involved')
        if ksi_cyc25: ped_cyc_parts.append(f'{ksi_cyc25} cyclist-involved')
        ped_cyc_txt = (': ' + ', '.join(ped_cyc_parts)) if ped_cyc_parts else ''
        ksi_line25 = f'{ksi_cnt25} serious-injury or fatal collisions, 2025 (full year){ped_cyc_txt}'
        if ksi_cnt26 is not None:
            sp25 = f'same period 2025: {ksi_ytd25_n}' if ksi_ytd25_n is not None else ''
            ksi_line26 = f'{ksi_cnt26} collisions, Jan 1–Sep 30, 2026' + (f' ({sp25})' if sp25 else '')
        else:
            ksi_line26 = None
    else:
        ksi_line25 = None
        ksi_line26 = None

    # Housing card
    pct_rnt = (w.get('census') or {}).get('pct_rented')
    c_rnt   = (city_census or {}).get('pct_rented')
    med_inc = (w.get('census') or {}).get('median_household_income_2020')
    c_inc   = (city_census or {}).get('median_household_income_2020')

    rnt_line = (f'{fmt_pct(pct_rnt)} of dwellings rented'
                + (f' <span class="stat-sub">(city: {fmt_pct(c_rnt)})</span>' if c_rnt is not None else '')) \
               if pct_rnt is not None else 'Not available'
    inc_line = (f'Median household income 2020: {fmt_dollar(med_inc)}'
                + (f' <span class="stat-sub">(city: {fmt_dollar(c_inc)})</span>' if c_inc is not None else '')) \
               if med_inc is not None else 'Not available'

    # Safety card
    crime_issues = issues.get('crime') or {}
    crime_yr25   = crime_issues.get('years', {}).get('2025') or {}
    crime_cnt25  = crime_yr25.get('count')
    crime_rate25 = crime_yr25.get('rate_per_1k')
    city_rate25  = crime_issues.get('city_rate_per_1k', {}).get('2025')
    ytd24_ward   = crime_issues.get('ytd_jan_sep_2024') or {}
    crime_cnt24  = ytd24_ward.get('count')
    city_ytd24   = crime_issues.get('city_ytd_jan_sep_2024') or {}
    city_cnt24   = city_ytd24.get('count')
    city_ytd25   = crime_issues.get('city_jan_sep_2025') or {}
    city_cnt25   = city_ytd25.get('count')

    if crime_cnt25 is not None:
        crime_line = f'{fmt_num(crime_cnt25)} police-reported offences, Jan–Sep 2025'
        rate_line  = (f'{crime_rate25:.1f} per 1,000 residents'
                      + (f' <span class="stat-sub">(city avg: {city_rate25:.1f})</span>'
                         if city_rate25 is not None else '')) if crime_rate25 is not None else ''
        # YoY ward Jan-Sep comparison
        if crime_cnt24 is not None and crime_cnt24 > 0:
            yoy_pct  = round((crime_cnt25 - crime_cnt24) / crime_cnt24 * 100, 0)
            yoy_sign = '+' if yoy_pct >= 0 else ''
            yoy_ward = f'{crime_cnt24:,} → {crime_cnt25:,} ({yoy_sign}{int(yoy_pct)}%)'
        else:
            yoy_ward = None
        # YoY city Jan-Sep comparison
        if city_cnt24 and city_cnt25 and city_cnt24 > 0:
            city_pct  = round((city_cnt25 - city_cnt24) / city_cnt24 * 100, 0)
            city_sign = '+' if city_pct >= 0 else ''
            yoy_city  = f'{city_cnt24:,} → {city_cnt25:,} ({city_sign}{int(city_pct)}%)'
        else:
            yoy_city = None
    else:
        crime_line = 'Not available'
        rate_line  = ''
        yoy_ward   = None
        yoy_city   = None

    # Property taxes card — only current councillor's votes
    cur_name = f"{w['councillor_first']} {w['councillor_last']}"
    bv_list  = [bv for bv in (w.get('budget_votes') or [])
                if bv.get('voted_by') == cur_name]
    if bv_list:
        bv_parts = [f'{bv["year"]}: {bv.get("vote","—")}' for bv in bv_list]
        bv_line  = f'<p class="stat-sub">{h(cur_name)}\'s budget votes — {h(", ".join(bv_parts))}</p>'
    else:
        bv_line = ''

    return f'''<section id="what-matters" aria-labelledby="h-matters">
  <h2 id="h-matters">What matters here</h2>
  <p class="note">A September 2026 survey asked Toronto residents their top concern for the municipal election.
     Ward data below is from City of Toronto open data.</p>

  <div class="poll-block">
    <h3>Top concerns — Toronto residents, September 2026</h3>
    <div class="poll-bars">
    {poll_html}
    </div>
    <p class="note">{h(POLL_SOURCE)}</p>
  </div>

  <div class="issue-cards">

    <div class="issue-card">
      <div class="issue-card__head issue-card__head--traffic">
        <span class="issue-card__pct">26%</span>
        <h3>Traffic and roads</h3>
      </div>
      <div class="issue-card__body">
        <p>{road_line}</p>
        <p class="note">The City renamed its 311 categories in 2025, so earlier years cannot be compared.
           Source: <a href="{LINKS["three11"]}">311 Service Requests</a>.</p>
        {f'<p class="stat-sub">{h(ksi_line25)}</p>' if ksi_line25 else ''}
        {f'<p class="stat-sub">{h(ksi_line26)}</p>' if ksi_line26 else ''}
        <p class="note">KSI = killed or seriously injured collisions (Toronto Police, by date of occurrence).
           Source: <a href="{LINKS["ksi"]}">Motor Vehicle Collisions — KSI</a>.</p>
      </div>
    </div>

    <div class="issue-card">
      <div class="issue-card__head issue-card__head--housing">
        <span class="issue-card__pct">18%</span>
        <h3>Housing costs</h3>
      </div>
      <div class="issue-card__body">
        <p>{rnt_line}</p>
        <p>{inc_line}</p>
        <p class="note">New housing permits per ward: not available. The City's building permits file
           uses a map-grid code (e.g. "E2022") that does not correspond to ward boundaries
           and contains no coordinates.
           Source: <a href="{LINKS["census"]}">2021 Census Ward Profiles</a>.</p>
      </div>
    </div>

    <div class="issue-card">
      <div class="issue-card__head issue-card__head--safety">
        <span class="issue-card__pct">16%</span>
        <h3>Public safety</h3>
      </div>
      <div class="issue-card__body">
        <p>{crime_line}</p>
        {f'<p>{rate_line}</p>' if rate_line else ''}
        {f'<p class="stat-sub">Jan–Sep 2024 vs Jan–Sep 2025 — this ward: {h(yoy_ward)}</p>' if yoy_ward else ''}
        {f'<p class="stat-sub">City-wide: {h(yoy_city)}</p>' if yoy_city else ''}
        <p class="note">Includes: Assault, Auto Theft, Break and Enter, Robbery, Theft Over.
           The dataset covers Jan–Sep 2025 only (most recent available).
           Offences are located to the nearest intersection for privacy; 1–2% dropped per year
           due to missing coordinates.
           Downtown wards have many commuters and visitors, so offences per resident can look higher.
           Source: <a href="{LINKS["crime_mci"]}">Major Crime Indicators</a>.</p>
      </div>
    </div>

    <div class="issue-card">
      <div class="issue-card__head issue-card__head--taxes">
        <span class="issue-card__pct">12%</span>
        <h3>Property taxes</h3>
      </div>
      <div class="issue-card__body">
        <p>Property tax rates are set by City Council and apply to all Toronto residential
           properties. There is no per-ward breakdown of tax rates.</p>
        {bv_line}
        <p class="note">See the full budget vote record in the
           <a href="#record">Councillor record</a> section below.</p>
      </div>
    </div>

  </div>
</section>'''


def sec_record(w):
    wn  = w['ward_num']
    cur = f"{w['councillor_first']} {w['councillor_last']}"
    bye = w.get('by_election')
    m   = COUNCILLOR_METRICS.get(cur, {})

    # ── Attendance ────────────────────────────────────────────────────────────
    att_pct = m.get('attendance_pct')
    att_str = fmt_pct(att_pct) if att_pct is not None else 'Not available'
    avg_str = fmt_pct(COUNCIL_AVG_ATT)

    # ── Voted with the Mayor ──────────────────────────────────────────────────
    mayor_pct = m.get('with_mayor_pct')
    mayor_n   = m.get('mayor_n') or 0
    if mayor_pct is not None:
        rng_lo, rng_hi = COUNCIL_MAYOR_RANGE
        mayor_str = (f'{fmt_pct(mayor_pct)} of contested final decisions '
                     f'<span class="stat-sub">(council range: {rng_lo}%–{rng_hi}%)</span>')
    else:
        mayor_str = 'Not calculated'

    # ── On the winning side ───────────────────────────────────────────────────
    maj_pct = m.get('with_majority_pct')
    maj_str = (f'{fmt_pct(maj_pct)} of contested final decisions'
               if maj_pct is not None else 'Not available')

    # ── Property tax and fee votes ────────────────────────────────────────────
    bv_list = [bv for bv in (w.get('budget_votes') or [])
               if bv.get('voted_by') == cur]
    if bv_list:
        bv_parts = []
        for bv in bv_list:
            v = bv.get('vote') or '—'
            bv_parts.append(f'{bv["year"]} {h(v)}')
        bv_str = ' · '.join(bv_parts)
    else:
        bv_str = 'Not available'

    # ── Low-n note (by-election councillors) ─────────────────────────────────
    contested_cast = m.get('contested_cast') or 0
    first_vote     = m.get('first_vote') or ''
    low_n_html = ''
    if 0 < contested_cast < 100 and first_vote:
        low_n_html = (f'<p class="note">Based on {contested_cast} contested votes '
                      f'since {h(first_vote)}.</p>')

    # ── Footnotes ─────────────────────────────────────────────────────────────
    footnote_mayor = (
        'Contested final decisions are final votes on an item where at least 3 councillors '
        'voted No (191 votes). Mayor Olivia Chow joined Council in July 2023; only votes '
        'she took part in are counted.'
    )
    footnote_budget = (
        'Under Ontario\'s strong-mayor rules, the Mayor\'s budget takes effect without a '
        'Council vote to adopt it. Council votes on amendments and on tax rates and fees.'
    )

    bye_html = (f'<p class="by-election-note"><strong>Note:</strong> {h(bye)}</p>'
                if bye else '')

    detail_url = f'councillor-ward-{wn}.html'

    return f'''<section id="record" aria-labelledby="h-record">
  <h2 id="h-record">{h(cur)}'s record, 2022–2026</h2>
  {bye_html}
  <div class="record-card">
    <dl class="record-metrics">
      <div class="record-metric">
        <dt>Attendance</dt>
        <dd>{att_str} of Council sessions
          <span class="stat-sub">(council average: {avg_str})</span></dd>
      </div>
      <div class="record-metric">
        <dt>Voted with the Mayor <sup class="record-sup">1</sup></dt>
        <dd>{mayor_str}</dd>
      </div>
      <div class="record-metric">
        <dt>On the winning side</dt>
        <dd>{maj_str}</dd>
      </div>
      <div class="record-metric">
        <dt>Property tax and fee votes <sup class="record-sup">2</sup></dt>
        <dd>{bv_str}</dd>
      </div>
    </dl>
    {low_n_html}
    <p class="note record-footnotes">
      <sup>1</sup> {h(footnote_mayor)}<br>
      <sup>2</sup> {h(footnote_budget)}
    </p>
    <p class="record-detail-link">
      <a href="{detail_url}">See every vote, explained &#8594;</a>
    </p>
  </div>
</section>'''

def sec_powers():
    can_li  = ''.join(f'<li>{h(x)}</li>' for x in COUNCIL_CAN)
    cant_li = ''.join(f'<li>{h(x)}</li>' for x in COUNCIL_CANNOT)
    return f'''<section id="council-powers" aria-labelledby="h-powers">
  <h2 id="h-powers">What City Council controls</h2>
  <p>City Council makes decisions on matters within the City's jurisdiction.
     Some services are managed by the province or the federal government, not the City.</p>
  <div class="powers-grid">
    <div>
      <h3>City Council decides</h3>
      <ul>{can_li}</ul>
    </div>
    <div>
      <h3>Not under City Council control</h3>
      <ul>{cant_li}</ul>
    </div>
  </div>
</section>'''

def sec_questions():
    q_li = ''.join(f'<li>{h(q)}</li>' for q in CANDIDATE_QUESTIONS)
    return f'''<section id="questions" aria-labelledby="h-questions">
  <h2 id="h-questions">Questions to ask candidates</h2>
  <p>The 2026 election is on {ELECTION_DATE}. These are general questions you can
     ask any candidate at an all-candidates meeting or by email.
     This site does not endorse any candidate or party.</p>
  <ul class="q-list">{q_li}</ul>
  <p>For the official list of candidates in your ward, see the
     <a href="{LINKS["candidates"]}">City of Toronto candidate list</a>.</p>
</section>'''

def sec_vote():
    return f'''<section id="vote-2026" aria-labelledby="h-vote">
  <h2 id="h-vote">How to vote — {ELECTION_DATE}</h2>
  <dl class="vote-dl">
    <div>
      <dt>Find your polling station</dt>
      <dd><a href="{LINKS["myvote"]}">MyVote (myvote.toronto.ca)</a> — enter your address
          to find your ward, your voting location, and advance polling options.</dd>
    </div>
    <div>
      <dt>Advance voting</dt>
      <dd>Advance voting locations are available before election day.
          <a href="{LINKS["advance"]}">See advance voting options</a>.</dd>
    </div>
    <div>
      <dt>What ID do I need?</dt>
      <dd><a href="{LINKS["id_req"]}">Accepted identification</a> — options include a
          driver's licence, Ontario photo card, utility bill, and many others.</dd>
    </div>
    <div>
      <dt>General voter information</dt>
      <dd><a href="{LINKS["voter_info"]}">toronto.ca — voter information</a></dd>
    </div>
  </dl>
</section>'''

def sec_sources(w):
    src = w.get('sources', {})
    return f'''<section id="sources" aria-labelledby="h-sources">
  <h2 id="h-sources">Data sources</h2>
  <p>All numbers on this page come from official City of Toronto open data.
     Nothing is estimated or invented. Where data is unavailable, the page says so.</p>
  <table class="data-table" aria-label="Data sources for this ward">
    <thead>
      <tr><th scope="col">Data</th><th scope="col">File</th><th scope="col">Open Data link</th></tr>
    </thead>
    <tbody>
      <tr><td>2022 voter turnout</td>
          <td>{h(src.get('registered_voters',''))}</td>
          <td><a href="{LINKS["voter_stats"]}">Elections – Voter Statistics</a></td></tr>
      <tr><td>2018 voter turnout</td>
          <td>{h(src.get('turnout_2018',''))}</td>
          <td><a href="{LINKS["voter_stats"]}">Elections – Voter Statistics</a></td></tr>
      <tr><td>2022 election results</td>
          <td>{h(src.get('candidates',''))}</td>
          <td><a href="{LINKS["results_22"]}">Election Results – Official</a></td></tr>
      <tr><td>Current councillor</td>
          <td>{h(src.get('officials',''))}</td>
          <td><a href="{LINKS["officials"]}">Elected Officials Contact Information</a></td></tr>
      <tr><td>By-election results</td>
          <td>Individual by-election files</td>
          <td><a href="{LINKS["by_election"]}">Elections – Official By-Election Results</a></td></tr>
      <tr><td>2021 Census ward profiles</td>
          <td>{h(src.get('census',''))}</td>
          <td><a href="{LINKS["census"]}">Ward Profiles (2011–2021 Census)</a></td></tr>
      <tr><td>Council voting record</td>
          <td>council-voting-2022-2026.csv</td>
          <td><a href="{LINKS["voting_rec"]}">Council Voting Record</a></td></tr>
      <tr><td>Council attendance</td>
          <td>{h(src.get('attendance',''))}</td>
          <td><a href="{LINKS["attendance"]}">Council Meeting Attendance</a></td></tr>
      <tr><td>Ward boundaries (map)</td>
          <td>city-wards-4326.geojson</td>
          <td><a href="{LINKS["wards_geo"]}">City Wards</a></td></tr>
      <tr><td>Major crime indicators (2018–2025; 2025 = Jan–Sep only)</td>
          <td>major-crime-indicators.csv</td>
          <td><a href="{LINKS["crime_mci"]}">Major Crime Indicators</a></td></tr>
      <tr><td>Motor vehicle collisions — KSI (2018–2025 full year; 2026 Jan–Sep)</td>
          <td>motor-vehicle-collisions-ksi-4326.csv</td>
          <td><a href="{LINKS["ksi"]}">Motor Vehicle Collisions — KSI</a></td></tr>
      <tr><td>311 service requests (2022–2025 full year; 2026 Jan–Sep)</td>
          <td>sr2022.zip – sr2026.zip</td>
          <td><a href="{LINKS["three11"]}">311 Service Requests — Customer Initiated</a></td></tr>
    </tbody>
  </table>
  <p class="note">Data published under the
     <a href="{LINKS["licence"]}">Open Government Licence – Toronto</a>.
     Numbers last verified {CHECKED}.</p>
</section>'''


# ── Page builders ──────────────────────────────────────────────────────────────

def build_ward_page(w, ward_paths, bounds, city_census):
    wn   = w['ward_num']
    name = w['ward_name']
    cur  = f"{w['councillor_first']} {w['councillor_last']}"
    bye  = w.get('by_election')

    map_svg  = city_map_svg(ward_paths, bounds, highlight=wn, tab_stop=False)
    bye_html = (f'<p class="by-election-strip"><strong>By-election:</strong> {h(bye)}</p>'
                if bye else '')

    page_nav = '''<nav class="page-nav" aria-label="Jump to section">
  <a href="#at-a-glance">At a glance</a>
  <a href="#what-matters">What matters</a>
  <a href="#results">2022 Results</a>
  <a href="#census">Census</a>
  <a href="#record">Councillor record</a>
  <a href="#council-powers">Council powers</a>
  <a href="#questions">Questions</a>
  <a href="#vote-2026">How to vote</a>
  <a href="#sources">Sources</a>
</nav>'''

    return '\n'.join([
        page_open(
            f'Ward {wn} — {name}',
            description=(f'Ward {wn} {name}: 2022 voter turnout, election results, '
                         f'councillor voting record, and neighbourhood data for the 2026 Toronto election.'),
            og_url=f'ward-{wn}.html',
        ),
        f'''<div class="ward-hero">
  <div class="ward-hero__text">
    <p class="ward-label">Ward {wn}</p>
    <h1>{h(name)}</h1>
    <p class="councillor-line">Current councillor: <strong>{h(cur)}</strong></p>
    {bye_html}
  </div>
  <div class="ward-hero__map" aria-hidden="true">{map_svg}</div>
</div>''',
        page_nav,
        sec_glance(w, city_census),
        sec_what_matters(w, city_census),
        sec_results(w),
        sec_census(w, city_census),
        sec_record(w),
        sec_powers(),
        sec_questions(),
        sec_vote(),
        sec_sources(w),
        page_close(),
    ])


def build_index(data, ward_paths, bounds):
    wards      = data['wards']
    city22     = data['city_2022']
    city18     = data['city_2018']

    reg22  = fmt_num(city22['registered_voters'])
    bc22   = fmt_num(city22['ballots_cast'])
    tp22   = fmt_pct(city22['turnout_pct'])
    tp18   = fmt_pct(city18['turnout_pct'])

    map_svg   = city_map_svg(ward_paths, bounds, link_all=True, tab_stop=False)
    chart_svg = turnout_chart_svg(wards, city22['turnout_pct'])

    def _issue_val(ward, key, sub, default=''):
        return (ward.get('issues') or {}).get(key, {}).get('years', {}).get('2025') or {}

    tbl_rows_list = []
    for ward in sorted(wards, key=lambda x: x['ward_num']):
        wn   = ward['ward_num']
        tp   = ward.get('turnout_pct') or 0
        pop  = (ward.get('census') or {}).get('population_2021') or 0

        crime_25   = ((ward.get('issues') or {}).get('crime') or {}).get('years', {}).get('2025') or {}
        crime_rate = crime_25.get('rate_per_1k') or ''

        three11_25 = ((ward.get('issues') or {}).get('three11') or {}).get('years', {}).get('2025') or {}
        road311    = three11_25.get('road_related') or ''

        ksi_25     = ((ward.get('issues') or {}).get('ksi') or {}).get('years', {}).get('2025') or {}
        ksi_cnt    = ksi_25.get('collisions') or ''

        tbl_rows_list.append(
            f'<tr>'
            f'<td data-val="{wn}"><a href="ward-{wn}.html">Ward {wn}</a></td>'
            f'<td data-val="{h(ward.get("ward_name",""))}">{h(ward.get("ward_name",""))}</td>'
            f'<td data-val="{h(ward["councillor_last"])}">{h(ward["councillor_first"])} {h(ward["councillor_last"])}</td>'
            f'<td data-val="{tp}">{fmt_pct(ward.get("turnout_pct"))}</td>'
            f'<td data-val="{crime_rate}">{f"{crime_rate:.1f}/1k" if crime_rate else "—"}</td>'
            f'<td data-val="{road311}">{fmt_num(road311) if road311 else "—"}</td>'
            f'<td data-val="{ksi_cnt}">{ksi_cnt if ksi_cnt else "—"}</td>'
            f'</tr>'
        )
    tbl_rows = '\n'.join(tbl_rows_list)

    sort_js = '''<script>
(function(){
  var tbl = document.getElementById('ward-table');
  if (!tbl) return;
  var ths = tbl.querySelectorAll('th[data-sort]');
  var state = {};
  ths.forEach(function(th){
    th.addEventListener('click', function(){
      var col = parseInt(th.getAttribute('data-sort'), 10);
      var asc = state[col] !== true;
      state = {};
      state[col] = asc;
      ths.forEach(function(h){ h.className = ''; });
      th.className = asc ? 'sort-asc' : 'sort-desc';
      var tbody = tbl.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function(a, b){
        var av = (a.children[col].getAttribute('data-val') || '').trim();
        var bv = (b.children[col].getAttribute('data-val') || '').trim();
        var an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  });
})();
</script>'''

    return '\n'.join([
        page_open(
            'Toronto Ward Facts',
            is_home=True,
            description=('Independent, non-partisan data on all 25 Toronto wards — '
                         'voter turnout, 2022 election results, councillor voting records, '
                         'and ward-level data on traffic, crime, and housing.'),
            og_url='index.html',
        ),
        f'''<div class="home-hero">
  <div class="home-hero__text">
    <h1>Toronto Ward Facts</h1>
    <p class="lead">Official data on all 25 Toronto wards — voter turnout, 2022 election
       results, census profiles, councillor voting records, and ward-level data on traffic,
       crime, and housing. Non-partisan. Sourced entirely from City of Toronto open data.</p>
    <p>Next election: <strong>{ELECTION_DATE}</strong></p>
    <a class="btn" href="{LINKS["myvote"]}">Find my ward and polling place</a>
  </div>
  <div class="home-hero__map" aria-hidden="true">{map_svg}</div>
</div>

<section id="city-stats" aria-labelledby="h-city">
  <h2 id="h-city">City-wide — 2022 municipal election</h2>
  <dl class="stat-grid">
    <div class="stat-item"><dt>Registered voters</dt><dd>{reg22}</dd></div>
    <div class="stat-item"><dt>Ballots cast</dt><dd>{bc22}</dd></div>
    <div class="stat-item"><dt>Voter turnout 2022</dt><dd>{tp22}</dd></div>
    <div class="stat-item"><dt>Voter turnout 2018</dt><dd>{tp18}</dd></div>
  </dl>
</section>

<section id="turnout-chart" aria-labelledby="h-chart">
  <h2 id="h-chart">2022 turnout by ward (sorted lowest → highest)</h2>
  <p>Select a ward bar to go to its full data page. Dashed line = city average.</p>
  <div class="chart-scroll">{chart_svg}</div>
</section>

<section id="ward-list" aria-labelledby="h-wards">
  <h2 id="h-wards">All 25 wards</h2>
  <p class="note">Click any column heading to sort. Crime rate is for Jan–Sep 2025 (most recent available in the dataset). Road 311 and KSI are full-year 2025. KSI = serious-injury or fatal collisions.</p>
  <div class="table-scroll">
  <table class="data-table ward-dir-tbl" id="ward-table" aria-label="All 25 Toronto wards">
    <thead>
      <tr>
        <th scope="col" data-sort="0">Ward</th>
        <th scope="col" data-sort="1">Name</th>
        <th scope="col" data-sort="2">Current councillor</th>
        <th scope="col" data-sort="3">2022 turnout</th>
        <th scope="col" data-sort="4">Crime/1k (Jan–Sep 2025)</th>
        <th scope="col" data-sort="5">Road 311 (2025 full year)</th>
        <th scope="col" data-sort="6">KSI (2025 full year)</th>
      </tr>
    </thead>
    <tbody>{tbl_rows}</tbody>
  </table>
  </div>
</section>''',
        sort_js,
        page_close(),
    ])


def build_about(data):
    city22 = data['city_2022']
    return '\n'.join([
        page_open(
            'About this site',
            description=('How Toronto Ward Facts works — data sources, methodology, '
                         'definitions, and how to report a correction.'),
            og_url='about.html',
        ),
        f'''<h1>About Toronto Ward Facts</h1>

<section aria-labelledby="h-what">
  <h2 id="h-what">What this site is</h2>
  <p>Toronto Ward Facts presents official municipal election and census data for all 25
     Toronto wards. It is non-partisan and has no affiliation with any candidate, party,
     or the City of Toronto. Every number comes from a City of Toronto or Statistics
     Canada open data file. Nothing is estimated or invented.</p>
</section>

<section aria-labelledby="h-data">
  <h2 id="h-data">Data sources</h2>
  <table class="data-table" aria-label="Data sources">
    <thead><tr><th scope="col">Dataset</th><th scope="col">Open Data link</th></tr></thead>
    <tbody>
      <tr><td>2022 and 2018 voter turnout statistics</td>
          <td><a href="{LINKS["voter_stats"]}">Elections – Voter Statistics</a></td></tr>
      <tr><td>2022 official election results</td>
          <td><a href="{LINKS["results_22"]}">Election Results – Official</a></td></tr>
      <tr><td>2023, 2024, 2025 by-election results</td>
          <td><a href="{LINKS["by_election"]}">Elections – Official By-Election Results</a></td></tr>
      <tr><td>Elected officials contact information</td>
          <td><a href="{LINKS["officials"]}">Elected Officials Contact Information</a></td></tr>
      <tr><td>Ward Profiles (2021 Census)</td>
          <td><a href="{LINKS["census"]}">Ward Profiles (2011–2021 Census)</a></td></tr>
      <tr><td>Council voting record (2022–2026)</td>
          <td><a href="{LINKS["voting_rec"]}">Members of Toronto City Council – Voting Record</a></td></tr>
      <tr><td>Council attendance (2022–2026)</td>
          <td><a href="{LINKS["attendance"]}">Members of Toronto City Council – Meeting Attendance</a></td></tr>
      <tr><td>City ward boundaries (GeoJSON)</td>
          <td><a href="{LINKS["wards_geo"]}">City Wards</a></td></tr>
      <tr><td>Major crime indicators (2018–2025, Jan–Sep 2025 only)</td>
          <td><a href="{LINKS["crime_mci"]}">Major Crime Indicators</a></td></tr>
      <tr><td>Motor vehicle collisions — KSI (2018–2025 full year; 2026 Jan–Sep)</td>
          <td><a href="{LINKS["ksi"]}">Motor Vehicle Collisions — KSI</a></td></tr>
      <tr><td>311 service requests (2022–2025 full year; 2026 Jan–Sep)</td>
          <td><a href="{LINKS["three11"]}">311 Service Requests — Customer Initiated</a></td></tr>
    </tbody>
  </table>
  <p class="note">All data published under the
     <a href="{LINKS["licence"]}">Open Government Licence – Toronto</a>.</p>
</section>

<section aria-labelledby="h-what-matters">
  <h2 id="h-what-matters">What matters here — methodology</h2>
  <p>The "What matters here" section on each ward page shows ward-level data for
     the four issues Toronto residents named most often in a September 2026 survey.</p>
  <ul>
    <li><strong>Traffic and roads:</strong> 311 service request counts for potholes, road damage,
        traffic signals, sidewalks, and related categories (2025 full year shown; 2026 Jan–Sep shown separately).
        The City renamed its 311 service categories in 2025, so earlier years cannot be compared directly
        and are not shown. KSI collision counts use unique collision IDs where the outcome was a fatality
        or serious injury. 2025 KSI is full year (Jan–Dec); 2026 KSI covers Jan–Sep only.</li>
    <li><strong>Housing costs:</strong> Renter share and median household income from the 2021 Census.
        Language spoken most often at home (excluding English and French) from the 2021 Census 25% sample.
        Building permits per ward are not available: the City's permits file uses a map-grid
        reference code that does not correspond to ward boundaries.</li>
    <li><strong>Public safety:</strong> Five MCI categories (Assault, Auto Theft, Break and Enter,
        Robbery, Theft Over) by date of occurrence. Ward assignment uses a spatial join of
        WGS84 coordinates against ward polygons (1–2% of records dropped per year due to
        missing coordinates). 2025 data covers January–September only (the full dataset does not
        include Oct–Dec 2025). A Jan–Sep 2024 comparison is provided for each ward and city-wide.
        Downtown wards have many commuters and visitors, so offences per resident can look higher.</li>
    <li><strong>Property taxes:</strong> Rates are set city-wide by City Council under Ontario's
        strong-mayor rules (since 2023). Per-ward tax-rate data does not exist. The section shows
        the councillor's vote on tax rates and fees for each budget year (2023–2026), including
        which sub-vote is shown.</li>
  </ul>
  <p>Poll source: Nanos Research for CTV News/CP24, Sept 30–Oct 4, 2026. n=755, MOE ±3.6%, 19 times out of 20.</p>
</section>

<section aria-labelledby="h-formula">
  <h2 id="h-formula">Turnout formula</h2>
  <p><strong>Turnout % = Number Voted ÷ Total Eligible Electors × 100</strong></p>
  <p>Ballots cast = Number Voted only (column 14 of the voter statistics file).
     Declined ballots are not included.
     Subdivisions 97 (mail-in), 98, and 99 (advance voting) are included in the vote count
     but not in the eligible-elector total, because those voters are already counted in
     their home subdivision's eligible total.</p>
  <p>City-wide 2022: {fmt_num(city22["registered_voters"])} registered,
     {fmt_num(city22["ballots_cast"])} ballots cast,
     {fmt_pct(city22["turnout_pct"])} turnout.</p>
</section>

<section aria-labelledby="h-by">
  <h2 id="h-by">By-election notes</h2>
  <ul>
    <li><strong>Ward 15 (Don Valley West):</strong> Rachel Chernos Lin won the
        November 4, 2024 by-election, succeeding Jaye Robinson who won the 2022 general election.</li>
    <li><strong>Ward 20 (Scarborough Southwest):</strong> Parthi Kandavel won the
        November 30, 2023 by-election, succeeding Gary Crawford who won the 2022 general election.</li>
    <li><strong>Ward 25 (Scarborough-Rouge Park):</strong> Neethan Shan won the
        September 29, 2025 by-election, succeeding Jennifer McKelvie who won the 2022 general election.</li>
  </ul>
</section>

<section aria-labelledby="h-independence">
  <h2 id="h-independence">Editorial independence</h2>
  <div class="independence-box">
    <p>Toronto Ward Facts is a civic project by
       <a href="https://perimtr.ca" rel="noopener">Perimtr</a>, an independent
       research and software company based in Toronto.</p>
    <p>This site is <strong>non-partisan</strong> and is not affiliated with any candidate,
       political party, or the City of Toronto. All data on this site comes from City of
       Toronto open data sources. Editorial decisions — what to show, how to describe it,
       and what to omit — are made independently by the Perimtr team.</p>
    <p>We do not accept advertising, sponsorship, or payment from any political organization.
       If you believe a number is wrong, please send corrections to
       <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a>.</p>
  </div>
</section>

<section aria-labelledby="h-contact">
  <h2 id="h-contact">Contact and corrections</h2>
  <p>Corrections: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a></p>
</section>''',
        page_close(),
    ])


# ── Staff preview page ────────────────────────────────────────────────────────

def build_staff_page():
    return '\n'.join([
        page_open(
            'For City Staff — Toronto Ward Facts',
            description='Staff briefing for the Toronto Ward Facts pre-release review.',
            og_url='for-city-staff.html',
        ),
        '''<div class="staff-page">
<div class="staff-hero">
  <p class="ward-label">Staff preview</p>
  <h1>Toronto Ward Facts — Staff Briefing</h1>
  <p class="lead">Thank you for reviewing this site before public release.
     This page explains what the site does, what data it uses, and how to
     flag corrections or concerns.</p>
</div>

<section aria-labelledby="h-what">
  <h2 id="h-what">What this site is</h2>
  <p>Toronto Ward Facts is a non-partisan civic information site that presents
     official City of Toronto open data in plain language for residents ahead of
     the October 26, 2026 municipal election. It covers all 25 wards.</p>
  <p>Each ward page shows: 2022 voter turnout and election results, councillor
     attendance and voting record on Council (2022–2026), census profile, and
     ward-level data on traffic, crime, and 311 service requests.</p>
  <p>Each councillor page shows: every close council vote the member participated
     in, with a plain-language summary of the agenda item and the vote result.</p>
</section>

<section aria-labelledby="h-data">
  <h2 id="h-data">Data sources</h2>
  <p>Every number on this site comes from a City of Toronto open data file,
     published under the
     <a href="https://open.toronto.ca/open-data-licence/">Open Government Licence – Toronto</a>.
     No numbers have been estimated, adjusted, or inferred.</p>
  <table class="data-table" style="margin-top:0.9rem">
    <thead><tr><th>Data</th><th>Source file</th></tr></thead>
    <tbody>
      <tr><td>Voter turnout 2022 and 2018</td><td>elections-voter-statistics (XLSX)</td></tr>
      <tr><td>2022 election results by candidate</td><td>elections-2022-results (XLSX)</td></tr>
      <tr><td>Councillor attendance 2022–2026</td><td>council-attendance-2022-2026.csv</td></tr>
      <tr><td>Council voting record 2022–2026</td><td>council-voting-2022-2026.csv</td></tr>
      <tr><td>Census profiles (2021 Census)</td><td>ward-profiles-2021-census.xlsx</td></tr>
      <tr><td>Major crime indicators</td><td>major-crime-indicators.csv</td></tr>
      <tr><td>Motor vehicle collisions (KSI)</td><td>motor-vehicle-collisions-ksi-4326.csv</td></tr>
      <tr><td>311 service requests 2022–2026</td><td>sr2022.zip – sr2026.zip</td></tr>
      <tr><td>Ward boundaries</td><td>city-wards-4326.geojson</td></tr>
    </tbody>
  </table>
</section>

<section aria-labelledby="h-verify">
  <h2 id="h-verify">What to review</h2>
  <p>We would welcome your review of the following:</p>
  <ol class="q-list" style="padding-left:1.2rem;margin-top:0.5rem">
    <li><strong>Numbers:</strong> Do the voter turnout figures, candidate results, and
        council vote counts match your records?</li>
    <li><strong>Fairness:</strong> Is every councillor described in the same way, with
        no editorial judgment about whether their record is good or bad?</li>
    <li><strong>Plain language:</strong> Is the methodology explanation on the
        <a href="about.html">About page</a> accurate and clear?</li>
    <li><strong>Council voting summaries:</strong> The one-sentence summaries of agenda
        items on councillor pages are generated from the official item title in the
        voting CSV. If any summary mischaracterizes an item, please flag it.</li>
    <li><strong>Links:</strong> All external links point to
        <code style="font-family:var(--mono);font-size:0.85em">toronto.ca</code>
        or Statistics Canada. Let us know if any are broken or misdirected.</li>
  </ol>
</section>

<section aria-labelledby="h-corrections">
  <h2 id="h-corrections">How to send feedback</h2>
  <p>Email corrections and concerns to
     <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a>. Please include:</p>
  <ul class="q-list" style="padding-left:1.2rem;margin-top:0.5rem">
    <li>The page URL and the specific figure or text in question</li>
    <li>What the correct value or wording should be, and the source</li>
  </ul>
  <p style="margin-top:0.7rem">We will acknowledge corrections within 48 hours and
     update the site before public launch.</p>
</section>

<section aria-labelledby="h-timeline">
  <h2 id="h-timeline">Timeline</h2>
  <dl class="stat-grid" style="margin-top:0.5rem">
    <div class="stat-item"><dt>Staff preview opens</dt><dd>October 2026</dd></div>
    <div class="stat-item"><dt>Correction deadline</dt><dd>To be confirmed</dd></div>
    <div class="stat-item"><dt>Public launch target</dt><dd>Before October 26, 2026</dd></div>
    <div class="stat-item"><dt>Election day</dt><dd>Monday, October 26, 2026</dd></div>
  </dl>
</section>

<section aria-labelledby="h-independence-s">
  <h2 id="h-independence-s">Independence note</h2>
  <div class="independence-box">
    <p>Toronto Ward Facts is produced by
       <a href="https://perimtr.ca" rel="noopener">Perimtr</a>, an independent
       research and software company. This site is not affiliated with any candidate,
       political party, or the City of Toronto. We do not accept advertising or
       sponsorship from any political organization.</p>
    <p>Our goal is to help Toronto residents make informed choices on election day
       using only official City data.</p>
  </div>
</section>
</div>''',
        page_close(),
    ])


# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = '''@font-face {
  font-family: 'Boska';
  src: url('fonts/boska-500.woff2') format('woff2');
  font-weight: 500; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Boska';
  src: url('fonts/boska-700.woff2') format('woff2');
  font-weight: 700; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'Lexend';
  src: url('fonts/lexend-400.woff2') format('woff2');
  font-weight: 300 700; font-style: normal; font-display: swap;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('fonts/jetbrains-mono-400.woff2') format('woff2');
  font-weight: 400; font-style: normal; font-display: swap;
}

:root {
  --bg:      #ffffff;
  --ink:     #000000;
  --accent:  #0047FF;
  --dim:     #f8f9fa;
  --rule:    #eeeeee;
  --muted:   #666666;
  --serif:   'Boska', 'Times New Roman', Georgia, serif;
  --sans:    'Lexend', 'Helvetica Neue', Arial, sans-serif;
  --mono:    'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: var(--sans); background: var(--bg); color: var(--ink);
       line-height: 1.6; font-size: 1rem; }
a { color: var(--accent); }
a:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
h1, h2, h3, h4 { font-family: var(--serif); font-weight: 500; }

/* Preview banner */
.preview-banner { background: var(--accent); color: #fff; text-align: center;
                  padding: 0.5rem 1rem; font-family: var(--sans); font-size: 0.82rem;
                  font-weight: 500; letter-spacing: 0.02em; }
.preview-banner a { color: #fff; font-weight: 700; }
.preview-banner strong { font-weight: 700; }

/* Skip link */
.skip-link { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
.skip-link:focus { position: fixed; left: 0; top: 0; width: auto; height: auto;
                   padding: 0.5rem 1rem; background: var(--ink); color: var(--bg);
                   z-index: 9999; font-weight: 700; }

/* Site header */
.site-header { background: var(--bg); color: var(--ink); padding: 0.65rem 1.25rem;
               border-bottom: 1px solid var(--rule);
               display: flex; justify-content: space-between; align-items: center;
               flex-wrap: wrap; gap: 0.5rem; }
.site-logo { color: var(--ink); text-decoration: none; font-family: var(--serif);
             font-weight: 500; font-size: 1.1rem; letter-spacing: -0.02em; }
.site-header__right { display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap; }
.site-nav a { color: var(--muted); text-decoration: none; margin-left: 1.1rem;
              font-size: 0.88rem; font-weight: 500; }
.site-nav a:hover { color: var(--ink); }
.site-credit { font-size: 0.72rem; color: var(--muted); display: flex;
               align-items: center; gap: 0.3rem; white-space: nowrap; }
.perimtr-link { display: inline-flex; align-items: center; }
.perimtr-logo-img { height: 18px; width: auto; display: block; opacity: 0.85; }
.perimtr-link:hover .perimtr-logo-img { opacity: 1; }

/* Main */
main { max-width: 960px; margin: 0 auto; padding: 1.25rem 1rem 3rem; }

/* Ward hero */
.ward-hero { display: grid; grid-template-columns: 1fr auto; gap: 1.5rem;
             align-items: start; padding: 1.5rem 0 1rem;
             border-bottom: 2px solid var(--ink); margin-bottom: 1.5rem; }
.ward-label { font-family: var(--sans); font-size: 0.72rem; text-transform: uppercase;
              letter-spacing: 0.18em; color: var(--accent); font-weight: 500; }
.ward-hero h1 { font-family: var(--serif); font-weight: 500;
                font-size: clamp(1.5rem, 4vw, 2.2rem); letter-spacing: -0.02em;
                color: var(--ink); margin: 0.25rem 0 0.4rem; }
.councillor-line { font-size: 1rem; }
.ward-hero__map { max-width: 220px; width: 100%; }
.by-election-strip { border-left: 4px solid var(--accent);
                     background: rgba(0,71,255,0.04);
                     padding: 0.45rem 0.75rem; margin-top: 0.6rem; font-size: 0.88rem; }

/* Home hero */
.home-hero { display: grid; grid-template-columns: 1fr auto; gap: 1.5rem;
             align-items: start; padding: 1.5rem 0 1rem;
             border-bottom: 2px solid var(--ink); margin-bottom: 2rem; }
.home-hero h1 { font-family: var(--serif); font-weight: 500;
                font-size: clamp(1.6rem, 4vw, 2.4rem); letter-spacing: -0.025em;
                color: var(--ink); margin-bottom: 0.5rem; }
.home-hero__map { max-width: 300px; width: 100%; }
.lead { font-size: 1rem; margin-bottom: 0.7rem; color: var(--muted); }
.btn { display: inline-block; background: var(--ink); color: var(--bg);
       padding: 0.5rem 1.2rem; text-decoration: none;
       font-weight: 600; font-size: 0.9rem; letter-spacing: 0.04em;
       margin-top: 0.7rem; border: 1px solid var(--ink); }
.btn:hover { background: var(--accent); border-color: var(--accent); color: #fff; }

/* Section nav */
.page-nav { display: flex; flex-wrap: wrap; gap: 0.35rem 0.9rem; margin-bottom: 1.75rem;
            padding: 0.55rem 0; border-top: 1px solid var(--rule);
            border-bottom: 1px solid var(--rule); }
.page-nav a { font-size: 0.82rem; color: var(--accent); text-decoration: none; }
.page-nav a:hover { text-decoration: underline; }

/* Sections */
section { margin-bottom: 2.5rem; }
h2 { font-family: var(--serif); font-weight: 500; font-size: 1.25rem;
     letter-spacing: -0.02em; color: var(--ink);
     border-bottom: 2px solid var(--ink); padding-bottom: 0.3rem; margin-bottom: 0.9rem; }
h3 { font-family: var(--serif); font-weight: 500; font-size: 1rem;
     letter-spacing: -0.01em; color: var(--ink); margin: 1.1rem 0 0.45rem; }

/* Stat grid */
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
             gap: 0.85rem; }
.stat-item { background: var(--dim); border: 1px solid var(--rule); padding: 0.8rem 1rem; }
.stat-item dt { font-family: var(--sans); font-size: 0.72rem; text-transform: uppercase;
                letter-spacing: 0.15em; color: var(--accent); font-weight: 500;
                margin-bottom: 0.2rem; }
.stat-item dd { font-size: 1.05rem; font-weight: 600; }
.stat-sub { display: block; font-size: 0.77rem; font-weight: 400; color: var(--muted);
            margin-top: 0.12rem; }

/* Progress bars */
.bar-wrap { background: var(--rule); height: 9px; margin-top: 0.4rem; overflow: hidden; }
.bar-fill { background: var(--accent); height: 100%; }
.bar-fill--green { background: var(--accent); }

/* Candidate table */
.cand-table { width: 100%; border-collapse: collapse; margin-top: 0.6rem; }
.cand-table th { background: var(--dim); text-align: left; padding: 0.4rem 0.55rem;
                 font-family: var(--sans); font-size: 0.72rem; text-transform: uppercase;
                 letter-spacing: 0.12em; font-weight: 500; border-bottom: 2px solid var(--ink); }
.cand-table td { padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--rule);
                 vertical-align: middle; }
.winner-row td { background: rgba(0,71,255,0.04); font-weight: 600; }
.winner-badge { background: var(--ink); color: var(--bg); font-family: var(--sans);
                font-size: 0.62rem; font-weight: 700; padding: 0.12rem 0.35rem;
                margin-left: 0.45rem; vertical-align: middle; letter-spacing: 0.06em; }
.cand-name { min-width: 140px; }
.cand-votes { text-align: right; white-space: nowrap; }
.cand-bar-cell { min-width: 160px; }
.cand-bar-wrap { position: relative; background: var(--rule); height: 20px; overflow: hidden; }
.cand-bar { position: absolute; top: 0; left: 0; height: 100%; background: var(--accent);
            opacity: 0.5; }
.winner-row .cand-bar { background: var(--accent); opacity: 1; }
.cand-pct { position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
            font-size: 0.77rem; font-weight: 600; }

/* Turnout chart */
.chart-scroll { overflow-x: auto; margin-top: 0.75rem; }
.turnout-chart { min-width: 420px; width: 100%; max-width: 760px; display: block; }
.tc-label { font-size: 9px; fill: #444; font-family: sans-serif; }
.tc-pct   { font-size: 9px; fill: #666; font-family: sans-serif; }
.tc-avg   { font-size: 9px; font-family: sans-serif; }

/* City map */
.city-map { width: 100%; height: auto; display: block; }

/* Attendance block */
.att-block { background: var(--dim); border: 1px solid var(--rule);
             padding: 0.9rem 1rem; margin-bottom: 0.9rem; }

/* Vote badges */
.vote-yes    { color: var(--accent); font-weight: 700; }
.vote-no     { color: var(--ink);    font-weight: 700; }
.vote-absent { color: var(--muted); }
.vote-na     { color: var(--muted);  }
.pred-note      { font-size: 0.77rem; color: var(--muted); font-weight: 400; }
.vote-twothirds { font-family: var(--mono); font-size: 0.7rem; color: var(--muted);
                  border: 1px solid var(--rule); padding: 0 4px;
                  margin-left: 4px; white-space: nowrap; }
.cv-desc        { font-size: 0.76rem; color: var(--muted); margin-top: 2px; }

/* Generic data table */
.data-table { width: 100%; border-collapse: collapse; margin-top: 0.6rem; font-size: 0.9rem; }
.data-table th { background: var(--dim); text-align: left; padding: 0.4rem 0.55rem;
                 font-family: var(--sans); font-size: 0.72rem; text-transform: uppercase;
                 letter-spacing: 0.12em; font-weight: 500; border-bottom: 2px solid var(--ink); }
.data-table td { padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--rule);
                 vertical-align: top; }
.data-table tr:last-child td { border-bottom: none; }

/* Close vote table */
.table-scroll { overflow-x: auto; }
.close-vote-tbl td:nth-child(2) { max-width: 260px; overflow: hidden;
                                   text-overflow: ellipsis; white-space: nowrap; }

/* Ward directory */
.ward-dir-tbl tr:hover td { background: var(--dim); }

/* Census languages */
.census-langs { margin-top: 0.9rem; }
.census-langs ol { padding-left: 1.2rem; margin-top: 0.35rem; }
.census-langs li { margin-bottom: 0.15rem; }

/* Council powers */
.powers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.4rem; }
.powers-grid ul { padding-left: 1.2rem; }
.powers-grid li { margin-bottom: 0.3rem; font-size: 0.92rem; }

/* Questions */
.q-list { padding-left: 1.2rem; }
.q-list li { margin-bottom: 0.45rem; }

/* Vote info */
.vote-dl { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr));
           gap: 0.85rem; }
.vote-dl > div { background: var(--dim); border: 1px solid var(--rule); padding: 0.8rem 1rem; }
.vote-dl dt { font-weight: 700; margin-bottom: 0.25rem; font-size: 0.92rem; }
.vote-dl dd { font-size: 0.88rem; }

/* By-election note in record */
.by-election-note { border-left: 4px solid var(--accent); background: rgba(0,71,255,0.04);
                    padding: 0.45rem 0.75rem; margin-bottom: 0.9rem; font-size: 0.88rem; }

/* Compact councillor record card */
.record-card { background: var(--dim); border: 1px solid var(--rule); padding: 1rem 1.1rem; }
.record-metrics { margin: 0 0 0.7rem; }
.record-metric { display: grid; grid-template-columns: 11rem 1fr; gap: 0.4rem 0.75rem;
                 padding: 0.45rem 0; border-bottom: 1px solid var(--rule); }
.record-metric:last-child { border-bottom: none; }
.record-metric dt { font-weight: 600; font-size: 0.88rem; color: var(--ink); }
.record-metric dd { font-size: 0.92rem; margin: 0; }
.record-sup { font-family: var(--mono); font-size: 0.65rem; vertical-align: super;
              line-height: 0; color: var(--muted); }
.record-footnotes { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
                    line-height: 1.55; margin-top: 0.6rem; }
.record-detail-link { margin-top: 0.85rem; }
.record-detail-link a { display: inline-block; font-size: 0.9rem; font-weight: 600;
                        color: var(--accent); text-decoration: none; border-bottom: 1px solid; }
.record-detail-link a:hover { color: var(--ink); border-color: var(--ink); }
@media (max-width: 480px) {
  .record-metric { grid-template-columns: 1fr; gap: 0.1rem; }
}

/* Councillor detail page */
.councillor-detail { max-width: 780px; margin: 0 auto; padding: 0 1rem 3rem; }
.breadcrumb { font-size: 0.85rem; margin-bottom: 1.1rem; }
.detail-subtitle { color: var(--muted); font-size: 0.92rem; margin-top: 0.1rem;
                   margin-bottom: 0.8rem; }

/* Dot strip */
.dot-strip-block { margin: 1.8rem 0; }
.dot-strip-block h2 { margin-bottom: 0.3rem; }
.dot-strip-svg { width: 100%; max-width: 600px; display: block; margin-top: 0.5rem; }

/* Close-vote cards */
.closest-decisions { margin-top: 2rem; }
.vote-cards { display: flex; flex-direction: column; gap: 1rem; margin-top: 0.8rem; }
.vote-card { background: var(--dim); border: 1px solid var(--rule); padding: 0.9rem 1.1rem; }
.vote-card__meta { display: flex; gap: 1rem; font-family: var(--mono); font-size: 0.72rem;
                   color: var(--muted); margin-bottom: 0.3rem; letter-spacing: 0.05em; }
.vote-card__title { font-size: 0.97rem; font-weight: 600; margin: 0 0 0.4rem; line-height: 1.4; }
.vote-card__summary { font-size: 0.85rem; color: var(--muted); margin: 0 0 0.6rem; }
.vote-card__votes { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.6rem; }
.vote-row { display: grid; grid-template-columns: 13rem 8rem 1fr; gap: 0.3rem 0.6rem;
            font-size: 0.85rem; padding: 0.35rem 0; border-top: 1px solid var(--rule); }
.vote-row:first-child { border-top: none; }
.vote-row__type { font-weight: 600; }
.vote-row__cast { }
.vote-row__result { color: var(--muted); }
.other-votes { margin-top: 0.4rem; }
.other-votes summary { font-size: 0.82rem; cursor: pointer; color: var(--accent);
                       padding: 0.2rem 0; }
.vote-card__link { font-family: var(--mono); font-size: 0.72rem; margin: 0;
                   letter-spacing: 0.04em; }
.vote-card__link a { color: var(--muted); }
.vote-card__link a:hover { color: var(--accent); }
@media (max-width: 560px) {
  .vote-row { grid-template-columns: 1fr 1fr; }
  .vote-row__result { grid-column: 1 / -1; }
}

/* Notes */
.note { font-family: var(--mono); font-size: 0.72rem; color: var(--muted);
        margin-top: 0.35rem; line-height: 1.5; }

/* Site footer */
.site-footer { background: var(--dim); border-top: 2px solid var(--ink);
               padding: 2rem 1.25rem; font-size: 0.82rem; margin-top: 3rem; }
.site-footer__inner { max-width: 960px; margin: 0 auto;
                      display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
.footer-data { color: var(--muted); }
.footer-data a { color: var(--accent); }
.footer-data p { margin-bottom: 0.35rem; }
.footer-independence { border-left: 2px solid var(--accent); padding-left: 1.25rem;
                       font-size: 0.8rem; color: var(--muted); }
.independence-label { font-family: var(--sans); font-size: 0.68rem; text-transform: uppercase;
                      letter-spacing: 0.18em; color: var(--accent); font-weight: 500;
                      margin-bottom: 0.4rem; }
.independence-box { border-left: 4px solid var(--accent); padding: 0.9rem 1.1rem;
                    background: rgba(0,71,255,0.03); font-size: 0.92rem; }
.independence-box p { margin-bottom: 0.5rem; }
.independence-box p:last-child { margin-bottom: 0; }

/* Staff preview page */
.staff-page { max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
.staff-hero { border-left: 4px solid var(--accent); padding: 1.1rem 1.4rem;
              margin-bottom: 2rem; }
.staff-hero h1 { margin-top: 0.3rem; }
.staff-page section { margin-bottom: 2rem; }

/* What matters here — poll bars */
.poll-block { background: var(--dim); border: 1px solid var(--rule);
              padding: 0.9rem 1rem; margin-bottom: 1.1rem; }
.poll-bars { display: flex; flex-direction: column; gap: 0.55rem; margin: 0.65rem 0 0.5rem; }
.poll-bar-row { display: grid; grid-template-columns: 155px 1fr; gap: 0.5rem; align-items: center; }
.poll-bar-label { font-size: 0.86rem; }
.poll-bar-wrap { display: flex; align-items: center; gap: 0.45rem; }
.poll-bar { background: var(--accent); height: 20px; min-width: 4px; }
.poll-bar-pct { font-size: 0.82rem; font-weight: 600; white-space: nowrap; }

/* What matters here — issue cards */
.issue-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 0.1rem; }
.issue-card { background: var(--bg); border: 1px solid var(--rule); overflow: hidden; }
.issue-card__head { padding: 0.6rem 1rem; display: flex; align-items: center; gap: 0.55rem;
                    background: var(--ink); }
.issue-card__head h3 { margin: 0; font-family: var(--sans); font-size: 0.88rem;
                       color: var(--bg); border: none; padding: 0; font-weight: 600; }
.issue-card__pct { font-size: 1.05rem; font-weight: 700; color: var(--bg);
                   min-width: 2.8rem; text-align: right; }
.issue-card__head--traffic,
.issue-card__head--housing,
.issue-card__head--safety,
.issue-card__head--taxes   { background: var(--ink); }
.issue-card__body { padding: 0.75rem 1rem; font-size: 0.88rem; }
.issue-card__body p { margin-bottom: 0.35rem; }
.issue-card__body p:last-child { margin-bottom: 0; }

/* Sortable table header */
th[data-sort] { cursor: pointer; user-select: none; }
th[data-sort]:hover { background: #e4e8f0; }
th[data-sort]::after { content: " ⇅"; font-size: 0.7rem; color: var(--muted); }
th[data-sort].sort-asc::after  { content: " ▲"; color: var(--accent); }
th[data-sort].sort-desc::after { content: " ▼"; color: var(--accent); }

/* Responsive */
@media (max-width: 640px) {
  .ward-hero, .home-hero { grid-template-columns: 1fr; }
  .ward-hero__map, .home-hero__map { max-width: 100%; margin: 0 auto; }
  .powers-grid { grid-template-columns: 1fr; }
  .issue-cards { grid-template-columns: 1fr; }
  .poll-bar-row { grid-template-columns: 130px 1fr; }
  .site-footer__inner { grid-template-columns: 1fr; }
}
@media (max-width: 420px) {
  .stat-grid { grid-template-columns: 1fr; }
  .vote-dl { grid-template-columns: 1fr; }
}
'''


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print('Loading wards.json …')
    with open(DATA_JSON, encoding='utf-8') as f:
        data = json.load(f)

    print('Loading GeoJSON …')
    gj     = load_geojson()
    bounds = compute_bounds(gj)
    paths  = build_ward_paths(gj, bounds)
    print(f'  Bounds: lon [{bounds[0]:.3f}, {bounds[1]:.3f}] '
          f'lat [{bounds[2]:.3f}, {bounds[3]:.3f}]. '
          f'SVG height = {_svg_height(MAP_W, bounds)}')

    city_census = data.get('city_census', {})

    print('Writing style.css …')
    with open(os.path.join(DOCS, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(CSS)

    print('Writing index.html …')
    with open(os.path.join(DOCS, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(build_index(data, paths, bounds))

    print('Writing about.html …')
    with open(os.path.join(DOCS, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(build_about(data))

    if PREVIEW:
        print('Writing for-city-staff.html …')
        with open(os.path.join(DOCS, 'for-city-staff.html'), 'w', encoding='utf-8') as f:
            f.write(build_staff_page())

    print('Writing 25 ward pages …')
    for w in sorted(data['wards'], key=lambda x: x['ward_num']):
        wn = w['ward_num']
        with open(os.path.join(DOCS, f'ward-{wn}.html'), 'w', encoding='utf-8') as f:
            f.write(build_ward_page(w, paths, bounds, city_census))
        print(f'  ward-{wn}.html — {w["ward_name"]}')

    # Councillor detail pages (only if vote_summaries.csv exists)
    if VOTE_SUMMARIES:
        print('\nGenerating councillor detail pages…')
        for w in sorted(data['wards'], key=lambda x: x['ward_num']):
            wn = w['ward_num']
            with open(os.path.join(DOCS, f'councillor-ward-{wn}.html'), 'w', encoding='utf-8') as f:
                f.write(build_councillor_page(w, paths, bounds))
            print(f'  councillor-ward-{wn}.html — {w["councillor_first"]} {w["councillor_last"]}')
        total = len(data['wards']) * 2 + (4 if PREVIEW else 3)
    else:
        print('\nNote: data/vote_summaries.csv not found — skipping councillor detail pages.')
        total = len(data['wards']) + (4 if PREVIEW else 3)

    print(f'\nDone. {total} files written to docs/')


if __name__ == '__main__':
    main()
