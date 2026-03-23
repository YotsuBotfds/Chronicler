# Phase 7 Viability Adjustments

> **Status:** Proposal
> **Date:** 2026-03-20
> **Context:** Review of `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` against the current `m50b` implementation state and the existing viewer architecture.

---

## Goal

Keep the Phase 7 roadmap viable without shrinking the underlying ambition. The proposal below preserves the current simulation direction while reducing three structural risks:

1. The viewer milestone is carrying both a frontend rewrite and a long backlog of previously deferred work.
2. The spatial branch of the roadmap is unnecessarily blocked on politics migration.
3. Settlement emergence assumes clustering forces that are not yet explicitly owned by M55.

The aim is not to redesign Phase 7. It is to tighten the execution order and place infrastructure where it naturally belongs.

---

## Proposed Changes

### 1. Move the Viewer to Phase 7.5

**Recommendation:** End core Phase 7 at **M61b**. Move the current viewer milestone (`M62a/b`) into a new **Phase 7.5** focused on data contracts, scalable loading, and visualization.

### Why

The current roadmap asks the viewer to do all of the following at once:

- absorb deferred Phase 3-6 viewer backlog,
- visualize Phase 7 spatial/interiority systems,
- support much larger simulation outputs,
- and remain compatible with future systems.

That is not just a UI pass. It is a data-plane and rendering-architecture project.

The current viewer still loads a whole bundle as one JSON object into memory (`viewer/src/hooks/useBundle.ts`) and models the bundle as a monolithic structure (`viewer/src/types.ts`). That is a poor fit for 500K-1M agent outputs, especially if the roadmap wants zoomable spatial inspection rather than only aggregate summaries.

### Revised structure

- **Phase 7 ends at M61b:** simulation complete, validated, export surfaces frozen.
- **Phase 7.5 begins at M62a:** viewer/data-contract work starts only after the simulation bundle contract is stable enough to target.

### Suggested Phase 7.5 milestones

- **M62a: Export Contracts & Bundle v2**
  - stable IDs for agents, settlements, routes, armies, artifacts;
  - chunkable spatial payload design;
  - summary vs detail layers;
  - versioned schema policy for later phases.
- **M62b: Viewer Data Plane & Spatial Foundations**
  - chunked/streamed loading or tiled fetches;
  - level-of-detail rules;
  - timeline virtualization;
  - large-bundle performance guardrails.
- **M62c: Domain Panels & Backlog Integration**
  - character memory/needs/relationships;
  - trade and military panels;
  - deferred Phase 3-6 visual components.

This keeps the viewer aligned with long-term systems instead of baking in another one-off schema.

---

### 2. Decouple Spatial Infrastructure from Politics Migration

**Recommendation:** Stop making the spatial branch wait on all of `M54a/b/c`.

The current roadmap places `Spatial Sort Infrastructure` inside **M54c: Rust Politics Migration + Spatial Sort**, then makes **M55** depend on all of `M54a-c`. This means a delay in politics migration can stall the entire spatial half of Phase 7 even if the shared sort infrastructure is already ready.

### Revised dependency shape

- **M54a:** Ecology migration + shared Arrow/FFI migration pattern + shared sort infrastructure.
- **M54b:** Economy migration.
- **M54c:** Politics migration.
- **M55:** depends on `M54a` plus the shared sort infrastructure, not on `M54b/c`.
- **M56, M57, M59:** may start after `M55`.
- **M58:** waits on `M54b + M55 + M42-M43`.
- **M60:** waits on `M55 + M59a`.
- **M61:** remains the full scale gate and still depends on all scale-track work finishing.

### Why

This preserves the existing idea that ecology is the simplest migration and should establish the Rust pattern first, while removing politics as a non-essential blocker for spatial work.

---

### 3. Make M55 Explicitly Own Proto-Settlement Clustering

**Recommendation:** Strengthen the M55 contract so it does not only place agents in space, but also creates the clustering pressure that M56 later detects.

