import { shallowRef } from "vue";

import { DATA_PATHS } from "@/constants";
import type { FirePerimeterFeatureCollection } from "@/types";

// The Eaton Fire burn outline is map-only decoration, so this loads
// independently of the parcels and stays null until (and unless) the fetch
// succeeds. shallowRef: the collection is never mutated.
const perimeter = shallowRef<FirePerimeterFeatureCollection | null>(null);

let inflight: Promise<void> | null = null;

async function load(): Promise<void> {
  try {
    const res = await fetch(DATA_PATHS.firePerimeter, { cache: "no-cache" });
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }
    perimeter.value = (await res.json()) as FirePerimeterFeatureCollection;
  } catch (err) {
    // Fail soft: the outline is context, not core data. A missing or malformed
    // asset (e.g. before the first pipeline run publishes it) must never break
    // the map — we just don't draw the outline.
    console.warn(`Fire perimeter not loaded (${DATA_PATHS.firePerimeter}):`, err);
    perimeter.value = null;
  }
}

/**
 * Lazily loads the dissolved fire-perimeter GeoJSON used by the map. The fetch
 * fires on first call and is shared across callers; failures are swallowed so a
 * missing outline never disrupts the map.
 */
export function useFirePerimeter() {
  if (!inflight && !perimeter.value) {
    inflight = load();
  }
  return { perimeter };
}
