# Watershed account (`--watershed`: B1 `record_only`, B2 `flow`)

Status, 2026-11-06: connected-world program, slices S1-A (lane B1, `record_only`) and lane B2
(`flow`). Experimental and **off by default**. A conserved water account runs on the drainage
graph of a procedural world.

- `record_only` (B1, the default mode) runs beside the existing water index and **changes
  nothing** outside its own record.
- `flow` (B2, section 4) makes the account the owner of the water index. It **replaces, never
  stacks on**, the native water climate terms, the irrigation water bonus and the downstream
  deforestation cascade (switched off once, through one pinned seam), writes the index derived from
  storage as the index the simulation uses, and lets the account's floods act through the existing
  fields. The old river-flood check keeps its draws; its effect is suppressed and recorded as
  superseded. Native ecology only.

The constants were recalibrated for B2 on the procedural development worlds (section 8); `flow`'s
effects are described by a development-only activation report (section 9), not by a screen.
Design source: the program-B contract audit
(`docs/superpowers/audits/connected-world/audit-b-watershed-infrastructure.md`, sections 1, 2,
5-8, 7.1-7.2) and the lead's decisions (`docs/superpowers/roadmaps/connected-world-program.md`,
5.2).

Code: `src/chronicler/watershed.py`, `src/chronicler/watershed_state.py`, the seams
`agent_bridge.configure_ecology_runtime` (pinned; provisional witness layer `cwb2`) and
`emergence._check_flood`; viewer `viewer/src/lib/watershed.ts`, `viewer/src/watershedTypes.ts`,
`viewer/src/components/systems/Watershed.tsx`; tests `tests/test_watershed.py`,
`tests/test_watershed_native.py` (native shard 0), `viewer/src/lib/__tests__/watershed.test.ts`,
`viewer/src/components/systems/__tests__/Watershed.test.tsx`; development tools
`scripts/watershed_calibration.py` (B1 report), `scripts/watershed_replay.py` (B2 calibration) and
`scripts/watershed_activation.py` (B2 activation report).

## 1. Switch

```sh
chronicler --worldgen procedural --regions 32 --civs 10 --watershed            # record_only
chronicler ... --watershed --watershed-mode record_only                          # the same, explicit
chronicler ... --watershed --watershed-mode flow                                 # B2: the account owns the index
```

- A livelihoods-registry package (`LIVELIHOODS_SWITCHES` entry `watershed`, state
  `WorldState.livelihoods.watershed`); nothing is created, recorded or forwarded without the switch,
  so feature-off output keeps its bytes. `batch_manifest.SIMULATION_ARG_KEYS` lists `watershed` and
  `watershed_mode`, both omitted from the recorded configuration when unset (`batch_manifest.py` is
  unchanged by B2).
- `record_only`: **every agent mode and every ecology path** (native `AgentSimulator` or
  `EcologySimulator`, and the pure-Python fallback without an extension): the hooks only read the
  world.
- `flow`: **native ecology only** (`AgentSimulator` with `--agents hybrid|shadow|demographics-only`,
  `EcologySimulator` with `--agents off`). It switches off native terms, which the pure-Python
  fallback cannot do, so it is refused at startup and on a state-file resume when the extension is
  not importable ("`--watershed-mode flow requires the native ecology ...`", `check_request`), and at
  planning if a turn would take the fallback path (`before_ecology`, `RuntimeError`).
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
    see it, so on a live lobby (`--live`) the setting is true and the run checks the world. A start
    that names the switch in its `features` and asks for a template world (12 regions or fewer) is
    refused with the reason ("`--watershed requires a procedural world ...`") and the lobby reopens;
    nothing has started; a saved state (`resume_state`) asking for it is refused at validation
    ("applies to new worlds only"), the lobby open.
  - **A live lobby's own command line may not hold `--watershed`** (`feature_catalog.LOBBY_REFUSED`):
    `--live --watershed` is refused at startup, before the lobby opens, with a message pointing to the
    per-start request. A live start chooses its own world (the server's `--worldgen` and `--regions`
    do not apply to it: verified), so even `--worldgen procedural` cannot promise one, and a held
    switch meeting a template start that names nothing would end the session (`live.py`, pinned,
    re-raises a refusal of an unrequested switch). `--live --resume` of a checkpoint with an account
    opens no lobby and is unaffected. The viewer's `liveStartFeatures` (`viewer/src/lib/featureWorld.ts`)
    still names any world-dependent switch a server holds, for later switches of the same kind.

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
  `stale_baseline_turns` counts it. `record_only` records it; **`flow` refuses it**: it writes the
  index, so an unsettled tick's change would be folded in as if another writer had made it, and
  `before_ecology` raises ("`watershed flow: the baseline index is stale ...`") before anything is
  applied (tested).
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
  `X` is right: that is the calibration question (section 8).
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
- In `flow` a flood acts (section 4) and a drought acts through the index itself: the derived index
  is the index drought intensification, the civ drought hazard, yields and capacity read.

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

