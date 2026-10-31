//go:build windows

package main

import (
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const (
	runKey      = `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
	runValue    = "ForeverScoutUploader"
	exeName     = "ForeverScoutUploader.exe"
	createNoWin = 0x08000000
	detached    = 0x00000008
	mbYesNo     = 0x00000004
	mbIconInfo  = 0x00000040
	mbIconQuest = 0x00000020
	mbSetFg     = 0x00010000
	idYes       = 6
)

var (
	user32         = syscall.NewLazyDLL("user32.dll")
	procMessageBox = user32.NewProc("MessageBoxW")
)

func messageBox(title, text string, flags uintptr) int {
	t, _ := syscall.UTF16PtrFromString(title)
	m, _ := syscall.UTF16PtrFromString(text)
	ret, _, _ := procMessageBox.Call(0, uintptr(unsafe.Pointer(m)), uintptr(unsafe.Pointer(t)), flags|mbSetFg)
	return int(ret)
}

func ask(title, text string) bool { return messageBox(title, text, mbYesNo|mbIconQuest) == idYes }
func say(title, text string)      { messageBox(title, text, mbIconInfo) }

func dataDir() (string, error) {
	if d := os.Getenv("FSCOUT_DATA_DIR"); d != "" {
		return d, nil
	}
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		var err error
		if base, err = os.UserConfigDir(); err != nil {
			return "", err
		}
	}
	return filepath.Join(base, "ForeverScout"), nil
}

func hidden(name string, args ...string) *exec.Cmd {
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWin}
	return cmd
}

func wowRoots() []string {
	var roots []string
	for _, key := range []string{
		`HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft`,
		`HKLM\SOFTWARE\Blizzard Entertainment\World of Warcraft`,
	} {
		out, err := hidden("reg", "query", key, "/v", "InstallPath").Output()
		if err != nil {
			continue
		}
		for _, line := range strings.Split(string(out), "\n") {
			if i := strings.Index(line, "REG_SZ"); i >= 0 {
				p := strings.TrimSpace(line[i+len("REG_SZ"):])
				p = strings.TrimRight(p, `\`)
				// InstallPath usually points at a game folder such as ...\_retail_
				if base := filepath.Base(p); strings.HasPrefix(base, "_") && strings.HasSuffix(base, "_") {
					p = filepath.Dir(p)
				}
				roots = append(roots, p)
			}
		}
	}
	for d := 'C'; d <= 'Z'; d++ {
		drive := string(d) + `:\`
		if _, err := os.Stat(drive); err != nil {
			continue
		}
		for _, sub := range []string{`Program Files (x86)\World of Warcraft`, `Program Files\World of Warcraft`,
			`World of Warcraft`, `Games\World of Warcraft`, `Blizzard\World of Warcraft`} {
			roots = append(roots, filepath.Join(drive, sub))
		}
	}
	return roots
}

func (a *App) installedExe() string { return filepath.Join(a.dir, exeName) }

func (a *App) isInstalled() bool {
	return hidden("reg", "query", runKey, "/v", runValue).Run() == nil
}

func (a *App) install() error {
	self, err := os.Executable()
	if err != nil {
		return err
	}
	target := a.installedExe()
	if !strings.EqualFold(filepath.Clean(self), filepath.Clean(target)) {
		a.requestStop()
		if err := copyFile(self, target); err != nil {
			return err
		}
	}
	cmdline := `"` + target + `" --background`
	if err := hidden("reg", "add", runKey, "/v", runValue, "/t", "REG_SZ", "/d", cmdline, "/f").Run(); err != nil {
		return err
	}
	cmd := exec.Command(target, "--background")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: detached | createNoWin}
	return cmd.Start()
}

func (a *App) uninstall() {
	a.requestStop()
	_ = hidden("reg", "delete", runKey, "/v", runValue, "/f").Run()
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	tmp := dst + ".new"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	_ = os.Remove(dst)
	return os.Rename(tmp, dst)
}

// openURL opens the player's default browser. The URL is built from constants and the install id.
func openURL(u string) error {
	return hidden("rundll32", "url.dll,FileProtocolHandler", u).Start()
}
