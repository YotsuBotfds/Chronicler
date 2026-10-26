"""Batch directories and their manifests (docs/integration/validation-integrity.md)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pytest

from chronicler.batch import run_batch
from chronicler.batch_manifest import (
    MANIFEST_FILENAME,
    NON_SIMULATION_ARG_KEYS,
    OUTPUT_ARG_KEYS,
    SIMULATION_ARG_KEYS,
    THREAD_ENV_VARS,
    BatchDestinationError,
    _resolve_git_head,
    file_sha256,
    load_batch_manifest,
    native_identity,
    source_identity,
)
from chronicler.validation_io import ValidationRequestError, check_batch_manifest, load_seed_runs


def _args(out: Path, seed, batch: int, **extra) -> argparse.Namespace:
    values = dict(
        seed=seed, turns=3, civs=2, regions=4, output=str(out / "chronicle.md"), state=str(out / "state.json"),
        resume=None, reflection_interval=10, local_url="http://localhost:1234/v1", sim_model=None,
        narrative_model=None, llm_actions=False, scenario=None, batch=batch, fork=None, interactive=False,
        parallel=None, pause_every=None, tuning=None, simulate_only=True, seed_range=None, agents="off",
    )
    values.update(extra)
    return argparse.Namespace(**values)


@pytest.fixture(scope="module")
def batch_42(tmp_path_factory):
    """Seeds 42-44, three turns, written once for the module."""
    out = tmp_path_factory.mktemp("batch")
    return run_batch(_args(out, 42, 3))


def _copy(batch_dir: Path, tmp_path: Path) -> Path:
    target = tmp_path / batch_dir.name
    shutil.copytree(batch_dir, target)
    return target


def _rewrite_manifest(batch_dir: Path, change) -> None:
    path = batch_dir / MANIFEST_FILENAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


# --- Reused destinations (the external review's reproduction) ----------


def test_a_second_batch_into_a_used_directory_is_refused(tmp_path):
    first = run_batch(_args(tmp_path, 42, 3))
    with pytest.raises(BatchDestinationError, match="is not empty"):
        run_batch(_args(tmp_path, 42, 1))
    # The first batch is untouched and validates as itself.
    assert sorted(run["seed"] for run in load_seed_runs(first)) == [42, 43, 44]
    assert check_batch_manifest(first)["seeds"] == [42, 43, 44]


def test_the_parallel_narration_guard_claims_no_directory(tmp_path):
    with pytest.raises(ValueError, match="--batch --parallel requires --simulate-only"):
        run_batch(_args(tmp_path, 42, 2, parallel=2, simulate_only=False))
    assert not (tmp_path / "batch_42").exists()


def test_a_batch_claims_its_directory_first(tmp_path):
    from chronicler.batch_manifest import prepare_batch_dir

    batch_dir = tmp_path / "batch_5"
    prepare_batch_dir(batch_dir)
    assert (batch_dir / MANIFEST_FILENAME).read_text() == ""
    with pytest.raises(BatchDestinationError):
        prepare_batch_dir(batch_dir)
    # A claim that never became a manifest is an error, not a legacy directory.
    with pytest.raises(ValidationRequestError, match="is empty: the batch claimed the directory and stopped"):
        check_batch_manifest(batch_dir, legacy_batch=True)


def test_an_empty_existing_directory_is_accepted(tmp_path):
    (tmp_path / "batch_7").mkdir()
    batch_dir = run_batch(_args(tmp_path, 7, 1))
    assert load_batch_manifest(batch_dir)["status"] == "complete"


def test_the_cli_reports_a_used_batch_directory(tmp_path, monkeypatch, capsys):
    from chronicler import main as cli

    argv = ["chronicler", "--seed-range", "5-5", "--turns", "2", "--civs", "2", "--regions", "4",
            "--simulate-only", "--output", str(tmp_path / "chronicle.md")]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    capsys.readouterr()
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    assert "is not empty" in capsys.readouterr().err


# --- Seed 0 --------------------------------------------------------------


def test_seed_zero_is_a_seed(tmp_path):
    batch_dir = run_batch(_args(tmp_path, 0, 2))
    assert batch_dir.name == "batch_0"
    assert sorted(path.name for path in batch_dir.iterdir() if path.is_dir()) == ["seed_0", "seed_1"]
    assert [run["seed"] for run in load_seed_runs(batch_dir)] == [0, 1]
    assert load_batch_manifest(batch_dir)["seeds"] == [0, 1]
    # No seed given: 42, as before.
    assert run_batch(_args(tmp_path / "default", None, 1)).name == "batch_42"


# --- Manifest contents ---------------------------------------------------


def test_the_manifest_records_the_cohort_and_identity(batch_42):
    manifest = load_batch_manifest(batch_42)
    assert (manifest["kind"], manifest["schema_version"], manifest["status"]) == ("chronicler-batch", 1, "complete")
    assert manifest["seeds"] == [42, 43, 44] and manifest["turns"] == 3
    simulation = manifest["simulation"]
    assert set(simulation) == set(SIMULATION_ARG_KEYS) | {"tuning_overrides"}
    assert (simulation["civs"], simulation["regions"], simulation["agents"], simulation["cities"]) == (2, 4, "off", None)
    assert manifest["outputs"]["simulate_only"] is True
    environment = manifest["environment"]
    assert set(environment["thread_env"]) == set(THREAD_ENV_VARS)
    assert environment["python"] == ".".join(map(str, sys.version_info[:3]))
    assert {"numpy", "pyarrow", "pydantic"} <= set(environment["packages"])
    assert len(manifest["source"]["package_digest"]) == 64
    assert manifest["native"]["status"] in ("found", "absent")
    for run, seed in zip(manifest["runs"], (42, 43, 44)):
        assert run["seed"] == seed and run["dir"] == f"seed_{seed}" and run["total_turns"] == 3
        assert run["bundle"] == f"seed_{seed}/chronicle_bundle.json"
        assert run["bundle"] in run["files"]
        for relative, sha in run["files"].items():
            assert file_sha256(batch_42 / relative) == sha
        # Outputs the validator does not read are not hashed (they may be pruned).
        assert f"seed_{seed}/state.json" not in run["files"]


def test_tuning_overrides_are_part_of_the_simulation(tmp_path):
    batch_dir = run_batch(_args(tmp_path, 3, 1), tuning_overrides_dict={"stability.drain.drought_immediate": 1.0})
    simulation = load_batch_manifest(batch_dir)["simulation"]
    assert simulation["tuning_overrides"] == {"stability.drain.drought_immediate": 1.0}


def test_every_cli_argument_is_classified():
    from chronicler.main import _build_parser

    destinations = {action.dest for action in _build_parser()._actions if action.dest != "help"}
    groups = [set(SIMULATION_ARG_KEYS), set(OUTPUT_ARG_KEYS), set(NON_SIMULATION_ARG_KEYS)]
    assert sum(len(group) for group in groups) == len(set().union(*groups)), "an argument is in two groups"
    assert destinations == set().union(*groups), "classify new arguments in chronicler.batch_manifest"


def test_a_cancelled_batch_is_marked_cancelled(tmp_path):
    import threading

    cancel = threading.Event()
    done = []

    def progress(completed, total, seed):
        done.append(seed)
        cancel.set()

    batch_dir = run_batch(_args(tmp_path, 9, 3), progress_cb=progress, cancel_event=cancel)
    manifest = load_batch_manifest(batch_dir)
    assert manifest["status"] == "cancelled" and done == [9]
    with pytest.raises(ValidationRequestError, match="'cancelled'"):
        check_batch_manifest(batch_dir)


# --- Validation consumes the manifest ------------------------------------


def test_a_verified_batch_reports_its_cohort(batch_42):
    entry = check_batch_manifest(batch_42)
    assert entry["status"] == "verified"
    assert (entry["seeds"], entry["turns"]) == ([42, 43, 44], 3)
    assert entry["manifest_sha256"] == file_sha256(batch_42 / MANIFEST_FILENAME)
    assert entry["simulation"]["agents"] == "off"


def test_a_bundle_not_in_the_manifest_is_refused(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    shutil.copytree(batch_dir / "seed_43", batch_dir / "seed_99")
    with pytest.raises(ValidationRequestError, match=r"1 bundle\(s\) not in the manifest: seed_99/chronicle_bundle.json"):
        check_batch_manifest(batch_dir)


def test_a_missing_seed_is_refused(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    shutil.rmtree(batch_dir / "seed_44")
    with pytest.raises(ValidationRequestError, match=r"have no bundle: seed 44 \(seed_44\)"):
        check_batch_manifest(batch_dir)


def test_a_changed_validation_input_is_refused(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    bundle = batch_dir / "seed_42" / "chronicle_bundle.json"
    bundle.write_text(bundle.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValidationRequestError, match=r"seed_42/chronicle_bundle.json \(changed\)"):
        check_batch_manifest(batch_dir)
    # Pruned outputs the validator does not read are fine.
    batch_dir = _copy(batch_42, tmp_path / "pruned")
    (batch_dir / "seed_42" / "state.json").unlink()
    assert check_batch_manifest(batch_dir)["status"] == "verified"


def test_a_run_shorter_than_requested_is_refused(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    _rewrite_manifest(batch_dir, lambda manifest: manifest.update(turns=500))
    with pytest.raises(ValidationRequestError, match=r"shorter than the requested 500 turns: seed 42 \(seed_42\) ran 3"):
        check_batch_manifest(batch_dir)


def test_an_unfinished_batch_is_refused(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    _rewrite_manifest(batch_dir, lambda manifest: manifest.update(status="running"))
    with pytest.raises(ValidationRequestError, match="batch status is 'running'"):
        check_batch_manifest(batch_dir)


def test_a_directory_without_a_manifest_needs_the_legacy_flag(batch_42, tmp_path):
    from chronicler.validate import main, run_oracles

    batch_dir = _copy(batch_42, tmp_path)
    (batch_dir / MANIFEST_FILENAME).unlink()
    with pytest.raises(ValidationRequestError, match="pass --legacy-batch"):
        run_oracles(batch_dir, ["artifacts"])
    report = run_oracles(batch_dir, ["artifacts"], legacy_batch=True)
    assert report["batch_manifest"]["status"] == "unchecked"
    # A single bundle has no manifest either.
    with pytest.raises(ValidationRequestError, match="pass --legacy-batch"):
        check_batch_manifest(batch_dir / "seed_42" / "chronicle_bundle.json")
    assert main(["--batch-dir", str(batch_dir), "--oracles", "artifacts"]) == 1
    assert main(["--batch-dir", str(batch_dir), "--oracles", "artifacts", "--legacy-batch"]) == 0


def test_the_legacy_flag_still_checks_a_present_manifest(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    shutil.rmtree(batch_dir / "seed_43")
    with pytest.raises(ValidationRequestError, match="have no bundle"):
        check_batch_manifest(batch_dir, legacy_batch=True)


def test_reports_carry_the_verified_cohort_and_profile(batch_42, capsys):
    from chronicler.validate import main

    assert main(["--batch-dir", str(batch_42), "--oracles", "artifacts", "--profile", "subset"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["batch_manifest"]["status"] == "verified"
    assert report["batch_manifest"]["seeds"] == [42, 43, 44]
    assert report["profile"] == "subset"


def test_a_malformed_manifest_is_an_error(batch_42, tmp_path):
    batch_dir = _copy(batch_42, tmp_path)
    (batch_dir / MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationRequestError, match="not a Chronicler batch manifest"):
        check_batch_manifest(batch_dir)


# --- Source and native identity without child processes ------------------


def test_git_head_is_read_from_the_git_files(tmp_path):
    sha = "a" * 40
    git = tmp_path / "repo" / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text(sha + "\n", encoding="utf-8")
    assert _resolve_git_head(git) == (sha, "refs/heads/main")
    # Packed refs.
    (git / "refs" / "heads" / "main").unlink()
    (git / "packed-refs").write_text(f"# pack-refs with: peeled\n{'b' * 40} refs/heads/main\n", encoding="utf-8")
    assert _resolve_git_head(git) == ("b" * 40, "refs/heads/main")
    # A worktree: its own HEAD, refs in the common directory.
    worktree = git / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    (worktree / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (worktree / "commondir").write_text("../..\n", encoding="utf-8")
    assert _resolve_git_head(worktree) == ("b" * 40, "refs/heads/main")
    # Detached.
    (git / "HEAD").write_text("c" * 40 + "\n", encoding="utf-8")
    assert _resolve_git_head(git) == ("c" * 40, None)


def test_source_identity_names_this_checkout():
    identity = source_identity()
    assert Path(identity["package_dir"]).name == "chronicler"
    assert identity["git_sha"] is None or len(identity["git_sha"]) == 40


def test_native_identity_finds_the_extension_without_importing_it(tmp_path, monkeypatch):
    import importlib.machinery

    package = tmp_path / "chronicler_agents"
    package.mkdir()
    extension = package / f"chronicler_agents{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    extension.write_bytes(b"not a real extension")
    monkeypatch.delitem(sys.modules, "chronicler_agents.chronicler_agents", raising=False)
    monkeypatch.setattr(sys, "path", [str(tmp_path)])
    identity = native_identity()
    assert identity["status"] == "found" and identity["source"] == "import_path"
    assert identity["sha256"] == file_sha256(extension)
    assert "chronicler_agents.chronicler_agents" not in sys.modules
    monkeypatch.setattr(sys, "path", [str(tmp_path / "elsewhere")])
    assert native_identity() == {"status": "absent"}
