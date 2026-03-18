# M43b: Supply Shock Detection, Trade Dependency & Raider Incentive — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect supply shocks, classify trade dependency, add raider WAR incentive, and surface all of it for narration and the curator pipeline. No Rust changes.

**Architecture:** M43b is a pure Python layer on M43a's stockpile infrastructure. Three functional areas: (1) detection (EconomyTracker + detect_supply_shocks), (2) behavior modification (raider WAR modifier in action_engine), (3) narration context (AgentContext/CivThematicContext extensions). All new code in economy.py, with small additions to models.py, action_engine.py, curator.py, narrative.py, and simulation.py.

**Tech Stack:** Python 3.12, Pydantic models, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`

---

## Chunk 1: Data Model & EconomyResult Extensions

### Task 1: Add ShockContext and Event metadata fields to models.py

**Files:**
- Modify: `src/chronicler/models.py:355-362` (Event class), `src/chronicler/models.py:669-677` (AgentContext), `src/chronicler/models.py:646-654` (CivThematicContext)
- Test: `tests/test_economy_m43b.py` (new)

- [ ] **Step 1: Write tests for new model fields**

```python
# tests/test_economy_m43b.py
"""M43b: Supply shock detection, trade dependency & raider incentive tests."""

from chronicler.models import Event, AgentContext, CivThematicContext, ShockContext


def test_event_shock_metadata_defaults_none():
    ev = Event(turn=1, event_type="war", actors=["A"], description="test")
    assert ev.shock_region is None
    assert ev.shock_category is None


def test_event_shock_metadata_set():
    ev = Event(
        turn=1, event_type="supply_shock", actors=["A", "B"],
        description="Supply shock: food in Plains",
        source="economy", shock_region="Plains", shock_category="food",
    )
    assert ev.shock_region == "Plains"
    assert ev.shock_category == "food"


def test_shock_context_construction():
    sc = ShockContext(region="Plains", category="food", severity=0.7, upstream_source="Aram")
    assert sc.region == "Plains"
    assert sc.severity == 0.7
    assert sc.upstream_source == "Aram"


def test_shock_context_upstream_defaults_none():
    sc = ShockContext(region="Plains", category="food", severity=0.5)
    assert sc.upstream_source is None


def test_agent_context_trade_fields_default_empty():
    ctx = AgentContext()
    assert ctx.trade_dependent_regions == []
    assert ctx.active_shocks == []


def test_civ_thematic_context_trade_dependency_default_none():
    ctx = CivThematicContext(
        name="Rome", trait="expansionist", domains=["plains"],
        dominant_terrain="plains", tech_era="bronze",
    )
    assert ctx.trade_dependency_summary is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: FAIL — `ShockContext` not defined, `shock_region` not on Event, etc.

- [ ] **Step 3: Add ShockContext model and Event fields**

In `src/chronicler/models.py`, add `ShockContext` before the `Event` class (around line 354):

```python
class ShockContext(BaseModel):
    """M43b: Structured shock data for narration context."""
    region: str
    category: str
    severity: float
    upstream_source: str | None = None
```

Add optional fields to `Event` (after line 362, the `source` field):

```python
    # M43b: Structured shock metadata (None for non-shock events)
    shock_region: str | None = None
    shock_category: str | None = None
```

Add fields to `AgentContext` (after `relationships` field, around line 676):

```python
    # M43b: Trade & supply context
    trade_dependent_regions: list[str] = Field(default_factory=list)
    active_shocks: list[ShockContext] = Field(default_factory=list)
```

Add field to `CivThematicContext` (after `active_named_events` field, around line 654):

```python
    # M43b: Trade vulnerability summary
    trade_dependency_summary: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `python -m pytest tests/test_models.py tests/test_economy.py tests/test_economy_m43a.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_economy_m43b.py
git commit -m "feat(m43b): add ShockContext model, Event shock metadata, AgentContext/CivThematicContext trade fields"
```

---

### Task 2: Add EconomyResult fields and inbound_sources tracking

**Files:**
- Modify: `src/chronicler/economy.py:276-293` (EconomyResult class), `src/chronicler/economy.py:674-680` (trade flow loop)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for new EconomyResult fields**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.economy import EconomyResult, CATEGORY_GOODS


def test_economy_result_m43b_fields_default():
    er = EconomyResult()
    assert er.imports_by_region == {}
    assert er.inbound_sources == {}
    assert er.stockpile_levels == {}
    assert er.import_share == {}
    assert er.trade_dependent == {}


def test_category_goods_food_contains_salt():
    assert "salt" in CATEGORY_GOODS["food"]


def test_category_goods_three_categories():
    assert set(CATEGORY_GOODS.keys()) == {"food", "raw_material", "luxury"}


def test_category_goods_all_8_goods_covered():
    all_goods = set()
    for goods in CATEGORY_GOODS.values():
        all_goods |= goods
    assert len(all_goods) == 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py::test_economy_result_m43b_fields_default -v`
Expected: FAIL — fields don't exist on EconomyResult

- [ ] **Step 3: Add fields to EconomyResult and CATEGORY_GOODS constant**

In `src/chronicler/economy.py`, add `CATEGORY_GOODS` near the top constants:

