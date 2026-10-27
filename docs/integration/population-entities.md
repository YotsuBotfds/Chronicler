# Population conservation and entity lifecycles (2026-10)

Branch `fix/population-entities` from `main` `18a05be` (PR #46), merged
without rebase with `22c021b` (PR #47, validation integrity, needs oracle
method 4), `dae4ba5` (PR #48, procedural open items), `2f654a8` (PR #49,
cohort oracle method 2) and `1cf3e74` (PR #50, viewer only). Behavioural
corrections, not optimizations: every one changes simulation output on
purpose, and each section below states its own effect. An external review
(line references against `fc01d6e`) reported eight items; each claim was
reproduced on `main` with a test before it was fixed ([Findings](#findings));
the Python tests were rerun against `dae4ba5` and every claim test fails
there.

Code: `src/chronicler/utils.py` (population helpers, debug ledger),
`ecology.py` (famine refugees), `climate.py` (overflow migration),
`simulation.py` (the debug check), `politics.py` and `politics_bridge.py`
(restorations recorded), `agent_bridge.py` (native deaths),
`historical_context.py` (the end of an ascended person's active life),
`agent_movements.py` (faith slots); Rust `demographics.rs` (initial
occupations), `spatial.rs` (coincident repulsion), `economy.rs`,
`region.rs`, `ecology.rs` and `ffi/mod.rs` (realized extraction). Tests:
`tests/test_population_conservation.py`,
`tests/test_population_entities_native.py`, `tests/test_agent_movements.py`,
`chronicler-agents/tests/test_population_entities.rs`,
`chronicler-agents/tests/test_spatial.rs`.

## Findings

| # | Claim | On `main` | Test that failed there |
| --- | --- | --- | --- |
| 1 | `add_region_pop` caps existing residents | Yes: 100 people on room for 48, one arrival: 48. A negative amount even drove a population negative (2 + -3 = -1) | `test_arrivals_never_remove_the_residents_of_a_crowded_region`, `test_tiny_populations_against_a_capacity_of_two` |
| 2 | Famine refugees create people | Yes: draining 1 person with 3 foreign neighbours took the total from 31 to 33; an uneven split (5 among 3) lost 2 | `test_one_refugee_among_three_neighbours_is_one_person`, `test_refugees_split_with_the_remainder_in_region_order`, `test_shadow_mode_keeps_the_conserving_python_drain` |
| 3 | Ascended movement founders never die | Yes: after the crowned founder's native death, `alive=True`, `death_turn=None`, no `character_death`, dynasty not extinct | `test_a_crowned_founder_dies_a_natural_death_later` |
| 4 | Recycled religion ids pass old reforms on | Yes: faith 4 was taken by a new sect while a toleration in force still named 4 (the native reform table matches believers by that number) | `test_a_recycled_faith_slot_never_carries_an_old_reform_or_movement`, `test_a_faith_referenced_only_by_reforms_is_not_free` |
| 5 | Occupation rounding creates agents at init | Yes: population 5 spawned 6 agents, 6 spawned 7 (the only two populations up to 100,000) | `test_initial_spawn_makes_one_agent_per_person` (native) |
| 6 | Coincident repulsion mixes id and slot spaces | Yes: ids 1 and 2 in slots 0 and 1 at one point drifted at 0 and 2 degrees, (+0.040, 0) and (+0.040, +0.0014), the same way | `test_coincident_pairs_are_pushed_apart` (Rust, run against `main`'s source in an isolated target) |
| 7 | Mineral depletion ignores realized extraction | Yes: 60 people, no farm labour (`farm_labor_factor` 0), no ore produced: reserves 1.0 -> 0.9892 after one turn, 0.9136 after eight, 0.892 after ten | `test_a_mine_without_miners_keeps_its_reserves` (native) |
| 8 | Conservation tests | Added (below) | |

Hybrid and demographics-only modes have no Python famine drain or refugees
(`agents_own_population` in `_check_famine_yield`): confirmed by
`test_agent_owned_populations_have_no_python_famine_drain_or_refugees`.
Items 1 and 2 act where Python owns population: `--agents off` and shadow.

## 1. Arrivals keep the residents

`utils.add_region_pop(region, amount, cap=None, flow="added")` set the
population to `min(population + amount, cap)`. A region above its effective
capacity (soil, water or a disaster lowered it) lost residents whenever
anyone arrived: growth, repopulation, a migration event's settlers,
overflow migrants and famine refugees all trimmed it to capacity. It now
accepts `max(0, min(amount, cap - population))` people, never removes
anyone and returns the number accepted.

Callers, audited:

| Caller | People asked for | Those not accepted |
| --- | --- | --- |
| `phase_production` growth and repopulation | births | are not born |
| `_apply_event_effects` `migration` (+10 to the region with most room) | settlers from outside | do not come |
| `climate.process_migration` overflow | the surplus of a region below half its population's capacity | die on the way (as before, when the destination clamp removed them) |
| `ecology._check_famine_yield` refugees | the famine toll | die on the way |

No caller used the return value before; the two migration paths now record
it. **Decision:** migrants and refugees a full region cannot take die. They
left a region that could not feed them, the no-neighbour case already
counts the whole toll as deaths (`famine_starvation` for overflow), and the
source's toll stays independent of its neighbours. "Staying home" would
keep a starving or over-capacity region full and have its toll depend on
the room next door.

## 2. Famine refugees are conserved

Each eligible (foreign-held) neighbour received `max(1, drain // n)`: one
refugee among three neighbours became three people, five among three
became three (two vanished). `ecology.refugee_shares` now splits exactly the
drained total: `drain // n` each, the remainder one at a time to the
neighbours lowest in `world.regions` order. A share can be 0 when there are
fewer refugees than neighbours; only neighbours offered refugees take the
-5 stability (before, every eligible neighbour received at least one and
the penalty). Refugees a full neighbour cannot take die (item 1).

## 3. Founders die after their ascension

A liberty movement's founder crowned by its secession
(`agent_movements._secede`) and an exile restored to the throne
(`succession.py`) leave the civ rosters with `fate="ascended"`, still
`alive`, into `world.retired_persons`. `AgentBridge._process_deaths`
searched the rosters only, so their agents' later deaths were dropped. A
death outside the rosters is now resolved through the permanent registry
`gp_by_agent_id` (`_retired_person_death`): `alive=False`, `death_turn`,
a `character_death` event (actors: the person and their recorded
civilization), and the dynasty extinction check sees it. The ascension stays
the person's `fate`; `historical_context._end_turn` dates the end of an
ascended person's active life at the ascension (their last dated deed up
to the death), so a view between the throne and the death says
`ascended`, alive, and a view after it `ascended`, dead. A second report of
the same death changes nothing.

## 4. Faith slots keep their reforms

When the 16-faith registry is full a schism takes the slot of a faith no
one holds (`_extinct_faith_slot`). It counted agents, regions, rulers,
temples, builds and the one-turn signals, not the movement state, so a
toleration in force (whose faith number the native reform table matches
believers by) passed to the unrelated church that took the slot. A slot is
now also kept by: a toleration in force, a toleration repealed within
`REPEAL_MEMORY` (60 turns) and not lapsed (a movement may seek its
restoration by that number), and a living movement's faith. With every free
faith referenced the sect rises instead (as for a full registry before).
This is the smaller change: no reform is lapsed and no event added. The
longer-term fix is a permanent religious identity separate from the
reusable native slot (governance conversion ambitions and great-person
spread-faith agendas also hold faith numbers; they were not changed).

## 5. Initial occupations from a conserved budget

`set_region_state`'s initial spawn rounded each share (60/15/10/10%) half
up on its own and gave priests `population - spawned` only when positive,
so 5 people became 6 agents (3/1/1/1) and 6 became 7 (4/1/1/1).
`demographics::initial_occupation_counts` takes the shares in occupation
order from a conserved budget, each rounded as before but never beyond the
people left; priests take the rest. 5 gives 3/1/1/0/0 and 6 gives 4/1/1/0/0
(the largest-remainder split, too); every other population up to 100,000
keeps its counts.

**RNG and identity.** Personality and age streams are per region, so draw
counts change only in a region of 5 or 6 people. But agent ids and pool
slots are sequential across regions: one agent fewer shifts every later id,
and id-seeded draws (names, spatial seeds, promotions) change, so the whole
world diverges. Such a world is rare: 14 of the 200 template full-gate
worlds (one region each, one agent fewer), 1 of 20 template subset worlds,
none of the 20 procedural subset worlds. Every hybrid world diverges anyway
through items 6 and 7: on the `18a05be` merge base all 20 template subset
worlds' history snapshots differ from `main`'s from turn 1 (8 worlds), 2 (7)
or 16 (5).

## 6. Coincident repulsion in one identity space

The zero-distance fallback of the drift step hashed the focal agent's
stable id against the neighbour's pool slot. With ids 1 and 2 in slots 0 and
1 the pair got angles 0 and 2 degrees and moved together. Both sides are
pool slots now (the identity space of the neighbour lists and of the
self-exclusion): a pair gets `(a ^ b) % 360` degrees, the lower slot
flipped by half a turn, so exactly opposite pushes. The scalar reference
(`compute_drift_for_agent`, whose fourth argument is now `agent_slot`), the
per-agent path and the 8-lane path changed together. The equivalence tests
(`exact_block_path_is_bit_identical_to_reference`,
`exact_lanes_are_bit_identical_to_reference`) pass slots to the reference
and still compare all three paths bit for bit, duplicates and dense knots
included; `test_coincident_pairs_are_pushed_apart` checks the production
step in exact and fast modes with ids offset from slots (0, 1 or 3 retired
agents first).

## 7. Minerals deplete by what was extracted

`ecology::compute_yields` depleted a mineral slot by `base x (population /
5) / (effective capacity / 3)` whatever the economy did (as does Python's
`compute_resource_yields`, the off-mode oracle, which keeps it). The agent economy now records what each slot
produced (`EconomyRegionResult::slot_output`, the same `amount` it adds to
the goods); `AgentSimulator::tick_economy` keeps it on the region
(`RegionState::realized_extraction`) and the next `tick_ecology` depletes
by `output / target crew x depletion_rate` and clears it (consumed once;
`test_ore_produced_depletes_and_is_consumed_once`). Goods per miner average
the base yield on healthy land, so a target crew of miners depletes at the
old average rate; no miners deplete nothing; output and depletion fall
together under the reserve ramp; abundance and technique multipliers raise
both. Without an economy tick (`EcologySimulator`, `--agents off`, or an
agent-mode tick before any economy tick) the population proxy is kept bit
for bit, so off-mode runs and the Python/Rust ecology parity suite are
unchanged. Overextraction's yield degradation (separately documented as not
reaching goods) was not touched.

## 8. Conservation checks

`tests/test_population_conservation.py`: the region total changes only by
births, deaths and migration on every touched path, with populations 0, 1
and 2 and crowded destinations (refugees, overflow migrants, growth); the
agent-owned modes have no Python drain; shadow keeps the conserving drain.

**Debug ledger.** The population helpers record each change as a flow:
`added` (births, arrivals from outside), `removed` (deaths), `emigrated`
and `immigrated`; `set_region_pop` records a restoration's settlers. With
`CHRONICLER_CHECK_POPULATION=1` an `--agents off` turn starts a ledger and
checks at its end that the regions' total changed by exactly `added -
removed + immigrated - emigrated` and that `immigrated <= emigrated`
(migration creates no one); otherwise it costs one environment read per
turn. Negative controls: a stray `population += 1` and the old refugee rule
both raise. Tests run 40 turns of seeds 42 and 7 with it on; 200-turn CLI
runs of seeds 42 and 7 pass it.

## Measured effects

### Aggregate population (items 1, 2): `--agents off`

`main` `dae4ba5` (its simulation is byte-identical to `2f654a8`'s) against
the branch, CLI runs (`--agents off --simulate-only`, every default of a
fresh run), template seeds 42-61 and procedural (32 regions, 10 civs) seeds
42-51, 300 turns each. The population helpers were wrapped to record, per
calling path, the people asked for and what the region gained (a negative
gain is residents the old clamp removed); overflow migrants are read from
the `migration` events' "(N displaced)".

| | template `main` | template branch | procedural `main` | procedural branch |
| --- | --- | --- | --- | --- |
| mean population over the run (per world) | 243.1 | 253.2 (+4.2%) | 872.8 | 909.2 (+4.2%) |
| final population (all worlds) | 4,596 | 4,910 | 8,252 | 8,944 |
| lowest world population after turn 10 | 51 | 64 | 336 | 377 |
| civs alive at the end | 75 | 70 | 145 | 140 |
| residents removed by arrivals | 9,551 | 0 | 14,769 | 0 |
| of which by famine refugees | 7,551 | 0 | 11,296 | 0 |
| famine reports | 3,149 | 3,208 | 3,558 | 3,724 |
| famine tolls (people drained) | 4,887 | 5,037 | 5,840 | 6,256 |
| refugees placed (asked) / settled | 6,263 / -5,999 net | 4,868 / 1,059 | 11,534 / -6,853 net | 6,173 / 2,166 |
| overflow `migration` reports | 1,026 | 1,298 | 2,131 | 2,524 |
| overflow migrants | 3,313 | 10,276 | 3,513 | 12,372 |
| of them settled | (clamped: -779 net) | 859 | (clamped: -1,100 net) | 2,226 |
| `famine_starvation` (no neighbour) | 4 | 8 | 2 | 12 |
| growth refused for want of room | 50,573 | 43,364 | 58,750 | 49,435 |

On `main` the refugee and migrant arrivals removed more residents than
they brought (net -5,999 refugees in the template worlds). The deaths the
old clamp hid now fall where they belong: crowded regions stay crowded
until they lose capacity by half, so overflow migration fires 27% (template)
and 18% (procedural) more often and moves three times as many people, most
of whom find no room and die. The net effect is 4% more people on average
and higher minima; slightly fewer civs survive 300 turns (75 -> 70,
145 -> 140).

The famine refugee rate itself: refugees now equal the toll wherever a
foreign neighbour exists (4,868 placed of 5,037 drained; the rest fell in
regions without one). Before, each famine placed `max(1, drain // n)` per
neighbour: 6,263 placements against 4,887 people drained by every famine,
with or without a neighbour.

### Hybrid gates

`scripts/m53b_run_validation.py`, fresh empty output roots, every report's
batch manifest verified (exactly the requested seeds and turns), needs
oracle method 4. Subsets: `--profile subset --parallel 1` with
`PYTHON_CPU_COUNT=2` (one worker), `--worldgen procedural` for the
procedural world, `main` `dae4ba5` (cohort method 1; simulation identical
to `2f654a8`) against the branch at its `dae4ba5` merge (simulation identical
to the final head), compared with `python -m chronicler.validation_compare
--profile subset --baseline-report <main> --current-report <branch>`: NO
REGRESSION for both worlds, same cohort.

| subset (20 x 200) | template `main` | template branch | procedural `main` | procedural branch |
| --- | --- | --- | --- | --- |
| gate | PASS | PASS | PASS | PASS |
| artifacts / arcs / regression (informational) | PASS / PASS / PASS | PARTIAL / PASS / PASS | PARTIAL / FAIL / PASS | PASS / FAIL / PASS |
| needs pooled (lower bound), seeds of 20 | +0.175 (+0.097), 14 | +0.135 (+0.045), 13 | +0.176 (+0.121), 19 | +0.126 (+0.059), 12 |
| needs binding (lower bound), pairs | +0.194 (+0.063), 211 | +0.153 (+0.009), 196 | +0.194 (+0.107), 360 | +0.163 (+0.059), 306 |
| cohort median effect | 1.347 | 1.272 | 0.867 | 0.723 |
| artifacts per civ per 100 turns; loss rate | 2.88; 0.028 | 2.93; 0.011 (below 0.02: PARTIAL) | 3.06 (creation fail); 0.034 | 2.99; 0.023 |
| migration / rebellion per agent-turn | 0.0689 / 0.0423 | 0.0668 / 0.0424 | 0.0778 / 0.0371 | 0.0768 / 0.0364 |
| mean population over the run (per world) | 188.0 | 189.8 | 583.6 | 575.5 |
| mineral slots exhausted at the end | 10 | 0 | 8 | 0 |
| mine collapses | 55 | 31 | 17 | 8 |

Every subset world diverges early, so a subset compares two samples of 20
worlds. The needs signal was lower on the branch in these subsets; a second
template range and two ablations (the branch with `main`'s `spatial.rs`, and
the branch without realized extraction, each built in its own target)
indicate sampling noise at that scale; the template full gate has the
branch higher, the procedural full gate lower (below):

| needs pooled (lower bound), seeds of 20 | seeds 42-61 | seeds 62-81 |
| --- | --- | --- |
| `main` | +0.175 (+0.097), 14 | +0.150 (+0.060), 13 |
| branch | +0.135 (+0.045), 13 | +0.269 (+0.153), 16 |
| branch with `main`'s repulsion | +0.219 (+0.149), 17 | +0.113 (+0.011), 13 |
| branch with the population proxy for depletion | +0.104 (+0.016), 12 | - |

**Template full gate** (200 x 500, `--profile full --parallel 3
--require-strict-regression`, the branch with `--baseline-report` `main`'s
report from the same oracle code): branch PASS strict, NO REGRESSION, same
cohort (200 runs of seeds 42-241, 500 turns).

| template full (200 x 500) | `main` `2f654a8` | branch `c0f354d` |
| --- | --- | --- |
| gate (required: community, needs, era, cohort, artifacts, arcs, regression) | PASS, strict | PASS, strict |
| needs pooled (lower bound), seeds of 200 | +0.174 (+0.155), 165 | +0.202 (+0.183), 174 |
| needs binding (lower bound), pairs | +0.172 (+0.147), 4,878 | +0.182 (+0.158), 4,947 |
| cohort median effect (method 2) | 1.601 | 1.543 |
| community qualifying seeds | 200 | 200 |
| era collapse episodes | 4,650 | 4,728 |
| artifacts per civ per 100 turns; loss rate | 1.77; 0.060 | 1.88; 0.053 |
| arcs: seeds with three types | 160 | 159 |
| migration / rebellion per agent-turn | 0.0636 / 0.0364 | 0.0629 / 0.0340 |
| satisfaction mean (latest) | 0.6167 (0.6259) | 0.6210 (0.6347) |
| Gini in range; extinct worlds; full civ survival | 0.850; 0; 0.125 | 0.847; 0; 0.135 |
| mean population over the run (per world) | 187.6 | 188.4 |
| lowest world population after turn 10 | 40 | 21 |
| civs alive at the end | 564 | 568 |
| famine / dearth reports | 17,688 / 47,757 | 18,002 / 48,316 |
| mineral slots exhausted (of 460); mean reserve | 161; 0.482 | 42; 0.581 |
| mine collapses | 2,732 | 1,485 |
| schisms; movement schisms taking a vanished faith's slot | 2,541; 141 | 2,549; 149 |
| of those, over a toleration still remembered | 1 | 0 |
| worlds with a region of 5 or 6 at the start (one extra agent on `main`) | 14 | 14 |
| ascended persons at the end (all aggregate exiles restored, none agent-backed) | 39 (29 in three worlds) | 5 |

Per correction in hybrid: depletion (item 7) is the one broad systematic
effect (exhausted mineral slots -74%, mine collapses -46%); repulsion
(item 6) moves every trajectory, and the subset ablations do not separate
any gate metric's change from sampling noise;
items 3-5 are rare (one recycled slot over a remembered toleration in 200
worlds, 14 worlds with one extra agent, no agent-backed ascension); items 1
and 2 do not act in hybrid. The ascended count on `main` is dominated by
counter-restoration loops in three worlds.

**Procedural full gate** (100 x 300, 32 regions, 10 civs, `--profile full
--worldgen procedural --parallel 3 --require-strict-regression`, the branch
with `--baseline-report` `main`'s report): branch PASS strict, NO
REGRESSION, same cohort (100 runs of seeds 42-141, 300 turns).

| procedural full (100 x 300) | `main` `2f654a8` | branch `c0f354d` |
| --- | --- | --- |
| gate (all seven required oracles) | PASS, strict | PASS, strict |
| needs pooled (lower bound), seeds of 100 | +0.169 (+0.149), 89 | +0.132 (+0.111), 84 |
| needs binding (lower bound), pairs | +0.168 (+0.131), 2,526 | +0.136 (+0.099), 2,291 |
| cohort median effect (method 2) | 0.906 | 0.984 |
| community qualifying seeds | 100 | 100 |
| era collapse episodes | 4,386 | 4,500 |
| artifacts per civ per 100 turns; loss rate | 2.41; 0.042 | 2.36; 0.040 |
| arcs: seeds with three types | 99 | 100 |
| migration / rebellion per agent-turn | 0.0757 / 0.0389 | 0.0757 / 0.0401 |
| satisfaction mean (latest) | 0.5670 (0.5736) | 0.5641 (0.5702) |
| Gini in range; extinct worlds; full civ survival | 0.914; 0; 0.07 | 0.910; 0; 0.10 |
| mean population over the run (per world) | 546.9 | 543.9 |
| lowest world population after turn 10 | 209 | 218 |
| civs alive at the end | 852 | 842 |
| famine / dearth reports | 11,195 / 60,001 | 10,855 / 58,755 |
| mineral slots exhausted (of 889); mean reserve | 101; 0.740 | 4; 0.802 |
| mine collapses | 307 | 151 |
| schisms; movement schisms taking a vanished faith's slot | 838; 238 | 896; 296 |
| of those, over a toleration still remembered | 0 | 0 |
| worlds with a region of 5 or 6 at the start | 3 | 3 |
| agent-backed ascended persons; their agents died | 9; 8, all still recorded alive | 11; 11, all recorded dead |

Founders (item 3) show here: on `main` 8 of 9 agent-backed ascended persons
had died in the agent pool and were still alive in the record; on the
branch all 11 are recorded dead. The needs signal is lower on the branch in
this world (pooled -0.037, binding -0.032, both still well above zero);
the template full gate moved the other way (+0.028, +0.010). The pooled
drop is about 2.1 standard errors (0.013 each); the binding drop about 1.0
(0.022 each). An ablation full gate, the branch with `main`'s `spatial.rs`
(its own build, `e145f288...`, the same 100 x 300 cohort), PASS strict, NO
REGRESSION, gives pooled +0.151 (+0.125), 83 of 100, and binding +0.160
(+0.124), 2,491 pairs: about half of the pooled drop and most of the
binding drop go with the repulsion correction (each about one standard
error), the rest is not attributed. Coincident agents now separate; what
that does to the needs-behaviour concordance was not traced further.

## `main`'s first full qualification (needs method 4, cohort method 2)

`main` `2f654a8`, exported (`git archive`), its own venv and a release
extension built from `dae4ba5`'s Rust (unchanged in `2f654a8`), SHA-256
`735558c9...a489`, compiled module and classes checked; Linux, Python
3.13.17, `PYTHONHASHSEED=0`, fresh empty output roots, no baseline:

```sh
python scripts/m53b_run_validation.py --profile full --parallel 3 --require-strict-regression --output-root <root>
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 --require-strict-regression --output-root <root>
```

| | template full (200 x 500) | procedural full (100 x 300) |
| --- | --- | --- |
| gate | PASS, strict | PASS, strict |
| batch manifest | verified, 200 runs x 500 turns (seeds 42-241) | verified, 100 runs x 300 turns (seeds 42-141) |
| needs (method 4) pooled (lower bound), seeds | +0.174 (+0.155), 165 of 200 | +0.169 (+0.149), 89 of 100 |
| needs binding (lower bound), pairs | +0.172 (+0.147), 4,878 | +0.168 (+0.131), 2,526 |
| cohort (method 2) median effect | 1.601 | 0.906 |
| community, era | PASS (200 seeds), PASS | PASS (100 seeds), PASS |
| artifacts per civ per 100 turns; loss rate | 1.77; 0.060, strict | 2.41; 0.042, strict |
| arcs: seeds with three types | 160 | 99 |
| regression: migration / rebellion per agent-turn | 0.0636 / 0.0364, strict | 0.0757 / 0.0389, strict |
| extinct worlds | 0 | 0 |
| wall time (3 workers) | 2,199 s | 2,086 s |

The template batch of `dae4ba5` (cohort method 1, run first) gives the same
report except the cohort result (median effect 1.6007 against 1.6006),
confirming `2f654a8`'s simulation is `dae4ba5`'s.

## Golden oracles

The Python off-mode oracle is rolled forward as
`corrected_population_2026_10.json` and
`corrected_artifacts_population_2026_10.json` (the `population` link of
`ORACLE_CHAIN`, after `open_items`); `corrected_open_items_2026_10*` and
older fixtures stay frozen. The capture loop reproduces the open-items
fixtures on `main` `dae4ba5` byte for byte. Consecutive captures (arrivals
alone, then the refugee split), first changed turn (the same before and
after the `dae4ba5` merge):

| Correction | single | standard | wide |
| --- | --- | --- | --- |
| PE-ARRIVALS | 16 | 11 (RNG trace changes) | 0 (RNG trace changes) |
| PE-REFUGEES | - | 9 | 5 (RNG trace changes) |
| the agent-mode corrections | - | - | - |

The `wide` world changes at turn 0: a region above its capacity at the
start was trimmed by its first growth. The snapshot-pruning real run
(seed 1, 10 regions, 5 civs, 120 turns, off) is re-pinned: the Dorrathi
Clans fall at turn 76 and are pruned from 87, the Kethani Empire at 66 and
is pruned from 77 (before: Dorrathi from 115, Kethani restored).

## Tests

Linux, Python 3.13.17, venvs under the run directory (pip-installed
dependencies, not `uv sync`), release extensions built fresh with `maturin
develop --release --locked` (`main`'s in a Cargo target directory of its
own) and checked (compiled `chronicler_agents.chronicler_agents`; `AgentSimulator`,
`EcologySimulator`, `PoliticsSimulator` real classes): the branch at
`c0f354d` `83b76b41...5b87`, `main` (`dae4ba5`'s Rust, unchanged in
`2f654a8`) `735558c9...a489`.

- `cargo test --locked`: 1,028 passed, 0 failed, 2 ignored (at `39d71fc`;
  the Rust has not changed since). New: `tests/test_population_entities.rs`
  (7), `test_coincident_pairs_are_pushed_apart` in `tests/test_spatial.rs`;
  the in-file spatial equivalence tests now pass slots.
- `pytest -m "not slow"` (native, one process): 6,545 passed, 3 skipped;
  `pytest -m slow`: 12 passed, 3 skipped; the no-Rust lane (`pytest` with no
  extension installed): 6,306 passed, 243 skipped.
- `python scripts/run_python_oracle_checks.py`: PASS in 97.4 s, a new
  `population` chunk (27 passed, 4 native skips).
- New Python tests: `tests/test_population_conservation.py` (27),
  `tests/test_population_entities_native.py` (4, native),
  `tests/test_agent_movements.py` (+4: founder death, roster death, two
  faith-slot tests). Re-pinned: the golden oracle (above), the
  snapshot-pruning real run, and the two wave-3 resume tests, which now
  save at a turn without a capped tech focus (a raw `WorldState.save` drops
  `_focus_applied_deltas`, so a capped focus is removed by its full modifier
  after a load; on `main` the same world already breaks resume identity for
  every save turn from 35 to 46, each with a capped focus, and the test's
  save turn fell outside them; on the branch it fell at 62, inside 55-63);
  the four-system test moves to seed 44 (seed 42 takes no loan between turns
  40 and 300 on the branch).

## Not run, open

- Founder deaths (item 3) are rare in the gates: the 39 ascended persons of
  `main`'s template full gate are all aggregate exiles restored to a throne
  (no agent); the procedural subset on `main` had one agent-backed ascended
  person whose agent died while the record kept them alive.
- A seceded state's `Leader` keeps reigning after its founder's agent dies
  (the leader and the founder's agent are not linked); `factions.py`
  records `ascended_to_leadership` as dead at the ascension. Neither changed.
- Restorations set a region's population outright (30, or the payload's)
  whatever its residents; the ledger records the difference, the behaviour
  is unchanged.
- Faith slots: governance conversion ambitions and great-person
  spread-faith agendas also hold faith numbers; a permanent religious
  identity apart from the native slot is the longer-term fix.
- The debug ledger covers `--agents off` only (shadow mode's Python
  population is not checked).
- Overextraction's yield streak still reads `population / 5` workers
  (documented separately, not changed); demographics-only mode still writes
  `min(agent count, 1.2 x capacity)` into `region.population`.
- Raw `WorldState.save` drops applied tech-focus deltas (pre-existing; see
  Tests).
- The procedural needs drop (pooled -0.037, binding -0.032) is half
  attributed to the repulsion correction by one ablation; no full-scale
  depletion ablation was run, and the mechanism was not traced.
- Not run: a determinism profile, a shadow-mode run, viewer checks (no
  viewer change), `uv sync --frozen` environments (the venvs were
  pip-installed).
- Operational: a test built from an exported `main` tree (`git archive`,
  older file times) into the Cargo target last used by the branch linked
  the branch's library: Cargo found the unit fresh. `main`'s extension and
  the ablation builds were then built in target directories of their own.
