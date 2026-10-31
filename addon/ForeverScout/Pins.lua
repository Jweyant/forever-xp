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

local used = {}
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

-- World map pins are big and labeled so they stand out from Questie's; minimap pins are compact.
-- A frame can only live on one map, so each spot gets a world frame and a minimap frame.
local function newPin(kind)
  local size = kind == "world" and 30 or 20
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(size, size)
  f.kind = kind
  f:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  f.glow = f:CreateTexture(nil, "BACKGROUND", nil, -1)
  f.glow:SetPoint("CENTER")
  f.glow:SetSize(size * 1.9, size * 1.9)
  f.glow:SetTexture("Interface\\Cooldown\\star4")
  f.glow:SetBlendMode("ADD")
  f.glow:SetVertexColor(0.31, 0.76, 0.97, kind == "world" and 0.9 or 0.6)
  f.border = f:CreateTexture(nil, "BACKGROUND")
  f.border:SetAllPoints()
  f.border:SetTexture(WHITE)
  f.border:SetVertexColor(0.31, 0.76, 0.97, 1)
  f.inner = f:CreateTexture(nil, "BORDER")
  f.inner:SetPoint("TOPLEFT", 2, -2)
  f.inner:SetPoint("BOTTOMRIGHT", -2, 2)
  f.inner:SetTexture(WHITE)
  f.inner:SetVertexColor(0, 0, 0, 1)
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetPoint("TOPLEFT", 3, -3)
  f.icon:SetPoint("BOTTOMRIGHT", -3, 3)
  f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  f.tag = f:CreateTexture(nil, "OVERLAY")
  f.tag:SetSize(size * 0.45, size * 0.45)
  f.tag:SetPoint("TOPLEFT", -size * 0.15, size * 0.15)
  f.tag:SetTexture("Interface\\AddOns\\ForeverScout\\logo")
  f.count = f:CreateFontString(nil, "OVERLAY", "NumberFontNormal")
  f.count:SetPoint("BOTTOMRIGHT", 3, -3)
  if kind == "world" then
    f.label = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    f.label:SetPoint("TOP", f, "BOTTOM", 0, -1)
    f.label:SetShadowOffset(1, -1)
    f.label:SetShadowColor(0, 0, 0, 1)
    f.label:SetWidth(140)
    f.label:SetWordWrap(false)
  end
  f:SetScript("OnEnter", onEnter)
  f:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f:SetScript("OnClick", onClick)
  return f
end

