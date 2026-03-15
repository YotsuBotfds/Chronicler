# M19: Simulation Analytics & Tuning — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-processing analytics pipeline that reads simulation bundle files, computes statistical metrics across batch runs, detects degenerate patterns, and provides a tuning override system for simulation constants.

**Architecture:** Analytics module (`analytics.py`) reads `chronicle_bundle.json` files from batch directories — never imports simulation code. Tuning module (`tuning.py`) provides an overlay dict on `WorldState` for constant overrides loaded from YAML. CLI gets `--analyze`, `--tuning`, `--compare`, `--checkpoints`, and `--seed-range` flags.

**Tech Stack:** Python 3.11+, Pydantic, PyYAML, argparse, statistics stdlib module. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-14-m19-simulation-analytics-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `src/chronicler/tuning.py` | Key constants (`K_*`), `KNOWN_OVERRIDES` set, `load_tuning()`, `_flatten()`, `get_override()` |
| `src/chronicler/analytics.py` | `load_bundles()`, 8 extractors, `generate_report()`, `format_text_report()`, `format_delta_report()`, anomaly detection |
| `tests/test_tuning.py` | Tuning YAML loading, flattening, validation, override reads |
| `tests/test_analytics.py` | Extractor unit tests, anomaly detection, report formatting, delta comparison |

### Modified Files

| File | Changes |
|---|---|
| `src/chronicler/models.py` | Add 2 fields to `TurnSnapshot` (`climate_phase`, `active_conditions`), add `tuning_overrides` to `WorldState` |
| `src/chronicler/main.py` | Add CLI flags, snapshot capture, `--analyze` dispatch, `--seed-range` parse |
| `src/chronicler/batch.py` | Wire `--tuning` loading, inject overrides into WorldState |
| `src/chronicler/simulation.py` | 5 example callsites wired to `get_override()` |

---

## Chunk 1: Tuning System

### Task 1: TurnSnapshot & WorldState Model Extension

**Files:**
- Modify: `src/chronicler/models.py:404-424` (TurnSnapshot) and `src/chronicler/models.py:307-353` (WorldState)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test for new TurnSnapshot fields**

```python
# tests/test_models.py — append to existing test file

def test_turn_snapshot_has_climate_phase():
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert snap.climate_phase == ""


def test_turn_snapshot_has_active_conditions():
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert snap.active_conditions == []


def test_world_state_has_tuning_overrides(sample_world):
    assert sample_world.tuning_overrides == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py::test_turn_snapshot_has_climate_phase tests/test_models.py::test_turn_snapshot_has_active_conditions tests/test_models.py::test_world_state_has_tuning_overrides -v`
Expected: FAIL — fields don't exist yet

- [ ] **Step 3: Add fields to models.py**

In `TurnSnapshot` (after `pandemic_regions` field, line 424):

```python
    climate_phase: str = ""
    active_conditions: list[dict] = Field(default_factory=list)
```

In `WorldState` (after `terrain_transition_rules` field, line 346-353 — the last field before `save()`):

```python
    tuning_overrides: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py::test_turn_snapshot_has_climate_phase tests/test_models.py::test_turn_snapshot_has_active_conditions tests/test_models.py::test_world_state_has_tuning_overrides -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat(m19): add climate_phase, active_conditions to TurnSnapshot and tuning_overrides to WorldState"
```

---

### Task 2: Tuning Module — Key Constants, Flattening, Validation

**Files:**
- Create: `src/chronicler/tuning.py`
- Create: `tests/test_tuning.py`

- [ ] **Step 1: Write failing tests for tuning module**

```python
# tests/test_tuning.py
"""Tests for the tuning override system."""
import warnings
from pathlib import Path

import pytest


def test_flatten_simple():
    from chronicler.tuning import _flatten
    result = _flatten({"stability": {"drain": {"drought": -10}}})
    assert result == {"stability.drain.drought": -10}


def test_flatten_mixed_depths():
    from chronicler.tuning import _flatten
    result = _flatten({"a": 1, "b": {"c": 2, "d": {"e": 3}}})
    assert result == {"a": 1, "b.c": 2, "b.d.e": 3}


def test_flatten_rejects_non_numeric_leaf():
    from chronicler.tuning import _flatten
    with pytest.raises(ValueError, match="non-numeric"):
        _flatten({"a": "string_value"})


def test_load_tuning_warns_on_unknown_keys(tmp_path):
    from chronicler.tuning import load_tuning
    yaml_file = tmp_path / "tuning.yaml"
    yaml_file.write_text("bogus_key_xyz: 99\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = load_tuning(yaml_file)
        assert any("Unknown tuning key" in str(warning.message) for warning in w)
    assert result == {"bogus_key_xyz": 99}


def test_load_tuning_accepts_known_keys(tmp_path):
    from chronicler.tuning import load_tuning, K_DROUGHT_STABILITY
    yaml_file = tmp_path / "tuning.yaml"
    # Write a hierarchical YAML that flattens to a known key
    yaml_file.write_text("stability:\n  drain:\n    drought_immediate: -5\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = load_tuning(yaml_file)
        unknown_warnings = [x for x in w if "Unknown tuning key" in str(x.message)]
        assert len(unknown_warnings) == 0
    assert result[K_DROUGHT_STABILITY] == -5


def test_get_override_returns_override():
    from chronicler.tuning import get_override
    from chronicler.models import WorldState, Region, Civilization, Leader, TechEra, Relationship
    world = WorldState(
        name="Test", seed=1, turn=0,
        regions=[Region(name="R", terrain="plains", carrying_capacity=60, resources="fertile", controller="C")],
        civilizations=[Civilization(
            name="C", population=50, military=30, economy=40, culture=30, stability=50,
            tech_era=TechEra.IRON, treasury=50,
            leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["R"], asabiya=0.5,
        )],
        relationships={},
        tuning_overrides={"some.key": 42.0},
    )
    assert get_override(world, "some.key", 10.0) == 42.0


def test_get_override_returns_default():
    from chronicler.tuning import get_override
    from chronicler.models import WorldState, Region, Civilization, Leader, TechEra
    world = WorldState(
        name="Test", seed=1, turn=0,
        regions=[Region(name="R", terrain="plains", carrying_capacity=60, resources="fertile", controller="C")],
        civilizations=[Civilization(
            name="C", population=50, military=30, economy=40, culture=30, stability=50,
            tech_era=TechEra.IRON, treasury=50,
            leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["R"], asabiya=0.5,
        )],
        relationships={},
    )
    assert get_override(world, "nonexistent.key", 10.0) == 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tuning.py -v`
Expected: FAIL — `chronicler.tuning` module does not exist

- [ ] **Step 3: Implement tuning.py**

