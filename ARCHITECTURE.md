# Architecture

For project overview, data source descriptions, and contributor quickstart, see [README.md](./README.md). This document covers internal architecture and is the primary reference for code changes.

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
│   fetch → join → aggregate   │                        │
│   → write outputs            │                        │
└──────────────┬───────────────┘                        │
               │ gh release upload --clobber            │
               ▼                                        │
┌──────────────────────────────┐                        │
│  GitHub Releases             │────────────────────────┘
│  - data-YYYY-MM-DD (history) │
│  - data-latest (rolling)     │
│  Assets:                     │
│    parcels.geojson           │
│    summary.json              │
│    tract_aggregates.csv      │
│    block_aggregates.csv      │
│    altagether_aggregates.csv │
└──────────────────────────────┘
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
│   │   ├── sources/              # ArcGIS fetchers, one per feature server
│   │   ├── processing/           # joins, normalization, aggregation
│   │   └── outputs/              # GeoJSON / JSON / CSV writers
│   ├── tests/
│   └── fixtures/                 # recorded ArcGIS responses for offline runs
├── web/                          # Vue 3 + Vite frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   └── public/
├── data/                         # local pipeline output (gitignored)
├── ARCHITECTURE.md
├── README.md
└── LICENSE
```

The pipeline and frontend are decoupled. The pipeline writes to `data/` locally and to a GitHub Release in CI. The frontend fetches from those Release URLs at runtime and never imports from `pipeline/`.

## Data pipeline

### Sources

Both sources are public ArcGIS Feature Servers (no auth, CORS-permissive). URLs and descriptions live in [README.md](./README.md#data-sources). Pull strategy:

- Use the FeatureServer query API with `f=geojson` and `where=1=1`, paginated via `resultOffset` / `resultRecordCount`.
- Respect each server's `maxRecordCount`. Page until `exceededTransferLimit` is false.
- Cache raw responses under `pipeline/.cache/` for the duration of a run; do not commit.

Known quirks to handle defensively:

- ArcGIS occasionally returns features with `null` geometry — drop and log.
- DINS damage classifications use multiple distinct strings — normalize to a documented enum in `processing/`.
- Source field names and types may drift between releases — validate against expected schema (see `pipeline/src/after_eaton/sources/schemas.py`) and fail loudly.

### Processing

The pipeline produces a parcel-level join, then derives all other outputs from it:

1. Fetch all DINS-tagged parcels in Altadena.
2. Fetch all EPIC-LA fire recovery cases in Altadena.
3. Join cases to parcels by APN
4. Compute per-parcel fields (see Parcel Analysis in README)
5. Aggregate to (a) site-wide totals, (b) census tracts, (c) census blocks, (d) Altagether blocks.

**TODO: Aggregate boundary definition and source.** Expected at `pipeline/src/after_eaton/processing/*.geojson` unless decided otherwise.

### Outputs

All outputs are written to `data/` locally and uploaded as Release assets in CI:

| File | Format | Contents |
|---|---|---|
| `parcels.geojson` | GeoJSON FeatureCollection | One feature per parcel with damage, permit, and rebuild fields |
| `summary.json` | JSON object | Burn area wide aggregate counts and percentages |
| `census_tracts.geojson` | GeoJSON FeatureCollection | Aggregate per census tract |
| `census_blocks.geojson` | GeoJSON FeatureCollection | Aggregate per census block |
| `altagether_aggregates.geojson` | GeoJSON FeatureCollection | Aggregate per Altagether block |

Every output carries a `generated_at` ISO 8601 timestamp:
- `summary.json`: top-level field
- `*.geojson`: `metadata.generated_at` on the FeatureCollection

### Schedule

```yaml
# .github/workflows/pipeline.yml
on:
  schedule:
    - cron: '0 20 * * 1-5'   # 13:00 PT during PDT, 12:00 PT during PST
  workflow_dispatch: {}
```

Notes:

- GitHub Actions cron is in UTC. `0 20 * * 1-5` lands on 1PM Pacific during PDT (mid-March through early November). During PST the run shifts to noon PT. We accept the one-hour seasonal drift rather than maintaining two cron entries.
- `workflow_dispatch` is always allowed and produces a release tagged with the run date.
- GitHub auto-disables scheduled workflows in repos with no commits for 60 days. Each successful run pushes a release built statically with the latest summary.json, which keeps the schedule alive.
- Scheduled runs can be delayed several minutes under GitHub load — fine for daily cadence.

### Failure modes

- **Source unavailable or 5xx:** retry with exponential backoff (3 attempts: 30s / 2m / 8m). If still failing, fail the workflow and do **not** publish a partial release.
- **Schema drift:** validate fields and types after fetch; fail with a descriptive error naming the offending field.
- **Empty result:** treat zero rows from EPIC-LA as suspicious. Require at least one row from each source or fail.
- **Geometry issues:** log and drop individual bad features; fail the run only if more than 1% of features are dropped.

## Release strategy

Each successful pipeline run does two things:

1. Creates a dated release `data-YYYY-MM-DD` with all five output files attached.
2. Updates the rolling `data-latest` tag to the same assets via `gh release upload data-latest <files> --clobber`.

The dated releases are the historical record; `data-latest` is the stable URL the frontend depends on. Future releases may allow for loading historical data.

**Public URLs the frontend depends on (canonical):**

```
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/parcels.geojson
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/summary.json
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/tract_aggregates.csv
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/block_aggregates.csv
https://github.com/bloudermilk/after-eaton/releases/download/data-latest/altagether_aggregates.csv
```

We use the explicit `data-latest` tag rather than `/releases/latest/download/` because `latest` resolves by GitHub's own ordering rules (most recent non-prerelease) and could behave unexpectedly when a dated release and the rolling tag are both updated in the same run.

Retention: keep all dated releases indefinitely. They are small and provide an audit trail of how rebuild progress changed over time.

## Frontend

Vue 3 + Vite, built as a static SPA. **TODO: higher-level framework (Nuxt static, vanilla Vue + vue-router, etc.) — currently undecided.**

### Data loading

On app load, fetch the data files from Releases:

- Send `If-None-Match` with cached `ETag` to leverage browser cache and Fastly conditional GETs.
- Show a loading state while data fetches.
- Show a stale-data banner if the embedded `generated_at` is more than 96 hours old.
- On fetch failure, render a clear error state

### Date display

The frontend prominently displays the data's `generated_at` date  as a footer pill, e.g. "Data as of Mon Apr 27, 2026 PDT/PST".

### Build and deploy

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
    paths: ['web/**', '.github/workflows/deploy.yml']
  workflow_dispatch: {}
```

Build: `cd web && npm ci && npm run build`. Deploy `web/dist/` to GitHub Pages via `actions/deploy-pages`.

The frontend deploy is **independent of the data pipeline**. Data updates do not redeploy the frontend; the frontend re-fetches data on each page load.

## Local development

### Prerequisites

- Python 3.11+
- Node 20+
- `gh` CLI (only needed for testing release uploads)

### Pipeline

**TODO: add pipeline usage docs**

### Frontend

**TODO: add frontend usage docs**

## Conventions

- **Python:** formatted with `ruff format`, linted with `ruff check`. Type-checked with `mypy --strict` on `pipeline/src/`.
- **JS/TS:** formatted with `prettier`, linted with `eslint`. TypeScript `strict` mode.
- **Commits:** conventional-commits-ish, not enforced. Prefixes: `feat:`, `fix:`, `chore:`, `data:`, `docs:`.
- **Branching:** trunk-based on `main`; PRs squash-merged.
- **Naming:** `snake_case` in Python, `camelCase` in TS, `kebab-case` for filenames in `web/`.

## Secrets and configuration

- `GITHUB_TOKEN` — automatically provided by Actions, sufficient for `gh release` operations on the same repo. No PAT needed.
- Both ArcGIS sources are public; no API keys.
- Local development needs no secrets.

## Operational notes

### Known limitations

- GitHub Pages bandwidth soft cap: ~100 GB/month.
- Releases asset downloads are CDN-backed but not rate-limit-documented; we expect this site to remain well under any practical limit.
- No alerting on pipeline failure beyond GitHub's default notification to the workflow author. **TODO: add a webhook (Slack/Discord/email list) once the project has more contributors.**

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
- The frontend's stale-data banner is the user-visible signal that the pipeline has stopped producing fresh output.

## Out of scope / non-goals

- **No user accounts or authentication.** The site is fully public and read-only.
- **No personally identifiable information.** Outputs are aggregated or parcel-level public records; no resident names, contact info, or anything sourced from non-public records.
- **No server-side runtime.** Static files plus client-side JavaScript only.
- **No runtime database.** All data lives in Release assets; the frontend treats them as the single source of truth.
- **No real-time data.** Daily-cadence updates are the contract.
- **No write paths.** No submissions, comments, or any user input beyond client-side filtering.