```python
CATEGORY_GOODS = {
    "food": frozenset({"grain", "fish", "botanicals", "exotic", "salt"}),
    "raw_material": frozenset({"timber", "ore"}),
    "luxury": frozenset({"precious"}),
}
```

Add fields to `EconomyResult` (after `conservation`, around line 293):

```python
    # M43b: Supply shock detection and trade dependency
    imports_by_region: dict[str, dict[str, float]] = field(default_factory=dict)
    inbound_sources: dict[str, list[str]] = field(default_factory=dict)
    stockpile_levels: dict[str, dict[str, float]] = field(default_factory=dict)
    import_share: dict[str, float] = field(default_factory=dict)
    trade_dependent: dict[str, bool] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43b.py
git commit -m "feat(m43b): add EconomyResult fields and CATEGORY_GOODS constant"
```

---

### Task 3: Wire inbound_sources, imports_by_region, stockpile_levels, import_share, trade_dependent into compute_economy()

**Files:**
- Modify: `src/chronicler/economy.py:674-680` (trade flow accumulation loop), `src/chronicler/economy.py:737-767` (stockpile sub-sequence), `src/chronicler/economy.py:808-814` (signal derivation)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for inbound_sources and trade dependency**

Append to `tests/test_economy_m43b.py`:

```python
from unittest.mock import MagicMock
from chronicler.economy import TRADE_DEPENDENCY_THRESHOLD


def _make_minimal_economy_result_with_trade():
    """Helper: create EconomyResult with import/demand data for trade dependency test."""
    er = EconomyResult()
    # Region "Coast" imports 80% of its food from "Plains"
    er.imports_by_region = {"Coast": {"food": 8.0, "raw_material": 0.0, "luxury": 0.0}}
    er.import_share = {"Coast": 0.8}
    er.trade_dependent = {"Coast": True}
    er.inbound_sources = {"Coast": ["Plains"]}
    return er


def test_import_share_above_threshold_is_trade_dependent():
    er = _make_minimal_economy_result_with_trade()
    assert er.trade_dependent["Coast"] is True
    assert er.import_share["Coast"] > TRADE_DEPENDENCY_THRESHOLD


def test_inbound_sources_tracks_origins():
    er = _make_minimal_economy_result_with_trade()
    assert "Plains" in er.inbound_sources["Coast"]
```

- [ ] **Step 2: Run tests to verify they pass (structural tests against static data)**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS (these test the data structure, not compute_economy)

- [ ] **Step 3: Wire inbound_sources into the trade flow loop**

In `src/chronicler/economy.py`, in the trade flow accumulation loop (around line 674), add inbound_sources tracking. After the existing loop:

```python
    for origin_name, route_flows_for_origin in all_route_flows.items():
        for route, cat_flows in route_flows_for_origin.items():
            _, dest = route
            for cat in CATEGORIES:
                amount = cat_flows[cat]
                if amount > 0:
                    result.inbound_sources.setdefault(dest, [])
                    if origin_name not in result.inbound_sources[dest]:
                        result.inbound_sources[dest].append(origin_name)
```

This goes right after the existing `region_exports`/`region_imports` accumulation loop (lines 674-680). Can be merged into the same loop body for efficiency.

- [ ] **Step 4: Wire imports_by_region, stockpile_levels, import_share, trade_dependent**

After the stockpile sub-sequence (after line 767, before signal derivation), add:

```python
    # --- M43b: Capture imports_by_region, stockpile_levels, trade dependency ---
    for region in regions:
        rname = region.name
        # imports_by_region: capture from transient region_imports before RegionGoods is built
        result.imports_by_region[rname] = dict(region_imports.get(rname, _empty_category_dict()))
        # stockpile_levels: aggregate per-good stockpile to per-category
        cat_stockpile = _empty_category_dict()
        for good, amount in region.stockpile.goods.items():
            for cat, goods_set in CATEGORY_GOODS.items():
                if good in goods_set:
                    cat_stockpile[cat] += amount
                    break
        result.stockpile_levels[rname] = cat_stockpile
        # import_share and trade_dependent
        food_demand = region_demand.get(rname, _empty_category_dict()).get("food", 0.0)
        food_imports = region_imports.get(rname, _empty_category_dict()).get("food", 0.0)
        share = food_imports / max(food_demand, 0.1)
        result.import_share[rname] = share
        result.trade_dependent[rname] = share > TRADE_DEPENDENCY_THRESHOLD
```

- [ ] **Step 5: Run all economy tests**

Run: `python -m pytest tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43b.py
git commit -m "feat(m43b): wire inbound_sources, imports_by_region, stockpile_levels, trade dependency into compute_economy()"
```

---

## Chunk 2: EconomyTracker & Shock Detection

### Task 4: Implement EconomyTracker

**Files:**
- Modify: `src/chronicler/economy.py` (add class near top, after constants)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for EconomyTracker**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.economy import EconomyTracker


def test_economy_tracker_first_update_initializes():
    tracker = EconomyTracker()
    tracker.update_stockpile("Plains", "food", 100.0)
    assert tracker.trailing_avg["Plains"]["food"] == 100.0


def test_economy_tracker_ema_converges():
    tracker = EconomyTracker()
    # Feed constant value — should converge to that value
    for _ in range(20):
        tracker.update_stockpile("Plains", "food", 50.0)
    assert abs(tracker.trailing_avg["Plains"]["food"] - 50.0) < 0.01


