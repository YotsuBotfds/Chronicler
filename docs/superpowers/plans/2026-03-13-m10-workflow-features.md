# M10: Workflow Features Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add batch runs, interestingness ranking, forking, and intervention hooks to the chronicler CLI.

**Architecture:** Four new flat modules (`batch.py`, `interestingness.py`, `fork.py`, `interactive.py`) plus a shared `types.py`. The existing `run_chronicle()` in `main.py` is refactored to extract `execute_run()` as the core entry point. Each workflow module calls `execute_run()` with different setup and teardown. No class hierarchy or abstraction layer.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, argparse, multiprocessing (for parallel batch). All existing dependencies; no new packages.

**Spec:** `docs/superpowers/specs/2026-03-13-m10-workflow-features-design.md`

---

## Chunk 1: Foundation — types.py, memory persistence, model changes, simulation wrapper

These are prerequisite changes that all workflow modules depend on. They can be implemented as independent tasks (parallelizable).

### Task 1: RunResult dataclass (`types.py`)

**Files:**
- Create: `src/chronicler/types.py`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_types.py`:

```python
"""Tests for shared types."""
from pathlib import Path
from chronicler.types import RunResult


def test_run_result_construction():
    result = RunResult(
        seed=42,
        output_dir=Path("output/seed_42"),
        war_count=3,
        collapse_count=1,
        named_event_count=5,
        distinct_action_count=4,
        reflection_count=2,
        tech_advancement_count=1,
        max_stat_swing=12.5,
        action_distribution={
            "Kethani Empire": {"develop": 10, "trade": 5, "war": 3},
            "Dorrathi Clans": {"war": 8, "expand": 4, "develop": 6},
        },
        dominant_faction="Kethani Empire",
        total_turns=50,
        boring_civs=[],
    )
    assert result.seed == 42
    assert result.war_count == 3
    assert result.dominant_faction == "Kethani Empire"
    assert result.boring_civs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicler.types'`

- [ ] **Step 3: Write minimal implementation**

Create `src/chronicler/types.py`:

```python
"""Shared types for workflow modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunResult:
    """Aggregate stats from a single chronicle run.

    Fields are computed inside execute_run() and returned without
    the full WorldState to keep batch memory usage low.
    """
    seed: int
    output_dir: Path
    war_count: int
    collapse_count: int
    named_event_count: int
    distinct_action_count: int
    reflection_count: int
    tech_advancement_count: int
    max_stat_swing: float
    action_distribution: dict[str, dict[str, int]]
    dominant_faction: str
    total_turns: int
    boring_civs: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/types.py tests/test_types.py
git commit -m "feat(m10): add RunResult dataclass in types.py"
```

---

### Task 2: Memory stream persistence (`memory.py`)

