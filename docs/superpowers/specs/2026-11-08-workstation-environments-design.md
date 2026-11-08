# Workstation environments (9950X, 3950X) — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** ENV-1 to ENV-8
> **Depends on:** nothing (ENV-5 and ENV-6 need a set-up machine)
> **Feeds:** PIN-2 (where identity goldens are captured), COR-1 (hash-seed sweep), every correction or feature that needs a 200-seed before/after baseline, DEP-9
> **Source:** owner goal: run Chronicler on a Ryzen 9 9950X or Ryzen 9 3950X workstation so that testing and expansion are easier. User guide: [docs/workstations.md](../../workstations.md)

## 1. Goal and scope

Make the two 16-core workstations the primary development and evaluation machines:

- **Documentation.** A setup guide (ENV-1) and agent-session notes (ENV-8).
- **Tooling** (three small, unpinned changes):
  - a machine receipt (ENV-2);
  - a parallel oracle lane (ENV-3);
  - hash-seed-safe parallel batches (ENV-4).
- **Measurements** (three, recorded in the guide):
  - a cross-machine identity matrix (ENV-5);
  - a local reproduction of CI's validation gate (ENV-6);
  - native build tuning (ENV-7).

Not changed: CI jobs, simulation defaults, outcomes on any platform where `PYTHONHASHSEED` is already set, CLI flags (new flags only), pinned files.

## 2. Current behaviour (verified)

**Setup.**
- `setup.sh` and `setup.bat` already build the two-venv layout. `.venv` is installed from `uv.lock` by `uv sync --frozen`. `--native-venv` builds the extension into `~/.venvs/chronicler-native` (`setup.sh:1-20`, `setup.sh:125-147`; DEVELOPMENT.md "Python environments").
- On Windows, the POSIX-only session suites are excluded (DEVELOPMENT.md "Python on Mac or Linux").

**CI.**
- CI is Ubuntu only (30 `runs-on: ubuntu-*` lines across `.github/workflows/`).
- The scheduled Validation Gate runs `scripts/m53b_run_validation.py --profile full` serially (no `--parallel`), with the native wheel installed into `.venv` (`.github/workflows/validation-gate.yml:44-111`).
- Run 42491150017 on `main` `c3d752fa` (2026-11-08) passed in about 51 minutes.

**Batches.**
- `--batch --parallel` uses `multiprocessing.Pool(workers, initializer=_init_parallel_worker)` (`batch.py:122`). The initializer only sets `RAYON_NUM_THREADS=1` (`batch.py:198-203`).
- No start method is chosen, so Linux forks and Windows spawns. No code sets `PYTHONHASHSEED`, and `batch_manifest.environment_identity` only records it (`batch_manifest.py:180-192`, `:442`).
- A bare `--parallel` sizes the pool to the affinity/cgroup-aware CPU budget minus one (`batch.py:35-50`, `main.py:2105`).
- A 4-seed `--parallel` smoke run passed in the cloud container (exit 0).

**Scripts.**
- `scripts/run_python_oracle_checks.py` runs its 76 chunks serially. Its options are `--list` and `--output-dir` (`:501-502`).
- `scripts/turn_speed_identity.py` has `run OUT [--case] [--source-root] [--native-root]` and `compare BASE NEW` (`:348-357`).
- `scripts/check_python_env.py` reports the interpreter and native state, with `--expect native|no-native`.
- Narration defaults to LM Studio at `http://localhost:1234/v1` (`llm.py:15`, `--local-url` at `main.py:2092`).

**Native build.**
- The crate has a `jemalloc` feature (`chronicler-agents/Cargo.toml` `[features]`).
- The release profile is `lto = true`, `codegen-units = 1`, `opt-level = 3`.

## 3. Design

- **ENV-1 Setup guide.** `docs/workstations.md` covers machines, layout (one Linux environment per machine, WSL2 on Windows), toolchain, install, environment variables, the first-run checklist, threads, native builds, identity, narration, sessions, and a receipt table. Link it from `docs/README.md` and DEVELOPMENT.md.

