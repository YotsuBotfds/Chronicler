# Chronicler Project Origin (2026-03-12)

> Source: user-provided kickoff summary captured on 2026-03-24.
> Purpose: preserve the original project intent, architecture bets, and early execution context.

---

## 1. Founder Context

- Tate (Willmar, MN), caregiver and contract driver, indie game developer, creative technologist.
- Hardware at kickoff:
  - Windows workstation: RTX 4090, Ryzen 9 9950X, 192GB DDR5
  - Mac: M5 with 24GB unified memory
- Tooling preferences:
  - Claude Max 20x workflow
  - "Fire-and-forget" agent sessions with milestone-level handoff/review loops

## 2. Kickoff Intent

- Initial problem: loss of interest in vibe-coded web/game work.
- Desired direction: deeper creative + intellectual systems work with strong autonomy.
- Chosen thesis: build a zero-player civilization chronicle generator where simulation decides outcomes and LLMs narrate consequences.

## 3. Early Research Inputs

Primary influences explored at kickoff:

- Dwarf Fortress world generation (simulation-first history)
- Caves of Qud sultanate history (domain-threaded rationalization)
- Stanford Generative Agents (memory + reflection loops)
- Peter Turchin frontier/asabiya dynamics
- Epitaph cascading probability patterns
- Stars Without Number faction turns

Adjacent exploration:

- Claude Composer
- Story-bible worldbuilding patterns
- Solo RPG automation patterns
- MCP integrations (Blender/Godot/Home Assistant)
- Generative/physical art workflows

## 4. Initial Architecture (Kickoff)

Four-layer hybrid architecture:

1. World state: Pydantic models serialized to JSON.
2. Simulation engine: deterministic Python turn loop (Environment -> Production -> Action -> Events -> Consequences -> Chronicle).
3. Narrative engine: LLM narration using prompt-scoped domain threading.
4. Memory/reflection: era summaries every 10 turns for continuity.

Core principle established at kickoff and preserved later:

- Simulation determines events.
- LLM layer narrates and contextualizes events.

## 5. Day-1 Build Snapshot (Kickoff)

- M1-M4 built in parallel by Claude Code subagents.
- Test count moved from 63 passing to 94 passing after M5-M6.
- M5-M6 delivered:
  - memory system
  - chronicle compiler
  - CLI entry point
  - local-only inference path with optional SDK dependency
- Early fixes landed:
  - collapse events narrated
  - `--resume` support
  - treasury cap
  - deterministic seeding
  - LLM error handling

## 6. Early Runtime/Model Findings

- ERNIE 4.5-21B-A3B: aggressive `EXPAND` behavior in early runs.
- GPT-OSS 20B: "all-DEVELOP" collapse tendency in short run.
- Qwen3-32B on 4090: too slow for dense loop and required `/no_think` suppression.
- Early conclusion: defer benchmark shootout until simulation depth improves.

## 7. Original Roadmap Direction (Kickoff)

Planned next milestones at project start:

- M7: simulation depth (action engine, tech progression, named events, leader depth)
- M8: custom scenarios
- M9: scenario library (including Minnesota/post-collapse setting variants)
- M10: workflow tooling (batch scoring, fork mode, intervention hooks)
- M11: visualization viewer
- M12: interactive mode

## 8. Development Method Established Early

Canonical workflow pattern:

`read memory -> plan milestone -> review plan -> implement -> review implementation and plan as a whole`

Practices established from the start:

- milestone-scoped sessions
- dependency-aware planning
- test-first implementation
- review gates between spec, plan, and implementation

## 9. Then vs Now Delta (2026-03-12 -> 2026-03-24)

This section records how the project evolved during the first 12 days.

### Scope and Milestone State

- Then (2026-03-12): foundational architecture in place, M1-M6 complete, M7 depth work about to begin.
- Now (2026-03-24): depth track through M53 concluded; scale track started with M54a landed and M54b/M54c/M55a actively specified.

Evidence:

- [phase-6-progress.md](C:/Users/tateb/Documents/opusprogram/docs/superpowers/progress/phase-6-progress.md) records M53 concluded and scale track handoffs (lines around 229-433).
- [2026-03-24-m55a-spatial-substrate-design.md](C:/Users/tateb/Documents/opusprogram/docs/superpowers/specs/2026-03-24-m55a-spatial-substrate-design.md) status: "Approved for implementation."
- [2026-03-21-m54b-rust-economy-migration-design.md](C:/Users/tateb/Documents/opusprogram/docs/superpowers/specs/2026-03-21-m54b-rust-economy-migration-design.md) status: "Implementation-ready."
- [2026-03-22-m54c-rust-politics-migration-design.md](C:/Users/tateb/Documents/opusprogram/docs/superpowers/specs/2026-03-22-m54c-rust-politics-migration-design.md) status: pre-spec locked after M54a.

### Architecture Trajectory

- Then: Python-first deterministic simulation with local-LLM narration and memory summaries.
- Now: explicit Python/Rust split with migration contracts, Arrow batch schemas, deterministic merge gates, and off-mode parity requirements.

### Validation Discipline

- Then: passing unit/integration tests were primary confidence signal (94 passing milestone marker).
- Now: milestone-level acceptance includes canonical seeded validation pipelines (200 seeds x 500 turns), dedicated parity gates, and duplicate-seed determinism smoke tests.

### Documentation Process Maturity

- Then: roadmap vision focused on near-term depth features and viewer plans.
- Now: separate documents for:
  - depth/scale execution roadmap
  - viewer follow-on roadmap (Phase 7.5)
  - Phase 8-9 horizon (explicitly brainstorm-level)
  - implementation-ready design specs and checkbox-driven plans per sub-milestone

### Workflow Continuity

- Then: milestone gating and review loops were the method.
- Now: same method persists, but with stronger contract language (scope locks, invariants, merge gates, non-goals, parity definitions, final gate checklists).

## 10. Why This Origin Record Matters

This origin snapshot captures the project's durable identity:

- simulation-first causality
- narration as an interpretive layer, not a decision engine
- milestone-driven execution with strict review gates
- deterministic and testable behavior as non-negotiable

Those assumptions have remained stable from kickoff through the current Phase 7 scale migration.