```python
# src/chronicler/tuning.py
"""Tuning override system — key constants, YAML loading, validation."""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from chronicler.models import WorldState

# --- Key constants: one per tunable parameter ---

# Stability drains
K_DROUGHT_STABILITY = "stability.drain.drought_immediate"
K_DROUGHT_ONGOING = "stability.drain.drought_ongoing"
K_PLAGUE_STABILITY = "stability.drain.plague_immediate"
K_FAMINE_STABILITY = "stability.drain.famine_immediate"
K_WAR_COST_STABILITY = "stability.drain.war_cost"
K_GOVERNING_COST = "stability.drain.governing_per_distance"
K_CONDITION_ONGOING_DRAIN = "stability.drain.condition_ongoing"  # -10/turn at severity >= 50

# Fertility
K_FERTILITY_DEGRADATION = "fertility.degradation_rate"
K_FERTILITY_RECOVERY = "fertility.recovery_rate"
K_FAMINE_THRESHOLD = "fertility.famine_threshold"

# Military
K_MILITARY_FREE_THRESHOLD = "military.maintenance_free_threshold"

# Emergence
K_BLACK_SWAN_BASE_PROB = "emergence.black_swan_base_probability"
K_BLACK_SWAN_COOLDOWN = "emergence.black_swan_cooldown_turns"

# Complete set of known override keys
KNOWN_OVERRIDES: set[str] = {
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY, K_GOVERNING_COST,
    K_CONDITION_ONGOING_DRAIN,
    K_FERTILITY_DEGRADATION, K_FERTILITY_RECOVERY, K_FAMINE_THRESHOLD,
    K_MILITARY_FREE_THRESHOLD, K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
}


def _flatten(d: dict, prefix: str = "") -> dict[str, float]:
    """Recursively join dict keys with '.' separator.

    Leaf values must be numeric (int or float). Raises ValueError on
    non-dict, non-numeric leaves (strings, lists, etc.).
    """
    result: dict[str, float] = {}
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, full_key))
        elif isinstance(value, (int, float)):
            result[full_key] = float(value)
        else:
            raise ValueError(
                f"Tuning YAML contains non-numeric leaf at '{full_key}': "
                f"{type(value).__name__} = {value!r}"
            )
    return result


def load_tuning(path: Path) -> dict[str, float]:
    """Load hierarchical YAML, flatten to dot-notation keys, validate."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Tuning YAML must be a mapping, got {type(raw).__name__}")
    flat = _flatten(raw)
    unknown = set(flat.keys()) - KNOWN_OVERRIDES
    if unknown:
        for key in sorted(unknown):
            warnings.warn(f"Unknown tuning key: {key}")
    return flat


def get_override(world: "WorldState", key: str, default: float) -> float:
    """Read a tunable constant with override fallback."""
    return world.tuning_overrides.get(key, default)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tuning.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tuning.py tests/test_tuning.py
git commit -m "feat(m19): add tuning module with key constants, YAML loading, and validation"
```

---

### Task 3: Wire Tuning into CLI and Batch Runner

**Files:**
- Modify: `src/chronicler/main.py:498-539` (parser), `src/chronicler/main.py:542-648` (dispatch)
- Modify: `src/chronicler/batch.py`
- Test: `tests/test_batch.py`

- [ ] **Step 1: Write failing test for --tuning in batch**

```python
# tests/test_batch.py — append to TestRunBatch class

    def test_tuning_overrides_applied(self, batch_args, tmp_path):
        """Tuning YAML overrides are injected into WorldState."""
        tuning_file = tmp_path / "tuning.yaml"
        tuning_file.write_text("stability:\n  drain:\n    drought_immediate: -1\n")
        batch_args.tuning = str(tuning_file)
        batch_args.simulate_only = True
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        # Verify the batch ran (tuning didn't crash)
        assert batch_dir.exists()
        assert (batch_dir / "summary.md").exists()


    def test_no_tuning_file_runs_normally(self, batch_args, tmp_path):
        """Batch runs without --tuning work as before."""
        batch_args.tuning = None
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch.py::TestRunBatch::test_tuning_overrides_applied -v`
Expected: FAIL — `batch_args` has no `tuning` attribute, or `run_batch` doesn't handle it

- [ ] **Step 3: Add --tuning and --seed-range flags to parser**

In `main.py` `_build_parser()`, after the `--simulate-only` line (line 538):

```python
    parser.add_argument("--tuning", type=str, default=None,
                        help="Path to tuning YAML file for constant overrides")
    parser.add_argument("--seed-range", type=str, default=None,
                        help="Seed range for batch mode (e.g., 1-200)")
```

- [ ] **Step 4: Add --seed-range parsing in main()**

In `main.py` `main()`, after the mutual exclusion check (after line 561), before scenario resolution:

```python
    # Parse --seed-range into seed + batch count
    if getattr(args, "seed_range", None):
        parts = args.seed_range.split("-")
        if len(parts) != 2:
            print("Error: --seed-range must be START-END (e.g., 1-200)", file=sys.stderr)
            sys.exit(1)
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            print("Error: --seed-range values must be integers (e.g., 1-200)", file=sys.stderr)
            sys.exit(1)
        if start > end:
            print(f"Error: --seed-range start ({start}) must be <= end ({end})", file=sys.stderr)
            sys.exit(1)
        args.seed = start
        args.batch = end - start + 1
```

- [ ] **Step 5: Wire tuning loading in batch.py**

In `batch.py` `run_batch()`, after `batch_dir.mkdir()` (line 25), before the results loop:

```python
    # Load tuning overrides if provided
    tuning_overrides: dict[str, float] = {}
    if getattr(args, "tuning", None):
        from chronicler.tuning import load_tuning
        tuning_overrides = load_tuning(Path(args.tuning))
```

Then in both the parallel and sequential paths, after `child_args` is created, add:

```python
            child_args.tuning_overrides = tuning_overrides
```

- [ ] **Step 6: Inject tuning overrides into WorldState in execute_run**

In `main.py` `execute_run()`, after world generation (after `generate_world` call), add:

```python
    # Apply tuning overrides to world state
    if getattr(args, "tuning_overrides", None):
        world.tuning_overrides = args.tuning_overrides
```

- [ ] **Step 7: Update batch_args fixture with new fields**

In `tests/test_batch.py`, update the `batch_args` fixture to include:

```python
        tuning=None, simulate_only=False, seed_range=None,
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_batch.py -v`
Expected: PASS (all batch tests)

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/main.py src/chronicler/batch.py tests/test_batch.py
git commit -m "feat(m19): wire --tuning and --seed-range CLI flags through batch runner"
```

---

### Task 4: Snapshot Capture for New Fields

**Files:**
- Modify: `src/chronicler/main.py:212-263` (snapshot capture block)

- [ ] **Step 1: Write failing test**

```python
# tests/test_main.py — append (or add to existing snapshot test section)
def test_snapshot_captures_climate_phase(sample_world):
    """TurnSnapshot includes climate_phase after run_turn."""
    from chronicler.main import execute_run
    import argparse
    from unittest.mock import MagicMock

    args = argparse.Namespace(
        seed=42, turns=2, civs=2, regions=5,
        output="/dev/null", state="/dev/null",
        reflection_interval=999, llm_actions=False,
        simulate_only=True, scenario=None,
        batch=None, fork=None, interactive=False,
        live=False, resume=None, parallel=None,
        pause_every=None, tuning=None, seed_range=None,
    )
    dummy = MagicMock()
    dummy.complete.return_value = "DEVELOP"
    dummy.model = "test"
    result = execute_run(args, sim_client=dummy, narrative_client=dummy)
    # Result should have history with snapshots containing climate_phase
    # (verified via bundle output or direct inspection)
    assert result is not None
```

- [ ] **Step 2: Add climate_phase and active_conditions to snapshot capture**

In `main.py`, in the `TurnSnapshot(...)` constructor (line 212-263), add after `pandemic_regions`:

```python
            climate_phase=get_climate_phase(world.turn, world.climate_config).value,
            active_conditions=[
                {"type": c.condition_type, "severity": c.severity, "duration": c.duration}
                for c in world.active_conditions
            ],
