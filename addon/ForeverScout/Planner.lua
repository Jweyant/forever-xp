-- ForeverScout: BIS planner. A port of the site's planner (site/src/scripts/gear/model.ts and
-- planner.ts) so the game and forever-xp.com pick the same items. The item data lives in the
-- load-on-demand ForeverScout_Data addon (global ForeverScoutData), loaded by P.LoadData().
-- No player names, realms or inventory contents leave this file; it only reads equipped item IDs.

local ADDON, ns = ...
local P = {}
ns.Planner = P

local floor, max = math.floor, math.max
local ITEMS = {}

-- Loads ForeverScout_Data if needed. Returns true when item data is available.
function P.LoadData()
  if ForeverScoutData and ForeverScoutData.ITEMS then ITEMS = ForeverScoutData.ITEMS return true end
  local load = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
  if load then pcall(load, "ForeverScout_Data") end
  if ForeverScoutData and ForeverScoutData.ITEMS then ITEMS = ForeverScoutData.ITEMS return true end
  return false
end
function P.DataBuild() return ForeverScoutData and ForeverScoutData.BUILD or "?" end
function P.Set(id) return ForeverScoutData and ForeverScoutData.SETS and ForeverScoutData.SETS[id] end

P.CRIT_RATING, P.HIT_RATING = 14, 10

P.CLASSES = {
  WARRIOR = { id = 1, name = "Warrior", bit = 1 }, PALADIN = { id = 2, name = "Paladin", bit = 2 },
  HUNTER = { id = 3, name = "Hunter", bit = 4 }, ROGUE = { id = 4, name = "Rogue", bit = 8 },
  PRIEST = { id = 5, name = "Priest", bit = 16 }, SHAMAN = { id = 7, name = "Shaman", bit = 64 },
  MAGE = { id = 8, name = "Mage", bit = 128 }, WARLOCK = { id = 9, name = "Warlock", bit = 256 },
  DRUID = { id = 11, name = "Druid", bit = 1024 },
}

P.SPECS = {
  WARRIOR = { { key = "arms", name = "Arms", role = "str" }, { key = "fury", name = "Fury", role = "str" }, { key = "prot", name = "Protection", role = "tank" } },
  PALADIN = { { key = "holy", name = "Holy", role = "healer" }, { key = "prot", name = "Protection", role = "tank" }, { key = "ret", name = "Retribution", role = "str" } },
  HUNTER = { { key = "bm", name = "Beast Mastery", role = "ranged" }, { key = "mm", name = "Marksmanship", role = "ranged" }, { key = "sv", name = "Survival", role = "ranged" } },
  ROGUE = { { key = "assa", name = "Assassination", role = "agi" }, { key = "combat", name = "Combat", role = "agi" }, { key = "sub", name = "Subtlety", role = "agi" } },
  PRIEST = { { key = "disc", name = "Discipline", role = "healer" }, { key = "holy", name = "Holy", role = "healer" }, { key = "shadow", name = "Shadow", role = "caster", school = { "shadow" } } },
  SHAMAN = { { key = "ele", name = "Elemental", role = "caster", school = { "nature", "fire" } }, { key = "enh", name = "Enhancement", role = "str" }, { key = "resto", name = "Restoration", role = "healer" } },
  MAGE = { { key = "arcane", name = "Arcane", role = "caster", school = { "arcane" } }, { key = "fire", name = "Fire", role = "caster", school = { "fire" } }, { key = "frost", name = "Frost", role = "caster", school = { "frost" } } },
  WARLOCK = { { key = "aff", name = "Affliction", role = "caster", school = { "shadow" } }, { key = "demo", name = "Demonology", role = "caster", school = { "shadow" } }, { key = "destro", name = "Destruction", role = "caster", school = { "shadow", "fire" } } },
  DRUID = { { key = "balance", name = "Balance", role = "caster", school = { "nature", "arcane" } }, { key = "cat", name = "Feral (cat)", role = "agi" }, { key = "bear", name = "Feral (bear)", role = "bear" }, { key = "resto", name = "Restoration", role = "healer" } },
}

