# M47d: War Frequency Calibration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce 500-turn war frequency from 204–508 to 5–40 via smooth damper, war-weariness, and peace dividend.

**Architecture:** Three mechanisms in action_engine.py weight pipeline + a per-turn update tick in simulation.py. Two new float fields on Civilization. 12 new K_ constants in tuning.py. No Rust changes.

**Tech Stack:** Python, Pydantic models, pytest

**Spec:** `docs/superpowers/specs/2026-03-19-m47d-war-frequency-design.md`

---

### Task 1: Add K_ Constants to tuning.py

**Files:**
- Modify: `src/chronicler/tuning.py:305-322`

- [ ] **Step 1: Add 12 constant definitions after the Action Engine section (after line 178)**

In `src/chronicler/tuning.py`, add after the existing action engine constants (after `K_INVEST_CULTURE_THRESHOLD`):

```python
# War frequency calibration (M47d) [CALIBRATE]
K_WAR_DAMPER_THRESHOLD = "action.war_damper_threshold"
K_WAR_DAMPER_FLOOR = "action.war_damper_floor"
K_WAR_WEARINESS_DECAY = "action.war_weariness_decay"
K_WAR_WEARINESS_INCREMENT = "action.war_weariness_increment"
K_WAR_PASSIVE_WEARINESS = "action.war_passive_weariness"
K_WAR_WEARINESS_DIVISOR = "action.war_weariness_divisor"
K_PEACE_MOMENTUM_BONUS = "action.peace_momentum_bonus"
K_PEACE_MOMENTUM_CAP = "action.peace_momentum_cap"
K_PEACE_MOMENTUM_WAR_DECAY = "action.peace_momentum_war_decay"
K_PEACE_MOMENTUM_DEFENDER_DECAY = "action.peace_momentum_defender_decay"
K_PEACE_DEVELOP_DIVISOR = "action.peace_develop_divisor"
K_PEACE_TRADE_DIVISOR = "action.peace_trade_divisor"
```

- [ ] **Step 2: Add all 12 to the KNOWN_OVERRIDES set**

In the `KNOWN_OVERRIDES` set (line ~305, the `# Action Engine` section), add after `K_INVEST_CULTURE_THRESHOLD`:

```python
    # War frequency calibration (M47d)
    K_WAR_DAMPER_THRESHOLD, K_WAR_DAMPER_FLOOR,
    K_WAR_WEARINESS_DECAY, K_WAR_WEARINESS_INCREMENT,
    K_WAR_PASSIVE_WEARINESS, K_WAR_WEARINESS_DIVISOR,
    K_PEACE_MOMENTUM_BONUS, K_PEACE_MOMENTUM_CAP,
    K_PEACE_MOMENTUM_WAR_DECAY, K_PEACE_MOMENTUM_DEFENDER_DECAY,
    K_PEACE_DEVELOP_DIVISOR, K_PEACE_TRADE_DIVISOR,
```

- [ ] **Step 3: Verify**

Run: `python -c "from chronicler.tuning import K_WAR_DAMPER_THRESHOLD, KNOWN_OVERRIDES; assert K_WAR_DAMPER_THRESHOLD in KNOWN_OVERRIDES; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/tuning.py
git commit -m "feat(m47d): add 12 war frequency calibration constants"
```

---

### Task 2: Add Model Fields

**Files:**
- Modify: `src/chronicler/models.py:300,608`

- [ ] **Step 1: Add fields to Civilization class**

In `src/chronicler/models.py`, after `previous_majority_faith` (line 300), add:

```python
    # M47d: War frequency calibration
    war_weariness: float = 0.0
    peace_momentum: float = 0.0
```

- [ ] **Step 2: Add fields to CivSnapshot class**

After `last_action` (line 608), add:

```python
    # M47d: War frequency analytics
    war_weariness: float = 0.0
    peace_momentum: float = 0.0
```

- [ ] **Step 3: Verify**

