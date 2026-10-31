// ForeverScout Uploader
//
// WoW addons cannot use the network. This small companion app watches the ForeverScout
// SavedVariables file and uploads it after the game saves it (logout or /reload), but only
// when the player turned on sharing inside the addon (/fscout share on).
//
// Double-click it once: it offers to start itself at login and then runs quietly in the
// background. Run it again to stop and uninstall.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Set at build time: go build -ldflags "-X main.uploadURL=https://... -X main.version=0.2.0"
var (
	uploadURL = ""
	version   = "dev"
)

const appName = "ForeverScout Uploader"

func main() {
	background := flag.Bool("background", false, "run the watcher loop (used by autostart)")
	once := flag.Bool("once", false, "upload anything new once and exit")
	uninstall := flag.Bool("uninstall", false, "stop the background uploader and remove autostart")
	status := flag.Bool("status", false, "print what would be uploaded and exit")
	flag.Parse()

	if u := os.Getenv("FSCOUT_UPLOAD_URL"); u != "" {
		uploadURL = u
	}

	app, err := newApp()
	if err != nil {
		fatal(err)
	}
	defer app.close()

	switch {
	case *uninstall:
		app.uninstall()
		say(appName, "The uploader is stopped and will no longer start at login.")
	case *status:
		app.printStatus()
	case *once:
		app.scanAndUpload(time.Now())
	case *background:
		app.runLoop()
	default:
		app.interactive()
	}
}

func fatal(err error) {
	say(appName, "Something went wrong:\n\n"+err.Error())
	os.Exit(1)
}

// interactive is the double-click flow.
func (a *App) interactive() {
	if a.isInstalled() {
		a.writeClaimFile()
		if ask(appName, "The ForeverScout Uploader is already set up and runs in the background.\n\n"+
			"Your name on the Scout leaderboard (forever-xp.com/leaderboard/) is "+scoutName(a.state.InstallID)+".\n"+
			"To show your Discord name there instead, open the link in "+filepath.Join(a.dir, "claim.txt")+".\n\n"+
			"Do you want to STOP it and remove it from startup?") {
			a.uninstall()
			say(appName, "Stopped and removed. Your recorded data stays on your computer.")
		}
		return
	}

	files := a.discover()
	var found string
	if len(files) == 0 {
		found = "No ForeverScout data was found yet. That's fine: install the ForeverScout addon " +
			"and log in once. The uploader will find it automatically."
	} else {
		found = fmt.Sprintf("Found ForeverScout data in %d WoW account folder(s).", len(files))
	}
	msg := found + "\n\nStart the uploader automatically when you sign in to your computer?\n\n" +
		"It checks for new ForeverScout data every 30 seconds and sends it only if you chose " +
		"\"Share automatically\" in game. No names, realms or chat are included."
	if !ask(appName, msg) {
		a.scanAndUpload(time.Now())
		say(appName, "OK, nothing was installed. Any data you chose to share has been sent once. "+
			"Run this app again any time to send new data or turn on automatic uploads.")
		return
	}
	if err := a.install(); err != nil {
		fatal(err)
	}
	say(appName, "All set. The uploader is running in the background and will start with your computer.\n\n"+
		"Log file: "+filepath.Join(a.dir, "uploader.log")+"\n\nRun this app again to stop it.")
	a.offerClaim()
}
