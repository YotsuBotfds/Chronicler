# V04 / H29 standalone event ledger

This implementation uses the historical `Event[]` contract at base commit
`2ab3b4814abb665c7b3d5c255152cf5767bbf25a`. It is independent of AppShell.
Phase 7.5 production mounting still requires the M61b gates in the viewer roadmap.
No simulation, native, export schema, shared type, or AppShell code was changed.

`viewer/src/lib/eventLedger.ts` intersects event types (OR within the requested
types), one civilization, and an inclusive turn range with a mandatory
`currentTurn` cutoff. Civilization matches an exact exported actor name. The
contract has no general entity-ID field; actor names are not durable entity IDs.
Missing/empty actor arrays match no focused civilization, and no unrelated events
are added to fill a page. An empty actor *name* remains distinguishable from an
unfiltered query.

Records sort by descending turn, with original source order within a turn. Each
entry retains the original event object and its original array index. There is
no content deduplication, even for identical-looking distinct events. Source
indices are relative to one artifact array, not persistent cross-artifact IDs.
The source array is treated as immutable and is never sorted or rewritten.

Pagination counts original event records: default 24, configurable up to 100.
Requested pages clamp to the available range. Each page groups those records by
turn and type, in first-occurrence order, with source order inside each group.
Grouping intentionally changes the interleaving of different types within a
turn; it does not change any event data. Group summaries say “on this page”
because a burst can continue on later pages. Expansion shows every individual
record, actors, consequences, importance, and source position. The page stays
bounded even when a group contains thousands of source records.

`viewer/src/components/phase75/GroupedEventLedger.tsx` provides labeled native
type/civilization controls, optional inclusive turn bounds, range errors, empty
states, reset, group disclosures with `aria-expanded`/`aria-controls`, and native
previous/next buttons. Filter or cutoff changes reset pagination and expansion.
An externally supplied civilization focus remounts the local query when it
changes. The reset button restores that external focus. Source shrinkage clamps
stored page state. End-page keyboard navigation moves focus to the available
paging button. Status changes announce the record count and page.

Future integration can pass civilization names via `civilizations` and connect
`onSelectEvent(event, sourceIndex)` to an inspector. Use an artifact identity as
the React `key` when replacing the whole source artifact. Mutating the input
array in place or treating source indices as cross-artifact IDs is unsupported.
The optional selection callback receives the original source event reference.

## Reproduce

```sh
cd viewer
npm ci
npm test -- src/lib/eventLedger.test.ts src/components/phase75/GroupedEventLedger.test.tsx
npm test
npx tsc -b
npm run build
npm run lint
npm run dev -- --host 127.0.0.1
```

In another terminal, with Python Playwright and Chromium available:

```sh
cd viewer
python scripts/qa_event_ledger.py --evidence /tmp/chronicler-ledger-qa
```

The QA URL is `http://127.0.0.1:5173/event-ledger-demo.html`. Its separate HTML
entry is served by Vite in development and is not part of the default production
build. It uses the existing viewer CSS and dependencies. The synthetic fixture
has 61 historical records, including a 55-record duplicate-containing burst,
three Beta settlements, one two-actor skirmish, missing/empty actor records, and
one turn-99 sentinel. It does not simulate anything or imply real export evidence.

Automated coverage includes all matches exactly once across pages, exact actor
queries, inclusive type/range/cutoff intersections, duplicate-looking records,
stable source references/order, page bounds/clamping, late-page filter changes,
invalid ranges, missing actors, empty type/actor names, a civilization literally
named `all`, selected-type rewind, repeated expansion, focus at paging boundaries,
and independent component IDs. Browser QA exercises Enter/Space disclosures,
Tab-to-inspection, native select keyboard operation, repeated interrupted rewind
and reopen flows, reload, exact Beta focus, future exclusion, and 390px layout.

Coverage gaps: Chromium only; no Firefox/WebKit, screen-reader, or automated
contrast audit. No accepted M61b-scale fixture, performance benchmark, production
mounting, or general entity filtering. The normal production build reports its
existing large JavaScript chunk warning; no dependency or bundle configuration
changes were made for this isolated feature.
