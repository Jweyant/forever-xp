-- ForeverScout: the in-game BIS planner window (/fscout bis) and the minimap button.
-- Shows what the character is wearing next to the best item for every slot for a chosen spec,
-- goal and optional stat focus, at the character's level or any level up to 60, with where
-- each item comes from. Reads only class, race, faction, level and equipped item IDs.

local ADDON, ns = ...
local P = ns.Planner
ns.BIS = {}

local WIN_W, WIN_H = 940, 650
local ROW_H, ROWS_W, ROWS_TOP = 26, 600, -126
local QUALITY_COLOR = { [0] = "9d9d9d", [1] = "ffffff", [2] = "1eff00", [3] = "0070dd", [4] = "a335ee", [5] = "ff8000" }
local GOAL_NAME = { pve = "PvE", pvp = "PvP", level = "Leveling" }
local QMARK = "Interface\\Icons\\INV_Misc_QuestionMark"
local WHITE = "Interface\\Buttons\\WHITE8x8"

-- Skin: flat dark panels, 1px borders, blue accent (the ForeverScout blue from the title).
local C = {
  bg = { 0.07, 0.07, 0.08, 0.96 }, panel = { 0.11, 0.11, 0.13, 1 }, border = { 0.24, 0.24, 0.28, 1 },
  btn = { 0.16, 0.16, 0.19, 1 }, btnHover = { 0.22, 0.22, 0.26, 1 }, accent = { 0.31, 0.76, 0.97, 1 },
  stripe = { 1, 1, 1, 0.03 }, select = { 0.31, 0.76, 0.97, 0.16 }, track = { 0.2, 0.2, 0.23, 1 },
}

local win, state, srcWin, focusWin
local statLines

------------------------------------------------------------------------------------------
-- Helpers
------------------------------------------------------------------------------------------
local function playerClass() local _, cls = UnitClass("player") return cls end
local function playerSide() return UnitFactionGroup("player") == "Horde" and "H" or "A" end

local function colored(it, fallback)
  if not it then return "|cff9d9d9d" .. (fallback or "nothing") .. "|r" end
  return ("|cff%s%s|r"):format(QUALITY_COLOR[it.q] or "ffffff", it.n)
end

-- Our own icon name first: Forever-only items aren't in a Classic client's cache, and the game
-- answers with a question mark for IDs it doesn't know.
local function iconOf(id, it)
  if it and it.i then return "Interface\\Icons\\" .. it.i end
  local tex
  if C_Item and C_Item.GetItemIconByID then tex = C_Item.GetItemIconByID(id)
  elseif GetItemIcon then tex = GetItemIcon(id) end
  return tex or QMARK
end

local function fmtGain(v)
  if v > 0.05 then return ("|cff55ff55+%.0f|r"):format(v) end
  if v < -0.05 then return ("|cffff5555%.0f|r"):format(v) end
  return "|cff9d9d9d0|r"
end

local function levelText(it)
  if it.e then return ("about level %d"):format(it.lv) end
  return ("level %d"):format(it.lv)
end

local function focusLabel(key)
  if not key then return "Any stat" end
  return P.STAT_LABEL[key] or key
end

-- Default spec: the talent tree with the most points, if the client exposes it.
local function guessSpec(cls)
  local specs = P.SPECS[cls] or {}
  if GetNumTalentTabs and GetTalentTabInfo then
    local bestTab, bestPts = nil, -1
    for tab = 1, GetNumTalentTabs() do
      local ok, a, b, c, d, e = pcall(GetTalentTabInfo, tab)
      local pts = ok and (type(c) == "number" and c or type(e) == "number" and e) or 0
      if pts > bestPts then bestTab, bestPts = tab, pts end
    end
    if bestTab and bestPts > 0 and specs[bestTab] then return specs[bestTab].key end
  end
  return specs[1] and specs[1].key
end

-- True when the game client can draw a tooltip for this item ID itself.
local function clientKnows(id)
  local info = (C_Item and C_Item.GetItemInfo or GetItemInfo)
  if not info then return false end
  local ok, name = pcall(info, id)
  return ok and name ~= nil
end

-- Name, quality and icon for an equipped item the planner's data doesn't have.
local function clientItem(id)
  local info = (C_Item and C_Item.GetItemInfo or GetItemInfo)
  if not info then return nil end
  local ok, name, _, quality, _, _, _, _, _, _, icon = pcall(info, id)
  if not ok or not name then return nil end
  return { n = name, q = quality or 1, tex = icon }
end

-- Tooltip for an item: the game's own (with the equipped-item comparison on Shift) when the
-- client knows the item, otherwise one drawn from the planner's data, so Forever-only items
-- never show "Retrieving item information".
local function showItemTip(owner, id, anchor)
  if not id then return end
  GameTooltip:SetOwner(owner, anchor or "ANCHOR_RIGHT")
  local it = P.Item(id)
  if clientKnows(id) then
    local ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. id)
    if ok then
      if it then GameTooltip:AddLine(P.SourceText(it), 0.31, 0.76, 0.97, true) end
      GameTooltip:Show()
      if GameTooltip_ShowCompareItem then pcall(GameTooltip_ShowCompareItem, GameTooltip) end
      return
    end
  end
  if not it then GameTooltip:SetText("Item " .. id) GameTooltip:Show() return end
  local q = QUALITY_COLOR[it.q] or "ffffff"
  GameTooltip:SetText(it.n, tonumber(q:sub(1, 2), 16) / 255, tonumber(q:sub(3, 4), 16) / 255, tonumber(q:sub(5, 6), 16) / 255)
  GameTooltip:AddLine(("Item level %d"):format(it.il), 1, 0.82, 0)
  GameTooltip:AddDoubleLine(P.SLOT_NAME[it.s] or it.s, it.ty ~= "misc" and (it.ty:gsub("^%l", string.upper)) or "", 1, 1, 1, 1, 1, 1)
  for _, line in ipairs(statLines(it)) do GameTooltip:AddLine(line, 1, 1, 1, true) end
  GameTooltip:AddLine(("Requires %s"):format(levelText(it)), 1, 1, 1)
  GameTooltip:AddLine(P.SourceText(it), 0.31, 0.76, 0.97, true)
  GameTooltip:AddLine("From forever-xp.com data; this client has no tooltip for the item.", 0.5, 0.5, 0.5, true)
  GameTooltip:Show()
