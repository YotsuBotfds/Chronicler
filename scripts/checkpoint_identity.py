#!/usr/bin/env python3
"""Resume identity for exact checkpoints (``--checkpoint-every``, ``--resume``).

``run OUT_DIR --case NAME [--case ...] [--ks K,K,...] [--jobs 2] [--cli-arg ARG ...]``
    For each case: one straight run of N turns without checkpoints
    (``plain``), one with a checkpoint at every turn of K (``straight``),
    and for every k in K a run resumed from the turn-k checkpoint
    (``resume_k``). Then compares, byte for byte (``chronicle_bundle.json``
    decoded without ``metadata.generated_at``, as ``scripts/cities_identity.py``):

    * ``plain`` with ``straight``: writing checkpoints changes nothing;
    * every ``resume_k`` with ``straight``: every file the resumed run
      writes. Per-turn validation JSON files of turns up to k are written
      only by the run that played those turns and are not expected in
      ``resume_k``.

    ``resume_k`` directories and checkpoints are deleted after a passing
    comparison (``--keep`` keeps them). Default K: every turn 1..N-1 for
    the short cases, a spread for the long ones (``cases`` lists them).
    Runs use ``PYTHONHASHSEED=0`` and ``RAYON_NUM_THREADS=1`` (resumes:
    ``--resume-hash-seed``), one CLI subprocess each, at most ``--jobs``
    at a time. Writes ``OUT_DIR/<case>/report.json`` and prints a line per k.

``run OUT_DIR --case live_...``
    Live sessions (``--live``; docs/integration/checkpoint-continuation.md,
    section 11), driven over the WebSocket protocol as a viewer drives them:
    ``start`` with the case's world, ``continue`` at every pause, the case's
    interventions and checkpoint requests. ``plain`` saves nothing;
    ``straight`` writes a checkpoint at every turn and asks for the case's
    checkpoints (while running and while paused); every ``resume_k`` is
    ``--live --resume`` of the turn-k checkpoint (and ``resume_live_k`` of
    a viewer's checkpoint), repeating the interventions of later pauses.
    Besides every file, it compares what a viewer is sent: the view after
    each turn (the ``init`` message with the turn messages applied, as the
    server keeps it), the ``init`` a viewer connecting to the resumed
    session receives (against the uninterrupted view at turn k), the
    server's own ``init`` at a reconnect during the last pause and the view
    after completion.

``cases``
    Lists the case matrix.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# name -> (CLI arguments, turns, starting-agent target or 0, resume turns)
# Resume turns None: every turn 1..N-1 (short runs); "spread": SPREAD below.
CASES: dict[str, tuple[list[str], int, int, str | None]] = {
    "off_s42": (["--seed", "42", "--agents", "off"], 60, 0, None),
    "off_s7_scholarship": (["--seed", "7", "--agents", "off", "--scholarship"], 60, 0, None),
    "off_s42_minimal": (["--seed", "42", "--agents", "off", "--no-campaigns", "--no-governance",
                         "--no-contact-ledger", "--no-finance", "--no-diplomacy", "--no-techniques",
                         "--no-maritime", "--no-gp-agendas", "--no-nomads", "--no-cities",
                         "--no-agent-movements", "--no-guilds", "--no-historiography",
                         "--no-languages", "--no-fisheries"], 40, 0, None),
    "hybrid_s42": (["--seed", "42", "--agents", "hybrid", "--validation-sidecar"], 60, 0, None),
    "hybrid_s7_scholarship": (["--seed", "7", "--agents", "hybrid", "--scholarship",
                               "--validation-sidecar", "--relationship-stats"], 60, 0, None),
    "hybrid_s1234_fast": (["--seed", "1234", "--agents", "hybrid", "--agent-scale-mode", "fast"],
                          40, 0, None),
    "demographics_s42": (["--seed", "42", "--agents", "demographics-only"], 40, 0, None),
    "shadow_s42": (["--seed", "42", "--agents", "shadow"], 40, 0, None),
    "proc32_hybrid_s11": (["--seed", "11", "--regions", "32", "--civs", "8", "--worldgen",
                           "procedural", "--agents", "hybrid", "--validation-sidecar"], 40, 0, None),
    "proc48_hybrid_s42_scholarship": (["--seed", "42", "--regions", "48", "--civs", "10",
                                       "--agents", "hybrid", "--scholarship"], 40, 0, None),
    # The long runs of scripts/turn_speed_identity.py.
    "off_s42_long": (["--seed", "42", "--agents", "off"], 300, 0, "spread"),
    "hybrid_s42_long": (["--seed", "42", "--agents", "hybrid", "--validation-sidecar"], 200, 0,
                        "spread"),
    "hybrid_s7_long_scholarship": (["--seed", "7", "--agents", "hybrid", "--validation-sidecar",
                                    "--scholarship"], 200, 0, "spread"),
    "proc48_off_s7_long": (["--seed", "7", "--regions", "48", "--civs", "10", "--agents", "off"],
                           200, 0, "spread"),
    "proc48_hybrid_s42_long": (["--seed", "42", "--regions", "48", "--civs", "10", "--agents",
                                "hybrid", "--validation-sidecar"], 150, 0, "spread"),
    "scaled22k_s42": (["--seed", "42", "--regions", "12", "--civs", "4", "--agents", "hybrid",
                       "--validation-sidecar"], 30, 18800, "spread"),
    "scaled52k_s7": (["--seed", "7", "--regions", "12", "--civs", "4", "--agents", "hybrid"], 20,
                     43700, "spread"),
    # Four sects take the native slots of vanished faiths (turns 37, 100, 134,
    # 168): resumes on both sides of each change of the permanent faith table
    # (docs/integration/permanent-faiths.md).
    "proc32_hybrid_s42_recycling": (["--seed", "42", "--regions", "32", "--civs", "10", "--worldgen",
                                     "procedural", "--agents", "hybrid", "--validation-sidecar"], 200, 0,
                                    "spread"),
}

# Resume turns of a long run: early turns, a Fibonacci spread, the first
# economy sidecar turns (100 on) and the last turn.
SPREAD = (1, 2, 3, 5, 8, 13, 21, 34, 35, 40, 46, 55, 89, 99, 100, 101, 110, 144, 233)


def _default_ks(turns: int, kind: str | None) -> list[int]:
    if kind is None:
        return list(range(1, turns))
    return sorted({k for k in SPREAD if k < turns} | {turns // 2, turns - 1})


_SCALED_RUNNER = r"""
import sys
import chronicler.main as cm
from chronicler.utils import sync_civ_population
target = int(sys.argv[1])
original = cm.generate_world
def scaled(*a, **k):
    world = original(*a, **k)
    mult = target / max(1, sum(r.population for r in world.regions))
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
        region.population = round(region.population * mult)
    for civ in world.civilizations:
        sync_civ_population(civ, world)
    return world
