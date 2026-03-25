# M56a: Settlement Detection — Design Spec

> Date: 2026-03-25
> Status: Draft
> Depends on: M55a (Spatial Substrate), M55b (Spatial Asabiya) — both merged
> Phase: 7 (Scale Track)
> Scope: Detection, persistence, naming, dissolution, diagnostics. No mechanical effects.

---

## 1. Overview

M56a detects and persists settlement structure from the spatial clustering pressure created by M55a. Settlements are **detected, not created** — M55a's attractor drift, density attraction, and repulsion forces produce spatial hotspots; M56a labels, tracks, and names them.

This milestone is detection-only:
- No Rust changes.
- No per-agent settlement flags or `is_urban` signals.
- No mechanical effects on satisfaction, economy, culture, or behavior.
- No new behavior modifiers.

M56b owns all mechanical wiring. M56a defines the contract M56b will consume: stable settlement IDs, region linkage, geometry, lifecycle state.

### Scope boundary

| In-scope | Out-of-scope (M56b+) |
|----------|----------------------|
| Settlement detection cadence + clustering | Urban/rural behavior split |
| Candidate persistence and anti-flicker inertia | Per-agent Rust settlement flags |
| Stable settlement identity lifecycle | Satisfaction/economy modifiers |
| Python-side data model + storage | Bundle/viewer contract changes beyond snapshot summary |
| Diagnostics for validation | Narrator integration for settlement events |
| Minimal founding/dissolution events | New causal patterns |

---

## 2. Data Model

### 2.1 Settlement (new Pydantic model in `models.py`)

```python
class SettlementStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"  # tombstone only

class Settlement(BaseModel):
    settlement_id: int = 0                    # Globally unique, never reused. 0 = unassigned (candidate).
    name: str = ""                            # "{region_name} Settlement {seq}", immutable once assigned. "" = unassigned (candidate).
    display_name: str | None = None           # Reserved for M56b/narrator enrichment
    region_name: str
    founding_turn: int = 0                    # Turn of promotion to active. 0 = not yet promoted (candidate).
    last_seen_turn: int
    dissolved_turn: int | None = None         # Set on tombstone creation
    population_estimate: int = 0
    peak_population: int = 0
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    status: SettlementStatus = SettlementStatus.CANDIDATE
    # Active/dissolving lifecycle state (dropped on tombstone)
    inertia: int = 0
    grace_remaining: int = 0
    # Candidate tracking
    candidate_passes: int = 0                 # Consecutive detection passes as candidate
```

### 2.2 WorldState additions

```python
# Persisted fields (survive save/load)
dissolved_settlements: list[Settlement] = Field(default_factory=list)
next_settlement_id: int = 1
settlement_naming_counters: dict[str, int] = Field(default_factory=dict)  # region_name -> next seq
settlement_candidates: list[Settlement] = Field(default_factory=list)      # Candidate bookkeeping

# Transient (dynamic attribute, not serialized — same pattern as _agent_snapshot, _economy_result)
# Set via: world._settlement_diagnostics = {...}
# Read via: getattr(world, '_settlement_diagnostics', None)
```

- `next_settlement_id` is a monotonic allocator. IDs are globally unique across all regions, never reused even after dissolution.
- `settlement_naming_counters` maps region names to the next unused sequence number for that region. Never-reused: dissolved settlement names are not recycled.
- `settlement_candidates` is persisted so mid-run save/load preserves candidate promotion timing.

### 2.3 Region additions

```python
# On Region model
settlements: list[Settlement] = Field(default_factory=list)  # Active + dissolving only
```

Follows the existing pattern of `Region.ecology`, `Region.stockpile`, `Region.asabiya_state`.

### 2.4 Storage split

| Container | Contents | Persisted |
|-----------|----------|-----------|
| `Region.settlements` | Active + dissolving settlements | Yes |
| `WorldState.settlement_candidates` | Candidate settlements (not yet promoted) | Yes |
| `WorldState.dissolved_settlements` | Tombstones (`status=DISSOLVED`) | Yes |
| `world._settlement_diagnostics` | Per-pass detection diagnostics | No (dynamic attr, same pattern as `_agent_snapshot`) |

---

