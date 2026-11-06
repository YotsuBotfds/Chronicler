"""A5-1 on the real compiled extension: war, resumes and resource checks.

Retail rules version 2 (the default of a new retail state). Development worlds
only, with the checkpoint-3 base flags and retail in every controlled region
(``--household-retail-boundary all``); campaigns are on (the default for new
worlds). Natural, not constructed: template seed 3 has Dorrathi Clans besiege
Obsidian Shore (region 1, the Ashkari capital) on turns 0-2, occupy it on turn 2
and receive it by treaty on turn 3; procedural seed 11 (32 x 10) has sieges
from turn 1. ``CHRONICLER_REQUIRE_RETAIL_NATIVE=1`` makes missing retail
methods a failure, as in ``test_household_retail_native.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("chronicler_agents")

from chronicler import household_retail as HR
from chronicler.run_checkpoint import read_checkpoint

pytestmark = pytest.mark.native

#: The checkpoint-3 base (``productive_recovery_screens.CP3.BASE`` without --turns)
#: and retail v2 in every controlled region.
CP3 = ["--grain-reserves", "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
       "--grain-storage", "--food-allocation", "--workshops", "--operating-wear", "--repair-projects", "--timber-stock"]
RETAIL = ["--household-retail", "--household-retail-boundary", "all"]
TEMPLATE_3 = ["--seed", "3", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only", *CP3, *RETAIL]
PROCEDURAL_11 = ["--seed", "11", "--worldgen", "procedural", "--regions", "32", "--civs", "10", "--agents", "hybrid",
                 "--simulate-only", *CP3, *RETAIL]
OBSIDIAN = 1


def _ready():
    from chronicler_agents import AgentSimulator
    return all(callable(getattr(AgentSimulator, name, None)) for name in HR.NATIVE_METHODS)


READY = _ready()


def test_the_retail_methods_this_module_needs_are_present():
    if os.environ.get("CHRONICLER_REQUIRE_RETAIL_NATIVE") == "1":
        assert READY, "CHRONICLER_REQUIRE_RETAIL_NATIVE=1: the retail native methods are missing"


def _run(out: Path, argv: list[str], *extra: str) -> dict:
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    execute_run(_build_parser().parse_args([*argv, *extra, "--output", str(out / "chronicle.md"),
                                            "--state", str(out / "state.json")]))
    return load_bundle(out / "chronicle_bundle.json")


def _main(monkeypatch, *argv: str) -> None:
    from chronicler.main import main
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv])
    main()


def _retail(bundle) -> list[dict]:
    return [s["livelihoods"]["household_retail"] for s in bundle["history"]
            if (s.get("livelihoods") or {}).get("household_retail")]


def _war_losses(records) -> dict[tuple, dict]:
    """Every war loss record seen in the run's snapshots, once each."""
    seen = {}
    for r in records:
        for rec in r["log"]:
            if rec["kind"] == "war_loss":
                seen[(rec["turn"], rec["region"], rec["cause"], rec["actor"], rec["milli"])] = rec
    return seen


def _assert_frames_close(records) -> None:
    for r in records:
        for f in r["regions"] or ():
            signed = sum(HR.FLOW_SIGNS[k] * v for k, v in f["flows"].items())
            assert f["open_milli"] + signed == f["close_milli"] == sum(f["goods_close"])


def test_a_refusal_in_an_asyncio_task_reaches_its_caller(monkeypatch):
    """Review A5, finding 4: ``asyncio.run`` raises the refusal to its caller
    as the ``ValueError`` it is (a ``SystemExit`` would be taken for a shutdown).
    Here, not offline: an event loop needs a socket pair."""
    import asyncio
    from chronicler.livelihoods import LivelihoodsRefusal, configure_livelihoods
    from chronicler.main import _build_parser
    from tests.test_household_retail import VERDANT, Harness, _people
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    h = Harness(retail=False)
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 6.0}})

    async def configure():
        configure_livelihoods(h.world, _build_parser().parse_args([]), agent_mode="off")
    with pytest.raises(LivelihoodsRefusal) as refused:
        asyncio.run(configure())
    assert isinstance(refused.value, ValueError) and not isinstance(refused.value, SystemExit)