Run: `python -c "from chronicler.models import Civilization, CivSnapshot, Leader, TechEra; c = Civilization(name='X', population=50, military=50, economy=50, culture=50, stability=50, tech_era=TechEra.IRON, treasury=100, leader=Leader(name='L', trait='bold', reign_start=0), regions=['R']); assert c.war_weariness == 0.0; assert c.peace_momentum == 0.0; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m47d): add war_weariness and peace_momentum fields"
```

---

### Task 3: Smooth WAR Damper (TDD)

**Files:**
- Modify: `src/chronicler/action_engine.py:864-866`
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_action_engine.py`:

```python
from chronicler.tuning import K_WAR_DAMPER_THRESHOLD, K_WAR_DAMPER_FLOOR


class TestWarDamper:
    """M47d: Smooth WAR damper replaces binary cliff."""

    def test_high_stability_no_penalty(self, engine_world):
        """Stability >= threshold: WAR weight unchanged."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        # WAR should not be dampened (multiplier = 1.0)
        # Just verify WAR is non-zero and not suppressed
        assert weights[ActionType.WAR] > 0

    def test_mid_stability_partial_damper(self, engine_world):
        """Stability at half threshold: WAR weight halved relative to undampened."""
        civ = engine_world.civilizations[0]
        civ.stability = 15  # half of default threshold 30
        engine = ActionEngine(engine_world)
        weights_low = engine.compute_weights(civ)

        civ.stability = 60  # above threshold, no damper
        weights_high = engine.compute_weights(civ)

        # WAR at stability=15 should be ~50% of WAR at stability=60
        ratio = weights_low[ActionType.WAR] / weights_high[ActionType.WAR]
        assert 0.45 <= ratio <= 0.55, f"Expected ~0.5 ratio, got {ratio}"

    def test_zero_stability_uses_floor(self, engine_world):
        """Stability 0: WAR weight at floor, not zero."""
        civ = engine_world.civilizations[0]
        civ.stability = 0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > 0, "WAR should not be zero at stability 0"

    def test_damper_does_not_amplify(self, engine_world):
        """Stability above threshold should NOT boost WAR weight."""
        civ = engine_world.civilizations[0]
        engine = ActionEngine(engine_world)

        civ.stability = 30
        weights_at_threshold = engine.compute_weights(civ)

        civ.stability = 90
        weights_above = engine.compute_weights(civ)

        # WAR weight should be identical above threshold (both get 1.0x)
        assert abs(weights_at_threshold[ActionType.WAR] - weights_above[ActionType.WAR]) < 0.001

    def test_diplomacy_boost_unchanged(self, engine_world):
        """DIPLOMACY *= 3.0 still fires at stability <= 20."""
        civ = engine_world.civilizations[0]
        civ.stability = 15
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        # DIPLOMACY should be boosted (binary cliff preserved)
        assert weights[ActionType.DIPLOMACY] > weights[ActionType.DEVELOP]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_engine.py::TestWarDamper -v`
Expected: `test_mid_stability_partial_damper` and `test_damper_does_not_amplify` FAIL (binary cliff gives 0.1x at stability 15, not 0.5x)

- [ ] **Step 3: Implement smooth damper**

In `src/chronicler/action_engine.py`, replace lines 864-866:

```python
        if civ.stability <= 20:
            weights[ActionType.DIPLOMACY] *= 3.0
            weights[ActionType.WAR] *= 0.1
```

With:

```python
        # M47d: Smooth WAR damper — linear ramp from floor to 1.0
        # Replaces binary cliff. DIPLOMACY boost stays as binary (qualitative regime change).
        threshold = get_override(self.world, K_WAR_DAMPER_THRESHOLD, 30.0)
        floor = get_override(self.world, K_WAR_DAMPER_FLOOR, 0.05)
        war_damper = max(min(civ.stability / threshold, 1.0), floor)
        weights[ActionType.WAR] *= war_damper
        if civ.stability <= 20:
            weights[ActionType.DIPLOMACY] *= 3.0
```

Add imports at the top of `action_engine.py` (with existing tuning imports):

```python
from chronicler.tuning import K_WAR_DAMPER_THRESHOLD, K_WAR_DAMPER_FLOOR
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_action_engine.py::TestWarDamper -v`
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(m47d): smooth WAR damper replacing binary cliff"
```

---

### Task 4: War-Weariness Weight Effect (TDD)

**Files:**
- Modify: `src/chronicler/action_engine.py:841` (insert after aggression bias, before streak-breaker)
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_action_engine.py`:

```python
from chronicler.tuning import K_WAR_WEARINESS_DIVISOR


class TestWarWeariness:
    """M47d: War-weariness suppresses WAR weight."""

    def test_zero_weariness_no_penalty(self, engine_world):
        """No weariness: WAR weight unaffected."""
        civ = engine_world.civilizations[0]
        civ.war_weariness = 0.0
        engine = ActionEngine(engine_world)
        weights_zero = engine.compute_weights(civ)

        # Compare to a small weariness — zero should give higher WAR
        civ.war_weariness = 5.0
        weights_weary = engine.compute_weights(civ)
        assert weights_zero[ActionType.WAR] > weights_weary[ActionType.WAR]

    def test_high_weariness_suppresses_war(self, engine_world):
        """Chronic warmonger weariness (~23): WAR suppressed to ~12%."""
        civ = engine_world.civilizations[0]
        civ.stability = 50  # above damper threshold
        engine = ActionEngine(engine_world)

        civ.war_weariness = 0.0
        war_fresh = engine.compute_weights(civ)[ActionType.WAR]

        civ.war_weariness = 23.0  # chronic warmonger steady state
        war_weary = engine.compute_weights(civ)[ActionType.WAR]

        ratio = war_weary / war_fresh
        # 1/(1 + 23/3) ≈ 0.115
        assert 0.08 <= ratio <= 0.15, f"Expected ~0.12 ratio, got {ratio}"

    def test_weariness_does_not_affect_other_actions(self, engine_world):
        """Weariness only touches WAR, not DEVELOP or TRADE."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.war_weariness = 0.0
        weights_fresh = engine.compute_weights(civ)

        civ.war_weariness = 10.0
        weights_weary = engine.compute_weights(civ)

        # DEVELOP should be identical (weariness doesn't touch it)
        assert abs(weights_fresh[ActionType.DEVELOP] - weights_weary[ActionType.DEVELOP]) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_engine.py::TestWarWeariness -v`
Expected: FAIL — weariness field exists but isn't read by compute_weights yet

- [ ] **Step 3: Implement weariness penalty in compute_weights**

In `src/chronicler/action_engine.py`, after the aggression bias line (after `weights[ActionType.WAR] *= get_multiplier(...)` for K_AGGRESSION_BIAS) and BEFORE the streak-breaker (`history = self.world.action_history...`), insert:

```python
        # M47d: War-weariness penalty — suppresses WAR after multiplicative boosters
        if civ.war_weariness > 0:
            divisor = get_override(self.world, K_WAR_WEARINESS_DIVISOR, 3.0)
            weariness_penalty = 1.0 / (1.0 + civ.war_weariness / divisor)
            weights[ActionType.WAR] *= weariness_penalty