## 3. Detection Algorithm

### 3.1 Grid-based density clustering

Detection runs Python-side from `world._agent_snapshot` (Arrow RecordBatch with `id`, `region`, `x`, `y` columns).

**Detection grid:** 10×10 per region, same `[0, 1)` coordinate semantics as Rust's `SpatialGrid` (`spatial.rs:7`). Grid cell `(cx, cy)` for position `(x, y)`:

```python
cx = min(int(x * GRID_SIZE), GRID_SIZE - 1)
cy = min(int(y * GRID_SIZE), GRID_SIZE - 1)
```

Where `GRID_SIZE = 10`.

**Dense cell rule:** A cell is dense if its agent count exceeds:

```python
threshold = max(DENSITY_FLOOR, region_agent_count * DENSITY_FRACTION)
```

- `DENSITY_FLOOR`: absolute minimum agents per cell to qualify as dense. [CALIBRATE M61b]
- `DENSITY_FRACTION`: fraction of region population that constitutes density. [CALIBRATE M61b]
- Suggested starting values: `DENSITY_FLOOR = 5`, `DENSITY_FRACTION = 0.03`.

**Connected components:** 8-neighbor adjacency. Scan in row-major order (row 0 left-to-right, then row 1, etc.) for deterministic cluster assignment. Each connected component of dense cells is one cluster.

Cluster key: `(region_index, component_id)` where `component_id` is assigned in row-major discovery order (first component found = 0, second = 1, etc.).

### 3.2 Cluster properties

For each cluster (connected component):
- **Population:** Count of agents whose positions fall within the cluster's cells.
- **Centroid:** Population-weighted mean of raw agent `(x, y)` positions within the cluster (not cell centers).
- **Cell set:** The set of `(cx, cy)` grid cells in the component (for footprint comparison if needed later).

---

## 4. Matching

### 4.1 Two-pass matching

Each detection pass runs two matching passes in sequence. Active/dissolving settlements match first (they have stable IDs and founding turns); candidates match second against remaining clusters.

**Pass 1 — Active/dissolving settlements:**

1. Build all eligible `(existing_settlement, new_cluster)` pairs where centroid distance ≤ `MAX_MATCH_DISTANCE`. [CALIBRATE M61b]
   - Only settlements from `Region.settlements` (status `ACTIVE` or `DISSOLVING`) participate.
   - Suggested starting value: `MAX_MATCH_DISTANCE = 0.25` (quarter of region space).
2. Sort pairs by `(distance ASC, settlement_age DESC, settlement_id ASC, cluster_key ASC)`.
   - `settlement_age = source_turn - settlement.founding_turn` where `source_turn` is the turn the snapshot was taken.
   - This sort is fully deterministic: no ties possible (settlement_id and cluster_key are unique).
3. Greedily assign first valid unmatched pair. Once a settlement or cluster is assigned, skip further pairs involving either.
4. **Unmatched settlements** → inertia/dissolution flow (Section 5.3, 5.4).

**Pass 2 — Candidates:**

5. From the clusters not claimed in Pass 1, build `(existing_candidate, remaining_cluster)` pairs within `MAX_MATCH_DISTANCE`.
6. Sort pairs by `(distance ASC, candidate_passes DESC, candidate_index ASC, cluster_key ASC)`.
   - `candidate_index` is the position in `WorldState.settlement_candidates` (stable within a detection pass).
   - Candidates have no `settlement_id` or `founding_turn` — these are assigned on promotion, not during matching.
7. Greedily assign as in Pass 1.
8. **Matched candidates** → increment `candidate_passes`, check for promotion (Section 5.2).
9. **Unmatched candidates** → silently dropped.
10. **Remaining unclaimed clusters** → create new candidates (Section 5.2).

### 4.2 Turn anchor

Detection uses snapshot positions from the current turn's agent tick. The `source_turn` for all lifecycle computations is `world.turn` at the time detection runs (after agent tick, before Phase 10).

---

## 5. Lifecycle

### 5.1 State machine