end

local function tip(frame, title, text, anchor)
  frame:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, anchor or "ANCHOR_BOTTOM")
    GameTooltip:SetText(title, 1, 1, 1)
    if text then GameTooltip:AddLine(text, 0.8, 0.8, 0.8, true) end
    GameTooltip:Show()
  end)
  frame:SetScript("OnLeave", function() GameTooltip:Hide() end)
end

-- Put a pin on the map: TomTom when installed, else the game's own map pin, else print it.
function ns.BIS.Waypoint(m, x, y, title)
  if not (m and x and y) then return end
  if TomTom and TomTom.AddWaypoint then
    local ok = pcall(TomTom.AddWaypoint, TomTom, m, x / 100, y / 100, { title = title, persistent = false, minimap = true, world = true })
    if ok then ns.Print(("Waypoint set: %s (%.1f, %.1f)"):format(title or "", x, y)) return end
  end
  if C_Map and C_Map.SetUserWaypoint and UiMapPoint and C_Map.CanSetUserWaypointOnMap and C_Map.CanSetUserWaypointOnMap(m) then
    local ok = pcall(function()
      C_Map.SetUserWaypoint(UiMapPoint.CreateFromCoordinates(m, x / 100, y / 100))
      if C_SuperTrack and C_SuperTrack.SetSuperTrackedUserWaypoint then C_SuperTrack.SetSuperTrackedUserWaypoint(true) end
    end)
    if ok then ns.Print(("Map pin set: %s (%.1f, %.1f). Open the map to see it."):format(title or "", x, y)) return end
  end
  ns.Print(("%s is at %.1f, %.1f. Install TomTom for an arrow."):format(title or "Target", x, y))
end

------------------------------------------------------------------------------------------
-- Skin pieces
------------------------------------------------------------------------------------------
local function flat(frame, bg, border)
  if not frame.SetBackdrop then return end
  frame:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  frame:SetBackdropColor(unpack(bg or C.panel))
  frame:SetBackdropBorderColor(unpack(border or C.border))
end

local function fontString(parent, template, x, y, w, justify)
  local s = parent:CreateFontString(nil, "OVERLAY", template)
  if x then s:SetPoint("TOPLEFT", x, y) end
  if w then s:SetWidth(w) end
  s:SetJustifyH(justify or "LEFT")
  return s
end

-- Flat button. `b:SetActive(true)` draws the accent border (the current choice in a group).
local function makeButton(parent, text, width)
  local b = CreateFrame("Button", nil, parent, "BackdropTemplate")
  b:SetSize(width or 120, 24)
  flat(b, C.btn)
  b.text = b:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  b.text:SetPoint("CENTER")
  b.text:SetText(text)
  b:SetScript("OnEnter", function(self) self:SetBackdropColor(unpack(C.btnHover)) end)
  b:SetScript("OnLeave", function(self) self:SetBackdropColor(unpack(C.btn)) end)
  function b:SetText(t) self.text:SetText(t) end
  function b:SetActive(on) self:SetBackdropBorderColor(unpack(on and C.accent or C.border)) end
  return b
end

-- Flat slider: a thin track and a small thumb; `onChange(value)` fires on every step.
local function makeSlider(parent, width, lo, hi, onChange)
  local s = CreateFrame("Slider", nil, parent, "BackdropTemplate")
  s:SetSize(width, 18)
  s:SetOrientation("HORIZONTAL")
  s:SetMinMaxValues(lo, hi)
  s:SetValueStep(1)
  s:SetObeyStepOnDrag(true)
  s:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1, insets = { left = 0, right = 0, top = 7, bottom = 7 } })
  s:SetBackdropColor(unpack(C.track))
  s:SetBackdropBorderColor(0, 0, 0, 0)
  local thumb = s:CreateTexture(nil, "ARTWORK")
  thumb:SetSize(10, 18)
  thumb:SetColorTexture(unpack(C.accent))
  s:SetThumbTexture(thumb)
  s:SetScript("OnValueChanged", function(self, v) onChange(math.floor(v + 0.5)) end)
  s:EnableMouseWheel(true)
  s:SetScript("OnMouseWheel", function(self, d) self:SetValue(self:GetValue() + d) end)
  return s
end

local function makeCheck(parent, label, onClick)
  local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  cb:SetSize(22, 22)
  cb.label = cb:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  cb.label:SetPoint("LEFT", cb, "RIGHT", 2, 0)
  cb.label:SetText(label)
  cb:SetScript("OnClick", function(self) onClick(self:GetChecked() and true or false) end)
  return cb
end

