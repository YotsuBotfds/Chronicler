"""Tests for batch runner."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import argparse

from chronicler.batch import run_batch


@pytest.fixture
def batch_args(tmp_path):
    return argparse.Namespace(
        seed=42, turns=3, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        local_url="http://localhost:1234/v1",
        sim_model=None, narrative_model=None,
        llm_actions=False, scenario=None,
        batch=3, fork=None, interactive=False,
        parallel=None, pause_every=None,
        tuning=None, simulate_only=False, seed_range=None,
    )


class TestRunBatch:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_creates_output_directories(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        assert (batch_dir / "seed_42").is_dir()
        assert (batch_dir / "seed_43").is_dir()
        assert (batch_dir / "seed_44").is_dir()

    def test_each_run_produces_chronicle(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        for seed in [42, 43, 44]:
            assert (batch_dir / f"seed_{seed}" / "chronicle.md").exists()
            assert (batch_dir / f"seed_{seed}" / "state.json").exists()

    def test_produces_summary(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        summary = batch_dir / "summary.md"
        assert summary.exists()
        content = summary.read_text()
        assert "Rank" in content or "rank" in content.lower()

    def test_returns_batch_directory_path(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.name == "batch_42"

    def test_tuning_overrides_applied(self, batch_args, tmp_path):
        tuning_file = tmp_path / "tuning.yaml"
        tuning_file.write_text("stability:\n  drain:\n    drought_immediate: 1\n")
        batch_args.tuning = str(tuning_file)
        batch_args.simulate_only = True
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        assert (batch_dir / "summary.md").exists()
        from chronicler.models import WorldState
        for seed in [42, 43, 44]:
            world = WorldState.load(batch_dir / f"seed_{seed}" / "state.json")
            assert "stability.drain.drought_immediate" in world.tuning_overrides
            assert world.tuning_overrides["stability.drain.drought_immediate"] == pytest.approx(1.0)

    def test_simulate_only_skips_llm(self, batch_args, tmp_path):
        """--simulate-only batch runs don't require real LLM clients."""
        batch_args.simulate_only = True
        batch_dir = run_batch(batch_args, sim_client=None, narrative_client=None)
        assert batch_dir.exists()


class _InlinePool:
    """A worker pool that records its size and runs each task in this process."""

    sizes: list[int] = []

    def __init__(self, processes, initializer=None):
        type(self).sizes.append(processes)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def apply_async(self, fn, args):
        result = fn(*args)
        return MagicMock(get=lambda: result)

    def terminate(self):
        pass


class TestParallelWorkers:
    """``--parallel N`` runs N workers; a bare ``--parallel`` sizes the pool."""

    @pytest.fixture
    def pool(self, monkeypatch):
        import chronicler.batch as batch_module
        _InlinePool.sizes = []
        monkeypatch.setattr(batch_module.multiprocessing, "Pool", _InlinePool)
        monkeypatch.setattr(batch_module, "automatic_workers", lambda: 7)
        return _InlinePool

    @pytest.mark.parametrize("parallel, workers", [
        (1, 1),       # an explicit 1 is one worker (main dae4ba5: cpu_count - 1)
        (2, 2),
        (12, 12),
        (-1, 7),      # bare --parallel (argparse const): automatic budget
        (True, 7),    # Batch Lab without a worker count
    ])
    def test_worker_count(self, batch_args, pool, parallel, workers):
        batch_args.simulate_only = True
        batch_args.parallel = parallel
        batch_dir = run_batch(batch_args)
        assert pool.sizes == [workers]
        assert sorted(path.name for path in batch_dir.glob("seed_*")) == ["seed_42", "seed_43", "seed_44"]

    def test_no_pool_without_parallel(self, batch_args, pool):
        for parallel in (None, 0, False):
            batch_args.simulate_only = True
            batch_args.parallel = parallel
            batch_args.output = str(Path(batch_args.output).parent / f"p{parallel}" / "chronicle.md")
            run_batch(batch_args)
        assert pool.sizes == []

    def test_cli_parsing(self):
        from chronicler.batch import parallel_workers
        from chronicler.main import _build_parser
        parser = _build_parser()
        assert parser.parse_args(["--batch", "3"]).parallel is None
        bare = parser.parse_args(["--batch", "3", "--parallel"]).parallel
        one = parser.parse_args(["--batch", "3", "--parallel", "1"]).parallel
        assert (parallel_workers(bare, cpu_count=4), parallel_workers(one, cpu_count=4)) == (3, 1)
        assert parallel_workers(True, cpu_count=1) == 1

    def test_one_worker_gives_the_sequential_results(self, batch_args, pool, tmp_path):
        """Each seed is deterministic: one worker or the sequential path, the same bundles."""
        import json
        batch_args.simulate_only = True

        def bundles(parallel, folder):
            batch_args.parallel = parallel
            batch_args.output = str(tmp_path / folder / "chronicle.md")
            batch_dir = run_batch(batch_args)
            out = {}
            for path in sorted(batch_dir.glob("seed_*/chronicle_bundle.json")):
                data = json.loads(path.read_text())
                data["metadata"].pop("generated_at", None)
                out[path.parent.name] = data
            return out

        assert bundles(1, "one") == bundles(None, "sequential")


