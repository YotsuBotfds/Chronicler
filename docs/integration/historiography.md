# In-world historiography

Branch `feat/historiography`, based on `integrate/wave-5` at `b1b3f2d` and
merged forward to `b7d9ced` (techniques on by default) before the identity
proofs; every comparison below is against `b7d9ced`. Code:
`src/chronicler/historiography.py` (the layer), hooks in `main.py` (switch,
per-turn observation, narration, bundle), `models.py` (the world slot and
the state sidecar), `curator.py` (contested bonus), `narrative.py` (prompt
block, mechanical passage), `bundle.py` (optional field), `live.py`. Viewer:
`viewer/src/lib/historiography.ts`, `viewer/src/components/phase75/InWorldAccounts.tsx`.

The world now keeps its own chronicles. Every civilization has a court
chronicler, and every faith with a standing temple has temple scribes. They
write down what happens to them, with their own biases, into archives that
sacks, conquest, fire, earthquakes, floods, plague and desecration destroy.
The narrator can tell the history the way the world's people remember it:

> As the Thornwall chronicles tell it: "In the glorious reign of Warchief
> Seren, at the Raid on Amber Valley the Thornwall host won the day: 3 of
> the Kethani fell, and none of ours." Though the Kethani chronicles say:
> "At the Raid on Amber Valley the Kethani host gave ground before the
> Thornwall in good order, losing none; ..."

The layer is **observational**. The simulation decides; the chroniclers only
read what happened. With the layer on or off, the simulation state, every
snapshot, the event timeline, the RNG streams, `state.json` and the
validation reports are byte-identical. Only the narration and the new bundle
field change ([Outcome identity](#outcome-identity)).

## Contract

* **Reads only.** `observe_turn(world)` runs in `execute_run` after each
  completed turn, after the snapshot is captured and before any checkpoint.
  It reads the world (civs, regions, relationships, governance, factions,
  faiths, temples, technique known-sets, battle and treaty records) and the
  turn's new timeline entries. It writes only into the slot. It builds none
  of the world's lookup caches (`civ_map`, `region_map`, trade-route caches,
  the history index, the technique practice map): it builds local dicts per
  turn. No simulation module imports it (a test pins the importers to
  `main`, `models`, `live`).
* **Deterministic, never a simulation stream.** Every choice is a draw from
  `stable_hash_int("historiography", seed, ...)` (`_unit`): the scribe's zeal
  (per chronicler and reign), omissions, and which copies survive a loss. The
  module imports neither `random` nor `numpy` (tested). `random.getstate()`
  and NumPy's global state are unchanged across an observation (tested).
* **Provenance.** Every account tells one real event (its `event_id`). Bias is
  a list of recorded transforms of that event. A blamed cause is another real
  event from the provenance graph, and the chronicler must hold a surviving
  account of it. No account or event is ever invented.
* **Identity.** Chroniclers are keyed by civilization index (`court:<i>`) or
  faith id (`temple:<faith id>`), archives by owner (`archive:<chronicler>`),
  accounts by `<chronicler>/<event_id>`. Regions are stored as indices into
  `world.regions`; the export adds names.

## Who writes, and what

**Court chroniclers.** A civ gets one at the first observed turn it holds
land; it falls silent while the civ holds none. Its archive stands in the
civ's capital and moves with it.

**Temple scribes.** Each faith in `belief_registry` with an active temple
gets temple scribes, and its archive stands at the faith's most prestigious
temple. They chronicle the events of civs whose majority faith is theirs.
While no temple stands they are silent and their archive is homeless.

**Selection.** An event is chronicled by the chroniclers of the civs it
concerns: its actors, its `civs`, and the controller of its region.

* **Importance.** Courts take events of importance 6 or more (5 for unrest,
  crises and rulers). Temples take 7 or more. An unclassified type needs 7.
* **Guilds** (`--guilds`, since `fix/movements-narration-polish`): from
  importance 3, so they sort after a turn's other picks. A guild formed, a
  privilege won or a guild charter granted is glory (a loyal court praises
  the ruler); a privilege lost or a guild charter repealed is the ruler's
  decree (`decree`: a loyal court upholds it, "By the just decree of ...",
  a disaffected one condemns it); a guild rising as a movement is disgrace.
  `movement_founded`, `movement_reform` and `reform_repealed` count as guild
  events only for a guild movement or a guild charter, read from the
  movement record (`_Turn.guild_stance`). In three narrated runs (template
  42 500 turns, procedural 48 x 10 seed 7 400, template 1234 300) this
  adds 18 / 88 / 10 accounts and changes no earlier one.
* **Skipped.** Routine actions and bookkeeping, `*_ended` closings, episode
  ticks and repeats, and a campaign `war` record without an outcome are not
  chronicled.
* **Repeats.** A recurring hostility, disaster or treaty with the same type,
  parties and region is not retold within 10 turns.
* **Cap.** Each chronicler writes at most 8 accounts per turn, the most
  important first.

**Stance.** Each event is classified per civ (`_stance`):

| Stance | How it is assigned |
| --- | --- |
| `victory` / `defeat` | Battle outcome (the `BattleRecord`, or the outcome token). Two-sided events: occupation, annexation, conquest, vassalization, union and twilight absorption, raids, hostages, liberation, secession. Peace treaties use the `TreatyRecord` winner. One-sided losses: army destroyed, capital lost, general fallen, scorched earth, techniques lost. |
| `stalemate` | Indecisive battles. |
| `aggression` / `grievance` | War declarations and hostilities: embargoes, sieges, border incidents (mutual), broken treaties, blockades. Also the subject's side of a vassal rebellion. |
| `disaster` | Famine, plague, epidemics, drought, earthquake, flood, wildfire, locusts, flight, demographic crisis, ... |
| `disgrace` | Rebellion, revolt, civil war, PSI crisis, coup, legitimacy and succession crises, twilight, collapse, tech regression, failed ambitions. Also the exposed sponsor of a proxy war, and the overlord of a rebellious vassal. |
| `glory` | Great persons, cultural works, discoveries, era advances, inventions, artifacts, fulfilled ambitions, enacted institutions, ... |
| `ruler`, `faith`, `peace`, `neutral` | Leader deaths, religious events, treaties, everything else. |

## Biases

The court's temper comes from simulation state when it writes:

* **Loyalty.** The ruler's legitimacy (`CivGovernance.ruler_legitimacy`; the
  stability/100 proxy with governance off) decides it. **Loyal** at 0.55 or
  more. **Disaffected** below 0.35 or during a faction power struggle.
  Neutral otherwise. On the 200-turn defaults, 48% of living civ-turns read
  loyal and 4% read disaffected by legitimacy.