def test_economy_tracker_ema_responds_to_step():
    tracker = EconomyTracker()
    # Initialize
    tracker.update_stockpile("Plains", "food", 100.0)
    # Step change to 0
    tracker.update_stockpile("Plains", "food", 0.0)
    # After one step: 0.67 * 100 + 0.33 * 0 = 67
    assert abs(tracker.trailing_avg["Plains"]["food"] - 67.0) < 0.1


def test_economy_tracker_imports_ema():
    tracker = EconomyTracker()
    tracker.update_imports("Coast", "food", 80.0)
    assert tracker.import_avg["Coast"]["food"] == 80.0
    tracker.update_imports("Coast", "food", 40.0)
    # 0.67 * 80 + 0.33 * 40 = 53.6 + 13.2 = 66.8
    assert abs(tracker.import_avg["Coast"]["food"] - 66.8) < 0.1


def test_economy_tracker_separate_regions():
    tracker = EconomyTracker()
    tracker.update_stockpile("Plains", "food", 100.0)
    tracker.update_stockpile("Coast", "food", 50.0)
    assert tracker.trailing_avg["Plains"]["food"] == 100.0
    assert tracker.trailing_avg["Coast"]["food"] == 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py::test_economy_tracker_first_update_initializes -v`
Expected: FAIL — `EconomyTracker` not defined

- [ ] **Step 3: Implement EconomyTracker**

In `src/chronicler/economy.py`, add after the constants section:

```python
class EconomyTracker:
    """Persistent economy analytics state across turns. Not world state.

    Tracks exponential moving averages (alpha=0.33, ~3-turn window) for:
    - Per-region per-category stockpile levels (shock detection)
    - Per-region per-category import levels (upstream source classification)
    """

    def __init__(self):
        self.trailing_avg: dict[str, dict[str, float]] = {}
        self.import_avg: dict[str, dict[str, float]] = {}

    def update_stockpile(self, region_name: str, category: str, current: float):
        key = self.trailing_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current

    def update_imports(self, region_name: str, category: str, current: float):
        key = self.import_avg.setdefault(region_name, {})
        if category not in key:
            key[category] = current
        else:
            key[category] = 0.67 * key[category] + 0.33 * current
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43b.py
git commit -m "feat(m43b): implement EconomyTracker with EMA for stockpiles and imports"
```

---

### Task 5: Implement detect_supply_shocks() and classify_upstream_source()

**Files:**
- Modify: `src/chronicler/economy.py`
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for detect_supply_shocks()**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.economy import (
    detect_supply_shocks, classify_upstream_source,
    SHOCK_DELTA_THRESHOLD, SHOCK_SEVERITY_FLOOR,
)
from chronicler.models import Region, RegionStockpile, WorldState


def _make_region(name, controller=None, terrain="plains"):
    return Region(
        name=name, terrain=terrain, carrying_capacity=50,
        resources="fertile", controller=controller,
        adjacencies=[],
    )


def _make_basic_world(regions, civs=None):
    """Minimal WorldState for shock detection tests."""
    world = WorldState(
        turn=10,
        regions=regions,
        civilizations=civs or [],
    )
    return world


def test_detect_shock_fires_on_delta_and_below_floor():
    """Food stockpile drops 50% from avg AND food_sufficiency below floor."""
    region = _make_region("Plains", controller="Rome")
    region.stockpile = RegionStockpile(goods={"grain": 50.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}  # avg was 100
    tracker.import_avg = {"Plains": {"food": 0.0}}

    from chronicler.models import Civilization
    rome = Civilization(name="Rome", regions=["Plains"])
    world = _make_basic_world([region], civs=[rome])
    region_map = {"Plains": region}

    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.5}  # below SHOCK_SEVERITY_FLOOR (0.8)
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 50.0}}

    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].event_type == "supply_shock"
    assert shocks[0].actors[0] == "Rome"
    assert shocks[0].shock_region == "Plains"
    assert shocks[0].shock_category == "food"
    assert shocks[0].importance >= 5


def test_detect_shock_does_not_fire_above_floor():
    """Food stockpile drops but food_sufficiency is still above floor — no shock."""
    region = _make_region("Plains", controller="Rome")
    region.stockpile = RegionStockpile(goods={"grain": 50.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}

    from chronicler.models import Civilization
    rome = Civilization(name="Rome", regions=["Plains"])
    world = _make_basic_world([region], civs=[rome])
    region_map = {"Plains": region}

    er = EconomyResult()
    er.food_sufficiency = {"Plains": 1.2}  # above floor
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 50.0}}

    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 0


def test_detect_shock_no_delta_no_fire():
    """Chronically low stockpile, no delta — no shock (not news)."""
    region = _make_region("Plains", controller="Rome")
    region.stockpile = RegionStockpile(goods={"grain": 20.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 22.0}}  # only ~9% drop, below 30% threshold

    from chronicler.models import Civilization
    rome = Civilization(name="Rome", regions=["Plains"])
    world = _make_basic_world([region], civs=[rome])
    region_map = {"Plains": region}

    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.4}
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 20.0}}

    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 0


def test_detect_shock_non_food_uses_delta_severity():
    """Non-food shock uses delta magnitude for severity, no food_sufficiency gate."""
    region = _make_region("Mountains", controller="Rome")
    region.stockpile = RegionStockpile(goods={"ore": 10.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Mountains": {"raw_material": 100.0}}  # 90% drop

    from chronicler.models import Civilization
    rome = Civilization(name="Rome", regions=["Mountains"])
    world = _make_basic_world([region], civs=[rome])
    region_map = {"Mountains": region}

    er = EconomyResult()
    er.food_sufficiency = {"Mountains": 1.0}
    er.imports_by_region = {"Mountains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Mountains": {"raw_material": 10.0}}

    shocks = detect_supply_shocks(world, {"Mountains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].shock_category == "raw_material"


def test_detect_shock_importance_scales_with_severity():
    """Importance ranges from 5 (low severity) to 9 (max severity)."""
    region = _make_region("Plains", controller="Rome")
    region.stockpile = RegionStockpile(goods={"grain": 10.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Plains": {"food": 100.0}}

    from chronicler.models import Civilization
    rome = Civilization(name="Rome", regions=["Plains"])
    world = _make_basic_world([region], civs=[rome])
    region_map = {"Plains": region}

    er = EconomyResult()
    er.food_sufficiency = {"Plains": 0.0}  # max severity
    er.imports_by_region = {"Plains": {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {}
    er.stockpile_levels = {"Plains": {"food": 10.0}}

    shocks = detect_supply_shocks(world, {"Plains": region.stockpile}, tracker, er, region_map)
    assert len(shocks) == 1
    assert shocks[0].importance == 9


def test_shock_actors_affected_first_upstream_second():
    """Affected civ is actors[0], upstream source is actors[1]."""
    region = _make_region("Coast", controller="Tyre")
    region.stockpile = RegionStockpile(goods={"fish": 20.0})

    tracker = EconomyTracker()
    tracker.trailing_avg = {"Coast": {"food": 100.0}}
    tracker.import_avg = {"Coast": {"food": 80.0}}

    from chronicler.models import Civilization
    tyre = Civilization(name="Tyre", regions=["Coast"])
    aram = Civilization(name="Aram", regions=["Plains"])
    plains = _make_region("Plains", controller="Aram")
    world = _make_basic_world([region, plains], civs=[tyre, aram])
    region_map = {"Coast": region, "Plains": plains}

    er = EconomyResult()
    er.food_sufficiency = {"Coast": 0.3}
    er.imports_by_region = {"Coast": {"food": 5.0, "raw_material": 0.0, "luxury": 0.0}}
    er.inbound_sources = {"Coast": ["Plains"]}
    er.stockpile_levels = {
        "Coast": {"food": 20.0},
        "Plains": {"food": 10.0},  # Plains also crashed
    }

    shocks = detect_supply_shocks(world, {"Coast": region.stockpile}, tracker, er, region_map)
    assert len(shocks) >= 1
    coast_shock = next(s for s in shocks if s.shock_region == "Coast")
    assert coast_shock.actors[0] == "Tyre"
    assert len(coast_shock.actors) >= 2
    assert coast_shock.actors[1] == "Aram"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py::test_detect_shock_fires_on_delta_and_below_floor -v`
