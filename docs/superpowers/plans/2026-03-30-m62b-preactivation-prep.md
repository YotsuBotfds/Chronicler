# M62b Pre-Activation Prep Plan

> **Status:** Draft prep (blocked on M62a acceptance and the M61b freeze gate)
> **Date:** 2026-03-30
> **Roadmap anchor:** `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`
> **Upstream input:** `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`

---

## Goal

Reduce M62b startup latency by locking the execution model, merge gate, and workstream split before the viewer data-plane work begins.

M62b is the substrate milestone. It should make the Phase 7.5 viewer capable of loading and navigating Phase 7-scale bundles without freezing or collapsing into panel polish. The milestone is successful when the app can open accepted fixtures, paint the map quickly, scrub the timeline responsively, and fetch detail slices predictably.

---

## Planning Lock Inherited From The Roadmap

- Tauri 2 is the canonical client for layered bundle browsing.
- The Rust side owns the query/data plane for layered bundle access.
- React 19 remains the default frontend until the explicit benchmark gate proves otherwise.
- PixiJS owns the world/map surface; Recharts stays for standard charts.
- Browser fallback remains limited to live mode plus legacy single-artifact bundle viewing.
- M62b is where the real query model, cache/index policy, spatial foundation, and benchmark gate land.

## Shell and Design-System Lock From The 2026-03-31 Mockup Pass

M62b should treat the recent Phase 7.5 mockup pass as a **provisional shell decision**, not just inspiration. The mockups converged on a usable common frame:

- compact metadata header
- dedicated timeline/scrubber rail directly below the header
- left narrative/event rail
- map-first center canvas
- persistent right inspector rail

This is now the planning-default shell for M62b/M62c. Do not design the substrate around separate bespoke layouts for Overview, Character, Trade, and Campaign.

### Primary implementation takeaway

- **Overview** is the anchor shell and should define the reusable frame.
- **Character** should keep the same shell while swapping in denser dossier modules.
- **Trade** and **Campaign** should feel like operational modes of the same map workspace, not separate products.

### Provisional visual-system lock

The design work also converged on a consistent visual language that implementation should preserve at the component level:

- charcoal/slate app chrome
- muted brass/gold dividers
- restrained cyan interaction state
- subdued dark-parchment terrain treatment
- editorial serif headings plus compact sans-serif data labels
- compact inspector cards and mini-charts instead of giant dashboard panes

This is not a demand for exact pixel-perfect mockup fidelity. It is a warning against needless visual drift while the shell is being built.

---

## Required Inputs From M62a

Do not start M62b implementation until the following are accepted:

- manifest-first Bundle v2 contract
- stable-ID policy
- accepted large reference fixture
- required/optional layer classification
- legacy browser fallback smoke path
- shallow Tauri shell scaffold with placeholder IPC surface

If any of the above is still unsettled, M62b risks designing the data plane around a moving target.

---

## Core Workstreams

### Workstream A: Rust/Tauri Data Plane

- [ ] Replace placeholder IPC commands with real query-oriented commands.
- [ ] Define request/response shapes for manifest open, summary load, turn window, entity detail, and overlay/detail slice fetches.
- [ ] Add cache/index policy for hot timeline, entity, and overlay paths.
- [ ] Keep responses slice-sized; do not move giant detail blobs over IPC.
- [ ] Record the concrete query contract so M62c panels can build against it.

### Workstream B: Map and Shell Foundation

- [ ] Replace the current world-map substrate with a PixiJS foundation.
- [ ] Preserve the roadmap shell model: top timeline rail, left chronicle/event/tools rail, center map canvas, right inspector rail.
- [ ] Support explicit civ selection from both map interaction and a persistent selector control.
- [ ] Ensure region/route/army clicks update the right rail predictably.
- [ ] Keep left-rail narrative/event shell structure in place even if M62c fills in richer content later.
- [ ] Build the shell as reusable primitives so Character, Trade, and Campaign reuse the same frame rather than branching into one-off layouts.
- [ ] Keep the center map visually dominant even in Character mode; deep-dive modules can dock or overlay, but should not erase shell continuity.
- [ ] Preserve the dark analytics workspace as the primary mode; defer any lighter archive/presentation mode to later polish.

