# City markets, 2026-10

Branch `feat/city-markets` from `origin/main` at `cee5013` (PR #28, cities
as actors, default off), merged with `origin/main` at `3355289` (PR #29:
navigation, famine and dearth labels, migration drivers) without rebase.
Three commits of work:

1. **Merchant routing correction** (`0d4df97`), on for every run: the
   three gaps left by [food logistics](food-logistics-2026-10.md).
2. **Cities as markets** (`bada9a5`), behind `--cities`: the first item of
   the [cities roadmap](cities.md#roadmap).
3. **Viewer Cities tab** (`b2f8353`).
4. After the merge (`955afe0`): a row-path fallback for the cities' agent
   reads (`7f54112`) and **cities on by default for new worlds**
   (`e979fd9`).

Code: `chronicler-agents/src/merchant.rs` (planner, tally), `knowledge.rs`
(trade packets), `economy.rs` and `ffi/mod.rs` (market outputs, city
inputs), `src/chronicler/agent_bridge.py` and `economy.py` (bridge
columns), `src/chronicler/cities.py` (city inputs, sieges, commerce),
`viewer/src/lib/cities.ts` and `viewer/src/components/systems/CitiesPanel.tsx`.

**Status.** The routing correction is on for every run. Cities (with their
markets) are **on by default for new worlds** since `e979fd9`;
`--no-cities` opts out and saved worlds keep their setting. The full gate
(200 x 500, hybrid, cities on, merged tree) passes **strict**, 0 of 200
worlds extinct, **NO REGRESSION** against main's latest full report
(`3355289`) and against Wave 8. With the switch off every output equals
`3355289` plus the routing correction (172 files, 0 differences).

## Part A: merchant routing correction

| Gap | Before | After |
| --- | --- | --- |
| Trade packets | A packet carried the observed region's export margin (`merchant_route_margin`), high where a region is cheap or empty; the packet planner scored non-food cargo by it | A packet advertises a market: its strength is the region's dearest good above balance (`market_signal`); packet-known markets are scored like any market |
| Non-food cargo | Carried by the activity proxy (origin margin + destination margin) | Carried by its price gap: demand over post-trade supply, the economy's own price for raw materials and luxuries |
| Herding | Every merchant at an origin saw the same state and chose the same market and cargo | Merchants plan one at a time in (origin, agent id) order against a per-tick tally of cargo committed to and from each market |

- **Market prices.** The native economy reports its demand and post-trade
  supply (available - exports + imports) per goods category (food, raw
  material, luxury) in six new region-result columns. Python keeps them on
  `EconomyResult.market_demand` / `market_supply`; the region batch carries
  them to Rust as `market_demand_<cat>` / `market_supply_<cat>` (absent: 0,
  no market). Raw materials and luxuries are priced demand / max(supply,
  0.1), at most 10 (food's cap), 0 without demand: a region without
  soldiers wants no ore, one without wealthy agents no luxuries. Food keeps
  1 / sufficiency and still goes first. A region without people has no
  price, is never a destination and emits no packet.
- **Packets.** `knowledge::observe_packets` emits a trade-opportunity packet
  when the observed region's `market_signal` (dearest price - 1, over 5,
  within [0, 1]) exceeds the existing 0.10 threshold, with the same
  intensity mapping. Prices at known markets are read live, as food's
  already were; packets decide which markets a merchant knows. M59b gating
  and its no-fallback rule are unchanged.
- **Tally** (`MarketTally`). Per region and category: cargo bound there
  (loading and in transit, arrived this tick, planned this tick) and cargo
  leaving it (reservations and this tick's departures), none of which the
  last economy tick has seen. Each price is read as if that cargo had
  arrived or left: food as sufficiency + net / food demand, other goods as
  demand / (supply + net). Every committed plan updates the tally before
  the next merchant plans, so merchants at one origin spread over markets
  and an exporter stops before it ships away its own food. Evaluation and
  application run in the order intents were applied in before, (origin,
  agent id); no new random draws.

### Before and after

Template world, seeds 42-51, 200 turns, hybrid, Wave 8 defaults,
`PYTHONHASHSEED=0`; base `cee5013` with its own extension (`96cad2b5…4abe62`)
against `0d4df97` (`3d7bfb10…19b7f`). Read every turn by an observer
(economy result, the tick's merchant arrivals, agent rows; not committed).
"Short" is sufficiency below 1; each food arrival is binned by the
destination's sufficiency in the turn it arrives. Famine events are the
pre-#29 label (any shortfall, 5-turn cooldown).

| Measure | Base | Part A |
| --- | ---: | ---: |
| Food deliveries per run | 605 | 445 |
| ... to short / fed / empty regions | 62.5% / 34.2% / 3.3% | **80.3% / 18.2% / 1.5%** |
| ... eaten in a short region (next turn) | 31.4% | **61.0%** |
| Non-food deliveries per run | 604 | 138 |
| Region-turns below 0.2 / 0.5 / 1 sufficiency | 11.2% / 29.2% / 48.9% | 10.2% / 28.4% / 50.1% |
| Mean sufficiency | 1.119 | 1.114 |
| Famine events per run | 140.4 | **130.7** |
| Deliveries per market Gini, all populated / short markets | 0.793 / 0.610 | **0.730 / 0.507** |
| Herding: top market's share of an origin's arrivals in a turn (2+ arrivals) | 0.912 | **0.798** |
| Merchant income per turn (world) | 2.20 | **2.42** |
| Merchant / farmer mean wealth at turn 200 | 14.0 / 5.91 | 17.2 / 5.86 |
| Satisfaction (agent-turns) | 0.589 | 0.599 |
| Migration per agent-turn | 0.0591 | 0.0562 |
| Merchant plans per run (packet / bootstrap) | 935 / 386 | 480 / 172 |
| Population at turn 200, mean (smallest) | 188 (129) | 187 (140) |

- Food now reaches short regions (80% of deliveries, 61% eaten there), and
  deep shortage and famine fall. Deliveries fall by a quarter: exporters
  stop at their own need and no longer top up fed regions, so the share of
  mildly short region-turns rises a little (48.9% to 50.1%).
- Non-food cargo fell from 604 to 138 deliveries per run: it now goes only
  where soldiers (raw materials) or wealthy agents (luxuries) want it.
- Herding is spread, not gone: most origins have one sensible market.
- Migration falls by 0.003 per agent-turn here (famine memory drives 43%
  of moves) and by 0.0015 on average over three subset sets; see
  [Gates](#gates).

## Part B: cities as markets (`--cities`)

### Design

- **Urban labour.** A farmer who lives in a city gives part of his labour
  to the town: the goods economy counts 0.8 (town), 0.7 (city) or 0.6
  (great city) of it on the land (`URBAN_FARM_LABOR`). Python computes the
  region's `farm_labor_factor` (1 - the sum over its cities of (1 - share)
  x the city's share of the region's farmers) from the agent rows the
  economy reads and sends it as an optional economy column; Rust multiplies
  the farmer labour by it (absent: 1.0). A city region then eats more than
  it grows and, with Part A, merchants bring grain to it by price: from
  same-realm neighbours, which are the nearest and whose kin moved to the
  city (the urban pull), and from trade partners.
- **Crafts.** City residents who are not soldiers want 0.1 raw materials a
  turn each (`CRAFT_RAW_PER_RESIDENT`, a soldier wants 0.3), sent as
  `craft_raw_demand` and added to the economy's raw-material demand. The
  economy has no craft goods; cities demand the materials their crafts
  work, so timber and ore have a market in cities.
- **Sieges.** A city that an enemy besieges (an army `sieging` there) or
  occupies is cut off from the merchant graph (`cities.merchant_route_graph`,
  after the maritime filter): no merchant enters or leaves; merchants on
  the way are rerouted or turned back by the mobility phase. Blockades
  already remove sea lanes (maritime).
- **Commerce.** Market access gains 2 x merchant imports (every category)
  over the region's food demand, at most 0.6 (the routes' cap).
- **Not adopted.** A city-market premium (prices x 1 + 0.1/0.2/0.3 by rank
  at both ends, paid in trade income) was measured: cities stopped
  exporting their surplus and food deliveries fell 15%; removed.

Contracts: the inputs are recomputed every turn from persisted city state
and the last tick's agent rows (`economy_columns`), never stored; Rust
reads them per economy call and keeps nothing (a call without the columns
is a full-labour call; native multi-call test). No new random draws. With
the switch off none of this runs (`test_feature_off_never_runs_city_code`
forbids the new entry points too).

### Effects

Same observer, seeds 42-51 x 200, `--cities` on both arms: Part A alone
(`0d4df97`) against Part A + B (`bada9a5`), pre-merge.

| Measure | Part A, cities on | + city markets |
| --- | ---: | ---: |
| City regions: mean sufficiency / short | 1.222 / 42.7% | 1.163 / 46.1% |
| Food arrivals in city regions per run | 162 | 170 |
| ... from same-realm neighbours / other same realm / foreign | 38.5% / 1.8% / 59.7% | 44.5% / 4.2% / 51.4% |
| Hinterland (same-realm neighbours of a city): farmer income modifier | 1.469 | 1.632 (+11%) |
| Other rural regions: farmer income modifier | 1.451 | 1.574 (+8%) |
| Hinterland / other rural farmer wealth | 4.86 / 5.71 | 5.07 / 5.35 |
| Mean sufficiency, all regions; famine events per run | 1.127; 129.4 | 1.078; 131.7 |
| Satisfaction; migration per agent-turn | 0.596; 0.0586 | 0.586; 0.0594 |
| Urban pull, share of migration units | 4.1% | 3.1% |
| Non-food deliveries per run | 161 | 171 |
| City purse, mean over city-turns | 21.4 | 21.3 |

- City regions turn from exporters into importers more often, and more of
  their grain comes from their own realm's neighbours. Prices and farmer
  wealth rise more around cities than elsewhere (the wage-gap driver sees
  hinterland farmers' wealth rise relative to other rural farmers: 0.85 to
  0.95 of theirs).
- At template scale merchant imports cover about 2% of a city region's
  food demand: a merchant carries one unit and the world has little
  surplus, so most of a city's food is still grown in its own region, which
  is its first hinterland. A city's food security follows that region's
  harvest and, at the margin, its neighbours'. Merchant income and the
  civic purse move within run-to-run noise here.
- The world is hungrier with cities on (mean sufficiency -0.05), the cost
  of townsfolk farming less; famine events +2%.

## Gates

Every gate is hybrid, `PYTHONHASHSEED=0`, run from a `git archive` export
with its own extension built from that export (`maturin build --release
--locked`, compiled module and classes verified): `3355289`
`6df1c3e1…19c33f0` (equal to main's recorded build), the merged head
`955afe0` `46f4fa81…c52b9b`. Subsets `--parallel 2`, full `--parallel 3`;
compared by `chronicler.validation_compare`.

### Full gate (200 x 500), cities on

Merged head with `--cities` (the routing correction in), against main's
latest full report (`fix/navigation-famine-labels` head, now `3355289`)
and Wave 8 (`a95e4d7`). **PASS strict**; comparator **NO REGRESSION**
against both.

| Oracle / measure | Wave 8 (`a95e4d7`) | main (`3355289`) | branch, cities on |
| --- | --- | --- | --- |
| regression | PASS strict | PASS strict | PASS strict |
| satisfaction mean / latest (ceiling 0.65) | 0.607 / 0.619 | 0.607 / 0.620 | 0.605 / 0.618 |
| migration per agent-turn (floor 0.05) | 0.0576 | 0.0576 | 0.0580 |
| rebellion per agent-turn | 0.0317 | 0.0314 | 0.0308 |
| Gini in range / occupation violations | 84.7% / 0.17% | 84.4% / 0.16% | 85.4% / 0.16% |
| all-founder survival (limit 0.20) | 0.110 | 0.110 | 0.120 |
| extinct worlds | 0 | 0 | 0 |
| final population min / median / max | 60 / 200.0 / 340 | 60 / 199.5 / 342 | 70 / 177.0 / 328 |
| needs (seeds; median effect) | 194; 1.41 | 196; 1.41 | 189; 1.41 |
| cohort / community | PASS / PASS | PASS / PASS | PASS / PASS |
| arcs (seeds with three types; families) | PASS (167; 6) | PASS (168; 6) | PASS (166; 6) |
| era (inflections; silent) | PASS (200; 0) | PASS (200; 0) | PASS (200; 0) |
| artifacts (per civ per 100 turns; loss) | PASS (1.49; 4.4%) | PASS (1.49; 4.5%) | PASS (1.43; 6.3%) |

- Migration and rebellion are within 0.0006 of main; satisfaction -0.002.
- Final populations are smaller (median 177 against 199.5): city regions
  grow less food, the cost measured in [Effects](#effects).
- Needs passes on 189 of 200 seeds (120 required), against 196.

### Subsets (20 x 200), merged tree

Routing correction against main (cities off), and cities on against
cities off. In the subset profile only community, needs and cohort are
required.

| | 42-61 main | 42-61 routing | 42-61 + cities | 62-81 main | 62-81 routing | 62-81 + cities |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION | PASS / NO REGRESSION | PASS / - | FAIL / REGRESSION | PASS / NO REGRESSION |
| needs (seeds; 12 required) | 13 | 19 | 16 | 14 | 8 | 16 |
| regression (informational) | PASS strict | PASS strict | PASS strict | FAIL: rebellion floor, civ survival | FAIL: rebellion floor, civ survival | FAIL: rebellion floor, civ survival |
| migration per agent-turn | 0.0597 | 0.0603 | 0.0619 | 0.0550 | 0.0522 | 0.0548 |
| rebellion per agent-turn | 0.0350 | 0.0411 | 0.0376 | 0.0130 | 0.0151 | 0.0153 |
| satisfaction mean / latest | 0.596 / 0.616 | 0.598 / 0.616 | 0.591 / 0.603 | 0.611 / 0.619 | 0.616 / 0.625 | 0.608 / 0.619 |
| arcs; artifacts | PASS; PASS | PASS; PASS | PASS; PARTIAL | FAIL; PARTIAL | PASS; PASS | PASS; PASS |
| extinct worlds | 0 | 0 | 0 | 0 | 0 | 0 |

### Subsets before the merge (base `cee5013`)

Part A (`0d4df97`) against the base, and Part A + B (`bada9a5`) with
`--cities` against Part A, plus a third seed set for Part A.

| | 42-61 base | 42-61 A | 42-61 A + B | 62-81 base | 62-81 A | 62-81 A + B | 82-101 base | 82-101 A |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION | PASS / NO REGRESSION | PASS / - | FAIL / REGRESSION | PASS / NO REGRESSION | PASS / - | PASS / NO REGRESSION |
| needs (seeds; 12 required) | 13 | 19 | 16 | 14 | 8 | 16 | 19 | 16 |
| regression (informational) | PASS strict | PASS strict | PASS strict | FAIL: rebellion floor, civ survival | FAIL: rebellion floor, civ survival | FAIL: rebellion floor, civ survival | PASS strict | PASS strict |
| migration per agent-turn | 0.0599 | 0.0603 | 0.0619 | 0.0549 | 0.0523 | 0.0549 | 0.0604 | 0.0581 |
| rebellion per agent-turn | 0.0350 | 0.0411 | 0.0376 | 0.0130 | 0.0152 | 0.0153 | 0.0415 | 0.0405 |
| satisfaction mean / latest | 0.595 / 0.615 | 0.598 / 0.616 | 0.591 / 0.603 | 0.611 / 0.620 | 0.616 / 0.624 | 0.608 / 0.619 | 0.603 / 0.601 | 0.604 / 0.603 |
| arcs; artifacts | PASS; PASS | PASS; PASS | PASS; PARTIAL | FAIL; PARTIAL | PASS; PASS | PASS; PASS | PASS; PASS | PASS; PASS |
| extinct worlds | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- The merged-tree subsets reproduce the pre-merge ones within 0.0002 per
  agent-turn (PR #29 hardly moves 200-turn template worlds).
- **62-81 fails needs with the routing correction alone** (8 of 12 seeds,
  base 14), before and after the merge; 42-61 (13 -> 19) and 82-101
  (19 -> 16) pass, the full gate passes it on 189 seeds, and with cities on
  the same seeds pass (16). See [Open items](#open-items).

## Identity

`scripts/cities_identity.py compare` over every output file (`state.json`
and sidecars, `chronicle.md`, `memories_*.json`, `agent_events.arrow`, the
bundle without `generated_at`), same interpreter, `PYTHONHASHSEED=0`, each
side its own export and extension.

| Runs | A | B | Files | Differences |
| --- | --- | --- | ---: | ---: |
| template 42 / 7 / 1234, `--agents off`, 300 turns | `3355289` | head, `--no-cities` | 27 | 0 |
| same | `3355289` | head, default (before the flip) | 27 | 0 |
| procedural 48 x 10 seed 7, off, 200 | `3355289` | head, `--no-cities` | 15 | 0 |
| template 42 / 7 / 1234, hybrid, 200 | `3355289` + Part A | head, `--no-cities` | 30 | 0 |
| same | `3355289` + Part A | head, default (before the flip) | 30 | 0 |
| procedural 48 x 10 seed 7, hybrid, 120 | `3355289` + Part A | head, `--no-cities` | 16 | 0 |
| template 42 / 7 / 1234, off, 300, `--cities` both | `3355289` | head | 27 | 0 |

"`3355289` + Part A" is the export of `3355289` with `git diff cee5013
0d4df97` applied (the oracle-lane chunk list excluded) and its own
extension (`d02942fd…ae273`). Before the merge the same matrix (Part A
`0d4df97` against Part A + B `bada9a5`) gave 145 files, 0 differences.
With `--agents off` the routing correction cannot act (no merchants), so
main and the head agree byte for byte. The frozen exact-trajectory oracles
(`test_performance_equivalence`, `test_governance_dormancy`) pass with no
fixture change: the correction touches only agent modes, so no golden
fixture moved and `ORACLE_CHAIN` gains no link. The flip pins cities off in
`scripts/benchmark_headless.run`.

Save/load resume identity with cities on: `tests/test_wave3_combined.py`
(cities and every other system on, `--agents off`) now also checks, turn by
turn for the 15 resumed turns, that every city-market input (the economy
columns for a fixed set of agent rows, the cut-off cities, the filtered
merchant graph) equals the uninterrupted run's.

## Tests

New: Rust `merchant.rs` (non-food price, food price with the tally,
market signal, timber by price, merchants spreading over two markets, an
exporter stopping, in-transit cargo counting), `economy.rs` (market
demand and supply, city labour, craft demand, bits without the inputs),
`tests/test_merchant.rs` (packet-known non-food by price, deliveries spread
over turns); `tests/test_city_markets.py` (region batch market columns; the
native economy's demand and supply; market columns consumed and reset
across ticks; city economy columns; the input batch only when on; sieges
and occupation cutting the graph; imports in commerce; city columns
consumed and reset per economy call; a hybrid run sending them); the
default-on and resume test; the resume identity extension; the viewer's
Cities panel and `lib/cities` tests.

Changed expectations, each from a change above:

- Routing: Rust tests that set `merchant_route_margin` to make a region
  a trade opportunity now make it a market (`set_market`: populated, short
  of food); the proxy test now routes timber by price;
  `tests/test_mutual_aid_adversarial.py` reactivates at turn 10, funded
  sends 4, 10, 11, 12 (was 4, 9, 10, 14).
- Flip: `test_cities.py` CLI tests pass `--no-cities` where they relied on
  the old default; `tests/test_bundle.py` records the guard world's sizes.

Verification on `e979fd9` (Linux, Python 3.13; extension built fresh from
the merged tree, `46f4fa81…c52b9b`, compiled module and classes verified):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 945 passed, 0 failed, 2 ignored (main 934) |
| `pytest -m "not slow" -n 3` | 6,046 passed, 3 skipped, 526 subtests (main 6,036) |
| `pytest -m slow -n 3` | 11 passed, 3 skipped |
| No-Rust lane (venv without `chronicler_agents`, every test) | 5,831 passed, 218 skipped (main 5,825 / 214) |
| `scripts/run_python_oracle_checks.py` | PASS in 67.6 s: 2,021 passed, 20 skipped; largest chunk 22.9 s of 110 s |
| Viewer `npm test`, `lint`, `build` | 276 tests passed (main 267); lint clean; build passed (existing large-chunk warning) |
| Bundle guard world (seed 1, 500 turns, agents off) | 18.78 MB native, 19.92 MB no-Rust (main 18.66 / 19.80; the cities field 0.12 MB); guard 24 MB |

Tick time (`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, 4
civs, hybrid, 20 warm-up and 8 measured turns, `--jobs 1`, default rayon
threads; medians, ms; main `3355289` against `e979fd9`). The machine was
shared with another agent's runs (load 3-4.5 on 4 cores), so wall times
are noisy; CPU times are the steadier measure.

| Target (alive) | Side | Rust tick wall / CPU | Turn wall / CPU | Runs |
| --- | --- | ---: | ---: | ---: |
| 18,800 (~23.5k / 22.1k / 21.6k) | main | 139 / 243 | 224 / 333 | 2 |
| | `--no-cities` | 146 / 239 | 201 / 294 | 2 |
| | `--cities` | 116 / 245 | 183 / 317 | 2 |
| 43,700 (~54.1k / 53.1k / 52.9k) | main | 499 / 1,119 | 661 / 1,518 | 4 |
| | `--no-cities` | 585 / 1,351 | 751 / 1,714 | 4 |
| | `--cities` | 544 / 1,366 | 683 / 1,762 | 4 |

- At ~22k the branch costs the same as main, cities on or off.
- At ~54k the measured turns cost about 20% more Rust CPU (turn CPU
  +13-16%). The planner is not the cause: on the first turns, with the
  same population, the branch's Rust tick costs the same or less
  (turn 0, 44,225 alive: 3,451 ms CPU against 3,704; turns 3 and 6
  equal). The worlds diverge after that: by turns 20-27 the branch has
  fewer merchants (6,975 against 8,420), more farmers (31,737 against
  28,533), half the packet-driven plans and twice the trade packets
  created, with as many live and transmitted packets. Per-turn cost then
  swings either way (turn 18 cheaper, turns 21 and 27 dearer). The
  Python side of a turn is unchanged (~360-400 ms CPU at ~54k).

## Open items

- **Needs oracle at subset scale.** Part A with cities off (now the
  `--no-cities` opt-out) on seeds 62-81 fails the required needs oracle,
  before and after the merge: 8 of 12 seeds (base 14). Seeds 42-61
  (13 -> 19) and 82-101 (19 -> 16) pass. At subset scale a seed's result
  rests on 1-4 matched pairs; with fewer deprived agents the material-need
  pairs that carried most seeds vanish.
- **Migration.** Part A lowers migration by about 0.0015 per agent-turn
  (better-fed worlds remember fewer famines); cities add some back.
- **City imports are small.** Merchant capacity (one unit) and the thin
  surplus of template worlds cap what a city can import; a bulk grain
  trade (carts, barges, an annona) would be its own slice.
- **Craft goods.** The economy has none; cities demand raw materials.
- **Tick cost at ~54k.** About 20% more Rust CPU in the measured turns,
  from a diverged world rather than the planner (see [Tests](#tests));
  a phase-timed profile would say which phase grows.
- **Sieges** are rare in template worlds (1 city-region-turn occupied in
  10 runs); the cut is tested directly, its aggregate effect is not
  measurable at this scale.
