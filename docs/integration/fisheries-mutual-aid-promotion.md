# Fisheries and mutual aid: promotion to default-on

Branch `feat/promote-fisheries-mutual-aid`, based on `integrate/wave-2`
(`cf13f87`). Two systems were built default-off and validated only on fixtures
and dying worlds:

- the renewable fish stock (`chronicler/experimental/fisheries.py`,
  `fisheries_bridge.py`; design in
  [2026-10-05-fishery-stock.md](../experiments/2026-10-05-fishery-stock.md));
- adjacent same-polity mutual aid (`chronicler/mutual_aid.py`; design in
  [adjacent-mutual-aid.md](../experiments/adjacent-mutual-aid.md)).

This branch re-validates both on living 500-turn worlds, fixes what was wrong
in that setting, and turns both on for new worlds. The two default flips are
the last two commits, so either can be reverted alone. The dated experiment
documents are evidence for what they tested and are not rewritten.

## Summary

| | Fisheries | Mutual aid |
| --- | --- | --- |
| Default for new worlds | **on** (`--no-fisheries` opts out) | **on** (`--no-mutual-aid` opts out) |
| Saved on the world | `WorldState.fishery_experiment` | `WorldState.mutual_aid_enabled` |
| Agent modes | active | active |
| `--agents off` | runs (Python or native ecology), but never binds: aggregate coastal populations are too small to overfish | dormant strict no-op. Only an explicit `--mutual-aid` with `--agents off` is still rejected |
| Living template worlds (hybrid) | every fished coast is drawn down; 3 of 10 seeds collapse a fishery within 500 turns | about one convoy per 13 runs of 200 turns: no region has a food surplus to give |
| New narrated events | `fishery_collapse` (importance 7), `fishery_recovery` (6) | `mutual_aid` relief convoys (importance 3, text rewritten) |
| Effect on famine and survival | within run-to-run divergence (below) | none measurable (it almost never fires) |

## Changes

### Fisheries

- **Switch.** `--fisheries` / `--no-fisheries` (tristate; `None` keeps the
  default or the saved setting). Worlds created by `execute_run`, batch and the
  live server follow `fisheries.DEFAULT_ENABLED_FOR_NEW_WORLDS`. Loaded, forked
  and caller-supplied worlds keep their saved `fishery_experiment`.
  `set_fisheries_enabled(world, on, new_world=...)` is the one entry point.
- **Living-world calibration (correction).** A fish slot sustains about
  `recovery_rate × reserve_turns × reference_workers` fishers at base yield.
  At the class default (`reference_workers=200`) that is 64. Template coasts
  carry 20 to 40 fishers, so in 6 seeds × 500 hybrid turns the stock fell to
  0.39-0.81 but never constrained a single catch. In off mode the stock
  barely moved. A new world that enables the fishery now gets
  `NEW_WORLD_REFERENCE_WORKERS = 100` (about 32 fishers), so the densest coasts
  can overfish. The `FisheryConfig` class default is unchanged, so a dormant
  config serializes exactly as before, and saved worlds keep their parameters.
  This is a `[CALIBRATE]` value, chosen from the sweep below.
- **Narration.** `fishery_stock_events` runs right after the stock update in
  both ecology paths (Python, and native including the off-mode
  `EcologySimulator`). A slot that falls below `COLLAPSE_STOCK = 0.25` emits
  one `fishery_collapse` event. Once it is back at `RECOVERED_STOCK = 0.6` it
  emits one `fishery_recovery` event. The gap is hysteresis, so a stock that
  hovers at a threshold does not repeat events. The memory is the new
  `Region.fishery_collapsed` (list of slots). It is `None`, and omitted from
  output, while no slot is collapsed. A removed fish resource clears it
  silently. The events consume no RNG and change no yield. Disabled runs
  neither read nor write the memory.

Calibration sweep (template worlds, hybrid, 6 seeds × 500 turns, fishery on;
aid off, or on in the 200 row, where it never fired):

| `reference_workers` | slots that collapse (< 0.25) | turns with a capped catch (mean per run) | final stock (mean) | mean population |
| --- | --- | --- | --- | --- |
| 200 (old) | 0 of 8 | 0 | 0.71 | 386 |
| **100 (new worlds)** | 3 of 8 | 57 | 0.43 | 386 |
| 64 | 3 of 8, all at the floor for 400+ turns | 213 | 0.31 | 389 |

### Mutual aid