## 4. Flow mode (B2)

`--watershed-mode flow` makes the account the owner of the water index (audit B, 7.1-7.2; plan 5.2).
The account itself (section 3: the plan, the constants, the attribution of external flows, the
closure checks) is the same in both modes; `flow` adds what the account does with it.

Per turn, in Phase 9:

1. `before_ecology` computes and checks the plan from the pre-tick world, as in `record_only`.
2. `_apply_flow` writes each region's derived index into `ecology.water` and lets each of this
   turn's floods act (below), **before the Phase 9 region sync**, so the native tick sees both.
3. The native tick runs with the replaced terms switched off and leaves the index as written (its
   clamp is a no-op: the derived index lies between the floor and the terrain cap). Its write-back
   rounds the index to 4 decimals (f32), so the index observed after the tick equals the derived
   one within 5e-5; verified in both native paths with irrigated regions in play
   (`tests/test_watershed_native.py`), while in `record_only` the old terms move the index by more
   than 0.01 on their own.
4. `after_ecology` records and commits as in `record_only`. The next turn's external flows are
   measured from the observed (rounded) index, so the rounding never enters storage.

**Replaced, never stacked: switched off exactly once.** `watershed.native_overrides(world)` returns
`FLOW_REPLACED_TERMS` and a zero harvest-shock water loss in `flow`, and `({}, None)` otherwise, so
without `flow` the configuration is exactly as before. Its one reader is the pinned seam
`agent_bridge.configure_ecology_runtime` (provisional witness layer `cwb2`, over `cwc1`), which
updates the native `EcologyConfig` once and passes the climate config's water loss:

| Native term | Field | `flow` value | What replaces it in the account |
| --- | --- | --- | --- |
| Drought-phase water decline | `water_drought` | 0 | drought-phase precipitation and evaporation |
| Temperate recovery | `water_recovery` | 0 | precipitation |
| Cooling-phase loss | `cooling_water_loss` | 0 | cooling-phase precipitation and evaporation |
| Tundra melt in warming | `warming_tundra_water_gain` | 0 | `TUNDRA_MELT` in precipitation |
| Irrigation water bonus | `irrigation_water_bonus` | 0 | the withdrawal `W`, taken from storage and counted as wetting in the derived index |
| Irrigation drought multiplier (x1.5) | `irrigation_drought_mult` | 1.0 | nothing: the decline it multiplied is gone |
| Downstream deforestation cascade (−0.05 per deforested upstream region) | `deforestation_water_loss` | 0 | cover-dependent capacity and transpiration on the graph |
| Harvest-shock water loss | `set_climate_config` water loss | 0.0 | `SHOCK_PRECIPITATION` (the crops keep their shock) |

These are every term of the native tick that writes the index (`chronicler-agents/src/ecology.rs`);
no Rust changed. Tests show the replacement happens once and nothing else moves: through the real
seam with a recording simulator, each configuration is set once; without `flow` (off or
`record_only`) it is identical to the feature-off one; with `flow` exactly the fields above differ,
the trend share the crops read is kept and the shock water loss is 0. With the real extension, the
observed index equals the derived one in every region over 30 turns, irrigated regions included, so
no bonus or cascade acted (native test above). The replaced terms' own state is untouched: a world
before and after planning differs only in the water index and, in flooded regions, the three flood
fields; irrigation works, rivers and the river topology are as they were.

**Upstream withdrawal reduces downstream inflow** on the graph: an irrigated tributary sends its
withdrawal nowhere, so the confluence's inflow falls by the same amount (tested offline; in `flow`
that lower inflow is the downstream region's index).

**Floods act, through the old river flood's own effects** (deterministic, no RNG; `Parameters`
`flood_*`). For a region with flood excess `e > 0` this turn:

```
days                       = 2 if e >= FLOOD_LONG_EXCESS (0.1 wu) else 1     the old flood drew 1-2
disaster_cooldowns["flood"] = max(days + 1, the cooldown it has)              never shortened
capacity_modifier           = min(current, FLOOD_CAPACITY_MODIFIER 0.85)       never raises a lower one
soil                        = max(soil, min(terrain soil cap, soil + FLOOD_SILT 0.15))
```

