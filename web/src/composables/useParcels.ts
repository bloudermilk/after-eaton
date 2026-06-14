import { readonly, shallowRef } from "vue";

import { DATA_PATHS } from "@/constants";
import type { ParcelFeatureCollection } from "@/types";

// shallowRef: the feature collection is large (~9.5k features) and never
// mutated, so we deliberately avoid Vue's deep reactivity proxy.
const parcels = shallowRef<ParcelFeatureCollection | null>(null);
const error = shallowRef<Error | null>(null);
const loading = shallowRef(false);

let inflight: Promise<void> | null = null;

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await fetch(DATA_PATHS.parcelsCompact, { cache: "no-cache" });
    if (!res.ok) {
      throw new Error(
        `Failed to fetch ${DATA_PATHS.parcelsCompact}: ${res.status} ${res.statusText}`,
      );
    }
    parcels.value = (await res.json()) as ParcelFeatureCollection;
  } catch (err) {
    error.value = err instanceof Error ? err : new Error(String(err));
  } finally {
    loading.value = false;
  }
}

/**
 * Lazily loads the compact parcel GeoJSON used by the map. The fetch fires on
 * first call (e.g. when the map view mounts) and is shared across callers, so
 * routes that never show the map don't pay for the download.
 */
export function useParcels() {
  if (!inflight && !parcels.value && !error.value) {
    inflight = load();
  }
  return {
    // Returned as-is (not deep-readonly) so the large collection passes
    // cleanly to the map's typed prop; callers only ever read it.
    parcels,
    loading: readonly(loading),
    error: readonly(error),
    reload: () => {
      inflight = load();
      return inflight;
    },
  };
}
