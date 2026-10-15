#!/usr/bin/env python3
"""
build.py – Toronto Ward Facts static site generator
Reads data/wards.json → writes docs/
Run: python3 build.py
"""
import json, os, html

BASE    = os.path.dirname(os.path.abspath(__file__))
DATA    = os.path.join(BASE, "data", "wards.json")
DOCS    = os.path.join(BASE, "docs")
CHECKED = "October 15, 2026"

# Official City of Toronto links (verified 2026-10-15)
LINKS = {
    "candidates":       "https://www.toronto.ca/city-government/elections/candidate-list/",
    "myvote":           "https://myvote.toronto.ca/home",
    "voter_info":       "https://www.toronto.ca/city-government/elections/voter-information/",
    "advance_voting":   "https://www.toronto.ca/city-government/elections/voter-information/voting-options/",
    "id_requirements":  "https://www.toronto.ca/city-government/elections/voter-information/acceptable-identification/",
    "find_my_ward":     "https://myvote.toronto.ca/home",
    "open_data_turnout":"https://open.toronto.ca/dataset/elections-voter-statistics/",
    "open_data_results":"https://open.toronto.ca/dataset/election-results-official/",
    "open_data_officials":"https://open.toronto.ca/dataset/elected-officials-contact-information/",
}

os.makedirs(DOCS, exist_ok=True)

with open(DATA) as f:
    data = json.load(f)

city   = data["city"]
wards  = data["wards"]
city_t = city["turnout_pct"]


# ── CSS ────────────────────────────────────────────────────────────────────
CSS = """\
/* Toronto Ward Facts – single stylesheet */
:root {
  --accent:  #003F8A;   /* City of Toronto blue */
  --accent2: #C8102E;   /* election red for bar highlight */
  --text:    #111;
  --muted:   #555;
  --border:  #ddd;
  --bg:      #fff;
  --bar-bg:  #e8eef7;
  font-size: 16px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}
a { color: var(--accent); }
a:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }

.site-header {
  background: var(--accent);
  color: #fff;
  padding: 1.25rem 1.5rem;
}
.site-header a { color: #fff; text-decoration: none; font-weight: 600; }
.site-header .subtitle { font-size: .85rem; opacity: .85; margin-top: .15rem; }

main { max-width: 900px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }

h1 { font-size: 1.75rem; margin-bottom: .5rem; }
h2 { font-size: 1.3rem; margin: 2rem 0 .75rem; border-bottom: 2px solid var(--accent); padding-bottom: .25rem; }
h3 { font-size: 1.05rem; margin: 1.25rem 0 .4rem; }

/* stat blocks */
.stats-grid { display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }
.stat {
  flex: 1 1 160px;
  background: var(--bar-bg);
  border-left: 4px solid var(--accent);
  padding: .75rem 1rem;
  border-radius: 4px;
}
.stat .num { font-size: 2rem; font-weight: 700; color: var(--accent); line-height: 1.1; }
.stat .label { font-size: .8rem; color: var(--muted); margin-top: .15rem; }

/* ward grid on homepage */
.ward-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: .6rem;
  margin: 1rem 0;
}
.ward-card {
  display: block;
  padding: .6rem .8rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  text-decoration: none;
  color: var(--text);
  transition: border-color .15s, background .15s;
}
.ward-card:hover, .ward-card:focus-visible {
  border-color: var(--accent);
  background: var(--bar-bg);
}
.ward-card .ward-num { font-size: .7rem; color: var(--muted); }
.ward-card .ward-name { font-size: .88rem; font-weight: 600; margin-top: .1rem; }
.ward-card .ward-turnout { font-size: .78rem; color: var(--muted); }

/* inline SVG chart */
.chart-wrap { overflow-x: auto; margin: 1rem 0; }
svg text { font-family: inherit; }

/* ward-page specifics */
.by-election-note {
  background: #fff8e1;
  border-left: 4px solid #f0a500;
  padding: .6rem 1rem;
  margin: .5rem 0 1rem;
  font-size: .9rem;
  border-radius: 3px;
}

/* vote bar */
.vote-bar-wrap { margin: .75rem 0; }
.vote-bar-track {
  height: 24px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}
.vote-bar-voted   { background: var(--accent);  }
.vote-bar-novote  { background: var(--border);   }
.vote-bar-label {
  display: flex; justify-content: space-between;
  font-size: .78rem; color: var(--muted); margin-top: .3rem;
}

/* candidate table */
table { border-collapse: collapse; width: 100%; margin: .5rem 0; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--border); font-size: .9rem; }
th { background: var(--bar-bg); font-weight: 600; }
td:last-child { white-space: nowrap; }

/* result bar inside table */
.result-bar {
  display: inline-block;
  height: 12px;
  background: var(--accent);
  border-radius: 2px;
  vertical-align: middle;
  margin-right: .4rem;
  min-width: 2px;
}

/* action links */
.action-links { list-style: none; padding: 0; margin: .5rem 0; }
.action-links li { margin: .4rem 0; }
.action-links a { font-weight: 600; }

/* source footnote */
.source-note {
  font-size: .75rem;
  color: var(--muted);
  margin-top: .3rem;
  border-top: 1px solid var(--border);
  padding-top: .3rem;
}
.source-note a { color: var(--muted); }

.page-footer {
  margin-top: 3rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
  font-size: .8rem;
  color: var(--muted);
}

@media (max-width: 600px) {
  h1 { font-size: 1.35rem; }
  .stat .num { font-size: 1.6rem; }
}
"""

