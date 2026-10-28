"""The merchant tax with the real native extension: the economy tick takes
the tax from the merchants it assesses, exactly once a tick
(chronicler-agents/src/tax.rs), the treasury is paid what they paid, the
earlier rule is restored by its tuning key, and hybrid runs balance the
books under CHRONICLER_CHECK_RESOURCES=1 (with domestic credit too) and
resume exactly from a checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pytest

from chronicler.main import execute_run

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    sim = getattr(ca, "AgentSimulator", None)
    if not isinstance(sim, type) or not hasattr(sim, "merchant_wealth_by_civ"):
        pytest.skip("requires a chronicler_agents build with the merchant tax")
    return ca


def _bridge_world(seed: int = 42, turns: int = 8, overrides: dict | None = None):
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world

    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    if overrides:
        world.tuning_overrides = dict(overrides)
    bridge = AgentBridge(world, mode="hybrid")
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world, bridge


def _tick(world, bridge, **kwargs):
    from chronicler.economy import (
        build_economy_region_input_batch, build_economy_trade_route_batch, reconstruct_economy_result,
    )
    out = bridge._sim.tick_economy(build_economy_region_input_batch(world),
                                   build_economy_trade_route_batch(world, active_trade_routes=[]),
                                   0, False, 1.0, **kwargs)
    return reconstruct_economy_result(*out, world, tax_debited=kwargs.get("debit_merchant_tax", True))


def _merchant_wealth_from_snapshot(sim) -> np.ndarray:
    from chronicler.columnar import pylist
    snap = sim.get_snapshot()
    occ = np.asarray(pylist(snap.column("occupation")))
    civ = np.asarray(pylist(snap.column("civ_affinity")))
    wealth = np.asarray(pylist(snap.column("wealth")), dtype=np.float64)
    return np.array([wealth[(occ == 2) & (civ == c)].sum() for c in range(256)])


def test_the_economy_tick_takes_the_tax_from_the_merchants_once():
    _native()
    world, bridge = _bridge_world()
    sim = bridge._sim
    before = np.asarray(sim.merchant_wealth_by_civ())
    assert np.allclose(before, _merchant_wealth_from_snapshot(sim))
    result = _tick(world, bridge)
    after = np.asarray(sim.merchant_wealth_by_civ())
    paid = result.tax_collected
    assert paid and set(paid) == set(result.treasury_tax)
    for civ, amount in paid.items():
        assert before[civ] - after[civ] == pytest.approx(amount, abs=1e-9 * max(1.0, before[civ]))
        assert amount == pytest.approx(0.05 * before[civ], rel=1e-5, abs=1e-9)
        assert amount == pytest.approx(result.treasury_tax[civ], rel=1e-5, abs=1e-6)
    untaxed = [c for c in range(256) if c not in paid]
    assert np.array_equal(before[untaxed], after[untaxed])
    assert sum(paid.values()) > 0
    # The snapshot is exported again: it shows what the merchants hold now.
    assert np.allclose(_merchant_wealth_from_snapshot(sim), after)
    # Nothing is carried to the next call: a second tick taxes what is left, once.
    again = _tick(world, bridge)
    later = np.asarray(sim.merchant_wealth_by_civ())
    for civ, amount in again.tax_collected.items():
        assert amount == pytest.approx(0.05 * after[civ], rel=1e-5, abs=1e-9)
        assert after[civ] - later[civ] == pytest.approx(amount, abs=1e-9 * max(1.0, after[civ]))


def test_the_earlier_rule_takes_nothing():
    _native()
    world, bridge = _bridge_world()
    sim = bridge._sim
    before = list(sim.merchant_wealth_by_civ())
    result = _tick(world, bridge, debit_merchant_tax=False)
    assert result.tax_collected is None
    assert list(sim.merchant_wealth_by_civ()) == before
    assert sum(result.treasury_tax.values()) > 0


def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


@pytest.mark.parametrize("domestic_credit", [False, True])
def test_a_checked_hybrid_run_balances_and_equals_the_unchecked_run(tmp_path, monkeypatch, domestic_credit):
    """CHRONICLER_CHECK_RESOURCES=1 checks the tax every tick (and with
    domestic credit its books too, which still balance with the tax paid);
    the checks only read: the final state equals an unchecked run's."""
    _native()
    states = {}
    for name, checked in (("checked", True), ("plain", False)):
        if checked:
            monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
        else:
            monkeypatch.delenv("CHRONICLER_CHECK_RESOURCES", raising=False)
        folder = tmp_path / name
        execute_run(_args(folder, 50, domestic_credit=domestic_credit))
        states[name] = (folder / "state.json").read_bytes()
    assert states["checked"] == states["plain"]
    if domestic_credit:
        books = json.loads(states["checked"])["domestic_credit"]
        assert books["totals"]["lent_merchants"] > 0


