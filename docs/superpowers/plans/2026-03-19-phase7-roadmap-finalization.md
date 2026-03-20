# Phase 7 Roadmap Finalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finalize the Phase 7 draft roadmap by resolving provisional caveats, tightening estimates, relabeling enrichments, extracting the Phase 8-9 brainstorm section, and cleaning up stale references.

**Architecture:** Pure document editing — no code changes, no tests. Copy the draft to its final filename, apply 8 change items from the spec, extract Phase 8-9 content to a standalone file, update cross-references, delete the draft.

**Spec:** `docs/superpowers/specs/2026-03-19-phase7-roadmap-finalization-design.md`

---

### Task 1: Copy Draft to Final Filename

**Files:**
- Source: `docs/superpowers/roadmaps/chronicler-phase7-draft.md`
- Create: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- [ ] **Step 1: Copy the file**

Run: `cp docs/superpowers/roadmaps/chronicler-phase7-draft.md docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- [ ] **Step 2: Verify the copy**

Run: `diff docs/superpowers/roadmaps/chronicler-phase7-draft.md docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`
Expected: No output (files identical).

All subsequent tasks edit `chronicler-phase7-roadmap.md`.

---

### Task 2: Update Header & Status (Spec §1)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:1-9`

- [ ] **Step 1: Update the title**

Line 1. Change:
```
# Chronicler Phase 7 Draft — Deep Society: Saturating the Hardware
```
To:
```
# Chronicler Phase 7 — Deep Society: Saturating the Hardware
```

- [ ] **Step 2: Update the status and prerequisite lines**

Lines 3-5. Change:
```
> **Status:** Provisional draft. Subject to revision as Phase 6 milestones land (especially M42-M43 trade, M45 character arcs, M47 tuning outcomes).
>
> **Phase 6 prerequisite:** All M32-M47 milestones landed. M47 tuning pass validates Phase 6 system interactions before Phase 7 adds new layers.
```
To:
```
> **Status:** Draft. Phase 6 architecture finalized through M45. M47 tuning pass outstanding — affects calibration baselines, not Phase 7 structure.
>
> **Phase 6 prerequisite:** M47 tuning pass landed. M47 validates Phase 6 system interactions before Phase 7 adds new layers.
```

---

### Task 3: Update Milestone Table & Total (Spec §2)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:45,55`

- [ ] **Step 1: Update M54 estimate**

Line 45. Change:
```
| M54 | Rust Phase Migration | Scale | M53 | 24-35 |
```
To:
```
| M54 | Rust Phase Migration | Scale | M53 | 25-35 |
```

- [ ] **Step 2: Update total estimate**

Line 55. Change:
```
**Total estimate:** 99-132 days across 15 milestones.
```
To:
```
**Total estimate:** 100-132 days across 15 milestones.
```

---

### Task 4: Update M54 Body Text (Spec §3)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:335,345`

- [ ] **Step 1: Update economy per-phase estimate**

Line 335. Change:
```
2. **Economy tick (Phase 2) — 8-12 days.** By the time M43a/M43b land, `economy.py` has transport costs, perishability tables, stockpile accumulation/decay/cap, salt preservation, conservation law tracking, shock detection, trade dependency classification, and the raider modifier. Trade flow computation has cross-region data dependencies — region-level parallelism with synchronization at the trade flow step. The most complex migration.
```
To:
```
2. **Economy tick (Phase 2) — 9-12 days.** `economy.py` (1,015 lines pre-M47, ~1,095 after tatonnement) has transport costs, perishability tables, stockpile accumulation/decay/cap, salt preservation, conservation law tracking, shock detection, trade dependency classification, and the raider modifier. Trade flow computation has cross-region data dependencies — region-level parallelism with synchronization at the trade flow step. The most complex migration.
```

- [ ] **Step 2: Replace the Phase 6 dependency block**

Line 345. Change:
```
**Phase 6 dependency:** M42's `economy.py` must be architecturally clean enough to translate to Rust. If M42's Python implementation uses complex data structures that don't map to Arrow, this migration gets harder. Flag during M42 implementation.
```
To:
```
**Economy migration notes:** M42-M43 landed with `@dataclass` result objects and dict/list structures — Arrow-translatable, no exotic Python types. Two migration details beyond the main translation work: (1) `EconomyTracker` (M43b) maintains dual-EMA state across turns — migration must decide whether EMA state lives in Rust permanently or round-trips through Python each turn. (2) `EconomyResult.conservation` is validation/diagnostic infrastructure, not simulation logic — migrating it is optional overhead; candidate for staying Python-side.
```

