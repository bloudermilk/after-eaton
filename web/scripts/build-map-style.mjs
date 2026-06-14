// Builds web/public/map-style.json: a warm, on-brand recolor of OpenFreeMap's
// "positron" basemap.
//
// Everything OpenFreeMap hosts for free is kept verbatim — the vector tiles
// (`sources`), the `sprite`, and the `glyphs` — so the only difference from
// upstream positron is the layer colors, which are swapped for warm equivalents
// of the design tokens in src/styles/tokens.css.
//
// Run with `npm run map:build-style`. Re-run whenever the upstream positron
// style changes or the palette below is tweaked.

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const POSITRON_URL = "https://tiles.openfreemap.org/styles/positron";

const here = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(here, "..", "public", "map-style.json");

// --- Palette ---------------------------------------------------------------
// Warm equivalents of every flat color positron uses, derived from the design
// tokens in src/styles/tokens.css (parchment paper, sage deodara greens, sand
// alluvial, muted lupin water). Poppy is deliberately reserved for the parcel
// dots painted on top, so the basemap stays calm beneath them.
//
// Keyed by the EXACT upstream color string. Halo colors are mapped separately
// (see HALO) because positron reuses "#fff" for both road fills and label
// halos, which want different warm targets.
const BASE = {
  "rgb(242,243,240)": "#f2ebdd", // background + piers  → paper
  "rgb(234, 234, 230)": "#ece2d0", // residential landuse → paper-deep
  "rgb(230, 233, 229)": "#dde3d0", // park                → light sage
  "rgb(220,224,220)": "#d3dcc4", // wood                → sage
  "hsl(0,0%,98%)": "#f8f3ea", // glacier / ice shelf → warm near-white
  "rgb(194, 200, 202)": "#b6c3cd", // water               → dusty blue
  "hsl(195,17%,78%)": "#b9c4cd", // waterway line       → dusty blue
  "rgb(234, 234, 229)": "#e7dcc8", // building fill       → alluvial-soft
  "rgb(219, 219, 218)": "#d8cab2", // building outline    → alluvial
  "rgb(213, 213, 213)": "#d9cdb6", // road casings        → sand
  "rgb(234,234,234)": "#ece1ce", // tunnel inner / path → warm tan
  "rgb(234, 234, 234)": "#e6dac6", // highway path        → warm tan
  "hsl(0,0%,88%)": "#e6dac6", // minor roads, taxiway→ warm tan
  "#fff": "#fbf6ec", // road inner          → warm white
  "hsla(0,0%,85%,0.69)": "rgba(216,202,178,0.69)", // major subtle
  "hsla(0,0%,85%,0.53)": "rgba(216,202,178,0.53)", // motorway subtle
  "rgba(255, 255, 255, 1)": "#faf4ea", // aeroway area/runway → warm white
  "#dddddd": "#d6cab3", // railway             → sand
  "#fafafa": "#f6f0e5", // railway dashline    → warm white
  "hsl(0,0%,70%)": "#a99e88", // boundaries          → warm gray
  // Label text colors → warm ink scale
  "#000": "#2a2a2a", // place names         → ink
  "#333": "#3a3631", // secondary places    → warm dark
  "#666": "#6f675b", // road / airport text → ink-muted
  "hsl(0,0%,66%)": "#9aa0a6", // waterway label text → muted blue-gray
  "hsl(30,0%,62%)": "#8a8073", // path name text      → warm gray
  "#495e91": "#565f86", // water name text     → muted indigo (lupin)
};

// Halo colors → warm parchment so labels read as if printed on the page.
const HALO = {
  "#fff": "#f4ede0",
  "#ffffff": "#f4ede0",
  "#f8f4f0": "#f3ecde",
  "rgba(255,255,255,0.7)": "rgba(244,237,224,0.78)",
};

// Recolor a paint value in place. `isHalo` selects the parchment halo map.
// Recurses through expression arrays so colors nested in interpolate/step/case
// expressions get remapped too.
function recolor(value, isHalo) {
  const map = isHalo ? HALO : BASE;
  if (typeof value === "string") return map[value] ?? value;
  if (Array.isArray(value)) return value.map((v) => recolor(v, isHalo));
  return value;
}

function transformPaint(paint) {
  if (!paint) return paint;
  const out = {};
  for (const [key, val] of Object.entries(paint)) {
    out[key] = key.includes("color") ? recolor(val, key.includes("halo")) : val;
  }
  return out;
}

const res = await fetch(POSITRON_URL);
if (!res.ok) throw new Error(`Failed to fetch positron style: ${res.status}`);
const positron = await res.json();

const style = {
  version: positron.version,
  name: "Altadata — warm positron",
  // Keep OpenFreeMap's free hosted tiles, sprites, and glyphs verbatim.
  sources: positron.sources,
  sprite: positron.sprite,
  glyphs: positron.glyphs,
  layers: positron.layers.map((layer) => {
    const next = { ...layer };
    if (next.paint) next.paint = transformPaint(next.paint);
    return next;
  }),
};

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, JSON.stringify(style, null, 2) + "\n");
console.log(`map:build-style → ${outPath} (${style.layers.length} layers)`);
