# Audit Crossreference - GPT-5 vs Opus 4.6 - 2026-03-31

Source docs:
- `docs/superpowers/audits/audit-gpt-5-2026-03-31.md`
- `docs/superpowers/audits/audit-opus-4.6-2026-03-31.md`

## Bottom Line

The two audits strongly agree on the main conclusion:
- do repo-hardening before `M60a`
- architecture is fundamentally sound
- the current green test/build surface overstates repo health

They differ mostly in emphasis:
- **GPT-5 audit** is stronger on workflow integrity, hidden red surfaces, validation fail-open behavior, viewer contract drift, and a few concrete action/economy bugs
- **Opus audit** is stronger on simulation-subsystem dead-wiring, religion/ecology correctness, and broader inventory of political/performance debt

## Strong Overlap

### 1. Politics/Diplomacy has real dead or partially dead systems

Both audits independently flag the politics stack as a pre-`M60a` risk.

Common themes:
- `war_start_turns` bookkeeping is broken or incomplete
- vassalization/federation behavior is not actually live the way the design suggests
- politics logic is duplicated across Python, Rust, and glue code

Combined read:
- GPT-5 caught the direct bug that ordinary wars never initialize `war_start_turns`
- Opus extends that into the larger diagnosis that federation defense is dead, vassalization never fires, and governing-cost stability is effectively zero

Verdict:
- this is a real cluster, not a one-off

### 2. FFI / bridge complexity is now a major risk surface

Both audits call out the Python/Rust boundary as too fragile for the next milestone jump.

Common themes:
- `ffi.rs` is too large
- politics and agent bridge flows have too many representations and too much duplicated mapping
- schema drift can silently degrade behavior

Combined read:
- GPT-5 focuses on correctness at the boundary: missing aggregate rows, promotion identity loss, permissive signal defaults
- Opus focuses on robustness and scale: panic path in `replace_social_edges()`, oversized `ffi.rs`, multiple active translation layers

Verdict:
- this should be treated as a first-class hardening area, not background cleanup

### 3. Main validation surface is misleadingly green

Both audits found “green but not healthy” conditions.

Common themes:
- hidden failing or weakly enforced checks
- docs/workflow drift
- missing fail-closed behavior

Combined read:
- GPT-5 caught the hidden failing `test/` suite, red viewer lint, red clippy pass, inert `--compare`, and fail-open oracle runner
- Opus adds that several important regression tests are weak or hanging, and that some documented workflows/flags are stale

Verdict:
- you cannot trust the default green surface as the sole go/no-go signal anymore

### 4. Viewer health is behind the rest of the repo

Both audits found viewer/tooling debt, even though the viewer is not the active milestone.

Common themes:
- stale docs/tooling
- fragmented loading paths
- missing or weak workflow integration

Combined read:
- GPT-5 focuses on stale bundle fixture, missing `npm test`, stock Vite README, and fragmented loader usage
- Opus adds runtime concerns like malformed WebSocket messages killing processing and blocked live narration

Verdict:
- not the first thing to fix, but enough debt is accumulating that contract cleanup should happen before more viewer-facing schema drift

## High-Value Findings Unique to GPT-5 Audit

These were not prominent in the Opus report and are worth preserving:

1. `TRADE` can grant treasury without an active trade route.
2. Executed action and recorded action can diverge (`WAR` fallback still recorded as `war`).
3. `--compare` is effectively inert unless paired with `--analyze`.
4. Validation is fail-open in a way that can make automation report success when validation did not really run correctly.
5. The hidden `test/` tree is excluded by default but still contains direct tests for live codepaths.
6. Viewer lint is red even though tests/build pass.
7. The committed viewer fixture is stale relative to the Python bundle contract.
8. `execute_run()` resume path does not preserve memories the same way CLI resume does.
9. The pure-Python economy oracle crashes on valid barren regions.
10. Black-market leakage only checks the first controlled region.

These are especially useful because they are concrete, reproducible, and mostly small-to-medium fix scope.

