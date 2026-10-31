-- ForeverScout: the in-game BIS planner window (/fscout bis) and the minimap button.
-- Shows what the character is wearing next to the best item for every slot for a chosen spec
-- and goal, at the character's level or any level up to 60, with where each item comes from.
-- Everything here reads only the player's class, race, faction, level and equipped item IDs.

local ADDON, ns = ...
local P = ns.Planner
ns.BIS = {}

local WIN_W, WIN_H = 920, 640
local ROW_H, ROWS_W, ROWS_TOP = 26, 592, -120
local QUALITY_COLOR = { [0] = "9d9d9d", [1] = "ffffff", [2] = "1eff00", [3] = "0070dd", [4] = "a335ee", [5] = "ff8000" }
local GOAL_NAME = { pve = "PvE", pvp = "PvP", level = "Leveling" }
local QMARK = "Interface\\Icons\\INV_Misc_QuestionMark"

local win, state, srcWin

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

local statLines -- defined below

-- True when the game client can draw a tooltip for this item ID itself.
local function clientKnows(id)
  local info = (C_Item and C_Item.GetItemInfo or GetItemInfo)
  if not info then return false end
  local ok, name = pcall(info, id)
  return ok and name ~= nil
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

-- Name, quality and icon for an equipped item the planner's data doesn't have.
local function clientItem(id)
  local info = (C_Item and C_Item.GetItemInfo or GetItemInfo)
  if not info then return nil end
  local ok, name, _, quality, _, _, _, _, _, _, icon = pcall(info, id)
  if not ok or not name then return nil end
  return { n = name, q = quality or 1, i = nil, tex = icon }
end

local function makeButton(parent, text, width)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width or 120, 22)
  b:SetText(text)
  return b
end

local function fontString(parent, template, x, y, w, justify)
  local s = parent:CreateFontString(nil, "OVERLAY", template)
  if x then s:SetPoint("TOPLEFT", x, y) end
  if w then s:SetWidth(w) end
  s:SetJustifyH(justify or "LEFT")
  return s
end

