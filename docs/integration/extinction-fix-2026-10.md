# World extinction fix, 2026-10

Branch `fix/world-extinction`, based on `837a44f`, with `integrate/ecology-goods`
(`51abfda`) and `integrate/wave-1` (`1282630`, then `01f2502`) merged in before
final tuning and gates, so the fix is tuned on the code that lands on main.
Every simulation change below is a **correction**: it changes behavior on
purpose, and the golden oracles were rolled forward with provenance.

At `837a44f` every default world went extinct. In the subset validation
profile 15 of 20 runs ended with zero living population (regression oracle
`terminal_population_extinction` FAIL). Seed 42 hybrid went from 164 agents to 3.

**Status.**

- Worlds now stay alive: 0 of 20 subset worlds and 0 of 200 full-profile
  worlds die.
- The subset gate passes.
- The full gate passes every required oracle except artifacts (PARTIAL).
  That oracle's calibration assumes the extinction-era turnover; see
  "Notes for later work".

## Root causes

1. **Non-decaying event cascade** (main cause). Every rolled event added its
   `EVENT_CASCADE_RULES` deltas to the world-level `event_probabilities`
   permanently. Within about 100 turns rebellion, migration, border incidents
   and leader death were stuck at 1.0 and plague at about 0.5. Plague then hit
   a random half of the living civs each turn whether or not they had contact
   with anyone. Famine, plague and emigration deaths compounded until the
   population was gone.
2. **Ecology pressure hysteresis.** The pressure multiplier and the
   soil-recovery gate compared population with `effective_capacity`, and
   effective capacity already includes the degraded soil and water. So
   depletion blocked its own recovery. In the first global drought every
   populated region dropped to the soil and water floors and stayed there.
3. **Synchronized twilight absorption.** Because of (2), every small civ fell
   below the "unviable" capacity threshold (`< 10`) in the same few turns.
   Politics step 9 then absorbed all of them in a row (seed 42: every civ but
   one was absorbed between t52 and t57). `vassal_relations` stayed empty for
   the whole game.
4. **Federation join/eject churn** (governance, root-fixed). The Rust
   federation-formation step appended dead civs, and civs that were only
   neutral towards a member. Step 6 then ejected them in the same pass and
   charged both stability penalties. This repeated every turn and drained
   55-90 stability per turn from every federation member. In off mode it alone
   caused a stability and population collapse.
5. **Crowding brake read the wrong population** (hybrid). Rust demographics
   computed fertility crowding from `RegionState.population`. In agent modes,
   `climate.process_migration` clamps that number toward capacity every turn
   (the clamp is pre-existing and left in place), so the brake never saw real
   crowding. With the cascade attrition gone, regions settled at 2-2.7x
   capacity and satisfaction was low.
6. **Occupation oracle under food shortage.** Once extinction was fixed, the
   occupation check (farmer share above 70%) became the blocking regression
   failure. Ecology-goods split farmer labor equally across all occupied slots.
   That left a hungry region's farmers on timber or ore, and the scarcity
   bonus pushed the farmer target to about 0.9.

7. **Fixed plague toll** (found in the first 200-seed, 500-turn run). Once
   (1) to (6) were fixed, 2 of 200 worlds still died by turn 500, and several
   more fell below 60 agents. A plague killed a fixed `int(10 × severity)`
   people per affected civ, whatever the civ's size. That is about 8% of a
   typical civ, but once a world was down to a few dozen agents the
   outbreaks killed people faster than births replaced them. In seed 100 there
   were 23 outbreaks in turns 300 to 349, with 130 deaths.

War is not an extinction driver. On the combined code, wars run about 8 per
200-turn run and about 16 per 500-turn run. War deaths and war-driven
collapses are bounded, and none of the dead worlds above died in a war.
Governance contributes only through (4).

One problem was in the tooling, not the simulation. The full gate's
validation subprocess was OOM-killed (13.8 GB, exit -9) on the 200 living
500-turn bundles, about 18 MB each, so the gate could not write a report. It
now loads data in bounded memory, and its output is byte-identical.

## Mechanics changed