---

### Task 5: Resolve Open Questions (Spec §4)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:789-805`

- [ ] **Step 1: Replace the Open Questions section**

Lines 789-805. Replace the entire block from `## Open Questions (Resolve During Phase 6)` through the end of the Resolved Questions table (line 805, before `---` at line 807) with:

```markdown
## Open Questions (Resolve During M54 Spec)

1. **Analytics interface for Rust-migrated phases.** Python analytics extractors (`analytics.py`) consume WorldState post-turn. If ecology/economy/politics move to Rust: (A) Rust phases return results as Arrow batches, extractors consume batches (consistent with existing agent tick FFI pattern); (B) Rust writes results back to WorldState Python objects, extractors unchanged. Option A is more consistent but requires designing the Arrow schema for each phase's output. M54 spec decision.

---

## Resolved Questions

| Question | Resolution | Decision |
|----------|-----------|----------|
| Does M42-M43 abstract trade survive alongside M58? | Yes — reframed as macro specification | D6 |
| Should needs affect satisfaction or stay orthogonal? | Orthogonal. Narrator sees both. | D7 |
| Settlement persistence across turns? | Detection every 10-20 ticks + inertia counter | D8 |
| Two-parent lineage (`parent_id` → `parent_ids`) | No breakage — planned schema migration across ~7 files in Rust and Python, all within M57 scope. Dynasty resolution for two-parent lineage is a design question handled in M57 spec. | — |
| Spatial positioning determinism | M55 adds 2 new `STREAM_OFFSETS` entries for position init and drift. Existing registry pattern and collision test (`agent.rs:202`) handle this. | — |
```

---

### Task 6: Relabel Enrichment Blocks (Spec §5)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — 8 locations

Each enrichment block gets converted to a blockquote with `> **Enrichment (not in estimate):**` prefix. Every line of the block must be prefixed with `>`.

- [ ] **Step 1: M50 Axelrod enrichment (line 194)**

Change:
```
**Research enrichment (Axelrod Cultural Dissemination):** M50's homophily-based bond formation aligns with Axelrod's dissemination model — agents interact only if culturally similar. Key finding: homophily strength matters far more than network topology for cultural fragmentation outcomes. Focus M53 tuning on bias weights, not connectivity graph structure. Bounded confidence extension (interact only if similarity > threshold τ) creates hysteresis — once divergent, hard to reconverge — which maps to M50's slot eviction creating permanent estrangement. Source: Axelrod, "The Dissemination of Culture" (1997).
```
To:
```
> **Enrichment (not in estimate):** M50's homophily-based bond formation aligns with Axelrod's dissemination model — agents interact only if culturally similar. Key finding: homophily strength matters far more than network topology for cultural fragmentation outcomes. Focus M53 tuning on bias weights, not connectivity graph structure. Bounded confidence extension (interact only if similarity > threshold τ) creates hysteresis — once divergent, hard to reconverge — which maps to M50's slot eviction creating permanent estrangement. Source: Axelrod, "The Dissemination of Culture" (1997).
```

- [ ] **Step 2: M50 diaspora enrichment (line 196)**

Change:
```
**Brainstorm enrichment:** M50 is the natural attachment point for diaspora tracking — `diaspora_registry: dict[civ_id, dict[region_id, population]]` tracking displaced populations. Chain migration uses the same relationship edges (diaspora at destination reduces migration cost). Enclave vs. assimilation dynamics emerge from cultural distance + diaspora size + host tolerance. See `docs/superpowers/design/brainstorm-simulation-depth-and-parameters.md` §E9.
```
To:
```
> **Enrichment (not in estimate):** M50 is the natural attachment point for diaspora tracking — `diaspora_registry: dict[civ_id, dict[region_id, population]]` tracking displaced populations. Chain migration uses the same relationship edges (diaspora at destination reduces migration cost). Enclave vs. assimilation dynamics emerge from cultural distance + diaspora size + host tolerance. See `docs/superpowers/design/brainstorm-simulation-depth-and-parameters.md` §E9.
```

- [ ] **Step 3: M52 cultural production enrichment (line 276)**

