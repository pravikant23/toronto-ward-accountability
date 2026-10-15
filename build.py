#!/usr/bin/env python3
"""
build.py — Toronto Ward Facts site generator (Phase 3).
Reads data/wards.json + data/raw/city-wards-4326.geojson
Writes docs/style.css, docs/index.html, docs/about.html, docs/ward-N.html (25 pages).
Run: python3 build.py
"""

import json
import os
import math
import html as html_lib

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
DATA_JSON = os.path.join(BASE, 'data', 'wards.json')
GEOJSON   = os.path.join(BASE, 'data', 'raw', 'city-wards-4326.geojson')
DOCS      = os.path.join(BASE, 'docs')
os.makedirs(DOCS, exist_ok=True)

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
}

CANDIDATE_QUESTIONS = [
    'What are your three priorities for this ward in the next term?',
    'How will you stay in contact with residents throughout the term?',
    'How will you approach major spending decisions at City Council?',
    'What is your view on housing affordability in this ward?',
    'How will you balance the interests of renters and homeowners?',
    'How will you work with other councillors and the Mayor to get things done?',
    'What would you protect and what would you change in the city budget?',
]

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

def city_map_svg(ward_paths, bounds, highlight=None, link_all=True):
    """Full-city outline SVG. highlight=ward_num draws that ward in dark blue."""
    h_val = _svg_height(MAP_W, bounds)
    has_hl = highlight is not None
    lines = [
        f'<svg viewBox="0 0 {MAP_W} {h_val}" xmlns="http://www.w3.org/2000/svg" '
        f'class="city-map" role="img" aria-label="Map of Toronto\'s 25 wards'
        + (f', ward {highlight} highlighted' if has_hl else '') + '">',
        '  <desc>Outline map showing all 25 Toronto municipal wards.</desc>',
    ]
    for wn in sorted(ward_paths):
        d    = ward_paths[wn]
        fill = '#1a4a7a' if wn == highlight else ('#c5d6e8' if has_hl else '#4a86c8')
        path = (f'<path d="{d}" fill="{fill}" stroke="#fff" stroke-width="0.7" '
                f'stroke-linejoin="round"><title>Ward {wn}</title></path>')
        if link_all or wn == highlight:
            lines.append(f'  <a href="ward-{wn}.html">{path}</a>')
        else:
            lines.append(f'  {path}')
    lines.append('</svg>')
    return '\n'.join(lines)


# ── HTML chrome ────────────────────────────────────────────────────────────────

def page_open(title, is_home=False):
    pt = 'Toronto Ward Facts' if is_home else f'{h(title)} | Toronto Ward Facts'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{pt}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
<a class="skip-link" href="#main">Skip to main content</a>
<header class="site-header">
  <a class="site-logo" href="index.html">Toronto Ward Facts</a>
  <nav class="site-nav" aria-label="Site navigation">
    <a href="index.html">Home</a>
    <a href="about.html">About</a>
  </nav>
</header>
<main id="main">'''

def page_close():
    return f'''</main>
<footer class="site-footer">
  <p>Data from <a href="{LINKS["voter_stats"]}">City of Toronto Open Data</a> under the
     <a href="{LINKS["licence"]}">Open Government Licence – Toronto</a>.
     Numbers last checked {CHECKED}. Corrections: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a></p>
  <p>This site is non-partisan and has no party affiliation.
     <a href="about.html">About &amp; Sources</a></p>
</footer>
</body>
</html>'''


# ── Inline SVG turnout bar chart (index page) ──────────────────────────────────

def turnout_chart_svg(wards, city_pct):
    """Horizontal bars sorted lowest → highest, city avg as dashed red line."""
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
        f'class="turnout-chart" role="img" '
        f'aria-label="2022 voter turnout by ward, sorted lowest to highest">',
        f'  <desc>Bar chart of 2022 voter turnout for each of Toronto\'s 25 wards. '
        f'City average {city_pct}% shown as a dashed red line.</desc>',
    ]
    for i, ward in enumerate(sorted_w):
        y     = i * bar_h + 8
        tp    = ward.get('turnout_pct') or 0
        bw    = max(2, round(tp / max_pct * chart_w))
        wn    = ward['ward_num']
        label = f"W{wn}"
        lines.append(
            f'  <a href="ward-{wn}.html">'
            f'<text x="{label_w - 6}" y="{y + 14}" text-anchor="end" '
            f'class="tc-label">{h(label)}</text>'
            f'<rect x="{label_w}" y="{y + 3}" width="{bw}" height="{bar_h - 8}" '
            f'fill="#4a86c8" rx="2"><title>Ward {wn}: {tp}%</title></rect>'
            f'<text x="{label_w + bw + 4}" y="{y + 14}" class="tc-pct">{tp:.1f}%</text>'
            f'</a>'
        )
    lines.append(
        f'  <line x1="{city_x}" y1="6" x2="{city_x}" y2="{total_h - 20}" '
        f'stroke="#c0392b" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'  <text x="{city_x + 3}" y="{total_h - 6}" class="tc-avg" fill="#c0392b">'
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
    w_1_in_n = w.get('winner_1_in_n')
    in_n     = f' (about 1 in every {w_1_in_n} registered voters)' if w_1_in_n else ''

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
    <h3>Top 3 non-official home languages</h3>
    {lang_html}
    <p class="note">Single-language mother-tongue responses. English and French not included.</p>
  </div>
</section>'''