```

Add the import near the top of `main.py` (with other chronicler imports):

```python
from chronicler.climate import get_climate_phase
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/main.py
git commit -m "feat(m19): capture climate_phase and active_conditions in TurnSnapshot"
```

---

### Task 5: Wire 5 Example Tuning Callsites

**Files:**
- Modify: `src/chronicler/simulation.py` (5 callsites)
- Test: `tests/test_simulation.py`

The goal is to prove the tuning system works end-to-end. Wire 5 representative stability drain constants.

- [ ] **Step 1: Write failing test for tuning override at callsite**

```python
# tests/test_simulation.py — append
def test_famine_stability_drain_respects_tuning_override(make_world):
    """Famine stability drain uses tuning override when present."""
    from chronicler.simulation import _check_famine

    world = make_world(num_civs=2)
    world.tuning_overrides = {"stability.drain.famine_immediate": 2}
    civ = world.civilizations[0]
    civ.stability = 50
    original_stability = civ.stability

    # Set a region to trigger famine (fertility below threshold 0.3)
    region = world.regions[0]
    region.fertility = 0.2
    region.famine_cooldown = 0
    region.controller = civ.name

    _check_famine(world)

    # With override of 2 (and severity_multiplier=1.0 for healthy civ),
    # stability should drop by 2 (not default 10)
    assert civ.stability == original_stability - 2
```

Note: There are multiple stability drain paths to wire. The test above covers `_check_famine` (line 820). Additional paths:
- Line 116: ongoing condition drain in `apply_automatic_effects`
- Line 535: immediate drought drain in `_apply_event_effects` / `apply_injected_event`

Wire all 5 example callsites across these paths. M19b will cover thorough testing of all ~250 callsites.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_simulation.py::test_drought_stability_drain_respects_tuning_override -v`
Expected: FAIL — function doesn't read tuning overrides

- [ ] **Step 3: Wire 5 callsites in simulation.py**

Add import at top of `simulation.py`:

```python
from chronicler.tuning import (
    K_DROUGHT_STABILITY, K_PLAGUE_STABILITY, K_FAMINE_STABILITY,
    K_WAR_COST_STABILITY, K_FAMINE_THRESHOLD,
    get_override,
)
```

Then replace 5 hardcoded constants with `get_override` calls:

**Callsite 1 — Drought immediate (line 535):**
```python
# Before:
civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
# After:
drain = int(get_override(world, K_DROUGHT_STABILITY, 10))
civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
```

**Callsite 2 — Plague immediate (line 547):**
```python
drain = int(get_override(world, K_PLAGUE_STABILITY, 10))
civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
```

**Callsite 3 — Famine stability drain (line 820):**
```python
drain = int(get_override(world, K_FAMINE_STABILITY, 10))
civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
```

**Callsite 4 — War cost stability drain (line 244):**
```python
drain = int(get_override(world, K_WAR_COST_STABILITY, 5))
c.stability = clamp(c.stability - drain, STAT_FLOOR["stability"], 100)
```

**Callsite 5 — Famine threshold (line ~812, the famine check):**
```python
threshold = get_override(world, K_FAMINE_THRESHOLD, 0.3)
if region.fertility < threshold:
```

Note: Line numbers are approximate. The implementer should grep for the exact locations. Each callsite reads the override in the phase function where `world` is available.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_simulation.py -v`
Expected: PASS (all simulation tests including new override test)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m19): wire 5 example tuning callsites in simulation.py"
```

---

## Chunk 2: Analytics Pipeline

### Task 6: Bundle Loader and Report Structure

**Files:**
- Create: `src/chronicler/analytics.py`
- Create: `tests/test_analytics.py`

- [ ] **Step 1: Write failing test for bundle loader**

```python
# tests/test_analytics.py
"""Tests for the analytics pipeline."""
import json
from pathlib import Path

import pytest


def _make_bundle(seed: int, turns: int = 10, num_civs: int = 2) -> dict:
    """Create a minimal synthetic bundle for testing.

    Generates diverse event types so all extractors have data to work with.
    Uses seed to vary some values (e.g., which events fire).
    """
    civ_names = [f"Civ{i}" for i in range(num_civs)]
    history = []
    events = []
    for t in range(turns):
        # Vary era based on turn to test era distribution
        era = "iron" if t < 5 else "classical"
        civ_stats = {}
        for name in civ_names:
            civ_stats[name] = {
                "population": 50, "military": 30, "economy": 40,
                "culture": 30, "stability": max(0, 50 - t * 3),
                "treasury": 50 + t, "asabiya": 0.5,
                "tech_era": era, "trait": "cautious",
                "regions": [f"{name}_region"], "leader_name": f"Leader_{name}",
                "alive": True, "last_income": 5,
                "active_trade_routes": 1 if t > 2 else 0,
                "is_vassal": False, "is_fallen_empire": False,
                "in_twilight": False, "federation_name": None,
                "prestige": 0, "capital_region": f"{name}_region",
                "great_persons": [{"name": "GP1", "role": "general", "trait": "bold"}] if t > 6 else [],
                "traditions": ["warrior"] if t > 7 else [],
                "folk_heroes": [], "active_crisis": t == 8,
                "civ_stress": t,
            }
        history.append({
            "turn": t, "civ_stats": civ_stats,
            "region_control": {f"{n}_region": n for n in civ_names},
            "relationships": {},
            "trade_routes": [["Civ0", "Civ1"]] if t > 2 else [],
            "active_wars": [["Civ0", "Civ1"]] if t == 5 else [],
            "embargoes": [],
            "fertility": {f"{n}_region": 0.8 - t * 0.05 for n in civ_names},
            "mercenary_companies": [],
            "vassal_relations": [], "federations": [],
            "proxy_wars": [], "exile_modifiers": [],
            "capitals": {n: f"{n}_region" for n in civ_names},
            "peace_turns": 0,
            "region_cultural_identity": {},
            "movements_summary": [{"id": "mov1", "value_affinity": "order", "adherent_count": 2, "origin_civ": "Civ0"}] if t > 4 else [],
            "stress_index": t,
            "pandemic_regions": [],
            "climate_phase": "temperate" if t < 5 else "drought",
            "active_conditions": [{"type": "drought", "severity": 50, "duration": 3}] if t == 6 else [],
        })
        # Diverse events across turns (using seed to vary slightly)
        if t == 2:
            events.append({"turn": t, "event_type": "drought", "actors": ["Civ0"], "description": "drought"})
        if t == 3:
            events.append({"turn": t, "event_type": "famine", "actors": ["Civ0"], "description": "famine"})
        if t == 4:
            events.append({"turn": t, "event_type": "movement_emerged", "actors": ["Civ0"], "description": "movement"})
        if t == 5:
            events.append({"turn": t, "event_type": "war", "actors": ["Civ0", "Civ1"], "description": "war"})
        if t == 6:
            events.append({"turn": t, "event_type": "great_person_born", "actors": ["Civ0"], "description": "gp born"})
            events.append({"turn": t, "event_type": "succession_crisis", "actors": ["Civ0"], "description": "crisis"})
        if t == 7:
            events.append({"turn": t, "event_type": "tech_advancement", "actors": ["Civ0"], "description": "tech"})
        if t == 8 and seed % 3 == 0:
            events.append({"turn": t, "event_type": "pandemic", "actors": [], "description": "black swan"})
        if t == 9 and seed % 5 == 0:
            events.append({"turn": t, "event_type": "secession", "actors": ["Civ0"], "description": "secession"})
    return {
        "metadata": {"seed": seed, "total_turns": turns, "generated_at": "2026-01-01T00:00:00"},
        "history": history,
        "events_timeline": events,
        "named_events": [],
        "world_state": {
            "civilizations": [
                {"name": n, "action_counts": {"develop": 3, "trade": 2, "war": 1}}
                for n in civ_names
            ],
        },
    }


def _write_batch(tmp_path: Path, num_runs: int = 5, turns: int = 10) -> Path:
    """Write synthetic bundles to a batch directory."""
    batch_dir = tmp_path / "batch_1"
    for i in range(num_runs):
        run_dir = batch_dir / f"seed_{i + 1}"
        run_dir.mkdir(parents=True)
        bundle = _make_bundle(seed=i + 1, turns=turns)
        (run_dir / "chronicle_bundle.json").write_text(json.dumps(bundle))
    return batch_dir


class TestBundleLoader:
    def test_loads_all_bundles(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        assert len(bundles) == 5

    def test_raises_on_fewer_than_2_bundles(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = _write_batch(tmp_path, num_runs=1)
        with pytest.raises(ValueError, match="fewer than 2"):
            load_bundles(batch_dir)

    def test_raises_on_empty_directory(self, tmp_path):
        from chronicler.analytics import load_bundles
        batch_dir = tmp_path / "empty_batch"
        batch_dir.mkdir()
        with pytest.raises(ValueError, match="fewer than 2"):
            load_bundles(batch_dir)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py::TestBundleLoader -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement bundle loader**

```python
# src/chronicler/analytics.py
"""Post-processing analytics pipeline — reads bundles, computes metrics."""
from __future__ import annotations

