# Healthy-world migration drivers

Branch `feat/healthy-migration`, from `fix/leftover-persecution` at
`f3eccec`, merged with `integrate/wave-6` (food logistics). A **behavior
correction** in the Rust agent tick: on in every agent mode, like the
food-balance corrections. Agents-off output and the golden fixtures
(off-mode captures) do not change. Migration constants are M53 HARD; this
document is their justification (approved for this change).

**Status.** Phase A (design, implementation, tests) and Phase B (merge,
calibration on the 20 x 500 probe, subset gates, golden check, full gate)
are done; the calibrated constants are in `8d675be`. Results below.

## Result

"Merged base" throughout: the tally commit `efc2b06` (the persecution fix,
no drivers) merged with `547ebbc` in a local scratch branch, built
separately.

| | merged base | branch |
| --- | ---: | ---: |
| migration per agent-turn, gate probe (seeds 142-161 x 500) | 0.0497 | 0.0569 |
| regression oracle on migration | calibrated floor | strict (>= 0.05) |
| migration per agent-turn, traced (same seeds, from turn 100) | 0.0486 | 0.0562 |
| paired by seed | - | +0.0067 +- 0.0025 (15 up / 4 down) |
| healthy drivers, share of migration units (with their household followers) | - | 5.9% (15.2%) |
| satisfaction mean / latest | 0.613 / 0.629 | 0.609 / 0.615 |
| rebellion per agent-turn | 0.0402 | 0.0403 |
| full gate, 200 x 500 (baseline: wave-6 head without the persecution fix) | PASS, migration 0.0514 | PASS, NO REGRESSION, migration 0.0570 |

