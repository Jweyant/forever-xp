// Classes, specs, goals and starting stat weights for the BIS planner.
// Weights are "value per point". Ratings use Forever's level-60 conversions as seen on items
// that Classic listed as percentages (about 14 crit rating and 10 hit rating per 1%).

export type Stats = Record<string, number>;
export interface Item {
  id: number; name: string; q: number; ilvl: number; req: number; lvl?: number; slot: string; inv: number; type: string; cls: number;
  stats: Stats; weapon?: { min: number; max: number; speed: number; dps: number }; fx?: { on: string; text: string }[];
  classes?: number; side?: "A" | "H"; icon?: string; bop?: 1; pvprank?: number; set?: number;
  src?: { t: string; n?: string; z?: string; lv?: number | number[]; ch?: number; boss?: number; qid?: number; qcls?: number; min?: number }[];
}

export const CRIT_RATING = 14;
export const HIT_RATING = 10;

export const CLASSES: Record<string, { id: number; name: string; bit: number }> = {
  WARRIOR: { id: 1, name: "Warrior", bit: 1 }, PALADIN: { id: 2, name: "Paladin", bit: 2 },
  HUNTER: { id: 3, name: "Hunter", bit: 4 }, ROGUE: { id: 4, name: "Rogue", bit: 8 },
  PRIEST: { id: 5, name: "Priest", bit: 16 }, SHAMAN: { id: 7, name: "Shaman", bit: 64 },
  MAGE: { id: 8, name: "Mage", bit: 128 }, WARLOCK: { id: 9, name: "Warlock", bit: 256 },
  DRUID: { id: 11, name: "Druid", bit: 1024 },
};

type Role = "str" | "agi" | "ranged" | "caster" | "healer" | "tank" | "bear";
export interface Spec { key: string; name: string; role: Role; school?: string[] }
export const SPECS: Record<string, Spec[]> = {
  WARRIOR: [{ key: "arms", name: "Arms", role: "str" }, { key: "fury", name: "Fury", role: "str" }, { key: "prot", name: "Protection", role: "tank" }],
  PALADIN: [{ key: "holy", name: "Holy", role: "healer" }, { key: "prot", name: "Protection", role: "tank" }, { key: "ret", name: "Retribution", role: "str" }],
  HUNTER: [{ key: "bm", name: "Beast Mastery", role: "ranged" }, { key: "mm", name: "Marksmanship", role: "ranged" }, { key: "sv", name: "Survival", role: "ranged" }],
  ROGUE: [{ key: "assa", name: "Assassination", role: "agi" }, { key: "combat", name: "Combat", role: "agi" }, { key: "sub", name: "Subtlety", role: "agi" }],
  PRIEST: [{ key: "disc", name: "Discipline", role: "healer" }, { key: "holy", name: "Holy", role: "healer" }, { key: "shadow", name: "Shadow", role: "caster", school: ["shadow"] }],
  SHAMAN: [{ key: "ele", name: "Elemental", role: "caster", school: ["nature", "fire"] }, { key: "enh", name: "Enhancement", role: "str" }, { key: "resto", name: "Restoration", role: "healer" }],
  MAGE: [{ key: "arcane", name: "Arcane", role: "caster", school: ["arcane"] }, { key: "fire", name: "Fire", role: "caster", school: ["fire"] }, { key: "frost", name: "Frost", role: "caster", school: ["frost"] }],
  WARLOCK: [{ key: "aff", name: "Affliction", role: "caster", school: ["shadow"] }, { key: "demo", name: "Demonology", role: "caster", school: ["shadow"] }, { key: "destro", name: "Destruction", role: "caster", school: ["shadow", "fire"] }],
  DRUID: [{ key: "balance", name: "Balance", role: "caster", school: ["nature", "arcane"] }, { key: "cat", name: "Feral (cat)", role: "agi" }, { key: "bear", name: "Feral (bear)", role: "bear" }, { key: "resto", name: "Restoration", role: "healer" }],
};

export const GOALS = [
  { key: "pve", name: "PvE raids and dungeons" },
  { key: "pvp", name: "PvP" },
  { key: "level", name: "Leveling" },
  { key: "custom", name: "Custom weights" },
] as const;
export type Goal = (typeof GOALS)[number]["key"];

export const STAT_LABEL: Record<string, string> = {
  str: "Strength", agi: "Agility", sta: "Stamina", int: "Intellect", spi: "Spirit", armor: "Armor",
  ap: "Attack power", rap: "Ranged attack power", crit: "Crit rating", hit: "Hit rating", haste: "Haste rating",
  sp: "Spell power", heal: "Healing", mp5: "Mana per 5 sec", hp5: "Health per 5 sec", def: "Defense",
  dodge: "Dodge rating", parry: "Parry rating", block: "Block rating", blockv: "Block value", spen: "Spell penetration",
  expertise: "Expertise", dps: "Weapon DPS", spellcrit: "Spell crit rating", spellhit: "Spell hit rating",
  sp_fire: "Fire spell power", sp_frost: "Frost spell power", sp_shadow: "Shadow spell power",
  sp_nature: "Nature spell power", sp_arcane: "Arcane spell power", sp_holy: "Holy spell power",
  fire_res: "Fire resistance", frost_res: "Frost resistance", shadow_res: "Shadow resistance",
  nature_res: "Nature resistance", arcane_res: "Arcane resistance", crit_pct: "Crit %", hit_pct: "Hit %",
  spellcrit_pct: "Spell crit %", spellhit_pct: "Spell hit %",
};
export const WEIGHT_KEYS = ["str", "agi", "sta", "int", "spi", "ap", "rap", "crit", "hit", "haste", "sp", "heal", "mp5",
  "dps", "armor", "def", "dodge", "parry", "block", "blockv", "spen", "hp5", "fire_res", "frost_res", "shadow_res", "nature_res", "arcane_res"];