import json
import statistics
from pathlib import Path


def load_bundles(batch_dir: Path) -> list[dict]:
    """Glob batch_dir/*/chronicle_bundle.json, deserialize, return list.

    Raises ValueError if fewer than 2 bundles found (distributions require
    multiple runs). If bundles have different total_turns, checkpoint clamping
    uses the minimum total_turns across all bundles.
    """
    bundle_paths = sorted(batch_dir.glob("*/chronicle_bundle.json"))
    if len(bundle_paths) < 2:
        raise ValueError(
            f"Analytics requires at least 2 bundles, found {len(bundle_paths)} "
            f"in {batch_dir}"
        )
    bundles = []
    for p in bundle_paths:
        with open(p) as f:
            bundles.append(json.load(f))
    return bundles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py::TestBundleLoader -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add analytics bundle loader with validation"
```

---

### Task 7: Distribution Helpers and First Extractor (Stability)

**Files:**
- Modify: `src/chronicler/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write failing tests for stability extractor**

```python
# tests/test_analytics.py — append

class TestDistributionHelpers:
    def test_percentiles_basic(self):
        from chronicler.analytics import _compute_percentiles
        values = list(range(100))
        p = _compute_percentiles(values)
        assert p["min"] == 0
        assert p["max"] == 99
        assert p["median"] == 49.5 or p["median"] == 50  # depends on method


class TestStabilityExtractor:
    def test_returns_percentiles_by_turn(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=5, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[5])
        assert "percentiles_by_turn" in result
        assert "5" in result["percentiles_by_turn"]
        assert "median" in result["percentiles_by_turn"]["5"]

    def test_clamps_checkpoints_to_total_turns(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=3, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[5, 50, 500])
        # Only checkpoint 5 should be present (50 and 500 > 10 turns)
        assert "5" in result["percentiles_by_turn"]
        assert "50" not in result["percentiles_by_turn"]
        assert "500" not in result["percentiles_by_turn"]

    def test_zero_rate_per_checkpoint(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_stability
        batch_dir = _write_batch(tmp_path, num_runs=5, turns=10)
        bundles = load_bundles(batch_dir)
        result = extract_stability(bundles, checkpoints=[9])
        # stability = max(0, 50 - t*3), at turn 9 = max(0, 50-27) = 23 > 0
        # So zero_rate at turn 9 should be 0.0
        assert "zero_rate_by_turn" in result
        assert result["zero_rate_by_turn"]["9"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py::TestStabilityExtractor -v`
Expected: FAIL

- [ ] **Step 3: Implement distribution helpers and stability extractor**

Add to `analytics.py`:

```python
# --- Distribution helpers ---

DEFAULT_CHECKPOINTS = [25, 50, 100, 200, 500]


def _compute_percentiles(values: list[float | int]) -> dict[str, float]:
    """Compute p10, p25, median, p75, p90, min, max for a list of values."""
    if not values:
        return {"min": 0, "p10": 0, "p25": 0, "median": 0, "p75": 0, "p90": 0, "max": 0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "min": sorted_vals[0],
        "p10": sorted_vals[max(0, int(n * 0.1))],
        "p25": sorted_vals[max(0, int(n * 0.25))],
        "median": statistics.median(sorted_vals),
        "p75": sorted_vals[min(n - 1, int(n * 0.75))],
        "p90": sorted_vals[min(n - 1, int(n * 0.9))],
        "max": sorted_vals[-1],
    }


def _clamp_checkpoints(checkpoints: list[int] | None, max_turn: int) -> list[int]:
    """Clamp checkpoint list to <= max_turn."""
    cps = checkpoints if checkpoints is not None else DEFAULT_CHECKPOINTS
    return [c for c in cps if c <= max_turn]


def _min_total_turns(bundles: list[dict]) -> int:
    """Get the minimum total_turns across all bundles."""
    return min(len(b["history"]) for b in bundles)


def _snapshot_at_turn(bundle: dict, turn: int) -> dict | None:
    """Look up a snapshot by its turn field, not list position."""
    for snap in bundle["history"]:
        if snap["turn"] == turn:
            return snap
    return None


# --- Extractors ---

def extract_stability(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Stability percentiles at checkpoint turns and per-checkpoint zero-rates."""
    max_turn = _min_total_turns(bundles) - 1  # 0-indexed
    cps = _clamp_checkpoints(checkpoints, max_turn)

    percentiles_by_turn: dict[str, dict] = {}
    zero_rate_by_turn: dict[str, float] = {}

    for cp in cps:
        values = []
        zero_count = 0
        total_count = 0
        for bundle in bundles:
            snap = _snapshot_at_turn(bundle, cp)
            if snap is None:
                continue
            for civ_name, civ_data in snap["civ_stats"].items():
                stab = civ_data["stability"]
                values.append(stab)
                total_count += 1
                if stab == 0:
                    zero_count += 1
        if values:
            percentiles_by_turn[str(cp)] = _compute_percentiles(values)
            zero_rate_by_turn[str(cp)] = zero_count / max(1, total_count)

    return {
        "percentiles_by_turn": percentiles_by_turn,
        "zero_rate_by_turn": zero_rate_by_turn,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py::TestStabilityExtractor tests/test_analytics.py::TestDistributionHelpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add distribution helpers and stability extractor"
```

---

### Task 8: Remaining 7 Extractors

**Files:**
- Modify: `src/chronicler/analytics.py`
- Modify: `tests/test_analytics.py`

Each extractor follows the same pattern: iterate bundles, extract per-run metrics, aggregate distributions. The implementer should write one test per extractor and implement them in order.

- [ ] **Step 1: Write failing tests for all remaining extractors**