The cooldown has one turn more than the old flood's because it is set in Phase 9, after that turn's
Phase 1 decrement, so it covers this turn's tick and the next `days` turns; the existing rule
restores the capacity modifier to 1.0 when the region has no cooldown left (`simulation.py`), and the
cooldown skips the region's coastal flood and emergence checks while it lasts, as the old flood's
did. Each flood records what it did (`consequence`: capacity modifier, cooldown, soil before and
after) and `flood_consequences` counts it, so every consequence is traceable to the recorded
condition (excess, arrivals by source, tributaries, upstream cover). A drought acts through the index
itself: the derived index is what drought intensification, the civ drought hazard, yields and
capacity read.

**The old river flood is superseded, its draws kept.** `emergence._check_flood` runs unchanged up to
and including its draws on the shared environment stream (`rng.random()` against the flood
probability, `rng.randint(1, 2)` for the duration). In `flow`, `watershed.supersede_river_flood`
records it (`SupersededFlood`: turn, region, duration) and the check returns the `SUPERSEDED`
sentinel: no cooldown, capacity modifier, silt or event, but `check_environmental_events` ends the
region's checks as for a fired check, so control flow and every later draw of that turn are as if the
flood had acted (tested with a counting RNG). The pending records settle into the next frame's
`superseded` list and the `superseded_river_floods` counter. Later turns can differ (no cooldown was
set), as anything `flow` changes can.

**Refusals and resume.** `flow` requires the native ecology (section 1); a stale baseline is refused
(section 3). The native `EcologyConfig` is checkpointed with the run, so a mode or switch change on
resume is refused (exact resume: the recorded configuration and
`livelihoods.livelihoods_resume_conflicts`; state file: `check_request`), and omitting the switch
keeps the saved mode. A `flow` run resumes exactly (section 11). B1 checkpoints and state files load
(the new fields default empty).

**What `flow` does not do.** No new mortality authority, no new randomness, no change to river
presence effects, the irrigation arable ceiling or the coastal flood; template worlds and the
pure-Python fallback are refused, not approximated.

## 5. Conserved quantities and indices

| Quantity | `record_only` | `flow` |
| --- | --- | --- |
| Watershed storage and its flows (precipitation, external in/out, evaporation, withdrawal, transfer, sea, sink) | **conserved**, closed every turn and cumulatively | the same |
| `ecology.water` (the index the simulation uses) | owned and written as before; recorded as `index_observed` | written by the account (the derived index) before the tick; recorded as `index_observed` |
| `index_derived` | derived from storage; **recorded only**, read by nothing | the index the simulation uses |
| Flood excess, drought spells | recorded conditions, no consequence | a flood acts (section 4), a drought through the index; both recorded |
| Forest cover, soil, timber stock, infrastructure | read only (cover enters capacity and transpiration) | read only, except a flood's silt on soil |

## 6. Who owns each effect

| Effect | Owner without the account | `record_only` (B1) | `flow` (B2, implemented) |
| --- | --- | --- | --- |
| Water climate terms (drought, cooling, temperate recovery, tundra melt, harvest-shock water) | native ecology tick / Python fallback | unchanged; mirrored as forcing in the account | **replaced** by the account's forcing (native rates 0 via `EcologyConfig`, harvest-shock water 0 via the climate config) |
| Water index value | ecology tick | unchanged; derived index recorded beside it | **the derived index**, written before the tick, left by it |
| Deforestation cascade (−0.05 per deforested upstream region) | native `deforestation_water_loss` | unchanged | **replaced** by cover-dependent capacity and transpiration on the graph |
| River +0.15 water bonus | world generation | inside the opening storage, once | the same |
| River presence effects (capacity x1.2, fish, trade discount, barge cap, migration bonus, attractor) | world generation, economy, merchant, behavior, spatial | unchanged | unchanged |
| Irrigation water bonus and drought x1.5 | native through `has_irrigation` | unchanged; a recorded withdrawal in the account | **replaced** by the withdrawal (bonus 0, multiplier 1.0) |
| Irrigation arable ceiling, irrigation technique | economy, techniques | unchanged | unchanged (condition scaling is B3) |
| Coastal flood +0.1 water, ports off | `climate.check_disasters` | unchanged; its index change is a recorded external inflow | the same external inflow, now into the index's storage |
| River flood (water > 0.8, spring) | `emergence._check_flood` | unchanged; the account records its own floods | **superseded**: draws kept, effect suppressed and recorded; the account's floods act with the same effects |
| Drought intensification, civ drought hazard, disease flares, yields, capacity, satisfaction, mortality stress | existing | unchanged | unchanged code, reading the derived index |
| Deaths | demographics, epidemics, famine | unchanged | unchanged: no new mortality authority |

## 7. Declared constants

`watershed.PARAMETERS` holds the constants in force (calibrated for B2, section 8) and
`B1_PARAMETERS` the B1 declared constants, kept for comparison. Both modes use `PARAMETERS`; each
record carries them (`parameters`).