P.GOALS = {
  { key = "pve", name = "PvE raids and dungeons" },
  { key = "pvp", name = "PvP" },
  { key = "level", name = "Leveling" },
}

-- Stats a player can focus a plan on (resistance sets, haste builds, stamina for PvP...).
P.FOCUS_STATS = { "sta", "haste", "hit", "crit", "ap", "sp", "heal", "mp5", "spi", "int", "def", "dodge", "armor",
  "fire_res", "frost_res", "nature_res", "shadow_res", "arcane_res" }
P.FOCUS_WEIGHT = 1000 -- per point of the focused stat, so it outranks everything else; normal score breaks ties

P.STAT_LABEL = {
  str = "Strength", agi = "Agility", sta = "Stamina", int = "Intellect", spi = "Spirit", armor = "Armor",
  ap = "Attack power", rap = "Ranged attack power", crit = "Crit rating", hit = "Hit rating", haste = "Haste rating",
  sp = "Spell power", heal = "Healing", mp5 = "Mana per 5 sec", hp5 = "Health per 5 sec", def = "Defense",
  dodge = "Dodge rating", parry = "Parry rating", block = "Block rating", blockv = "Block value", spen = "Spell penetration",
  expertise = "Expertise", dps = "Weapon DPS", spellcrit = "Spell crit rating", spellhit = "Spell hit rating",
  sp_fire = "Fire spell power", sp_frost = "Frost spell power", sp_shadow = "Shadow spell power",
  sp_nature = "Nature spell power", sp_arcane = "Arcane spell power", sp_holy = "Holy spell power",
  fire_res = "Fire resistance", frost_res = "Frost resistance", shadow_res = "Shadow resistance",
  nature_res = "Nature resistance", arcane_res = "Arcane resistance", crit_pct = "Crit %", hit_pct = "Hit %",
  spellcrit_pct = "Spell crit %", spellhit_pct = "Spell hit %",
}

local CR, HR = P.CRIT_RATING, P.HIT_RATING
local BASE = {
  str = { str = 2.2, agi = 1.2, ap = 1, crit = 22 / CR, hit = 26 / HR, haste = 1.2, sta = 0.15, dps = 14, armor = 0.005, expertise = 1.5 },
  agi = { agi = 2.0, str = 1.1, ap = 1, crit = 22 / CR, hit = 26 / HR, haste = 1.2, sta = 0.15, dps = 13, armor = 0.005, expertise = 1.5 },
  ranged = { agi = 2.2, rap = 1, ap = 0.4, crit = 22 / CR, hit = 24 / HR, haste = 1.1, int = 0.4, sta = 0.15, dps = 14, mp5 = 1, armor = 0.005 },
  caster = { sp = 1, int = 0.45, spi = 0.1, crit = 11 / CR, hit = 14 / HR, haste = 1, mp5 = 1, sta = 0.1, spen = 0.7 },
  healer = { heal = 1, sp = 0.9, int = 0.6, spi = 0.45, mp5 = 2.2, crit = 9 / CR, haste = 0.9, sta = 0.15 },
  tank = { sta = 1.5, def = 1.3, dodge = 1.1, parry = 1, block = 0.6, blockv = 0.35, armor = 0.12, str = 0.5, agi = 0.6, hit = 0.8, ap = 0.2, dps = 2, expertise = 0.8 },
  bear = { sta = 1.4, agi = 1.0, armor = 0.14, def = 1.2, dodge = 1.2, str = 0.6, hit = 0.7, ap = 0.25, crit = 0.4 },
}

function P.Spec(cls, specKey)
  local list = P.SPECS[cls]
  if not list then return nil end
  for _, s in ipairs(list) do if s.key == specKey then return s end end
  return list[1]
