# Cities as historical actors (`--cities`)

Branch `feat/cities`, from `integrate/wave-7` at `bcf14d8` (healthy-world
migration and the persecution fix), merged with `origin/main` at `a95e4d7`
(PR #27, Wave 8 defaults: great-person agendas, maritime and nomads on for
new worlds) without rebase. Code: `src/chronicler/cities.py` (behaviour),
`src/chronicler/cities_state.py` (persisted state), one migration driver in
`chronicler-agents/src/migration_drivers.rs`, and `scripts/cities_report.py`
/ `scripts/cities_identity.py`.

**Status.** **On by default for new worlds** since the city-markets full
gate (`feat/city-markets`, [city-markets.md](city-markets.md): 200 x 500
with the switch on, PASS strict, NO REGRESSION against main `3355289` and
Wave 8); `--no-cities` opts out and saved worlds keep their setting. That
branch also made cities markets in the goods economy (city farmers'
labour, craft demand, sieges cutting supply, imports in commerce) and added
the viewer Cities tab. The rest of this page describes the first slice
(`feat/cities`, then default off): with the switch off every output was
byte-identical to `a95e4d7`, agents off and hybrid (see
[Identity](#feature-off-identity)); with it on, both 20-seed subset gates
passed with no comparator regression (see [Gates](#switch-on-subset-gates)).

## Result

Merged tree (Wave 8 defaults), switch off (= `a95e4d7`) against on:

| | off | `--cities` |
| --- | ---: | ---: |
| subset 42-61: gate / comparator | PASS | PASS / NO REGRESSION |
| subset 62-81: gate / comparator | PASS | PASS / NO REGRESSION |
| migration per agent-turn, 42-61 / 62-81 | 0.0599 / 0.0549 | 0.0622 / 0.0558 |
| rebellion per agent-turn, 42-61 / 62-81 | 0.0350 / 0.0130 | 0.0341 / 0.0138 |
| epidemic deaths, 42-61 / 62-81 | 2,890 / 2,760 | 3,156 / 3,237 |
| cities founded / fallen per world (200 turns, 40 worlds) | - | 4.5 / 0.85 |
| urban pull, share of migration units (with household followers) | - | 1.9% (4.3%) |

## What exists

- **M56a** (`settlements.py`) detects dense agent clusters every 15 turns
  from the Phase 10 agent rows, matches them across passes, promotes a
  candidate after two passes, and dissolves a settlement after its inertia
  and grace run out. Identity is `settlement_id` (monotonic, never reused);
  the name is `"<region> Settlement <n>"`. Agents-off worlds have no
  settlements.
- **M56b** sends active and dissolving footprints to Rust each tick; every
  agent carries `settlement_id` (0 = rural) and urban agents get small
  needs, satisfaction, culture-drift and conversion modifiers. Snapshots
  carry urban fractions; narration gets the top settlements.
- Sieges already treat a settled region as fortified. The languages layer
  names each settlement, and narration maps canonical names in event text
  to the in-world names.

A settlement had no wealth, no politics, no draw on the countryside and no
history of its own: it formed and dissolved, and nothing in between acted
or was recorded.

## The slice

One actor built on the M56a settlement: a city with **wealth**, a
**population drawn from its hinterland**, a **political voice** and the
capacity to **rise and fall**. Disease and war act on it through the
existing systems. Guild factions, scholars and archives tied to places, and
merchant routing toward city markets are later slices
([Roadmap](#roadmap)).

Cities need agents: with `--agents off` nothing detects settlements, so a
fresh world founds no city and runs identically with the switch on (shown
[below](#feature-off-identity)). A world that already carries settlements
(resumed, forked or built by a test) keeps its cities with `--agents off`;
their size stays at M56a's last estimate and the default occupation mix is
assumed. The save/load resume test uses this mode.

### Size, rank, decline and fall

- **Residents** are M56a's `population_estimate` (refreshed each detection
  pass). The **size** follows it, closing 5% of the gap a turn, so a city
  does not rise and fall with every census. The agents now in the
  footprint (`settlement_id`) give the occupation mix and mean
  satisfaction, when at least three are there.
- An ACTIVE settlement with town-size residents becomes a **city**, keyed by
  its `settlement_id`, with its region index and founder civ index. Ranks:
  town, city, great city at 12, 25 and 40 residents, scaled by the world's
  mean region carrying capacity over 60 (template worlds: 9, 19, 31). A rank
  is gained when the size reaches the next threshold and lost after 10
  turns below 0.7 of its own.
- A city **falls** when M56a dissolves its settlement (*abandoned*), or
  after 10 turns under 5 residents (*deserted*). The fall cites the city's
  sack in the last 40 turns, or the region's latest epidemic or open famine.
  Fallen cities are kept; a city founded later in the same region names
  its predecessor. A settlement founds at most one city.

### Wealth

- **Commerce** per turn: size at the reference scale (size over the world
  scale above, so commerce does not grow with the agent count) x the
  mix-weighted treasury of a resident (farmer 0.025, soldier 0.05, merchant
  0.3, scholar 0.12, priest 0.1) x market access (1 + 0.15 per goods trade
  route of the region, from the economy result, at most four) x food (the
  region's food sufficiency, capped at 1) x 0.25 while an enemy occupies the
  region. A great city of merchants yields about 5 a turn, a town of
  farmers under 1.
- **Dues** by charter: 30% without one, 20% with market rights, 10%
  self-governing. They are owed to the lord (the region's controller) and
  paid at the start of the next turn's Phase 2, after the goods-economy
  tax, as `keep` treasury with the fraction carried; `--finance` therefore
  counts them as revenue. A free city keeps 30% for its own treasury the
  same way. Dues owed to a lord that has died are dropped.
- The rest fills a **civic purse** that decays 2% a turn and pays for
  charters and walls; sacks and fines take from it.
- With `--finance`, a lord's domestic credit (the merchant lenders) is
  multiplied by 1 + 0.1 per charter level of its cities, at most 1.5,
  beside the techniques and agenda factors.

### Population drawn from the hinterland (Rust)

A fourth healthy-world driver, **urban pull**, with its own gate. Python
gives each region a `city_pull`: its largest city's rank weight (0.4 / 0.7
/ 1.0) x (1 - unrest) x food, zero while occupied. The region batch carries
it as an optional `city_pull` column only when the switch is on; Rust sets
`RegionState.city_pull` from every batch and reads 0 when the column is
absent.

- Gate: a rural adult (`settlement_id` 0) who is not a soldier; a
  neighbouring region of the same realm whose `city_pull` exceeds home's by
  at least 0.25; that region fed (food sufficiency at least 1) and below
  capacity (farmers: below 0.80, the frontier gate's threshold, so the pull
  does not refill a region frontier settlement is leaving).
- Pull: 0.5 x ramp(gap, 0.25, 0.75), opening at `PULL_AT_GATE` (0.75 of the
  pull) like the other drivers. It counts net of roots and only toward a
  region the mover would not leave again at once (the reach rule).
- No existing weight changes. The hysteresis, the 5-turn lock, the
  persecution terms and the other three drivers are untouched; no new
  random draw. The budget tally gains the `urban` term (appended after
  `chain`) and `open_urban` / `gate_urban`.

### Political voice

- **Patricians.** Each turn a lord's merchant faction gains 0.002 per unit
  of `rank x (1 + charter / 2)` over its cities, at most 0.015, and the
  influence is renormalized.
- **Charters.** A town with the fee in its purse petitions for market
  rights (15); a city for self-government (40); at most every 15 turns.
  The lord grants with chance 0.45, +0.25 for cautious, calculating, shrewd
  or opportunistic rulers and -0.25 for aggressive, zealous, stubborn or
  bold ones, +0.15 with a treasury under 30, +0.15 under 30 stability, +0.6
  x (merchant influence - 0.25), within [0.05, 0.95]. A grant pays the fee
  to the lord (`keep`), lowers dues and raises the merchant faction by 0.03;
  a refusal leaves a grievance of 0.25.
- **Unrest** moves 20% a turn toward a target: 2 x (0.5 - residents' mean
  satisfaction) when positive, 0.5 x the food shortfall below 0.8 of
  sufficiency, dues (0.10 without a charter, 0.05 with market rights), 0.3
  while occupied, and the grievance (decaying 4% a turn).
- **Urban revolt.** From unrest 0.6 a revolt breaks out with a chance
  rising to 0.2 a turn at unrest 1 (cooldown 12): the lord loses 5
  stability (`guard-shock`). Outcome, from the lord's stability after it:
  - **free city** under 30, when the city is of rank 2 or more with a
    charter, the lord keeps at least one other region and the city is not
    its capital or occupied: the region secedes as a city-state, a new
    civilization built as `check_secession` builds one (one region, its
    capital; hostile to its old lord and neutral to the rest; the lord's
    military and economy split by population share, `guard`; the lord's
    stability -10, `guard-shock`; in hybrid mode the region's agents
    transferred through `apply_secession_transitions`), with half the purse
    as treasury, a shrewd, calculating or cautious ruler and `freedom`
    among its values;
  - **concession** under 30 otherwise, or with chance 0.3: one charter
    level and the grievance cleared;
  - **suppression**: a fine of a quarter of the purse to the lord (`keep`),
    unrest -0.4, grievance +0.1.

  A free city does not revolt against itself. If it is conquered or
  absorbed it returns to self-government (one level less on conquest).

### War and disease

- **Sack.** An enemy that occupies the city's region, or takes it while at
  war with its lord (or within a turn of its occupation or conquest),
  carries off half the purse (`keep` to the sacker) and leaves a grievance
  of 0.3; at most once in 20 turns. A conqueror also revokes one charter
  level. The event cites the occupation or conquest. Other lord changes
  are recorded as `city_lord_changed`.
- **Walls.** A city of rank 2 or more, or any city whose lord is at war,
  with 30 in its purse and no fortifications in its region starts them
  through the infrastructure pipeline (`pending_build`, the usual three
  turns), paid from the purse. The campaign layer's fortification rules
  then apply.
- **Disease.** With `--epidemiology`, a region's susceptibility is
  multiplied by 1 + 0.5 x its urban share (city residents over the region's
  population), so contact imports and the within-region recursion both run
  hotter in cities. Plague, pox and pestilence in a city's region (and
  famine onsets) enter its history, at most one of a kind per 30 turns.

### Names

City events name the settlement canonically (`Sunfire Steppe Settlement
1`). With `--languages` (on by default) the narrator's IN-WORLD NAMES block
gives the name each people uses, and `scripts/cities_report.py` prints it:
`Sunfire Steppe Settlement 1 (Sokre in Vrashni, 'sun town')`.

### Contracts

- Randomness: `random.Random(stable_hash_int("cities", <namespace>, seed,
  turn, settlement_id))` for petitions (`petition`), revolts (`revolt`)
  and a free city's ruler (`free_city`, `regnal`). The Rust driver adds no
  draw.
- Identity: region index, civ index, `settlement_id`. A free city is a new
  civ index appended to `world.civilizations`, as secession does.
- `city_pull` is recomputed from persisted city state for every region
  batch, and Rust resets it to 0 for a batch without the column; nothing
  transient is left on the world. A free city sets the region's existing
  `_seceded_this_turn` flag, consumed and cleared by the next region batch
  as for every secession.
- Accumulator categories: dues, fees, fines and plunder `keep`; revolt and
  free-city stability `guard-shock`; the free city's military and economy
  split `guard`. Merchant influence is written to the faction state.
- Append-only orders: `RANK_NAMES`, `CHARTER_NAMES`, `HISTORY_KINDS`,
  `COUNTER_KEYS` (Python); `TERM_URBAN` and `VOLUNTARY_DRIVER_NAMES` (Rust).

## Turn placement

| When | What |
| --- | --- |
| Phase 1 (`--epidemiology`) | urban susceptibility factor |
| Phase 2, after the goods-economy tax | dues assessed last turn paid to lords (`keep`) |
| Phase 3b (`--finance`) | city credit factor in domestic credit |
| Agent tick | `city_pull` in the region batch; the urban driver |
| Phase 10, after diplomacy and agendas | `tick_cities`: foundings; then per city falls, lord changes and sacks, mix and satisfaction, size and rank, commerce and dues, unrest, walls, charters, revolts, history, pull; then the patricians' voice |

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--cities` / `--no-cities` (`BooleanOptionalAction`) |
| World field | `WorldState.cities: CityState \| None` (presence = on), omitted while `None` |
| Default | on (`cities.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, since `feat/city-markets`; off before) for `execute_run`, batch and the live server; resumed, forked and supplied worlds keep their setting; `scripts/benchmark_headless.run` pins it off |
| Gate runner | `scripts/m53b_run_validation.py --cities` forwards the switch and records it in `run_manifest.json` |
| Bundle | `history[n].cities`: living cities (id, name, region, lord, rank, residents, purse, charter, unrest, satisfaction), the fallen count and counters; omitted while off. The viewer Cities tab reads it with `world_state.cities` (city-markets.md) |
| Analytics | `generate_report` gains `cities` for runs that carry it |
| State | living and fallen cities (each with its history as `(turn, kind, event id)`), dues owed and carried per civ index, counters |

## A city's history

`scripts/cities_report.py RUN_DIR` prints each city's record with the event
text the simulation wrote. Template world, seed 70, 300 turns, hybrid,
`--cities`, everything else at its default (`--simulate-only`,
`PYTHONHASHSEED=0`, merged head):

```
Verdant Plains Settlement 1 (Skārīpu in Dorrathi, 'green town'), Verdant Plains;
founded turn 15 under Dorrathi Clans; peak great city (44 people), purse peak 105;
charter free city; standing: town of 6, lord Free City of Verdant Plains
  15: founded: Verdant Plains Settlement 1 in Verdant Plains has grown into a great city of 41 people
  18: charter: Dorrathi Clans grants Verdant Plains Settlement 1 market rights for 15
  33: refused: Dorrathi Clans refuses Verdant Plains Settlement 1 self-government
  48: refused: Dorrathi Clans refuses Verdant Plains Settlement 1 self-government
  53: famine: Famine strikes Verdant Plains, devastating Dorrathi Clans.
  59: revolt: The people of Verdant Plains Settlement 1 in Verdant Plains rise against Dorrathi Clans
  59: free_city: Verdant Plains Settlement 1 throws off Dorrathi Clans's rule: the Free City of Verdant Plains
  87: declined: Verdant Plains Settlement 1 in Verdant Plains has shrunk to a city of 18 people
 126: famine: Famine strikes Verdant Plains, devastating Free City of Verdant Plains.
 174: declined: Verdant Plains Settlement 1 in Verdant Plains has shrunk to a town of 12 people
 205: famine: Famine strikes Verdant Plains, devastating Free City of Verdant Plains.
 278: famine: Famine strikes Verdant Plains, devastating Free City of Verdant Plains.
```

The recorded causes tie it to the rest of the run: the revolt cites the
second refusal and the famine (`59:urban_revolt:0` -> `48:charter_refused:0`,
`58:famine:1`), the free city cites the revolt. The Free City of Verdant
Plains then acts as a state: at turn 185 it goes to war with the Vrashni
Dominion for Amber Valley (citing an embargo), makes peace, goes back to war
at 211, besieges and occupies Amber Valley (213), occupies Obsidian Shore
and sacks its town (`219:city_sacked:0` -> `219:occupation:0`, 17 in
plunder), and in the Ivory Concord (220) takes Amber Valley and Mistwood.
At turn 300 it holds three regions while its own city has shrunk, through
recurring famine, from a great city of 41 to a town of 6. A second
settlement in Verdant Plains, founded under the free city at 210, rises
against the patrician government at 226 (conceded: market rights), buys
self-government at 268 and rises again at 299.

Rise and fall in 120 turns (seed 53, same settings): `Amber Valley
Settlement 3` (Suvagha, 'gold town', in the Vrashni dialect of Amber Valley)
is founded at turn 150, refused market rights at once and sold them at 168;
its revolt at 180 is put down with a fine, its second at 247 wins
self-government, and the town is abandoned at 270 (the fall cites
`266:epidemic:2`, marsh fever, which cites the famine of 261).

Over the 40 gate worlds (200 turns), per world: 4.5 cities founded, 0.85
fallen, 4.0 charters granted and 2.7 refused, 0.58 revolts (0.3
concessions, 0.2 suppressions, 0.075 free cities), 0.2 walls, 0.075 sacks.

## Feature-off identity

Base: `a95e4d7` (`origin/main`, which contains `integrate/wave-7`) exported
with `git archive` (its `src/` and `scripts/`) and its extension (no Rust
change since `bcf14d8`; built from the base tree before any change, SHA-256
`3d47d60f...91a51`), on `PYTHONPATH`; branch: the merged head and its
extension (`96cad2b5...4abe62`). Same interpreter, `PYTHONHASHSEED=0`.
`scripts/cities_identity.py` (as `scripts/diplomacy_identity.py`).

1. **Direct runs**: template seeds 42 / 7 / 1234 with `--agents off` 300
   turns and hybrid 200 turns; procedural 48 regions x 10 civs, seed 7, off
   200 and hybrid 120 turns. Every file (`state.json` and its historiography
   and languages sidecars, `chronicle.md`, `memories_*.json`,
   `agent_events.arrow`, the bundle without `metadata.generated_at`): **88
   files, 0 differences** with the default switch and **88 files, 0
   differences** with `--no-cities`. Before the merge the same matrix
   against `bcf14d8` gave the same: 88 / 0 and 88 / 0.
2. **Switch on, agents off.** The four `--agents off` runs with `--cities`:
   **42 files, 0 differences** once the layer's own fields are removed
   (`compare-inert`: `cities` in the state and in every bundle snapshot);
   without removing them only those 8 files differ. Without settlements the
   layer is inert.
3. **Subset gate**, seeds 42-61 x 200 hybrid: the base gate (run from the
   exported tree) against this branch's switch-off gate: all 2,200 run files
   identical; the validation report, gate decision, gate summary and summary
   identical once the batch path is normalized (4 files, 0 differences).
   Same result before the merge against `bcf14d8`.
4. **In the suite.** The frozen exact-trajectory oracles
   (`test_performance_equivalence`, `test_governance_dormancy`) pass with no
   fixture change; `test_feature_off_never_runs_city_code` forbids every
   city entry point (the tick, dues, pull, epidemic and credit factors,
   snapshot) through 25 off-mode turns with the ledger, epidemiology and
   finance on and a settlement in place, and checks that the region batch
   carries no `city_pull`. In Rust, the urban term is added last, so with
   `city_pull` 0 the pull sum keeps its bits
   (`without_city_pull_the_urban_driver_adds_nothing_and_the_sum_keeps_its_bits`).

## Switch-on subset gates

`scripts/m53b_run_validation.py --profile subset --parallel 1 --cities`
(20 seeds x 200 turns, hybrid), compared by `validation_compare`
(`--baseline-report`) with the switch-off gate of the same seeds (42-61:
this branch, shown identical to the base above; 62-81: the exported base).
Merged head, Wave 8 defaults.

| | 42-61 off | 42-61 on | 62-81 base | 62-81 on |
| --- | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | **PASS / NO REGRESSION** | PASS / - | **PASS / NO REGRESSION** |
| regression oracle (informational at subset) | PASS strict | PASS strict | FAIL: rebellion floor, civ survival | FAIL: rebellion floor, civ survival |
| migration per agent-turn | 0.0599 | 0.0622 | 0.0549 | 0.0558 |
| rebellion per agent-turn (floor 0.02) | 0.0350 | 0.0341 | 0.0130 | 0.0138 |
| satisfaction mean / latest | 0.595 / 0.615 | 0.599 / 0.619 | 0.611 / 0.620 | 0.608 / 0.616 |
| needs (seeds with the expected sign; 12 required) | 13 | 16 | 14 | 16 |
| cohort / community | PASS / PASS | PASS / PASS | PASS / PASS | PASS / PASS |
| arcs (informational) | PASS | PASS | FAIL | PASS |
| artifacts | PASS | PASS | PARTIAL | PARTIAL |
| epidemic deaths / outbreaks | 2,890 / 1,452 | 3,156 / 1,641 | 2,760 / 1,392 | 3,237 / 1,617 |
| extinct worlds / polities alive at the end (mean) | 0 / 2.85 | 0 / 2.95 | 0 / 3.10 | 0 / 3.15 |
| cities founded / fallen | - | 92 / 18 | - | 89 / 16 |
| charters granted / refused | - | 79 / 55 | - | 82 / 52 |
| revolts: concession / suppression / free city | - | 9 / 5 / 1 | - | 3 / 3 / 2 |
| walls / sacks | - | 2 / 0 | - | 6 / 3 |

- **Migration** rises in both sets (+0.0023, +0.0009): the urban pull adds
  moves without displacing the other drivers; the strict 0.05 floor holds.
- **Epidemics**: deaths +9.2% and +17.3%, outbreaks +13.0% and +16.2%, from
  the urban susceptibility factor (and divergence).
- **Rebellion**: -0.0009 and +0.0008. Before the merge (Wave 7 defaults,
  `a8b4b6d` against `bcf14d8`) the same comparison gave +0.0052 and
  +0.0018 (0.0343 -> 0.0395, 0.0189 -> 0.0207); the sign does not hold
  across the two baselines, so the change is within run-to-run divergence.
  Satisfaction moves by at most 0.004.
- **Arcs** pass in both switched-on sets. Before the merge both
  switched-on sets had cinderella arcs at 40.2% of civ arcs against the
  oracle's 40% dominance ceiling (bases 37-38%); the base 62-81 fails it
  here. The arcs oracle is informational in the subset profile.
- **Extinction**: no world went extinct in any of the 80 gate runs (160
  with the pre-merge runs); free cities add polities.
- Before the merge, both gates also passed with NO REGRESSION (migration
  0.0600 -> 0.0635 and 0.0571 -> 0.0580, needs 13 -> 19 and 15 -> 17,
  epidemic deaths +5.5% and +12.8%).
- Revolts end in concessions or suppression roughly evenly here (12 / 8);
  hybrid lords sit near 30 stability (in an 8-seed, 300-turn probe the
  lords' stability over city-turns had median 40 and lower quartile 30), so
  the concession and free-city rules apply often.

### Urban pull in the migration budget

Seeds 42-61 x 200 turns, hybrid, `--cities`, merged head, the native budget
summed over every tick (`AgentSimulator.get_migration_driver_stats`; an
observer, not committed):

| driver | share of migration units | gate open (per evaluated agent-turn) | pull beyond roots |
| --- | ---: | ---: | ---: |
| frontier | 1.78% | 1.34% | 1.03% |
| wage | 3.09% | 2.64% | 2.09% |
| chain | 0.25% | 0.86% | 0.38% |
| **urban** | **1.90%** (4.34% with household followers) | 1.79% | 1.58% |

Urban moves are 3.4% of decided migrations. Voluntary moves are led by
young adults (41% of voluntary-led decisions aged 20-34, 29% 35-49).

## Tick time

Measured before the merge (`a8b4b6d` against `bcf14d8`, Wave 7 defaults;
the merge changes no city or Rust code).
`scripts/agent_scale_benchmark.py` (gains `--cli-arg` to forward CLI
switches), seed 42, 12 regions, starting targets 18,800 and 43,700 so that
about 23,500 and 54,000 agents are alive when measured; 20 warm-up turns
(cities are founded at turn 15, the second detection pass) and 8 timed
turns, two repeats, one child at a time, release builds, shared 4-core
machine. Median per run, wall / process CPU, in ms:

| agents | | base `bcf14d8` | branch, off | branch, `--cities` |
| ---: | --- | ---: | ---: | ---: |
| ~23,500 | Rust tick | 143, 151 / 229, 243 | 157, 130 / 247, 258 | 133, 120 / 225, 215 |
| | whole turn | 221, 221 / 321, 330 | 234, 214 / 327, 345 | 211, 188 / 312, 300 |
| ~54,000 | Rust tick | 586, 642 / 1,050, 1,042 | 367, 373 / 1,041, 1,076 | 520, 534 / 1,072, 1,063 |
| | whole turn | 757, 782 / 1,317, 1,314 | 483, 481 / 1,475, 1,506 | 699, 699 / 1,402, 1,405 |

The cities-on runs had three or four cities from turn 15 (1,600-7,800
residents each). Process CPU is unchanged within the machine's noise: the
switch-off branch runs the base's code path, yet its 54k whole-turn CPU
differs from the base's by 12% in this set and by 2% in the second set. A
starting-target set of 22,000 / 53,000 (25,700 / 64,500 alive when
measured) gave the same picture: Rust tick CPU base 333-340 / 1,545-1,550,
off 326-350 / 1,487-1,505, on 347-353 / 1,566-1,599 ms. The Python tick
is a few `bincount` passes over the agent rows and a loop over the cities;
the Rust cost is one comparison chain per neighbour in the existing pull
evaluation.

### Bundle size

The 500-turn guard world (`tests/test_bundle.py`, seed 1, 5 civs, 10
regions) runs with `--agents off`, where the layer is inert, so the guard is
unchanged. The same world in hybrid mode (merged head): 16.40 MB without and
17.50 MB with `--cities` (under the 24 MB guard); the `cities` field is
0.32 MB, the rest is the diverged world.

## Tests

- `tests/test_cities.py` (34 tests, in the offline lane's `systems-1`
  chunk; the three native ones skip there): switch, dormancy and old saves;
  founding (town size, candidates and dissolving settlements skipped),
  ranks with hysteresis, abandoned and deserted falls, no second city from a
  settlement, the predecessor; commerce, scale independence, dues paid as
  `keep` next turn with the carry, dues to a dead lord dropped; charters
  granted and refused, the grant chance; unrest from misery, hunger and
  occupation; revolts suppressed, conceded and won as a free city (new
  polity, hostility, dues to itself, no revolt against itself), no free
  city from a capital or a one-region realm; sacks on occupation (once per
  cooldown) and conquest (charter revoked), peaceful lord changes; walls
  through the pipeline; the merchant voice within its cap; `city_pull` by
  region and the batch column only when on; the epidemic and credit
  factors and epidemiology reading them; snapshot, history and metrics;
  in-world names of city events through the languages index; the feature
  off never running city code; off-mode determinism; the CLI flag, gate
  forwarding, live default, persistence on resume and analytics; a free
  city living on with every system on; the identity script; native: a
  hybrid run founding cities, the `city_pull` signal consumed and reset
  across turns (gate open while the column is sent, zero once it is
  absent), the budget keys.
- `tests/test_wave3_combined.py`: save/load resume identity with cities and
  every other system on (32-region procedural world, `--agents off`, four
  settlements placed as M56a records them): saved at the first turn from 30
  on with charters, a refusal, dues owed, nomads raiding, loans and
  treaties; every byte of the resumed world after 15 more turns.
- Rust: `migration_drivers` (the urban gate condition by condition, the bit
  identity without `city_pull`, the budget term), and
  `tests/test_urban_pull.rs` (multi-tick: a city draws rural people of its
  realm; the draw stops when `city_pull` returns to 0; determinism).
- `tests/test_healthy_migration.py`: the budget key set gains `urban`.

## Verification

Linux, Python 3.13; native extension built fresh (`maturin develop
--release --locked`) from this tree into the worktree environment and
checked as the compiled `chronicler_agents.chronicler_agents` with real
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` classes
(SHA-256 `96cad2b5...4abe62`). Python lanes at the merged head `d3d53a4`
(later commits change documentation only); `cargo test` on the same Rust
source (the merge changes none).

| Check | Result |
| --- | --- |
| `cargo test --locked` | 933 passed, 0 failed, 2 ignored (base 927; +3 unit, +3 multi-tick) |
| `pytest -m "not slow" -n 2` | 6,002 passed, 3 skipped, 526 subtests (`a95e4d7`: 5,967) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| no-Rust lane (the same environment with `chronicler_agents` removed, slow included) | 5,792 passed, 213 skipped |
| `scripts/run_python_oracle_checks.py` | PASS in 82.9 s: core 1,055, governance 568, systems-1 158 (with `tests/test_cities.py`; its native tests skip), systems-2 201 passed; slowest chunk 30.2 s of 110 s |
| frozen exact-trajectory oracles | pass, no fixture changed |
| identity, switch-on gates, resume identity | above |

Before the merge (`a8b4b6d`): not-slow 5,999 passed, slow 11, no-Rust
5,789, oracle lane PASS (79.6 s). The offline lane does not qualify native
execution; the native checks are the cargo tests, the native pytest lanes
and the gates above. The full 200-seed gate was not run on this slice; it
ran with the city markets ([city-markets.md](city-markets.md)).

## Roadmap

1. **Urban economy, deeper.** Done in part by
   [city-markets.md](city-markets.md): urban food demand drawing grain from
   the hinterland through merchant routing by price, craft demand for raw
   materials, sieges cutting a city's supply, imports in commerce. Open: a
   craft output good, bulk grain trade (merchant capacity caps imports at
   about 2% of a city's food), finance's merchant lenders by city rather
   than by realm.
2. **Guilds and patricians as a faction.** A city faction in `factions.py`
   needs a new `FactionType` value (an enum and state-shape change); this
   slice routes the voice through the merchant faction instead.
3. **Free cities in the polity ladder.** Leagues of free cities through the
   federation code; free cities as clients of a protector (diplomacy's
   client stage); recapture wars by the old lord.
4. **Culture and knowledge.** Done in part by
   [scholarship.md](scholarship.md): libraries founded and kept by cities,
   academies and temple schools, scholars drawn to them, techniques and
   archives kept there and lost in sacks. Open: technique diffusion weighted
   by urban contact.
5. **War.** Sieges that pick city regions as targets by wealth; sacks that
   kill residents and destroy buildings; walls as their own level.
6. **Viewer.** The Cities tab exists ([city-markets.md](city-markets.md));
   a map layer does not.
7. **Calibration.** The full 200-seed gate with the switch on passed
   ([city-markets.md](city-markets.md); rebellion 0.0308, arcs pass); a
   city proxy for `--agents off` is still open.

