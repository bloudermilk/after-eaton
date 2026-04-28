# After Eaton

**After Eaton** is a living analysis of the impacts of the Eaton Fire of 2025 on the unincorporated town of Altadena. We use open data from LA County and other sources to compare rebuild efforts to the pre-fire state of the community. Our site is free and publicly accessible, and intended to be useful for community members, county agencies, and other stakeholders.

## Data sources

* [EPIC-LA Fire Recovery Cases](https://lacounty.maps.arcgis.com/home/item.html?id=e87c8fcf5a2c4f7e87198b0c208d3d9f) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/EPICLA_Eaton_Palisades/FeatureServer)) — building plans, permits, rebuild progress.
* [2025 Parcels with DINS data](https://data.lacounty.gov/datasets/lacounty::2025-parcels-with-dins-data/about) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/2025_Parcels_with_DINS_data/FeatureServer/5)) — pre-fire assessor parcel data and post-fire damage assessments.
* [Eaton Fire Perimeter](https://data.lacounty.gov/datasets/lacounty::eaton-fire-perimeter/about) ([API Service](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Eaton_Fire_Perimeter/FeatureServer/0))
* [2020 Census Tracts](https://data.lacounty.gov/datasets/lacounty::2020-census-tracts-4/about) ([API Service](https://public.gis.lacounty.gov/public/rest/services/LACounty_Dynamic/Demographics/MapServer/14))
* [2020 Census Block Groups](https://data.lacounty.gov/maps/51f14a2885794cf2a487b5057f149086/about) ([API Service](https://public.gis.lacounty.gov/public/rest/services/LACounty_Dynamic/Demographics/MapServer/15))

All feeds are public, no-auth ArcGIS Feature/Map Servers maintained by LA County.

## What we publish

The pipeline runs each weekday and uploads a fresh snapshot to a GitHub Release. The rolling `data-latest` tag points at the most recent snapshot; every dated release is preserved indefinitely as an audit trail.

| File | Contents |
|---|---|
| `parcels.geojson` | One feature per Altadena parcel with all derived fields. |
| `summary.json` | Burn-area-wide aggregate counts. |
| `qc-report.json` | QC threshold pass/fail and per-parcel warnings. |
| `2020-census-tracts.geojson` | One feature per 2020 census tract intersecting the fire perimeter, with the same counts as `summary.json` rolled up per tract. |
| `2020-census-block-groups.geojson` | One feature per 2020 census block group intersecting the fire perimeter, with the same counts as `summary.json` rolled up per block group. |
| `source-dins.json` | Snapshot of raw fetched DINS records. |
| `source-epicla.json` | Snapshot of raw fetched EPIC-LA records. |
| `source-fire-perimeter.json` | Snapshot of the Eaton Fire perimeter polygon(s). |
| `source-2020-census-tracts.json` | Snapshot of raw fetched 2020 census tract polygons within the perimeter envelope. |
| `source-2020-census-block-groups.json` | Snapshot of raw fetched 2020 census block group polygons within the perimeter envelope. |

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

`summary.json` contains burn-area-wide totals. `2020-census-tracts.geojson` and `2020-census-block-groups.geojson` carry the same counts rolled up per 2020 census tract / block group. Each parcel is assigned to a single tract and a single block group by polygon-centroid containment, so the per-region totals sum back to the burn-area totals exactly. Altagether-zone aggregates are planned but not yet implemented.

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

## Apendix

* [LA County Recovery Map](https://lacounty.maps.arcgis.com/apps/instant/portfolio/index.html?appid=b53bc2994933497ba2b2f04ceb67999d)
* [Official 2025 Fire Rebuilding Metric Definitions PDF](https://file.lacounty.gov/SDSInter/lac/1184128_2025FireRebuildingMetricDefinitions.pdf)

## License

MIT. See [LICENSE](./LICENSE).
