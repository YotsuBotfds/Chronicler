# Food logistics, 2026-10

Branch `fix/food-logistics`, based on `integrate/wave-5` at `b7d9ced` (new-world
defaults: epidemiology, finance, diplomacy and techniques on; maritime, nomads
and great-person agendas off). It starts from the "Open items" of
[`food-balance-2026-10.md`](food-balance-2026-10.md). Two root causes are
**corrected** and one constant is **recalibrated**, one commit each; the golden
oracles are rolled forward in a fourth commit. Three more candidates were
verified and are not changed. No validation threshold, famine threshold or
food demand constant changed.

| Candidate | Finding | Action |
| --- | --- | --- |
| Merchant food routing ignores need | Real: a destination was scored by its own *export* margin, so empty and well-fed regions attracted the cargo | **Corrected** (`787ba4e`) |
| No subsistence without a food slot | Real: the goods economy lost M34's subsistence floor when it took over famine in agent modes (PR #11) | **Corrected** (`afe3b3d`) |
| Locust rate | Implausible: a swarm in 62% of eligible region-years; an M35b placeholder never calibrated | **Recalibrated** 0.15 -> 0.02 (`98ba9a2`) |
| Granaries / storage | Caps rarely bind (3% of region-turns); grain decay is within premodern storage losses | Not a bug |
| Drought/cooling double count | M34 deliberately routes drought through the crop climate factor *and* the water term | Design, not a bug |
| Occupational dead band | Real: M53 moved the exit threshold to the target but left entry at 2/3 of it | Fix measured; it lowers migration below the strict floor; **left open** |

**Status.**

- Food goes where it is needed: 70% of merchant food deliveries reach regions
  short of food (30% on the base) and 2% land in regions with no people (24%).
- Starvation is rarer and shallower: region-turns below 0.2 sufficiency fall
  from 24.5% to 13.7%, fed region-turns rise from 44.6% to 49.6%, winter
  shortfall from 67% to 61% of region-turns (plains 61% to 54%), and famines
  below 0.25 sufficiency from 43% to 32% of all famines. Famine events per run
  fall from 147 to 137; a famine is any shortfall in agent modes (see
  "Famine definition").
- Locust swarms cover 3.8% of eligible summer and autumn region-turns (25.5%).
- Template worlds end with 184 people on average (164), the smallest with 138
  (90); procedural 64-region worlds never fall below 625 (492).
- Full gate (200 x 500): **PASS strict**, 0 of 200 worlds extinct,
  `validation_compare` **NO REGRESSION** against the current defaults' full
  report; migration 0.0514 against the strict 0.05 floor (0.0512 on the base).

## Root causes and changes

Commit order. Template measurements use the default 8-region / 4-civ world
(`--agents hybrid`, seeds 42-51, 200 turns); procedural ones 64 regions / 16
civs, seeds 7-9, 300 turns. Sufficiency is the economy's pre-consumption food /
demand, clamped to [0, 2], over populated controlled region-turns. "Short" is
sufficiency below 1.

### 1. Merchants scored a destination by its own export margin (native)

`merchant::evaluate_route` (the oracle planner) scored a destination by
`origin_margin + dest_margin`, and `evaluate_route_packet_aware` (M59b) by
`origin_margin + packet_strength`, where a trade packet's strength is the
observed region's `merchant_route_margin`. That margin is the economy's
origin-side signal: the average gap from a region's prices to its trade
neighbours' prices, normalized by 5. It is high when a region is *cheaper* than
its neighbours: well supplied, or empty, because a region without people has no
demand and every price 0. M58a documented the destination term as a "bilateral
market-activity proxy" for M58b to refine with goods-level prices; M58b did not,
and M59b describes packet strength as "the destination's attractiveness". The
cargo was the origin's largest stock, whatever the destination needed.

Evidence (base, hybrid):

