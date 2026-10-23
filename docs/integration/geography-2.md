# Geography 2.0: procedural worlds, sea zones and wide adjacency

Branch `feat/geography-2` (base `integrate/wave-1` @ `1282630`).

## What changed

| Area | Before | Now |
| --- | --- | --- |
| Regions | 12 hand-written templates, uniform-random x/y, asking for more raised | Procedural generator above 12 regions (or `--worldgen procedural`): heightmap + raster Voronoi cells, real neighbours |
| Civilizations | 6 templates; `--civs 10` silently gave 6 | Procedural civs whenever templates cannot honor the request; `--civs N` gives N or fails clearly |
| Sea | every coast/river/maritime region adjacent to every other (clique) | named sea zones (not ownable) and local sea lanes; clique kept for template worlds |
| Native adjacency | `u32` adjacency/river bitmasks, max 32 regions | sorted `Vec<u16>` lists, any `u16` region count |
| Terrains | plains, mountains, coast, forest, desert, tundra (+ scenario hills/river) | + steppe, jungle, marsh (Python and Rust tables); procedural worlds also use hills |
| Climate | global phase only | `latitude_band` per procedural region scales climate-driven ecology losses and disaster odds |

## Generator (`src/chronicler/geography.py`)

All randomness comes from namespaced streams
`random.Random(stable_hash_int("geography", seed, <stream>, ...))`
(`sites`, `continents`, `noise/<field>`, `latitude`, `capacity`,
`names/<kind>`, `civ_starts`, `civ_expansion`, `civ/<k>`); there is no module
RNG and generator floats are quantized to 6 decimals before comparisons so
libm last-ulp differences cannot flip a tie.

1. **Sites**: a jittered grid of `ceil(regions / 0.5)` cells over the 100 x 100
   map (`cols = ceil(sqrt(cells))`).
2. **Heightmap**: 4-octave value noise + `1 + regions // 30` (max 7) continent
   Gaussian bumps - an edge falloff. The `regions` highest cells are land, so the
   land count is exact; the rest is water.
3. **Neighbours**: each pixel of a 6 px/cell raster belongs to its nearest site
   (the jittered grid bounds the search to the 5 x 5 surrounding cells); two
   cells are neighbours when their areas share at least 2 pixel edges.
4. **Climate**: latitude runs pole to pole along y (span 2.2-2.5 with a seeded
   offset, clipped to [-1, 1]); temperature = `1 - 1.05|lat| - 0.3 elevation
   rank + noise`; moisture = latitude belts (`cos(3 pi |lat|)`: wet equator and
   mid-latitudes, dry subtropics and poles) + distance from water + noise.
   `latitude_band`: 0 equatorial (<0.15), 1 tropical (<0.35), 2 temperate
   (<0.6), 3 subpolar (<0.8), 4 polar.
5. **Terrain** from elevation rank x moisture x temperature: mountains (top
   10 %), tundra (cold), hills (next 13 %), desert/steppe (dry), jungle (wet and
   hot), marsh (wet lowland), forest, plains; low coastal plains/steppe become
   coast. Carrying capacity is a terrain base +-6 + moisture, 12..80 before the
   river bonus.
6. **Rivers**: each land cell drains to its lowest neighbour; rain-weighted flow
   (`0.2 + moisture`) accumulates downhill; cells with flow >= 2.0 are river
   cells. Paths run source to mouth (upstream first, as the ecology cascade
   expects); longest first, tributaries stop at the confluence region so they
   share it. Masks and the M35a bonuses (water, capacity x1.2, fish slot) use the
   same code as scenario rivers (`geography.apply_river_bonuses`, moved verbatim
   from `scenario.py`).
7. **Water**: connected water bodies are `ocean` (touch the map edge), `sea`
   (enclosed) or `lake` (<= 3 cells); oceans and seas are split into zones of
   about 7 cells (farthest-point seeds + BFS). Coastal regions bordering a zone
   get sea lanes to their 2 nearest same-zone coasts within 2.6 grid spacings.
   Remaining land masses are joined by the shortest crossing on a shared water
   body (nearest pair overall as a fallback), so every region is reachable.
   Sea lanes are ordinary entries in `Region.adjacencies` (armies, trade,
   migration use them exactly like the template sea routes) and are listed in
   `WorldState.geography.sea_lanes` for future naval logic.