The subset gates, the golden check and the full gate are in
[Gates](#gates).

## The gap

The persecution fix removed the phantom persecution that had held migration
up; on the 20-seed x 500-turn probe (seeds 142-161) migration fell from
0.0501 to 0.0468 per agent-turn, against the 0.05 strict floor and the
5-15% design band (M53 spec, sections 5.4 and 7.2). After the merge with
food logistics the base reads 0.0497 on the gate probe and passes only on
the calibrated floor.

The migrate utility (`behavior.rs`) answers distress only:

- `W_MIGRATE_SAT 1.10 x (0.25 - satisfaction)+`: off at the usual 0.6;
- `W_MIGRATE_OPP 1.10 x (opportunity - 0.18)+`, where opportunity is the
  best neighbour's score minus home's (mean satisfaction, headroom 0.20 x
  (1 - pop/cap), overcrowding 0.80 x (pop/cap - 1)+, food 0.25 x (suff - 1)).
  Between fed, uncrowded neighbours the gap stays under 0.18;
- live persecution, memories of famine, war and persecution, and needs,
  which trigger only in deprivation.

The decision is a Gumbel draw over rebel, migrate, switch and stay at
temperature 0.3, with stay at 0.58. A migrate utility that is barely
positive already wins 12.6% of the time (0.1: 16.8%, 0.3: 28.2%); zero or
less is never chosen. What decides migration is therefore whether the
utility is positive at all: each driver's *gate* sets its volume, its size
matters less. A driver that only raises a weight does nothing where the
gate is closed and floods where it is open.

### Exact budget of the base

The first commit (`efc2b06`) makes the decision record each migration it
decides, split across the positive terms in proportion
(`AgentSimulator.get_migration_driver_stats`). It is behavior-neutral:
hybrid output of seeds 42 and 7 over 150 turns is identical to the base,
18 files, 0 differences. The probe budget had been rebuilt from 10-turn
census sidecars, which left 17-20% unattributed.

Merged base, seeds 142-161, 500 turns, from turn 100, as shares of
migration units (each decision one unit, each household follower one
unit): household followers 41.9%, famine memory 31.3%, persecution memory
11.0%, live persecution 4.8%, opportunity terms 9.7%, needs 0.8%. Four in
ten migrants follow a married decider (`household.rs`). Nothing moves
agents in a healthy world.

## Design

`chronicler-agents/src/migration_drivers.rs`. Three pulls, each with its own
gate, and one threshold every pull must clear.

**Structure.** For an agent that is not displaced or travelling:

1. `Mobility::for_agent` builds, on the stack, the agent's roots and its
   bonds toward settled emigrants (one pass over at most 8 bonds).
2. For every admissible neighbour (the existing soft-cap, exit-delta and
   relative-crowding filters still apply), `pull_toward` gives the gross
   pull by driver; `net_of_roots` keeps what exceeds the roots.
3. **Reach.** The pull counts only toward a neighbour from which home would
   not score the 0.18 hysteresis better (river bonus counted from both
   sides); otherwise the opportunity term would carry the mover back once
   the 5-turn lock ends.
4. The net pull joins the neighbour's score in the target choice, and the
   pull toward the chosen target is added to the migrate utility (before the
   household damping). The opportunity term reads the score without it.

A gate that opens gives `PULL_AT_GATE` 0.75 of the driver's full pull,
growing to the full pull with the gap. An agent whose roots hold against
every pull, or who is not eligible, chooses and decides exactly as before
(the pull is added only when positive). The decision still makes four
Gumbel draws per agent; no new random stream.

**Internal only.** Every voluntary pull needs the same ruler at both ends.
Moving never changes an agent's civ affinity, and 69% of agents already
live under another civ's rule (four seeds, 300 turns), so "own civ" is the
realm the agent lives in:

- across a border the mover joins a foreign minority: cultural mismatch
  with the controller's values (up to 0.15), religious mismatch, exposure
  to a militant ruler's persecution, and loyalty drift toward a happier
  civ in the region (which can flip affinity);
- hybrid mode counts cross-border moves in the civ migration hazard
  (`_agent_unrest_shares`: rate scales with the cross-border share, each
  event drains stability); internal moves are excluded;
- unclaimed land has no controller values, which the cultural penalty
  reads as a full mismatch (0.15), and no administration.

Distress migration keeps crossing borders as before.

### Frontier settlement

Young farmers leave land that is full for land of the same realm that is
not: inheritance and holding sizes push the surplus generation out
(internal colonisation, frontier settlement). The draw is land. In the
model carrying capacity stands for the room, and the harvest a farmer
would get for what the land can feed.

- Gate: a farmer; home at `FRONTIER_SOURCE_MIN_RATIO` 0.80 of capacity or
  more; the neighbour at least `FRONTIER_MIN_GAP` 0.25 emptier (share of
  capacity); its land feeds a farmer: `food_potential` at least
  `FRONTIER_MIN_FOOD_POTENTIAL` 0.5.
- `food_potential` is the best food slot's year of harvest per farmer as the
  land stands (`ecology::annual_yield_potential`: base yield x the mean
  season modifier x soil x water for crops), with no season, climate phase
  or abundance multiplier. 0.5 is the economy's food a head: land where a
  farmer at least feeds himself. Food here is what the goods economy counts
  as food (`economy::is_food_resource`).
- Pull: `FRONTIER_PULL` 0.6 x ramp(gap, 0.25, 0.65).
- An empty region reads mean satisfaction 0 and no stores, so its score
  never beat home's. An agent pulled toward an empty region judges it by
  home's mean satisfaction and food signal and the destination's room;
  agents without a pull score it as before.
- Why not stored food. The first design gated on food sufficiency 1.0.
  Sufficiency is stores over demand, and under-filled regions are mostly
  empty (median population 0, 78% without a farmer when they are the
  emptiest candidate). Over every qualifying neighbour of the young adults
  (20-30) who sit in a crowded home next to an emptier region of the realm
  (28% of young adults; base, three seeds, 300 turns), the stores gate
  passed 7.5% of the cases and the land gate passes 28% (18% for farmers);
  a quarter of the cases are empty land. Farmers who arrive produce in the
  next turn's harvest, which the economy runs before the agent tick, so
  their own food counts before a famine memory could be written.
- Self-limiting: the wave stops when home falls under 0.80 or the gap under
  0.25. In the Rust multi-tick test (`tests/test_healthy_migration.rs`) a
  wave leaves the full region in the first turns, stops once home is under
  the gate and nobody moves back over 40 turns.

### Wage gap

People move where people like them earn more (expected-income models of
migration). Two occupations earn by location in this model: farmers
(`BASE_FARMER_INCOME x farmer_income_modifier x yield`) and merchants
(regional arbitrage per merchant). Soldier and scholar pay is flat; priest
pay and tithe are set per civ.

- Signal: the mean wealth of the occupation's adult peers in each region
  (merchants away on a trip count at home). Wealth accumulates income at 2%
  decay a turn, so it is income averaged over about 50 turns: steady
  against seasonal yield swings that a current-income signal would chase.
  Newcomers dilute the destination's mean, and more farmers lower the farm
  price, so the gap closes as people arrive. Children are left out: they
  carry an occupation and earn from birth, but start from
  `STARTING_WEALTH`, so counting them made a region with many births look
  poorly paid (see the calibration).
- Gate: at least `WAGE_MIN_PEERS` 5 adult peers there; their mean wealth
  at least `WAGE_MIN_RATIO` 1.25 times home's (home's mean floored at
  `WAGE_WEALTH_FLOOR` 1.0, so near-zero wealth is not a large ratio); the
  destination below `WAGE_MAX_TARGET_RATIO`, the frontier gate's 0.80, so
  the wage gap does not refill a region that frontier settlement is
  leaving.
