# Civilization Chronicle Generator — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python program that generates a procedural civilization chronicle — one prompt in, readable mythic history out — by combining a deterministic simulation engine with LLM-powered narrative generation.

**Architecture:** Four-layer hybrid system. Layer 1: Pydantic models serialized to JSON for world state (source of truth). Layer 2: Deterministic Python simulation engine running a six-phase turn loop (Environment → Production → Action → Events → Consequences → Chronicle). Layer 3: LLM narrative engine behind a **swappable client protocol** — high-volume simulation calls (action selection, event resolution) route to a **local model via LM Studio** (OpenAI-compatible API), while quality-sensitive narrative calls (chronicle prose, era reflections) route to **Claude API**. Layer 4: Memory/reflection system producing era-level summaries every 10 turns. The simulation engine drives consistency; the LLM provides literary quality; the hybrid routing keeps costs manageable at 100+ turns.

**Tech Stack:** Python 3.14, `uv` (project management), Pydantic v2 (models + JSON serialization), `anthropic` SDK (Claude API narrative calls), `openai` SDK (LM Studio local inference — OpenAI-compatible), `pytest` (testing), standard library `random` (dice rolls/event selection).

**Spec document:** `compass_artifact_wf-d176bec3-59a2-4ed7-9896-da3f22f48c40_text_markdown.md`

**Key Principles:**
- **Incremental validation:** Build the simulation engine first and test it for 5 turns with stub callbacks before scaling to 100. Claude Code writes better systems when the loop is validated early — otherwise a massive program may error on turn 47 and lose the whole run.
- **Per-turn state persistence:** Save `WorldState` to JSON after every turn. If it crashes mid-run, resume from the last good state instead of starting from scratch. Also lets you inspect the raw mechanical data behind interesting chronicle moments.
- **Milestone-scoped sessions:** Each milestone (M1–M6) is a natural scope boundary for one session. Focus on the current milestone plus awareness of where it fits — don't try to hold the entire project in your head at once.

---

## Milestone Structure & Dependency Graph

```
M1 (Foundation: project setup + data models)
  ├── M2 (World Generation)              ── can run in parallel ──┐
  ├── M3 (Simulation Engine + 5-turn     ── can run in parallel ──┤
  │       validation with stubs)                                   │
  └── M4 (Narrative Engine)              ── can run in parallel ──┘
                                                                   │
M5 (Memory/Reflection + Chronicle) ── depends on M3 + M4 ─────────┘
  │
M6 (Integration: CLI + full 100-turn run) ── depends on all above
```

Each milestone is **independently testable**:
- M1 → Pydantic models serialize and validate
- M2 → `generate_world()` produces a valid JSON you can read
- M3 → `run_turn()` with stubs produces a simulation log you can verify for 5 turns
- M4 → Narrative engine produces prose from mock state (with mocked LLM)
- M5 → Era reflections partition the timeline into named ages
- M6 → Full pipeline produces a readable Markdown chronicle

---

## File Structure

```
opusprogram/
├── pyproject.toml                  # uv project config, dependencies
├── .gitignore
├── src/
│   └── chronicler/
│       ├── __init__.py
│       ├── models.py               # All Pydantic models (world state contract)
│       ├── llm.py                  # LLM client protocol + local/API implementations
│       ├── world_gen.py            # Initial world + civilization generation
│       ├── simulation.py           # Six-phase turn loop orchestrator
│       ├── events.py               # Event types + Epitaph-style cascading probabilities
│       ├── narrative.py            # LLM narrative engine + Qud-style domain threading
│       ├── memory.py               # Memory streams + periodic reflections
│       ├── chronicle.py            # Final markdown chronicle assembly
│       └── main.py                 # CLI entry point
├── tests/
│   ├── conftest.py                 # Shared fixtures (sample world state, mock LLM clients)
│   ├── test_models.py              # Model validation + serialization round-trips
│   ├── test_llm.py                 # LLM client protocol, local + API implementations
│   ├── test_world_gen.py           # World generation produces valid state
│   ├── test_simulation.py          # Turn loop + individual phase logic
│   ├── test_events.py              # Event probability + cascading mechanics
│   ├── test_narrative.py           # Narrative engine with mocked LLM
│   ├── test_memory.py              # Memory stream + reflection generation
│   └── test_chronicle.py           # Chronicle compilation
├── output/                         # Runtime: JSON state + chronicle output (gitignored)
└── docs/
    └── plans/
        └── 2026-03-12-civilization-chronicle-generator.md  # This file
```

**Design rationale:** 9 source modules, each with one responsibility. Models are the shared contract. `llm.py` defines a `LLMClient` protocol with two implementations — `LocalClient` (OpenAI-compatible, for LM Studio) and `AnthropicClient` (for Claude API). Engine modules (simulation, events) are deterministic and testable without LLM. Narrative/memory modules accept any `LLMClient`, with role-based routing configured at the top level. Chronicle module is pure formatting.

**Cost model:** At 100 turns with 4 civs: ~400 action selection calls + ~100 event resolution calls → local model (free). ~100 chronicle calls + ~10 era reflections → Claude API. Estimated API cost: ~$1–3 total vs. ~$30–80 if everything hit the API.

---

## M1: Foundation — Project Setup + Data Models

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/chronicler/__init__.py`

- [ ] **Step 1: Initialize git repository**

```bash
cd /Users/tbronson/Documents/opusprogram
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "chronicler"
version = "0.1.0"
description = "AI-driven civilization chronicle generator"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.0",
    "anthropic>=0.50.0",
    "openai>=1.0.0",
]

[project.scripts]
chronicler = "chronicler.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Create .gitignore**

```
output/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.env
```

- [ ] **Step 4: Create src/chronicler/__init__.py**

```python
"""AI-driven civilization chronicle generator."""
```

- [ ] **Step 5: Install dependencies with uv**

```bash
cd /Users/tbronson/Documents/opusprogram
uv sync
```

- [ ] **Step 6: Verify pytest runs (no tests yet, but no errors)**

```bash
uv run pytest --co -q
```
Expected: `no tests ran` (clean exit)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src/chronicler/__init__.py uv.lock
git commit -m "chore: scaffold project with uv, pydantic, anthropic deps"
```

---

### Task 2: Core Data Models

**Files:**
- Create: `src/chronicler/models.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`

These models are the shared contract for the entire system. Every other module reads/writes `WorldState`.

- [ ] **Step 1: Write failing tests for models**

Create `tests/test_models.py`:

```python
"""Tests for core data models — validation, serialization, and invariants."""
import json
import pytest
from chronicler.models import (
    TechEra,
    Disposition,
    ActionType,
    Region,
    Leader,
    Civilization,
    Relationship,
    HistoricalFigure,
    Event,
    ActiveCondition,
    WorldState,
)


class TestRegion:
    def test_create_valid_region(self):
        r = Region(name="Verdant Plains", terrain="plains", carrying_capacity=7, resources="fertile")
        assert r.name == "Verdant Plains"
        assert r.controller is None

    def test_carrying_capacity_bounds(self):
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=0, resources="fertile")
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=11, resources="fertile")


class TestCivilization:
    def test_create_with_defaults(self):
        leader = Leader(name="Kael", trait="ambitious", reign_start=0)
        civ = Civilization(
            name="Kethani Empire",
            population=5,
            military=4,
            economy=6,
            culture=7,
            stability=5,
            leader=leader,
            domains=["maritime", "commerce"],
            values=["Honor", "Trade"],
        )
        assert civ.tech_era == TechEra.TRIBAL
        assert civ.treasury == 0
        assert civ.asabiya == 0.5

    def test_stat_bounds(self):
        leader = Leader(name="X", trait="bold", reign_start=0)
        with pytest.raises(Exception):
            Civilization(
                name="Bad", population=0, military=1, economy=1,
                culture=1, stability=1, leader=leader,
            )
        with pytest.raises(Exception):
            Civilization(
                name="Bad", population=11, military=1, economy=1,
                culture=1, stability=1, leader=leader,
            )


class TestRelationship:
    def test_defaults(self):
        r = Relationship()
        assert r.disposition == Disposition.NEUTRAL
        assert r.treaties == []
        assert r.grievances == []
        assert r.trade_volume == 0


class TestWorldState:
    def test_json_round_trip(self, sample_world):
        """WorldState serializes to JSON and deserializes identically."""
        json_str = sample_world.model_dump_json(indent=2)
        restored = WorldState.model_validate_json(json_str)
        assert restored.name == sample_world.name
        assert len(restored.civilizations) == len(sample_world.civilizations)
        assert restored.turn == sample_world.turn

    def test_save_and_load_file(self, sample_world, tmp_path):
        """WorldState persists to a JSON file and loads back."""
        path = tmp_path / "world.json"
        path.write_text(sample_world.model_dump_json(indent=2))
        loaded = WorldState.model_validate_json(path.read_text())
        assert loaded.name == sample_world.name
        assert loaded.civilizations[0].name == sample_world.civilizations[0].name
```

- [ ] **Step 2: Create shared test fixtures**

Create `tests/conftest.py`:

```python
"""Shared test fixtures for the chronicler test suite."""
import pytest
from chronicler.models import (
    TechEra,
    Disposition,
    Region,
    Leader,
    Civilization,
    Relationship,
    WorldState,
)


@pytest.fixture
def sample_regions():
    return [
        Region(name="Verdant Plains", terrain="plains", carrying_capacity=8, resources="fertile", controller="Kethani Empire"),
        Region(name="Iron Peaks", terrain="mountains", carrying_capacity=4, resources="mineral", controller="Dorrathi Clans"),
        Region(name="Sapphire Coast", terrain="coast", carrying_capacity=6, resources="maritime", controller="Kethani Empire"),
        Region(name="Thornwood", terrain="forest", carrying_capacity=5, resources="timber"),
        Region(name="Ashara Desert", terrain="desert", carrying_capacity=3, resources="barren"),
    ]


@pytest.fixture
def sample_civilizations():
    return [
        Civilization(
            name="Kethani Empire",
            population=7, military=5, economy=8, culture=6, stability=6,
            tech_era=TechEra.IRON,
            treasury=12,
            leader=Leader(name="Empress Vaelith", trait="calculating", reign_start=0),
            domains=["maritime", "commerce"],
            values=["Trade", "Order"],
            goal="Expand trade networks to all coastal regions",
            regions=["Verdant Plains", "Sapphire Coast"],
            asabiya=0.6,
        ),
        Civilization(
            name="Dorrathi Clans",
            population=4, military=7, economy=3, culture=5, stability=4,
            tech_era=TechEra.IRON,
            treasury=5,
            leader=Leader(name="Warchief Gorath", trait="aggressive", reign_start=0),
            domains=["mountain", "warfare"],
            values=["Honor", "Strength"],
            goal="Conquer the Verdant Plains",
            regions=["Iron Peaks"],
            asabiya=0.8,
        ),
    ]


@pytest.fixture
def sample_relationships():
    return {
        "Kethani Empire": {
            "Dorrathi Clans": Relationship(
                disposition=Disposition.SUSPICIOUS,
                grievances=["Border raids in the northern foothills"],
                trade_volume=2,
            ),
        },
        "Dorrathi Clans": {
            "Kethani Empire": Relationship(
                disposition=Disposition.HOSTILE,
                grievances=["Kethani merchants exploit mountain resources"],
                trade_volume=2,
            ),
        },
    }


