# Experiment inspection lane transfer

- Base: public `edf72991cad58d6670b1f382c33d50d903a6054a` (PR13 included).
- Local branch: `experiment-inspector`. The commit containing this manifest is
  the complete lane artifact; resolve it with `git rev-parse experiment-inspector`.
- Private frozen `b665e198` science was not inspected or compared. No scientific
  mechanism, performance, or cross-baseline claims are made.
- No push, merge, default promotion, hosting, deployment, Drive write, external
  artifact transfer, paid service, credential/security change, or denied-read
  bypass was performed.

## Scope and ownership

This lane owns only the optional static region-history inspector in the existing
viewer. It reads existing legacy ecology history, region control, named events,
controller event context, and final per-good stockpiles. It does not overlap
fishery-stock, mutual-aid, or fertility-memory simulation mechanisms.

Files changed:

- `viewer/src/components/RegionHistoryInspector.tsx` and `region-history.css`:
  filters, sample-dot chart, paginated evidence tables, raw provenance, missing
  labels, final-only stockpiles and qualified event context.
- `viewer/src/components/phase75/AppShell.tsx`: closed-by-default, lazy-mounted
  disclosure on static inspection surfaces.
- `viewer/src/lib/regionHistory.ts`: read-only query helpers preserving source
  indices/JSON pointers; no interpolation, mutation, or food aggregates.
- `viewer/src/lib/artifactIdentity.ts` and `viewer/src/hooks/useBundle.ts`:
  original-byte SHA-256, BOM-aware decoding, and asynchronous load sequencing.
- `viewer/src/App.tsx`: identity wiring and static endpoint/live received-turn
  navigation bounds.
- `viewer/src/__fixtures__/region_inspection_bundle.json`: deterministic synthetic
  fixture with gaps, changing control, missing/zero values, explicit and contextual
  events, and separate grain/salt/timber final observations.
- Five new test files under `viewer/src/__tests__`, `components/__tests__`,
  `hooks/__tests__`, and `lib/__tests__`: 18 additional regression tests.
- `viewer/scripts/qa_region_history.py`: reproducible local Chromium smoke test.
- `viewer/README.md`, `docs/experiment-inspector.md`, and this manifest:
  entry instructions, evidence semantics, limits, verification, and transfer scope.

Python/Rust simulation code, export schemas, scientific evidence, reporting
defaults, package manifests/lockfiles, and roadmap activation status are unchanged.

## Verification and reviews

- `npm test`: 112 passing tests across 17 files.
- `npm run build`: TypeScript and production build passed. Vite reports a
  nonblocking >500 kB bundle warning (about 647 kB minified); this lane makes no
  large-layer performance acceptance claim.
- `npm run lint` and `git diff --check`: passed.
- `python scripts/qa_region_history.py`: passed in local Chromium at 1440×1100
  and 390×844, covering collapsed defaults, filters, original-byte identity with
  UTF-8 BOM, missing/zero/final goods, endpoint navigation, artifact replacement,
  horizontal table scrolling, and intercepted live received-turn following with
  the inspector excluded. No page or console errors.
- Fresh Sol6.1/high Tier 1 correctness review accepted after closing live-mode
  findings. Fresh Sol6.1/high Tier 2 acceptance review accepted and independently
  reran the exact-state suite, build, diff check, and Chromium QA. UTF-16 BOM
  compatibility finding was closed with LE/BE tests; snapshot-gap documentation
  wording was clarified.

## Transfer and remaining limits

Apply only this branch's commit to the public baseline after the owner's promotion
decision. This local result is not authorization to push or merge. A machine-
readable manifest and incremental Git bundle are prepared locally under
`/workspace/scratch/experiment-inspector-transfer.json` and
`/workspace/scratch/experiment-inspector.bundle`, with the final commit and hashes.

There are no unresolved blocking findings. Historic stockpile amounts and Arrow
agent-event sidecars are absent from this inspector's data contract. Live
initialization state is not presented as final state. Stable entity IDs,
large-layer indexing, and Tauri/Bundle v2 remain deferred. Fixture outputs are
contract demonstrations, not simulation/science validation.
