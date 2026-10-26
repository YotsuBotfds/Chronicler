# Bulk trade, mines and forests, crafts (2026-10)

Branch `feat/bulk-trade-crafts` from `main` `7fa364a` (PR #35, bundle
version 6). Three parts, each its own commit, on by default, in commit
order:

| Commit | Part | Restores the old behaviour |
| --- | --- | --- |
| `41a461c` | A. Bulk trade: merchant loads by mode of travel, filled against committed deliveries | `economy.{land,river,sea}_cargo_cap: 1`, `economy.cargo_fill: 0` |
| `8ac3f08` | C. Mines and forests on their own curves, not the farmland's | `economy.raw_reference_density: 0` |
| `f58076e` | B. Crafts: wares made in cities from raw materials, used everywhere, traded | `--no-cities` (no wares demand) |

All three change hybrid runs only: `--agents off` has no goods economy, so
the golden fixtures do not change (section 6).

Every run is Linux, Python 3.13, `PYTHONHASHSEED=0`, hybrid unless stated,
each arm a `git archive` export with its own virtualenv and a release
extension built fresh (`maturin develop --release --locked`; compiled
`AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified). SHA-256
of the extensions: `main` `21344bb6…02ef`, A `badb986f…a14c`, C
`8f6b4c3f…ae05b`, B (head) `fa666c6e…d2f7`. Probes: template worlds (8
regions, 4 civs) seeds 42-51 and procedural worlds (64 regions, 16 civs)
seeds 7-11, 200 turns, one read-only observer on every arm. Food
sufficiency is the economy's pre-consumption food over demand; a famine
episode is a run of three or more turns below 0.6. City import share is
the economy's food imports in city regions over their food demand. Herding
is the share of an origin's arrivals in a tick that go to its most-served
destination, over origins with two or more arrivals. Table values are pooled
over the runs; "±" follows the mean of the per-seed differences with its
standard error, which weighs seeds equally and can differ from the pooled
difference.

## Result

| | `main` | head |
| --- | ---: | ---: |
| food delivered / run, template; procedural | 372; 1,622 | 407; 2,024 |
| food delivered to famine regions / run, template; procedural | 154; 664 | 172; 801 |
| city import share of food demand, template; procedural | 1.04%; 1.36% | 1.43%; 1.81% |
| famine episode mean, template; procedural (turns) | 8.10; 5.31 | 7.97; 5.31 |
| famine episodes of 20+ turns, template; procedural | 10.7%; 2.2% | 10.4%; 1.6% |
| ore per worker at slot density < 0.1 / 0.75-1, template (x constant returns) | 1.16 / 1.11 | 1.75 / 0.56 |
| wares made / run, template; procedural | - | 161; 897 |
| merchant income per turn (world), template; procedural | 1.60; 6.49 | 2.25; 10.9 |
| herding, template; procedural | 0.775; 0.652 | 0.615; 0.535 |
| subset gates 42-61 / 62-81 | PASS / PASS | needs FAIL / PASS (section 4) |
| full gate (200 x 500) against `main`'s newest full report | PASS | PASS strict; NO REGRESSION |
| needs method 2: seeds; lower bound (full gate) | 182; 0.178 | 171; 0.157 |
| migration; rebellion; latest satisfaction (full gate) | 0.0610; 0.0308; 0.630 | 0.0600; 0.0327; 0.632 |
| extinct worlds (full gate) | 0 | 0 |

More food reaches cities and famine regions, but the gain is a fifth to a
quarter, not a change of scale: most trips are limited by the destination's
price, not by what the merchant can carry (section 1). Mines and forests
saturate on their own capacity. Wares are made where cities are and sold
everywhere, and merchants earn 40-70% more. The Part B subset 42-61 fails
the needs oracle; 62-81, 82-101, 102-121 and the full gate pass (section 4).

## 1. Part A: bulk trade

A merchant carried one load per trip (`MERCHANT_CARGO_CAP` 1). Now:

- **Capacity by mode of travel** (`merchant.rs`, `CargoConfig`). A trip
  carries up to the capacity of its narrowest leg: 2 loads overland (cart),
  5 on an edge between two regions on a common river (barge), 10 on a sea
  lane (ship). Goods that go by ship or barge go by cart on a land leg.
- **Filled against committed deliveries** (`plan_load`). Loads are added
  while the next one still earns the one-load price-gap threshold
  (`LOAD_MARGIN` = `MIN_TRIP_PROFIT` x `PRICE_GAP_SCALE`), with both prices
  read as if this tick's committed cargo (the market tally) and the load had
  arrived. A trip is made where a one-load trip was; one merchant does not
  overshoot a market; an exporter stops where its own price meets the
  market's. Bisection, 16 steps. A market whose food demand is not known yet
  takes one load.
- **Choice of market**: the destination where the cargo earns the most
  (the load times the mean of the gap before and after it; the one-load
  planner took the largest gap). Food first, as before; otherwise the best
  trip among raw materials, luxuries and wares. Ties to the lower region
  index.
- **Raids and blockades**: raiders seize the whole cargo, so a ship is a
  larger prize; blockades remove the lanes as before.
- Graphs built directly (tests, the legacy entry points) carry one load
  (`CargoConfig::LEGACY`); the simulator applies its configuration
  (`set_merchant_cargo_config`, sent from `agent_bridge.configure_merchant_cargo`
  only when a tuning key overrides it). No new random draws.

Measured, `main` against A:

| Measure | template `main` | A | procedural `main` | A |
| --- | ---: | ---: | ---: | ---: |
| food qty delivered / run | 372 | 405 | 1,622 | 1,969 (+347 ± 91) |
| ... to famine regions (below 0.6) | 154 (41%) | 183 (45%) | 664 (41%) | 842 (43%) |
| city import share of food demand | 1.04% | 1.31% (+0.34 ± 0.23 pp) | 1.36% | 1.68% (+0.28 ± 0.16 pp) |
| region-turns in famine | 22.0% | 22.7% (+1.3 ± 1.2 pp) | 18.8% | 19.0% (+0.1 ± 1.3 pp) |
| famine episode mean / p90 (turns) | 8.10 / 21 | 7.98 / 21 | 5.31 / 9 | 5.14 / 9 |
| famine episodes of 20+ turns | 10.7% | 11.4% | 2.2% | 1.8% |
| non-food qty delivered / run | 191 | 123 | 1,096 | 769 |
| completed trips / run | 576 | 514 | 2,796 | 2,672 |
| merchant income per turn (world) | 1.60 | 1.47 | 6.49 | 6.59 |
| merchant wealth gini, end | 0.585 | 0.566 | 0.584 | 0.575 |
| herding (an origin's top destination's share of its arrivals) | 0.775 | 0.693 | 0.652 | 0.556 |
| sea qty / run; share raided | 15; 0% | 3; 0% | 820; 1.8% | 898; 1.1% |
| final population | 188 | 169 (-20 ± 11) | 886 | 824 (-62 ± 61) |
| migration per agent-turn | 0.0602 | 0.0604 | 0.0671 | 0.0679 |

Template sea trade happens in two of ten worlds (seeds 44 and 46) and is
not a measure.

**What limits a load.** Part A's arrivals, procedural: below one load 56%,
one to two 18%, exactly two (the cart's capacity) 23%, more than two 2%.
Most trips stop below one load because the destination's price falls to
the origin's within the first load: a region eats 0.5 a head, most deficits
are a few loads, and neighbours are short in the same seasons (in template
worlds 13% of a short city's deficit could be covered from fed neighbours'
stocks). Two variants of Part A, procedural seeds 7-11:

| Capacities (land / river / sea) | 2 / 5 / 10 (A) | 2 / 5 / 2 | 10 / 10 / 10 |
| --- | ---: | ---: | ---: |
| sea qty / run | 898 | 872 | 943 |
| sea crossings over five loads | 1.1% | 0% | 4.5% |
| food qty delivered / run | 1,969 | 2,003 | 2,379 |
| city import share of food demand | 1.68% | 1.74% | 2.61% |
| region-turns in famine; episodes of 20+ | 19.0%; 1.8% | 20.4%; 1.7% | 17.6%; 0.9% |
| merchant income; herding | 6.59; 0.556 | 7.08; 0.568 | 6.19; 0.501 |

The ship's capacity binds on about 1% of crossings; cutting it to the
cart's moves sea trade 3%. The cart's capacity binds on a fifth of loads:
at 10 everywhere, city imports rise to 2.6% and long famines halve. Kept at
2 / 5 / 10 (a cart carries little; the gate ran on this); the variant is
an open item.

**Side effects.** Non-food quantities fall 30-36% with deliveries down
6-9%: a one-load trip carried a whole load into a thin raw-material or
luxury market, the fill rule stops where the prices meet (0.99 -> 0.70 a
delivery, template). Merchant income moves -8% / +2%. Herding falls: the
tally and the fill rule spread an origin's cargo over more markets.

## 2. Part C: mines and forests

The farmland curve (`farmland-climate.md`, E(L) = L (L_ref + L_h) / (L +
L_h), L_ref = 0.33 x capacity, half-saturation from the 0.5 elasticity) took
all farm labour, so miners and woodcutters crowded the fields: ore and timber
output per worker followed the farmland's crowding (about 1.1 x constant
returns at any density on the slot), and field hands' output followed the
mines'.

Now (`economy.rs` `split_labor_on_slot_curves`, `economy.py`
`slot_labor_curves`): farm labour is split by headcount, food first (the
food need read through the farm curve). Food labour works the farmland on
the farm curve. Each non-food slot's labour saturates on its own capacity,
with the farmland's form and reference density (`RAW_REFERENCE_DENSITY`
0.33):

- a mine (ore, precious) on its deposit: potential capacity x reserves left,
  floor 0.1 (an exhausted mine is worked, poorly);
- a forest on its woodland: potential capacity x forest cover / 0.9.

Optional economy columns `slot_labor_{ref,half}_{0,1,2}`; absent, the kernel
keeps the farm curve on all farm labour. The Python oracle
(`compute_allocated_production`) mirrors the kernel.

Measured, A against C (output per worker over constant returns, by headcount
on the slot over its capacity):

| | template A | C | procedural A | C |
| --- | ---: | ---: | ---: | ---: |
| timber per worker, density < 0.1 / 0.3-0.5 / > 1.5 | 1.19 / 1.11 / 1.14 | 1.70 / 0.94 / 0.17 | 1.26 / 1.11 / 1.09 | 1.70 / 0.92 / 0.18 |
| ore per worker, density < 0.1 / 0.3-0.5 / 1-1.5 | 1.14 / 1.08 / 0.96 | 1.74 / 0.93 / 0.43 | 1.25 / 0.98 / 1.10 | 1.75 / 0.98 / 0.44 |
| timber output / run | 104 | 125 (+20%) | 1,375 | 1,734 (+26%) |
| ore and precious output / run | 246 | 295 (+20%) | 1,595 | 1,973 (+24%) |
| food output / run | 15,623 | 16,457 (+5%) | 78,460 | 85,623 (+9%) |
| mean food sufficiency | 1.098 | 1.134 (+0.046 ± 0.025) | 1.116 | 1.184 (+0.073 ± 0.027) |
| region-turns in famine | 22.7% | 20.8% (-2.3 ± 1.2 pp) | 19.0% | 17.9% (-1.3 ± 0.8 pp) |
| final population | 169 | 181 (+12 ± 10) | 824 | 906 (+82 ± 51) |
| migration per agent-turn | 0.0604 | 0.0576 (-0.0027 ± 0.0021) | 0.0679 | 0.0660 (-0.0017 ± 0.0015) |

Sparse mines and forests yield more, crowded ones far less; most of them are
sparse, so raw output rises a fifth. Field hands no longer pay for the
miners' crowding: food output +5-9%.

## 3. Part B: crafts

There is no artisan occupation (farmer, soldier, merchant, scholar, priest),
and adding one would move every occupation share and the needs it feeds.
Wares are made by a city's civilian residents, at the rate the existing
`craft_raw_demand` sets (0.1 raw material per civilian resident a turn,
`city-markets.md`):

- **Good.** A ninth good, `crafts` (wares: tools, cloth, pottery), slot 8,
  in a fourth category `craft`; no transit decay, 1% wear a turn in store;
  not food.
- **Making.** A city's crafts work the raw materials on hand (timber and
  ore: stock and this turn's output, less this tick's merchant departures),
  pro rata, into wares, one load of wares per load of raw material, up to
  the crafts' raw demand (`economy.rs` Phase A). Farmer income ignores
  wares.
- **Use.** Every region's people want 0.01 wares a head a turn
  (`CRAFT_DEMAND_PER_CAPITA`, a fiftieth of the food ration by volume;
  `craft_demand`, sent with cities on). Wares are used up to that demand.
  Sufficiency (stock over demand, 0-2) restores the material need:
  0.006 x min(1, sufficiency) x deficit a turn (`MATERIAL_RESTORE_CRAFTS`;
  food restores 0.018 x min(1.5, sufficiency) x deficit).
- **Trade.** Merchants carry wares by price like any good. Trade packets do
  not advertise wares (every region without a city would).
- **Commerce.** A city's share (by size) of the wares its region made raises
  its market access: + wares / food demand, at most 0.3 (`cities._commerce`).

Schemas and loading: the economy and region schemas carry
`stockpile_crafts`, `market_{demand,supply}_craft`, `craft_output`,
`craft_sufficiency`, `imports_craft` and `stockpile_craft`. The economy
input's `stockpile_crafts`, `craft_demand` and the region batch's
`craft_sufficiency` are optional, so older batches read no wares. A
region's stock gains a `crafts` key only once it holds wares, so runs with
`--no-cities` write the same stock keys as before (section 5). Python goods
maps (`FIXED_GOODS`, `ALL_GOODS`, `CATEGORY_GOODS`, decay tables,
`SHOCK_CATEGORIES` keep the three old categories); market tuples have four
entries and older three-entry ones are padded. City state gains `crafts`
(default 0). The bundle carries goods by name, so its format is unchanged;
the viewer's Cities tab gains a Wares column ("-" for older bundles).

Measured, C against B:

| | template C | B | procedural C | B |
| --- | ---: | ---: | ---: | ---: |
| wares made / run; per city region-turn | - | 161; 0.30 | - | 897; 0.37 |
| wares sufficiency, city regions / elsewhere | - | 0.92 / 0.27 | - | 1.37 / 0.21 |
| wares deliveries / run (loads) | - | 137 (35) | - | 657 (227) |
| raw materials delivered to city regions / run | 41 | 144 | 262 | 780 |
| non-food deliveries / run | 176 | 315 | 1,050 | 1,676 |
| merchant income per turn (world) | 1.39 | 2.25 | 7.11 | 10.9 |
| herding | 0.682 | 0.615 | 0.575 | 0.535 |
| city commerce, mean | 1.062 | 1.051 | 1.062 | 0.996 |
| wares term in city access: mean; p90 | - | 0.015; 0.047 | - | 0.022; 0.059 |
| food qty delivered / run | 375 | 407 | 2,045 | 2,024 |
| mean food sufficiency | 1.134 | 1.119 (-0.008 ± 0.020) | 1.184 | 1.128 (-0.058 ± 0.018) |
| region-turns in famine | 20.8% | 21.8% (+0.9 ± 1.0 pp) | 17.9% | 20.7% (+2.9 ± 1.7 pp) |
| famine episode mean (turns) | 8.65 | 7.97 | 5.11 | 5.31 |
| final population | 181 | 185 (+4 ± 9) | 906 | 972 (+66 ± 74) |
| migration per agent-turn | 0.0576 | 0.0597 | 0.0660 | 0.0653 |
| occupation shares (farmer / merchant) | 0.524 / 0.139 | 0.523 / 0.141 | 0.548 / 0.130 | 0.549 / 0.131 |

Cities pull raw materials (three to three and a half times the deliveries
to city regions) and sell wares outward; merchants earn half again as much.
The wares term adds 1.5-2% to city commerce on average, less than other
changes take away (an open item). In procedural worlds mean food sufficiency falls 0.06: more
people (+7%, within noise) and merchants' trips go to wares and raw
materials (food deliveries -5%).

## 4. Gates

Subset gates: 20 seeds x 200 turns, hybrid, `--parallel 1`, each part's
exported tree, comparator against the previous part's own subset report
(`main` for A). In the subset only community, needs and cohort are required.

| 42-61 | `main` | A | C | B |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | PASS; NO REGRESSION | PASS; NO REGRESSION | **needs FAIL; REGRESSION** |
| needs: net; lower bound; seeds (of 12 needed) | 0.225; 0.167; 18 | 0.123; 0.051; 15 | 0.109; 0.031; 15 | 0.031; -0.053; 13 |
| material pairs C / D | 213 / 111 | 182 / 128 | 187 / 155 | 218 / 207 |
| cohort; community; era | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 |
| artifacts; arcs | PASS; PASS | PARTIAL; PASS | PASS; PASS | PASS; PASS |
| regression | PASS | PASS | FAIL (civ_survival) | PASS |
| satisfaction; latest | 0.603; 0.618 | 0.597; 0.613 | 0.605; 0.622 | 0.602; 0.609 |
| migration; rebellion | 0.0659; 0.0364 | 0.0667; 0.0362 | 0.0648; 0.0355 | 0.0664; 0.0410 |
| final population min / median; extinct | 95 / 180; 0 | 80 / 163; 0 | 84 / 190; 0 | 96 / 181; 0 |

| 62-81 | `main` | A | C | B |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | PASS; NO REGRESSION | PASS; NO REGRESSION | PASS; NO REGRESSION |
| needs: net; lower bound; seeds | 0.158; 0.073; 14 | 0.160; 0.079; 14 | 0.167; 0.088; 14 | 0.128; 0.058; 13 |
| artifacts; arcs | PASS; PASS | PASS; PASS | PASS; PASS | PARTIAL; PASS |
| regression | FAIL (rebellion, civ_survival) | FAIL (civ_survival) | FAIL (rebellion, civ_survival) | FAIL (rebellion, civ_survival) |
| satisfaction; latest | 0.611; 0.621 | 0.614; 0.628 | 0.611; 0.619 | 0.612; 0.622 |
| migration; rebellion | 0.0596; 0.0178 | 0.0624; 0.0253 | 0.0615; 0.0195 | 0.0598; 0.0187 |
| final population min / median; extinct | 135 / 175; 0 | 105 / 176; 0 | 137 / 179; 0 | 136 / 193; 0 |

The subset's regression oracle is informational; the 62-81 rebellion and
civ-survival failures are `main`'s own.

**The Part B needs failure in 42-61.** The seed fraction holds (13 of the
12 needed); the pooled lower bound does not (-0.053). Material pairs carry
it (218 concordant against 207 discordant; C 187 / 155). Checked:

| Needs (method 2) | C | B | B without the wares' material term |
| --- | --- | --- | --- |
| 42-61: net; lower bound; seeds | 0.109; 0.031; 15 | 0.031; -0.053; 13 | 0.040; -0.043; 13 |
| 82-101 | 0.119; 0.039; 14 | 0.211; 0.138; 16 | |
| 102-121 | 0.112; 0.041; 13 | 0.202; 0.106; 14 | |

Setting `MATERIAL_RESTORE_CRAFTS` to 0 leaves 42-61 failing, so the wares'
restoration of the material need is not the cause; B is above C in 82-101
and 102-121, and the full gate passes. Read as a draw of 20 seeds from a
lower pooled concordance (full gate: 0.194 -> 0.173), not as a failure of
the mechanism; recorded rather than tuned away.

Full gate: 200 seeds x 500 turns, hybrid, `--parallel 3`, from the head's
exported tree, against `main`'s newest full report (`feat/farmland-climate`
`84bfb44`; bundle version 6 changed no simulation output). PR #36 (needs
calibration) had not merged; its report is not `main`'s. 2,222 s.

| Oracle | `main` (farmland head) | **head** `f58076e` |
| --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** |
| community; cohort; era (seeds) | 200; 200; 200 (1 silent) | 200; 200; 200 (1 silent) |
| needs (method 2): seeds; net; lower bound; informative pairs | 182; 0.194; 0.178; 16,492 | 171; 0.173; 0.157; 17,612 |
| arcs (three types; families) | 170; 6 | 164; 6 |
| artifacts (status; creation; loss) | PASS; 1.51; 6.0% | PASS; 1.64; 6.0% |
| regression | PASS (strict) | PASS (strict) |
| satisfaction mean; latest (ceiling 0.65) | 0.617; 0.630 | 0.620; 0.632 |
| migration per agent-turn (strict floor 0.05) | 0.0610 | 0.0600 |
| rebellion per agent-turn (0.02-0.08) | 0.0308 | 0.0327 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 46 / 179 / 325 | 37 / 188 / 331 |

## 5. Identity and compatibility

Each pair of exported trees with its own extension, every output file
compared (`chronicle_bundle.json` without `generated_at`; with a tuning file,
state and bundle without the run's record of it):

| Check | Worlds | Result |
| --- | --- | --- |
| A with `land/river/sea_cargo_cap: 1`, `cargo_fill: 0` against `main` | template 42, 43 (200 turns); procedural 7 (100 turns) | 42 files, 0 differ |
| C with `raw_reference_density: 0` against A | same | 42 files, 0 differ |
| B against C, both `--no-cities` | same | 42 files, 0 differ |
| B against `main`, `--agents off` | template 42, 43 (200 turns) | 18 files, 0 differ |

- A state and a bundle written by `main` (seed 44, 60 turns, hybrid, cities
  on) load in the head: no wares keys in old stocks, old cities read
  `crafts` 0, the version-6 bundle restores (60 snapshots); a resumed run
  (`--agents off`) reaches turn 80. The bundle stores goods by name, so its
  format is unchanged; the viewer shows "-" for wares in older bundles.
- Region identity is the index in `world.regions` throughout; no IDs added.

## 6. Golden fixtures

Unchanged. The golden oracles run `--agents off`, where none of the three
parts runs (the goods economy runs with agents only; benchmark cities are
off), and the agents-off identity above is byte for byte. No `ORACLE_CHAIN`
link.

## 7. Tick time and bundle size

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700, 20 warm-up and 8 timed turns, two repeats, one child at a
time, `main` and head trees each with its own release extension, shared
4-core host. Medians per run, wall / process CPU, in ms:

| alive (`main`; head) | | `main` | head |
| --- | --- | ---: | ---: |
| 22,110; 23,380 | Rust tick | 107, 104 / 270, 272 | 111, 103 / 271, 265 |
| | whole turn | 174, 161 / 334, 333 | 178, 169 / 389, 371 |
| 50,360; 54,494 | Rust tick | 423, 404 / 1,421, 1,324 | 448, 415 / 1,401, 1,325 |
| | whole turn | 560, 513 / 1,788, 1,728 | 557, 525 / 1,805, 1,718 |

Rust tick CPU per alive agent: 12.2-12.3 against 11.3-11.6 us at about 22k,
26.3-28.2 against 24.3-25.7 us at about 52k. Whole-turn CPU per agent at
22k: 15.1 against 15.9-16.6 us (+5-10%, not profiled); at 52k 34.3-35.5
against 31.5-33.1 us. The worlds diverge from the first turn (the head holds
6-8% more agents), so the arms are not the same work. New native work: a
16-step bisection per market and cargo a merchant considers, three slot
curves per region and the wares step in the economy.

Bundle guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, `--agents off`): native 7.89 MB (8,276,564
bytes), no-Rust 8.61 MB (9,029,934 bytes), both the same as `main` (agents
off is byte-identical); guard 10.5 MB.

## 8. Verification

Head `f58076e` plus this document, extension built fresh (SHA-256
`fa666c6e…d2f7`, the same as the head's exported tree), shared 4-core host.

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 982 passed, 2 ignored (`main`: 969) |
| `pytest -m "not slow" -n 2` | 6,181 passed, 3 skipped, 526 subtests (`main`: 6,163) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (virtualenv without `chronicler_agents`) | 5,953 passed, 231 skipped, 526 subtests (`main`: 5,940 / 226) |
| `scripts/run_python_oracle_checks.py` | PASS in 82.7 s: 2,137 passed, 33 skipped; largest chunk `systems-2` 31.6 s of 110 s |
| Viewer (`npm test`, `npm run lint`, `npm run build`) | 281 tests in 37 files (`main`: 280), lint clean, build passes |
| Old state, cities and bundle | load and resume (section 5) |

New tests: `tests/test_bulk_trade.py` (4, native), `tests/test_mines_forests.py`
(7), `tests/test_crafts.py` (7), in the oracle lane's `systems-1` and
`systems-2` chunks; Rust `merchant` (leg and path capacity, the fill
margin, trips where one-load trips were, the market where cargo earns most,
the tally against the next merchant, unknown demand and legacy graphs,
wares travel but are not advertised), `economy` (mines saturate on their
deposit, the inverse curve, food first through the curve, wares from raw
materials, short raw, none; farmer income and merchant departures), `needs`
(the wares' material term); viewer `SystemsPanel` (Wares column).

Changed expectations:

* Part A. `scripts/mutual_aid_adversarial.py` pins one-load trade (its
  convoys answer one-load merchants).
* Part C. `test_maritime.py`: the raid run is seed 10, 40 turns (26
  crossings, about 12 loads lost; seed 7 now crosses twice and loses none).
  `test_economy.py`: mock regions get forest cover and reserves.
  `test_economy_bridge.py`: the economy batch has 26 columns (the six slot
  curve columns).
* Part B. `test_economy_bridge.py`: 27 columns, nine goods.
  `test_economy_m43a.py`, `test_economy_m43b.py`: nine goods, four
  categories. `test_city_markets.py`: market tuples of four, the
  `craft_demand` column. `scripts/qualify_third_wave.py`: its goods,
  survival and decay tables include wares. Rust tests: nine-good stockpile
  literals; the FFI commitments test reads `2 x NUM_GOODS` rows.

## 9. Open items

* **Thin markets, not capacity, limit trade.** Most loads stop under one
  unit; the cart's capacity binds on a fifth, the ship's on 1%. Larger
  capacities (10 everywhere: city imports 2.6%, long famines halved) or
  state grain (the annona, charity convoys) would need their own gate.
* **Non-food quantities fall with Part A** (loads stop where prices meet);
  Part B's wares and raw-material trips more than restore them.
* **Wares in commerce** add 1.5-2%: wares are counted by volume against food
  demand. A price for wares would weigh them properly.
* **Tools**: wares do not raise farm or mine output; no artisan occupation;
  no guilds (left to `feat/movements-2`).
* **Needs subset 42-61 with Part B** fails on the pooled lower bound
  (section 4); the full gate passes.
* **PR #36** (needs calibration) was open; after it merges the branch needs
  `main` merged in and its gates run again against its full report.
