# M62a: Export Contracts and Bundle v2 - Design Draft

> **Status:** Draft (pre-activation prep)
> **Date:** 2026-03-24
> **Depends on:** M61b accepted freeze gate
> **Roadmap anchor:** `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`

---

## 1. Goal

Define a stable, versioned Bundle v2 contract that:

- preserves deterministic identity across exports,
- supports manifest-first selective loading,
- separates summary and detail layers,
- and gives Phase 8-9 systems typed extension points without rewriting the loader.

This draft is intentionally pre-M61b: it locks shape and compatibility rules, not final field inventory from scale fixtures.

---

## 2. Scope

### In scope (M62a)

- Bundle v2 manifest shape
- Layer taxonomy and reserved namespaces
- Stable ID policy
- Versioning and compatibility policy
- Loader diagnostics contract
- Contract-test fixture matrix
- Tauri shell scaffold with IPC command surface placeholder for manifest open / summary load / layer query
- Legacy single-artifact adapter export and browser-loader smoke path

### Out of scope (M62a)

- Final chunk-size tuning and LOD thresholds (M62b)
- Final panel payload wiring (M62c)
- View-layer UX polish
- Detail-layer format choice (Arrow IPC is the likely path but deferred until M61b fixtures confirm it)

### Execution alignment with the Phase 7.5 roadmap

- The Tauri shell work in M62a is intentionally shallow: it proves the local-host boundary, app boot path, and placeholder IPC surface. It is not the full Rust query/data plane, which belongs to M62b.
- The browser fallback remains intentionally narrow in Phase 7.5: live mode plus legacy single-artifact bundle viewing. Full layered Bundle v2 browsing is not required outside Tauri.
- Detail-layer encoding remains open until accepted M61b fixtures confirm the right tradeoff. M62a locks the manifest/layer contract, not the final binary payload choice.

### Consumer-pressure points from the current design synthesis

The 2026-03-31 viewer mockup pass does **not** lock visual implementation details for M62a, but it does clarify which contract surfaces the shell will depend on from day one:

- header/run metadata for world name, scenario, seed, schema version, current turn, total turns, mode, and high-level run metrics
- timeline metadata for era boundaries, major event markers, narrated-vs-mechanical segmentation, and optional causal-link references
- chronicle/event-log payloads that can support left-rail narrative and filtered mechanical log views without ad hoc panel-specific schemas
- overlay and inspector-oriented data families so the map-first shell can select an entity on the canvas and populate the right rail through stable-ID joins

M62a should therefore protect these shell-driving families in the contract vocabulary even while deeper payload shape stays deferred to accepted M61b fixtures.

---

## 3. Contract Layers

Bundle v2 uses explicit payload families referenced by a manifest.

| Layer family | Purpose | Typical consumers |
|---|---|---|
| `summary` | Archive-grade run snapshot and high-level metrics | batch workflows, quick open |
| `entities` | Stable identity envelope and index maps | all entity panels |
| `timeline` | Typed event ledger and turn-indexed references | timeline scrubber, event diagnostics |
| `metrics` | Numeric families and dashboard-ready series | civ/region/entity charts |
| `overlays` | Map-ready regional/spatial data surfaces | map layers and fog/knowledge views |
| `networks` | Edge lists for relationships/trade/patronage-like graphs | graph and cluster tools |
| `detail` | High-cardinality detail slices (agent/settlement/campaign) | deep drilldown paths |

Rule: panel payloads compose from contract layers; panels do not define one-off schema roots.

### Shell-driving summary requirements

Even before deep detail layers are finalized, the accepted contract should be able to open a Phase 7.5 shell without custom wiring. At minimum, the `summary` + `timeline` families should be capable of supplying:

- top-shell run metadata
- era-band and timeline-marker metadata
- chronicle/era-reflection/gap-summary anchors or typed references
- enough civ/region/entity summary state to populate a first-pass right rail after selection

This is still a contract concern, not a final UI-schema freeze: the point is to avoid designing Bundle v2 as a data lake with no obvious shell-level open path.

---

## 4. Manifest Shape (Draft)