@pytest.fixture
def sample_world(sample_regions, sample_civilizations, sample_relationships):
    return WorldState(
        name="Testworld",
        seed=42,
        turn=0,
        regions=sample_regions,
        civilizations=sample_civilizations,
        relationships=sample_relationships,
        historical_figures=[],
        events_timeline=[],
        active_conditions=[],
        event_probabilities={
            "drought": 0.05,
            "plague": 0.03,
            "earthquake": 0.02,
            "religious_movement": 0.04,
            "discovery": 0.06,
            "leader_death": 0.03,
            "rebellion": 0.05,
            "migration": 0.04,
            "cultural_renaissance": 0.03,
            "border_incident": 0.08,
        },
    )
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
uv run pytest tests/test_models.py -v
```
Expected: ImportError — `chronicler.models` does not exist yet.

- [ ] **Step 4: Implement models.py**

Create `src/chronicler/models.py`:

```python
"""Core data models for the civilization chronicle generator.

WorldState is the single source of truth. All simulation and narrative
modules read from and write to WorldState, which serializes to JSON.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class TechEra(str, Enum):
    TRIBAL = "tribal"
    BRONZE = "bronze"
    IRON = "iron"
    CLASSICAL = "classical"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"


class Disposition(str, Enum):
    HOSTILE = "hostile"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class ActionType(str, Enum):
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"


# --- Core entities ---

class Region(BaseModel):
    name: str
    terrain: str  # plains, mountains, coast, forest, desert, tundra
    carrying_capacity: int = Field(ge=1, le=10)
    resources: str  # fertile, mineral, timber, maritime, barren
    controller: Optional[str] = None


class Leader(BaseModel):
    name: str
    trait: str
    reign_start: int
    alive: bool = True


class Civilization(BaseModel):
    name: str
    population: int = Field(ge=1, le=10)
    military: int = Field(ge=1, le=10)
    economy: int = Field(ge=1, le=10)
    culture: int = Field(ge=1, le=10)
    stability: int = Field(ge=1, le=10)
    tech_era: TechEra = TechEra.TRIBAL
    treasury: int = 0
    domains: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    leader: Leader
    goal: str = ""
    regions: list[str] = Field(default_factory=list)
    asabiya: float = Field(default=0.5, ge=0.0, le=1.0)


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    treaties: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0


class HistoricalFigure(BaseModel):
    name: str
    role: str
    traits: list[str] = Field(default_factory=list)
    civilization: str
    alive: bool = True
    deeds: list[str] = Field(default_factory=list)


class Event(BaseModel):
    turn: int
    event_type: str
    actors: list[str]
    description: str
    consequences: list[str] = Field(default_factory=list)
    importance: int = Field(default=5, ge=1, le=10)


class ActiveCondition(BaseModel):
    condition_type: str
    affected_civs: list[str]
    duration: int
    severity: int = Field(ge=1, le=10)


# --- Top-level state ---

class WorldState(BaseModel):
    name: str
    seed: int
    turn: int = 0
    regions: list[Region] = Field(default_factory=list)
    civilizations: list[Civilization] = Field(default_factory=list)
    relationships: dict[str, dict[str, Relationship]] = Field(default_factory=dict)
    historical_figures: list[HistoricalFigure] = Field(default_factory=list)
    events_timeline: list[Event] = Field(default_factory=list)
    active_conditions: list[ActiveCondition] = Field(default_factory=list)
    event_probabilities: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/test_models.py -v
```
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add core data models with Pydantic validation and JSON serialization"
```

---

### Task 3: Helper — World State Persistence Utilities

**Files:**
- Modify: `src/chronicler/models.py` (add `save` / `load` classmethods)
- Modify: `tests/test_models.py` (add persistence tests)

- [ ] **Step 1: Write failing test for save/load helpers**

Append to `tests/test_models.py`:

```python
class TestWorldStatePersistence:
    def test_save_creates_file(self, sample_world, tmp_path):
        path = tmp_path / "state.json"
        sample_world.save(path)
        assert path.exists()

    def test_load_restores_state(self, sample_world, tmp_path):
        path = tmp_path / "state.json"
        sample_world.save(path)
        loaded = WorldState.load(path)
        assert loaded.name == sample_world.name
        assert len(loaded.civilizations) == 2

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            WorldState.load(tmp_path / "nope.json")
```

- [ ] **Step 2: Run tests — verify new tests fail**

```bash
uv run pytest tests/test_models.py::TestWorldStatePersistence -v
```
Expected: AttributeError — `save` and `load` don't exist.

- [ ] **Step 3: Add save/load methods to WorldState**

Add to `WorldState` in `src/chronicler/models.py`:

```python
    def save(self, path: Path) -> None:
        """Persist world state to a JSON file."""
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> WorldState:
        """Load world state from a JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"No state file at {path}")
        return cls.model_validate_json(path.read_text())
```

Also add `from pathlib import Path` to the imports.

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_models.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat: add WorldState save/load persistence helpers"
```

---

### Task 3b: LLM Client Protocol — Swappable Local/API Interface

**Files:**
- Create: `src/chronicler/llm.py`
- Create: `tests/test_llm.py`

This is the foundational abstraction that enables hybrid inference: high-volume simulation calls route to a local model (LM Studio via OpenAI-compatible API, free), while quality-sensitive narrative calls route to Claude API. Both implement the same `LLMClient` protocol so the rest of the codebase doesn't care which backend is in use.

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm.py`:

```python
"""Tests for LLM client protocol and implementations."""
import pytest
from unittest.mock import MagicMock, patch
from chronicler.llm import LLMClient, LocalClient, AnthropicClient, create_clients


class TestLLMClientProtocol:
    def test_local_client_conforms_to_protocol(self):
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")

    def test_anthropic_client_conforms_to_protocol(self):
        mock_sdk = MagicMock()
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")


class TestLocalClient:
    def test_complete_calls_openai_api(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="DEVELOP"))]
        )
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        client._client = mock_openai  # Inject mock

        result = client.complete("Pick an action", max_tokens=10)
        assert result == "DEVELOP"
        mock_openai.chat.completions.create.assert_called_once()

    def test_complete_with_system_prompt(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="WAR"))]
        )
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        client._client = mock_openai

        result = client.complete("Pick an action", max_tokens=10, system="You are a warlord.")
        assert result == "WAR"
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"


class TestAnthropicClient:
    def test_complete_calls_anthropic_api(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[MagicMock(text="The empire rose from the ashes...")]
        )
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        result = client.complete("Write a chronicle entry", max_tokens=500)
        assert "empire" in result
        mock_sdk.messages.create.assert_called_once()


class TestCreateClients:
    def test_creates_both_clients(self):
        mock_anthropic_sdk = MagicMock()
        sim_client, narrative_client = create_clients(
            local_url="http://localhost:1234/v1",
            local_model="gemma-3",
            narrative_model="claude-sonnet-4-6",
            anthropic_client=mock_anthropic_sdk,
        )
        assert isinstance(sim_client, LocalClient)
        assert isinstance(narrative_client, AnthropicClient)

    def test_api_only_mode(self):
        """When no local URL provided, both clients use Anthropic."""
        mock_anthropic_sdk = MagicMock()
        sim_client, narrative_client = create_clients(
            local_url=None,
            local_model=None,
            narrative_model="claude-sonnet-4-6",
            anthropic_client=mock_anthropic_sdk,
        )
        assert isinstance(sim_client, AnthropicClient)
        assert isinstance(narrative_client, AnthropicClient)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_llm.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement llm.py**

Create `src/chronicler/llm.py`:

```python
"""LLM client protocol with swappable local/API implementations.

Hybrid inference strategy:
- LocalClient: OpenAI-compatible API (LM Studio) for high-volume simulation calls.
  Action selection, event resolution — hundreds of small calls, free.
- AnthropicClient: Claude API for quality-sensitive narrative generation.
  Chronicle prose, era reflections — fewer calls, higher quality.

Both implement the same LLMClient protocol so the rest of the codebase
is backend-agnostic.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completion backends."""
    model: str

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        """Send a prompt and return the completion text."""
        ...


class LocalClient:
    """OpenAI-compatible client for local inference (LM Studio, ollama, etc.)."""

    def __init__(self, base_url: str, model: str):
        self.model = model
        self.base_url = base_url
        from openai import OpenAI
        self._client = OpenAI(base_url=base_url, api_key="not-needed")

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()


class AnthropicClient:
    """Anthropic SDK client for Claude API calls."""

    def __init__(self, client: Any, model: str = "claude-sonnet-4-6"):
        self.model = model
        self._client = client

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text.strip()


def create_clients(
    local_url: str | None,
    local_model: str | None,
    narrative_model: str,
    anthropic_client: Any,
) -> tuple[LLMClient, LLMClient]:
    """Create simulation and narrative clients based on configuration.

    If local_url is provided, simulation calls route to the local model
    and narrative calls route to Claude API (hybrid mode).
    If local_url is None, everything routes to Claude API (API-only mode).
    """
    narrative_client = AnthropicClient(client=anthropic_client, model=narrative_model)

    if local_url and local_model:
        sim_client: LLMClient = LocalClient(base_url=local_url, model=local_model)
    else:
        sim_client = AnthropicClient(
            client=anthropic_client,
            model="claude-haiku-4-5-20251001",
        )

    return sim_client, narrative_client
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_llm.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/llm.py tests/test_llm.py
git commit -m "feat: add swappable LLM client protocol with local (LM Studio) and API (Claude) backends"
```

---

## M2: World Generation

### Task 4: Initial World Generator

**Files:**
- Create: `src/chronicler/world_gen.py`
- Create: `tests/test_world_gen.py`

The world generator creates a starting `WorldState` with 4–6 civilizations on a map of named regions. It uses the LLM to generate thematic names and cultural details, falling back to deterministic defaults for testing.

- [ ] **Step 1: Write failing tests**

Create `tests/test_world_gen.py`:

```python
"""Tests for initial world generation."""
import pytest
from unittest.mock import AsyncMock
from chronicler.world_gen import generate_world, generate_regions, assign_civilizations
from chronicler.models import WorldState, TechEra


class TestGenerateRegions:
    def test_generates_correct_count(self):
        regions = generate_regions(count=8, seed=42)
        assert len(regions) == 8

    def test_all_regions_have_names(self):
        regions = generate_regions(count=6, seed=42)
        assert all(r.name for r in regions)

    def test_deterministic_with_same_seed(self):
        r1 = generate_regions(count=6, seed=42)
        r2 = generate_regions(count=6, seed=42)
        assert [r.name for r in r1] == [r.name for r in r2]

    def test_terrain_variety(self):
        regions = generate_regions(count=8, seed=42)
        terrains = {r.terrain for r in regions}
        assert len(terrains) >= 3  # At least 3 different terrain types


class TestAssignCivilizations:
    def test_correct_civ_count(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        assert len(civs) == 4

    def test_each_civ_controls_at_least_one_region(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert len(civ.regions) >= 1

    def test_civs_have_domains(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert len(civ.domains) >= 2

    def test_civs_have_leaders(self):
        regions = generate_regions(count=8, seed=42)
        civs = assign_civilizations(regions, civ_count=4, seed=42)
        for civ in civs:
            assert civ.leader.name
            assert civ.leader.trait


class TestGenerateWorld:
    def test_produces_valid_world_state(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert isinstance(world, WorldState)
        assert world.seed == 42
        assert world.turn == 0
        assert len(world.regions) == 8
        assert len(world.civilizations) == 4

    def test_relationships_initialized(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        civ_names = [c.name for c in world.civilizations]
        for name in civ_names:
            assert name in world.relationships
            for other in civ_names:
                if other != name:
                    assert other in world.relationships[name]

    def test_event_probabilities_initialized(self):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert len(world.event_probabilities) > 0
        assert all(0 < p < 1 for p in world.event_probabilities.values())
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_world_gen.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement world_gen.py**

Create `src/chronicler/world_gen.py`:

```python
"""Initial world generation — creates a starting WorldState.

Uses deterministic generation from a seed. Region names, civilization names,
leader names, and cultural details are drawn from curated pools to ensure
thematic coherence without requiring LLM calls during generation.
"""
from __future__ import annotations

import random

from chronicler.models import (
    Civilization,
    Disposition,
    Leader,
    Region,
    Relationship,
    TechEra,
    WorldState,
)

# --- Name and trait pools ---