------------------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------------------
local function buildRow(f, d)
  local r = CreateFrame("Button", nil, f)
  r:SetSize(ROWS_W, ROW_H)
  r.doll = d
  r.hl = r:CreateTexture(nil, "BACKGROUND")
  r.hl:SetAllPoints()
  r.hl:SetColorTexture(1, 1, 1, 0.07)
  r.hl:Hide()
  r.sel = r:CreateTexture(nil, "BACKGROUND")
  r.sel:SetAllPoints()
  r.sel:SetColorTexture(0.31, 0.76, 0.97, 0.18)
  r.sel:Hide()
  r.stripe = r:CreateTexture(nil, "BACKGROUND", nil, -1)
  r.stripe:SetAllPoints()
  r.stripe:SetColorTexture(1, 1, 1, 0.025)

  r.slot = fontString(r, "GameFontHighlightSmall", nil, nil, 68)
  r.slot:SetPoint("LEFT", 4, 0)
  r.slot:SetText(P.DOLL_LABEL[d])

  r.curIcon = r:CreateTexture(nil, "ARTWORK")
  r.curIcon:SetSize(18, 18)
  r.curIcon:SetPoint("LEFT", 76, 0)
  r.cur = fontString(r, "GameFontHighlightSmall", nil, nil, 178)
  r.cur:SetPoint("LEFT", 98, 0)
  r.cur:SetWordWrap(false)

  r.arrow = fontString(r, "GameFontDisableSmall", nil, nil, 16, "CENTER")
  r.arrow:SetPoint("LEFT", 280, 0)
  r.arrow:SetText(">")

  r.icon = r:CreateTexture(nil, "ARTWORK")
  r.icon:SetSize(18, 18)
  r.icon:SetPoint("LEFT", 300, 0)
  r.name = fontString(r, "GameFontHighlightSmall", nil, nil, 196)
  r.name:SetPoint("LEFT", 322, 0)
  r.name:SetWordWrap(false)

  r.gain = fontString(r, "GameFontHighlightSmall", nil, nil, 60, "RIGHT")
  r.gain:SetPoint("LEFT", 524, 0)

  r:SetScript("OnEnter", function(self)
    self.hl:Show()
    showItemTip(self, self.itemId)
  end)
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

  -- Controls: spec, goal, level, filter
  f.spec = makeButton(f, "Spec", 140)
  f.spec:SetPoint("TOPLEFT", 22, -44)
  f.spec:SetScript("OnClick", function()
    local specs = P.SPECS[state.cls] or {}
    for i, s in ipairs(specs) do
      if s.key == state.spec then state.spec = (specs[i + 1] or specs[1]).key break end
    end
    ns.BIS.Refresh()
  end)
  f.spec:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:SetText("Spec", 1, 1, 1)
    GameTooltip:AddLine("Click to switch between your class's specs.", 0.8, 0.8, 0.8)
    GameTooltip:Show()
  end)
  f.spec:SetScript("OnLeave", function() GameTooltip:Hide() end)

  f.goal = makeButton(f, "Goal", 100)
  f.goal:SetPoint("LEFT", f.spec, "RIGHT", 6, 0)
  f.goal:SetScript("OnClick", function()
    for i, g in ipairs(P.GOALS) do
      if g.key == state.goal then state.goal = (P.GOALS[i + 1] or P.GOALS[1]).key break end
    end
    ns.BIS.Refresh()
  end)
  f.goal:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:SetText("Gearing for", 1, 1, 1)
    GameTooltip:AddLine("Leveling, PvE (raids and dungeons) or PvP. Changes the stat weights.", 0.8, 0.8, 0.8)
    GameTooltip:Show()
  end)
  f.goal:SetScript("OnLeave", function() GameTooltip:Hide() end)

  f.levelLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.levelLabel:SetPoint("LEFT", f.goal, "RIGHT", 16, 0)
  f.levelLabel:SetText("Level |cffffffff60|r")

  local slider = CreateFrame("Slider", "ForeverScoutBISLevel", f, "OptionsSliderTemplate")
  slider:SetSize(170, 16)
  slider:SetPoint("LEFT", f.levelLabel, "RIGHT", 10, 0)
  slider:SetMinMaxValues(1, 60)
  slider:SetValueStep(1)
  slider:SetObeyStepOnDrag(true)
  _G[slider:GetName() .. "Low"]:SetText("1")
  _G[slider:GetName() .. "High"]:SetText("60")
  _G[slider:GetName() .. "Text"]:SetText("")
  slider:SetScript("OnValueChanged", function(self, v)
    v = math.floor(v + 0.5)
    f.levelLabel:SetText(("Level |cffffffff%d|r"):format(v))
    if v == state.level then return end
    state.level = v
    if ns.BIS.refreshTimer then ns.BIS.refreshTimer:Cancel() end
    ns.BIS.refreshTimer = C_Timer.NewTimer(0.2, ns.BIS.Refresh)
  end)
  f.level = slider

  f.myLevel = makeButton(f, "My level", 76)
  f.myLevel:SetPoint("LEFT", slider, "RIGHT", 16, 0)
  f.myLevel:SetScript("OnClick", function() f.level:SetValue(UnitLevel("player")) end)
  f.plus5 = makeButton(f, "+5", 40)
  f.plus5:SetPoint("LEFT", f.myLevel, "RIGHT", 4, 0)
  f.plus5:SetScript("OnClick", function() f.level:SetValue(math.min(60, state.level + 5)) end)

  local cb = CreateFrame("CheckButton", "ForeverScoutBISUpgrades", f, "UICheckButtonTemplate")
  cb:SetSize(24, 24)
  cb:SetPoint("LEFT", f.plus5, "RIGHT", 10, 0)
  _G[cb:GetName() .. "Text"]:SetText("Upgrades only")
  cb:SetScript("OnClick", function(self) state.upgradesOnly = self:GetChecked() and true or false ns.BIS.Layout() end)
  f.upgrades = cb

  f.sources = makeButton(f, "Sources", 90)
  f.sources:SetPoint("LEFT", cb, "RIGHT", 118, 0)
  f.sources:SetScript("OnClick", function() ns.BIS.ToggleSources() end)
  f:SetScript("OnHide", function() if srcWin then srcWin:Hide() end end)
  f.sources:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:SetText("Where items may come from", 1, 1, 1)
    GameTooltip:AddLine("Untick raids, PvP, crafting or anything you won't do, and the plan only uses the rest.", 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  f.sources:SetScript("OnLeave", function() GameTooltip:Hide() end)

  -- Next-step line (click to select that slot)
  local nextBtn = CreateFrame("Button", nil, f)
  nextBtn:SetPoint("TOPLEFT", 22, -74)
  nextBtn:SetSize(ROWS_W, 34)
  nextBtn.hl = nextBtn:CreateTexture(nil, "BACKGROUND")
  nextBtn.hl:SetAllPoints()
  nextBtn.hl:SetColorTexture(1, 0.82, 0, 0.06)
  nextBtn.text = fontString(nextBtn, "GameFontHighlight", nil, nil, ROWS_W - 8)
  nextBtn.text:SetPoint("LEFT", 4, 0)
  nextBtn.text:SetWordWrap(true)
  nextBtn:SetScript("OnClick", function(self)
    if self.doll then state.selected = self.doll ns.BIS.RenderDetail() end
  end)
  nextBtn:SetScript("OnEnter", function(self)
    if self.itemId then showItemTip(self, self.itemId, "ANCHOR_BOTTOMLEFT") end
  end)
  nextBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f.next = nextBtn

  -- Column headers
  local function header(text, x, w, justify)
    local h = fontString(f, "GameFontNormalSmall", x, ROWS_TOP + 14, w, justify)
    h:SetText(text)
    return h
  end
  header("Slot", 26, 70)
  header("You have", 98, 180)
  header("Best for this plan", 322, 190)
  header("Gain", 546, 60, "RIGHT")

  f.rows = {}
  for _, d in ipairs(P.PAPERDOLL) do f.rows[d] = buildRow(f, d) end

  -- Detail panel (right)
  local panel = CreateFrame("Frame", nil, f, "BackdropTemplate")
  panel:SetPoint("TOPLEFT", 636, -72)
  panel:SetPoint("BOTTOMRIGHT", -22, 52)
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
  panel.name = fontString(panel, "GameFontNormal", 56, -12, 190)
  panel.name:SetWordWrap(true)
  panel.sub = fontString(panel, "GameFontHighlightSmall", 56, -30, 190)
  panel.body = fontString(panel, "GameFontHighlightSmall", 12, -60)
  panel.body:SetPoint("RIGHT", -12, 0)
  panel.body:SetJustifyV("TOP")
  panel.body:SetWordWrap(true)
  panel.body:SetSpacing(2)
  panel:EnableMouse(true)
  panel:SetScript("OnEnter", function(self) if state.selected then showItemTip(self, state.plan[state.selected], "ANCHOR_LEFT") end end)
  panel:SetScript("OnLeave", function() GameTooltip:Hide() end)

  -- Footer
  f.foot = fontString(f, "GameFontDisableSmall", 24, nil, 600)
  f.foot:ClearAllPoints()
  f.foot:SetPoint("BOTTOMLEFT", 24, 22)
  f.foot:SetWordWrap(false)

  f.copy = makeButton(f, "Copy gear for the site", 160)
  f.copy:SetPoint("BOTTOMRIGHT", -22, 18)
  f.copy:SetScript("OnClick", function() ns.ShowGear() end)
  f.copy:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText("forever-xp.com/bis", 1, 1, 1)
    GameTooltip:AddLine("Copies your gear as text to paste on the site, where you can edit stat weights and share the plan.", 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  f.copy:SetScript("OnLeave", function() GameTooltip:Hide() end)

  return f
end

------------------------------------------------------------------------------------------
-- Source filter popup
------------------------------------------------------------------------------------------
local function sourceSet()
  local saved = ns.db.settings.bisSources
  local set = {}
  for _, k in ipairs(P.SOURCE_KINDS) do
    set[k.key] = not (saved and saved[k.key] == false)
  end
  return set
end

local function buildSources()
  local f = CreateFrame("Frame", "ForeverScoutBISSources", win, "BackdropTemplate")
  f:SetSize(230, 24 * #P.SOURCE_KINDS + 60)
  f:SetPoint("TOPLEFT", win.sources, "BOTTOMLEFT", 0, -4)
  f:SetFrameStrata("DIALOG")
  f:EnableMouse(true)
  if f.SetBackdrop then
    f:SetBackdrop({ bgFile = "Interface\\Tooltips\\UI-Tooltip-Background", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
      tile = true, tileSize = 16, edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } })
    f:SetBackdropColor(0, 0, 0, 0.92)
    f:SetBackdropBorderColor(0.5, 0.45, 0.3, 1)
  end
  local title = fontString(f, "GameFontNormal", 12, -10, 200)
  title:SetText("Where items may come from")
  f.checks = {}
  for i, k in ipairs(P.SOURCE_KINDS) do
    local cb = CreateFrame("CheckButton", "ForeverScoutBISSource" .. i, f, "UICheckButtonTemplate")
    cb:SetSize(22, 22)
    cb:SetPoint("TOPLEFT", 10, -26 - (i - 1) * 24)
    _G[cb:GetName() .. "Text"]:SetText(k.name)
    cb.key = k.key
    cb:SetScript("OnClick", function(self)
      ns.db.settings.bisSources = ns.db.settings.bisSources or {}
      ns.db.settings.bisSources[self.key] = self:GetChecked() and true or false
      ns.BIS.Refresh()
    end)
    f.checks[k.key] = cb
  end
  local all = makeButton(f, "All", 60)
  all:SetPoint("BOTTOMLEFT", 10, 8)
  all:SetScript("OnClick", function() ns.db.settings.bisSources = nil ns.BIS.ToggleSources(true) ns.BIS.Refresh() end)
  local none = makeButton(f, "None", 60)
  none:SetPoint("LEFT", all, "RIGHT", 4, 0)
  none:SetScript("OnClick", function()
    ns.db.settings.bisSources = {}
    for _, k in ipairs(P.SOURCE_KINDS) do ns.db.settings.bisSources[k.key] = false end
    ns.BIS.ToggleSources(true) ns.BIS.Refresh()
  end)
  return f
end

function ns.BIS.ToggleSources(keepOpen)
  if not srcWin then srcWin = buildSources() end
  if srcWin:IsShown() and not keepOpen then srcWin:Hide() return end
  local set = sourceSet()
  for key, cb in pairs(srcWin.checks) do cb:SetChecked(set[key]) end
  srcWin:Show()
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
  for _, r in pairs(f.rows) do if r.doll == d then r.sel:Show() else r.sel:Hide() end end
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
  L[#L + 1] = ""
  L[#L + 1] = "|cffffd100Where to get it|r"
  if it.src and #it.src > 0 then
    for _, s in ipairs(it.src) do
      local line = P.SourceText({ src = { s } })
      if s.t == "quest" and s.lv then line = line .. (" (quest level %d)"):format(s.lv)
      elseif s.lv then line = line .. (" (level %d)"):format(s.lv) end
      L[#L + 1] = "- " .. line
    end
  else
    L[#L + 1] = "- Not known yet. Players running ForeverScout fill this in as they loot."
  end
  if it.set then
    local set = P.Set(it.set)
    if set then
      L[#L + 1] = ""
      L[#L + 1] = "|cffffd100" .. set.n .. "|r"
      for _, b in ipairs(set.b or {}) do L[#L + 1] = ("(%d) %s"):format(b[1], b[2]) end
    end
  end

  L[#L + 1] = ""
  L[#L + 1] = "|cffffd100Compared with what you have|r"
  local curId = state.cur[d]
  local cur = curId and P.Item(curId)
  if curId == id then
    L[#L + 1] = "|cff55ff55You're wearing it.|r"
  elseif cur then
    local gain = P.Value(state.opts, state.weights, d, it) - P.Value(state.opts, state.weights, d, cur)
    L[#L + 1] = ("%s score over %s."):format(fmtGain(gain), colored(cur))
    L[#L + 1] = ("|cff9d9d9dShift-hover any row to compare tooltips.|r")
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
  local y = ROWS_TOP
  local shown = 0
  for i, d in ipairs(P.PAPERDOLL) do
    local r = f.rows[d]
    local hide = state.upgradesOnly and (r.owned or not r.itemId or (r.gainV or 0) <= 0)
    if hide then
      r:Hide()
    else
      r:ClearAllPoints()
      r:SetPoint("TOPLEFT", 22, y)
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

  local sources, limited = sourceSet(), 0
  for _, k in ipairs(P.SOURCE_KINDS) do if not sources[k.key] then limited = limited + 1 end end
  f.sources:SetText(limited > 0 and ("Sources (%d off)"):format(limited) or "Sources")
  state.opts = { cls = state.cls, spec = state.spec, goal = state.goal, level = state.level, side = state.side, sources = sources }
  local plan, w = P.Suggest(state.opts)
  state.plan, state.weights = plan, w
  state.cur = P.Equipped()
  local rows = P.Compare(state.opts, plan, state.cur, w)

  local bestRow, upgrades = nil, 0
  for _, row in ipairs(rows) do
    local r = f.rows[row.slot]
    local it = row.plan and P.Item(row.plan)
    local cur = row.cur and P.Item(row.cur)
    r.itemId, r.gainV = row.plan, row.gain
    r.owned = row.cur ~= nil and row.cur == row.plan
    r.icon:SetTexture(it and iconOf(row.plan, it) or nil)
    r.name:SetText(colored(it, "none at this level"))
    if cur then
      r.curIcon:SetTexture(iconOf(row.cur, cur))
      r.cur:SetText(colored(cur))
    elseif row.cur then
      local ci = clientItem(row.cur)
      r.curIcon:SetTexture(ci and ci.tex or iconOf(row.cur))
      r.cur:SetText(ci and colored(ci) or ("|cffffffffItem " .. row.cur .. "|r"))
    else
      r.curIcon:SetTexture(nil)
      r.cur:SetText("|cff9d9d9dempty|r")
    end
    if r.owned then
      r.gain:SetText("|cff55ff55have|r")
      r.arrow:SetText("=")
    else
      r.gain:SetText(it and fmtGain(row.gain) or "")
      r.arrow:SetText(">")
      if it and row.gain > 0 then upgrades = upgrades + 1 end
    end
    if it and not r.owned and row.gain > 0 and (not bestRow or row.gain > bestRow.gain) then bestRow = row end
  end

  if bestRow then
    local it = P.Item(bestRow.plan)
    f.next.doll, f.next.itemId = bestRow.slot, bestRow.plan
    f.next.text:SetText(("|cffffd100Next step:|r %s for your %s (%s). %s"):format(
      colored(it), P.DOLL_LABEL[bestRow.slot]:lower(), fmtGain(bestRow.gain), P.SourceText(it)))
  else
    f.next.doll, f.next.itemId = nil, nil
    f.next.text:SetText("|cffffd100Next step:|r nothing. You have the best item in every slot for this plan.")
  end
  f.foot:SetText(("%d upgrades at level %d. Same stat weights as forever-xp.com/bis (%s, %s). Forever build %s."):format(
    upgrades, state.level, spec and spec.name or "", GOAL_NAME[state.goal] or "", P.DataBuild()))
  ns.BIS.Layout()
  if not state.selected or not plan[state.selected] then
    state.selected = bestRow and bestRow.slot or P.PAPERDOLL[1]
  end
  ns.BIS.RenderDetail()
end

function ns.BIS.Toggle()
  if win and win:IsShown() then win:Hide() if srcWin then srcWin:Hide() end return end
  ns.BIS.Show()
end

function ns.BIS.Show()
  local cls = playerClass()
  if not P.CLASSES[cls] then ns.Print("The BIS planner doesn't know this class yet.") return end
  if not win then win = build() end
  if not state then
    state = { cls = cls, side = playerSide(), spec = guessSpec(cls), goal = "level", level = UnitLevel("player"), upgradesOnly = false }
    if state.level >= 60 then state.goal = "pve" end
  end
  state.cls, state.side = cls, playerSide()
  win:Show()
  win.level:SetValue(state.level)
  win.upgrades:SetChecked(state.upgradesOnly)
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
