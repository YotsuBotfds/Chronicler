# Program B audit: living watersheds and infrastructure

Audit lane B, 2026-11-06. Source: `/home/user/Chronicler` at `8abc1acb` (detached `HEAD`,
clean tree; PR #82, the checkpoint-3 record). Read-only: no tracked file was changed. Every
file this lane wrote is under `.../scratchpad/audit-b/`.

**Evidence labels.** **[V]** means verified in source (file:line) or in a run or script this
lane executed. **[I]** means inferred from the formulas, not measured. **[U]** means
unverified. Line numbers refer to `8abc1acb`.

**What this lane ran** (development seeds only, one process at a time, `PYTHONHASHSEED=0
RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1 PYTHONPATH=src`):

- `scripts/river_topology.py` and `scripts/drainage.py` (in this folder): **world generation
  only**, no simulation. They cover template 1, 3, 7, 9, 11, 23, 42 (8x4), procedural 7, 11,
  13, 17, 21, 31, 302, 303 (32x10) and procedural 7, 11 (64x16). Outputs:
  `river_topology.txt`, `drainage.txt`.
- One simulation: procedural seed 7, 32x10, 200 turns, `--agents off --simulate-only`, 17 s.
  `.venv` has **no native extension**, so this run used the pure-Python ecology fallback.
  Output is in `runs/p7off/`.
- `scripts/refactor_preflight.py` (read-only) on 57 candidate files. Outputs:
  `preflight.json`, `preflight2.json`, `preflight-summary.txt`.
- No hybrid run (no extension in `.venv`; the lead is building `~/.venvs/chronicler-native`).
  No held or reserved seed.

---

## 0. Headline findings

1. **Rivers almost never exist in development worlds. [V]** Template worlds have none:
   `generate_regions` never creates them (`world_gen.py:76-105`), and rivers come only from
   procedural geography (`world_gen.py:553-556, 583-584`) or scenarios
   (`scenario.py:482-514`). At procedural 32x10, 5 of 8 development worlds have **zero**
   rivers and 3 have one river of 2-3 regions. At 64x16 there are 1-3 rivers of 2-4 regions,
   and no region lies on two rivers (`river_topology.txt`).
   - So every river-keyed mechanism (the deforestation cascade, river floods, river trade
     discounts, barge cargo, the migration bonus, the river attractor) is nearly inert in the
     cohorts Program B will screen.
2. **A full drainage graph can be rebuilt from persisted procedural data. [V]**
   - The rule: each region drains to the lowest land neighbour that is lower than itself.
     Coastal regions drain to the sea. Land neighbours are `adjacencies` minus
     `geography.sea_lanes`, and heights come from `geo.elevation`.
   - The rebuilt graph reproduces **every** persisted river step on all 10 procedural
     development worlds (`drainage.txt`, `rivers_reproduced=True`).
   - At 32x10: 13-15 inland regions per world have a downhill neighbour, there are 8-11
     multi-region basins, chains are up to 3 hops, and up to 5 regions lie upstream of one
     region.
   - The watershed model should run on this graph. Named rivers are the high-flow subset of
     it.
3. **Water is a dimensionless index; nothing hydrological is conserved. [V]**
   - `Region.ecology.water` is clamped to a terrain range: floor 0.10, terrain caps 0.20-0.95
     (`ecology.py:51-77`).
   - Recovery is climatic (+0.03 per temperate turn). Losses come from the climate phase, the
     harvest shock and the river cascade. Irrigation adds +0.03 x pressure outside drought and
     multiplies drought loss by 1.5 (`ecology.py:785-821`; `ecology.rs:716-771`).
4. **The deforestation cascade is pair-deduplicated but uncalibrated. [V]/[I]**
   - It is not conserved. It is in `ecology.py:1145-1163` and `ecology.rs:866-911`.
   - Each distinct upstream region with cover below 0.2 removes 0.05 water a turn from every
     region below it on the same river path. That exceeds temperate recovery (+0.03). [I] One
     deforested upstream region therefore holds a downstream river region near the 0.10 floor
     for as long as it stays deforested.
   - A tributary stops at its confluence, so tributary deforestation never reaches regions
     below the confluence. That is an under-count, not a double count (`geography.py:686-694`).
5. **Irrigation and roads are near-universal and permanent; ports are nearly absent. [V]** In
   the procedural-7 off-mode run at turn 200 (32 regions):
   - 25 active irrigation works (33 built), 27 active roads, 0 active ports (3 built, all
     later deactivated);
   - 12 scorched-earth events.

   None of these assets has any condition, upkeep or repair (`infrastructure.py:164-213`).
   - Roads give **no** transport discount (`economy.py:72`, "placeholder — no roads yet"). They
     only extend two-hop trade range through the road technique and the railways focus
     (`techniques.py:1152-1192`, `resources.py:215-222`).
   - The PORTS infrastructure type is not read by maritime, which treats coastal regions as
     its ports (`maritime.py:221-308`). PORTS counts only in tech-focus scores and is
     deactivated by coastal floods (`climate.py:317-319`).
6. **There is an existing repair authority to reuse.**
   - RS2 repair projects provide scope, labour channels, timber, coins, prepaid rounding,
     ledger closure, L9 `repairs` envelopes and war damage. PL3 adds named farm crews and the
     maintenance-obligation reservation. PL1 supplies timber.
   - RS2's asset kinds are fixed to `Literal["granary", "workshop"]`
     (`repair_projects_state.py:91`), and the viewer reader rejects any other kind
     (`viewer/src/lib/repairProjects.ts:67-150`).
7. **Pins.**
   - Every seam that would let infrastructure condition reach its existing effects is in
     pinned Python: `economy.arable_capacity`, plus the `has_irrigation` column and
     `configure_ecology_runtime` in `agent_bridge.py`.
   - The whole native ecology path is pinned by the RS5 inverse layer: `ecology.rs`,
     `region.rs`, `ffi/ecology_sim.rs`, `ffi/batch.rs` and `ecology.py`.
   - The proposal below needs **no Rust change** and a small number of reviewed Python
     witness layers.

---

## 1. Rivers: generation, representation, consumers, double counting

### 1.1 Generation

- **Template worlds:** no rivers. [V] `generate_regions` (`world_gen.py:76-105`) samples
  templates, and nothing assigns `world.rivers`. `adjacency.SEA_ROUTE_TERRAINS = {"coast",
  "river"}` (`adjacency.py:9`) refers to the scenario terrain `river`, not to river paths.
- **Procedural worlds** (`geography.py:653-695`). [V]
  - Each land cell is one region (`geography.py:318-319`, `region_of = {c: k ...}`), so
    river cell paths are region paths.
  - `downhill[c]` is the lowest neighbour (water cells included) if it is lower than `c`.
  - Flow `0.2 + moisture` accumulates downhill over land, and cells with flow ≥
    `RIVER_FLOW_THRESHOLD = 2.0` (`geography.py:57`) are river cells.
  - Paths are traced source to mouth, sorted longest first. A tributary path is cut at the
    first already-claimed cell (`geography.py:684-694`), so **the confluence region is the
    tributary's last element and lies on both rivers**.
  - Names come from `_name_rivers` (`geography.py:698-709`).
- **Scenarios** (`scenario.py:482-514`). [V]
  - At most 32 rivers. Each step must join adjacent regions.
  - On procedural worlds, scenario rivers replace the generated ones.
  - **There is no check of direction, acyclicity, or a single downstream target per region.**
    [V by absence in `scenario.py:498-509`]
- **Bonuses, applied once per river region, not per river** (`geography.apply_river_bonuses`,
  `geography.py:844-873`): water +0.15 (clamped), carrying capacity x1.2, a fish slot. [V]

### 1.2 Representation

| Where | Form | Ref |
| --- | --- | --- |
| `WorldState.rivers` | `list[River(name, path: list[str])]`, upstream first | `models.py:376-378, 1238-1239` |
| `Region.river_mask` | Python int bitmask, bit i = river i | `models.py:476`; `geography.assign_river_masks` `geography.py:835-841` |
| Native `RegionState.rivers` | sorted `Vec<u16>` from `river_ids_from_mask` (`ffi_constants.py:112`), column `rivers` | `region.rs:55-58`; `agent_bridge.py:455, 625-626` |
| Native `RiverTopology` | `Vec<Vec<u16>>` region-index paths, set once by `set_river_topology` from `configure_ecology_runtime` | `ecology.rs:299-301`; `agent_bridge.py:1041-1049`; persisted (`ecology.rs:1460`) |

Region identity is the index in `world.regions` throughout. River paths are names in Python
and indices natively. [V]

### 1.3 Consumers

| Consumer | Rule | Ref |
| --- | --- | --- |
| Deforestation cascade (Python fallback) | for each river and each region on it with cover < 0.2, every region later on that path loses 0.05 water; a `seen` set de-duplicates (upstream, downstream) pairs across rivers; then a clamp | `ecology.py:1145-1163` |
| Deforestation cascade (native) | identical (`seen: Vec<(u16,u16)>`); step 6 of the tick, after the per-region clamp and before yields | `ecology.rs:866-911, 1156` |
| Goods-economy trade routes | `is_river` = the pair is **consecutive** on a path (`build_river_route_set`) | `economy.py:370-380, 1352-1377` |
| Transport cost | `RIVER_DISCOUNT = 0.5` when on a river | `economy.py:70, 516-540` |
| Merchant graph | `is_river` = the two regions **share any river id** (`_regions_share_river`); barge cargo `RIVER_CARGO_CAP = 5` | `economy.py:1396-1416`; `merchant.rs:259-346, 477-478` |
| Migration | `RIVER_MIGRATION_BONUS = 0.1` if `shares_river` (any common id) | `behavior.rs:32, 334-345` |
| Spatial attractor (where settlements form) | River attractor active if `has_river()`; weight = water | `spatial.rs:241-242, 385` |
| River flood | river region, spring, water > 0.8, 20%, from the shared environment RNG | `emergence.py:920-946` |
| Resources | fish slot at world generation | `geography.py:864-873` |

The settlement and city modules do not read rivers directly
(`settlements.py`, `cities.py`: no hits). [V]

### 1.4 Tributaries, confluences, multiple rivers, double counting

A region can lie on several rivers: a procedural confluence, or any scenario overlap. [V] No
development world has one (`river_topology.txt`, `on_multiple=0`).

| Risk | Status |
| --- | --- |
| River bonuses applied twice to a confluence | **No.** Applied once per region with a non-zero mask (`geography.py:848, 858`). [V] |
| Cascade counting one (upstream, downstream) pair on two rivers | **No.** The `seen` set prevents it (`ecology.py:1150-1158`; `ecology.rs:874-896`). [V] |
| Cascade stacking over several deforested upstream regions | **By design.** Downstream loss = 0.05 x (number of distinct deforested upstream regions). It is unbounded per turn apart from the clamp. [V] Not a double count, but uncalibrated. |
| Tributary deforestation below the confluence | **Under-count.** The tributary path ends at the confluence, so regions below it never see that upstream. [V] |
| Scenario rivers defined in both directions (`[X, Y]` and `[Y, X]`) | **Double count possible.** Pairs (X,Y) and (Y,X) are distinct, both count, and a cycle is not rejected. [V code] [U whether any shipped scenario does this] |
| River edge definitions | **Inconsistent.** The goods economy uses consecutive path pairs; the merchant graph and migration use any shared river id. Two adjacent but non-consecutive regions on one river are a river edge for merchants, not for goods routes. [V] |
| A new flow model stacked on the +0.15 world-generation water bonus | **Risk.** Dynamic river supply would duplicate the static bonus unless the bonus is folded into the opening storage (section 7.2). [I] |

---

## 2. The ecological water value

### 2.1 Range and caps

- Floor 0.10. Caps by terrain [V] (`ecology.py:62-72` Python, `ecology.rs:85-99` native):
  plains 0.70, forest 0.80, mountains 0.90, coast 0.90, desert 0.20, tundra 0.60, steppe 0.50,
  jungle 0.95, marsh 0.95. The plains caps are the fallback for `river`/`hills`.
- Clamped and rounded to 4 decimals: Python `clamp_ecology` (`ecology.py:1302-1312`), native
  `round4` and clamp (`ecology.rs:415-427`).
- Defaults: `TERRAIN_ECOLOGY_DEFAULTS` (`ecology.py:51-60`). Procedural worlds add
  `(moisture - 0.5) x 0.2` (`world_gen.py:509-510`).

### 2.2 Every writer [V]

| Writer | When | Effect | Ref |
| --- | --- | --- | --- |
| World generation | gen | terrain default, procedural moisture tweak | `world_gen.py:101-103, 509-510` |
| River bonus | gen | +0.15 once per river region | `geography.py:861` |
| Scenario override | gen | arbitrary | `scenario.py:353-355` |
| Coastal flood disaster | Phase 1 | +0.1 up to the cap (coast terrain; 3%, x2 in warming) | `climate.py:313-319, 242-247` |
| Drought phase | Phase 9 | −0.04 x exposure x trend (x1.5 if irrigated) | `ecology.py:794-797`; `ecology.rs:722-727` |
| Cooling phase | Phase 9 | −0.02 x exposure x trend | `ecology.py:798-799`; `ecology.rs:728-729` |
| Warming, tundra | Phase 9 | +0.05 | `ecology.py:800-802`; `ecology.rs:730-731` |
| Harvest shock (regional bad year) | Phase 9 | −h x `harvest_shock_water_loss` (0.0667 x trend-derived) | `ecology.py:776-783, 804`; `ecology.rs:733-736`; `climate.py:104-118` |
| Temperate recovery | Phase 9 | +0.03 (not gated by population since the 2026-10 correction) | `ecology.py:806-815`; `ecology.rs:738-745` |
| Irrigation bonus | Phase 9 | +0.03 x pressure multiplier, every phase but drought | `ecology.py:818-821`; `ecology.rs:747-751` |
| Uncontrolled regions | Phase 9 | climate terms only, no irrigation | `ecology.py:1118-1130`; `ecology.rs:754-771` |
| Deforestation cascade | Phase 9, after the clamp | −0.05 per deforested upstream region | `ecology.py:1159`; `ecology.rs:894` |
| Native write-back | Phase 9 | Python water = native result, clamped | `ecology.py:442-481` |

**Not writers:**

- Disease flares only read water.
- The river flood and drought intensification change `capacity_modifier` and soil, not water
  (`emergence.py:933-938, 1001-1009`).
- Phase 1 hazard "drought" changes civ stability and economy plus an `ActiveCondition`
  (`simulation.py:235-252, 1205-1219`).

### 2.3 Every reader [V]

| Reader | Use | Ref |
| --- | --- | --- |
| `effective_capacity` (Py/Rust) | `cc x cap_mod x soil x min(1, water/0.5)` | `ecology.py:81-90`; `ecology.rs:326-334` |
| Crop yields (Phase 2 preview, Phase 9) | crop `ecology_mod = soil x water` | `ecology.py:574-576`; `ecology.rs:1013-1016` |
| Forest regrowth gate | water ≥ 0.3 | `ecology.py:849-853`; `ecology.rs:822-828, 840-845` |
| L3 timber regrowth gate | water ≥ 0.3 | `timber_stock.py:136-139` |
| Disease flares | water < 0.3 (non-desert), or a drop > 0.1 against `prev_turn_water` | `ecology.rs:463-477`; `ecology.py:907-916` |
| Demographic mortality stress | `(0.5 − water)+` | `demographics.rs:158-163` |
| Farmer satisfaction | `0.4 + 0.3 soil + 0.2 water` | `satisfaction.rs:121` |
| River attractor weight | water | `spatial.rs:385` |
| Off-mode overflow migration | via `effective_capacity` | `climate.py:352-420` |
| Hazard drought driver | dryness = 1 − water/cap | `events.py:509-519` |
| River flood / drought intensification | water > 0.8 / water < 0.25 | `emergence.py:929, 994` |
| Nomad pasture, dzud | grass ∝ water/ref; dzud x DZUD_DRY if < 0.25 | `nomads.py:302-303, 798` |
| Scientific claims | water band | `scientific_claims.py:78` |
| Viewer | `history[n].ecology[region].water`, region history line | `models.py:1423`; `viewer/src/lib/regionHistory.ts:48-50` |

`target_occupation_ratio` takes water but ignores it (`satisfaction.rs:287-290`, `_water`).
[V]

### 2.4 Conserved or index?

- Nothing is conserved. [V] Water is a bounded condition index whose terms are climatic rates
  plus a clamp. Water that leaves an upstream region does not arrive downstream. The cascade
  removes water downstream without adding anything anywhere. Floods add water from nowhere.
- Soil and forest cover are indices of the same kind.
- **Conserved quantities that exist today:** L3 timber stock (closed ledger every turn,
  `timber_stock.py`, doc section 3), RS2/PL1 coins and wages (`check_ledger`, docs), and the
  PL1 cut-timber identity.

---

## 3. Infrastructure and existing repair systems

### 3.1 Data model [V]

- `InfrastructureType`: ROADS, FORTIFICATIONS, IRRIGATION, PORTS, MINES, TEMPLES. This is an
  enum declaration order to preserve (`models.py:215-221`).
- `Infrastructure(type, builder_civ, built_turn, active, faith_id, temple_prestige)`
  (`models.py:260-266`).
  - **There is no id, no condition and no owner other than `builder_civ`.** Region
    controllers change.
- `PendingBuild(type, builder_civ, started_turn, turns_remaining, faith_id)`
  (`models.py:289-294`).
- `Region.infrastructure: list`, `Region.pending_build` (`models.py:435-436`). Records are
  appended, and inactive records stay in the list.
- Native: only the bools `has_irrigation`, `has_mines` (persisted) and `has_temple` and
  `temple_prestige` (`region.rs:70, 99-100, 108`). Python fills them from `_has_infra`, which
  reads `active` (`agent_bridge.py:269-275, 615-616`).

### 3.2 Build, complete, destroy [V]

- **BUILD action** (`infrastructure.handle_build`, `infrastructure.py:255-336`).
  - A candidate region is chosen by `stable_hash_int("build_action", ...)` plus sha256. The
    type comes from trait priority (`TRAIT_BUILD_PRIORITY`, `:244-252`), then the cheapest
    affordable type.
  - Cost comes from `BUILD_SPECS` (`:60-67`): roads 10/2 turns, forts 15/3, irrigation 12/2
    (not desert), ports 15/3 (coast only), mines 10/2 (mineral slot), temples 10/3. With
    `--techniques` it is discounted (`techniques.py:1081-1093`).
  - **The civ treasury pays at start** (accumulator `keep`, or direct mutation).
  - Cities build walls from city wealth plus guild help (`cities.py:722-748`).
- **Completion:** `tick_infrastructure` in Phase 2 `apply_automatic_effects`, **after** the
  goods economy (`simulation.py:2185`; `infrastructure.py:164-213`). An irrigation work that
  completes in Phase 2 of turn T first affects the Phase 9 ecology of T, and the arable
  capacity of the T+1 economy.
- **Rebuild:** `valid_build_types` excludes only *active* records of a type
  (`infrastructure.py:117`), so a deactivated work is replaced by appending a new record at
  full cost. There is no repair path.
- **Destroyers:**

  | Cause | Effect | Ref |
  | --- | --- | --- |
  | scorched earth on `region_lost` (sha256 roll) | all active → inactive, pending cancelled | `infrastructure.py:216-241`; `action_engine.py:591, 671` |
  | earthquake disaster (mountains) | one random active record → inactive | `climate.py:295-305` |
  | coastal flood | PORTS → inactive | `climate.py:317-319` |
  | depopulation (`mark_depopulated`) | all → inactive, ruin quality | `exploration.py:179-184` |
  | supervolcano | **`region.infrastructure = []`**: records deleted | `emergence.py:533-536` |
  | militant conquest, temple replacement | temple → inactive | `infrastructure.py:369-392`; `action_engine.py:702-707` |

- **Conquest:** infrastructure persists unless scorched; `builder_civ` is unchanged. [V]
- **River flood:** its event text says "damaging infrastructure", but the code damages
  nothing (`emergence.py:939-945`). This is a narration-versus-state defect. [V]

### 3.3 Effects of the three types Program B targets [V]

| Type | Effect | Ref |
| --- | --- | --- |
| IRRIGATION | water +0.03 x pressure outside drought; drought loss x1.5 (native through the `has_irrigation` bool) | `ecology.rs:722-726, 747-751`; `ecology.py:785-821` |
| IRRIGATION | arable capacity +0.10 (`FARM_CEILING_IRRIGATION`) → `farm_labor_ref` of the diminishing-returns curve | `economy.py:768-784, 787-797` |
| IRRIGATION | agriculture focus score | `tech_focus.py:171-174` |
| (irrigation **technique**, separate) | grain yield +5%, ceiling +10% | `techniques.py:159-163` |
| ROADS | two-hop trade range with road practice (`techniques.extend_trade_routes`) or the railways focus | `techniques.py:1152-1192`; `resources.py:215-222` |
| ROADS | **no** transport cost effect: `INFRASTRUCTURE_DISCOUNT = 1.0` placeholder | `economy.py:72, 539` |
| ROADS | railways and networks focus scores | `tech_focus.py:208-224` |
| PORTS | navigation, commerce and naval focus scores only; maritime does not read the type | `tech_focus.py:161-219`; `maritime.py:221-308` |

**No condition, decay, upkeep or service capacity exists for any of these three types. [V]**

Prevalence in the one development run [V, procedural 7, 32x10, `--agents off`, Python ecology,
200 turns]:

- active at turn 200: irrigation 25, roads 27, fortifications 28, temples 26, mines 7, ports 0;
- inactive: roads 13, irrigation 7, ports 3;
- built over the run: irrigation 33, roads 41, ports 3; scorched earth 12.

Hybrid prevalence is unmeasured. [U]

### 3.4 Existing repair, labour, timber and budget authorities [V from the docs and code listed]

| System | What it does | Labour | Materials | Coins / budget |
| --- | --- | --- | --- | --- |
| Grain storage (`grain_storage.py:35-45`) | granary condition: wear 0.01 a tick, usable capacity = capacity x condition, extra spoilage 0.07 x (1−c); maintain 4 work → +0.10 | anonymous farmer-equivalent work in the native `granary_work_requested` column (`economy.rs:1247-1319`; `ffi/mod.rs:3275-3285`) | 1 timber per work | 2 coins per work from the treasury, which **leave the economy** |
| RS2 `--repair-projects` (`repair_projects.py`; doc) | project per asset below `OPEN_BELOW` 0.75, scope = deficit x work per condition; war damage 0.25 at conquest, sack or seizure; cost-only control | granary: the same column; workshop: named crew, wage 500 milli per work through `transfer_wealth` | free timber = stockpile − merchant commitments + PL1 store | planned against the projected treasury; one charge per civ per turn; prepaid sub-unit; L9 `repairs` envelope (`local_budgets.py:1041`; `repair_projects.py:1376-1400`) |
| PL3 `--recovery-crews` | names granary crews (free adult farmers of the region, veterans first), paid or unpaid | work registry `reserve_work`, category `repair` | — | wages through `transfer_wealth` batch 1 |
| PL3 `--maintenance-obligation` | reserves RS2's planned charges before L9 bargaining | — | — | `Decision.reserved["maintenance"]` |
| PL2 `--operating-wear` | workshop wear while operating (the maintenance assumption) | — | — | — |
| PL1 `--timber-supply` | paid woodcutting expeditions feeding an RS2 store | crew reserved first, away from home | L3 stock debited | wages, recall on unpaid turns |
| L9 `--local-budgets` | one envelope per service per ruler, decided Phase 10 of T for T+1; closure `spent ≤ amount` | — | — | `floor(share x (projected − floor − obligations − committed))` |

**Lessons the docs record:**

- L9 valued maintenance only after failure: 64-67% of repairs proposals were refused
  `no_support` (maintenance-obligation doc, "Why").
- RS1's extra repairs came from its own wear assumption (operating-wear doc, D2).
- 98% of RS2 stalls were `no_timber`, caused by production (timber-supply doc).

Infrastructure condition will meet all three issues.

---

## 4. Forest cover and timber stock

They are distinct quantities. [V]

| | Forest cover (`ecology.forest_cover`, index 0..cap) | Timber stock (L3, `livelihoods.timber_stock`, goods) |
| --- | --- | --- |
| Loss | clearing −0.02 when population > 0.5 x cc in a controlled region (`ecology.rs:807-818`); cooling −0.01 x exposure; wildfire −0.3 (`climate.py:323-327`); supervolcano → 0.05; succession forest→plains → 0.1 (`emergence.py:851-857`) | extraction (economy slot output plus PL1 woodcut, `timber-supply.md` native seam); `cleared = max(0, S − K_eff)` when cover falls (all cover-loss causes lumped together) |
| Gain | regrowth +0.01 x pressure when population is below the threshold and water ≥ 0.3 (`ecology.rs:822-828`); succession plains→forest 0.7 | logistic regrowth `r(S + aK_eff)(1 − S/K_eff)`, r 0.03, a 0.05, gated by water ≥ 0.3 (`timber_stock.py:141-146`) |
| Link | — | `K_eff = K x cover / 0.9` (`timber_stock.py:127-131`) |
| Protection | RS5 suspends population clearing at the native decision point (`ecology.rs:799-830`) | L3 cap; PL1 `GUARD_SHARE` 0.5 |

- **Harvest never changes cover. [V]** The timber-stock doc section 3 says "forest cover,
  soil, yields and every other world field are untouched", and PL1's woodcut only debits the
  stock. Checkpoint 3's out-of-scope list names "harvest-driven cover loss" and
  "infrastructure repair" (`docs/CONTINUATION.md:59-62`). [V]
- **Cover's effects on water today:**
  - the cascade threshold (cover < 0.2), river regions only;
  - nothing else. The cross effect is soil +0.01 when cover > 0.5 (`ecology.rs:856-861`).
- **Water's effect on forest:** the 0.3 regrowth gate for both cover and stock.
- In the development run, 10 of 14 drainage-edge upstream regions had cover < 0.2 at turn 200
  [V, `runs/p7off`, off mode]. None of them is on a river, so the cascade never fired.

---

## 5. Climate, drought and flood

| Mechanism | Where | What | RNG |
| --- | --- | --- | --- |
| Global phase | `climate.get_climate_phase` (`climate.py:36-48`) | 75-turn cycle: temperate, warming, drought, cooling | none |
| Regional harvest shocks | `climate.py:121-200`; native `harvest_shock` column (`agent_bridge.py:731-735`) | clusters of ≤ 3 neighbours; 12-turn good or bad years; crop loss h ∈ [0.2, 0.6]; water −h x 0.0667 | `stable_hash_int("climate.harvest_year", ...)`, pure |
| Trend share | `climate.py:68, 84` | phase crop and water effects at 0.5 | — |
| Latitude exposure | `geography.climate_exposure`; native `climate_exposure` | drought and cooling water and forest losses x band factor (procedural only) | — |
| Disasters | `climate.check_disasters` (`climate.py:242-350`) | earthquake (mountains, deactivates one infra), coastal flood (+0.1 water, ports off), wildfire (−0.3 cover, timber suspended 10), sandstorm (trade routes suspended) | sha256(seed:region:turn:type) |
| Civ hazards | `simulation.py:200-293` | drought hazard (driver = phase x dryness), −stability and economy (signal), `ActiveCondition` drought 3 turns, ongoing −2 stability (guard-shock) | `Random(stable_hash_int("env_hazard", seed, civ, type))` |
| River flood | `emergence._check_flood` (`emergence.py:920-946`) | river region, spring, water > **0.8**: `capacity_modifier` 0.85 for 1-2 turns, soil +0.15 | **shared** `Random(seed + turn x 1013)` (`simulation.py:2004-2006`) |
| Drought intensification | `emergence._check_drought` (`emergence.py:984-1015`) | drought phase, summer, water < 0.25: `capacity_modifier` 0.5 for 4-8 turns, spreading to adjacent deserts | same shared stream |
| Famine | `ecology._check_famine_yield` | reads yields and sufficiency | — |

Findings:

- River floods can fire only where the terrain water cap exceeds 0.8: mountains, coast,
  jungle and marsh. Plains, forest, steppe, desert and tundra river regions can never flood.
  [V from `ecology.py:62-72` and `emergence.py:929`]
- Coastal floods ignore rivers.
- No flood or drought arises from runoff, storage or upstream conditions. [V]

---

## 6. Turn order, RNG and checkpoint state

### 6.1 Turn order (from `simulation.run_turn_result`, `simulation.py:1891-2690`) [V]

| Step | What runs (B-relevant) | Ref |
| --- | --- | --- |
| Turn start | transient flags reset | `:1967-1987` |
| Phase 1 | cooldowns and suspensions decrement, `capacity_modifier` reset when no cooldown; `check_disasters`; off-mode migration; civ hazards | `:165-293` |
| Phase 1 (cont.) | epidemics; black swans (supervolcano); `check_environmental_events` (river flood, drought intensification) | `:1993-2006` |
| Phase 2 | trade routes; storage plan; `build_economy_region_input_batch` (arable capacity reads irrigation); livelihoods `reserve_first` → `prepare_phase2` (RS2/PL3 work column, timber holds; L3 caps; PL1 woodcut); native `tick_economy`; storage finish; livelihoods `finish_phase2` (L3 settle, RS2 pay and credit, PL1) or `rollback_phase2` | `:2008-2180` |
| Phase 2 | `apply_automatic_effects`: `tick_infrastructure` (build completion) | `:2185`; `:299-311` |
| Phases 3-8 | production, finance, technology, **Phase 5 actions (BUILD, war, conquest → scorched earth, RS2 war damage)**, culture, random events, leaders | `:2194-2245` |
| Phase 9 | livelihoods `before_ecology` (RS5 plans) → region sync (`sync_regions` or `set_region_state`) → `tick_ecology` (native or Python; succession, soil floor and post-pass patch inside) → livelihoods `after_ecology` (RS5 settles) | `:2247-2285` |
| Agent tick | wrapped by livelihoods hooks (paid-work receipts) | `:2293-2340` |
| Phase 10 | livelihoods `phase10_before_reserves` (RS2 lifecycle, PL1 need, etc.) → `tick_grain_reserves` → livelihoods `phase10` (L9 settle and decide) | `:2526-2539` |
| Phase 10 tail | temple prestige, tech regression, stress, snapshot | `:1566, 2643-2690` |

`before_ecology` runs **before** the region sync (`simulation.py:2253-2266`), so a Python
change to `Region.ecology` made there reaches the native tick in every mode. [V]
`after_ecology` runs **after** `_tick_ecology_rust` has applied its post-pass patch
(`ecology.py:1290-1292`). A change made in `after_ecology` is therefore stale in native state
until the next sync, and this turn's agent tick reads the stale value. [V]

### 6.2 RNG in these paths [V]

- **Stateless or namespaced:**
  - disasters (sha256);
  - harvest shocks and clusters (`stable_hash_int`);
  - env hazards (`stable_hash_int("env_hazard"...)`);
  - BUILD (`stable_hash_int("build_action")` plus sha256); scorched earth (sha256);
  - river fish (`stable_hash_int("river_fish")`);
  - geography streams.
- **No RNG:** the ecology tick (both runtimes), L3, RS2, PL1, PL3, RS5, L9. The docs state
  "no RNG is drawn".
- **Shared sequential stream:** `check_environmental_events` uses one
  `random.Random(seed + turn x 1013)` across all regions and checks in order. Each check draws
  only when its condition holds (`emergence.py:1048-1074`). **Any change to water levels
  changes which checks draw, and so shifts every later region's locust, flood, collapse,
  drought and recovery draws in that turn.** That is acceptable in an enabled arm. It is a
  reason never to add new draws to this stream.
- Black swans: `Random(seed + turn x k)` for several k (`emergence.py:226-650`).

### 6.3 Checkpoint state relevant to B [V]

- **Python world** (pickled whole):
  - `Region.ecology`, `prev_turn_water`, `capacity_modifier`, `disaster_cooldowns`,
    `resource_suspensions`;
  - `low_forest_turns`, `forest_regrowth_turns`, `infrastructure`, `pending_build`,
    `river_mask`, `geo`, `latitude_band`;
  - `world.rivers`, `world.geography`, `climate_config`;
  - livelihoods sub-states (`livelihoods_state.py:58-79`). Their transient within-turn parts
    are never pickled (RS2 `_turn`, L3 `_offered`).
- **Native:**
  - `RegionState` is persisted (`region.rs:505-519`), including water, `has_irrigation`,
    rivers and `harvest_shock`;
  - `clearing_protection` is the only transient field (`region.rs:520-523`);
  - `EcologyConfig` and `RiverTopology` are persisted (`ecology.rs:1444, 1460`).
  - **Adding a persisted `RegionState` field changes the checkpoint schema fingerprint**;
    transient fields do not (RS5 doc section 2).
  - Because `EcologyConfig` is restored from the checkpoint, any config change a switch makes
    must be re-applied when the switch changes on resume, or such a resume refused.
- `_capacity_modifier_source` is a dynamic attribute set by emergence
  (`emergence.py:937, 1002`). [U] Whether it survives pickling or is read anywhere was not
  checked.

---

## 7. Design proposal for B1-B5

### 7.1 Ownership table (after the change, switches on)

"Flow" means `--watershed-mode flow`. "Cond." means `--infrastructure-condition`.

| Effect | Owner today | Owner after | Old term |
| --- | --- | --- | --- |
| Water climate terms: drought, cooling, temperate recovery, tundra melt, harvest-shock water | native ecology tick (`tick_water_*`) | **watershed** (precipitation and evapotranspiration forcing); native rates set to 0 through `EcologyConfig`/`set_climate_config` | **replaced** in flow; unchanged in record_only |
| Water index value | native tick (plus write-back) | **derived** each turn from watershed storage plus irrigation application (7.2) | replaced in flow |
| Deforestation cascade | `river_cascade` | watershed cover-dependent retention, overflow and baseflow on the drainage graph; `deforestation_water_loss = 0` | **replaced** |
| River +0.15 water bonus | world generation | folded into opening storage at enable; flows decide afterwards | replaced (once, recorded) |
| River capacity x1.2, fish slot, trade discount, barge cap, migration bonus, attractor | world generation, economy, merchant, behavior, spatial | unchanged (presence-based) | kept |
| Irrigation water bonus and drought x1.5 | native through `has_irrigation` | watershed: withdrawal from storage x service; `irrigation_water_bonus = 0` | **replaced** in flow |
| Irrigation arable ceiling +10% | `economy.arable_capacity` | same, x irrigation service | kept, scaled (Cond.) |
| Irrigation technique +5% grain, +10% ceiling | techniques | unchanged | kept (distinct) |
| Coastal flood +0.1 water, ports off | `climate.check_disasters` | unchanged; the water delta becomes a recorded **external** inflow | kept (folded) |
| River flood (water > 0.8) | `emergence._check_flood` | **watershed flood** (overflow beyond channel capacity), consequences through existing fields | replaced in flow |
| Drought intensification, civ drought hazard, disease flares, yields, capacity, satisfaction, mortality stress | existing | unchanged; they read the derived index | kept |
| Forest cover | ecology tick, disasters, succession, RS5 | + harvest gap loss (`--harvest-cover`, B4) at one Python seam | extended |
| Timber stock | L3 | unchanged; consistency rule (7.4) | kept |
| Infrastructure existence (build, active, destroyers) | `infrastructure.py`, BUILD, disasters | unchanged | kept |
| Infrastructure condition and service | none | **infrastructure-condition** package | new |
| Repair labour, timber, coins | RS2 (+ PL3, PL1) | RS2 with new kinds `irrigation`, `roads` | extended |
| Funding | treasury `keep`; L9 `repairs`; maintenance obligation | same envelopes; new relief measure per kind | extended |
| War damage | RS2 (granary, workshop) | + irrigation and roads at the same real events | extended |
| Deaths | demographics, epidemics, famine | unchanged: **no new mortality authority** | kept |

**Conserved after the change:**

- the watershed account (both modes);
- L3 timber;
- RS2/PL3 coins, wages and timber holds;
- delivered work ≤ requested.

**Still indices:** the water index (derived in flow), soil, cover and infrastructure
condition. Condition is state with declared wear and credited repair; work that does not
reach condition (cost_only) is recorded.

### 7.2 Bounded water-flow model (`--watershed`, B2)

**Graph.**

- Source: procedural geography (`world.geography.generator == "procedural"`).
- Rule: each region drains to the lowest land neighbour that is lower (by `geo.elevation`,
  tie broken by lower index). Coastal regions drain to the sea, and a region with no lower
  neighbour is a sink.
- At enable, check that every persisted river step equals the graph. This is
  `drainage.txt`'s check, which held on all 10 development worlds.
- The graph is a forest: elevation strictly decreases along every edge, so it is acyclic.
  - Order: elevation descending, then index. Every region is processed after all its
    upstream regions.
  - **Each unit of water leaves a region by exactly one path. A confluence sums its inflows
    once.** This is the structural guard against counting tributaries twice.
- Template worlds have no elevation: rejected with a clear message (open question 10.1).
  Scenario rivers that fail validation are rejected.
  - Validation: several downstream targets for one region, a reversed duplicate, or a cycle.

**State per region** (float64, water units "wu"; one procedural region ≈ one Voronoi cell of
similar area):

- storage `S ∈ [0, C_eff]`;
- `C_eff = C x (1 + κ x cover)`, so forest soils hold more;
- `last_index`: the index observed after the last write-back.

**Per turn** (declared constants, uncalibrated; all formulas are deterministic and draw no
RNG):

```
P_r  = P0 x (0.2 + moisture_r) x φ(phase, exposure_r, trend, shock_r)  # forcing: replaces the old climate water terms
X_r  = external: (index now − last_index) mapped to wu                  # flow mode: every foreign index writer (coastal flood, scenario) recorded once
I_r  = Σ Q_u over u with down(u) = r                                    # downstream transfer, same turn
A    = S_r + P_r + X_r + I_r
E_r  = min(A, E0 x ψ(phase, terrain) x (1 + τ x cover_r))               # evapotranspiration (losses; forests transpire)
W_r  = min(A − E_r, D_irr x service_r)  if irrigated                    # consumptive irrigation use (upstream/downstream tradeoff)
B    = A − E_r − W_r
Q_r  = k_b x min(B, C_eff) + max(0, B − C_eff)                          # baseflow + overflow
S_r' = B − Q_r          (0 ≤ S_r' ≤ C_eff)
Q_r → I_down(r) | to_sea | sink (lake: evaporates, recorded)
flood_r   = max(0, I_r + P_r − channel_r)        # recorded condition; channel larger on named-river regions
drought_r = S_r'/C below a threshold for N turns # recorded condition
index_r   = floor + (cap_t − floor) x min(1, S_r'/C + α x W_r/C)        # derived view (flow mode)
```

**Closure, checked every turn and raising before commit:**

```
Σ(S' − S) = ΣP + ΣX − ΣE − ΣW − to_sea − sink_loss      (rel. 1e-9, math.fsum)
```

- **Opening:** `S = C x (water − floor)/(cap_t − floor)`. The index is continuous at enable,
  and the river +0.15 bonus is inside it.
- **Forest effect:** more cover means more retention, smaller overflow peaks downstream and
  more dry-season baseflow, but more evapotranspiration. Deforestation upstream gives flashier
  floods and drier droughts downstream. This reproduces the cascade's intent without removing
  water from nowhere.
- **Irrigation:** upstream withdrawals wet the irrigated region's crops (through the index)
  and reduce downstream inflow. Service scales capacity. That is the tradeoff "where it
  arises naturally".
- **Consequences, all through existing authorities, applied in `before_ecology` so that the
  sync carries them:**
  - a flood above a threshold sets `capacity_modifier` 0.85 and a `disaster_cooldowns["flood"]`
    of a duration derived from the excess (no RNG), adds silt to soil, and records condition
    damage for infrastructure (Cond.);
  - droughts act only through the derived index (yields, capacity, disease, migration).
  - Flow mode disables `emergence._check_flood` (the replaced river flood). This shifts the
    shared stream in enabled arms, which is acceptable and must be documented.
- **Derive or keep both? Recommendation: derive, in two stages.**
  1. `record_only`: the old index is untouched. The account runs in parallel, and the derived
     index is recorded beside the observed one. This is how the constants get calibrated:
     headwater regions should reproduce the old index's climate cycle on average.
  2. `flow`: the derived index replaces the native hydrology terms. Every other writer is
     folded in as a recorded external inflow, so no writer is silently lost or stacked.
  - **Alternative, not recommended:** keep the native climate terms and add flow deltas. That
    counts climate twice (local index plus reduced upstream inflow), and the +0.15 static
    bonus stacks on the dynamic supply.
- **Placement: Python, no Rust change.**
  - Cost is O(regions) a turn; at 150 regions it is negligible beside the governance tick.
  - The flow mode needs the native hydrology rates at zero. Every rate already exists in
    `EcologyConfig` (`agent_bridge.py:1064-1093`) and `set_climate_config`. One pinned Python
    edit is enough: `configure_ecology_runtime` merges `watershed.native_ecology_overrides(
    world)` (empty when off).
  - Because `EcologyConfig` is checkpointed, the overrides must be re-applied when the switch
    changes on resume, or such a change refused (the PL1 precedent).
  - The pure-Python ecology fallback (no extension) reads tuning directly in
    `ecology._tick_water`, and `ecology.py` is RS5-pinned. **Flow mode rejects the Python
    fallback.** `record_only` works in any ecology path.
  - A native water model would touch five RS5-pinned files and add persisted `RegionState`
    fields (a schema change). It is not justified by cost.

### 7.3 Infrastructure condition and service (`--infrastructure-condition`, B3)

**Scope.** Irrigation first, then roads. Ports are deferred: there is no consumer, 0 are
active in the development run, and maritime does not read the type. Giving ports a role
(yards, sea cargo) is a maritime design change and needs native `merchant.rs`, which is
pinned.

**State** (`InfrastructureConditionState` under `WorldState.livelihoods`; `models.py`
untouched):

- `InfraAsset(aid, region, kind, record_index, built_turn, builder_civ, opened_turn, condition,
  service, status ∈ {serving, failed, inactive, destroyed}, wear, damage, credited)`;
- `InfraDamage(did, turn, aid, cause ∈ {flood, war, earthquake, scorch, ...}, amount, ref)`;
- `next_aid`, `ledger_turn`, the ledger, counters.

**Stable ids.**

- An `aid` is allocated when a new active record is seen. It is matched each turn by
  `(region, record_index, type, built_turn, builder_civ)`; records are append-only.
- If a record turns inactive, the asset becomes `inactive`, with its cause where a dated
  event names it.
- If the list is wiped (supervolcano), the asset becomes `destroyed`.
- A rebuild gets a new `aid`.
- Conquest keeps the asset; responsibility moves to the new controller with a dated note,
  the RS2 rule.

**Wear and service** (declared):

- wear: irrigation 0.01 a turn (the grain-storage rate), roads 0.005;
- flood damage ∝ excess (B2);
- war damage at RS2's three existing hooks;
- service `s = min(1, condition / 0.5)`;
- condition 0 means `failed`: the record stays `active`, so existence semantics and BUILD are
  unchanged. A failed work must be repaired; it cannot be rebuilt.

**Consumers** (one helper `infrastructure_condition.service(world, region, kind)`, which
returns exactly 1.0 when off):

- irrigation: `arable_capacity` uses `mult += FARM_CEILING_IRRIGATION x s` (`economy.py:783`,
  pinned). `0.10 x 1.0 == 0.10` exactly, so the switch-off path is bit-identical.
- irrigation, index mode: `has_irrigation = active and s ≥ 0.5` (`agent_bridge.py:615`,
  pinned).
- irrigation, flow mode: withdrawal capacity x s (no native involvement).
- roads: the two-hop range rules additionally require `s ≥ 0.5` (`techniques.py:1177`,
  `resources.py:221`; unpinned).
- A road transport discount through `INFRASTRUCTURE_DISCOUNT` would be a **new bonus**. If
  wanted, it needs its own mode, documented as new and not replacing anything.

**Repair, through existing authorities only.**

- RS2 gains kinds `irrigation` and `roads`. Scope = (1 − c) x work-per-condition.
- **Labour:** anonymous farm labour through `granary_work_requested`, or PL3 named crews.
  - The native column already accepts any region's request (`ffi/mod.rs:3275-3285`). The
    package appends it when grain storage is off.
  - Shared regions sum their requests. Delivered work is split in a fixed order (granary
    first, then irrigation, then roads) and recorded.
- **Materials:** timber per work (declared: irrigation 0.25, roads 0.5) from RS2 free timber
  and the PL1 store.
- **Coins:** RS2's charge, with the L9 `repairs` envelope covering the new kinds.
  - The relief measure must exist before failure (food at risk = arable ceiling lost x
    expected output over `HORIZON`). Otherwise the `no_support` failure documented for
    workshops repeats.
- **Maintenance obligation:** reserves the new kinds' planned charges.
- **Stalls:** `no_timber`, `no_coins`, `no_labor`, `no_envelope`. This is the natural
  "underfunded public works" story.
- **Controls:**
  - `record_only`: condition is tracked, service is forced to 1.0, no projects. It should
    equal off except for the record.
  - RS2's `cost_only`.
  - A wear arm without repair: the PL2 lesson, so that repair is measured against the same
    wear assumption.
- **Schema:**
  - RS2's kind `Literal` and the strict viewer reader both need the new kinds. Bump RS2's
    record schema only when a new kind is present.
  - The alternative is a sibling record `livelihoods.infrastructure_works` that reuses RS2
    internals. It keeps the RS2 schema untouched, at the cost of duplication. **The lead
    decides** (open question 10.4).

### 7.4 Forest linkage (`--harvest-cover`, B4)

- **Cover** is canopy area (owned by the ecology tick). **Stock** is wood on that canopy
  (owned by L3). Harvest takes wood. A canopy cut too thin opens gaps.
- **Rule**, at L3 settlement (`finish_phase2`, Python, before the Phase 9 sync):
  - if `S/K_eff < G` (declared 0.3), cover loses `min(rate x (G − S/K_eff), cover −
    cover_supported(S))`;
  - `cover_supported(S) = 0.9 x S/K` keeps `K_eff(new) ≥ S`, so **no standing wood is
    destroyed**, and L3's next `cleared` does not count the same loss again;
  - the loss is recorded as `harvest_cover_loss`.
- Cover regrowth stays with the ecology tick.
- **Downstream outcome:** cover enters `C_eff` and evapotranspiration in the watershed.
  RS5 protection, L3 enforcement and PL1's guard change upstream cover, and so downstream
  storage, floods and droughts, with the account closed: water is moved in time and place,
  never created.
- **Demonstration:** matched arms on development worlds (protection against no protection;
  harvest-cover against record_only). Any protected-woodland example must be labelled
  "constructed".

### 7.5 Viewer history (B5)

- **Records.**
  - `snapshot.livelihoods.watershed` (schema 1): `source_turn`, mode; per region `opening, P,
    X, inflow, E, W, outflow (to_down/sea/sink), closing, index_observed, index_derived,
    flood_excess, drought_turns`; dated `floods` and `droughts` (cause terms: forcing deficit,
    upstream inflow deficit, upstream withdrawals, upstream cover); totals plus closure.
  - The static graph (`down`, order, river membership) is recorded once.
  - `snapshot.livelihoods.infrastructure_condition`: assets (condition, service, status),
    dated damages with cause references, wear.
  - RS2 receipts gain the new kinds.
  - Size: about 14 floats per region-turn, roughly 1 MB of JSON at 32 regions x 200 turns and
    about 5 MB at 150 regions. [I]
- **Panels.**
  - a basin layer on the region map (downstream arrows; cross-civ edges marked);
  - region history lines for storage, both indices, inflow and outflow, and irrigation
    service;
  - an asset table and history;
  - a public-works chain: flood or wear → damage → project → stall reasons → service →
    arable ceiling and yields → L9 grievance, linked by `aid` and `pid` (by id where recorded,
    by region otherwise, as the recovery chain view does);
  - an upstream/downstream panel per civ pair.
- **Strict readers:** absent, malformed, disabled and recorded-zero must stay distinct. The
  existing gap is that five readers conflate absent and malformed; new readers must not.
- **The failed public-works story:** natural if a stalled irrigation project coincides with a
  drought on a development world; otherwise constructed and labelled as such.

### 7.6 Switch names, state, placement, FFI, pins

| Switch | Modes | Requires | State | Placement |
| --- | --- | --- | --- | --- |
| `--watershed` | `record_only` (first), `flow` | procedural geography (or validated scenario rivers, later); `flow`: a native ecology runtime | `WatershedState` (`watershed_state.py`) | Python `before_ecology` (compute, apply) and `after_ecology` (observe the written-back index) |
| `--infrastructure-condition` | `wear`, `record_only` | `--agents hybrid` | `InfrastructureConditionState` | Python: reconcile and wear at Phase 2 finish; service helper; Phase 10 reconcile after BUILD and conquest |
| (RS2 kinds) | RS2 `repair`/`cost_only` | `--repair-projects` + `--infrastructure-condition` | RS2 state, schema extended | RS2 hooks |
| `--harvest-cover` | `loss`, `record_only` | `--timber-stock` | in L3 or a small sibling state | L3 `finish_phase2` seam |
| later: water agreements | — | `--diplomacy` + `--watershed flow` | append treaty kind `water_rights` and grievance kind `water` (append only) | diplomacy (needs D2 attribution) |

**Registry, in the PL1 pattern:**

- append to `LIVELIHOODS_SWITCHES`;
- add a `LivelihoodsState` field;
- add choices and prerequisites in `livelihoods.py`;
- add `feature_catalog.REQUIREMENTS`;
- add `batch_manifest.SIMULATION_ARG_KEYS` and its omit-when-unset tuple, and
  `tests/test_batch_manifest.py`.

**FFI:** none. Flow mode reuses the existing `set_ecology_config`/`set_climate_config`
calls. The repairs reuse the existing `granary_work_requested` column and work registry.

**Pinned files at risk** (`refactor_preflight.py`, `preflight-summary.txt`):

| File | Pins | Needed for |
| --- | --- | --- |
| `src/chronicler/batch_manifest.py` | 18 enforced | every new switch (unavoidable) |
| `tests/test_batch_manifest.py` | 14 enforced | every new switch |
| `src/chronicler/economy.py` | 5 enforced | irrigation service in `arable_capacity`; optional road discount |
| `src/chronicler/agent_bridge.py` | 3 enforced | `has_irrigation` service gate; `configure_ecology_runtime` overrides (flow) |
| `src/chronicler/tuning.py` | 4 enforced | registering tuning keys (optional; the L3 precedent warns "Unknown tuning key") |
| `viewer/src/types.ts` | 5 enforced | record types |
| avoid: `simulation.py` (11), `models.py` (4), `main.py` (9), `run_checkpoint.py` (4), `grain_storage.py` (2), `grain_reserves.py` (9), `ecology.py` (1, RS5), `ecology.rs`/`region.rs`/`ffi/ecology_sim.rs`/`ffi/batch.rs` (RS5), `ffi/mod.rs` (15), `economy.rs` (6), `merchant.rs` (1) | | the proposal needs none of them |
| digest-only (read the test before editing): `exploration.py`, `tech_focus.py` | performance and reference-baseline provenance | |
| unpinned (references only): `infrastructure.py`, `climate.py`, `emergence.py`, `geography.py`, `repair_projects.py`, `repair_projects_state.py`, `local_budgets.py`, `maintenance_obligation.py`, `recovery_crews.py`, `timber_stock.py`, `timber_supply.py`, `clearing_protection.py`, `livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py`, `resources.py`, `techniques.py`, `action_engine.py`, `household_retail.py`, `war/occupation.py`, `cities.py`, viewer `repairProjects.ts`, `regionHistory.ts`, `RepairProjects.tsx`, `RecoveryChain.tsx` | | |

`tests/test_geography.py` pins `generate_world` JSON digests. A helper added to
`geography.py` that changes no output is safe; recheck it.

**Compatibility matrix to register and test:**

- `--watershed` on a template world, or `flow` without an extension → error.
- `--infrastructure-condition` with `--agents off|shadow|demographics-only` → error (first
  slice).
- Changing either switch's mode on resume without the explicit `--no-<switch>` → error.
- `record_only` of both switches with every other switch on → identity of everything except
  the records.
- All-enabled checkpoint cases: `flow` + condition + RS2 + PL3 + L9 + maintenance obligation +
  PL1 + RS5 + harvest-cover.

---

## 8. Smallest first slice (the "initial watershed/infrastructure slice")

Two PR-sized parts, in order. Part A alone is the minimal slice if the lead wants it smaller.

### S1-A: watershed foundation, `--watershed` mode `record_only` only

- Graph construction and validation at enable: procedural only; template rejected with a
  clear message.
- `WatershedState` (graph, storage, `last_index`, ledger, totals, flood and drought records).
- The per-turn account in `before_ecology`/`after_ecology`, with closure checks. **No world
  field changes; no RNG.**
- Snapshot record; viewer reader, panel and region-history lines (index observed against
  derived).
- **No pinned edits except the registry pins.** No native change.

### S1-B: irrigation condition, `--infrastructure-condition` (`wear`, `record_only`) with RS2 kind `irrigation`

- Asset registry with stable ids, wear, the service helper, and the two pinned consumer edits
  (`economy.arable_capacity`; `agent_bridge` `has_irrigation`).
- RS2 kind `irrigation`:
  - labour through the work column, or PL3 crews;
  - timber and coins;
  - the L9 envelope plus a relief measure;
  - the maintenance-obligation planned cost;
  - war damage at conquest.
- Viewer: asset table, RS2 kind support, the chain link.

### Test plan

**Offline unit tests** (a new chunk with headroom; under 110 s):

- **Graph.**
  - The rebuilt drainage reproduces every persisted river step (all 10 development
    procedural worlds, plus synthetic cases).
  - Each region has exactly one destination; topological order; acyclic.
  - Confluence inflow = Σ tributary outflow.
  - Scenario-river validation rejects reversed duplicates, cycles and multiple downstream
    targets.
  - Template rejected with its message.
- **Account.**
  - Closure every turn (rel. 1e-9).
  - Bounds 0 ≤ S ≤ C_eff; non-negative flows.
  - Determinism: patch `random` to raise.
  - **record_only mutates nothing:** deep-compare the world before and after the hooks,
    excluding the record.
  - A turn settles once. A failed ecology tick leaves no settled ledger, and the next turn
    settles cleanly.
  - Multi-turn consumption and reset of any transient field (the AGENTS.md rule).
- **Assets.**
  - A build completion opens an asset at condition 1.
  - Scorch, earthquake, coastal flood and depopulation → `inactive` with a cause.
  - Supervolcano → `destroyed`. A rebuild gets a new `aid`. Conquest keeps the asset with a
    note.
  - `service(...) == 1.0` exactly when off. `arable_capacity` is bitwise-identical when off.
    The `has_irrigation` column is identical when off.
- **RS2 kind.**
  - Open, scope, pro-rata credit, cap waste, cost_only, controller inheritance, abandonment.
  - Shared work column: granary-first split, closure of delivered ≤ requested.
  - Stalls: `no_envelope`, `no_coins`, `no_timber`, `no_labor`.
  - Ledger closure (charged x 1000 + prepaid identity).
  - `household_retail.check_farm_labour` holds with irrigation crews present: named farm time
    is included in the removal sums.
- **Readers.**
  - Viewer readers are strict: absent, malformed, disabled and zero stay distinct.
  - A historical bundle (no records) still loads.

**Native suite** (fresh extension in the lead's venv): the hybrid RS2 irrigation kind with
PL3 crews and grain storage on and off, so the column is appended when absent. Verify the
real compiled submodule.

**Identity:**

- Feature-off `turn_speed_identity` against **`8abc1acb` and the preceding integrated main**
  (the 9 standard cases).
- `record_only` (both switches) against off on development worlds: bundles equal except
  `livelihoods.*` records, the manifest and tuning. Cases: procedural 7, 11, 13, 303; template
  for condition only.

**Checkpoint/resume** (`scripts/checkpoint_identity.py`, a hybrid procedural all-switch
case):

- resume points while an irrigation project is open with scope partly delivered, across a
  stall, across a controller change, and on the turn condition crosses the service gate;
- watershed storage mid-cycle (drought into temperate).

**Refused resumes, with explicit errors:**

- a mode change without `--no-…`;
- a template world;
- a legacy JSON state-file continuation that would skip the hooks (the recorded limit:
  reject or document it);
- `flow` without an extension.

**Development measurements** (procedural 7, 11, 13, 17, 21, 31, 302, 303 and template 1, 3,
7, 9, 11, 23, 42 for condition; 200 turns; no held seeds):

- activation: assets, projects, stalls by reason, condition distribution;
- watershed magnitudes: derived against observed index; floods and droughts per world;
- timing pilot to set compute ceilings.

**Viewer:** tests, lint, build; browser QA on a development world (desktop and phone).

---

## 9. Dependencies on other programs

- **Program A.**
  - **A1-A2 (accounting):**
    - RS2 and grain-storage material coins (2 a work) leave the economy, an unexplained sink
      in A1's terms;
    - B3 repairs must not add sinks A1 has not classified. Prefer paid crews (PL3) and
      market purchases of materials (A4) over new coin sinks;
    - if A1 introduces a spendable balance, public-works wages must use it.
  - **A3:** workshop crews share the work registry and timber with repairs. Placement order
    in Phase 2 (`reserve_first`, then the planners) must include the new kinds.
  - **A4:** timber-poor regions need supply for repair materials. Cross-civ timber trade was
    out of scope at checkpoint 3.
  - **A5:** infrastructure persists through conquest; the owned-stock lifecycle rules
    (exactly once) apply to RS2 war damage and the new kinds.
  - **A6:** livelihood decisions could later respond to irrigation service. Avoid
    duplicating labour.
- **Program C.**
  - Disease flares already read water (< 0.3, drops > 0.1). A volatile derived index would
    raise flares through the existing authority, not through a new one.
  - C2 sanitation could read the watershed. The epidemic system keeps disease deaths.
- **Program D.**
  - War damage to infrastructure at the existing RS2 hooks; scorched earth stays existence.
  - D2 attribution (actor, victim, cause) is a prerequisite for upstream/downstream
    grievances and water agreements. In the development run, 11 of 14 drainage edges crossed
    civ borders at turn 200 [V, off mode]. D4 reconstruction of infrastructure uses RS2.
- **Program E:** turn-order table, schemas, witness layers, feature catalog, compact codecs
  for the per-region-turn records, the chain view links, checkpoint identity cases. All are
  owned by the lead.
- **Native venv:** only the S1-B native suite and the identity and checkpoint runs need it.
  No native build changes are proposed.

## 10. Open questions for the lead or owner

1. **Template worlds:**
   - (a) accept a procedural-only watershed (the screens' template stratum has no
     watershed);
   - (b) a declared, labelled terrain-rank drainage heuristic (it fabricates geography);
   - (c) scenario-defined rivers only.

   Recommendation: (a), recorded as an intentional boundary.
2. Flow mode needs one pinned edit in `agent_bridge.configure_ecology_runtime`, plus refusal
   or re-application on resume because `EcologyConfig` is checkpointed. Accept?
3. In flow mode, should `emergence._check_flood` be disabled (replaced)? It shifts the shared
   environment-event stream in enabled arms only.
4. RS2 new kinds (a schema extension plus the viewer) or a sibling `infrastructure_works`
   record?
5. Roads: is a transport discount (a new bonus, its own mode) wanted, or only range gating by
   service?
6. Ports: defer, or design a maritime role (native, pinned)?
7. Constants: all declared and uncalibrated. Calibrate the watershed's P0, E0, κ, τ, k_b and
   channel from `record_only` against the old index's cycle on development worlds only?
8. `harvest-cover` threshold G and rate: declared. Should cover lost to harvest feed L3's
   `cleared` attribution separately (needs an L3 record field)?
9. The L9 relief measure for irrigation and roads (food at risk, trade lost): who owns the
   cross-constituency valuation?

## 11. Recorded limits and defects found (to carry and classify)

| # | Item | Class | Evidence |
| --- | --- | --- | --- |
| 1 | Rivers absent in template worlds and rare at 32x10 procedural | intentional boundary today / evidence gap for B | `river_topology.txt` |
| 2 | River flood text claims infrastructure damage, but none is applied | defect (narration against state) | `emergence.py:939-945` |
| 3 | River floods impossible on plains, forest, steppe, desert and tundra (caps ≤ 0.8) | missing capability | `ecology.py:62-72`; `emergence.py:929` |
| 4 | Cascade −0.05 per upstream region exceeds +0.03 recovery and pins the downstream floor | uncalibrated; possible defect | `ecology.rs:866-911` [I] |
| 5 | Tributary cascade stops at the confluence | defect (under-count) | `geography.py:686-694` |
| 6 | River edge definition differs between goods routes and the merchant graph | defect (inconsistency) | `economy.py:370-380, 1396-1404` |
| 7 | Scenario rivers not validated for direction or cycles | missing check | `scenario.py:498-509` |
| 8 | Roads give no transport discount (placeholder) | missing capability | `economy.py:72` |
| 9 | PORTS type has no maritime role and is destroyed by coastal floods | missing capability | `maritime.py`; `climate.py:317-319` |
| 10 | No condition, upkeep or repair for any infrastructure; inactive records accumulate | missing capability | `infrastructure.py:164-213` |
| 11 | Supervolcano deletes infrastructure records (an identity break for anything keyed to them) | intentional, but needs handling | `emergence.py:535` |
| 12 | Irrigation raises drought water loss x1.5 while its +0.03 x pressure gain is mostly clipped at the cap in temperate turns; it may be net-negative for water over a cycle | possible design defect | [I] `ecology.rs:722-751` |
| 13 | `after_ecology` writes are stale in native state for this turn's agent tick | contract note | `simulation.py:2283-2285`; `ecology.py:1290-1292` |
| 14 | Shared sequential RNG for environmental events | contract note | `simulation.py:2004-2006`; `emergence.py:1048-1074` |
| 15 | Infrastructure prevalence measured only in off mode on one world | evidence gap | `runs/p7off` |

---

### Appendix: files written by this lane

All under the audit session's scratch directory (2026-11-06; not retained in the repository):

- `AUDIT-B.md` (this file)
- `scripts/river_topology.py`, `river_topology.txt`: river counts and topology (world generation only)
- `scripts/drainage.py`, `drainage.txt`: drainage graph rebuild and river reproduction check
- `preflight.json`, `preflight2.json`, `preflight-summary.txt`: read-only refactor preflight
- `runs/p7off/`: procedural 7, 32x10, off mode, 200 turns (`output/state.json`, bundle, logs)
