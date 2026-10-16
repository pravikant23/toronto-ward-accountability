#!/usr/bin/env python3
"""
data/councillor_metrics.py
Calculates verified metrics for every City Council member who served 2022–2026.
Produces data/councillor_metrics.csv.

Hard-fail test answers (independently computed):
  unique recorded votes : 1,718
  final-decision votes  : 707
  contested final dec.  : 191
  Gord Perks      : contested_cast=185, with_majority=80.5%, with_mayor=85.2%
  Stephen Holyday : contested_cast=191, with_majority=30.4%, with_mayor=22.7%
  Amber Morley    : contested_cast=187, with_majority=93.0%, with_mayor=95.2%
  Neethan Shan    : contested_cast= 49, with_majority=91.8%, with_mayor=89.1%
  with_mayor range (current members): 22.7%–95.2%
"""

import csv, os, sys
from collections import defaultdict

BASE     = os.path.dirname(os.path.abspath(__file__))
VOTE_CSV = os.path.join(BASE, 'raw', 'council-voting-2022-2026.csv')
ATT_CSV  = os.path.join(BASE, 'raw', 'council-attendance-2022-2026.csv')
OUT_CSV  = os.path.join(BASE, 'councillor_metrics.csv')

# Members who left before the 2026 election (predecessors + resigned mayor)
NON_CURRENT = {'John Tory', 'Jaye Robinson', 'Gary Crawford', 'Jennifer McKelvie'}


def fail(msg):
    print(f'FAIL: {msg}', file=sys.stderr)
    sys.exit(1)


def pct(num, den, decimals=1):
    return round(num / den * 100, decimals) if den else None


# ── Load voting CSV (City Council only) ────────────────────────────────────────