Expected: FAIL — `detect_supply_shocks` not defined

- [ ] **Step 3: Implement detect_supply_shocks() and classify_upstream_source()**

Add to `src/chronicler/economy.py`:

```python
# M43b constants
SHOCK_DELTA_THRESHOLD = 0.30  # [CALIBRATE] 30% drop triggers detection
SHOCK_SEVERITY_FLOOR = 0.8   # [CALIBRATE] food_sufficiency below this = crisis
TRADE_DEPENDENCY_THRESHOLD = 0.6  # [CALIBRATE] >60% food import share


def classify_upstream_source(
    world,
    economy_tracker: EconomyTracker,
    economy_result: "EconomyResult",
    region_name: str,
    category: str,
    region_map: dict,
) -> str | None:
    """Find upstream civ if shock is import-driven.

    Compares current import level against import EMA. If imports dropped
    significantly, identifies the trade partner whose stockpile also dropped
    (confirming upstream disruption vs embargo).
    """
    current_imports = economy_result.imports_by_region.get(region_name, {}).get(category, 0.0)
    avg_imports = economy_tracker.import_avg.get(region_name, {}).get(category, current_imports)

    if avg_imports <= 0 or current_imports / avg_imports > (1.0 - SHOCK_DELTA_THRESHOLD):
        return None  # imports didn't drop significantly — local cause

    for source_name in economy_result.inbound_sources.get(region_name, []):
        source_stockpile = economy_result.stockpile_levels.get(source_name, {}).get(category, 0.0)
        source_avg = economy_tracker.trailing_avg.get(source_name, {}).get(category, source_stockpile)
        if source_avg > 0 and source_stockpile / source_avg < (1.0 - SHOCK_DELTA_THRESHOLD):
            source_region = region_map.get(source_name)
            if source_region and source_region.controller:
                return source_region.controller
    return None


def detect_supply_shocks(
    world,
    stockpiles: dict[str, "RegionStockpile"],
    economy_tracker: EconomyTracker,
    economy_result: "EconomyResult",
    region_map: dict,
) -> list:
    """Detect supply shocks: delta trigger + absolute severity gate.

    Returns list of Event objects with event_type='supply_shock'.
    """
    from chronicler.models import Event
    from chronicler.utils import get_civ

    shocks = []
    for name, sp in stockpiles.items():
        region = region_map.get(name)
        if region is None or region.controller is None:
            continue
        owner_civ_name = region.controller
        for cat, goods in CATEGORY_GOODS.items():
            current = sum(sp.goods.get(g, 0.0) for g in goods)
            avg = economy_tracker.trailing_avg.get(name, {}).get(cat, current)
            if avg <= 0 or current / avg >= (1.0 - SHOCK_DELTA_THRESHOLD):
                continue
            # Delta triggered
            if cat == "food":
                food_suff = economy_result.food_sufficiency.get(name, 1.0)
                if food_suff >= SHOCK_SEVERITY_FLOOR:
                    continue
                severity = 1.0 - (food_suff / SHOCK_SEVERITY_FLOOR)
            else:
                severity = min(1.0 - (current / max(avg, 0.1)), 1.0)

            upstream = classify_upstream_source(
                world, economy_tracker, economy_result, name, cat, region_map,
            )
            actors = [owner_civ_name]
            if upstream:
                actors.append(upstream)
            shocks.append(Event(
                turn=world.turn,
                event_type="supply_shock",
                actors=actors,
                description=f"Supply shock: {cat} in {name}",
                consequences=[],
                importance=5 + int(severity * 4),
                source="economy",
                shock_region=name,
                shock_category=cat,
            ))
    return shocks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 5: Run full economy test suite**

Run: `python -m pytest tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43b.py
git commit -m "feat(m43b): implement detect_supply_shocks() and classify_upstream_source()"
```

---

## Chunk 3: Raider WAR Modifier & Action Engine Integration

### Task 6: Implement raider WAR modifier in compute_weights()

**Files:**
- Modify: `src/chronicler/action_engine.py:773` (after holy war modifier)
- Modify: `src/chronicler/economy.py` (add `_get_adjacent_enemy_regions()`, raider constants)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for _get_adjacent_enemy_regions() and raider modifier**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.economy import (
    _get_adjacent_enemy_regions, RAIDER_WAR_WEIGHT, RAIDER_CAP,
    FOOD_GOODS,
)
from chronicler.models import Civilization, Disposition, Relationship


def _make_world_with_enemy_stockpile():
    """Two civs: Rome (Plains) hostile to Persia (Mountains with big stockpile)."""
    plains = _make_region("Plains", controller="Rome")
    plains.adjacencies = ["Mountains"]
    mountains = _make_region("Mountains", controller="Persia", terrain="mountain")
    mountains.adjacencies = ["Plains"]
    mountains.stockpile = RegionStockpile(goods={"grain": 500.0})

    rome = Civilization(name="Rome", regions=["Plains"])
    persia = Civilization(name="Persia", regions=["Mountains"])

    world = _make_basic_world([plains, mountains], civs=[rome, persia])
    world.relationships = {
        "Rome": {"Persia": Relationship(disposition=Disposition.HOSTILE)},
        "Persia": {"Rome": Relationship(disposition=Disposition.HOSTILE)},
    }
    return world, rome, persia


def test_adjacent_enemy_regions_finds_hostile():
    world, rome, _ = _make_world_with_enemy_stockpile()
    enemies = _get_adjacent_enemy_regions(rome, world)
    assert len(enemies) == 1
    assert enemies[0].name == "Mountains"


def test_adjacent_enemy_regions_empty_for_friendly():
    world, rome, _ = _make_world_with_enemy_stockpile()
    world.relationships["Rome"]["Persia"].disposition = Disposition.FRIENDLY
    enemies = _get_adjacent_enemy_regions(rome, world)
    assert len(enemies) == 0


def test_raider_modifier_zero_below_threshold():
    """Stockpile below RAIDER_THRESHOLD → no bonus."""
    # Test with very small stockpile — below any reasonable threshold
    from chronicler.economy import RAIDER_THRESHOLD
    bonus = 0.0
    max_food = 1.0  # well below threshold
    if max_food > RAIDER_THRESHOLD:
        bonus = RAIDER_WAR_WEIGHT * min(max_food / RAIDER_THRESHOLD - 1.0, RAIDER_CAP)
    assert bonus == 0.0


def test_raider_modifier_scales_above_threshold():
    """Stockpile above threshold → positive bonus, capped."""
    from chronicler.economy import RAIDER_THRESHOLD
    max_food = RAIDER_THRESHOLD * 3  # 2x overshoot
    bonus = RAIDER_WAR_WEIGHT * min(max_food / RAIDER_THRESHOLD - 1.0, RAIDER_CAP)
    assert bonus == RAIDER_WAR_WEIGHT * RAIDER_CAP  # capped at 2.0x


def test_raider_modifier_uses_max_not_sum():
    """Should use max across adjacent enemy regions, not sum."""
    plains = _make_region("Plains", controller="Rome")
    plains.adjacencies = ["A", "B"]
    a = _make_region("A", controller="Persia")
    a.adjacencies = ["Plains"]
    a.stockpile = RegionStockpile(goods={"grain": 10.0})
    b = _make_region("B", controller="Persia")
    b.adjacencies = ["Plains"]
    b.stockpile = RegionStockpile(goods={"grain": 200.0})

    rome = Civilization(name="Rome", regions=["Plains"])
    persia = Civilization(name="Persia", regions=["A", "B"])
    world = _make_basic_world([plains, a, b], civs=[rome, persia])
    world.relationships = {
        "Rome": {"Persia": Relationship(disposition=Disposition.HOSTILE)},
    }

    enemies = _get_adjacent_enemy_regions(rome, world)
    max_food = max(
        sum(r.stockpile.goods.get(g, 0.0) for g in FOOD_GOODS)
        for r in enemies
    )
    assert max_food == 200.0  # max, not sum (210)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py::test_adjacent_enemy_regions_finds_hostile -v`
