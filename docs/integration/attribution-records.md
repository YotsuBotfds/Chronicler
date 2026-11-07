# Attribution records (D2, `--attribution-records`)

Status: implemented on `claude/cw-d2-attribution`, default off, hybrid only, observation only.
Design: AUDIT-D section 7.3 and section 4
([audit](../superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md)); plan
section 5.4 ([plan](../superpowers/roadmaps/connected-world-program.md)). Code:
`src/chronicler/attribution_records.py` (notes, commit, snapshot, reader reference
`record_status`), `src/chronicler/attribution_records_state.py` (persisted state, declared
kinds, counters); viewer `viewer/src/lib/attributionRecords.ts` (types and reader) and
`viewer/src/components/systems/AttributionRecords.tsx` (Livelihoods tab).

## Why

Program D2: audit attribution before foreign grievances use it, so that the actual actor,
victim and cause survive conquest and state changes, with no omniscient information and no
duplicate influence through the existing institutional pathways. The audit found:

- a granary seizure names only its victim, in a field called `buyer` (`grain_reserves.seize_granary`);
- `war.armies.reconcile_rosters` books the natural deaths of enlisted soldiers (including the
  native x2 soldier-at-war mortality) as army casualties, so `Army.casualties` merges battle,
  attrition and natural deaths;
- a restored polity reuses the dead polity's index and name, so anything attributed to the old
  polity by index or name silently applies to the new one;
- the burdens one polity lays on another are recorded in a dozen places with different
  identities (names, indices, settlement ids), as real transfers, minted amounts or destroyed
  stock, or not at all.

This slice records them, at the event, in one dated record. Nothing reads it: it adds no
grievance. A later grievance (D1) may replace a proxy with a recorded burden behind its own
switch (for example diplomacy's flat occupation increment, `diplomacy.py`, replaced by the
recorded requisitions); it must not stack on the channels that already carry war harm
(AUDIT-D section 4.3: native needs, movements, `city.grievance`, diplomacy grievances, finance
creditor grievance, governance PSI, factions), and it must use only what the grieving party could
know: this record is observer truth (it knows the books owner of a granary, the actor of every
death), not a polity's information.

## The switch

`--attribution-records` (`BooleanOptionalAction`; `--no-attribution-records` ends it with a dated
record). A livelihoods package (`livelihoods_state.LIVELIHOODS_SWITCHES`), inserted before
`wealth_accounting`, which stays last so its hooks still run after every payer. Why a
livelihoods package rather than its own group: it reuses the persisted container
(`WorldState.livelihoods`, omitted while None, so feature-off state and bundles keep their
bytes), the CLI forwarding, the checkpoint header flags, the resume-conflict checks, the snapshot
path (`snapshot.livelihoods.attribution_records`) and the feature catalog's generated entry, with
no edit to pinned `models.py`, `main.py` or `simulation.py`. Its own group would have needed a
new `WorldState` field (pinned `models.py`) and its own forwarding, checkpoint and snapshot
wiring. Registered: `feature_catalog.REQUIREMENTS` (`--agents hybrid`), `batch_manifest`
(`SIMULATION_ARG_KEYS` and the omit-when-unset list; pinned, witness layer `cwd2`). A saved world
outside hybrid is refused until the switch is ended.

## Contract

- It never writes simulation state, draws no random number and builds no world lookup cache
  (`civ_map`, `region_map`, `civ_index_map`): it scans `world.civilizations` and
  `world.regions`, as provenance does. A name resolves to an index as the simulation's own maps
  resolve it (the last index with that name).
- With the switch on, every output except this record equals the switch off (tested offline
  and on the compiled extension; evidence below).
- Event-time notes come from the unpinned decision modules, each inside the existing
  `world.livelihoods` guard and a no-op unless this switch is active:

| Seam | Note | What it records |
| --- | --- | --- |
| `war.armies.apply_casualties` | `note_casualties` | deaths by cause (`battle`, `trapped`, `revolt`, `attrition`) |
| `war.armies.reconcile_rosters` | `note_natural_deaths` | enlisted agents found dead after the tick |
| `war.occupation._requisition` | `note_requisition` | commons food destroyed, the granary SEIZED flow, the retail war loss (siege, occupation) |
| `war.occupation.start_occupation` | `note_plunder` | the occupier's plunder (minted) |
| `war.occupation.tick_occupations` | `note_occupation_turn` | the owner's lost taxes (destroyed) and the occupier's requisition (minted) |
| `action_engine.apply_region_conquest` | `note_conquest` | goods destroyed, the granary SEIZED flow, the retail war loss, per call |
| `cities._commerce` | `note_city_dues` | dues assessed for the lord, split from a guild levy's part |
| `cities._sack` | `note_city_sack` | plunder paid to the sacker and the loot no one receives |

  The only change to a decision line is `tax_lost = spend(...)` in `tick_occupations` (the
  amount `spend` already returned, now named). `tests/test_attribution_records.py` pins the eight
  call sites and their guard.
