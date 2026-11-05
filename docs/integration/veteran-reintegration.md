# Veteran reintegration (RS3, `--veteran-reintegration`, default off)

People who leave a real army alive are recorded by native stable id. While
they remain eligible they come first, among candidates who are otherwise
eligible, for the openings other packages already have: workshop crews (the
native crew planner's `priority_ids`), apprenticeship seats (RS1) and repair
crews (RS2). Nothing is guaranteed and nothing is created: with no opening
there is no placement, and this package moves no money, creates no person and
grants no skill. Module `chronicler.veteran_reintegration`, state
`chronicler.veteran_reintegration_state`, phase plan
`docs/superpowers/roadmaps/recovery-skills-phase.md` (RS3).

## Switch, modes and prerequisites

- `--veteran-reintegration` requires `--agents hybrid` and at least one of
  `--workshops`, `--apprenticeship` or `--repair-projects`.
- `--veteran-mode priority` (default when on): eligible veterans are put first.
- `--veteran-mode record_only`: the control. Capture, tracking, outcomes and
  the "who would have been put first" lists are identical in kind; nobody's
  order changes (`priority_ids` returns `[]`).
- A world that never enabled the switch has no sub-state, snapshot key,
  checkpoint flag or manifest entry, and the capture hooks in the campaign
  layer are not consulted (they check for the livelihoods container first).

## Audit: the war and army events actually used

Source as of this lane (phase branch `52711f27` plus RS3). Rosters are
`(stable id, region index)` pairs in `Army.roster`; the region is the
person's residence, refreshed from the post-tick snapshot by
`reconcile_rosters`.

| Where (file:line) | What happens to the roster | Ids available | Event emitted | RS3 |
| --- | --- | --- | --- | --- |
| `war/armies.py:353` `release_soldiers` | `leaving` (a local set) removed alive | yes (local set) | none | captured, cause `desertion` or `scattered` (its callers' causes) |
| `war/logistics.py:114` | low morale: `release_soldiers(cause="desertion")` | via above | none | `desertion` |
| `war/battles.py:350` `_destroy` | a broken army's survivors: `release_soldiers(cause="scattered")`, then `disband("destroyed")` with an empty roster | via above | `army_destroyed` (no ids) | `scattered` |
| `war/runtime.py:207` `_drop_empty` | below `MIN_ARMY` (3): survivors `scattered`, then `disband` with an empty roster | via above | `army_destroyed`/`army_disbanded` (count only) | `scattered` |
| `war/runtime.py:325` `_demobilize` | returning with no reachable home for 60 turns: `scattered`, then `disband` | via above | `army_disbanded` | `scattered` |
| `war/armies.py:372` `disband` | `army.roster = []`: at-home demobilisation (`runtime.py:321`) calls it with the roster intact | yes, before the clear | `army_disbanded` (survivor count, no ids) | captured before the clear, cause `demobilised` (reason `demobilized`) or `destroyed`; no current caller reaches `destroyed` with people still enlisted |
| `war/runtime.py:170` `_validate_armies` | army dropped silently: its civilization is gone or its region vanished; roster alive (reconciled last tick) | yes | none | `dissolved` |
| `war/runtime.py:329` `end_of_turn_sync` | after Phase 10: armies of civilizations that died in Phase 10 dropped silently; rosters alive (reconciled this tick) | yes | none | `dissolved`, committed into the settled turn |
| `war/armies.py:315` `apply_casualties` | deaths queued natively (`queue_targeted_deaths`) | yes | battle records | not a release |
| `war/armies.py:393` `reconcile_rosters` | dead after the tick dropped | yes | none | not a release (the record, if any, closes `died`) |
| `war/armies.py:428` `rebind_rosters` | non-exact resume (rebuilt pool): rosters kept if every id is live, else redrafted with new ids | new ids | none | releases nobody; see "Pool rebuild" |
| `war/peace.py:174` `_finish` | armies of the ended war set `returning` | — | peace events | the later `_demobilize` captures them |

War identity is `(war_key, start_turn)`: `war_key` is the civilization pair
and is reused by later wars of the same pair. `world.war_start_turns`
(`runtime.py:118`, `peace.py:112`, popped at `peace.py:189`) feeds
`WarRecord.start_turn`. A record names the war the army was raised for: the
war record of the army's key (active `war_state.wars` or `ended_wars`) that
was open at the army's `raised_turn` (latest start wins); `null` when none is
found.

`select_recruits` (`armies.py:117`) skips current roster members, named
characters and anyone holding this turn's registry work. A veteran placed in
a crew therefore cannot be drafted in the same turn; crews are planned in
Phase 2, before campaigns draft.

## Capture, timing and exactly-once

- The campaign layer calls `armies.note_released(world, army, entries, cause)`
  at each row above; it is a no-op without the livelihoods container, and
  `capture_release` is a no-op unless the switch is active. Neither changes
  the army or draws RNG.
- Campaigns run in Phase 5: after this turn's Phase 2 crew planning and before
  the native agent tick. Captures are only buffered (transient, stamped with
  the turn and `id()` of the native simulator). Phase 2 offers and crew
  placements, and outcomes other packages report through `note_outcome`, are
  staged the same way.
- Everything is committed once, in this package's `phase10` hook, after the
  agent tick succeeded, against the post-tick snapshot. `last_settled_turn`
  refuses a second commit of a turn. Order of the commit: placements (Phase 2
  precedes this turn's releases), then captures (an id with an open record is
  closed `remobilised` first: drafted and released between two observations),
  then every open record is observed.
- A failed Phase 2 (`rollback_phase2`) or agent tick (`rollback_agent_tick`,
  when the livelihoods wrapper runs) drops what is staged. If the run goes on
  after a failure regardless, staged rows of another turn or pool are discarded
  and counted (`captures_discarded`, `notes_discarded`) at the next hook. A
  failed turn therefore commits no record, placement or counter. The only
  later capture, `end_of_turn_sync`, runs after Phase 10 and commits directly
  into the turn already settled (and is buffered for Phase 10 if that turn has
  not settled yet).
- Checkpoints are written at turn boundaries, when nothing is staged; records,
  the frame and counters are persisted state.

## Records, eligibility and priority

A record: `{record_id, agent_id, civ, army_id, war_key, war_start, cause,
released_turn, released_region, region, age, status, reason, closed_turn,
closed_reason, placements, placed_turns, spells, outcomes, outcomes_dropped}`.
`civ` is the served civilization's index in `world.civilizations`; regions are
indices in `world.regions`.

Eligibility, evaluated live whenever `priority_ids(world, region)` is asked:

- an open record (alive at the last post-tick observation);
- adult: age at least 20 (native `agent::AGE_ADULT`, the crew planner's age);
- released before this turn and at most `ELIGIBLE_TURNS` (20) turns ago;
- not on any army roster now;
- resident in a region whose controller is the civilization they served.

`priority_ids` returns the eligible veterans resident in that region, earliest
release first, then id, in `priority` mode only. Consumers:

- workshops: `workshops._crew_priority` passes one list per open site region
  to `plan_workshop_crews(..., priority_ids=...)`. Listed ids that are
  eligible crew candidates come first, in the listed order; nobody becomes
  eligible by being listed.
- RS1 apprenticeship seats and RS2 repair crews call `priority_ids` and report
  placements with `note_outcome(world, id, "placed:apprentice" |
  "placed:repair", turn=..., detail={"site": ..., "region": ...})`. Reports are
  staged and committed in this package's Phase 10 hook of the same turn, so
  they must be made before it (Phase 2, the agent-tick hooks or an earlier
  package's Phase 10 hook). Ids that are not open records are ignored; kinds
  outside `OUTCOMES` raise.
- Crew placements are detected here: after Phase 2, the turn's workshop
  receipts are compared with the open records. A veteran on the crew of a site
  that worked this turn (`allocated > 0`, never in observe mode) is
  `placed:crew`, with `prioritised` true only when priority mode put them
  first. In `record_only` the same comparison records who was placed anyway.

## Outcomes and lifecycle

Dated outcomes (`OUTCOMES`, declaration order, append only): `placed:crew`,
`placed:apprentice`, `placed:repair`, `waiting`, `remobilised`, `died`,
`migrated`, `control_lost`, `expired`, `pool_reset`.

- Placement: consecutive placed turns in one kind of opening at one site are
  one spell (`spells`, at most 8 kept); a new spell is another placement and
  another dated `placed:*` outcome. `placements` counts spells, `placed_turns`
  turns, and the counter `people_placed` distinct people.
- `waiting`: dated when a record becomes eligible and unplaced (after capture,
  after a placement spell ends, after control is regained).
- `migrated` `{from, to}`: the post-tick residence changed. Eligibility follows
  residence.
- `control_lost` `{region, controller}`: the record's region is not ruled by the
  civilization served (conquest, secession, a move into foreign land, a dead
  civilization). The record stays open and becomes eligible again if control
  returns or the person moves home.
- Closing: `died` (absent from the post-tick snapshot), `remobilised`
  `{army_id}` (on a roster again; a later release opens a new record),
  `expired` (the window ended; `{placed_turns}`), `pool_reset`.
- A minor (drafted under 20) is `ineligible` with reason `minor` until adult.

Per turn, every veteran who was eligible at Phase 2 and placed nowhere is a
waiting row with a reason (`UNMET_REASONS`): `no_site` (no workshop site in
their region), `site_idle` (a site that did not work: building, unfunded or
worn), `not_crew_eligible` (the site worked; they are not one of its resident
adult urban farmers), `crew_full` (they are; the crew cap was reached ahead of
them), `unplaced` (none observed: a trip, other work). The first two mean no
opening existed.

## Pool rebuild

`on_pool_reset` (called by `livelihoods.bind_native_pool` when the native pool
is rebuilt, a legacy state-file resume) closes every open record with a dated
`pool_reset`, drops staged rows of the old pool and the ids kept for the
distinct-person count (the count is kept). When the rebuild finds enlisted
rosters, `pool_reset_turn` is set: those rosters named the old pool and the
campaign layer then keeps them (stale ids that now name strangers) or redrafts
them. Releases from armies raised before that turn are not captured
(`captures_untrusted`), so neither a redraft nor a stale roster makes a
veteran. Armies raised afterwards are captured as usual. An exact checkpoint
load re-binds without a reset.

## Declared constants, bounds and costs

- `ELIGIBLE_TURNS = 20` (declared, uncalibrated); `AGE_ADULT = 20` (native).
- Bounds: `MAX_OPEN` 512 open records (beyond it captures are counted,
  `capture_overflow`, never stored), `MAX_OUTCOMES` 24 per record (older dropped
  and counted), `MAX_SPELLS` 8, `MAX_ARCHIVE` 64 closed records,
  `MAX_PLACED_IDS` 4096 (beyond it a first placement is counted as
  `people_placed_unverified`), `MAX_FRAME_ROWS` 128 rows per frame list
  (`rows_dropped`). The snapshot shows at most 64 open records
  (`veterans_omitted`).
- Costs: none. Placements are paid, if at all, by the package that owns the
  opening (workshop upkeep, RS1 stipends, RS2 wages). No accumulator entry,
  transfer, RNG draw or event is added.

## Snapshot (`snapshot.livelihoods.veteran_reintegration`)

`{schema_version: 1, stage: "RS3", enabled, mode, source_turn, frame,
veterans, veterans_omitted, closed, counters, parameters}`. `frame` is the
completed turn (`frame.turn == source_turn`) or `null` when no turn was
committed (unknown, not zero): `captured` rows `{agent_id, civ, army_id,
war_key, war_start, cause, region}`, `captured_total`, `captured_by_cause`,
`offered` (`[region, ids]` per workshop site region; the lists the planner
received, or would have received in the control; `null` without an observed
Phase 2), `placed`, `waiting` (with reasons), this turn's `outcomes`, `counts`
and `priority_applied`. `veterans` are open records (copies), `closed` those
closed in the source turn.

Viewer: `viewer/src/lib/veterans.ts` (strict reader `veteransAt`, funnel,
outcome counts, unmet by reason) and
`viewer/src/components/systems/Veterans.tsx` (not mounted; the lead mounts
it). The reader rejects misdated, out-of-range or inconsistent records (a
placed status without a spell this turn, a prioritised placement in the
control, half a war identity, unbalanced cause counts, undated order).

## Evidence

### Tests

- `tests/test_veteran_reintegration.py` (offline, constructed war world and
  pool): capture by cause and war at release, disband, `_drop_empty`,
  `_validate_armies` and `end_of_turn_sync`; feature off (no container,
  disabled, not hybrid) with identical rosters and RNG; war identity across a
  reused key; priority order and every eligibility rule; death, migration,
  control lost and regained, remobilisation and a second record (also when
  drafted and released again within one turn), expiry and the live window;
  crew placements, spells and every unmet reason in both modes; staged
  reports, duplicates and stale reports; a failed turn commits nothing and a
  turn settles once; pool reset and a redraft that makes no veteran; bounds; no
  money moves; dated, copied snapshot; JSON, pickle and RS0-era pickle
  round trips.
- `tests/test_veteran_reintegration_native.py` (real extension, procedural
  32×10 seed 302): an independent oracle (roster difference around each
  campaign tick, plus drafts within it, minus queued war deaths) equals the
  captures every turn; placements are on worked crews, once per person; the
  native planner's crews put the offered veterans first in the offered order;
  `record_only` leaves the whole trajectory identical to the run without the
  switch, and `--no-veteran-reintegration` equals never enabled; exact
  checkpoint resume at turn 30 with open, placed records is byte identical; a
  legacy state-file resume closes every open record `pool_reset`, and its kept
  or redrafted rosters release nobody into the records.

### Feature-off identity

With the switch off, the parent commit `52711f27` (its `src/` exported with
`git archive`) and this lane give identical bundles (minus `generated_at`),
`chronicle.md`, `agent_events.arrow` and `state.json`, with the shared RS0
extension, in three worlds where armies are raised and released: procedural
32×10 seed 302 (60 turns, `--workshops`), procedural 32×10 seed 7 (60 turns, no
livelihoods container) and template seed 42 (40 turns, `--workshops`).

### Development measurement (natural activation, 80 turns, `--workshops` operate)

Procedural worlds are 32 regions × 10 civilizations; template worlds are the
default 8 × 4. Shared RS0 extension; `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`.
Veteran-turns count a person once per turn.

| World | Captured (demobilised / scattered / desertion) | Put first (veteran-turns) | Placements (spells / people / turns), priority | same, `record_only` | Prioritised spells | Waiting veteran-turns: no site / site idle / not crew-eligible / crew full | Closed: died / remobilised / expired | Control lost | Moves |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 302 | 71 (39 / 26 / 6) | 139 | 11 / 8 / 29 | 11 / 8 / 29 | 7 | 454 / 65 / 56 / 0 | 15 / 8 / 48 | 41 | 128 |
| procedural 303 | 63 (53 / 10 / 0) | 244 | 23 / 16 / 67 | 23 / 16 / 66 | 12 | 315 / 23 / 185 / 0 (control: 1 crew full) | 13 / 1 / 49 | 55 | 129 |
| procedural 7 | 98 (56 / 35 / 7) | 98 | 11 / 6 / 13 | 11 / 6 / 13 | 7 | 381 / 53 / 36 / 0 | 33 / 22 / 43 | 67 | 161 |
| template 42 | 29 (19 / 10 / 0) | 195 | 2 / 1 / 4 | 2 / 1 / 4 | 2 | 183 / 183 / 8 / 0 | 3 / 7 / 19 | 8 | 25 |
| template 11 | 24 (15 / 8 / 1) | 56 | 0 | 0 | 0 | 203 / 38 / 18 / 0 | 5 / 1 / 18 | 10 | 24 |

- Activation is natural in all five worlds; no `destroyed` or `dissolved`
  capture occurred (a destroyed army's survivors are `scattered`).
  Demobilisation at home is 64% of captures (182 of 285).
- Priority changes who is first, rarely who is placed. The `record_only`
  control placed the same people in every world but one veteran-turn
  (procedural 303, a crew at its cap). In procedural 302 and 7 the priority
  run equals the run without the switch once crew order is ignored; in 303 the
  trajectory diverges from turn 28. `record_only` equals the run without the
  switch in all three procedural worlds (80 turns), apart from its own key.
- The binding constraint is location, then crew eligibility: 60–80% of waiting
  veteran-turns are in regions with no workshop site (at most four sites per
  world), and most veterans are not resident adult urban farmers of a site's
  city (many are soldiers by occupation).
- Natural example (procedural 302, priority): person 10 served the Yuguri
  Dominion in army-19 (the Republic of Miros–Yuguri Dominion war that began at
  turn 8), was sent home at turn 23 (`demobilised`) in Mitokan Meadows, moved
  to Fyvariel Woods at turn 25, and at turn 27 joined the Fyvariel Woods crew,
  listed first with two other veterans (`[10, 15, 101, 28, 45, 110, 554]`; the
  control's crew that turn is the same seven people in id order: 7 eligible,
  cap 8). Failure example, the same turn: veterans 434 and 441 were put first
  at Medyra Shore, whose crew was full (8 of 9 eligible), but they were not
  crew candidates there (`not_crew_eligible`); 24 of the turn's 29 waiting
  veterans lived in regions with no workshop site.

Commands (reproducible; scratch output directories):

```sh
PY=/root/.venvs/native-rs0/bin/python   # or any interpreter with a fresh extension
for seed in 302 303 7; do
  for mode in priority record_only; do
    PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src $PY -m chronicler.main --seed $seed --turns 80 \
      --worldgen procedural --regions 32 --civs 10 --agents hybrid --simulate-only --workshops \
      --veteran-reintegration --veteran-mode $mode --output out/p${seed}_${mode}/chronicle.md
  done
done
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src $PY -m chronicler.main --seed 42 --turns 80 \
  --agents hybrid --simulate-only --workshops --veteran-reintegration --output out/t42/chronicle.md
```

## Limits and open questions

- Development measurement only (five worlds, 80 turns); nothing here is a
  held screen or a qualification gate. `ELIGIBLE_TURNS` is not calibrated.
- Crews are the only opening measured: RS1 and RS2 report their own placements
  once integrated; until then `placed:apprentice`/`placed:repair` are tested
  only on constructed reports.
- Priority acts only when openings are scarce (a crew at its cap). With at most
  four workshop sites and few veterans who are urban farmers of a site's city,
  the effect on placements is near zero in these worlds.
- Residence and age are observed once per turn after the tick;
  `control_lost` is dated when observed (Phase 10), while `priority_ids` checks
  control live.
- A veteran placed "anyway" in a region ruled by another civilization is a
  placement (not prioritised), and their record stays ineligible.
