"""Domestic credit with the real native extension: reading and moving
merchant agents' wealth (chronicler-agents/src/credit.rs), the merchants'
grievance column, and hybrid runs with the switch on (balanced books with
CHRONICLER_CHECK_RESOURCES=1, determinism, a checkpoint resume)."""
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
    if not isinstance(sim, type) or not hasattr(sim, "apply_merchant_transfers"):
        pytest.skip("requires a chronicler_agents build with domestic credit")
    return ca


def _bridge_world(seed: int = 42, turns: int = 6):
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world

    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world, bridge


def _merchants_by_home(sim, n: int) -> tuple[np.ndarray, np.ndarray]:
    from chronicler.columnar import pylist
    snap = sim.get_snapshot()
    occ = np.asarray(pylist(snap.column("occupation")))
    reg = np.asarray(pylist(snap.column("region")))
    wealth = np.asarray(pylist(snap.column("wealth")), dtype=np.float64)
    names = snap.schema.names
    if "trip_origin_region" in names and "trip_phase" in names:
        phase = np.asarray(pylist(snap.column("trip_phase")))
        origin = np.asarray(pylist(snap.column("trip_origin_region")))
        reg = np.where(phase != 0, origin, reg)
    totals, counts = np.zeros(n), np.zeros(n, dtype=int)
    for r in range(n):
        m = (occ == 2) & (reg == r)
        totals[r] = wealth[m].sum()
        counts[r] = int(m.sum())
    return totals, counts


def test_merchant_wealth_is_read_and_moved_exactly_once():
    _native()
    world, bridge = _bridge_world()
    sim = bridge._sim
    n = len(world.regions)
    wealth, counts = sim.merchant_wealth_by_region()
    assert len(wealth) == n and len(counts) == n
    if "trip_origin_region" in sim.get_snapshot().schema.names:
        expect, expect_counts = _merchants_by_home(sim, n)
        assert np.allclose(wealth, expect) and list(counts) == list(expect_counts)
    r = int(np.argmax(wealth))
    assert wealth[r] > 0
    take = 0.4 * wealth[r]
    applied = sim.apply_merchant_transfers([r], [-take])
    after, _ = sim.merchant_wealth_by_region()
    assert applied[0] == pytest.approx(-take, rel=1e-5)
    assert after[r] - wealth[r] == pytest.approx(applied[0], abs=1e-6)
    assert [a for i, a in enumerate(after) if i != r] == [w for i, w in enumerate(wealth) if i != r]
    # Nothing is held over: an empty call changes nothing, and a credit
    # comes back exactly.
    assert sim.apply_merchant_transfers([], []) == []
    assert sim.merchant_wealth_by_region()[0] == after
    back = sim.apply_merchant_transfers([r], [take])
    assert back[0] == pytest.approx(take, rel=1e-5)
    with pytest.raises(ValueError, match="region ids"):
        sim.apply_merchant_transfers([0, 1], [1.0])
    with pytest.raises(ValueError, match="not finite"):
        sim.apply_merchant_transfers([0], [float("nan")])
    # Regions without merchants (or beyond the world) take nothing.
    empty = [i for i, c in enumerate(counts) if c == 0]
    if empty:
        assert sim.apply_merchant_transfers([empty[0]], [5.0]) == [0.0]
    assert sim.apply_merchant_transfers([n + 3], [5.0]) == [0.0]


def test_the_grievance_column_costs_merchants_satisfaction():
    _native()
    import pyarrow as pa
    from chronicler.agent_bridge import build_region_batch
    from chronicler.columnar import pylist

    def merchant_satisfaction(grievance: float | None) -> float:
        world, bridge = _bridge_world(seed=7, turns=4)
        batch = build_region_batch(world, bridge._economy_result)
        if grievance is not None:
            batch = batch.append_column("creditor_grievance",
                                        pa.array([grievance] * batch.num_rows, type=pa.float32()))
        bridge._sim.set_region_state(batch)
        from chronicler.agent_bridge import build_signals
        bridge._sim.tick(world.turn, build_signals(world, economy_result=bridge._economy_result))
        snap = bridge._sim.get_snapshot()
        occ = np.asarray(pylist(snap.column("occupation")))
        sat = np.asarray(pylist(snap.column("satisfaction")), dtype=np.float64)
        return float(sat[occ == 2].mean())

    calm = merchant_satisfaction(None)
    aggrieved = merchant_satisfaction(1.0)
    assert aggrieved < calm
    world, bridge = _bridge_world(seed=7, turns=1)
    batch = build_region_batch(world, bridge._economy_result)
    bad = batch.append_column("creditor_grievance", pa.array([1.5] * batch.num_rows, type=pa.float32()))
    with pytest.raises(ValueError, match="creditor_grievance"):
        bridge._sim.set_region_state(bad)


def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid", tuning_overrides={}, domestic_credit=True,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def test_a_hybrid_run_lends_balances_its_books_and_is_deterministic(tmp_path, monkeypatch):
    _native()
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    runs = []
    for name in ("a", "b"):
        folder = tmp_path / name
        execute_run(_args(folder, 60))
        runs.append(json.loads((folder / "state.json").read_text()))
    a, b = runs
    assert a["domestic_credit"] == b["domestic_credit"]
    assert a["finance"] == b["finance"]
    books = a["domestic_credit"]
    assert books["totals"]["lent_merchants"] > 0
    flows = (books["totals"]["interest_merchants"] + books["totals"]["repaid_merchants"]
             - books["totals"]["lent_merchants"])
    assert books["merchant_applied"] + sum(books["merchant_due"]) == pytest.approx(flows, abs=1e-6)
    loans = [e for e in a["events_timeline"] if e["event_type"] == "loan_taken"
             and "merchant houses" not in e["description"] and " from the " in e["description"]]
    assert loans, "domestic loans name their lenders"


def test_a_checkpoint_resume_continues_the_books_exactly(tmp_path):
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
    execute_run(_args(straight, 40, checkpoint_every=15, checkpoint=str(straight / "c{turn}.ckpt")))
    assert rc.describe(straight / "c15.ckpt")["flags"]["domestic_credit"] is True
    for k in (15, 30):
        resumed = tmp_path / f"resumed_{k}"
        args = _args(resumed, 40)
        args.domestic_credit = None
        execute_run(args, checkpoint_resume=rc.read_checkpoint(straight / f"c{k}.ckpt"))
        expected, got = outputs(straight), outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []
        assert json.loads((resumed / "state.json").read_text())["domestic_credit"]["totals"]["lent_merchants"] > 0
