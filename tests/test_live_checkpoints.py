"""Exact checkpoints of live sessions (chronicler.live_checkpoints).

A live run that saves writes what one that does not writes; a session
resumed from any of its checkpoints writes what the uninterrupted session
writes and shows a connecting viewer the same history; interventions are
recorded in the checkpoint; a viewer's request names no path.

Offline lane: no sockets (``tests/live_session_harness.py`` plays the
viewer through the server's queues) and the native ecology/politics
runtimes held off. Socket-level protocol tests are in
``tests/test_live_integration.py``; native agent modes in
``tests/test_live_checkpoints_native.py``.
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
from pathlib import Path

import pytest

import chronicler.run_checkpoint as rc
from chronicler.live import LiveServer, make_live_pause
from chronicler.live_checkpoints import (
    LIVE_CHECKPOINT_DIR, LiveCheckpointError, LiveCheckpoints, LiveView,
)
from tests.live_session_harness import outputs, session

START = {"turns": 12, "civs": 3, "regions": 6, "seed": 42, "scenario": None}


@pytest.fixture(autouse=True)
def _pure_python_lane(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, **extra) -> argparse.Namespace:
    """A live CLI namespace (world size, seed and length come from ``start``)."""
    args = argparse.Namespace(
        seed=None, turns=None, civs=None, regions=None, worldgen=None,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=4, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", local_url=None, live_port=0, pause_every=4,
        narrator="local",
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _first_civ() -> str:
    """The first civ of START's world (the live session builds the same one)."""
    from chronicler.world_gen import generate_world
    return generate_world(seed=START["seed"], num_regions=START["regions"],
                          num_civs=START["civs"]).civilizations[0].name


def _ckpt(folder: Path, turn: int) -> Path:
    return folder / "ckpt" / f"turn_{turn:04d}.ckpt"


def _straight(tmp_path: Path, **script):
    folder = tmp_path / "straight"
    _, viewer, _ = session(_args(folder, checkpoint_every=1,
                                 checkpoint=str(folder / "ckpt" / "turn_{turn:04d}.ckpt")),
                           start=START, **script)
    return folder, viewer


def _resume(tmp_path: Path, path: Path, name: str, **script):
    folder = tmp_path / name
    # As the CLI does (main._adopt_checkpoint_args): the checkpoint's turns
    # and seed; the pause interval comes from the session's view.
    args = _args(folder, resume=str(path), turns=12, seed=42, pause_every=None)
    result, viewer, _ = session(args, exact_resume=rc.read_checkpoint(path), **script)
    return folder, viewer, result


def _same_views(resumed, straight, k: int) -> None:
    # A viewer connecting at the resumed pause, after every later turn and
    # after completion is sent what the uninterrupted session sends.
    assert resumed.views[k] == straight.views[k]
    assert {t: v for t, v in resumed.views.items() if t >= k} == \
        {t: v for t, v in straight.views.items() if t >= k}
    assert resumed.final_view == straight.final_view


def test_saving_changes_nothing_and_every_save_resumes_exactly(tmp_path):
    _, plain, _ = session(_args(tmp_path / "plain"), start=START)
    # Saves while running (from turn 2) and while paused (turn 8), and a
    # checkpoint at every turn.
    folder, straight = _straight(tmp_path, on_turn={2: [("checkpoint",)]},
                                 at_pause={8: [("checkpoint",)]})
    # The running save lands on the first boundary after the request (turn 2
    # unless the run outpaced the viewer); the paused one on the pause.
    running, paused = straight.saved
    assert 2 <= running["turn"] < 8 and paused["turn"] == 8
    for saved in straight.saved:
        assert Path(saved["path"]) == folder / LIVE_CHECKPOINT_DIR / f"turn_{saved['turn']:04d}.ckpt"
        assert saved["exact"] and saved["resume_hint"] == f"--live --resume {saved['path']}"
    assert outputs(tmp_path / "plain") == outputs(folder)
    assert plain.views == straight.views and plain.final_view == straight.final_view
    assert plain.pauses == straight.pauses == [(4, "pause_interval"), (8, "pause_interval"),
                                              (12, "pause_interval")]

    for k, path in [(1, _ckpt(folder, 1)), (4, _ckpt(folder, 4)), (6, _ckpt(folder, 6)),
                    (11, _ckpt(folder, 11)),
                    (running["turn"], Path(running["path"])), (8, Path(paused["path"]))]:
        resumed_dir, resumed, result = _resume(tmp_path, path, f"resume_{path.parent.name}_{k}")
        assert result.total_turns == 12
        assert resumed.pauses[0] == (k, "resumed")
        assert outputs(resumed_dir) == outputs(folder), k
        _same_views(resumed, straight, k)


