# Pipeline Implementation Plan

Scope: Python data pipeline only. Produces `parcels.geojson` and `summary.json` for the burn area. Census block/tract and Altagether aggregates are out of scope for this phase.

---

## What the real data reveals

### Join key
`DINS.AIN` = `EPIC-LA.MAIN_AIN` (10-digit no-dash string, e.g. `"5841009012"`)

### DINS structure slots
Up to 5 slots per parcel (`DesignType1–5`, `Units1–5`, `SQFTmain1–5`). DesignType prefix determines structure class:
- `01xx` → SFR
- `02xx`–`05xx` → MFR
- Multi-slot `01xx` parcels with `UseDescription = "Single"` often represent main house + guesthouse (treat secondary slots as pre-fire ADU candidates)

### DAMAGE_1 enum (6 raw strings)
```
"No Damage" | "No Data/Vacant" | "Affected (1-9%)" | "Minor (10-25%)" | "Major (26-50%)" | "Destroyed (>50%)"
```

### EPIC-LA cases
Multiple records per APN. Two module types:
- `PermitManagement` — actual building permit; has `DESCRIPTION` with sqft and structured `ACCESSORY_DWELLING_UNIT`, `NEW_DWELLING_UNITS`
- `PlanManagement` — disaster recovery plan review; has `USE_PROPOSED1` and rebuild progress checkboxes

### Rebuild progress stages (ordered)
```
1 → Rebuild Applications Received
2 → Zoning Reviews Cleared
3 → Full Building Plans Received
4 → Building Plans Approved
5 → Building Permits Issued
6 → Rebuild In Construction
7 → Construction Completed
None → Temporary Housing (ignore for rebuild_progress)
```

---

## EPIC-LA free-text parsing strategy

Most post-fire sqft and structure-type classification requires parsing `DESCRIPTION`. Structured fields (`ACCESSORY_DWELLING_UNIT`, `NEW_DWELLING_UNITS`) are unreliable when a single permit covers multiple structures.

### Real description examples
```
# Single structure:
"EATON FIRE REBUILD - NEW 1-STORY 3,218 S.F. SINGLE FAMILY RESIDENCE WITH ..."
"EATON FIRE REBUILD - (N) 2,140 SF SFD (4 BED, 3 BATH)"

# Multi-structure (numbered list):
"1. EATON FIRE REBUILD - NEW 2-STORY 1107 SF SB9 (2 BEDROOMS AND 2 BATHROOMS) WITH 464 SF ATTACHED GARAGE ...\n2. EATON FIRE REBUILD - NEW 2-STORY 1115 SF SFR (2 BEDROOMS AND 2 BATHROOMS)\n3. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU \n4. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU"

# Like-for-like signals in PROJECT_NAME:
"Like-for-Like SFR Rebuild @ 3458 Monterosa Dr"
"Non-Like-for-Like SFR Rebuild @ 2915 N Fair Oaks Ave"
"Eaton Rebuild @ 411 Punahou St"   ← no explicit LFL label
```

### Parsing steps

**Step 1** — Split into segments. If description contains lines starting with `\d+\.`, treat each line as a separate structure. Otherwise treat the whole description as one segment.

**Step 2** — Extract sqft from each segment:
```python
re.search(r'(\d[\d,]*\.?\d*)\s*S\.?[FQ]\.?\s*(?:FT\.?)?', segment, re.IGNORECASE)
```
Strip commas, cast to float.

**Step 3** — Classify each segment's structure type:
```python
SFR_RE  = re.compile(r'\bS[FH]R?\b|\bSINGLE\s*FAMIL|\bSFD\b|\bSFH\b', re.I)
ADU_RE  = re.compile(r'\bADU\b|\bACCESSORY\s+DWELL', re.I)
JADU_RE = re.compile(r'\bJADU\b|\bJUNIOR\s+ADU', re.I)
SB9_RE  = re.compile(r'\bSB[- ]?9\b|\bSENATE\s+BILL\s*9', re.I)
MFR_RE  = re.compile(r'\bDUPLEX\b|\bTRIPLEX\b|\bMFR\b|\bMULTI[- ]?FAMILY', re.I)
```

**Step 4** — LFL claim from `PROJECT_NAME`:
- Contains `like-for-like` (case-insensitive, hyphens optional) → `lfl_claimed = True`
- Contains `non-like-for-like` → `lfl_claimed = False`
- Otherwise → `lfl_claimed = None`

