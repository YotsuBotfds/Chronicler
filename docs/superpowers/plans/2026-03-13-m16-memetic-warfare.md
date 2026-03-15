# M16: Memetic Warfare Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cultural values, regional identity, and ideological movements mechanically load-bearing — affecting disposition drift, territorial stability, and cross-border conflict.

**Architecture:** Two new modules (`culture.py` for culture-as-property, `movements.py` for ideas-as-entities) plus model extensions, simulation phase hooks, and action engine integration. Pure Python simulation — no LLM calls.

**Tech Stack:** Python 3.12, Pydantic v2 models, hashlib.sha256 for deterministic rolls, pytest for testing.

**Spec:** `docs/superpowers/specs/2026-03-13-m16-memetic-warfare-design.md`

**M14 status:** M14 (Political Topology) is fully merged to main (516 tests). All M14 fields (`vassal_relations`, `federations`, `capital_region`, etc.) are present. No guards needed.

**M15 status:** M15 (Living World) is fully merged (628 tests). `TechEra.INFORMATION` exists in `ERA_BONUSES`. `terrain.py`, `infrastructure.py`, `climate.py`, `exploration.py` are all present. `Region.adjacencies` always exists.

**P1 status:** P1 (stat migration 0-100 scale) is complete. All stats use `Field(ge=0, le=100)`. Test fixtures should use 0-100 values (e.g., `stability=50` not `stability=5`).

---

## ERRATA — Read Before Implementing

This plan was written before M14, M15, and P1 were complete. All three are now merged. The following corrections apply throughout the plan. **Apply these corrections as you encounter the affected sections.**

### E1: Action resolution uses `@register_action` + `ACTION_REGISTRY`, NOT `_resolve_action`

The plan references `_resolve_action` in `simulation.py` (Task 16 Step 4). **This function does not exist.** The actual pattern in `action_engine.py`:

```python
@register_action(ActionType.INVEST_CULTURE)
def _resolve_invest_culture(civ: Civilization, world: WorldState) -> Event:
    from chronicler.culture import resolve_invest_culture
    return resolve_invest_culture(civ, world)
```

Register INVEST_CULTURE in `action_engine.py` using the decorator, not an `elif` branch in simulation.py.

### E2: `ERA_BONUSES` uses P1-scale values — plan shows pre-P1 values

The plan's Task 14 shows `"military": 1, "economy": 2` etc. The actual values are P1-migrated:
```python
TechEra.BRONZE: {"military": 10},
TechEra.IRON: {"economy": 10},
TechEra.CLASSICAL: {"culture": 10},
TechEra.MEDIEVAL: {"military": 10},
TechEra.RENAISSANCE: {"economy": 20, "culture": 10},
TechEra.INDUSTRIAL: {"economy": 20, "military": 20},
TechEra.INFORMATION: {"culture": 10, "economy": 5},
```

When adding multiplier keys, **preserve the existing P1 values** and add the new keys alongside them. Do NOT overwrite the existing stat bonuses with the plan's pre-P1 values.

### E3: Test fixtures must use 0-100 scale stat values

Throughout the plan, test fixtures use `population=5, military=5, economy=5, culture=5, stability=5`. These are pre-P1 (1-10 scale). Replace with P1-scale values: `population=50, military=50, economy=50, culture=50, stability=50`. Also: `culture=70` for propaganda tests (not `culture=7`), `culture=80` for cultural milestone threshold tests (not `culture=8`).

### E4: `STAT_MAX` should be imported from `utils.py`

The plan hardcodes `STAT_MAX = 100` in `movements.py`. Instead: `from chronicler.utils import STAT_FLOOR` and define or import `STAT_MAX = 100` from utils if it exists there. Check `utils.py` for the correct constant name.

### E5: `TechEra.INFORMATION` exists — uncomment and include

The plan comments out `TechEra.INFORMATION` in `_ERA_BONUS` dict in movements.py. INFORMATION era is present (added by M15). Include it:
```python
TechEra.INFORMATION: 0.3,
```

### E6: `hasattr(r, 'adjacencies')` guards are unnecessary

Task 15 Step 4 and Task 16 Step 3 use `hasattr(r, 'adjacencies')`. Region always has `adjacencies: list[str]`. Use `r.adjacencies` directly.

### E7: `phase_consequences` ordering needs careful insertion

The current `phase_consequences` ordering (post-M14/M15) is:
1. Tick condition durations
2. Apply asabiya dynamics
3. Capital loss check
4. Secession check
5. Update allied turns
6. Vassal/federation/proxy checks
7. Restoration/twilight/decline
8. Collapse check
9. Depopulation/ruin tracking

M16 culture effects should be inserted AFTER tick conditions (step 1) and BEFORE asabiya dynamics (step 2):
```
1. Tick condition durations
2. tick_movements(world)           # M16b — NEW
3. apply_value_drift(world)        # M16a — NEW
4. tick_cultural_assimilation(world) # M16a — NEW
5. check_cultural_victories(world)  # M16c — NEW (last of culture effects)
6. Apply asabiya dynamics          # existing (stability changes from assimilation feed asabiya)
7. ... rest of existing ordering
```

---

## Chunk 1: M16a — Cultural Foundations

### Task 1: Model Changes (Civilization, Region, Relationship)

**Files:**
- Modify: `src/chronicler/models.py:57` (Civilization), `src/chronicler/models.py:45` (Region), `src/chronicler/models.py:91` (Relationship)
- Test: `tests/test_culture.py` (create)

- [ ] **Step 1: Write test for new model fields**

Create `tests/test_culture.py`:

```python
"""Tests for M16a cultural foundations."""
import pytest
from chronicler.models import Civilization, Region, Relationship, Leader, TechEra, Disposition


class TestModelFields:
    def test_civilization_has_prestige_field(self):
        civ = Civilization(
            name="Test", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R1"],
        )
        assert civ.prestige == 0

    def test_region_has_cultural_identity_field(self):
        region = Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile")
        assert region.cultural_identity is None
        assert region.foreign_control_turns == 0

    def test_relationship_has_disposition_drift_field(self):
        rel = Relationship()
        assert rel.disposition_drift == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestModelFields -v`
Expected: FAIL — fields don't exist yet.

- [ ] **Step 3: Add prestige to Civilization**

In `src/chronicler/models.py`, add after `action_counts` field (line ~87):

```python
    prestige: int = 0  # M16a: accumulated from cultural works, decays -1/turn
```

- [ ] **Step 4: Add cultural_identity and foreign_control_turns to Region**

In `src/chronicler/models.py`, add after `y` field (line ~53):

```python
    cultural_identity: str | None = None  # M16a: set to controller at world gen
    foreign_control_turns: int = 0        # M16a: turns under non-identity controller
```

- [ ] **Step 5: Add disposition_drift to Relationship**

In `src/chronicler/models.py`, add after `trade_volume` field (line ~96):

```python
    disposition_drift: int = 0  # M16a: accumulator for value-based disposition shifts
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestModelFields -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/models.py tests/test_culture.py
git commit -m "feat(m16a): add prestige, cultural_identity, disposition_drift model fields"
```

---

### Task 2: Value Opposition Table and Value Drift

**Files:**
- Create: `src/chronicler/culture.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for value drift**

Append to `tests/test_culture.py`:

```python
from chronicler.models import WorldState
from chronicler.culture import VALUE_OPPOSITIONS, apply_value_drift


