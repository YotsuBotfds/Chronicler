# M53a/b: Depth Tuning Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calibrate ~145+ constants across M48-M52 depth systems, build validation oracles proving emergent social structure, and freeze constants before the scale track begins.

**Architecture:** Three-phase pipeline: (1) M53a.0 adds observability (bulk FFI exports, graph+memory sidecar, validation summary, tag normalization), (2) M53a.1 runs staged tuning (smoke → baseline → 6 system passes → integration → freeze), (3) M53b builds formal validation oracles in a new `chronicler.validate` module. All simulation runs use `--simulate-only --parallel 12`; narration is a separate small sample.

**Tech Stack:** Python 3.12, Rust/PyO3 (new Arrow FFI methods), pytest, YAML (tuning snapshots), Arrow IPC (sidecar format).

**Spec:** `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `src/chronicler/validate.py` | Oracle runner module (`python -m chronicler.validate --batch-dir <path> --oracles all`). Post-processing pass over bundles + sidecars. |
| `src/chronicler/sidecar.py` | Sidecar writer/reader: graph+memory snapshots, condensed community summaries, agent aggregate, validation summary. |
| `tests/test_validate.py` | Oracle unit tests with synthetic data. |
| `tests/test_sidecar.py` | Sidecar write/read round-trip tests. |
| `tuning/m53_baseline.yaml` | Phase 0 baseline snapshot (all defaults before tuning). |
| `tuning/m53a_frozen.yaml` | Final frozen constant values with HARD/SOFT tier tags. |

### Modified Files

| File | Changes |
|------|---------|
| `chronicler-agents/src/ffi.rs` | Add `get_all_memories()` and `get_all_needs()` bulk Arrow export methods. |
| `chronicler-agents/src/agent.rs` | Normalize `[CALIBRATE M53]` tags (individual per constant). Tuning edits in later tasks. |
| `src/chronicler/analytics.py` | Add `extract_bond_health()`, `extract_era_signals()`, `extract_legacy_chain_metrics()`. Extend `extract_relationship_metrics()`. |
| `src/chronicler/main.py` | Add `--validation-sidecar` CLI flag. Wire `--relationship-stats` → FFI → metadata. |
| `src/chronicler/agent_bridge.py` | Call sidecar writer during tick when `--validation-sidecar` is active. Wire `get_relationship_stats()` into metadata collection. |
| `src/chronicler/batch.py` | Thread `--validation-sidecar` flag through to worker processes. |
| `src/chronicler/narrative.py` | Update `_NEED_THRESHOLDS` when Rust constants change in tuning passes. |
| `src/chronicler/artifacts.py` | Tuning edits to `[CALIBRATE M53]` constants in later tasks. |
| `src/chronicler/dynasties.py` | Tuning edits to `LEGITIMACY_DIRECT_HEIR`, `LEGITIMACY_SAME_DYNASTY` in later tasks. |

---

## Task 1: Tag Normalization (M53a.0 prerequisite)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:283-337` (M50b formation constants)
- Modify: `chronicler-agents/src/agent.rs:170-217` (M48 block-header-only constants)
- Modify: `chronicler-agents/src/agent.rs:222-267` (M49 block-header-only constants)

- [ ] **Step 1: Add individual `[CALIBRATE M53]` tags to every M50b formation constant**

In `agent.rs`, lines 284-337 have a single block-header tag `// M50b: Formation constants [CALIBRATE M53]` but no individual tags. Add `// [CALIBRATE M53]` to each constant line. Example:

```rust
pub const FORMATION_CADENCE: u32 = 6;  // [CALIBRATE M53]

// Similarity weights
pub const W_CULTURE: f32 = 0.35;  // [CALIBRATE M53]
pub const W_BELIEF: f32 = 0.35;   // [CALIBRATE M53]
// ... (all 28 constants in this block)
```

- [ ] **Step 2: Verify all M48 and M49 constants have individual tags**

Scan lines 170-267. Block headers already have `[CALIBRATE M53]`. Add individual tags to each constant line that lacks one (most M48 intensity/half-life constants and M49 decay/threshold/weight/restoration constants have block headers only).

- [ ] **Step 3: Verify tag count matches spec inventory**

Run: `grep -c "CALIBRATE M53" chronicler-agents/src/agent.rs`
Expected: ~114 individual tags (41 memory + 37 needs + 8 drift + 28 formation)

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "chore(m53): normalize [CALIBRATE M53] tags — individual per constant"
```

---

## Task 2: Bulk Memory FFI Export

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Test: `chronicler-agents/tests/test_m53_ffi.rs`

- [ ] **Step 1: Write integration test for `get_all_memories()`**

Create `chronicler-agents/tests/test_m53_ffi.rs`:

```rust
use chronicler_agents::ffi::AgentSimulator;

