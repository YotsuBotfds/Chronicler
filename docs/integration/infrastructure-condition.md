# Infrastructure condition and repair (B3, `--infrastructure-condition`)

Status, 2026-11-07: connected-world program, lane B3 (Program B item 3). Experimental and **off by
default**; nothing here is calibrated or scientifically qualified. Design source: the program-B
contract audit (`docs/superpowers/audits/connected-world/audit-b-watershed-infrastructure.md`,
sections 3 and 7.3, its **sibling-record** alternative) and the lead's decisions
(`docs/superpowers/roadmaps/connected-world-program.md`, 5.2): irrigation and road condition live
in their own record keyed by a stable infrastructure id, so RS2's schema, record and viewer stay
unchanged; works are repaired with the same labour channel, timber and L9 `repairs` envelope as
RS2's projects, so no budget is spent twice; ports are deferred; roads gain service-gated range
only (no transport discount).

Code: `src/chronicler/infrastructure_condition.py`, `src/chronicler/infrastructure_condition_state.py`;
guarded seams in `repair_projects.py`, `maintenance_obligation.py`, `local_budgets.py`, `money.py`,
`wealth_accounting_state.py`, `techniques.py`, `resources.py` and the pinned `economy.py` and
`agent_bridge.py` (witness layer `cwb3`); viewer `viewer/src/lib/infrastructureCondition.ts`,
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
  inserted before `wealth_accounting` (the ledger still runs last); state
  `WorldState.livelihoods.infrastructure_condition`; `batch_manifest.SIMULATION_ARG_KEYS` lists
  `infrastructure_condition` and `infrastructure_condition_mode`, both omitted from the recorded
  configuration when unset, so feature-off manifests keep their bytes.
