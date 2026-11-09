"""Frozen screen evidence and the one screen runner's state files.

``scripts/productive_recovery_screens.py`` and ``scripts/livelihoods_screens.py`` are
frozen preregistration evidence: their held runs and reports were made by these
exact bytes, so they are pinned here by SHA-256. Do not edit them, and never update
a digest below to make a change pass: a new screen is a new file that declares
``screen_runner.Screen`` entries (see ``docs/integration/connected-world-screens.md``).

The second part writes, by hand, the run-directory files ``scripts/screen_runner.py``
writes (``source.txt``, ``metrics.jsonl``, ``derived.jsonl``) into a temporary folder
and checks that the runner's readers parse them: the report, the identity lines a
resume and a pilot comparison use, and a resume that repeats nothing. Offline: no
simulation, no child process, nothing written under ``output/``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Frozen preregistration evidence (a change needs a new file instead).
FROZEN = {
    "scripts/productive_recovery_screens.py": "f326285c9eb3429ae56bd6e6206c2354bc4cbcca77758eb583a90f6231fd46d3",
    "scripts/livelihoods_screens.py": "ff49d0bd10813152200ca0b30ff0feb60f97383d46f57f795b4953892b5d9d7c",
}


@pytest.mark.parametrize("path, digest", sorted(FROZEN.items()))
def test_frozen_screen_scripts_are_unchanged(path, digest):
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    assert actual == digest, (
        f"{path} is frozen preregistration evidence; write a new screen file that declares "
        f"screen_runner.Screen entries instead of editing it (never update this digest)")


# --- The runner's state files ------------------------------------------------------------

@pytest.fixture(scope="module")
def CW():
    path = ROOT / "scripts" / "connected_world_screens.py"
    spec = importlib.util.spec_from_file_location("connected_world_screens_frozen_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def SR(CW):
    return CW.SR


WORLDS = (("t", 1), ("p", 7))


def _identity(SR, screen):
    """Identity lines in the runner's own format (fixed revision, real file hashes)."""
    return SR.identity_lines("abc123", 0, "/repo/src/chronicler/__init__.py", "none", screen)


def _write_run(SR, screen, out: Path, identity, cohort="dev"):
    """The files a finished development run leaves (layout of ``run_main``)."""
    out.mkdir(parents=True)
    digest = SR.identity_digest(identity)
    (out / "source.txt").write_text(
        "\n".join(identity) + "\n"
        f"run: screen {screen.name}; cohort {cohort}; seeds all; arms W,TS; jobs 1; worlds t1,p7; turns 5; "
        "rows already written 0\nstarted 2026-11-08T00:00:00Z\n"
        "derived plan t1 (from arm W): sha256 " + "0" * 64 + " derived/plan-t1.json\n"
        "finished 2026-11-08T00:01:00Z: 4 runs, 4 failed, 6 s of simulation and extraction "
        "(0.002 core-hours in all), 6.0 s wall\n", encoding="utf-8")
    rows = []
    for tag, seed in WORLDS:
        for arm in screen.arms:
            row = {"screen": screen.name, "cohort": cohort, "arm": arm, "stratum": tag, "seed": seed,
                   "rc": 1, "wall_s": 1.0, "extract_s": 0.5, "identity": digest, "error": "constructed"}
            if arm == "W" and tag == "t":
                row["derived"] = {"plan": {"path": "derived/plan-t1.json", "sha256": "0" * 64, "info": None}}
            rows.append(row)
    (out / "metrics.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out / "derived.jsonl").write_text(json.dumps(
        {"name": "plan", "arm": "W", "stratum": "t", "seed": 1, "path": "derived/plan-t1.json",
         "sha256": "0" * 64, "info": None, "recorded": "2026-11-08T00:00:30Z"}) + "\n", encoding="utf-8")
    return rows


