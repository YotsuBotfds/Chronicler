"""Tests for DemandSignalManager — 3-turn linear decay."""
import pytest
from chronicler.models import DemandSignal


class TestDemandSignalManager:

    def test_single_signal_three_turn_decay(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(civ_id=0, occupation=1, magnitude=0.17, turns_remaining=3))

        # Turn 0: full magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17)

        # Turn 1: 2/3 magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17 * 2 / 3, abs=0.001)

        # Turn 2: 1/3 magnitude
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.17 * 1 / 3, abs=0.001)

        # Turn 3: expired
        shifts = mgr.tick()
        assert 0 not in shifts  # civ not present → no active signals

    def test_multiple_signals_same_civ_aggregate(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))  # soldier
        mgr.add(DemandSignal(0, 2, 0.05, 3))  # merchant
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.10)   # soldier
        assert shifts[0][2] == pytest.approx(0.05)   # merchant

    def test_signals_different_civs(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))
        mgr.add(DemandSignal(1, 2, 0.20, 3))
        shifts = mgr.tick()
        assert shifts[0][1] == pytest.approx(0.10)
        assert shifts[1][2] == pytest.approx(0.20)

    def test_reset_clears_all(self):
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.10, 3))
        mgr.reset()
        shifts = mgr.tick()
        assert len(shifts) == 0

    def test_total_impulse(self):
        """Total delivered impulse should be 2 * magnitude."""
        from chronicler.demand_signals import DemandSignalManager
        mgr = DemandSignalManager()
        mgr.add(DemandSignal(0, 1, 0.30, 3))
        total = 0.0
        for _ in range(5):  # Extra ticks to ensure expiry
            shifts = mgr.tick()
            total += shifts.get(0, [0.0] * 5)[1]
        assert total == pytest.approx(0.60, abs=0.001)  # 2 * 0.30
