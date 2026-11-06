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
this page applies. Experimental and opt-in; not promoted, not screened on held worlds.

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
| Migrants | Rust picks migration targets from adjacency; a migration closure needs a native input (slice C1b). In hybrid worlds migrants carried most cross-polity arrivals in the audit's one pilot world. |
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
| CLI | `--quarantine-mode {legacy,none,cost_only,closure}` (default unset = legacy) |
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

## Not done here (by name)

- C1.2 border guards (labour cost through the farm-labour seam), C1b migration closure (native),
  pilgrim restriction, convoy closure: out of C1 by decision.
- A promotion decision, and the C2-C4 slices (care, dated outbreak reports).
- No dated outbreak reports (C4): a polity still learns of a foreign outbreak the tick it is
  reported, as under the legacy rule.