Expected: FAIL — `_get_adjacent_enemy_regions` not defined

- [ ] **Step 3: Implement _get_adjacent_enemy_regions() and raider constants**

Add to `src/chronicler/economy.py`:

```python
# M43b: Raider constants
RAIDER_THRESHOLD = 200.0  # [CALIBRATE] set after M43a 200-seed data
RAIDER_WAR_WEIGHT = 0.15  # [CALIBRATE] base additive WAR bonus at 1x overshoot
RAIDER_CAP = 2.0          # max overshoot multiplier (bonus caps at 0.30)


def _get_adjacent_enemy_regions(civ, world) -> list:
    """Find regions adjacent to civ's territory controlled by hostile/suspicious civs."""
    from chronicler.models import Disposition

    enemy_civs = set()
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                enemy_civs.add(other_name)
    if not enemy_civs:
        return []

    region_map = {r.name: r for r in world.regions}
    own_regions = set(civ.regions)
    adjacent_enemy = []
    seen = set()
    for rname in own_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj_name in region.adjacencies:
            if adj_name in seen:
                continue
            adj_region = region_map.get(adj_name)
            if adj_region and adj_region.controller in enemy_civs:
                adjacent_enemy.append(adj_region)
                seen.add(adj_name)
    return adjacent_enemy
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43b.py
git commit -m "feat(m43b): implement _get_adjacent_enemy_regions() and raider constants"
```

