// Shapes mirror the Python pipeline outputs:
// - SummaryResult & RegionCounts: pipeline/src/after_eaton/processing/aggregate.py
// - QcReport, RecordWarning, ThresholdCheck: pipeline/src/after_eaton/qc/{report,aggregate,per_record}.py

export interface Summary {
  generated_at: string;
  total_parcels: number;
  damaged_parcels: number;
  destroyed_parcels: number;
  bsd_red_count: number;
  bsd_yellow_count: number;
  bsd_green_count: number;
  bsd_red_or_yellow_count: number;
  no_permit_count: number;
  permit_in_review_count: number;
  permit_issued_count: number;
  construction_count: number;
  completed_count: number;
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
  adu_added_1_count: number;
  adu_added_2_count: number;
  adu_added_3_plus_count: number;
  dwelling_rebuild_count: number;
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
