# Permanent faith identity (2026-10)

Branch `feat/permanent-faiths` from `main` `7c44ed8` (PR #59). The longer-term
fix named by [population-entities.md](population-entities.md) item 4.

Code: `src/chronicler/faiths.py` (new: the table, the slot <-> permanent
mapping, older runs), `models.py` (`FaithRecord`, `WorldState.faiths`),
`world_gen.py`, `religion.py` and `agent_movements.py` (founding, release,
the movement and reform records), `gp_agendas.py`, `governance_runtime.py`,
`scholarship.py` (objectives and seats), `infrastructure.py` (temple
records), `historiography.py`, `languages.py`, `narrative.py`,
`narration_context.py`, `narration_provenance.py`, `narration_inputs.py`,
`run_checkpoint.py`, `simulation.py`; viewer `src/lib/faiths.ts` (new),
`src/components/systems/FaithsPanel.tsx` (new), `src/lib/movements.ts`,
`src/lib/systems.ts`; scripts `turn_speed_identity.py` (`--faith-ids`),
`cities_identity.py`, `checkpoint_identity.py` (a recycling case),
`third_wave_controls.py`, `build_movements_fixture.py` (`--faiths`). Tests:
`tests/test_permanent_faiths.py` (new, oracle lane chunk `faiths`),
`viewer/src/lib/__tests__/faiths.test.ts` (new), the systems panel tests.
No native code changed: the runtime keeps slots.

## 1. The problem

A faith's native id (`Belief.faith_id`; the agents' `belief` byte) is one of
at most 16 slots (`religion.MAX_FAITHS`). Schisms fill the registry in the
first turns of most worlds; after that a sect that breaks away
(`agent_movements._schism`) takes the slot of a faith that no agent holds and
nothing references (`_extinct_faith_slot`). PR #51 made in-force and
remembered tolerations and living movements hold their slot, so a recycled
slot no longer inherits an old toleration. But every record that outlives
its turn and names a faith by slot (a movement's faith, a repealed
toleration, a temple's destruction, a chronicler, a word) then names two
unrelated churches over a run: the viewer, the narrator and the in-world
layers read the later church's name into the earlier records.

## 2. Audit

Every place a faith is named by slot on `main`, and what it is now.
*Live*: read for the current turn (or protected while it reads), where the
slot is the right identity. *Historical*: names a particular religion beyond
its turn.

| Where | Field | Kind | Now |
| --- | --- | --- | --- |
| World state | `belief_registry[].faith_id` | live registry | slot; the permanent table `faiths` beside it |
| | regions' `majority_belief`, `conversion_target_signal`, `schism_convert_from/_to`, `persecuting_faith` | live, per turn | slot |
| | civs' `civ_majority_faith`, `previous_majority_faith` | live, per turn (and protected) | slot |
| | temples' and pending builds' `faith_id` | live while the infrastructure record exists (protected) | slot |
| | `_prev_belief_distribution` (conversion deltas) | live, one turn | slot |
| Movements | `Movement.faith` | live while the movement lives (protected), historical after | **permanent** |
| | `schism_from`, `schism_to`, a schism's `successor` | historical | **permanent** |
| | `Reform.faith` (toleration) | live while in force or remembered (protected), historical after | **permanent** |
| | movement/reform texts (`_demand_text`, `reform_name`, `movement_history`) | historical text, named through the current registry | named by permanent id |
| Objectives | `GovernanceAmbition.conversion_faith_id`: ruler conversion ambitions (up to 40 turns) and great-person spread-faith agendas (up to 25) | **live, not protected** | **permanent** (§5) |
| Scholarship | `Seat.faith` (`--scholarship`) | **live for the seat's life, not protected** | **permanent** (§5) |
| Events | `temple_destroyed` "Temple of faith N destroyed/replaced in R" | historical | **permanent id** in the text |
| | Schism, Reformation, Persecution, pilgrimage | names, not ids | unchanged |
| | agent events (`AgentEventRecord.belief`, `agent_events.arrow` `belief`) | historical, native | slot; resolve by the table's tenure (`holder_at`, an agent event of turn T reads the end of T - 1) |
| Historiography | chronicler id `temple:<N>`, `Chronicler.faith`, account and archive ids built on it, a temper's faith | historical | **permanent** (a church in a recycled slot has its own chronicler) |
| Languages | `Word.ref` of faith words, `LanguagesState.faiths` keys, export `faiths[].faith` | historical | **permanent**; a vanished faith stays named |
| Narration | `event_text`'s temple names, `NarrativeEngine._faiths`, `_reform_label` | final registry by slot | permanent names |
| Provenance (PR #56) | `L.f<N>` (faith words), `temple:<N>/e<i>` (accounts), the names table | ids follow the layers | permanent |
| Audit | `narration_audit` names check (`EntityUniverse`) | live registry names | every faith's name |
| Bundle | `world_state` live fields above | final live state | slot (correct at the end) |
| | `history[n].agent_movements.reforms[].faith` | historical (snapshot) | **permanent** |
| | `world_state.faiths` | | new |
| Viewer | reform names (`lib/movements.ts`), from the final registry | historical | permanent identity: name and founding turn |
| | infrastructure `faith_id`, `civ_majority_faith` types | final live state, not shown | slot |
| Checkpoints (PR #54) | the pickled run graph (world, history) | as above | the table travels with the world |
| | `checkpoint_replay` JSON envelope | `WorldState` schema | the table is a field |
| Validation sidecars | needs, relationships, memory signatures, aggregates, community and economy summaries | no faith ids (co-religionist bonds are a bond type) | unchanged |
| Native | pool beliefs, region faith fields, reform table `faith`, movement table `convert_from/_to`, formation belief census | live | slot; Python converts at the boundary |
| Other live readers | conversion signals, persecution, martyrdom, pilgrimages, holy war, co-religion diplomacy, secession faith mismatch, temple tithe, inquisition, initial agent beliefs, co-religionist bonds | live, per turn | slot |

## 3. Design

**The table.** `WorldState.faiths: list[FaithRecord]`, index = permanent id
(the house rule: identity is the index in a list that never reorders). A
record holds `name`, `founded_turn`, `civ` (the founding civilization,
`Belief.civ_origin`), `origin` (`founding`, `schism` from the religion path,
`sect` from a movement, `unrecorded` for a faith added outside the founding
paths), `slot` (held or last held), `released_turn` (the turn its slot passed
to another faith; absent while it holds it), `parent` (permanent id it broke
from), `region`, `movement` and `leader` (a sect's movement and its leader at
the schism) and `doctrines`. Optional fields are omitted while unset. Id 255
is never used (the no-faith sentinel; a reserved empty record would take it
after ~240 recycles in one world).

**Founding and release.** World generation records the founding faiths in
registry order (id == slot == civ index). `religion.detect_schisms` and
`agent_movements._schism` record each new faith (`faiths.found`) right after
`fire_schism`; a recycle first releases the vanished faith
(`faiths.release`). Faiths are founded in slot order until the registry
first fills, so **every faith founded before the first recycle has permanent
id == slot**: a run without a recycle writes exactly the faith numbers it
wrote before. The mapping changes only at a recycle.

**The boundary.** `uid_of(world, slot)` (the faith holding a slot now),
`slot_of(world, uid)` (the slot a faith holds now, None once released),
`live_slot(world, value)` (`slot_of` for a faith; a value that is not a
faith, such as None, the 255 sentinel or a temple's -1 placeholder, as it
is), `same_faith(world, uid, slot)` (values that are not faiths compare raw,
as slots did), `name_of`, `names`, `holder_at(table, slot, turn)`
(historical resolution: the end of a turn). Records store permanent ids;
per-turn comparisons with live slot fields go through `same_faith` or
`live_slot`; the native tables (`movement_table`, `reform_table`) get slots.
`faiths.ensure(world)` runs at the start of every turn and after loading: it
gives a world without a table its table (§4) and records a registry faith
added outside `found` (a test fixture); in a recorded run it changes nothing.

## 4. Older runs

**Rebuilding the table** (`faiths.reconstruct`, `lib/faiths.ts`
`reconstructFaiths`, the same algorithm). From the final registry and the
run's `Schism` events, backwards: each schism names its new faith (and, for a
sect taking a vanished faith's slot, "in place of the vanished '...'"); the
new faith is dated and, where it took a slot, the vanished faith becomes the
slot's earlier holder. What holds a slot at the start is a founding faith
when its name is the world-generation name ("Faith of <civ>", slot = civ
index). Parents are matched by name among the faiths holding a slot then.
**Live faiths keep permanent id == slot** and the vanished ones get ids after
them, in the order they gave up their slot: every live reference of an older
save stays exact and a resumed run behaves as before. A faith whose founding
is in no event (a trimmed timeline) or a schism the parser cannot read marks
`legacy="unresolved"`: an older record naming its slot may mean an earlier,
undetermined faith. Rebuilt from a recorded run's own events, the table
names the same faiths, foundings and releases as the recorded one (the
procedural seed-42 fixture, every recycle test).

**Mapping references.** Only references to a recycled slot change: each is
resolved at the turn it was written (a movement's faith at its end, its
schism fields at the schism, a toleration at its enactment, a snapshot row of
turn T at T - 1, a temple event at its turn, a seat at its founding, an
objective at its declaration, a chronicler at its founding, a word at its
coining).

* **State files** (`WorldState.load`) and **checkpoints of an older build**
  (`run_checkpoint.read_checkpoint` with `--resume-allow-mismatch`; the
  pickled world has no `faiths` attribute): `ensure` rebuilds the table and
  maps the world's records; a checkpoint's history snapshots too. A
  checkpoint written by this build carries the table and is left as written.
* **Bundles** read for narration (`narration_inputs.from_bundle`, used by
  `--narrate` and live range narration): `faiths.upgrade_bundle` adds
  `world_state.faiths` and maps the records, the snapshots' reform rows, the
  temple texts, the temple chroniclers' faith, the faith words (listing every
  faith a word names) and the objectives. Chronicler ids such as `temple:4`
  are kept: accounts and provenance cite them.
* **The viewer** rebuilds an older bundle's table on load (once per bundle)
  and resolves each slot reference at the turn its row was written.

## 5. Corrections

Two kinds of live state held a faith's slot across turns without
protecting it, so after a recycle they read the new church:

* **Conversion objectives** (`conversion_faith_id`): a great person's
  spread-faith agenda preached (set the region's conversion signal) for the
  church that took his faith's slot and could be fulfilled by its believers;
  a ruler's conversion ambition could be satisfied the same way. Now they
  name the faith by permanent id: an agenda finds the slot its faith holds
  (none once released: the prophet has nothing to preach), observations are
  made by permanent id.
* **Seats of learning** (`--scholarship`, default off): a seat's scholars'
  faith; under a church that took that slot and persecuted from it, the
  seat counted as the persecutor's own. Now `_persecuted` compares permanent
  ids (a vanished faith is outside every ruler's).

Tests reproduce each with a control that reads the stored value as a slot
(main's semantics): the prophet preaches for the new church and the agenda is
fulfilled; the ambition's predicate is converted by the new church's
believers; the seat is not persecuted.

Records corrected by the same change (no simulation effect): a restoration
movement's demand and `reform_name` named a repealed toleration through the
current registry; narration named a destroyed temple by the final registry;
a church in a recycled slot reused the vanished faith's temple chronicler
(its draws and name); the languages layer retired and recoined faith words
only when the slot's name changed, so a sect reusing a vanished faith's name
inherited its words (now the vanished faith's words are retired at its
release and the sect is named afresh), and the exported list dropped the
vanished faith's name.

**Measured.** Neither correction changes a decision in any world run for
this change: the 80 recycling worlds of §6 (40 with the defaults, 65 slots
given up; the same 40 with `--scholarship`, 54) and the turn-speed matrix
(with and without `--scholarship`) are equal to `main` in every simulation
output, so no objective or seat read a recycled slot there. A probe of
`main` over the 40 default worlds counted, after each recycle it detected
(one whose name changed),
the live references still on the old slot: 0 open agendas, 0 pending
ambitions, 0 preaching turns, 0 objectives completed (scholarship off). The
references are short-lived (agendas 10-25 turns, ambitions 20-40) and a
faith must lose every believer and every protected reference in that time.
A temple school cannot meet the case at all: its temple's `faith_id` keeps
the slot from being recycled while the temple stands, and the school falls
with its temple.

**A regression found and fixed on the branch** (not a correction: `main`
never had it). The first version mapped every recorded value as a
permanent id, including values that are not faiths. `slot_of(255)` is None,
so a temple school whose temple was built without a faith (`faith_id` 255,
or the -1 placeholder) found no temple and fell, where `main` compares 255
with 255 and keeps it. The `--scholarship` recycle arm caught it: template
seed 51 (no recycle) closed the Temple School of Thornwood at turn 205 and
diverged from there (88 files), procedural seed 44 likewise (68 files).
`live_slot` and `same_faith` now pass such values through unchanged (commit
`66f3072`). The other call sites never see one: a spread-faith agenda needs
a faith, a toleration of no faith is not enacted, and the recycling check
only looks for registry slots. Both worlds then match `main` (procedural
44 gives up four slots and differs only in its languages faith list). Test:
`test_a_temple_built_without_a_faith_keeps_its_school` (255 and -1, with
the mapped-as-id control).

## 6. Identity

Simulation state and decisions are unchanged: every output other than the
new faith fields and the two observational layers is byte for byte equal to
`main`'s, measured as below. Linux, Python 3.13.17, `PYTHONHASHSEED=0`,
`RAYON_NUM_THREADS=1`, one release extension (`maturin develop --release
--locked`, SHA-256 `da65b716...cf67`; the Rust is `main`'s, unchanged) for
both sides; `main` run from an exported `7c44ed8` tree, the branch from an
exported tree of `66f3072` (the final simulation code; everything below,
and the gates). Earlier passes on `2ec180a` and `fefc2ac` gave the same
results wherever scholarship is off; with `--scholarship` they found the
regression of §5.

**The normalisation** (`turn_speed_identity.py compare --faith-ids`, class
`FaithProjection`): the new run's own `faiths` table is dropped and every
field that carries a permanent id since this change is projected back to
the slot that faith held (`table[id].slot`): movements' `faith`,
`schism_from`, `schism_to`, a schism's `successor`; tolerations' `faith` in
the world state and in the history's reform rows; `conversion_faith_id` of
agendas and ambitions; seats' `faith`; the `Temple of faith <id>` texts; the
temple chroniclers' `temple:<id>` ids (wherever they occur) and `faith`; the
faith words' `ref` and the languages' faith keys. Nothing else is touched;
each case prints how many values each field changed and, for a file that
still differs, which of its parts.

**The turn-speed matrix** (9 cases: off and hybrid template seeds 42 and 7,
hybrid 1234, procedural 48 x 10 hybrid 42 and off 7, scaled 22k and 52k
agents): 399 files, **0 differences**. No case recycles a slot (at most 16
faiths, none released): the projection only drops the table. With
`--scholarship` on every case: 399 files, 1 difference, the bundle's
`languages` part of `hybrid_s1234`, which then gives up one slot (the
vanished faith stays listed, below).

**Recycling worlds** (the probe worlds, hybrid with validation sidecars):
template seeds 42-61 x 500 turns and procedural 32 x 10 seeds 42-61 x 300
turns, each with the defaults and with `--scholarship`: 80 worlds, 17,120
files (261 per template world, 167 per procedural one). Slots given up:
defaults 65 in 26 worlds (template 11 in 7, procedural 54 in 19), scholarship
54 in 26 (template 11 in 8, procedural 43 in 18). After the projection
**every** `state.json`, `agent_events.arrow`, validation sidecar (needs,
relationships, memory signatures, per-turn aggregates, community and
economy summaries), `chronicle.md`, memory file, and every bundle part but
two are equal in all 80 worlds: the event timeline (temple texts included),
the history snapshots, the world state, named events. No world without a
recycle differs at all. The parts that differ, in the 52 worlds with a
recycle, are the observational layers, as the change intends:

| part | worlds (defaults / scholarship) | why |
| --- | ---: | --- |
| bundle `languages.faiths` | 26 / 26 | a vanished faith stays listed by its own name (its retired words name it) |
| bundle `languages` words, languages' change counts, sidecar `state.words` / `state.languages` | 4 / 2 | a sect that reused a vanished faith's name inherited its words (no retirement when the slot's name did not change); now the vanished faith's words are retired at its release and the sect coins its own, which then drift with the language |
| bundle `historiography` accounts and archives, sidecar `state.accounts` / `state.archives` | 4 / 2 | a temple chronicler of a church in a recycled slot is `temple:<permanent id>`; its identity-keyed draws (zeal, archive survival) differ from those of the `temple:<slot>` id it had |

**Checkpoints** (`checkpoint_identity.py`, every checkpointed run against
its straight run, then every resume against it): the recycling world
`proc32_hybrid_s42_recycling` (new case: procedural 32 x 10 seed 42, 200
turns, slots recycled at 37, 100, 134 and 168, resumed at 19 turns on both
sides of each), `hybrid_s42` (every turn of 60) and `proc32_hybrid_s11`
(every turn of 40): 117 resume points, 4,686 files, **0 differences**;
checkpointing changes nothing (201 files). A checkpoint written by `main`
(procedural seed 42, turn 50, after the recycle at 37) resumed by the branch
with `--resume-allow-mismatch` rebuilds the table; to turn 80 every file
equals `main`'s straight run after the projection except the resume label
in the bundle's metadata and the languages' faith list (the vanished faith
named).

**Full gates** (the corrections of §5 are live-logic changes):
`m53b_run_validation.py --profile full --parallel 3
--require-strict-regression` on the final tree, against `main`'s reports
from the mine-soil ordering gates (needs method 6, cohort method 3).

* **Template 200 x 500: PASS** (strict regression), comparator **NO
  REGRESSION**, every metric delta 0.0. The batch manifest's validator inputs
  (every input but the bundle, agent events included) are identical to
  `main`'s in all 200 worlds. The gate worlds founded 3,329 faiths and gave
  up 129 slots in 84 worlds. 20 movement or reform records name a faith that
  has since given up its slot (under slot numbers they would name the later
  church), and no open conversion objective names one at the end.
* **Procedural 100 x 300**: queued behind another full gate on the shared
  machine; not run at this commit.

## 7. Viewer

* `lib/faiths.ts`: `faithTable(bundle)` (the recorded table, or the rebuilt
  one for an older bundle, cached per bundle), `resolveFaith` (an older
  bundle's slot at the turn a row was written), `faithLabel` ("Faith of X
  (Reformed) (founded turn 37)"), `faithsKnownAt`, `slotSharers`,
  `successorInSlot`, `faithEvents`, `templeEventText`.
* **Faiths tab** (systems panel, present for a bundle with the table or an
  older one whose record holds a schism): tiles (founded, holding a slot,
  vanished, slots reused) and every faith known at the scrubbed turn with
  its founding turn, origin (founding faith of a civ, a schism in a region,
  a movement's sect and its leader), the faith it broke from, its slot
  (marked shared when another church held it by then) and its status
  (holds the slot, or vanished and which church took the slot when);
  selecting one lists its schism, reformations and temples. An older bundle
  says its identities were rebuilt and how many could not be traced.
* **Movements tab**: lasting reforms name a toleration's faith by name and
  founding turn (an older bundle's slot read at the row's turn); a sect's
  note names its church and, after a schism, the church it became.
* As-of semantics (PRs #45, #49): faiths founded after the scrubbed turn are
  not shown, a release is shown only from its turn, a movement's church is
  the one it broke from until its schism. Lazy loading (PR #50): the faith
  library is its own 4.89 kB lazy chunk, loaded with the systems and
  languages panels (the systems panel passes a "has a faith record" flag so
  the entry does not import it); the systems chunk grows from 90.76 to
  95.12 kB and the entry chunk from 308.14 to 308.33 kB (+190 B).
* **Languages panel**: faith words are glossed by the faith's name and
  founding turn.

## 8. Tests

On the final tree (`66f3072`, the release extension above):

* `tests/test_permanent_faiths.py` (new, 18 tests; oracle lane chunk
  `faiths`): the founding table, a recycle naming two churches, `holder_at`,
  `ensure`, the reserved id 255, a toleration through a later recycle, temple
  texts and their narration, the three corrections each with a control that
  reads the stored value as a slot, values that are not faiths (the
  sentinel and the temple school of a faithless temple, 255 and -1, with a
  mapped-as-id control), a recycled slot's temple chronicler, an older save
  rebuilt and mapped, untraceable faiths marked, an older bundle upgraded,
  checkpoints of this build and of an older one. `tests/test_agent_movements.py`
  (the schism tests now expect the sect's permanent id and its slot) and
  `tests/test_geography.py` (the template digest leaves out the table, which
  is asserted on its own) were updated.
* Python, native: not slow 6,687 passed, 3 skipped (526 subtests); slow 12
  passed, 3 skipped. `scripts/run_python_oracle_checks.py`: PASS in 124.4 s
  (`faiths` chunk 18 passed). No-Rust lane (the extension hidden behind an
  import blocker): 6,430 passed, 261 skipped.
* `cargo test --locked` (`CARGO_PROFILE_TEST_DEBUG=0`): 1,053 passed, 2
  ignored. The Rust is `main`'s; no native struct changed, so `persist.rs`
  has no new field.
* `python -m chronicler.narration_audit`: a mechanical narrated run of the
  recycling world (procedural 32 x 10 seed 42, 200 turns): 34 entries,
  1,648 facts, 687 spans, 752 sentences, 0 uncited, **no flags**. `main`'s
  bundle of the same world narrated by the branch (`--narrate`, table
  rebuilt): the same 34 narratives, word for word, and no flags (before
  the audit rebuilt an older bundle's table as the narrator does, it raised
  3 false `unsupplied_name` flags).
* Viewer (`npm ci`; `npm test -- --maxWorkers=2`): 55 files, 439 tests
  passed; `npm run lint` and `npm run build` pass. New
  `lib/__tests__/faiths.test.ts` (8, on the procedural seed-42 fixtures
  written by the branch and by `main`: the recorded table; the older
  bundle's table rebuilt as the run recorded it, naming the same churches in
  its records; untraceable faiths marked; both schism wordings; a faith's
  events and temples; when the tab shows; a toleration named with its
  founding turn), the Faiths panel tests (5: two churches that shared a
  slot listed apart, the faiths as known at the scrubbed turn, an older
  bundle rebuilt and said so, the tab beside the movements, a sect's church
  and the church it became), and updated movements, systems and languages
  tests.
* Bundle size: +3.2 KB for a 20-faith world; the slow 10.5 MB guard test
  passes.

## 9. Open

* Agent events (`agent_events.arrow` and `AgentEventRecord.belief`) keep the
  native slot. They are resolvable through the table's tenure
  (`holder_at`, the end of turn T - 1 for an event of turn T), but nothing
  reads them by faith yet.
* An older bundle's temple chronicler ids (`temple:<slot>`) are kept as
  written, because accounts and provenance cite them; their `faith` field is
  mapped.
* Two faiths can share a name (a sect reusing a vanished faith's name). The
  viewer tells them apart by founding turn; the prose does not.
* Rebuilding an older run's table depends on the wording of the `Schism`
  events. A faith whose schism is missing or unreadable is marked
  `unresolved`, not guessed.
* The viewer's general event log outside the Faiths tab still shows the raw
  `Temple of faith <id>` text (now a permanent id).
* The corrections of §5 are reproduced by tests only: none fired in any
  measured world.
* Not run: browser QA of the viewer, Windows and macOS.