### Case selection per APN
```python
# Filter to fire-related cases only
fire_cases = [c for c in cases
              if c["DISASTER_TYPE"] == "Eaton Fire (01-2025)"
              or (c["DESCRIPTION"] and re.search(r'eaton fire', c["DESCRIPTION"], re.I))]

# Rebuild progress = max across all fire cases
rebuild_progress_num = max(
    (c["REBUILD_PROGRESS_NUM"] for c in fire_cases if c["REBUILD_PROGRESS_NUM"]),
    default=None
)

# Primary permit = PermitManagement case with highest REBUILD_PROGRESS_NUM
permit_cases = [c for c in fire_cases
                if c["MODULENAME"] == "PermitManagement"
                and c["WORKCLASS_NAME"] in ("New", "Rebuild Project")]
primary_permit = max(permit_cases, key=lambda c: c["REBUILD_PROGRESS_NUM"] or 0, default=None)
```

---

## Expected QA parcel values

These are ground-truth values for the three initial QA parcels, validated against live data at plan-writing time.

### 5841009012 — 411 Punahou St
- Pre-fire: SFR × 1, 1136 sqft. No ADU. No MFR. DAMAGE: Destroyed.
- Post-fire: SFR × 1 (1115 sf), SB-9 unit × 1 (1107 sf), ADU × 2 (1110 sf each)
- `lfl_claimed = None` (PROJECT_NAME: "Eaton Rebuild @ 411 Punahou St")
- `sfr_size_comparison = "smaller"` (1115 < 1136)
- `adds_sb9 = True`, `added_adu_count = 2`
- `rebuild_progress_num = 4` (Building Plans Approved)

### 5842024014 — 3458 Monterosa Dr
- Pre-fire: SFR × 1, 3062 sqft. No ADU. No MFR. DAMAGE: Destroyed.
- Post-fire: SFR × 1 (3218 sf)
- `lfl_claimed = True` (PROJECT_NAME: "Like-for-Like SFR Rebuild @ 3458 Monterosa Dr")
- `sfr_size_comparison = "larger"` (3218 > 3062)
- `adds_sb9 = False`, `added_adu_count = 0`
- `rebuild_progress_num = 7` (Construction Completed — max of permit=7, plan=2)

### 5842022003 — 3245 Arrowhead Ct
- Pre-fire: SFR × 1, 2012 sqft. No ADU. No MFR. DAMAGE: Destroyed.
- Post-fire: SFR × 1 (2140 sf)
- `lfl_claimed = True` (PROJECT_NAME: "Like-for-Like SFR Rebuild @ 3245 Arrowhead Ct")
- `sfr_size_comparison = "larger"` (2140 > 2012)
- `adds_sb9 = False`, `added_adu_count = 0`
- `rebuild_progress_num = 6` (Rebuild In Construction — max of plan=2, permit=6)

---

## File layout

```
pipeline/
  pyproject.toml
  PLAN.md
  src/after_eaton/
    __init__.py
    cli.py                        # entrypoint: run()
    sources/
      __init__.py
      arcgis.py                   # paginated ArcGIS fetcher, retry logic
      dins.py                     # fetch_dins_parcels() → list[dict]
      epicla.py                   # fetch_epicla_cases() → list[dict]
      schemas.py                  # TypedDicts + validate() for both sources
    processing/
      __init__.py
      normalize.py                # DamageLevel enum, RebuildProgress enum
      join.py                     # join_cases_to_parcels() → list[JoinedParcel]
      parcel_analysis.py          # analyze_parcel() → ParcelResult
      description_parser.py       # parse_description() → list[ParsedStructure]
      aggregate.py                # aggregate_burn_area() → SummaryResult
    qc/
      __init__.py
      per_record.py               # per-ParcelResult warnings
      aggregate.py                # dataset-level threshold checks (hard fail)
      report.py                   # formats pass/fail summary to stdout + JSON log
    outputs/
      __init__.py
      geojson_writer.py           # write_parcels_geojson()
      summary_writer.py           # write_summary_json()
  tests/
    conftest.py                   # QA fixture loader
    fixtures/
      qa/
        5841009012.json           # hand-verified DINS + EPIC-LA + expected values
        5842024014.json
        5842022003.json
        ...                       # grows to dozens over time
    scripts/
      fetch_fixtures.py           # local dev only: downloads live data for offline runs
    test_description_parser.py    # unit tests for parse_description()
    test_parcel_analysis.py       # regression tests against all qa/ fixtures
    test_aggregate.py             # aggregate math tests
```

No full-dataset fixtures are committed to the repo. The full dataset is fetched fresh by CI each pipeline run.

