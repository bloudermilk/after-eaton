<script setup lang="ts">
import "maplibre-gl/dist/maplibre-gl.css";

import {
  AttributionControl,
  type GeoJSONSource,
  type GeoJSONSourceSpecification,
  type LngLatBoundsLike,
  Map as MaplibreMap,
  NavigationControl,
  Popup,
} from "maplibre-gl";
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";

import { ALTADENA_BOUNDS, BASEMAP_STYLE_URL } from "@/constants";
import { buildMapColor, buildMapFilter, type FilterSet, getMetric, NEUTRAL_DOT } from "@/metrics";
import type { ParcelFeatureCollection, ParcelProperties } from "@/types";

import { buildPopupContent } from "./popupContent";

const props = defineProps<{
  geojson: ParcelFeatureCollection | null;
  // Drives the dot color ramp and the default (no-bucket) view.
  focusedMetricId: string | null;
  // metricId -> selected bucket keys (OR within a metric, AND across metrics).
  filterSet: FilterSet;
}>();

const SOURCE_ID = "parcels";
const LAYER_ID = "parcels-circles";

const container = ref<HTMLDivElement | null>(null);
// shallowRef: the maplibre Map is imperative — never wrap it in a deep proxy.
const map = shallowRef<MaplibreMap | null>(null);
// One reused popup, opened on marker click (see registerInteractions).
const popup = shallowRef<Popup | null>(null);
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
  popup.value = new Popup({
    closeButton: true,
    closeOnClick: true,
    maxWidth: "320px",
    className: "parcel-popup",
  });
  m.on("load", () => {
    ready.value = true;
    applyData();
    applySelection();
    registerInteractions(m);
  });
  map.value = m;
});

onBeforeUnmount(() => {
  popup.value?.remove();
  popup.value = null;
  map.value?.remove();
  map.value = null;
  ready.value = false;
});

/** Open the parcel popup on click; show a pointer over markers. Handlers are
 * scoped to the parcel layer, so they only fire for markers currently rendered
 * (i.e. passing the active metric filter) — exactly the "visible markers". */
function registerInteractions(m: MaplibreMap): void {
  m.on("click", LAYER_ID, (e) => {
    const feature = e.features?.[0];
    const p = popup.value;
    if (!feature || !p) return;
    const props = feature.properties as unknown as ParcelProperties;
    // Anchor on the marker's own point so the tip lands on the dot.
    const coords: [number, number] =
      feature.geometry.type === "Point"
        ? [feature.geometry.coordinates[0], feature.geometry.coordinates[1]]
        : [e.lngLat.lng, e.lngLat.lat];
    p.setLngLat(coords).setDOMContent(buildPopupContent(props)).addTo(m);
  });
  m.on("mouseenter", LAYER_ID, () => {
    m.getCanvas().style.cursor = "pointer";
  });
  m.on("mouseleave", LAYER_ID, () => {
    m.getCanvas().style.cursor = "";
  });
}

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

/** Reflect the focused metric + filter set into the layer's filter + color. */
function applySelection(): void {
  const m = map.value;
  if (!m || !ready.value || !m.getLayer(LAYER_ID)) return;
  // A parcel hidden by the new filter shouldn't keep its popup open.
  popup.value?.remove();
  const metric = getMetric(props.focusedMetricId);
  if (!metric) {
    // Default state: every parcel, one neutral color.
    m.setFilter(LAYER_ID, null);
    m.setPaintProperty(LAYER_ID, "circle-color", NEUTRAL_DOT);
    return;
  }
  // The filter ANDs each metric's buckets together; the color stays the focused
  // metric's ramp until the set spans ≥2 metrics, then a single highlight.
  m.setFilter(LAYER_ID, buildMapFilter(metric, props.filterSet));
  m.setPaintProperty(LAYER_ID, "circle-color", buildMapColor(metric, props.filterSet));
}

watch(() => props.geojson, applyData);
watch(() => [props.focusedMetricId, props.filterSet], applySelection, { deep: true });
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

<!-- Un-scoped: maplibre injects the popup outside this component's DOM, so a
     scoped block can't reach it. Everything is namespaced under .parcel-popup
     (the popup's className) so nothing leaks to the rest of the app. -->
<style>
.parcel-popup .maplibregl-popup-content {
  background: var(--color-paper);
  color: var(--color-ink);
  font-family: var(--font-sans);
  border: 1px solid var(--color-rule);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card);
  padding: var(--space-4);
}
.parcel-popup .maplibregl-popup-tip {
  border-top-color: var(--color-paper);
  border-bottom-color: var(--color-paper);
}
.parcel-popup .maplibregl-popup-close-button {
  color: var(--color-ink-muted);
  font-size: var(--fs-md);
  padding-right: var(--space-2);
}
.parcel-popup__title {
  font-weight: 600;
  font-size: var(--fs-sm);
  line-height: 1.3;
  padding-right: var(--space-4);
}
.parcel-popup__ain {
  margin-top: var(--space-1);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--color-ink-muted);
}
.parcel-popup__grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-3);
  margin: var(--space-3) 0 0;
  font-size: var(--fs-xs);
}
.parcel-popup__grid dt {
  color: var(--color-ink-muted);
  white-space: nowrap;
}
.parcel-popup__grid dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.parcel-popup__link {
  display: inline-block;
  margin-top: var(--space-3);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--color-poppy);
  text-decoration: none;
}
.parcel-popup__link:hover {
  text-decoration: underline;
}
</style>
