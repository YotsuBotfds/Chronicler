# CLAUDE.md Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 845-line monolithic `phoebe-session-context.md` with a lightweight `CLAUDE.md` (~150 lines) and a slim companion `phase-6-progress.md`.

**Architecture:** Two files. CLAUDE.md at project root (auto-loaded by Claude Code every session) contains stable architecture reference + a small updatable "Current Focus" section. Phase 6 progress file captures only forward-looking decisions and active gotchas. Everything else is retired to git history.

**Tech Stack:** Markdown files only. No code changes.

**Spec:** `docs/superpowers/specs/2026-03-17-claude-md-migration-design.md`

---

## Chunk 1: File Creation and Verification

### Task 1: Create progress directory and phase-6-progress.md

**Files:**
- Create: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Create the progress directory**

```bash
mkdir -p docs/superpowers/progress
```

- [ ] **Step 2: Write phase-6-progress.md**

Create `docs/superpowers/progress/phase-6-progress.md` with this exact content:

```markdown
# Phase 6 Progress — Living Society

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-03-17

---

## Active Pre-Merge Items

### M36: Cultural Identity (pre-merge, 1 fix needed)

- **`_culture_investment_active` sticky flag:** Set in `resolve_invest_culture()` but never reset. Once a region receives INVEST_CULTURE, flag persists forever, giving perpetual drift bonus. Fix: clear in `build_region_batch()` after reading, or reset at turn start.

### M38a: Temples & Clergy Faction (pre-merge, 2 fixes needed)

1. **Tithe produces float treasury:** `TITHE_RATE * trade_income` is float, `civ.treasury` is int. Causes pydantic ValidationError. Fix: `civ.treasury += int(tithe)` in `factions.py`.
2. **Temple conquest lifecycle is dead code:** `destroy_temple_on_conquest()` and `destroy_temple_for_replacement()` exist but are never called from production code. `handle_build()` blocks ALL temple building in templed regions (including foreign temples). Fix: add faith-aware check in `handle_build`, wire `destroy_temple_on_conquest` into war resolution.

---

## Locked Design Decisions for Upcoming Milestones

### M38b: Schisms, Pilgrimages & Persecution (spec reviewed, plan not written)

- **B-1:** Neutral-axis schisms produce identical doctrines (`-0 = 0`). Fix: when axis value is 0, set to +1/-1 based on trigger context.
- **B-2:** Schism belief reassignment has one-turn delay (Phase 10 detection, agent tick already ran). Documented as intentional.
- **G-1:** Spec needs file changes table.
- **G-2:** Spec needs `--agents=off` section — all three subsystems depend on agent snapshots.
- **G-3:** Pilgrimage pseudocode uses `gp.agent.belief` but `GreatPerson` has `agent_id`, not `agent` ref. Clarify data access path (lookup via snapshot by `agent_id`).
- **G-4:** Trigger 4 needs `last_conquered_turn` on Region — specify default value for existing regions.

### M39: Family & Lineage (design reviewed, spec not written)

1. **Inherit at birth, drift handles assimilation.** Child inherits parent's cultural values and belief. M36 drift and M37 conversion apply normally afterward. No special inheritance flags.
2. **Dead ancestors valid, parent-child only (no grandparent chain).** Skip-a-generation requires pool lookback for non-promoted parents — unreliable when parent dies. `parent_id in named_agents` dict gives O(1) detection.
3. **Purely narrative for M39.** `dynasty_id` on `NamedCharacter` is the hook for future mechanical effects. No simulation coupling in M39.
4. **No seeding, 50-70 turn bootstrap.** Initial agents get `parent_id = PARENT_NONE`. First dynasties ~turn 50-70. Tier 2 regression needs ≥200 turns.
5. **Approach A: Rust owns `parent_id`, Python owns dynasty logic.** `parent_ids: Vec<u32>` in pool, exposed via Arrow column. Dynasty detection via `named_agents` dict lookup. No new FFI functions.

---

## Known Gotchas / Deferred Items

- **`_culture_investment_active` dead code pattern:** `build_region_batch()` in `agent_bridge.py` has cleanup code after `return` (lines after return are dead). Any new system using the same pattern (e.g., M38b schisms) must clear transient state BEFORE the return.
- **M34 farmer-as-miner:** Has forward dependency on M41 wealth dispatch.
- **M44 (API narration):** Free-floating — schedule flexibly between heavy milestones.
- **Viewer extensions (M21-M24, M40):** Tech focus badge, faction influence bar, ecology hover, intel indicator — all deferred to Phase 6 M46.
- **Spec-ahead strategy:** M39 design fully locked. Tier 1 spec-able: M41, M44. Tier 2 (after M38b plan): M45.
```

- [ ] **Step 3: Verify the file exists and looks right**

```bash
wc -l docs/superpowers/progress/phase-6-progress.md
```