```
                    ┌─────────────────────────────────┐
                    │                                  │
    new cluster ──► CANDIDATE ──(persist N passes)──► ACTIVE ──(inertia=0)──► DISSOLVING ──(grace=0)──► DISSOLVED
                    │                                  │  ▲                    │                          (tombstone)
                    │ (disappear)                      │  │                    │ (re-match)
                    ▼                                  │  └────────────────────┘
                  (silent drop)                        │
                                                       │ (matched each pass)
                                                       └──► inertia++
```

### 5.2 Candidate stage

- Clusters remaining after Pass 1 (active/dissolving matching) enter Pass 2 (candidate matching).
- Clusters that match an existing candidate: `candidate_passes += 1` on that candidate. Update candidate centroid and population.
- Clusters that match no candidate: create a new candidate `Settlement(status=CANDIDATE, region_name=..., centroid_x=..., centroid_y=..., population_estimate=..., candidate_passes=1, last_seen_turn=source_turn)`. Sentinel defaults: `settlement_id=0`, `name=""`, `founding_turn=0`. Stored in `WorldState.settlement_candidates`.
- Existing candidates that match no cluster: silently dropped. No tombstone, no event.
- When `candidate_passes >= CANDIDATE_PERSISTENCE` [CALIBRATE M61b]: promote to active.
  - Suggested starting value: `CANDIDATE_PERSISTENCE = 2` (2 consecutive passes = 30 turns at interval 15).
- **Sentinel values:** Candidates use `settlement_id=0`, `name=""`, `founding_turn=0` as construction defaults. These are never emitted in events, snapshots, or bundle output. They are overwritten on promotion. Code that filters for active/dissolving settlements should check `status`, not test for sentinel values.

**On promotion:**
- Allocate `settlement_id` from `WorldState.next_settlement_id` (increment after).
- Assign `name` from `"{region_name} Settlement {seq}"` using `WorldState.settlement_naming_counters[region_name]` (increment after).
- Set `founding_turn = source_turn`.
- Set `status = ACTIVE`, `inertia = 1`.
- Move from `WorldState.settlement_candidates` to `Region.settlements`.
- Emit `settlement_founded` event.

### 5.3 Active stage

Each detection pass where an active settlement is **matched:**
- Update `centroid_x`, `centroid_y` from cluster centroid.
- Update `population_estimate` from cluster population.
- Update `peak_population = max(peak_population, population_estimate)`.
- Update `last_seen_turn = source_turn`.
- `inertia = min(inertia + 1, inertia_cap)`.

**Inertia cap** scales with age and smoothed population:

```python
inertia_cap = min(
    BASE_INERTIA_CAP
    + age_turns // AGE_BONUS_INTERVAL
    + settlement.population_estimate // POP_BONUS_INTERVAL,
    MAX_INERTIA_CAP
)
```

- `BASE_INERTIA_CAP`: starting cap for newly promoted settlements. [CALIBRATE M61b]
- `AGE_BONUS_INTERVAL`: turns per +1 cap bonus. [CALIBRATE M61b]
- `POP_BONUS_INTERVAL`: population per +1 cap bonus. [CALIBRATE M61b]
- `MAX_INERTIA_CAP`: hard ceiling. [CALIBRATE M61b]
- `settlement.population_estimate` is the value from the most recent matched detection pass. It uses the last-matched value rather than any averaging, which naturally smooths because detection runs every 15 turns and `population_estimate` is only updated on match. No separate smoothing field is needed.
- Suggested starting values: `BASE_INERTIA_CAP = 3`, `AGE_BONUS_INTERVAL = 50`, `POP_BONUS_INTERVAL = 100`, `MAX_INERTIA_CAP = 10`.

Each detection pass where an active settlement is **unmatched:**
- `inertia -= 1`.
- If `inertia == 0`: transition to `DISSOLVING` with `grace_remaining = DISSOLVE_GRACE`.

### 5.4 Dissolving stage

Each detection pass where a dissolving settlement is **matched:**
- Restore to `ACTIVE` with `inertia = 1` (revived).
- Update centroid, population, last_seen_turn as in active stage.
- Transition reason: `revived_on_match`.