| Constant | B1 (declared) | In force (calibrated) | Meaning |
| --- | --- | --- | --- |
| `STORAGE_BASE` | 1.0 wu | 1.0 wu | storage capacity without forest cover |
| `FOREST_RETENTION` | 0.5 | **0.25** | capacity x (1 + retention x cover) |
| `PRECIPITATION_BASE` | 0.1 wu/turn | **0.13** | at (0.2 + moisture) = 1 |
| `PHASE_PRECIPITATION` | temperate 1.0, warming 0.85, drought 0.3, cooling 0.6 | **temperate 1.0, warming 1.2, drought −0.9, cooling −0.5** | factor `max(0, 1 - (1 - f) x exposure x trend)` |
| `SHOCK_PRECIPITATION` | 1.0 | **1.25** | a bad year of depth h cuts precipitation by 1.25 h |
| `TUNDRA_MELT` | 0.05 wu/turn | 0.05 | tundra, warming phase |
| `EVAPORATION_BASE` | 0.03 wu/turn | **0.02** | potential evapotranspiration |
| `PHASE_EVAPORATION` | temperate 1.0, warming 1.3, drought 1.6, cooling 0.7 | **temperate 1.0, warming 1.05, drought 2.8, cooling 1.35** | scaled by exposure x trend |
| `TERRAIN_EVAPORATION` | desert 1.6, steppe 1.25, tundra 0.5, others 1.0 | the same | |
| `TRANSPIRATION` | 0.3 | 0.3 | evaporation x (1 + 0.3 x cover) |
| `BASEFLOW` | 0.05 | **0.009** | share of storage released downstream a turn |
| `IRRIGATION_DEMAND` | 0.02 wu/turn | 0.02 | consumptive use with an active irrigation work (service 1.0) |
| `IRRIGATION_WETTING` | 1.0 | 1.0 | the derived index counts applied water W/C |
| `CHANNEL_CAPACITY`, `RIVER_CHANNEL_FACTOR` | 0.25 wu/turn, x2 on a river region | **0.35**, x2 | flood threshold |
| `DROUGHT_FRACTION`, `DROUGHT_TURNS` | 0.2, 3 | the same | drought definition |
| `FLOOD_CAPACITY_MODIFIER`, `FLOOD_SILT`, `FLOOD_LONG_EXCESS` | (none) | 0.85, 0.15, 0.1 wu | `flow` flood effects (the old river flood's modifier and silt) |
| `INDEX_FLOOR` | 0.10 | 0.10 | the ecology's water floor |
| `CLOSURE_TOLERANCE` | 1e-9 | 1e-9 | relative |

## 8. Calibration (B2, development worlds only)

**Method.** In `record_only` the account changes nothing, so the index the simulation uses and every
input the account reads are the same whatever its constants. `scripts/watershed_replay.py capture`
ran the procedural development worlds 7, 11, 13, 17, 21, 31, 302 and 303 once (32 regions, 10 civs,
`--agents hybrid`, 200 turns: two and a half climate cycles of 75 turns) and saved each turn's
inputs (`watershed.region_inputs`) and observed index; `replay` runs the pure `account_step` on them
under other constants. A replay of a capture equals an actual run with the same constants bit for
bit (checked). The tool refuses any other seed; no held or evaluation world was used. Metrics
(the first cycle, a spin-up from the world-generation index, is left out of all but drift):

- **drift**: the relative change of the world's storage between the same climate phases one cycle
  apart after the first cycle (turns 150-199 against 75-124); the observed index's own drift over
  the same windows is reported beside it;
- **level**: mean (derived − observed) index, all regions, headwater regions and regions with
  upstream inflow;
- **amplitude**: the derived index's climate-phase amplitude over the observed index's;
- **correlation**: the median per-region correlation of the two series;
- **droughts**: the share of region-turns in a drought, against the same rule (fill below 0.2 for 3
  turns) applied to the observed index's fill;
- **floods**: flood region-turns per world.

`search` (coordinate descent over a grid) and `search --refine` (a deterministic local search within
physically ordered ranges: warming evaporates at least as much as temperate, cooling no more than
1.5x, forests keep capacity and transpiration effects) minimised a declared score (stationarity
first, then level, amplitude and drought share); the result was rounded. Flood frequency is not in
the score: `CHANNEL_CAPACITY` was then chosen so that account floods are about as frequent as the
coastal floods of the same worlds (24.0 per world over 200 turns): a sweep gave 51.1 flood
region-turns per world at 0.30, **24.4 at 0.35** and 5.5 at 0.45.

| Pooled over 8 worlds | B1 constants | Calibrated |
| --- | --- | --- |
| Storage drift after the first cycle (observed index: +9.0%) | −15.5% (worst world 30.7%) | **−3.1%** (worst world 11.3%) |
| Level, derived − observed: all / headwater / with upstream | −0.193 / −0.248 / −0.098 | **+0.004 / −0.021 / +0.048** |
| Phase amplitude ratio | 0.29 | **0.99** |
| Median per-region correlation | 0.55 | **0.72** |
| Drought share (old index, same rule: 0.107) | 0.324 | **0.128** |
| Flood region-turns per world | 11.4 | **24.4** |

| World | Drift (observed) | Level | Amplitude | Correlation | Drought share (old rule) | Floods | Storage opening → turn 200 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | +11.3% (+34.0%) | +0.005 | 0.95 | 0.67 | 0.266 (0.198) | 33 | 32.9 → 12.7 |
| procedural 11 | −7.7% (+0.5%) | +0.038 | 0.99 | 0.74 | 0.086 (0.105) | 1 | 34.6 → 26.6 |
| procedural 13 | −4.7% (+2.1%) | +0.009 | 0.96 | 0.80 | 0.110 (0.118) | 1 | 35.3 → 25.8 |
| procedural 17 | −5.9% (+4.0%) | −0.049 | 1.06 | 0.69 | 0.084 (0.023) | 3 | 34.2 → 23.5 |
| procedural 21 | −3.3% (+4.5%) | +0.029 | 0.90 | 0.69 | 0.103 (0.111) | 44 | 34.5 → 26.6 |
| procedural 31 | −6.5% (+13.7%) | +0.030 | 0.90 | 0.65 | 0.104 (0.105) | 95 | 33.2 → 24.6 |
| procedural 302 | −11.2% (+1.1%) | −0.043 | 0.95 | 0.79 | 0.173 (0.106) | 1 | 32.4 → 22.5 |
| procedural 303 | +3.5% (+12.0%) | +0.012 | 1.21 | 0.74 | 0.099 (0.094) | 17 | 34.3 → 26.6 |

Reading (development only):

- Storage is close to stationary after the first cycle (pooled −3.1%; the observed index itself
  moves +9% over the same windows); the first cycle's fall from the opening (about 33-35 wu, the
  world-generation index near its caps) to 22-27 wu is spin-up. Procedural 7 is the outlier (a dry
  world: storage 12.7 wu, drought share 0.27 against 0.20).
