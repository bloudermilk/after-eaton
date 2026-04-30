// Copies pipeline outputs from ../data/ into web/public/data/ for use by
// the dev server. Run with `npm run data:fetch-local`.

import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ASSETS = ["summary.json", "qc-report.json", "parcels.csv"];

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(here, "..", "..", "data");
const dstDir = resolve(here, "..", "public", "data");

if (!existsSync(srcDir)) {
  console.error(`fetch-data-local: ${srcDir} does not exist. Run the pipeline first.`);
  process.exit(1);
}
mkdirSync(dstDir, { recursive: true });

const present = new Set(readdirSync(srcDir));
const missing = ASSETS.filter((a) => !present.has(a));
if (missing.length) {
  console.error(`fetch-data-local: missing in ${srcDir}: ${missing.join(", ")}`);
  process.exit(1);
}

for (const asset of ASSETS) {
  copyFileSync(resolve(srcDir, asset), resolve(dstDir, asset));
  console.log(`fetch-data-local: ${asset} → public/data/`);
}