## High-Value Findings Unique to Opus Audit

These were not prominent in the GPT-5 report and should be added to the merged priority list:

1. Positive event gains routed as `guard-shock` can penalize agents instead of helping them.
2. `replace_social_edges()` has a positional `.unwrap()` panic path in FFI.
3. Schism conversion is dead-wired.
4. Martyrdom boost decay is never called.
5. Martyrdom applies to all deaths, not persecution-specific deaths.
6. Rewilding is structurally impossible because the threshold conflicts with Rust terrain caps.
7. Federation defense is defined but never wired into production war flow.
8. Governing-cost stability is always zero because of `int(0.5)`.
9. War frequency remains massively above target and should probably be fixed before stacking `M60a` on top.
10. Several religion/culture/politics systems are present in code but still effectively narrative-only or dead-wired.

These matter because they suggest the simulation is currently missing intended behavior, not just carrying cleanup debt.

## Where Opus Looks Stronger

Opus appears stronger on:
- religion/culture subsystem correctness
- ecology correctness
- political system dead-wiring inventory
- broad performance hotspot inventory
- dead code / deprecated code inventory

If you are triaging subsystem realism, I would trust those parts of the Opus audit heavily.

## Where GPT-5 Looks Stronger

GPT-5 appears stronger on:
- validation/CLI workflow correctness
- hidden failing surfaces
- viewer contract/tooling drift
- cross-stack operational trustworthiness
- a few concrete action/economy correctness bugs

If you are triaging “can we trust our green checks and operator workflows,” I would trust those parts heavily.

## Combined Priority Order

### Priority A: Fix behavior that is wrong every turn

Merged from both audits:
- positive `guard-shock` routing bug
- `TRADE` without real route
- action recorded differently from action executed
- missing `war_start_turns`
- federation defense not wired
- governing-cost stability always zero
- zero-agent controller civs omitted from aggregate writeback
- promotion civ/origin identity loss across FFI
- unfinished severity-multiplier sweep

### Priority B: Fix dead-wired systems before adding new ones

- vassalization path never firing
- schism conversion not consumed
- martyrdom decay not wired
- martyrdom filtering wrong
- rewilding impossible
- any other “implemented in docs/spec, inert in runtime” political/religious/ecology behaviors

### Priority C: Make validation honest

- fail closed on invalid/missing oracle names
- non-zero exit codes for failed validation
- fix `--compare`
- decide and document whether `--batch --parallel` can narrate
- decide the fate of the hidden `test/` tree
- fix/redesign hanging or trivially weak regression tests

### Priority D: Restore toolchain hygiene

- viewer lint green
- real `npm test`
- decide whether clippy is advisory or required
- regenerate viewer contract fixture
- add contract tests between Python bundle output and viewer loader

### Priority E: Pre-`M60a` design debt tranche

- split `ffi.rs`
- reduce politics source-of-truth duplication
- split `AgentBridge`
- split `validate.py`
- replace transient `world._*` scratch channels with typed phase outputs/contexts

## Net Recommendation

If I merge both audits into one go/no-go call:

- **Do not start `M60a` yet**
- Take a focused hardening pass first
- Start with the behavior bugs and dead-wired systems, then lock validation/tooling honesty, then do the minimum architectural splits needed to keep `M60a` from compounding drift

## Suggested Minimum Acceptable Pre-`M60a` Bar

1. Green:
- `pytest tests`
- viewer tests
- viewer lint

2. Honest workflow behavior:
- validation fails closed
- `--compare` works or is removed
- hidden `test/` decision made

3. Critical runtime correctness fixed:
- positive `guard-shock` routing
- route-gated trade
- action-history mismatch
- war start bookkeeping
- federation defense wiring
- zero-agent aggregate writeback
- promotion identity bridge

4. At least one dead-wired political path and one dead-wired religion/ecology path repaired before stacking more milestone logic on top

That would leave the repo in a much safer place to begin `M60a`.
