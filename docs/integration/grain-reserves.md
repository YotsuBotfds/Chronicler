# Public granaries: stock-target grain procurement and reserves (`--grain-reserves`)

Branch `feat/grain-reserves` from `main` `3c3775d` (PR #55), fast-forwarded to
`6da8fe5` (PR #56, narration provenance: narration only, simulation output
unchanged) before any commit. Code: `src/chronicler/grain_reserves.py`
(behaviour, the resource ledger), `src/chronicler/grain_reserves_state.py`
(persisted state), hooks in `simulation.py` (Phase 2 and Phase 10),
`action_engine.py` (conquest), `war/occupation.py` and `war/battles.py`
(occupation and siege requisitions), `sidecar.py` (the granary ledger file),
`main.py`, `live.py`, `batch_manifest.py`, `run_checkpoint.py`,
`analytics.py`, `narration_context.py` and `historiography.py` (one routine
type); `scripts/m53b_run_validation.py` (`--grain-reserves`),
`scripts/grain_reserves_probe.py` (paired measurement). No Rust change: the
native extension built from the branch is byte-identical to `main`'s
(SHA-256 `99c1e1d5...ee12f`).

An external review recommended stock-target grain procurement and reserves
that reuse real surplus, route permissions, commitments and transit losses,
noting that ship capacity binds on only about 1% of crossings. This branch
audits how food moves (section 1), adds granaries behind a switch, default
off (sections 2-3), checks their balances (section 4), proves the switch
off identical to `main` (section 5), resumes checkpoints with it on
(section 6), measures it (section 7), runs the gates with it on (section
8) and tells it (section 9).

**Status.** Implemented behind `--grain-reserves`, off by default, and
kept off: this branch does not propose turning it on. Switch off: every
output byte-identical to `main` (section 5). Switch on: every checked run
balances its granary ledger (section 4) and resumes from checkpoints with 0
differences (section 6); granaries take about an eighth of the short severe
shortages away and lower deaths per agent-turn by 1.5-4% (section 7), with
modest reserves (12-17% of their targets) and spoilage about equal to the
release. Gates with the switch on (section 8): template full 200 x 500 and
procedural full 100 x 300 PASS strict, EXPLORATORY NO REGRESSION against
`main`; the template subset 42-61 fails the needs oracle where `main`
passes (20 seeds). With `CHRONICLER_CHECK_RESOURCES=1` the production
ledger's mines' soil check stops some procedural worlds, `main`'s as well:
a native ordering of PR #52, not a granary balance (section 4).

## 1. Audit: how food moves today

### Who holds food, and why

| Stage | Where | What decides it | Plans ahead? |
| --- | --- | --- | --- |
| Production | Phase 2, native goods economy (`economy::tick_economy_core`): yields (season, regional climate, soil, water, techniques) x food-first farm labour on the farm curve; foraging where no food slot yields | farmers' occupation choices (agents) | no |
| Market stock | `Region.stockpile` per good: last turn's stock + production + imports - exports, before the people eat | nobody: it is what is left | no |
| Food sufficiency | food on hand before eating over demand (0.5 a head), clamped 0-2 | the economy | - |
| Consumption | demand drawn from every food good in proportion | fixed ration | - |
| Storage loss | grain 3% a turn, fish 6%, botanicals 2%, exotic 4%; salt preserves up to half of it | the economy's constants | - |
| Storage cap | 2.5 a head per good (five turns of demand); the rest is destroyed (`cap_overflow`) | the economy's constant | - |
| Prices | demand over post-trade supply per category (`market_demand` / `market_supply`); farmer income follows | the economy | - |
| Merchants | native agents: a trip carries the home market's largest food stock to the known market where food is dearest (1 / sufficiency), against a per-tick tally of committed cargo; loads by mode of travel (2 overland, 5 by river, 10 by sea); reservations and departures are commitments on the origin's stock; 5% grain transit decay on arrival | price gaps seen now (trade packets) | no: they react to today's prices |
| Mutual aid (default on) | before the economy at N+1, adjacent regions of one ruler: a fed donor (beyond two turns of its demand, at most a quarter of it) sends to a region short for three turns (at most half its demand); treasury 0.1 a unit; transit decay | three turns of reported stress | no: it answers hunger already there |
| Allied relief (`--diplomacy`, default on) | an ally sends treasury (up to 10) to a famine-struck ally | a famine or dearth report | no; and no food moves |
| Conquest, occupation, siege | a conquest destroys half of every stock; an occupation takes 20% of the food, a siege 15% a turn | war | - |
| Famine labels, mortality | Phase 9: dearth (below 1) or famine (below 0.6 for three turns) reports; the agents' deaths, births, needs, satisfaction and famine-memory migration read this turn's sufficiency | the economy's sufficiency | - |

Nobody decides to hold food. A region's stock is the residual of its harvest,
its people's ration and the merchants' trips, capped at five turns per good.
Every response to hunger is reactive: merchants follow today's prices, mutual
aid answers three turns of stress, allies send money after a report. No actor
buys ahead of a shortage, and none stores more than the market's cap.

### Measured flows

Read-only probe of `main` (`6da8fe5` simulation; the probe wraps the
economy's result reconstruction and the native delivery diagnostics, outside
the repository): template seeds 42-49 and procedural 32 x 10 seeds 42-43, 200
turns, hybrid, current defaults.

| per world, 200 turns | template (8 worlds) | procedural (2 worlds) |
| --- | ---: | ---: |
| food demand | 17,877 | 64,500 |
| production | 16,696 (93% of demand) | 65,425 (101%) |
| consumption | 14,993 (84% of demand) | 58,800 (91%) |
| storage loss | 678 (4.1% of production) | 2,482 (3.8%) |
| destroyed above the storage cap | 1,089 (6.5%) | 3,685 (5.6%) |
| merchants' food departures | 373 (2.2%) | 1,854 (2.8%) |
| merchant transit loss | 17 | 86 |
| mutual aid delivered | 7 | 64 |
| populated region-turns fed / dearth (0.6-1) / below 0.6 | 48.0% / 24.1% / 27.9% | 58.3% / 17.9% / 23.8% |
| post-consumption stock above 1 / 2 / 3 turns of demand | 27.7% / 19.6% / 13.4% of region-turns | 30.3% / 19.3% / 12.3% |
| food price in regions with more than two turns in stock (median) | 0.21 | 0.22 |

The cap and storage destroy 10.6% of the template world's food (9.4% on
procedural worlds), three to five times what the merchants carry, while 16% of the
demand goes unmet (9%). The surplus is not where or when the hunger is. At
a dearth or famine turn, food beyond two turns of need in the region's own
realm (within four steps through its land) covers 3.9% of the shortfall
(8.4% procedural); in foreign regions next to the realm 9.5% (26.7%); all of
it together 11% (31%). Of 52 template regions with 20 or more populated
turns, 27 are short in more than half of them and rarely hold a surplus;
15 alternate. The harvest's coefficient of variation counted up to the need
(below) is 0.33 at the median (0.29 procedural); regions where it is above
0.5 are short in 74-95% of their turns (73-86%), below 0.1 in 14% (3%).