def test_interventions_are_kept_in_the_checkpoint_of_their_turn(tmp_path):
    civ = _first_civ()
    script = {4: [("set", civ, "military", 90), ("inject", "plague", civ)]}
    session(_args(tmp_path / "plain"), start=START, at_pause=script)
    folder, straight = _straight(tmp_path, at_pause=script)
    session(_args(tmp_path / "untouched"), start=START)
    assert outputs(tmp_path / "plain") == outputs(folder)
    assert outputs(tmp_path / "untouched") != outputs(folder)  # they change the run

    # The turn-4 checkpoint was written again after the pause: it holds both
    # and records them; earlier checkpoints do not, later ones carry them.
    header = rc.describe(_ckpt(folder, 4))
    assert header["run_config"]["interventions"] == [
        {"turn": 4, "command": "set", "civ": civ, "stat": "military", "value": 90},
        {"turn": 4, "command": "inject", "event_type": "plague", "civ": civ}]
    assert "interventions" not in rc.describe(_ckpt(folder, 3))["run_config"]
    assert rc.describe(_ckpt(folder, 9))["run_config"]["interventions"] == \
        header["run_config"]["interventions"]

    resumed_dir, resumed, _ = _resume(tmp_path, _ckpt(folder, 4), "resume_4")
    assert outputs(resumed_dir) == outputs(folder)
    _same_views(resumed, straight, 4)
    # From before the pause, the viewer repeats them at turn 4.
    resumed_dir, resumed, _ = _resume(tmp_path, _ckpt(folder, 2), "resume_2", at_pause=script)
    assert outputs(resumed_dir) == outputs(folder)
    _same_views(resumed, straight, 2)


def test_a_save_holds_the_pause_as_it_was_when_written(tmp_path):
    """A request sent before a command is written before it is applied."""
    civ = _first_civ()
    folder, _ = _straight(tmp_path, at_pause={4: [("checkpoint",), ("set", civ, "military", 90)]})
    early = rc.read_checkpoint(folder / LIVE_CHECKPOINT_DIR / "turn_0004.ckpt")
    late = rc.read_checkpoint(_ckpt(folder, 4))
    assert next(c for c in late.state.world.civilizations if c.name == civ).military == 90
    assert next(c for c in early.state.world.civilizations if c.name == civ).military != 90
    assert "interventions" not in early.state.run_config


def test_quit_at_the_resumed_pause_writes_nothing(tmp_path):
    folder, _ = _straight(tmp_path)
    resumed_dir, resumed, result = _resume(tmp_path, _ckpt(folder, 5), "quit", at_resume=[("quit",)])
    assert result is None and resumed.pauses == [(5, "resumed")]
    assert not (resumed_dir / "chronicle_bundle.json").exists()


def test_a_save_at_the_resumed_pause_is_the_loaded_run(tmp_path):
    folder, straight = _straight(tmp_path)
    resumed_dir, resumed, _ = _resume(tmp_path, _ckpt(folder, 5), "resume_5",
                                      at_resume=[("checkpoint",)])
    saved = resumed_dir / LIVE_CHECKPOINT_DIR / "turn_0005.ckpt"
    assert [m["path"] for m in resumed.saved] == [str(saved)]
    again_dir, again, _ = _resume(tmp_path, saved, "again")
    assert outputs(again_dir) == outputs(folder)
    _same_views(again, straight, 5)


def test_a_single_run_checkpoint_resumes_live_with_a_rebuilt_view(tmp_path):
    from chronicler.main import execute_run
    single = tmp_path / "single"
    execute_run(_args(single, seed=42, turns=12, civs=3, regions=6, checkpoint_every=6,
                      checkpoint=str(single / "ckpt" / "turn_{turn:04d}.ckpt")))
    resumed_dir, resumed, _ = _resume(tmp_path, _ckpt(single, 6), "resume")
    assert outputs(resumed_dir) == outputs(single)
    init = json.loads(resumed.views[6])
    assert [row["turn"] for row in init["history"]] == list(range(1, 7))
    assert init["current_turn"] == 6 and init["world_state"]["turn"] == 6


