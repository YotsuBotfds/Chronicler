# Infrastructure condition and repair (B3, `--infrastructure-condition`)

Status, 2026-11-07 (revised after the independent review the same day): connected-world program,
lane B3 (Program B item 3). Experimental and **off by
default**; nothing here is calibrated or scientifically qualified. Design source: the program-B
contract audit (`docs/superpowers/audits/connected-world/audit-b-watershed-infrastructure.md`,
sections 3 and 7.3, its **sibling-record** alternative) and the lead's decisions
(`docs/superpowers/roadmaps/connected-world-program.md`, 5.2): irrigation and road condition live
in their own record keyed by a stable infrastructure id, so RS2's schema, record and viewer stay
unchanged; works are repaired with the same labour channel and timber as RS2's projects and,
under L9, through **their own** proposal and envelope from the same budget (lead decision after the
review: never pooled with RS2's proposal), so no coin is promised twice; ports are deferred; roads
gain service-gated range only (no transport discount).

Code: `src/chronicler/infrastructure_condition.py`, `src/chronicler/infrastructure_condition_state.py`;
guarded seams in `repair_projects.py`, `local_budgets.py` (the provider registration), `money.py`,
`wealth_accounting_state.py`, `techniques.py`, `resources.py`, `watershed.py` and the pinned
`economy.py`, `agent_bridge.py` and `ecology.py` (witness layer `cwb3`); viewer `viewer/src/lib/infrastructureCondition.ts`,
`viewer/src/infrastructureConditionTypes.ts`, `viewer/src/components/systems/InfrastructureCondition.tsx`
(Livelihoods tab); tests `tests/test_infrastructure_condition.py` (offline, chunk
`connected-world-b`), `tests/test_infrastructure_condition_native.py` (real extension),
`viewer/src/lib/__tests__/infrastructureCondition.test.ts`,
`viewer/src/components/systems/__tests__/InfrastructureCondition.test.tsx`.

## 1. Switch and modes

```sh
chronicler --agents hybrid --grain-reserves --grain-storage --repair-projects --infrastructure-condition
chronicler --agents hybrid --infrastructure-condition --infrastructure-condition-mode record_only
```

| Mode | Needs | Condition | Service reaches consumers | Works |
| --- | --- | --- | --- | --- |
| `repair` (default) | `--repair-projects` | wear, damage, repair | yes | plan, pay, credit |
| `cost_only` | `--repair-projects` | wear, damage | yes | plan, hold timber, use labour and pay identically; credit nothing (RS2's cost control) |
| `wear_only` | hybrid only | wear, damage | yes | none (the no-repair control against the same wear) |
| `record_only` | hybrid only | wear, damage (recorded) | **no** (service is forced to 1.0) | none: every output except the record equals the switch off |

- Every mode requires `--agents hybrid` (the consumers' native flag and the works' labour column are
  native). A livelihoods-registry package: `LIVELIHOODS_SWITCHES` entry `infrastructure_condition`,
  after `workshop_economics` and before `attribution_records` (D2 observes after every acting package)
  and `wealth_accounting` (the ledger still runs last); state
  `WorldState.livelihoods.infrastructure_condition`; `batch_manifest.SIMULATION_ARG_KEYS` lists
  `infrastructure_condition` and `infrastructure_condition_mode`, both omitted from the recorded
  configuration when unset, so feature-off manifests keep their bytes.
- Feature catalog: `REQUIREMENTS["infrastructure_condition"] = (hybrid, any(mode in {record_only,
  wear_only}, --repair-projects))`; the catalog test checks it against the run's own refusals. A
  mode given without the switch (`--infrastructure-condition-mode` alone, or with
  `--no-infrastructure-condition`) is refused.
- **Resume.** The mode is chosen when the record opens; a different `--infrastructure-condition-mode`
  on resume is refused (`check_request`; the exact-resume path reports it through
  `livelihoods_resume_conflicts`). A saved record resumed outside hybrid, or a saved work mode
  resumed with `--no-repair-projects`, is refused with "pass `--no-infrastructure-condition` to end
  it". `--no-infrastructure-condition` ends the switch: open works are abandoned (`switched_off`),
  prepaid remainders are written off (counted), the record is kept, and service returns to 1.0.

## 2. Assets and identity

- An asset is created when an **active** irrigation or road record is first seen (Phase 10
  reconciliation, or a mid-turn damage hook), at condition 1.0, with a persisted, never-reused
  `aid`. It is matched each turn by `(region index, record index, type, built_turn,
  builder_civ)`: `Region.infrastructure` is append-only, and nothing reactivates a record.
- Statuses: `serving` (record active, condition > 0), `failed` (record active, condition 0),
  `inactive` (the record was deactivated) and `destroyed` (the record list was removed, the
  supervolcano). Ends are decided in Phase 10, when the turn's events are in the timeline, with
  the cause read from dated state: `depopulation` (`region.depopulated_since == turn`),
  `earthquake` (an `earthquake` event of the region this turn), `scorch` (this turn's
  `scorched_earth` event whose text is `scorched <region> during retreat`), else `unknown`; a
  removed list ends `record_removed`. A
  mid-turn hook never damages an asset whose record is no longer active.
- A rebuild is a new record and a new asset (BUILD only rebuilds when no active record of the type
  exists). A **failed** asset keeps its active record, so BUILD never replaces it: it must be
  repaired.
- **Conquest** keeps the asset (the record and its `builder_civ` are untouched). Responsibility (the
  region's controller, `responsible`) moves to the new controller with a dated
  `responsibility` entry, and an open work is inherited with a dated `controller` note (RS2's rule).

## 3. Wear, damage and service (declared, uncalibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `WEAR` | irrigation 0.01, roads 0.005 per turn | condition lost by a serving asset each Phase 10 (irrigation: the grain-storage rate) |
| `SERVICE_FULL` | 0.5 | `service = min(1, condition / 0.5)` |
| `SERVICE_GATE` | 0.5 | least service at which irrigation sets `has_irrigation` and a road extends range |
| `WAR_DAMAGE` | 0.25 x `repair_projects.war_damage` | per real conquest or sack (RS2's hooks), at most one damage per asset and turn (a second event the same turn, e.g. a flood onset after a conquest, is skipped, counted in `damages_skipped_same_turn` and `damages_skipped_<event>` and recorded in `skipped_damages` with its ref) |
| `FLOOD_DAMAGE_PER_EXCESS`, `FLOOD_DAMAGE_CAP` | 0.5, 0.5 | condition a watershed `flow` flood takes at its onset per unit of its excess (water units above the channel), capped |
| `OPEN_BELOW` | 0.75 | a wear work opens below this (RS2's threshold) |
| `WORK_PER_CONDITION` | 20 (both kinds) | work units restoring a whole unit of condition |
| `WORK_PER_TURN` | 4 | most work one asset's work asks per turn (the storage batch) |
| `TIMBER_PER_WORK` | irrigation 0.25, roads 0.5 | lead decision |
| `COIN_MILLI_PER_WORK` | irrigation 600, roads 500 milli-units | a whole repair from condition 0 costs exactly the undiscounted BUILD cost of a new record (irrigation 12, roads 10, `infrastructure.BUILD_SPECS`): repair is never dearer in coins than a rebuild; its labour and timber are additional real inputs a BUILD does not have |

- **War damage** is recorded only at RS2's two existing real events: region conquest
  (`repair_projects.region_conquered`, called from `action_engine.apply_region_conquest`) and a city
  sack (`repair_projects.city_sacked`), each before RS2's own active check, so B3 damage applies in
  every B3 mode even without RS2. Granary seizure is granary-only. The cause is the war's
  `(war_key, war_start_turn)` when found (RS2's `_war_identity`).
- **Flood damage** (`infrastructure_condition.flood_damage(world, region, excess, ref=...)`) is
  called by the watershed's `flow` mode only (`watershed._apply_flow`; a test fails on any other
  caller), **once, at a flood event's onset**, as the same act as the flood's other consequences
  (capacity modifier, cooldown, silt): every serving asset of the region takes
  `min(FLOOD_DAMAGE_CAP, FLOOD_DAMAGE_PER_EXCESS x excess)`, recorded with the flood event's
  identity `flood:<region>:<start turn>` as its `ref`. Never on a turn of an ongoing flood (no
  onset), never twice on resume (the onset is read from the saved frame, and one damage per asset
  per turn). An onset withheld because the region holds a disaster cooldown does nothing, as B2
  withholds every other effect of that flood. A damaged asset's work opens with cause `flood`.
  Floods are rare and small in `flow` (B2's channel passes all but anomalous arrivals): procedural
  13 has one onset in 200 turns, excess 0.018, damage 0.009; procedural 11 none.

## 4. Consumers

One helper, `infrastructure_condition.service(world, region, kind)`, returns **exactly 1.0** while
the switch is off, in `record_only`, outside hybrid, or for a record not yet registered:

| Consumer | Edit | Off |
| --- | --- | --- |
| `ecology._tick_water` (pinned; the Python fallback without a native ecology) | `has_irrigation = active and serves(...)` | identical |
| `watershed` account in `record_only` (B1): irrigation withdrawal | an active work that serves | identical |
| `economy.arable_capacity` (pinned) | `mult += FARM_CEILING_IRRIGATION * service(...)` | `0.10 x 1.0 == 0.10`: bit-identical |
| `agent_bridge.build_region_batch` `has_irrigation` (pinned) | `active and serves(...)` (service >= 0.5) | `True and True`: identical |
| `techniques.extend_trade_routes` (road practice) | the intermediate road must serve | identical |
| `resources._compute_active_trade_routes` (railways focus) | the intermediate road must serve | identical |

`service` **fails closed**: a region that is not in `world.regions` (by identity, or by its unique
name for a copy) raises instead of reading 1.0. The irrigation **technique** (+5% grain, +10%
ceiling) is a separate practice and unchanged. No road transport discount is added
(`INFRASTRUCTURE_DISCOUNT` stays the placeholder 1.0).

**Watershed `flow` x condition** (both switches opt-in; only the combined mode changes). In
`--watershed-mode flow` with `--infrastructure-condition` (repair, cost_only or wear_only), an
irrigation work's withdrawal capacity scales with its service:
`W = min(available, IRRIGATION_DEMAND x service)` (and the same demand in the flood-ending normal
arrivals), a declared term of the account, which still closes every turn. **Continuous, not the
0.5 gate**, because the gate exists only for consumers that read a yes/no flag (the native
`has_irrigation`, a road's range); withdrawal is a quantity, as the arable ceiling is (`0.10 x s`),
and `flow` already replaces the native irrigation water bonus and drought multiplier that the flag
drives, so the account's withdrawal is the only water effect of irrigation there; a partly silted
canal delivering proportionally less water is the plain reading of "service". A failed work
withdraws nothing. `flow` without the condition switch (or with it in `record_only`) reads every
active work at service 1.0, exactly as on main (`demand x 1.0 == demand`); the condition switch
without `flow` is unchanged (the `record_only` watershed account keeps the >= 0.5 gate).

## 5. Works (`repair`, `cost_only`)

**Opening (Phase 10, before the L9 decision).** A work opens for an asset below `OPEN_BELOW`
(cause `wear`) or carrying a damage record not yet taken by a work (`war`, `flood`), when the
region has a controller with regions (else an unmet need, `no_controller`). Scope `(1 - condition)
x WORK_PER_CONDITION`; damage to an asset with an open work extends its scope. A work completes
when its scope is delivered (within `1e-6`), and is abandoned when its asset ends (`asset_lost`),
its region loses its controller (`no_controller`) or the switch ends (`switched_off`).

**Phase 2, inside RS2's turn.** RS2's `prepare_phase2` calls `plan_phase2` after RS2 planned its
own projects and before RS2 applies the turn's timber holds; RS2's `finish_phase2` calls
`settle_phase2` after RS2 charged. Works are planned in the fixed order irrigation, then roads,
by region and `aid`.

- **Labour through the native `granary_work_requested` column.** With PL3, eligible named adult
  farmers are reserved once and paid through `infrastructure_wage`; the unpaid control keeps the
  same reservation. Actual work replaces farming. With PL3 off, the earlier anonymous unpaid
  path remains (see the named-crew contract below). The column is shared in a fixed order,
  **granary -> irrigation -> roads**, decided by storage's **actual** request this turn and
  recorded on each receipt (`granary_request`, `shared`) and in the frame (`shared` regions):
  - grain storage off: B3 appends the column;
  - a region where storage asks for work this turn (its computed request is above 0) belongs to the
    granary: the works stall `granary_first`;
  - a region where storage asked for nothing this turn (neglect, maintain at 1.0, or no budget,
    timber or work budget for it) is **claimed** after storage planned: B3 adds it to the storage
    plan's suspended regions, so storage's settlement, whose request there is 0, ignores the works'
    delivered work. Nothing storage planned, held or would charge changes; RS2's suspension seam,
    RS2's record and L9's granary skip are untouched;
  - a region under an RS2 granary project: the works add to RS2's request; RS2 takes
    `min(delivered, its request)` first, the works the rest.
  - A region with no farmer in the Phase 2 rows: the works stall `no_labor`.
- **Timber:** `TIMBER_PER_WORK` per unit from RS2's free timber after RS2's holds (stockpile minus
  merchant commitments, plus the PL1 store), added to RS2's per-region holds (so the store is taken
  first and a failed tick returns everything with RS2's holds); the unused part is returned after
  the tick (store part through PL1's `return_store`).
- **Timber supply (PL1, `--timber-supply`):** the works' outstanding timber need enters PL1's
  planner, the existing authority, **after every RS2 need row of the turn** (lead decision,
  2026-11-07; `timber_wants` here, `timber_supply._plan_works` there). Per region, ascending: the
  timber the open works could use in one turn at their per-turn cap,
  `min(WORK_PER_TURN, remaining) x TIMBER_PER_WORK` (PL1's horizon for RS2's projects), set against
  what the free timber and the cargo on the way leave after RS2's want in the region:
  `gap = max(0, want - max(0, free + in_transit - rs2_want))`. A region with a live expedition
  gets no second one; a gap of at least PL1's `MIN_GAP` launches one under PL1's checks (forest
  within `MAX_HOPS`, the `GUARD_SHARE` ecological guard, one expedition per forest, at most
  `CREW_CAP` eligible residents, the whole expedition's wages affordable), PL1's crew rule, its
  wages from the controller's treasury and the one work reservation: no other labour authority, no
  free timber. The cargo is cut through the forest's L3 account and delivered to the home region's
  store, which RS2's holds (the works' included) take first, exactly once; PL1 keeps the store
  where a work asks for timber (the same screen as the need rows) instead of releasing it, and
  releases it once none asks, so a work that asks nothing (a region without a farmer, or a predicted granary-first region)
  never holds RS2's leftover out of the stockpile (review of `0187bfb5`). **Boundary:** only
  works already opened by the lifecycle ask, never an asset that has not opened one; a work asks
  nothing when its record is not in service, its region has no controller or had no farmer after
  the turn's agent tick (RS2's observed count, as PL1 skips RS2 granaries without farm labour);
  under L9 a work is funded only through the works' own proposal, so either repair kind that
  proposal could name asks (a region whose storage is set to ask for work is screened
  `granary_first` by the same prediction; the proposal's `no_timber` screen is what supply relieves). Without L9 storage's actual request decides `granary_first` at Phase
  2 (it depends on storage's own inputs, so no prediction screens the need); a work stalled there
  keeps its delivered timber in the store. Works opened in this Phase 10 ask from the next (B3's
  Phase 10 hook runs after PL1's). The rows are recorded here (`timber_needs`); PL1's own need rows
  and their counters stay RS2's, PL1's `launched` counts RS2's launches and `launched_works` the
  works' (absent until the works launch one; the veteran and per-expedition counters count every
  expedition). Off, and in `record_only`/`wear_only`, nothing changes.
- **Coins:** `COIN_MILLI_PER_WORK` per delivered unit, rounded up to the milli-unit; one whole-unit
  charge per civ and turn, the sub-unit remainder prepaid toward the civ's next works (RS2's rule).
  The works plan **after** every Phase 2 bill RS2 plans around and after RS2's own planned charge,
  whose rounding is reserved whole (RS2 never charges above `ceil(planned / 1000)`). Later Phase 2
  planners (PL1's expedition wages) see both charges **rounded separately**:
  `repair_projects.pending_bills` adds `ceil(RS2 milli / 1000) + ceil(works milli / 1000)`, the
  most the two separate charges can take (review M1: one rounding could leave a unit that a later
  planner spent and the settlement then lacked). Settlement validates every civ's charge with the
  payment seam's quote before anything is credited or moved.
- **Payment, and where the coins go:** the charge is paid **through the payment seam**
  (`money.pay`): treasury -> the declared sink `public_works` (appended to `money.SINKS`), purpose
  `infrastructure_repair` (appended to `PYTHON_PURPOSES`), batch = civ index, so each (turn,
  purpose, batch) settles exactly once (persisted keys); the bill is registered in
  `wealth_accounting_state.MONEY_BILLS` (`("infrastructure_condition", "_bill")`) and the package's
  book in `money.MONEY_BOOKS`. **The sink has no payee: these coins are destroyed** (they leave
  the economy, as the storage channel's and RS2's granary coins do, which are not declared at all).
  Nobody receives them, the labour is unpaid farm time and the timber comes from the commons
  stockpile or the PL1 store; for A1/A2 calibration this is a deflationary leak (`sink_milli`
  counts it). No agent wealth moves (no ledger channel is needed).
- **Stalls** (a turn without delivered work, per reason): `no_timber`, `no_coins`, `no_labor`,
  `no_envelope`, `granary_first`. A reason that only limited the work is counted as `limited_*`.

**L9 (`--local-budgets`): the works' own proposal** (lead decision after review M2). The works
are a proposal provider of their own (`infrastructure_condition.BUDGET_PROVIDER`, appended to
`local_budgets.PROVIDERS`; service `infrastructure_works`, group `repairs` shared with RS2 for the
`fixed_shares` control, claim `infrastructure:<civ>`), **never pooled with RS2's divisible
proposal**:

- one divisible proposal per ruler covers feasible open **irrigation and road** works. Both kinds
  share one finite whole-coin envelope and one payer ledger; named paid crews reserve one extra
  whole coin for the independently rounded wage/material bills;
- dated screens exclude no farmer (`no_labor`), predicted storage work (`granary_first`) and no
  free timber after RS2's needs (`no_timber`). PL1 can procure timber for either kind before an
  award exists; timber still must arrive before a feasible proposal can be made;
- commons relief remains the declared irrigation **food at risk relieved**: arable ceiling kept
  over L9's horizon under declared wear, times observed food production / arable capacity. This
  assumes food output scales with land capacity and overstates relief where labour limits output;
- patrician relief is feasible **road repair worker-turns**, bounded by measured remaining road
  repair work. The same outstanding worker-turns enter patrician burden while B3 repair or
  `cost_only` is active, alongside L9's existing idle workshop work. This is a declared maintenance
  stake, not nutrition, measured trade revenue or a second labour authority;
- claims record each stable `infrastructure_work:<wid>` as well as the civ's service claim. A
  same-region work that was screened out or opened later cannot spend the award. Historical
  checkpoints with the earlier recipient-only claims retain their irrigation-only authority;
- proposal details preserve each kind's expected work, relief, screens and the rounding reserve
  in the commitment. Partial grants scale the expected bundle proportionally, an approximation:
  Phase 2 retains fixed irrigation-first execution and may deliver an uneven bundle;
- settlement reports actual delivered and credited work **by kind**, and checks the one civ charge
  against the envelope. A new promise is kept only if **each promised kind** reaches L9's kept
  threshold. Spending the full grant on irrigation cannot satisfy its road promise. `cost_only`
  may keep a work-delivery promise but explicitly records zero credited work/service restoration.
  RS2's separate envelope and maintenance reservation remain separate authorities.

Each irrigation asset also records `food_at_risk`: the food its region would lose over the horizon
without repair (observed each Phase 10 with an economy tick; null otherwise).

## 6. Accounting and closure

Per civ and turn (`WorksLedger`, `check_ledger` when written; the viewer re-checks):

    charged x 1000 + prepaid_before == coin_cost + prepaid_after     (prepaid in [0, 1000))
    charged <= envelope                                              (with L9: the works' own envelope)

Per receipt: `delivered <= requested`; `timber_held == timber_used + timber_returned`;
`timber_used == delivered x rate`. The sink's lifetime total equals the sum of charges (`sink_milli`).
Condition is an index with declared wear and credited repair; credit beyond 1.0 is counted
(`cap_waste`). Nothing creates labour, timber or coins.

Guards against applying anything twice: a turn settles once (`last_settled_turn`, `_begin`); the
payment key `(turn, infrastructure_repair, civ)` settles once; a failed native tick drops the turn's
plan and RS2 returns every hold; the turn in flight is never pickled.

## 7. Record (`livelihoods.infrastructure_condition`, schema 1, stage `B3`)

Completed-turn observations dated by `source_turn`: `assets` (serving and failed, each with
`condition`, the applied `service` and `condition_service = min(1, condition / 0.5)`, status,
responsible civ, lifetime wear, damage and credit, `failed_turn`, `food_at_risk` and a bounded
dated history), `terminal` (the last 32 ended assets), `works` (open), `closed` (last 16),
`damages` (last 32, a declared bound: drops are counted in `damages_dropped` and, for a record no
work had taken, `damages_dropped_unattached`), `skipped_damages` (only once a damage was skipped),
`timber_needs` and `timber_needs_dropped` (only for a turn PL1 planned the works' timber need: per
region the works, want, RS2's want, free timber, cargo on the way, gap, and what PL1 did: `supplied`,
`expedition`, `launched` or `refused` with PL1's reason and the expedition id), `receipts`/`ledger`/`unmet`/`shared` (all null when the turn had no settled
Phase 2 in a work mode: unknown, not zero; receipts and ledger are always null in
`record_only`/`wear_only`, which have no works), `prepaid`, `sink_milli`, `counters` (declared set)
and `parameters`. The strict viewer reader keeps disabled, absent, malformed, unsettled, no-works and
recorded-zero states distinct; the panel shows the asset table (condition, applied service,
status, food at risk, a condition trace across the run's snapshots), the works (progress, this
turn, stall turns by cause, funding), the charges against the one repairs limit, and the run's most
stalled work as the directly recorded "underfunded public works" story.

## 8. Evidence

### Tests

- `tests/test_infrastructure_condition.py` (offline, 69 tests): identity matching and lifecycle
  (every end cause, removal, rebuild, mid-turn damage skipping an ended record), wear, service and
  failure (failed is not rebuilt), service failing closed for an unknown region, consumers
  bit-identical when off and in `record_only` (arable capacity, `has_irrigation`, the road range
  gates, the watershed record and the Python ecology), works moving real labour, timber and coins
  once, a whole repair costing no more coins than a rebuild, a refused charge raising before
  anything is credited, a failed tick returning every hold, the granary-first split in a shared
  column and storage's actual request deciding a region, every stall cause, the works spending only
  their own envelope (roads none) beside RS2's, `pending_bills` adding the two separate roundings
  (the reviewer's 500 + 500 milli probe and the tight-treasury PL1 budget), the works' own screened
  L9 proposal with its audited detail (RS2's proposal never carries them), the works' envelope
  settling from their own ledger, the food-at-risk rule, cost-only, completion of a failed asset,
  the wear-only control, `record_only` equal to off except the record over four turns, an exact
  pickle resume at an open work, switching off, invalid combinations (including a mode without the
  switch), the payment registration, and watershed `flow` x condition: withdrawal scaling with
  service and account closure (flow alone and condition `record_only` at service 1.0, the
  `record_only` account's gate), a failed work withdrawing nothing, flood damage once at the onset
  with the event as cause and never on the ongoing flood, a withheld onset damaging nothing, a
  pickle resume inside an open flood with damaged works, and the PL1 timber link on PL1's
  constructed line (one forest between two regions): the works get woodcutters only after RS2 (an
  RS2 need in a higher-indexed region takes the one forest, the works' row is refused
  `forest_busy`; alone the works' need launches PL1's crew and counts in `launched_works`; in RS2's
  own region one expedition serves both, RS2's want counted first), the works ask, and keep a store,
  only for open works that can use timber
  (no farmer, L9 roads and L9's predicted `granary_first` ask nothing; `record_only`/`wear_only`
  never ask), RS2 and PL1 byte-identical over eight turns when the works ask for nothing (no
  work, a work its own stockpile covers, `record_only`, `wear_only`) and over sixteen turns with an
  L9 road work in RS2's own region (RS2's leftover store released as with the switch off; this
  case failed before the fix), every load the works use cut
  by PL1's crew and passed through the store exactly once (delivered = used + released, held -
  returned = used, the store kept until the work completed), and an exact pickle resume with a
  works' expedition outstanding.
- `tests/test_infrastructure_condition_native.py` (real extension, about 17 s): procedural seed 31
  60 turns with `CHRONICLER_CHECK_RESOURCES=1` (every receipt and ledger closes; the sink equals the
  charges; conquest damage and scorched records occur); an exact checkpoint resume at turn 37
  inside open works (history, world state and `state.json` byte-identical); template seed 11 40
  turns `record_only` equal to the switch off except the record; procedural seed 13 with flow, an
  exact resume inside an open flood with damaged works; template seed 11 with PL1, an exact
  checkpoint resume at turn 45 while the expedition the works' need launched at turn 43 is cutting
  (it delivers after the resume).

### Development activation (development worlds only; not a screen, no held seed)

Source `32d27330` (the review revision; `src` unchanged at the branch head), extension
`20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca` (main's Rust). Template seeds 1,
3, 7, 9, 11, 23, 42 (8 regions) and procedural 32x10 seeds 7, 11, 13, 17, 21, 31; 200 turns;
`--agents hybrid --simulate-only --grain-reserves --grain-storage --repair-projects
--infrastructure-condition`, `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`. Arms: `repair` with
`--local-budgets --maintenance-obligation`; `repair_treasury` (repair without L9, treasury-funded);
`wear_only` with L9 (the control). 39 runs; plus the `repair` arm on the pre-review source
`d6c27e81` (13 runs) for the before/after of review M2. Raw outputs deleted; compact statistics in
`/home/user/evidence/b3/activation-32d27330.json` and `activation-before-d6c27e81.json` (outside the
repository). Arms diverge once any spending differs, so differences between arms are not effects of
the mechanism.

| Stratum, arm | Assets (irr./roads) | Failed / restored | Failed asset-turns | Works opened / completed | Progress / stalled work-turns | Stalls: timber / envelope / labour / coins / granary first | Work delivered | Charged (coins, destroyed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| template, repair | 131 (60/71) | 41 / 3 | 1,903 | 113 / 0 | 8 / 11,418 | 7,270 / 7,405 / 4,013 / 59 / 0 | 10.1 | 8 |
| template, repair_treasury | 136 (61/75) | 69 / 30 | 1,963 | 125 / 7 | 112 / 11,529 | 7,457 / — / 4,069 / 4 / 0 | 64.9 | 46 |
| template, wear_only | 128 (58/70) | 39 / 0 | 1,949 | — | — | — | 0 | 0 |
| procedural, repair | 391 (182/209) | 129 / 11 | 5,548 | 373 / 16 | 119 / 35,604 | 21,298 / 21,609 / 13,648 / 246 / 309 | 190.7 | 128 |
| procedural, repair_treasury | 403 (186/217) | 162 / 40 | 4,719 | 433 / 78 | 480 / 34,194 | 20,987 / — / 13,206 / 199 / 0 | 560.2 | 341 |
| procedural, wear_only | 401 (185/216) | 129 / 0 | 6,174 | — | — | — | 0 | 0 |

A stall turn can carry several reasons (a work without timber usually also lacks an envelope), so
the reason counts exceed the stalled turns.

**Awarded against delivered (review M2), `repair` arm with L9, before (`d6c27e81`, works pooled into
RS2's proposal) and after (`32d27330`, the works' own proposal).** For every awarded L9 proposal
carrying works, the works' receipts of that civ in the next turn:

| Stratum | Proposals carrying works | Awarded (coins) | Next turn: works' charge | Works' work delivered (irrigation) | Works receipts with nothing delivered |
| --- | --- | --- | --- | --- | --- |
| template, before | 113 | 10 (37) | 5 | 2.5 (0.0) | 18 of 20 (irrigation 4 of 4) |
| template, after | 64 | 8 (11) | 8 | 10.1 (10.1) | 32 of 40 (irrigation 10 of 18) |
| procedural, before | 99 | 20 (88) | 35 | 17.3 (13.8) | 95 of 107 (irrigation 42 of 51) |
| procedural, after | 424 | 121 (212) | 128 | 190.7 (190.7) | 676 of 795 (irrigation 271 of 390) |

Before, an award priced on irrigation's relief mostly paid RS2 (37 award coins bought 2.5 units of
works in template worlds, none of it irrigation); after, an award funds only the works it names:
the works' charge is 73% (template) and 60% (procedural) of the coins awarded, and their delivered
work per awarded coin rises from 0.07 to 0.91 (template) and from 0.20 to 0.90 (procedural). The
receipts counted are every work of the civ, including roads and works the screen kept out of the
proposal, so the zero-delivery counts are upper bounds for the proposed works; the remaining
zero-delivery receipts are partial awards (a divisible proposal funds its first works in split
order, the rest stall `no_envelope`), timber taken by RS2 or others before the works plan, and
roads (not proposed). Without the maintenance reservation and RS2's envelope room the works do
less in all under L9 than before (template 10.1 against 53.0 work units, procedural 190.7 against
303.2): the envelope is now spent only on what was awarded for.

- **Activation.** Every world builds irrigation and roads (15-24 assets per template world, 55-78
  per procedural world, across the arms); under declared wear every world has failed assets by
  turn 200 (4-7 per template world, 17-26 per procedural world in `wear_only`). Ends (any arm):
  earthquakes in every world, scorched earth in 2 template and all 6 procedural worlds, a
  supervolcano destroying records in template 1, 7 and 23 and procedural 7 (template 23 loses six
  assets in three regions at turn 167, the supervolcano's turn); conquest damage in 2 template and
  all 6 procedural worlds.
- **The underfunded public works story.** With L9 works almost never progress: 0.07% (template)
  and 0.3% (procedural) of work-turns deliver. Timber binds nearly every work (`no_timber`), the
  works' own envelope binds as often, and labour binds where there are no farmers. Template
  worlds' works are proposed 64 times and awarded 8 times in 7 worlds; without L9 (`repair_treasury`)
  they progress 14 times as often, still timber- and labour-bound.
- **Outcomes are mixed.** Failed asset-turns: repair with L9 1,903 and 5,548 against the control's
  1,949 and 6,174; the treasury arm 1,963 and 4,719. Repair restores few failed assets (3 and 11 with
  L9); in the treasury arm a little work repeatedly lifts failed assets just above 0 before they
  fail again (30 and 40 restorations, 69 and 162 failures). Single development worlds per seed, not
  a screen.
- **Food at risk** (irrigation, observed each Phase 10 with an economy tick): up to 60.1 (template)
  and 78.1 (procedural) food units over the 10-turn horizon for one asset.
- **Granary first.** In procedural worlds 309 work-turns stalled because the region's storage asked
  for work that turn (`granary_first`, now decided by storage's actual request); template worlds
  had none.
- **Timing.** About 7-9 s per template world and 17-23 s per procedural world over 200 turns (no
  separate profiling at a declared scale).

### Timber link re-measure (development worlds only; no held seed; no tuning)

The works' timber need entering PL1 after RS2's (section 5), measured before (`518407eb`) and after
(`dbfcd84a`, the link with the review's store fix; at `9daaec56`, before that fix, only procedural
13 under L9 differed: 12 expeditions for the works, 144 person-turns, timber stalls 4,348, works
117.3 (12), RS2 368.9 and 1,860 timber stalls, 785 woodcutter person-turns) on template seeds 7
and 11 and procedural seed 13
(32 regions, 10 civs), CW3b's work arms at 200 turns: `C` (L9 and the maintenance obligation) and
`C_T` (treasury), both with RS2, grain storage, the L3 stock and PL1. Extension
`20e77f99...c0c1ca`; script and compact output `/home/user/evidence/b3/timber_remeasure.py` and
`timber-remeasure3.json` (outside the repository; `timber-remeasure.json` holds the `9daaec56` side). The two sides follow different trajectories
once anything differs, so a single world's difference mixes the link with trajectory divergence.

| World, arm | Expeditions for the works (woodcutter person-turns) | Works' timber-stall work-turns before / after | Works' work delivered before / after (completed) | RS2 work delivered before / after | RS2 timber-stall work-turns before / after | All woodcutter person-turns before / after |
| --- | --- | --- | --- | --- | --- | --- |
| template 7, C | 0 | 1,250 / 1,250 | 0 / 0 | 22.7 / 22.7 | 936 / 936 | 64 / 64 |
| template 7, C_T | 1 (18) | 1,317 / 1,294 | 17.9 (3) / 15.7 (3) | 66.8 / 72.7 | 791 / 905 | 34 / 57 |
| template 11, C | 0 | 1,203 / 1,203 | 0.29 / 0.29 | 41.7 / 41.7 | 617 / 617 | 5 / 5 |
| template 11, C_T | 4 (37) | 930 / 955 | 11.0 (1) / 38.2 (5) | 65.1 / 86.1 | 506 / 468 | 111 / 104 |
| procedural 13, C | 3 (36) | 4,147 / 4,256 | 77.4 (8) / 112.1 (11) | 296.3 / 442.0 | 1,782 / 1,638 | 696 / 707 |
| procedural 13, C_T | 3 (35) | 3,774 / 3,764 | 282.1 (50) / 266.7 (49) | 490.4 / 466.4 | 1,721 / 1,906 | 764 / 765 |

- **PL1's own rules bind the works' need.** Of the works' need rows, PL1 refused most:
  `no_forest` (template 7: 482 C, 557 C_T rows; procedural 13: 669 / 523) and `forest_depleted`
  (template 11 C_T 497; procedural 13 794 / 1,451), then `forest_busy` and `too_far`; it launched
  1-4 expeditions per world and arm. Under L9 on the template worlds it launched none (every row
  refused or covered), and the run's counters are unchanged (the record gains its rows).
- **Timber stalls barely move** (-1.7% to +2.7% of work-turns): the works still lack timber
  wherever PL1 can reach no healthy free forest.
- **Works delivered:** up in template 11 C_T (x3.5, completions 1 -> 5) and procedural 13 C (+45%,
  8 -> 11 completions); down in template 7 C_T (-12%) and procedural 13 C_T (-5.5%).
- **RS2 displacement (harm):** RS2's delivery rose in three activated arms (+9%, +32%, +49%; the
  works' deliveries to a shared store and trajectory changes) and fell in procedural 13 C_T (-4.9%),
  where RS2's timber-stall work-turns rose 10.7% (1,721 -> 1,906); in template 7 C_T they rose 14%
  while RS2's delivery rose. RS2 is served first within each turn; displacement acts across turns,
  through forests and crews a works' expedition still holds when RS2 next needs them.
- Woodcutter time follows the launches (up to +23 person-turns, template 7 C_T).

### Verification

Section 9.

## 9. Verification record (2026-11-07; branch `claude/cw-b3-infrastructure`, code at `dbfcd84a`)

Source: the branch head (main 66e1ec40 merged at `33fc1685`, main bac45cb5, PR #90, at `8da9ead4`;
the reviewer approved `10d73230`; the flow x condition integration at `c5593e81`, approved at
`453d307c`; the skipped-damage counter and the CW3b revisions at `7364c643`/`518407eb`; the works'
timber need in PL1 at `733e5e08`/`9daaec56`, approved at `0187bfb5` with one minor; the review's
fixes (the store kept only where works ask, PL1's `launched_works`, the CW3b pair gate) at
`dbfcd84a`; later commits are documents, the CW3b pilot and held-run files and the registry's
run record; layer `cwb3`
last, after `cwd2` and `cwb2`, unchanged since `8da9ead4`: the timber link touches no pinned file).
Every native step used `PYTHONPATH=<worktree>/src` and the extension at `~/.venvs/native-a3`,
SHA-256 `20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`, built from Rust
identical to main (no Rust change in this lane, so `cargo test` was not rerun). Compact evidence
under `/home/user/evidence/b3/` (outside the repository). Every check below ran at `dbfcd84a`.

| Check | Result |
| --- | --- |
| Focused offline tests | `tests/test_infrastructure_condition.py` 69 passed; with PL1, RS2, PL3, the screen runner, the CW3 screens, watershed, money, A1, catalog and manifest: 490 passed |
| Witness and pin modules (the playbook's list) | 509 passed, 61 subtests passed |
| Bounded offline lane (`scripts/run_python_oracle_checks.py`) | PASS in 300.4 s: 70 chunks, 7,419 passed, 69 skipped, 0 failed; `connected-world-b` 135 passed in 4.6 s of 110 s |
| Native pytest (real extension) | 66 passed in 160.1 s: `test_infrastructure_condition_native.py` (5, including the exact resume with an outstanding timber order) with the RS2, PL3, closure, PL1, L3, A1, A3, D2 and watershed native modules |
| Feature-off identity against `8abc1acb` (`turn_speed_identity.py`, the 9 standard cases) | 9 cases, 399 files compared, 0 differences |
| Feature-off identity against the preceding main `bac45cb5` | 9 cases, 399 files compared, 0 differences |
| Each switch alone against `518407eb` (the head before the timber link; hybrid_s42 and proc48_hybrid_s42 with grain storage, RS2, the L3 stock, PL1, L9 and the maintenance obligation): B3 off, `record_only`, `wear_only` | each 2 cases, 205 files compared, 0 differences |
| B3 `repair` **without** PL1 against `518407eb` (the same cases, RS2 and L9) | 2 cases, 205 files compared, 0 differences: the link acts only through PL1 |
| Positive control: B3 `repair` **with** PL1 against `518407eb` (treasury) | differs by intent (hybrid_s42 3 files, proc48_hybrid_s42 69 files): the comparisons above are not vacuous |
| Exact resume, every livelihoods switch with retail everywhere, A3, D2, A1, PL1 and B3 (`hybrid_s42_long`, 19 resume points) | PASS: checkpointing changes nothing, every resume byte-identical |
| Exact resume, watershed `flow` x condition with RS2, L9 and the maintenance obligation (`proc32_hybrid_s11`, 39 resume points) | PASS |
| Exact resume, B3 `repair` with PL1 and the L3 stock (treasury; `proc32_hybrid_s11`, 39 resume points) | PASS |
| Viewer | full suite 1,626 passed and 2 skipped (163 files, `--maxWorkers=2`); `npm run lint` clean; `npm run build` passes |
| CW3b screen | `check --screen all` passes (42 outcomes, 3 primary); timing pilot at `dbfcd84a` (template 5, procedural 19) 12 runs, 0 failed, every arm activated, every pair in the primaries; `check --metrics` passes; held run on the frozen code: 72 runs, 0 failed, 0.288 core-hours, `check --metrics --cohort held` passes |

**After merging `main` d8a5277b (PR #91, C2 epidemic care) at `7d19b2d6`.** Switch order `...,
workshop_economics, infrastructure_condition, epidemic_care, attribution_records, wealth_accounting`
(C2's guard: only observers follow its carers); L9 providers `..., epidemic_care,
infrastructure_condition`; money books and bills in landing order; layer `cwb3` rebuilt last, after
`cwc2`, against d8a5277b (the same 7 B3 hunks). The works' own labour is the anonymous storage column
and names nobody; the woodcutters PL1 sends for them hold the native registry's `repair` category,
which C2's shared query (`labour_reservations.booked`) reports (a test), so no carer is booked twice
with them. Checks at `7d19b2d6`: feature-off identity against `8abc1acb` and against d8a5277b, 9
cases and 399 files each, 0 differences; B3 off with PL1 and L9 against d8a5277b (hybrid_s42,
proc48_hybrid_s42) 205 files, 0 differences; `record_only` against d8a5277b without the switch:
only the bundle and `state.json` differ, and they are equal once the B3 record and its two keys are
removed; exact resume with every livelihoods switch, C2 in place of A1 (they exclude each other),
B3 and PL1 (`hybrid_s42_long`, 19 resume points) PASS, and flow x condition (`proc32_hybrid_s11`, 39)
PASS; offline lane PASS (71 chunks, 7,481 passed, 0 failed); native B3, PL1, C2, RS2, closure and
watershed modules 28 passed; witness 509 passed; viewer 1,636 passed, lint and build clean; every
stored screen report (CW1, CW3, CW4, CW4b, CW5c, CW3b; held and pilot) regenerates byte for byte
under the merged runner. The CW3b gate then moved to `Outcome.pair` (the CW3b page, post-run
refactor): numbers unchanged, excluded cells labelled.

**After merging `main` 4ecfb54d (PR #92, A4 titled trade, new Rust) at `a370923c`.** Switch
order `..., workshop_economics, titled_trade, infrastructure_condition, epidemic_care,
attribution_records, wealth_accounting` (B3 books labour, so before C2's carers; C2's guard green;
A4's order test names B3 between titled trade and C2); money books append-only with B3 last; layer
`cwb3` rebuilt last, after `cwa4`, against 4ecfb54d (the same 7 B3 hunks); the runner is `main`'s.
Every native step used `~/.venvs/native-a4` (extension `43cbd22a...`, `main`'s Rust; B3 changes no
Rust). Checks at `a370923c`: feature-off identity against `8abc1acb` and against 4ecfb54d, 9 cases
and 399 files each, 0 differences; B3 off with PL1 and L9 against 4ecfb54d (hybrid_s42,
proc48_hybrid_s42) 205 files, 0 differences; `record_only` against 4ecfb54d without the switch:
bundle and `state.json` equal once the B3 record and its keys are removed; exact resume with every
livelihoods switch, C2 in place of A1, titled trade, B3 and PL1 (`hybrid_s42_long`, 19 resume
points) PASS, and flow x condition (`proc32_hybrid_s11`, 39) PASS; offline lane PASS (71 chunks,
7,562 passed, 0 failed); native B3, PL1, C2, A4, RS2, closure and watershed modules 36 passed;
witness 509 passed; every stored screen report (CW1, CW2, CW3, CW4, CW4b, CW5, CW5c, CW3b; held and
pilot) regenerates byte for byte, CW3b held with only its 14 exclusion labels; viewer 1,646 passed
with one timeout under a load average near 6.6 (`FeatureOptions`, 7.8 s against 5 s; 14 of 14 alone),
lint and build clean.

Earlier identities still standing: `--watershed-mode flow` alone against main bac45cb5 (92 files, 0
differences, at `e2b62e6c`) and `--infrastructure-condition` alone without L9 against the approved
`10d73230` (205 files, 0 differences, at `e2b62e6c`); with `--local-budgets` the condition switch
alone differs from `10d73230` by the award fix (an envelope funds only the works in its recipient
regions), the one intended change since `10d73230` apart from the timber link (which acts only with
PL1) and the skipped-damage record (present only once a damage was skipped).

**Not run:** a desktop and phone browser journey (V8), profiling at a declared scale (V11), the
narration audit (no narration change), the 200-seed
gate and the procedural qualification gate.

## 10. Limits and open questions

- **Named crews require PL3.** With `--recovery-crews`, works use the named, paid or unpaid
  farm crews described below. Without PL3, the earlier anonymous, unpaid labour contract remains.
  Neither path reassigns native occupations.
- **Material coins are destroyed.** The `public_works` material sink pays no one (section 5).
  Accepted named wages use the separate treasury-to-agent channel described below; they are not
  recorded as a public-works sink.
- **PL1 supply is bounded by PL1's own rules.** The works now ask PL1 for timber after RS2
  (section 5), but PL1 sends a crew only to a healthy forest within two hops that no other crew is
  cutting, so many works' needs are refused `no_forest`, `too_far`, `forest_busy` or
  `forest_depleted` (section 8, timber link re-measure); a crew's harvest follows the forest
  slot's labour curve and can be small. None of PL1's constants was changed for B3.
- **Road relief is a declared maintenance stake.** Outstanding repair worker-turns are valued
  in the patrician work unit, not as measured trade gains. Partial grant expectations are
  proportional and may miss the fixed-order delivered mix; settlements expose this deferral.
- **granary_first is decided by storage's actual request** in Phase 2, but the L9 proposal's screen
  predicts it from the current storage policy (L9 decides next turn's storage policy in the same
  Phase 10).
- **`cost_only` is RS2's convention**: a work whose scope was delivered without credit closes and
  reopens larger while the asset stays worn, so it is not a same-spend control after the first
  completion.
- **D2 attribution** records accepted conquest/sack damage in its own asset-condition unit when
  `--attribution-records` is active. Skipped duplicate damage and floods create no foreign burden.
  This observation creates no grievance or estimated food/money harm.
- Ports are deferred (no consumer reads the type). Flood damage per unit of excess is declared and
  uncalibrated (floods are rare and small under `flow`). Constants are declared and uncalibrated;
  nothing was tuned on held seeds, and the 200-seed gate is unrun.
- **CW3b held screen (run 2026-11-07, frozen code `dbfcd84a`;
  `docs/superpowers/progress/connected-world-screens-cw3b.md`, Results):** 72 runs, 0 failed, 0.288
  of 0.50 core-hours. Treasury-funded repair kept more irrigation serving on every gated world that
  differed (procedural +0.12, 4 of 4; template +0.05, 4 of 5); under L9 procedural +0.09 (4 of 4)
  but template a null (+0.02; the L9 works delivered 5.8 work units per world); food shortfall in
  the irrigated regions lower under L9 repair (procedural -0.016, 4 of 4; template -0.006, 3 of 4).
  Harms beside it: RS2 delivered less repair under L9 (5 of 6 procedural worlds), treasury-funded
  works sent more woodcutters (procedural +180 person-turns, 6 of 6), and the works stalled for
  timber on every world under PL1's real forest limits. Whole-trajectory differences on four to six
  worlds per stratum; no promotion.

### Named farm crews (opt-in PL3 integration)

When `--recovery-crews` is also active, every B3 irrigation/road request is
limited to a named crew of living adult farmers in its region. Existing PL3
exclusions apply: enlisted, trips, health work, mentors and shared-registry
holders cannot be named. Earlier RS2/granary commitments keep priority. Each
person contributes only their available farm share; the native shared labor
column removes exactly the delivered named work from farming. No anonymous
labor fills a named request. Unpaid PL3 control names, reserves and withholds
the same work. PL3 being off preserves the explicitly anonymous B3 contract.

Paid crews request 500 milli-coins per actual delivered worker-turn (the
existing repair wage). Irrigation's remaining 100 milli/work is material;
roads' nominal 500 milli/work is the wage. Fractional rounding can leave a
small material remainder. `infrastructure_wage` routes through native
`repair_wage`, batch `0xB3000 + civ`, separate from all existing consumers.
Every payer's wages and materials are quoted against one finite treasury and
one envelope before either bill is paid. Planning reserves one additional
whole coin to cover the separate rounding of wage and material bills; this is
a conservative restriction, especially on a one-coin envelope. Material and
wage prepaid balances are distinct. The wage seam returns refused/absent
credits to the payer's carry or treasury. Only accepted wages enter wealth;
materials enter `public_works`. No money is minted from a sink.

The named ledger records nominal cost, actual accepted cost, requested,
accepted/refused wages and both prepaid balances. Its integer closure is
`charged*1000 + material_before + wage_before = actual_cost + material_after + wage_after`.
The same native paid-work receipt supplies each person's ordinary income
withheld. Receipts retain stable ids, reservation/work shares and individual
wages. `cost_only` changes no condition while retaining these same work and
money mechanisms. None of this constitutes native occupation reassignment,
a second spendable balance or a globally conserved cash system.

A natural procedural seed 31, 32 regions, 10 agents per region, 72-turn development run with PL1 supplied real
active crews and passed exact resume at turn 61. The earlier 44-turn run had no B3
crew activation because timber was unavailable; that null is not evidence
that wages ran. The helper contracts additionally exercise trip/registry and
age exclusions, no duplicate worker, unpaid control and wealth-ceiling
refusal with exact ledger closure. No fresh held efficacy cohort was consumed.


## L9 road completion, 2026-11-07

The earlier CW3/CW3b tables above describe their exact historical irrigation-only L9 source;
those held results are retained and do not qualify this follow-on. The current contract includes
roads in the same finite works envelope, exact stable work claims, dated worker-turn burden,
and per-kind promise settlement. Constructed tests exercise a real L9 decision, partial mixed
bundles, an unpromised same-region work, named paid repair and cost-only control, and a
PL1 expedition that delivers timber before L9 funds the named road crew. They retain PL1's
sole forest/crew/store authority and the shared native work column. Native and integrated
held/profile evidence must name the later source explicitly.

Follow-on verification on the isolated Python source (parent `39d5ef5e`, unchanged
native Rust source at `e3bce686`; read-only extension SHA256
`f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`):

- 248 focused offline tests passed on CPython 3.13.16: infrastructure condition,
  local budgets, PL3 crews, PL1 timber supply, repair projects, shared treasury and
  maintenance obligation. The native module remains in its existing shard.
- A natural development procedural seed 31, 32 regions / 10 civs, 72 turns with
  grain reserves/storage, RS2, B3, PL3, L3, PL1 and L9 delivered 9 progressing road
  receipts: 20.40 worker-turns, 10.20 timber and 10,196 milli accepted named wages.
  Its 12 works settlements were 11 kept and 1 deferred. This is activation evidence,
  not an efficacy comparison or held qualification.
- The first raw CLI attempt stopped because this isolated lane lacked the lead's
  A1 `infrastructure_wage` channel registration. The test supplies that shared
  registration explicitly. The subsequent native journey exposed two real B3
  integration defects: settlement used the first plan's zero allowance instead
  of the finite whole-service envelope; and an absent individual native income
  receipt raised despite the shared PL3 lifecycle contract. Both failures were
  retained. Regression tests now keep an unpromised first irrigation plan while
  funding a later road, and distinguish a missing whole receipt (error) from a
  missing individual row (unknown withheld income). Exact wages are unchanged.
- The corrected 72-turn run and checkpoint resume at turn 61 passed in 11.39s,
  crossing open road works. The strengthened test checkpoints at turn 66, inside
  a funded road promise, and requires the complete history, final world and state
  file to match exactly. Final integrated native, compatibility, profile and CI
  gates still belong to the lead; this local run does not establish them.

Reproduce the bounded native journey with
`PYTHONPATH=src <verified-native-python> -m pytest -q tests/test_infrastructure_condition_native.py -k l9_named_road`.
The test uses only the development seed, supplies the isolated A1 registration,
and records no paid narration call. Evidence logs and bundles are kept outside
Git under `/workspace/evidence/b3/l9-roads-*` for this session.
