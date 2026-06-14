// Single source of truth for the four metrics, shared by the stat cards and
// the map. Bucket keys mirror the per-parcel classifiers in the pipeline
// (processing/aggregate.py) so a parcel's `*_bucket` property on
// parcels-compact.geojson lines up exactly with the summary.json counts the
// cards display. Colors live here as hex so the cards and the maplibre paint
// expressions never drift.

import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";

import type { Summary } from "@/types";

export type MetricId = "rebuild_progress" | "sfr_size" | "lfl" | "adu" | "density";
export type ChartKind = "vbars" | "donut" | "dist" | "bignumber" | "stagelist";

// Only the numeric (count) fields of Summary are valid card sources.
type NumberKeys<T> = { [K in keyof T]: T[K] extends number ? K : never }[keyof T];
export type SummaryCountKey = NumberKeys<Summary>;

export interface MetricBucket {
  /** Matches the parcel's bucket value resolved by `valueExpr`. */
  key: string;
  label: string;
  /** Hex color, shared by the card chart and the map. */
  color: string;
  /** Count field on summary.json that the card reads for this bucket. */
  summaryKey: SummaryCountKey;
  /**
   * "stage" metrics only: the milestone's ordinal (0–7). It drives the color
   * ramp (metricColorStage) and is the exact value the map filters
   * `rebuild_stage` against when this bucket is selected (metricFilterStage).
   */
  stage?: number;
}

export interface MetricDef {
  id: MetricId;
  title: string;
  subtitle: string;
  chart: ChartKind;
  /**
   * How this metric paints/filters the map. "bucket" (default): each parcel
   * resolves to exactly one bucket via `valueExpr`. "stage": the map colors
   * every damaged parcel by `rebuild_stage` (the furthest milestone it
   * reached); selecting a bucket filters to the parcels currently AT that
   * stage, so the lit dots share one color (see metricColorStage /
   * metricFilterStage). The card list, by contrast, stays cumulative.
   */
  mapMode?: "bucket" | "stage";
  /** maplibre accessor resolving a parcel feature to its bucket key (a string). */
  valueExpr: ExpressionSpecification;
  buckets: MetricBucket[];
}

// Palette mirrors styles/tokens.css.
const C = {
  poppy: "#e96b27",
  poppySoft: "#f0894d",
  lupin: "#5c5588",
  lupinSoft: "#8e88b4",
  alluvial: "#c8b594",
  liveOak: "#2f4a33",
  liveOakSoft: "#6f9a73",
  deodara: "#5e7a6e",
  deodaraSoft: "#8fa9a0",
} as const;

/** Default dot color when no metric is active (also the match fallback). */
export const NEUTRAL_DOT = C.alluvial;

// Tiny helpers so the literal expressions type-check cleanly against the
// recursive style-spec tuple types.
const get = (prop: string): ExpressionSpecification =>
  ["get", prop] as unknown as ExpressionSpecification;
// adds_sb9 / adds_sb1123 are booleans; resolve each parcel to its state-bill
// pathway. The two are mutually exclusive in the pipeline (most-recent wins),
// so a parcel is at most one of "sb9" / "sb1123"; everything else is "none".
const densityValue = [
  "case",
  ["get", "adds_sb9"],
  "sb9",
  ["get", "adds_sb1123"],
  "sb1123",
  "none",
] as unknown as ExpressionSpecification;

