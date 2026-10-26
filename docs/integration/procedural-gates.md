# Procedural gate profile

Branch `feat/procedural-gates` from `main` `11238d5`, merged without
rebase with `aa0f655` (PR #40, guilds on by default), `2dd47d4` (PR #41,
narration) and `b3ad9a4` (PR #42, movement founders). Every run is Linux,
Python 3.13, `PYTHONHASHSEED=0`, hybrid, on a shared 4-core host, from a
frozen copy of the tested source, with a native extension built fresh from
it (`maturin develop --release --locked`) and its compiled
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` verified
(`aa0f655`: `5ede10a9...8b07d6`; `b3ad9a4` and the merged head:
`c26d6cd2...bbb99`).

## Why

The gate runner (`scripts/m53b_run_validation.py`) ran only the default
world: 8 template regions and 4 civs. `--worldgen auto` gives procedural
heightmap/Voronoi geography above 12 regions ([geography-2.md](geography-2.md)),
which is what users get on larger maps, and every recent system was gated on
templates only.

## Profile

`--worldgen procedural` runs every seed on a procedural world of
`PROCEDURAL_WORLD` regions and civs (default 32 and 10; `--regions` and
`--civs` override, and are refused for the template world).
`--worldgen template`, the default, runs the CLI's default world with the
same commands as before.

| Profile | template | procedural |
| --- | --- | --- |
| subset | 20 seeds x 200 turns | 20 seeds x 200 turns |
| full | 200 seeds x 500 turns | 100 seeds x 300 turns |
| determinism-off / -hybrid | 2 x 200 | 2 x 200 |

```sh
python scripts/m53b_run_validation.py --profile subset --worldgen procedural --parallel 2 --output-root output/m53/procedural-subset
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 --output-root output/m53/procedural-full \
    --baseline-report <earlier procedural full report>
```

The run manifest records `worldgen`, `regions` and `civs`.

### World size

32 regions and 10 civs: well past the 12-region template limit, inside the
24-48 regions and 8-12 civs users pick for a larger map, and 3.2 regions per
civ against the template world's 2. One size, so procedural reports compare
with each other; `--regions`/`--civs` measure other sizes (their reports
then name a different world and do not compare with the default's).

### Cost and the full profile's size

Measured per seed (500 turns, hybrid with validation sidecars, three runs at
once on the shared host, seeds 43-45 on `aa0f655`; CPU is user + system
time of the run):

| World | agents (mean) | CPU s | batch MB | validation s | validation memory MB |
| --- | ---: | ---: | ---: | ---: | ---: |
| template 8 x 4 | 208 | 24 | 22 | 3.3 | ~22 |
| procedural 24 x 8 (one seed) | ~550 | 70 | 60 | - | - |
| procedural 32 x 10 | 455 | 77 | 58 | 7.8 | 80-105 |
| procedural 48 x 12 | 762 | 106 | 88 | 13.9 | 90-145 |

Validation memory is the RSS a loaded seed run adds (the validator keeps
every seed's sidecar columns until the oracles finish; the template full
gate peaks at 4.4 GB). A 32 x 10 seed costs about 3.2 template seeds of
CPU, 2.6 of disk and 3-4 of validation memory. 200 x 500 would take about
4.3 CPU-hours (1.5-3 h on three workers), 12 GB of disk and 10-16 GB of
validation memory, more than this host can spare beside other agents (15
GB in all, 11-13 GB of disk free).

100 seeds x 300 turns is 0.3 of that work. Measured on `main` (three
workers, with other agents' simulations running): 32 minutes of
simulation, 14 minutes of validation at a 2.5 GB peak, 45 minutes in all;
the batch holds 2.8 GB once `state.json`, the memory streams and the
historiography/language sidecars of finished seeds are deleted (the
validator reads none of them), about 5 GB without. 100 seeds resolve the
seed-fraction oracles to 1%, and a procedural seed has 2-3.5 times the
agents of a template seed, so the needs and cohort oracles get more
agent pairs than the 200 template seeds give. 300 turns still give each
third of the arc classifier 100 turns, the regression oracle its 60-turn
late window and the era oracle 24-82 collapses per seed to mark; the
template full gate keeps the 500-turn horizon. The subset (20 x 200, two
workers) takes 8 minutes.

## Oracles on procedural worlds

The oracles and their thresholds are unchanged in meaning. One oracle
presumed the template world:

* **Artifacts.** The creation band (1-3 artifacts per civ per 100 turns)
  divided every batch's artifacts by a fixed 4 civs, the template world's
  count, so a 10-civ world read 2.5 times its rate. It now divides by each
  seed's starting civs (the civ rows of the first history snapshot). On
  template worlds that is 4, the same denominator, so template reports are
  byte-identical (checked on three template seeds).

The others normalise already: needs, cohort and community pair or group
agents within a seed; era and arcs score each civ's own series and count
seeds or civ shares; regression rates are per agent-turn, satisfaction is
agent-weighted, and civ survival asks that some civ lives (and that not
every starting civ survives in more than 20% of seeds).

Reports of batches with non-template worlds carry a `worlds` list
(generator, regions, starting civs, seeds); template reports have none, so
their bytes do not change. `chronicler.validation_compare` refuses to
compare reports of different worlds (a missing `worlds` means the template
world), so a procedural report cannot be read against a template baseline.

## Procedural worlds on `main`

### Gates

Procedural full (100 x 300) and subset (20 x 200, seeds 42-61) on `main`
(`541b51d`: `aa0f655` plus the gate tooling, no simulation change), with
the template gates for reference: the template full gate is the guilds
merge report (200 x 500), the template subset is 42-61 on the same tree.

| | template full (guilds, 200x500) | procedural full (100x300) | template subset | procedural subset |
| --- | --- | --- | --- | --- |
| gate | PASS | FAIL: artifacts | PASS | PASS |
| strict regression | strict | strict | fail | strict |
| community: seeds with a community | 200 of 200 | 100 of 100 | 20 of 20 | 20 of 20 |
| needs: seeds with net concordance > 0 | 172 of 200 (need 120) | 88 of 100 (need 60) | 14 of 20 (need 12) | 16 of 20 (need 12) |
| needs: pooled lower bound | +0.196 | +0.134 | +0.035 | +0.067 |
| needs: binding lower bound | +0.178 | +0.125 | +0.080 | -0.042 |
| cohort: seeds in the expected direction | 200 of 200 | 100 of 100 | 20 of 20 | 20 of 20 |
| era: seeds with inflections / silent collapses | 200 / 0 | 100 / 0 | 20 / 0 | 20 / 0 |
| arcs: families / dominance | 6 / none | 6 / none | 5 / cinderella 0.41 | 6 / cinderella 0.44 |
| artifacts: status | PASS | PARTIAL | PARTIAL | PARTIAL |
| artifacts per starting civ per 100 turns (1-3) | 1.71 | 5.38 | 3.02 | 5.93 |
| artifacts: largest type share ok / loss rate | True / 5.8% | False / 2.6% | True / 3.1% | True / 2.9% |
| satisfaction mean / latest | 0.617 / 0.627 | 0.561 / 0.564 | 0.606 / 0.621 | 0.568 / 0.578 |
| migration per agent-turn (0.05-0.15) | 0.0644 | 0.0748 | 0.0693 | 0.0751 |
| rebellion per agent-turn (0.02-0.08) | 0.0368 | 0.0353 | 0.0439 | 0.0362 |
| gini in range | 0.858 | 0.900 | 0.831 | 0.842 |
| all starting civs survive (max 0.20) | 0.180 | 0.110 | 0.250 | 0.150 |
| extinct worlds | 0 | 0 | 0 | 0 |
| final population min / median / max | 63 / 183 / 304 | 254 / 536 / 934 | 86 / 190 / 292 | 338 / 585 / 815 |

The procedural full gate fails one required oracle, artifacts: 5.38
artifacts per starting civ per 100 turns against the 1-3 band, and one
type above half of all artifacts (artworks). With the old fixed 4-civ
denominator it would have read 13.4. Everything else passes, regression
strictly: no world dies, migration and rebellion sit inside their bands,
needs passes in 88 of 100 seeds with both lower bounds positive.
Satisfaction is lower than on templates (0.56 against 0.62) and the
subset's binding lower bound is negative (-0.04; informational there).

### Per-system activity

Counts per starting civ per 100 turns, pooled over the worlds (in brackets
the share of worlds where the measure is above zero), from
`scripts/world_systems_report.py --per-civ-century`. The subsets share
seeds (42-61) and turns (200); the full batches add 100 procedural worlds
of 300 turns and 200 template worlds of 500 (template full: the gate after
the fix, which leaves four-civ worlds unchanged). Population, civ and
famine-share rows are per world.

| Measure | template | procedural | procedural, fix |
| --- | ---: | ---: | ---: |
| worlds | 20 | 20 | 20 |
| extinct worlds | 0.000 (0%) | 0.000 (0%) | 0.000 (0%) |
| population, start | 205.7 (100%) | 508.8 (100%) | 508.8 (100%) |
| population, final | 188.9 (100%) | 584.6 (100%) | 599.5 (100%) |
| population, minimum / start | 0.663 (100%) | 0.844 (100%) | 0.866 (100%) |
| civs at start | 4.000 (100%) | 10.0 (100%) | 10.0 (100%) |
| civ records at end | 4.000 (100%) | 10.2 (100%) | 10.5 (100%) |
| civs alive at end | 3.200 (100%) | 8.700 (100%) | 8.900 (100%) |
| famine region-turns (share of observed) | 0.284 (100%) | 0.252 (100%) | 0.250 (100%) |
| famine episodes | 3.881 (100%) | 6.857 (100%) | 6.680 (100%) |
| famine episode mean length (turns) | 8.105 (100%) | 4.999 (100%) | 4.994 (100%) |
| famine episodes of 20+ turns (share) | 0.106 (85%) | 0.015 (65%) | 0.012 (60%) |
| wars declared | 0.287 (100%) | 1.315 (100%) | 1.252 (100%) |
| calls to arms | 0.013 (10%) | 0.273 (95%) | 0.230 (95%) |
| federation defence calls | 0.031 (10%) | 0.497 (95%) | 0.440 (90%) |
| secessions | - | 0.007 (15%) | 0.018 (20%) |
| rebellions (civ events) | 2.081 (70%) | 2.530 (95%) | 2.585 (95%) |
| mass migrations | 11.1 (100%) | 12.6 (100%) | 13.5 (100%) |
| cities founded | 0.562 (100%) | 0.828 (100%) | 0.815 (100%) |
| cities alive at end | 0.463 (100%) | 0.632 (100%) | 0.615 (100%) |
| free cities | 0.000 (0%) | 0.005 (10%) | 0.007 (15%) |
| city commerce (cumulative) | 90.3 (100%) | 103.1 (100%) | 103.8 (100%) |
| guilds founded | 0.569 (100%) | 0.848 (100%) | 0.860 (100%) |
| guild privileges | 0.619 (100%) | 0.915 (100%) | 0.877 (100%) |
| burgher factions formed | 0.331 (100%) | 0.405 (100%) | 0.395 (100%) |
| movement news foundings | 0.212 (65%) | 0.430 (100%) | 0.367 (100%) |
| movements founded | 1.225 (100%) | 1.675 (100%) | 1.552 (100%) |
| reforms enacted | 0.375 (95%) | 0.450 (100%) | 0.448 (100%) |
| movement risings | 0.062 (35%) | 0.060 (45%) | 0.062 (75%) |
| movement secessions | 0.000 (0%) | 0.000 (0%) | 0.000 (0%) |
| sea trade (cargo units) | 5.913 (30%) | 66.5 (100%) | 66.4 (100%) |
| fleets commissioned | 0.075 (30%) | 1.558 (100%) | 1.285 (100%) |
| naval battles | 0.000 (0%) | 1.975 (95%) | 1.450 (95%) |
| overseas campaigns | 0.000 (0%) | 0.185 (90%) | 0.163 (90%) |
| colonies | 0.000 (0%) | 0.083 (85%) | 0.087 (85%) |
| nomad raids | 0.056 (35%) | 0.228 (65%) | 0.220 (75%) |
| hordes formed | 0.000 (0%) | 0.018 (35%) | 0.025 (30%) |
| nomad conquests | 0.013 (5%) | 0.043 (35%) | 0.037 (35%) |
| great persons born | 1.762 (100%) | 4.810 (100%) | 1.298 (100%) |
| artifacts created | 3.019 (100%) | 5.930 (100%) | 2.737 (100%) |
| trading houses founded | 0.362 (70%) | 1.365 (100%) | 0.395 (90%) |
| exiles restored | 0.013 (10%) | 0.058 (40%) | 0.072 (45%) |
| agendas declared | 5.638 (100%) | 9.995 (100%) | 4.817 (100%) |
| agendas fulfilled | 3.019 (100%) | 6.062 (100%) | 2.317 (100%) |
| epidemics (events) | 10.5 (100%) | 22.4 (100%) | 22.9 (100%) |
| epidemic deaths | 22.3 (100%) | 39.1 (100%) | 38.9 (100%) |
| loans taken (events) | 1.056 (95%) | 2.987 (100%) | 2.770 (100%) |
| loan principal issued (domestic + foreign) | 50.9 (95%) | 390.6 (100%) | 307.8 (100%) |
| loan principal written off | 6.994 (50%) | 54.9 (100%) | 57.5 (100%) |
| fiscal crises | 0.369 (40%) | 1.387 (100%) | 1.350 (100%) |
| state defaults | 0.081 (30%) | 0.325 (95%) | 0.323 (95%) |
| treaties signed | 1.650 (100%) | 6.320 (100%) | 6.178 (100%) |
| techniques invented | 1.387 (100%) | 0.677 (100%) | 0.677 (100%) |
| techniques adopted (events) | 2.519 (100%) | 3.305 (100%) | 3.208 (100%) |

What differs, beyond what more regions and civs give anyway:

* **Merchants and artifacts.** 4.8 great persons per civ-century on
  procedural worlds (templates 1.8), most of them aggregate merchants;
  1.8 times the agendas and 3.8 times the trading houses. See problem 1.
* **Wars.** Wars declared per civ are 4-5 times the template rate, and
  about half of them follow a call to arms or a federation's defence
  (`call_to_arms` 20 times, `federation_defense` 16 times the template
  rate per civ); in seed 42 the first ten wars include allies three to
  five regions from the enemy they join. Treasury follows: loans 3 times, loan principal 6-8 times, fiscal
  crises 3.8 times and defaults 4 times the template rate per civ. See
  open item 1.
* **Sea and steppe.** Sea trade in every procedural world (templates: 30%
  of worlds, at a tenth of the volume per civ), naval battles in 95%
  (templates none in the subset), colonies in 85-90%; hordes form in a
  quarter to a third of procedural worlds (templates: none in these
  batches; 5 of 200 in the template full gate). These systems are
  measured mainly by the procedural profile.
* **Famine.** Fewer and shorter famines: 25% of observed region-turns in
  famine (templates 28%), episodes of 5.0 turns on average (templates 8.1),
  1.5% of them 20 turns or longer (templates 10.6%). Procedural regions are
  thinner (14-16 agents a region against 26) and trade food further.
* **Epidemics.** About twice the epidemic events per civ and 1.6 times the
  deaths per head (0.71 against 0.45 per person per century); "virgin
  soil" arrivals recur as pathogens reach distant regions. Population
  still grows (final over start 1.15 against 0.92).
* **Techniques.** Half the inventions per civ (0.68 against 1.39 per
  century) and a third more adoptions (3.3 against 2.5): in a ten-civ
  world a technique invented once spreads, so fewer civs invent it. Not a
  problem.
* **Needs.** Spiritual need below its threshold in 26% of agent samples
  (templates 14%; three 500-turn worlds each): more faiths and more agents
  under a foreign faith. Material deficits are rarer (4% against 11%).
  Civ economy and culture stats average about 60% of the template's
  (28 and 23 against 49 and 44 in the same worlds).
* **Restorations.** Exiles are restored 4-5 times as often per civ: a
  deposed ruler almost always finds a friendly court in a ten-civ world,
  and in low-stability realms pretenders depose each other within turns
  (seed 43: three restorations in Suyerai in turns 60-70). See open item 3.

### Histories read

Seeds 42-44 of the full batch and 43 of the subset, read as event digests
(population, the four largest realms and the important events every 50
turns):

* Seed 42: ten realms, all alive at turn 300; population 537 -> 743 by
  turn 50, 635-808 later. Ten wars in the first 13 turns, mostly allies
  joining (Lisolenen League against Khorain Kingdom five regions away),
  then none until turn 242, when one call to arms puts Nithys at war with
  five realms at once. A pox and later the plague cross the map as
  "never known" outbreaks every few turns; famines hit the same thin
  regions (Saniwen Greenwood, Thukuheim Highlands) every decade.
* Seed 43: Jujojaki Clans conquered at turn 13; Suyerai's pretenders
  restore each other three times in ten turns; 31 wars in turns 150-199
  around one naval coalition, with 51 naval battles.
* Seed 44: 14 fiscal crises and 6 defaults in the first 100 turns, 16 and
  4 in the next; a realm of 7 regions holds 43 people.
* Template seeds 42-44 of the subset for contrast: three or four realms;
  one to four wars, all in the first 50 turns and none after; famines in
  the same few regions; seed 42 also has 15 fiscal crises in its first 100
  turns, so fiscal stress is not new, only more common.

## Problems and fixes

### 1. Merchant great persons flooded procedural worlds (fixed)

The aggregate merchant needs 10 consecutive "high trade route" turns
(`traditions.update_event_counts`), then a 20-turn cooldown. With the
contact ledger (on by default) a high trade route turn is a turn with at
least `MERCHANT_HUB_PARTNERS = 3` living partners trading at least 1.0.
That number was set on the four-civ template world, where three partners
are every other civ. In a ten-civ world three of nine is ordinary:

| Hub probe (seeds 42-44, 300 turns) | template | procedural |
| --- | ---: | ---: |
| living civ-turns with 3+ partners | 2.2% (6 seeds: 7.8%) | 84% (6 seeds: 74%) |
| mean live partners | 1.1 | 4.6 |
| aggregate merchants per world | 3-7 | 100-163 |
| artifacts per starting civ per 100 turns | 1.75-2.42 | 5.0-7.5 |
| artwork share of artifacts | 10-24% | 50-60% |

Every merchant brings an artwork (`artifacts._GP_ROLE_TO_ARTIFACT`), an
agenda and often a trading house, so artworks became half of all
artifacts and the artifact oracle failed.

**Fix** (`contact_ledger.merchant_hub_partners`, commit `937b3c5`): a hub
trades with every other living civ, and with at least three. With four
living civs or fewer nothing changes. Probed thresholds (share of the
other living civs a hub needs; hub share of procedural civ-turns,
aggregate merchants per world, artifacts per starting civ per 100 turns):

| Threshold | hub civ-turns | merchants / world | artifacts | artwork |
| --- | ---: | ---: | ---: | ---: |
| 3 (`main`) | 75-84% | 100-163 | 5.0-7.5 | 50-60% |
| three quarters, at least 3 | 23% | 6-80 | 1.5-5.2 | 7-44% |
| all others, at least 3 (chosen) | 3.5-9.9% | 6-39 | 1.5-3.7 | 7-31% |

Three quarters would have left worlds of five living civs unchanged, but
leaves procedural worlds at three times the template's merchant rate
and at the top of the artifact band; "every other living civ" is the
template rule's own meaning and puts the procedural hub share where the
template's is. Template worlds change only while five or more civs live
(the 200-seed template full gate ends with five or six in 3 worlds). The
snapshot-pruning test world (10 regions, 5 civs, agents off) changes and
was re-pinned (commit `7fae9d5`). The legacy rule with the ledger off
(4 relationships that ever traded) is unchanged.

Before and after on `aa0f655` (tree `541b51d` against `937b3c5`, the same
extension):

| | procedural full, aa0f655 | procedural full, fix | procedural subset, aa0f655 | procedural subset, fix |
| --- | --- | --- | --- | --- |
| gate | FAIL: artifacts | PASS | PASS | PASS |
| strict regression | strict | strict | strict | strict |
| community: seeds with a community | 100 of 100 | 100 of 100 | 20 of 20 | 20 of 20 |
| needs: seeds with net concordance > 0 | 88 of 100 (need 60) | 85 of 100 (need 60) | 16 of 20 (need 12) | 18 of 20 (need 12) |
| needs: pooled lower bound | +0.134 | +0.141 | +0.067 | +0.134 |
| needs: binding lower bound | +0.125 | +0.139 | -0.042 | +0.076 |
| cohort: seeds in the expected direction | 100 of 100 | 100 of 100 | 20 of 20 | 20 of 20 |
| era: seeds with inflections / silent collapses | 100 / 0 | 100 / 0 | 20 / 0 | 20 / 0 |
| arcs: families / dominance | 6 / none | 6 / none | 6 / cinderella 0.44 | 6 / cinderella 0.46 |
| artifacts: status | PARTIAL | PASS | PARTIAL | PASS |
| artifacts per starting civ per 100 turns (1-3) | 5.38 | 2.01 | 5.93 | 2.74 |
| artifacts: largest type share ok / loss rate | False / 2.6% | True / 4.0% | True / 2.9% | True / 3.5% |
| satisfaction mean / latest | 0.561 / 0.564 | 0.565 / 0.568 | 0.568 / 0.578 | 0.572 / 0.583 |
| migration per agent-turn (0.05-0.15) | 0.0748 | 0.0750 | 0.0751 | 0.0762 |
| rebellion per agent-turn (0.02-0.08) | 0.0353 | 0.0382 | 0.0362 | 0.0351 |
| gini in range | 0.900 | 0.917 | 0.842 | 0.886 |
| all starting civs survive (max 0.20) | 0.110 | 0.110 | 0.150 | 0.100 |
| extinct worlds | 0 | 0 | 0 | 0 |
| final population min / median / max | 254 / 536 / 934 | 230 / 502 / 912 | 338 / 585 / 815 | 415 / 604 / 754 |

Comparator: NO REGRESSION for the procedural full and subset, and for the
template subset, whose reports and seeds 42-44 bundles are identical
(only `generated_at` differs). Per starting civ per 100 turns on the
procedural full batch: great persons 4.54 -> 0.94, artifacts 5.38 ->
2.01, trading houses 0.98 -> 0.29, agendas declared 8.3 -> 3.4; wars,
calls to arms, population and civ survival unchanged within noise
(fiscal crises 1.21 -> 1.36: fewer merchant houses lend to their crowns).
Great persons per civ are now below the template's (0.94 against 1.76 on
the subset): the aggregate merchant is now as rare as on templates, and
agent-born great persons stop at the registry cap (open item 4).

### 2. The artifact oracle counted 4 civs (fixed in the gate)

See "Oracles on procedural worlds": the creation band is now per starting
civ. Template reports are byte-identical.

## Open items

1. **Calls to arms across the map.** Allies join wars against enemies
   three to five regions away (half of procedural war declarations), and
   at war a state borrows to keep its full reserve
   (`finance.WAR_CHEST_SHARE`), so these wars cost treasuries without
   fighting: fiscal crises 3.8 times and defaults 4 times the template
   rate per civ, and civ economy and culture stats about 60% of the
   template's. An ally that cannot reach the enemy (no border, no sea
   lane, no army in range) could decline, or join without the war-chest
   borrowing; that is a diplomacy design change, not a calibration.
2. **Accuracy bonuses reach every civ.** A dominant merchant or cultural
   faction and an active merchant great person add intelligence accuracy
   toward every civ in the world (`intelligence.compute_accuracy`), so a
   civ "knows" realms it has never met and can choose them as war
   targets. Harmless on four nearby template civs; on procedural worlds
   it widens the set of reachable enemies. The bonus could apply only on
   top of real contact.
3. **Pretender restorations.** `succession.create_exiled_leader` places a
   deposed ruler with the friendliest non-hostile civ; a ten-civ world
   nearly always has one, so every deposition creates a pretender, whose
   drain keeps stability under 20, where restoration rolls 5-8% a turn.
   Restorations run 4-5 times the template rate per civ.
4. **Named-character registry** (both world types). The native registry
   keeps the dead and closes promotions at 50 named characters per world
   (`named_characters.rs` `GLOBAL_CAP`), reached within the first 50
   turns on template and procedural worlds alike (43-54 agent-born great
   persons by turn 50, 0-12 in the 450 turns after, in six 500-turn
   probe worlds). With ten civs that is five per civ, with four twelve.
5. **Epidemic intensity.** Deaths per head 1.6 times the template rate;
   population still grows. Worth a look with the epidemiology owner.
6. **Spiritual need.** 26% of procedural agent samples below the threshold
   (templates 14%); satisfaction 0.56-0.57 against 0.61-0.62. Inside the
   regression band; a calibration question for the needs owner.

## Gates

TABLE-GATES-FINAL

## Tests

TESTS-PLACEHOLDER
