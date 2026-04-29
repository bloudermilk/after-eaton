# Methodology

This document describes — end-to-end and at the attribute level — how the After Eaton pipeline turns LA County's open data into the fields you see in our outputs. It is intended for two audiences:

1. **End users** who want to understand what a number on the site means.
2. **Auditors and journalists** who want to reproduce or critique a specific result.

For the *project* overview see [README.md](./README.md). For implementation specifics (module layout, retry policy, etc.) see [ARCHITECTURE.md](./ARCHITECTURE.md).

The pipeline runs once per weekday and produces a fresh snapshot. Every snapshot is preserved as a dated GitHub Release; the rolling `data-latest` tag points at the most recent. Re-running the pipeline against the same upstream data produces identical outputs (modulo the timestamp), and we publish the raw fetched records alongside the analysis so any output is traceable to its source.

---

## Sources

We pull from two public ArcGIS Feature Servers operated by LA County. No authentication is required and we never modify the source data; we read once per run and persist a snapshot.

### DINS — 2025 Parcels with DINS data

- **Service:** `services.arcgis.com/RmCCgQtiZLDCtblq/.../2025_Parcels_with_DINS_data/FeatureServer/5`
- **Filter applied:** `COMMUNITY = 'Altadena'`
- **Records fetched:** ~9,500 parcels (the entire Altadena community, including parcels with no fire damage — we keep them so totals make sense).
- **Persisted as:** `source-dins.json` in every release.

DINS ("Damage INSpection") is the County's parcel-level fire-impact dataset. Each row is one assessor parcel with the post-fire damage observation overlaid on the assessor's pre-fire structure record. Geometry is the parcel polygon.

DINS fields we read:

