-- ForeverScout: the in-game BIS planner window (/fscout bis) and the minimap button.
-- Shows the best item for every slot for this character's class, a chosen spec and goal, at the
-- character's level (or a higher one), next to what is equipped, with where each item comes from.
-- Everything here reads only the player's class, race, faction, level and equipped item IDs.

local ADDON, ns = ...
local P = ns.Planner
ns.BIS = {}

local ROW_H, ROWS_W = 26, 330
local QUALITY_COLOR = { [0] = "9d9d9d", [1] = "ffffff", [2] = "1eff00", [3] = "0070dd", [4] = "a335ee", [5] = "ff8000" }
local GOAL_NAME = { pve = "PvE", pvp = "PvP", level = "Leveling" }

local win, state

------------------------------------------------------------------------------------------
-- Helpers
------------------------------------------------------------------------------------------
local function playerClass()
  local _, cls = UnitClass("player")
  return cls
end

local function playerSide()
  return UnitFactionGroup("player") == "Horde" and "H" or "A"
end

local function colored(it)
  if not it then return "|cff9d9d9dnothing|r" end
  return ("|cff%s%s|r"):format(QUALITY_COLOR[it.q] or "ffffff", it.n)
end

local function iconOf(id, it)
  local tex
  if C_Item and C_Item.GetItemIconByID then tex = C_Item.GetItemIconByID(id)
  elseif GetItemIcon then tex = GetItemIcon(id) end
  if not tex and it and it.i then tex = "Interface\\Icons\\" .. it.i end
  return tex or "Interface\\Icons\\INV_Misc_QuestionMark"
end

local function fmtGain(v)
  if v > 0.05 then return ("|cff55ff55+%.0f|r"):format(v) end
  if v < -0.05 then return ("|cffff5555%.0f|r"):format(v) end
  return "|cff9d9d9d=|r"
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

local function showItemTip(owner, id)
  if not id then return end
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  local ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. id)
  if not ok then GameTooltip:SetText("Item " .. id) end
  GameTooltip:Show()
end

------------------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------------------
local function makeButton(parent, text, width)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width or 120, 22)
  b:SetText(text)
  return b
end