- Feature catalog: `REQUIREMENTS["infrastructure_condition"] = (hybrid, any(mode in {record_only,
  wear_only}, --repair-projects))`; the catalog test checks it against the run's own refusals.
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
  `earthquake` (an `earthquake` event of the region this turn), `scorch` (a `scorched_earth`
  event naming the region this turn), else `unknown`; a removed list ends `record_removed`. A
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
| `WAR_DAMAGE` | 0.25 x `repair_projects.war_damage` | per real conquest or sack (RS2's hooks), at most one damage per asset and turn |
| `FLOOD_DAMAGE_PER_EXCESS`, `FLOOD_DAMAGE_CAP` | 0.5, 0.5 | the flood seam (`flood_damage`), for the watershed's flow mode |
| `OPEN_BELOW` | 0.75 | a wear work opens below this (RS2's threshold) |
| `WORK_PER_CONDITION` | 20 (both kinds) | work units restoring a whole unit of condition |
| `WORK_PER_TURN` | 4 | most work one asset's work asks per turn (the storage batch) |
| `TIMBER_PER_WORK` | irrigation 0.25, roads 0.5 | lead decision |
| `COINS_PER_WORK` | 2 | the storage rule |

- **War damage** is recorded only at RS2's two existing real events: region conquest
  (`repair_projects.region_conquered`, called from `action_engine.apply_region_conquest`) and a city
  sack (`repair_projects.city_sacked`), each before RS2's own active check, so B3 damage applies in
  every B3 mode even without RS2. Granary seizure is granary-only. The cause is the war's
  `(war_key, war_start_turn)` when found (RS2's `_war_identity`).
- **Flood damage** (`infrastructure_condition.flood_damage(world, region, excess, ref=...)`) is a
  clean seam: nothing calls it until the watershed's `flow` mode exists (a test fails if a caller
  appears unreviewed).

## 4. Consumers

One helper, `infrastructure_condition.service(world, region, kind)`, returns **exactly 1.0** while
the switch is off, in `record_only`, outside hybrid, or for a record not yet registered:

| Consumer | Edit | Off |
| --- | --- | --- |
| `economy.arable_capacity` (pinned) | `mult += FARM_CEILING_IRRIGATION * service(...)` | `0.10 x 1.0 == 0.10`: bit-identical |
| `agent_bridge.build_region_batch` `has_irrigation` (pinned) | `active and serves(...)` (service >= 0.5) | `True and True`: identical |
| `techniques.extend_trade_routes` (road practice) | the intermediate road must serve | identical |
| `resources._compute_active_trade_routes` (railways focus) | the intermediate road must serve | identical |

The irrigation **technique** (+5% grain, +10% ceiling) is a separate practice and unchanged. The
Python ecology fallback's irrigation read (`ecology.py`, pinned by RS5) is not gated: B3 needs
hybrid, where the native ecology reads `has_irrigation`. No road transport discount is added
(`INFRASTRUCTURE_DISCOUNT` stays the placeholder 1.0).

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

- **Labour: anonymous farm labour through the native `granary_work_requested` column** (the
  storage channel; the economy delivers `min(request, farmers x farm_labor_factor)` and removes it
  from farming). No named crew: PL3's named crews stay granary-only (see Limits). The column is
  shared in a fixed order, **granary -> irrigation -> roads**, recorded on each receipt
  (`granary_request`, `shared`) and in the frame (`shared` regions):
  - grain storage off: B3 appends the column;
  - a region whose storage asks for work this turn (maintain below condition 1.0, expand) belongs
    to the granary: the works stall `granary_first`;
  - a region whose storage would ask for nothing (no owner, `neglect`, maintain at 1.0) is
    **claimed** for the works through RS2's suspension seam (`storage_suspended_regions` adds
    `storage_claims`), so storage's settlement reads it as suspended; this changes nothing storage
    would have done (its budget and timber planning are untouched). L9's granary skip still reads
    RS2's own projects only (`granary_project_regions`);
  - a region under an RS2 granary project: the works add to RS2's request; RS2 takes
    `min(delivered, its request)` first, the works the rest.
  - A region with no farmer in the Phase 2 rows: the works stall `no_labor`.
- **Timber:** `TIMBER_PER_WORK` per unit from RS2's free timber after RS2's holds (stockpile minus
  merchant commitments, plus the PL1 store), added to RS2's per-region holds (so the store is taken
  first and a failed tick returns everything with RS2's holds); the unused part is returned after
  the tick (store part through PL1's `return_store`).
- **Coins:** `COINS_PER_WORK` per delivered unit, rounded up to the milli-unit; one whole-unit charge
  per civ and turn, the sub-unit remainder prepaid toward the civ's next works (RS2's rule). The
  works plan **after** every Phase 2 bill RS2 plans around and after RS2's own planned charge,
  whose rounding is reserved whole (RS2 never charges above `ceil(planned / 1000)`), against both
  the treasury and the civ's **one `repairs` spending limit** (the L9 envelope plus a maintenance
  reservation, RS2's `_envelope`). So `RS2 charge + works charge <= limit` (checked on every ledger
  row) and no coin is promised twice. Later Phase 2 planners see the works' planned coins
  (`repair_projects.pending_bills`).
- **Payment:** the charge is paid **through the payment seam** (`money.pay`): treasury -> the
  declared sink `public_works` (appended to `money.SINKS`), purpose `infrastructure_repair`
  (appended to `PYTHON_PURPOSES`), batch = civ index, so each (turn, purpose, batch) settles exactly
  once (persisted keys); the bill is registered in `wealth_accounting_state.MONEY_BILLS`
  (`("infrastructure_condition", "_charge")`) and the package's book in `money.MONEY_BOOKS`. No
  agent wealth moves (no ledger channel is needed).
- **Stalls** (a turn without delivered work, per reason): `no_timber`, `no_coins`, `no_labor`,
  `no_envelope`, `granary_first`. A reason that only limited the work is counted as `limited_*`.