Each detection pass where a dissolving settlement is **unmatched:**
- `grace_remaining -= 1`.
- If `grace_remaining == 0`:
  - Set `status = DISSOLVED`, `dissolved_turn = source_turn`.
  - Drop transient lifecycle fields (`inertia`, `grace_remaining`, `candidate_passes`).
  - Move from `Region.settlements` to `WorldState.dissolved_settlements`.
  - Emit `settlement_dissolved` event.
  - Transition reason: `dissolved_grace_expired`.

`DISSOLVE_GRACE`: number of additional passes after inertia exhaustion. [CALIBRATE M61b]
- Suggested starting value: `DISSOLVE_GRACE = 2` (2 passes = 30 turns grace period).

---

## 6. Events

Events are emitted on lifecycle transition edges only:

### 6.1 `settlement_founded`

Emitted when a candidate promotes to active.

```python
Event(
    turn=source_turn,
    event_type="settlement_founded",
    actors=[region_controller or ""],  # Civ that controls the region
    description=f"A settlement has formed in {region_name}: {settlement_name}",
    consequences=[],
    importance=4,
    source="agent",
)
```

### 6.2 `settlement_dissolved`

Emitted when a dissolving settlement's grace expires.

```python
Event(
    turn=source_turn,
    event_type="settlement_dissolved",
    actors=[region_controller or ""],
    description=f"The settlement of {settlement_name} in {region_name} has been abandoned",
    consequences=[],
    importance=3,
    source="agent",
)
```

No new `CAUSAL_PATTERNS` entries in M56a. No narrator templates. Events flow through the existing curator pipeline for selection and clustering.

---

## 7. Cadence and Phase Placement

### 7.1 Detection interval

`SETTLEMENT_DETECTION_INTERVAL = 15` [CALIBRATE M61b]

Detection runs when `world.turn % SETTLEMENT_DETECTION_INTERVAL == 0`.

### 7.2 Forced terminal detection

On the final turn of a run, detection runs regardless of interval gate. Plumbing: `run_turn()` receives a `force_settlement_detection: bool = False` parameter, set to `True` by the run loop on the last iteration.

### 7.3 Call site in `run_turn()`

Inserted after snapshot stash and before Phase 10:

```python
# simulation.py, after line ~1567 (economy_result stash)

# M56a: Settlement detection
if agent_bridge is not None:
    from chronicler.settlements import detect_settlements
    if world.turn % SETTLEMENT_DETECTION_INTERVAL == 0 or force_settlement_detection:
        settlement_events = detect_settlements(world, source_turn=world.turn)
        turn_events.extend(settlement_events)
```

In `--agents=off` mode: no detection runs, no settlement state created. Debug log emitted once per run: `"Settlement detection disabled: no agent snapshot (mode=off)"`.

### 7.4 `--agents=off` behavior

Deterministic no-op. Settlement fields on Region and WorldState remain at their default (empty list / 0 / None). TurnSnapshot carries deterministic empty settlement summaries so bundle shape is stable across modes.

---

## 8. TurnSnapshot Surface

### 8.1 New field on `TurnSnapshot`

```python
class SettlementSummary(BaseModel):
    settlement_id: int
    name: str
    region_name: str
    population_estimate: int
    centroid_x: float
    centroid_y: float
    founding_turn: int
    status: str  # "active" or "dissolving"

class TurnSnapshot(BaseModel):
    # ... existing fields ...
    # M56a: Settlement summary
    settlement_count: int = 0                                    # Active + dissolving
    candidate_count: int = 0
    total_settlement_population: int = 0
    active_settlements: list[SettlementSummary] = Field(default_factory=list)
    founded_this_turn: list[int] = Field(default_factory=list)   # Settlement IDs
    dissolved_this_turn: list[int] = Field(default_factory=list)  # Settlement IDs
```

Populated during inline snapshot construction in `main.py` (where `TurnSnapshot(...)` is built). In `--agents=off` mode, all fields remain at defaults (0 / empty list).

### 8.2 Deterministic ordering

`active_settlements` sorted by `(region_name, settlement_id)`. `founded_this_turn` and `dissolved_this_turn` sorted by settlement ID.

---

## 9. Diagnostics

### 9.1 Per-turn diagnostics

Every turn (not just detection passes), `world._settlement_diagnostics` records:

