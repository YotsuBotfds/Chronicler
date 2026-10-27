# Development setup

Use a fresh clone to avoid overwriting preserved work. All source and tests are
in Git; machine-specific environments and historical evidence packages are not
required to edit this branch.

```sh
git clone --branch continuation/recovered-20261011 https://github.com/YotsuBotfds/Chronicler.git
cd Chronicler
git status --short --branch
```

## Python on Windows

Use Python 3.13 or newer. In PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest pytest-asyncio
.\.venv\Scripts\python.exe scripts/run_python_oracle_checks.py
.\.venv\Scripts\python.exe -m chronicler.main --seed 42 --turns 20 --agents off --simulate-only --output output/smoke/chronicle.md
```

Substitute an installed newer Python version if necessary. Do not reuse an
unrelated virtual environment for native qualification. The simulation-only
smoke command needs no narration credential. `--agents off` alone does not
guarantee no native ecology/politics execution if an extension is installed.
The guarded test command explicitly enforces the Python oracle lane.

## Python on Mac or Linux

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -e . pytest pytest-asyncio
.venv/bin/python scripts/run_python_oracle_checks.py
.venv/bin/python -m chronicler.main --seed 42 --turns 20 --agents off --simulate-only --output output/smoke/chronicle.md
```

Use `.venv/bin/python -m pytest -q` for the full no-Rust lane in a clean environment
where `chronicler_agents` is absent. The detached durable session tools require
POSIX advisory locks, nonblocking file reads, atomic replace and directory fsync;
they explicitly reject unsupported Windows persistence. Their suites belong in
the POSIX lane, not in the bounded Windows selection.

The guarded runner splits its selection into chunks (`CHUNKS` in the script).
Each chunk is a separate pytest process with its own offline guard and a
110-second limit; the runner stops at the first failing chunk. It writes the
interpreter, source-file hashes and, per chunk, the command, guard receipt,
exit status, seconds and output under ignored `output/python-oracle/`.
`--list` prints the selected node IDs. When a chunk nears its limit, move files
to another chunk or add one rather than raising the limit. The runner excludes
the two cross-process determinism/replay cases and broader
native/socket/POSIX/subprocess suites. It is a reproducible focused gate, not
the full suite or the scientific milestone gate.

## Viewer

Use Node.js compatible with the locked Vite 7 toolchain (20.19+ or 22.12+).
From `viewer/`:

```sh
npm ci
npm test -- --maxWorkers=2
npm run lint
npm run build
npm run dev
```

The recovery used the existing lockfile; no dependency versions were changed.
Windows Node 26.7.0 passed the tests/build. The existing large-bundle warning
remains. The isolated event/settlement demo pages use synthetic fixtures.

## Native and full qualification

Build into the active virtual environment, with an appropriate Rust toolchain:

```sh
python -m pip install "maturin>=1.5,<2"
python -m maturin develop --release --locked --manifest-path chronicler-agents/Cargo.toml
cargo test --locked --manifest-path chronicler-agents/Cargo.toml
```

Before native Python tests, verify `chronicler_agents.chronicler_agents` resolves
to a compiled extension and `AgentSimulator`, `EcologySimulator`, and
`PoliticsSimulator` are real classes. The exact verification and full-suite
commands are in `README.md` and `.github/workflows/tests.yml`. Native CI builds
fresh source. A previously installed extension is not evidence for this branch.

Full population/regression qualification remains the explicit validation-profile
workflow and 200-seed gate. Do not activate experiments, deploy, or merge this
draft continuation solely because the bounded gate passes.

The gate runner also has a procedural world profile: `--worldgen procedural`
runs every seed on a 32-region, 10-civ heightmap/Voronoi world (subset 20
seeds x 200 turns, full 100 seeds x 300 turns; `--regions`/`--civs`
override). A change to default behaviour should pass it as well as the
template gates; compare a procedural report only with a procedural baseline
of the same world size (the comparator refuses mixed worlds). The procedural
full profile takes about 45 minutes on three workers; its batch holds about
5 GB (2.8 GB without the seeds' `state.json` and memory streams, which the
validator does not read) and validation peaks at 2.5 GB. See
`docs/integration/procedural-gates.md`.

```sh
python scripts/m53b_run_validation.py --profile subset --worldgen procedural --parallel 2 --output-root output/m53/procedural-subset
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 --output-root output/m53/procedural-full
```

A batch (`--batch`, `--seed-range`, the gate runner, Batch Lab) writes
`batch_<first seed>` next to `--output` and refuses a directory that already
holds files: use a new `--output-root` for every gate. Its
`batch_manifest.json` records the expected seeds and turns, the requested
simulation configuration, the source revision and package digest, the native
extension's SHA-256, the interpreter and thread environment, and the SHA-256
of every file the validator reads. `python -m chronicler.validate` refuses a
directory whose bundles, horizons or validation inputs differ from its
manifest; `--legacy-batch` validates a directory written before manifests
without checking its runs. `python -m chronicler.validation_compare` refuses
reports of different seeds, turns, worlds, simulation configuration or
profile unless `--exploratory` (the runner's `--exploratory-comparison`), and
NO REGRESSION means no newly failing required gate, not unchanged
distributions. See `docs/integration/validation-integrity.md`.

The subset and full profiles also run the ablation oracles
(`--ablation-oracles`, the default there; `--no-ablation-oracles` opts out
and leaves the cohort oracle, and in the full profile the needs oracle's
deciding component, `NOT_RUN`: required failures): the batch
writes exact checkpoints at the fork turns (`--checkpoint-turns`), and each
seed is forked at every 100th turn with the need terms (`needs`) and the
kin roots (`kin_roots`) switched off for 22 turns, into `ablation_<first
seed>` beside the batch. The forks keep only their agent events; the
checkpoints (about 1.2 GB for the template full gate) are removed once
forked. On four shared cores the two arms add about 23-28 minutes to the
template full gate (800 forks per arm), 9 minutes to the procedural one
(200 forks per arm) and 1-2 minutes to a subset;
`--ablation-arms needs,kin_roots,placebo` adds the placebo arm (half as
much again). Needs method 7 and cohort method 4 replace methods 6 and 3, so
comparing with an older report gives `rebaseline_required`. See
`docs/integration/ablation-oracles.md`.

## Continuing on another machine

Fetch the continuation, create a personal branch from its current remote SHA,
and inspect the ledger before changing code. Record platform, interpreter,
source identity, commands, passes/skips and unrun gates. Preserve unsupported
platform failures and fail-closed persistence behavior. Do not publish run data,
credentials or private evidence packages with source changes.