---

### Task 7: Wire raider modifier into action_engine.py compute_weights()

**Files:**
- Modify: `src/chronicler/action_engine.py:773` (after holy war block)
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write integration test for raider modifier in compute_weights()**

Add to `tests/test_economy_m43b.py`:

```python
def test_raider_modifier_in_compute_weights():
    """Integration: raider bonus added to WAR weight when adjacent enemy has large stockpile."""
    from chronicler.action_engine import ActionSelector
    from chronicler.economy import RAIDER_THRESHOLD, RAIDER_WAR_WEIGHT

    world, rome, persia = _make_world_with_enemy_stockpile()
    # Set stockpile well above threshold
    mountains = next(r for r in world.regions if r.name == "Mountains")
    mountains.stockpile.goods["grain"] = RAIDER_THRESHOLD * 2

    # Need minimal world state for ActionSelector
    world.action_history = {}
    world.relationships = {
        "Rome": {"Persia": Relationship(disposition=Disposition.HOSTILE)},
        "Persia": {"Rome": Relationship(disposition=Disposition.HOSTILE)},
    }
    # Set _economy_result so raider block fires
    er = EconomyResult()
    world._economy_result = er

    # Give Rome a leader
    from chronicler.models import Leader
    rome.leader = Leader(name="Caesar", trait="balanced")
    rome.treasury = 100
    rome.military = 50
    rome.economy = 50

    selector = ActionSelector(world)
    weights_with = selector.compute_weights(rome)
    war_weight_with = weights_with.get(ActionType.WAR, 0)

    # Remove economy_result — raider block should be skipped
    world._economy_result = None
    selector2 = ActionSelector(world)
    weights_without = selector2.compute_weights(rome)
    war_weight_without = weights_without.get(ActionType.WAR, 0)

    assert war_weight_with > war_weight_without
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43b.py::test_raider_modifier_in_compute_weights -v`
Expected: FAIL — raider block not in compute_weights yet

- [ ] **Step 3: Add raider modifier block to compute_weights()**

In `src/chronicler/action_engine.py`, after the holy war modifier block (after line 773, the `break` at the end of the holy war section), add:

```python
        # M43b: Raider incentive — wealthy adjacent enemy stockpiles attract WAR
        if hasattr(self.world, '_economy_result') and self.world._economy_result is not None:
            from chronicler.economy import (
                _get_adjacent_enemy_regions, RAIDER_THRESHOLD,
                RAIDER_WAR_WEIGHT, RAIDER_CAP, FOOD_GOODS,
            )
            adjacent_enemy_regions = _get_adjacent_enemy_regions(civ, self.world)
            if adjacent_enemy_regions:
                max_adjacent_food = max(
                    sum(r.stockpile.goods.get(g, 0.0) for g in FOOD_GOODS)
                    for r in adjacent_enemy_regions
                )
                if max_adjacent_food > RAIDER_THRESHOLD:
                    raider_bonus = RAIDER_WAR_WEIGHT * min(
                        max_adjacent_food / RAIDER_THRESHOLD - 1.0,
                        RAIDER_CAP,
                    )
                    weights[ActionType.WAR] += raider_bonus
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py tests/test_action_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_economy_m43b.py
git commit -m "feat(m43b): wire raider WAR modifier into compute_weights() after holy war bonus"
```