**L9 (`--local-budgets`).** The works join RS2's single divisible `repairs` proposal per ruler
(one rounding, one envelope; `detail.infrastructure_works`). Their relief is a declared rule owned
by B3 (lead decision): **commons food at risk relieved** = the irrigation arable ceiling the
proposed work keeps over L9's `horizon` (service with the work minus service without, each turn
under `WEAR`) x the region's observed food production (`food_ledger` produced) / its arable
capacity. It is positive **before failure**, as soon as service would fall within the horizon
(condition below `0.5 + horizon x 0.01`, 0.6 with the default horizon); far from the gate it is 0, so
those works are funded only through a maintenance reservation. Roads carry no relief of their own.
RS2's settlement adds the works' charge and delivered work (`detail.infrastructure_works`,
`infrastructure_charged`) and their stall reasons; the maintenance obligation splits the combined
charge (`ReservationUse.charged` = RS2 + works) pro rata, so its closure holds for the one limit.
Each irrigation asset also records `food_at_risk`: the food its region would lose over the horizon
without repair (observed each Phase 10 with an economy tick; null otherwise).

## 6. Accounting and closure

Per civ and turn (`WorksLedger`, `check_ledger` when written; the viewer re-checks):

    charged x 1000 + prepaid_before == coin_cost + prepaid_after     (prepaid in [0, 1000))
    charged + rs2_charged <= envelope                                (with L9)

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
`damages` (last 32), `receipts`/`ledger`/`unmet`/`shared` (all null when the turn had no settled
Phase 2 in a work mode: unknown, not zero; receipts and ledger are always null in
`record_only`/`wear_only`, which have no works), `prepaid`, `sink_milli`, `counters` (declared set)
and `parameters`. The strict viewer reader keeps disabled, absent, malformed, unsettled, no-works and
recorded-zero states distinct; the panel shows the asset table (condition, applied service,
status, food at risk, a condition trace across the run's snapshots), the works (progress, this
turn, stall turns by cause, funding), the charges against the one repairs limit, and the run's most
stalled work as the directly recorded "underfunded public works" story.

## 8. Evidence

### Tests

- `tests/test_infrastructure_condition.py` (offline): identity matching and lifecycle (every end
  cause, removal, rebuild, mid-turn damage skipping an ended record), wear, service and failure
  (failed is not rebuilt), consumers bit-identical when off and in `record_only`, the road range
  gates, works moving real labour, timber and coins once, a failed tick returning every hold, the
  granary-first split in a shared column and in a working storage region, every stall cause, one
  envelope for RS2 and the works, the L9 settlement and the maintenance split reading both
  charges, the proposal's food-at-risk relief, cost-only, completion of a failed asset, the
  wear-only control, `record_only` equal to off except the record over four turns, an exact pickle
  resume at an open work, switching off, the flood seam, invalid combinations, and the payment
  registration.
- `tests/test_infrastructure_condition_native.py` (real extension, about 17 s): procedural seed 31
  60 turns with `CHRONICLER_CHECK_RESOURCES=1` (every receipt and ledger closes; the sink equals the
  charges; conquest damage and scorched records occur); an exact checkpoint resume at turn 37
  inside open works (history, world state and `state.json` byte-identical); template seed 11 40
  turns `record_only` equal to the switch off except the record.

### Development activation (development worlds only; not a screen, no held seed)

