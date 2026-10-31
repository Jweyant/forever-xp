import { readFile } from "node:fs/promises";
export async function load(url, context, next) {
  if (url.endsWith(".json")) {
    return { format: "json", shortCircuit: true, source: await readFile(new URL(url)) };
  }
  return next(url, context);
}
