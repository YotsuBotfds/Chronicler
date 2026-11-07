"""C2 epidemic care with the real native extension (hybrid runs).

Natural runs name and pay carers within L9 envelopes and the next tick
applies their dated capacity; ``cost_only`` names, reserves and pays the same
carers and changes nothing else until care first changes a tick; an exact
checkpoint resume during an outbreak with carers named and capacity pending
reproduces every file; carers never hold a second job in the same turn beside
health care and PL3 crews (the native registry refuses a double booking). Run
against a freshly built extension.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.native


def _native():
    native = pytest.importorskip("chronicler_agents")
    sim = getattr(native, "AgentSimulator", None)
    if not isinstance(sim, type) or not all(hasattr(sim, name) for name in (
            "reserve_work", "extend_paid_work", "transfer_wealth", "wealth_transfer_purposes", "checkpoint_state")):
        pytest.skip("requires a fresh chronicler_agents build (work registry, paid work, wealth transfers)")
    return native


def _args(folder: Path, turns: int, *, seed: int = 42, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, simulate_only=True, agents="hybrid", tuning_overrides={},
        grain_reserves=True, local_budgets=True,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _history(folder: Path) -> list[dict]:
    from chronicler.bundle_codec import load_bundle
    return load_bundle(folder / "chronicle_bundle.json")["history"]


def _care(snapshot: dict) -> dict | None:
    return (snapshot.get("livelihoods") or {}).get("epidemic_care")


def _outputs(folder: Path, after: int = -1) -> dict[str, bytes]:
    from chronicler.bundle_codec import load_bundle
    out = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt":
            continue
        stem = path.stem
        if "_turn_" in stem and int(stem.rsplit("_", 1)[1]) <= after:
            continue
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            out[path.name] = json.dumps(data, sort_keys=True).encode()
        else:
            out[path.relative_to(folder).as_posix()] = path.read_bytes()
    return out


def test_carers_are_named_paid_and_their_dated_capacity_lowers_the_next_tick(tmp_path):
    _native()
    from chronicler.epidemic_care import CARE_CFR_REDUCTION
    from chronicler.main import execute_run
    execute_run(_args(tmp_path, 60, epidemic_care=True))
    history = _history(tmp_path)
    frames = {s["turn"]: _care(s) for s in history if _care(s) is not None}
    assert len(frames) == len(history)
    staffed = applied = 0
    for label, care in sorted(frames.items()):
        assert care["source_turn"] == label - 1
        for row in care["frame"] or []:
            if row["carers"]:
                staffed += 1
                assert row["wages_paid_milli"] + row["wage_residual_milli"] == row["wages_due_milli"]
                assert row["care_time"] <= row["need"] + 1e-5 or row["limit"] != "need_met"
        for row in care["ledger"] or []:
            assert row["treasury_units"] * 1000 + row["carry_before"] == row["paid_milli"] + row["carry_after"]
        # The tick applies exactly the capacity dated the turn before, once.
        before = frames.get(label - 1)
        expected = {c["region"]: c for c in (before or {}).get("capacity", [])}
        got = {a["region"]: a for a in (care["tick"] or {}).get("applied", [])}
        assert set(got) == set(expected)
        for region, a in got.items():
            assert a["source_turn"] == label - 2 and a["patients"] == expected[region]["patients"]
            assert a["care_factor"] == pytest.approx(1 - CARE_CFR_REDUCTION * a["coverage"])
            applied += a["coverage"] > 0
    assert staffed > 0 and applied > 0
    # Every care envelope the budget awarded was settled from the frame.
    budget = history[-1]["livelihoods"]["local_budgets"]
    assert budget["counters"].get("awards", 0) > 0


def test_cost_only_is_identical_until_care_first_changes_a_tick(tmp_path):
    _native()
    from chronicler.main import execute_run
    runs = {}
    for mode in ("care", "cost_only"):
        folder = tmp_path / mode
        execute_run(_args(folder, 40, epidemic_care=True, epidemic_care_mode=mode))
        runs[mode] = _history(folder)
    first = next(s["turn"] for s in runs["care"]
                 if any(a["care_factor"] < 1 for a in ((_care(s) or {}).get("tick") or {}).get("applied", [])))
    for care, cost in zip(runs["care"], runs["cost_only"]):
        if care["turn"] >= first:
            # The tick of snapshot ``first`` is the first that differs: the same
            # capacity and coverage, only the factor applied.
            a = {r["region"]: r for r in _care(care)["tick"]["applied"]}
            b = {r["region"]: r for r in _care(cost)["tick"]["applied"]}
            assert {k: (v["patients"], v["coverage"], v["would_be"]) for k, v in a.items()} == \
                   {k: (v["patients"], v["coverage"], v["would_be"]) for k, v in b.items()}
            assert all(v["care_factor"] == 1.0 for v in b.values())
            break
        x, y = json.loads(json.dumps(care)), json.loads(json.dumps(cost))
        x["livelihoods"]["epidemic_care"].pop("mode")
        y["livelihoods"]["epidemic_care"].pop("mode")
        assert x == y, care["turn"]


def test_exact_resume_during_an_outbreak_with_carers_and_pending_capacity(tmp_path):
    _native()
    import chronicler.run_checkpoint as rc
    from chronicler.main import execute_run
    turns = 60
    straight = tmp_path / "straight"
    execute_run(_args(straight, turns, epidemic_care=True, checkpoint_every=1,
                      checkpoint=str(straight / "c{turn}.ckpt")))
    chosen = []
    for k in range(1, turns):
        world = rc.read_checkpoint(straight / f"c{k}.ckpt").state.world
        care = world.livelihoods.epidemic_care
        reported = any(row.reported for row in world.epidemics.rows)
        if care.capacity and care.frame and any(r.carers for r in care.frame) and reported:
            chosen.append(k)
    assert chosen, "no checkpoint during an outbreak with carers named and capacity pending"
    for k in (chosen[0], chosen[len(chosen) // 2]):
        resumed = tmp_path / f"resumed_{k}"
        execute_run(_args(resumed, turns), checkpoint_resume=rc.read_checkpoint(straight / f"c{k}.ckpt"))
        expected, got = _outputs(straight, after=k), _outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []


def test_carers_hold_no_second_job_beside_health_care_and_recovery_crews(tmp_path):
    """The native registry refuses anyone already holding registry or rural
    health work, so a completed run is itself the check; the records agree."""
    _native()
    from chronicler.main import execute_run
    execute_run(_args(tmp_path, 50, epidemic_care=True, health_care=True, grain_storage=True,
                      repair_projects=True, recovery_crews=True))
    history = _history(tmp_path)
    named = clash = 0
    for s in history:
        care = _care(s) or {}
        carers = {c["agent_id"] for r in care.get("frame") or [] for c in r["carers"]}
        named += len(carers)
        crews = (s.get("livelihoods") or {}).get("recovery_crews") or {}
        members = {m["agent_id"] for r in crews.get("receipts") or [] for m in r["members"]}
        clash += len(carers & members)
    assert named > 0 and clash == 0


def test_a_switched_off_switch_on_a_new_world_changes_nothing(tmp_path):
    _native()
    from chronicler.main import execute_run
    execute_run(_args(tmp_path / "omitted", 20))
    execute_run(_args(tmp_path / "off", 20, epidemic_care=False))
    a, b = _outputs(tmp_path / "omitted"), _outputs(tmp_path / "off")
    assert a.keys() == b.keys() and [k for k in a if a[k] != b[k]] == []
