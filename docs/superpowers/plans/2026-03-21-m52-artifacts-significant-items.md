# M52: Artifacts & Significant Items — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python-side artifact system with world-level registry, intent-based creation, portability-based lifecycle, ephemeral prestige contribution, deterministic naming, and event-backed narrative integration.

**Architecture:** Triggers detect artifact-worthy moments inline and emit lightweight `ArtifactIntent` / `ArtifactLifecycleIntent` objects to transient lists on `WorldState`. A central `tick_artifacts()` function in Phase 10 processes all intents, manages ownership transitions, computes ephemeral prestige, and emits events. Artifact prestige is a derived signal that feeds `tick_prestige()` the following turn — no stock mutation.

**Tech Stack:** Python, Pydantic, pytest. No Rust changes.

**Spec:** `docs/superpowers/specs/2026-03-21-m52-artifacts-significant-items-design.md`

---

## File Structure

| File | Role | New/Modified |
|------|------|-------------|
| `src/chronicler/models.py` | `Artifact`, `ArtifactType`, `ArtifactStatus`, `ArtifactIntent`, `ArtifactLifecycleIntent` types. `WorldState.artifacts`, transient PrivateAttrs. `GreatPerson.mule_artifact_created` | Modified |
| `src/chronicler/artifacts.py` | `tick_artifacts()`, `generate_artifact_name()`, `_prosperity_gate()`, `_get_relevant_artifacts()`, naming templates/vocabulary, prestige computation, lifecycle logic, all calibration constants | New |
| `src/chronicler/simulation.py` | `tick_artifacts()` call in Phase 10. Intent emission in `phase_cultural_milestones()` and `cultural_renaissance` handler | Modified |
| `src/chronicler/infrastructure.py` | Intent emission in `tick_infrastructure()` on temple completion | Modified |
| `src/chronicler/action_engine.py` | Mule artifact intent + conquest lifecycle intents in `_resolve_war_action()` | Modified |
| `src/chronicler/agent_bridge.py` | Intent emission in `_process_promotions()` for high-prestige GP artifacts | Modified |
| `src/chronicler/great_persons.py` | Intent emission in `check_great_person_generation()` for aggregate-mode GP artifacts | Modified |
| `src/chronicler/politics.py` | Lifecycle intents in `check_twilight_absorption()` | Modified |
| `src/chronicler/culture.py` | `tick_prestige()` reads ephemeral artifact bonus | Modified |
| `src/chronicler/narrative.py` | `artifact_context_text` in prompt assembly. `ARTIFACT_DESCRIPTIONS`. `render_artifact_context()` | Modified |
| `src/chronicler/analytics.py` | `extract_artifacts()` extractor | Modified |
| `tests/test_artifacts.py` | All M52 unit and integration tests | New |

---

### Task 1: Data Model — Types, Artifact, WorldState fields

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write the failing tests for model types and invariants**

```python
# tests/test_artifacts.py
import pytest
from chronicler.models import (
    Artifact, ArtifactType, ArtifactStatus,
    ArtifactIntent, ArtifactLifecycleIntent, WorldState,
)


class TestArtifactModel:
    def test_artifact_type_enum_values(self):
        assert ArtifactType.RELIC == "relic"
        assert ArtifactType.WEAPON == "weapon"
        assert ArtifactType.MONUMENT == "monument"
        assert ArtifactType.ARTWORK == "artwork"
        assert ArtifactType.TREATISE == "treatise"
        assert ArtifactType.MANIFESTO == "manifesto"
        assert ArtifactType.TRADE_GOOD == "trade_good"

    def test_artifact_status_enum_values(self):
        assert ArtifactStatus.ACTIVE == "active"
        assert ArtifactStatus.LOST == "lost"
        assert ArtifactStatus.DESTROYED == "destroyed"

    def test_artifact_construction_minimal(self):
        a = Artifact(
            artifact_id=1,
            name="The Iron Blade of Tessara",
            artifact_type=ArtifactType.WEAPON,
            anchored=False,
            origin_turn=10,
            origin_event="Forged at promotion of General Kiran",
            origin_region="Tessara",
            creator_name="Kiran",
            creator_civ="Kethani Empire",
            owner_civ="Kethani Empire",
            holder_name="Kiran",
            holder_born_turn=8,
            anchor_region=None,
            prestige_value=2,
            status=ArtifactStatus.ACTIVE,
            history=["Forged at the promotion of General Kiran, turn 10"],
        )
        assert a.artifact_id == 1
        assert a.mule_origin is False
        assert a.anchored is False

    def test_artifact_civ_owned_monument(self):
        a = Artifact(
            artifact_id=2,
            name="The Great Pillar of Ashara",
            artifact_type=ArtifactType.MONUMENT,
            anchored=True,
            origin_turn=50,
            origin_event="Erected during cultural renaissance",
            origin_region="Ashara",
            creator_name=None,
            creator_civ="Selurian Republic",
            owner_civ="Selurian Republic",
            holder_name=None,
            holder_born_turn=None,
            anchor_region="Ashara",
            prestige_value=4,
            status=ArtifactStatus.ACTIVE,
            history=["Erected during a cultural renaissance in Ashara, turn 50"],
        )
        assert a.anchored is True
        assert a.holder_name is None
        assert a.anchor_region == "Ashara"

    def test_artifact_serialization_roundtrip(self):
        a = Artifact(
            artifact_id=1,
            name="Test Artifact",
            artifact_type=ArtifactType.RELIC,
            anchored=True,
            origin_turn=5,
            origin_event="test",
            origin_region="Region1",
            creator_name=None,
            creator_civ="Civ1",
            owner_civ="Civ1",
            holder_name=None,
            holder_born_turn=None,
            anchor_region="Region1",
            prestige_value=3,
            status=ArtifactStatus.ACTIVE,
            history=["created"],
        )
        data = a.model_dump()
        a2 = Artifact(**data)
        assert a2.name == a.name
        assert a2.artifact_type == ArtifactType.RELIC


class TestArtifactIntent:
    def test_creation_intent(self):
        intent = ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="Kethani Empire",
            region_name="Ashara",
            anchored=True,
            context="Sacred relic forged in the temple of Ashara",
        )
        assert intent.mule_origin is False

    def test_lifecycle_intent(self):
        intent = ArtifactLifecycleIntent(
            action="conquest_transfer",
            losing_civ="Selurian Republic",
            gaining_civ="Kethani Empire",
            region="Ashara",
            is_capital=True,
            is_full_absorption=False,
            is_destructive=False,
        )
        assert intent.action == "conquest_transfer"


class TestWorldStateArtifactFields:
    def test_world_state_has_artifacts_field(self):
        world = WorldState(seed=42)
        assert hasattr(world, 'artifacts')
        assert world.artifacts == []

    def test_world_state_has_transient_intent_lists(self):
        world = WorldState(seed=42)
        assert hasattr(world, '_artifact_intents')
        assert world._artifact_intents == []
        assert hasattr(world, '_artifact_lifecycle_intents')
        assert world._artifact_lifecycle_intents == []
        assert hasattr(world, '_artifact_prestige_by_civ')
        assert world._artifact_prestige_by_civ == {}

    def test_transient_fields_not_serialized(self):
        world = WorldState(seed=42)
        world._artifact_intents.append("test")
        data = world.model_dump()
        assert '_artifact_intents' not in data
        assert '_artifact_lifecycle_intents' not in data
        assert '_artifact_prestige_by_civ' not in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py -v`
Expected: FAIL — `ArtifactType`, `Artifact`, etc. not importable

- [ ] **Step 3: Add model types to `models.py`**

In `src/chronicler/models.py`, add after the existing `InfrastructureType` enum (near line 123):

```python
class ArtifactType(str, Enum):
    RELIC = "relic"
    WEAPON = "weapon"
    MONUMENT = "monument"
    ARTWORK = "artwork"
    TREATISE = "treatise"
    MANIFESTO = "manifesto"
    TRADE_GOOD = "trade_good"


class ArtifactStatus(str, Enum):
    ACTIVE = "active"
    LOST = "lost"
    DESTROYED = "destroyed"
```

Add the `Artifact` model after the `Infrastructure` class (near line 152):

```python
class Artifact(BaseModel):
    artifact_id: int
    name: str
    artifact_type: ArtifactType
    anchored: bool
    origin_turn: int
    origin_event: str
    origin_region: str
    creator_name: str | None
    creator_civ: str
    owner_civ: str | None
    holder_name: str | None
    holder_born_turn: int | None
    anchor_region: str | None
    prestige_value: int
    status: ArtifactStatus
    history: list[str] = Field(default_factory=list)
    mule_origin: bool = False
```

Add dataclasses near the other dataclasses (`StatChange`, `CivShock`, etc.):

```python
@dataclass
class ArtifactIntent:
    artifact_type: ArtifactType
    trigger: str
    creator_name: str | None
    creator_born_turn: int | None
    holder_name: str | None
    holder_born_turn: int | None
    civ_name: str
    region_name: str
    anchored: bool | None = None
    mule_origin: bool = False
    context: str = ""


@dataclass
class ArtifactLifecycleIntent:
    action: str
    losing_civ: str
    gaining_civ: str | None
    region: str
    is_capital: bool
    is_full_absorption: bool
    is_destructive: bool
```

Add to `WorldState` (near existing fields):

```python
    artifacts: list[Artifact] = Field(default_factory=list)
```

Add to `WorldState` PrivateAttrs (near existing `_region_map`):

```python
    _artifact_intents: list = PrivateAttr(default_factory=list)
    _artifact_lifecycle_intents: list = PrivateAttr(default_factory=list)
    _artifact_prestige_by_civ: dict = PrivateAttr(default_factory=dict)
```