local function build()
  local f = CreateFrame("Frame", "ForeverScoutBIS", UIParent, "BackdropTemplate")
  f:SetSize(720, 560)
  f:SetPoint("CENTER")
  f:SetFrameStrata("HIGH")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:SetClampedToScreen(true)
  if f.SetBackdrop then
    f:SetBackdrop({
      bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
      tile = true, tileSize = 32, edgeSize = 32,
      insets = { left = 11, right = 12, top = 12, bottom = 11 },
    })
  end
  tinsert(UISpecialFrames, "ForeverScoutBIS")

  f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  f.title:SetPoint("TOP", 0, -16)
  f.title:SetText("Forever|cFF4FC3F7XP|r best in slot")

  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -6, -6)

  -- Controls row: spec, goal, level
  f.spec = makeButton(f, "Spec", 150)
  f.spec:SetPoint("TOPLEFT", 22, -44)
  f.spec:SetScript("OnClick", function()
    local specs = P.SPECS[state.cls] or {}
    for i, s in ipairs(specs) do
      if s.key == state.spec then state.spec = (specs[i + 1] or specs[1]).key break end
    end
    ns.BIS.Refresh()
  end)

  f.goal = makeButton(f, "Goal", 110)
  f.goal:SetPoint("LEFT", f.spec, "RIGHT", 6, 0)
  f.goal:SetScript("OnClick", function()
    for i, g in ipairs(P.GOALS) do
      if g.key == state.goal then state.goal = (P.GOALS[i + 1] or P.GOALS[1]).key break end
    end
    ns.BIS.Refresh()
  end)

  f.levelLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  f.levelLabel:SetPoint("LEFT", f.goal, "RIGHT", 14, 0)
  f.levelLabel:SetText("Plan for level")

  local slider = CreateFrame("Slider", "ForeverScoutBISLevel", f, "OptionsSliderTemplate")
  slider:SetSize(150, 16)
  slider:SetPoint("LEFT", f.levelLabel, "RIGHT", 10, 0)
  slider:SetMinMaxValues(1, 60)
  slider:SetValueStep(1)
  slider:SetObeyStepOnDrag(true)
  _G[slider:GetName() .. "Low"]:SetText("")
  _G[slider:GetName() .. "High"]:SetText("")
  slider:SetScript("OnValueChanged", function(self, v)
    v = math.floor(v + 0.5)
    if v == state.level then return end
    state.level = v
    _G[self:GetName() .. "Text"]:SetText(v)
    if ns.BIS.refreshTimer then ns.BIS.refreshTimer:Cancel() end
    ns.BIS.refreshTimer = C_Timer.NewTimer(0.25, ns.BIS.Refresh)
  end)
  f.level = slider

  f.myLevel = makeButton(f, "My level", 80)
  f.myLevel:SetPoint("LEFT", slider, "RIGHT", 12, 0)
  f.myLevel:SetScript("OnClick", function() f.level:SetValue(UnitLevel("player")) end)

  -- Next-step line
  f.next = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  f.next:SetPoint("TOPLEFT", 24, -78)
  f.next:SetWidth(670)
  f.next:SetJustifyH("LEFT")
  f.next:SetWordWrap(true)

  -- Column headers
  local function header(text, x, w)
    local h = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    h:SetPoint("TOPLEFT", x, -108)
    h:SetWidth(w)
    h:SetJustifyH("LEFT")
    h:SetText(text)
    return h
  end
  header("Slot", 24, 80)
  header("Best in slot", 104, 180)
  header("Gain", 300, 50)

  -- Slot rows
  f.rows = {}
  for i, d in ipairs(P.PAPERDOLL) do
    local r = CreateFrame("Button", nil, f)
    r:SetSize(ROWS_W, ROW_H)
    r:SetPoint("TOPLEFT", 22, -122 - (i - 1) * ROW_H)
    r.hl = r:CreateTexture(nil, "BACKGROUND")
    r.hl:SetAllPoints()
    r.hl:SetColorTexture(1, 1, 1, 0.08)
    r.hl:Hide()
    r.sel = r:CreateTexture(nil, "BACKGROUND")
    r.sel:SetAllPoints()
    r.sel:SetColorTexture(0.31, 0.76, 0.97, 0.18)
    r.sel:Hide()
    r.slot = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.slot:SetPoint("LEFT", 2, 0)
    r.slot:SetWidth(76)
    r.slot:SetJustifyH("LEFT")
    r.slot:SetText(P.DOLL_LABEL[d])
    r.icon = r:CreateTexture(nil, "ARTWORK")
    r.icon:SetSize(20, 20)
    r.icon:SetPoint("LEFT", 82, 0)
    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.name:SetPoint("LEFT", 106, 0)
    r.name:SetWidth(170)
    r.name:SetJustifyH("LEFT")
    r.name:SetWordWrap(false)
    r.gain = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.gain:SetPoint("LEFT", 280, 0)
    r.gain:SetWidth(48)
    r.gain:SetJustifyH("RIGHT")
    r.doll = d
    r:SetScript("OnEnter", function(self) self.hl:Show() showItemTip(self, self.itemId) end)
    r:SetScript("OnLeave", function(self) self.hl:Hide() GameTooltip:Hide() end)
    r:SetScript("OnClick", function(self) state.selected = self.doll ns.BIS.RenderDetail() end)
    f.rows[d] = r
  end

  -- Detail panel (right)
  local panel = CreateFrame("Frame", nil, f, "BackdropTemplate")
  panel:SetPoint("TOPLEFT", 366, -104)
  panel:SetPoint("BOTTOMRIGHT", -22, 50)
  if panel.SetBackdrop then
    panel:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
      tile = true, tileSize = 16, edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    panel:SetBackdropColor(0, 0, 0, 0.6)
    panel:SetBackdropBorderColor(0.5, 0.45, 0.3, 1)
  end
  f.panel = panel
  panel.icon = panel:CreateTexture(nil, "ARTWORK")
  panel.icon:SetSize(36, 36)
  panel.icon:SetPoint("TOPLEFT", 12, -12)
  panel.name = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  panel.name:SetPoint("TOPLEFT", 56, -12)
  panel.name:SetWidth(260)
  panel.name:SetJustifyH("LEFT")
  panel.sub = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  panel.sub:SetPoint("TOPLEFT", 56, -30)
  panel.sub:SetWidth(260)
  panel.sub:SetJustifyH("LEFT")
  panel.body = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  panel.body:SetPoint("TOPLEFT", 12, -58)
  panel.body:SetPoint("RIGHT", -12, 0)
  panel.body:SetJustifyH("LEFT")
  panel.body:SetJustifyV("TOP")
  panel.body:SetWordWrap(true)
  panel.body:SetSpacing(2)
  panel:EnableMouse(true)
  panel:SetScript("OnEnter", function(self) if state.selected then showItemTip(self, state.plan[state.selected]) end end)
  panel:SetScript("OnLeave", function() GameTooltip:Hide() end)

  -- Footer
  f.foot = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  f.foot:SetPoint("BOTTOMLEFT", 24, 24)
  f.foot:SetWidth(430)
  f.foot:SetJustifyH("LEFT")

  f.copy = makeButton(f, "Copy to forever-xp.com", 160)
  f.copy:SetPoint("BOTTOMRIGHT", -22, 20)
  f.copy:SetScript("OnClick", function() ns.ShowGear() end)

  return f
end