Expected: ~65-75 lines.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs: add phase-6-progress.md with forward-looking decisions and active items"
```

---

### Task 2: Write CLAUDE.md

**Files:**
- Create: `CLAUDE.md` (project root)

- [ ] **Step 1: Write CLAUDE.md**

Create `CLAUDE.md` at the project root with this exact content:

```markdown
# Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Seed + scenario + turn count → complete chronicle with wars, famines, cultural renaissances, political collapses, and tech advancement — all emerging from interacting systems, not scripted events.

**Hardware:** 9950X (16C/32T, 192GB DDR5) for simulation, 4090 (24GB VRAM) via LM Studio for local LLM inference. CPU and GPU workloads are fully decoupled. Currently running Qwen 3 235B (A22B MoE) locally at 2-3 tk/s — adequate for batch narration, too slow for live mode demos.

**Codebase:** ~17,500+ lines across 50+ Python files. ~2,300 lines Rust (chronicler-agents crate). React/TypeScript viewer (~3,600 lines) with WebSocket live mode. All simulation is pure Python — the LLM only narrates, never decides. Rust handles agent-level computation via Arrow FFI.

**API narration planned:** Phase 6 (M44) will wire Claude Sonnet 4.6 via API for curated moment narration.

---

## Architecture

### 10-Phase Turn Loop + Agent Tick

```
Phase  1: Environment (climate, conditions, terrain transitions)
Phase  2: Economy (trade routes, income, tribute, treasury)
Phase  3: Politics (governing costs, vassal checks, congress, secession)
Phase  4: Military (maintenance, war costs, mercenaries)
Phase  5: Diplomacy (disposition drift, federation checks, peace)
Phase  6: Culture (prestige, value drift, assimilation, movements)
Phase  7: Tech (advancement rolls, focus selection, focus effects)
Phase  8: Action selection + resolution (action engine)
Phase  9: Ecology (soil/water/forest tick, terrain transitions, famine checks)
--- Agent tick (between Phase 9 and 10) ---
  StatAccumulator routes Phases 1-9 mutations by category (keep/guard/signal)
  Rust tick: satisfaction → decisions → migration → occupation → loyalty → demographics
  Write-back: agent aggregates overwrite civ stats in hybrid mode
  Promotions: named character detection → GreatPerson creation
  Event detection: agent events (rebellion, migration, etc.) → curator pipeline
Phase 10: Consequences (emergence, factions, succession, named events, snapshot)
  Phase 10 guards: acc=None in aggregate mode (direct mutations); acc passed in hybrid mode
```

Each phase reads/mutates a shared `WorldState`. Pydantic models throughout (`validate_assignment=False` — direct mutations).

### Python Key Files (src/chronicler/)

| File | Role |
|------|------|
| `simulation.py` | Core turn loop, all 10 phases, StatAccumulator integration |
| `politics.py` | Governing costs, secession, federation, vassals, proxy wars, twilight, congress |
| `main.py` | CLI entry point, `--agents` flag, argument parsing, run orchestration |
| `action_engine.py` | Action selection with weight modifiers (11 ActionTypes), accumulator routing |
| `emergence.py` | Black swans, severity multiplier, pandemics, terrain succession |
| `analytics.py` | Post-processing extractors, anomaly detection, delta reports |
| `agent_bridge.py` | Rust↔Python bridge, shock/demand signals, write-back, event aggregation |
| `factions.py` | Four factions (military/merchant/cultural/clergy), power struggles |
| `ecology.py` | Coupled soil/water/forest, climate-driven drought, rewilding |
| `accumulator.py` | StatAccumulator class with category routing |
| `models.py` | All Pydantic models |
| `curator.py` | Event selection, causal linking, clustering, role assignment |
| `narrative.py` | NarrativeEngine, era register, NarrationContext, LLM client wrappers |
| `bundle.py` | Bundle assembly |

### Rust Crate (chronicler-agents/src/)

| File | Role |
|------|------|
| `lib.rs` | Module exports |
| `agent.rs` | Constants, Occupation enum, `STREAM_OFFSETS` RNG registry |
| `pool.rs` | SoA AgentPool with free-list arena |
| `ffi.rs` | PyO3 bindings, AgentSimulator, Arrow RecordBatch I/O |
| `region.rs` | RegionState struct |
| `tick.rs` | Multi-phase tick orchestration |
| `satisfaction.rs` | Branchless satisfaction formula with shock/demand/culture/religion terms |
| `behavior.rs` | Decision model: utility-based selection with personality modifiers |
| `demographics.rs` | Age-dependent mortality, ecology-sensitive fertility |
| `named_characters.rs` | Named character promotion tracking |
| `conversion_tick.rs` | Belief conversion per-agent rolls |
| `culture_tick.rs` | Cultural drift per-agent |
| `signals.rs` | CivSignals/TickSignals parsing from Arrow columns |

### ActionType Enum (models.py)

11 action types — **use these exact names, not invented aliases:**

```
EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR, BUILD,
EMBARGO, MOVE_CAPITAL, FUND_INSTABILITY, EXPLORE, INVEST_CULTURE
```

