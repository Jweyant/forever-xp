-- ForeverScout: /fscout gear (copy your equipped gear into the forever-xp.com BIS planner)
-- and loot logging (which mob or chest dropped which item, so the site knows where Forever's
-- new items come from). Neither stores names, realms, gold or bag contents.

local ADDON, ns = ...

local SLOTS = {
  { 1, "head" }, { 2, "neck" }, { 3, "shoulder" }, { 15, "back" }, { 5, "chest" }, { 9, "wrist" },
  { 10, "hands" }, { 6, "waist" }, { 7, "legs" }, { 8, "feet" }, { 11, "finger1" }, { 12, "finger2" },
  { 13, "trinket1" }, { 14, "trinket2" }, { 16, "mainhand" }, { 17, "offhand" }, { 18, "ranged" },
}

-- FXPG1:<CLASS>:<level>:<RACE>[.<M|F>]:<A|H>:<slot>=<itemId>[.<enchantId>],...
-- (the body type after the race lets the site show the matching character portrait)
function ns.GearString()
  local _, class = UnitClass("player")
  local _, race = UnitRace("player")
  local faction = UnitFactionGroup("player") == "Horde" and "H" or "A"
  local body = UnitSex and UnitSex("player") == 3 and "F" or "M"
  local parts = {}
  for _, s in ipairs(SLOTS) do
    local link = GetInventoryItemLink("player", s[1])
    if link then
      local id, enchant = link:match("item:(%d+):(%d*)")
      if id then
        local v = s[2] .. "=" .. id
        if enchant and enchant ~= "" and enchant ~= "0" then v = v .. "." .. enchant end
        table.insert(parts, v)
      end
    end
  end
  return ("FXPG1:%s:%d:%s.%s:%s:%s"):format(class or "?", UnitLevel("player") or 0, race or "?", body, faction,
    table.concat(parts, ","))
end

function ns.ShowGear()
  ns.ShowCopy("Your gear for forever-xp.com",
    "Ctrl+C to copy, then paste it on forever-xp.com/bis under Import from the game. "
      .. "It only contains your class, level, race, faction and equipped item IDs.",
    ns.GearString())
end

------------------------------------------------------------------------------------------
-- Loot logging: item ID, where it came from (NPC or object ID) and the map position.

local function sourceOf(guid)
  if not guid then return nil end
  local kind, _, _, _, _, id = strsplit("-", guid)
  return kind, tonumber(id)
end

ns:On("LOOT_OPENED", function()
  if not GetNumLootItems then return end
  local seen = {}
  for slot = 1, GetNumLootItems() do
    local link = GetLootSlotLink(slot)
    local item = link and tonumber(link:match("item:(%d+)"))
    if item and not seen[item] then
      seen[item] = true
      local _, _, _, _, quality = GetLootSlotInfo(slot)
      if (quality or 0) >= 2 or (C_Item and C_Item.GetItemInventoryTypeByID and (C_Item.GetItemInventoryTypeByID(item) or 0) > 0) then
        local kind, id
        if GetLootSourceInfo then kind, id = sourceOf((GetLootSourceInfo(slot))) end
        ns:Log("loot", { item = item, q = quality, src = id, kind = kind })
      end
    end
  end
end)