- **Per-civ decaying hazards** (`chronicler/events.py`).
  `λ = λ0_k · f_k(state) + E_k`, with `P = 1 − exp(−λ)`.
  - `event_probabilities` are now constant base rates μ. Old saves load
    unchanged, and μ = 1 is still certain.
  - λ0 = −ln(1−μ) times a per-civ share (environment events 0.5, others 0.25).
  - `f_k` reads real state:
    - drought: climate phase × regional dryness;
    - plague: endemic severity × crowding, with no new outbreak while one is
      running;
    - earthquake: terrain;
    - border incident: shared borders × hostility (×1.5 at war);
    - rebellion and migration: unrest and hardship;
    - religious movement, discovery, renaissance: stability, culture and
      economy.
  - `E_k` (`Civilization.event_excitation`) is a Markov Hawkes excitation.
    It decays with τ = 8 turns and is fed by `EVENT_CASCADE_RULES`, which act
    as α. The branching ratio is about 0.45, so cascades stay subcritical.
  - Plague cross-excites civs in contact (shared border or trade route) and
    self-inhibits (immunity). A border incident also excites its counterparty.
  - The rules that never fired before now do: `tech_advancement`, and the
    named events `coup`, `legacy` and `rival_fall`. Their dead `trade`/`war`
    targets are removed.
  - Hybrid mode: civ-level rebellion and migration are rolled up from the
    agents' own rebel and cross-border-migrant decisions in the previous tick,
    so they are not counted twice. Off, shadow and demographics-only modes keep
    the aggregate drivers.
- **Plague toll.** A plague (rolled or injected) now kills
  `min(10, 10% of the civ's population) × severity`. Civs of 100 or more
  lose exactly what they did before.
- **Leader age.** Leaders now have `Leader.birth_turn`. Successors draw a
  deterministic accession age that depends on succession type; for founders
  and old saves an age is inferred. Death is a Gompertz age hazard (about a
  30-year mean reign) plus war and coup terms. A low-stability coup installs a
  usurper.
- **Ecology.** Pressure and the soil gate are measured against potential
  capacity (`carrying_capacity × capacity_modifier`), in both Python and Rust.
- **Twilight pacing and tributaries** (`politics.prepare_twilight_absorption`).
  - A civ counts as unviable when its capacity stays below 10 for 20
    consecutive turns.
  - At most one civ is eligible per pass, and absorptions are at least 10 turns
    apart world-wide.
  - A declining one-region state first becomes a **tributary** of a stable
    neighbour, using the existing `VassalRelation`. It is annexed only after
    30 turns.
  - The gate reaches Rust as an optional `absorption_eligible` column. A
    missing column means eligible, so old callers behave as before.
- **Federations.** Dead civs never join. A civ joins only when the dissolution
  check would not eject it straight away (Rust and the Python oracle).
- **Crowding.** The demographics tick uses the live agent count. Births taper
  from 1.0x capacity and stop at 1.6x.
- **Food-first labor** (separate commit). When the equal split would not cover
  food demand, farmers move to the food slots. Each non-food slot keeps at
  least 25% of its equal share. The farmer target is capped at 0.66.
- **Validation memory** (`validation_io`). This changes no simulation
  behavior:
  - bundles are parsed one at a time;
  - each seed run keeps only the bundle fields the oracles read;
  - null-free numeric arrow columns are packed into `array`;
  - agent events keep only the codes an oracle counts.
  On 20 full-profile seeds the report is byte-identical to the old loader,
  and peak memory falls from 3.0 GB to 0.68 GB. The 200-seed batch validates
  at a 4.4 GB peak.

Determinism: all new draws use namespaced `stable_hash_int` streams
(`env_hazard`, `event_hazard`, `leader_mortality`, `leader_accession_age`).
Stat changes go through the accumulator with the existing categories. Civs
and regions are identified by index.

## Tests changed and why

New tests:

- `tests/test_event_hazards.py`:
  - hazard limits, exponential decay and expiry, excitation that raises and
    then relaxes a hazard;
  - subcritical branching, contact-only plague spread, border-incident
    counterparty, the formerly dead cascade sources, hybrid roll-up;
  - leader accession ages, `birth_turn` for old saves, Gompertz rise with
    age, plausible mean reign, war/coup terms, coup installs a usurper;
  - absorption persistence and spacing, the tributary step, federation
    admission;
  - the plague toll cap;
  - same-seed determinism in off and hybrid (`execute_run` digests);
  - slow multi-seed survival (6 seeds × 200 turns, off and hybrid).
- `tests/test_validate.py`: the narrowed seed-run bundle, the agent-event
  filter (it keeps "has events"), and lossless column packing.
- `tests/test_food_first_labor.py`: the food-first split and its invariants.
- Rust:
  - `test_federation_append_skips_dead_civ_like_python_oracle` replaces the
    test that pinned the pre-H-8 dead-civ append;
  - `test_federation_does_not_append_member_it_would_eject`;
  - `test_twilight_absorption_respects_python_pacing_gate`;
  - `test_depleted_soil_recovers_when_population_is_below_potential`;
  - `test_population_pressure_for_uses_explicit_head_count`;
  - two `food_first_labor` tests;
  - `test_target_occupation_ratio_farmer_share_is_capped`.

