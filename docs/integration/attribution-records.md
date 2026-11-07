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
- `war.armies.reconcile_rosters` books every enlisted agent found dead after the native tick as an
  army casualty, so `Army.casualties` merges battle, attrition, deaths from war drains, native
  mortality (with its x2 for soldiers at war) and plague;
- a restored polity reuses the dead polity's index and name, so anything attributed to the old
  polity by index or name silently applies to the new one;
- the burdens one polity lays on another are recorded in a dozen places with different
  identities (names, indices, settlement ids), as real transfers, minted amounts or destroyed
  stock, or not at all.

This slice records them, at the event, in one dated record. Nothing reads it: it adds no
grievance. A later grievance (D1) may replace a proxy with a recorded burden behind its own
switch (for example diplomacy's flat occupation increment replaced by the recorded
requisitions); it must not stack on the channels that already carry war harm (AUDIT-D section
4.3: native needs, movements, `city.grievance`, diplomacy grievances, finance creditor
grievance, governance PSI, factions), and it must use only what the grieving party could know:
this record is observer truth (it knows the books owner of a granary, the actor of every death),
not a polity's information.

## The switch

`--attribution-records` (`BooleanOptionalAction`; `--no-attribution-records` ends it with a dated
record). A livelihoods package (`livelihoods_state.LIVELIHOODS_SWITCHES`), placed after
`workshop_economics` (A3, which acts through the workshop seams) and before `wealth_accounting`,
which stays last so its hooks still run after every payer: the observers come after every acting
package. Why a livelihoods package rather than its own group: it reuses the persisted container
(`WorldState.livelihoods`, omitted while None, so feature-off state and bundles keep their
bytes), the CLI forwarding, the checkpoint header flags, the resume-conflict checks, the snapshot
path (`snapshot.livelihoods.attribution_records`) and the feature catalog's generated entry, with
no edit to pinned `models.py`, `main.py` or `simulation.py`. Its own group would have needed a
new `WorldState` field (pinned `models.py`) and its own forwarding, checkpoint and snapshot
wiring. Registered: `feature_catalog.REQUIREMENTS` (`--agents hybrid`), `batch_manifest`
(`SIMULATION_ARG_KEYS` and the omit-when-unset list; pinned, witness layer `cwd2`, after `cwa3`).
A saved world outside hybrid is refused until the switch is ended.

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
| `war.armies.reconcile_rosters` | `note_natural_deaths` | enlisted agents found dead after the tick, with their regions |
| `war.armies.drain_population` | `note_war_drain` | deaths a war drain staged per region (agent modes), with its actor |
| `war.occupation._requisition` | `note_requisition` | commons food destroyed, the granary SEIZED flow, the retail war loss (siege, occupation) |
| `war.occupation.start_occupation` | `note_plunder` | the occupier's plunder (minted) |
| `war.occupation.tick_occupations` | `note_occupation_turn` | the owner's lost taxes (destroyed) and the occupier's requisition (minted) |
| `action_engine.apply_region_conquest` | `note_conquest` | goods destroyed, the granary SEIZED flow, the retail war loss, per call |
| `cities._commerce` | `note_city_dues` | dues assessed for the lord, split from a guild levy's part |
| `cities._sack` | `note_city_sack` | plunder paid to the sacker and the loot no one receives |

  Changes to decision code besides the guarded note calls: `tax_lost = spend(...)` in
  `tick_occupations` names the amount `spend` already returned; `drain_population` takes an
  optional `actor` keyword, passed by the siege (the besieger), a battle's garrison loss (the other
  side, through `_apply_side_losses`'s new optional `enemy`), occupation depopulation and a crushed
  revolt (the occupier), which only the note reads. `tests/test_attribution_records.py` pins the
  nine call sites and their guard, and fails on a `note_*` function without a registered site.
- The Phase 10 commit (`phase10`, the livelihoods hook after every package but the wealth
  ledger) reads the turn's battle records, treaties, granary flows, retail log, quarantine
  receipt, armies and civilization table, writes the frame and clears the notes.
- Pinned `grain_reserves.py` is not edited: the seizure note reads the flow the seizure has just
  appended (the newest flow of the turn, of this region, not yet attributed), and the commit
  counts SEIZED flows no note saw (`unattributed`).

## Records

