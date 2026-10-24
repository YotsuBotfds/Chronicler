# Chronicler agent guide

Read `docs/CONTINUATION.md` and `docs/DEVELOPMENT.md` before changing code.
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