- **ENV-2 Machine receipt.** `scripts/check_python_env.py --machine [--json PATH]`, report-only, exit 0. It adds:
  - CPU model (`/proc/cpuinfo` "model name"; on Windows, `platform.processor()` plus `PROCESSOR_IDENTIFIER`);
  - logical CPUs and the batch CPU budget, by reusing `chronicler.cpu_budget.automatic_workers` (the function `batch.parallel_workers` uses);
  - total memory (`/proc/meminfo`, or `GlobalMemoryStatusEx` via `ctypes` on Windows);
  - OS release and a WSL flag (`microsoft` in `/proc/sys/kernel/osrelease`);
  - tool versions: `uv`, `rustc`, `cargo`, `node`, `npm` (each `--version` through `subprocess`, with a 5 s timeout; "absent" when not found);
  - `PYTHONHASHSEED`, `RAYON_NUM_THREADS` and `RUSTFLAGS`;
  - git HEAD and dirty state.

  It never imports `chronicler_agents` unless `--expect native` is also given. Its JSON fills the guide's receipt table and can be attached to gate and benchmark outputs.

- **ENV-3 Parallel oracle lane.** `run_python_oracle_checks.py --jobs N`. The default of 1 keeps today's serial behaviour, so CI is unchanged.
  - With N > 1, a thread pool launches up to N chunk subprocesses. Each is already its own guarded pytest process with its own 110 s limit, and the limit stays.
  - The receipt keeps chunk order.
  - On the first failure, no new chunks start, running chunks finish, and every failure is reported. The exit code keeps its meaning.
  - The guide recommends N ≤ 16 (physical cores) so that contention does not push a chunk near its cap over the 110 s limit.

- **ENV-4 Hash-seed-safe parallel batches.** In `run_batch`, the pool is created with `multiprocessing.get_context("spawn")`. If the parent's environment has no `PYTHONHASHSEED`, `"0"` is set in `os.environ` before the pool starts, so every worker on every platform uses hash seed 0.
  - Today, forked Linux workers inherit the parent's random hash secret and spawned Windows workers each draw their own. Hash-order-dependent code (`war_requisition.py:183`, the goods-economy sums in `economy.py`) can therefore differ from run to run and from worker to worker.
  - The manifest's existing `environment_identity()` then records the value actually used. The plan verifies the call order.
  - Sequential runs are unchanged. After COR-1 removes the order-sensitive sites, the difference disappears entirely.
  - Spawn adds the import cost per worker (about 1.8 s, scout 28), which is negligible for batch runs.

- **ENV-5 Identity matrix.**
  - Run `PYTHONHASHSEED=0 … turn_speed_identity.py run` on each environment: 9950X WSL2, 9950X Windows native, 3950X, and one CI-like Ubuntu container.
  - `compare` every pair and record the results in the guide.
  - Decision rule: environments that match exactly share goldens. If Windows differs from Linux, Linux or WSL2 is canonical for PIN-2 goldens and gate evidence, and Windows is supported but not canonical.

- **ENV-6 Local gate reproduction.**
  - Check out `c3d752fa` and set up the native venv as CI does (a wheel or `maturin develop --release --locked`).
  - Run `m53b_run_validation.py --profile full --parallel K`, with K chosen from the ENV-2 budget and a one-run memory probe.
  - Download CI run 42491150017's report artifact and compare the two with `--baseline-report`.
  - Accept when pass/fail is equal and the metrics are equal, or within the gate's own tolerance where hash-seed-sensitive sums are involved. Record wall time and peak RSS.
  - From then on, the workstation is an admissible machine for before/after baselines. The owner confirms this as part of DEC-1 or a separate note.

- **ENV-7 Native tuning (optional, after ENV-5).**
  - Benchmark with `scripts/agent_scale_benchmark.py`: `--features jemalloc` (Linux only), and `RUSTFLAGS="-C target-cpu=x86-64-v3"` (a baseline both CPUs share) against default.
  - Adopt a setting only if `turn_speed_identity compare` stays empty and the speedup is measurable. Never ship `target-cpu=native` artifacts across the two machines.