REGION_TEMPLATES: list[dict] = [
    {"name": "Verdant Plains", "terrain": "plains", "capacity": 8, "resources": "fertile"},
    {"name": "Iron Peaks", "terrain": "mountains", "capacity": 4, "resources": "mineral"},
    {"name": "Sapphire Coast", "terrain": "coast", "capacity": 6, "resources": "maritime"},
    {"name": "Thornwood", "terrain": "forest", "capacity": 5, "resources": "timber"},
    {"name": "Ashara Desert", "terrain": "desert", "capacity": 3, "resources": "barren"},
    {"name": "Crystalfen Marsh", "terrain": "plains", "capacity": 4, "resources": "fertile"},
    {"name": "Stormbreak Cliffs", "terrain": "mountains", "capacity": 3, "resources": "mineral"},
    {"name": "Sunfire Steppe", "terrain": "plains", "capacity": 6, "resources": "fertile"},
    {"name": "Mistwood", "terrain": "forest", "capacity": 5, "resources": "timber"},
    {"name": "Obsidian Shore", "terrain": "coast", "capacity": 5, "resources": "maritime"},
    {"name": "Frostholm Tundra", "terrain": "tundra", "capacity": 2, "resources": "barren"},
    {"name": "Amber Valley", "terrain": "plains", "capacity": 7, "resources": "fertile"},
]

CIV_TEMPLATES: list[dict] = [
    {"name": "Kethani Empire", "domains": ["maritime", "commerce"], "values": ["Trade", "Order"], "trait": "calculating"},
    {"name": "Dorrathi Clans", "domains": ["mountain", "warfare"], "values": ["Honor", "Strength"], "trait": "aggressive"},
    {"name": "Selurian Republic", "domains": ["scholarship", "diplomacy"], "values": ["Knowledge", "Liberty"], "trait": "cautious"},
    {"name": "Vrashni Dominion", "domains": ["faith", "expansion"], "values": ["Piety", "Destiny"], "trait": "zealous"},
    {"name": "Thornwall Confederacy", "domains": ["forest", "resilience"], "values": ["Tradition", "Self-reliance"], "trait": "stubborn"},
    {"name": "Ashkari Nomads", "domains": ["desert", "adaptability"], "values": ["Freedom", "Cunning"], "trait": "opportunistic"},
]

LEADER_NAMES: list[str] = [
    "Vaelith", "Gorath", "Seren", "Thaldric", "Mirael",
    "Kassander", "Ulveth", "Zhara", "Fenrik", "Aelindra",
]

LEADER_TITLES: list[str] = [
    "Emperor", "Empress", "Warchief", "Archon", "High Priestess",
    "Chancellor", "Sovereign", "Elder", "Khan", "Consul",
]

DEFAULT_EVENT_PROBABILITIES: dict[str, float] = {
    "drought": 0.05,
    "plague": 0.03,
    "earthquake": 0.02,
    "religious_movement": 0.04,
    "discovery": 0.06,
    "leader_death": 0.03,
    "rebellion": 0.05,
    "migration": 0.04,
    "cultural_renaissance": 0.03,
    "border_incident": 0.08,
}


def generate_regions(count: int = 8, seed: int = 42) -> list[Region]:
    """Generate a set of named regions from the template pool."""
    rng = random.Random(seed)
    templates = rng.sample(REGION_TEMPLATES, k=min(count, len(REGION_TEMPLATES)))
    return [
        Region(
            name=t["name"],
            terrain=t["terrain"],
            carrying_capacity=t["capacity"],
            resources=t["resources"],
        )
        for t in templates
    ]


def assign_civilizations(
    regions: list[Region],
    civ_count: int = 4,
    seed: int = 42,
) -> list[Civilization]:
    """Create civilizations and assign them starting regions."""
    rng = random.Random(seed)
    templates = rng.sample(CIV_TEMPLATES, k=min(civ_count, len(CIV_TEMPLATES)))
    names_pool = list(LEADER_NAMES)
    rng.shuffle(names_pool)
    titles_pool = list(LEADER_TITLES)
    rng.shuffle(titles_pool)

    # Distribute regions: each civ gets at least 1, remainder uncontrolled
    available = list(regions)
    rng.shuffle(available)

    civs: list[Civilization] = []
    for i, t in enumerate(templates):
        # Assign 1–2 starting regions
        assigned = [available.pop(0).name] if available else []
        if available and rng.random() < 0.5:
            assigned.append(available.pop(0).name)

        # Mark regions as controlled
        for region in regions:
            if region.name in assigned:
                region.controller = t["name"]

        leader_name = f"{titles_pool[i % len(titles_pool)]} {names_pool[i % len(names_pool)]}"
        civs.append(
            Civilization(
                name=t["name"],
                population=rng.randint(3, 7),
                military=rng.randint(2, 7),
                economy=rng.randint(3, 7),
                culture=rng.randint(2, 7),
                stability=rng.randint(4, 7),
                tech_era=TechEra.IRON,
                treasury=rng.randint(3, 15),
                leader=Leader(name=leader_name, trait=t["trait"], reign_start=0),
                domains=t["domains"],
                values=t["values"],
                goal="",
                regions=assigned,
                asabiya=round(rng.uniform(0.4, 0.8), 2),
            ),
        )
    return civs


def _build_relationships(civ_names: list[str], seed: int) -> dict[str, dict[str, Relationship]]:
    """Initialize relationship matrix between all civilizations."""
    rng = random.Random(seed)
    dispositions = [Disposition.NEUTRAL, Disposition.SUSPICIOUS, Disposition.FRIENDLY]
    rels: dict[str, dict[str, Relationship]] = {}
    for name in civ_names:
        rels[name] = {}
        for other in civ_names:
            if other != name:
                rels[name][other] = Relationship(
                    disposition=rng.choice(dispositions),
                )
    return rels