`snapshot.livelihoods.attribution_records` (schema 1, stage `D2`, dated by `source_turn`):
`frame` (None when that turn was not observed: unknown, not zero), lifetime totals (`LIFETIME`),
counters (`COUNTERS`), the identity log, a dated log, labels and parameters. Like the A1 and B1
records, every snapshot carries the static labels and parameters (about 4 KB), so any segment of a
history reads on its own; the review measured about 3% of a bundle.

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
and `deaths`. Classes and causes:

- `combat`: `battle` (field, skirmish or assault; the actor is the other side of the battle
  record the engagement appends next: the note keeps its index, so two battles of one
  civilization in one turn are told apart, and the war is the battle's, not the army's),
  `trapped` (a beaten army with no retreat bleeds a fifth after the battle it lost; the actor is
  that battle's other side), `revolt` (an occupation uprising; the actor is the occupied region's
  owner polity, whose partisans are drawn from the population).
- `attrition`: terrain, hunger, supply, siege disease; no actor.
- `war_drain`: an enlisted agent found dead after the tick in a region where a war drain
  (`drain_population`: siege civilians, a battle's garrison, occupation depopulation, a crushed
  revolt) staged deaths that turn. The native tick kills staged catastrophe deaths among all the
  region's people, soldiers included, so such a death may be the drain's or natural: cause
  `war_drain` with the drain's actor when the region's drains that turn name one, `possibly_enemy`
  (no actor) when they name several or none. `war_drains` lists the drains (region, staged deaths,
  named actors, unnamed drains).
- `natural`: the other deaths found after the tick: native mortality, including its x2 for
  Soldier-occupation agents at war (`demographics.rs`; separating it needs a native change, D3),
  plague and other non-war catastrophes. No actor.

Militia, mercenary and civilian deaths are not roster soldiers and are not here (battle records
count them). A roster-less army's casualties (aggregate mode) are drained across its civilization's
regions; hybrid armies always have rosters.

Checks:
- `armies`: per live army, the deaths recorded this turn against the change of its own casualty
  counter since the last commit (`closes`; None without a baseline: an army new to the records, or
  gone). Both writers of the counter (`apply_casualties`, `reconcile_rosters`) note the same
  number, so this proves only that no note was dropped (and would catch a third writer); it does
  not validate the cause split.
- `battle_checks`: per battle and side, the battle deaths recorded for that side's armies, at most
  the side's losses in the battle record (which also count mercenaries and garrison): a death
  resolved to the wrong battle or side shows (`holds` false).
- `unresolved`: combat deaths whose battle record did not match.

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
= 256 per turn; `entries_dropped`; the pairs stay exact). `zero_events`: per kind, events that
moved nothing (no plunder from a region of fewer than ten people, nothing left to spend, seize or
destroy); they are counted there, not in the pairs, so a consumer counting `events` sees only
real burdens (restrictions keep their zero-route events). `retail_unattributed`: retail war
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

Natures: `transfer` (paid to the actor), `minted` (credited to the actor, taken from nobody:
today's plunder and occupation requisition), `destroyed` (lost, received by nobody: today's food
requisition, seized granary grain, conquest losses), `restriction` (no amount moves). Payers:
dues and sacks are paid from the city's purse (its abstract commerce), not from the victim
polity's treasury; dues are assessed at Phase 10 and paid at the next Phase 2 in whole units with
the fraction carried, and dues owed to a lord dead by then are dropped, so `city_dues` is an
assessed transfer; a sack without a sacker credits nothing and is recorded wholly as
`city_sack_loss`; a treaty payment is paid from the loser's treasury. The commons food a
requisition destroys is derived from the commons after the cut and the factor
(`after x (1 - f) / f`, float rounding). `conquest_stock_loss` sums different goods into one
`goods` amount; its food part is in the entry's `detail`. City dues are internal pairs (the lord
is the region's controller); the levy's part is `commerce x LEVY_SHARE` while a levy stands. Not
recorded in this slice: diplomacy tribute installments, vassal tribute, siege and occupation
civilian deaths, the cost-only quarantine declarations (they restrict nothing).

## Guard: decisions never read provenance