| Field | Used for |
|---|---|
| `AIN_1` | 10-digit parcel ID, our join key. |
| `APN_1` | 12-character APN (`5841-009-012`), included in output for human readability. |
| `SitusFullAddress` (or `SitusAddress`) | Display address. |
| `DAMAGE_1` | Pre-fire damage classification — see [Damage levels](#damage-levels-firescope-vs-bsd-tag). |
| `BSD_Tag` | Safety-assessment tag — what LA County's Recovery Map reports as Destroyed/Damaged Parcels. |
| `DesignType1` … `DesignType5` | Per-structure design code; first two digits classify SFR vs. MFR. |
| `SQFTmain1` … `SQFTmain5` | Per-structure square footage (assessor's record). |
| `Units1` … `Units5` | Per-structure unit count (carried for context, not yet aggregated). |
| `UseDescription` | Used to disambiguate single-residence parcels (e.g. main house + guesthouse). |
| `DINS_Count` | Count of damaged structures the inspector tagged on the parcel. Pass-through. |
| `Permit_Status`, `ROE_Status`, `Debris_Cleared` | Pass-through status fields. |
| Geometry | Parcel polygon, used for `parcels.geojson`. |

### EPIC-LA — Eaton/Palisades Fire Recovery Cases

- **Service:** `services.arcgis.com/RmCCgQtiZLDCtblq/.../EPICLA_Eaton_Palisades/FeatureServer/0`
- **Filter applied:** `DISASTER_TYPE = 'Eaton Fire (01-2025)'`
- **Records fetched:** ~5,700 cases (one row per *case*, not per parcel).
- **Persisted as:** `source-epicla.json` in every release.

EPIC-LA is the County's permitting workflow database, exposed publicly for fire recovery. A single parcel can have multiple cases — typically a `PlanManagement` case (filed first, for plan/zoning review) followed by one or more `PermitManagement` cases (the actual building permit). 41% of parcels with cases have both module types; 56% have permit-only; 3% have plan-only.

EPIC-LA fields we read:

| Field | Used for |
|---|---|
| `MAIN_AIN` | 10-digit parcel ID, the join key onto `DINS.AIN_1`. |
| `MODULENAME` | `PermitManagement` (building permit) vs. `PlanManagement` (plan review). |
| `WORKCLASS_NAME` | Permit category: `New`, `Rebuild Project`, `Express Temporary Housing`, `Repair/Replacement`, `Addition/Alteration`, etc. We treat `New` and `Rebuild Project` as primary-permit candidates. |
| `DISASTER_TYPE` | Used to filter to Eaton Fire cases. |
| `DESCRIPTION` | Free text — parsed for structure type, sqft, LFL claim. |
| `PROJECT_NAME` | Free text — parsed for LFL claim as fallback to DESCRIPTION. |
| `REBUILD_PROGRESS_NUM` | Integer 1–7, the permit's lifecycle stage (see [Rebuild progress](#rebuild-progress)). |
| `REBUILD_PROGRESS` | Human-readable label corresponding to the number. |
| `APPLY_DATE` | Epoch milliseconds. Used for recency ordering in LFL resolution. |
| `STAT_CLASS` | EPIC-LA's structure-type tag (e.g. `New SFR not a tract`). We do *not* trust this for classification — many ADU/garage permits carry it incorrectly. |
| `NEW_DWELLING_UNITS`, `ACCESSORY_DWELLING_UNIT`, `JUNIOR_ADU` | Carried for context and used in QC heuristics. We don't trust them as the primary structure-type signal because they conflate slots. |

### Eaton Fire Perimeter

- **Service:** `services.arcgis.com/RmCCgQtiZLDCtblq/.../Eaton_Fire_Perimeter/FeatureServer/0`
- **Filter applied:** none — the layer covers only the Eaton Fire.
- **Persisted as:** `source-fire-perimeter.json`.
- **Used for:** computing the bounding envelope used to filter the 2020 census tract and block group queries.

### 2020 Census Tracts / Block Groups

- **Services:** `public.gis.lacounty.gov/.../Demographics/MapServer/14` (tracts) and `MapServer/15` (block groups).
- **Filters applied:**
  - Tracts: spatial — only polygons whose envelope intersects the fire-perimeter envelope (EPSG:4326).
  - Block groups: attribute — `CT20 IN (<the CT20 values from the fetched tract set>)`. We do *not* re-apply the perimeter envelope to block groups: filtering by parent tract guarantees the block groups exactly partition the tracts (no orphan block groups whose parent tract was excluded, no stray groups from neighbouring tracts that happened to clip the perimeter envelope).
- **Persisted as:** `source-2020-census-tracts.json` and `source-2020-census-block-groups.json`.
- **Used for:** the per-tract / per-block-group rollups in `2020-census-tracts.geojson` and `2020-census-block-groups.geojson`.

Each layer's identifier fields (`CT20`, `BG20`, `LABEL`) flow through to the per-feature `properties`.

### What we explicitly do *not* use

- **`STAT_CLASS` for SFR/ADU classification.** It is set by intake on a permit-type basis and routinely mislabels ADU and garage permits. We classify from `DESCRIPTION` text instead.
- **`NEW_DWELLING_UNITS` / `ACCESSORY_DWELLING_UNIT` for primary classification.** These are aggregate counts that don't tell us how many of each type. We use them only as QC sanity checks.
- **DINS records for parcels outside Altadena.** EPIC-LA cases whose `MAIN_AIN` doesn't match an Altadena DINS parcel are dropped at the join step (typically <20 parcels per run; logged at `INFO`).

---

## Damage levels (FIRESCOPE vs BSD tag)

LA County publishes two distinct damage signals on the same parcel. They mean different things and disagree on roughly 200 parcels. We expose both.

### `damage` — DINS `DAMAGE_1` (FIRESCOPE %-loss)

The FIRESCOPE classification, used by California fire agencies for post-incident assessment. It bins parcels by *percentage of structure lost*:

| Code in our output | DINS string | Definition |
|---|---|---|
| `destroyed` | `Destroyed (>50%)` | More than 50% of the structure is lost. |
| `major` | `Major (26-50%)` | 26–50% damage. |
| `minor` | `Minor (10-25%)` | 10–25% damage. |
| `affected` | `Affected (1-9%)` | 1–9% damage. |
| `no_damage` | `No Damage` | <1% damage. |
| `no_data` | `No Data/Vacant` (or null) | No tag recorded. |

Source: `pipeline/src/after_eaton/processing/normalize.py:RAW_TO_DAMAGE`.

### `bsd_status` — DINS `BSD_Tag` (Safety Assessment)

The post-fire Building Safety Department field-assessment tag. This is what the LA County Recovery Map publishes as "Destroyed/Damaged Parcels":

| Code in our output | DINS string | Definition (per [LA County metric definitions PDF][1]) |
|---|---|---|
| `red` | `Red` | "Red Tagged" — uninhabitable; structure may not be entered or occupied. |
| `yellow` | `Yellow` | "Yellow Tagged" — limited access, certain areas restricted due to safety. |
| `green` | `Green` | "Green Tagged" — safe to occupy. |
| `none` | (null or empty) | No safety-assessment tag recorded. |

[1]: https://file.lacounty.gov/SDSInter/lac/1184128_2025FireRebuildingMetricDefinitions.pdf

The two systems are independent. The FIRESCOPE bucket reflects observed % loss; the BSD tag reflects safety inspectors' occupancy decision. They mostly agree, but ~141 parcels are FIRESCOPE-Destroyed but only Yellow-tagged (rebuild-with-restrictions rather than uninhabitable), and a handful go the other way.

The Recovery Map's headline "5,936 Destroyed/Damaged Parcels" corresponds to `bsd_red_count + bsd_yellow_count` in our `summary.json`. Our `damaged_parcels` (from FIRESCOPE) is computed differently — see the `summary.json` reference below.

---

## Rebuild progress

EPIC-LA assigns each case a `REBUILD_PROGRESS_NUM` of 1–7 corresponding to a stage in the rebuild lifecycle:

| Number | Label |
|---|---|
| 1 | Rebuild Applications Received |
| 2 | Zoning Reviews Cleared |
| 3 | Full Building Plans Received |
| 4 | Building Plans Approved |
| 5 | Building Permits Issued |
| 6 | Rebuild In Construction |
| 7 | Construction Completed |
| `null` | Temporary Housing or other non-rebuild case (ignored for progress) |

For a parcel with multiple cases, we report the **maximum** `REBUILD_PROGRESS_NUM` across all fire cases (both modules). A parcel with a `PlanManagement` case at progress 2 and a `PermitManagement` case at progress 6 is reported as `rebuild_progress_num = 6`.

---

## Pre-fire structure inference (DINS slots)

DINS encodes up to five structures per parcel via `DesignType{1..5}` and `SQFTmain{1..5}`. We classify each slot by the first two digits of `DesignType`:

- **`01xx` — Single-Family-class.** By default this is an SFR. *Exception:* for parcels with `UseDescription = 'Single'`, slots **2 through 5** with an `01xx` design type are treated as ADUs (typically a guesthouse on a single-residence parcel).
- **`02xx` – `05xx` — Multi-Family-class.** Counted as MFR.
- **All other prefixes (`06xx` and above, or null)** — ignored; these are commercial, agricultural, or unbuilt parcels we don't analyze.

Per parcel we emit:

- `pre_sfr_count`, `pre_sfr_sqft` — counts and summed square footage of `01xx` slots not reclassified as ADU.
- `pre_adu_count`, `pre_adu_sqft` — counts and summed square footage of `01xx` secondary slots on `Single`-use parcels.
- `pre_mfr_count`, `pre_mfr_sqft` — counts and summed square footage of `02xx`–`05xx` slots.

Sqft fields are `null` (rather than 0) when the corresponding count is 0, so consumers can distinguish "no SFR on this parcel" from "an SFR with unknown sqft".

Source: `pipeline/src/after_eaton/processing/parcel_analysis.py:_analyze_pre_fire`.

> **Note on LA County's broader definition.** The County's official metric definitions PDF treats SFR as "2 units or less (duplex, apartment, condo, etc.)" and MFR as "3 or more units". Our parser currently classifies any DUPLEX as MFR, which is stricter than the County's definition. This is a known divergence; reconciling it would require revising both the regex and the DINS-slot logic.

---

## Post-fire structure inference

A single parcel often has multiple fire-related EPIC-LA records — a `PlanManagement` "Rebuild" record filed first for zoning/plan review, followed by one or more `PermitManagement` "New"/"Rebuild Project" records for the actual building permits. ~49% of parcels have ≥2 such records, and the most common pattern is a separate SFR permit + separate ADU permit.

The pipeline runs **two extractors in parallel** on each parcel and prefers the LLM result, with the regex extractor as a cross-validation channel:

### LLM extractor (primary)

For every parcel with at least one **qualifying record**, we send the full bundle to an LLM and ask it to return the list of structures expected post-completion.

A record qualifies when:
- `MODULENAME = "PermitManagement"` and `WORKCLASS_NAME ∈ {"New", "Rebuild Project"}`, **or**
- `MODULENAME = "PlanManagement"` and `WORKCLASS_NAME = "Rebuild"`.

Temporary Housing Project records (RVs / trailers) are excluded — they aren't part of the planned final state.

The LLM follows explicit dedup rules (`pipeline/src/after_eaton/processing/llm_prompts.py:SYSTEM_PROMPT`):

1. Numbered list items in one description (`1.`, `2.`, …) → distinct structures.
2. Explicit `REVISION TO`, `REPLACES`, `SUPERSEDES`, `VOIDS` language → same structure (most recent wins).
3. Plan + permit on the same project → same structure (most-recent-by-`APPLY_DATE` wins, regardless of module).
4. `UNIT 1`/`UNIT 2`, `BUILDING 1`/`BUILDING 2`, `FRONT`/`REAR` separators → distinct structures.
5. Floor labels alone do **not** merge — each independently-habitable dwelling unit (own kitchen, bath, bedrooms — i.e. each unit that would receive its own street address) counts separately. Worked example: AIN 5845016021's "2 NEW ADU DUPLEXS … 798 SF PER UNIT" with four floor-by-floor permits = **4 ADUs**, not 1.
6. Cross-references like "PERMIT FEES PAID UNDER BLDR…" are billing conveniences and do **not** imply duplication.
7. Same type + different sqft → distinct.
8. Different types → distinct.

Each structure carries a `confidence` field (`high` / `medium` / `low`); low-confidence items emit a per-record QC warning so reviewers can audit.

Results are cached deterministically in `llm-extraction-cache.json` (released alongside other data assets). Cache keys hash `(ain, sorted (case_number, description_hash) tuples, prompt_version, provider, model)`, so a permit moving from "Issued" → "Finaled" doesn't trigger re-extraction, but a description edit does.

The pipeline runs the regex extractor on the same parcel and emits comparison warnings to `qc-report.json`:

- `extraction_count_disagreement` (info) — regex and LLM produced different counts for some residential type.
- `extraction_sqft_disagreement` (info) — counts match but sqft differs by >10%.
- `extraction_only_llm` (info) — plan-only parcel; regex had no opinion.
- `extraction_low_confidence` (info) — LLM marked at least one structure as low-confidence.
- `llm_extraction_failed` (data) — LLM call errored; regex fallback used.

The aggregate `extraction_comparison` block in `qc-report.json` reports overall agreement rate, provider/model used, and per-warning-type counts — all informational, not gated.

### Regex extractor (fallback)

If the LLM is disabled (no API key, `--no-llm-extraction`) or its call fails for a specific parcel, the pipeline falls back to the original single-permit regex parser described below. The regex path also remains the cross-validator when both run.

Regex selection picks one **primary permit** per parcel:

1. Restrict to `MODULENAME = 'PermitManagement'` cases whose `WORKCLASS_NAME` is `New` or `Rebuild Project`.
2. Among those, pick the case with the highest `REBUILD_PROGRESS_NUM` (ties broken by source order).
3. If no qualifying permit exists, all `post_*` fields on the parcel are `null`.

The primary permit's `DESCRIPTION` is then parsed by `parse_description()`. The parser's job is to (a) split a multi-structure description into segments, (b) classify each segment's primary structure type, and (c) extract that segment's primary square footage.

### Step 1 — Segment splitting

If the description contains **numbered list items** (lines matching `^\s*\d+\.\s`), each item becomes its own segment. Otherwise the whole description is treated as a single segment.

Real example (one parcel, four structures):

```
1. EATON FIRE REBUILD - NEW 2-STORY 1107 SF SB9 (2 BEDROOMS AND 2 BATHROOMS) WITH 464 SF ATTACHED GARAGE…
2. EATON FIRE REBUILD - NEW 2-STORY 1115 SF SFR (2 BEDROOMS AND 2 BATHROOMS) WITH 50 SF PORCH
3. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU
4. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU
```

This produces four `ParsedStructure` records: `(sb9, 1107)`, `(sfr, 1115)`, `(adu, 1110)`, `(adu, 1110)`.

### Step 2 — Per-segment structure classification

Each segment is classified into one of these types:

| Type | Recognized via | Counts toward post-fire dwellings? |
|---|---|---|
| `sfr` | `\bSF[RDH]\b`, `\bSINGLE[\s-]+FAMIL` (matches "SFR", "SFD", "SFH", "SINGLE FAMILY"/"SINGLE-FAMILY") | Yes |
| `adu` | `\bADUS?\b`, `\bACCESSORY\s+DWELL` (matches "ADU", "ADUS", "ACCESSORY DWELLING") | Yes |
| `jadu` | `\bJADUS?\b`, `\bJUNIOR\s+ADU` | Yes |
| `sb9` | `\bSB[\- ]?9\b`, `\bSENATE\s+BILL\s*9` | Yes |
| `mfr` | `\bDUPLEX\b`, `\bTRIPLEX\b`, `\bMFR\b`, `\bMULTI[\s-]*FAMIL`, `\bCONDO\s+UNIT` | Yes |
| `garage` | `\bGARAGE\b`, `\bCARPORT\b` | No |
| `temporary_housing` | `\bTEMP(?:\.\|ORARY)?\s+HOUSING`, `\b(RV\|MOTOR\s+HOME\|TRAILER\|CAMPER)\b` | No |
| `repair` | `\bREPAIR\b`, `\bALTERATION\b`, `\bREPLACE\b`, `\bRENOVAT…`, `\bRESTORATION\b`, `\bREMODEL\b`, `\bTENANT\s+IMPROV` | No |
| `retaining_wall` | `\bRETAINING\s+WALL`, `\bCMU\s+WALL`, `\b(LANDSCAPING\|GRADING)\b` | No |
| `seismic` | `\bSEISMIC\s+(RETROFIT\|UPGRADE\|REROFIT)` | No |
| `unknown` | none of the above match | No |

When more than one keyword matches the same segment, we use a **three-tier priority** rule:

- **Tier 1 (residential primary):** sb9, jadu, adu, sfr, mfr
- **Tier 2 (secondary structure):** garage
- **Tier 3 (non-structural):** temporary_housing, repair, retaining_wall, seismic

We pick the earliest match in the highest-priority tier with any match. This is the rule that makes `"WITH 524 SF ATTACHED GARAGE WITH 270 SF REAR PATIO WITH … 3,484 SF SINGLE FAMILY RESIDENCE"` classify as `sfr` even though `GARAGE` appears first — `sfr` is in tier 1 and `garage` in tier 2.

Within tier 1, we use earliest position. So `"REBUILD-ADU- 1-STORY 800 SF SFD"` classifies as `adu` (ADU appears before SFD), correctly recognizing that the SFD is descriptor for the ADU.

Source: `pipeline/src/after_eaton/processing/description_parser.py:_TIERS`, `_parse_segment`.

### Step 3 — Per-segment square-foot extraction

After classification, we extract the segment's primary sqft by finding the numeric sqft *closest to* the structure keyword's position. The sqft regex matches:

- **Abbreviated units:** `1,680 SF`, `1,680 S.F.`, `1,680 SQFT`, `1,680 sq ft`, `1,680 sq. ft.`
- **Spelled-out units:** `1,680-square-foot`, `1,680 square foot`, `1,680 square feet`

The leading `\b` anchor before the digit prevents matching the trailing `9` in tokens like `SB9 SFR` as `9` sqft. There is deliberately no trailing constraint — `"1,705 SFR"` (unit running into the next word) and `"1412 SF\n"` (unit at end of line) both match.

Source: `pipeline/src/after_eaton/processing/description_parser.py:_SQFT_RE`, `_pick_sqft_near`.

### Step 4 — Per-parcel aggregation

We group segments by type and sum sqft within each group:

- `post_sfr_count`, `post_sfr_sqft` — count and summed sqft of `sfr` segments.
- `post_adu_count`, `post_adu_sqft` — same for `adu` (note: `jadu` is classified separately and not folded into `adu`).
- `post_mfr_count`, `post_mfr_sqft` — same for `mfr`.
- `post_sb9_count`, `post_sb9_sqft` — same for `sb9`.

`garage`, `temporary_housing`, `repair`, `retaining_wall`, `seismic`, and `unknown` segments are recognized for QC purposes but do not contribute to dwelling counts.

If no primary permit exists for the parcel, all `post_*` fields are `null`. (Under the LLM path, plan-only parcels can still produce non-null `post_*` values — the LLM will return whatever structures are described in the plan record.)

---

## Like-for-Like vs Custom (LFL claim)

LA County's metric definitions distinguish two rebuild paths:

- **Like-for-Like (LFL):** "Reconstruction that matches the original structure in size, location, and use, with allowances for minor modifications." Faster review path.
- **Custom:** "Reconstruction potentially involves an increase in size, height, or use, and is subject to more extensive reviews and approvals." (EPIC-LA case text usually says "Non-Like-for-Like" rather than "Custom".)

We classify each parcel into one of three states: `True` (LFL claimed), `False` (Custom / Non-LFL claimed), or `null` (no signal in any case).

### Resolution rule

For a parcel with one or more fire-related EPIC-LA cases, walk cases in **reverse-chronological order** by `APPLY_DATE`. For each case:

1. Try `extract_lfl_claim(DESCRIPTION)`. If non-null, that's the answer.
2. Otherwise try `extract_lfl_claim(PROJECT_NAME)`. If non-null, that's the answer.
3. If both are null on this case, fall through to the next-most-recent case.

If no case yields a signal, `lfl_claimed = null`.

`extract_lfl_claim(text)` itself uses two patterns, *negative checked first* so "Non-Like-for-Like" doesn't accidentally match the positive pattern:

- Negative: `non[\s-]*like[\s-]*for[\s-]*like` → `False`
- Positive: `like[\s-]*for[\s-]*like` → `True`
- No match → `null`

Both are case-insensitive and tolerate hyphen / whitespace variations.

### Conflict detection

A parcel's cases sometimes give *different* non-null signals. When that happens, we deterministically pick the most-recent case's signal (per the rule above) and additionally set `lfl_conflict = True` so the case can be flagged for review. The flag is exposed both as a per-parcel attribute and as a `lfl_conflict` per-record warning in `qc-report.json`.

In our most recent run, 85 parcels had conflicts. Causes include applicant typos in the permit description (we've seen `"Eaton Non-Fire Like-for-Like Rebuild"` where the intent was clearly Non-LFL), as well as legitimate intent shifts between an early plan filing and a later permit filing.

Source: `pipeline/src/after_eaton/processing/parcel_analysis.py:_resolve_lfl`.

---

## Derived characterization fields

These are the per-parcel fields that combine pre- and post-fire information.

### `sfr_size_comparison`

For parcels where both `pre_sfr_sqft` and `post_sfr_sqft` are non-null:

- `larger` if `post - pre > 10`
- `smaller` if `post - pre < -10`
- `identical` if `|post - pre| ≤ 10`

The 10-sqft tolerance (`_IDENTICAL_TOLERANCE`) absorbs minor measurement rounding. If either side is null, `sfr_size_comparison = null`.

### `adds_sb9`

`True` if the primary permit's parsed structures contain at least one segment classified as `sb9`. This signals the rebuild adds a second primary unit under California's SB-9 lot-split / two-unit law. Otherwise `False` (including when no permit exists yet).

### `added_adu_count`

`max(0, post_adu_count − pre_adu_count)`. Positive only when the rebuild adds ADUs beyond what the parcel had pre-fire. If `post_adu_count` is unknown (no permit), returns `0` rather than null — so this field is a count of *confirmed* added ADUs, not an upper bound.

### `lfl_conflict`

See [Like-for-Like vs Custom](#like-for-like-vs-custom-lfl-claim).

---

## Geographic aggregations

The same parcel-level counts that roll up into `summary.json` also roll up per 2020 census tract and per 2020 census block group, and ship as `2020-census-tracts.geojson` / `2020-census-block-groups.geojson`.

**Boundary sources:** LA County's *2020 Census Tracts* (Demographics MapServer layer 14) and *2020 Census Block Groups* (layer 15). Tracts are fetched by spatial intersection with the Eaton Fire perimeter envelope (LA County's *Eaton Fire Perimeter* FeatureServer). Block groups are then fetched by `CT20 IN (...)` over the fetched tract set, so each tract's block groups perfectly partition that tract. The full perimeter polygon ships as `source-fire-perimeter.json` alongside the raw tract / block-group polygons.

**Assignment rule:** each Altadena DINS parcel is assigned to **exactly one** tract and **exactly one** block group by **polygon-centroid containment**. We compute the parcel polygon's centroid (shapely 2.x), then pick the tract/block-group polygon that contains it via an STRtree spatial index. Centroids landing exactly on a shared boundary are awarded to the nearest candidate (deterministic tiebreaker). Centroids that fall outside every fetched tract are not counted into any region and emit a `parcel_outside_census_tracts` per-record warning (severity `data`).

**Sum invariants** (enforced as hard-fail QC thresholds in `qc/aggregate.py`; see [Aggregate thresholds](#aggregate-thresholds-gate-the-run)):

- `tract_total_matches_summary` — `sum(tract.total_parcels) + len(unassigned_ains)` equals the burn-area total.
- `tract_partitions_into_block_groups` — every tract's `total_parcels` equals the sum of its block-groups' `total_parcels`. We fetch block groups via `CT20 IN (<tract ids>)` precisely so this invariant holds by construction; a violation flags drift between the two LA County census layers.

A failure of either invariant aborts the run with exit code 3 and **no release is published**.

**Per-feature contract:** each tract/block-group `Feature` carries identifier fields (`ct20` + `label` for tracts; `bg20` + `ct20` + `label` for block groups) plus every numeric count from `summary.json` — `total_parcels`, `damaged_parcels`, `destroyed_parcels`, the `bsd_*_count` set, the rebuild-progress set, the LFL set, the SFR-size set, `sb9_count`, and `added_adu_count`. A tract/block-group that intersects the perimeter envelope but contains zero Altadena parcels still ships as a feature with all counts = 0, so the geographic frame is stable regardless of source drift.

Source: `pipeline/src/after_eaton/processing/spatial_aggregate.py:aggregate_by_region`.

---

## Quality controls

Every run produces a `qc-report.json` documenting both gate-level pass/fail and per-parcel warnings.

### Aggregate thresholds (gate the run)

If any threshold fails, the run aborts with exit code 3 and **no release is published**. The thresholds are constants at the top of `pipeline/src/after_eaton/qc/aggregate.py`.

| Threshold | Default | Definition |
|---|---|---|
| `description_parse_rate` | ≥ 90% | Of fire-related `PermitManagement` cases with non-null `DESCRIPTION`, fraction the parser classified to a known type or extracted a sqft from. |
| `sfr_sqft_extraction_rate` | ≥ 85% | Of permits whose `DESCRIPTION` mentions an SFR keyword and a numeric sqft, fraction the parser classified as `sfr` with a sqft. (Includes false-positive candidates where SFR is used as a descriptor, e.g. `"ADU 800 SF SFD"`; the parser correctly classifies those as ADU and they count as misses here.) |
| `warning_rate` | ≤ 5% | Fraction of parcels that raised at least one **`data`-severity** per-record warning. `info`-severity warnings (real-world ambiguity) are excluded. |
| `min_completed_rebuilds` | ≥ 1 | Sanity check against an empty/stale dataset — at least one parcel has reached `Construction Completed`. |
| `tract_total_matches_summary` | exact equality | `sum(tract.total_parcels) + len(unassigned)` must equal the burn-area `total_parcels`. Catches a parcel being double-counted across tracts or silently dropped during the centroid pass. |
| `tract_partitions_into_block_groups` | exact equality | For every tract, `tract.total_parcels` must equal the sum of its block-groups' `total_parcels`. Catches drift between the two LA County census layers, or a parcel whose centroid lands in a tract but in none of that tract's block-group polygons. |

The candidate-set predicates are deliberately defined with regexes independent from the parser, so a parser regression cannot shrink the denominator and silently mask itself.

### Per-record warnings

Every `ParcelResult` is checked against five conditions. Each emits a warning with a stable `code`, a free-text `detail`, and a `severity`:

| Code | Severity | When it fires |
|---|---|---|
| `destroyed_no_epicla` | `info` | Parcel is `damage = destroyed` but has no EPIC-LA cases. Reflects reality (many destroyed parcels haven't filed yet) — does not indicate a data bug. |
| `implausible_post_sfr_sqft` | `data` | Post-fire SFR sqft is < 200 or > 20,000. Indicates a parser misread or a genuinely odd permit. |
| `permit_all_unknown_structures` | `data` | A permit reports `NEW_DWELLING_UNITS > 0` but the parser classified every segment as `unknown`. Indicates the parser is missing a description pattern. |
| `size_compared_without_lfl_signal` | `info` | We have both pre and post SFR sqft (so `sfr_size_comparison` is non-null) but no source stated LFL or Custom. Real-world ambiguity. |
| `lfl_conflict` | `data` | The parcel's cases produced two or more distinct LFL/Custom signals; the most-recent case won, but the disagreement is flagged. |
| `parcel_outside_census_tracts` | `data` | The parcel's polygon centroid did not fall inside any fetched 2020 census tract — likely a corrupt parcel polygon or perimeter/tract boundary drift. The parcel still appears in `parcels.geojson` and `summary.json` but is not counted into any per-tract / per-block-group total. |

Severity controls only whether the warning counts toward `warning_rate`. All warnings are written to `qc-report.json` regardless.

---

## Output reference (attribute-level)

All outputs are written to a flat directory (`data/` locally, GitHub Release assets in CI). Every file carries a `generated_at` ISO 8601 timestamp.

### `parcels.geojson`

GeoJSON `FeatureCollection`. One `Feature` per Altadena parcel.

```json
{
  "type": "FeatureCollection",
  "metadata": { "generated_at": "2026-04-27T23:34:02+00:00" },
  "features": [ { "type": "Feature", "properties": { ... }, "geometry": { ... } }, ... ]
}
```

`geometry` is a GeoJSON `Polygon` (single-ring parcels) or `MultiPolygon` (rare; parcels with disjoint rings), reprojected to WGS84 (EPSG:4326). `properties` carries every `ParcelResult` field:

| Property | Type | Source / definition |
|---|---|---|
| `ain` | `string` | DINS `AIN_1`, the 10-digit parcel ID. |
| `apn` | `string` | DINS `APN_1`, the 12-character APN with dashes (`5841-009-012`). |
| `address` | `string` | DINS `SitusFullAddress`, falling back to `SitusAddress`. May be empty. |
| `damage` | `string` enum | Normalized FIRESCOPE level: `destroyed`/`major`/`minor`/`affected`/`no_damage`/`no_data`. See [Damage levels](#damage-levels-firescope-vs-bsd-tag). |
| `bsd_status` | `string` enum | Normalized BSD tag: `red`/`yellow`/`green`/`none`. See [Damage levels](#damage-levels-firescope-vs-bsd-tag). |
| `pre_sfr_count` | `int` | Count of pre-fire SFR structures from DINS slots 1–5. |
| `pre_sfr_sqft` | `int \| null` | Summed sqft of pre-fire SFR structures, or `null` when count is 0. |
| `pre_adu_count` | `int` | Count of pre-fire ADUs (secondary `01xx` slots on `Single`-use parcels). |
| `pre_adu_sqft` | `int \| null` | Summed sqft of pre-fire ADUs, or `null` when count is 0. |
| `pre_mfr_count` | `int` | Count of pre-fire MFR structures (`02xx`–`05xx` slots). |
| `pre_mfr_sqft` | `int \| null` | Summed sqft of pre-fire MFRs, or `null` when count is 0. |
| `post_sfr_count` | `int \| null` | Count of post-fire SFRs from primary-permit DESCRIPTION; `null` if no primary permit exists. |
| `post_sfr_sqft` | `int \| null` | Summed sqft, or `null` if no primary permit or no sqft was extracted. |
| `post_adu_count` | `int \| null` | Same shape, for `adu` segments. |
| `post_adu_sqft` | `int \| null` | |
| `post_mfr_count` | `int \| null` | Same shape, for `mfr` segments. |
| `post_mfr_sqft` | `int \| null` | |
| `post_sb9_count` | `int \| null` | Same shape, for `sb9` segments. |
| `post_sb9_sqft` | `int \| null` | |
| `lfl_claimed` | `bool \| null` | `true` = Like-for-Like, `false` = Custom/Non-LFL, `null` = no source stated either way. See [Like-for-Like vs Custom](#like-for-like-vs-custom-lfl-claim). |
| `lfl_conflict` | `bool` | `true` if cases gave conflicting LFL signals; the most-recent case still wins. |
| `sfr_size_comparison` | `string \| null` | `larger`/`identical`/`smaller` (±10 sqft tolerance), or `null` if either pre or post SFR sqft is missing. |
| `adds_sb9` | `bool` | `true` if the primary permit description included an SB-9 segment. |
| `added_adu_count` | `int` | `max(0, post_adu_count − pre_adu_count)`. Always 0 if no primary permit. |
| `rebuild_progress_num` | `int \| null` | Max `REBUILD_PROGRESS_NUM` (1–7) across all fire cases on the parcel. `null` = no fire case with a progress number (e.g. parcel has only Temporary Housing cases). |
| `rebuild_progress` | `string \| null` | Human-readable label corresponding to `rebuild_progress_num`. |
| `permit_status` | `string \| null` | DINS `Permit_Status`, pass-through. |
| `roe_status` | `string \| null` | DINS `ROE_Status`, pass-through. |
| `debris_cleared` | `string \| null` | DINS `Debris_Cleared`, pass-through. |
| `dins_count` | `int` | DINS `DINS_Count`: number of damaged structures the inspector tagged on the parcel. |

### `summary.json`

Burn-area-wide aggregate counts.

```json
{
  "generated_at": "2026-04-27T23:34:02+00:00",
  "total_parcels": 9515,
  ...
}
```

| Field | Type | Definition |
|---|---|---|
| `generated_at` | `string` | ISO 8601 UTC timestamp at the start of the run. |
| `total_parcels` | `int` | Every Altadena DINS parcel, regardless of damage. |
| `damaged_parcels` | `int` | FIRESCOPE-based: parcels with `damage` in `{destroyed, major, minor, affected}`. |
| `destroyed_parcels` | `int` | FIRESCOPE-based: parcels with `damage = destroyed`. |
| `bsd_red_count` | `int` | BSD-tag-based: parcels with `bsd_status = red`. |
| `bsd_yellow_count` | `int` | BSD-tag-based: parcels with `bsd_status = yellow`. |
| `bsd_green_count` | `int` | BSD-tag-based: parcels with `bsd_status = green`. |
| `bsd_red_or_yellow_count` | `int` | `bsd_red_count + bsd_yellow_count`. **This is the figure that matches the LA County Recovery Map's "Destroyed/Damaged Parcels".** |
| `no_permit_count` | `int` | Parcels with `rebuild_progress_num = null` (no fire case carrying a progress number). |
| `permit_in_review_count` | `int` | Parcels with `rebuild_progress_num` in `{1, 2, 3, 4}` — application received through plans approved. |
| `permit_issued_count` | `int` | Parcels with `rebuild_progress_num = 5`. |
| `construction_count` | `int` | Parcels with `rebuild_progress_num = 6`. |
| `completed_count` | `int` | Parcels with `rebuild_progress_num = 7`. |
| `lfl_count` | `int` | Parcels with `lfl_claimed = true`. |
| `nlfl_count` | `int` | Parcels with `lfl_claimed = false`. |
| `lfl_unknown_count` | `int` | Parcels with `lfl_claimed = null` *that have a permit*. (Parcels with no permit are tracked separately by `no_permit_count`.) |
| `sfr_larger_count` | `int` | Parcels with `sfr_size_comparison = larger`. |
| `sfr_identical_count` | `int` | Parcels with `sfr_size_comparison = identical`. |
| `sfr_smaller_count` | `int` | Parcels with `sfr_size_comparison = smaller`. |
| `sb9_count` | `int` | Parcels with `adds_sb9 = true`. |
| `added_adu_count` | `int` | Parcels with `added_adu_count > 0` (note: name reused, slightly misleading — this is a *count of parcels*, not an aggregate ADU count). |

### `2020-census-tracts.geojson` / `2020-census-block-groups.geojson`

GeoJSON `FeatureCollection`. One `Feature` per 2020 census tract / block group intersecting the Eaton Fire perimeter envelope. Geometry is a GeoJSON `Polygon` or `MultiPolygon` in EPSG:4326.

```json
{
  "type": "FeatureCollection",
  "metadata": { "generated_at": "2026-04-27T23:34:02+00:00" },
  "features": [ { "type": "Feature", "properties": { ... }, "geometry": { ... } }, ... ]
}
```

`properties` carries:

- **Identifiers:** `ct20` (string), `label` (string) for tracts; `bg20` (string), `ct20` (string), `label` (string) for block groups.
- **Counts:** every numeric field listed in [`summary.json`](#summaryjson) below — `total_parcels`, `damaged_parcels`, `destroyed_parcels`, `bsd_red_count`, `bsd_yellow_count`, `bsd_green_count`, `bsd_red_or_yellow_count`, `no_permit_count`, `permit_in_review_count`, `permit_issued_count`, `construction_count`, `completed_count`, `lfl_count`, `nlfl_count`, `lfl_unknown_count`, `sfr_larger_count`, `sfr_identical_count`, `sfr_smaller_count`, `sb9_count`, `added_adu_count`.

See [Geographic aggregations](#geographic-aggregations) for the assignment rule.

### `qc-report.json`

```json
{
  "generated_at": "...",
  "total_parcels": 9515,
  "passed": true,
  "thresholds": [
    { "name": "description_parse_rate", "actual": 0.988, "threshold": 0.90, "passed": true, "detail": "..." },
    ...
  ],
  "warnings": [
    { "ain": "5841009012", "code": "lfl_conflict", "detail": "...", "severity": "data" },
    ...
  ]
}
```

| Field | Type | Definition |
|---|---|---|
| `generated_at` | `string` | ISO 8601 UTC. |
| `total_parcels` | `int` | Same as in summary.json. |
| `passed` | `bool` | `true` iff every threshold's `passed` is `true`. |
| `thresholds` | `list` | One entry per threshold. `actual` and `threshold` are floats; `detail` is a human-readable explanation including raw counts. |
| `warnings` | `list` | One entry per per-record warning. Multiple warnings per parcel are emitted as separate entries. |

### `source-dins.json`, `source-epicla.json`

Snapshot of the raw fetched records. Same envelope on both:

```json
{
  "source": "2025_Parcels_with_DINS_data",
  "fetched_at": "2026-04-27T23:34:02+00:00",
  "record_count": 9515,
  "records": [ { ... raw ArcGIS attributes + "_geometry" ... }, ... ]
}
```

Each record is the flat ArcGIS `attributes` dict merged with a `_geometry` key carrying the raw ArcGIS geometry (rings/x-y, EPSG:4326). These files exist so any output value can be traced back to the exact source row that produced it. Re-running the rest of the pipeline against a saved snapshot reproduces the same outputs.

---

## Known limitations

We document these openly because the pipeline is meant to be auditable, not just functional.

1. **MFR vs SFR definition diverges from the County's.** LA County treats up to 2 dwelling units (including duplexes) as SFR. We classify any DUPLEX/TRIPLEX as MFR. This affects 5–10 parcels in our current data.

2. **Parser correctness is measured by sqft *presence*, not *correctness*.** `sfr_sqft_extraction_rate` checks that some sqft was extracted; it doesn't verify the right one was picked when a description has multiple. Most miscalculations are caught by the per-record `implausible_post_sfr_sqft` warning (sqft < 200 or > 20,000), but silent miscalculations within plausible ranges are possible. The QA fixture suite is the primary defense — every fixture asserts an exact expected sqft.

3. **LFL resolution can be defeated by typos.** When a permit description contains a typo (e.g. `"Eaton Non-Fire Like-for-Like Rebuild"` where the applicant meant the Non-LFL track), the resolver follows the typo's literal reading. The `lfl_conflict` flag surfaces these for review but does not auto-correct.

4. **Attached vs detached ADU not distinguished.** LA County's metric definitions count only *detached* ADUs as separate units. Our parser treats both equally. Fixing this would require recognizing `ATTACHED` / `DETACHED` modifiers in the segment text.

5. **No commercial/non-residential coverage.** DINS slots `06xx`+ and EPIC-LA permits without a residential keyword are excluded from analysis. The Recovery Map's "Units" total includes commercial structures; ours does not.

6. **Altagether-zone aggregates are not yet implemented.** Census-tract and census-block-group aggregates ship as `2020-census-tracts.geojson` / `2020-census-block-groups.geojson` (see [Geographic aggregations](#geographic-aggregations)); Altagether-zone boundaries remain undecided.

7. **Recovery Map vs our numbers will disagree by a small amount.** Both sources refresh on independent cadences; expect 5–20 parcel drift between any two snapshots. Larger disagreements indicate a methodological difference and should be investigated rather than reconciled cosmetically.

---

## Reproducibility

To reproduce any output value:

1. Identify the parcel by `ain` from `parcels.geojson`.
2. Open `source-dins.json` and find the record whose `AIN_1` matches.
3. Open `source-epicla.json` and find every record whose `MAIN_AIN` matches.
4. Apply the rules in this document, in order: pre-fire from DINS slots → primary-permit selection → DESCRIPTION parsing → LFL resolution → derived fields.
5. The result should match the parcel's properties in `parcels.geojson` exactly. If it doesn't, the discrepancy is reproducible and traceable — please file an issue.

For a sanity check, four parcels are pinned as test fixtures with hand-verified expected values: `5829015008`, `5841009012`, `5842022003`, `5842024014`. See `pipeline/tests/fixtures/qa/`.
