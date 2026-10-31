module github.com/Jweyant/forever-xp/tools/simrunner

go 1.25.0

// The wowsims/forever combat engine (MIT), pinned to one commit. The timestamp-and-sha
// pseudo-version below and WOWSIMS_COMMIT in .github/workflows/sim-weights.yml name the same
// commit; tools/test/test_simconfigs.py checks they agree.
require github.com/wowsims/forever v0.0.0-20261031023002-376a6aa2886b