```python
{
    "detection_executed": bool,       # True if detection pass ran this turn
    "interval": SETTLEMENT_DETECTION_INTERVAL,
    "reason": str,                    # "interval_match", "forced_terminal", "not_detection_turn", "mode_off_no_snapshot"
}
```

### 9.2 Per-detection-pass diagnostics

When `detection_executed` is True, additional fields:

```python
{
    # ... per-turn fields above ...
    "source_turn": int,
    "per_region": {
        region_name: {
            "dense_cells": int,
            "cluster_count": int,
            "candidate_count": int,
            "active_count": int,
            "dissolving_count": int,
        }
    },
    "matching_stats": {
        "matched_active": int,
        "unmatched_active": int,
        "new_candidates": int,
        "promoted": int,
        "revived": int,
        "entered_dissolving": int,
        "tombstoned": int,
    },
    "transitions": [
        {
            "settlement_id": int,
            "name": str,
            "region_name": str,
            "from_status": str,
            "to_status": str,
            "reason": str,  # "promoted_persistence", "dissolved_grace_expired", "revived_on_match", "entered_dissolving"
        }
    ],
    "global": {
        "total_active": int,
        "total_candidates": int,
        "total_dissolving": int,
        "total_dissolved_cumulative": int,
    },
}
```

### 9.3 Analytics extractor

`extract_settlement_diagnostics(history: list[dict]) -> dict` in `analytics.py`:
- Settlement count time series (active, candidates, dissolved cumulative per turn)
- Per-settlement lifespan (founding turn → dissolution turn or ongoing)
- Population estimates over time per settlement
- Founding/dissolution rate per era
- Consumes TurnSnapshot chain, same pattern as `extract_spatial_diagnostics()`.

---

## 10. Calibration Constants

All constants marked `[CALIBRATE M61b]`:

| Constant | Default | Description |
|----------|---------|-------------|
| `SETTLEMENT_DETECTION_INTERVAL` | 15 | Turns between detection passes |
| `GRID_SIZE` | 10 | Detection grid resolution per axis |
| `DENSITY_FLOOR` | 5 | Minimum agents per cell to qualify as dense |
| `DENSITY_FRACTION` | 0.03 | Fraction of region population for density threshold |
| `MAX_MATCH_DISTANCE` | 0.25 | Maximum centroid distance for settlement-cluster matching |
| `CANDIDATE_PERSISTENCE` | 2 | Consecutive passes for candidate → active promotion |
| `BASE_INERTIA_CAP` | 3 | Starting inertia cap for newly promoted settlements |
| `AGE_BONUS_INTERVAL` | 50 | Turns per +1 inertia cap bonus |
| `POP_BONUS_INTERVAL` | 100 | Population per +1 inertia cap bonus |
| `MAX_INERTIA_CAP` | 10 | Hard ceiling on inertia cap |
| `DISSOLVE_GRACE` | 2 | Additional passes after inertia exhaustion before tombstone |

RNG stream offset `1500` is reserved for M56a in the roadmap's `STREAM_OFFSETS` table. M56a's detection algorithm is deterministic without RNG (grid assignment, connected components, sorted bipartite matching are all deterministic). The offset is reserved for future use if noise is added to detection thresholds during calibration.

---

## 11. Determinism Guarantees

1. **Grid assignment:** `int(x * GRID_SIZE)` is deterministic for identical `f32` inputs.
2. **Connected components:** Row-major scan order produces identical component IDs.
3. **Matching sort:** Pass 1: 4-key sort `(distance ASC, age DESC, settlement_id ASC, cluster_key ASC)` has no ties (unique IDs). Pass 2: 4-key sort `(distance ASC, candidate_passes DESC, candidate_index ASC, cluster_key ASC)` has no ties (unique indices).
4. **Lifecycle transitions:** Integer arithmetic only (inertia, grace_remaining, candidate_passes).
5. **Naming:** Monotonic counters produce identical names for identical seed/scenario.
6. **No hash-order dependencies:** All iteration is over sorted lists or fixed-index arrays.
7. **Snapshot ordering:** All emitted lists sorted by `(region_name, settlement_id)`.

Repeated same-seed runs produce identical settlement IDs, names, and lifecycle transitions.

---

## 12. File Touch Map

