#!/usr/bin/env python3
"""
data/build_issues.py — Phase 1 of "What matters here" section.
Reads raw City of Toronto open data → adds 'issues' key to each ward in wards.json.

Data sources:
  311  : data/raw/311/sr{year}.zip        (2022-2026)
  Crime: data/raw/major-crime-indicators.csv
  KSI  : data/raw/motor-vehicle-collisions-ksi-4326.csv
  Wards: data/raw/city-wards-4326.geojson (for spatial join)
  Pop  : data/wards.json                  (census populations)

Building permits: WARD_GRID field is a city map-grid code (e.g. E2022, N0831),
not the 25-ward numbering system, and the file has no coordinates.
Per-ward housing data is therefore NOT AVAILABLE.
"""

import csv, json, io, os, re, sys, zipfile
from collections import defaultdict
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
RAW  = os.path.join(BASE, 'raw')

WARDS_JSON   = os.path.join(BASE, 'wards.json')
GEOJSON_PATH = os.path.join(RAW,  'city-wards-4326.geojson')
CRIME_CSV    = os.path.join(RAW,  'major-crime-indicators.csv')
KSI_CSV      = os.path.join(RAW,  'motor-vehicle-collisions-ksi-4326.csv')
AUDIT_CSV    = os.path.join(BASE, 'data_audit.csv')

# 2026 YTD cutoff: Sep 30 (last full month in the file)
YTD_2026_CUTOFF = '2026-09-30'
YTD_MONTHS      = 9  # Jan-Sep

# ── Road-related 311 request types (official names) ───────────────────────────
# Scope: potholes, road damage, traffic signals, sidewalks, road maintenance.
# Excludes: administrative complaints, garbage/waste, graffiti, elections signs.
#
# NOTE: The City renamed many 311 categories in 2025. Pre-2025 names are listed
# alongside their 2025+ equivalents so the count is consistent across all years.
# Rename mapping confirmed by comparing city-wide counts:
#   "Road - Pot hole"              → "Road Pothole / Road Damage"
#   "Road - Damaged"               → included in Road Pothole / Road Damage
#   "Road - Cleaning/Debris"       → "Clean up Debris on Road"
#   "Road Ploughing Required"      → "Road Plowing Request"
#   "Road - Sanding / Salting Required" → "Road Salting Request"
#   "Sidewalk - Snow Clearing"     → "Sidewalk Snow Clearing Required"
#   "Sidewalk Icy|| Needs Sand/Salt" → "Icy Sidewalk Needs Salting"
#   "Sidewalk - Damaged / Concrete"→ "Damaged Concrete Sidewalk"
#   "Traffic Signal Maintenance"   → "Traffic Signal Repair"
#   "Missing/Damaged Signs"        → "Missing / Damaged Street or Traffic Signs"
ROAD_311_TYPES = frozenset([
    # 2025+ names
    'Road Pothole / Road Damage',
    'Pothole on Expressway',
    'Bike Lane Pothole',
    'Road - Sinking',
    'Road Water Ponding',
    'Road Plow Damage',
    'Road Plowing Request',
    'Road Salting Request',
    'Minor Road Damage',
    'Road damaged on Expressway',
    'Damaged Concrete Sidewalk',
    'Sidewalk - Damaged /Brick/Interlock',
    'Sidewalk - Cleaning',
    'Sidewalk Snow Clearing Required',
    'Icy Sidewalk Needs Salting',
    'Illegal Snow Dumping & Failure to Clear Snow or Ice on Public Sidewalk',
    'Sidewalk-Water Ponding',
    'Sidewalk - Accessible Ramps & Tactile Pavers',
    'Traffic Signal Repair',
    'Vehicle Traffic Signal Issue',
    'Pedestrian Signal Issue',
    'Missing / Damaged Street or Traffic Signs',
    'Missing/Faded Pavement Markings',
    'Curb - Damaged',
    'Guardrail - Damaged',
    'Damaged Catch Basin on the Road',
    'Damaged Catch Basin on the Roadside',
    'Clean up Debris on Road',
    'Roadway Utility Cut - Settlement',
    # Pre-2025 names (renamed in 2025; kept for 2022-2024 consistency)
    'Road - Pot hole',
    'Road - Damaged',
    'Road - Cleaning/Debris',
    'Road Ploughing Required',
    'Road - Sanding / Salting Required',
    'Sidewalk - Snow Clearing',
    'Sidewalk Icy|| Needs Sand/Salt',
    'Sidewalk - Damaged / Concrete',
    'Traffic Signal Maintenance',
    'Missing/Damaged Signs',
    'Catch Basin - Blocked / Flooding',
    'Catch basin (Storm) - Overflowing',
    'Catch basin (Storm) - Damage',
    'Catch Basin - Damaged Maintenance Requested',
    'Catch Basin - Debris / Litter',
    'Catch basin Maintenance and Repair',
    'Roadside Utility Cut - Settlement',
])

