// Centralized URLs and paths so they're easy to retarget.

export const REPO_URL = "https://github.com/bloudermilk/after-eaton";

const baseUrl = import.meta.env.BASE_URL;

export const DATA_PATHS = {
  summary: `${baseUrl}data/summary.json`,
  qcReport: `${baseUrl}data/qc-report.json`,
  parcelsCsv: `${baseUrl}data/parcels.csv`,
  parcelsCompact: `${baseUrl}data/parcels-compact.geojson`,
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

// Free vector basemap (no API key). See https://openfreemap.org/.
export const BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