local pools = { world = {}, mini = {} }
local function getPin(kind)
  local f = table.remove(pools[kind]) or newPin(kind)
  used[#used + 1] = f
  return f
end

function Pins.Clear()
  if not Pins.Available() then return end
  HBDPins:RemoveAllMinimapIcons(REF)
  HBDPins:RemoveAllWorldMapIcons(REF)
  for _, f in ipairs(used) do f:Hide() f.entries = nil table.insert(pools[f.kind], f) end
  wipe(used)
end

local function fill(f, spot)
  local first = spot.entries[1]
  f.entries, f.m, f.x, f.y = spot.entries, spot.m, spot.x, spot.y
  f.icon:SetTexture(iconOf(first.id, first.it))
  local c = QUALITY_RGB[first.it.q] or QUALITY_RGB[1]
  f.border:SetVertexColor(c[1], c[2], c[3], 1)
  f.count:SetText(#spot.entries > 1 and tostring(#spot.entries) or "")
  if f.label then
    f.label:SetText(#spot.entries > 1 and ("%s +%d"):format(first.it.n, #spot.entries - 1) or first.it.n)
    f.label:SetTextColor(c[1], c[2], c[3])
  end
  f:Show()
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
    local w, mm = getPin("world"), getPin("mini")
    fill(w, spot) fill(mm, spot)
    HBDPins:AddWorldMapIconMap(REF, w, spot.m, spot.x / 100, spot.y / 100, HBD_PINS_WORLDMAP_SHOW_PARENT, 200)
    HBDPins:AddMinimapIconMap(REF, mm, spot.m, spot.x / 100, spot.y / 100, false, true)
    n = n + 1
  end
  return n
end

------------------------------------------------------------------------------------------
-- Ping: open the world map on the right zone and pulse a big marker at the spot for a while,
-- on the world map and at the minimap edge, so "Show on map" is unmistakable.
------------------------------------------------------------------------------------------
local ping

local function makePing(size)
  local f = CreateFrame("Frame", nil, UIParent)
  f:SetSize(size, size)
  f.ring = f:CreateTexture(nil, "OVERLAY")
  f.ring:SetAllPoints()
  f.ring:SetTexture("Interface\\Cooldown\\star4")
  f.ring:SetBlendMode("ADD")
  f.ring:SetVertexColor(0.31, 0.76, 0.97, 1)
  f.dot = f:CreateTexture(nil, "OVERLAY", nil, 1)
  f.dot:SetSize(size / 4, size / 4)
  f.dot:SetPoint("CENTER")
  f.dot:SetTexture(WHITE)
  f.dot:SetVertexColor(1, 0.85, 0.2, 1)
  local ag = f:CreateAnimationGroup()
  ag:SetLooping("REPEAT")
  local grow = ag:CreateAnimation("Scale")
  grow:SetDuration(0.6) grow:SetOrder(1)
  if grow.SetScaleFrom then grow:SetScaleFrom(0.6, 0.6) grow:SetScaleTo(1.3, 1.3) else grow:SetScale(1.8, 1.8) end
  local fade = ag:CreateAnimation("Alpha")
  fade:SetDuration(0.6) fade:SetOrder(1) fade:SetFromAlpha(1) fade:SetToAlpha(0.2)
  local shrink = ag:CreateAnimation("Scale")
  shrink:SetDuration(0.6) shrink:SetOrder(2)
  if shrink.SetScaleFrom then shrink:SetScaleFrom(1.3, 1.3) shrink:SetScaleTo(0.6, 0.6) else shrink:SetScale(1 / 1.8, 1 / 1.8) end
  local unfade = ag:CreateAnimation("Alpha")
  unfade:SetDuration(0.6) unfade:SetOrder(2) unfade:SetFromAlpha(0.2) unfade:SetToAlpha(1)
  f.anim = ag
  f:Hide()
  return f
end

function Pins.ZoneName(m)
  local info = C_Map and C_Map.GetMapInfo and m and C_Map.GetMapInfo(m)
  return info and info.name or ("map " .. tostring(m))
end

function Pins.Ping(m, x, y, title, seconds)
  if not Pins.Available() or not (m and x and y) then return false end
  ping = ping or { world = makePing(48), mini = makePing(28) }
  HBDPins:RemoveAllWorldMapIcons("ForeverScoutPing")
  HBDPins:RemoveAllMinimapIcons("ForeverScoutPing")
  for _, f in pairs(ping) do f.title = title f:Show() f.anim:Play() end
  HBDPins:AddWorldMapIconMap("ForeverScoutPing", ping.world, m, x / 100, y / 100, HBD_PINS_WORLDMAP_SHOW_PARENT, 100)
  HBDPins:AddMinimapIconMap("ForeverScoutPing", ping.mini, m, x / 100, y / 100, true, true)
  -- Open the map on that zone (twice: some clients reset the zone as the frame opens).
  local function showZone()
    if WorldMapFrame and WorldMapFrame.SetMapID then pcall(WorldMapFrame.SetMapID, WorldMapFrame, m) end
  end
  if not InCombatLockdown() then
    if WorldMapFrame and not WorldMapFrame:IsShown() then
      if OpenWorldMap then pcall(OpenWorldMap, m) else pcall(ShowUIPanel, WorldMapFrame) end
    end
    showZone()
    C_Timer.After(0.1, showZone)
  end
  if ping.timer then ping.timer:Cancel() end
  ping.timer = C_Timer.NewTimer(seconds or 20, function()
    HBDPins:RemoveAllWorldMapIcons("ForeverScoutPing")
    HBDPins:RemoveAllMinimapIcons("ForeverScoutPing")
    for _, f in pairs(ping) do if f.anim then f.anim:Stop() f:Hide() end end
  end)
  return true
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
