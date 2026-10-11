//go:build darwin

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const agentLabel = "com.foreverscout.uploader"

func osa(script string) (string, error) {
	out, err := exec.Command("osascript", "-e", script).Output()
	return strings.TrimSpace(string(out)), err
}

func quote(s string) string {
	return `"` + strings.ReplaceAll(strings.ReplaceAll(s, `\`, `\\`), `"`, `\"`) + `"`
}

func ask(title, text string) bool {
	out, err := osa(fmt.Sprintf(`button returned of (display dialog %s with title %s buttons {"No", "Yes"} default button "Yes")`,
		quote(text), quote(title)))
	return err == nil && out == "Yes"
}

func say(title, text string) {
	_, _ = osa(fmt.Sprintf(`display dialog %s with title %s buttons {"OK"} default button "OK"`, quote(text), quote(title)))
}

func dataDir() (string, error) {
	if d := os.Getenv("FSCOUT_DATA_DIR"); d != "" {
		return d, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "Library", "Application Support", "ForeverScout"), nil
}

func wowRoots() []string {
	home, _ := os.UserHomeDir()
	return []string{"/Applications/World of Warcraft", filepath.Join(home, "Applications", "World of Warcraft")}
}

func (a *App) agentPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "LaunchAgents", agentLabel+".plist")
}

func (a *App) isInstalled() bool {
	_, err := os.Stat(a.agentPath())
	return err == nil
}

func (a *App) install() error {
	self, err := os.Executable()
	if err != nil {
		return err
	}
	target := filepath.Join(a.dir, "ForeverScoutUploader")
	if filepath.Clean(self) != filepath.Clean(target) {
		data, err := os.ReadFile(self)
		if err != nil {
			return err
		}
		if err := os.WriteFile(target, data, 0o755); err != nil {
			return err
		}
	}
	plist := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>%s</string>
  <key>ProgramArguments</key><array><string>%s</string><string>--background</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict></plist>
`, agentLabel, target)
	if err := os.MkdirAll(filepath.Dir(a.agentPath()), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(a.agentPath(), []byte(plist), 0o644); err != nil {
		return err
	}
	return exec.Command("launchctl", "load", a.agentPath()).Run()
}

func (a *App) uninstall() {
	a.requestStop()
	_ = exec.Command("launchctl", "unload", a.agentPath()).Run()
	_ = os.Remove(a.agentPath())
}