@pytest.fixture
def drift_world():
    """Two civs with known value relationships."""
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Freedom"], regions=["R2"],
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL)},
    }
    return WorldState(
        name="test", seed=42, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestValueOppositions:
    def test_freedom_opposes_order(self):
        assert VALUE_OPPOSITIONS["Freedom"] == "Order"

    def test_neutral_values_not_in_table(self):
        assert "Strength" not in VALUE_OPPOSITIONS
        assert "Destiny" not in VALUE_OPPOSITIONS


class TestValueDrift:
    def test_shared_value_positive_drift(self, drift_world):
        """CivA and CivB share 'Trade' → +2 drift per turn."""
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        # shared=1 (Trade), opposing=1 (Order vs Freedom) → net = (1*2) - (1*2) = 0
        assert rel.disposition_drift == 0

    def test_pure_shared_values_drift(self, drift_world):
        """Both civs have identical values → all shared, no opposing."""
        drift_world.civilizations[1].values = ["Trade", "Order"]
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        # shared=2, opposing=0 → net = 4
        assert rel.disposition_drift == 4

    def test_drift_upgrades_disposition_at_threshold(self, drift_world):
        """Drift reaching +10 upgrades disposition one level and resets."""
        drift_world.civilizations[1].values = ["Trade", "Order"]
        # Pre-set drift to 8 so one turn of +4 pushes over 10
        drift_world.relationships["CivA"]["CivB"].disposition_drift = 8
        drift_world.relationships["CivB"]["CivA"].disposition_drift = 8
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.FRIENDLY  # upgraded from NEUTRAL
        assert rel_ab.disposition_drift == 0  # reset to 0 on trigger (spec: no remainder)

    def test_drift_downgrades_disposition_at_negative_threshold(self, drift_world):
        """Drift reaching -10 downgrades disposition one level and resets."""
        drift_world.civilizations[0].values = ["Freedom"]
        drift_world.civilizations[1].values = ["Order"]
        # shared=0, opposing=1 → net = -2 per turn
        drift_world.relationships["CivA"]["CivB"].disposition_drift = -9
        drift_world.relationships["CivB"]["CivA"].disposition_drift = -9
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.SUSPICIOUS  # downgraded from NEUTRAL
        assert rel_ab.disposition_drift == 0  # reset to 0 on trigger (spec: no remainder)

    def test_empty_values_no_drift(self, drift_world):
        """Civ with empty values list contributes no drift."""
        drift_world.civilizations[0].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestValueOppositions tests/test_culture.py::TestValueDrift -v`
Expected: FAIL — `culture` module doesn't exist.

- [ ] **Step 3: Implement culture.py with VALUE_OPPOSITIONS and apply_value_drift**

Create `src/chronicler/culture.py`:

```python
"""M16a: Culture as property — value drift, assimilation, prestige."""

from __future__ import annotations

from chronicler.models import Disposition, WorldState

# Full value vocabulary: Freedom, Order, Liberty, Tradition, Knowledge,
# Honor, Cunning, Piety, Self-reliance, Trade, Strength, Destiny.
# Liberty and Freedom both oppose Order but are distinct for shared-value bonuses.
VALUE_OPPOSITIONS: dict[str, str] = {
    "Freedom": "Order",
    "Order": "Freedom",
    "Liberty": "Order",
    "Tradition": "Knowledge",
    "Knowledge": "Tradition",
    "Honor": "Cunning",
    "Cunning": "Honor",
    "Piety": "Cunning",
    "Self-reliance": "Trade",
    "Trade": "Self-reliance",
}

_DISPOSITION_ORDER = list(Disposition)


def _upgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[min(idx + 1, len(_DISPOSITION_ORDER) - 1)]


def _downgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[max(idx - 1, 0)]


def apply_value_drift(world: WorldState) -> None:
    """Phase 10: Accumulate disposition drift from shared/opposing values.

    O(N²) per turn where N = number of civs. Fine for 4-6 civs in Phase 3.
    """
    civs = world.civilizations
    for i, civ_a in enumerate(civs):
        for civ_b in civs[i + 1:]:
            # Count shared and opposing values
            shared = sum(1 for v in civ_a.values if v in civ_b.values)
            opposing = sum(
                1 for va in civ_a.values for vb in civ_b.values
                if VALUE_OPPOSITIONS.get(va) == vb
            )
            net_drift = (shared * 2) - (opposing * 2)
            if net_drift == 0:
                continue

            # Apply drift symmetrically
            for a_name, b_name in [(civ_a.name, civ_b.name), (civ_b.name, civ_a.name)]:
                rel = world.relationships.get(a_name, {}).get(b_name)
                if rel is None:
                    continue
                rel.disposition_drift += net_drift
                # Check thresholds — reset to 0 on trigger (spec: no remainder)
                if rel.disposition_drift >= 10:
                    rel.disposition = _upgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0
                elif rel.disposition_drift <= -10:
                    rel.disposition = _downgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestValueOppositions tests/test_culture.py::TestValueDrift -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_culture.py
git commit -m "feat(m16a): add value opposition table and disposition drift"
```

---

### Task 3: Cultural Assimilation

**Files:**
- Modify: `src/chronicler/culture.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for cultural assimilation**

Append to `tests/test_culture.py`:

```python
from chronicler.models import ActiveCondition
from chronicler.culture import tick_cultural_assimilation, ASSIMILATION_THRESHOLD, RECONQUEST_COOLDOWN


@pytest.fixture
def assimilation_world():
    """World with one region controlled by a foreign civ."""
    regions = [
        Region(
            name="Contested", terrain="plains", carrying_capacity=5,
            resources="fertile", controller="CivB",
            cultural_identity="CivA", foreign_control_turns=0,
        ),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=[],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Order"], regions=["Contested"],
        ),
    ]
    return WorldState(
        name="test", seed=42, regions=regions, civilizations=civs,
        relationships={"CivA": {"CivB": Relationship()}, "CivB": {"CivA": Relationship()}},
    )


class TestCulturalAssimilation:
    def test_foreign_control_increments(self, assimilation_world):
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 1

    def test_assimilation_flips_identity_at_threshold(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_assimilation_generates_named_event(self, assimilation_world):
        assimilation_world.regions[0].foreign_control_turns = ASSIMILATION_THRESHOLD - 1
        tick_cultural_assimilation(assimilation_world)
        assert any(
            ne.event_type == "cultural_assimilation"
            for ne in assimilation_world.named_events
        )

    def test_stability_drain_per_mismatched_region(self, assimilation_world):
        """Controller loses stability for each mismatched region."""
        assimilation_world.regions[0].foreign_control_turns = RECONQUEST_COOLDOWN  # past exemption
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.civilizations[1].stability == initial_stability - 3

    def test_reconquest_cooldown_exempts_drain(self, assimilation_world):
        """Regions in first RECONQUEST_COOLDOWN turns skip per-turn drain."""
        assimilation_world.regions[0].foreign_control_turns = 5  # within cooldown
        initial_stability = assimilation_world.civilizations[1].stability
        tick_cultural_assimilation(assimilation_world)
        # foreign_control_turns increments but no stability drain
        assert assimilation_world.civilizations[1].stability == initial_stability

    def test_first_control_sets_identity_immediately(self, assimilation_world):
        """Uncontrolled region (identity=None) gets controller's identity immediately."""
        assimilation_world.regions[0].cultural_identity = None
        assimilation_world.regions[0].controller = "CivB"
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].cultural_identity == "CivB"
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_matching_identity_resets_counter(self, assimilation_world):
        """Controller matching identity → foreign_control_turns resets."""
        assimilation_world.regions[0].controller = "CivA"
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].foreign_control_turns = 10
        tick_cultural_assimilation(assimilation_world)
        assert assimilation_world.regions[0].foreign_control_turns == 0

    def test_reconquest_applies_restless_population(self, assimilation_world):
        """Reconquest of previously-assimilated region applies ActiveCondition."""
        # Region was assimilated (identity changed from CivA to CivB), now CivA reconquers
        assimilation_world.regions[0].cultural_identity = "CivA"
        assimilation_world.regions[0].controller = "CivA"  # reconquest
        assimilation_world.regions[0].foreign_control_turns = 5
        tick_cultural_assimilation(assimilation_world)
        restless = [
            c for c in assimilation_world.active_conditions
            if c.condition_type == "restless_population"
        ]
        assert len(restless) == 1
        assert restless[0].duration == RECONQUEST_COOLDOWN
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalAssimilation -v`
Expected: FAIL — `tick_cultural_assimilation` not defined.

- [ ] **Step 3: Implement tick_cultural_assimilation**

Append to `src/chronicler/culture.py`:

```python
from chronicler.models import ActiveCondition, NamedEvent
from chronicler.utils import clamp

ASSIMILATION_THRESHOLD = 15
ASSIMILATION_STABILITY_DRAIN = 3  # P1-dependent: calibrated for 0-100 scale
RECONQUEST_COOLDOWN = 10


def tick_cultural_assimilation(world: WorldState) -> None:
    """Phase 10: Tick cultural assimilation timers, apply stability drain."""
    for region in world.regions:
        if region.controller is None:
            continue

        # First control: no existing culture to resist
        if region.cultural_identity is None:
            region.cultural_identity = region.controller
            continue

        # Matching identity: reset counter, check for reconquest
        if region.cultural_identity == region.controller:
            if region.foreign_control_turns > 0:
                # Reconquest — apply restless population condition
                region.foreign_control_turns = 0
                world.active_conditions.append(ActiveCondition(
                    condition_type="restless_population",
                    affected_civs=[region.controller],
                    duration=RECONQUEST_COOLDOWN,
                    severity=5,
                ))
            continue

        # Foreign controller: tick assimilation timer
        region.foreign_control_turns += 1

        if region.foreign_control_turns >= ASSIMILATION_THRESHOLD:
            # Assimilation complete
            region.cultural_identity = region.controller
            region.foreign_control_turns = 0
            world.named_events.append(NamedEvent(
                name=f"Assimilation of {region.name}",
                event_type="cultural_assimilation",
                turn=world.turn,
                actors=[region.controller],
                region=region.name,
                description=f"{region.name} has been culturally assimilated by {region.controller}.",
                importance=6,
            ))
        elif region.foreign_control_turns >= RECONQUEST_COOLDOWN:
            # Stability drain (only after cooldown period)
            controller = next(
                (c for c in world.civilizations if c.name == region.controller), None
            )
            if controller:
                controller.stability = clamp(
                    controller.stability - ASSIMILATION_STABILITY_DRAIN, 0, 100
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalAssimilation -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_culture.py
git commit -m "feat(m16a): add cultural assimilation with stability drain"
```

---

### Task 4: Prestige System

**Files:**
- Modify: `src/chronicler/culture.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for prestige**

Append to `tests/test_culture.py`:

```python
from chronicler.culture import tick_prestige


class TestPrestige:
    def test_prestige_decays(self, drift_world):
        drift_world.civilizations[0].prestige = 10
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 9

    def test_prestige_minimum_zero(self, drift_world):
        drift_world.civilizations[0].prestige = 0
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].prestige == 0

    def test_prestige_trade_income_bonus(self, drift_world):
        """prestige // 5 added as trade income bonus."""
        drift_world.civilizations[0].prestige = 11  # after decay: 10 → bonus = 2
        initial_treasury = drift_world.civilizations[0].treasury
        tick_prestige(drift_world)
        assert drift_world.civilizations[0].treasury == initial_treasury + 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestPrestige -v`
Expected: FAIL — `tick_prestige` not defined.

- [ ] **Step 3: Implement tick_prestige**

Append to `src/chronicler/culture.py`:

```python
def tick_prestige(world: WorldState) -> None:
    """Phase 2: Decay prestige and apply income effects."""
    for civ in world.civilizations:
        # Decay first
        civ.prestige = max(0, civ.prestige - 1)
        # Trade income bonus: prestige // 5
        trade_bonus = civ.prestige // 5
        if trade_bonus > 0:
            civ.treasury += trade_bonus
        # Congress voting weight (M14c is merged): prestige // 3 added to negotiating power
        # Wire into politics.py congress resolution where voting weights are computed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestPrestige -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_culture.py
