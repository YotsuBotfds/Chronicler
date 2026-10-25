# Wave 8 defaults: agendas, maritime and nomads on

Branch `feat/defaults-wave8`, from `integrate/wave-7` at `bcf14d8` (PR #26:
the persecution fix, healthy-world migration, food logistics, languages,
the viewer systems tabs; merged into `main` as `2a49040` with the same
tree). This branch decides three finished, default-off systems on one full
gate and turns all three on for new worlds:

- great-person agendas ([great-person-agendas.md](great-person-agendas.md));
- maritime ([maritime.md](maritime.md));
- nomads ([nomads.md](nomads.md)).

No oracle, threshold, calibration constant or system parameter changes. The
only code changes are the three `DEFAULT_ENABLED_FOR_NEW_WORLDS` values, the
CLI help, live-server comments, the frozen benchmark pins and tests.

Every gate below is hybrid, `PYTHONHASHSEED=0`, `--parallel 3`; every run
is on Linux with Python 3.13 and a native extension built fresh (`maturin develop --release
--locked`) from the branch's Rust (unchanged from `bcf14d8`; SHA-256
`3d47d60f…b91a51`), with the compiled `chronicler_agents.chronicler_agents`
and its `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
verified. The base runs used a `git archive` export of `bcf14d8` with the
same interpreter and extension.

## 1. Why now, and dependencies

Agendas were held back by their rebellion tail: +176 ± 68 agent rebellions
per run on 60 worlds. The persecution fix (PR #26,
[persecution-fix-2026-10.md](persecution-fix-2026-10.md)) removed left-over
persecution intensity, and the same comparison then read −15 ± 86. Maritime
and nomads had passed their own subset gates but never a full gate with the
switch on. Every other Wave 3-6 system was already on by default.

Agendas read other switches, all on by default for new worlds:

| Agenda part | Reads | Without it |
| --- | --- | --- |
| Action-weight bias | governance (the agenda factors multiply inside the governance bucket and its 1.5x clamp) | no weight effect |
| Ruler weakness for `seize_throne` | governance legitimacy and crisis | stability only |
| `lend_to_crown` | finance | not in the pool |
| `invent_technique` | techniques | `advance_learning` instead |
| `spread_faith` (preaching) | an agent mode | not in the pool |

None is a hard dependency: with `--no-governance` agendas still declare,
act and resolve, but move no action weight and judge rulers by stability
alone. The tests turn governance on because `generate_world` worlds carry
no governance state; CLI, batch and live worlds have it by default.

Maritime reads campaigns (naval campaigns and war records), diplomacy
(naval and blockade grievances) and the techniques' tech focuses.
`navigation_level` still returns 0: `chronicler.techniques` exposes no
`technique_level` (unchanged open item in [maritime.md](maritime.md)).
Nomads read campaigns (hordes ride through the campaign WAR path),
diplomacy (treaties protect from raids; raids leave grievances) and
techniques (raid battle multipliers). All are on by default.

## 2. Subset gates: all three on against all three off

20 seeds x 200 turns per set, on `bcf14d8`, `--no-maritime --no-gp-agendas
--no-nomads` against `--maritime --gp-agendas --nomads`, compared with
`chronicler.validation_compare`. In the subset only community, needs and
cohort are required; the rest is informational.

| Oracle | 42-61 off | 42-61 on | 62-81 off | 62-81 on |
| --- | --- | --- | --- | --- |
| gate | PASS | PASS | PASS | PASS |
| comparator | - | NO REGRESSION | - | NO REGRESSION |
| community (seeds) | 20 | 20 | 20 | 20 |
| needs (seeds; median effect) | 13; 1.00 | 13; 1.00 | 15; 1.41 | 14; 1.21 |
| cohort (seeds; median effect) | 20; 1.09 | 20; 1.36 | 20; 1.18 | 20; 1.18 |
| era (seeds with inflections; silent collapses) | 20; 0 | 20; 0 | 20; 0 | 20; 0 |
| arcs (seeds with three types; families) | 16; 5 | 14; 6 | 15; 5 | 11; 5 |
| artifacts (status; creation per civ per 100 turns; loss) | PASS; 2.10; 2.7% | PASS; 2.45; 3.3% | PARTIAL; 2.36; 1.3% | PARTIAL; 3.05; 1.4% |
| regression (status; failed checks) | PASS (strict); - | PASS (strict); - | FAIL (fail); rebellion_rate_per_agent_turn, civ_survival | FAIL (fail); rebellion_rate_per_agent_turn, civ_survival |
| satisfaction mean; latest (ceiling 0.65) | 0.597; 0.623 | 0.595; 0.615 | 0.599; 0.609 | 0.611; 0.620 |
| migration per agent-turn (floor 0.05) | 0.0600 | 0.0599 | 0.0571 | 0.0549 |
| rebellion per agent-turn (0.02-0.08) | 0.0343 | 0.0350 | 0.0189 | 0.0130 |
| all founders surviving (limit 0.20) | 0.150 | 0.050 | 0.400 | 0.400 |
| extinct worlds | 0 | 0 | 0 | 0 |
| final population min / median / max | 78 / 198 / 279 | 86 / 192.5 / 272 | 130 / 182 / 266 | 143 / 193.5 / 260 |

The off batches reproduce the Wave 7 subset reports of
[healthy-migration.md](healthy-migration.md) exactly (every result, batch
paths normalised): languages and the viewer fields are observational.

What moves, on against off:

- **Rebellion.** Flat on 42-61 (0.0343 to 0.0350). On 62-81, the
  low-rebellion set, 0.0189 to 0.0130; both arms are under the 0.02 floor
  there (informational). Eleven of its 20 worlds have no civ-level
  rebellion in either arm, and four worlds carry the fall (civ-level
  rebellion events 23 to 4, 35 to 10, 23 to 16, 24 to 17): the chance tails
  the persecution fix describes.
- **Migration.** 0.0600 to 0.0599 and 0.0571 to 0.0549; the strict floor is
  0.05.
- **Satisfaction.** Latest 0.623 to 0.615 and 0.609 to 0.620, under the
  0.65 ceiling.
- **Needs.** 13 to 13 and 15 to 14 seeds (12 required).
- **Era.** 20 seeds with inflections and no silent collapse in every batch.
- **Artifacts.** Creation 2.10 to 2.45 and 2.36 to 3.05 per civ per 100
  turns (trading houses and shrines). On 62-81 both arms are PARTIAL on
  loss (1.3% and 1.4% against a 2% minimum), and creation with all on is
  just over the 3.0 band. Informational.
- **Extinction.** 0 of 80 worlds.
- **Founders all surviving.** 0.15 to 0.05 and 0.40 to 0.40
  (informational; the full gate reads it).

Per run (same worlds):

| Per run | 42-61 off (20) | 42-61 on (20) | 62-81 off (20) | 62-81 on (20) |
| --- | ---: | ---: | ---: | ---: |
| population | 192.65 | 192.25 | 181.35 | 197.80 |
| polities alive | 3.05 | 2.85 | 3.05 | 3.10 |
| wars declared | 1.85 | 2.55 | 2.40 | 2.10 |
| war events | 9.15 | 11.00 | 9.75 | 8.80 |
| famine events | 140.55 | 137.25 | 141.90 | 147.05 |
| rebellion (civ events) | 14.60 | 13.90 | 8.50 | 6.45 |
| coups (named) | 6.85 | 6.30 | 7.80 | 7.40 |
| treaties signed | 9.45 | 9.25 | 9.85 | 9.85 |
| artifacts | 16.80 | 19.60 | 18.85 | 24.40 |
| agenda declared | 0.00 | 36.95 | 0.00 | 46.80 |
| agenda fulfilled | 0.00 | 20.55 | 0.00 | 27.40 |
| gp coups seized | 0.00 | 0.10 | 0.00 | 0.10 |
| gp coups crushed | 0.00 | 0.25 | 0.00 | 0.20 |
| fleets commissioned | 0.00 | 0.60 | 0.00 | 0.80 |
| naval battles | 0.00 | 0.00 | 0.00 | 0.75 |
| blockades | 0.00 | 0.00 | 0.00 | 0.20 |
| raids | 0.00 | 0.20 | 0.00 | 1.05 |
| raids repulsed | 0.00 | 0.20 | 0.00 | 0.25 |
| sedentarizations | 0.00 | 0.10 | 0.00 | 0.20 |
| dzuds | 0.00 | 0.35 | 0.00 | 0.50 |

Template worlds have few seas and herders: 7 and 12 of the 20 worlds have a
sea, and 11 and 12 show herd activity. Agendas reach every world.

## 3. Full gate: Wave 8 defaults against Wave 7

Full profile (seeds 42-241, 500 turns) with the three defaults flipped and
no switch passed, compared with the Wave 7 full report (the
healthy-migration full gate of [healthy-migration.md](healthy-migration.md),
the three switches off). `bcf14d8` adds only observational and viewer-only
changes to that tree, and its off subsets reproduce that branch's subset
reports exactly (section 2). 2,432 s on the shared host; the batch was
5.4 GB before its run directories were deleted.

| Oracle | Wave 7 defaults | Wave 8 defaults |
| --- | --- | --- |
| gate | PASS | PASS |
| comparator | NO REGRESSION | NO REGRESSION |
| community (seeds) | 200 | 200 |
| needs (seeds; median effect) | 185; 1.41 | 194; 1.41 |
| cohort (seeds; median effect) | 200; 1.59 | 200; 1.62 |
| era (seeds with inflections; silent collapses) | 200; 0 | 200; 0 |
| arcs (seeds with three types; families) | 164; 6 | 167; 6 |
| artifacts (status; creation per civ per 100 turns; loss) | PASS; 1.29; 3.8% | PASS; 1.49; 4.4% |
| regression (status; failed checks) | PASS (strict); - | PASS (strict); - |
| satisfaction mean; latest (ceiling 0.65) | 0.608; 0.619 | 0.607; 0.619 |
| migration per agent-turn (floor 0.05) | 0.0570 | 0.0576 |
| rebellion per agent-turn (0.02-0.08) | 0.0307 | 0.0317 |
| all founders surviving (limit 0.20) | 0.115 | 0.110 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 46 / 192.5 / 358 | 60 / 200 / 340 |

Era collapses: 4,295 (2,603 marked by the civ's own signals, 1,692 by
crises only), against 4,530 (2,706 / 1,824). The run summaries count 16.3
war events per run against 15.0, and 0 collapses against 0.015.

The gate ran from a copy of the working tree whose code is the branch's
(two module docstrings were re-wrapped afterwards; no other difference).

What the three systems did over the 200 worlds (per run unless marked):

| | Per run |
| --- | ---: |
| Agendas declared (generals / merchants / prophets / scientists) | 54.3 (3.1 / 25.0 / 8.9 / 17.2) |
| Fulfilled / failed | 30.9 / 23.1 |
| Great-person coups (all 200 runs: attempts, seized, crushed) | 85, 31, 54 |
| Bonds formed | 14.6 |
| Trading houses / shrines / crown loans | 3.1 / 3.9 / 0.9 |
| Preaching missions | 3.8 |
| Artifacts | 29.8 |
| Worlds with a sea / with fleets / with naval battles / with blockades | 86 / 83 / 16 / 21 |
| Fleets / naval battles / blockades / overseas campaigns / colonies (all runs) | 188 / 232 / 49 / 49 / 7 |
| Cargo units carried across sea lanes / lost to pirates | 203 / 0.75 |
| Worlds with herders / raids / hordes / tribute / sedentarization | 119 / 66 / 5 / 6 / 23 |
| Raids through / driven off / nomad conquests (all runs) | 108 / 134 / 40 |
| Agent rebellions (116 worlds with any) | 3,162 |

## 4. The flips

One commit per system, so each can be reverted alone:

- `884f28d` maritime, `29e2dce` great-person agendas, `b21c215` nomads:
  `DEFAULT_ENABLED_FOR_NEW_WORLDS = True`; CLI help ("default on for new
  worlds; --no-X opts out; saved on resume"); live-server comments; a
  `test_new_worlds_default_on_and_resume_keeps_saved_setting` per system
  (a fresh world has the system, `--no-X` leaves it out, and on resume an
  off world stays off and an on world stays on); the existing CLI tests'
  off runs pass `--no-X` explicitly.
- `scripts/benchmark_headless.run` pins `maritime=False`,
  `gp_agendas=False` and `nomads=False` next to the earlier pins, so the
  frozen performance oracles replay the same worlds.
- `scripts/m53b_run_validation.py` already forwards `--maritime`,
  `--gp-agendas` and `--nomads` (and their `--no-` forms); unchanged.

Resumed, forked and caller-supplied worlds keep their saved setting
(`fresh_world` in `execute_run`; the live server sets the switches only on
the worlds it creates).

## 5. Identity and resume

Base: the `bcf14d8` export. New: the branch's committed source. Same
interpreter and extension, `PYTHONHASHSEED=0`, `--simulate-only`, compared
with `scripts/diplomacy_identity.py compare` (every output file; the bundle
without `metadata.generated_at`).

| Comparison | Runs | Result |
| --- | --- | --- |
| base (no flags) against branch `--no-maritime --no-gp-agendas --no-nomads` | template seeds 42 and 7, `--agents off` 150 turns and `--agents hybrid` 120 turns; procedural 48 regions x 10 civs, seed 7, off 150 and hybrid 100 | 69 files, **0 differences** |
| base `--maritime --gp-agendas --nomads` against branch (no flags) | template seed 42 hybrid 120; procedural seed 7 off 150 | 25 files, **0 differences** |
| an old save resumed: base save at turn 30 (agents off, no flags), resumed to turn 60 by the base and by the branch, no flags | template seed 42; procedural 48 x 10 seed 13 | 24 files, **0 differences**; the resumed worlds carry none of the three fields |

So the explicit off switches reproduce the base byte for byte, the new
defaults are exactly the gated configuration, and a world saved before the
flip resumes with its saved (off) setting. The unit tests cover the other
direction (an on world stays on when resumed).

## 6. Bundle size and golden fixtures

The bundle-size guard (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, agents off) passes no switch, so its world takes
every default, these three included. It has a sea (one zone) and
agro-pastoral peoples, and agendas run in every world.

| Guard world | Three off | Wave 8 defaults |
| --- | ---: | ---: |
| native | 17.66 MB (18,522,896 bytes) | 20.35 MB (21,337,377 bytes) |
| no-Rust | 18.28 MB (19,172,321 bytes) | 19.72 MB (20,677,190 bytes) |

(MB here is 2^20 bytes, as the test computes it.) The three history fields
take 0.83 MB together (native: maritime 0.37, nomads 0.30, agendas 0.16).
The rest is a different history: natively 14 polities over the run instead
of 11 (5.06 alive per turn against 4.51) and 12% more events. The 24 MB
limit stays; the test comment records the sizes.

`scripts/benchmark_headless.run` pins the three off. With the pins,
`test_performance_equivalence`, `test_governance_dormancy` and
`test_turn_artifact_lifecycle` pass unchanged (94 passed, 1 skipped);
without them 9 fail (`test_corrected_baseline_all_turns_and_rng` for the
single, standard and wide workloads, and
`test_complete_corrected_outputs_with_dormant_governance` for the same
three, governance dormant on and off). No golden fixture changes.

## 7. Verification

Linux, Python 3.13, the fresh native build above, on `ba5ceef` (the flips
plus the pruning-test pin below; later commits change documentation and a
test comment only).

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 3` | 5,967 passed, 3 skipped, 526 subtests (the base collects 5,967 not-slow tests; three default tests added) |
| `pytest -m slow -n 3` | 11 passed, 3 skipped (`TestBundleSize` at 20.35 MB) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, every test) | 5,760 passed, 210 skipped |
| `scripts/run_python_oracle_checks.py` | PASS: 1,951 passed, 12 skipped, 2 deselected in four chunks; guard PASS, no native module loaded, no blocked I/O; 79.7 s, largest chunk 29.4 s of 110 s |
| Golden fixtures | unchanged (section 6) |
| Rust, viewer | unchanged by this branch; `cargo test` and the viewer checks not run |