```

Add import:

```python
from chronicler.tuning import K_WAR_WEARINESS_DIVISOR
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_action_engine.py::TestWarWeariness -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(m47d): war-weariness WAR weight penalty"
```

---

### Task 5: Peace Dividend Weight Effect (TDD)

**Files:**
- Modify: `src/chronicler/action_engine.py` (same insertion point as Task 4, right after weariness)
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_action_engine.py`:

```python
from chronicler.tuning import K_PEACE_DEVELOP_DIVISOR, K_PEACE_TRADE_DIVISOR


class TestPeaceDividend:
    """M47d: Peace momentum boosts DEVELOP and TRADE weights."""

    def test_zero_momentum_no_bonus(self, engine_world):
        """No peace momentum: DEVELOP/TRADE unaffected."""
        civ = engine_world.civilizations[0]
        civ.peace_momentum = 0.0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        # Baseline — just verify they're positive
        assert weights[ActionType.DEVELOP] > 0
        assert weights[ActionType.TRADE] > 0

    def test_high_momentum_boosts_develop_trade(self, engine_world):
        """20 turns of peace: DEVELOP and TRADE get 3x bonus."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.peace_momentum = 0.0
        develop_base = engine.compute_weights(civ)[ActionType.DEVELOP]
        trade_base = engine.compute_weights(civ)[ActionType.TRADE]

        civ.peace_momentum = 20.0  # cap value
        develop_peace = engine.compute_weights(civ)[ActionType.DEVELOP]
        trade_peace = engine.compute_weights(civ)[ActionType.TRADE]

        # 1 + 20/10 = 3.0x bonus
        develop_ratio = develop_peace / develop_base
        trade_ratio = trade_peace / trade_base
        assert 2.8 <= develop_ratio <= 3.2, f"Expected ~3.0 DEVELOP ratio, got {develop_ratio}"
        assert 2.8 <= trade_ratio <= 3.2, f"Expected ~3.0 TRADE ratio, got {trade_ratio}"

    def test_momentum_does_not_affect_war(self, engine_world):
        """Peace momentum only touches DEVELOP/TRADE, not WAR."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.peace_momentum = 0.0
        war_base = engine.compute_weights(civ)[ActionType.WAR]

        civ.peace_momentum = 20.0
        war_peace = engine.compute_weights(civ)[ActionType.WAR]

        assert abs(war_base - war_peace) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_engine.py::TestPeaceDividend -v`
