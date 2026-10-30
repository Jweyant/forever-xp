// Copy the pinned npm dependencies into public/vendor, where index.html loads them from.
// Run after npm ci, before wrangler deploy (npm run vendor).
import { copyFileSync, mkdirSync } from "node:fs";

const FILES = {
  "node_modules/jquery/dist/jquery.min.js": "public/vendor/jquery.min.js",
  "node_modules/wow-model-viewer/index.js": "public/vendor/wow-model-viewer/index.js",
  "node_modules/wow-model-viewer/wow_model_viewer.js": "public/vendor/wow-model-viewer/wow_model_viewer.js",
  "node_modules/wow-model-viewer/character_modeling.js": "public/vendor/wow-model-viewer/character_modeling.js",
  "node_modules/wow-model-viewer/setup.js": "public/vendor/wow-model-viewer/setup.js",
};
mkdirSync("public/vendor/wow-model-viewer", { recursive: true });
for (const [from, to] of Object.entries(FILES)) copyFileSync(from, to);
console.log(`vendor: copied ${Object.keys(FILES).length} files into public/vendor`);