-- A popup list anchored under a button; `rows` = { {key, label}, ... }, `onPick(key)`.
local function makePopup(parent, anchor, title, rows, onPick, width)
  local f = CreateFrame("Frame", nil, parent, "BackdropTemplate")
  f:SetSize(width or 230, 22 * #rows + 40)
  f:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", 0, -4)
  f:SetFrameStrata("DIALOG")
  f:EnableMouse(true)
  flat(f, { 0.09, 0.09, 0.1, 0.98 })
  local t = fontString(f, "GameFontNormal", 10, -10, (width or 230) - 20)
  t:SetText(title)
  f.rows = {}
  for i, r in ipairs(rows) do
    local b = CreateFrame("Button", nil, f)
    b:SetSize((width or 230) - 12, 22)
    b:SetPoint("TOPLEFT", 6, -30 - (i - 1) * 22)
    b.key = r[1]
    b.bg = b:CreateTexture(nil, "BACKGROUND")
    b.bg:SetAllPoints()
    b.bg:SetColorTexture(unpack(C.select))
    b.bg:Hide()
    b.mark = fontString(b, "GameFontHighlight", nil, nil, 14, "CENTER")
    b.mark:SetPoint("LEFT", 4, 0)
    b.label = fontString(b, "GameFontHighlight", nil, nil, (width or 230) - 40)
    b.label:SetPoint("LEFT", 22, 0)
    b.label:SetText(r[2])
    b:SetScript("OnEnter", function(self) self.bg:Show() end)
    b:SetScript("OnLeave", function(self) if not self.on then self.bg:Hide() end end)
    b:SetScript("OnClick", function(self) onPick(self.key) end)
    f.rows[#f.rows + 1] = b
  end
  function f:Mark(isOn)
    for _, b in ipairs(self.rows) do
      b.on = isOn(b.key)
      b.mark:SetText(b.on and "|cff4fc3f7>|r" or "")
      if b.on then b.bg:Show() else b.bg:Hide() end
    end
  end
  f:Hide()
  return f
end

------------------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------------------
local function buildRow(f, d)
  local r = CreateFrame("Button", nil, f)
  r:SetSize(ROWS_W, ROW_H)
  r.doll = d
  r.stripe = r:CreateTexture(nil, "BACKGROUND", nil, -1)
  r.stripe:SetAllPoints()
  r.stripe:SetColorTexture(unpack(C.stripe))
  r.hl = r:CreateTexture(nil, "BACKGROUND")
  r.hl:SetAllPoints()
  r.hl:SetColorTexture(1, 1, 1, 0.06)
  r.hl:Hide()
  r.sel = r:CreateTexture(nil, "BACKGROUND")
  r.sel:SetAllPoints()
  r.sel:SetColorTexture(unpack(C.select))
  r.sel:Hide()
  r.bar = r:CreateTexture(nil, "BACKGROUND", nil, 1)
  r.bar:SetPoint("LEFT", 0, 0)
  r.bar:SetSize(3, ROW_H)
  r.bar:SetColorTexture(unpack(C.accent))
  r.bar:Hide()

  r.slot = fontString(r, "GameFontHighlightSmall", nil, nil, 66)
  r.slot:SetPoint("LEFT", 8, 0)
  r.slot:SetText(P.DOLL_LABEL[d])

  r.curIcon = r:CreateTexture(nil, "ARTWORK")
  r.curIcon:SetSize(18, 18)
  r.curIcon:SetPoint("LEFT", 78, 0)
  r.curIcon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  r.cur = fontString(r, "GameFontHighlightSmall", nil, nil, 176)
  r.cur:SetPoint("LEFT", 100, 0)
  r.cur:SetWordWrap(false)

  r.arrow = fontString(r, "GameFontDisableSmall", nil, nil, 16, "CENTER")
  r.arrow:SetPoint("LEFT", 280, 0)
  r.arrow:SetText(">")

  r.icon = r:CreateTexture(nil, "ARTWORK")
  r.icon:SetSize(18, 18)
  r.icon:SetPoint("LEFT", 300, 0)
  r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  r.name = fontString(r, "GameFontHighlightSmall", nil, nil, 176)
  r.name:SetPoint("LEFT", 322, 0)
  r.name:SetWordWrap(false)

  r.focus = fontString(r, "GameFontHighlightSmall", nil, nil, 48, "RIGHT")
  r.focus:SetPoint("LEFT", 492, 0)
  r.gain = fontString(r, "GameFontHighlightSmall", nil, nil, 52, "RIGHT")
  r.gain:SetPoint("LEFT", 542, 0)

  r:SetScript("OnEnter", function(self) self.hl:Show() showItemTip(self, self.itemId) end)
  r:SetScript("OnLeave", function(self) self.hl:Hide() GameTooltip:Hide() end)
  r:SetScript("OnClick", function(self) state.selected = self.doll ns.BIS.RenderDetail() end)
  return r
end

local function build()
  local f = CreateFrame("Frame", "ForeverScoutBIS", UIParent, "BackdropTemplate")
  f:SetSize(WIN_W, WIN_H)
  f:SetPoint("CENTER")
  f:SetFrameStrata("HIGH")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:SetClampedToScreen(true)
  flat(f, C.bg)
  tinsert(UISpecialFrames, "ForeverScoutBIS")

  -- Title bar
  local bar = f:CreateTexture(nil, "BACKGROUND", nil, 1)
  bar:SetPoint("TOPLEFT", 1, -1)
  bar:SetPoint("TOPRIGHT", -1, -1)
  bar:SetHeight(30)
  bar:SetColorTexture(0.1, 0.1, 0.12, 1)
  local line = f:CreateTexture(nil, "BACKGROUND", nil, 2)
  line:SetPoint("TOPLEFT", 1, -31)
  line:SetPoint("TOPRIGHT", -1, -31)
  line:SetHeight(1)
  line:SetColorTexture(unpack(C.border))
  f.title = fontString(f, "GameFontNormal", 12, -8, 400)
  f.title:SetText("Forever|cFF4FC3F7XP|r  best in slot")
  f.char = fontString(f, "GameFontHighlightSmall", nil, nil, 400, "CENTER")
  f.char:SetPoint("TOP", 0, -9)

  local close = makeButton(f, "x", 24)
  close:SetPoint("TOPRIGHT", -4, -3)
  close:SetScript("OnClick", function() f:Hide() end)

  -- Controls: spec, goal, focus, sources, level
  f.spec = makeButton(f, "Spec", 130)
  f.spec:SetPoint("TOPLEFT", 12, -42)
  f.spec:SetScript("OnClick", function()
    local specs = P.SPECS[state.cls] or {}
    for i, s in ipairs(specs) do
      if s.key == state.spec then state.spec = (specs[i + 1] or specs[1]).key break end
    end
    ns.BIS.Refresh()
  end)
  tip(f.spec, "Spec", "Click to switch between your class's specs.")

  f.goal = makeButton(f, "Goal", 96)
  f.goal:SetPoint("LEFT", f.spec, "RIGHT", 6, 0)
  f.goal:SetScript("OnClick", function()
    for i, g in ipairs(P.GOALS) do
      if g.key == state.goal then state.goal = (P.GOALS[i + 1] or P.GOALS[1]).key break end
    end
    ns.BIS.Refresh()
  end)
  tip(f.goal, "Gearing for", "Leveling, PvE (raids and dungeons) or PvP. Changes the stat weights.")

  f.focus = makeButton(f, "Focus: any stat", 170)
  f.focus:SetPoint("LEFT", f.goal, "RIGHT", 6, 0)
  f.focus:SetScript("OnClick", function() ns.BIS.ToggleFocus() end)
  tip(f.focus, "Focus on a stat", "Plan for fire resistance, haste, stamina and so on: items with the stat win, most of it first, "
    .. "and the normal score breaks ties. Slots with no such item fall back to the usual pick.")

  f.sources = makeButton(f, "Sources", 110)
  f.sources:SetPoint("LEFT", f.focus, "RIGHT", 6, 0)
  f.sources:SetScript("OnClick", function() ns.BIS.ToggleSources() end)
  tip(f.sources, "Where items may come from", "Untick raids, PvP, crafting or anything you won't do, and the plan only uses the rest.")

  f.levelLabel = fontString(f, "GameFontNormal", nil, nil, 70)
  f.levelLabel:SetPoint("LEFT", f.sources, "RIGHT", 16, 0)
  f.levelLabel:SetText("Level |cffffffff60|r")
  f.level = makeSlider(f, 150, 1, 60, function(v)
    f.levelLabel:SetText(("Level |cffffffff%d|r"):format(v))
    if v == state.level then return end
    state.level = v
    if ns.BIS.refreshTimer then ns.BIS.refreshTimer:Cancel() end
    ns.BIS.refreshTimer = C_Timer.NewTimer(0.2, ns.BIS.Refresh)
  end)
  f.level:SetPoint("LEFT", f.levelLabel, "RIGHT", 4, 0)
  f.myLevel = makeButton(f, "Me", 40)
  f.myLevel:SetPoint("LEFT", f.level, "RIGHT", 10, 0)
  f.myLevel:SetScript("OnClick", function() f.level:SetValue(UnitLevel("player")) end)
  tip(f.myLevel, "Back to your level")
  f.plus5 = makeButton(f, "+5", 40)
  f.plus5:SetPoint("LEFT", f.myLevel, "RIGHT", 4, 0)
  f.plus5:SetScript("OnClick", function() f.level:SetValue(math.min(60, state.level + 5)) end)
  tip(f.plus5, "Five levels ahead", "What to aim for next.")

  f.upgrades = makeCheck(f, "Upgrades only", function(on) state.upgradesOnly = on ns.BIS.Layout() end)
  f.upgrades:SetPoint("TOPLEFT", 10, -72)

  f.pins = makeCheck(f, "Pins on map and minimap", function(on) ns.Pins.SetEnabled(on) ns.BIS.UpdatePins() end)
  f.pins:SetPoint("LEFT", f.upgrades, "RIGHT", 120, 0)
  tip(f.pins, "Show every planned item's location", "Quest givers, vendors and chests with known positions get a pin on the world map "
    .. "and minimap. Click a pin for a waypoint. Pins stay after you close this window.")
  if not ns.Pins.Available() then f.pins:Disable() f.pins.label:SetText("|cff9d9d9dPins (map library missing)|r") end

  -- Next-step line (click to select that slot)
  local nextBtn = CreateFrame("Button", nil, f, "BackdropTemplate")
  nextBtn:SetPoint("TOPLEFT", 12, -98)
  nextBtn:SetSize(ROWS_W, 26)
  flat(nextBtn, { 0.13, 0.12, 0.09, 1 }, { 0.35, 0.3, 0.15, 1 })
  nextBtn.text = fontString(nextBtn, "GameFontHighlight", nil, nil, ROWS_W - 64)
  nextBtn.text:SetPoint("LEFT", 8, 0)
  nextBtn.text:SetWordWrap(false)
  nextBtn:SetScript("OnClick", function(self) if self.doll then state.selected = self.doll ns.BIS.RenderDetail() end end)
  nextBtn:SetScript("OnEnter", function(self) if self.itemId then showItemTip(self, self.itemId, "ANCHOR_BOTTOMLEFT") end end)
  nextBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f.next = nextBtn

  -- Column headers
  local function header(text, x, w, justify)
    local h = fontString(f, "GameFontNormalSmall", x, ROWS_TOP + 16, w, justify)
    h:SetText(text)
    return h
  end
  header("Slot", 20, 66)
  header("You have", 112, 176)
  header("Best for this plan", 334, 176)
  f.focusHead = header("", 504, 48, "RIGHT")
  header("Gain", 554, 52, "RIGHT")
  local hline = f:CreateTexture(nil, "BACKGROUND", nil, 2)
  hline:SetPoint("TOPLEFT", 12, ROWS_TOP + 2)
  hline:SetSize(ROWS_W, 1)
  hline:SetColorTexture(unpack(C.border))

  f.rows = {}
  for _, d in ipairs(P.PAPERDOLL) do f.rows[d] = buildRow(f, d) end

  -- Detail panel (right)
  local panel = CreateFrame("Frame", nil, f, "BackdropTemplate")
  panel:SetPoint("TOPLEFT", 626, -72)
  panel:SetPoint("BOTTOMRIGHT", -12, 44)
  flat(panel, C.panel)
  f.panel = panel
  panel.icon = panel:CreateTexture(nil, "ARTWORK")
  panel.icon:SetSize(36, 36)
  panel.icon:SetPoint("TOPLEFT", 12, -12)
  panel.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  panel.name = fontString(panel, "GameFontNormal", 56, -12, 230)
  panel.name:SetWordWrap(true)
  panel.sub = fontString(panel, "GameFontHighlightSmall", 56, -30, 230)
  panel.body = fontString(panel, "GameFontHighlightSmall", 12, -60)
  panel.body:SetPoint("RIGHT", -12, 0)
  panel.body:SetPoint("BOTTOM", 0, 40)
  panel.body:SetJustifyV("TOP")
  panel.body:SetWordWrap(true)
  panel.body:SetSpacing(2)
  panel:EnableMouse(true)
  panel:SetScript("OnEnter", function(self) if state.selected then showItemTip(self, state.plan[state.selected], "ANCHOR_LEFT") end end)
  panel:SetScript("OnLeave", function() GameTooltip:Hide() end)

  -- Footer
  f.foot = fontString(f, "GameFontDisableSmall", 14, nil, 600)
  f.foot:ClearAllPoints()
  f.foot:SetPoint("BOTTOMLEFT", 14, 16)
  f.foot:SetWordWrap(false)
  panel.pin = makeButton(panel, "Show on map", 120)
  panel.pin:SetPoint("BOTTOMLEFT", 10, 10)
  panel.pin:SetScript("OnClick", function(self) if self.m then ns.BIS.Waypoint(self.m, self.x, self.y, self.title) end end)
  tip(panel.pin, "Pin the quest giver or source on your map", "Uses TomTom if you have it, otherwise the game's map pin.", "ANCHOR_TOP")
  panel.pin:Hide()

  f.nextPin = makeButton(f, "Map", 44)
  f.nextPin:SetPoint("RIGHT", nextBtn, "RIGHT", -3, 0)
  f.nextPin:SetScript("OnClick", function(self) if self.m then ns.BIS.Waypoint(self.m, self.x, self.y, self.title) end end)
  tip(f.nextPin, "Pin the next step on your map")
  f.nextPin:Hide()

  f.copy = makeButton(f, "Copy gear for the site", 170)
  f.copy:SetPoint("BOTTOMRIGHT", -12, 12)
  f.copy:SetScript("OnClick", function() ns.ShowGear() end)
  tip(f.copy, "forever-xp.com/bis", "Copies your gear as text to paste on the site, where you can edit stat weights and share the plan.", "ANCHOR_TOP")

  f:SetScript("OnHide", function() if srcWin then srcWin:Hide() end if focusWin then focusWin:Hide() end end)

  -- A click anywhere outside an open popup (and its button) closes it.
  f.clickWatch = CreateFrame("Frame")
  f.clickWatch:RegisterEvent("GLOBAL_MOUSE_DOWN")
  f.clickWatch:SetScript("OnEvent", function()
    for _, pair in ipairs({ { srcWin, f.sources }, { focusWin, f.focus } }) do
      local popup, button = pair[1], pair[2]
      if popup and popup:IsShown() and not popup:IsMouseOver() and not button:IsMouseOver() then popup:Hide() end
    end
  end)
  return f
end

------------------------------------------------------------------------------------------
-- Popups: sources and focus
------------------------------------------------------------------------------------------
local function sourceSet()
  local saved = ns.db.settings.bisSources
  local set = {}
  for _, k in ipairs(P.SOURCE_KINDS) do set[k.key] = not (saved and saved[k.key] == false) end
  return set
end

function ns.BIS.ToggleSources(keepOpen)
  if focusWin then focusWin:Hide() end
  if not srcWin then
    local rows = {}
    for _, k in ipairs(P.SOURCE_KINDS) do rows[#rows + 1] = { k.key, k.name } end
    rows[#rows + 1] = { "__all", "|cff9d9d9dEverything|r" }
    srcWin = makePopup(win, win.sources, "Where items may come from (click to toggle)", rows, function(key)
      if key == "__all" then ns.db.settings.bisSources = nil
      else
        local set = sourceSet()
        ns.db.settings.bisSources = ns.db.settings.bisSources or {}
        ns.db.settings.bisSources[key] = not set[key]
      end
      ns.BIS.Refresh()
      ns.BIS.ToggleSources(true)
    end, 260)
  end
  if srcWin:IsShown() and not keepOpen then srcWin:Hide() return end
  local set = sourceSet()
  srcWin:Mark(function(key) return key ~= "__all" and set[key] end)
  srcWin:Show()
end

function ns.BIS.ToggleFocus(keepOpen)
  if srcWin then srcWin:Hide() end
  if not focusWin then
    local rows = { { "__none", "Any stat (normal plan)" } }
    for _, k in ipairs(P.FOCUS_STATS) do rows[#rows + 1] = { k, P.STAT_LABEL[k] or k } end
    focusWin = makePopup(win, win.focus, "Focus the plan on one stat", rows, function(key)
      state.focus = key ~= "__none" and key or nil
      ns.db.settings.bisFocus = state.focus
      focusWin:Hide()
      ns.BIS.Refresh()
    end, 240)
  end
  if focusWin:IsShown() and not keepOpen then focusWin:Hide() return end
  focusWin:Mark(function(key) return (state.focus or "__none") == key end)
  focusWin:Show()
end

------------------------------------------------------------------------------------------
-- Rendering
------------------------------------------------------------------------------------------
function statLines(it)
  local L = {}
  if it.w then L[#L + 1] = ("%d - %d damage, speed %.2f (%.1f DPS)"):format(it.w[1], it.w[2], it.w[3], it.st.dps or 0) end
  if it.st.armor then L[#L + 1] = ("%d Armor"):format(it.st.armor) end
  for _, k in ipairs({ "str", "agi", "sta", "int", "spi" }) do
    if it.st[k] then L[#L + 1] = ("+%d %s"):format(it.st[k], P.STAT_LABEL[k]) end
  end
  local extra = {}
  for k in pairs(it.st) do
    if not (k == "str" or k == "agi" or k == "sta" or k == "int" or k == "spi" or k == "armor" or k == "dps") then
      extra[#extra + 1] = k
    end
  end
  table.sort(extra)
  for _, k in ipairs(extra) do
    local label = P.STAT_LABEL[k] or k
    if k:sub(-4) == "_pct" then L[#L + 1] = ("|cff1eff00Equip: Improves %s by %s%%.|r"):format((label:gsub(" %%", "")), tostring(it.st[k]))
    else L[#L + 1] = ("|cff1eff00Equip: +%s %s.|r"):format(tostring(it.st[k]), label) end
  end
  for _, fx in ipairs(it.fx or {}) do
    local on = fx[1] == "use" and "Use" or fx[1] == "hit" and "Chance on hit" or "Equip"
    L[#L + 1] = ("|cff1eff00%s: %s|r"):format(on, fx[2])
  end
  return L
end

function ns.BIS.RenderDetail()
  local f, p = win, win.panel
  local d = state.selected
  local id = d and state.plan[d]
  local it = id and P.Item(id)
  for _, r in pairs(f.rows) do
    if r.doll == d then r.sel:Show() r.bar:Show() else r.sel:Hide() r.bar:Hide() end
  end
  if not it then
    p.icon:SetTexture(nil)
    p.name:SetText("Pick a slot")
    p.sub:SetText("")
    p.body:SetText("Click a row to see the item, its stats and where to get it.")
    return
  end
  p.icon:SetTexture(iconOf(id, it))
  p.name:SetText(colored(it))
  p.sub:SetText(("%s, item level %d, needs %s"):format(P.DOLL_LABEL[d], it.il, levelText(it)))

  local L = statLines(it)
  if state.focus then
    L[#L + 1] = ("|cff4fc3f7%s: %d|r"):format(focusLabel(state.focus), P.FocusAmount(it, state.focus))
  end
  L[#L + 1] = ""
  L[#L + 1] = "|cff4fc3f7Where to get it|r"
  p.pin:Hide()
  if it.src and #it.src > 0 then
    for i, s in ipairs(it.src) do
      if i > 1 then L[#L + 1] = "" end
      for _, line in ipairs(P.SourceLines(s)) do L[#L + 1] = line end
      if not p.pin:IsShown() then
        local m, x, y, title = P.SourcePin(s)
        if m then p.pin.m, p.pin.x, p.pin.y, p.pin.title = m, x, y, title p.pin:Show() end
      end
    end
  else
    L[#L + 1] = "Not known yet. Players running ForeverScout fill this in as they loot."
  end
  if it.set then
    local set = P.Set(it.set)
    if set then
      L[#L + 1] = ""
      L[#L + 1] = "|cff4fc3f7" .. set.n .. "|r"
      for _, b in ipairs(set.b or {}) do L[#L + 1] = ("(%d) %s"):format(b[1], b[2]) end
    end
  end

  L[#L + 1] = ""
  L[#L + 1] = "|cff4fc3f7Compared with what you have|r"
  local curId = state.cur[d]
  local cur = curId and P.Item(curId)
  if curId == id then
    L[#L + 1] = "|cff55ff55You're wearing it.|r"
  elseif cur then
    local gain = P.Value(state.plain, state.weights, d, it) - P.Value(state.plain, state.weights, d, cur)
    L[#L + 1] = ("%s score over %s."):format(fmtGain(gain), colored(cur))
    if state.focus then
      L[#L + 1] = ("%s: %d now, %d with this item."):format(focusLabel(state.focus), P.FocusAmount(cur, state.focus), P.FocusAmount(it, state.focus))
    end
    L[#L + 1] = "|cff9d9d9dShift-hover any row to compare tooltips.|r"
  elseif curId then
    local ci = clientItem(curId)
    L[#L + 1] = ("%s isn't in Forever's item data, so it can't be scored."):format(ci and colored(ci) or ("Item " .. curId))
  else
    L[#L + 1] = "Nothing equipped in this slot."
  end
  if it.e then
    L[#L + 1] = ""
    L[#L + 1] = "|cff9d9d9dThe level is an estimate: the game data has no requirement for this item.|r"
  end
  p.body:SetText(table.concat(L, "\n"))
end

-- Lay the rows out top to bottom, hiding the ones the filter removes.
function ns.BIS.Layout()
  local f = win
  local y, shown = ROWS_TOP, 0
  for _, d in ipairs(P.PAPERDOLL) do
    local r = f.rows[d]
    local hide = state.upgradesOnly and (r.owned or not r.itemId or (r.gainV or 0) <= 0)
    if hide then r:Hide()
    else
      r:ClearAllPoints()
      r:SetPoint("TOPLEFT", 12, y)
      r:Show()
      shown = shown + 1
      if shown % 2 == 0 then r.stripe:Show() else r.stripe:Hide() end
      y = y - ROW_H
    end
  end
end

function ns.BIS.Refresh()
  if not win or not win:IsShown() then return end
  if not P.LoadData() then
    win.next.text:SetText("|cffff5555Item data (ForeverScout_Data) could not be loaded.|r Reinstall ForeverScout from CurseForge.")
    return
  end
  local f = win
  local spec = P.Spec(state.cls, state.spec)
  f.spec:SetText(spec and spec.name or "Spec")
  f.goal:SetText(GOAL_NAME[state.goal] or state.goal)
  f.focus:SetText("Focus: " .. focusLabel(state.focus):lower())
  f.focus:SetActive(state.focus ~= nil)
  f.char:SetText(("%s, level %d %s"):format(UnitName("player") or "", UnitLevel("player"), P.CLASSES[state.cls].name))

  local sources, limited = sourceSet(), 0
  for _, k in ipairs(P.SOURCE_KINDS) do if not sources[k.key] then limited = limited + 1 end end
  f.sources:SetText(limited > 0 and ("Sources (%d off)"):format(limited) or "Sources")
  f.sources:SetActive(limited > 0)
  f.focusHead:SetText(state.focus and (P.STAT_LABEL[state.focus] or ""):gsub(" resistance", " res"):gsub(" rating", "") or "")

  state.opts = { cls = state.cls, spec = state.spec, goal = state.goal, level = state.level, side = state.side,
    sources = sources, focus = state.focus }
  local plan, w = P.Suggest(state.opts)
  state.plan, state.weights = plan, w
  state.cur = P.Equipped()
  -- Scores shown to the player are the plain ones (what the site shows); the focus stat has its own column.
  state.plain = { cls = state.cls, spec = state.spec, goal = state.goal, level = state.level, side = state.side }

  local bestRow, upgrades, focusTotal = nil, 0, 0
  for _, d in ipairs(P.PAPERDOLL) do
    local r = f.rows[d]
    local pid, cid = plan[d], state.cur[d]
    local it, cur = pid and P.Item(pid), cid and P.Item(cid)
    -- Gain uses the plain score (what the site shows); the focus stat gets its own column.
    local gain = P.Value(state.plain, w, d, it) - P.Value(state.plain, w, d, cur)
    r.itemId, r.gainV = pid, gain
    r.owned = cid ~= nil and cid == pid
    r.icon:SetTexture(it and iconOf(pid, it) or nil)
    r.name:SetText(colored(it, "none at this level"))
    if cur then
      r.curIcon:SetTexture(iconOf(cid, cur))
      r.cur:SetText(colored(cur))
    elseif cid then
      local ci = clientItem(cid)
      r.curIcon:SetTexture(ci and ci.tex or iconOf(cid))
      r.cur:SetText(ci and colored(ci) or ("|cffffffffItem " .. cid .. "|r"))
    else
      r.curIcon:SetTexture(nil)
      r.cur:SetText("|cff9d9d9dempty|r")
    end
    if state.focus and it then
      local amt = P.FocusAmount(it, state.focus)
      focusTotal = focusTotal + amt
      r.focus:SetText(amt > 0 and ("|cff4fc3f7%d|r"):format(amt) or "|cff9d9d9d-|r")
    else
      r.focus:SetText("")
    end
    if r.owned then
      r.gain:SetText("|cff55ff55have|r")
      r.arrow:SetText("=")
    else
      r.gain:SetText(it and fmtGain(gain) or "")
      r.arrow:SetText(">")
      if it and (gain > 0 or (state.focus and P.FocusAmount(it, state.focus) > P.FocusAmount(cur, state.focus))) then
        upgrades = upgrades + 1
        r.gainV = math.max(gain, 0.1)
      end
    end
    local rank = state.focus and (P.FocusAmount(it, state.focus) - P.FocusAmount(cur, state.focus)) * P.FOCUS_WEIGHT + gain or gain
    if it and not r.owned and rank > 0 and (not bestRow or rank > bestRow.rank) then bestRow = { slot = d, id = pid, rank = rank, gain = gain } end
  end

  if bestRow then
    local it = P.Item(bestRow.id)
    f.next.doll, f.next.itemId = bestRow.slot, bestRow.id
    local why = state.focus and ("+%d %s"):format(P.FocusAmount(it, state.focus) - P.FocusAmount(state.cur[bestRow.slot] and P.Item(state.cur[bestRow.slot]), state.focus), focusLabel(state.focus):lower()) or fmtGain(bestRow.gain)
    f.next.text:SetText(("|cffffd100Next step:|r %s for your %s (%s). %s"):format(colored(it), P.DOLL_LABEL[bestRow.slot]:lower(), why, P.SourceText(it)))
    f.nextPin:Hide()
    for _, s in ipairs(it.src or {}) do
      local m, x, y, title = P.SourcePin(s)
      if m then f.nextPin.m, f.nextPin.x, f.nextPin.y, f.nextPin.title = m, x, y, title f.nextPin:Show() break end
    end
  else
    f.next.doll, f.next.itemId = nil, nil
    f.nextPin:Hide()
    f.next.text:SetText("|cffffd100Next step:|r nothing. You have the best item in every slot for this plan.")
  end
  local focusNote = state.focus and (", %d %s in the full set"):format(focusTotal, focusLabel(state.focus):lower()) or ""
  f.foot:SetText(("%d upgrades at level %d%s. Same stat weights as forever-xp.com/bis (%s, %s). Forever build %s."):format(
    upgrades, state.level, focusNote, spec and spec.name or "", GOAL_NAME[state.goal] or "", P.DataBuild()))
  ns.BIS.Layout()
  ns.BIS.UpdatePins()
  if not state.selected or not plan[state.selected] then state.selected = bestRow and bestRow.slot or P.PAPERDOLL[1] end
  ns.BIS.RenderDetail()
end

function ns.BIS.UpdatePins()
  if not state or not state.plan then return end
  ns.Pins.Remember(state.plan, state.cur)
  if ns.Pins.Enabled() then
    local n = ns.Pins.Show(state.plan, state.cur)
    win.pins.label:SetText(("Pins on map and minimap (%d)"):format(n))
  else
    ns.Pins.Clear()
    win.pins.label:SetText("Pins on map and minimap")
  end
end

function ns.BIS.Toggle()
  if win and win:IsShown() then win:Hide() return end
  ns.BIS.Show()
end

function ns.BIS.Show()
  local cls = playerClass()
  if not P.CLASSES[cls] then ns.Print("The BIS planner doesn't know this class yet.") return end
  if not win then win = build() end
  if not state then
    state = { cls = cls, side = playerSide(), spec = guessSpec(cls), goal = "level", level = UnitLevel("player"),
      upgradesOnly = false, focus = ns.db.settings.bisFocus }
    if state.level >= 60 then state.goal = "pve" end
  end
  state.cls, state.side = cls, playerSide()
  win:Show()
  win.level:SetValue(state.level)
  win.upgrades:SetChecked(state.upgradesOnly)
  win.pins:SetChecked(ns.Pins.Enabled())
  ns.BIS.Refresh()
end

------------------------------------------------------------------------------------------
-- Minimap button
------------------------------------------------------------------------------------------
local function minimapButton()
  local b = CreateFrame("Button", "ForeverScoutMinimapButton", Minimap)
  b:SetSize(31, 31)
  b:SetFrameStrata("MEDIUM")
  b:SetFrameLevel(8)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:RegisterForDrag("LeftButton")
  b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  local overlay = b:CreateTexture(nil, "OVERLAY")
  overlay:SetSize(53, 53)
  overlay:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  overlay:SetPoint("TOPLEFT")
  local icon = b:CreateTexture(nil, "BACKGROUND")
  icon:SetSize(21, 21)
  icon:SetTexture("Interface\\AddOns\\ForeverScout\\logo")
  icon:SetPoint("TOPLEFT", 6, -5)
  b.icon = icon
  local dot = b:CreateTexture(nil, "OVERLAY", nil, 1)
  dot:SetSize(8, 8)
  dot:SetPoint("BOTTOMRIGHT", -6, 6)
  dot:SetTexture("Interface\\COMMON\\Indicator-Green")
  b.dot = dot

  local function place()
    local angle = math.rad(ns.db.settings.minimapAngle or 200)
    b:ClearAllPoints()
    b:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * 80, math.sin(angle) * 80)
  end
  b:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", function()
      local mx, my = Minimap:GetCenter()
      local cx, cy = GetCursorPosition()
      local scale = Minimap:GetEffectiveScale()
      cx, cy = cx / scale, cy / scale
      ns.db.settings.minimapAngle = math.deg(math.atan2(cy - my, cx - mx))
      place()
    end)
  end)
  b:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
  b:SetScript("OnClick", function(_, button)
    if button == "RightButton" then
      ns.db.settings.paused = not ns.db.settings.paused
      ns.Print(ns.db.settings.paused and "Recording paused. Right-click the minimap button or /fscout resume to continue." or "Recording resumed.")
      ns.BIS.UpdateDot()
    else
      ns.BIS.Toggle()
    end
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:AddLine("Forever|cFF4FC3F7Scout|r")
    GameTooltip:AddLine(ns.db.settings.paused and "|cffff5555Recording paused|r" or "|cff55ff55Recording|r", 1, 1, 1)
    GameTooltip:AddLine(ns.db.settings.share and "Sharing on" or "Sharing off (local only)", 0.8, 0.8, 0.8)
    GameTooltip:AddLine("Left-click: best in slot planner", 0.8, 0.8, 0.8)
    GameTooltip:AddLine("Right-click: pause or resume recording", 0.8, 0.8, 0.8)
    GameTooltip:AddLine("Drag to move", 0.6, 0.6, 0.6)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  place()
  return b
end

function ns.BIS.UpdateDot()
  local b = ns.BIS.button
  if not b then return end
  b.dot:SetTexture(ns.db.settings.paused and "Interface\\COMMON\\Indicator-Red" or "Interface\\COMMON\\Indicator-Green")
end

ns:On("PLAYER_LOGIN", function()
  if Minimap and not ns.db.settings.hideMinimap then
    ns.BIS.button = minimapButton()
    ns.BIS.UpdateDot()
  end
end)

ns:On("PLAYER_EQUIPMENT_CHANGED", function()
  if win and win:IsShown() then ns.BIS.Refresh() end
end)
