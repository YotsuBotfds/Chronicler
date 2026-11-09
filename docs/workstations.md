# Workstations: Ryzen 9 9950X and Ryzen 9 3950X (Linux)

This guide sets up a full development and evaluation environment on the two 16-core Linux workstations. Such a machine can run every test lane, build the native extension and run the 200-seed gate quickly. A 4-core cloud container or GitHub runner cannot do the last two well.

It adds nothing new to install. It assembles the documented paths ([DEVELOPMENT.md](DEVELOPMENT.md), the [README](../README.md), `setup.sh`) for these machines, and it records what has to be measured on them. The tasks it feeds are ENV-1 to ENV-8 in the [roadmap](superpowers/roadmaps/streamline-and-deepen.md).

Both machines are assumed to run Linux (owner instruction, 2026-11-08). If one runs Windows, see the appendix.

## The machines

| | Ryzen 9 9950X | Ryzen 9 3950X |
|---|---|---|
| Cores / threads | 16 / 32 | 16 / 32 |
| Microarchitecture | Zen 5 | Zen 2 |
| Vector ISA | AVX-512 and AVX2 | AVX2 (no AVX-512) |
| Memory | 192 GB DDR5 (recorded at project start, 2026-03; re-check) | not recorded |
| GPU | RTX 4090 (local narration) | not recorded |
| OS | Linux | Linux |

Fill in the blanks with the machine receipt (`check_python_env.py --machine`, below).

## Layout

- **Check out once per machine**, on a local disk (not a network share). Do not share `.venv`, the native venv or `chronicler-agents/target` between machines; each machine builds its own.
- **Use two environments per checkout**, as DEVELOPMENT.md describes:
  - `.venv` is the no-native lane. It is installed exactly from `uv.lock` and has no `chronicler_agents`.
  - `~/.venvs/chronicler-native` holds the Rust extension, built on that machine.
- **CI is Ubuntu.** Ubuntu 24.04 LTS is the closest match. Any current distribution with Python 3.13 (through uv), rustup and Node works.

## Toolchain

| Tool | Version | Ubuntu / Debian | Fedora | Arch |
|---|---|---|---|---|
| Git, compiler, pkg-config | – | `sudo apt install git build-essential pkg-config curl` | `sudo dnf install git gcc gcc-c++ make pkgconf-pkg-config curl` | `sudo pacman -S git base-devel curl` |
| uv | ≥ 0.5 (CI pins `<1`) | official installer | same | same |
| Python | 3.13, patch ≥ 3.13.17 (CI pins 3.13.17 for its native jobs). 3.13.5 fails `test_argparse_output_is_pinned` in the `validation-tooling` chunk on untouched `main`, because its argparse prints choices without quotes; 3.13.18 passes. | `uv python install 3.13`, then check `python --version` | same | same |
| Rust | stable, ≥ 1.85 (`rust-version` in `chronicler-agents/Cargo.toml`) | rustup | rustup | rustup |
| Node.js | 22.12+ or 20.19+ (Vite 7) | nvm or NodeSource | nvm or `dnf module` | nvm or `pacman -S nodejs npm` |
| Optional | cargo-nextest; Playwright Chromium for the `viewer/scripts` QA tools (not yet declared as a dependency, FIX-8) | `cargo install cargo-nextest`; `npx playwright install --with-deps chromium` | same | same |

## Install

```bash
CHRONICLER_PYTHON="$(uv python find 3.13)" bash setup.sh --native-venv
```

## Environment variables

Set these in `~/.profile` or `~/.bashrc`.

| Variable | Setting | Why |
|---|---|---|
| `PYTHONHASHSEED` | `0` | Some code still iterates sets in hash order, for example `war_requisition.py:183` and the goods-economy sums in `economy.py`; COR-1 removes that. Parallel batch workers are spawned and run with hash seed 0 when the parent has no `PYTHONHASHSEED` (ENV-4), so a parallel batch equals the sequential batch run with 0. Sequential runs and other tools still use the parent's seed, so two invocations without it can differ. `what_if` exact runs require it (`what_if.py:224`), and every identity tool uses 0. |
| `RAYON_NUM_THREADS` | unset | Batch and ablation workers set it to 1 each (`batch.py:203`). A single large hybrid run uses every thread when it is unset. |
| `RUSTFLAGS` | unset for builds you compare or share | See "Native builds". |
| `CHRONICLER_NATIVE_VENV` | optional | Moves the native venv. |

