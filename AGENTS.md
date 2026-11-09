# Chronicler agent guide

Read [current source and recovery/archive index](docs/RECOVERY.md),
`docs/CONTINUATION.md` and `docs/DEVELOPMENT.md` before changing code;
[docs/README.md](docs/README.md) maps the rest of the documentation.
Start new work from fetched `main`; PR #81 (productive recovery, checkpoint 3, the
integrated chain) merged on 2026-11-06 at `c4c17c98`, completing that phase after PR #80
(checkpoint 2) at `96c20439`, PR #78 (checkpoint 1) at `dde5c004` and PR #76 (recovery
skills) at `c4e259b6`. The
default-off livelihoods, recovery-skills and productive-recovery packages and their
boards are under `docs/superpowers/` (`livelihoods-*`, `recovery-skills*`,
`productive-recovery*`).
Older branch instructions and machine paths are dated historical evidence.
In Claude Code cloud sessions, `scripts/cloud_setup.sh` installs dependencies;
build native extensions only into the separate venv it describes. On a
workstation, use `setup.sh --native-venv` (see [docs/workstations.md](docs/workstations.md)).
The current roadmap is
[docs/superpowers/roadmaps/streamline-and-deepen.md](docs/superpowers/roadmaps/streamline-and-deepen.md).
The current milestone ledger is `docs/superpowers/progress/phase-6-progress.md`;
dated evidence describes the source and platform it actually tested.

## Architecture and contracts

- `src/chronicler/`: deterministic simulation, CLI, narration, analytics and
  detached experiments. The simulation chooses outcomes; narration describes them.
- `chronicler-agents/`: optional Rust/PyO3 agent, ecology and politics runtimes.
- `viewer/`: React/TypeScript viewer. Synthetic demonstration pages are distinct
  from production data loading and supported features.
- Preserve aggregate snapshot/RNG behavior, serialization and historical import
  compatibility. Describe intentional corrections separately from optimizations.
- Respect accumulator categories (`keep`, `guard`, `guard-action`, `guard-shock`,
  `signal`), enum declaration order and the capped action-weight modifiers.
- Region identity is its index in `world.regions`; civilization identity is its
  index in `world.civilizations`. `civ.regions` contains names. Do not invent IDs.
- Clear transient Python/Rust signals before returning from their builder. Add
  multi-turn consumption/reset checks when changing a bridge signal.
- Keep experimental features default-off. Detached governance/session kernels
  do not imply production runtime activation or scientific qualification.

## Working safely

Inspect status, remotes, branches and worktrees first. Preserve dirty and
untracked project source before mutation; work in a fresh clone or isolated
branch. Do not reset, rebase or overwrite another agent's checkout. Reconcile
with fetched `main` without force-push. The preserved desktop foundation line
has competing architecture and must be reviewed separately, not overlaid.

Workflow byte copies, the native shard manifest and oracle-chunk ownership pin
paths and contents; run `scripts/refactor_preflight.py` before refactoring,
moving or deleting files (levels in DEVELOPMENT.md, "Before refactoring").
Source-witness fixtures and `tests/fixtures/frozen_pin_sources/` are frozen
history: they verify the reviewed chains against the sources as of
`pin-freeze-2026-11` (`main` c3d752fa), not the working tree. Never edit,
re-hash or regenerate them, and never rewrite a pinned hash to make a change
pass. Gate refactors with `scripts/turn_speed_identity.py check` (and `compare`
for two-checkout runs) plus the oracle lane.

Keep environments, credentials, personal data, generated runs, private logs and
app/session databases outside commits. Commit source, tests and relevant project
documentation. Update the continuation ledger after material work.

## Verification

Start with focused checks; `python scripts/run_python_oracle_checks.py` reproduces
the bounded offline Python lane. It runs in chunks, each a pytest process with
its own guard and a 110-second limit, and stops at the first failing chunk. The
guard blocks native imports, network and child processes inside pytest and
replaces the two main native runtime factories. Add new tests to a chunk with
headroom or a new chunk; do not raise the limit. Passing it does not qualify
native execution or POSIX session persistence.

For native work, build a fresh extension into the same Python environment,
verify the real compiled submodule/classes, run appropriate Python/Rust tests,
and retain source/build identities. Full milestone qualification requires its
documented 200-seed before/after gate. Viewer changes require tests, lint and
build. Never call an unrun gate complete.
