"""Real native migration output joined to guarded X1/public-health readers."""
from __future__ import annotations

from dataclasses import replace
import pickle

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _rows(batch):
    import pyarrow as pa
    return pa.record_batch(batch).to_pylist()


def _append(world, events):
    from chronicler.agent_bridge import EVENT_TYPE_MAP
    from chronicler.models import AgentEventRecord
    for e in events:
        world.agent_events_raw.append(AgentEventRecord(
            turn=world.turn, agent_id=e["agent_id"], event_type=EVENT_TYPE_MAP[e["event_type"]],
            region=e["region"], target_region=e["target_region"], civ_affinity=e["civ_affinity"],
            occupation=e["occupation"], belief=e["belief"], migration_driver=e["migration_driver"]))


def _environment(world, crowding):
    from chronicler import public_health as PH
    from chronicler.public_health_state import PublicHealthState
    object.__setattr__(world.livelihoods, "public_health", PublicHealthState(crowding=crowding))
    return PH.environment_factors(world)


def test_actual_native_unknown_moves_have_label_invariant_arrival_facts_and_density_exposure():
    from chronicler import residence_ledger as RL
    from chronicler.models import MIGRATION_DRIVER_NAMES
    from tests.test_decision_delivery_native import _setup, _signals
    from tests.test_residence_ledger import FakeBridge, _world

    sim, world = _setup(), _world(turn=0)
    RL.phase10(world, None, None, FakeBridge(sim))
    world.turn += 1
    witnessed = False
    for _ in range(12):
        sim.set_adaptive_information(world.turn, [])
        events = _rows(sim.tick(world.turn, _signals(), 1.0))
        _append(world, events)
        unknown = [e for e in events if e["event_type"] == 2 and e["migration_driver"] == 255]
        if not unknown:
            RL.phase10(world, None, None, FakeBridge(sim))
            world.turn += 1
            continue

        witnessed = True
        known = pickle.loads(pickle.dumps(world))
        code = MIGRATION_DRIVER_NAMES.index("material_need")
        known.agent_events_raw = [replace(e, migration_driver=code)
            if e.turn == world.turn and e.event_type == "migration" and e.migration_driver == 255 else e
            for e in known.agent_events_raw]
        # The native post-tick pool is literally the same read-only source in
        # both writes. Only the copied event's reason is adversarially changed.
        before = sim.checkpoint_state()
        RL.phase10(world, None, None, FakeBridge(sim))
        RL.phase10(known, None, None, FakeBridge(sim))
        assert sim.checkpoint_state() == before
        a, b = world.livelihoods.residence_ledger.frame, known.livelihoods.residence_ledger.frame
        for key in ("alive", "observed", "recent_residence_arrivals"):
            assert a["totals"][key] == b["totals"][key]
        assert a["totals"]["recent_residence_arrivals"] > 0
        assert a["totals"]["recent_residence_arrivals_unknown_reason"] > 0
        def physical(frame):
            return [(r["region"], r["residents"], r["recent_residence_arrivals"]) for r in frame["regions"]
                    if r["residents"] or r["recent_residence_arrivals"]]
        assert physical(a) == physical(b)
        world.turn += 1
        known.turn += 1
        ea, eb = _environment(world, "density_only"), _environment(known, "density_only")
        assert [r["crowding_factor"] for r in ea] == [r["crowding_factor"] for r in eb] == [1.0] * len(world.regions)
        # Preserve the old experiment exactly as an explicitly named control.
        old_a, old_b = _environment(world, "legacy_displacement"), _environment(known, "legacy_displacement")
        assert any(x["crowding_factor"] != y["crowding_factor"] for x, y in zip(old_a, old_b, strict=True))
        break
    assert witnessed, "the fixed tiny native fixture must actually emit a driver255 migration"


def test_native_checkpoint_resumes_actual_unknown_migrations_and_residential_frames_exactly():
    from chronicler import residence_ledger as RL
    from chronicler_agents import AgentSimulator
    from tests.test_decision_delivery_native import _setup, _signals
    from tests.test_residence_ledger import FakeBridge, _world

    original, world = _setup(), _world(turn=0)
    RL.phase10(world, None, None, FakeBridge(original))
    world.turn += 1
    while world.turn < 6:
        original.set_adaptive_information(world.turn, [])
        events = _rows(original.tick(world.turn, _signals(), 1.0))
        _append(world, events)
        RL.phase10(world, None, None, FakeBridge(original))
        world.turn += 1
    restored = AgentSimulator.from_checkpoint_state(original.checkpoint_state())
    resumed_world = pickle.loads(pickle.dumps(world))
    actual_moves = 0
    for _ in range(6):
        for native in (original, restored):
            native.set_adaptive_information(world.turn, [])
        left = _rows(original.tick(world.turn, _signals(), 1.0))
        right = _rows(restored.tick(resumed_world.turn, _signals(), 1.0))
        assert left == right
        actual_moves += sum(e["event_type"] == 2 for e in left)
        for w, native, events in ((world, original, left), (resumed_world, restored, right)):
            _append(w, events)
            RL.phase10(w, None, None, FakeBridge(native))
            w.turn += 1
        assert original.checkpoint_state() == restored.checkpoint_state()
        assert world.livelihoods.residence_ledger.frame == resumed_world.livelihoods.residence_ledger.frame
        assert _environment(world, "density_only") == _environment(resumed_world, "density_only")
    assert actual_moves > 0, "checkpoint comparison must include real moves, not just a quiet clock"


def test_enabled_full_stack_exact_resume_keeps_selected_crowding_rule_and_arrow_outputs(tmp_path, monkeypatch):
    from pathlib import Path
    import chronicler
    from chronicler.main import _build_parser, execute_run
    from chronicler.run_checkpoint import read_checkpoint
    from tests.test_run_checkpoint_native import _args, _outputs

    monkeypatch.syspath_prepend(str(Path(chronicler.__file__).resolve().parents[2] / "scripts"))
    import cw_integrated_screen as CW
    straight = tmp_path / "straight"
    args = _build_parser().parse_args([*CW.BASE, *CW.arm_flags(), "--seed", "5", "--turns", "16",
        "--worldgen", "template", "--regions", "8", "--civs", "4",
        "--adaptive-livelihoods-rules", "3", "--adaptive-livelihoods-decision-channels", "all",
        "--public-health-crowding", "density_only", "--checkpoint-every", "4",
        "--checkpoint", str(straight / "c{turn}.ckpt"),
        "--output", str(straight / "chronicle.md"), "--state", str(straight / "state.json")])
    execute_run(args)
    saved = read_checkpoint(straight / "c8.ckpt")
    world = saved.state.world
    assert world.livelihoods.public_health.crowding == "density_only"
    assert world.livelihoods.adaptive_livelihoods.rules == "3"
    assert world.livelihoods.adaptive_livelihoods.decision_channels == "all"
    assert world.livelihoods.residence_ledger.rows
    assert any(row.move_turn is not None for row in world.livelihoods.residence_ledger.rows.values())
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 16, "off"), checkpoint_resume=saved)
    assert _outputs(resumed) == _outputs(straight, after=8)