def test_an_extended_resume_shows_and_saves_the_new_length(tmp_path):
    folder, _ = _straight(tmp_path)
    args = _args(tmp_path / "longer", resume=str(_ckpt(folder, 12)), turns=16, seed=42,
                 pause_every=None)
    _, viewer, _ = session(
        args, exact_resume=rc.read_checkpoint(_ckpt(folder, 12)), at_resume=[("checkpoint",)],
    )
    init = json.loads(viewer.views[12])
    assert init["total_turns"] == init["metadata"]["total_turns"] == 16
    assert json.loads(viewer.final_view)["current_turn"] == 16

    saved = tmp_path / "longer" / LIVE_CHECKPOINT_DIR / "turn_0012.ckpt"
    loaded = rc.read_checkpoint(saved)
    assert loaded.state.world.turn == 12
    assert loaded.state.num_turns == 16
    from chronicler.main import _adopt_checkpoint_args, _build_parser
    parser = _build_parser()
    resumed_args = parser.parse_args(["--live", "--resume", str(saved)])
    assert _adopt_checkpoint_args(parser, resumed_args, loaded) == []
    assert resumed_args.turns == 16


def test_a_live_run_records_the_clients_world(tmp_path):
    folder, _ = _straight(tmp_path)
    simulation = rc.describe(_ckpt(folder, 3))["run_config"]["simulation_args"]
    assert (simulation["civs"], simulation["regions"], simulation["turns"]) == (3, 6, 12)
    assert rc.read_checkpoint(_ckpt(folder, 3)).state.live["pause_every"] == 4


# --- the request: authentication, fields, state, paths -------------------------

def test_checkpoint_requests_need_this_session_and_name_nothing(tmp_path):
    server = LiveServer(port=0)
    ok_path = f"/?token={server.token}"
    lobby = server.checkpoint_reply({"type": "checkpoint"}, origin=None, path=ok_path)
    assert lobby == {"type": "checkpoint_error", "message": "No live run to checkpoint"}
    server._server_state = "running"
    server.checkpoints = LiveCheckpoints(tmp_path, queue.Queue(), LiveView(), lambda: 1.0, 10)
    for origin, path in [(None, "/?token=wrong"), (None, "/"),
                         ("http://evil.example", ok_path)]:
        reply = server.checkpoint_reply({"type": "checkpoint"}, origin=origin, path=path)
        assert reply["type"] == "checkpoint_error" and reply["message"].startswith("Not authorized")
    for extra in ({"path": "/etc/passwd"}, {"name": "../x"}, {"turn": 3}):
        reply = server.checkpoint_reply({"type": "checkpoint", **extra}, origin=None, path=ok_path)
        assert reply["type"] == "checkpoint_error" and "takes no fields" in reply["message"]
    assert server.checkpoints._requests.empty()
    assert server.checkpoint_reply({"type": "checkpoint"}, origin="http://localhost:5173",
                                   path=ok_path) == {"type": "checkpoint_requested", "paused": False}
    assert server.checkpoints._requests.qsize() == 1
    server.checkpoints.close("finished")
    assert server.checkpoint_reply({"type": "checkpoint"}, origin=None, path=ok_path) == {
        "type": "checkpoint_error", "message": "The run has finished"}
    # The queued request is answered too.
    assert server.checkpoints.status_queue.get_nowait() == {"type": "checkpoint_error",
                                                            "message": "finished"}


def test_checkpoint_files_stay_in_the_output_directory(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    checkpoints = LiveCheckpoints(out, queue.Queue(), LiveView(), lambda: 1.0, 10)
    assert checkpoints.path_for(7) == out / LIVE_CHECKPOINT_DIR / "turn_0007.ckpt"
    for bad in (-1, "7", "../7", True, 7.0):
        with pytest.raises(LiveCheckpointError):
            checkpoints.path_for(bad)
    # A file in its place that is a link (or a directory) is refused.
    outside = tmp_path / "outside.ckpt"
    (out / LIVE_CHECKPOINT_DIR / "turn_0008.ckpt").symlink_to(outside)
    with pytest.raises(LiveCheckpointError):
        checkpoints.path_for(8)
    (out / LIVE_CHECKPOINT_DIR / "turn_0009.ckpt").mkdir()
    with pytest.raises(LiveCheckpointError):
        checkpoints.path_for(9)
    # A checkpoint directory that leads elsewhere is refused.
    other = tmp_path / "other"
    other.mkdir()
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / LIVE_CHECKPOINT_DIR).symlink_to(other, target_is_directory=True)
    with pytest.raises(LiveCheckpointError):
        LiveCheckpoints(linked, queue.Queue(), LiveView(), lambda: 1.0, 10).path_for(1)
    assert not list(other.iterdir()) and not outside.exists()
    # Braces in the output directory are not a template.
    braces = tmp_path / "run{turn}"
    braced = LiveCheckpoints(braces, queue.Queue(), LiveView(), lambda: 1.0, 10)

    def save(template):
        path = rc.checkpoint_path(template, 3)
        path.write_bytes(b"x")
        return path

    braced.bind(save, {})
    reply = braced.save_now(argparse.Namespace(turn=3))
    assert reply["type"] == "checkpoint_saved" and reply["bytes"] == 1
    assert reply["path"] == str(braces / LIVE_CHECKPOINT_DIR / "turn_0003.ckpt")


