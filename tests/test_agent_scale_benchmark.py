"""Benchmark input failures must happen before any simulation or file creation."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def benchmark():
    source = Path(__file__).resolve().parents[1] / "scripts/agent_scale_benchmark.py"
    spec = importlib.util.spec_from_file_location("scale_benchmark_contracts", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("option,value", [
    ("--turns", "0"), ("--turns", "-1"),
    ("--repeats", "0"), ("--repeats", "-1"),
    ("--jobs", "0"), ("--jobs", "-1"),
    ("--regions", "0"), ("--civs", "0"),
    ("--warmup", "-1"), ("--target", "-1"),
    ("--capacity-mult", "0"), ("--capacity-mult", "-1"),
    ("--capacity-mult", "nan"), ("--capacity-mult", "inf"),
    ("--timeout", "0"), ("--timeout", "-1"),
    ("--timeout", "nan"), ("--timeout", "inf"),
    ("--targets", ""), ("--targets", "1,"),
    ("--targets", "1,,2"), ("--targets", "-1"),
    ("--targets", "3,03"), ("--targets", "many"),
    ("--seeds", ""), ("--seeds", "1,"),
    ("--seeds", "1,,2"), ("--seeds", "1,01"),
])
def test_invalid_jobs_refuse_before_output_or_process_creation(benchmark, tmp_path, monkeypatch, option, value):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid benchmark inputs reached filesystem or child launch")
    monkeypatch.setattr(benchmark.subprocess, "Popen", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    with pytest.raises(SystemExit) as caught:
        benchmark.main(["--run-root", str(tmp_path / "runs"), f"{option}={value}"])
    assert caught.value.code == 2


def test_zero_target_and_zero_warmup_remain_valid(benchmark):
    opts = benchmark._parse(["--targets", "0,2000", "--warmup", "0", "--seeds=-2,42"])
    assert opts.targets == [0, 2000]
    assert opts.seeds == [-2, 42]
    assert opts.warmup == 0
    assert opts.capacity_mult == 1.0
    assert benchmark._parse([]).targets == [1000, 5000, 20000, 50000, 100000]


def test_repeated_profiles_have_unique_destinations_and_same_simulation_arguments(benchmark, tmp_path):
    opts = benchmark._parse(["--profile-dir", str(tmp_path), "--targets", "1000,2000",
                             "--seeds", "42,43", "--repeats", "3"])
    destinations = set()
    for target in opts.targets:
        for seed in opts.seeds:
            unprofiled = None
            for repeat in range(opts.repeats):
                command = benchmark._child_cmd(opts, target, seed, repeat)
                index = command.index("--profile-out")
                destination = Path(command[index + 1])
                assert destination.parent == tmp_path
                assert destination not in destinations
                destinations.add(destination)
                same_arguments = command[:index] + command[index + 2:]
                if unprofiled is None:
                    unprofiled = same_arguments
                assert same_arguments == unprofiled
    assert len(destinations) == 12


def test_unprofiled_child_command_retains_its_old_arguments(benchmark):
    opts = benchmark._parse(["--turns", "7", "--warmup", "2", "--cli-arg=--cities"])
    assert benchmark._child_cmd(opts, 1000, 42, 0) == benchmark._child_cmd(opts, 1000, 42, 3)
    command = benchmark._child_cmd(opts, 1000, 42)
    assert "--profile-out" not in command
    assert command[command.index("--turns") + 1] == "7"
    assert command[command.index("--warmup") + 1] == "2"
    assert "--cli-arg=--cities" in command
