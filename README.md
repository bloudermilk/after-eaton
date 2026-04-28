# After Eaton

**After Eaton** is a living analysis of the impacts of the Eaton Fire of 2025 on the unincorporated town of Altadena. We use open data from LA County and other sources to compare rebuild efforts to the pre-fire state of the community. Our site is free and publicly accessible, and intended to be useful for community members, county agencies, and other stakeholders.

## Data sources

* [EPIC-LA Fire Recovery Cases](https://lacounty.maps.arcgis.com/home/item.html?id=e87c8fcf5a2c4f7e87198b0c208d3d9f) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/EPICLA_Eaton_Palisades/FeatureServer)) — building plans, permits, rebuild progress.
* [2025 Parcels with DINS data](https://data.lacounty.gov/datasets/lacounty::2025-parcels-with-dins-data/about) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/2025_Parcels_with_DINS_data/FeatureServer/5)) — pre-fire assessor parcel data and post-fire damage assessments.

Both feeds are public, no-auth ArcGIS Feature Servers maintained by LA County. Reference: [LA County Recovery Map](https://lacounty.maps.arcgis.com/apps/instant/portfolio/index.html?appid=b53bc2994933497ba2b2f04ceb67999d) and the [official 2025 Fire Rebuilding Metric Definitions PDF](https://file.lacounty.gov/SDSInter/lac/1184128_2025FireRebuildingMetricDefinitions.pdf).

## What we publish

The pipeline runs each weekday and uploads a fresh snapshot to a GitHub Release. The rolling `data-latest` tag points at the most recent snapshot; every dated release is preserved indefinitely as an audit trail.

| File | Contents |
|---|---|
| `parcels.geojson` | One feature per Altadena parcel with all derived fields. |
| `summary.json` | Burn-area-wide aggregate counts. |
| `qc-report.json` | QC threshold pass/fail and per-parcel warnings. |
| `source-dins.json` | Snapshot of raw fetched DINS records. |
| `source-epicla.json` | Snapshot of raw fetched EPIC-LA records. |

The raw source snapshots ship alongside our derived outputs so any number on the site is traceable back to its source row.

## Parcel analysis

For each parcel in the burn area we compute, among other things:

* Quantity and size of single-family residence(s), accessory dwelling unit(s), and multi-family residence(s) — both pre-fire (from DINS structure slots) and post-fire (from EPIC-LA permit descriptions).
* Whether the rebuild is **Like-for-Like** or **Custom** (the County's binary categorization).
* If Like-for-Like, whether the rebuilt SFR is `smaller`, `identical`, or `larger` than pre-fire (±10 sqft tolerance).
* Whether the rebuild adds a primary unit under California's **SB-9** lot-split / two-unit law.
* Whether the rebuild adds **ADUs** beyond what the parcel had pre-fire, and how many.
* Two damage signals side-by-side: **FIRESCOPE** %-loss bucket (DINS `DAMAGE_1`) and **Safety Assessment** tag (DINS `BSD_Tag`). Both are exposed because they answer different questions and disagree on ~200 parcels.
* Pass-through fields from each source: permit status, ROE status, debris-clearing status, rebuild progress.

We also flag parcels where the source data is internally inconsistent (e.g. the permit description says "Like-for-Like" but the project name says "Non-Like-for-Like") so reviewers can audit them.

For the full attribute-level definition of every output field, including the regexes used to parse permit descriptions and the precedence rules used to resolve conflicts, see [METHODOLOGY.md](./METHODOLOGY.md).

## Aggregate analysis

`summary.json` contains burn-area-wide totals. Per-tract, per-block, and Altagether-zone aggregates are planned but not yet implemented.

## Architecture

The pipeline is a Python package (`after_eaton`) with one CLI entrypoint. The frontend (a Vue 3 + Vite SPA, planned) will fetch the released data files at runtime — there is no backend, no database, no user state. The two halves are fully decoupled.

For internal architecture, module layout, retry/QC logic, and operational notes, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Development

**Prerequisites:** Python 3.11+, Node 20+ (for the frontend, when it exists). [`uv`](https://github.com/astral-sh/uv) is recommended for managing the Python venv.

**Pipeline (one-time setup):**

```bash
cd pipeline
uv venv --python 3.11
uv pip install -e ".[dev]"
```

**Run a fresh end-to-end pull against live ArcGIS:**

```bash
.venv/bin/after-eaton --out-dir ../data
```

Outputs land flat in `data/` (gitignored). The run takes ~30 seconds; expect ~50 MB of output, mostly the raw source snapshots.

**Quality gates:**

```bash
.venv/bin/ruff format src/ tests/
.venv/bin/ruff check  src/ tests/
.venv/bin/mypy --strict src/
.venv/bin/pytest
```

For deeper guidance on the pipeline's internals, conventions, and testing strategy, see [ARCHITECTURE.md](./ARCHITECTURE.md). For the analytical methodology — what each output field means and how it was derived — see [METHODOLOGY.md](./METHODOLOGY.md).

## License

MIT. See [LICENSE](./LICENSE).