#[test]
fn test_get_all_memories_returns_record_batch() {
    let mut sim = AgentSimulator::new(2, 42);
    // Spawn some agents, run a tick to generate memories
    // ... (use existing test patterns from test_m50b_formation.rs)
    let batch = sim.get_all_memories().unwrap();
    // Verify schema: agent_id, slot, event_type, turn, intensity, is_legacy,
    //                civ_affinity, region, occupation
    assert_eq!(batch.num_columns(), 9);
    assert!(batch.num_rows() > 0);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run test_get_all_memories -p chronicler-agents`
Expected: FAIL — method does not exist

- [ ] **Step 3: Implement `get_all_memories()` on `AgentSimulator`**

In `ffi.rs`, add a new PyO3 method following the `get_all_relationships()` pattern (line ~1133). Iterate alive agents, expand 8 memory slots per agent into rows:

```rust
#[pyo3(name = "get_all_memories")]
pub fn get_all_memories(&self) -> PyResult<PyRecordBatch> {
    let pool = &self.pool;
    let mut agent_ids = Vec::new();
    let mut slots = Vec::new();
    let mut event_types = Vec::new();
    let mut turns = Vec::new();
    let mut intensities = Vec::new();
    let mut is_legacy = Vec::new();
    let mut civ_affinities = Vec::new();
    let mut regions = Vec::new();
    let mut occupations = Vec::new();

    for slot_idx in 0..pool.capacity() {
        if !pool.alive[slot_idx] { continue; }
        let agent_id = pool.ids[slot_idx];
        let count = pool.memory_count[slot_idx] as usize;
        for i in 0..count {
            let evt = pool.memory_event_types[slot_idx][i];
            agent_ids.push(agent_id);
            slots.push(i as u8);
            event_types.push(evt);
            turns.push(pool.memory_turns[slot_idx][i]);
            intensities.push(pool.memory_intensities[slot_idx][i]);
            is_legacy.push(((pool.memory_is_legacy[slot_idx] >> i) & 1) as u8);
            civ_affinities.push(pool.civ_affinities[slot_idx]);
            regions.push(pool.regions[slot_idx]);
            occupations.push(pool.occupations[slot_idx]);
        }
    }
    // Build Arrow arrays and RecordBatch (same pattern as get_all_relationships)
    // Schema: agent_id(u32), slot(u8), event_type(u8), turn(u16),
    //         intensity(i8), is_legacy(u8), civ_affinity(u16), region(u16), occupation(u8)
    // NOTE: civ_affinity uses UInt16 (with `as u16` cast) to match existing snapshot_schema() convention
    // ... (Arrow builder boilerplate)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo nextest run test_get_all_memories -p chronicler-agents`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_m53_ffi.rs
git commit -m "feat(m53): get_all_memories() bulk Arrow FFI export"
```

---

## Task 3: Bulk Needs FFI Export

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Modify: `chronicler-agents/tests/test_m53_ffi.rs`

- [ ] **Step 1: Write integration test for `get_all_needs()`**

Add to `test_m53_ffi.rs`:

```rust
#[test]
fn test_get_all_needs_returns_record_batch() {
    let mut sim = AgentSimulator::new(2, 42);
    // Spawn agents
    let batch = sim.get_all_needs().unwrap();
    // Schema: agent_id(u32), safety(f32), autonomy(f32), social(f32), spiritual(f32),
    //         material(f32), purpose(f32), civ_affinity(u16), region(u16), occupation(u8),
    //         satisfaction(f32), boldness(f32), ambition(f32), loyalty_trait(f32)
    // NOTE: civ_affinity uses UInt16 to match existing snapshot_schema() convention
    assert_eq!(batch.num_columns(), 14);
    assert!(batch.num_rows() > 0);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run test_get_all_needs -p chronicler-agents`
Expected: FAIL

- [ ] **Step 3: Implement `get_all_needs()` on `AgentSimulator`**

Same pattern as `get_all_memories()`. One row per alive agent, 14 columns including join columns (civ_affinity, region, occupation, satisfaction, personality traits).

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo nextest run test_get_all_needs -p chronicler-agents`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_m53_ffi.rs
git commit -m "feat(m53): get_all_needs() bulk Arrow FFI export with join columns"
```

---

## Task 4: Sidecar Writer/Reader

**Files:**
- Create: `src/chronicler/sidecar.py`
- Create: `tests/test_sidecar.py`
- Modify: `src/chronicler/main.py:669-758` (add `--validation-sidecar` flag)

- [ ] **Step 1: Write round-trip test for sidecar**

Create `tests/test_sidecar.py`:

```python
from chronicler.sidecar import SidecarWriter, SidecarReader
import tempfile, pathlib

def test_graph_snapshot_round_trip():
    """Write a graph+memory snapshot, read it back, verify contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        # Synthetic edge data: [(agent_a, agent_b, bond_type, sentiment)]
        edges = [(1, 2, 3, 50), (2, 3, 0, 60)]
        # Synthetic memory signatures: {agent_id: [(event_type, turn, valence_sign)]}
        mem_sigs = {1: [(0, 10, -1), (6, 20, 1)], 2: [(0, 10, -1)], 3: []}
        writer.write_graph_snapshot(turn=10, edges=edges, memory_signatures=mem_sigs)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        snapshot = reader.read_graph_snapshot(turn=10)
        assert len(snapshot["edges"]) == 2
        assert snapshot["edges"][0] == (1, 2, 3, 50)
        assert snapshot["memory_signatures"][1] == [(0, 10, -1), (6, 20, 1)]

def test_agent_aggregate_round_trip():
    """Write per-civ agent aggregate, read it back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        agg = {
            "civ_0": {
                "satisfaction_mean": 0.55, "satisfaction_std": 0.12,
                "occupation_counts": {"farmers": 200, "soldiers": 50, "merchants": 30, "scholars": 10, "priests": 10},
                "agent_count": 300,
                "need_means": {"safety": 0.45, "autonomy": 0.50, "social": 0.40, "spiritual": 0.35, "material": 0.55, "purpose": 0.48},
                "memory_slot_occupancy_mean": 4.2,
            }
        }
        writer.write_agent_aggregate(turn=10, aggregates=agg)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        result = reader.read_agent_aggregate(turn=10)
        assert abs(result["civ_0"]["satisfaction_mean"] - 0.55) < 0.001

def test_condensed_community_summary():
    """Write condensed community summary for gate runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        summary = {
            "region_0": {"cluster_count": 3, "sizes": [5, 8, 12], "dominant_memory_type": 0},
            "region_1": {"cluster_count": 1, "sizes": [7], "dominant_memory_type": 1},
        }
        writer.write_community_summary(turn=100, summary=summary)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        result = reader.read_community_summary(turn=100)
        assert result["region_0"]["cluster_count"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sidecar.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement `SidecarWriter` and `SidecarReader`**

Create `src/chronicler/sidecar.py`. Use Arrow IPC for graph snapshots and needs snapshots (efficient binary), JSON for agent aggregates and community summaries (small, human-readable). Methods: `write_graph_snapshot()`, `write_needs_snapshot()`, `write_agent_aggregate()`, `write_community_summary()`, plus corresponding readers. Files organized as:

```
<seed_dir>/
  validation_summary/
    graph_turn_010.arrow
    needs_turn_010.arrow
    graph_turn_020.arrow
    needs_turn_020.arrow
    ...
    aggregate_turn_010.json
    community_turn_100.json
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sidecar.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Add `--validation-sidecar` CLI flag**

In `main.py:_build_parser()`, add:

```python
parser.add_argument("--validation-sidecar", action="store_true",
                    help="Write heavy validation sidecars (graph snapshots, agent aggregates)")
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/sidecar.py tests/test_sidecar.py src/chronicler/main.py
git commit -m "feat(m53): sidecar writer/reader — graph snapshots, agent aggregates, community summaries"
```

---

## Task 5: Wire Sidecar Into Simulation Loop

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/batch.py`

- [ ] **Step 1: Thread `--validation-sidecar` through batch runner to AgentBridge**

In `batch.py`, `child_args` already copies `args` via `copy.copy(args)` at line 56 — the flag propagates automatically.

In `main.py`, `execute_run()` constructs `AgentBridge` at ~line 198 as `AgentBridge(world, mode=agent_mode)`. Add `validation_sidecar=getattr(args, 'validation_sidecar', False)` parameter. Thread from: `_build_parser()` → `args.validation_sidecar` → `execute_run()` → `AgentBridge.__init__(validation_sidecar=...)`.

In `agent_bridge.py`, add `validation_sidecar: bool = False` parameter to `AgentBridge.__init__()`. When True, instantiate `SidecarWriter(output_dir)` and store as `self._sidecar`.

- [ ] **Step 2: Wire sidecar writer into agent bridge tick**

In `agent_bridge.py`, add sidecar writing logic. When `self._sidecar` is set, every 10 turns:
- Call `self._sim.get_all_relationships()` + `self._sim.get_all_memories()` → write graph+memory snapshot via `self._sidecar.write_graph_snapshot()`
- Call `self._sim.get_all_needs()` → write needs snapshot via `self._sidecar.write_needs_snapshot()` (Oracle 2 requires this for matched-cohort comparison)
- Compute `AgentAggregate` from the needs + snapshot data: satisfaction mean/std, occupation counts, per-need means, memory slot occupancy → write via `self._sidecar.write_agent_aggregate()`
- Compute condensed community summary from graph snapshot → write via `self._sidecar.write_community_summary()`

All three bulk FFI calls (`get_all_relationships`, `get_all_memories`, `get_all_needs`) are called at the same sample points so the data is temporally consistent for oracle joins.

- [ ] **Step 3: Wire `--relationship-stats` → `get_relationship_stats()` → bundle metadata**

In `agent_bridge.py`, when `relationship_stats=True`:
- Call `self._sim.get_relationship_stats()` each tick
- Accumulate into `self._relationship_stats_history: list[dict]`
- Expose via property for bundle metadata injection

In `main.py`, thread `args.relationship_stats` into `AgentBridge` constructor and into bundle metadata assembly.

- [ ] **Step 4: Test sidecar integration manually**

Run: `python -m chronicler --seed 42 --turns 50 --agents hybrid --simulate-only --validation-sidecar`
Verify: `validation_summary/` directory created with graph snapshots at turns 10, 20, 30, 40, 50.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/simulation.py src/chronicler/batch.py src/chronicler/main.py
git commit -m "feat(m53): wire sidecar writer into simulation loop + relationship-stats metadata"
```

---

## Task 6: Standard Analytics Extractors

**Files:**
- Modify: `src/chronicler/analytics.py`
- Create: `tests/test_m53_analytics.py`

- [ ] **Step 1: Write tests for new extractors**

```python
def test_extract_bond_health_global():
    """extract_bond_health returns global stats from relationship_stats metadata."""
    bundle = {"metadata": {"relationship_stats": [
        {"bonds_formed": 5, "bonds_dissolved_death": 1, "bonds_dissolved_structural": 2,
         "mean_rel_count": 3.2, "bond_type_count_0": 10, "bond_type_count_3": 5,
         "cross_civ_bond_fraction": 0.15},
    ]}}
    result = extract_bond_health([bundle])
    assert result["mean_rel_count_per_turn"][0] == 3.2
    assert result["bonds_formed_per_turn"][0] == 5

def test_extract_era_signals():
    """extract_era_signals returns per-civ time series."""
    # Bundle history is list of turn snapshots, each with civ_stats dict
    bundle = {"history": [
        {"turn": 0, "civ_stats": {"Aram": {"population": 100, "stability": 50, "treasury": 20, "prestige": 5, "regions": ["a", "b"], "gini": 0.4}}},
        {"turn": 1, "civ_stats": {"Aram": {"population": 120, "stability": 45, "treasury": 25, "prestige": 8, "regions": ["a", "b", "c"], "gini": 0.45}}},
    ]}
    result = extract_era_signals([bundle])
    assert result["Aram"]["population"] == [100, 120]
    assert result["Aram"]["territory"] == [2, 3]
    assert result["Aram"]["gini"] == [0.4, 0.45]

def test_extract_legacy_chain_metrics():
    """extract_legacy_chain_metrics computes legacy memory stats from bulk export."""
    # Synthetic: pass mock bulk memory data and GP dynasty data
    # Verify: legacy intensity mean, chain length, activation rate
    pass  # Detailed after bulk FFI available
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_m53_analytics.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `extract_bond_health()`**

**Replaces** `extract_relationship_metrics()` at `analytics.py:1697` (rename in-place, update the caller in `generate_report()` at line ~1226). Consumes `metadata.relationship_stats` (global stats from `get_relationship_stats()`). Returns: `mean_rel_count_per_turn`, `bonds_formed_per_turn`, `bonds_dissolved_per_turn`, `bond_type_counts` (8 types), `cross_civ_bond_fraction_per_turn`. Do not create both extractors — spec explicitly requires one name.

- [ ] **Step 4: Implement `extract_era_signals()`**

New extractor. Reads `history` dict from bundles. Per civ: extract time series for population, territory (`len(regions)`), prestige, treasury, stability, gini.

- [ ] **Step 5: Implement `extract_legacy_chain_metrics()`**

New extractor. Reads bulk memory export data + GreatPerson dynasty data from bundles. Computes: legacy memory intensity mean at 2nd/3rd generation, dynasty chain length, legitimacy activation rate.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_m53_analytics.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/analytics.py tests/test_m53_analytics.py
git commit -m "feat(m53): extract_bond_health, extract_era_signals, extract_legacy_chain_metrics"
```

---

## Task 7: Validate Module — Scaffold + Determinism Gate

**Files:**
- Create: `src/chronicler/validate.py`
- Create: `tests/test_validate.py`

- [ ] **Step 1: Write test for determinism gate**

```python
def test_determinism_scrubbed_comparison():
    """Scrubbed comparison ignores generated_at timestamp."""
    bundle_a = {"metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    bundle_b = {"metadata": {"generated_at": "2026-03-21T10:05:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    from chronicler.validate import scrubbed_equal
    assert scrubbed_equal(bundle_a, bundle_b)

    bundle_c = dict(bundle_b)
    bundle_c["world_state"] = {"turn": 101}
    assert not scrubbed_equal(bundle_a, bundle_c)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validate.py::test_determinism_scrubbed_comparison -v`
Expected: FAIL

- [ ] **Step 3: Implement validate module scaffold**

Create `src/chronicler/validate.py`:

```python
"""M53b: Validation oracle runner.

Usage: python -m chronicler.validate --batch-dir <path> --oracles all
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

SCRUB_KEYS = {"generated_at"}

def scrubbed_equal(a: dict, b: dict) -> bool:
    """Compare two bundles ignoring transient metadata fields."""
    def _scrub(d):
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if k not in SCRUB_KEYS}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d
    return _scrub(a) == _scrub(b)

def run_determinism_gate(batch_dir: Path) -> dict:
    """Run determinism smoke gate: 2 identical seeds must produce scrubbed-equal output."""
    # Implementation: load two bundles with same seed, compare
    ...

def run_oracles(batch_dir: Path, oracles: list[str]) -> dict:
    """Run specified oracles and return structured report."""
    ...

def main():
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    args = parser.parse_args()
    report = run_oracles(args.batch_dir, args.oracles)
    json.dump(report, sys.stdout, indent=2)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): validate module scaffold + determinism scrubbed comparison"
```

---

## Task 8: Oracle 1 — Community/Cohort Emergence

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for label propagation community detection**

```python
def test_community_detection_finds_clusters():
    """Label propagation finds communities in a graph with clear structure."""
    # Two disconnected cliques of 5 agents each, all sharing a memory signature
    edges = [(i, j, 2, 50) for i in range(5) for j in range(i+1, 5)]  # clique 1: friend bonds
    edges += [(i, j, 2, 50) for i in range(5, 10) for j in range(i+1, 10)]  # clique 2
    mem_sigs = {i: [(0, 10, -1)] for i in range(10)}  # all share famine memory
    from chronicler.validate import detect_communities
    communities = detect_communities(edges, mem_sigs)
    assert len(communities) == 2
    assert all(len(c) == 5 for c in communities)

def test_community_excludes_kin_only():
    """Communities with only kin bonds are excluded."""
    edges = [(0, 1, 0, 60), (1, 2, 0, 60), (0, 2, 0, 60)]  # bond_type 0 = Kin
    mem_sigs = {0: [(0, 10, -1)], 1: [(0, 10, -1)], 2: [(0, 10, -1)]}
    from chronicler.validate import detect_communities
    communities = detect_communities(edges, mem_sigs)
    assert len(communities) == 0  # excluded: kin-only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validate.py::test_community_detection_finds_clusters -v`
Expected: FAIL

- [ ] **Step 3: Implement `detect_communities()` and Oracle 1**

Deterministic label propagation: sorted agent-ID processing order, tie-break by minimum label ID, undirected edge projection, max 20 iterations. Filter: >=80% shared memory signature, >=1 non-kin positive edge, >=5 members.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 1 — community/cohort detection via label propagation"
```

---

## Task 9: Oracle 2 — Needs Behavioral Diversity

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for matched-cohort comparison**

```python
def test_needs_diversity_detects_behavioral_difference():
    """Agents with divergent needs show different behavioral event rates."""
    # Synthetic: two groups matched on traits, divergent on safety need
    # Group A: low safety → higher migration rate
    # Group B: high safety → lower migration rate
    from chronicler.validate import compute_needs_diversity
    result = compute_needs_diversity(
        needs_data=...,  # synthetic bulk needs
        events_data=..., # synthetic agent_events
        match_tolerance={"personality": 0.1},
        need_divergence=0.2,
        observation_window=20,
    )
    assert result["median_effect_size"] > 0.05
    assert result["seeds_with_expected_sign"] > 0.5
```

- [ ] **Step 2: Implement `compute_needs_diversity()`**

Matched-cohort logic: identify agent pairs matched on (civ, region, occupation, personality ±0.1) but divergent on >=1 need (delta >0.2). Compare migration, occupation_switch, rebellion rates over 20 turns. Per-seed Cohen's d.

- [ ] **Step 3: Run tests, verify pass**

Run: `pytest tests/test_validate.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 2 — needs behavioral diversity matched-cohort comparison"
```

---

## Task 10: Oracle 3 — Era Inflection Detection

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for changepoint detection**

```python
def test_era_inflection_detects_collapse():
    """Detect inflection point when population drops >30%."""
    pop_series = [100]*50 + [60]*50  # sharp drop at t=50
    from chronicler.validate import detect_inflection_points
    points = detect_inflection_points(pop_series, smoothing_window=5)
    assert any(45 <= p <= 55 for p in points)

def test_era_inflection_no_false_positive_on_noise():
    """Noisy but stable series produces no inflection points."""
    import random; random.seed(42)
    pop_series = [100 + random.randint(-5, 5) for _ in range(100)]
    points = detect_inflection_points(pop_series, smoothing_window=5)
    assert len(points) == 0
```

- [ ] **Step 2: Implement `detect_inflection_points()` and Oracle 3**

Simple smoothed-derivative sign-change detection. Smooth with rolling mean (window=5), compute first derivative, flag sign changes with magnitude above threshold. Threshold auto-calibrated as 1.5× series std.

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 3 — era inflection detection via smoothed changepoints"
```

---

## Task 11: Oracle 4 — Cohort Behavioral Distinctiveness

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for cohort vs control comparison**

```python
def test_cohort_distinctiveness_detects_anchoring():
    """Community members migrate less than matched non-community agents."""
    from chronicler.validate import compute_cohort_distinctiveness
    # Synthetic: community agents with 5% migration, control agents with 15%
    result = compute_cohort_distinctiveness(
        communities=[[0,1,2,3,4]],
        events_data=...,  # synthetic
        agent_data=...,   # synthetic demographics for matching
    )
    assert result["migration_effect_direction"] == "community_lower"
    assert result["median_effect_size"] > 0.05
```

- [ ] **Step 2: Implement `compute_cohort_distinctiveness()`**

For each community from Oracle 1, construct matched control (same civ, region, occupation distribution). Compare migration, occupation switch, rebellion rates. Per-seed effect sizes.

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 4 — cohort behavioral distinctiveness vs matched control"
```

---

## Task 12: Oracle 5 — Artifact Lifecycle

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for artifact oracle**

```python
def test_artifact_oracle_checks_creation_rate():
    """Artifact oracle validates creation rate per civ per 100 turns."""
    from chronicler.validate import check_artifact_lifecycle
    bundles = [{"world_state": {"artifacts": [
        {"artifact_type": "relic", "status": "active", "owner_civ": "Aram", "mule_origin": False, "prestige_value": 3},
        {"artifact_type": "artwork", "status": "active", "owner_civ": "Aram", "mule_origin": True, "prestige_value": 2},
        {"artifact_type": "weapon", "status": "destroyed", "owner_civ": "Aram", "mule_origin": False, "prestige_value": 2},
    ]}, "metadata": {"total_turns": 500, "seed": 42}}]
    result = check_artifact_lifecycle(bundles, num_civs=4)
    assert "creation_rate_per_civ_per_100" in result
    assert "type_diversity_ok" in result
```

- [ ] **Step 2: Implement `check_artifact_lifecycle()`**

Import `extract_artifacts` from `chronicler.analytics` into `validate.py`. `check_artifact_lifecycle()` has two sub-checks:

**Sub-check A (bundle-only, runs on full 200-seed gate):** Creation rate (1-3 per civ per 100 turns), type diversity (no type >50%), loss/destruction rate (10-30%), Mule artifact fraction (50-70% of Mules produce artifact). Uses `extract_artifacts()` output.

**Sub-check B (narration sample, runs on 10-seed narrated subset in Task 22 Step 5):** Relic conversion impact (regions with relics show higher conversion rate — compare against `extract_conversion_rates()` output for relic-holding vs non-relic regions). Narrative visibility (>=50% of curated moments involving artifact-holding named characters include artifact context in prose — scan narrated output for artifact names). This sub-check feeds back into the oracle's pass/fail: if Sub-check A passes but Sub-check B fails, the oracle reports "PARTIAL — mechanical OK, narrative gap."

Both sub-checks contribute to the oracle's final result. The oracle is not complete until Task 22 Step 5 runs the narration sample.

Note: `validate.py` imports from `analytics.py` for bundle-level extractors (`extract_artifacts`, `extract_era_signals`, `extract_conversion_rates`). The validate module consumes exported data — it does not run the simulation.

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 5 — artifact lifecycle validation"
```

---

## Task 13: Oracle 6 — Six Emotional Arcs

**Files:**
- Modify: `src/chronicler/validate.py`
- Modify: `tests/test_validate.py`

- [ ] **Step 1: Write test for arc classification**

```python
def test_arc_classifier_rags_to_riches():
    """Rising trajectory classified as Rags to Riches."""
    from chronicler.validate import classify_civ_arc
    trajectory = {"population": list(range(50, 150)), "territory": list(range(2, 6))*25}
    arc = classify_civ_arc(trajectory)
    assert arc == "rags_to_riches"

def test_arc_classifier_icarus():
    """Rise then fall classified as Icarus."""
    pop = list(range(50, 100)) + list(range(100, 50, -1))
    trajectory = {"population": pop}
    arc = classify_civ_arc(trajectory)
    assert arc == "icarus"
```

- [ ] **Step 2: Implement `classify_civ_arc()` and Oracle 6**

Classify based on smoothed derivative sign changes. 6 arc types: rags_to_riches (monotone up), riches_to_rags (monotone down), icarus (up then down), oedipus (down then up then down), cinderella (down then up), man_in_a_hole (down then up with recovery). Check: 5 of 6 families across 200 seeds, no type >40%.

- [ ] **Step 3: Run tests, verify pass**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/validate.py tests/test_validate.py
git commit -m "feat(m53): Oracle 6 — six emotional arcs civ trajectory classification"
```

---

## Task 14: Baseline Sweep (M53a.1 Phase 0)

**Files:**
- Create: `tuning/m53_baseline.yaml`
- Create: `scripts/m53_baseline.py`

- [ ] **Step 1: Create baseline collection script**

`scripts/m53_baseline.py`: runs the smoke gate (5 seeds x 50 turns), then baseline sweep (40 seeds x 200 turns with `--validation-sidecar`). Collects all default constant values from `agent.rs`, `artifacts.py`, `dynasties.py`, `action_engine.py`, `agent_bridge.py`, `narrative.py`. Writes `tuning/m53_baseline.yaml`.

- [ ] **Step 2: Run smoke gate**

Run: `PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 50 --agents hybrid --simulate-only --batch 5 --parallel 4 --validation-sidecar --output output/m53/smoke/chronicle.md`
Verify: No crashes, sidecar files written in `output/m53/smoke/`, no NaN/all-zero degeneracy.

- [ ] **Step 3: Run determinism check**

Run two identical seeds, verify scrubbed equality:
```bash
PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 50 --agents hybrid --simulate-only --output output/m53/determinism_a/chronicle.md
PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 50 --agents hybrid --simulate-only --output output/m53/determinism_b/chronicle.md
python -m chronicler.validate --batch-dir output/m53/determinism_a --oracles determinism --compare output/m53/determinism_b
```

- [ ] **Step 4: Run baseline sweep**

Run: `PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 200 --agents hybrid --simulate-only --batch 40 --parallel 12 --validation-sidecar --output output/m53/baseline/chronicle.md`

- [ ] **Step 5: Collect and save baseline metrics**

Run `scripts/m53_baseline.py` to extract all metrics and save `tuning/m53_baseline.yaml`.

- [ ] **Step 6: Commit baseline**

```bash
git add tuning/m53_baseline.yaml scripts/m53_baseline.py
git commit -m "data(m53): baseline sweep — 40x200 with all defaults"
```

---

## Task 15: System Pass 1a — Memory (M48)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:170-217` (M48 memory constants)
- Modify: `tuning/m53a_frozen.yaml` (add memory constants)

- [ ] **Step 1: Analyze baseline memory metrics**

From baseline sweep: check memory slot occupancy, intensity distribution, satisfaction contribution. Identify which constants are out of range vs the spec targets (slot occupancy 3-6 mean, intensity not degenerate, satisfaction within 0.40 cap budget).

- [ ] **Step 2: Tune memory constants via scout loops**

For each constant adjustment:
1. Edit value in `agent.rs`
2. `cargo build --release -p chronicler-agents` (hooks auto-run cargo check)
3. Run scout: `PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 200 --agents hybrid --simulate-only --batch 40 --parallel 12 --validation-sidecar --output output/m53/scout_1a/chronicle.md` (increment suffix per iteration)
4. Check metrics against targets
5. Iterate

Key calibration flag to check: **negative modifier trapping** — do memory-driven satisfaction penalties push agents into permanent low-satisfaction?

- [ ] **Step 3: Run full gate for memory freeze confirmation**

Run: `PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 500 --agents hybrid --simulate-only --batch 200 --parallel 12 --output output/m53/gate_1a/chronicle.md`

- [ ] **Step 4: Record frozen memory constants**

Add memory section to `tuning/m53a_frozen.yaml` with HARD/SOFT tier tags.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/agent.rs tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1a — memory constants (M48)"
```

---

## Task 16: System Pass 1b — Needs (M49)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:222-267` (M49 needs constants)
- Modify: `src/chronicler/narrative.py:83-84` (sync `_NEED_THRESHOLDS`)
- Modify: `tuning/m53a_frozen.yaml`

- [ ] **Step 1: Analyze baseline needs metrics**

Check need activation fraction, behavioral diversity, sawtooth patterns. Target: peacetime 10-20%, crisis 40-70%.

- [ ] **Step 2: Tune needs constants via scout loops**

M49 calibration flags checklist (all checked in this pass):
- Persecution triple-stacking: total rebel modifier <0.64
- Famine double-counting: food_sufficiency + Safety need don't over-stack
- Needs-only rebellion rate: <5%
- Need activation fraction: peacetime 10-20%, crisis 40-70%
- Migration sloshing: no region-pair oscillation
- Sawtooth oscillation: no <10-turn need cycling
- Duty cycle: each need in both satisfied and deficit states
- Autonomy assimilation loop: no trapped autonomy deficit cycle

- [ ] **Step 3: Sync Python thresholds**

When Rust thresholds change, update `narrative.py:83-84` (`MEMORY_NARRATION_VIVID`, `MEMORY_NARRATION_FADING`) and any `_NEED_THRESHOLDS` values to match.

- [ ] **Step 4: Run full gate, record frozen needs constants**

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/agent.rs src/chronicler/narrative.py tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1b — needs constants (M49)"
```

---

## Task 17: System Pass 1c — Relationships (M50)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:270-337` (M50a/b constants)
- Modify: `tuning/m53a_frozen.yaml`

- [ ] **Step 1: Analyze baseline bond metrics**

Check bond count/agent (target 3-5), formation/dissolution rates, sentiment distribution, `SOCIAL_BLEND_ALPHA` effect.

- [ ] **Step 2: Ramp `SOCIAL_BLEND_ALPHA`**

The M50b progress note says "Alpha=0.0 at ship; M53 ramps." This is a key deliverable: ramp from 0.0 to a positive value so bond-based social-need restoration replaces the pre-M50 proxy. Start with 0.3, scout, adjust.

- [ ] **Step 3: Tune formation and drift constants via scout loops**

Check: social proxy adequacy (M49 flag #8). Does the blend formula produce reasonable social-need restoration?

- [ ] **Step 4: Run full gate, record frozen relationship constants**

`SOCIAL_BLEND_ALPHA` is HARD-frozen (cross-system). Formation cadence, initial sentiments, etc. are SOFT-frozen.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/agent.rs tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1c — relationship constants (M50), SOCIAL_BLEND_ALPHA ramped"
```

---

## Task 18: System Pass 1d — Mule (M48)

**Files:**
- Modify: `src/chronicler/action_engine.py:40-42`
- Modify: `src/chronicler/agent_bridge.py:37-49`
- Modify: `tuning/m53a_frozen.yaml`

- [ ] **Step 1: Analyze baseline Mule metrics**

Check Mule frequency (~0-1 per 100 turns at 50K), impact window visibility, civ action distribution shift.

- [ ] **Step 2: Tune all ~25 Mule constants across both files**

**In `action_engine.py:40-42`:** `MULE_ACTIVE_WINDOW` (20-30 turns), `MULE_FADE_TURNS` (~10).

**In `agent_bridge.py:37-49`:** `MULE_PROMOTION_PROBABILITY` (target 5-10%) + `MULE_MAPPING` dict with 9 event-type entries, each containing 2-3 action→weight pairs (~22 individual weight values). All entries are in scope:
- Famine → DEVELOP:3.0, TRADE:2.0, WAR:0.3
- Battle → WAR:3.0, DIPLOMACY:0.5
- Conquest → WAR:3.0, EXPAND:2.0, DIPLOMACY:0.3
- Persecution → FUND_INSTABILITY:3.0, TRADE:0.5
- Migration → EXPAND:3.0, TRADE:2.0
- Victory → WAR:2.5, EXPAND:2.0
- DeathOfKin → DIPLOMACY:3.0, WAR:0.3
- Conversion → INVEST_CULTURE:3.0, BUILD:2.0
- Secession → DIPLOMACY:2.5, INVEST_CULTURE:2.0

Verify: 80%+ of Mule active windows generate at least one curator-selected event.

- [ ] **Step 3: Run full gate, record frozen Mule constants**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/agent_bridge.py tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1d — Mule constants (M48)"
```

---

## Task 19: System Pass 1e — Legacy (M51)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:197-199` (legacy constants)
- Modify: `src/chronicler/dynasties.py:133-134` (legitimacy constants)
- Modify: `tuning/m53a_frozen.yaml`

- [ ] **Step 1: Analyze baseline legacy metrics**

Check legacy persistence (target 2-3 generations), dynasty chain length, legitimacy activation rate (target >20% of successions). Verify `LEGACY_HALF_LIFE` is actually consumed by M51 implementation (not dead code from vestigial `MemoryEventType::Legacy` path — see progress doc gotcha).

- [ ] **Step 2: Tune legacy and legitimacy constants**

`LEGACY_HALF_LIFE` (100 turns), `LEGACY_MIN_INTENSITY` (10), `LEGACY_MAX_MEMORIES` (2), `LEGITIMACY_DIRECT_HEIR` (0.15), `LEGITIMACY_SAME_DYNASTY` (0.08).

- [ ] **Step 3: Run full gate, record frozen legacy constants**

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs src/chronicler/dynasties.py tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1e — legacy memory + dynasty legitimacy (M51)"
```

---

## Task 20: System Pass 1f — Artifacts (M52)

**Files:**
- Modify: `src/chronicler/artifacts.py:13-30`
- Modify: `tuning/m53a_frozen.yaml`

- [ ] **Step 1: Analyze baseline artifact metrics**

Use existing `extract_artifacts()`. Check creation rate (target 1-3 per civ per 100 turns), type diversity, loss/destruction rate (10-30%), Mule artifact rate.

- [ ] **Step 2: Tune artifact constants**

`CULTURAL_PRODUCTION_CHANCE` (0.15), `GP_PRESTIGE_THRESHOLD` (50), `RELIC_CONVERSION_BONUS` (0.15), `PROSPERITY_STABILITY_THRESHOLD` (70), `PROSPERITY_TREASURY_THRESHOLD` (20), `HISTORY_CAP` (10), `PRESTIGE_BY_TYPE` (7 entries).

- [ ] **Step 3: Run full gate, record frozen artifact constants**

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/artifacts.py tuning/m53a_frozen.yaml
git commit -m "tune(m53): Pass 1f — artifact constants (M52)"
```

---

## Task 21: Integration Pass + Freeze

**Files:**
- Modify: `chronicler-agents/src/agent.rs` (tag updates: `[CALIBRATE M53]` → `[FROZEN M53 HARD/SOFT]`)
- Modify: `tuning/m53a_frozen.yaml` (final freeze record)
- Modify: possibly `chronicler-agents/src/satisfaction.rs` (if cap budget rebalancing needed)

- [ ] **Step 1: Run full integration gate**

Run: `PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 500 --agents hybrid --simulate-only --batch 200 --parallel 12 --output output/m53/integration/chronicle.md`

- [ ] **Step 2: Check cross-system metrics**

- Satisfaction floor-hitting: <30% of any region's agents at floor simultaneously
- Total rebel modifier: within intended budget
- Migration stability: no sloshing
- Rebellion rate: 2-8% of agent-turns
- Migration rate: 5-15%
- Occupation distribution: no collapse
- Civ survival: 1-4 civs alive at turn 500

- [ ] **Step 3: If integration issues found — rebalance**

Identify primary contributing system, re-run that pass, re-run integration. If satisfaction.rs constants need adjustment, promote to `[CALIBRATE M53-INTEGRATION]` tag.

- [ ] **Step 4: Run regression suite**

Determinism gate + behavioral regression (Section 7 of spec). All metrics within acceptable ranges.

- [ ] **Step 5: Finalize freeze**

- Update all source tags: `[CALIBRATE M53]` → `[FROZEN M53 HARD]` or `[FROZEN M53 SOFT]`
- Finalize `tuning/m53a_frozen.yaml` with all constant values and tier assignments
- Document any satisfaction.rs constants adjusted under `M53-INTEGRATION`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "tune(m53): integration pass complete — all constants frozen"
```

---

## Task 22: Run Oracle Suite (M53b)

**Files:**
- Modify: `docs/superpowers/analytics/m53b-validation-report.md`

- [ ] **Step 1: Generate oracle subset with raw sidecars**

Run seeds 42-61 (20 seeds) with full validation sidecar:
```bash
PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 500 --agents hybrid --simulate-only --batch 20 --parallel 12 --validation-sidecar --output output/m53/oracle_subset/chronicle.md
```

- [ ] **Step 2: Run all oracles**

```bash
python -m chronicler.validate --batch-dir output/batch_42 --oracles all
```

- [ ] **Step 3: Check blocking oracle acceptance criteria**

- Oracle 1 (Community): >=15/20 seeds with qualifying communities
- Oracle 2 (Needs Diversity): median effect >0.1, >=12/20 expected sign
- Oracle 3 (Era Inflection): >=80% seeds with >=2 inflection points
- Oracle 4 (Cohort Distinctiveness): >=12/20 expected direction

- [ ] **Step 4: Check committed oracle criteria**

- Oracle 5 (Artifacts): creation rate 1-3/civ/100turns, type diversity, loss rate
- Oracle 6 (Six Arcs): 5 of 6 families across 200 seeds

- [ ] **Step 5: Run narration sample for narrative-facing checks**

Run 10-seed narration sample for era inflection alignment and artifact narrative visibility:
```bash
PYTHONHASHSEED=0 python -m chronicler --seed 42 --turns 500 --agents hybrid --narrator api --batch 10 --output output/m53/narration_sample/chronicle.md
```

- [ ] **Step 6: Write validation report**

Create `docs/superpowers/analytics/m53b-validation-report.md` with oracle results, acceptance criteria pass/fail, any informational findings.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/analytics/m53b-validation-report.md
git commit -m "docs(m53): M53b validation report — all oracles pass"
```

---

## Task 23: Final Gate + Progress Update

- [ ] **Step 1: Verify M53a + M53b both pass**

All completion criteria from spec Section 8.

- [ ] **Step 2: Update progress doc**

Update `docs/superpowers/progress/phase-6-progress.md`:
- Move M53a/b to Merged section
- Document frozen constant summary
- Note any gotchas for M54a

- [ ] **Step 3: Final commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m53): M53 complete — depth tuning + validation gate passed"
```
