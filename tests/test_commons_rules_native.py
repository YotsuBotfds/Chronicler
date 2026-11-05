"""L8 commons rules on the real compiled extension.

docs/integration/commons-rules.md: the native kernel honours the lowered
``timber_harvest_cap_{slot}`` (a binding rule's harvest never exceeds its
limit), the bills are charged through the accumulator, cost_only leaves every
cap as the timber stock offered it, and a run with the switch on but no rule
adopted keeps the trajectory of a timber-only run.
"""
from pathlib import Path

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _native():
    import chronicler_agents as ca
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def _run(tmp_path, *extra, seed=3, turns=30):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    from chronicler.tuning import load_tuning
    tmp_path.mkdir(parents=True, exist_ok=True)
    argv = ["--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
            "--agents", "hybrid", "--simulate-only",
            "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra]
    args = _build_parser().parse_args(argv)
    args.tuning_overrides = load_tuning(Path(args.tuning)) if args.tuning else {}
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def _strip(bundle):
    import json
    b = json.loads(json.dumps(bundle))
    b["metadata"] = {}
    b["world_state"]["livelihoods"].pop("commons_rules", None)
    for snap in b["history"]:
        snap.get("livelihoods", {}).pop("commons_rules", None)
    return b


def _cut_over(monkeypatch):
    """Every stand starts cut over, so rules are adopted from the second turn."""
    from chronicler import timber_stock as T
    enable = T.set_timber_stock_enabled

    def cut_over(world, value, **kwargs):
        enable(world, value, **kwargs)
        for row in world.livelihoods.timber_stock.stocks:
            row.stock *= 0.001

    monkeypatch.setattr(T, "set_timber_stock_enabled", cut_over)


def _checked(monkeypatch, seen):
    from chronicler import commons_rules as C
    original = C.finish_phase2

    def finish(world, economy_result, agent_bridge, acc):
        plan = world.livelihoods.commons_rules._plan
        before = len(acc._changes)
        events = original(world, economy_result, agent_bridge, acc)
        for row, receipt in zip(plan.rows, world.livelihoods.commons_rules.frame, strict=True):
            region = world.regions[receipt.region_id]
            assert receipt.extraction == economy_result.slot_output[region.name][receipt.slot]
            if receipt.applied and world.livelihoods.commons_rules.mode == "enforced":
                assert receipt.extraction <= receipt.limit
            seen["rows"] += 1
            seen["binding"] += bool(receipt.binding)
            seen["paid"] += receipt.paid
        charged = [c for c in acc._changes[before:] if c.stat == "treasury" and c.category == "keep"]
        assert -sum(c.delta for c in charged) == sum(row.paid for row in plan.rows)
        seen["keep_changes"] += len(charged)
        return events

    monkeypatch.setattr(C, "finish_phase2", finish)


def test_the_kernel_honours_a_lowered_cap_and_bills_are_charged(tmp_path, monkeypatch):
    _native()
    _cut_over(monkeypatch)
    seen = {"rows": 0, "binding": 0, "paid": 0, "keep_changes": 0}
    _checked(monkeypatch, seen)
    bundle = _run(tmp_path, "--timber-stock", "--commons-rules")
    assert seen["rows"] > 0 and seen["binding"] > 0 and seen["paid"] > 0 and seen["keep_changes"] > 0
    counters = bundle["world_state"]["livelihoods"]["commons_rules"]["counters"]
    assert counters["adopted"] >= 1 and counters["tightened_turns"] > 0 and counters["paid"] == seen["paid"]
    for snap in bundle["history"]:
        record = snap["livelihoods"]["commons_rules"]
        assert record["observed"] and record["completed_turn"] == snap["turn"] == record["source_turn"] + 1
        timber = {(r["region_id"], r["slot"]): r for r in snap["livelihoods"]["timber_stock"]["regions"]}
        for receipt in record["receipts"]:
            row = timber[(receipt["region_id"], receipt["slot"])]
            assert receipt["extraction"] == row["extraction"] and receipt["stock_cap"] == row["cap"]
            if receipt["applied"]:
                assert receipt["extraction"] <= receipt["limit"] < receipt["stock_cap"]


def test_cost_only_leaves_every_cap_as_the_stock_offered(tmp_path, monkeypatch):
    _native()
    _cut_over(monkeypatch)
    from chronicler import commons_rules as C, timber_stock as T
    seen = {"tightened": 0}
    original = T.tighten_harvest_caps

    def spy(*args, **kwargs):
        seen["tightened"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(T, "tighten_harvest_caps", spy)
    bundle = _run(tmp_path, "--timber-stock", "--commons-rules", "--commons-rule-mode", "cost_only")
    counters = bundle["world_state"]["livelihoods"]["commons_rules"]["counters"]
    assert seen["tightened"] == 0 and counters["adopted"] >= 1 and counters["paid"] > 0
    assert counters["binding_turns"] == 0 and counters["tightened_turns"] == 0
    assert C.MODES == ("enforced", "cost_only")


def test_switch_on_without_adoption_keeps_the_timber_only_trajectory(tmp_path):
    _native()
    plain = _run(tmp_path / "timber", "--timber-stock")
    ruled = _run(tmp_path / "commons", "--timber-stock", "--commons-rules")
    counters = ruled["world_state"]["livelihoods"]["commons_rules"]["counters"]
    assert counters["eligible_slot_turns"] > 0 and counters["adopted"] == 0
    assert _strip(ruled) == _strip(plain)