The roadmap currently describes M56 as "detection, not creation." That only works if M55 already produces meaningful proto-settlement structure. As written, M55 gives agents random drift toward attractors, but the attractors are not concrete enough yet, and some of the implied attractors (like markets) do not exist at M55 time.

### Add to M55

- deterministic per-region attractor seeds from geography and existing simulation facts:
  - river/coast access,
  - high-yield resource sites,
  - temples,
  - existing capitals or administrative centers if available;
- occupation-weighted attraction:
  - farmers prefer resource/yield attractors,
  - clergy prefer temple attractors,
  - merchants prefer route/intersection attractors once available;
- weak local density attraction with short radius and cap;
- repulsion / saturation term so clusters do not collapse into a single point;
- explicit clustering precursor validation:
  - non-uniform spatial density,
  - persistent hotspots over time,
  - frontier/core differences where appropriate.

### Why

Without this, M56 risks becoming a detector over mostly noisy drift. With it, M56 can stay true to its intended role: label and persist settlement structure that the simulation already generated.

---

### 4. Pull Validation Plumbing Forward

**Recommendation:** Treat validation as distributed infrastructure instead of back-loading too much into `M53b` and `M61a/b`.

The roadmap is directionally correct to include narrative oracles, determinism harnesses, community detection, trade validation, and settlement plausibility checks. The issue is packaging too much of that as short tail milestones.

### Revised validation ownership

- Each milestone that adds a major new system also adds:
  - its minimum extractor surface,
  - its minimum debug counters,
  - and its minimum replay hooks if it changes large-scale behavior.
- **M53b** becomes the assembly point for depth-scale oracles, not the first place instrumentation appears.
- **M61a** focuses on determinism, replay logging, and performance harnesses.
- **M61b** focuses on macro-pattern validation, not first-time observability work.

### Practical examples

- `M55` should already emit clustering precursors needed by `M56`.
- `M58` should already emit merchant route/travel diagnostics needed by later trade validation.
- `M59` should already expose packet lag / cache staleness statistics.
- `M60` should already expose campaign range and supply attrition statistics.

This does not require inventing more systems. It just spreads the instrumentation work to the place where context is freshest.

---

## Revised High-Level Sequence

```text
Depth Track:
M48 -> M49 / M50a -> M50b / M51 / M52 -> M53a -> M53b

Scale Track:
M54a (ecology + shared migration pattern + sort infra)
  -> M55
     -> M56a -> M56b
     -> M57a -> M57b
     -> M59a -> M59b
     -> M60a -> M60b

M54b (economy) runs after M54a and in parallel with M55+
  -> M58a -> M58b

M54c (politics) runs after M54a and in parallel with the spatial branch

Full gate:
M61a -> M61b

Phase 7.5:
M62a -> M62b -> M62c
```

This keeps the simulation critical path moving even if one Rust migration lags.

---

## What Does Not Need to Change

- The core Phase 7 vision remains sound: memory, needs, relationships, spatiality, trade, information, and campaigns still belong together.
- M51 does not need to become formally dependent on M50a if that dependency is only a process/cleanliness preference.
- The abstract M42-M43 trade model can still serve as the macro calibration target for M58.
- The current Phase 8-9 boundary still looks reasonable.

---

## Minimal Doc Edits Implied by This Proposal

If this proposal is accepted, the roadmap should make the following concrete edits:

1. End Phase 7 milestone scope at `M61b`.
2. Move viewer work into a new `Phase 7.5` section.
3. Rewrite the dependency graph so `M55` does not wait on `M54c`.
4. Rewrite the M55 goal text to explicitly own clustering forces, not only coordinates and drift.
5. Add a short note that validation hooks ship incrementally with their systems, not only in tuning milestones.

---

## Bottom Line

Phase 7 is viable, but it becomes much more executable if:

- the viewer becomes a dedicated compatibility phase,
- spatial work is decoupled from politics migration,
- settlement precursors are made explicit in M55,
- and validation plumbing is pulled forward into the milestones that create the behaviors.

Those changes reduce schedule fragility without meaningfully reducing simulation depth.