git commit -m "feat(m16a): add prestige decay and trade income bonus"
```

---

### Task 5: Cultural Works Enhancement

**Files:**
- Modify: `src/chronicler/simulation.py:665-685`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write test for cultural works enhancement**

Append to `tests/test_culture.py`:

```python
from chronicler.simulation import phase_cultural_milestones


class TestCulturalWorksEnhancement:
    def test_cultural_work_boosts_prestige(self, drift_world):
        """Producing a cultural work adds +2 prestige."""
        drift_world.civilizations[0].culture = 80  # hits threshold (P1 scale)
        initial_prestige = drift_world.civilizations[0].prestige
        phase_cultural_milestones(drift_world)
        assert drift_world.civilizations[0].prestige == initial_prestige + 2

    def test_cultural_work_boosts_asabiya(self, drift_world):
        """Producing a cultural work adds +0.05 asabiya."""
        drift_world.civilizations[0].culture = 80  # P1 scale
        initial_asabiya = drift_world.civilizations[0].asabiya
        phase_cultural_milestones(drift_world)
        assert drift_world.civilizations[0].asabiya == pytest.approx(initial_asabiya + 0.05)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalWorksEnhancement -v`
Expected: FAIL — prestige and asabiya not modified by current `phase_cultural_milestones`.

- [ ] **Step 3: Modify phase_cultural_milestones to add prestige and asabiya boosts**

In `src/chronicler/simulation.py`, modify `phase_cultural_milestones` (line ~672-680). After the `NamedEvent` is created and appended, add the enhancements:

```python
                # M16a: Cultural works enhancement
                civ.asabiya = min(1.0, civ.asabiya + 0.05)
                civ.culture = clamp(civ.culture + 5, 0, 100)  # post-P1 scale
                civ.prestige += 2
```

Insert these lines after `world.named_events.append(ne)` (line 680) and before `events.append(Event(...))` (line 681).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalWorksEnhancement -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_culture.py
git commit -m "feat(m16a): enhance cultural works with prestige and asabiya boosts"
```

---

### Task 6: World Generation — Initialize cultural_identity

**Files:**
- Modify: `src/chronicler/world_gen.py:120-145`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write test for world gen initialization**

Append to `tests/test_culture.py`:

```python
from chronicler.world_gen import generate_world


class TestWorldGenCulture:
    def test_controlled_regions_get_cultural_identity(self):
        world = generate_world(seed=42, civ_count=4)
        for region in world.regions:
            if region.controller is not None:
                assert region.cultural_identity == region.controller, \
                    f"{region.name} should have cultural_identity={region.controller}"

    def test_uncontrolled_regions_have_no_identity(self):
        world = generate_world(seed=42, civ_count=4)
        for region in world.regions:
            if region.controller is None:
                assert region.cultural_identity is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestWorldGenCulture -v`
Expected: FAIL — cultural_identity not set during world gen.

- [ ] **Step 3: Initialize cultural_identity in world_gen.py**

In `src/chronicler/world_gen.py`, in the `generate_world` function, after regions are assigned to civilizations and the WorldState is created, add:

```python
    # M16a: Initialize cultural identity for controlled regions
    for region in world.regions:
        if region.controller is not None:
            region.cultural_identity = region.controller
```

Insert this after the WorldState is constructed and before the return statement.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestWorldGenCulture -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_culture.py
git commit -m "feat(m16a): initialize cultural_identity at world generation"
```

---

### Task 7: Phase Integration — Wire M16a into Simulation

**Files:**
- Modify: `src/chronicler/simulation.py:704-753` (run_turn)
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write integration test**

Append to `tests/test_culture.py`:

```python
class TestM16aPhaseIntegration:
    def test_prestige_runs_in_phase_2(self, drift_world):
        """tick_prestige should be called during phase 2 (production)."""
        drift_world.civilizations[0].prestige = 10
        from chronicler.simulation import phase_production
        phase_production(drift_world)
        # After phase_production, prestige should have decayed
        assert drift_world.civilizations[0].prestige == 9

    def test_value_drift_runs_in_consequences(self, drift_world):
        """apply_value_drift should be called during phase_consequences."""
        drift_world.civilizations[0].values = ["Trade", "Order"]
        drift_world.civilizations[1].values = ["Trade", "Order"]
        from chronicler.simulation import phase_consequences
        phase_consequences(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4  # shared=2, opposing=0 → net=4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestM16aPhaseIntegration -v`
Expected: FAIL — prestige not called in production, drift not called in consequences.

- [ ] **Step 3: Wire tick_prestige into phase_production**

In `src/chronicler/simulation.py`, add import at top:

```python
from chronicler.culture import tick_prestige, apply_value_drift, tick_cultural_assimilation
```

In `phase_production` (line ~143), add at the end of the function (after population logic, ~line 174):

```python
    # M16a: Prestige decay and income effects
    tick_prestige(world)
```

- [ ] **Step 4: Wire apply_value_drift and tick_cultural_assimilation into phase_consequences**

In `phase_consequences` (line ~607), add BEFORE `apply_asabiya_dynamics(world)` (line ~622). Move `apply_asabiya_dynamics` to run after M16 culture effects:

```python
    # M16b: Movement lifecycle (must run FIRST — see spec)
    # (wired in Task 13, placeholder comment here)

    # M16a: Cultural effects (order matters — see spec)
    apply_value_drift(world)
    tick_cultural_assimilation(world)

    # Asabiya dynamics (runs AFTER cultural effects — stability changes from
    # assimilation drain feed into asabiya calculations)
    apply_asabiya_dynamics(world)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestM16aPhaseIntegration -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest -v`
Expected: All existing tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/simulation.py tests/test_culture.py
git commit -m "feat(m16a): wire prestige, value drift, and assimilation into simulation phases"
```

---

## Chunk 2: M16b — Movements & Schisms

### Task 8: Movement Model

**Files:**
- Modify: `src/chronicler/models.py:134` (insert Movement class, extend WorldState)
- Test: `tests/test_movements.py` (create)

- [ ] **Step 1: Write test for Movement model**

Create `tests/test_movements.py`:

```python
"""Tests for M16b movements and schisms."""
import pytest
from chronicler.models import (
    Movement, WorldState, Region, Civilization, Relationship,
    Leader, TechEra, Disposition,
)


class TestMovementModel:
    def test_movement_creation(self):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=30,
            value_affinity="Trade",
        )
        assert m.adherents == {}
        assert m.value_affinity == "Trade"

    def test_worldstate_has_movements(self):
        world = WorldState(name="test", seed=42)
        assert world.movements == []
        assert world.next_movement_id == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementModel -v`
Expected: FAIL — `Movement` not defined, WorldState missing fields.

- [ ] **Step 3: Add Movement model and extend WorldState**

In `src/chronicler/models.py`, insert before `# --- Top-level state ---` (line 134):

```python
class Movement(BaseModel):
    """M16b: An ideological movement that spreads between civilizations."""
    id: str
    origin_civ: str
    origin_turn: int
    value_affinity: str
    adherents: dict[str, int] = Field(default_factory=dict)  # civ_name → variant counter


```

Add to `WorldState` class (after `scenario_name` field, line ~150):

```python
    movements: list[Movement] = Field(default_factory=list)  # M16b
    next_movement_id: int = 0  # M16b: monotonic counter
```

Add `Movement` to the imports/exports at top of file if using `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementModel -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_movements.py
git commit -m "feat(m16b): add Movement model and extend WorldState"
```

---

### Task 9: Movement Emergence

**Files:**
- Create: `src/chronicler/movements.py`
- Test: `tests/test_movements.py` (append)

- [ ] **Step 1: Write tests for movement emergence**

Append to `tests/test_movements.py`:

```python
from chronicler.movements import tick_movements, MOVEMENT_EMERGENCE_INTERVAL


@pytest.fixture
def movement_world():
    """World suitable for movement testing."""
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA", cultural_identity="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB", cultural_identity="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=70,
            stability=30, leader=Leader(name="LA", trait="visionary", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
            tech_era=TechEra.CLASSICAL,
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=40,
            stability=80, leader=Leader(name="LB", trait="aggressive", reign_start=0),
            domains=["warfare"], values=["Honor", "Strength"], regions=["R2"],
            tech_era=TechEra.IRON,
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL, trade_volume=5)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL, trade_volume=5)},
    }
    return WorldState(
        name="test", seed=42, turn=0, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestMovementEmergence:
    def test_no_emergence_before_interval(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL - 1
        tick_movements(movement_world)
        assert len(movement_world.movements) == 0

    def test_emergence_at_interval(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert len(movement_world.movements) == 1

    def test_movement_has_correct_fields(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        m = movement_world.movements[0]
        assert m.id == "movement_0"
        assert m.origin_turn == MOVEMENT_EMERGENCE_INTERVAL
        assert m.origin_civ in [c.name for c in movement_world.civilizations]
        assert m.value_affinity in movement_world.civilizations[0].values + movement_world.civilizations[1].values

    def test_origin_civ_auto_adopts(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        m = movement_world.movements[0]
        assert m.origin_civ in m.adherents

    def test_next_movement_id_increments(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert movement_world.next_movement_id == 1

    def test_emergence_generates_named_event(self, movement_world):
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert any(
            ne.event_type == "movement_emergence"
            for ne in movement_world.named_events
        )

    def test_empty_values_skips_emergence(self, movement_world):
        """Civ with no values cannot spawn a movement."""
        for civ in movement_world.civilizations:
            civ.values = []
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        tick_movements(movement_world)
        assert len(movement_world.movements) == 0

    def test_deterministic_tiebreaker(self, movement_world):
        """Same seed + turn always produces same origin civ."""
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        # Make both civs score identically
        movement_world.civilizations[0].culture = 50
        movement_world.civilizations[0].stability = 50
        movement_world.civilizations[1].culture = 50
        movement_world.civilizations[1].stability = 50
        movement_world.civilizations[0].tech_era = TechEra.IRON
        movement_world.civilizations[1].tech_era = TechEra.IRON
        tick_movements(movement_world)
        origin1 = movement_world.movements[0].origin_civ

        # Reset and replay
        movement_world.movements.clear()
        movement_world.next_movement_id = 0
        movement_world.named_events.clear()
        tick_movements(movement_world)
        origin2 = movement_world.movements[0].origin_civ

        assert origin1 == origin2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementEmergence -v`
Expected: FAIL — `movements` module doesn't exist.

- [ ] **Step 3: Implement movements.py with emergence logic**

Create `src/chronicler/movements.py`:

```python
"""M16b: Ideas as entities — emergence, spread, adoption, variant drift, schism detection."""

from __future__ import annotations

import hashlib

from chronicler.models import Movement, NamedEvent, TechEra, WorldState
from chronicler.culture import VALUE_OPPOSITIONS

MOVEMENT_EMERGENCE_INTERVAL = 30
SCHISM_DIVERGENCE_THRESHOLD = 3
VARIANT_DRIFT_INTERVAL = 10
SEEDED_OFFSET_RANGE = 3

_ERA_BONUS: dict[TechEra, float] = {
    TechEra.TRIBAL: 0.0, TechEra.BRONZE: 0.0,
    TechEra.IRON: 0.1, TechEra.CLASSICAL: 0.1,
    TechEra.MEDIEVAL: 0.2, TechEra.RENAISSANCE: 0.2,
    TechEra.INDUSTRIAL: 0.3,
    TechEra.INFORMATION: 0.3,  # M15 added INFORMATION era
}

STAT_MAX = 100  # P1 migrated; check utils.py for canonical constant


def _seeded_offset(civ_name: str, movement_id: str) -> int:
    """Deterministic starting variant offset. SHA256 for cross-process consistency."""
    return int(hashlib.sha256(
        (civ_name + movement_id).encode()
    ).hexdigest(), 16) % SEEDED_OFFSET_RANGE


def _check_emergence(world: WorldState) -> None:
    """Every MOVEMENT_EMERGENCE_INTERVAL turns, spawn a movement from highest-scoring civ."""
    if world.turn == 0 or world.turn % MOVEMENT_EMERGENCE_INTERVAL != 0:
        return

    # Score all civs
    scored: list[tuple[float, str]] = []
    for civ in world.civilizations:
        if not civ.values:
            continue
        era_bonus = _ERA_BONUS.get(civ.tech_era, 0.3)
        score = (civ.culture / STAT_MAX) + (1 - civ.stability / STAT_MAX) + era_bonus
        scored.append((score, civ.name))

    if not scored:
        return

    # Find max score
    max_score = max(s for s, _ in scored)
    tied = [name for s, name in scored if s == max_score]

    # SHA256 tiebreaker
    if len(tied) > 1:
        salt = f"{world.seed}:{world.turn}:movement_origin"
        tied.sort(key=lambda name: hashlib.sha256(
            f"{salt}:{name}".encode()
        ).hexdigest())

    winner_name = tied[0]
    winner = next(c for c in world.civilizations if c.name == winner_name)

    movement_id = f"movement_{world.next_movement_id}"
    movement = Movement(
        id=movement_id,
        origin_civ=winner.name,
        origin_turn=world.turn,
        value_affinity=winner.values[0],
        adherents={winner.name: _seeded_offset(winner.name, movement_id)},
    )
    world.movements.append(movement)
    world.next_movement_id += 1

    world.named_events.append(NamedEvent(
        name=f"Rise of {movement_id.replace('_', ' ').title()}",
        event_type="movement_emergence",
        turn=world.turn,
        actors=[winner.name],
        description=f"A new ideological movement emerges from {winner.name}, rooted in {movement.value_affinity}.",
        importance=6,
    ))


def tick_movements(world: WorldState) -> None:
    """Phase 10: Process all movement lifecycle — emergence, spread, drift, schisms."""
    _check_emergence(world)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementEmergence -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/movements.py tests/test_movements.py
git commit -m "feat(m16b): add movement emergence with scoring and SHA256 tiebreaker"
```

---

### Task 10: Movement Spread

**Files:**
- Modify: `src/chronicler/movements.py`
- Test: `tests/test_movements.py` (append)

- [ ] **Step 1: Write tests for movement spread**

Append to `tests/test_movements.py`:

```python
class TestMovementSpread:
    def test_spread_via_trade_route(self, movement_world):
        """Movement spreads from adopter to trade partner."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        # CivB values=["Honor", "Strength"] → compatibility=50 (neutral)
        # trade_volume=5 → probability = 5 * 50 / 100 = 2.5%
        # Run many turns to verify spread can happen (or set trade_volume high)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200  # guarantee spread
        movement_world.relationships["CivB"]["CivA"].trade_volume = 200
        tick_movements(movement_world)
        assert "CivB" in m.adherents

    def test_no_spread_to_opposing_value(self, movement_world):
        """Movement with value opposed by target has 0% spread chance."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Cunning",  # opposes Honor (CivB's value)
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 1000
        movement_world.relationships["CivB"]["CivA"].trade_volume = 1000
        tick_movements(movement_world)
        assert "CivB" not in m.adherents

    def test_no_cascade_in_single_turn(self, movement_world):
        """A civ adopted this turn should NOT spread to others in the same turn."""
        # Add CivC
        civ_c = Civilization(
            name="CivC", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LC", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R3"],
        )
        movement_world.civilizations.append(civ_c)
        r3 = Region(name="R3", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivC", cultural_identity="CivC")
        movement_world.regions.append(r3)
        # CivA→CivB has trade, CivB→CivC has trade, CivA→CivC has no trade
        movement_world.relationships["CivA"]["CivC"] = Relationship(trade_volume=0)
        movement_world.relationships["CivC"] = {
            "CivA": Relationship(trade_volume=0),
            "CivB": Relationship(trade_volume=200),
        }
        movement_world.relationships["CivB"]["CivC"] = Relationship(trade_volume=200)

        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200

        tick_movements(movement_world)
        # CivB may adopt from CivA, but CivC should NOT adopt from CivB this turn
        if "CivB" in m.adherents:
            assert "CivC" not in m.adherents, "Single-turn cascade should be prevented"

    def test_spread_generates_named_event(self, movement_world):
        """Adoption should generate a movement_adoption NamedEvent."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},
        )
        movement_world.movements.append(m)
        movement_world.relationships["CivA"]["CivB"].trade_volume = 200
        movement_world.relationships["CivB"]["CivA"].trade_volume = 200
        # CivB has neutral compatibility (50), high trade → should adopt
        tick_movements(movement_world)
        if "CivB" in m.adherents:
            assert any(
                ne.event_type == "movement_adoption"
                for ne in movement_world.named_events
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementSpread -v`
Expected: FAIL — `_process_spread` not implemented.

- [ ] **Step 3: Implement _process_spread**

Add to `src/chronicler/movements.py`:

```python
def _process_spread(world: WorldState) -> None:
    """Spread movements from adopters to trade partners. Snapshot prevents cascades."""
    for movement in world.movements:
        current_adherents = list(movement.adherents.keys())
        for adopter_name in current_adherents:
            # Check all civs with trade toward this adopter
            for civ in world.civilizations:
                if civ.name == adopter_name or civ.name in movement.adherents:
                    continue
                # Get trade volume (check both directions)
                rel = world.relationships.get(adopter_name, {}).get(civ.name)
                if rel is None or rel.trade_volume <= 0:
                    continue

                # Compute compatibility
                if movement.value_affinity in civ.values:
                    compatibility = 100
                elif VALUE_OPPOSITIONS.get(movement.value_affinity) in civ.values:
                    compatibility = 0
                else:
                    compatibility = 50

                adoption_probability = rel.trade_volume * compatibility / 100
                roll = int(hashlib.sha256(
                    f"{world.seed}:{world.turn}:{movement.id}:{civ.name}:spread".encode()
                ).hexdigest(), 16) % 100

                if roll < adoption_probability:
                    movement.adherents[civ.name] = _seeded_offset(civ.name, movement.id)
                    world.named_events.append(NamedEvent(
                        name=f"{civ.name} adopts {movement.id.replace('_', ' ')}",
                        event_type="movement_adoption",
                        turn=world.turn,
                        actors=[civ.name, movement.origin_civ],
                        description=f"{civ.name} adopts a {movement.value_affinity}-aligned movement from {movement.origin_civ}.",
                        importance=5,
                    ))
```

