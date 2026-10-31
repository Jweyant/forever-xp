// Simrunner computes the BIS planner's stat weights with our own simulation runs.
//
// The combat engine is wowsims/forever (MIT), pinned in go.mod; every number in the output comes
// from simulations this tool runs on the setups in gamedata/simconfigs/ — nothing published by
// wowsims ships. Each setup is a SIML file (the engine's text format for a full character setup:
// gear from our BIS planner, talents, consumables, buffs, encounter, and which stats to weigh).
// Build and run with the engine's item database compiled in:
//
//	go run -tags=with_db . -checkout <wowsims checkout at the pinned commit> \
//	    -configs ../../gamedata/simconfigs -out ../../gamedata/simweights.json
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/wowsims/forever/sim"
	"github.com/wowsims/forever/sim/core"
	"github.com/wowsims/forever/sim/core/proto"
	"github.com/wowsims/forever/sim/siml"
	"google.golang.org/protobuf/encoding/protojson"
)

// Engine stat names -> the planner's stat keys (site/src/scripts/gear/model.ts SIM_KEYS).
// A stat not listed here is dropped and named in the report.
var statKey = map[string]string{
	"StatStrength": "str", "StatAgility": "agi", "StatStamina": "sta", "StatIntellect": "int",
	"StatSpirit": "spi", "StatAttackPower": "ap", "StatRangedAttackPower": "rap",
	"StatHitRating": "hit", "StatCritRating": "crit", "StatHasteRating": "haste",
	"StatExpertiseRating": "expertise", "StatSpellDamage": "sp", "StatHealingPower": "heal",
	"StatMP5": "mp5", "StatSpellPiercing": "spen",
	"StatArcaneDamage": "sp_arcane", "StatFireDamage": "sp_fire", "StatFrostDamage": "sp_frost",
	"StatHolyDamage": "sp_holy", "StatNatureDamage": "sp_nature", "StatShadowDamage": "sp_shadow",
	"StatDefenseRating": "def", "StatDodgeRating": "dodge", "StatParryRating": "parry",
	"StatBlockRating": "block", "StatBlockValue": "blockv", "StatArmor": "armor",
}
var pseudoKey = map[string]string{
	"PseudoStatMainHandDps": "dps", "PseudoStatOffHandDps": "dps_oh", "PseudoStatRangedDps": "dps_ranged",
}

// One entry of gamedata/simconfigs/index.json.
type entry struct {
	Key     string `json:"key"`     // the planner's "CLASS.spec"
	Label   string `json:"label"`   // shown on the site ("Planner BIS · Arms")
	Note    string `json:"note"`    // shown on the site under the weights
	File    string `json:"file"`    // the setup, relative to the configs dir
	SpecDir string `json:"specDir"` // ui/specs/<specDir> in the checkout, where the setup is read (so its `use` lines resolve)
	AplJSON string `json:"aplJson"` // optional APLRotation protojson in the checkout, replacing the setup's rotation
	Hps     bool   `json:"hps"`     // weigh healing instead of damage
}

type preset struct {
	Label string             `json:"label"`
	W     map[string]float64 `json:"w"`
	Note  string             `json:"note"`
}

func main() {
	checkout := flag.String("checkout", "", "wowsims/forever checkout at the commit pinned in go.mod")
	configs := flag.String("configs", "", "directory with index.json and the setup .siml files")
	out := flag.String("out", "", "where simweights.json goes")
	iterations := flag.Int("iterations", 5000, "sim iterations per stat-weight run")
	only := flag.String("only", "", "run just this key (for trying one spec)")
	flag.Parse()
	if *checkout == "" || *configs == "" || *out == "" {
		log.Fatal("need -checkout, -configs and -out")
	}
	sim.RegisterAll()

	var index []entry
	data, err := os.ReadFile(filepath.Join(*configs, "index.json"))
	if err != nil {
		log.Fatal(err)
	}
	if err := json.Unmarshal(data, &index); err != nil {
		log.Fatalf("index.json: %v", err)
	}

	specs := map[string][]preset{}
	var skipped []string
	for _, e := range index {
		if *only != "" && e.Key != *only {
			continue
		}
		w, dropped, err := runOne(*checkout, *configs, e, int32(*iterations))
		if err != nil {
			log.Fatalf("%s (%s): %v", e.Key, e.File, err)
		}
		skipped = append(skipped, dropped...)
		specs[e.Key] = append(specs[e.Key], preset{Label: e.Label, W: w, Note: e.Note})
		fmt.Printf("%s: %s -> %d stats\n", e.Key, e.Label, len(w))
	}

	sort.Strings(skipped)
	result := map[string]any{
		"source": map[string]string{
			"name":    "forever-xp sim runs",
			"engine":  "wowsims/forever (MIT)",
			"url":     "https://github.com/wowsims/forever",
			"site":    "https://wowsims.com/forever",
			"commit":  engineCommit(),
			"license": "MIT",
		},
		"specs":  specs,
		"report": map[string]any{"specs": len(specs), "skipped_stats": skipped},
	}
	buf, err := json.MarshalIndent(result, "", " ")
	if err != nil {
		log.Fatal(err)
	}
	if err := os.WriteFile(*out, append(buf, '\n'), 0o644); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("%d specs -> %s\n", len(specs), *out)
}

