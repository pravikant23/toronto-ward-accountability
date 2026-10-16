#!/usr/bin/env python3
"""
data/generate_summaries.py
Generates data/vote_summaries.csv — one neutral summary sentence per close-vote item.
Source: Agenda Item Titles already stored in data/wards.json (from council-voting-2022-2026.csv).

TMMIS (secure.toronto.ca) blocks server-side HTTP requests, so summaries are derived
from the official item title in the voting CSV. The source_text column preserves the
exact title so reviewers can verify accuracy. Edit the summary column as needed, then
run build.py to generate docs/councillor-ward-N.html.

Run: python3 data/generate_summaries.py
"""

import csv, json, os, re

BASE     = os.path.dirname(os.path.abspath(__file__))
WARDS_JS = os.path.join(BASE, 'wards.json')
OUT_CSV  = os.path.join(BASE, 'vote_summaries.csv')

# ── Collect unique items from close_votes ──────────────────────────────────────

with open(WARDS_JS, encoding='utf-8') as f:
    data = json.load(f)

items = {}  # item_num -> title
for w in data['wards']:
    for cv in (w.get('close_votes') or []):
        items[cv['item']] = cv['title']

print(f'Found {len(items)} unique agenda items across all 25 wards.')

# ── Summary generator ──────────────────────────────────────────────────────────

_TRIM_SUFFIXES = [
    ' - Ontario Land Tribunal Hearing - Request for Directions',
    ' - OLT Hearing - Request for Directions',
    ' - Request for Directions',
    ' - Decision Report - Approval',
    ' - Decision Report',
    ' - Approval',
    ' - Final Report',
    ' - Staff Report',
    ' - Phase Two Work Plan',
    ': Evaluation Findings',
]

def _strip_mover(title):
    """Remove '- by Councillor X, seconded by ...' from title. Returns (clean_title, mover|None)."""
    m = re.search(r'\s*-\s*by Councillor ([A-Za-z\' -]+?)(?:,.*)?$', title)
    if m:
        mover = m.group(1).strip()
        return title[:m.start()].strip(), mover
    return title, None


def summarize(item_num, title):
    """Return (summary_sentence, source_text_used)."""
    t = title.strip()
    source = t

    t, mover = _strip_mover(t)

    for suffix in _TRIM_SUFFIXES:
        if t.endswith(suffix):
            t = t[:-len(suffix)].strip()

    # Address-based planning application detection
    _addr_re = re.compile(
        r'\d+\s+(?:and\s+\d+\s+)?[A-Z][A-Za-z ]+(?:Road|Street|Avenue|Drive|Boulevard|'
        r'Way|Court|Crescent|Place|Lane|Terrace|Circle|Gate|Trail|Park|Square)',
        re.IGNORECASE,
    )
    is_address = bool(_addr_re.search(t))

    if mover:
        summary = f'A motion by Councillor {mover}: {t}.'
    elif is_address:
        summary = f'A planning decision regarding {t}.'
    elif t.lower().startswith('appointment of '):
        summary = f'A vote on the {t[0].lower() + t[1:]}.'
    elif t.lower().startswith('implementing '):
        rest = t[len('Implementing '):]
        summary = f'A proposal to implement {rest}.'
    elif t.lower().startswith('expanding '):
        rest = t[len('Expanding '):]
        summary = f'A proposal to expand {rest}.'
    elif t.lower().startswith('regarding '):
        rest = t[len('Regarding '):]
        summary = f'A vote regarding {rest}.'
    elif t.lower().startswith('request for '):
        rest = t[len('Request for '):]
        summary = f'A request for {rest}.'
    elif t.lower().startswith('request to '):
        rest = t[len('Request to '):]
        summary = f'A request to {rest}.'
    elif t.lower().startswith('protecting '):
        summary = f'A proposal to protect {t[len("Protecting "):]}.'
    elif t.lower().startswith('respecting '):
        summary = f'A vote on respecting {t[len("Respecting "):]}.'
    elif t.lower().startswith('prioritization of '):
        summary = f'A vote on prioritizing {t[len("Prioritization of "):]}.'
    elif 'Ombudsman' in t:
        summary = f'An Ombudsman Toronto report: {t}.'
    elif 'Audit' in t and ('Reinforcing' in t or 'Audit' == t[:5]):
        summary = f'An auditor general report: {t}.'
    elif t.startswith('FIFA '):
        summary = f'A city planning measure for {t}.'
    elif t.lower().startswith('review of '):
        rest = t[len('Review of '):]
        summary = f'A review of {rest}.'
    elif t.lower().startswith('update on ') or t.lower().startswith('updates on '):
        rest = re.sub(r'^[Uu]pdates? on ', '', t)
        summary = f'A council update on {rest}.'
    elif ' Update' in t and not t.startswith('2026'):
        summary = f'A council update: {t}.'
    elif 'Financial' in t and ('Plan' in t or 'Outlook' in t or 'Update' in t):
        summary = f'A vote on the city financial report: {t}.'
    elif 'Legislative' in t or 'Bill' in t:
        summary = f'A vote on legislative changes: {t}.'
    elif 'Getting to the Root' in t:
        summary = f'A performance report: {t}.'
    elif 'Billy Bishop' in t or 'Airport' in t:
        summary = f'A decision regarding Billy Bishop Toronto City Airport.'
    elif 'Ontario Science Centre' in t:
        summary = f'A vote on the Ontario Science Centre: {t}.'
    elif t.lower().startswith('cold weather'):
        summary = f'A report on {t[0].lower() + t[1:]}.'
    elif 'Data on' in t:
        summary = f'A report on {t.replace("Data on ", "").lower()}.'
    else:
        summary = f'A vote on: {t}.'

    # Ensure ends with single period
    summary = summary.rstrip('.') + '.'

    return summary, source


# ── Write CSV ──────────────────────────────────────────────────────────────────

FIELDS = ['item_num', 'title', 'summary', 'source_text', 'official_url']

rows = []
for item_num in sorted(items):
    title   = items[item_num]
    summary, source = summarize(item_num, title)
    url     = f'https://secure.toronto.ca/council/agenda-item.do?item={item_num}'
    rows.append({
        'item_num':    item_num,
        'title':       title,
        'summary':     summary,
        'source_text': source,
        'official_url': url,
    })

with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)

print(f'Wrote {OUT_CSV}\n')
print(f'{"#":<3} {"item_num":<18} {"summary":<90}')
print('─' * 115)
for i, r in enumerate(rows, 1):
    print(f'{i:<3} {r["item_num"]:<18} {r["summary"][:88]}')

print(f'\n{len(rows)} items total.')
print('\nReview and edit the "summary" column as needed.')
print('Forbidden words: attempt, blocked, pushed, controversial, rejected, failed.')
print('Run build.py after editing to generate docs/councillor-ward-N.html.')
