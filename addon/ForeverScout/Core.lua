-- ForeverScout: Core
-- Saved data layout (account-wide, no player names or realms are ever stored):
-- ForeverScoutDB = {
--   schema = 1,
--   chars = {
--     [charId] = { race, class, faction, sessions = {
--       { start = epoch, build = "1.60.1.69913", startLevel, startXP, startMaxXP,
--         events = { {t, kind, ...}, ... },   -- t = seconds since session start
--         crumbs = { "t,map,x,y,flags", ... } },
--     } },
--   },
--   settings = { paused = false, crumbSeconds = 10, share = true|false|nil, shareAsked, minimapAngle, hideMinimap },
-- ForeverScoutCharDB = { charId }   -- per character, never uploaded
-- }

local ADDON, ns = ...
ns.SCHEMA = 1
ns.VERSION = "0.2.1"

local GetTime, time, floor = GetTime, time, math.floor

ns.frame = CreateFrame("Frame")
ns.handlers = {}

function ns:On(event, fn)
  if not self.handlers[event] then
    self.handlers[event] = {}
    self.frame:RegisterEvent(event)
  end
  table.insert(self.handlers[event], fn)
end

ns.frame:SetScript("OnEvent", function(_, event, ...)
  local list = ns.handlers[event]
  if not list then return end
  for i = 1, #list do
    local ok, err = pcall(list[i], ...)
    if not ok and ns.debug then print("|cffff5555ForeverScout error|r", event, err) end
  end
end)

function ns.Print(msg)
  DEFAULT_CHAT_FRAME:AddMessage("|cFF4FC3F7ForeverScout:|r " .. tostring(msg))
end

------------------------------------------------------------------------------------------
-- Safe helpers. Forever can return "secret" values for some unit data; never touch them.
------------------------------------------------------------------------------------------
local function isSecret(v)
  return issecretvalue and issecretvalue(v) or false
end
ns.isSecret = isSecret

-- Returns "npc"/"object"/nil, id from a GUID like "Creature-0-1-2-3-3143-0000ABCD".
function ns.ParseGUID(guid)
  if not guid or isSecret(guid) or type(guid) ~= "string" then return nil end
  local kind, _, _, _, _, id = strsplit("-", guid)
  id = tonumber(id)
  if not id then return nil end
  if kind == "Creature" or kind == "Vehicle" then return "npc", id end
  if kind == "GameObject" then return "object", id end
  return nil
end

function ns.UnitNpcId(unit)
  if not UnitExists(unit) then return nil end
  local ok, guid = pcall(UnitGUID, unit)
  if not ok then return nil end
  local kind, id = ns.ParseGUID(guid)
  return kind, id
end

local function round2(v) return floor(v * 10000 + 0.5) / 100 end -- 0..1 -> 0..100, 2 decimals

-- Current position: uiMapID, x, y (map percent 0-100). nil inside most instances.
function ns.Position()
  if not C_Map or not C_Map.GetBestMapForUnit then return nil end
  local mapID = C_Map.GetBestMapForUnit("player")
  if not mapID then return nil end
  local pos = C_Map.GetPlayerMapPosition(mapID, "player")
  if not pos then return mapID end
  local x, y = pos:GetXY()
  if not x or isSecret(x) then return mapID end
  return mapID, round2(x), round2(y)
end

------------------------------------------------------------------------------------------
-- Database / session
------------------------------------------------------------------------------------------
local function newId()
  local t = {}
  for i = 1, 12 do t[i] = string.format("%x", math.random(0, 15)) end
  return table.concat(t)
end

