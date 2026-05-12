# Track A — Genealogy → Current Parcel

> **Status: existing infra in place; canonical resolver pending consolidation.**
> **Audience: TRPA dev team, anyone reading or extending the genealogy pipeline.**

One of three parallel tracks of work in this repo (the others are Track B — Allocation Tracking, and Track C — QA Corrections). Track A's job is **never lose track of an APN** as parcels split, merge, get renamed, or shift format (the 2018 leading-zero reformat that affected multiple counties). Every other track joins on parcel; Track A is the substrate that makes those joins reliable.

## What this track does

Three responsibilities:

1. **APN canonicalization** — turn any raw APN string into a single canonical form. Implemented in [`parcel_development_history_etl/utils.py`](../parcel_development_history_etl/utils.py) as `canonical_apn(raw)` (broad — pads any standard `NNN-NNN-NN(N)` to 3-digit third segment) plus the existing `el_pad`/`el_depad` for El-Dorado-specific cases.
2. **Genealogy event sourcing** — collect parcel split/merge/rename events from 4 distinct source systems into per-source CSVs, and a master CSV that consolidates them. Today this lives across multiple scripts; goal is a single canonical resolver.
3. **APN resolution at query time** — given an APN and an as-of date, walk the genealogy chain to return the canonical parcel ID at that date. Schema target: `fn_resolve_apn(@apn, @as_of)` (proposed in [target_schema.md](./target_schema.md)).

## Source systems (4 lineages, currently independent)

Each genealogy CSV in [`data/qa_data/`](../data/qa_data/) carries one source's view of parcel changes:

| File | Source | Rows |
|---|---|---:|
| [`apn_genealogy_master.csv`](../data/qa_data/apn_genealogy_master.csv) | Manual master (Ken-curated) | ~5K |
| [`apn_genealogy_accela.csv`](../data/qa_data/apn_genealogy_accela.csv) | Accela permit system parent/child links | ~30K |
| [`apn_genealogy_ltinfo.csv`](../data/qa_data/apn_genealogy_ltinfo.csv) | LT Info parcel records | ~3K |
| [`apn_genealogy_spatial.csv`](../data/qa_data/apn_genealogy_spatial.csv) | Spatial overlap detection (geometric) | ~1K |
| [`apn_genealogy_tahoe.csv`](../data/qa_data/apn_genealogy_tahoe.csv) | Consolidated current-best-guess (input to ETL) | ~37K |

Each script (`build_genealogy_master.py`, `parse_genealogy_sources.py`, `build_spatial_genealogy.py`, `s02b_genealogy.py`) maintains its own slice. The consolidation step (`s02b_genealogy.py`) is the one closest to a canonical resolver but doesn't yet expose `fn_resolve_apn` cleanly to other tracks.

## Data flow

```
                  ┌─────────────────────────────────────────────────┐
                  │  Source systems (4)                             │
                  │  Manual master · Accela · LT Info · Spatial     │
                  └──────────────────────┬──────────────────────────┘
                                         │
            [parse_genealogy_sources.py + build_genealogy_master.py +
                            build_spatial_genealogy.py]
                                         │
                                         ▼
                  ┌─────────────────────────────────────────────────┐
                  │  data/qa_data/apn_genealogy_*.csv (5 files)     │
                  └──────────────────────┬──────────────────────────┘
                                         │
                       [s02b_genealogy.py (in main ETL)]
                                         │
                                         ▼
                  ┌─────────────────────────────────────────────────┐
                  │  Canonical APN resolver — used by every track   │
                  │  (currently per-script; goal: utils-level fn)   │
                  └─────────────────────────────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
  Track B (allocations)           Track C (QA corrections)         Track A QA
  joins parcels via canonical     joins Ken's CA Changes via       internal
  APN to allocation/permit        canonical APN to s06             validation
                                  detections
```

## Key utilities (use these, don't reinvent)

```python
from parcel_development_history_etl.utils import canonical_apn, el_pad, el_depad
```

