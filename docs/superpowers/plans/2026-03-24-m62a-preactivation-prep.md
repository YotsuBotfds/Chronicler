# M62a Pre-Activation Prep Plan

> **Status:** Active prep (Phase 7.5 still dormant until the M61b freeze gate)
> **Date:** 2026-03-24
> **Roadmap anchor:** `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`
> **Design draft:** `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`

---

## Goal

Reduce M62a startup latency by preparing the contract, test, loader, and shallow Tauri-shell guardrails ahead of M61b, without violating the export-freeze dependency.

M62a is the contract gate. It is **not** the full viewer data plane. The prep work here should make activation day boring:

- the Bundle v2 contract is already framed,
- the merge gate is explicit,
- the browser fallback is protected,
- and the Tauri shell can boot without dragging M62b implementation forward early.

---

## Planning Lock Inherited From The Roadmap

- Tauri 2 is the canonical client for layered bundle browsing.
- Browser fallback remains limited to live mode plus legacy single-artifact bundle viewing.
- M62a owns the manifest/layer contract, merge gate, browser fallback smoke coverage, and only a **shallow** Tauri shell scaffold.
- M62b owns the real Rust query/data plane, PixiJS map foundation, performance budgets, and benchmark gate.
- Detail-layer format choice remains open until accepted M61b fixtures confirm it.

---

## Current State On `main`

The following baseline already exists:

- Bundle v2 contract draft exists.
- `viewer/src/lib/bundleV2.ts` exists.
- `viewer/src/lib/bundleLoader.ts` already detects Bundle v2 manifests and tells users to use the legacy single-artifact adapter until layered loading is active.
- `viewer/src/__fixtures__/bundle_v2/` already exists with starter fixture structure.

The following still needs explicit prep work:

- contract-test coverage
- typed loader/data-plane interface cleanup
- legacy adapter/browser smoke coverage
- Tauri 2 shell scaffold
- activation-day checklist and merge gate notes

---

## Workstreams Ready To Execute Before M61b

### Workstream A: Contract Test Harness

- [ ] Normalize the fixture folder layout for `small`, `medium`, `large`, and `negative`.
- [ ] Add schema snapshot coverage for manifest and layer descriptors.
- [ ] Add negative fixtures for missing required layer, unknown layer kind, malformed manifest, and schema-version mismatch.
- [ ] Document which fixture variants are placeholder-only until an accepted M61b artifact exists.

### Workstream B: Loader and Compatibility Interface

- [ ] Introduce a typed loader interface that separates `manifest open`, `summary load`, and `layer fetch`.
- [ ] Add a diagnostic envelope type that can be reused by browser and Tauri paths.
- [ ] Define the compatibility adapter interface for legacy single-artifact exports.
- [ ] Add browser-loader smoke coverage for the legacy adapter output.

### Workstream C: Tauri Shell Scaffold

- [ ] Initialize `src-tauri/` with Tauri 2 project structure (`main.rs`, `lib.rs`, `tauri.conf.json`, `Cargo.toml`, `capabilities/`).
- [ ] Add placeholder IPC commands for `manifest_open`, `summary_load`, and `layer_query`.
- [ ] Wire the existing Vite/React app into Tauri dev mode and confirm HMR works.
- [ ] Add only the filesystem/dialog/plugin plumbing needed to prove the shell boundary; do not start the full M62b query/data plane here.

### Workstream D: Merge-Gate Readiness

- [ ] Write the explicit M62a merge checklist in repo docs, not just in roadmap prose.
- [ ] Assign owners for the M62a contract work, M62b data plane, and M62c panel layer.
- [ ] Prepare kickoff issue/template notes for activation day.
- [ ] Record migration notes for the browser fallback and the future Tauri-first path.

---

## Must Wait For M61b Acceptance

- [ ] Final required field inventory from the accepted scale fixture.
- [ ] Stable-ID token derivation lock from canonical export inputs.
- [ ] Required/optional classification for each layer family from real export surfaces.
- [ ] Final chunk boundaries and prefetch behavior tuning for M62b.
- [ ] Confirmation of which detail-layer encoding path survives the accepted fixture review.

---

## M62a Activation-Day Sequence

When the gate opens, use this order:

1. Lock accepted large fixture into the fixture matrix.
2. Finalize stable-ID derivation inputs and required/optional layer status.
3. Land the manifest/layer contract and merge-gate tests.
4. Land the browser fallback smoke path for the legacy adapter.
5. Land the shallow Tauri shell scaffold and placeholder IPC surface.
6. Hand off the accepted contract, fixture set, and shell scaffold to M62b.

This ordering preserves the main principle: stable export contracts before rich panels.

---

## Draft M62a Merge Checklist

- [ ] Manifest-first contract shape accepted
- [ ] Stable-ID policy accepted
- [ ] Layer taxonomy and reserved namespaces accepted
- [ ] Typed diagnostics vocabulary accepted
- [ ] Fixture-driven contract tests passing
- [ ] N-1 compatibility coverage in place
- [ ] Negative fixture coverage in place
- [ ] Legacy single-artifact adapter export smoke passes
- [ ] Browser loader can open adapter output
- [ ] Tauri shell boots and placeholder commands are invokable
- [ ] Activation handoff notes for M62b recorded

---

## Activation Checklist (M61b -> M62a)

Use this exact gate before flipping Phase 7.5 from dormant to active:

1. M61b canonical validation accepted.
2. Export surface freeze declared (no pending schema-breaking PRs).
3. At least one accepted large reference fixture checked in.
4. Named owners assigned for M62a/M62b/M62c.
5. M62a kickoff date set and published.