CRIME_CATEGORIES = frozenset([
    'Assault', 'Break and Enter', 'Auto Theft', 'Robbery', 'Theft Over',
])

CRIME_YEARS   = list(range(2018, 2026))   # 2018-2025 full years
KSI_YEARS     = list(range(2018, 2027))   # 2018-2025 full + 2026 YTD


# ── Spatial join helpers ───────────────────────────────────────────────────────

def load_ward_polygons():
    """Return list of (ward_num, shapely_polygon) sorted by ward_num."""
    from shapely.geometry import shape, MultiPolygon, Point
    with open(GEOJSON_PATH, encoding='utf-8') as f:
        gj = json.load(f)
    polys = []
    for feat in gj['features']:
        wn  = int(feat['properties']['AREA_SHORT_CODE'])
        geom = shape(feat['geometry'])
        polys.append((wn, geom))
    polys.sort(key=lambda x: x[0])
    return polys

def build_spatial_index(polys):
    """Return shapely STRtree for fast point-in-polygon."""
    from shapely.strtree import STRtree
    geoms = [p for _, p in polys]
    tree  = STRtree(geoms)
    return tree

def point_to_ward(lon, lat, polys, tree):
    """Return ward_num for (lon, lat), or None if outside all wards."""
    from shapely.geometry import Point
    pt = Point(lon, lat)
    for idx in tree.query(pt):
        wn, poly = polys[idx]
        if poly.contains(pt):
            return wn
    return None


# ── Ward number parsers ────────────────────────────────────────────────────────

_WARD_RE = re.compile(r'\((\d{1,2})\)\s*$')

def parse_ward_311(val):
    """'Etobicoke-Lakeshore (03)' → 3, or None."""
    m = _WARD_RE.search(str(val).strip())
    return int(m.group(1)) if m else None

def parse_ward_ksi(val):
    """'Don Valley East (16)' → 16, or None."""
    m = _WARD_RE.search(str(val).strip())
    return int(m.group(1)) if m else None


# ── 311 processing ─────────────────────────────────────────────────────────────

def process_311():
    """
    Returns:
      ward_year_types : {ward_num: {year: {type: count}}}
      ward_year_road  : {ward_num: {year: int}}   road-related totals
      ward_year_total : {ward_num: {year: int}}   all 311
      city_year_total : {year: int}
      unparsed        : {year: int}   rows where ward couldn't be parsed
      ytd_cutoff      : str  (YYYY-MM-DD)
    """
    print('\n=== Processing 311 data ===')
    years    = [2022, 2023, 2024, 2025, 2026]
    enc_map  = {2022:'utf-8-sig', 2023:'utf-8-sig', 2024:'utf-8-sig',
                2025:'latin-1',   2026:'latin-1'}

    wyt  = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # ward→yr→type
    wyroad  = defaultdict(lambda: defaultdict(int))                    # ward→yr
    wytotal = defaultdict(lambda: defaultdict(int))                    # ward→yr
    cyt     = defaultdict(int)                                         # yr (city)
    unp     = defaultdict(int)                                         # yr unparsed

    for yr in years:
        zpath = os.path.join(RAW, '311', f'sr{yr}.zip')
        enc   = enc_map[yr]
        print(f'  Loading {yr}…', end=' ', flush=True)
        with zipfile.ZipFile(zpath) as z:
            nm = z.namelist()[0]
            with z.open(nm) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding=enc, errors='replace'))
                for row in reader:
                    cdate = row.get('Creation Date', '')[:10]
                    # For 2026: only count Jan 1 – Sep 30
                    if yr == 2026 and (not cdate or cdate > YTD_2026_CUTOFF):
                        continue
                    # For YTD comparison: 2025 only Jan-Sep
                    # We store by year; the comparison is done in aggregation

                    cyt[yr] += 1
                    wv  = row.get('Ward', '').strip()
                    wn  = parse_ward_311(wv)
                    rt  = row.get('Service Request Type', '').strip()

                    if wn is None or wn < 1 or wn > 25:
                        unp[yr] += 1
                        continue

                    wyt[wn][yr][rt] += 1
                    wytotal[wn][yr] += 1
                    if rt in ROAD_311_TYPES:
                        wyroad[wn][yr] += 1

        parsed = cyt[yr] - unp[yr]
        print(f'{cyt[yr]:,} rows, {unp[yr]:,} unparsed ({unp[yr]/cyt[yr]*100:.1f}%)')

    return dict(wyt), dict(wyroad), dict(wytotal), dict(cyt), dict(unp)