For long benchmark or gate runs, the `performance` CPU governor gives steadier timings, for example `sudo cpupower frequency-set -g performance`. The machine receipt reports the current governor.

## First-run checklist

Run these in order on each machine, and record the results in the receipt table at the end.

```bash
# 1. Environments are what they claim to be. Each command checks and saves a receipt; exit status 0 means PASS.
#    The native receipt's native.compiled_files[].sha256 is the "Native ext SHA-256" column.
mkdir -p output
.venv/bin/python scripts/check_python_env.py --expect no-native --machine --json > output/machine-receipt-no-native.json
~/.venvs/chronicler-native/bin/python scripts/check_python_env.py --expect native --machine --json > output/machine-receipt-native.json

# 2. Bounded offline Python lane: 76 chunks of at most 110 s each.
#    CI runs it serially; --jobs runs chunks at once (keep it at or below the 16 physical cores)
.venv/bin/python scripts/run_python_oracle_checks.py --jobs 12

# 3. Full no-Rust suite (native-only tests skip here)
.venv/bin/python -m pytest -q

# 4. Native Python lane: see README "native Python lane" (preloads and checks the real
#    extension, then runs pytest in the native venv)

# 5. Rust suite
cargo test --manifest-path chronicler-agents/Cargo.toml --quiet

# 6. Viewer
npm --prefix viewer ci
npm --prefix viewer test -- --maxWorkers=16
npm --prefix viewer run lint
npm --prefix viewer run build

# 7. Simulation smoke run, then a parallel batch smoke run
.venv/bin/python -m chronicler.main --seed 42 --turns 20 --agents off --simulate-only --output output/smoke/chronicle.md
~/.venvs/chronicler-native/bin/python -m chronicler.main --batch 32 --parallel --seed 42 --turns 100 --simulate-only --output output/smoke-batch/chronicle.md

# 8. The canonical validation gate on your current checkout (a local PASS, nothing more)
~/.venvs/chronicler-native/bin/python scripts/m53b_run_validation.py --profile full --parallel 30 --output-root output/m53/full-local
```

Expected results:
- Step 1 passes for both environments.
- Steps 2, 3 and 5 pass, with native-only tests skipping in `.venv`.
- Step 8 is a local PASS or FAIL on whatever you checked out. It is not, by itself, a reproduction of CI.

### Reproducing CI's reference gate run (ENV-6)

The scheduled Validation Gate ran the `full` profile on `main` `c3d752fa` (run 42491150017, 2026-11-08) and passed in about 51 minutes, serially on a GitHub runner. A same-source reproduction needs that exact commit, a fresh native build from it, and CI's report as the baseline:

1. Run `git worktree add ../chronicler-c3d752fa c3d752faf0b287b7833bf5d58af470a127c985b2`, then run `setup.sh --native-venv` inside it. Use a separate `CHRONICLER_NATIVE_VENV`, so your everyday native venv is untouched.
2. Download the run's artifact `validation-gate-42491150017`, which holds `output/github-validation/42491150017/`, into a directory outside the worktree, for example with `gh run download 42491150017 -n validation-gate-42491150017 -D ../ci-gate-42491150017`. Locate the validation report JSON in it.
3. In the worktree, run `PYTHONHASHSEED=0 $CHRONICLER_NATIVE_VENV/bin/python scripts/m53b_run_validation.py --profile full --parallel K --output-root output/m53/full-c3d752fa --baseline-report ../ci-gate-42491150017/<report>.json`. Choose K from the machine receipt's batch budget and a one-run memory probe.
4. Record:
   - pass/fail equality;
   - the comparison's regression lines;
   - wall time, K and peak memory;
   - the receipts.

Only an equal verdict, with no unexplained metric difference against CI's report on the same commit, counts as a demonstrated reproduction. The [workstation plan](superpowers/plans/2026-11-08-workstation-environments.md), measurement M3, has the same steps.

## Using 32 threads

| Workload | How to parallelise it | Notes |
|---|---|---|
| Oracle lane | `run_python_oracle_checks.py --jobs N` | Chunks start in order, nothing new starts after a failure, and the receipt lists chunks in order. CI keeps N = 1. |
| Batch runs | `--batch N --parallel` (a bare flag sizes the pool to the CPU budget and reserves one CPU) or `--parallel K` | Requires `--simulate-only`. Each seed runs whole in one worker. |
| Validation gate | `scripts/m53b_run_validation.py --parallel K` | Try K = 30. Measure peak memory on a short run first. |
| Screens and funnels | `--jobs K` (`livelihoods_screens.py`, `productive_recovery_screens.py`, the funnels) | Defaults are 2–3, sized for CI. |
| Agent-scale benchmark | `scripts/agent_scale_benchmark.py --jobs K` | |
| Full pytest | serial (`pytest-xdist` is not a dependency) | |
| Rust | `cargo test` and builds use every core | |
| Viewer tests | `--maxWorkers` | |

