//go:build !windows && !darwin

package main

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Linux/other: used for development and testing. No autostart integration.

func ask(title, text string) bool {
	if os.Getenv("FSCOUT_ASSUME") != "" {
		return os.Getenv("FSCOUT_ASSUME") == "yes"
	}
	fmt.Printf("[%s]\n%s\n[y/N] ", title, text)
	line, _ := bufio.NewReader(os.Stdin).ReadString('\n')
	return strings.HasPrefix(strings.ToLower(strings.TrimSpace(line)), "y")
}

func say(title, text string) { fmt.Printf("[%s]\n%s\n", title, text) }

func dataDir() (string, error) {
	if d := os.Getenv("FSCOUT_DATA_DIR"); d != "" {
		return d, nil
	}
	base, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "ForeverScout"), nil
}

func wowRoots() []string { return nil }

func (a *App) isInstalled() bool { return false }

func (a *App) install() error {
	return errors.New("automatic startup is only supported on Windows and macOS; run with --background instead")
}

func (a *App) uninstall() { a.requestStop() }

func openURL(u string) error {
	fmt.Printf("Open this link in your browser:\n%s\n", u)
	return nil
}
