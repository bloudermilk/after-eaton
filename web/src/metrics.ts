// Single source of truth for the four metrics, shared by the stat cards and
// the map. Bucket keys mirror the per-parcel classifiers in the pipeline
// (processing/aggregate.py) so a parcel's `*_bucket` property on
// parcels-compact.geojson lines up exactly with the summary.json counts the
// cards display. Colors live here as hex so the cards and the maplibre paint
// expressions never drift.

import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";

import type { Summary } from "@/types";

export type MetricId = "sfr_size" | "lfl" | "adu" | "density";
export type ChartKind = "vbars" | "donut" | "dist" | "bignumber";

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
}

export interface MetricDef {
  id: MetricId;
  title: string;
  subtitle: string;
  chart: ChartKind;
  /** maplibre accessor resolving a parcel feature to its bucket key (a string). */
  valueExpr: ExpressionSpecification;
  buckets: MetricBucket[];
}

// Palette mirrors styles/tokens.css.
const C = {
  poppy: "#e96b27",
  poppySoft: "#f0894d",
  lupin: "#5c5588",
  alluvial: "#c8b594",
  deodara: "#5e7a6e",
  deodaraSoft: "#8fa9a0",
} as const;

/** Default dot color when no metric is active (also the match fallback). */
export const NEUTRAL_DOT = "#9a9488";

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