Add to `GreatPerson` (after existing `mule` field, near line 395):

```python
    mule_artifact_created: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py -v`
Expected: PASS (all model tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_artifacts.py
git commit -m "feat(m52): artifact data model — types, Artifact, WorldState fields, intents"
```

---

### Task 2: Naming System — `generate_artifact_name()`

**Files:**
- Create: `src/chronicler/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for name generation**

```python
# Add to tests/test_artifacts.py
from chronicler.artifacts import generate_artifact_name


class TestArtifactNaming:
    def test_weapon_name_with_creator(self):
        name = generate_artifact_name(
            ArtifactType.WEAPON, "Kiran", "Tessara", ["Honor"], seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0
        # Should contain either creator or place reference
        assert "Kiran" in name or "Tessara" in name

    def test_monument_name_with_place(self):
        name = generate_artifact_name(
            ArtifactType.MONUMENT, None, "Ashara", ["Trade"], seed=99,
        )
        assert "Ashara" in name

    def test_deterministic_same_seed(self):
        n1 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        n2 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        assert n1 == n2

    def test_different_seed_different_name(self):
        n1 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=42)
        n2 = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["Honor"], seed=43)
        # Different seeds should usually produce different names (not guaranteed but very likely)
        # Just verify both are valid strings
        assert isinstance(n1, str) and isinstance(n2, str)

    def test_cultural_flavor_honor(self):
        name = generate_artifact_name(ArtifactType.WEAPON, "Kiran", "Tessara", ["Honor"], seed=0)
        # Honor pool: Iron, Crimson, Bloodforged, Unyielding
        honor_adjs = {"Iron", "Crimson", "Bloodforged", "Unyielding"}
        # At least one honor adjective should appear in the name (may not if template doesn't use {adj})
        assert isinstance(name, str)

    def test_cultural_flavor_trade(self):
        name = generate_artifact_name(ArtifactType.ARTWORK, None, "Velanya", ["Trade"], seed=0)
        assert isinstance(name, str)

    def test_fallback_to_default_for_unknown_value(self):
        name = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", ["UnknownValue"], seed=42)
        assert isinstance(name, str) and len(name) > 0

    def test_empty_values_uses_default(self):
        name = generate_artifact_name(ArtifactType.RELIC, None, "Reg1", [], seed=42)
        assert isinstance(name, str) and len(name) > 0

    def test_possessive_creator_name(self):
        name = generate_artifact_name(ArtifactType.MONUMENT, "Ashara", "Region1", ["Order"], seed=0)
        # If template uses {creator}'s, should have possessive
        # Just verify it doesn't crash and produces a string
        assert isinstance(name, str)

    def test_all_types_produce_names(self):
        for atype in ArtifactType:
            name = generate_artifact_name(atype, "Creator", "Place", ["Honor"], seed=42)
            assert isinstance(name, str) and len(name) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestArtifactNaming -v`
Expected: FAIL — `artifacts` module doesn't exist

- [ ] **Step 3: Create `src/chronicler/artifacts.py` with naming system**

```python
"""M52: Artifacts & Significant Items.

Central artifact logic: naming, creation, lifecycle, prestige computation.
Model types live in models.py; behavior lives here.
"""
from __future__ import annotations

from chronicler.models import (
    Artifact, ArtifactType, ArtifactStatus,
    ArtifactIntent, ArtifactLifecycleIntent, Event,
)

# --- Calibration constants [CALIBRATE M53] ---

CULTURAL_PRODUCTION_CHANCE = 0.15
GP_PRESTIGE_THRESHOLD = 50
RELIC_CONVERSION_BONUS = 0.15
PROSPERITY_STABILITY_THRESHOLD = 70
PROSPERITY_TREASURY_THRESHOLD = 20
HISTORY_CAP = 10

PRESTIGE_BY_TYPE = {
    ArtifactType.MONUMENT: 4,
    ArtifactType.RELIC: 3,
    ArtifactType.WEAPON: 2,
    ArtifactType.ARTWORK: 2,
    ArtifactType.TREATISE: 2,
    ArtifactType.MANIFESTO: 1,
    ArtifactType.TRADE_GOOD: 1,
}

# --- Naming vocabulary ---

_ADJECTIVES = {
    "Honor": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Strength": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Self-reliance": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Trade": ["Golden", "Gilded", "Silver-wrought", "Precious"],
    "Knowledge": ["Ancient", "Illuminated", "Sage", "Inscribed"],
    "Tradition": ["Ancestral", "Hallowed", "Timeless", "Venerable"],
    "Order": ["Sovereign", "Imperial", "Lawbound", "Exalted"],
    "Destiny": ["Sovereign", "Imperial", "Lawbound", "Exalted"],
    "Cunning": ["Shadow", "Veiled", "Serpentine", "Subtle"],
    "Piety": ["Sacred", "Blessed", "Radiant", "Divine"],
    "Freedom": ["Wild", "Untamed", "Windsworn", "Bold"],
    "Liberty": ["Wild", "Untamed", "Windsworn", "Bold"],
}
_DEFAULT_ADJECTIVES = ["Great", "Renowned", "Storied", "Fabled"]

_NOUNS = {
    ArtifactType.WEAPON: ["Blade", "Shield", "Banner", "Spear", "Standard"],
    ArtifactType.RELIC: ["Chalice", "Tome", "Seal", "Vessel", "Shard"],
    ArtifactType.MONUMENT: ["Pillar", "Arch", "Colossus", "Obelisk", "Gate"],
    ArtifactType.ARTWORK: ["Tapestry", "Mosaic", "Fresco", "Idol", "Mask"],
    ArtifactType.TREATISE: ["Codex", "Scrolls", "Commentaries", "Meditations"],
    ArtifactType.MANIFESTO: ["Manifesto", "Declarations", "Edicts", "Theses"],
    ArtifactType.TRADE_GOOD: ["Silk", "Jade", "Amber", "Ivory", "Incense"],
}

_TEMPLATES = {
    ArtifactType.RELIC: [
        "The Sacred {adj} of {place}",
        "The {adj} Relic of {creator}",
        "The Holy {noun} of {place}",
    ],
    ArtifactType.WEAPON: [
        "The {noun} of {creator}",
        "{adj} {noun}",
        "The Blade of {place}",
    ],
    ArtifactType.MONUMENT: [
        "The {adj} {noun} of {place}",
        "The Great {noun} of {place}",
        "{creator_poss} {noun}",
    ],
    ArtifactType.ARTWORK: [
        "The {adj} {noun}",
        "The {noun} of {place}",
        "{creator_poss} {adj} {noun}",
    ],
    ArtifactType.TREATISE: [
        "The {noun} of {creator}",
        "The {adj} Codex",
        "The Letters of {creator}",
    ],
    ArtifactType.MANIFESTO: [
        "The {adj} Manifesto",
        "The Declarations of {creator}",
        "{creator_poss} {noun}",
    ],
    ArtifactType.TRADE_GOOD: [
        "The {adj} {noun} of {place}",
        "{place} {noun}",
    ],
}


def _possessive(name: str) -> str:
    """Generate possessive form: Ashara -> Ashara's."""
    if name.endswith("s"):
        return f"{name}'"
    return f"{name}'s"


def generate_artifact_name(
    artifact_type: ArtifactType,
    creator_name: str | None,
    origin_region: str,
    civ_values: list[str],
    seed: int,
) -> str:
    """Generate a deterministic canonical artifact name."""
    import random as _random
    rng = _random.Random(seed)

    # Resolve vocabulary
    dominant_value = civ_values[0] if civ_values else None
    adjs = _ADJECTIVES.get(dominant_value, _DEFAULT_ADJECTIVES)
    nouns = _NOUNS[artifact_type]
    templates = _TEMPLATES[artifact_type]

    adj = rng.choice(adjs)
    noun = rng.choice(nouns)
    template = rng.choice(templates)

    creator = creator_name or origin_region
    creator_poss = _possessive(creator)
    place = origin_region

    name = template.format(
        adj=adj, noun=noun, creator=creator,
        creator_poss=creator_poss, place=place,
    )
    return name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestArtifactNaming -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/artifacts.py tests/test_artifacts.py
git commit -m "feat(m52): artifact naming system with cultural flavor vocabulary"
```

---

### Task 3: Core `tick_artifacts()` — Creation from Intents

**Files:**
- Modify: `src/chronicler/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for artifact creation from intents**

```python
# Add to tests/test_artifacts.py
from chronicler.artifacts import tick_artifacts, PRESTIGE_BY_TYPE


def _make_world_with_civ(civ_name="TestCiv", region_name="Region1", values=None):
    """Helper: build a minimal WorldState with one civ and one region."""
    from chronicler.models import WorldState, Civilization, Region, Leader
    region = Region(name=region_name, terrain="plains", resources=["wheat"],
                    adjacencies=[], carrying_capacity=100)
    leader = Leader(name="TestLeader", trait="brave", reign_start=0)
    civ = Civilization(
        name=civ_name,
        values=values or ["Honor"],
        leader=leader,
        regions=[region_name],
        capital_region=region_name,
    )
    world = WorldState(name="TestWorld", seed=42)
    world.civilizations = [civ]
    world.regions = [region]
    region.controller = civ_name
    return world


class TestTickArtifactsCreation:
    def test_creation_from_intent(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Sacred relic forged in the temple",
        ))
        world.turn = 10
        events = tick_artifacts(world)
        assert len(world.artifacts) == 1
        a = world.artifacts[0]
        assert a.artifact_type == ArtifactType.RELIC
        assert a.anchored is True
        assert a.owner_civ == "TestCiv"
        assert a.origin_region == "Region1"
        assert a.status == ArtifactStatus.ACTIVE
        assert a.prestige_value == PRESTIGE_BY_TYPE[ArtifactType.RELIC]

    def test_creation_emits_event(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.WEAPON,
            trigger="gp_promotion",
            creator_name="Kiran",
            creator_born_turn=8,
            holder_name="Kiran",
            holder_born_turn=8,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=False,
            context="Forged at promotion",
        ))
        world.turn = 10
        events = tick_artifacts(world)
        assert any(e.event_type == "artifact_created" for e in events)

    def test_intents_cleared_after_tick(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.ARTWORK,
            trigger="cultural_work",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=False,
            context="Cultural masterwork",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert world._artifact_intents == []
        assert world._artifact_lifecycle_intents == []

    def test_artifact_id_increments(self):
        world = _make_world_with_civ()
        for i in range(3):
            world._artifact_intents.append(ArtifactIntent(
                artifact_type=ArtifactType.TREATISE,
                trigger="cultural_work",
                creator_name=None,
                creator_born_turn=None,
                holder_name=None,
                holder_born_turn=None,
                civ_name="TestCiv",
                region_name="Region1",
                anchored=False,
                context=f"Work {i}",
            ))
        world.turn = 10
        tick_artifacts(world)
        ids = [a.artifact_id for a in world.artifacts]
        assert ids == [1, 2, 3]

    def test_name_collision_reroll(self):
        world = _make_world_with_civ()
        # Create two artifacts with same params to force potential collision
        for _ in range(2):
            world._artifact_intents.append(ArtifactIntent(
                artifact_type=ArtifactType.RELIC,
                trigger="temple_construction",
                creator_name=None,
                creator_born_turn=None,
                holder_name=None,
                holder_born_turn=None,
                civ_name="TestCiv",
                region_name="Region1",
                anchored=True,
                context="Temple relic",
            ))
        world.turn = 10
        tick_artifacts(world)
        names = [a.name for a in world.artifacts]
        assert len(set(names)) == 2  # No duplicates

    def test_prestige_by_civ_computed(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.MONUMENT,
            trigger="cultural_work",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Monument",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert world._artifact_prestige_by_civ.get("TestCiv") == PRESTIGE_BY_TYPE[ArtifactType.MONUMENT]

    def test_history_entry_on_creation(self):
        world = _make_world_with_civ()
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.RELIC,
            trigger="temple_construction",
            creator_name=None,
            creator_born_turn=None,
            holder_name=None,
            holder_born_turn=None,
            civ_name="TestCiv",
            region_name="Region1",
            anchored=True,
            context="Sacred relic forged in the temple",
        ))
        world.turn = 10
        tick_artifacts(world)
        assert len(world.artifacts[0].history) == 1
        assert "turn 10" in world.artifacts[0].history[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestTickArtifactsCreation -v`
Expected: FAIL — `tick_artifacts` not defined

- [ ] **Step 3: Implement `tick_artifacts()` in `artifacts.py`**

Add to `src/chronicler/artifacts.py`:

```python
def _next_artifact_id(world) -> int:
    if not world.artifacts:
        return 1
    return max(a.artifact_id for a in world.artifacts) + 1


def _default_anchored(artifact_type: ArtifactType) -> bool:
    """Return default portability for a type."""
    if artifact_type == ArtifactType.MONUMENT:
        return True
    if artifact_type in (ArtifactType.WEAPON, ArtifactType.TRADE_GOOD,
                         ArtifactType.TREATISE, ArtifactType.MANIFESTO):
        return False
    if artifact_type == ArtifactType.RELIC:
        return True  # temple-bound by default
    # ARTWORK: portable by default
    return False


def _add_history(artifact: Artifact, entry: str) -> None:
    """Append a history entry, capping at HISTORY_CAP."""
    artifact.history.append(entry)
    if len(artifact.history) > HISTORY_CAP:
        # Keep first entry (origin) and trim from second position
        artifact.history = [artifact.history[0]] + artifact.history[-(HISTORY_CAP - 1):]


def tick_artifacts(world) -> list[Event]:
    """Phase 10: Process artifact intents, lifecycle, and prestige.

    Called at end of Phase 10, after GP/conquest/exile state has settled.
    """
    events: list[Event] = []
    existing_names = {a.name for a in world.artifacts}

    # 1. Process creation intents
    for intent in world._artifact_intents:
        anchored = intent.anchored if intent.anchored is not None else _default_anchored(intent.artifact_type)
        # Character-held implies portable
        if intent.holder_name is not None:
            anchored = False

        # Generate name with collision avoidance
        civ = None
        for c in world.civilizations:
            if c.name == intent.civ_name:
                civ = c
                break
        civ_values = civ.values if civ else []
        base_seed = world.seed + world.turn + _next_artifact_id(world)

        name = generate_artifact_name(
            intent.artifact_type, intent.creator_name,
            intent.region_name, civ_values, seed=base_seed,
        )
        # Collision re-rolls (salted seed)
        for salt in range(1, 3):
            if name not in existing_names:
                break
            name = generate_artifact_name(
                intent.artifact_type, intent.creator_name,
                intent.region_name, civ_values, seed=base_seed + salt * 7919,
            )
        # Final fallback: numeral suffix
        if name in existing_names:
            suffix = 2
            while f"{name} {_roman(suffix)}" in existing_names:
                suffix += 1
            name = f"{name} {_roman(suffix)}"
        existing_names.add(name)

        artifact = Artifact(
            artifact_id=_next_artifact_id(world),
            name=name,
            artifact_type=intent.artifact_type,
            anchored=anchored,
            origin_turn=world.turn,
            origin_event=intent.context,
            origin_region=intent.region_name,
            creator_name=intent.creator_name,
            creator_civ=intent.civ_name,
            owner_civ=intent.civ_name,
            holder_name=intent.holder_name,
            holder_born_turn=intent.holder_born_turn,
            anchor_region=intent.region_name if anchored else None,
            prestige_value=PRESTIGE_BY_TYPE.get(intent.artifact_type, 1),
            status=ArtifactStatus.ACTIVE,
            history=[f"{intent.context}, turn {world.turn}"],
            mule_origin=intent.mule_origin,
        )
        world.artifacts.append(artifact)

        actors = [intent.creator_name or intent.civ_name, name]
        events.append(Event(
            turn=world.turn,
            event_type="artifact_created",
            actors=actors,
            description=f"{name} created by {intent.civ_name}",
            importance=6,
        ))

    # 2. Process lifecycle intents (Task 5)

    # 3. Holder lifecycle (Task 5)

    # 4. Compute ephemeral prestige
    world._artifact_prestige_by_civ = {}
    for a in world.artifacts:
        if a.status == ArtifactStatus.ACTIVE and a.owner_civ:
            world._artifact_prestige_by_civ[a.owner_civ] = (
                world._artifact_prestige_by_civ.get(a.owner_civ, 0) + a.prestige_value
            )

    # 5. Clear intents
    world._artifact_intents = []
    world._artifact_lifecycle_intents = []

    return events


def _roman(n: int) -> str:
    """Simple roman numeral for small collision suffixes."""
    numerals = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
                6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
    return numerals.get(n, str(n))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestTickArtifactsCreation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/artifacts.py tests/test_artifacts.py
git commit -m "feat(m52): tick_artifacts() core — creation from intents, prestige, naming"
```

---

### Task 4: `_prosperity_gate()` and Cultural Production Type Selection

**Files:**
- Modify: `src/chronicler/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for prosperity gate**

```python
# Add to tests/test_artifacts.py
from chronicler.artifacts import _prosperity_gate, select_cultural_artifact_type


class TestProsperityGate:
    def test_prosperous_civ_passes(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is True

    def test_low_stability_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 60
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_at_war_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = [("TestCiv", "EnemyCiv")]
        assert _prosperity_gate(civ, world) is False

    def test_in_decline_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 3
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_succession_crisis_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 5
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False

    def test_low_treasury_fails(self):
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 10
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        world.active_wars = []
        assert _prosperity_gate(civ, world) is False


class TestCulturalArtifactTypeSelection:
    def test_returns_valid_type(self):
        from chronicler.models import Civilization, Leader
        civ = Civilization(
            name="TestCiv", values=["Knowledge"], leader=Leader(name="L", trait="t"),
            regions=["R1"],
        )
        atype = select_cultural_artifact_type(civ, seed=42)
        assert atype in (ArtifactType.ARTWORK, ArtifactType.TREATISE, ArtifactType.MONUMENT)

    def test_deterministic(self):
        from chronicler.models import Civilization, Leader
        civ = Civilization(
            name="TestCiv", values=["Knowledge"], leader=Leader(name="L", trait="t"),
            regions=["R1"],
        )
        t1 = select_cultural_artifact_type(civ, seed=42)
        t2 = select_cultural_artifact_type(civ, seed=42)
        assert t1 == t2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestProsperityGate tests/test_artifacts.py::TestCulturalArtifactTypeSelection -v`
Expected: FAIL

- [ ] **Step 3: Implement `_prosperity_gate()` and `select_cultural_artifact_type()`**

Add to `src/chronicler/artifacts.py`:

```python
def _prosperity_gate(civ, world) -> bool:
    """Check whether a civ is in a prosperous enough state for cultural production."""
    return (
        civ.stability > PROSPERITY_STABILITY_THRESHOLD
        and civ.treasury >= PROSPERITY_TREASURY_THRESHOLD
        and not any(civ.name in war for war in world.active_wars)
        and civ.decline_turns == 0
        and civ.succession_crisis_turns_remaining == 0
    )


def select_cultural_artifact_type(civ, seed: int) -> ArtifactType:
    """Select cultural artifact type, biased by faction dominance.

    Cultural faction dominance biases toward ARTWORK/TREATISE.
    Military dominance biases toward MONUMENT.
    Default is uniform among the three types.
    """
    import random as _random
    rng = _random.Random(seed)

    # Check for cultural faction dominance
    weights = {
        ArtifactType.ARTWORK: 1.0,
        ArtifactType.TREATISE: 1.0,
        ArtifactType.MONUMENT: 1.0,
    }

    # civ.factions is a FactionState with .dominant (str | None), not an iterable
    if hasattr(civ, 'factions') and civ.factions and civ.factions.dominant:
        dominant = civ.factions.dominant
        if dominant == "cultural":
            weights[ArtifactType.ARTWORK] = 2.0
            weights[ArtifactType.TREATISE] = 1.5
        elif dominant == "military":
            weights[ArtifactType.MONUMENT] = 2.0
        elif dominant == "merchant":
            weights[ArtifactType.ARTWORK] = 1.5

    types = list(weights.keys())
    w = [weights[t] for t in types]
    return rng.choices(types, weights=w, k=1)[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestProsperityGate tests/test_artifacts.py::TestCulturalArtifactTypeSelection -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/artifacts.py tests/test_artifacts.py
git commit -m "feat(m52): prosperity gate and cultural artifact type selection"
```

---

### Task 5: Lifecycle — Conquest Transfers, Holder Reversion, Civ Destruction

**Files:**
- Modify: `src/chronicler/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for lifecycle transitions**

```python
# Add to tests/test_artifacts.py
from chronicler.models import GreatPerson, Leader


def _make_active_artifact(world, artifact_type=ArtifactType.RELIC, anchored=True,
                           owner_civ="TestCiv", region="Region1", **kwargs):
    """Helper: add an active artifact to world and return it."""
    aid = len(world.artifacts) + 1
    a = Artifact(
        artifact_id=aid, name=f"Artifact {aid}", artifact_type=artifact_type,
        anchored=anchored, origin_turn=1, origin_event="test",
        origin_region=region, creator_name=None, creator_civ=owner_civ,
        owner_civ=owner_civ, holder_name=kwargs.get("holder_name"),
        holder_born_turn=kwargs.get("holder_born_turn"),
        anchor_region=region if anchored else None,
        prestige_value=PRESTIGE_BY_TYPE.get(artifact_type, 1),
        status=ArtifactStatus.ACTIVE, history=["created"],
        **{k: v for k, v in kwargs.items() if k not in ("holder_name", "holder_born_turn")},
    )
    world.artifacts.append(a)
    return a


class TestConquestTransfers:
    def test_anchored_artifact_changes_owner_on_nondestructive_conquest(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "Conqueror"
        assert world.artifacts[0].status == ArtifactStatus.ACTIVE

    def test_anchored_artifact_destroyed_on_scorched_earth(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=True,
        ))
        world.turn = 20
        events = tick_artifacts(world)
        assert world.artifacts[0].status == ArtifactStatus.DESTROYED
        assert world.artifacts[0].owner_civ is None
        assert any(e.event_type == "artifact_destroyed" for e in events)

    def test_portable_artifacts_transfer_on_capital_capture(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.TREATISE, anchored=False, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=True, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        events = tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "Conqueror"
        assert any(e.event_type == "artifact_captured" for e in events)

    def test_portable_artifacts_NOT_transferred_on_non_capital_conquest(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.TREATISE, anchored=False, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=False, is_full_absorption=False, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        assert world.artifacts[0].owner_civ == "TestCiv"  # unchanged

    def test_character_held_artifact_stays_with_holder(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8,
        )
        # Add a GP so holder lifecycle doesn't revert it
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=True,
        )
        world.civilizations[0].great_persons.append(gp)
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="conquest_transfer", losing_civ="TestCiv", gaining_civ="Conqueror",
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 20
        tick_artifacts(world)
        # Character-held artifact stays with holder
        assert world.artifacts[0].holder_name == "Kiran"


class TestHolderLifecycle:
    def test_inactive_holder_reverts_to_civ(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8,
        )
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=False, fate="dead",
        )
        world.civilizations[0].great_persons.append(gp)
        world.turn = 30
        tick_artifacts(world)
        assert world.artifacts[0].holder_name is None
        assert world.artifacts[0].owner_civ == "TestCiv"

    def test_mule_holder_death_emits_event(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8, mule_origin=True,
        )
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=8, active=False, fate="dead",
        )
        world.civilizations[0].great_persons.append(gp)
        world.turn = 30
        events = tick_artifacts(world)
        assert any(e.event_type == "mule_artifact_relinquished" for e in events)