* **Zeal.** A per-chronicler, per-ruler draw in [0, 1): each reign gets its
  own scribe.
* **Clergy.** The clergy faction's influence: from 0.30 the court sees the
  gods' hand in disasters.
* **Grievances.** Disposition toward each civ (hostile 3, suspicious 1.5,
  friendly -1, allied -2), plus the diplomacy memory's grievance stock (up
  to 3), plus 3 at war.

| Stance | Court | Temple |
| --- | --- | --- |
| victory | `inflate`: enemy battle losses x (1.5 + 1.5 zeal), at least +1, or "a great triumph"; `minimize` own losses; `praise` the ruler if loyal | `divine` favour; `praise` the ruler of a pious civ (clergy 0.25 or more) |
| stalemate | from zeal 0.40, `claim` victory (and inflate) | `divine` trial |
| defeat | loyal: `omit` with p = 0.30 + 0.40 zeal; otherwise `minimize` (own losses x (0.4 + 0.3 (1 - zeal)), or a type-specific phrase: "the garrison withdrew to fight another day", "an honoured guest, not a captive", ...) and `blame`; `condemn` the ruler if disaffected | `divine` trial |
| disaster | clergy 0.30 or more: `divine` wrath at the ruler's impiety (disaffected), at a faithless enemy of another faith, or at the people's sins; otherwise `blame` (a recorded link only), or `condemn` if disaffected | `divine` wrath at the ruler (clergy weak) or at heretics |
| disgrace | loyal: `omit` with p = 0.40 + 0.40 zeal, else `blame`; disaffected: `condemn` | `divine` wrath |
| glory | `praise` if loyal | `divine` favour, `praise` if pious |
| ruler (death) | loyal: "the realm mourned a great ruler"; disaffected: "few mourned" | `praise` or `condemn` |
| aggression | `blame`: a pretext, the latest held deed of the civ acted against; a loyal court omits its own broken treaty with p = 0.5 | - |

