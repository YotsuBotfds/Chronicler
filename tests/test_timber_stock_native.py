"""L3 timber stock on the real compiled extension (``timber_harvest_cap_{slot}``).

docs/integration/timber-stock.md: hybrid turns settle every timber slot from
the economy's realized slot output, the kernel never exceeds the offered cap,
the cost-retaining ablation leaves the trajectory of a run without the stock
unchanged, and the extension refuses an invalid cap.
"""
import math
from pathlib import Path

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _native():
    import chronicler_agents as ca
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def _run(tmp_path, *extra, seed=3, turns=30, tuning=None):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    from chronicler.tuning import load_tuning
    tmp_path.mkdir(parents=True, exist_ok=True)
    argv = ["--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
            "--agents", "hybrid", "--simulate-only",
            "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra]
    if tuning:
        path = tmp_path / "tuning.yaml"
        path.write_text(tuning)
        argv += ["--tuning", str(path)]
    args = _build_parser().parse_args(argv)
    args.tuning_overrides = load_tuning(Path(args.tuning)) if args.tuning else {}
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def _strip(bundle):
    import json
    b = json.loads(json.dumps(bundle))
    b["metadata"] = {}
    b["world_state"].pop("livelihoods", None)
    b["world_state"].pop("tuning_overrides", None)
    for snap in b["history"]:
        snap.pop("livelihoods", None)
    return b


def test_hybrid_turns_settle_realized_output_under_the_cap(tmp_path, monkeypatch):
    _native()
    from chronicler import timber_stock as T
    seen = {"slots": 0, "binding": 0}
    original = T.finish_phase2

    def checked_finish(world, economy_result, agent_bridge, acc):
        offered = dict(world.livelihoods.timber_stock._offered)
        events = original(world, economy_result, agent_bridge, acc)
        for row in world.livelihoods.timber_stock.ledger:
            region = world.regions[row.region_id]
            assert row.extraction == economy_result.slot_output[region.name][row.slot]
            cap, _possible = offered[(row.region_id, row.slot)]
            assert row.cap == cap and row.extraction <= cap
            seen["slots"] += 1
            seen["binding"] += bool(row.capped)
        return events

    monkeypatch.setattr(T, "finish_phase2", checked_finish)
    # Every stand starts cut over, so the cap binds from the first harvest.
    enable = T.set_timber_stock_enabled

    def cut_over(world, value, **kwargs):
        enable(world, value, **kwargs)
        for row in world.livelihoods.timber_stock.stocks:
            row.stock *= 0.001

    monkeypatch.setattr(T, "set_timber_stock_enabled", cut_over)
    bundle = _run(tmp_path, "--timber-stock")
    assert seen["slots"] > 0 and seen["binding"] > 0
    for snap in bundle["history"]:
        record = snap["livelihoods"]["timber_stock"]
        assert record["observed"] and record["completed_turn"] == snap["turn"] == record["source_turn"] + 1
        for row in record["regions"]:
            closing = math.fsum([row["opening"], -row["cleared"], -(row["extraction"] - row["overdraft"]),
                                 row["regrowth"], -row["removed"]])
            assert closing == pytest.approx(row["stock"], rel=1e-12, abs=1e-9)
            assert row["overdraft"] == 0.0 and row["extraction"] <= row["cap"]
    assert bundle["world_state"]["livelihoods"]["timber_stock"]["totals"]["observed_turns"] == 30


def test_the_ablation_keeps_the_trajectory_of_a_run_without_the_stock(tmp_path):
    _native()
    off = _run(tmp_path / "off")
    ablation = _run(tmp_path / "ablation", "--timber-stock",
                    tuning="livelihoods:\n  timber:\n    enforce_cap: 0\n")
    records = [snap["livelihoods"]["timber_stock"] for snap in ablation["history"]]
    assert all(r["enforce_cap"] is False and r["observed"] for r in records)
    assert all(row["cap"] is None for r in records for row in r["regions"])
    assert _strip(ablation) == _strip(off)


def test_the_extension_refuses_a_cap_off_a_timber_slot(tmp_path, monkeypatch):
    _native()
    import pyarrow as pa
    from chronicler import timber_stock as T
    original = T.prepare_phase2

    def bad_prepare(world, region_input, agent_bridge, snapshot, acc):
        batch = original(world, region_input, agent_bridge, snapshot, acc)
        i = batch.schema.get_field_index("timber_harvest_cap_2")
        return batch.set_column(i, "timber_harvest_cap_2",
                                pa.array([1.0] * batch.num_rows, type=pa.float32()))

    monkeypatch.setattr(T, "prepare_phase2", bad_prepare)
    with pytest.raises(ValueError, match="invalid timber harvest cap"):
        _run(tmp_path, "--timber-stock", turns=2)