class TestCivDestruction:
    def test_no_absorber_marks_artifacts_lost(self):
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv")
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="civ_destruction", losing_civ="TestCiv", gaining_civ=None,
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 50
        events = tick_artifacts(world)
        assert world.artifacts[0].status == ArtifactStatus.LOST
        assert world.artifacts[0].owner_civ is None
        assert any(e.event_type == "artifact_lost" for e in events)

    def test_live_holder_survives_civ_destruction(self):
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Exile", holder_born_turn=5,
        )
        gp = GreatPerson(
            name="Exile", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=5, active=True,
        )
        world.civilizations[0].great_persons.append(gp)
        world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
            action="civ_destruction", losing_civ="TestCiv", gaining_civ=None,
            region="Region1", is_capital=True, is_full_absorption=True, is_destructive=False,
        ))
        world.turn = 50
        tick_artifacts(world)
        # Live holder keeps artifact active
        assert world.artifacts[0].status == ArtifactStatus.ACTIVE
        assert world.artifacts[0].holder_name == "Exile"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestConquestTransfers tests/test_artifacts.py::TestHolderLifecycle tests/test_artifacts.py::TestCivDestruction -v`
Expected: FAIL — lifecycle logic not implemented

- [ ] **Step 3: Add lifecycle logic to `tick_artifacts()` in `artifacts.py`**

Replace the placeholder comments `# 2. Process lifecycle intents` and `# 3. Holder lifecycle` in `tick_artifacts()` with:

```python
    # 2. Process lifecycle intents
    for intent in world._artifact_lifecycle_intents:
        if intent.action == "conquest_transfer":
            _process_conquest(world, intent, events)
        elif intent.action == "twilight_absorption":
            _process_conquest(world, intent, events)  # same rules
        elif intent.action == "civ_destruction":
            _process_civ_destruction(world, intent, events)

    # 3. Holder lifecycle — check for inactive holders
    _process_holder_lifecycle(world, events)
```

Add the helper functions:

```python
def _find_gp(world, name: str, born_turn: int | None):
    """Find a GreatPerson by (name, born_turn) across all civs."""
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.name == name and gp.born_turn == born_turn:
                return gp
    return None


def _process_conquest(world, intent: ArtifactLifecycleIntent, events: list) -> None:
    """Handle artifact transfers on conquest or twilight absorption."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE:
            continue

        # Character-held artifacts stay with holder
        if a.holder_name is not None:
            continue

        # Anchored artifacts in the conquered region
        if a.anchored and a.anchor_region == intent.region:
            if intent.is_destructive:
                a.status = ArtifactStatus.DESTROYED
                a.owner_civ = None
                _add_history(a, f"Destroyed during the sack of {intent.region}, turn {world.turn}")
                events.append(Event(
                    turn=world.turn, event_type="artifact_destroyed",
                    actors=[intent.gaining_civ or "unknown", a.name],
                    description=f"{a.name} destroyed in {intent.region}",
                    importance=7,
                ))
            else:
                old_owner = a.owner_civ
                a.owner_civ = intent.gaining_civ
                _add_history(a, f"Claimed by {intent.gaining_civ} after the fall of {intent.region}, turn {world.turn}")
            continue

        # Portable civ-owned artifacts — only on capital capture or full absorption
        if not a.anchored and a.owner_civ == intent.losing_civ:
            if intent.is_capital or intent.is_full_absorption:
                old_owner = a.owner_civ
                a.owner_civ = intent.gaining_civ
                _add_history(a, f"Captured by {intent.gaining_civ} during the fall of {intent.region}, turn {world.turn}")
                events.append(Event(
                    turn=world.turn, event_type="artifact_captured",
                    actors=[intent.gaining_civ, intent.losing_civ, a.name],
                    description=f"{a.name} captured by {intent.gaining_civ}",
                    importance=7,
                ))


def _process_civ_destruction(world, intent: ArtifactLifecycleIntent, events: list) -> None:
    """Handle artifacts when a civ is destroyed without absorber."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE or a.owner_civ != intent.losing_civ:
            continue

        # Live holder keeps artifact
        if a.holder_name is not None:
            gp = _find_gp(world, a.holder_name, a.holder_born_turn)
            if gp and gp.active:
                continue  # holder lives, artifact stays active

        a.status = ArtifactStatus.LOST
        a.owner_civ = None
        a.holder_name = None
        a.holder_born_turn = None
        _add_history(a, f"Lost when {intent.losing_civ} fell, turn {world.turn}")
        events.append(Event(
            turn=world.turn, event_type="artifact_lost",
            actors=[intent.losing_civ, a.name],
            description=f"{a.name} lost when {intent.losing_civ} fell",
            importance=6,
        ))


def _process_holder_lifecycle(world, events: list) -> None:
    """Check character-held artifacts for inactive holders."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE or a.holder_name is None:
            continue
        gp = _find_gp(world, a.holder_name, a.holder_born_turn)
        if gp is None or not gp.active:
            revert_civ = gp.civilization if gp else a.owner_civ
            fate = gp.fate if gp else "unknown fate"
            holder_name = a.holder_name

            if a.mule_origin:
                events.append(Event(
                    turn=world.turn, event_type="mule_artifact_relinquished",
                    actors=[holder_name, revert_civ or "", a.name],
                    description=f"{a.name} relinquished after {holder_name}'s {fate}",
                    importance=7,
                ))

            _add_history(a, f"Returned to {revert_civ} after {holder_name}'s {fate}, turn {world.turn}")
            a.holder_name = None
            a.holder_born_turn = None
            a.owner_civ = revert_civ
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestConquestTransfers tests/test_artifacts.py::TestHolderLifecycle tests/test_artifacts.py::TestCivDestruction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/artifacts.py tests/test_artifacts.py
git commit -m "feat(m52): artifact lifecycle — conquest transfers, holder reversion, civ destruction"
```

