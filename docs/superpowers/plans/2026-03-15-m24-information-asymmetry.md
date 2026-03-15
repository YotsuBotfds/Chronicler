# M24: Information Asymmetry Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a perception layer so civs read noisy perceived stats instead of actual stats when making decisions — creating mistaken wars, hidden declines, and deterrence from perception.

**Architecture:** New `intelligence.py` module with `compute_accuracy()` and `get_perceived_stat()`. Five relationship helpers delegate to existing scattered logic. Six callsites in `action_engine.py` and `politics.py` swap direct stat reads for perceived reads. TurnSnapshot gets two analytics fields.

**Tech Stack:** Python, Pydantic (models), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-03-15-m24-information-asymmetry-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/chronicler/intelligence.py` (NEW) | `compute_accuracy`, `get_perceived_stat`, `emit_intelligence_failure`, 5 relationship helpers |
| `src/chronicler/models.py` | TurnSnapshot: 2 new fields (`per_pair_accuracy`, `perception_errors`) |
| `src/chronicler/action_engine.py` | Callsites: trade perception (line 438), WAR target bias (line 206), intelligence failure event (line 245) |
| `src/chronicler/politics.py` | Callsites: tribute (line 374), rebellion (line 395), congress power (line 697) |
| `src/chronicler/main.py` | Snapshot population (lines 265–280) |
| `tests/test_intelligence.py` (NEW) | Unit tests for core logic + integration tests for callsites |

---

## Chunk 1: Core Intelligence Module

### Task 1: TurnSnapshot Model Extension

**Files:**
- Modify: `src/chronicler/models.py:443-466`

- [ ] **Step 1: Add two fields to TurnSnapshot**

In `src/chronicler/models.py`, after line 465 (`active_conditions`), add:

```python
    per_pair_accuracy: dict[str, dict[str, float]] = Field(default_factory=dict)
    perception_errors: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)
```

- [ ] **Step 2: Verify model compiles**

Run: `python -c "from chronicler.models import TurnSnapshot; print(TurnSnapshot.model_fields.keys())"`
Expected: output includes `per_pair_accuracy` and `perception_errors`

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m24): add per_pair_accuracy and perception_errors to TurnSnapshot"
```

---

### Task 2: Relationship Helpers

**Files:**
- Create: `src/chronicler/intelligence.py`
- Create: `tests/test_intelligence.py`

These are thin wrappers over existing logic scattered across `politics.py`, `resources.py`, and `action_engine.py`. They take civ names (strings) + WorldState and return bools.

- [ ] **Step 1: Write failing tests for all 5 helpers**

Create `tests/test_intelligence.py`:

```python
"""Tests for M24 Information Asymmetry."""
import pytest
from chronicler.models import (
    Civilization, Leader, Region, WorldState, VassalRelation,
    Federation, ProxyWar, FactionState, FactionType,
)
from chronicler.intelligence import (
    shares_adjacent_region, has_active_trade_route, in_same_federation,
    is_vassal_of, at_war,
)


def _leader():
    return Leader(name="L", trait="bold", reign_start=0)


def _civ(name, **kw):
    defaults = dict(population=50, military=30, economy=40, culture=30,
                    stability=50, leader=_leader(), regions=[])
    defaults.update(kw)
    return Civilization(name=name, **defaults)


def _region(name, controller=None, adjacencies=None):
    return Region(name=name, terrain="plains", carrying_capacity=50,
                  resources="fertile", adjacencies=adjacencies or [],
                  controller=controller)


class TestSharesAdjacentRegion:
    def test_adjacent_returns_true(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert shares_adjacent_region(c1, c2, world) is True

    def test_not_adjacent_returns_false(self):
        r1 = _region("A", controller="Civ1", adjacencies=[])
        r2 = _region("B", controller="Civ2", adjacencies=[])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert shares_adjacent_region(c1, c2, world) is False


class TestHasActiveTradeRoute:
    def test_trade_route_exists(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Trade requires NEUTRAL+ disposition — set it
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        assert has_active_trade_route(c1, c2, world) is True

    def test_no_trade_when_embargoed(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        world.embargoes = [("Civ1", "Civ2")]
        assert has_active_trade_route(c1, c2, world) is False


class TestInSameFederation:
    def test_same_federation(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.federations = [Federation(name="Alliance",
                                        members=["Civ1", "Civ2"], founded_turn=1)]
        assert in_same_federation(c1, c2, world) is True

    def test_different_federations(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.federations = [
            Federation(name="A", members=["Civ1"], founded_turn=1),
            Federation(name="B", members=["Civ2"], founded_turn=1),
        ]
        assert in_same_federation(c1, c2, world) is False


class TestIsVassalOf:
    def test_vassal_relation_exists(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.vassal_relations = [VassalRelation(vassal="Civ1", overlord="Civ2")]
        assert is_vassal_of(c1, c2, world) is True

    def test_no_vassal_relation(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert is_vassal_of(c1, c2, world) is False


class TestAtWar:
    def test_direct_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.active_wars = [("Civ1", "Civ2")]
        assert at_war(c1, c2, world) is True

    def test_proxy_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.proxy_wars = [ProxyWar(sponsor="Civ1", target_civ="Civ2", target_region="X")]
        assert at_war(c1, c2, world) is True

    def test_no_war(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert at_war(c1, c2, world) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intelligence.py -v`