- **Off mode.** Aid moves goods-economy stocks, and those exist only in agent
  modes (with `--agents off` stockpiles are seeded at world generation and only
  shrink through conquest and occupation). `mutual_aid_active(world)` is false
  for `agent_mode` `None` or `"off"`, and then observation and dispatch are
  strict no-ops. A default-on or saved setting therefore runs silently under
  `--agents off`. A hybrid save resumed with `--agents off` also runs without
  error; it keeps `agent_mode="hybrid"`, so, as before, its stress memory is
  cleared for lack of observations and nothing is dispatched. An explicit
  `--mutual-aid --agents off` still raises, because it asks for something that
  cannot happen.
- **Switch.** New worlds follow `mutual_aid.DEFAULT_ENABLED_FOR_NEW_WORLDS`.
  Loaded worlds keep `mutual_aid_enabled`. The live server applies the same
  default to its new worlds.
- **Narration.** Convoy events read "*Civ* sends a relief convoy of 2.8 food
  from *Donor* to hungry *Recipient*; 2.7 arrives (treasury cost 1)." They
  were "*Donor* sent 2.797 food to …".
- No policy constant changed. See the next section for why.

### Harnesses

- `scripts/m53b_run_validation.py` forwards explicit `--fisheries` /
  `--mutual-aid` switches. It never passes `--mutual-aid` to an
  `--agents off` run. The run summary records both.
- `scripts/benchmark_headless.run` pins `fisheries=False, mutual_aid=False`
  for its frozen oracles, like the governance and contact-ledger pins. No other
  golden test goes through the new-world default. The suite passes with the
  defaults flipped.

## Validation on living worlds

All runs are `--simulate-only` on this branch. Run data is outside the
repository. "Template" means the default 8-region, 4-civ world. The runs and
the branch gate used a native build of `1244939`'s Rust. After rebuilding from
this tree (`cf13f87` adds a native snapshot cache), five reruns gave identical
per-turn trajectories: hybrid seeds 42, 48 and 60 × 200 turns, hybrid seed 43 ×
500, and off seed 42 × 500.

### Fisheries: it fires and does what the design claims

Hybrid, template, 10 seeds × 500 turns, both systems on. Mean stock of the
fished slots in controlled regions:

| seed | t1 | t50 | t100 | t200 | t300 | t400 | t500 | collapse turn | capped-catch turns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | 0.96 | 0.47 | 0.25 | 0.18 | 0.16 | 0.20 | 0.15 | 101 | 7 |
| 43 | – | 0.73 | 0.16 | 0.13 | 0.11 | 0.12 | 0.11 | 87 | 187 |
| 44 | 0.99 | 0.68 | 0.66 | 0.61 | 0.66 | 0.64 | 0.61 | – | 0 |
| 45 | 0.98 | 0.68 | 0.62 | 0.60 | 0.63 | 0.58 | 0.56 | – | 0 |
| 46 | 0.97 | 0.46 | 0.36 | 0.37 | 0.36 | 0.36 | 0.35 | 50 | 146 |
| 47 | 0.99 | 0.69 | 0.62 | 0.65 | 0.64 | 0.63 | 0.62 | – | 0 |
| 48 | 0.99 | 0.67 | 0.61 | 0.63 | 0.65 | 0.58 | 0.59 | – | 0 |
| 49 | 0.99 | 0.71 | 0.65 | 0.64 | 0.63 | 0.62 | 0.61 | – | 0 |
| 50 | – | – | – | – | – | – | – | – (coast never settled) | 0 |
| 51 | 0.99 | 0.65 | 0.61 | 0.58 | 0.54 | 0.57 | 0.53 | – | 0 |

Seed 46 has two fished coasts; one sits at the floor and the other near 0.6.

- **Stable.** Stocks settle at `1 − fishers / 32`, or at the harvest-cap floor
  (about 0.11) when fishers exceed what the slot sustains. The catch is then
  capped at the sustainable yield: on seeds 43 and 46 the realized catch per
  fisher fell to as little as 42-53% of potential in lean seasons. All values
  stayed finite and in [0, 1] in every run.
- **Collapse is a commons trap.** No collapsed fishery recovered within 500
  turns. Fishing effort did not fall when the catch fell: coastal populations
  stay at 1.0-1.6× capacity, the food-scarcity bonus favours farming, and
  hybrid hunger does not kill. A `fishery_recovery` therefore needs a
  population loss on that coast (war, plague, emigration). The fixture tests
  cover the event.
- **Off mode is inert.** Aggregate coastal populations are 20-35, and the
  ecology effort proxy is `population // 5`. In 10 seeds × 500 turns of
  `--agents off` the stock stayed at 0.81-0.97 and never capped a catch.
  Outcomes were identical with the fishery on and off.