- The derived index tracks the old index's level (within 0.05 in every world and group) and its
  seasonal amplitude (0.90-1.21), where B1's constants smoothed the cycle to 0.29 and ran 0.19 drier.
- Drought frequency is plausible (0.128 against 0.107 by the same rule in the old index); floods
  are concentrated: in `flow` runs each flooding world floods in one or two coastal confluences
  (regions draining to the sea with two tributaries), and four of eight worlds flood at most three
  times in 200 turns.
- **Caveats.** The phase factors are fitted to reproduce the old index's cycle, not physical rates:
  drought −0.9 and cooling −0.5 make precipitation fall to zero at high exposure, and warming 1.2 sits
  at the top of its search range. Fitted on the same eight worlds the activation report uses; no
  held-out check exists yet. The B1 report below is kept for comparison.

### B1 report (declared constants, superseded)

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

## 9. Development activation report (development-only)

**Development-only evidence, not a screen and not an effect estimate.** `scripts/watershed_activation.py
FLOW_DIR:RECORD_DIR ...` compares, per procedural development world, a `flow` run with a
`record_only` run of the same seed: 32 regions, 10 civs, `--agents hybrid`, 200 turns, source
`c25a4113`, native extension `101a4cd5…`. `record_only` changes nothing (section 11), so it is the
world without the account. One run per world: a trajectory diverges chaotically from the first turn
the index differs, so per-world differences in food, capacity and population include that
divergence. It refuses any other seed; no held screen was run (CW3 is preregistered after review).

Means over the 200 snapshots, `flow` / `record_only` (capacity and population: the final state; the
water factor is the capacity term `min(1, water / 0.5)`; food is the mean sufficiency and the share of
region-turns below 1):