// engineCommit reads the pinned pseudo-version's commit prefix out of our go.mod at build time.
func engineCommit() string {
	data, err := os.ReadFile("go.mod")
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		if i := strings.Index(line, "github.com/wowsims/forever v"); i >= 0 {
			parts := strings.Split(strings.TrimSpace(line[i:]), "-")
			return parts[len(parts)-1]
		}
	}
	return ""
}

func runOne(checkout, configs string, e entry, iterations int32) (map[string]float64, []string, error) {
	// The setup is read from inside the checkout's spec folder, so its `use "apls/x.apl.siml"`
	// lines resolve against the engine's files at the pinned commit.
	src, err := os.ReadFile(filepath.Join(configs, e.File))
	if err != nil {
		return nil, nil, err
	}
	staged := filepath.Join(checkout, "ui", "specs", filepath.FromSlash(e.SpecDir), "__forever_xp.siml")
	if err := os.WriteFile(staged, src, 0o644); err != nil {
		return nil, nil, err
	}
	defer os.Remove(staged)
	f, err := siml.ReadFile(staged)
	if f == nil || f.Settings == nil {
		return nil, nil, fmt.Errorf("could not read the setup: %v", err)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "%s: %v\n", e.File, err)
	}
	s := f.Settings
	if s.Player == nil || s.Encounter == nil {
		return nil, nil, fmt.Errorf("the setup needs player settings and an encounter")
	}
	if e.AplJSON != "" {
		data, err := os.ReadFile(filepath.Join(checkout, filepath.FromSlash(e.AplJSON)))
		if err != nil {
			return nil, nil, err
		}
		rotation := &proto.APLRotation{}
		if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal(data, rotation); err != nil {
			return nil, nil, fmt.Errorf("%s: %w", e.AplJSON, err)
		}
		s.Player.Rotation = rotation
	}
	if s.Player.Rotation == nil || s.Player.Rotation.Type != proto.APLRotation_TypeAPL {
		return nil, nil, fmt.Errorf("the setup needs an APL rotation (a `use` of an .apl.siml, or aplJson)")
	}

	// Which stats to weigh: the ones the setup's sim section marks in ep_weights_stats.
	var stats []proto.Stat
	var pseudo []proto.PseudoStat
	if ep := s.EpWeightsStats; ep != nil {
		for i, v := range ep.Stats {
			if v != 0 {
				stats = append(stats, proto.Stat(i))
			}
		}
		for i, v := range ep.PseudoStats {
			if v != 0 {
				pseudo = append(pseudo, proto.PseudoStat(i))
			}
		}
	}
	if len(stats) == 0 {
		return nil, nil, fmt.Errorf("the setup's sim section marks no stats in ep_weights_stats")
	}

	request := &proto.StatWeightsRequest{
		Player:             s.Player,
		RaidBuffs:          s.RaidBuffs,
		PartyBuffs:         s.PartyBuffs,
		Debuffs:            s.Debuffs,
		Encounter:          s.Encounter,
		Tanks:              s.Tanks,
		SimOptions:         &proto.SimOptions{Iterations: iterations, RandomSeed: 20261104},
		StatsToWeigh:       stats,
		PseudoStatsToWeigh: pseudo,
		EpReferenceStat:    s.DpsRefStat,
		HpsReferenceStat:   s.HealRefStat,
	}
	result := core.StatWeights(request)
	if result.Error != nil {
		return nil, nil, fmt.Errorf("sim error: %s", result.Error.Message)
	}
	values := result.Dps
	if e.Hps {
		values = result.Hps
	}
	if values == nil || values.EpValues == nil {
		return nil, nil, fmt.Errorf("the sim returned no EP values")
	}

	w := map[string]float64{}
	var dropped []string
	keep := func(name, key string, v float64) {
		if v != v || v < -5 || v > 100 { // NaN or out of bounds
			dropped = append(dropped, fmt.Sprintf("%s (out of bounds: %g)", name, v))
			return
		}
		if v >= 0.005 || v <= -0.005 {
			w[key] = float64(int(v*10000+0.5)) / 10000
		}
	}
	for _, st := range stats {
		name := st.String()
		key, ok := statKey[name]
		if !ok || int(st) >= len(values.EpValues.Stats) {
			dropped = append(dropped, name)
			continue
		}
		keep(name, key, values.EpValues.Stats[st])
	}
	for _, ps := range pseudo {
		name := ps.String()
		key, ok := pseudoKey[name]
		if !ok || int(ps) >= len(values.EpValues.PseudoStats) {
			dropped = append(dropped, name)
			continue
		}
		keep(name, key, values.EpValues.PseudoStats[ps])
	}
	// The planner scores every weapon through one "dps" weight (hunters count ranged weapons in
	// full and melee at a fraction), so a ranged-weapon weight stands in for it.
	if v, ok := w["dps_ranged"]; ok && w["dps"] == 0 {
		w["dps"] = v
		delete(w, "dps_ranged")
	}
	if len(w) == 0 {
		return nil, nil, fmt.Errorf("every weighed stat was dropped: %s", strings.Join(dropped, ", "))
	}
	return w, dropped, nil
}