### Workstream C: Performance and Benchmark Gate

- [ ] Build the representative 500-turn scrub benchmark fixture and interaction trace.
- [ ] Measure manifest open + summary load, first map paint, scrub latency, overlay toggle latency, and entity open latency.
- [ ] Compare React's critical interaction path against a minimal Solid prototype only if React misses the target budgets badly enough to justify migration.
- [ ] Record the benchmark method in repo docs so future rewrites use the same yardstick.

### Workstream D: Overlay and LOD Rules

- [ ] Define zoom/visibility rules for labels, active entity chips, fog/awareness, and heavy overlays.
- [ ] Define which overlays can coexist and which are mutually exclusive for readability.
- [ ] Ensure the map color grammar lets territory, flows, fog, and diagnostics coexist without turning into noise.
- [ ] Keep agent-detail drill-down conditional and zoom-gated; do not promise full all-agent rendering at every zoom level.
- [ ] Explicitly reserve distinct overlay grammar for territory/base map, trade flows, campaign fronts, and knowledge/fog so the four canonical screen modes can share one map renderer cleanly.

### Workstream E: Compatibility and Handoff

- [ ] Keep live-mode rendering functional through the existing WebSocket path.
- [ ] Confirm the Tauri-hosted app and browser fallback do not diverge in diagnostics vocabulary or user-facing bundle errors.
- [ ] Write the M62b handoff notes M62c will need: query contract, shell state model, inspector-entry patterns, and performance assumptions.

---

## Explicit Non-Goals

- finishing all rich entity panels in M62b
- full browser parity for layered Bundle v2 browsing
- committing to a Solid port before benchmark evidence exists
- polishing the archive/parchment visual mode
- solving every map annotation/layout problem before the data plane is stable

---

## Draft M62b Merge Gate

- [ ] Tauri app opens the accepted large fixture successfully
- [ ] Summary load stays within the agreed budget
- [ ] First map paint stays within the agreed budget
- [ ] Turn scrub stays within the agreed budget on the benchmark trace
- [ ] Overlay toggles stay within the agreed budget
- [ ] Civ selection works from both map interaction and selector control
- [ ] Inspector state stays synchronized with selection and turn changes
- [ ] Query responses remain slice-sized and do not regress into giant JSON IPC payloads
- [ ] Left-rail shell supports chronicle/event/tool navigation even if M62c still owns richer content
- [ ] Overview, Character, Trade, and Campaign can all be expressed as variants of the same shell without layout forks
- [ ] M62c handoff notes are written down

---

## Risks To Watch Early

| Risk | Why it matters | Early guardrail |
|------|----------------|-----------------|
| IPC responses become too large | Moves the bottleneck from file parsing to serialization | Enforce slice-oriented query shapes early |
| PixiJS map foundation grows into a one-off scene graph | Makes later overlays and inspectors harder to extend | Keep overlay registration and selection state generic |
| React performance arguments become ideological | Can trigger premature framework churn | Use the explicit benchmark trace before changing frameworks |
| Narrative shell gets postponed because M62b is "data plane only" | Leaves the left rail structurally wrong for M62c | Land shell structure now, richer content later |
| Overlay combinations become unreadable | Makes the map impressive in screenshots but unusable in practice | Define coexistence and LOD rules as first-class work |
| Character or campaign views drift into bespoke layouts | Breaks product cohesion and multiplies component cost | Treat Overview as the shell anchor and reuse it across modes |

---

## Activation Checklist (M62a -> M62b)

Use this before starting M62b:

1. M62a contract accepted.
2. Accepted large fixture checked in.
3. Tauri shell scaffold merged.
4. Browser fallback smoke path passing.
5. M62b owner assigned and kickoff date set.
