-- ForeverScout: Recorder
-- Turns game events into compact log entries. Event kinds (field "k"):
--   accept   q, by (giver "n123"/"o456"/"i789"), offerXP, qlvl
--   turnin   q, xp, money, by (ender), qlvl
--   abandon  q
--   xp       d (gained), src ("q" quest, "k" kill, "o" other), mob (npc id when known), mlvl
--   obj      text, n, of, mob          (objective progress such as "Mottled Boar slain: 3/10")
--   level    to
--   zone     name
--   hearth / bind name / fm (flight master opened) / taxi on|off
--   death / alive
--   newquest q, title, objective, by    (quest unknown to the installed QuestieDB)
--   newnpc   npc, name, mlvl, react      (targeted NPC unknown to the installed QuestieDB)
--   note     text
-- Every entry also carries t (seconds since session start), lvl, map, x, y.

local ADDON, ns = ...
local Recorder = {}
ns.Recorder = Recorder

local GetTime = GetTime
local HEARTHSTONE_SPELL = 8690
local XP_WINDOW = 1.5 -- seconds to match an XP gain to a turn-in or kill

local pendingDetail = {}   -- questID -> { by, offerXP, title, objective }
local pendingEnder = {}    -- questID -> by
local turnedIn = {}        -- questID -> GetTime()
local lastTurnIn, lastKill, lastKillMob, lastKillLvl = 0, 0, nil, nil
local lastXP, lastMaxXP, lastLevel
local reportedNpc = {}
ns.missing = {}
ns.missingCount = 0

------------------------------------------------------------------------------------------
-- Helpers
------------------------------------------------------------------------------------------
local function questGiverRef()
  local kind, id = ns.UnitNpcId("questnpc")
  if not kind then kind, id = ns.UnitNpcId("npc") end
  if kind == "npc" then return "n" .. id end
  if kind == "object" then return "o" .. id end
  return nil
end

local function stripName(text)
  if type(text) ~= "string" then return nil end
  local name = UnitName("player")
  if name and name ~= "" then text = text:gsub(name, "<name>") end
  return text:sub(1, 500)
end

local function questLogLevel(questID)
  if C_QuestLog and C_QuestLog.GetLogIndexForQuestID and C_QuestLog.GetInfo then
    local ok, index = pcall(C_QuestLog.GetLogIndexForQuestID, questID)
    if ok and index then
      local ok2, info = pcall(C_QuestLog.GetInfo, index)
      if ok2 and info and info.level then return info.level end
    end
  end
  if GetNumQuestLogEntries and GetQuestLogTitle then
    for i = 1, GetNumQuestLogEntries() do
      local _, level, _, _, _, _, _, id = GetQuestLogTitle(i)
      if id == questID then return level end
    end
  end
  return nil
end

local function addMissing(line)
  ns.missingCount = ns.missingCount + 1
  table.insert(ns.missing, line)
end

-- QUEST_ACCEPTED is (questID) on modern clients and (logIndex, questID) on older ones.
local function questIdFromArgs(a, b)
  if b and type(b) == "number" and b > 0 then return b end
  return a
end

------------------------------------------------------------------------------------------
-- Quest dialogs: remember who offered / who takes the quest
------------------------------------------------------------------------------------------
ns:On("QUEST_DETAIL", function()
  local questID = GetQuestID and GetQuestID()
  if not questID or questID <= 0 then return end
  pendingDetail[questID] = {
    by = questGiverRef(),
    offerXP = GetRewardXP and GetRewardXP() or nil,
    title = GetTitleText and GetTitleText() or nil,
    objective = stripName(GetObjectiveText and GetObjectiveText() or nil),
  }
end)

local function rememberEnder()
  local questID = GetQuestID and GetQuestID()
  if questID and questID > 0 then pendingEnder[questID] = questGiverRef() end
end
ns:On("QUEST_PROGRESS", rememberEnder)
ns:On("QUEST_COMPLETE", rememberEnder)

ns:On("QUEST_ACCEPTED", function(a, b)
  local questID = questIdFromArgs(a, b)
  if not questID then return end
  local d = pendingDetail[questID] or {}
  pendingDetail[questID] = nil
  local by = d.by
  if not by then
    -- Quests started from items show no quest giver; note the item if we can't tell.
    by = nil
  end
  local qlvl = questLogLevel(questID)
  ns:Log("accept", { q = questID, by = by, offerXP = d.offerXP, qlvl = qlvl })

  if ns.KnownToQuestie("Quest", questID) == false then
    ns:Log("newquest", { q = questID, title = d.title, objective = d.objective, by = by, qlvl = qlvl })
    addMissing(("Quest %d \"%s\" (level %s) from %s"):format(
      questID, tostring(d.title), tostring(qlvl), tostring(by or "unknown")))
  end
end)