const BASE: Record<Role, Stats> = {
  str: { str: 2.2, agi: 1.2, ap: 1, crit: 22 / CRIT_RATING, hit: 26 / HIT_RATING, haste: 1.2, sta: 0.15, dps: 14, armor: 0.005, expertise: 1.5 },
  agi: { agi: 2.0, str: 1.1, ap: 1, crit: 22 / CRIT_RATING, hit: 26 / HIT_RATING, haste: 1.2, sta: 0.15, dps: 13, armor: 0.005, expertise: 1.5 },
  ranged: { agi: 2.2, rap: 1, ap: 0.4, crit: 22 / CRIT_RATING, hit: 24 / HIT_RATING, haste: 1.1, int: 0.4, sta: 0.15, dps: 14, mp5: 1, armor: 0.005 },
  caster: { sp: 1, int: 0.45, spi: 0.1, crit: 11 / CRIT_RATING, hit: 14 / HIT_RATING, haste: 1, mp5: 1, sta: 0.1, spen: 0.7 },
  healer: { heal: 1, sp: 0.9, int: 0.6, spi: 0.45, mp5: 2.2, crit: 9 / CRIT_RATING, haste: 0.9, sta: 0.15 },
  tank: { sta: 1.5, def: 1.3, dodge: 1.1, parry: 1, block: 0.6, blockv: 0.35, armor: 0.12, str: 0.5, agi: 0.6, hit: 0.8, ap: 0.2, dps: 2, expertise: 0.8 },
  bear: { sta: 1.4, agi: 1.0, armor: 0.14, def: 1.2, dodge: 1.2, str: 0.6, hit: 0.7, ap: 0.25, crit: 0.4 },
};

/** Starting weights for a spec and goal. Players can edit these; Custom starts from PvE. */
export function weightsFor(cls: string, specKey: string, goal: Goal): Stats {
  const spec = (SPECS[cls] || []).find((s) => s.key === specKey) || SPECS[cls]?.[0];
  if (!spec) return {};
  const w: Stats = { ...BASE[spec.role] };
  if (spec.role === "caster") for (const s of spec.school || []) w[`sp_${s}`] = 1;
  if (spec.role === "healer") w.sp_holy = 0.3;
  if (goal === "pvp") {
    w.sta = Math.max(w.sta || 0, spec.role === "tank" || spec.role === "bear" ? 1.6 : 1.1);
    w.armor = (w.armor || 0) + 0.02;
    if (w.hit) w.hit *= 0.6;
    w.crit = (w.crit || 0) * 1.1;
    if (spec.role === "healer") { w.mp5 = (w.mp5 || 0) * 0.8; w.int = (w.int || 0) * 1.2; }
    w.spen = (w.spen || 0) + (spec.role === "caster" ? 0.5 : 0);
  } else if (goal === "level") {
    w.sta = Math.max(w.sta || 0, 0.6);
    if (w.hit) w.hit *= 0.5;
    if (spec.role === "caster" || spec.role === "healer") { w.spi = Math.max(w.spi || 0, 0.6); w.int = (w.int || 0) + 0.2; }
    if (spec.role === "str" || spec.role === "agi") w.dps = (w.dps || 0) * 1.25;
    w.armor = (w.armor || 0) + 0.01;
  }
  return w;
}

