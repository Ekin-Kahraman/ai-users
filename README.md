# AI Users

A research tool for visually exploring estimated generative AI usage by country. This is not a report, a paper, or an official statistical publication - it is a development tool for exploring public AI diffusion data visually.

**Live demo: run locally with `cd site && python3 -m http.server 8000`**

## What's here

The current build covers **147 countries/economies** from Microsoft's public Q1 2026 AI diffusion appendix, spanning about **5.3B** working-age people in the source-covered countries. We join that usage table to UN population data and World Bank infrastructure indicators, then build an interactive treemap where each rectangle's **area** is proportional to estimated Q1 2026 AI users and **colour** shows the selected metric - toggle between total users, AI user share, recent momentum, infrastructure readiness, model gap, access headroom, internet intensity, and region.

The headline estimate is about **948.1M** Q1 2026 working-age AI users in the countries covered by the source data.

## Model-powered colouring

The repo includes a small data pipeline for writing custom country-level metrics into the static site. The default layers are source-backed metrics and transparent model outputs:

- **Users** - estimated Q1 2026 AI users.
- **2026 Share** - Q1 2026 AI diffusion share.
- **Momentum** - percentage-point growth from H2 2025 to Q1 2026.
- **Readiness** - a weighted score from internet access, electricity access, and GDP per head.
- **Model Gap** - actual Q1 2026 AI share minus an infrastructure-only modelled share.
- **Headroom** - reachable working-age non-users under the access ceiling model.
- **Internet Intensity** - AI share divided by internet access.
- **Region** - World Bank region grouping.

**What these estimates are NOT:**

- They do **not** count every regular, paid, daily, enterprise, or heavy AI user.
- They do **not** predict future adoption.
- They do **not** use a fabricated 2024 country baseline. The comparable Microsoft country series in this build starts at H1 2025, so the growth series is H1 2025 -> H2 2025 -> Q1 2026.
- They do **not** imply that infrastructure causes adoption. The model gap is directional and exploratory.
- Model-gap scoring is only calculated for countries with complete internet, electricity, and GDP inputs.
- They are modelled estimates from public sources, not official statistics.

## Data pipeline

1. **Fetch AI shares** (`build_site_data.py`) - downloads Microsoft's Q1 2026 AI diffusion PDF and caches it in `data/raw/`.
2. **Extract table** (`build_site_data.py`) - uses `pdftotext -layout` to parse the report appendix into H1 2025, H2 2025, and Q1 2026 country shares.
3. **Fetch population denominators** (`build_site_data.py`) - downloads UN World Population Prospects working-age population data through Our World in Data.
4. **Fetch infrastructure data** (`build_site_data.py`) - downloads World Bank country metadata plus internet access, electricity access, and GDP per capita indicators.
5. **Join and model** (`build_site_data.py`) - matches countries by ISO3 code, computes estimated users, growth, readiness, headroom, internet intensity, and model gap.
6. **Build site data** (`build_site_data.py`) - writes `country_usage.csv`, `site/data.json`, and `site/data.js`.
7. **Website** (`site/index.html`) - renders the interactive treemap as a static site with no build step.

## Key files

| File | Description |
|------|-------------|
| `country_usage.csv` | Generated country table with estimates, growth metrics, infrastructure fields, model gap, ranks, and source URL |
| `site/data.json` | Generated JSON consumed by the static frontend |
| `site/data.js` | Generated browser fallback so `site/index.html` can be opened directly from disk |
| `site/index.html` | Static treemap visualisation |
| `build_site_data.py` | Reproducible data pipeline using public source URLs |
| `make_prompt.py` | Generates `prompt.md` from the built data |
| `prompt.md` | Data-grounded prompt for discussing the estimates in an LLM |
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

World Bank internet access is source-backed for **145** of the 147 countries. **138** values are from 2024, **7** use the latest older available World Bank value, and **Taiwan** plus **French Guiana** are missing from the World Bank infrastructure join.

## Estimate definitions

```text
estimated_ai_users = ai_share_pct / 100 * working_age_population
```

The main current estimate uses:

```text
estimated_ai_users_q1_2026 =
  ai_share_q1_2026_pct / 100 * working_age_population_2026
```

Comparable growth metrics use the Microsoft appendix periods:

```text
h1_to_h2_growth_pct = (h2_users - h1_users) / h1_users * 100
h2_to_q1_growth_pct = (q1_users - h2_users) / h2_users * 100
h1_to_q1_growth_pct = (q1_users - h1_users) / h1_users * 100
```

The source-covered total moved from about **798.0M** users in H1 2025 to **862.3M** in H2 2025 and **948.1M** in Q1 2026.

## Infrastructure model

```text
readiness_score =
  0.55 * internet_user_pct
+ 0.25 * electricity_access_pct
+ 0.20 * log_scaled_gdp_per_capita
```

```text
access_ceiling_pct = min(internet_user_pct, electricity_access_pct)
access_headroom_users =
  max(0, access_ceiling_pct - ai_share_q1_2026_pct)
  / 100 * working_age_population_2026
```

```text
modelled_ai_share_q1_2026_pct =
  ridge regression estimate on logit(ai_share_q1_2026_pct)
  using internet access, electricity access, and log-scaled GDP per head

diffusion_gap_pp =
  ai_share_q1_2026_pct - modelled_ai_share_q1_2026_pct
```

The model currently scores **145** of the 147 source-covered countries. Countries missing any infrastructure input are shown as unmodelled rather than imputed.

## LLM prompt

[`prompt.md`](prompt.md) packages the source definition, caveats, summary statistics, top countries, model outputs, citations, and CSV into a single file designed to be pasted into an LLM. Regenerate it with:

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
# Rebuild source data, CSV, and site payloads
python3 build_site_data.py

# Regenerate the LLM prompt
python3 make_prompt.py

# Serve the site locally
cd site && python3 -m http.server 8000
```

Then open `http://localhost:8000`. You can also open `site/index.html` directly in a browser because the build writes `site/data.js`.

## Attribution and compliance

Inspired by [Andrej Karpathy's `karpathy/jobs`](https://github.com/karpathy/jobs), especially the small static-site shape: a reproducible data pipeline, generated site data, and an interactive treemap.

Compliance check, 2026-05-30:

- GitHub reports `karpathy/jobs` with `license: null`.
- The upstream root currently has no `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `COPYING`, `NOTICE`, or `SECURITY.md` file.
- GitHub's security advisory API returned zero public advisories for `karpathy/jobs`.
- Because there is no explicit upstream licence, this project should credit the inspiration and avoid copying upstream code or README prose verbatim.
