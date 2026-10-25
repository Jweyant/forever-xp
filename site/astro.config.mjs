import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://forever-xp.com",
  trailingSlash: "ignore",
  build: { format: "directory" },
});