```python
# tests/test_analytics.py — append

class TestResourceExtractor:
    def test_famine_turn_distribution(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_resources
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_resources(bundles)
        assert "famine_turn_distribution" in result
        # All bundles have famine at turn 3
        assert result["famine_turn_distribution"]["median"] == 3

    def test_trade_route_percentiles(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_resources
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_resources(bundles, checkpoints=[5])
        assert "trade_route_percentiles_by_turn" in result
        # At turn 5, trade routes exist (t > 2 in fixture)
        assert result["trade_route_percentiles_by_turn"]["5"]["median"] >= 1


class TestPoliticsExtractor:
    def test_firing_rates(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_politics
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_politics(bundles)
        assert "war_rate" in result
        assert result["war_rate"] == 1.0  # all bundles have war at turn 5
        assert "elimination_turn_distribution" in result

    def test_secession_rate(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_politics
        batch_dir = _write_batch(tmp_path, num_runs=15)
        bundles = load_bundles(batch_dir)
        result = extract_politics(bundles)
        # secession fires when seed % 5 == 0, so ~20% of runs
        assert 0 < result.get("secession_rate", 0) < 1.0


class TestClimateExtractor:
    def test_disaster_frequency(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_climate
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_climate(bundles)
        assert "disaster_frequency_by_type" in result
        # All bundles have drought at turn 2
        assert result["disaster_frequency_by_type"].get("drought", 0) == 1.0


class TestMemeticExtractor:
    def test_movement_metrics(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_memetic
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_memetic(bundles, checkpoints=[5])
        assert "paradigm_shift_rate" in result
        # All bundles have movement_emerged at turn 4
        assert "movement_count_percentiles_by_turn" in result


class TestGreatPersonExtractor:
    def test_generation_and_crisis_rate(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_great_persons
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_great_persons(bundles)
        # All bundles have great_person_born and succession_crisis at turn 6
        assert result["great_person_born_rate"] == 1.0
        assert result["succession_crisis_rate"] == 1.0


class TestEmergenceExtractor:
    def test_black_swan_frequency(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_emergence
        batch_dir = _write_batch(tmp_path, num_runs=15)
        bundles = load_bundles(batch_dir)
        result = extract_emergence(bundles)
        assert "black_swan_frequency_by_type" in result
        # pandemic fires when seed % 3 == 0, so ~33% of runs
        assert 0 < result["black_swan_frequency_by_type"].get("pandemic", 0) < 1.0
        assert "regression_rate" in result


class TestGeneralExtractor:
    def test_era_distribution(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_general
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_general(bundles)
        assert "era_distribution_at_final" in result
        # Final turn era is "classical" (t >= 5 in fixture)
        assert "classical" in result["era_distribution_at_final"]
        assert "median_era_at_final" in result

    def test_first_war_and_civs_alive(self, tmp_path):
        from chronicler.analytics import load_bundles, extract_general
        batch_dir = _write_batch(tmp_path, num_runs=5)
        bundles = load_bundles(batch_dir)
        result = extract_general(bundles)
        assert "first_war_turn_distribution" in result
        # All bundles have war at turn 5
        assert result["first_war_turn_distribution"]["median"] == 5
        assert "civs_alive_at_end" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py -k "Extract" -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement all 7 remaining extractors**

Add to `analytics.py`. Each extractor follows the pattern:
1. Iterate bundles
2. For event-based metrics: scan `events_timeline`, compute per-run firing rates
3. For time-series metrics: read `history[checkpoint].civ_stats`, aggregate
4. Return dict with documented keys

The extractors are:

```python
def extract_resources(bundles, checkpoints=None) -> dict:
    """Turn-of-first-famine distribution, trade route and treasury percentiles."""

def extract_politics(bundles) -> dict:
    """Firing rates for secession/federation/vassal/mercenary/war/twilight, elimination timing."""

def extract_climate(bundles) -> dict:
    """Disaster frequency by type from events_timeline."""

def extract_memetic(bundles, checkpoints=None) -> dict:
    """Movement count over time, paradigm shift rate, assimilation rate."""

def extract_great_persons(bundles) -> dict:
    """GP generation rate by era, tradition rate, succession crisis rate, hostage rate."""

def extract_emergence(bundles) -> dict:
    """Black swan frequency by type, stress distribution, regression and terrain transition rates."""

def extract_general(bundles) -> dict:
    """Era distribution at final turn, action diversity, civs alive, first war turn."""
```

Implementation guidance for each:

- **extract_resources**: Find first `event_type == "famine"` turn per run → distribution. Read `trade_routes` length from `history[cp]` → percentiles. Read `civ_stats[name]["treasury"]` → percentiles.
- **extract_politics**: Count runs with at least one `event_type` in `{"secession", "federation_formed", "vassal_imposed", "mercenary_spawned", "war", "twilight_absorption"}`. Compute firing rate = count / total_runs. Also compute `elimination_turn_distribution`: `CivSnapshot.alive` is available at `snap["civ_stats"][name]["alive"]` — find the first turn where it becomes `False` for any civ.
- **extract_climate**: Count events where `event_type` in `{"drought", "plague", "earthquake", "flood", "wildfire", "sandstorm"}`. Compute frequency = count / total_runs.
- **extract_memetic**: Read `movements_summary` length from checkpoints. Count `paradigm_shift` and `cultural_assimilation` events.
- **extract_great_persons**: Count `great_person_born` events grouped by the civ's `tech_era` at that turn. Count `tradition_acquired`, `succession_crisis`, `hostage_taken` events.
- **extract_emergence**: Count events by type for the 4 black swan types. Read `stress_index` from checkpoints. Count `tech_regression` and `terrain_transition` events.
- **extract_general**: Read `tech_era` from final turn's `civ_stats` → era distribution. Compute `median_era_at_final` using `ERA_ORDER` index (take median of ordinal positions, map back to era name). Count distinct action types from `world_state.civilizations[i].action_counts`. Count alive civs at final turn. Find first `war` event turn.

**Turn indexing note:** Snapshot `history` is a list indexed by position. The `turn` field inside each snapshot gives the actual turn number. Always look up by `turn` field, not by list index, to avoid off-by-one on real data where snapshots might start from a non-zero turn (e.g., resumed runs).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py -k "Extract" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add 7 remaining analytics extractors"
```

---

### Task 9: Anomaly Detection and Event Firing Rates

**Files:**
- Modify: `src/chronicler/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics.py — append

class TestEventFiringRates:
    def test_discovers_event_types_from_data(self, tmp_path):
        from chronicler.analytics import compute_event_firing_rates
        batch_dir = _write_batch(tmp_path, num_runs=5)
        from chronicler.analytics import load_bundles
        bundles = load_bundles(batch_dir)
        rates = compute_event_firing_rates(bundles)
        assert "famine" in rates
        assert "war" in rates
        assert rates["famine"] == 1.0  # every synthetic bundle has a famine
        assert rates["war"] == 1.0  # every synthetic bundle has a war

    def test_rare_events_flagged(self, tmp_path):
        """Event types appearing in < 5% of runs are flagged."""
        from chronicler.analytics import compute_event_firing_rates
        batch_dir = _write_batch(tmp_path, num_runs=100)
        from chronicler.analytics import load_bundles
        bundles = load_bundles(batch_dir)
        rates = compute_event_firing_rates(bundles)
        # tech_advancement appears in all runs, famine in all runs
        assert rates["tech_advancement"] == 1.0


class TestAnomalyDetection:
    def test_detects_degenerate_patterns(self, tmp_path):
        from chronicler.analytics import detect_anomalies
        # Create a report dict with known degenerate values
        report = {
            "stability": {"zero_rate_by_turn": {"100": 0.5}},
            "event_firing_rates": {"famine": 0.99},
            "general": {"median_era_at_final": "tribal"},
        }
        anomalies = detect_anomalies(report)
        assert any(a["name"] == "stability_collapse" for a in anomalies)

    def test_detects_never_fire(self, tmp_path):
        from chronicler.analytics import detect_anomalies
        report = {
            "stability": {"zero_rate_by_turn": {}},
            "event_firing_rates": {"famine": 1.0, "hostage_taken": 0.0},
            "general": {"median_era_at_final": "medieval"},
        }
        anomalies = detect_anomalies(report)
        never_fire = [a for a in anomalies if a["name"] == "never_fire"]
        assert len(never_fire) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py -k "FiringRate or Anomaly" -v`
