package main

import (
	"bytes"
	"compress/gzip"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	pollInterval   = 30 * time.Second
	settleTime     = 10 * time.Second // wait until the game has finished writing
	maxUploadBytes = 20 << 20
	heartbeatStale = 3 * pollInterval
)

var shareOn = regexp.MustCompile(`\["share"\]\s*=\s*true`)

// scoutSalt must match SCOUT_SALT in tools/ingest_logs.py: the leaderboard on forever-xp.com/leaderboard/
// shows this same name, made from a one-way hash so the install id itself is never shown.
const scoutSalt = "forever-xp scout|"

// scoutName is the player's public name on the Scout leaderboard, e.g. "Scout 97800d".
func scoutName(installID string) string {
	h := sha256.Sum256([]byte(scoutSalt + installID))
	return "Scout " + hex.EncodeToString(h[:])[:6]
}

// claimSite is where a player links this install to their forever-xp.com account so the
// leaderboard shows their Discord name instead of "Scout a1b2c3". The install id is the claim
// code: a 128-bit random value only this computer has (see docs: scout identity flow).
const claimSite = "https://forever-xp.com/account/"

func (a *App) claimURL() string {
	return claimSite + "?claim=" + a.state.InstallID
}

// writeClaimFile keeps the claim link next to the log, for players who want to copy it by hand.
func (a *App) writeClaimFile() {
	text := "ForeverScout Uploader\n\n" +
		"Your name on the Scout leaderboard is " + scoutName(a.state.InstallID) + ".\n" +
		"To show your Discord name instead, open this link, sign in with Discord and confirm:\n\n" +
		a.claimURL() + "\n\n" +
		"Keep this link to yourself: anyone with it can claim your scout name.\n"
	_ = os.WriteFile(filepath.Join(a.dir, "claim.txt"), []byte(text), 0o600)
}

// offerClaim asks once per install whether to open the claim page now.
func (a *App) offerClaim() {
	a.writeClaimFile()
	if a.state.ClaimOffered {
		return
	}
	a.state.ClaimOffered = true
	a.saveState()
	if ask(appName, "Your name on the Scout leaderboard (forever-xp.com/leaderboard/) is "+scoutName(a.state.InstallID)+".\n\n"+
		"Want it to show your Discord name instead? This opens forever-xp.com in your browser, "+
		"where you sign in with Discord and confirm.\n\nYou can do it later: the link is in "+
		filepath.Join(a.dir, "claim.txt")+".") {
		if err := openURL(a.claimURL()); err != nil {
			say(appName, "Couldn't open your browser. Open this link yourself:\n\n"+a.claimURL())
		}
	}
}

type fileState struct {
	Hash       string    `json:"hash"`
	ModTime    time.Time `json:"modTime"`
	UploadedAt time.Time `json:"uploadedAt"`
	RetryAfter time.Time `json:"retryAfter,omitempty"`
}

type persisted struct {
	InstallID    string                `json:"installId"`
	ClaimOffered bool                  `json:"claimOffered,omitempty"`
	WowDirs      []string              `json:"wowDirs,omitempty"` // optional manual roots
	Files        map[string]*fileState `json:"files"`
}

type App struct {
	dir    string
	state  persisted
	logger *log.Logger
	logF   *os.File
	client *http.Client
}