function ns:InitDB()
  ForeverScoutDB = ForeverScoutDB or {}
  local db = ForeverScoutDB
  db.schema = ns.SCHEMA
  db.chars = db.chars or {}
  db.charIndex = nil                  -- removed in 0.2: ids now live in per-character data
  db.settings = db.settings or {}
  if db.settings.paused == nil then db.settings.paused = false end
  db.settings.crumbSeconds = db.settings.crumbSeconds or 10
  self.db = db

  -- Each character keeps its own random id in per-character SavedVariables, so the shared
  -- account file links sessions without any name, realm or GUID-derived value.
  ForeverScoutCharDB = ForeverScoutCharDB or {}
  if not ForeverScoutCharDB.charId then ForeverScoutCharDB.charId = newId() end
  local charId = ForeverScoutCharDB.charId
  self.charId = charId

  local _, race = UnitRace("player")
  local _, class = UnitClass("player")
  local faction = UnitFactionGroup("player")
  local char = db.chars[charId] or { sessions = {} }
  char.race, char.class, char.faction = race, class, faction
  db.chars[charId] = char
  self.char = char
end

function ns:StartSession()
  local version, build = GetBuildInfo()
  self.session = {
    start = time(),
    build = tostring(version) .. "." .. tostring(build),
    addon = ns.VERSION,
    startLevel = UnitLevel("player"),
    startXP = UnitXP("player"),
    startMaxXP = UnitXPMax("player"),
    events = {},
    crumbs = {},
  }
  self.sessionStartClock = GetTime()
  table.insert(self.char.sessions, self.session)
end

-- Seconds since session start (integer, survives client clock changes).
function ns:Now()
  return floor(GetTime() - (self.sessionStartClock or GetTime()) + 0.5)
end

-- Append an event: kind plus a field table. Position is attached automatically.
function ns:Log(kind, fields)
  if not self.session or self.db.settings.paused then return end
  local e = fields or {}
  e.t = self:Now()
  e.k = kind
  e.lvl = UnitLevel("player")
  local map, x, y = ns.Position()
  e.map, e.x, e.y = map, x, y
  table.insert(self.session.events, e)
  return e
end

------------------------------------------------------------------------------------------
-- Questie cross-check (optional). Flags quests/NPCs the installed QuestieDB doesn't know.
------------------------------------------------------------------------------------------
local function questieLib()
  return rawget(_G, "LibQuestieDB")
end

local function knownTo(entityName, id)
  local lib = questieLib()
  if not lib or not lib[entityName] or not id then return nil end -- nil = can't tell
  local ok, name = pcall(lib[entityName].Get, id, "name")
  if not ok then return nil end
  return type(name) == "string" and name ~= ""
end
ns.KnownToQuestie = knownTo

------------------------------------------------------------------------------------------
-- Slash commands
------------------------------------------------------------------------------------------
local function countEvents()
  local sessions, events, crumbs = 0, 0, 0
  for _, char in pairs(ns.db.chars) do
    for _, s in ipairs(char.sessions) do
      sessions = sessions + 1
      events = events + #s.events
      crumbs = crumbs + #s.crumbs
    end
  end
  return sessions, events, crumbs
end