end

-- Starting weights for a spec and goal (same numbers as the site).
function P.WeightsFor(cls, specKey, goal)
  local spec = P.Spec(cls, specKey)
  if not spec then return {} end
  local w = {}
  for k, v in pairs(BASE[spec.role]) do w[k] = v end
  if spec.role == "caster" then for _, s in ipairs(spec.school or {}) do w["sp_" .. s] = 1 end end
  if spec.role == "healer" then w.sp_holy = 0.3 end
  if goal == "pvp" then
    w.sta = max(w.sta or 0, (spec.role == "tank" or spec.role == "bear") and 1.6 or 1.1)
    w.armor = (w.armor or 0) + 0.02
    if w.hit then w.hit = w.hit * 0.6 end
    w.crit = (w.crit or 0) * 1.1
    if spec.role == "healer" then w.mp5 = (w.mp5 or 0) * 0.8; w.int = (w.int or 0) * 1.2 end
    w.spen = (w.spen or 0) + (spec.role == "caster" and 0.5 or 0)
  elseif goal == "level" then
    w.sta = max(w.sta or 0, 0.6)
    if w.hit then w.hit = w.hit * 0.5 end
    if spec.role == "caster" or spec.role == "healer" then w.spi = max(w.spi or 0, 0.6); w.int = (w.int or 0) + 0.2 end
    if spec.role == "str" or spec.role == "agi" then w.dps = (w.dps or 0) * 1.25 end
    w.armor = (w.armor or 0) + 0.01
  end
  return w
end

local function set(list) local t = {} for _, v in ipairs(list) do t[v] = true end return t end
local WEAPONS = {
  WARRIOR = set { "axe1", "axe2", "mace1", "mace2", "sword1", "sword2", "polearm", "staff", "fist", "dagger", "bow", "gun", "crossbow", "thrown" },
  PALADIN = set { "axe1", "axe2", "mace1", "mace2", "sword1", "sword2", "polearm" },
  HUNTER = set { "axe1", "axe2", "sword1", "sword2", "polearm", "staff", "fist", "dagger", "bow", "gun", "crossbow", "thrown" },
  ROGUE = set { "mace1", "sword1", "fist", "dagger", "bow", "gun", "crossbow", "thrown" },
  PRIEST = set { "mace1", "staff", "dagger", "wand" },
  SHAMAN = set { "axe1", "axe2", "mace1", "mace2", "staff", "fist", "dagger" },
  MAGE = set { "sword1", "staff", "dagger", "wand" },
  WARLOCK = set { "sword1", "staff", "dagger", "wand" },
  DRUID = set { "mace1", "mace2", "staff", "fist", "dagger", "polearm" },
}
local ARMOR = {
  WARRIOR = function(l) return { cloth = true, leather = true, mail = true, plate = l >= 40 } end,
  PALADIN = function(l) return { cloth = true, leather = true, mail = true, plate = l >= 40 } end,
  HUNTER = function(l) return { cloth = true, leather = true, mail = l >= 40 } end,
  SHAMAN = function(l) return { cloth = true, leather = true, mail = l >= 40 } end,
  ROGUE = function() return { cloth = true, leather = true } end,
  DRUID = function() return { cloth = true, leather = true } end,
  PRIEST = function() return { cloth = true } end,
  MAGE = function() return { cloth = true } end,
  WARLOCK = function() return { cloth = true } end,
}
local SHIELD = set { "WARRIOR", "PALADIN", "SHAMAN" }
local DUAL = set { "WARRIOR", "ROGUE", "HUNTER" }
local RELIC = { PALADIN = "libram", DRUID = "idol", SHAMAN = "totem" }
local CASTERS = set { "PRIEST", "MAGE", "WARLOCK", "DRUID", "SHAMAN", "PALADIN" }
local ARMOR_TYPES = set { "cloth", "leather", "mail", "plate" }