with open(os.path.join(DOCS, "style.css"), "w") as f:
    f.write(CSS)
print("Wrote style.css")


# ── helpers ────────────────────────────────────────────────────────────────
def fmt_num(n):
    return f"{n:,}"

def h(s):
    return html.escape(str(s))

def header(title, subtitle="", back=False, is_home=False):
    back_link = '<a href="index.html">← All Wards</a> · ' if back else ""
    page_title = title if is_home else f"{title} – Toronto Ward Facts"
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(page_title)}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site-header">
  <div>{back_link}<a href="index.html">Toronto Ward Facts</a></div>
  <div class="subtitle">Official numbers for every ward, before you vote on Oct 26</div>
</header>
<main>
<h1>{h(title)}</h1>
{('<p>' + h(subtitle) + '</p>') if subtitle else ''}
"""

def footer():
    return f"""\
<div class="page-footer">
  <p>
    Data from <a href="https://open.toronto.ca/" target="_blank" rel="noopener">City of Toronto Open Data</a> under the
    <a href="https://open.toronto.ca/open-data-licence/" target="_blank" rel="noopener">Open Government Licence – Toronto</a>.
    Data last checked: {CHECKED}. Corrections: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a>
    · <a href="about.html">About &amp; Sources</a>
  </p>
</div>
</main>
</body>
</html>
"""


# ── SVG bar chart ──────────────────────────────────────────────────────────
def svg_chart(wards_sorted, city_avg):
    W = 860
    BAR_H = 22
    GAP   = 4
    LABEL_W = 200
    BAR_MAX_W = W - LABEL_W - 60
    max_pct = max(w["turnout_pct"] for w in wards_sorted)
    rows = len(wards_sorted)
    H = rows * (BAR_H + GAP) + 40

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'role="img" aria-label="Turnout bar chart for all 25 wards">',
             f'<title>2022 voter turnout by ward, sorted ascending</title>']

    avg_x = LABEL_W + int(city_avg / max_pct * BAR_MAX_W)

    for i, ward in enumerate(wards_sorted):
        y = i * (BAR_H + GAP)
        bar_w = max(2, int(ward["turnout_pct"] / max_pct * BAR_MAX_W))
        is_above = ward["turnout_pct"] >= city_avg
        fill = "#003F8A" if is_above else "#6699cc"
        name_short = ward["ward_name"] if len(ward["ward_name"]) <= 22 else ward["ward_name"][:20] + "…"
        label = f"W{ward['ward_num']}: {name_short}"
        lines.append(
            f'<text x="{LABEL_W-6}" y="{y+16}" text-anchor="end" font-size="11" fill="#333">{h(label)}</text>'
            f'<rect x="{LABEL_W}" y="{y+4}" width="{bar_w}" height="{BAR_H-8}" fill="{fill}" rx="2"/>'
            f'<text x="{LABEL_W+bar_w+4}" y="{y+16}" font-size="11" fill="#333">{ward["turnout_pct"]:.1f}%</text>'
        )

    # city average line
    lines.append(
        f'<line x1="{avg_x}" y1="0" x2="{avg_x}" y2="{H-20}" stroke="#C8102E" stroke-width="2" stroke-dasharray="5,3"/>'
        f'<text x="{avg_x+4}" y="{H-6}" font-size="11" fill="#C8102E">City avg {city_avg:.1f}%</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


# ── INDEX PAGE ─────────────────────────────────────────────────────────────
wards_sorted = sorted(wards, key=lambda w: w["turnout_pct"])

idx_parts = [header("Toronto Ward Facts",
                     "Official 2022 voter turnout and election results for all 25 wards. "
                     "Vote on Monday, October 26, 2026.",
                     is_home=True)]

idx_parts.append('<h2>City-Wide Totals – 2022 Municipal Election</h2>')
idx_parts.append('<div class="stats-grid">')
idx_parts.append(f'<div class="stat"><div class="num">{fmt_num(city["registered_voters"])}</div>'
                 f'<div class="label">Registered voters</div></div>')
idx_parts.append(f'<div class="stat"><div class="num">{fmt_num(city["ballots_cast"])}</div>'
                 f'<div class="label">Ballots cast</div></div>')
idx_parts.append(f'<div class="stat"><div class="num">{city["turnout_pct"]:.1f}%</div>'
                 f'<div class="label">Voter turnout</div></div>')
idx_parts.append('</div>')
idx_parts.append(f'<p class="source-note">Source: <a href="{LINKS["open_data_turnout"]}" target="_blank" rel="noopener">City of Toronto Open Data – Voter Statistics (2022)</a>. '
                 f'Turnout = (ballots cast including declined ballots) ÷ total eligible electors. '
                 f'Data last checked: {CHECKED}.</p>')

idx_parts.append('<h2>Turnout by Ward (2022, sorted low → high)</h2>')
idx_parts.append(f'<p>Dark bars are at or above the city average ({city_t:.1f}%). Red line = city average.</p>')
idx_parts.append('<div class="chart-wrap">')
idx_parts.append(svg_chart(wards_sorted, city_t))
idx_parts.append('</div>')

idx_parts.append('<h2>All 25 Wards</h2>')
idx_parts.append(f'<p>Don\'t know your ward? <a href="{LINKS["find_my_ward"]}" target="_blank" rel="noopener">Find it on MyVote ↗</a></p>')
idx_parts.append('<div class="ward-grid">')
for ward in wards:
    by = " (by-election)" if ward["by_election"] else ""
    idx_parts.append(
        f'<a class="ward-card" href="ward-{ward["ward_num"]}.html">'
        f'<div class="ward-num">Ward {ward["ward_num"]}</div>'
        f'<div class="ward-name">{h(ward["ward_name"])}</div>'
        f'<div class="ward-turnout">{ward["turnout_pct"]:.1f}% turnout · {h(ward["councillor_name"])}{h(by)}</div>'
        f'</a>'
    )
idx_parts.append('</div>')

idx_parts.append(footer())
with open(os.path.join(DOCS, "index.html"), "w") as f:
    f.write("".join(idx_parts))
print("Wrote index.html")


# ── WARD PAGES ─────────────────────────────────────────────────────────────
for ward in wards:
    w       = ward["ward_num"]
    name    = ward["ward_name"]
    cllr    = ward["councillor_name"]
    t_pct   = ward["turnout_pct"]
    reg     = ward["registered_voters"]
    ballots = ward["ballots_cast"]
    cands   = ward["candidates_2022"]
    total_v = ward["total_votes_2022"]
    n_cands = ward["total_candidates_2022"]
    be      = ward["by_election"]

    parts = [header(f"Ward {w}: {name}", back=True)]

    # ── Section 1: councillor ──────────────────────────────────────────────
    parts.append('<h2>Current Councillor</h2>')
    parts.append(f'<p><strong><a href="{h(ward["councillor_website"])}" target="_blank" rel="noopener">'
                 f'{h(cllr)}</a></strong></p>')
    if be:
        parts.append(
            f'<div class="by-election-note">'
            f'<strong>Note:</strong> {h(be["note"])}'
            f'</div>'
        )
    parts.append(f'<p class="source-note">Source: <a href="{LINKS["open_data_officials"]}" '
                 f'target="_blank" rel="noopener">City of Toronto Open Data – Elected Officials Contact Information '
                 f'(2022–2026)</a>. Data last checked: {CHECKED}.</p>')

    # ── Section 2: who voted in 2022 ──────────────────────────────────────
    parts.append('<h2>Who Voted in 2022</h2>')
    parts.append('<div class="stats-grid">')
    parts.append(f'<div class="stat"><div class="num">{fmt_num(reg)}</div>'
                 f'<div class="label">Registered voters</div></div>')
    parts.append(f'<div class="stat"><div class="num">{fmt_num(ballots)}</div>'
                 f'<div class="label">Ballots cast</div></div>')
    parts.append(f'<div class="stat"><div class="num">{t_pct:.1f}%</div>'
                 f'<div class="label">Ward turnout vs {city_t:.1f}% city-wide</div></div>')
    parts.append('</div>')

    voted_pct  = min(100, t_pct)
    novote_pct = 100 - voted_pct
    voted_bar_w  = int(voted_pct / 100 * 100)
    novote_bar_w = 100 - voted_bar_w

    parts.append('<div class="vote-bar-wrap">')
    parts.append(f'<div role="img" aria-label="Bar showing {t_pct:.1f}% voted, {100-t_pct:.1f}% did not vote">'
                 f'<div class="vote-bar-track">'
                 f'<div class="vote-bar-voted" style="width:{voted_bar_w}%" title="{t_pct:.1f}% voted"></div>'
                 f'<div class="vote-bar-novote" style="width:{novote_bar_w}%"></div>'
                 f'</div>'
                 f'<div class="vote-bar-label">'
                 f'<span>{t_pct:.1f}% voted</span>'
                 f'<span>{100-t_pct:.1f}% did not vote</span>'
                 f'</div></div>')
    parts.append('</div>')
    parts.append(f'<p class="source-note">Source: <a href="{LINKS["open_data_turnout"]}" '
                 f'target="_blank" rel="noopener">City of Toronto Open Data – Voter Statistics (2022)</a>. '
                 f'Turnout = (ballots cast including declined ballots) ÷ total eligible electors. '
                 f'Data last checked: {CHECKED}.</p>')

    # ── Section 3: 2022 results ────────────────────────────────────────────
    parts.append('<h2>2022 Election Results (Councillor)</h2>')
    top5   = cands[:5]
    others = cands[5:]
    parts.append(f'<p>{n_cands} candidates · {fmt_num(total_v)} total votes cast</p>')
    parts.append('<table><thead><tr><th>Candidate</th><th>Votes</th><th>Share</th></tr></thead><tbody>')
    for i, c in enumerate(top5):
        bar_w = int(c["pct"] / 100 * 120)
        winner_mark = " ✓" if i == 0 else ""
        parts.append(
            f'<tr><td>{h(c["name"])}{h(winner_mark)}</td>'
            f'<td>{fmt_num(c["votes"])}</td>'
            f'<td><span class="result-bar" style="width:{bar_w}px" aria-hidden="true"></span>{c["pct"]:.1f}%</td></tr>'
        )
    if others:
        others_total = sum(c["votes"] for c in others)
        others_pct   = round(others_total / total_v * 100, 1) if total_v else 0
        parts.append(
            f'<tr><td><em>{len(others)} other candidates</em></td>'
            f'<td>{fmt_num(others_total)}</td>'
            f'<td>{others_pct:.1f}%</td></tr>'
        )
    parts.append('</tbody></table>')

    if be:
        parts.append(f'<p><strong>Current councillor elected in {be["date"]} by-election.</strong> '
                     f'The 2022 results above are for the general election that year.</p>')

    parts.append(f'<p class="source-note">Source: <a href="{LINKS["open_data_results"]}" '
                 f'target="_blank" rel="noopener">City of Toronto Open Data – Elections – Official Results (2022)</a>, '
                 f'file 2022_Toronto_Poll_By_Poll_Councillor.xlsx. Data last checked: {CHECKED}.</p>')

    # ── Section 4: vote on Oct 26 ──────────────────────────────────────────
    parts.append('<h2>Vote on Monday, October 26, 2026</h2>')
    parts.append('<ul class="action-links">')
    parts.append(f'<li><a href="{LINKS["candidates"]}" target="_blank" rel="noopener">'
                 f'2026 Candidate list (all wards) ↗</a> – Official City of Toronto candidate list</li>')
    parts.append(f'<li><a href="{LINKS["myvote"]}" target="_blank" rel="noopener">'
                 f'MyVote – Confirm you\'re on the voters\' list, find your polling location ↗</a></li>')
    parts.append(f'<li><a href="{LINKS["advance_voting"]}" target="_blank" rel="noopener">'
                 f'Voting options &amp; advance voting dates ↗</a></li>')
    parts.append(f'<li><a href="{LINKS["id_requirements"]}" target="_blank" rel="noopener">'
                 f'Acceptable identification (ID requirements) ↗</a></li>')
    parts.append('</ul>')
    parts.append('<p>All links go to official City of Toronto pages (toronto.ca or myvote.toronto.ca).</p>')

    parts.append(footer())
    out_path = os.path.join(DOCS, f"ward-{w}.html")
    with open(out_path, "w") as f:
        f.write("".join(parts))

print("Wrote 25 ward pages")


# ── ABOUT PAGE ─────────────────────────────────────────────────────────────
about_parts = [header("About Toronto Ward Facts")]
about_parts.append("""
<p>Toronto Ward Facts is a non-partisan, static website that presents official City of
Toronto data about the 2022 municipal election for each of Toronto's 25 wards.
Every number on this site comes directly from a City of Toronto open-data file.
Nothing has been estimated or modelled.</p>

