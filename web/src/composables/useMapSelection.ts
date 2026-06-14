import { readonly, ref } from "vue";

// The metric selected on first load. Exactly one metric is always active (see
// toggleMetric), so this is also the metric a user can never fully deselect.
const DEFAULT_METRIC_ID = "rebuild_progress";

// Module-scoped so the cards rail and the map share one selection. Exactly one
// metric is active at a time; within it, at most one bucket.
const activeMetricId = ref<string | null>(DEFAULT_METRIC_ID);
const activeBucketKey = ref<string | null>(null);

/**
 * Activate a metric. Exactly one metric is always selected, so tapping the
 * already-active card's header does not deselect it — it just clears any
 * bucket focus. Switching to a different metric clears the bucket too.
 */
function toggleMetric(id: string): void {
  if (activeMetricId.value === id) {
    activeBucketKey.value = null;
    return;
  }
  activeMetricId.value = id;
  activeBucketKey.value = null;
}

/**
 * Select a bucket within a metric. Activates the metric if it wasn't already,
 * and toggles the bucket off if it was already the selected one.
 */
function selectBucket(id: string, key: string): void {
  if (activeMetricId.value !== id) {
    activeMetricId.value = id;
    activeBucketKey.value = key;
    return;
  }
  activeBucketKey.value = activeBucketKey.value === key ? null : key;
}

export function useMapSelection() {
  return {
    activeMetricId: readonly(activeMetricId),
    activeBucketKey: readonly(activeBucketKey),
    toggleMetric,
    selectBucket,
  };
}
