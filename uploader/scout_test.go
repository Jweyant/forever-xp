package main

import "testing"

// Same vector as tools/test/test_scouts.py: the uploader and the leaderboard must agree.
func TestScoutName(t *testing.T) {
	if got := scoutName("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"); got != "Scout 97800d" {
		t.Fatalf("scoutName = %q, want %q", got, "Scout 97800d")
	}
}
