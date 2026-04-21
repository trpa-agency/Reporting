"""Validate claim: AuditLog replay on ParcelCommodityInventory reproduces yearly
values in ExistingResidential_2012_2025_unstacked.csv (SFRUU + MFRUU per parcel).

Read-only: all SQL is SELECT. Writes erd/validate_auditlog_replay.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ERD = Path(__file__).resolve().parent
sys.path.insert(0, str(ERD))
from db_corral import get_engine  # noqa: E402

REPO = ERD.parent
CSV = REPO / "data" / "raw_data" / "ExistingResidential_2012_2025_unstacked.csv"
YEARS = [2016, 2018, 2020, 2022, 2023]  # within AuditLog horizon
COMMODITY_IDS = [5, 14]  # SFRUU + MFRUU
SAMPLE_SIZE = 25


REPLAY_SQL = text("""
WITH changes AS (
    SELECT al.RecordID AS PCIID,
           al.NewValue,
           al.AuditLogDate,
           ROW_NUMBER() OVER (PARTITION BY al.RecordID
                              ORDER BY al.AuditLogDate DESC) AS rn
    FROM dbo.AuditLog al
    WHERE al.TableName = 'ParcelCommodityInventory'
      AND al.ColumnName = 'VerifiedPhysicalInventoryQuantity'
      AND al.AuditLogDate <= :asof
),
latest AS (
    SELECT PCIID, NewValue FROM changes WHERE rn = 1
)
SELECT p.ParcelNumber AS APN,
       SUM(TRY_CAST(COALESCE(ly.NewValue,
                             CAST(pci.VerifiedPhysicalInventoryQuantity AS varchar))
                    AS int)) AS Qty
FROM dbo.ParcelCommodityInventory pci
JOIN dbo.Parcel p               ON pci.ParcelID = p.ParcelID
JOIN dbo.LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
LEFT JOIN latest ly             ON ly.PCIID = pci.ParcelCommodityInventoryID
WHERE lct.CommodityID IN :commodity_ids
  AND p.ParcelNumber IN :apns
