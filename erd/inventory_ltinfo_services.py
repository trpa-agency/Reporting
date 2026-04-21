"""Catalog LTinfo web services referenced in this repo.

The public /WebServices/List directory is behind a Keystone login, so we seed
from the endpoints already wired into repo code and probe each for its response
schema using our LTINFO_API_KEY.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

OUT_DIR = Path(__file__).resolve().parent
load_dotenv(OUT_DIR.parent / ".env")

TOKEN = os.environ.get("LTINFO_API_KEY", "")
BASE = "https://www.laketahoeinfo.org/WebServices"
TIMEOUT = 120

# Seeded from repo usage (development_rights_etl/, general/, ipynbs).
SEED = [
    ("GetAllParcels", "Parcel master list (APN, jurisdiction, land use)."),
    ("GetTransactedAndBankedDevelopmentRights", "All transacted + banked dev rights; history of transfers."),
    ("GetBankedDevelopmentRights", "Currently banked development rights inventory."),
    ("GetParcelDevelopmentRightsForAccela", "Parcel-level dev rights as exposed to the Accela permit system."),
    ("GetDeedRestrictedParcels", "Parcels with recorded deed restrictions (affordable/achievable housing, etc.)."),
    ("GetParcelIPESScores", "IPES scores per parcel (land capability sensitivity index)."),
]


def probe(endpoint: str) -> dict:
    url = f"{BASE}/{endpoint}/JSON/{TOKEN}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return {"status": "error", "url": url, "error": str(exc)[:300]}
    if r.status_code != 200:
        return {"status": f"http_{r.status_code}", "url": url}
    try:
        body = r.json()
    except ValueError:
        return {"status": "non_json", "url": url, "snippet": r.text[:200]}
    sample = body[0] if isinstance(body, list) and body else body if isinstance(body, dict) else None
    fields = (
        {k: type(v).__name__ for k, v in sample.items()}
        if isinstance(sample, dict)
        else {"_type": type(body).__name__}
    )
    return {
        "status": "ok",
        "url": url,
        "record_count": len(body) if isinstance(body, list) else 1,
        "fields": fields,
        "sample_record": sample,
    }


def main() -> None:
    results = []
    for name, desc in SEED:
        print(f"probe {name}")
        results.append({"name": name, "description": desc, "probe": probe(name)})
    # Also record the Accela Excel API (not JSON, not probed here)
    results.append(
        {
            "name": "GetAccelaRecordDetailsExcel",
            "description": "Per-record Accela permit details as Excel file. URL pattern: https://laketahoeinfo.org/Api/GetAccelaRecordDetailsExcel/{GUID} (per-record, not a bulk feed).",
            "probe": {"status": "not_probed", "reason": "binary xlsx output; requires per-record GUID"},
        }
    )
    (OUT_DIR / "ltinfo_services.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    ok = sum(1 for r in results if r["probe"].get("status") == "ok")
    print(f"OK: {ok}/{len(results)}")
    print(f"Wrote {OUT_DIR / 'ltinfo_services.json'}")


if __name__ == "__main__":
    main()