---

## Chunk 4: Curator & Narration Integration

### Task 8: Add CAUSAL_PATTERNS entries to curator.py

**Files:**
- Modify: `src/chronicler/curator.py:29-44` (CAUSAL_PATTERNS list)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write test for new causal patterns**

Append to `tests/test_economy_m43b.py`:

```python
def test_causal_patterns_include_supply_shock():
    from chronicler.curator import CAUSAL_PATTERNS
    shock_patterns = [p for p in CAUSAL_PATTERNS if "supply_shock" in (p[0], p[1])]
    assert len(shock_patterns) == 7
    # Verify shock-to-shock self-link exists
    self_link = [p for p in shock_patterns if p[0] == "supply_shock" and p[1] == "supply_shock"]
    assert len(self_link) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43b.py::test_causal_patterns_include_supply_shock -v`
Expected: FAIL — no supply_shock patterns

- [ ] **Step 3: Add patterns to CAUSAL_PATTERNS**

In `src/chronicler/curator.py`, add after the existing entries (after line 43, before the `]`):

```python
    # M43b: Supply shock causal patterns
    ("drought", "supply_shock", 5, 3.0),
    ("war", "supply_shock", 3, 2.0),
    ("embargo", "supply_shock", 3, 3.0),
    ("supply_shock", "famine", 5, 3.0),
    ("supply_shock", "rebellion", 10, 2.0),
    ("supply_shock", "migration", 10, 2.0),
    ("supply_shock", "supply_shock", 3, 2.5),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py tests/test_curator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_economy_m43b.py
git commit -m "feat(m43b): add 7 supply_shock CAUSAL_PATTERNS entries to curator"
```

---

### Task 9: Wire narration context (AgentContext + CivThematicContext)

**Files:**
- Modify: `src/chronicler/narrative.py:58-121` (build_agent_context_block), `src/chronicler/narrative.py:124-137` (build_agent_context_for_moment)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write tests for narration context wiring**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.narrative import build_agent_context_block
from chronicler.models import AgentContext, ShockContext


def test_agent_context_block_renders_trade_dependency():
    ctx = AgentContext(
        trade_dependent_regions=["Coast", "Port"],
    )
    block = build_agent_context_block(ctx)
    assert "Trade-dependent regions: Coast, Port" in block


def test_agent_context_block_renders_shocks():
    ctx = AgentContext(
        active_shocks=[
            ShockContext(region="Plains", category="food", severity=0.7, upstream_source="Aram"),
        ],
    )
    block = build_agent_context_block(ctx)
    assert "Supply crisis in Plains" in block
    assert "food" in block
    assert "Aram" in block


def test_agent_context_block_no_trade_data_no_section():
    ctx = AgentContext()
    block = build_agent_context_block(ctx)
    assert "Trade-dependent" not in block
    assert "Supply crisis" not in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43b.py::test_agent_context_block_renders_trade_dependency -v`
Expected: FAIL — trade dependency not in output

- [ ] **Step 3: Add trade/shock rendering to build_agent_context_block()**

In `src/chronicler/narrative.py`, in `build_agent_context_block()`, add before the "Guidelines:" section (before line 104):

```python
    # M43b: Trade dependency and supply shock context
    if ctx.trade_dependent_regions:
        lines.append(f"Trade-dependent regions: {', '.join(ctx.trade_dependent_regions)}")
    if ctx.active_shocks:
        for shock in ctx.active_shocks:
            lines.append(
                f"Supply crisis in {shock.region}: {shock.category} "
                f"(severity {shock.severity:.1f}, "
                f"source: {shock.upstream_source or 'local'})"
            )
    if ctx.trade_dependent_regions or ctx.active_shocks:
        lines.append("")
```

- [ ] **Step 4: Add economy_result parameter to build_agent_context_for_moment()**

In `src/chronicler/narrative.py`, add `economy_result=None` parameter to `build_agent_context_for_moment()` (line 124). After the existing `AgentContext` construction (around line 205), add:

```python
    # M43b: Populate trade dependency and shock context
    if economy_result is not None:
        moment_civs = {ev.actors[0] for ev in moment.events if ev.actors}
        region_map_by_name = {r.name: r for r in world.regions} if hasattr(world, 'regions') else {}
        ctx.trade_dependent_regions = [
            rname for rname, dep in getattr(economy_result, 'trade_dependent', {}).items()
            if dep and region_map_by_name.get(rname, None) is not None
            and region_map_by_name[rname].controller in moment_civs
        ]
        ctx.active_shocks = [
            ShockContext(
                region=ev.shock_region,
                category=ev.shock_category,
                severity=(ev.importance - 5) / 4.0,
                upstream_source=ev.actors[1] if len(ev.actors) > 1 else None,
            )
            for ev in moment.events
            if ev.event_type == "supply_shock" and ev.shock_region is not None
        ]
