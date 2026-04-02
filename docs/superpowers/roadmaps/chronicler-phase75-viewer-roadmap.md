# Chronicler Phase 7.5 - Viewer and Bundle Compatibility

> **Status:** Draft (dormant until the M61b freeze gate is green)
>
> **Last planning refresh:** 2026-03-30
>
> **Phase 7 prerequisite:** M61b lands and freezes the core Phase 7 export surfaces.
>
> **Extracted from:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` during the 2026-03-20 viability revision, then refreshed on 2026-03-30 with explicit implementation guidance.
>
> **Structural principle:** Stable export contracts before rich panels. Phase 7.5 is a data-contract and rendering-architecture project first, and a UI polish project second.
>
> **Current state:** `viewer/` remains break/fix only until this roadmap is reactivated.

## Why Phase 7.5 Exists

Core Phase 7 is the simulation program: memory, needs, relationships, space, settlements, trade, information, campaigns, and the scale/determinism validation needed to trust them. Viewer work is different in kind. The current viewer can inspect legacy bundle outputs, but the next wave of requirements changes the problem:

- Phase 7 bundles are larger and more layered than the current single-file snapshots.
- Inspection needs shift from civ summaries to settlement-, character-, route-, and campaign-level drill-down.
- Stable IDs and schema layering are needed so future phases can attach new panels and overlays without another rewrite.
- Deferred Phase 3-6 viewer backlog still needs a home, but should land only after the data plane is stable.

Separating Phase 7.5 creates a clean handoff:

- **Phase 7** proves the simulation and freezes the export contract.
- **Phase 7.5** builds the long-lived viewer/data plane against that stable target.

## Planning Lock (2026-03-30)

The sections below capture the current implementation recommendation. This is not a "begin coding now" instruction; Phase 7.5 is still gated on M61b acceptance. It is the planning default that future agents should use once the gate opens.

### Canonical product shape

- **Primary client:** Tauri 2 desktop application.
- **Why:** Phase 7.5 needs native filesystem access, layered bundle loading, and good non-coder ergonomics for local runs. Designing around a browser-only file API adds friction right where the product is weakest.
- **Packaging stance:** Tauri is the canonical client, not a late wrapper around a browser-first design.
- **Browser fallback:** keep the browser path for live mode and legacy single-artifact bundle viewing. Full Bundle v2 browsing is not required outside Tauri in Phase 7.5.

### Frontend stack lock

- **Framework:** React 19 + Vite + TypeScript.
- **Keep:** current live-mode infrastructure, current panel/component investment, and current chart stack where it still fits.
- **Do not rewrite by default:** Svelte, Solid, Rust-native GUI stacks, and game-engine UIs are out unless Phase 7.5 benchmarking proves a hard blocker.

### Rendering stack lock

- **Map/spatial surface:** PixiJS v8.
- **Charts/dashboards:** Recharts stays for standard charts and dashboard panels.
- **Small graph views:** continue using lightweight graph tooling where needed; do not force PixiJS to own every visualization.
- **Rationale:** the world view is primarily a 2D synthetic-coordinate rendering problem, not a geospatial web-map problem and not a full 3D scene problem.

### Data-plane lock

- **Primary data plane:** Rust-side processing inside the Tauri app.
- **Rust owns:** filesystem access, manifest parsing, layer discovery, detail-layer parsing and decoding, indexing, cache policy, and query/slice endpoints.
- **Frontend owns:** viewport state, panel state, map rendering, timeline interaction, chart rendering, and live-mode UX.
- **Important constraint:** do not parse large bundle layers in the webview and then hand giant blobs to React. The frontend should request small turn/viewport/entity windows from Rust.

### Open measurement gate

- **React vs Solid:** treat this as a benchmark gate, not a planning argument.
- Build a scrub/overlay benchmark against a representative 500-turn fixture during M62b.
- If React is within 30 ms of Solid for the critical scrub path, keep React.
- If React misses the target by more than 50 ms on the critical interaction path, a Solid port becomes a valid M62b rewrite decision.
- Until that benchmark exists, React remains the default.

## Starting Point on `main`

This is the baseline Phase 7.5 should assume when reactivated:

- `viewer/` is already a React 19 + Vite + TypeScript app.
- `viewer/` already supports live mode over WebSocket.
- `viewer/` already has bundle-v2 manifest detection and fixture scaffolding, but layered loading is intentionally inactive.
- Existing charts/panels are useful salvage, but the map/data plane should be treated as a rewrite surface.

Implication: Phase 7.5 is not a greenfield UI. It is a targeted architecture pivot:

- keep the frontend shell and working live-mode path,
- replace the map substrate,
- add a Tauri shell and Rust viewer-core,
- and migrate bundle loading away from browser-side monolithic parsing.

## Architecture Boundaries

Future agents should preserve this split unless there is a concrete, measured reason to change it.

### Python ownership

- Bundle v2 export contract and stable-ID production
- Legacy single-artifact adapter export for compatibility
- Live-mode server and simulation orchestration
- Fixture generation for viewer testing

### Rust/Tauri ownership

- App shell, installer, and local filesystem access
- Manifest loading, required/optional layer validation, diagnostics
- Detail-layer parsing/decoding, indexing, and caching
- Query-oriented IPC for viewport, turn-window, entity, and overlay requests
- Optional pre-aggregation for hot viewer paths

### Frontend ownership

- Window/layout/navigation state
- Timeline scrubber and playback UX
- PixiJS map scene and overlay toggles
- Character/civ/settlement/campaign panels
- Recharts dashboards and supporting controls
- Live-mode rendering over the existing WebSocket path

### Explicit non-goals for Phase 7.5

- Full browser parity for layered local bundle browsing
- Native desktop UI rewrite in egui, Qt, SwiftUI, Flutter, etc.
- Replacing React before benchmark evidence exists
- Heavy browser-only data infrastructure if the Tauri data plane already solves the problem

## Entry Flow and Product Front Door

Phase 7.5 should not assume users arrive only by opening an already-exported bundle from disk. The product direction is stronger if the viewer becomes the front door for setup, execution, and inspection.

### Preferred entry points

- **New World:** configure scenario/world options, seed, turn count, and narration mode, then launch directly into a run.
- **Batch Lab:** run many seeds, rank results by interestingness, compare reports, and open selected runs in the full viewer.
- **Open Existing:** open an already-exported bundle directly for inspection.

### Why this belongs in the viewer plan

- The current codebase already has useful setup-lobby and batch-run surfaces that can be evolved instead of discarded.
- A Tauri-first local app is a better place than the CLI for non-coder workflows such as "generate a world and inspect it immediately."
- Interestingness-ranked batch workflows are part of Chronicler's value proposition, not just a developer-only auxiliary tool.

### Product-flow planning default

Treat setup, execution, and viewing as one continuous application flow:

1. configure a world or batch job
2. run it
3. surface progress/status
4. auto-open the resulting bundle/report in the viewer

The happy path should not require users to manually hunt for output files after a run finishes.

### Single-run guidance

- The single-run setup surface should evolve from the current setup lobby rather than being replaced gratuitously.
- "Narration mode" should be a first-class run choice, with the UX phrased around behavior (`Off`, `Local`, `API`) rather than exposing raw implementation details where possible.
- On successful completion, the app should move straight into the main viewer shell for the generated run.

### Batch guidance

- Batch mode should evolve from the current batch-run and batch-report tooling rather than becoming a separate sidecar product.
- Batch results should be rankable and browsable by interestingness, with at least seed, score, major event counts, and anomaly signals visible in the ranked view.
- Users should be able to open a selected run in the full viewer from the ranked list.
- Side-by-side comparison remains valuable, but should sit behind the ranked-results workflow rather than replacing it.
- A future "narrate top N runs" workflow is a plausible extension, but it is not required for initial Phase 7.5 scope.

### Implementation posture

This does **not** mean Phase 7.5 must finish every setup/batch polish feature before the viewer ships. It does mean the roadmap should preserve a clean path for:

- setup/lobby integration into the Tauri shell
- batch execution visibility and report ranking
- direct handoff from completed run -> viewer open state

These should be treated as product-integration affordances that strengthen the viewer, not as unrelated tooling.

## Milestone Map

| # | Milestone | Depends On | Est. Days | Goal |
|---|-----------|------------|-----------|------|
| M62a | Export Contracts and Bundle v2 | M61b | 3-4 | Stable IDs, manifest-first contract, summary/detail split, compatibility policy, Tauri shell + loader skeleton |
| M62b | Viewer Data Plane and Spatial Foundations | M62a | 4-5 | Query-driven Rust data plane, PixiJS map foundation, timeline virtualization, level-of-detail rules, benchmark gate |
| M62c | Entity, Trade and Network Panels | M62b | 4-5 | Rich inspection panels, diagnostics, backlog integration, domain-specific affordances |

**Phase 7.5 estimate:** 11-14 days across 3 milestones/sub-milestones.

## Reactivation Gate (M61b -> M62a)

Phase 7.5 starts only when all conditions below are true:

- M61b canonical validation run is complete and accepted.
- Export surfaces needed by M62a are frozen for the current cycle (no pending schema-breaking PRs).
- At least one full-scale reference bundle from the accepted M61b run is available for fixture-driven viewer work.
- Ownership is explicitly assigned for Bundle v2 contract, Rust/Tauri data plane, and panel-layer work.

## Pre-Activation Assets

The following assets are partially scaffolded and should be treated as the starting handoff into M62a (see the prep plan checklist for remaining items):

- Bundle v2 contract draft: `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`
- M62a pre-activation execution plan/checklist: `docs/superpowers/plans/2026-03-24-m62a-preactivation-prep.md`
- M62b pre-activation execution plan/checklist: `docs/superpowers/plans/2026-03-30-m62b-preactivation-prep.md`
- Dormant viewer-side manifest fixtures and type scaffolding under `viewer/src/__fixtures__/bundle_v2/` and `viewer/src/lib/bundleV2.ts`

Scope note: this is doc-first and scaffold-first preparation only. Net-new Phase 7.5 feature work still waits for M61b acceptance.

## What Stays, What Changes, What Is New

| Category | Stays | Changes | New |
|----------|-------|---------|-----|
| Shell | - | Browser-only viewer -> Tauri 2 | `src-tauri/` app shell and IPC surface |
| Framework | React 19 + Vite + TypeScript | - | - |
| Map | - | Current SVG/d3-force-oriented world view -> PixiJS world surface | PixiJS map foundation and scene model |
| Charts | Recharts and existing chart patterns | - | Additional metric families for M62c |
| Panels | Chronicle/event/dashboard investment where still relevant | Panel set grows around Phase 7 systems | New character/settlement/campaign/diagnostic panels |
| Live mode | Existing WebSocket live connection path | Minimal adaptation only | Tauri host path for local app delivery |
| Bundle loading | Existing bundle-v2 terminology/types where useful | Browser-side monolithic loader -> Rust/Tauri query layer | Rust manifest parser, diagnostics, cache/index layer |
| Data processing | - | Browser-side heavy parsing is removed from the primary path | Query-oriented Rust viewer-core |

## Visual Direction From Current Inspiration

The current image set should be treated as moodboard input, not as a locked UI spec. It is still useful because it converges on a recognizable viewer shape and visual language that fits the Phase 7.5 goals.

### 2026-03-31 design synthesis

A focused mockup pass on 2026-03-31 produced a more coherent provisional shell than the earlier loose inspiration set. Treat the result as **execution guidance for M62b/M62c**, not as final pixel-perfect art direction:

- the strongest outputs converged on one reusable shell instead of per-mode one-off layouts
- **Overview** is the anchor view and should define the shell reused by Character, Trade, and Campaign
- **Trade** and **Campaign** validated the dark analytics workspace especially well
- **Character** validated the required content modules, but also showed the main failure mode to avoid: drifting into an editorial dossier that no longer feels like the same app shell

The main lesson: Phase 7.5 should implement **one durable product shell with multiple inspection modes**, not four bespoke screen families.

### Primary visual direction

- **Primary mode:** dark cartographic analytics workspace.
- **Use case fit:** best match for diagnostics, trade, campaign, knowledge, and multi-overlay inspection.
- **Core feel:** subdued terrain, restrained metallic accents, bright data overlays, and dense-but-structured inspection panels.
- **Map status:** the map remains the hero surface. Panels support the map; they do not replace it.

### Secondary visual direction

- **Secondary mode:** lighter parchment/archive presentation.
- **Use case fit:** static chronicle browsing, presentation screenshots, and an eventual "archive" or "atlas" view.
- **Scope note:** this is optional polish, not a Phase 7.5 blocker. The primary implementation target remains the dark analytics workspace.

### Layout guidance

The mockups consistently point toward one durable layout:

- **Top rail:** world/run metadata, live/archive state, timeline scrubber, and major event markers.
- **Left rail:** chronicle surface, grouped/filterable event log, search/filter tools, and mode/layer controls.
- **Center canvas:** map-first workspace with overlays, route/front/fog rendering, and hover/click inspection affordances.
- **Right rail:** inspector panel for civ/character/route/army/settlement detail.
- **Modal/detail sheets:** high-density character or campaign dossiers can open as focused overlays without replacing the main workspace.

This should be treated as the default shell for M62b/M62c unless benchmarking or usability testing gives a concrete reason to deviate.

### Provisional shell lock from the 2026-03-31 mockup pass

Until real implementation pressure proves otherwise, use the following as the default shell model:

- **Header:** compact top metadata bar with world/run identity, schema version, current turn, performance, and live/archive state
- **Timeline rail:** a dedicated scrubber directly under the header with era bands, major event markers, and optional causal-link cues
- **Left rail:** chronicle/event/navigation surface; narrow enough to preserve map space, rich enough to keep narrative context first-class
- **Center canvas:** map-first workspace with subdued cartographic terrain, quiet borders, and overlay-first interaction
- **Right rail:** persistent inspector for civ/character/settlement/route/army detail with compact cards and small high-value charts

Treat these as reusable shell primitives rather than mode-specific layout inventions. Character, Trade, and Campaign should all read as variants of the same application frame.

### Provisional design-system lock from the 2026-03-31 mockup pass

These visual decisions have now appeared consistently enough to guide implementation:

- charcoal/slate chrome as the default app frame
- muted brass/gold dividers and emphasis lines
- restrained cyan for interaction state and selected overlays
- dark parchment / subdued cartographic terrain as the main map treatment
- editorial serif headings paired with compact sans-serif data labels
- card-heavy inspectors with compact graphs instead of oversized dashboard canvases

This should be read as a **product-shell direction**, not as a demand for exact colors or pixel values from the mockups.

### Reusable interaction patterns worth carrying forward

- top timeline with era bands, event markers, and causal-link cues
- explicit civ selection from both map interaction and a persistent selector control
- inspector cards with small, high-value mini visualizations instead of large dashboard walls
- map annotation chips for armies, routes, and other active entities
- fog/awareness rendered as soft regional gradients, not hard binary masks
- hover preview -> click to pin -> inspect in right rail
- explicit layer toggles for diagnostics instead of hiding important overlays behind deep menus
- "actual vs perceived/stale" comparisons as first-class trade and knowledge diagnostics
- grouped/collapsible event rows so repetitive mechanical events do not swamp the left rail

### Panel design guidance

- Character detail should read like a dossier, not a game-RPG stats page.
- Campaign and trade views should feel like operational maps with analytical sidebars.
- Civ and settlement panels should prioritize composition, pressure, and trend summaries over raw field dumps.
- One panel should not try to show every graph at once; summaries first, deeper drill-down on demand.
- Right-rail inspectors should prefer tabs or collapsible sections when density climbs past a single-screen overview.
- Preserve shell continuity across modes. A character-focused screen can become denser, but it should still look like the same app as Overview rather than a separate poster-like artifact.

### Canonical screen archetypes from the mockup pass

The design work now gives M62b/M62c four concrete inspection archetypes to plan around:

- **Overview / Strategic Command:** map-first civ/region shell and the canonical layout anchor
- **Character Detail / Great-Person Deep-Dive:** memory, needs, relationships, dynasty, artifact provenance, movement, and Mule state
- **Trade Diagnostics / Logistics Observability:** route profitability, stale-vs-current beliefs, in-transit goods, market pressure, and role diagnostics
- **Campaign and Validation / Military Intelligence:** fronts, marches, supply, battle summary, knowledge freshness, asabiya, and oracle/validation affordances

These archetypes should drive reusable panel and overlay design rather than separate vertical products.

### Narrative and event-log guidance

- The viewer must preserve Chronicler's narrative identity, not just its analytics surface.
- Chronicle entries, era reflections, and gap summaries need an explicit home in the main shell.
- The chronicle surface can share the left rail with the event log via tabs, or appear as a toggleable companion panel, but it should not be buried behind secondary navigation.
- Event logs need first-class filtering by type/entity/civ/turn range and should support grouped summaries for repetitive bursts such as settlement foundings, migrations, or repeated skirmishes.
- The viewer should make it easy to move between narrative and mechanics: click from chronicle entry to turn, from turn to map, and from map selection back to related chronicle context.

### Map styling guidance

- terrain and borders should be quiet enough that route/front/knowledge overlays remain legible
- use glow selectively for active flows, fronts, or selected entities; avoid making the whole map neon
- labels should reveal by zoom and context; do not render every entity name at once
- region fills, route lines, fog, and diagnostic heatmaps need a shared color grammar so overlays can coexist

### Anti-patterns to avoid

Do not cargo-cult the mockups literally. Several common mockup failures should be avoided on purpose:

- unreadably small microcharts or inspector text
- too many simultaneous labels, arcs, and glow effects
- fake "everything visible at once" density that falls apart in real data
- decorative chrome that competes with the map
- mode-specific one-off layouts that prevent reuse across trade/campaign/knowledge/character inspection
- oversized editorial title treatments that consume too much vertical space in what should be a software shell

## M62a: Export Contracts and Bundle v2

**Goal:** Replace the implicit "one giant bundle blob" assumption with a versioned manifest-first contract designed for long-term compatibility and selective loading.

### Required deliverables

- Stable IDs for agents, named characters, civs, regions, settlements, dynasties, households, routes, armies, artifacts, factions, and faiths
- Bundle versioning policy with explicit backward-compat expectations
- Summary-vs-detail layer split
- Chunkable spatial/detail payload design
- Manifest shape for multi-part exports
- Compatibility story for archive/batch workflows that still want a simple artifact
- Typed timeline/event payloads that can carry character, civ, settlement, route, and army history without custom schema rewrites
- Generic metric/overlay registry so future phases can add new dashboards and map layers without changing the base loader contract
- Tauri shell scaffold with command surface placeholder for manifest open / summary load / layer query

### Packaging decision (planning lock)

| Option | Backward compatibility | Selective loading | Long-term schema evolution | Complexity | Planning decision |
|--------|-------------------------|-------------------|----------------------------|------------|-------------------|
| Monolithic JSON + optional chunks | Strong near-term | Weak-medium | Medium | Lower | Fallback only |
| Manifest-first (summary + layered detail payloads) | Medium (needs adapter) | Strong | Strong | Medium | **Default** |

**Planning default:** Bundle v2 is manifest-first, with explicit payload families.

**Compatibility fallback:** keep a legacy single-artifact export path as migration glue for archive/batch workflows and browser fallback.

### Contract rules

- Treat entity identity, timelines, metrics, overlays, and networks as first-class layers, not one-off panel payloads.
- Cross-layer joins must use stable IDs only.
- Reserve namespaces now for likely Phase 8-9 families such as institutions, cultural traits, prestige goods, patronage edges, revolt clusters, and diplomacy belief records.
- Loader diagnostics must be typed and actionable; missing required layers fail fast.

### M62a merge gate

- Golden fixture bundles for small, medium, and large runs (including one accepted M61b-scale fixture)
- Schema snapshot tests for manifest, IDs, timeline events, metric families, overlays, and network layers
- N-1 compatibility tests for additive changes
- Determinism checks on manifest/entity-ID stability
- Negative tests for missing layer, unknown layer kind, malformed manifest, and schema-version mismatch
- Legacy single-artifact adapter export produces valid output and browser loader can open it (browser fallback smoke test)

## M62b: Viewer Data Plane and Spatial Foundations

**Goal:** Build the scalable loading/rendering substrate before adding feature-rich panels.

### Core responsibilities

- Query-driven Rust data plane inside Tauri
- Manifest open, summary load, and slice-fetch IPC surface
- Cache/index policy for hot timeline, entity, and overlay paths
- Timeline virtualization
- Level-of-detail rules
- PixiJS world/map foundation
- Settlement overlays
- Regional knowledge/fog overlays
- Settlement precursor and attractor overlays where useful for diagnostics
- Trade-route rendering
- Army-march rendering
- Asabiya heatmap
- Frontier/core and influence overlays
- Generic layer toggles for current and future map-backed systems

### Scope guard

M62b is where the viewer becomes capable of handling Phase 7 scale. If schedule pressure appears, protect the query model, spatial loading rules, and map foundation first. Do not burn this milestone on panel polish.

### Data-plane performance budgets (draft merge gates)

These are practical budgets for M62b/M62c acceptance on modern desktop hardware:

| Metric | Budget (p95 unless noted) |
|--------|----------------------------|
| Manifest parse + summary load | <= 2.0 s |
| First map paint after bundle open | <= 1.0 s after summary load |
| Turn scrub latency | <= 120 ms |
| Overlay toggle latency | <= 150 ms |
| Entity panel open latency | <= 200 ms |
| Region-level drilldown fetch | <= 300 ms |
| Peak webview memory on large fixture | <= 2.5 GB |
| Hard failure threshold | no freeze > 3 s |

### Benchmark gate

M62b should include a targeted benchmark fixture and interaction trace:

- representative 500-turn scrub path
- representative overlay toggle path
- representative entity-panel open path

Use this benchmark to confirm whether React stays or whether the Solid fallback becomes worth its migration cost.

## M62c: Entity, Trade and Network Panels

**Goal:** Add the domain-specific inspection tools that make Phase 7 systems understandable to humans.

### Target panels and affordances

- Chronicle/narrative surface: chronicle entries, era reflections, gap summaries, and jump-to-turn affordances
- Event log surface: grouped mechanical events, filters, collapse/expand behavior, and jump-to-entity/turn affordances
- Character detail panel: memory timeline, needs radar, relationship graph
- Settlement detail panel: founding, growth, infrastructure state, pull factors, and notable residents
- Civ detail panel: factions, faith/culture composition, wealth/trade diagnostics, asabiya, and dynastic links
- Dynasty/household affordances: spouse/child links, legacy-memory context, succession order, and inter-civ marriage ties
- Artifact display on character and civ panels
- Mule indicator with memory-that-warped-them and active-window countdown
- Trade diagnostics: route profitability, stale-vs-current price views, in-transit goods, and merchant plans
- Knowledge diagnostics: familiarity, staleness, source channel, and confidence for cross-region information
- Army/campaign diagnostics: composition, morale, supply, target rationale, march history, and battle outcomes
- Cohort/community affordances: strong-tie clusters and grievance-rich group inspection

### Backlog integration rule

The deferred Phase 3-6 viewer backlog belongs here, after Bundle v2 and the M62b data plane exist.

### Shell interaction requirements

- Civ selection must be explicit and fast: map click, persistent selector, and turn-synchronized inspector state should all be valid entry points.
- Region/route/army clicks should update the right rail predictably instead of spawning inconsistent one-off panels.
- The main shell should support narrative-first and analytics-first workflows without changing the underlying layout model.

## Phase 7.5 Component Envelope

These are the user-facing capabilities the full Phase 7.5 build should support:

- Chronicle surface with chronicle entries, era reflections, gap summaries, and turn-linked navigation
- Grouped/filterable event log that remains usable on long runs with repetitive mechanical output
- Spatial map with zoom from region-level to settlement-level and, where feasible, agent-detail drill-down
- Settlement overlay and settlement detail panel
- Civ detail panel with economy/faction/faith/culture/asabiya summaries
- Trade-route visualization and route/market diagnostics
- Army-march visualization and campaign panel
- Character detail panel with memory timeline, needs view, and relationship graph
- Dynasty and household explorer
- Artifact display on character and civ panels
- Knowledge/familiarity overlay with freshness/fog semantics
- Asabiya heatmap overlay
- Cohort/community inspection for relationship clusters and trauma-bonded groups
- Validation/diagnostic mode for settlement, trade, determinism, and scale-pattern oracles

## Phase 7 Coverage Checklist

This is the minimum inspection surface the viewer should cover. Not every item needs a top-level panel, but every major Phase 7 system must be inspectable through some combination of panel, overlay, timeline, or diagnostic view.

| Phase 7 system | Minimum viewer surface |
|----------------|------------------------|
| Chronicle / curator outputs | Chronicle entries, era reflections, gap summaries, and mechanics-to-narrative cross-links |
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
| M60 campaigns and battle resolution | Army composition, march path, morale, supply, war-target rationale, and battle/casualty summaries |
| M61 validation and pattern oracles | Diagnostic mode for settlement plausibility, trade baseline comparisons, cohort scaling, and determinism/perf summaries |

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
| RegionMap | Trade-flow arrows (goods type + volume along routes) | M42-M43 |

### Phase 6 society (from dropped M46)

| Component | Feature | Source |
|-----------|---------|--------|
| CharacterPanel | Personality radar chart (3 axes: boldness, ambition, loyalty) | M33 |
| CharacterPanel | Character arc timeline (horizontal, key events marked) | M45 |
| CharacterPanel | Family tree (vertical, max 3 generations) | M39 |
| CharacterPanel | Social network (mini graph, relationships to other named chars) | M40 |
| CharacterPanel | Religious identity + faith icon | M37-M38 |
| RegionMap | Cultural identity overlay (color by dominant cultural values) | M36 |
| RegionMap | Religious majority overlay (color by dominant faith) | M37 |
| CivPanel | Wealth distribution histogram + Gini coefficient | M41 |
| CivPanel | Class tension indicator | M41 |
| CivPanel | Goods production/consumption balance | M42 |
| CivPanel | Trade dependency indicator | M43 |

## Bundle Surface Expected From Phase 7

Bundle v2 should expose at least:

- named characters with personality, dynasty, faith, arc type, relationships, memory, needs, Mule flags, utility overrides, and legacy-memory context
- civs and regions as stable first-class entities
- dynasties, households, marriages, and succession-order data
- faction composition and influence data
- cultural and religious map layers
- wealth distribution and goods economy surfaces
- trade routes, price-belief bands, and transit/reservation state
- resource, settlement, and spatial surfaces
- regional knowledge/familiarity/staleness data
- army, campaign, and battle-summary data
- regional asabiya
- artifacts
- validation/oracle summaries needed for diagnostic mode

This is the target contract envelope. Delivery should follow the manifest-first planning lock above, with explicit migration notes for any contract changes.

## Phase 8-9 Compatibility Hooks

Phase 7.5 should not implement Phase 8-9 early, but it should leave clean attachment points for them:

- reserve entity namespaces and manifest sections for institutions, ruler-legitimacy records, cultural traits, prestige goods, patronage edges, revolt clusters, and diplomacy beliefs
- keep civ/region/entity cards pluggable enough that PSI, legitimacy, institutional cost, or trait composition can slot in later
- keep the network substrate generic enough to render patronage, faction, alliance, and revolt-spread edges
- keep the event ledger generic enough to support institution enactment, ambition completion, trait adoption, embargoes, and revolutionary outbreaks without redesign
- keep the overlay registry extensible enough to add institutional reach, cultural trait concentration, prestige-good routes, and revolt heat without replacing the map stack

## Future Extension (Not Phase 7.5 Scope)

If later phases need both Tauri and browser clients to support rich layered bundle browsing, a shared Rust `viewer-core` compiled to both native and WASM is a valid follow-on direction. That is not an M62a/M62b requirement and should not block the Tauri-first plan.

## Estimated Implementation Footprint

Planning estimate: roughly 7,500-11,500 lines across TypeScript, Rust/Tauri, schema, and export-plumbing work. The point of Phase 7.5 is to make large-bundle loading and versioned compatibility explicit before agent-level inspection is promised.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Viewer scope balloons because bundle loading remains monolithic | High | Protect M62a and M62b. Stable IDs, Bundle v2, Tauri data-plane boundaries, and query slicing come before rich panels. |
| Backlog UI work crowds out the data plane | High | Defer Phase 3-6 backlog integration to M62c only. |
| Rust/Tauri data plane degrades into giant JSON IPC blobs | High | Keep IPC query-oriented. Frontend requests turn/viewport/entity windows, not full detail layers. |
| Viewer over-focuses on characters and underexposes civ/settlement/knowledge/campaign diagnostics | High | Use the Phase 7 coverage checklist as a contract. Every major Phase 7 system needs an inspection surface. |
| Schema churn from Phase 8 forces another rewrite | Medium | Stable IDs, manifest/layer split, and versioning policy land in M62a before panel work. |
| Agent-level rendering promises exceed practical performance | Medium | Use level-of-detail rules and chunked loading; do not require all-agent rendering at all zoom levels. |
| React overhead becomes the dominant scrub bottleneck | Medium | Run the explicit M62b benchmark gate before considering a framework rewrite. |

## Iteration Hook

This document is meant to be tightened again once M61b is accepted and the team is ready to build the viewer. At that point:

- replace provisional layer details with the actual accepted export surfaces
- lock the concrete IPC/query contract for the Rust/Tauri data plane
- confirm the React benchmark result
- assign named owners for M62a, M62b, and M62c

Reactivation trigger for status change from `Dormant` to `Active`:

- M61b accepted
- Bundle fixtures checked in
- M62a owner assigned
- Kickoff date set
