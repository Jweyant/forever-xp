-- export_questiedb.lua
-- Loads a generated QuestieDB flavor (Static Corrections already folded in) through the
-- library's own runtime reader and dumps every entity, plus support tables, to JSON.
--
-- Run from the QuestieDB checkout root with its bundled Lua 5.1:
--   tools/lua-binary/linux-x64/lua /path/to/export_questiedb.lua Forever /path/to/outdir

local flavorName = arg[1] or "Forever"
local outDir = arg[2] or "export"

local config = dofile("src/config.lua")
local emulator = dofile("emulator/metadata.lua")
local client = dofile("emulator/client.lua")
local flavorLoader = dofile("generator/flavor.lua")

------------------------------------------------------------------------------------------
-- Minimal JSON encoder
------------------------------------------------------------------------------------------
local escapes = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b', ['\f'] = '\\f',
                  ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }

local function encodeString(s)
  return '"' .. s:gsub('[%c"\\]', function(c)
    return escapes[c] or string.format("\\u%04x", c:byte())
  end) .. '"'
end

local function isArray(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k % 1 ~= 0 then return false end
    n = n + 1
  end
  for i = 1, n do if t[i] == nil then return false end end
  return true
end

local encode
function encode(v, out)
  local tv = type(v)
  if tv == "nil" then out[#out + 1] = "null"
  elseif tv == "boolean" then out[#out + 1] = tostring(v)
  elseif tv == "number" then
    if v ~= v or v == math.huge or v == -math.huge then out[#out + 1] = "null"
    elseif v % 1 == 0 and math.abs(v) < 2^53 then out[#out + 1] = string.format("%d", v)
    else out[#out + 1] = string.format("%.14g", v) end
  elseif tv == "string" then out[#out + 1] = encodeString(v)
  elseif tv == "table" then
    if isArray(v) then
      out[#out + 1] = "["
      for i = 1, #v do
        if i > 1 then out[#out + 1] = "," end
        encode(v[i], out)
      end
      out[#out + 1] = "]"
    else
      local keys = {}
      for k in pairs(v) do keys[#keys + 1] = k end
      table.sort(keys, function(a, b)
        if type(a) == type(b) then return a < b end
        return type(a) == "number"
      end)
      out[#out + 1] = "{"
      for i, k in ipairs(keys) do
        if i > 1 then out[#out + 1] = "," end
        out[#out + 1] = encodeString(tostring(k))
        out[#out + 1] = ":"
        encode(v[k], out)
      end
      out[#out + 1] = "}"
    end
  else
    out[#out + 1] = "null"
  end
end

local function writeJson(path, value)
  local out = {}
  encode(value, out)
  local f = assert(io.open(path, "wb"))
  f:write(table.concat(out))
  f:close()
end

------------------------------------------------------------------------------------------
-- Load the generated addon through the emulator, exactly as verify.lua does
------------------------------------------------------------------------------------------
local flavor
for _, f in ipairs(config.flavors or {}) do
  if f.name == flavorName then flavor = f end
end
if not flavor and flavorLoader.byName then flavor = flavorLoader.byName(flavorName) end
assert(flavor, "unknown flavor " .. flavorName)

local tocPath = "./" .. config.tocPath(flavor)
local map = emulator.parse(tocPath)
client.reset()
client.install({ expansion = flavor.expansion })
emulator.install(config.addonName, map)
local Lib = emulator.loadAddon(tocPath, config.addonName)

os.execute('mkdir -p "' .. outDir .. '"')

------------------------------------------------------------------------------------------
-- Entities: every field by name
------------------------------------------------------------------------------------------
local counts = {}
for _, typeName in ipairs({ "Quest", "Npc", "Object", "Item" }) do
  local entity = Lib[typeName]
  local meta = Lib.Meta[typeName]
  local result = {}
  local n = 0
  for _, id in ipairs(entity.GetAllIds()) do
    local row = { id = id }
    for index = 1, meta.fieldCount do
      local name = meta.names[index]
      local value = entity.Get(id, index)
      -- Numeric getters return 0 for "absent"; keep 0 only where it is meaningful data.
      if value ~= nil and not (type(value) == "table" and next(value) == nil) then
        row[name] = value
      end
    end
    result[#result + 1] = row
    n = n + 1
  end
  writeJson(outDir .. "/" .. typeName:lower() .. "s.json", result)
  counts[typeName] = n
  io.write(("%-7s %6d exported\n"):format(typeName, n))
end

------------------------------------------------------------------------------------------
-- Support tables useful for routing
------------------------------------------------------------------------------------------
local support = {}
local ok, questXP = pcall(Lib.Support.Get, "QuestXP")
if ok and questXP then support.questXP = questXP.db end

local okZ, zoneDB = pcall(Lib.Support.Get, "ZoneDB")
if okZ and zoneDB then
  support.zoneIDs = zoneDB.zoneIDs
  local p = zoneDB.private or {}
  for _, key in ipairs({ "areaIdToUiMapId", "uiMapIdToAreaId", "subZoneToParentZone", "dungeons" }) do
    local value = p[key]
    if type(value) == "string" then
      local fn = loadstring(value)
      if fn then local good, t = pcall(fn); if good then value = t end end
    end
    if type(value) == "table" then support[key] = value end
  end
end

for name, value in pairs(support) do
  writeJson(outDir .. "/" .. name .. ".json", value)
  io.write(("support %-20s written\n"):format(name))
end

writeJson(outDir .. "/manifest.json", {
  flavor = flavorName,
  counts = counts,
  schema = {
    Quest = Lib.Meta.Quest.names, Npc = Lib.Meta.Npc.names,
    Object = Lib.Meta.Object.names, Item = Lib.Meta.Item.names,
  },
})
print("done -> " .. outDir)
