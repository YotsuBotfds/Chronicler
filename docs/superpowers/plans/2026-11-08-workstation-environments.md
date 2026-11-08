# Workstation environments — Implementation Plan

> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** Make the Ryzen 9 9950X and 3950X workstations ready for every lane and gate, and measure what they reproduce.

**Architecture:**
- Docs: [docs/workstations.md](../../workstations.md).
- Three small, unpinned tooling changes: a machine receipt, `--jobs` for the oracle lane, and a spawn pool with hash seed 0 for parallel batches.
- Three measurement records.

**Tech stack:** Python 3.13 and uv, Rust stable, Node 22, WSL2 Ubuntu 24.04.

**Status:** PR 1 (ENV-1, ENV-8), PR 2 (ENV-2) and PR 3 (ENV-3) are implemented on branch `claude/relaxed-brown-4ozgeg`. PR 4 (ENV-4) is lower priority on Linux. Both machines run Linux.

**Prerequisites:** none for PR 1 to PR 4. Measurements M1 to M3 need a workstation set up per the guide. Spec: `docs/superpowers/specs/2026-11-08-workstation-environments-design.md`.

## File map

| File | Change |
|---|---|
| `docs/workstations.md` | guide (exists; extend with receipts) |
| `docs/README.md`, `docs/DEVELOPMENT.md` | one link line each |
| `AGENTS.md` | one sentence (ENV-8) |
| `scripts/check_python_env.py` | `--machine`, `--json` |
| `tests/test_check_python_env.py` | machine-report tests |
| `scripts/run_python_oracle_checks.py` | `--jobs N` |
| `tests/test_oracle_runner_jobs.py` (new) | runner scheduling tests |
| `scripts/testing/native_shards_manifest.json`, `tests/test_native_ci_shards.py` | register the new test module (additions map, module count) |
| `src/chronicler/batch.py` | spawn context, default hash seed |
| `tests/test_batch_worker_threads.py` | parallel/sequential equality under an unset parent seed |

## PR 1: Docs (ENV-1, ENV-8)

- [ ] Step 1: Preflight: `.venv/bin/python scripts/refactor_preflight.py docs/README.md docs/DEVELOPMENT.md AGENTS.md`. All three are reference-only; read the hits.
- [ ] Step 2: Make three one-line edits:
  - In `docs/README.md`, add a bullet: "`workstations.md`: setting up the 16-core workstations (9950X, 3950X): layout, toolchain, threads, identity and gate reproduction."
  - In DEVELOPMENT.md "Python environments", add one sentence linking `workstations.md`.
  - In AGENTS.md "In Claude Code cloud sessions …", add "On a workstation, use `setup.sh --native-venv` (see `docs/workstations.md`)." (already applied on this branch)
- [ ] Step 3: Verify:
  - `.venv/bin/python -m pytest -q tests/test_native_build_lanes.py`: it reads README and workflows, and must stay green.
  - A link check (every relative link in the three files resolves).
- [ ] Step 4: Commit `docs: workstation setup guide and links`.

## PR 2: Machine receipt (ENV-2)

- [ ] Step 1: Preflight `scripts/check_python_env.py tests/test_check_python_env.py`.
- [x] (done) Step 2: Add `--machine` to the argument parser; it combines with the existing `--json`. Add `machine_report() -> dict` with keys:

  ```
  cpu_model, logical_cpus, batch_cpu_budget, memory_bytes, os, os_release, wsl,
  python, uv, rustc, cargo, node, npm, env:{PYTHONHASHSEED,RAYON_NUM_THREADS,RUSTFLAGS},
  git:{head,dirty}
  ```

  - Load `src/chronicler/cpu_budget.py` by path and call `automatic_workers()` for `batch_cpu_budget`.
  - Get each tool version with `subprocess.run([tool, "--version"], timeout=5, capture_output=True)`, after `shutil.which`, and report `"absent"` when the tool is missing.
  - Read memory from `os.sysconf` (`SC_PAGE_SIZE` × `SC_PHYS_PAGES`); report `None` where it does not exist.
  - Set `wsl` when `"microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()`.
  - Do not import `chronicler_agents` unless `--expect native` is also given.
- [ ] Step 3: Tests in `tests/test_check_python_env.py`:
  - JSON keys present;
  - a monkeypatched `shutil.which` returning None yields `"absent"`;
  - `sys.modules` does not gain `chronicler_agents`.

  The oracle guard blocks subprocesses, so mark any test that calls a tool with `pytest.mark.native` or monkeypatch `subprocess.run`.
- [ ] Step 4: Verify:
  - `.venv/bin/python -m pytest -q tests/test_check_python_env.py`
  - `.venv/bin/python scripts/check_python_env.py --machine --json > /tmp/m.json`, then inspect the output. The script takes no output filename; `--json` prints to stdout.
  - `.venv/bin/python scripts/run_python_oracle_checks.py`
- [ ] Step 5: Commit `scripts: machine receipt in check_python_env`.

## PR 3: Parallel oracle lane (ENV-3)

