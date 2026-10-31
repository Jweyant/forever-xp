-- ForeverScout: world map and minimap pins for the BIS plan.
-- Every planned item with a known location (quest giver, vendor, chest) gets a pin on the
-- world map and the minimap, drawn with HereBeDragons. Pins stay up while the window is
-- closed and come back at login until the player turns them off (/fscout pins).

local ADDON, ns = ...
local Pins = {}
ns.Pins = Pins

local HBD = LibStub and LibStub("HereBeDragons-2.0", true)
local HBDPins = LibStub and LibStub("HereBeDragons-Pins-2.0", true)
local P = ns.Planner

local QUALITY_RGB = { [0] = { 0.62, 0.62, 0.62 }, [1] = { 1, 1, 1 }, [2] = { 0.12, 1, 0 }, [3] = { 0, 0.44, 0.87 }, [4] = { 0.64, 0.21, 0.93 }, [5] = { 1, 0.5, 0 } }
local WHITE = "Interface\\Buttons\\WHITE8x8"

local pool, used = {}, {}
local REF = "ForeverScoutBIS"

function Pins.Available() return HBD ~= nil and HBDPins ~= nil end

local function iconOf(id, it)
  if it and it.i then return "Interface\\Icons\\" .. it.i end
  if C_Item and C_Item.GetItemIconByID then return C_Item.GetItemIconByID(id) end
  return "Interface\\Icons\\INV_Misc_QuestionMark"
end

local function onEnter(self)
  GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
  GameTooltip:AddLine("Forever|cFF4FC3F7XP|r best in slot")
  for _, e in ipairs(self.entries) do
    local c = QUALITY_RGB[e.it.q] or QUALITY_RGB[1]
    GameTooltip:AddLine(e.it.n, c[1], c[2], c[3])
    GameTooltip:AddLine(("   for your %s"):format(P.DOLL_LABEL[e.slot]:lower()), 0.8, 0.8, 0.8)
    for _, line in ipairs(P.SourceLines(e.src)) do GameTooltip:AddLine("   " .. line:gsub("^%s+", ""), 0.8, 0.8, 0.8, true) end
  end
  GameTooltip:AddLine("Click: waypoint. Right-click: open the planner.", 0.5, 0.5, 0.5)
  GameTooltip:Show()
end

local function onClick(self, button)
  if button == "RightButton" then ns.BIS.Toggle() return end
  local e = self.entries[1]
  ns.BIS.Waypoint(self.m, self.x, self.y, e and e.it.n or "Item")
end

local function newPin()
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(16, 16)
  f:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  f.border = f:CreateTexture(nil, "BACKGROUND")
  f.border:SetAllPoints()
  f.border:SetTexture(WHITE)
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetPoint("TOPLEFT", 1, -1)
  f.icon:SetPoint("BOTTOMRIGHT", -1, 1)
  f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  f.count = f:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmall")
  f.count:SetPoint("BOTTOMRIGHT", 2, -2)
  f:SetScript("OnEnter", onEnter)
  f:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f:SetScript("OnClick", onClick)
  return f
end

local function getPin()
  local f = table.remove(pool) or newPin()
  used[#used + 1] = f
  return f
end

function Pins.Clear()
  if not Pins.Available() then return end
  HBDPins:RemoveAllMinimapIcons(REF)
  HBDPins:RemoveAllWorldMapIcons(REF)
  for _, f in ipairs(used) do f:Hide() f.entries = nil pool[#pool + 1] = f end
  wipe(used)
end

-- plan = { [slot] = itemId }, cur = { [slot] = itemId } (owned items get no pin).
function Pins.Show(plan, cur)
  if not Pins.Available() then return 0 end
  Pins.Clear()
  if not P.LoadData() then return 0 end
  local spots, order = {}, {}
  for _, slot in ipairs(P.PAPERDOLL) do
    local id = plan[slot]
    local it = id and P.Item(id)
    if it and (not cur or cur[slot] ~= id) then
      for _, s in ipairs(it.src or {}) do
        local m, x, y = P.SourcePin(s)
        if m then
          local key = ("%d:%.1f:%.1f"):format(m, x, y)
          if not spots[key] then spots[key] = { m = m, x = x, y = y, entries = {} } order[#order + 1] = key end
          table.insert(spots[key].entries, { it = it, id = id, slot = slot, src = s })
        end
      end
    end
  end
  local n = 0
  for _, key in ipairs(order) do
    local spot = spots[key]
    local f = getPin()
    local first = spot.entries[1]
    f.entries, f.m, f.x, f.y = spot.entries, spot.m, spot.x, spot.y
    f.icon:SetTexture(iconOf(first.id, first.it))
    local c = QUALITY_RGB[first.it.q] or QUALITY_RGB[1]
    f.border:SetVertexColor(c[1], c[2], c[3], 1)
    f.count:SetText(#spot.entries > 1 and tostring(#spot.entries) or "")
    f:Show()
    HBDPins:AddMinimapIconMap(REF, f, spot.m, spot.x / 100, spot.y / 100, false, true)
    HBDPins:AddWorldMapIconMap(REF, f, spot.m, spot.x / 100, spot.y / 100, HBD_PINS_WORLDMAP_SHOW_PARENT)
    n = n + 1
  end
  return n
end

-- Remember the plan so pins come back at the next login.
function Pins.Remember(plan, cur)
  local saved = {}
  for slot, id in pairs(plan) do if not cur or cur[slot] ~= id then saved[slot] = id end end
  ns.db.settings.bisPlan = saved
end

function Pins.Enabled() return ns.db.settings.bisPins ~= false end

function Pins.SetEnabled(on)
  ns.db.settings.bisPins = on and true or false
  if on then
    if ns.db.settings.bisPlan then Pins.Show(ns.db.settings.bisPlan, P.Equipped()) end
  else
    Pins.Clear()
  end
end

ns:On("PLAYER_LOGIN", function()
  if Pins.Enabled() and ns.db.settings.bisPlan and next(ns.db.settings.bisPlan) then
    C_Timer.After(8, function()
      local n = Pins.Show(ns.db.settings.bisPlan, P.Equipped())
      if n > 0 then ns.Print(("%d gear locations on your map. /fscout pins to hide them."):format(n)) end
    end)
  end
end)
