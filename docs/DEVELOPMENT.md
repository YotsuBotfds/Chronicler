# Development setup

Use a fresh clone to avoid overwriting preserved work. All source and tests are
in Git; machine-specific environments and historical evidence packages are not
required to edit this branch.

```sh
git clone --branch main https://github.com/YotsuBotfds/Chronicler.git
cd Chronicler
git status --short --branch
```

## Python environments

Development uses two virtual environments. `.venv` is the no-native lane: it
must not contain `chronicler_agents` while you run the no-Rust or offline
lanes. Build the Rust extension into a separate native venv,
`CHRONICLER_NATIVE_VENV` (default `~/.venvs/chronicler-native`;
`%USERPROFILE%\.venvs\chronicler-native` on Windows). `maturin develop`
installs into `VIRTUAL_ENV`, or into `./.venv` when none is set, so always
build with the native venv active. For the 16-core workstations (9950X, 3950X), see
[workstations.md](workstations.md): it covers WSL2 layout, threads, the identity matrix
and running the validation gate locally.

`bash setup.sh --native-venv` (Mac, Linux, Git Bash) and
`setup.bat --native-venv` (Windows Command Prompt) set both up. Without
`--native-venv` the scripts keep the end-user layout: one `.venv` with the
extension built into it, so `chronicler --agents hybrid` runs there; that
`.venv` is not a no-native lane until `uv sync --frozen` (or
`setup --no-rust`) removes the extension again. With [uv](https://docs.astral.sh/uv/) on PATH they run
`uv lock --check` and install `.venv` exactly from `uv.lock` with
`uv sync --frozen` (the `dev` group, plus `--extra api`/`--extra gemini` for
`--api`/`--gemini`), as CI does. An exact sync also uninstalls packages the lock
does not list, including a `chronicler_agents` left in `.venv` by an older
setup. Without uv they warn and fall back to an unlocked
`pip install -e . pytest pytest-asyncio`, with whatever versions the index
serves that day, and uninstall `chronicler-agents` from `.venv` explicitly.
Install uv for a reproducible environment. Unless `--no-rust` is given or
`cargo` is missing, setup then installs maturin and builds a fresh release
extension into `.venv`, or with `--native-venv` syncs the native venv the same
way (removing the previous build) and builds into it. It finishes with
`scripts/check_python_env.py --expect native` on the venv it built into and
`--expect no-native` on `.venv` whenever `.venv` should be extension-free, and
fails if a check fails. `CHRONICLER_PYTHON` picks the interpreter (default: the first
3.13+ of `python3.13`, `python3` and `python`; `setup.bat` uses `python`), and
`UV_PROJECT_ENVIRONMENT` moves `.venv`. The native venv's editable install
points at the last checkout that synced it, so give each checkout its own
`CHRONICLER_NATIVE_VENV`.

`scripts/check_python_env.py` reports the interpreter and venv, whether
`chronicler` resolves to this checkout's `src/` and has its console script, and
whether `chronicler_agents` is importable, from where, and the SHA-256 of its
compiled file. `--expect no-native` never imports it; `--expect native` imports
it and requires the compiled `chronicler_agents.chronicler_agents` submodule and
real `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` classes. It
exits 1 on any mismatch; run it with the interpreter you are checking (from a
worktree whose venv belongs to another checkout, with `PYTHONPATH=src`).

| Path | Interpreter | `.venv` dependencies | Native extension | Viewer |
| --- | --- | --- | --- | --- |
| `setup.sh` / `setup.bat`, uv present | see above | `uv lock --check`, `uv sync --frozen` | fresh `maturin develop --release --locked` into `.venv`, or the native venv with `--native-venv`; none with `--no-rust` | not installed |
| `setup.sh` / `setup.bat`, no uv | see above | unlocked `pip install -e .` | the same, with pip-built venvs | not installed |
| `scripts/cloud_setup.sh` | `python3.13` | `uv lock --check`, `uv sync --frozen` | native venv synced with maturin, nothing built | `npm ci` |
| CI (`tests.yml`) | setup-python 3.13 / 3.13.17 | `uv lock --check`, `uv sync --frozen` | `maturin build` wheel installed into the job's own fresh `.venv` | `npm ci`, Node 20.19.0 |

## Python on Windows

Use Python 3.13 or newer. `setup.bat --no-rust` is the scripted form. By hand,
in PowerShell:

```powershell
uv sync --frozen --python 3.13
.\.venv\Scripts\python.exe scripts/check_python_env.py --expect no-native
.\.venv\Scripts\python.exe scripts/run_python_oracle_checks.py
.\.venv\Scripts\python.exe -m chronicler.main --seed 42 --turns 20 --agents off --simulate-only --output output/smoke/chronicle.md
```

Without uv, replace the first line with the unlocked
`py -3.13 -m venv .venv` and
`.\.venv\Scripts\python.exe -m pip install -e . pytest pytest-asyncio`.
Substitute an installed newer Python version if necessary. Do not reuse an
unrelated virtual environment for native qualification. The simulation-only
smoke command needs no narration credential. `--agents off` alone does not
guarantee no native ecology/politics execution if an extension is installed.
The guarded test command explicitly enforces the Python oracle lane.

## Python on Mac or Linux

`bash setup.sh --no-rust` is the scripted form. By hand:

```sh
uv sync --frozen --python 3.13
.venv/bin/python scripts/check_python_env.py --expect no-native
.venv/bin/python scripts/run_python_oracle_checks.py
.venv/bin/python -m chronicler.main --seed 42 --turns 20 --agents off --simulate-only --output output/smoke/chronicle.md
```

Without uv, replace the first line with the unlocked
`python3.13 -m venv .venv` and
`.venv/bin/python -m pip install -e . pytest pytest-asyncio`.

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
The standard CI Viewer job runs tests, lint, and the production build on Node
20.19.0 so changes are checked at the supported floor. From `viewer/`:

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

## Live sessions and exact checkpoints

`--live` serves the viewer over a local WebSocket that accepts only the
viewer origins and the session token in the link the CLI prints
(`--live-port 0` takes a free port). `--checkpoint-every N` writes exact
resume checkpoints in single, batch, fork, interactive and live runs, and
`--resume FILE` continues one byte for byte. `--live --resume FILE`
continues any exact checkpoint as a live session: viewers see the saved
history, and it starts paused at the checkpoint's turn. In a live session
the pause panel's **Save checkpoint** (the `checkpoint` message, which
names no file) writes `live_checkpoints/turn_<turn>.ckpt` under the output
directory at the next turn boundary; `inject` and `set` are recorded in
the checkpoints that follow. `--live --simulate-only` makes no LLM calls.
`--interactive` pauses do the same with commands typed in the terminal,
and `--interactive --resume FILE` continues an exact checkpoint as an
interactive session, paused first at its turn. See
`docs/integration/checkpoint-continuation.md` (section 11 for live and
interactive sessions); `scripts/checkpoint_identity.py` has live and
interactive cases (`live_*`, `interactive_*`), and
`viewer/scripts/qa-live-checkpoint.mjs` is an opt-in browser check of the
pause panel's Save checkpoint and `--live --resume`.

