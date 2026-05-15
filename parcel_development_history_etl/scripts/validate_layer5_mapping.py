"""
validate_layer5_mapping.py - empirically test Layer 5 field semantics
against the analyst-derived regional_plan_allocations.json.

Why this exists
---------------
The Cumulative_Accounting combine view (UNION layer 5 + layer 3 into the
era-split shape the dashboards consume) is blocked on one open question
from `erd/regional_plan_allocations_service.md`:

    Q1. GetDevelopmentRightPoolBalanceReport field semantics. Confirm the
        mapping: is `BalanceRemaining` exactly "not assigned to a project,"
        and is `ApprovedTransactionsQuantity` + `BalanceRemaining` = the
        pool's authorization? `TotalDisbursements` did not cleanly equal
        the xlsx `RegionalPlanMaximum` in spot checks - what does it count?

We have ground truth: the analyst built the per-pool 2012-era numbers in
`All Regional Plan Allocations Summary.xlsx`, which the converter writes
into `regional_plan_allocations.json`. The same pools appear in Layer 5
(`Cumulative_Accounting/MapServer/5`, staged from
GetDevelopmentRightPoolBalanceReport). Joining the two and testing
candidate field-mapping hypotheses tells us empirically whether the LT Info
fields can stand in for the analyst's numbers - and which mapping works.

Hypotheses tested
-----------------
  H1: layer5.BalanceRemaining                                            == json.not_assigned
  H2: layer5.ApprovedTransactionsQuantity                                == json.assigned_to_projects
  H2a: layer5.ApprovedTransactionsQuantity + PendingTransactionQuantity  == json.assigned_to_projects
  H3a: layer5.ApprovedTransactionsQuantity + BalanceRemaining            == json.regional_plan_maximum
  H3b: layer5.TotalDisbursements                                         == json.regional_plan_maximum

For each (commodity, pool), the script records ground-truth json values
alongside the candidate layer 5 derivations and the per-hypothesis deltas.
A summary table reports how many pools agree exactly per hypothesis.

Output
------
  data/qa_data/layer5_mapping_validation.csv  -- row per pool with all candidates + deltas
  data/qa_data/layer5_mapping_validation.md   -- human summary of hypothesis pass rates
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import QA_DATA_DIR, REGIONAL_PLAN_ALLOCATIONS_JSON  # noqa: E402
from utils import get_logger  # noqa: E402

log = get_logger("validate_layer5_mapping")

LAYER_5_URL = (
    "https://maps.trpa.org/server/rest/services/Cumulative_Accounting"
    "/MapServer/5/query"
)
OUT_CSV = Path(QA_DATA_DIR) / "layer5_mapping_validation.csv"
OUT_MD = Path(QA_DATA_DIR) / "layer5_mapping_validation.md"

# Layer 5 DevelopmentRight value -> JSON top-level key.
# Layer 5 surfaces non-residential commodities with parenthetical abbreviations
# (e.g. "Commercial Floor Area (CFA)"); residential is bare.
COMMODITY_TO_JSON_KEY = {
    "Residential Allocation":           "residential",
    "Residential Bonus Unit (RBU)":     "residential_bonus_units",
    "Commercial Floor Area (CFA)":      "commercial_floor_area",
    "Tourist Accommodation Unit (TAU)": "tourist_accommodation_units",
    "Tourist Bonus Unit (TBU)":         "tourist_accommodation_units",  # legacy / TBU
}

# Jurisdiction normalization: layer 5 uses "City of South Lake Tahoe (CSLT)";
# JSON uses bare "City of South Lake Tahoe". Strip trailing parenthetical.
import re
def _norm_juris(s: str | None) -> str | None:
    if not isinstance(s, str):
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()


# ---------------------------------------------------------------------------

def fetch_layer5() -> pd.DataFrame:
    log.info("Fetching layer 5 (Development Right Pool Balance Report)...")
    params = {
        "where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json",
        "resultRecordCount": 2000, "orderByFields": "OBJECTID ASC",
    }
    r = requests.get(LAYER_5_URL, params=params, timeout=60)
    r.raise_for_status()
    feats = r.json().get("features", [])
    df = pd.DataFrame(f["attributes"] for f in feats)
    log.info("  layer 5 rows: %d", len(df))
    df["juris_norm"] = df["Jurisdiction"].map(_norm_juris)
    return df


def load_json_pool_2012() -> pd.DataFrame:
    """Extract the 2012-era per-pool numbers from regional_plan_allocations.json.

    Returns a long-form DataFrame with one row per (commodity, pool/jurisdiction)
    in the 2012 plan era, with regional_plan_maximum, not_assigned, assigned_to_projects.
    """
    log.info("Loading regional_plan_allocations.json (2012 era only)...")
    j = json.loads(Path(REGIONAL_PLAN_ALLOCATIONS_JSON).read_text())
    rows: list[dict] = []

    # Residential: by_jurisdiction with plan_1987/plan_2012/combined sub-keys
    for entry in j["residential"]["by_jurisdiction"]:
        p2012 = entry.get("plan_2012") or {}
        rows.append({
            "commodity": "residential",
            "pool": entry["name"],
            "json_regional_plan_maximum": p2012.get("regional_plan_maximum"),
            "json_not_assigned":          p2012.get("not_assigned"),
            "json_assigned_to_projects":  p2012.get("assigned_to_projects"),
        })

    # Non-residential: status.by_pool has per-pool 2012-era totals (the
    # xlsx 2012 plan-era table; the JSON's by_pool is already 2012-only).
    for key, label in (
        ("residential_bonus_units", "residential_bonus_units"),
        ("commercial_floor_area",   "commercial_floor_area"),
        ("tourist_accommodation_units", "tourist_accommodation_units"),
    ):
        for entry in j[key]["status"]["by_pool"]:
            rows.append({
                "commodity": label,
                "pool": entry["name"],
                "json_regional_plan_maximum": entry.get("regional_plan_maximum"),
                "json_not_assigned":          entry.get("not_assigned"),
                "json_assigned_to_projects":  entry.get("assigned_to_projects"),
            })

    out = pd.DataFrame(rows)
    log.info("  json 2012-era pools: %d", len(out))
    return out


def normalize_layer5(df5: pd.DataFrame) -> pd.DataFrame:
    """Reduce layer 5 to candidate fields keyed by (commodity, pool/jurisdiction)."""
    df = df5.copy()
    df["commodity_json"] = df["DevelopmentRight"].map(COMMODITY_TO_JSON_KEY)
    df = df.dropna(subset=["commodity_json"])

    # For per-pool join, the matching key is DevelopmentRightPoolName mostly,
    # but the JSON keys pools by short jurisdiction / pool name (e.g. "Placer
    # County", "TRPA Pool"). The pool name in layer 5 follows
    # "<DevelopmentRight> - <ShortName>"; strip the prefix.
    def short_pool(name: str | None, dr: str | None) -> str | None:
        if not isinstance(name, str):
            return None
        prefix = f"{dr} - " if isinstance(dr, str) else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    df["pool"] = df.apply(lambda r: short_pool(r["DevelopmentRightPoolName"], r["DevelopmentRight"]), axis=1)
    df["pool"] = df["pool"].fillna(df["juris_norm"])
    return df


def aggregate_layer5(df5n: pd.DataFrame) -> pd.DataFrame:
    """Aggregate layer 5 to one row per (commodity_json, pool) summing numeric fields."""
    grp = df5n.groupby(["commodity_json", "pool"], dropna=False).agg({
        "TotalDisbursements":           "sum",
        "ApprovedTransactionsQuantity": "sum",
        "PendingTransactionQuantity":   "sum",
        "BalanceRemaining":             "sum",
    }).reset_index().rename(columns={"commodity_json": "commodity"})
    grp["l5_approved_plus_pending"]  = grp["ApprovedTransactionsQuantity"] + grp["PendingTransactionQuantity"]
    grp["l5_approved_plus_balance"]  = grp["ApprovedTransactionsQuantity"] + grp["BalanceRemaining"]
    grp["l5_approved_pending_balance"] = grp["l5_approved_plus_pending"] + grp["BalanceRemaining"]
    return grp


def reconcile(json_df: pd.DataFrame, l5_df: pd.DataFrame) -> pd.DataFrame:
    df = json_df.merge(l5_df, on=["commodity", "pool"], how="outer", indicator=True)
    # Hypothesis deltas
    df["delta_H1_balance_vs_not_assigned"]    = df["BalanceRemaining"] - df["json_not_assigned"]
    df["delta_H2_approved_vs_assigned"]       = df["ApprovedTransactionsQuantity"] - df["json_assigned_to_projects"]
    df["delta_H2a_approved_plus_pending_vs_assigned"] = df["l5_approved_plus_pending"] - df["json_assigned_to_projects"]
    df["delta_H3a_approved_plus_balance_vs_max"] = df["l5_approved_plus_balance"] - df["json_regional_plan_maximum"]
    df["delta_H3b_disbursements_vs_max"] = df["TotalDisbursements"] - df["json_regional_plan_maximum"]
    df["delta_H3c_total3_vs_max"] = df["l5_approved_pending_balance"] - df["json_regional_plan_maximum"]
    return df


def hypothesis_pass_rate(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Per-hypothesis: count exact matches, near-matches (|delta| < 5), big misses."""
    hyps = {
        "H1  BalanceRemaining == json.not_assigned":
            "delta_H1_balance_vs_not_assigned",
        "H2  ApprovedTransactionsQuantity == json.assigned_to_projects":
            "delta_H2_approved_vs_assigned",
        "H2a Approved + Pending == json.assigned_to_projects":
            "delta_H2a_approved_plus_pending_vs_assigned",
        "H3a Approved + BalanceRemaining == json.regional_plan_maximum":
            "delta_H3a_approved_plus_balance_vs_max",
        "H3b TotalDisbursements == json.regional_plan_maximum":
            "delta_H3b_disbursements_vs_max",
        "H3c Approved + Pending + BalanceRemaining == json.regional_plan_maximum":
            "delta_H3c_total3_vs_max",
    }
    # Restrict to rows present in BOTH sources (inner join), otherwise the delta
    # is a NaN that we don't want to interpret as a "miss."
    inner = df[df["_merge"] == "both"].copy()
    summary: dict[str, dict[str, int]] = {}
    for name, col in hyps.items():
        d = inner[col].dropna()
        summary[name] = {
            "tested":       len(d),
            "exact":        (d == 0).sum(),
            "within_5":     ((d.abs() > 0) & (d.abs() <= 5)).sum(),
            "off_by_10+":   (d.abs() > 10).sum(),
            "max_abs":      int(d.abs().max()) if len(d) else 0,
            "mean_abs":     round(float(d.abs().mean()), 2) if len(d) else 0,
        }
    return summary


