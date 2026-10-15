#!/usr/bin/env python3
"""
data/add_key_votes.py
Adds budget votes and close votes per councillor to data/wards.json.
Run after build_data.py (wards.json must already exist).
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date

BASE      = os.path.dirname(os.path.abspath(__file__))
VOTE_CSV  = os.path.join(BASE, "raw", "council-voting-2022-2026.csv")
OUT_JSON  = os.path.join(BASE, "wards.json")

# ── Budget final-adoption items (one per year) ────────────────────────────────
# The final budget vote is "Adopt Item as Amended" on the CC item.
# We pick the most contested sub-vote (most No votes).
BUDGET_CC_ITEMS = {
    2023: "2023.CC4.1",
    2024: "2024.CC15.1",
    2025: "2025.CC27.1",
    2026: "2026.CC38.1",
}

# ── Councillor history per ward (for wards with by-elections) ─────────────────
# format: {ward_num: [(csv_full_name, start_date, end_date), ...]}
# end_date=None means still serving
WARD_COUNCILLOR_HISTORY = {
    15: [
        ("Jaye Robinson",    date(2022, 11, 15), date(2024, 11,  4)),
        ("Rachel Chernos Lin", date(2024, 11,  4), None),
    ],
    20: [
        ("Gary Crawford",    date(2022, 11, 15), date(2023, 11, 30)),
        ("Parthi Kandavel",  date(2023, 11, 30), None),
    ],
    25: [
        ("Jennifer McKelvie", date(2022, 11, 15), date(2025,  9, 29)),
        ("Neethan Shan",      date(2025,  9, 29), None),
    ],
}

# Procedural motions to exclude from close votes display
PROCEDURAL_EXCLUDE = {"Extend the Meeting", "Amend the Order Paper"}


# ── Load vote CSV into structures ─────────────────────────────────────────────

def load_votes():
    """
    Returns rows_by_item and vote_groups.
      rows_by_item: {agenda_item_num: [row, ...]}
      vote_groups:  {(date, item, motion_type, vote_description): [row, ...]}
    """
    rows_by_item = defaultdict(list)
    vote_groups  = defaultdict(list)

    with open(VOTE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Committee"].strip() != "City Council":
                continue
            rows_by_item[row["Agenda Item #"]].append(row)
            key = (
                row["Date/Time"][:10],
                row["Agenda Item #"],
                row["Motion Type"],
                row["Vote Description"],
            )
            vote_groups[key].append(row)

    return rows_by_item, vote_groups


def pick_budget_vote(rows_by_item, item_num):
    """
    From a budget CC item, pick the key 'Adopt Item as Amended' sub-vote:
    the one with the most No votes (most contested = actual budget passage).
    Returns list of rows for that sub-vote, or [] if not found.
    """
    all_rows = rows_by_item.get(item_num, [])
    adopt_rows = [r for r in all_rows if r["Motion Type"] == "Adopt Item as Amended"]
    if not adopt_rows:
        return []

    # Group by Vote Description to find individual sub-votes
    by_vd = defaultdict(list)
    for r in adopt_rows:
        by_vd[r["Vote Description"]].append(r)

    # Pick the sub-vote with the most No votes (most contested)
    best_vd, best_no = None, -1
    for vd, rows in by_vd.items():
        no_count = sum(1 for r in rows if r["Vote"] == "No")
        if no_count > best_no:
            best_no = no_count
            best_vd = vd

    return by_vd.get(best_vd, [])


def find_close_votes(vote_groups):
    """
    Returns list of (date, item_num, mt, vd, yes, no, result, title, rows)
    for all City Council votes with margin ≤ 3 and at least 10 votes cast.
    Excludes purely procedural motion types.
    """
    close = []
    for (dt, item_num, mt, vd), rows in vote_groups.items():
        if mt in PROCEDURAL_EXCLUDE:
            continue
        yes = sum(1 for r in rows if r["Vote"] == "Yes")
        no  = sum(1 for r in rows if r["Vote"] == "No")
        if yes + no >= 10 and abs(yes - no) <= 3:
            result = rows[0]["Result"]
            title  = rows[0]["Agenda Item Title"]
            close.append((dt, item_num, mt, vd, yes, no, result, title, rows))

    close.sort(key=lambda x: x[0])
    return close


def councillor_vote(rows, full_name):
    """Return 'Yes', 'No', 'Absent', or None for a councillor in a vote group."""
    first_q, last_q = full_name.split(" ", 1) if " " in full_name else (full_name, "")
    for r in rows:
        if r["First Name"].strip() == first_q and r["Last Name"].strip() == last_q:
            return r["Vote"]
    return None


def councillors_for_ward(ward_doc):
    """
    Returns list of (csv_full_name, start_date, end_date) for a ward.
    For most wards: [(current_councillor, 2022-11-15, None)].
    For by-election wards: uses WARD_COUNCILLOR_HISTORY.
    """
    wn = ward_doc["ward_num"]
    if wn in WARD_COUNCILLOR_HISTORY:
        return WARD_COUNCILLOR_HISTORY[wn]
    # Regular ward: councillor served the full term
    name = f"{ward_doc['councillor_first']} {ward_doc['councillor_last']}"
    return [(name, date(2022, 11, 15), None)]


def councillor_for_date(history, vote_date_str):
    """Given councillor history list and a date string, return csv_full_name."""
    vd = date.fromisoformat(vote_date_str)
    for name, start, end in history:
        if start <= vd and (end is None or vd < end):
            return name
    # Fallback: last councillor in history
    return history[-1][0]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Loading wards.json …")
    with open(OUT_JSON, encoding="utf-8") as f:
        data = json.load(f)

    print("Loading council voting CSV …")
    rows_by_item, vote_groups = load_votes()

    # ── Budget votes ───────────────────────────────────────────────────────────
    print("Extracting budget adoption votes …")
    budget_vote_sets = {}   # year -> rows of the key Adopt sub-vote
    budget_meta = {}        # year -> {date, item, item_title, result}
    for yr, item_num in BUDGET_CC_ITEMS.items():
        rows = pick_budget_vote(rows_by_item, item_num)
        if not rows:
            print(f"  WARNING: no Adopt Item as Amended found for {yr} ({item_num})",
                  file=sys.stderr)
            continue
        yes = sum(1 for r in rows if r["Vote"] == "Yes")
        no  = sum(1 for r in rows if r["Vote"] == "No")
        result  = rows[0]["Result"]
        title   = rows[0]["Agenda Item Title"]
        vote_dt = rows[0]["Date/Time"][:10]
        budget_vote_sets[yr] = rows
        budget_meta[yr] = {
            "year":       yr,
            "date":       vote_dt,
            "item":       item_num,
            "item_title": title,
            "result":     result,
            "yes_count":  yes,
            "no_count":   no,
        }
        print(f"  {yr}: {item_num} {vote_dt} → {result} (Y={yes} N={no})")

    # ── Close votes ────────────────────────────────────────────────────────────
    print("Extracting close votes …")
    close_votes = find_close_votes(vote_groups)
    print(f"  Found {len(close_votes)} close votes (margin ≤ 3, n ≥ 10)")

    # ── Enrich each ward ───────────────────────────────────────────────────────
    print("Enriching wards …")
    for ward_doc in data["wards"]:
        history = councillors_for_ward(ward_doc)

        # Budget votes: per-year, find who voted and how
        budget_votes_out = []
        for yr in sorted(budget_vote_sets):
            meta = budget_meta[yr]
            rows = budget_vote_sets[yr]
            name = councillor_for_date(history, meta["date"])
            vote = councillor_vote(rows, name)
            budget_votes_out.append({
                **meta,
                "voted_by":    name,
                "vote":        vote,   # "Yes" / "No" / "Absent" / None
            })
        ward_doc["budget_votes"] = budget_votes_out

        # Close votes: for each, find the ward's councillor at that time and their vote
        close_votes_out = []
        for dt, item_num, mt, vd, yes, no, result, title, rows in close_votes:
            name  = councillor_for_date(history, dt)
            vote  = councillor_vote(rows, name)
            if vote is None:
                # Councillor not in the vote record → absent or not yet serving
                vote = "Not recorded"
            close_votes_out.append({
                "date":            dt,
                "item":            item_num,
                "title":           title,
                "motion_type":     mt,
                "vote_description": vd,
                "yes_count":       yes,
                "no_count":        no,
                "result":          result,
                "voted_by":        name,
                "vote":            vote,
            })
        ward_doc["close_votes"] = close_votes_out

    # ── Write back ─────────────────────────────────────────────────────────────
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nUpdated {OUT_JSON}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    print(f"{'W':>2}  {'Councillor':<22}  {'2023':>5}  {'2024':>5}  {'2025':>5}  {'2026':>5}  {'Close (Y/N/other)':>20}")
    print("─" * 80)
    for ward_doc in data["wards"]:
        bv   = {b["year"]: b["vote"] for b in ward_doc.get("budget_votes", [])}
        cv   = ward_doc.get("close_votes", [])
        name = f"{ward_doc['councillor_first']} {ward_doc['councillor_last']}"
        # Count close votes by current councillor's position
        cur_name = f"{ward_doc['councillor_first']} {ward_doc['councillor_last']}"
        yes_n = sum(1 for c in cv if c["voted_by"] == cur_name and c["vote"] == "Yes")
        no_n  = sum(1 for c in cv if c["voted_by"] == cur_name and c["vote"] == "No")
        oth   = sum(1 for c in cv if c["voted_by"] == cur_name and c["vote"] not in ("Yes", "No"))
        summary = f"{yes_n}Y/{no_n}N/{oth}?"
        print(
            f"{ward_doc['ward_num']:>2}  {name:<22}  "
            f"{bv.get(2023,'—'):>5}  {bv.get(2024,'—'):>5}  "
            f"{bv.get(2025,'—'):>5}  {bv.get(2026,'—'):>5}  "
            f"{summary:>20}"
        )


if __name__ == "__main__":
    main()