Expected: FAIL — peace_momentum field exists but compute_weights doesn't read it

- [ ] **Step 3: Implement peace dividend in compute_weights**

Right after the weariness block (from Task 4), insert:

```python
        # M47d: Peace dividend — boost DEVELOP/TRADE from peace momentum
        if civ.peace_momentum > 0:
            develop_divisor = get_override(self.world, K_PEACE_DEVELOP_DIVISOR, 10.0)
            trade_divisor = get_override(self.world, K_PEACE_TRADE_DIVISOR, 10.0)
            weights[ActionType.DEVELOP] *= 1.0 + civ.peace_momentum / develop_divisor
            weights[ActionType.TRADE] *= 1.0 + civ.peace_momentum / trade_divisor
```

Add imports:

```python
from chronicler.tuning import K_PEACE_DEVELOP_DIVISOR, K_PEACE_TRADE_DIVISOR
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_action_engine.py::TestPeaceDividend -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(m47d): peace dividend DEVELOP/TRADE weight boost"
```

---

### Task 6: Weariness/Momentum Update Tick (TDD)

**Files:**
- Modify: `src/chronicler/simulation.py:1273` (insert after `phase_action()` call)
- Test: `tests/test_simulation.py`

This is the per-turn update logic that modifies `war_weariness` and `peace_momentum` on each living civ.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_simulation.py`:

```python
from chronicler.models import (
    ActionType, Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)
from chronicler.simulation import update_war_frequency_accumulators


def _make_world_with_wars():
    """Create a minimal world for testing weariness/momentum tick."""
    civ_a = Civilization(
        name="Civ A", population=50, military=50, economy=50, culture=50,
        stability=50, tech_era=TechEra.IRON, treasury=150,
        leader=Leader(name="Vaelith", trait="aggressive", reign_start=0),
        regions=["Region A"],
    )
    civ_b = Civilization(
        name="Civ B", population=50, military=50, economy=50, culture=50,
        stability=50, tech_era=TechEra.IRON, treasury=150,
        leader=Leader(name="Gorath", trait="cautious", reign_start=0),
        regions=["Region B"],
    )
    civ_dead = Civilization(
        name="Civ Dead", population=0, military=0, economy=0, culture=0,
        stability=0, tech_era=TechEra.TRIBAL, treasury=0,
        leader=Leader(name="Ghost", trait="cautious", reign_start=0),
        regions=[],  # dead
    )
    world = WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ B"),
        ],
        civilizations=[civ_a, civ_b, civ_dead],
    )
    return world


