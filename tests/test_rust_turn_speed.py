"""Native turn-speed switches (docs/performance/turn-speed-2026-10b.md)."""
from __future__ import annotations

import pytest


def _native():
    native = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(native, "AgentSimulator", None), type):
        pytest.skip("chronicler_agents is not a compiled extension")
    if not hasattr(native.AgentSimulator, "set_spatial_sort_profiling"):
        pytest.skip("installed chronicler_agents predates the spatial sort switch")
    return native


@pytest.mark.native
def test_spatial_sort_profiling_is_off_by_default_and_switchable():
    native = _native()
    sim = native.AgentSimulator(num_regions=3, seed=1)
    assert sim.spatial_sort_profiling is False
    assert sim.get_spatial_diagnostics()["sort_time_us"] == [0.0]
    sim.set_spatial_sort_profiling(True)
    assert sim.spatial_sort_profiling is True
    sim.set_spatial_sort_profiling(False)
    assert sim.spatial_sort_profiling is False