def sec_record(w):
    cur = f"{w['councillor_first']} {w['councillor_last']}"
    bye = w.get('by_election')

    # Attendance
    att = w.get('attendance')
    if att and att.get('sessions_total'):
        att_pct  = att.get('attendance_pct') or 0
        present  = fmt_num(att.get('sessions_present'))
        total    = fmt_num(att.get('sessions_total'))
        avg      = fmt_pct(att.get('council_avg_pct'))
        att_html = f'''<div class="att-block">
    <p><strong>City Council attendance:</strong> {present} of {total} sessions
       ({fmt_pct(att_pct)})</p>
    <div class="bar-wrap" role="meter" aria-valuenow="{att_pct:.1f}"
         aria-valuemin="0" aria-valuemax="100" aria-label="Attendance rate gauge">
      <div class="bar-fill bar-fill--green" style="width:{min(att_pct,100):.1f}%"></div>
    </div>
    <p class="stat-sub">Council average for 2022–2026 term: {avg}</p>
  </div>'''
    else:
        att_html = '<p>Attendance data not available.</p>'

    # Budget votes
    bv_list = w.get('budget_votes', [])
    if bv_list:
        bv_rows = ''
        for bv in bv_list:
            yr      = bv.get('year', '—')
            vote    = bv.get('vote')
            result  = h(bv.get('result', '—'))
            voted_b = h(bv.get('voted_by', '—'))
            note    = ('' if bv.get('voted_by') == cur
                       else f' <span class="pred-note">(voted by {voted_b})</span>')
            bv_rows += f'<tr><td>{yr}</td><td>{vote_badge(vote)}{note}</td><td>{result}</td></tr>'
        bv_html = f'''<h3>Annual budget vote</h3>
  <p class="note">The city budget is adopted in parts. This shows the most contested part
  of each year's budget adoption vote (the sub-vote with the most votes against).</p>
  <table class="data-table" aria-label="Budget votes">
    <thead><tr><th scope="col">Year</th><th scope="col">Vote</th><th scope="col">Result</th></tr></thead>
    <tbody>{bv_rows}</tbody>
  </table>'''
    else:
        bv_html = ''

    # Close votes — filter to current councillor
    all_cv = w.get('close_votes', [])
    cur_cv = [cv for cv in all_cv if cv.get('voted_by') == cur]

    if cur_cv:
        cv_rows = ''
        for cv in sorted(cur_cv, key=lambda x: x['date'], reverse=True):
            dt     = cv['date']
            title  = cv['title']
            short  = title[:65] + ('…' if len(title) > 65 else '')
            vote   = cv.get('vote')
            result = h(cv.get('result', '—'))
            cv_rows += (f'<tr><td>{h(dt)}</td>'
                        f'<td title="{h(title)}">{h(short)}</td>'
                        f'<td>{vote_badge(vote)}</td>'
                        f'<td>{result}</td></tr>')
        cv_html = f'''<h3>Close votes — {len(cur_cv)} total (margin of 3 or fewer)</h3>
  <p class="note">City Council recorded votes where the margin between Yes and No was
  3 or fewer, with at least 10 members voting. Purely procedural motions excluded.
  Sorted most recent first.</p>
  <div class="table-scroll">
  <table class="data-table close-vote-tbl" aria-label="Close votes for this councillor">
    <thead>
      <tr><th scope="col">Date</th><th scope="col">Issue</th>
          <th scope="col">Vote</th><th scope="col">Result</th></tr>
    </thead>
    <tbody>{cv_rows}</tbody>
  </table>
  </div>'''
    else:
        cv_html = '<p>No close votes recorded for this councillor in the 2022–2026 term.</p>'

    bye_html = (f'<p class="by-election-note"><strong>Note:</strong> {h(bye)}</p>'
                if bye else '')

    return f'''<section id="record" aria-labelledby="h-record">
  <h2 id="h-record">Councillor record — 2022–2026 term</h2>
  {bye_html}
  <p>Record shown for <strong>{h(cur)}</strong>.</p>
  {att_html}
  {bv_html}
  {cv_html}
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

    map_svg  = city_map_svg(ward_paths, bounds, highlight=wn)
    bye_html = (f'<p class="by-election-strip"><strong>By-election:</strong> {h(bye)}</p>'
                if bye else '')

    page_nav = '''<nav class="page-nav" aria-label="Jump to section">
  <a href="#at-a-glance">At a glance</a>
  <a href="#results">2022 Results</a>
  <a href="#census">Census</a>
  <a href="#record">Councillor record</a>
  <a href="#council-powers">Council powers</a>
  <a href="#questions">Questions</a>
  <a href="#vote-2026">How to vote</a>
  <a href="#sources">Sources</a>