| World | Index, all | Headwater | With upstream | Water factor | Food sufficiency | Shortfall share | Effective capacity, end | Population, end | Famine events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | 0.522 / 0.508 | 0.460 / 0.480 | 0.626 / 0.556 | 0.776 / 0.786 | 1.11 / 1.11 | 0.463 / 0.475 | 698 / 1002 | 414 / 414 | 135 / 130 |
| procedural 11 | 0.632 / 0.586 | 0.635 / 0.625 | 0.626 / 0.511 | 0.910 / 0.849 | 1.44 / 1.33 | 0.289 / 0.351 | 1170 / 961 | 503 / 677 | 36 / 60 |
| procedural 13 | 0.619 / 0.595 | 0.607 / 0.605 | 0.641 / 0.574 | 0.889 / 0.857 | 1.30 / 1.33 | 0.367 / 0.351 | 1373 / 1195 | 854 / 606 | 121 / 94 |
| procedural 17 | 0.630 / 0.636 | 0.611 / 0.638 | 0.667 / 0.631 | 0.905 / 0.916 | 1.24 / 1.21 | 0.383 / 0.409 | 1028 / 970 | 660 / 597 | 97 / 98 |
| procedural 21 | 0.632 / 0.606 | 0.607 / 0.589 | 0.667 / 0.631 | 0.890 / 0.867 | 1.13 / 1.09 | 0.472 / 0.475 | 1157 / 1157 | 423 / 487 | 104 / 132 |
| procedural 31 | 0.627 / 0.584 | 0.619 / 0.565 | 0.638 / 0.612 | 0.893 / 0.856 | 1.10 / 1.20 | 0.475 / 0.415 | 1130 / 1041 | 624 / 732 | 114 / 112 |
| procedural 302 | 0.590 / 0.607 | 0.541 / 0.577 | 0.653 / 0.645 | 0.843 / 0.868 | 1.11 / 1.18 | 0.459 / 0.431 | 1056 / 1075 | 517 / 464 | 119 / 101 |
| procedural 303 | 0.645 / 0.604 | 0.633 / 0.622 | 0.666 / 0.569 | 0.907 / 0.863 | 1.03 / 0.94 | 0.544 / 0.614 | 1021 / 938 | 509 / 367 | 132 / 146 |

| World | Droughts declared (flow / record-only account) | Floods that acted (flow) | Superseded river floods (flow) | River floods (record only) | Coastal floods (flow / record only) | Index with / without upstream irrigation (flow) |
| --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | 59 / 60 | 31 | 0 | 0 | 4 / 4 | 0.639 / 0.606 |
| procedural 11 | 30 / 29 | 0 | 0 | 0 | 22 / 22 | 0.601 / 0.688 |
| procedural 13 | 33 / 32 | 0 | 6 | 1 | 22 / 22 | 0.624 / 0.681 |
| procedural 17 | 28 / 27 | 0 | 0 | 0 | 32 / 32 | 0.708 / 0.636 |
| procedural 21 | 30 / 26 | 44 | 0 | 0 | 25 / 25 | 0.682 / 0.650 |
| procedural 31 | 29 / 32 | 94 | 0 | 0 | 36 / 36 | 0.648 / 0.627 |
| procedural 302 | 41 / 40 | 0 | 0 | 0 | 34 / 34 | 0.665 / 0.629 |
| procedural 303 | 25 / 27 | 15 | 12 | 1 | 17 / 17 | 0.652 / 0.691 |

Observations (development only):

- **Water.** Regions with upstream inflow are wetter under `flow` in all eight worlds (+0.01 to
  +0.12): the account passes baseflow downstream, which the old index had no term for (it only had
  the cascade's loss). Headwater regions move both ways (−0.04 to +0.05). The world mean is higher in
  six of eight worlds; the water factor of capacity is higher in five (+0.02 to +0.06) and lower in
  three (−0.01 to −0.03). Soil is unchanged within 0.005 (silt is local to floods).
- **Food and carrying capacity: no consistent direction.** Mean sufficiency is higher in five worlds
  and lower in three; the shortfall share follows; final effective capacity is higher in five, equal
  in one, and lower in two (procedural 7: 698 against 1002, a dry world whose headwaters run drier and
  whose one flooding region keeps the 0.85 modifier); final population and famine counts move both
  ways. Eight single runs cannot separate these from trajectory divergence.
- **Droughts** are as frequent as the record-only account finds in the world without it (25-59
  against 26-60 declared per world), now acting through the index.
- **Floods act where the account floods.** 15-94 consequences in four worlds, each in one or two
  coastal confluences (a region draining to the sea with two tributaries, not a named river);
  none in the other four. Every consequence is recorded with its flood's conditions.
- **Superseded river floods.** The old check, reading the derived index, draws a river flood more
  often (6 and 12 in procedural 13 and 303, against 1 each without the account): spring storage on
  river regions sits above 0.8 more often. All were superseded; none acted. Coastal floods are
  identical in both modes.
- **Downstream.** The last column compares different regions (those whose upstream irrigates
  against those whose upstream does not), so it is confounded by where irrigation is built and is
  mixed (lower in three worlds). The controlled evidence that upstream withdrawal reduces downstream
  inflow is the offline test (section 4).

## 10. Record and viewer

`snapshot.livelihoods.watershed` (schema 1; stage `B1` with mode `record_only`, stage `B2` with mode
`flow`; a record_only record keeps exactly the B1 shape):

- every record: `source_turn` (the completed turn, snapshot turn − 1), `completed_turn`,
  `opened_turn`, `observed`, `cumulative` (flows since opening, the opening storage, the storage now and
  the cumulative residual) and `counters`;
- the static part, `units`, `parameters` and the graph (`down`, `sea` −1, `sink` −2, `lake` −3,
  `river_steps`), in every record, so any segment of a history reads on its own (a state-file resume
  or a fork begins after the opening turn); the bundle's deltas write it once;
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
- `flow` only: each flood's `consequence` (`capacity_modifier`, `cooldown`, `soil_before`,
  `soil_after`), the record's `superseded` list (this turn's superseded river floods: `turn`,
  `region`, `duration`; `null` when unobserved) and the counters `flood_consequences` and
  `superseded_river_floods`. `regions.index_observed` equals `index_derived` within the native
  rounding.

