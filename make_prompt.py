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
        "ai_share_h1_2025_pct",
        "ai_share_h2_2025_pct",
        "ai_share_q1_2026_pct",
        "h1_to_h2_change_pp",
        "h2_to_q1_change_pp",
        "estimated_user_change_h1_to_h2",
        "estimated_ai_users_q1_2026",
        "estimated_user_change_h2_to_q1",
        "internet_user_pct",
        "electricity_access_pct",
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


def main() -> int:
    data = json.loads((ROOT / "site" / "data.json").read_text(encoding="utf-8"))
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

    lines = [
        "# AI usage atlas prompt",
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
        "- Model-gap scoring is only calculated for countries with complete internet, electricity, and GDP inputs.",
        "- The infrastructure model is explanatory and directional. It is not a causal model and should not be described as a forecast.",
        "- Access headroom is a reachability model, not a prediction that those people will adopt AI.",
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
        f"- Modelled access headroom: {format_count(summary['total_access_headroom_users'])}",
        f"- Infrastructure model training countries: {summary['infrastructure_model']['training_country_count']}",
        f"- Countries with model-gap scores: {summary['modelled_country_count']}",
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

    lines += ["", "Countries most above the infrastructure model:", ""]
    for row in top_model_gap:
        lines.append(
            f"- {row['country']}: {row['diffusion_gap_pp']:+.1f} pp "
            f"(actual {format_pct(row['ai_share_q1_2026_pct'])}, "
            f"model {format_pct(row['modelled_ai_share_q1_2026_pct'])})"
        )

    lines += ["", "Countries most below the infrastructure model:", ""]
    for row in bottom_model_gap:
        lines.append(
            f"- {row['country']}: {row['diffusion_gap_pp']:+.1f} pp "
            f"(actual {format_pct(row['ai_share_q1_2026_pct'])}, "
            f"model {format_pct(row['modelled_ai_share_q1_2026_pct'])})"
        )

    lines += ["", "Largest modelled access headroom:", ""]
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