- Pull: `WAGE_PULL` 0.55 x ramp(ratio, 1.25, 3.0).

### Chain migration

Emigrants draw their kin and friends after them. The pull runs through
bonds into the destination; the bonds at home keep anchoring.

- Bonds: positive valence (kin, marriage, friend, mentor, co-religionist,
  exile), sentiment at least `BOND_MIN_SENTIMENT` 20, strength
  sentiment / 127.
- Gate: the bonded person emigrated from the agent's region
  (`origin_region` is the agent's region), is settled (no displacement
  turns left) in a neighbouring region of the same realm, and the strength
  of such bonds there exceeds the strength of the bonds at home. The spouse
  is not an anchor: the spouse moves with the household.
- Pull: `CHAIN_PULL_PER_BOND` 0.30 per unit strength, capped at
  `CHAIN_PULL_CAP` 0.45.
- Direction: a native of the destination does not pull, and the emigrant is
  not pulled back toward the people left behind (they are not emigrants
  from the emigrant's new region). Social anchoring stays: community
  members, with dense bonds at home, are pulled only once most of their
  bonds have left.

### Roots (life course)

Mobility peaks in young adulthood and falls with age and household ties.
Roots are the share of a pull an agent does not act on:

- `MOBILITY_MIN_AGE` = `AGE_ADULT` 20: dependants take no voluntary moves
  (they follow a married parent's household move, `household.rs`);
- age: 0 through `ROOTS_FREE_AGE` 35, then `ROOTS_PER_YEAR` 0.006 a year
  (0.15 at 60, 0.27 at 80);
- `ROOTS_MARRIED` 0.02: a married decider moves the household, whose
  utility the household damping already lowers;
- `ROOTS_PER_HOME_BOND` 0.02 per unit of positive bond strength at home
  (spouse excluded), up to `ROOTS_HOME_BOND_CAP` 2 units.

Roots apply to the voluntary pulls only; distress migration is unchanged.
Frontier and wage pulls open at 0.45 and 0.41 and grow to 0.60 and 0.55,
so roots alone close one only past 100; they shrink it with age,
and the life course shows in who acts (below).

### The 0.18 hysteresis

Kept. A smaller continuous pull on the destination score would act on
noise. Per-turn region scores (base, seeds 142-144, 300 turns, directed
neighbour pairs from turn 50):

| score gap | share of pair-turns | reversed within 5 turns |
| --- | ---: | ---: |
| 0.05-0.10 | 5.6% | |
| 0.10-0.18 | 5.7% | |
| >= 0.05 | 21.4% | 41% |
| >= 0.10 | 15.8% | 26% |
| >= 0.18 | 10.1% | 11% |

"Reversed" means the opposite direction clears the same threshold within
five turns, the length of the displacement lock. At 0.10 a quarter of the
gaps that would open the gate reverse before the movers may move again,
and any positive utility moves 12.6% of the eligible agents a turn. The
new drivers instead gate on structural differences (crowding, wealth
accumulated over decades, where people's bonds are) that do not flip from
turn to turn. The 5-turn displacement lock is kept.

## Phase A (design values, before food logistics)

Seeds 142-161 x 500 turns, hybrid, `--simulate-only`, `PYTHONHASHSEED=0`,
through the output-neutral observer, from turn 100. Base `efc2b06`; branch
`c0cadd5` (land gate, farmers, empty regions judged by home).

- Migration 0.0449 -> 0.0508 per agent-turn (paired +0.0069 +- 0.0033,
  13 up / 6 down); frontier / wage / chain 0.2 / 0.4 / 0.0% of units.
- Gates open before roots for 2.2 / 4.5 / 1.0% of evaluated agent-turns,
  beyond roots 0.3 / 0.6 / 0.1%: roots held about seven in eight.
- The stores gate (`ba7a9c8`) opened about as often over all agents, but
  mostly toward populated regions with stock; the land gate also opens
  toward empty fertile land.
- Sloshing checks at or below the base; agents-off identity 16 files,
  0 differences.

## Phase B: calibration on the merged world

`integrate/wave-6` (`547ebbc`) merged without rebase (`56944ca`);
`tests/test_maritime.py` reconciled (seed 12, 40 turns). The gate-open
rates were re-measured on the merged world before tuning (the locust rate
fell from 0.15 to 0.02): with the Phase A constants (b0) they are 1.7 /
5.4 / 0.9% of evaluated agent-turns, and roots still held most of them.

Each step changes the one before: the 20 x 500 gate probe (the subset
profile at 500 turns, compared with the merged base by
`validation_compare`) and the traced arm (same seeds, observer, from turn
100). Every probe passed the gate with no comparator regression.

| step | change | gate probe | traced | healthy (with followers) | voluntary-led by age 20-34 / 35-49 / 50-64 / 65+ |
| --- | --- | ---: | ---: | --- | --- |
| base | merged, no drivers | 0.0497 | 0.0486 | - | - |
| b0 | Phase A constants | - | 0.0509 | 0.7% | - |
| R3 | roots 35 / 0.004 / 0.02 / 0.02; wage 1.35; frontier 0.80 / 0.25 | - | 0.0537 | 3.2% | - |
| R5 | `PULL_AT_GATE`; pulls 0.45 / 0.40 / 0.30; wage 1.25; land 0.5 | 0.0588 | 0.0580 | 7.4% (19.5%) | - |
| R6 | land 0.75 | 0.0553 | 0.0536 | 6.1% | - |
| R7 | land 0.5; `PULL_AT_GATE` 0.75; frontier 0.5, wage 0.45 | 0.0611 | 0.0606 | 8.4% (22.0%) | 43 / 27 / 17 / 12% |
| R8 | roots 0.008; wage 1.5 | 0.0560 | 0.0551 | 6.3% (16.7%) | 51 / 31 / 14 / 4% |
| R9 | wage 1.25; wage room below 0.80 | 0.0567 | 0.0561 | 5.7% (14.7%) | 52 / 31 / 14 / 3% |
| R10 | roots 0.006; pulls 0.6 / 0.55 | 0.0580 | 0.0570 | 7.2% (18.6%) | 44 / 28 / 18 / 10% |
| R11 | adult peers, 5 peers | 0.0571 | 0.0558 | 6.1% (15.7%) | 44 / 28 / 18 / 10% |
| final | reach rule | 0.0569 | 0.0562 | 5.9% (15.2%) | 44 / 28 / 18 / 11% |

All decisions by age (final): under 20 34%, 20-34 20%, 35-49 15%, 50-64
12%, 65+ 19%. Voluntary moves are led by young adults at twice their share
of all decisions; under-20s take none.

### Budget per driver, before and after

Shares of migration units, from turn 100 (20 runs):

| driver | base | b0 | R7 | final |
| --- | ---: | ---: | ---: | ---: |
| migrations per run (events) | 3,658 | 3,818 | 4,619 | 4,298 |
| migration per agent-turn | 0.0486 | 0.0509 | 0.0606 | 0.0562 |
| household followers | 41.9% | 42.0% | 44.1% | 43.8% |
| famine memory | 31.3% | 28.9% | 25.9% | 26.9% |
| persecution memory | 11.0% | 12.2% | 8.2% | 9.5% |
| live persecution | 4.8% | 5.4% | 3.7% | 4.2% |
| opportunity: food / satisfaction / capacity | 4.7 / 2.8 / 2.1% | 4.7 / 2.8 / 2.0% | 4.2 / 2.5 / 1.6% | 4.2 / 2.5 / 1.7% |
| low own satisfaction / needs | 0.5 / 0.8% | 0.5 / 0.8% | 0.5 / 0.7% | 0.5 / 0.8% |
| frontier settlement | - | 0.2% | 1.4% | 1.5% |
| wage gap | - | 0.5% | 6.7% | 4.2% |
| chain migration | - | 0.0% | 0.3% | 0.3% |
| healthy drivers with their followers | - | - | 22.0% | 15.2% |
| gate open before roots, frontier / wage / chain (per evaluated agent-turn) | - | 1.71 / 5.39 / 0.87% | 1.09 / 5.95 / 0.95% | 1.18 / 3.24 / 1.06% |
| pull beyond roots | - | 0.23 / 0.68 / 0.07% | 0.99 / 5.11 / 0.47% | 0.86 / 2.56 / 0.42% |
| decided per turn with the pull beyond roots | - | 0.12 / 0.13 / 0.14 | 0.19 / 0.17 / 0.15 | 0.20 / 0.18 / 0.14 |

Distress terms keep their order; the healthy drivers take 15% of the
units with their households, wage gaps the most.

### Corrections found while calibrating

The first three were traced in the multi-tick Rust tests, which started
to move people back as the pulls grew; the fourth follows from the
utility:

- **Wage refilling the frontier.** A wage gap drew farmers into a region at
  0.80 of capacity, which reopened the frontier gate out of it the next
  turn. Wage targets now need room below the frontier gate's 0.80.
- **Children in the peer mean.** Births (pop 42 -> 65 in 14 turns) diluted
  a region's farmer mean wealth and flipped the wage gap in the other
  direction within 14 turns. Peers are now adults.
- **Three peers.** With three or four merchants, whoever switched into
  trade set the mean (in the test world, merchants earn nothing, yet the
  gate opened both ways within 11 turns). Five peers are required.
- **Reach.** Without it a strong pull could take an agent to a region that
  scores far below home, from which the opportunity term carries it back.

On the base world (three seeds, sampled every 5 turns) the wealth gate
for farmers reverses within 10 turns in 5% of open cases (adults only:
4%), for merchants in 9% (7%).

R7's extra volume came from weaker roots and from wage gaps that these
corrections remove (R10 -> R11: -0.0012 traced); its 0.061 is not kept.

### Sloshing

Per-seed, paired with the base (20 seeds, mean +- standard error):

| | returns within 10 turns | reverse flow next turn | region pairs alternating 3+ turns |
| --- | --- | --- | ---: |
| base | 20.9% | 17.2% | 260 |
| R7 | +1.57 +- 1.09 pp | +1.66 +- 1.23 pp | 478 |
| R9 | -0.64 +- 1.06 pp | +0.55 +- 1.06 pp | 409 |
| final | +0.98 +- 1.03 pp | +1.51 +- 1.04 pp | 375 |

- "Returns" is the share of migrations followed by the same agent moving
  back within 10 turns; "reverse flow" the share matched by a flow the
  other way on the next turn. Both are within about one standard error of
  the base: histories diverge from the first changed move, so per-seed
  differences are mostly chance.
- Alternating pairs count region pairs with flows both ways on 3 or more
  consecutive turns; they grow with the number of flows (+17% events),
  and two drivers can move different people both ways (farmers one way,
  merchants the other).
- Returns by destination size (final): 1-5 agents 29.9% (197 moves),
  6-20 26.5%, 21+ 21.1%. Settling nearly empty land is rare and not where
  the returns are.
- Returns by occupation (R10 against the base, seeds 142-150, occupation
  from the cached post-tick snapshot; the traced events are identical to
  the untraced arm): farmers 20.6 -> 24.2%, merchants 16.0 -> 20.6%, other
  occupations -0.8 to +1.8 pp. Voluntary movers and their households come
  back more often than people who fled; with a strong rise in voluntary
  moves the per-migrant return share rises with them. The corrections
  above (R11, final) did not change the overall share beyond noise.

### Not reached: 0.06-0.08

The aim was migration comfortably at 0.06-0.08. The drivers' gates open for
1.2 / 3.2 / 1.1% of evaluated agent-turns, and about a fifth of the agents
with a pull beyond their roots act on it each turn; with household
followers this adds +0.007 to +0.008. More volume would come from larger
pulls or looser gates: from raised weights, which the design rules out,
or from gaps the hysteresis analysis shows to be noise. The margin over
the strict 0.05 floor is 0.0069 on the probe and 0.0070 on the full gate;
the base passes the probe only on the calibrated floor.

The occupational dead-band patch (`c3b`, about -0.006 migration) is not
applied: it would take the probe to about 0.051.

## Gates

**Subset gates** (20 seeds x 200 turns, `--parallel 3`), the merged base
against the branch (`8d675be`), compared by `validation_compare`:

| | 42-61 base | 42-61 branch | 62-81 base | 62-81 branch |
| --- | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION | PASS / - | PASS / NO REGRESSION |
| migration per agent-turn | 0.0521 | 0.0600 | 0.0474 | 0.0571 |
| rebellion per agent-turn | 0.0307 | 0.0343 | 0.0206 | 0.0189 |
| satisfaction mean / latest | 0.600 / 0.616 | 0.597 / 0.623 | 0.612 / 0.630 | 0.599 / 0.609 |
| needs (seeds with the expected sign) | 16 | 13 | 12 | 15 |
| cohort / community (seeds) | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 |
| regression oracle (informational at subset) | FAIL: civ survival | PASS strict | PASS calibrated floor (migration) | FAIL: rebellion, civ survival |

At 200 turns the regression oracle is informational. Its civ-survival
check allows at most a fifth of the worlds with every civ alive (62-81:
base 3, branch 8 of 20) and its rebellion floor is 0.02 (62-81: base
0.0206, branch 0.0189); the base fails the civ-survival check on 42-61
(5 of 20; branch 3). Both are settled by the full gate below.

**Golden fixtures.** `tests/test_performance_equivalence.py` and
`tests/test_governance_dormancy.py` against the live
`corrected_food_logistics_2026_10.json` oracle and every `ORACLE_CHAIN`
link: 74 passed, unchanged (the fixtures are agents-off captures).

**Full gate.** `scripts/m53b_run_validation.py --profile full --parallel 3`
(200 seeds x 500 turns, seeds 42-241, `PYTHONHASHSEED=0`), branch build
`8d675be`, compared by `validation_compare` with the food-logistics full
gate of the merged wave-6 head (`eda0ec0`, which does not include the
persecution fix):

| | baseline `eda0ec0` | branch |
| --- | ---: | ---: |
| gate / comparator | PASS | **PASS / NO REGRESSION** |
| regression oracle | PASS strict | PASS strict |
| migration per agent-turn | 0.0514 | 0.0570 |
| satisfaction mean / latest (ceiling 0.65) | 0.602 / 0.611 | 0.608 / 0.619 |
| rebellion per agent-turn (floor 0.02) | 0.0513 | 0.0307 |
| needs (seeds with the expected sign; 120 required) | 190 | 185 |
| cohort / community (seeds) | 200 / 200 | 200 / 200 |
| arcs (seeds with three types) / era | 166 / 200 | 164 / 200 |
| worlds with every civ alive / extinct worlds | 12% / 0 | 12% / 0 |
| artifacts | PASS | PASS |

The rebellion drop is the persecution fix, which the baseline lacks: on
the probe, the merged base with the fix reads 0.0402 and the branch
0.0403. Migration clears the strict 0.05 floor by 0.007 on 200 seeds.

## Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, 3 warm-up and 8
timed turns, two repeats, one child at a time, release builds, shared
4-core machine (median Rust tick per run, wall / process CPU):

| agents | merged base | branch `8d675be` |
| ---: | ---: | ---: |
| ~21,800 | 151, 130 / 278, 275 ms | 92, 92 / 278, 268 ms |
| ~53,100 | 713, 499 / 1,586, 1,630 ms | 525, 712 / 1,500, 1,495 ms |

Process CPU, the steadier figure on a shared machine, is unchanged or
lower; wall time moves with the machine's load. Phase A (`c0cadd5` against
`f3eccec`) was also within noise. The per-agent work is one pass over at
most 8 bonds (one id lookup each, in the map the household code already
builds) and a few comparisons per neighbour, with no allocation; per-region
peer wealth, food potential and the internal-neighbour flag are computed
once per tick in the existing region-stats pass. The follower attribution
is a binary search in the region's slot-ordered decisions.

## Constants

All M53 HARD (migration consideration thresholds), tagged
`[CALIBRATE M53 HARD]` in the source.

| Constant | Value | Why |
| --- | ---: | --- |
| `MOBILITY_MIN_AGE` | 20 | the model's adulthood (`AGE_ADULT`); households carry dependants |
| `ROOTS_FREE_AGE` | 35 | end of the young-adult mobility peak |
| `ROOTS_PER_YEAR` | 0.006 | 0.15 at 60, 0.27 at 80: a quarter to two thirds of a frontier or wage pull (0.41-0.60); voluntary moves stay led by young adults (44% of them 20-34, against 20% of all decisions). 0.008 (R9) gave 52 / 31 / 14 / 3% at the same volume, within noise on the sloshing checks |
| `ROOTS_MARRIED` | 0.02 | a household moves as one, and the household damping already lowers the lead's utility |
| `ROOTS_PER_HOME_BOND` | 0.02 | a typical agent's 1-2 units at home cost 0.02-0.04 |
| `ROOTS_HOME_BOND_CAP` | 2.0 | anchoring saturates; dense networks do not freeze agents outright |
| `BOND_MIN_SENTIMENT` | 20 | below the weakest formed bond (co-religionist 25): fading ties count for nothing |
| `PULL_AT_GATE` | 0.75 | an open gate is a real opportunity; a pull that starts from zero would sit wherever an agent's roots put it |
| `FRONTIER_SOURCE_MIN_RATIO` | 0.80 | "near capacity": between the 75th (0.72) and 90th (0.90) percentile of ruled region-samples (base, three seeds) |
| `FRONTIER_MIN_GAP` | 0.25 | well above the turn-to-turn noise of crowding; prevents a back-flow gradient |
| `FRONTIER_FULL_GAP` | 0.65 | full pull for a region less than a sixth full next to a full one |
| `FRONTIER_MIN_FOOD_POTENTIAL` | 0.5 | the economy's food a head: a farmer at least feeds himself. 0.75 (the usual farmer share feeding everyone; R6) took the gate probe from 0.0588 to 0.0553 |
| `FRONTIER_PULL` | 0.6 | above any single distress push (fresh famine memory 0.125, live persecution up to 0.20); acts on about a fifth of the open gates a turn |
| `WAGE_MIN_RATIO` / `WAGE_FULL_RATIO` | 1.25 / 3.0 | a clear gap in income accumulated over decades; 1.5 (R8, with roots 0.008) cut the wage moves by a third, the sloshing checks within noise either way |
| `WAGE_WEALTH_FLOOR` | 1.0 | below starting-wealth scale, ratios are meaningless |
| `WAGE_MIN_PEERS` | 5 | with three, one agent's wealth set the mean |
| `WAGE_MAX_TARGET_RATIO` | 0.80 | = `FRONTIER_SOURCE_MIN_RATIO`: no wage move into a region the frontier gate counts as full |
| `WAGE_PULL` | 0.55 | a little under the frontier pull: income gaps are less certain than land |
| `CHAIN_PULL_PER_BOND` / `CHAIN_PULL_CAP` | 0.30 / 0.45 | one close kin bond (0.5-0.6 units) gives 0.15-0.19; two or three reach the cap |

## Migration budget tooling

- Native: `get_migration_driver_stats()` after each tick: `evaluated`,
  `decided`, `unexplained`, `share_<term>` and `present_<term>` for 17
  terms (including `frontier`, `wage`, `chain`), `follow_<term>` (household
  followers by the lead's largest term), `gate_<driver>` (agents for whom
  some neighbour opens the gate, before roots), `open_<driver>` (agents
  whose chosen target carries that pull beyond their roots), and
  `decided_age_<band>` / `voluntary_age_<band>` (decisions by the
  decider's age band, all and voluntary-led). Production Python does not
  read it, so bundles do not change.
- Observer and tools (run directory, not committed): `mtrace.py` records
  the tally, household followers, migration events and region populations
  per tick; `budget.py` prints the budget with one row per driver,
  household followers as their own row, and the sloshing checks;
  `returns_paired.py` pairs the sloshing checks by seed.

## Tests

- Rust, `migration_drivers`: roots by age, marriage and home bonds;
  `net_of_roots`; mobility eligibility (dependants, unruled regions); the
  frontier, wage and chain gates one condition at a time (farmers,
  crowding, gap, land not stores, foreign and unclaimed targets;
  occupations, peers, room, wealth floor; settled emigrants, natives,
  displacement, spouse, home bonds, rivals, weak bonds, borders); food
  potential (best food slot, season-free, suspension); the budget split.
  Thresholds are read from the constants.
- Rust, `behavior`: frontier settlers leave a full region; elders whose
  roots exceed the full pull (the gate opens, the roots hold), dependants
  and foreign targets draw none, and the net pull falls with age; settlers
  judge an empty region by home and others do not; the pull counts in the
  target choice but not in the opportunity; no pull toward a region the
  mover would leave again (reach); memory and need pushes by type.
- Rust, `tests/test_healthy_migration.rs` (multi-tick through
  `tick_agents`): a frontier wave fills the emptier region, stops at the
  gate and moves nobody back; no frontier pull toward a foreign region;
  determinism; kin follow settled emigrants and no chain decision moves
  anyone back.
- Python, `tests/test_healthy_migration.py` (native, through
  `AgentBridge`): the budget getter's keys and shares; frontier settlement
  inside the realm and none toward a foreign-ruled neighbour, mostly young
  movers.
- No existing expectation changed.

## Verification

Linux, Python 3.13; native extension built fresh (`maturin develop
--release --locked`) from `8d675be` into the worktree environment and
checked as the compiled `chronicler_agents.chronicler_agents` with real
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` classes
(sha256 `3d47d60f15503b47...`).

| Check | Result |
| --- | --- |
| `cargo test --locked` | 927 passed, 0 failed, 2 ignored |
| `pytest -m "not slow" -n 3` | 5,923 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 3` | 11 passed, 3 skipped |
| no-Rust lane (virtualenv without `chronicler_agents`) | 5,718 passed, 208 skipped (the native tests skip) |
| `scripts/run_python_oracle_checks.py` | PASS in 66.1 s: core 1,055, governance 568, systems-1 126, systems-2 160 passed; slowest chunk 18.5 s of 110 s (the new tests are native and not in its selection) |
| golden fixtures (above) | 74 passed |
| `tests/test_maritime.py` (merge resolution: seed 12, 40 turns) | passes on the final build |
| agents-off identity, merged base (its build) against `8d675be` (seeds 42 and 7, 150 turns) | 16 files, 0 differences |
| hybrid identity of the tally commit `efc2b06` against `f3eccec` | 18 files, 0 differences (Phase A) |

The oracle lane does not qualify native execution; the native checks are
the cargo tests, the native pytest lanes and the gates above.

## Open items

- `mass_migration` events (8 or more agents leaving one region in one
  tick) are narrated as flight ("fled X for Y") whatever moved them, so a
  settlement wave reads as flight. Labelling them needs the dominant
  driver on each migration event (a new or repurposed agent-event column
  and household followers inheriting the lead's label), which changes
  `agent_events` content and hybrid bundle text; left for its own review.
  Done on `fix/navigation-famine-labels` (a `migration_driver` event
  column; [navigation-famine-labels.md](navigation-famine-labels.md)).
- The 0.06-0.08 aim is not reached (above).
