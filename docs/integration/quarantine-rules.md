# Quarantine rules: a real, dated trade restriction and its costs

Connected-world program, slice C1 (branch `claude/cw-c1-quarantine`, from the program branch
`claude/connected-world` at `bfe51ba`, itself on `main` `8abc1acb`). Code:
`src/chronicler/quarantine_rules.py`; hooks in `epidemiology.py` (`_introduce`,
`_decide_quarantine`, the snapshot and analytics), `resources.py`
(`_compute_active_trade_routes`), `contact_ledger.py` (`observe_phase2`), `agent_bridge.py` (the
two agent-tick merchant-graph sites), `expansion_features.py` and `livelihoods.py` (parser,
forwarding, configuration and the exact-resume seam), `feature_catalog.py` and
`batch_manifest.py`. Design source: the Program C contract audit
(`docs/superpowers/audits/connected-world/audit-c-public-health.md`, sections 2, 6.1 and 7) and
the lead's decisions in `docs/superpowers/roadmaps/connected-world-program.md` section 5.3.

Status: implemented behind `--quarantine-mode`, **default legacy** (the option omitted). With the
option omitted the epidemic model's existing quarantine runs byte for byte as before; nothing in
this page applies. Experimental and opt-in; not promoted. C1 was screened on held worlds (CW4,
below); the migration channel of slice C1b (`--quarantine-channels trade,migration`,
[below](#migration-closure-c1b)) is not screened yet.

## Why

The epidemic model's quarantine moved nothing ([epidemiology](epidemiology.md)). A state in
contact with a reported foreign outbreak paid 2 treasury and multiplied the foreign import
pressure on its regions by `1 - efficacy` (0.7, up to 0.9 with law codes and lazarets), on all
four contact channels at once. The flat charge "stood in for lost commerce". A routing-based
quarantine has two double-count traps: the multiplier would cut exposure a second time on the
stock that routing already stops growing (and on channels routing never touched), and the flat
charge would stack on the route income the closure really costs.

## Modes

| `--quarantine-mode` | Decisions | Cost | Journeys restricted | Import multiplier |
| --- | --- | --- | --- | --- |
| omitted, or `legacy` | as before | 2 treasury per closed state-turn | none | 0.7-0.9 on foreign pressure |
| `none` | none | none | none | none |
| `cost_only` | as `closure` | enforcement cost | none | none |
| `closure` | targeted closures | enforcement cost; real route income and trade losses emerge | trade (below) | none |

`legacy` is listed as a choice so the feature catalog's convention holds (the first choice is the
run's rule when unset). An explicit `legacy` is the option omitted: it installs nothing, needs
neither epidemiology nor the ledger (so a screen can forward it to an epidemics-off control arm)
and writes the same world as omitting it, with epidemics on or off
(`test_an_explicit_mode_needs_epidemiology_and_the_ledger`). Its one difference: on a world that
already carries rules of another mode it is a conflicting request and is refused.

- `none`, `cost_only` and `closure` require epidemiology and the contact ledger. Epidemics are on
  by default for new worlds with the ledger; one of these modes with `--no-epidemiology` or
  `--no-contact-ledger` (or on a world without them) raises `ValueError`.
- Valid in every agent mode (`off`, `demographics-only`, `shadow`, `hybrid`): the closure is
  Python-side.
- Saved on the world: `EpidemicState.quarantine_rules` (omitted from `state.json` and the bundle
  while None; read with `getattr`, so checkpoints pickled before this slice load).

## The decision

Phase 1 of turn T, at the end of the epidemic tick, with information available at the time: this
tick's outbreak reports (`cases >= max(2, 3% of the region)`) and the contact ledger. The trigger
is the legacy one, so the change of mechanism is isolated from any change in the decision:

- a living polity with stability >= 30 and treasury >= the enforcement cost,
- in ledger contact (any channel, either direction) with a region that reported an outbreak this
  tick and that **another polity controls**,

closes against **each polity controlling such a region** (targeted, not "all foreign": the
lead's decision). An outbreak in an uncontrolled region has no route to close and opens no
closure. A closure follows polities, not territory: if a closed target's sick region changes
hands during the turn, the new controller's border stays open until the next decision (a one-turn
lag). A closure decided at T applies to the journeys of T (the Phase 2 routes, the TRADE
action and the agent tick of T), is **renewed** at T+1 while the trigger still holds and
**lapses** otherwise. `state.quarantine` (closing civ indices) stays filled in every mode, so the
existing viewer chips and `quarantine_turns` analytics keep working; in `none` it is empty.

Each closing polity emits the existing `quarantine` event (a chronic episode per state, so repeats
fold and `quarantine_ended` follows), citing the first threat's outbreak report: "X closes its
borders to trade with Y against the plague raging in Z." (`closure`) or "... declares a quarantine
against Y ..., paying for border watch but closing no route." (`cost_only`).

No new random draws: polities, threats and targets are visited in sorted order.

## What closes (`closure`)

For every closed pair (closing polity, target polity), in both directions:

1. **Economy trade routes of every kind** (adjacency, NAVIGATION/RAILWAYS two-hop, techniques
   extension, federation): one post-filter at the end of `resources._compute_active_trade_routes`.
   Everything that reads the route set follows: route income (+2 per route per side), the goods
   economy's trade-route input (agent modes), the aggregate (`--agents off`) trade proxy in the
   contact ledger, specialization, intelligence and the M18 pandemic path; through the ledger's
   trade stock, the diplomatic second-order effects of trade dependence follow too. The route
   cache is invalidated when the set of closed pairs changes.
2. **The TRADE action** cannot choose a closed partner: its candidates are route partners, and
   without one it falls back to develop (`test_trade_action_cannot_choose_a_closed_partner`).
3. **Agent merchants** (hybrid, shadow, demographics-only): the border edges between the two
   polities leave the native merchant graph at the two agent-tick sites of `agent_bridge`
   (`_quarantine_route_graph`, after `_city_route_graph`). Native merchants already handle a
   vanished edge: a merchant in transit replans (`REPLANNED`) or unwinds its cargo to the origin
   (`RETURNED`); a reservation whose route vanished is cancelled. No Rust change.

### What stays open (intentional boundaries, recorded in every snapshot's `exempt`)

| Movement | Why |
| --- | --- |
| Public grain shipments and grain convoys (relief) | They build their own graph (`grain_reserves._route_graph` uses `_city_route_graph` only) and are not ledger contact: blocking them would be harm with no modelled benefit (open question Q-C3, decided exempt). |
| Armies | A quarantine does not halt campaigns; the soldiers channel stays at full pressure. |
| Hostages | Diplomatic custody (people channel), not restricted. |
| Migrants | Open under the default `--quarantine-channels trade`. Closed by the opt-in migration channel of slice C1b ([below](#migration-closure-c1b)); the snapshot's `exempt` then drops `migrants`. In hybrid worlds migrants carried most cross-polity arrivals in the audit's one pilot world. |
| Pilgrims | A very small channel; not restricted in C1. |
| Transit through a third polity | Only the closed pair's border edges are cut. A merchant can still reach the target through a third polity whose borders are open; the ledger records such a delivery as origin-to-destination contact. Counted in the receipt as `leaked_deliveries` (below). |

The law-code and lazaret technique bonus raises only the legacy multiplier; under the new modes
it has nothing to raise and is not applied (a deliberate disposition; a later slice may give it a
real meaning such as inspected passage).

## Costs

- **Enforcement:** `ENFORCEMENT_COST` = 2 treasury per closing polity per closed turn,
  accumulator category `keep`, charged at the decision. It is declared (border watch and
  administration), not calibrated, and it **replaces** the legacy flat charge. It is never a proxy
  for lost commerce. Labour costs (guards drawn from farm work) are slice C1.2.
- **Lost commerce emerges** from the closed routes: both sides lose the route income of each
  closed goods route (2 per side per turn) and whatever the goods economy, specialization and the
  TRADE action would have produced. The receipt states the forgone route income as the
  counterfactual route set minus the actual one, so an embargoed pair (no route to remove) is
  never attributed to the quarantine, and two polities closed against each other lose the pair
  once.
- **Food cost** emerges from lost cross-border goods imports (agent modes).

## The dated lag (no multiplier, so the timing is real)

Imports keep reading the contact ledger's decayed stock (`DECAY` 0.9 per turn for trade). A
closure stops **new** contacts only:

- **Aggregate** (`--agents off`): closure decided at T; the route proxy flow of T is missing from
  the ledger at the end of T; the first reduced import step is T+1
  (`test_aggregate_closure_at_t_stops_the_proxy_flow_of_t_and_lowers_contact_at_t1`).
- **Agent merchants:** deliveries made in the agent tick of T are read by the ledger at Phase 2
  of T+1, so the ledger misses them at the end of T+1 and the first reduced import step is T+2.
  Merchants that crossed before the closure may still deliver.
- Pre-closure stock then decays as `0.9^k` (still 59% after five turns), with no second cut
  (`test_a_closed_pairs_trade_stock_decays_without_a_second_cut`). The legacy multiplier cut
  70-90% at once. A real closure is therefore weaker and slower than the abstract cut; that is a
  result to report, not a defect. Any change of the import basis (for example to recent inflow)
  would be its own rules-versioned decision (open question Q-C1).

## Identity, receipts and persistence

**Closures.** `QuarantineClosure(id, civ, target, opened_turn, last_renewed_turn, cause,
channels=["trade"])`, one per (closing polity, target polity) pair. Ids come from
`next_closure_id` (starting at 1): stable, checkpointed and never reused. A lapse followed by a new
closure of the same pair gets a new id, also across a save
(`test_ids_are_stable_and_a_lapse_then_reclosure_gets_a_new_id_across_a_save`). Civ identity is
the index in `world.civilizations`.

**Receipt** (`QuarantineReceipt`, the turn named in `turn`, filled phase by phase):

| Field | Filled at | Meaning |
| --- | --- | --- |
| `decided` | Phase 1 | (civ, target) pairs closed (`closure`) or declared (`cost_only`) |
| `continued` | Phase 1 | polity pairs closed at the previous decision and again now, by either side |
| `opened`, `renewed`, `lapsed` | Phase 1 | closure ids |
| `enforcement` | Phase 1 | (civ, treasury paid) |
| `phase2_observed`, `routes_removed`, `forgone_income` | Phase 2 (`closure`) | the routes the closure removed from the authoritative route set and the route income both sides forwent |
| `merchant_edges_removed` | agent tick (`closure`) | directed merchant edges cut; None without an agent merchant graph (aggregate) |
| `closed_last_tick` | Phase 1 (`closure`) | polity pairs closed at the previous decision: closed during the agent tick whose deliveries this turn's Phase 2 reads |
| `leaked_deliveries`, `leaked_quantity` | Phase 2 (`closure`, agent modes) | merchant deliveries of the previous tick whose origin and destination polities form a `closed_last_tick` pair, a closure's last tick included: journeys that crossed before the closure, or went round through a third polity; None when no delivery record was read. Controllers are read at this reading, so an ownership change between the delivery and the reading can misattribute one |

Completed receipts fold into `totals` at the next decision. Merchant disruption counters
(replans, unwinds, stalled trips) stay where they already are, per tick and world-wide: the
bundle's `merchant_trip_stats` and, with `--transaction-receipts`, the `replanned`, `returned` and
`reservation_cancelled` rows. The closure receipt does not attribute them.

| Surface | Value |
| --- | --- |
| CLI | `--quarantine-mode {legacy,none,cost_only,closure}` (default unset = legacy); `--quarantine-channels {trade,trade,migration}` (C1b, default unset = trade) |
| World field | `EpidemicState.quarantine_rules: QuarantineRulesState \| None` (presence = a new mode) |
| Snapshot | `history[n].epidemics.quarantine_rules` (schema 1: mode, channels, exempt, closures, receipt, totals with the current receipt folded in); absent under the legacy rule |
| Analytics | `extract_epidemic_metrics(...)["by_seed"][i]["quarantine_rules"]` under a new mode (`turns_with_decision` and `closed_pair_turns` count declared quarantines under `cost_only`) |
| Batch manifest | `quarantine_mode` in `SIMULATION_ARG_KEYS`, omitted when unset |
| Forwarding | `expansion_features.expansion_arguments` (batch children, the gate runner `m53b_run_validation.py`) |
| Feature catalog | group "Public health": a top-level choice requiring the `epidemiology` setting (epidemiology with the contact ledger) or the value `legacy`; the Batch Lab surface reports the setting from the batch's own `contact_ledger` (config, else the server's) |
| Viewer | the Epidemics panel's "Quarantine rule" section (`viewer/src/lib/quarantineRules.ts`); Batch Lab and live setup offer the mode under "Public health" |

**Resume.** A world keeps its rules for its run:

- An exact checkpoint records an explicit mode in its run configuration; a different mode on
  resume is refused by the generic adoption. A checkpoint that never recorded one (a legacy run,
  or a run continued from a state file) is checked against the retained world state through
  `livelihoods_resume_conflicts` (`quarantine_resume_conflicts`): a different explicit mode,
  including a new mode on a legacy world, is refused.
- A JSON state file (`--resume state.json`, not exact) keeps its saved rules when the option is
  omitted, and `--no-epidemiology` or `--no-contact-ledger` on a world with saved rules is refused
  (the setters refuse, as the exact path's adoption does), instead of dropping the rules or
  leaving them dormant (`test_a_json_resume_cannot_switch_off_what_saved_rules_need`). A
  different explicit mode is refused once the world's epidemic model has ticked
  (`last_tick_turn >= 0`); a world whose epidemics never ran (a new or supplied world before its
  first turn) takes the requested mode. A legacy state file therefore continues the legacy rule,
  and `--quarantine-mode closure` on it is refused with a clear message
  (`test_legacy_json_resume_is_defined`).

## Evidence (2026-11-06, this branch, Linux container, Python 3.13.18)

Native extension used for every native step: the shared build, SHA-256
`101a4cd5b928b14f43539f925fa565036b94e38d91b9698071c80fa3656e0df3` (no Rust change in C1).

- **Feature-off identity** (`scripts/turn_speed_identity.py`, 9 cases, each side with its own
  source tree and extension copy), head source tree `3f6fa94d` (commit `f237adf9`) against
  `8abc1acb` (also the preceding integrated `main`): default (epidemics on) 9 cases, 399 files,
  0 differences; with `--no-epidemiology` on both sides 9 cases, 399 files, 0 differences.
  Rerun after the review fixes on source tree `dbe3e7a5` (commit `44706db9`): the same, both
  matrices 9 cases, 399 files, 0 differences; the chosen-point closure resume below, 12 points,
  PASS again.
- **Enabled exact resume** (`scripts/checkpoint_identity.py`, `--quarantine-mode closure`, every
  resume turn): `hybrid_s42` with `--transaction-receipts`, 59 resume points PASS; `off_s42`, 59
  PASS; `proc32_hybrid_s11` with `--transaction-receipts`, 39 PASS. A chosen-point run of
  `hybrid_s42` (resume points 13, 14, 15, 29, 30, 34, 35, 42, 47, 48, 51, 52, picked from the
  straight run's receipts) covers a resume right after two closures opened with 6 merchant edges
  cut and 2 voyages in transit, resumes across lapses and reclosures with new ids, and resumes
  across mass openings and lapses: 12 points, all PASS. The all-enabled compatible case (every
  catalog switch with retail in every region, plus `--transaction-receipts` and
  `--quarantine-mode=closure`, on `hybrid_s42`): 13 chosen resume points inside and across
  closures (openings with voyages in transit, lapses, reclosures), all PASS. Source and extension
  identities were recorded beside each run (`checkpoint_identity.py` records neither).
- **Natural closures on development worlds (development-only, not a screen).** 100 turns,
  `--quarantine-mode closure`, template worlds 1, 3, 7, 9, 11, 23, 42 and procedural worlds 7, 11,
  13, 17, 21, 31 (32 regions, 10 polities), aggregate and hybrid. Closures occurred in all 26 runs.

  | Worlds | Runs | Turns with a closure (range) | Closures opened | Closed pair-turns | Route-turns removed | Route income forgone | Merchant edges cut | Deliveries still crossing |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | template, aggregate | 7 | 18-62 | 101 | 484 | 342 | 1,348 | n/a | n/a |
  | template, hybrid | 7 | 2-84 | 234 | 826 | 402 | 1,376 | 1,314 | 21 |
  | procedural, aggregate | 6 | 28-89 | 1,126 | 3,493 | 1,632 | 5,196 | n/a | n/a |
  | procedural, hybrid | 6 | 45-88 | 1,351 | 4,760 | 2,569 | 8,528 | 10,172 | 454 |

  Most closures are short (opened and lapsed within a few turns as reports come and go). The
  hybrid leak count (deliveries made during any closed tick of a pair, its last included; counted
  after the review fix m2, which raised it from 16 and 338) is small against the edges cut but not
  zero, mostly in the larger procedural worlds where a third polity's open border offers a way
  round. Every other column is unchanged by that fix (a receipt-only correction).

**Held screen CW4 (2026-11-06).** The QL/Q0/QC/QR comparison of AUDIT-C section 7 test 7 ran
as the preregistered screen CW4 on fresh worlds (template 761-766, procedural 861-866, hybrid,
200 turns; 48 runs, 0 failed, 0.153 core-hours), declared in `scripts/connected_world_screens.py`
(`cw4_extract`, `cw4_activation`; `tests/test_cw4_screen.py`). Preregistration, results and
raw records: [connected-world-screens-cw4](../superpowers/progress/connected-world-screens-cw4.md).
Every arm activated on every world. Both primaries, closure minus cost_only over the whole
run, are nulls in both strata: cross-polity epidemic arrivals (template mean +0.8, procedural
+0.5) and world epidemic deaths per 1,000 person-turns (-0.21 and -1.46, with large per-world
differences of either sign). The harms are recorded: route income forgone (mean 519 template,
1,769 procedural, both sides), more merchant unwinds and replans (procedural 6 of 6 worlds),
deliveries still crossing closed pairs (8 and 60.5 per run), and more food shortfall after relief
(8 of 12 worlds) and more migration (10 of 12) under closure, as whole-trajectory associations.
A trade-only closure did not reduce cross-polity arrivals in these hybrid worlds, where the
legacy multiplier's world had fewer recorded arrivals than the closure's; with migrants open,
this is the evidence that motivates migration closure (C1b) before any further claim about
quarantine's effect. Under cost_only the enforcement is debited each turn but mostly displaces
finance's court spending rather than the reserve (traced on template 761 in the results page).

Tests: `tests/test_quarantine_rules.py` (offline, oracle chunk `connected-world-c`) and
`tests/test_quarantine_rules_native.py` (real extension), both on native shard 0. The legacy
quarantine tests in `tests/test_epidemiology.py` pass unchanged.

## Migration closure (C1b)

Slice C1b (branch `claude/cw-c1b-migration`, from `main` `8286804c`). CW4 found both primaries
null for a trade-only closure in hybrid worlds, where migrants carry most cross-polity contact
(the audit's pilot: 147 of 177 hybrid cross-polity arrivals by migrants). C1b closes the
migration channel for closed pairs, with its own costs. Code: `quarantine_rules.py`
(`install_migration_closure`, `take_migration_receipt`, the channel option and its resume
rules), the native module `chronicler-agents/src/migration_closure.rs`, one gate in `tick.rs`,
three FFI methods in `ffi/mod.rs`, two transient pool fields, and the two agent-tick sites of
`agent_bridge.py`. Design source: AUDIT-C section 6.2 and the lead's decision Q-C6 (a native
closure input, not an adjacency filter, which would also stop movement news crossing the border
and change the frontier logic). **Lead decision (review m3): refusal, not diversion.** AUDIT-C
6.2 listed the migration target loops (`behavior.rs`), household follow, relocation and the
migration drivers as check sites, so that a closed target would never be chosen. C1b departs
from that on purpose: the decision is left as it was made and only the closed crossing is
refused, so the mover stays home. Diversion would invent a destination choice the agent never
made. The cost is the larger harm of this design: an agent whose best target is closed does not
take an open second-best while the closure lasts. A diverting variant would be its own later
option.

**Option.** `--quarantine-channels trade|trade,migration`, default `trade` (the option omitted):
C1's closure byte for byte, so existing `closure` runs and the CW4 evidence are unchanged. An
explicit `trade` is the option omitted and needs nothing (it can be forwarded to any arm).
`trade,migration` requires `--quarantine-mode closure` and an agent mode in which the native pool
owns the population: `hybrid` or `demographics-only`. Both other modes are refused (lead decision,
review M1): with `--agents off` there are no native migrants, and in `--agents shadow` the
authoritative population is Python's, which still migrates across a closed pair through climate
overflow (`climate.process_migration`) and famine refugees (`ecology`, to foreign-held neighbours)
while only the native shadow pool would be closed (the review found 1 to 6 such transfers in 40
turns of shadow worlds 7, 11 and 13). In `demographics-only` and `hybrid` both Python paths are
no-ops and every other Python population change is an in-place growth or loss, never a move
between regions. Saved on the world as `QuarantineRulesState.migration` (omitted while false);
closures opened under it record `channels: ["trade", "migration"]`.

**What closes.** Before every agent tick of a run with the channel, Python installs natively
(`AgentSimulator.set_migration_closure(turn, region_civ, pairs)`) the controller index of every
region, read at the agent tick as the merchant-graph cut reads it, and the closed polity pairs
(each open closure (civ, target), unordered). A tick installs even when no closure is open, so
every tick leaves a receipt. After household consolidation and before the liquid-reserve and
fare gates, the native gate refuses every decided move whose origin and destination are ruled by
the two polities of a closed pair, **in both directions**. Moves inside a polity, to or from
uncontrolled land, and between open pairs are untouched. Movement news, adjacency and the
frontier logic are not touched (no adjacency filter).

| Policy | Decision |
| --- | --- |
| Refused, not diverted | The decision (target, utilities, the four Gumbel draws per agent) is the unconstrained one; only the application of a closed crossing is refused, and the mover stays where it is. The receipt is therefore exact for the tick: those moves were decided and would otherwise have been made. A refused agent decides afresh next tick (and is refused again while the closure lasts and the closed region stays its best target). |
| Households | A household moves as a unit: the spouse and dependants the consolidator linked share the lead's origin and destination and are refused with it; a follower whose own rebellion or occupation switch the consolidator replaced gets it back, as the other household gates do (a follower's own earlier choice to migrate elsewhere, replaced by the lead's move, is not restored: it stays home, as under the liquid-reserve gate). Refused moves are never priced by relocation fares or counted by the liquid-reserve gate (tested at tick level). The opt-in decision-delivery move observer is not told of refusals: refused proposals are simply absent from its applied moves, as for the liquid-reserve gate. |
| Already moving | No migrant is in flight: a native migration is decided and applied in the same tick. A move applied before the closure's first tick is complete and is never reversed; every new move during the closure is refused. Merchants on a trip are not migrants (their border edges leave the merchant graph, C1). |
| Refugees | Not exempt: a move driven by famine, battle, conquest or persecution memories, live persecution or the safety need is refused like any other. The receipt keeps each refused move's driver (the dominant term; a follower takes its lead's); refusals of those six drivers (`FLIGHT_DRIVERS`) are reported apart as flight, a harm, and hunger-driven moves (food opportunity, material need: `HUNGER_DRIVERS`) as a second harm line; flight excludes them. Python's aggregate famine and overflow refugee routing is dormant in the two accepted modes. |
| Transit | The closure is between two polities, not on the person: a migrant may still reach a closed polity through a third polity over several turns (each leg crosses an open pair; a migrant is displaced for 5 turns after each move), the way round that merchants also find. Such journeys are not counted. |

No new random draws, no new mortality authority: refused people stay where they are, and the
labour and food consequences emerge (they keep working and eating at home). The closure and its
receipt are transient pool fields (the `transient` persistence clause): absent from the native
checkpoint payload and schema, recomputed from Python state each tick, so checkpoints keep their
layout. The FFI refuses a tick while a closure for another turn is pending; Python drops any
stale closure before each install and releases the install after the tick whatever happens
(`migration_closure_tick`: a tick that raises leaves no closure or receipt pending).

**Units.** A receipt counts the persons refused that tick (each at most once per tick). A refused
agent decides afresh the next tick and may be refused again, so the totals sum **refusals**
(person-ticks); the distinct persons refused are counted by stable agent id
(`QuarantineRulesState.refused_ids`, persisted while the channel is on). A rebuilt native pool
(a JSON resume) starts a new id space, so after one the distinct count is a lower bound.

**Older checkpoints.** Every C1b field is read with `getattr` defaults: a checkpoint pickled by
`main` (any rules mode) lacks them and resumes unchanged on this branch, including through
`--resume-allow-mismatch` (fixture `tests/fixtures/quarantine_rules_c1_pickles.json`, states
pickled with `8286804c`'s classes).

**Receipts.** Taken once right after the tick (`take_migration_closure_receipt`): refused
persons by (origin, destination, driver) and the refused agents' stable ids. Each row is
attributed to the closure of the polity whose border the mover would have entered (its closure
against the origin polity), else the origin polity's closure against the destination polity.

| Field | Where | Meaning |
| --- | --- | --- |
| `migrants_blocked` | receipt (state) | rows (closure id, origin region, destination region, driver, persons); None while no native receipt was read this turn |
| `migrants_refused_first` | receipt (state) | agents refused this tick for the first time in the run |
| `receipt.migrants_blocked`, `_flight`, `_hunger`, `receipt.migrants_refused_first` | snapshot | persons refused this tick, of them fleeing war, famine or persecution, of them hunger-driven, and of them refused for the first time; null: not observed |
| `receipt.migration_refusals` | snapshot | the rows with region names: `{closure, from, to, driver, persons}`; null: not observed, `[]`: a recorded zero |
| `totals.migrants_blocked`, `_flight`, `_hunger` | snapshot, state, analytics | refusals (person-ticks) folded per receipt; absent without the channel |
| `totals.migrants_refused_persons` | snapshot, state, analytics | distinct persons refused (stable ids) |

The event text names the channel: "X closes its borders to trade and migration with Y against
...". Viewer: the Epidemics panel's quarantine section shows a "Migrants refused" tile (not
restricted without the channel; "not observed" for a null receipt; a recorded zero; otherwise
the persons refused this tick with the flight, hunger and first-time shares), a table of refusals
by closure and the totals (refusals as person-ticks, and distinct persons). Feature catalog:
`quarantine_channels`, a second top-level choice of the Public health group (requires
`--quarantine-channels trade`, or `--quarantine-mode closure` and `--agents hybrid` or
`demographics-only`). Batch
manifest: `quarantine_channels` in `SIMULATION_ARG_KEYS`, omitted when unset; forwarded by
`expansion_arguments`.

**Resume.** As for the mode: an exact checkpoint records an explicit value; one that never
recorded it is checked against the retained world (`quarantine_resume_conflicts`), so
`trade,migration` on a trade-only checkpoint, or `trade` on a migration checkpoint, is refused.
A JSON resume keeps the saved channels when the option is omitted, refuses a different value once
the epidemic model has ticked, and refuses `--agents off` or `shadow` on a world whose saved
rules close migration.

**Pinned files.** `lib.rs`, `pool.rs`, `tick.rs`, `ffi/mod.rs`, `agent_bridge.py`,
`batch_manifest.py` and `tests/test_batch_manifest.py` carry the reviewed exact-inverse layer
`cwc1b` (`tests/fixtures/livelihoods_cwc1b_source_inverse.json`, parent `8286804c`), appended
after `cwc1`.

Tests: `tests/test_quarantine_migration.py` (offline, oracle chunk `connected-world-c`) and
`tests/test_quarantine_migration_native.py` (real extension), both on native shard 0; Rust unit
tests in `migration_closure.rs` and `tick.rs` (a closed pair blocks both directions while the
open pair's moves are exactly the unclosed run's; completed moves stay; a closure for another
turn is not applied; the household is refused as a unit with its follower's action restored).

### Evidence (2026-11-06, this branch, Linux container, Python 3.13.18)

Source commit `a212ba1f`; native extension built from it into the lane's own venv, SHA-256
`6c461a0bb5879d1e8f591890e6eb30295b8bf877ff8debb4354c117dfee28103` (the comparison side of
`main` used the shared build `101a4cd5...`, equal to `main`'s Rust).

- **Feature-off identity** (`scripts/turn_speed_identity.py`, 9 cases, each side with its own
  source tree and extension): head against `8abc1acb` 9 cases, 399 files, 0 differences; against
  the preceding `main` `8286804c` 9 cases, 399 files, 0 differences; with `--no-epidemiology` on
  both sides against `8abc1acb` 9 cases, 399 files, 0 differences.
- **C1 unchanged** (`--quarantine-mode closure`, default channels, every case): head against
  `main` `8286804c` 9 cases, 399 files, 0 differences. The development table's trade-only rows
  below also equal C1's table above.
- **Enabled exact resume** (`scripts/checkpoint_identity.py`, `--quarantine-mode closure
  --quarantine-channels trade,migration`, every resume turn): `hybrid_s42` with
  `--transaction-receipts` 59 points PASS (migrants refused on 22 of its 60 turns);
  `proc32_hybrid_s11` with `--transaction-receipts` 39 PASS (12 turns with refusals);
  `shadow_s42` 39 PASS; `demographics_s42` 39 PASS; the all-enabled compatible case (every
  catalog switch with retail in every region, relocation fares included, plus
  `--transaction-receipts`) on `hybrid_s42` 59 PASS (refusals on 35 turns).
- **Natural activation on development worlds (development-only, not a screen).** 100 turns,
  hybrid, template worlds 1, 3, 7, 9, 11, 23, 42 and procedural worlds 7, 11, 13, 17, 21, 31 (32
  regions, 10 polities), `closure` with trade only (QR) and with `trade,migration` (QM); one run
  per world and arm, so no inference. Migrants were refused in all 13 QM runs (3 to 2,775 per
  run), every QM receipt was observed (0 null), no extractor problem.

  | Worlds | Arm | Turns with a closure (range) | Closures opened | Closed pair-turns | Migrants refused | of whom flight | Turns with refusals | Cross-polity arrivals | Epidemic deaths |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | template | QR | 2-84 | 234 | 826 | n/a | n/a | n/a | 145 | 592 |
  | template | QM | 2-96 | 195 | 756 | 3,027 | 2,302 | 249 | 89 | 395 |
  | procedural | QR | 45-88 | 1,351 | 4,760 | n/a | n/a | n/a | 733 | 2,670 |
  | procedural | QM | 47-93 | 1,559 | 6,663 | 9,877 | 6,789 | 456 | 512 | 2,049 |

  Cross-polity epidemic arrivals (CW4's world count) were lower under QM in 10 of 13 worlds
  (equal in 1) and epidemic deaths lower in 10 of 13 (equal in 1). Most refusals are flight
  (of 12,904 refused persons, famine memory 58%, persecution memory 7%, persecution 4%; food
  opportunity 14%): the harm the channel imposes. These are development worlds and single
  trajectories; the effect is for a preregistered held screen to measure, with migration, hunger
  and food harms alongside.

Evidence and runners: `/home/user/evidence/c1b/` (outside the repository).

## Not done here (by name)

- C1.2 border guards (labour cost through the farm-labour seam), pilgrim restriction, convoy
  closure: out of C1 by decision. The migration channel is C1b ([above](#migration-closure-c1b));
  it has not been screened on held worlds.
- A promotion decision, and the C2-C4 slices (care, dated outbreak reports).
- No dated outbreak reports (C4): a polity still learns of a foreign outbreak the tick it is
  reported, as under the legacy rule.
