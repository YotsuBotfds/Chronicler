# M47 Phase 6 Tuning Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire 8 Tier 1 multipliers, fix severity inconsistency (25 sites), fix civ-removal crash, add batch tatonnement, implement 9 analytics extractors, and run the first 200-seed health check of Phase 6.

**Architecture:** Three sequential phases: Tier A (civ-removal bug fix), M47a (consumer wiring + severity fix + tatonnement), M47b (extractors + health check). M47a and M47b can parallelize after Tier A. See `docs/superpowers/specs/2026-03-19-m47-tuning-pass-design.md` for full design.

**Tech Stack:** Python 3.12, Rust stable, PyO3/Arrow FFI, pytest, cargo nextest

**Spec:** `docs/superpowers/specs/2026-03-19-m47-tuning-pass-design.md`

**Pre-plan investigation findings (bugs that were NOT bugs):**

- **1a (Phase 10 double-apply keep): NOT A BUG.** In hybrid mode, `acc.apply_keep(world)` runs at simulation.py:1281, applying treasury/asabiya/prestige. The same `acc` is then passed to Phase 10 (line 1316), but Phase 10 routes mutations to `world.pending_shocks` via `CivShock` objects — it never calls `acc.apply_keep()` or `acc.apply()` again. The accumulator is consumed for signal routing, not reapplied. Verified: grep for `acc.apply` finds only two call sites in the entire codebase (lines 1281 and 1294), neither inside Phase 10.

- **1c (Accumulator not threaded): NOT A BUG.** The flagged functions (`apply_value_drift`, `apply_balance_of_power`, `check_federation_formation`, `check_twilight_absorption`) only modify relationship state (dispositions, allied_turns), structural state (federation membership, region controllers), or derived metrics (peak_region_count). None mutate civ stats (stability, prestige, asabiya, economy, military, population, treasury). All actual stat-mutating functions already have `acc` parameters. `apply_asabiya_dynamics` already takes `acc` (simulation.py:567). `compute_all_stress` was not found in the codebase.

- **1e (Federation/balance missing acc): NOT A BUG.** Same finding as 1c. `check_federation_formation()` creates/modifies `Federation` objects in `world.federations`. `trigger_federation_defense()` modifies disposition. `apply_balance_of_power()` modifies `world.relationships` disposition and `balance_of_power_turns`. `check_twilight_absorption()` transfers region controllers. None of these touch civ stat fields that the accumulator routes.

---

## File Map

### Tier A: Civ-Removal Fix
- Modify: `src/chronicler/politics.py:1194-1197` (remove the `remove()` call)
- Modify: `src/chronicler/agent_bridge.py:1004` (add dead-civ guard in `_write_back`)
- Modify: ~15 files with `for civ in world.civilizations` loops needing `len(civ.regions) > 0` guards (see Task 1 for full list)
- Test: `tests/test_politics.py` (new integration test for twilight absorption + next turn)

### M47a: Consumer Wiring (Step 1)
- Modify: `src/chronicler/action_engine.py:797` (K_AGGRESSION_BIAS)
- Modify: `src/chronicler/economy.py:419` (K_TRADE_FRICTION)
- Modify: `src/chronicler/ecology.py:118` (K_RESOURCE_ABUNDANCE)
- Modify: `src/chronicler/emergence.py:87` (K_SEVERITY_MULTIPLIER + signature change)
- Modify: `src/chronicler/politics.py:126` (K_SECESSION_LIKELIHOOD)
- Modify: `src/chronicler/tech.py:99,106` (K_TECH_DIFFUSION_RATE)
- Modify: `src/chronicler/tuning.py:162-172` (multiplier validation in load_tuning)
- Modify: `src/chronicler/simulation.py` (11 severity call sites: lines 137, 156, 179, 640, 665, 681, 706, 713, 800 + world param)
- Modify: `src/chronicler/ecology.py:283` (severity call site + world param)
- Modify: `src/chronicler/factions.py:413` (severity call site + world param)
- Modify: `chronicler-agents/src/signals.rs` (2 new CivSignals fields)
- Modify: `chronicler-agents/src/culture_tick.rs:64` (drift multiplier)
- Modify: `chronicler-agents/src/conversion_tick.rs:64` (religion multiplier)
- Modify: `src/chronicler/agent_bridge.py` (2 new columns in build_civ_batch)
- Modify: `src/chronicler/culture.py:69` (Python-side drift multiplier)
- Modify: `src/chronicler/religion.py:27,50,514` (Python-side religion consumers)
- Test: `tests/test_tuning.py` (new — multiplier validation, per-consumer unit tests)
- Test: `tests/test_emergence.py:292-309` (update 4 existing tests for new signature)
- Test: `chronicler-agents/tests/` (update CivSignals fixtures)

### M47a: Severity Inconsistency Fix (Step 3)
- Modify: `src/chronicler/action_engine.py:330,494,504` (3 missing sites)
- Modify: `src/chronicler/climate.py:221` (1 missing site)
- Modify: `src/chronicler/culture.py:226` (1 missing site)
- Modify: `src/chronicler/ecology.py:307` (1 missing site)
- Modify: `src/chronicler/emergence.py:398` (1 missing site)
- Modify: `src/chronicler/leaders.py:221,229` (2 missing sites)
- Modify: `src/chronicler/politics.py` (11 missing sites: lines 52, 257, 322, 613, 624, 688, 865, 903, 1220, plus 2 more)
- Modify: `src/chronicler/simulation.py:299,316,741,764` (4 missing sites)
- Modify: `src/chronicler/succession.py:254` (1 missing site)
- Test: `tests/test_severity.py` (new — spot-check 3-4 representative sites, both `acc.add()` path AND direct-mutation `else` path)

### M47a: Tatonnement (Step 4)
- Modify: `src/chronicler/economy.py` (wrap lines 768-841 in iteration loop)
- Test: `tests/test_economy.py` (new tatonnement convergence tests)

