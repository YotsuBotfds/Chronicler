# Realized production and extraction ledger (2026-10)

Branch `feat/production-ledger` from `main` `8142c48` (PR #51). An external
review recommended connecting actual output, stocks, depletion, recovery and
degradation before adding production modifiers: several paths consumed,
depleted or degraded a resource from a proxy (population-derived workers, a
flat rate per building), not from what was produced. This branch audits every
production path (section 1), records a per-slot ledger of what each turn took
(section 2), makes four paths follow realized output (sections 3-6), checks
the balances (section 7) and reports before/after (sections 8-9).

The four changes are **behavioural corrections**, on by default, each with a
tuning key that restores the earlier rule (section 10). All four keys at 0 are
byte-identical to `main` (section 10). Where no economy ticks (`--agents off`,
the off-mode `EcologySimulator`, an agent-mode turn before any economy tick)
every rule keeps its proxy bit for bit, so the off-mode golden fixtures do not
change and no `ORACLE_CHAIN` link is added.

Code: Rust `ecology.rs` (`ExtractionLedger`, `overextraction_take`,
`mine_crew_ratio`, `yield_penalty_factor`, `tick_ecology_with_ledger`),
`economy.rs` (`forage_output`), `ffi/mod.rs`, `ffi/ecology_sim.rs`
(`set_extraction_config`), `ffi/batch.rs`, `ffi/schema.rs`; Python
`production_ledger.py` (new), `ecology.py`, `economy.py`,
`experimental/fisheries.py`, `scenario.py`, `emergence.py`, `sidecar.py`,
`simulation.py`, `agent_bridge.py`, `tuning.py`;
`scripts/production_ledger_report.py` (new). Tests:
`tests/test_production_ledger.py`, `tests/test_production_ledger_native.py`,
`chronicler-agents/tests/test_production_ledger.rs`.

Every run is Linux, Python 3.13.17, `PYTHONHASHSEED=0`, hybrid unless stated,
each arm with its own virtualenv and a release extension built fresh
(`maturin develop --release --locked`, its own `CARGO_TARGET_DIR`; compiled
`chronicler_agents.chronicler_agents` with `AgentSimulator`,
`EcologySimulator`, `PoliticsSimulator` real classes). `main` `8142c48` from
an exported tree: extension SHA-256 `83b76b41...5b87`, the same as the
`c0f354d` build its full-gate reports came from (`c0f354d` and `8142c48` have
the same `src/`, `chronicler-agents/` and `scripts/`). Branch code commit
`b51ec01` (every gate and test below): `c8ef41f5...b6ff`. The commits after
it change this documentation, the progress ledger and the report script's
matched-seed options (`--saved`, `--seeds`) only.

## 1. Audit: what decides output, what takes from the land, what gives back

| Path | Output decided by | Depletes or degrades | Recovers | Charge basis on `main` | This branch |
| --- | --- | --- | --- | --- | --- |
| Farming (grain, botanicals, exotic) | Phase 2 preview `compute_resource_yields`: base x season x regional crop climate x soil x water x abundance x technique (x pastoral crop share), over the harvest normal; x food-first farm labour on the farm curve (`tick_economy_core`). Off mode: the harvest index feeds the aggregate famine check | Soil -0.005 a turn while population > potential capacity, doubled after 30 turns above 0.7 x carrying capacity on a crop slot; the mines' soil charge (mines row); a technology accident -0.3. Water: climate phases, harvest shocks, upstream deforestation. Overextraction streak (grain, botanicals): -10% effective yield after 35 turns | Soil +0.05 x pressure while population < 0.75 x potential (+0.02 agriculture focus), +0.01 under forest > 0.5, the soil-floor tradition, flood silt; water: temperate +0.03, irrigation; `ecological_recovery` restores effective yields | soil: population pressure (by design, M35b decision 7); streak: population / 5; the penalty never reached the yields | soil unchanged (population pressure, documented); streak on realized output (section 3); penalty in the yields (section 4) |
| Fisheries (fish) | Goods yield (marine season x climate x abundance x the lagged catch ratio) x food labour, capped by last turn's catch allowance | Fish stock (default on, reference 100 workers): each Phase 9 reserves next turn's allowance, `min(potential x effort / 100, 25% x (stock + regrowth) x capacity)`, and debits it at once; effort = a food-first split of the snapshot's farmers (agent modes) or population / 5 (off). Overextraction streak (fish) | +4% x (1 - stock) a turn | the whole allowance, whether the economy landed it or not; streak population / 5 | the landed catch (section 5); streak on realized output |
| Forests (timber) | Goods yield (timber season x forestry climate x forest cover) x labour on the woodland curve (potential capacity x cover / 0.9) | Forest cover -0.02 while population > 0.5 x carrying capacity (land clearing), cooling damage; terrain succession after 50 turns under 0.2. Timber output takes no cover | +0.01 x pressure while population < 0.5 x capacity and water >= 0.3 | population (clearing); timber harvest takes nothing | unchanged (documented, section 12) |
| Mines (ore, precious) | Base x season x reserve ramp (reserve / 0.25; 4% trickle under 0.01) x abundance x technique, x labour on the deposit curve (potential x max(reserve, 0.1)) | Reserve -(extraction x 0.009): extraction = output / target crew (a third of effective capacity) where the economy reported output (PR #51), base x (population / 5) / target crew otherwise. Soil: every active mine -0.03 a turn (x0.5 metallurgy, x2 mechanization). `mine_collapse` (mountains, reserve < 0.3, 10% a turn) suspends the slot 3-5 turns. Overextraction streak (ore, precious) | none (non-renewable) | reserve: realized (PR #51); soil: flat per mine, worked or not; streak population / 5 | soil on the ore taken (section 6); streak on realized output |
| Salt | Goods yield (evaporite season x climate) x food labour | nothing | - | - | unchanged |
| Pastoral (nomads, default on) | Herd food (herd / scale x share x season) added to the first food slot's harvest index, then that slot's labour; pastoral civs' crop share cut | Herds: logistic growth on pasture (terrain x grass from water), die-off above the seasonal capacity, dzud. Herd food draws nothing from the herd; grazing degrades no soil or water | herd growth | none (a flow from the stock) | unchanged (documented, section 12) |
| Foraging | Farmers without a yielding food slot forage `SUBSISTENCE_BASELINE x crop climate` grain each | nothing | - | - | reported (`forage_output`) |
| Crafts (wares) | City crafts work raw materials on hand (timber, ore, stock and this turn's output less departures) one for one into wares, up to their raw demand | The raw materials used (exact, `craft_input`); 1% wear a turn in store | - | realized | unchanged |
| `--agents off` | No goods economy | Minerals population / 5; fishery effort population / 5 (never binds); streak population / 5; flat mine soil | as above | proxies | proxies kept bit for bit; the yield penalty applies (never triggers: needs population / 5 > 200 x yield) |

Two paths already followed realized output on `main`: mineral depletion in
agent modes (PR #51) and crafts. The Python ecology lane
(`_tick_ecology_python`) runs only without a native runtime, where no
economy ticks; it keeps every proxy, as before.

## 2. The ledger

`chronicler.production_ledger`: one row per region (index in
`world.regions`) and occupied resource slot per turn, from just before the
Phase 9 ecology tick (after the Phase 2 economy) to just after it. It reads
only: no state, RNG or output changes (tested: a 30-turn hybrid run with and
without it gives the same bundle). It is built only when the validation
sidecar is written or `CHRONICLER_CHECK_RESOURCES=1` is set; otherwise one
`None` check per turn. The sidecar writes it on close as
`validation_resource_ledger.arrow` (Arrow IPC, zstd) beside the other
validation files; the bundle is untouched. It is not a validator input, so
the batch manifest does not hash it.

| Column | Meaning |
| --- | --- |
| `turn`, `region`, `slot`, `resource_type` | identity (region index, slot 0-2, `ResourceType`) |
| `realized`, `output` | the economy reported this turn's output; the goods the slot produced (`EconomyRegionResult::slot_output`, after the catch cap) |
| `stock_kind` | 1 mineral reserve, 2 fish stock, 0 none |
| `stock_before`, `depletion`, `recovery`, `stock_after` | `stock_after = stock_before - depletion + recovery`. Reserve: depletion is the draw, recovery 0. Fish: stock is the fish in the water plus the allowance reserved for the next catch (`reserved_*`); depletion is the catch landed plus any allowance charged but not landed (`lost`); recovery is the regrowth |
| `proxy_depletion` | what the earlier rule charges the same stock this turn: population / 5 against the target crew (reserve, from the native tick), the whole allowance (fish) |
| `lost` | fish charged but never landed (0 under the landed-catch rule) |
| `effective_before`, `effective_after` | the overextraction track; a fall is a penalty |
| `take`, `proxy_take`, `sustainable`, `streak` | what the streak compared (`take`) with `effective x workers_per_yield_unit`; population / 5; the streak after |
| `soil_*`, `forest_*` | the region's land before and after Phase 9 (region-level, repeated per slot) |
| `mine_soil`, `proxy_mine_soil` | soil the region's mines took this tick, and what the flat rule takes (on the region's first mineral slot) |

Native inputs: the economy region result gains `slot_output_{0,1,2}` and
`forage_output`; the ecology region batch gains `extraction_realized`,
`mineral_drawn_{i}`, `proxy_mineral_draw_{i}`, `extraction_target_crew`,
`overextraction_take_{i}`, `mine_soil`, `proxy_mine_soil`,
`mine_crew_ratio` (33 columns; computed by `tick_ecology_with_ledger`
alongside the tick and written only to that tick's batch). Older
extensions without them: the Python economy result has no slot output, the
ledger reads state alone, and the landed-catch charge refuses to run
(`require_fishery_runtime`).

Size: 2,600 rows and 34 KB for a 200-turn template world (seed 42); the
template subset batch's 20 ledgers are 0.72 MB of 173 MB (0.4%).

## 3. Overextraction streak on realized output

`ecology::overextraction_take`, Python `ecology.overextraction_take`. The
streak read `population / 5` workers for every depletable slot (grain,
botanicals, fish, ore, precious), whatever the economy did: a suspended
slot, an exhausted mine, a fishery held to its catch counted in full. Where
the economy reported output the take is the output in worker equivalents at
the slot's undegraded productivity, `output / base yield` (goods per worker
average the base yield on healthy land, so a crew of N at the normal yield
takes N). It follows the season (a field takes a third in winter) and a
degraded slot's take falls with its yield. Without an economy tick the
proxy is kept bit for bit.

Effect: none in default worlds. The sustainable workers are `effective
yield x 200` (about 200 a slot) and no slot comes near: realized pressure
(take / sustainable) peaks at 0.58 in the template full gate and 0.56 in the
procedural one (per-world peaks: medians 0.41 and 0.36). Realized takes run
above the proxy (template subset: 1.98 times population / 5 pooled, median
1.40 over 21,609 slot-turns), but a template region's slot holds tens of
workers. No `resource_depletion` event in any arm; the calibration is not
changed here (section 12).

## 4. The overextraction penalty reaches the yields

`yield_penalty_factor` (Rust and Python): a slot's yield is multiplied by
`effective / base` when the effective yield is below the base yield by more
than `YIELD_PENALTY_TOLERANCE` (1e-6; the native ecology holds effective
yields in single precision, so an undegraded slot's written-back copy sits
up to 6e-8 below a double-precision base yield, and a penalty takes 10%).
Undegraded slots keep their bits. Both the Phase 2 preview (the economy's
goods yields) and the Phase 9 yields carry it, and the exhausted trickle.
This is the change PR #11 rejected (ecology-goods-reconciliation.md,
"Considered and rejected") because scenario slots had base yields and no
effective yields; the prerequisite is fixed:

- `scenario.apply_scenario` gives every slot with a base yield and no
  effective yield its base yield (a river's fish slot, `specialized_resources`,
  whose replaced resource's effective yield was kept); generate_world already
  did.
- An effective yield of 0 with a base yield (scenario saves from before) is
  read as undegraded (factor 1), and `_check_ecological_recovery` no longer
  treats it as degraded. On `main` such a slot drew a recovery roll every
  turn and fired spurious `ecological_recovery` events (narration only).
  Scenario worlds with rivers or specialized resources draw fewer rolls
  from the shared environment stream, so they diverge; no gate or golden
  world has such a slot.

Effect: none in default worlds (no penalty fires, section 3); verified bit
identical against the old rule (section 10).

## 5. The fishery stock is charged for the landed catch

`fisheries.charges_landed_catch`, `unlanded_stock`. Each Phase 9 reserves
next turn's allowance and debits it at once; next turn the economy lands at
most that allowance (its production cap) and often less: its fishers work
on the farm curve, in the next season and in food-first splits the
allowance's labour proxy does not follow. Fish left the water that never
became goods. Now, before this turn's regrowth, the part of last turn's
allowance the economy did not land (its fish-slot `slot_output` converted
back by the harvest normal) returns to the stock; net, the stock loses what
was landed. Where all of it is landed the stock is exactly the old one.
Without an economy tick the allowance stays charged in full. The allowance
itself is still sized by the labour proxy (a cap, not a charge; section 12).

Effect (the ledger on the same worlds): 11.7% of the allowance was never
landed in the template full gate (203 of 1,733 stock units; per world median
11.6%), 10.6% in the procedural one (269 of 2,527); template probes 12% (3.32
of 27.28 over 10 worlds x 200 turns). Final fish stocks rise 0.02-0.04. On
its own (the mine-soil key at 0) it changes no history row of 10 template
probe worlds and nothing the validator reads in 40 procedural subset worlds
(200 turns): the harvestable bound did not bind in them, so only the stock
moved, and the 6 `fishery_collapse` events of `main`'s
procedural subsets (2 in seeds 42-61, 4 in 62-81; 4 recoveries) do not
happen: those stocks fell below 0.25 on fish never landed. In 500-turn
worlds `main` collapses 4 of 56 template fish slots (section 9), the branch
none.

## 6. The mines' soil charge on the ore taken

`ecology::mine_crew_ratio`, `tick_soil_controlled_ledger`. An active mine took
`mine_soil_degradation` (0.03, x0.5 metallurgy, x2 mechanization) every turn
whether or not any ore was mined. Where the economy reported output the
charge is multiplied by the region's mineral output over what the deposit's
target crew produces at the base yield, `sum over mineral slots of output /
(base yield x target crew)`, the crew from the effective capacity before this
turn's soil change. A target crew at the base yield takes the old rate (the
same anchor as PR #51's depletion); an idle mine takes nothing. Without an
economy tick the flat rule is kept bit for bit.

Effect: the flat rule overcharged. The mines' realized charge is 9.1% of the
flat rule in the template full gate (397.5 of 4,378.8 soil; per world median
8%), 10.2% in the procedural one (375.9 of 3,680.9), 19% in 10 template
probes (19.2 of 101.6) and 11-14% in the procedural subsets: most mines are
worked by a fraction of a target crew (food comes first in the labour split;
a mineral slot keeps 25% of its equal share), and some by no one (template
seed 42's region 0 mine stood idle for its 29 active turns, at 0.03 a turn on
`main`). This is the one correction that moves trajectories: every template
probe world diverges within its first 3-18 turns. Mining regions keep more
soil; worlds grow 2.2-2.3% larger by the end of the full gates.

**Correction (2026-10-27, `fix/mine-soil-ordering`; section 13).** Until
then the native charge did not quite follow this rule: the ledger recorded
the crew ratio before the soil step, but the charge recomputed it after the
step's overpopulation loss. Where that loss took the effective capacity
across a multiple of three (crowded regions only) the crew was one smaller
and the mines took N/(N-1) of the soil their ore warranted, and
`CHRONICLER_CHECK_RESOURCES=1` raised. The charge now reads the ratio from
before the step, as stated above.

## 7. Checks

`CHRONICLER_CHECK_RESOURCES=1` (all modes; the population check,
`CHRONICLER_CHECK_POPULATION`, covers `--agents off` only) builds the ledger
every turn and raises `AssertionError("resource ledger does not balance ...")`
when:

- a mineral reserve fell by other than the tick's reported draw, grew, or
  went negative; where the economy reported output, the draw is not
  `min(reserve, output / target crew x depletion rate)` (no output, no draw);
- a fish stock plus its outstanding allowance did not change by exactly the
  regrowth less the fish that left the water (to 1e-9);
- the slots' output, the foraged grain and the wares made do not add up to
  the economy's production (what entered the stocks; to 1e-5 relative);
- the overextraction take is not the realized output (or the proxy without
  one), the streak did not follow it, or the mines' soil charge is not the
  rule's (until 2026-10-27 this raised in crowded mining regions whose
  overpopulation loss crossed a crew boundary: section 13);
- the native tick and the economy disagree on whether output was reported.

Negative controls (tests): a reserve that grows and a fish stock that loses
fish outside the accounts both raise. Covered runs: 40 off-mode turns of
seeds 42 and 7 (Python lane), 40 hybrid turns of seeds 42 and 7, 30 of a
16-region procedural world, and 40 with every old rule restored.

## 8. Analytics: `scripts/production_ledger_report.py`

```sh
python scripts/production_ledger_report.py --batch main=<batch dir> --batch branch=<batch dir> \
    --json report.json --markdown report.md
```

Per world and batch: mineral slots exhausted (reserve < 0.01 at the end),
mean final reserve, mine collapses, fish slots and final stock, fishery
collapses and recoveries with their times (from events; from the ledger's
stock series where present), overextraction and soil-exhaustion events,
final population; from the ledger, realized against proxy depletion, fish
landed against charged, regrowth, the mines' soil against the flat rule,
peak overextraction pressure and penalties. A batch without the ledger
(`main`) is summarized from its bundles. `summarize_ledger` is the per-world
function.

## 9. Before and after

### Gates

`scripts/m53b_run_validation.py`, fresh empty output roots, every batch
manifest verified (exactly the requested seeds and turns), needs oracle
method 4, cohort method 2. Subsets: one worker each (`PYTHON_CPU_COUNT=2`),
`main` from its exported tree with its own venv, the branch from this
worktree; the branch compared with `main`'s own subset report:

```sh
python scripts/m53b_run_validation.py --profile subset --parallel 1 --output-root <root>
python scripts/m53b_run_validation.py --profile subset --worldgen procedural --parallel 1 --output-root <root>
# branch: the same plus --baseline-report <main's validate_report_subset.json>
# second procedural range: --seed-start 62 (main and branch)
```

`main`'s subsets reproduce the `fix/population-entities` head's subset
reports in every oracle but cohort (that head's subsets ran cohort method 1),
so `main` is that simulation.

| Subset (20 x 200) | template `main` | template branch | procedural `main` | procedural branch | procedural 62-81 `main` | branch |
| --- | --- | --- | --- | --- | --- | --- |
| gate | PASS | PASS | PASS | **needs FAIL** | PASS | PASS |
| comparator | | NO REGRESSION | | REGRESSION (needs newly failing) | | (not compared) |
| needs pooled (lower bound), seeds of 20 (12 needed) | +0.135 (+0.045), 13 | +0.190 (+0.092), 14 | +0.126 (+0.059), 12 | +0.093 (+0.033), **11** | +0.162 (+0.098), 18 | +0.104 (+0.040), 15 |
| needs binding (lower bound; informational) | +0.153 (+0.009) | +0.230 (+0.100) | +0.163 (+0.059) | +0.080 (-0.032) | +0.176 (+0.060) | +0.178 (+0.062) |
| cohort median effect | 1.202 | 1.249 | 0.749 | 0.915 | 0.902 | 0.763 |
| artifacts; arcs (informational in subsets) | PARTIAL; PASS | PARTIAL; FAIL | PASS; FAIL | PARTIAL; FAIL | PASS; FAIL | PARTIAL; FAIL |
| migration per agent-turn; latest satisfaction | 0.0668; 0.631 | 0.0664; 0.626 | 0.0768; 0.577 | 0.0766; 0.577 | 0.0762; 0.546 | 0.0768; 0.552 |

**The procedural subset's needs failure.** The pooled lower bound stays
positive (+0.033); the seed fraction misses by one seed (11 of the 12
needed; `main` had exactly 12). Root cause: the mine-soil correction
(section 6) is the only one that moves trajectories. The branch with
`ecology.mine_soil_realized: 0` (three corrections on) reproduces `main`'s
procedural subset reports exactly in both ranges (every field of both
validate reports; needs 12 / +0.1261 and 18 / +0.1620), so the
change is that correction's divergence of the worlds, not the ledger, the
fishery or the overextraction changes. It lowers procedural pooled
concordance in both ranges (-0.033, -0.058; each about one standard error of
the difference, 0.052), mostly in the material and social pairings
(material +0.168 -> +0.132 and +0.216 -> +0.140; social +0.089 -> +0.056 and
+0.116 -> +0.057), and raises it in the template subset (+0.135 -> +0.190;
material +0.274 -> +0.319). No threshold was changed; the full gates decide
(below).

Full gates on the branch head `b51ec01`, three workers, against `main`'s full
reports (`c0f354d`, the same `src/`, `chronicler-agents/` and `scripts/` as
`8142c48`, the same extension SHA-256; the comparator accepts them as the
same cohort and configuration):

```sh
python scripts/m53b_run_validation.py --profile full --parallel 3 --require-strict-regression \
    --baseline-report <main c0f354d-template-validate_report_full.json> --output-root <root>
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 --require-strict-regression \
    --baseline-report <main c0f354d-procedural-validate_report_full.json> --output-root <root>
```

| Template full (200 x 500) | `main` | branch `b51ec01` |
| --- | --- | --- |
| gate (all seven required oracles) | PASS, strict | **PASS, strict** |
| comparator | | **NO REGRESSION**, same cohort (200 runs of seeds 42-241, 500 turns) |
| needs pooled (lower bound), seeds of 200 | +0.202 (+0.183), 174 | +0.196 (+0.177), 170 |
| needs binding (lower bound), pairs | +0.182 (+0.158), 4,947 | +0.175 (+0.152), 4,878 |
| cohort median effect | 1.543 | 1.536 |
| community; era collapse episodes | 200; 4,728 | 200; 4,662 |
| artifacts per civ per 100 turns; loss rate | 1.88; 0.053 | 1.85; 0.055 |
| arcs: seeds with three types | 159 | 152 |
| migration / rebellion per agent-turn | 0.0629 / 0.0340 | 0.0635 / 0.0329 |
| satisfaction mean (latest) | 0.6210 (0.6347) | 0.6213 (0.6341) |
| Gini in range; extinct worlds; full civ survival | 0.847; 0; 0.135 | 0.853; 0; 0.165 |
| final population (all worlds) | 36,202 | 37,016 |
| mineral slots exhausted (of 460); mean reserve per world | 42; 0.581 | 36; 0.587 |
| mine collapses | 1,485 | 1,459 |
| wall time (3 workers) | | 1,540 s |

| Procedural full (100 x 300, 32 regions, 10 civs) | `main` | branch `b51ec01` |
| --- | --- | --- |
| gate (all seven required oracles) | PASS, strict | **PASS, strict** |
| comparator | | **NO REGRESSION**, same cohort (100 runs of seeds 42-141, 300 turns) |
| needs pooled (lower bound), seeds of 100 | +0.132 (+0.111), 84 | +0.111 (+0.088), 84 |
| needs binding (lower bound), pairs | +0.136 (+0.099), 2,291 | +0.117 (+0.084), 2,317 |
| cohort median effect | 0.984 | 0.943 |
| community; era collapse episodes | 100; 4,500 | 100; 4,436 |
| artifacts per civ per 100 turns; loss rate | 2.36; 0.040 | 2.50; 0.036 |
| arcs: seeds with three types | 100 | 97 |
| migration / rebellion per agent-turn | 0.0757 / 0.0401 | 0.0755 / 0.0387 |
| satisfaction mean (latest) | 0.5641 (0.5702) | 0.5671 (0.5751) |
| Gini in range; extinct worlds; full civ survival | 0.910; 0; 0.10 | 0.901; 0; 0.08 |
| final population (all worlds) | 52,792 | 54,006 |
| mineral slots exhausted (of 889); mean reserve per world | 4; 0.802 | 4; 0.801 |
| mine collapses | 151 | 169 |
| wall time (3 workers) | | 1,321 s |

The procedural needs signal is lower on the branch again (pooled -0.021,
binding -0.019; standard errors 0.013 and 0.020-0.022 each, so about 1.1 and
0.6 standard errors of the difference), the same direction as both
procedural subsets; the template full gate moved -0.006. The seed fraction
is unchanged (84 of 100). The subset ablations put the whole change on the
mine-soil correction; its mechanism (more soil kept in mining regions, a
slightly larger population: +2.2% template, +2.3% procedural) was not traced
to particular need pairings beyond the subsets' material and social pairs. In both full-gate tables `main`'s final population, mineral
and mine-collapse rows are the `fix/population-entities` measurements of the
batches behind these reports (`metrics-c0f354d-full-*.json`; those batches
are deleted); the branch's come from `scripts/production_ledger_report.py`
on its own batches.

### Production analytics

`scripts/production_ledger_report.py` over the branch's full-gate batches
(the ledger beside every run: realized and the earlier rule's charge in the
same worlds) and, for before/after, `main` batches of the full gates' own
configuration and first seeds (template 42-81 x 500 turns, procedural 42-61 x
300 turns, `--validation-sidecar`, one worker each) against the same seeds of
the branch's gates (`--seeds 42-81`, `--saved`):

| Matched worlds | template `main` | template branch | procedural `main` | procedural branch |
| --- | --- | --- | --- | --- |
| worlds | 40 x 500 | 40 x 500 | 20 x 300 | 20 x 300 |
| mineral slots exhausted at the end (of) | 10 (96) | 8 (96) | 1 (171) | 0 (171) |
| mean final reserve per world | 0.607 | 0.592 | 0.828 | 0.819 |
| mine collapses | 329 | 440 | 15 | 24 |
| fish slots; mean final stock | 56; 0.650 | 56; 0.688 | 160; 0.693 | 160; 0.715 |
| fishery collapses (stock < 0.25) / recoveries (>= 0.6) | 4 / 0 (4 unrecovered at the end) | 0 / 0 | 3 / 1 (98 turns) | 0 / 0 |
| overextraction (`resource_depletion`) events | 0 | 0 | 0 | 0 |
| soil exhaustion events | 173 | 166 | 55 | 52 |
| final population | 7,202 | 7,329 | 11,598 | 11,990 |

| Branch full gates, from the ledger | template (200 x 500) | procedural (100 x 300) |
| --- | --- | --- |
| mineral reserve drawn (realized) / by the population proxy | 195.3 / 452.1 | 178.1 / 283.2 |
| per world, realized / proxy: median (quartiles; range) | 0.52 (0.44-0.67; 0-1.68) | 0.68 (0.57-0.82; 0.33-10.4) |
| ore and precious output (goods) | 117,863 | 178,680 |
| fish landed / allowance charged by the full-charge rule (stock units) | 1,529.6 / 1,732.8 | 2,258.1 / 2,527.1 |
| per world, unlanded share of the allowance: median (quartiles; max) | 11.6% (10.3-13.1%; 16.8%) | 10.6% (9.5-11.8%; 15.3%) |
| fish regrowth (stock units) | 1,451.3 | 2,073.2 |
| fishery collapses / recoveries; mean recovery | 0 / 0 | 1 / 1; 161 turns |
| soil the mines took / the flat rule takes | 397.5 / 4,378.8 | 375.9 / 3,680.9 |
| per world, realized / flat: median (quartiles; max) | 0.08 (0.02-0.13; 0.49) | 0.09 (0.06-0.14; 0.22) |
| overextraction pressure, peak (per-world median) | 0.58 (0.41) | 0.56 (0.36) |
| slot-turns over sustainable; yield penalties | 0; 0 | 0; 0 |
| mineral slots exhausted (of); mine collapses | 36 (460); 1,459 | 4 (889); 169 |

Mineral depletion has followed realized output since PR #51: half to two
thirds of what the population proxy would draw (some worlds more: a small
population's proxy crew can sit below its miners). The fishery's landed-catch
rule keeps about a ninth of each allowance in the water, fish `main` debited
unlanded: `main`'s matched worlds have seven fishery collapse events (four
template slots still below 0.6 after 500 turns), the branch's none; in the
procedural subsets, where the other corrections leave the trajectories
identical, the landed-catch rule alone removes all six of `main`'s (section
5). The mines' soil charge falls to a tenth. Overextraction and its penalty
stay dormant. Mine collapses rise in the matched worlds (329 -> 440, 15 ->
24) and the procedural full gate (151 -> 169), not in the template full gate
(1,485 -> 1,459): mining regions keep more soil and people and mine more,
and a collapse needs a reserve under 0.3 (mean final reserves 0.01-0.02
lower in the matched worlds); exhaustion moves little (42 -> 36 and 4 -> 4
in the full gates).

## 10. Identity and the restore keys

| Key (default 1) | 0 restores |
| --- | --- |
| `ecology.overextraction_realized` | the streak on population / 5 |
| `ecology.mine_soil_realized` | the flat charge per active mine |
| `ecology.fishery_charges_landed_catch` | the whole allowance charged |
| `ecology.yield_penalty_reaches_goods` | yields from base yields |

The native keys go through `set_extraction_config` (sent only when a key
is 0). Identity, every output file compared (bundle without
`generated_at`), `main` `8142c48` and the branch given the same tuning file
(`main` ignores the keys):

| Check | Worlds | Result |
| --- | --- | --- |
| all four keys 0 against `main` | template 42, 43 (200 turns, hybrid, sidecar) | 110 + 110 files, 0 differ |
| all four keys 0 against `main` | procedural 7: 8 regions (100 turns), 32 regions x 10 civs (100 turns) | 59 + 65 files, 0 differ |
| defaults, `--agents off` | template 42 (200 turns) | 9 files, 0 differ |
| mine soil 0 (three corrections on) against `main` | template 42-51 (200 turns, bundles); procedural subsets 42-61 and 62-81 (validated) | template: every history row identical; procedural: the validate reports equal `main`'s in every field (paths and timestamps aside); final fish stocks and fishery events differ |

Golden oracles: the Python off-mode lane (`test_performance_equivalence.py`)
passes unchanged.

## 11. Tests

Linux, Python 3.13.17; the branch venv with the release extension above
(`c8ef41f5...b6ff`, built from `b51ec01`'s Rust; compiled module and the three
classes checked), the no-Rust venv without `chronicler_agents`; Cargo with
`CARGO_PROFILE_TEST_DEBUG=0` in its own target directory.

| Check | Result |
| --- | --- |
| `cargo test --locked` | 1,038 passed, 0 failed, 2 ignored (`main`: 1,028); new `tests/test_production_ledger.rs` (10); `test_ecology.rs` schema test, 33 columns |
| `pytest -m "not slow"` (native) | 6,570 passed, 3 skipped, 526 subtests |
| `pytest -m slow` (native) | 12 passed, 3 skipped |
| no-Rust lane (`pytest`, no extension) | 6,323 passed, 251 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS in 80.3 s; new `production-ledger` chunk (17 passed, 8 native skips) |

New: `tests/test_production_ledger.py` (17: the penalty in the yields, bits
kept when undegraded, uninitialized slots, scenario slots, the realized take,
the landed-catch return and its fallbacks, slot output in the Python oracle,
the ledger's balances over 40 off-mode turns of two seeds, that it reads
only, negative controls, the goods check, the file round trip),
`tests/test_production_ledger_native.py` (8: hybrid template and procedural
turns balance, the sidecar's ledger reconciles, the ledger changes no bundle,
the restore keys, the ledger columns consumed once, the off-mode simulator's
proxy). Changed expectations: `tests/test_ecology_bridge.py` (the ecology
batch's ledger columns); `scripts/qualify_third_wave.py`, the independent
fishery oracle of `tests/test_third_wave_joint.py`, now returns the unlanded
allowance before regrowth (and checks the native landed catch against its
own production).

## 12. Open items

- **Overextraction is unreachable.** Realized pressure peaks at about half
  the sustainable level; the streak and its penalty (now in the yields) are
  correct but dormant at `workers_per_yield_unit` 200. Calibrating it is a
  separate decision.
- **The fishery allowance is sized by a labour proxy** (the snapshot's
  farmers, food-first, without the farm curve, the city labour factor or the
  season ahead). It is a cap: the stock is now charged only what is landed,
  but where the economy could land more than the allowance the cap binds on
  the proxy. Sizing it from the harvestable stock alone would change the
  fishery's dynamics.
- **Timber takes no forest cover**; clearing is population-driven. Making
  the harvest deplete cover needs its own calibration.
- **Soil degradation and recovery are population pressure** (M35b decision
  7, recalibrated by the food-balance corrections); crop output does not
  charge the soil.
- **Herd food is a flow from the herd** and grazing degrades no pasture; the
  herd's food scales with the farm labour on the first food slot.
- **The procedural needs signal is lower** with the mine-soil correction
  (full gate pooled -0.021, binding -0.019; both subsets in the same
  direction, 42-61 failing the seed fraction by one seed); the template full
  gate moved -0.006 and the template subset up. The mechanism (which agents'
  needs and behaviour decouple when mining regions keep their soil) was not
  traced beyond the material and social pairings.
- **Mine collapses rise** where mining regions keep more soil and people
  (procedural full gate 151 -> 169; matched 500-turn template worlds 329 ->
  440, the template full gate 1,485 -> 1,459).
- The mine-soil anchor is the deposit's target crew, as PR #51's depletion;
  a crew-independent anchor would be a recalibration.
- The frontier settlement gate's `annual_yield_potential` reads undegraded
  potential (only matters once a penalty fires).
- Shadow and demographics-only modes run the same corrections (they have an
  economy tick) but were not run; the population check still covers
  `--agents off` only.
- Not run: determinism profiles, viewer checks (no viewer change), `uv sync
  --frozen` environments (the venvs were pip-installed).
- Operational: the full-gate batches were pruned during the runs of what the
  validator does not read (state files and memory streams of finished seeds)
  for disk space; batches, venvs and targets are deleted, reports kept.

## 13. Correction (2026-10-27): the mines' soil charge reads the crew before the soil step

Branch `fix/mine-soil-ordering` from `main` `2106ef2` (PR #57), merged
without rebase with `8a68658` (PR #58, public granaries: Python only, off by
default and byte-identical to `2106ef2` when off). Code: Rust `ecology.rs`
(`tick_soil_controlled_ledger`, `tick_ecology_with_ledger`). Tests:
`chronicler-agents/tests/test_production_ledger.rs` (2 new),
`tests/test_production_ledger_native.py` (1 new case). This is a behavioural
correction. It adds no state, column, tuning key or checkpoint field.

**Finding.** The grain-reserves work (PR #58, `grain-reserves.md` section 4)
found that with `CHRONICLER_CHECK_RESOURCES=1` the mines' soil check (section
7) raised in some procedural worlds. The ecology tick recorded
`mine_crew_ratio` (section 6) just before the soil step. The step
(`tick_soil_controlled_ledger`) then took the overpopulation loss (0.005 a
turn, doubled under soil pressure, while population exceeds the land's
potential). Then it called `mine_crew_ratio` again for the charge, from the
lowered soil. Where that loss took the effective capacity across a multiple
of three, the charge's crew was one smaller (N -> N-1), so the mines took
N/(N-1) of the rule's soil.

Linux, Python 3.13.17, `PYTHONHASHSEED=0`, hybrid, `--validation-sidecar`,
every check raising unless stated:

| Run | Result |
| --- | --- |
| `main` `2106ef2`, procedural 32 x 10, seed 64 | raises at turn 27: region 3 (64 people, potential 63), mines took 0.0121226, the rule says 0.0113649 (16/15) |
| `main` `8a68658` with `--grain-reserves`, seed 42 (PR #58's example) | raises at turn 128: region 25 (47 people, potential 44), 0.012847907841205597 against 0.01177724960944243 (12/11) |
| `main` `2106ef2`, seed 42, 300 turns | clean: the turn-128 case needs the switch on |
| `main` `2106ef2`, procedural seeds 42-141 x 300 (the full gate's cohort), the mines' soil check recorded instead of raised | 16 mismatches in 14 of 100 worlds (seeds 58, 64, 69, 84, 94, 95, 99, 104 (3), 107, 116, 121, 129, 135, 138), turns 27-280; every other check passed |
| `main` `2106ef2`, template seeds 42-81 x 500, recorded | 6 mismatches in 4 of 40 worlds (46 (2), 60, 65, 74 (2)), turns 37-456 |
| `main` `8a68658` with `--grain-reserves`, procedural seeds 42-72 x 300, recorded | 10 mismatches in 7 of 31 worlds (42, 45, 49 (2), 51 (3), 55, 58, 63), as PR #58 recorded |

Every mismatch is in a crowded region (1-22 people above the potential).
The charge was N/(N-1) of the rule for crews of 3 to 22: 3/2 at template
seed 74's turn 41, 22/21 at procedural seed 84's turn 47. The mines took
0.0001-0.0215 more soil than the rule per mismatch: 0.033 in total over
the 100 procedural worlds and 0.031 over the 40 template ones.

**Which fix.** One option is (a): the charge reads the crew from before the
soil step, as the ledger records and section 6 states. The other is (b): the
ledger records the crew the charge used. (b) changes no trajectory, but it
rewrites the rule around an ordering artifact. (a) is taken because realized
extraction should drive the charge:

- The charge scales the flat rate by this turn's ore output over what a
  target crew produces on the deposit as it was worked. The economy mined
  that ore in Phase 2, on the land as it stood before Phase 9. The
  overpopulation loss comes after the ore was taken.
- Under (b) crowding is charged twice: once by its own loss, and again by
  shrinking the crew the ore is divided by. The same ore would cost a
  crowded region's mines 5-50% more soil (1/(N-1)). This would happen only
  in regions above their potential, and only when the loss happens to cross
  a multiple of three. The rule would also depend on the order of two terms
  in one step: if the mine charge were applied before the overpopulation
  loss, it would already be (a).
- Under (a) the charge, the ledger and section 6 describe one rule: the
  ratio is computed once, before the step, and both read it.

**Fix.** `tick_soil_controlled_ledger` now takes `mine_crew_ratio` once,
before the overpopulation loss. It records the ratio in the ledger and
multiplies the charge by the same value. `tick_ecology_with_ledger` no longer
computes it separately. A region-turn without a crossing gets the same f32
product as before, bit for bit. Nothing is added to the native state, so
`persist.rs` does not change.

**Effect.** The comparison uses matched worlds. `main` `2106ef2` ran with its
own venv and release extension, `99c1e1d5...e12f`, the same build as the
oracle follow-ups' gates. The branch ran with `da65b716...cf67`. Every output
file is compared (`chronicle_bundle.json` without `generated_at`), along with
each region's soil and population after every turn:

| | procedural 42-141 x 300 | template 42-81 x 500 |
| --- | --- | --- |
| worlds identical, every file | 86 of 100 | 36 of 40 |
| worlds that differ | 14: exactly the worlds where `main` fired, each from the turn of its first mismatch | 4: the same rule |
| of them, populations differ | 8 (58, 64, 69, 84, 94, 99, 107, 116) | 0 |
| of them, soil only, transient | 6: 5-33 region-turns, until both arms meet at the terrain's soil cap or floor | 4: 2-13 region-turns; in 46 and 65 only the bundle and the resource ledger differ (soil +0.0001-0.0005, no validator input) |
| region-turns whose soil differs | 2,964 of 960,000 (0.31%) | 30 of 160,000 |
| region-turns whose population differs | 24,751 (2.6%, all after a divergence) | 0 |
| final population, all worlds | 53,741 -> 53,807 (+0.12%) | 7,243 -> 7,243 |
| final population, changed worlds | 7,215 -> 7,281 | 687 -> 687 |
| mean soil over the run, changed worlds | 0.66244 -> 0.66237 | 0.67712 -> 0.67712 |
| soil the mines took, changed worlds | 70.97 -> 68.75 | |

The correction itself takes 0.0001-0.0215 less soil in one region-turn.
The populations and soils that follow differ because a diverged world goes
its own way, not because of a systematic shift: seed 64 ends with 561 -> 482
people, seed 107 with 497 -> 629. The gates' batch manifests hash every
validator input of every run, and they show the same pattern at full scale.
Template full: 180 of 200 worlds have every validator input identical to
`main`'s baseline batch, and 20 differ (9 with different agent events, 11 in
needs and state snapshots only). Procedural full: 86 of 100 are identical,
and the 14 that differ are exactly the 14 where `main` fired (8 with
different events, 6 in snapshots only). The gates ran without the check, so
the ledger is not what moves them.

With `--grain-reserves` (`8a68658` against the branch, procedural seeds
42-72 x 300), 24 of 31 worlds are identical. The 7 that differ are exactly
the worlds where `8a68658` fired, each from that turn. The turn-speed
identity matrix (`scripts/turn_speed_identity.py`, 9 cases: off, hybrid,
procedural and scaled worlds), `main` against the branch: 399 files, 0
differences. None of those worlds crosses a crew boundary.

**Checkpoints.** No native state was added, so `persist.rs` is unchanged.
`scripts/checkpoint_identity.py` ran on the branch with
`CHRONICLER_CHECK_RESOURCES=1`: `hybrid_s42` (59 resume points) and
`proc32_hybrid_s11` (39) both PASS, with 0 differences, and plain against
straight with checkpoints also shows 0 differences.

**Checks with the correction.** With every check raising, there were zero
raises in:

- procedural 32 x 10 seeds 42-141 x 300 (100 worlds);
- template seeds 42-81 x 500 (40 worlds);
- procedural seeds 42-72 x 300 with `--grain-reserves` (31 worlds, granary
  checks included), the seven worlds above among them.

**Gates.** `--profile full --parallel 3 --require-strict-regression`, fresh
empty roots, manifests verified. The baselines are `main`'s reports under
needs method 6 and cohort method 3: the oracle follow-ups' full gates of
`99bfb7d`, whose `src/`, `chronicler-agents/` and extension are `2106ef2`'s.

| | template 200 x 500: baseline | branch | procedural 100 x 300: baseline | branch |
| --- | --- | --- | --- | --- |
| gate | PASS, strict | **PASS, strict** | PASS, strict | **PASS, strict** |
| comparator | | **NO REGRESSION**, same cohort | | **NO REGRESSION**, same cohort |
| needs pooled (lower bound), seeds | +0.1656 (+0.1436), 154 of 200 | +0.1648 (+0.1433), 156 | +0.0910 (+0.0662), 72 of 100 | +0.0892 (+0.0646), 72 |
| needs binding (lower bound), pairs | +0.1910 (+0.1639), 4,109 | +0.1859 (+0.1593), 4,115 | +0.1341 (+0.0982), 1,984 | +0.1356 (+0.1004), 2,006 |
| cohort (method 3): seeds, median effect | 200, 2.0 | 200, 2.0 | 100, 1.0 | 100, 1.0 |
| era collapse episodes | 4,662 | 4,666 | 4,436 | 4,431 |
| artifacts per civ per 100 turns; loss rate | 1.846; 0.055 | 1.849; 0.053 | 2.500; 0.036 | 2.497; 0.036 |
| arcs: seeds with three types | 152 | 151 | 97 | 97 |
| migration / rebellion per agent-turn | 0.06348 / 0.03287 | 0.06340 / 0.03295 | 0.07548 / 0.03874 | 0.07555 / 0.03863 |
| satisfaction mean (latest) | 0.6213 (0.6341) | 0.6212 (0.6330) | 0.5671 (0.5751) | 0.5667 (0.5741) |
| Gini in range; extinct worlds; full civ survival | 0.853; 0; 0.165 | 0.852; 0; 0.170 | 0.901; 0; 0.08 | 0.910; 0; 0.08 |
| wall time (3 workers, shared machine) | | 2,340 s | | 3,192 s |

**Tests.** These ran in the branch venv with its extension; the compiled
`chronicler_agents.chronicler_agents` and the three classes were checked.

| Check | Result |
| --- | --- |
| `cargo test --locked` (`CARGO_PROFILE_TEST_DEBUG=0`) | 1,053 passed, 0 failed, 2 ignored |
| the 2 new Rust tests against `main`'s source (its own target) | both fail (charged 0.03272727 = 0.03 x 12/11; the sweep at its first soil level), the other 10 pass |
| `pytest -m "not slow"` (native) | 6,669 passed, 3 skipped, 526 subtests |
| `pytest -m slow` (native) | 12 passed, 3 skipped |
| no-Rust lane (`pytest`, no extension) | 6,412 passed, 261 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS in 108.6 s (2,675 passed, 59 skipped) |
| `test_production_ledger_native.py` on `main` with the new case | the seed-64 case fails at turn 27 (16/15), the rest pass |

The new tests:

- `the_mines_soil_charge_reads_the_crew_before_the_soil_step`: a crowded
  mine whose loss takes the effective capacity from 36 to 35. The charge is
  exactly the flat rate, and the soil is 0.5660 where the recomputed crew
  left 0.5633.
- `the_mines_soil_charge_is_the_ledger_ratio_across_crew_boundaries`: soil
  levels 0.30-0.95, crowded and not, with at least 20 crossings. The charge
  is the recorded ratio times the flat rate, bit for bit, and the ratio is
  the pre-tick one.
- `test_hybrid_turns_balance_the_resource_ledger` gains procedural seed 64
  to turn 28.

**Open.** The reserve depletion (PR #51) divides the output by the target
crew after the whole tick (soil, water, forest, cross-effects and the river
cascade: `ExtractionLedger::target_crew`). The soil charge divides by the
crew before it. Section 6's "the same anchor" therefore holds except where
the tick's own soil or water change crosses a multiple of three. The
depletion's check uses the crew it drew with, so it balances. Aligning the
two would move trajectories wherever any of the tick's changes crosses a
crew boundary, water included, and needs a decision of its own.