- **`canonical_apn(raw)`** — broad. Pads any `NNN-NNN-NN(N)` to 3-digit third segment. Returns `None` for empty/NaN. Other formats (Douglas long-form `1418-03-301-010`) pass through unchanged. **This is what Track C's loader uses.**
- **`el_pad(apn)`** — El-Dorado-specific 2→3 digit pad.
- **`el_depad(apn)`** — reverse direction.

## Cadence

- **Continuous** — new genealogy events get detected as the source systems change. No formal "sweep" cadence like Track C; the master CSV gets updated as needed.
- **APN canonicalization is read-time** — every track that joins on parcel calls `canonical_apn` on the input string before lookup. No batch normalization step.

## Open issues

### O1. Consolidate the 4 source CSVs into one canonical resolver

Currently each script has its own consolidation logic. Goal: a single `fn_resolve_apn(@apn, @as_of)` (proposed in `target_schema.md`'s implementation notes) that walks the merged genealogy graph and returns the canonical APN at the requested date. Termination conditions, tie-breaking, cycle detection all already specified — see `target_schema.md` §"Multi-hop genealogy resolver."

### O2. Schema land — `ParcelGenealogyEventEnriched`

`target_schema.md` proposes this as a 10+ column extension over Corral's 3-column `dbo.ParcelGenealogy`. Carries `EventType`, `IsPrimary`, `OverlapPct`, `Source`, `SourcePriority`, `Confidence`, `Verified`. Once the schema lands, the 4 CSVs feed it instead of staying as flat files.

### O3. Genealogy-restatement change events

When a new `old_apn → new_apn` mapping affects historical rows in `ParcelExistingDevelopment`, do we **rewrite** in place or insert `ChangeSource='genealogy_restatement'` rows in `ParcelDevelopmentChangeEvent`? Q8 in `target_schema.md` recommends the latter (preserves audit trail). Need to wire that into `s02b_genealogy.py`.

### O4. Track A uses Track A's own canonicalization, but Track C bypassed s02b_genealogy.py

The loader notebook `04_load_ca_changes.ipynb` calls `canonical_apn` directly from `utils.py` instead of going through `s02b_genealogy.py`. That's fine for the leading-zero case but doesn't catch APN renames or splits. Once O1 lands, Track C should switch to the resolver function.

### O5. CSV vs DB resolver

For now the resolver runs in Python on CSV inputs. Once the DB schema lands, `fn_resolve_apn` becomes a SQL function. The Python and SQL versions should produce identical output — a contract test would catch drift.

## Where this fits in the broader 3-track plan

| Track | Relationship to Track A |
|---|---|
| **A — Genealogy** *(this doc)* | substrate: every parcel join goes through canonical APN |
| **B — Allocations** | uses canonical APN to join allocations to parcels and to dashboards' parcel-grain views |
| **C — QA Corrections** | uses canonical APN to load Ken's per-APN CA Changes; once O1 lands, switches to full resolver |

Track A is the most stable but also the most under-documented. The ETL scripts work; the schema proposal is in `target_schema.md`; this doc consolidates the moving parts in one place.

## Files reference

- **Schema:** [`target_schema.md`](./target_schema.md) §`ParcelGenealogyEventEnriched` and §"Multi-hop genealogy resolver"
- **Utils:** [`../parcel_development_history_etl/utils.py`](../parcel_development_history_etl/utils.py) — `canonical_apn`, `el_pad`, `el_depad`
- **ETL step:** [`../parcel_development_history_etl/steps/s02b_genealogy.py`](../parcel_development_history_etl/steps/s02b_genealogy.py)
- **Source builders:** [`../parcel_development_history_etl/scripts/parse_genealogy_sources.py`](../parcel_development_history_etl/scripts/parse_genealogy_sources.py), [`build_genealogy_master.py`](../parcel_development_history_etl/scripts/build_genealogy_master.py), [`build_spatial_genealogy.py`](../parcel_development_history_etl/scripts/build_spatial_genealogy.py)
- **Source CSVs:** [`../data/qa_data/apn_genealogy_*.csv`](../data/qa_data/) (5 files)
- **Diagnostic scripts:** [`../parcel_development_history_etl/scripts/diagnose_*.py`](../parcel_development_history_etl/scripts/) — investigation tools used during the 2026 sweep to root-cause unknown APNs