- The Phase 10 commit (`phase10`, the livelihoods hook after every package but the wealth
  ledger) reads the turn's battle records, treaties, granary flows, retail log, quarantine
  receipt, armies and civilization table, writes the frame and clears the notes.
- Pinned `grain_reserves.py` is not edited: the seizure note reads the flow the seizure has just
  appended (the newest flow of the turn, of this region, not yet attributed), and the commit
  counts SEIZED flows no note saw (`unattributed`).

## Records

`snapshot.livelihoods.attribution_records` (schema 1, stage `D2`, dated by `source_turn`):
`frame` (None when that turn was not observed: unknown, not zero), lifetime totals (`LIFETIME`),
counters (`COUNTERS`), the identity log, a dated log, labels and parameters.

### 1. Granary seizures (`frame.granary`)

`active` (granaries active; when false, `seizures` is empty and `unattributed` is None: not
observed), `seizures` (one per SEIZED flow: `region`, `flow` index, `grain`, `cause`
(`siege`, `occupation`, `conquest`), `via` (a conquest's path: `war`, `treaty`, `consolidated`,
`owner_gone`), `actor`, `victim`, `books_owner`, `owner_stale`), `unattributed`.
The victim is the region's ruler at the event (the defender of a conquest). `books_owner` is
the flow's `buyer`: the granary owner on the books, set at the Phase 2 opening, so after a first
conquest in the same turn it is stale (`owner_stale`): two conquests of one region in one turn
(`--no-campaigns`) are two seizures, the second with the first conqueror as victim and the
original ruler still on the books.

### 2. Casualties (`frame.casualties`)