<h2>What this site shows</h2>
<ul>
  <li>2022 voter turnout by ward (registered voters, ballots cast, turnout %).</li>
  <li>2022 official councillor results: top 5 candidates with vote counts and percentages.</li>
  <li>Current councillor, with a note where a by-election changed the seat after 2022.</li>
  <li>Links to the City's 2026 candidate list and voter tools – no candidate names or
      promises are copied here.</li>
</ul>

<h2>Data Sources</h2>
<table>
  <thead><tr><th>Data</th><th>Source</th></tr></thead>
  <tbody>
""")
about_parts.append(f"""\
    <tr>
      <td>Voter turnout (registered voters, ballots cast, turnout %)</td>
      <td><a href="{LINKS['open_data_turnout']}" target="_blank" rel="noopener">
          City of Toronto Open Data – Elections – Voter Statistics</a><br>
          File: 2022_voter_turnout_statistics_final.xlsx (resource 631b7042)</td>
    </tr>
    <tr>
      <td>2022 vote counts per candidate per ward</td>
      <td><a href="{LINKS['open_data_results']}" target="_blank" rel="noopener">
          City of Toronto Open Data – Elections – Official Results</a><br>
          File: 2022_Toronto_Poll_By_Poll_Councillor.xlsx (resource 3ad371de)</td>
    </tr>
    <tr>
      <td>Current councillor names and websites</td>
      <td><a href="{LINKS['open_data_officials']}" target="_blank" rel="noopener">
          City of Toronto Open Data – Elected Officials Contact Information</a><br>
          File: 2022-2026-elected-officials-contact-info.json (resource 161c66b5)</td>
    </tr>
    <tr>
      <td>By-election results (Wards 15, 20, 25)</td>
      <td><a href="https://open.toronto.ca/dataset/elections-official-by-election-results/" target="_blank" rel="noopener">
          City of Toronto Open Data – Elections Official By-Election Results</a> and
          <a href="https://www.toronto.ca/city-government/elections/election-results-reports/election-results/by-election-results/"
             target="_blank" rel="noopener">City of Toronto By-Election Results page</a></td>
    </tr>
    <tr>
      <td>2026 candidate list, voter tools</td>
      <td><a href="https://www.toronto.ca/city-government/elections/" target="_blank" rel="noopener">
          City of Toronto Elections</a></td>
    </tr>
  </tbody>
