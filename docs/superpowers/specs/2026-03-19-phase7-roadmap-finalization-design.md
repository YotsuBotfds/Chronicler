# Phase 7 Roadmap Finalization — Design Spec

> **Status:** Approved design. Ready for execution.
>
> **Date:** 2026-03-19
>
> **Scope:** Edit pass on the Phase 7 draft roadmap to resolve provisional caveats, tighten estimates, and extract uncommitted brainstorm content. No milestone scope changes.

---

## Context

The Phase 7 draft (`chronicler-phase7-draft.md`) was written while Phase 6 milestones M42-M45 were in-flight. Those milestones have all merged. The draft's provisional status and open questions can now be resolved. M47 (tuning pass) remains outstanding but affects calibration baselines, not Phase 7 architecture.

## Changes

### 1. Header & Status

**Before:** "Provisional draft. Subject to revision as Phase 6 milestones land (especially M42-M43 trade, M45 character arcs, M47 tuning outcomes)."

**After:** "Draft. Phase 6 architecture finalized through M45. M47 tuning pass outstanding — affects calibration baselines, not Phase 7 structure."

Prerequisite line simplifies from "All M32-M47 milestones landed" to "M47 tuning pass landed."

### 2. Milestone Table

- M54 low estimate: `24` → `25` (economy low end tightened, see §3)
- Total: `99-132` → `100-132`

### 3. M54 Body Text

**Economy per-phase estimate:** `8-12 days` → `9-12 days`. The 8-day low was generous given M43a/M43b additions (EconomyTracker, stockpile management, conservation tracking). Known code structure (1,015-line `economy.py` pre-M47, ~1,095 after tatonnement; clean function boundaries) supports a tighter low without reducing the high.

**Replace "Phase 6 dependency" block** (header + body) with:

**Header:** "Economy migration notes" (reflects resolved context, not unresolved prerequisite).

**Body:** Three items:
1. Arrow compatibility resolved — `@dataclass` result objects and dict/list structures, no exotic Python types.
2. `EconomyTracker` (M43b) maintains dual-EMA state across turns — migration must decide whether EMA state lives in Rust permanently or round-trips through Python each turn.
3. `EconomyResult.conservation` is validation/diagnostic infrastructure, not simulation logic — candidate for staying Python-side.

Does NOT repeat `allocate_trade_flow()` synchronization point (already at line 335).

### 4. Open Questions

**Q1 (two-parent lineage) → Resolved Questions table.** Resolution: No breakage — planned schema migration across ~7 files in Rust and Python, all within M57 scope. Dynasty resolution for two-parent lineage is a design question handled in M57 spec.

**Q2 (spatial determinism) → Resolved Questions table.** Resolution: M55 adds 2 new `STREAM_OFFSETS` entries for position init and drift. Existing registry pattern and collision test (`agent.rs:202`) handle this.

**Q3 (analytics interface) → Stays open, rewritten.** Header changes from "Resolve During Phase 6" to "Resolve During M54 Spec." Content: Two options (A: Rust returns Arrow batches, extractors consume batches — consistent with agent tick FFI pattern; B: Rust writes back to WorldState Python objects, extractors unchanged). M54 spec decision.

### 5. Enrichment Labels

8 enrichment blocks across 5 milestones. Each reformatted as blockquote with explicit label:

| # | Milestone | Current Label | Line |
|---|-----------|---------------|------|
| 1 | M50 | "Research enrichment (Axelrod...)" | ~194 |
| 2 | M50 | "Brainstorm enrichment" (diaspora) | ~196 |
| 3 | M52 | "Brainstorm enrichment" (cultural production) | ~276 |
| 4 | M55 | "Brainstorm enrichment" (SEIRS disease) | ~452 |
| 5 | M58 | "Research enrichment (Gravity...)" | ~526 |
| 6 | M58 | "Research enrichment (Leontief...)" | ~528 |
| 7 | M60 | "Research enrichment (Fearon...)" | ~603 |
| 8 | M60 | "Research enrichment (Power Transition...)" | ~605 |

**New format:** `> **Enrichment (not in estimate):** [existing content]`