8. **Roles** (`classify_procedural_roles`): `classify_regions` would call
   nearly every Voronoi region a crossroads (3+ neighbours). Procedural worlds
   use frontier (<= 2 neighbours), chokepoint (articulation point, land-mass
   crossing endpoint, or top-5% betweenness bottleneck above twice the mean),
   crossroads (>= 7 neighbours), standard otherwise (150 regions: ~8
   chokepoints, ~10 crossroads).

### Latitude and climate

`geography.climate_exposure(band, phase)` multiplies the climate-driven
ecology losses in both ecology ticks (Python `_tick_water`/`_tick_forest` and
the uncontrolled path; Rust `tick_water_*`/`tick_forest_*` via
`RegionState.climate_exposure`):

| phase | equatorial | tropical | temperate | subpolar | polar |
| --- | --- | --- | --- | --- | --- |
| drought (water loss) | 0.8 | 1.4 | 1.0 | 0.7 | 0.5 |
| cooling (water loss, forest damage) | 0.4 | 0.7 | 1.0 | 1.4 | 1.8 |

Recovery and warming are unscaled. `climate.check_disasters` multiplies flood
(1.4 .. 0.6 from equator to pole), wildfire (peak tropical) and sandstorm
(peak tropical) odds by band. Regions without a band (template worlds) use
exactly 1.0.

Names come from eight small phonologies (maritime, steppe, mountain, forest,
desert, jungle, marsh, tundra) chosen by terrain, plus terrain suffixes
("Plains", "Fen", "Peaks", ...); seas ("the X Sea", "the Gulf of X", "Lake X")
and rivers ("the X River") are unique per world.

Measured generation time (pure Python): 13 regions 6 ms, 64 regions ~20 ms,
150 regions ~45 ms.

### Persisted data

* `Region.latitude_band: int | None` and `Region.geo: RegionGeography | None`
  (elevation, moisture, latitude, coastal, bordering sea zones).
* `WorldState.geography: WorldGeography | None` (generator, version, cells,
  sea zones with coastal regions and neighbour zones, sea lanes).

All three are omitted from serialized output while `None`
(`model_serializer` wrappers like the governance and campaign fields), so
template worlds keep their exact bytes and need no
`scripts/third_wave_controls.py` registration.

## Procedural civilizations (`world_gen.generate_procedural_civilizations`)

Used when the world is procedural or when more than the six templates are
requested. `check_civ_request` rejects fewer than 1, more than 254 (see below)
or more civs than regions, with the reason in the message.

* **Capitals**: greedy farthest-point sampling on hop distance (first pick a
  seeded choice among the top quarter by capacity; tundra/desert/mountains only
  if needed); about half the civs also get the best free neighbouring region.
* **Identity**: home-terrain phonology -> civ name (`"Kethani Empire"` or
  `"Kingdom of Varn"` style) and a 24-name `leader_name_pool` (scenario-style
  custom pool, so later rulers keep the culture); polity form from terrain and
  trait; founding title from the form (always one of `leaders.TITLES`).
* **Values / domains / trait**: two non-opposed values from the 12-value pool,
  terrain-weighted; first domain maps to a leader archetype; any trait.
* **Stats**: the template ranges (population 30-70, military 20-70, ...),
  population split by effective capacity with the shared P4 helper.

## Native runtime (`chronicler-agents`)

* `RegionState.adjacency_mask: u32` -> `adjacency: Vec<u16>`;
  `river_mask: u32` -> `rivers: Vec<u16>`; both sorted and deduplicated.
  The three neighbour walks in `behavior.rs` iterate the list (same ascending
  order as the old bit walk); the river test is
  `RegionState::shares_river` (two-pointer intersection, equal to
  `mask & mask != 0`); the spatial river attractor uses `has_river()`.