Change:
```
**Brainstorm enrichment:** M52's artifact type enum is the natural home for cultural production — works of art, philosophical treatises, monuments. Cultural golden ages where prosperity enables creative output that defines a civilization's identity. Monuments as visible landmarks on maps. See brainstorm §E7.
```
To:
```
> **Enrichment (not in estimate):** M52's artifact type enum is the natural home for cultural production — works of art, philosophical treatises, monuments. Cultural golden ages where prosperity enables creative output that defines a civilization's identity. Monuments as visible landmarks on maps. See brainstorm §E7.
```

- [ ] **Step 4: M55 SEIRS disease enrichment (line 452)**

Change:
```
**Brainstorm enrichment:** M55's spatial density enables a disease system upgrade from M35b's endemic baseline to a full SEIRS model — transmission rate (beta) scales with population density, urban settlements (M56) become disease amplifiers, quarantine as a policy tradeoff (reduces contact rate at cost of trade penalty). See brainstorm §E3.
```
To:
```
> **Enrichment (not in estimate):** M55's spatial density enables a disease system upgrade from M35b's endemic baseline to a full SEIRS model — transmission rate (beta) scales with population density, urban settlements (M56) become disease amplifiers, quarantine as a policy tradeoff (reduces contact rate at cost of trade penalty). See brainstorm §E3.
```

- [ ] **Step 5: M58 gravity trade routes enrichment (line 526)**

Change:
```
**Research enrichment (Gravity-Based Trade Routes):** Route formation can be endogenous rather than static: trade route probability ∝ `(pop_A × pop_B) / distance²`. Routes activate when expected profit exceeds threshold. Merchants learn via exponential moving average of profitability — routes persist or dissolve based on realized returns. This means when a civ develops luxury goods, routes spontaneously form; wars shut routes down automatically (profit drops). ~100-150 lines Python + 20 lines Rust signal write-back. M58's agent merchants then operate on this dynamic route network rather than static paths. Source: Enhanced Gravity Model (Frontiers in Physics 2019).
```
To:
```
> **Enrichment (not in estimate):** Route formation can be endogenous rather than static: trade route probability ∝ `(pop_A × pop_B) / distance²`. Routes activate when expected profit exceeds threshold. Merchants learn via exponential moving average of profitability — routes persist or dissolve based on realized returns. This means when a civ develops luxury goods, routes spontaneously form; wars shut routes down automatically (profit drops). ~100-150 lines Python + 20 lines Rust signal write-back. M58's agent merchants then operate on this dynamic route network rather than static paths. Source: Enhanced Gravity Model (Frontiers in Physics 2019).
```

- [ ] **Step 6: M58 Leontief enrichment (line 528)**

Change:
```
**Research enrichment (Leontief Input-Output):** Formalize production as `output[good] = f(inputs)` via sparse matrix. When inputs are scarce, production throttles to `min(available[input] / required[input])` across all inputs. Creates cascade effects: coal mine disruption → steel throttle → sword production drops → military power weakens. O(G²) per civ, negligible. ~120 lines extending `economy.py` goods definitions with input requirements. Source: ABIDES-Economist (arxiv 2024), BazaarBot (gamedeveloper.com).
```
To:
```
> **Enrichment (not in estimate):** Formalize production as `output[good] = f(inputs)` via sparse matrix. When inputs are scarce, production throttles to `min(available[input] / required[input])` across all inputs. Creates cascade effects: coal mine disruption → steel throttle → sword production drops → military power weakens. O(G²) per civ, negligible. ~120 lines extending `economy.py` goods definitions with input requirements. Source: ABIDES-Economist (arxiv 2024), BazaarBot (gamedeveloper.com).
```

- [ ] **Step 7: M60 Fearon enrichment (line 603)**