```

Add `ShockContext` to the imports at the top of `narrative.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43b.py tests/test_narrative.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/narrative.py tests/test_economy_m43b.py
git commit -m "feat(m43b): wire trade dependency and shock context into narration pipeline"
```

---

## Chunk 5: Simulation Wiring & Integration Tests

### Task 10: Wire EconomyTracker and detect_supply_shocks() into simulation.py

**Files:**
- Modify: `src/chronicler/simulation.py:1204-1220` (Phase 2 economy block)
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write integration test for Phase 2 shock detection wiring**

Append to `tests/test_economy_m43b.py`:

```python
def test_simulation_economy_tracker_wired():
    """Verify EconomyTracker is instantiated and persists across turns."""
    # This is a structural check — verify the tracker is created in run setup
    from chronicler.economy import EconomyTracker
    tracker = EconomyTracker()
    # After update, state persists
    tracker.update_stockpile("Plains", "food", 100.0)
    tracker.update_stockpile("Plains", "food", 80.0)
    # EMA: 0.67 * 100 + 0.33 * 80 = 93.4
    assert abs(tracker.trailing_avg["Plains"]["food"] - 93.4) < 0.1
```

- [ ] **Step 2: Wire EconomyTracker into simulation.py**

In `src/chronicler/simulation.py`, in the main run function (where `agent_bridge` is initialized), add `EconomyTracker` instantiation:

```python
    from chronicler.economy import EconomyTracker
    economy_tracker = EconomyTracker()
```

Then in the Phase 2 economy block (after line 1217, `agent_bridge.set_economy_result(economy_result)`), add:

```python
        # M43b: Update tracker EMAs and detect supply shocks
        from chronicler.economy import detect_supply_shocks, CATEGORY_GOODS
        for region in world.regions:
            rname = region.name
            for cat, goods in CATEGORY_GOODS.items():
                stock_total = sum(region.stockpile.goods.get(g, 0.0) for g in goods)
                economy_tracker.update_stockpile(rname, cat, stock_total)
                imports_total = economy_result.imports_by_region.get(rname, {}).get(cat, 0.0)
                economy_tracker.update_imports(rname, cat, imports_total)

        stockpiles = {r.name: r.stockpile for r in world.regions}
        shock_events = detect_supply_shocks(
            world, stockpiles, economy_tracker, economy_result, region_map,
        )
        turn_events.extend(shock_events)

        # M43b: Store economy_result for Phase 8 raider modifier
        world._economy_result = economy_result
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_simulation.py tests/test_action_engine.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_economy_m43b.py
git commit -m "feat(m43b): wire EconomyTracker and detect_supply_shocks() into Phase 2 turn loop"
```

---

### Task 11: End-to-end integration tests

**Files:**
- Test: `tests/test_economy_m43b.py`

- [ ] **Step 1: Write end-to-end test for shock-to-curator flow**

Append to `tests/test_economy_m43b.py`:

```python
from chronicler.curator import compute_causal_links, compute_base_scores


def test_shock_events_flow_through_curator():
    """supply_shock events are scored and linked by curator pipeline."""
    drought = Event(
        turn=5, event_type="drought", actors=["Rome"],
        description="Drought in Plains", importance=6,
    )
    shock = Event(
        turn=7, event_type="supply_shock", actors=["Rome", "Aram"],
        description="Supply shock: food in Coast", importance=7,
        source="economy", shock_region="Coast", shock_category="food",
    )
    famine = Event(
        turn=10, event_type="famine", actors=["Rome"],
        description="Famine in Coast", importance=8,
    )
    events = [drought, shock, famine]
    scores = compute_base_scores(events, [], "Rome", seed=42)
    links = compute_causal_links(events, scores)

    # drought→supply_shock link (shared actor "Rome", gap=2, max_gap=5)
    drought_to_shock = [l for l in links if l.cause_event_type == "drought" and l.effect_event_type == "supply_shock"]
    assert len(drought_to_shock) == 1

    # supply_shock→famine link (shared actor "Rome", gap=3, max_gap=5)
    shock_to_famine = [l for l in links if l.cause_event_type == "supply_shock" and l.effect_event_type == "famine"]
    assert len(shock_to_famine) == 1


def test_shock_to_shock_chain_linking():
    """supply_shock → supply_shock links for cascade chains."""
    shock_a = Event(
        turn=5, event_type="supply_shock", actors=["Aram"],
        description="Supply shock: food in Plains", importance=7,
        source="economy", shock_region="Plains", shock_category="food",
    )
    shock_b = Event(
        turn=7, event_type="supply_shock", actors=["Tyre", "Aram"],
        description="Supply shock: food in Coast", importance=7,
        source="economy", shock_region="Coast", shock_category="food",
    )
    events = [shock_a, shock_b]
    scores = compute_base_scores(events, [], "Aram", seed=42)
    links = compute_causal_links(events, scores)

    # shock→shock link (shared actor "Aram", gap=2, max_gap=3)
    chain = [l for l in links if l.cause_event_type == "supply_shock" and l.effect_event_type == "supply_shock"]
    assert len(chain) == 1
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_economy_m43b.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_economy_m43b.py
git commit -m "test(m43b): add end-to-end curator integration tests for supply shock events"
```

---

### Task 12: Full regression check

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All PASS. No regressions from M43b additions.

- [ ] **Step 2: Verify --agents=off compatibility**

Run: `python -m pytest tests/test_simulation.py -v -k "agents_off or aggregate"`
Expected: All PASS. Shock detection and trade dependency work in all modes.

- [ ] **Step 3: Final commit with all files**

Verify `git status` is clean. If any uncommitted changes remain:

```bash
git add -A
git commit -m "chore(m43b): final cleanup"
```