class TestAutomaticCpuBudget:
    @pytest.fixture
    def cpu(self, monkeypatch, tmp_path):
        import chronicler.cpu_budget as budget
        root = tmp_path / "cgroup"
        root.mkdir()
        process = tmp_path / "process-cgroup"
        process.write_text("0::/\n")
        monkeypatch.setattr(budget, "_CGROUP_ROOT", root)
        monkeypatch.setattr(budget, "_PROCESS_CGROUP", process)
        monkeypatch.setattr(budget.os, "cpu_count", lambda: 16)
        monkeypatch.setattr(budget.os, "process_cpu_count", lambda: 16, raising=False)
        monkeypatch.setattr(budget.os, "sched_getaffinity", lambda pid: set(range(16)), raising=False)
        return budget, root, process

    @pytest.mark.parametrize("quota,affinity,expected", [
        ("400000 100000", 16, 3),   # host visibility exceeds a four-CPU container
        ("800000 100000", 3, 2),    # affinity is the tighter limit
        ("250000 100000", 16, 1),   # fractional quota rounds down before reserving
        ("50000 100000", 16, 1),    # one worker remains possible below one CPU
        ("max 100000", 4, 3),       # unlimited quota still respects affinity
    ])
    def test_quota_and_affinity_limit_automatic_workers(self, cpu, monkeypatch, quota, affinity, expected):
        budget, root, _process = cpu
        (root / "cpu.max").write_text(quota)
        monkeypatch.setattr(budget.os, "sched_getaffinity", lambda pid: set(range(affinity)))
        assert budget.automatic_workers() == expected

    def test_parent_quota_applies_when_the_process_quota_is_unlimited(self, cpu):
        budget, root, process = cpu
        (root / "cpu.max").write_text("300000 100000")
        nested = root / "parent" / "child"
        nested.mkdir(parents=True)
        (nested.parent / "cpu.max").write_text("200000 100000")
        (nested / "cpu.max").write_text("max 100000")
        process.write_text("0::/parent/child\n")
        assert budget.automatic_workers() == 1

    def test_v1_cpu_controller_quota(self, cpu):
        budget, root, process = cpu
        mount = root / "cpu,cpuacct"
        nested = mount / "job"
        nested.mkdir(parents=True)
        (mount / "cpu.cfs_quota_us").write_text("-1")
        (mount / "cpu.cfs_period_us").write_text("100000")
        (nested / "cpu.cfs_quota_us").write_text("300000")
        (nested / "cpu.cfs_period_us").write_text("100000")
        process.write_text("2:cpu,cpuacct:/job\n")
        assert budget.automatic_workers() == 2

    @pytest.mark.parametrize("malformed", ["", "nonsense", "1 2 3", "400000 0", "-2 100000"])
    def test_malformed_or_missing_quota_falls_back_to_visible_cpus(self, cpu, malformed):
        budget, root, process = cpu
        (root / "cpu.max").write_text(malformed)
        process.write_text("malformed\n0::/../../outside\n")
        assert budget.automatic_workers() == 15

    def test_unreadable_cgroup_and_unsupported_affinity_use_portable_fallback(self, cpu, monkeypatch):
        budget, _root, _process = cpu

        def unreadable(*args, **kwargs):
            raise PermissionError("not available")

        def unsupported(*args):
            raise NotImplementedError

        monkeypatch.setattr(budget.os, "sched_getaffinity", unsupported)
        monkeypatch.setattr(budget.os, "process_cpu_count", lambda: None)
        monkeypatch.setattr(budget.os, "cpu_count", lambda: 4)
        with monkeypatch.context() as scope:
            scope.setattr(Path, "read_text", unreadable)
            workers = budget.automatic_workers()
        assert workers == 3
        monkeypatch.setattr(budget.os, "cpu_count", lambda: None)
        with monkeypatch.context() as scope:
            scope.setattr(Path, "read_text", unreadable)
            workers = budget.automatic_workers()
        assert workers == 1

    def test_explicit_worker_counts_do_not_consult_automatic_budget(self, monkeypatch):
        import chronicler.batch as batch

        def unused():
            raise AssertionError("an explicit count needs no automatic budget")

        monkeypatch.setattr(batch, "automatic_workers", unused)
        assert batch.parallel_workers(1) == 1
        assert batch.parallel_workers(12) == 12