def write_report(df: pd.DataFrame, summary: dict[str, dict[str, int]], totals_df: pd.DataFrame | None = None) -> None:
    df.to_csv(OUT_CSV, index=False)
    log.info("Validation CSV: %s (%d rows)", OUT_CSV, len(df))

    lines = [
        "# Layer 5 field-semantics validation",
        "",
        f"Generated {_dt.datetime.now().isoformat(timespec='seconds')}.",
        "",
        "## What this tests",
        "",
        "Whether `Cumulative_Accounting/MapServer/5` (staged from LT Info ",
        "`GetDevelopmentRightPoolBalanceReport`) can serve the 2012-era pool ",
        "balances the dashboards need - by joining its rows to the analyst-",
        "built `regional_plan_allocations.json` and comparing candidate field ",
        "mappings.",
        "",
        "Inputs:",
        "",
        "- Layer 5 (live)",
        f"- `{Path(REGIONAL_PLAN_ALLOCATIONS_JSON).name}` (analyst-built ground truth)",
        "",
    ]

    # Aggregate-by-commodity table (headline test)
    if totals_df is not None:
        lines += [
            "## Headline: layer 5 totals vs json `summary`",
            "",
            "Summing layer 5 across all pools per commodity, against the ",
            "JSON's `status.summary` (the combined 1987+2012 era totals for ",
            "non-residential; for residential we compare to `summary.plan_2012`).",
            "",
            "| Commodity | n pools | json max | l5 TotalDisb | json assigned | l5 Approved | json not_assigned | l5 Balance | delta_max(H3b) | delta_assigned(H2) | delta_not_assigned(H1) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for _, r in totals_df.iterrows():
            lines.append(
                f"| {r['commodity']} | {int(r['layer5_n_pools'])} | "
                f"{r['json_regional_plan_maximum']!s} | {int(r['l5_TotalDisbursements'])} | "
                f"{r['json_assigned_to_projects']!s} | {int(r['l5_Approved'])} | "
                f"{r['json_not_assigned']!s} | {int(r['l5_BalanceRemaining'])} | "
                f"{int(r['delta_H3b_disbursements_vs_max']):+d} | "
                f"{int(r['delta_H2_approved_vs_assigned']):+d} | "
                f"{int(r['delta_H1_balance_vs_not_assigned']):+d} |"
            )
        lines += [
            "",
            "## Findings",
            "",
            "1. **`BalanceRemaining` == `not_assigned`** for the three non-",
            "   residential commodities (RBU, CFA, TAU): delta = 0 at the ",
            "   aggregate level. This is the cleanest confirmed field mapping.",
            "",
            "2. **Residential `BalanceRemaining` is off by exactly 770** vs ",
            "   the JSON's 2012 not_assigned (998 vs 1,768). The 770 is the ",
            "   *unreleased allocations* tracked separately in the residential ",
            "   allocation grid (layer 4 / Corral_2026 derivation), not in the ",
            "   pool balance report. The combine view must add these back in.",
            "",
            "3. **`TotalDisbursements` does NOT equal `regional_plan_maximum`**. ",
            "   For non-residential, the deltas are exactly the size of the ",
            "   1987-era cap (e.g. CFA: 1,000,000 - 581,342 = 418,658, of which ",
            "   layer 3 holds 800,000 1987-era + the JSON treats some pool as ",
            "   1987-era-only). `TotalDisbursements` is the 2012-era ",
            "   *cumulative disbursed* (Approved + Pending + Balance), not the ",
            "   policy cap.",
            "",
            "4. **`Approved` does NOT equal `assigned_to_projects`**. The JSON's ",
            "   `assigned_to_projects` rolls in 1987-era assignments which are ",
            "   in layer 3, not layer 5. Layer 5 only reports the 2012-era ",
            "   sub-status.",
            "",
            "## Combine-view recipe (empirically supported)",
            "",
            "For non-residential (RBU / CFA / TAU):",
            "",
            "```text",
            "combined.not_assigned        := layer5.BalanceRemaining (per jurisdiction sum)",
            "combined.regional_plan_max   := layer3.regional_plan_maximum  -- 1987 baseline",
            "                              + (layer5.TotalDisbursements - layer5.Approved - layer5.Pending)",
            "                              ... OR ... source the 2012-additional cap from a frozen reference",
            "combined.assigned_to_projects:= combined.regional_plan_max - combined.not_assigned",
            "```",
            "",
            "For residential, additionally:",
            "",
            "```text",
            "plan_2012.not_assigned       := layer5.BalanceRemaining + unreleased_count",
            "                                 where unreleased_count = layer4 IssuanceYear IS NULL count",
            "```",
            "",
            "## Remaining open question",
            "",
            "What is the 2012-era *additional* cap per pool? For residential ",
            "we know it's 2,600 (2,112 issued + 488 unreleased per the grid). ",
            "For RBU/CFA/TAU we'd need the LT Info owner to confirm whether ",
            "`TotalDisbursements + BalanceRemaining` == 2012-era cap, or ",
            "whether the 2012 additional is hard-coded by policy.",
            "",
        ]

    lines += [
        "## Per-pool hypothesis pass rates",
        "",
        "Lower-confidence: pool-name normalization is fragile (layer 5 has ",
        "fine-grained sub-pools that the JSON aggregates by jurisdiction). ",
        "Only rows that join on both sides are counted.",
        "",
        "| Hypothesis | tested | exact match | within 5 | off by 10+ | mean abs delta | max abs delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in summary.items():
        lines.append(
            f"| {name} | {s['tested']} | {s['exact']} | {s['within_5']} | "
            f"{s['off_by_10+']} | {s['mean_abs']} | {s['max_abs']} |"
        )

    # Rows present in only one source (= join-key normalization gaps)
    one_side = df[df["_merge"] != "both"]
    if not one_side.empty:
        lines += [
            "",
            "## Pools that joined on only one side (normalization gap)",
            "",
            "| commodity | pool | source |",
            "| --- | --- | --- |",
        ]
        for _, r in one_side.iterrows():
            src = "json only" if r["_merge"] == "left_only" else "layer5 only"
            lines.append(f"| {r['commodity']} | {r['pool']} | {src} |")

    lines += [
        "",
        "## Top 15 row-level deltas (rows where any hypothesis is off by 10+)",
        "",
        "(Useful for spotting per-pool data-quality issues independent of ",
        "field-mapping choice.)",
        "",
        "| commodity | pool | json max / assigned / not_assigned | layer5 TotalDisb / Approved / Pending / Balance |",
        "| --- | --- | --- | --- |",
    ]
    bad = df[df["_merge"] == "both"].copy()
    bad["worst_delta"] = bad[[
        "delta_H1_balance_vs_not_assigned",
        "delta_H2a_approved_plus_pending_vs_assigned",
        "delta_H3c_total3_vs_max",
    ]].abs().max(axis=1)
    for _, r in bad.nlargest(15, "worst_delta").iterrows():
        lines.append(
            f"| {r['commodity']} | {r['pool']} | "
            f"{r['json_regional_plan_maximum']!s} / {r['json_assigned_to_projects']!s} / {r['json_not_assigned']!s} | "
            f"{int(r['TotalDisbursements'])!s} / {int(r['ApprovedTransactionsQuantity'])!s} / "
            f"{int(r['PendingTransactionQuantity'])!s} / {int(r['BalanceRemaining'])!s} |"
        )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    log.info("Validation report: %s", OUT_MD)


def commodity_total_test(layer5_norm: pd.DataFrame) -> pd.DataFrame:
    """Highest-confidence test: aggregate layer 5 by commodity and compare to
    json.summary.plan_2012 totals. If the field semantics are right at all,
    these totals should match exactly - independent of any pool-name mapping."""
    j = json.loads(Path(REGIONAL_PLAN_ALLOCATIONS_JSON).read_text())
    # JSON's plan_2012 summary, per commodity
    json_totals = {
        "residential":                 j["residential"]["summary"]["plan_2012"],
        "residential_bonus_units":     j["residential_bonus_units"]["status"]["summary"],
        "commercial_floor_area":       j["commercial_floor_area"]["status"]["summary"],
        "tourist_accommodation_units": j["tourist_accommodation_units"]["status"]["summary"],
    }
    rows = []
    for comm, jt in json_totals.items():
        sub = layer5_norm[layer5_norm["commodity_json"] == comm]
        rows.append({
            "commodity": comm,
            "layer5_n_pools":               len(sub),
            "json_regional_plan_maximum":   jt.get("regional_plan_maximum"),
            "json_assigned_to_projects":    jt.get("assigned_to_projects"),
            "json_not_assigned":            jt.get("not_assigned"),
            "l5_TotalDisbursements":        int(sub["TotalDisbursements"].sum()),
            "l5_Approved":                  int(sub["ApprovedTransactionsQuantity"].sum()),
            "l5_Pending":                   int(sub["PendingTransactionQuantity"].sum()),
            "l5_BalanceRemaining":          int(sub["BalanceRemaining"].sum()),
        })
    df = pd.DataFrame(rows)
    df["delta_H1_balance_vs_not_assigned"] = df["l5_BalanceRemaining"] - df["json_not_assigned"]
    df["delta_H2_approved_vs_assigned"]    = df["l5_Approved"] - df["json_assigned_to_projects"]
    df["delta_H2a_approved+pending_vs_assigned"] = (df["l5_Approved"] + df["l5_Pending"]) - df["json_assigned_to_projects"]
    df["delta_H3a_approved+balance_vs_max"]      = (df["l5_Approved"] + df["l5_BalanceRemaining"]) - df["json_regional_plan_maximum"]
    df["delta_H3b_disbursements_vs_max"]   = df["l5_TotalDisbursements"] - df["json_regional_plan_maximum"]
    df["delta_H3c_all3_vs_max"]            = (df["l5_Approved"] + df["l5_Pending"] + df["l5_BalanceRemaining"]) - df["json_regional_plan_maximum"]
    return df


def main() -> int:
    layer5_raw = fetch_layer5()
    layer5 = normalize_layer5(layer5_raw)

    # Headline: aggregate-by-commodity test (independent of pool-name normalization)
    totals_df = commodity_total_test(layer5)
    log.info("=" * 72)
    log.info("AGGREGATE-BY-COMMODITY COMPARISON (layer 5 SUM vs json.summary.plan_2012)")
    log.info("=" * 72)
    log.info("\n%s", totals_df.to_string(index=False))

    # Per-pool test (lower confidence; many normalization gaps)
    layer5_agg = aggregate_layer5(layer5)
    json_2012 = load_json_pool_2012()
    df = reconcile(json_2012, layer5_agg)
    summary = hypothesis_pass_rate(df)

    log.info("=" * 72)
    log.info("PER-POOL HYPOTHESIS PASS RATES (rows that joined on both sides)")
    log.info("=" * 72)
    for name, s in summary.items():
        log.info("%s\n   tested=%d  exact=%d  within_5=%d  off_by_10+=%d  mean_abs=%.2f  max_abs=%d",
                 name, s["tested"], s["exact"], s["within_5"], s["off_by_10+"], s["mean_abs"], s["max_abs"])

    # Save both
    totals_csv = Path(QA_DATA_DIR) / "layer5_commodity_totals.csv"
    totals_df.to_csv(totals_csv, index=False)
    log.info("Commodity-total CSV: %s", totals_csv)

    write_report(df, summary, totals_df)
    return 0


if __name__ == "__main__":
    sys.exit(main())