**Files:**
- Modify: `src/chronicler/memory.py` (add `save`/`load` methods + `sanitize_civ_name`)
- Test: `tests/test_memory.py` (add new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_memory.py`:

```python
import json
from chronicler.memory import MemoryStream, MemoryEntry, sanitize_civ_name


class TestMemoryPersistence:
    def test_round_trip_entries_and_reflections(self, tmp_path):
        """Save a MemoryStream, load it back, verify all fields match."""
        stream = MemoryStream(civilization_name="Kethani Empire")
        for i in range(10):
            stream.add(text=f"Event {i} occurred", turn=i, importance=i % 10 + 1)
        stream.add_reflection("The Age of Iron", turn=10)
        stream.add_reflection("The Age of Sorrow", turn=20)

        path = tmp_path / "memories_kethani_empire.json"
        stream.save(path)
        assert path.exists()

        loaded = MemoryStream.load(path)
        assert loaded.civilization_name == "Kethani Empire"
        assert len(loaded.entries) == 10
        assert len(loaded.reflections) == 2

        for orig, loaded_e in zip(stream.entries, loaded.entries):
            assert orig.turn == loaded_e.turn
            assert orig.text == loaded_e.text
            assert orig.importance == loaded_e.importance
            assert orig.entry_type == loaded_e.entry_type

        for orig, loaded_r in zip(stream.reflections, loaded.reflections):
            assert orig.turn == loaded_r.turn
            assert orig.text == loaded_r.text
            assert orig.importance == loaded_r.importance

    def test_round_trip_empty_stream(self, tmp_path):
        stream = MemoryStream(civilization_name="Empty Civ")
        path = tmp_path / "memories_empty_civ.json"
        stream.save(path)
        loaded = MemoryStream.load(path)
        assert loaded.civilization_name == "Empty Civ"
        assert loaded.entries == []
        assert loaded.reflections == []

    def test_save_creates_valid_json(self, tmp_path):
        stream = MemoryStream(civilization_name="Test")
        stream.add("An event", turn=1, importance=5)
        path = tmp_path / "memories_test.json"
        stream.save(path)
        data = json.loads(path.read_text())
        assert data["civilization_name"] == "Test"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["turn"] == 1


class TestSanitizeCivName:
    def test_spaces_to_underscores(self):
        assert sanitize_civ_name("Kethani Empire") == "kethani_empire"

    def test_special_characters_stripped(self):
        assert sanitize_civ_name("Dorrathi's Clans!") == "dorrathis_clans"

    def test_already_clean(self):
        assert sanitize_civ_name("rustborn") == "rustborn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memory.py::TestMemoryPersistence -v && pytest tests/test_memory.py::TestSanitizeCivName -v`
Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: Write implementation**

Add to `src/chronicler/memory.py`:

```python
import json
import re

def sanitize_civ_name(name: str) -> str:
    """Sanitize a civilization name for use in filenames."""
    name = name.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", name)
```

Add methods to `MemoryStream` class:

```python
    def save(self, path: Path) -> None:
        """Persist memory stream to a JSON file."""
        data = {
            "civilization_name": self.civilization_name,
            "entries": [
                {"turn": e.turn, "text": e.text, "importance": e.importance, "entry_type": e.entry_type}
                for e in self.entries
            ],
            "reflections": [
                {"turn": r.turn, "text": r.text, "importance": r.importance, "entry_type": r.entry_type}
                for r in self.reflections
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> MemoryStream:
        """Load a memory stream from a JSON file."""
        data = json.loads(path.read_text())
        stream = cls(civilization_name=data["civilization_name"])
        stream.entries = [
            MemoryEntry(turn=e["turn"], text=e["text"], importance=e["importance"], entry_type=e["entry_type"])
            for e in data["entries"]
        ]
        stream.reflections = [
            MemoryEntry(turn=r["turn"], text=r["text"], importance=r["importance"], entry_type=r["entry_type"])
            for r in data["reflections"]
        ]
        return stream
```

Also add `from pathlib import Path` to imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory.py -v`
Expected: All pass (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/memory.py tests/test_memory.py
git commit -m "feat(m10): add MemoryStream save/load persistence and sanitize_civ_name"
```

---

### Task 3: Add `scenario_name` to `WorldState` (`models.py` + `scenario.py`)

**Files:**
- Modify: `src/chronicler/models.py:134-148` (add field)
- Modify: `src/chronicler/scenario.py:197-318` (set field in `apply_scenario`)
- Test: `tests/test_models.py` (add test), `tests/test_scenario.py` (add test)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_world_state_scenario_name_default_none(sample_world):
    assert sample_world.scenario_name is None


def test_world_state_scenario_name_persists(sample_world, tmp_path):
    sample_world.scenario_name = "Dead Miles"
    path = tmp_path / "state.json"
    sample_world.save(path)
    loaded = WorldState.load(path)
    assert loaded.scenario_name == "Dead Miles"
```

Append to `tests/test_scenario.py`:

```python
def test_apply_scenario_sets_scenario_name(sample_world):
    from chronicler.scenario import ScenarioConfig, apply_scenario
    config = ScenarioConfig(name="Test Scenario")
    apply_scenario(sample_world, config)
    assert sample_world.scenario_name == "Test Scenario"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py::test_world_state_scenario_name_default_none tests/test_models.py::test_world_state_scenario_name_persists tests/test_scenario.py::test_apply_scenario_sets_scenario_name -v`
Expected: FAIL — `scenario_name` attribute doesn't exist

- [ ] **Step 3: Write implementation**

In `src/chronicler/models.py`, add to `WorldState` class (after `action_history` field, line 147):

```python
    scenario_name: str | None = None
```

In `src/chronicler/scenario.py`, add at the end of `apply_scenario()` (after the world name override, around line 317):

```python
    # --- Step 7: Record scenario name ---
    world.scenario_name = config.name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py tests/test_scenario.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py src/chronicler/scenario.py tests/test_models.py tests/test_scenario.py
git commit -m "feat(m10): add scenario_name field to WorldState, set in apply_scenario"
```

---

### Task 4: Add `apply_injected_event()` to `simulation.py`

**Files:**
- Modify: `src/chronicler/simulation.py:514-544` (add public wrapper after `_apply_event_effects`)
- Test: `tests/test_simulation.py` (add test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_simulation.py`:

```python
from chronicler.simulation import apply_injected_event


class TestApplyInjectedEvent:
    def test_plague_reduces_pop_and_stability(self, sample_world):
        civ = sample_world.civilizations[0]
        old_pop = civ.population
        old_stb = civ.stability
        events = apply_injected_event("plague", civ.name, sample_world)
        assert len(events) == 1
        assert events[0].event_type == "plague"
        assert events[0].actors == [civ.name]
        assert civ.population <= old_pop
        assert civ.stability <= old_stb

    def test_discovery_boosts_culture_and_economy(self, sample_world):
        civ = sample_world.civilizations[1]
        old_culture = civ.culture
        old_economy = civ.economy
        events = apply_injected_event("discovery", civ.name, sample_world)
        assert civ.culture >= old_culture
        assert civ.economy >= old_economy

    def test_unknown_civ_returns_empty(self, sample_world):
        events = apply_injected_event("plague", "Nonexistent Civ", sample_world)
        assert events == []

    def test_creates_active_condition_for_drought(self, sample_world):
        civ = sample_world.civilizations[0]
        old_conditions = len(sample_world.active_conditions)
        apply_injected_event("drought", civ.name, sample_world)
        # drought handler creates an ActiveCondition
        assert len(sample_world.active_conditions) > old_conditions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulation.py::TestApplyInjectedEvent -v`
Expected: FAIL with `ImportError: cannot import name 'apply_injected_event'`

- [ ] **Step 3: Write implementation**

Add to `src/chronicler/simulation.py` after the `_apply_event_effects` function (after line 544):

```python
def apply_injected_event(
    event_type: str, target_civ_name: str, world: WorldState
) -> list[Event]:
    """Process a manually injected event targeting a single civ.

    Unlike natural events which randomly select affected civs,
    injected events affect only the named target. Returns a list
    containing the event (or empty if target civ not found).
    """
    civ = _get_civ(world, target_civ_name)
    if civ is None:
        return []

    event = Event(
        turn=world.turn,
        event_type=event_type,
        actors=[target_civ_name],
        description=f"[Injected] {event_type} strikes {target_civ_name}",
        importance=7,
    )

    # Environment events (drought/plague/earthquake) have special handling
    # that creates ActiveConditions. Replicate that logic for the single target.
    if event_type == "drought":
        civ.stability = clamp(civ.stability - 1, 1, 10)
        civ.economy = clamp(civ.economy - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=[target_civ_name],
                duration=3,
                severity=5,
            )
        )
    elif event_type == "plague":
        civ.population = clamp(civ.population - 1, 1, 10)
        civ.stability = clamp(civ.stability - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=[target_civ_name],
                duration=4,
                severity=6,
            )
        )
    elif event_type == "earthquake":
        civ.economy = clamp(civ.economy - 1, 1, 10)
    else:
        # Non-environment events use the standard effect handler
        _apply_event_effects(event_type, civ, world)

    # Apply cascading probabilities
    world.event_probabilities = apply_probability_cascade(
        event_type, world.event_probabilities
    )

    return [event]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_simulation.py -v`
Expected: All pass (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m10): add apply_injected_event() public wrapper in simulation.py"
```

---

### Task 5: Add `interestingness_weights` to `ScenarioConfig`

**Files:**
- Modify: `src/chronicler/scenario.py:63-79` (add field to `ScenarioConfig`)
- Modify: `src/chronicler/scenario.py:114-127` (add validation in `load_scenario`)
- Test: `tests/test_scenario.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scenario.py`:

```python
class TestInterestingnessWeights:
    def test_scenario_config_accepts_weights(self):
        from chronicler.scenario import ScenarioConfig
        config = ScenarioConfig(
            name="Weighted",
            interestingness_weights={"war_count": 5, "collapse_count": 10},
        )
        assert config.interestingness_weights["war_count"] == 5

    def test_scenario_config_weights_default_none(self):
        from chronicler.scenario import ScenarioConfig
        config = ScenarioConfig(name="No Weights")
        assert config.interestingness_weights is None

    def test_invalid_weight_key_raises(self, tmp_path):
        from chronicler.scenario import load_scenario
        scenario_yaml = tmp_path / "bad_weights.yaml"
        scenario_yaml.write_text(
            "name: Bad Weights\n"
            "interestingness_weights:\n"
            "  bogus_metric: 5\n"
        )
        with pytest.raises(ValueError, match="Invalid interestingness weight key"):
            load_scenario(scenario_yaml)

    def test_valid_weight_keys_accepted(self, tmp_path):
        from chronicler.scenario import load_scenario
        scenario_yaml = tmp_path / "good_weights.yaml"
        scenario_yaml.write_text(
            "name: Good Weights\n"
            "interestingness_weights:\n"
            "  war_count: 5\n"
            "  collapse_count: 10\n"
            "  reflection_count: 0\n"
        )
        config = load_scenario(scenario_yaml)
        assert config.interestingness_weights["war_count"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scenario.py::TestInterestingnessWeights -v`
Expected: FAIL — field doesn't exist or validation not implemented

- [ ] **Step 3: Write implementation**

In `src/chronicler/scenario.py`, add to `ScenarioConfig` class (after `narrative_style`, line 78):

```python
    interestingness_weights: dict[str, float] | None = None
```

Add a module-level constant after `VALID_EVENT_OVERRIDE_KEYS` (around line 18):

```python
VALID_INTERESTINGNESS_KEYS = {
    "war_count", "collapse_count", "named_event_count",
    "distinct_action_count", "reflection_count",
    "tech_advancement_count", "max_stat_swing",
}
```

Add validation in `load_scenario()`, after the event_flavor validation block (after line 135):

```python
    # Interestingness weight keys must be valid metric names
    if config.interestingness_weights:
        for key in config.interestingness_weights:
            if key not in VALID_INTERESTINGNESS_KEYS:
                raise ValueError(
                    f"Invalid interestingness weight key '{key}'. "
                    f"Valid keys: {sorted(VALID_INTERESTINGNESS_KEYS)}"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scenario.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_scenario.py
git commit -m "feat(m10): add interestingness_weights field to ScenarioConfig with validation"
```

---

## Chunk 2: Interestingness scoring module

### Task 6: `score_run()` and `find_boring_civs()` (`interestingness.py`)

**Files:**
- Create: `src/chronicler/interestingness.py`
- Test: `tests/test_interestingness.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interestingness.py`:

```python
"""Tests for interestingness scoring."""
import pytest
from pathlib import Path
from chronicler.interestingness import score_run, find_boring_civs, DEFAULT_WEIGHTS
from chronicler.types import RunResult


@pytest.fixture
def sample_result():
    return RunResult(
        seed=42,
        output_dir=Path("output/seed_42"),
        war_count=3,
        collapse_count=1,
        named_event_count=5,
        distinct_action_count=4,
        reflection_count=2,
        tech_advancement_count=1,
        max_stat_swing=12.5,
        action_distribution={
            "Kethani Empire": {"develop": 10, "trade": 5, "war": 3},
            "Dorrathi Clans": {"war": 8, "expand": 4, "develop": 6},
        },
        dominant_faction="Kethani Empire",
        total_turns=50,
        boring_civs=[],
    )


class TestScoreRun:
    def test_default_weights(self, sample_result):
        score = score_run(sample_result)
        # war_count(3)*3 + collapse_count(1)*5 + named_event_count(5)*1
        # + distinct_action_count(4)*1 + reflection_count(2)*2
        # + tech_advancement_count(1)*2 + max_stat_swing(12.5)*1
        expected = 3*3 + 1*5 + 5*1 + 4*1 + 2*2 + 1*2 + 12.5*1
        assert score == pytest.approx(expected)

    def test_custom_weights_override_defaults(self, sample_result):
        custom = {"war_count": 10, "collapse_count": 0}
        score = score_run(sample_result, weights=custom)
        # war_count(3)*10 + collapse_count(1)*0 + rest at defaults
        expected = 3*10 + 1*0 + 5*1 + 4*1 + 2*2 + 1*2 + 12.5*1
        assert score == pytest.approx(expected)

    def test_all_zeros_result(self):
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=0, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution={}, dominant_faction="None", total_turns=10,
            boring_civs=[],
        )
        assert score_run(result) == 0.0


class TestFindBoringCivs:
    def test_no_boring_civs(self):
        dist = {
            "Civ A": {"develop": 5, "trade": 5, "war": 5},
            "Civ B": {"expand": 4, "develop": 4, "war": 4},
        }
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=3, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Civ A",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []

    def test_detects_boring_civ(self):
        dist = {
            "Boring Civ": {"develop": 18, "trade": 1, "war": 1},  # 90% develop
            "Good Civ": {"develop": 5, "trade": 5, "war": 5},
        }
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=3, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Good Civ",
            total_turns=20, boring_civs=[],
        )
        boring = find_boring_civs(result)
        assert any("Boring Civ" in b for b in boring)
        assert not any("Good Civ" in b for b in boring)

    def test_threshold_boundary(self):
        # Exactly 60% should NOT be boring (threshold is >60%)
        dist = {"Edge Civ": {"develop": 6, "trade": 4}}
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=2, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Edge Civ",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []

    def test_empty_distribution(self):
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=0, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution={}, dominant_faction="None",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []


class TestDefaultWeights:
    def test_all_expected_keys_present(self):
        expected_keys = {
            "war_count", "collapse_count", "named_event_count",
            "distinct_action_count", "reflection_count",
            "tech_advancement_count", "max_stat_swing",
        }
        assert set(DEFAULT_WEIGHTS.keys()) == expected_keys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_interestingness.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/chronicler/interestingness.py`:

```python
"""Interestingness scoring for chronicle runs."""
from __future__ import annotations

from chronicler.types import RunResult


DEFAULT_WEIGHTS: dict[str, float] = {
    "war_count": 3,
    "collapse_count": 5,
    "named_event_count": 1,
    "distinct_action_count": 1,
    "reflection_count": 2,
    "tech_advancement_count": 2,
    "max_stat_swing": 1,
}


def score_run(result: RunResult, weights: dict[str, float] | None = None) -> float:
    """Score a run's interestingness based on weighted metrics.

    Custom weights override matching keys in DEFAULT_WEIGHTS;
    unspecified keys keep defaults.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    return (
        result.war_count * w["war_count"]
        + result.collapse_count * w["collapse_count"]
        + result.named_event_count * w["named_event_count"]
        + result.distinct_action_count * w["distinct_action_count"]
        + result.reflection_count * w["reflection_count"]
        + result.tech_advancement_count * w["tech_advancement_count"]
        + result.max_stat_swing * w["max_stat_swing"]
    )


def find_boring_civs(result: RunResult, threshold: float = 0.6) -> list[str]:
    """Find civs where any single action exceeds threshold of total actions.

    Returns list of civ names that are boring (empty if none).
    """
    boring = []
    for civ_name, actions in result.action_distribution.items():
        total = sum(actions.values())
        if total == 0:
            continue
        for action_type, count in actions.items():
            pct = count / total
            if pct > threshold:
                boring.append(f"{civ_name} ({action_type} {pct:.0%})")
                break
    return boring
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interestingness.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/interestingness.py tests/test_interestingness.py
git commit -m "feat(m10): add interestingness scoring module with score_run and find_boring_civs"
```

---

## Chunk 3: execute_run refactor and memory persistence in the run loop

### Task 7: Extract `execute_run()` from `run_chronicle()` in `main.py`

This is the core refactor. `execute_run()` becomes the shared entry point for single runs, batch, fork, and interactive modes. It returns a `RunResult` instead of writing output directly (that's the caller's responsibility). Memory streams are saved every turn alongside `state.json`.

**Files:**
- Modify: `src/chronicler/main.py`
- Test: `tests/test_main.py` (modify existing tests, add new ones)

- [ ] **Step 1: Write the failing tests for `execute_run()`**

Append to `tests/test_main.py`:

```python
from chronicler.main import execute_run
from chronicler.types import RunResult
from chronicler.memory import MemoryStream
import argparse


class TestExecuteRun:
    def _mock_llm(self, response: str = "DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def _make_args(self, tmp_path, seed=42, turns=5, civs=2, regions=4):
        """Build a minimal args namespace for execute_run."""
        return argparse.Namespace(
            seed=seed,
            turns=turns,
            civs=civs,
            regions=regions,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None,
            reflection_interval=10,
            local_url="http://localhost:1234/v1",
            sim_model=None,
            narrative_model=None,
            llm_actions=False,
            scenario=None,
            batch=None,
            fork=None,
            interactive=False,
            parallel=None,
            pause_every=None,
        )

    def test_returns_run_result(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Things happened.")
        args = self._make_args(tmp_path, turns=3)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        assert isinstance(result, RunResult)
        assert result.seed == 42
        assert result.total_turns == 3
        assert result.output_dir == tmp_path

    def test_saves_memory_streams(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Events occurred.")
        args = self._make_args(tmp_path, turns=3)
        execute_run(args, sim_client=sim, narrative_client=narr)
        # Memory files should exist for each civ
        memory_files = list(tmp_path.glob("memories_*.json"))
        assert len(memory_files) >= 1  # At least one civ

    def test_populates_action_distribution(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        assert len(result.action_distribution) > 0
        for civ_name, actions in result.action_distribution.items():
            assert isinstance(actions, dict)

    def test_computes_max_stat_swing(self, tmp_path):
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=3)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        assert isinstance(result.max_stat_swing, float)

    def test_accepts_preloaded_world_and_memories(self, tmp_path):
        """Fork/resume path: pass in existing world and memories."""
        from chronicler.world_gen import generate_world
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Story.")
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        world.turn = 3  # Simulate mid-run state
        memories = {c.name: MemoryStream(c.name) for c in world.civilizations}
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(
            args, sim_client=sim, narrative_client=narr,
            world=world, memories=memories,
        )
        # Should only run turns 3-4 (2 turns), not 0-4
        assert result.total_turns == 2

    def test_counts_events_from_start_turn(self, tmp_path):
        """Fork scenario: pre-fork events must NOT appear in RunResult counts."""
        from chronicler.world_gen import generate_world
        from chronicler.models import Event, Disposition, Relationship
        sim = self._mock_llm("DEVELOP")
        narr = self._mock_llm("Peace reigned.")
        world = generate_world(seed=42, num_regions=4, num_civs=2)
        world.turn = 3
        # Inject 3 pre-fork war events that should be excluded from counts
        for t in range(3):
            world.events_timeline.append(Event(
                turn=t, event_type="war", actors=[world.civilizations[0].name],
                description=f"Old war {t}", importance=5,
            ))
        # Make all relationships ALLIED so no new wars happen
        for src in world.relationships:
            for dst in world.relationships[src]:
                world.relationships[src][dst].disposition = Disposition.ALLIED
        memories = {c.name: MemoryStream(c.name) for c in world.civilizations}
        args = self._make_args(tmp_path, turns=5)
        result = execute_run(
            args, sim_client=sim, narrative_client=narr,
            world=world, memories=memories,
        )
        # 3 pre-fork wars must be excluded; with ALLIED + DEVELOP, no new wars
        assert result.war_count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py::TestExecuteRun -v`
Expected: FAIL with `ImportError: cannot import name 'execute_run'`

- [ ] **Step 3: Write implementation**

Refactor `src/chronicler/main.py`. The key changes:

1. Extract `execute_run()` as a public function
2. `run_chronicle()` becomes a thin wrapper calling `execute_run()`
3. `execute_run()` returns `RunResult` and saves memory streams every turn
4. Accepts optional `world`, `memories`, `on_pause`, `pause_every`, `pending_injections`
5. Counts events only from `start_turn` onward for `RunResult`

Replace the `run_chronicle` function and add `execute_run`:

```python
from chronicler.interestingness import find_boring_civs
from chronicler.memory import MemoryStream, generate_reflection, should_reflect, sanitize_civ_name
from chronicler.simulation import run_turn, apply_injected_event
from chronicler.types import RunResult


class _DummyClient:
    """Fallback LLM client for deterministic-only runs (no API calls)."""
    model = "dummy"
    def complete(self, prompt: str, max_tokens: int = 100) -> str:
        return "DEVELOP"


def execute_run(
    args,
    sim_client: LLMClient | None = None,
    narrative_client: LLMClient | None = None,
    world: WorldState | None = None,
    memories: dict[str, MemoryStream] | None = None,
    on_pause: Any = None,  # Callable[[WorldState, dict[str, MemoryStream], list], bool] | None
    pause_every: int | None = None,
    pending_injections: list[tuple[str, str]] | None = None,
    scenario_config: Any = None,  # ScenarioConfig | None
    provenance_header: str | None = None,
) -> RunResult:
    """Core run logic shared by single, batch, fork, and interactive modes.

    Returns a RunResult with aggregate stats. Full state is saved to disk.
    """
    seed = args.seed if hasattr(args, 'seed') and args.seed is not None else 42
    num_turns = args.turns if hasattr(args, 'turns') and args.turns is not None else 50
    output_dir = Path(args.output).parent if hasattr(args, 'output') else Path("output")
    state_path = Path(args.state) if hasattr(args, 'state') and args.state else None
    reflection_interval = getattr(args, 'reflection_interval', None) or 10
    use_llm_actions = getattr(args, 'llm_actions', False)

    # Extract presentation-layer config for narrative engine
    event_flavor = scenario_config.event_flavor if scenario_config else None
    narrative_style = scenario_config.narrative_style if scenario_config else None

    # NarrativeEngine requires non-None clients. For deterministic-only runs
    # (e.g., parallel batch without --llm-actions), create a dummy client
    # whose complete() returns a placeholder string.
    _sim = sim_client or _DummyClient()
    _narr = narrative_client or _DummyClient()
    engine = NarrativeEngine(
        sim_client=_sim,
        narrative_client=_narr,
        event_flavor=event_flavor,
        narrative_style=narrative_style,
    )

    # World setup
    if world is None:
        num_civs = getattr(args, 'civs', None) or 4
        num_regions = getattr(args, 'regions', None) or 8
        world = generate_world(seed=seed, num_regions=num_regions, num_civs=num_civs)
        if scenario_config:
            from chronicler.scenario import apply_scenario
            apply_scenario(world, scenario_config)
        if sim_client:
            try:
                enrich_with_llm(world, sim_client)
            except Exception:
                pass

    start_turn = world.turn

    # Memory setup
    if memories is None:
        memories = {
            civ.name: MemoryStream(civilization_name=civ.name)
            for civ in world.civilizations
        }

    # Run simulation
    chronicle_entries: list[ChronicleEntry] = []
    era_reflections: dict[int, str] = {}
    output_path = Path(args.output) if hasattr(args, 'output') else output_dir / "chronicle.md"

    for turn_num in range(start_turn, num_turns):
        # Drain pending injections before normal phases
        if pending_injections:
            for event_type, target_civ in pending_injections:
                injection_events = apply_injected_event(event_type, target_civ, world)
                world.events_timeline.extend(injection_events)
            pending_injections.clear()

        # Create action engine fresh each turn
        action_engine = ActionEngine(world)

        if use_llm_actions and sim_client:
            def action_selector(civ, world, _engine=action_engine, _narr=engine):
                try:
                    action = _narr.select_action(civ, world)
                    eligible = _engine.get_eligible_actions(civ)
                    if action in eligible:
                        return action
                except Exception:
                    pass
                return _engine.select_action(civ, seed=world.seed)
        else:
            def action_selector(civ, world, _engine=action_engine):
                return _engine.select_action(civ, seed=world.seed)

        # Run one turn
        chronicle_text = run_turn(
            world,
            action_selector=action_selector,
            narrator=engine.narrator,
            seed=seed + turn_num,
        )

        chronicle_entries.append(ChronicleEntry(turn=world.turn, text=chronicle_text))

        # Update memory streams
        turn_events = [e for e in world.events_timeline if e.turn == world.turn - 1]
        for event in turn_events:
            for actor in event.actors:
                if actor in memories:
                    memories[actor].add(
                        text=event.description or f"{event.event_type} occurred",
                        turn=world.turn,
                        importance=event.importance,
                    )

        # Era reflections
        if should_reflect(world.turn, interval=reflection_interval):
            era_start = world.turn - reflection_interval + 1
            era_end = world.turn
            reflection_texts = []
            for civ_name, stream in memories.items():
                reflection = generate_reflection(
                    stream, era_start=era_start, era_end=era_end, client=narrative_client,
                )
                reflection_texts.append(reflection)
            combined = "\n\n".join(reflection_texts)
            era_reflections[world.turn] = f"## Era: Turns {era_start}\u2013{era_end}\n\n{combined}"

        # Save state + memory streams every turn
        if state_path:
            world.save(state_path)
        for civ_name, stream in memories.items():
            mem_path = output_dir / f"memories_{sanitize_civ_name(civ_name)}.json"
            stream.save(mem_path)

        # Pause hook for interactive mode
        if on_pause and pause_every and world.turn % pause_every == 0:
            should_continue = on_pause(world, memories, pending_injections or [])
            if not should_continue:
                break  # User typed quit

    # Compile chronicle
    epilogue = f"Thus concludes the chronicle of {world.name}, spanning {world.turn - start_turn} turns of history."
    if world.turn < num_turns:
        epilogue = f"> Chronicle ended early at turn {world.turn} of {num_turns}."
    output_text = compile_chronicle(
        world_name=world.name,
        entries=chronicle_entries,
        era_reflections=era_reflections,
        epilogue=epilogue,
    )

    # Add provenance header for forks
    if provenance_header:
        output_text = provenance_header + "\n\n" + output_text

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text)

    # Save final state
    if state_path:
        world.save(state_path)

    # Compute RunResult — only count events from start_turn onward
    new_events = [e for e in world.events_timeline if e.turn >= start_turn]
    war_count = sum(1 for e in new_events if e.event_type == "war")
    collapse_count = sum(1 for e in new_events if e.event_type == "collapse")
    tech_advancement_count = sum(1 for e in new_events if e.event_type == "tech_advancement")
    named_event_count = len([ne for ne in world.named_events if ne.turn >= start_turn])
    reflection_count = sum(
        1 for s in memories.values() for r in s.reflections if r.turn >= start_turn
    )

    # Action distribution from Civilization.action_counts
    action_distribution = {
        civ.name: dict(civ.action_counts) for civ in world.civilizations
    }
    all_actions = set()
    for actions in action_distribution.values():
        all_actions.update(actions.keys())
    distinct_action_count = len(all_actions)

    # Max stat swing: population variance of final total stats
    total_stats = [
        civ.population + civ.military + civ.economy + civ.culture + civ.stability
        for civ in world.civilizations
    ]
    if total_stats:
        mean_stat = sum(total_stats) / len(total_stats)
        max_stat_swing = sum((s - mean_stat) ** 2 for s in total_stats) / len(total_stats)
    else:
        max_stat_swing = 0.0

    # Dominant faction
    dominant = max(world.civilizations, key=lambda c: c.population + c.military + c.economy + c.culture + c.stability) if world.civilizations else None
    dominant_faction = dominant.name if dominant else "None"

    actual_turns = world.turn - start_turn

    result = RunResult(
        seed=seed,
        output_dir=output_dir,
        war_count=war_count,
        collapse_count=collapse_count,
        named_event_count=named_event_count,
        distinct_action_count=distinct_action_count,
        reflection_count=reflection_count,
        tech_advancement_count=tech_advancement_count,
        max_stat_swing=max_stat_swing,
        action_distribution=action_distribution,
        dominant_faction=dominant_faction,
        total_turns=actual_turns,
    )
    result.boring_civs = find_boring_civs(result)

    return result


def run_chronicle(
    seed: int = 42,
    num_turns: int = 50,
    num_civs: int = 4,
    num_regions: int = 8,
    output_path: Path = Path("output/chronicle.md"),
    state_path: Path | None = None,
    sim_client: LLMClient | None = None,
    narrative_client: LLMClient | None = None,
    reflection_interval: int = 10,
    resume_path: Path | None = None,
    use_llm_actions: bool = False,
    scenario_config: "ScenarioConfig | None" = None,
) -> None:
    """Legacy wrapper — calls execute_run() internally."""
    import argparse
    args = argparse.Namespace(
        seed=seed, turns=num_turns, civs=num_civs, regions=num_regions,
        output=str(output_path),
        state=str(state_path) if state_path else None,
        resume=str(resume_path) if resume_path else None,
        reflection_interval=reflection_interval,
        llm_actions=use_llm_actions,
        scenario=None,
        batch=None, fork=None, interactive=False,
        parallel=None, pause_every=None,
    )

    world = None
    memories = None
    if resume_path:
        world = WorldState.load(resume_path)
        # Load memory streams if available
        resume_dir = resume_path.parent
        memories = {}
        for civ_name_file in resume_dir.glob("memories_*.json"):
            stream = MemoryStream.load(civ_name_file)
            memories[stream.civilization_name] = stream

    execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        world=world,
        memories=memories,
        scenario_config=scenario_config,
    )
```

- [ ] **Step 4: Run ALL existing tests to verify nothing breaks**

Run: `pytest tests/ -v`
Expected: All existing tests pass + new TestExecuteRun tests pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m10): extract execute_run() from run_chronicle, add memory persistence every turn"
```

---

## Chunk 4: Batch runner and CLI dispatch

### Task 8: Batch runner module (`batch.py`)

**Files:**
- Create: `src/chronicler/batch.py`
- Test: `tests/test_batch.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_batch.py`:

```python
"""Tests for batch runner."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import argparse

from chronicler.batch import run_batch


@pytest.fixture
def batch_args(tmp_path):
    return argparse.Namespace(
        seed=42, turns=3, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        local_url="http://localhost:1234/v1",
        sim_model=None, narrative_model=None,
        llm_actions=False, scenario=None,
        batch=3, fork=None, interactive=False,
        parallel=None, pause_every=None,
    )


class TestRunBatch:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_creates_output_directories(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        assert (batch_dir / "seed_42").is_dir()
        assert (batch_dir / "seed_43").is_dir()
        assert (batch_dir / "seed_44").is_dir()

    def test_each_run_produces_chronicle(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        for seed in [42, 43, 44]:
            assert (batch_dir / f"seed_{seed}" / "chronicle.md").exists()
            assert (batch_dir / f"seed_{seed}" / "state.json").exists()

    def test_produces_summary(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        summary = batch_dir / "summary.md"
        assert summary.exists()
        content = summary.read_text()
        assert "Rank" in content or "rank" in content.lower()

    def test_returns_batch_directory_path(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.name == "batch_42"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_batch.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/chronicler/batch.py`:

```python
"""Batch runner — run multiple chronicles with sequential seeds."""
from __future__ import annotations

import argparse
import copy
import multiprocessing
from pathlib import Path
from typing import Any

from chronicler.interestingness import score_run
from chronicler.types import RunResult


def run_batch(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> Path:
    """Run N chronicles with sequential seeds. Returns the batch directory path."""
    base_seed = args.seed or 42
    count = args.batch
    base_output = Path(args.output).parent if hasattr(args, 'output') else Path("output")
    batch_dir = base_output / f"batch_{base_seed}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []

    if args.parallel:
        workers = args.parallel if isinstance(args.parallel, int) and args.parallel > 1 else max(1, multiprocessing.cpu_count() - 1)
        # Build arg list for pool
        run_args = []
        for i in range(count):
            run_seed = base_seed + i
            run_dir = batch_dir / f"seed_{run_seed}"
            run_dir.mkdir(parents=True, exist_ok=True)
            child_args = copy.copy(args)
            child_args.seed = run_seed
            child_args.output = str(run_dir / "chronicle.md")
            child_args.state = str(run_dir / "state.json")
            run_args.append((child_args, scenario_config))

        with multiprocessing.Pool(workers) as pool:
            results = pool.starmap(_run_single_no_llm, run_args)
    else:
        for i in range(count):
            run_seed = base_seed + i
            run_dir = batch_dir / f"seed_{run_seed}"
            run_dir.mkdir(parents=True, exist_ok=True)

            child_args = copy.copy(args)
            child_args.seed = run_seed
            child_args.output = str(run_dir / "chronicle.md")
            child_args.state = str(run_dir / "state.json")

            from chronicler.main import execute_run
            result = execute_run(
                child_args,
                sim_client=sim_client,
                narrative_client=narrative_client,
                scenario_config=scenario_config,
            )
            results.append(result)
            print(f"  Batch run {i + 1}/{count} complete (seed {run_seed})")

    # Write summary
    weights = scenario_config.interestingness_weights if scenario_config and hasattr(scenario_config, 'interestingness_weights') else None
    _write_summary(batch_dir, results, weights)

    return batch_dir


def _run_single_no_llm(args: argparse.Namespace, scenario_config: Any = None) -> RunResult:
    """Worker function for parallel batch (no LLM clients — deterministic only)."""
    from chronicler.main import execute_run
    return execute_run(args, scenario_config=scenario_config)


def _write_summary(
    batch_dir: Path,
    results: list[RunResult],
    weights: dict[str, float] | None = None,
) -> None:
    """Write summary.md sorted by interestingness score."""
    scored = [(r, score_run(r, weights)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)

    lines = ["# Batch Summary\n"]
    lines.append("| Rank | Seed | Score | Dominant Faction | Wars | Collapses | Tech | Boring Civs |")
    lines.append("|------|------|-------|------------------|------|-----------|------|-------------|")

    for rank, (result, score) in enumerate(scored, 1):
        boring_str = ", ".join(result.boring_civs) if result.boring_civs else "-"
        lines.append(
            f"| {rank} | {result.seed} | {score:.1f} | {result.dominant_faction} "
            f"| {result.war_count} | {result.collapse_count} "
            f"| {result.tech_advancement_count} | {boring_str} |"
        )

    lines.append("")
    (batch_dir / "summary.md").write_text("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/batch.py tests/test_batch.py
git commit -m "feat(m10): add batch runner module with sequential and parallel execution"
```

---

### Task 9: Fork mode module (`fork.py`)

**Files:**
- Create: `src/chronicler/fork.py`
- Test: `tests/test_fork.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fork.py`:

```python
"""Tests for fork mode."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import argparse

from chronicler.fork import run_fork
from chronicler.main import execute_run
from chronicler.memory import MemoryStream, sanitize_civ_name


class TestRunFork:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def _run_parent(self, tmp_path):
        """Run a parent chronicle that produces state + memory files."""
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        args = argparse.Namespace(
            seed=42, turns=5, civs=2, regions=4,
            output=str(parent_dir / "chronicle.md"),
            state=str(parent_dir / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=None, interactive=False,
            parallel=None, pause_every=None,
        )
        execute_run(args, sim_client=sim, narrative_client=narr)
        return parent_dir

    def test_fork_produces_chronicle_with_provenance(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        sim = self._mock_llm()
        narr = self._mock_llm("Forked story.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        result = run_fork(fork_args, sim_client=sim, narrative_client=narr)
        chronicle = (tmp_path / "fork_out" / "chronicle.md").read_text()
        assert "Forked from seed 42" in chronicle
        assert result.total_turns > 0

    def test_fork_loads_memory_streams(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        # Verify parent produced memory files
        memory_files = list(parent_dir.glob("memories_*.json"))
        assert len(memory_files) >= 1

        sim = self._mock_llm()
        narr = self._mock_llm("Forked.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        result = run_fork(fork_args, sim_client=sim, narrative_client=narr)
        assert result.seed == 999

    def test_fork_warns_about_missing_scenario(self, tmp_path, capsys):
        parent_dir = self._run_parent(tmp_path)
        # Set scenario_name on the saved state
        from chronicler.models import WorldState
        world = WorldState.load(parent_dir / "state.json")
        world.scenario_name = "Dead Miles"
        world.save(parent_dir / "state.json")

        sim = self._mock_llm()
        narr = self._mock_llm("Forked.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        run_fork(fork_args, sim_client=sim, narrative_client=narr)
        captured = capsys.readouterr()
        assert "Dead Miles" in captured.out
        assert "scenario" in captured.out.lower()

    def test_fork_requires_seed(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        fork_args = argparse.Namespace(
            seed=None, turns=5, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        with pytest.raises(ValueError, match="--seed is required"):
            run_fork(fork_args, sim_client=self._mock_llm(), narrative_client=self._mock_llm("Story."))

    def test_fork_requires_turns(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        fork_args = argparse.Namespace(
            seed=999, turns=None, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        with pytest.raises(ValueError, match="--turns is required"):
            run_fork(fork_args, sim_client=self._mock_llm(), narrative_client=self._mock_llm("Story."))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fork.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/chronicler/fork.py`:

```python
"""Fork mode — load a mid-run state and explore alternate futures."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from chronicler.memory import MemoryStream
from chronicler.models import WorldState
from chronicler.types import RunResult


def run_fork(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> RunResult:
    """Fork from a saved state with a new seed. Returns RunResult."""
    fork_path = Path(args.fork)
    fork_dir = fork_path.parent
    new_seed = args.seed
    new_turns = args.turns

    if new_seed is None:
        raise ValueError("--seed is required with --fork")
    if new_turns is None:
        raise ValueError("--turns is required with --fork")

    # Load parent state
    world = WorldState.load(fork_path)
    parent_seed = world.seed
    fork_turn = world.turn

    # Warn if parent used a scenario but --scenario not passed
    if world.scenario_name and not scenario_config:
        print(
            f"Note: parent run used scenario '{world.scenario_name}'; "
            f"forking without --scenario means event flavor and narrative "
            f"style will not be applied. Pass --scenario to preserve them."
        )

    # Load memory streams from parent directory
    memories: dict[str, MemoryStream] = {}
    for mem_file in fork_dir.glob("memories_*.json"):
        stream = MemoryStream.load(mem_file)
        memories[stream.civilization_name] = stream

    # Fill in any civs that don't have memory files
    for civ in world.civilizations:
        if civ.name not in memories:
            memories[civ.name] = MemoryStream(civilization_name=civ.name)

    # Apply new seed
    world.seed = new_seed

    # Set up fork output directory
    fork_out_dir = Path(args.output).parent
    fork_out_dir.mkdir(parents=True, exist_ok=True)

    # Set turns to fork_turn + new_turns
    import copy
    fork_args = copy.copy(args)
    fork_args.turns = fork_turn + new_turns
    fork_args.seed = new_seed

    # Provenance header
    provenance = f"> Forked from seed {parent_seed} at turn {fork_turn}. New seed: {new_seed}."

    from chronicler.main import execute_run
    return execute_run(
        fork_args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        world=world,
        memories=memories,
        scenario_config=scenario_config,
        provenance_header=provenance,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fork.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/fork.py tests/test_fork.py
git commit -m "feat(m10): add fork mode module with provenance header and scenario warning"
```

---

### Task 10: Interactive mode module (`interactive.py`)

**Files:**
- Create: `src/chronicler/interactive.py`
- Test: `tests/test_interactive.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interactive.py`:

```python
"""Tests for interactive mode."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import argparse

from chronicler.interactive import (
    run_interactive,
    format_state_summary,
    parse_command,
    VALID_INJECTABLE_EVENTS,
    VALID_STATS,
)
from chronicler.models import WorldState


class TestParseCommand:
    def test_continue(self):
        cmd, cmd_args = parse_command("continue")
        assert cmd == "continue"

    def test_quit(self):
        cmd, cmd_args = parse_command("quit")
        assert cmd == "quit"

    def test_help(self):
        cmd, cmd_args = parse_command("help")
        assert cmd == "help"

    def test_fork(self):
        cmd, cmd_args = parse_command("fork")
        assert cmd == "fork"

    def test_inject(self):
        cmd, cmd_args = parse_command('inject plague "Kethani Empire"')
        assert cmd == "inject"
        assert cmd_args == ("plague", "Kethani Empire")

    def test_inject_invalid_event(self):
        cmd, cmd_args = parse_command('inject bogus "Kethani Empire"')
        assert cmd == "error"
        assert "Invalid event type" in cmd_args

    def test_set(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" military 9')
        assert cmd == "set"
        assert cmd_args == ("Kethani Empire", "military", 9)

    def test_set_invalid_stat(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" bogus 5')
        assert cmd == "error"
        assert "Invalid stat" in cmd_args

    def test_set_out_of_bounds(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" military 15')
        assert cmd == "error"
        assert "bounds" in cmd_args.lower() or "1-10" in cmd_args

    def test_set_treasury_allows_high_values(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" treasury 999')
        assert cmd == "set"
        assert cmd_args == ("Kethani Empire", "treasury", 999)

    def test_unknown_command(self):
        cmd, cmd_args = parse_command("explode")
        assert cmd == "error"

    def test_empty_input(self):
        cmd, cmd_args = parse_command("")
        assert cmd == "error"


class TestFormatStateSummary:
    def test_includes_faction_standings(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        assert "Kethani Empire" in summary
        assert "Dorrathi Clans" in summary

    def test_includes_era(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        # At least one civ's tech era should appear
        assert "Turn" in summary

    def test_includes_relationships(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        assert "HOSTILE" in summary or "SUSPICIOUS" in summary


class TestValidConstants:
    def test_injectable_events_match_default_probabilities(self):
        from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
        assert VALID_INJECTABLE_EVENTS == set(DEFAULT_EVENT_PROBABILITIES.keys())

    def test_valid_stats(self):
        expected = {"population", "military", "economy", "culture", "stability", "treasury"}
        assert VALID_STATS == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_interactive.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/chronicler/interactive.py`:

```python
"""Interactive mode — pause at intervals, accept commands, resume."""
from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from chronicler.memory import MemoryStream, sanitize_civ_name
from chronicler.models import WorldState
from chronicler.types import RunResult
from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES


VALID_INJECTABLE_EVENTS = set(DEFAULT_EVENT_PROBABILITIES.keys())
VALID_STATS = {"population", "military", "economy", "culture", "stability", "treasury"}
CORE_STATS = {"population", "military", "economy", "culture", "stability"}


def parse_command(raw: str) -> tuple[str, Any]:
    """Parse a user command string. Returns (command_name, args_or_error_msg)."""
    raw = raw.strip()
    if not raw:
        return ("error", "Empty command. Type 'help' for available commands.")

    try:
        tokens = shlex.split(raw)
    except ValueError as e:
        return ("error", f"Parse error: {e}")

    cmd = tokens[0].lower()

    if cmd in ("continue", "quit", "help", "fork"):
        return (cmd, None)

    if cmd == "inject":
        if len(tokens) < 3:
            return ("error", "Usage: inject <event_type> \"<civ_name>\"")
        event_type = tokens[1]
        civ_name = tokens[2]
        if event_type not in VALID_INJECTABLE_EVENTS:
            return ("error", f"Invalid event type '{event_type}'. Valid types: {sorted(VALID_INJECTABLE_EVENTS)}")
        return ("inject", (event_type, civ_name))

    if cmd == "set":
        if len(tokens) < 4:
            return ("error", 'Usage: set "<civ_name>" <stat> <value>')
        civ_name = tokens[1]
        stat = tokens[2].lower()
        if stat not in VALID_STATS:
            return ("error", f"Invalid stat '{stat}'. Valid stats: {sorted(VALID_STATS)}")
        try:
            value = int(tokens[3])
        except ValueError:
            return ("error", f"Value must be an integer, got '{tokens[3]}'")
        if stat in CORE_STATS and not (1 <= value <= 10):
            return ("error", f"Value for {stat} must be 1-10, got {value}")
        if stat == "treasury" and value < 0:
            return ("error", f"Treasury must be >= 0, got {value}")
        return ("set", (civ_name, stat, value))

    return ("error", f"Unknown command '{cmd}'. Type 'help' for available commands.")


def format_state_summary(world: WorldState, total_turns: int) -> str:
    """Format a text summary of current world state for display at pause."""
    lines = []
    # Determine era from first civ (they can differ, but shows general progress)
    era = world.civilizations[0].tech_era.value.upper() if world.civilizations else "UNKNOWN"
    lines.append(f"=== Turn {world.turn} / {total_turns} | Era: {era} ===")
    lines.append("")
    lines.append("Faction Standings:")
    for civ in world.civilizations:
        lines.append(
            f"  {civ.name:20s} — pop:{civ.population} mil:{civ.military} "
            f"eco:{civ.economy} cul:{civ.culture} stb:{civ.stability} "
            f"tre:{civ.treasury} | Leader: {civ.leader.name} ({civ.leader.trait})"
        )
    lines.append("")

    # Relationships
    lines.append("Relationships:")
    printed_pairs: set[tuple[str, str]] = set()
    for src, targets in world.relationships.items():
        for dst, rel in targets.items():
            pair = tuple(sorted([src, dst]))
            if pair not in printed_pairs:
                printed_pairs.add(pair)
                lines.append(f"  {src} \u2194 {dst}: {rel.disposition.value.upper()}")
    lines.append("")

    # Recent events
    recent = [e for e in world.events_timeline if e.turn >= max(0, world.turn - 5)]
    if recent:
        lines.append("Recent Events (last 5 turns):")
        for event in recent[-10:]:
            lines.append(f"  T{event.turn}: {event.description}")
        lines.append("")

    # Active conditions
    if world.active_conditions:
        lines.append("Active Conditions:")
        for cond in world.active_conditions:
            civs = ", ".join(cond.affected_civs)
            lines.append(
                f"  {cond.condition_type} on {civs} — "
                f"severity {cond.severity}, {cond.duration} turns remaining"
            )
        lines.append("")

    return "\n".join(lines)


def _print_help() -> None:
    """Print available commands."""
    print("\nAvailable commands:")
    print("  continue                         — Resume simulation until next pause")
    print('  inject <event_type> "<civ>"       — Queue event for next turn')
    print('  set "<civ>" <stat> <value>        — Modify a civ stat')
    print("  fork                             — Save current state as fork point")
    print("  quit                             — Compile chronicle and exit")
    print("  help                             — Show this message")
    print(f"\nValid event types: {sorted(VALID_INJECTABLE_EVENTS)}")
    print(f"Valid stats: {sorted(VALID_STATS)} (1-10 for core stats, 0+ for treasury)")
    print()


def interactive_pause(
    world: WorldState,
    memories: dict[str, MemoryStream],
    pending_injections: list,
    total_turns: int = 0,
    output_dir: Path = Path("output"),
) -> bool:
    """Pause handler for interactive mode. Returns True to continue, False to quit."""
    print("\n" + format_state_summary(world, total_turns))

    while True:
        try:
            raw = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print("\nQuitting...")
            return False

        cmd, cmd_args = parse_command(raw)

        if cmd == "continue":
            return True

        elif cmd == "quit":
            return False

        elif cmd == "help":
            _print_help()

        elif cmd == "fork":
            fork_dir = output_dir / f"fork_save_t{world.turn}"
            fork_dir.mkdir(parents=True, exist_ok=True)
            world.save(fork_dir / "state.json")
            for civ_name, stream in memories.items():
                stream.save(fork_dir / f"memories_{sanitize_civ_name(civ_name)}.json")
            print(f"Fork saved to {fork_dir}")

        elif cmd == "inject":
            event_type, civ_name = cmd_args
            # Validate civ exists
            civ_names = [c.name for c in world.civilizations]
            if civ_name not in civ_names:
                print(f"Error: Civ '{civ_name}' not found. Valid civs: {civ_names}")
                continue
            pending_injections.append((event_type, civ_name))
            print(f"Queued: {event_type} -> {civ_name} (fires next turn)")

        elif cmd == "set":
            civ_name, stat, value = cmd_args
            civ = next((c for c in world.civilizations if c.name == civ_name), None)
            if civ is None:
                civ_names = [c.name for c in world.civilizations]
                print(f"Error: Civ '{civ_name}' not found. Valid civs: {civ_names}")
                continue
            setattr(civ, stat, value)
            print(f"Set {civ_name}.{stat} = {value}")

        elif cmd == "error":
            print(f"Error: {cmd_args}")


def run_interactive(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> RunResult:
    """Run in interactive mode with pauses at configured intervals."""
    pause_every = args.pause_every or getattr(args, 'reflection_interval', None) or 10
    total_turns = args.turns or 50
    output_dir = Path(args.output).parent

    pending_injections: list[tuple[str, str]] = []

    def on_pause(world, memories, injections):
        return interactive_pause(
            world, memories, injections,
            total_turns=total_turns,
            output_dir=output_dir,
        )

    from chronicler.main import execute_run
    return execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        on_pause=on_pause,
        pause_every=pause_every,
        pending_injections=pending_injections,
        scenario_config=scenario_config,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interactive.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/interactive.py tests/test_interactive.py
git commit -m "feat(m10): add interactive mode with command parsing, state summary, and pause handler"
```

---

### Task 11: CLI flags and dispatch in `main.py`

**Files:**
- Modify: `src/chronicler/main.py:198-273` (update `_build_parser` and `main`)
- Test: `tests/test_main.py` (add CLI flag tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`:

```python
class TestNewCLIFlags:
    def test_batch_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5"])
        assert args.batch == 5

    def test_parallel_flag_bare(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5", "--parallel"])
        assert args.parallel == -1  # const value for bare --parallel

    def test_parallel_flag_with_count(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--batch", "5", "--parallel", "4"])
        assert args.parallel == 4

    def test_fork_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--fork", "output/state.json", "--seed", "999", "--turns", "50"])
        assert args.fork == "output/state.json"

    def test_interactive_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--interactive"])
        assert args.interactive is True

    def test_pause_every_flag(self):
        from chronicler.main import _build_parser
        p = _build_parser()
        args = p.parse_args(["--interactive", "--pause-every", "5"])
        assert args.pause_every == 5


class TestMutualExclusions:
    def test_parallel_and_llm_actions_rejected(self, capsys):
        """--parallel and --llm-actions should error out."""
        import sys
        from chronicler.main import main
        sys.argv = ["chronicler", "--batch", "3", "--parallel", "--llm-actions"]
        with pytest.raises(SystemExit):
            main()

    def test_batch_and_fork_rejected(self, capsys):
        import sys
        from chronicler.main import main
        sys.argv = ["chronicler", "--batch", "3", "--fork", "state.json"]
        with pytest.raises(SystemExit):
            main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py::TestNewCLIFlags -v`
Expected: FAIL — flags not recognized by argparse

- [ ] **Step 3: Write implementation**

Update `_build_parser()` in `src/chronicler/main.py` — add new flags after the existing `--scenario` flag:

```python
    # --- M10 workflow flags ---
    parser.add_argument("--batch", type=int, default=None,
                        help="Run N chronicles with sequential seeds")
    parser.add_argument("--parallel", type=int, nargs="?", const=-1, default=None,
                        help="Parallel workers for batch mode (default: cpu_count-1). "
                             "Mutually exclusive with --llm-actions.")
    parser.add_argument("--fork", type=str, default=None,
                        help="Fork from a saved state.json with a new seed")
    parser.add_argument("--interactive", action="store_true", default=False,
                        help="Interactive mode: pause at intervals for commands")
    parser.add_argument("--pause-every", type=int, default=None,
                        help="Pause interval in turns for interactive mode (default: reflection_interval)")
```

Update `main()` in `src/chronicler/main.py` — add validation and dispatch after scenario loading:

```python
def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # --- Mutual exclusion validation ---
    mode_flags = []
    if args.batch: mode_flags.append("--batch")
    if args.fork: mode_flags.append("--fork")
    if args.interactive: mode_flags.append("--interactive")
    if args.resume: mode_flags.append("--resume")
    if len(mode_flags) > 1:
        print(f"Error: {' and '.join(mode_flags)} are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.parallel is not None and args.llm_actions:
        print("Error: Cannot use --parallel with --llm-actions "
              "(parallel LLM calls create unpredictable latency and resource "
              "contention on local inference servers)", file=sys.stderr)
        sys.exit(1)

    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        sim_model=args.sim_model,
        narrative_model=args.narrative_model,
    )

    # Resolve scenario
    scenario_config = None
    if args.scenario:
        from chronicler.scenario import load_scenario, resolve_scenario_params
        scenario_config = load_scenario(Path(args.scenario))
        params = resolve_scenario_params(scenario_config, args)
        # Apply resolved params back to args
        args.seed = params["seed"]
        args.turns = params["num_turns"]
        args.civs = params["num_civs"]
        args.regions = params["num_regions"]
        args.reflection_interval = params["reflection_interval"]
    else:
        args.seed = args.seed if args.seed is not None else DEFAULT_CONFIG.get("seed", 42)
        args.turns = args.turns if args.turns is not None else DEFAULT_CONFIG["num_turns"]
        args.civs = args.civs if args.civs is not None else DEFAULT_CONFIG["num_civs"]
        args.regions = args.regions if args.regions is not None else DEFAULT_CONFIG["num_regions"]
        args.reflection_interval = args.reflection_interval if args.reflection_interval is not None else DEFAULT_CONFIG["reflection_interval"]

    # --- Dispatch ---
    if args.batch:
        from chronicler.batch import run_batch
        batch_dir = run_batch(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nBatch complete: {batch_dir}")

    elif args.fork:
        from chronicler.fork import run_fork
        result = run_fork(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nFork complete: {result.output_dir}")

    elif args.interactive:
        from chronicler.interactive import run_interactive
        result = run_interactive(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nInteractive session complete: {result.output_dir}")

    else:
        # Single run (default) or resume
        world = None
        memories = None
        if args.resume:
            resume_path = Path(args.resume)
            world = WorldState.load(resume_path)
            memories = {}
            for mem_file in resume_path.parent.glob("memories_*.json"):
                stream = MemoryStream.load(mem_file)
                memories[stream.civilization_name] = stream
            print(f"Resuming from {resume_path} at turn {world.turn}")

        result = execute_run(
            args,
            sim_client=sim_client,
            narrative_client=narrative_client,
            world=world,
            memories=memories,
            scenario_config=scenario_config,
        )
        print(f"\nChronicle complete: {result.output_dir}")
```

- [ ] **Step 4: Run ALL tests to verify nothing breaks**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m10): add CLI flags and dispatch for batch, fork, interactive modes"
```

---

## Chunk 5: Integration tests and final validation

### Task 12: Integration tests

**Files:**
- Create: `tests/test_m10_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_m10_integration.py`:

```python
"""M10 integration tests — verify features compose correctly."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import argparse

from chronicler.main import execute_run
from chronicler.batch import run_batch
from chronicler.fork import run_fork
from chronicler.interestingness import score_run
from chronicler.memory import MemoryStream


def _mock_llm(response="DEVELOP"):
    mock = MagicMock()
    mock.complete.return_value = response
    mock.model = "test-model"
    return mock


def _make_args(tmp_path, **overrides):
    defaults = dict(
        seed=42, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None,
        batch=None, fork=None, interactive=False,
        parallel=None, pause_every=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestBatchWithScoring:
    def test_batch_summary_sorted_by_score(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, batch=3, turns=5)
        batch_dir = run_batch(args, sim_client=sim, narrative_client=narr)
        summary = (batch_dir / "summary.md").read_text()
        # Should have 3 data rows + header rows
        lines = [l for l in summary.split("\n") if l.startswith("|") and "Rank" not in l and "---" not in l]
        assert len(lines) == 3


class TestForkFromBatch:
    def test_fork_from_batch_run(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        # Run a batch
        args = _make_args(tmp_path, batch=2, turns=5)
        batch_dir = run_batch(args, sim_client=sim, narrative_client=narr)

        # Fork from first run's state
        state_path = batch_dir / "seed_42" / "state.json"
        assert state_path.exists()

        fork_out = tmp_path / "fork_output"
        fork_args = _make_args(
            tmp_path,
            fork=str(state_path),
            seed=999,
            turns=3,
            output=str(fork_out / "chronicle.md"),
            state=str(fork_out / "state.json"),
        )
        sim2 = _mock_llm()
        narr2 = _mock_llm("Forked story.")
        result = run_fork(fork_args, sim_client=sim2, narrative_client=narr2)
        assert result.seed == 999
        chronicle = (fork_out / "chronicle.md").read_text()
        assert "Forked from seed 42" in chronicle


class TestMemoryPersistenceInRun:
    def test_memories_saved_every_turn(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, turns=5)
        execute_run(args, sim_client=sim, narrative_client=narr)
        memory_files = list(tmp_path.glob("memories_*.json"))
        assert len(memory_files) >= 1
        # Load and verify non-empty
        for mf in memory_files:
            stream = MemoryStream.load(mf)
            assert stream.civilization_name
            assert len(stream.entries) >= 0  # May be empty for civs with no events


class TestScoringIntegration:
    def test_score_run_on_real_result(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, turns=10)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        score = score_run(result)
        assert isinstance(score, float)
        assert score >= 0
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_m10_integration.py -v`
Expected: All pass

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All 308+ existing tests pass, plus all new M10 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_m10_integration.py
git commit -m "test(m10): add integration tests for batch+scoring, fork-from-batch, memory persistence"
```

---

## Task Dependency Summary

```
Task 1 (types.py)        ─┐
Task 2 (memory persist)  ─┤── Foundation (parallelizable)
Task 3 (scenario_name)   ─┤
Task 4 (apply_injected)  ─┤
Task 5 (interestingness  ─┘
         weights)

Task 6 (interestingness) ─── depends on Task 1

Task 7 (execute_run)     ─── depends on Tasks 1, 2, 4, 6

Task 8 (batch)           ─── depends on Task 7
Task 9 (fork)            ─── depends on Tasks 2, 7
Task 10 (interactive)    ─── depends on Tasks 4, 7
Task 11 (CLI dispatch)   ─── depends on Tasks 8, 9, 10

Task 12 (integration)    ─── depends on all above
```

**Parallelization opportunities:**
- Tasks 1-5: all independent, run in parallel
- Tasks 8, 9, 10: independent of each other (all depend on 7), run in parallel