- [ ] Step 1: Preflight `scripts/run_python_oracle_checks.py`. Read `tests/test_native_ci_shards.py` to see how it names the runner, and read the chunk loop and receipt writer (`:532-580`). The loop is top-level script code with no `main()`, so importing the module runs the whole lane.
- [ ] Step 2: Move the top-level execution under `def main()` and `if __name__ == "__main__":`, keeping the `CHUNKS` and `TESTS` definitions at module level for their readers. Then refactor the per-chunk body (`:542-577`) into `run_chunk(name, nodes) -> ChunkResult`. Neither change alters behaviour: the CI command line and the receipt bytes, apart from timings, stay the same.
- [ ] Step 3: Add `--jobs N` (int ≥ 1, default 1).
  - With `N == 1`, keep the existing loop.
  - With `N > 1`, use `concurrent.futures.ThreadPoolExecutor(N)`. Submit chunks in order while no failure has been seen; after the first failure, submit nothing new and let running chunks finish.
  - Write receipts sorted by chunk index. Exit 1 if any chunk failed.
- [ ] Step 4: Write `tests/test_oracle_runner_jobs.py`. Monkeypatch `run_chunk` with fakes that sleep and fail, so no real pytest runs. Assert:
  - order is preserved;
  - nothing is launched after a failure;
  - `--jobs 1` equals serial.

  Register the module in the shard manifest additions map and in the module count in `tests/test_native_ci_shards.py`, and put it in an oracle chunk with headroom.
- [ ] Step 5: Verify:
  - The new test file.
  - `tests/test_native_ci_shards.py`.
  - `.venv/bin/python scripts/run_python_oracle_checks.py` (serial) and `--jobs 4` in the cloud container. Both must pass with the same chunk receipts apart from timings.
- [ ] Step 6: Commit `scripts: --jobs for the bounded oracle lane (default serial)`.

## PR 4: Hash-seed-safe parallel batches (ENV-4)

- [ ] Step 1: Preflight `src/chronicler/batch.py src/chronicler/batch_manifest.py`. `batch_manifest.py` is enforced: do not edit it.
- [ ] Step 2: Confirm the order: `environment_identity()` (`batch_manifest.py:442`) must run after the point where `run_batch` creates the pool. If it runs earlier, record the effective seed by passing an environment copy, or move the default-setting to before the manifest is built.
- [ ] Step 3: In `run_batch`, before `multiprocessing.Pool(...)` (`batch.py:122`):

  ```python
  os.environ.setdefault("PYTHONHASHSEED", "0")  # spawned workers inherit it
  ctx = multiprocessing.get_context("spawn")
  with ctx.Pool(workers, initializer=_init_parallel_worker) as pool:
  ```

  Add a docstring note: "until COR-1 removes set-order iteration, parallel workers run with hash seed 0 on every platform".
- [ ] Step 4: Add a test in `tests/test_batch_worker_threads.py`, in the native/subprocess lane rather than the oracle lane (the guard blocks child processes). Run it in a subprocess whose environment has no `PYTHONHASHSEED`:
  - run a 3-seed, 15-turn, `--agents off` parallel batch;
  - assert the manifest records `PYTHONHASHSEED=0`;
  - assert the bundles are byte-identical (after the existing `generated_at` normalisation) to a sequential batch run with `PYTHONHASHSEED=0`.
- [ ] Step 5: Verify:
  - `.venv/bin/python -m pytest -q tests/test_batch.py tests/test_batch_worker_threads.py tests/test_batch_manifest.py`
  - the batch smoke from the guide.
- [ ] Step 6: Commit `batch: spawn workers with a fixed hash seed`. Add a CONTINUATION note that parallel batches without `PYTHONHASHSEED` are now deterministic; this is a fix, not an outcome correction.

## Measurements (no PR; record in docs/workstations.md, then one docs PR)

- [ ] **M1 (ENV-2 and checklist).** On each environment, set it up per the guide and run the eight checklist steps. Fill the receipt row from `check_python_env.py --machine --json`, and add wall times for steps 2, 3, 5 and 8.
- [ ] **M2 (ENV-5).** Run `PYTHONHASHSEED=0 ~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py run output/identity/<env>` on each environment and in one Ubuntu 24.04 cloud container. `compare` every pair, record the identical and differing pairs, and apply the spec's decision rule.
- [ ] **M3 (ENV-6).**
  1. `git checkout c3d752fa` in a clean worktree, then build the native venv.
  2. Probe memory: run one `--profile full` seed under `/usr/bin/time -v` to get peak RSS per worker.
  3. Run `m53b_run_validation.py --profile full --parallel K --output-root output/m53/full-local`.
  4. Download the report artifact of CI run 42491150017 and compare it with `--baseline-report`.
  5. Record pass/fail equality, metric differences, wall time and K.
- [ ] **M4 (ENV-7, optional).** Benchmark the defaults against `--features jemalloc` and `RUSTFLAGS="-C target-cpu=x86-64-v3"` with `scripts/agent_scale_benchmark.py --jobs 1` on both CPUs. Adopt a setting only with an empty identity compare and a measurable gain.

## Done when

- [ ] The guide is linked, and every machine and environment has a receipt row.
- [ ] `--machine`, `--jobs` and the spawn-pool fix are merged with tests; CI is unchanged (serial oracle lane).
- [ ] The identity matrix is recorded and the canonical environment is named.
- [ ] A local full gate on `c3d752fa` is compared with CI run 42491150017, and the result is recorded.