------------------------------------------------------------------------------------------
-- Rendering
------------------------------------------------------------------------------------------
local function statLines(it)
  local L = {}
  if it.w then L[#L + 1] = ("%d - %d damage, speed %.2f (%.1f DPS)"):format(it.w[1], it.w[2], it.w[3], it.st.dps or 0) end
  if it.st.armor then L[#L + 1] = ("%d Armor"):format(it.st.armor) end
  for _, k in ipairs({ "str", "agi", "sta", "int", "spi" }) do
    if it.st[k] then L[#L + 1] = ("+%d %s"):format(it.st[k], P.STAT_LABEL[k]) end
  end
  local extra = {}
  for k, v in pairs(it.st) do
    if not (k == "str" or k == "agi" or k == "sta" or k == "int" or k == "spi" or k == "armor" or k == "dps") then
      extra[#extra + 1] = k
    end
  end
  table.sort(extra)
  for _, k in ipairs(extra) do
    local label = P.STAT_LABEL[k] or k
    if k:sub(-4) == "_pct" then L[#L + 1] = ("|cff1eff00Equip: Improves %s by %s%%.|r"):format(label:gsub(" %%", ""), tostring(it.st[k]))
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
  if not it then
    p.icon:SetTexture(nil)
    p.name:SetText("Pick a slot")
    p.sub:SetText("")
    p.body:SetText("Click a row on the left to see the item, its stats and where to get it.")
    return
  end
  p.icon:SetTexture(iconOf(id, it))
  p.name:SetText(colored(it))
  local curId = state.cur[d]
  local cur = curId and P.Item(curId)
  p.sub:SetText(("Item level %d, needs level %d"):format(it.il, it.lv))
  local L = statLines(it)
  L[#L + 1] = ""
  L[#L + 1] = "|cffffd100Where to get it|r"
  if it.src and #it.src > 0 then
    for i, s in ipairs(it.src) do
      local one = { n = it.n, src = { s } }
      local line = P.SourceText(one)
      if s.lv and s.t ~= "quest" then line = line .. (" (level %d)"):format(s.lv) end
      if s.t == "quest" and s.lv then line = line .. (" (quest level %d)"):format(s.lv) end
      L[#L + 1] = "- " .. line
    end
  else
    L[#L + 1] = "- Source not known yet. Scouts with ForeverScout fill this in as they loot."
  end
  L[#L + 1] = ""
  L[#L + 1] = "|cffffd100You have|r"
  if cur then
    local gain = P.Value(state.opts, state.weights, d, it) - P.Value(state.opts, state.weights, d, cur)
    L[#L + 1] = ("%s (%s)"):format(colored(cur), fmtGain(gain) .. " score")
  elseif curId then
    L[#L + 1] = ("Item %d (not in the planner's data yet)"):format(curId)
  else
    L[#L + 1] = "Nothing equipped here."
  end
  p.body:SetText(table.concat(L, "\n"))
  for _, r in pairs(f.rows) do if r.doll == d then r.sel:Show() else r.sel:Hide() end end
end

function ns.BIS.Refresh()
  if not win or not win:IsShown() then return end
  if not P.LoadData() then
    win.next:SetText("|cffff5555Item data (ForeverScout_Data) could not be loaded.|r Reinstall ForeverScout from CurseForge.")
    return
  end
  local f = win
  local spec = P.Spec(state.cls, state.spec)
  f.spec:SetText(spec and spec.name or "Spec")
  f.goal:SetText(GOAL_NAME[state.goal] or state.goal)
  _G[f.level:GetName() .. "Text"]:SetText(state.level)

  state.opts = { cls = state.cls, spec = state.spec, goal = state.goal, level = state.level, side = state.side }
  local plan, w = P.Suggest(state.opts)
  state.plan, state.weights = plan, w
  state.cur = P.Equipped()
  local rows = P.Compare(state.opts, plan, state.cur, w)

  local bestRow
  for _, row in ipairs(rows) do
    local r = f.rows[row.slot]
    local it = row.plan and P.Item(row.plan)
    r.itemId = row.plan
    r.icon:SetTexture(it and iconOf(row.plan, it) or nil)
    r.name:SetText(colored(it))
    local owned = row.cur and row.plan and row.cur == row.plan
    r.gain:SetText(owned and "|cff55ff55have|r" or fmtGain(row.gain))
    if it and not owned and row.gain > 0 and (not bestRow or row.gain > bestRow.gain) then bestRow = row end
  end
  if bestRow then
    local it = P.Item(bestRow.plan)
    f.next:SetText(("|cffffd100Next step:|r %s for your %s (%s). %s"):format(
      colored(it), P.DOLL_LABEL[bestRow.slot]:lower(), fmtGain(bestRow.gain), P.SourceText(it)))
  else
    f.next:SetText("|cffffd100Next step:|r you already have the best item in every slot for this plan.")
  end
  f.foot:SetText(("Forever build %s. Scores use the same stat weights as forever-xp.com/bis for %s %s. Open the site for custom weights."):format(
    P.DataBuild(), spec and spec.name or "", GOAL_NAME[state.goal] or ""))
  if not state.selected or not plan[state.selected] then
    state.selected = bestRow and bestRow.slot or P.PAPERDOLL[1]
  end
  ns.BIS.RenderDetail()
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
    state = { cls = cls, side = playerSide(), spec = guessSpec(cls), goal = "level", level = UnitLevel("player") }
    if state.level >= 60 then state.goal = "pve" end
  end
  state.cls, state.side = cls, playerSide()
  win:Show()
  win.level:SetValue(state.level)
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
  icon:SetSize(20, 20)
  icon:SetTexture("Interface\\Icons\\INV_Misc_Map_01")
  icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
  icon:SetPoint("TOPLEFT", 7, -5)
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