class TestWarFrequencyAccumulators:
    """M47d: Per-turn weariness and momentum update tick."""

    def test_war_action_adds_increment(self):
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["war"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].war_weariness > 0.0  # Civ A chose WAR
        assert world.civilizations[1].war_weariness == 0.0  # Civ B did not

    def test_weariness_decays(self):
        world = _make_world_with_wars()
        world.civilizations[0].war_weariness = 10.0
        world.action_history = {"Civ A": ["develop"]}  # no war this turn
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].war_weariness < 10.0  # decayed
        assert world.civilizations[0].war_weariness == pytest.approx(10.0 * 0.95)

    def test_passive_weariness_from_active_wars(self):
        world = _make_world_with_wars()
        world.active_wars = [("Civ A", "Civ B")]  # Civ A is attacker
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        # Both participants get passive weariness
        assert world.civilizations[0].war_weariness > 0  # attacker
        assert world.civilizations[1].war_weariness > 0  # defender

    def test_peace_momentum_increments(self):
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == 1.0
        assert world.civilizations[1].peace_momentum == 1.0

    def test_peace_momentum_caps(self):
        world = _make_world_with_wars()
        world.civilizations[0].peace_momentum = 19.5
        world.action_history = {"Civ A": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == 20.0  # capped

    def test_aggressor_peace_decay(self):
        world = _make_world_with_wars()
        world.civilizations[0].peace_momentum = 20.0
        world.active_wars = [("Civ A", "Civ B")]  # Civ A is w[0] = aggressor
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == pytest.approx(20.0 * 0.3)

    def test_defender_peace_decay(self):
        world = _make_world_with_wars()
        world.civilizations[1].peace_momentum = 20.0
        world.active_wars = [("Civ A", "Civ B")]  # Civ B is w[1] = defender
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        # Defender gets gentler decay (0.8x)
        assert world.civilizations[1].peace_momentum == pytest.approx(20.0 * 0.8)

    def test_declaration_turn_double_counting(self):
        """Civ that declares WAR gets INCREMENT + PASSIVE on same turn (intentional)."""
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["war"]}
        world.active_wars = [("Civ A", "Civ B")]  # new war already in active_wars
        update_war_frequency_accumulators(world)
        # INCREMENT (1.0) + decay of 0 * 0.95 + PASSIVE (0.15) = 1.15
        assert world.civilizations[0].war_weariness == pytest.approx(1.15)

    def test_dead_civ_skipped(self):
        world = _make_world_with_wars()
        world.civilizations[2].war_weariness = 5.0  # dead civ
        world.civilizations[2].peace_momentum = 10.0
        world.action_history = {}
        update_war_frequency_accumulators(world)
        # Dead civ should not be updated
        assert world.civilizations[2].war_weariness == 5.0
        assert world.civilizations[2].peace_momentum == 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulation.py::TestWarFrequencyAccumulators -v`
Expected: FAIL — `update_war_frequency_accumulators` does not exist

- [ ] **Step 3: Implement the update function**

In `src/chronicler/simulation.py`, add the function (near other phase functions):

```python
from chronicler.tuning import (
    K_WAR_WEARINESS_DECAY, K_WAR_WEARINESS_INCREMENT,
    K_WAR_PASSIVE_WEARINESS, K_PEACE_MOMENTUM_BONUS,
    K_PEACE_MOMENTUM_CAP, K_PEACE_MOMENTUM_WAR_DECAY,
    K_PEACE_MOMENTUM_DEFENDER_DECAY,
)
from chronicler.tuning import get_override


