# Validation Skill: Parcel Development History Conflict Detection

## Purpose

`validation.py` is a standalone post-ETL QA script. After the main ETL pipeline
builds `Parcel_Development_History`, this script reads it, queries external truth
sources (physical footprints, permits, certificates), and writes a `QA_Flag_Table`
(APN × Year) to the same GDB. It **never modifies** the source feature class.

The goal is to surface the ~1% of weird cases (phantom development, unit dropouts,
genealogy disconnects, active-permit mismatches) so you can apply local knowledge
without touching the underlying dataset.

---

## Invocation

```bash
cd parcel_development_history_etl
C:\...\arcgispro-py3\python.exe validation.py                      # all checks
C:\...\arcgispro-py3\python.exe validation.py --flags PHANTOM DROPOUT   # subset
C:\...\arcgispro-py3\python.exe validation.py --apn 035-123-456    # debug one APN
```

**Available flags:** `PHANTOM`, `DROPOUT`, `GENEALOGY`, `UNVERIFIED`

`DROPOUT` and `GENEALOGY` require no external services and run immediately.
`PHANTOM` and `UNVERIFIED` query REST services; if URLs are not yet configured
in `config.py`, those checks are skipped with a warning.

---

## Services (Truth Matrix)

| Rank | Name | config.py key | What it checks |
|------|------|--------------|----------------|
| 1 | Base Anchor | _(OUTPUT_FC)_ | 2012–2025 known-good parcel data |
| 2 | Impervious Surface | `IMPERVIOUS_SVC` | Physical building footprint present on parcel |
| 3 | Permits | `LTINFO_PERMITS` | Permit finalized year from LTinfo |
| 4 | Allocations | `LTINFO_ALLOCS` | Legal allocation exists for unit year _(future)_ |
| 5 | BMP Certificate | `BMP_CERT_SVC` | Active BMP certificate for that year range |
| 6 | VHR Permit | `VHR_PERMIT_SVC` | Active vacation home rental permit for that year |
| 7 | Dev Rights | `LTINFO_DEV_RIGHTS` | Aspatial unit transfers _(future)_ |
| 8 | County Land Use | _(future)_ | Land use / improvement status shift _(future)_ |

To activate a service check: set its URL constant in `config.py` and, if the
field names returned differ from what `validation.py` expects, update the
`_fetch_*` function for that service.

---

## Flag Rules

Each rule produces rows in `QA_Flag_Table`. A single APN × Year can have
multiple flags; they are collapsed into one row with pipe-delimited `FLAG_CODE`
and semicolon-concatenated `EVIDENCE`.

---

### A. PHANTOM — "Developed on the ground but shows 0 units"

**Condition:**
```
Residential_Units == 0
AND (
    impervious_footprint_detected(APN)          # IMPERVIOUS_SVC
    OR permit_finaled_year(APN) <= Year         # LTINFO_PERMITS
)
```

**Evidence format:** `"Impervious"` and/or `"Permit:{year}"`

**Skip if:** Both IMPERVIOUS_SVC and LTINFO_PERMITS are empty strings in config.py.

**Interpretation:** The parcel appears physically developed but the attribute
data shows vacant. Could be a missing CSV entry, a geometry mismatch, or a
county data lag.

---

### B. DROPOUT — "Yo-yo unit gap"

**Condition:**
```
Residential_Units[Year-1] > 0
AND Residential_Units[Year]   == 0
AND Residential_Units[Year+1] > 0
```

**Evidence format:** `"Units: {prev}={N}, {yr}=0, {next}={N}"`

**No service needed.** Pure in-memory check on OUTPUT_FC.

**Interpretation:** Likely a temporary data gap in the county source. The unit
count "blinks off" for one year between two non-zero years.

---

### C. GENEALOGY — "Units lost at subdivision"

**Condition:**
```
QA_Genealogy_Applied has a record where:
    Total_Units_Moved > 0
    AND New_APN has Residential_Units == 0 for years >= Change_Year
```

**Evidence format:**
`"Old:{old_apn}→New:{new_apn}; Units moved:{N}; New APN missing units for years:[list]"`

**Source:** `QA_Genealogy_Applied` GDB table (written by S02b during the main ETL run).
No external service needed.

**Interpretation:** The genealogy substitution remapped units from `old_apn` to
`new_apn`, but the successor APN has no unit count in the FC for the affected years.
Could indicate a missed CSV update after a parcel split/rename.

---

### D. UNVERIFIED — "Active admin record but shows 0 units"

**Condition:**
```
Residential_Units == 0
AND (
    bmp_certificate_active_in(APN, Year)    # BMP_CERT_SVC
    OR vhr_permit_active_in(APN, Year)      # VHR_PERMIT_SVC
)
```

**Evidence format:** `"BMP"` and/or `"VHR"`

**Skip if:** Both BMP_CERT_SVC and VHR_PERMIT_SVC are empty strings in config.py.

**Interpretation:** Administrative records (BMP cert or VHR permit) indicate the
parcel is in active residential or tourist use, but the data shows 0 units.
Could be a data mismatch between the CSV maintainer and the permit/cert system.

---

## Output: QA_Flag_Table Schema

| Field | Type | Description |
|-------|------|-------------|
| `APN` | TEXT(50) | Parcel identifier |
| `YEAR` | LONG | Year slice flagged |
| `FLAG_CODE` | TEXT(50) | `PHANTOM`, `DROPOUT`, `GENEALOGY`, `UNVERIFIED`; pipe-delimited if multiple |
| `CSV_VAL` | LONG | `Residential_Units` in OUTPUT_FC at time of run |
| `MATRIX_VAL` | LONG | Suggested value from truth matrix (0 if indeterminate) |
| `EVIDENCE` | TEXT(500) | Semicolon-delimited source labels with detail |
| `QA_STATUS` | TEXT(20) | Manually set: `"Pending"` (default), `"Confirmed"`, `"Ignore"` |

---

## Manual Review Workflow

1. Run `validation.py` after the main ETL.
2. In ArcGIS Pro: join `QA_Flag_Table` to `Parcel_Development_History`
   on `APN + YEAR`.
3. Filter `QA_STATUS = 'Pending'` to see unreviewed flags.
4. For each flag, inspect the parcel on the map using the EVIDENCE field as a guide.
5. Set `QA_STATUS` to `"Confirmed"` (real issue — fix the CSV or service data)
   or `"Ignore"` (false positive — add a note in EVIDENCE if useful).

**SQL quick-filter example:**
```sql
SELECT * FROM QA_Flag_Table
WHERE APN LIKE '035%' AND FLAG_CODE = 'PHANTOM'
ORDER BY YEAR DESC;
```

---

## Adding a New Flag

1. Add the rule to this file under **Flag Rules** with:
   - Condition (pseudocode)
   - Evidence format
   - Skip condition
   - Interpretation note
2. If a new service is needed, add its URL constant to `config.py`.
3. Ask Claude: _"Update validation.py to match validation.md"_ —
   Claude will read this file and implement the new check.

---

## Update Instructions for Claude

> When this file is updated, re-read it in full and update `validation.py` to match.
> Specifically:
> - Each entry under **Flag Rules** maps to a `check_*()` function in `validation.py`.
> - Each entry under **Services** maps to a `_fetch_*()` function and a config key.
> - The **Output schema** maps to `_TEXT_LENGTHS` and the `_make_flag()` return dict.
> - Do not change `validation.py` independently of this file.
> - After updating, verify that `--flags DROPOUT GENEALOGY` still runs without
>   any service URLs configured.
