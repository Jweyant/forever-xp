-- ForeverScout: copy windows for /fscout report and /fscout export

local ADDON, ns = ...

local window
local FLAT = "Interface\\Buttons\\WHITE8X8"
local SIZES = { compact = { 400, 150 }, full = { 500, 320 } }

local function flat(frame, r, g, b, a, br, bg, bb, ba)
  if not frame.SetBackdrop then return end
  frame:SetBackdrop({ bgFile = FLAT, edgeFile = FLAT, edgeSize = 1 })
  frame:SetBackdropColor(r, g, b, a)
  frame:SetBackdropBorderColor(br, bg, bb, ba)
end

local function getWindow()
  if window then return window end
  local f = CreateFrame("Frame", "ForeverScoutWindow", UIParent, "BackdropTemplate")
  f:SetPoint("CENTER", 0, 120)
  f:SetFrameStrata("DIALOG")
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  flat(f, 0.05, 0.05, 0.07, 0.94, 0, 0, 0, 0.9)

  -- Thin gold accent along the top, like the site's cards.
  local accent = f:CreateTexture(nil, "ARTWORK")
  accent:SetTexture(FLAT)
  accent:SetVertexColor(0.91, 0.72, 0.18, 0.9)
  accent:SetPoint("TOPLEFT", 1, -1)
  accent:SetPoint("TOPRIGHT", -1, -1)
  accent:SetHeight(2)

  f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.title:SetPoint("TOPLEFT", 12, -12)
  f.title:SetJustifyH("LEFT")

  local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
  close:SetSize(22, 22)
  close:SetPoint("TOPRIGHT", -4, -4)

  f.hint = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  f.hint:SetPoint("TOPLEFT", f.title, "BOTTOMLEFT", 0, -6)
  f.hint:SetPoint("RIGHT", f, "RIGHT", -12, 0)
  f.hint:SetJustifyH("LEFT")
  f.hint:SetWordWrap(true)

  -- Darker inset for the text, scrollable for long reports.
  local box = CreateFrame("Frame", nil, f, "BackdropTemplate")
  box:SetPoint("TOPLEFT", f.hint, "BOTTOMLEFT", 0, -8)
  box:SetPoint("BOTTOMRIGHT", -12, 12)
  flat(box, 0, 0, 0, 0.55, 1, 1, 1, 0.12)

  local scroll = CreateFrame("ScrollFrame", "ForeverScoutWindowScroll", box, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 6, -6)
  scroll:SetPoint("BOTTOMRIGHT", -24, 6)

  local edit = CreateFrame("EditBox", nil, scroll)
  edit:SetMultiLine(true)
  edit:SetAutoFocus(false)
  edit:SetFontObject(ChatFontSmall or ChatFontNormal)
  edit:SetTextColor(0.9, 0.9, 0.9)
  edit:SetScript("OnEscapePressed", function() f:Hide() end)
  edit:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
  -- Read-only: typing puts the original text back, so the copy can't be broken by accident.
  edit:SetScript("OnTextChanged", function(self, user) if user and f.text then self:SetText(f.text) self:HighlightText() end end)
  scroll:SetScrollChild(edit)
  scroll:SetScript("OnSizeChanged", function(_, w) edit:SetWidth(w) end)
  f.edit, f.scroll = edit, scroll

  tinsert(UISpecialFrames, "ForeverScoutWindow")
  window = f
  return f
end

--- Show text to copy. `compact` gives a small window for one-line strings like /fscout gear.
function ns.ShowCopy(title, hint, text, compact)
  local f = getWindow()
  local w, h = unpack(compact and SIZES.compact or SIZES.full)
  f:SetSize(w, h)
  f.edit:SetWidth(w - 54)
  f.title:SetText(title)
  f.hint:SetText(hint)
  f.text = text
  f.edit:SetText(text)
  f:Show()
  f.edit:SetFocus()
  f.edit:HighlightText()
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