`tests/test_provenance_decision_guard.py` (AUDIT-D 7.3 item 7). It walks every module under
`src/chronicler` except the narration and curation modules (`provenance`, `curator`,
`narrative`, `narration_context`, `historiography`, `narration_provenance`, `narration_audit`)
and collects every read of provenance: a call of, or any other reference to, a provenance read
function through the module (resolved from absolute and relative imports, `f = prov.recall`,
`getattr(prov, "recall")`), an `import_module`/`__import__` of the provenance module, and every
read of an attribute `provenance`, `causes` or `episode` (as an attribute, through
`getattr`/`hasattr` with a constant name, as a constant subscript such as `vars(w)["provenance"]`,
or through `.get` with a constant key). Every read site must be registered with a reviewed
classification (`cites`, `labels`, `filters`, `analysis` for the three bundle-reading audit and
forensics tools, `decision`); the test fails on an unregistered site, a changed count, a stale
row, a new `decision` row, or an undeclared read function in `provenance.py`. The D-program record
and war modules read none.

Limits (not caught): a name computed at run time (`getattr(x, name)` with a non-constant name,
`eval`/`exec`); a value that flows from a registered `cites` helper into a decision elsewhere (the
classification is a human review per reading function, so a new `cites` row must be read like
code, callers included); a read hidden behind a non-provenance helper; and the provenance-shaped
timeline itself: `provenance.observe` folds chronic repeats of some event types, so a decision
that reads timeline events (for example `cities._record_misfortune`) sees the folded timeline
([causal provenance](causal-provenance.md), Chronic conditions).

