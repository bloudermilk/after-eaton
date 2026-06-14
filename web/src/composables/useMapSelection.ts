import { readonly, ref } from "vue";

// Module-scoped so the cards rail and the map share one selection. At most one
// metric is active at a time; within it, at most one bucket.
const activeMetricId = ref<string | null>(null);
const activeBucketKey = ref<string | null>(null);

/** Toggle a metric on/off. Activating a metric clears any bucket selection. */
function toggleMetric(id: string): void {
  if (activeMetricId.value === id) {
    activeMetricId.value = null;
    activeBucketKey.value = null;
  } else {
    activeMetricId.value = id;
    activeBucketKey.value = null;
  }
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

function clear(): void {
  activeMetricId.value = null;
  activeBucketKey.value = null;
}

export function useMapSelection() {
  return {
    activeMetricId: readonly(activeMetricId),
    activeBucketKey: readonly(activeBucketKey),
    toggleMetric,
    selectBucket,
    clear,
  };
}
