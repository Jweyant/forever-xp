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

-- One clean marker per spot: the item's icon cut to a circle inside a thin blue ring.
-- A frame can only live on one map, so each spot gets a world frame and a minimap frame.
local RING = "Interface\\AddOns\\ForeverScout\\ring"
local DISC = "Interface\\AddOns\\ForeverScout\\disc"
local MASK = "Interface\\CharacterFrame\\TempPortraitAlphaMask"

local function newPin(kind)
  local size = kind == "world" and 24 or 18
  local f = CreateFrame("Button", nil, UIParent)
  f:SetSize(size, size)
  f.kind = kind
  f:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  f.back = f:CreateTexture(nil, "BACKGROUND")
  f.back:SetAllPoints()
  f.back:SetTexture(DISC)
  f.back:SetVertexColor(0, 0, 0, 1)
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetPoint("TOPLEFT", 2, -2)
  f.icon:SetPoint("BOTTOMRIGHT", -2, 2)
  f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  if f.icon.SetMask then pcall(f.icon.SetMask, f.icon, MASK) end
  f.ring = f:CreateTexture(nil, "OVERLAY")
  f.ring:SetAllPoints()
  f.ring:SetTexture(RING)
  f.ring:SetVertexColor(0.31, 0.76, 0.97, 1)
  f.count = f:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmall")
  f.count:SetPoint("BOTTOMRIGHT", 4, -2)
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
  f.count:SetText(#spot.entries > 1 and tostring(#spot.entries) or "")
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
  f.area = f:CreateTexture(nil, "BACKGROUND")
  f.area:SetPoint("CENTER")
  f.area:SetSize(size * 2.2, size * 2.2)
  f.area:SetTexture(DISC)
  f.area:SetVertexColor(0.31, 0.76, 0.97, 0.18)
  f.ring = f:CreateTexture(nil, "OVERLAY")
  f.ring:SetAllPoints()
  f.ring:SetTexture(RING)
  f.ring:SetVertexColor(0.31, 0.76, 0.97, 1)
  local ag = f.ring:CreateAnimationGroup()
  ag:SetLooping("REPEAT")
  local grow = ag:CreateAnimation("Scale")
  grow:SetDuration(1.0) grow:SetOrder(1)
  if grow.SetScaleFrom then grow:SetScaleFrom(0.5, 0.5) grow:SetScaleTo(1.6, 1.6) else grow:SetScale(3, 3) end
  local fade = ag:CreateAnimation("Alpha")
  fade:SetDuration(1.0) fade:SetOrder(1) fade:SetFromAlpha(1) fade:SetToAlpha(0)
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
  ping = ping or { world = makePing(36), mini = makePing(22) }
  HBDPins:RemoveAllWorldMapIcons("ForeverScoutPing")
  HBDPins:RemoveAllMinimapIcons("ForeverScoutPing")
  for _, f in pairs(ping) do f.title = title f:Show() f.anim:Play() end
  HBDPins:AddWorldMapIconMap("ForeverScoutPing", ping.world, m, x / 100, y / 100, HBD_PINS_WORLDMAP_SHOW_CURRENT, 300)
  HBDPins:AddMinimapIconMap("ForeverScoutPing", ping.mini, m, x / 100, y / 100, true, true)
  -- Open the map and put it on that zone. Set the zone a few times: the frame resets it as it opens.
  local function showZone()
    if WorldMapFrame and WorldMapFrame.SetMapID and WorldMapFrame:IsShown() and WorldMapFrame:GetMapID() ~= m then
      pcall(WorldMapFrame.SetMapID, WorldMapFrame, m)
    end
  end
  if not InCombatLockdown() and WorldMapFrame then
    if not WorldMapFrame:IsShown() then
      if ToggleWorldMap then pcall(ToggleWorldMap) else pcall(ShowUIPanel, WorldMapFrame) end
    end
    showZone()
    for _, t in ipairs({ 0.05, 0.2, 0.5 }) do C_Timer.After(t, showZone) end
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