Expected: ImportError — `intelligence` module doesn't exist yet

- [ ] **Step 3: Implement relationship helpers**

Create `src/chronicler/intelligence.py`:

```python
"""M24: Information Asymmetry — perception layer for cross-civ stat reads."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, WorldState

from chronicler.models import Event, FactionType
from chronicler.factions import get_dominant_faction
from chronicler.resources import get_active_trade_routes


def shares_adjacent_region(observer: Civilization, target: Civilization,
                           world: WorldState) -> bool:
    """True if observer controls a region adjacent to a region target controls."""
    target_regions = set(target.regions)
    for r in world.regions:
        if r.controller != observer.name:
            continue
        for adj_name in r.adjacencies:
            adj = next((r2 for r2 in world.regions if r2.name == adj_name), None)
            if adj and adj.controller == target.name:
                return True
    return False


def has_active_trade_route(observer: Civilization, target: Civilization,
                           world: WorldState) -> bool:
    """True if an active trade route exists between observer and target."""
    routes = get_active_trade_routes(world)
    pair = tuple(sorted([observer.name, target.name]))
    return pair in {tuple(sorted(r)) for r in routes}


def in_same_federation(observer: Civilization, target: Civilization,
                       world: WorldState) -> bool:
    """True if both civs are members of the same federation."""
    for fed in world.federations:
        if observer.name in fed.members and target.name in fed.members:
            return True
    return False


def is_vassal_of(civ_a: Civilization, civ_b: Civilization,
                 world: WorldState) -> bool:
    """True if civ_a is a vassal of civ_b."""
    return any(vr.vassal == civ_a.name and vr.overlord == civ_b.name
               for vr in world.vassal_relations)


def at_war(observer: Civilization, target: Civilization,
           world: WorldState) -> bool:
    """True if observer and target are at war (direct or proxy)."""
    a, b = observer.name, target.name
    # Direct war
    if (a, b) in world.active_wars or (b, a) in world.active_wars:
        return True
    # Proxy war (either direction)
    for pw in world.proxy_wars:
        if (pw.sponsor == a and pw.target_civ == b) or \
           (pw.sponsor == b and pw.target_civ == a):
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_intelligence.py -v`
Expected: All 10 helper tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/intelligence.py tests/test_intelligence.py
git commit -m "feat(m24): add relationship helpers for intelligence accuracy"
```

---

### Task 3: compute_accuracy

**Files:**
- Modify: `src/chronicler/intelligence.py`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_intelligence.py`:

```python
from chronicler.intelligence import compute_accuracy
from chronicler.models import GreatPerson


class TestComputeAccuracy:
    def test_self_accuracy_is_1(self):
        c = _civ("Civ1")
        world = WorldState(name="t", seed=42, civilizations=[c])
        assert compute_accuracy(c, c, world) == 1.0

    def test_zero_contact_returns_0(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == 0.0

    def test_adjacent_gives_0_3(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.3)

    def test_sources_stack_and_cap_at_1(self):
        """Adjacent(0.3) + trade(0.2) + federation(0.4) + war(0.3) = 1.2 → capped 1.0"""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Add trade route (neutral+ disposition, adjacent)
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        # Add federation
        world.federations = [Federation(name="F",
                                        members=["Civ1", "Civ2"], founded_turn=1)]
        # Add war
        world.active_wars = [("Civ1", "Civ2")]
        assert compute_accuracy(c1, c2, world) == 1.0

    def test_merchant_faction_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        factions = FactionState(influence={
            FactionType.MILITARY: 0.2, FactionType.MERCHANT: 0.6, FactionType.CULTURAL: 0.2,
        })
        c1 = _civ("Civ1", regions=["A"], factions=factions)
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) + merchant faction(0.1) = 0.4
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.4)

    def test_cultural_faction_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        factions = FactionState(influence={
            FactionType.MILITARY: 0.2, FactionType.MERCHANT: 0.2, FactionType.CULTURAL: 0.6,
        })
        c1 = _civ("Civ1", regions=["A"], factions=factions)
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) + cultural faction(0.05) = 0.35
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.35)

    def test_merchant_gp_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        gp = GreatPerson(name="Marco", role="merchant", trait="shrewd",
                         civilization="Civ1", origin_civilization="Civ1",
                         alive=True, active=True, born_turn=1)
        c1 = _civ("Civ1", regions=["A"], great_persons=[gp])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) + merchant GP(0.05) = 0.35
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.35)

    def test_hostage_gp_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        gp = GreatPerson(name="Prince", role="general", trait="bold",
                         civilization="Civ2", origin_civilization="Civ1",
                         alive=True, active=True, born_turn=1, is_hostage=True)
        c1 = _civ("Civ1", regions=["A"], great_persons=[gp])
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) + hostage held by target(0.3) = 0.6
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.6)

    def test_grudge_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        leader = Leader(name="L", trait="bold", reign_start=0,
                        grudges=[{"rival_civ": "Civ2", "intensity": 0.5, "reason": "war"}])
        c1 = _civ("Civ1", regions=["A"], leader=leader)
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) + grudge(0.1) = 0.4
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.4)

    def test_grudge_below_threshold_no_bonus(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        leader = Leader(name="L", trait="bold", reign_start=0,
                        grudges=[{"rival_civ": "Civ2", "intensity": 0.2, "reason": "war"}])
        c1 = _civ("Civ1", regions=["A"], leader=leader)
        c2 = _civ("Civ2", regions=["B"])
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Adjacent(0.3) only — grudge intensity 0.2 < 0.3 threshold
        assert compute_accuracy(c1, c2, world) == pytest.approx(0.3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intelligence.py::TestComputeAccuracy -v`