So the binding constraints are distance in time and space and the cap, not
cargo capacity: little of the surplus coincides with a shortfall within
reach, and what overflows is destroyed. A reserve can only help by carrying
grain from the turns and places that overflow to the ones that starve.

## 2. Design

### Actor

The ruler of a region keeps its granary: one granary per region,
`GrainReserveState.granaries[i]` for `world.regions[i]`, owned by the civ
index of its controller. Civs are the actors with a treasury in every region
they hold; cities' civic purses exist only where there are cities and are
not used.

### Target

Turns of the region's food demand in proportion to the observed swing of its
own harvest:

    target = min(MAX_TURNS, TURNS_PER_CV x cv) x demand        (TURNS_PER_CV 6, MAX_TURNS 4)

`cv` is the coefficient of variation of the region's food harvest (its food
slots' output and foraging) over its food demand, counted up to the need
(`HARVEST_CAP` 1: grain beyond the need feeds no shortfall), as exponential
means over about a year (`HARVEST_EMA` 1/12) of the ratio and its square. A
region whose harvest always covers its people, or never varies, keeps no
reserve: a steady shortfall is trade's to cover, not a granary's. A grain
region with the seasons' swing (cv about 0.3-0.45) holds two to three turns.

### Procurement (Phase 10)

After the merchants planned their trips (Phase 9) and the turn's income and
finance (Phase 3b), before the Phase 10 accumulator flush:

* **Real surplus only.** A market sells grain it holds beyond its merchants'
  commitments (cargo loading there and departures awaiting the next economy
  tick, `get_stockpile_commitments`, as mutual aid reads them) and beyond
  `KEEP_TURNS` (4) turns of its own food demand (all food goods counted).
  The market's carry and the merchants' trade come first; the granary takes
  what would otherwise sit near the five-turn storage cap.
* **Price.** The selling market's food price, demand over post-trade supply
  (`EconomyResult.market_demand` / `market_supply`), in the value units of
  merchant income (taxed into the treasury one for one). Paid in whole
  treasury units: a purchase of `cost` coins takes `cost / price` grain.
* **Budget.** At most `BUDGET_SHARE` (10%) of the projected treasury above
  `TREASURY_FLOOR` (20) a turn.
* **Order.** Every ruler first buys in its own realm, then (a second pass,
  so each ruler has first claim on its own surplus) abroad; civs in index
  order. Its granaries buy emptiest against their target first (ties:
  hungriest, then region index). For a granary, the sources are its own
  market, then its realm's other regions within `MAX_HOPS` (3) steps of
  the route graph through its own land (nearest, then cheapest); abroad,
  the regions one step beyond those (cheapest first).
* **Route permissions.** The route graph is the merchants'
  (`economy.build_merchant_route_graph`, the maritime blockade filter, the
  cities' siege cut-off): no step across a war, an embargo, a hostile or
  suspicious disposition on either side, a suspended route, a blockaded sea
  lane or a besieged or occupied city. A foreign seller is a neighbour on a
  permitted edge (contact by adjacency).
* **Transit.** Grain from another region loses `TRANSIT_DECAY["grain"]`
  (5%) on the way, as a merchant's cargo does; grain bought in the
  granary's own market loses nothing.
* **Payment.** Grain bought in the realm is paid to its own producers: the
  coins leave the treasury (`keep`). Grain bought abroad is paid to the
  seller's ruler through `finance.transfer` (treasury `keep` both sides;
  with finance on, specie moves too).

### Release (Phase 2)

