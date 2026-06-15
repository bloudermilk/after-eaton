// Centralized URLs and paths so they're easy to retarget.

export const REPO_URL = "https://github.com/bloudermilk/after-eaton";

const baseUrl = import.meta.env.BASE_URL;

export const DATA_PATHS = {
  summary: `${baseUrl}data/summary.json`,
  qcReport: `${baseUrl}data/qc-report.json`,
  parcelsCsv: `${baseUrl}data/parcels.csv`,
  parcelsCompact: `${baseUrl}data/parcels-compact.geojson`,
  firePerimeter: `${baseUrl}data/fire-perimeter.geojson`,
} as const;

// Frontend treats data older than this as stale and shows a banner.
export const STALE_AFTER_MS = 96 * 60 * 60 * 1000; // 96 hours

// Default map viewport: a hardcoded bounding box covering all Altadena
// parcels, [[west, south], [east, north]] in WGS84 (matches the parcel
// envelope produced by the pipeline). Used to fit the map on load.
export const ALTADENA_BOUNDS: [[number, number], [number, number]] = [
  [-118.1644, 34.1676],
  [-118.095, 34.2146],
];

// Our warm, on-brand recolor of OpenFreeMap's positron basemap. Self-hosted
// from public/ as a static style.json, while the vector/raster tiles, sprites,
// and glyphs all stay on OpenFreeMap's free host. Rebuild with
// `npm run map:build-style`; see scripts/build-map-style.mjs.
export const BASEMAP_STYLE_URL = `${baseUrl}map-style.json`;

// Public EPIC-LA (LA County Electronic Permitting & Inspections) Self-Service
// search. We deep-link to the search results for a parcel's 10-digit AIN rather
// than a specific case, so the link works for every parcel (and surfaces all of
// its cases) without the pipeline carrying case numbers. The `st` (search term)
// param is the AIN; the rest mirror the portal's default search query.
const EPICLA_SEARCH_BASE = "https://epicla.lacounty.gov/energov_prod/SelfService/#/search";

export function epiclaSearchUrl(ain: string): string {
  return `${EPICLA_SEARCH_BASE}?m=1&fm=1&ps=10&pn=1&em=true&st=${encodeURIComponent(ain)}`;
}