Blockquote `>` on every line including multi-paragraph enrichments.

### 6. Risk Register — M54 Row Update

The M54 risk row (line 1000) contains two stale references:
- Economy estimate "8-12" → "9-12"
- "flag early if M42-M43 Python structure doesn't map cleanly to Arrow" → remove, Arrow compatibility is resolved

**Updated row:** `M54 schedule risk from three complex Rust migrations | High | Per-phase estimates (8-11 ecology, 9-12 economy, 6-10 politics) allow independent tracking. Ecology first to establish pattern. Economy is the critical path — EconomyTracker state handoff and trade flow synchronization are the key design challenges.`

### 7. Phase 8-9 Extraction

**Extract:** Everything from `## Phase 8-9 Horizon — Emergent Order` through the end of that section (before `## Risk Register`). Includes: Why Emergent Order, sketch milestone map (M63-M73), all Phase 8-9 enrichments, cross-system interactions, mechanistic sketches, narrative examples, Phase 7 dependencies table, research sources (entire section — Phase 7 enrichments are self-citing via inline source attributions), "Still Deferred Beyond Phase 9." Phase 8-9 enrichments move as-is and do not get the `> **Enrichment (not in estimate):**` format — they're already in brainstorm territory.

**Heading promotion:** Extracted subsections are h3 (`###`) in the draft (under an h2 parent). In the standalone file with an h1 title, promote all subsections to h2 (`##`) to maintain correct heading hierarchy.

**Destination:** `docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md`

**New file header:**
```markdown
# Chronicler Phase 8-9 Horizon — Emergent Order

> **Status:** Brainstorm. Not a commitment. Ideas to evaluate once Phase 7 systems are stable.
>
> **Phase 7 prerequisite:** M61 tuning pass validates depth + scale systems at 500K-1M agents.
>
> **Extracted from:** Phase 7 roadmap during finalization (2026-03-19). Separated to keep Phase 7 focused on committed scope (M48-M62).
```

**Phase 7 roadmap replacement:** One-line forward reference after Risk Register:
```markdown
## Phase 8-9 Horizon

See `chronicler-phase8-9-horizon.md` for brainstorm-level ideas on governance, institutions, cultural traits, and revolution dynamics. Not committed scope.
```

### 7. File Operations

1. Copy `chronicler-phase7-draft.md` → `chronicler-phase7-roadmap.md`
2. Apply changes 1-7 to the new file
3. Create `chronicler-phase8-9-horizon.md` from extracted content (with heading promotion)
4. Update `phase-6-progress.md` line 179 — full rewrite of the bullet:
   - Label: "Phase 7 draft roadmap" → "Phase 7 roadmap"
   - Filename: `chronicler-phase7-draft.md` → `chronicler-phase7-roadmap.md`
   - Status: remove "provisional, subject to revision as Phase 6 milestones land"
   - Content note: remove "Now includes Phase 8-9 horizon section (Phoebe-reviewed)" — Phase 8-9 is now in its own file
   - Replacement: `**Phase 7 roadmap:** \`docs/superpowers/roadmaps/chronicler-phase7-roadmap.md\` — draft, M47 dependency for sequencing. Phase 8-9 horizon extracted to \`chronicler-phase8-9-horizon.md\`.`
5. Delete `chronicler-phase7-draft.md` (untracked, no git history to preserve — the new file is authoritative)
6. `git add` new and modified files

---

## Not Changed

- Milestone scopes (M48-M62)
- Dependency graph
- Design decisions D1-D8
- Memory budget analysis
- Risk register — stays in Phase 7 roadmap (M54 row updated per §6, all others unchanged)
- Inspiration source references in header
- Per-milestone data models, storage layouts, tick integration details
- Structural principle ("depth first, then scale")

## Deferred

- **CLAUDE.md reference table:** Currently says "Phase 2-7 roadmaps (Phase 7 is provisional draft)". Parenthetical is outdated, and `chronicler-phase8-9-horizon.md` is unreferenced. Update separately — CLAUDE.md changes are high-traffic and better batched with other updates.