Values are rounded to 6 decimals; the full-precision frame (outflow and full drought conditions
included) stays in the state. Growth of the encoded bundle (version-6 deltas, after review m7): a
60-turn hybrid 32-region run (procedural 11) +141 KB, **+4.25%** (was +5.52%); a 150-turn agents-off
32-region run (procedural 31) **+5.79%** (the reviewer measured +8.5% before). The static part costs
nothing in the encoded bundle (its deltas elide unchanged values), so it stays in every record; the
savings come from dropping the repeated storage list, the derived outflow column and the repeated
drought conditions.

Viewer (types in `viewer/src/watershedTypes.ts`; `types.ts` is pinned and unchanged):

- `readWatershed(snapshot, regions, run)` is strict and keeps five states apart (both modes; a
  record mixing them, a stage that does not match its mode, a flow record without its superseded
  list or a flood without its consequence, a record-only record with either, or a flow index used
  that differs from the derived one by more than the native rounding (5e-5) is malformed): **disabled** (no
  snapshot of the run carries the record, `readWatershedRun`), **absent** (on in the run, missing at
  this snapshot), **malformed** (with the reason: a null record or a non-object livelihoods container,
  schema, dating, the record's graph (range, cycles) and parameters, the exact counter, cumulative and total
  key sets, the cumulative and turn closure, outflows routed to the sea, sinks, lakes and downstream
  matching the totals, tributary inflows, external flows by source adding up, flood arithmetic, drought
  dating), **unobserved** (no settled account this turn: unknown, not zero) and **ok** (a zero is a
  recorded zero).
- Its identities allow for the record's rounding exactly: the account closes in Python to relative
  1e-9 (`CLOSURE_TOLERANCE`), and each recorded value carries at most 5e-7 of rounding
  (`HALF_DIGIT`), so a check over *n* recorded values allows `n x 5e-7` plus the closure tolerance of
  its magnitude (a derived outflow combines 8 values; a routed total over *k* regions 8k + 1). This
  is a bound by construction, not a margin. On whole development histories the worst use of an
  allowance was 0.44 (procedural 11, 60 turns), 0.22 (its resumed and forked segments) and 0.67
  (procedural 13, 150 regions, 200 turns; all 200 snapshots read ok).
- The Livelihoods tab mounts a **Watershed** panel whenever the run records it: the turn's account,
  external flows by source, a stale-baseline note, each region's destination, storage/capacity, index
  used against index derived, inflow, derived outflow, irrigation, flood excess and dry turns; floods
  with arrivals by source and tributaries; droughts declared and ended with their conditions and the
  open ones compactly; cumulative totals and closure (labelled as a routing check, not a validation);
  counters.
- In `flow` the panel says that the derived index is the index the simulation used and which terms
  were switched off, adds a "What it did" column to the floods (capacity modifier, cooldown, soil
  before → after) and a "Superseded river floods" table (region, duration), and shows the flow
  counters.
- Region history offers "Water index the simulation used", the derived index and "Watershed storage"
  when the run records the account, labelled by the run's mode (`watershedRunMode`): "Water index
  the watershed account would derive (record only)" or "... derived (flow: the index used)", with a
  matching explanation; absent, malformed and unobserved turns read as missing with their reason.
- Batch Lab's feature options recompute `procedural_world` from the regions the batch will send
  (`viewer/src/lib/featureWorld.ts`, `TEMPLATE_REGION_POOL` 12, pinned on the Python side by
  `tests/test_watershed.py`).

## 11. Verification (2026-11-06, extension `101a4cd5…`)

### B2 (`flow`, recalibrated constants; source `c25a4113` and this documentation commit)

Native runs used the shared extension (SHA-256 `101a4cd5…`, no Rust change) with
`PYTHONPATH` set to this worktree's `src`, the source identity checked before each run.