```json
{
  "manifest_version": 1,
  "bundle_schema_version": "2.0.0",
  "seed": 12345,
  "total_turns": 500,
  "generated_at": "2026-03-24T12:00:00Z",
  "summary_layer": "summary.core.v1",
  "layers": [
    {
      "id": "summary.core.v1",
      "kind": "summary",
      "version": "1.0.0",
      "path": "layers/summary.core.v1.json",
      "required": true
    },
    {
      "id": "timeline.events.v1",
      "kind": "timeline",
      "version": "1.0.0",
      "path": "layers/timeline.events.v1.json",
      "required": true
    }
  ],
  "namespaces": {
    "phase7": ["characters", "settlements", "campaigns", "trade", "knowledge"],
    "reserved_phase8_9": [
      "institutions",
      "cultural_traits",
      "prestige_goods",
      "patronage_edges",
      "revolt_clusters"
    ]
  }
}
```

Notes:

- `summary_layer` is the fast-open anchor.
- `layers[*].required=false` is allowed for optional enrichment.
- `path` is artifact-relative; alternate storage backends can be resolved by adapter later.

---

## 5. Stable ID Policy

Every first-class entity referenced by layer payloads must carry a deterministic stable ID.

### Required entity families

- character
- civilization
- region
- settlement
- dynasty
- household
- route
- army
- artifact
- faction
- faith

### Rules

1. IDs must not depend on allocation order, transient hash maps, or thread count.
2. IDs must survive additive schema evolution.
3. IDs must be unique within `(entity_family, run_seed)` at minimum.
4. Cross-layer joins must use stable IDs only; no positional joins.

### Canonical shape (draft)

`<namespace>:<family>:<token>`

Examples:

- `phase7:character:9f8f4c2a`
- `phase7:settlement:2d7a81b4`

`token` derivation is finalized at M61b freeze using accepted deterministic export inputs.

---

## 6. Versioning and Compatibility

Bundle v2 follows semver intent:

- `MAJOR`: incompatible contract change
- `MINOR`: additive backward-compatible layers/fields
- `PATCH`: non-structural corrections/documentation clarifications

Compatibility policy:

1. Viewer loader must support `N` and `N-1` `MINOR` versions for a fixed `MAJOR`.
2. Missing optional layers degrade gracefully with explicit diagnostics.
3. Missing required layers fail fast with actionable diagnostics.
4. Legacy single-artifact export path remains as migration adapter, not primary contract.

---

## 7. Loader Diagnostics Contract

Bundle loader errors should be typed and actionable:

- `MANIFEST_PARSE_ERROR`
- `MANIFEST_SCHEMA_ERROR`
- `UNSUPPORTED_MAJOR_VERSION`
- `MISSING_REQUIRED_LAYER`
- `UNKNOWN_LAYER_KIND`
- `LAYER_LOAD_FAILURE`
- `LAYER_SCHEMA_ERROR`

Each diagnostic must include:

- `code`
- `message`
- `manifest_version` (if parse reached manifest level)
- `layer_id` (when layer-scoped)
- `path` (if available)

---

## 8. M62a Contract Test Matrix

M62a merge gate should include fixture-driven tests for:

1. Small fixture (developer run)
2. Medium fixture (normal batch size)
3. Large fixture (M61b-scale accepted reference)
4. Deterministic identity snapshot checks
5. N-1 compatibility checks for additive change
6. Negative tests:
   - missing required layer
   - unknown layer kind
   - malformed manifest
   - schema-version mismatch
7. Legacy single-artifact adapter smoke:
   - adapter export produces a valid single-artifact bundle
   - browser loader can open the adapter output
8. Tauri shell scaffold smoke:
   - shell boots against the existing Vite/React app
   - placeholder manifest open / summary load / layer query commands are invokable against fixture data

---

## 9. Open Items Blocked by M61b Freeze

1. Final token derivation inputs for each stable ID family.
2. Final layer split boundaries for high-cardinality detail payloads.
3. Required-vs-optional designation for each Phase 7 export surface from accepted fixtures.
4. Hard thresholds for chunk sizing and prefetch hints (M62b handoff input).
5. Final query granularity and cache/index strategy for the Rust/Tauri data plane (M62b handoff input).

---

## 10. Pre-Activation Deliverables Completed in This Draft

1. Manifest-first contract shape and terminology lock.
2. Stable-ID policy and namespace reservation baseline.
3. Typed diagnostics vocabulary for loader behavior.
4. Fixture/test matrix outline for M62a merge gate, including browser fallback smoke.
5. M62a scope alignment with the roadmap: contract/test work plus shallow Tauri shell scaffold, while the full Rust query plane stays in M62b.
