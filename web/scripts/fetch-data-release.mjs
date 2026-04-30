// Downloads the data assets from the GitHub `data-latest` release into
// web/public/data/. Mirrors what CI does. Requires `gh` to be installed
// and authenticated. Run with `npm run data:fetch-release`.

import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dstDir = resolve(here, "..", "public", "data");
mkdirSync(dstDir, { recursive: true });

const args = [
  "release",
  "download",
  "data-latest",
  "--pattern",
  "summary.json",
  "--pattern",
  "qc-report.json",
  "--pattern",
  "parcels.csv",
  "--dir",
  dstDir,
  "--clobber",
];

try {
  execFileSync("gh", args, { stdio: "inherit" });
  console.log(`fetch-data-release: downloaded to ${dstDir}`);
} catch (err) {
  console.error(
    `fetch-data-release: failed. Is the gh CLI installed and authenticated? (${err.message})`,
  );
  process.exit(1);
}
