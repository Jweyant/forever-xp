// Lets Node import the site's TypeScript, which imports JSON the way Astro allows (no import
// attribute). Registers a loader that treats .json files as JSON modules.
import { register } from "node:module";
register(new URL("./node-json-loader.mjs", import.meta.url));