</nav>'''

    return '\n'.join([
        page_open(f'Ward {wn} — {name}'),
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

    map_svg   = city_map_svg(ward_paths, bounds, link_all=True)
    chart_svg = turnout_chart_svg(wards, city22['turnout_pct'])

    tbl_rows = ''.join(
        f'<tr>'
        f'<td><a href="ward-{w["ward_num"]}.html">Ward {w["ward_num"]}</a></td>'
        f'<td>{h(w.get("ward_name",""))}</td>'
        f'<td>{h(w["councillor_first"])} {h(w["councillor_last"])}</td>'
        f'<td>{fmt_pct(w.get("turnout_pct"))}</td>'
        f'</tr>'
        for w in sorted(wards, key=lambda x: x['ward_num'])
    )

    return '\n'.join([
        page_open('Toronto Ward Facts', is_home=True),
        f'''<div class="home-hero">
  <div class="home-hero__text">
    <h1>Toronto Ward Facts</h1>
    <p class="lead">Official data on all 25 Toronto wards — voter turnout, 2022 election
       results, census profiles, and councillor voting records. Non-partisan. Sourced
       entirely from City of Toronto open data.</p>
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
  <p>Select a ward bar to go to its full data page. Dashed red line = city average.</p>
  <div class="chart-scroll">{chart_svg}</div>
</section>

<section id="ward-list" aria-labelledby="h-wards">
  <h2 id="h-wards">All 25 wards</h2>
  <table class="data-table ward-dir-tbl" aria-label="All 25 Toronto wards">
    <thead>
      <tr>
        <th scope="col">Ward</th>
        <th scope="col">Name</th>
        <th scope="col">Current councillor</th>
        <th scope="col">2022 turnout</th>
      </tr>
    </thead>
    <tbody>{tbl_rows}</tbody>
  </table>
</section>''',
        page_close(),
    ])


def build_about(data):
    city22 = data['city_2022']
    return '\n'.join([
        page_open('About this site'),
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
    </tbody>
  </table>
  <p class="note">All data published under the
     <a href="{LINKS["licence"]}">Open Government Licence – Toronto</a>.</p>
</section>

<section aria-labelledby="h-formula">
  <h2 id="h-formula">Turnout formula</h2>
  <p><strong>Turnout % = (Number Voted + Declined Ballots) ÷ Total Eligible Electors × 100</strong></p>
  <p>This matches the City's own definition in the voter statistics file.
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

<section aria-labelledby="h-contact">
  <h2 id="h-contact">Contact and corrections</h2>
  <p>Corrections: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a></p>
  <p>This site is non-partisan and is not affiliated with any candidate, party, or the City of Toronto.</p>
</section>''',
        page_close(),
    ])


# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = ''':root {
  --clr-primary: #1a4a7a;
  --clr-accent:  #0062a3;
  --clr-bg:      #f5f7fa;
  --clr-card:    #ffffff;
  --clr-text:    #1a1a1a;
  --clr-muted:   #666;
  --clr-border:  #d8dde3;
  --clr-bar:     #4a86c8;
  --clr-yes:     #1a5c38;
  --clr-no:      #8b1f1f;
  --clr-absent:  #666;
  --clr-green:   #2d6a4f;
  --radius:      6px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif;
       background: var(--clr-bg); color: var(--clr-text); line-height: 1.6;
       font-size: 1rem; }
a { color: var(--clr-accent); }
a:focus-visible { outline: 3px solid var(--clr-accent); outline-offset: 2px; }