- **ENV-8 Agent sessions.** Add a short AGENTS.md note: on workstations, use `setup.sh --native-venv`; `scripts/cloud_setup.sh` is for cloud containers. The guide covers local and Remote Control sessions.

## 4. Compatibility

- **Flags:** new flags only (`--machine`, `--json`, `--jobs`). Outputs and receipts keep their shapes; the oracle receipt keeps chunk order.
- **Batch outputs:** on Linux runs with `PYTHONHASHSEED` already set, parallel batch outputs are byte-identical to before. Without it, they become deterministic (hash seed 0) where they were random. Saved bundles and manifests keep their fields.

## 5. Pins and preflight

`refactor_preflight.py` levels:

| File | Level |
|---|---|
| `scripts/check_python_env.py` | reference |
| `scripts/run_python_oracle_checks.py` | reference |
| `scripts/m53b_run_validation.py` | reference |
| `scripts/turn_speed_identity.py` | reference |
| `src/chronicler/batch.py` | historical and reference |
| `docs/DEVELOPMENT.md`, `setup.sh`, `setup.bat` | reference |

None is enforced. `batch_manifest.py` is enforced, so ENV-4 must not edit it; its existing environment capture records the hash seed. The tests that touch these files are `tests/test_check_python_env.py`, `tests/test_native_ci_shards.py` (it names the oracle runner) and `tests/test_batch*.py`. README.md is read by `tests/test_native_build_lanes.py`, so the guide is linked from `docs/README.md` and DEVELOPMENT.md, not from README.

## 6. Classification

| Task | Class | Proof |
|---|---|---|
| ENV-1, ENV-8 | docs | – |
| ENV-2, ENV-3 | tooling | Serial `--jobs 1` output equals today's |
| ENV-4 | fix (removes nondeterminism) | A test shows sequential runs with `PYTHONHASHSEED=0` equal parallel runs whose parent has no `PYTHONHASHSEED`. `turn_speed_identity` cases (which run with `PYTHONHASHSEED=0`) are unchanged. |
| ENV-5, ENV-6, ENV-7 | measurement | Recorded receipts |

## 7. Tests

- **`tests/test_check_python_env.py`:**
  - `--machine --json` writes the documented keys;
  - no import of `chronicler_agents` without `--expect native`;
  - tool absence is reported as "absent".
- **New `tests/test_oracle_runner_jobs.py`** (added to an oracle chunk with headroom and to the shard manifest's additions map):
  - with two fake chunks, `--jobs 2` records results in chunk order;
  - a failing chunk stops further launches;
  - `--jobs 1` equals serial.
- **`tests/test_batch_worker_threads.py`, in the native/subprocess lane** (the oracle guard blocks child processes):
  - a spawned-pool batch with an unset parent seed records `PYTHONHASHSEED=0` in the manifest;
  - it equals a `PYTHONHASHSEED=0` sequential batch.

## 8. Risks, open questions, rollback

- **Open questions:**
  - What OS does the 3950X run? (The guide covers both.)
  - Will the owner admit workstation gate runs as evidence?
  - What is WSL2's memory ceiling on the 9950X?
- **Risks:**
  - ENV-3 contention could push slow chunks over 110 s. Mitigate with a lower N; the cap itself stays.
  - Spawn on Linux changes worker start-up cost and the fork-inherited state. A worker that relied on state inherited from the parent would break, and the batch tests catch that.
- **Rollback:** each PR is independent. ENV-4 reverts to the default context.

## 9. Size

| Task | Lines |
|---|---:|
| ENV-2 | about +150 |
| ENV-3 | about +80 |
| ENV-4 | about +15 |
| Tests | about +200 |
| Docs | about +250 |

That makes 3 code PRs, 1 docs PR (ENV-1 and ENV-8), and 3 measurement records.
