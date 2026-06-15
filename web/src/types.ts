// Shapes mirror the Python pipeline outputs:
// - SummaryResult & RegionCounts: pipeline/src/altadata/processing/aggregate.py
// - QcReport, RecordWarning, ThresholdCheck: pipeline/src/altadata/qc/{report,aggregate,per_record}.py

export interface Summary {
  generated_at: string;
  total_parcels: number;
  damaged_parcels: number;
  destroyed_parcels: number;
  bsd_red_count: number;
  bsd_yellow_count: number;
  bsd_green_count: number;
  bsd_red_or_yellow_count: number;
  // Full rebuild funnel across ALL workclasses: parcels at or beyond each
  // milestone. Monotonic — a parcel is counted at every stage up to the furthest
  // it reached, so the counts strictly decline. Retained for future funnels
  // (earlier stages / repair pathways); the app publishes the `rebuild_new_*`
  // funnel below instead. See metrics.ts (rebuild_progress).
  rebuild_app_received_parcels: number;
  rebuild_zoning_cleared_parcels: number;
  rebuild_plans_received_parcels: number;
  rebuild_plans_approved_parcels: number;
  rebuild_permit_issued_parcels: number;
  rebuild_in_construction_parcels: number;
  rebuild_construction_completed_parcels: number;
  // New-construction milestones funnel — the one shown in the app. Parcels with a
  // new-building ("New" workclass) permit AND a FIRESCOPE-destroyed structure,
  // counted monotonically. Starts at "plans received" (New permits never carry
  // the earlier application/zoning milestones). Denominator is destroyed_parcels.
  rebuild_new_plans_received_parcels: number;
  rebuild_new_plans_approved_parcels: number;
  rebuild_new_permit_issued_parcels: number;
  rebuild_new_in_construction_parcels: number;
  rebuild_new_construction_completed_parcels: number;
  lfl_count: number;
  nlfl_count: number;
  lfl_unknown_count: number;
  sfr_size_pct_smaller_over_30: number;
  sfr_size_pct_smaller_10_to_30: number;
  sfr_size_pct_within_10: number;
  sfr_size_pct_larger_10_to_30: number;
  sfr_size_pct_larger_over_30: number;
  sfr_size_pct_unknown: number;
  sb9_count: number;
  sb1123_count: number;
  adu_added_1_count: number;
  adu_added_2_count: number;
  adu_added_3_plus_count: number;
  dwelling_rebuild_count: number;
}

// Shape of parcels-compact.geojson — one Point per parcel carrying only the
// properties the map reads. Bucket-key strings mirror the pipeline classifiers
// in processing/aggregate.py (and are described by METRICS in metrics.ts).
export interface ParcelProperties {
  ain: string;
  address: string;
  sfr_size_bucket: string;
  lfl_bucket: string;
  adu_bucket: string;
  adds_sb9: boolean;
  adds_sb1123: boolean;
  // Red- or Yellow-tagged in the post-fire Safety Assessment (County
  // "Damaged/Destroyed Parcels" scope). Retained for future use; the new-build
  // funnel's baseline is now FIRESCOPE `damage == "destroyed"` (see below).
  bsd_red_or_yellow: boolean;
  // Furthest rebuild milestone reached across ALL workclasses (0–7). Retained
  // for future funnels; the published funnel and map use rebuild_new_stage.
  rebuild_stage: number;
  // Furthest NEW-building ("New" workclass) milestone reached (0, or 3–7). Drives
  // the "New construction milestones" funnel's map stage ramp and its "currently
  // at stage N" filter (with the `damage == "destroyed"` baseline).
  rebuild_new_stage: number;
  // Raw counts/sqft + classifications read only by the per-parcel detail popup
  // (the buckets above drive the map coloring). Post-fire fields are null when
  // the parcel has no primary permit yet ("not yet filed").
  pre_sfr_count: number;
  post_sfr_count: number | null;
  pre_sfr_sqft: number | null;
  post_sfr_sqft: number | null;
  pre_adu_count: number;
  post_adu_count: number | null;
  added_adu_count: number;
  // FIRESCOPE %-loss bucket ("destroyed" | "major" | "minor" | "affected" |
  // "no_damage" | "no_data") and safety tag ("red" | "yellow" | "green" | "none").
  damage: string;
  bsd_status: string;
}

export interface ParcelFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: ParcelProperties;
}

export interface ParcelFeatureCollection {
  type: "FeatureCollection";
  metadata?: { generated_at: string };
  features: ParcelFeature[];
}

// Shape of fire-perimeter.geojson — a single dissolved (Multi)Polygon the map
// draws as a thin outline for burn-area context. The map reads no properties;
// they're carried for debugging/attribution only.
export interface FirePerimeterFeature {
  type: "Feature";
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
  properties: Record<string, unknown>;
}

export interface FirePerimeterFeatureCollection {
  type: "FeatureCollection";
  metadata?: { generated_at: string };
  features: FirePerimeterFeature[];
}

export type WarningSeverity = "data" | "info";

export interface RecordWarning {
  ain: string;
  code: string;
  detail: string;
  severity: WarningSeverity;
}

export interface ThresholdCheck {
  name: string;
  passed: boolean;
  actual: number;
  threshold: number;
  detail: string;
}

export interface QcReport {
  generated_at: string;
  total_parcels: number;
  warnings: RecordWarning[];
  thresholds: ThresholdCheck[];
  // extraction_comparison block has a flexible shape we don't render
  // strongly-typed yet — pass through as unknown.
  extraction_comparison?: unknown;
}
