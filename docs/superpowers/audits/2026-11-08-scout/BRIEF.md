# Shared scout brief (read this first)

You are one of 32 parallel read-only scouts auditing the Chronicler repository at
`the repository root` (branch `claude/relaxed-brown-4ozgeg`, identical to `main` @ `c3d752fa`,
2026-11-08). Your area is in your prompt; other scouts cover the rest, so stay in your lane
except to trace callers and consumers.

## Project

Deterministic civilization-history simulator.

- `src/chronicler/` — Python package, ~154k lines, 286 modules. `simulation.py` runs a 10-phase
  turn loop; `main.py` is the CLI (`chronicler = chronicler.main:main`).
- `chronicler-agents/` — optional Rust/PyO3 agent crate (~56k lines): agents, ecology, politics.
- `viewer/` — React/TypeScript viewer (~64k lines).
- `tests/` (~221k lines, 477 files), `scripts/` (~150 scripts), `docs/` (40 MB, mostly dated
  evidence written by earlier AI leads).

Successive AI "leads" added many experimental, default-off CLI systems in a "connected-world"
program: livelihoods and trade, watersheds and infrastructure, public health, institutions and
war, stories and evidence. The latest held evaluation (144 runs) found the full connected-world
configuration worsened food shortfall in 11 of 12 worlds and raised recorded epidemic deaths in
9; it stays off by default. The last lead confirmed an "attribution-to-health coupling", added a
corrected opt-in mode, and fixed a problem in "adaptive controls".

The owner now wants a **grand, broad, wide and detailed simulation**, and wants to know what needs
doing: dead code, flaky or fragile systems, refinement, and where the simulation is thin.

## Project contracts (AGENTS.md) — do not recommend breaking them

- The simulation decides outcomes deterministically; narration only describes.
- Preserve aggregate snapshot/RNG behaviour, serialization and historical import compatibility.
- Respect accumulator categories (`keep`, `guard`, `guard-action`, `guard-shock`, `signal`), enum
  declaration order and the capped action-weight modifiers.
- Region identity = its index in `world.regions`; civ identity = its index in
  `world.civilizations`; `civ.regions` holds names.
- Transient Python/Rust signals are cleared before their builder returns.
- Experimental features stay default-off.
- Source-witness fixtures, workflow tests and `scripts/testing/native_shards_manifest.json` pin
  file contents and paths. When you propose deleting or moving a file, grep `tests/` and
  `scripts/testing/` for its path and say whether it is pinned.

## Rules

1. **Read-only.** Do not create, edit, move or delete anything under `the repository root`. Run no
   state-changing git command (no checkout, commit, stash, reset, clean). `git log/show/blame/grep`
   are fine.
2. **CPU is shared** (4 cores, 32 scouts): no full test suites, no `cargo build/test/check`, no
   `npm install/test/build`, no simulation runs — unless your prompt explicitly allows it.
   `rg`/`grep`, reading files and short `.venv/bin/python -c` / scratch scripts are fine.
   Use `.venv/bin/python` (the native extension is not installed there).
3. **Evidence.** Every finding cites `file:line` or a path. Before calling anything dead or unused,
   grep for its name across `src/`, `tests/`, `scripts/`, `chronicler-agents/` and `viewer/`,
   including string dispatch, `getattr`, registries, CLI flag names and serialized field names;
   say what you searched. Distinguish "used only by tests/scripts" from "fully unused". Write
   "unverified" rather than guess. Code beats docs; docs here are often stale.
4. **No session or orchestration tools.** Never call any `mcp__claude-code-remote__*` tool
   (send_message, create_session, archive_session, triggers, environments, …), SendMessage,
   Agent, Artifact, or anything that posts, creates or deletes outside your scratch dir. Your
   final message is how you report back. GitHub MCP tools are allowed only where your prompt
   says so, and only read-only.
5. Put any scratch files under
   `work-<NN>/`.
6. **Deliverable.** Write your full report to
   `<NN>-<slug>.md`,
   then return the same report as your final message.

## Report format (markdown, at most ~1100 words)

```
## <NN> <Area>
**Map** — 3–8 bullets: what lives here, how it plugs into the turn loop/CLI, sizes.
**Findings** — numbered, most severe first, 6–15 real ones, each:
  [high|med|low] [dead-code|bug|flaky|fragile|duplication|complexity|perf|test-gap|sim-depth|docs]
  Title — evidence (file:line) — why it matters — suggested action
**Simulation depth** — 2–5 bullets: concrete ways this area could become broader, deeper or more
  detailed, grounded in what the code does or lacks now.
**Confidence** — one line: what you verified versus inferred.
```

Quality over quantity: a short report of verified findings beats a long list of guesses.

## Owner emphasis (added mid-run)

The owner believes the codebase is bloated and wants it **streamlined**: remove unneeded or buggy
code, consolidate duplication, refactor anything that blocks expansion. So, in addition to the
format above, end your report with a **Streamlining candidates** table:

```
| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
```

Only list candidates you verified with grep. Note when a deletion would remove a CLI flag or a
field that old bundles/checkpoints contain (historical import compatibility).
