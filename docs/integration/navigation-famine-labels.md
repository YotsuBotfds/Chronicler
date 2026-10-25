# Navigation, famine labels and migration drivers (2026-10)

Branch `fix/navigation-famine-labels` from `feat/defaults-wave8` at
`7f055d6` (Wave 8 defaults: maritime, great-person agendas and nomads on;
[defaults-wave8.md](defaults-wave8.md)), no rebase. Three items, one commit
each:

| Item | Commit | Kind |
| --- | --- | --- |
| 1. Maritime navigation reads the known navigation techniques | `47bd9d9` | behavior change (maritime, where techniques are on) |
| 2. Food-crisis reports labelled famine or dearth | `3ffa444` | labels only; mechanics unchanged |
| 3. Migration drivers on agent migration events and `mass_migration` | `9930dbc` | labels only (one new native event column) |

Every run below is Linux, Python 3.13, `PYTHONHASHSEED=0`, with a native
extension built fresh (`maturin develop --release --locked`) and its
compiled `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
verified. Items 1 and 2 use the base Rust (SHA-256 `3d47d60f…b91a51`, as
Wave 8); item 3 changes Rust (`c8c3dd02…41e07d`). Template worlds are the
default 8 regions and 4 civs; procedural ones are named by regions x civs.

## 1. Maritime navigation

`maritime.navigation_level` returned 0 for every civ:
`chronicler.techniques` had no `technique_level`, and maritime fell back to
neutral. Techniques record, per civ, the techniques it knows
(`TechniqueState.known`, taken up at 0.10 practice in any region, lost
below 0.03 everywhere) and per region its practice.

Change: `techniques.technique_level(world, civ, domain)`, a read-only
accessor, counts the techniques of a domain in the civ's saved known set (0
with techniques off, an unknown domain or civ). `navigation_level` reads it
for `"navigation"`: coastal sailing, celestial navigation, the compass and
ocean navigation, 0 to 4. Maritime is its only reader; techniques never
read maritime. The level enters where maritime already used it:

| Use | Per level |
| --- | --- |
| Fleet range (zone hops from home waters) | +1 (base 3) |
| Fleet quality | x(1 + 0.10) |
| Ship cap | +2 |
| Storm chance | x(1 - 0.15), floor 0.3 |

Known sets rather than practice: the level is a discrete count, and the
known set already carries the hysteresis that keeps a civ from forgetting
and relearning when people move. Tests: a civ that knows two navigation
techniques gets 2 (other domains do not count), one that knows none gets
0, the level reaches quality, range and storms, and the accessor changes
nothing it reads.

### Subset gates (20 seeds x 200 turns, hybrid, `--parallel 2`)

Against the Wave 8 subset reports (the same worlds with the base code;
[defaults-wave8.md](defaults-wave8.md), section 2), compared with
`chronicler.validation_compare`:

| Oracle | 42-61 Wave 8 | 42-61 navigation | 62-81 Wave 8 | 62-81 navigation |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS; - | PASS; NO REGRESSION | PASS; - | PASS; NO REGRESSION |
| needs (seeds; effect) | 13; 1.00 | 13; 1.00 | 14; 1.21 | 14; 1.21 |
| cohort (seeds; effect) | 20; 1.36 | 20; 1.38 | 20; 1.18 | 20; 1.27 |
| arcs (three types; families) | 14; 6 | 15; 6 | 11; 5 | 12; 5 |
| artifacts | PASS 2.45, 3.3% | PASS 2.44, 3.3% | PARTIAL 3.05, 1.4% | PARTIAL 3.11, 1.8% |
| satisfaction mean; latest | 0.595; 0.615 | 0.596; 0.616 | 0.611; 0.620 | 0.611; 0.618 |
| migration per agent-turn | 0.0599 | 0.0597 | 0.0549 | 0.0550 |
| rebellion per agent-turn | 0.0350 | 0.0350 | 0.0130 | 0.0130 |
| regression (status) | PASS (strict) | PASS (strict) | FAIL (rebellion, survival) | FAIL (rebellion, survival) |
| final population min / median / max | 86 / 192.5 / 272 | 86 / 192.5 / 263 | 143 / 193.5 / 260 | 159 / 200.5 / 260 |
| extinct | 0 | 0 | 0 | 0 |

The 62-81 regression FAIL is the low-rebellion set's floor and the
founders' survival, both informational in the subset and the same in both
arms. Only 2 of 20 histories (seeds 44, 57) and 4 of 20 (64, 67, 69, 73)
change: template worlds have few seas (7 and 12 worlds), and the level
matters only once a civ has fleets. At turn 200, 45 of 57 living civs in
42-61 know one navigation technique (coastal sailing) and 2 know two; in
62-81, 42, 5 and 1 know one, two and three of 62.

What moves, per run (same worlds):

| Per run | 42-61 Wave 8 | 42-61 navigation | 62-81 Wave 8 | 62-81 navigation |
| --- | ---: | ---: | ---: | ---: |
| fleets commissioned | 0.60 | 0.60 | 0.80 | 0.75 |
| ships built | 2.00 | 2.00 | 5.40 | 5.20 |
| ships lost to storms | 0.50 | 0.35 | 0.75 | 0.50 |
| naval battles | 0.00 | 0.00 | 0.75 | 0.65 |
| blockades | 0.00 | 0.00 | 0.20 | 0.20 |
| overseas campaigns | 0.00 | 0.00 | 0.20 | 0.15 |
| sea cargo carried (units) | 156.8 | 160.3 | 64.7 | 64.8 |
| cargo lost to pirates | 0.25 | 0.20 | 0.35 | 0.35 |
| mass migrations | 75.35 | 74.50 | 66.15 | 66.85 |
| population | 192.25 | 191.75 | 197.80 | 200.15 |

Storm losses fall (the storm chance is 0.85x at level 1); sea trade,
battles and piracy move by a few percent on the few worlds with fleets;
migration and satisfaction stay within 0.0002 and 0.002.
Procedural worlds (48 x 10, seeds 7, 13, 29, 200 turns) show why the
effect is small this early: in two of the three no civ knows a navigation
technique at turn 200 and the runs are identical to the base; in seed 7
(seven civs at level 1) fleets 14 -> 20, ships 184 -> 207, naval battles
17 -> 15, sea cargo 519 -> 509. Over 500 turns (same worlds,
`scripts/maritime_report.py`), seed 13 stays identical, seed 29 moves by a
fleet or a battle, and seed 7 changes course: fleets 72 -> 52, ships 728 ->
660, naval battles 162 -> 111, blockades 59 -> 55, sea cargo 944 -> 1,337,
colonies 1 -> 0, polities alive at the end 10 -> 9. Means of the three:
fleets 91 -> 84, naval battles 169 -> 152, blockades 70 -> 69, cargo lost
to pirates 31.8 -> 32.1, sea cargo 2,294 -> 2,425. At turn 500 at most one
navigation technique is known (coastal sailing; 13 of 32 living civs).

## 2. What counts as famine

### Where famine is decided and what follows

| Where | Decision | Consequences |
| --- | --- | --- |
| `ecology._check_famine_yield` (agent modes) | any shortfall: economy food sufficiency below 1, once the region's 5-turn cooldown has run out | event, importance 8; stability -3 x severity (`signal`); cooldown 5; shadow mode only: population -5 and refugees |
| same, aggregate (`--agents off`) | a food slot's yield below 0.12 (subsistence 0.15 x climate where slots are empty) | the same, with population -5 x severity and refugees to foreign neighbours |
| `famine_cooldown > 0` (any report) | read by | epidemics: susceptibility +0.2, case fatality +0.25; technique growth halved; emergence stress +2 per region; rebellion and migration hazards +0.5 hardship; nomad raid hunger at least 0.5 |
| the report event | read by | traditions (`famines_survived`), factions (military and merchant -0.015, cultural +0.015), allied aid convoys (onsets), provenance cause rules, the era oracle's hunger group, chroniclers, the curator's causal links |
| provenance | `famine` chronic episode per region (gap 5); repeats kept as ticks | `famine_ended` after 5 turns without a report; the viewer's famine spans |
| Rust `tick.rs` | an agent in a region below 0.6 sufficiency gains a famine memory (-80, half-life 20), gated until the region reaches 1.0 | migration push up to 0.125 (`FAMINE_MIGRATE_BOOST` 0.2 x intensity) |
| Rust, continuous in sufficiency | | satisfaction penalty (1 - s) x 0.15; farmer target rises below 0.85; safety need restores only above 0.8; tithe scaled below 0.5; merchant food price 1 / s |
| Rust mortality | none | `demographics::mortality_rate` reads age, soil, water, crowding, war and endemic disease, not food |
| narration | agent memories as "a great famine"; event text "Famine strikes X, devastating Y" | |
| viewer | Food tab, Food map layer, region inspector | a region is "in famine" from a report until `famine_ended` |

### Measurements (base `7f055d6`, hybrid)

Read-only probes (kept outside the repository) record the famine check's
input, its reports, the timeline and the native agent events. Region-turns
are controlled and populated; spans are the viewer's.

| | Template, seeds 42-51, 200 turns | Procedural 64 x 16, seeds 7-9, 300 turns |
| --- | --- | --- |
| region-turns | 11,569 | 32,739 |
| fed / short / below 0.6 / below 0.2 | 51.0% / 49.0% / 32.7% / 11.1% | 45.1% / 54.9% / 38.2% / 17.8% |
| short in winter | 59.2% | 65.7% |
| reports per run | 140.4 | 1,596.7 |
| sufficiency at the report: below 0.2 / 0.2-0.4 / 0.4-0.6 / 0.6-0.8 / 0.8-1.0 | 21.1 / 23.0 / 15.3 / 18.2 / 22.4% | 35.3 / 16.2 / 14.6 / 16.6 / 17.2% |
| report on the first short turn / after 13+ short turns | 37.5% / 28.4% | 45.9% / 22.3% |
| controlled regions inside a famine span, per turn: mean; worst turn (mean over runs) | 44.2%; 80.8% | 45.5%; 75.1% |
| inside spans: fed / 0.6-1.0 / below 0.6 | 15.9 / 28.0 / 56.2% | 14.0 / 26.2 / 59.9% |
| shortage spells (consecutive short turns): median, p75, p90 length | 3, 7, 27 turns | 2, 4, 13 turns |
| spells never below 0.6 / below 0.6 for 1-2 turns / for 3+ running | 25.9 / 46.6 / 27.5% | 18.9 / 52.7 / 28.4% |
| deaths per 1,000 agent-turns, fed | 14.4 | 16.1 |
| deaths, 0.8-1.0 / 0.6-0.8 / 0.4-0.6 / 0.2-0.4 / below 0.2 | 16.4 / 17.6 / 19.2 / 21.4 / 23.3 | 18.8 / 22.2 / 21.9 / 22.7 / 23.6 |
| migration per agent-turn; famine-memory share of migration units | 0.0591; 24.8% | 0.0631; 25.1% |

(A turn is a month; a season is three turns.) A report fires on the first
short turn after the cooldown, so a region short for a few months in most
years reports every five turns and stays inside one span: the viewer then
shows nearly half the realm in famine, a sixth of it fed at that turn.

Deaths are up to 60% higher where food is short, but no agent dies of
hunger: mortality has no food term (`demographics::mortality_rate`). The
excess goes with what shortage shares or sets: soil, water and crowding
stress, and the epidemic susceptibility and fatality that every report's
cooldown raises (not decomposed here).

### Definitions and the rule

Historically, famine is a sustained, severe shortage that kills people
beyond the usual death rate (Ó Gráda, *Famine: A Short History*, 2009:
"a shortage of food or purchasing power that leads directly to excess
mortality from starvation or hunger-induced diseases"; the IPC's phase 5
needs extreme food gaps and raised crude death rates). Dearth is the
early-modern word for a bad season: food short and dear, hardship and
unrest, usually without a mortality crisis (Walter and Schofield, *Famine,
Disease and the Social Order in Early Modern Society*, 1989). A lean
winter is dearth; famine is what follows when it deepens and lasts.

The famine check keeps its trigger, effects and cooldown. Its report is
labelled by severity and duration:

* **famine** when sufficiency has stayed below 0.6
  (`FAMINE_SEVERE_SUFFICIENCY`, the agents' famine-memory threshold) for at
  least 3 consecutive turns (`FAMINE_SEVERE_TURNS`, a season) up to the
  report;
* **dearth** otherwise ("Dearth in X: food runs short and dear for Y",
  importance 4).

`Region.food_severe_turns` counts the run of severe turns in agent modes
(saved, so a resumed run labels as an uninterrupted one; omitted while
None, so worlds without a severe shortage and every `--agents off` world
keep their bytes). A region not measured, empty or ruled by nobody resets.
Aggregate famine (yields below 0.12, with population loss) keeps its label.

Applied to the base runs (the rule reads only the base's own sufficiency
and reports, so these are exact for its mechanics):

| | Template | Procedural |
| --- | --- | --- |
| reports labelled famine | 36.2% | 28.1% |
| region-turns inside famine spans (was 44.2%, 46.7%) | 16.1% | 13.1% |
| inside famine spans: below 0.6 / fed | 89% / 4% | 86% / 5% |
| deaths per 1,000 agent-turns: famine spans / dearth spans / neither | 21.7 / 17.2 / 14.4 | 22.2 / 21.0 / 15.5 |

Labelled runs reproduce them (template: the same 140.4 reports, 36.2%
famine; regions in famine per turn 15.8% on average, worst turn 59.6%;
procedural on the branch, which includes item 1: 12.1% and 43.6%).
Variants measured on the same data: 0.6 for one turn labels 59-66% of
reports famine with 26-31% of region-turns in famine spans; 0.4 for three
turns 18-26% and 8-12%. The chosen rule reuses an existing threshold and
the season.

### What changed and what did not

Labels:

* the report's type and text (above); agent famine memories are narrated as
  "hunger under the X" (they are written after one month below 0.6);
* provenance: dearth and famine reports of a region share one episode
  (`EPISODE_FAMILY`), so onsets and ticks fall where they fell; an episode
  that reached famine ends as `famine_ended`, one that did not as
  `dearth_ended`; a dearth has the famine cause rule;
* allied aid convoys go to "famine-struck" or "hungry" allies;
* chroniclers keep recording famine (importance 8); a dearth (4) falls
  under their thresholds;
* viewer: the Food tab, the Food map layer and the region inspector show
  famine (orange) and dearth (pale amber) separately. A span runs from a
  report to the next report with the other label or to the episode's end.
  Bundles written before the labels have only famine reports and read as
  before (`foodCrisisSpans` reduces to the old spans; tested).

Unchanged: every report's effects and cooldown, so every consumer of
`famine_cooldown`; traditions, factions, aid convoys, the era oracle's
hunger group and the chroniclers' disaster set read both labels
(`FOOD_CRISIS_EVENT_TYPES`). Identity against item 1 (`47bd9d9`):

| Comparison | Result |
| --- | --- |
| `--agents off`: template seeds 42 and 7, 150 turns; procedural 48 x 10 seed 7, 100 turns | 33 files, 0 differences (byte-identical) |
| hybrid: template seeds 42 and 7, 120 turns; procedural seed 7, 100 turns | `agent_events.arrow` byte-identical; `state.json` and the bundle timeline identical once the labels are undone (dearth -> famine, food-crisis text, importance and ids renumbered); bundle history identical. Only memories (narration) and the chroniclers' sidecar differ |

Golden fixtures are unchanged: their workloads run `--agents off` with
maritime pinned off (`scripts/benchmark_headless.run`), so none of the
three items reaches them.

### Mechanics: not changed

Nothing in the evidence shows a mechanic is wrong, as opposed to
mislabelled:

* a dearth raising unrest, epidemic risk and migration is historically
  grounded (food riots, hunger-weakened bodies, people leaving);
* the agents' famine memory (below 0.6, once per shortage spell) drives a
  quarter of migration units. Raising its threshold or asking for duration
  would lower migration (0.0576 on the Wave 8 full gate against the strict
  0.05 floor; famine memory is the largest single driver), and no measure
  here says the memory is wrong rather than broad. It is left; changing it
  needs the 20 x 500 migration probe of
  [healthy-migration.md](healthy-migration.md).

Open items:

* **Hunger kills no one in agent modes.** Mortality has no food term; a
  famine's excess deaths come only through ecological stress and
  epidemics. A starvation term would be a population mechanic with its own
  gate (and would move the needs, cohort and migration oracles).
* **The cooldown effects do not scale with severity.** Dearth and famine
  carry the same stability drain, epidemic susceptibility, technique
  slow-down, stress and hazard hardship. Scaling them would change
  mechanics; measure first.
* Shadow mode drains 5 population on every report, dearth included
  (unchanged; shadow is a diagnostic mode).
* A famine is declared at the first report after its third severe turn,
  so a region entering a severe shortage reads dearth for up to five turns.

## 3. Migration drivers

`mass_migration` (8 or more agents leaving a region in one tick) always
read "N farmers fled X for Y". The native decision already found each
migration's largest utility term for the migration budget
(`migration_drivers::dominant_term`) and attributed household followers to
their lead.

Change (native): `AgentEvent.migration_driver`, the decision's largest term
(index into `MIGRATION_TERM_NAMES`); spouses and dependants that household
consolidation moves carry their lead's (`PendingDecisions.migration_followers`,
read by `migration_driver_of`); `MIGRATION_TERMS` when no term was
positive; 255 on every other event. The events batch gains a `migration_driver` column. No
decision reads it and no random draw is added.

Python: `AgentEventRecord.migration_driver` (255 when an extension or file
lacks the column); `agent_events.arrow` writes it. `mass_migration` carries
`driver`, the label most of its moves carry (ties: the lower term), and its
text reads it:

| Driver | Text |
| --- | --- |
| frontier | N farmers left X to settle Y |
| wage | ... left X for work in Y |
| chain | ... followed kin from X to Y |
| urban (the cities' pull, `--cities`; merged from `main`) | ... left X for the city in Y |
| famine_memory, opp_food | ... fled hunger in X for Y |
| persecution, persecution_memory | ... fled persecution in X for Y |
| battle_memory, conquest_memory | ... fled war in X for Y |
| low_satisfaction, safety, material and spiritual needs | ... left hardship in X for Y |
| opp_satisfaction, opp_capacity, opp_river, opp_news | ... left X for better prospects in Y |
| none recorded | ... fled X for Y (as before) |

`notable_migration` (a named character moving) carries its agent's
driver. Moves driven by settling, work, kin or a city cite no distress as causes
(provenance) and are not a calamity to the chroniclers; the episode label
"exodus" is now "wave of departures". The viewer's Migration layer names
the drivers of the window's mass departures (older bundles: no driver,
shown as before). `Event.driver` is omitted while None, so other events
and older bundles keep their bytes.

Identity against item 2 (`3ffa444` with the base extension): `--agents
off`, template seeds 42 and 7, 150 turns: 18 files, 0 differences; hybrid,
template seeds 42 and 7 (120 turns) and procedural 48 x 10 seed 7 (100
turns): every agent-event column identical (the new one added), state and
bundle timeline identical once the migration events' text, causes and
driver are dropped, bundle history identical.

Mass migrations by driver (hybrid, template seeds 42 and 7, 120 turns):
famine memory 57, opp_capacity 16, opp_food 12, wage 8, frontier 5,
opp_satisfaction 2, persecution and its memory 4, low satisfaction 1 (105). Procedural 48
x 10 seed 7, 100 turns: famine memory 41, opp_food 11, low satisfaction
10, frontier 9, wage 5, other 15 (91). 13 of 105 and 14 of 91 mass
migrations were settling or seeking work and used to read as flight.

## Merge with `main`

Before the push `origin/main` had moved to `cee5013` (PR #27, Wave 8, same
tree as the base, and PR #28, cities, default off). The merge (no rebase)
resolves the ledger and the oracle lane's `systems-1` chunk (both new test
files and `tests/test_cities.py`) and adapts two things: the cities' urban
pull is migration term 17 (`MIGRATION_TERMS` 18), so `urban` joins
`MIGRATION_DRIVER_NAMES` and the voluntary drivers; and cities record a
famine report (onset or a dearth deepening into famine, at most one per 30
turns) as a city's misfortune, not a dearth, and name a fall's crisis by its
label. Cities stay default off, so the gates above stand for the merged
tree; the merged head's tests are in the ledger.

## Bundle size

The bundle-size guard world (`tests/test_bundle.py::TestBundleSize`: seed
1, 500 turns, 10 regions, 5 civs, agents off, every default) has a sea:
navigation changes its history (13 polities over the run instead of 14).
Labels and drivers do not reach it (agents off).

| Guard world | Wave 8 | This branch |
| --- | ---: | ---: |
| native | 20.35 MB (21,337,377 bytes) | 18.66 MB (19,566,373 bytes) |
| no-Rust | 19.72 MB (20,677,190 bytes) | 19.80 MB (20,762,835 bytes) |

(MB is 2^20 bytes, as the test computes it.) The 24 MB limit stays.

## Full gate

Full profile (seeds 42-241, 500 turns, hybrid, `--parallel 2`) on
`9930dbc` (all three items, default switches) against the Wave 8 full
report ([defaults-wave8.md](defaults-wave8.md), section 3): **PASS
strict, NO REGRESSION**. 3,041 s on the shared host. Seed directories were
deleted once the reports and a per-seed extract were kept.

| Oracle | Wave 8 | This branch |
| --- | --- | --- |
| gate; comparator | PASS; NO REGRESSION | PASS; NO REGRESSION |
| community (seeds) | 200 | 200 |
| needs (seeds; median effect) | 194; 1.41 | 196; 1.41 |
| cohort (seeds; median effect) | 200; 1.62 | 200; 1.63 |
| era (seeds with inflections; silent collapses) | 200; 0 | 200; 0 |
| arcs (seeds with three types; families) | 167; 6 | 168; 6 |
| artifacts (status; creation; loss) | PASS; 1.49; 4.4% | PASS; 1.49; 4.5% |
| regression (status) | PASS (strict) | PASS (strict) |
| satisfaction mean; latest (ceiling 0.65) | 0.607; 0.619 | 0.607; 0.620 |
| migration per agent-turn (strict floor 0.05) | 0.0576 | 0.0576 |
| rebellion per agent-turn (0.02-0.08) | 0.0317 | 0.0314 |
| all founders surviving (limit 0.20) | 0.110 | 0.110 |
| extinct worlds | 0 | 0 |
| final population min / median / max | 60 / 200 / 340 | 60 / 199.5 / 342 |

Only navigation changes histories: 55 of the 200 differ, all among the 86
with a sea (food-crisis labels counted as one type). At turn 500 the 552
living civs know 0, 1, 2, 3 and 4 navigation techniques: 124, 305, 82, 40
and 1.

| Per run (200 worlds) | Wave 8 | This branch |
| --- | ---: | ---: |
| fleets commissioned | 0.94 | 0.90 |
| ships built | 8.78 | 7.99 |
| ships lost to storms | 2.42 | 2.02 |
| naval battles | 1.16 | 0.90 |
| blockades | 0.24 | 0.24 |
| overseas campaigns | 0.24 | 0.20 |
| sea cargo carried (units) | 203.5 | 210.2 |
| cargo lost to pirates | 0.75 | 0.67 |
| wars declared | 4.92 | 4.78 |
| agent migrations | 5,748.5 | 5,747.3 |
| agent rebellions | 3,162.1 | 3,133.0 |
| population | 200.25 | 199.41 |
| food-crisis reports (famine / dearth) | 348.5 (all famine) | 348.7 (140.3 / 208.4) |
| mass migrations | 185.0 | 184.8 |

40.2% of the branch's reports are famine. Of its 36,958 mass migrations
the dominant driver is famine memory 44.6%, wage 12.3%, opp_food 10.3%,
persecution memory 10.1%, frontier 8.6%, opp_capacity 6.5%, live
persecution 5.3%, other 2.3%: one in five (21.0%) is settling or seeking
work and used to read as flight.

## Verification

On `9930dbc` with the item-3 extension (`c8c3dd02…41e07d`), shared 4-core
host (`-n 2`):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 928 passed, 2 ignored |
| `pytest -m "not slow" -n 2` | 6,000 passed, 3 skipped, 526 subtests (Wave 8: 5,967) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped (`TestBundleSize` at 18.66 MB) |
| No-Rust lane (virtualenv without `chronicler_agents`, every test) | 5,792 passed, 211 skipped |
| `scripts/run_python_oracle_checks.py` | PASS in 77.3 s: 1,983 passed, 13 skipped, 2 deselected in four chunks; largest chunk 27.2 s of 110 s; guard PASS, no native module loaded |
| Viewer `npm test`, `npm run lint`, `npm run build` | 267 tests passed; lint clean; build passed (the existing large-chunk warning) |
| Golden fixtures | unchanged |

After the merge with `main` (`2bd2c53`, extension `6df1c3e1…19c33f0`,
cities' Rust included):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 934 passed, 2 ignored |
| `pytest -m "not slow" -n 2` | 6,036 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane | 5,825 passed, 214 skipped |
| `scripts/run_python_oracle_checks.py` | PASS in 83.8 s: 2,015 passed, 16 skipped in four chunks; largest chunk 30.3 s of 110 s |
| Viewer tests, lint, build | 267 tests passed; lint clean; build passed |
| Bundle-size guard world | 18.66 MB native, 19.80 MB no-Rust (the same bytes as `9930dbc`) |

New tests: `tests/test_food_crisis_labels.py` (14) and
`tests/test_migration_driver_labels.py` (16, one native) in the oracle
lane's `systems-1` chunk; three navigation tests in `test_maritime.py` and
one in `test_techniques.py`; the Rust household test for followers'
labels; viewer tests for labelled spans, the Food panel and map layer, and
mass-departure drivers.

## Open items

* Famine: hunger kills no one in agent modes; the cooldown effects do not
  scale with severity; shadow mode drains population on a dearth; a famine
  is declared up to five turns late (section 2).
* The agents' famine-memory threshold is unchanged; any change needs the
  migration probe (migration margin 0.0076 on the Wave 8 full gate).
* Navigation: template worlds have few seas and fleets, so the subset and
  full gates read little of it; the procedural maritime report
  (`scripts/maritime_report.py`) over 500 turns would show more.
* Migration drivers reach `mass_migration` and `notable_migration` only;
  the viewer-only `history[n].migration` field still counts moves by region
  pair without their drivers.