def test_a_failed_save_is_reported_and_the_run_goes_on(tmp_path):
    status = queue.Queue()
    checkpoints = LiveCheckpoints(tmp_path, status, LiveView(), lambda: 1.0, 10)
    checkpoints.request()
    world = argparse.Namespace(turn=2)
    assert checkpoints.turn_end(world) is False  # unbound: refused, not raised
    reply = status.get_nowait()
    assert reply["type"] == "checkpoint_error" and reply["turn"] == 2

    def broken(template):
        raise OSError("disk full")

    checkpoints.bind(broken, {})
    checkpoints.request()
    checkpoints.request()
    assert checkpoints.service(world) == 2  # one write for both, one reply each
    replies = [status.get_nowait(), status.get_nowait()]
    assert all(r["type"] == "checkpoint_error" and "disk full" in r["message"] for r in replies)


def test_the_pause_lists_checkpoint_and_writes_requests_while_paused(tmp_path):
    from chronicler.world_gen import generate_world
    world = generate_world(seed=3, num_regions=4, num_civs=2)
    civ = world.civilizations[0].name
    commands, status = queue.Queue(), queue.Queue()
    checkpoints = LiveCheckpoints(tmp_path, status, LiveView(), lambda: 1.0, 10)
    seen = []

    def save(template):
        path = rc.checkpoint_path(template, world.turn)
        seen.append(next(c.military for c in world.civilizations if c.name == civ))
        path.write_bytes(b"x")
        return path

    checkpoints.bind(save, {})
    pause = make_live_pause(commands, status, output_dir=tmp_path, checkpoints=checkpoints)
    checkpoints.request()
    commands.put({"type": "set", "civ": civ, "stat": "military", "value": 77})
    commands.put({"type": "continue"})
    assert pause(world, {}, []) is True
    messages = [status.get_nowait() for _ in range(status.qsize())]
    assert [m["type"] for m in messages] == ["paused", "checkpoint_saved", "ack", "ack"]
    assert "checkpoint" in messages[0]["valid_commands"]
    # Written before the set was applied.
    assert len(seen) == 1 and seen[0] != 77 and world.civilizations[0].military == 77
    assert checkpoints.turn_end(world) is True and checkpoints.turn_end(world) is False


def test_the_cli_resumes_only_exact_checkpoints_live(tmp_path, monkeypatch, capsys):
    import chronicler.live
    import chronicler.main as main_mod
    from chronicler.main import execute_run

    single = tmp_path / "single"
    execute_run(_args(single, seed=42, turns=6, civs=3, regions=6, checkpoint_every=3,
                      checkpoint=str(single / "turn_{turn}.ckpt")))
    calls = []
    monkeypatch.setattr(chronicler.live, "run_live",
                        lambda args, exact_resume=None: calls.append((args, exact_resume)))
    base = ["chronicler", "--live", "--live-port", "0", "--simulate-only",
            "--output", str(tmp_path / "live" / "chronicle.md")]
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "state.json")])
    with pytest.raises(SystemExit) as refused:
        main_mod.main()
    assert refused.value.code == 2 and "is not one" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "turn_3.ckpt")])
    main_mod.main()
    (args, loaded), = calls
    assert loaded.state.world.turn == 3 and args.seed == 42 and args.turns == 6
    assert args.regions == 6 and args.civs == 3
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "turn_3.ckpt"),
                                      "--agents", "hybrid"])
    with pytest.raises(SystemExit):
        main_mod.main()
    assert "conflicts with the checkpoint" in capsys.readouterr().err