ns:On("QUEST_TURNED_IN", function(questID, xpReward, moneyReward)
  local now = GetTime()
  turnedIn[questID] = now
  lastTurnIn = now
  ns:Log("turnin", { q = questID, xp = xpReward, money = moneyReward,
                     by = pendingEnder[questID], qlvl = questLogLevel(questID) })
  pendingEnder[questID] = nil
end)

ns:On("QUEST_REMOVED", function(questID)
  if not questID then return end
  -- Fires for turn-ins as well as abandons; wait a moment to see which it was.
  C_Timer.After(1.5, function()
    local t = turnedIn[questID]
    if t and GetTime() - t < 5 then return end
    ns:Log("abandon", { q = questID })
  end)
end)

------------------------------------------------------------------------------------------
-- Experience
------------------------------------------------------------------------------------------
ns:On("CHAT_MSG_COMBAT_XP_GAIN", function()
  lastKill = GetTime()
  local kind, id = ns.UnitNpcId("target")
  if kind == "npc" then
    lastKillMob = id
    lastKillLvl = UnitLevel("target")
  else
    lastKillMob, lastKillLvl = nil, nil
  end
end)

local function classify(at)
  if math.abs(lastTurnIn - at) <= XP_WINDOW then return "q" end
  if math.abs(lastKill - at) <= XP_WINDOW then return "k" end
  return "o"
end

ns:On("PLAYER_XP_UPDATE", function(unit)
  if unit and unit ~= "player" then return end
  local xp, maxXP, level = UnitXP("player"), UnitXPMax("player"), UnitLevel("player")
  if lastXP == nil then lastXP, lastMaxXP, lastLevel = xp, maxXP, level return end
  local delta
  if level > lastLevel then
    delta = (lastMaxXP - lastXP) + xp
  else
    delta = xp - lastXP
  end
  lastXP, lastMaxXP, lastLevel = xp, maxXP, level
  if delta <= 0 then return end
  local at = GetTime()
  -- Chat/turn-in events may arrive just after the XP update; classify a moment later.
  C_Timer.After(0.6, function()
    local src = classify(at)
    local entry = { d = delta, src = src }
    if src == "k" then entry.mob, entry.mlvl = lastKillMob, lastKillLvl end
    ns:Log("xp", entry)
  end)
end)

ns:On("PLAYER_LEVEL_UP", function(level)
  ns:Log("level", { to = level, played = nil })
end)

------------------------------------------------------------------------------------------
-- Objective progress ("Mottled Boar slain: 3/10", "Cactus Apple: 4/10")
------------------------------------------------------------------------------------------
-- Which active quest (and which of its objectives) a progress message belongs to.
-- Matches the objective text against the quest log; returns nil when unsure.
local function objectiveOwner(text)
  if C_QuestLog and C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo and C_QuestLog.GetQuestObjectives then
    local okN, n = pcall(C_QuestLog.GetNumQuestLogEntries)
    for i = 1, (okN and n or 0) do
      local ok, info = pcall(C_QuestLog.GetInfo, i)
      if ok and info and not info.isHeader and info.questID then
        local ok2, objs = pcall(C_QuestLog.GetQuestObjectives, info.questID)
        for oi, o in ipairs(ok2 and objs or {}) do
          if type(o.text) == "string" and o.text:find(text, 1, true) == 1 then return info.questID, oi end
        end
      end
    end
  elseif GetNumQuestLogEntries and GetQuestLogTitle and GetNumQuestLeaderBoards and GetQuestLogLeaderBoard then
    for i = 1, (GetNumQuestLogEntries() or 0) do
      local _, _, _, isHeader, _, _, _, id = GetQuestLogTitle(i)
      if not isHeader and id then
        for oi = 1, (GetNumQuestLeaderBoards(i) or 0) do
          local t = GetQuestLogLeaderBoard(oi, i)
          if type(t) == "string" and t:find(text, 1, true) == 1 then return id, oi end
        end
      end
    end
  end
end