cm.generate_world = scaled
sys.argv = ["chronicler"] + sys.argv[2:]
cm.main()
"""

_PER_TURN = re.compile(r"_turn_(\d+)\.json$")


def _env(hash_seed: str = "0") -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["RAYON_NUM_THREADS"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    return env


def _run(cmd: list[str], log: Path, env: dict) -> tuple[int, float]:
    t0 = time.monotonic()
    with open(log, "w") as fh:
        proc = subprocess.run(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, cwd=str(log.parent))
    return proc.returncode, time.monotonic() - t0


def _cmd(target: int, cli: list[str]) -> list[str]:
    if target:
        return [sys.executable, "-c", _SCALED_RUNNER, str(target), *cli]
    return [sys.executable, "-m", "chronicler.main", *cli]


def _outputs(directory: Path) -> list[str]:
    return ["--simulate-only", "--output", str(directory / "chronicle.md"),
            "--state", str(directory / "state.json")]


def _compare_resume(straight: Path, resumed: Path, k: int) -> tuple[int, list[str]]:
    from cities_identity import compare as compare_dirs
    checked, problems = compare_dirs(straight, resumed)
    kept = []
    for line in problems:
        if line.startswith("only in base: "):
            rel = line[len("only in base: "):]
            if rel.startswith("ckpt/"):
                continue
            m = _PER_TURN.search(rel)
            if m and int(m.group(1)) <= k:
                continue
        kept.append(line)
    return checked, kept


def run_case(out: Path, name: str, ks: list[int] | None, jobs: int, extra: list[str],
             keep: bool, resume_hash_seed: str) -> dict:
    cli, turns, target, kind = CASES[name]
    cli = [*cli, "--turns", str(turns), *extra]
    case = out / name
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    ks = sorted(set(ks if ks is not None else _default_ks(turns, kind)))
    ks = [k for k in ks if 0 < k < turns]
    report: dict = {"case": name, "cli": cli, "turns": turns, "target_agents": target, "ks": ks,
                    "results": {}}
    plain, straight = case / "plain", case / "straight"
    plain.mkdir()
    straight.mkdir()
    ckpt = straight / "ckpt"
    ckpt_args = ["--checkpoint-every", "1", "--checkpoint", str(ckpt / "turn_{turn:04d}.ckpt")]
    # Checkpoints not in K are deleted as soon as they appear (each is
    # complete when visible: written to a temporary file and renamed).
    sizes: dict[int, int] = {}
    stop = threading.Event()

    def prune() -> None:
        while True:
            done = stop.is_set()
            for path in sorted(ckpt.glob("turn_*.ckpt")):
                turn = int(path.stem.split("_")[1])
                if turn not in sizes:
                    sizes[turn] = path.stat().st_size
                if turn not in ks:
                    path.unlink()
            if done:
                return
            stop.wait(0.2)

    pruner = threading.Thread(target=prune, daemon=True)
    pruner.start()
    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        f_plain = pool.submit(_run, _cmd(target, [*cli, *_outputs(plain)]), case / "plain.log", _env())
        f_straight = pool.submit(_run, _cmd(target, [*cli, *_outputs(straight), *ckpt_args]),
                                 case / "straight.log", _env())
        (rc_p, s_p), (rc_s, s_s) = f_plain.result(), f_straight.result()
    stop.set()
    pruner.join()
    report["plain"] = {"exit": rc_p, "seconds": round(s_p, 2)}
    report["straight"] = {"exit": rc_s, "seconds": round(s_s, 2)}
    if rc_p or rc_s:
        report["error"] = "straight run failed"
        return report
    report["checkpoint_bytes"] = dict(sorted(sizes.items()))
    from cities_identity import compare as compare_dirs
    checked, problems = compare_dirs(plain, straight)
    problems = [p for p in problems if not p.startswith("only in new: ckpt/")]
    report["checkpointing_changes_nothing"] = {"files": checked, "differences": problems}
    print(f"{name}: plain vs straight with checkpoints: {checked} files, {len(problems)} differences",
          flush=True)

    def resume(k: int) -> tuple[int, dict]:
        rdir = case / f"resume_{k:04d}"
        rdir.mkdir()
        rc, secs = _run(_cmd(0, ["--resume", str(ckpt / f"turn_{k:04d}.ckpt"), *_outputs(rdir)]),
                        case / f"resume_{k:04d}.log", _env(resume_hash_seed))
        result = {"exit": rc, "seconds": round(secs, 2)}
        if rc == 0:
            n, diffs = _compare_resume(straight, rdir, k)
            result.update(files=n, differences=diffs)
            if not diffs and not keep:
                shutil.rmtree(rdir)
                (case / f"resume_{k:04d}.log").unlink()
        return k, result

    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        for k, result in pool.map(resume, ks):
            report["results"][str(k)] = result
            status = ("FAIL exit %d" % result["exit"] if result["exit"]
                      else f"{result['files']} files, {len(result['differences'])} differences")
            print(f"{name}: resume at {k}: {status}", flush=True)
            for line in result.get("differences", [])[:10]:
                print(f"    {line}", flush=True)
    passed = (not problems and all(r["exit"] == 0 and not r["differences"]
                                   for r in report["results"].values()))
    report["pass"] = passed
    if passed and not keep:
        shutil.rmtree(ckpt)
        shutil.rmtree(plain)
    (case / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({len(ks)} resume points)", flush=True)
    return report


# --- live sessions ----------------------------------------------------------------

# name -> (CLI arguments of the server, the viewer's ``start`` world, turns,
# pause interval, the viewer's script). Script: ``save_on_turn`` (ask for a
# checkpoint when that turn's message arrives), ``at_pause`` {turn: actions}
# with actions ``("set", stat, value)`` and ``("inject", event)`` on the first
# civ and ``("checkpoint",)``.
LIVE_CASES: dict[str, tuple[list[str], dict, int, int, dict]] = {
    "live_hybrid_s42": (["--agents", "hybrid", "--validation-sidecar"],
                        {"seed": 42, "civs": 4, "regions": 8}, 20, 5,
                        {"save_on_turn": [3],
                         "at_pause": {10: [("set", "military", 90), ("inject", "plague"),
                                           ("checkpoint",)]}}),
    "live_proc32_hybrid_s11": (["--agents", "hybrid", "--validation-sidecar"],
                               {"seed": 11, "civs": 8, "regions": 32, "worldgen": "procedural"},
                               20, 5, {"save_on_turn": [7], "at_pause": {15: [("checkpoint",)]}}),
    "live_off_s42": (["--agents", "off"], {"seed": 42, "civs": 4, "regions": 8}, 20, 5,
                     {"save_on_turn": [2], "at_pause": {5: [("checkpoint",)]}}),
}
_LIVE_TIMEOUT = 600.0


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _LiveProcess:
    """A ``--live`` CLI process: its log, and the viewer link it prints."""

    def __init__(self, cmd: list[str], log: Path, env: dict):
        self.log = open(log, "w")
        self.proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, cwd=str(log.parent))
        self.link: str | None = None
        self._found = threading.Event()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.log.write(line)
            self.log.flush()
            if line.startswith("Open viewer: ") and self.link is None:
                self.link = line.split("Open viewer: ", 1)[1].strip()
                self._found.set()
        self._found.set()

    def ws_url(self) -> str:
        from urllib.parse import parse_qs, urlsplit
        if not self._found.wait(120) or self.link is None:
            raise RuntimeError("the live session printed no viewer link")
        query = parse_qs(urlsplit(self.link).query)
        return f"{query['ws'][0]}/?token={query['token'][0]}"

    def finish(self) -> int:
        try:
            code = self.proc.wait(timeout=_LIVE_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.proc.kill()  # this process only (its PID)
            code = self.proc.wait()
        self._reader.join(timeout=10)
        self.log.close()
        return code


async def _drive(url: str, start: dict | None, turns: int, script: dict, resumed_at: int | None) -> dict:
    """Play the viewer; returns what it saw (view hashes, saves, pauses)."""
    import asyncio
    import websockets.asyncio.client as ws_client
    from chronicler.live import apply_completed_message, apply_turn_message

    out: dict = {"views": {}, "saves": [], "pauses": [], "errors": []}
    state: dict = {"view": None}

    async def connect():
        # A reconnect can find the previous connection not yet released.
        for _attempt in range(100):
            ws = await ws_client.connect(url, max_size=None)
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT))
            if first["type"] != "error":
                return ws, first
            await ws.close()
            await asyncio.sleep(0.1)
        raise RuntimeError("the live server kept refusing the connection")

    async def recv(ws) -> dict:
        """The next message, with the bookkeeping every message gets."""
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT))
        kind = msg["type"]
        if kind == "init" and msg.get("state") == "running":
            state["view"] = msg
            if resumed_at is not None and "connect_view" not in out:
                out["connect_view"] = _sha(json.dumps(msg))
                out["connect_turn"] = msg["current_turn"]
        elif kind == "turn":
            apply_turn_message(state["view"], msg)
            out["views"][str(msg["turn"])] = _sha(json.dumps(state["view"]))
        elif kind == "checkpoint_saved":
            out["saves"].append({key: msg[key] for key in ("turn", "path", "exact")})
        elif kind in ("checkpoint_error", "error"):
            out["errors"].append(msg)
        elif kind == "completed":
            apply_completed_message(state["view"], msg)
            out["final_view"] = _sha(json.dumps(state["view"]))
        return msg

    async def until(ws, kinds: set[str]) -> dict:
        while True:
            msg = await recv(ws)
            if msg["type"] in kinds:
                return msg

    ws, first = await connect()
    try:
        await ws.send(json.dumps({"type": "speed", "value": 1000}))
        if start is not None:
            assert first.get("state") == "lobby", first
            await ws.send(json.dumps({"type": "start", "turns": turns, "scenario": None, **start}))
        else:  # a resumed session: its view, then the pause at the checkpoint's turn
            assert first.get("state") == "running", first
            state["view"] = first
            out["connect_view"] = _sha(json.dumps(first))
            out["connect_turn"] = first["current_turn"]
        while True:
            msg = await recv(ws)
            kind = msg["type"]
            if kind == "turn" and resumed_at is None and msg["turn"] in script.get("save_on_turn", []):
                await ws.send(json.dumps({"type": "checkpoint"}))
            elif kind == "paused":
                turn, reason = msg["turn"], msg["reason"]
                out["pauses"].append([turn, reason])
                civ = msg["civs"][0]
                actions = script.get("at_pause", {}).get(turn, []) if reason == "pause_interval" else []
                for action in actions:
                    if action[0] == "checkpoint":
                        if resumed_at is not None:
                            continue  # the uninterrupted session's own saves
                        await ws.send(json.dumps({"type": "checkpoint"}))
                        await until(ws, {"checkpoint_saved", "checkpoint_error"})
                    elif action[0] == "set":
                        await ws.send(json.dumps({"type": "set", "civ": civ, "stat": action[1],
                                                  "value": action[2]}))
                        await until(ws, {"ack", "error"})
                    else:
                        await ws.send(json.dumps({"type": "inject", "event_type": action[1],
                                                  "civ": civ}))
                        await until(ws, {"ack", "error"})
                if turn == turns:
                    # A viewer connecting now: the server's own reconnect data,
                    # then the pause it is in.
                    await ws.close()
                    ws, first = await connect()
                    out["reconnect_view"] = _sha(json.dumps(first))
                    out["reconnect_matches_view"] = json.dumps(first) == json.dumps(state["view"])
                    again = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT))
                    assert again["type"] == "paused" and again["turn"] == turn, again
                await ws.send(json.dumps({"type": "continue"}))
            elif kind == "completed":
                break
    finally:
        await ws.close()
    return out


def _live_session(cmd: list[str], log: Path, env: dict, start: dict | None, turns: int,
                  script: dict, resumed_at: int | None) -> dict:
    import asyncio
    t0 = time.monotonic()
    process = _LiveProcess(cmd, log, env)
    try:
        seen = asyncio.run(_drive(process.ws_url(), start, turns, script, resumed_at))
    except Exception as exc:
        process.proc.kill()  # this process only (its PID)
        seen = {"exception": repr(exc)}
    seen["exit"] = process.finish()
    seen["seconds"] = round(time.monotonic() - t0, 2)
    return seen


def _view_differences(straight: dict, resumed: dict, k: int) -> list[str]:
    out = []
    for turn, sha in resumed["views"].items():
        if straight["views"].get(turn) != sha:
            out.append(f"view after turn {turn}")
    if sorted(map(int, resumed["views"])) != list(range(k + 1, len(straight["views"]) + 1)):
        out.append(f"turn messages {sorted(map(int, resumed['views']))}")
    if resumed.get("connect_view") != straight["views"].get(str(k)):
        out.append(f"connect view at turn {k}")
    for key in ("reconnect_view", "final_view"):
        if resumed.get(key) != straight.get(key):
            out.append(key)
    if not resumed.get("reconnect_matches_view"):
        out.append("the reconnect view is not the accumulated view")
    return out


def run_live_case(out: Path, name: str, ks: list[int] | None, jobs: int, extra: list[str],
                  keep: bool, resume_hash_seed: str) -> dict:
    cli, start, turns, pause_every, script = LIVE_CASES[name]
    cli = [*cli, *extra]
    case = out / name
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    ks = sorted({k for k in (ks if ks is not None else range(1, turns)) if 0 < k < turns})
    report: dict = {"case": name, "cli": cli, "start": start, "turns": turns,
                    "pause_every": pause_every, "script": script, "ks": ks, "results": {}}
    plain, straight = case / "plain", case / "straight"
    plain.mkdir()
    straight.mkdir()
    ckpt = straight / "ckpt"

    def live_cmd(directory: Path, *more: str) -> list[str]:
        return [sys.executable, "-u", "-m", "chronicler.main", "--live", "--live-port", "0",
                *more, "--output", str(directory / "chronicle.md"),
                "--state", str(directory / "state.json")]

    fresh = [*cli, "--simulate-only", "--pause-every", str(pause_every)]
    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        f_plain = pool.submit(_live_session, live_cmd(plain, *fresh), case / "plain.log", _env(),
                              start, turns, {"at_pause": {
                                  t: [a for a in acts if a[0] != "checkpoint"]
                                  for t, acts in script.get("at_pause", {}).items()}}, None)
        f_straight = pool.submit(
            _live_session, live_cmd(straight, *fresh, "--checkpoint-every", "1", "--checkpoint",
                                    str(ckpt / "turn_{turn:04d}.ckpt")),
            case / "straight.log", _env(), start, turns, script, None)
        seen_plain, seen_straight = f_plain.result(), f_straight.result()
    report["plain"] = seen_plain
    report["straight"] = seen_straight
    if seen_plain["exit"] or seen_straight["exit"] or "exception" in seen_plain \
            or "exception" in seen_straight:
        report["error"] = "a straight session failed"
        (case / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    from cities_identity import compare as compare_dirs
    checked, problems = compare_dirs(plain, straight)
    problems = [p for p in problems if not p.startswith(("only in new: ckpt/",
                                                        "only in new: live_checkpoints/"))]
    view_problems = [key for key in ("views", "reconnect_view", "final_view")
                     if seen_plain.get(key) != seen_straight.get(key)]
    report["saving_changes_nothing"] = {"files": checked, "differences": problems,
                                        "view_differences": view_problems}
    print(f"{name}: plain vs straight (saves {[s['turn'] for s in seen_straight['saves']]}): "
          f"{checked} files, {len(problems)} differences, views "
          f"{'equal' if not view_problems else view_problems}", flush=True)

    points = [(k, ckpt / f"turn_{k:04d}.ckpt", f"resume_{k:04d}") for k in ks]
    points += [(s["turn"], Path(s["path"]), f"resume_live_{s['turn']:04d}")
               for s in seen_straight["saves"]]
    resume_script = {"at_pause": script.get("at_pause", {})}

    def resume(point) -> tuple[str, dict]:
        k, path, label = point
        rdir = case / label
        rdir.mkdir()
        # Interventions of pauses after k are repeated; the checkpoint holds
        # those of turn k and before.
        later = {"at_pause": {t: a for t, a in resume_script["at_pause"].items() if t > k}}
        seen = _live_session(live_cmd(rdir, "--resume", str(path)), case / f"{label}.log",
                             _env(resume_hash_seed), None, turns, later, k)
        result = {"exit": seen["exit"], "seconds": seen["seconds"], "turn": k,
                  "pauses": seen.get("pauses"), "errors": seen.get("errors")}
        if seen["exit"] == 0 and "exception" not in seen:
            n, diffs = _compare_resume(straight, rdir, k)
            diffs = [d for d in diffs if not d.startswith("only in base: live_checkpoints/")]
            result.update(files=n, differences=diffs,
                          view_differences=_view_differences(seen_straight, seen, k))
            if not diffs and not result["view_differences"] and not keep:
                shutil.rmtree(rdir)
                (case / f"{label}.log").unlink()
        else:
            result["exception"] = seen.get("exception")
        return label, result

    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        for label, result in pool.map(resume, points):
            report["results"][label] = result
            if result["exit"] or "files" not in result:
                status = f"FAIL exit {result['exit']} {result.get('exception') or ''}"
            else:
                status = (f"{result['files']} files, {len(result['differences'])} differences, "
                          f"views {'equal' if not result['view_differences'] else result['view_differences']}")
            print(f"{name}: {label} (turn {result['turn']}): {status}", flush=True)
            for line in result.get("differences", [])[:10]:
                print(f"    {line}", flush=True)
    passed = (not problems and not view_problems
              and all(r["exit"] == 0 and "files" in r and not r["differences"]
                      and not r["view_differences"] for r in report["results"].values()))
    report["pass"] = passed
    if passed and not keep:
        shutil.rmtree(ckpt)
        shutil.rmtree(plain)
        shutil.rmtree(straight / "live_checkpoints", ignore_errors=True)
    (case / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({len(points)} resume points)", flush=True)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--case", action="append", choices=sorted(CASES) + sorted(LIVE_CASES),
                   required=True)
    r.add_argument("--ks", type=str, default=None, help="comma-separated resume turns (default: all)")
    r.add_argument("--jobs", type=int, default=1, choices=(1, 2))
    r.add_argument("--keep", action="store_true")
    r.add_argument("--resume-hash-seed", default="0")
    r.add_argument("--cli-arg", action="append", default=[])
    sub.add_parser("cases")
    a = p.parse_args(argv)
    if a.cmd == "cases":
        for name, (cli, turns, target, kind) in CASES.items():
            print(f"{name}: {turns} turns{f', {target} agents' if target else ''}, resume at "
                  f"{_default_ks(turns, kind)}: {' '.join(cli)}")
        for name, (cli, start, turns, pause_every, script) in LIVE_CASES.items():
            print(f"{name}: live, {turns} turns, pause every {pause_every}, start {start}, "
                  f"resume at 1..{turns - 1} and each viewer checkpoint, script {script}: "
                  f"{' '.join(cli)}")
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    ks = [int(x) for x in a.ks.split(",")] if a.ks else None
    status = 0
    for name in a.case:
        runner = run_live_case if name in LIVE_CASES else run_case
        report = runner(a.out.resolve(), name, ks, a.jobs, a.cli_arg, a.keep, a.resume_hash_seed)
        status |= not report.get("pass", False)
    return status


if __name__ == "__main__":
    sys.exit(main())