Memory scales with the number of workers and, in hybrid mode, with agent counts. Check the peak memory of one worker before you size K for the 3950X, with `/usr/bin/time -v` (the `time` package on Ubuntu/Debian; the shell builtin `time` does not report memory).

## Native builds

- **Build per machine.** The supported build is `maturin develop --release --locked` in the native venv; `setup.sh` runs it. The release profile already uses LTO with `codegen-units = 1`.
- **`-C target-cpu=native`.** Leave it off for anything you compare across machines or share. A 9950X build may use AVX-512, which the 3950X lacks. Rust does not fuse floating-point operations on its own, so the instruction set should not change results, but check it with an identity compare before trusting it (ENV-7). `-C target-cpu=x86-64-v3` is the baseline both CPUs share.
- **jemalloc.** The crate has an optional `jemalloc` feature (`chronicler-agents/Cargo.toml`): `maturin develop --release --locked --features jemalloc` in the native venv. Measure it with the agent-scale benchmark before adopting it.

## Cross-machine identity (ENV-5)

Both machines run Linux, so the open questions are narrower:
- Do Zen 5 and Zen 2 produce byte-identical outputs?
- Does each match an Ubuntu CI-like container?
- How do distribution differences (glibc version, compiler) matter?

Measure it rather than assume it:

```bash
PYTHONHASHSEED=0 ~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py run output/identity/9950x
.venv/bin/python scripts/turn_speed_identity.py compare output/identity/9950x output/identity/3950x
```

Record which pairs match. The answer decides where the identity goldens of PIN-2 are captured and which machine serves as the gate machine.

## Local narration

- Narration defaults to `--narrator local` with `--local-url http://localhost:1234/v1` (an OpenAI-compatible server).
- LM Studio's Linux build serves that address. Any OpenAI-compatible server works if you point `--local-url` at it, for example llama.cpp's server, vLLM or Ollama's OpenAI endpoint.
- `--simulate-only` runs never call a narrator.
- The simulation decides outcomes; narration only describes them.

## Claude Code on the workstations

- **Local sessions.** Run Claude Code in the checkout on the workstation with `claude` in a terminal. `claude remote-control` in the repository folder also makes the session visible in the Claude app.
- **Cloud sessions.** A cloud session can work in a workstation folder only if the folder is shared through Remote Control. This may not be available on every account.
- **Setup scripts.** `scripts/cloud_setup.sh` is for cloud containers. On a workstation, use `setup.sh --native-venv`.

## Machine receipts

Fill this in as each machine is set up. `check_python_env.py --machine --json` gives the first columns.

| Machine | Distribution / kernel | Python | rustc | Node | Native ext SHA-256 | Oracle lane (`--jobs`) | Full pytest | `cargo test` | Full gate (K workers) | Identity vs CI |
|---|---|---|---|---|---|---|---|---|---|---|
| 9950X | | | | | | | | | | |
| 3950X | | | | | | | | | | |

Cloud-container reference (4 cores, 2026-11-08, the code of commit `987a107`): the oracle lane passed both ways.

| Run | Chunks | Tests | Lane time | Slowest chunk |
|---|---|---|---|---|
| Serial | 76 | 8,135 passed, 69 skipped, 0 failed | 324.6 s | `systems-2`, 33.1 s |
| `--jobs 4` | 76, same order | same per-chunk counts | 85.2 s | `systems-2`, 33.7 s |

The limit is 110 s per chunk. On a 16-core workstation, `--jobs 12` should be faster still; measure it before relying on it.

## Appendix: if a machine runs Windows

Use WSL2 with Ubuntu 24.04 for canonical work. Clone inside the Linux file system, not under `/mnt/c`.

`%UserProfile%\.wslconfig`:

```ini
[wsl2]
processors=32
memory=160GB
networkingMode=mirrored
```

The last line lets `localhost` reach a narration server on the Windows host. `setup.bat` supports native Windows for the viewer and interactive runs; the POSIX session suites do not run there. Batch workers are spawned on every platform and run with hash seed 0 unless `PYTHONHASHSEED` is set (ENV-4).
