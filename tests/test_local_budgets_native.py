"""L9 local budgets on the real compiled extension (hybrid runs).

Every governed payment in a real run must sit inside an accepted envelope
of the paying civilization for that turn: workshop bills, storage work and
granary purchases. The two arbitration modes spend the same kind of budget
differently, and an enabled world resumes exactly from a checkpoint.
"""
from __future__ import annotations

import random

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ("--grain-reserves", "--grain-storage", "--workshops", "--food-allocation", "--local-budgets")


def _run(tmp_path, *extra, seed=3, turns=60):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def _spending(bundle):
    """Per (turn, civ): governed payments observed in the services' own receipts."""
    from chronicler.grain_reserves_state import FLOW_KINDS
    paid = {}
    for snap in bundle["history"]:
        liv = snap.get("livelihoods") or {}
        for r in (liv.get("workshops") or {}).get("receipts") or []:
            total = sum((r.get("paid") or {}).values())
            if total:
                paid.setdefault((r["turn"], r["payer"], "workshop", r["site"]), 0)
                paid[(r["turn"], r["payer"], "workshop", r["site"])] += total
        reserves = snap.get("grain_reserves") or {}
        storage = reserves.get("storage") or {}
        for r in storage.get("receipts") or []:
            if r["treasury_paid"] and r["turn"] == reserves["source_turn"]:
                paid[(r["turn"], r["owner"], "storage", r["region"])] = r["treasury_paid"]
        for f in reserves.get("flows") or []:
            if f["kind"] in ("bought", "dispatched") and f["cost"]:
                key = (reserves["source_turn"], f["buyer"], "relief", None)
                paid[key] = paid.get(key, 0) + f["cost"]
    return paid


def _envelopes(bundle):
    out = {}
    for snap in bundle["history"]:
        lb = snap["livelihoods"]["local_budgets"]
        for c in lb["settled"] or []:
            service = "storage" if c["service"].startswith("granary") else c["service"]
            target = c["site"] if service == "workshop" else c["recipients"][0] if service == "storage" else None
            out[(c["for_turn"], c["civ"], service, target)] = c
    return out


def test_every_governed_payment_sits_inside_an_accepted_envelope(tmp_path):
    bundle = _run(tmp_path, *FLAGS)
    envelopes, paid = _envelopes(bundle), _spending(bundle)
    assert envelopes and paid
    for key, amount in paid.items():
        c = envelopes.get(key)
        assert c is not None, f"payment without an envelope: {key} {amount}"
        assert amount <= c["amount"] and c["spent"] == amount
    kept = [c for c in envelopes.values() if c["outcome"] == "kept"]
    assert kept and all(c["spent"] <= c["amount"] for c in envelopes.values())
    for snap in bundle["history"]:
        for d in snap["livelihoods"]["local_budgets"]["decisions"] or []:
            assert sum(a["amount"] for a in d["awards"]) <= d["budget"]
            claims = [c for a in d["awards"] for c in d["proposals"][a["pid"]]["claims"]]
            assert len(claims) == len(set(claims))
            assert len(d["proposals"]) <= 8 and all(p["source_turn"] == d["turn"] for p in d["proposals"])
    counters = bundle["history"][-1]["livelihoods"]["local_budgets"]["counters"]
    assert counters["spent_coins"] <= counters["envelope_coins"]


def test_bargained_and_fixed_shares_spend_the_budget_differently(tmp_path):
    bargained = _run(tmp_path / "bargained", *FLAGS)
    fixed = _run(tmp_path / "fixed", *FLAGS, "--local-budget-mode", "fixed_shares")

    def by_service(bundle):
        out = {}
        for (turn, civ, service, target), amount in _spending(bundle).items():
            out[service] = out.get(service, 0) + amount
        return out

    a, b = by_service(bargained), by_service(fixed)
    assert a != b
    last = fixed["history"][-1]["livelihoods"]["local_budgets"]
    assert last["mode"] == "fixed_shares" and last["counters"].get("responses", 0) == 0
    assert all(r == [] for s in fixed["history"] for r in [s["livelihoods"]["local_budgets"]["responses"] or []])


def _setup():
    from chronicler import grain_reserves as G
    from chronicler import local_budgets as LB
    from chronicler.agent_bridge import AgentBridge
    from chronicler.grain_storage import enable_storage
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    G.set_grain_reserves_enabled(world, True)
    enable_storage(world)
    for civ in world.civilizations:
        civ.treasury = 300
    world.livelihoods = LivelihoodsState()
    LB.set_local_budgets_enabled(world, True, args=type("A", (), {"local_budget_mode": None})(), agent_mode="hybrid")
    return world, AgentBridge(world, mode="hybrid")


def _advance(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    engine = ActionEngine(world)
    return run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed),
                    lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)


def test_open_envelopes_resume_exactly_from_a_checkpoint(tmp_path):
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    world, bridge = _setup()
    for _ in range(12):
        _advance(world, bridge)
        if world.livelihoods.local_budgets.open:
            break
    state = world.livelihoods.local_budgets
    assert state.open and state.decision_turn == world.turn - 1 and state._trace == {}
    path = tmp_path / "budgets.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
                                    era_reflections={}, pending_injections=[], start_turn=0, seed=42,
                                    num_turns=30, agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    resumed, resumed_bridge = loaded.state.world, loaded.state.agent_bridge
    assert resumed.model_dump_json() == world.model_dump_json()
    for _ in range(4):
        rng = random.getstate()
        _advance(world, bridge)
        after = random.getstate()
        random.setstate(rng)
        _advance(resumed, resumed_bridge)
        assert random.getstate() == after
        assert resumed.model_dump_json() == world.model_dump_json()
        assert resumed_bridge._sim.checkpoint_state() == bridge._sim.checkpoint_state()
    assert world.livelihoods.local_budgets.counters.get("awards", 0) >= 1


ALL_FLAGS = ("--grain-reserves", "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
             "--workshops", "--workshop-payroll", "--timber-stock", "--commons-rules", "--food-allocation",
             "--local-budgets")


def test_warden_bills_and_firm_academy_sales_sit_inside_their_envelopes(tmp_path):
    """Seed 1: academy orders from workshop firms from about turn 70, a
    commons rule paid from turn 85 (docs/integration/local-budgets.md)."""
    bundle = _run(tmp_path, *ALL_FLAGS, seed=1, turns=200)
    paid, envelopes, teaching = {}, {}, 0
    for snap in bundle["history"]:
        liv = snap["livelihoods"]
        commons = liv["commons_rules"]
        for r in commons["receipts"] or []:
            if r["paid"]:
                paid[(commons["source_turn"], r["owner"], "wardens", f'wardens:{r["region_id"]}:{r["slot"]}')] = r["paid"]
        for r in liv["workshop_payroll"]["receipts"] or []:
            if r["sales"]:
                paid[(r["turn"], r["controller"], "teaching_supplies", f'teaching:{r["site"]}')] = r["sales"] // 1000
        lb = liv["local_budgets"]
        for c in lb["settled"] or []:
            if c["service"] in ("wardens", "teaching_supplies"):
                envelopes[(c["for_turn"], c["civ"], c["service"], c["claims"][0])] = c
        for d in lb["decisions"] or []:
            teaching += sum(p["service"] == "teaching_supplies" for p in d["proposals"])
    assert any(key[2] == "wardens" for key in paid) and teaching >= 1
    for key, amount in paid.items():
        c = envelopes.get(key)
        assert c is not None, f"payment without an envelope: {key} {amount}"
        assert c["spent"] == amount <= c["amount"]
