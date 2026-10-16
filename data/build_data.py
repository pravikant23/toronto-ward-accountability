#!/usr/bin/env python3
"""
data/build_data.py
Compiles data/wards.json from official City of Toronto raw data files.
Source files are never modified; all values are read exactly as published.
"""

import json
import csv
import os
import sys
import openpyxl
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "raw")

# ── Source file paths ──────────────────────────────────────────────────────────
VOTER_2022      = os.path.join(RAW, "2022_voter_turnout_statistics_final.xlsx")
VOTER_2018      = os.path.join(RAW, "2018-voter-statistics", "2018_Voter_Turnout_Statistics_FINAL.XLSX")
RESULTS_2022    = os.path.join(RAW, "2022-results", "2022_Toronto_Poll_By_Poll_Councillor.xlsx")
RESULTS_2018    = os.path.join(RAW, "2018-results", "2018_Toronto_Poll_By_Poll_Councillor.xlsx")
OFFICIALS_JSON  = os.path.join(RAW, "2022-2026-elected-officials.json")
CENSUS          = os.path.join(RAW, "ward-profiles-2021-census.xlsx")
ATTENDANCE_CSV  = os.path.join(RAW, "council-attendance-2022-2026.csv")

OUT_JSON  = os.path.join(BASE, "wards.json")
OUT_AUDIT = os.path.join(BASE, "data_audit.csv")

# ── By-election facts (confirmed from City Clerk Declaration-of-Results PDFs) ─
BY_ELECTIONS = {
    15: {
        "councillor_first": "Rachel",
        "councillor_last":  "Chernos Lin",
        "date": "2024-11-04",
        "predecessor": "Robinson Jaye",
    },
    20: {
        "councillor_first": "Parthi",
        "councillor_last":  "Kandavel",
        "date": "2023-11-30",
        "predecessor": "Gary Crawford",
    },
    25: {
        "councillor_first": "Neethan",
        "councillor_last":  "Shan",
        "date": "2025-09-29",
        "predecessor": "Jennifer McKelvie",
    },
}

# ── Census row indices (0-based) in '2021 One Variable' sheet ─────────────────
# Verified row by row against the source file.
CENSUS_ROWS = {
    "population":      18,   # "Total - Age" = total population
    "median_age":      39,   # "Median age"
    "total_dwellings": 54,   # "Total - Tenure (includes band housing)"
    "owned":           55,   # "  Owned"
    "rented":          58,   # "  Rented"
    "median_income":  1384,  # "  Median total income of households in 2020 ($)"
}
# "Language spoken most often at home" rows: 0-indexed 655–987 in the same sheet
# English (row 658) and French (row 659) are excluded explicitly.
LANG_HOME_START = 655
LANG_HOME_END   = 987


# ── Helpers ────────────────────────────────────────────────────────────────────

