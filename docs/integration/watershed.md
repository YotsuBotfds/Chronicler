# Watershed account (`--watershed`: B1 `record_only`, B2 `flow`)

Status, 2026-11-06: connected-world program, slices S1-A (lane B1, `record_only`) and lane B2
(`flow`). Experimental and **off by default**. A conserved water account runs on the drainage
graph of a procedural world.

- `record_only` (B1, the default mode) runs beside the existing water index and **changes
  nothing** outside its own record.
- `flow` (B2, section 4) makes the account the owner of the water index. It **replaces, never
  stacks on**, the native water climate terms, the irrigation water bonus and the downstream
  deforestation cascade (switched off once, through one pinned seam), writes the index derived from
  storage as the index the simulation uses, and lets each flood event act once, at its onset, through the existing
  fields. The old river-flood check keeps its draws; its effect is suppressed and recorded as
  superseded. Native ecology only.

The constants were refit after review (three fitted, the rest fixed with stated reasons; leave-two-out
cross-validated on the procedural development worlds, with a 64x16 transfer check; section 8), and the
remaining mismatch with the old index is stated there. `flow`'s effects are described by a
development-only activation report (section 9), not by a screen.
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
- `--watershed-mode` without `--watershed` on a world without an account is refused
  ("`--watershed-mode flow requires --watershed ...`"), so a run cannot look like a `flow` run that
  did nothing (review n1). On a resumed world with an account, the mode alone is checked against it.
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

- **Flood event** (B2): it starts on a settled turn whose arrivals `P + I` exceed the region's
  channel capacity after a settled turn at or below it, while no event is open there; the opening
  turn (storage opens from the world-generation index, often near capacity) starts none. It stays
  open until arrivals return to the region's **normal arrivals**: its own normal precipitation and
  seasonal melt plus the normal net outflow of every region upstream (their normal precipitation and
  melt less potential evaporation at phase factor 1 and the irrigation demand), from the same
  declared quantities, with no constant of its own (re-check minor 1: a fixed 0.75 of the channel lay
  below normal flow, 0.74-0.94 of the channel, so events stayed open until the drought phase and a
  second exceedance inside one got no consequence). An onset always crosses the channel from below. Arrivals are channel flow, as in
  AUDIT-B 7.2 (`flood = max(0, I + P − channel)`): an external inflow (a coastal flood's surge)
  enters storage but is not counted (B1 counted it). The onset record keeps the turn, excess,
  arrivals by source, the channel, opening storage and capacity, every tributary with the outflow it
  sent, the mean forest cover of all regions upstream and how many are below 0.2; open events are
  recorded compactly (region, start, turns, peak excess) and an event that ends with its end turn.
  The per-region `flood_excess` column and `flood_region_turns` still count every turn above the
  channel.
- **Channel** (B2): `CHANNEL_RATIO` (1.0) x the region's drainage basin's **normal inflow** in this
  phase: the normal precipitation (phase factor 1, no shock) of the region and every region upstream,
  plus the seasonal melt the account adds for their terrain in this phase (`TUNDRA_MELT`, tundra,
  warming), so normal rain and melt never cross it (lead decision: the first refit's channel left the
  melt out, so 105 of 112 flood events were the expected tundra melt). B1 used a fixed channel
  (`CHANNEL_CAPACITY`, x `RIVER_CHANNEL_FACTOR` on a named river region).
- **Model limitation: floods come only from storage released by forest loss.** Precipitation has no
  weather variability in this model: phase factors are at most 1 and a harvest shock only reduces it,
  so rain and melt never exceed their normal. A flood therefore needs stored water to be released:
  when an upstream region's forest cover drops (wildfire or clearing), its storage capacity falls and
  the water above the new capacity spills downstream. Every flood onset of the development `flow`
  runs (5) coincides with such an upstream capacity drop of 0.15-0.16 wu, as do all 63 exceedances the
  re-check found in replays at 32x10, 48x12 and 64x16. This matches AUDIT-B's intent that
  deforestation gives flashier floods, but there are no rain-driven floods; the onset record does not
  name the cause (its upstream cover and tributary outflows show it).
- **Drought**: a run of at least `DROUGHT_TURNS` settled turns with `S'/C < DROUGHT_FRACTION`. Its
  record keeps the start, declaration and end turns, the lowest fill, and over the run the
  precipitation against the normal precipitation (the forcing deficit), inflow, evaporation, the
  region's own irrigation withdrawal, the withdrawals of every region upstream and the upstream cover.
  Shorter runs are not recorded; the per-region `drought_turns` column shows them.
- Neither has any consequence in `record_only`. The existing river flood
  (`emergence._check_flood`), drought intensification and civ drought hazard are untouched.
- In `flow` a flood event acts once, at its onset (section 4), and a drought acts through the index
  itself: the derived index is the index drought intensification, the civ drought hazard, yields and
  capacity read.

### Order, state and resume

- `before_ecology` (immediately before the Phase 9 region sync): compute and check the account from
  the pre-tick world into a transient plan (`WatershedState._plan`, never serialized).
  `after_ecology` (after the ecology tick and its write-back): read the observed index, build the
  flood and drought records, commit storage, `last_index`, spells, the frame and the totals.
- A plan left by a failed tick is dropped at the next planning (`abandoned_plans`); nothing was
  settled, so a turn settles once. `after_ecology` without a plan for this turn raises.
- Persisted: the graph, storage, `last_index`, the opening storage, running drought spells, open
  flood events, `flow`'s pending flood modifiers, the last settled frame (full precision),
  cumulative totals and counters (about 11.5 KB of JSON at 32 regions). Exact checkpoints and state files carry it; no native state changes, so the checkpoint
  schema fingerprint is unchanged.

## 4. Flow mode (B2)

`--watershed-mode flow` makes the account the owner of the water index (audit B, 7.1-7.2; plan 5.2).
The account itself (section 3: the plan, the constants, the attribution of external flows, the
closure checks) is the same in both modes; `flow` adds what the account does with it.

Per turn, in Phase 9:

1. `before_ecology` computes and checks the plan from the pre-tick world, as in `record_only`.
2. `_apply_flow` writes each region's derived index into `ecology.water` and lets each of this
   turn's flood onsets act (below), **before the Phase 9 region sync**, so the native tick sees both.
3. The native tick runs with the replaced terms switched off and leaves the index as written (its
   clamp is a no-op: the derived index lies between the floor and the terrain cap). Its write-back
   rounds the index to 4 decimals (f32), so the index observed after the tick equals the derived
   one within 5e-5; verified in both native paths over a whole climate cycle (every phase) with
   irrigated regions in play (`tests/test_watershed_native.py`), while in `record_only` the old
   terms move the index by more than 0.01 on their own.
4. **Terrain transitions.** The Phase 9 post-pass (`emergence.tick_terrain_succession`) can turn a
   forest into plains, and `clamp_ecology` then cuts the index to the plains cap (0.80 → 0.70). The
   index used that turn is `min(index_derived, cap_after)`. `after_ecology` records each transition
   as a **cap change** (`cap_changes`: region, terrain and cap before and after, and in `flow`
   `index_out = max(0, index_derived − cap_after)`, an attributed outflow of the index). It is not a
   storage flow: the storage is unchanged, and from the next turn the account derives the index from
   the same storage under the new cap (taking the clamp from storage as well would count the cap
   change twice). The next turn's external flow is measured from the clamped index, so it is zero.
   The review found such turns in every development `flow` run (1-4 per 200 turns; gaps up to 0.1)
   that the viewer then refused; it now checks `observed = min(derived, cap_after)` there.
5. `after_ecology` records and commits as in `record_only`. The next turn's external flows are
   measured from the observed (rounded) index, so the rounding never enters storage.

**Replaced, never stacked: switched off exactly once.** `watershed.native_overrides(world)` returns
`FLOW_REPLACED_TERMS` and a zero harvest-shock water loss in `flow`, and `({}, None)` otherwise, so
without `flow` the configuration is exactly as before. Its one reader is the pinned seam
`agent_bridge.configure_ecology_runtime` (provisional witness layer `cwb2`, rebuilt over `cwc1b`), which
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
observed index equals the derived one in every region and phase over 80 turns (a whole cycle),
irrigated regions included, except the recorded cap changes, so no climate term, bonus or cascade
acted (native test above). The replaced terms' own state is untouched: a world before and after
planning differs only in the water index and, in regions where a flood event starts, the three flood
fields; irrigation works, rivers and the river topology are as they were. Tuning overrides of the
replaced keys (`ecology.water_recovery`, `ecology.deforestation_water_loss`, ...) have no effect in
`flow` (the overrides are applied after them).

**Upstream withdrawal reduces downstream inflow** on the graph: an irrigated tributary sends its
withdrawal nowhere, so the confluence's inflow falls by the same amount (tested offline; in `flow`
that lower inflow is the downstream region's index).

**Flood events act once, at their onset, through the old river flood's own effects**
(deterministic, no RNG; `Parameters` `flood_*`). The first B2 draft re-applied them on every turn
above the channel, which made 1-2 coastal confluences per world chronic flood sites (15-42 turn
runs, the capacity modifier held for a third of a run, the region's environment checks skipped for
the whole spell; review M2). Now, on the onset turn of an event with excess `e` (section 3):

```
days                        = 2 if e >= FLOOD_LONG_EXCESS (0.1 wu) else 1     the old flood drew 1-2
disaster_cooldowns["flood"] = days + 1
capacity_modifier           = min(current, FLOOD_CAPACITY_MODIFIER 0.85)       never raises a lower one
soil                        = max(soil, min(terrain soil cap, soil + FLOOD_SILT 0.15))   silt once
```

- **Withheld on a region under a cooldown.** As the old river flood never fired on a region holding
  any disaster cooldown, an onset on such a region acts not at all; the onset record says so
  (`withheld_by`: the cooldowns it held) and `flood_consequences_withheld` counts it. This counts a
  coastal flood's storm once (its cooldown is set in Phase 1 of the same turn; its surge is not
  channel flow either; review m2).