* Arrow: `set_region_state` reads `List<UInt16>` columns `adjacency` and
  `rivers`; the legacy `adjacency_mask` / `river_mask` `UInt32` columns are
  still accepted and decoded in bit order (`read_region_id_lists`).
* `Terrain` gains `Steppe = 6, Jungle = 7, Marsh = 8` (append only);
  `TERRAIN_CAPS` and `TERRAIN_COST` rows mirror the Python tables.
* `RegionState.climate_exposure: f32` (default 1.0) from the optional
  `climate_exposure` column multiplies drought water loss and cooling water /
  forest losses in the ecology tick (both simulators). Exposure 1.0 is exact,
  and the column is only sent for procedural worlds.
* Python bridge: `build_region_batch` drops the 32-region check (limit is now
  the uint16 id space) and calls `ffi_constants.check_civ_capacity`.

## Civ id guard

Civ ids are `u8` with 255 = none and civ records are never removed
(secessions/restorations append). `ffi_constants.MAX_CIV_RECORDS = 254`;
world generation rejects larger requests and `build_region_batch` raises
`ValueError("World has N civilization records but the native runtimes support
at most 254 ...")` before any id could wrap.

## Flags

* `--worldgen {auto,template,procedural}` (CLI, `checkpoint_replay`, live
  `params["worldgen"]`; batch runs inherit it). `auto` (default): templates for
  <= 12 regions, procedural above. `template` above 12 still raises the old
  error.
* `--regions N` above 12 now works (procedural); `--civs N` is honored.
* Scenarios: on template worlds unchanged. On procedural worlds the generated
  graph is kept (renamed regions are renamed everywhere, explicit scenario
  adjacencies are merged and symmetrized), generated rivers are kept unless the
  scenario defines rivers (which then replace them).

## Big-world scaling fixes

* `intelligence.border_pairs` + `compute_accuracy(..., borders=)`: the
  per-turn snapshot computed accuracy for every civ-record pair with an
  O(regions) border scan each (O(records^2 x regions)); now one pass.
  Identical output (equivalence test; default artifacts byte-identical).
* `adjacency.graph_distances_from`: governing costs run one BFS from the
  capital instead of one per owned region. Identical output.
* Procedural worlds only: `TurnSnapshot.relationships`, `per_pair_accuracy`
  and `perception_errors` list living civs only. Civ records are never
  removed and secessions accumulate (150 regions x 30 civs, off, 200 turns:
  81 records, 29 alive), so the all-records matrices dominated the bundle
  (132 MB -> 64.5 MB for that run). Template worlds keep every record.

## Evidence (this branch, Linux, Python 3.13, shared 4-core host)

Base `integrate/wave-1` @ `1282630`; base outputs were produced from an
exported copy of the base tree and its own compiled extension.

* `pytest -q -m "not slow" -n 2`: base 5228 passed / 3 skipped (+2 viewer
  fixture tests that failed only because the exported base tree omitted
  `viewer/`); branch 5267 passed / 3 skipped (adds `tests/test_geography.py`,
  updated terrain-set and bridge tests).
* `cargo test` (all crate tests, including adjacency-list, river
  intersection, append-only terrain, climate-exposure and a 64-region tick
  that migrates agents between regions >= 32): all pass.
* Identity, default worlds, seeds 42 / 7 / 1234, `--agents off` 300 turns
  and `--agents hybrid` 200 turns: every artifact (chronicle, state,
  bundle minus `generated_at`, memories, agent events) byte-identical to
  base, re-checked after every behaviour-touching commit.
  `generate_world` JSON for seeds 42/7/1234 x (8,4), (12,6), (5,3) identical
  (three digests pinned in `tests/test_geography.py`).
* Subset gate (`m53b_run_validation.py --profile subset`, 20 seeds x 200
  turns hybrid): all 20 seeds' artifacts byte-identical to base;
  `validation_compare`: NO REGRESSION, all metric deltas 0.0. Gate PASS on
  both; informational regression oracle FAIL (`terminal_population_extinction`)
  on base and branch alike (pre-existing).

