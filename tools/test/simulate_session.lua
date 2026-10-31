-- Minimal WoW client mock: loads ForeverScout, plays a short Valley of Trials session,
-- then writes the SavedVariables file exactly as the client would.
-- Usage: lua simulate_session.lua <addonDir> <out SavedVariables file>

local addonDir, outFile = arg[1], arg[2]

-- Clock and timers -------------------------------------------------------------------
local clock = 1000
local timers = {}
function GetTime() return clock end
local epoch = tonumber(os.getenv("SIM_EPOCH") or "") or 1791000000
math.randomseed(epoch)
function time() return epoch + math.floor(clock) end
C_Timer = {
  After = function(d, fn) table.insert(timers, { at = clock + d, fn = fn }) end,
  NewTicker = function(d, fn) table.insert(timers, { at = clock + d, fn = fn, every = d }) end,
}
local function advance(seconds)
  local target = clock + seconds
  while true do
    table.sort(timers, function(a, b) return a.at < b.at end)
    local nextT = timers[1]
    if not nextT or nextT.at > target then break end
    table.remove(timers, 1)
    clock = nextT.at
    nextT.fn()
    if nextT.every then nextT.at = clock + nextT.every table.insert(timers, nextT) end
  end
  clock = target
end

-- Player state -----------------------------------------------------------------------
local P = { level = 1, xp = 0, max = 400, map = 1411, x = 0.4330, y = 0.6850, taxi = false,
            target = nil, questnpc = nil, dead = false }
local XPMAX = { 400, 900, 1400, 2100, 2800 }

function UnitGUID(unit)
  if unit == "player" then return "Player-1234-0ABCDEF" .. (os.getenv("SIM_PLAYER") or "0") end
  local id = (unit == "target" and P.target) or ((unit == "questnpc" or unit == "npc") and P.questnpc)
  if not id then return nil end
  return ("Creature-0-4372-1-1-%d-0000123456"):format(id)
end
function UnitExists(unit) return UnitGUID(unit) ~= nil end
function UnitLevel(unit) if unit == "player" then return P.level end return P.targetLevel or 1 end
function UnitXP() return P.xp end
function UnitXPMax() return P.max end
function UnitName(unit) if unit == "player" then return "Testchar" end return P.targetName end
function UnitRace() return "Troll", "Troll" end
function UnitClass() return "Hunter", "HUNTER" end
function UnitFactionGroup() return "Horde" end
function UnitReaction() return 2 end
function UnitOnTaxi() return P.taxi end
function UnitIsDeadOrGhost() return P.dead end
function UnitAffectingCombat() return false end
function IsResting() return false end
function IsMounted() return false end
function GetXPExhaustion() return nil end
function GetBuildInfo() return "1.60.1", "69913" end
function GetZoneText() return "Durotar" end
function GetBindLocation() return "Razor Hill" end
function strsplit(sep, s)
  local out = {}
  for piece in (s .. sep):gmatch("(.-)" .. sep:gsub("%p", "%%%0")) do out[#out + 1] = piece end
  return unpack(out)
end
C_Map = {
  GetBestMapForUnit = function() return P.map end,
  GetPlayerMapPosition = function() return { GetXY = function() return P.x, P.y end } end,
}
local currentQuest
function GetQuestID() return currentQuest and currentQuest.id or 0 end
function GetRewardXP() return currentQuest and currentQuest.xp or 0 end
function GetTitleText() return currentQuest and currentQuest.title end
function GetObjectiveText() return currentQuest and currentQuest.obj end
-- One quest in the log while boars are being killed: "Mottled Boar slain" belongs to quest 789, objective 1.
C_QuestLog = { GetLogIndexForQuestID = function(id) return id end,
               GetInfo = function(i) return { level = (i == 99999 and 7) or 2, questID = (i == 1 and 789) or i, isHeader = false } end,
               GetNumQuestLogEntries = function() return 1 end,
               GetQuestObjectives = function(id)
                 if id == 789 then return { { text = "Mottled Boar slain: 0/10" } } end
                 return {}
               end }

-- UI stubs (Windows.lua is loaded but its frames are never shown here)
local frames = {}
function CreateFrame()
  local f = { events = {} }
  function f:RegisterEvent(e) self.events[e] = true end
  function f:SetScript(name, fn) self[name] = fn end
  table.insert(frames, f)
  return f
end
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) print("[chat] " .. m:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end }
SlashCmdList = {}
StaticPopupDialogs = {}
-- SIM_SHARE=0 simulates a player who declines sharing
StaticPopup_Show = function(name)
  if os.getenv("SIM_SHARE") == "0" then StaticPopupDialogs[name].OnCancel() else StaticPopupDialogs[name].OnAccept() end
end
UISpecialFrames = {}
function tinsert(t, v) table.insert(t, v) end

-- Fake QuestieDB: knows everything except quest 99999 and NPC 90001
LibQuestieDB = {
  Quest = { Get = function(id) return id ~= 99999 and "Known quest" or nil end },
  Npc = { Get = function(id) return id ~= 90001 and "Known npc" or nil end },
}

