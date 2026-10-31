# ForeverScout Uploader

WoW addons can't use the internet, so this companion app sends your ForeverScout log for you.
It works the same way the Raider.IO and Warcraft Logs companion apps do.

## For players

1. Download `ForeverScoutUploader.exe` (Windows) or the Mac build for your chip from
   [Releases](https://github.com/Jweyant/forever-xp/releases).
2. Double-click it and choose **Yes** to start it automatically when you sign in.
3. That's it. Whenever the game saves (logout or `/reload`), the uploader checks for new data
   within 30 seconds and sends it, but **only** if you chose "Share automatically" in game.

To stop it, run the app again and choose **Yes** to remove it.

**Windows:** the app isn't code-signed yet, so SmartScreen may say "Windows protected your PC".
Click **More info**, then **Run anyway**.
**Mac:** right-click the file, choose **Open**, then **Open** again. You may also need to allow
it in System Settings > Privacy & Security.

## What it does and doesn't do

- It reads only `WTF\Account\*\SavedVariables\ForeverScout.lua` inside your WoW folders.
- It sends the file's contents. Your account folder name is replaced by a random ID.
- It never modifies game files, never reads other addons' data, and never touches the game process.
- Its own files (settings and a log of what it sent) are in `%LOCALAPPDATA%\ForeverScout` on
  Windows and `~/Library/Application Support/ForeverScout` on Mac.

## Command line

```
ForeverScoutUploader --status      what it found and when it last uploaded
ForeverScoutUploader --once        upload anything new, then exit
ForeverScoutUploader --uninstall   stop and remove from startup
```

If your WoW install isn't found automatically, set `FSCOUT_WOW_DIR` to the folder that
contains your game folders (e.g. `D:\Games\World of Warcraft`).

## Build

```bash
GOOS=windows GOARCH=amd64 go build -ldflags "-H=windowsgui -X main.uploadURL=https://..." -o ForeverScoutUploader.exe .
```

## Your name on the leaderboard

The uploader shows you your scout name (for example "Scout a1b2c3"), a one-way hash of this
install's random id. After setup it offers to open forever-xp.com so you can sign in with
Discord and have your Discord name shown instead. The link is also saved in `claim.txt` next to
the log. Keep it private: anyone with the link can claim your scout name.