Change:
```
**Research enrichment (Fearon War Bargaining):** Current war triggers are power-disparity based. Fearon identifies three structural conditions that explain war better than raw power: (1) **Commitment problems** — declining power is tempted to preempt before parity shifts; (2) **Information asymmetry** — mutual overconfidence when perception gap > 40%; (3) **No settlement zone** — overlapping claims leave no mutually acceptable division. Integration: check power trajectory (declining → preventive war risk), information gap (how well do civs estimate each other's strength — pairs with M59's perception lag), and settlement feasibility. This enriches M60 from "armies fight" to "wars start for structural reasons." Source: Fearon, "Rationalist Explanations for War" (Stanford 1995).
```
To:
```
> **Enrichment (not in estimate):** Current war triggers are power-disparity based. Fearon identifies three structural conditions that explain war better than raw power: (1) **Commitment problems** — declining power is tempted to preempt before parity shifts; (2) **Information asymmetry** — mutual overconfidence when perception gap > 40%; (3) **No settlement zone** — overlapping claims leave no mutually acceptable division. Integration: check power trajectory (declining → preventive war risk), information gap (how well do civs estimate each other's strength — pairs with M59's perception lag), and settlement feasibility. This enriches M60 from "armies fight" to "wars start for structural reasons." Source: Fearon, "Rationalist Explanations for War" (Stanford 1995).
```

- [ ] **Step 8: M60 Organski enrichment (line 605)**

Change:
```
**Research enrichment (Power Transition Theory — Organski):** War risk spikes at power parity (ratio within ±15%), especially when the rising power is revisionist (dissatisfied with status quo). 3-5× more war-likely at parity than at clear dominance. Integration: compute pairwise power trajectories, flag pairs approaching parity, feed into war risk modifier in action engine. O(n log n). Complements Fearon's commitment problem mechanism.
```
To:
```
> **Enrichment (not in estimate):** War risk spikes at power parity (ratio within ±15%), especially when the rising power is revisionist (dissatisfied with status quo). 3-5× more war-likely at parity than at clear dominance. Integration: compute pairwise power trajectories, flag pairs approaching parity, feed into war risk modifier in action engine. O(n log n). Complements Fearon's commitment problem mechanism.
```

Note: The original Organski enrichment lacks a source attribution (unlike all other enrichments). Not adding one here — the label change is the only authorized modification per spec §5.

---

### Task 7: Update Risk Register M54 Row (Spec §6)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:1000`

- [ ] **Step 1: Update the M54 risk row**

Line 1000. Change:
```
| M54 schedule risk from three complex Rust migrations | High | Per-phase estimates (8-11 ecology, 8-12 economy, 6-10 politics) allow independent tracking. Ecology first to establish pattern. Economy is the critical path — flag early if M42-M43 Python structure doesn't map cleanly to Arrow. |
```
To:
```
| M54 schedule risk from three complex Rust migrations | High | Per-phase estimates (8-11 ecology, 9-12 economy, 6-10 politics) allow independent tracking. Ecology first to establish pattern. Economy is the critical path — EconomyTracker state handoff and trade flow synchronization are the key design challenges. |
```

---

### Task 8: Extract Phase 8-9 to Standalone File (Spec §7)

**Files:**
- Modify: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md:809-981`
- Create: `docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md`

- [ ] **Step 1: Create the Phase 8-9 horizon file**

Extract lines 809-981 from the roadmap. The new file starts with a fresh header, then the extracted content with headings promoted from h3 to h2:

The file structure is:
```
# Chronicler Phase 8-9 Horizon — Emergent Order       ← new h1 header
> Status/prerequisite/provenance blockquote             ← new
## Why Emergent Order                                   ← was ### (line 819)
## Sketch Milestone Map                                 ← was ### (line 837)
  [all M63-M73 content, enrichments unchanged]
## Cross-System Interactions (Phase 9 payoffs)          ← was ### (line 875)
## Mechanistic Sketches                                 ← was ### (line 889)
## Narrative Examples                                   ← was ### (line 915)
## Phase 7 Dependencies                                 ← was ### (line 929)
## Research Sources                                     ← was ### (line 944)
## Still Deferred Beyond Phase 9                        ← was ### (line 971)
```

New file header (replaces lines 809-813):
```markdown
# Chronicler Phase 8-9 Horizon — Emergent Order

> **Status:** Brainstorm. Not a commitment. Ideas to evaluate once Phase 7 systems are stable.
>
> **Phase 7 prerequisite:** M61 tuning pass validates depth + scale systems at 500K-1M agents.
>
> **Extracted from:** Phase 7 roadmap during finalization (2026-03-19). Separated to keep Phase 7 focused on committed scope (M48-M62).
```

The `> **Status:** Brainstorm...` and `> **Phase 7 prerequisite:**` lines from the draft (811-813) are replaced by the new header blockquote. The `> **Structural principle:**` line (815) and `> **Phase split rationale:**` line (817) both move as-is under the new header — they are Phase 8-9 framing, not Phase 7 metadata.

All `###` headings within the extracted content become `##`.