export const METRICS: MetricDef[] = [
  {
    id: "rebuild_progress",
    title: "Rebuild progress",
    subtitle: "Permitting milestones reached",
    chart: "stagelist",
    mapMode: "stage",
    // Unused in stage mode (the stage helpers read `rebuild_stage` directly)
    // but kept non-null to satisfy the type.
    valueExpr: get("rebuild_stage"),
    // Rebuild funnel. The first bucket, "Damaged or destroyed" (stage 0), is the
    // baseline/denominator — LA County's published "Damaged/Destroyed Parcels"
    // scope (Red+Yellow safety tags); it reads 100% in the card. The seven
    // milestone buckets below come from the `*_parcels` summary fields, which are
    // MONOTONIC: a parcel is counted at every stage up to the furthest it reached,
    // so the rows strictly decline (this differs from LA County's non-monotonic
    // case-level dashboard). `stage` orders the color ramp and is what the map
    // filters `rebuild_stage` against when a row is selected.
    buckets: [
      {
        key: "damaged_destroyed",
        label: "Damaged or destroyed",
        color: NEUTRAL_DOT,
        summaryKey: "bsd_red_or_yellow_count",
        stage: 0,
      },
      {
        key: "app_received",
        label: "Application received",
        color: C.deodaraSoft,
        summaryKey: "rebuild_app_received_parcels",
        stage: 1,
      },
      {
        key: "zoning_cleared",
        label: "Zoning cleared",
        color: C.deodara,
        summaryKey: "rebuild_zoning_cleared_parcels",
        stage: 2,
      },
      {
        key: "plans_received",
        label: "Plans received",
        color: C.lupinSoft,
        summaryKey: "rebuild_plans_received_parcels",
        stage: 3,
      },
      {
        key: "plans_approved",
        label: "Plans approved",
        color: C.lupin,
        summaryKey: "rebuild_plans_approved_parcels",
        stage: 4,
      },
      {
        key: "permit_issued",
        label: "Permits issued",
        color: C.liveOak,
        summaryKey: "rebuild_permit_issued_parcels",
        stage: 5,
      },
      {
        key: "in_construction",
        label: "In construction",
        color: C.poppySoft,
        summaryKey: "rebuild_in_construction_parcels",
        stage: 6,
      },
      {
        key: "construction_completed",
        label: "Construction completed",
        color: C.poppy,
        summaryKey: "rebuild_construction_completed_parcels",
        stage: 7,
      },
    ],
  },
  {
    id: "sfr_size",
    title: "Relative size",
    subtitle: "Post-fire SFR vs. pre-fire SFR",
    chart: "vbars",
    valueExpr: get("sfr_size_bucket"),
    buckets: [
      {
        key: "smaller_over_30",
        label: ">30% smaller",
        color: C.deodara,
        summaryKey: "sfr_size_pct_smaller_over_30",
      },
      {
        key: "smaller_10_to_30",
        label: "10–30% smaller",
        color: C.deodaraSoft,
        summaryKey: "sfr_size_pct_smaller_10_to_30",
      },
      {
        key: "within_10",
        label: "±10%",
        color: C.alluvial,
        summaryKey: "sfr_size_pct_within_10",
      },
      {
        key: "larger_10_to_30",
        label: "10–30% larger",
        color: C.poppySoft,
        summaryKey: "sfr_size_pct_larger_10_to_30",
      },
      {
        key: "larger_over_30",
        label: ">30% larger",
        color: C.poppy,
        summaryKey: "sfr_size_pct_larger_over_30",
      },
    ],
  },
  {
    id: "lfl",
    title: "Like-for-like",
    subtitle: "Rebuild project type",
    chart: "donut",
    valueExpr: get("lfl_bucket"),
    buckets: [
      { key: "lfl", label: "Like-for-like", color: C.deodara, summaryKey: "lfl_count" },
      { key: "nlfl", label: "Not like-for-like", color: C.poppy, summaryKey: "nlfl_count" },
      {
        key: "unknown",
        label: "Not specified",
        color: C.poppySoft,
        summaryKey: "lfl_unknown_count",
      },
    ],
  },
  {
    id: "adu",
    title: "Accessory dwellings",
    subtitle: "ADUs added relative to pre-fire",
    chart: "dist",
    valueExpr: get("adu_bucket"),
    buckets: [
      { key: "added_1", label: "+1 ADU", color: C.deodara, summaryKey: "adu_added_1_count" },
      { key: "added_2", label: "+2 ADUs", color: C.lupin, summaryKey: "adu_added_2_count" },
      {
        key: "added_3_plus",
        label: "+3 or more",
        color: C.poppy,
        summaryKey: "adu_added_3_plus_count",
      },
    ],
  },
  {
    id: "density",
    title: "Density projects",
    subtitle: "Parcels filing under state bills",
    chart: "bignumber",
    valueExpr: densityValue,
    buckets: [
      { key: "sb9", label: "SB 9", color: C.poppy, summaryKey: "sb9_count" },
      { key: "sb1123", label: "SB 1123", color: C.lupin, summaryKey: "sb1123_count" },
    ],
  },
];

export function getMetric(id: string | null): MetricDef | null {
  if (!id) return null;
  return METRICS.find((m) => m.id === id) ?? null;
}

/**
 * Which parcels are visible for the active metric. With no active bucket, every
 * one of the metric's buckets shows; with one selected, only that bucket.
 * Parcels outside the metric (e.g. `unknown`/`none` keys) are always hidden.
 */
export function metricFilter(metric: MetricDef, activeBucket: string | null): FilterSpecification {
  const keys = activeBucket ? [activeBucket] : metric.buckets.map((b) => b.key);
  return ["in", metric.valueExpr, ["literal", keys]] as unknown as FilterSpecification;
}

/** Color each visible parcel by its bucket, matching the card. */
export function metricColor(metric: MetricDef): ExpressionSpecification {
  const pairs = metric.buckets.flatMap((b) => [b.key, b.color]);
  return ["match", metric.valueExpr, ...pairs, NEUTRAL_DOT] as unknown as ExpressionSpecification;
}

// ----- "stage" map mode (color by current stage, filter to one stage) -------
// A parcel belongs to every stage up to the furthest it reached, so it can't
// resolve to a single bucket key. Instead we color every damaged parcel by
// `rebuild_stage` (furthest milestone reached); selecting a bucket filters to
// the parcels currently AT that stage, so the lit dots share one color. (The
// card list stays cumulative, so its count exceeds the lit dots for a row.)

/** Color each parcel by the furthest milestone it reached (the stage ramp). */
export function metricColorStage(metric: MetricDef): ExpressionSpecification {
  const pairs = metric.buckets.flatMap((b) => [b.stage as number, b.color]);
  return [
    "match",
    ["get", "rebuild_stage"],
    ...pairs,
    NEUTRAL_DOT,
  ] as unknown as ExpressionSpecification;
}

/**
 * The damaged set (`bsd_red_or_yellow`) is the map's universe in stage mode.
 * With no active bucket, show every damaged parcel (colored by its current
 * stage); with one selected, narrow to the parcels currently AT that stage so
 * the lit dots share a single color. The stage-0 "Damaged or destroyed" row
 * therefore means "damaged but not yet started," not every parcel at stage 0.
 */
export function metricFilterStage(
  metric: MetricDef,
  activeBucket: string | null,
): FilterSpecification {
  const damaged = ["==", ["get", "bsd_red_or_yellow"], true];
  if (!activeBucket) {
    return damaged as unknown as FilterSpecification;
  }
  const stage = metric.buckets.find((b) => b.key === activeBucket)?.stage ?? 0;
  return [
    "all",
    damaged,
    ["==", ["get", "rebuild_stage"], stage],
  ] as unknown as FilterSpecification;
}