- **Hybrid checkpoint continuation (gap closed for the fishery's own state).**
  A hybrid resume rebuilds the native agent pool, as it does for every system.
  Bit-identical hybrid continuation would need the pool, RNG, cargo and delivery
  buffers serialized, which is out of scope. What the fishery needs does
  carry over: stocks, catch ratios, per-slot catch budgets, collapse memory
  and config.
  - `test_hybrid_resume_continues_the_fishery_from_its_saved_state` runs
    hybrid, saves, reloads into a fresh `AgentBridge`, and checks that the
    boundary turn packs exactly the uninterrupted run's fish yield and catch
    credit. The saved credit still caps the catch.
  - On seed 43, resumed at t200 and run to t400, the stock went
    0.1290 → 0.1294 across the boundary and stayed at 0.11-0.12, the same as the
    uninterrupted run. Aid memory (8 observed regions with full stress streaks)
    also carried over.
- Shadow and demographics-only runs (60 turns) work with both systems on.

### Mutual aid: why it never fired, and why no threshold change fixes that

The stress side works: almost every populated region qualifies as a recipient
after the first few turns. The donor side never opens, because the goods
economy has no food surplus anywhere. Seed 43, hybrid, 200 turns, 1,576
populated region-turns:

- Pre-consumption food sufficiency is below 0.2 in 68% of region-turns. It is
  at 1.0 or more in 1.5% (24 region-turns): half of them in the first three
  turns (the initial buffer) and all but three in the first 20.
- Food left after the economy tick (the stock aid could move) is below half a
  turn of demand in 1,564 of 1,576 region-turns. At the sampled turns (t50,
  t150) it was 0.0 in every populated region.
- The best-fed regions are fish coasts at about 0.8-0.9. Grain plains run at
  0.0-0.11: water sits at 0.30-0.37 under 1.0-1.6× crowding, which crushes crop
  yields.

Donor reserve sensitivity (number of convoys):

| Worlds | reserve 2.0 turns (unchanged) | 0.5 turns | 0 |
| --- | --- | --- | --- |
| template, hybrid, 6 seeds × 500 turns | 0 | 0 | 19 per run, 29 food per run |
| procedural 64 regions / 16 civs, hybrid, 4 seeds × 300 turns | 2.5 per run (0.95 food) | 13.8 per run (5.4 food) | – |

Typical demand is about 200 food per turn per world. Even with no reserve,
aid would move about 0.03% of food. The thresholds were not calibrated on
dying worlds; the world simply has nothing to share. The policy constants are
therefore unchanged, and the existing adversarial and long-cargo fixtures keep
their exact turn-by-turn expectations. With the defaults on, aid fired 3 times
in 40 template runs of 200 turns: seed 60 at t197 and t199 (2.8 and 6.3 food,
1 treasury each) and seed 81 at t25 (1.0 food). It becomes active once
regions produce more food than they eat. That is the open ecology/goods
balance sweep, which this branch does not attempt.

### Big procedural worlds

`--worldgen procedural --regions 64 --civs 16`, both systems on, 500 turns,
seeds 11 and 12, in hybrid and in off mode: no crash, no invalid state. Hybrid
convoys: 6 and 1. Fish stocks ended at 0.95 mean (minimum 0.40), with no
collapse.

These hybrid worlds lose about 90% of their population: from a peak of about
1,050-1,100 to 84-120 at t300 and 103-134 at t500.
This is **pre-existing** and unrelated to these systems: seed 7 with both off
goes 758 → 93 by t150, the same as with both on (74). Off-mode procedural worlds
stay alive (about 830 at t500). Flagged for the Geography 2.0 / ecology owners.

### Effect on famine and survival

Hybrid template worlds, both on versus both off:

| Measure | on | off |
| --- | --- | --- |
| 10 seeds × 500 turns: famine events per run | 764 | 742 |
| mean population | 380 | 383 |
| final population | 434 | 427 |
| polities alive at t500 | 2.8 | 2.7 |
| 40 seeds × 200 turns: famine events per run | 297 | 293 |
| final population | 395 | 391 |
| runs where all initial civs survive | 10 / 40 | 9 / 40 |
| worlds with zero living population | 0 | 0 |

Hybrid famine does not kill directly (agents own the population). It drains
stability. In off mode, where famine does kill, outcomes are identical, as
noted above. Fish-only runs give the same 40-seed survival and famine figures
as both-on runs, so the residual differences come from the fishery: its
lagged catch credit (set from last turn's fishers) perturbs a coastal harvest
whenever the fishing workforce grows, and trajectories then diverge. The
divergence goes both ways: 3 of 40 seeds change their all-survive flag, 2 up and
1 down.

## Subset gate (20 seeds × 200 turns, hybrid, `--parallel 2`)

Base: `1244939` exported, which is behavior-identical to `cf13f87` (its
merge is a byte-identical performance change). Branch: this tree, both
defaults on.

| | Base | Branch |
| --- | --- | --- |
| Gate | PASS | PASS |
| Required (community / needs / cohort) | PASS | PASS |
| `validation_compare` | | exit 0, `regression_detected: false`, no new required failures |
| regression (informational in subset) | PASS, calibrated floor | **FAIL** (`civ_survival`) |
| artifacts / determinism | PARTIAL / SKIP | PARTIAL / SKIP |
| satisfaction mean / latest | 0.4714 / 0.4348 | 0.4782 / 0.4365 |
| migration per agent-turn | 0.0513 | 0.0512 |
| famine per run / final population | 285.7 / 399.9 | 291.7 / 399.3 |
| fishery collapses / convoys per run | 0 / 0 | 0.4 / 0.1 |

The only oracle change is regression `civ_survival`. That check requires the
fraction of runs in which every initial civ survives to stay at or below 0.20.
Base sits exactly on the limit (4 of 20). On the branch, seed 48 keeps all
four civs to turn 200, giving 5 of 20 (0.25). This is run-to-run divergence,
not a trend:

- On seeds 62-81, base itself is at 0.25 (5 of 20), the same as the branch.
- Across 40 seeds the branch is 10/40 and base is 9/40, with flips in both
  directions.

The calibration dates from the extinction era: the extinction-fix note records
all-initial-survival rising from 0.0 to the 0.2 limit, and 0.195 in the full
profile. Any perturbation of the trajectories can push it over. The strict
`latest_satisfaction_mean` miss (< 0.45) is pre-existing.

**Caution for the full profile.** There, regression is a required oracle and
base all-initial-survival is 0.195 against the 0.20 limit. A one-seed-in-40
change could flip it. The full gate was not run in this environment. The owner
of the regression oracle should recalibrate this living-world band before a
full-profile qualification of this branch.

## Tests

`tests/test_fisheries_mutual_aid_promotion.py` (19 tests) covers:

- the tristate switches; new-world defaults; the explicit-off dormant config
  bytes; new-world calibration; resume keeping saved parameters, and an
  explicit switch on resume flipping only `enabled`;
- the live server and gate-runner forwarding;
- collapse/recovery hysteresis, slot removal and disabled-run dormancy;
- round-trip and omitted-while-`None` serialization of the collapse memory;
- the ecology tick returning the event, and the calibration letting a dense
  coast overfish;
- the explicit `--mutual-aid --agents off` rejection, saved aid staying dormant
  in off mode with no state written, the strict aggregate-mode no-op, and the
  convoy text;
- the native hybrid resume boundary.

Suite results:

- `pytest -m "not slow" -n 2`: base (`1244939`) 5330 passed, 3 skipped, 1
  failed. Branch head, with the native extension rebuilt from this tree: 5469
  passed, 3 skipped, 1 failed. The difference includes `cf13f87`'s new tests.
  The only failure on both is the known
  `test_contact_ledger.py::test_save_load_round_trip_continues_identically`
  (`resource_suspensions` keys, pending from `fix/world-extinction`).
- Slow tests in the hazard, fishery and mutual-aid files: 2 passed.
- No Rust changed, so there is no `cargo test` delta.

## Follow-ups

- **Ecology/goods food balance** (owners of that sweep). Hybrid grain regions
  run at 0-11% food sufficiency under crowding and degraded water. Until some
  regions run a surplus, mutual aid stays near-dormant, and famine counts are
  saturated: every region fires every 5-turn cooldown.
- **Regression `civ_survival` band.** Recalibrate for living worlds before the
  next full-profile gate (see above).
- **Fishery recovery dynamics.** Effort does not respond to a falling catch per
  fisher, so collapse is permanent unless the coast loses population. An
  occupation response to fish income, or a per-region scaling of
  `reference_workers` to carrying capacity, would allow boom-bust cycles.
- **Off-mode fishing effort.** `population // 5` never reaches the sustainable
  workforce. If off-mode fisheries should matter, give them their own effort
  proxy.
- **Curator.** A `fishery_collapse → famine` / `migration` causal pattern
  belongs to the causal-provenance work and is not added here.
- **Procedural hybrid worlds die** (about 90% population loss by t300; seed 7
  loses as much with both systems off). This is pre-existing, see above.