def update_war_frequency_accumulators(world: WorldState) -> None:
    """M47d: Per-turn update of war_weariness and peace_momentum on each living civ."""
    decay = get_override(world, K_WAR_WEARINESS_DECAY, 0.95)
    increment = get_override(world, K_WAR_WEARINESS_INCREMENT, 1.0)
    passive = get_override(world, K_WAR_PASSIVE_WEARINESS, 0.15)
    peace_bonus = get_override(world, K_PEACE_MOMENTUM_BONUS, 1.0)
    peace_cap = get_override(world, K_PEACE_MOMENTUM_CAP, 20.0)
    aggressor_decay = get_override(world, K_PEACE_MOMENTUM_WAR_DECAY, 0.3)
    defender_decay = get_override(world, K_PEACE_MOMENTUM_DEFENDER_DECAY, 0.8)

    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue  # dead civ guard

        # --- War weariness ---
        history = world.action_history.get(civ.name, [])
        chose_war = len(history) > 0 and history[-1] == ActionType.WAR.value

        if chose_war:
            civ.war_weariness = civ.war_weariness * decay + increment
        else:
            civ.war_weariness *= decay

        # Passive weariness from active wars
        for war in world.active_wars:
            if civ.name in war:
                civ.war_weariness += passive

        # --- Peace momentum ---
        is_aggressor = chose_war or any(w[0] == civ.name for w in world.active_wars)
        is_defender = any(w[1] == civ.name for w in world.active_wars) and not is_aggressor
        is_at_peace = not is_aggressor and not is_defender

        if is_at_peace:
            civ.peace_momentum = min(civ.peace_momentum + peace_bonus, peace_cap)
        elif is_aggressor:
            civ.peace_momentum *= aggressor_decay
        elif is_defender:
            civ.peace_momentum *= defender_decay
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_simulation.py::TestWarFrequencyAccumulators -v`
Expected: All 8 PASS

- [ ] **Step 5: Wire into run_turn()**

In `src/chronicler/simulation.py`, in `run_turn()`, after line 1273 (`turn_events.extend(phase_action(...))`), insert:

```python
    # M47d: Update war-weariness and peace momentum accumulators
    update_war_frequency_accumulators(world)
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m47d): war-weariness and peace momentum update tick"
```

---

### Task 7: Extinction Resets (TDD)

**Files:**
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_simulation.py`

When a civ goes extinct (regions drops to 0), reset both accumulators to prevent restored civs from inheriting stale state.

- [ ] **Step 1: Write failing test**

Add to `tests/test_simulation.py`:

```python
from chronicler.simulation import reset_war_frequency_on_extinction


class TestExtinctionReset:
    """M47d: Reset weariness/momentum when civ goes extinct."""

    def test_extinction_resets_both_fields(self):
        world = _make_world_with_wars()
        civ = world.civilizations[0]
        civ.war_weariness = 15.0
        civ.peace_momentum = 10.0
        civ.regions = []  # goes extinct
        reset_war_frequency_on_extinction(civ)
        assert civ.war_weariness == 0.0
        assert civ.peace_momentum == 0.0

    def test_living_civ_not_reset(self):
        world = _make_world_with_wars()
        civ = world.civilizations[0]
        civ.war_weariness = 15.0
        civ.peace_momentum = 10.0
        reset_war_frequency_on_extinction(civ)
        assert civ.war_weariness == 15.0
        assert civ.peace_momentum == 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulation.py::TestExtinctionReset -v`
Expected: FAIL — `reset_war_frequency_on_extinction` does not exist

- [ ] **Step 3: Implement reset function**

In `src/chronicler/simulation.py`:

```python
def reset_war_frequency_on_extinction(civ: Civilization) -> None:
    """M47d: Reset accumulators when civ loses all regions."""
    if len(civ.regions) == 0:
        civ.war_weariness = 0.0
        civ.peace_momentum = 0.0
```

- [ ] **Step 4: Wire into existing extinction sites**

Search for places where a civ's last region is removed. The three known sites are:

1. `action_engine.py` `_resolve_war_action()` — after conquest removes last region
2. `politics.py` `check_twilight_absorption()` — after absorption removes regions
3. `politics.py` exile restoration (~line 1005) — `absorber.regions.remove(target_region)` can leave the absorber with 0 regions

At each site, after the region transfer that can leave a civ with 0 regions, add:

```python
from chronicler.simulation import reset_war_frequency_on_extinction
# ... after region removal ...
if len(defeated_civ.regions) == 0:
    reset_war_frequency_on_extinction(defeated_civ)
```

