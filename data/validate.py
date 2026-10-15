#!/usr/bin/env python3
"""
data/validate.py
Hard-fail validation of data/wards.json against source files.
The build must FAIL if any check fails.
Run after build_data.py.
"""

import json
import os
import sys
import random
import openpyxl
from collections import Counter

BASE     = os.path.dirname(os.path.abspath(__file__))
RAW      = os.path.join(BASE, "raw")
OUT_JSON = os.path.join(BASE, "wards.json")

VOTER_2022   = os.path.join(RAW, "2022_voter_turnout_statistics_final.xlsx")
RESULTS_2022 = os.path.join(RAW, "2022-results", "2022_Toronto_Poll_By_Poll_Councillor.xlsx")

PASS_COUNT = 0
FAIL_COUNT = 0


def ok(msg):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  PASS  {msg}")


def fail(msg):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  FAIL  {msg}", file=sys.stderr)


# ── Load wards.json ────────────────────────────────────────────────────────────
with open(OUT_JSON, encoding="utf-8") as f:
    data = json.load(f)

wards = data["wards"]

print("=== Structural checks ===")

# 1. Exactly 25 wards
if len(wards) == 25:
    ok(f"Exactly 25 wards found")
else:
    fail(f"Expected 25 wards, got {len(wards)}")

# 2. Ward numbers 1–25 with no duplicates
ward_nums = [w["ward_num"] for w in wards]
if sorted(ward_nums) == list(range(1, 26)):
    ok("Ward numbers 1–25, no duplicates")
else:
    missing  = sorted(set(range(1, 26)) - set(ward_nums))
    extra    = sorted(set(ward_nums) - set(range(1, 26)))
    fail(f"Ward numbers wrong — missing: {missing}, extra: {extra}")

# 3. Exactly one winner per ward
print("\n=== Winner checks ===")
for w in wards:
    winners = [c for c in w["candidates_2022"] if c.get("is_winner")]
    if len(winners) == 1:
        ok(f"Ward {w['ward_num']:>2}: exactly one winner ({winners[0]['name']})")
    else:
        fail(f"Ward {w['ward_num']:>2}: {len(winners)} winners")

# 4. Candidate vote sum ≤ ballots_cast
print("\n=== Vote count checks ===")
for w in wards:
    total_cand_votes = sum(c["votes"] for c in w["candidates_2022"])
    ballots          = w["ballots_cast"] or 0
    if total_cand_votes <= ballots:
        ok(
            f"Ward {w['ward_num']:>2}: candidate votes ({total_cand_votes:,}) "
            f"≤ ballots cast ({ballots:,})"
        )
    else:
        fail(
            f"Ward {w['ward_num']:>2}: candidate votes ({total_cand_votes:,}) "
            f"> ballots cast ({ballots:,})"
        )

# 5. Our computed turnout matches city's published turnout within 0.1 pt
print("\n=== Turnout accuracy checks ===")
for w in wards:
    reg = w["registered_voters"]
    bc  = w["ballots_cast"]
    tp  = w["turnout_pct"]
    if reg and bc and tp is not None:
        computed = round(bc / reg * 100, 2)
        diff     = abs(computed - tp)
        if diff <= 0.1:
            ok(f"Ward {w['ward_num']:>2}: turnout {tp}% matches computed {computed}% (diff={diff:.2f})")
        else:
            fail(
                f"Ward {w['ward_num']:>2}: turnout {tp}% ≠ computed {computed}% "
                f"(diff={diff:.4f})"
            )
    else:
        fail(f"Ward {w['ward_num']:>2}: missing registration or ballots data")

# 6. City-level turnout = 29.68%
print("\n=== City-level check ===")
city = data.get("city_2022", {})
city_tp = city.get("turnout_pct")
if city_tp == 29.68:
    ok(f"City 2022 turnout = {city_tp}% (matches expected 29.68%)")
else:
    fail(f"City 2022 turnout = {city_tp}%, expected 29.68%")

city_reg = city.get("registered_voters")
city_bc  = city.get("ballots_cast")
if city_reg == 1_898_750 and city_bc == 563_563:
    ok(f"City 2022 registered={city_reg:,}, ballots={city_bc:,} match expected values")
else:
    fail(
        f"City 2022 totals: registered={city_reg:,} (exp 1,898,750), "
        f"ballots={city_bc:,} (exp 563,563)"
    )

# 7. No null/zero placeholders for critical fields
print("\n=== Null/zero checks ===")
REQUIRED_NONZERO = [
    "registered_voters",
    "ballots_cast",
    "turnout_pct",
    "turnout_2018_pct",
    "winner_votes",
    "num_candidates",
]
for w in wards:
    for field in REQUIRED_NONZERO:
        val = w.get(field)
        if val is None:
            fail(f"Ward {w['ward_num']:>2}: {field} is None")
        elif val == 0:
            fail(f"Ward {w['ward_num']:>2}: {field} is zero")
        else:
            ok(f"Ward {w['ward_num']:>2}: {field} = {val}")

