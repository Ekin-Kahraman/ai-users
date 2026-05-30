"""
Create a compact prompt for discussing the generated dataset with an LLM.

Usage:
    python3 make_prompt.py
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


def format_count(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    value = int(round(value))
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def make_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "rank_by_estimated_users",
        "rank_by_ai_share",
        "rank_by_h1_to_h2_change",
        "rank_by_h2_to_q1_change",
        "rank_by_positive_diffusion_gap",
        "country",
        "code",
        "region",
        "income_group",
        "ai_share_h1_2025_pct",
        "ai_share_h2_2025_pct",
        "ai_share_q1_2026_pct",
        "h1_to_h2_change_pp",
        "h2_to_q1_change_pp",
        "h1_to_q1_growth_pct",
        "estimated_user_change_h1_to_h2",
        "estimated_ai_users_q1_2026",
        "estimated_user_change_h2_to_q1",
        "internet_user_pct",
        "internet_year",
        "electricity_access_pct",
        "electricity_year",
        "readiness_score",
        "access_headroom_users",
        "modelled_ai_share_q1_2026_pct",
        "diffusion_gap_pp",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})
    return buffer.getvalue()


def aggregate(rows: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get(group_key) or "Unclassified"
        group = groups.setdefault(
            key,
            {
                "name": key,
                "countries": 0,
                "users_q1_2026": 0,
                "users_h2_2025": 0,
                "users_h1_2025": 0,
                "population_2026": 0,
                "headroom": 0,
            },
        )
        group["countries"] += 1
        group["users_q1_2026"] += row["estimated_ai_users_q1_2026"]
        group["users_h2_2025"] += row["estimated_ai_users_h2_2025"]
        group["users_h1_2025"] += row["estimated_ai_users_h1_2025"]
        group["population_2026"] += row["working_age_population_2026"]
        group["headroom"] += row.get("access_headroom_users") or 0

    out = []
    for group in groups.values():
        q1_users = group["users_q1_2026"]
        h2_users = group["users_h2_2025"]
        h1_users = group["users_h1_2025"]
        population = group["population_2026"]
        out.append(
            {
                **group,
                "weighted_share_q1_2026_pct": q1_users / population * 100
                if population
                else None,
                "h2_to_q1_growth_pct": (q1_users - h2_users) / h2_users * 100
                if h2_users
                else None,
                "h1_to_q1_growth_pct": (q1_users - h1_users) / h1_users * 100
                if h1_users
                else None,
            }
        )
    return sorted(out, key=lambda row: row["users_q1_2026"], reverse=True)


def main() -> int:
    data = json.loads((ROOT / "site" / "data.json").read_text(encoding="utf-8"))
    audit_path = ROOT / "data_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else None
    summary = data["summary"]
    rows = data["countries"]

    top_users = rows[:15]
    top_share = sorted(rows, key=lambda row: row["ai_share_q1_2026_pct"], reverse=True)[:15]
    top_change = sorted(rows, key=lambda row: row["h2_to_q1_change_pp"], reverse=True)[:15]
    modelled_rows = [row for row in rows if row.get("diffusion_gap_pp") is not None]
    top_model_gap = sorted(modelled_rows, key=lambda row: row["diffusion_gap_pp"], reverse=True)[:15]
    bottom_model_gap = sorted(modelled_rows, key=lambda row: row["diffusion_gap_pp"])[:15]
    top_headroom = sorted(
        [row for row in rows if row.get("access_headroom_users") is not None],
        key=lambda row: row["access_headroom_users"],
        reverse=True,
    )[:15]
    region_aggregates = aggregate(rows, "region")
    income_aggregates = aggregate(rows, "income_group")

    lines = [
        "# AI Users prompt",
        "",
        "You are analysing a source-backed prototype dataset for estimated generative AI usage by country.",
        "",
        "Main estimate:",
        "",
        "estimated_ai_users = ai_share_pct / 100 * working_age_population",
        "",
        "Infrastructure model:",
        "",
        "- internet_normalised_ai_intensity_pct = ai_share_q1_2026_pct / internet_user_pct * 100",
        "- access_ceiling_pct = min(internet_user_pct, electricity_access_pct)",
        "- access_headroom_users = max(0, access_ceiling_pct - ai_share_q1_2026_pct) / 100 * working_age_population_2026",
        "- readiness_score = weighted internet access, electricity access, and log-scaled GDP per capita",
        "- modelled_ai_share_q1_2026_pct = ridge regression estimate from internet access, electricity access, and log-scaled GDP per capita",
        "- diffusion_gap_pp = actual Q1 2026 AI share minus the infrastructure-modelled share",
        "",
        "Important caveats:",
        "",
        "- The AI shares are Microsoft AI Economy Institute modelled estimates, not surveys.",
        "- H1 2025, H2 2025, and Q1 2026 values come from the Microsoft Q1 2026 appendix table.",
        "- The public country-level Microsoft series in this build starts at H1 2025, so do not present a 2024 country growth rate unless another comparable source is added.",
        "- Infrastructure indicators are latest available World Bank values up to 2024, so they lag the AI period.",
        "- Above/below expected scoring is only calculated for countries with complete internet, electricity, and GDP inputs.",
        "- The infrastructure model is explanatory and directional. It is not a causal model and should not be described as a forecast.",
        "- Potential users is a reachability model, not a prediction that those people will adopt AI.",
        "- Treat this as a directional prototype, not an official count of regular AI users.",
        "",
        "Dataset summary:",
        "",
        f"- Countries: {summary['country_count']}",
        f"- Main AI source period: {summary['main_ai_source_period']}",
        f"- Total estimated Q1 2026 users: {format_count(summary['total_estimated_ai_users_q1_2026'])}",
        f"- Weighted Q1 2026 AI share: {format_pct(summary['weighted_ai_user_share_q1_2026_pct'])}",
        f"- H1 2025 to H2 2025 user change: {format_count(summary['estimated_user_change_h1_to_h2'])}",
        f"- H1 2025 to H2 2025 user growth: {format_pct(summary['estimated_user_growth_h1_to_h2_pct'])}",
        f"- H2 2025 to Q1 2026 user change: {format_count(summary['estimated_user_change_h2_to_q1'])}",
        f"- H2 2025 to Q1 2026 user growth: {format_pct(summary['estimated_user_growth_h2_to_q1_pct'])}",
        f"- H1 2025 to Q1 2026 user change: {format_count(summary['estimated_user_change_h1_to_q1'])}",
        f"- H1 2025 to Q1 2026 user growth: {format_pct(summary['estimated_user_growth_h1_to_q1_pct'])}",
        f"- Potential users under access model: {format_count(summary['total_access_headroom_users'])}",
        f"- Infrastructure model training countries: {summary['infrastructure_model']['training_country_count']}",
        f"- Countries with above/below expected scores: {summary['modelled_country_count']}",
        "",
        "Source coverage audit:",
        "",
    ]

    if audit:
        internet = audit["source_coverage"]["internet_access"]
        electricity = audit["source_coverage"]["electricity_access"]
        gdp = audit["source_coverage"]["gdp_per_capita"]
        missing = ", ".join(
            f"{row['country']} ({row['code']})"
            for row in audit["missing_infrastructure_inputs"]
        )
        lines += [
            f"- Formula checks passed: {audit['formula_checks']['passed']}",
            f"- Internet access coverage: {internet['present']}/{summary['country_count']} countries",
            f"- Internet access year distribution: {internet['year_distribution']}",
            f"- Electricity access coverage: {electricity['present']}/{summary['country_count']} countries",
            f"- Electricity access year distribution: {electricity['year_distribution']}",
            f"- GDP per capita coverage: {gdp['present']}/{summary['country_count']} countries",
            f"- GDP per capita year distribution: {gdp['year_distribution']}",
            f"- Missing infrastructure inputs: {missing or 'none'}",
            "",
        ]
    else:
        lines += [
            "- data_audit.json was not present when this prompt was generated.",
            "",
        ]

    lines += [
        "Regional aggregates:",
        "",
    ]

    for row in region_aggregates:
        lines.append(
            f"- {row['name']}: {format_count(row['users_q1_2026'])} Q1 2026 users, "
            f"{format_pct(row['weighted_share_q1_2026_pct'])} weighted share, "
            f"{format_pct(row['h2_to_q1_growth_pct'])} H2-to-Q1 user growth, "
            f"{row['countries']} countries"
        )

    lines += ["", "Income-group aggregates:", ""]
    for row in income_aggregates:
        lines.append(
            f"- {row['name']}: {format_count(row['users_q1_2026'])} Q1 2026 users, "
            f"{format_pct(row['weighted_share_q1_2026_pct'])} weighted share, "
            f"{format_pct(row['h2_to_q1_growth_pct'])} H2-to-Q1 user growth, "
            f"{row['countries']} countries"
        )

    lines += [
        "",
        "Top countries by estimated Q1 2026 users:",
        "",
    ]

    for row in top_users:
        lines.append(
            f"- {row['rank_by_estimated_users']}. {row['country']}: "
            f"{format_count(row['estimated_ai_users_q1_2026'])}, "
            f"{format_pct(row['ai_share_q1_2026_pct'])} AI share, "
            f"{format_count(row['estimated_user_change_h2_to_q1'])} vs H2 2025"
        )

    lines += ["", "Top countries by Q1 2026 AI user share:", ""]
    for row in top_share:
        lines.append(
            f"- {row['rank_by_ai_share']}. {row['country']}: "
            f"{format_pct(row['ai_share_q1_2026_pct'])}, "
            f"{format_count(row['estimated_ai_users_q1_2026'])}"
        )

    lines += ["", "Fastest movers from H2 2025 to Q1 2026:", ""]
    for row in top_change:
        lines.append(
            f"- {row['rank_by_h2_to_q1_change']}. {row['country']}: "
            f"+{row['h2_to_q1_change_pp']:.1f} percentage points, "
            f"{format_pct(row['h2_to_q1_growth_pct'])} relative growth"
        )

    lines += ["", "Countries most above expected adoption:", ""]
    for row in top_model_gap:
        lines.append(
            f"- {row['country']}: {row['diffusion_gap_pp']:+.1f} pp "
            f"(actual {format_pct(row['ai_share_q1_2026_pct'])}, "
            f"model {format_pct(row['modelled_ai_share_q1_2026_pct'])})"
        )

    lines += ["", "Countries most below expected adoption:", ""]
    for row in bottom_model_gap:
        lines.append(
            f"- {row['country']}: {row['diffusion_gap_pp']:+.1f} pp "
            f"(actual {format_pct(row['ai_share_q1_2026_pct'])}, "
            f"model {format_pct(row['modelled_ai_share_q1_2026_pct'])})"
        )

    lines += ["", "Largest potential users under access model:", ""]
    for row in top_headroom:
        lines.append(
            f"- {row['country']}: {format_count(row['access_headroom_users'])} reachable non-users, "
            f"{format_pct(row.get('internet_user_pct'))} internet access"
        )

    lines += [
        "",
        "Sources:",
        "",
        f"- AI diffusion: {summary['sources']['ai_diffusion']['citation']}",
        f"- Population: {summary['sources']['working_age_population']['citation']}",
        f"- Internet access: {summary['sources']['internet_access']['citation']}",
        f"- Electricity access: {summary['sources']['electricity_access']['citation']}",
        f"- GDP per capita: {summary['sources']['gdp_per_capita']['citation']}",
        "",
        "Full dataset CSV:",
        "",
        "```csv",
        make_csv(rows).strip(),
        "```",
        "",
    ]

    (ROOT / "prompt.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote prompt.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
