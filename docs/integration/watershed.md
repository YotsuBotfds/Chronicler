# Watershed account (B1, `--watershed record_only`)

Status, 2026-11-06: connected-world program, slice S1-A (lane B1). Experimental and **off by
default**. Mode `record_only` is the only mode: a conserved water account runs on the drainage
graph of a procedural world beside the existing water index and **changes nothing** outside its
own record. The later `flow` mode (plan section 5.2) will replace, not stack on, the old water
terms; it is not implemented here. Design source: the program-B contract audit
(`docs/superpowers/audits/connected-world/audit-b-watershed-infrastructure.md`, sections 1, 2,
5-8) and the lead's decisions (`docs/superpowers/roadmaps/connected-world-program.md`, 5.2).

Code: `src/chronicler/watershed.py`, `src/chronicler/watershed_state.py`; viewer
`viewer/src/lib/watershed.ts`, `viewer/src/watershedTypes.ts`,
`viewer/src/components/systems/Watershed.tsx`; tests `tests/test_watershed.py`,
`viewer/src/lib/__tests__/watershed.test.ts`,
`viewer/src/components/systems/__tests__/Watershed.test.tsx`; development calibration
`scripts/watershed_calibration.py`.

## 1. Switch

```sh
chronicler --worldgen procedural --regions 32 --civs 10 --watershed            # record_only
chronicler ... --watershed --watershed-mode record_only                          # the same, explicit
```

- A livelihoods-registry package (`LIVELIHOODS_SWITCHES` entry `watershed`, state
  `WorldState.livelihoods.watershed`); nothing is created, recorded or forwarded without the switch,
  so feature-off output keeps its bytes. `batch_manifest.SIMULATION_ARG_KEYS` lists `watershed` and
  `watershed_mode`, both omitted from the recorded configuration when unset.
- **Every agent mode and every ecology path** (native `AgentSimulator` or `EcologySimulator`, and
  the pure-Python fallback without an extension): the hooks only read the world.
- **Procedural worlds only.** Template worlds have no elevation, so no drainage can be derived:
  `--watershed` on a template world is refused at startup and on a state-file resume with
  "`--watershed requires a procedural world ...`". This is an intentional, documented boundary; the
  program's watershed screens use the procedural stratum.
- **A switch change on resume is refused.** The account opens with a new world (turn 0); asking for
  it on a resumed world (turn > 0) is refused. A world that keeps an account cannot end it
  (`--no-watershed`) or change its mode, on an exact resume (the checkpoint's recorded configuration
  and `livelihoods.livelihoods_resume_conflicts`) or on a state-file resume
  (`watershed.check_request`). Omitting the switch on resume keeps the saved account.
