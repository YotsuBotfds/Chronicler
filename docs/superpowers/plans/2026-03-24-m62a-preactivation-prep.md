# M62a Pre-Activation Prep Plan

> **Status:** Active prep (Phase 7.5 still dormant until M61b freeze gate)
> **Date:** 2026-03-24
> **Roadmap anchor:** `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`
> **Design draft:** `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`

---

## Goal

Reduce M62a startup latency by preparing contract, test, and loader guardrails now, without violating the M61b freeze dependency.

---

## Done In This Prep Session

- [x] Drafted Bundle v2 contract design document with manifest-first shape, layer taxonomy, stable ID policy, diagnostics vocabulary, and test matrix.
- [x] Captured the dormant-state roadmap/activation checklist for Phase 7.5 so the contract work can merge before viewer implementation begins.
- [ ] Viewer-side manifest detection guardrail
- [ ] Viewer-side Bundle v2 compatibility tests
- [ ] Fixture skeleton under `viewer/src/__fixtures__/bundle_v2/`
- [ ] Typed loader abstraction (`bundleLoader`) for manifest-first ingest

---

## Ready To Execute Before M61b

### Task Group A: Contract Test Harness Skeleton

- [ ] Create viewer contract-test fixture folder layout for `small`, `medium`, and `large` (placeholder for large until M61b accepted artifact).
- [ ] Add schema snapshot harness for manifest and layer descriptors.
- [ ] Add negative fixtures: missing required layer, unknown layer kind, malformed manifest.

### Task Group B: Loader/Data-Plane Interface Scaffolding

- [ ] Introduce a typed loader interface that separates `manifest fetch`, `summary load`, and `layer fetch`.
- [ ] Add diagnostic envelope type to standardize loader errors across static and live modes.
- [ ] Add compatibility adapter interface for legacy single-artifact exports.

### Task Group C: Ownership and Merge Gate Readiness

- [ ] Assign owners for M62a contract, M62b data plane, and M62c panel layer.
- [ ] Define the explicit M62a merge checklist (tests, fixture coverage, compatibility notes, migration notes).
- [ ] Prepare kickoff issue template for M62a activation day.

---

## Must Wait For M61b Acceptance

- [ ] Final required field inventory from accepted scale fixture.
- [ ] Stable ID token derivation lock from canonical export inputs.
- [ ] Required/optional classification for each layer family from real export surfaces.
- [ ] Final chunk boundaries and prefetch behavior tuning for M62b.

---

## Activation Checklist (M61b -> M62a)

Use this exact gate before flipping Phase 7.5 from dormant to active:

1. M61b canonical validation accepted.
2. Export surface freeze declared (no pending schema-breaking PRs).
3. At least one accepted large reference fixture checked in.
4. Named owners assigned for M62a/M62b/M62c.
5. M62a kickoff date set and published.
