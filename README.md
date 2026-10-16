# Toronto Ward Facts

A non-partisan, static website presenting official City of Toronto municipal election
and census data for all 25 wards. Served from the `/docs` folder via GitHub Pages.

Live site: https://pravikant23.github.io/toronto-ward-accountability/

## What it shows

Each of the 25 ward pages includes:

- **At a glance** — registered voters, ballots cast, 2022 turnout vs city average and vs 2018
- **2022 election results** — all candidates with vote counts and share bars
- **2021 Census** — population, median age, median household income, housing tenure, top 3 non-official languages (Statistics Canada custom tabulation)
- **Councillor record** — City Council attendance %, budget adoption vote for each year (2023–2026), and all close votes (margin ≤ 3) during the term
- **Council powers** — what City Council does and does not control (factual)
- **Questions to ask candidates** — generic civic questions (no platforms or party affiliation)
- **How to vote in 2026** — official toronto.ca links only
- **Sources** — data provenance for every field, with Open Data links

The index page shows a city-wide SVG map (clickable), city-wide stats, and a turnout chart sorted by ward.

Every number comes from a City of Toronto or Statistics Canada open-data file. Nothing is estimated or invented.

## How to rebuild

Three large raw data files are excluded from git (see `.gitignore`) and must be
downloaded before running step 3. Download them from the open data links in the
Data sources table below and place them in `data/raw/`:

- `major-crime-indicators.csv` (~133 MB)
- `motor-vehicle-collisions-ksi-4326.csv` (~10 MB)
- `data/raw/311/sr{2022..2026}.zip` (five ZIP files, ~6 MB each) from the 311 dataset

```bash
# Prerequisites: Python 3 + openpyxl + shapely
pip3 install openpyxl shapely

# Step 1: Build wards.json from raw source files
python3 data/build_data.py

# Step 2: Add council voting data (budget votes, close votes)
python3 data/add_key_votes.py

# Step 3: Add issue data (311, crime, KSI) to wards.json
#         Downloads raw CSVs/ZIPs to data/raw/ if not already present.
#         Prints spot-check for Ward 1 and Ward 11 — review before proceeding.
python3 data/build_issues.py

# Step 4: Validate (hard-fail — must pass before building HTML)
python3 data/validate.py

# Step 5: Generate all HTML and CSS
python3 build.py
```

Output goes to `docs/`. Commit and push to deploy via GitHub Pages.

## How to update for 2026 results

After election night (October 26, 2026), the City publishes official results to Open Data.

1. Download the 2026 official results from  
   <https://open.toronto.ca/dataset/election-results-official/>  
   and the 2026 voter turnout statistics from  
   <https://open.toronto.ca/dataset/elections-voter-statistics/>  
   Save both to `data/raw/`.

2. Update `data/build_data.py` to parse the 2026 files (format expected to match 2022).

3. Run steps 1–4 above.

4. Update `CHECKED` in `build.py` to the date you ran the rebuild.

5. Commit and push.

## Data sources

| Data | File | Open Data URL |
|------|------|---------------|
| 2022 voter turnout | `2022_voter_turnout_statistics_final.xlsx` | <https://open.toronto.ca/dataset/elections-voter-statistics/> |
| 2018 voter turnout | `2018_Voter_Turnout_Statistics_FINAL.XLSX` | <https://open.toronto.ca/dataset/elections-voter-statistics/> |
| 2022 official results | `2022_Toronto_Poll_By_Poll_Councillor.xlsx` | <https://open.toronto.ca/dataset/election-results-official/> |
| Current councillors | `2022-2026-elected-officials.json` | <https://open.toronto.ca/dataset/elected-officials-contact-information/> |
| By-election results | Individual by-election .xlsx files | <https://open.toronto.ca/dataset/elections-official-by-election-results/> |
| 2021 Census ward profiles | `ward-profiles-2021-census.xlsx` | <https://open.toronto.ca/dataset/ward-profiles-2011-2021-census/> |
| Council voting record | `council-voting-2022-2026.csv` | <https://open.toronto.ca/dataset/members-of-toronto-city-council-voting-record/> |
| Council attendance | `council-attendance-2022-2026.csv` | <https://open.toronto.ca/dataset/members-of-toronto-city-council-meeting-attendance/> |
| Ward boundaries | `city-wards-4326.geojson` | <https://open.toronto.ca/dataset/city-wards/> |
| Major crime indicators (2018–2025) | `major-crime-indicators.csv` | <https://open.toronto.ca/dataset/major-crime-indicators/> |
| Motor vehicle collisions — KSI (2018–2026) | `motor-vehicle-collisions-ksi-4326.csv` | <https://open.toronto.ca/dataset/motor-vehicle-collisions-involving-killed-or-seriously-injured-persons/> |
| 311 service requests (2022–2026) | `data/raw/311/sr{year}.zip` | <https://open.toronto.ca/dataset/311-service-requests-customer-initiated/> |

All data published under the [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).

## Turnout formula

**Turnout % = (Number Voted + Declined Ballots) ÷ Total Eligible Electors × 100**

This matches the City's own definition in the voter statistics file.
Subdivisions 97 (mail-in), 98 and 99 (advance vote) are included in the vote count
but not the eligible-elector total (those voters are already counted in their home
subdivisions).

City-wide 2022: 1,898,750 registered — 563,563 ballots cast — 29.68% turnout.

## By-election notes

- **Ward 15 Don Valley West:** Rachel Chernos Lin won the **November 4, 2024 by-election**, succeeding Jaye Robinson.
- **Ward 20 Scarborough Southwest:** Parthi Kandavel won the **November 30, 2023 by-election**, succeeding Gary Crawford.
- **Ward 25 Scarborough-Rouge Park:** Neethan Shan won the **September 29, 2025 by-election**, succeeding Jennifer McKelvie.

## Licence

Code: MIT. Data: [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).

## Contact

Corrections: ravi@perimtr.ca