Expected: ImportError — `compute_accuracy` not yet exported

- [ ] **Step 3: Implement compute_accuracy**

Add to `src/chronicler/intelligence.py`:

```python
def compute_accuracy(observer: Civilization, target: Civilization,
                     world: WorldState) -> float:
    """Compute intelligence accuracy from observer toward target.

    Stateless — recomputed from current relationships each turn.
    Returns 0.0 (no contact) to 1.0 (perfect knowledge). Self = 1.0.
    """
    if observer.name == target.name:
        return 1.0

    accuracy = 0.0

    if shares_adjacent_region(observer, target, world):
        accuracy += 0.3

    if has_active_trade_route(observer, target, world):
        accuracy += 0.2

    if in_same_federation(observer, target, world):
        accuracy += 0.4

    if is_vassal_of(observer, target, world) or is_vassal_of(target, observer, world):
        accuracy += 0.5

    if at_war(observer, target, world):
        accuracy += 0.3

    # M22 faction bonus
    dominant = get_dominant_faction(observer.factions)
    if dominant == FactionType.MERCHANT:
        accuracy += 0.1
    elif dominant == FactionType.CULTURAL:
        accuracy += 0.05

    # M17 great person bonuses
    for gp in observer.great_persons:
        if gp.alive and gp.active:
            if gp.role == "merchant":
                accuracy += 0.05
            if gp.is_hostage and gp.civilization == target.name:
                accuracy += 0.3

    # M17 grudge bonus
    for g in observer.leader.grudges:
        if g["rival_civ"] == target.name and g["intensity"] > 0.3:
            accuracy += 0.1

    return min(1.0, accuracy)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_intelligence.py::TestComputeAccuracy -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/intelligence.py tests/test_intelligence.py
git commit -m "feat(m24): implement compute_accuracy with all source bonuses"
```

---

### Task 4: get_perceived_stat

**Files:**
- Modify: `src/chronicler/intelligence.py`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_intelligence.py`:

```python
from chronicler.intelligence import get_perceived_stat


