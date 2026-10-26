# Bulk trade, mines and forests, crafts (2026-10)

Branch `feat/bulk-trade-crafts` from `main` `7fa364a` (PR #35, bundle
version 6), merged without rebase with `main` `b5d41af` (PR #36, needs
calibration) and `f5425dc` (PR #37, movements on by default); head
`21c0e7e`. Three parts, each its own commit, on by default, in commit
order:

| Commit | Part | Restores the old behaviour |
| --- | --- | --- |
| `41a461c` | A. Bulk trade: merchant loads by mode of travel, filled against committed deliveries | `economy.{land,river,sea}_cargo_cap: 1`, `economy.cargo_fill: 0` |
| `8ac3f08` | C. Mines and forests on their own curves, not the farmland's | `economy.raw_reference_density: 0` |
| `f58076e` | B. Crafts: wares made in cities from raw materials, used everywhere, traded | `--no-cities` (no wares demand; no cities either) |

All three change hybrid runs only: `--agents off` has no goods economy, so
the golden fixtures do not change (section 6).

Every run is Linux, Python 3.13, `PYTHONHASHSEED=0`, hybrid unless stated,
each arm a `git archive` export with its own virtualenv and a release
extension built fresh (`maturin develop --release --locked`; compiled
`AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified). SHA-256
of the extensions: `main` `7fa364a` `21344bb6…02ef`, A `badb986f…a14c`, C
`8f6b4c3f…ae05b`, B `fa666c6e…d2f7`; `main` `f5425dc` `028c1fd1…c52a`,
head `21c0e7e` `cf109460…cd90e`. Probes: template worlds (8
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

The head against `main` `f5425dc`, each from its exported tree, probes of
section 1's worlds; per-part tables (sections 1-3) were measured before the
merges, each part against the one before it.

| | `main` `f5425dc` | head `21c0e7e` |
| --- | ---: | ---: |
| food delivered / run, template; procedural | 382; 1,629 | 403; 2,028 (+399 ± 142) |
| food delivered to famine regions / run, template; procedural | 155; 705 | 189; 893 |
| city import share of food demand, template; procedural | 1.12%; 1.38% | 1.41%; 2.11% (+0.68 ± 0.20 pp) |
| famine episode mean, template; procedural (turns) | 7.98; 5.28 | 7.82; 4.99 |
| famine episodes of 20+ turns, template; procedural | 10.6%; 1.4% | 10.3%; 1.2% |
| region-turns in famine, template; procedural | 23.0%; 18.7% | 21.8%; 18.8% |
| ore per worker at slot density < 0.1 / 0.5-0.75, template (x constant returns) | 1.15 / 1.03 | 1.75 / 0.71 |
| timber; ore and precious output / run, template | 85; 247 | 115; 419 |
| wares made / run, template; procedural | - | 174; 929 |
| non-food qty delivered / run, template; procedural | 194; 1,046 | 260; 1,328 |
| merchant income per turn (world), template; procedural | 1.61; 6.52 | 2.55; 10.4 |
| herding, template; procedural | 0.800; 0.653 | 0.635; 0.535 |
| final population, template; procedural | 182; 868 | 176 (-6 ± 9); 803 (-64 ± 40) |
| subset gates 42-61 / 62-81 | PASS / PASS | PASS / PASS; NO REGRESSION |
| full gate (200 x 500) against the movements-on report | PASS | PASS strict; NO REGRESSION |
| needs method 2: seeds; lower bound (full gate) | 188; 0.192 | 190; 0.177 |
| migration; rebellion; latest satisfaction (full gate) | 0.0629; 0.0409; 0.631 | 0.0615; 0.0388; 0.627 |
| extinct worlds (full gate) | 0 | 0 |

More food reaches cities and famine regions, but the gain is a fifth to a
half, not a change of scale: most trips are limited by the destination's
price, not by what the merchant can carry (section 1). Mines and forests
saturate on their own capacity. Wares are made where cities are and sold
everywhere, and merchants earn 60% more. Before the merges the three parts
failed the needs oracle in subset 42-61 (lower bound -0.05); after the
needs-calibration merge 42-61 failed on the seed fraction (11 of 12); the
head passes both subsets and every full gate (section 4).

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

Subset gates: 20 seeds x 200 turns, hybrid, `--parallel 1`; full gates: 200
seeds x 500 turns, hybrid, `--parallel 3`; each from an exported tree with
its own extension. In the subset only community, needs and cohort are
required; its regression oracle is informational.

### 4.1 The head, after both merges

The head `21c0e7e` (extension `cf109460…cd90e`) against `main` `f5425dc`
(movements on by default): subsets against `main`'s own subset reports from
its exported tree; the full gate against the movements-on full report
(`feat/movements-2`), 2,337 s.

| Subset | `main` 42-61 | head 42-61 | `main` 62-81 | head 62-81 |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** | PASS | **PASS; NO REGRESSION** |
| needs: net; lower bound; seeds (of 12 needed) | 0.152; 0.075; 15 | 0.163; 0.081; 14 | 0.178; 0.110; 15 | 0.152; 0.090; 17 |
| cohort; community; era | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 |
| artifacts; arcs | PASS; PASS | PARTIAL; PASS | PARTIAL; PASS | PARTIAL; PASS |
| regression | PASS | FAIL (civ_survival) | FAIL (civ_survival) | FAIL (civ_survival) |
| satisfaction; latest | 0.599; 0.619 | 0.603; 0.618 | 0.610; 0.625 | 0.614; 0.622 |
| migration; rebellion | 0.0689; 0.0489 | 0.0657; 0.0418 | 0.0621; 0.0252 | 0.0612; 0.0266 |
| final population min / median; extinct | 76 / 182; 0 | 102 / 167; 0 | 127 / 189; 0 | 116 / 186; 0 |

| Full gate | `main` (movements on) | **head** `21c0e7e` |
| --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** |
| community; cohort; era (seeds) | 200; 200; 200 (0 silent) | 200; 200; 200 (0 silent) |
| needs (method 2): seeds; net; lower bound; informative pairs | 188; 0.207; 0.192; 19,775 | 190; 0.191; 0.177; 19,746 |
| arcs (three types; families) | 164; 6 | 158; 6 |
| artifacts (status; creation; loss) | PASS; 1.62; 6.6% | PASS; 1.68; 6.0% |
| regression | PASS (strict) | PASS (strict) |
| satisfaction mean; latest (ceiling 0.65) | 0.616; 0.631 | 0.616; 0.627 |
| migration per agent-turn (strict floor 0.05) | 0.0629 | 0.0615 |
| rebellion per agent-turn (0.02-0.08) | 0.0409 | 0.0388 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 40 / 177 / 342 | 78 / 185 / 331 |

### 4.2 Each part, before the merges

Comparator against the previous part's own subset report (`main` `7fa364a`
for A).

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

The 62-81 rebellion and civ-survival failures are `main`'s own.

**The Part B needs failure in 42-61** (before the merges; the head passes,
section 4.1). The seed fraction holds (13 of the
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

Full gate of the three parts, against `main` `7fa364a`'s newest full report
(`feat/farmland-climate` `84bfb44`; bundle version 6 changed no simulation
output), 2,222 s:

| Oracle | `main` (farmland head) | B `f58076e` |
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

### 4.3 After merging needs calibration

`ec246ab` merges `main` `b5d41af` (PR #36); its tree is that of a trial
merge with the PR's head `e1b6a13` gated before the PR landed. Conflicts:
the material-need block (the wares' term beside the new dearth and famine
pressures; `MATERIAL_RESTORE_CRAFTS` stays 0.006 against food's new 0.115)
and the maritime raid test's seed (13). Subsets against `e1b6a13`'s own;
full gate against the needs-calibration full report, 1,863 s.

| | needs-cal 42-61 | merged 42-61 | needs-cal 62-81 | merged 62-81 | needs-cal full | merged full |
| --- | --- | --- | --- | --- | --- | --- |
| gate; comparator | PASS | needs FAIL; REGRESSION | PASS | PASS; NO REGRESSION | PASS | PASS strict; NO REGRESSION |
| needs: net; lower bound; seeds | 0.228; 0.170; 18 | 0.118; 0.042; **11** | 0.155; 0.097; 14 | 0.170; 0.077; 14 | 0.209; 0.195; 190 | 0.209; 0.194; 182 |
| satisfaction latest | 0.614 | 0.613 | 0.619 | 0.636 | 0.622 | 0.628 |
| migration; rebellion | 0.0705; 0.0521 | 0.0666; 0.0455 | 0.0614; 0.0229 | 0.0607; 0.0215 | 0.0626; 0.0385 | 0.0616; 0.0383 |
| extinct | 0 | 0 | 0 | 0 | 0 | 0 |

The merged 42-61 subset fails the seed fraction (11 of 12) with a positive
lower bound; the full gate's seeds 42-61 at 500 turns have net concordance
0.155 and 17 of 20 seeds with the expected sign (needs calibration 0.216,
20). After the movements merge 42-61 passes (section 4.1). In full gates the
three parts lower pooled needs concordance by 0.00-0.02 (0.194 -> 0.173,
0.209 -> 0.209, 0.207 -> 0.191).

## 5. Identity and compatibility

Each pair of exported trees with its own extension, every output file
compared (`chronicle_bundle.json` without `generated_at`; with a tuning file,
state and bundle without the run's record of it):

| Check | Worlds | Result |
| --- | --- | --- |
| A with `land/river/sea_cargo_cap: 1`, `cargo_fill: 0` against `main` `7fa364a` | template 42, 43 (200 turns); procedural 7 (100 turns) | 42 files, 0 differ |
| C with `raw_reference_density: 0` against A | same | 42 files, 0 differ |
| B against C, both `--no-cities` | same | 42 files, 0 differ |
| B against `main` `7fa364a`, `--agents off` | template 42, 43 (200 turns) | 18 files, 0 differ |
| head against `main` `f5425dc`, `--agents off` | template 42, 43 (200 turns) | 18 files, 0 differ |
| head with all three switches off (the four cargo keys, `raw_reference_density: 0`, `--no-cities`) against `main` `f5425dc` `--no-cities` | template 42 (120 turns); procedural 7 (80 turns) | 32 files, 0 differ |

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
time, each tree with its own release extension, shared 4-core host (another
agent's runs alongside, so wall time is noisy). Medians per run, wall /
process CPU, in ms:

| alive (`main`; head) | | `main` | head |
| --- | --- | ---: | ---: |
| head `21c0e7e` against `main` `f5425dc` | | | |
| 23,060; 22,440 | Rust tick | 183, 214 / 289, 298 | 150, 195 / 259, 268 |
| | whole turn | 306, 332 / 406, 424 | 253, 306 / 359, 377 |
| 50,462; 55,571 | Rust tick | 779, 778 / 1,327, 1,292 | 666, 673 / 1,248, 1,264 |
| | whole turn | 1,006, 1,083 / 1,691, 1,616 | 939, 987 / 1,669, 1,770 |
| B `f58076e` against `main` `7fa364a` | | | |
| 22,110; 23,380 | Rust tick | 107, 104 / 270, 272 | 111, 103 / 271, 265 |
| | whole turn | 174, 161 / 334, 333 | 178, 169 / 389, 371 |
| 50,360; 54,494 | Rust tick | 423, 404 / 1,421, 1,324 | 448, 415 / 1,401, 1,325 |
| | whole turn | 560, 513 / 1,788, 1,728 | 557, 525 / 1,805, 1,718 |

Rust tick CPU per alive agent, head against `main` `f5425dc`: 11.6-11.9
against 12.6-12.9 us at about 23k, 22.5-22.8 against 25.6-26.3 us at about
52k; whole-turn CPU per agent 16.0-16.8 against 17.6-18.4 us and 30.0-31.9
against 32.0-33.5 us. Before the merges, at 22k, whole-turn CPU per agent
was 5-10% above `main` (15.9-16.6 against 15.1 us; not profiled). The worlds
diverge from the first turn, so the arms are not the same work. New native
work: a 16-step bisection per market and cargo a merchant considers, three
slot curves per region and the wares step in the economy.

Bundle guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, `--agents off`), head: native 7.89 MB (8,277,349
bytes), no-Rust 8.61 MB (9,030,719 bytes), the same as `main` `f5425dc`
(agents off is byte-identical); guard 10.5 MB.

## 8. Verification

Head `21c0e7e` plus this document, extension built fresh (SHA-256
`cf109460…cd90e`, the same as the head's exported tree), shared 4-core host.

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 995 passed, 2 ignored (B before the merges: 982; `main` `7fa364a`: 969) |
| `pytest -m "not slow" -n 2` | 6,196 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (virtualenv without `chronicler_agents`) | 5,966 passed, 233 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS in 96.2 s: 2,147 passed, 33 skipped; largest chunk `systems-2` 37.3 s of 110 s |
| Viewer (`npm test`, `npm run lint`, `npm run build`) | 292 tests in 38 files, lint clean, build passes |
| Old state, cities and bundle (written by `main` `7fa364a`) | load and resume (section 5) |

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
  crossings, about 12 loads lost; seed 7 now crosses twice and loses none);
  after the needs-calibration merge seed 13 (76 crossings, about 11 loads
  lost; seeds 7, 8 and 11 lose none, seed 10 a fifth of a load).
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
* **Needs concordance** falls 0.00-0.02 in full gates with the three parts,
  and subset 42-61 failed twice before the movements merge (section 4); the
  head passes.
* **Wares' material weight** stays 0.006, a third of food's weight before
  the needs calibration raised food's to 0.115; not recalibrated.