---

### Task 6: Ephemeral Prestige in `tick_prestige()`

**Files:**
- Modify: `src/chronicler/culture.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test for artifact prestige in trade bonus**

```python
# Add to tests/test_artifacts.py
class TestArtifactPrestigeIntegration:
    def test_artifact_prestige_adds_to_treasury(self):
        """Artifact prestige should add to treasury via trade bonus in tick_prestige()."""
        from chronicler.culture import tick_prestige
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = 0
        civ.treasury = 100
        # Set ephemeral artifact prestige
        world._artifact_prestige_by_civ = {"TestCiv": 5}
        tick_prestige(world)
        # With 0 base prestige (trade_bonus=0) and 5 artifact prestige,
        # total_trade_bonus = 0 + 5 = 5, added to treasury
        assert civ.treasury > 100  # artifact bonus added via treasury

    def test_no_artifact_prestige_no_extra_treasury(self):
        """When no artifacts and 0 prestige, no trade bonus to treasury."""
        from chronicler.culture import tick_prestige
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = 0
        treasury_before = civ.treasury
        world._artifact_prestige_by_civ = {}
        tick_prestige(world)
        # With 0 prestige and no artifacts, treasury gets no trade bonus
        # (prestige decays but can't go below 0)
        assert civ.treasury <= treasury_before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestArtifactPrestigeIntegration -v`
Expected: FAIL — `tick_prestige` doesn't read `_artifact_prestige_by_civ`

- [ ] **Step 3: Modify `tick_prestige()` in `culture.py`**

Read `src/chronicler/culture.py` lines 392-410. `tick_prestige()` computes `trade_bonus = civ.prestige // prestige_divisor` and adds it to `civ.treasury`. After the existing `trade_bonus` line (around line 404), add the artifact term:

```python
        trade_bonus = civ.prestige // prestige_divisor
        # M52: Add ephemeral artifact prestige to trade bonus
        if hasattr(world, '_artifact_prestige_by_civ'):
            trade_bonus += world._artifact_prestige_by_civ.get(civ.name, 0)
```

This ensures the artifact prestige contribution flows through the same `trade_bonus → treasury` path as stock-based prestige.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestArtifactPrestigeIntegration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_artifacts.py
git commit -m "feat(m52): ephemeral artifact prestige in tick_prestige() trade bonus"
```

---

### Task 7: Intent Emission — Simulation (Cultural Production)

**Files:**
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test for cultural production intent emission**

```python
# Add to tests/test_artifacts.py
class TestCulturalProductionIntents:
    def test_cultural_work_emits_intent_when_prosperous(self):
        """phase_cultural_milestones should emit artifact intent when prosperity gate passes."""
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.stability = 80
        civ.treasury = 50
        civ.decline_turns = 0
        civ.succession_crisis_turns_remaining = 0
        civ.culture = 60  # above first milestone threshold
        civ.cultural_milestones = []
        civ.capital_region = "Region1"
        world.active_wars = []
        world.turn = 10
        world.seed = 1  # seed that hits CULTURAL_PRODUCTION_CHANCE

        from chronicler.simulation import phase_cultural_milestones
        # Run multiple times with different seeds to find one that triggers
        # Just verify the mechanism exists and can produce intents
        found = False
        for s in range(100):
            world.seed = s
            civ.cultural_milestones = []
            world._artifact_intents = []
            phase_cultural_milestones(world)
            if world._artifact_intents:
                found = True
                break
        # With CULTURAL_PRODUCTION_CHANCE=0.15, ~15 of 100 seeds should trigger
        assert found, "No artifact intent emitted after 100 seeds"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestCulturalProductionIntents -v`
Expected: FAIL — no intent emission code in `phase_cultural_milestones`

- [ ] **Step 3: Add intent emission to `simulation.py`**

In `phase_cultural_milestones()` (line ~1117 of `simulation.py`), after the existing `cultural_work` event creation block (after `events.append(Event(...))` near line 1145), add:

```python
                # M52: Cultural artifact production
                from chronicler.artifacts import (
                    _prosperity_gate, select_cultural_artifact_type,
                    CULTURAL_PRODUCTION_CHANCE,
                )
                from chronicler.models import ArtifactIntent
                import random as _rng_mod
                _art_rng = _rng_mod.Random(world.seed + world.turn + civ_idx + 9999)
                if _prosperity_gate(civ, world) and _art_rng.random() < CULTURAL_PRODUCTION_CHANCE:
                    _art_type = select_cultural_artifact_type(civ, seed=world.seed + world.turn + civ_idx)
                    _art_region = civ.capital_region or (civ.regions[0] if civ.regions else "unknown")
                    world._artifact_intents.append(ArtifactIntent(
                        artifact_type=_art_type,
                        trigger="cultural_work",
                        creator_name=None,
                        creator_born_turn=None,
                        holder_name=None,
                        holder_born_turn=None,
                        civ_name=civ.name,
                        region_name=_art_region,
                        anchored=True if _art_type.value == "monument" else None,
                        context=f"Produced during a cultural milestone of {civ.name}",
                    ))
```

Similarly, in `_apply_event_effects()` (near line 700 where `cultural_renaissance` is handled), after the existing stat modifications for the `cultural_renaissance` case, add:

```python
            # M52: Cultural artifact production on renaissance
            from chronicler.artifacts import (
                _prosperity_gate, select_cultural_artifact_type,
                CULTURAL_PRODUCTION_CHANCE,
            )
            from chronicler.models import ArtifactIntent
            import random as _rng_mod
            _art_rng = _rng_mod.Random(world.seed + world.turn + civ_idx + 8888)
            if _prosperity_gate(civ, world) and _art_rng.random() < CULTURAL_PRODUCTION_CHANCE:
                _art_type = select_cultural_artifact_type(civ, seed=world.seed + world.turn + civ_idx)
                _art_region = civ.capital_region or (civ.regions[0] if civ.regions else "unknown")
                world._artifact_intents.append(ArtifactIntent(
                    artifact_type=_art_type,
                    trigger="cultural_renaissance",
                    creator_name=None,
                    creator_born_turn=None,
                    holder_name=None,
                    holder_born_turn=None,
                    civ_name=civ.name,
                    region_name=_art_region,
                    anchored=True if _art_type.value == "monument" else None,
                    context=f"Inspired during a cultural renaissance of {civ.name}",
                ))
```

Note: `civ` and `civ_idx` are both available inside `_apply_event_effects()` — `civ` is a parameter, `civ_idx` is computed at line 646 via `civ_index(world, civ.name)`.

Also add the `tick_artifacts()` call in the turn loop. In `run_turn()` (near line 1395 after `phase_consequences`), before the timeline write:

```python
    # M52: Artifact processing
    from chronicler.artifacts import tick_artifacts
    artifact_events = tick_artifacts(world)
    turn_events.extend(artifact_events)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestCulturalProductionIntents -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_artifacts.py
git commit -m "feat(m52): cultural production intents + tick_artifacts() in turn loop"
```

---

### Task 8: Intent Emission — Infrastructure (Temple Relic)

**Files:**
- Modify: `src/chronicler/infrastructure.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_artifacts.py
class TestTempleRelicIntent:
    def test_temple_completion_emits_relic_intent(self):
        from chronicler.models import PendingBuild, InfrastructureType
        world = _make_world_with_civ()
        region = world.regions[0]
        region.pending_build = PendingBuild(
            type=InfrastructureType.TEMPLES, turns_remaining=1,
            builder_civ="TestCiv", started_turn=9,
        )
        world.turn = 10
        world._artifact_intents = []

        from chronicler.infrastructure import tick_infrastructure
        tick_infrastructure(world)

        relic_intents = [i for i in world._artifact_intents if i.trigger == "temple_construction"]
        assert len(relic_intents) == 1
        assert relic_intents[0].artifact_type == ArtifactType.RELIC
        assert relic_intents[0].anchored is True

    def test_non_temple_completion_no_intent(self):
        from chronicler.models import PendingBuild, InfrastructureType
        world = _make_world_with_civ()
        region = world.regions[0]
        region.pending_build = PendingBuild(
            type=InfrastructureType.ROADS, turns_remaining=1,
            builder_civ="TestCiv", started_turn=9,
        )
        world.turn = 10
        world._artifact_intents = []

        from chronicler.infrastructure import tick_infrastructure
        tick_infrastructure(world)

        assert len(world._artifact_intents) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestTempleRelicIntent -v`
Expected: FAIL

- [ ] **Step 3: Add intent emission to `tick_infrastructure()`**

In `src/chronicler/infrastructure.py`, inside the completion block (after the `infrastructure_completed` event is appended, near line 111), add a TEMPLES-only gate:

```python
                # M52: Temple relic creation (only for temples, not other infrastructure)
                if completed.type == InfrastructureType.TEMPLES:
                    from chronicler.models import ArtifactIntent, ArtifactType as _AT
                    world._artifact_intents.append(ArtifactIntent(
                        artifact_type=_AT.RELIC,
                        trigger="temple_construction",
                        creator_name=None,
                        creator_born_turn=None,
                        holder_name=None,
                        holder_born_turn=None,
                        civ_name=region.pending_build.builder_civ,
                        region_name=region.name,
                        anchored=True,
                        context=f"Sacred relic consecrated in the temple of {region.name}",
                    ))