</table>
""")
about_parts.append(f"""
<h2>How Numbers Are Calculated</h2>
<h3>Registered voters</h3>
<p>The "Total Eligible Electors" column from the voter statistics file, summed across
all voting subdivisions (1–96) within each ward. Subdivisions 97 (mail-in), 98 and 99
(advance vote locations) do not carry their own eligible-elector count – those voters
are already counted in their home subdivisions – so they are excluded from the eligible
total to avoid double-counting.</p>

<h3>Ballots cast</h3>
<p>The sum of "Number Voted" and "Declined Ballots" from all subdivisions (including
97, 98, 99), per ward. This matches the City's own definition of turnout in the file's
readme tab.</p>

<h3>Turnout %</h3>
<p>Ballots cast ÷ Registered voters × 100, rounded to two decimal places.
Formula as described in the file's readme: "Percentage of voters that voted.
Number Voted plus Declined Ballots divide by Total Eligible Electors."</p>

<h3>Candidate percentages</h3>
<p>Each candidate's votes ÷ total votes cast in that ward (councillor race only) × 100.
The "Total" column from the City's poll-by-poll spreadsheet is used directly.</p>

<h2>By-Election Notes</h2>
<ul>
  <li><strong>Ward 15 Don Valley West:</strong> Jaye Robinson won the 2022 general election.
      She resigned. Rachel Chernos Lin won the <strong>November 4, 2024 by-election</strong>
      (source: <a href="https://www.toronto.ca/wp-content/uploads/2024/11/9727-Declaration-of-Results-for-the-Councillor-Ward-15-ByElectionfor-posting.pdf"
      target="_blank" rel="noopener">City Clerk's Declaration of Results</a>).</li>
  <li><strong>Ward 20 Scarborough Southwest:</strong> Gary Crawford won the 2022 general election.
      He resigned. Parthi Kandavel won the <strong>November 30, 2023 by-election</strong>
      (source: <a href="https://www.toronto.ca/wp-content/uploads/2023/12/94c0-Declaration-of-Results-for-the-Councillor-Ward-20-ByElection-Final.pdf"
      target="_blank" rel="noopener">City Clerk's Declaration of Results</a>).</li>
  <li><strong>Ward 25 Scarborough-Rouge Park:</strong> Jennifer McKelvie won the 2022 general election.
      She resigned. Neethan Shan won the <strong>September 29, 2025 by-election</strong>
      (source: <a href="https://www.toronto.ca/wp-content/uploads/2025/09/97f1-Declaration-of-Results-Councillor-Ward-25-ByElection.pdf"
      target="_blank" rel="noopener">City Clerk's Declaration of Results</a>).</li>
</ul>

<h2>Limitations</h2>
<ul>
  <li>All turnout data is from the 2022 general election. Ward populations and eligible
      voter counts change year to year.</li>
  <li>This site does not show 2026 candidates or results (those become available from
      the City's open data after election night).</li>
  <li>Candidate name formatting follows the City's own files (last name first in some
      fields); this site reproduces the names as they appear in the official data.</li>
</ul>

<h2>Contact</h2>
<p>To report a factual error: <a href="mailto:ravi@perimtr.ca">ravi@perimtr.ca</a></p>

<h2>Data Last Checked</h2>
<p>{CHECKED}</p>
""")
about_parts.append(footer())

with open(os.path.join(DOCS, "about.html"), "w") as f:
    f.write("".join(about_parts))
print("Wrote about.html")
print(f"\nDone. Output in {DOCS}/")