**Note for implementer:** Grep for `civ.regions.remove` and `civ.regions = []` to verify all extinction paths are covered. Add the reset call at each one where `len(civ.regions)` can reach 0.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_simulation.py::TestExtinctionReset -v`
Expected: All 2 PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/action_engine.py src/chronicler/politics.py tests/test_simulation.py
git commit -m "feat(m47d): extinction resets for war-weariness and peace momentum"
```

---

### Task 8: Wire CivSnapshot in main.py

**Files:**
- Modify: `src/chronicler/main.py:307`

- [ ] **Step 1: Add fields to CivSnapshot constructor**

In `src/chronicler/main.py`, in the `CivSnapshot(...)` constructor (around line 307, after the `gini=...` line), add:

```python
                    war_weariness=civ.war_weariness,
                    peace_momentum=civ.peace_momentum,
```

- [ ] **Step 2: Verify**

Run: `python -c "print('OK')"`
(No standalone test needed — this is wiring. The integration test in Task 9 will cover it.)

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/main.py
git commit -m "feat(m47d): wire war_weariness and peace_momentum into CivSnapshot"
```

---

### Task 9: Integration Smoke Test

**Files:**
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write integration test**

Add to `tests/test_action_engine.py`:

```python
class TestWarFrequencyIntegration:
    """M47d: Verify all three mechanisms work together."""

    def test_combined_suppression(self, engine_world):
        """Low stability + high weariness + zero momentum = heavily suppressed WAR."""
        civ = engine_world.civilizations[0]
        civ.stability = 15        # damper: 0.5x
        civ.war_weariness = 10.0  # weariness: 1/(1+10/3) ≈ 0.23x
        civ.peace_momentum = 0.0  # no peace bonus
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)

        # WAR should be heavily suppressed relative to other actions
        assert weights[ActionType.WAR] < weights[ActionType.DEVELOP]
        assert weights[ActionType.WAR] < weights[ActionType.DIPLOMACY]

    def test_peaceful_civ_prefers_develop(self, engine_world):
        """High stability + zero weariness + high momentum = DEVELOP/TRADE dominant."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        civ.war_weariness = 0.0
        civ.peace_momentum = 20.0  # max
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)

        # DEVELOP and TRADE should be boosted significantly
        assert weights[ActionType.DEVELOP] > weights[ActionType.WAR]
        assert weights[ActionType.TRADE] > weights[ActionType.WAR]

    def test_warmonger_still_can_fight(self, engine_world):
        """Even with high weariness, WAR is not zero — just suppressed."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        civ.war_weariness = 23.0  # chronic warmonger steady state
        civ.peace_momentum = 0.0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > 0, "WAR should never be zero from weariness alone"
```

- [ ] **Step 2: Run all M47d tests**

Run: `pytest tests/test_action_engine.py::TestWarDamper tests/test_action_engine.py::TestWarWeariness tests/test_action_engine.py::TestPeaceDividend tests/test_action_engine.py::TestWarFrequencyIntegration tests/test_simulation.py::TestWarFrequencyAccumulators tests/test_simulation.py::TestExtinctionReset -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite (excluding known hangs)**

Run: `pytest tests/ --ignore=tests/test_bundle.py --ignore=tests/test_m36_regression.py --ignore=tests/test_main.py -x -q`
Expected: All pass (no regressions from M47d changes)

- [ ] **Step 4: Commit**

```bash
git add tests/test_action_engine.py
git commit -m "test(m47d): integration smoke tests for war frequency mechanisms"
```

---

### Task 10: Update Progress Doc

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Update M47d section in progress doc**

Move M47d from "Ready for Implementation" to "Merged Milestones" section. Update with:
- Commit hashes
- Test counts
- Constants summary
- Note that 200-seed validation is pending

- [ ] **Step 2: Update CLAUDE.md if needed**

If any cross-cutting rules changed (none expected for M47d), update CLAUDE.md.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs: update progress for M47d war frequency calibration"
```
