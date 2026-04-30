# Architecture

For project overview and data source descriptions, see [README.md](./README.md). For end-to-end analytical methodology — what every output field means and how it was computed — see [METHODOLOGY.md](./METHODOLOGY.md). This document covers internal architecture and is the primary reference for code changes.

## High-level architecture

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│  ArcGIS Feature Servers      │         │                              │
│  - EPIC-LA Fire Recovery     │         │   GitHub Pages (Fastly CDN)  │
│  - 2025 Parcels w/ DINS data │         │   serves Vue + Vite SPA      │
└──────────────┬───────────────┘         │                              │
               │ HTTPS (no auth)         └──────────────▲───────────────┘
               │ FeatureServer query                    │ HTTPS fetch()
               ▼                                        │
┌──────────────────────────────┐                        │
│  GitHub Actions: pipeline.yml│                        │
│  weekdays @ noon Pacific     │                        │
│  (workflow_dispatch allowed) │                        │
│                              │                        │
│  Python 3.11+                │                        │
│   fetch → join → analyze     │                        │
│   → QC → aggregate → write   │                        │
└──────────────┬───────────────┘                        │
               │ gh release upload --clobber            │
               ▼                                        │
┌────────────────────────────────────────────┐          │
│  GitHub Releases                           │──────────┘
│  - data-YYYY-MM-DD (history)               │
│  - data-latest (rolling)                   │
│  Assets:                                   │
│    parcels.geojson                         │
│    summary.json                            │
│    qc-report.json                          │
│    2020-census-tracts.geojson              │
│    2020-census-block-groups.geojson        │
│    source-dins.json                        │
│    source-epicla.json                      │
│    source-fire-perimeter.json              │
│    source-2020-census-tracts.json          │
│    source-2020-census-block-groups.json    │
│    llm-extraction-cache.json               │
└────────────────────────────────────────────┘
```

The site is fully static. There is no backend, no database, and no user state. The frontend fetches data files at runtime from the rolling `data-latest` Release tag.

## Repository layout

```
.
├── .github/
│   └── workflows/
│       ├── pipeline.yml          # scheduled data pipeline
│       └── deploy.yml            # frontend build + Pages deploy
├── pipeline/                     # Python data processing
│   ├── pyproject.toml
│   ├── src/after_eaton/
│   │   ├── cli.py                # click entrypoint, wires the run
│   │   ├── sources/              # ArcGIS fetchers + typed schemas
│   │   ├── processing/           # join, normalize, parse, analyze, aggregate
│   │   ├── qc/                   # per-record warnings + threshold gates
│   │   └── outputs/              # GeoJSON / JSON writers
│   └── tests/
│       ├── conftest.py           # auto-discovers QA fixtures
│       ├── fixtures/qa/*.json    # hand-verified per-parcel regression cases
│       └── test_*.py             # unit + integration tests
├── web/                          # Vue 3 + Vite SPA
├── data/                         # local pipeline output (gitignored)
├── ARCHITECTURE.md               # this file
├── METHODOLOGY.md                # analytical methodology, attribute-level docs
├── README.md
└── LICENSE
```

The pipeline and frontend are decoupled. The pipeline writes to `data/` locally and to a GitHub Release in CI. The frontend fetches from those Release URLs at runtime and never imports from `pipeline/`.

## Data pipeline

The pipeline is a single Python package, `after_eaton`, exposing one CLI entrypoint (`after-eaton`). A run executes this pipeline in order; if any step fails, no release is published.

```
fetch DINS                    → sources/dins.py
fetch EPIC-LA                 → sources/epicla.py
fetch fire perimeter          → sources/fire_perimeter.py
fetch census tracts/BGs       → sources/census.py        (perimeter-envelope filter)
   → write raw snapshots to data/
validate schemas              → sources/schemas.py        (raises SchemaError)
join cases to parcels by AIN  → processing/join.py
analyze each parcel           → processing/parcel_analysis.py
   ├─ pre-fire from DINS slots
   ├─ post-fire (regex)        from EPIC-LA primary permit
   │     parse DESCRIPTION   → processing/description_parser.py
   ├─ post-fire (LLM, default) all qualifying plan + permit records
   │     extract structures  → processing/llm_extraction.py
   │     compare vs regex    → processing/extraction_compare.py
   ├─ resolve LFL signals     → processing/parcel_analysis.py:_resolve_lfl
   └─ normalize damage / BSD  → processing/normalize.py
spatial assignment            → processing/spatial_aggregate.py
   (parcel centroid → tract / block group; reused for QC + GeoJSON output)
QC:
   ├─ per-record warnings     → qc/per_record.py          (collected, not fatal)
   └─ aggregate thresholds    → qc/aggregate.py           (raise QcFailedError)
write qc-report.json
aggregate to burn-area totals → processing/aggregate.py
write summary.json
write parcels.geojson
write 2020-census-tracts.geojson, 2020-census-block-groups.geojson
```

For the analytical contract — what each derived field *means* — see [METHODOLOGY.md](./METHODOLOGY.md). This file describes the *shape* of the code.

### Module responsibilities

| Module | Responsibility | Key types/functions |
|---|---|---|
| `sources/arcgis.py` | Paginated FeatureServer fetcher with retry. Drops null-geometry features. | `fetch_all()`, `SourceError` |
| `sources/dins.py` | Thin wrapper: pulls `COMMUNITY = 'Altadena'` from the DINS layer. | `fetch_dins_parcels()` |
| `sources/epicla.py` | Thin wrapper: pulls `DISASTER_TYPE = 'Eaton Fire (01-2025)'` from EPIC-LA layer 0. | `fetch_epicla_cases()` |
| `sources/fire_perimeter.py` | Thin wrapper: pulls every feature from the Eaton Fire Perimeter layer. | `fetch_fire_perimeter()` |
| `sources/census.py` | Pulls 2020 census tracts (layer 14) intersecting the fire-perimeter envelope, then pulls every block group (layer 15) whose parent CT20 is in that tract set so block groups exactly partition the tracts. | `fetch_census_tracts()`, `fetch_census_block_groups()` |
| `sources/schemas.py` | TypedDict definitions and `validate_*` functions. Required-field type checks; raises `SchemaError` (with `field=`) on drift. | `DinsParcel`, `EpicCase`, `FirePerimeter`, `CensusTract`, `CensusBlockGroup`, `validate_dins`, `validate_epicla`, `validate_fire_perimeter`, `validate_census_tracts`, `validate_census_block_groups` |
| `processing/normalize.py` | Damage and BSD enums + raw→canonical maps. Rebuild-progress label table. | `DamageLevel`, `BsdStatus`, `normalize_damage`, `normalize_bsd`, `rebuild_progress_label` |
| `processing/description_parser.py` | EPIC-LA free-text parser: splits a DESCRIPTION into structures, classifies each as `sfr`/`adu`/`jadu`/`mfr`/`garage`/`temporary_housing`/`repair`/`retaining_wall`/`seismic`/`unknown`, extracts sqft. Bare-SB9 segments classify as `sfr` via fallback. Also extracts LFL/Custom claim from PROJECT_NAME or DESCRIPTION, and exposes `mentions_sb9()` for parcel-level SB-9 detection. | `parse_description()`, `extract_lfl_claim()`, `mentions_sb9()`, `ParsedStructure`, `RESIDENTIAL_TYPES` |
| `processing/join.py` | Group cases by `MAIN_AIN`, left-join to DINS parcels. Logs unmatched AINs. | `join_cases_to_parcels()`, `JoinedParcel` |
| `processing/parcel_analysis.py` | Per-parcel synthesis. Reads DINS structure slots for pre-fire; selects primary permit for regex post-fire; selects qualifying records (plans + permits) for LLM input; runs LFL resolution; computes size comparison, SB-9 pathway flag (text scan over DESCRIPTION/PROJECT_NAME/PROJECTNAME), and ADU deltas. | `analyze_parcel()`, `ParcelResult`, `_resolve_lfl()`, `_select_primary_permit()`, `select_qualifying_records()`, `_detect_sb9()`, `pre_fire_summary()` |
| `processing/llm_provider.py` | OpenRouter chat-completions client (OpenAI-compatible endpoint, `temperature=0`, retry on transient HTTP errors). The cache key includes `model_id` so swapping models invalidates the cache cleanly. | `OpenRouterProvider`, `LLMResponse`, `LLMError` |
| `processing/llm_prompts.py` | System + user prompt templates and `parcel_cache_key()` (deterministic SHA-256 over sorted record content + provider + model + prompt version). Bump `PROMPT_VERSION` when the prompt changes meaningfully. | `SYSTEM_PROMPT`, `PROMPT_VERSION`, `ParcelContext`, `render_user_prompt()`, `parcel_cache_key()` |
| `processing/llm_extraction.py` | Per-parcel `extract_structures()` (cache-or-call, fallback on invalid JSON / fenced output) plus cache load/save (single JSON file under `data/llm-extraction-cache.json`) and `prune_cache()`. | `LLMExtraction`, `ExtractedStructure`, `ExtractionCache`, `extract_structures()`, `load_cache()`, `save_cache()`, `prune_cache()` |
| `processing/extraction_compare.py` | Bucket LLM structures into the regex `PostFire` shape, compare per type, emit `ComparisonIssue`s, and `override_with_llm()` to apply LLM result to a `ParcelResult`. `extraction_metrics()` produces the `extraction_comparison` block in `qc-report.json`. | `derive_post_from_llm()`, `compare_extractions()`, `override_with_llm()`, `extraction_metrics()`, `ExtractionRunInfo` |
| `processing/aggregate.py` | Roll `ParcelResult` list into `SummaryResult` (counts only, no per-parcel detail). The shared `count_parcels()` helper produces the same counting set used by per-tract / per-block-group aggregation. | `aggregate_burn_area()`, `count_parcels()`, `SummaryResult`, `RegionCounts` |
| `processing/spatial_aggregate.py` | Assign each parcel to one tract and one block group by polygon-centroid containment (shapely STRtree); roll up per-region counts. | `aggregate_by_region()`, `RegionFeature`, `SpatialAggregation` |
| `qc/per_record.py` | Per-parcel data-quality warnings. Each warning carries a `severity` of `data` (counts toward threshold) or `info` (real-world ambiguity, surfaced but doesn't gate the run). | `check_record()`, `RecordWarning` |
| `qc/aggregate.py` | Four hard-fail dataset-level checks. Constants at top of file are tunable. | `check_thresholds()`, `ThresholdCheck`, `QcFailedError` |
| `qc/report.py` | Formats and writes `qc-report.json`; pretty-prints to stdout. | `QcReport`, `print_report`, `write_report`, `enforce` |
| `outputs/geojson_writer.py` | Per-feature GeoJSON output. Converts ArcGIS rings to GeoJSON Polygon/MultiPolygon (`esri_to_geojson` is reused by the region writer). | `write_parcels_geojson()`, `esri_to_geojson()` |
| `outputs/region_writer.py` | FeatureCollection writer for tract / block-group GeoJSONs. | `write_regions_geojson()` |
| `outputs/summary_writer.py` | Dump `SummaryResult` as JSON. | `write_summary_json()` |
| `outputs/raw_writer.py` | Snapshot raw fetched records to disk for reproducibility. | `write_raw_records()` |
| `outputs/csv_writer.py` | Per-parcel CSV (`parcels.csv`): every `ParcelResult` field, no geometry, end-user friendly. | `write_parcels_csv()` |
| `cli.py` | Click entrypoint; one `run()` command with `--out-dir`, `--log-level`, and LLM-extraction flags (`--llm-extraction`, `--llm-provider`, `--llm-model`, `--llm-cache-path`). Loads `.env` for local development. | `run()` |

### Sources

Both sources are public ArcGIS Feature Servers (no auth, CORS-permissive). URLs are constants in `sources/dins.py` and `sources/epicla.py`. Pull strategy:

- FeatureServer query API with `f=json`, `outSR=4326`, `returnGeometry=true`, `where=<source-specific filter>`.
- Paginated via `resultOffset` / `resultRecordCount` (page size 1000). Page until `exceededTransferLimit` is false.
- Per-page request timeout 60 s. Up to 3 retries on `httpx.HTTPError` or transient ArcGIS errors (5xx / 504 / 429), with exponential back-off `30 s → 120 s → 480 s` (`tenacity.wait_exponential(multiplier=30, exp_base=4, min=30, max=480)`).

Known quirks handled defensively:

- ArcGIS occasionally returns features with `null` geometry — dropped at the fetcher with a per-feature warning log.
- DINS damage classifications use specific strings — normalized via `RAW_TO_DAMAGE` in `processing/normalize.py`.
- Source field names and types may drift between releases — `sources/schemas.py:validate_*` raises `SchemaError(field=...)` and the run aborts.

### QC gates

Hard-fail thresholds live as constants at the top of `qc/aggregate.py`:

| Constant | Default | Meaning |
|---|---|---|
| `DESCRIPTION_PARSE_MIN_RATE` | 0.90 | Of fire-related PermitManagement cases with non-null DESCRIPTION, fraction the parser classifies to a known type or extracts a sqft from. |
| `SFR_SQFT_EXTRACTION_MIN_RATE` | 0.85 | Of permits whose DESCRIPTION mentions an SFR keyword and a numeric sqft, fraction the parser classifies as `sfr` with a sqft. |
| `WARNING_RATE_MAX` | 0.05 | Maximum fraction of parcels allowed to raise a `data`-severity per-record warning (`info` warnings excluded). |
| `MIN_COMPLETED_REBUILDS` | 1 | Sanity check against an empty/stale dataset. |

In addition, two spatial-aggregation invariants run as hard-fail equality checks (no tunable threshold — they must be 0):

| Threshold | Pass condition | Meaning |
|---|---|---|
| `tract_total_matches_summary` | `sum(tract.total_parcels) + len(unassigned_ains) == burn-area total` | Catches double-assignment or dropped parcels in the centroid pass. |
| `tract_partitions_into_block_groups` | for every tract: `tract.total_parcels == sum(its block-groups' total_parcels)` | Catches drift between the two LA County census layers, or a parcel landing in a tract but not in any of its block groups (boundary mismatch). |

The candidate-set predicates in `qc/aggregate.py` are deliberately defined with regexes independent of the parser — a parser regression cannot shrink the denominator and silently mask itself.

Per-record warning severities:

- **`data`** — flags a parser/source bug worth fixing. Counts toward `warning_rate`.
- **`info`** — flags real-world ambiguity (e.g. a destroyed parcel that hasn't filed a permit yet). Surfaced in `qc-report.json` but excluded from the threshold.

### Outputs

All outputs are written to `data/` locally and uploaded as Release assets in CI:

| File | Format | Contents |
|---|---|---|
| `parcels.geojson` | GeoJSON FeatureCollection | One feature per Altadena parcel; attributes per `ParcelResult`. See METHODOLOGY.md for field-by-field semantics. |
| `parcels.csv` | CSV | Same per-parcel attributes, no geometry. End-user-friendly download surfaced in the site footer. |
| `summary.json` | JSON object | Burn-area totals (counts). |
| `qc-report.json` | JSON object | Pass/fail of every threshold + every per-record warning that fired. |
| `2020-census-tracts.geojson` | GeoJSON FeatureCollection | One feature per 2020 census tract intersecting the perimeter; attributes are identifiers (`ct20`, `label`) plus every `RegionCounts` field. |
| `2020-census-block-groups.geojson` | GeoJSON FeatureCollection | One feature per 2020 census block group intersecting the perimeter; attributes are identifiers (`bg20`, `ct20`, `label`) plus every `RegionCounts` field. |
| `source-dins.json` | JSON object | Raw fetched DINS records (`{source, fetched_at, record_count, records}`). |
| `source-epicla.json` | JSON object | Raw fetched EPIC-LA records (same envelope). |
| `source-fire-perimeter.json` | JSON object | Raw Eaton Fire perimeter polygon(s) (same envelope). |
| `source-2020-census-tracts.json` | JSON object | Raw 2020 census tract polygons within the perimeter envelope (same envelope). |
| `source-2020-census-block-groups.json` | JSON object | Raw 2020 census block group polygons within the perimeter envelope (same envelope). |
| `llm-extraction-cache.json` | JSON object | Per-parcel LLM extractions keyed deterministically on record content + provider + model + prompt version. Restored at the start of the next CI run so steady-state pipeline cost is bounded by the daily delta of changed records. |

Every output carries a `generated_at` ISO 8601 timestamp:
- `summary.json`, `qc-report.json`, `source-dins.json`, `source-epicla.json`, `source-fire-perimeter.json`, `source-2020-census-tracts.json`, `source-2020-census-block-groups.json`: top-level field (`fetched_at` on raw source files)
- `parcels.geojson`, `2020-census-tracts.geojson`, `2020-census-block-groups.geojson`: `metadata.generated_at` on the FeatureCollection

### Schedule

```yaml
# .github/workflows/pipeline.yml
on:
  schedule:
    - cron: '0 20 * * 1-5'   # 13:00 PT during PDT, 12:00 PT during PST
  workflow_dispatch: {}
```

Notes:

- GitHub Actions cron is in UTC. `0 20 * * 1-5` lands at 1 PM Pacific during PDT (mid-March through early November). During PST the run shifts to noon PT. We accept the one-hour seasonal drift rather than maintaining two cron entries.
- `workflow_dispatch` is always allowed and produces a release tagged with the run date.
- GitHub auto-disables scheduled workflows in repos with no commits for 60 days. Each successful run pushes a release, which keeps the schedule alive.
- Scheduled runs can be delayed several minutes under GitHub load — fine for daily cadence.

### Failure modes

- **Source unavailable or 5xx:** retry with exponential back-off (3 attempts: 30 s / 120 s / 480 s). If still failing, the fetcher raises `SourceError`, the workflow fails, and **no** partial release is published.
- **Schema drift:** `validate_dins` / `validate_epicla` raises `SchemaError` naming the offending field. The workflow fails before any processing.
- **Empty result:** zero rows from either source aborts the run with exit code 2.
- **QC threshold breach:** the aggregate-threshold check raises `QcFailedError` and the workflow exits with code 3 *after* writing `qc-report.json` (so the failure is auditable). Outputs `summary.json` / `parcels.geojson` are not written and no release is uploaded.
- **Geometry issues:** individual features with `null` geometry are dropped and logged. There is currently no >1% drop-rate gate (TODO).

On any non-zero exit, `pipeline.yml` uploads the `data/` directory as a workflow artifact named `pipeline-outputs` so partial outputs — notably `qc-report.json` and the raw source snapshots — remain downloadable from the failed run. The job also runs under a `pipeline` concurrency group with `cancel-in-progress: false`, so a manual `workflow_dispatch` overlapping the scheduled run will queue rather than race on the same release.

## Release strategy

Each successful pipeline run does two things:

1. Creates the dated release `data-YYYY-MM-DD` (date in `America/Los_Angeles`) and attaches all five output files. Same-day re-runs update the existing release via `gh release upload <tag> <files> --clobber` rather than failing.
2. Updates the rolling `data-latest` tag to the same assets via `gh release upload data-latest <files> --clobber`.

The dated releases are the historical record; `data-latest` is the stable URL the frontend depends on. Future releases may allow loading historical data.

**Public URLs of the canonical data assets:**

```
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/parcels.geojson
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/parcels.csv
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/summary.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/qc-report.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/2020-census-tracts.geojson
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/2020-census-block-groups.geojson
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/source-dins.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/source-epicla.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/source-fire-perimeter.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/source-2020-census-tracts.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/source-2020-census-block-groups.json
```

We use the explicit `data-latest` tag rather than `/releases/latest/download/` because `latest` resolves by GitHub's own ordering rules (most recent non-prerelease) and could behave unexpectedly when a dated release and the rolling tag are both updated in the same run.

The frontend does **not** fetch these URLs directly at runtime. The deploy workflow downloads `summary.json`, `qc-report.json`, and `parcels.csv` into `web/public/data/` at build time so the published site serves them same-origin from GitHub Pages — no CORS surface, no third-party runtime dependency. Because data is baked into the deploy, every successful pipeline run triggers a fresh deploy via the `workflow_run` event (see `.github/workflows/deploy.yml`).

Retention: keep all dated releases indefinitely. They are small and provide an audit trail of how rebuild progress changed over time.

## Frontend

Vue 3 + Vite + TypeScript, built as a static SPA and served from GitHub Pages.

### Routes

Hash-mode routing (`#/...`) sidesteps the GitHub Pages SPA-404 issue.

- `#/` — homepage dashboard with four stats: Relative Size, Like-for-Like, Accessory Dwellings, SB-9. Each stat carries an info button explaining its methodology.
- `#/methodology` — renders `METHODOLOGY.md` inline (`markdown-it` + `markdown-it-anchor`) with a sticky table of contents.
- `#/quality-control` — pass/fail thresholds table plus the full per-record warnings table from `qc-report.json`.

### Data loading

The site fetches `summary.json` and `qc-report.json` from same-origin (`./data/...` under the Pages base path) on app load:

- `useDataset()` is a module-scope composable so the fetch happens once and is shared across pages.
- Shows a loading state while data fetches.
- Shows a stale-data banner if the embedded `generated_at` is more than 96 hours old (formatted as "Data as of Mon Apr 27, 2026 PDT/PST" in the footer pill).
- On fetch failure, renders a clear error state — in dev, the error includes a hint about running `npm run data:fetch-local` / `data:fetch-release`.

`parcels.csv` is exposed as a direct download link in the footer (`./data/parcels.csv`).

### Build and deploy

`.github/workflows/deploy.yml` deploys `web/dist/` to GitHub Pages via `actions/upload-pages-artifact` + `actions/deploy-pages`. Trigger conditions:

1. **Push to `main`** touching `web/**`, `.github/workflows/deploy.yml`, or `METHODOLOGY.md` — frontend / methodology code changes.
2. **Successful `pipeline` workflow run** (`workflow_run` event) — re-bake the bundled JSON / CSV after a data refresh.
3. **Manual `workflow_dispatch`**.

The build step runs `gh release download data-latest` to populate `web/public/data/` before `npm run build`, so the resulting `dist/` is self-contained — no third-party runtime fetches.

**One-time manual setup:** in repo Settings → Pages, set the source to "GitHub Actions". `vite.config.ts` sets `base: '/after-eaton/'` for the project-page URL.

## Local development

### Prerequisites

- Python 3.11+ (the pipeline targets 3.11 via `requires-python` in `pyproject.toml`)
- Node 20+ (for the frontend, when it exists)
- `gh` CLI (only needed for testing release uploads)
- `uv` recommended for venv/dep management; `pip` works too

### Pipeline

**Install (one-time):**

```bash
cd pipeline
uv venv --python 3.11
uv pip install -e ".[dev]"
```

This installs the `after-eaton` console script into the venv.

**Run end-to-end against live ArcGIS data:**

```bash
.venv/bin/after-eaton --out-dir ../data
```

Flags:
- `--out-dir DIR` (default `data`) — directory for outputs.
- `--log-level {DEBUG,INFO,WARNING,ERROR}` (default `INFO`).

Outputs land flat in `--out-dir`: `parcels.geojson`, `summary.json`, `qc-report.json`, `source-dins.json`, `source-epicla.json`. The `data/` directory is gitignored.

Exit codes:
- `0` — success, all QC thresholds passed.
- `2` — a source returned zero rows (refused to publish).
- `3` — one or more QC thresholds failed; `qc-report.json` is still written.
- non-zero on schema drift, source failure after retries, etc.

**Quality gates** (all run in CI):

```bash
.venv/bin/ruff format src/ tests/      # auto-format
.venv/bin/ruff check  src/ tests/      # lint (E, F, I, UP rules)
.venv/bin/mypy --strict src/           # type check
.venv/bin/pytest                       # all tests
.venv/bin/pytest tests/test_foo.py     # one file
```

**Tuning thresholds:** edit the constants at the top of `pipeline/src/after_eaton/qc/aggregate.py` (`DESCRIPTION_PARSE_MIN_RATE`, etc.). The names are stable for ops review.

### Frontend

**Install (one-time):**

```bash
cd web
npm install
```

**Run locally:**

```bash
npm run data:fetch-local      # copies ../data/*.json + parcels.csv → public/data/
# or: npm run data:fetch-release   # mirrors what CI does, via the gh CLI
npm run dev
```

`web/public/data/` is gitignored. If it's empty, the SPA shows the error state with a hint to run one of the data-fetch scripts. `scripts/copy-methodology.mjs` runs from `predev`/`prebuild` to copy `../METHODOLOGY.md` into `src/assets/methodology.md` (also gitignored), where it's imported via Vite's `?raw` loader.

**Quality gates:**

```bash
npm run build              # vue-tsc + vite build (production)
npx prettier --check .
npx eslint .
```

## Testing

Test layout:

```
tests/
├── conftest.py                    # parametrizes qa_fixture from fixtures/qa/*.json
├── fixtures/
│   └── qa/                        # one JSON per hand-verified parcel; auto-discovered
│       ├── 5829015008.json
│       ├── 5841009012.json
│       ├── 5842022003.json
│       └── 5842024014.json
├── test_aggregate.py              # SummaryResult math (synthetic ParcelResults)
├── test_description_parser.py     # parser regex/tier/sqft tests on inline strings
├── test_lfl_resolution.py         # _resolve_lfl precedence + recency rules
└── test_parcel_analysis.py        # end-to-end on QA fixtures
```

**Three layers:**

1. **Unit tests** (`test_description_parser.py`, `test_aggregate.py`, `test_lfl_resolution.py`) — fast, in-memory, no fixtures. Cover parser regex edge cases, aggregate counting, and LFL precedence rules.
2. **QA regression tests** (`test_parcel_analysis.py`) — load every JSON file under `tests/fixtures/qa/` and assert `analyze_parcel()` produces the values listed under `expected`. Each fixture file becomes one parametrized test case automatically — adding a new validated parcel requires only dropping a JSON file, no code change.
3. **End-to-end smoke** — running `after-eaton` against live ArcGIS produces the canonical outputs. Not yet automated in CI; today it's an interactive check before merge.

**QA fixture format:**

```json
{
  "ain": "5841009012",
  "_note": "optional human-readable note about edge cases or known issues",
  "dins": { ... raw DINS feature attributes + _geometry ... },
  "epic_cases": [ { ... raw EPIC-LA case attributes + _geometry ... }, ... ],
  "expected": {
    "pre_sfr_sqft": 1136,
    "post_sfr_sqft": 2222,
    "adds_sb9": true,
    "added_adu_count": 2,
    "rebuild_progress_num": 4,
    "lfl_claimed": null,
    "sfr_size_comparison": "larger"
  }
}
```

Fixtures are sourced from real live records (originally fetched at plan-writing time). They are stable inputs — when the live API changes, the fixture continues to encode the historical state we hand-verified, not whatever ArcGIS is serving today.

## Conventions

- **Python:** formatted with `ruff format`, linted with `ruff check` (rules E, F, I, UP). Type-checked with `mypy --strict` on `pipeline/src/`.
- **JS/TS:** formatted with `prettier`, linted with `eslint`. TypeScript `strict` mode.
- **Commits:** conventional-commits-ish, not enforced. Prefixes: `feat:`, `fix:`, `chore:`, `data:`, `docs:`.
- **Branching:** trunk-based on `main`; PRs squash-merged.
- **Naming:** `snake_case` in Python, `camelCase` in TS, `kebab-case` for filenames in `web/` and for top-level output files (e.g. `qc-report.json`).

## Secrets and configuration

- `GITHUB_TOKEN` — automatically provided by Actions, sufficient for `gh release` operations on the same repo. No PAT needed.
- Both ArcGIS sources are public; no API keys.
- `OPENROUTER_API_KEY` — required for the LLM-based structure extractor. Set as a repo secret (`Settings → Secrets and variables → Actions`) for CI; for local development, place in `pipeline/.env` (gitignored). If missing, the pipeline falls back to regex-only extraction and emits an `llm_disabled` info-warning.
- Local development for regex-only extraction needs no secrets; pass `--no-llm-extraction` to skip the LLM pass entirely.

## Operational notes

### Known limitations

- GitHub Pages bandwidth soft cap: ~100 GB/month.
- Releases asset downloads are CDN-backed but not rate-limit-documented; we expect this site to remain well under any practical limit.
- No alerting on pipeline failure beyond GitHub's default notification to the workflow author. **TODO: add a webhook (Slack/Discord/email list) once the project has more contributors.**
- No `>1%` dropped-feature gate at the fetch layer (one is described in earlier plans but not yet implemented). Bad geometries are dropped silently except for an INFO log line.

### Manual operations

```bash
# Trigger a fresh pipeline run
gh workflow run pipeline.yml

# Roll back data-latest to a previous dated release
gh release download data-2026-04-26 --dir /tmp/rollback
gh release upload data-latest /tmp/rollback/* --clobber

# Re-deploy the frontend
gh workflow run deploy.yml
```

### Monitoring

- Watch the Actions tab for failed runs.
- The frontend's stale-data banner (when implemented) is the user-visible signal that the pipeline has stopped producing fresh output.
- `qc-report.json` is the audit log: every run captures both the threshold pass/fail state and the full list of per-record warnings, including conflicts the resolver had to break.

## Out of scope / non-goals

- **No user accounts or authentication.** The site is fully public and read-only.
- **No personally identifiable information.** Outputs are aggregated or parcel-level public records; no resident names, contact info, or anything sourced from non-public records.
- **No server-side runtime.** Static files plus client-side JavaScript only.
- **No runtime database.** All data lives in Release assets; the frontend treats them as the single source of truth.
- **No real-time data.** Daily-cadence updates are the contract.
- **No write paths.** No submissions, comments, or any user input beyond client-side filtering.

## Future work (not yet implemented)

- Altagether-zone aggregates (boundary source undecided). Census-tract and census-block-group aggregates ship as `2020-census-tracts.geojson` / `2020-census-block-groups.geojson` alongside the burn-area `summary.json`.
- Pipeline-failure webhook alerting.
- Geometry drop-rate gate.