def test_the_tuning_key_restores_the_earlier_rule_in_a_run(tmp_path, monkeypatch):
    """Key 0: nobody pays (the ledger, on, checks the pool never moves) and
    the treasury is paid the assessment; the run differs from the default."""
    _native()
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    restored = tmp_path / "restored"
    execute_run(_args(restored, 30, tuning_overrides={"economy.merchant_tax_debited": 0}))
    corrected = tmp_path / "corrected"
    execute_run(_args(corrected, 30))
    assert (restored / "state.json").read_bytes() != (corrected / "state.json").read_bytes()


def test_tax_is_paid_into_the_treasury_every_turn_of_a_run(monkeypatch):
    """Multi-turn: each turn the merchants pay once and the treasury is
    credited what they paid (whole units, the rest carried)."""
    _native()
    import chronicler.simulation as simulation

    seen = []
    orig = simulation._apply_treasury_tax_from_economy

    def spy(world, acc, economy_result, *args, **kwargs):
        start = len(acc._changes)
        carry0 = dict(getattr(world, "_treasury_tax_carry", {}))
        orig(world, acc, economy_result, *args, **kwargs)
        if economy_result is None:
            return
        credited = {}
        for c in acc._changes[start:]:
            credited[c.civ_id] = credited.get(c.civ_id, 0) + c.delta
        seen.append((world.turn, dict(economy_result.tax_collected), credited, carry0,
                     dict(world._treasury_tax_carry)))

    monkeypatch.setattr(simulation, "_apply_treasury_tax_from_economy", spy)
    _bridge_world(turns=12)
    turns = [t for t, *_ in seen]
    assert len(turns) >= 10 and turns == sorted(set(turns)), "once a turn"
    paid_total = credited_total = 0.0
    for _turn, paid, credited, carry0, carry1 in seen:
        for civ, amount in paid.items():
            got = credited.get(civ, 0) + carry1.get(civ, 0.0) - carry0.get(civ, 0.0)
            assert got == pytest.approx(amount, abs=1e-9)
        paid_total += sum(paid.values())
        credited_total += sum(credited.values())
    assert paid_total > 0
    assert credited_total + sum(seen[-1][4].values()) == pytest.approx(paid_total, abs=1e-9)


def test_a_checkpoint_resume_continues_exactly(tmp_path):
    _native()
    from chronicler import run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle

    def content(path: Path) -> bytes:
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            return json.dumps(data, sort_keys=True).encode()
        return path.read_bytes()

    def outputs(folder: Path) -> dict[str, bytes]:
        return {p.relative_to(folder).as_posix(): content(p) for p in sorted(folder.rglob("*"))
                if p.is_file() and p.suffix != ".ckpt"}

    straight = tmp_path / "straight"
    execute_run(_args(straight, 30, checkpoint_every=12, checkpoint=str(straight / "c{turn}.ckpt")))
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 30), checkpoint_resume=rc.read_checkpoint(straight / "c12.ckpt"))
    expected, got = outputs(straight), outputs(resumed)
    assert got.keys() == expected.keys()
    assert [name for name in got if got[name] != expected[name]] == []