Update `tick_movements` to call `_process_spread`:

```python
def tick_movements(world: WorldState) -> None:
    _check_emergence(world)
    _process_spread(world)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestMovementSpread -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/movements.py tests/test_movements.py
git commit -m "feat(m16b): add movement spread via trade routes with snapshot guard"
```

---

### Task 11: Variant Drift and Schism Detection

**Files:**
- Modify: `src/chronicler/movements.py`
- Test: `tests/test_movements.py` (append)

- [ ] **Step 1: Write tests for variant drift and schism**

Append to `tests/test_movements.py`:

```python
from chronicler.movements import (
    _seeded_offset, VARIANT_DRIFT_INTERVAL, SCHISM_DIVERGENCE_THRESHOLD,
    SEEDED_OFFSET_RANGE,
)


class TestVariantDrift:
    def test_seeded_offset_deterministic(self):
        """Same inputs always produce same offset."""
        a = _seeded_offset("CivA", "movement_0")
        b = _seeded_offset("CivA", "movement_0")
        assert a == b
        assert 0 <= a < SEEDED_OFFSET_RANGE

    def test_variant_increments_on_tick(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        movement_world.movements.append(m)
        movement_world.turn = VARIANT_DRIFT_INTERVAL  # tick turn
        tick_movements(movement_world)
        assert m.adherents["CivA"] == 1
        assert m.adherents["CivB"] == 1

    def test_no_increment_off_tick(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        movement_world.movements.append(m)
        movement_world.turn = VARIANT_DRIFT_INTERVAL + 1  # off-tick
        tick_movements(movement_world)
        assert m.adherents["CivA"] == 0
        assert m.adherents["CivB"] == 0


class TestSchismDetection:
    def test_schism_fires_at_threshold(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD},
        )
        movement_world.movements.append(m)
        movement_world.turn = 1  # any non-tick turn
        tick_movements(movement_world)
        assert any(
            ne.event_type == "movement_schism"
            for ne in movement_world.named_events
        )

    def test_schism_fire_once_guard(self, movement_world):
        """Same schism should not fire twice."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD},
        )
        movement_world.movements.append(m)
        movement_world.turn = 1
        tick_movements(movement_world)
        count_before = len(movement_world.named_events)
        tick_movements(movement_world)
        count_after = len(movement_world.named_events)
        assert count_after == count_before  # no new schism event

    def test_no_schism_below_threshold(self, movement_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD - 1},
        )
        movement_world.movements.append(m)
        movement_world.turn = 1
        tick_movements(movement_world)
        assert not any(
            ne.event_type == "movement_schism"
            for ne in movement_world.named_events
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestVariantDrift tests/test_movements.py::TestSchismDetection -v`
Expected: FAIL — `_increment_variants` and `_detect_schisms` not implemented.

- [ ] **Step 3: Implement _increment_variants and _detect_schisms**

Add to `src/chronicler/movements.py`:

```python
from itertools import combinations


def _increment_variants(world: WorldState) -> None:
    """Increment variant counters for all adherents on tick turns."""
    for movement in world.movements:
        if (world.turn - movement.origin_turn) % VARIANT_DRIFT_INTERVAL == 0:
            for civ_name in movement.adherents:
                movement.adherents[civ_name] += 1


def _detect_schisms(world: WorldState) -> None:
    """Check adherent pairs for divergence threshold crossing. Fire-once via named_events."""
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for a, b in combinations(adherent_names, 2):
            divergence = abs(movement.adherents[a] - movement.adherents[b])
            if divergence >= SCHISM_DIVERGENCE_THRESHOLD:
                # Fire-once guard
                already_fired = any(
                    ne.event_type == "movement_schism"
                    and a in ne.actors and b in ne.actors
                    and movement.id in ne.description
                    for ne in world.named_events
                )
                if not already_fired:
                    world.named_events.append(NamedEvent(
                        name=f"Schism of {movement.id.replace('_', ' ')}",
                        event_type="movement_schism",
                        turn=world.turn,
                        actors=[a, b],
                        description=f"[{movement.id}] Schism between {a} and {b}.",
                        importance=7,
                    ))
```

Update `tick_movements`:

```python
def tick_movements(world: WorldState) -> None:
    _check_emergence(world)
    _process_spread(world)
    _increment_variants(world)
    _detect_schisms(world)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestVariantDrift tests/test_movements.py::TestSchismDetection -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/movements.py tests/test_movements.py
git commit -m "feat(m16b): add variant drift and schism detection with fire-once guard"
```

---

### Task 12: Movement Disposition Effects (integrate into apply_value_drift)

**Files:**
- Modify: `src/chronicler/culture.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for movement disposition effects**

Append to `tests/test_culture.py`:

```python
from chronicler.models import Movement
from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD


class TestMovementDispositionEffects:
    def test_co_adopters_get_positive_drift(self, drift_world):
        """Compatible co-adopters add +5 drift."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 1},  # divergence=1 < 3
        )
        drift_world.movements.append(m)
        # Zero out base value drift by giving both civs empty values
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 5

    def test_schism_co_adopters_get_negative_drift(self, drift_world):
        """Schismatic co-adopters add -5 drift."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": SCHISM_DIVERGENCE_THRESHOLD},
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == -5

    def test_non_adopter_no_effect(self, drift_world):
        """Non-adopters get 0 movement effect."""
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0},  # only CivA adopted
        )
        drift_world.movements.append(m)
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0

    def test_multiple_movements_stack(self, drift_world):
        """Effects from multiple movements stack."""
        m1 = Movement(id="movement_0", origin_civ="CivA", origin_turn=0,
                       value_affinity="Trade", adherents={"CivA": 0, "CivB": 0})
        m2 = Movement(id="movement_1", origin_civ="CivA", origin_turn=0,
                       value_affinity="Order", adherents={"CivA": 0, "CivB": 0})
        drift_world.movements.extend([m1, m2])
        drift_world.civilizations[0].values = []
        drift_world.civilizations[1].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 10  # +5 + +5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestMovementDispositionEffects -v`
Expected: FAIL — `apply_value_drift` doesn't include movement effects yet.

- [ ] **Step 3: Add movement co-adoption effects to apply_value_drift**

In `src/chronicler/culture.py`, modify `apply_value_drift` to add movement effects after the base value drift computation. Add import at top:

```python
from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD
```

In `apply_value_drift`, after the value drift loop, add a second loop for movement effects:

```python
    # Movement co-adoption effects
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for idx_a, name_a in enumerate(adherent_names):
            for name_b in adherent_names[idx_a + 1:]:
                divergence = abs(movement.adherents[name_a] - movement.adherents[name_b])
                movement_drift = 5 if divergence < SCHISM_DIVERGENCE_THRESHOLD else -5
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel is None:
                        continue
                    rel.disposition_drift += movement_drift
                    if rel.disposition_drift >= 10:
                        rel.disposition = _upgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
                    elif rel.disposition_drift <= -10:
                        rel.disposition = _downgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestMovementDispositionEffects -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_culture.py
git commit -m "feat(m16b): integrate movement co-adoption effects into value drift"
```

---

### Task 13: Wire M16b into Simulation

**Files:**
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_movements.py` (append)

- [ ] **Step 1: Write integration test**

Append to `tests/test_movements.py`:

```python
class TestM16bPhaseIntegration:
    def test_tick_movements_runs_in_consequences(self, movement_world):
        """tick_movements called in phase_consequences, before value drift."""
        movement_world.turn = MOVEMENT_EMERGENCE_INTERVAL
        from chronicler.simulation import phase_consequences
        phase_consequences(movement_world)
        # Movement should have emerged
        assert len(movement_world.movements) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestM16bPhaseIntegration -v`
Expected: FAIL — tick_movements not called in phase_consequences.

- [ ] **Step 3: Wire tick_movements into phase_consequences**

In `src/chronicler/simulation.py`, add import:

```python
from chronicler.movements import tick_movements
```

In `phase_consequences`, add before the M16a cultural effects (before `apply_value_drift`):

```python
    # M16b: Movement lifecycle (must run BEFORE value drift — see spec)
    tick_movements(world)
```

The final phase_consequences order should be:
1. Tick conditions
2. Remove expired conditions
3. `tick_movements(world)` — M16b
4. `apply_value_drift(world)` — M16a
5. `tick_cultural_assimilation(world)` — M16a
6. `apply_asabiya_dynamics(world)`
7. Collapse check

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_movements.py::TestM16bPhaseIntegration -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_movements.py
git commit -m "feat(m16b): wire tick_movements into phase_consequences"
```

---

## Chunk 3: M16c — Strategic Culture

### Task 14: get_era_bonus Accessor and Paradigm Shift Bonuses