The review found seven sites where a decision reads provenance, against the contract in
[causal provenance](causal-provenance.md) ("no simulation decision reads it"). They predate this
guard and stay unchanged (a change goes behind a switch for the owner's decision); they are
recorded as defects (`KNOWN_DECISION_READS`). Four run on the default path of a new world
(cities, diplomacy, nomads and epidemiology with the contact ledger are on by default); the three
scholarship sites run only under `--scholarship` (off by default):

| Site | Decision | Default |
| --- | --- | --- |
| `cities._lord_change` | a conquest or occupation key within one turn turns a lord change into a sack | on |
| `diplomacy._aid_convoys` | famine `tick` repeats are skipped, so aid follows crisis onsets only | on |
| `epidemiology._reports` | an open epidemic episode suppresses the arrival event and the row's source reset | on |
| `nomads._herds` | a recalled drought key gates the `pasture_drought` event | on |
| `scholarship._newly_occupied` | an occupation key of this turn strikes a seat | off (`--scholarship`) |
| `scholarship._sack_cause` | a sack, conquest or occupation key makes a lord change hostile and blocks a founding | off |
| `scholarship._in_famine` | an open famine episode blocks a founding | off |

## Viewer

The Livelihoods tab mounts the panel whenever any snapshot of the run carries the record. Six
readings stay distinct: disabled (off in the run), absent (on in the run, missing at this
snapshot: unknown), malformed (refused, with the reason; nothing shown), unobserved (`frame:
null`), recorded zero (observed, nothing attributed; granaries off reads as not observed, not
zero) and recorded (deaths by war, victim, actor and cause, with the war-drain class; failed
battle checks; seizures with the stale books owner; burden pairs with nature and unit; zero-amount
events; identity events). Types are in the new `viewer/src/lib/attributionRecords.ts` (`types.ts`
is pinned); `battle_checks`, `war_drains` and `zero_events` are optional to the reader, so records
written before the review revision still read.

## Verification

Linux container, Python 3.13.18. Source: `main` `8401aa74` (PR #88, A3) merged into the branch
after `ae94bca6` (PR #87, C1b); review fixes on top; the Python tree under test is commit
`9d047965` (later commits change only tests, the viewer and docs). Native extension SHA-256
`20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca` (`~/.venvs/native-a3`,
built by lane A3; its Rust is identical to `main` `8401aa74` and to the head: no Rust changed in
this slice, nothing was built here).

- **Focused (offline):** `tests/test_attribution_records.py` 45 passed (constructed war
  scenarios: field battle, trapped, revolt, attrition, natural deaths on one army, war-drain and
  possibly-enemy deaths, each drain site's actor, battle checks, two battles of one civilization
  in one turn, siege/occupation/conquest seizures, two conquests in one turn, an unattributed
  seizure, restoration through `politics.check_restoration`, a new index with an old name,
  occupation plunder and turns, zero-amount events and a sack without a sacker, treaty payment,
  quarantine closure, city dues and sack, guild levy split, retail war losses twice in one turn,
  the entry cap, the note sites, observer identity, the reader states);
  `tests/test_provenance_decision_guard.py` 5 passed (with every read form in a probe package);
  with the registry, retail, quarantine, A3, catalog, manifest and every witness module: 793 passed.
- **Bounded offline lane** (`scripts/run_python_oracle_checks.py`, default output directory):
  PASS, 70 chunks, 14,549 tests, 338.4 s; slowest chunk `systems-2` 40.6 s of 110 s (shared
  4-core machine); `connected-world-d` 9.9 s (50 tests).
- **Native:** `tests/test_attribution_records_native.py` (observer identity on procedural 32x10
  seed 13, 60 turns, and on template seed 42 with every livelihoods payer, 40 turns; a natural war
  run attributed and closing; retail war losses all attributed) with the offline modules,
  `test_wealth_accounting_native.py`, `test_household_retail_war_native.py`,
  `test_quarantine_migration_native.py` and `test_workshop_economics_native.py`: 77 passed in 90.9 s.
- **Feature-off identity** (`scripts/turn_speed_identity.py`, 9 cases, each side its own source
  tree and extension): head against the `8abc1acb` reference outputs (extension `101a4cd5...`):
  9 cases, 399 files compared, 0 differences.
- **Observer identity** (hybrid, every switch): `hybrid_s42`, `hybrid_s7` and
  `proc48_hybrid_s42` with the catalog's all-on livelihoods set (retail in every region),
  `--workshop-economics`, `--wealth-accounting`, `--finance --domestic-credit`, `--quarantine-mode
  closure --quarantine-channels trade,migration`, with and without `--attribution-records`: 3
  cases, 317 files compared, 0 differences after removing only the record (every
  `attribution_records` key and a container that held nothing else; bundles decoded without
  `generated_at`); 550 snapshots carry the record (45 battle checks, none failed).
- **Exact resume** (`scripts/checkpoint_identity.py`, `hybrid_s42_long`, 200 turns, the same
  all-switch set plus `--attribution-records`): writing checkpoints changes nothing and every one
  of the 19 resume points equals the straight run (0 differences; the points at turns 1, 2, 3, 5,
  8 and 13 fall inside live armies or occupations, so the army baselines and the civilization
  table cross the checkpoint).
- **Viewer:** `npm test -- --maxWorkers=2` 161 files, 1,595 passed, 2 skipped; `npm run lint` clean;
  `npm run build` passes (the existing large-chunk warning).
- **Preflight** (`refactor_preflight.py --git-diff origin/main`): the only content-pinned files
  are `batch_manifest.py` and `tests/test_batch_manifest.py`, carried by the provisional layer
  `cwd2` (two hunks and one, read: the new key in `SIMULATION_ARG_KEYS` and in the omit-when-unset
  lists), built against `main` `8401aa74` as the last layer (`LAYERS = (..., "cwc1b", "cwa3",
  "cwd2")`); the witness modules pass. The lead regenerates one integrated layer per slice.

### Development worlds (development only; not a held screen)

Template 1, 3, 7, 9, 11, 23, 42 and procedural 32x10 seeds 7, 11, 13, 17, 21, 31, 200 turns each,
`--agents hybrid --grain-reserves --attribution-records`, default campaigns, `PYTHONHASHSEED=0`,
on the review revision. No combat death went unresolved, no army closure failed (978 checked,
110 unchecked), no battle check failed (297), no seizure went unattributed and no restoration
happened in these runs; 175 burden events moved nothing (`zero_events`).

| World | Observed turns | Soldiers' deaths combat / attrition / war drain / natural | Army closures held / failed / unchecked | Granary seizures (grain; stale books owner; unattributed) | Identity events |
| --- | --- | --- | --- | --- | --- |
| t1 | 200 (5 zero) | 14 / 2 / 0 / 2 | 48 / 0 / 8 | 0 (0.0; 0; 0) | 0 |
| t3 | 200 (9 zero) | 4 / 0 / 0 / 1 | 11 / 0 / 2 | 0 (0.0; 0; 0) | 0 |
| t7 | 200 (15 zero) | 8 / 0 / 2 / 3 | 13 / 0 / 2 | 10 (6.0; 0; 0) | 0 |
| t9 | 200 (9 zero) | 5 / 0 / 0 / 0 | 20 / 0 / 2 | 0 (0.0; 0; 0) | 0 |
| t11 | 200 (6 zero) | 21 / 1 / 1 / 3 | 20 / 0 / 3 | 0 (0.0; 0; 0) | 0 |
| t23 | 200 (8 zero) | 12 / 0 / 0 / 4 | 21 / 0 / 4 | 0 (0.0; 0; 0) | 0 |
| t42 | 200 (3 zero) | 15 / 7 / 0 / 0 | 37 / 0 / 6 | 0 (0.0; 0; 0) | 0 |
| p7 | 200 (11 zero) | 70 / 11 / 4 / 20 | 134 / 0 / 12 | 13 (21.6; 0; 0) | 0 |
| p11 | 200 (6 zero) | 10 / 1 / 1 / 0 | 40 / 0 / 6 | 5 (0.7; 0; 0) | 0 |
| p13 | 200 (1 zero) | 67 / 11 / 0 / 17 | 212 / 0 / 18 | 24 (34.4; 0; 0) | 0 |
| p17 | 200 (4 zero) | 49 / 7 / 2 / 10 | 135 / 0 / 13 | 0 (0.0; 0; 0) | 0 |
| p21 | 200 (7 zero) | 86 / 12 / 2 / 11 | 208 / 0 / 25 | 8 (9.1; 0; 0) | 0 |
| p31 | 200 (0 zero) | 39 / 3 / 2 / 5 | 79 / 0 / 9 | 9 (8.3; 0; 0) | 0 |

Burdens summed over the 13 worlds (2,600 observed turns; events with an amount; cross-polity:
actor and victim differ):

| Burden kind | Nature | Unit | Total amount | Events | Cross-polity events |
| --- | --- | --- | --- | --- | --- |
| city_dues | transfer | treasury | 3296.3 | 14988 | 0 |
| city_sack | transfer | treasury | 28.0 | 4 | 4 |
| city_sack_loss | destroyed | treasury | 0.7 | 4 | 4 |
| conquest_stock_loss | destroyed | goods | 307.1 | 20 | 20 |
| food_requisition | destroyed | food | 815.4 | 141 | 141 |
| granary_seizure | destroyed | grain | 80.1 | 69 | 69 |
| guild_levy | transfer | treasury | 111.9 | 1139 | 0 |
| occupation_plunder | minted | treasury | 71.0 | 28 | 28 |
| occupation_requisition | minted | treasury | 158.0 | 158 | 158 |
| occupation_tax_loss | destroyed | treasury | 280.0 | 141 | 141 |
| treaty_payment | transfer | treasury | 394.0 | 22 | 22 |

What the records show on these worlds:

- Army casualty counters merge 400 combat, 55 attrition, 14 war-drain and 76 natural deaths:
  90 of 545 soldiers' deaths (17%) were not campaign casualties, and 14 of those died where a
  siege, garrison fight, occupation or crushed revolt had staged deaths that turn (each region's
  drains named one actor; no `possibly_enemy` death occurred).
- Every recorded cross-polity treasury burden of war but treaties and sacks is minted or
  destroyed: occupation plunder (71) and requisitions (158) are credited to occupiers and taken
  from no one, while owners lose 280 to occupation, spent into nothing. The real cross-polity
  transfers are treaty payments (394) and sack plunder (28). Food requisitions destroy 815 food
  units and granary seizures 80 grain that no army receives.
- City dues (3,296) and guild levies (112) are all internal: a city's lord is its region's
  controller, so they ground no foreign grievance.
- Granary books stayed current (no stale owner) in these campaign runs: a stale books owner needs
  two conquests of one region in one turn (`--no-campaigns`; tested offline).

Evidence (outside the repository): `/home/user/evidence/d2/` (first revision) and
`/home/user/evidence/d2/r2/` (review revision: identity, native, feature-off, observer, resume,
oracle lane and development outputs).

## Not done in this slice

- No consumer: no grievance, diplomacy or movement reads the record (by design; D1 decides a
  replacement behind its own switch).
- The native soldier-at-war x2 mortality stays inside `natural` (needs a native change, D3); a
  `war_drain` death may still be natural (the native tick does not say which).
- The seven pre-existing decision reads of provenance are recorded, not changed.
- Diplomacy tribute installments and vassal tribute are not itemized.