print('Loading council-voting-2022-2026.csv …')
all_rows = []
with open(VOTE_CSV, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['Committee'].strip() == 'City Council':
            all_rows.append(row)

# Group rows by unique vote key
vote_groups: dict = defaultdict(list)
for r in all_rows:
    key = (r['Date/Time'], r['Agenda Item #'], r['Vote Description'])
    vote_groups[key].append(r)

total_unique = len(vote_groups)

# Final-decision votes: motion type Adopt Item or Adopt Item as Amended
final_keys = {
    k for k, grp in vote_groups.items()
    if grp[0]['Motion Type'] in ('Adopt Item', 'Adopt Item as Amended')
}

# Contested final decisions: >= 3 members voted No
contested_keys = {
    k for k in final_keys
    if sum(1 for r in vote_groups[k] if r['Vote'] == 'No') >= 3
}

# ── Hard-fail structural checks ─────────────────────────────────────────────────

if total_unique != 1718:
    fail(f'Expected 1,718 unique votes, got {total_unique}')
if len(final_keys) != 707:
    fail(f'Expected 707 final-decision votes, got {len(final_keys)}')
if len(contested_keys) != 191:
    fail(f'Expected 191 contested final decisions, got {len(contested_keys)}')

print(f'  unique votes={total_unique}, final-decision={len(final_keys)}, contested={len(contested_keys)} ✓')

# Olivia Chow's contested votes (for with_mayor_pct)
chow_votes: dict = {}
for k in contested_keys:
    for r in vote_groups[k]:
        if r['First Name'].strip() == 'Olivia' and r['Last Name'].strip() == 'Chow':
            if r['Vote'] in ('Yes', 'No'):
                chow_votes[k] = r['Vote']
print(f'  Chow contested Yes/No cast: {len(chow_votes)}')

# ── Collect members in order of first appearance ───────────────────────────────

members_seen: dict = {}   # fullname -> (first, last, first_dt)
for r in all_rows:
    fn, ln = r['First Name'].strip(), r['Last Name'].strip()
    fullname = f'{fn} {ln}'
    if fullname not in members_seen:
        members_seen[fullname] = (fn, ln, r['Date/Time'][:10])

# ── Per-member vote metrics ────────────────────────────────────────────────────

def member_row_in_vote(key, fn, ln):
    for r in vote_groups[key]:
        if r['First Name'].strip() == fn and r['Last Name'].strip() == ln:
            return r
    return None


print('Computing per-member vote metrics …')
vote_metrics: dict = {}

for fullname, (fn, ln, _) in members_seen.items():
    my_rows = [
        r for r in all_rows
        if r['First Name'].strip() == fn and r['Last Name'].strip() == ln
    ]

    votes_eligible = len(my_rows)
    votes_missed   = sum(1 for r in my_rows if r['Vote'] == 'Absent')
    votes_ai       = sum(1 for r in my_rows if r['Vote'] == 'Absent(Interest Declared)')
    votes_cast     = votes_eligible - votes_missed - votes_ai

    dates      = sorted(r['Date/Time'][:10] for r in my_rows)
    first_vote = dates[0]  if dates else None
    last_vote  = dates[-1] if dates else None

    # Contested final-decision metrics
    contested_cast  = 0
    majority_match  = majority_total = 0
    mayor_match     = mayor_total    = 0
    exclude_mayor   = fullname in ('Olivia Chow', 'John Tory')

    for k in contested_keys:
        r = member_row_in_vote(k, fn, ln)
        if r is None:
            continue
        v = r['Vote']
        if v not in ('Yes', 'No'):
            continue   # Absent / Absent(Interest Declared)

        contested_cast  += 1
        majority_total  += 1
        carried = 'Carried' in r['Result']
        if (v == 'Yes' and carried) or (v == 'No' and not carried):
            majority_match += 1

        if not exclude_mayor and k in chow_votes:
            mayor_total += 1
            if v == chow_votes[k]:
                mayor_match += 1

    with_majority = pct(majority_match, majority_total)
    with_mayor    = pct(mayor_match, mayor_total) if (not exclude_mayor and mayor_total > 0) else None

    vote_metrics[fullname] = {
        'fn': fn, 'ln': ln,
        'votes_eligible':    votes_eligible,
        'votes_cast':        votes_cast,
        'votes_missed':      votes_missed,
        'votes_ai':          votes_ai,
        'first_vote':        first_vote,
        'last_vote':         last_vote,
        'contested_cast':    contested_cast,
        'majority_match':    majority_match,
        'majority_total':    majority_total,
        'with_majority_pct': with_majority,
        'mayor_match':       mayor_match,
        'mayor_total':       mayor_total,
        'with_mayor_pct':    with_mayor,
    }

# ── Hard-fail member checks ────────────────────────────────────────────────────

def check_member(fullname, exp_cast, exp_majority, exp_mayor):
    m = vote_metrics.get(fullname)
    if m is None:
        fail(f'{fullname} not found in voting data')
    if m['contested_cast'] != exp_cast:
        fail(f'{fullname}: contested_cast={m["contested_cast"]}, expected {exp_cast}')
    if m['with_majority_pct'] != exp_majority:
        fail(f'{fullname}: with_majority_pct={m["with_majority_pct"]}, expected {exp_majority}')
    if m['with_mayor_pct'] != exp_mayor:
        fail(f'{fullname}: with_mayor_pct={m["with_mayor_pct"]}, expected {exp_mayor}')
    print(f'  {fullname}: {exp_cast} | {exp_majority}% | {exp_mayor}% ✓')


print('Verifying test answers …')
check_member('Gord Perks',      185, 80.5, 85.2)
check_member('Stephen Holyday', 191, 30.4, 22.7)
check_member('Amber Morley',    187, 93.0, 95.2)
check_member('Neethan Shan',     49, 91.8, 89.1)

current_mayor_pcts = [
    vote_metrics[fn]['with_mayor_pct']
    for fn in vote_metrics
    if fn not in NON_CURRENT and vote_metrics[fn]['with_mayor_pct'] is not None
]
range_min = min(current_mayor_pcts)
range_max = max(current_mayor_pcts)
if range_min != 22.7 or range_max != 95.2:
    fail(f'with_mayor range (current): {range_min}%–{range_max}%, expected 22.7%–95.2%')
print(f'  with_mayor range (current members): {range_min}%–{range_max}% ✓')

# ── Load attendance CSV (City Council only) ────────────────────────────────────

print('\nLoading council-attendance-2022-2026.csv …')
sessions_present: dict = defaultdict(int)
sessions_total:   dict = defaultdict(int)

with open(ATT_CSV, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['Committee'].strip() != 'City Council':
            continue
        fullname = f"{row['First Name'].strip()} {row['Last Name'].strip()}"
        sessions_total[fullname]   += 1
        if row['Present'].strip().upper() == 'Y':
            sessions_present[fullname] += 1

att_pcts = []
att_metrics: dict = {}
for fullname in members_seen:
    tot = sessions_total.get(fullname, 0)
    pre = sessions_present.get(fullname, 0)
    ap  = round(pre / tot * 100, 1) if tot else None
    att_metrics[fullname] = {
        'sessions_present': pre,
        'sessions_total':   tot,
        'attendance_pct':   ap,
    }
    if ap is not None:
        att_pcts.append(ap)

council_avg_att = round(sum(att_pcts) / len(att_pcts), 1) if att_pcts else None

# Verify Perks: 252/259 = 97.3%
pa = att_metrics['Gord Perks']
if pa['sessions_present'] != 252 or pa['sessions_total'] != 259:
    fail(f"Perks attendance {pa['sessions_present']}/{pa['sessions_total']}, expected 252/259")
if pa['attendance_pct'] != 97.3:
    fail(f"Perks attendance_pct={pa['attendance_pct']}, expected 97.3")
print(f"  Gord Perks attendance: {pa['sessions_present']}/{pa['sessions_total']} = {pa['attendance_pct']}% ✓")

if council_avg_att != 92.1:
    fail(f'Council avg attendance={council_avg_att}, expected 92.1')
print(f'  Council avg attendance: {council_avg_att}% ✓')

print('\nAll hard-fail checks PASSED.')

# ── Write CSV ──────────────────────────────────────────────────────────────────

FIELDS = [
    'fullname', 'is_current',
    'sessions_present', 'sessions_total', 'attendance_pct', 'council_avg_att',
    'votes_eligible', 'votes_cast', 'votes_missed', 'votes_ai',
    'first_vote', 'last_vote',
    'contested_cast',
    'with_majority_pct', 'majority_n',
    'with_mayor_pct',    'mayor_n',
]

with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    for fullname in sorted(members_seen):
        vm = vote_metrics[fullname]
        am = att_metrics.get(fullname, {})
        w.writerow({
            'fullname':          fullname,
            'is_current':        'N' if fullname in NON_CURRENT else 'Y',
            'sessions_present':  am.get('sessions_present', ''),
            'sessions_total':    am.get('sessions_total', ''),
            'attendance_pct':    am.get('attendance_pct', ''),
            'council_avg_att':   council_avg_att,
            'votes_eligible':    vm['votes_eligible'],
            'votes_cast':        vm['votes_cast'],
            'votes_missed':      vm['votes_missed'],
            'votes_ai':          vm['votes_ai'],
            'first_vote':        vm['first_vote'],
            'last_vote':         vm['last_vote'],
            'contested_cast':    vm['contested_cast'],
            'with_majority_pct': '' if vm['with_majority_pct'] is None else vm['with_majority_pct'],
            'majority_n':        vm['majority_total'],
            'with_mayor_pct':    '' if vm['with_mayor_pct'] is None else vm['with_mayor_pct'],
            'mayor_n':           vm['mayor_total'],
        })

print(f'\nWrote {OUT_CSV}')

# ── Print full table ───────────────────────────────────────────────────────────

HDR = (
    f"{'Name':<22}  {'Cur':>3}  {'Att%':>5}  {'Elig':>5}  {'Cast':>5}  "
    f"{'Miss':>5}  {'AI':>3}  {'ConTest':>7}  {'Maj%':>5}  {'MajN':>4}  "
    f"{'Mayor%':>6}  {'MayN':>4}  {'First':>10}  {'Last':>10}"
)
SEP = '─' * len(HDR)

print(f'\n{"=" * len(HDR)}')
print('COUNCILLOR METRICS — 2022–2026 TERM')
print(f'{"=" * len(HDR)}')
print(HDR)
print(SEP)

for fullname in sorted(members_seen):
    vm = vote_metrics[fullname]
    am = att_metrics.get(fullname, {})
    is_cur  = 'N' if fullname in NON_CURRENT else 'Y'
    att     = f"{am.get('attendance_pct', '—')}" if am.get('attendance_pct') is not None else '—'
    maj_s   = f"{vm['with_majority_pct']}" if vm['with_majority_pct'] is not None else '—'
    may_s   = f"{vm['with_mayor_pct']}"    if vm['with_mayor_pct']    is not None else '—'
    print(
        f"{fullname:<22}  {is_cur:>3}  {att:>5}  "
        f"{vm['votes_eligible']:>5}  {vm['votes_cast']:>5}  "
        f"{vm['votes_missed']:>5}  {vm['votes_ai']:>3}  "
        f"{vm['contested_cast']:>7}  {maj_s:>5}  {vm['majority_total']:>4}  "
        f"{may_s:>6}  {vm['mayor_total']:>4}  "
        f"{vm['first_vote']:>10}  {vm['last_vote']:>10}"
    )

print(SEP)
print(
    f"{'(council avg)':>22}  {'—':>3}  {council_avg_att:>5.1f}  "
    f"{'—':>5}  {'—':>5}  {'—':>5}  {'—':>3}  {'—':>7}  "
    f"{'—':>5}  {'—':>4}  {'—':>6}  {'—':>4}  {'—':>10}  {'—':>10}"
)
print(f'\nwith_mayor range (current members, n≥1): {range_min}%–{range_max}%')
print(f'Contested final decisions total: {len(contested_keys)}')
print(f"Chow's contested Yes/No votes used for with_mayor: {len(chow_votes)}")