**Files:**
- Modify: `src/chronicler/tech.py:32-39`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for get_era_bonus**

Append to `tests/test_culture.py`:

```python
from chronicler.tech import get_era_bonus


class TestEraBonus:
    def test_existing_stat_bonus(self):
        assert get_era_bonus(TechEra.IRON, "economy", default=0.0) == 10  # P1 scale

    def test_multiplier_key(self):
        assert get_era_bonus(TechEra.IRON, "military_multiplier", default=1.0) == 1.3

    def test_missing_key_returns_default(self):
        assert get_era_bonus(TechEra.BRONZE, "culture_projection_range", default=1) == 1

    def test_fortification_multiplier(self):
        assert get_era_bonus(TechEra.MEDIEVAL, "fortification_multiplier", default=1.0) == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestEraBonus -v`
Expected: FAIL — `get_era_bonus` doesn't exist.

- [ ] **Step 3: Extend ERA_BONUSES and add get_era_bonus**

In `src/chronicler/tech.py`, modify `ERA_BONUSES` (line ~32-39) to add paradigm shift multipliers:

```python
# Stat keys (military, economy, culture) are one-time bonuses applied at era advancement.
# Multiplier/range keys (military_multiplier, fortification_multiplier, culture_projection_range)
# are ongoing modifiers queried per-turn by consuming modules.
# Consumers should always use get_era_bonus(), never read the dict directly.
#
# NOTE: Preserve existing P1-scale stat values. Only ADD the new multiplier keys.
ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 10, "military_multiplier": 1.0},
    TechEra.IRON: {"economy": 10, "military_multiplier": 1.3},
    TechEra.CLASSICAL: {"culture": 10, "fortification_multiplier": 1.0},
    TechEra.MEDIEVAL: {"military": 10, "fortification_multiplier": 2.0},
    TechEra.RENAISSANCE: {"economy": 20, "culture": 10},
    TechEra.INDUSTRIAL: {"economy": 20, "military": 20},
    TechEra.INFORMATION: {"culture": 10, "economy": 5, "culture_projection_range": -1},
}
```

Add after ERA_BONUSES:

```python
def get_era_bonus(era: TechEra, key: str, default: float = 0.0) -> float:
    """Look up an era-specific bonus. Returns default if key not present for this era."""
    return ERA_BONUSES.get(era, {}).get(key, default)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestEraBonus -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech.py tests/test_culture.py
git commit -m "feat(m16c): extend ERA_BONUSES with paradigm shift multipliers and get_era_bonus()"
```

---

### Task 15: INVEST_CULTURE Action Type and Engine Weights

**Files:**
- Modify: `src/chronicler/models.py:35-41` (ActionType enum)
- Modify: `src/chronicler/action_engine.py:11-22,39-58,103-137`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for INVEST_CULTURE eligibility and weighting**

Append to `tests/test_culture.py`:

```python
from chronicler.models import ActionType
from chronicler.action_engine import ActionEngine


class TestInvestCultureAction:
    def test_invest_culture_in_action_type_enum(self):
        assert hasattr(ActionType, "INVEST_CULTURE")

    def test_invest_culture_eligible_at_culture_60(self, drift_world):
        drift_world.civilizations[0].culture = 60
        # Need adjacency for targeting and rival cultural identity
        drift_world.regions[0].adjacencies = ["R2"]
        drift_world.regions[1].adjacencies = ["R1"]
        drift_world.regions[1].cultural_identity = "CivB"
        engine = ActionEngine(drift_world)
        eligible = engine.get_eligible_actions(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE in eligible

    def test_invest_culture_not_eligible_below_60(self, drift_world):
        drift_world.civilizations[0].culture = 59
        engine = ActionEngine(drift_world)
        eligible = engine.get_eligible_actions(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE not in eligible

    def test_visionary_weights_invest_culture_highest(self, drift_world):
        drift_world.civilizations[0].culture = 60
        drift_world.civilizations[0].leader.trait = "visionary"
        drift_world.regions[0].adjacencies = ["R2"]
        drift_world.regions[1].adjacencies = ["R1"]
        drift_world.regions[1].cultural_identity = "CivB"
        engine = ActionEngine(drift_world)
        weights = engine.compute_weights(drift_world.civilizations[0])
        assert ActionType.INVEST_CULTURE in weights
        assert weights[ActionType.INVEST_CULTURE] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestInvestCultureAction -v`
Expected: FAIL — INVEST_CULTURE not in ActionType.

- [ ] **Step 3: Add INVEST_CULTURE to ActionType**

In `src/chronicler/models.py`, add to ActionType enum (line ~35-41):

```python
    INVEST_CULTURE = "invest_culture"
```

- [ ] **Step 4: Add INVEST_CULTURE to TRAIT_WEIGHTS and action engine**

In `src/chronicler/action_engine.py`, add INVEST_CULTURE weight to each trait in TRAIT_WEIGHTS (line ~11-22):

```python
    "aggressive":   {..., ActionType.INVEST_CULTURE: 0.3},
    "cautious":     {..., ActionType.INVEST_CULTURE: 1.3},
    "opportunistic":{..., ActionType.INVEST_CULTURE: 0.8},
    "zealous":      {..., ActionType.INVEST_CULTURE: 0.5},
    "ambitious":    {..., ActionType.INVEST_CULTURE: 1.0},
    "calculating":  {..., ActionType.INVEST_CULTURE: 1.5},
    "visionary":    {..., ActionType.INVEST_CULTURE: 2.0},
    "bold":         {..., ActionType.INVEST_CULTURE: 0.4},
    "shrewd":       {..., ActionType.INVEST_CULTURE: 1.8},
    "stubborn":     {},  # unchanged
```

In `get_eligible_actions` (line ~39), add INVEST_CULTURE eligibility:

```python
        # M16c: INVEST_CULTURE requires culture >= 60 and valid targets
        if civ.culture >= 60:
            from chronicler.tech import get_era_bonus
            global_proj = get_era_bonus(civ.tech_era, "culture_projection_range", default=1) == -1
            civ_regions = {r.name for r in self.world.regions if r.controller == civ.name}
            adjacent = set()
            if not global_proj:
                for r in self.world.regions:
                    if r.name in civ_regions:
                        adjacent.update(r.adjacencies)
            has_valid_target = any(
                r.controller is not None
                and r.controller != civ.name
                and r.cultural_identity != civ.name
                and (global_proj or r.name in adjacent)
                for r in self.world.regions
            )
            if has_valid_target:
                eligible.append(ActionType.INVEST_CULTURE)
```

In `_apply_situational` or `compute_weights`, add the x2.0 modifier when rival-adjacent regions exist:

```python
        # M16c: Boost INVEST_CULTURE when rival-adjacent regions exist
        if ActionType.INVEST_CULTURE in weights and weights[ActionType.INVEST_CULTURE] > 0:
            weights[ActionType.INVEST_CULTURE] *= 2.0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestInvestCultureAction -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py src/chronicler/action_engine.py tests/test_culture.py
git commit -m "feat(m16c): add INVEST_CULTURE action type with engine weights"
```

---

### Task 16: INVEST_CULTURE Resolution and Counter-Propaganda

**Files:**
- Modify: `src/chronicler/culture.py`
- Modify: `src/chronicler/simulation.py:204-224`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for INVEST_CULTURE resolution**

Append to `tests/test_culture.py`:

```python
from chronicler.culture import (
    resolve_invest_culture, PROPAGANDA_COST, PROPAGANDA_ACCELERATION,
    COUNTER_PROPAGANDA_COST,
)


@pytest.fixture
def propaganda_world():
    """World with a high-culture civ adjacent to a rival region."""
    regions = [
        Region(name="Home", terrain="plains", carrying_capacity=50, resources="fertile",
               controller="CivA", cultural_identity="CivA", adjacencies=["Target"]),
        Region(name="Target", terrain="plains", carrying_capacity=50, resources="fertile",
               controller="CivB", cultural_identity="CivB", adjacencies=["Home"]),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=70,
            stability=50, treasury=20,
            leader=Leader(name="LA", trait="visionary", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["Home"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=30,
            stability=50, treasury=20,
            leader=Leader(name="LB", trait="aggressive", reign_start=0),
            domains=["warfare"], values=["Honor"], regions=["Target"],
        ),
    ]
    return WorldState(
        name="test", seed=42, regions=regions, civilizations=civs,
        relationships={
            "CivA": {"CivB": Relationship()},
            "CivB": {"CivA": Relationship()},
        },
    )


class TestInvestCultureResolution:
    def test_propaganda_costs_treasury(self, propaganda_world):
        initial = propaganda_world.civilizations[0].treasury
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.civilizations[0].treasury == initial - PROPAGANDA_COST

    def test_propaganda_accelerates_assimilation(self, propaganda_world):
        initial_fct = propaganda_world.regions[1].foreign_control_turns
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        # With defender counter-spend: net +0. Without: net +3
        expected = initial_fct + PROPAGANDA_ACCELERATION
        if propaganda_world.civilizations[1].treasury >= COUNTER_PROPAGANDA_COST:
            expected = initial_fct  # counter-spend negates
        assert propaganda_world.regions[1].foreign_control_turns == expected

    def test_defender_counter_spend_deducts_treasury(self, propaganda_world):
        initial_def_treasury = propaganda_world.civilizations[1].treasury
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.civilizations[1].treasury == initial_def_treasury - COUNTER_PROPAGANDA_COST

    def test_defender_no_counter_when_broke(self, propaganda_world):
        propaganda_world.civilizations[1].treasury = 0
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert propaganda_world.regions[1].foreign_control_turns == PROPAGANDA_ACCELERATION

    def test_cannot_target_own_cultural_region(self, propaganda_world):
        """Regions where cultural_identity == projecting civ are not valid targets."""
        propaganda_world.regions[1].cultural_identity = "CivA"
        event = resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        # No valid target → no treasury spent
        assert propaganda_world.civilizations[0].treasury == 20

    def test_generates_named_event(self, propaganda_world):
        resolve_invest_culture(propaganda_world.civilizations[0], propaganda_world)
        assert any(
            ne.event_type == "propaganda_campaign"
            for ne in propaganda_world.named_events
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestInvestCultureResolution -v`
Expected: FAIL — `resolve_invest_culture` not defined.