Source `d6c27e81` (identical `src` to the branch head), extension
`20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca` (main 8401aa74's Rust). Template
seeds 1, 3, 7, 9, 11, 23, 42 (8 regions) and procedural 32x10 seeds 7, 11, 13, 17, 21, 31; 200 turns;
`--agents hybrid --simulate-only --grain-reserves --grain-storage --repair-projects
--infrastructure-condition`, `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`. Arms: `repair` with
`--local-budgets --maintenance-obligation`; `repair_treasury` (repair without L9, treasury-funded);
`wear_only` with L9 (the control). 39 runs, 6.5 minutes in all; raw outputs deleted, compact
statistics in `/home/user/evidence/b3/activation-d6c27e81.json` (outside the repository). Arms
diverge once any spending differs, so differences between arms are not effects of the mechanism.

| Stratum, arm | Assets (irr./roads) | Failed / restored | Failed asset-turns | Works opened (wear/war) / completed | Progress / stalled work-turns | Stalls: timber / envelope / labour / coins / granary first | Work delivered | Charged (coins) | L9 repairs proposals with works (awarded) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| template, repair | 132 (60/72) | 42 / 2 | 1,824 | 118/1 / 7 | 52 / 11,386 | 6,962 / 7,214 / 4,171 / 138 / 0 | 53.0 | 109 | 113 (10) |
| template, repair_treasury | 136 (61/75) | 69 / 30 | 1,983 | 125/0 / 7 | 112 / 11,549 | 7,462 / — / 4,084 / 8 / 0 | 64.9 | 136 | — |
| template, wear_only | 128 (58/70) | 39 / 0 | 1,949 | — | — | — | 0 | 0 | — |
| procedural, repair | 388 (180/208) | 128 / 11 | 5,341 | 392/1 / 41 | 214 / 34,733 | 22,219 / 22,302 / 12,226 / 492 / 148 | 303.2 | 621 | 99 (20) |
| procedural, repair_treasury | 407 (184/223) | 156 / 29 | 4,932 | 428/2 / 75 | 394 / 34,045 | 20,027 / — / 14,009 / 495 / 0 | 521.7 | 1,066 | — |
| procedural, wear_only | 401 (185/216) | 129 / 0 | 6,174 | — | — | — | 0 | 0 | — |

A stall turn can carry several reasons (a work without timber usually also lacks an envelope), so
the reason counts exceed the stalled turns.

- **Activation.** Every world builds irrigation and roads (16-24 assets per template world, 58-72
  per procedural world); under declared wear every world has failed assets by turn 200 (4-7 per
  template world, 17-26 per procedural world in `wear_only`). Ends: earthquakes in every world,
  scorched earth in 1 template and 5 procedural worlds, a supervolcano destroying records in
  template 1, 7 and 23 and procedural 7 (checked against the event: template 23 loses six assets in
  three regions at turn 167, the supervolcano's turn); conquest damage in 2 template and 5
  procedural worlds (repair arm).
- **The underfunded public works story.** Works open as assets wear below 0.75 but almost never
  progress: with L9 and the maintenance obligation, 0.5% (template) and 0.6% (procedural) of
  work-turns deliver. Timber binds nearly every work (the RS2 lesson, `no_timber`), and the L9
  envelope binds as often: the repairs proposals that carry works are few (113 and 99 proposals
  over the two strata) and rarely awarded (10 and 20), partly because a work without free timber
  proposes nothing. Labour binds in regions without farmers (`no_labor`). Without L9
  (`repair_treasury`) twice as many work-turns deliver and more work is done (64.9 and 521.7 units
  against 53.0 and 303.2), still timber- and labour-bound.
- **Outcomes are mixed.** Failed asset-turns are lower with repair than in the control in both
  strata (1,824 and 5,341 against 1,949 and 6,174; the treasury arm 1,983 and 4,932), but repair
  restores few failed assets (2 and 11 with L9); in the treasury arm a little work repeatedly lifts
  failed assets just above 0 before they fail again (30 and 29 restorations, 69 and 156 failures).
  These are single development worlds per seed, not a screen.
- **Food at risk** (irrigation, observed each Phase 10 with an economy tick): up to 59.4 (template)
  and 78.1 (procedural) food units over the 10-turn horizon for one asset; it exists before failure
  and is the commons relief L9 sees when the works can propose.
- **Granary first.** In procedural worlds 148 work-turns stalled because the region's storage held
  the labour column (`granary_first`); template worlds had none.
- **Timing.** About 9 s per template world and 22 s per procedural world over 200 turns with every
  arm's switches (no separate profiling at a declared scale).

### Verification

Section 9.

## 9. Verification record (2026-11-07, branch `claude/cw-b3-infrastructure`)

Source: the branch's `src` at `d6c27e81` (unchanged at `562bc0f8`); every native step used
`PYTHONPATH=<worktree>/src` and the extension at `~/.venvs/native-a3`, SHA-256
`20e77f9945efa71d597c142e99069337586cc865ddee7a17c6d20948a2c0c1ca`, built from Rust identical to main
8401aa74 (no Rust change in this lane, so `cargo test` was not rerun). Compact evidence under
`/home/user/evidence/b3/` (outside the repository).

| Check | Result |
| --- | --- |
| Focused offline tests | `tests/test_infrastructure_condition.py` 39 passed; with the catalog, manifest, money, ledger, RS2, PL1, PL3, wiring, matrix, A3, B1 and shard tests, all pass |
| Witness chain with layer `cwb3` (last, after `cwa3`) | the 16 witness and pin modules of the playbook: 299 passed, 61 subtests passed |
| Bounded offline lane (`scripts/run_python_oracle_checks.py`, default output dir) | PASS in 337.7 s: 69 chunks, 7,312 passed, 69 skipped, 0 failed; `connected-world-b` 81 passed in 4.8 s of 110 s; commit `562bc0f8` |
| Native pytest (real extension) | 35 passed in 145.5 s: `test_infrastructure_condition_native.py` (3) with the RS2, PL3, closure, PL1, A1 and A3 native modules |
| Feature-off identity against `8abc1acb` (`turn_speed_identity.py`, the 9 standard cases, each side its own tree and extension) | 9 cases, 399 files compared, 0 differences |
| Explicit `--no-infrastructure-condition` against the switch omitted (hybrid_s42 and proc48_hybrid_s42 with `--grain-reserves --grain-storage --workshops --repair-projects --local-budgets --maintenance-obligation`) | 2 cases, 205 files compared, 0 differences |
| `record_only` against the switch omitted (the same two cases and prerequisites) | the bundle and `state.json` differ; with the record and its two manifest keys removed, 0 differences in both (hybrid_s42: 15 assets, 7 failed; proc48: 68 assets, 10 failed recorded) |
| Exact resume, every livelihoods switch with retail everywhere, A3, A1 and B3 (`checkpoint_identity.py`, `hybrid_s42_long`, 200 turns, 19 resume points) | PASS: checkpointing changes nothing; every resume byte-identical; resumes at turns 99, 100, 101 and 144 are inside open works with work delivered that turn (11-13 open works) |
| Native exact resume inside open works (`test_infrastructure_condition_native.py`, procedural 31, checkpoint 37) | history, world state and `state.json` byte-identical |
| Compatibility matrix (`scripts/feature_matrix.py`) | 378 pairs, 0 refused unexpectedly, 0 prerequisite drops accepted; all-enabled hybrid selections accepted (27 switches template, 28 procedural) |
| Viewer | the two new test files 17 passed; full suite 1,601 passed and 2 skipped, 5 tests in 5 unrelated files (AppShell, FeatureOptions, Watershed) timed out at 5 s under a load average near 7 and passed on rerun (4 with `--maxWorkers=2`, 1 alone); `npm run lint` clean; `npm run build` passes |

**Not run:** a desktop and phone browser journey (V8), profiling at a declared scale (V11), the
narration audit (no narration change), any held screen, the 200-seed gate and the procedural
qualification gate.

## 10. Limits and open questions

- **Named crews.** Works use anonymous farm labour only. PL3's named crews (`--recovery-crews`)
  remain granary-only: paying named infrastructure crews would need a treasury-to-agent payment,
  which the payment seam's first slice refuses, and a new ledger channel. Recorded as a missing
  capability for a later slice.
- **PL1 demand.** The woodcutters' need (`timber_supply`) is computed from RS2's projects; the works
  use whatever the store holds after RS2's holds, so PL1 does not yet send expeditions for them.
- **Roads have no relief measure** under L9 (trade range lost is not valued); they are funded in the
  same proposal as irrigation or through a maintenance reservation.
- **A region whose storage works this turn** gives the works nothing (`granary_first`), even when
  the farmers could do both; the split order is declared, not optimized.
- Ports are deferred (no consumer reads the type). The flood seam has no caller until the
  watershed's `flow` mode lands. Constants are declared and uncalibrated; nothing here was run on
  held seeds or through the 200-seed gate.
