# Narration coverage (2026-10)

Branch `feat/narration-coverage` from `main` `11238d5` (PR #39), merged
without rebase with `main` `aa0f655` (PR #40, guilds on by default). Code:
`src/chronicler/narration_context.py` (new: event lines, prompt event
selection, standing state, timeline lookups), `narrative.py` (prompt
builder, mechanical chronicle, agent context), `curator.py` (narrative
weights, cluster score, diversity); viewer `FoodPanel.tsx`,
`RegionSystemsDetail.tsx`, `lib/food.ts`, `lib/mapLayers.ts`,
`MovementsPanel.tsx`, `lib/movements.ts`, `lib/cities.ts`,
`AppShell.tsx`; scripts `narration_prompts.py` (capture and measure
prompts), `narration_coverage.py` (the table below),
`narration_identity.py` (everything but the narration is equal).

Narration only: the simulation, its saved state, sidecars, snapshots,
timeline, agent events and validation sidecars are byte-identical
([Identity](#identity)). The narrator still describes only what a run
recorded; every new line is read from the record.

Follow-ups on `fix/movements-narration-polish` (movement news per founding,
guild chronicles, temporal spread of the chronicle):
[Follow-ups](#follow-ups-news-guild-chronicles-spread).

## Result

Three hybrid runs with every default system on, `--narrator mechanical`
(no LLM; the engine builds each prompt before rendering it), 50 moments
each, on the merged source (guilds on). Before: `main` `aa0f655`. After:
this branch. Tokens are estimated at four characters each.

| | template 42, 500 turns | procedural 48 x 10, seed 7, 400 turns | template 1234, 300 turns |
| --- | ---: | ---: | ---: |
| events in the timeline | 5,925 | 26,275 | 4,307 |
| prompt mean, characters (tokens) | 22,022 -> 10,679 (5,505 -> 2,669) | 101,495 -> 16,197 (25,373 -> 4,049) | 23,634 -> 10,595 (5,908 -> 2,648) |
| prompt max, tokens | 12,204 -> 4,912 | 38,483 -> 6,169 | 15,313 -> 5,846 |
| all 50 prompts, tokens | 275,279 -> 133,482 | 1,268,692 -> 202,455 | 295,420 -> 132,442 |
| event lines in all prompts | 3,800 -> 983 | 20,292 -> 2,291 | 4,307 -> 897 |
| turning points (importance 8+) listed | 97 -> 103 of 107 | 306 -> 287 of 350 | 108 -> 108 of 108 |
| kinds with an importance 7+ event listed | 27 -> 28 of 29 | 41 -> 41 of 44 | 24 -> 23 of 24 |
| top 30 events by impact listed | 24 -> 24 | 22 -> 21 | 30 -> 29 |

Before, every event of a moment's six-turn window was listed (a procedural
moment held about 400 lines), so turning points were "listed" but buried
among routine actions, and the largest prompts exceeded common local
context windows. After, a prompt lists at most 12 lines (plus up to four
for turning points of kinds no line shows), folds repeats, and counts the
rest. Every turning point inside a selected moment is listed (287 of 287
in the procedural run); the procedural run's selected moments hold fewer
turning points (287 against 306) because the curator no longer prefers
windows crowded with famines (see [Curator](#curator)). "Impact" is
importance plus log2(1 + direct recorded consequences), one event per kind,
first actor and region (`scripts/narration_prompts.py report`).

Coverage of the 252 event types the simulation can emit (static scan of
`src/chronicler` plus computed and native emitters; 200 seen in the runs):

| | before | after |
| --- | ---: | ---: |
| readable, not misleading prompt line | 235 | 252 |
| empty line (no description, no label) | 14 | 0 |
| misleading description | 3 | 0 (reworded) |
| seen types listed in a prompt at least once | 194 of 200 | 143 of 200 |
| standing state read from snapshots | rulers only through events | rulers, wars, movements, reforms, cities, guilds, burghers, food |

The second-to-last row falls by design: routine actions and episode
bookkeeping (develop, trade, `*_ended`, quarantine, supply shocks) are
counted ("Also recorded in these turns (not listed): 41 develop, ..."), not
listed; 57 seen types now reach a prompt only in that count (routine and
bookkeeping kinds, and minor kinds that crowded moments leave out).

## 1. What the narrator receives

`NarrativeEngine._prepare_narration_prompts` builds one prompt per curated
moment (`curator.curate`, 50 by default). Paths: the in-run narration
(`--narrator api|gemini|mechanical`, live world and agent bridge) and
`--narrate BUNDLE` (rebuilt from the bundle's `world_state`). The per-turn
local narrator (`generate_chronicle`) uses the same event lines.

| block | before | after |
| --- | --- | --- |
| EVENTS | every event of the window, `[type] description (actors, importance)`; empty for hazard rolls and native politics triggers | at most 12 lines (+4 for unshown turning points), `[turn T] type: line (importance; driver; other actors; N more alike, turns, places)`, recorded order; "Also recorded ... (not listed)" counts the rest |
| landmarks | every named event whose actors match an event of the window | the five most important; named events matching no event join the moment covering their turn; placeholder ids cut ("Movement 3") |
| causes | recorded chains, then every recorded cause -> effect pair as type arrows (often 50-150 lines) | recorded chains (unchanged); type arrows only for events without provenance (old bundles), at most 6 |
| consequences | type arrows | LATER CONSEQUENCES: up to 4 recorded effects after the moment, most important first, as event lines |
| standing state | none | STANDING STATE after the moment's last turn, at most 10 lines |
| in-world accounts, names | from every event of the moment | from the listed events |
| agent context | every active named character of the world (10), all memories | the characters the events name, then active characters of the moment's civs (6), three strongest memories each |
| before / after, artifacts, register | unchanged | unchanged |

**Standing state** (`narration_context.standing_state_lines`), from the
snapshot after the moment's last turn (a snapshot of turn T holds the state
after turn T - 1), for the civs and regions of the moment's most important
events:

- rulers and capitals, vassal and federation (`CivSnapshot`);
- wars from the campaign record (aim, start turn, war score from the
  attacker's side), else the plain war pairs;
- living movements against those civs: creed, stage, members and share,
  leader (or "its leader X martyred in turn T" when a `movement_martyr`
  event records the death: a movement keeps its dead leader's name),
  stronghold;
- reforms in force (named as the record names them, guild charters
  included);
- chartered or great cities in their lands: rank, lord, charter, unrest;
- guilds of the moment's regions and cities: kind, masters, monopoly, say
  in dues, a charter won as a movement, raised dues; the burgher faction's
  share at court;
- regions short of food: food on hand over need and the dearth or famine
  the timeline records there since its report (famine severity was never
  in a prompt before).

In the final runs every prompt carries a standing state; movements appear
in 25 / 41 / 18 of 50 prompts (template 42 / procedural / template 1234),
reforms in 0 / 36 / 20, cities in 48 / 43 / 45, guilds in 48 / 46 / 48,
food in 44 / 24 / 42, wars in 9 / 21 / 2.

## 2. Gaps found in the generated prompts

- **Prompt size.** A procedural 400-turn run's prompts averaged 25,000
  tokens (max 38,500): beyond most local models' context. Template runs
  averaged 5,500.
- **Empty lines.** Hazard rolls (drought, plague, earthquake, rebellion,
  migration, border incident, discovery, religious movement, cultural
  renaissance) and native politics triggers (`proxy_detected`,
  `federation_formed`, `federation_collapsed`, and some `capital_loss`,
  `vassal_rebellion`) are recorded without a description; the prompt showed
  `- [drought]  (actors: X, importance: 5/10)`. The curator's labels were
  used only inside causal chains.
- **Misleading descriptions** (read as recorded, reworded in narration
  only): `move_capital` "relocated capital from X to X" (36 times in one
  run; the cost was paid, the seat did not move); a mass migration without
  a recorded driver "fled" (bundles before drivers); `brain_drain`
  "scholars fled" (scholar migrations); religion's `Mass Migration`
  "Religious minorities flee X" (recorded when the persecuted share passes
  a threshold; it counts no one leaving). Temples were named "faith 3".
- **Selection.** The chain bonus saturated (nearly every event of an
  epidemic, famine or supply shock sits on a long recorded chain and hit
  the cap of 12), so quarantines (importance 4) outscored a supervolcano
  (importance 10, no recorded sequel), which never reached a prompt in two
  of the three pre-guild runs. Minor named events (treaties, legacies, propaganda) fell in
  nearly every window and exempted it from the diversity penalty; the
  penalty's civs were every actor of the window and its dominant kind the
  most numerous (often `develop`). With a budget of 1-2 the civ check
  demoted the best moment for a civ seen once.
- **Standing state never seen**: a reform in force, a city's charter, a
  famine's severity and duration, a movement's creed, stage and leader
  (and whether the leader is dead), guilds and burghers, wars' aims.
  Migration drivers were in the descriptions but not named in the line.
- **Determinism.** Selection was deterministic in practice, but the
  diversity penalty counted civs through a set; it now uses ordered lists
  (identical prompts under `PYTHONHASHSEED` 0, 1 and 4242).
- **Not fixable in narration** (recorded in [Open](#open); the first is
  addressed in [Follow-ups](#follow-ups-news-guild-chronicles-spread)): movement news
  leaves no per-founding record (a run counter only), so a founding cannot
  be told as caused by news; the historiography layer writes its accounts
  during the run with `curator.event_label`, whose text is saved output
  and stays as it was.

## 3. Changes

### Event lines

`narration_context.event_text` (prompt lines, chains, consequences, the
mechanical chronicle, the per-turn prompt): the recorded description
without its full stop; a label for the types recorded without one
(`EVENT_LABELS`, 19 types); the four rewordings above; a temple named by its
faith. Lines name the migration driver in plain words ("driven by memory
of hunger") and actors the line does not already name.

### Prompt event selection

`select_prompt_events`: salience is importance, +3 for a step of the
moment's recorded chains, +2 for a named event, +1.5 for events of the civs
of the moment's two most important events, +2 / +1 for kinds seen at most 5
/ 20 times in the run, -log2(count / 40) (at most 2) for kinds seen more
than 40 times, -2 for routine kinds. Bookkeeping (`*_ended` closings except
`war_ended` and `tribute_ended`, episode repeats, capability unlocks) is
never listed. Events of one kind and first actor fold into one line; a kind
gets at most two lines, the rest fold into its best; routine kinds fill
only quiet moments (under four lines). Up to four extra lines go to turning
points of kinds no line shows.

### Curator

`apply_narrative_weights` after the base and chain scores: chain bonuses
weigh at 0.4; routine and bookkeeping kinds score their importance only;
turning points gain 1.5 per importance step from 8 (+4.5 at 10); kinds seen
3-5 times +1; kinds seen more than 12 times lose log2(count / 12), at most
3. A cluster scores its best member plus half the second and a quarter of
the third (was the sum of the top three), so one great event can carry a
moment. Diversity reads a moment's civs as the actors of its three most
important events and its kind as the one with most importance among
non-routine events; only landmarks (a named event of importance 7+) are
exempt; a civ or kind in one moment is never over-represented.
`faction_dominance_shift` (the burghers' rise) is no longer routine; the
guild kinds weigh by importance.

### Mechanical chronicle

The listed events as sentences, with folded places ("Famine strikes North,
devastating A (and in South)."), then the recorded chains, accounts and
names as before. It read as one block of every description joined by "; "
(with ".;" between sentences).

## 4. Before and after: one moment

Template 42, turns 78-83 (a commons movement's demand, refusal, rising and
the poor relief it wins), from the pre-guild runs. Before: 28,811
characters, 108 event lines (the rising the 80th), 153 type-arrow lines.
After: 10,356 characters, 12 lines listing 17 events.

Before:

```
EVENTS:
- [quarantine] Kethani Empire closes its borders against the marsh fever raging in Verdant Plains. (actors: Kethani Empire, importance: 4/10)
- [technique_adopted] Kethani Empire learned herbal lore from migrants out of Selurian Republic (actors: Kethani Empire, importance: 3/10)
- [develop] Ashkari Nomads invested in culture. (actors: Ashkari Nomads, importance: 3/10)
- [build_started] Kethani Empire begins building irrigation in Frostholm Tundra (actors: Kethani Empire, importance: 3/10)
- [trade] Thornwall Confederacy traded with Selurian Republic. (actors: Thornwall Confederacy, Selurian Republic, importance: 3/10)
...
- [earthquake]  (actors: Ashkari Nomads, importance: 5/10)
...
CAUSES leading to this moment:
- technique_invented→technique_adopted (turn 20) [recorded]
- move_capital→capital_relocation_ended (turn 30) [recorded]
...
```

After:

```
EVENTS:
- [turn 78] famine: Famine strikes Thornwood, devastating Thornwall Confederacy (importance 8)
- [turn 80] earthquake: An earthquake shakes Ashkari Nomads (importance 5)
- [turn 81] movement_demand: the Levellers of Amber Valley, 11 strong (30% of the people of Kethani Empire), demands relief from hunger and dues (importance 5)
- [turn 81] movement_refused: Kethani Empire refuses the Levellers of Amber Valley (importance 4)
- [turn 82] movement_rising: the Levellers of Amber Valley rises against Kethani Empire in Amber Valley (9 members) (importance 7)
- [turn 83] mass_migration: 10 farmers fled hunger in Verdant Plains for Ashara Desert (importance 5; driven by memory of hunger; 2 more alike, turns 81-83: Ashara Desert, Amber Valley)
- [turn 83] movement_concession: After the rising, Kethani Empire grants the Levellers of Amber Valley relief: remitted dues and grain from the stores (19 from the treasury); poor relief becomes law (importance 6)
Also recorded in these turns (not listed): 6 develop, 6 invest culture, 6 supply shock, 5 dearth, 5 trade, 4 epidemic, 4 infrastructure completed, 4 occupation shift ended, 51 others.
...
STANDING STATE after turn 83 (as recorded; describe it, do not change it):
- Rulers: Thornwall Confederacy: Chieftain Twilara (capital Verdant Plains, in The Grand Pact); ...; Kethani Empire: Chancellor Shoalwick (capital Iron Peaks, in The Grand Pact)
- Movement: the Levellers of Amber Valley (commons, satisfied) against Kethani Empire, 11 members (29% of its people), led by Warchief Gorgemeld, strongest in Amber Valley
- Reform in force: the poor relief in Kethani Empire since turn 83
- City: Thornwood Settlement 1 (town in Thornwood, lord Thornwall Confederacy), market rights, unrest 0.79
- Food in Amber Valley: food on hand covers 35% of need, dearth recorded since turn 77 (2 reports)
```

## 5. Coverage table

`scripts/narration_coverage.py table src/chronicler BEFORE AFTER` over the
three runs (before: `main` `aa0f655`; after: this branch). Columns: where
the type is emitted; occurrences; the prompt line before and after (ok,
empty, misleading; label, reworded); the curator class after; events listed
in a prompt before and after (before listed every event of a selected
window); in-world names (yes: most events carry a region, a civ actor or a
civ field, which `languages.NameIndex` resolves; actors: only character
actors; -: not seen); historiography (the category it is chronicled under;
`routine` and `bookkeeping` are never chronicled; `unclassified` only at
importance 7+). Narration does not change the historiography layer.

| type | emitted in | n | line before | line after | curator after | listed before | listed after | names | accounts |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- | --- |
| Mass Migration | religion.py | 227 | misleading | reworded | scored | 178 | 0 | yes | faith |
| Persecution | religion.py | 226 | ok | ok | scored | 178 | 0 | yes | faith |
| Reformation | religion.py | 19 | ok | ok | turning point | 18 | 16 | yes | faith |
| Schism | agent_movements.py | 37 | ok | ok | scored | 31 | 30 | yes | faith |
| action | action_engine.py | 12 | ok | ok | routine | 10 | 0 | yes | routine |
| agenda_declared | gp_agendas.py | 346 | ok | ok | routine | 245 | 0 | yes | unclassified (7+) |
| agenda_failed | gp_agendas.py | 132 | ok | ok | scored | 112 | 5 | yes | unclassified (7+) |
| agenda_fulfilled | gp_agendas.py | 208 | ok | ok | scored | 161 | 3 | yes | unclassified (7+) |
| aid_convoy | diplomacy.py | 1158 | ok | ok | routine | 898 | 0 | yes | routine |
| ambition_declared | governance_runtime.py | 297 | ok | ok | routine | 227 | 0 | yes | unclassified (7+) |
| ambition_failed | governance_runtime.py | 121 | ok | ok | scored | 100 | 19 | yes | disgrace |
| ambition_fulfilled | governance_runtime.py | 38 | ok | ok | scored | 28 | 12 | yes | glory |
| amphibious_landing | maritime.py | 9 | ok | ok | scored | 7 | 6 | yes | unclassified (7+) |
| annexation | war/occupation.py | 10 | ok | ok | scored | 2 | 8 | yes | two sided |
| army_destroyed | war/armies.py | 44 | ok | ok | scored | 32 | 16 | yes | one sided loss |
| army_disbanded | war/armies.py | 29 | ok | ok | routine | 15 | 0 | yes | routine |
| army_raised | war/armies.py | 73 | ok | ok | routine | 49 | 0 | yes | routine |
| artifact_captured | artifacts.py | 3 | ok | ok | scored | 3 | 3 | yes | two sided |
| artifact_created | artifacts.py | 273 | ok | ok | scored | 197 | 7 | yes | glory |
| artifact_destroyed | artifacts.py | 5 | ok | ok | scored | 2 | 3 | yes | one sided loss |
| artifact_lost | artifacts.py | 5 | ok | ok | scored | 3 | 1 | yes | one sided loss |
| blockade | maritime.py | 38 | ok | ok | scored | 28 | 16 | yes | hostility |
| blockade_lifted | maritime.py | 38 | ok | ok | scored | 26 | 0 | yes | unclassified (7+) |
| border_incident | simulation.py (hazard) | 434 | empty | label | scored | 324 | 42 | yes | hostility |
| brain_drain | agent_bridge.py | 349 | misleading | reworded | scored | 275 | 53 | yes | disaster |
| build_started | infrastructure.py | 647 | ok | ok | routine | 499 | 0 | yes | routine |
| call_to_arms | diplomacy.py | 14 | ok | ok | scored | 13 | 7 | yes | war start |
| campaign_victory | gp_agendas.py | 13 | ok | ok | scored | 9 | 9 | yes | unclassified (7+) |
| capability_banking | action_engine.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_commerce | action_engine.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_exploration | action_engine.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_fortification | infrastructure.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_mechanization | simulation.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_media | culture.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_metallurgy | ecology.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_naval_power | action_engine.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_networks | action_engine.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_printing | movements.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_scholarship | tech.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capability_surveillance | politics.py | 0 | ok | ok | bookkeeping | 0 | 0 | - | bookkeeping |
| capital_loss | politics.py | 2 | empty | label | turning point | 0 | 2 | yes | one sided loss |
| character_death | agent_bridge.py | 79 | ok | ok | scored | 65 | 22 | yes | unclassified (7+) |
| charter_refused | cities.py | 22 | ok | ok | scored | 19 | 3 | yes | unclassified (7+) |
| city_charter | agent_movements.py | 41 | ok | ok | scored | 30 | 8 | yes | unclassified (7+) |
| city_declined | cities.py | 12 | ok | ok | scored | 11 | 2 | yes | unclassified (7+) |
| city_fell | cities.py | 14 | ok | ok | scored | 13 | 5 | yes | unclassified (7+) |
| city_founded | cities.py | 38 | ok | ok | scored | 32 | 5 | yes | unclassified (7+) |
| city_grew | cities.py | 14 | ok | ok | scored | 9 | 4 | yes | unclassified (7+) |
| city_lord_changed | cities.py | 1 | ok | ok | scored | 0 | 0 | yes | unclassified (7+) |
| city_sacked | cities.py | 1 | ok | ok | scored | 0 | 1 | yes | unclassified (7+) |
| city_walls | cities.py | 5 | ok | ok | scored | 4 | 3 | yes | unclassified (7+) |
| civ_conquered | war/occupation.py | 0 | ok | ok | scored | 0 | 0 | - | two sided |
| civil_war | governance_runtime.py | 1 | ok | ok | turning point | 1 | 1 | yes | disgrace |
| cognomen_awarded | governance_runtime.py | 7 | ok | ok | scored | 5 | 4 | yes | glory |
| collapse | simulation.py | 0 | ok | ok | scored | 0 | 0 | - | disgrace |
| congress_ceasefire | politics.py | 3 | ok | ok | scored | 2 | 1 | yes | peace |
| congress_collapse | politics.py | 0 | ok | ok | scored | 0 | 0 | - | disgrace |
| congress_peace | politics.py | 2 | ok | ok | turning point | 2 | 2 | yes | peace |
| conquest_exile | agent_bridge.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| crown_loan | gp_agendas.py | 7 | ok | ok | scored | 4 | 2 | yes | unclassified (7+) |
| cultural_renaissance | simulation.py (hazard) | 110 | empty | label | scored | 77 | 26 | yes | glory |
| cultural_work | simulation.py | 20 | ok | ok | scored | 13 | 14 | yes | glory |
| dearth | ecology.py | 1436 | ok | ok | scored | 1162 | 263 | yes | disaster |
| debasement | finance.py | 18 | ok | ok | scored | 11 | 9 | yes | unclassified (7+) |
| debt_written_off | finance.py | 0 | ok | ok | routine | 0 | 0 | - | routine |
| demographic_crisis | agent_bridge.py | 420 | ok | ok | scored | 371 | 158 | yes | disaster |
| develop | action_engine.py | 2963 | ok | ok | routine | 2268 | 0 | yes | routine |
| diplomacy | action_engine.py | 1197 | ok | ok | routine | 906 | 0 | yes | routine |
| discovery | simulation.py (hazard) | 124 | empty | label | scored | 86 | 28 | yes | glory |
| drought | simulation.py (hazard) | 125 | empty | label | scored | 92 | 25 | yes | disaster |
| drought_intensification | emergence.py | 48 | ok | ok | turning point | 42 | 45 | yes | disaster |
| dynasty_extinct | dynasties.py | 9 | ok | ok | scored | 9 | 4 | actors | disgrace |
| dynasty_founded | dynasties.py | 9 | ok | ok | scored | 5 | 5 | actors | glory |
| dynasty_split | dynasties.py | 2 | ok | ok | scored | 2 | 0 | actors | disgrace |
| dzud | nomads.py | 16 | ok | ok | scored | 14 | 6 | yes | disaster |
| earthquake | climate.py | 86 | empty | label | scored | 67 | 34 | yes | disaster |
| ecological_recovery | emergence.py | 0 | ok | ok | scored | 0 | 0 | - | glory |
| economic_boom | agent_bridge.py | 170 | ok | ok | scored | 125 | 36 | yes | glory |
| elite_overproduction | governance_runtime.py | 14 | ok | ok | routine | 10 | 0 | yes | routine |
| embargo | action_engine.py | 410 | ok | ok | scored | 287 | 10 | yes | hostility |
| epidemic | epidemiology.py | 1507 | ok | ok | turning point | 1231 | 1027 | yes | disaster |
| epidemic_arrival | epidemiology.py | 1060 | ok | ok | turning point | 884 | 392 | yes | disaster |
| exile_return | agent_bridge.py | 5 | ok | ok | scored | 4 | 4 | yes | glory |
| expand | action_engine.py | 127 | ok | ok | scored | 90 | 4 | yes | routine |
| exploration | exploration.py | 25 | ok | ok | scored | 6 | 0 | yes | glory |
| explore_failed | exploration.py | 0 | ok | ok | routine | 0 | 0 | - | routine |
| faction_dominance_shift | factions.py | 103 | ok | ok | scored | 65 | 9 | yes | routine |
| famine | ecology.py | 310 | ok | ok | turning point | 292 | 268 | yes | disaster |
| famine_starvation | climate.py | 0 | ok | ok | scored | 0 | 0 | - | disaster |
| federation_collapsed | politics.py | 9 | empty | label | scored | 8 | 9 | yes | disgrace |
| federation_defense | politics.py | 20 | ok | ok | scored | 19 | 14 | yes | unclassified (7+) |
| federation_formed | politics.py | 14 | empty | label | scored | 9 | 11 | yes | peace |
| first_contact | exploration.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| fiscal_crisis | governance_runtime.py | 99 | ok | ok | scored | 81 | 17 | yes | disgrace |
| fiscal_strain | finance.py | 61 | ok | ok | routine | 35 | 0 | yes | routine |
| fleet_commissioned | maritime.py | 54 | ok | ok | scored | 43 | 0 | yes | unclassified (7+) |
| fleet_lost | maritime.py | 24 | ok | ok | scored | 21 | 22 | yes | one sided loss |
| fleet_storm | maritime.py | 54 | ok | ok | scored | 44 | 0 | yes | disaster |
| flood | climate.py | 70 | ok | ok | scored | 53 | 19 | yes | disaster |
| folk_hero_created | great_persons.py | 23 | ok | ok | scored | 18 | 9 | yes | glory |
| free_city | cities.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| fund_instability | politics.py | 265 | ok | ok | routine | 180 | 0 | yes | routine |
| fund_instability_failed | politics.py | 0 | ok | ok | routine | 0 | 0 | - | routine |
| general_fallen | war/armies.py | 3 | ok | ok | scored | 1 | 2 | yes | one sided loss |
| government_transition | governance_runtime.py | 64 | ok | ok | scored | 46 | 29 | yes | routine |
| gp_alliance_formed | runs only | 105 | ok | ok | scored | 79 | 0 | yes | unclassified (7+) |
| gp_coup | gp_agendas.py | 1 | ok | ok | turning point | 0 | 0 | yes | unclassified (7+) |
| gp_coup_failed | gp_agendas.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| gp_rivalry_formed | runs only | 4 | ok | ok | scored | 1 | 1 | yes | unclassified (7+) |
| great_person_born | simulation.py | 183 | ok | ok | scored | 143 | 12 | yes | glory |
| great_person_retired | simulation.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| guild_dissolved | guilds.py | 15 | ok | ok | scored | 13 | 2 | yes | unclassified (7+) |
| guild_founded | guilds.py | 38 | ok | ok | scored | 32 | 2 | yes | guild glory (3+) |
| guild_levy | guilds.py | 36 | ok | ok | scored | 26 | 4 | yes | unclassified (7+) |
| guild_privilege | guilds.py | 44 | ok | ok | scored | 33 | 4 | yes | guild glory (3+) |
| guild_privilege_lost | guilds.py | 0 | ok | ok | scored | 0 | 0 | - | guild decree (3+) |
| horde_dissolved | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| horde_formed | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | glory |
| horde_fragmented | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | disgrace |
| horde_rides | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | war start |
| hostage_taken | action_engine.py | 29 | ok | ok | scored | 23 | 25 | yes | two sided |
| infrastructure_completed | infrastructure.py | 662 | ok | ok | routine | 505 | 0 | yes | routine |
| institution_enacted | governance_runtime.py | 96 | ok | ok | scored | 67 | 10 | yes | glory |
| institution_enforcement_lapse | governance_runtime.py | 50 | ok | ok | routine | 45 | 0 | yes | unclassified (7+) |
| institution_repealed | governance_runtime.py | 45 | ok | ok | scored | 34 | 14 | yes | unclassified (7+) |
| institutional_regime_shift | governance_runtime.py | 39 | ok | ok | routine | 32 | 0 | yes | routine |
| intelligence_failure | intelligence.py | 2 | ok | ok | scored | 1 | 1 | yes | disgrace |
| invest_culture | culture.py | 149 | ok | ok | routine | 114 | 0 | yes | routine |
| leader_death | epidemiology.py | 292 | ok | ok | scored | 224 | 81 | yes | ruler |
| legacy | leaders.py | 2 | ok | ok | scored | 1 | 1 | yes | unclassified (7+) |
| legitimacy_crisis | governance_runtime.py | 8 | ok | ok | scored | 6 | 2 | yes | disgrace |
| liberation | war/occupation.py | 9 | ok | ok | scored | 6 | 1 | yes | two sided |
| loan_taken | finance.py | 142 | ok | ok | routine | 88 | 0 | yes | routine |
| local_rebellion | agent_bridge.py | 438 | ok | ok | scored | 343 | 117 | yes | disgrace |
| locust_swarm | emergence.py | 38 | ok | ok | scored | 31 | 31 | yes | disaster |
| loyalty_cascade | agent_bridge.py | 1 | ok | ok | scored | 1 | 1 | yes | disgrace |
| marriage_formed | simulation.py | 5 | ok | ok | scored | 2 | 4 | actors | unclassified (7+) |
| mass_migration | agent_bridge.py | 835 | ok | ok | scored | 636 | 104 | yes | disaster |
| mercenary_spawned | simulation.py | 88 | ok | ok | routine | 65 | 0 | yes | routine |
| migration | climate.py | 221 | empty | label | scored | 183 | 14 | yes | disaster |
| mine_collapse | emergence.py | 0 | ok | ok | scored | 0 | 0 | - | disaster |
| move_capital | politics.py | 142 | misleading | reworded | routine | 103 | 0 | yes | routine |
| movement_adoption | movements.py | 108 | ok | ok | scored | 95 | 17 | yes | faith |
| movement_concession | agent_movements.py | 3 | ok | ok | scored | 3 | 3 | yes | disgrace |
| movement_crackdown | agent_movements.py | 7 | ok | ok | scored | 6 | 7 | yes | unclassified (7+) |
| movement_crushed | agent_movements.py | 1 | ok | ok | scored | 1 | 1 | yes | unclassified (7+) |
| movement_demand | agent_movements.py | 49 | ok | ok | scored | 41 | 14 | yes | unclassified (7+) |
| movement_dispersed | agent_movements.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| movement_end | agent_movements.py | 94 | ok | ok | scored | 87 | 17 | yes | unclassified (7+) |
| movement_founded | agent_movements.py | 99 | ok | ok | scored | 84 | 29 | yes | unclassified (7+); a guild's: disgrace (3+) |
| movement_leader | agent_movements.py | 14 | ok | ok | scored | 9 | 3 | yes | unclassified (7+) |
| movement_martyr | agent_movements.py | 16 | ok | ok | scored | 16 | 2 | yes | faith |
| movement_reform | agent_movements.py | 22 | ok | ok | scored | 19 | 13 | yes | unclassified (7+); a guild charter: glory (3+) |
| movement_refused | agent_movements.py | 20 | ok | ok | scored | 16 | 3 | yes | unclassified (7+) |
| movement_rising | agent_movements.py | 4 | ok | ok | scored | 3 | 4 | yes | disgrace |
| movement_spread | agent_movements.py | 142 | ok | ok | routine | 119 | 0 | yes | unclassified (7+) |
| mule_artifact_relinquished | artifacts.py | 6 | ok | ok | scored | 6 | 5 | yes | unclassified (7+) |
| mutual_aid | mutual_aid.py | 37 | ok | ok | routine | 26 | 0 | yes | routine |
| naval_battle | maritime.py | 97 | ok | ok | scored | 69 | 63 | yes | battles |
| notable_migration | agent_bridge.py | 357 | ok | ok | routine | 285 | 0 | yes | routine |
| occupation | war/occupation.py | 19 | ok | ok | turning point | 10 | 15 | yes | two sided |
| occupation_revolt | war/occupation.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| occupation_shift | agent_bridge.py | 432 | ok | ok | routine | 322 | 0 | yes | routine |
| pandemic | emergence.py | 1 | ok | ok | turning point | 1 | 1 | yes | disaster |
| pandemic_leader_death | emergence.py | 0 | ok | ok | scored | 0 | 0 | - | disaster |
| pandemic_spread | emergence.py | 0 | ok | ok | routine | 0 | 0 | - | routine |
| pasture_abandoned | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| pasture_drought | nomads.py | 6 | ok | ok | scored | 3 | 0 | yes | disaster |
| pathogen_mutation | epidemiology.py | 31 | ok | ok | scored | 25 | 8 | yes | unclassified (7+) |
| peace_treaty | war/peace.py | 54 | ok | ok | turning point | 29 | 40 | yes | peace |
| pilgrimage_departure | great_persons.py | 24 | ok | ok | scored | 9 | 0 | yes | faith |
| pilgrimage_return | great_persons.py | 17 | ok | ok | scored | 10 | 3 | yes | faith |
| piracy | maritime.py | 3 | ok | ok | scored | 3 | 0 | yes | hostility |
| plague | epidemiology.py | 255 | empty | label | turning point | 220 | 127 | yes | disaster |
| power_struggle_resolved | factions.py | 87 | ok | ok | scored | 63 | 36 | yes | unclassified (7+) |
| power_struggle_started | factions.py | 89 | ok | ok | scored | 69 | 29 | yes | disgrace |
| preaching | gp_agendas.py | 24 | ok | ok | routine | 16 | 0 | yes | unclassified (7+) |
| price_inflation | finance.py | 18 | ok | ok | routine | 12 | 0 | yes | routine |
| proxy_detected | politics.py | 213 | empty | label | scored | 135 | 41 | yes | hostility |
| psi_crisis | governance_runtime.py | 17 | ok | ok | turning point | 11 | 16 | yes | disgrace |
| psi_recovery | governance_runtime.py | 15 | ok | ok | scored | 14 | 7 | yes | unclassified (7+) |
| quarantine | epidemiology.py | 440 | ok | ok | routine | 335 | 0 | yes | routine |
| raid | nomads.py | 2 | ok | ok | scored | 1 | 1 | yes | two sided |
| raid_repulsed | nomads.py | 1 | ok | ok | scored | 1 | 0 | yes | two sided |
| rebellion | simulation.py (hazard) | 167 | empty | label | scored | 128 | 8 | yes | disgrace |
| reform_lapsed | agent_movements.py | 0 | ok | ok | routine | 0 | 0 | - | unclassified (7+) |
| reform_pressure | governance_runtime.py | 11 | ok | ok | routine | 9 | 0 | yes | routine |
| reform_repealed | agent_movements.py | 16 | ok | ok | scored | 12 | 11 | yes | unclassified (7+); a guild charter: decree (3+) |
| religious_movement | simulation.py (hazard) | 105 | empty | label | scored | 75 | 20 | yes | faith |
| resource_depletion | ecology.py | 0 | ok | ok | scored | 0 | 0 | - | disaster |
| resource_discovery | emergence.py | 0 | ok | ok | scored | 0 | 0 | - | glory |
| restoration | politics.py | 0 | ok | ok | scored | 0 | 0 | - | glory |
| revolt | governance_runtime.py | 24 | ok | ok | scored | 21 | 13 | yes | disgrace |
| revolt_suppressed | cities.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| rival_fall | leaders.py | 1 | ok | ok | scored | 0 | 0 | yes | unclassified (7+) |
| rivalry_formed | simulation.py | 12 | ok | ok | scored | 9 | 2 | yes | unclassified (7+) |
| ruin_discovery | exploration.py | 0 | ok | ok | scored | 0 | 0 | - | glory |
| sandstorm | climate.py | 22 | ok | ok | scored | 13 | 6 | yes | disaster |
| scorched_earth | infrastructure.py | 8 | ok | ok | scored | 2 | 2 | yes | one sided loss |
| sea_contested | maritime.py | 7 | ok | ok | scored | 5 | 0 | yes | unclassified (7+) |
| sea_control | maritime.py | 78 | ok | ok | scored | 52 | 0 | yes | glory |
| sea_control_lost | maritime.py | 0 | ok | ok | scored | 0 | 0 | - | one sided loss |
| secession | agent_movements.py | 0 | ok | ok | scored | 0 | 0 | - | two sided |
| secession_defection | agent_bridge.py | 0 | ok | ok | scored | 0 | 0 | - | disgrace |
| secession_suppressed | governance_runtime.py | 1 | ok | ok | scored | 0 | 1 | yes | glory |
| sedentarization | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| settlement_dissolved | settlements.py | 35 | ok | ok | routine | 32 | 0 | yes | routine |
| settlement_founded | settlements.py | 59 | ok | ok | scored | 44 | 2 | yes | glory |
| shrine_commissioned | gp_agendas.py | 17 | ok | ok | routine | 5 | 0 | yes | unclassified (7+) |
| shrine_consecrated | gp_agendas.py | 15 | ok | ok | scored | 4 | 0 | yes | unclassified (7+) |
| siege_begun | war/battles.py | 35 | ok | ok | scored | 23 | 9 | yes | hostility |
| soil_exhaustion | ecology.py | 6 | ok | ok | scored | 4 | 5 | yes | disaster |
| state_default | finance.py | 16 | ok | ok | turning point | 15 | 13 | yes | unclassified (7+) |
| succession_backed | gp_agendas.py | 1 | ok | ok | scored | 1 | 1 | yes | unclassified (7+) |
| succession_crisis | simulation.py | 8 | ok | ok | turning point | 6 | 8 | yes | disgrace |
| succession_crisis_resolved | factions.py | 9 | ok | ok | turning point | 8 | 9 | yes | ruler |
| supervolcano | emergence.py | 7 | ok | ok | turning point | 4 | 7 | yes | disaster |
| supply_shock | economy.py | 2147 | ok | ok | routine | 1685 | 0 | yes | routine |
| tech_accident | emergence.py | 0 | ok | ok | scored | 0 | 0 | - | disaster |
| tech_advancement | tech.py | 23 | ok | ok | scored | 21 | 23 | yes | glory |
| tech_focus_selected | simulation.py | 0 | ok | ok | routine | 0 | 0 | - | routine |
| tech_regression | emergence.py | 7 | ok | ok | turning point | 6 | 7 | yes | disgrace |
| technique_adopted | techniques.py | 97 | ok | ok | routine | 72 | 0 | yes | unclassified (7+) |
| technique_invented | techniques.py | 28 | ok | ok | scored | 20 | 13 | yes | glory |
| technique_lost | techniques.py | 22 | ok | ok | scored | 14 | 7 | yes | one sided loss |
| temple_destroyed | infrastructure.py | 236 | ok | ok | scored | 187 | 25 | actors | faith |
| terrain_transition | emergence.py | 9 | ok | ok | routine | 5 | 0 | yes | routine |
| trade | action_engine.py | 752 | ok | ok | routine | 602 | 0 | yes | routine |
| trade_mission | gp_agendas.py | 14 | ok | ok | scored | 8 | 0 | yes | unclassified (7+) |
| trading_house_founded | gp_agendas.py | 37 | ok | ok | scored | 28 | 3 | yes | unclassified (7+) |
| tradition_acquired | simulation.py | 42 | ok | ok | scored | 33 | 4 | yes | glory |
| trait_evolution | simulation.py | 225 | ok | ok | routine | 165 | 0 | yes | routine |
| treaty_broken | diplomacy.py | 20 | ok | ok | scored | 17 | 16 | yes | hostility |
| treaty_expired | diplomacy.py | 180 | ok | ok | routine | 149 | 0 | yes | routine |
| treaty_renewed | diplomacy.py | 560 | ok | ok | routine | 430 | 0 | yes | routine |
| treaty_signed | diplomacy.py | 196 | ok | ok | scored | 148 | 64 | yes | peace |
| tribute_agreed | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | peace |
| tribute_ended | nomads.py | 0 | ok | ok | scored | 0 | 0 | - | bookkeeping |
| twilight | politics.py | 1 | ok | ok | scored | 1 | 1 | yes | disgrace |
| twilight_absorption | politics.rs (native) | 0 | ok | ok | scored | 0 | 0 | - | two sided |
| union_annexation | runs only | 2 | ok | ok | scored | 2 | 1 | yes | two sided |
| urban_concession | cities.py | 2 | ok | ok | scored | 2 | 2 | yes | unclassified (7+) |
| urban_revolt | cities.py | 2 | ok | ok | scored | 2 | 2 | yes | unclassified (7+) |
| vassal_loosened | diplomacy.py | 0 | ok | ok | scored | 0 | 0 | - | unclassified (7+) |
| vassal_promoted | diplomacy.py | 7 | ok | ok | scored | 6 | 5 | yes | unclassified (7+) |
| vassal_rebellion | politics.py | 2 | empty | label | turning point | 2 | 2 | yes | disgrace |
| vassalization | diplomacy.py | 4 | ok | ok | scored | 3 | 2 | yes | two sided |
| war | action_engine.py | 134 | ok | ok | scored | 86 | 64 | yes | battles |
| war_agitation | gp_agendas.py | 10 | ok | ok | scored | 8 | 0 | yes | unclassified (7+) |
| war_declared | war/peace.py | 70 | ok | ok | scored | 56 | 49 | yes | war start |
| war_ended | war/peace.py | 15 | ok | ok | scored | 14 | 0 | yes | bookkeeping |
| wildfire | climate.py | 35 | ok | ok | scored | 21 | 8 | yes | disaster |

Episode closings seen in the runs (bookkeeping, counted not listed): Mass Migration_ended, brain_drain_ended, capital_relocation_ended, culture_legacy_ended, dearth_ended, demographic_crisis_ended, drought_ended, economic_boom_ended, economy_legacy_ended, epidemic_ended, famine_ended, fiscal_strain_ended, local_rebellion_ended, loyalty_cascade_ended, mass_migration_ended, military_legacy_ended, occupation_shift_ended, piracy_ended, plague_ended, price_inflation_ended, quarantine_ended, restless_population_ended, soil_exhaustion_ended, stability_legacy_ended, supply_shock_ended, volcanic_winter_ended

**Agent events from the native tick** (`agent_bridge.EVENT_TYPE_MAP`:
death, rebellion, migration, occupation switch, loyalty flip, birth,
dissolution) are per-agent records, never narrated directly. They reach the
narrator as the bridge's summaries (`mass_migration` with its driver,
`local_rebellion`, `loyalty_cascade`, `occupation_shift`,
`demographic_crisis`, `economic_boom`, `brain_drain`) and character events
(`notable_migration`, `character_death`, `exile_return`, `conquest_exile`,
`secession_defection`), all in the table; and through the agent context
(mood from `local_rebellion` / `demographic_crisis`, displacement, named
characters' memories and needs).

**Named events** (landmarks) by kind, lines in the three runs' prompts:

| kind | n | landmark lines before | after |
| --- | ---: | ---: | ---: |
| treaty | 250 | 242 | 45 |
| legacy | 185 | 140 | 70 |
| battle | 164 | 107 | 72 |
| propaganda_campaign | 149 | 141 | 88 |
| movement_schism | 146 | 129 | 62 |
| movement_adoption | 108 | 95 | 17 |
| coup | 93 | 93 | 77 |
| rival_fall | 49 | 21 | 7 |
| movement_emergence | 38 | 23 | 23 |
| tech_breakthrough | 23 | 23 | 18 |
| cultural_work | 20 | 13 | 13 |
| occupation | 19 | 10 | 3 |
| cultural_assimilation | 13 | 12 | 6 |
| conquest | 10 | 2 | 6 |
| cultural_hegemony | 6 | 4 | 4 |
| universal_enlightenment | 6 | 0 | 5 |
| paradigm_shift | 5 | 5 | 5 |

Lines are prompt lines naming the event. Before, every named event whose
actors matched an event of a selected window was listed; after, the five
most important of a moment, and named events that match no event (an
enlightenment named for every civ, schisms, rivals' falls) join the moment
covering their turn (universal enlightenment, importance 10: 0 -> 5).

**Guilds, burghers and movement news** (PR #40): the five guild kinds are
in the table with readable lines (founded, privilege won, privilege lost,
levy, dissolved), weighed by importance (3-4, so a guild line is listed
when the moment is quiet or the guild's civ is its focus); the standing
state names the guilds of the moment's regions and the burgher faction's
share. A guild rising as a
movement is a `movement_founded` with the guild creed, and a guild charter
a reform in force. The burghers' rise is a `faction_dominance_shift`, no
longer routine. Movement news (native information packets, type 4) is not
an event: it raises founding chances and is counted per run
(`GuildState.counters["news_foundings"]`). Since the follow-up below, a
founding clearly sparked by news of a like movement's won demand cites
that demand as a cause ([Follow-ups](#follow-ups-news-guild-chronicles-spread)).

## 6. Viewer QA

Production code on the Vite dev server, headless Chromium (Playwright,
`/opt/pw-browsers`), real bundles of the runs above: the Movements, Cities
and Food tabs and the food map layer at a seeked turn, checked for console
errors and `NaN` / `undefined` / `null` text (none). Found and fixed:

- **Food crises a turn early** (Food tab, food map layer, region detail).
  A snapshot of turn T holds the state after turn T - 1 (its food is what
  turn T - 1 observed), but crises were read at turn T, so a dearth or
  famine reported in turn T showed beside the previous turn's food: 655 of
  861 new reports in the procedural run sat beside food at or above need or
  unobserved; read at T - 1, 6 of 861. `lib/food.crisesAtSnapshot`.
- **Hungry regions**: regions not observed sorted first (as if at 0); now
  last.
- **Wares column** showed one decimal: 104 of 1,983 non-zero values were
  under 0.05 and read "0.0"; now two decimals (the snapshot's own).
- **Movements tab**: the creed chart had no legend; the selected movement's
  note read "ended won at turn 201" and gave the whole run's totals at an
  earlier turn without saying so ("Whole record: ...; won its demand at
  turn 201 (after turn 191)"); a dead leader was shown as leading ("Archon
  Banyaris (martyred T62)"). The legend lists the guild creed only where the
  run records guilds.
- **Header** named every loaded bundle "Procedural setup"; now "Template
  world" or "Procedural world".

Screenshots (outside the repository), `<HOME>/runs/narration/screens/`:
before the fixes `r2_t191_movements.png`, `r2_t191_cities.png`,
`r2_t191_food.png`; after, pre-guilds `r2_t191_after_*.png`,
`r1_t72_after_*.png`; on the merged source `final_r2_t348_{movements,
cities,food,food_layer,wares_column}.png` and `final_r1_t457_*.png`.

## Identity

Base: `main` source (`11238d5`, then `aa0f655`) on `PYTHONPATH`; head: this
branch; same interpreter, native extension (fresh release builds,
`f8e1017e...c2f410` on `11238d5`, `5ede10a9...8b07d6` after the merge,
compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator`),
arguments and `PYTHONHASHSEED=0`.

- Simulate-only, `scripts/cities_identity.py compare` (every file byte for
  byte): template 42 `--agents off` 300 turns (9 files), template 7 hybrid
  200 turns with `--validation-sidecar` (110 files: validation sidecars and
  agent events included), procedural 48 x 10 seed 11 hybrid 150 turns with
  `--validation-sidecar` (91 files): 0 differences, on both bases.
- The three narrated runs, `scripts/narration_identity.py compare`
  (everything but `chronicle.md`, the prompt capture and the bundle's
  `chronicle_entries` / `gap_summaries`): 9 / 15 / 9 files, 0 differences,
  on both bases.
- A first version routed `curator.event_label` through the new lines and
  changed `state.historiography.json`: the historiography layer calls it
  while the run is observed. It is restored and pinned by a test.
- Narration determinism: the same run gives byte-identical prompts and
  chronicle (in-run, rerun) and identical prompts and entries from a bundle
  under `PYTHONHASHSEED` 0, 1 and 4242.

## Tests

Linux, Python 3.13, `-n 2`, code head `7b38e41`, native extension built
fresh after the merge (`5ede10a9...8b07d6`, compiled classes verified):

- `pytest -m "not slow"`: 6,274 passed, 3 skipped; `-m slow`: 11 passed,
  3 skipped; no-Rust environment (no `chronicler_agents`), `-m "not slow"`:
  6,034 passed, 229 skipped.
- `scripts/run_python_oracle_checks.py`: PASS in 101.7 s (2,279 passed, 35
  skipped; a new `narration` chunk, 98 tests in 1.3 s).
- Viewer: 303 tests passed (39 files, `--maxWorkers=1`), ESLint clean,
  production build (the existing large-chunk warning).
- New: `tests/test_narration_context.py` (29: labels, rewordings, the label
  historiography writes with, faith names, bounded selection, folding,
  extra turning-point lines, scarce kinds and chain steps, standing state
  with wars, movements, martyred leaders, reforms, cities, guilds, burghers
  and food, food-crisis spans, later consequences, prompt blocks,
  determinism, mechanical sentences, landmarks, unmatched named events,
  agent context, curator weights, a lone catastrophe against saturated
  chains, the two scripts); `test_curator.py` (cluster score, diversity on
  main actors and kinds, minor named events); viewer `food.test.ts`
  (crises at their snapshot, the fixture's alignment), `movements.test.ts`
  (record note, martyrdoms), `SystemsPanel.test.tsx` (unobserved regions
  last, wares to two decimals, creed legend), `AppShell.helpers.test.ts`.
  Intentional changes in existing tests: the cluster score, the mechanical
  fallback text ("Battle."), landmarks need importance 7 to exempt.
- Not run: `cargo test` (no Rust change on this branch) and a 200-seed gate
  (the simulation is byte-identical).

## Follow-ups: news, guild chronicles, spread

Branch `fix/movements-narration-polish` (from `main` `2dd47d4`, PR #41).
Its first commit changes the simulation (movement founders enrolled at
founding; [agent-movements.md](agent-movements.md#founders-at-founding-no-empty-movements));
the rest observe the run and change no simulation state.

- **Movement news per founding** (`agent_movements.news_cause`). The native
  grievance census also names, per region and creed, the news most of the
  informed aggrieved hold (`news_source_{region,turn,kind,count}_*`, read
  only). A census founding whose region's aggrieved hold, at least a quarter
  of them (`NEWS_CAUSE_SHARE`, the founding chance x1.5 or more), news of a
  demand a like movement won in another region (`movement_reform` or
  `movement_concession`) cites that event as a cause: a recorded "because"
  link (curator chains, the viewer's Because panel), no new event. Prompt
  lines add "stirred by news of the demand won in R in turn T", and such a
  founding weighs +2 in the line selection, as a named event does. One
  linked founding in each of the procedural seed-7, template 1234 and
  procedural seed-11 runs below, none in template 42: the timeline is not
  flooded. Template 1234's prompt lists it ("In Frostholm Tundra, the
  discontented found the Brethren of the Last Days (172) ... stirred by
  news of the demand won in Crystalfen Marsh in turn 163"); the procedural
  moment holding its one keeps busier lines.
- **Guild chronicles** (`historiography.GUILD_GLORY`, `GUILD_DECREE`,
  `_Turn.guild_stance`): from importance 3, a guild formed, a privilege won
  or a guild charter granted is told as the realm's prosperity (glory: a
  loyal court praises the ruler); a privilege lost or a guild charter
  repealed as the ruler's decree (a loyal court: "By the just decree of
  ..."; a disaffected one: "...; such was the misrule of ..."); a guild
  rising as a movement as unrest (disgrace: omitted or blamed by a loyal
  court, held against the ruler by a disaffected one). Guild movements and
  charters are read from the movement record; other movements keep their
  floors. New accounts in the three runs: 18 / 88 / 10 (formations and
  privileges; in the procedural run also 4 risings, 2 charters, 1 repeal,
  1 privilege lost); no earlier account changed or was lost.
- **Temporal spread** (`curator.spread_moments`): after the diversity
  penalty, an untold stretch longer than two even spacings of the run
  (`SPREAD_GAP`, span / moments) gets its best window in place of the
  weakest selected moment whose removal opens no such stretch, if it scores
  at least 75% of it (`SPREAD_KEEP`). A moment holding an event or named
  event of importance 9 or more stays (`SPREAD_PROTECT`): in the procedural
  world every selected window held a named event of importance 7, so the
  diversity rule's landmark exemption would leave nothing to move.

Selected moments over the run, the same bundles curated without and with
the rule (`scripts/curator_spread.py compare`; the in-run narration gives
the same rows):

| | template 42, 500 turns | procedural 48 x 10, seed 7, 400 | template 1234, 300 |
| --- | --- | --- | --- |
| moments per tenth of the run | 4 6 4 7 3 5 6 5 4 6 -> 4 7 4 7 4 5 6 3 5 5 | 7 5 4 4 6 3 7 2 6 6 -> 6 5 3 5 6 4 7 3 6 5 | 4 5 5 5 5 5 5 5 5 6 (unchanged) |
| longest untold stretch, turns | 30 -> 18 | 18 -> 12 | 1 -> 1 |
| largest gap between moments, turns | 36 -> 24 | 29 -> 23 | 11 -> 11 |
| gaps' coefficient of variation | 0.80 -> 0.63 | 0.68 -> 0.57 | 0.40 -> 0.40 |
| turning points (8+) in the moments | 103 -> 95 | 332 -> 329 | 136 -> 136 |
| importance-10 events in the moments | 3 -> 3 | 1 -> 1 | 13 -> 13 |
| summed moment scores | 1,210.7 -> 1,203.8 | 1,259.7 -> 1,259.9 | 1,146.4 -> 1,146.4 |

Template 1234 has 50 windows for 50 moments, so every window is told.
Template 42 trades five of its lowest-scoring moments (scores 20.1-20.9;
the eight-plus events given up are nine reports of two famines) for
windows in three stretches of 24-30 untold turns (scores 16.6-20.4); the
procedural run swaps three (21.9-22.9 out, 21.6-23.2 in, one of them a
window the diversity penalty had demoted). A uniform crowding
discount was tried first and dropped: it spread the procedural run worse
(largest gap 18 -> 23) and gave up 30 of its turning points, and the
diversity penalty's swaps undid it in template 42.

**Prompts stay bounded** (in-run, before -> after; tokens at four
characters): mean 2,647 -> 2,638 / 4,097 -> 4,080 / 2,737 -> 2,739, max
4,870 / 6,003 / 5,813 unchanged, all 50 prompts 132,351 -> 131,911 /
204,853 -> 204,014 / 136,893 -> 136,973; turning points listed 103 -> 95
of 115 / 332 -> 329 of 406 / 136 of 136.

**Identity** (base: the branch's first commit `022deb2` with its
extension `4e2f699d...a328e`; head `e144ae6` with `c26d6cd2...bbb99`;
`PYTHONHASHSEED=0`): `scripts/narration_identity.py compare-observers`
(everything but the narration, the in-world chronicles and the founding
news links) over the three narrated runs and template 42 `--agents off`
300, template 7 hybrid 200 and procedural 48 x 10 seed 11 hybrid 150 (both
with `--validation-sidecar`): 8 / 14 / 8 / 7 / 108 / 89 files, 0
differences. Byte for byte (`scripts/cities_identity.py`): template 42 off
9 files identical; `state.json` identical where no founding was linked
(template 7, template 42 hybrid) and different by one cause where one was;
snapshots, validation sidecars and agent events identical in every run.
Narration determinism: prompts and entries from the bundles identical under
`PYTHONHASHSEED` 0, 1 and 4242 (template 42, procedural 7), and an in-run
rerun (template 1234) byte-identical in prompts, chronicle, state and
chronicles.

## Open

- A moment in a 10-civ world mixes unrelated stories; the focus bonus and
  the per-kind cap keep one story in front, but there is no per-civ split.
- Movement news is cited only for a won demand clearly held by the
  aggrieved; news of a founding or a rising elsewhere, and news carried by
  migrants beyond the founding region's census, are not.
- Historiography still classifies `faction_dominance_shift` as routine and
  does not chronicle levies or dissolved guilds.
- Descriptions keep game notation ("intensity=0.43", "(18 ships)"); the
  system prompt asks the model not to repeat mechanics.
- City names are "Region Settlement 1" in the record; in-world names come
  from `languages` where the run has them.
- No LLM was called: prose quality with these prompts is untested.