ns:On("UI_INFO_MESSAGE", function(...)
  local msg
  for i = 1, select("#", ...) do
    local v = select(i, ...)
    if type(v) == "string" then msg = v break end
  end
  if not msg or ns.isSecret(msg) then return end
  local text, n, of = msg:match("^(.-):%s*(%d+)%s*/%s*(%d+)$")
  if not text then return end
  local kind, id = ns.UnitNpcId("target")
  local q, oi = objectiveOwner(text)
  ns:Log("obj", { text = text:sub(1, 120), n = tonumber(n), of = tonumber(of),
                  mob = kind == "npc" and id or nil, q = q, oi = oi })
end)

------------------------------------------------------------------------------------------
-- Travel, zones, deaths
------------------------------------------------------------------------------------------
ns:On("ZONE_CHANGED_NEW_AREA", function()
  ns:Log("zone", { name = GetZoneText and GetZoneText() or nil })
end)

ns:On("UNIT_SPELLCAST_SUCCEEDED", function(unit, _, spellID)
  if unit == "player" and spellID == HEARTHSTONE_SPELL then ns:Log("hearth") end
end)

ns:On("HEARTHSTONE_BOUND", function()
  ns:Log("bind", { name = GetBindLocation and GetBindLocation() or nil })
end)

ns:On("TAXIMAP_OPENED", function()
  local by = questGiverRef()
  if not by then
    local kind, id = ns.UnitNpcId("npc")
    if kind == "npc" then by = "n" .. id end
  end
  ns:Log("fm", { by = by })
end)

-- PLAYER_ALIVE also fires after loading screens (hearth, zeppelins), so only log a
-- resurrection when we actually saw a death first.
local dead = false
ns:On("PLAYER_DEAD", function() dead = true; ns:Log("death") end)
local function revived()
  if dead and not UnitIsDeadOrGhost("player") then
    dead = false
    ns:Log("alive")
  end
end
ns:On("PLAYER_UNGHOST", revived)
ns:On("PLAYER_ALIVE", revived)

------------------------------------------------------------------------------------------
-- NPCs unknown to Questie (any level, once per NPC per session)
------------------------------------------------------------------------------------------
ns:On("PLAYER_TARGET_CHANGED", function()
  local kind, id = ns.UnitNpcId("target")
  if kind ~= "npc" or reportedNpc[id] then return end
  reportedNpc[id] = true
  if ns.KnownToQuestie("Npc", id) ~= false then return end
  local react = UnitReaction and UnitReaction("target", "player") or nil
  local name = UnitName("target")
  if ns.isSecret(name) then name = nil end
  ns:Log("newnpc", { npc = id, name = name, mlvl = UnitLevel("target"), react = react })
  local map, x, y = ns.Position()
  addMissing(("NPC %d \"%s\" level %s at map %s (%s, %s)"):format(
    id, tostring(name), tostring(UnitLevel("target")), tostring(map), tostring(x), tostring(y)))
end)

------------------------------------------------------------------------------------------
-- Route breadcrumbs
------------------------------------------------------------------------------------------
local lastCrumb = { t = -999, map = nil, x = 0, y = 0, flags = "" }

local function flags()
  local f = ""
  if UnitOnTaxi("player") then f = f .. "T" end
  if UnitIsDeadOrGhost("player") then f = f .. "D" end
  if IsResting() then f = f .. "R" end
  if UnitAffectingCombat("player") then f = f .. "C" end
  if IsMounted and IsMounted() then f = f .. "M" end
  return f
end

local wasOnTaxi = false
local function tick()
  if not ns.session or ns.db.settings.paused then return end
  local map, x, y = ns.Position()
  local f = flags()
  local onTaxi = f:find("T") ~= nil
  if onTaxi ~= wasOnTaxi then
    wasOnTaxi = onTaxi
    ns:Log("taxi", { on = onTaxi })
  end
  local t = ns:Now()
  local moved = map ~= lastCrumb.map or not x
    or math.abs((x or 0) - lastCrumb.x) + math.abs((y or 0) - lastCrumb.y) > 0.15
  if moved or f ~= lastCrumb.flags or t - lastCrumb.t >= 60 then
    table.insert(ns.session.crumbs, table.concat({ t, map or 0, x or -1, y or -1, f }, ","))
    lastCrumb.t, lastCrumb.map, lastCrumb.x, lastCrumb.y, lastCrumb.flags = t, map, x or 0, y or 0, f
  end
end

function Recorder.Start()
  lastXP, lastMaxXP, lastLevel = UnitXP("player"), UnitXPMax("player"), UnitLevel("player")
  tick()
  C_Timer.NewTicker(ns.db.settings.crumbSeconds, tick)
end
