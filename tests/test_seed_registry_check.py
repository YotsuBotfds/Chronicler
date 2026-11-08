"""scripts/check_seed_registry.py: gate seeds against the registry, restricted reuse.

Reads files only (no child process, network or native import).
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_seed_registry.py"
RUNNER = ROOT / "scripts" / "m53b_run_validation.py"

# Run entries recorded before the check existed whose seeds intersect a restricted
# range and whose use does not say "development". They are history, kept as is;
# a new entry of this kind must be labelled development or not reuse the range.
REUSE_ALLOWLIST = (
    "ls1-held-t", "crisis-held-t", "shortfall-scaffold-t", "holdout-t", "holdout-p",
    "claims-sham-t", "claims-sham-p", "mutual-aid-gate-t", "previews-t", "identity-t",
    "identity-p", "example-worlds-t", "m-af1-t", "m53-probes-t",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def CSR():
    return _load(SCRIPT, "check_seed_registry")


@pytest.fixture(scope="module")
def registry(CSR):
    return CSR.load_registry()


@pytest.mark.parametrize("stratum,count", (("template", 200), ("procedural", 100)))
def test_full_gate_seeds_match_their_gate_entry(CSR, registry, stratum, count):
    assert CSR.check("full", CSR.profile_seeds(42, count), stratum, registry) == []


@pytest.mark.parametrize("seeds", (range(42, 241), range(43, 243), range(1, 201), [42, 44]))
def test_full_profile_refuses_any_other_range(CSR, registry, seeds):
    problems = CSR.check("full", seeds, "template", registry)
    assert len(problems) == 1 and "match no restricted_gate entry" in problems[0]
    assert "gate200-t (42-241)" in problems[0]


def test_full_profile_does_not_accept_the_subset_gate_entry(CSR, registry):
    # gate200-subset-t (42-61) is a restricted_gate entry, but not the gate range.
    assert CSR.check("full", range(42, 62), "template", registry)
    assert CSR.check("subset", range(42, 62), "template", registry) == []
    assert CSR.check("subset", range(42, 62), "procedural", registry) == []
    assert CSR.check("subset", range(42, 242), "template", registry) == []
    assert CSR.check("subset", range(500, 520), "template", registry)


def test_full_profile_without_a_gate_entry_is_a_problem(CSR, registry):
    broken = copy.deepcopy(registry)
    broken["entries"] = [e for e in broken["entries"] if e["id"] != "gate200-t"]
    assert CSR.check("full", range(42, 242), "template", broken) == [
        "template: no restricted_gate entry has the gate range [[42, 241]]"]
    assert CSR.check("full", range(42, 242), "elsewhere", registry)


def test_restricted_reuse_offenders_are_the_recorded_allowlist(CSR, registry):
    offenders = [o["id"] for o in CSR.reuse_offenders(registry)]
    assert offenders == list(REUSE_ALLOWLIST)
    assert len(CSR.reuse_warnings(registry)) == len(REUSE_ALLOWLIST)


def test_a_new_restricted_reuse_is_reported_unless_development(CSR, registry):
    grown = copy.deepcopy(registry)
    entry = {"id": "new-run-t", "source": "x", "use": "a new held run", "stratum": "template",
             "world": "template 8x4", "seeds": [[50, 52]], "turns": [100], "status": "run"}
    grown["entries"].append(entry)
    assert CSR.reuse_offenders(grown)[-1] == {"id": "new-run-t", "stratum": "template", "restricted_seeds": 3}
    entry["use"] = "development probe"
    assert [o["id"] for o in CSR.reuse_offenders(grown)] == list(REUSE_ALLOWLIST)
    entry.update(use="holdout probe", seeds=[1500], stratum="procedural")
    assert CSR.reuse_offenders(grown)[-1]["id"] == "new-run-t"
    entry.update(seeds=[300])          # outside every procedural restricted range
    assert [o["id"] for o in CSR.reuse_offenders(grown)] == list(REUSE_ALLOWLIST)


def test_cli_exit_codes(CSR, capsys):
    assert CSR.main([]) == 0
    assert CSR.main(["--profile", "full"]) == 0
    assert CSR.main(["--profile", "full", "--worldgen", "procedural"]) == 0
    assert CSR.main(["--profile", "full", "--seeds", "20"]) == 1
    assert CSR.main(["--profile", "subset", "--seeds", "7"]) == 0
    out = capsys.readouterr().out
    assert "error: profile full template seeds 42-61" in out
    assert "warning: profile subset template seeds 42-48" in out


def test_m53b_refuses_a_full_run_off_the_gate_range_before_running(monkeypatch, tmp_path, capsys):
    runner = _load(RUNNER, "m53b_run_validation")

    def forbidden(*args, **kwargs):
        raise AssertionError("a full run off the gate range must be refused before simulation")

    for name in ("run_subset", "run_full", "run_determinism", "run_arms", "validate_batch", "_run"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.sys, "argv", [
        "m53b_run_validation.py", "--profile", "full", "--seeds", "20", "--parallel", "1",
        "--output-root", str(tmp_path / "runs")])
    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2
    assert "seed registry: profile full template seeds 42-61" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_m53b_registry_check_accepts_the_gate_and_warns_on_a_subset(tmp_path, capsys):
    runner = _load(RUNNER, "m53b_run_validation")
    ns = runner.argparse.Namespace
    full = runner.apply_profile_defaults(ns(profile="full", seeds=None, turns=None, worldgen="template",
                                             regions=None, civs=None, seed_start=42))
    assert runner.registry_seed_problems(full) == []
    proc = runner.apply_profile_defaults(ns(profile="full", seeds=None, turns=None, worldgen="procedural",
                                             regions=None, civs=None, seed_start=42))
    assert runner.registry_seed_problems(proc) == []
    odd = runner.apply_profile_defaults(ns(profile="subset", seeds=4, turns=100, worldgen="template",
                                            regions=None, civs=None, seed_start=42))
    assert runner.registry_seed_problems(odd)


def test_m53b_hash_seed_defaults_to_the_gate_value():
    runner = _load(RUNNER, "m53b_run_validation")
    assert runner._build_env()["PYTHONHASHSEED"] == "0"
    assert runner._build_env("random")["PYTHONHASHSEED"] == "random"
    for good in ("0", "1", "4294967295", "random"):
        assert runner._hash_seed(good) == good
    for bad in ("-1", "01", "4294967296", "x", ""):
        with pytest.raises(runner.argparse.ArgumentTypeError):
            runner._hash_seed(bad)
