# Healthy-world migration drivers

Branch `feat/healthy-migration`, from `fix/leftover-persecution` at
`f3eccec`. A **behavior correction** in the Rust agent tick: on in every
agent mode, like the food-balance corrections. Agents-off output and the
golden fixtures (off-mode captures) do not change. Migration constants are
M53 HARD; this document is their justification (approved for this change).

**Status.** Phase A (design, implementation, tests) is done. Phase B
(merge of `integrate/wave-6` with food logistics, calibration on the 20 x 500
probe, subset gates, golden check, full gate) waits for food logistics. The
constants below are design values, not calibrated ones.

## The gap

The persecution fix removed the phantom persecution that had held migration
up; on the 20-seed x 500-turn probe (seeds 142-161) migration fell from
0.0501 to 0.0468 per agent-turn, against the 0.05 strict floor and the
5-15% design band (M53 spec, sections 5.4 and 7.2).

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

The probe budget had been rebuilt from 10-turn census sidecars, which left
17-20% unattributed. The first commit (`efc2b06`) makes the decision record
each migration it decides, split across the positive terms in proportion
(`AgentSimulator.get_migration_driver_stats`; household followers stay in
`get_household_stats`). It is behavior-neutral: hybrid output of seeds 42
and 7 over 150 turns is identical to the base, 18 files, 0 differences.

Base (`f3eccec` behavior), seeds 142-161, 500 turns, migrations from turn
100, as shares of migration units (each decision one unit, each household
follower one unit):

| Driver | share |
| --- | ---: |
| migrations per run (events) | 2,927 |
| household followers (spouses, dependants) | 43.6% |
| famine memory | 30.9% |
| persecution memory | 9.1% |
| opportunity: food / satisfaction gap / capacity | 5.4 / 3.2 / 2.4% |
| live persecution | 3.4% |
| low own satisfaction | 1.0% |
| needs | 0.8% |
| war memories | 0.1% |

Four in ten migrants are followers of a married decider: households move as
units (`household.rs`). Of the agents' own decisions, famine memory carries
55%, persecution 22%, all opportunity terms 20%. Nothing moves agents in a
healthy world.

## Design

`chronicler-agents/src/migration_drivers.rs`. Three pulls, each with its own
gate, and one threshold every pull must clear.

**Structure.** For an agent that is not displaced or travelling:

1. `Mobility::for_agent` builds, on the stack, the agent's roots and its
   bonds toward settled emigrants (one pass over at most 8 bonds).
2. For every admissible neighbour (the existing soft-cap, exit-delta and
   relative-crowding filters still apply), `pull_toward` gives the gross
   pull by driver; `net_of_roots` keeps what exceeds the roots.
3. The net pull joins the neighbour's score in the target choice, and the
   pull toward the chosen target is added to the migrate utility (before the
   household damping). The opportunity term reads the score without it.

An agent whose roots hold against every pull, or who is not eligible,
chooses and decides exactly as before (the pull is added only when
positive). The decision still makes four Gumbel draws per agent; no new
random stream.

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

- Gate: a farmer; home at `FRONTIER_SOURCE_MIN_RATIO` 0.85 of capacity or
  more; the neighbour at least `FRONTIER_MIN_GAP` 0.30 emptier (share of
  capacity); its land feeds settlers: `food_potential` at least
  `FRONTIER_MIN_FOOD_POTENTIAL` 0.75.
- `food_potential` is the best food slot's year of harvest per farmer as the
  land stands (`ecology::annual_yield_potential`: base yield x the mean
  season modifier x soil x water for crops), with no season, climate phase
  or abundance multiplier. 0.75 is the economy's 0.5 food a head over the
  0.66 ceiling on the farmers' share of the labor mix: land where the usual
  share of farmers feeds everyone. Food here is what the goods economy
  counts as food (`economy::is_food_resource`).
- Pull: `FRONTIER_PULL` 0.30 x ramp(gap, 0.30, 0.70).
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
- Self-limiting: the wave stops when home falls under 0.85 or the gap under
  0.30. In the Rust multi-tick test (`tests/test_healthy_migration.rs`) a
  wave leaves the full region in the first turns, stops once home is under
  the gate and nobody moves back.