Right after the goods economy computed this turn's food sufficiency and
before anything reads it (supply-shock detection, mutual aid's observation,
the agents' tick in Phase 9, the famine labels, epidemics next turn):

* where food on hand is below the need (sufficiency below 1: dearth or
  famine), a granary holding at least `RESERVE_FOR_FAMINE` (half) of its
  target covers the whole shortfall; one holding less lifts the people only
  to the famine line (sufficiency 0.6) and keeps the rest for worse;
* the released grain is eaten that turn; the economy result's food
  sufficiency is raised by release / demand and its post-trade food supply
  by the release. Prices and incomes the economy already computed stay: the
  grain is handed out, not sold.

### Storage, conquest, owners

* Spoilage: `STORAGE_DECAY["grain"]` (3%) a turn after the release, the
  market's grain rate without salt; crumbs below 1e-6 spoil at once.
* A conquest (`apply_region_conquest`) destroys the share of the granary a
  conquest destroys of the region's stocks (half); an occupation takes 20%,
  a siege 15% a turn, as they do of the market's food.
* A new ruler takes over the rest at the next Phase 2 (`captured`). A
  region without a ruler gets its granary's grain in its market
  (`abandoned`).

### Events

| type | when | importance |
| --- | --- | --- |
| `granary_opened` | the first release of an opening that feeds at least a tenth of the turn's need ("X opens its granary in R against the dearth/famine: G grain feeds the hungry (food a -> b of need)"); cites the open famine or dearth report | 4; 5 below 0.6 |
| `granary_exhausted` | an announced opening runs out ("The granary of X in R is empty ...") | 4; 5 below 0.6 |
| `grain_bought` | a ruler bought grain abroad this turn (one event per buyer, sellers in `civs`) | 2, routine |

Famine or dearth in the text follows the labels' rule (a famine is a severe
shortage in its third turn). `grain_bought` is routine for the narrator and
never chronicled by the in-world historians; the other two weigh by their
importance. All three go through the turn's provenance observer, so they
carry event ids and their causes.

### Contracts

* Identity: region index, civ index. No random draws.
* Accumulator: treasury `keep` (purchases, foreign receipts).
* Append-only orders: `FLOW_KINDS`, `COUNTER_KEYS`, `EVENT_TYPES`.
* No bridge signal: the release patches the economy result Python already
  hands to the agent tick; nothing transient survives the turn (the
  turn's ledger, a private attribute, is cleared at the end of the Phase 10
  tick).
* Dormant under `--agents off` (no goods economy): an explicit
  `--grain-reserves` with `--agents off` is refused, a saved setting is a
  strict no-op.

### Turn placement

| When | What |
| --- | --- |
| Phase 2, after the economy's result | owners (captured, abandoned); releases; spoilage |
| Phase 5 | conquest (half), occupation (20%), siege (15%) |
| Phase 10, after scholarship, before the flush | harvest means and targets; procurement (realm, then abroad) |

### Considered and not adopted

Measured on template seeds 42-49 (and 50-65 for the last two), 200 turns,
paired with the switch off:

| variant | released / spoiled per world | severe share | famine share | deaths per 1,000 agent-turns | merchant food departures |
| --- | ---: | ---: | ---: | ---: | ---: |
| base 2 turns x (1 + cv), uncapped harvest, full release, keep 2 | 512 / 442 | -1.5 pts | +1.2 pts | -0.36 (SE 0.54) | -22 |
| capped harvest, 6 x cv up to 4 turns, full release, keep 2 | 334 / 249 | -1.2 | +0.8 | -0.08 (0.34) | -78 |
| the same, release to the famine line below half the target, keep 2 (16 worlds) | 392 / 320 | -2.5 (0.5) | +1.0 (0.65) | -0.24 (0.31) | -69 (21) |
| the same, smaller targets (3 x cv up to 2 turns), keep 2 (16 worlds) | 304 / 176 | -1.6 (0.4) | +1.3 (0.8) | -0.54 (0.25) | -67 (20) |
| **shipped: capped, 6 x cv up to 4 turns, famine line below half, keep 4** (16 worlds) | 195 / 208 | -1.4 (0.4) | -0.4 (0.6) | -0.42 (0.25) | -37 (15) |

The uncapped harvest's swing gave surplus regions large targets they filled
from their own markets and rarely released (spoilage near the release).
Selling beyond two turns of need took surplus the merchants would have
carried to short regions (their food departures fell by 15%), and
sustained famine rose by about a point in every two-turn variant; four
turns leaves the merchants their trade and the famine share does not rise.