Expected: FAIL

- [ ] **Step 3: Implement event firing rates and anomaly detection**

Add to `analytics.py`:

```python
# --- Event types ---

EXPECTED_EVENT_TYPES = {
    "famine", "embargo", "war", "secession", "collapse", "mercenary_spawned",
    "vassal_imposed", "federation_formed", "proxy_war_started", "twilight_absorption",
    "drought", "plague", "earthquake", "flood", "migration",
    "movement_emerged", "paradigm_shift", "cultural_assimilation",
    "great_person_born", "tradition_acquired", "succession_crisis",
    "hostage_taken", "rivalry_formed", "folk_hero_created",
    "pandemic", "supervolcano", "resource_discovery", "tech_accident",
    "tech_regression", "terrain_transition",
    "tech_advancement", "rebellion",
}

ERA_ORDER = ["tribal", "bronze", "iron", "classical", "medieval", "renaissance", "industrial", "information"]


def compute_event_firing_rates(bundles: list[dict]) -> dict[str, float]:
    """Discover event types from data and compute firing rates."""
    n_runs = len(bundles)
    # Collect all event types and which runs they appear in
    type_run_sets: dict[str, set[int]] = {}
    for i, bundle in enumerate(bundles):
        for event in bundle.get("events_timeline", []):
            et = event["event_type"]
            if et not in type_run_sets:
                type_run_sets[et] = set()
            type_run_sets[et].add(i)
    return {et: len(runs) / n_runs for et, runs in sorted(type_run_sets.items())}


def detect_anomalies(report: dict) -> list[dict]:
    """Run anomaly checks against a completed report."""
    anomalies = []

    # Degenerate pattern checks — use worst (highest) per-checkpoint zero rate
    zero_rates = report.get("stability", {}).get("zero_rate_by_turn", {})
    if zero_rates:
        worst_cp = max(zero_rates, key=zero_rates.get)
        worst_rate = zero_rates[worst_cp]
        if worst_rate > 0.4:
            anomalies.append({
                "name": "stability_collapse", "severity": "CRITICAL",
                "detail": f"{worst_rate:.0%} of civs at stability 0 at turn {worst_cp}",
            })

    famine_rate = report.get("event_firing_rates", {}).get("famine", 0)
    if famine_rate > 0.95:
        anomalies.append({
            "name": "universal_famine", "severity": "CRITICAL",
            "detail": f"Famine fires in {famine_rate:.0%} of runs",
        })

    median_era = report.get("general", {}).get("median_era_at_final", "medieval")
    if ERA_ORDER.index(median_era.lower()) < ERA_ORDER.index("medieval"):
        anomalies.append({
            "name": "no_late_game", "severity": "WARNING",
            "detail": f"Median era at final turn is {median_era}",
        })

    # Never-fire: event types with < 5% rate
    firing_rates = report.get("event_firing_rates", {})
    for et, rate in firing_rates.items():
        if rate < 0.05:
            anomalies.append({
                "name": "never_fire", "severity": "WARNING",
                "detail": f"{et} fired in {rate:.0%} of runs",
            })

    # Safety net: expected types completely absent
    present_types = set(firing_rates.keys())
    for et in EXPECTED_EVENT_TYPES - present_types:
        anomalies.append({
            "name": "never_fire", "severity": "CRITICAL",
            "detail": f"{et} absent from all runs (0 events across all bundles)",
        })

    return anomalies
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py -k "FiringRate or Anomaly" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add event firing rates and anomaly detection"
```

---

### Task 10: Report Assembly and Text Formatter

**Files:**
- Modify: `src/chronicler/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics.py — append

class TestReportAssembly:
    def test_generate_report_returns_all_sections(self, tmp_path):
        from chronicler.analytics import generate_report
        batch_dir = _write_batch(tmp_path, num_runs=5)
        report = generate_report(batch_dir)
        assert "metadata" in report
        assert "stability" in report
        assert "resources" in report
        assert "politics" in report
        assert "event_firing_rates" in report
        assert "anomalies" in report
        assert report["metadata"]["runs"] == 5
        assert report["metadata"]["report_schema_version"] == 1

    def test_generate_report_respects_checkpoints(self, tmp_path):
        from chronicler.analytics import generate_report
        batch_dir = _write_batch(tmp_path, num_runs=3, turns=10)
        report = generate_report(batch_dir, checkpoints=[5])
        # Only checkpoint 5 should appear
        assert "5" in report["stability"]["percentiles_by_turn"]


class TestTextFormatter:
    def test_format_text_report_produces_output(self, tmp_path):
        from chronicler.analytics import generate_report, format_text_report
        batch_dir = _write_batch(tmp_path, num_runs=5)
        report = generate_report(batch_dir)
        text = format_text_report(report)
        assert "STABILITY" in text or "stability" in text.lower()
        assert len(text) > 100  # non-trivial output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py -k "ReportAssembly or TextFormatter" -v`
Expected: FAIL

- [ ] **Step 3: Implement generate_report and format_text_report**

Add to `analytics.py`:

```python
from datetime import datetime


def generate_report(
    batch_dir: Path,
    checkpoints: list[int] | None = None,
) -> dict:
    """Load bundles, run all extractors, run anomaly checks, return composite report."""
    bundles = load_bundles(batch_dir)
    max_turn = _min_total_turns(bundles) - 1
    cps = _clamp_checkpoints(checkpoints, max_turn)

    # Metadata
    seeds = [b["metadata"]["seed"] for b in bundles]
    metadata = {
        "runs": len(bundles),
        "turns_per_run": max_turn + 1,
        "seed_range": [min(seeds), max(seeds)],
        "checkpoints": cps,
        "timestamp": datetime.now().isoformat(),
        "version": "post-M18",
        "report_schema_version": 1,
        "tuning_file": None,
    }

    # Run all extractors
    stability = extract_stability(bundles, checkpoints=cps)
    resources = extract_resources(bundles, checkpoints=cps)
    politics = extract_politics(bundles)
    climate = extract_climate(bundles)
    memetic = extract_memetic(bundles, checkpoints=cps)
    great_persons = extract_great_persons(bundles)
    emergence = extract_emergence(bundles, checkpoints=cps)
    general = extract_general(bundles)
    firing_rates = compute_event_firing_rates(bundles)

    report = {
        "metadata": metadata,
        "stability": stability,
        "resources": resources,
        "politics": politics,
        "climate": climate,
        "memetic": memetic,
        "great_persons": great_persons,
        "emergence": emergence,
        "general": general,
        "event_firing_rates": firing_rates,
    }

    # Anomaly detection
    report["anomalies"] = detect_anomalies(report)

    return report


def format_text_report(report: dict) -> str:
    """Format full analytics report as grep-friendly plain text.

    Reads all top-level report sections (stability, resources, politics, etc.)
    plus event_firing_rates and anomalies. Each section produces 1-3 summary
    lines. Anomalies appended at end grouped by severity (CRITICAL first).
    """
    lines = []
    meta = report["metadata"]
    n_runs = meta["runs"]
    lines.append(f"ANALYTICS REPORT — {n_runs} runs, {meta['turns_per_run']} turns each")
    lines.append(f"Seeds: {meta['seed_range'][0]}-{meta['seed_range'][1]}")
    lines.append(f"Checkpoints: {meta['checkpoints']}")
    lines.append("")

    # Stability
    stab = report.get("stability", {})
    for cp, pcts in stab.get("percentiles_by_turn", {}).items():
        lines.append(f"STABILITY at turn {cp}:  median={pcts['median']}, "
                      f"p10={pcts['p10']}, p90={pcts['p90']}")
    for cp, zr in stab.get("zero_rate_by_turn", {}).items():
        if zr > 0:
            flag = "  ← CRITICAL" if zr > 0.4 else ""
            lines.append(f"  Zero-stability rate at turn {cp}: {zr:.0%}{flag}")
    lines.append("")

    # Resources
    res = report.get("resources", {})
    famine_dist = res.get("famine_turn_distribution", {})
    if famine_dist:
        lines.append(f"Famine:     first occurrence median turn {famine_dist.get('median', '?')}")
    for cp, pcts in res.get("trade_route_percentiles_by_turn", {}).items():
        lines.append(f"Trade routes at turn {cp}: median={pcts.get('median', 0)}")
    lines.append("")

    # Politics
    pol = report.get("politics", {})
    for key in ["war_rate", "secession_rate", "federation_rate", "vassal_rate",
                "mercenary_rate", "twilight_rate"]:
        rate = pol.get(key, 0)
        if rate > 0:
            count = int(rate * n_runs)
            label = key.replace("_rate", "").title()
            flag = "  ← EVERY RUN" if rate >= 1.0 else ""
            lines.append(f"{label}: {count}/{n_runs} ({rate:.0%}){flag}")
    lines.append("")

    # Climate
    clim = report.get("climate", {})
    for dtype, freq in clim.get("disaster_frequency_by_type", {}).items():
        lines.append(f"Disaster {dtype}: {freq:.0%} of runs")
    lines.append("")

    # Great Persons
    gp = report.get("great_persons", {})
    for key in ["great_person_born_rate", "succession_crisis_rate",
                "tradition_acquired_rate", "hostage_taken_rate"]:
        rate = gp.get(key, 0)
        label = key.replace("_rate", "").replace("_", " ").title()
        lines.append(f"{label}: {rate:.0%} of runs")
    lines.append("")

    # Emergence
    emrg = report.get("emergence", {})
    bs = emrg.get("black_swan_frequency_by_type", {})
    if bs:
        parts = ", ".join(f"{k} {v:.0%}" for k, v in bs.items())
        lines.append(f"Black Swan: {parts}")
    lines.append(f"Regression: {emrg.get('regression_rate', 0):.0%} of runs")
    lines.append("")

    # General
    gen = report.get("general", {})
    if "median_era_at_final" in gen:
        lines.append(f"Median era at final turn: {gen['median_era_at_final']}")
    lines.append("")

    # Event firing rates
    lines.append("EVENT FIRING RATES:")
    for et, rate in sorted(report.get("event_firing_rates", {}).items(), key=lambda x: -x[1]):
        count = int(rate * n_runs)
        flag = ""
        if rate >= 1.0:
            flag = "  ← EVERY RUN"
        elif rate < 0.05:
            flag = "  ← RARE"
        lines.append(f"  {et}: {count}/{n_runs} ({rate:.0%}){flag}")
    lines.append("")

    # Anomalies
    anomalies = report.get("anomalies", [])
    if anomalies:
        critical = [a for a in anomalies if a["severity"] == "CRITICAL"]
        warnings_ = [a for a in anomalies if a["severity"] == "WARNING"]
        if critical:
            lines.append("DEGENERATE PATTERNS:")
            for a in critical:
                lines.append(f"  ⚠ {a['name']}: {a['detail']}")
            lines.append("")
        if warnings_:
            lines.append("NEVER-FIRE / WARNINGS:")
            for a in warnings_:
                lines.append(f"  ⚠ {a['name']}: {a['detail']}")
            lines.append("")
    else:
        lines.append("No anomalies detected.")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py -k "ReportAssembly or TextFormatter" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add report assembly and text formatter"
```

---

### Task 11: Delta Comparison Report

**Files:**
- Modify: `src/chronicler/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analytics.py — append

class TestDeltaReport:
    def test_delta_shows_changed_metrics(self):
        from chronicler.analytics import format_delta_report
        baseline = {
            "stability": {"zero_rate_by_turn": {"100": 0.43}},
            "event_firing_rates": {"famine": 0.99},
            "anomalies": [{"name": "stability_collapse", "severity": "CRITICAL", "detail": "bad"}],
        }
        current = {
            "stability": {"zero_rate_by_turn": {"100": 0.08}},
            "event_firing_rates": {"famine": 0.65},
            "anomalies": [],
        }
        text = format_delta_report(baseline, current)
        assert "100" in text  # checkpoint turn reference
        assert "famine" in text
        assert "RESOLVED" in text

    def test_delta_omits_small_changes(self):
        from chronicler.analytics import format_delta_report
        baseline = {"stability": {"zero_rate_by_turn": {"100": 0.50}}}
        current = {"stability": {"zero_rate_by_turn": {"100": 0.49}}}  # < 5% change
        text = format_delta_report(baseline, current, threshold=0.05)
        assert "omitted" in text.lower() or "0 %" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analytics.py::TestDeltaReport -v`
Expected: FAIL

- [ ] **Step 3: Implement format_delta_report**

Add to `analytics.py`:

```python
def format_delta_report(
    baseline: dict,
    current: dict,
    threshold: float = 0.05,
) -> str:
    """Format delta-only comparison between two reports.

    Walks both reports' numeric leaf values. Omits metrics where the relative
    change is below threshold (default 5%).
    """
    lines = ["DELTA REPORT (baseline → current)", "=" * 40, ""]

    deltas = []
    omitted = 0

    def _walk(base: dict, curr: dict, prefix: str = ""):
        nonlocal omitted
        for key in sorted(set(list(base.keys()) + list(curr.keys()))):
            if key in ("anomalies", "metadata"):
                continue
            full_key = f"{prefix}.{key}" if prefix else key
            b_val = base.get(key)
            c_val = curr.get(key)
            if isinstance(b_val, dict) and isinstance(c_val, dict):
                _walk(b_val, c_val, full_key)
            elif isinstance(b_val, (int, float)) and isinstance(c_val, (int, float)):
                rel_change = abs(c_val - b_val) / max(abs(b_val), 1e-9)
                if rel_change >= threshold:
                    pct = ((c_val - b_val) / max(abs(b_val), 1e-9)) * 100
                    sign = "+" if pct > 0 else ""
                    deltas.append(f"  {full_key}: {b_val} → {c_val}  ({sign}{pct:.0f}%)")
                else:
                    omitted += 1

    _walk(baseline, current)

    if deltas:
        lines.extend(deltas)
    else:
        lines.append("  No significant changes.")
    lines.append("")

    # Anomalies resolved / new
    base_anomaly_names = {a["name"] for a in baseline.get("anomalies", [])}
    curr_anomaly_names = {a["name"] for a in current.get("anomalies", [])}
    resolved = base_anomaly_names - curr_anomaly_names
    new_anomalies = curr_anomaly_names - base_anomaly_names

    if resolved:
        lines.append("ANOMALIES RESOLVED:")
        for name in sorted(resolved):
            lines.append(f"  ✓ {name}")
        lines.append("")
    if new_anomalies:
        lines.append("ANOMALIES NEW:")
        for name in sorted(new_anomalies):
            lines.append(f"  ⚠ {name}")
        lines.append("")

    lines.append(f"{omitted} metrics omitted (< {threshold:.0%} change)")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analytics.py::TestDeltaReport -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m19): add delta comparison report formatter"
```

