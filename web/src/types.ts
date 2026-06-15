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
  // Rebuild-progress funnel: parcels at or beyond each milestone. Monotonic —
  // a parcel is counted at every stage up to the furthest it reached, so the
  // counts strictly decline (unlike LA County's non-monotonic case-level
  // dashboard). See metrics.ts (rebuild_progress).
  rebuild_app_received_parcels: number;
  rebuild_zoning_cleared_parcels: number;
  rebuild_plans_received_parcels: number;
  rebuild_plans_approved_parcels: number;
  rebuild_permit_issued_parcels: number;
  rebuild_in_construction_parcels: number;
  rebuild_construction_completed_parcels: number;
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
  // County "Damaged/Destroyed Parcels" scope: Red- or Yellow-tagged in the
  // post-fire Safety Assessment. Drives the funnel's "Damaged or destroyed"
  // baseline filter (== summary.bsd_red_or_yellow_count).
  bsd_red_or_yellow: boolean;
  // Rebuild-progress: a boolean per milestone, true when the parcel reached
  // that stage or beyond (for "at or past stage N" map filtering), plus
  // `rebuild_stage` (furthest milestone reached, 0–7) for the stage color ramp.
  rebuild_app_received: boolean;
  rebuild_zoning_cleared: boolean;
  rebuild_plans_received: boolean;
  rebuild_plans_approved: boolean;
  rebuild_permit_issued: boolean;
  rebuild_in_construction: boolean;
  rebuild_construction_completed: boolean;
  rebuild_stage: number;
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