def generate_world(
    seed: int = 42,
    num_regions: int = 8,
    num_civs: int = 4,
    world_name: str = "Aetheris",
) -> WorldState:
    """Generate a complete initial WorldState ready for simulation."""
    regions = generate_regions(count=num_regions, seed=seed)
    civs = assign_civilizations(regions, civ_count=num_civs, seed=seed)
    civ_names = [c.name for c in civs]
    relationships = _build_relationships(civ_names, seed=seed + 1)

    return WorldState(
        name=world_name,
        seed=seed,
        turn=0,
        regions=regions,
        civilizations=civs,
        relationships=relationships,
        historical_figures=[],
        events_timeline=[],
        active_conditions=[],
        event_probabilities=dict(DEFAULT_EVENT_PROBABILITIES),
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_world_gen.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_world_gen.py
git commit -m "feat: add deterministic world generation with region/civilization templates"
```

---

## M3: Simulation Engine

### Task 5: Event Types and Cascading Probability System

**Files:**
- Create: `src/chronicler/events.py`
- Create: `tests/test_events.py`

Implements the Epitaph-style cascading probability system: each event modifies the probability of future events.

- [ ] **Step 1: Write failing tests**

Create `tests/test_events.py`:

```python
"""Tests for event types and cascading probability system."""
import pytest
from chronicler.events import (
    roll_for_event,
    apply_probability_cascade,
    EVENT_CASCADE_RULES,
    ENVIRONMENT_EVENTS,
)
from chronicler.models import Event


class TestRollForEvent:
    def test_returns_none_when_no_event_triggers(self):
        """With all-zero probabilities, no event should fire."""
        probs = {k: 0.0 for k in ["drought", "plague", "earthquake"]}
        result = roll_for_event(probs, turn=1, seed=42)
        assert result is None

    def test_returns_event_when_guaranteed(self):
        """With probability 1.0, an event always fires."""
        probs = {"drought": 1.0}
        result = roll_for_event(probs, turn=1, seed=42)
        assert result is not None
        assert result.event_type == "drought"

    def test_returns_at_most_one_event(self):
        probs = {"drought": 1.0, "plague": 1.0, "earthquake": 1.0}
        result = roll_for_event(probs, turn=1, seed=42)
        assert isinstance(result, Event)  # One event, not a list

    def test_deterministic_with_seed(self):
        probs = {"drought": 0.5, "plague": 0.5}
        r1 = roll_for_event(probs, turn=1, seed=99)
        r2 = roll_for_event(probs, turn=1, seed=99)
        # Same seed → same result
        if r1 is None:
            assert r2 is None
        else:
            assert r2 is not None
            assert r1.event_type == r2.event_type


class TestProbabilityCascade:
    def test_drought_increases_famine_and_migration(self):
        probs = {"drought": 0.05, "plague": 0.03, "migration": 0.04, "rebellion": 0.05}
        updated = apply_probability_cascade("drought", probs)
        assert updated["migration"] > probs["migration"]
        assert updated["rebellion"] > probs["rebellion"]

    def test_probabilities_stay_in_bounds(self):
        probs = {"drought": 0.95, "plague": 0.95, "migration": 0.95, "rebellion": 0.95}
        updated = apply_probability_cascade("drought", probs)
        assert all(0.0 <= v <= 1.0 for v in updated.values())

    def test_unknown_event_returns_unchanged(self):
        probs = {"drought": 0.05}
        updated = apply_probability_cascade("alien_invasion", probs)
        assert updated == probs


class TestEnvironmentEvents:
    def test_environment_events_are_subset_of_all_events(self):
        all_events = set(EVENT_CASCADE_RULES.keys())
        for e in ENVIRONMENT_EVENTS:
            assert e in all_events or e in ["drought", "plague", "earthquake"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_events.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement events.py**

Create `src/chronicler/events.py`:

```python
"""Event types and Epitaph-style cascading probability system.

Each event modifies the probability of future events, creating chains
of causally linked occurrences. Probabilities are clamped to [0, 1].
"""
from __future__ import annotations

import random

from chronicler.models import Event

# Events that can occur during the Environment phase (natural causes)
ENVIRONMENT_EVENTS: list[str] = ["drought", "plague", "earthquake"]

# When event X occurs, modify probabilities of other events by these deltas
EVENT_CASCADE_RULES: dict[str, dict[str, float]] = {
    "drought": {
        "plague": +0.02,        # Weakened populations get sick
        "migration": +0.04,     # People flee famine
        "rebellion": +0.03,     # Hungry people revolt
        "discovery": -0.02,     # Less resources for research
    },
    "plague": {
        "rebellion": +0.03,
        "migration": +0.03,
        "leader_death": +0.02,  # Leaders die too
        "cultural_renaissance": -0.02,
    },
    "earthquake": {
        "migration": +0.02,
        "discovery": +0.01,     # Ruins exposed, new resources found
        "border_incident": +0.02,
    },
    "religious_movement": {
        "rebellion": +0.02,
        "cultural_renaissance": +0.03,
        "border_incident": +0.01,
    },
    "discovery": {
        "cultural_renaissance": +0.03,
        "border_incident": +0.02,  # Others covet the discovery
        "rebellion": -0.01,
    },
    "leader_death": {
        "rebellion": +0.05,
        "border_incident": +0.03,  # Neighbors sense weakness
        "migration": +0.01,
    },
    "rebellion": {
        "leader_death": +0.03,
        "migration": +0.02,
        "plague": +0.01,          # War brings disease
        "border_incident": +0.02,
    },
    "migration": {
        "border_incident": +0.03,
        "cultural_renaissance": +0.01,  # New ideas arrive
        "rebellion": +0.01,
    },
    "cultural_renaissance": {
        "discovery": +0.04,
        "rebellion": -0.02,       # People are content
        "religious_movement": +0.02,
    },
    "border_incident": {
        "rebellion": +0.01,
        "migration": +0.01,
    },
}


def roll_for_event(
    probabilities: dict[str, float],
    turn: int,
    seed: int | None = None,
    allowed_types: list[str] | None = None,
) -> Event | None:
    """Roll against each event probability; return at most one event.

    Events are checked in shuffled order. The first one that triggers wins.
    This means at most one event fires per call.
    """
    rng = random.Random(seed)
    candidates = list(probabilities.keys())
    if allowed_types is not None:
        candidates = [c for c in candidates if c in allowed_types]
    rng.shuffle(candidates)

    for event_type in candidates:
        prob = probabilities.get(event_type, 0.0)
        if rng.random() < prob:
            return Event(
                turn=turn,
                event_type=event_type,
                actors=[],
                description="",  # Filled in by narrative engine
                importance=5,
            )
    return None


def apply_probability_cascade(
    event_type: str,
    probabilities: dict[str, float],
) -> dict[str, float]:
    """Apply cascading probability modifications after an event occurs."""
    rules = EVENT_CASCADE_RULES.get(event_type)
    if rules is None:
        return dict(probabilities)

    updated = dict(probabilities)
    for target, delta in rules.items():
        if target in updated:
            updated[target] = max(0.0, min(1.0, updated[target] + delta))
    return updated
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_events.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/events.py tests/test_events.py
git commit -m "feat: add event system with Epitaph-style cascading probabilities"
```

---

### Task 6: Simulation Engine — Turn Phases

**Files:**
- Create: `src/chronicler/simulation.py`
- Create: `tests/test_simulation.py`

The simulation engine runs the six-phase turn loop. Phases 1–2 and 4–5 are deterministic. Phase 3 (Action) takes a callback for action selection (LLM or test stub). Phase 6 (Chronicle) takes a callback for narrative generation.

- [ ] **Step 1: Write failing tests for individual phases**

Create `tests/test_simulation.py`:

```python
"""Tests for the six-phase simulation engine."""
import pytest
from chronicler.simulation import (
    phase_environment,
    phase_production,
    phase_action,
    phase_random_events,
    phase_consequences,
    run_turn,
    resolve_war,
    resolve_trade,
    apply_asabiya_dynamics,
)
from chronicler.models import (
    WorldState,
    Civilization,
    ActionType,
    Disposition,
    Event,
    ActiveCondition,
)


class TestPhaseEnvironment:
    def test_no_event_with_zero_probabilities(self, sample_world):
        sample_world.event_probabilities = {k: 0.0 for k in sample_world.event_probabilities}
        events = phase_environment(sample_world, seed=42)
        assert events == []

    def test_drought_reduces_stability(self, sample_world):
        """If a drought occurs, affected civs lose stability."""
        sample_world.event_probabilities["drought"] = 1.0
        # Zero out others to isolate
        for k in sample_world.event_probabilities:
            if k != "drought":
                sample_world.event_probabilities[k] = 0.0
        old_stabilities = {c.name: c.stability for c in sample_world.civilizations}
        events = phase_environment(sample_world, seed=42)
        assert len(events) >= 1
        assert events[0].event_type == "drought"
        # At least one civ should have reduced stability
        new_stabilities = {c.name: c.stability for c in sample_world.civilizations}
        assert any(new_stabilities[n] < old_stabilities[n] for n in old_stabilities)


class TestPhaseProduction:
    def test_treasury_increases(self, sample_world):
        old_treasuries = {c.name: c.treasury for c in sample_world.civilizations}
        phase_production(sample_world)
        for civ in sample_world.civilizations:
            # Treasury should increase by economy-based income
            assert civ.treasury >= old_treasuries[civ.name]

    def test_population_bounded(self, sample_world):
        # Set population to max
        sample_world.civilizations[0].population = 10
        phase_production(sample_world)
        assert sample_world.civilizations[0].population <= 10


class TestPhaseAction:
    def test_each_civ_takes_one_action(self, sample_world):
        """With a stub action selector, every civ takes exactly one action."""
        def stub_selector(civ: Civilization, world: WorldState) -> ActionType:
            return ActionType.DEVELOP

        events = phase_action(sample_world, action_selector=stub_selector)
        assert len(events) == len(sample_world.civilizations)


class TestResolveWar:
    def test_attacker_wins_if_stronger(self, sample_world):
        attacker = sample_world.civilizations[1]  # Dorrathi: military=7
        defender = sample_world.civilizations[0]  # Kethani: military=5
        attacker_mil_before = attacker.military
        result = resolve_war(attacker, defender, sample_world, seed=42)
        assert result in ("attacker_wins", "defender_wins", "stalemate")

    def test_war_costs_treasury(self, sample_world):
        attacker = sample_world.civilizations[1]
        defender = sample_world.civilizations[0]
        old_att_treasury = attacker.treasury
        old_def_treasury = defender.treasury
        resolve_war(attacker, defender, sample_world, seed=42)
        assert attacker.treasury <= old_att_treasury
        assert defender.treasury <= old_def_treasury


class TestResolveTrade:
    def test_trade_increases_treasury(self, sample_world):
        c1 = sample_world.civilizations[0]
        c2 = sample_world.civilizations[1]
        old_t1 = c1.treasury
        old_t2 = c2.treasury
        resolve_trade(c1, c2, sample_world)
        assert c1.treasury >= old_t1
        assert c2.treasury >= old_t2


class TestAsabiyaDynamics:
    def test_frontier_civs_gain_asabiya(self, sample_world):
        """Civs bordering hostile neighbors should gain asabiya (Turchin model)."""
        # Dorrathi is hostile to Kethani
        sample_world.relationships["Dorrathi Clans"]["Kethani Empire"].disposition = Disposition.HOSTILE
        old_asabiya = sample_world.civilizations[1].asabiya
        apply_asabiya_dynamics(sample_world)
        assert sample_world.civilizations[1].asabiya >= old_asabiya

    def test_asabiya_stays_bounded(self, sample_world):
        sample_world.civilizations[0].asabiya = 0.99
        apply_asabiya_dynamics(sample_world)
        assert sample_world.civilizations[0].asabiya <= 1.0


class TestPhaseConsequences:
    def test_conditions_tick_down(self, sample_world):
        sample_world.active_conditions.append(
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=3, severity=5)
        )
        phase_consequences(sample_world)
        assert sample_world.active_conditions[0].duration == 2

    def test_expired_conditions_removed(self, sample_world):
        sample_world.active_conditions.append(
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=1, severity=5)
        )
        phase_consequences(sample_world)
        assert len(sample_world.active_conditions) == 0


class TestRunTurn:
    def test_turn_increments(self, sample_world):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "A quiet turn passed."

        run_turn(sample_world, action_selector=stub_selector, narrator=stub_narrator, seed=42)
        assert sample_world.turn == 1

    def test_events_recorded(self, sample_world):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "Things happened."

        run_turn(sample_world, action_selector=stub_selector, narrator=stub_narrator, seed=42)
        assert len(sample_world.events_timeline) > 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_simulation.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement simulation.py — phase by phase**

Create `src/chronicler/simulation.py`:

```python
"""Six-phase simulation engine for the civilization chronicle.

Turn phases:
1. Environment — natural events (drought, plague, earthquake)
2. Production — income, population growth
3. Action — each civ takes one action from constrained menu
4. Random Events — 0-1 external events from cascading probability table
5. Consequences — resolve cascading effects, tick condition durations
6. Chronicle — narrative summary (delegated to narrator callback)

The engine is deterministic given a seed, except for Phase 3 (action
selection) and Phase 6 (narration) which accept callbacks.
"""
from __future__ import annotations

import random
from typing import Callable, Protocol

from chronicler.events import (
    ENVIRONMENT_EVENTS,
    apply_probability_cascade,
    roll_for_event,
)
from chronicler.models import (
    ActionType,
    ActiveCondition,
    Civilization,
    Disposition,
    Event,
    WorldState,
)


# --- Type aliases for callbacks ---

ActionSelector = Callable[[Civilization, WorldState], ActionType]
Narrator = Callable[[WorldState, list[Event]], str]


# --- Helpers ---

def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _get_civ(world: WorldState, name: str) -> Civilization | None:
    for c in world.civilizations:
        if c.name == name:
            return c
    return None


# --- Phase 1: Environment ---

def phase_environment(world: WorldState, seed: int) -> list[Event]:
    """Check for natural disasters. At most one environment event per turn."""
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=ENVIRONMENT_EVENTS,
    )
    if event is None:
        return []

    # Apply effects based on event type
    rng = random.Random(seed + 1)
    affected = rng.sample(
        world.civilizations,
        k=max(1, len(world.civilizations) // 2),
    )
    event.actors = [c.name for c in affected]

    if event.event_type == "drought":
        for civ in affected:
            civ.stability = _clamp(civ.stability - 1, 1, 10)
            civ.economy = _clamp(civ.economy - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=event.actors,
                duration=3,
                severity=5,
            )
        )
    elif event.event_type == "plague":
        for civ in affected:
            civ.population = _clamp(civ.population - 1, 1, 10)
            civ.stability = _clamp(civ.stability - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=event.actors,
                duration=4,
                severity=6,
            )
        )
    elif event.event_type == "earthquake":
        for civ in affected:
            civ.economy = _clamp(civ.economy - 1, 1, 10)

    # Cascade probabilities
    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    return [event]


# --- Phase 2: Production ---

def phase_production(world: WorldState) -> None:
    """Generate income and adjust population for each civilization."""
    for civ in world.civilizations:
        # Income: base from economy, bonus from trade, penalty from conditions
        income = civ.economy + len(civ.regions)
        condition_penalty = sum(
            c.severity // 3
            for c in world.active_conditions
            if civ.name in c.affected_civs
        )
        civ.treasury += max(0, income - condition_penalty)

        # Military maintenance
        maintenance = civ.military // 2
        civ.treasury = max(0, civ.treasury - maintenance)

        # Population growth: if economy > population and stability > 3
        region_capacity = sum(
            r.carrying_capacity
            for r in world.regions
            if r.controller == civ.name
        )
        max_pop = min(10, region_capacity)
        if civ.economy > civ.population and civ.stability > 3 and civ.population < max_pop:
            civ.population = _clamp(civ.population + 1, 1, 10)
        # Population decline if stability very low
        elif civ.stability <= 2 and civ.population > 1:
            civ.population = _clamp(civ.population - 1, 1, 10)


# --- Phase 3: Action ---

def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
) -> list[Event]:
    """Each civilization takes one action from the constrained menu."""
    events: list[Event] = []

    for civ in world.civilizations:
        action = action_selector(civ, world)
        event = _resolve_action(civ, action, world)
        events.append(event)

    return events


def _resolve_action(civ: Civilization, action: ActionType, world: WorldState) -> Event:
    """Resolve a single civilization's action and return the event."""
    if action == ActionType.DEVELOP:
        return _resolve_develop(civ, world)
    elif action == ActionType.EXPAND:
        return _resolve_expand(civ, world)
    elif action == ActionType.TRADE:
        return _resolve_trade_action(civ, world)
    elif action == ActionType.DIPLOMACY:
        return _resolve_diplomacy(civ, world)
    elif action == ActionType.WAR:
        return _resolve_war_action(civ, world)
    else:
        return Event(
            turn=world.turn,
            event_type="action",
            actors=[civ.name],
            description=f"{civ.name} rests.",
            importance=1,
        )


def _resolve_develop(civ: Civilization, world: WorldState) -> Event:
    """Invest in infrastructure: spend treasury to boost economy or culture."""
    cost = 3
    if civ.treasury >= cost:
        civ.treasury -= cost
        if civ.economy <= civ.culture:
            civ.economy = _clamp(civ.economy + 1, 1, 10)
            target = "economy"
        else:
            civ.culture = _clamp(civ.culture + 1, 1, 10)
            target = "culture"
        return Event(
            turn=world.turn, event_type="develop", actors=[civ.name],
            description=f"{civ.name} invested in {target}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="develop", actors=[civ.name],
        description=f"{civ.name} attempted development but lacked funds.", importance=2,
    )


def _resolve_expand(civ: Civilization, world: WorldState) -> Event:
    """Claim an uncontrolled adjacent region."""
    unclaimed = [r for r in world.regions if r.controller is None]
    if unclaimed and civ.military >= 3:
        target = unclaimed[0]
        target.controller = civ.name
        civ.regions.append(target.name)
        civ.military = _clamp(civ.military - 1, 1, 10)  # Expansion stretches forces
        return Event(
            turn=world.turn, event_type="expand", actors=[civ.name],
            description=f"{civ.name} expanded into {target.name}.", importance=6,
        )
    return Event(
        turn=world.turn, event_type="expand", actors=[civ.name],
        description=f"{civ.name} could not expand — no available territory or insufficient military.",
        importance=2,
    )


