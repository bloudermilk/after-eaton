// Centralized URLs and paths so they're easy to retarget.

export const REPO_URL = "https://github.com/bloudermilk/after-eaton";

const baseUrl = import.meta.env.BASE_URL;

export const DATA_PATHS = {
  summary: `${baseUrl}data/summary.json`,
  qcReport: `${baseUrl}data/qc-report.json`,
  parcelsCsv: `${baseUrl}data/parcels.csv`,
} as const;

// Frontend treats data older than this as stale and shows a banner.
export const STALE_AFTER_MS = 96 * 60 * 60 * 1000; // 96 hours
