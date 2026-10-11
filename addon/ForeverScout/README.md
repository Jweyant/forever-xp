# ForeverScout

A lightweight logger for World of Warcraft: Forever. It records how you level — quests,
XP, where things are, and how long everything takes — so the community can build free,
fast leveling guides and fill in quest data that Questie doesn't have yet.

## Install

1. Copy the `ForeverScout` folder into your Forever client's `Interface\AddOns\` folder
   (inside your World of Warcraft install, in the Forever game folder).
2. Log in. You'll see "ForeverScout: recording your route."
3. Play normally. Questie is optional, but with it installed ForeverScout also tells you
   when a quest or NPC is missing from Questie's database.

## Commands

| Command | What it does |
|---|---|
| `/fscout` | Status: sessions, events, route points, items missing from Questie |
| `/fscout pause` / `resume` | Stop or restart recording |
| `/fscout note <text>` | Drop a note at your current spot ("cave is packed", "skip this, elite") |
| `/fscout report` | Copyable list of quests/NPCs Questie is missing — share it on Questie's Discord |
| `/fscout export` | Copyable export string of your recorded sessions |
| `/fscout wipe confirm` | Erase everything recorded |

## Sharing your data

Your log is written when you log out or `/reload`:

```
<Forever game folder>\WTF\Account\<ACCOUNT>\SavedVariables\ForeverScout.lua
```

Zip that file and attach it to a "Submit a log" issue at
https://github.com/Jweyant/forever-leveling/issues/new/choose (or paste `/fscout export`
there). The file is the better option for long sessions.

## What is recorded

- Quests accepted, turned in and abandoned, with the quest-giver/turn-in NPC ID and your position
- XP gained and whether it came from a quest, a kill (with mob ID and level) or something else
- Objective progress messages ("Mottled Boar slain: 3/10") with position and mob ID
- Your position about every 10 seconds while moving, plus taxi, death, hearthstone and zone changes
- Your class, race, faction and level, and the game build

## What is never recorded

- Your character name, realm, account name or GUID. Each character gets a random ID.
- Chat, whispers, other players, gold, inventory or anything outside questing.
- Your name is replaced with `<name>` in any quest text that contains it.

Note: the SavedVariables folder path contains your account folder name, but that path is
not part of the file's contents.

## Limits

- ForeverScout only reads game events. It never automates anything.
- Inside most instances the game hides map position, so dungeon routes have fewer points.