---

## pyproject.toml dependencies

```toml
[project]
name = "after-eaton"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "tenacity>=9.0",
    "shapely>=2.0",
    "pygeojson>=3.1",
    "click>=8.1",
]

[project.scripts]
after-eaton = "after_eaton.cli:run"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-httpx>=0.32", "ruff>=0.4", "mypy>=1.10"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.mypy]
strict = true
```

---

## Module responsibilities & key signatures

### `sources/arcgis.py`
```python
def fetch_all(url: str, params: dict[str, str], *, max_retries: int = 3) -> list[dict[str, Any]]:
    """Paginate a FeatureServer query endpoint. Returns raw feature attributes list."""
```
Retry schedule: 30s / 120s / 480s via `tenacity.wait_exponential`. Drops features with null geometry (logs each). Raises `SourceError` if all retries exhausted.

### `sources/schemas.py`
```python
class DinsParcel(TypedDict): ...
class EpicCase(TypedDict): ...        # Note: EpicCase, not EpiclCase

def validate_dins(records: list[dict[str, Any]]) -> list[DinsParcel]: ...
def validate_epicla(records: list[dict[str, Any]]) -> list[EpicCase]: ...
```
Minimum required DINS fields: `AIN_1`, `DAMAGE_1`, `SQFTmain1`, `DesignType1`, `COMMUNITY`.
Minimum required EPIC-LA fields: `MAIN_AIN`, `MODULENAME`, `REBUILD_PROGRESS_NUM`, `DESCRIPTION`.
Raises `SchemaError` (with offending field name) on type mismatch or missing required field.

### `processing/normalize.py`
```python
class DamageLevel(str, Enum):
    NO_DAMAGE = "no_damage"
    NO_DATA   = "no_data"
    AFFECTED  = "affected"    # 1-9%
    MINOR     = "minor"       # 10-25%
    MAJOR     = "major"       # 26-50%
    DESTROYED = "destroyed"   # >50%

RAW_TO_DAMAGE: dict[str | None, DamageLevel] = {
    "No Damage":        DamageLevel.NO_DAMAGE,
    "No Data/Vacant":   DamageLevel.NO_DATA,
    "Affected (1-9%)":  DamageLevel.AFFECTED,
    "Minor (10-25%)":   DamageLevel.MINOR,
    "Major (26-50%)":   DamageLevel.MAJOR,
    "Destroyed (>50%)": DamageLevel.DESTROYED,
    None:               DamageLevel.NO_DATA,
}
```

### `processing/description_parser.py`
```python
@dataclass
class ParsedStructure:
    sqft: float | None
    struct_type: Literal["sfr", "adu", "jadu", "sb9", "mfr", "garage", "unknown"]
    raw_segment: str

def parse_description(description: str | None) -> list[ParsedStructure]: ...
def extract_lfl_claim(project_name: str | None) -> bool | None: ...
```

### `processing/join.py`
```python
@dataclass
class JoinedParcel:
    din: DinsParcel
    cases: list[EpicCase]    # all fire-related cases for this APN

def join_cases_to_parcels(
    parcels: list[DinsParcel],
    cases: list[EpicCase],
) -> list[JoinedParcel]:
    """Group cases by MAIN_AIN, left-join to parcels. Log APNs with no matching cases."""
```

### `processing/parcel_analysis.py`
```python
@dataclass
class ParcelResult:
    ain: str
    apn: str
    address: str
    damage: DamageLevel
    # Pre-fire (from DINS)
    pre_sfr_count: int
    pre_sfr_sqft: int | None
    pre_adu_count: int
    pre_adu_sqft: int | None
    pre_mfr_count: int
    pre_mfr_sqft: int | None
    # Post-fire (from EPIC-LA)
    post_sfr_count: int | None       # None = no permits yet
    post_sfr_sqft: int | None
    post_adu_count: int | None
    post_adu_sqft: int | None
    post_mfr_count: int | None
    post_mfr_sqft: int | None
    post_sb9_count: int | None
    post_sb9_sqft: int | None
    # Rebuild characterization
    lfl_claimed: bool | None         # from PROJECT_NAME
    sfr_size_comparison: Literal["smaller", "identical", "larger"] | None
    adds_sb9: bool
    added_adu_count: int
    # Progress
    rebuild_progress_num: int | None
    rebuild_progress: str | None
    # Pass-through DINS fields
    permit_status: str | None
    roe_status: str | None
    debris_cleared: str | None
    dins_count: int

def analyze_parcel(joined: JoinedParcel) -> ParcelResult: ...
```
`sfr_size_comparison`: only computed when both `post_sfr_sqft` and `pre_sfr_sqft` are non-null. Tolerance ±10 sqft for "identical".