The lobby message carries `feature_catalog`, which lists the experimental
livelihoods switches, their prerequisites and their dependencies. Batch Lab
and the setup form use it to offer them, with nothing selected by default.
The server refuses an invalid `features` request (`start` or
`batch_start.config`) before anything starts. When adding a livelihoods
switch, declare its requirements in `feature_catalog.REQUIREMENTS`;
`tests/test_feature_catalog.py` checks them against the run's own checks.
See `docs/integration/feature-options.md`.

## Native and full qualification

For native development, build into the native venv rather than `.venv`, with
an appropriate Rust toolchain (`bash setup.sh --native-venv` does the first
four steps):

```sh
NATIVE=${CHRONICLER_NATIVE_VENV:-$HOME/.venvs/chronicler-native}
UV_PROJECT_ENVIRONMENT=$NATIVE uv sync --frozen --python 3.13
uv pip install --python "$NATIVE/bin/python" "maturin>=1.5,<2"
VIRTUAL_ENV=$NATIVE "$NATIVE/bin/python" -m maturin develop --release --locked --manifest-path chronicler-agents/Cargo.toml
"$NATIVE/bin/python" scripts/check_python_env.py --expect native
cargo test --locked --manifest-path chronicler-agents/Cargo.toml
```

Before native Python tests, verify `chronicler_agents.chronicler_agents` resolves
to a compiled extension and `AgentSimulator`, `EcologySimulator`, and
`PoliticsSimulator` are real classes (`check_python_env.py --expect native`
does this and prints the extension's SHA-256). The in-process verification and
full-suite commands are in `README.md` and `.github/workflows/tests.yml`. Native CI builds
fresh source. A previously installed extension is not evidence for this branch.

Full population/regression qualification remains the explicit validation-profile
workflow and 200-seed gate. PR #69 is merged; its bounded checks do not complete
that scientific gate or authorize experimental default promotion or deployment.

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

The full profile also runs the ablation oracles (`--ablation-oracles`, the
default there and opt-in for a subset; `--no-ablation-oracles` opts out):
the batch writes exact checkpoints at the fork turns (`--checkpoint-turns`),
and each seed is forked with the need terms (`needs`) and the kin roots
(`kin_roots`) switched off for 22 turns, into `ablation_<first seed>`
beside the batch: at every 100th turn in template worlds and every 20th
from turn 100 in procedural worlds (fork design 2, for the power of the
sparse needs pairings). The forks keep only their agent events; the
checkpoints (about 1.2 GB for the template full gate, 4.5 GB for the
procedural one) are removed once forked. On four shared cores the two arms
add about 23-28 minutes to the template full gate (800 forks per arm),
about 45 minutes to the procedural one (900 forks per arm) and 1-2 minutes to a
subset that asks for them; `--ablation-arms needs,kin_roots,placebo` adds
the placebo arm (half as much again). Their verdicts are causal evidence,
reported but not yet required: the gate is decided by the needs oracle's
observational verdict and cohort method 3, as before;
`--require-causal-oracles` makes the ablations decide. Needs method 8 and
cohort method 5 (fork design 2) replace methods 7 and 4, so comparing with
an older report gives `rebaseline_required`; arms of design 1 are still
scored by methods 7 and 4. See `docs/integration/ablation-oracles.md` and
`docs/integration/community-anchoring.md`.

Community method 2 keeps method 1's result as its legacy component, which
decides, and reports M53 oracle 1 as the spec states it as its spec
component: communities found over friend, co-religionist and kin edges
weighted by sentiment within a region (native bond codes from
`chronicler.ffi_constants.BOND_TYPES`), judged by the spec's count, size
and region-share criteria (`validation_gate.COMMUNITY_SPEC_REQUIRED`, off).
Cohort method 6 is method 5 with those communities as the members of every
component (observational, kin roots, placebo, community anchor). Both
replace community method 1 and cohort method 5 in a comparison
(`rebaseline_required`); `run_community_oracle(..., method_version=1)` and
`run_cohort_oracle(..., method_version=5)` re-score the old methods. See
`docs/integration/spec-communities.md`.

`--community-anchoring` (default off) lets community ties hold agents
back from moving (`docs/integration/community-anchoring.md`); the gate
runner forwards it and then also forks the `community_anchor` arm.

`--domestic-credit` (default off; needs `--finance` and an agent pool)
makes the realm's merchant agents, guilds and cities the domestic lenders:
they fund the state's domestic loans from their wealth, receive the
interest and repayments and lose what a default writes off
(`docs/integration/domestic-credit.md`). Lenders lend no new money that
would raise the borrower's interest due above half its revenue, and while
the agent pool's wealth builds up from its cold start the realm's abstract
merchant houses lend finance's revenue term, fading as `0.98 ** turn`
(section 13 there). The gate runner forwards it to the agent-mode runs;
`CHRONICLER_CHECK_RESOURCES=1` also checks its books.

## Before refactoring, moving or deleting files

Several tests pin repository content, so a change that looks mechanical can
fail far from the file you touched. Run the read-only preflight first:

```sh
.venv/bin/python scripts/refactor_preflight.py src/chronicler/utils.py tests/test_foo.py
.venv/bin/python scripts/refactor_preflight.py --move scripts/a.py:scripts/tools/a.py
.venv/bin/python scripts/refactor_preflight.py --git-diff origin/main   # every changed path
```

It reports four levels per path (`--json` for tooling, `--fail-on-enforced`
to exit 1 on a pin):

- **enforced:** a known check fails when the bytes change or the path moves
  (workflow byte copies, shard and oracle-chunk ownership, the frozen witness
  snapshot). Source witnesses are no longer enforced pins on the working tree.
- **digest:** the file's current SHA-256 or Git blob id appears in test data;
  treat it as pinned until you have read the test.
- **reference:** tests, witnesses, workflows, importers or docs name the path
  or module; read each hit.
- **historical:** an older recorded hash (performance and reference-baseline
  provenance), or a source witness verified against the file's frozen copy
  ("frozen source witness"). Neither pins the current file; never rewrite it
  to match.

Each report also prints `identity gate:` with the cases that execute the path
(from `tests/fixtures/identity/coverage.json`), or `NO IDENTITY CASE` when only
tests, or nothing, guard it.

It always prints what it cannot see (runtime-built paths, `inspect.getsource`,
whole-tree digests, behavioral goldens, TypeScript and Rust module graphs). "No
known pins" is not a safety proof; run the lanes above.

The mechanisms it checks:

- **Source witnesses (frozen history).** `scripts/testing/*_witness.py` project
  source back through each reviewed candidate's patches
  (`tests/fixtures/*_source_inverse.json`; `grain_release_witness.py` embeds its
  own layers) and compare hashes at every step. Since DEC-1 option A
  (2026-11-08) the witness tests read the 91 witnessed files from
  `tests/fixtures/frozen_pin_sources/` (via `scripts/testing/frozen_sources.py`),
  byte copies of `main` c3d752fa (tag `pin-freeze-2026-11`), not from the
  working tree. Editing a witnessed source no longer breaks a chain and needs no
  inverse layer; `reviewed_main_witness.py` and the livelihoods layers are now
  history. Never edit, re-hash or regenerate the fixtures, the copies or their
  `MANIFEST.json`: `tests/test_refactor_preflight.py` checks every copy against
  the manifest, and `scripts/testing/freeze_pin_sources.py --verify` (full
  clone) checks the copies against the freeze commit. Behaviour is guarded by
  the identity gate below instead.
- **Workflows.** `docs/workflows/native-two-shards*.yml.in` must stay
  byte-identical to `.github/workflows/`, and `tests/test_native_ci_shards.py`
  records the workflow's SHA-256. `tests/test_native_build_lanes.py` reads
  `tests.yml` and parts of `README.md`. The benchmark scripts hash their workflow
  files into receipts.
- **Test-module ownership.** Every test module must be in exactly one shard of
  `scripts/testing/native_shards_manifest.json`, which also lists expected
  skipped node IDs and the successful-subtest count (623). A new module also
  goes into the `additions` map and module count in
  `tests/test_native_ci_shards.py`, and, if it is offline-safe, into a chunk of
  `scripts/run_python_oracle_checks.py` with headroom.
- **Import compatibility.** `tests/test_import_compatibility.py` and the
  re-export blocks (for example in `politics.py` and `validate.py`) keep
  historical import paths working; an unused-looking import may be one of them.
  Tests also monkeypatch module attributes by string target, so moving a helper
  can silently disconnect a patch.
- **Script paths.** Tests import scripts as `scripts.<name>` or load them by
  path, and workflows call them by path (see [scripts/README.md](../scripts/README.md)).

Evidence JSON under `docs/` records hashes and paths as they were; leave it
byte-for-byte unchanged when moving the files it names.

### Identity gate

`.github/workflows/identity-gate.yml` runs on pull requests that touch
`src/chronicler/`, `chronicler-agents/src/`, `scripts/turn_speed_identity.py`
or `tests/fixtures/identity/`, and weekly. Each lane runs its cases with
`scripts/turn_speed_identity.py run`, then `check` compares the output digests
with the committed goldens in `tests/fixtures/identity/`:

| Lane | Case | Switches |
| --- | --- | --- |
| python | `g_off_s42` | seed 42, 120 turns, `--agents off` |
| python | `g_off_proc_s7` | seed 7, 100 turns, 48 regions, 10 civs, `--agents off` |
| python | `g_batch_off` | `--batch 3`, seed 100, 40 turns, `--agents off` |
| native | `g_hybrid_s42` | seed 42, 100 turns, hybrid, validation sidecar |
| native | `g_grain_s7` | seed 7, 120 turns, hybrid, grain reserves and storage (`maintain`, work budget 1), public grain shipments, harvest forecasts, transaction receipts |
| native | `g_learning_s42` | seed 42, 120 turns, 24 regions, 6 civs, hybrid, scholarship, academy services |
| native | `g_mobility_s1234` | seed 1234, 100 turns, hybrid, household mobility (liquid requirement 25), community anchoring, capacity-aware refugees |
| native | `g_scaled_s42` | seed 42, 30 turns, 12 regions, 4 civs, hybrid, validation sidecar, scaled to 18,800 starting agents |
| native | `g_off_s42` | as the python case, with the native ecology simulator |

`check` refuses a native build that is not the checkout's (build receipt) and a
runtime whose Python minor version, platform or Rust channel differs from the
goldens'; a rebuilt extension with identical outputs passes. Locally, gate a
refactor with `check` against the goldens or with `compare` between two
checkouts' `run` directories, plus the oracle lane. The cases run only their
listed switches: the preflight's `identity gate:` line shows which cases reach a
file, and code reached only through other flags still needs its tests.

An intended outcome change (a correction) updates the goldens in its own PR:
capture them with the workflow's `capture` input, commit them unmodified, and
record the before/after differences and a CONTINUATION entry. Never edit a
golden by hand, and never mix a golden update into a refactor.

## Claude Code cloud sessions

The cloud container already provides Python 3.13, uv, Node 22, npm and a
stable Rust toolchain. The environment's setup script only needs:

```sh
bash Chronicler/scripts/cloud_setup.sh
```

It installs the locked `.venv` (offline/no-Rust lane), `viewer/node_modules`
and the Cargo downloads, and prepares a separate native venv at
`~/.venvs/chronicler-native` (dependencies and maturin, no extension) in
about 10 seconds. It does not build the extension: native work needs a fresh
build of the branch under test anyway. Build into the native venv with
`VIRTUAL_ENV` set; without it, `maturin develop` installs into `./.venv` and
breaks the lanes that require `chronicler_agents` to be absent:

```sh
VIRTUAL_ENV=$HOME/.venvs/chronicler-native $HOME/.venvs/chronicler-native/bin/python \
  -m maturin develop --release --locked --manifest-path chronicler-agents/Cargo.toml
$HOME/.venvs/chronicler-native/bin/python scripts/check_python_env.py --expect native
```

The script ends by running `scripts/check_python_env.py --expect no-native` on
`.venv` and a report-only check on the native venv; like its other steps, a
failed check prints `!!` and setup continues.

Observed on a 4-core cloud container (2026-11-04): bounded offline lane
about 4 minutes, viewer tests/lint/build about 2 minutes, `cargo test` about
1.5 minutes, native release build 2-3 minutes.

## Continuing on another machine

Fetch `main`, create a personal branch from its current remote SHA,
and inspect the [recovery/archive index](RECOVERY.md) and continuation ledger
before changing code. Record platform, interpreter,
source identity, commands, passes/skips and unrun gates. Preserve unsupported
platform failures and fail-closed persistence behavior. Do not publish run data,
credentials or private evidence packages with source changes.

## Durable Python qualification evidence

`scripts/python_qualification.py` runs a fixed full pytest lane against an
explicit clean source SHA, interpreter and native binary SHA (or verified
native absence), with fresh external output, atomic receipts and JUnit/logs.
Linux detached mode and cooperative before/after-pytest controls retain
execution evidence when a launching shell exits. Partial or interrupted lanes
never earn a pass. See
[the preregistered protocol and usage](integration/python-qualification-supervisor.md).
`cancel-before-tests --output PATH --reason TEXT` can stop only a verified
Linux worker acknowledged before pytest, using a pidfd and immutable cancellation
evidence. It refuses a running pytest process; cancellation is never a test pass.
The full focused suite requires local Git and real subprocesses; its OS/process
cases remain outside the bounded offline guard. Registered pure rejection and
parser cases run in the existing `qualification-tools` chunk.

## Lossless copies of parent extras

`scripts/archive_parent_extras.py` archives one finalized parent's narrowly
allowlisted state/memory JSON into a fresh external destination, performs an
actual restore into another fresh directory, and verifies byte hashes. Explicit
manifest/index hashes, input/output bounds and unchanged protected validation
inputs are required. See [the storage protocol](integration/parent-extra-archive.md).
There is no raw deletion API. Wait for the official gate and its forks to finish
before archiving a cohort; focused synthetic tests do not qualify a live cohort.