# 8. Census data not null for each ward
print("\n=== Census null checks ===")
CENSUS_REQUIRED = [
    "population_2021",
    "median_age_2021",
    "pct_owned",
    "pct_rented",
    "median_household_income_2020",
]
for w in wards:
    cen = w.get("census", {})
    for field in CENSUS_REQUIRED:
        val = cen.get(field)
        if val is None:
            fail(f"Ward {w['ward_num']:>2}: census.{field} is None")
        else:
            ok(f"Ward {w['ward_num']:>2}: census.{field} = {val}")

# 9. By-election wards have by_election note; others don't
print("\n=== By-election flag checks ===")
BY_ELECTION_WARDS = {15, 20, 25}
for w in wards:
    wn  = w["ward_num"]
    bye = w.get("by_election")
    if wn in BY_ELECTION_WARDS:
        if bye:
            ok(f"Ward {wn:>2}: has by_election note")
        else:
            fail(f"Ward {wn:>2}: missing by_election note (expected one)")
    else:
        if bye is None:
            ok(f"Ward {wn:>2}: no by_election note (correct)")
        else:
            fail(f"Ward {wn:>2}: unexpected by_election note: {bye}")

# 10. Spot-check 3 random wards against raw source files
print("\n=== Spot-check (3 random wards vs raw source) ===")
random.seed(42)
spot_wards = random.sample(range(1, 26), 3)

# Load raw voter 2022 for spot check
wb_vt = openpyxl.load_workbook(VOTER_2022, read_only=True, data_only=True)
ws_vt = wb_vt["2022 Voter Turnout Statistics"]
raw_eligible = {}
raw_voted    = {}
raw_declined = {}
current_ward = None
for i, row in enumerate(ws_vt.iter_rows(values_only=True)):
    if i == 0:
        continue
    wc = row[0]
    sc = row[1]
    if isinstance(wc, int):
        current_ward = wc
    if current_ward is None:
        continue
    try:
        sub_num = int(sc)
    except (TypeError, ValueError):
        continue
    if 1 <= sub_num <= 96:
        raw_eligible[current_ward] = raw_eligible.get(current_ward, 0) + (row[13] or 0)
    raw_voted[current_ward]    = raw_voted.get(current_ward, 0)    + (row[14] or 0)
    raw_declined[current_ward] = raw_declined.get(current_ward, 0) + (row[17] or 0)

# Load raw results 2022 for spot check
wb_res = openpyxl.load_workbook(RESULTS_2022, read_only=True, data_only=True)
raw_winner_votes = {}
for sheet_name in wb_res.sheetnames:
    if not sheet_name.startswith("Ward "):
        continue
    try:
        wn = int(sheet_name.split()[1])
    except (IndexError, ValueError):
        continue
    ws_r = wb_res[sheet_name]
    rows = list(ws_r.iter_rows(values_only=True))
    cands = []
    for row in rows[3:]:
        nc, vc = row[0], row[-1]
        if nc and vc and isinstance(vc, (int, float)):
            ns = str(nc).strip()
            if ns and "Totals" not in ns:
                cands.append(int(vc))
    if cands:
        raw_winner_votes[wn] = max(cands)

for wn in spot_wards:
    wd      = next(w for w in wards if w["ward_num"] == wn)
    exp_reg = int(raw_eligible.get(wn, 0))
    exp_bc  = int(raw_voted.get(wn, 0) + raw_declined.get(wn, 0))
    exp_wv  = raw_winner_votes.get(wn)

    if wd["registered_voters"] == exp_reg:
        ok(f"Ward {wn:>2}: registered_voters {exp_reg:,} matches raw file")
    else:
        fail(
            f"Ward {wn:>2}: registered_voters {wd['registered_voters']:,} "
            f"≠ raw {exp_reg:,}"
        )

    if wd["ballots_cast"] == exp_bc:
        ok(f"Ward {wn:>2}: ballots_cast {exp_bc:,} matches raw file")
    else:
        fail(
            f"Ward {wn:>2}: ballots_cast {wd['ballots_cast']:,} "
            f"≠ raw {exp_bc:,}"
        )

    if exp_wv is not None and wd["winner_votes"] == exp_wv:
        ok(f"Ward {wn:>2}: winner_votes {exp_wv:,} matches raw file")
    elif exp_wv is not None:
        fail(
            f"Ward {wn:>2}: winner_votes {wd['winner_votes']:,} "
            f"≠ raw {exp_wv:,}"
        )

# ── Final result ───────────────────────────────────────────────────────────────
print()
print(f"{'=' * 50}")
print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
print(f"{'=' * 50}")

if FAIL_COUNT > 0:
    print("\nBUILD FAILED — fix errors above before proceeding.", file=sys.stderr)
    sys.exit(1)
else:
    print("\nAll checks passed. wards.json is valid.")
