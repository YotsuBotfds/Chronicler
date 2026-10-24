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

Young people leave land that is full for land of the same realm that is
not: inheritance and holding sizes push the surplus generation out
(internal colonisation, frontier settlement). In the model carrying
capacity stands for the land.

- Gate: home at `FRONTIER_SOURCE_MIN_RATIO` 0.85 of capacity or more; the
  neighbour at least `FRONTIER_MIN_GAP` 0.30 emptier (share of capacity);
  the neighbour fed (`FRONTIER_MIN_FOOD`: food sufficiency 1.0).
- Pull: `FRONTIER_PULL` 0.30 x ramp(gap, 0.30, 0.70).
- The food gate keeps settlers out of regions with no stores. An empty
  region has none (sufficiency is stores over demand), and an agent in a
  region under 0.6 writes a famine memory next tick: settling there would
  start a famine-memory return.
- Self-limiting: the wave stops when home falls under 0.85 or the gap under
  0.30. In the Rust multi-tick test (`tests/test_healthy_migration.rs`)
  16 of 40 agents move in five turns, home drops to 0.80 and nobody moves
  back.

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
`PYTHONHASHSEED=0`, through the output-neutral observer; base is `efc2b06`
(the tally on `f3eccec` behavior), branch `ba7a9c8`; from turn 100.

| | base | branch |
| --- | ---: | ---: |
| migrations per run (events) | 2,927 | 3,376 |
| migration per agent-turn (pooled) | 0.0449 | 0.0489 |
| paired by seed (mean of seeds) | 0.0429 | 0.0474 (+0.0045 +- 0.0030, up/down 14/5) |
| household followers | 43.6% | 43.6% |
| famine memory | 30.9% | 32.3% |
| persecution memory / live persecution | 9.1 / 3.4% | 7.2 / 2.9% |
| opportunity terms | 11.0% | 11.4% |
| frontier / wage / chain | - | 0.2 / 0.4 / 0.1% |
| gate open, before roots (per evaluated agent-turn) | - | 2.44 / 4.26 / 1.01% |
| pull beyond roots | - | 0.29 / 0.54 / 0.10% |
| reverse flow on the next turn (share of migrations) | 18.7% | 17.2% |
| agent back where it came from within 10 turns | 23.6% | 22.3% |
| region pairs alternating 3+ turns (20 runs) | 208 | 217 |

- The drivers act rarely here, and roots hold about seven in eight of the
  open gates. Histories diverge from the first changed move, so the
  per-seed differences are mostly chance (one world is identical: no gate
  ever opened beyond roots).
- **The frontier is unfed.** Among young adults (20-30) with a ruled home,
  23% sit in a home at 0.85 of capacity or more with a neighbour of the
  same realm at least 0.30 emptier; for 0.2% of them that neighbour is fed
  (sufficiency 1.0), and for 1.9% it holds 0.4 (four seeds, 300 turns, base).
  Regions are empty because they cannot feed people: food does not move
  between regions. Food logistics is expected to change this, so Phase B
  calibrates on the merged world.
- Sloshing does not rise: in the base nearly a quarter of migrants are
  back where they came from within ten turns (famine-memory churn); the
  branch is at or below it on the per-migrant checks and within chance on
  alternating pairs.
- Agents-off identity, base (`f3eccec`, its build) against the branch
  (`ba7a9c8`, its build), seeds 42 and 7, 150 turns: 16 files,
  0 differences.

### Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, 3 warm-up and 8
timed turns, two repeats, one child at a time, release builds of `f3eccec`
and `ba7a9c8`, shared 4-core machine (medians per run):

| agents | base: tick wall / CPU | branch: tick wall / CPU |
| ---: | ---: | ---: |
| ~21,800 | 185, 195 / 310, 297 ms | 223, 204 / 317, 317 ms |
| ~53,200 | 1,077, 1,060 / 1,847, 1,788 ms | 1,058, 1,074 / 1,864, 1,749 ms |

Within noise at 53k; at most about 3% more CPU at 22k. The per-agent work
is one pass over at most 8 bonds (one id lookup each, in the map the
household code already builds) and a few comparisons per neighbour, with
no allocation; per-region peer wealth and the internal-neighbour flag are
computed once per tick in the existing region-stats pass.

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
| `FRONTIER_MIN_FOOD` | 1.0 | settle only where stores cover demand |
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
  `frontier`, `wage`, `chain`) and `open_<driver>` (agents whose chosen
  target carries that pull beyond their roots). Production Python does not
  read it, so bundles do not change.
- Observer and tools (run directory, not committed): `mtrace.py` records
  the tally, household followers and migration events per tick;
  `budget.py` prints the budget with one row per driver, household
  followers as their own row, and three sloshing checks (reverse flow on
  the next turn, an agent returning within 10 turns, region pairs
  alternating 3 or more turns).

## Tests

- Rust, `migration_drivers`: roots by age, marriage and home bonds;
  `net_of_roots`; mobility eligibility (dependants, unruled regions); the
  frontier, wage and chain gates one condition at a time (crowding, gap,
  food, foreign and unclaimed targets; occupations, peers, room, wealth
  floor; settled emigrants, natives, displacement, spouse, home bonds,
  rivals, weak bonds, borders); the budget split.
- Rust, `behavior`: frontier settlers leave a full region; elders,
  dependants and foreign targets draw none; the pull counts in the target
  choice but not in the opportunity; memory and need pushes by type.
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
--release --locked`) from `b510077` and checked as the compiled
`chronicler_agents.chronicler_agents` with real `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` classes.

| Check | Result |
| --- | --- |
| `cargo test --locked` | 915 passed, 0 failed, 2 ignored (18 new) |
| `pytest -m "not slow" -n 2` | 5,904 passed, 3 skipped, 526 subtests (2 new) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| no-Rust lane (fresh virtualenv without `chronicler_agents`) | 5,701 passed, 206 skipped (the 2 new native tests skip) |
| `scripts/run_python_oracle_checks.py` (PR #19's guard fix applied locally, not committed) | PASS: 1,892 passed, 10 skipped, 2 deselected; no native module loaded, no blocked I/O; pytest 71.9 s of the 110 s limit (the new tests are not in its selection) |
| agents-off identity against `f3eccec` | 16 files, 0 differences |
| hybrid identity of the tally commit against `f3eccec` | 18 files, 0 differences |

Not run: calibration, subset gates, golden roll-forward check and the full
gate (Phase B).

## Open items

- Phase B: merge `integrate/wave-6`, calibrate, subset gates on 42-61 and
  62-81, golden check, full gate.
- `mass_migration` events (8 or more agents leaving one region in one
  tick) are narrated as flight ("fled X for Y") whatever moved them. A
  settlement wave would be narrated as flight too; narration should read
  the driver. Not changed here.
