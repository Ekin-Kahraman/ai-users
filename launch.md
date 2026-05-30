# Launch Notes

Use this when sharing the project publicly. The benchmark shape is [karpathy/jobs](https://github.com/karpathy/jobs): one clear demo, one clear source story, generated artefacts in the repo, and caveats that do not overclaim.

## Links

- Live demo: https://ekin-kahraman.github.io/ai-users/
- GitHub repo: https://github.com/Ekin-Kahraman/ai-users
- Benchmark inspiration: https://github.com/karpathy/jobs

## One-line pitch

AI Users: an interactive country treemap estimating generative AI usage from Microsoft's Q1 2026 AI diffusion data, UN population data, and World Bank infrastructure indicators.

## Hacker News

Title:

```text
Show HN: AI Users - estimated generative AI usage by country
```

URL:

```text
https://ekin-kahraman.github.io/ai-users/
```

First comment:

```text
I built a small static research tool for exploring estimated generative AI usage by country.

The main usage source is Microsoft's Q1 2026 Global AI Diffusion appendix. I join it to UN working-age population data and World Bank internet, electricity, GDP, region, and income metadata. The page is a treemap: area is estimated Q1 2026 AI users, colour is the selected layer.

Important caveat: this is not an official count of regular AI users. The country-level comparable source series starts at H1 2025, so I show H1 2025 -> H2 2025 -> Q1 2026 rather than inventing a 2024 baseline.

Repo: https://github.com/Ekin-Kahraman/ai-users
Inspired by the shape of karpathy/jobs: https://github.com/karpathy/jobs
```

## X / Twitter

```text
AI Users: a country-level treemap of estimated generative AI usage.

948M estimated working-age AI users across 147 countries in Q1 2026, using Microsoft AI diffusion data + UN population + World Bank infrastructure indicators.

Live: https://ekin-kahraman.github.io/ai-users/
Repo: https://github.com/Ekin-Kahraman/ai-users
```

## Reddit

Title:

```text
I built an interactive country treemap for estimated generative AI usage
```

Body:

```text
I built a small static site for exploring estimated generative AI usage by country.

Data sources:
- Microsoft AI Economy Institute Q1 2026 AI diffusion appendix
- UN World Population Prospects via Our World in Data
- World Bank internet access, electricity access, GDP per capita, region, and income metadata

The visual area is estimated Q1 2026 AI users. Colour layers include adoption rate, H2 2025 to Q1 2026 momentum, readiness, above/below expected adoption, potential users, internet intensity, and region.

Caveat: this is a directional prototype, not official statistics. I also do not show 2024 growth because the comparable Microsoft country series in this build starts at H1 2025.

Live: https://ekin-kahraman.github.io/ai-users/
Repo: https://github.com/Ekin-Kahraman/ai-users
```

## GitHub Repo Description

```text
A research tool for visually exploring estimated generative AI usage by country.
```

## Suggested Topics

```text
ai, generative-ai, data-visualization, public-data, static-site, treemap, world-bank, microsoft, github-pages
```

## Launch Checklist

- Live page loads and shows `AI Users`.
- GitHub repo is public.
- `README.md` has live demo, source stack, pipeline, generated files, and attribution.
- `scores.json`, `data_audit.json`, `country_usage.csv`, `site/data.json`, and `prompt.md` are committed.
- Top site link points to this repo.
- Footer attribution links to `karpathy/jobs`.
- Do not claim 2024 -> 2025 country growth unless a comparable 2024 source is added.