Phase 8-9 enrichments (on M63, M68, M69, M71) keep their existing format — they are NOT relabeled with `> **Enrichment (not in estimate):**` since the entire file is brainstorm territory.

- [ ] **Step 2: Replace the extracted section in the roadmap**

In `chronicler-phase7-roadmap.md`, replace lines 809-981 (everything from `## Phase 8-9 Horizon — Emergent Order` through the line before `## Risk Register`) with:

```markdown
## Phase 8-9 Horizon

See `chronicler-phase8-9-horizon.md` for brainstorm-level ideas on governance, institutions, cultural traits, and revolution dynamics. Not committed scope.
```

- [ ] **Step 3: Verify the roadmap structure**

Run: `grep '^## ' docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

Expected output (section headings in order):
```
## Why Deep Society
## Milestone Overview
## Depth Track (M48-M53)
## Scale Track (M54-M60)
## Per-Agent Memory Budget
## Dependency Graph
## Design Decisions
## New Constants Summary
## Open Questions (Resolve During M54 Spec)
## Resolved Questions
## Phase 8-9 Horizon
## Risk Register
```

- [ ] **Step 4: Verify the extracted file structure**

Run: `grep '^## ' docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md`

Expected output:
```
## Why Emergent Order
## Sketch Milestone Map
## Cross-System Interactions (Phase 9 payoffs)
## Mechanistic Sketches
## Narrative Examples
## Phase 7 Dependencies
## Research Sources
## Still Deferred Beyond Phase 9
```

---

### Task 9: Update Cross-References

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md:194`

- [ ] **Step 1: Update phase-6-progress.md reference**

Line 194. Change:
```
- **Phase 7 draft roadmap:** `docs/superpowers/roadmaps/chronicler-phase7-draft.md` — provisional, subject to revision as Phase 6 milestones land. Now includes Phase 8-9 horizon section (Phoebe-reviewed).
```
To:
```
- **Phase 7 roadmap:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — draft, M47 dependency for sequencing. Phase 8-9 horizon extracted to `chronicler-phase8-9-horizon.md`.
```

---

### Task 10: Delete Draft & Commit

**Files:**
- Delete: `docs/superpowers/roadmaps/chronicler-phase7-draft.md`
- Stage: all new and modified files

- [ ] **Step 1: Delete the draft**

Run: `rm docs/superpowers/roadmaps/chronicler-phase7-draft.md`

- [ ] **Step 2: Verify the draft is gone and the new files exist**

Run: `ls docs/superpowers/roadmaps/chronicler-phase7* docs/superpowers/roadmaps/chronicler-phase8*`

Expected:
```
docs/superpowers/roadmaps/chronicler-phase7-roadmap.md
docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md
```

- [ ] **Step 3: Stage and commit**

```bash
git add docs/superpowers/roadmaps/chronicler-phase7-roadmap.md \
       docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md \
       docs/superpowers/progress/phase-6-progress.md \
       docs/superpowers/specs/2026-03-19-phase7-roadmap-finalization-design.md \
       docs/superpowers/plans/2026-03-19-phase7-roadmap-finalization.md
git commit -m "docs: finalize Phase 7 roadmap, extract Phase 8-9 horizon

Resolve provisional caveats (M42-M45 merged), tighten M54 estimate
(25-35 days), resolve 2 open questions, relabel 8 enrichment blocks,
update Risk Register M54 row, extract Phase 8-9 brainstorm to
chronicler-phase8-9-horizon.md.

Spec: docs/superpowers/specs/2026-03-19-phase7-roadmap-finalization-design.md"
```

---

## Deferred (not in this commit)

- **CLAUDE.md References table:** Parenthetical "(Phase 7 is provisional draft)" is stale. New `chronicler-phase8-9-horizon.md` unreferenced. Batch with other CLAUDE.md updates.
- **Enrichment name searchability:** Leontief enrichment loses its name in the label change (body text says "ABIDES-Economist, BazaarBot" not "Leontief"). Future cleanup could use `> **Enrichment — Name (not in estimate):**` format.
- **Organski source attribution:** Original enrichment (line 605) lacks source citation unlike all other enrichments. Future cleanup.
