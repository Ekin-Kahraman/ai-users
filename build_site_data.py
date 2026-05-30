"""
Build the country-level dataset for the static site.

The main usage source is Microsoft's Global AI Diffusion Q1 2026 PDF. The
script extracts its appendix table, joins public population and infrastructure
datasets, then writes:

    country_usage.csv
    site/data.json
    site/data.js
    scores.json
    data_audit.json
    data/raw/*

Usage:
    python3 build_site_data.py
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
SITE_DIR = ROOT / "site"

MICROSOFT_Q1_2026_PDF_URL = (
    "https://www.microsoft.com/en-us/research/wp-content/uploads/2026/05/"
    "Microsoft-AI-Diffusion-Report-2026-Q1.pdf"
)
POPULATION_URL = (
    "https://ourworldindata.org/grapher/"
    "dependency-age-groups-to-2100.csv?csvType=full&useColumnShortNames=true"
)
POPULATION_METADATA_URL = (
    "https://ourworldindata.org/grapher/"
    "dependency-age-groups-to-2100.metadata.json"
)
WORLD_BANK_COUNTRIES_URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"
WORLD_BANK_INDICATOR_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=20000"

AI_BASE_YEAR = 2025
AI_CURRENT_YEAR = 2026
USER_AGENT = "ai-country-usage prototype/0.2 (+https://github.com/)"

POP_ESTIMATE_COLUMN = "population__sex_all__age_15_64__variant_estimates"
POP_PROJECTED_COLUMN = "population__sex_all__age_15_64__variant_medium__projected"
WORLD_BANK_CUTOFF_YEAR = 2024

INDICATORS = {
    "internet_user_pct": {
        "indicator": "IT.NET.USER.ZS",
        "label": "Individuals using the Internet (% of population)",
        "url": "https://data.worldbank.org/indicator/IT.NET.USER.ZS",
    },
    "electricity_access_pct": {
        "indicator": "EG.ELC.ACCS.ZS",
        "label": "Access to electricity (% of population)",
        "url": "https://data.worldbank.org/indicator/EG.ELC.ACCS.ZS",
    },
    "gdp_per_capita_usd": {
        "indicator": "NY.GDP.PCAP.CD",
        "label": "GDP per capita (current US$)",
        "url": "https://data.worldbank.org/indicator/NY.GDP.PCAP.CD",
    },
}

NAME_ALIASES = {
    "cote d'ivoire": "cote d'ivoire",
    "democratic republic of the congo": "democratic republic of congo",
    "czech republic": "czechia",
    "slovak republic": "slovakia",
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8")


def fetch_json(url: str) -> object:
    return json.loads(fetch_text(url))


def write_raw(name: str, content: bytes | str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / name
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if isinstance(content, bytes) else {"encoding": "utf-8"}
    with path.open(mode, **kwargs) as handle:
        handle.write(content)
    return path


def read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(text.splitlines()))


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract PDF text with pdftotext, keeping layout for table parsing."""
    if not shutil.which("pdftotext"):
        raise RuntimeError(
            "pdftotext is required to extract Microsoft's PDF appendix. "
            "Install Poppler, or use the generated site/data.json already in the repo."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "source.pdf"
        txt_path = Path(tmp_dir) / "source.txt"
        pdf_path.write_bytes(pdf_bytes)
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return txt_path.read_text(encoding="utf-8", errors="replace")


def parse_microsoft_ai_diffusion(text: str) -> list[dict[str, Any]]:
    """Parse the Q1 2026 Microsoft appendix table."""
    if "AI Diffusion Data Source" not in text:
        raise RuntimeError("Could not find AI Diffusion Data Source in Microsoft PDF text.")

    section = text.split("AI Diffusion Data Source", 1)[1]
    pattern = re.compile(
        r"^(.+?)\s+([0-9.]+)%\s+([0-9.]+)%\s+([0-9.]+)%\s+([0-9.]+)%$"
    )
    rows: list[dict[str, Any]] = []
    for line in section.splitlines():
        compact = " ".join(line.strip().split())
        match = pattern.match(compact)
        if not match:
            continue
        economy, h1, h2, q1, q1_change = match.groups()
        rows.append(
            {
                "economy": economy,
                "ai_share_h1_2025_pct": float(h1),
                "ai_share_h2_2025_pct": float(h2),
                "ai_share_q1_2026_pct": float(q1),
                "q1_change_pp": float(q1_change),
            }
        )

    if len(rows) < 140:
        raise RuntimeError(f"Parsed only {len(rows)} Microsoft rows; expected about 147.")
    return rows


def load_population() -> tuple[dict[tuple[str, int], int], dict[str, str], dict[str, str], dict[str, Any]]:
    pop_csv = fetch_text(POPULATION_URL)
    pop_metadata = fetch_json(POPULATION_METADATA_URL)
    write_raw("dependency-age-groups-to-2100.csv", pop_csv)
    write_raw("dependency-age-groups-to-2100.metadata.json", json.dumps(pop_metadata, indent=2))

    population: dict[tuple[str, int], int] = {}
    code_to_name: dict[str, str] = {}
    name_to_code: dict[str, str] = {}

    for row in read_csv(pop_csv):
        code = row.get("code", "")
        entity = row.get("entity", "")
        if not code or not entity:
            continue
        year = int(row["year"])
        raw_value = row.get(POP_PROJECTED_COLUMN) or row.get(POP_ESTIMATE_COLUMN)
        if not raw_value:
            continue
        population[(code, year)] = int(float(raw_value))
        code_to_name.setdefault(code, entity)
        name_to_code[normalise_name(entity)] = code

    return population, name_to_code, code_to_name, pop_metadata


def normalise_name(name: str) -> str:
    key = " ".join(name.strip().lower().split())
    return NAME_ALIASES.get(key, key)


def load_world_bank_country_metadata() -> dict[str, dict[str, str]]:
    data = fetch_json(WORLD_BANK_COUNTRIES_URL)
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError("Unexpected World Bank country metadata response.")
    rows = data[1]
    write_raw("world-bank-countries.json", json.dumps(rows, indent=2))

    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row.get("id", "")
        if not code:
            continue
        region = row.get("region", {}).get("value", "").strip()
        income = row.get("incomeLevel", {}).get("value", "").strip()
        metadata[code] = {
            "region": region if region and region != "Aggregates" else "Unclassified",
            "income_group": income or "Unclassified",
        }
    return metadata


def load_world_bank_indicator(indicator: str) -> dict[str, dict[str, float | int]]:
    url = WORLD_BANK_INDICATOR_URL.format(indicator=indicator)
    data = fetch_json(url)
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError(f"Unexpected World Bank indicator response for {indicator}.")
    rows = data[1]
    write_raw(f"world-bank-{indicator}.json", json.dumps(rows, indent=2))

    latest: dict[str, dict[str, float | int]] = {}
    for row in rows:
        code = row.get("countryiso3code")
        value = row.get("value")
        if not code or value is None:
            continue
        year = int(row["date"])
        if year > WORLD_BANK_CUTOFF_YEAR:
            continue
        current = latest.get(code)
        if current is None or year > int(current["year"]):
            latest[code] = {"value": float(value), "year": year}
    return latest


def log_score(value: float | None, lo: float, hi: float) -> float | None:
    if value is None or value <= 0 or lo <= 0 or hi <= lo:
        return None
    return max(0.0, min(100.0, (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo)) * 100))


