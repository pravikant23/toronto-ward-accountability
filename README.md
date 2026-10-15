# Toronto Ward Facts

A non-partisan, static website presenting official City of Toronto municipal election data
for all 25 wards. Served from the `/docs` folder via GitHub Pages.

Live site: https://pravikant23.github.io/toronto-ward-accountability/

## What It Shows

- **2022 voter turnout** (registered voters, ballots cast, turnout %) per ward
- **2022 official councillor results** – top 5 candidates with vote counts and percentages
- **Current councillor** – with a note where a by-election changed the seat after 2022
- **Links to official 2026 election tools** – candidate list, MyVote, advance voting, ID requirements

Every number comes from a City of Toronto open-data file. Nothing is estimated.

## How to Rebuild

```bash
# Prerequisites: Python 3 + openpyxl
pip3 install openpyxl

# Rebuild the entire docs/ folder from data/wards.json
python3 build.py
```

The raw source files in `data/raw/` are the original downloads from the City's open-data portal.
`build.py` reads `data/wards.json` (compiled from those raw files) and writes all HTML to `docs/`.

## How to Update for 2026 Results

After election night (October 26, 2026), the City publishes official results to Open Data.

1. Download the 2026 official results ZIP from  
   https://open.toronto.ca/dataset/election-results-official/  
   and save it to `data/raw/`.

2. Download the 2026 voter turnout statistics from  
   https://open.toronto.ca/dataset/elections-voter-statistics/  
   and save it to `data/raw/`.

3. Update `build.py` to parse the 2026 files (the format should be similar to 2022).

4. Rebuild: `python3 build.py`

5. Update the `CHECKED` date in `build.py` to the date you ran the rebuild.

6. Commit and push.

## Data Sources

| Data | File | Open Data URL |
|------|------|---------------|
| 2022 voter turnout | `2022_voter_turnout_statistics_final.xlsx` | https://open.toronto.ca/dataset/elections-voter-statistics/ |
| 2022 official results | `2022-results.zip` | https://open.toronto.ca/dataset/election-results-official/ |
| Current councillors | `2022-2026-elected-officials-contact-info.json` | https://open.toronto.ca/dataset/elected-officials-contact-information/ |
| By-election results | individual .xlsx files | https://open.toronto.ca/dataset/elections-official-by-election-results/ |

All data is published by the City of Toronto under the
[Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).

## Turnout Formula

**Turnout % = (Number Voted + Declined Ballots) ÷ Total Eligible Electors × 100**

This matches the City's own definition in the voter statistics readme tab.
Subdivisions 97 (mail-in), 98 and 99 (advance vote locations) are included in the
vote count but not the eligible-elector total (those voters are already counted in
their home subdivisions).

## By-Election Notes

- **Ward 15 Don Valley West:** Rachel Chernos Lin won the **November 4, 2024 by-election**.
- **Ward 20 Scarborough Southwest:** Parthi Kandavel won the **November 30, 2023 by-election**.
- **Ward 25 Scarborough-Rouge Park:** Neethan Shan won the **September 29, 2025 by-election**.

## Licence

Code: MIT. Data: [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).

## Contact

Corrections: ravi@perimtr.ca