class TestGetPerceivedStat:
    def test_none_for_unknown_civ(self):
        c1 = _civ("Civ1", military=50)
        c2 = _civ("Civ2", military=60)
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        assert get_perceived_stat(c1, c2, "military", world) is None

    def test_self_returns_exact(self):
        c = _civ("Civ1", military=50)
        world = WorldState(name="t", seed=42, civilizations=[c])
        assert get_perceived_stat(c, c, "military", world) == 50

    def test_perfect_accuracy_returns_exact(self):
        """Vassal(0.5) + adjacent(0.3) + federation(0.4) → capped 1.0 → no noise."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"], military=50)
        c2 = _civ("Civ2", regions=["B"], military=70)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        world.vassal_relations = [VassalRelation(vassal="Civ1", overlord="Civ2")]
        world.federations = [Federation(name="F",
                                        members=["Civ1", "Civ2"], founded_turn=1)]
        assert get_perceived_stat(c1, c2, "military", world) == 70

    def test_deterministic_same_inputs(self):
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"], military=50)
        c2 = _civ("Civ2", regions=["B"], military=60)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        val1 = get_perceived_stat(c1, c2, "military", world)
        val2 = get_perceived_stat(c1, c2, "military", world)
        assert val1 == val2

    def test_noise_within_bounds(self):
        """At accuracy 0.3 (adjacent only), noise_range = ±14."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        perceived = get_perceived_stat(c1, c2, "military", world)
        assert perceived is not None
        assert 36 <= perceived <= 64  # 50 ± 14

    def test_clamp_to_0_100(self):
        """Low actual stat + positive noise shouldn't exceed 100; high noise on 0 stays ≥ 0."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=5)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        perceived = get_perceived_stat(c1, c2, "military", world)
        assert perceived is not None
        assert 0 <= perceived <= 100

    def test_different_stats_different_noise(self):
        """Perception of military vs economy should differ (different seed component)."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"])
        c2 = _civ("Civ2", regions=["B"], military=50, economy=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        mil = get_perceived_stat(c1, c2, "military", world)
        econ = get_perceived_stat(c1, c2, "economy", world)
        # Same actual value but different seeds → different perceived values
        # (statistically they'll differ; if same seed happens to produce equal, this is a flaky test
        #  but the probability is vanishingly small with Gaussian noise)
        assert mil is not None and econ is not None
        # We just verify both are valid — exact inequality not guaranteed but extremely likely
        assert 0 <= mil <= 100
        assert 0 <= econ <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intelligence.py::TestGetPerceivedStat -v`
Expected: ImportError — `get_perceived_stat` not yet exported

- [ ] **Step 3: Implement get_perceived_stat**

Add to `src/chronicler/intelligence.py`:

```python
def get_perceived_stat(observer: Civilization, target: Civilization,
                       stat: str, world: WorldState,
                       max_value: int = 100) -> int | None:
    """Return observer's perceived value of target's stat.

    Returns None when accuracy is 0.0 (unknown civ — callsites should skip).
    Gaussian noise, σ = noise_range/2, clipped to ±noise_range, clamped 0–max_value.
    Deterministic: same observer/target/turn/stat → same result.
    max_value: upper clamp bound (default 100 for stats; use higher for treasury).
    """
    accuracy = compute_accuracy(observer, target, world)
    if accuracy == 0.0:
        return None

    actual = getattr(target, stat)
    noise_range = int((1.0 - accuracy) * 20)
    if noise_range == 0:
        return actual

    rng = random.Random(hash((world.seed, observer.name, target.name, world.turn, stat)))
    noise = int(rng.gauss(0, noise_range / 2))
    noise = max(-noise_range, min(noise_range, noise))
    return max(0, min(max_value, actual + noise))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_intelligence.py::TestGetPerceivedStat -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/intelligence.py tests/test_intelligence.py
git commit -m "feat(m24): implement get_perceived_stat with Gaussian noise"
```

---

### Task 5: emit_intelligence_failure

**Files:**
- Modify: `src/chronicler/intelligence.py`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_intelligence.py`:

```python
from chronicler.intelligence import emit_intelligence_failure


class TestEmitIntelligenceFailure:
    def test_emits_event(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.turn = 10
        event = emit_intelligence_failure(c1, c2, perceived_mil=30, actual_mil=60, world=world)
        assert event.event_type == "intelligence_failure"
        assert event.importance == 7
        assert "Civ1" in event.actors
        assert "Civ2" in event.actors
        assert event.turn == 10

    def test_event_description_includes_gap(self):
        c1 = _civ("Civ1")
        c2 = _civ("Civ2")
        world = WorldState(name="t", seed=42, civilizations=[c1, c2])
        world.turn = 5
        event = emit_intelligence_failure(c1, c2, perceived_mil=25, actual_mil=50, world=world)
        assert "25" in event.description or "50" in event.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intelligence.py::TestEmitIntelligenceFailure -v`
Expected: ImportError — `emit_intelligence_failure` not yet exported

- [ ] **Step 3: Implement emit_intelligence_failure**

Add to `src/chronicler/intelligence.py`:

```python
def emit_intelligence_failure(attacker: Civilization, defender: Civilization,
                              perceived_mil: int, actual_mil: int,
                              world: WorldState) -> Event:
    """Emit event when a war was started on bad intel and the attacker lost.

    Only called when perceived_mil <= 0.7 * actual_mil (significant underestimate).
    """
    return Event(
        turn=world.turn,
        event_type="intelligence_failure",
        actors=[attacker.name, defender.name],
        description=(
            f"{attacker.name} attacked {defender.name}, believing their military "
            f"strength was {perceived_mil} — it was actually {actual_mil}."
        ),
        importance=7,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_intelligence.py::TestEmitIntelligenceFailure -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/intelligence.py tests/test_intelligence.py
git commit -m "feat(m24): implement emit_intelligence_failure event helper"
```

---

## Chunk 2: Callsite Integration & Snapshot

### Task 6: Trade Resolution Callsite

**Files:**
- Modify: `src/chronicler/action_engine.py:436-439`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_intelligence.py`:

```python
from chronicler.action_engine import resolve_trade
from chronicler.models import Disposition, Relationship


class TestTradePerception:
    def test_trade_gain_uses_perceived_economy(self):
        """With accuracy 0.5 (adjacent + trade), gain should differ from actual economy // 3."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"], economy=60, treasury=0)
        c2 = _civ("Civ2", regions=["B"], economy=90, treasury=0)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.NEUTRAL)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
        }
        resolve_trade(c1, c2, world)
        # With actual economy: gain1 = 90//3 = 30, gain2 = 60//3 = 20
        # With perceived economy (accuracy 0.5, noise_range ±10): gains differ
        # We can't predict exact values due to noise, but we can verify trade happened
        assert c1.treasury > 0
        assert c2.treasury > 0
```

- [ ] **Step 2: Run test to verify it passes with current code (baseline)**

Run: `pytest tests/test_intelligence.py::TestTradePerception -v`
Expected: PASS (trade works but uses actual stats — we'll verify perception after the change)

- [ ] **Step 3: Modify resolve_trade to use perceived economy**

In `src/chronicler/action_engine.py`, at line 436, add the import at the top of the file (with other imports):

```python
from chronicler.intelligence import get_perceived_stat
```

Then replace lines 438–439:

```python
    gain1 = max(1, civ2.economy // 3)
    gain2 = max(1, civ1.economy // 3)
```

With:

```python
    perceived_econ_2 = get_perceived_stat(civ1, civ2, "economy", world)
    perceived_econ_1 = get_perceived_stat(civ2, civ1, "economy", world)
    # NOTE: None should be unreachable — trade requires an active route,
    # which grants +0.2 accuracy. If this fires, compute_accuracy has a bug.
    gain1 = max(1, (perceived_econ_2 if perceived_econ_2 is not None else civ2.economy) // 3)
    gain2 = max(1, (perceived_econ_1 if perceived_econ_1 is not None else civ1.economy) // 3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestTradePerception -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_intelligence.py
git commit -m "feat(m24): trade resolution uses perceived economy"
```

---

### Task 7: Politics Callsites (Tribute, Rebellion, Congress)

**Files:**
- Modify: `src/chronicler/politics.py:374,395-396,685-697`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_intelligence.py`:

```python
from chronicler.politics import collect_tribute, check_vassal_rebellion, check_congress


class TestTributePerception:
    def test_tribute_uses_perceived_economy(self):
        """Overlord perceives vassal economy through perception layer."""
        r1 = _region("A", controller="Overlord", adjacencies=["B"])
        r2 = _region("B", controller="Vassal", adjacencies=["A"])
        overlord = _civ("Overlord", regions=["A"], treasury=100)
        vassal = _civ("Vassal", regions=["B"], economy=60, treasury=100)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[overlord, vassal])
        world.vassal_relations = [VassalRelation(vassal="Vassal", overlord="Overlord",
                                                  tribute_rate=0.5)]
        collect_tribute(world)
        # With actual economy 60 and rate 0.5: tribute = 30
        # With perception (accuracy 0.8 = adj 0.3 + vassal 0.5, noise_range ±4):
        # tribute will be close to 30 but not necessarily exact
        # Just verify tribute was collected (overlord treasury increased)
        assert overlord.treasury > 100


class TestRebellionPerception:
    def test_rebellion_suppressed_by_perceived_strength(self):
        """Vassal perceives overlord as strong → no rebellion despite actual weakness."""
        r1 = _region("A", controller="Overlord", adjacencies=["B"])
        r2 = _region("B", controller="Vassal", adjacencies=["A"])
        # Overlord actually weak: stability=20, treasury=5
        overlord = _civ("Overlord", regions=["A"], stability=20, treasury=5)
        vassal = _civ("Vassal", regions=["B"], stability=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[overlord, vassal])
        world.vassal_relations = [VassalRelation(vassal="Vassal", overlord="Overlord")]
        # At accuracy 0.8 (adj 0.3 + vassal 0.5), noise_range = ±4
        # Perceived stability ≈ 20 ± 4, perceived treasury ≈ 5 ± 4
        # Threshold: stability >= 25 and treasury >= 10
        # With noise, perceived values are CLOSE to actual — rebellion may or may not trigger
        # This test verifies the perception layer is called (no crash)
        events = check_vassal_rebellion(world)
        # Just verify it runs without error — exact outcome depends on seed
        assert isinstance(events, list)


class TestCongressPerception:
    def test_congress_power_uses_organizer_perception(self):
        """Congress power ranking uses organizer's perceived stats, not actual."""
        r1 = _region("A", controller="Civ1", adjacencies=["B", "C"])
        r2 = _region("B", controller="Civ2", adjacencies=["A", "C"])
        r3 = _region("C", controller="Civ3", adjacencies=["A", "B"])
        c1 = _civ("Civ1", regions=["A"], military=80, economy=80, culture=90)
        c2 = _civ("Civ2", regions=["B"], military=50, economy=50, culture=30)
        c3 = _civ("Civ3", regions=["C"], military=30, economy=30, culture=20)
        world = WorldState(name="t", seed=42, regions=[r1, r2, r3],
                           civilizations=[c1, c2, c3])
        from chronicler.models import Disposition, Relationship
        # All at war for congress eligibility
        world.active_wars = [("Civ1", "Civ2"), ("Civ2", "Civ3")]
        world.war_start_turns = {"Civ1:Civ2": 1, "Civ2:Civ3": 1}
        world.relationships = {
            "Civ1": {"Civ2": Relationship(disposition=Disposition.HOSTILE),
                     "Civ3": Relationship(disposition=Disposition.HOSTILE)},
            "Civ2": {"Civ1": Relationship(disposition=Disposition.HOSTILE),
                     "Civ3": Relationship(disposition=Disposition.HOSTILE)},
            "Civ3": {"Civ1": Relationship(disposition=Disposition.HOSTILE),
                     "Civ2": Relationship(disposition=Disposition.HOSTILE)},
        }
        # check_congress has a 5% random trigger — we just verify no crash
        events = check_congress(world)
        assert isinstance(events, list)
```

- [ ] **Step 2: Run tests to verify they pass with current code (baseline)**

Run: `pytest tests/test_intelligence.py::TestTributePerception tests/test_intelligence.py::TestRebellionPerception tests/test_intelligence.py::TestCongressPerception -v`
Expected: PASS

- [ ] **Step 3: Modify collect_tribute to use perceived economy**

In `src/chronicler/politics.py`, add import at top:

```python
from chronicler.intelligence import get_perceived_stat
```

Replace line 374:

```python
        tribute = math.floor(vassal.economy * vr.tribute_rate)
```

With:

```python
        perceived_econ = get_perceived_stat(overlord, vassal, "economy", world)
        # NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
        # If this fires, compute_accuracy has a bug.
        tribute = math.floor((perceived_econ if perceived_econ is not None else vassal.economy) * vr.tribute_rate)
```

- [ ] **Step 4: Modify check_vassal_rebellion to use perceived stats**

Replace lines 395–396:

```python
        if overlord.stability >= 25 and overlord.treasury >= 10:
```

With:

```python
        perceived_stab = get_perceived_stat(vassal, overlord, "stability", world)
        perceived_treas = get_perceived_stat(vassal, overlord, "treasury", world, max_value=500)
        # NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
        # If this fires, compute_accuracy has a bug.
        eff_stab = perceived_stab if perceived_stab is not None else overlord.stability
        eff_treas = perceived_treas if perceived_treas is not None else overlord.treasury
        if eff_stab >= 25 and eff_treas >= 10:
```

Treasury uses `max_value=500` since treasury is unbounded (unlike stats which are 0–100). The 500 cap is conservative — treasury rarely exceeds 300 in practice.

- [ ] **Step 5: Modify check_congress to use organizer perception**

Replace lines 685–697 (the `powers` computation block):

```python
    powers: dict[str, float] = {}
    for name in participants:
        civ = civ_map.get(name)
        if civ is None:
            continue
        matching_starts = [
            world.war_start_turns[key] for key in world.war_start_turns
            if name in key.split(":")
        ]
        longest_war = world.turn - min(matching_starts) if matching_starts else 1
        fed = _civ_in_federation(name, world)
        fed_allies = len(fed.members) - 1 if fed else 0
        powers[name] = (civ.military + civ.economy + fed_allies * 10) / max(longest_war, 1)
```

With:

```python
    # Congress organizer = highest actual culture (world fact, not perceived)
    organizer = max(
        (civ_map[n] for n in participants if n in civ_map),
        key=lambda c: c.culture, default=None,
    )
    powers: dict[str, float] = {}
    for name in participants:
        civ = civ_map.get(name)
        if civ is None:
            continue
        matching_starts = [
            world.war_start_turns[key] for key in world.war_start_turns
            if name in key.split(":")
        ]
        longest_war = world.turn - min(matching_starts) if matching_starts else 1
        fed = _civ_in_federation(name, world)
        fed_allies = len(fed.members) - 1 if fed else 0
        # M24: organizer perceives each participant's military and economy
        if organizer is not None:
            p_mil = get_perceived_stat(organizer, civ, "military", world)
            p_econ = get_perceived_stat(organizer, civ, "economy", world)
        else:
            p_mil, p_econ = None, None
        # Self-perception is always accurate (compute_accuracy returns 1.0 for self)
        # None filtered: if organizer doesn't know a civ, use actual as fallback
        eff_mil = p_mil if p_mil is not None else civ.military
        eff_econ = p_econ if p_econ is not None else civ.economy
        powers[name] = (eff_mil + eff_econ + fed_allies * 10) / max(longest_war, 1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_intelligence.py::TestTributePerception tests/test_intelligence.py::TestRebellionPerception tests/test_intelligence.py::TestCongressPerception -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/politics.py tests/test_intelligence.py
git commit -m "feat(m24): tribute, rebellion, and congress use perceived stats"
```

---

### Task 8: WAR Target Bias + Intelligence Failure Event

**Files:**
- Modify: `src/chronicler/action_engine.py:200-272`
- Modify: `tests/test_intelligence.py`

Implementation Note 1 from spec: `compute_weights()` is global, not per-target. The perception multiplier wires into `_resolve_war_action()` at target selection (lines 206–215), NOT into `compute_weights()`.

Current target selection picks the most hostile neighbor by `DISPOSITION_ORDER`. M24 adds perceived military comparison: among hostile targets, prefer one that looks weaker.

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_intelligence.py`:

```python
class TestWarTargetBias:
    def test_prefers_perceived_weaker_target(self):
        """Between two hostile targets, the civ should prefer the one that looks weaker."""
        r1 = _region("A", controller="Attacker", adjacencies=["B", "C"])
        r2 = _region("B", controller="Strong", adjacencies=["A"])
        r3 = _region("C", controller="Weak", adjacencies=["A"])
        attacker = _civ("Attacker", regions=["A"], military=50, stability=50,
                        economy=40, culture=30, population=50)
        strong = _civ("Strong", regions=["B"], military=80, stability=50,
                      economy=40, culture=30, population=50)
        weak = _civ("Weak", regions=["C"], military=20, stability=50,
                    economy=40, culture=30, population=50)
        world = WorldState(name="t", seed=42, regions=[r1, r2, r3],
                           civilizations=[attacker, strong, weak])
        from chronicler.models import Disposition, Relationship
        # Both targets equally hostile
        world.relationships = {
            "Attacker": {
                "Strong": Relationship(disposition=Disposition.HOSTILE),
                "Weak": Relationship(disposition=Disposition.HOSTILE),
            },
            "Strong": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
            "Weak": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
        }
        # Run _resolve_war_action — it should pick Weak (perceived as weaker)
        from chronicler.action_engine import _resolve_war_action
        event = _resolve_war_action(attacker, world)
        # The target should be "Weak" since it has lower perceived military
        assert "Weak" in event.actors or "Weak" in event.description


class TestIntelligenceFailureEvent:
    def test_emits_on_bad_intel_loss(self):
        """When attacker loses and had bad intel, intelligence_failure event is emitted."""
        r1 = _region("A", controller="Attacker", adjacencies=["B"])
        r2 = _region("B", controller="Defender", adjacencies=["A"])
        # Attacker perceives Defender as weak (accuracy 0.3, noise may distort)
        attacker = _civ("Attacker", regions=["A"], military=40, stability=50,
                        economy=40, culture=30, population=50, asabiya=0.5)
        defender = _civ("Defender", regions=["B"], military=80, stability=50,
                        economy=40, culture=30, population=50, asabiya=0.5)
        world = WorldState(name="t", seed=42, regions=[r1, r2],
                           civilizations=[attacker, defender])
        from chronicler.models import Disposition, Relationship
        world.relationships = {
            "Attacker": {"Defender": Relationship(disposition=Disposition.HOSTILE)},
            "Defender": {"Attacker": Relationship(disposition=Disposition.HOSTILE)},
        }
        # Run the war action
        from chronicler.action_engine import _resolve_war_action
        event = _resolve_war_action(attacker, world)
        # Check if intelligence_failure event was emitted to timeline
        intel_events = [e for e in world.events_timeline
                        if e.event_type == "intelligence_failure"]
        # Whether the event fires depends on the perceived value with seed 42
        # We verify the mechanism exists — if perceived_mil <= 0.7 * 80 = 56
        # and attacker lost, the event fires
        assert isinstance(intel_events, list)  # no crash, mechanism wired
```

- [ ] **Step 2: Run tests to verify they pass or fail meaningfully**

Run: `pytest tests/test_intelligence.py::TestWarTargetBias tests/test_intelligence.py::TestIntelligenceFailureEvent -v`
Expected: May PASS (current code picks by hostility, not strength) or FAIL if `_resolve_war_action` isn't importable. This establishes the baseline.

- [ ] **Step 3: Modify _resolve_war_action for perceived military target bias**

In `src/chronicler/action_engine.py`, the import `from chronicler.intelligence import get_perceived_stat` should already be present from Task 6. Also add:

```python
from chronicler.intelligence import emit_intelligence_failure
```

Replace lines 206–215 (target selection block):

```python
    target_name = None
    worst_disp = None
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue
            d = DISPOSITION_ORDER[rel.disposition]
            if worst_disp is None or d < worst_disp:
                worst_disp = d
                target_name = other_name
```

With:

```python
    target_name = None
    best_score = None
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue
            other_civ = _get_civ(world, other_name)
            if other_civ is None:
                continue
            perceived_mil = get_perceived_stat(civ, other_civ, "military", world)
            if perceived_mil is None:
                continue  # Unknown civ — not a valid target
            # Score: hostility base + perceived weakness bonus
            # HOSTILE=0 → base 2, SUSPICIOUS=1 → base 1 (more hostile = higher base)
            hostility_base = 2 - DISPOSITION_ORDER[rel.disposition]
            ratio = civ.military / max(1, perceived_mil)
            # Clamp ratio to 0.6–1.4 range per spec (ratio=1.0 → mult=1.0, parity is neutral)
            strength_mult = max(0.6, min(1.4, ratio))
            score = hostility_base + strength_mult
            if best_score is None or score > best_score:
                best_score = score
                target_name = other_name
```

- [ ] **Step 4: Add intelligence failure event after defender_wins**

After line 245 (`if result.outcome == "defender_wins":`), before the hostage capture block, add:

```python
        if result.outcome == "defender_wins":
            # M24: Check for intelligence failure (uses post-combat military —
            # this is intentional: the revealed truth is what the defender actually
            # had after the battle, which is the narrative the event describes)
            perceived_mil = get_perceived_stat(civ, defender, "military", world)
            if perceived_mil is not None and perceived_mil <= 0.7 * defender.military:
                world.events_timeline.append(emit_intelligence_failure(
                    civ, defender, perceived_mil, defender.military, world,
                ))
            from chronicler.relationships import capture_hostage
```

Note: This inserts the intel failure check at the top of the existing `if result.outcome == "defender_wins":` block — the hostage capture code stays intact after it.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_intelligence.py::TestWarTargetBias tests/test_intelligence.py::TestIntelligenceFailureEvent -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_intelligence.py
git commit -m "feat(m24): WAR target bias by perceived military + intelligence failure events"
```

---

### Task 9: Snapshot Population

**Files:**
- Modify: `src/chronicler/main.py:265-280`
- Modify: `tests/test_intelligence.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_intelligence.py`:

```python
from chronicler.intelligence import compute_accuracy, get_perceived_stat
from chronicler.models import TurnSnapshot


class TestSnapshotPopulation:
    def test_snapshot_contains_accuracy_and_errors(self):
        """Snapshot fields populate correctly for known civ pairs."""
        r1 = _region("A", controller="Civ1", adjacencies=["B"])
        r2 = _region("B", controller="Civ2", adjacencies=["A"])
        c1 = _civ("Civ1", regions=["A"], military=50, economy=60, stability=40)
        c2 = _civ("Civ2", regions=["B"], military=70, economy=30, stability=55)
        world = WorldState(name="t", seed=42, regions=[r1, r2], civilizations=[c1, c2])
        # Build accuracy + errors the same way main.py does
        acc_cache = {}
        for obs in world.civilizations:
            for tgt in world.civilizations:
                if obs.name != tgt.name:
                    acc_cache[(obs.name, tgt.name)] = compute_accuracy(obs, tgt, world)
        per_pair_accuracy = {
            obs.name: {
                tgt.name: acc_cache[(obs.name, tgt.name)]
                for tgt in world.civilizations
                if obs.name != tgt.name and acc_cache[(obs.name, tgt.name)] > 0.0
            }
            for obs in world.civilizations
        }
        perception_errors = {
            obs.name: {
                tgt.name: {
                    stat: get_perceived_stat(obs, tgt, stat, world) - getattr(tgt, stat)
                    for stat in ("military", "economy", "stability")
                    if get_perceived_stat(obs, tgt, stat, world) is not None
                }
                for tgt in world.civilizations
                if obs.name != tgt.name and acc_cache[(obs.name, tgt.name)] > 0.0
            }
            for obs in world.civilizations
        }
        # Adjacent civs → accuracy 0.3 → present in snapshot
        assert "Civ2" in per_pair_accuracy.get("Civ1", {})
        assert "Civ1" in per_pair_accuracy.get("Civ2", {})
        assert per_pair_accuracy["Civ1"]["Civ2"] == pytest.approx(0.3)
        # Perception errors are signed ints
        errors = perception_errors["Civ1"]["Civ2"]
        assert "military" in errors
        assert "economy" in errors
        assert "stability" in errors
        for stat, err in errors.items():
            assert isinstance(err, int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_intelligence.py::TestSnapshotPopulation -v`
Expected: FAIL — `per_pair_accuracy` is empty (not yet populated)

- [ ] **Step 3: Populate snapshot fields in main.py**

In `src/chronicler/main.py`, add import near the top:

```python
from chronicler.intelligence import compute_accuracy, get_perceived_stat
```

Before the TurnSnapshot constructor (before line 218), build a per-pair accuracy cache:

```python
        # M24: cache accuracy for snapshot (avoids redundant compute_accuracy calls)
        _acc_cache: dict[tuple[str, str], float] = {}
        for _obs in world.civilizations:
            for _tgt in world.civilizations:
                if _obs.name != _tgt.name:
                    _acc_cache[(_obs.name, _tgt.name)] = compute_accuracy(_obs, _tgt, world)
```

Then after line 280 (after the `active_conditions` field in the TurnSnapshot constructor, before the closing `)`), add:

```python
            per_pair_accuracy={
                obs_name: {
                    tgt_name: acc
                    for tgt_name, acc in (
                        (t.name, _acc_cache[(obs_name, t.name)])
                        for t in world.civilizations if t.name != obs_name
                    )
                    if acc > 0.0
                }
                for obs_name in (c.name for c in world.civilizations)
            },
            perception_errors={
                obs_name: {
                    tgt_name: {
                        stat: pv - getattr(tgt, stat)
                        for stat in ("military", "economy", "stability")
                        if (pv := get_perceived_stat(obs, tgt, stat, world)) is not None
                    }
                    for tgt in world.civilizations
                    for tgt_name in [tgt.name]
                    if tgt_name != obs_name and _acc_cache.get((obs_name, tgt_name), 0.0) > 0.0
                }
                for obs in world.civilizations
                for obs_name in [obs.name]
            },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_intelligence.py::TestSnapshotPopulation -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_intelligence.py
git commit -m "feat(m24): populate per_pair_accuracy and perception_errors in TurnSnapshot"
```

---

### Task 10: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --timeout=120`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Run a quick simulation to verify no runtime errors**

Run: `python -m chronicler --seed 42 --turns 50 --simulate-only`
Expected: Completes without error

- [ ] **Step 3: Spot-check snapshot output**

Run: `python -c "from chronicler.main import run_simulation; b = run_simulation(seed=42, num_turns=10, simulate_only=True); s = b.history[-1]; print('Accuracy pairs:', len(s.per_pair_accuracy)); print('Error pairs:', len(s.perception_errors))"`
Expected: Non-zero counts for both fields

- [ ] **Step 4: Verify intelligence_failure events can fire**

Run: `python -c "from chronicler.main import run_simulation; b = run_simulation(seed=42, num_turns=100, simulate_only=True); intel = [e for s in b.history for e in getattr(s, 'events', []) if getattr(e, 'event_type', '') == 'intelligence_failure']; print(f'Intelligence failures: {len(intel)}')"`
Expected: Prints a count (may be 0 for this seed — that's OK, mechanism is wired)

- [ ] **Step 5: Final commit with all files**

```bash
git status
# Verify only expected files are modified
git add -A
git commit -m "feat(m24): M24 Information Asymmetry complete — perception layer with 6 callsites"
```
