"""D1c's constructed foreign-membership transition on the compiled runtime.

Only the initial saved movement memberships are constructed. Wealth debits,
native lapse/recruitment, mortality, migration and exact restore are real.
This is a mechanism/compatibility test, not a held efficacy screen.
"""
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


@pytest.fixture
def constructed_members(monkeypatch):
    import chronicler.main as main_mod
    from chronicler.agent_movements_state import Movement, MovementState
    generate = main_mod.generate_world

    def constructed(*args, **kwargs):
        world = generate(*args, **kwargs)
        host = 1
        regions = {r.name: i for i, r in enumerate(world.regions)}
        home_region = regions[world.civilizations[0].regions[0]]
        foreign_region = regions[world.civilizations[host].regions[0]]
        movement = Movement(name="Constructed foreign membership", creed=0, founded_turn=-10,
                            home_region=home_region, target=0, stage_turn=-10,
                            members=160, peak_members=160,
                            member_regions=[[home_region, 80], [foreign_region, 80]])
        world.agent_movements = MovementState(movements=[movement])
        return world

    monkeypatch.setattr(main_mod, "generate_world", constructed)


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _bundle(folder):
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(folder / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at", None)
    return bundle


def _strip(value):
    if isinstance(value, dict):
        out = {k: _strip(v) for k, v in value.items() if k != "movement_branches"}
        if "livelihoods" in out and isinstance(out["livelihoods"], dict) and set(out["livelihoods"]) <= {"schema_version"}:
            out.pop("livelihoods")
        return out
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def test_actual_branch_fee_and_exact_resume_with_permission_due_next_tick(tmp_path, monkeypatch, constructed_members):
    from chronicler.movement_branches import record_status
    from chronicler.run_checkpoint import read_checkpoint
    argv = ["--seed", "23", "--agents", "hybrid", "--simulate-only", "--turns", "18", "--movement-branches"]
    straight, resumed = tmp_path / "straight", tmp_path / "resumed"
    _cli(monkeypatch, straight, *argv, "--checkpoint-turns", "3")
    ckpt = straight / "checkpoint_turn_3.ckpt"
    saved = read_checkpoint(ckpt).state.world.livelihoods.movement_branches
    assert saved.frame_turn == 2 and saved.frame.turn == 2
    assert any(row.status == "funded" and row.active_from == 3 and len(row.payers) >= 3 for row in saved.frame.rows)
    assert saved.book.flows and all(f.payer[0] == "agent_wealth" and f.payee[0] == "civ_treasury"
                                     and f.applied == 10 for f in saved.book.flows)
    _cli(monkeypatch, resumed, "--resume", str(ckpt), "--simulate-only")
    assert _bundle(straight) == _bundle(resumed)
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    for snapshot in _bundle(straight)["history"]:
        assert record_status(snapshot)[0] in ("recorded", "recorded_zero")


def test_record_only_preserves_native_world_and_history(tmp_path, monkeypatch, constructed_members):
    argv = ["--seed", "23", "--agents", "hybrid", "--simulate-only", "--turns", "12"]
    off, record = tmp_path / "off", tmp_path / "record"
    _cli(monkeypatch, off, *argv)
    _cli(monkeypatch, record, *argv, "--movement-branches", "--movement-branches-mode", "record_only")
    a, b = _bundle(off), _bundle(record)
    assert _strip(a) == _strip(b)
    frames = [s["livelihoods"]["movement_branches"]["frame"] for s in b["history"]]
    assert any(row["members"] > 0 for f in frames for row in f["rows"])
    assert all(row["dues_milli"] == 0 and row["active_from"] is None for f in frames for row in f["rows"])