def test_source_txt_identity_and_run_header_are_read_back(SR, CW, tmp_path):
    screen = CW.SCREENS["DEV"]
    identity = _identity(SR, screen)
    assert [line.split(" ", 1)[0] for line in identity] == [
        "source", "dirty", "dirty-code", "chronicler", "native", "interpreter", "runner", "screens", "registry",
        "registry-content"]
    assert SR._field(identity, "runner").split(" ")[0] == SR.sha256_file(SR.RUNNER)
    out = tmp_path / "run"
    rows = _write_run(SR, screen, out, identity)
    text = (out / "source.txt").read_text(encoding="utf-8")
    assert SR.identity_of(text) == identity
    assert SR.recorded_run(text) == ("DEV", "dev")
    assert SR.identity_key(SR.identity_of(text)) == [line for line in identity if not line.startswith("registry ")]
    assert SR.read_rows(out / "metrics.jsonl", screen) == rows
    assert {r["identity"] for r in rows} == {SR.identity_digest(SR.identity_of(text))}
    derived = [json.loads(line) for line in (out / "derived.jsonl").read_text(encoding="utf-8").splitlines()]
    made = {(n, r["stratum"], r["seed"]): rec["sha256"] for r in rows for n, rec in (r.get("derived") or {}).items()}
    assert {(d["name"], d["stratum"], d["seed"]): d["sha256"] for d in derived} == made


def test_report_reads_the_metrics_file(SR, CW, tmp_path, capsys):
    screen = CW.SCREENS["DEV"]
    out = tmp_path / "run"
    _write_run(SR, screen, out, _identity(SR, screen))
    assert SR.report_main([str(out / "metrics.jsonl"), "--screen", "DEV"], CW.SCREENS) == 0
    text = capsys.readouterr().out
    assert "- FAILED W t1 (rc 1)" in text and "- FAILED TS p7 (rc 1)" in text


def test_a_resume_reads_the_files_and_repeats_nothing(SR, CW, tmp_path):
    screen = CW.SCREENS["DEV"]
    identity = _identity(SR, screen)
    out = tmp_path / "run"
    _write_run(SR, screen, out, identity)

    def simulate(cmd):
        raise AssertionError(f"a resume of a complete run simulated {cmd}")

    rt = SR.Runtime(simulate=simulate, identity=lambda s: list(identity), clock=lambda: 0.0,
                    ledger=tmp_path / "ledger.jsonl", changed_paths=lambda old, new: [])
    argv = [str(out), "--screen", "DEV", "--cohort", "dev", "--worlds", "t1,p7", "--turns", "5", "--jobs", "1",
            "--resume"]
    assert SR.run_main(argv, CW.SCREENS, rt) == 0
    text = (out / "source.txt").read_text(encoding="utf-8")
    assert "resumed: screen DEV; cohort dev;" in text and "rows already written 4" in text
    assert SR.identity_of(text) == identity
    assert not (tmp_path / "ledger.jsonl").exists()
    # Another runner digest is another identity: the resume is refused.
    other = [f"runner {'f' * 64} scripts/screen_runner.py" if line.startswith("runner ") else line
             for line in identity]
    moved = SR.Runtime(simulate=simulate, identity=lambda s: list(other), clock=lambda: 0.0,
                       ledger=tmp_path / "ledger.jsonl", changed_paths=lambda old, new: [])
    with pytest.raises(SystemExit, match="resume refused"):
        SR.run_main(argv, CW.SCREENS, moved)


def test_a_pilot_of_another_runner_digest_is_refused(SR, CW, tmp_path):
    """Pilot and held compare the ``runner`` line: editing screen_runner.py between them
    invalidates the pilot."""
    screen = CW.SCREENS["DEV"]
    identity = _identity(SR, screen)
    out = tmp_path / "pilot"
    _write_run(SR, screen, out, identity, cohort="pilot")
    rt = types.SimpleNamespace(changed_paths=lambda old, new: [])
    rows, problems = SR.load_pilot(out / "metrics.jsonl", screen, identity, rt)
    assert len(rows) == 4 and problems == []
    other = [f"runner {'f' * 64} scripts/screen_runner.py" if line.startswith("runner ") else line
             for line in identity]
    _rows, problems = SR.load_pilot(out / "metrics.jsonl", screen, other, rt)
    assert len(problems) == 1 and problems[0].startswith("pilot refused: runner ")
