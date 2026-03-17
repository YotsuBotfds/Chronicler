# CLAUDE.md Migration Design

> Migrate `docs/superpowers/phoebe-session-context.md` (845 lines) to a lightweight `CLAUDE.md` (~135 lines) that Claude Code auto-loads every session.

## Problem

The session context file has grown into a monolith mixing stable architecture reference, milestone history, and ~500 lines of Phase 6 Phoebe review notes. Every milestone appends more content. Most of the file is either derivable from code/specs or only relevant to the session that produced it.

## Design Principles

1. **Light** — ~135-150 lines, auto-loaded every session without token waste
2. **Stable core, updatable edge** — architecture rarely changes; only "Current Focus" updates per milestone
3. **Pointers over prose** — reference specs/plans/roadmaps instead of duplicating their content
4. **Forward-looking** — preserve decisions that affect upcoming work; let git history keep the rest

## CLAUDE.md Structure

### Section 1: What Is Chronicler (~15 lines)

Project identity, hardware, codebase stats, API narration note. Lifted from current doc lines 9-17.

Content:
- One-paragraph project description
- Hardware line (9950X, 4090, LM Studio)
- Codebase stats line (Python, Rust, React/TS)
- API narration planned note

### Section 2: Architecture (~80 lines)

Stable reference Cici needs to avoid mistakes.

Content:
- 10-phase turn loop + agent tick (ASCII diagram, ~20 lines)
- Python key files table (~15 lines, no line counts — those go stale)
- Rust crate file table (~12 lines): lib.rs, agent.rs, pool.rs, ffi.rs, region.rs, tick.rs, satisfaction.rs, decisions.rs, demographics.rs, named_characters.rs
- ActionType enum with "use these exact names" warning (~5 lines)
- StatAccumulator: 4 routing categories (keep/guard/guard-action/signal) + `civ_idx` parameter on every call (~8 lines)
- Bundle format one-liner
- Feature flags one-liner
- Key gotcha: "Civilization has no `id` field — use index into world.civilizations"

Why no line counts: they go stale after every milestone. File roles are stable; sizes aren't.

### Section 3: Cross-Cutting Rules (~10 lines)

Invariants that every session must respect:
- Negative stat changes through M18 severity multiplier (except treasury, ecology)
- Combined action weight multiplier cap at 2.5x
- 200-seed regression before/after each milestone
- `--agents=off` produces Phase 4 bit-identical output
- Phase 10 receives `acc=None` in aggregate mode
- Bundle format: consumer code doesn't know if stats came from agents or aggregates

### Section 4: Session Workflow (~10 lines)

Roles and process:
- Phoebe reviews architecture, specs, and plans
- Cici designs, specs, plans, and implements (Opus 4.6, 1M context)
- Phoebe reviews Cici's outputs before implementation starts
- Implementation plans written AFTER prerequisite milestones land
- Tuning iterations flag Tate for approval

### Section 5: Current Focus (~10 lines)

The only section that changes regularly. Contains:
- Current phase + pointer to roadmap file
- Active milestone(s) and their status (1-3 lines)
- Blockers or pending items (if any)
- Pointer to phase progress file for details

Example:
```
Phase 6 — Living Society. Roadmap: `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md`

Active: M39 (Parentage & Dynasties) — spec Phoebe-reviewed, ready for plan
Pending: M38b merge (2 bugs, 4 gaps addressed), M36 pre-merge fix
See: `docs/superpowers/progress/phase-6-progress.md`
```

Update cost: change 1-2 lines when a milestone lands.

### Section 6: References (~10 lines)

Pointer table to:
- Phase roadmaps (phase 2-6 files)
- Specs directory
- Plans directory
- Phase 6 progress file
- Key file locations (src/chronicler/, chronicler-agents/src/, viewer/, tests/)

## Companion File: `docs/superpowers/progress/phase-6-progress.md`

Slim file (~50-80 lines). Structured as:

### Sections
1. **Active Pre-Merge Items** — milestones implemented but not yet merged, with specific pending fixes
2. **Locked Design Decisions for Upcoming Milestones** — Phoebe-approved decisions that constrain future implementation
3. **Known Gotchas / Deferred Items** — active constraints, calibration notes, deferred work

### Content to extract (by milestone)
From current session context lines 272-809:
- **M32-M35b:** Drop entirely (merged, implemented, in code)
- **M36:** Keep pre-merge fix item only (line 645 area)
- **M37:** Drop (merged, bugs fixed)
- **M38a:** Keep pre-merge items: treasury int bug fix, temple conquest lifecycle cleanup
- **M38b:** Keep all spec review items (2 bugs, 4 gaps — not yet implemented)
- **M39:** Keep all 5 design decisions from Phoebe Q&A (constrains upcoming plan)

### Lifecycle
When a phase completes, archive the progress file and create a new one for the next phase (e.g., `phase-7-progress.md`). CLAUDE.md Section 5 updates its pointer.

## What Gets Retired

`docs/superpowers/phoebe-session-context.md` stops being maintained. It remains in git history. CLAUDE.md replaces it as the session context source.

## File Locations

| File | Purpose |
|------|---------|
| `CLAUDE.md` (project root) | Auto-loaded session context (~135-150 lines) |
| `docs/superpowers/progress/phase-6-progress.md` | Forward-looking Phase 6 decisions and active gotchas |

## Implementation Steps

1. Create `docs/superpowers/progress/` directory
2. Write `phase-6-progress.md` — extract forward-looking content from session context lines 272-809
3. Write `CLAUDE.md` at project root — assemble sections 1-6 from current session context + design above
4. Verify CLAUDE.md is ~135 lines
5. Commit both files
6. Note in session context that it's retired (or leave as-is — git history suffices)