### StatAccumulator (accumulator.py)

4 routing categories at call site, plus `civ_idx` parameter on every call:
- `keep`: apply directly in all modes (treasury, asabiya, prestige)
- `guard`: skip in agent mode — agents produce emergently
- `guard-action`: action engine outcomes → DemandSignals
- `signal`: external shocks → ShockSignals

### Bundle & Feature Flags

**Bundle:** `chronicle_bundle.json` — `world_state`, `history`, `events_timeline`, `named_events`, `chronicle_entries`, `gap_summaries`, `era_reflections`, `metadata` (includes `bundle_version`).

**Flags:** `--agents=off|demographics-only|shadow|hybrid` + `--agent-narrative` + `--narrator=local|api`

### Data Model Gotchas

- `civ.regions` is `list[str]` (names), not `list[Region]` — resolve via `region_map`
- `Region` has no `region_id` field — use index into `world.regions`
- `Civilization` has no `id` field — use index into `world.civilizations`
- `Civilization` has no `alive` field — check `len(civ.regions) > 0`
- `GreatPerson` has no agent-pool fields (belief, occupation, etc.) — lookup via snapshot by `agent_id`
- `build_region_batch()` return-then-cleanup is dead code — clear transient state BEFORE the return

---

## Cross-Cutting Rules

- All negative stat changes go through M18 severity multiplier (except treasury, ecology)
- Combined action weight multiplier cap at 2.5x (traditions x tech focus x factions)
- Each milestone: run 200 seeds before/after, compare distributions, check for regressions
- `--agents=off` produces Phase 4 bit-identical output (regression test)
- Phase 10 receives `acc=None` in aggregate mode
- Bundle format: consumer code doesn't know if stats came from agents or aggregates
- Non-ecological satisfaction penalties capped at -0.40 total (cultural + religious + persecution = budget) [Decision 10]
- RNG stream offsets registered in `agent.rs` `STREAM_OFFSETS` block — any new RNG source needs a unique offset [Decision 11]
- Religion is a fourth faction (clergy), not a value dimension — regression baseline required before wiring [Decision 9]
- Milestone ordering: environment → culture → religion → family (each system needs the prior substrate) [Decision 7]

---

## Session Workflow

- **Phoebe** reviews architecture, specs, and plans. Catches misalignments before implementation.
- **Cici** designs, specs, plans, and implements. Runs on Opus 4.6 with 1M context.
- Phoebe reviews Cici's outputs before implementation starts.
- Implementation plans are written AFTER prerequisite milestones land (so line references are accurate).
- Tuning iterations flag Tate for approval before applying changes and when structural conflicts arise.

---

## Current Focus

Phase 6 — Living Society. Roadmap: `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md`

**Active:** M39 (Parentage & Dynasties) — design Phoebe-reviewed (5 decisions locked), ready for spec
**Pending:** M38a merge (tithe int fix + conquest lifecycle), M38b spec fixes (2 bugs, 4 gaps), M36 pre-merge fix
**See:** `docs/superpowers/progress/phase-6-progress.md`

---

## References

| Path | Contents |
|------|----------|
| `docs/superpowers/roadmaps/` | Phase 2-6 roadmaps |
| `docs/superpowers/specs/` | Design specs (per-milestone) |
| `docs/superpowers/plans/` | Implementation plans (per-milestone) |
| `docs/superpowers/progress/phase-6-progress.md` | Active Phase 6 decisions and gotchas |
| `src/chronicler/` | All Python source |
| `chronicler-agents/src/` | Rust agent crate |
| `viewer/` | React/TS viewer app |
| `tests/` | Python test suite |
| `chronicler-agents/tests/` | Rust integration tests |
```

- [ ] **Step 2: Verify line count**

```bash
wc -l CLAUDE.md
```

Expected: ~145-155 lines (within the ~135-150 target, accounting for markdown headers and separators).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md — lightweight session context replacing monolithic phoebe-session-context.md"
```

---

### Task 3: Final verification

- [ ] **Step 1: Verify both files exist and CLAUDE.md is within budget**

```bash
wc -l CLAUDE.md docs/superpowers/progress/phase-6-progress.md
```

Expected: CLAUDE.md ~145-155 lines, phase-6-progress.md ~65-75 lines.

- [ ] **Step 2: Spot-check CLAUDE.md content**

Verify key items are present:
- Turn loop diagram with all 10 phases
- Both file tables (Python + Rust)
- All 6 data model gotchas
- All 10 cross-cutting rules (including Decisions 7/9/10/11)
- Current Focus pointing to M39 and phase-6-progress.md

```bash
grep -c "Phase" CLAUDE.md          # should show 10+ (turn loop phases + other mentions)
grep "Decision" CLAUDE.md          # should show 4 lines (Decisions 7, 9, 10, 11)
grep "region_map" CLAUDE.md        # should show 1 (data model gotcha)
grep "phase-6-progress" CLAUDE.md  # should show 2 (Current Focus + References)
```