- [ ] **Step 3: Implement resolve_invest_culture with counter-propaganda**

Add constants and function to `src/chronicler/culture.py`:

```python
import hashlib

PROPAGANDA_COST = 5
PROPAGANDA_ACCELERATION = 3
COUNTER_PROPAGANDA_COST = 3
CULTURE_PROJECTION_THRESHOLD = 60


def _counter_propaganda_reaction(world: WorldState, defender, region, seed: int) -> int:
    """Returns adjustment to propaganda acceleration (0 or -PROPAGANDA_ACCELERATION)."""
    if defender.treasury >= COUNTER_PROPAGANDA_COST:
        defender.treasury -= COUNTER_PROPAGANDA_COST
        return -PROPAGANDA_ACCELERATION
    return 0


def resolve_invest_culture(civ, world: WorldState) -> Event | None:
    """Resolve INVEST_CULTURE action: project propaganda into a rival region."""
    from chronicler.models import Event, NamedEvent

    from chronicler.tech import get_era_bonus

    # Check projection range: -1 = global (INFORMATION era), else adjacency required
    projection_range = get_era_bonus(civ.tech_era, "culture_projection_range", default=1)
    global_projection = projection_range == -1

    # Find valid targets: rival-controlled, cultural_identity != civ
    candidates = [
        r for r in world.regions
        if r.controller is not None
        and r.controller != civ.name
        and r.cultural_identity != civ.name
    ]

    # Apply adjacency filter unless global projection
    if global_projection:
        targets = candidates
    else:
        # Get all regions adjacent to civ's regions
        civ_regions = {r.name for r in world.regions if r.controller == civ.name}
        adjacent = set()
        for r in world.regions:
            if r.name in civ_regions:
                adjacent.update(r.adjacencies)
        targets = [r for r in candidates if r.name in adjacent]

    if not targets or civ.treasury < PROPAGANDA_COST:
        return Event(
            turn=world.turn, event_type="action", actors=[civ.name],
            description=f"{civ.name} attempts cultural influence but finds no valid target.",
            importance=1,
        )

    # Target selection: highest foreign_control_turns (closest to assimilation)
    targets.sort(key=lambda r: r.foreign_control_turns, reverse=True)
    # Tiebreaker: SHA256
    max_fct = targets[0].foreign_control_turns
    tied = [r for r in targets if r.foreign_control_turns == max_fct]
    if len(tied) > 1:
        salt = f"{world.seed}:{world.turn}:propaganda:{civ.name}"
        tied.sort(key=lambda r: hashlib.sha256(f"{salt}:{r.name}".encode()).hexdigest())
    target = tied[0]

    # Pay cost
    civ.treasury -= PROPAGANDA_COST

    # Defender counter-spend
    defender = next((c for c in world.civilizations if c.name == target.controller), None)
    adjustment = 0
    if defender:
        adjustment = _counter_propaganda_reaction(world, defender, target, world.seed)

    # Apply acceleration
    net_acceleration = PROPAGANDA_ACCELERATION + adjustment
    target.foreign_control_turns += net_acceleration

    # Generate event
    world.named_events.append(NamedEvent(
        name=f"Propaganda in {target.name}",
        event_type="propaganda_campaign",
        turn=world.turn,
        actors=[civ.name],
        region=target.name,
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    ))

    return Event(
        turn=world.turn, event_type="invest_culture", actors=[civ.name],
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    )
```

- [ ] **Step 4: Register INVEST_CULTURE handler in action_engine.py**

In `src/chronicler/action_engine.py`, add a registered handler (NOT in simulation.py — see ERRATA E1):

```python
@register_action(ActionType.INVEST_CULTURE)
def _resolve_invest_culture(civ: Civilization, world: WorldState) -> Event:
    from chronicler.culture import resolve_invest_culture
    return resolve_invest_culture(civ, world)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestInvestCultureResolution -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/culture.py src/chronicler/simulation.py tests/test_culture.py
git commit -m "feat(m16c): add INVEST_CULTURE resolution with counter-propaganda reaction"
```

---

### Task 17: Cultural Victory Tracking

**Files:**
- Modify: `src/chronicler/culture.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for cultural victories**

Append to `tests/test_culture.py`:

```python
from chronicler.culture import check_cultural_victories


