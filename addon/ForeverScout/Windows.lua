-- ForeverScout: copy windows for /fscout report and /fscout export

local ADDON, ns = ...

local window

local function getWindow()
  if window then return window end
  local f = CreateFrame("Frame", "ForeverScoutWindow", UIParent, "BackdropTemplate")
  f:SetSize(560, 420)
  f:SetPoint("CENTER")
  f:SetFrameStrata("DIALOG")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  if f.SetBackdrop then
    f:SetBackdrop({
      bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
      tile = true, tileSize = 32, edgeSize = 32,
      insets = { left = 11, right = 12, top = 12, bottom = 11 },
    })
  end

  f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  f.title:SetPoint("TOP", 0, -18)

  f.hint = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  f.hint:SetPoint("TOP", f.title, "BOTTOM", 0, -6)
  f.hint:SetWidth(500)

  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -6, -6)

  local scroll = CreateFrame("ScrollFrame", "ForeverScoutWindowScroll", f, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 22, -64)
  scroll:SetPoint("BOTTOMRIGHT", -40, 22)

  local edit = CreateFrame("EditBox", nil, scroll)
  edit:SetMultiLine(true)
  edit:SetAutoFocus(false)
  edit:SetFontObject(ChatFontNormal)
  edit:SetWidth(490)
  edit:SetScript("OnEscapePressed", function() f:Hide() end)
  scroll:SetScrollChild(edit)
  f.edit = edit

  tinsert(UISpecialFrames, "ForeverScoutWindow")
  window = f
  return f
end

function ns.ShowCopy(title, hint, text)
  local f = getWindow()
  f.title:SetText(title)
  f.hint:SetText(hint)
  f.edit:SetText(text)
  f.edit:HighlightText()
  f.edit:SetFocus()
  f:Show()
end

------------------------------------------------------------------------------------------
-- Compact serializer for exports (Lua table literal, readable by the ingest script)
------------------------------------------------------------------------------------------
local function serialize(v, out)
  local tv = type(v)
  if tv == "table" then
    out[#out + 1] = "{"
    local n = #v
    for i = 1, n do serialize(v[i], out) out[#out + 1] = "," end
    for k, val in pairs(v) do
      if not (type(k) == "number" and k >= 1 and k <= n and k % 1 == 0) then
        if type(k) == "string" and k:match("^[%a_][%w_]*$") then
          out[#out + 1] = k .. "="
        else
          out[#out + 1] = "["
          serialize(k, out)
          out[#out + 1] = "]="
        end
        serialize(val, out)
        out[#out + 1] = ","
      end
    end
    out[#out + 1] = "}"
  elseif tv == "string" then
    out[#out + 1] = string.format("%q", v):gsub("\\\n", "\\n")
  elseif tv == "number" or tv == "boolean" then
    out[#out + 1] = tostring(v)
  else
    out[#out + 1] = "nil"
  end
end

function ns.ShowExport()
  local char = ns.char
  if not char then return end
  local payload = { schema = ns.SCHEMA, charId = ns.charId, race = char.race,
                    class = char.class, faction = char.faction, sessions = char.sessions }
  local out = {}
  serialize(payload, out)
  local text = "FSCOUT1:" .. table.concat(out)
  ns.ShowCopy("ForeverScout export",
       "Ctrl+A, Ctrl+C, then paste into the project's submission form. "
       .. "Sending the SavedVariables\\ForeverScout.lua file works too and is better for long sessions.",
       text)
end

function ns.ShowReport()
  local lines = {}
  local version, build = GetBuildInfo()
  table.insert(lines, ("ForeverScout %s — client %s.%s"):format(ns.VERSION, tostring(version), tostring(build)))
  local _, race = UnitRace("player")
  local _, class = UnitClass("player")
  table.insert(lines, ("Character: level %d %s %s"):format(UnitLevel("player"), tostring(race), tostring(class)))
  table.insert(lines, "")
  if #ns.missing == 0 then
    if rawget(_G, "LibQuestieDB") then
      table.insert(lines, "Nothing missing from Questie found this session.")
    else
      table.insert(lines, "QuestieDB is not installed, so missing-data checks are off.")
    end
  else
    table.insert(lines, "Not in Questie's database (this session):")
    for _, line in ipairs(ns.missing) do table.insert(lines, "- " .. line) end
  end
  ns.ShowCopy("Missing from Questie",
       "Copy this and share it with the Questie team on their Discord (#bug-redirect).",
       table.concat(lines, "\n"))
end