### `processing/aggregate.py`
```python
@dataclass
class SummaryResult:
    generated_at: str           # ISO 8601
    total_parcels: int
    damaged_parcels: int
    destroyed_parcels: int
    no_permit_count: int
    permit_in_review_count: int
    permit_issued_count: int
    construction_count: int
    completed_count: int
    lfl_count: int
    nlfl_count: int
    lfl_unknown_count: int
    sfr_larger_count: int
    sfr_identical_count: int
    sfr_smaller_count: int
    sb9_count: int
    added_adu_count: int        # parcels that added ≥1 ADU

def aggregate_burn_area(parcels: list[ParcelResult], generated_at: str) -> SummaryResult: ...
```

---

## QC module

QC runs after analyze, before any output is written. A hard failure aborts the run and produces no release.

### `qc/per_record.py`
Collects named warnings (does not immediately abort) for each `ParcelResult`:
- `damage == DESTROYED` and no EPIC-LA cases found
- `post_sfr_sqft` parsed but < 200 sf or > 20,000 sf
- `parse_description` returned all-`unknown` on a permit with `NEW_DWELLING_UNITS > 0`
- `sfr_size_comparison` is non-null but `lfl_claimed is None`

### `qc/aggregate.py`
Hard-fails the pipeline if any threshold is breached:

| Check | Threshold |
|---|---|
| Description parse success rate (fire-related PermitManagement with non-null DESCRIPTION) | ≥ 90% |
| SFR sqft extraction rate (`STAT_CLASS == "New SFR not a tract"`) | ≥ 85% |
| Per-record warning rate | ≤ 5% of total parcels |
| Parcels with `rebuild_progress_num == 7` | ≥ 1 (sanity check against empty/stale data) |

Thresholds are named constants at the top of the file, easy to tighten over time.

### `qc/report.py`
Formats the full `QcReport` to stdout and writes a `qc_report.json` alongside the other outputs. Failed records are logged individually (AIN + warning type), not just counted.

---

## CI pipeline stage order (`pipeline.yml`)

```
fetch DINS → fetch EPIC-LA
  → validate schemas
  → join + analyze
  → QC: per-record warnings
  → QC: aggregate thresholds  ← failure aborts here; no release published
  → aggregate (summary.json)
  → write outputs
  → publish release
```

---

## Test structure

### `tests/fixtures/qa/<AIN>.json` format
```json
{
  "ain": "5841009012",
  "dins": { ... },
  "epic_cases": [ ... ],
  "expected": {
    "pre_sfr_sqft": 1136,
    "adds_sb9": true,
    "post_sfr_sqft": 1115,
    "added_adu_count": 2,
    "rebuild_progress_num": 4,
    "lfl_claimed": null,
    "sfr_size_comparison": "smaller"
  }
}
```

### `tests/test_parcel_analysis.py`
Loads all files under `tests/fixtures/qa/` automatically. Adding a new validated parcel requires only dropping a JSON file — no code change.

### `tests/test_description_parser.py`
Fast unit tests against inline strings (no fixtures):
- Numbered multi-structure description → 4 structures (sfr×1, sb9×1, adu×2) with correct sqft
- Simple single-structure SFR → correct sqft and type
- LFL/NLFL/unknown variants of PROJECT_NAME

### `tests/scripts/fetch_fixtures.py`
Local dev only. Downloads the full live dataset to a local cache so coverage-style tests can be run offline without hitting APIs on every iteration. Not invoked by CI.

---

## Build order

1. `pyproject.toml` + package skeleton (`__init__.py` files)
2. `sources/arcgis.py` — pagination + retry
3. `sources/schemas.py` + `processing/normalize.py` — types and enums
4. `sources/dins.py` + `sources/epicla.py` — thin wrappers over arcgis.py
5. Record QA fixtures — fetch the 3 QA APNs from live data, save to `tests/fixtures/qa/`
6. `processing/description_parser.py` — write tests first, then implementation
7. `processing/join.py`
8. `processing/parcel_analysis.py` — write QA regression tests first, then implementation
9. `processing/aggregate.py`
10. `qc/` — per_record, aggregate, report
11. `outputs/geojson_writer.py` + `outputs/summary_writer.py`
12. `cli.py` — wire everything together
13. Run end-to-end locally, validate QA parcel output against expected values
14. Iterate until QC reaches defined minimum thresholds