local function band(a, b) -- bitwise AND for class masks (Lua 5.1 has no operator; masks are < 2^11)
  local r, p = 0, 1
  while a > 0 and b > 0 do
    if a % 2 == 1 and b % 2 == 1 then r = r + p end
    a, b, p = floor(a / 2), floor(b / 2), p * 2
  end
  return r
end

function P.CanDualWield(cls) return DUAL[cls] == true end

function P.CanUse(it, cls, level)
  local c = P.CLASSES[cls]
  if not c or not WEAPONS[cls] or not ARMOR[cls] then return false end
  if it.cm and band(it.cm, c.bit) == 0 then return false end
  if it.src and #it.src > 0 then
    local onlyOthers = true
    for _, s in ipairs(it.src) do
      if not (s.t == "quest" and s.qcls and band(s.qcls, c.bit) == 0) then onlyOthers = false break end
    end
    if onlyOthers then return false end
  end
  if it.c == 2 then return WEAPONS[cls][it.ty] == true end
  if it.s == "shield" then return SHIELD[cls] == true end
  if it.s == "relic" then return RELIC[cls] == it.ty end
  if it.s == "holdable" then return CASTERS[cls] == true end
  if ARMOR_TYPES[it.ty] and it.s ~= "back" then return ARMOR[cls](level)[it.ty] == true end
  return true
end

P.PAPERDOLL = { "head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet",
  "finger1", "finger2", "trinket1", "trinket2", "mainhand", "offhand", "ranged" }
P.DOLL_LABEL = {
  head = "Head", neck = "Neck", shoulder = "Shoulders", back = "Back", chest = "Chest", wrist = "Wrists", hands = "Hands",
  waist = "Waist", legs = "Legs", feet = "Feet", finger1 = "Ring 1", finger2 = "Ring 2", trinket1 = "Trinket 1",
  trinket2 = "Trinket 2", mainhand = "Main hand", offhand = "Off hand", ranged = "Ranged / relic",
}
-- Paper-doll slot -> inventory slot ID for GetInventoryItemLink.
P.INV_SLOT = { head = 1, neck = 2, shoulder = 3, back = 15, chest = 5, wrist = 9, hands = 10, waist = 6, legs = 7,
  feet = 8, finger1 = 11, finger2 = 12, trinket1 = 13, trinket2 = 14, mainhand = 16, offhand = 17, ranged = 18 }

function P.Fits(doll, it, cls)
  local s = it.s
  if doll == "finger1" or doll == "finger2" then return s == "finger" end
  if doll == "trinket1" or doll == "trinket2" then return s == "trinket" end
  if doll == "mainhand" then return s == "onehand" or s == "mainhand" or s == "twohand" end
  if doll == "offhand" then return s == "shield" or s == "holdable" or s == "offhand" or (s == "onehand" and DUAL[cls] == true) end
  if doll == "ranged" then return s == "ranged" or s == "relic" end
  return s == doll
end

P.SOURCE_KINDS = {
  { key = "raid", name = "Raids" }, { key = "dungeon", name = "Dungeons" }, { key = "pvp", name = "PvP rewards" },
  { key = "rep", name = "Reputation" }, { key = "quest", name = "Quests" }, { key = "craft", name = "Crafted" },
  { key = "vendor", name = "Vendors" }, { key = "chest", name = "Chests and objects" }, { key = "drop", name = "Mob drops" },
  { key = "world", name = "World drops" }, { key = "logged", name = "Seen by players" }, { key = "unknown", name = "Source not known yet" },
}
P.SLOT_NAME = {
  head = "Head", neck = "Neck", shoulder = "Shoulder", back = "Back", chest = "Chest", wrist = "Wrist", hands = "Hands",
  waist = "Waist", legs = "Legs", feet = "Feet", finger = "Finger", trinket = "Trinket", mainhand = "Main Hand",
  offhand = "Off Hand", onehand = "One-Hand", twohand = "Two-Hand", ranged = "Ranged", relic = "Relic", shield = "Off Hand",
  holdable = "Held In Off-hand",
}
P.SRC_LABEL = {
  chest = "Chest", raid = "Raid", dungeon = "Dungeon", pvp = "PvP", rep = "Reputation", quest = "Quest", craft = "Crafted",
  vendor = "Vendor", drop = "Drop", world = "World drop", logged = "Seen in Forever",
}