### Big worlds (seed 7, 200 turns, `--simulate-only`)

Wall ms/turn is the mean over turns (excluding world generation and the final
bundle write) on a host shared with other jobs (load ~6-8 on 4 cores); CPU
ms/turn is process time.

| regions x civs | mode | wall ms/turn (median, p95) | CPU ms/turn | run s | bundle MB | civ records / alive | battles | merchant trips |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 64 x 16 | hybrid | 87 (76, 198) | 83 | 19.5 | 26.5 | 18 / 8 | 36 | 14,276 |
| 64 x 16 | off | 65 (58, 125) | 61 | 14.9 | 26.3 | 41 / 14 | 69 | - |
| 100 x 24 | hybrid | 157 (137, 326) | 151 | 34.8 | 46.1 | 49 / 32 | 85 | 19,549 |
| 100 x 24 | off | 154 (144, 299) | 150 | 34.9 | 58.6 | 73 / 33 | 91 | - |
| 150 x 30 | hybrid | 239 (212, 469) | 235 | 52.5 | 67.7 | 54 / 37 | 63 | 19,872 |
| 150 x 30 | off | 174 (156, 316) | 168 | 38.8 | 64.5 | 81 / 29 | 128 | - |

All runs finished; wars, battles, sieges, treaties, annexations and
secessions occur at every size; trade routes and native merchant trips run;
rivers 2-7 and sea zones 10-22 per world. Hybrid population still collapses
late in the run (total population 83 at turn 200 for 150 x 30) - the
same pre-existing extinction trend the regression oracle reports on default
worlds (base default hybrid worlds end at population 0).

Bundle composition at 150 x 30 hybrid: history 38 MB (civ_stats 14.4,
perception_errors 6.8, relationships 5.6, per_pair_accuracy 3.0, ecology 2.7),
world_state 15.5 MB, events_timeline 13.8 MB (the events timeline is written
twice: top level and inside world_state). Region-driven parts (ecology,
region_control, cultural identity, settlements) are about 30 KB per turn.

cProfile of 150 x 30 hybrid, 200 turns (profiler roughly doubles times), top
cumulative per turn: governance tick 75 ms (`_tick_civ` 69, elite metrics 23),
perceived-stat reads 29, Arrow `to_pylist` 24, economy reconstruction 23,
`graph_distance` 18 (now partly removed: governing costs), culture drift 18,
trade-knowledge sharing 17, `build_region_batch` 17, trade routes 13. None of
the Geography 2.0 code paths is O(regions^2); world generation takes
~45 ms at 150 regions and ~0.8 s at 1,000 regions.

## Known gaps

* Hybrid late-run population collapse (pre-existing; another branch owns it).
* Bundles still grow with civ records x turns (`civ_stats` keeps every record
  each turn) and `events_timeline` is stored twice; a delta/compact history
  format needs a viewer change.
* 254-civ guard: long big-world hybrid runs accumulate secession records
  (~0.3-0.5 per region per 200 turns); a 150-region world could reach 254
  records in ~500+ turns and then stops with the clear error. Recycling dead
  civ ids would need a model/FFI change.
* Belief ids are u8 too (one faith per civ plus schisms); not guarded here.
* Sea zones are metadata; armies, trade and migration treat sea lanes as
  ordinary edges (as the template sea routes always were). No naval movement,
  ports-on-zones or zone control.
* `hills` keeps the plains effects/ecology/climate it has for scenarios
  (only resources and transport cost differ); procedural hills therefore
  play like plains with more ore and stone.
* The viewer's `RegionMap` colours `mountains`, `marsh` and `hills` grey
  (its table uses `mountain`/`swamp`); no viewer change was made.
* The scenario 32-river cap remains (scenario-only; the native side no longer
  needs it).
* Big-world balance (civ spacing, river density, chokepoint share, sea-lane
  range) is illustrative, not fitted to any gate.
