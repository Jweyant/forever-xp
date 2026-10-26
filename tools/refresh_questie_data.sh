#!/usr/bin/env bash
# Rebuild data/ from Questie's QuestieDB (Forever data is on the default branch). Linux x64 or set LUA to a Lua 5.1.
# The raw export stays in data/ (gitignored). tools/build_quests.py turns it into gamedata/quests.json,
# which is committed (Questie is GPLv3, like this repo).
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
work=${QUESTIEDB_DIR:-"$root/.cache/QuestieDB"}
if [[ -d "$work/.git" ]]; then
  git -C "$work" pull --ff-only
else
  git clone --depth 1 https://github.com/Questie/QuestieDB.git "$work"
fi
cd "$work"
./generate.sh Forever
lua=${LUA:-"$work/tools/lua-binary/linux-x64/lua"}
"$lua" "$root/tools/export_questiedb.lua" Forever "$root/data/questiedb"
python3 "$root/tools/build_sqlite.py" "$root/data/questiedb" "$root/data/forever_questdb.sqlite"
echo "Questie commit: $(git -C "$work" rev-parse HEAD)"