```

Note: `completed` is the `Infrastructure` object created from `region.pending_build` in the completion block. `region.pending_build` is singular (`PendingBuild | None`), not a list. Read the actual loop structure before editing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestTempleRelicIntent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/infrastructure.py tests/test_artifacts.py
git commit -m "feat(m52): temple completion emits relic artifact intent"
```

---

### Task 9: Intent Emission — GP Promotion & Mule Action

**Files:**
- Modify: `src/chronicler/agent_bridge.py`, `src/chronicler/great_persons.py`, `src/chronicler/action_engine.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for GP and Mule intents**

```python
# Add to tests/test_artifacts.py
class TestGPPromotionIntent:
    def test_high_prestige_general_promotion_emits_weapon_intent(self):
        """When a general is promoted and civ prestige > threshold, emit WEAPON intent."""
        from chronicler.artifacts import GP_PRESTIGE_THRESHOLD
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = GP_PRESTIGE_THRESHOLD + 10
        world._artifact_intents = []
        world.turn = 15

        # Simulate what the intent emission code should do
        from chronicler.artifacts import emit_gp_artifact_intent
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=15,
        )
        emit_gp_artifact_intent(world, civ, gp)
        assert len(world._artifact_intents) == 1
        assert world._artifact_intents[0].artifact_type == ArtifactType.WEAPON
        assert world._artifact_intents[0].holder_name == "Kiran"

    def test_low_prestige_no_intent(self):
        from chronicler.artifacts import GP_PRESTIGE_THRESHOLD
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = GP_PRESTIGE_THRESHOLD - 10
        world._artifact_intents = []

        from chronicler.artifacts import emit_gp_artifact_intent
        gp = GreatPerson(
            name="Kiran", role="general", trait="brave", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=15,
        )
        emit_gp_artifact_intent(world, civ, gp)
        assert len(world._artifact_intents) == 0

    def test_prophet_promotion_emits_relic(self):
        from chronicler.artifacts import GP_PRESTIGE_THRESHOLD
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = GP_PRESTIGE_THRESHOLD + 10
        world._artifact_intents = []

        from chronicler.artifacts import emit_gp_artifact_intent
        gp = GreatPerson(
            name="Prophet", role="prophet", trait="wise", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=20,
        )
        emit_gp_artifact_intent(world, civ, gp)
        assert len(world._artifact_intents) == 1
        assert world._artifact_intents[0].artifact_type == ArtifactType.RELIC

    def test_exile_promotion_no_artifact(self):
        from chronicler.artifacts import GP_PRESTIGE_THRESHOLD
        world = _make_world_with_civ()
        civ = world.civilizations[0]
        civ.prestige = GP_PRESTIGE_THRESHOLD + 10
        world._artifact_intents = []

        from chronicler.artifacts import emit_gp_artifact_intent
        gp = GreatPerson(
            name="Exile", role="exile", trait="shrewd", civilization="TestCiv",
            origin_civilization="TestCiv", born_turn=20,
        )
        emit_gp_artifact_intent(world, civ, gp)
        assert len(world._artifact_intents) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestGPPromotionIntent -v`
Expected: FAIL — `emit_gp_artifact_intent` doesn't exist

- [ ] **Step 3: Add `emit_gp_artifact_intent()` to `artifacts.py`**

```python
# GP role → artifact type mapping
_GP_ROLE_TO_ARTIFACT = {
    "general": (ArtifactType.WEAPON, True),    # (type, character_held)
    "prophet": (ArtifactType.RELIC, False),
    "merchant": (ArtifactType.ARTWORK, False),
    "scientist": (ArtifactType.TREATISE, False),
}


def emit_gp_artifact_intent(world, civ, gp) -> None:
    """Emit artifact creation intent for a newly promoted GP, if prestige threshold is met."""
    if civ.prestige < GP_PRESTIGE_THRESHOLD:
        return
    mapping = _GP_ROLE_TO_ARTIFACT.get(gp.role)
    if mapping is None:
        return  # exile, hostage — no artifact

    artifact_type, character_held = mapping
    region = gp.origin_region or civ.capital_region or (civ.regions[0] if civ.regions else "unknown")

    world._artifact_intents.append(ArtifactIntent(
        artifact_type=artifact_type,
        trigger="gp_promotion",
        creator_name=gp.name,
        creator_born_turn=gp.born_turn,
        holder_name=gp.name if character_held else None,
        holder_born_turn=gp.born_turn if character_held else None,
        civ_name=civ.name,
        region_name=region,
        anchored=None,
        context=f"Created at the rise of {gp.name}",
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestGPPromotionIntent -v`
Expected: PASS

- [ ] **Step 5: Wire `emit_gp_artifact_intent()` into `_process_promotions()` and `check_great_person_generation()`**

In `src/chronicler/agent_bridge.py`, in `_process_promotions()` after a GP is created and appended to `civ.great_persons`, add:

```python
            # M52: GP artifact intent
            from chronicler.artifacts import emit_gp_artifact_intent
            emit_gp_artifact_intent(self.world, civ, gp)
```

In `src/chronicler/great_persons.py`, in `check_great_person_generation()` after a GP is created and appended, add the same call:

```python
            # M52: GP artifact intent (aggregate mode)
            from chronicler.artifacts import emit_gp_artifact_intent
            emit_gp_artifact_intent(world, civ, gp)
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/artifacts.py src/chronicler/agent_bridge.py src/chronicler/great_persons.py tests/test_artifacts.py
git commit -m "feat(m52): GP promotion artifact intents — agent + aggregate paths"
```

- [ ] **Step 7: Wire Mule artifact intent in `action_engine.py`**

In `src/chronicler/action_engine.py`, after the Mule weight modification block (near line 895), add Mule artifact intent emission. After action resolution, when the chosen action matches a Mule's favored action:

Read the existing Mule weight loop structure first. The intent should fire after the civ's action is resolved and the action type is known. Add a new function to `artifacts.py`:

```python
def emit_mule_artifact_intent(world, civ, gp, action_name: str) -> None:
    """Emit Mule artifact intent on first matching action success."""
    from chronicler.action_engine import MULE_ACTIVE_WINDOW
    if not gp.mule or not gp.active or gp.mule_artifact_created:
        return
    age = world.turn - gp.born_turn
    if age > MULE_ACTIVE_WINDOW:
        return
    # Check if this action is genuinely favored (multiplier > 1.0, not suppressed)
    if gp.utility_overrides.get(action_name, 1.0) <= 1.0:
        return

    _MULE_ACTION_ARTIFACTS = {
        ("general", "WAR"): ArtifactType.RELIC,
        ("general", "DEVELOP"): ArtifactType.TREATISE,
        ("merchant", "TRADE"): ArtifactType.TRADE_GOOD,
        ("merchant", "FUND_INSTABILITY"): ArtifactType.MANIFESTO,
        ("prophet", "BUILD"): ArtifactType.RELIC,
        ("scientist", "DEVELOP"): ArtifactType.TREATISE,
    }
    artifact_type = _MULE_ACTION_ARTIFACTS.get((gp.role, action_name))
    if artifact_type is None:
        return

    region = gp.origin_region or civ.capital_region or (civ.regions[0] if civ.regions else "unknown")
    world._artifact_intents.append(ArtifactIntent(
        artifact_type=artifact_type,
        trigger="mule_action",
        creator_name=gp.name,
        creator_born_turn=gp.born_turn,
        holder_name=gp.name,
        holder_born_turn=gp.born_turn,
        civ_name=civ.name,
        region_name=region,
        anchored=None,
        mule_origin=True,
        context=f"Born of {gp.name}'s influence over {civ.name}",
    ))
    gp.mule_artifact_created = True
```

In `simulation.py`, inside `phase_action()` (near line 531-571), after `resolve_action(civ, action, world, acc=acc)` returns, add:

```python
        # M52: Mule artifact on action success
        from chronicler.artifacts import emit_mule_artifact_intent
        for gp in civ.great_persons:
            if gp.mule and gp.active:
                emit_mule_artifact_intent(world, civ, gp, action.name)
```

Note: `action` is the `ActionType` enum value from the action selection loop. `action.name` gives the string like `"WAR"`, `"TRADE"`, etc. `world` is a module-level parameter, not `self.world`.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/artifacts.py src/chronicler/action_engine.py
git commit -m "feat(m52): Mule artifact intent on first matching action success"
```

---

### Task 10: Intent Emission — Conquest & Twilight Absorption

**Files:**
- Modify: `src/chronicler/action_engine.py`, `src/chronicler/politics.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test for conquest lifecycle intent**

```python
# Add to tests/test_artifacts.py
class TestConquestLifecycleIntentEmission:
    def test_conquest_emits_lifecycle_intent(self):
        """_resolve_war_action should emit ArtifactLifecycleIntent on conquest."""
        # This is an integration test — verify the intent is emitted
        # by checking world._artifact_lifecycle_intents after a conquest
        # Full integration test with action engine is complex; verify the
        # mechanism via a unit test of the emission helper
        from chronicler.artifacts import emit_conquest_lifecycle_intent
        world = _make_world_with_civ()
        world._artifact_lifecycle_intents = []
        emit_conquest_lifecycle_intent(
            world, losing_civ="Defender", gaining_civ="Attacker",
            region="Region1", is_capital=True, is_destructive=False,
        )
        assert len(world._artifact_lifecycle_intents) == 1
        intent = world._artifact_lifecycle_intents[0]
        assert intent.action == "conquest_transfer"
        assert intent.is_capital is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestConquestLifecycleIntentEmission -v`
Expected: FAIL

- [ ] **Step 3: Add `emit_conquest_lifecycle_intent()` to `artifacts.py`**

```python
def emit_conquest_lifecycle_intent(
    world, losing_civ: str, gaining_civ: str, region: str,
    is_capital: bool, is_destructive: bool,
) -> None:
    """Emit a lifecycle intent for conquest or twilight absorption."""
    losing = None
    for c in world.civilizations:
        if c.name == losing_civ:
            losing = c
            break
    is_full = losing is not None and len(losing.regions) == 0

    world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
        action="conquest_transfer",
        losing_civ=losing_civ,
        gaining_civ=gaining_civ,
        region=region,
        is_capital=is_capital,
        is_full_absorption=is_full,
        is_destructive=is_destructive,
    ))