- **The modifier lasts its recorded cooldown.** The cooldown has one turn more than the old flood's
  because it is set in Phase 9, after that turn's Phase 1 decrement, so it covers this turn's tick and
  the next `days` turns. `simulation.py` restores the capacity modifier in Phase 1 only when every
  cooldown is gone, so a disaster that begins during the flood's cooldown would hold 0.85 longer; the
  account then restores its own value at its next Phase 9 (`active_consequences`), unless another
  system changed the modifier since (review m3). The flood cooldown skips the region's coastal flood
  and emergence checks for those `days` turns only, as the old flood's did; the rest of a long event
  leaves them alone.
- **A chronicle event per flood that acted** (`event_type` `flood`, "Swollen waters overflow the
  channels of ..."), so the chronicle, provenance and era-crisis counts see the consequence the
  simulation applied, in place of the superseded river flood's event (review m4). A withheld onset
  emits none (the coastal flood already did).
- Each onset records what it did (`consequence`: capacity modifier, cooldown, soil before and after)
  and `flood_consequences` counts it, so every consequence is traceable to the recorded condition
  (excess, arrivals by source, tributaries, upstream cover).

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
| Water index value | ecology tick | unchanged; derived index recorded beside it | **the derived index**, written before the tick, left by it (capped at a new terrain's cap where the post-pass changes terrain: a recorded cap change) |
| Deforestation cascade (−0.05 per deforested upstream region) | native `deforestation_water_loss` | unchanged | **replaced** by cover-dependent capacity and transpiration on the graph |
| River +0.15 water bonus | world generation | inside the opening storage, once | the same |
| River presence effects (capacity x1.2, fish, trade discount, barge cap, migration bonus, attractor) | world generation, economy, merchant, behavior, spatial | unchanged | unchanged |
| Irrigation water bonus and drought x1.5 | native through `has_irrigation` | unchanged; a recorded withdrawal in the account | **replaced** by the withdrawal (bonus 0, multiplier 1.0) |
| Irrigation arable ceiling, irrigation technique | economy, techniques | unchanged | unchanged (condition scaling is B3) |
| Coastal flood +0.1 water, ports off | `climate.check_disasters` | unchanged; its index change is a recorded external inflow | the same external inflow, now into the index's storage |
| River flood (water > 0.8, spring) | `emergence._check_flood` | unchanged; the account records its own flood events | **superseded**: draws kept, effect suppressed and recorded; each account flood event acts once with the same effects and its own chronicle event |
| Drought intensification, civ drought hazard, disease flares, yields, capacity, satisfaction, mortality stress | existing | unchanged | unchanged code, reading the derived index |
| Deaths | demographics, epidemics, famine | unchanged | unchanged: no new mortality authority |

## 7. Declared constants

`watershed.PARAMETERS` holds the constants in force (the refit after review, section 8) and
`B1_PARAMETERS` the B1 declared constants, kept for comparison. Both modes use `PARAMETERS`; each
record carries them (`parameters`). Only three constants are fitted; every other one is fixed and
the table says why.

| Constant | B1 (declared) | First B2 fit (superseded) | In force | Status |
| --- | --- | --- | --- | --- |
| `STORAGE_BASE` | 1.0 wu | 1.0 | 1.0 | unit (capacity without forest cover) |
| `PRECIPITATION_BASE` | 0.1 wu/turn | 0.13 | **0.3488** | **fitted** (at (0.2 + moisture) = 1) |
| `EVAPORATION_BASE` | 0.03 wu/turn | 0.02 | 0.03 | fixed (B1): only the precipitation/evaporation ratio is identified |
| `BASEFLOW` | 0.05 | 0.009 | **0.0644** | **fitted** (share of storage released downstream a turn) |
| `PHASE_PRECIPITATION` warming | 0.85 | 1.2 (at its range's top) | 1.0 | fixed: the old index has no warming-phase water term besides tundra melt |
| `PHASE_PRECIPITATION` drought | 0.3 | −0.9 | −1.0 | fixed at its physical limit: every drop of rain lost at the largest exposure x trend share (0.5); every freer fit went there |
| `PHASE_PRECIPITATION` cooling | 0.6 | −0.5 | **−0.3936** | **fitted** |
| `PHASE_EVAPORATION` warming | 1.3 | 1.05 | 1.0 | fixed (as warming precipitation) |
| `PHASE_EVAPORATION` drought | 1.6 | 2.8 | 4.0 | fixed at its declared limit (potential evaporation x2.5 at the largest exposure x trend); every freer fit went there |
| `PHASE_EVAPORATION` cooling | 0.7 | 1.35 | 1.0 | fixed: collinear with cooling precipitation (only their net is identified) |
| `SHOCK_PRECIPITATION` | 1.0 | 1.25 | 1.0 | fixed at its declared meaning (a bad year of depth h is a precipitation deficit of h); refits ranged 0-0.5 |
| `FOREST_RETENTION` | 0.5 | 0.25 (at its range's floor) | 0.5 | fixed (B1): the old index has no forest storage, so it cannot identify the forest linkage; refits ran to 0 |
| `TRANSPIRATION` | 0.3 | 0.3 | 0.3 | fixed (B1), for the same reason; refits ranged 0.02-0.55 |
| `TUNDRA_MELT` | 0.05 wu/turn | 0.05 | 0.05 | declared |
| `TERRAIN_EVAPORATION` | desert 1.6, steppe 1.25, tundra 0.5, others 1.0 | the same | the same | declared |
| `IRRIGATION_DEMAND`, `IRRIGATION_WETTING` | 0.02 wu/turn, 1.0 | the same | the same | declared |
| Channel | `CHANNEL_CAPACITY` 0.25 wu/turn, x2 on a river region | 0.35, x2 | `CHANNEL_RATIO` 1.0 | declared, not fitted: a channel carries its drainage basin's normal inflow (the region's and every region's upstream: precipitation at phase factor 1 and no shock, plus their terrain's seasonal melt in this phase) |
| Flood event end | (none) | (none; the review draft used 0.75 of the channel) | the region's normal arrivals | no constant: normal rain and melt plus the normal net outflow upstream |
| `DROUGHT_FRACTION`, `DROUGHT_TURNS` | 0.2, 3 | the same | the same | declared drought definition |
| `FLOOD_CAPACITY_MODIFIER`, `FLOOD_SILT`, `FLOOD_LONG_EXCESS` | (none) | 0.85, 0.15, 0.1 wu | the same | `flow` flood effects (the old river flood's modifier and silt) |
| `INDEX_FLOOR`, `CLOSURE_TOLERANCE` | 0.10, 1e-9 | the same | the same | the ecology's floor; relative |

## 8. Calibration (B2, development worlds only)

**Why it was redone.** The review (M3) found that the first B2 fit (twelve constants fitted on
eight 200-turn worlds) did not hold out of sample: at 64x16 the downstream wet bias doubled, over
turns 200-399 storage kept falling in three of four worlds, fold refits changed the sign of
constants, and four constants sat on their search bounds. The report above it also overstated fit
and stationarity. This section replaces it.

**Method** (`scripts/watershed_replay.py`; development worlds only, any other seed refused; no held
or evaluation world was used or targeted).

- Captures: the procedural development worlds 7, 11, 13, 17, 21, 31, 302 and 303, each at 32x10 and
  at 64x16, `--agents hybrid`, `record_only`, **400 turns** (five climate cycles of 75): each turn's
  inputs and observed index, the opening index and cover. In `record_only` the account changes
  nothing, so a replay under any constants sees the same world.
- Replay: `simulate`, a transcription of `account_step` (storage, derived index, flood excess); it
  equals `account_step` exactly on every capture (`check`, max difference 0). The opening storage is
  recomputed under the replayed constants (review m1: the first fit replayed from an opening computed
  under the capture's constants, which spilled at turn 0 and inflated its flood counts).
- Objective (`score`, lower is better): the **mean over worlds** of each world's weighted absolute
  errors, so errors in two worlds cannot cancel: 4 x |long-run storage drift| (whole cycle 2,
  turns 75-149, to cycle 5, turns 300-374) + 4 x |level, all regions| + |level, headwater| +
  |level, with upstream| + |amplitude ratio − 1| + 2 x |drought share − the same rule on the old
  index|. Turns 0-74 (spin-up from the world-generation index) are left out of all but the drift.
- Parameterizations: `full` (the first fit's twelve constants), `reduced` (six: precipitation,
  evaporation, baseflow, drought and cooling precipitation, drought evaporation), `minimal` (four:
  `reduced` with the drought phase fixed at the limits every freer fit reached) and `core` (three:
  `minimal` with evaporation fixed, since only the precipitation/evaporation ratio is identified).
  Bounds are physical: a phase factor f gives `max(0, 1 − (1 − f) x exposure x trend)`, and
  f ≥ −1 means at most all precipitation is lost at the largest exposure x trend share (0.5).
- Search: bounded Powell from three declared starting points (the declared values, and 25% and 75%
  of each range), the best kept; deterministic. A single start stopped in different local optima
  per fold (the `reduced` and `minimal` single-start runs below).
- Cross-validation: hold out two seeds, fit on the other six at 32x10, score the held two at 32x10
  and at 64x16 (the same seeds as larger worlds: a transfer check). Four disjoint folds compare the
  parameterizations; the chosen one is run over all 28 seed pairs (leave-two-out).

**Parameterizations, four disjoint folds** (held pairs {7, 11}, {13, 17}, {21, 31}, {302, 303};
scores are means over the folds; lower is better):

| Parameterization | Free | Train | Held, 32x10 | Held, 64x16 | Constants at a bound | Spread across folds |
| --- | --- | --- | --- | --- | --- | --- |
| `full` (single start) | 12 | 0.367 | 0.419 | 0.562 | warming precipitation 1.5 (top) and warming evaporation 1.0 (floor) in 4/4, drought evaporation 4.0 (top) 4/4, forest retention → 0 in 4/4 | shock 0.09-0.44, transpiration 0.02-0.55, cooling evaporation 0.54-0.78 |
| `reduced` (single start) | 6 | 0.525 | 0.624 | 0.725 | drought precipitation −1 (floor) and drought evaporation 4 (top) in 4/4 | stuck in local optima (cooling −0.06 to +1.0) |
| `minimal` (three starts; 3 of 4 folds) | 4 | 0.351 | 0.427 | 0.468 | precipitation at its 0.3 top in 1/3 | baseflow 0.036-0.080, cooling −0.23 to +0.64 |
| **`core` (three starts)** | **3** | **0.335** | **0.366** | **0.435** | none | precipitation 0.33-0.35, baseflow 0.062-0.070, cooling −0.36 to −0.38 |
| First B2 fit (fixed constants; fitted on these seeds at 200 turns) | — | — | 0.612 | 0.731 | | |
| B1 declared (fixed) | — | — | 3.00 | 3.46 | | |

`core` is chosen: the fewest free constants, the best held-out scores at both sizes, no constant at a
bound and the same constants in every fold.

**Leave-two-out over all 28 seed pairs** (`core`; fit on six seeds at 32x10, score the held two):

| | Train | Held, 32x10 | Held, 64x16 |
| --- | --- | --- | --- |
| Mean score (range over folds) | 0.334 (0.293-0.376) | 0.371 (0.232-0.482) | 0.440 (0.264-0.644) |
| Ratio to train | 1 | 1.11 (held worse in 17 of 28 folds) | 1.32 |
| Fitted constants across folds | precipitation 0.315-0.398 (median 0.339), baseflow 0.052-0.074 (0.066), cooling precipitation −0.50 to −0.27 (−0.37); none at a bound | | |

**Independent check** (the reviewer's folds, run with this tool on captures verified bit-identical to
independent ones, and a size no fit or model choice saw):

| Check | Train | Held, 32x10 | Held, 64x16 | Constants (precipitation, baseflow, cooling) |
| --- | --- | --- | --- | --- |
| Held pair {7, 31} | 0.323 | 0.391 (1.21x) | 0.645 (2.0x, the worst fold) | 0.3345, 0.0614, −0.379 |
| Held pair {11, 302} | 0.313 | 0.456 (1.46x) | 0.392 | 0.3178, 0.0629, −0.271; none at a bound |
| Unseen size 48x12 (seeds 7, 11, 13, 17; constants in force) | 0.340 (the 32x10 train score) | score 0.417 (1.23x); level with upstream +0.079 (max +0.138), all +0.024; drought 0.119 (old rule 0.134); drift −0.9% (cycle 2 → 5), +2.5% late; corr 0.71, amplitude 0.97 | | first B2 fit 0.499, B1 2.95 |

So the remaining overfit, precisely: held-out error is 1.1-1.5x the training error at the fitted size
(up to 2.0x in one fold at 64x16), 1.23x at the unseen 48x12, and the downstream wet bias (+0.05 to
+0.08, up to +0.15) is what grows out of sample.

Per held seed (mean over its 7 folds): score at 32x10 / 64x16 — procedural 7 0.50 / 0.70, 11 0.53 /
0.44, 13 0.38 / 0.51, 17 0.35 / 0.37, 21 0.21 / 0.19, 31 0.33 / 0.63, 302 0.36 / 0.37, 303 0.31 /
0.32. The held-out error is 11% above the training error at the fitted size and 32% above it at
64x16, where the downstream bias is larger (below).

**The constants in force** (`core` fitted on all eight seeds at 32x10; train score 0.340), replayed
over 400 turns:

| | 32x10 (fitted) | 64x16 (transfer) | First B2 fit, 32x10 / 64x16 |
| --- | --- | --- | --- |
| Score | 0.340 | 0.434 | 0.612 / 0.731 |
| Level, all / headwater / with upstream | +0.007 / −0.020 / +0.053 | +0.028 / −0.021 / +0.083 | −0.021 / −0.050 / +0.028; −0.003 / −0.059 / +0.062 |
| Largest per-world level, with upstream | +0.148 (p11) | +0.152 (p7) | +0.125; +0.129 |
| Amplitude ratio; median correlation | 0.99; 0.71 | 1.00; 0.70 | 1.03, 0.70; 1.03, 0.67 |
| Drought share (old rule) | 0.122 (0.111) | 0.123 (0.152) | 0.153 (0.111); 0.168 (0.152) |
| Storage drift, cycle 2 → 5 (old index) | +0.7%, worst 6.8% (+12.3%) | −2.2%, worst 6.1% (+13.6%) | −2.6%, worst 17.1%; −10.4%, worst 16.2% |
| Storage drift over 200-399, cycle 4 → 5 (old index) | −1.2% (+3.4%) | −1.4% (+1.7%) | +0.1%; −0.2% |
| Flood events per world, 400 turns | 1.1 (none in five of eight worlds; longest 6 turns) | 4.6 (in every world; longest 13) | (fixed channel) |

Per world, 32x10 (fitted) and 64x16 (transfer):

| World | Score 32 / 64 | Level with upstream 32 / 64 | Drought share 32 (old rule) | Drought share 64 (old rule) | Drift cycle 4 → 5, 32 (old index) |
| --- | --- | --- | --- | --- | --- |
| procedural 7 | 0.45 / 0.71 | +0.039 / +0.152 | 0.160 (0.126) | 0.134 (0.219) | +2.7% (+9.4%) |
| procedural 11 | 0.50 / 0.46 | +0.148 / +0.102 | 0.108 (0.145) | 0.119 (0.162) | +10.8% (+9.8%) |
| procedural 13 | 0.37 / 0.49 | +0.085 / +0.073 | 0.127 (0.149) | 0.121 (0.141) | +3.2% (+22.8%) |
| procedural 17 | 0.33 / 0.37 | +0.007 / +0.055 | 0.119 (0.067) | 0.131 (0.124) | −4.1% (−4.5%) |
| procedural 21 | 0.18 / 0.16 | +0.022 / +0.062 | 0.112 (0.097) | 0.128 (0.129) | −0.4% (+1.6%) |
| procedural 31 | 0.31 / 0.60 | +0.037 / +0.085 | 0.123 (0.116) | 0.124 (0.164) | −1.0% (+2.0%) |
| procedural 302 | 0.31 / 0.36 | +0.004 / +0.057 | 0.110 (0.079) | 0.096 (0.124) | −20.4% (−12.8%) |
| procedural 303 | 0.26 / 0.33 | +0.084 / +0.079 | 0.119 (0.110) | 0.134 (0.155) | −0.3% (−1.1%) |

**The remaining mismatch, plainly** (development worlds only):

- **Downstream wet bias.** Regions with upstream inflow run wetter than the old index: +0.05 on
  average at 32x10 and +0.08 at 64x16, up to +0.15 in single worlds. The account passes water
  downstream, which the old index has no term for; the bias grows with basin size. Headwater regions
  are within −0.05 of the old index in every world.
- **Drought frequency differs by world.** The account's drought share is 0.11-0.16 at 32x10 and
  0.10-0.13 at 64x16; the old rule's ranges 0.07-0.15 and 0.12-0.22. The account is more uniform
  across worlds than the old index: it has more drought than the old rule in six worlds at 32x10 (by
  up to 0.05) and less in six at 64x16 (by up to 0.09, procedural 7).
- **The drought phase is at its physical limits** (no rain at the largest exposure, evaporation
  x2.5): the account cannot dry as fast as the old index's drought term where exposure is highest.
- **Correlation 0.67-0.78** (median per region): the derived index follows the climate cycle, not
  the old index's turn-to-turn moves.
- **Stationarity.** Over whole cycles storage moves −6% to +7% from cycle 2 to cycle 5 while the old
  index itself moves −1% to +34% over the same cycles; within cycles 4 → 5 storage follows the old
  index's own movement (−20% in procedural 302 where the old index falls 13%; +11% in procedural 11
  where it rises 10%), which comes from the forcing, not from a loss in the account.
- **Floods are rare and come from forest loss.** The channel carries the basin's normal inflow,
  seasonal melt included (section 3), and rain never exceeds its normal in this model, so floods
  arise only from storage released when upstream forest cover drops (section 3's model limitation):
  about 1.1 flood events per world per 400 turns at 32x10 (none in five of eight worlds) and 4.6 at
  64x16, each one exceedance long or a few turns. With the first refit's channel (normal
  precipitation without melt) 105 of 112 events in the development `flow` runs were the expected
  tundra melt in the warming phase. No constant was tuned toward a flood count; the channel and the
  event rule do not touch storage or the derived index, so the calibration above is unchanged.
- **Identifiability.** The old index identifies three constants (the precipitation/evaporation
  ratio, baseflow and the cooling-phase cut); everything else is fixed by declaration. The fitted
  three are stable across folds. The fit is still to the old index's behaviour on eight development
  worlds; no held-out world was used and none was targeted.

`flow`'s documented claims rest on this: the derived index matches the old index's level and cycle
in headwater regions and on average, runs wetter downstream (more so in larger worlds), and holds
storage close to stationary over 400 turns on these worlds.

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
`record_only` run of the same seed: 32 regions, 10 civs, `--agents hybrid`, 200 turns, the constants
in force (section 7), native extension `101a4cd5…`. `record_only` changes nothing (section 11), so it is the world without the
account. One run per world: a trajectory diverges chaotically from the first turn the index
differs, so per-world differences in food, capacity and population include that divergence. It
refuses any other seed; no held screen was run (CW3 is preregistered after review).

Means over the 200 snapshots, `flow` / `record_only` (capacity and population: the final state; the
water factor is the capacity term `min(1, water / 0.5)`; food is the mean sufficiency and the share of
region-turns below 1). Runs of source `538ad09e` (the channel with seasonal melt, no onset on the
opening turn, events ending at normal arrivals; extension `e724072d…`, main's Rust after PR #87):

| World | Index, all | Headwater | With upstream | Water factor | Food sufficiency | Shortfall share | Effective capacity, end | Population, end | Famine events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | 0.524 / 0.508 | 0.466 / 0.480 | 0.620 / 0.556 | 0.791 / 0.786 | 1.20 / 1.11 | 0.422 / 0.475 | 1050 / 1002 | 481 / 414 | 116 / 130 |
| procedural 11 | 0.621 / 0.586 | 0.612 / 0.625 | 0.640 / 0.511 | 0.900 / 0.849 | 1.47 / 1.33 | 0.258 / 0.351 | 956 / 961 | 389 / 677 | 39 / 60 |
| procedural 13 | 0.613 / 0.595 | 0.591 / 0.605 | 0.654 / 0.574 | 0.883 / 0.857 | 1.42 / 1.33 | 0.306 / 0.351 | 1090 / 1195 | 607 / 606 | 81 / 94 |
| procedural 17 | 0.624 / 0.636 | 0.606 / 0.638 | 0.656 / 0.631 | 0.897 / 0.916 | 1.24 / 1.20 | 0.387 / 0.409 | 935 / 970 | 618 / 597 | 112 / 98 |
| procedural 21 | 0.630 / 0.606 | 0.606 / 0.589 | 0.665 / 0.631 | 0.890 / 0.867 | 1.26 / 1.09 | 0.394 / 0.475 | 941 / 1157 | 473 / 487 | 126 / 132 |
| procedural 31 | 0.616 / 0.584 | 0.597 / 0.565 | 0.644 / 0.612 | 0.892 / 0.856 | 1.09 / 1.19 | 0.491 / 0.415 | 986 / 1041 | 811 / 732 | 147 / 112 |
| procedural 302 | 0.609 / 0.607 | 0.575 / 0.577 | 0.652 / 0.645 | 0.869 / 0.868 | 1.16 / 1.18 | 0.431 / 0.431 | 915 / 1075 | 606 / 464 | 121 / 101 |
| procedural 303 | 0.630 / 0.604 | 0.620 / 0.622 | 0.649 / 0.569 | 0.900 / 0.863 | 1.10 / 0.94 | 0.494 / 0.614 | 849 / 938 | 348 / 367 | 111 / 146 |

| World | Droughts (flow / record-only account) | Flood events that acted (flow) | Superseded river floods | River floods (record only) | Coastal floods (flow / record only) | Index with / without upstream irrigation (flow) |
| --- | --- | --- | --- | --- | --- | --- |
| procedural 7 | 81 / 84 | 0 | 0 | 0 | 4 / 4 | 0.653 / 0.575 |
| procedural 11 | 48 / 45 | 0 | 0 | 0 | 22 / 22 | 0.643 / 0.633 |
| procedural 13 | 54 / 53 | 1 | 7 | 1 | 22 / 22 | 0.659 / 0.640 |
| procedural 17 | 48 / 50 | 1 | 0 | 0 | 32 / 32 | 0.732 / 0.597 |
| procedural 21 | 47 / 42 | 3 | 0 | 0 | 25 / 25 | 0.682 / 0.638 |
| procedural 31 | 47 / 51 | 0 | 0 | 0 | 36 / 36 | 0.695 / 0.609 |
| procedural 302 | 51 / 53 | 0 | 0 | 0 | 34 / 34 | 0.649 / 0.655 |
| procedural 303 | 46 / 50 | 0 | 12 | 1 | 17 / 17 | 0.647 / 0.651 |

**Flood events by cause** (`flow`, 8 worlds x 200 turns; an account flood event is *melt* when the
seasonal melt of its basin alone accounts for its excess, else *release*: stored water released after
an upstream forest loss, since rain never exceeds its normal (section 3); every release onset in force
coincides with an upstream capacity drop of 0.15-0.16 wu. *Coastal* are the coastal floods, a separate
authority): with the channel = normal precipitation; with the channel = normal inflow, melt included;
and in force (that channel, no onset on the opening turn, events ending at normal arrivals):

| World | Normal precipitation: release / melt / coastal | Normal inflow: release / melt / coastal | In force: release / melt / coastal |
| --- | --- | --- | --- |
| procedural 7 | 0 / 13 / 4 | 0 / 0 / 4 | 0 / 0 / 4 |
| procedural 11 | 1 / 15 / 22 | 1 / 0 / 22 | 0 / 0 / 22 |
| procedural 13 | 1 / 13 / 22 | 1 / 0 / 22 | 1 / 0 / 22 |
| procedural 17 | 1 / 16 / 32 | 1 / 0 / 32 | 1 / 0 / 32 |
| procedural 21 | 2 / 9 / 25 | 2 / 0 / 25 | 3 / 0 / 25 |
| procedural 31 | 0 / 14 / 36 | 0 / 0 / 36 | 0 / 0 / 36 |
| procedural 302 | 1 / 8 / 34 | 1 / 0 / 34 | 0 / 0 / 34 |
| procedural 303 | 1 / 17 / 17 | 1 / 0 / 17 | 0 / 0 / 17 |
| **Total** | **7 / 105 / 192** | **7 / 0 / 192** | **5 / 0 / 192** |

The opening rule removed three events, all on turn 0 (procedural 11, 302 and 303), when every storage
opens near capacity from the world-generation index; the end rule added one (procedural 21's second
exceedance, at turn 42, fell inside the first event's 31 open turns and had no consequence).

**Events against exceedances** (an exceedance: a turn crossing the channel from below, never the
opening turn), before and after the end rule:

| | Exceedances | Events (per exceedance) | Consequences | Median / longest event, turns |
| --- | --- | --- | --- | --- |
| Development `flow` runs, 200 turns: end at 0.75 of the channel | 5 | 4 (0.80) | 4 | 31 / 31 |
| The same, end at normal arrivals (in force) | 5 | 5 (1.00) | 5 | 1 / 6 |
| Replays 32x10, 400 turns: 0.75 of the channel / normal arrivals | 9 | 7 (0.78) / 9 (1.00) | — | 15 / 31; 1 / 6 |
| Replays 64x16, 400 turns: 0.75 of the channel / normal arrivals | 37 | 34 (0.92) / 37 (1.00) | — | 10 / 43; 1 / 13 | An equilibrium opening was
considered instead and not taken: it would make the index `flow` uses jump at turn 0 (the derived
index is continuous with the old index at enable by design); the onset rule needs no constant.

**Flood spells across the fixes** (`flow`, 200 turns): the first B2 draft re-applied the consequences
on every turn above the fixed channel (spells are runs of consecutive flood turns); the review's event
rule acted once per event; the melt-aware channel leaves only the anomalous events:

| World | First draft: spells, longest, consequences | Events, channel without melt: events, median / longest, consequences | Events, channel with melt (in force): events, turns, consequences |
| --- | --- | --- | --- |
| procedural 7 | 2, 27, 31 | 13, 15 / 15, 13 | 0, —, 0 |
| procedural 11 | 0, 0, 0 | 16, 15 / 45, 16 | 0, —, 0 |
| procedural 13 | 0, 0, 0 | 14, 15 / 15, 14 | 1, 6, 1 |
| procedural 17 | 0, 0, 0 | 17, 15 / 15, 17 | 1, 1, 1 |
| procedural 21 | 5, 15, 44 | 11, 15 / 31, 11 | 3, 1 / 3, 3 |
| procedural 31 | 5, 42, 94 | 14, 15 / 15, 14 | 0, —, 0 |
| procedural 302 | 0, 0, 0 | 9, 15 / 45, 9 | 0, —, 0 |
| procedural 303 | 1, 15, 15 | 18, 15 / 45, 18 | 0, —, 0 |

None was withheld in either event run.

Observations (development only):

- **Water.** Regions with upstream inflow are wetter under `flow` in all eight worlds (+0.01 to
  +0.13): the account passes baseflow downstream, which the old index has no term for (section 8's
  downstream bias). Headwater regions move both ways (−0.03 to +0.03). The world mean and the water
  factor of capacity are higher in seven of eight worlds; soil is unchanged within 0.006.
- **Food, carrying capacity and population: no consistent direction.** Mean sufficiency is higher in
  six worlds and lower in two, the shortfall share follows; final effective capacity is lower in seven
  (a single end-of-run snapshot); final population is higher in five and lower in three. Eight single
  runs cannot separate these from trajectory divergence.
- **Floods are rare and follow forest loss.** 0-3 account flood events per world in 200 turns (5 in
  all), each lasting 1-6 turns and acting once at its onset; every one follows an upstream forest
  loss that released stored water (an upstream capacity drop of 0.15-0.16 wu). There are no
  rain-driven floods in this model (section 3). The expected melt no longer floods (105 events
  before, 0 after), nor does the opening turn (3 before). Coastal floods (192) are unchanged.
- **Droughts** are as frequent as the record-only account finds in the world without it (46-81
  against 42-84 declared per world), now acting through the index.
- **Superseded river floods.** The old check, reading the derived index, draws a river flood more
  often (7 and 12 in procedural 13 and 303, against 1 each without the account); all were superseded.
- **Downstream.** The last column of the second table compares different regions (whose upstream
  does or does not irrigate), so it is confounded by where irrigation is built (mixed: lower in three
  worlds). The controlled evidence that upstream withdrawal reduces downstream inflow is the offline
  test (section 4).

## 10. Record and viewer

`snapshot.livelihoods.watershed` (schema 1). This code writes stage `B2` records in both modes (flood
events, terrain cap changes, the B2 constants; review n2: a `record_only` record no longer carries
stage `B1` beside B2 constants). Stage `B1` records (`record_only`, earlier bundles) are still read:

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
- B2, when observed: `floods` holds the flood events that **started** this turn (onset records,
  arrivals = precipitation + inflow; B1 listed every region-turn above the channel, with the
  external inflow in its arrivals), `flood_events` the `open` events (region, start, turns, peak
  excess) and those `ended` this turn (with their end turn), and `cap_changes` the terrain
  transitions of the post-pass (region, terrain and cap before and after; `flow`: `index_out`); the
  counters add `floods_started`, `floods_ended` and `terrain_cap_changes`;
- when not observed: the per-turn fields are `null`, never empty, and `storage` holds the account's
  storage (a settled turn's `regions.storage` is the same list, so it is not repeated).
- `flow` only: each onset's `consequence` (`capacity_modifier`, `cooldown`, `soil_before`,
  `soil_after`) or, when withheld, `withheld_by` (the cooldowns the region held), the record's
  `superseded` list (this turn's superseded river floods: `turn`, `region`, `duration`; `null` when
  unobserved) and the counters `flood_consequences`, `flood_consequences_withheld` and
  `superseded_river_floods`. `regions.index_observed` equals `index_derived` within the native
  rounding, or `min(index_derived, cap_after)` for a region with a cap change.

Values are rounded to 6 decimals; the full-precision frame (outflow and full drought conditions
included) stays in the state. Growth of the encoded bundle (version-6 deltas, after review m7): a
60-turn hybrid 32-region run (procedural 11) +141 KB, **+4.25%** (was +5.52%); a 150-turn agents-off
32-region run (procedural 31) **+5.79%** (the reviewer measured +8.5% before). The static part costs
nothing in the encoded bundle (its deltas elide unchanged values), so it stays in every record; the
savings come from dropping the repeated storage list, the derived outflow column and the repeated
drought conditions.

Viewer (types in `viewer/src/watershedTypes.ts`; `types.ts` is pinned and unchanged):

- `readWatershed(snapshot, regions, run)` is strict and keeps five states apart (stage B1
  `record_only` and stage B2 in both modes; a record with another stage's fields, a flow record
  without its superseded list, a flow onset with neither or both of a consequence and a withheld
  list, a record-only flood with either, an onset without its open event, an event both open and
  ended, a malformed cap change, or a flow index used that differs from the derived one, or from
  the derived one capped at a recorded cap change, by more than the native rounding (5e-5) is
  malformed): **disabled** (no
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
- For a B2 record the panel lists the flood events that started (onset conditions), the open and
  ended events (start, turns, peak excess) and the terrain cap changes, and explains the event rule.
- In `flow` the panel says that the derived index is the index the simulation used and which terms
  were switched off, adds a "What it did" column to the onsets (capacity modifier, cooldown, soil
  before → after, or "withheld: the region held a ... cooldown"), shows the index the clamp removed
  at a cap change, a "Superseded river floods" table (region, duration) and the flow counters.
- Region history offers "Water index the simulation used", the derived index and "Watershed storage"
  when the run records the account, labelled by the run's mode (`watershedRunMode`): "Water index
  the watershed account would derive (record only)" or "... derived (flow: the index used)", with a
  matching explanation; absent, malformed and unobserved turns read as missing with their reason.
- Batch Lab's feature options recompute `procedural_world` from the regions the batch will send
  (`viewer/src/lib/featureWorld.ts`, `TEMPLATE_REGION_POOL` 12, pinned on the Python side by
  `tests/test_watershed.py`).

## 11. Verification (2026-11-06, extension `101a4cd5…`)

### B2 after review and re-check (source `538ad09e`: the review fixes, the melt-aware channel, no onset on the opening turn, events ending at normal arrivals, and the merge of `main` `ae94bca6`)

Native runs used the shared extension built from `main` `ae94bca6` (SHA-256 `e724072d…`; this branch's
Rust equals main's, no Rust change) with `PYTHONPATH` set to this worktree's `src`; the identity runs
used a `git archive` of the committed tree and a copy of that extension.

- Offline: `tests/test_watershed.py`, 62 cases, in the oracle chunk `connected-world-b`. Bounded
  offline lane (`cwb2` last: `..., "cws1", "cwc1b", "cwb2"`, rebuilt against main's
  `agent_bridge.py`): PASS, 69 chunks in 310.3 s, slowest `systems-2` 37.4 s of 110 s. Witness tests of the playbook: 509 passed.
- Native: `tests/test_watershed_native.py` (shard 0; 417 modules), 3 passed: in `--agents hybrid` and
  `--agents off` over 80 turns (every climate phase) the observed index equals the derived one within
  the native rounding, or the derived one capped at a recorded cap change, with irrigated regions in
  play; `record_only` shows the old terms moving it by more than 0.01; a `flow` run resumes exactly.
- Feature-off identity (`turn_speed_identity.py`) against `8abc1acb` (its outputs with their own
  copied extension): 9 cases, 399 files, 0 differences.
- `record_only` against off (procedural 11 and 31, hybrid, 200 turns), outputs compared after
  removing only the watershed record: 16 files each, 0 differences.
- `flow` exact resume, `checkpoint_identity.py run --case proc32_hybrid_s11` with
  `--watershed --watershed-mode=flow`: PASS, 39 resume points, 0 differences; checkpointing changes
  nothing (40 files). Procedural 13, hybrid, resumed at turn 33 with a flood event open (since turn
  30) to turn 60: 16 files, 0 differences.
- Calibration replay: `simulate` equals `account_step` exactly on all 16 captures, normal arrivals
  included (max difference 0).
- Viewer: every snapshot of the 16 development runs (8 `flow`, 8 `record_only`, 200 turns each) reads
  ok with the real reader (3200 snapshots); 1587 tests passed, 2 skipped (157 files), lint and production build; desktop 1440x900 and phone 390x844
  browser check of the procedural-13 `flow` run (a superseded river flood at snapshot 2, a flood
  event that acted at 31, a terrain cap change at 73, the last snapshot, and the region history
  labelled for `flow`): 62/62 checks, no console errors, no page overflow on the phone.
- The same checks passed on `cbccee74` (the opening rule, events ending at 0.75 of the channel): lane
  69 chunks in 337.8 s, feature-off 0 differences, resume PASS, viewer 1587 tests, 62/62 browser
  checks; and on `b87e9aa2` before the merge (extension `101a4cd5…`).

### B2 first draft (superseded constants and flood rule; source `c25a4113`)

The same checks passed on the first draft: offline lane PASS (66 chunks, 259.9 s), native tests 3
passed (30 turns), feature-off identity 9 cases / 399 files / 0 differences, `record_only` against
off 0 differences, `checkpoint_identity` with `flow` PASS (39 resume points), a mid-flood resume
16 files / 0 differences, viewer 1560 tests with lint and build and a 47/47 browser check. The review
then found the defects corrected above (M1-M3, m1-m5).

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
| Three constants fitted to the old index on the eight development worlds; the rest fixed by declaration | evidence gap (review M3) | calibration (section 8): leave-two-out CV and a 64x16 transfer check; remaining mismatch stated there (downstream wet bias +0.05 at 32x10, +0.08 at 64x16; drought frequency more uniform than the old index's; drought phase at its physical limits). No held world used; the activation report uses the same worlds |
| Flood events are rare: about 1.1 per world per 400 turns at 32x10 (none in five of eight worlds), 4.6 at 64x16, each 1-13 turns | declared (channel = the basin's normal inflow, seasonal melt included; events end at normal arrivals), not fitted toward any count | section 8; consequences act once per event (section 4) |
| Floods come only from storage released by upstream forest loss; no rain-driven floods | model limitation (re-check minor 2): precipitation has no weather variability (phase factors at most 1, shocks only reduce it) | section 3; a weather term would be a later slice |
| `flow`'s effects on food, carrying capacity and population | evidence gap | development activation report (section 9): no consistent direction over eight single runs; CW3, preregistered after review, is the test |
| `record_only` floods and droughts have no consequence | intentional (record only) | `flow` applies them through the existing fields and the index (section 4) |
| `flow` requires the native ecology | intentional boundary | the pure-Python fallback cannot switch native terms off: refused at startup, on a state-file resume and at planning (tested) |
| `flow` floods act in Phase 9, a turn after the old Phase 1 river flood would | intentional | the cooldown is one turn longer so it covers the same turns (section 4) |
| A flood modifier held past its cooldown by a later disaster's cooldown | corrected (review m3) | the account restores it at its next Phase 9 (up to Phases 1-8 of one turn late) unless another system changed it (tested) |
| A terrain transition clamps the index to a new cap in the Phase 9 post-pass | corrected (review M1) | recorded as a cap change; the viewer reads `min(derived, cap)` there (section 4) |
| `--watershed-mode` without `--watershed` on a new world | refused (review n1) | `--watershed-mode ... requires --watershed` (tested) |
| `--agents off` flow when the extension imports but `EcologySimulator` cannot be built | intentional (review n4) | refused at turn 0's planning, not at startup (the native flag is known only then) |
| The native write-back rounds the index to 4 decimals | intentional (native, unchanged) | observed within 5e-5 of the derived index; never enters storage (the next external flow is measured from the observed index) |
| A superseded river flood sets no cooldown | intentional | its draws and that turn's control flow are kept; the region's checks run in later turns, as any `flow` change can alter them |
| `agent_bridge.configure_ecology_runtime` is pinned | reviewed provisional witness layer `cwb2` | the one seam, rebuilt over `cwc1b` (main `ae94bca6`); consolidated by the lead at merge |
| Irrigation service is 1.0 for every active work | missing capability | infrastructure condition (B3) scales it |
| The account reads pre-tick terrain for the index cap; a same-turn succession changes the cap only from the next turn | intentional | recorded as a cap change (B2) |
| Lake shores | corrected (review m8) | a shore on lakes only drains to the lake (`to_lake`), never to the sea; no development world has a lake (a constructed one is tested) |
| External flows other than the coastal flood are unattributed | evidence gap | recorded with an explicit `unattributed` remainder; a stale baseline is flagged in `record_only` and refused in `flow` (tested) |
| Closure checks are construction invariants | documented (review m2) | they guard routing and bounds; the model itself is a calibration question |
| A drop of the index larger than storage is recorded as unmet, not taken | intentional | recorded (`external_out_unmet`) |
| Opening on a resumed world, ending or changing mode on resume | refused | tested (exact and state-file resumes); in `flow` the native config is checkpointed with the run |