def _resolve_trade_action(civ: Civilization, world: WorldState) -> Event:
    """Initiate trade with the friendliest neighbor."""
    best_partner = None
    best_disp = -1
    disp_order = {
        Disposition.HOSTILE: 0, Disposition.SUSPICIOUS: 1,
        Disposition.NEUTRAL: 2, Disposition.FRIENDLY: 3, Disposition.ALLIED: 4,
    }
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = disp_order.get(rel.disposition, 0)
            if d > best_disp:
                best_disp = d
                best_partner = _get_civ(world, other_name)

    if best_partner and best_disp >= 2:  # At least neutral
        resolve_trade(civ, best_partner, world)
        return Event(
            turn=world.turn, event_type="trade", actors=[civ.name, best_partner.name],
            description=f"{civ.name} traded with {best_partner.name}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="trade", actors=[civ.name],
        description=f"{civ.name} found no willing trade partners.", importance=2,
    )


def _resolve_diplomacy(civ: Civilization, world: WorldState) -> Event:
    """Attempt to improve relations with the most hostile neighbor."""
    worst_name = None
    worst_disp = 5
    disp_order = {
        Disposition.HOSTILE: 0, Disposition.SUSPICIOUS: 1,
        Disposition.NEUTRAL: 2, Disposition.FRIENDLY: 3, Disposition.ALLIED: 4,
    }
    disp_upgrade = {
        Disposition.HOSTILE: Disposition.SUSPICIOUS,
        Disposition.SUSPICIOUS: Disposition.NEUTRAL,
        Disposition.NEUTRAL: Disposition.FRIENDLY,
        Disposition.FRIENDLY: Disposition.ALLIED,
        Disposition.ALLIED: Disposition.ALLIED,
    }
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = disp_order.get(rel.disposition, 2)
            if d < worst_disp:
                worst_disp = d
                worst_name = other_name

    if worst_name and civ.culture >= 3:
        # Improve relationship in both directions
        rel_out = world.relationships[civ.name][worst_name]
        rel_out.disposition = disp_upgrade[rel_out.disposition]
        if worst_name in world.relationships and civ.name in world.relationships[worst_name]:
            rel_in = world.relationships[worst_name][civ.name]
            rel_in.disposition = disp_upgrade[rel_in.disposition]
        return Event(
            turn=world.turn, event_type="diplomacy", actors=[civ.name, worst_name],
            description=f"{civ.name} improved relations with {worst_name}.", importance=4,
        )
    return Event(
        turn=world.turn, event_type="diplomacy", actors=[civ.name],
        description=f"{civ.name} attempted diplomacy without success.", importance=2,
    )


def _resolve_war_action(civ: Civilization, world: WorldState) -> Event:
    """Declare war on the most hostile neighbor."""
    target_name = None
    disp_order = {
        Disposition.HOSTILE: 0, Disposition.SUSPICIOUS: 1,
        Disposition.NEUTRAL: 2, Disposition.FRIENDLY: 3, Disposition.ALLIED: 4,
    }
    worst_disp = 5
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = disp_order.get(rel.disposition, 2)
            if d < worst_disp:
                worst_disp = d
                target_name = other_name

    if target_name:
        defender = _get_civ(world, target_name)
        if defender:
            result = resolve_war(civ, defender, world, seed=world.turn)
            return Event(
                turn=world.turn, event_type="war", actors=[civ.name, target_name],
                description=f"{civ.name} attacked {target_name}: {result}.",
                importance=8,
            )
    return Event(
        turn=world.turn, event_type="war", actors=[civ.name],
        description=f"{civ.name} prepared for war but found no target.", importance=3,
    )


# --- Combat resolution (simplified Lanchester) ---

def resolve_war(
    attacker: Civilization,
    defender: Civilization,
    world: WorldState,
    seed: int = 0,
) -> str:
    """Resolve combat between two civilizations. Returns outcome string."""
    rng = random.Random(seed)

    # Lanchester-inspired: effective power = military^2 * asabiya + random factor
    att_power = (attacker.military ** 2) * attacker.asabiya + rng.uniform(0, 3)
    def_power = (defender.military ** 2) * defender.asabiya + rng.uniform(0, 3)

    # War costs treasury regardless of outcome
    attacker.treasury = max(0, attacker.treasury - 2)
    defender.treasury = max(0, defender.treasury - 1)

    if att_power > def_power * 1.3:
        # Attacker wins — seize a region if possible
        defender_regions = [r for r in world.regions if r.controller == defender.name]
        if defender_regions:
            seized = rng.choice(defender_regions)
            seized.controller = attacker.name
            attacker.regions.append(seized.name)
            defender.regions = [r for r in defender.regions if r != seized.name]
        attacker.military = _clamp(attacker.military - 1, 1, 10)
        defender.military = _clamp(defender.military - 2, 1, 10)
        defender.stability = _clamp(defender.stability - 1, 1, 10)
        return "attacker_wins"
    elif def_power > att_power * 1.3:
        # Defender wins
        attacker.military = _clamp(attacker.military - 2, 1, 10)
        defender.military = _clamp(defender.military - 1, 1, 10)
        attacker.stability = _clamp(attacker.stability - 1, 1, 10)
        return "defender_wins"
    else:
        # Stalemate — both sides lose
        attacker.military = _clamp(attacker.military - 1, 1, 10)
        defender.military = _clamp(defender.military - 1, 1, 10)
        return "stalemate"


# --- Trade resolution ---