`rows`, one per (war key, war start turn, victim, actor, cause, battle kind): `victim` (the
army's civilization), `actor`, `opponent` (the other side of the war), `cause`, `class`
(`combat`: `battle`, `trapped`, `revolt`; `attrition`; `natural`), `kind` (`field`,
`skirmish`, `assault`) and `deaths`.

- `battle`: the actor is the other side of the battle record the engagement appends next (the
  note keeps its index, so two battles of one civilization in one turn are told apart), and the
  war is the battle's, not the army's (an army raised against one enemy may die fighting
  another).
- `trapped`: a beaten army with no retreat bleeds a fifth after the battle it lost; the actor is
  that battle's other side.
- `revolt`: an occupation uprising; the actor is the occupied region's owner.
- `attrition` (terrain, hunger, supply, siege disease) and `natural` have no actor.
- `natural` deaths include the native x2 mortality of Soldier-occupation agents at war
  (`demographics.rs`); separating it needs a native change (D3). Militia, mercenary and civilian
  deaths are not roster soldiers and are not here (battle records count them).

`armies`: per live army, the deaths recorded this turn against the change of its own casualty
counter since the last commit (`closes`; None without a baseline: an army new to the records, or
gone). `by_class`, `by_cause`, `unresolved` (combat deaths whose battle record did not match).
The record stays outside `models.Army` (pinned through `models.py`).

### 3. Restored-civilization identity (`frame.identity`, `identity_log`)

An intentional boundary, declared: a restoration (`politics.check_restoration`, and the native
politics path in `politics_bridge`) gives the dead polity's index and name to a new polity, with a
new `founded_turn`. The simulation keeps doing so (default path unchanged). The records keep one
row per civilization index (name, alive, founding turn, last observed living turn) and date
every reuse:

- `restored`: a new founding turn under an index (`old_founded_turn`, `new_founded_turn`,
  `old_last_alive_turn`, `old_alive_at_last_observation`);
- `revived`: alive again without a new founding;
- `name_reused`: a new index named like an older one (a "New" restoration materialized as a new
  civilization);
- `renamed`.

A consumer that keys anything by civilization index or name (diplomacy memory, RS3's served
civilization, native memories' `source_civ`, city lords, these records) must split it at these
dates: before the event it belongs to the old polity. A restoration resets diplomacy
relationships with the restored polity (`world.relationships`); the other records carry over.
Every record here is dated, so the split is exact from the first observed turn.

### 4. Burdens (`frame.burdens`)

`pairs`: per (kind, nature, unit, actor, victim) the summed `amount`, `unknown` (events with no
amount), `events`, the `authority` that decided it and `internal` (actor = victim: a polity's own
dues). `entries`: the events, each with region, city, cause and receipt (at most `MAX_ENTRIES`
= 256 per turn; `entries_dropped`; the pairs stay exact). `retail_unattributed`: retail war
losses of the turn no note saw (None while retail is inactive).

| Kind | Authority | Nature | Unit |
| --- | --- | --- | --- |
| `city_dues` | `cities._commerce`, paid at the next Phase 2 by `cities.pay_dues` | transfer | treasury |
| `guild_levy` | `guilds._levies` raises the dues share (`guilds.dues_share`) | transfer | treasury |
| `city_sack` | `cities._sack`, the plunder paid | transfer | treasury |
| `city_sack_loss` | `cities._sack`, the loot no one receives | destroyed | treasury |
| `occupation_plunder` | `war.occupation.start_occupation` | minted | treasury |
| `occupation_requisition` | `war.occupation.tick_occupations` | minted | treasury |
| `occupation_tax_loss` | `war.occupation.tick_occupations` | destroyed | treasury |
| `food_requisition` | `war.occupation._requisition` (siege x0.85, occupation x0.8) | destroyed | food |
| `conquest_stock_loss` | `action_engine.apply_region_conquest` (x0.5) | destroyed | goods |
| `granary_seizure` | `grain_reserves.seize_granary` | destroyed | grain |
| `retail_war_loss` | `household_retail.on_conquest`/`on_war_loss` (rules 2) | destroyed | milli_food |
| `treaty_payment` | `war.peace.conclude_peace` | transfer | treasury |
| `quarantine_closure` | `quarantine_rules.decide` (closure mode) | restriction | routes |

Natures: `transfer` (paid by the victim, received by the actor), `minted` (credited to the actor,
taken from nobody: today's plunder and occupation requisition), `destroyed` (lost by the victim,
received by nobody: today's food requisition, seized granary grain, conquest losses), `restriction`
(no amount moves). The commons food a requisition destroys is derived from the commons after the
cut and the factor (`after x (1 - f) / f`, float rounding). City dues are internal pairs (the lord
is the region's controller); the levy's part is `commerce x LEVY_SHARE` while a levy stands.
Not recorded in this slice: diplomacy tribute installments, vassal tribute, siege and occupation
civilian deaths, the cost-only quarantine declarations (they restrict nothing).

## Guard: decisions never read provenance

`tests/test_provenance_decision_guard.py` (AUDIT-D 7.3 item 7). It walks every module under
`src/chronicler` except the narration and curation modules (`provenance`, `curator`,
`narrative`, `narration_context`, `historiography`, `narration_provenance`, `narration_audit`)
and collects every read of provenance: a call of a provenance read function through the module
(resolved from its imports) and every load of an attribute `provenance`, `causes` or `episode`.
Every read site must be registered with a reviewed classification (`cites`, `labels`,
`filters`, `decision`); the test fails on an unregistered site, a changed count, a stale row, a
new `decision` row, or an undeclared read function in `provenance.py`. The D-program record and
war modules read none.

The review found seven sites where a decision reads provenance, against the contract in
[causal provenance](causal-provenance.md) ("no simulation decision reads it"). They predate this
guard, are default-path behaviour and stay unchanged (a change goes behind a switch for the
owner's decision); they are recorded as defects (`KNOWN_DECISION_READS`):

| Site | Decision |
| --- | --- |
| `cities._lord_change` | a conquest or occupation key within one turn turns a lord change into a sack (cities are on by default for new worlds) |
| `scholarship._newly_occupied` | an occupation key of this turn strikes a seat |
| `scholarship._sack_cause` | a sack, conquest or occupation key makes a lord change hostile and blocks a founding |
| `scholarship._in_famine` | an open famine episode blocks a founding |
| `diplomacy._aid_convoys` | famine `tick` repeats are skipped, so aid follows crisis onsets only |
| `epidemiology._reports` | an open epidemic episode suppresses the arrival event and the row's source reset |
| `nomads._herds` | a recalled drought key gates the `pasture_drought` event |

The classification is a human review: a new `cites` row is read like code.

## Viewer

The Livelihoods tab mounts the panel whenever any snapshot of the run carries the record. Six
readings stay distinct: disabled (off in the run), absent (on in the run, missing at this
snapshot: unknown), malformed (refused, with the reason; nothing shown), unobserved (`frame:
null`), recorded zero (observed, nothing attributed; granaries off reads as not observed, not
zero) and recorded (deaths by war, victim, actor and cause; seizures with the stale books owner;
burden pairs with nature and unit; identity events). Types are in the new
`viewer/src/lib/attributionRecords.ts` (`types.ts` is pinned).

## Verification

Linux container, Python 3.13.18. Source: `main` `ae94bca6` (PR #87) merged into the branch; the
Python tree under test is the merge `ef021e7f` (the later commits change only the viewer and
docs). Native extension SHA-256 `e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b`:
`main`'s current Rust (the shared `~/.venvs/chronicler-native`, rebuilt by the lead from
`ae94bca6`; the same bytes as lane C1b's build from `51cd3167`, whose Rust equals the head's). No
Rust changed in this slice; nothing was built here.

- **Focused (offline):** `tests/test_attribution_records.py` 38 passed (constructed war
  scenarios: field battle, trapped, revolt, attrition, natural deaths on one army, two battles of
  one civilization in one turn, siege/occupation/conquest seizures, two conquests in one turn,
  an unattributed seizure, restoration through `politics.check_restoration`, a new index with an
  old name, occupation plunder and turns, treaty payment, quarantine closure, city dues and sack,
  guild levy split, retail war losses twice in one turn, the entry cap, the note sites, observer
  identity, the reader states); `tests/test_provenance_decision_guard.py` 5 passed; with the
  registry, retail, quarantine, catalog, manifest and every witness module: 853 passed.
- **Bounded offline lane** (`scripts/run_python_oracle_checks.py`, default output directory):
  PASS, 70 chunks, 14,435 tests, 347.0 s; slowest chunk `systems-2` 39.2 s of 110 s (shared
  4-core machine); the new chunk `connected-world-d` 9.4 s (43 tests).
- **Native:** `tests/test_attribution_records_native.py` (observer identity on procedural 32x10
  seed 13, 60 turns, and on template seed 42 with every livelihoods payer, 40 turns; a natural war
  run attributed and closing; retail war losses all attributed) with the offline modules,
  `test_wealth_accounting_native.py`, `test_household_retail_war_native.py` and
  `test_quarantine_migration_native.py`: 67 passed in 74.6 s.
- **Feature-off identity** (`scripts/turn_speed_identity.py`, 9 cases, each side its own source
  tree and extension): head against the `8abc1acb` reference outputs (extension `101a4cd5...`):
  9 cases, 399 files compared, 0 differences.
- **Observer identity** (hybrid, every switch): `hybrid_s42`, `hybrid_s7` and
  `proc48_hybrid_s42` with the catalog's all-on livelihoods set (retail in every region),
  `--wealth-accounting`, `--finance --domestic-credit`, `--quarantine-mode closure
  --quarantine-channels trade,migration`, with and without `--attribution-records`: 3 cases, 317
  files compared, 0 differences after removing only the record (every `attribution_records` key
  and a container that held nothing else; bundles decoded without `generated_at`); 550 snapshots
  carry the record.
- **Exact resume** (`scripts/checkpoint_identity.py`, `hybrid_s42_long`, 200 turns, the same
  all-switch set plus `--attribution-records`): writing checkpoints changes nothing (112 files, 0
  differences) and every one of the 19 resume points equals the straight run (0 differences; the
  points at turns 1, 2, 3, 5, 8 and 13 fall inside live armies or occupations, so the army
  baselines and the civilization table cross the checkpoint); largest checkpoint 4.92 MB.
- **Viewer:** `npm test -- --maxWorkers=2` 159 files, 1,586 passed, 2 skipped (a first run under a
  load average of 9 timed out two unrelated panel tests at 5 s; both pass alone and in the rerun);
  `npm run lint` clean; `npm run build` passes (the existing large-chunk warning). A type-only fix
  of the reading's union followed; the four affected test files (54 tests), lint and build reran.
- **Preflight** (`refactor_preflight.py --git-diff origin/main`): the only content-pinned files
  are `batch_manifest.py` and `tests/test_batch_manifest.py`, carried by the provisional layer
  `cwd2` (two hunks and one, read: the new key in `SIMULATION_ARG_KEYS` and in the omit-when-unset
  lists), built against `main` `ae94bca6` as the last layer (`LAYERS = (..., "cws1", "cwc1b",
  "cwd2")`); the witness modules pass. The lead regenerates one integrated layer per slice.

### Development worlds (development only; not a held screen)

Template 1, 3, 7, 9, 11, 23, 42 and procedural 32x10 seeds 7, 11, 13, 17, 21, 31, 200 turns each,
`--agents hybrid --grain-reserves --attribution-records`, default campaigns, `PYTHONHASHSEED=0`.
No combat death went unresolved, no army closure failed (978 checked, 110 unchecked: armies new
to the records or gone), no seizure went unattributed and no restoration happened in these runs.

| World | Observed turns | Soldiers' deaths combat / attrition / natural | Army closures held / failed / unchecked | Granary seizures (grain; stale books owner; unattributed) | Identity events |
| --- | --- | --- | --- | --- | --- |
| t1 | 200 (5 zero) | 14 / 2 / 2 | 48 / 0 / 8 | 0 (0.0; 0; 0) | 0 |
| t3 | 200 (6 zero) | 4 / 0 / 1 | 11 / 0 / 2 | 0 (0.0; 0; 0) | 0 |
| t7 | 200 (15 zero) | 8 / 0 / 5 | 13 / 0 / 2 | 10 (6.0; 0; 0) | 0 |
| t9 | 200 (9 zero) | 5 / 0 / 0 | 20 / 0 / 2 | 0 (0.0; 0; 0) | 0 |
| t11 | 200 (6 zero) | 21 / 1 / 4 | 20 / 0 / 3 | 0 (0.0; 0; 0) | 0 |
| t23 | 200 (8 zero) | 12 / 0 / 4 | 21 / 0 / 4 | 0 (0.0; 0; 0) | 0 |
| t42 | 200 (3 zero) | 15 / 7 / 0 | 37 / 0 / 6 | 0 (0.0; 0; 0) | 0 |
| p7 | 200 (10 zero) | 70 / 11 / 24 | 134 / 0 / 12 | 13 (21.6; 0; 0) | 0 |
| p11 | 200 (6 zero) | 10 / 1 / 1 | 40 / 0 / 6 | 5 (0.7; 0; 0) | 0 |
| p13 | 200 (1 zero) | 67 / 11 / 17 | 212 / 0 / 18 | 24 (34.4; 0; 0) | 0 |
| p17 | 200 (4 zero) | 49 / 7 / 12 | 135 / 0 / 13 | 0 (0.0; 0; 0) | 0 |
| p21 | 200 (5 zero) | 86 / 12 / 13 | 208 / 0 / 25 | 8 (9.1; 0; 0) | 0 |
| p31 | 200 (0 zero) | 39 / 3 / 7 | 79 / 0 / 9 | 9 (8.3; 0; 0) | 0 |

Burdens summed over the 13 worlds (2,600 observed turns; cross-polity: actor and victim differ):

| Burden kind | Nature | Unit | Total amount | Events | Cross-polity events |
| --- | --- | --- | --- | --- | --- |
| city_dues | transfer | treasury | 3296.3 | 14988 | 0 |
| city_sack | transfer | treasury | 28.0 | 5 | 5 |
| city_sack_loss | destroyed | treasury | 0.7 | 5 | 5 |
| conquest_stock_loss | destroyed | goods | 307.1 | 25 | 25 |
| food_requisition | destroyed | food | 815.4 | 270 | 270 |
| granary_seizure | destroyed | grain | 80.1 | 69 | 69 |
| guild_levy | transfer | treasury | 111.9 | 1139 | 0 |
| occupation_plunder | minted | treasury | 71.0 | 50 | 50 |
| occupation_requisition | minted | treasury | 158.0 | 158 | 158 |
| occupation_tax_loss | destroyed | treasury | 280.0 | 158 | 158 |
| treaty_payment | transfer | treasury | 394.0 | 22 | 22 |

What the records show on these worlds:

- Natural deaths are 90 of the 545 soldiers' deaths (17%; 24 of 105 on procedural 7) that army
  casualty counters book together with 400 combat and 55 attrition deaths.
- Every recorded cross-polity treasury burden of war but treaties and sacks is minted or
  destroyed: occupation plunder (71) and requisitions (158) are credited to occupiers and taken
  from no one, while owners lose 280 to occupation, spent into nothing. The real cross-polity
  transfers are treaty payments (394) and sack plunder (28). Food requisitions destroy 815 food
  units and granary seizures 80 grain that no army receives.
- City dues (3,296) and guild levies (112) are all internal: a city's lord is its region's
  controller, so they ground no foreign grievance.
- Granary books stayed current (no stale owner) in these campaign runs: a stale books owner needs
  two conquests of one region in one turn (`--no-campaigns`; tested offline).

Evidence (outside the repository): `/home/user/evidence/d2/` (identity, preflight, oracle log,
native, feature-off, observer, resume and development outputs).

## Not done in this slice

- No consumer: no grievance, diplomacy or movement reads the record (by design; D1 decides a
  replacement behind its own switch).
- The native soldier-at-war x2 mortality stays inside `natural` (needs a native change, D3).
- The seven pre-existing decision reads of provenance are recorded, not changed.
- Diplomacy tribute installments and vassal tribute are not itemized.