if READY:

    def test_a_legacy_state_file_resume_with_hybrid_settles_every_resumed_turn(tmp_path, monkeypatch):
        """RL3: a legacy resume given --agents hybrid runs L2 and retail. The rebuilt
        pool closes every saved claim to the commons on the first resumed turn and
        retail settles each resumed turn. Without hybrid the saved world is
        refused cleanly: one ``Error:`` line, status 1, no traceback."""
        first = tmp_path / "first"
        _run(first, ["--seed", "7", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only",
                     "--food-allocation", *RETAIL], "--turns", "6")
        saved = json.loads((first / "state.json").read_text(encoding="utf-8"))
        retail = saved["livelihoods"]["household_retail"]
        held = sum(sum(r["claims"].values()) for r in retail["regions"])
        assert saved["turn"] == 6 and retail["rules_version"] == 2 and held > 0
        settled = retail["counters"]["turns_settled"]
        resumed = tmp_path / "resumed"
        _main(monkeypatch, "--resume", str(first / "state.json"), "--agents", "hybrid", "--simulate-only",
              "--turns", "10", "--output", str(resumed / "chronicle.md"), "--state", str(resumed / "state.json"))
        from chronicler.bundle_codec import load_bundle
        bundle = load_bundle(resumed / "chronicle_bundle.json")
        assert bundle["metadata"]["resume"] == {"kind": "legacy-state", "exact": False, "turn": 6}
        records = {r["source_turn"]: r for r in _retail(bundle) if r["source_turn"] >= 6}
        assert sorted(records) == [6, 7, 8, 9] and all(r["regions"] is not None for r in records.values())
        assert all(any(f["provisioning"] for f in r["regions"]) for r in records.values())
        food = [s["livelihoods"]["food_allocation"] for s in bundle["history"]
                if s.get("source_turn", s.get("turn", 0)) >= 6 and (s.get("livelihoods") or {}).get("food_allocation")]
        assert food                                                  # L2 ran too
        first_turn = records[6]
        assert sum(f["commons"].get("pool_reset", 0) for f in first_turn["regions"]) == held
        assert [r["kind"] for r in first_turn["log"]].count("pool_reset") >= 1
        final = json.loads((resumed / "state.json").read_text(encoding="utf-8"))["livelihoods"]["household_retail"]
        assert final["counters"]["pool_resets"] == 1 and final["counters"]["turns_settled"] == settled + 4
        _assert_frames_close(records.values())
        # Without --agents hybrid: the clean refusal, before any turn runs.
        import chronicler
        env = {**os.environ, "PYTHONPATH": str(Path(chronicler.__file__).resolve().parents[1]),
               "CHRONICLER_QUIET": "1"}
        refused = tmp_path / "refused"
        done = subprocess.run([sys.executable, "-c", "from chronicler.main import main; main()",
                               "--resume", str(first / "state.json"), "--simulate-only", "--turns", "10",
                               "--output", str(refused / "chronicle.md"), "--state", str(refused / "state.json")],
                              capture_output=True, text=True, env=env, timeout=300)
        assert done.returncode == 1, done.stderr
        assert "Traceback" not in done.stderr
        assert done.stderr.strip().splitlines()[-1].startswith(
            "Error: --household-retail requires --agents hybrid and --food-allocation; this world has it on")
        assert not (refused / "chronicle_bundle.json").exists()

    def test_an_exact_resume_inside_a_natural_siege_and_occupation_equals_the_straight_run(tmp_path, monkeypatch):
        """Template seed 3: resumes at the start of turn 2 (a live siege, siege turn
        2 of 3: the siege turn and the occupation start follow) and of turn 3 (a
        live occupation: the treaty cession follows) are byte-identical to the
        straight run, and each war loss appears once."""
        straight = tmp_path / "straight"
        ck = tmp_path / "ck"
        a = _run(straight, TEMPLATE_3, "--turns", "6", "--checkpoint-every", "1",
                 "--checkpoint", str(ck / "turn_{turn:04d}.ckpt"))
        losses = _war_losses(_retail(a))
        assert Counter((t, cause) for t, region, cause, _a, _m in losses if region == OBSIDIAN) == Counter(
            {(0, "siege"): 1, (1, "siege"): 1, (2, "siege"): 1, (2, "occupation"): 1, (3, "conquest"): 1})
        (cession,) = [rec for k, rec in losses.items() if k[2] == "conquest"]
        assert (cession["actor_name"], cession["victim_name"]) == ("Dorrathi Clans", "Ashkari Nomads")
        assert cession["note"].endswith("(ceded by treaty)")
        _assert_frames_close(_retail(a))
        for turn, live in ((2, "siege"), (3, "occupation")):
            state = read_checkpoint(ck / f"turn_{turn:04d}.ckpt").state
            world = state.world
            assert world.turn == turn
            entry = world.livelihoods.household_retail.region(OBSIDIAN)
            assert entry is not None and sum(entry.goods) > 0              # owned food in the war region
            if live == "siege":
                assert any(army.phase == "sieging" and army.region == world.regions[OBSIDIAN].name
                           for army in world.war_state.armies)
            else:
                assert [o.region for o in world.war_state.occupations] == [world.regions[OBSIDIAN].name]
            state.agent_bridge.close()
            resumed = tmp_path / f"resumed_{turn}"
            _main(monkeypatch, "--resume", str(ck / f"turn_{turn:04d}.ckpt"),
                  "--output", str(resumed / "chronicle.md"), "--state", str(resumed / "state.json"))
            from chronicler.bundle_codec import load_bundle
            b = load_bundle(resumed / "chronicle_bundle.json")
            assert a["history"] == b["history"] and a["world_state"] == b["world_state"]

    def test_campaigns_with_retail_everywhere_balance_under_the_resource_checks(tmp_path, monkeypatch):
        """Procedural development world 11: natural sieges of pilot regions with
        CHRONICLER_CHECK_RESOURCES=1; every frame closes."""
        monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
        bundle = _run(tmp_path, PROCEDURAL_11, "--turns", "12")
        records = _retail(bundle)
        assert records and all(r.get("rules_version") == 2 for r in records)
        losses = _war_losses(records)
        assert any(k[2] == "siege" for k in losses), "a natural siege of a pilot region was expected"
        assert all(rec["actor"] is not None and rec["victim"] is not None for rec in losses.values())
        _assert_frames_close(records)
        counters = records[-1]["counters"]
        assert counters["war_loss_milli"] == sum(counters.get(f"war_loss_{c}_milli", 0) for c in HR.WAR_CAUSES)
        assert "requisition_exempt_region_turns" not in counters