Changed tests. Each one pinned a behavior that is now corrected:

- Rust `test_pressure_multiplier_basic` and `test_basic_plains_tick` pinned
  pressure against degraded effective capacity (0.375). Against potential
  capacity it is 0.5, so soil goes to 0.825 and water to 0.615.
  `tests/legacy_ecology_oracle.py` mirrors the same formula so that
  `test_ecology_parity` still compares like with like.
- Two demographics crowding tests are moved to the new 1.0/1.6 band.
- `tests/test_fishery_experiment.py` (two tests) and the expected harvest in
  `scripts/economy_coupling_experiment.py` pinned the equal labor split under
  food shortage. They now compute the food-first allocation.
- Exact-trajectory oracles:
  - New `corrected_extinction_2026_10.json` and
    `corrected_artifacts_extinction_2026_10.json`, captured with the tests'
    own loops. Provenance: correction `EXT-2026-10`, which changes every
    workload from turn index 0, because the new fields are in the turn-0
    snapshot.
  - The backlog and 423a67c fixtures stay frozen. The scoped-difference test
    now checks each link of the chain against that link's own provenance.
  - The edf7299 historical check reads the frozen backlog file.
- T1-3: no golden workload has a tech regression any more, so reverting T1-3
  changes nothing. The revert proof is replaced by a direct off-mode test
  that the era bonus is removed at once (`acc=None`).
- `test_exact_baseline_two_turns_events_narration_state_and_rng` grafts the
  corrected `phase_environment`, `phase_random_events` and cascade ingest
  onto the A01 baseline. It still isolates the coordinator refactor.
- `test_real_pending_stockpile_boundary_rejects_api_and_cli`: the seed-42
  pending-bootstrap boundary moved from split 12 to 14.
- `test_multiturn_native_stress_cargo_reserve_funding_and_recovery`: the
  Mine now has a one-turn shortfall blip before its fresh three-turn stress.
  The restart is located as the first 1,2,3 run. Reset and reactivation are
  unchanged.

Suite results:

- `pytest -m "not slow" -n 2`: 5266 passed, 3 skipped.
- Slow `test_event_hazards`: 2 passed.
- `cargo test`: 863 passed, 0 failed.

## Gate results

Both gates ran on the final code. Run output is kept outside the repository.

### Subset (20 seeds × 200 turns, hybrid)

**PASS** (as at baseline). `validation_compare` against the `837a44f`
subset report says **NO REGRESSION**.

| Oracle | 837a44f | Final | Why it changed |
| --- | --- | --- | --- |
| regression | FAIL `terminal_population_extinction` | PASS, calibrated floor | 0 of 20 worlds extinct (was 15). Satisfaction 0.409→0.471, latest 0.420→0.434 (the only strict miss, < 0.45), migration 0.0494→0.0525, occupation violations 0.32%→0.12%, all-initial-survival 0.0→0.2 (limit 0.2), Gini in range 0.86→1.0 |
| arcs | PASS | FAIL (informational) | `cinderella` 41.3% > 40%. Living civs dip and recover, where they used to decline to death (`icarus`/`riches_to_rags`/`oedipus`). Passes at 500 turns. |
| artifacts | PARTIAL | PARTIAL | Loss/destruction 8.2%→0.4%: no extinction turnover (see notes). Creation 1.76→2.92 per civ per 100 turns, diversity OK |
| era | PASS | PASS | Silent-collapse seeds 0→0 |
| needs / cohort / community | PASS | PASS | Expected-sign seeds 16→18, cohort effect size 1.02→1.23, 20 of 20 qualifying |
| determinism | SKIP | SKIP | No duplicate seeds in the profile |

Outcomes (837a44f → final):

| Measure | 837a44f | Final |
| --- | --- | --- |
| Worlds with zero living population at turn 200 | 15 of 20 | 0 of 20 |
| Final living population per world | 0 to 96 | 275 to 548 |
| Polities alive at the end (mean) | 2.65 | 2.9 |
| Minimum alive at any time | 1 in every run | 2 to 4 |
| Population, t1 / 51 / 101 / 151 / 200 | 207 / 333 / 256 / 132 / 14 | 208 / 349 / 364 / 370 / 409 |

Events per run (837a44f → final):

| Event | 837a44f | Final |
| --- | --- | --- |
| plague | 51 | 15.5 |
| rebellion | 34.6 | 26.7 |
| leader death | 25.4 | 26.5 |
| twilight absorption | 4.1 | 0.7 |
| secession | 2.0 | 0.0 |
| restoration | 1.1 | 0.3 |
| war | 2.6 | 7.7 |
| border incident | 35 | 47.6 |
| coup | 4.8 | 6.6 |
| federations formed / collapsed | 5.9 / 5.5 | 1.2 / 0.1 |
| famine | 150 | 286 |