## 3. Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--grain-reserves` / `--no-grain-reserves` (`BooleanOptionalAction`); needs an agent mode |
| World field | `WorldState.grain_reserves: GrainReserveState \| None` (presence = on), omitted while `None` |
| Default | off for new worlds (`grain_reserves.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`); resumed, forked and caller-supplied worlds keep their saved setting |
| Live | new live worlds follow the default (`live.py`) |
| Gate runner | `scripts/m53b_run_validation.py --grain-reserves` forwards the switch and records it in `run_manifest.json`; `batch_manifest` names `grain_reserves` among the simulation arguments |
| Checkpoints | the PR #54 envelope pickles the world with its granaries (and the sidecar's granary rows); the header's switches name `grain_reserves` |
| Bundle | `world_state.grain_reserves` (granaries, the last turn's flows, counters) while on; no per-turn snapshot field (the transport contract and viewer are unchanged) |
| Validation sidecar | `validation_reserve_ledger.arrow` while on (not a validator input) |
| Analytics | `generate_report` gains `grain_reserves` for runs that carry it |
| Old saves | load with `grain_reserves` None |

## 4. Conservation and the resource ledger

No grain or money is created. Grain leaves a market only as surplus sold
(`sent`), reaches a granary less its transit decay, and leaves a granary
only as a release (eaten), spoilage, a seizure or an abandonment (back to
the market). Money leaves a buyer's treasury as the purchase price and goes
to the seller's ruler (abroad) or to the realm's producers, outside the
treasury accounts (at home), as upkeep does.

`CHRONICLER_CHECK_RESOURCES=1` (PR #52's switch) now also builds the granary
ledger (`grain_reserves.ReserveLedger`) every turn with granaries on, and
raises `AssertionError("resource ledger does not balance at turn N
(granaries): ...")` when:

* a granary's grain at the end of the Phase 10 tick is not its grain at the
  Phase 2 tick plus what it received, less releases, spoilage, seizures and
  abandonment, or is negative;
* a market's grain changed in a granary tick by other than the grain it
  sold or received from an abandoned granary, or went negative, or sold more
  than its free surplus;
* a shipment's grain received is not the grain sent less the transit decay
  (from another region) or the grain sent (own market); a purchase cost
  nothing or bought nothing;
* a release came at or above a full meal or exceeded the shortfall, or the
  economy's sufficiency is not the recorded one plus release / demand;
* spoilage is not the storage rate of the grain held;
* a buyer's projected treasury did not fall by its payments, or a foreign
  seller's did not rise by its receipts.

Negative controls (tests): grain added to a granary outside the flows, and a
transfer that credits the seller without debiting the buyer, both raise. With
the validation sidecar the per-turn rows (one per granary that held or moved
grain: grain before and after, bought, released, spoiled, seized,
abandoned, target, sold from its market, paid, sufficiency before and after
its release) are written as `validation_reserve_ledger.arrow`.

Runs checked with `CHRONICLER_CHECK_RESOURCES=1`, every turn balanced: the
60-turn hybrid run of the native test (template seed 42, sidecars), every
straight and resumed run of the checkpoint matrix (section 6: hybrid,
procedural 32 x 8, demographics-only, shadow and fast-scale worlds, 40-200
turns, with and without `--scholarship`), and 31 procedural 32 x 10 worlds
of 300 turns (seeds 42-72, hybrid, sidecars). The production ledger's own
checks ran alongside in the same runs, all of them in the first two groups;
in the procedural worlds all but its mines' soil check (below). The
procedural full gate ran without the checks (section 8); its 100 worlds x
300 turns balance offline from their `validation_reserve_ledger.arrow`
(167,933 rows, 0 problems): each row's grain after is its grain before plus
the turn's flows and never negative, each granary's rows chain from turn to
turn, its last row is the final state's grain, and the rows' sums are the
final counters (received, released, spoiled, seized, abandoned, paid). A copy
with one row's grain changed by 0.01, or one release dropped, fails that
verification.

**The production ledger's mines' soil check (PR #52) and the switch on.**
With `CHRONICLER_CHECK_RESOURCES=1` the procedural full gate stopped in
seed 42 at turn 128: "region 25: mines took 0.012847907841205597 of soil,
the rule says 0.01177724960944243". The check is native against native:
the ecology tick records `mine_crew_ratio` (output over the target crew, a
third of the effective capacity) before the soil step, and the soil step
(`tick_soil_controlled_ledger`) first takes the overpopulation degradation
(population above the land's potential: 47 against 44 here) and then
computes the crew ratio again for the charge, from the lowered soil. When
that loss (0.005, more under soil pressure) moves the effective capacity
across a multiple of three, the charge's crew is one smaller (12 -> 11
here: 0.012848 / 0.011777 = 12 / 11), and the charge differs from the rule
as documented ("the crew from the effective capacity before this turn's
soil change", production-ledger.md section 6). The ordering is `main`'s, in
Rust this branch does not change.

Recorded instead of raised (every other check raising), over procedural
32 x 10 seeds 42-72, 300 turns: 10 mismatches in 7 of the 31 worlds with
the switch on, and 3 in 3 worlds on `main` (seeds 58, 64 and 69; `main`'s
seed 42 ran its 300 turns with every check raising). In each the charge's
crew is one smaller than the ledger's (ratios 16/15 to 4/3), every one in a
region above its land's potential. So `main`'s own procedural full gate
stops too with the checks on; with the switch on, and its larger
populations (section 7), the mismatch shows about three times as often.
Not fixed here, since either fix belongs to a correction of its own: the
charge reading the crew from before the soil step (as documented; it moves
`main`'s trajectories wherever it fires), or the ledger recording the crew
the charge used (no trajectory change; the documented rule changes). The
gate was rerun without the checks, as `main`'s baseline and the template
gate ran (section 8).

## 5. Switch off: byte-identical to `main`

Linux, Python 3.13.17, `PYTHONHASHSEED=0`. `main`: an export of `6da8fe5`
(its Rust is `3c3775d`'s) in its own virtualenv with its own release build;
branch: an export of the code commit `49cd760` in its own virtualenv with
its own release build (`maturin develop --release --locked`, `CARGO_TARGET_DIR`
inside the run directory). Both extensions are
`99c1e1d577e1f7f7e627e8a6ea9dc9fa745e98dd8a953a91735a7a0c237ee12f`, with
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` real classes.

| Comparison | Result |
| --- | --- |
| `scripts/turn_speed_identity.py run` (the 9-case matrix: template seeds 42 and 7 off 300 turns, hybrid 200 turns with sidecars, seed 1234 hybrid, procedural 48 x 10 hybrid and off, about 22k and 52k agents), branch without the flag | 9 cases, 399 files, **0 differences** (bundles decoded and raw with `generated_at` blanked) |
| the same, `--cli-arg=--no-grain-reserves` | 9 cases, 399 files, **0 differences** |
| hybrid batch, `--batch 3 --seed 42 --turns 100 --validation-sidecar` (`scripts/cities_identity.py compare`), without the flag and with `--no-grain-reserves` | 182 files, 1 difference each: `batch_manifest.json` (run identity: timestamps, interpreter and package paths, source digest, the new `simulation.grain_reserves` None / False, the raw bundles' hashes, whose only difference is `generated_at`) |
| procedural 32 x 10, seed 11, 150 turns, hybrid with sidecars, without the flag and with `--no-grain-reserves` | 92 files, **0 differences** each |

The batch manifest's new key is read by the comparator as the CLI default
when a manifest lacks it, so switch-off reports stay comparable with `main`'s.

## 6. Checkpoints with the switch on

`scripts/checkpoint_identity.py run --cli-arg=--grain-reserves --jobs 2`
with `CHRONICLER_CHECK_RESOURCES=1` (every resumed and straight run also
checks the granary ledger each turn), branch export `49cd760`:

| case | turns | resume points | files compared | differences |
| --- | ---: | ---: | ---: | ---: |
| `hybrid_s42` (sidecars) | 60 | 59 (every turn) | 1,839 | 0 |
| `proc32_hybrid_s11` (procedural 32 x 8, sidecars) | 40 | 39 | 1,215 | 0 |
| `demographics_s42` | 40 | 39 | 351 | 0 |
| `shadow_s42` | 40 | 39 | 429 | 0 |
| `hybrid_s1234_fast` (`--agent-scale-mode fast`) | 40 | 39 | 390 | 0 |
| `hybrid_s42_long` (sidecars) | 200 | 19 (spread) | 1,635 | 0 |
| `hybrid_s7_long_scholarship` (sidecars, `--scholarship`) | 200 | 19 | 1,635 | 0 |

253 resume points, 7,494 resumed files and 340 plain-against-checkpointed
files, 0 differences; the resumed runs write the same
`validation_reserve_ledger.arrow`. Checkpoints are 0.21-1.52 MB at their
largest. The envelope needed no change: the world's granaries are model
fields of the pickled world, the turn's ledger is cleared before the turn
ends, and the sidecar's granary rows travel with the pickled sidecar.

## 7. What granaries do (paired worlds)

`scripts/grain_reserves_probe.py run` (the same seed with the switch off and
on, hybrid, current defaults, one process each, branch export `49cd760`),
`summarize`, `compare`. Template: 40 worlds (seeds 42-81), 300 turns.
Procedural 32 x 10: 20 worlds (seeds 42-61), 200 turns. Mean per world;
difference with its paired standard error. Sufficiency classes are the
populated, ruled region-turns' food sufficiency as the agents read it (after
any release): fed (1 or more), dearth (0.6-1), severe (below 0.6 for one or
two turns), famine (below 0.6 for three turns or more). Food price: the
economy's demand over post-trade supply (before a release); volatility: per
region the standard deviation of the log price over its populated turns.

| per world | template off | on | difference (SE) | procedural off | on | difference (SE) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| region-turns fed | 49.7% | 50.0% | +0.3 pts (0.4) | 58.3% | 58.2% | -0.1 (1.0) |
| ... dearth | 21.7% | 22.8% | **+1.1 (0.3)** | 17.0% | 18.6% | **+1.6 (0.4)** |
| ... severe (1-2 turns below 0.6) | 12.2% | 10.6% | **-1.6 (0.3)** | 15.0% | 13.4% | **-1.7 (0.4)** |
| ... famine (3+ turns below 0.6) | 16.4% | 16.7% | +0.2 (0.4) | 9.7% | 9.8% | +0.2 (0.5) |
| mean shortfall (1 - sufficiency) | 0.242 | 0.239 | -0.003 (0.003) | 0.220 | 0.213 | -0.008 (0.007) |
| famine reports | 52.5 | 54.8 | +2.3 (1.5) | 71.4 | 75.5 | +4.2 (5.1) |
| dearth reports | 157.0 | 152.3 | -4.7 (2.8) | 411.4 | 406.6 | -4.9 (11) |
| deaths per 1,000 agent-turns | 16.55 | 16.30 | **-0.25 (0.11)** | 18.01 | 17.29 | **-0.72 (0.23)** |
| ... in short region-turns | 19.81 | 19.54 | -0.27 (0.24) | 21.14 | 20.10 | **-1.04 (0.42)** |
| births per 1,000 agent-turns | 16.12 | 15.99 | -0.13 (0.11) | 18.86 | 18.55 | -0.31 (0.20) |
| population, mean over the run | 186.7 | 188.9 | +2.2 (2.1) | 578.8 | 616.2 | **+37.4 (11)** |
| population at the end | 182.2 | 186.4 | +4.2 (3.6) | 607.5 | 669.2 | **+61.7 (16)** |
| food price, mean | 1.924 | 1.982 | +0.058 (0.029) | 1.867 | 1.871 | +0.004 (0.065) |
| food price volatility | 0.896 | 0.877 | **-0.019 (0.007)** | 0.855 | 0.844 | -0.011 (0.008) |
| treasury, mean per living civ-turn | 577 | 604 | +28 (20) | 320 | 324 | +4 (20) |
| civ-turns with treasury below 20 | 7.0% | 5.4% | -1.5 pts (0.8) | 13.3% | 13.3% | 0.0 (1.4) |
| fiscal crises per civ-century | 0.40 | 0.39 | -0.01 (0.09) | 1.78 | 1.59 | -0.19 (0.21) |
| loans / defaults / debasements per civ-century | 0.79 / 0.085 / 0.10 | 0.84 / 0.098 / 0.11 | +0.06 / +0.013 / +0.013 (0.08 / 0.012 / 0.017) | 2.69 / 0.39 / 0.31 | 2.92 / 0.34 / 0.26 | +0.22 / -0.05 / -0.04 (0.15 / 0.035 / 0.046) |
| merchants' food departures | 599 | 553 | **-45 (17)** | 1,519 | 1,547 | +28 (34) |
| mutual-aid convoys | 3.6 | 2.2 | **-1.3 (0.5)** | 23.4 | 21.1 | -2.3 (3.6) |
| allied relief convoys | 13.5 | 15.6 | +2.2 (2.3) | 226.4 | 203.8 | -22.6 (17) |

The granaries themselves (switch on):

| per world | template, 300 turns | procedural, 200 turns |
| --- | ---: | ---: |
| grain received from the granary's own market / the realm / abroad | 323 / 130 / 175 | 227 / 259 / 395 |
| grain sent; lost in transit | 643; 16 | 916; 34 |
| treasury paid to own producers / foreign rulers | 71 / 28 | 77 / 61 |
| released (of it, into severe shortage below 0.6) | 294 (234) | 399 (331) |
| released, share of all food demand | 1.0% | 0.6% |
| spoiled; taken by conquest, occupation, siege | 290; 1.4 | 348; 12 |
| openings; emptied | 32; 12 | 58; 21 |
| events `granary_opened` / `granary_exhausted` / `grain_bought` | 24.6 / 10.1 / 17.2 | 45.1 / 17.4 / 37.3 |
| grain held, mean (target, mean) | 33 (185): 17% | 60 (498): 12% |
| grain held over the run's first / middle / last third | 15 / 46 / 38 | 38 / 64 / 77 |
| grain held after spring / summer / autumn / winter | 29 / 31 / 38 / 35 | 52 / 56 / 69 / 63 |

What this shows:

* **Hunger.** Granaries take about an eighth of the short severe
  shortages away: the share of region-turns below the famine line for a
  turn or two falls by 1.6-1.7 points (13% and 11%), and four fifths of the
  released grain goes into shortages below that line. Most of what they
  lift lands just above the line (a granary below half its target stops
  there), so dearth rises by the same amount;
  the fed share and the share in sustained famine do not move beyond
  their noise. Famine reports rise a little (+2-4 per run, about one
  standard error and a half): a granary that covers a dearth also spares
  the region the dearth report's five-turn cooldown, so a later famine is
  reported where before it fell inside the cooldown.
* **Deaths and people.** Deaths per agent-turn fall 1.5% on template
  worlds and 4% on procedural ones (5% in the short region-turns); the
  procedural worlds end with 10% more people (6% over the run). Births per
  head do not move beyond noise (more people, the same rate).
* **Prices.** Volatility of the food price falls 2% on template worlds
  (1.3% procedural, within noise); the mean price rises 3% on template
  worlds (the purchases take grain off the market; the releases do not
  pass through it).
* **Money.** Purchases cost about 100 treasury per template world over 300
  turns and 140 per procedural world over 200, against mean treasuries of
  580 and 320. No fiscal measure moves beyond its noise.
* **Migration** (agent events, migrations per world by driver): on
  template worlds famine-memory migrations fall from 1,565 to 1,369 (-196,
  SE 51) and all migrations from 3,539 to 3,414 (-126, SE 66), while
  migrations for material need rise from 132 to 156 (+24, SE 9); on
  procedural worlds, with 6% more people, all migrations rise by 345 (SE
  228) and famine-memory ones by 122 (SE 116), both within noise.
* **Trade.** On template worlds the merchants carry 8% less food (the
  granaries buy the surplus near the storage cap, which they also ship) and
  mutual aid answers a third less often (releases cover the stress it
  waits for); on procedural worlds neither moves beyond noise, and the
  granaries' own shipments (916 grain sent) are 60% of the merchants'
  food departures.
* **The reserves.** Granaries fill to 12-17% of their targets on average:
  real surplus beyond four turns of a market's own need is scarce, and
  what is bought spoils about as fast as it is released (spoiled about
  equal to released). They fill after the harvest and draw down through
  winter and spring.

These are modest effects: the reserves release 0.6-1.0% of the food
demand, against a shortfall of 22-24% of it. A granary cannot cover a
structural deficit (section 1), only move surplus that the markets would
have lost to the storage cap and spoilage toward the turns and places that
starve.

## 8. Gates with the switch on

Linux, 4 cores, Python 3.13.17, `PYTHONHASHSEED=0`; the branch export
`49cd760` with its release build (section 5); fresh output roots. Subset
baselines: `main` `6da8fe5`'s export with its own build, run the same day.
Full baselines: the needs-method-5 full reports of `main` `3c3775d` (PR #55;
`6da8fe5`'s simulation is the same, section 5).

```sh
# subsets, 20 x 200: template seeds 42-61, procedural 32 x 10 (--worldgen procedural),
# template seeds 62-81 (--seed-start 62); main the same without --grain-reserves and a baseline
python scripts/m53b_run_validation.py --profile subset --parallel 1 --grain-reserves \
  --baseline-report <main's subset report> --exploratory-comparison --output-root <fresh root>
# full, one gate at a time on the machine
python scripts/m53b_run_validation.py --profile full --parallel 3 --grain-reserves \
  --require-strict-regression --baseline-report <main's template full report> \
  --exploratory-comparison --output-root <fresh root>
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 \
  --grain-reserves --require-strict-regression \
  --baseline-report <main's procedural full report> --exploratory-comparison --output-root <fresh root>
```

A first procedural full run with `CHRONICLER_CHECK_RESOURCES=1` stopped at
seed 42's turn 128 on the production ledger's mines' soil check (section 4:
`main`'s native ordering, not a granary balance); the gate was rerun into a
fresh root without the check, as `main`'s baselines and the template gate
ran.

The comparator refuses a baseline of another simulation configuration
("simulation configuration: grain_reserves None vs True") unless the
comparison is marked exploratory; it then still reports new required
failures and strict-regression downgrades, and says the reports are not
regression evidence for the same cohort.

### Full gates

| | template `main` | template on | procedural `main` | procedural on |
| --- | --- | --- | --- | --- |
| worlds | 200 x 500 | 200 x 500 | 100 x 300 | 100 x 300 |
| gate | PASS | **PASS** | PASS | **PASS** |
| comparison with `main` | - | **EXPLORATORY, NO REGRESSION** | - | **EXPLORATORY, NO REGRESSION** |
| regression | PASS strict | PASS strict | PASS strict | PASS strict |
| needs: net (lower bound); seeds with the expected sign (needed) | 0.166 (0.144); 154 (120) | 0.174 (0.153); 172 (120) | 0.091 (0.066); 72 (60) | 0.130 (0.105); 79 (60) |
| needs binding: net (lower bound) | 0.191 (0.164) | 0.218 (0.191) | 0.134 (0.098) | 0.207 (0.171) |
| needs material pairing: net (lower bound) | 0.189 (0.161) | 0.202 (0.177) | 0.117 (0.084) | 0.201 (0.157) |
| cohort / community / era | PASS | PASS | PASS | PASS |
| arcs (seeds with three arc types) | PASS (152) | PASS (159) | PASS (97) | PASS (98) |
| artifacts (per civ per 100 turns; lost or destroyed) | PASS (1.85; 5.5%) | PASS (1.91; 4.9%) | PASS (2.50; 3.6%) | PASS (2.53; 3.6%) |
| satisfaction, mean / last 60 turns | 0.6213 / 0.6341 | 0.6220 / 0.6355 | 0.5671 / 0.5751 | 0.5706 / 0.5769 |
| migration per agent-turn | 0.0635 | 0.0598 | 0.0755 | 0.0728 |
| rebellion per agent-turn | 0.0329 | 0.0350 | 0.0387 | 0.0343 |
| Gini in range | 0.853 | 0.865 | 0.901 | 0.918 |
| worlds where every founder survives (at most 0.20) | 0.165 | 0.145 | 0.08 | 0.04 |
| extinct worlds; treasury failures | 0; 0 | 0; 0 | 0; 0 | 0; 0 |
| batch time | - | 18 min | - | 18 min |

Both full gates pass strict with the switch on, and the comparator finds
no required oracle newly failing and no strict check downgraded. The needs
oracle's net, lower bound, binding pairs and seed count are higher than
`main`'s on both world types (procedural 72 -> 79 seeds with the expected
sign; the material pairing 0.117 -> 0.201). Migration per agent-turn is 6%
lower on template worlds (fewer famine-memory migrations, section 7) and
3.5% on procedural ones; rebellion is lower on procedural worlds (0.0387 ->
0.0343) and higher on template ones (0.0329 -> 0.0350); all within the
regression bands. The procedural run's 100 worlds also balance their
granary ledgers offline (section 4).

### Subsets

| 20 x 200 | template 42-61 `main` | on | template 62-81 `main` | on | procedural `main` | on |
| --- | --- | --- | --- | --- | --- | --- |
| gate | PASS | **FAIL** (needs) | FAIL (needs) | FAIL (needs) | FAIL (needs) | **PASS** |
| needs: net (lower bound); seeds (needed) | 0.196 (0.082); 14 (12) | 0.047 (-0.061); 10 (12) | 0.115 (-0.018); 16 (12) | 0.101 (-0.011); 12 (12) | 0.046 (-0.021); 11 (12) | 0.073 (0.003); 12 (12) |
| needs material pairing: concordant / discordant (net) | 127 / 64 (0.33) | 87 / 80 (0.04) | 117 / 87 (0.15) | 100 / 94 (0.03) | 145 / 116 (0.11) | 177 / 143 (0.11) |
| needs binding: net (lower bound), informational | 0.240 (0.080) | 0.166 (0.013) | -0.021 (-0.185) | 0.090 (-0.058) | 0.060 (-0.069) | 0.116 (0.013) |
| regression (informational in a subset) | PASS strict | PASS strict | FAIL: founders | FAIL: founders, rebellion | PASS strict | FAIL: founders |
| worlds where every founder survives (at most 0.20) | 0.10 | 0.15 | 0.45 | 0.45 | 0.20 | 0.25 |
| migration per agent-turn | 0.0664 | 0.0651 | 0.0612 | 0.0585 | 0.0766 | 0.0747 |
| rebellion per agent-turn (at least 0.02) | 0.0462 | 0.0452 | 0.0205 | **0.0179** | 0.0370 | 0.0314 |
| arcs; artifacts (informational) | FAIL; PARTIAL | FAIL; PARTIAL | FAIL; PARTIAL | PASS; PARTIAL | FAIL; PARTIAL | FAIL; PARTIAL |
| comparison with `main` | - | EXPLORATORY, REGRESSION (needs newly fails) | - | - | - | EXPLORATORY, NO REGRESSION |

The needs oracle is the only required failure. On template seeds 42-61 it
passes on `main` and fails with the switch on, almost entirely through
its material pairing (net 0.33 -> 0.04: concordant pairs 127 -> 87,
discordant 64 -> 80). Granaries change who migrates: in the paired template worlds
(section 7) migrations driven by famine memory fall by 196 per world (SE
51), all migrations by 126 (66), migrations for material need rise by 24
(9). The lost concordant pairs are consistent with fewer departures after
hunger, which the pairing counts when the agent with the lower material
need is the one who leaves (not traced pair by pair). On seeds 62-81
`main` fails as well (16 seeds with the expected sign but a lower bound
below zero), and so does the switch on (lower bound -0.011, 12 seeds); on
procedural worlds `main` fails and the switch on passes. Over the full 200
template worlds the material pairing's net is higher with the switch on
(0.189 -> 0.202), as are the oracle's net, its binding pairs' net and its
seed count (154 -> 172); twenty seeds do not resolve the change. Of the
subsets' informational regression failures, the rebellion rate of template
seeds 62-81 with the switch on (0.0179, below the 0.02 floor; `main`
0.0205) is the granaries' (the full template gate's is 0.0350, `main`
0.0329); the others are the founders' survival check (five of 20
procedural worlds keep every founder with the switch on, four on `main`;
nine of 20 template worlds 62-81 on both).

## 9. Narration

* **Events** (section 2): `granary_opened` and `granary_exhausted` have
  readable lines (`curator.event_label` is their description) and weigh by
  importance (4-5); `grain_bought` is routine for the narrator
  (`narration_context.ROUTINE_TYPES`) and for the in-world historians
  (`historiography.ROUTINE`). An opening and an exhaustion cite the open
  famine or dearth report of the region when there is one, so the causal
  context reaches the shortage behind them. The rows are in the coverage
  table of [narration-coverage.md](narration-coverage.md#5-coverage-table):
  in a 500-turn template run (seed 42) 54 openings (25 listed in a curated
  prompt), 22 exhaustions (8) and 3 foreign purchases (0, routine).
* **Provenance** (PR #56): the events are emitted through the turn's
  observer, so they carry event ids and recorded causes and are fact ids
  (`e<i>`) in the prompts and the entries' provenance. `python -m
  chronicler.narration_audit` on mechanical narrated runs with the switch
  on: template seed 42, 200 turns (34 entries, 838 facts, 722 sentences;
  14 openings and 5 exhaustions among the facts) and 500 turns (50 entries,
  1,278 facts, 1,079 sentences), procedural 32 x 10 seed 11, 150 turns (25
  entries, 1,225 facts, 567 sentences): **no flags**, no uncited sentence.
  The names an event line uses are its actors and region.
* No standing-state line: the granaries' stock is not in the per-turn
  snapshots (section 3), and the food line already names a region's
  recorded dearth or famine.

## 10. Tests

* `tests/test_grain_reserves.py` (21 tests, two native; in the oracle
  lane's new `grain-reserves` chunk):
  * the switch: default off, dormancy (no state, and a strict no-op under
    `--agents off`), old saves, save/load; append-only orders; the CLI flag,
    the gate runner's forwarding, the live default, the batch manifest key,
    the benchmark pin; an explicit switch with `--agents off` refused; new
    worlds follow the default and a resumed world keeps its saved setting;
    the switch off never runs granary code (every entry point replaced by
    a failure, 15 turns with campaigns);
  * targets: a steady harvest and one above the need keep none, a swinging
    harvest the CV rule, a failing one the cap, nothing grown none;
  * release: the shortfall covered before anything reads it (sufficiency,
    post-trade supply, spoilage), a fed region untouched, a low granary
    only to the famine line, an opening and its exhaustion told once, a
    small release without an event;
  * procurement: the own market first at its price in whole coins and paid
    to its producers, four turns of need kept; realm shipments with transit
    decay and a suspended route blocking them; foreign purchases paid to
    the seller, war and embargo blocking them, the `grain_bought` event;
    merchant commitments not for sale; the budget share and floor;
  * conquest, occupation and siege shares; the new ruler's capture; an
    abandoned granary to its market;
  * the resource ledger: a season of purchases and releases balances; grain
    added outside the flows and a transfer that never debits the buyer
    raise;
  * metrics, event lines and narrator/historian classes;
  * native: a 60-turn hybrid run with `CHRONICLER_CHECK_RESOURCES=1` and the
    sidecar (purchases, releases, the ledger file equal to the counters, the
    events, no snapshot field); the switch off is the run without it.
* Changed: `tests/test_serialization_dormant_fields.py` (`grain_reserves`
  omitted while off).
* `scripts/benchmark_headless.py` pins `grain_reserves=False` for the frozen
  oracles, as it pins every other switch.

Runs (Linux, Python 3.13.17, the branch virtualenv with its fresh release
build): `python -m pytest -q -n 2 -m "not slow"` **6,655 passed, 3 skipped**
(526 subtests); `python -m pytest -q -m slow` **12 passed, 3 skipped**;
`python scripts/run_python_oracle_checks.py` **PASS in 95.5 s** (13 chunks;
`grain-reserves` 19 passed, 2 native skipped, 0.9 s); `cargo test --locked
--manifest-path chronicler-agents/Cargo.toml` (`CARGO_PROFILE_TEST_DEBUG=0`;
the Rust is `main`'s) **1,051 passed, 2 ignored** in 36 test binaries.

## 11. Open

* **Scarce real surplus.** Granaries fill to 12-17% of their targets and
  release 0.6-1.0% of the food demand; the worlds' shortfall is structural
  (section 1). Selling beyond two turns of a market's need instead of four
  fills them more but takes the merchants' surplus and sustained famine
  rises (section 2, variants).
* **Spoilage.** About as much grain spoils in the granaries as they
  release: they keep the market's 3% a turn. Purpose-built storage (a
  granary building, a technique) would lose less; not modelled.
* **Template subsets** (section 8): seeds 42-61 fail the needs oracle
  through its material pairing (`main` passes), and seeds 62-81's
  rebellion rate falls below the regression floor (0.0179; informational in
  a subset). The full template gate passes both, with a stronger needs
  result than `main`'s.
* **Merchants are not contracted.** The state buys at markets; cargo in
  transit is not for sale, and the merchants' committed cargo is left to
  them. State shipments are not merchant trips: the contact ledger,
  epidemics, piracy and city commerce do not see them.
* **Home purchases leave the treasury** to the realm's producers outside
  the treasury accounts (no agent wealth or regional specie is credited),
  as upkeep does. Prices are not deflated by the finance price index.
* **Relief is handed out, not sold.** The economy's prices and farmer
  incomes of the release turn stay; the higher sufficiency the merchants
  then read draws imports elsewhere (template food departures -8%). A sale
  at a below-market price (the ever-normal granary's rule) would need the
  release inside the native economy.
* **In place only.** A granary releases in its own region; it does not ship
  to a starving neighbour (mutual aid does that from market stocks).
* **Grain only**; fish and other foods are not stored. No viewer panel and
  no per-turn snapshot field (the final state and the sidecar ledger carry
  the granaries). Dormant under `--agents off`.
* **Famine report counts** rise slightly through the dearth report's
  cooldown (section 7); the region-turn shares are the measure.
* **The mines' soil charge** (`main`'s, PR #52) reads the crew after the
  overpopulation degradation, its ledger before; with the switch on the
  resource checks stop on it in some procedural worlds (section 4). A
  correction of its own, outside this branch.
