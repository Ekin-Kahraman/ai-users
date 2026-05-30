# AI Users

A research tool for visually exploring estimated generative AI usage by country. This is not a report, a paper, or an official statistical publication - it is a development tool for exploring public AI diffusion data visually.

**Live demo: [ekin-kahraman.github.io/ai-users](https://ekin-kahraman.github.io/ai-users/)**

## What's here

The current build covers **147 countries/economies** from Microsoft's public Q1 2026 AI diffusion appendix. It joins that usage table to UN working-age population data and World Bank infrastructure indicators, then builds an interactive treemap where each rectangle's **area** is proportional to estimated Q1 2026 AI users and **colour** shows the selected metric.

The headline estimate is about **948.1M** Q1 2026 working-age AI users across the countries covered by the source data.

## Model-powered colouring

The repo includes a reproducible pipeline for writing country-level metrics into a static treemap. The default layers are:

- **Users** - estimated Q1 2026 AI users.
- **Adoption Rate** - Q1 2026 AI diffusion share.
- **Momentum** - percentage-point growth from H2 2025 to Q1 2026.
- **Readiness** - weighted internet access, electricity access, and GDP per head.
- **Above Expected** - actual Q1 2026 AI share minus an infrastructure-only expected share.
- **Potential Users** - reachable working-age non-users under the access ceiling model.
- **Internet Intensity** - AI share divided by internet access.
- **Region** - World Bank region grouping.

`scores.json` is the deterministic score artefact for these model layers. It is the local equivalent of the generated score file in [karpathy/jobs](https://github.com/karpathy/jobs), but the scores here are formula/model outputs rather than LLM judgements.

**What these estimates are NOT:**

- They do **not** count every regular, paid, daily, enterprise, or heavy AI user.
- They do **not** predict future adoption.
- They do **not** use a fabricated 2024 country baseline. The comparable Microsoft country series in this build starts at H1 2025, so the growth series is H1 2025 -> H2 2025 -> Q1 2026.
- They do **not** imply that infrastructure causes adoption. Above/below expected adoption is directional and exploratory.
- They are modelled estimates from public sources, not official statistics.

## Data pipeline

1. **Fetch AI shares** (`build_site_data.py`) - downloads Microsoft's Q1 2026 AI diffusion PDF and caches it in `data/raw/`.
2. **Extract table** (`build_site_data.py`) - uses `pdftotext -layout` to parse the report appendix into H1 2025, H2 2025, and Q1 2026 country shares.
3. **Fetch population denominators** (`build_site_data.py`) - downloads UN World Population Prospects working-age population data through Our World in Data.
4. **Fetch infrastructure data** (`build_site_data.py`) - downloads World Bank country metadata plus internet access, electricity access, and GDP per capita indicators.
5. **Join and model** (`build_site_data.py`) - computes estimated users, growth, readiness, potential users, internet intensity, and above/below expected adoption.
6. **Build score and audit files** (`build_site_data.py`) - writes `scores.json` and `data_audit.json`.
7. **Build site data** (`build_site_data.py`) - writes `country_usage.csv`, `site/data.json`, and `site/data.js`.
8. **Website** (`site/index.html`) - renders the interactive treemap as a static site with no build step.

## Key files

| File | Description |
|------|-------------|
| `country_usage.csv` | Generated country table with estimates, growth metrics, infrastructure fields, model gaps, ranks, and source URL |
| `scores.json` | Deterministic country score artefact for readiness, expected adoption, diffusion gap, and headroom |
| `data_audit.json` | Generated coverage and validation audit: source years, missing infrastructure inputs, formula checks, and totals checks |
| `site/data.json` | Generated JSON consumed by the static frontend |
| `site/data.js` | Generated browser fallback so `site/index.html` can be opened directly from disk |
| `site/index.html` | Static treemap visualisation |
| `build_site_data.py` | Reproducible data pipeline using public source URLs |
| `make_prompt.py` | Generates `prompt.md` from the built data |
| `prompt.md` | Data-grounded prompt for discussing the estimates in an LLM |
| `launch.md` | Copy-ready launch notes and posts for sharing the project |
| `data/raw/` | Cached downloaded source PDF, extracted text, CSV, and JSON files |

## Source stack

| Layer | Source | Used for |
|------|--------|----------|
| AI diffusion | [Microsoft AI Economy Institute, Global AI Diffusion: Q1 2026 Trends and Insights](https://www.microsoft.com/en-us/research/wp-content/uploads/2026/05/Microsoft-AI-Diffusion-Report-2026-Q1.pdf) | H1 2025, H2 2025, Q1 2026 AI diffusion shares and Q1 change |
| Population denominator | [UN World Population Prospects via Our World in Data](https://ourworldindata.org/grapher/dependency-age-groups-to-2100) | Working-age population, age 15-64, 2025 and 2026 |
| Internet access | [World Bank WDI: Individuals using the Internet](https://data.worldbank.org/indicator/IT.NET.USER.ZS) | Latest available value up to 2024 |
| Electricity access | [World Bank WDI: Access to electricity](https://data.worldbank.org/indicator/EG.ELC.ACCS.ZS) | Latest available value up to 2024 |
| GDP per head | [World Bank WDI: GDP per capita, current US dollars](https://data.worldbank.org/indicator/NY.GDP.PCAP.CD) | Latest available value up to 2024, log-scaled in the model |
| Regions and income groups | [World Bank country API](https://api.worldbank.org/v2/country) | Display metadata and grouping |

`data_audit.json` currently reports World Bank internet access for **145** of 147 countries. **138** internet values are from 2024, **7** use the latest older available World Bank value, and **Taiwan** plus **French Guiana** are missing from the World Bank infrastructure join.

## Estimate definitions

```text
estimated_ai_users = ai_share_pct / 100 * working_age_population
```

```text
readiness_score =
  0.55 * internet_user_pct
+ 0.25 * electricity_access_pct
+ 0.20 * log_scaled_gdp_per_capita
```

```text
modelled_ai_share_q1_2026_pct =
  ridge regression estimate on logit(ai_share_q1_2026_pct)
  using internet access, electricity access, and log-scaled GDP per head

diffusion_gap_pp =
  ai_share_q1_2026_pct - modelled_ai_share_q1_2026_pct
```

The source-covered total moved from about **798.0M** users in H1 2025 to **862.3M** in H2 2025 and **948.1M** in Q1 2026.

## LLM prompt

[`prompt.md`](prompt.md) packages the source definition, caveats, summary statistics, regional and income-group cuts, model outputs, source coverage audit, citations, and CSV into a single file designed to be pasted into an LLM. Regenerate it with:

```bash
python3 make_prompt.py
```

## Setup

No Python packages are required beyond the standard library.

```bash
python3 --version
```

Python 3.10+ is recommended. To rebuild from the Microsoft PDF, install Poppler so `pdftotext` is available:

```bash
brew install poppler
```

## Usage

```bash
# Rebuild source data, CSV, score, audit, and site payloads
python3 build_site_data.py

# Regenerate the LLM prompt
python3 make_prompt.py

# Serve the site locally
cd site && python3 -m http.server 8000
```

Then open `http://localhost:8000`. You can also open `site/index.html` directly in a browser because the build writes `site/data.js`.

## Attribution and compliance

Inspired by [Andrej Karpathy's `karpathy/jobs`](https://github.com/karpathy/jobs), especially the small static-site shape: a reproducible data pipeline, generated site data, generated score/prompt artefacts, and an interactive treemap. When in doubt about the intended benchmark shape, compare against that repo rather than copying its code or prose.

Technical note: the site is static HTML, CSS, and JavaScript. There is no Java runtime; JavaScript is used because it runs natively in browsers and drives the interactive treemap.

Compliance check, 2026-05-30:

- GitHub reports `karpathy/jobs` with `license: null`.
- The upstream root currently has no `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `COPYING`, `NOTICE`, or `SECURITY.md` file.
- GitHub's security advisory API returned zero public advisories for `karpathy/jobs`.
- Because there is no explicit upstream licence, this project credits the inspiration and does not copy upstream code or README prose verbatim.