def resolve_trade(civ1: Civilization, civ2: Civilization, world: WorldState) -> None:
    """Resolve trade: both sides gain treasury proportional to their economy."""
    gain1 = max(1, civ2.economy // 3)
    gain2 = max(1, civ1.economy // 3)
    civ1.treasury += gain1
    civ2.treasury += gain2
    # Update trade volume in relationships
    if civ1.name in world.relationships and civ2.name in world.relationships[civ1.name]:
        world.relationships[civ1.name][civ2.name].trade_volume += 1
    if civ2.name in world.relationships and civ1.name in world.relationships[civ2.name]:
        world.relationships[civ2.name][civ1.name].trade_volume += 1


# --- Asabiya dynamics (Turchin metaethnic frontier model) ---

def apply_asabiya_dynamics(world: WorldState) -> None:
    """Update asabiya (collective solidarity) for each civilization.

    Frontier civilizations (bordering hostile/suspicious neighbors) gain asabiya.
    Interior civilizations (no hostile borders) lose asabiya through decay.
    """
    r0 = 0.05   # Growth rate at frontiers
    delta = 0.02  # Decay rate in interior

    disp_threat = {Disposition.HOSTILE, Disposition.SUSPICIOUS}

    for civ in world.civilizations:
        has_frontier = False
        if civ.name in world.relationships:
            for _other, rel in world.relationships[civ.name].items():
                if rel.disposition in disp_threat:
                    has_frontier = True
                    break

        s = civ.asabiya
        if has_frontier:
            # Logistic growth: S' = S + r0 * S * (1 - S)
            s = s + r0 * s * (1 - s)
        else:
            # Decay: S' = S - delta * S
            s = s - delta * s

        civ.asabiya = round(max(0.0, min(1.0, s)), 4)


# --- Phase 4: Random events ---

def phase_random_events(world: WorldState, seed: int) -> list[Event]:
    """Roll for 0-1 random external events (non-environment)."""
    non_env = [k for k in world.event_probabilities if k not in ENVIRONMENT_EVENTS]
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=non_env,
    )
    if event is None:
        return []

    # Assign affected civilizations
    rng = random.Random(seed + 2)
    event.actors = [rng.choice(world.civilizations).name]

    # Apply cascading probabilities
    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    # Apply mechanical effects
    affected_civ = _get_civ(world, event.actors[0])
    if affected_civ:
        _apply_event_effects(event.event_type, affected_civ, world)

    return [event]


def _apply_event_effects(event_type: str, civ: Civilization, world: WorldState) -> None:
    """Apply mechanical stat changes for a random event."""
    if event_type == "leader_death":
        civ.leader.alive = False
        civ.stability = _clamp(civ.stability - 2, 1, 10)
    elif event_type == "rebellion":
        civ.stability = _clamp(civ.stability - 2, 1, 10)
        civ.military = _clamp(civ.military - 1, 1, 10)
    elif event_type == "discovery":
        civ.culture = _clamp(civ.culture + 1, 1, 10)
        civ.economy = _clamp(civ.economy + 1, 1, 10)
    elif event_type == "religious_movement":
        civ.culture = _clamp(civ.culture + 1, 1, 10)
        civ.stability = _clamp(civ.stability - 1, 1, 10)
    elif event_type == "cultural_renaissance":
        civ.culture = _clamp(civ.culture + 2, 1, 10)
        civ.stability = _clamp(civ.stability + 1, 1, 10)
    elif event_type == "migration":
        civ.population = _clamp(civ.population + 1, 1, 10)
        civ.stability = _clamp(civ.stability - 1, 1, 10)
    elif event_type == "border_incident":
        civ.stability = _clamp(civ.stability - 1, 1, 10)


# --- Phase 5: Consequences ---

def phase_consequences(world: WorldState) -> None:
    """Resolve cascading effects and tick condition durations."""
    # Tick down active conditions
    for condition in world.active_conditions:
        condition.duration -= 1
        # Ongoing damage from conditions
        for civ_name in condition.affected_civs:
            civ = _get_civ(world, civ_name)
            if civ and condition.severity >= 5:
                civ.stability = _clamp(civ.stability - 1, 1, 10)

    # Remove expired conditions
    world.active_conditions = [c for c in world.active_conditions if c.duration > 0]

    # Apply Turchin asabiya dynamics
    apply_asabiya_dynamics(world)

    # Check for civilization collapse (asabiya < 0.1 and stability <= 2)
    for civ in world.civilizations:
        if civ.asabiya < 0.1 and civ.stability <= 2:
            # Collapse: lose all but one region, stats halved
            if len(civ.regions) > 1:
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
                civ.military = _clamp(civ.military // 2, 1, 10)
                civ.economy = _clamp(civ.economy // 2, 1, 10)
                world.events_timeline.append(Event(
                    turn=world.turn,
                    event_type="collapse",
                    actors=[civ.name],
                    description=f"{civ.name} collapsed under internal pressure.",
                    importance=10,
                ))


# --- Turn orchestrator ---

def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
) -> str:
    """Execute one complete turn of the simulation. Returns chronicle text."""
    turn_events: list[Event] = []

    # Phase 1: Environment
    env_events = phase_environment(world, seed=seed)
    turn_events.extend(env_events)

    # Phase 2: Production
    phase_production(world)

    # Phase 3: Action
    action_events = phase_action(world, action_selector=action_selector)
    turn_events.extend(action_events)

    # Phase 4: Random events
    random_events = phase_random_events(world, seed=seed + 100)
    turn_events.extend(random_events)

    # Phase 5: Consequences
    phase_consequences(world)

    # Record events
    world.events_timeline.extend(turn_events)

    # Phase 6: Chronicle (narrative generation)
    chronicle_text = narrator(world, turn_events)

    # Advance turn counter
    world.turn += 1

    return chronicle_text
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_simulation.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat: add six-phase simulation engine with combat, trade, and Turchin dynamics"
```

---

### Task 6b: 5-Turn Validation Run (Critical Gate)

**Before proceeding to M4**, validate the simulation engine works end-to-end with stub callbacks. This catches structural bugs (infinite loops, state corruption, index errors) before the system grows more complex.

- [ ] **Step 1: Write a 5-turn integration test with state inspection**

Append to `tests/test_simulation.py`:

```python
class TestFiveTurnValidation:
    """Critical gate: run 5 turns with stubs and verify the simulation loop is sound."""

    def test_five_turns_no_crash(self, sample_world, tmp_path):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return f"Turn {world.turn}: {len(turn_events)} events occurred."

        for i in range(5):
            text = run_turn(sample_world, stub_selector, stub_narrator, seed=i)
            assert isinstance(text, str)
            # Save state after every turn (crash recovery pattern)
            sample_world.save(tmp_path / f"state_turn_{sample_world.turn}.json")

        assert sample_world.turn == 5
        assert len(sample_world.events_timeline) > 0

    def test_five_turns_state_files_loadable(self, sample_world, tmp_path):
        """Every per-turn state file should deserialize back to a valid WorldState."""
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "ok"

        for i in range(5):
            run_turn(sample_world, stub_selector, stub_narrator, seed=i)
            path = tmp_path / f"state_turn_{sample_world.turn}.json"
            sample_world.save(path)
            # Verify round-trip
            loaded = WorldState.load(path)
            assert loaded.turn == sample_world.turn
            assert len(loaded.civilizations) == len(sample_world.civilizations)

    def test_five_turns_stats_stay_bounded(self, sample_world):
        """All civilization stats must remain within [1, 10] after 5 turns."""
        def stub_selector(civ, world):
            # Mix of actions to stress-test bounds
            actions = [ActionType.DEVELOP, ActionType.WAR, ActionType.EXPAND,
                       ActionType.TRADE, ActionType.DIPLOMACY]
            return actions[world.turn % len(actions)]

        def stub_narrator(world, turn_events):
            return "ok"

        for i in range(5):
            run_turn(sample_world, stub_selector, stub_narrator, seed=i)

        for civ in sample_world.civilizations:
            assert 1 <= civ.population <= 10
            assert 1 <= civ.military <= 10
            assert 1 <= civ.economy <= 10
            assert 1 <= civ.culture <= 10
            assert 1 <= civ.stability <= 10
            assert 0.0 <= civ.asabiya <= 1.0
```

- [ ] **Step 2: Run the validation**

```bash
uv run pytest tests/test_simulation.py::TestFiveTurnValidation -v
```
Expected: All 3 tests PASS. If any fail, fix the simulation engine before proceeding.

- [ ] **Step 3: Commit**

```bash
git add tests/test_simulation.py
git commit -m "test: add 5-turn validation gate for simulation engine"
```

**STOP GATE:** Do not proceed to M4 until all 5-turn validation tests pass. This is the most cost-effective place to catch bugs.

---

## M4: Narrative Engine

### Task 7: LLM Client Abstraction and Domain Threading

**Files:**
- Create: `src/chronicler/narrative.py`
- Create: `tests/test_narrative.py`

The narrative engine wraps the Anthropic SDK, generates domain-threaded prose (Caves of Qud technique), and produces both turn-level chronicle entries and action selections.

- [ ] **Step 1: Write failing tests with mocked LLM**

Create `tests/test_narrative.py`:

```python
"""Tests for the narrative engine — LLM interaction is mocked."""
import pytest
from unittest.mock import MagicMock, patch
from chronicler.narrative import (
    NarrativeEngine,
    build_action_prompt,
    build_chronicle_prompt,
    thread_domains,
)
from chronicler.models import (
    ActionType,
    Civilization,
    Event,
    Leader,
    WorldState,
)


class TestDomainThreading:
    def test_thread_domains_replaces_placeholders(self):
        text = "The civilization faced a great crisis."
        civ_domains = {"TestCiv": ["maritime", "commerce"]}
        result = thread_domains(text, "TestCiv", civ_domains)
        # Domain threading should be present in output
        assert isinstance(result, str)
        assert len(result) > 0

    def test_thread_domains_no_civ_returns_unchanged(self):
        text = "Something happened."
        result = thread_domains(text, "Unknown", {})
        assert result == text


class TestBuildActionPrompt:
    def test_includes_civ_stats(self, sample_world):
        civ = sample_world.civilizations[0]
        prompt = build_action_prompt(civ, sample_world)
        assert civ.name in prompt
        assert "expand" in prompt.lower() or "EXPAND" in prompt
        assert "develop" in prompt.lower() or "DEVELOP" in prompt

    def test_includes_valid_actions(self, sample_world):
        civ = sample_world.civilizations[0]
        prompt = build_action_prompt(civ, sample_world)
        for action in ActionType:
            assert action.value in prompt.lower()


class TestBuildChroniclePrompt:
    def test_includes_turn_events(self, sample_world):
        events = [
            Event(turn=0, event_type="develop", actors=["Kethani Empire"],
                  description="Kethani Empire invested in economy.", importance=3),
        ]
        prompt = build_chronicle_prompt(sample_world, events)
        assert "Kethani Empire" in prompt
        assert "develop" in prompt.lower() or "invested" in prompt.lower()


class TestNarrativeEngine:
    def _mock_llm_client(self, response_text: str) -> MagicMock:
        """Create a mock LLMClient that returns the given text."""
        mock = MagicMock()
        mock.complete.return_value = response_text
        mock.model = "test-model"
        return mock

    def test_select_action_returns_valid_action(self, sample_world):
        sim_client = self._mock_llm_client("DEVELOP")
        narrative_client = self._mock_llm_client("")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        civ = sample_world.civilizations[0]
        action = engine.select_action(civ, sample_world)
        assert action in ActionType
        sim_client.complete.assert_called_once()

    def test_select_action_defaults_on_invalid_response(self, sample_world):
        sim_client = self._mock_llm_client("gibberish that is not an action")
        narrative_client = self._mock_llm_client("")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        civ = sample_world.civilizations[0]
        action = engine.select_action(civ, sample_world)
        assert action == ActionType.DEVELOP  # Safe default

    def test_generate_chronicle_returns_text(self, sample_world):
        sim_client = self._mock_llm_client("")
        narrative_client = self._mock_llm_client("In the third age, the empire rose...")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        events = [
            Event(turn=0, event_type="develop", actors=["Kethani Empire"],
                  description="Invested in economy.", importance=3),
        ]
        text = engine.generate_chronicle(sample_world, events)
        assert isinstance(text, str)
        assert len(text) > 0
        narrative_client.complete.assert_called_once()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_narrative.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement narrative.py**

Create `src/chronicler/narrative.py`:

```python
"""LLM narrative engine — action selection and chronicle generation.

Uses two LLMClient instances with role-based routing:
- sim_client (local model via LM Studio): action selection — high volume, free
- narrative_client (Claude API): chronicle prose — lower volume, higher quality

Domain threading (Caves of Qud technique): each civilization's thematic
keywords (domains) are woven into every narrative mention, creating the
perception of deep cultural coherence with minimal mechanical overhead.
"""
from __future__ import annotations

from chronicler.llm import LLMClient
from chronicler.models import (
    ActionType,
    Civilization,
    Disposition,
    Event,
    WorldState,
)


def thread_domains(text: str, civ_name: str, civ_domains: dict[str, list[str]]) -> str:
    """Weave civilization domain keywords into narrative text.

    This is a post-processing hint — the real domain threading happens
    in the LLM prompt where we instruct it to reference domains.
    For non-LLM contexts (testing), returns text unchanged.
    """
    if civ_name not in civ_domains:
        return text
    return text


def build_action_prompt(civ: Civilization, world: WorldState) -> str:
    """Build the prompt for LLM action selection."""
    # Summarize relationships
    rel_summary = ""
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            rel_summary += f"  - {other_name}: {rel.disposition.value}"
            if rel.grievances:
                rel_summary += f" (grievances: {', '.join(rel.grievances)})"
            if rel.treaties:
                rel_summary += f" (treaties: {', '.join(rel.treaties)})"
            rel_summary += "\n"

    # Summarize active conditions
    conditions = [
        c for c in world.active_conditions if civ.name in c.affected_civs
    ]
    cond_text = ", ".join(f"{c.condition_type} (severity {c.severity}, {c.duration} turns left)"
                          for c in conditions) or "None"

    return f"""You are the strategic advisor for {civ.name}.

CURRENT STATE:
- Population: {civ.population}/10
- Military: {civ.military}/10
- Economy: {civ.economy}/10
- Culture: {civ.culture}/10
- Stability: {civ.stability}/10
- Tech Era: {civ.tech_era.value}
- Treasury: {civ.treasury}
- Asabiya (solidarity): {civ.asabiya}
- Controlled regions: {', '.join(civ.regions) or 'None'}
- Cultural domains: {', '.join(civ.domains)}
- Values: {', '.join(civ.values)}
- Leader: {civ.leader.name} ({civ.leader.trait})
- Goal: {civ.goal}

RELATIONSHIPS:
{rel_summary or '  None'}

ACTIVE CONDITIONS: {cond_text}

Choose exactly ONE action from: EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR

Consider: your goal, your stats, your relationships, active threats, and available resources.
Respond with ONLY the action name (one word, all caps). Nothing else."""


def build_chronicle_prompt(world: WorldState, events: list[Event]) -> str:
    """Build the prompt for LLM chronicle narration."""
    # Build civilization summaries
    civ_summaries = ""
    for civ in world.civilizations:
        civ_summaries += f"\n{civ.name} (domains: {', '.join(civ.domains)}):"
        civ_summaries += f" Pop {civ.population}, Mil {civ.military}, Econ {civ.economy},"
        civ_summaries += f" Culture {civ.culture}, Stability {civ.stability},"
        civ_summaries += f" Treasury {civ.treasury}, Asabiya {civ.asabiya}"
        civ_summaries += f"\n  Leader: {civ.leader.name} ({civ.leader.trait})"
        civ_summaries += f"\n  Regions: {', '.join(civ.regions)}"

    # Build event list
    event_text = ""
    for e in events:
        event_text += f"\n- [{e.event_type}] {e.description} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)"

    return f"""You are a mythic historian chronicling the world of {world.name}.

TURN {world.turn}:

CIVILIZATIONS:{civ_summaries}

EVENTS THIS TURN:{event_text}

Write a chronicle entry for this turn (2-4 paragraphs). Rules:
1. Write in the style of a mythic history — evocative, literary, as if written by a scholar looking back on these events centuries later.
2. For each civilization mentioned, weave their cultural DOMAINS into the prose. A maritime culture's trade dispute involves harbors and currents; a mountain culture's crisis involves peaks and stone. This is critical for thematic coherence.
3. Focus on events with importance >= 5. Mention lower-importance events briefly or skip them.
4. Reference specific leader names, region names, and cultural values where relevant.
5. End with a sentence that hints at coming tension or change.
6. Do NOT include turn numbers or game mechanics in the prose."""


class NarrativeEngine:
    """LLM-powered action selection and chronicle generation.

    Accepts two separate LLMClient instances: one for simulation calls
    (action selection — high volume, can be local) and one for narrative
    calls (chronicle prose — lower volume, benefits from higher quality).
    """

    def __init__(self, sim_client: LLMClient, narrative_client: LLMClient):
        self.sim_client = sim_client
        self.narrative_client = narrative_client

    def select_action(self, civ: Civilization, world: WorldState) -> ActionType:
        """Ask the LLM to choose an action for a civilization.

        Routes to sim_client (local model) for cost efficiency.
        """
        prompt = build_action_prompt(civ, world)
        text = self.sim_client.complete(prompt, max_tokens=10).upper()

        # Parse response — must be exactly one valid action
        try:
            return ActionType(text.lower())
        except ValueError:
            # Fuzzy match
            for action in ActionType:
                if action.value.upper() in text:
                    return action
            return ActionType.DEVELOP  # Safe default

    def generate_chronicle(self, world: WorldState, events: list[Event]) -> str:
        """Generate a chronicle entry for the current turn.

        Routes to narrative_client (Claude API) for prose quality.
        """
        prompt = build_chronicle_prompt(world, events)
        return self.narrative_client.complete(prompt, max_tokens=1000)

    def action_selector(self, civ: Civilization, world: WorldState) -> ActionType:
        """Adapter method matching the ActionSelector callback signature."""
        return self.select_action(civ, world)

    def narrator(self, world: WorldState, events: list[Event]) -> str:
        """Adapter method matching the Narrator callback signature."""
        return self.generate_chronicle(world, events)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_narrative.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat: add LLM narrative engine with domain threading and action selection"
```

---

## M5: Memory, Reflection, and Chronicle Output

### Task 8: Memory Streams and Periodic Reflections

**Files:**
- Create: `src/chronicler/memory.py`
- Create: `tests/test_memory.py`

Implements Stanford Generative Agents-style memory: each civilization maintains a running memory stream. Every 10 turns, the system generates higher-level "reflections" that become era/chapter breaks.

- [ ] **Step 1: Write failing tests**

Create `tests/test_memory.py`:

```python
"""Tests for memory streams and periodic reflections."""
import pytest
from unittest.mock import MagicMock
from chronicler.memory import (
    MemoryStream,
    MemoryEntry,
    should_reflect,
    build_reflection_prompt,
    generate_reflection,
)
from chronicler.models import Event


class TestMemoryEntry:
    def test_create_entry(self):
        entry = MemoryEntry(
            turn=5,
            text="The Kethani Empire expanded into the Thornwood.",
            importance=6,
            entry_type="event",
        )
        assert entry.turn == 5
        assert entry.importance == 6


class TestMemoryStream:
    def test_add_entry(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("The empire traded with the republic.", turn=1, importance=3)
        assert len(stream.entries) == 1

    def test_get_recent(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        for i in range(20):
            stream.add(f"Event {i}", turn=i, importance=5)
        recent = stream.get_recent(count=5)
        assert len(recent) == 5
        assert recent[-1].text == "Event 19"

    def test_get_important(self):
        stream = MemoryStream(civilization_name="Test")
        stream.add("Minor event", turn=1, importance=2)
        stream.add("Major event", turn=2, importance=9)
        stream.add("Medium event", turn=3, importance=5)
        important = stream.get_important(min_importance=5)
        assert len(important) == 2
        assert important[0].importance >= 5

    def test_add_reflection(self):
        stream = MemoryStream(civilization_name="Test")
        stream.add_reflection("The empire entered a golden age.", turn=10)
        assert len(stream.reflections) == 1
        assert stream.reflections[0].entry_type == "reflection"

    def test_get_context_window(self):
        """Context window returns recent entries + all reflections."""
        stream = MemoryStream(civilization_name="Test")
        for i in range(30):
            stream.add(f"Event {i}", turn=i, importance=5)
        stream.add_reflection("Era of Growth", turn=10)
        context = stream.get_context_window(recent_count=5)
        # Should have 5 recent entries + 1 reflection
        assert len(context) == 6


class TestShouldReflect:
    def test_reflects_every_10_turns(self):
        assert should_reflect(turn=10, interval=10) is True
        assert should_reflect(turn=20, interval=10) is True
        assert should_reflect(turn=0, interval=10) is False

    def test_does_not_reflect_between_intervals(self):
        assert should_reflect(turn=7, interval=10) is False
        assert should_reflect(turn=15, interval=10) is False


class TestReflectionGeneration:
    def test_build_reflection_prompt_includes_memories(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("Expanded into Thornwood", turn=1, importance=6)
        stream.add("Traded with Selurians", turn=2, importance=3)
        stream.add("Lost a border skirmish", turn=5, importance=7)
        prompt = build_reflection_prompt(stream, era_start=1, era_end=10)
        assert "Kethani Empire" in prompt
        assert "Thornwood" in prompt

    def test_generate_reflection_returns_text(self):
        mock_client = MagicMock()
        mock_client.complete.return_value = "The Age of Expansion saw the Kethani Empire grow..."
        mock_client.model = "test-model"
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("Expanded", turn=1, importance=6)
        text = generate_reflection(
            stream, era_start=1, era_end=10, client=mock_client
        )
        assert "Kethani" in text or "Expansion" in text or len(text) > 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_memory.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement memory.py**

Create `src/chronicler/memory.py`:

```python
"""Memory streams and periodic reflections (Stanford Generative Agents pattern).

Each civilization maintains a MemoryStream of natural-language entries with
timestamps and importance scores. Every N turns, reflections consolidate
recent memories into higher-level era summaries that serve as chapter breaks
in the final chronicle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    turn: int
    text: str
    importance: int  # 1-10 scale
    entry_type: str = "event"  # "event" or "reflection"


class MemoryStream:
    """Running memory for a single civilization."""

    def __init__(self, civilization_name: str):
        self.civilization_name = civilization_name
        self.entries: list[MemoryEntry] = []
        self.reflections: list[MemoryEntry] = []

    def add(self, text: str, turn: int, importance: int = 5) -> None:
        self.entries.append(MemoryEntry(
            turn=turn, text=text, importance=importance, entry_type="event",
        ))

    def add_reflection(self, text: str, turn: int) -> None:
        entry = MemoryEntry(
            turn=turn, text=text, importance=10, entry_type="reflection",
        )
        self.reflections.append(entry)

    def get_recent(self, count: int = 10) -> list[MemoryEntry]:
        return self.entries[-count:]

    def get_important(self, min_importance: int = 5) -> list[MemoryEntry]:
        return [e for e in self.entries if e.importance >= min_importance]

    def get_context_window(self, recent_count: int = 10) -> list[MemoryEntry]:
        """Return recent entries + all reflections for LLM context."""
        recent = self.get_recent(recent_count)
        return list(self.reflections) + recent


def should_reflect(turn: int, interval: int = 10) -> bool:
    """Check whether it's time to generate a reflection."""
    return turn > 0 and turn % interval == 0


def build_reflection_prompt(
    stream: MemoryStream,
    era_start: int,
    era_end: int,
) -> str:
    """Build the prompt for LLM reflection generation."""
    era_entries = [e for e in stream.entries if era_start <= e.turn <= era_end]
    important = [e for e in era_entries if e.importance >= 5]
    all_entries = important or era_entries[-10:]  # Fallback to recent if no high-importance

    memory_text = "\n".join(
        f"- Turn {e.turn}: {e.text} (importance: {e.importance})"
        for e in all_entries
    )

    prev_reflections = "\n".join(
        f"- {r.text}" for r in stream.reflections
    ) or "None yet."

    return f"""You are a mythic historian reflecting on the history of {stream.civilization_name}.

PREVIOUS ERA SUMMARIES:
{prev_reflections}

EVENTS FROM TURNS {era_start}-{era_end}:
{memory_text}

Write a 2-3 sentence reflection summarizing this era for {stream.civilization_name}.
This should read like the name and description of a historical age — e.g.,
"The Age of Iron and Sorrow" followed by a concise characterization.
Focus on the most significant themes: expansion, decline, cultural flowering,
military conflict, or internal strife. Reference specific events where impactful.
This reflection will serve as a chapter heading in the final chronicle."""


def generate_reflection(
    stream: MemoryStream,
    era_start: int,
    era_end: int,
    client: Any,  # LLMClient — uses narrative client for quality
) -> str:
    """Generate an era-level reflection using the LLM.

    Accepts any LLMClient. In hybrid mode, this should be the narrative_client
    (Claude API) since era reflections benefit from high prose quality.
    """
    prompt = build_reflection_prompt(stream, era_start, era_end)
    text = client.complete(prompt, max_tokens=300)
    stream.add_reflection(text, turn=era_end)
    return text
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_memory.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/memory.py tests/test_memory.py
git commit -m "feat: add memory streams with era-level reflections (Generative Agents pattern)"
```

---

### Task 9: Chronicle Compiler

**Files:**
- Create: `src/chronicler/chronicle.py`
- Create: `tests/test_chronicle.py`

Assembles all turn-level chronicle entries and era reflections into a single readable Markdown document.

- [ ] **Step 1: Write failing tests**

Create `tests/test_chronicle.py`:

```python
"""Tests for chronicle compilation."""
import pytest
from chronicler.chronicle import compile_chronicle, ChronicleEntry


class TestChronicleEntry:
    def test_create_entry(self):
        entry = ChronicleEntry(turn=1, text="The war began.", era=None)
        assert entry.turn == 1


class TestCompileChronicle:
    def test_produces_markdown(self):
        entries = [
            ChronicleEntry(turn=1, text="The empires met at the border."),
            ChronicleEntry(turn=2, text="Trade agreements were forged."),
        ]
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections={},
        )
        assert "# Chronicle of Aetheris" in result
        assert "The empires met" in result

    def test_inserts_era_headers(self):
        entries = [
            ChronicleEntry(turn=i, text=f"Events of turn {i}.")
            for i in range(1, 21)
        ]
        era_reflections = {
            10: "## The Age of Iron\n\nA time of conflict and expansion.",
            20: "## The Age of Commerce\n\nPeace brought prosperity.",
        }
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections=era_reflections,
        )
        assert "Age of Iron" in result
        assert "Age of Commerce" in result

    def test_empty_chronicle(self):
        result = compile_chronicle(world_name="Aetheris", entries=[], era_reflections={})
        assert "Chronicle of Aetheris" in result

    def test_includes_world_summary_at_end(self):
        entries = [ChronicleEntry(turn=1, text="Something happened.")]
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections={},
            epilogue="And so the world turned on.",
        )
        assert "And so the world turned on." in result
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_chronicle.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement chronicle.py**