-- Load addon ------------------------------------------------------------------------
local ns = {}
for _, file in ipairs({ "Core.lua", "Recorder.lua", "Windows.lua" }) do
  local chunk = assert(loadfile(addonDir .. "/" .. file))
  chunk("ForeverScout", ns)
end

local function fire(event, ...)
  for _, f in ipairs(frames) do
    if f.events[event] and f.OnEvent then f.OnEvent(f, event, ...) end
  end
end

local function gainXP(amount)
  P.xp = P.xp + amount
  while P.xp >= P.max do
    P.xp = P.xp - P.max
    P.level = P.level + 1
    P.max = XPMAX[P.level] or 3000
    fire("PLAYER_LEVEL_UP", P.level)
  end
  fire("PLAYER_XP_UPDATE", "player")
end

local function walk(toX, toY, seconds)
  local steps = math.floor(seconds / 5)
  local fx, fy = P.x, P.y
  for i = 1, steps do
    P.x = fx + (toX - fx) * i / steps
    P.y = fy + (toY - fy) * i / steps
    advance(5)
  end
end

local function talkAndAccept(npc, quest)
  P.questnpc = npc
  currentQuest = quest
  fire("QUEST_DETAIL")
  advance(3)
  fire("QUEST_ACCEPTED", quest.id)
  P.questnpc = nil
end

local function turnIn(npc, quest)
  P.questnpc = npc
  currentQuest = quest
  fire("QUEST_COMPLETE")
  advance(2)
  fire("QUEST_TURNED_IN", quest.id, quest.xp, 50)
  gainXP(quest.xp)
  fire("QUEST_REMOVED", quest.id)
  P.questnpc = nil
  advance(2)
end

local function killBoar(n, of)
  P.target, P.targetLevel = 3098, 2
  advance(12)
  gainXP(40)
  fire("CHAT_MSG_COMBAT_XP_GAIN", "Mottled Boar dies, you gain 40 experience.")
  fire("UI_INFO_MESSAGE", 0, ("Mottled Boar slain: %d/%d"):format(n, of))
  P.target = nil
end

GetInstanceInfo = function() return "Ragefire Chasm", "party", 1, "Normal", 5, 0, false, 389 end

local function bossFight(ok, seconds)
  fire("ENCOUNTER_START", 1443, "Taragaman the Hungerer", 1, 5)
  advance(seconds)
  fire("ENCOUNTER_END", 1443, "Taragaman the Hungerer", 1, 5, ok and 1 or 0)
end

-- Session --------------------------------------------------------------------------
fire("PLAYER_LOGIN")
advance(5)
talkAndAccept(10176, { id = 4641, xp = 40, title = "Your Place In The World" })
walk(0.4206, 0.6833, 30)
turnIn(3143, { id = 4641, xp = 40 })
talkAndAccept(3143, { id = 788, xp = 170, title = "Cutting Teeth" })
walk(0.4400, 0.6300, 40)
for i = 1, 10 do killBoar(i, 10) walk(P.x + 0.002, P.y - 0.001, 10) end
walk(0.4206, 0.6833, 45)
turnIn(3143, { id = 788, xp = 170 })
-- an unknown Forever quest and NPC
P.target, P.targetName, P.targetLevel = 90001, "Skyborne Envoy", 5
fire("PLAYER_TARGET_CHANGED")
talkAndAccept(90001, { id = 99999, xp = 300, title = "A Forever Quest", obj = "Find Testchar's lost map." })
P.target = nil
-- abandon a quest
talkAndAccept(3143, { id = 789, xp = 250, title = "Sting of the Scorpid" })
fire("QUEST_REMOVED", 789)
advance(5)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-1", 8690)
advance(10)
SlashCmdList.FOREVERSCOUT("")
bossFight(false, 40)
bossFight(true, 95)
fire("PLAYER_LOGOUT")

-- Write SavedVariables ---------------------------------------------------------------
local function dump(v, indent, out)
  indent = indent or ""
  local tv = type(v)
  if tv == "table" then
    out[#out + 1] = "{\n"
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b)
      if type(a) == type(b) then return a < b end
      return type(a) == "number"
    end)
    for _, k in ipairs(keys) do
      out[#out + 1] = indent .. "\t[" .. (type(k) == "string" and string.format("%q", k) or tostring(k)) .. "] = "
      dump(v[k], indent .. "\t", out)
      out[#out + 1] = ",\n"
    end
    out[#out + 1] = indent .. "}"
  elseif tv == "string" then
    out[#out + 1] = string.format("%q", v)
  else
    out[#out + 1] = tostring(v)
  end
end
local out = { "\nForeverScoutDB = " }
dump(ForeverScoutDB, "", out)
out[#out + 1] = "\n"
local f = assert(io.open(outFile, "w"))
f:write(table.concat(out))
f:close()
print("wrote " .. outFile)
