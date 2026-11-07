# Residence ledger (X1, `--residence-ledger`): the displacement contract

Lane X1 of the connected-world program; the lead-owned displacement contract shared by C2
(crowding), D3 (war's human consequences) and A6 (adaptive decisions). Specification: audit A6
sections 9–11 (definitions 11.1, one writer 11.2, dated persistence 11.3, readers 11.4, relation
to existing records 11.5), adopted by the lead as the spec; plan section 2 records the contract.
Code: `src/chronicler/residence_ledger.py`, `residence_ledger_state.py`; viewer
`viewer/src/lib/residenceLedger.ts`, `components/systems/ResidenceLedger.tsx`; report
`scripts/residence_ledger_report.py`.

## Why

"Displaced" meant three things, none fit for a consumer: the native `displacement_turns`
counter ("moved in the last 5 turns", whatever the reason: 26–29% of the living on development
worlds), `origin_region` (the birth region, never updated: 68–70% live away from it) and the
bridge's `displacement_by_region` share (the counter again, for narration). The ledger keeps one
dated record of where each person lives, where they belong and why they left, with the cause and
the home-region event, so each consumer selects its own subset: C2 every spell, D3
`anchor == war`, A6 the person's own.

## The switch

`--residence-ledger` (default off; `--no-residence-ledger` ends it). Hybrid only: refused in
every other agent mode, also when only saved ("pass --no-residence-ledger to end it"). Record
only: no modes. Registered in `feature_catalog.REQUIREMENTS` (`{"agents": ["hybrid"]}`, the
Livelihoods group), so the compatibility matrix includes it in every pair, drop and all-enabled
selection (`tests/test_feature_matrix.py`). In `LIVELIHOODS_SWITCHES` it sits immediately after
`workshop_economics` and before `attribution_records` and `wealth_accounting`, so its Phase 10
hook runs after every acting package and before D2's records and A1's ledger. B3's
`infrastructure_condition` also goes before `attribution_records`: whichever lands second places
them `infrastructure_condition, residence_ledger` (infrastructure first) and updates the order
tests (`test_wealth_accounting.py::SWITCH_ORDER`, `test_attribution_records.py`,
`test_residence_ledger.py`).

A world that never enabled it has no sub-state, no snapshot key, no checkpoint flag and no
manifest key: feature-off output is byte-identical (verified below).

## Definitions (audit 11.1, as implemented)

- **Residence** `res`: the native region after the tick. A merchant on a native trip keeps the
  residence last recorded (a trip is not a migration). A traveller alive when first seen is
  recorded at the end of its trip (`deferred`).
- **Location** (record only): the residence, except a merchant in transit (the snapshot region)
  and a person on an army roster (the army's region). v1 records it as aggregates
  (`in_transit` by residence, `attached_away` by home), not per person.
- **Attachment**: `(army_id, army region)` from the rosters after `reconcile_rosters` at T, else
  none. Enlistment never re-homes. An army dissolved at the end-of-turn sync is still attached
  in T's frame and gone at T+1 (declared).
- **Home**, dated `home_since`: the residence at first observation (the birth region for a
  person born after it). It changes only when a voluntary or unclassified move is applied (a
  migrant re-homes at once), or when an open spell resettles after `REHOME_TURNS = 20` turns at
  one residence.
- **Displacement spell**: opened when an applied move leaves home and its driver is in C1b's
  `FLIGHT_DRIVERS` (cause `flight`) or `HUNGER_DRIVERS` (`hunger`), imported from
  `quarantine_rules` (one source). A household follower's event carries its lead's driver
  natively (`behavior.rs`), so the follower opens the same spell. Fields: `start`,
  `origin = home`, `cause`, `anchor` and `anchor_kinds`, `anchor_partial`, `moves`.
  **Displaced** = an open spell.
- **Anchor**: the home-region event dated in the `ANCHOR_TURNS = 5` turns before the departure:
  `war` (a controller change, an occupation or a conquest), `famine` (a famine or dearth report:
  `famine_cooldown` at its onset value 5), `persecution` (`persecution_intensity > 0`); the first
  present in that order is `anchor`, every kind present is kept in `anchor_kinds`; `none` without
  one. `anchor_partial`: the window reaches before the ledger watched the regions (the first five
  turns of an observation epoch).
- **Closures**: `returned` (residence equals home after a move), `resettled` (home becomes the
  residence; the event's `by` says `rehome_turns` or `move`), `died`, `pool_reset`,
  `unobserved_gap`.
- **Separated** (D3; computed on demand by `separation`, never stored): a married partner, or a
  dependent child's (age below 20, native `AGE_ADULT`) parent, alive with a different residence
  or location, with the cause `trip`, `attached`, `displaced` or `migrated` (first that applies).

### Decisions within 11.1 (for the lead)

1. **A displaced person's voluntary or unclassified onward move resettles the spell** at the
   destination (`by: "move"`), as 11.1 reads ("home changes only when a voluntary or unclassified
   move is applied"). The audit's probe kept such spells open. This is the main reason the
   ledger's displaced shares are below audit section 10's (measured below: with the probe's rule
   the ledger reproduces section 10 within 0.01). Changing it is one branch in `_move`; it
   changes D3's meaning of "return" (audit 14, question 1).
2. **Anchor dating** follows when the event happened relative to the tick. Read at Phase 10 of
   T: a conquest (`last_conquered_turn == T`, Phase 5), an occupation (Phase 5) and a famine onset
   (Phase 9 ecology) dated T precede T's agent tick and anchor T's departures. A controller
   change without a conquest (secession, cession, absorption; mostly Phase 10) and persecution
   (computed in Phase 10; T's tick persecuted by T−1's reading, which is in the window) dated T
   anchor departures from T+1. The probe counted same-turn controller changes for T; the
   war-anchored share on procedural 13 is 0.0056 here against 0.0082 with the probe's onward rule.
3. **A second native relocation path.** Audit 11.2 says only `apply_migrations` relocates
   ordinary agents. A merchant trip unwound on a conquest (`merchant.rs`, `reset_trip_fields`
   without a return) leaves the traveller in its current transit region. The ledger recognises
   it (`travelling`, the ids on a trip at the last write) and records it as an unclassified
   relocation (`trip_relocations`; re-homes, or resettles or returns an open spell, with
   `relocation: true` on the event); anything else not explained by a move is counted as
   `unexplained_relocations` and applied the same way. Measured: 7 trip relocations (2 of them
   in the same tick as a move) in 120 turns of procedural 13; no unexplained relocation in any
   run. The native code is unchanged (a correction to the audit's statement, not a defect fix).
4. **Switching off** closes open spells as `unobserved_gap` and drops the rows, the frame and the
   region watch (counters and log kept); switching on again starts a new epoch.
5. **Per-person events** (spell openings and closures by stable id, at most 512 per turn) are in
   the snapshot record for the viewer, narration and analysis, never in `read_frame`.

## One writer (audit 11.2)

The livelihoods `phase10` hook of turn T (`simulation.py`, after `reconcile_rosters`, every
acting package and the granary procurement; before D2's records and A1's ledger) reads:

- T's applied native migrations with their drivers (`world.agent_events_raw`, event type
  `migration`, as RS4 reads them);
- the post-tick snapshot (`id`, `region`, `origin_region`, `displacement_turn`) and
  `trip_agent_ids()`;
- the army rosters;
- region state for the anchors (controller against its own previous reading, `occupied_by`,
  `last_conquered_turn`, `famine_cooldown`, `persecution_intensity`).

It registers no agent-tick hook, so the post-tick snapshot hand-over is unchanged, and reads
relationships only when `separation` is asked (a test fails the writer if it reads them). No
native change.

## Dated persistence and the record (audit 11.3)

State (`world.livelihoods.residence_ledger`, checkpointed, omitted while off): one row per
observed living person by stable id (home, home_since, residence and since, first seen, the last
move with its driver, the open spell, the attachment), at most `MAX_ROWS = 262,144` (refusals
counted); one watch row per region; `observed_from`; the frame of the last observed turn.

Snapshot record `snapshot.livelihoods.residence_ledger` (stage `X1`, `source_turn = T`): `frame`
(None when T was not observed: unknown, not zero) with `totals` (`TOTAL_KEYS`) and `regions`
(`REGION_KEYS`, regions with anything recorded): open spells by residence, cause and anchor, by
origin; this turn's departures by driver group (flight, hunger, voluntary, other), arrivals and
displaced arrivals; spells opened (by departure region), returned (by home), resettled and died
(by residence); deaths; attached and attached away (by home); merchants in transit; and two
comparison counts with the measures this contract replaces (`recent_movers_native`,
`away_from_birth_region`). Then `events`, `counters`, `log`, `labels` and `parameters`.
`record_status` (the reference reader): absent, malformed, unobserved, recorded_zero (no one
displaced or attached, no move, opening, closure or death), recorded.

Resume: an exact resume restores everything (pickled state). A legacy state-file resume rebuilds
the native pool; the first livelihoods hook calls `on_pool_reset`, which closes open spells as
`pool_reset` (reported in that turn's frame), drops the rows and restarts observation
(`observed_from` = the resumed turn). Nothing is rebuilt from the saved rows. A turn the writer
did not run (an observation gap) closes open spells as `unobserved_gap`.

Cost: per turn one snapshot read and a pass over the rows (O(alive + moves + regions +
roster)). Record: hybrid_s42 bundle 3.19 → 3.61 MB over 200 turns, proc48_hybrid_s42 9.1 →
10.2 MB. The rows are in the final world state (bundle and `state.json`) at about 200 bytes a
person: on the 43,700-agent scaled case the bundle grows 0.7 → 9.9 MB and `state.json` 0.7 →
18.2 MB. Only exact checkpoints continue the rows, so a compact row encoding, or leaving the rows
out of JSON with a count for the pool-reset report, is a possible follow-up for the lead.

## Readers (audit 11.4)

| Reader | Function | What it returns | Dating |
| --- | --- | --- | --- |
| C2 crowding, C4 and ruler decisions | `read_frame(world, consumer_turn=)` | T's aggregates (a copy): totals and region rows, no person | refuses `consumer_turn != world.turn` and a frame of `consumer_turn` or later (same-turn/future, `LedgerReadRefused`); None when T was not observed or the ledger is off |
| A6 | `own_row(world, agent_id, consumer_turn=)` | the person's own row as of T | as above |
| D3 | `separation(world, agent_bridge, consumer_turn=)` | separated pairs with relation and cause, counts by cause and relation | as above; native bonds, parents and trips are read at the call: exact between T's write and T+1's agent tick (nothing native changes in between); a call after T+1's tick pairs T's residences with T+1's bonds |
| viewer, narration, analysis | `snapshot_summary` / `record_status` | the record | completed turns only |

**Guard** (`tests/test_residence_ledger_guard.py`, the D2 provenance guard's approach): every
module under `src/chronicler` but the ledger's own is walked; a read of the ledger's state
(`.residence_ledger`, `getattr`/subscript/`.get` with that name, an import of
`residence_ledger_state`) is refused outside the owners and the switch wiring; a reference to
the ledger module must be registered as `aggregate` (`read_frame`), `own_row` (only A6's
`adaptive_livelihoods`), `separation` (only D3 modules, none registered yet) or `record` (only
narration and analysis modules). Today no decision module reads the ledger; every consumer
registers its read there with its review. The guard also checks the ledger is structurally
record-only (it assigns no world attribute but its own container slot and calls only
`get_snapshot`, `trip_agent_ids` and `get_all_relationships` on the simulator), that its public
names are declared, and that the bridge's displaced share stays with narration (`agent_bridge`,
`main`, `narrative`, `historical_context`). The D2 provenance guard now also covers the ledger
(it reads no provenance).

## Relation to existing records (audit 11.5)

- **RS4** keeps its own diaspora ledger (one entry per mover from the first move, onward moves
  keep the origin). Where both describe the same journey they agree
  (`test_residence_ledger_native.py::test_rs4_and_the_ledger_agree_on_origins_returns_and_deaths`,
  template 7, 60 turns, both on): a spell opened by a person's first RS4 departure has RS4's
  origin; a ledger return (by a move) of RS4's origin closes RS4's entry as a return in the same
  turn and every RS4 return leaves the person living at its origin (closing the ledger's spell of
  that origin); a ledger death closes RS4's entry in the same turn (as a death, or as a return
  when the dying person's last move reached RS4's older origin first).
- The bridge's displaced share stays narration-only (guard above); the native cooldown and birth
  region are unchanged (no native change; feature-off identity).

## Viewer

Livelihoods tab, "Residence and displacement" (mounted on the run's records, so a snapshot
without one reads as absent): the displaced share by cause and anchor; open spells by region
(residents, displaced here by cause, by anchor, displaced from here); this turn's departures by
driver group, arrivals (displaced), openings, returns, resettlements, deaths while displaced and
deaths by region; people on army rosters by home region and those whose army is elsewhere,
merchants in transit; the comparison measures; and the last eight snapshots, each read on its own.
Readings go through `recordReading.ts` (`readResidenceLedger`): disabled, absent, malformed,
unobserved, recorded zero and recorded stay distinct. Tests:
`lib/__tests__/residenceLedger.test.ts` (a natural record of procedural 13 and constructed
edits), `components/systems/__tests__/ResidenceLedger.test.tsx`.

## Development-world evidence (not a screen; never held seeds)

Template 7 and procedural 32×10 seed 13, hybrid, read by `scripts/residence_ledger_report.py`
(means over the last three quarters of the turns, as audit section 10). Compact outputs:
`/home/user/evidence/x1/measure/` (outside the repository).

**Audit section 10 reproduced on the same trajectories.** Configuration C of the audit (plain
hybrid plus RS4; template 7 200 turns, procedural 13 120 turns), the audit's probe and the ledger
in one process (the probe reproduced its published numbers exactly, so the ledger changed
nothing it observed):

| Definition (share of the living) | probe t7 | ledger t7 | ledger, probe's onward rule t7 | probe p13 | ledger p13 | ledger, probe's onward rule p13 |
| --- | --- | --- | --- | --- | --- | --- |
| native cooldown | 0.292 | 0.292 | 0.292 | 0.283 | 0.283 | 0.283 |
| away from the birth region | 0.698 | 0.698 | 0.698 | 0.682 | 0.682 | 0.682 |
| open spell (flight or hunger from home) | 0.598 | 0.572 | 0.598 | 0.482 | 0.415 | 0.482 |
| the same, flight only | 0.535 | 0.516 | 0.534 | 0.397 | 0.341 | 0.397 |
| the same, famine or war anchor | 0.517 | 0.488 | 0.508 | 0.289 | 0.258 | 0.284 |
| the same, war anchor | 0.0006 | 0.0006 | 0.0006 | 0.0089 | 0.0056 | 0.0082 |

The comparison measures are equal; with the probe's rule for onward moves (an analysis-only
variant, `measure/variant_keep_spell.py`) the spell shares match within 0.01 and the resettlement
counts match (180 against 182, 346 against 346); the remaining anchor difference is the stricter
dating (decision 2). The contract as implemented (decision 1) resettles 301 (t7) and 683 (p13)
spells, 120 and 337 more than the probe.

**Ledger alone** (no RS4; 200 turns each):

| | template 7 | procedural 13 |
| --- | --- | --- |
| living (range) | 104–272 | 458–804 |
| displaced share (flight · famine-or-war anchor · war anchor) | 0.491 (0.387 · 0.394 · 0.000) | 0.427 (0.362 · 0.280 · 0.0003) |
| spells opened (flight / hunger) | 1,096 (858 / 238) | 3,017 (2,579 / 438) |
| opened by anchor (war / famine / persecution / none) | 1 / 849 / 72 / 174 | 31 / 1,739 / 581 / 666 |
| closed: returned / resettled / died | 356 / 313 / 379 | 884 / 980 / 977 |
| median length: returned / resettled / died | 9 / 20 / 10 | 9 / 20 / 10 |
| pool resets, unobserved gaps, unexplained relocations | 0, 0, 0 | 0, 0, 0 |

War-anchored displacement is rare on both worlds (one spell in 200 turns of template 7; 31 on
procedural 13, 0.03% of the living on average); famine anchors dominate. For C2 the stock of open
spells is high everywhere (43–49% of the living), as audit 14 question 6 anticipated; this turn's
displaced arrivals are recorded beside it.

## Verification (lane X1, 2026-11-07; Linux, Python 3.13, native extension `20e77f99…` = main's Rust, no native change)

- **Offline**: `tests/test_residence_ledger.py` (39) and `tests/test_residence_ledger_guard.py` (7)
  in the new oracle chunk `connected-world-x`; the D2 provenance guard extended; the order tests
  (`test_wealth_accounting.py`, `test_attribution_records.py`), feature catalog and matrix, batch
  manifest and witness suites pass. `scripts/run_python_oracle_checks.py`: PASS, 71 chunks in 295.0 s (slowest chunk 34.2 s of
  110 s; `connected-world-x` 5.9 s, 46 passed).
- **Native** (`tests/test_residence_ledger_native.py`, shard 0, 7 tests, 20 s): record-only
  identity on template 7 (with RS4) and procedural 13 (40 turns each: history, world state,
  `state.json`, chronicle and agent events equal after removing the record); frame invariants on
  60-turn runs (region rows sum to the totals, the stock moves by openings minus closures, the
  events match the counts, no unexplained relocation); RS4 agreement; an exact resume at turn 12
  inside open spells; a legacy state-file resume (pool reset, nothing carried over); separation
  read at the next turn before its tick. Offline lane: the module skips.
- **Witness**: layer `cwx1` (parent `bac45cb5`) inverts the two pinned edits
  (`batch_manifest.py`, `tests/test_batch_manifest.py`), appended last in `LAYERS`; the
  livelihoods sprint witness and every chained witness suite pass.
- **Feature-off identity** (`scripts/turn_speed_identity.py`, 9 cases, each side its own source
  tree): head against the `8abc1acb` reference outputs: 9 cases, 399 files, 0 differences; head
  against `main` `bac45cb5`: 9 cases, 399 files, 0 differences; explicit `--no-residence-ledger`
  (hybrid_s42, proc48_hybrid_s42): 203 files, 0 differences.
- **Record-only identity**: ledger on against off, every file equal after removing only the
  record: the six hybrid cases (hybrid_s42, hybrid_s7, hybrid_s1234, proc48_hybrid_s42,
  scaled22k_s42, scaled52k_s7): 366 files, 0 differences (800 snapshots carry the record); with
  every catalog switch on (template and procedural all-enabled sets, retail in every region, D2,
  A1, quarantine closure with the migration channel): 205 files, 0 differences.
- **Exact resume** (`scripts/checkpoint_identity.py`, `--cli-arg=--residence-ledger`):
  `hybrid_s42_long` PASS at 19 resume points (16 with open spells, 6 with armies on campaign);
  `proc32_hybrid_s11` PASS at all 39 (37 with open spells, 23 with armies); writing checkpoints
  changes nothing (111 and 40 files, 0 differences).
- **Viewer**: `npx vitest run --maxWorkers=1` 163 files, 1,626 passed, 2 skipped (a first run under
  concurrent identity load timed out one unrelated FeatureOptions case at 5 s; alone it passes); `npm run lint` clean; `npm run build`
  passes (the existing large-chunk warning).
- **Preflight** (`refactor_preflight.py --git-diff origin/main`): content pins only on
  `batch_manifest.py` and `tests/test_batch_manifest.py` (covered by `cwx1`); the other enforced
  entries are test-module enrollment (shard owner, oracle chunk).

## Not done in this slice

- No consumer: C2, D3, A6 and C4 register their reads in the guard with their own review.
- Location per person, D3's `evacuated` cause and the labour reservation (audit 12) are out of
  scope.
- No held screen; development worlds only.