### Wage gap

People move where people like them earn more (expected-income models of
migration). Two occupations earn by location in this model: farmers
(`BASE_FARMER_INCOME x farmer_income_modifier x yield`) and merchants
(regional arbitrage per merchant). Soldier and scholar pay is flat; priest
pay and tithe are set per civ.

- Signal: the mean wealth of the occupation's peers in each region
  (merchants away on a trip count at home). Wealth accumulates income at 2%
  decay a turn, so it is income averaged over about 50 turns: steady
  against seasonal yield swings that a current-income signal would chase.
  Newcomers dilute the destination's mean, and more farmers lower the farm
  price, so the gap closes as people arrive.
- Gate: at least `WAGE_MIN_PEERS` 3 peers there; their mean wealth at least
  `WAGE_MIN_RATIO` 1.5 times home's (home's mean floored at
  `WAGE_WEALTH_FLOOR` 1.0, so near-zero wealth is not a large ratio); the
  destination below capacity (`WAGE_MAX_TARGET_RATIO` 1.0).
- Pull: `WAGE_PULL` 0.25 x ramp(ratio, 1.5, 3.0).

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
- Pull: `CHAIN_PULL_PER_BOND` 0.20 per unit strength, capped at
  `CHAIN_PULL_CAP` 0.30.