### M47a: Pydantic Cleanup (Step 5)
- Modify: `src/chronicler/models.py` (remove misleading ge=/le= kwargs)

### M47b: Extractors + Structural
- Modify: `src/chronicler/models.py` (add gini field to CivSnapshot, delete CivThematicContext)
- Modify: `src/chronicler/main.py:278` (populate gini in snapshot assembly)
- Modify: `src/chronicler/models.py` (add region_map cached property to WorldState)
- Modify: `src/chronicler/analytics.py` (9 new extractors)
- Test: `tests/test_analytics.py` (new extractor tests)

---

## Task 1: Tier A — Civ-Removal Fix

**Files:**
- Modify: `src/chronicler/politics.py:1194-1197`
- Modify: `src/chronicler/agent_bridge.py:1004`
- Modify: Multiple files (see step 5)
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing test — dead civ stays in list after twilight absorption**

```python
def test_twilight_absorption_keeps_dead_civ_in_list():
    """After twilight absorption, dead civ remains in world.civilizations with 0 regions."""
    world = make_test_world(civs=3, regions=6)
    # Drain one civ to 0 regions to trigger twilight
    target = world.civilizations[2]
    target.regions = []
    target.stability = 0
    initial_count = len(world.civilizations)
    check_twilight_absorption(world)
    # Civ should still be in the list
    assert len(world.civilizations) == initial_count
    assert len(target.regions) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py::test_twilight_absorption_keeps_dead_civ_in_list -v`
Expected: FAIL (remove() call at line 1197 removes the civ)

- [ ] **Step 3: Fix — delete the remove() call**

In `src/chronicler/politics.py`, delete lines 1196-1197 only:
```python
# DELETE these two lines:
    for civ in to_remove:
        world.civilizations.remove(civ)
```

Do NOT delete lines 1194-1195 (closing paren of the Event constructor + blank line). The `to_remove` list and event generation above stay — we still need the twilight_absorption events. Only the list mutation is removed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py::test_twilight_absorption_keeps_dead_civ_in_list -v`
Expected: PASS

- [ ] **Step 5: Add dead-civ guard in _write_back()**

In `src/chronicler/agent_bridge.py:1004`, add guard:
```python
    for row_idx, civ_id in enumerate(civ_ids):
        if civ_id >= len(world.civilizations):
            continue
        civ = world.civilizations[civ_id]
        if len(civ.regions) == 0:
            continue  # Skip dead civs whose agents haven't loyalty-flipped
```

- [ ] **Step 6: Add dead-civ guards to critical simulation loops**

Add `if len(civ.regions) == 0: continue` at the top of the loop body in these **critical** locations (data corruption risk):

| File | Line | Function |
|---|---|---|
| `simulation.py` | 208 | Military maintenance |
| `simulation.py` | 388 | Reset last_income |
| `simulation.py` | 532 | Action selection phase |
| `simulation.py` | 573 | Military advance |
| `simulation.py` | 844 | Mercenary hiring |
| `simulation.py` | 1057 | phase_technology |
| `simulation.py` | 1135 | phase_leader_dynamics |
| `culture.py` | 340 | check_cultural_victories |
| `culture.py` | 376 | tick_prestige |
| `infrastructure.py` | 254 | Temple prestige |
| `traditions.py` | 26,30,88 | War/economy tracking, tradition acquisition |
| `politics.py` | 1038 | update_peak_regions |
| `politics.py` | 1063 | update_decline_tracking |

Non-critical loops (read-only, cosmetic, or narration-only) can be deferred. Focus on loops that mutate state.

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 8: Run `--agents=off` bit-identical gate**

Run: `python -m chronicler --seed 42 --turns 50 --agents off --simulate-only > /tmp/gate_a.json && python -m chronicler --seed 42 --turns 50 --agents off --simulate-only > /tmp/gate_b.json && diff /tmp/gate_a.json /tmp/gate_b.json`
Expected: No diff (deterministic). This captures the pre-M47a baseline.

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/politics.py src/chronicler/agent_bridge.py src/chronicler/simulation.py src/chronicler/culture.py src/chronicler/infrastructure.py src/chronicler/traditions.py tests/test_politics.py
git commit -m "fix: stop removing dead civs from world.civilizations list

Twilight absorption was removing civs via world.civilizations.remove(),
invalidating Rust-side civ_affinity indices. Dead civs now stay in the
list (len(regions)==0 convention). Guards added to critical simulation
loops and _write_back().

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: M47a Step 1 — Wire Python-Side Multiplier Consumers (5 of 8)

**Files:**
- Modify: `src/chronicler/action_engine.py:797`
- Modify: `src/chronicler/economy.py:419`
- Modify: `src/chronicler/ecology.py:118`
- Modify: `src/chronicler/politics.py:126`
- Modify: `src/chronicler/tech.py:99,102`
- Modify: `src/chronicler/tuning.py:162-172`
- Test: `tests/test_tuning.py` (new file)

- [ ] **Step 1: Write failing tests for multiplier validation**

Create `tests/test_tuning.py`:
```python
import pytest
from chronicler.tuning import load_tuning, PRESETS

