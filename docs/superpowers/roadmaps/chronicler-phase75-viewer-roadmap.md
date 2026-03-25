# Chronicler Phase 7.5 - Viewer & Bundle Compatibility

> **Status:** Draft (Dormant until M61b freeze gate is green)
>
> **Phase 7 prerequisite:** M61b lands and freezes the core simulation outputs for Phase 7.
>
> **Extracted from:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` during the 2026-03-20 viability revision, to keep the main Phase 7 roadmap focused on simulation milestones through M61b.
>
> **Structural principle:** Stable export contracts before rich panels. The viewer should target durable simulation outputs, not chase a moving schema while Phase 7 systems are still settling.
>
> **Current state:** `viewer/` is deprecated for net-new feature work. Only break/fix maintenance is in scope until this roadmap is reactivated.
>
> **When to pick this back up:** Once M61b is complete, use this document as the working roadmap for viewer implementation and refinement.

## Why Phase 7.5 Exists

Core Phase 7 is now explicitly the simulation program: memory, needs, relationships, space, settlements, trade, information, campaigns, and the scale/determinism validation needed to trust them. Viewer work is different in kind. It is not just presentation polish. It is a data-contract and rendering-architecture problem.

The current viewer can load and inspect bundle outputs, but the next wave of requirements changes the problem:

- large Phase 7 bundles rather than relatively small snapshots,
- agent-level or settlement-level drill-down rather than only aggregate summaries,
- stable IDs and schema layering so future phases do not require another viewer rewrite,
- and deferred Phase 3-6 viewer backlog that still needs a proper home.

Separating Phase 7.5 creates a clean handoff:

- **Phase 7** proves the simulation and freezes the export contract.
- **Phase 7.5** designs and builds the long-lived viewer/data plane against that stable target.

## Milestone Map

| # | Milestone | Depends On | Est. Days | Goal |
|---|-----------|------------|-----------|------|
| M62a | Export Contracts & Bundle v2 | M61b | 3-4 | Stable IDs, chunkable bundle structure, summary/detail layers, versioning policy |
| M62b | Viewer Data Plane & Spatial Foundations | M62a | 4-5 | Chunked/tiled loading, level-of-detail rules, timeline virtualization, spatial foundations |
| M62c | Entity, Trade & Network Panels | M62b | 4-5 | Rich inspection panels, diagnostics, backlog integration, domain-specific affordances |

**Phase 7.5 estimate:** 11-14 days across 3 milestones/sub-milestones.

## Reactivation Gate (M61b -> M62a)

Phase 7.5 starts only when all conditions below are true:

- M61b canonical validation run is complete and accepted.
- Export surfaces needed by M62a are frozen for the current cycle (no pending schema-breaking PRs).
- At least one full-scale reference bundle from the accepted M61b run is available for fixture-driven viewer work.
- Ownership is explicitly assigned for Bundle v2 contract, viewer data plane, and panel layer work.

## Pre-Activation Assets (2026-03-24)

The following doc-level assets are prepared ahead of M61b so M62a can start quickly once the reactivation gate is green:

- Bundle v2 contract draft: `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`
- M62a pre-activation execution plan/checklist: `docs/superpowers/plans/2026-03-24-m62a-preactivation-prep.md`
- Dormant implementation notes for typed loader/fixture/test scaffolding exist in local prep work, but that viewer-side code is intentionally not merged to `main` until Phase 7.5 is reactivated.

Scope note: this is pre-activation scaffolding only. Phase 7.5 remains dormant until M61b acceptance. On `main`, the checked-in prep is doc-first: contract and activation planning are ready, while loader/fixture code stays deferred until activation.

## M62a: Export Contracts & Bundle v2

**Goal:** Replace the implicit "one giant bundle blob" assumption with a versioned contract designed for long-term compatibility and selective loading.

### Required deliverables

- Stable IDs for agents, named characters, civs, regions, settlements, dynasties, households, routes, armies, artifacts, factions, and faiths
- Bundle versioning policy with explicit backward-compat expectations
- Summary-vs-detail layer split
- Chunkable spatial payload design
- Manifest shape for multi-part exports if needed
- Compatibility story for archive/batch workflows that still want a simple artifact
- Typed timeline/event payload shape that can carry character, civ, settlement, route, and army history without custom schema rewrites
- Generic metric/overlay registry so future phases can add new dashboards and map layers without changing the base loader contract
- Reserved namespace policy for future Phase 8-9 entities such as institutions, cultural traits, prestige goods, patronage edges, and revolt clusters

### Bundle v2 direction

Move from a single monolithic export toward a manifest-plus-layers model:

- summary snapshots for archive/batch workflows,
- chunkable spatial/detail layers for viewer drill-down,
- stable IDs so later phases can add panels without rewriting the base schema,
- and generic timeline/metric/network shapes so Phase 8-9 can plug in new systems rather than fork the viewer architecture.

### Future-proofing rules

- Treat entity identity, timelines, metrics, overlays, and networks as first-class contract layers rather than one-off panel payloads.
- Keep panel composition data-driven where possible so a new entity type can reuse cards, charts, timelines, and edge lists.
- Prefer typed extension points over opaque blobs: the viewer should know how to load a new overlay or metric family without hardcoding each future milestone.

### Bundle packaging decision (planning lock)

| Option | Backward compatibility | Selective loading | Long-term schema evolution | Complexity | Planning decision |
|--------|-------------------------|-------------------|----------------------------|------------|-------------------|
| Monolithic JSON + optional chunks | Strong near-term | Weak-medium | Medium | Lower | Fallback only |
| Manifest-first (summary + layered detail payloads) | Medium (needs adapter) | Strong | Strong | Medium | **Default** |

**Planning default:** Bundle v2 is manifest-first, with summary/detail layers split into explicit payload families.

**Compatibility fallback:** Keep a legacy "single artifact" export path as an adapter for archive/batch workflows during migration. The adapter is compatibility glue, not the primary contract.

### Bundle contract test suite (M62a merge gate)

M62a should land with fixture-driven contract tests, not only ad hoc viewer checks.

- Golden fixture bundles for small, medium, and large runs (including one M61b-scale fixture).
- Schema snapshot tests for manifest, entity IDs, timeline events, metric families, overlays, and network layers.
- Backward-compat tests: N-1 loader compatibility for additive changes.
- Determinism tests: same input run exports identical manifest/entity IDs and stable ordering.
- Negative tests: missing chunk, unknown layer kind, and malformed manifest diagnostics are explicit and actionable.

**Versioning rule (Bundle v2):**

- `MAJOR`: incompatible schema change.
- `MINOR`: additive backward-compatible fields/layers.
- `PATCH`: doc-only or non-structural clarifications.

## M62b: Viewer Data Plane & Spatial Foundations

**Goal:** Build the scalable loading/rendering substrate before adding feature-rich panels.

### Core responsibilities

- Chunked or tiled loading
- Level-of-detail rules
- Timeline virtualization
- Spatial map foundations
- Settlement overlays
- Regional knowledge/fog overlays
- Settlement precursor and attractor overlays where useful for diagnostics
- Trade route rendering
- Army march rendering
- Asabiya heatmap
- Frontier/core and influence overlays
- Data plumbing for large bundles
- Generic layer toggles for current and future map-backed systems

### Scope guard

M62b is where the viewer becomes capable of handling Phase 7 scale. It should not get buried under panel polish. If schedule pressure appears, protect the data plane and spatial loading rules first.

### Data-plane performance budgets (draft merge gates)

These are practical budgets for M62b/M62c acceptance on modern desktop hardware:

| Metric | Budget (p95 unless noted) |
|--------|----------------------------|
| Manifest parse + summary load | <= 2.0s |
| First map paint after bundle open | <= 1.0s after summary load |
| Turn scrub latency (timeline drag) | <= 120ms |
| Overlay toggle latency | <= 150ms |
| Entity panel open latency (character/settlement/civ) | <= 200ms |
| Region-level drilldown (agent/settlement detail fetch) | <= 300ms |
| Peak browser memory on large fixture | <= 2.5GB |
| Hard failure threshold | no full-tab freeze > 3s |

## M62c: Entity, Trade & Network Panels

**Goal:** Add the domain-specific inspection tools that make Phase 7 systems understandable to humans.

### Target panels and affordances

- Character detail panel: memory timeline, needs radar, relationship graph
- Settlement detail panel: founding, growth, infrastructure state, pull factors, and notable residents
- Civ detail panel: factions, faith/culture composition, wealth/trade diagnostics, asabiya, and dynastic links
- Dynasty/household affordances: spouse/child links, legacy memory context, succession order, and inter-civ marriage ties
- Artifact display on character and civ panels
- Mule character indicator with memory-that-warped-them and active window countdown
- Trade diagnostics: route profitability, stale vs current price views, in-transit goods, and merchant plans
- Knowledge diagnostics: familiarity, staleness, source channel, and confidence for cross-region information
- Army/campaign diagnostics: composition, morale, supply, target rationale, march history, and battle outcomes
- Cohort and social-network affordances: community summaries, strong-tie clusters, and grievance-rich group inspection

### Backlog integration rule

The deferred Phase 3-6 viewer backlog belongs here, after Bundle v2 and the spatial loading/data-plane work exist.

## Phase 7.5 Component Envelope

These are the user-facing capabilities the full Phase 7.5 build should support:

- Spatial agent map (zoomable from region-level to agent-level)
- Settlement overlay (city boundaries, population, character)
- Settlement detail panel with founding/growth/infrastructure context
- Civ detail panel with economy/faction/faith/culture/asabiya summaries
- Trade route visualization (merchant paths, goods flow)
- Route and market diagnostics (profitability, stale price beliefs, goods in transit)
- Army march visualization (troop movement, supply lines)
- Army/campaign panel (morale, supply, target, battle ledger)
- Character detail panel: memory timeline, needs radar, relationship graph
- Dynasty and household explorer (lineage, marriages, succession, diplomatic ties)
- Artifact display on character and civ panels
- Mule character indicator (distinctive marker on character panel, memory-that-warped-them displayed, active window countdown)
- Knowledge/familiarity overlay with freshness or fog semantics
- Asabiya heatmap overlay (per-region, frontier vs. interior shading)
- Cohort/community inspection for relationship clusters and trauma-bonded groups
- Validation/diagnostic mode for settlement, trade, and scale-pattern oracles

## Phase 7 Coverage Checklist

This is the minimum Phase 7 inspection surface the viewer should cover. Not every item needs a bespoke top-level panel, but every system should be inspectable through some combination of panel, overlay, timeline, or diagnostic view.

| Phase 7 system | Minimum viewer surface |
|----------------|------------------------|
| M48 memory | Character memory timeline, source tags, intensity, recency, and legacy-memory marking |
| M49 needs | Character needs breakdown/radar and "what is driving decisions right now" summary |
| M50 relationships | Relationship graph, strongest ties, bond type, sentiment drift, and cohort/community summaries |
| M51 multi-generational memory | Family tree, succession order, royal numbering, inherited memories, and dynasty timeline context |
| M52 artifacts | Artifact provenance, ownership chain, holder location, prestige effects, and Mule-origin marking |
| M55 spatial positioning | Spatial agent/settlement map, frontier-core framing, attractor-aware diagnostics where needed |
| M56 settlements | Settlement founding, persistence, hierarchy, growth, infrastructure state, migration pressure, and notable residents |
| M57 households and dynastic diplomacy | Household links, marriages, children, dynastic alliances, and inter-civ relationship context |
| M58 trade logistics and pricing | Route maps, merchant plans, reserved goods, goods in transit, route profit, and stale-vs-current price context |
| M59 information propagation | Knowledge freshness/familiarity, source channel, confidence/staleness, and regional fog/awareness overlays |
| M60 campaigns and battle resolution | Army composition, march path, morale, supply, war target rationale, and battle/casualty summaries |
| M61 validation and pattern oracles | Diagnostic mode for settlement plausibility, trade baseline comparisons, cohort scaling, determinism/perf summaries |

## Deferred Backlog To Fold Into M62c

### Phase 3-4 backlog (from dropped M46)

| Component | Feature | Source |
|-----------|---------|--------|
| CivPanel | Tech focus badge (icon + tooltip) | M21 |
| CivPanel | Faction influence bar (four-segment: MIL/MER/CUL/CLR) | M22 + M38 |
| RegionMap | Ecology variables on hover (soil/water/forest progress bars) | M23 |
| RegionMap | Intelligence quality indicator (confidence ring or fog overlay) | M24 |

### Phase 5 agent data (from dropped M46)

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Population heatmap (agent count, color by mean satisfaction) | M30 |
| RegionMap | Occupation distribution donut on region hover | M30 |
| TerritoryMap | Named character markers (icon + name label) | M30 |
| TerritoryMap | Migration flow arrows (aggregate direction/volume, 10-turn window) | M30 |

### Phase 6 material world (from dropped M46)

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Resource icons per region (crop/mineral/special) | M34 |
| RegionMap | Seasonal indicator (spring/summer/autumn/winter badge) | M34 |
| RegionMap | River overlay (blue lines connecting river-adjacent regions) | M35 |
| RegionMap | Disease severity heatmap layer (toggle) | M35 |
| RegionMap | Trade flow arrows (goods type + volume along routes) | M42-M43 |

### Phase 6 society (from dropped M46)

| Component | Feature | Source |
|-----------|---------|--------|
| CharacterPanel | Personality radar chart (3 axes: boldness, ambition, loyalty) | M33 |
| CharacterPanel | Character arc timeline (horizontal, key events marked) | M45 |
| CharacterPanel | Family tree (vertical, max 3 generations) | M39 |
| CharacterPanel | Social network (d3-force mini-graph, relationships to other named chars) | M40 |
| CharacterPanel | Religious identity + faith icon | M37-M38 |
| RegionMap | Cultural identity overlay (color by dominant cultural values) | M36 |
| RegionMap | Religious majority overlay (color by dominant faith) | M37 |
| CivPanel | Wealth distribution histogram + Gini coefficient | M41 |
| CivPanel | Class tension indicator | M41 |
| CivPanel | Goods production/consumption balance | M42 |
| CivPanel | Trade dependency indicator | M43 |

## Bundle Surface Expected From Phase 7

Bundle v2 should be able to expose at least:

- named characters with personality, dynasty, faith, arc type, relationships, memory, needs, mule flags, utility overrides, and legacy-memory context
- civs and regions as stable first-class entities
- dynasties, households, marriages, and succession-order data
- agent wealth distribution
- faction composition and influence data
- cultural map
- religious map
- goods economy
- trade routes, price-belief bands, and transit/reservation state
- resource map
- spatial data
- settlement data
- regional knowledge/familiarity/staleness data
- army, campaign, and battle-summary data
- regional asabiya
- artifacts
- validation/oracle summaries needed for diagnostic mode

This is the target contract envelope. Delivery should follow the manifest-first planning lock above, with explicit migration notes for any contract changes.

## Phase 8-9 Compatibility Hooks

The Phase 7.5 viewer should not implement Phase 8-9 early, but it should leave clean attachment points for them:

- **Entity namespaces:** reserve IDs and manifest sections for institutions, ruler-legitimacy records, cultural traits, prestige goods, patronage edges, revolt clusters, and diplomacy beliefs.
- **Generic dashboards:** civ/region/entity cards should already support pluggable metric groups so PSI, legitimacy, institutional cost, or trait composition can slot in later.
- **Generic network substrate:** the same network viewer used for relationships should be able to render patronage, faction, alliance, and revolt-spread edges.
- **Generic timeline/event ledger:** a shared event model should support institution enactment, ambition completion, trait adoption, embargoes, and revolutionary outbreaks without redesign.
- **Overlay registry:** map layers should be extensible enough to add institutional reach, cultural trait concentration, prestige-good routes, and revolt heat without replacing the map stack.
- **Panel composition hooks:** character, settlement, civ, and future institution panels should support optional section injection rather than hardcoded one-off layouts.

## Estimated Implementation Footprint

~7500-10500 lines across TypeScript, schema, and export-plumbing work. The point of Phase 7.5 is to make large-bundle loading and versioned compatibility explicit before agent-level inspection is promised.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Viewer scope balloons because bundle loading remains monolithic | High | Protect M62a and M62b. Stable IDs, Bundle v2, and chunking/LOD decisions come before rich panels. |
| Backlog UI work crowds out the data plane | High | Defer Phase 3-6 backlog integration to M62c only. |
| Viewer over-focuses on characters and underexposes civ/settlement/knowledge/campaign diagnostics | High | Use the Phase 7 coverage checklist as a contract. Every major Phase 7 system must have an inspection surface, even if not a bespoke panel. |
| Schema churn from Phase 8 forces another rewrite | Medium | Stable IDs, manifest/layer split, and versioning policy land in M62a before panel work. |
| Agent-level rendering promises exceed practical performance | Medium | Use level-of-detail rules and chunked loading; do not require all-agent rendering at all zoom levels. |

## Iteration Hook

This document is meant to be improved once `M61b` is done and the team is ready to build the viewer. At that point, replace the high-level Bundle v2 direction with a concrete schema and loading plan based on the actual Phase 7 export surfaces that landed.

Reactivation trigger for status change from "Dormant" to "Active":

- M61b accepted.
- Bundle fixtures checked in.
- M62a owner assigned and kickoff date set.
