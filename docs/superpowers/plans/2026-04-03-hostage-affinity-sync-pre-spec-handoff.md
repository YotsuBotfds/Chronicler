# Hostage Affinity Sync Pre-Spec Handoff

> Date: 2026-04-03
> Purpose: fast context pack for Spec B, covering the remaining hostage lifecycle gap where Rust agent civ affinity can diverge from Python ownership.

## Status Snapshot

- There is no dedicated spec or implementation plan for this work yet.
- The original deferred item was "hostage capture/release never syncs Rust agent civ affinity."
- The live code is now in an in-between state:
  - `capture_hostage()` contains optional Rust sync logic
  - current war callsites do not pass the `bridge`, so that logic is effectively dormant
  - `release_hostage()` has no bridge input and does not sync at all

Inference:

- this is no longer a single missing line
- it is a small lifecycle-contract decision about how hostage transfers should interact with the existing Python/Rust civ-sync seam

## Recommendation Context

My recommendation is:

- write a short spec for the full hostage civ-affinity lifecycle
- cover both:
  - capture
  - release
- keep it scoped to Python plus existing FFI calls

Reason:

- if the spec only mentions release, capture remains half-wired because the existing sync path never fires
- if the spec only mentions callsite plumbing, it may miss the repository-wide pattern that many other civ-transfer sites already use `world._agent_bridge` or explicit `bridge._sim.set_agent_civ(...)`

## What The Docs Currently Say

Primary references:

- `docs/superpowers/plans/2026-04-03-reaudit-remediation-plan.md`
- `docs/superpowers/plans/2026-04-03-full-audit-remediation-plan.md`
- `docs/superpowers/progress/phase-6-progress.md`

Current verified repo state:

- the re-audit deferred note is directionally correct
- some older descriptions say capture/release both never sync; the live code has progressed beyond that, but only partially
- there is no Rust schema change involved here
- the only Rust-facing operation needed is the existing `set_agent_civ()` FFI call

## Current Code Reality

### The world already knows its bridge

`AgentBridge.__init__()` stores a back-reference on `world._agent_bridge`.

That means the runtime already has two viable patterns available:

- explicit `bridge` parameter threading
- local `bridge = getattr(world, "_agent_bridge", None)` lookup

The spec should choose one and use it consistently.

### Capture path: sync logic exists, but callers do not activate it

`capture_hostage()` in `src/chronicler/relationships.py` already accepts:

- `bridge=None`

and already attempts:

- `bridge._sim.set_agent_civ(youngest.agent_id, winner_civ_idx)`

But the decisive-war callsites in `src/chronicler/action_engine.py` call:

- `capture_hostage(civ, defender, world, contested_region=...)`
- `capture_hostage(defender, civ, world, contested_region=...)`

with no `bridge`.

Important consequence:

- the existing capture sync code is dead in normal gameplay

### Release path: still no sync seam at all

`tick_hostages()` currently advances hostages and calls:

- `release_hostage(gp, civ, origin, world, acc=acc)`

`release_hostage()`:

- clears hostage state
- moves the GP back to the origin civ
- sets `gp.civilization`
- sets `gp.region`
- routes the treasury ransom through the accumulator when present

It does **not**:

- accept `bridge`
- resolve `world._agent_bridge`
- call `set_agent_civ()` for the returned GP

### Other civ-transfer paths already sync Rust affinity

This matters because hostage handling is now an outlier.

Elsewhere, civ-transfer logic already updates Rust affinity during:

- conquest transitions
- exile return / migration-related transfers
- restoration
- absorption
- polity op application

Inference:

- the spec should frame hostage sync as restoring consistency with the repo's broader named-character transfer contract

## Real Design Question

The hard part here is not "which Rust API do we call?"

It is:

- where should the bridge lookup live?

## Two Plausible Contract Shapes

### Option A: explicit bridge plumbing

Pattern:

- keep `capture_hostage(..., bridge=None)` as the public contract
- add `bridge=None` to `tick_hostages()`
- add `bridge=None` to `release_hostage()`
- callsites resolve `bridge = getattr(world, "_agent_bridge", None)` and pass it explicitly

What changes:

- war resolution passes the bridge into `capture_hostage()`
- simulation Phase 2 passes the bridge into `tick_hostages()`
- `tick_hostages()` forwards it to `release_hostage()`
- `release_hostage()` calls `set_agent_civ(agent_id, origin_idx)` after moving the GP back

Pros:

- explicit and easy to test
- matches the current partial `capture_hostage(..., bridge=None)` API
- keeps bridge ownership visible at the seam instead of hidden inside helper code

Cons:

- slightly more callsite churn

### Option B: internal world lookup

Pattern:

- `relationships.py` resolves `bridge = getattr(world, "_agent_bridge", None)` internally
- public signatures stay smaller

Pros:

- smallest caller diff
- consistent with other modules that already consult `world._agent_bridge`

Cons:

- more implicit
- easier to miss in tests or future helper reuse
- capture already exposes a `bridge` param, so this would partially change direction rather than finishing the current one

## My Recommendation

I would spec **Option A**.

Reason:

- the code has already started down the explicit-bridge route for capture
- finishing that pattern is cleaner than switching midstream to hidden lookup
- the work stays small:
  - two war callsites
  - one simulation callsite
  - two function signatures
  - one release-time `set_agent_civ()`

## Important Behavioral Details To Lock Down

### 1. Capture and release should both no-op safely when no bridge exists

This must remain safe for:

- `--agents=off`
- lightweight unit tests
- any Python-only path without a live `AgentBridge`

### 2. Synthetic hostages still need a policy

`capture_hostage()` can synthesize a new hostage when the losing civ has no candidate GP.

That synthetic hostage may have:

- no `agent_id`

The spec should say explicitly:

- no `set_agent_civ()` call is attempted when `agent_id is None`

### 3. Release must sync to the origin civ, not the captor

On normal release, the Python-side ownership changes back to the origin civ.

The Rust sync target should be:

- the origin civilization index

not:

- the captor civ
- the current region controller

### 4. Extinction/orphan release should stay as-is unless intentionally widened

When origin is extinct or missing, the current behavior is:

- clear hostage state
- retire in place with the captor civ

The spec should decide whether Rust sync is also required in that path.

My recommendation:

- yes, if a bridge exists and the GP has an `agent_id`, sync to the civ that now owns the character in Python

Reason:

- the invariant should be "Rust affinity matches Python `gp.civilization` after hostage lifecycle changes"
- not "sync only on the happy-path release"

## Current Test Anchors

Useful existing tests:

- `tests/test_relationships.py`
  - capture behavior
  - auto-release behavior
  - direct release behavior
- `tests/test_audit_batch_e.py`
  - extinct/missing-origin cleanup regressions
- `tests/test_agent_bridge.py`
  - multiple stubs already assert `set_agent_civ()` calls for other civ-transfer paths

What new coverage will probably matter once the spec becomes a plan:

- capture path actually calls `set_agent_civ()` when war callsites pass a bridge
- release path calls `set_agent_civ()` with the origin civ index
- extinct-origin release syncs to the captor/holder civ if the spec chooses that invariant
- no-op behavior when:
  - bridge is absent
  - `agent_id` is absent
  - target civ lookup fails

## Recommended Spec Shape

If the next agent wants a tight deliverable, I would aim for:

1. one short lifecycle statement:
   - "Rust civ affinity must match Python GP ownership after hostage capture/release"
2. one design choice section:
   - explicit bridge plumbing vs internal `world._agent_bridge` lookup
3. one caller map:
   - decisive war capture callsites
   - Phase 2 `tick_hostages()` callsite
4. one edge-case section:
   - synthetic hostages
   - extinct origin
   - no-bridge mode
5. a narrow test strategy section built on existing `test_relationships.py` anchors

## My Recommended End State

The smallest durable contract is:

- keep the explicit `bridge` pattern
- pass `bridge` into both capture and release lifecycles
- make release-time sync mirror capture-time sync
- preserve safe no-op behavior when there is no bridge or no agent id
- define the invariant in terms of Python ownership:
  - after any hostage lifecycle transition, if the GP is agent-backed and a bridge exists, Rust affinity should match the civ that now owns the GP in Python

That keeps Spec B genuinely small while closing the actual contract gap instead of only one visible symptom.
