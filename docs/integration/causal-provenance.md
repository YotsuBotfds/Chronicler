# Causal provenance

Branch `feat/causal-provenance`, based on `integrate/wave-2` at `cf13f87`
(wave 1, the world-extinction fix, Geography 2.0, Rust agent scale, the
contact ledger and the Python scale work). Code: `src/chronicler/provenance.py`
(recording), `src/chronicler/curator.py` (cause graph), `src/chronicler/narrative.py`
(chains in prompts and the mechanical chronicle).

The simulation decides outcomes; provenance only records **why**. It draws no
random numbers, mutates no simulation state and no simulation decision reads it.
Every simulation outcome is identical to the base branch (see
[Outcome identity](#outcome-identity)).

## Why

`Event` had no identity, region or causes, and its `consequences` field was
never written. The curator guessed causal links from event-type pairs, time
gaps and shared actors: on the base subset gate it produced **48,664 links per
200-turn run**, 54% `supply_shock→supply_shock` and 30% `supply_shock→migration`.
Agent summary events (`demographic_crisis`, `local_rebellion`, `economic_boom`,
`brain_drain`, ...) named only characters (or nobody), so they never linked to
a civilization's causes. Chronic conditions emitted an event every turn
(`supply_shock` about 1,800 times per hybrid run, at importance 5-9).

## Event identity

New `Event` fields, all optional and omitted from serialized output while
empty (old saves, bundles and fixtures keep their bytes):

| Field | Meaning |
| --- | --- |
| `event_id` | `"<turn>:<event_type>:<n>"`: the turn being simulated, the type, and a per-(turn, type) counter |
| `causes` | ids of the events that produced this one (effect → cause) |
| `region` | region name, for regional events |
| `civs` | civilizations involved when the actors are not (character-only or empty actors) |
| `episode` | chronic conditions: `onset`, `tick` (a repeat a simulation consumer reads), `end`; `repeat` only in the diagnostic legacy timeline |
| `duration` | turns, on `end` events |

`ActiveCondition` gains `condition_id` (`"<turn>:condition.<type>:<n>"`),
`cause_id` (the event that created it) and `onset_turn`. `Event.consequences`
stays a legacy free-text field; the graph is stored once, as `causes`.

**Assignment.** `run_turn` passes each phase's output through
`provenance.observe` (the local `_emit` helper replaces `turn_events.extend`),
in phase order. `observe` first takes the events the phase appended straight to
`world.events_timeline`, then the events it returned. Each gets an id, its
causes, and is registered in the causal index. `end_turn` closes finished
episodes and conditions before the post-Phase-10 commit, and `finish_turn` ids
any straggler. Emitters whose same-phase chains must resolve in order observe
at emission (`provenance.observe_now`, used by `war.common.emit`), and an
emitter can take an id early with `provenance.ensure_id`.

Ids are a pure function of the deterministic event stream: no RNG, no clock,
no hashing of mutable state. The per-turn counters live on
`WorldState._provenance_turn` (`TurnIds`), an equality-neutral cache that is
reset whenever the world moves to another turn, so a world loaded at a turn
boundary resumes with exactly the ids an uninterrupted run assigns (tested).
Events without ids (old saves) can be given read-time legacy ids
(`provenance.backfill_ids`, prefix `L`).

## Causes

Two sources, both recorded at emission time from state the triggering
mechanism actually reads. No cause is inferred from type pairs or time gaps.

1. **Emitter stamps** where the code knows the exact cause.
2. **Cause rules** (`provenance.CAUSE_RULES`), applied when an emitter left
   `causes` empty (and merged for civ `rebellion`, `migration` and
   `supply_shock`, whose emitters stamp only part of the story). They look up the
   persisted causal index `WorldState.provenance.keys`: the event that
   currently stands for a state, such as `war:A|B` (the war of a pair),
   `occupation:<region>`, `siege:<region>`, `psi:<civ>`, `drought:<civ>`,
   `pandemic:<region>`, `disaster:<region>`, the open famine or food shortage
   of a region. Keys are registered when the standing event is observed and
   removed when the state ends (peace, liberation, PSI recovery). Recency
   windows bound keys whose end is not an event (border incidents, droughts).

| Area | What is recorded |
| --- | --- |
| War (`war/`) | battles cite their war's declaration; sieges the war; occupations the battle or siege that took the region; annexation, liberation and occupation revolts the occupation; `civ_conquered` the annexation; peace treaties and `war_ended` the war; fallen generals, destroyed armies and hostages the battle; a declaration cites recent border incidents, embargoes, proxy wars and the last peace of the pair. Battle, siege, occupation and army events carry `region`. |
| Famine (`ecology.py`) | drought on the civ, a recent disaster in the region, open soil exhaustion, the open food shortage, a siege or occupation, a pandemic in the region. Repeat strikes (`tick`) carry the causes of their own turn. |
| Flight (`climate.py`, agent summaries) | climate flight, `mass_migration`, `brain_drain`, `demographic_crisis`, `notable_migration`: the region's famine, battle, occupation, pandemic, disaster, persecution, the civ's drought. |
| Unrest | `local_rebellion`, `loyalty_cascade`: the region's famine, occupation, conquest and persecution, the civ's PSI crisis. Civ `rebellion`, `secession`, `secession_suppressed`, `collapse`: the civ's open famines, PSI crisis, recent revolt, active wars, recent plague (the conditions that drain the stability those checks read), plus legitimacy crises and earlier secessions. Twilight and absorption: collapse, twilight, secession. |
| Governance (`governance_runtime.py`) | `psi_crisis` cites the drivers it names (elite overproduction, fiscal distress, popular immiseration as open famines); `revolt` the PSI crisis (revolts roll only during one); `civil_war` the revolt that escalated and a recent legitimacy crisis; neglect repeals and enforcement lapses the fiscal crisis. |
| Disease (`emergence.py`, `events.py`) | a new `pandemic_spread` event per contact edge the plague crossed (source region → target region; adjacency or contact-ledger flows), citing the source region's pandemic; pandemic leader deaths cite the pandemic in the civ's regions; hazard-rolled `plague` cites the plague in a contact civ that excited it (below). |
| Hazard excitation (`events.py`, `simulation.py`) | `ingest_turn_events` records, per civ and event type, the event whose decayed excitation is currently largest (`WorldState.provenance.exciters`; inhibiting terms such as plague self-immunity are ignored; plague contact and border-incident reciprocity included). A rolled hazard event (drought, plague, rebellion, migration, border incident, discovery, renaissance, leader death by "misfortune") cites that event when its term is at least half of the rate the event was rolled at: in a Hawkes process the probability that an event was triggered by one excitation term is that term's share of the rate. |
| Leaders | a leader death cites the mortality component that drew it (battle: the civ's wars; coup: PSI crisis, revolt, civil war, legitimacy; misfortune: the exciting event); the succession crisis it triggers cites the death. |
| Tech regression | the triggers that matched: capital loss (the occupation/annexation that took the capital, secession, collapse), entry into twilight, a black swan while stressed. |
| Great persons | `great_person_born` cites the achievement its threshold counts (the latest war win for a general, the era advance since the last scientist, the movement adoption for a prophet); the person's later deeds (artifacts, pilgrimages) cite the emergence. |
| Religion | persecutions carry their region and cite a recent conquest of it; the "Mass Migration" of the faithful cites the persecution; schisms cite persecution in their region. |
| Other | supply shocks cite the upstream region's open shortage (import-driven shocks), disasters, sieges, occupations, droughts, wars and recent embargoes of the civ; ecological recovery cites the depletion it recovers from; capital loss the occupation of the capital; exiles the conquest; exile returns the exile; artifact losses the conquest. |

**Agent events.** Agent summaries now carry `region` and `civs` (the region's
controller; `loyalty_cascade` also the civ it shifts to); character events
carry the character's region and civ. Their causes are a deterministic
Python-side join on the region's conditions in the causal index: no Rust
`AgentEvent` field was needed and the native extension is unchanged.

## Chronic conditions

`provenance.CHRONIC` lists the conditions that reported every turn. The first
report opens an episode (`episode="onset"`); later reports within the
condition's gap fold into it; when the reports stop, a closing
`<type>_ended` event (`episode="end"`, `duration`, citing the onset) is
emitted. Episodes are keyed by type, region (and shock category) and persist
in `WorldState.provenance.episodes`, so a resumed run closes them correctly.

| Type | Gap | Repeats | Notes |
| --- | --- | --- | --- |
| `famine` | 5 (famine cooldown) | kept as `tick` | traditions (`famines_survived`) and factions count every strike |
| `supply_shock` | 1 | folded | onset importance capped at 6 (was 5-9) |
| `economic_boom`, `brain_drain`, `demographic_crisis`, `loyalty_cascade` | 1 | folded | windowed agent patterns that re-fired every turn |
| `occupation_shift`, `mass_migration`, `local_rebellion` | 1 | folded | consecutive turns in one region |
| `migration` (climate flight), `famine_starvation`, `soil_exhaustion`, "Mass Migration" | 1 | folded | |

Only regional reports are folded (hazard-rolled civ `migration` has no region
and is untouched). `pandemic_spread` is the one new event type that is not an
episode end; it exists only to carry provenance. No simulation code reads the folded types; the per-turn
signal that is consumed (famine) stays on the timeline. `ActiveCondition`s
(drought, plague, capital relocation, volcanic winter, ...) emit
`<type>_ended` with their duration when they expire.

## Curator

`curate` builds a `CauseGraph` from the recorded `causes` that resolve inside
the event list and adds a chain bonus per event (`compute_chain_scores`):

* root causes (no recorded cause): `1.5 × depth + 1.0 × log2(1 + descendants)`;
* effects with consequences: `0.75 × depth + 0.5 × log2(1 + descendants) + 0.5 × cause depth`;
* capped at 12; closing events (and legacy-timeline repeats) score nothing and
  never anchor a moment; famine ticks, renewed strikes with their own causes,
  count like any other event.

Depth counts substantive steps (closing events do not extend a chain).
`CAUSAL_PATTERNS` remain only as a fallback for events without any provenance
(no id and no causes: old saves and bundles): one link per effect and
pattern, to the most recent matching cause, in O(n log n) instead of every
pair. An observed event without causes has none the simulation knows of and
is not guessed at. (`movement` in the patterns, a type that never occurs, is
now `movement_adoption`.) `CausalLink` gains `cause_id`, `effect_id` and `provenance`
(`recorded` or `pattern`). Each moment carries up to three `causal_chains`
(`CausalChain` of `ChainStep`s, root first): the deepest recorded chains
ending at its events.

## Narration

* The narrator prompt gains a `CAUSAL CHAINS recorded by the simulation` block
  (`[turn 0] A goes to war with B -> [turn 6] X is occupied -> [turn 9] Famine strikes X`)
  and marks recorded links.
* The mechanical chronicle (`narrative.mechanical_narrative`, used for every
  LLM failure and by the new `--narrator mechanical`) keeps the event
  descriptions and appends one "because" sentence per chain. Within one
  chronicle, a cause told before is cut short ("..., as told above").
* `--narrator mechanical` (also with `--simulate-only`, and for `--narrate
  bundle`) writes a curated no-LLM chronicle.

## Viewer bundle

`LEGACY_BUNDLE_VERSION` is 4. Events carry their provenance fields, chronicle
entries `causal_chains`, causal links their ids and provenance; all optional,
so version-3 bundles load unchanged (the viewer fixtures are version 3).

* Legacy UI: `ChroniclePanel` lists an entry's recorded chains ("Because") and
  marks recorded links.
* AppShell: events are selected by `event_id` when present (the old
  turn-type key collided for same-turn events of one type); the event
  inspector shows "Because" (the cited events) and "Led to" (events citing it).

## Outcome identity

Contract: provenance never draws RNG, never writes simulation fields and is
never read by a simulation decision. It also never builds or touches the
world's lookup caches (`civ_map`, `region_map`, trade-route caches): building a
cache earlier than the simulation would can change what a later stale-cache read
returns. Lookups scan `world.civilizations` and `world.regions` directly.

Proof, three layers:

1. **Frozen exact-trajectory oracles, in the suite.**
   `provenance.LEGACY_TIMELINE` is a diagnostic switch (never set in
   production): ids, causes and the index are recorded, but the timeline is
   written exactly as a provenance-free run writes it (no folding, no
   importance cap, no end events). `test_performance_equivalence`,
   `test_governance_dormancy` and `test_turn_artifact_lifecycle` run with it
   and compare events without the additive fields
   (`scripts/third_wave_controls.legacy_event_dump`/`strip_provenance`; the
   provenance-only `pandemic_spread` events are also left out): every turn's
   snapshot, events and narration hash, the ordered RNG trace and the
   state/bundle/memory artifact bytes match the unchanged
   `corrected_extinction_2026_10` fixtures.
2. **In-suite production check.** `test_provenance_does_not_change_simulation_outcomes`
   runs the same seed with the observer disabled, in legacy mode and in
   production: worlds are identical apart from provenance fields, and the
   production timeline is an ordered subsequence of the provenance-free one.
3. **Native hybrid and off runs against the base commit**
   (`scripts/provenance_identity.py`). Base `cf13f87` and this branch, seeds
   42, 7 and 1234, `--agents hybrid` 200 turns and `--agents off` 300 turns,
   `PYTHONHASHSEED=0`, same native extension:

| Run | Legacy timeline (`run-legacy`) | Production |
| --- | --- | --- |
| hybrid 42, 200 turns | identical (5,364 events) | identical; timeline 5,364 → 2,607 (3,217 repeats folded, 460 end events) |
| hybrid 7, 200 turns | identical (7,511 events) | identical; 7,511 → 4,165 (4,411 folded, 1,065 end) |
| hybrid 1234, 200 turns | identical (4,806 events) | identical; 4,806 → 2,233 (2,934 folded, 361 end) |
| off 42, 300 turns | identical (2,715 events) | identical; 2,715 → 2,881 (28 folded, 194 end) |
| off 7, 300 turns | identical (1,973 events) | identical; 1,973 → 2,073 (47 folded, 147 end) |
| off 1234, 300 turns | identical (2,505 events) | identical; 2,505 → 2,579 (94 folded, 168 end) |

"Identical" covers `state.json` (all world state except the timeline),
every bundle history snapshot, the bundle world state, named events and the
`agent_events.arrow` bytes; in legacy mode also the whole timeline. In
production the timeline is the base timeline with only chronic repeats removed
(ordered-subsequence check) plus the added `*_ended`/`pandemic_spread` events.
The same production comparison passes for all 20 subset-gate seeds (base and
branch gate outputs), and a legacy-timeline run of gate seed 58, which has a
pandemic, is identical as well. Off mode gains events: its few chronic
reports fold, while conditions and famines now also close with an end event.

## Results

Subset profile (20 seeds × 200 turns, hybrid, default features), base
`cf13f87` → this branch:

| Per run | Base | Branch |
| --- | --- | --- |
| Timeline events | 5,897 | 2,930 |
| Events with recorded causes | 0 | 1,473 (50%) |
| Curator causal links | 48,664 | 1,811 |
| Links with recorded provenance | 0% | 100% (1,207 causal, 605 episode onset → end) |
| Type-pair (pattern) links | 48,664 (54% `supply_shock→supply_shock`, 30% `supply_shock→migration`) | 0 (patterns now only link events without provenance) |
| `curate()` wall time | about 46 s (2 seeds measured) | 0.08 s |

Deepest recorded chains in subset seed 42 (curator labels):

1. t0 Ashkari Nomads goes to war with Thornwall Confederacy → t0 The Fight for
   Thornwood → t0 Thornwood is occupied → t3 food shortage in Thornwood → t3
   famine in Thornwood → t6 Thornwood loses 40% of its people.
2. t0 Kethani Empire goes to war with Thornwall Confederacy → t6 The Fight for
   Amber Valley → t6 Amber Valley is occupied → t9 food shortage → t9 famine →
   t11 Amber Valley loses 33% of its people.
3. t1 plague in Ashkari Nomads → t8 plague in Kethani Empire (contact
   excitation) → t11 emigration from Kethani Empire → t14 border incident
   Kethani/Thornwall → t15 border incident Thornwall/Selurian.
4. t22 drought in Ashkari Nomads → t26 food shortage in Stormbreak Cliffs →
   t43 shortage in Obsidian Shore (upstream) → t46 famine in Obsidian Shore →
   t47 24 people flee Obsidian Shore.
5. t29 locusts in Amber Valley → t33 food shortage → t34 famine → t38 9
   farmers flee to Iron Peaks.

Mechanical chronicle (`--narrate <bundle> --narrator mechanical`, same seed),
the "because" passage of the first two moments:

> Famine strikes Thornwood, devastating Thornwall Confederacy (turn 3), because
> Supply shock: food in Thornwood (turn 3), because Thornwood is occupied by
> The First Warband of Ashkari Nomads (turn 0), because The Fight for
> Thornwood: Ashkari Nomads (7) vs Thornwall Confederacy (4) at Thornwood:
> attacker_wins. Losses 1/1 (turn 0), because Ashkari Nomads goes to war with
> Thornwall Confederacy, seeking conquest of Thornwood (turn 0). ...
>
> Thornwood lost 40% of its population over 7 turns (turn 6), because Famine
> strikes Thornwood, devastating Thornwall Confederacy (turn 3, as told above).
> Amber Valley lost 33% of its population over 12 turns (turn 11), because
> Famine strikes Amber Valley, devastating Kethani Empire (turn 9), because
> Supply shock: food in Amber Valley (turn 9), because Amber Valley is occupied
> by The First Warband of Thornwall Confederacy (turn 6), because The Fight for
> Amber Valley ... (turn 6), because Kethani Empire goes to war with Thornwall
> Confederacy, seeking tribute (turn 0, as told above).

## Gate

Subset profile, `--parallel 2`, base `cf13f87` and branch: both **PASS**
(artifacts PARTIAL and determinism SKIP are informational, as on base).
`validation_compare`: **NO REGRESSION**, and the two validation reports are
identical except for their batch path: every oracle (regression, arcs,
artifacts, era, needs, cohort, community) and every metric is unchanged,
because no oracle reads the event timeline and the simulation is identical.

Tests: `pytest -m "not slow" -n 2` 5,468 passed, 3 skipped, 1 failed
(`test_contact_ledger.py::test_save_load_round_trip_continues_identically`,
which fails identically on the base until its pending fix lands; base: 5,450
passed). Viewer: 166 tests, lint and build pass. Rust is untouched (no
`cargo test` needed).

## API for later work

Epidemiology (SEIRS) and other systems can record provenance the same way:

```python
from chronicler import provenance as prov
ev = Event(..., region=region.name)          # stamp the region
prov.cite(ev, prov.recall(world, prov.key("pandemic", source_region)))  # exact cause
prov.remember(world, prov.key("pandemic", region.name), ev)   # stand for a state
prov.open_episode(world, "famine", region.name)              # latest report of a condition
prov.observe_now(world, ev)        # only for same-phase chains that must resolve in order
```

Add a `CAUSE_RULES` entry for state-derived causes, a `_register` branch for
the keys the event stands for, and a `CHRONIC` entry for a condition that
reports every turn. Keep the contract above: read state only, never caches.

## Notes and limits

* Analytics that count event types (`--analyze` firing rates) now count
  supply-shock and agent-pattern episodes, not per-turn reports.
* Memory streams (narration context) see the folded timeline and the end events.
* Some emitters still carry no causes (civ actions such as `develop` or
  `trade` are choices; drought, earthquake and locusts are weather; leader
  deaths of old age).
* Very long chronic conditions are real: in agent modes many grain regions
  run below full food sufficiency for most of a run (see
  `extinction-fix-2026-10.md`), so a famine or shortage episode can stay open
  for a hundred turns. Recurring famine strikes are cited by their latest
  tick, which carries that turn's causes, not by the onset.