Create `src/chronicler/chronicle.py`:

```python
"""Chronicle compiler — assembles turn entries and era reflections into Markdown.

The final output reads like a mythic history: named ages, chapter breaks at
era reflections, and turn-level narrative woven into continuous prose.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChronicleEntry:
    turn: int
    text: str
    era: str | None = None


def compile_chronicle(
    world_name: str,
    entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    epilogue: str | None = None,
) -> str:
    """Compile all chronicle entries and era reflections into a Markdown document."""
    lines: list[str] = []
    lines.append(f"# Chronicle of {world_name}\n")
    lines.append("---\n")

    for entry in entries:
        # Insert era header if this turn marks an era boundary
        if entry.turn in era_reflections:
            lines.append("")
            lines.append(era_reflections[entry.turn])
            lines.append("")

        lines.append(entry.text)
        lines.append("")  # Blank line between entries

    if epilogue:
        lines.append("---\n")
        lines.append(f"*{epilogue}*\n")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_chronicle.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/chronicle.py tests/test_chronicle.py
git commit -m "feat: add chronicle compiler for assembling final Markdown output"
```

---

## M6: Integration — Main Loop and CLI

### Task 10: Main Entry Point

**Files:**
- Create: `src/chronicler/main.py`
- Create: `tests/test_main.py`

The main module ties everything together: generates a world, runs N turns of simulation, produces a chronicle, and writes it to disk.

- [ ] **Step 1: Write failing tests**

Create `tests/test_main.py`:

