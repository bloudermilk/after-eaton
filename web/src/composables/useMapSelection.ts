import { computed, readonly, ref } from "vue";

import { METRICS } from "../metrics";

// The metric focused on first load. One metric is always focused (it drives the
// map's color ramp and which card is "primary"), so this is the metric a user
// can never fully clear out of. Always the first metric in the list, so the
// default tracks the rail's ordering.
const DEFAULT_METRIC_ID = METRICS[0].id;

// Module-scoped so the cards rail and the map share one selection.
//
// `filterSet` maps a metricId to the bucket keys selected within it. Buckets in
// the same metric combine with OR; different metrics combine with AND — e.g.
// `{ lfl: ["lfl"], new_construction: ["plans_received", "plans_approved"] }`
// means "Like-for-like AND (plans received OR plans approved)". An empty set is
// the default "whole metric" view (every bucket of the focused metric shown).
//
// `focusedMetricId` is always set: it picks the color ramp and the primary card,
// and is the metric a plain bucket/heading click resets to.
const filterSet = ref<Record<string, string[]>>({});
const focusedMetricId = ref<string>(DEFAULT_METRIC_ID);

/** True once any metric has at least one bucket selected. */
const isFilterSetActive = computed(() =>
  Object.values(filterSet.value).some((keys) => keys.length > 0),
);

/** The selected bucket keys for a metric (empty array if none). */
function selectedBucketsFor(metricId: string): string[] {
  return filterSet.value[metricId] ?? [];
}

/** True when the whole set is exactly `{ [metricId]: [key] }` and nothing else. */
function isOnlySelection(metricId: string, key: string): boolean {
  const active = Object.entries(filterSet.value).filter(([, keys]) => keys.length > 0);
  const only = active.length === 1 ? active[0] : undefined;
  return only !== undefined && only[0] === metricId && only[1].length === 1 && only[1][0] === key;
}

/**
 * Select a bucket within a metric.
 *
 * Plain (additive=false): single-select, replacing the whole set with just this
 * bucket — or clearing it if this bucket was already the lone selection (the
 * familiar toggle-off back to the whole-metric view).
 *
 * Additive (Shift): toggle this bucket inside the set, building a multi-bucket /
 * multi-metric filter. Removing a metric's last bucket drops it from the set.
 */
function selectBucket(metricId: string, key: string, additive = false): void {
  if (!additive) {
    filterSet.value = isOnlySelection(metricId, key) ? {} : { [metricId]: [key] };
    focusedMetricId.value = metricId;
    return;
  }

  const current = filterSet.value[metricId] ?? [];
  const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];

  const updated = { ...filterSet.value };
  if (next.length > 0) {
    updated[metricId] = next;
  } else {
    delete updated[metricId];
  }
  filterSet.value = updated;

  // Keep the focus on the touched metric while it still has buckets; otherwise
  // hand it to a metric still in the set (so its ramp colors the map when the
  // set collapses to one metric), falling back to the touched metric when empty.
  if (next.length > 0) {
    focusedMetricId.value = metricId;
  } else {
    const remaining = Object.keys(updated);
    focusedMetricId.value = remaining[0] ?? metricId;
  }
}

/**
 * Activate a metric from its card heading.
 *
 * Plain: clear the filter set and focus this metric (also the path that resets a
 * multi-metric set back to a single metric). Shift while a set is active is a
 * deliberate no-op — Shift only ever adds buckets, never metrics.
 */
function toggleMetric(metricId: string, additive = false): void {
  if (additive && isFilterSetActive.value) return;
  filterSet.value = {};
  focusedMetricId.value = metricId;
}

export function useMapSelection() {
  return {
    filterSet: readonly(filterSet),
    focusedMetricId: readonly(focusedMetricId),
    isFilterSetActive,
    selectedBucketsFor,
    toggleMetric,
    selectBucket,
  };
}
