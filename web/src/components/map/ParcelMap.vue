<script setup lang="ts">
import "maplibre-gl/dist/maplibre-gl.css";

import {
  AttributionControl,
  type GeoJSONSource,
  type GeoJSONSourceSpecification,
  type LngLatBoundsLike,
  Map as MaplibreMap,
  NavigationControl,
} from "maplibre-gl";
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";

import { ALTADENA_BOUNDS, BASEMAP_STYLE_URL } from "@/constants";
import { getMetric, metricColor, metricFilter, NEUTRAL_DOT } from "@/metrics";
import type { ParcelFeatureCollection } from "@/types";

const props = defineProps<{
  geojson: ParcelFeatureCollection | null;
  activeMetricId: string | null;
  activeBucket: string | null;
}>();

const SOURCE_ID = "parcels";
const LAYER_ID = "parcels-circles";

const container = ref<HTMLDivElement | null>(null);
// shallowRef: the maplibre Map is imperative — never wrap it in a deep proxy.
const map = shallowRef<MaplibreMap | null>(null);
const ready = shallowRef(false);

onMounted(() => {
  if (!container.value) return;
  const m = new MaplibreMap({
    container: container.value,
    style: BASEMAP_STYLE_URL,
    bounds: ALTADENA_BOUNDS as LngLatBoundsLike,
    fitBoundsOptions: { padding: 40 },
    // Render our own AttributionControl so it starts collapsed.
    attributionControl: false,
  });
  m.addControl(new NavigationControl({ showZoom: true, showCompass: true }), "top-right");
  m.addControl(new AttributionControl({ compact: true }), "bottom-right");
  m.on("load", () => {
    ready.value = true;
    applyData();
    applySelection();
  });
  map.value = m;
});

onBeforeUnmount(() => {
  map.value?.remove();
  map.value = null;
  ready.value = false;
});

/** Add (or refresh) the parcel source + circle layer once the style is ready. */
function applyData(): void {
  const m = map.value;
  if (!m || !ready.value || !props.geojson) return;
  const data = props.geojson as unknown as GeoJSONSourceSpecification["data"];
  const existing = m.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (existing) {
    existing.setData(data);
    return;
  }
  m.addSource(SOURCE_ID, { type: "geojson", data });
  m.addLayer({
    id: LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1.5, 13, 2.6, 16, 5],
      "circle-color": NEUTRAL_DOT,
      "circle-opacity": 0.85,
    },
  });
  applySelection();
}

/** Reflect the active metric/bucket selection into the layer's filter + color. */
function applySelection(): void {
  const m = map.value;
  if (!m || !ready.value || !m.getLayer(LAYER_ID)) return;
  const metric = getMetric(props.activeMetricId);
  if (!metric) {
    // Default state: every parcel, one neutral color.
    m.setFilter(LAYER_ID, null);
    m.setPaintProperty(LAYER_ID, "circle-color", NEUTRAL_DOT);
    return;
  }
  m.setFilter(LAYER_ID, metricFilter(metric, props.activeBucket));
  m.setPaintProperty(LAYER_ID, "circle-color", metricColor(metric));
}

watch(() => props.geojson, applyData);
watch(() => [props.activeMetricId, props.activeBucket], applySelection);
</script>

<template>
  <div ref="container" class="parcel-map" />
</template>

<style scoped>
.parcel-map {
  width: 100%;
  height: 100%;
}
/* maplibre injects controls/canvas; ensure they aren't clipped oddly. */
.parcel-map :deep(.maplibregl-canvas) {
  outline: none;
}
</style>
