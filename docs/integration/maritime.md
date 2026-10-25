# Maritime layer: fleets, sea control, blockade, naval campaigns, piracy, colonies

Branch `feat/maritime`, started on `integrate/wave-3` at `20eeead` (Geography
2.0, the contact ledger, campaign warfare, causal provenance, default-off
epidemiology, finance and diplomacy) and merged with `integrate/wave-3` at
`92b6122` (the food-balance corrections), which is the identity and gate
base for every result below. Code: `src/chronicler/maritime.py`
(behavior) and `src/chronicler/maritime_state.py` (persisted state); native
change in `chronicler-agents/src/merchant.rs` and `src/ffi/mod.rs`.

**Status.** On by default for new worlds since the Wave 8 full gate
([defaults-wave8.md](defaults-wave8.md)); `--no-maritime` opts out and saved
worlds keep their setting. Originally default off behind
`WorldState.maritime` (CLI `--maritime`).
With the switch off no maritime code runs and every output is byte-identical
to `92b6122` (see [Identity](#feature-off-identity)). The 20-seed subset gate
passes with the switch on (see [Results](#results)); the full 200-seed gate
was not run.

## What was built, and what was cut

| Part | Built |
| --- | --- |
| Sea model | Procedural worlds: Geography 2.0's sea zones; every sea lane belongs to one zone. Template worlds: one derived zone per connected group of coast-clique regions, every edge between two of them a lane. Built once when the switch is turned on and saved. |
| Fleets | Per civ (at most 3), commissioned at own coastal ports by a naval programme; cost treasury, and timber from physical stocks where the goods economy keeps them (hybrid) or its price in coin elsewhere; upkeep every turn; lost in battles, storms and to unpaid upkeep. |
| Zone control | Per zone each turn: `uncontested` (no fleet strong enough), `contested` (hostile fleets, none dominant) or `controlled` by one civ. |
| Naval battles | Fleets of civs at war sharing a zone fight; losses, retreat to refit, war score and weariness through the campaign `WarRecord`, a named battle for decisive ones. |
| Blockade | A controller at war with a civ that holds ports in its zone closes that civ's lanes there: trade routes, goods-economy boundary pairs, the native merchant graph, the contact ledger's route proxy, and the enemy's sea supply. |
| Naval campaigns | Armies cross a lane only with an escort fleet in the zone (20 soldiers per ship per turn) or under their own command of it; never through an enemy-commanded zone. They wait on the shore and request an escort, which the next maritime tick answers. Landings fight through the existing campaign battle/siege code, at 0.85 power on the landing turn. |
| Piracy | Pirate pressure per zone grows with sea traffic where no one commands the sea (faster where fleets contest it) and is suppressed under command. It skims the `--agents off` route proxy; in agent modes it seizes real merchant cargo in Rust (the dormant `Raid` loss reason, now active). Owners lose treasury; reports are a chronic provenance episode. |
| Colonization | Through the existing EXPAND path: an unclaimed coast the civ cannot walk to (over land, through its own or unclaimed regions) is a target only while its fleet is in that zone. Every other target keeps the base reach. Civs with no walkable land left build a small colony fleet, and while it stands off such coasts EXPAND aims there. |
| Diplomacy | With diplomacy on, naval battles add war grievances like land battles (ships for soldiers) and a standing blockade an embargo grievance per turn. |
| Provenance | Commissions cite the war or the pirates they answer; battles cite the war and every fleet; control cites the battle or the fleet; blockades cite the control and the war; piracy cites the zone's status event; landings cite the escort or the command and the war, and the fight on the beachhead that turn cites the landing; colonies cite the fleet. |

**Cut** (and why):

* *Naval transport capacity as a separate unit, troop ships, ship classes and
  shore bombardment*: escort capacity per ship stands in for transport.
* *Privateering missions* (fleets raiding enemy trade on orders): the raid
  risk is pirate pressure only; war at sea raises it through contested zones.
* *Fleet movement between unconnected water bodies*: fleets sail only along
  zone neighbours; derived template zones have none.
* *Navigation techniques*: `navigation_level(world, civ)` is the only
  reader and returns 0 (neutral) until the technique registry (another line
  of work) exposes `chronicler.techniques.technique_level`. The existing
  tech focuses still count: `naval_power` raises fleet quality, `navigation`
  lowers storm risk.
* *Naval battles in `war_state.battles`*: they live in `MaritimeState.battles`
  so land-battle consumers (contested regions, viewer battle lists) never see
  a zone where they expect a region.
* *Viewer panels*: `history[n].maritime` is in the bundle; the viewer does
  not display it. (Since added on `feat/viewer-systems` as tables and a
  zone-control strip, then a Sea map layer: see
  [viewer-systems.md](viewer-systems.md).)

## Sea model

### Procedural worlds

`MaritimeState.zones` mirrors `WorldGeography.sea_zones` (same order, so a
zone's index is stable): kind, ports (`coastal_regions` as region indices)
and neighbour zones. Every entry of `WorldGeography.sea_lanes` becomes a lane
row `(a, b, zone)` with `a < b`: the lowest-index zone both ends border, or,
for the generator's land-mass crossings between different zones, the zone
(among those either end borders) whose centre is nearest the lane's midpoint.

### Template worlds: the coast clique

Template and scenario worlds have no sea zones; `compute_adjacencies` joins
every coast/river/maritime region to every other (the "clique"). The derived
model takes the connected groups of those regions (over their mutual edges)
with at least two members; each is one zone of kind `coast`, named after its
lowest-index region ("the Obsidian Sea"), with no neighbour zones, and every
edge between two of its regions is a lane. A land border between two clique
regions cannot be told apart from the clique edge, so it counts as a lane
too. Template worlds with fewer than two coastal regions have no sea and the
layer does nothing there (most 8-region template seeds: only 42% of them draw
both coasts; 12-region worlds always have one zone and one lane).

`MaritimeState.landmass` (components with lanes removed) is kept as world
metadata. Generated worlds are almost always one land mass (every procedural
world from 24 to 150 regions surveyed was), which is why colonization uses
walkable reach rather than land masses.

## Turn placement

| When | What |
| --- | --- |
| Phase 2 (`--agents off`) | `observe_phase2`: sea-lane trade and piracy measured on the goods-route proxy rows the contact ledger uses (`contact_ledger.off_mode_trade_rows`) |
| Phase 2 (agent modes) | goods-economy boundary pairs over blockaded lanes dropped before `tick_economy` |
| After Phase 5 | `tick_maritime` (order below) |
| Campaign tick | crossings, escort requests, landings, retreat and supply rules |
| Agent tick | the merchant route graph without blockaded lanes and with `sea_raid_risk`; raids happen in the native mobility phase |
| End of turn (agent modes) | `observe_agent_sea_trade` reads the native sea-crossing log |
| After Phase 10 (diplomacy on) | naval battles and blockades enter diplomatic memory |

`tick_maritime`: drop fleets of fallen civs and re-home fleets that lost
their port; consume the measured sea trade and piracy (piracy reports,
treasury losses); upkeep; naval programmes; orders and one zone of movement;
clear the consumed escort requests; storms; naval battles; zone control;
blockades; pirate pressure; prune landings older than this turn.

Trade consumers in Phase 2 read the blockades and pirate pressure of the
previous tick (one turn of lag, like every other Phase 2 input); the agent
tick and the campaign tick read this turn's.

## Fleets

**Naval programme** (per living civ with ports or fleets). For every zone
within reach (3 zone hops of its ports, plus where its fleets are) it wants:

| Need | Ships | Condition |
| --- | --- | --- |
| patrol | 4 | own port in the zone, sea trade there last tick, pirate pressure >= 0.15 |
| colony | 3 | no walkable unclaimed land left, military at the EXPAND threshold, an unclaimed coast it cannot walk to in the zone |
| war | 6 + 1.25 x enemy ships there | an enemy (at war) holds a port or has ships in the zone |
| escort | the ships its waiting armies asked for | escort requests from the campaign tick |

Total wanted is capped at 6 per port plus military / 5 (max 60). It builds
up to 4 ships a turn, spending at most 30% of the treasury above a reserve of
30: 8 coin per ship plus 2 timber, taken from its regions' free stocks
(stock minus merchant reservations and pending departures, port first) in
hybrid runs, the shortfall (or all of it in other modes) bought at 3 coin per
timber. Ships join the civ's fleet in the shipyard's zone, form a new fleet
(only with at least 2 ships), or join its nearest fleet when it has three.

**Upkeep**: one coin per two ships per turn; an unpaid fleet loses 10% of
its ships (at least one). Fleets below 2 ships are gone.

**Orders**: per civ, fleets (largest first) take the most urgent unmet need
within range (escort, war, colony, patrol; then nearest), avoid zones where
the enemy is more than 1.5x stronger (except home waters), and sail one zone
toward it. After a defeat a fleet refits in home waters for 3 turns.

**Storms**: 1% per fleet per turn, x1.5 ocean, x1.0 sea, x0.8 coast, x0.3
lake, x2 in winter, x0.7 with the `navigation` focus (and x(1 - 0.15 per
navigation level), floor 0.3). A storm sinks 15-35% of the ships (at least
one).

**Quality**: `(1 + 0.12 x era index) x (1 + 0.1 x navigation level)`, x1.25
with the `naval_power` focus; x1.1 fighting in a zone with own ports.

## Naval battles and control

Each zone, each pair of civs at war with ships there fights once a turn (a
civ fights at most one battle per zone). Power = ships x quality x U(0.85,
1.15). A ratio of 1.2 is decisive: the loser loses 25% + 15% per unit of
excess ratio (max 60%), the winner 15% - 5% (min 5%); otherwise both lose
10%. Losses are split over fleets by largest remainder. War score: +-(4 + 8
x the loser's loss share) battle points; both sides gain war weariness; the
loser loses 2 stability (guard-shock).

**Control**: the strongest civ in a zone commands it when it has at least 3
ships and twice the strength of every civ at war with it there combined;
hostile fleets without such dominance make the zone contested; no fleet (or
a lone squadron of 2) leaves it uncontested. Neutral fleets do not contest.
Command won from a rival, out of a contest, by battle or over an enemy's
ports emits `sea_control`; peacetime patrols coming and going are silent.

## Blockade

For every zone commanded by a civ at war with a civ that holds a port there,
a `Blockade(zone, blockader, target)` stands while that holds (`blockade` and
`blockade_lifted` events). Its lanes with a target-held end are
`MaritimeState.blocked`:

* `resources._compute_active_trade_routes` skips them (direct and the
  navigation 2-hop routes), so a pair that touches only across the sea loses
  its route: Phase 2 trade income, goods routes, TRADE partners;
* the goods-economy boundary-pair batch (hybrid) and the native merchant
  route graph drop them;
* the contact ledger's `--agents off` route proxy records nothing on them;
* the target's armies draw no supply through any zone an enemy commands
  (`NavalContext.supply_graph`), so an overseas army supplied only across
  such a zone is cut off.

## Naval campaigns

`WarContext.naval` (a `NavalContext`, `None` with the switch off):

* **Planning**: objectives and paths use only lanes the civ could cross: in
  a zone it commands, where it has a fleet, or where it has a port (a fleet
  can be built there), never through an enemy-commanded zone.
* **Crossing**: at the shore, an army crosses when its civ commands the zone,
  or its ships there can still carry the army this turn (20 soldiers per
  ship); otherwise it waits and files an `EscortRequest(civ, zone, ships)`,
  which the next maritime tick answers (escort need, fleet orders).
* **Landing**: crossing onto ground the civ does not hold is an
  `amphibious_landing` (the first landing of each army is one overseas
  campaign); the army fights at 0.85 power that turn; battles, skirmishes and
  sieges are the existing campaign code.
* **Retreat**: a beaten army cannot fall back across a lane unless its civ
  commands the zone or has ships there.

## Piracy

Pirate pressure `p` per zone (start 0.05; lakes 0 and capped at 0.3), with
traffic `t = min(1, last tick's sea cargo / 1.0)`:

* uncontested: `p += 0.03 t (1 - p) - 0.01 (1 - t) p`;
* contested: `p += 0.04 max(t, 0.5) (1 - p)`;
* controlled: `p *= 0.75`, and no piracy at all.

Outside command, pirates take `0.25 p` of the sea cargo: `--agents off`
skims the route proxy (and the ledger with it); agent modes send that
probability per crossing to Rust, which seizes the merchant's cargo. The
cargo owners (origin region's controller) lose 2 coin per unit (whole coins
plus a deterministic chance for the fraction). Zones losing at least 0.5
units report `piracy` (folded into one episode per zone, at its first port,
with a `piracy_ended` close).

## Colonization

`expansion_candidates` filters EXPAND's unclaimed list (eligibility and
resolution alike): an unclaimed port the civ's settlers cannot walk to
(`land_reachable`: breadth-first over land edges through unclaimed regions
from all its regions) is kept only when the civ has a fleet in one of its
zones that no enemy commands. While a fleet on a `colony` mission stands in
a zone with such coasts, the targets narrow to those coasts (the settlers
board it; without this the fleet only added a coast or two to EXPAND's
random pool, and colony fleets sailed without landing anyone).
`overseas_zone` (before the claim) and `note_colony` record the colony,
cite the fleet and rewrite the event as "settled X across the Y Sea,
carried by Z". Inland targets and walkable coasts are untouched otherwise,
so on a world without sea nothing changes.

## Native change

* `RouteGraph.sea_lanes`: filled from an optional `sea_raid_risk` Float32
  column of `set_merchant_route_graph` (negative on land edges). Absent, the
  map is empty and the mobility phase is unchanged.
* `merchant_mobility_phase_at(..., turn, ...)`: before a transit hop across
  a sea lane, the crossing is logged (`SeaCrossing`) and, for a positive
  risk, a roll on its own stream (`MERCHANT_RAID_STREAM_OFFSET = 2300`, keyed
  on agent id, lane and turn, same composite-stream discipline as knowledge)
  may seize the cargo: `ShadowLedger::seize` takes it off the in-transit
  book, the trip resets, nothing arrives (the departure debit stands), and
  the robbed merchant goes home like a delivering one
  (`return_delivering_merchants_home`, from the food-balance correction).
  `merchant_mobility_phase` keeps its signature (turn 0).
* `LossReason::Raid` is active; `Disruption` and `Spoilage` stay dormant.
* `AgentSimulator.get_sea_trade_log()`: this tick's crossings (rebuilt every
  tick, never drained). `get_merchant_trip_stats()` and the delivery
  diagnostics keep their exact keys.

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--maritime` / `--no-maritime` (`BooleanOptionalAction`) |
| World field | `WorldState.maritime: MaritimeState \| None` (presence = on) |
| Default | **On** (`maritime.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, since the full gate in [defaults-wave8.md](defaults-wave8.md)) for `execute_run`, batch and the live server; `--no-maritime` opts out and drops the state; resumed, forked and caller-supplied worlds keep their setting. `scripts/benchmark_headless.run` pins it off so the frozen performance oracles replay the same worlds |
| Gate runner | `scripts/m53b_run_validation.py --maritime` forwards the switch to every run and records it in `run_manifest.json` |
| Dormant fields | `WorldState.maritime` and `TurnSnapshot.maritime` are `None` by default and omitted from serialized output, so flag-off saves, bundles and fixtures keep their bytes and old saves load unchanged |
| State | zones (status, controller, pirates, status event), lanes, land masses, fleets, battles, blockades, colonies, blocked lanes, escort requests, landings, pending measurements, counters; region, civ and zone identity by index |

The pending sea trade and piracy, the escort requests and the landings are
persisted inputs consumed by the next tick (a resumed run consumes exactly
what an uninterrupted one would); the only derived cache (`_CacheSlot`) never
serializes or affects equality.

## Parameters

All in `chronicler/maritime.py` (illustrative, not fitted to any gate):
`SHIP_COST 8`, `SHIP_TIMBER 2.0`, `TIMBER_PRICE 3`, `UPKEEP_SHIPS_PER_COIN 2`,
`UNPAID_LOSS_SHARE 0.10`, `BUILD_PER_TURN 4`, `BUILD_SHARE 0.3`,
`TREASURY_RESERVE 30`, `MAX_FLEETS_PER_CIV 3`, `SHIPS_PER_PORT 6`,
`MAX_SHIPS_PER_CIV 60`, `MIN_FLEET_SHIPS 2`, `PATROL_SHIPS 4`,
`COLONY_SHIPS 3`, `WAR_SHIPS 6`, `WAR_SHIPS_MATCH 1.25`, `FLEET_RANGE 3`,
`SOLDIERS_PER_SHIP 20`, `ERA_QUALITY_STEP 0.12`, `NAVIGATION_QUALITY 0.10`,
`NAVAL_POWER_FOCUS 1.25`, `HOME_WATERS 1.10`, `DECISIVE_RATIO 1.2`,
`NAVAL_POINTS_BASE 4`, `NAVAL_POINTS_SCALE 8`, `REFIT_TURNS 3`,
`EVADE_RATIO 1.5`, `NAVAL_DEFEAT_STABILITY 2`, `NAVAL_WEARINESS 0.5`,
`STORM_CHANCE 0.01`, `STORM_WINTER 2.0`, `STORM_LOSS 0.15-0.35`,
`CONTROL_RATIO 2.0`, `MIN_CONTROL_SHIPS 3`, `PIRATE_GROWTH 0.03`,
`PIRATE_GROWTH_CONTESTED 0.04`, `PIRATE_DECAY 0.01`,
`PIRATE_SUPPRESSION 0.25`, `PIRATE_TRAFFIC_REF 1.0`, `PIRACY_MAX_SKIM 0.25`,
`PIRATE_PATROL_MIN 0.15`, `PIRACY_TREASURY_PER_UNIT 2.0`,
`PIRACY_EVENT_MIN 0.5`, `LANDING_POWER 0.85`.

Contracts: no new accumulator category (treasury `keep`, the naval-defeat
stability loss `guard-shock`); no action type, enum value or action-weight
modifier added (EXPAND eligibility changes only through its target list);
`ZONE_STATUSES`, `FLEET_MISSIONS` and `COUNTER_KEYS` are append-only; all
randomness is `random.Random(stable_hash_int("maritime", <namespace>, seed,
turn, ...))` (`storm`, `battle`, `piracy`) plus the native raid stream.

## Feature-off identity

1. **Direct runs** (`scripts/diplomacy_identity.py compare`). The base
   export (`92b6122`, with its own extension built from that tree: SHA-256
   `e38fbfde…e3b26f`, the same binary the food-balance work recorded)
   against this branch (fresh extension), same interpreter and
   `PYTHONHASHSEED=0`: template default worlds, seeds 42 / 7 / 1234,
   `--agents off` 300 turns and `--agents hybrid` 200 turns, and a procedural
   48-region x 10-civ world (seed 7, off 200 and hybrid 120 turns). Every
   output file (`state.json`, `chronicle.md`, `memories_*.json`,
   `agent_events.arrow`, `chronicle_bundle.json` minus
   `metadata.generated_at`): **72 files, 0 differences** with the default
   switch and 72 files, 0 differences with an explicit `--no-maritime`, on the final
   head. (The same proof against `20eeead` before the merge: 72 files, 0
   differences.)
2. **Gate batch.** The base subset gate (run from the exported `92b6122`
   tree with its extension) against this branch's switch-off subset gate,
   20 seeds x 200 hybrid turns, final head: all 20 seed directories, 2,160
   run files (states, bundles, agent-event and validation sidecars,
   memories, chronicles), plus the validation report, gate decision and both
   summaries (batch path normalized): 0 differences.
3. **Switch on, no sea.** With `--maritime`, the 13 subset-gate seeds whose
   template world has fewer than two coasts end with exactly the base's
   state (minus the `maritime` field) and chronicle: the layer is inert
   without a sea, and the sea-lane raid column of all-land graphs leaves the
   native mobility phase unchanged.
4. **In the suite.** The frozen exact-trajectory oracles (golden fixtures
   `corrected_food_balance_2026_10*.json`) pass unchanged;
   `test_feature_off_never_runs_maritime_code` forbids every maritime entry
   point during a 30-turn procedural campaign run; the Rust test
   `test_graph_without_sea_lanes_is_unchanged` pins the native no-op.

## Tests

`tests/test_maritime.py` (44 tests, also in the bounded offline lane):

* sea model: procedural zones and lanes, the template coast clique (one zone
  "the Obsidian Sea" on 12-region worlds), no sea without a clique, the
  neutral navigation level;
* switch: dormancy and omitted fields, old saves, a monkeypatched switch-off
  campaign run that forbids every entry point, round trips with a warm
  cache, the CLI flag, gate forwarding, the snapshot, analytics and the
  report script on flag-on and flag-off runs;
* fleet lifecycle: a war need commissioning a fleet paid from the treasury,
  no one-ship squadrons, upkeep and unpaid losses, storms sinking ships and
  small fleets, battle losses, retreat to refit, war score and provenance,
  deterministic battles;
* zone control: uncontested, silent peacetime command, neutral fleets not
  contesting, hostile fleets contesting, command regained at twice the
  hostile strength, the three-ship minimum;
* blockade: closing the enemy's lanes (with provenance) and lifting them;
  trade routes, the ledger proxy, goods-economy batches and the merchant
  graph cut; enemy command cutting sea supply;
* naval campaigns: an army waiting on the shore and requesting an escort; an
  escorted landing citing its fleet, fought through the campaign siege/
  skirmish code and cited by that fight; per-turn escort capacity; crossing
  under own command and never under enemy command; the one-turn landing
  penalty; objectives ignoring lanes the civ cannot cross;
* piracy: skim and treasury loss (consumed once: multi-turn reset), chronic
  reports citing the zone's status, suppression under command, the ledger
  skim, the native crossing log folded in (stub), the real extension
  accepting the column, and a hybrid run in which real native merchants
  cross sea lanes, are raided and the run repeats exactly; a patrol citing
  the raid it answers;
* colonization: overseas coasts gated on a fleet, inland targets keeping the
  base reach, sealess worlds unchanged, a colony citing its fleet, land
  expansion not a colony, the colony need, settlers following a colony fleet;
* runs: determinism with fleets, save/load resume identity with fleets at sea
  (every byte of the resumed world after 15 more turns), escort requests and
  pending trade consumed every tick;
* diplomacy: naval battles and blockades in diplomatic memory.

`tests/test_wave3_combined.py` adds maritime with epidemiology, finance and
diplomacy on one 32-region procedural world: state round trip, save/load
resume identity at the first turn from 30 on where every system is live
(fleets at sea after a naval battle, sea trade, an epidemic death, a loan, a
treaty), and determinism.

Rust: `tests/test_maritime_raid.rs` (6): the graph without the column is
unchanged, negative risks are land edges, a safe crossing is logged and
delivers, a raided cargo is seized, never arrives and its merchant goes
home, raid rolls are deterministic and keyed, the log is rebuilt every tick.
The stream-offset collision test now includes the catastrophe (2200) and
raid (2300) offsets.

## Results

| Check (final head, Linux, Python 3.13, shared 4-core host) | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (extension rebuilt from this tree; compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | 5,657 passed, 3 skipped (base `92b6122`, its own extension: 5,610 passed, 3 skipped; +44 maritime and +3 combined tests) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -q -n 2`, slow included, as CI runs it) | 5,461 passed, 199 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19's guard line applied locally, not committed) | PASS: 1,677 passed, 6 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O |
| `cargo test --release` (all crate tests) | 894 passed, 0 failed |

### Subset gate (20 seeds x 200 turns, hybrid, `--parallel 2`)

Base `92b6122` (exported tree, its own extension) against this branch with
`--maritime`, compared with `chronicler.validation_compare`: **PASS** and
**NO REGRESSION**; **0 of 20 worlds extinct** on either side.

| Oracle / metric | Base `92b6122` | `--maritime` |
| --- | --- | --- |
| community, era | PASS | PASS |
| needs | PASS (15 seeds, effect 0.82) | PASS (16, 1.00) |
| cohort | PASS (19, effect 1.24) | PASS (19, 1.13) |
| arcs | PASS (18 seeds with three arc types) | PASS (19) |
| artifacts | PARTIAL (creation 1.88, loss 1.3%) | PARTIAL (1.91, 1.6%) |
| regression | PASS (strict) | PASS (strict) |
| satisfaction / latest | 0.585 / 0.595 | 0.584 / 0.610 |
| migration / rebellion per agent-turn | 0.0589 / 0.0437 | 0.0588 / 0.0440 |
| Gini in range / occupation violations | 0.855 / 0.28% | 0.911 / 0.19% |
| all founders alive | 0.15 | 0.15 |
| final population min / median / max | 106 / 197 / 295 | 106 / 177 / 273 |

Only 7 of the 20 default worlds draw both template coasts and so have a sea
(seeds 44, 46, 53, 55, 57, 59, 60); the other 13 are outcome-identical to
the base. Over the batch: 13 fleets commissioned (83 ships), 11 naval
battles, 4 blockades, 5 overseas campaigns, 2.0 cargo units lost to
pirates, no colonies, 2,164 cargo units carried across sea lanes; polities
alive 3.05 per world on both sides.

### Procedural worlds (48 regions x 10 civs, 200 turns, seeds 7 / 13 / 29)

`scripts/maritime_report.py`, switch on against off (off is the base: see
identity). "Sea cargo" is the maritime layer's own measurement (route-proxy
units in `--agents off`, native merchant cargo per sea-lane hop in hybrid);
"ledger sea trade" is the contact ledger's final decayed trade stock on
sea-lane edges, measured the same way on both sides.

| Run | Fleets (ships) | Naval battles | Blockades | Piracy losses | Overseas campaigns | Colonies | Sea cargo | Ledger sea trade on / off | Polities alive on / off |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off, seed 7 | 9 (38) | 4 | 2 | 1.4 | 3 | 0 | 371 | 11.2 / 14.5 | 12 / 15 |
| off, seed 13 | 61 (300) | 98 | 39 | 2.8 | 12 | 1 | 1,139 | 67.2 / 43.0 | 19 / 18 |
| off, seed 29 | 18 (83) | 8 | 9 | 8.7 | 5 | 0 | 380 | 10.0 / 20.4 | 20 / 20 |
| hybrid, seed 7 | 18 (92) | 11 | 14 | 1.2 | 0 | 0 | 227 | 1.9 / 0.0 | 7 / 14 |
| hybrid, seed 13 | 20 (120) | 14 | 5 | 10.9 | 4 | 2 | 993 | 27.2 / 32.1 | 9 / 10 |
| hybrid, seed 29 | 16 (64) | 1 | 2 | 14.4 | 0 | 1 | 1,853 | 42.0 / 31.1 | 8 / 9 |
| **mean** | 23.7 (116) | 22.7 | 11.8 | 6.6 | 4.0 | 0.7 | 827 | 26.6 / 23.5 | 12.5 / 14.3 |

All runs finished; no world went extinct (final population 571-1,188 on,
388-1,169 off). Seed 13 is a crowded coast: ten civs share four zones, and
wars there are fought at sea every few turns.

Side effects in the same runs (on / off):

| Run | Wars | Land battles | Expansions | Trading pairs (mean) | Treasury per civ | Population | Stability |
| --- | --- | --- | --- | --- | --- | --- | --- |
| off, seed 7 | 39 / 37 | 110 / 122 | 4 / 6 | 6.7 / 10.7 | 966 / 1,714 | 735 / 786 | 43 / 41 |
| off, seed 13 | 86 / 70 | 209 / 198 | 13 / 15 | 22.8 / 32.2 | 837 / 1,736 | 1,188 / 1,139 | 35 / 35 |
| off, seed 29 | 64 / 65 | 179 / 204 | 17 / 17 | 24.1 / 27.8 | 1,247 / 1,633 | 1,185 / 1,169 | 42 / 29 |
| hybrid, seed 7 | 21 / 25 | 53 / 34 | 24 / 27 | 10.5 / 10.7 | 1,470 / 647 | 571 / 388 | 26 / 17 |
| hybrid, seed 13 | 9 / 14 | 24 / 43 | 26 / 26 | 14.5 / 17.4 | 3,810 / 2,948 | 810 / 753 | 30 / 21 |
| hybrid, seed 29 | 5 / 12 | 24 / 42 | 31 / 32 | 13.8 / 18.5 | 2,894 / 2,946 | 948 / 963 | 37 / 34 |

The on and off worlds diverge within the first six turns (the coastal
EXPAND gate and the initial pirate pressure act at once), so single-run
differences mix mechanism with divergence; three seeds establish no
direction for wars or polities. What holds in every run: fewer living civ
pairs trade (blockades and piracy cut sea commerce), and in `--agents off`
treasuries end a quarter to a half lower (fleets cost coin; the base
off-mode treasury is a large idle stock). In the 20-seed gate (7 seas) the
same quantities barely move: wars 2.2 against 2.1 per world, expansions 1.7
against 1.6, trading pairs 2.7 against 2.6, treasury 5,962 against 5,925,
population 180 against 186, stability 35.9 against 34.8.

The hybrid seed 7 world keeps 7 polities against 14: with the switch off it
sees five secessions (15 civ records, 14 alive); with it on, none (10
records), but eleven annexations against three, thirteen occupations against
four, and two states conquered.

### Stories

Event ids are the runs' own (`<turn>:<type>:<n>`); arrows follow recorded
causes.

**1. A war lost at sea** (procedural 48x10, seed 7, `--agents off`).
Pythysi League goes to war with the Kingdom of Geniwyn for its subjugation
(`17:war_declared:0`). Both commission war fleets the same turn, each citing
the declaration: Pythysi's First Fleet (3 ships) at Vicaros Strand and
Geniwyn's First Fleet (4 ships) at Nylion Forest. Geniwyn wins the Battle of
the Cesora Deep that turn (citing the war and both fleets). Next turn
Pythysi's First Warband crosses the Pyra Sound and lands at Tzetoya Jungle,
"escorted by the First Fleet of Pythysi League" (`18:amphibious_landing:0`
-> its fleet and the war). Geniwyn adds two more squadrons, wins the Second
Battle of the Pyra Sound (`19:naval_battle:0`), takes command of the sound
(`19:sea_control:0` -> the battle) and blockades Pythysi's ports there
(`19:blockade:0` -> command and war), then the Raros Sea too
(`21:blockade:0`); Pythysi's fleet is sunk in the Third Battle of the Pyra
Sound (`20:fleet_lost:0` -> the battle). The landed warband is beaten at
Dovondor Strand and destroyed (`22:army_destroyed:0`); Geniwyn's Second Warband
lays siege to Vicaros Strand, Pythysi's shipyard, and Pythysi capitulates in
the Silver Accord, paying 32 in reparations (turn 26; war score -68, every
point won in battle). The blockades had lifted after two and five turns
(`23:blockade_lifted:0`, `24:blockade_lifted:0`, each citing its blockade).

**2. The beach at Tirion Strand** (same world, turns 148-175). The Hatoyan
Kingdom commissions its First Fleet at Motoya Rainforest to guard its sea
lanes (turn 148). At turn 163 it opens four wars at once, the first against
the Confederacy of Wodeth for Gewalion Weald (`163:war_declared:0`). Its 11th
Warband (3 soldiers, all it can muster) sails across the Tara Bight under
the First Fleet and lands at Tirion Strand (`163:amphibious_landing:0` ->
the fleet and the declaration). The landing fights the ordinary campaign
code at reduced power: the Raid on Tirion Strand (`163:war:1` -> the
landing) is a defender's victory, the warband is destroyed
(`163:army_destroyed:0` -> the raid) and Wodeth takes Queen Yitoxa hostage.
Six turns later the 13th Warband makes the same crossing
(`169:amphibious_landing:0`) and meets the same end in the Fourth Skirmish
at Tirion Strand; Empress Xepepan becomes the second hostage. Wodeth's
counter-raid on Motoya Rainforest fails in turn (King Gilawyn taken), and
the Cedar Concordat restores the status quo ante (turn 175).

**3. Raiders in the Gulf of Daros, settlers across the Nyrarion Bight**
(procedural 48x10, seed 13, `--agents hybrid`: real native merchants).
Pirates take merchant cargo in the uncommanded Gulf of Daros in four
episodes (turns 50, 71, 82 and 85-92), each opened by one chronic `piracy`
report at Vandor Coast and closed by `piracy_ended` (`54:piracy_ended:0` ->
`50:piracy:0`, ...). The Republic of Bemidar commissions its First Fleet at
Vandor Coast "to guard its sea lanes", citing the latest raid
(`90:fleet_commissioned:0` -> `85:piracy:0`); the Pomapan Kingdom follows
with two squadrons citing the same raid (turns 93-94). The last episode ends
(`92:piracy_ended:0`), the two patrols pass command of the gulf back and
forth (`97:sea_control:0`, `98:sea_control:0`), no cargo is reported taken
in the gulf after turn 92, and its pirate pressure ends the run at 0.0002. Earlier in the same world the Peterioni League, hemmed in
after settling Dagar Heights and Thenylas Wood (turns 37 and 40), has no
land left it can walk to; it commissions its Second Fleet at Mesiros Shores
"to seek new shores" (`40:fleet_commissioned:0`) and three turns later
"settled Chumapa Wilds across the Nyrarion Bight, carried by the Second
Fleet of Peterioni League" (`43:expand:0` -> the fleet), a coast the Qeduni
Empire's rulers had vowed to settle since turn 0. Peterioni builds roads,
fortifications, irrigation and temples there, creates the Sacred Gilded of
Chumapa Wilds (turn 77) and holds the colony to the end.


## Effects on other systems

* **Trade and the contact ledger.** Blockaded lanes leave trade routes
  (Phase 2 income, goods routes, TRADE partners, the hybrid economy's
  boundary pairs, the merchant graph); piracy skims the off-mode route proxy
  and seizes native cargo. The ledger therefore records less sea commerce,
  which lowers `trade_volume`, dependence and trade warmth and, through the
  ledger, movement spread, merchant great persons and epidemic contact.
* **War.** Naval battle points enter the campaign war score (peace terms and
  timing), both sides gain war weariness and the loser loses 2 stability.
  Armies need an escort or command to cross water, wait on the shore
  otherwise, fight at 0.85 the turn they land, cannot retreat across water
  without ships and lose sea supply in enemy-commanded zones.
* **Expansion.** Unclaimed coasts a civ cannot walk to need a fleet; every
  other EXPAND target is unchanged.
* **Treasury and goods.** Ships, upkeep and piracy losses are `keep`
  treasury charges; in hybrid runs ships consume free timber stocks (never
  merchant reservations or pending departures). With `--finance` on, fleet
  costs come out of the same, tighter treasuries.
* **Diplomacy.** Naval battles add war grievances and standing blockades
  embargo grievances.
* **Food balance.** Raided merchants go home like delivering ones, so piracy
  never relocates population; seized food cargo is lost food.
* **Provenance.** New event types `fleet_commissioned`, `fleet_storm`,
  `fleet_lost`, `naval_battle`, `sea_control`, `sea_contested`,
  `sea_control_lost`, `blockade`, `blockade_lifted`, `piracy` (chronic, with
  `piracy_ended`) and `amphibious_landing`; `landing:<region>` and
  `piracy:<port>` join the causal index. Colonies rewrite their `expand`
  event's description and cite the fleet.
* **Performance.** A maritime tick costs about 4 ms a turn on a 150-region,
  30-civ off-mode world (0.24 s of CPU over 60 turns; whole run 4.6 s either
  way).

## Known gaps

* The full 200-seed gate ran with maritime on in
  [defaults-wave8.md](defaults-wave8.md), together with agendas and nomads.
* Piracy is small in these worlds: most sea lanes have an unclaimed end for
  long stretches, patrols command trade zones early, and one cargo unit per
  merchant trip keeps sea cargo low. The pressure model and the native raid
  are tested; the magnitudes are illustrative.
* Colonization is rare (0-2 per run): procedural worlds are one land mass
  and settlers can walk almost everywhere until late.
* Template worlds with fewer than two coastal regions (most 8-region seeds)
  have no sea.
* Sea-lane trade in agent modes is measured per merchant hop; the ledger's
  delivery records only see one-hop sea deliveries as sea-lane edges.
* No viewer panels (since added: [viewer-systems.md](viewer-systems.md));
  naval battles are not in `war_state.battles`.