- Offline: `tests/test_watershed.py`, 53 cases (41 in B1), in the oracle chunk `connected-world-b`
  (3.4 s of 110 s). Bounded offline lane with the `cwb2` layer in place: PASS, 66 chunks in
  259.9 s, slowest `systems-2` 33.7 s of 110 s. Witness tests of the playbook after merging `main`
  (`8286804c`) and building `cwb2` over `cwc1`: 509 passed.
- Native: `tests/test_watershed_native.py` (shard 0; the manifest lists 408 modules), 3 passed: in
  `--agents hybrid` and `--agents off` the observed index equals the derived one within the native
  rounding over 30 turns with irrigated regions in play, while `record_only` shows the old terms
  moving it by more than 0.01; a `flow` run resumes exactly from a checkpoint.
- Feature-off identity (`turn_speed_identity.py`, each side its own `git archive` tree and copied
  extension) against `8abc1acb`: 9 cases, 399 files, 0 differences.
- `record_only` unchanged: against off (procedural 11 and 31, hybrid, 200 turns), and against
  `main`'s B1 `record_only` (the old constants), outputs compared after removing only the watershed
  record: 16 files each, 0 differences.
- `flow` exact resume, `checkpoint_identity.py run --case proc32_hybrid_s11` with
  `--watershed --watershed-mode=flow`: PASS, 39 resume points, 0 differences; checkpointing changes
  nothing (40 files). A procedural-303 hybrid resume inside a flood spell (checkpoint at turn 33) to
  turn 60: 16 files, 0 differences.
- Calibration replay: a replay of the captured inputs equals an actual run with the same constants
  bit for bit.
- Viewer: 1560 tests passed, 2 skipped (153 files), lint and production build; desktop 1440x900 and
  phone 390x844 browser check of a procedural-303 `flow` run (200 turns): the panel at snapshots 1
  (a superseded river flood), 31 (a flood with what it did) and 200, and the region history of the
  derived index labelled for `flow`: 47/47 checks, no console errors, no page overflow on the phone.

### B1 (`record_only`, declared constants)

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

## 12. Limits and boundaries

| Item | Class | Disposition |
| --- | --- | --- |
| Template worlds have no watershed | intentional boundary | refused at startup and on a state-file resume (tested) |
| A live start cannot be checked against its requested world by the catalog (static surface; `live.py` is pinned) | intentional boundary of the catalog surface | on a live lobby the run checks it: a start naming the switch on a template world is refused and the lobby reopens; a lobby whose command line holds `--watershed` is refused at startup (tested) |
| Constants fitted on the eight development worlds to the old index's cycle (B1's drifted down) | evidence gap | calibration report (section 8): the phase factors are fitted, not physical rates (drought and cooling precipitation can reach zero; warming 1.2 at its range's top); no held-out check yet; the activation report uses the same worlds |
| `flow`'s effects on food, carrying capacity and population | evidence gap | development activation report (section 9): no consistent direction over eight single runs; CW3, preregistered after review, is the test |
| `record_only` floods and droughts have no consequence | intentional (record only) | `flow` applies them through the existing fields and the index (section 4) |
| `flow` requires the native ecology | intentional boundary | the pure-Python fallback cannot switch native terms off: refused at startup, on a state-file resume and at planning (tested) |
| `flow` floods act in Phase 9, a turn after the old Phase 1 river flood would | intentional | the cooldown is one turn longer so it covers the same turns (section 4) |
| The native write-back rounds the index to 4 decimals | intentional (native, unchanged) | observed within 5e-5 of the derived index; never enters storage (the next external flow is measured from the observed index) |
| A superseded river flood sets no cooldown | intentional | its draws and that turn's control flow are kept; the region's checks run in later turns, as any `flow` change can alter them |
| `agent_bridge.configure_ecology_runtime` is pinned | reviewed provisional witness layer `cwb2` | the one seam, over `cwc1`; consolidated by the lead at merge |
| Irrigation service is 1.0 for every active work | missing capability | infrastructure condition (B3) scales it |
| The account reads pre-tick terrain for the index cap; a same-turn succession changes the cap only from the next turn | intentional | documented |
| Lake shores | corrected (review m8) | a shore on lakes only drains to the lake (`to_lake`), never to the sea; no development world has a lake (a constructed one is tested) |
| External flows other than the coastal flood are unattributed | evidence gap | recorded with an explicit `unattributed` remainder; a stale baseline is flagged in `record_only` and refused in `flow` (tested) |
| Closure checks are construction invariants | documented (review m2) | they guard routing and bounds; the model itself is a calibration question |
| A drop of the index larger than storage is recorded as unmet, not taken | intentional | recorded (`external_out_unmet`) |
| Opening on a resumed world, ending or changing mode on resume | refused | tested (exact and state-file resumes); in `flow` the native config is checkpointed with the run |
