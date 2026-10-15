# Toronto Ward Accountability Platform

A static website showing ward-level political accountability in Toronto. See if your neighbourhood improved under your elected councillor, what they spent money on, and what projects they brought in during their 2022–2026 term.

**Live:** https://pravikant23.github.io/toronto-ward-accountability

---

## What This Is

This is a **static HTML site** (no server, no database) with 25 ward report cards. Each card shows:

1. **Ward Overview** — Councillor name, party, 2022 election results (top 5 candidates & vote counts)
2. **Neighbourhood Metrics** — Schools, transit, trees, cycling, safety (2022 vs 2026 comparison)
3. **Budget Snapshot** — Discretionary spend, capital projects, priorities
4. **Development Pipeline** — Rezoning, approvals, completions
5. **The Narrative** — Did the ward improve? Mixed? Declined? (Based on verified data only)
6. **Community Discussion** — Disqus comments per ward for resident engagement

---

## Files & Structure

```
docs/
├── index.html              # Homepage: all 25 wards at a glance
├── ward-1.html             # Ward 1 report card
├── ward-2.html             # Ward 2 report card
├── ... (ward-3 through ward-25)
└── README.md               # This file
```

---

## How to Deploy to GitHub Pages

### Step 1: Clone/Create Your Repository

```bash
git clone https://github.com/pravikant23/toronto-ward-accountability.git
cd toronto-ward-accountability
```

(Or create a new repo if this is your first time.)

### Step 2: Replace the `docs` Folder

Copy all files from this `docs/` folder into your repo's `docs/` folder.

### Step 3: Enable GitHub Pages

1. Go to your GitHub repo settings
2. Scroll down to **"GitHub Pages"**
3. Under **"Source"**, select **`main` branch** → **`/docs` folder**
4. Click **Save**

Your site will be live at: `https://pravikant23.github.io/toronto-ward-accountability`

### Step 4: Commit & Push

```bash
git add docs/
git commit -m "Add Toronto Ward Accountability Platform"
git push origin main
```

Done! 🎉

---

## Data Sources

All data is sourced from **Toronto Open Data** and verified public records:

- **Election Results (2022):** [Toronto Elections Official Results](https://open.toronto.ca/dataset/election-results-official/)
- **Councillor Info:** [toronto.ca](https://www.toronto.ca/city-government/elections/)
- **Neighbourhood Metrics:** [Toronto Open Data Portal](https://open.toronto.ca/)
- **Development & Budgets:** Toronto CKAN API

---

## What's "In Progress"

The MVP (Minimum Viable Product) has launched with:
- ✅ All 25 ward pages
- ✅ 2022 election results & councillor info
- ✅ Professional, mobile-friendly design
- ✅ Data sourcing & transparency

Coming next:
- 📊 Neighbourhood metrics (schools, transit, trees, cycling, safety)
- 💰 Budget & discretionary spending breakdown
- 🏗️ Development approvals & completions
- 📈 Year-over-year comparisons (2022 → 2026)
- 💬 Disqus comment threads per ward

---

## Key Design Decisions

1. **No Councillor Photos** — Focus on data, not personality
2. **Top 5 Candidates by Vote %** — Shows electoral competitiveness
3. **2022–2026 Timeline Only** — Current councillor term
4. **Static HTML (No Backend)** — Fast, free, easy to deploy
5. **Disqus Comments** — Community engagement with zero backend
6. **Correlation, Not Causation** — Honest about data limits
7. **Every Claim Sourced** — Full transparency

---

## How to Expand or Modify

### Edit a Ward Card

1. Open `docs/ward-X.html` in a text editor
2. Find the relevant section (e.g., "Section 2: Neighbourhood Metrics")
3. Replace placeholder text with real data
4. Save & push to GitHub

### Add a New Data Section

1. Copy the structure from an existing section
2. Add the new `<section>` block to all 25 ward files
3. Or regenerate all files using the `generate_site.py` script (requires Python 3)

### Regenerate All Ward Pages

If you have raw data (CSV/JSON of election results, budgets, etc.), use `generate_site.py`:

```bash
python3 -I generate_site.py
```

The script will regenerate all 25 `ward-X.html` files from data in `ward_data.json`.

---

## Features

### Mobile-Friendly
- Responsive design works on phones, tablets, desktops
- Touch-friendly navigation
- Readable text at all screen sizes

### Accessible
- High-contrast design
- Clear hierarchy
- Semantic HTML

### Fast
- ~50 KB per ward page
- No external dependencies (except Disqus for comments)
- GitHub Pages CDN = instant load times globally

### Verifiable
- Every data point is sourced
- Links to original data
- No opinion, only facts

---

## Contact & Contributions

**Creator:** Pravikant  
**Email:** sonaviation@gmail.com  
**GitHub:** @pravikant23  

Want to help? Contributions welcome:
- Find missing or outdated data
- Add neighbourhood metrics
- Improve design
- Report bugs

---

## License

Public Domain / CC0. Use freely.

---

## FAQ

**Q: Why no interactive maps or filters?**  
A: MVP scope. Static is fast & maintainable. Phase 2 can add interactivity.

**Q: Can I download the data?**  
A: All data comes from [Toronto Open Data](https://open.toronto.ca/). Download directly from there.

**Q: How often is the data updated?**  
A: Currently manual snapshots. Real-time updates coming in Phase 2.

**Q: How do I leave feedback?**  
A: Comment on your ward's page (Disqus) or email sonaviation@gmail.com.

---

**Built:** October 14, 2026  
**Status:** MVP / v1.0 Launch  
**Next Update:** Phase 2 (Q4 2026)