def test_load_tuning_rejects_zero_multiplier(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("multiplier:\n  severity: 0.0\n")
    with pytest.raises(ValueError, match="must be > 0"):
        load_tuning(p)

def test_load_tuning_rejects_negative_multiplier(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("multiplier:\n  aggression_bias: -1.0\n")
    with pytest.raises(ValueError, match="must be > 0"):
        load_tuning(p)

def test_load_tuning_accepts_positive_multiplier(tmp_path):
    p = tmp_path / "ok.yaml"
    p.write_text("multiplier:\n  severity: 1.5\n")
    result = load_tuning(p)
    assert result["multiplier.severity"] == 1.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tuning.py -v`
Expected: First two FAIL (no validation), third PASS

- [ ] **Step 3: Implement multiplier validation in load_tuning()**

In `src/chronicler/tuning.py`, after the `unknown` key warning block (line 172), add:
```python
    for key, value in flat.items():
        if key.startswith("multiplier.") and value <= 0:
            raise ValueError(
                f"Multiplier '{key}' must be > 0, got {value}"
            )
```

- [ ] **Step 4: Run validation tests**

Run: `pytest tests/test_tuning.py -v`
Expected: All PASS

- [ ] **Step 5: Write failing tests for each Python consumer**

Add to `tests/test_tuning.py`:
```python
from chronicler.tuning import get_multiplier, K_AGGRESSION_BIAS, K_TRADE_FRICTION, K_RESOURCE_ABUNDANCE, K_SECESSION_LIKELIHOOD, K_TECH_DIFFUSION_RATE

def _make_world_with_multiplier(key, value):
    """Helper: create minimal WorldState with one tuning override."""
    from chronicler.models import WorldState
    w = WorldState.__new__(WorldState)
    w.tuning_overrides = {key: value}
    return w

def test_aggression_bias_scales_war_weight():
    """K_AGGRESSION_BIAS multiplies WAR weight before the 2.5x cap."""
    from chronicler.action_engine import ActionEngine, ActionType
    world = _make_world_with_multiplier(K_AGGRESSION_BIAS, 2.0)
    # ... setup minimal world with civ + eligible WAR action ...
    engine = ActionEngine(world)
    weights_biased = engine.compute_weights(world.civilizations[0])
    world.tuning_overrides = {}
    weights_default = engine.compute_weights(world.civilizations[0])
    # WAR weight should be ~2x higher with bias (before cap)
    assert weights_biased[ActionType.WAR] > weights_default[ActionType.WAR] * 1.5

def test_trade_friction_scales_transport_cost():
    """friction_multiplier parameter scales compute_transport_cost output."""
    from chronicler.economy import compute_transport_cost
    cost_default = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    cost_high = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False, friction_multiplier=2.0)
    assert cost_high == pytest.approx(cost_default * 2.0)

def test_resource_abundance_scales_yields():
    """K_RESOURCE_ABUNDANCE multiplies compute_resource_yields output."""
    # Setup: region with known base yields, world with abundance=2.0
    # Verify yields are 2x higher than default
    pass  # Depends on region fixture; implement with real Region object

def test_secession_likelihood_scales_probability():
    """K_SECESSION_LIKELIHOOD multiplies secession probability."""
    # Setup: civ with stability=10 → base prob = (20-10)/100 = 0.10
    # At multiplier 2.0 → prob = 0.20, clamped to 1.0
    pass  # Depends on politics test fixtures

def test_tech_diffusion_rate_scales_cost():
    """K_TECH_DIFFUSION_RATE divides advancement cost."""
    # At rate 2.0, cost should halve; at 0.5, cost should double
    from chronicler.tech import check_tech_advancement
    # Setup: civ meeting requirements with treasury exactly at cost
    # With rate=2.0, effective_cost = cost/2, so treasury is sufficient
    # With rate=0.5, effective_cost = cost*2, so treasury is insufficient
    pass  # Depends on tech test fixtures; exact assertions need civ at threshold
```

- [ ] **Step 6: Wire K_AGGRESSION_BIAS**

In `src/chronicler/action_engine.py`, after the raider incentive block (line 796), before the streak-breaker (line 798), add:
```python
        # M47: Aggression bias multiplier
        from chronicler.tuning import get_multiplier, K_AGGRESSION_BIAS
        weights[ActionType.WAR] *= get_multiplier(self.world, K_AGGRESSION_BIAS)
```

- [ ] **Step 7: Wire K_TRADE_FRICTION**

In `src/chronicler/economy.py`, at the end of `compute_transport_cost()` (line 419), add a `friction_multiplier` parameter:
```python
def compute_transport_cost(
    terrain_a: str,
    terrain_b: str,
    *,
    is_river: bool,
    is_coastal: bool,
    is_winter: bool,
    friction_multiplier: float = 1.0,  # M47: from K_TRADE_FRICTION
) -> float:
    ...
    return TRANSPORT_COST_BASE * terrain_factor * infra * min(river, coastal) * seasonal * friction_multiplier
```

At the call site in `compute_economy()` (~line 812), pass the multiplier:
```python
from chronicler.tuning import get_multiplier, K_TRADE_FRICTION
friction = get_multiplier(world, K_TRADE_FRICTION)
# ... in the route_transport_costs loop:
route_transport_costs[route] = compute_transport_cost(
    origin_region.terrain, dest_region.terrain,
    is_river=is_river, is_coastal=is_coastal, is_winter=is_winter,
    friction_multiplier=friction,
)
```
This keeps `compute_transport_cost` world-agnostic — it takes a scalar, caller resolves from tuning. Existing test callers don't break (default 1.0).

- [ ] **Step 8: Wire K_RESOURCE_ABUNDANCE**

In `src/chronicler/ecology.py`, at line 118, change:
```python
        yields[slot] = base * season_mod * climate_mod * ecology_mod * reserve_ramp
```
to:
```python
        from chronicler.tuning import get_multiplier, K_RESOURCE_ABUNDANCE
        yields[slot] = base * season_mod * climate_mod * ecology_mod * reserve_ramp * get_multiplier(world, K_RESOURCE_ABUNDANCE)
```

- [ ] **Step 9: Wire K_SECESSION_LIKELIHOOD**

In `src/chronicler/politics.py`, after the secession probability computation (line 126), add:
```python
        from chronicler.tuning import get_multiplier, K_SECESSION_LIKELIHOOD
        prob *= get_multiplier(world, K_SECESSION_LIKELIHOOD)
        prob = min(prob, 1.0)
```

- [ ] **Step 10: Wire K_TECH_DIFFUSION_RATE**

In `src/chronicler/tech.py`, change both cost lines (99 and 106):
```python
    from chronicler.tuning import get_multiplier, K_TECH_DIFFUSION_RATE
    rate = max(get_multiplier(world, K_TECH_DIFFUSION_RATE), 0.1)
    if civ.active_focus == "scholarship":
        effective_cost = int(cost * 0.8 / rate)
    else:
        effective_cost = int(cost / rate)
```

- [ ] **Step 11: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass (multipliers default to 1.0, no behavioral change)

- [ ] **Step 12: Commit Python consumers**

```bash
git add src/chronicler/action_engine.py src/chronicler/economy.py src/chronicler/ecology.py src/chronicler/politics.py src/chronicler/tech.py src/chronicler/tuning.py tests/test_tuning.py
git commit -m "feat(m47a): wire 5 Python-side multiplier consumers

K_AGGRESSION_BIAS, K_TRADE_FRICTION, K_RESOURCE_ABUNDANCE,
K_SECESSION_LIKELIHOOD, K_TECH_DIFFUSION_RATE. All default to 1.0
(no behavioral change). Multiplier validation in load_tuning()
rejects values <= 0.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: M47a Step 1 — Severity Cap + Signature Change (11 call sites)

**Files:**
- Modify: `src/chronicler/emergence.py:87-89`
- Modify: `src/chronicler/simulation.py` (9 call sites)
- Modify: `src/chronicler/ecology.py:283`
- Modify: `src/chronicler/factions.py:413`
- Modify: `tests/test_emergence.py:292-309`
- Test: `tests/test_tuning.py` (add severity cap test)

- [ ] **Step 1: Write failing test for severity composition cap**

Add to `tests/test_tuning.py`:
```python
def test_severity_composition_cap():
    from chronicler.emergence import get_severity_multiplier
    from chronicler.models import Civilization, WorldState
    # Max stress civ (stress=20) → base = 1.0 + (20/20)*0.5 = 1.5
    # Dark-age preset severity = 1.8 → composed = 1.5 * 1.8 = 2.7
    # Should be capped at 2.0
    civ = Civilization.__new__(Civilization)
    civ.civ_stress = 20
    world = WorldState.__new__(WorldState)
    world.tuning_overrides = {"multiplier.severity": 1.8}
    result = get_severity_multiplier(civ, world)
    assert result == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tuning.py::test_severity_composition_cap -v`
Expected: FAIL (old signature takes only `civ`)

- [ ] **Step 3: Update get_severity_multiplier signature and implementation**

In `src/chronicler/emergence.py:87-89`, change:
```python
def get_severity_multiplier(civ: Civilization) -> float:
    """Return cascade severity multiplier based on civ stress. Range: 1.0-1.5."""
    return 1.0 + (civ.civ_stress / 20) * 0.5
```
to:
```python
def get_severity_multiplier(civ: Civilization, world: "WorldState") -> float:
    """Return cascade severity multiplier. Composed with tuning multiplier, capped at 2.0."""
    from chronicler.tuning import get_multiplier, K_SEVERITY_MULTIPLIER
    base = 1.0 + (civ.civ_stress / 20) * 0.5
    return min(base * get_multiplier(world, K_SEVERITY_MULTIPLIER), 2.0)
```

- [ ] **Step 4: Update 11 call sites to pass `world`**

Each call changes from `get_severity_multiplier(civ)` to `get_severity_multiplier(civ, world)`:

| File | Line | Context |
|---|---|---|
| `simulation.py` | 137 | Drought |
| `simulation.py` | 156 | Plague |
| `simulation.py` | 179 | Earthquake |
| `simulation.py` | 640 | Leader death |
| `simulation.py` | 665 | Rebellion |
| `simulation.py` | 681 | Religious movement |
| `simulation.py` | 706 | Migration |
| `simulation.py` | 713 | Border incident |
| `simulation.py` | 800 | Ongoing conditions |
| `ecology.py` | 283 | Famine yield check |
| `factions.py` | 413 | Faction power struggle |

- [ ] **Step 5: Update 4 existing tests in test_emergence.py**

Lines 292-309 — update test calls to pass a mock world with empty tuning_overrides.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_emergence.py tests/test_tuning.py -v`
Expected: All PASS

- [ ] **Step 7: Commit severity cap**

```bash
git add src/chronicler/emergence.py src/chronicler/simulation.py src/chronicler/ecology.py src/chronicler/factions.py tests/test_emergence.py tests/test_tuning.py
git commit -m "feat(m47a): severity composition cap at 2.0x with world parameter

get_severity_multiplier(civ, world) now composes base severity with
K_SEVERITY_MULTIPLIER tuning override, capped at 2.0. Prevents
dark-age (1.8) + max stress (1.5) = 2.7x death spirals. All 11
call sites updated.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: M47a Step 1 — Wire Rust-Side Multiplier Consumers (FFI)

**Files:**
- Modify: `chronicler-agents/src/signals.rs`
- Modify: `chronicler-agents/src/culture_tick.rs:64`
- Modify: `chronicler-agents/src/conversion_tick.rs:64`
- Modify: `src/chronicler/agent_bridge.py` (build_civ_batch)
- Test: Rust tests in `chronicler-agents/tests/`

- [ ] **Step 1: Add 2 new fields to CivSignals struct**

In `chronicler-agents/src/signals.rs`, add to `CivSignals`:
```rust
pub cultural_drift_multiplier: f32,
pub religion_intensity_multiplier: f32,
```

In the `CivSignals` parsing/extraction code, default both to `1.0` for missing columns:
```rust
cultural_drift_multiplier: columns.get("cultural_drift_multiplier")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>())
    .map(|a| a.value(row))
    .unwrap_or(1.0),
```

- [ ] **Step 2: Wire cultural_drift_multiplier in culture_tick.rs**

At line 64 of `culture_tick.rs`, change:
```rust
drift_agent(slot, pool, &dist, agent::CULTURAL_DRIFT_RATE, &mut rng);
```
to:
```rust
let effective_rate = agent::CULTURAL_DRIFT_RATE * civ_signals.cultural_drift_multiplier;
drift_agent(slot, pool, &dist, effective_rate, &mut rng);
```
(Thread `civ_signals` into the culture tick function if not already available.)

- [ ] **Step 3: Wire religion_intensity_multiplier in conversion_tick.rs**

At line 64 of `conversion_tick.rs`, multiply both conversion rate paths:
```rust
let prob = if region.conquest_conversion_active {
    (agent::CONQUEST_CONVERSION_RATE * civ_signals.religion_intensity_multiplier).min(1.0)
} else {
    let base = region.conversion_rate * civ_signals.religion_intensity_multiplier;
    if pool.satisfactions[slot] < agent::SUSCEPTIBILITY_THRESHOLD {
        (base * agent::SUSCEPTIBILITY_MULTIPLIER).min(1.0)
    } else {
        base.min(1.0)
    }
};
```

- [ ] **Step 4: Add columns to build_civ_batch() in agent_bridge.py**

In `src/chronicler/agent_bridge.py`, in `build_civ_batch()`, add two new columns reading from world.tuning_overrides:
```python
from chronicler.tuning import get_multiplier, K_CULTURAL_DRIFT_SPEED, K_RELIGION_INTENSITY
# ... in column building:
"cultural_drift_multiplier": pa.array([get_multiplier(world, K_CULTURAL_DRIFT_SPEED)] * n_civs, type=pa.float32()),
"religion_intensity_multiplier": pa.array([get_multiplier(world, K_RELIGION_INTENSITY)] * n_civs, type=pa.float32()),
```

- [ ] **Step 5: Wire Python-side K_CULTURAL_DRIFT_SPEED consumer**

In `src/chronicler/culture.py`, in `apply_value_drift()` around line 69, multiply `net_drift`:
```python
from chronicler.tuning import get_multiplier, K_CULTURAL_DRIFT_SPEED
net_drift = int(net_drift * get_multiplier(world, K_CULTURAL_DRIFT_SPEED))
```

- [ ] **Step 6: Wire Python-side K_RELIGION_INTENSITY consumers**

In `src/chronicler/religion.py`:
```python
from chronicler.tuning import get_multiplier, K_RELIGION_INTENSITY

# Line 27 area — conversion rate:
effective_base_rate = BASE_CONVERSION_RATE * get_multiplier(world, K_RELIGION_INTENSITY)

# Line 50 area — schism threshold (with floor):
effective_threshold = max(SCHISM_MINORITY_THRESHOLD / get_multiplier(world, K_RELIGION_INTENSITY), 0.10)

# Line 514 area — persecution intensity:
intensity *= get_multiplier(world, K_RELIGION_INTENSITY)
```

- [ ] **Step 7: Update Rust test fixtures**

All Rust tests that construct `CivSignals` need the two new fields. Add `cultural_drift_multiplier: 1.0, religion_intensity_multiplier: 1.0` to every test fixture.

- [ ] **Step 8: Write Rust tests for multiplier effect**

```rust
#[test]
fn test_culture_drift_multiplier_doubles_rate() {
    // With multiplier=2.0, drift should happen ~2x as often
    // Compare drift counts over N iterations at 1.0 vs 2.0
}

#[test]
fn test_religion_multiplier_doubles_conversion() {
    // With multiplier=2.0, conversion probability doubles
}
```

- [ ] **Step 9: Run Rust tests**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
Expected: All PASS

- [ ] **Step 10: Run Python tests**

Run: `pytest tests/ -x -q`
Expected: All PASS

- [ ] **Step 11: Commit FFI consumers**

```bash
git add chronicler-agents/src/ src/chronicler/agent_bridge.py src/chronicler/culture.py src/chronicler/religion.py
git commit -m "feat(m47a): wire Rust-side multiplier consumers via FFI

K_CULTURAL_DRIFT_SPEED and K_RELIGION_INTENSITY threaded through
CivSignals as cultural_drift_multiplier and religion_intensity_multiplier.
Rust consumers in culture_tick.rs and conversion_tick.rs. Python-side
consumers in culture.py and religion.py. Missing columns default to 1.0.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: M47a Step 2 — Bit-Identical Verification + Preset Tests

**Files:**
- Test: `tests/test_tuning.py` (preset integration tests)

- [ ] **Step 1: Run `--agents=off` bit-identical check**

Run: `python -m chronicler --seed 42 --turns 50 --agents off --simulate-only > /tmp/m47a_a.json && python -m chronicler --seed 42 --turns 50 --agents off --simulate-only > /tmp/m47a_b.json && diff /tmp/m47a_a.json /tmp/m47a_b.json`
Expected: No diff. Verifies all 8 consumer wirings are no-ops at default multipliers (1.0).

**If this fails:** A consumer is not defaulting to 1.0. Check each wiring site.

- [ ] **Step 2: Write preset integration tests**

Add to `tests/test_tuning.py`:
```python
@pytest.mark.parametrize("preset,check_key,direction", [
    ("dark-age", "war_pct", "gt"),
    ("golden-age", "war_pct", "lt"),
    ("silk-road", "trade_pct", "gt"),
    ("ice-age", "food_sufficiency", "lt"),
])
def test_preset_directional_effect(preset, check_key, direction):
    """Presets shift action distributions in expected directions vs default baseline."""
    # Run 50 turns with seed 42, default vs preset
    # Compare action distributions
    # Assert directional shift
    pass  # Implementation depends on simulation runner API
```

- [ ] **Step 3: Commit verification**

```bash
git add tests/test_tuning.py
git commit -m "test(m47a): bit-identical verification and preset directional tests

Consumer wiring verified as no-op at default multipliers.
Preset tests verify directional effects on action distributions.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: M47a Step 3 — Severity Inconsistency Fix (25 sites)

**Files:**
- Modify: 10 files (see file map above)
- Test: `tests/test_severity.py` (new)

- [ ] **Step 1: Write failing test for representative missing site**

Create `tests/test_severity.py`:
```python
def test_embargo_damage_uses_severity():
    """EMBARGO stability drain should scale with get_severity_multiplier."""
    # Setup: civ with high stress (civ_stress=20) → base severity 1.5
    # EMBARGO damage of -5 should become -7 (int(5 * 1.5))
    # At default tuning, severity cap is 2.0 but base is 1.5
    pass  # Exact test depends on ActionEngine test harness
```

- [ ] **Step 2: Apply severity multiplier to all 25 missing sites**

Pattern for each site — wrap the drain value:
```python
# Before:
acc.add(civ_idx, civ, "stability", -10, "signal")
# After:
mult = get_severity_multiplier(civ, world)
acc.add(civ_idx, civ, "stability", -int(10 * mult), "signal")
```

For direct mutation paths (the `else` branches):
```python
# Before:
civ.stability = clamp(civ.stability - 10, 0, 100)
# After:
mult = get_severity_multiplier(civ, world)
civ.stability = clamp(civ.stability - int(10 * mult), 0, 100)
```

Apply to all 25 sites listed in the spec. Verify `world` is in scope at each site (it is — all phase functions receive `world`).

**Ecology exemption decision:** `ecology.py:307` (famine neighbor stability drain, -5) is a cross-civ political consequence triggered by ecology, not a direct ecology effect. The primary famine drain (`ecology.py:283`) already uses severity — it affects the famine-stricken civ directly. The neighbor drain is a refugee/spillover stability hit on an adjacent civ. Apply severity: this is a political consequence, not an ecology mutation. The ecology exemption covers soil/water/forest mutations, not stability drains caused by ecological events.

**Category routing note:** The plan's generic pattern shows `"signal"` category, but actual sites use mixed categories (`"signal"`, `"guard-shock"`, etc.). Preserve the existing routing category at each site — only wrap the drain magnitude with `int(X * get_severity_multiplier(civ, world))`. Do not change the category.

**Files and counts:**
- `action_engine.py`: 3 sites (lines 330, 494, 504)
- `climate.py`: 1 site (line 221)
- `culture.py`: 1 site (line 226)
- `ecology.py`: 1 site (line 307)
- `emergence.py`: 1 site (line 398)
- `leaders.py`: 2 sites (lines 221, 229)
- `politics.py`: 11 sites (lines 52, 257, 322, 613, 624, 688, 865, 903, 1220, +2)
- `simulation.py`: 4 sites (lines 299, 316, 741, 764)
- `succession.py`: 1 site (line 254)

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: All PASS. Note: this intentionally changes simulation behavior — severity now applies everywhere.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/climate.py src/chronicler/culture.py src/chronicler/ecology.py src/chronicler/emergence.py src/chronicler/leaders.py src/chronicler/politics.py src/chronicler/simulation.py src/chronicler/succession.py tests/test_severity.py
git commit -m "fix(m47a): apply severity multiplier to 25 missing negative stat mutations

Per CLAUDE.md rule: all negative stat changes go through
get_severity_multiplier() except treasury and ecology. Found 25 sites
across 9 source files that bypassed severity scaling. politics.py had
11 missing sites. Usurper coup (-30) was the highest-severity miss.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: M47a Step 4 — Batch Walrasian Tatonnement

**Files:**
- Modify: `src/chronicler/economy.py` (insert between lines 891-893)
- Test: `tests/test_economy.py`

- [ ] **Step 1: Write failing test for tatonnement convergence**

Add to `tests/test_economy.py`:
```python
def test_tatonnement_converges_in_3_passes():
    """Price discovery should converge within 3 iterations when supply/demand are balanced."""
    # Setup: 2 regions with complementary surpluses
    # After tatonnement, prices should be closer to equilibrium than single-pass
    pass  # Exact test depends on compute_economy internals

def test_tatonnement_price_clamp_prevents_oscillation():
    """Per-pass price adjustment clamped to [0.5, 2.0] prevents extreme swings."""
    # Setup: extreme excess demand (10x supply)
    # Even with large imbalance, price should at most double per pass
    pass
```

- [ ] **Step 2: Implement tatonnement loop**

In `src/chronicler/economy.py`, wrap the category-level price→trade→import cycle (lines 768-841) in an iteration loop. The per-good decomposition (line 877+) happens AFTER the loop, not inside it.

**Loop boundary:** Steps 2c (pre-trade prices, line 768) through 2e (trade flow allocation + import aggregation, line 841).

**Variables reinitialized per pass:**
- `pre_trade_prices` — recomputed from `region_production + region_imports` (not just production)
- `region_imports` — re-zeroed (accumulates fresh from new trade flow)
- `all_route_flows` — re-zeroed (fresh allocation per pass)

**Variables constant across passes (computed once, upstream):**
- `region_production`, `region_demand` — from production step, don't change
- `exportable_surplus` — derived from production, constant
- `route_transport_costs` — terrain-based, constant
- `origin_routes`, `merchant_count` — structural, constant

```python
TATONNEMENT_MAX_PASSES = 3
TATONNEMENT_DAMPING = 0.2  # [CALIBRATE] for M47c
TATONNEMENT_CONVERGENCE = 0.01
TATONNEMENT_PRICE_CLAMP = (0.5, 2.0)

for _pass in range(TATONNEMENT_MAX_PASSES):
    prev_prices = {rn: dict(p) for rn, p in pre_trade_prices.items()}

    # Step 2c: Recompute prices from (production + last-pass imports)
    for rname in region_production:
        supply = {cat: region_production[rname][cat] + region_imports.get(rname, _empty_category_dict())[cat]
                  for cat in CATEGORIES}
        new_prices = compute_prices(supply, region_demand[rname])
        for cat in CATEGORIES:
            old_p = prev_prices.get(rname, {}).get(cat, 1.0)
            ratio = new_prices[cat] / max(old_p, 0.001)
            clamped = max(TATONNEMENT_PRICE_CLAMP[0], min(ratio, TATONNEMENT_PRICE_CLAMP[1]))
            new_prices[cat] = old_p * (1.0 + TATONNEMENT_DAMPING * (clamped - 1.0))
        pre_trade_prices[rname] = new_prices

    # Re-zero accumulators
    region_imports = {rn: _empty_category_dict() for rn in region_production}
    all_route_flows = {}

    # Step 2e: Re-run trade allocation with updated margins
    for origin_name, routes in origin_routes.items():
        dest_prices = {dest: pre_trade_prices.get(dest, _empty_category_dict())
                       for _, dest in routes}
        flow = allocate_trade_flow(
            routes, pre_trade_prices.get(origin_name, _empty_category_dict()),
            dest_prices, exportable_surplus.get(origin_name, _empty_category_dict()),
            merchant_count_by_region.get(origin_name, 0),
            transport_costs=route_transport_costs,
        )
        all_route_flows[origin_name] = flow
        for route, cat_amounts in flow.items():
            _, dest = route
            for cat, amount in cat_amounts.items():
                region_imports[dest][cat] = region_imports[dest].get(cat, 0.0) + amount

    # Convergence check
    max_delta = 0.0
    for rname in region_production:
        for cat in CATEGORIES:
            delta = abs(pre_trade_prices[rname].get(cat, 0) - prev_prices.get(rname, {}).get(cat, 0))
            max_delta = max(max_delta, delta)
    if max_delta < TATONNEMENT_CONVERGENCE:
        break

# After loop: proceed to per-good decomposition (line 877+), post-trade prices (line 893+)
```

Note: The `allocate_trade_flow` call parameters must match the existing call site at ~line 827. The above shows the essential structure — exact variable names may differ slightly. Verify against the actual code at implementation time.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_economy.py -v`
Expected: All PASS (including existing M42/M43 tests)

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m47a): batch Walrasian tatonnement for price discovery

Iterate price→trade→import cycle up to 3 passes with early exit on
convergence. Damping=0.2, per-pass price clamp [0.5, 2.0] prevents
oscillation. Improves price equilibrium quality before M47c calibration.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: M47a Step 5 — Pydantic Cleanup

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Remove misleading ge=/le= kwargs from Field definitions**

In `src/chronicler/models.py`, search for `ge=` and `le=` kwargs on Field() calls. Remove them and add a comment at the top of the model:
```python
# Note: validate_assignment=False for performance. Field constraints
# (ranges, bounds) are enforced via manual clamp() calls, not Pydantic
# validation. Do not add ge=/le= kwargs — they are silently ignored.
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -x -q`
Expected: All PASS (no behavioral change)

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "chore(m47a): remove misleading Pydantic Field constraints

validate_assignment=False means ge=/le= kwargs are never enforced.
Removed to prevent confusion. Clamping is manual throughout.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: M47b-prep — Gini CivSnapshot + CivThematicContext Deletion

**Files:**
- Modify: `src/chronicler/models.py` (add gini field, delete CivThematicContext)
- Modify: `src/chronicler/main.py:278` (populate gini)

- [ ] **Step 1: Add gini field to CivSnapshot**

In `src/chronicler/models.py`, add to `CivSnapshot`:
```python
gini: float = 0.0  # Wealth Gini coefficient (M41), populated from AgentBridge._gini_by_civ
```

- [ ] **Step 2: Populate gini in snapshot assembly**

In `src/chronicler/main.py:278`, in the CivSnapshot constructor (inside the `for civ in world.civilizations` comprehension which uses `enumerate`), add:
```python
# _gini_by_civ is dict[int, float] keyed by civ index, not name
gini=getattr(agent_bridge, '_gini_by_civ', {}).get(civ_idx, 0.0) if agent_bridge else 0.0,
```
where `civ_idx` comes from the existing `enumerate()` loop variable. If the snapshot comprehension doesn't use `enumerate`, convert it or use `civ_index(world, civ.name)` to get the integer key.

- [ ] **Step 3: Delete CivThematicContext and its references**

In `src/chronicler/models.py`:
1. Delete the `CivThematicContext` class definition (~line 660)
2. Remove the `civ_context: dict[str, CivThematicContext]` field from `NarrationContext` (~line 709). Replace with nothing — the field was never populated (dead infrastructure per progress doc).
3. In `src/chronicler/narrative.py:25`, remove the `CivThematicContext` import.
4. Grep for any remaining references and remove them.

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py src/chronicler/main.py
git commit -m "feat(m47b): add gini to CivSnapshot, delete dead CivThematicContext

Gini coefficient now persisted in turn snapshots for analytics
extraction. CivThematicContext was never constructed — dead code removed.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: M47b-prep — Region Map Cache

**Files:**
- Modify: `src/chronicler/models.py` (add region_map to WorldState)
- Modify: 6+ files that rebuild region_map each call

- [ ] **Step 1: Add region_map property to WorldState**

In `src/chronicler/models.py`, add to `WorldState` using Pydantic `PrivateAttr` (prevents leaking into `model_dump()` and bundle serialization):
```python
from pydantic import PrivateAttr

class WorldState(BaseModel):
    # ... existing fields ...
    _region_map: dict[str, "Region"] | None = PrivateAttr(default=None)

    @property
    def region_map(self) -> dict[str, "Region"]:
        if self._region_map is None:
            self._region_map = {r.name: r for r in self.regions}
        return self._region_map

    def invalidate_region_map(self) -> None:
        """Call after region list changes (conquest, expansion)."""
        self._region_map = None
```

- [ ] **Step 2: Replace inline region_map rebuilds**

Search for `{r.name: r for r in world.regions}` and replace with `world.region_map`. Add `world.invalidate_region_map()` calls after region mutations (conquest, expansion, secession).

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -x -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py src/chronicler/simulation.py src/chronicler/economy.py src/chronicler/politics.py
git commit -m "perf(m47b): cache region_map on WorldState

Replaces 6+ per-turn dict rebuilds with a cached property.
Invalidated on region mutations (conquest, expansion, secession).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: M47b-prep — 9 Analytics Extractors

**Files:**
- Modify: `src/chronicler/analytics.py`
- Test: `tests/test_analytics.py`

- [ ] **Step 1: Implement extractors following existing pattern**

Each extractor follows `extract_<name>(bundles, checkpoints=None) -> dict`. Use `_snapshot_at_turn()`, `_compute_percentiles()`, and `_firing_rate()` utilities.

```python
def extract_gini_trajectory(bundles, checkpoints=None):
    """Gini coefficient per civ at checkpoints."""
    checkpoints = _clamp_checkpoints(checkpoints or DEFAULT_CHECKPOINTS, _min_total_turns(bundles))
    result = {}
    for turn in checkpoints:
        values = []
        for b in bundles:
            snap = _snapshot_at_turn(b, turn)
            if snap:
                for name, cs in snap["civ_stats"].items():
                    if cs.get("alive", True) and len(cs.get("regions", [])) > 0:
                        values.append(cs.get("gini", 0.0))
        result[str(turn)] = _compute_percentiles(values) if values else {}
    return {"gini_by_turn": result}

def extract_schism_count(bundles):
    """Count of schism events per run."""
    counts = []
    for b in bundles:
        n = sum(1 for e in b.get("events_timeline", []) if e.get("event_type") == "Schism")
        counts.append(n)
    return {"schism_count": _compute_percentiles(counts), "firing_rate": sum(1 for c in counts if c > 0) / max(len(counts), 1)}

def extract_dynasty_count(bundles):
    """Count of unique dynasties per run."""
    counts = []
    for b in bundles:
        dynasty_ids = set()
        for civ_data in b.get("world_state", {}).get("civilizations", []):
            for gp in civ_data.get("great_persons", []):
                did = gp.get("dynasty_id")
                if did and did != 0:
                    dynasty_ids.add(did)
        counts.append(len(dynasty_ids))
    return {"dynasty_count": _compute_percentiles(counts), "firing_rate": sum(1 for c in counts if c > 0) / max(len(counts), 1)}

def extract_arc_distribution(bundles):
    """Arc type distribution across all great persons."""
    type_counts = {}
    total = 0
    for b in bundles:
        for civ_data in b.get("world_state", {}).get("civilizations", []):
            for gp in civ_data.get("great_persons", []):
                at = gp.get("arc_type")
                if at:
                    type_counts[at] = type_counts.get(at, 0) + 1
                    total += 1
    return {"arc_types": type_counts, "total": total, "distinct_count": len(type_counts)}

def extract_food_sufficiency(bundles, checkpoints=None):
    """Food sufficiency mean/min across civs at checkpoints."""
    # Reads from economy_result if available in bundle, or derives from snapshots
    # Implementation depends on how EconomyResult data is bundled
    pass  # Adapt to bundle structure during implementation

def extract_trade_volume(bundles, checkpoints=None):
    """Trade volume per turn (total goods traded)."""
    pass  # Adapt to EconomyResult bundling

def extract_stockpile_levels(bundles):
    """Stockpile levels at final turn per region."""
    pass  # Read from world_state regions at end of run

def extract_conversion_rates(bundles):
    """Conversion event counts per faith."""
    # NOTE: Verify actual event_type strings — may be "Persecution", "Mass Migration",
    # "Schism", "Reformation" rather than "conversion". Check religion.py event emission.
    pass  # Adapt to actual event_type strings

def extract_trade_flow_by_distance(bundles):
    """Trade flow volume by category and hop distance."""
    pass  # Requires EconomyResult per-route data in bundle
```

- [ ] **Step 2: Write tests for each extractor**

Add to `tests/test_analytics.py`:
```python
def test_extract_schism_count_basic():
    bundles = [{"events_timeline": [{"event_type": "Schism"}, {"event_type": "war"}]}]
    result = extract_schism_count(bundles)
    assert result["schism_count"]["median"] == 1.0
    assert result["firing_rate"] == 1.0

def test_extract_arc_distribution_counts_types():
    bundles = [{"world_state": {"civilizations": [
        {"great_persons": [{"arc_type": "Rise-and-Fall"}, {"arc_type": "Exile-and-Return"}]}
    ]}}]
    result = extract_arc_distribution(bundles)
    assert result["distinct_count"] == 2
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_analytics.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m47b): add 9 analytics extractors for health check