Famine counts region-turns with food sufficiency below 1. More regions are
alive and populated now, so the count is higher.

### Full (200 seeds × 500 turns, hybrid, `--parallel 3`)

**FAIL, on one required oracle: artifacts (PARTIAL).** No full-profile
baseline exists. Compared against the subset baseline's oracle set,
`validation_compare` reports **NO REGRESSION** and lists regression as a
resolved required failure.

| Oracle | Result |
| --- | --- |
| regression | PASS, calibrated floor. 0 of 200 worlds extinct; final population 181 / 447 / 590 (min / median / max). Satisfaction 0.483, latest 0.492. Migration 0.0481 is the only strict miss (< 0.05). Occupation violations 0.11%. All-initial-survival 0.195 (limit 0.20). Gini in range 94%. |
| arcs | PASS. `cinderella` 38%, 6 families. |
| era / needs / cohort / community | PASS. 200 of 200 seeds with inflections, 1 silent collapse; expected sign in 199; cohort effect 1.67; 200 qualifying. |
| artifacts | PARTIAL. Creation 2.35 (OK). Diversity fails: treatise 70%. Loss/destruction 2.1%, against the 10-30% band. |

Full-profile outcomes: 0 extinct worlds. Polities alive at the end: 9 worlds
with 1, 56 with 2, 89 with 3, 45 with 4 and 1 with 5 (mean 2.87). Mean
population by turn 1 / 126 / 251 / 376 / 500 is 203 / 382 / 392 / 416 / 433.

Per 500-turn run: war 15.6, plague 41.6, leader death 68, coup 15.2,
twilight absorption 0.9, secession 0.1.

The first full run was taken before the plague cap. Its validator was
OOM-killed. Re-validated with the bounded loader, it had regression FAIL
(seeds 100 and 127 extinct), which is what led to correction (7).

## Notes for later work

- `climate.process_migration` still clamps `RegionState.population` in agent
  modes. Rust crowding no longer depends on it, but the clamp still hides
  overshoot from the Python ecology.
Several calibrations were tuned on worlds that died. The M53 baseline
(`tuning/m53_baseline.yaml`) records agent extinction at turn 77 on average,
and the May 2026 artifact rebalance passed the full gate on those runs. In
500-turn worlds that stay alive these calibrations misfire. None of them is
changed here, because each one needs its owner's decision:

- **Artifact loss band (10-30%).** The band was met through turnover from
  extinction. In the baseline subset, 16 of the 23 losses were capture losses
  during 82 absorptions.
  - Now about 13% of artifacts are ever touched by a fall: captured, claimed,
    destroyed or lost. Even a 100% capture-loss chance could not reach 10%.
  - Two things were tried and reverted, because they move the rate by less
    than a point: exposing a capital's portable artifacts when campaigns
    occupy it (M60b bypasses the M52 capital-capture rule), and one scientist
    per prosperity streak.
- **Treatise dominance (full profile).** The aggregate scientist trigger
  ("sustained high economy") is level-triggered. Civ economy sits at its
  100 cap in 62% of civ-turns, so a scientist appears every 20-turn
  cooldown, and treatises reach 70% of artifacts in the full profile. One
  scientist per streak gives 52% (20-seed sample).
- **Arc shapes.** Prestige decays by a flat 1 per turn and grows without
  bound: the mean goes from 0 to 525 by turn 500. Arc composites therefore
  end on an upswing, and `cinderella` sits near the 40% dominance limit
  (subset 41%, full 38%).
- **Secession.** Secession now fires 0 to 0.1 times per 500-turn run. M47d
  planned to raise the threshold below 1 per run. Threshold 20 gives 1.6 per
  run and 3.55 polities at the end, but 2 of 20 worlds nearly died. Small
  fragmented polities starve under the chronic ecology-goods food shortage:
  grain regions run at 5-30% food sufficiency for most of a run, and famine
  fires about 1.4 times per turn. The threshold is left at 10 until the
  ecology-goods balance sweep.
- **Tributaries.** No tributary (`vassalization`) fired in either gate. The
  step needs a neighbour with stability above 40, and that is now rare. The
  ladder only handles one-region decliners. Multi-region federations and
  vassal chains are left to the politics owners.
- `docs/integration/deferred-backlog-2026-10.md` refers to the T1-3 revert
  proof. That proof is now a direct routing test, because no golden workload
  regresses any more.