- Feature catalog: `REQUIREMENTS["watershed"] = (_setting("procedural_world"),)`; `watershed_mode`
  is a choice of `watershed`. The setting depends on the requested world, which the catalog's static
  surfaces cannot see, so it is evaluated per surface:
  - **Batch Lab**: Batch Lab passes no `--worldgen`, so `auto` builds a procedural world above 12
    regions. The server's batch check reads the batch config's `regions` (else the batch default, 8);
    the viewer recomputes the setting from the regions it will send
    (`viewer/src/lib/featureWorld.ts`), so a batch of more than 12 regions can enable the watershed.
  - **Live start**: the client's start message chooses the world and the static live surface cannot
    see it. A server started with `--watershed` reports the setting true, so the viewer keeps the
    operator's switch on every live start (it never sends an explicit `false`); a start that asks for
    12 regions or fewer is then refused explicitly by the run ("`--watershed requires a procedural
    world ...`", the lobby reopens with it). A server started without it cannot be asked for it on a
    live start.

## 2. The drainage graph

Built once at enable from saved procedural geography (`world.geography`, `Region.geo`), and kept in
the state (`WatershedGraph`):

- a **coastal** region (`geo.coastal`) on an ocean or sea (any bordering zone of kind `ocean` or
  `sea`) drains to the **sea**; a shore on lakes only drains to a **lake** (closed water: what reaches it
  leaves the account as `to_lake`, never as outflow to the sea). Worldgen can make lakes
  (`geography._sea_zones`, `LAKE_MAX_CELLS`), but none of the 64 development world/size combinations
  checked (procedural 7-303 at 13-150 regions) has one; a constructed lake is tested;
- an **inland** region drains to its lowest land neighbour (`Region.adjacencies` without
  `geography.sea_lanes`) that is strictly lower (`geo.elevation`), ties to the lower index;
- an inland region with no lower land neighbour is a **sink** (a closed basin).

Elevation strictly falls along every edge, so the graph is acyclic and each region has exactly one
destination (`down[i]`: a region index, `-1` sea, `-2` sink or `-3` lake). `order` lists every region after all
regions that drain into it (elevation descending, then index).

Validation at enable (each failure refuses the switch with a message naming the river and step):

- every persisted river step (`world.rivers`, procedural or scenario) must equal the graph's edge;
- the rivers must be well formed: no step and its reverse (a reversed duplicate, in one river or two),
  no region with two downstream targets, no cycle, no unknown region, no step that does not move.
  This checks scenario rivers too (audit B finding 7); `scenario.py` itself is unchanged, so a
  scenario loads as before and is refused only when the watershed is asked for.

On the development worlds (tests, `test_the_drainage_graph_reproduces_every_persisted_river_step`):

| World | Sea | Sinks | Inland edges | River steps reproduced | Longest chain | Most regions upstream | Multi-region basins |
| --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7, 32x10 | 18 | 0 | 14 | 0 of 0 | 2 | 4 | 9 |
| procedural 11 | 18 | 0 | 14 | 2 of 2 | 3 | 5 | 8 |
| procedural 13 | 19 | 0 | 13 | 1 of 1 | 2 | 4 | 9 |
| procedural 17 | 19 | 0 | 13 | 0 of 0 | 2 | 2 | 9 |
| procedural 21 | 19 | 0 | 13 | 0 of 0 | 2 | 2 | 11 |
| procedural 31 | 16 | 1 | 15 | 0 of 0 | 3 | 5 | 8 |
| procedural 302 | 18 | 0 | 14 | 0 of 0 | 2 | 2 | 11 |
| procedural 303 | 18 | 0 | 14 | 1 of 1 | 3 | 4 | 8 |
| procedural 7, 64x16 | 29 | 0 | 35 | 6 of 6 | 5 | 10 | 15 |
| procedural 11, 64x16 | 28 | 0 | 36 | 3 of 3 | 5 | 6 | 16 |

Named rivers are the high-flow subset of this graph; every river-keyed mechanism of the old model
(cascade, river floods, trade and migration bonuses) is untouched.

## 3. The account

Per turn, in Phase 9, deterministic, float64, no randomness. Water units (wu): one region's storage
capacity without forest cover is `STORAGE_BASE` = 1. Regions are processed in `order`, so each unit
of water leaves a region by exactly one path and a confluence sums its tributaries' outflows once
(the structural guard against counting tributaries twice).

```
C    = STORAGE_BASE x (1 + FOREST_RETENTION x cover)                      capacity
X    = (index now - index after the last Phase 9) / (cap - floor) x C     external in (+) or out (-)
P    = PRECIPITATION_BASE x (0.2 + moisture)
         x max(0, 1 - (1 - PHASE_PRECIPITATION[phase]) x exposure x trend)
         x max(0, 1 - SHOCK_PRECIPITATION x harvest shock)  (+ TUNDRA_MELT, tundra, warming)
I    = sum of the outflows of the regions draining here (same turn)
A    = S + P + X_in - X_out + I
E    = min(A, EVAPORATION_BASE x (1 + (PHASE_EVAPORATION[phase] - 1) x exposure x trend)
              x TERRAIN_EVAPORATION[terrain] x (1 + TRANSPIRATION x cover))
W    = min(A - E, IRRIGATION_DEMAND) with an active irrigation work, else 0
S'   = (1 - BASEFLOW) x min(A - E - W, C)
Q    = A - E - W - S'                                                     baseflow + overflow
Q   -> I of the destination | to_sea | to_sink (a closed basin loses it) | to_lake
```

- `exposure` is the region's latitude climate exposure, `trend` the climate trend share and the
  harvest shock the region's regional bad year (`climate.region_harvest_shocks`): the same forcing
  the old index reads, through pure functions (no state, no RNG).
- `X` folds every other writer of the index between two ticks into the account once, as a recorded
  external flow, **attributed by source** (`ExternalFlow`):
  - `coastal_flood`: the coastal flood of `climate.check_disasters` struck this region in Phase 1 of
    this turn. It is recognised from the disaster's own deterministic roll and probability and the
    cooldown it set this turn (cooldowns are decremented before the check, and `emergence` skips a
    region with any cooldown), reading only; at most its nominal gain (`K_FLOOD_WATER_GAIN`) is
    attributed to it;
  - `unattributed`: any other writer (a scenario, a live `set`, an index write in Phase 10 of the
    previous turn) and any remainder above the flood's gain; every external outflow.

  `X_out` is limited to the storage; any remainder is recorded as `external_out_unmet` and never
  taken from elsewhere.
- **Stale baseline.** `X` is measured against the index observed after the previous turn's tick. When
  that baseline is stale (a plan was dropped because a tick never settled, or a turn is missing), the
  frame is flagged `stale_baseline`, every external flow of that turn is unattributed, and
  `stale_baseline_turns` counts it. `record_only` records it; **`flow` mode must refuse or reconcile a
  stale baseline before it may apply the account** (a prerequisite, not done here).
- **Closure checks are construction invariants and routing guards, not a validation of the model.**
  Each region's outflow is defined as the residual of its account (`Q = A - E - W - S'`), so the
  per-region identity `S' - S = P + X_in - X_out + I - E - W - Q` holds by construction and can fail
  only through float pathology. The world-total check
  `sum(S' - S) = sum(P + X_in - X_out - E - W) - to_sea - to_sink - to_lake` and the tributary check
  (each inflow equals the sum of its tributaries' outflows; each outflow goes to exactly one
  destination) guard the routing: water sent to no region, or to a region already processed (a broken
  order), would make them fail. The bounds (`0 <= S' <= C`, `X_out <= S`, every flow non-negative
  and finite) catch bad inputs. The cumulative check against the opening storage catches an
  out-of-band edit of the stored account between turns. All raise before anything is committed
  (relative 1e-9, `math.fsum`). None of them says the forcing, the constants or the attribution of
  `X` is right: that is the calibration question (section 7).
- **Opening** at enable: `S = C x (index - floor)/(cap - floor)`, so the derived index is continuous
  with the old one; the world-generation river bonus (+0.15 on river regions) is inside the opening
  storage, never added again.
- **Derived index**: `floor + (cap - floor) x min(1, S'/C + IRRIGATION_WETTING x W/C)` with the
  terrain's water cap. It is recorded beside `index_observed`, the index the simulation actually used
  after the ecology tick.

### Floods and droughts

- **Flood**: a settled turn whose arrivals `P + I + X_in` exceed the region's channel capacity
  (`CHANNEL_CAPACITY`, x `RIVER_CHANNEL_FACTOR` on a named river region). The record keeps the
  turn, excess, arrivals by source (precipitation, inflow, external), the channel, opening storage
  and capacity, every tributary with the outflow it sent, the mean forest cover of all regions
  upstream and how many are below 0.2.
- **Drought**: a run of at least `DROUGHT_TURNS` settled turns with `S'/C < DROUGHT_FRACTION`. Its
  record keeps the start, declaration and end turns, the lowest fill, and over the run the
  precipitation against the normal precipitation (the forcing deficit), inflow, evaporation, the
  region's own irrigation withdrawal, the withdrawals of every region upstream and the upstream cover.
  Shorter runs are not recorded; the per-region `drought_turns` column shows them.
- Neither has any consequence in `record_only`. The existing river flood
  (`emergence._check_flood`), drought intensification and civ drought hazard are untouched.

### Order, state and resume

- `before_ecology` (immediately before the Phase 9 region sync): compute and check the account from
  the pre-tick world into a transient plan (`WatershedState._plan`, never serialized).
  `after_ecology` (after the ecology tick and its write-back): read the observed index, build the
  flood and drought records, commit storage, `last_index`, spells, the frame and the totals.
- A plan left by a failed tick is dropped at the next planning (`abandoned_plans`); nothing was
  settled, so a turn settles once. `after_ecology` without a plan for this turn raises.
- Persisted: the graph, storage, `last_index`, the opening storage, running drought spells, the last
  settled frame (full precision), cumulative totals and counters (about 11.5 KB of JSON at 32
  regions). Exact checkpoints and state files carry it; no native state changes, so the checkpoint
  schema fingerprint is unchanged.

## 4. Conserved quantities and indices

| Quantity | Kind in `record_only` |
| --- | --- |
| Watershed storage and its flows (precipitation, external in/out, evaporation, withdrawal, transfer, sea, sink) | **conserved**, closed every turn and cumulatively |
| `ecology.water` (the index the simulation uses) | an index, owned and written as before; recorded as `index_observed` |
| `index_derived` | an index derived from storage; **recorded only**, read by nothing |
| Flood excess, drought spells | recorded conditions, no consequence |
| Forest cover, soil, timber stock, infrastructure | read only (cover enters capacity and transpiration) |

## 5. Who owns each effect

| Effect | Owner today | `record_only` (this slice) | `flow` (later, plan 5.2) |
| --- | --- | --- | --- |
| Water climate terms (drought, cooling, temperate recovery, tundra melt, harvest-shock water) | native ecology tick / Python fallback | unchanged; mirrored as forcing in the account | replaced by the account's forcing (native rates set to 0 via `EcologyConfig`) |
| Water index value | ecology tick | unchanged; derived index recorded beside it | derived from storage |
| Deforestation cascade (−0.05 per deforested upstream region) | `river_cascade` | unchanged | replaced by cover-dependent capacity and transpiration on the graph |
| River +0.15 water bonus | world generation | inside the opening storage, once | the same |
| River presence effects (capacity x1.2, fish, trade discount, barge cap, migration bonus, attractor) | world generation, economy, merchant, behavior, spatial | unchanged | unchanged |
| Irrigation water bonus and drought x1.5 | native through `has_irrigation` | unchanged; a recorded withdrawal in the account | replaced by the withdrawal |
| Irrigation arable ceiling, irrigation technique | economy, techniques | unchanged | unchanged (condition scaling is B3) |
| Coastal flood +0.1 water, ports off | `climate.check_disasters` | unchanged; its index change is a recorded external inflow | the same external inflow |
| River flood (water > 0.8) | `emergence._check_flood` | unchanged; the account records its own floods | replaced by the watershed flood |
| Drought intensification, civ drought hazard, disease flares, yields, capacity, satisfaction, mortality stress | existing | unchanged | read the derived index |
| Deaths | demographics, epidemics, famine | unchanged | unchanged: no new mortality authority |

## 6. Declared constants (uncalibrated)

| Constant | Value | Meaning |
| --- | --- | --- |
| `STORAGE_BASE` | 1.0 wu | storage capacity without forest cover |
| `FOREST_RETENTION` | 0.5 | capacity x (1 + 0.5 x cover) |
| `PRECIPITATION_BASE` | 0.1 wu/turn | at (0.2 + moisture) = 1 |
| `PHASE_PRECIPITATION` | temperate 1.0, warming 0.85, drought 0.3, cooling 0.6 | scaled by exposure x trend |
| `SHOCK_PRECIPITATION` | 1.0 | a bad year of depth h cuts precipitation by h |
| `TUNDRA_MELT` | 0.05 wu/turn | tundra, warming phase |
| `EVAPORATION_BASE` | 0.03 wu/turn | potential evapotranspiration |
| `PHASE_EVAPORATION` | temperate 1.0, warming 1.3, drought 1.6, cooling 0.7 | scaled by exposure x trend |
| `TERRAIN_EVAPORATION` | desert 1.6, steppe 1.25, tundra 0.5, others 1.0 | |
| `TRANSPIRATION` | 0.3 | evaporation x (1 + 0.3 x cover) |
| `BASEFLOW` | 0.05 | share of storage released downstream a turn |
| `IRRIGATION_DEMAND` | 0.02 wu/turn | consumptive use with an active irrigation work (service 1.0) |
| `IRRIGATION_WETTING` | 1.0 | the derived index counts applied water W/C |
| `CHANNEL_CAPACITY`, `RIVER_CHANNEL_FACTOR` | 0.25 wu/turn, x2 on a river region | flood threshold |
| `DROUGHT_FRACTION`, `DROUGHT_TURNS` | 0.2, 3 | drought definition |
| `INDEX_FLOOR` | 0.10 | the ecology's water floor |
| `CLOSURE_TOLERANCE` | 1e-9 | relative |

## 7. Development calibration report (development worlds only)

`scripts/watershed_calibration.py` reads bundles of `--watershed` runs and refuses any seed that is not
a procedural development world. Runs: procedural 7, 11, 13 and 31 (32 regions, 10 civs),
`--agents hybrid`, 150 turns (two climate cycles), native extension SHA-256 `101a4cd5…`, source
`0779587`. These describe the declared constants; they tune nothing and are not evidence about any
held or evaluation world.

| World | Group | Regions | Mean index used | Mean derived | Mean abs gap | Median correlation | Phase-cycle amplitude used / derived |
| --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | headwater | 20 | 0.489 | 0.362 | 0.207 | 0.589 | 0.391 / 0.144 |
| procedural 7 | with upstream | 12 | 0.575 | 0.561 | 0.169 | 0.672 | 0.417 / 0.209 |
| procedural 11 | headwater | 21 | 0.597 | 0.420 | 0.249 | 0.562 | 0.402 / 0.208 |
| procedural 11 | with upstream | 11 | 0.504 | 0.572 | 0.189 | 0.617 | 0.395 / 0.228 |
| procedural 13 | headwater | 21 | 0.586 | 0.420 | 0.213 | 0.740 | 0.435 / 0.212 |
| procedural 13 | with upstream | 11 | 0.548 | 0.591 | 0.169 | 0.728 | 0.471 / 0.271 |
| procedural 31 | headwater | 19 | 0.534 | 0.395 | 0.227 | 0.646 | 0.399 / 0.183 |
| procedural 31 | with upstream | 13 | 0.579 | 0.523 | 0.167 | 0.578 | 0.470 / 0.223 |

| World | Floods (regions) | Droughts declared | Drought region-turns | Precipitation | Evaporation | Irrigation | To sea | To sinks | Storage opening → turn 150 | Max abs residual (wu) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | 11 (1) | 24 | 1435 | 311.1 | 151.4 | 39.7 | 139.2 | 0 | 32.9 → 13.8 | 1.5e-15 |
| procedural 11 | 1 (1) | 27 | 964 | 317.0 | 148.4 | 43.8 | 148.9 | 0 | 34.6 → 12.1 | 2.3e-15 |
| procedural 13 | 1 (1) | 29 | 859 | 311.4 | 150.7 | 42.3 | 144.7 | 0 | 35.3 → 10.1 | 1.5e-15 |
| procedural 31 | 28 (1) | 27 | 1232 | 293.7 | 152.8 | 37.7 | 123.9 | 3.6 | 33.2 → 11.2 | 1.7e-15 |

Observations (development only):

- The derived index follows the old index's climate cycle (median per-region correlation 0.56-0.74)
  with about half its phase amplitude (0.14-0.27 against 0.39-0.47): the account smooths the cycle.
- Headwater regions run 0.13-0.18 drier than the old index on average; regions with upstream inflow
  are close in mean (−0.06 to +0.07) and wetter than the old index in drought and cooling, where
  upstream baseflow buffers them.
- The declared constants lose water: storage falls from about 33-35 wu at opening (the old index,
  near its caps at world generation) to 10-14 wu after two cycles, and droughts are frequent
  (24-29 declared per world). A first calibration would raise `PRECIPITATION_BASE` or lower
  `EVAPORATION_BASE`/`BASEFLOW` until a headwater region is stationary over a cycle.
- Floods are rare and concentrated: each world floods in one region (its largest confluence or a
  coastal region whose flood surge, an external inflow, adds to its arrivals).
- Irrigation withdraws 12-14% of precipitation; the upstream/downstream trade-off is visible in the
  tests (an irrigated tributary lowers its outflow and the confluence's inflow).

## 8. Record and viewer

`snapshot.livelihoods.watershed` (schema 1, stage `B1`, mode `record_only`):

- every record: `source_turn` (the completed turn, snapshot turn − 1), `completed_turn`,
  `opened_turn`, `observed`, `cumulative` (flows since opening, the opening storage, the storage now and
  the cumulative residual) and `counters`;
- **once**, in the record of the opening turn (`source_turn == opened_turn`): the static part,
  `units`, `parameters` and the graph (`down`, `sea` −1, `sink` −2, `lake` −3, `river_steps`). Later
  records leave these keys out; readers take them from the run's opening record;
- when observed: the climate `phase`, `stale_baseline`, per-region columns (`storage_open`,
  `precipitation`, `external_in`, `external_out`, `inflow`, `evaporation`, `withdrawal`, `storage`,
  `capacity`, `index_observed`, `index_derived`, `flood_excess`, `drought_turns`), `external` (flows by
  source, non-zero at the record's precision), `floods`, `droughts` and `totals` (flows, the
  external flows by source, the storage open and close and the residual). Outflow is not recorded: it
  is each region's residual by construction, and readers derive it. `droughts` holds the spells
  `declared` this turn and those `ended` this turn in full (with their conditions), and every `open`
  spell compactly (region, start, declaration, turns, lowest fill);
- when not observed: the per-turn fields are `null`, never empty, and `storage` holds the account's
  storage (a settled turn's `regions.storage` is the same list, so it is not repeated).

Values are rounded to 6 decimals; the full-precision frame (outflow and full drought conditions
included) stays in the state. Growth of the encoded bundle (version-6 deltas, after review m7): a
60-turn hybrid 32-region run (procedural 11) +141 KB, **+4.25%** (was +5.52%); a 150-turn agents-off
32-region run (procedural 31) **+5.79%** (the reviewer measured +8.5% before). The static part was
already elided by the bundle's deltas; the savings come from dropping the repeated storage list, the
derived outflow column and the repeated drought conditions.

Viewer (types in `viewer/src/watershedTypes.ts`; `types.ts` is pinned and unchanged):

- `readWatershedRun(history)` finds the run's static part once; `readWatershed(snapshot, regions,
  run)` is strict and keeps five states apart: **disabled** (no snapshot of the run carries the
  record), **absent** (on in the run, missing at this snapshot), **malformed** (with the reason: a null
  record or a non-object livelihoods container, schema, dating, a static part outside the opening
  record or a missing opening record, graph range and cycles, the exact counter, cumulative and total
  key sets, the cumulative and turn closure, outflows routed to the sea, sinks, lakes and downstream
  matching the totals, tributary inflows, external flows by source adding up, flood arithmetic, drought
  dating), **unobserved** (no settled account this turn: unknown, not zero) and **ok** (a zero is a
  recorded zero).
- The Livelihoods tab mounts a **Watershed** panel whenever the run records it: the turn's account,
  external flows by source, a stale-baseline note, each region's destination, storage/capacity, index
  used against index derived, inflow, derived outflow, irrigation, flood excess and dry turns; floods
  with arrivals by source and tributaries; droughts declared and ended with their conditions and the
  open ones compactly; cumulative totals and closure (labelled as a routing check, not a validation);
  counters.
- Region history offers "Water index the simulation used", "Water index the watershed account would
  derive (record only)" and "Watershed storage" when the run records the account, with absent,
  malformed and unobserved turns reading as missing with their reason.
- Batch Lab's feature options recompute `procedural_world` from the regions the batch will send
  (`viewer/src/lib/featureWorld.ts`, `TEMPLATE_REGION_POOL` 12, pinned on the Python side by
  `tests/test_watershed.py`).

## 9. Verification (2026-11-06, extension `101a4cd5…`)

First pass (source `0779587`) and, after the independent review's findings, again on `a33f408`:

- Offline: `tests/test_watershed.py`, 41 cases, in the oracle chunk `connected-world-b` (3.4 s of
  110 s); native shard 0. Bounded offline lane (`scripts/run_python_oracle_checks.py`, `cwb1` layer
  in place): PASS, 64 chunks in 286.8 s, slowest `systems-2` 34.5 s of 110 s (first pass: 241.5 s).
  The witness tests of the playbook (sprint, restoration, scenarios, information, academy,
  household mobility, crisis, food accounting, grain release, public grain shipments, regional
  population, health care, practice observer, native shards, preflight): 509 passed.
- Feature-off identity (`turn_speed_identity.py`, each side its own `git archive` tree and copied
  extension) against `8abc1acb` (also the preceding integrated `main`): 9 cases, 399 files,
  0 differences, on both sources; with an explicit `--no-watershed` on `hybrid_s42` and
  `proc48_hybrid_s42` (first pass): 203 files, 0 differences.
- `record_only` against off, outputs compared after removing only the watershed record:
  - **with every other livelihoods switch on** (review M1: the checkpoint-3 chain, i.e. the sprint
    and sprint-2/3 base, food allocation, workshops, operating wear, repair projects, timber stock,
    household retail at the `paid_work` boundary, timber supply, recovery crews and remittances, plus
    apprenticeship, veteran reintegration, clearing protection, local budgets, maintenance
    obligation, workshop payroll, learning cohorts, commons rules, grain convoys and relocation
    costs): procedural 11, 32x10, hybrid, 80 turns, source `a33f408`: 16 files, 0 differences;
  - alone (first pass): procedural 7, 13, 303 hybrid (100 turns), 11 hybrid (60), 31 agents-off
    native ecology (100) and 21 pure-Python fallback (60): 0 differences in every file.
- Enabled exact resume, `checkpoint_identity.py run --case proc32_hybrid_s11`:
  - **with the same full stack plus `--watershed --watershed-mode=record_only`** (review M1, source
    `a33f408`): PASS, 39 resume points, 0 differences; checkpointing changes nothing (41 files);
  - with the watershed alone (first pass): PASS, 39 resume points; a procedural-11 hybrid resume
    inside the drought phase (turn 50, five open droughts) to turn 80: 16 files, 0 differences.
- Viewer: 1468 tests (148 files), lint and production build; desktop 1440x900 and phone 390x844
  browser check of the panel on procedural 11 (60 turns): 23/23 checks, no console errors, no page
  overflow on the phone.

## 10. Limits and boundaries

| Item | Class | Disposition |
| --- | --- | --- |
| Template worlds have no watershed | intentional boundary | refused at startup and on a state-file resume (tested) |
| A live start cannot be checked against its requested world by the catalog (static surface; `live.py` is pinned) | intentional boundary of the catalog surface | a server started with `--watershed` keeps it on every live start and the run refuses a template start explicitly; without it, a live start cannot ask for it; Batch Lab above 12 regions and the CLI can |
| Constants uncalibrated; storage drifts down over two cycles | evidence gap | development calibration report (section 7); `flow` needs calibration first |
| Floods and droughts have no consequence | intentional (record only) | `flow` (later) applies them through existing authorities |
| Irrigation service is 1.0 for every active work | missing capability | infrastructure condition (B3) scales it |
| The account reads pre-tick terrain for the index cap; a same-turn succession changes the cap only from the next turn | intentional | documented |
| Lake shores | corrected (review m8) | a shore on lakes only drains to the lake (`to_lake`), never to the sea; no development world has a lake (a constructed one is tested) |
| External flows other than the coastal flood are unattributed | evidence gap (record only) | recorded with an explicit `unattributed` remainder; a stale baseline is flagged; `flow` must refuse or reconcile a stale baseline first |
| Closure checks are construction invariants | documented (review m2) | they guard routing and bounds; the model itself is a calibration question |
| A drop of the index larger than storage is recorded as unmet, not taken | intentional | recorded (`external_out_unmet`) |
| Opening on a resumed world, ending or changing mode on resume | refused | tested (exact and state-file resumes) |