SLASH_FOREVERSCOUT1 = "/fscout"
SLASH_FOREVERSCOUT2 = "/scout"
SlashCmdList.FOREVERSCOUT = function(input)
  local cmd, rest = (input or ""):match("^%s*(%S*)%s*(.-)%s*$")
  cmd = cmd:lower()
  if cmd == "pause" then
    ns.db.settings.paused = true
    ns.Print("Recording paused. /fscout resume to continue.")
    if ns.BIS and ns.BIS.UpdateDot then ns.BIS.UpdateDot() end
  elseif cmd == "resume" then
    ns.db.settings.paused = false
    ns.Print("Recording resumed.")
    if ns.BIS and ns.BIS.UpdateDot then ns.BIS.UpdateDot() end
  elseif cmd == "share" then
    local v = rest:lower()
    if v == "on" or v == "off" then
      ns.SetShare(v == "on")
    else
      ns.Print("Automatic sharing is " .. (ns.db.settings.share and "|cff55ff55on|r" or "|cffff5555off|r")
        .. ". Use /fscout share on or /fscout share off.")
    end
  elseif cmd == "note" or cmd == "mark" then
    ns:Log("note", { text = rest:sub(1, 200) })
    ns.Print("Note saved: " .. rest)
  elseif cmd == "report" then
    ns.ShowReport()
  elseif cmd == "export" then
    ns.ShowExport()
  elseif cmd == "gear" then
    ns.ShowGear()
  elseif cmd == "bis" or cmd == "plan" then
    ns.BIS.Toggle()
  elseif cmd == "pins" then
    ns.Pins.SetEnabled(not ns.Pins.Enabled())
    ns.Print("Map pins " .. (ns.Pins.Enabled() and "on" or "off") .. ".")
  elseif cmd == "minimap" then
    ns.db.settings.hideMinimap = not ns.db.settings.hideMinimap
    if ns.BIS.button then ns.BIS.button:SetShown(not ns.db.settings.hideMinimap) end
    ns.Print("Minimap button " .. (ns.db.settings.hideMinimap and "hidden" or "shown") .. ".")
  elseif cmd == "debug" then
    ns.debug = not ns.debug
    ns.Print("Debug " .. (ns.debug and "on" or "off"))
  elseif cmd == "wipe" then
    if rest == "confirm" then
      ForeverScoutDB = nil
      ns:InitDB()
      ns:StartSession()
      ns.Print("All recorded data erased.")
    else
      ns.Print("This erases everything recorded. Type |cffffff00/fscout wipe confirm|r to proceed.")
    end
  else
    local s, e, c = countEvents()
    local state = ns.db.settings.paused and "|cffff5555PAUSED|r" or "|cff55ff55recording|r"
    ns.Print(("%s — %d sessions, %d events, %d route points. Unknown to Questie: %d"):format(
      state, s, e, c, ns.missingCount or 0))
    if ns.db.settings.share then
      ns.Print("Automatic sharing is |cff55ff55on|r. The ForeverScout Uploader app sends your log after you log out or /reload.")
    else
      ns.Print("Automatic sharing is |cffff5555off|r. Turn it on with /fscout share on.")
    end
    ns.Print("Commands: /fscout bis | pins | pause | resume | share on|off | note <text> | gear | report | export | minimap | wipe")
  end
end

------------------------------------------------------------------------------------------
-- Boot
------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------
-- Sharing consent. The addon cannot use the network; this flag tells the ForeverScout
-- Uploader app (which reads the SavedVariables file) whether it may send the log.
------------------------------------------------------------------------------------------
function ns.SetShare(on)
  ns.db.settings.share = on and true or false
  ns.db.settings.shareAsked = true
  if on then
    ns.Print("Automatic sharing |cff55ff55on|r. Install the ForeverScout Uploader app once and your "
      .. "route is sent after each logout or /reload. Turn off any time with /fscout share off.")
  else
    ns.Print("Automatic sharing |cffff5555off|r. Recording continues locally only.")
  end
end

local function askToShare()
  if ns.db.settings.shareAsked or not StaticPopupDialogs or not StaticPopup_Show then return end
  StaticPopupDialogs.FOREVERSCOUT_SHARE = {
    text = "|cFF4FC3F7ForeverScout|r records your questing route (quests, XP, positions, timing) "
      .. "to build free leveling guides for everyone.\n\nShare it automatically? "
      .. "No names, realms or chat are ever included.",
    button1 = "Share automatically",
    button2 = "Keep it local",
    OnAccept = function() ns.SetShare(true) end,
    OnCancel = function() ns.SetShare(false) end,
    timeout = 0,
    whileDead = true,
    hideOnEscape = false,
    preferredIndex = 3,
  }
  StaticPopup_Show("FOREVERSCOUT_SHARE")
end

ns:On("PLAYER_LOGIN", function()
  ns:InitDB()
  ns:StartSession()
  ns:Log("login", { xp = UnitXP("player"), maxxp = UnitXPMax("player"), rested = GetXPExhaustion() })
  if ns.Recorder and ns.Recorder.Start then ns.Recorder.Start() end
  ns.Print("recording your route. Type /fscout for status.")
  C_Timer.After(5, askToShare)
end)

ns:On("PLAYER_LOGOUT", function()
  if ns.session then
    ns:Log("logout", { xp = UnitXP("player") })
    ns.session.duration = ns:Now()
  end
end)