func newApp() (*App, error) {
	dir, err := dataDir()
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	a := &App{dir: dir, client: &http.Client{Timeout: 60 * time.Second}}
	a.logF, _ = os.OpenFile(filepath.Join(dir, "uploader.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	var w io.Writer = io.Discard
	if a.logF != nil {
		w = a.logF
	}
	a.logger = log.New(w, "", log.LstdFlags)
	a.loadState()
	return a, nil
}

func (a *App) close() {
	if a.logF != nil {
		a.logF.Close()
	}
}

func (a *App) statePath() string { return filepath.Join(a.dir, "state.json") }

func (a *App) loadState() {
	if b, err := os.ReadFile(a.statePath()); err == nil {
		_ = json.Unmarshal(b, &a.state)
	}
	if a.state.Files == nil {
		a.state.Files = map[string]*fileState{}
	}
	if len(a.state.InstallID) != 32 {
		buf := make([]byte, 16)
		_, _ = rand.Read(buf)
		a.state.InstallID = hex.EncodeToString(buf)
		a.saveState()
	}
}

func (a *App) saveState() {
	b, _ := json.MarshalIndent(a.state, "", "  ")
	tmp := a.statePath() + ".tmp"
	if os.WriteFile(tmp, b, 0o644) == nil {
		_ = os.Rename(tmp, a.statePath())
	}
}

// slot identifies one account folder without revealing its name.
func (a *App) slot(path string) string {
	h := sha256.Sum256([]byte(a.state.InstallID + "|" + strings.ToLower(filepath.Clean(path))))
	return hex.EncodeToString(h[:8])
}

// ---------------------------------------------------------------------------------------
// Discovery
// ---------------------------------------------------------------------------------------

// discover returns every ForeverScout.lua under any WoW game folder (_classic_, _forever_ ...).
func (a *App) discover() []string {
	roots := append([]string{}, a.state.WowDirs...)
	if env := os.Getenv("FSCOUT_WOW_DIR"); env != "" {
		roots = append(roots, filepath.SplitList(env)...)
	}
	roots = append(roots, wowRoots()...)
	seen := map[string]bool{}
	var out []string
	for _, root := range roots {
		for _, pattern := range []string{
			filepath.Join(root, "_*_", "WTF", "Account", "*", "SavedVariables", "ForeverScout.lua"),
			filepath.Join(root, "WTF", "Account", "*", "SavedVariables", "ForeverScout.lua"),
		} {
			matches, _ := filepath.Glob(pattern)
			for _, m := range matches {
				key := strings.ToLower(filepath.Clean(m))
				if !seen[key] {
					seen[key] = true
					out = append(out, m)
				}
			}
		}
	}
	sort.Strings(out)
	return out
}

// ---------------------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------------------

type result int

const (
	skipped result = iota
	uploaded
	failed
)

func (a *App) scanAndUpload(now time.Time) (up, fail int) {
	for _, path := range a.discover() {
		switch a.process(path, now) {
		case uploaded:
			up++
		case failed:
			fail++
		}
	}
	a.saveState()
	return
}

func (a *App) process(path string, now time.Time) result {
	info, err := os.Stat(path)
	if err != nil {
		return skipped
	}
	st := a.state.Files[path]
	if st == nil {
		st = &fileState{}
		a.state.Files[path] = st
	}
	if info.ModTime().Equal(st.ModTime) && st.RetryAfter.IsZero() {
		return skipped // unchanged since last look
	}
	if now.Sub(info.ModTime()) < settleTime || now.Before(st.RetryAfter) {
		return skipped // still being written, or backing off
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return skipped
	}
	st.ModTime = info.ModTime()
	if !shareOn.Match(data) {
		st.RetryAfter = time.Time{}
		return skipped // player has not opted in
	}
	sum := sha256.Sum256(data)
	hash := hex.EncodeToString(sum[:])
	if hash == st.Hash {
		st.RetryAfter = time.Time{}
		return skipped
	}
	if len(data) > maxUploadBytes {
		a.logger.Printf("skip %s: %d bytes is over the limit", a.slot(path), len(data))
		return skipped
	}
	if uploadURL == "" {
		a.logger.Printf("no upload URL configured; would upload %s (%d bytes)", a.slot(path), len(data))
		return skipped
	}
	if err := a.send(path, data); err != nil {
		var retry *retryError
		backoff := 5 * time.Minute
		if errors.As(err, &retry) && retry.after > 0 {
			backoff = retry.after
		}
		st.RetryAfter = now.Add(backoff)
		a.logger.Printf("upload %s failed: %v (retry in %s)", a.slot(path), err, backoff)
		return failed
	}
	st.Hash, st.UploadedAt, st.RetryAfter = hash, now, time.Time{}
	a.logger.Printf("uploaded %s (%d bytes)", a.slot(path), len(data))
	return uploaded
}

type retryError struct {
	status int
	after  time.Duration
}

func (e *retryError) Error() string { return fmt.Sprintf("server returned %d", e.status) }

func (a *App) send(path string, data []byte) error {
	var buf bytes.Buffer
	zw := gzip.NewWriter(&buf)
	_, _ = zw.Write(data)
	_ = zw.Close()
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(uploadURL, "/")+"/v1/upload", &buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/gzip")
	req.Header.Set("X-FScout-Install", a.state.InstallID)
	req.Header.Set("X-FScout-Slot", a.slot(path))
	req.Header.Set("X-FScout-Version", version)
	resp, err := a.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
	switch {
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		return nil
	case resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500:
		after := 5 * time.Minute
		if s := resp.Header.Get("Retry-After"); s != "" {
			if d, err := time.ParseDuration(s + "s"); err == nil {
				after = d
			}
		}
		return &retryError{status: resp.StatusCode, after: after}
	default:
		// Rejected (bad file, too large...). Wait for the file to change before trying again.
		return &retryError{status: resp.StatusCode, after: 24 * time.Hour}
	}
}

// ---------------------------------------------------------------------------------------
// Background loop, single instance via heartbeat file, stop via stop file
// ---------------------------------------------------------------------------------------

func (a *App) heartbeatPath() string { return filepath.Join(a.dir, "running") }
func (a *App) stopPath() string      { return filepath.Join(a.dir, "stop") }

func (a *App) otherInstanceRunning() bool {
	info, err := os.Stat(a.heartbeatPath())
	return err == nil && time.Since(info.ModTime()) < heartbeatStale
}

func (a *App) runLoop() {
	if a.otherInstanceRunning() {
		return
	}
	_ = os.Remove(a.stopPath())
	a.logger.Printf("background uploader %s started", version)
	for {
		_ = os.WriteFile(a.heartbeatPath(), []byte(fmt.Sprint(os.Getpid())), 0o644)
		a.scanAndUpload(time.Now())
		for i := 0; i < int(pollInterval/time.Second); i++ {
			if _, err := os.Stat(a.stopPath()); err == nil {
				_ = os.Remove(a.stopPath())
				_ = os.Remove(a.heartbeatPath())
				a.logger.Printf("background uploader stopped")
				return
			}
			time.Sleep(time.Second)
		}
	}
}

// requestStop asks a running background instance to exit and waits briefly.
func (a *App) requestStop() {
	if !a.otherInstanceRunning() {
		return
	}
	_ = os.WriteFile(a.stopPath(), nil, 0o644)
	for i := 0; i < 5; i++ {
		time.Sleep(time.Second)
		if _, err := os.Stat(a.heartbeatPath()); err != nil {
			return
		}
	}
}

func (a *App) printStatus() {
	fmt.Printf("%s %s\ndata folder: %s\nupload URL: %q\ninstalled: %v, running: %v\nleaderboard name: %s\n",
		appName, version, a.dir, uploadURL, a.isInstalled(), a.otherInstanceRunning(), scoutName(a.state.InstallID))
	for _, p := range a.discover() {
		data, _ := os.ReadFile(p)
		st := a.state.Files[p]
		last := "never"
		if st != nil && !st.UploadedAt.IsZero() {
			last = st.UploadedAt.Format(time.RFC3339)
		}
		fmt.Printf("- %s\n  sharing: %v, size: %d bytes, last upload: %s\n", p, shareOn.Match(data), len(data), last)
	}
}
