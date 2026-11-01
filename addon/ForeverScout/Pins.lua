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
    local c = QUALITY_RGB[e.q] or QUALITY_RGB[1]
    GameTooltip:AddLine(e.n, c[1], c[2], c[3])
    GameTooltip:AddLine(("   for your %s"):format((P.DOLL_LABEL[e.slot] or e.slot or ""):lower()), 0.8, 0.8, 0.8)
    for _, line in ipairs(e.lines or {}) do GameTooltip:AddLine("   " .. line:gsub("^%s+", ""), 0.8, 0.8, 0.8, true) end
  end
  GameTooltip:AddLine("Click: waypoint. Right-click: open the planner.", 0.5, 0.5, 0.5)
  GameTooltip:Show()
end

local function onClick(self, button)
  if button == "RightButton" then ns.BIS.Toggle() return end
  local e = self.entries[1]
  ns.BIS.Waypoint(self.m, self.x, self.y, e and e.n or "Item")
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
  f.icon:SetTexture(iconOf(first.id, { i = first.i }))
  f.count:SetText(#spot.entries > 1 and tostring(#spot.entries) or "")
  f:Show()
end

-- Build the list of map spots for a plan: { {m, x, y, entries = { {id, n, q, i, slot, lines} }} }.
-- Needs the item data; the result is plain values so it can be saved and shown at login without it.
function Pins.Spots(plan, cur)
  if not P.LoadData() then return {} end
  local spots, order = {}, {}
  for _, slot in ipairs(P.PAPERDOLL) do
    local id = plan[slot]
    local it = id and P.Item(id)
    if it and (not cur or cur[slot] ~= id) then
      for _, src in ipairs(it.src or {}) do
        local m, x, y = P.SourcePin(src)
        if m then
          local key = ("%d:%.1f:%.1f"):format(m, x, y)
          if not spots[key] then spots[key] = { m = m, x = x, y = y, entries = {} } order[#order + 1] = key end
          table.insert(spots[key].entries, { id = id, n = it.n, q = it.q, i = it.i, slot = slot, lines = P.SourceLines(src) })
        end
      end
    end
  end
  local list = {}
  for _, key in ipairs(order) do list[#list + 1] = spots[key] end
  return list
end

-- Draw a list of spots (from Pins.Spots or the saved copy). Returns how many were placed.
function Pins.ShowSpots(list)
  if not Pins.Available() then return 0 end
  Pins.Clear()
  local n = 0
  for _, spot in ipairs(list or {}) do
    if type(spot.m) == "number" and type(spot.x) == "number" and type(spot.y) == "number" and type(spot.entries) == "table" and spot.entries[1] then
      local w, mm = getPin("world"), getPin("mini")
      fill(w, spot) fill(mm, spot)
      HBDPins:AddWorldMapIconMap(REF, w, spot.m, spot.x / 100, spot.y / 100, HBD_PINS_WORLDMAP_SHOW_PARENT)
      HBDPins:AddMinimapIconMap(REF, mm, spot.m, spot.x / 100, spot.y / 100, false, true)
      n = n + 1
    end
  end
  return n
end

-- plan = { [slot] = itemId }, cur = { [slot] = itemId } (owned items get no pin).
function Pins.Show(plan, cur)
  return Pins.ShowSpots(Pins.Spots(plan, cur))
end

------------------------------------------------------------------------------------------
-- Ping: open the world map on the right zone and pulse a big marker at the spot for a while,
-- on the world map and at the minimap edge, so "Show on map" is unmistakable.
------------------------------------------------------------------------------------------
local ping, pingTimer

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
  pcall(function()
    local grow = ag:CreateAnimation("Scale")
    grow:SetDuration(1.0) grow:SetOrder(1)
    if grow.SetScaleFrom then grow:SetScaleFrom(0.5, 0.5) grow:SetScaleTo(1.6, 1.6) else grow:SetScale(3, 3) end
    local fade = ag:CreateAnimation("Alpha")
    fade:SetDuration(1.0) fade:SetOrder(1)
    if fade.SetFromAlpha then fade:SetFromAlpha(1) fade:SetToAlpha(0) else fade:SetChange(-1) end
  end)
  f.anim = ag
  f:Hide()
  return f
end

function Pins.ZoneName(m)
  local info = C_Map and C_Map.GetMapInfo and m and C_Map.GetMapInfo(m)
  return info and info.name or ("map " .. tostring(m))
end

function Pins.Ping(m, x, y, title, seconds)
  local ok, result = pcall(Pins.PingRaw, m, x, y, title, seconds)
  if not ok then
    if ns.debug then ns.Print("ping error: " .. tostring(result)) end
    return false
  end
  return result
end

function Pins.PingRaw(m, x, y, title, seconds)
  if not Pins.Available() or not (m and x and y) then return false end
  ping = ping or { world = makePing(36), mini = makePing(22) }
  HBDPins:RemoveAllWorldMapIcons("ForeverScoutPing")
  HBDPins:RemoveAllMinimapIcons("ForeverScoutPing")
  for _, f in ipairs({ ping.world, ping.mini }) do f.title = title f:Show() f.anim:Play() end
  HBDPins:AddWorldMapIconMap("ForeverScoutPing", ping.world, m, x / 100, y / 100, HBD_PINS_WORLDMAP_SHOW_PARENT)
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
  if pingTimer then pingTimer:Cancel() end
  pingTimer = C_Timer.NewTimer(seconds or 20, function()
    HBDPins:RemoveAllWorldMapIcons("ForeverScoutPing")
    HBDPins:RemoveAllMinimapIcons("ForeverScoutPing")
    for _, f in ipairs({ ping.world, ping.mini }) do f.anim:Stop() f:Hide() end
  end)
  return true
end

-- Remember this character's spots so pins come back at the next login without loading the data.
function Pins.Remember(plan, cur)
  ForeverScoutCharDB.bisSpots = Pins.Spots(plan, cur)
  return ForeverScoutCharDB.bisSpots
end

function Pins.Enabled() return ns.db.settings.bisPins ~= false end

function Pins.SetEnabled(on)
  ns.db.settings.bisPins = on and true or false
  if on then Pins.ShowSpots(ForeverScoutCharDB.bisSpots) else Pins.Clear() end
end

ns:On("PLAYER_LOGIN", function()
  if ns.db.settings.bisPlan then ns.db.settings.bisPlan = nil end  -- account-wide copy from 0.3; now per character
  local saved = ForeverScoutCharDB.bisSpots
  if Pins.Enabled() and type(saved) == "table" and #saved > 0 then
    C_Timer.After(8, function()
      local n = Pins.ShowSpots(saved)
      if n > 0 then ns.Print(("%d gear locations on your map. /fscout pins to hide them."):format(n)) end
    end)
  end
end)