The first not-slow run, on `b21c215`, failed one test:
`test_snapshot_pruning.py::TestRealRun::test_bundle_is_version_5_and_prunes_the_dead`
follows one history of the bundle-size world (seed 1, 50 turns, agents
off), in which Thornwall Confederacy loses its land at turn 33 and is pruned
from turn 44. With agendas or nomads on (each alone; maritime alone does
not), Thornwall survives those turns and nothing is pruned. `ba5ceef` pins
the three switches off in that test world, as the benchmark workloads do;
its assertions are unchanged.

## 8. Open items

- **Rebellion floor.** The full gate reads 0.0317 agent rebellions per
  agent-turn (Wave 7 0.0307) against the 0.02 floor. On the low-rebellion
  subset 62-81 both arms are under the floor (0.0189 off, 0.0130 on), from
  a handful of worlds; any change of history moves such worlds in or out
  of a persecuted conquest (see the persecution fix).
- **Migration margin.** 0.0576 against the strict 0.05 floor (Wave 7
  0.0570); on subset 62-81 the three lower it 4% (0.0571 to 0.0549).
- **Artifacts.** Creation rises with trading houses and shrines: 1.29 to
  1.49 per civ per 100 turns on the full gate (band 1-3); on subset 62-81
  it reads 3.05, just over the band (informational there).
- **Maritime navigation.** `navigation_level` stays 0 until
  `chronicler.techniques` exposes `technique_level`.
- **Reach.** Template worlds have few seas and herders: 86 of the 200
  full-gate worlds have a sea, hordes form in 5. Procedural worlds show
  more of both ([maritime.md](maritime.md), [nomads.md](nomads.md)).
- Carried over: nomads' off-mode herd food with the native ecology
  runtime ([nomads.md](nomads.md)); agendas' cut parts (artists,
  persecution and toleration).
