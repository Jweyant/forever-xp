// Site-wide settings. Change links here, not in pages.
export const SITE = {
  name: "Forever XP",
  tagline: "Routes, quests, gear and talents for WoW Forever",
  discord: "https://discord.gg/z8DfMK7Uw",
  repo: "https://github.com/Jweyant/forever-xp",
  curseforge: "", // fill in once the ForeverScout project is live on CurseForge
  launch: "2026-11-04",
  // Comments on quest, item and guide pages use giscus (GitHub Discussions). Leave repoId empty
  // to keep comments off. Get the IDs from https://giscus.app after enabling Discussions.
  giscus: { repo: "Jweyant/forever-xp", repoId: "", category: "Site comments", categoryId: "" },
};
export const ICON = (n: string, size: 18 | 36 | 56 = 56) => `https://render.worldofwarcraft.com/us/icons/${size}/${n}.jpg`;
export const QUALITY = ["poor", "common", "uncommon", "rare", "epic", "legendary", "artifact"] as const;
export const CLASS_COLOR: Record<string, string> = {
  warrior: "#c79c6e", paladin: "#f58cba", hunter: "#abd473", rogue: "#fff569", priest: "#ffffff",
  shaman: "#0070de", mage: "#69ccf0", warlock: "#9482c9", druid: "#ff7d0a",
};