**Blame** names a different real cause (`_pick_blame`):

1. **`relation: ancestor`.** First the event's recorded ancestors (the causes
   of its causes, up to 6 steps and 64 events) are searched for a deed of an
   enemy. The enemy must be its doer: declarer, attacker, taker, raider,
   embargoer, treaty breaker, or the land a sickness came from. The
   chronicler must hold a surviving account of that deed. The most resented
   enemy wins, then the nearest step.
2. **`relation: pretext`.** If no ancestor fits, the chronicler takes the
   latest deed of a resented enemy (grievance 1.5 or more; for an
   aggression, the target) among its own surviving accounts of the last 30
   turns. Natural disasters never take a pretext.

The account's `cited` list then holds the substituted cause instead of the
recorded ones. Unbiased accounts cite the recorded causes the chronicler
still holds.

## Archives

A loss episode strikes an archive when a turn's event hits its home:

| Cause | Trigger | Copy survives with |
| --- | --- | --- |
| sack | the region is occupied or annexed by another civ | 0.50 |
| conquest | the owner civ is extinguished (`civ_conquered`) | 0.25 |
| collapse | the owner civ collapses | 0.60 |
| absorption | the owner is absorbed (union, twilight absorption) | 0.60 |
| fire | wildfire in the region | 0.70 |
| quake | earthquake, supervolcano | 0.75 |
| flood | flood | 0.85 |
| plague | plague, epidemic, pandemic in the region | 0.97 |
| desecration | this faith's great temple destroyed or replaced | 0.50 |

At most one episode strikes per archive, cause and turn. A surviving account
survives an episode if any of its copies does: p = 1 - (1 - s)^copies, one
namespaced draw per account and episode. An archive keeps 1 copy, plus 1 per
writing technique its owner civ knows when `--techniques` is on (now the
default): writing +1, written law +1, printing +2, telegraph +1, so a
printing culture keeps 5. Lost accounts keep their text and record
`lost_turn` and `lost_cause`, so the viewer can show what was lost; the
narration treats them as lost. A chronicler cites only causes it still holds
(`holds`), so once an archive burns, later accounts cannot name what it held.
When a civ falls, its court falls silent and its archive suffers the
conquest. What the world remembers of its wars is the victor's version.

## Contested accounts

`export` marks an event **contested** when two or more of its accounts
diverge (`divergence`):

* `silence`: one tells it, another left it out;
* `lost`: one survives, another was destroyed;
* `outcome`: a stalemate claimed, or both sides claiming the victory;
* `magnitude`: different inflated or minimized claims;
* `blame`: different culprits or substituted causes;
* `divine`: the gods' hand seen by one and not the other;
* `ruler`: different verdicts on the rulers.

`telling(...)` turns a contested event into one narratable passage:

> As the Kethani chronicles tell it: "...". Though the Ashkari chronicles
> say: "...". No account from the Thornwall chronicles survives: their
> archive at Iron Peaks was emptied by plague (turn 56).