def weighted_score(parts: list[tuple[float | None, float]]) -> float | None:
    total_weight = sum(weight for value, weight in parts if value is not None)
    if total_weight == 0:
        return None
    return sum(float(value) * weight for value, weight in parts if value is not None) / total_weight


def pct_change(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return (new - old) / old * 100


def median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot calculate median of an empty list.")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def logit(p: float) -> float:
    p = clamp(p, 0.001, 0.999)
    return math.log(p / (1 - p))


def logistic(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small linear system with Gauss-Jordan elimination."""
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]

    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise RuntimeError("Infrastructure model matrix is singular.")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]

        pivot_value = augmented[col][col]
        augmented[col] = [value / pivot_value for value in augmented[col]]

        for row in range(size):
            if row == col:
                continue
            factor = augmented[row][col]
            if factor == 0:
                continue
            augmented[row] = [
                value - factor * augmented[col][i] for i, value in enumerate(augmented[row])
            ]

    return [row[-1] for row in augmented]


def fit_infrastructure_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit a simple logistic adoption model from infrastructure covariates."""
    feature_keys = ["internet_user_pct", "electricity_access_pct", "gdp_readiness_score"]
    training_rows = [row for row in rows if all(row.get(key) is not None for key in feature_keys)]
    x_rows: list[list[float]] = []
    y_values: list[float] = []

    for row in training_rows:
        x_rows.append([1.0] + [float(row[key]) / 100 for key in feature_keys])
        y_values.append(logit(float(row["ai_share_q1_2026_pct"]) / 100))

    width = len(x_rows[0])
    ridge = 0.08
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]

    for x, y in zip(x_rows, y_values):
        for i in range(width):
            xty[i] += x[i] * y
            for j in range(width):
                xtx[i][j] += x[i] * x[j]

    for i in range(1, width):
        xtx[i][i] += ridge

    coefficients = solve_linear_system(xtx, xty)

    for row in rows:
        if any(row.get(key) is None for key in feature_keys):
            row["modelled_ai_share_q1_2026_pct"] = None
            row["modelled_ai_users_q1_2026"] = None
            row["diffusion_gap_pp"] = None
            row["modelled_user_gap_q1_2026"] = None
            continue

        features = [1.0] + [float(row[key]) / 100 for key in feature_keys]
        prediction = logistic(sum(coef * feature for coef, feature in zip(coefficients, features))) * 100
        if row.get("access_ceiling_pct") is not None:
            prediction = min(prediction, float(row["access_ceiling_pct"]))
        prediction = clamp(prediction, 0, 100)
        modelled_users = round(float(row["working_age_population_2026"]) * prediction / 100)

        row["modelled_ai_share_q1_2026_pct"] = prediction
        row["modelled_ai_users_q1_2026"] = modelled_users
        row["diffusion_gap_pp"] = float(row["ai_share_q1_2026_pct"]) - prediction
        row["modelled_user_gap_q1_2026"] = int(row["estimated_ai_users_q1_2026"]) - modelled_users

    return {
        "training_country_count": len(training_rows),
        "target": "logit(ai_share_q1_2026_pct / 100)",
        "features": {
            "internet_user_pct": "World Bank individuals using the Internet, scaled 0-1",
            "electricity_access_pct": "World Bank electricity access, scaled 0-1",
            "gdp_readiness_score": "Log-scaled GDP per capita, scaled 0-1",
        },
        "coefficients": {
            "intercept": coefficients[0],
            "internet_user_pct": coefficients[1],
            "electricity_access_pct": coefficients[2],
            "gdp_readiness_score": coefficients[3],
        },
        "missing_inputs_policy": "Countries missing any infrastructure feature are excluded from model-gap scoring.",
        "ridge_penalty": ridge,
    }


def make_scores(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write deterministic country scores in a benchmark-style artefact."""
    scores: list[dict[str, Any]] = []
    for row in rows:
        gap = row.get("diffusion_gap_pp")
        if gap is None:
            rationale = "Not scored because at least one infrastructure input is missing."
        elif gap >= 0:
            rationale = "Actual Q1 2026 AI share is above the infrastructure-only expected share."
        else:
            rationale = "Actual Q1 2026 AI share is below the infrastructure-only expected share."

        scores.append(
            {
                "country": row["country"],
                "code": row["code"],
                "region": row["region"],
                "estimated_ai_users_q1_2026": row["estimated_ai_users_q1_2026"],
                "ai_share_q1_2026_pct": row["ai_share_q1_2026_pct"],
                "readiness_score": row.get("readiness_score"),
                "modelled_ai_share_q1_2026_pct": row.get("modelled_ai_share_q1_2026_pct"),
                "diffusion_gap_pp": gap,
                "access_headroom_users": row.get("access_headroom_users"),
                "internet_user_pct": row.get("internet_user_pct"),
                "electricity_access_pct": row.get("electricity_access_pct"),
                "gdp_per_capita_usd": row.get("gdp_per_capita_usd"),
                "rationale": rationale,
            }
        )
    return scores


def round_metric(value: float | int | None, digits: int = 3) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return round(value, digits)


def year_distribution(rows: list[dict[str, Any]], year_key: str) -> dict[str, int]:
    counts = Counter(str(row.get(year_key) or "missing") for row in rows)
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def missing_for_keys(rows: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    missing = []
    for row in rows:
        missing_keys = [key for key in keys if row.get(key) is None]
        if missing_keys:
            missing.append(
                {
                    "country": row["country"],
                    "code": row["code"],
                    "missing": missing_keys,
                }
            )
    return missing


def make_data_audit(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    formula_failures: list[dict[str, Any]] = []
    for row in rows:
        checks = {
            "estimated_ai_users_h1_2025": round(
                row["working_age_population_2025"] * row["ai_share_h1_2025_pct"] / 100
            ),
            "estimated_ai_users_h2_2025": round(
                row["working_age_population_2025"] * row["ai_share_h2_2025_pct"] / 100
            ),
            "estimated_ai_users_q1_2026": round(
                row["working_age_population_2026"] * row["ai_share_q1_2026_pct"] / 100
            ),
        }
        failed = [key for key, expected in checks.items() if expected != row[key]]
        if failed:
            formula_failures.append(
                {
                    "country": row["country"],
                    "code": row["code"],
                    "failed_fields": failed,
                }
            )

    infrastructure_keys = [
        "internet_user_pct",
        "electricity_access_pct",
        "gdp_per_capita_usd",
    ]

    older_internet = [
        {
            "country": row["country"],
            "code": row["code"],
            "year": row["internet_year"],
            "value": round_metric(row["internet_user_pct"]),
        }
        for row in rows
        if row.get("internet_year") is not None
        and row["internet_year"] < WORLD_BANK_CUTOFF_YEAR
    ]
    older_gdp = [
        {
            "country": row["country"],
            "code": row["code"],
            "year": row["gdp_year"],
            "value": round_metric(row["gdp_per_capita_usd"]),
        }
        for row in rows
        if row.get("gdp_year") is not None
        and row["gdp_year"] < WORLD_BANK_CUTOFF_YEAR
    ]

    return {
        "generated_at": summary["generated_at"],
        "benchmark_reference": "https://github.com/karpathy/jobs",
        "country_count": len(rows),
        "formula_checks": {
            "estimated_user_formula": summary["formulas"]["estimated_ai_users"],
            "passed": not formula_failures,
            "failure_count": len(formula_failures),
            "failures": formula_failures,
        },
        "totals_match_site_summary": {
            "total_estimated_ai_users_q1_2026": sum(
                row["estimated_ai_users_q1_2026"] for row in rows
            )
            == summary["total_estimated_ai_users_q1_2026"],
            "total_estimated_ai_users_h2_2025": sum(
                row["estimated_ai_users_h2_2025"] for row in rows
            )
            == summary["total_estimated_ai_users_h2_2025"],
            "total_estimated_ai_users_h1_2025": sum(
                row["estimated_ai_users_h1_2025"] for row in rows
            )
            == summary["total_estimated_ai_users_h1_2025"],
        },
        "source_coverage": {
            "ai_diffusion": {
                "source": summary["sources"]["ai_diffusion"]["url"],
                "countries": len(rows),
                "periods": ["H1 2025", "H2 2025", "Q1 2026"],
            },
            "internet_access": {
                "present": sum(1 for row in rows if row.get("internet_user_pct") is not None),
                "missing": sum(1 for row in rows if row.get("internet_user_pct") is None),
                "year_distribution": year_distribution(rows, "internet_year"),
                "older_than_2024": older_internet,
            },
            "electricity_access": {
                "present": sum(
                    1 for row in rows if row.get("electricity_access_pct") is not None
                ),
                "missing": sum(
                    1 for row in rows if row.get("electricity_access_pct") is None
                ),
                "year_distribution": year_distribution(rows, "electricity_year"),
            },
            "gdp_per_capita": {
                "present": sum(1 for row in rows if row.get("gdp_per_capita_usd") is not None),
                "missing": sum(1 for row in rows if row.get("gdp_per_capita_usd") is None),
                "year_distribution": year_distribution(rows, "gdp_year"),
                "older_than_2024": older_gdp,
            },
        },
        "missing_infrastructure_inputs": missing_for_keys(rows, infrastructure_keys),
        "model": {
            "modelled_country_count": summary["modelled_country_count"],
            "training_country_count": summary["infrastructure_model"]["training_country_count"],
            "missing_inputs_policy": summary["infrastructure_model"]["missing_inputs_policy"],
        },
    }


def build_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pdf_bytes = fetch(MICROSOFT_Q1_2026_PDF_URL)
    write_raw("Microsoft-AI-Diffusion-Report-2026-Q1.pdf", pdf_bytes)
    pdf_text = pdf_to_text(pdf_bytes)
    write_raw("Microsoft-AI-Diffusion-Report-2026-Q1.txt", pdf_text)
    microsoft_rows = parse_microsoft_ai_diffusion(pdf_text)

    population, name_to_code, code_to_name, pop_metadata = load_population()
    country_metadata = load_world_bank_country_metadata()
    indicators = {
        key: load_world_bank_indicator(config["indicator"])
        for key, config in INDICATORS.items()
    }

    gdp_values = [
        item["value"]
        for item in indicators["gdp_per_capita_usd"].values()
        if item.get("value") and item["value"] > 0
    ]
    gdp_lo, gdp_hi = min(gdp_values), max(gdp_values)

    rows: list[dict[str, Any]] = []
    missing_codes: list[str] = []
    missing_population: list[str] = []

    for item in microsoft_rows:
        code = name_to_code.get(normalise_name(item["economy"]))
        if not code:
            missing_codes.append(item["economy"])
            continue

        pop_2025 = population.get((code, 2025))
        pop_2026 = population.get((code, 2026))
        if pop_2025 is None or pop_2026 is None:
            missing_population.append(f"{item['economy']} ({code})")
            continue

        internet = indicators["internet_user_pct"].get(code)
        electricity = indicators["electricity_access_pct"].get(code)
        gdp = indicators["gdp_per_capita_usd"].get(code)

        internet_pct = float(internet["value"]) if internet else None
        electricity_pct = float(electricity["value"]) if electricity else None
        gdp_pc = float(gdp["value"]) if gdp else None
        gdp_score = log_score(gdp_pc, gdp_lo, gdp_hi)
        readiness_score = weighted_score(
            [
                (internet_pct, 0.55),
                (electricity_pct, 0.25),
                (gdp_score, 0.20),
            ]
        )

        h1_share = float(item["ai_share_h1_2025_pct"])
        h2_share = float(item["ai_share_h2_2025_pct"])
        q1_share = float(item["ai_share_q1_2026_pct"])

        h1_users = round(pop_2025 * h1_share / 100)
        h2_users = round(pop_2025 * h2_share / 100)
        q1_users = round(pop_2026 * q1_share / 100)

        access_ceiling_pct = None
        if internet_pct is not None and electricity_pct is not None:
            access_ceiling_pct = min(internet_pct, electricity_pct)
        elif internet_pct is not None:
            access_ceiling_pct = internet_pct
        elif electricity_pct is not None:
            access_ceiling_pct = electricity_pct

        access_headroom_users = None
        if access_ceiling_pct is not None:
            access_headroom_users = round(max(0.0, (access_ceiling_pct - q1_share) / 100 * pop_2026))

        internet_intensity_pct = None
        if internet_pct and internet_pct > 0:
            internet_intensity_pct = q1_share / internet_pct * 100

        offline_working_age_population = None
        if internet_pct is not None:
            offline_working_age_population = round(max(0.0, (100 - internet_pct) / 100 * pop_2026))

        wb = country_metadata.get(code, {})
        rows.append(
            {
                "country": code_to_name.get(code, item["economy"]),
                "microsoft_economy": item["economy"],
                "code": code,
                "region": wb.get("region", "Unclassified"),
                "income_group": wb.get("income_group", "Unclassified"),
                "ai_share_h1_2025_pct": h1_share,
                "ai_share_h2_2025_pct": h2_share,
                "ai_share_q1_2026_pct": q1_share,
                "h2_to_q1_change_pp": float(item["q1_change_pp"]),
                "h1_to_h2_change_pp": h2_share - h1_share,
                "h1_to_q1_change_pp": q1_share - h1_share,
                "h1_to_h2_growth_pct": pct_change(h2_share, h1_share),
                "h2_to_q1_growth_pct": pct_change(q1_share, h2_share),
                "h1_to_q1_growth_pct": pct_change(q1_share, h1_share),
                "working_age_population_2025": pop_2025,
                "working_age_population_2026": pop_2026,
                "estimated_ai_users_h1_2025": h1_users,
                "estimated_ai_users_h2_2025": h2_users,
                "estimated_ai_users_q1_2026": q1_users,
                "estimated_user_change_h2_to_q1": q1_users - h2_users,
                "estimated_user_change_h1_to_h2": h2_users - h1_users,
                "estimated_user_change_h1_to_q1": q1_users - h1_users,
                "internet_user_pct": internet_pct,
                "internet_year": int(internet["year"]) if internet else None,
                "electricity_access_pct": electricity_pct,
                "electricity_year": int(electricity["year"]) if electricity else None,
                "gdp_per_capita_usd": gdp_pc,
                "gdp_year": int(gdp["year"]) if gdp else None,
                "gdp_readiness_score": gdp_score,
                "readiness_score": readiness_score,
                "access_ceiling_pct": access_ceiling_pct,
                "access_headroom_users": access_headroom_users,
                "internet_normalised_ai_intensity_pct": internet_intensity_pct,
                "offline_working_age_population": offline_working_age_population,
                "source_url": MICROSOFT_Q1_2026_PDF_URL,
            }
        )

    if missing_codes:
        raise RuntimeError(f"Could not match Microsoft economies to ISO3 codes: {missing_codes}")
    if missing_population:
        raise RuntimeError(f"Missing population denominators: {missing_population}")

    infrastructure_model = fit_infrastructure_model(rows)

    rows.sort(key=lambda row: row["estimated_ai_users_q1_2026"], reverse=True)
    assign_rank(rows, "rank_by_estimated_users", "estimated_ai_users_q1_2026", reverse=True)
    assign_rank(rows, "rank_by_ai_share", "ai_share_q1_2026_pct", reverse=True)
    assign_rank(rows, "rank_by_h1_to_h2_change", "h1_to_h2_change_pp", reverse=True)
    assign_rank(rows, "rank_by_h2_to_q1_change", "h2_to_q1_change_pp", reverse=True)
    assign_rank(rows, "rank_by_readiness", "readiness_score", reverse=True)
    assign_rank(rows, "rank_by_access_headroom", "access_headroom_users", reverse=True)
    assign_rank(rows, "rank_by_positive_diffusion_gap", "diffusion_gap_pp", reverse=True)
    assign_rank(rows, "rank_by_negative_diffusion_gap", "diffusion_gap_pp", reverse=False)

    total_q1_users = sum(row["estimated_ai_users_q1_2026"] for row in rows)
    total_h2_users = sum(row["estimated_ai_users_h2_2025"] for row in rows)
    total_h1_users = sum(row["estimated_ai_users_h1_2025"] for row in rows)
    total_modelled_users = sum(row["modelled_ai_users_q1_2026"] or 0 for row in rows)
    total_pop_2026 = sum(row["working_age_population_2026"] for row in rows)
    total_pop_2025 = sum(row["working_age_population_2025"] for row in rows)
    total_headroom = sum(row["access_headroom_users"] or 0 for row in rows)
    total_offline = sum(row["offline_working_age_population"] or 0 for row in rows)
    modelled_rows = [row for row in rows if row["diffusion_gap_pp"] is not None]

    pop_column = pop_metadata["columns"][
        "Population - Sex: all - Age: 15-64 - Variant: medium"
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "country_count": len(rows),
        "main_ai_source_period": "Q1 2026",
        "baseline_periods": ["H1 2025", "H2 2025"],
        "population_current_year": 2026,
        "population_baseline_year": 2025,
        "population_variant": "UN WPP medium scenario projection",
        "total_estimated_ai_users_q1_2026": total_q1_users,
        "total_estimated_ai_users_h2_2025": total_h2_users,
        "total_estimated_ai_users_h1_2025": total_h1_users,
        "total_working_age_population_2026": total_pop_2026,
        "weighted_ai_user_share_q1_2026_pct": total_q1_users / total_pop_2026 * 100,
        "weighted_ai_user_share_h2_2025_pct": total_h2_users / total_pop_2025 * 100,
        "weighted_ai_user_share_h1_2025_pct": total_h1_users / total_pop_2025 * 100,
        "estimated_user_change_h1_to_h2": total_h2_users - total_h1_users,
        "estimated_user_growth_h1_to_h2_pct": pct_change(total_h2_users, total_h1_users),
        "estimated_user_change_h2_to_q1": total_q1_users - total_h2_users,
        "estimated_user_growth_h2_to_q1_pct": pct_change(total_q1_users, total_h2_users),
        "estimated_user_change_h1_to_q1": total_q1_users - total_h1_users,
        "estimated_user_growth_h1_to_q1_pct": pct_change(total_q1_users, total_h1_users),
        "total_modelled_ai_users_q1_2026": total_modelled_users,
        "modelled_country_count": sum(
            1 for row in rows if row["modelled_ai_users_q1_2026"] is not None
        ),
        "total_modelled_user_gap_q1_2026": sum(
            row["modelled_user_gap_q1_2026"] or 0 for row in rows
        ),
        "total_access_headroom_users": total_headroom,
        "total_offline_working_age_population": total_offline,
        "top_country_by_estimated_users": rows[0]["country"] if rows else None,
        "top_country_by_ai_share": max(rows, key=lambda row: row["ai_share_q1_2026_pct"])[
            "country"
        ]
        if rows
        else None,
        "top_country_by_h2_to_q1_change": max(rows, key=lambda row: row["h2_to_q1_change_pp"])[
            "country"
        ]
        if rows
        else None,
        "top_country_above_infrastructure_model": max(
            modelled_rows, key=lambda row: row["diffusion_gap_pp"]
        )["country"]
        if modelled_rows
        else None,
        "top_country_below_infrastructure_model": min(
            modelled_rows, key=lambda row: row["diffusion_gap_pp"]
        )["country"]
        if modelled_rows
        else None,
        "formulas": {
            "estimated_ai_users": "ai_share_pct / 100 * working_age_population",
            "internet_normalised_ai_intensity_pct": "ai_share_q1_2026_pct / internet_user_pct * 100",
            "access_ceiling_pct": "min(internet_user_pct, electricity_access_pct)",
            "access_headroom_users": "max(0, access_ceiling_pct - ai_share_q1_2026_pct) / 100 * working_age_population_2026",
            "readiness_score": "0.55*internet_user_pct + 0.25*electricity_access_pct + 0.20*log_scaled_gdp_per_capita",
            "infrastructure_model": "ridge regression on logit(ai_share_q1_2026_pct) using internet access, electricity access, and log-scaled GDP per capita",
            "diffusion_gap_pp": "ai_share_q1_2026_pct - modelled_ai_share_q1_2026_pct",
        },
        "infrastructure_model": infrastructure_model,
        "sources": {
            "ai_diffusion": {
                "url": MICROSOFT_Q1_2026_PDF_URL,
                "citation": "Microsoft AI Economy Institute. Global AI Diffusion: Q1 2026 Trends and Insights. May 2026.",
                "description": "Country-level H1 2025, H2 2025, and Q1 2026 AI diffusion shares extracted from the report appendix.",
            },
            "working_age_population": {
                "url": "https://ourworldindata.org/grapher/dependency-age-groups-to-2100",
                "download_url": POPULATION_URL,
                "citation": pop_column.get("citationLong"),
                "description": pop_column.get("descriptionShort"),
                "last_updated": pop_column.get("lastUpdated"),
            },
            "internet_access": {
                "url": INDICATORS["internet_user_pct"]["url"],
                "citation": "World Bank, World Development Indicators: Individuals using the Internet (% of population). Latest available value up to 2024.",
            },
            "electricity_access": {
                "url": INDICATORS["electricity_access_pct"]["url"],
                "citation": "World Bank, World Development Indicators: Access to electricity (% of population). Latest available value up to 2024.",
            },
            "gdp_per_capita": {
                "url": INDICATORS["gdp_per_capita_usd"]["url"],
                "citation": "World Bank, World Development Indicators: GDP per capita (current US$). Latest available value up to 2024.",
            },
            "regions": {
                "url": "https://api.worldbank.org/v2/country",
                "citation": "World Bank country metadata, fetched from the World Bank API.",
            },
        },
    }

    return rows, summary


def assign_rank(rows: list[dict[str, Any]], rank_key: str, value_key: str, reverse: bool) -> None:
    ranked = sorted(
        [row for row in rows if row.get(value_key) is not None],
        key=lambda row: row[value_key],
        reverse=reverse,
    )
    for index, row in enumerate(ranked, start=1):
        row[rank_key] = index
    for row in rows:
        row.setdefault(rank_key, None)


def write_csv(rows: list[dict[str, Any]]) -> None:
    path = ROOT / "country_usage.csv"
    fieldnames = [
        "rank_by_estimated_users",
        "rank_by_ai_share",
        "rank_by_h1_to_h2_change",
        "rank_by_h2_to_q1_change",
        "rank_by_readiness",
        "rank_by_access_headroom",
        "rank_by_positive_diffusion_gap",
        "rank_by_negative_diffusion_gap",
        "country",
        "microsoft_economy",
        "code",
        "region",
        "income_group",
        "ai_share_h1_2025_pct",
        "ai_share_h2_2025_pct",
        "ai_share_q1_2026_pct",
        "h1_to_h2_change_pp",
        "h2_to_q1_change_pp",
        "h1_to_q1_change_pp",
        "h1_to_h2_growth_pct",
        "h2_to_q1_growth_pct",
        "h1_to_q1_growth_pct",
        "working_age_population_2025",
        "working_age_population_2026",
        "estimated_ai_users_h1_2025",
        "estimated_ai_users_h2_2025",
        "estimated_ai_users_q1_2026",
        "estimated_user_change_h1_to_h2",
        "estimated_user_change_h2_to_q1",
        "estimated_user_change_h1_to_q1",
        "internet_user_pct",
        "internet_year",
        "electricity_access_pct",
        "electricity_year",
        "gdp_per_capita_usd",
        "gdp_year",
        "gdp_readiness_score",
        "readiness_score",
        "access_ceiling_pct",
        "access_headroom_users",
        "internet_normalised_ai_intensity_pct",
        "modelled_ai_share_q1_2026_pct",
        "modelled_ai_users_q1_2026",
        "diffusion_gap_pp",
        "modelled_user_gap_q1_2026",
        "offline_working_age_population",
        "source_url",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_site_data(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "countries": rows}

    json_path = SITE_DIR / "data.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    js_path = SITE_DIR / "data.js"
    with js_path.open("w", encoding="utf-8") as handle:
        handle.write("window.AI_COUNTRY_USAGE_DATA = ")
        json.dump(payload, handle, indent=2)
        handle.write(";\n")


def write_scores(rows: list[dict[str, Any]]) -> None:
    with (ROOT / "scores.json").open("w", encoding="utf-8") as handle:
        json.dump(make_scores(rows), handle, indent=2)
        handle.write("\n")


def write_data_audit(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    with (ROOT / "data_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(make_data_audit(rows, summary), handle, indent=2)
        handle.write("\n")


def main() -> int:
    rows, summary = build_rows()
    write_csv(rows)
    write_site_data(rows, summary)
    write_scores(rows)
    write_data_audit(rows, summary)

    print(f"Wrote {len(rows)} countries to country_usage.csv and site/data.json")
    print("Wrote scores.json and data_audit.json")
    print(f"Q1 2026 estimated AI users: {summary['total_estimated_ai_users_q1_2026']:,}")
    print(f"H2 2025 to Q1 2026 user change: {summary['estimated_user_change_h2_to_q1']:,}")
    print(f"Weighted Q1 2026 AI user share: {summary['weighted_ai_user_share_q1_2026_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