Gini trajectory, schism count, dynasty count, arc distribution,
food sufficiency, trade volume, stockpile levels, conversion rates,
trade flow by distance. Follows existing extractor pattern.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: M47b-run — Dispatch 200-Seed Health Check

- [ ] **Step 1: Run criterion 0 (determinism check)**

```bash
python -m chronicler --seed 42 --turns 500 --agents off --simulate-only > /tmp/c0_a.json
python -m chronicler --seed 42 --turns 500 --agents off --simulate-only > /tmp/c0_b.json
diff /tmp/c0_a.json /tmp/c0_b.json
```
Expected: No diff. This is the post-M47a authoritative baseline.

- [ ] **Step 2: Dispatch 200-seed health check as background agent**

```bash
python -m chronicler --seed-range 1-200 --turns 500 --civs 4 --regions 8 --agents hybrid --simulate-only --batch 200
```

- [ ] **Step 3: Run extractors on batch output and generate health check report**

Apply all extractors to the 200 bundles. Compare against criteria table in spec. Generate report matching `m19b-post-m24-tuning-report.md` format.

---

## Completion Checklist

After all tasks:
- [ ] All tests pass: `pytest tests/ -x -q` + `cargo nextest run`
- [ ] `--agents=off` bit-identical verified
- [ ] Spec updated with investigation findings (1a/1c/1e not bugs)
- [ ] Progress doc updated
- [ ] Health check report generated
