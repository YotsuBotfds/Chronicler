# Workstations: Ryzen 9 9950X and Ryzen 9 3950X

This guide sets up a full development and evaluation environment on a 16-core workstation. Such a machine can run every test lane, build the native extension and run the 200-seed gate quickly. A 4-core cloud container or GitHub runner cannot do the last two well.

It adds nothing new to install. It assembles the documented paths ([DEVELOPMENT.md](DEVELOPMENT.md), the [README](../README.md), `setup.sh`/`setup.bat`) for these machines, and it records what has to be measured on them. The tasks it feeds are ENV-1 to ENV-8 in the [roadmap](superpowers/roadmaps/streamline-and-deepen.md).

## The machines

| | Ryzen 9 9950X | Ryzen 9 3950X |
|---|---|---|
| Cores / threads | 16 / 32 | 16 / 32 |
| Microarchitecture | Zen 5 | Zen 2 |
| Vector ISA | AVX-512 and AVX2 | AVX2 (no AVX-512) |
| Memory | 192 GB DDR5 (recorded at project start, 2026-03; re-check) | not recorded |
| GPU | RTX 4090, used with LM Studio for local narration | not recorded |
| OS | Windows (recorded 2026-03) | not recorded |

Fill in the blanks with the machine receipt (ENV-2) when each machine is set up.

## Recommended layout

1. **Give each machine one Linux environment for canonical work.** Use native Ubuntu 24.04, or WSL2 Ubuntu 24.04 on Windows.
   - CI runs on Ubuntu.
   - The durable session tools and their suites are POSIX-only: they need advisory locks, atomic replace and directory fsync (see DEVELOPMENT.md "Python on Mac or Linux").
   - The identity and gate tools are run and compared on Linux.
2. **Windows-native use is optional.** It suits viewer work, LM Studio and interactive runs. `setup.bat` supports it, but the Windows selection is a bounded subset of the tests, not the POSIX lane.
3. **Use one checkout per environment.**
   - In WSL2, clone inside the Linux file system, for example `~/src/Chronicler`. Never build from `/mnt/c`: it is slow and mixes line endings.
   - Do not share `.venv`, the native venv or `chronicler-agents/target` between Windows and Linux, or between the two machines.
4. **Build the native extension on each machine.** Do not copy wheels between the 9950X and the 3950X unless they were built for a common baseline (see "Native builds").

### WSL2 settings (Windows)

`%UserProfile%\.wslconfig`:

```ini
[wsl2]
processors=32
memory=160GB          # WSL2 defaults to half the host's RAM; leave headroom for Windows and LM Studio
swap=16GB
networkingMode=mirrored  # Windows 11 22H2+: localhost reaches LM Studio on the host
```

Run `wsl --shutdown`, then check inside Ubuntu that `nproc` prints 32 and that `free -g` shows the new limit.

## Toolchain

| Tool | Version | Linux / WSL2 | Windows native |
|---|---|---|---|
| Git | any recent | `apt install git` | Git for Windows |
| Build tools | – | `apt install build-essential pkg-config curl` | Visual Studio Build Tools, "Desktop development with C++" |
| uv | ≥ 0.5, < 1 (as CI) | official installer | official installer |
| Python | 3.13 (CI uses 3.13) | `uv python install 3.13` | `uv python install 3.13` |
| Rust | stable, ≥ 1.85 (`rust-version` in `chronicler-agents/Cargo.toml`) | rustup | rustup (MSVC host) |
| Node.js | 22.12+ or 20.19+ (Vite 7) | nvm or NodeSource | official installer |
| Optional | cargo-nextest; Playwright Chromium for `viewer/scripts` QA (not yet declared, FIX-8) | `cargo install cargo-nextest`; `npx playwright install chromium` | same |

## Install

Linux or WSL2, from the checkout:

```bash
CHRONICLER_PYTHON="$(uv python find 3.13)" bash setup.sh --native-venv
```

This creates two environments:
- **`.venv`** is the no-native lane. It is installed exactly from `uv.lock` and has no `chronicler_agents`.
- **`~/.venvs/chronicler-native`** holds a fresh `maturin develop --release --locked` build of the Rust extension.

Keep them separate; DEVELOPMENT.md explains why. On Windows, `setup.bat --native-venv` creates the same layout, with the native venv under `%USERPROFILE%\.venvs\chronicler-native`.

## Environment variables

| Variable | Setting | Why |
|---|---|---|
| `PYTHONHASHSEED` | `0` in your shell profile | Some code still iterates sets in hash order. COR-1 fixes it; until then `war_requisition.py:183` and the goods-economy sums in `economy.py` depend on it. `what_if` exact runs require it (`what_if.py:224`). `--batch --parallel` workers on Windows start as new processes, so without it each worker draws its own hash seed. All identity tools use 0. |
| `RAYON_NUM_THREADS` | unset | Batch and ablation workers set it to 1 each (`batch.py:203`). A single large hybrid run uses every thread when it is unset. |
| `RUSTFLAGS` | unset for builds you compare or share | See "Native builds". |
| `CHRONICLER_NATIVE_VENV` | optional | Moves the native venv. |

