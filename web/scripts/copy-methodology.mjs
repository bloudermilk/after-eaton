// Copies the repo's METHODOLOGY.md into src/assets so the SPA can import
// it via Vite's `?raw` loader without reaching outside the web/ tree.
// Runs from package.json's prebuild/predev hooks.

import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "..", "..", "METHODOLOGY.md");
const dst = resolve(here, "..", "src", "assets", "methodology.md");

if (!existsSync(src)) {
  console.error(`copy-methodology: source not found at ${src}`);
  process.exit(1);
}

mkdirSync(dirname(dst), { recursive: true });
copyFileSync(src, dst);
console.log(`copy-methodology: ${src} → ${dst}`);