The narrator gets the two most divergent voices and one note on silence or
loss (a temple's loss only where nothing else survives). The viewer shows
all of them.

## Narration

* **Prompt.** With an `AccountIndex`, `NarrativeEngine` prompts gain an
  `IN-WORLD ACCOUNTS` block after the causal chains. It covers up to 3 events
  per moment (contested first, then the most important), each with up to 3
  voices: quoted text with its transform kinds, silences and losses. It
  instructs the narrator to present them as claims ("as the X chronicles
  tell it ..., though the Y records say ...") and never as fact. The truth
  stays in `EVENTS` and `CAUSAL CHAINS`.
* **Mechanical chronicle.** `mechanical_narrative` appends "In their own
  words: ..." with the tellings of up to 2 events. Each archive loss is told
  once per chronicle (like the chains' "as told above"). A temple's lost copy
  is noted only where no voice survives. This passage is also used when an
  LLM call fails.
* **Curator.** `curate(..., contested=...)` adds `1.0` per divergence kind
  (at most 3) to contested events, so moments where the accounts diverge are
  picked more often. `None` (the default) leaves curation exactly as before
  (tested).
* **Entries.** `ChronicleEntry.accounts` lists the account ids a narration
  drew on. It is omitted while empty.
* **`--narrate <bundle>`** uses the bundle's field when it has one
  (`--no-historiography` ignores it). Old bundles narrate exactly as before.
  The live viewer's "narrate this range" also uses the field when the loaded
  bundle carries it.

## Bundle field

`bundle["historiography"]` is added at the end and only when the layer is
on. Bundles without it keep their bytes. No version bump is needed: readers
that don't know it ignore it, and it carries its own `version`.

Abridged, from the final-head hybrid seed-42 run (the Thornwall archive keeps
two copies by then: Thornwall has learned writing):

```json
{"version": 1, "enabled_turn": 0, "counts": {"accounts": 405, "omitted": 9, "lost:plague": 30, "transform:blame": 21, ...},
 "chroniclers": [{"id": "court:2", "kind": "court", "name": "the Thornwall chronicles", "civ": 2, "civ_name": "Thornwall Confederacy", "faith": null, "founded_turn": 0, "active": true, "archive": "archive:court:2", "accounts": 141, "surviving": 89}, ...],
 "archives": [{"id": "archive:court:2", "owner": "court:2", "region": 1, "region_name": "Iron Peaks", "copies": 2, "status": "damaged", "losses": [{"turn": 34, "cause": "plague", "event_id": "34:epidemic:0", "region": 1, "copies": 1, "lost": 4, "survived": 51, "region_name": "Iron Peaks"}]}, ...],
 "account_columns": ["event_id", "chronicler", "turn", "stance", "transforms", "cited", "text", "lost_turn", "lost_cause"],
 "accounts": [["7:war:0", "court:2", 7, "victory", [["inflate", {"of": "enemy losses", "true": 1, "claimed": 3}], ["minimize", {"of": "own losses", "true": 1, "claimed": 0}], ["praise", {"ruler": "Warchief Seren"}]], ["0:war_declared:1"], "In the glorious reign of Warchief Seren, at the Raid on Amber Valley the Thornwall host won the day: 3 of the Kethani fell, and none of ours.", null, null], ...],
 "plain": {"court:0": ["0:war_declared:0"]},
 "contested": [{"event_id": "7:war:0", "divergence": ["blame", "magnitude", "ruler"]}, ...]}
```

`accounts` holds compact rows (`account_columns`, append only): every
biased, silent or lost account and every account of a contested event. An
uncontested account that tells its event plainly is listed by event id
under `plain`; its text is the event's own. On the 20-seed subset (200
hybrid turns) the field averages 148 KB (at most 260 KB), +2.6% on the
bundle.

**Viewer.** `Bundle.historiography?` and `NewChronicleEntry.accounts?` are
optional types. `lib/historiography.ts` decodes the rows by column name. The
AppShell event inspector gains an **In-world accounts** section for the
pinned event: each chronicler's version with its transform kinds,
silences, losses (the lost text struck through) and plain tellings, and the
divergence kinds when contested. Bundles without the field show nothing new.

## Persistence and the switch

`--historiography` / `--no-historiography`. New worlds use
`DEFAULT_ENABLED_FOR_NEW_WORLDS` (on), and live mode's new worlds follow it.
A supplied or resumed world keeps its own setting. An explicit flag switches
it: on starts the chronicles at that turn, off drops them.

The state lives on `WorldState._historiography` (a `HistoriographySlot`,
equality-neutral like the provenance counters, outside `model_dump`).
`WorldState.save`, `WorldState.load` and the compact checkpoint writer carry
it in a sidecar next to the state file: `state.json` ->
`state.historiography.json`. So `state.json` keeps its exact bytes, and
every resume path (CLI `--resume`, fork, interactive and live forks through
`world.save`) keeps the chronicles.

* **Old saves** (no sidecar) load with the layer off.
* **A stale sidecar** (another turn, or a cursor beyond the timeline) is not
  trusted: the chronicles restart at the loaded turn, with a warning.
* **Saving with the layer off** removes a stale sidecar.
* **Live mode** resumes from a client-sent state dict, so it has no sidecar
  and starts without chronicles.

Derived lookups (the event-id index, the account index, the repeat table)
are rebuilt from the state after a load. A resumed run writes exactly what
an uninterrupted one writes (tested).

## Default: on for new worlds

The layer is on by default because it meets the bar the task set ("costs
little and is well-tested") and changes nothing the simulation or its
gates read:

* **Outcome-neutral, proven.** `state.json`, snapshots, timeline, memories,
  agent events, RNG streams and validation reports are byte-identical with
  it on (below). AGENTS.md keeps *experimental simulation* features default
  off until qualified. Nothing here needs simulation qualification: no
  oracle, decision or stream can see it.
* **Cheap.**
  * About 4% run time on the 500-turn guard world (27.9 s against 26.8 s,
    three alternating runs each): observation plus sidecar checkpoints.
  * The bundle grows by 2.6% on the subset and stays within the 24 MB
    size-guard world (20.73 MB native, 23.61 MB no-Rust).
  * The sidecar is 243 KB per 200-turn run.
* **Tested.** 39 focused tests (in the offline lane), the frozen
  exact-trajectory oracles rerun with it on, base-commit identity in both
  agent modes, and three subset gates.

**What does change by default**, all of it narration:

* The bundle gains the field.
* Curated narration (`--narrator api|gemini|mechanical`, `--narrate`) can pick
  other moments, because contested events get a bonus.
* The prompt gains the accounts block, adding tokens per moment: at most 3
  events x 3 voices.
* The mechanical chronicle gains the passage.

`--no-historiography` restores the previous output byte for byte. The
frozen benchmark workloads (`scripts/benchmark_headless.run`) pin it off,
as they pin the other post-freeze defaults. One test runs them with it on.

## Outcome identity

1. **Frozen exact-trajectory oracles, with the layer on.**
   `test_frozen_oracles_hold_with_historiography_on` runs the three frozen
   corrected workloads with chronicles kept. It checks every turn's
   snapshot, events and narration hash, the ordered RNG trace and every
   artifact byte against the unchanged fixtures. The only additions are the
   bundle field and the sidecar. `test_governance_dormancy`,
   `test_performance_equivalence` and `test_turn_artifact_lifecycle` pass
   unchanged with the pin. No fixture changed.
2. **In-suite run identity.**
   * `test_flag_on_changes_no_simulation_output` (40 turns, mechanical
     narrator) checks every snapshot and every file except the narration.
     The bundle is identical apart from the narration fields.
   * `test_native_hybrid_run_is_outcome_identical_with_the_flag` does the
     same for a 20-turn native hybrid run.
   * `test_flag_off_never_runs_the_layer` forbids `observe_turn`, `export`
     and `AccountIndex` while off.
   * `test_observation_reads_only` checks that the world dump, random and
     NumPy state and the world caches are untouched.
3. **Against the base commit** (`scripts/historiography_identity.py`, a
   variant of `diplomacy_identity.py`). Base `b7d9ced` is exported with
   `git archive` and run with its own source on `PYTHONPATH`; same
   interpreter and native extension (built from this tree; no Rust change),
   `PYTHONHASHSEED=0`, `--narrator mechanical`. The set: template seeds 42,
   7 and 1234 (off 300 turns, hybrid 200), plus a procedural 48 x 10 seed 7
   (off 200, hybrid 120).

   | Comparison | agents off | hybrid |
   | --- | --- | --- |
   | base vs `--no-historiography` (`compare`) | 34 files, 0 differences | 38 files, 0 differences |
   | base vs default (on) (`compare --historiography`) | 34 files, 0 differences; 4 sidecars only in new; 4 `chronicle.md` narrations differ; 4 bundles identical apart from `historiography`, `chronicle_entries`, `gap_summaries` | 38 files, 0 differences; same |

   "Identical" covers `state.json`, the memory streams, `agent_events.arrow`
   and the bundle: world state, every history snapshot, `pruned_civ_stats`,
   the event timeline, named events, era reflections and metadata.
   `compare --historiography` also checks that every account, every cited
   cause and every chronicle entry's account id in NEW resolves.
4. **Subset gates** (20 seeds x 200 turns, hybrid, `--parallel 2`): base
   `b7d9ced`, the branch with `--no-historiography`, and the branch with
   `--historiography`. All three **PASS** with identical oracle statuses:
   arcs, cohort, community, era and needs PASS; artifacts PARTIAL (strict);
   regression FAIL (informational); determinism SKIP. The three
   `validate_report_subset.json` files and the gate decisions are identical
   once the one line naming the batch directory is normalized.

   | Comparison | Result |
   | --- | --- |
   | base vs off | 2,164 files, 0 differences |
   | off vs on | 2,164 files, 0 differences; 20 sidecars only in on; bundles identical apart from the narration fields |

## Results

| Check (Linux, Python 3.13, shared 4-core host) | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (extension built from this tree; compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | **5,883 passed, 3 skipped** (base `b7d9ced`: 5,844 passed, 3 skipped; +39 in `tests/test_historiography.py`) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -q -n 2`, slow included, as CI runs it) | **5,683 passed, 203 skipped** (the slow 500-turn bundle guard included) |
| `scripts/run_python_oracle_checks.py` (PR #19's guard line applied locally, not committed; the lane now includes `tests/test_historiography.py`) | **PASS**: 1,888 passed, 10 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O; 79 s of the 110 s budget |
| Viewer: `npm test -- --maxWorkers=2`, `npm run lint`, `npm run build` | 219 tests passed (+9), lint clean, build passes (the existing large-chunk warning remains) |
| 500-turn bundle-size guard (`seed=1, turns=500, civs=5, regions=10`, agents off) | native 20.73 MB with the layer (field 0.65 MB; 20.07 MB off); no-Rust 23.61 MB (field 0.77 MB; 22.84 MB off); the 24 MB guard holds on both paths and is unchanged (its comment records these sizes) |
| Run time (guard world, native, alternating on/off runs) | on 28.3 / 26.9 / 28.6 s, off 26.3 / 26.7 / 27.3 s (means 27.9 and 26.8 s, +4%), on a shared host at load about 10 |
| `cargo test` | not run: no Rust change |

**Per 200-turn hybrid run** (the 20-seed subset, defaults, flag on):

* **Volume.** 650 accounts by 8.8 chroniclers: 509 exported as rows and 141
  as plain. 189 contested events.
* **Transforms.** divine 184, condemn 179, praise 52, blame 38, minimize 28,
  omit 24, inflate 21, claim 0.8.
* **Accounts lost.** desecration 68, sack 24, earthquake 10.5, fire 9.9,
  flood 8.8, plague 5.3, absorption 4.5, conquest 3.1.
* **Contested events by divergence kind.** divine 140, ruler 127, lost 87,
  blame 30, magnitude 22, silence 14, outcome 4. Divine and ruler
  divergences are mostly temple scribes condemning rulers of weak clergy
  whom the court tells plainly.
* **Size.** The field averages 148 KB (at most 260 KB), +2.6% on the bundle.
  The sidecar averages 243 KB.

**Curator effect.** The curator merges events within 5 turns into clusters.
A 200-turn run makes fewer clusters than the default 50-moment budget, so in
the identity runs every moment is the same with and without the bonus; only
the prose changes. The bonus decides selection only when there are more
clusters than budget (longer runs, a smaller `--budget`), and it can move the
climax role.

## Seed 42 excerpts

From the final-head identity runs (`--narrator mechanical`, `PYTHONHASHSEED=0`).

**1. The mechanical chronicle**: hybrid, 200 turns, the first moment's
"because" passage and its new paragraph:

> Thornwall Confederacy takes High Priestess Cohortis hostage from Ashkari
> Nomads (turn 5), because The Raid on Iron Peaks: Ashkari Nomads (4) vs
> Thornwall Confederacy (10) at Iron Peaks: defender_wins. Losses 2/0 (turn
> 5), because Ashkari Nomads goes to war with Thornwall Confederacy, seeking
> conquest of Thornwood (turn 0, as told above). ...
>
> In their own words: As the Ashkari chronicles tell it: "At the Raid on
> Iron Peaks the Ashkari host gave ground before the Thornwall in good
> order, losing none; the fault lay with the Thornwall, as in turn 5, when
> Thornwall Confederacy imposed a trade embargo on Ashkari Nomads." No
> account from the Thornwall chronicles survives: their archive at Iron
> Peaks was thrown down by an earthquake (turn 125). As the Thornwall
> chronicles tell it: "At the Skirmish at Verdant Plains the Thornwall host
> held the field: 3 of the Ashkari fell, and none of ours."

The Ashkari lost 2 soldiers at Iron Peaks and the Thornwall none. The
Skirmish at Verdant Plains (`1:war:0`) was a stalemate in which the Ashkari
lost 1. A zealous Thornwall scribe claims it as a victory (`claim`) and
triples the Ashkari dead (`inflate` 1 -> 3).

**2. A contested battle** (hybrid, `7:war:0`, divergence blame, magnitude,
ruler):

* **Recorded chain:** [t7] The Raid on Amber Valley: Thornwall Confederacy
  (8) vs Kethani Empire (4): attacker_wins, losses 1/1 <- [t0] Kethani
  Empire goes to war with Thornwall Confederacy, seeking tribute.
* **Kethani chronicles** (minimize, blame): "At the Raid on Amber Valley the
  Kethani host gave ground before the Thornwall in good order, losing none;
  the fault lay with the Thornwall, as in turn 6, when Thornwall
  Confederacy takes Chancellor Pearlwind hostage from Kethani Empire."
  *Cites* `6:hostage_taken:0`, a real Thornwall deed it holds, instead of
  its own declaration of war.
* **Thornwall chronicles** (inflate 1 -> 3, minimize 1 -> 0, praise): "In
  the glorious reign of Warchief Seren, at the Raid on Amber Valley the
  Thornwall host won the day: 3 of the Kethani fell, and none of ours."
  *Cites* the true root, `0:war_declared:1`.

**3. The victor's version** (agents off, 300 turns, `9:civ_conquered:0`):

* **Recorded chain:** Kethani Empire is extinguished (t9) <- Frostholm
  Tundra is ceded by treaty (t9) <- Frostholm Tundra is occupied (t4) <- The
  Fight for Frostholm Tundra (t4) <- Kethani Empire goes to war with
  Thornwall Confederacy, seeking tribute (t0).
* **Kethani chronicles**, written but **lost** when Amber Valley was sacked
  that turn (15 of 23 accounts gone, then 6 of the last 8 in the conquest):
  "Kethani Empire is extinguished; ...; the spirit of the realm endured; the
  fault lay with the Thornwall, as in turn 4, when Frostholm Tundra is
  occupied ...; such was the misrule of Archon Ulveth."
* **Thornwall chronicles**, surviving: "In the glorious reign of Warchief
  Seren, Kethani Empire is extinguished; its last land falls to Thornwall
  Confederacy, a great triumph for the Thornwall."
* **Narrated:** "As the Thornwall chronicles tell it: "...". No account from
  the Kethani chronicles survives: their archive at Amber Valley was sacked
  (turn 9)."

## What was cut, and limits

* **Scribes read their own archive only.** No copying between archives, no
  captured archives carried off by a conqueror, no later historians who
  rewrite surviving accounts. Chroniclers do not revise old entries when a
  new ruler takes the throne.
* **Rulers come from the current reign.** Ruler names and loyalty are those
  of the reign at the end of the turn. A ruler who died that turn is
  mourned as "the late ruler".
* **Religion is read coarsely.** Temple scribes follow civ majority faiths
  and the great temple. Agent-level belief and persecuted minorities are not
  tracked per account. Without agents, majority faiths stay those of the
  founders.
* **The prose is mechanical.** Texts are templates over the event's own
  description. Inflation and minimization change casualty numbers and
  qualifiers, not event identities. Agents-off battles are small (a few
  soldiers), so the inflated figures are small too.
* **Calibration is illustrative.** The bias probabilities, thresholds and
  survival rates shape narration only. Plague in the capital is the most
  frequent loss (often several outbreaks per run with epidemiology on), so
  plague is mild (0.97 per copy) and one episode per cause and turn.
  Temple desecration is the largest single loss source on the subset (68
  accounts per run), because temples are often replaced.
* **No retroactive chronicles.** Old saves and bundles get no accounts. A
  world switched on mid-run is chronicled from that turn.
* **Not run.** The full 200-seed gate (not needed: the simulation is
  unchanged and the subset reports are identical) and live-mode browser QA.