// Who can use what (Classic rules; mail and plate from level 40).
const WEAPONS: Record<string, string[]> = {
  WARRIOR: ["axe1", "axe2", "mace1", "mace2", "sword1", "sword2", "polearm", "staff", "fist", "dagger", "bow", "gun", "crossbow", "thrown"],
  PALADIN: ["axe1", "axe2", "mace1", "mace2", "sword1", "sword2", "polearm"],
  HUNTER: ["axe1", "axe2", "sword1", "sword2", "polearm", "staff", "fist", "dagger", "bow", "gun", "crossbow", "thrown"],
  ROGUE: ["mace1", "sword1", "fist", "dagger", "bow", "gun", "crossbow", "thrown"],
  PRIEST: ["mace1", "staff", "dagger", "wand"],
  SHAMAN: ["axe1", "axe2", "mace1", "mace2", "staff", "fist", "dagger"],
  MAGE: ["sword1", "staff", "dagger", "wand"],
  WARLOCK: ["sword1", "staff", "dagger", "wand"],
  DRUID: ["mace1", "mace2", "staff", "fist", "dagger", "polearm"],
};
const ARMOR: Record<string, (lvl: number) => string[]> = {
  WARRIOR: (l) => ["cloth", "leather", "mail", ...(l >= 40 ? ["plate"] : [])],
  PALADIN: (l) => ["cloth", "leather", "mail", ...(l >= 40 ? ["plate"] : [])],
  HUNTER: (l) => ["cloth", "leather", ...(l >= 40 ? ["mail"] : [])],
  SHAMAN: (l) => ["cloth", "leather", ...(l >= 40 ? ["mail"] : [])],
  ROGUE: () => ["cloth", "leather"], DRUID: () => ["cloth", "leather"],
  PRIEST: () => ["cloth"], MAGE: () => ["cloth"], WARLOCK: () => ["cloth"],
};
const SHIELD = new Set(["WARRIOR", "PALADIN", "SHAMAN"]);
const DUAL = new Set(["WARRIOR", "ROGUE", "HUNTER"]);
const RELIC: Record<string, string> = { PALADIN: "libram", DRUID: "idol", SHAMAN: "totem" };
const CASTERS = new Set(["PRIEST", "MAGE", "WARLOCK", "DRUID", "SHAMAN", "PALADIN"]);

export function canUse(it: Item, cls: string, level: number): boolean {
  const c = CLASSES[cls];
  if (!c) return false;
  if (it.classes && !(it.classes & c.bit)) return false;
  // Tier pieces and class rewards: if every way to get the item is a quest for other classes, skip it.
  if (it.src?.length && it.src.every((s) => s.t === "quest" && s.qcls && !(s.qcls & c.bit))) return false;
  if (it.cls === 2) {
    if (it.type === "wand") return WEAPONS[cls].includes("wand");
    return WEAPONS[cls].includes(it.type);
  }
  if (it.slot === "shield") return SHIELD.has(cls);
  if (it.slot === "relic") return RELIC[cls] === it.type;
  if (it.slot === "holdable") return CASTERS.has(cls);
  if (["cloth", "leather", "mail", "plate"].includes(it.type) && it.slot !== "back") return ARMOR[cls](level).includes(it.type);
  return true;
}
export const canDualWield = (cls: string) => DUAL.has(cls);

export const PAPERDOLL = ["head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet",
  "finger1", "finger2", "trinket1", "trinket2", "mainhand", "offhand", "ranged"] as const;
export type DollSlot = (typeof PAPERDOLL)[number];
export const DOLL_LABEL: Record<DollSlot, string> = {
  head: "Head", neck: "Neck", shoulder: "Shoulders", back: "Back", chest: "Chest", wrist: "Wrists", hands: "Hands",
  waist: "Waist", legs: "Legs", feet: "Feet", finger1: "Ring 1", finger2: "Ring 2", trinket1: "Trinket 1",
  trinket2: "Trinket 2", mainhand: "Main hand", offhand: "Off hand", ranged: "Ranged / relic",
};

/** Which item slots can go in a paper-doll slot for this class. */
export function fits(doll: DollSlot, it: Item, cls: string): boolean {
  switch (doll) {
    case "finger1": case "finger2": return it.slot === "finger";
    case "trinket1": case "trinket2": return it.slot === "trinket";
    case "mainhand": return it.slot === "onehand" || it.slot === "mainhand" || it.slot === "twohand";
    case "offhand":
      return it.slot === "shield" || it.slot === "holdable" || it.slot === "offhand" || (it.slot === "onehand" && canDualWield(cls));
    case "ranged": return it.slot === "ranged" || it.slot === "relic";
    default: return it.slot === doll;
  }
}

export const SOURCE_KINDS = [
  { key: "raid", name: "Raids" }, { key: "dungeon", name: "Dungeons" }, { key: "pvp", name: "PvP rewards" },
  { key: "rep", name: "Reputation" }, { key: "quest", name: "Quests" }, { key: "craft", name: "Crafted" },
  { key: "vendor", name: "Vendors" }, { key: "chest", name: "Chests and objects" }, { key: "drop", name: "Mob drops" }, { key: "world", name: "World drops" },
  { key: "logged", name: "Seen by players" }, { key: "unknown", name: "Source not known yet" },
] as const;

export function sourceKind(it: Item): string {
  const s = it.src?.[0];
  if (!s) return "unknown";
  if (s.t === "drop" && s.boss) return "dungeon";
  return s.t;
}

export function score(it: Item, w: Stats): number {
  let v = 0;
  for (const [k, n] of Object.entries(it.stats)) {
    if (k === "crit_pct") v += n * CRIT_RATING * (w.crit || 0);
    else if (k === "hit_pct") v += n * HIT_RATING * (w.hit || 0);
    else if (k === "spellcrit_pct" || k === "spellcrit") v += (k === "spellcrit" ? n : n * CRIT_RATING) * (w.crit || 0);
    else if (k === "spellhit_pct" || k === "spellhit") v += (k === "spellhit" ? n : n * HIT_RATING) * (w.hit || 0);
    else v += n * (w[k] || 0);
  }
  return Math.round(v * 10) / 10;
}