/* Skip link */
.skip-link { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
.skip-link:focus { position: fixed; left: 0; top: 0; width: auto; height: auto;
                   padding: 0.5rem 1rem; background: var(--clr-primary); color: #fff;
                   z-index: 9999; font-weight: bold; }

/* Site header */
.site-header { background: var(--clr-primary); color: #fff; padding: 0.7rem 1.25rem;
               display: flex; justify-content: space-between; align-items: center;
               flex-wrap: wrap; gap: 0.5rem; }
.site-logo { color: #fff; text-decoration: none; font-weight: 700; font-size: 1.05rem; }
.site-nav a { color: #b8d0e8; text-decoration: none; margin-left: 1.25rem; font-size: 0.9rem; }
.site-nav a:hover { color: #fff; }

/* Main */
main { max-width: 960px; margin: 0 auto; padding: 1.25rem 1rem 3rem; }

/* Ward hero */
.ward-hero { display: grid; grid-template-columns: 1fr auto; gap: 1.5rem;
             align-items: start; padding: 1.5rem 0 1rem;
             border-bottom: 2px solid var(--clr-border); margin-bottom: 1.5rem; }
.ward-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em;
              color: var(--clr-muted); }
.ward-hero h1 { font-size: clamp(1.4rem, 4vw, 2rem); color: var(--clr-primary);
                margin: 0.2rem 0 0.4rem; }
.councillor-line { font-size: 1rem; }
.ward-hero__map { max-width: 220px; width: 100%; }
.by-election-strip { background: #fef9e6; border-left: 4px solid #d4ac0d;
                     padding: 0.45rem 0.75rem; margin-top: 0.6rem;
                     border-radius: 0 var(--radius) var(--radius) 0; font-size: 0.88rem; }

/* Home hero */
.home-hero { display: grid; grid-template-columns: 1fr auto; gap: 1.5rem;
             align-items: start; padding: 1.5rem 0 1rem;
             border-bottom: 2px solid var(--clr-border); margin-bottom: 2rem; }
.home-hero h1 { font-size: clamp(1.5rem, 4vw, 2.1rem); color: var(--clr-primary);
                margin-bottom: 0.5rem; }
.home-hero__map { max-width: 300px; width: 100%; }
.lead { font-size: 1rem; margin-bottom: 0.7rem; }
.btn { display: inline-block; background: var(--clr-primary); color: #fff;
       padding: 0.5rem 1.2rem; border-radius: var(--radius); text-decoration: none;
       font-weight: 600; margin-top: 0.7rem; }
.btn:hover { background: var(--clr-accent); }

/* Section nav */
.page-nav { display: flex; flex-wrap: wrap; gap: 0.35rem 0.9rem; margin-bottom: 1.75rem;
            padding: 0.55rem 0; border-top: 1px solid var(--clr-border);
            border-bottom: 1px solid var(--clr-border); }
.page-nav a { font-size: 0.82rem; color: var(--clr-accent); text-decoration: none; }
.page-nav a:hover { text-decoration: underline; }

/* Sections */
section { margin-bottom: 2.5rem; }
h2 { font-size: 1.2rem; color: var(--clr-primary); border-bottom: 2px solid var(--clr-border);
     padding-bottom: 0.3rem; margin-bottom: 0.9rem; }
h3 { font-size: 0.97rem; color: var(--clr-primary); margin: 1.1rem 0 0.45rem; }

/* Stat grid */
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
             gap: 0.85rem; }
.stat-item { background: var(--clr-card); border: 1px solid var(--clr-border);
             border-radius: var(--radius); padding: 0.8rem 1rem; }
.stat-item dt { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em;
                color: var(--clr-muted); margin-bottom: 0.2rem; }
.stat-item dd { font-size: 1.05rem; font-weight: 600; }
.stat-sub { display: block; font-size: 0.77rem; font-weight: 400; color: var(--clr-muted);
            margin-top: 0.12rem; }

/* Progress bars */
.bar-wrap { background: #dde5ee; border-radius: 4px; height: 9px; margin-top: 0.4rem;
            overflow: hidden; }
.bar-fill { background: var(--clr-bar); height: 100%; border-radius: 4px; }
.bar-fill--green { background: var(--clr-green); }

/* Candidate table */
.cand-table { width: 100%; border-collapse: collapse; margin-top: 0.6rem; }
.cand-table th { background: #e5eaf0; text-align: left; padding: 0.4rem 0.55rem;
                 font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
.cand-table td { padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--clr-border);
                 vertical-align: middle; }
.winner-row td { background: #eaf1fb; font-weight: 600; }
.winner-badge { background: var(--clr-primary); color: #fff; font-size: 0.62rem;
                font-weight: 700; padding: 0.12rem 0.35rem; border-radius: 3px;
                margin-left: 0.45rem; vertical-align: middle; }
.cand-name { min-width: 140px; }
.cand-votes { text-align: right; white-space: nowrap; }
.cand-bar-cell { min-width: 160px; }
.cand-bar-wrap { position: relative; background: #dde5ee; height: 20px;
                 border-radius: 3px; overflow: hidden; }
.cand-bar { position: absolute; top: 0; left: 0; height: 100%; background: var(--clr-bar); }
.winner-row .cand-bar { background: var(--clr-primary); }
.cand-pct { position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
            font-size: 0.77rem; font-weight: 600; }

/* Turnout chart */
.chart-scroll { overflow-x: auto; margin-top: 0.75rem; }
.turnout-chart { min-width: 420px; width: 100%; max-width: 760px; display: block; }
.tc-label { font-size: 9px; fill: #444; }
.tc-pct   { font-size: 9px; fill: #666; }
.tc-avg   { font-size: 9px; }

/* City map */
.city-map { width: 100%; height: auto; display: block; }
.city-map a:hover path { opacity: 0.8; }

/* Attendance block */
.att-block { background: var(--clr-card); border: 1px solid var(--clr-border);
             border-radius: var(--radius); padding: 0.9rem 1rem; margin-bottom: 0.9rem; }

/* Vote badges */
.vote-yes    { color: var(--clr-yes);    font-weight: 700; }
.vote-no     { color: var(--clr-no);     font-weight: 700; }
.vote-absent { color: var(--clr-absent); }
.vote-na     { color: var(--clr-muted);  }
.pred-note   { font-size: 0.77rem; color: var(--clr-muted); font-weight: 400; }

/* Generic data table */
.data-table { width: 100%; border-collapse: collapse; margin-top: 0.6rem; font-size: 0.9rem; }
.data-table th { background: #e5eaf0; text-align: left; padding: 0.4rem 0.55rem;
                 font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
.data-table td { padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--clr-border);
                 vertical-align: top; }
.data-table tr:last-child td { border-bottom: none; }

/* Close vote table */
.table-scroll { overflow-x: auto; }
.close-vote-tbl td:nth-child(2) { max-width: 260px; overflow: hidden;
                                   text-overflow: ellipsis; white-space: nowrap; }

/* Ward directory */
.ward-dir-tbl tr:hover td { background: #edf2f7; }

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
.vote-dl > div { background: var(--clr-card); border: 1px solid var(--clr-border);
                 border-radius: var(--radius); padding: 0.8rem 1rem; }
.vote-dl dt { font-weight: 700; margin-bottom: 0.25rem; font-size: 0.92rem; }
.vote-dl dd { font-size: 0.88rem; }

/* By-election note in record */
.by-election-note { background: #fef9e6; border-left: 4px solid #d4ac0d;
                    padding: 0.45rem 0.75rem; margin-bottom: 0.9rem;
                    border-radius: 0 var(--radius) var(--radius) 0; font-size: 0.88rem; }

/* Notes */
.note { font-size: 0.77rem; color: var(--clr-muted); margin-top: 0.35rem; }

/* Site footer */
.site-footer { background: var(--clr-primary); color: #b8d0e8; padding: 1.4rem 1.25rem;
               font-size: 0.82rem; text-align: center; margin-top: 3rem; }
.site-footer a { color: #8ebcd8; }
.site-footer p { margin-bottom: 0.35rem; }

/* Responsive */
@media (max-width: 640px) {
  .ward-hero, .home-hero { grid-template-columns: 1fr; }
  .ward-hero__map, .home-hero__map { max-width: 100%; margin: 0 auto; }
  .powers-grid { grid-template-columns: 1fr; }
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

    print('Writing 25 ward pages …')
    for w in sorted(data['wards'], key=lambda x: x['ward_num']):
        wn = w['ward_num']
        with open(os.path.join(DOCS, f'ward-{wn}.html'), 'w', encoding='utf-8') as f:
            f.write(build_ward_page(w, paths, bounds, city_census))
        print(f'  ward-{wn}.html — {w["ward_name"]}')

    total = len(data['wards']) + 3  # wards + index + about + style
    print(f'\nDone. {total} files written to docs/')


if __name__ == '__main__':
    main()
