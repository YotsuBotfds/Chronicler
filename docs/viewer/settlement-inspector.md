# Historical settlement inspector (V05/H28)

This isolated implementation uses the timestamped legacy settlement summary already
exported by `src/chronicler/main.py:460–486`. It does not mount the Phase 7.5 shell
or alter simulation, export schemas, shared viewer types, or the map. Production
mounting still requires the roadmap's M61b gates.

## API and evidence semantics

`viewer/src/lib/settlementInspection.ts` owns local types and three entry points:

- `inspectSettlement({ requestedTurn, settlementId, snapshot, sourcePath? })`
  consumes only an exact-turn historical snapshot: `turn`, `active_settlements`,
  `settlement_source_turn`, `founded_this_turn`, and `dissolved_this_turn`.
- `inspectSettlementHistory(history, requestedTurn, settlementId)` locates that
  exact snapshot, preserves JSON pointers and rejects duplicate turn records or
  an active summary after this ID's earlier recorded dissolution. ID reuse is
  invalid under the producer's monotonic settlement ID/lifecycle contract.
- `settlementPopulationHistory` returns bounded-window observations in original
  source order; the component paginates them to 20 rows. `settlementOptions`
  preserves summary/list order and uses only the requested snapshot's labels.

Each summary field returns its recorded value, source pointer, and explicit
unavailable reason. Population is an estimate; centroids retain exported units
and precision. Missing fields are not zero. ID 0 means no settlement. No world
state is accepted by this API. Gaps are unavailable, without nearest-turn,
forward-fill, interpolation, or terminal-state substitution.

An absent ID means **not listed in this snapshot**. Absence alone establishes
neither a founding time nor dissolution. The dissolution list explicitly labels
a recorded dissolution; an absent active summary has no population or centroid.
Founding and dissolution list membership is described as recorded in the
snapshot, rather than assigning an inferred event time. Missing lists differ
from present empty lists.

Observation age is `requestedTurn - settlement_source_turn` when both timestamps
are valid and the source is not in the future. A positive age is clearly labeled
stale. A missing/invalid source timestamp leaves age unavailable while preserving
otherwise valid fields in an exact timestamped snapshot. A future source turn,
unknown/mismatched snapshot timestamp, duplicate ID/turn, or contradictory lifecycle
record makes the observation unavailable. The producer advances the source turn
even when detection is skipped, so this age does **not** prove when detection last
ran or each population/centroid last changed.

`SettlementInspector` is controlled by `history`, `requestedTurn`, `settlementId`,
and `onSelectSettlement`. Optional `onSeek` and `onClose` callbacks let a later
host coordinate navigation. Native select/buttons/disclosures provide keyboard
interaction; the status announces as-of semantics. Turn/selection changes reset
population pagination, and same-turn history replacement clamps it. Infrastructure,
pull factors, residents, peak population, and last detection time are explicitly
unavailable under the current summary export.

## Isolated local demo and verification

```sh
cd viewer
npm ci --cache /tmp/chronicler-npm-cache
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
# Open http://127.0.0.1:5173/settlement-inspector-demo.html
python scripts/qa_settlement_inspector.py
```

The separate HTML entry imports only the inspector, a six-turn hand-authored
fixture, React, and existing viewer styles. Turn 1 precedes founding, turn 2 has
exact population/centroids, turn 3 is stale, turn 4 has no snapshot, turn 5 records
dissolution of #7, and turn 6 has missing timestamps/fields for #9. The normal
`index.html` entry and AppShell do not import this demo or the inspector.

```sh
npm test -- src/lib/settlementInspection.test.ts src/components/phase75/SettlementInspector.test.tsx
npm test
npx tsc -b
npm run build
npm run lint
```

The local Chromium script checks actual keyboard arrows/Home/End, native select,
Tab order, Enter/Space disclosures, historical seek, source pointers, repeated
scrubbing/selection, close/reopen while changing turn, reload, missing fields,
desktop/mobile values, and page overflow. It writes screenshots and a JSON receipt
under `/tmp/chronicler-settlement-qa` by default. Requires Python Playwright and
Chromium, with no additional viewer dependency.

Coverage gaps: production AppShell/map mounting, accepted M61b-scale artifacts,
scale/performance budget qualification, Firefox/WebKit and assistive-technology
runs, and domain details absent from historical summaries. No simulation/native
qualification is claimed for this viewer-only change.
