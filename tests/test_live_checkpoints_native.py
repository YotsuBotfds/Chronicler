"""Live checkpoints with the real native extension: a hybrid live session
(agent pool, validation sidecars) resumed from its checkpoints writes what
the uninterrupted session writes and shows a connecting viewer the same
history; off mode with the native ecology and politics runtimes as well
(chronicler.live_checkpoints, tests/live_session_harness.py)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import chronicler.run_checkpoint as rc
from chronicler.live_checkpoints import LIVE_CHECKPOINT_DIR
from tests.live_session_harness import outputs, session

pytestmark = pytest.mark.native

START = {"turns": 10, "civs": 3, "regions": 6, "seed": 42, "scenario": None}


@pytest.fixture(autouse=True)
def _native():
    ca = pytest.importorskip("chronicler_agents")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(ca, name, None)
        if not isinstance(cls, type) or not hasattr(cls, "checkpoint_state"):
            pytest.skip("requires a chronicler_agents build with exact checkpoints")


def _args(folder: Path, agents: str, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=None, turns=None, civs=None, regions=None, worldgen=None,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=5, llm_actions=False, scenario=None,
        simulate_only=True, agents=agents, local_url=None, live_port=0, pause_every=5,
        narrator="local", validation_sidecar=agents != "off",
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


@pytest.mark.parametrize("agents", ["hybrid", "off"])
def test_a_live_session_resumes_exactly(tmp_path, agents):
    _, plain, _ = session(_args(tmp_path / "plain", agents), start=START)
    straight = tmp_path / "straight"
    _, viewer, _ = session(_args(straight, agents, checkpoint_every=1,
                                 checkpoint=str(straight / "ckpt" / "turn_{turn:04d}.ckpt")),
                           start=START, at_pause={5: [("checkpoint",)]})
    assert outputs(tmp_path / "plain") == outputs(straight)
    assert plain.views == viewer.views and plain.final_view == viewer.final_view
    loaded_native = rc.read_checkpoint(straight / "ckpt" / "turn_0005.ckpt")
    natives = [s["name"] for s in loaded_native.header["sections"] if s["name"] != "python"]
    assert natives == (["native.agent.0"] if agents == "hybrid"
                       else ["native.ecology.0", "native.politics.0"])

    for k, path in [(2, straight / "ckpt" / "turn_0002.ckpt"),
                    (5, straight / LIVE_CHECKPOINT_DIR / "turn_0005.ckpt"),
                    (7, straight / "ckpt" / "turn_0007.ckpt")]:
        folder = tmp_path / f"resume_{k}"
        args = _args(folder, agents, resume=str(path), turns=10, seed=42, pause_every=None)
        _, resumed, _ = session(args, exact_resume=rc.read_checkpoint(path))
        assert resumed.pauses[0] == (k, "resumed")
        # The per-turn sidecar files of turns up to k are written by the run
        # that played them.
        assert outputs(folder) == outputs(straight, after=k), k
        assert {t: v for t, v in resumed.views.items() if t >= k} == \
            {t: v for t, v in viewer.views.items() if t >= k}
        assert resumed.final_view == viewer.final_view


def test_enabled_public_grain_live_midtransit_native_checkpoint_is_exact(tmp_path, monkeypatch):
    """Actual hybrid run/live writer, native economy and StatAccumulator legs.

    The host must supply its fresh own-source wheel. This is not a physical
    efficacy/scale claim. Only initial conditions are controlled; every wrapped
    producer delegates once to the original, without changing its result.
    """
    import hashlib
    import importlib.machinery
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as compiled
    from chronicler import live, public_grain_shipments as shipments, grain_reserves
    from chronicler.accumulator import StatAccumulator
    from chronicler.bundle_codec import load_bundle
    from chronicler.economy import EconomyResult
    from chronicler.finance import _projections
    from chronicler.models import Disposition
    from chronicler.agent_bridge import AgentBridge

    extension = Path(compiled.__file__)
    assert any(str(extension).endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
    assert package.AgentSimulator is compiled.AgentSimulator
    native_digest = hashlib.sha256(extension.read_bytes()).hexdigest()
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    horizon = 8
    arm = {"name": "straight"}
    traces = {name: {"dispatch": [], "arrival": [], "final_native": None}
              for name in ("straight", "resumed")}
    checkpoints = {}
    original_world = live._live_world

    def initial_world(args, params):
        candidate, scenario = original_world(args, params)
        state = grain_reserves._ensure(candidate)
        buyer_name = candidate.civilizations[2].name
        for region, granary in zip(candidate.regions, state.granaries):
            if region.controller is not None:
                granary.owner = candidate.civ_index_map[region.controller]
                granary.observed, granary.harvest_mean, granary.harvest_sq = 12, 0.5, 0.5
                # Positive scarce food avoids a zero-stock bootstrap. Foreign
                # public markets retain finite real stocks and ordinary prices.
                region.stockpile.goods = {"grain": 0.01 if region.controller == buyer_name else 500.0}
        for civ in candidate.civilizations:
            civ.treasury = 500
        for row in candidate.relationships.values():
            for relation in row.values():
                relation.disposition = Disposition.NEUTRAL
        return candidate, scenario

    original_dispatch = shipments.dispatch_order
    def observe_dispatch(candidate, **kwargs):
        bridge = candidate._agent_bridge
        assert isinstance(bridge, AgentBridge)
        assert isinstance(bridge._sim, compiled.AgentSimulator)
        assert isinstance(bridge._economy_result, EconomyResult)
        acc = kwargs["acc"]
        assert isinstance(acc, StatAccumulator)
        changes, start, watermark = acc._changes, len(acc._changes), acc._keep_applied_up_to
        before = _projections(candidate, acc)
        direct = tuple(c.treasury for c in candidate.civilizations)
        result = original_dispatch(candidate, **kwargs)
        if result is not None:
            order = candidate.grain_reserves.shipments.pending[-1]
            transition = candidate.grain_reserves.shipments.frame[-1]
            assert transition.order == order.order and transition.dispatch_turn == order.dispatch_turn
            assert acc._changes is changes and acc._keep_applied_up_to == watermark
            legs = [(c.civ_id, c.stat, c.delta, c.category) for c in changes[start:]]
            assert legs == [(order.buyer, "treasury", -order.paid, "keep"),
                            (order.seller, "treasury", order.paid, "keep")]
            expected = list(before)
            expected[order.buyer] -= order.paid
            expected[order.seller] += order.paid
            assert _projections(candidate, acc) == expected
            assert tuple(c.treasury for c in candidate.civilizations) == direct
            traces[arm["name"]]["dispatch"].append({
                "id": transition.id, "turn": candidate.turn, "paid": order.paid,
                "net": order.net, "buyer": order.buyer, "seller": order.seller, "legs": legs})
        return result

    original_arrivals = shipments.settle_arrivals
    def observe_arrivals(candidate):
        before = tuple(c.treasury for c in candidate.civilizations)
        result = original_arrivals(candidate)
        assert tuple(c.treasury for c in candidate.civilizations) == before
        state = candidate.grain_reserves.shipments
        if state.frame_turn == candidate.turn:
            traces[arm["name"]]["arrival"].extend(
                {"id": row.id, "turn": row.turn, "paid_at_dispatch": row.paid, "net": row.net}
                for row in state.frame if row.operation == "arrived")
        return result

    original_write = rc.write_checkpoint
    def observe_checkpoint(path, state, **kwargs):
        assert isinstance(state.agent_bridge._sim, compiled.AgentSimulator)
        native = state.agent_bridge._sim.checkpoint_state()
        world_json = state.world.model_dump_json()
        result = original_write(path, state, **kwargs)
        assert state.agent_bridge._sim.checkpoint_state() == native
        assert state.world.model_dump_json() == world_json
        checkpoints[Path(path)] = {"native": native, "world_json": world_json}
        return result

    original_close = AgentBridge.close
    def observe_close(bridge):
        result = original_close(bridge)
        traces[arm["name"]]["final_native"] = bridge._sim.checkpoint_state()
        return result

    monkeypatch.setattr(live, "_live_world", initial_world)
    monkeypatch.setattr(shipments, "dispatch_order", observe_dispatch)
    monkeypatch.setattr(shipments, "settle_arrivals", observe_arrivals)
    monkeypatch.setattr(rc, "write_checkpoint", observe_checkpoint)
    monkeypatch.setattr(AgentBridge, "close", observe_close)
    straight = tmp_path / "grain_straight"
    start = {"turns": horizon, "civs": 4, "regions": 8, "seed": 42, "scenario": None}
    _, viewer, _ = session(_args(straight, "hybrid", pause_every=1, grain_reserves=True,
                                public_grain_shipments=True, transaction_receipts=True),
                            start=start,
                            at_pause={turn: [("checkpoint",)] for turn in range(1, horizon)})
    assert viewer.error is None
    pending = []
    for turn in range(1, horizon):
        path = straight / LIVE_CHECKPOINT_DIR / f"turn_{turn:04d}.ckpt"
        assert path in checkpoints
        saved = json.loads(checkpoints[path]["world_json"])["grain_reserves"]["shipments"]
        if saved["pending"]:
            pending.append((turn, path, saved["pending"][0]))
    assert pending, "bounded real Native run must dispatch a foreign public order"
    turn, path, order = pending[0]  # preregistered earliest actual midtransit pause
    assert order["dispatch_turn"] == turn - 1 and order["due_turn"] == turn
    ident = f"public-grain-shipment:{order['dispatch_turn']}:{order['order']}"
    loaded = rc.read_checkpoint(path)
    assert loaded.exact and loaded.mismatches == [] and loaded.state.live is not None
    assert [s["name"] for s in loaded.header["sections"]] == ["python", "native.agent.0"]
    assert loaded.header["identity"]["native"]["sha256"] == native_digest
    assert loaded.state.world.model_dump_json() == checkpoints[path]["world_json"]
    assert loaded.state.agent_bridge._sim.checkpoint_state() == checkpoints[path]["native"]
    assert loaded.state.world._agent_bridge is loaded.state.agent_bridge
    assert loaded.state.run_config["simulation_args"]["public_grain_shipments"] is True
    assert loaded.state.world.grain_reserves.shipments.pending[0].order == order["order"]

    resumed = tmp_path / "grain_resumed"
    arm["name"] = "resumed"
    _, again, _ = session(_args(resumed, "hybrid", resume=str(path), turns=horizon,
                               seed=42, pause_every=1), exact_resume=loaded)
    assert again.pauses[0] == (turn, "resumed")
    assert outputs(resumed) == outputs(straight, after=turn)
    assert again.final_view == viewer.final_view
    assert {t:v for t,v in again.views.items() if t >= turn} == {t:v for t,v in viewer.views.items() if t >= turn}
    assert traces["resumed"]["final_native"] == traces["straight"]["final_native"]
    assert traces["resumed"]["final_native"] is not None
    assert traces["resumed"]["dispatch"] == [row for row in traces["straight"]["dispatch"] if row["turn"] >= turn]
    assert sum(row["id"] == ident for row in traces["straight"]["dispatch"]) == 1
    assert not any(row["id"] == ident for row in traces["resumed"]["dispatch"])
    for name in ("straight", "resumed"):
        delivered = [row for row in traces[name]["arrival"] if row["id"] == ident]
        assert len(delivered) == 1 and delivered[0]["turn"] == order["due_turn"]
        assert delivered[0]["paid_at_dispatch"] == order["paid"]
        assert delivered[0]["net"] == order["net"]

    bundle = load_bundle(straight / "chronicle_bundle.json")
    transitions = [row for snapshot in bundle["history"]
                   for row in snapshot.get("grain_reserves", {}).get("shipments", {}).get("transitions", [])
                   if row["id"] == ident]
    assert [row["operation"] for row in transitions] == ["dispatched", "arrived"]
    assert transitions[1]["turn"] == transitions[0]["turn"] + 1
