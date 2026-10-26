"""Bulk trade (2026-10): merchant loads by mode of travel, filled against the
tick's committed deliveries. See ``docs/integration/bulk-trade-crafts.md``.
Native tests run the real extension."""
from __future__ import annotations

import pytest

from chronicler.agent_bridge import configure_merchant_cargo
from chronicler.economy import MERCHANT_CARGO
from chronicler.tuning import (
    K_CARGO_FILL, K_LAND_CARGO_CAP, K_RIVER_CARGO_CAP, K_SEA_CARGO_CAP, KNOWN_OVERRIDES,
)

LEGACY = {K_LAND_CARGO_CAP: 1.0, K_RIVER_CARGO_CAP: 1.0, K_SEA_CARGO_CAP: 1.0, K_CARGO_FILL: 0.0}


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


class _Recorder:
    def __init__(self):
        self.calls = []

    def set_merchant_cargo_config(self, *args):
        self.calls.append(args)


class _World:
    def __init__(self, overrides):
        self.tuning_overrides = overrides


def test_cargo_keys_are_known_tuning_keys():
    for key in LEGACY:
        assert key in KNOWN_OVERRIDES


def test_cargo_config_is_sent_only_when_a_key_overrides_it():
    sim = _Recorder()
    configure_merchant_cargo(sim, _World({}))
    configure_merchant_cargo(sim, _World({"economy.per_capita_food": 0.5}))
    assert sim.calls == []
    configure_merchant_cargo(sim, _World({K_SEA_CARGO_CAP: 12.0}))
    (args,) = sim.calls
    assert args[2] == 12.0
    # Every other value is the default.
    assert args[:2] == MERCHANT_CARGO[:2]
    assert args[3] is True
    configure_merchant_cargo(sim, _World(LEGACY))
    assert sim.calls[-1][:4] == (1.0, 1.0, 1.0, False)


@pytest.mark.native
def test_native_cargo_config_rejects_invalid_values():
    _require_native()
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(num_regions=2, seed=1)
    sim.set_merchant_cargo_config(1.0, 1.0, 1.0, False)
    sim.set_merchant_cargo_config(*MERCHANT_CARGO[:3], True)
    for bad in ((0.0, 1.0, 1.0), (1.0, -1.0, 1.0), (1.0, 1.0, float("nan"))):
        with pytest.raises(ValueError):
            sim.set_merchant_cargo_config(*bad, True)


def _arrival_loads(tmp_path, monkeypatch, tuning: dict | None, seed: int = 44, turns: int = 60):
    """Every merchant arrival's load in a hybrid run."""
    import chronicler.agent_bridge as ab
    from chronicler.main import _build_parser, execute_run
    loads = []
    real = ab.AgentBridge._process_tick_results

    def spy(self, agent_events, world, *a, **k):
        batch = self._sim.get_pending_arrivals()
        loads.extend(batch.column("qty").to_pylist())
        return real(self, agent_events, world, *a, **k)

    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only", "--output", str(tmp_path / "run" / "chronicle.md")])
    args.tuning_overrides = dict(tuning or {})
    with monkeypatch.context() as m:
        m.setattr(ab.AgentBridge, "_process_tick_results", spy)
        execute_run(args)
    return loads


@pytest.mark.native
def test_native_bulk_loads_exceed_one_load_and_legacy_keys_carry_one(tmp_path, monkeypatch):
    _require_native()
    bulk = _arrival_loads(tmp_path / "bulk", monkeypatch, None)
    assert bulk, "merchants delivered"
    assert max(bulk) > 1.0 + 1e-6, "a bulk trip carries more than one load"
    assert max(bulk) <= max(MERCHANT_CARGO[:3]) + 1e-5
    legacy = _arrival_loads(tmp_path / "legacy", monkeypatch, LEGACY)
    assert legacy and max(legacy) <= 1.0 + 1e-6