| File | Changes |
|------|---------|
| `src/chronicler/settlements.py` | **New.** Detection grid, clustering, matching, lifecycle, diagnostics. |
| `src/chronicler/models.py` | `Settlement`, `SettlementStatus`, `SettlementSummary` models. Fields on `Region`, `WorldState`, `TurnSnapshot`. |
| `src/chronicler/simulation.py` | Standalone call in `run_turn()` (~line 1568). `force_settlement_detection` parameter. |
| `src/chronicler/analytics.py` | `extract_settlement_diagnostics()` extractor. |
| `src/chronicler/main.py` | Thread `force_settlement_detection` on terminal turn. |
| `tests/test_settlements.py` | **New.** Unit + integration + determinism tests. |

No Rust changes. No viewer changes.

---

## 13. Validation Plan

### 13.1 Unit tests (`test_settlements.py`)

- **Grid construction:** Agents placed at known positions produce expected cell assignments.
- **Dense cell detection:** Threshold logic with floor and fraction.
- **Connected components:** Known dense-cell patterns produce expected clusters (single cell, L-shape, diagonal adjacency, two separate clusters).
- **Matching:** Deterministic bipartite assignment with distance gate, age priority, ID tiebreak.
- **Candidate promotion:** Candidate persists through N passes → promotes with correct ID/name.
- **Candidate drop:** Candidate disappears before persistence threshold → silently dropped.
- **Inertia accumulation:** Matched active settlement increments inertia up to cap.
- **Inertia cap scaling:** Cap increases with age and population.
- **Dissolution flow:** Unmatched active → inertia decrement → dissolving → grace → tombstone.
- **Revival:** Dissolving settlement re-matches → restored to active with inertia 1.
- **Naming:** Per-region sequence numbers, never reused after dissolution.
- **ID uniqueness:** IDs never reused across regions or after dissolution.
- **Events:** Founded/dissolved events emitted on correct transitions with correct payload.
- **Off-mode:** No detection, empty outputs, stable TurnSnapshot shape.
- **Forced terminal:** Detection runs on final turn regardless of interval.

### 13.2 Integration tests

- **Multi-turn lifecycle:** 100+ turn run with agents clustering → settlements form → persist → some dissolve.
- **Save/load continuity:** Save mid-run, reload, continue → candidate state, naming counters, and settlement IDs preserved.
- **No regression in off-mode:** `--agents=off` runs produce identical output to pre-M56a baseline.
- **No regression in M55 tests:** Existing spatial substrate and asabiya tests pass unchanged.
- **Coexistence with Phase 10:** Settlement detection doesn't interfere with culture, religion, factions, or succession in `phase_consequences()`.

### 13.3 Determinism tests

- **Seed stability:** Two identical runs (same seed, same scenario, same turn count) produce identical settlement IDs, names, lifecycle transitions, and diagnostics.
- **Snapshot stability:** TurnSnapshot settlement summaries are byte-identical across repeated runs.

### 13.4 Gate criteria

- [ ] Settlements form in regions with spatial clustering pressure (attractor-driven hotspots).
- [ ] Settlements persist through consecutive detection passes with stable IDs.
- [ ] Settlements dissolve when clustering pressure disappears, with inertia absorbing transient dips.
- [ ] IDs remain stable through the full lifecycle.
- [ ] Determinism: identical across repeated same-seed runs.
- [ ] No regressions in `--agents=off`, M55a, or M55b tests.
- [ ] Diagnostics surface is available and correct.
- [ ] 200-seed regression comparison shows no unintended behavioral changes outside settlement subsystem.

---

## 14. Contract for M56b

M56b will consume the following from M56a:

- `Region.settlements` list with stable `settlement_id`, `centroid_x/y`, `population_estimate`, `status`.
- `Settlement.settlement_id` for per-agent `settlement_id: u16` Rust field (M56b adds this).
- Settlement footprint (cell set or centroid + radius) for "is agent urban?" classification.
- `WorldState.dissolved_settlements` for ruins/resettlement detection.
- Lifecycle events for richer narrator templates.
- `display_name` field for narrator-assigned settlement names.

M56a does not constrain M56b's mechanical design — it only provides the observational substrate.