function P.SourceKind(it)
  local s = it.src and it.src[1]
  if not s then return "unknown" end
  if s.t == "drop" and s.boss then return "dungeon" end
  return s.t
end

function P.Score(it, w)
  local v = 0
  for k, n in pairs(it.st) do
    if k == "crit_pct" then v = v + n * CR * (w.crit or 0)
    elseif k == "hit_pct" then v = v + n * HR * (w.hit or 0)
    elseif k == "spellcrit_pct" then v = v + n * CR * (w.crit or 0)
    elseif k == "spellcrit" then v = v + n * (w.crit or 0)
    elseif k == "spellhit_pct" then v = v + n * HR * (w.hit or 0)
    elseif k == "spellhit" then v = v + n * (w.hit or 0)
    else v = v + n * (w[k] or 0) end
  end
  return floor(v * 10 + 0.5) / 10
end

------------------------------------------------------------------------------------------
-- Suggestions. `opts` = { cls, spec, goal, level, side, sources (set of kinds or nil), weights (or nil) }
------------------------------------------------------------------------------------------
local function slotWeights(opts, w, doll, it)
  if not it.w then return w end
  local hunter = opts.cls == "HUNTER"
  local k = 1
  if doll == "ranged" then k = hunter and 1 or 0.08
  elseif hunter then k = 0.15
  elseif doll == "offhand" then k = 0.5 end
  if it.s == "twohand" and not hunter then k = k * 1.9 end
  if k == 1 then return w end
  local w2 = {}
  for key, v in pairs(w) do w2[key] = v end
  w2.dps = (w.dps or 0) * k
  return w2
end

-- The focused stat on an item, counting the percent and spell forms of hit and crit.
function P.FocusAmount(it, focus)
  if not it or not focus then return 0 end
  local st = it.st
  local v = st[focus] or 0
  if focus == "crit" then v = v + (st.spellcrit or 0) + ((st.crit_pct or 0) + (st.spellcrit_pct or 0)) * P.CRIT_RATING
  elseif focus == "hit" then v = v + (st.spellhit or 0) + ((st.hit_pct or 0) + (st.spellhit_pct or 0)) * P.HIT_RATING
  elseif focus == "sp" then
    for _, k in ipairs({ "sp_fire", "sp_frost", "sp_shadow", "sp_nature", "sp_arcane" }) do v = math.max(v, st[k] or 0) end
  end
  return v
end

function P.Value(opts, w, doll, it)
  if not it then return 0 end
  local v = P.Score(it, slotWeights(opts, w, doll, it))
  if opts.focus then v = v + P.FocusAmount(it, opts.focus) * P.FOCUS_WEIGHT end
  return v
end