- 24.5% of merchant food deliveries landed in regions with no people, 45.2% in
  fed regions and 30.4% in regions short of food (procedural 26.6% / 53.8% /
  19.6%). Departures came only from fed regions.
- Route margin by region status (seed 43): empty regions median 1.0, the clamp
  (68% above the 0.10 trade-packet threshold); fed 0.0 (34%); short 0.31
  (54%). Empty regions were the best destinations and emitted the strongest
  trade packets.
- 85% of merchant plans were packet-driven (seed 43: 1,553 against 277
  bootstrap), so fixing only the oracle planner would not have mattered. 83% of
  departing cargo was food (grain 71%, fish 12%), timber 14%, ore 3%.

**Correction** (`chronicler-agents/src/merchant.rs`). Food (grain, fish, salt,
botanicals, exotic) travels by the food price gap. The planner's food price is
demand / supply = `1 / food_sufficiency`, the economy's own post-trade price
(0 where nobody lives; the economy's 0.1 floor caps it at 10), and the gap is
scaled by 5 into margin units so `MIN_TRIP_PROFIT` keeps its meaning: a fed
origin (sufficiency 1) does not ship to a market at 0.85, but does at 0.75. A
merchant first looks for a food trip (its home's largest food stock to the
known market where food is dearest); otherwise it carries its largest non-food
stock by the activity proxy, which is all the planner knows about other goods.
Food never travels by the proxy, and a region with no people is never a
destination. Packets still decide which markets a merchant knows (M59b gating
and its no-fallback rule are unchanged); the food price at a known market is
read live, as M58b's perfect-information price source does. No new random
draws; the tie-breaks are unchanged.

Template worlds after this commit alone: food deliveries to short regions 30.4%
-> 70.8%, to empty regions 24.5% -> 1.5% (procedural 19.6% -> 57.9% and 26.6%
-> 6.6%). The aggregate measures barely move by themselves: imports cover only
15-20% of a foodless region's demand (a merchant carries one unit), and famine
counts any shortfall. Procedural final population rises from 760 to 836.

### 2. The goods economy had no subsistence floor (agent modes)

M34's aggregate famine check gives a region whose food slots yield nothing
(none present, or all suspended, for example by locusts) a food yield of
`SUBSISTENCE_BASELINE (0.15) x crop climate` ("mountain villages survived on
terrace agriculture and herding; forest communities foraged"). Since PR #11
(`76e1d2a`) the goods economy decides famine in agent modes, and it had no
counterpart: a region without a food slot produced no food at all, and a locust
swarm left a grain region with nothing where the aggregate model falls back to
subsistence. On the base, 14% of populated template region-turns were in
regions without a food slot, at median sufficiency 0.0 (mountains 0.07,
forests 0.15).

**Correction.** Farmers who would work food land forage instead, at the same
baseline converted to goods on the grain scale,
`goods_per_worker(GRAIN, 0.15 x crop climate)`: 0.36 grain per forager in
temperate phases (0.32 warming, 0.18 drought, 0.25 cooling) against the 0.5 a
person eats, so a foraging region still needs imports. Barren food slots' labor
forages; without a food slot, foraging is one more food share in the food-first
split and every non-food slot keeps its 25% floor (an ore region of 30 farmers
short of food keeps 2.5 on ore). Foraged food is grain. Python computes the rate
(`ecology.subsistence_goods_per_worker`, read through the existing
`ecology.subsistence_baseline` key) and passes it as an optional
`subsistence_yield` column, 0 wherever a food slot yields (absent: no
foraging); the Rust kernel (`economy::allocate_farm_labor`) and the Python
oracle (`economy.farm_labor`) implement the same split, and a native/Python
parity case covers it. Off mode does not run the goods economy and is
unchanged.

On top of commit 1 (template): region-turns below 0.2 sufficiency 25.2% ->
13.4%, foodless regions' median sufficiency 0.0 -> 0.39, final population 165
-> 187 (smallest world 96 -> 142), famines below 0.25 sufficiency 44% -> 29%
of all famines.

### 3. Recalibration: locust swarm rate

This is a recalibration, kept in its own commit. M35b's spec table set
`LOCUST_PROBABILITY` to 0.15 "per-eligible-turn" with no calibration rationale
(`be6ee5c`, 2026-03-16); it was never revisited. M34, the same day, made the
year 12 turns (season = `(turn % 12) // 3`), so a plains or desert grain region
with soil above 0.4 is eligible six turns a year (summer and autumn), and a
swarm suspends grain and botanicals for 2-3 turns.

Base template worlds: 0.71 swarms per eligible region-year, a swarm in 62.5% of
eligible region-years, and 25.5% of eligible summer and autumn region-turns
under a swarm (procedural 25.0%): about a fifth of the annual grain harvest,
everywhere grain grows, every year.

Real locust damage is episodic. FAO describes desert-locust plagues as periods
of one or more years of widespread infestation separated by recessions of
several years (6-7 years on average before coordinated control lengthened
them); India recorded six plague spells between 1900 and 1962. Even the
2003-05 upsurge left Sahel cereal output within its five-year range, with
large local losses (Mauritania) but no national-level effect in Mali. The
Ming-Qing record (Tian et al. 2011, PNAS) has a locust report somewhere in
eastern China in about nine years in ten, across hundreds of counties; a single
locality is struck far less often. A swarm in most years in every eligible
region is not plausible.

**Recalibration.** 0.02 per eligible turn: a swarm in about 11% of eligible
region-years (`1 - 0.98^6`), one year in nine. The `emergence.locust_probability`
tuning key still overrides it (0.15 restores M35b); a swarm's duration and
effects are unchanged. This is the only change that moves off-mode
trajectories: the environment RNG draws a swarm's duration only when one fires,
so golden workloads with eligible regions change from their first summer turn
(see "Golden fixtures").

On top of commits 1-2 (template): locust turns 26.1% -> 3.8%, fed 45.4% ->
49.6%, winter shortfall 65.3% -> 60.6% (plains 61.1% -> 54.4%), famine events
155 -> 137 per run.

Determinism: no new random draws in the corrections (the recalibration changes
only how often an existing draw fires); stat changes keep their accumulator
categories; regions and civs are identified by index; the one new bridge
input, the economy batch's `subsistence_yield` column, is rebuilt every turn
and stored nowhere (Rust treats a missing column as no foraging). Saves load:
no persisted field changed.

## Verified, not changed

### Granaries and storage: not a bug

The per-good storage cap is 2.5 per head (five turns of demand per good), and
grain decays 3% a turn (fish 6%, botanicals 2%; salt preserves up to half).
Plains carry 1.0-1.5 turns of demand between seasons (autumn close 1.48,
winter close 0.95; base template), and only 3.1% of populated region-turns
(plains 5.0%) end with food at a single good's cap. Over a summer-to-winter
carry of about six turns grain keeps 83%, within the range of premodern
storage losses. Winter is short because too little is harvested and kept, not
because it cannot be stored; corrections 2 and 3 and the routing fix are what
moved it.

### Drought and cooling: designed, not a double count

Crop yield is `base x season x climate_mod x soil x water`. Drought cuts the
crop climate factor to 0.5 and drains water by 0.04 a turn; cooling cuts it to
0.7 and drains 0.02. M34 states the intent: "IRRIGATION gives +0.03 water
recovery. This already boosts crop yields because it sustains the water
multiplier in ecology_mod near 1.0 during drought". The water channel is meant
to act during drought alongside the climate factor, and M23 made water the
drought variable. The compounding is real (base template: 90% of cooling
region-turns and 72% of drought ones short, against 45% temperate and 36%
warming), and M34's worked example (drought winter grain 0.084 = 0.168 x 0.5)
assumed healthy water, but how much of a drought each channel should carry is
a climate-model calibration, not a defect. Unchanged.

### Occupational dead band: real; the measured fix lowers migration below the floor

`behavior::switch_utility` lets an agent leave an occupation above its target
(`OCCUPATION_SWITCH_OVERSUPPLY` 1.0) but enter one only below two thirds of its
target (`OCCUPATION_SWITCH_UNDERSUPPLY` 1.5). M26 paired a 2x exit with that
2/3 entry; the M53 baseline capture (`aff1b18`: "0.5 made the derived 2.0x
oversupply threshold unreachable for farmer-majority regions") moved the exit
to the target itself and left the entry alone. An occupation between 2/3 and 1x
of its target then neither gains nor loses; the band, a third of the target, is
about six workers for farming in a 30-agent region and about one for the small
occupations. Every newborn is a farmer, so labor drains out of farming and
circulates among the small occupations. Seed 43, base: farmer share 0.545
against an estimated target of 0.632; 497 switches out of farming and 126 into
it.

The fix was measured and not committed: entry when the alternative is short by
more than one worker (`SWITCH_MIN_SHORTFALL` 1.0), first on the entry side only
and then with the same one-worker margin on the exit side, to damp the seasonal
churn that the food-pressure swing of the farmer target causes.

| On commits 1-2 | Farmer share, seed 43 | Switches (top 20 flows), seed 43 | Template fed / famine / winter short | Subset occupation violations (42-61) | Subset migration (42 / 62 / 82) |
| --- | --- | --- | --- | --- | --- |
| Without | 0.545 (base) | 1,617 (base) | 45.4% / 155 / 65.3% | 0.15% | 0.0595 / 0.0491 / 0.0560 |
| Entry rule only | 0.588 | 3,822 | 50.7% / 132 / 59.5% | 1.04% (limit 1.0%) | 0.0518 / - / - |
| Symmetric margin | 0.586 | 2,448 | 53.5% / 118 / 57.6% | 0.77% | 0.0522 / 0.0426 / 0.0517 |

The symmetric variant feeds worlds better than any other change here, but it
lowers the subset migration rate by about 0.006 per agent-turn on average (more
agents have a positive switch utility, which competes with migration in the
same choice, and fed agents migrate less). The full gate's rate is 0.0514 at
the branch head against the strict 0.05 floor, so it would fail. It is left
open, with the patch in the run directory, for whoever owns the migration
oracle and agent-behavior calibration.

### Famine definition (noted)

In agent modes a famine event fires whenever sufficiency is below 1.0 (any
shortfall, 5-turn cooldown) since PR #11; the aggregate model fires below a
0.12 yield index. Famine counts therefore move little when food improves
unless regions cross 1.0, and the severity distribution says more. The
definition is unchanged; the tables report both.

## Before and after

`b7d9ced` against the branch, hybrid, cumulative by commit.

Template (8 regions / 4 civs, seeds 42-51, 200 turns):

| Measure | Base | Merchant routing (1) | + subsistence (2) | + locust rate (3, head) |
| --- | --- | --- | --- | --- |
| Region-turns analysed | 10,815 | 10,867 | 11,512 | 10,932 |
| Sufficiency p10 / p25 / median / p75 / p90 | 0 / 0.21 / 0.86 / 1.92 / 2 | 0 / 0.20 / 0.82 / 1.90 / 2 | 0.17 / 0.33 / 0.88 / 2 / 2 | 0.16 / 0.35 / 0.99 / 2 / 2 |
| Below 0.2 / below 0.5 | 24.5% / 37.0% | 25.2% / 38.0% | 13.4% / 34.3% | 13.7% / 32.2% |
| Fed (at least 1.0) | 44.6% | 43.0% | 45.4% | 49.6% |
| Mean sufficiency | 0.956 | 0.942 | 1.016 | 1.090 |
| Short in winter (all / plains) | 67.0% / 61.1% | 68.8% / 62.5% | 65.3% / 61.1% | 60.6% / 54.4% |
| Short in spring / summer / autumn | 54.2% / 47.9% / 53.1% | 56.5% / 49.2% / 53.9% | 53.8% / 47.9% / 52.1% | 50.3% / 44.2% / 47.0% |
| Foodless regions: region-turns, median sufficiency | 1,477, 0.0 | 1,878, 0.0 | 2,283, 0.39 | 1,959, 0.42 |
| Food deliveries per run | 724 | 538 | 649 | 656 |
| Food deliveries to short / fed / empty regions | 30.4% / 45.2% / 24.5% | 70.8% / 27.7% / 1.5% | 68.0% / 30.7% / 1.2% | 70.3% / 27.8% / 1.8% |
| Food deliveries eaten in a short region (next turn) | 22.5% | 41.3% | 38.6% | 39.6% |
| Famine events per run | 146.6 | 151.7 | 155.3 | 136.9 |
| Famines below 0.25 / 0.5 / 0.75 / 1 sufficiency | 43% / 17% / 17% / 23% | 44% / 17% / 16% / 22% | 29% / 27% / 20% / 25% | 32% / 25% / 20% / 24% |
| Farmer / merchant share | 53.1% / 14.3% | 53.2% / 14.1% | 53.3% / 13.7% | 53.3% / 13.9% |
| Agent migrations per agent-turn (probe) | 0.0549 | 0.0576 | 0.0578 | 0.0538 |
| Locust swarms per run; eligible turns under a swarm | 30.7; 25.5% | 30.7; 25.8% | 31.0; 26.1% | 4.7; 3.8% |
| Mutual-aid convoys per run | 13.4 | 12.5 | 8.7 | 10.2 |
| Population at turn 200, mean (smallest world) | 164 (90) | 165 (96) | 187 (142) | 184 (138) |
| Lowest population, any world and turn | 74 | 93 | 97 | 103 |
| Civs alive at the end | 3.3 | 3.1 | 2.7 | 2.6 |

"Food deliveries to ..." bins each merchant food arrival by the destination's
sufficiency in the turn it arrives; the next line bins it by the turn its cargo
enters the stock. The probe's migration count is the agent migration events
per agent-turn, the regression oracle's definition, over these 10 runs.

Procedural (64 regions / 16 civs, seeds 7-9, 300 turns):

| Measure | Base | 1 | 1-2 | Head |
| --- | --- | --- | --- | --- |
| Below 0.2 / fed | 23.3% / 45.2% | 21.7% / 45.1% | 18.9% / 46.2% | 17.1% / 45.7% |
| Short in winter (all / plains) | 67.5% / 71.8% | 67.0% / 75.9% | 65.5% / 75.3% | 66.1% / 72.5% |
| Foodless regions: region-turns, median sufficiency | 2,116, 0.0 | 2,753, 0.0 | 2,974, 0.29 | 3,489, 0.30 |
| Food deliveries to short / fed / empty regions | 19.6% / 53.8% / 26.6% | 57.9% / 35.5% / 6.6% | 60.3% / 32.2% / 7.5% | 60.5% / 31.6% / 7.9% |
| Famine events per run; below 0.25 | 1,417; 45% | 1,493; 43% | 1,511; 42% | 1,478; 37% |
| Locust: eligible turns under a swarm | 25.0% | 26.5% | 27.3% | 4.0% |
| Agent migrations per agent-turn (probe) | 0.0556 | 0.0619 | 0.0606 | 0.0621 |
| Population turn 0 -> 300, mean | 802 -> 760 | 803 -> 836 | 803 -> 811 | 803 -> 791 |
| Smallest world at turn 300 / lowest any turn | 493 / 492 | 809 / 552 | 743 / 375 | 628 / 625 |
| Civs alive at the end | 18.0 | 15.7 | 12.7 | 16.7 |

All procedural worlds survive in every arm. Epidemics (on by default) drive
swings of up to 40% within a run in every arm (base seed 9 ends at 493; seed 9
dips to 375 at turn 154 after commit 2 and recovers to 743), so three seeds
separate the arms less clearly than the template set. More people live in
foodless regions after commits 1-2 because they are no longer at zero.

## Golden fixtures

Corrections 1 and 2 do not touch the off-mode lane (it runs neither merchants
nor the goods economy): consecutive captures with the tests' own capture loops
reproduce `corrected_food_balance_2026_10.json` and its artifact oracles
exactly at `b7d9ced` and at `afe3b3d`. The recalibration moves it, so
`402230e` adds two live oracles (Python off mode, native ecology/politics
runtimes disabled, legacy timeline):

- `tests/fixtures/performance/corrected_food_logistics_2026_10.json`: turn
  hashes and RNG traces;
- `tests/fixtures/performance/corrected_artifacts_food_logistics_2026_10.json`:
  every emitted file's SHA-256 and byte count in the bundle-version-5
  projection (`workloads`) and, from the same run, the pre-pruning projection
  (`pre_pruning_workloads`).

`corrected_food_balance_2026_10*` and `corrected_artifacts_dead_civ_pruning_2026_10.json`
stay frozen. Provenance (first changed turn per workload, relative to the
oracle with all earlier changes applied):

| Change | single | standard | wide | Artifact files changed |
| --- | --- | --- | --- | --- |
| FL-MERCHANT-FOOD-PRICE | - | - | - | none (native merchants only) |
| FL-SUBSISTENCE | - | - | - | none (off mode has no goods economy) |
| FL-LOCUST-RATE (recalibration) | - | 3 | 3 | state, bundle, memories (standard, wide) |

`tests/test_performance_equivalence.py` adds the `food_logistics` link to
`ORACLE_CHAIN` (food balance -> food logistics), and
`tests/test_governance_dormancy.py` reads the new artifact oracle for both
projections and checks that only the declared workloads differ from the frozen
artifacts.

## Tests changed and why

New tests:

- Rust `merchant.rs`: the planner's food price (1 / sufficiency, 0 without
  people); food goes to the short market, not the cheap or empty one; food
  stays home without a dearer market while timber uses the proxy and skips an
  empty region; a 0.176 price gap does not pay for a trip and 0.333 does.
- Rust `tests/test_merchant.rs`: among packet-known markets food goes to the
  short one whatever the packet strength, an empty region is not a market, and
  without a dearer known market there is no trip and no oracle fallback.
- Rust `economy.rs`: foraging only when no food slot yields; the no-food-slot
  split (food share, 25% floor, all forage without slots, labor conserved);
  barren food slots forage; foraged grain reaches stock, sufficiency and
  conservation.
- `tests/test_food_logistics.py` (15 cases): the subsistence rate is M34's
  baseline in grain goods for every climate phase and reads the tuning key; it
  stays under half a ration; the Python labor split mirrors the Rust cases;
  production credits foraged grain; the locust swarm fires below 0.02 only,
  the key still overrides, and 0.02 gives a swarm in 10-12% of eligible years.
- `tests/test_economy_coupling.py`: a native/Python parity scenario for a
  region without a food slot that forages.
- `tests/test_governance_dormancy.py`: the food-logistics artifact oracle
  differs from the frozen artifacts only for its declared workloads.

Changed expectations, each following from a change:

- Merchant routing (1). Fixtures that planned trips between unpopulated,
  equally fed regions now give the destination people and a shortage, or
  carry timber where they test the activity proxy:
  - Rust `merchant.rs` route tests: regions have 20 people; the profitable and
    tie-break tests make regions 1 and 2 short (sufficiency 0.5); the
    tie-break also asserts the lower region wins.
  - Rust `tick.rs::test_death_releases_loading_and_transit_once_before_slot_reuse`:
    region 3 has 20 people at sufficiency 0.5.
  - Rust `tests/test_merchant.rs`: the linear world has 20 people per region,
    region 2 at 0.5 and region 3 at 0.4 (3 is still the oracle's choice, 2 the
    packet one); the two planning-margin tests carry timber; the one-hop
    lifecycle test makes region 1 short.
  - Rust `tests/test_maritime_raid.rs`: same linear-world change.
  - `tests/test_mutual_aid_adversarial.py`: merchants now carry food to the
    stressed Mine, so its fresh stress starts a turn earlier: aid reactivates at
    turn 9 (was 10), and in the funded run that convoy leaves the Mine at 0.44
    sufficiency, so aid sends again at turn 10; funded sends are 4, 9, 10 and 14
    (were 4, 10, 14).
- Subsistence (2):
  - `tests/test_economy_bridge.py`: the economy input batch has 18 columns,
    `subsistence_yield` after the resource columns (was 17).
  - Harnesses whose specification is a food-less region keep it food-less with
    `ecology.subsistence_baseline = 0` (older sources ignore the key):
    `scripts/qualify_third_wave.py` (its independent ledger splits labor
    equally over slots), `scripts/mutual_aid_adversarial.py` (the Mine's stress
    is what aid answers), `scripts/mutual_aid_long_cargo.py`, and in
    `tests/test_economy_coupling.py` the phantom-goods and no-route/no-surplus
    tests and the mixed-inventory parity scenario.
  - `scripts/economy_coupling_experiment.py`: the expected harvest includes
    foraging (falls back on sources without it).
  - `tests/test_maritime.py::test_hybrid_merchants_cross_sea_lanes_and_are_raided_deterministically`:
    60 turns (was 40); this world's first merchant sea crossing now comes after
    turn 40 (12 crossings by turn 60).
- Locust rate (3):
  - `tests/test_checkpoint_replay.py::test_resumed_state_json_matches_uninterrupted_across_a_suspension`
    pins the M35b 0.15 through the tuning key in both worlds (`701bd92`): it
    needs a suspension across its turn-6 save point, and 0.02 fires none there.
  - Golden oracles: see "Golden fixtures".

## Verification

On `701bd92` (the last simulation-relevant change is `98ba9a2`; Rust last
changed in `afe3b3d`), Linux, Python 3.13. The native extension was built from
this tree with `maturin develop --release`; the installed
`chronicler_agents.chronicler_agents` module (SHA-256 `a52d56c3...c5d9`, the
same bytes from two separate builds of `afe3b3d`) exposes `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` as classes. The base build (archived
`b7d9ced`, own venv) is `2a9861de...548d43`, the same bytes as the first base
build in this worktree.

- `pytest -m "not slow" -n 2`: 5,859 passed, 3 skipped (base 5,844).
- Slow tests (`-m slow`): 11 passed, 3 skipped.
- No-Rust environment (fresh venv without `chronicler_agents`): 5,651 passed,
  197 skipped (base 5,637 / 196).
- `cargo test --release`: CARGO_RESULT.
- Offline Python oracle lane (`scripts/run_python_oracle_checks.py`, PR #19's
  guard fix applied locally and reverted): 1,852 passed, 9 skipped, 2
  deselected, guard PASS, 63 s.

## Gate results

Gates on the current defaults (`--parallel 3`). Only report files are kept,
outside the repository.

### Full (200 seeds x 500 turns, hybrid)

On `98ba9a2` (C1-C3; later commits change only tests, fixtures and docs).
**PASS, strict: every required oracle passes; 0 of 200 worlds extinct.**
`validation_compare` against the techniques-on full report (the current
defaults' gate): **NO REGRESSION**. A full gate on `afe3b3d` (C1-C2) also
passed strict with no regression.

| Oracle / measure | Current defaults (full-on report) | `afe3b3d` (1-2) | `98ba9a2` (head) |
| --- | --- | --- | --- |
| regression | PASS strict | PASS strict | PASS strict |
| satisfaction mean / latest (ceiling 0.65) | 0.594 / 0.604 | 0.597 / 0.608 | 0.602 / 0.611 |
| migration per agent-turn (floor 0.05) | 0.0512 | 0.0545 | 0.0514 |
| rebellion per agent-turn | 0.0503 | 0.0516 | 0.0513 |
| Gini in range / occupation violations | 85.1% / 0.20% | 82.0% / 0.18% | 82.6% / 0.16% |
| all-founder survival (limit 0.20) | 0.110 | 0.105 | 0.115 |
| final population min / median / max | 36 / 170 / 349 | 36 / 182 / 303 | 52 / 183 / 329 |
| artifacts | PASS (1.25 per civ per 100 turns; loss 5.1%) | PASS (1.24; 5.1%) | PASS (1.23; 4.3%) |
| arcs | PASS (6 families; 166 seeds with three types) | PASS (6; 159) | PASS (6; 166) |
| era | PASS (200 with inflections, 0 silent) | PASS (200, 0) | PASS (200, 0) |
| needs | PASS (188 seeds) | PASS (190) | PASS (192) |
| cohort / community | PASS / PASS | PASS / PASS | PASS / PASS |
| determinism | SKIP (no duplicate seeds) | SKIP | SKIP |

### Subsets (20 seeds x 200 turns, hybrid), base against head

| Seeds | Gate base / head | Comparator | Migration base / head | Satisfaction base / head | Notes |
| --- | --- | --- | --- | --- | --- |
| 42-61 | PASS / PASS | NO REGRESSION | 0.0577 / 0.0563 | 0.580 / 0.588 | Base regression FAIL (`civ_survival` 0.25, informational in the subset) is PASS on the head (0.15); arcs FAIL on the head (cinderella 41% of arcs against a 40% limit; 24% in the full profile), informational |
| 62-81 | FAIL / PASS | NO REGRESSION | 0.0474 / 0.0460 | 0.599 / 0.611 | The base fails the required needs oracle (11 of 12 seeds), as the techniques default recorded; the head passes it (12) |
| 82-101 | PASS / PASS | NO REGRESSION | 0.0539 / 0.0491 | 0.591 / 0.603 | |

Artifacts read PARTIAL on head seeds 62-81 and 82-101 and on base seeds 42-61
(loss rate below its band, which is calibrated for 500 turns); informational.

## Open items

- **Occupational dead band.** Real and measured (see above); fixing it feeds
  worlds better than anything else here but takes the migration oracle below
  its strict floor. It needs a decision on the migration oracle (calibrated on
  starving worlds, like the others `wave3-defaults.md` revisited) or on how
  switching and migration share an agent's turn.
- **Migration margin.** The head's full-gate migration is 0.0514 against the
  0.05 floor, the same margin as the base (0.0512); every food improvement
  measured here lowers it.
- **Packet information.** Trade packets still encode the observed region's
  export margin; food routing reads the live food price of packet-known
  markets. A packet that carried the destination's food price would make food
  routing subject to M59's information lag as well.
- **Non-food routing** still uses the activity proxy; the planner has no
  per-region prices for raw materials or luxuries.
- **Herding.** All merchants at one origin pick the same best market in a
  turn; at template scale (a few merchants, one unit each) that rarely
  overshoots a deficit, but larger worlds may need a per-turn delivery tally.
- **Drought/cooling calibration** and the **famine definition** (any
  shortfall) are unchanged; both are documented above.
- **Fewer polities.** Civs alive at the end fall somewhat in template worlds
  (3.3 -> 2.6 over 10 runs); procedural worlds vary (18.0 -> 16.7).

## Reproduction

The probe and analysis scripts live outside the repository. Measurements come
from ordinary runs (`python -m chronicler.main --seed S --turns T --agents
hybrid --simulate-only`, plus `--worldgen procedural --regions 64 --civs 16`)
with the economy result, delivery diagnostics, agent migrations and occupation
snapshots read each turn. Gates are `scripts/m53b_run_validation.py --profile
subset|full --parallel 3`, compared with the base subset reports and, for the
full profile, the techniques-on full report.
