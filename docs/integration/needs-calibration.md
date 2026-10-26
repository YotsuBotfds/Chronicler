# Needs calibration (2026-10)

> Follow-ups in [`needs-followups.md`](needs-followups.md): needs oracle
> method 3 (a binding component that reads the terms, required in the full
> profile), newborns start from the birth parent's needs, and a move no
> longer blocks autonomy restoration. The open items of §4 and §10 on these
> three point there.

Branch `fix/needs-calibration` from `origin/main` `48b72be`, merged with
`feat/hunger-mortality` (PR #32), `fix/needs-oracle-power` (PR #33) and
`feat/farmland-climate` (PR #34) through `main` `ea08126`, without rebase.
A correction of the agents' needs in every agent mode; no switch.
`--agents off` output and the golden fixtures do not change
([Identity](#7-identity-and-golden-fixtures)).

Every run is Linux, Python 3.13, `PYTHONHASHSEED=0`, hybrid unless stated,
with a native extension built fresh (`maturin develop --release --locked`)
and its compiled `AgentSimulator`, `EcologySimulator` and
`PoliticsSimulator` verified. "Base" is `main` `ea08126` with its own
extension (SHA-256 `21344bb6...0502ef`); the head extension is
`0cb2948c...7cdb8d`, built from `3a9b945` (later commits change tests and
documents only). Template worlds are the default 8 regions and 4 civs,
procedural ones 64 regions and 16 civs. A turn is a year for agent ages.

**Result.** Under their bad conditions the four inert needs now bind:
safety in 25% of agent-turns in war zones, conquered and raided regions;
material in 44% of famine agent-turns (72% for the poorest third); social
in 26% without a co-resident bond; autonomy in 37% under persecution,
conquest or martial law. In good conditions 0.8-2.9% bind (autonomy 5.7%).
Before, 0-0.2% bound anywhere. A social deficit now pushes migration
instead of staying. Full gate PASS strict, NO REGRESSION (migration
0.0626, rebellion 0.0385, latest satisfaction 0.622, needs 190 of 200, 0
extinct). Zeroing the terms does not fail the needs oracle on any of three
subsets (one of three before the farmland merge): that target is not met
([§4](#4-the-needs-oracle-and-the-rust-terms)).

## 1. Why the needs were inert

A read-only probe (kept outside the repository) recorded every turn of 15
worlds (template 42-51 and procedural 7-11, 200 turns) each living agent's
six needs, with the region batch and civ signals its tick saw, its bonds
and its decisions. Per need and condition it gives the share below the
behavioural threshold and the empirical restoration rate
`R = (delta + decay) / (1 - need)` on unclamped steps. One update is
`s -> (s - D) + R (1 - s + D) - P` (decay `D`, condition pressure `P`), so a
need settles at `1 + D - (D + P) / R`, approached at a rate of about `R` a
turn.

Base, all 15 worlds (1.21 M agent-turns):

| Need | Threshold | Below | Mean | p10 / p50 / p90 |
| --- | ---: | ---: | ---: | --- |
| safety | 0.30 | 0.02% | 0.56 | 0.47 / 0.57 / 0.68 |
| material | 0.30 | 0.01% | 0.59 | 0.47 / 0.57 / 0.72 |
| social | 0.25 | 0.05% | 0.43 | 0.38 / 0.42 / 0.47 |
| spiritual | 0.30 | 9.9% | 0.45 | 0.33 / 0.47 / 0.57 |
| autonomy | 0.25 | 0.02% | 0.66 | 0.53 / 0.62 / 0.88 |
| purpose | 0.35 | 11.4% | 0.40 | 0.33 / 0.42 / 0.47 |

By condition (base, all worlds):

| Need, condition | Share of agent-turns | R | Fixed point | Below |
| --- | ---: | ---: | ---: | ---: |
| safety, civ at peace | 80% | 0.039 | 0.68 | 0.01% |
| safety, civ at war, region uncontested | 16% | 0.018 | 0.27 | 0.07% |
| safety, war zone (armies, battles, occupation) | 4.1% | 0.024 | 0.47 | 0.05% |
| material, fed | 63% | 0.037 | 0.74 | 0% |
| material, famine (below 0.6 for a season) | 8.2% | 0.017 | 0.43 | 0.07% |
| material, famine, poorest third | 2.8% | 0.009 | 0 | 0.16% |
| social, 2+ co-resident bonds | 78% | 0.012 | 0.34 | 0.03% |
| social, no co-resident bond | 7.7% | 0.008 | 0 | 0.11% |
| autonomy, self-ruled | 37% | 0.053 | 0.86 | 0% |
| autonomy, persecuted (own faith targeted) | 7.3% | 0.057 | 0.87 | 0.03% |

1. **Bad conditions kept restoration at or above decay.** In famine
   material settled at 0.43, in a war zone safety at 0.47, both above
   their 0.30 thresholds. Only the poorest in famine, a civ at war and
   isolation had fixed points at or under a threshold.
2. **Slow dynamics, short spells.** At rates of 0.01-0.04 a need takes
   25-100 turns to approach its fixed point, and decay of 0.008-0.013 a
   turn needs 25 or more turns to carry it from 0.55 to 0.30 even with no
   restoration. Seven in ten famine agent-turns fall in a famine's first
   five turns, and only 4% of agent-turns without a co-resident bond come
   after the tenth such turn. After 21 or more turns of famine 1.1% were
   below the threshold, after 21 turns of isolation 2.6%.
3. **Needs read as age.** Every agent spawned at 0.5 and moved slowly, so
   the social need sat between 0.38 and 0.47 for everyone; bonded or
   isolated, its mean was 0.43-0.44.
4. **Social counted bonds anywhere.** The bond factor counted positive
   bonds wherever the other person lived, until their sentiment faded (1 a
   turn from 25-127), so a migrant who left everyone behind kept its social
   restoration for decades.
5. **Persecution was region-wide, and rebellion paid.** "No persecution"
   restoration stopped for everyone in a persecuting region, the ruler's
   faithful included, while the persecuted kept self-rule restoration. A
   rebellion adds 0.10 autonomy and the persecuted rebelled in about 16%
   of their agent-turns, so their autonomy (mean 0.72) was the highest of
   any group.
6. **Not clamps, and not thresholds alone.** No need sat at 0 or 1.
   Raising thresholds alone would bind agents in good conditions about as
   often as in bad, since the distributions barely differ by condition.

Spiritual (minority faith without a temple: 22% below) and purpose
(non-farmers 20-28% below) did bind; both are unchanged
([Open](#10-open)).

## 2. Design

Decay and restoration were raised together so that a need follows its
conditions within about 5-15 turns, with the fed, peaceful fixed points
where they were (0.62-0.75). Bad conditions now add pressure (`P`) or cut
restoration enough to put their fixed points under the threshold. Fixed
points below are for an agent of neutral boldness, rural, fed at
sufficiency 1.

**Safety** (decay 0.013 -> 0.040, threshold 0.30). Restoration: civ at
peace 0.025, region not contested 0.032 (new), health 0.028 x (1 -
endemic), food 0.022 x sufficiency above 0.8; times boldness and urban
factors as before. Pressure: a war zone, a contested region whose ruler or
whose agent's civ is at war, 0.05. Shocks: a conquest of the region -0.15,
a successful raid -0.20 (new one-turn signal). Epidemic deaths act through
the health term only: catastrophe deaths are mostly epidemics (5.8% of
region-turns), and a death shock bound a quarter of agents in those turns.

| Condition | Fixed point |
| --- | ---: |
| at peace, uncontested | 0.67 |
| civ at war, region uncontested (hungry) | 0.55 (0.37) |
| armies in a region at peace | 0.51 |
| war zone | 0 (below 0.30 after about 6 turns) |

**Material** (decay 0.010 -> 0.060, threshold 0.30). Restoration: food
0.115 x sufficiency (up to 1.5), wealth (0.044 + 0.15 x shortfall) x the
civ wealth percentile, so the wealthy buy food in a dearth. Pressure: the
hunger mortality bands (`demographics::hunger_components`), dearth 0.039
and famine 0.018.

| Poorest / median / richest tenth | Fixed point |
| --- | --- |
| fed | 0.56 / 0.62 / 0.67 |
| dearth, sufficiency 0.8 | 0.26 / 0.44 / 0.56 |
| famine, 0.4 for a season | 0 / 0.13 / 0.43 |

In such a famine the poor go below 0.30 within 4 turns, the median within
9; the richest stay above.

**Social** (decay 0.008 -> 0.030, threshold 0.25 -> 0.35). Restoration:
0.054 for one or more positive bonds (positive sentiment) with living
people in the agent's region, plus the community proxy 0.019 x population
ratio x occupation x age as before. The 0.3/0.7 blend and bonds anywhere
are gone. One co-resident bond or more: 0.62 (0.53 for a child); none: 0,
below 0.35 about 14 turns after the last bond leaves or dies.

**Autonomy** (decay 0.008 -> 0.025, threshold 0.25 -> 0.35). Restoration
unless displaced (the five turns after a move, as before): self-rule
0.031, not persecuted 0.060, where "persecuted" is now the agent's own
faith being the target (`RegionState::persecutes`), not any persecution in
the region. Pressure: persecution 0.02 x intensity; harsh rule 0.03 (new
`harsh_rule` column: the controller has enacted martial law); a remembered
conquest by another civ 0.06 x the strongest such conquest memory
(`|intensity| / 127`, half-life 30; the conqueror's own people and those
who have since joined it are not pressed). A conquest caps the conquered's
autonomy at 0.20 that turn.

| Condition | Fixed point |
| --- | ---: |
| self-ruled, not persecuted | 0.75 |
| foreign rule (after a displaced spell) | 0.61 (0.48) |
| persecuted under its own civ, intensity 0.2 / 0.5 | 0.09 / 0 |
| martial law, self-ruled / foreign | 0.42 / 0.11 |
| fresh conquest by another civ | 0.06, above 0.35 after about 50 turns |

The conquered leave the bound by rebelling (+0.10 each time) or by changing
allegiance, after which the memory no longer counts.

**Thresholds.** Safety and material stay at 0.30. Social and autonomy rise
to 0.35: with the faster dynamics the fixed points under good conditions
(0.62 and 0.75, foreign rule 0.61) are far from it, so the higher threshold
binds isolation and oppression sooner without binding the fed and free.
`narrative._NEED_THRESHOLDS` follows.

### Targets and measured shares

Targets: in good conditions at most about 3% of agent-turns below the
threshold; in bad conditions 20-50%, rising with a spell's length and
severity. Below a threshold the decision gains a positive utility, and at
the decision temperature (0.3) against the stay utility (0.58) any
positive utility opens a hazard of about 12.6% a turn. Binding the fed and
free would move agents with no reason to move and spend the migration
(at most 0.08) and rebellion (0.02-0.08) bands; binding everyone in a bad
spell from its first turn would turn every famine and war into a mass
exit and leave the oracle no contrast within a condition.

Probe, all 15 worlds, before (base) and after (head). Shares of
agent-turns are the head's.

| Need | Condition | Share | Below before | Below after |
| --- | --- | ---: | ---: | ---: |
| safety | civ at peace | 80% | 0.01% | 0.5% |
| safety | civ at war, region uncontested | 16% | 0.07% | 4.8% |
| safety | contested region, ruler or civ at war | 2.7% | 0.07% | 32% |
| safety | region conquered in the last 10 turns | 0.7% | 0% | 25% |
| safety | region raided in the last 10 turns | 0.7% | n/a | 25% |
| material | fed (poorest / richest third) | 64% | 0% (0% / 0%) | 0.8% (1.6% / 0.1%) |
| material | dearth (poorest / richest third) | 28% | 0.01% (0.02% / 0%) | 9.5% (20% / 0.9%) |
| material | famine (poorest / middle / richest third) | 7.6% | 0.07% (0.16% / 0.04% / 0%) | 44% (72% / 52% / 9.9%) |
| social | 2+ co-resident bonds | 77% | 0.03% | 2.3% |
| social | one co-resident bond | 15% | 0.08% | 8.6% |
| social | no co-resident bond | 8.0% | 0.11% | 26% |
| autonomy | self-ruled | 35% | 0% | 2.6% |
| autonomy | foreign rule, settled / displaced | 41% / 19% | 0.04% / 0.03% | 6.5% / 17% |
| autonomy | own faith persecuted | 9.5% | 0.03% | 37% |
| autonomy | conquered by another civ in the last 10 turns | 0.3% | 0% | 40% |
| autonomy | martial law | 0.4% | 0% | 35% |
| spiritual | all (unchanged) | 100% | 9.9% | 7.9% |
| purpose | all (unchanged) | 100% | 11.4% | 11.6% |

Pooled good / bad conditions: safety 1.0% / 25%, material (fed / famine)
0.8% / 44%, social 2.9% / 15% (bad includes one bond after a recent
loss), autonomy 5.7% / 37%. Autonomy misses the 3% target in good
conditions: displacement blocks restoration for five turns after every
move (a quarter of agent-turns), and the displaced, 14% below, make up
most of the good-condition share. Spiritual and purpose dynamics are
unchanged; their shifts come from where agents now live and work.

## 3. Behaviour terms and the social sign

| Need | Below threshold pushes | Weight; most at need 0 |
| --- | --- | --- |
| safety | migrate +, stay - | 0.7; 0.21 |
| material | migrate +; switch + (not farmers) | 0.5; 0.15 |
| social | migrate + (was stay +, migrate -) | 0.5; 0.175 |
| spiritual | migrate + | 0.4; 0.12 |
| autonomy | rebel +; loyalty drift x (1 + 0.6 deficit) | 0.45; 0.16 |
| purpose | switch + | 0.4; 0.14 |

Each channel stays capped at `NEEDS_MODIFIER_CAP` 0.30; the terms enter the
decision where they did, after memory modifiers and before the gates. No
other migration weight changed, and the healthy-migration drivers are
untouched.

**Social sign.** The old term made a social deficit favour staying. Its
design note ("resist leaving populated areas", "deeply rooted agents resist
leaving") describes high social need, but the term fires on low social
need: it anchored the isolated. The data agree with the literature that
isolated people move and bonded people stay (location-specific social
capital: DaVanzo 1981; Kan 2007; chain migration: MacDonald and MacDonald
1964): at base, agents with no co-resident bond migrated at 10.6% a turn
against 5.6% for those with two or more, and agents below the social
threshold at 6.5% against 6.4%; the needs oracle's social pairing read
-0.30 on the three subsets and -0.20 at 500 turns. The model already holds
the bonded through the migration drivers' roots (`ROOTS_PER_HOME_BOND`)
and pulls them toward emigrated kin (chain). So a social deficit now
pushes migration (weight 0.5, its own `social_need` term in the migration
budget, appended as driver code 18 so saved codes 0-17 keep their
meaning), and the stay bonus is gone.

**Material and farmers.** With material binding in famine, its push to
change work drove starving farmers out of farming (fewer harvests, and
farmers bear more children: `FERTILITY_BASE_FARMER` 0.060 against 0.042).
Procedural worlds lost 12% of their agent-turns. The push now skips
farmers; others are pushed to other work, in a shortage mostly the fields.

**Direction and bounds.** Unit tests in `needs.rs` and `tests/test_needs.rs`
fix each push's sign, the farmer exclusion, the social push replacing the
stay bonus, and the cap. In the probe the behaviour each term drives is
more frequent below the threshold than above it (events per agent-turn,
head, all 15 worlds):

| Need -> behaviour | Below | Above |
| --- | ---: | ---: |
| safety -> migrate | 7.5% | 6.6% |
| material -> migrate | 9.7% | 6.4% |
| material -> switch | 5.9% | 4.2% |
| social -> migrate | 7.6% | 6.6% |
| spiritual -> migrate | 7.7% | 6.5% |
| autonomy -> rebel | 9.4% | 3.6% |
| purpose -> switch | 7.8% | 3.8% |

These are associations. Within a bad condition two reverse: without a
co-resident bond, agents below the social threshold migrate at 7.6%
against 12.6% above it (those above are mostly recent arrivals, who move
again often), and persecuted agents rebel at 15% below against 20% above
(a rebellion adds 0.10 autonomy). The matched pairs in §4 compare like
with like. Migration and rebellion stay inside their bands ([Gates](#5-gates)).

## 4. The needs oracle and the Rust terms

The check builds the head with every need-driven term zeroed
(`compute_need_utility_modifiers` returns zeros and the autonomy deficit
no longer speeds loyalty drift). Needs still evolve and nothing reads
them; the world differs from the head's only through behaviour. The
target was that this build fails the needs oracle (method 2) on most
subsets. **It is not met.**

Net concordance (seed-clustered lower bound), seeds with C > D of 20
(12 required):

| Subset, 20 seeds x 200 turns | Base | Head, terms on | Head, terms off |
| --- | --- | --- | --- |
| 42-61 | +0.225 (0.167), 18 | +0.228 (0.170), 18 | +0.123 (0.047), 14 |
| 62-81 | +0.158 (0.073), 14 | +0.155 (0.097), 14 | +0.184 (0.096), 15 |
| 82-101 | +0.152 (0.076), 15 | +0.234 (0.160), 17 | +0.155 (0.075), 15 |
| oracle | PASS 3/3 | PASS 3/3 | PASS 3/3 (target: FAIL on most) |

Before the farmland merge (`main` `82c131b`, same head constants) terms
off failed one of three (+0.095 / +0.019 / +0.088, terms on +0.152 /
+0.250 / +0.239).

By pairing, pooled over the three subsets ((C - D) / (C + D)):

| Pairing | Base | On | Off | On, lower agent below threshold | Off, same |
| --- | ---: | ---: | ---: | ---: | ---: |
| autonomy -> rebellion | +0.25 | +0.56 | +0.13 | +0.65 (68) | +0.08 (37) |
| social -> migration | -0.30 | +0.15 | +0.11 | +0.31 (104) | +0.05 (124) |
| purpose -> switch | -0.05 | +0.07 | -0.03 | +0.20 (65) | +0.19 (52) |
| material -> migration | +0.22 | +0.18 | +0.15 | +0.20 (368) | +0.09 (385) |
| safety -> migration | +0.25 | +0.16 | +0.25 | +0.22 (18) | -0.22 (23) |
| all | +0.18 | +0.21 | +0.15 | +0.27 (623) | +0.08 (621) |

Informative pairs in brackets. Why zeroing the terms barely moves the
oracle:

1. **The needs now track conditions that drive the same behaviour by
   other routes.** Famine, battle, conquest and persecution memories push
   migration, as do low satisfaction, food elsewhere and persecution
   itself; persecution also raises the rebel utility. A terms-off build's
   needs fall in famine and war as the head's do, and its agents still
   leave, so the pairs read the conditions: terms-off material and safety
   (+0.15, +0.25) are near base (+0.22, +0.25).
2. **Most pairs sit where the terms do nothing.** In 72% of informative
   pairs, on and off, the lower agent is above its threshold. There the
   residual channels decide: the 0.5 start of newborns (needs carry age),
   recent migrants, who move again and whose needs have not settled, and
   wealth.
3. **The terms are gate-limited.** Below the threshold any positive
   utility opens a hazard of about 12.6% a turn; a deficit adds at most
   0.12-0.21 to one channel.

Restricted to pairs whose lower agent is below its threshold, terms on
read +0.27 against +0.08 off, with autonomy, social and material each
higher on. Safety's 18-23 such pairs are too few to read; its all-pairs
difference (-0.09) is within about 1.3 standard errors.

Variants that removed the age channel (newborns at their conditions'
fixed points, terms for adults only, household wealth percentiles) made
terms off fail all three subsets (+0.005 / -0.071 / -0.032) but also
terms on fail two of three (+0.053 / +0.107 / +0.071, lower bounds
-0.024 / +0.028 / -0.025), losing the strict PASS; they were reverted.
Inheriting the parents' needs at birth raised the residual further and
cost population and the arcs oracle; reverted.

## 5. Gates

Guard rails: no extinct world, migration 0.052-0.08 (strict floor
0.05), rebellion 0.02-0.08, latest satisfaction at most 0.65, needs
method 2 strict PASS, era, cohort, community, artifacts and arcs PASS.

**Full gate** (200 seeds x 500 turns, `--parallel 3`), head `3a9b945`
against the farmland full report (PR #34's head `953aa9e`, the tree of
`main` `ea08126`):

| | Base | Head |
| --- | --- | --- |
| gate; compare | PASS strict | PASS strict; NO REGRESSION |
| needs net (lower bound), seeds with C > D | +0.194 (0.178), 182 of 200 | +0.209 (0.195), 190 of 200 |
| autonomy / social / purpose / material / safety | +0.12 / -0.20 / +0.04 / +0.22 / +0.25 | +0.62 / +0.19 / +0.02 / +0.17 / +0.18 |
| era, cohort, community, artifacts, arcs | PASS | PASS |
| migration per agent-turn | 0.0610 | 0.0626 |
| rebellion per agent-turn | 0.0308 | 0.0385 |
| satisfaction mean; latest | 0.617; 0.630 | 0.614; 0.622 |
| extinct worlds; silent collapses | 0; 1 | 0; 1 |
| final population min / median / max | 46 / 179 / 325 | 46 / 177 / 277 |

**Subsets** (20 seeds x 200 turns, `--parallel 1`), head against base;
arcs, artifacts and regression are informational in a subset:

| Seeds | Arm | Gate; compare | Needs net (lb), seeds | Migration | Rebellion | Latest sat. | Extinct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 42-61 | base | PASS | +0.225 (0.167), 18 | 0.0659 | 0.0364 | 0.618 | 0 |
| 42-61 | head | PASS; NO REGRESSION | +0.228 (0.170), 18 | 0.0705 | 0.0521 | 0.614 | 0 |
| 62-81 | base | PASS | +0.158 (0.073), 14 | 0.0596 | 0.0178 | 0.621 | 0 |
| 62-81 | head | PASS; NO REGRESSION | +0.155 (0.097), 14 | 0.0614 | 0.0229 | 0.619 | 0 |
| 82-101 | base | PASS | +0.152 (0.076), 15 | 0.0648 | 0.0331 | 0.619 | 0 |
| 82-101 | head | PASS; NO REGRESSION | +0.234 (0.160), 17 | 0.0640 | 0.0427 | 0.614 | 0 |

Informational: the head's artifacts read PARTIAL on 62-81 (base PASS; the
terms-off build PARTIAL too). Regression's civ-survival check (all
founders alive in at most 20% of worlds, set for 500 turns) fails at 200
turns on 62-81 for base, head and terms off (0.55 / 0.50 / 0.55) and on
82-101 for the head (0.30 against 0.20); base 62-81 also reads rebellion
0.0178, under 0.02. Both pass at 500 turns.

## 6. Bridge signals

- `harsh_rule` (region batch, f32 0-1): 1 when the region's controller has
  `martial_law` among its governance institutions, recomputed every batch;
  absent (older callers) reads 0.
- `raided_this_turn` (region batch, bool): set by a successful nomad raid
  on the region (`Region._raided_this_turn`), read and cleared by
  `build_region_batch`; absent reads false.
- `social_need` migration driver (code 18), with its mass-migration text.
  The viewer shows it through its generic fallback ("social need").
- Tests: `tests/test_needs_calibration.py` (harsh rule follows the
  controller and clears on repeal; the raid signal is read once; the driver
  appended; native: harsh rule presses autonomy only while it lasts).

## 7. Identity and golden fixtures

`--agents off`, 200 turns, base and head each with its own extension
(`scripts/agent_movements_identity.py compare`): template seed 42, 9
files, and procedural seed 7 (64 regions, 16 civs), 21 files, 0
differences. The golden fixtures (`tests/test_performance_equivalence.py`,
68 tests) pass unchanged; no `ORACLE_CHAIN` link was needed. The bundle
guard world writes 21.55 MB native and 22.67 MB no-Rust, as on base.

## 8. Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 20 warm-up and 8 measured
turns, two repeats, one job at a time, on a shared 4-core machine:

| Alive (base / head) | Rust tick CPU, base | Head | Per agent | Rust tick wall, base / head |
| --- | ---: | ---: | ---: | --- |
| 22,110 / 23,015 | 260 ms | 287 ms | +6% | 144 / 112 ms |
| 50,360 / 50,462 | 1,260 ms | 1,390 ms | +10% | 454 / 419 ms |

The new per-agent work is the co-resident bond count (one id-to-region
map a tick and a pass over its bonds) and a scan of its conquest memories.
Wall time was noisier than the difference.

## 9. Verification

On the merged head (extension `0cb2948c...7cdb8d`, source `3a9b945`;
test-only changes after it):

- `cargo test` (debuginfo off): 979 passed, 2 ignored.
- `pytest -m "not slow" -n 2`: 6,146 passed, 3 skipped. Two tests were
  updated: the native harsh-rule test reads the needs batch through
  pyarrow, and the maritime piracy test moved from seed 7 to seed 8 (seed
  7's 40-turn hybrid world now crosses the sea 3 times; over seeds 7-14
  crossings average 67 against 54 on base).
- `pytest -m slow -n 2`: 11 passed, 3 skipped.
- No-Rust suite (`chronicler_agents` absent): 5,921 passed, 228 skipped.
- `scripts/run_python_oracle_checks.py`: PASS in 76.0 s, 2,102 passed, 28
  skipped; largest chunk 28.3 s of 110 s.

## 10. Open

- **The oracle does not see the terms** (§4; addressed by method 3,
  `needs-followups.md` §1). Candidates for an oracle change, not made here: count a pair only when its lower agent is below
  the threshold (terms on +0.27 against off +0.08 on these subsets), match
  within the condition (famine, war zone, persecution) as well as the
  cell, or run a terms-off control arm in the gate.
- **Newborns start every need at 0.5**, so needs still carry age
  (addressed: newborns start from the birth parent's needs,
  `needs-followups.md` §2).
  Fixed-point newborns removed that channel but cost the strict PASS with
  the terms on.
- **Autonomy in good conditions** binds 5.7%, mostly the five-turn block
  on restoration after each move, unchanged from base (addressed: the
  block is gone, `needs-followups.md` §3).
- **Material** raises the will to move, not the pull of any destination;
  where a whole world starves, its push has nowhere better to send people.
- **Safety** has few pairs below the threshold (war zones are 3.7% of
  agent-turns), so its pairing reads conditions, not the term.
- **Rebellion** rose 0.0308 -> 0.0385 at 500 turns (subsets up to 0.052),
  inside the band. With the terms zeroed the subsets read 0.038 / 0.022 /
  0.037, near base (0.036 / 0.018 / 0.033), so the rise comes from the
  autonomy push.
- **Spiritual and purpose** are unchanged: minority faiths without a
  temple 19% below, non-farmers 21-28%.
- Artifacts PARTIAL on subset 62-81 (informational; the terms-off build
  too).