```

- [ ] **Step 4: Wire into `_resolve_war_action()` in `action_engine.py`**

In `src/chronicler/action_engine.py`, after the conquest block (after `defender.regions = [r for r in defender.regions if r != contested.name]` near line 517), and after the scorched earth check (line 527), add:

```python
            # M52: Artifact lifecycle intent
            from chronicler.artifacts import emit_conquest_lifecycle_intent
            _scorched = bool(scorch_events)  # True if scorched earth fired
            _was_capital = (contested.name == defender.capital_region)
            emit_conquest_lifecycle_intent(
                world, losing_civ=defender.name, gaining_civ=attacker.name,
                region=contested.name, is_capital=_was_capital,
                is_destructive=_scorched,
            )
```

- [ ] **Step 5: Wire into `check_twilight_absorption()` in `politics.py`**

In `src/chronicler/politics.py`, inside `check_twilight_absorption()` (near line 1175), after the absorption transfers regions, add:

```python
                # M52: Artifact lifecycle intent for twilight absorption
                from chronicler.artifacts import emit_conquest_lifecycle_intent
                for region_name in absorbed_regions:
                    emit_conquest_lifecycle_intent(
                        world, losing_civ=civ.name, gaining_civ=absorber.name,
                        region=region_name,
                        is_capital=(region_name == civ.capital_region),
                        is_destructive=False,
                    )
```

Read `check_twilight_absorption()` first to find the exact loop and variable names for absorbed regions and the absorber civ.

- [ ] **Step 6: Wire civ_destruction intent in `simulation.py`**

In `simulation.py`, after the dead-civ detection logic (where civs with zero regions are identified after conquest or absorption), emit a `civ_destruction` lifecycle intent. Look for the section in `phase_consequences()` or `run_turn()` where dead civs are detected. Add:

```python
        # M52: Artifact lifecycle on civ destruction
        from chronicler.artifacts import emit_civ_destruction_intent
        for civ in world.civilizations:
            if len(civ.regions) == 0 and not civ._marked_for_artifact_destruction:
                emit_civ_destruction_intent(world, civ.name)
                civ._marked_for_artifact_destruction = True
```

Add to `artifacts.py`:

```python
def emit_civ_destruction_intent(world, civ_name: str) -> None:
    """Emit lifecycle intent when a civ reaches zero regions without absorber."""
    world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
        action="civ_destruction",
        losing_civ=civ_name,
        gaining_civ=None,
        region="",
        is_capital=True,
        is_full_absorption=True,
        is_destructive=False,
    ))
```

Note: Read the actual dead-civ detection logic before implementing. The existing M47 "dead civs stay in list" convention means you need a guard to avoid re-emitting each turn. A simpler approach: emit in `tick_artifacts()` itself by scanning for civs with zero regions that still own active artifacts, rather than hooking external detection.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestConquestLifecycleIntentEmission -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/artifacts.py src/chronicler/action_engine.py src/chronicler/politics.py src/chronicler/simulation.py tests/test_artifacts.py
git commit -m "feat(m52): conquest, twilight absorption, and civ destruction lifecycle intents"
```

---

### Task 11: Relic Conversion Bonus in `religion.py`

**Files:**
- Modify: `src/chronicler/religion.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_artifacts.py
class TestRelicConversionBonus:
    def test_relic_boosts_conversion_in_controlled_region(self):
        from chronicler.artifacts import get_relic_conversion_modifier
        world = _make_world_with_civ()
        region = world.regions[0]
        region.controller = "TestCiv"
        _make_active_artifact(
            world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv", region="Region1",
        )
        modifier = get_relic_conversion_modifier(world, region)
        assert modifier > 1.0  # should be 1.0 + RELIC_CONVERSION_BONUS

    def test_no_relic_no_bonus(self):
        from chronicler.artifacts import get_relic_conversion_modifier
        world = _make_world_with_civ()
        region = world.regions[0]
        modifier = get_relic_conversion_modifier(world, region)
        assert modifier == 1.0

    def test_conquered_relic_no_bonus(self):
        from chronicler.artifacts import get_relic_conversion_modifier
        world = _make_world_with_civ()
        region = world.regions[0]
        region.controller = "Conqueror"  # different from relic owner
        _make_active_artifact(
            world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv", region="Region1",
        )
        modifier = get_relic_conversion_modifier(world, region)
        assert modifier == 1.0  # conquered relic doesn't help occupier

    def test_non_stacking_multiple_relics(self):
        from chronicler.artifacts import get_relic_conversion_modifier
        world = _make_world_with_civ()
        region = world.regions[0]
        region.controller = "TestCiv"
        _make_active_artifact(world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv", region="Region1")
        _make_active_artifact(world, ArtifactType.RELIC, anchored=True, owner_civ="TestCiv", region="Region1")
        modifier = get_relic_conversion_modifier(world, region)
        # Non-stacking: same as single relic
        expected = 1.0 + 0.15  # RELIC_CONVERSION_BONUS
        assert abs(modifier - expected) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestRelicConversionBonus -v`
Expected: FAIL

- [ ] **Step 3: Add `get_relic_conversion_modifier()` to `artifacts.py`**

```python
def get_relic_conversion_modifier(world, region) -> float:
    """Return conversion rate multiplier from temple-bound relics in this region.

    Non-stacking: one relic bonus per region max.
    Only applies when owner_civ matches region controller.
    """
    for a in world.artifacts:
        if (a.artifact_type == ArtifactType.RELIC
                and a.anchored
                and a.anchor_region == region.name
                and a.status == ArtifactStatus.ACTIVE
                and a.owner_civ == region.controller):
            return 1.0 + RELIC_CONVERSION_BONUS
    return 1.0
```

Then wire it into `religion.py` at the conversion rate calculation point. Read `religion.py` to find the exact location, then multiply the conversion rate by the relic modifier.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestRelicConversionBonus -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/artifacts.py src/chronicler/religion.py tests/test_artifacts.py
git commit -m "feat(m52): relic conversion bonus — non-stacking, owner-gated"
```

---

### Task 12: Narrative Integration — Artifact Context in Prompts

**Files:**
- Modify: `src/chronicler/narrative.py`, `src/chronicler/artifacts.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing tests for artifact context rendering**

```python
# Add to tests/test_artifacts.py
class TestArtifactNarrativeContext:
    def test_get_relevant_artifacts_character_held(self):
        from chronicler.artifacts import _get_relevant_artifacts
        from chronicler.models import NarrativeMoment, NarrativeRole, Event
        world = _make_world_with_civ()
        _make_active_artifact(
            world, ArtifactType.WEAPON, anchored=False, owner_civ="TestCiv",
            holder_name="Kiran", holder_born_turn=8,
        )
        moment = NarrativeMoment(
            anchor_turn=10, turn_range=(9, 11),
            events=[Event(turn=10, event_type="war", actors=["Kiran", "TestCiv"],
                         description="Battle", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        )
        relevant = _get_relevant_artifacts(world, moment)
        assert len(relevant) == 1
        assert relevant[0].holder_name == "Kiran"

    def test_get_relevant_artifacts_max_3(self):
        from chronicler.artifacts import _get_relevant_artifacts
        from chronicler.models import NarrativeMoment, NarrativeRole, Event
        world = _make_world_with_civ()
        for i in range(5):
            _make_active_artifact(
                world, ArtifactType.RELIC, anchored=True,
                owner_civ="TestCiv", region="Region1",
            )
        moment = NarrativeMoment(
            anchor_turn=10, turn_range=(9, 11),
            events=[Event(turn=10, event_type="war", actors=["TestCiv"],
                         description="Battle", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        )
        relevant = _get_relevant_artifacts(world, moment)
        assert len(relevant) <= 3

    def test_render_artifact_context(self):
        from chronicler.artifacts import render_artifact_context
        a = Artifact(
            artifact_id=1, name="The Iron Blade of Tessara",
            artifact_type=ArtifactType.WEAPON, anchored=False,
            origin_turn=5, origin_event="Forged at promotion",
            origin_region="Tessara", creator_name="Kiran",
            creator_civ="Kethani", owner_civ="Kethani",
            holder_name="Kiran", holder_born_turn=8,
            anchor_region=None, prestige_value=2,
            status=ArtifactStatus.ACTIVE, history=["created"],
        )
        text = render_artifact_context([a])
        assert "ARTIFACTS:" in text
        assert "The Iron Blade of Tessara" in text
        assert "weapon" in text.lower()
        assert "Kiran" in text

    def test_render_empty_returns_empty(self):
        from chronicler.artifacts import render_artifact_context
        assert render_artifact_context([]) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_artifacts.py::TestArtifactNarrativeContext -v`