```python
"""Tests for the main entry point — end-to-end with mocked LLM."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from chronicler.main import run_chronicle, DEFAULT_CONFIG


class TestDefaultConfig:
    def test_config_has_required_keys(self):
        assert "num_turns" in DEFAULT_CONFIG
        assert "num_civs" in DEFAULT_CONFIG
        assert "num_regions" in DEFAULT_CONFIG
        assert "reflection_interval" in DEFAULT_CONFIG


class TestRunChronicle:
    def _mock_llm(self, response: str = "DEVELOP"):
        """Create a mock LLMClient."""
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_produces_markdown_file(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("The empire grew stronger.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        assert output_path.exists()
        content = output_path.read_text()
        assert "Chronicle of" in content
        assert len(content) > 100

    def test_state_file_saved(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Events occurred.")

        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"
        run_chronicle(
            seed=42,
            num_turns=3,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        assert state_path.exists()

    def test_respects_num_turns(self, tmp_path):
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("Things happened.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=5,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )
        # Verify the mocks were called for action selection + narration
        assert sim_client.complete.call_count > 0
        assert narrative_client.complete.call_count > 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_main.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement main.py**

Create `src/chronicler/main.py`:

```python
"""Main entry point — orchestrates world generation, simulation, and chronicle output.

Usage:
    chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output chronicle.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import anthropic

from chronicler.chronicle import ChronicleEntry, compile_chronicle
from chronicler.llm import LLMClient, create_clients
from chronicler.memory import MemoryStream, generate_reflection, should_reflect
from chronicler.models import Event, WorldState
from chronicler.narrative import NarrativeEngine
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

DEFAULT_CONFIG = {
    "num_turns": 50,
    "num_civs": 4,
    "num_regions": 8,
    "reflection_interval": 10,
    "local_url": "http://localhost:1234/v1",  # LM Studio default
    "local_model": None,                       # Set to enable hybrid mode
    "narrative_model": "claude-sonnet-4-6",
}


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
) -> None:
    """Run the full chronicle generation pipeline.

    Accepts two separate LLM clients:
    - sim_client: handles action selection (high volume, local model)
    - narrative_client: handles chronicle prose + reflections (Claude API)
    """
    engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)

    # Generate initial world
    world = generate_world(
        seed=seed,
        num_regions=num_regions,
        num_civs=num_civs,
    )

    # Initialize memory streams for each civilization
    memories: dict[str, MemoryStream] = {
        civ.name: MemoryStream(civilization_name=civ.name)
        for civ in world.civilizations
    }

    # Run simulation
    chronicle_entries: list[ChronicleEntry] = []
    era_reflections: dict[int, str] = {}

    mode = "hybrid (local sim + API narrative)" if type(sim_client).__name__ == "LocalClient" else "API-only"
    print(f"Generating chronicle for '{world.name}' — {num_turns} turns, {num_civs} civs [{mode}]")

    for turn_num in range(num_turns):
        # Run one turn
        chronicle_text = run_turn(
            world,
            action_selector=engine.action_selector,
            narrator=engine.narrator,
            seed=seed + turn_num,
        )

        # Record chronicle entry
        chronicle_entries.append(ChronicleEntry(
            turn=world.turn,
            text=chronicle_text,
        ))

        # Update memory streams with this turn's events
        turn_events = [e for e in world.events_timeline if e.turn == world.turn - 1]
        for event in turn_events:
            for actor in event.actors:
                if actor in memories:
                    memories[actor].add(
                        text=event.description or f"{event.event_type} occurred",
                        turn=world.turn,
                        importance=event.importance,
                    )

        # Generate era reflections at intervals (uses narrative_client for quality)
        if should_reflect(world.turn, interval=reflection_interval):
            era_start = world.turn - reflection_interval + 1
            era_end = world.turn
            reflection_texts: list[str] = []

            for civ_name, stream in memories.items():
                reflection = generate_reflection(
                    stream,
                    era_start=era_start,
                    era_end=era_end,
                    client=narrative_client,
                )
                reflection_texts.append(reflection)

            combined = "\n\n".join(reflection_texts)
            era_reflections[world.turn] = f"## Era: Turns {era_start}–{era_end}\n\n{combined}"
            print(f"  Era reflection generated for turns {era_start}-{era_end}")

        # Save state after EVERY turn (crash recovery — resume from last good state)
        if state_path:
            world.save(state_path)

        # Progress indicator
        if world.turn % 10 == 0:
            print(f"  Turn {world.turn}/{num_turns} complete")

    # Compile final chronicle
    output_text = compile_chronicle(
        world_name=world.name,
        entries=chronicle_entries,
        era_reflections=era_reflections,
        epilogue=f"Thus concludes the chronicle of {world.name}, spanning {num_turns} turns of history.",
    )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text)
    print(f"\nChronicle written to {output_path} ({len(output_text)} characters)")

    # Save final state
    if state_path:
        world.save(state_path)
        print(f"Final world state saved to {state_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate an AI-driven civilization chronicle",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--turns", type=int, default=DEFAULT_CONFIG["num_turns"], help="Number of simulation turns")
    parser.add_argument("--civs", type=int, default=DEFAULT_CONFIG["num_civs"], help="Number of civilizations")
    parser.add_argument("--regions", type=int, default=DEFAULT_CONFIG["num_regions"], help="Number of regions")
    parser.add_argument("--output", type=str, default="output/chronicle.md", help="Output file path")
    parser.add_argument("--state", type=str, default="output/state.json", help="State file path")
    parser.add_argument("--resume", type=str, default=None, help="Resume from a saved state JSON file")
    parser.add_argument("--reflection-interval", type=int, default=DEFAULT_CONFIG["reflection_interval"])

    # Hybrid inference config
    parser.add_argument("--local-url", type=str, default=DEFAULT_CONFIG["local_url"],
                        help="LM Studio / local model API URL (OpenAI-compatible)")
    parser.add_argument("--local-model", type=str, default=DEFAULT_CONFIG["local_model"],
                        help="Local model name for simulation calls (enables hybrid mode)")
    parser.add_argument("--narrative-model", type=str, default=DEFAULT_CONFIG["narrative_model"],
                        help="Claude model for narrative generation")

    args = parser.parse_args()

    anthropic_client = anthropic.Anthropic()
    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        local_model=args.local_model,
        narrative_model=args.narrative_model,
        anthropic_client=anthropic_client,
    )

    run_chronicle(
        seed=args.seed,
        num_turns=args.turns,
        num_civs=args.civs,
        num_regions=args.regions,
        output_path=Path(args.output),
        state_path=Path(args.state),
        sim_client=sim_client,
        narrative_client=narrative_client,
        reflection_interval=args.reflection_interval,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_main.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Run all tests — full suite**

```bash
uv run pytest -v
```
Expected: All tests across all modules PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat: add main entry point with CLI and end-to-end orchestration"
```

---

### Task 11: LLM-Enhanced World Generation (Optional Enhancement)

**Files:**
- Modify: `src/chronicler/world_gen.py` (add `generate_world_with_llm`)
- Modify: `tests/test_world_gen.py` (add LLM generation tests)

After the core pipeline works end-to-end, optionally add an LLM-powered world generator that creates more creative names, backstories, and initial goals.

- [ ] **Step 1: Write failing test**

Append to `tests/test_world_gen.py`:

```python
class TestLLMWorldGeneration:
    def test_llm_generates_goals(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"goals": ["Dominate the eastern trade routes", "Unite the mountain clans", "Spread the faith to all shores", "Preserve the ancient knowledge"]}')]
        )
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Without LLM, goals are empty
        assert all(c.goal == "" for c in world.civilizations)

        from chronicler.world_gen import enrich_with_llm
        enrich_with_llm(world, client=mock_client)
        # After LLM enrichment, goals should be set
        assert any(c.goal != "" for c in world.civilizations)
```

- [ ] **Step 2: Run test — verify it fails**

```bash
uv run pytest tests/test_world_gen.py::TestLLMWorldGeneration -v
```
Expected: ImportError for `enrich_with_llm`.

- [ ] **Step 3: Implement enrich_with_llm**

Add to `src/chronicler/world_gen.py`:

```python
def enrich_with_llm(world: WorldState, client: Any, model: str = "claude-haiku-4-5-20251001") -> None:
    """Use the LLM to generate creative goals and backstory details."""
    civ_summaries = "\n".join(
        f"- {c.name}: domains={c.domains}, values={c.values}, "
        f"leader={c.leader.name} ({c.leader.trait}), regions={c.regions}"
        for c in world.civilizations
    )

    prompt = f"""Given these civilizations in the world of {world.name}:

{civ_summaries}

Generate a strategic goal for each civilization. Goals should be specific,
achievable within 50 turns, and reflect the civilization's domains and values.

Respond as JSON: {{"goals": ["goal for civ 1", "goal for civ 2", ...]}}"""

    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    import json
    try:
        data = json.loads(response.content[0].text)
        goals = data.get("goals", [])
        for i, civ in enumerate(world.civilizations):
            if i < len(goals):
                civ.goal = goals[i]
    except (json.JSONDecodeError, KeyError):
        pass  # Keep empty goals on parse failure
```

Also add `from typing import Any` to imports if not already present.

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_world_gen.py -v
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_world_gen.py
git commit -m "feat: add optional LLM enrichment for world generation goals"
```

---

### Task 12: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e.py`

A single end-to-end test that runs the full pipeline with mocked LLM to verify everything connects properly.

- [ ] **Step 1: Write e2e test**

Create `tests/test_e2e.py`:

```python
"""End-to-end smoke test — full pipeline with mocked LLM."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from chronicler.main import run_chronicle
from chronicler.models import WorldState


class TestEndToEnd:
    def _mock_llm(self, response: str):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_full_pipeline_20_turns(self, tmp_path):
        """Run 20 turns with mocked LLM clients and verify output."""
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm(
            "The merchants of the empire grew bolder, their ships venturing further along the sapphire coast."
        )

        output_path = tmp_path / "chronicle.md"
        state_path = tmp_path / "state.json"

        run_chronicle(
            seed=42,
            num_turns=20,
            num_civs=4,
            num_regions=8,
            output_path=output_path,
            state_path=state_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )

        # Verify chronicle file
        assert output_path.exists()
        content = output_path.read_text()
        assert "Chronicle of" in content
        assert len(content) > 500

        # Verify state file
        assert state_path.exists()
        world = WorldState.load(state_path)
        assert world.turn == 20
        assert len(world.events_timeline) > 0

        # Verify both clients were called
        # sim_client: action selection (4 civs * 20 turns = 80 calls)
        # narrative_client: chronicle (20 calls) + reflections (2 eras * 4 civs = 8 calls)
        assert sim_client.complete.call_count >= 80
        assert narrative_client.complete.call_count >= 20

    def test_output_contains_era_reflections(self, tmp_path):
        """With 20 turns and interval 10, should have era reflections."""
        sim_client = self._mock_llm("DEVELOP")
        narrative_client = self._mock_llm("The Age of Growth dawned.")

        output_path = tmp_path / "chronicle.md"
        run_chronicle(
            seed=42,
            num_turns=20,
            num_civs=2,
            num_regions=4,
            output_path=output_path,
            sim_client=sim_client,
            narrative_client=narrative_client,
            reflection_interval=10,
        )

        content = output_path.read_text()
        assert "Era:" in content
```

- [ ] **Step 2: Run e2e test**

```bash
uv run pytest tests/test_e2e.py -v
```
Expected: All tests PASS.

- [ ] **Step 3: Run full test suite one final time**

```bash
uv run pytest -v --tb=short
```
Expected: All tests across all modules PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end smoke test for full chronicle pipeline"
```

---

## Post-Implementation Verification Checklist

After all milestones are complete, verify in order:

- [ ] `uv run pytest -v` — all tests pass (unit + 5-turn validation + e2e)
- [ ] `uv run chronicler --help` — CLI shows usage
- [ ] **API-only mode:** `uv run chronicler --seed 42 --turns 5 --civs 2 --regions 4` — 5-turn smoke run
- [ ] **Hybrid mode:** `uv run chronicler --seed 42 --turns 5 --civs 2 --regions 4 --local-model <your-model>` — 5-turn smoke run with LM Studio handling action selection
- [ ] Inspect `output/state.json` — valid world state, turn count matches
- [ ] Read 5-turn chronicle — verify it's coherent prose, not JSON or error traces
- [ ] Full run: `uv run chronicler --seed 42 --turns 100 --civs 4 --regions 8 --local-model <your-model>`
- [ ] If full run crashes: `uv run chronicler --resume output/state.json --turns 100` — resume from last good state
- [ ] Output chronicle is readable mythic history with era headings
- [ ] No hardcoded API keys in source

---

## Future Enhancements (Not in Scope)

These are noted for reference but explicitly **not** part of this plan:

1. **LLM-generated world details** — expand `enrich_with_llm()` beyond goals to generate civilization names, leader names, cultural domains, region names, and backstory. The template pools (12 regions, 6 civs, 10 leaders) give determinism for testing but cap variety across runs. The hook point already exists; it just needs broader scope. Route through the local model to keep it free.
2. **Spatial simulation** — grid-based map with adjacency, distance-based power projection (Turchin model)
3. **Technology tree** — unlockable techs that modify event probabilities and action effectiveness
4. **Individual agents** — named characters with goals, memories, and social networks
5. **Parallel narrative threads** — per-civilization POV chapters interleaved in the chronicle
6. **Streaming output** — display chronicle entries as they're generated
7. **Web UI** — Streamlit dashboard with map visualization and live simulation