# ── Crime processing ───────────────────────────────────────────────────────────

def process_crime(polys, tree):
    """
    Returns:
      ward_year_cat    : {ward_num: {year: {cat: count}}}
      ward_year_total  : {ward_num: {year: int}}
      city_year_total  : {year: int}
      dropped          : {year: int}   records with missing/zero coords
      occ_none_count   : int           records with OCC_YEAR='None'
      ward_ytd24_total : {ward_num: int}   Jan-Sep 2024 count per ward
      city_ytd24_total : int               Jan-Sep 2024 city total
    """
    print('\n=== Processing crime (MCI) data ===')
    wyt     = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    wytotal = defaultdict(lambda: defaultdict(int))
    cyt     = defaultdict(int)
    dropped = defaultdict(int)
    occ_none = 0
    ward_ytd24  = defaultdict(int)   # Jan-Sep 2024 per ward
    city_ytd24  = 0

    with open(CRIME_CSV, encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row.get('MCI_CATEGORY', '').strip()
            if cat not in CRIME_CATEGORIES:
                continue

            yr_str = row.get('OCC_YEAR', '').strip()
            if yr_str == 'None' or not yr_str:
                occ_none += 1
                continue
            try:
                yr = int(yr_str)
            except ValueError:
                occ_none += 1
                continue

            if yr not in CRIME_YEARS:
                continue

            cyt[yr] += 1

            # Jan-Sep 2024 city count (before coord filter, to match raw total)
            if yr == 2024:
                _JAN_SEP = {'January','February','March','April','May','June',
                            'July','August','September'}
                month_s = row.get('OCC_MONTH', '').strip()
                _in_ytd24 = month_s in _JAN_SEP
                if _in_ytd24:
                    city_ytd24 += 1
            else:
                _in_ytd24 = False

            lon_s = row.get('LONG_WGS84', '').strip()
            lat_s = row.get('LAT_WGS84', '').strip()
            try:
                lon, lat = float(lon_s), float(lat_s)
                if lon == 0 or lat == 0:
                    raise ValueError('zero coords')
            except (ValueError, TypeError):
                dropped[yr] += 1
                continue

            wn = point_to_ward(lon, lat, polys, tree)
            if wn is None:
                dropped[yr] += 1
                continue

            wyt[wn][yr][cat] += 1
            wytotal[wn][yr] += 1

            # Jan-Sep 2024 per-ward count (placed only, consistent with annual ward counts)
            if _in_ytd24 and 1 <= wn <= 25:
                ward_ytd24[wn] += 1

    for yr in CRIME_YEARS:
        ward_sum = sum(wytotal[wn].get(yr, 0) for wn in range(1, 26))
        total = cyt.get(yr, 0)
        drop  = dropped.get(yr, 0)
        pct_d = drop / total * 100 if total else 0
        print(f'  {yr}: city={total:,}, placed={ward_sum:,}, dropped={drop:,} ({pct_d:.1f}%)')

    print(f'  OCC_YEAR=None/missing: {occ_none:,}')
    print(f'  Jan-Sep 2024 (YTD comparison): city={city_ytd24:,}, '
          f'ward_sum={sum(ward_ytd24.values()):,}')
    return dict(wyt), dict(wytotal), dict(cyt), dict(dropped), occ_none, \
           dict(ward_ytd24), city_ytd24


# ── KSI processing ─────────────────────────────────────────────────────────────

def process_ksi(polys, tree):
    """
    Returns:
      ward_year_ksi   : {ward_num: {year: {'total': int, 'ped': int, 'cyc': int}}}
      city_year_ksi   : {year: {'total': int, 'ped': int, 'cyc': int}}
      dropped_ward    : {year: int}   collisions without parseable ward
    """
    print('\n=== Processing KSI data ===')
    # First pass: build per-collision data
    # Each collision_id gets: year, ward_num (or None), acclass, ped_involved, cyc_involved
    coll = {}   # collision_id → {yr, wn, acclass, ped, cyc}

    blank_ward_coords = []  # (collision_id, lon, lat) for spatial join

    with open(KSI_CSV, encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid    = row.get('collision_id', '').strip()
            accdate= row.get('accdate', '')[:10]
            yr     = int(accdate[:4]) if accdate else None
            if yr is None or yr not in KSI_YEARS:
                continue

            # For 2026: only Jan-Sep
            if yr == 2026 and accdate > YTD_2026_CUTOFF:
                continue

            acclass = row.get('acclass', '').strip()
            ped     = row.get('pedestrian', '').strip().lower() in ('true', '1', 'yes')
            cyc     = row.get('cyclist', '').strip().lower()    in ('true', '1', 'yes')

            if cid not in coll:
                wn_raw = row.get('wardname', '').strip()
                wn     = parse_ward_ksi(wn_raw)
                lon_s  = row.get('longitude', '').strip()
                lat_s  = row.get('latitude', '').strip()
                try:
                    lon, lat = float(lon_s), float(lat_s)
                except (ValueError, TypeError):
                    lon, lat = None, None

                if wn is None and lon is not None and lat is not None:
                    blank_ward_coords.append((cid, lon, lat))

                coll[cid] = {
                    'yr': yr, 'wn': wn, 'acclass': acclass,
                    'ped': False, 'cyc': False,
                    'month': int(accdate[5:7]) if len(accdate) >= 7 else 0,
                }

            # Accumulate ped/cyc across rows for same collision
            if ped: coll[cid]['ped'] = True
            if cyc: coll[cid]['cyc'] = True

    # Spatial join for collisions with blank wardname
    print(f'  Spatial-joining {len(blank_ward_coords)} collisions with blank wardname…')
    resolved = 0
    for cid, lon, lat in blank_ward_coords:
        wn = point_to_ward(lon, lat, polys, tree)
        if wn:
            coll[cid]['wn'] = wn
            resolved += 1
    print(f'  Resolved {resolved} of {len(blank_ward_coords)} via spatial join')

    # Aggregate
    wyk     = defaultdict(lambda: defaultdict(lambda: {'total':0,'ped':0,'cyc':0}))
    cyk     = defaultdict(lambda: {'total':0,'ped':0,'cyc':0})
    drop    = defaultdict(int)   # year → collisions without ward after spatial join
    wyk_ytd25 = defaultdict(lambda: {'total':0,'ped':0,'cyc':0})   # ward Jan-Sep 2025
    cyk_ytd25 = {'total':0,'ped':0,'cyc':0}                         # city Jan-Sep 2025

    for cid, d in coll.items():
        yr      = d['yr']
        acclass = d['acclass']
        if acclass not in ('Fatal Injury', 'Non-Fatal Injury'):
            continue   # skip Property Damage Only
        ped   = d['ped']
        cyc   = d['cyc']
        wn    = d['wn']
        month = d.get('month', 0)

        cyk[yr]['total'] += 1
        if ped: cyk[yr]['ped'] += 1
        if cyc: cyk[yr]['cyc'] += 1

        # Jan-Sep 2025 subset (for comparison with 2026 YTD)
        if yr == 2025 and 1 <= month <= 9:
            cyk_ytd25['total'] += 1
            if ped: cyk_ytd25['ped'] += 1
            if cyc: cyk_ytd25['cyc'] += 1

        if wn is None or wn < 1 or wn > 25:
            drop[yr] += 1
            continue

        wyk[wn][yr]['total'] += 1
        if ped: wyk[wn][yr]['ped'] += 1
        if cyc: wyk[wn][yr]['cyc'] += 1

        # Jan-Sep 2025 per-ward
        if yr == 2025 and 1 <= month <= 9:
            wyk_ytd25[wn]['total'] += 1
            if ped: wyk_ytd25[wn]['ped'] += 1
            if cyc: wyk_ytd25[wn]['cyc'] += 1

    for yr in KSI_YEARS:
        ct = cyk.get(yr, {}).get('total', 0)
        dt = drop.get(yr, 0)
        ws = sum(wyk[wn].get(yr, {}).get('total', 0) for wn in range(1, 26))
        print(f'  {yr}: city KSI collisions={ct}, placed={ws}, dropped={dt}')
    print(f'  2025 Jan-Sep: city={cyk_ytd25["total"]}, '
          f'ward_sum={sum(v["total"] for v in wyk_ytd25.values())}')

    return dict(wyk), dict(cyk), dict(drop), dict(wyk_ytd25), cyk_ytd25


# ── Validation helpers ────────────────────────────────────────────────────────

def run_validation(ward_data, crime_ward, crime_city, crime_drop,
                   three11_ward_total, three11_city, three11_unparsed,
                   ksi_ward, ksi_city, ksi_drop):
    """Hard-fail validation. Returns list of failure strings."""
    failures = []

    # 311: sum of ward counts + unparsed = city total per year
    for yr in [2022, 2023, 2024, 2025, 2026]:
        ward_sum = sum(three11_ward_total.get(wn, {}).get(yr, 0) for wn in range(1, 26))
        unp      = three11_unparsed.get(yr, 0)
        city     = three11_city.get(yr, 0)
        if ward_sum + unp != city:
            failures.append(f'311 {yr}: ward_sum({ward_sum})+unparsed({unp}) != city({city})')

    # Crime: sum of ward counts + dropped = city total per year
    for yr in CRIME_YEARS:
        ward_sum = sum(crime_ward.get(wn, {}).get(yr, 0) for wn in range(1, 26))
        drop     = crime_drop.get(yr, 0)
        city     = crime_city.get(yr, 0)
        if ward_sum + drop != city:
            failures.append(f'Crime {yr}: ward({ward_sum})+drop({drop}) != city({city})')

    # KSI: ward sum + dropped = city total per year
    for yr in KSI_YEARS:
        ward_sum = sum((ksi_ward.get(wn, {}).get(yr) or {}).get('total', 0) for wn in range(1, 26))
        drop     = ksi_drop.get(yr, 0)
        city     = (ksi_city.get(yr) or {}).get('total', 0)
        if ward_sum + drop != city:
            failures.append(f'KSI {yr}: ward({ward_sum})+drop({drop}) != city({city})')

    # Rates: flag wards with 0 or >5x city average
    pops = {w['ward_num']: w['census']['population_2021'] for w in ward_data}
    city_pop = sum(pops.values())

    for yr in CRIME_YEARS:
        city_rate = crime_city.get(yr, 0) / city_pop * 1000
        for wn in range(1, 26):
            cnt  = crime_ward.get(wn, {}).get(yr, 0)
            pop  = pops.get(wn, 0)
            if pop == 0:
                continue
            rate = cnt / pop * 1000
            if rate == 0:
                failures.append(f'Crime {yr} ward {wn}: rate is exactly 0 (suspicious)')
            elif city_rate > 0 and rate > 5 * city_rate:
                failures.append(f'Crime {yr} ward {wn}: rate {rate:.2f} > 5x city {city_rate:.2f} — VERIFY')

    return failures


# ── Spot-print for Ward 1 and Ward 11 ─────────────────────────────────────────

def spot_print(wn, ward_data, crime_ward, crime_city, crime_drop,
               three11_types, three11_road, three11_city, three11_unparsed,
               ksi_ward, ksi_city, ksi_drop):
    pops = {w['ward_num']: w['census']['population_2021'] for w in ward_data}
    pop  = pops[wn]
    city_pop = sum(pops.values())
    name = next(w['ward_name'] for w in ward_data if w['ward_num'] == wn)

    print(f'\n{"="*60}')
    print(f'SPOT CHECK: Ward {wn} — {name}  (2021 pop: {pop:,})')
    print('='*60)

    # Crime
    print('\n--- Crime (MCI, 5 categories) ---')
    print(f'{"Year":>5}  {"Ward":>8}  {"City":>8}  {"WardRate":>9}  {"CityRate":>9}')
    for yr in CRIME_YEARS:
        cat_d = crime_ward.get(wn, {}).get(yr, {})
        wc    = sum(cat_d.values()) if isinstance(cat_d, dict) else int(cat_d)
        cc   = crime_city.get(yr, 0)
        wr   = wc / pop * 1000
        cr   = cc / city_pop * 1000
        drop = crime_drop.get(yr, 0)
        print(f'{yr:>5}  {wc:>8,}  {cc:>8,}  {wr:>9.2f}  {cr:>9.2f}  (dropped={drop})')

    # 311 top 5 in 2025 vs 2024
    print('\n--- 311 Top 5 Request Types — 2025 (vs 2024) ---')
    types_25 = three11_types.get(wn, {}).get(2025, {})
    types_24 = three11_types.get(wn, {}).get(2024, {})
    top5 = sorted(types_25.items(), key=lambda x: x[1], reverse=True)[:5]
    for rt, cnt in top5:
        prev = types_24.get(rt, 0)
        chg  = cnt - prev
        print(f'  {cnt:>5,} {("+" if chg>=0 else "")}{chg:>5,}  {rt}')

    print('\n--- 311 Road-related per year ---')
    print(f'{"Year":>5}  {"Road311":>8}  {"Total311":>9}  {"RoadRate/1k":>12}')
    for yr in [2022, 2023, 2024, 2025, 2026]:
        road  = three11_road.get(wn, {}).get(yr, 0)
        total = sum(three11_types.get(wn, {}).get(yr, {}).values())
        rate  = road / pop * 1000
        ytd   = ' (Jan-Sep)' if yr == 2026 else ''
        print(f'{yr:>5}  {road:>8,}  {total:>9,}  {rate:>12.2f}{ytd}')

    # KSI
    print('\n--- KSI Collisions (Fatal + Non-Fatal) per year ---')
    print(f'{"Year":>5}  {"Ward KSI":>9}  {"Ped":>5}  {"Cyc":>5}  {"City KSI":>9}')
    for yr in KSI_YEARS:
        wksi = ksi_ward.get(wn, {}).get(yr) or {}
        cksi = ksi_city.get(yr) or {}
        ytd  = ' (Jan-Sep)' if yr == 2026 else ''
        print(f'{yr:>5}  {wksi.get("total",0):>9}  '
              f'{wksi.get("ped",0):>5}  {wksi.get("cyc",0):>5}  '
              f'{cksi.get("total",0):>9}{ytd}')

    # Dropped / unparsed
    print('\n--- Data quality: dropped/unparsed ---')
    print('Crime dropped by year:', {yr: crime_drop.get(yr,0) for yr in CRIME_YEARS})
    print('311 unparsed by year: ', {yr: three11_unparsed.get(yr,0) for yr in [2022,2023,2024,2025,2026]})
    print('KSI dropped by year:  ', {yr: ksi_drop.get(yr,0) for yr in KSI_YEARS})
    print(f'Building permits per ward: NOT AVAILABLE')
    print(f'  (WARD_GRID field uses city map-grid codes, not 25-ward numbers; no coordinates in file)')


# ── Audit CSV helpers ─────────────────────────────────────────────────────────

def append_audit(rows):
    """Append new rows to data_audit.csv."""
    exists = os.path.isfile(AUDIT_CSV)
    with open(AUDIT_CSV, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['ward', 'ward_name', 'field', 'value', 'source_file', 'note'])
        for r in rows:
            w.writerow(r)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('Loading wards.json…')
    with open(WARDS_JSON, encoding='utf-8') as f:
        data = json.load(f)
    ward_data = data['wards']

    print('Loading ward polygons for spatial join…')
    polys = load_ward_polygons()
    tree  = build_spatial_index(polys)
    print(f'  {len(polys)} ward polygons loaded')

    # ── Process datasets ────────────────────────────────────────────────────────
    three11_types, three11_road, three11_total, three11_city, three11_unparsed = process_311()

    crime_ward_cat, crime_ward_total, crime_city, crime_drop, occ_none, \
        crime_ward_ytd24, crime_city_ytd24 = process_crime(polys, tree)
    # Flatten crime_ward_total: {wn: {yr: count}}
    cw_total = {wn: crime_ward_total.get(wn, {}) for wn in range(1, 26)}

    ksi_ward, ksi_city, ksi_drop, ksi_ward_ytd25, ksi_city_ytd25 = process_ksi(polys, tree)

    # ── Validation ──────────────────────────────────────────────────────────────
    print('\n=== Validation ===')
    pops = {w['ward_num']: w['census']['population_2021'] for w in ward_data}

    failures = run_validation(
        ward_data,
        {wn: crime_ward_total.get(wn, {}) for wn in range(1, 26)},
        crime_city, crime_drop,
        three11_total, three11_city, three11_unparsed,
        ksi_ward, ksi_city, ksi_drop,
    )

    if failures:
        for f in failures:
            print(f'  FAIL: {f}')
        print(f'\n{len(failures)} validation failure(s). Aborting.')
        sys.exit(1)
    else:
        print(f'  All validation checks passed.')

    # ── Spot prints ─────────────────────────────────────────────────────────────
    for wn in [1, 11]:
        spot_print(wn, ward_data, crime_ward_cat,
                   crime_city, crime_drop,
                   three11_types, three11_road, three11_city, three11_unparsed,
                   ksi_ward, ksi_city, ksi_drop)

    # ── Build issues dict per ward ───────────────────────────────────────────────
    print('\n=== Building issues data per ward ===')
    city_pop = sum(pops.values())
    audit_rows = []

    for ward in ward_data:
        wn   = ward['ward_num']
        pop  = pops.get(wn, 0)
        wname= ward['ward_name']

        # Crime rates per 1,000 residents per year
        crime_by_year = {}
        for yr in CRIME_YEARS:
            total = crime_ward_total.get(wn, {}).get(yr, 0)
            by_cat = {cat: crime_ward_cat.get(wn, {}).get(yr, {}).get(cat, 0)
                      for cat in CRIME_CATEGORIES}
            rate   = round(total / pop * 1000, 2) if pop else None
            crime_by_year[yr] = {
                'count': total,
                'rate_per_1k': rate,
                'by_category': by_cat,
            }
            audit_rows.append([wn, wname, f'crime_total_{yr}', total,
                                'major-crime-indicators.csv', f'MCI_CATEGORY in 5 cats, OCC_YEAR={yr}'])
            audit_rows.append([wn, wname, f'crime_rate_{yr}', rate,
                                'major-crime-indicators.csv', 'per 1,000 residents (2021 Census pop)'])

        # City crime rates
        city_crime_rates = {}
        for yr in CRIME_YEARS:
            cc = crime_city.get(yr, 0)
            city_crime_rates[yr] = round(cc / city_pop * 1000, 2) if city_pop else None

        # Jan-Sep 2024 ward count (for comparison with Jan-Sep 2025)
        ytd24_count = crime_ward_ytd24.get(wn, 0)
        ytd24_rate  = round(ytd24_count / pop * 1000, 2) if pop else None
        city_ytd24_rate = round(crime_city_ytd24 / city_pop * 1000, 2) if city_pop else None

        # 311 data
        three11_by_year = {}
        for yr in [2022, 2023, 2024, 2025]:
            total_yr = sum(three11_types.get(wn, {}).get(yr, {}).values())
            road_yr  = three11_road.get(wn, {}).get(yr, 0)
            top5     = sorted(
                three11_types.get(wn, {}).get(yr, {}).items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            three11_by_year[yr] = {
                'total': total_yr,
                'road_related': road_yr,
                'top5': [{'type': rt, 'count': cnt} for rt, cnt in top5],
            }
            audit_rows.append([wn, wname, f'311_total_{yr}', total_yr,
                                f'sr{yr}.zip', 'All 311 requests, ward-parseable rows only'])

        # 2026 YTD (Jan-Sep) and 2025 Jan-Sep comparison
        ytd_2026_total = sum(three11_types.get(wn, {}).get(2026, {}).values())
        ytd_2025_total = sum(
            cnt for rt, cnt in three11_types.get(wn, {}).get(2025, {}).items()
        )
        # For Jan-Sep 2025, we need to re-filter (the 2025 full-year is already loaded)
        # We stored full-year 2025 above; for fair YTD comparison we compute Jan-Sep 2025 below
        ytd_2026_road  = three11_road.get(wn, {}).get(2026, 0)
        three11_by_year['2026_ytd'] = {
            'months': 'Jan-Sep',
            'total': ytd_2026_total,
            'road_related': ytd_2026_road,
        }

        # KSI
        ksi_by_year = {}
        for yr in KSI_YEARS:
            kd = (ksi_ward.get(wn, {}).get(yr)) or {}
            ksi_by_year[yr] = {
                'collisions':  kd.get('total', 0),
                'pedestrian':  kd.get('ped', 0),
                'cyclist':     kd.get('cyc', 0),
            }
            audit_rows.append([wn, wname, f'ksi_collisions_{yr}', kd.get('total',0),
                                'motor-vehicle-collisions-ksi-4326.csv',
                                'Fatal+Non-Fatal acclass; unique collision_id per ward'])

        # City KSI rates
        city_ksi = {yr: (ksi_city.get(yr) or {}) for yr in KSI_YEARS}

        # Jan-Sep 2025 KSI (for comparison with Jan-Sep 2026)
        ksi_ytd25_ward = ksi_ward_ytd25.get(wn, {'total':0,'ped':0,'cyc':0})
        ksi_ytd25_city = ksi_city_ytd25

        ward['issues'] = {
            'permits_note': (
                'Not available per ward. The building permits file uses a city map-grid code '
                '(WARD_GRID, e.g. "E2022") rather than the 25-ward numbering system, and '
                'contains no latitude/longitude coordinates. Ward-level permit counts cannot '
                'be derived from this source without a lookup table or geocoding service.'
            ),
            'crime': {
                'years': crime_by_year,
                'ytd_jan_sep_2024': {
                    'count':        ytd24_count,
                    'rate_per_1k':  ytd24_rate,
                },
                'city_rate_per_1k': city_crime_rates,
                'city_ytd_jan_sep_2024': {
                    'count':        crime_city_ytd24,
                    'rate_per_1k':  city_ytd24_rate,
                },
                'city_jan_sep_2025': {
                    'count':        crime_city.get(2025, 0),
                    'rate_per_1k':  round(crime_city.get(2025, 0) / city_pop * 1000, 2) if city_pop else None,
                },
                'categories': sorted(CRIME_CATEGORIES),
                'source': 'major-crime-indicators.csv',
                'note': (
                    'Police-reported offences by date of occurrence, located at the nearest '
                    'intersection for privacy. Rates use 2021 Census population. '
                    f'Dropped (missing/zero coords): {crime_drop}'
                ),
            },
            'three11': {
                'years': three11_by_year,
                'road_types_included': sorted(ROAD_311_TYPES),
                'source': '311 Service Requests ZIP files 2022-2026',
                'note': (
                    '311 covers 6 City divisions only. Results are shaped by housing type — '
                    'areas with more houses report more curbside issues. Shows what residents '
                    'reported, not how good City services are.'
                ),
            },
            'ksi': {
                'years': ksi_by_year,
                'ytd_jan_sep_2025': {
                    'collisions': ksi_ytd25_ward['total'],
                    'pedestrian': ksi_ytd25_ward['ped'],
                    'cyclist':    ksi_ytd25_ward['cyc'],
                },
                'city': city_ksi,
                'city_ytd_jan_sep_2025': {
                    'collisions': ksi_ytd25_city['total'],
                    'pedestrian': ksi_ytd25_city['ped'],
                    'cyclist':    ksi_ytd25_city['cyc'],
                },
                'source': 'motor-vehicle-collisions-ksi-4326.csv',
                'note': (
                    'Unique collisions (not people) where acclass is Fatal or Non-Fatal Injury. '
                    'Pedestrian/cyclist columns indicate any such road user was involved. '
                    f'Blank ward (122 rows): resolved by spatial join. Dropped (no ward): {dict(ksi_drop)}'
                ),
            },
        }

    # Compute Jan-Sep 2025 311 totals for YTD comparison — needs separate pass
    print('\nComputing Jan-Sep 2025 311 totals for YTD comparison…')
    ytd_2025_ward_total = defaultdict(int)
    ytd_2025_ward_road  = defaultdict(int)
    ytd_2025_city       = 0
    with zipfile.ZipFile(os.path.join(RAW, '311', 'sr2025.zip')) as z:
        nm = z.namelist()[0]
        with z.open(nm) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='latin-1', errors='replace'))
            for row in reader:
                cdate = row.get('Creation Date', '')[:10]
                if not cdate or cdate > '2025-09-30':
                    continue
                ytd_2025_city += 1
                wv = row.get('Ward', '').strip()
                wn = parse_ward_311(wv)
                rt = row.get('Service Request Type', '').strip()
                if wn and 1 <= wn <= 25:
                    ytd_2025_ward_total[wn] += 1
                    if rt in ROAD_311_TYPES:
                        ytd_2025_ward_road[wn] += 1

    print(f'  2025 Jan-Sep: city total={ytd_2025_city:,}')

    # Store Jan-Sep 2025 in each ward's issues
    for ward in ward_data:
        wn = ward['ward_num']
        ward['issues']['three11']['years']['2025_ytd_for_comparison'] = {
            'months': 'Jan-Sep',
            'total': ytd_2025_ward_total.get(wn, 0),
            'road_related': ytd_2025_ward_road.get(wn, 0),
        }

    # ── Write wards.json ────────────────────────────────────────────────────────
    with open(WARDS_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'\nUpdated {WARDS_JSON}')

    # ── Append to audit CSV ─────────────────────────────────────────────────────
    append_audit(audit_rows)
    print(f'Appended {len(audit_rows)} rows to data_audit.csv')

    # ── Summary ─────────────────────────────────────────────────────────────────
    print('\n=== Summary ===')
    print(f'Crime:     {len(CRIME_YEARS)} years, {sum(crime_city.values()):,} total records placed/dropped')
    print(f'311:       2022-2026 (2026 Jan-Sep), {sum(three11_city.values()):,} total rows')
    print(f'KSI:       {len(KSI_YEARS)} years incl 2026 YTD')
    print(f'Permits:   NOT AVAILABLE per ward (WARD_GRID mismatch, no coords)')


if __name__ == '__main__':
    main()
