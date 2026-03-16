"""Tests for StatAccumulator — M27 core routing logic."""
import pytest
from unittest.mock import MagicMock
from chronicler.models import StatChange, CivShock, DemandSignal


def _make_civ(civ_id, stability=50, economy=50, military=50, culture=50, treasury=100, asabiya=0.5, prestige=10):
    """Create a mock Civilization with stat fields."""
    civ = MagicMock()
    civ.id = civ_id
    civ.stability = stability
    civ.economy = economy
    civ.military = military
    civ.culture = culture
    civ.treasury = treasury
    civ.asabiya = asabiya
    civ.prestige = prestige
    return civ


def _make_world(civs):
    world = MagicMock()
    world.civilizations = civs
    return world


class TestStatAccumulatorApply:
    """Aggregate mode: apply() must produce bit-identical results to direct mutation."""

    def test_apply_single_change(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -10, "signal")
        acc.apply(world)
        assert civ.stability == 40

    def test_apply_preserves_insertion_order(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -50, "signal")
        acc.add(0, civ, "stability", -50, "signal")
        acc.apply(world)
        # First: 80-50=30. Second: 30-50=-20 → clamped to floor (5 for stability)
        assert civ.stability == 5  # STAT_FLOOR["stability"]

    def test_apply_clamps_to_100(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, economy=95)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "economy", 20, "guard-shock")
        acc.apply(world)
        assert civ.economy == 100

    def test_apply_treasury_no_upper_clamp(self):
        """Treasury uses max(0, ...) not clamp(..., 100)."""
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, treasury=200)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "treasury", 50, "keep")
        acc.apply(world)
        assert civ.treasury == 250  # No upper bound

    def test_apply_treasury_floors_at_zero(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, treasury=10)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "treasury", -30, "keep")
        acc.apply(world)
        assert civ.treasury == 0  # Floors at 0, not negative


class TestStatAccumulatorRouting:
    """Category routing: each method processes only its categories."""

    def test_apply_keep_only_processes_keep(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50, treasury=100)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -10, "signal")
        acc.add(0, civ, "treasury", -5, "keep")
        acc.add(0, civ, "military", 10, "guard-action")
        acc.apply_keep(world)
        assert civ.treasury == 95   # keep applied
        assert civ.stability == 50  # signal NOT applied
        assert civ.military == 50   # guard-action NOT applied

    def test_to_shock_signals_processes_signal_and_guard_shock(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80, culture=50)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -20, "signal")
        acc.add(0, civ, "culture", 10, "guard-shock")
        acc.add(0, civ, "treasury", -5, "keep")
        acc.add(0, civ, "military", 10, "guard-action")
        shocks = acc.to_shock_signals()
        assert len(shocks) == 1  # one civ
        assert shocks[0].stability_shock == pytest.approx(-0.25)  # -20/80
        assert shocks[0].culture_shock == pytest.approx(0.2)      # 10/50
        assert shocks[0].economy_shock == 0.0
        assert shocks[0].military_shock == 0.0

    def test_to_demand_signals_processes_guard_action_only(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, military=50)
        acc = StatAccumulator()
        acc.add(0, civ, "military", -10, "guard-action")
        acc.add(0, civ, "stability", -5, "signal")
        acc.add(0, civ, "treasury", -3, "keep")
        signals = acc.to_demand_signals({0: 60})
        assert len(signals) == 1
        assert signals[0].occupation == 1  # soldier
        assert signals[0].magnitude == pytest.approx(-10 / 60 * 1.0)
        assert signals[0].turns_remaining == 3

    def test_guard_category_skipped_everywhere(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=50)
        world = _make_world([civ])
        acc = StatAccumulator()
        acc.add(0, civ, "stability", 10, "guard")
        acc.apply_keep(world)
        assert civ.stability == 50  # not applied
        shocks = acc.to_shock_signals()
        assert len(shocks) == 0
        signals = acc.to_demand_signals({0: 60})
        assert len(signals) == 0


class TestShockNormalization:
    """Shock normalization: delta / max(stat_at_time, 1), clamped ±1.0."""

    def test_normal_negative(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=80)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-0.25)

    def test_fragile_civ_feels_more(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=20)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)

    def test_zero_stat_guarded(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=0)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)

    def test_positive_shock(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, culture=50)
        acc = StatAccumulator()
        acc.add(0, civ, "culture", 10, "guard-shock")
        shocks = acc.to_shock_signals()
        assert shocks[0].culture_shock == pytest.approx(0.2)

    def test_multiple_shocks_same_stat_accumulate(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=100)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -10, "signal")
        acc.add(0, civ, "stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-0.3)

    def test_shock_clamped_at_negative_one(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, stability=10)
        acc = StatAccumulator()
        acc.add(0, civ, "stability", -20, "signal")
        shocks = acc.to_shock_signals()
        assert shocks[0].stability_shock == pytest.approx(-1.0)

    def test_shock_clamped_at_positive_one(self):
        from chronicler.accumulator import StatAccumulator
        civ = _make_civ(0, culture=5)
        acc = StatAccumulator()
        acc.add(0, civ, "culture", 20, "guard-shock")
        shocks = acc.to_shock_signals()
        assert shocks[0].culture_shock == pytest.approx(1.0)


class TestBitIdenticalRegression:
    """Accumulator in aggregate mode produces identical results to direct mutations."""

    def test_100_turn_aggregate_deterministic(self):
        """Run 100 turns twice with same seed. All civ fields must match exactly.
        This verifies the accumulator doesn't introduce non-determinism."""
        import copy
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.action_engine import ActionEngine

        world_a = generate_world(seed=42, num_civs=4, num_regions=8)
        world_b = copy.deepcopy(world_a)

        def noop_narrator(world, events):
            return ""

        for turn in range(100):
            world_a.turn = turn
            world_b.turn = turn

            engine_a = ActionEngine(world_a)
            selector_a = lambda civ, w, eng=engine_a: eng.select_action(civ, seed=w.seed + w.turn)

            engine_b = ActionEngine(world_b)
            selector_b = lambda civ, w, eng=engine_b: eng.select_action(civ, seed=w.seed + w.turn)

            run_turn(world_a, selector_a, noop_narrator, seed=turn)
            run_turn(world_b, selector_b, noop_narrator, seed=turn)

        # Compare every stat on every civ
        for i, (ca, cb) in enumerate(zip(world_a.civilizations, world_b.civilizations)):
            for stat in ("stability", "economy", "military", "culture",
                         "treasury", "population"):
                val_a = getattr(ca, stat)
                val_b = getattr(cb, stat)
                assert val_a == val_b, (
                    f"Turn 100, Civ {i} ({ca.name}) {stat}: "
                    f"run_a={val_a} run_b={val_b}"
                )