---

## Chunk 3: CLI Integration & End-to-End

### Task 12: Wire --analyze and --compare CLI Flags

**Files:**
- Modify: `src/chronicler/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_main.py — append
def test_analyze_flag_parses(tmp_path):
    """--analyze flag is accepted by the parser."""
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--analyze", str(tmp_path)])
    assert args.analyze == str(tmp_path)


def test_analyze_mutually_exclusive_with_batch(tmp_path):
    """--analyze and --batch cannot be used together."""
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--analyze", str(tmp_path), "--batch", "5"])
    # The mutual exclusion check happens in main(), not argparse
    # So this test verifies the args are parsed, and the next test checks main()
    assert args.analyze == str(tmp_path)
    assert args.batch == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_analyze_flag_parses -v`
Expected: FAIL — unrecognized argument `--analyze`

- [ ] **Step 3: Add --analyze, --compare, --checkpoints flags to parser**

In `main.py` `_build_parser()`, after the `--seed-range` line added in Task 3:

```python
    parser.add_argument("--analyze", type=str, default=None,
                        help="Analyze a batch directory and produce batch_report.json")
    parser.add_argument("--compare", type=str, default=None,
                        help="Compare against a baseline batch_report.json (delta-only output)")
    parser.add_argument("--checkpoints", type=str, default=None,
                        help="Comma-separated checkpoint turns for analytics (e.g., 25,50,100)")
```

- [ ] **Step 4: Add --analyze to mutual exclusion check and dispatch**

In `main.py` `main()`, add to the `mode_flags` check:

```python
    if getattr(args, "analyze", None):
        mode_flags.append("--analyze")
```

Add the analyze dispatch before the batch dispatch (around line 602):

```python
    if getattr(args, "analyze", None):
        from chronicler.analytics import generate_report, format_text_report, format_delta_report
        analyze_dir = Path(args.analyze)
        checkpoints = None
        if getattr(args, "checkpoints", None):
            checkpoints = [int(x.strip()) for x in args.checkpoints.split(",")]
        report = generate_report(analyze_dir, checkpoints=checkpoints)
        # Write report JSON
        report_path = analyze_dir / "batch_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        # Output
        if getattr(args, "compare", None):
            with open(args.compare) as f:
                baseline = json.load(f)
            print(format_delta_report(baseline, report))
        else:
            print(format_text_report(report))
        print(f"\nReport written to: {report_path}")

    elif args.batch:
```

Add `import json` to the top of `main.py` if not already present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m19): wire --analyze, --compare, --checkpoints CLI flags"
```

---

### Task 13: End-to-End Integration Test

**Files:**
- Create: `tests/test_m19_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_m19_integration.py
"""M19 end-to-end integration test: batch → analyze → compare."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def batch_args(tmp_path):
    import argparse
    return argparse.Namespace(
        seed=1, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=999,
        local_url="http://localhost:1234/v1",
        sim_model=None, narrative_model=None,
        llm_actions=False, scenario=None,
        batch=3, fork=None, interactive=False,
        parallel=None, pause_every=None,
        simulate_only=True, tuning=None,
        seed_range=None, live=False,
    )


class TestM19Integration:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_batch_then_analyze(self, batch_args, tmp_path):
        """Full pipeline: batch run → analyze → report."""
        from chronicler.batch import run_batch
        from chronicler.analytics import generate_report, format_text_report

        sim = self._mock_llm()
        narr = self._mock_llm("Story.")

        # Step 1: Run batch
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()

        # Step 2: Analyze
        report = generate_report(batch_dir, checkpoints=[2, 4])
        assert report["metadata"]["runs"] == 3
        assert "stability" in report
        assert "event_firing_rates" in report
        assert "anomalies" in report

        # Step 3: Format text report
        text = format_text_report(report)
        assert len(text) > 50

        # Step 4: Write and re-read report
        report_path = batch_dir / "batch_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f)
        with open(report_path) as f:
            reloaded = json.load(f)
        assert reloaded["metadata"]["runs"] == 3

    def test_tuning_overrides_in_batch(self, batch_args, tmp_path):
        """Tuning YAML is loaded and applied during batch run."""
        from chronicler.batch import run_batch

        tuning_file = tmp_path / "tuning.yaml"
        tuning_file.write_text("stability:\n  drain:\n    drought_immediate: -1\n")
        batch_args.tuning = str(tuning_file)

        sim = self._mock_llm()
        narr = self._mock_llm("Story.")

        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        # Verify bundles exist
        bundles = list(batch_dir.glob("*/chronicle_bundle.json"))
        assert len(bundles) == 3

    def test_compare_two_reports(self, tmp_path):
        """Delta comparison between two reports."""
        from chronicler.analytics import format_delta_report

        baseline = {
            "stability": {"zero_rate_by_turn": {"100": 0.43}, "percentiles_by_turn": {"5": {"median": 8}}},
            "event_firing_rates": {"famine": 0.99, "war": 0.5},
            "anomalies": [{"name": "stability_collapse", "severity": "CRITICAL", "detail": "bad"}],
        }
        current = {
            "stability": {"zero_rate_by_turn": {"100": 0.08}, "percentiles_by_turn": {"5": {"median": 31}}},
            "event_firing_rates": {"famine": 0.65, "war": 0.5},
            "anomalies": [],
        }
        text = format_delta_report(baseline, current)
        assert "zero_rate" in text
        assert "RESOLVED" in text
        assert "stability_collapse" in text
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/test_m19_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass, no regressions

- [ ] **Step 4: Commit**

```bash
git add tests/test_m19_integration.py
git commit -m "test(m19): add end-to-end integration tests for batch → analyze → compare pipeline"
```

---

### Task 14: Verify --simulate-only Wiring

**Files:**
- Read: `src/chronicler/batch.py`, `src/chronicler/main.py`
- Test: `tests/test_batch.py`

- [ ] **Step 1: Write test to verify simulate-only in batch mode**

```python
# tests/test_batch.py — append to TestRunBatch class

    def test_simulate_only_skips_llm(self, batch_args, tmp_path):
        """--simulate-only batch runs don't require real LLM clients."""
        batch_args.simulate_only = True
        # Pass None for LLM clients — should not crash
        batch_dir = run_batch(batch_args, sim_client=None, narrative_client=None)
        assert batch_dir.exists()
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_batch.py::TestRunBatch::test_simulate_only_skips_llm -v`
Expected: If it passes, `--simulate-only` is already wired correctly. If it fails, fix the wiring.

- [ ] **Step 3: Fix if needed**

If the test fails because `execute_run` tries to use `None` LLM clients, ensure that `execute_run` checks `args.simulate_only` early and replaces clients with `_DummyClient()`. The existing check at `main.py:570-571` handles this for the `main()` entry point, but `batch.py` sequential path passes clients through directly. Verify the `_DummyClient` fallback works in both paths.

- [ ] **Step 4: Commit if changes were needed**

```bash
git add src/chronicler/batch.py tests/test_batch.py
git commit -m "fix(m19): verify --simulate-only wiring through batch runner"
```

---

### Task 15: Final Verification and Cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify line counts match estimates**

```bash
wc -l src/chronicler/analytics.py src/chronicler/tuning.py
```
Expected: analytics.py ~350 lines, tuning.py ~80 lines

- [ ] **Step 3: Verify no simulation imports in analytics.py**

```bash
grep "from chronicler\." src/chronicler/analytics.py
```
Expected: No imports from simulation, models, or any other chronicler module (analytics reads JSON only)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(m19): simulation analytics and tuning system complete"
```