GROUP BY p.ParcelNumber
""").bindparams()


def select_sample(df: pd.DataFrame, corral_apns: set[str]) -> pd.DataFrame:
    df = df.copy()
    for c in ["2020 Final", "2023 Final"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    candidates = df[(df["2020 Final"].fillna(0) > 0) & (df["2023 Final"].fillna(0) > 0)]
    candidates = candidates[candidates["APN"].isin(corral_apns)]
    # Prefer stable and varied values
    steady = candidates[candidates["2020 Final"] == candidates["2023 Final"]].head(SAMPLE_SIZE // 2)
    changed = candidates[candidates["2020 Final"] != candidates["2023 Final"]].head(SAMPLE_SIZE // 2)
    return pd.concat([steady, changed]).head(SAMPLE_SIZE)


def main() -> None:
    engine = get_engine()

    with engine.connect() as conn:
        apns_in_corral = {
            r[0] for r in conn.execute(
                text("SELECT ParcelNumber FROM dbo.Parcel WHERE ParcelNumber IS NOT NULL")
            )
        }

    csv = pd.read_csv(CSV, dtype=str)
    csv["APN"] = csv["APN"].astype(str).str.strip()
    sample = select_sample(csv, apns_in_corral)
    apns = sample["APN"].tolist()
    print(f"Sampled {len(apns)} APNs: first 5 = {apns[:5]}")

    # Diagnostic: which sampled APNs even have SFRUU/MFRUU PCI rows?
    apn_coverage = {}
    with engine.connect() as conn:
        sql_cov = """
            SELECT p.ParcelNumber, COUNT(pci.ParcelCommodityInventoryID) AS pci_rows
            FROM dbo.Parcel p
            LEFT JOIN dbo.ParcelCommodityInventory pci ON pci.ParcelID = p.ParcelID
            LEFT JOIN dbo.LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
                 AND lct.CommodityID IN ({cids})
            WHERE p.ParcelNumber IN ({ph})
            GROUP BY p.ParcelNumber
        """.format(
            cids=",".join(str(x) for x in COMMODITY_IDS),
            ph=",".join(f":a{i}" for i in range(len(apns))),
        )
        for r in conn.execute(text(sql_cov), {f"a{i}": a for i, a in enumerate(apns)}):
            apn_coverage[r[0]] = int(r[1] or 0)
    tracked = sum(1 for v in apn_coverage.values() if v > 0)
    print(f"Corral PCI coverage for SFRUU/MFRUU: {tracked}/{len(apns)} sampled APNs have at least one row.")

    results = []
    with engine.connect() as conn:
        for yr in YEARS:
            asof = f"{yr}-12-31 23:59:59"
            stmt = text("""
                WITH changes AS (
                    SELECT al.RecordID AS PCIID,
                           al.NewValue,
                           al.AuditLogDate,
                           ROW_NUMBER() OVER (PARTITION BY al.RecordID
                                              ORDER BY al.AuditLogDate DESC) AS rn
                    FROM dbo.AuditLog al
                    WHERE al.TableName = 'ParcelCommodityInventory'
                      AND al.ColumnName = 'VerifiedPhysicalInventoryQuantity'
                      AND al.AuditLogDate <= :asof
                ),
                latest AS (SELECT PCIID, NewValue FROM changes WHERE rn = 1)
                SELECT p.ParcelNumber AS APN,
                       SUM(TRY_CAST(COALESCE(ly.NewValue,
                                             CAST(pci.VerifiedPhysicalInventoryQuantity AS varchar))
                                    AS int)) AS Qty
                FROM dbo.ParcelCommodityInventory pci
                JOIN dbo.Parcel p               ON pci.ParcelID = p.ParcelID
                JOIN dbo.LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
                LEFT JOIN latest ly             ON ly.PCIID = pci.ParcelCommodityInventoryID
                WHERE lct.CommodityID IN (5, 14)
                  AND p.ParcelNumber IN :apns
                GROUP BY p.ParcelNumber
            """).bindparams()
            stmt = stmt.bindparams()  # placeholder
            sql = """
                WITH changes AS (
                    SELECT al.RecordID AS PCIID,
                           al.NewValue,
                           al.AuditLogDate,
                           ROW_NUMBER() OVER (PARTITION BY al.RecordID
                                              ORDER BY al.AuditLogDate DESC) AS rn
                    FROM dbo.AuditLog al
                    WHERE al.TableName = 'ParcelCommodityInventory'
                      AND al.ColumnName = 'VerifiedPhysicalInventoryQuantity'
                      AND al.AuditLogDate <= :asof
                ),
                latest AS (SELECT PCIID, NewValue FROM changes WHERE rn = 1)
                SELECT p.ParcelNumber AS APN,
                       SUM(TRY_CAST(COALESCE(ly.NewValue,
                                             CAST(pci.VerifiedPhysicalInventoryQuantity AS varchar))
                                    AS int)) AS Qty
                FROM dbo.ParcelCommodityInventory pci
                JOIN dbo.Parcel p               ON pci.ParcelID = p.ParcelID
                JOIN dbo.LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
                LEFT JOIN latest ly             ON ly.PCIID = pci.ParcelCommodityInventoryID
                WHERE lct.CommodityID IN ({cids})
                  AND p.ParcelNumber IN ({apn_ph})
                GROUP BY p.ParcelNumber
            """.format(
                cids=",".join(str(x) for x in COMMODITY_IDS),
                apn_ph=",".join(f":a{i}" for i in range(len(apns))),
            )
            params = {"asof": asof, **{f"a{i}": a for i, a in enumerate(apns)}}
            corral_by_apn = {r[0]: int(r[1] or 0) for r in conn.execute(text(sql), params)}

            col = f"{yr} Final"
            for _, row in sample.iterrows():
                apn = row["APN"]
                csv_v = pd.to_numeric(row[col], errors="coerce")
                csv_v = int(csv_v) if pd.notna(csv_v) else 0
                corral_v = corral_by_apn.get(apn, 0)
                results.append(
                    {
                        "apn": apn,
                        "year": yr,
                        "csv_value": csv_v,
                        "corral_value": corral_v,
                        "match": csv_v == corral_v,
                        "delta": corral_v - csv_v,
                    }
                )

    # Summary
    total = len(results)
    matches = sum(1 for r in results if r["match"])
    by_year = {}
    for r in results:
        y = r["year"]
        by_year.setdefault(y, {"total": 0, "match": 0})
        by_year[y]["total"] += 1
        by_year[y]["match"] += int(r["match"])
    # Coverage-adjusted rate: restrict to APNs that Corral actually tracks.
    tracked_apns = {a for a, n in apn_coverage.items() if n > 0}
    tracked_results = [r for r in results if r["apn"] in tracked_apns]
    tracked_matches = sum(1 for r in tracked_results if r["match"])
    summary = {
        "sample_size": len(apns),
        "corral_tracked_apns": len(tracked_apns),
        "years": YEARS,
        "commodity_ids": COMMODITY_IDS,
        "commodity_label": "SFRUU + MFRUU (physical residential dwellings)",
        "total_checks": total,
        "total_matches": matches,
        "match_rate_all_sample": round(matches / total, 4) if total else 0.0,
        "match_rate_tracked_only": round(tracked_matches / len(tracked_results), 4)
            if tracked_results else 0.0,
        "apn_coverage": apn_coverage,
        "by_year": {
            y: {"rate": round(v["match"] / v["total"], 4), **v} for y, v in by_year.items()
        },
        "results": results,
    }
    out = ERD / "validate_auditlog_replay.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"Match rate (full sample): {matches}/{total} = {summary['match_rate_all_sample']:.1%}")
    print(f"Match rate (tracked APNs only): {tracked_matches}/{len(tracked_results)} = {summary['match_rate_tracked_only']:.1%}")
    for y, v in summary["by_year"].items():
        print(f"  {y}: {v['match']}/{v['total']} = {v['rate']:.1%}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