local function candidates(opts, doll)
  local out, focused = {}, {}
  for id, it in pairs(ITEMS) do
    if it.q >= 1 and it.lv <= opts.level and (not it.sd or it.sd == opts.side)
      and (not opts.sources or opts.sources[P.SourceKind(it)])
      and P.CanUse(it, opts.cls, opts.level) and P.Fits(doll, it, opts.cls) then
      it.id = id
      out[#out + 1] = it
      if opts.focus and P.FocusAmount(it, opts.focus) > 0 then focused[#focused + 1] = it end
    end
  end
  if opts.focus and #focused > 0 then return focused end
  return out
end

local function best(opts, w, doll, exclude)
  local top, topV = nil, 0
  for _, it in ipairs(candidates(opts, doll)) do
    if it.id ~= exclude then
      local v = P.Value(opts, w, doll, it)
      -- Ties go to the lower item ID so results are stable between runs and match the site.
      if v > topV or (v == topV and top and v > 0 and it.id < top.id) then top, topV = it, v end
    end
  end
  return top
end

local function bestOf(list, opts, w, doll)
  local top, topV = nil, -1
  for _, it in ipairs(list) do
    local v = P.Value(opts, w, doll, it)
    if v > topV or (v == topV and top and it.id < top.id) then top, topV = it, v end
  end
  return top
end

-- Returns { [dollSlot] = itemId } plus the weights used.
function P.Suggest(opts)
  local w = opts.weights or P.WeightsFor(opts.cls, opts.spec, opts.goal)
  local plan = {}
  for _, d in ipairs(P.PAPERDOLL) do
    if d ~= "finger2" and d ~= "trinket2" and d ~= "mainhand" and d ~= "offhand" then
      local it = best(opts, w, d)
      if it then plan[d] = it.id end
    end
  end
  local r2 = best(opts, w, "finger2", plan.finger1); if r2 then plan.finger2 = r2.id end
  local t2 = best(opts, w, "trinket2", plan.trinket1); if t2 then plan.trinket2 = t2.id end

  local mains = candidates(opts, "mainhand")
  local twos, ones = {}, {}
  for _, it in ipairs(mains) do if it.s == "twohand" then twos[#twos + 1] = it else ones[#ones + 1] = it end end
  local twoH, oneH = bestOf(twos, opts, w, "mainhand"), bestOf(ones, opts, w, "mainhand")
  local offs = {}
  for _, it in ipairs(candidates(opts, "offhand")) do
    if not oneH or it.id ~= oneH.id then offs[#offs + 1] = it end
  end
  local off = bestOf(offs, opts, w, "offhand")
  local vTwo = P.Value(opts, w, "mainhand", twoH)
  if twoH and vTwo >= P.Value(opts, w, "mainhand", oneH) + P.Value(opts, w, "offhand", off) then
    plan.mainhand = twoH.id
  else
    if oneH then plan.mainhand = oneH.id end
    if off then plan.offhand = off.id end
  end
  return plan, w
end

-- The player's equipped item IDs by paper-doll slot (only IDs the planner knows).
function P.Equipped()
  local cur = {}
  if not GetInventoryItemLink then return cur end
  for doll, inv in pairs(P.INV_SLOT) do
    local link = GetInventoryItemLink("player", inv)
    local id = link and tonumber(link:match("item:(%d+)"))
    if id then cur[doll] = id end
  end
  return cur
end

function P.Item(id) return ITEMS[id] end

-- Upgrade list: for each slot, the BIS pick, the current item and the score difference.
function P.Compare(opts, plan, cur, w)
  local rows = {}
  for _, d in ipairs(P.PAPERDOLL) do
    local pid, cid = plan[d], cur[d]
    local pit, cit = pid and ITEMS[pid], cid and ITEMS[cid]
    local pv, cv = P.Value(opts, w, d, pit), P.Value(opts, w, d, cit)
    rows[#rows + 1] = { slot = d, plan = pid, cur = cid, planV = pv, curV = cv, gain = pv - cv }
  end
  return rows
end

-- One line on where an item comes from, in the site's wording.
function P.SourceText(it)
  local s = it.src and it.src[1]
  if not s then return "Source not known yet" end
  local where = {}
  if s.n then where[#where + 1] = s.n end
  if s.z then where[#where + 1] = s.z end
  local txt = (P.SRC_LABEL[s.t] or s.t)
  if #where > 0 then txt = txt .. ": " .. table.concat(where, ", ") end
  if s.ch then txt = txt .. (" (%s%%)"):format(tostring(s.ch)) end
  return txt
end