class TestCulturalVictories:
    def test_hegemony_when_culture_exceeds_all_others(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        check_cultural_victories(drift_world)
        assert any(
            ne.event_type == "cultural_hegemony" and "CivA" in ne.actors
            for ne in drift_world.named_events
        )

    def test_no_hegemony_when_not_dominant(self, drift_world):
        drift_world.civilizations[0].culture = 50
        drift_world.civilizations[1].culture = 50
        check_cultural_victories(drift_world)
        assert not any(
            ne.event_type == "cultural_hegemony"
            for ne in drift_world.named_events
        )

    def test_hegemony_fire_once(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        check_cultural_victories(drift_world)
        count = len(drift_world.named_events)
        check_cultural_victories(drift_world)
        assert len(drift_world.named_events) == count  # no duplicate

    def test_universal_enlightenment(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        drift_world.movements.append(m)
        check_cultural_victories(drift_world)
        assert any(
            ne.event_type == "universal_enlightenment"
            for ne in drift_world.named_events
        )

    def test_universal_enlightenment_fire_once(self, drift_world):
        m = Movement(
            id="movement_0", origin_civ="CivA", origin_turn=0,
            value_affinity="Trade",
            adherents={"CivA": 0, "CivB": 0},
        )
        drift_world.movements.append(m)
        check_cultural_victories(drift_world)
        count = len(drift_world.named_events)
        check_cultural_victories(drift_world)
        assert len(drift_world.named_events) == count
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalVictories -v`
Expected: FAIL — `check_cultural_victories` not defined.

- [ ] **Step 3: Implement check_cultural_victories**

Add to `src/chronicler/culture.py`:

```python
def check_cultural_victories(world: WorldState) -> None:
    """Phase 10 (last): Check for cultural hegemony and universal enlightenment."""
    # Cultural hegemony: one civ's culture > all others combined
    for civ in world.civilizations:
        others_combined = sum(c.culture for c in world.civilizations if c != civ)
        if civ.culture > others_combined:
            if not any(
                ne.event_type == "cultural_hegemony" and civ.name in ne.actors
                for ne in world.named_events
            ):
                world.named_events.append(NamedEvent(
                    name=f"Cultural Hegemony of {civ.name}",
                    event_type="cultural_hegemony",
                    turn=world.turn,
                    actors=[civ.name],
                    description=f"{civ.name} achieves cultural hegemony — their culture surpasses all others combined.",
                    importance=9,
                ))

    # Universal enlightenment: all civs adopt same movement
    all_civ_names = {c.name for c in world.civilizations}
    for movement in world.movements:
        if set(movement.adherents.keys()) == all_civ_names:
            if not any(
                ne.event_type == "universal_enlightenment"
                and movement.id in ne.description
                for ne in world.named_events
            ):
                world.named_events.append(NamedEvent(
                    name=f"Universal Enlightenment ({movement.id})",
                    event_type="universal_enlightenment",
                    turn=world.turn,
                    actors=list(movement.adherents.keys()),
                    description=f"[{movement.id}] Universal enlightenment achieved — all civilizations have adopted this movement.",
                    importance=10,
                ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestCulturalVictories -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/culture.py tests/test_culture.py
git commit -m "feat(m16c): add cultural victory tracking with fire-once guards"
```

---

### Task 18: Wire M16c into Simulation and Snapshot Changes

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/models.py:167-193` (snapshots)
- Modify: `src/chronicler/bundle.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write integration tests**

Append to `tests/test_culture.py`:

```python
class TestM16cIntegration:
    def test_check_cultural_victories_runs_last_in_phase_10(self, drift_world):
        drift_world.civilizations[0].culture = 90
        drift_world.civilizations[1].culture = 10
        from chronicler.simulation import phase_consequences
        phase_consequences(drift_world)
        assert any(
            ne.event_type == "cultural_hegemony"
            for ne in drift_world.named_events
        )


class TestSnapshotChanges:
    def test_civ_snapshot_has_prestige(self):
        from chronicler.models import CivSnapshot
        snap = CivSnapshot(
            population=50, military=50, economy=50, culture=50, stability=50,
            treasury=10, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
            regions=["R1"], leader_name="L", alive=True, prestige=10,
        )
        assert snap.prestige == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestM16cIntegration tests/test_culture.py::TestSnapshotChanges -v`
Expected: FAIL — victories not wired in, CivSnapshot missing prestige.

- [ ] **Step 3: Wire check_cultural_victories into phase_consequences**

In `src/chronicler/simulation.py`, add to imports:

```python
from chronicler.culture import check_cultural_victories
```

In `phase_consequences`, add after `tick_cultural_assimilation(world)` and before the collapse check:

```python
    # M16c: Cultural victory tracking (must run LAST in culture effects)
    check_cultural_victories(world)
```

- [ ] **Step 4: Add prestige to CivSnapshot, cultural_identity to region snapshot, movements to TurnSnapshot**

In `src/chronicler/models.py`, add to `CivSnapshot` (line ~167-180):

```python
    prestige: int = 0  # M16a
```

Add `cultural_identity` to region data in `TurnSnapshot` — change `region_control` to include identity:

```python
    region_cultural_identity: dict[str, str | None] = Field(default_factory=dict)  # M16a
    movements_summary: list[dict] = Field(default_factory=list)  # M16b
```

- [ ] **Step 5: Update bundle.py to include all snapshot data**

In `src/chronicler/bundle.py`, in `assemble_bundle`:
- Add `prestige=civ.prestige` to CivSnapshot construction
- Add `region_cultural_identity={r.name: r.cultural_identity for r in world.regions}` to TurnSnapshot
- Add `movements_summary=[{"id": m.id, "value_affinity": m.value_affinity, "adherent_count": len(m.adherents), "origin_civ": m.origin_civ} for m in world.movements]` to TurnSnapshot

- [ ] **Step 5.5: Add paradigm shift event generation to tech advancement**

In `src/chronicler/simulation.py`, in `phase_technology` (line ~650), after a tech advancement event is generated, check for paradigm shift multipliers and generate a NamedEvent:

```python
            # M16c: Check for paradigm shift (multiplier != 1.0 or special key)
            from chronicler.tech import ERA_BONUSES
            era_bonuses = ERA_BONUSES.get(civ.tech_era, {})
            has_paradigm_shift = any(
                k in era_bonuses and era_bonuses[k] != 1.0
                for k in ("military_multiplier", "fortification_multiplier", "culture_projection_range")
            )
            if has_paradigm_shift:
                world.named_events.append(NamedEvent(
                    name=f"Paradigm Shift: {civ.tech_era.value.title()} Era",
                    event_type="paradigm_shift",
                    turn=world.turn,
                    actors=[civ.name],
                    description=f"{civ.name} enters the {civ.tech_era.value.title()} era, fundamentally changing the rules of engagement.",
                    importance=7,
                ))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestM16cIntegration tests/test_culture.py::TestSnapshotChanges -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Run full test suite**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/models.py src/chronicler/bundle.py tests/test_culture.py
git commit -m "feat(m16c): wire cultural victories into simulation, add prestige to snapshots"
```

---

### Task 19: Named Event Generators

**Files:**
- Modify: `src/chronicler/named_events.py`
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write tests for name generators**

Append to `tests/test_culture.py`:

```python
from chronicler.named_events import (
    generate_movement_name, generate_schism_name,
    generate_propaganda_name, generate_cultural_milestone_name,
)


class TestNameGenerators:
    def test_generate_movement_name_returns_string(self, drift_world):
        name = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_movement_name_deterministic(self, drift_world):
        a = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        b = generate_movement_name(drift_world.civilizations[0], drift_world, seed=42)
        assert a == b

    def test_generate_schism_name_returns_string(self, drift_world):
        name = generate_schism_name(["CivA", "CivB"], drift_world, seed=42)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_propaganda_name_returns_string(self, drift_world):
        name = generate_propaganda_name(
            drift_world.civilizations[0], drift_world.regions[0], drift_world, seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_cultural_milestone_name_returns_string(self, drift_world):
        name = generate_cultural_milestone_name(
            drift_world.civilizations[0], "hegemony", drift_world, seed=42,
        )
        assert isinstance(name, str)
        assert len(name) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestNameGenerators -v`
Expected: FAIL — functions don't exist.

- [ ] **Step 3: Implement name generators**

Append to `src/chronicler/named_events.py`:

```python
MOVEMENT_PREFIXES = [
    "The Way of", "The School of", "The Path of", "The Doctrine of",
    "The Fellowship of", "The Order of", "The Brotherhood of", "The Covenant of",
    "The Teaching of", "The Circle of", "The Creed of", "The Vision of",
]

MOVEMENT_THEMES = [
    "Enlightenment", "Unity", "Liberation", "Harmony", "Justice",
    "Wisdom", "Renewal", "Awakening", "Transcendence", "Redemption",
    "Truth", "Virtue", "Grace", "Resolve", "Fortitude",
]

SCHISM_PREFIXES = [
    "The Great Schism", "The Sundering", "The Division", "The Rift",
    "The Fracture", "The Split", "The Parting", "The Divergence",
]


def generate_movement_name(civ, world, seed: int) -> str:
    """Generate a name for a cultural movement."""
    rng = _seed_rng(seed, world.turn, civ.name + "movement")
    prefix = rng.choice(MOVEMENT_PREFIXES)
    theme = rng.choice(MOVEMENT_THEMES)
    name = f"{prefix} {theme}"
    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


def generate_schism_name(actors: list[str], world, seed: int) -> str:
    """Generate a name for a movement schism."""
    rng = _seed_rng(seed, world.turn, "".join(sorted(actors)))
    prefix = rng.choice(SCHISM_PREFIXES)
    name = f"{prefix} of {actors[0]} and {actors[1]}"
    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


PROPAGANDA_ADJECTIVES = [
    "Grand", "Subtle", "Relentless", "Cunning", "Glorious",
    "Insidious", "Magnificent", "Silent", "Brazen", "Calculated",
]

PROPAGANDA_NOUNS = [
    "Campaign", "Influence", "Proclamation", "Initiative", "Crusade",
    "Offensive", "Mandate", "Projection", "Outreach", "Gambit",
]

MILESTONE_PREFIXES = {
    "hegemony": ["The Age of", "The Dominion of", "The Supremacy of", "The Reign of"],
    "enlightenment": ["The Great Awakening", "The Universal Accord", "The Age of Light", "The Grand Convergence"],
}


def generate_propaganda_name(civ, region, world, seed: int) -> str:
    """Generate a name for a propaganda campaign."""
    rng = _seed_rng(seed, world.turn, civ.name + region.name)
    adj = rng.choice(PROPAGANDA_ADJECTIVES)
    noun = rng.choice(PROPAGANDA_NOUNS)
    name = f"The {adj} {noun} of {region.name}"
    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)


def generate_cultural_milestone_name(civ, milestone_type: str, world, seed: int) -> str:
    """Generate a name for a cultural milestone (hegemony, enlightenment)."""
    rng = _seed_rng(seed, world.turn, civ.name + milestone_type)
    prefixes = MILESTONE_PREFIXES.get(milestone_type, ["The Rise of"])
    prefix = rng.choice(prefixes)
    name = f"{prefix} {civ.name}" if milestone_type == "hegemony" else prefix
    existing = [ne.name for ne in world.named_events]
    return deduplicate_name(name, existing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestNameGenerators -v`
Expected: PASS (5 tests).

**Note:** After this task, update `_check_emergence`, `_process_spread`, `_detect_schisms`, `resolve_invest_culture`, and `check_cultural_victories` to call these name generators instead of inline `f"..."` strings. This wiring is a straightforward search-and-replace — each `name=f"..."` in a NamedEvent constructor should call the appropriate generator.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/named_events.py tests/test_culture.py
git commit -m "feat(m16c): add movement and schism name generators"
```

---

### Task 20: Final Integration Test — Full Simulation Run

**Files:**
- Test: `tests/test_culture.py` (append)

- [ ] **Step 1: Write end-to-end integration test**

Append to `tests/test_culture.py`:

```python
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


class TestM16EndToEnd:
    def test_5_turn_simulation_with_culture(self):
        """Run 5 turns with M16 mechanics active. Verify no crashes."""
        world = generate_world(seed=42, civ_count=4)

        def dummy_narrator(world, events):
            return "Turn narration."

        for _ in range(5):
            from chronicler.action_engine import ActionEngine
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn),
                narrator=dummy_narrator,
                seed=world.seed,
            )

        # Basic sanity checks
        assert world.turn == 5
        assert all(r.cultural_identity is not None for r in world.regions if r.controller is not None)
        # Prestige should have decayed for civs that didn't produce cultural works
        # (just verify no crashes — specific values are tested in unit tests)

    def test_30_turn_simulation_produces_movement(self):
        """Run 30 turns — a movement should emerge."""
        world = generate_world(seed=42, civ_count=4)

        def dummy_narrator(world, events):
            return "Turn narration."

        for _ in range(30):
            from chronicler.action_engine import ActionEngine
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn),
                narrator=dummy_narrator,
                seed=world.seed,
            )

        assert world.turn == 30
        assert len(world.movements) >= 1, "At least one movement should emerge by turn 30"
```

- [ ] **Step 2: Run end-to-end tests**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_culture.py::TestM16EndToEnd -v`
Expected: PASS (2 tests).

- [ ] **Step 3: Run complete test suite for regression check**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_culture.py
git commit -m "test(m16): add end-to-end integration tests for 5 and 30 turn simulations"
```
