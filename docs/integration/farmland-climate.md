# Farmland and regional climate (2026-10)

Branch `feat/farmland-climate` from `feat/hunger-mortality` `d720fce`,
fast-forwarded to `main` `617a87e` (PR #32, hunger mortality) and `82c131b`
(PR #33, needs oracle method 2). Three **corrections**, on by default, each
with a tuning key that restores the old behaviour for tests and comparisons
(section 9). The hunger work ([hunger-mortality.md](hunger-mortality.md))
held its magnitudes at the low end because famines could not end: farm
labour had constant returns, and the climate phase put whole worlds in
famine at once.

Commits: `1893a62` diminishing returns, regional climate and the hunger
magnitudes; `84bfb44` the golden oracles; this document and the ledger.

Every run is Linux, Python 3.13, `PYTHONHASHSEED=0`, hybrid unless stated,
with a native extension built fresh (`maturin develop --release --locked`)
and its compiled `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
verified. Template worlds are the default 8 regions and 4 civs, seeds 42-51;
procedural ones 64 regions and 16 civs (`--worldgen procedural`), seeds 7-11;
200 turns. Base is `main` `82c131b` with its own extension (SHA-256
`5d58881c…bf21da`); head `84bfb44` (extension `21344bb6…02ef`). Food
sufficiency `s` is the economy's pre-consumption food over demand; a famine
episode is a run of turns with `s` below 0.6 lasting three turns or more
(the report label's rule), its length the whole run.

## Result

| | base | head |
| --- | ---: | ---: |
| famine episode length, template: mean / p90 (turns) | 11.5 / 28 | 8.1 / 21 |
| episodes of 20 turns or more, template (procedural) | 30% (7.4%) | 11% (2.2%) |
| climate famines, template: mean / p90 length | 14.9 / 30 | 10.5 / 26 |
| turns with 75% or more of a template world in famine | 15.6% | 6.7% |
| longest world-wide famine (75%+ of regions), template | 25 turns | 24 turns, one world (of 10+ turns: 3 in 10 worlds, base 13) |
| output per farmer at density 0.1-0.2 / 0.5-0.6 (x constant returns) | 1.00 / 1.00 | 1.46 / 0.84 |
| final population mean, template (procedural) | 160 (749) | 189 (880) |
| famine death rate / fed rate, template | 1.96 | 2.04 |
| births in famine / fed, template | 1.00 | 0.87 |
| subset gates 42-61 / 62-81 (needs seeds) | PASS (14 / 16) | PASS (18 / 14) |
| full gate (200 x 500) | PASS (hunger head) | PASS strict; NO REGRESSION |
| migration per agent-turn (full gate; strict floor 0.05) | 0.0554 | 0.0610 |
| extinct worlds (full gate) | 0 | 0 |

Famines end sooner and rarely cover a whole world; crowded land feeds fewer
per farmer and thinned land more. The hunger terms rise part of the way to
the middle of the historical ranges: the mid-range terms failed the needs
subset gate (section 6).

## 1. Where food is made

| Step | Where | Before this branch |
| --- | --- | --- |
| Yield per farmer | Phase 2 preview, Python `ecology.compute_resource_yields`: base x season x crop climate (`CLIMATE_CLASS_MOD`, global phase) x soil x water (crops) x techniques; `goods_per_worker` divides by the long-run normal | the same yield however many farm |
| Labour | Rust `economy::tick_economy_core`: farmers (pool count) x cities' labour factor, split food-first over the slots (`allocate_farm_labor`); output = yield x slot labour | linear in farmers |
| Food sufficiency | production + stock + delivered imports over 0.5 per head | |
| Farmer income | Rust `tick.rs`: base income x price modifier x the region's primary yield | per farmer, constant in density |
| Capacity terms | `carrying_capacity` (terrain), `capacity_modifier` (disasters), `potential_capacity` = their product; `effective_capacity` adds soil and water; the fertility brake reads population / carrying capacity (0.75-1.0) | crowding acted through births and mortality only |
| Climate | `climate.get_climate_phase` (pure, global): temperate 40% of a 75-turn cycle, warming, drought and cooling 20% each; crops x0.9 / 0.5 / 0.7; water -0.04 a turn in drought, -0.02 in cooling, +0.03 in temperate (Python `_tick_water`, Rust `tick_water_controlled`) | every region at once |
| Agents off | `ecology._check_famine_yield`: famine when the best food slot's index is below 0.12; growth +5 a region while under effective capacity | food per head independent of population |

Read-only probes (outside the repository) recorded, per region and turn in
Phase 2, the farmers in the pool, the economy's input yields, the food the
kernel produces (mirrored with the Python labour split), the land terms, the
technique practice, the global phase, war context and the food sufficiency.

**Output per farmer against density.** Density `x` is farm labour over
potential capacity. In the base the kernel gives each farmer the slot's
yield at any density; the observed food per farmer rises with density only
because poor land is thinly settled:

| `x`, template | region-turns | food per farmer | sufficiency | below 0.6 |
| --- | ---: | ---: | ---: | ---: |
| 0.0-0.1 | 931 | 0.61 | 0.77 | 49% |
| 0.1-0.2 | 2,083 | 0.66 | 0.81 | 48% |
| 0.2-0.3 | 2,265 | 0.74 | 0.96 | 41% |
| 0.3-0.4 | 2,116 | 0.87 | 1.18 | 27% |
| 0.4-0.5 | 1,965 | 0.98 | 1.44 | 13% |
| 0.5-0.6 | 1,022 | 1.00 | 1.54 | 11% |
| 0.6-0.8 | 232 | 0.93 | 1.37 | 19% |

Farmer-weighted median density: 0.43 in fed region-turns, 0.29 in famine
(template); 0.41 and 0.25 procedurally. Famine regions are thinner than fed
ones: deaths and flight thin them, and constant returns gave the survivors
nothing for it. Densities stop near 0.55 because the fertility brake
stops births at carrying capacity and farmers are 54% of the population.

**Famine episodes by cause** (first matching rule at onset: war, the
controller at war and the region a front, besieged or blockaded within the
first three turns; climate, a drought or cooling phase or the land's
climate potential, crop modifier x water over the terrain's default water,
below 0.6; crowding, population at or above effective capacity; other):

| Base, 200 turns | episodes per world | share | mean / median / p90 length | region-turns |
| --- | ---: | ---: | --- | ---: |
| template: climate | 14.1 | 59% | 14.9 / 13 / 30 | 2,097 |
| template: war or blockade | 1.6 | 7% | 14.6 / 5 / 33 | 233 |
| template: crowding | 3.2 | 13% | 5.8 / 4 / 7 | 186 |
| template: other (season, no food slot) | 5.0 | 21% | 4.6 / 3 / 6 | 228 |
| procedural: climate | 164 | 65% | 7.6 / 5 / 20 | 6,223 |
| procedural: war or blockade | 20 | 8% | 9.2 / 4 / 19 | 926 |
| procedural: crowding | 3.2 | 1% | 3.3 / 3 / 4 | 53 |
| procedural: other | 67 | 26% | 4.1 / 3 / 6 | 1,384 |

Climate is three quarters of famine region-turns on template worlds. The
crop modifier is the smaller part: the water lost over drought and cooling
(0.9 over 30 turns, from 0.7 towards the 0.1 floor on plains) cuts crops,
which grow with soil x water, to about a quarter for 25 turns, in every
region at once:

| Template base, cycle position | phase | water | food yield | sufficiency | in famine |
| --- | --- | ---: | ---: | ---: | ---: |
| 15-29 | temperate | 0.71 | 1.25 | 1.41 | 4% |
| 45-49 | drought | 0.59 | 0.77 | 1.21 | 7% |
| 55-59 | drought | 0.18 | 0.46 | 0.41 | 63% |
| 60-74 | cooling | 0.15 | 0.53 | 0.50 | 67% |
| 0-4 | temperate | 0.41 | 0.91 | 1.10 | 26% |

In 15.6% of template turns three quarters of a world's regions were in
famine; such world-wide famines came 3.8 times per 200-turn world and lasted
up to 25 turns. Procedural worlds, whose latitude bands scale the climate
losses, rarely reach 75% (0.1% of turns) but half their regions in 8.5%.

## 2. Diminishing returns

Farm labour is effective labour on the region's land, a saturating curve
in the farmers working it:

    E(L) = L (L_ref + L_h) / (L + L_h)
    L_ref = 0.33 x arable capacity,   L_h = L_ref x eps / (1 - eps),   eps = 0.5
    arable capacity = potential capacity x (1 + 0.10 irrigation + 0.10 ox plough
                      + 0.15 heavy plough (practice-weighted) + 0.10 irrigation works)

| Farmers per unit of arable capacity | 0.08 | 0.17 | 0.33 | 0.50 | 0.66 | 1.0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| output per farmer (x constant returns) | 1.60 | 1.33 | 1.00 | 0.80 | 0.67 | 0.50 |
| marginal farmer's output | 1.28 | 0.89 | 0.50 | 0.32 | 0.22 | 0.12 |

* **The curve.** At the reference a farmer grows what constant returns
  gave. Fewer farmers grow more each, at most twice as much; more grow
  less, and the land's output never exceeds `L_ref + L_h` (twice the
  reference output). The output elasticity to labour at the reference is
  0.5, in the range Malthusian accounts use for pre-industrial agriculture
  (labour's share 0.5-0.7, land's the rest).
* **Calibration.** 0.33 is the density at which today's well-fed regions
  produce what they did: over the base's fed region-turns (template) the
  curve gives 0.98-1.01 times their output for references of 0.32-0.34; over
  all region-turns 1.00-1.03. Measured with the ceiling below, the
  farmer-weighted median density of fed region-turns is 0.36.
* **The ceiling.** Soil, water, season and climate stay in the yield (the
  land's quality); the curve's scale is the land's extent. The farming
  techniques (irrigation, the ox and heavy ploughs, by the region's
  practice) and irrigation works raise it: a region with all of them feeds
  up to 1.45 times the farmers at the same output per head. In base runs
  the mean multiplier is 1.04 in turns 0-49 and 1.16 by turns 150-199. There
  is no crop rotation technique.
* **Where it acts.** Python passes `farm_labor_ref` and `farm_labor_half`
  per region (optional economy columns; absent, the kernel keeps constant
  returns). The kernel applies the curve to the farm labour before the
  food-first split, so every slot's output (food and raw materials) and the
  foraging share use effective labour. It reports `farm_productivity`, the
  output per farmer against constant returns, which Python passes back in
  the region batch (optional column; absent reads 1.0) and the agent tick
  multiplies into farmer income. Crowded farmers earn less, the emptied
  land's more. The Python economy oracle (`compute_economy`) mirrors it.
* **Agents off** has no farmers. The aggregate famine check scales the
  region's food yield by the same curve, with farm labour 0.54 x population
  (the mean farmer share of hybrid worlds): a crowded region starves on a
  harvest a thin one survives, and a famine's toll raises the survivors'
  food per head.

Tuning `economy.farm_reference_density` 0 restores constant returns;
`economy.farm_labor_elasticity` sets `eps`.

## 3. Regional climate

The global phase stays the long trend, at half of its crop and water
effects; the other half of the same pressure comes as regional harvest
shocks.

* **Trend.** A region's crop climate factor is `1 - 0.5 (1 - m) - h`, with
  `m` the phase's crop modifier and `h` its harvest shock (drought 0.75,
  cooling 0.85 without a shock). The drought and cooling water losses are
  halved. Forest, fisheries, disasters, nomads and narration read the
  global phase as before.
* **Clusters.** Regions taken in a hashed order
  (`stable_hash_int("climate.cluster", seed, name)`) found a cluster with up
  to two of their unassigned neighbours (`climate.climate_clusters`, pure in
  the seed and geography). Template worlds have 3-4 clusters, 64-region
  worlds 25-27.
* **Harvest years.** Each cluster's years (12 turns, the season calendar)
  are good or bad: a bad year follows a bad one with probability 0.4 and a
  good one with the probability that keeps the stationary share of bad
  years at 22.5%. Runs of bad years last 1.7 years on average; 16% last
  three years or more, 6% four or more. A bad year's depth is uniform in
  0.2-0.6. Every draw is
  `stable_hash_int("climate.harvest_year", seed, founder, year)`; the chain
  is evaluated from year 0 and cached, so `climate.harvest_shock` is a pure
  function of seed, cluster and turn, and a resumed world reads what an
  uninterrupted one does. No state is saved and no RNG stream changes.
* **Pressure kept.** The shock's mean is the half of the global schedule's
  mean crop loss the trend gave up (0.09; the cycle-mean crop factor stays
  0.82, so `harvest_normal_index` is unchanged). A bad year also dries the
  land: `h x 0.0667` water a turn, the half of the drought and cooling
  losses (0.012 a turn over a cycle) the trend gave up, spread over the mean
  shock. Both shares are derived from the phase tables and the water tuning
  keys, not tuned.
* **Where it acts.** The Phase 2 harvest preview, the aggregate famine
  check, the goods economy's foraging (regions without a yielding food slot)
  and the Python water tick read the region's factor; the native ecology
  reads an optional `harvest_shock` region column and
  `set_climate_config(trend_share, harvest_shock_water_loss)` (absent and
  not called: the global schedule). `get_climate_phase` is unchanged. The
  magnitude variants of section 6 were built before foraging read it (their
  foragers met the global phase at full strength).

Tuning `climate.trend_share` 1.0 restores the global schedule alone.

Trend shares tried (template; procedural in brackets):

| Trend share | famine share of region-turns | episodes of 20+ turns | turns with 75%+ in famine | final population |
| --- | ---: | ---: | ---: | ---: |
| 1.0 (base) | 21.2% (18.1%) | 30.1% (7.4%) | 15.6% (0.1%) | 160 (749) |
| 1.0, diminishing returns only | 23.7% (15.2%) | 30.2% (6.7%) | 18.0% (0) | 184 (926) |
| 0.5, regional climate only | 16.6% (16.0%) | 12.3% (3.6%) | 8.3% (0) | 176 (769) |
| **0.5, both** | 16.9% (11.9%) | 12.8% (3.2%) | 5.5% (0) | 181 (956) |
| 0.35, both | 17.1% (12.1%) | 10.0% (3.1%) | 5.1% (0) | 182 (888) |
| 0.25, both | 17.2% (10.3%) | 6.4% (1.1%) | 4.6% (0) | 187 (861) |

Diminishing returns alone do not shorten climate famines (mean 14.4
turns): the water floor, not the farmers, sets their end. Regional climate
alone cuts long famines by three fifths. Lower trend shares shorten them
further but keep the world-wide share near 5%: a template world has only
3-4 clusters, so all of them are sometimes bad together. 0.5 keeps the
long trend visible (a drought still takes a quarter of every region's crop).

## 4. After

Head against base, the same worlds and probes as section 1:

Output per farmer against density (template; the productivity column is
output per farmer against constant returns, the curve's factor):

| `x` | base: food per farmer | head: food per farmer | head: productivity | head: sufficiency | head: below 0.6 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.0-0.1 | 0.61 | 0.83 | 1.53 | 0.78 | 50% |
| 0.1-0.2 | 0.66 | 0.84 | 1.46 | 0.84 | 42% |
| 0.2-0.3 | 0.74 | 0.91 | 1.23 | 1.05 | 35% |
| 0.3-0.4 | 0.87 | 0.94 | 1.07 | 1.21 | 25% |
| 0.4-0.5 | 0.98 | 0.91 | 0.94 | 1.29 | 17% |
| 0.5-0.6 | 1.00 | 0.80 | 0.84 | 1.25 | 17% |
| 0.6-0.8 | 0.93 | 0.68 | 0.74 | 1.19 | 24% |

Procedurally the productivity runs from 1.40 (density below 0.1) to 0.73
(0.6-0.8). Famine regions are no longer much thinner than fed ones
(farmer-weighted median density 0.36 in famine, 0.41 when fed; base 0.29
and 0.43): the survivors of a famine now grow more each.

Famine episodes by cause (rules of section 1):

| Head, 200 turns | episodes per world | mean / median / p90 length (base) | region-turns (base) |
| --- | ---: | --- | ---: |
| template: climate | 17.1 | 10.5 / 6 / 26 (14.9 / 13 / 30) | 1,796 (2,097) |
| template: war or blockade | 1.9 | 6.9 / 5 / 14 (14.6 / 5 / 33) | 131 (233) |
| template: crowding | 5.4 | 4.9 / 4 / 8 (5.8 / 4 / 7) | 262 (186) |
| template: other | 5.6 | 4.5 / 3 / 7 (4.6 / 3 / 6) | 252 (228) |
| procedural: climate | 157 | 5.8 / 4 / 10 (7.6 / 5 / 20) | 4,524 (6,223) |
| procedural: war or blockade | 15 | 6.3 / 4 / 11 (9.2 / 4 / 19) | 467 (926) |
| procedural: crowding | 6.2 | 4.3 / 3 / 3 (3.3 / 3 / 4) | 132 (53) |
| procedural: other | 57 | 4.0 / 3 / 6 (4.1 / 3 / 6) | 1,158 (1,384) |

| Per world, 200 turns | template base | template head | procedural base | procedural head |
| --- | ---: | ---: | ---: | ---: |
| region-turns in famine (run of 3+ below 0.6) | 21.2% | 16.7% | 18.1% | 11.7% |
| fed region-turns | 49.8% | 48.6% | 46.2% | 53.0% |
| famine episodes; mean length | 23.9; 11.5 | 30.0; 8.1 | 254; 6.8 | 235; 5.3 |
| episodes of 10+ / 20+ turns | 35% / 30% | 21% / 11% | 16% / 7.4% | 9.7% / 2.2% |
| turns with half the regions in famine | 23.1% | 15.0% | 8.5% | 1.2% |
| turns with three quarters in famine | 15.6% | 6.7% | 0.1% | 0 |
| world-wide famines (75%+) of 10 turns or more, 10 worlds | 13 | 3 | 0 | 0 |
| final population mean (min) | 160 (118) | 189 (122) | 749 (551) | 880 (760) |

Climate famines are shorter and fewer worlds starve at once: famines now
start more often (more, shorter, local bad years) and end sooner. Crowding
famines become more frequent but stay short: crowded land saturates and the
toll and flight thin it. War and blockade famines halve in length. The long
world-wide famines of the base (13 of 10 or more turns in 10 worlds, up to
25) are down to 3; the longest, 24 turns in seed 50, starts in the global
drought while its clusters have bad years together.

| Template head, cycle position | phase | water | food yield | sufficiency | in famine (base) |
| --- | --- | ---: | ---: | ---: | ---: |
| 15-29 | temperate | 0.68 | 1.17 | 1.33 | 6% (4%) |
| 45-49 | drought | 0.60 | 0.90 | 1.17 | 7% (7%) |
| 55-59 | drought | 0.35 | 0.60 | 0.59 | 40% (63%) |
| 60-74 | cooling | 0.29 | 0.62 | 0.59 | 52% (67%) |
| 0-4 | temperate | 0.47 | 0.93 | 1.16 | 15% (26%) |

Hunger (template, the same probes as [hunger-mortality.md](hunger-mortality.md),
deaths per 1,000 agent-turns; births per 1,000 aged 16-60):

| | base fed | base famine | head fed | head famine |
| --- | ---: | ---: | ---: | ---: |
| share of agent-turns | 62.5% | 14.5% | 58.0% | 11.6% |
| deaths | 13.7 | 26.9 | 13.8 | 28.1 |
| deaths aged 0-4 / 60+ | 7.7 / 32.7 | 17.6 / 58.7 | 9.8 / 33.0 | 22.4 / 63.9 |
| births | 27.6 | 27.6 | 31.5 | 27.4 |
| share of deaths from the hunger term | 0 | 22% | 0 | 31% |
| share of births withheld | 0 | 27% | 0 | 32% |

Famine deaths are 2.04 times the fed rate (base 1.96; under 5: 2.27, 60+:
1.94), famine births 0.87 times (1.00). Dearth covers 22% of agent-turns
(base 17%): the halved global drought and the bad years leave more lean
turns than famines.

## 5. Agents off

The aggregate model's famine check reads the curve (food per head against
the crowding of the land) and the regional crop factor; growth is unchanged.
Template worlds:

| `--agents off` | base | head |
| --- | ---: | ---: |
| seeds 42-51, 200 turns: famine reports per run | 130.4 | 107.9 |
| mean population over the run | 216.8 | 239.2 |
| lowest population after turn 10 | 29 | 84 |
| seeds 42-45, 500 turns: famine reports per run | 368.8 | 281.5 |
| mean population over the run | 205.4 | 230.2 |
| lowest population after turn 10 | 25 | 31 |
| extinct worlds | 0 | 0 |

Base off-mode famines struck thin regions (median density 0.10 at the
report): the curve feeds them 1.5 times more per head, so reports fall a
fifth and the lowest world holds more people.

Golden oracles (Python off mode, native runtimes disabled) are rolled
forward as `corrected_farmland_2026_10.json` (turn hashes, RNG traces) and
`corrected_artifacts_farmland_2026_10.json` (artifact bytes, both
projections), with the `farmland` link in `ORACLE_CHAIN`;
`corrected_hunger_2026_10*` stay frozen. Consecutive captures, first changed
turn per workload:

| Correction | single | standard | wide | Artifact files changed |
| --- | --- | --- | --- | --- |
| FC-FARM-RETURNS | 5 | 0 | 9 (RNG trace changes in standard and wide) | |
| FC-REGIONAL-CLIMATE | 0 | 0 | 26 | |
| FC-HUNGER-MAGNITUDES | - | - | - | none (the aggregate toll's share of the old toll rounds to the same losses) |
| all | | | | single: bundle; standard and wide: bundle, state, memories |

## 6. Hunger magnitudes

With famines able to end, the hunger terms were raised towards the middle of
the historical ranges ([hunger-mortality.md](hunger-mortality.md), section 3:
deaths `x (1 + v (D dearth + F famine))`, births
`x (1 - D dearth)(1 - F famine)`). Each variant was built into its own tree
with its own extension, on the farmland and climate corrections (before
foraging read the regional factor, section 3):

| Variant | deaths D / F | births D / F | famine deaths / fed, template | births famine / fed | hunger term's share of famine deaths; births withheld | needs seeds 42 / 62 / 82 / 102 (12 needed) | of 80 (pooled net concordance) | lowest population, 7 low seeds x 500 turns |
| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: |
| base (*main*) | 0.05 / 0.50 | 0.10 / 0.30 | 1.96 | 1.00 | 22%; 27% | 14 / 16 / 16 / 15 | 61 (0.152) | 56 |
| farmland, shipped terms | 0.05 / 0.50 | 0.10 / 0.30 | 1.92 | 0.96 | 18%; 23% | 19 / 15 / 13 / 15 | 62 (0.191) | 74 |
| mid range | 0.10 / 1.50 | 0.15 / 0.60 | 2.24 | 0.74 | 39%; 40% | **10** / 13 / 14 / 13 | 50 (0.131) | 66 |
| **raised (shipped)** | 0.10 / 1.00 | 0.15 / 0.45 | 2.07 | 0.92 | 30%; 33% | 18 / 16 / **13, FAIL** / 17 | 64 (0.166) | 85 |

* **Mid range.** Deaths in famine reach 2.24 times the fed rate (2.85 for
  young children, 2.27 for the old) and births fall to 0.74 times, but the
  needs oracle fails 42-61 (10 of 20 seeds with the expected sign; 12
  needed). Over 80 seeds it has 50 positive seeds, two above the 60% bar the
  full gate applies, so a full gate would turn on a few seeds. No world
  went extinct; the lowest of the risk seeds fell to 66 (base 56).
* **Raised.** Deaths in famine 2.07 times fed (young children 2.16, the old
  1.91), births 0.92 times; the term is 30% of famine deaths and 4% of
  dearth deaths, and withholds 33% of famine births and 8% in dearth. The
  required subsets pass (42-61 and 62-81); 82-101 fails the needs lower
  bound (net concordance 0.073, lower bound -0.015) with 13 of 20 seeds
  positive; over 80 seeds 64 are positive and the pooled concordance is
  above the base's. The head (these terms and the foraging fix) passes all
  four subsets and the full gate (section 7); its probes give famine deaths
  2.04 and births 0.87 times the fed rate (section 4).
* Simulated famines still recur more often than historical famine years
  (famine is 12% of agent-turns on template worlds), so per-year
  magnitudes applied to every turn of a famine compound; the death ratio
  stays at the low end of the historical two to four times.

## 7. Gates

Subset gates (20 seeds x 200 turns, hybrid, `--parallel 2`,
`chronicler.validation_compare` against `main` `82c131b`'s own subset
report; the needs oracle is method 2, `needs-oracle-power.md`; in the subset
only community, needs and cohort are required):

| Oracle | 42-61 base | head | 62-81 base | head | 82-101 base | head | 102-121 base | head |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gate; comparator | PASS | PASS; NO REGRESSION | PASS | PASS; NO REGRESSION | PASS | PASS; NO REGRESSION | PASS | PASS; NO REGRESSION |
| needs: seeds with expected sign; lower bound | 14; 0.025 | 18; 0.167 | 16; 0.127 | 14; 0.073 | 16; 0.097 | 15; 0.076 | 15; 0.070 | 14; 0.061 |
| cohort (seeds; median effect) | 20; 1.17 | 20; 1.33 | 19; 1.02 | 20; 1.03 | 20; 1.14 | 20; 1.02 | 20; 1.34 | 20; 1.07 |
| regression | FAIL (civ_survival) | PASS (strict) | FAIL (rebellion, civ_survival) | FAIL (rebellion, civ_survival) | PASS (strict) | PASS (strict) | PASS (strict) | PASS (strict) |
| satisfaction mean; latest | 0.598; 0.616 | 0.603; 0.618 | 0.620; 0.627 | 0.611; 0.621 | 0.612; 0.615 | 0.605; 0.619 | 0.606; 0.612 | 0.596; 0.608 |
| migration per agent-turn | 0.0599 | 0.0659 | 0.0526 | 0.0596 | 0.0568 | 0.0648 | 0.0603 | 0.0669 |
| rebellion per agent-turn | 0.0330 | 0.0364 | 0.0122 | 0.0178 | 0.0319 | 0.0331 | 0.0367 | 0.0365 |
| final population min / median | 64 / 150 | 95 / 179.5 | 91 / 154 | 135 / 174.5 | 105 / 157.5 | 112 / 176.5 | 83 / 149 | 88 / 182.5 |
| extinct | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Over the 80 seeds the needs oracle finds 61 seeds with the expected sign in
both (pooled net concordance 0.152 base, 0.171 head).

Full gate (200 seeds x 500 turns, hybrid, `--parallel 3`, against the
hunger-mortality head's full report; seed directories deleted once the
reports and a per-seed extract were kept):

| Oracle | hunger head `223e23a` (PR #32) | **head** `84bfb44` |
| --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** |
| community (seeds) | 200 | 200 |
| needs | PASS, method 1: 186 seeds | PASS, method 2: 182 seeds with the expected sign, pooled net concordance 0.194, lower bound 0.178 (16,492 informative pairs) |
| cohort (seeds; median effect) | 200; 1.62 | 200; 1.51 |
| era (seeds with inflections; silent collapses) | 200; 1 | 200; 1 |
| arcs (seeds with three types; families) | 167; 6 | 170; 6 |
| artifacts (status; creation; loss) | PASS; 1.32; 7.5% | PASS; 1.51; 6.0% |
| regression (status) | PASS (strict) | PASS (strict) |
| satisfaction mean; latest (ceiling 0.65) | 0.612; 0.622 | 0.617; 0.630 |
| migration per agent-turn (strict floor 0.05) | 0.0554 | 0.0610 |
| rebellion per agent-turn (0.02-0.08) | 0.0301 | 0.0308 |
| all founders surviving (limit 0.20) | 0.07 | 0.14 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 49 / 165 / 326 | 46 / 179 / 325 |

The comparator scores the two needs results by different methods and does
not compare them (`rebaseline_required`; both PASS). 1,967 s on the shared
host.

| Per run (200 worlds, 500 turns) | hunger head | head |
| --- | ---: | ---: |
| population at turn 500 | 168.4 | 181.7 |
| agent deaths / births | 1,400.0 / 1,369.5 | 1,523.0 / 1,505.8 |
| food-crisis reports (famine / dearth) | 120.2 / 193.9 | 90.7 / 238.0 |
| epidemic reports | 135.3 | 171.9 |
| civ plague outbreaks | 28.8 | 36.6 |
| mass migrations | 154.2 | 193.8 |
| agent migrations | 4,758.3 | 5,649.3 |
| agent rebellions | 2,584.4 | 2,851.6 |
| wars | 20.6 | 19.2 |
| cities founded | 6.0 | 6.3 |
| polities alive at turn 500 | 2.71 | 2.85 |

Population rises 8% over 500 turns. Famine reports fall a quarter and
dearth reports rise a fifth. Migration per agent-turn rises 0.0056 to
0.0610, 0.0110 above the strict floor (weights unchanged): fed land is
crowded and thin land rich, and the frontier and wage-gap drivers read
both. Epidemic reports rise 27%: more people and more dearth, whose
susceptibility term reads measured hunger. Latest satisfaction rises
0.008, 0.020 under the ceiling.

## 8. Tick time and bundle size

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700, 20 warm-up and 8 timed turns, two repeats, one child at a
time, release builds, base `main` against the head, each tree with its own
extension; two samples on the shared 4-core host (load 4.5-8). Medians per
run, wall / process CPU, in ms:

| alive (base; head) | | base | head |
| --- | --- | ---: | ---: |
| 23,097; 22,110 | Rust tick | 166, 164, 171, 177 / 254, 262, 275, 289 | 153, 167, 139, 159 / 249, 245, 253, 258 |
| | whole turn | 224, 258, 282, 265 / 335, 374, 428, 393 | 241, 230, 195, 224 / 311, 299, 309, 319 |
| 51,354; 50,360 | Rust tick | 731, 469, 402, 369 / 1,039, 1,118, 1,223, 1,172 | 582, 395, 713, 705 / 1,210, 1,309, 1,281, 1,241 |
| | whole turn | 926, 600, 517, 485 / 1,351, 1,345, 1,686, 1,627 | 765, 498, 910, 910 / 1,585, 1,669, 1,638, 1,613 |

Rust tick CPU per alive agent: 11.1-11.7 against 11.0-12.5 us at about
22k; 24.0-26.0 against 20.2-23.8 us at about 51k (median +10%). Wall time
moves both ways with the host's load. The new native work is two
arithmetic terms per region in the economy and ecology and one product per
farmer's income; the worlds diverge from the first turn (the head moves
more agents: agent migrations +19% in the full gate), so the arms are not
the same work.

Bundle guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, `--agents off`, every default):

| Guard world | base (`main`) | head |
| --- | ---: | ---: |
| native | 16.44 MB (17,236,056 bytes) | 21.55 MB (22,594,862 bytes) |
| no-Rust | 22.21 MB (23,285,909 bytes) | 22.67 MB (23,769,889 bytes) |

(MB is 2^20 bytes.) Not longer history or more polities: the native world
founds 11 polities over the run in both, the no-Rust one 10 (base 16). More
of them live at once: 5.5 civs per snapshot natively against 4.2 (5.6
against 5.4 without Rust), and every snapshot carries each living civ's
stats, diplomacy and proxy-war rows (native history 11.7 -> 15.6 MB: civ
stats 4.1 -> 5.4, diplomacy 1.3 -> 2.0, proxy wars 0 -> 0.9). Its events
rise 23% (wars 53 -> 114; famine reports 385 -> 365). The 24 MB limit
stays; the no-Rust world is 1.33 MB under it, the native one 2.45 MB.

## 9. Why on by default

The brief makes these corrections to the simulation: constant returns to
farm labour and a synchronous world climate are the defects. Each has a
tuning key that restores the old behaviour exactly
(`economy.farm_reference_density: 0`, `climate.trend_share: 1.0`): with
both, the head built with the old hunger constants is byte-identical to
`main` on three worlds (section 10). The hunger magnitudes are constants, as
before. Tests of other mechanics that pin constant-returns or global-phase
arithmetic set the two keys.

## 10. Verification

Head `84bfb44` plus this document and a test comment (no code change),
extension
built fresh (SHA-256 `21344bb6…02ef`), shared 4-core host (`-n 2`).

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 969 passed, 2 ignored (`main`: 963) |
| `pytest -m "not slow" -n 2` | 6,141 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (virtualenv without `chronicler_agents`) | 5,918 passed, 226 skipped, 526 subtests; `TestBundleSize` passed (22.67 MB) |
| `scripts/run_python_oracle_checks.py` | PASS in 83.0 s: 2,102 passed, 28 skipped; largest chunk `systems-2` 27.6 s of 110 s |
| Golden fixtures | rolled forward (section 5); `ORACLE_CHAIN` link `farmland` |
| Identity with both corrections off | the head with the old hunger constants and `economy.farm_reference_density: 0`, `climate.trend_share: 1.0` against `main` (each tree its own extension): hybrid template seed 42 (120 turns), hybrid procedural seed 7 (48 regions, 10 civs, 100 turns), agents-off seed 42 (150 turns): 35 files, 0 differ |
| Viewer | not touched |

New tests: `tests/test_farmland_climate.py` (23, three native: farmer
income follows `farm_productivity` and resets without the column, the
kernel reports it for crowded and empty land, the native ecology reads the
harvest shock), in the oracle lane's `systems-2` chunk; Rust `economy` (the
curve, the kernel on crowded and empty land), `ecology` (the regional crop
factor, a bad year's crop and water, default config bit-identical), `tick`
(farmer income).

Changed expectations, each because farm output now saturates or the
climate is regional:

* Tests and experiment scripts of other mechanics that pin constant-returns
  or global-phase arithmetic set `economy.farm_reference_density: 0` and/or
  `climate.trend_share: 1.0`: `test_economy_m43a.py` (M42 equilibrium,
  stockpile integration), `test_fishery_experiment.py` and
  `scripts/validate_fishery_recovery.py` (catch per fisher is the fishery
  model's own), `scripts/economy_coupling_experiment.py` (designed goods per
  farmer under the full drought), `scripts/mutual_aid_adversarial.py`,
  `test_city_markets.py` (half the labour grows half the food),
  `test_hunger_mortality.py` (the aggregate toll's depth), `test_food_balance.py`,
  `test_ecology.py` (irrigation trap) and `test_ecology_harvest_timing.py`
  (the phase's own water and harvest arithmetic).
* `test_economy.py`: the mock regions get land terms.
* `test_economy_bridge.py`: the economy batch has 20 columns (the curve's two).
* `scripts/qualify_third_wave.py`: its independent production oracle reads
  the curve's columns.
* `test_maritime.py`: the raid run is seed 7, 40 turns (seed 12 now loses
  no cargo).
* `test_snapshot_pruning.py`: the real run is 75 turns; Thornwall falls at
  turn 70 and is pruned from 71; Kethani, exiled at 60-63 and restored,
  stays unpruned.
* `test_bundle.py`: the guard world's sizes in the comment.
* `test_performance_equivalence.py`, `test_governance_dormancy.py`,
  `test_historiography.py`, `test_languages.py`: read the farmland oracles;
  a scoped-difference test for the farmland artifacts.

## 11. Open items

* **Clocks.** A turn is a month for seasons and harvest years and a year for
  ages; a bad harvest year is 12 turns of shock and 12 years of demography.
* **Population.** More people live on the land: final population +18% on
  template worlds at 200 turns, +8% at 500 in the full gate, mostly where
  thin, poor land now feeds its farmers better. Tick time scales with it.
* **Raw materials.** The curve applies to all farm labour, so ore and timber
  output also saturate on crowded land; mines and forests have no ceiling of
  their own.
* **Fisheries.** The fishery experiment (default off) caps catch by its
  stock; with it on, fish output reads both the curve and the cap.
* **Clusters.** Fixed partitions of up to three neighbours; shocks do not
  spill over cluster borders, and latitude does not scale them.
* **Dearth.** The trend's halved drought and the bad years leave more lean
  turns than famines: dearth region-turns rise (template 17% to 23% of
  agent-turns).
* **Mid-range hunger.** Held back by the needs oracle's seed criterion at
  subset scale; the raised terms are a step, not the middle.