## First-run checklist

Run these in order on each machine and environment, and record the results in the receipt table at the end. Every step uses commands the repository already documents.

```bash
# 1. Environments are what they claim to be
.venv/bin/python scripts/check_python_env.py --expect no-native
~/.venvs/chronicler-native/bin/python scripts/check_python_env.py --expect native

# 2. Bounded offline Python lane (76 chunks of at most 110 s each; serial today, ENV-3 adds --jobs)
.venv/bin/python scripts/run_python_oracle_checks.py

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

# 8. The canonical validation gate (ENV-6); compare it with CI's run on the same commit
~/.venvs/chronicler-native/bin/python scripts/m53b_run_validation.py --profile full --parallel 30 --output-root output/m53/full-local
```

Expected results:
- Step 1 passes for both environments.
- Steps 2, 3 and 5 pass. Native-only tests skip in `.venv`, and on Windows the POSIX suites skip.
- Step 8 produces a report comparable with CI. The scheduled Validation Gate ran the `full` profile on `main` `c3d752fa` (run 42491150017, 2026-11-08) and passed in about 51 minutes, serially on a GitHub runner. That is the reference for ENV-6.

## Using 32 threads

| Workload | How to parallelise it | Notes |
|---|---|---|
| Batch runs | `--batch N --parallel` (a bare flag sizes the pool to the CPU budget and reserves one CPU) or `--parallel K` | Requires `--simulate-only`. Each seed runs whole in one worker. |
| Validation gate | `scripts/m53b_run_validation.py --parallel K` | Try K = 30. Measure peak memory on a short run first. |
| Screens and funnels | `--jobs K` (`livelihoods_screens.py`, `productive_recovery_screens.py`, the funnels) | Defaults are 2–3, sized for CI. |
| Agent-scale benchmark | `scripts/agent_scale_benchmark.py --jobs K` | |
| Oracle lane | serial today | ENV-3 adds `--jobs`. |
| Full pytest | serial (`pytest-xdist` is not a dependency) | |
| Rust | `cargo test` and builds use every core | |
| Viewer tests | `--maxWorkers` | |

Memory scales with the number of workers and, in hybrid mode, with agent counts. Check the peak memory of one worker before you size K for the 3950X.

## Native builds

- **Build per machine.** The supported build is `maturin develop --release --locked` in the native venv; `setup.sh` runs it. The release profile already uses LTO with `codegen-units = 1`.
- **`-C target-cpu=native`.** Leave it off for anything you compare across machines or share. A 9950X build may use AVX-512, which the 3950X lacks. Rust does not fuse floating-point operations on its own, so the instruction set should not change results, but check it with an identity compare before trusting it (ENV-7).
- **jemalloc.** The crate has an optional `jemalloc` feature (`chronicler-agents/Cargo.toml`). It is for Linux only; it does not build on MSVC. Measure it with the agent-scale benchmark before adopting it.

## Cross-machine identity (ENV-5)

Nobody has yet checked whether the 9950X, the 3950X, Windows, WSL2 and CI produce byte-identical outputs. A plausible source of last-bit differences is the platform's floating-point math library (glibc against the Windows CRT). Measure it rather than assume it:

```bash
PYTHONHASHSEED=0 ~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py run output/identity/<machine>-<os>
.venv/bin/python scripts/turn_speed_identity.py compare output/identity/9950x-wsl output/identity/3950x-linux
```

Record which pairs match. The answer decides where the identity goldens of PIN-2 are captured and which machine serves as the gate machine.

## Local narration (LM Studio on the 4090)

- Narration defaults to `--narrator local` with `--local-url http://localhost:1234/v1` (LM Studio's OpenAI-compatible server).
- From WSL2 in mirrored networking mode, `localhost` reaches the Windows host. In NAT mode, use the host's IP and enable LM Studio's serving on the local network.
- `--simulate-only` runs never call a narrator.
- The simulation decides outcomes; narration only describes them.

## Claude Code on the workstations

- **Local sessions.** Run Claude Code in the checkout on the workstation, either in the Claude desktop app or with `claude` in a terminal. `claude remote-control` in the repository folder makes the session visible in the Claude app.
- **Cloud sessions.** A cloud session can work in a workstation folder only if the folder is shared through the desktop app (Settings, Claude Code, Remote Control). This may not be available on every account.
- **Setup scripts.** `scripts/cloud_setup.sh` is for cloud containers. On a workstation, use `setup.sh --native-venv`.

## Machine receipts

Fill this in as each environment is set up. ENV-2 will generate the first columns.

| Machine | OS / env | Python | rustc | Node | Native ext SHA-256 | Oracle lane | Full pytest | `cargo test` | Full gate (K workers) | Identity vs CI |
|---|---|---|---|---|---|---|---|---|---|---|
| 9950X | WSL2 Ubuntu 24.04 | | | | | | | | | |
| 9950X | Windows native | | | | | | n/a (POSIX suites skip) | | | |
| 3950X | | | | | | | | | | |