- Direction: a native of the destination does not pull, and the emigrant is
  not pulled back toward the people left behind (they are not emigrants
  from the emigrant's new region). Social anchoring stays: community
  members, with dense bonds at home, are pulled only once most of their
  bonds have left, and their roots are higher (below).

### Roots (life course)

Mobility peaks in young adulthood and falls with age and household ties.
Roots are the share of a pull an agent does not act on:

- `MOBILITY_MIN_AGE` = `AGE_ADULT` 20: dependants take no voluntary moves
  (they follow a married parent's household move, `household.rs`);
- age: 0 through `ROOTS_FREE_AGE` 30, then `ROOTS_PER_YEAR` 0.01 a year
  (0.10 at 40, 0.30 at 60, where a full frontier pull no longer moves
  anyone);
- `ROOTS_MARRIED` 0.08: a married decider moves the household;
- `ROOTS_PER_HOME_BOND` 0.06 per unit of positive bond strength at home
  (spouse excluded), up to `ROOTS_HOME_BOND_CAP` 2 units.

Roots apply to the voluntary pulls only; distress migration is unchanged.

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

## Phase A measurement (design values, before food logistics)

Not a calibration. Seeds 142-161 x 500 turns, hybrid, `--simulate-only`,
`PYTHONHASHSEED=0`, through the output-neutral observer, from turn 100.
Base is `efc2b06` (the tally on `f3eccec` behavior); "stores gate" is
`ba7a9c8` (frontier gated on food sufficiency); branch is `c0cadd5` (land
gate, farmers, empty regions judged by home).

| | base | stores gate | branch |
| --- | ---: | ---: | ---: |
| migrations per run (events) | 2,927 | 3,376 | 3,393 |
| migration per agent-turn (pooled) | 0.0449 | 0.0489 | 0.0508 |
| paired by seed against the base | - | +0.0045 +- 0.0030 (14/5) | +0.0069 +- 0.0033 (13/6) |
| household followers | 43.6% | 43.6% | 43.8% |
| famine memory | 30.9% | 32.3% | 29.5% |
| persecution memory / live persecution | 9.1 / 3.4% | 7.2 / 2.9% | 9.4 / 3.6% |
| opportunity terms | 11.0% | 11.4% | 10.8% |
| frontier / wage / chain | - | 0.2 / 0.4 / 0.1% | 0.2 / 0.4 / 0.0% |
| gate open, before roots (per evaluated agent-turn) | - | 2.44 / 4.26 / 1.01% | 2.16 / 4.51 / 0.98% |
| pull beyond roots | - | 0.29 / 0.54 / 0.10% | 0.27 / 0.58 / 0.08% |
| reverse flow on the next turn (share of migrations) | 18.7% | 17.2% | 17.4% |
| agent back where it came from within 10 turns | 23.6% | 22.3% | 22.7% |
| region pairs alternating 3+ turns (20 runs) | 208 | 217 | 207 |

- The drivers act rarely here: roots hold about seven in eight of the open
  gates. Roots are the main calibration lever, more than the pull sizes.
- The land gate opens as often as the stores gate did over all ages and
  occupations, but for farmers and toward land that can feed them: the
  stores gate mostly opened toward populated regions with stock, the land
  gate also toward empty fertile land.
- Histories diverge from the first changed move, so the per-seed
  differences are mostly chance.
- Sloshing does not rise: in the base nearly a quarter of migrants are
  back where they came from within ten turns (famine-memory churn); the
  branch is at or below it on the per-migrant checks and within chance on
  alternating pairs.
- Agents-off identity, base (`f3eccec`, its build) against the branch (its
  build), seeds 42 and 7, 150 turns: 16 files, 0 differences (`ba7a9c8`;
  `c0cadd5` in Verification).

### Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, 3 warm-up and 8
timed turns, two repeats, one child at a time, release builds, shared
4-core machine (median Rust tick per run, wall / process CPU):

| agents | base `f3eccec` | stores gate `ba7a9c8` | branch `c0cadd5` |
| ---: | ---: | ---: | ---: |
| ~21,800 | 185, 195 / 310, 297 ms | 223, 204 / 317, 317 ms | 187, 178 / 305, 314 ms |
| ~53,200 | 1,077, 1,060 / 1,847, 1,788 ms | 1,058, 1,074 / 1,864, 1,749 ms | 1,030, 1,041 / 1,732, 1,920 ms |

Within the run-to-run noise. The per-agent work is one pass over at most 8
bonds (one id lookup each, in the map the household code already builds)
and a few comparisons per neighbour, with no allocation; per-region peer
wealth, food potential and the internal-neighbour flag are computed once
per tick in the existing region-stats pass.

## Constants

All M53 HARD (migration consideration thresholds), tagged
`[CALIBRATE M53 HARD]` in the source until Phase B freezes them.

| Constant | Value | Why |
| --- | ---: | --- |
| `MOBILITY_MIN_AGE` | 20 | the model's adulthood (`AGE_ADULT`); households carry dependants |
| `ROOTS_FREE_AGE` | 30 | end of the young-adult mobility peak |
| `ROOTS_PER_YEAR` | 0.01 | roots equal the full frontier pull at 60 (`AGE_ELDER`) |
| `ROOTS_MARRIED` | 0.08 | a household moves as one; about a quarter of a full pull |
| `ROOTS_PER_HOME_BOND` | 0.06 | a typical agent's 1-2 units at home cost 0.06-0.12 |
| `ROOTS_HOME_BOND_CAP` | 2.0 | anchoring saturates; dense networks do not freeze agents outright |
| `BOND_MIN_SENTIMENT` | 20 | below the weakest formed bond (co-religionist 25): fading ties count for nothing |
| `FRONTIER_SOURCE_MIN_RATIO` | 0.85 | "near capacity": the upper third of region-turns (base median 0.81) |
| `FRONTIER_MIN_GAP` | 0.30 | well above the turn-to-turn noise of crowding; prevents a back-flow gradient |
| `FRONTIER_FULL_GAP` | 0.70 | full pull for a region less than a third full next to a full one |
| `FRONTIER_MIN_FOOD_POTENTIAL` | 0.75 | 0.5 food a head over the 0.66 farmer-share ceiling: the usual share of farmers feeds everyone |
| `FRONTIER_PULL` | 0.30 | equal to the roots at 60; a fresh famine memory pushes 0.125, live persecution at most 0.20 |
| `WAGE_MIN_RATIO` / `WAGE_FULL_RATIO` | 1.5 / 3.0 | a clear gap in accumulated income, not noise |
| `WAGE_WEALTH_FLOOR` | 1.0 | below starting-wealth scale, ratios are meaningless |
| `WAGE_MIN_PEERS` | 3 | a mean of fewer peers is anecdote |
| `WAGE_MAX_TARGET_RATIO` | 1.0 | a full region does not absorb newcomers |
| `WAGE_PULL` | 0.25 | a little under the frontier pull: income gaps are less certain than land |
| `CHAIN_PULL_PER_BOND` / `CHAIN_PULL_CAP` | 0.20 / 0.30 | one close kin bond (0.5-0.6 units) gives about 0.1-0.12 |

## Migration budget tooling

- Native: `get_migration_driver_stats()` after each tick: `evaluated`,
  `decided`, `share_<term>`, `present_<term>` for 17 terms (including
  `frontier`, `wage`, `chain`), `gate_<driver>` (agents for whom some
  neighbour opens the gate, before roots) and `open_<driver>` (agents whose
  chosen target carries that pull beyond their roots). Production Python
  does not read it, so bundles do not change.
- Observer and tools (run directory, not committed): `mtrace.py` records
  the tally, household followers and migration events per tick;
  `budget.py` prints the budget with one row per driver, household
  followers as their own row, and three sloshing checks (reverse flow on
  the next turn, an agent returning within 10 turns, region pairs
  alternating 3 or more turns).

## Tests

- Rust, `migration_drivers`: roots by age, marriage and home bonds;
  `net_of_roots`; mobility eligibility (dependants, unruled regions); the
  frontier, wage and chain gates one condition at a time (farmers,
  crowding, gap, land not stores, foreign and unclaimed targets;
  occupations, peers, room, wealth floor; settled emigrants, natives,
  displacement, spouse, home bonds, rivals, weak bonds, borders); food
  potential (best food slot, season-free, suspension); the budget split.
- Rust, `behavior`: frontier settlers leave a full region; elders (the
  gate opens, the roots hold), dependants and foreign targets draw none;
  settlers judge an empty region by home and others do not; the pull
  counts in the target choice but not in the opportunity; memory and need
  pushes by type.
- Rust, `tests/test_healthy_migration.rs` (multi-tick through
  `tick_agents`): a frontier wave fills the emptier region, stops at the
  gate and moves nobody back; no frontier pull toward a foreign region;
  determinism; kin follow settled emigrants and nobody is pulled back.
- Python, `tests/test_healthy_migration.py` (native, through
  `AgentBridge`): the budget getter's keys and shares; frontier settlement
  inside the realm and none toward a foreign-ruled neighbour, mostly young
  movers.
- No existing expectation changed.

## Verification (Phase A, before the merge with food logistics)

Linux, Python 3.13; native extension built fresh (`maturin develop
--release --locked`) from `c0cadd5` and checked as the compiled
`chronicler_agents.chronicler_agents` with real `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` classes.

| Check | Result |
| --- | --- |
| `cargo test --locked` | 917 passed, 0 failed, 2 ignored (20 new) |
| `pytest -m "not slow" -n 2` | 5,904 passed, 3 skipped, 526 subtests (2 new) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| no-Rust lane (fresh virtualenv without `chronicler_agents`) | 5,701 passed, 206 skipped (the 2 new native tests skip) |
| `scripts/run_python_oracle_checks.py` (PR #19's guard fix applied locally, not committed) | PASS: 1,892 passed, 10 skipped, 2 deselected; no native module loaded, no blocked I/O; pytest 66.8 s of the 110 s limit (the new tests are not in its selection) |
| agents-off identity against `f3eccec` (seeds 42 and 7, 150 turns) | 16 files, 0 differences |
| hybrid identity of the tally commit `efc2b06` against `f3eccec` | 18 files, 0 differences |

Not run: calibration, subset gates, golden roll-forward check and the full
gate (Phase B).

## Open items

- Phase B: merge `integrate/wave-6`, calibrate, subset gates on 42-61 and
  62-81, golden check, full gate.
- Phase B calibration: roots hold about seven in eight of the open gates,
  so they are the first lever; each move records the budget per driver
  before and after. A pulled married head moves the household (followers
  are 44% of migration units), which weighs on sloshing and on the
  community anchoring oracle.
- `mass_migration` events (8 or more agents leaving one region in one
  tick) are narrated as flight ("fled X for Y") whatever moved them, so a
  settlement wave reads as flight. Labelling them needs the dominant
  driver on each migration event (a new or repurposed agent-event column
  and household followers inheriting the lead's label), which changes
  `agent_events` content and hybrid bundle text; left for its own
  review.
