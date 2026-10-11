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

The guarded runner writes its selected node IDs, interpreter, source-file hashes,
guard receipt, exit status and output under ignored `output/python-oracle/`.
It excludes the two cross-process determinism/replay cases and broader
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

## Continuing on another machine

Fetch the continuation, create a personal branch from its current remote SHA,
and inspect the ledger before changing code. Record platform, interpreter,
source identity, commands, passes/skips and unrun gates. Preserve unsupported
platform failures and fail-closed persistence behavior. Do not publish run data,
credentials or private evidence packages with source changes.