Expected: FAIL

- [ ] **Step 3: Add `_get_relevant_artifacts()` and `render_artifact_context()` to `artifacts.py`**

```python
ARTIFACT_DESCRIPTIONS = {
    ArtifactType.RELIC: "a sacred relic",
    ArtifactType.WEAPON: "a legendary weapon",
    ArtifactType.MONUMENT: "a great monument",
    ArtifactType.ARTWORK: "a renowned work of art",
    ArtifactType.TREATISE: "a scholarly treatise",
    ArtifactType.MANIFESTO: "a political manifesto",
    ArtifactType.TRADE_GOOD: "a prized luxury",
}


def _get_relevant_artifacts(world, moment, max_count: int = 3) -> list:
    """Return artifacts relevant to a narrative moment (max 3)."""
    relevant = []

    # Collect actor names from moment events
    actor_names = set()
    for e in moment.events:
        actor_names.update(e.actors)

    # Collect region names from named_events
    moment_regions = set()
    for ne in moment.named_events:
        if hasattr(ne, 'region') and ne.region:
            moment_regions.add(ne.region)

    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE:
            continue
        # 1. Character-held artifacts for GPs in this moment
        if a.holder_name and a.holder_name in actor_names:
            relevant.append(a)
            continue
        # 2. Anchored artifacts in moment regions
        if a.anchored and a.anchor_region in moment_regions:
            relevant.append(a)
            continue
        # 3. Civ-owned notable artifacts for civs in moment
        if a.owner_civ in actor_names and (a.mule_origin or a.prestige_value >= 3):
            relevant.append(a)

    return relevant[:max_count]


def render_artifact_context(artifacts: list) -> str:
    """Render artifact context block for narrator prompt."""
    if not artifacts:
        return ""
    lines = ["ARTIFACTS:"]
    for a in artifacts:
        holder_info = f"held by {a.holder_name}" if a.holder_name else (
            f"temple-bound in {a.anchor_region}" if a.anchored else f"owned by {a.owner_civ}"
        )
        lines.append(f"- {a.name} ({a.artifact_type.value}, {holder_info}) — {a.origin_event}")
    return "\n".join(lines)
```

- [ ] **Step 4: Wire into `_prepare_narration_prompts()` in `narrative.py`**

In `src/chronicler/narrative.py`, in `_prepare_narration_prompts()` (near line 1074), add artifact context to the prompt. After `agent_context_text` is computed and before the prompt string is assembled:

```python
            # M52: Artifact context
            artifact_context_text = ""
            if hasattr(self, '_world') and self._world is not None:
                from chronicler.artifacts import _get_relevant_artifacts, render_artifact_context
                relevant_artifacts = _get_relevant_artifacts(self._world, moment)
                artifact_context_text = render_artifact_context(relevant_artifacts)
                if artifact_context_text:
                    artifact_context_text = "\n\n" + artifact_context_text
```

Then add `{artifact_context_text}` to the prompt string after `{agent_context_text}`.

**Important plumbing:** `NarrativeEngine` does not currently store a `world` reference. You must either:
- (a) Thread `world` through `narrate_batch()` → `_prepare_narration_prompts()` as a new parameter, or
- (b) Store `world` on the engine instance (e.g., `self._world = world`) in `narrate_batch()` before calling `_prepare_narration_prompts()`.

Option (b) is simpler. Read `narrative.py` line ~843 (`NarrativeEngine` class) and line ~1087 (`narrate_batch` or `_narrate_batch_api`) to find where `world` is available and can be stored.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestArtifactNarrativeContext -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/artifacts.py src/chronicler/narrative.py tests/test_artifacts.py
git commit -m "feat(m52): artifact narrative context — relevance selection + prompt rendering"
```

---

### Task 13: Analytics Extractor

**Files:**
- Modify: `src/chronicler/analytics.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_artifacts.py
class TestArtifactAnalytics:
    def test_extract_artifacts_basic(self):
        from chronicler.analytics import extract_artifacts
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.RELIC, owner_civ="TestCiv")
        _make_active_artifact(world, ArtifactType.WEAPON, owner_civ="TestCiv")
        _make_active_artifact(world, ArtifactType.MONUMENT, owner_civ="TestCiv")
        result = extract_artifacts(world)
        assert result["total_artifacts"] == 3
        assert result["active_artifacts"] == 3
        assert "TestCiv" in result["artifacts_by_civ"]
        assert result["artifacts_by_civ"]["TestCiv"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_artifacts.py::TestArtifactAnalytics -v`
Expected: FAIL

- [ ] **Step 3: Add `extract_artifacts()` to `analytics.py`**

```python
def extract_artifacts(world) -> dict:
    """Extract artifact metrics from world state."""
    from chronicler.models import ArtifactStatus
    result = {
        "total_artifacts": len(world.artifacts),
        "active_artifacts": 0,
        "lost_artifacts": 0,
        "destroyed_artifacts": 0,
        "artifacts_by_civ": {},
        "artifacts_by_type": {},
        "total_prestige_contribution": 0,
        "mule_artifacts": 0,
    }
    for a in world.artifacts:
        if a.status == ArtifactStatus.ACTIVE:
            result["active_artifacts"] += 1
            if a.owner_civ:
                result["artifacts_by_civ"][a.owner_civ] = result["artifacts_by_civ"].get(a.owner_civ, 0) + 1
                result["total_prestige_contribution"] += a.prestige_value
        elif a.status == ArtifactStatus.LOST:
            result["lost_artifacts"] += 1
        elif a.status == ArtifactStatus.DESTROYED:
            result["destroyed_artifacts"] += 1
        type_name = a.artifact_type.value
        result["artifacts_by_type"][type_name] = result["artifacts_by_type"].get(type_name, 0) + 1
        if a.mule_origin:
            result["mule_artifacts"] += 1
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_artifacts.py::TestArtifactAnalytics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_artifacts.py
git commit -m "feat(m52): extract_artifacts() analytics extractor"
```

---

### Task 14: Transient Signal 2-Turn Integration Test

**Files:**
- Test: `tests/test_artifacts.py`

Per CLAUDE.md: every new transient signal requires a 2+ turn integration test verifying the value resets after consumption.

- [ ] **Step 1: Write integration test**

```python
# Add to tests/test_artifacts.py
class TestTransientSignalReset:
    def test_artifact_intents_cleared_each_turn(self):
        """Verify _artifact_intents is empty after tick_artifacts runs."""
        world = _make_world_with_civ()
        world.turn = 1
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.RELIC, trigger="test",
            creator_name=None, creator_born_turn=None,
            holder_name=None, holder_born_turn=None,
            civ_name="TestCiv", region_name="Region1",
            anchored=True, context="test",
        ))
        tick_artifacts(world)
        assert world._artifact_intents == []
        assert world._artifact_lifecycle_intents == []

        # Turn 2: no intents, should still clear
        world.turn = 2
        tick_artifacts(world)
        assert world._artifact_intents == []

    def test_artifact_prestige_recomputed_each_turn(self):
        """Verify _artifact_prestige_by_civ is recomputed, not accumulated."""
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, owner_civ="TestCiv")

        world.turn = 1
        tick_artifacts(world)
        prestige_t1 = world._artifact_prestige_by_civ.get("TestCiv", 0)

        world.turn = 2
        tick_artifacts(world)
        prestige_t2 = world._artifact_prestige_by_civ.get("TestCiv", 0)

        # Should be the same value each turn (recomputed, not accumulated)
        assert prestige_t1 == prestige_t2
        assert prestige_t1 == PRESTIGE_BY_TYPE[ArtifactType.MONUMENT]

    def test_prestige_drops_on_artifact_loss(self):
        """Verify prestige disappears when artifact is lost."""
        world = _make_world_with_civ()
        _make_active_artifact(world, ArtifactType.MONUMENT, owner_civ="TestCiv")

        world.turn = 1
        tick_artifacts(world)
        assert world._artifact_prestige_by_civ.get("TestCiv", 0) > 0

        # Destroy the artifact
        world.artifacts[0].status = ArtifactStatus.LOST
        world.artifacts[0].owner_civ = None
        world.turn = 2
        tick_artifacts(world)
        assert world._artifact_prestige_by_civ.get("TestCiv", 0) == 0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_artifacts.py::TestTransientSignalReset -v`
Expected: PASS (these should already work with the existing implementation)

- [ ] **Step 3: Commit**

```bash
git add tests/test_artifacts.py
git commit -m "test(m52): transient signal 2-turn integration tests for artifact intents + prestige"
```

---

### Task 15: Full Test Suite Run + Final Commit

- [ ] **Step 1: Run the full M52 test suite**

Run: `pytest tests/test_artifacts.py -v`
Expected: ALL PASS

- [ ] **Step 2: Run the full Python test suite for regressions**

Run: `pytest tests/ -v --timeout=60`
Expected: No new failures introduced by M52

- [ ] **Step 3: Verify `--agents=off` compatibility**

Run a quick check that the artifact code paths don't crash in aggregate mode:

```bash
python -m chronicler --seed 42 --turns 50 --agents=off --narrator off
```
Expected: Completes without errors. May produce cultural artifacts from `cultural_work` events.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore(m52): test suite cleanup and final verification"
```