def fail(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_voter_stats(xlsx_path, sheet_name):
    """
    Parse a voter-turnout xlsx.
    Returns (wards_dict, city_dict).
      wards_dict: {ward_num: {registered, ballots_cast, turnout_pct}}
      city_dict:  {registered, ballots_cast, turnout_pct}

    Eligible voters: sum col 13 (Total Eligible Electors) for subs 1–96 only.
    Ballots cast:    sum(col 14 + col 17) for ALL subs (includes 97, 98, 99).
    The 2018 file stores ward numbers as Excel formulas ('=A2' etc.) in some
    rows; those rows inherit the last seen integer ward value.
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[sheet_name]

    ward_eligible = defaultdict(float)
    ward_voted    = defaultdict(float)
    ward_declined = defaultdict(float)
    current_ward  = None

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header row

        ward_col    = row[0]
        sub_col     = row[1]
        eligible    = row[13]   # Total Eligible Electors
        voted       = row[14]   # Number Voted
        declined    = row[17]   # Declined Ballots

        # Ward column is an int for the first subdivision of each ward; later
        # rows in the 2018 file store an Excel formula string instead.
        if isinstance(ward_col, int):
            current_ward = ward_col

        if current_ward is None:
            continue

        try:
            sub_num = int(sub_col)
        except (TypeError, ValueError):
            continue

        # Eligible: regular polling subdivisions only
        if 1 <= sub_num <= 96 and isinstance(eligible, (int, float)):
            ward_eligible[current_ward] += eligible

        # Votes: all subdivisions (97=mail-in, 98/99=advance)
        if isinstance(voted,    (int, float)):
            ward_voted[current_ward]    += voted
        if isinstance(declined, (int, float)):
            ward_declined[current_ward] += declined

    wards = {}
    city_eligible = city_voted = city_declined = 0.0

    for ward in sorted(ward_eligible):
        reg = int(ward_eligible[ward])
        bc  = int(ward_voted[ward])   # Number Voted only (City definition)
        tp  = round(bc / reg * 100, 2) if reg > 0 else None
        wards[ward] = {"registered": reg, "ballots_cast": bc, "turnout_pct": tp}
        city_eligible += ward_eligible[ward]
        city_voted    += ward_voted[ward]
        city_declined += ward_declined[ward]

    city_bc = int(city_voted)   # Number Voted only
    city_tp = round(city_bc / int(city_eligible) * 100, 2) if city_eligible > 0 else None
    city = {
        "registered":   int(city_eligible),
        "ballots_cast": city_bc,
        "turnout_pct":  city_tp,
    }
    return wards, city


def load_councillor_results(xlsx_path):
    """
    Parse a poll-by-poll councillor results xlsx.
    Returns {ward_num: {ward_name, candidates (desc by votes), total_valid_votes}}.

    Sheet layout per ward:
      Row 0:  "City Ward N <Name>"  (title)
      Row 1:  subdivision numbers; last cell = "Total"
      Row 2:  "Councillor"  (label row — skip)
      Row 3+: Candidate Name | per-sub votes … | Total
      Last candidate row is NOT the totals row; that row contains "City Ward N Totals".
    """
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    result = {}

    for sheet_name in wb.sheetnames:
        if not sheet_name.startswith("Ward "):
            continue
        try:
            ward_num = int(sheet_name.split()[1])
        except (IndexError, ValueError):
            continue

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        # Extract ward name from title cell "City Ward N <Name>"
        title = str(rows[0][0] or "").strip()
        parts = title.split(None, 3)
        ward_name = parts[3].strip() if len(parts) >= 4 else ""

        # Candidate rows start at index 3
        candidates = []
        for row in rows[3:]:
            name_cell  = row[0]
            votes_cell = row[-1]   # "Total" column is always last

            if name_cell is None or votes_cell is None:
                continue
            name_str = str(name_cell).strip()
            if not name_str:
                continue
            # Skip the aggregate totals row ("City Ward N Totals")
            if "Totals" in name_str:
                continue
            if not isinstance(votes_cell, (int, float)):
                continue

            candidates.append({"name": name_str, "votes": int(votes_cell)})

        total_valid = sum(c["votes"] for c in candidates)

        for c in candidates:
            c["vote_pct"] = (
                round(c["votes"] / total_valid * 100, 2) if total_valid > 0 else None
            )

        candidates.sort(key=lambda x: x["votes"], reverse=True)

        for i, c in enumerate(candidates):
            c["is_winner"] = i == 0

        result[ward_num] = {
            "ward_name": ward_name,
            "candidates": candidates,
            "total_valid_votes": total_valid,
        }

    return result


def load_census():
    """
    Parse the Ward Profiles 2021 Census xlsx.
    Returns (wards_census, city_census).
      wards_census: {ward_num: {population_2021, median_age_2021, pct_owned,
                                pct_rented, median_household_income_2020,
                                top_non_official_languages}}
      city_census:  same fields for Toronto as a whole
    Column layout: col 1 (B) = Toronto; col N+1 = Ward N.
    """
    wb   = openpyxl.load_workbook(CENSUS, read_only=True, data_only=True)
    ws   = wb["2021 One Variable"]
    rows = list(ws.iter_rows(values_only=True))

    def city_val(row_idx):
        return rows[row_idx][1]

    def ward_val(row_idx, ward_num):
        return rows[row_idx][ward_num + 1]  # ward 1 → col index 2

    # Build the list of individual "spoken most often at home" language rows
    lang_entries = []
    for i in range(LANG_HOME_START, LANG_HOME_END + 1):
        r = rows[i]
        label   = r[0]
        c_count = r[1]
        if not label or not isinstance(c_count, (int, float)) or c_count <= 0:
            continue
        stripped = label.strip()
        sl = stripped.lower()
        # Exclude official languages
        if stripped in ('English', 'French'):
            continue
        # Exclude aggregate / header rows
        if sl.startswith('total'):
            continue
        if 'non-official' in sl:
            continue
        if 'languages' in sl or 'n.e.c.' in sl or 'responses' in sl:
            continue
        # Exclude composite bilingual categories (e.g. "English and non-official language(s)")
        if ' and ' in sl and 'language' in sl:
            continue
        ward_counts = [r[w + 1] for w in range(1, 26)]  # wards 1-25
        lang_entries.append(
            {"label": stripped, "city": int(c_count), "ward_counts": ward_counts}
        )

    def top_langs(ward_num, n=3):
        idx = ward_num - 1  # 0-based index into ward_counts list
        langs = []
        for entry in lang_entries:
            count = entry["ward_counts"][idx]
            if isinstance(count, (int, float)) and count > 0:
                langs.append(
                    {
                        "language": entry["label"],
                        "speakers": int(count),
                        "city_speakers": entry["city"],
                    }
                )
        langs.sort(key=lambda x: x["speakers"], reverse=True)
        return langs[:n]

    def tenure_pct(owned, rented, total):
        if not total or total == 0:
            return None, None
        return round(owned / total * 100, 1), round(rented / total * 100, 1)

    # City-level values
    c_pop   = city_val(CENSUS_ROWS["population"])
    c_age   = city_val(CENSUS_ROWS["median_age"])
    c_total = city_val(CENSUS_ROWS["total_dwellings"])
    c_owned = city_val(CENSUS_ROWS["owned"])
    c_rent  = city_val(CENSUS_ROWS["rented"])
    c_inc   = city_val(CENSUS_ROWS["median_income"])
    c_po, c_pr = tenure_pct(c_owned, c_rent, c_total)

    city_census = {
        "population_2021":                  int(c_pop),
        "median_age_2021":                  float(c_age),
        "total_dwellings":                  int(c_total),
        "owned_dwellings":                  int(c_owned),
        "rented_dwellings":                 int(c_rent),
        "pct_owned":                        c_po,
        "pct_rented":                       c_pr,
        "median_household_income_2020":     int(c_inc),
    }

    wards_census = {}
    for w in range(1, 26):
        pop   = ward_val(CENSUS_ROWS["population"], w)
        age   = ward_val(CENSUS_ROWS["median_age"], w)
        total = ward_val(CENSUS_ROWS["total_dwellings"], w)
        owned = ward_val(CENSUS_ROWS["owned"], w)
        rent  = ward_val(CENSUS_ROWS["rented"], w)
        inc   = ward_val(CENSUS_ROWS["median_income"], w)
        po, pr = tenure_pct(owned, rent, total)

        wards_census[w] = {
            "population_2021":              int(pop)   if isinstance(pop,   (int, float)) else None,
            "median_age_2021":              float(age) if isinstance(age,   (int, float)) else None,
            "total_dwellings":              int(total) if isinstance(total, (int, float)) else None,
            "owned_dwellings":              int(owned) if isinstance(owned, (int, float)) else None,
            "rented_dwellings":             int(rent)  if isinstance(rent,  (int, float)) else None,
            "pct_owned":                    po,
            "pct_rented":                   pr,
            "median_household_income_2020": int(inc)   if isinstance(inc,   (int, float)) else None,
            "top_non_official_languages":   top_langs(w),
        }
    return wards_census, city_census


def load_attendance():
    """
    Parse council-attendance-2022-2026.csv.
    Filters to Committee = 'City Council'.
    Returns {"First Last": {sessions_present, sessions_total, attendance_pct}}.
    """
    sessions_present = defaultdict(int)
    sessions_total   = defaultdict(int)

    with open(ATTENDANCE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Committee"].strip() != "City Council":
                continue
            key = f"{row['First Name'].strip()} {row['Last Name'].strip()}"
            sessions_total[key] += 1
            if row["Present"].strip().upper() == "Y":
                sessions_present[key] += 1

    result = {}
    for key, total in sessions_total.items():
        present = sessions_present[key]
        result[key] = {
            "sessions_present": present,
            "sessions_total":   total,
            "attendance_pct":   round(present / total * 100, 1) if total > 0 else None,
        }
    return result


def load_officials():
    """
    Parse the elected-officials JSON.
    Returns {ward_num: {first, last, email, website, photo_url}}.
    """
    with open(OFFICIALS_JSON, encoding="utf-8") as f:
        records = json.load(f)

    result = {}
    for rec in records:
        district_id = rec.get("District ID", "")
        try:
            ward_num = int(district_id)
        except (TypeError, ValueError):
            continue
        if not 1 <= ward_num <= 25:
            continue
        result[ward_num] = {
            "first":     rec.get("First name",  "").strip(),
            "last":      rec.get("Last name",   "").strip(),
            "email":     rec.get("Email",       "").strip() or None,
            "website":   rec.get("Website",     "").strip() or None,
            "photo_url": rec.get("Photo URL",   "").strip() or None,
        }
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Loading 2022 voter statistics …")
    voter22, city22 = load_voter_stats(VOTER_2022, "2022 Voter Turnout Statistics")
    print(
        f"  City 2022: {city22['registered']:,} registered | "
        f"{city22['ballots_cast']:,} ballots | {city22['turnout_pct']}%"
    )

    print("Loading 2018 voter statistics …")
    voter18, city18 = load_voter_stats(VOTER_2018, "2018 Voter Turnout Statistics")
    print(
        f"  City 2018: {city18['registered']:,} registered | "
        f"{city18['ballots_cast']:,} ballots | {city18['turnout_pct']}%"
    )

    print("Loading 2022 councillor results …")
    res22 = load_councillor_results(RESULTS_2022)

    print("Loading 2018 councillor results …")
    res18 = load_councillor_results(RESULTS_2018)

    print("Loading census data …")
    census_wards, census_city = load_census()

    print("Loading attendance data …")
    attendance = load_attendance()
    # Council-wide average attendance (City Council sessions)
    all_pcts = [a["attendance_pct"] for a in attendance.values() if a["attendance_pct"] is not None]
    council_avg_att = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else None

    print("Loading elected officials …")
    officials = load_officials()

    # ── Assemble wards ─────────────────────────────────────────────────────────
    wards_out = []
    audit_rows = []

    for wn in range(1, 26):
        v22  = voter22.get(wn, {})
        v18  = voter18.get(wn, {})
        r22  = res22.get(wn, {})
        r18  = res18.get(wn, {})
        cen  = census_wards.get(wn, {})
        off  = officials.get(wn, {})
        bye  = BY_ELECTIONS.get(wn)

        ward_name = r22.get("ward_name", "")
        candidates = r22.get("candidates", [])

        if not candidates:
            fail(f"Ward {wn}: no candidates in results file")

        winner    = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None

        registered   = v22.get("registered")
        ballots_cast = v22.get("ballots_cast")
        tp22         = v22.get("turnout_pct")
        tp18         = v18.get("turnout_pct")
        change       = round(tp22 - tp18, 2) if (tp22 is not None and tp18 is not None) else None

        margin_votes = (
            winner["votes"] - runner_up["votes"] if runner_up else None
        )
        margin_pct = (
            round(winner["vote_pct"] - runner_up["vote_pct"], 2)
            if runner_up and winner["vote_pct"] is not None and runner_up["vote_pct"] is not None
            else None
        )

        winner_share = (
            round(winner["votes"] / registered, 4)
            if registered and registered > 0 else None
        )
        winner_1_in_n = (
            round(1 / winner_share)
            if winner_share and winner_share > 0 else None
        )

        # Open seat: did the 2018 winner appear on the 2022 ballot?
        open_seat = None
        if r18.get("candidates"):
            w18_winner = r18["candidates"][0]["name"]
            # The results use "LastName FirstName"; compare first token (last name)
            w18_last = w18_winner.split()[0].lower()
            names22  = [c["name"].lower() for c in candidates]
            open_seat = not any(w18_last in n for n in names22)

        # Current councillor
        if bye:
            c_first = bye["councillor_first"]
            c_last  = bye["councillor_last"]
            by_note = (
                f"By-election {bye['date']}: {c_first} {c_last} "
                f"succeeded {bye['predecessor']}."
            )
        else:
            c_first = off.get("first", "")
            c_last  = off.get("last", "")
            by_note = None

        # Attendance: look up current councillor by name
        att_key = f"{c_first} {c_last}"
        att_data = attendance.get(att_key)
        if att_data:
            att_out = {**att_data, "council_avg_pct": council_avg_att}
        else:
            att_out = None

        ward_doc = {
            "ward_num":               wn,
            "ward_name":              ward_name,
            "councillor_first":       c_first,
            "councillor_last":        c_last,
            "councillor_email":       off.get("email"),
            "councillor_website":     off.get("website"),
            "councillor_photo_url":   off.get("photo_url"),
            "by_election":            by_note,
            # 2022 election
            "registered_voters":      registered,
            "ballots_cast":           ballots_cast,
            "turnout_pct":            tp22,
            "city_turnout_pct":       city22["turnout_pct"],
            "turnout_2018_pct":       tp18,
            "change_vs_2018":         change,
            "candidates_2022":        candidates,
            "total_valid_votes_2022": r22.get("total_valid_votes"),
            "winner_votes":           winner["votes"],
            "runner_up_name":         runner_up["name"]   if runner_up else None,
            "runner_up_votes":        runner_up["votes"]  if runner_up else None,
            "margin_votes":           margin_votes,
            "margin_pct_points":      margin_pct,
            "winner_share_of_registered": winner_share,
            "winner_1_in_n":          winner_1_in_n,
            "num_candidates":         len(candidates),
            "open_seat":              open_seat,
            # Census (ward-level + city reference)
            "census":                 cen,
            # Attendance
            "attendance":             att_out,
            # Source provenance
            "sources": {
                "registered_voters": "2022_voter_turnout_statistics_final.xlsx",
                "turnout_2018":      "2018-voter-statistics/2018_Voter_Turnout_Statistics_FINAL.XLSX",
                "candidates":        "2022-results/2022_Toronto_Poll_By_Poll_Councillor.xlsx",
                "open_seat_ref":     "2018-results/2018_Toronto_Poll_By_Poll_Councillor.xlsx",
                "officials":         "2022-2026-elected-officials-contact-info.json",
                "census":            "ward-profiles-2021-census.xlsx",
                "attendance":        "council-attendance-2022-2026.csv",
            },
        }
        wards_out.append(ward_doc)

        # Audit trail
        def audit(field, value, source, note=""):
            audit_rows.append({
                "ward":        wn,
                "ward_name":   ward_name,
                "field":       field,
                "value":       value,
                "source_file": source,
                "note":        note,
            })

        audit("registered_voters",          registered,
              "2022_voter_turnout_statistics_final.xlsx",
              "Sum of col 13 (Total Eligible Electors) for subs 1-96 only")
        audit("ballots_cast",               ballots_cast,
              "2022_voter_turnout_statistics_final.xlsx",
              "Sum of col 14 (Number Voted) for all subs; declined ballots not included")
        audit("turnout_pct",                tp22,
              "2022_voter_turnout_statistics_final.xlsx",
              "ballots_cast / registered_voters * 100")
        audit("turnout_2018_pct",           tp18,
              "2018-voter-statistics/2018_Voter_Turnout_Statistics_FINAL.XLSX",
              "Same formula as 2022")
        audit("winner_votes",               winner["votes"],
              "2022-results/2022_Toronto_Poll_By_Poll_Councillor.xlsx",
              "Total column, highest-vote candidate")
        audit("population_2021",            cen.get("population_2021"),
              "ward-profiles-2021-census.xlsx",
              "Row 19 'Total - Age', '2021 One Variable' sheet")
        audit("median_household_income_2020", cen.get("median_household_income_2020"),
              "ward-profiles-2021-census.xlsx",
              "Row 1385 'Median total income of households in 2020'")

    # ── Write wards.json ───────────────────────────────────────────────────────
    output = {
        "generated": "2026-10-15",
        "city_2022": {
            "registered_voters": city22["registered"],
            "ballots_cast":      city22["ballots_cast"],
            "turnout_pct":       city22["turnout_pct"],
        },
        "city_2018": {
            "registered_voters": city18["registered"],
            "ballots_cast":      city18["ballots_cast"],
            "turnout_pct":       city18["turnout_pct"],
        },
        "city_census": census_city,
        "wards": wards_out,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUT_JSON}")

    # ── Write data_audit.csv ───────────────────────────────────────────────────
    with open(OUT_AUDIT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["ward", "ward_name", "field", "value", "source_file", "note"],
        )
        writer.writeheader()
        writer.writerows(audit_rows)
    print(f"Wrote {OUT_AUDIT}")

    # ── Summary table ──────────────────────────────────────────────────────────
    hdr = (
        f"{'W':>2}  {'Ward Name':<30}  {'Councillor':<22}  "
        f"{'Reg':>9}  {'T22%':>6}  {'T18%':>6}  {'Chg':>6}  "
        f"{'2022 Winner':<22}  {'W%':>5}  {'Margin':>7}  {'Share':>6}  {'Open?':>5}"
    )
    print()
    print(hdr)
    print("─" * len(hdr))

    for w in wards_out:
        winner_c = next((c for c in w["candidates_2022"] if c.get("is_winner")), None)
        cname    = f"{w['councillor_first']} {w['councillor_last']}"
        wname    = winner_c["name"][:22] if winner_c else ""
        reg      = w["registered_voters"] or 0
        tp22_v   = w["turnout_pct"] or 0.0
        tp18_v   = w["turnout_2018_pct"] or 0.0
        chg_v    = w["change_vs_2018"] or 0.0
        wpct     = winner_c["vote_pct"] if winner_c and winner_c["vote_pct"] is not None else 0.0
        margin   = w["margin_votes"] or 0
        share    = (w["winner_share_of_registered"] or 0) * 100
        open_s   = "Y" if w["open_seat"] else ("?" if w["open_seat"] is None else "N")

        print(
            f"{w['ward_num']:>2}  {w['ward_name']:<30}  {cname:<22}  "
            f"{reg:>9,}  {tp22_v:>6.2f}  {tp18_v:>6.2f}  {chg_v:>+6.2f}  "
            f"{wname:<22}  {wpct:>5.1f}  {margin:>7,}  {share:>5.1f}%  {open_s:>5}"
        )

    print()
    print(
        f"City 2022: {city22['registered']:,} registered | "
        f"{city22['ballots_cast']:,} ballots | {city22['turnout_pct']}% turnout"
    )
    print(
        f"City 2018: {city18['registered']:,} registered | "
        f"{city18['ballots_cast']:,} ballots | {city18['turnout_pct']}% turnout"
    )
    if council_avg_att is not None:
        print(f"Council avg attendance (City Council sessions): {council_avg_att}%")


if __name__ == "__main__":
    main()
