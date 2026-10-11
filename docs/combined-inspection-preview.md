# Isolated combined synthetic preview

The reviewed event ledger and temporal settlement inspector are composed at
`viewer/combined-inspection-demo.html`. This entry is a synthetic, nonproduction
fixture. It neither imports AppShell nor activates the simulation, live connections,
seed controls, native code, or schema changes. Production mounting remains gated by
M61b; this work does not establish acceptance.

From `viewer`, install the unchanged lockfile dependencies and start the local server:

```sh
npm ci --cache /tmp/chronicler-npm-cache
npm run dev -- --host 127.0.0.1
# Open http://127.0.0.1:5173/combined-inspection-demo.html
python scripts/qa_combined_inspection.py --evidence /tmp/chronicler-combined-qa
```

One Requested turn slider controls the event cutoff and exact-turn settlement
snapshot, including seeks from the population table. Example civilization selects
Alpha, Beta, or the intentionally empty Nobody example. Changing civilization resets
the ledger query/page/expansion and picks the example's known settlement ID. The
ledger Civilization control is disabled in this composition so Reset filters keeps
the shared actor scope. Standalone ledgers retain their existing editable control.

Settlement IDs and civilization ownership in the fixture are hand-authored selection
metadata. The event format exports actor names but no settlement IDs. Settlement
selection therefore does not imply an event-to-settlement join; the ledger continues
to show civilization events. Source event indices refer to the complete immutable
72-record fixture, including records excluded by scope/cutoff. There is no actor
backfill. Events order by newest turn and then source position, grouped by turn/type
within each 24-record page. Groups explicitly cover only their current page.

The fixture has 32 requested turns and two separately supplied settlement histories.
Alpha's 55 turn-3 migration records span three pages. A joint Alpha/Beta treaty
matches both actor scopes; an actorless weather record matches neither. The turn-33
future sentinel and its type/unique actor are never offered in the bounded preview.

Explore Alpha settlement 7 at turns 1/2/3/4/5: absence, founding, a stale source-turn-2
summary, a missing exact-turn snapshot, and recorded dissolution. Scrubbing back
restores the exact prior observation. Settlement 9 at turn 6 has deliberately missing
fields/timestamps. At turns 24/25 it retains source turn 23 with age 1/2, and has
23/24 historical rows (turn 4 is missing), crossing the 20-row population page bound.
Population observations preserve input order, source pointers, and source timestamps;
gaps never acquire inferred values. Beta ID 21 has a distinct population and region.
Close/reopen discards interrupted local UI while using the current shared controls;
Reload synthetic fixture restores Alpha/7/turn 3 and remounts both panels.

Keyboard pagination transfers focus to the available sample-navigation button at
each boundary. A population-row seek moves focus to the shared Requested turn
slider so it remains usable after the exact-turn table remounts.

Focused verification:

```sh
npm test -- src/demos/CombinedInspectionDemo.test.tsx src/lib/eventLedger.test.ts src/lib/settlementInspection.test.ts src/components/phase75/GroupedEventLedger.test.tsx src/components/phase75/SettlementInspector.test.tsx
npm test
npx tsc -b --force
npm run build
npm run lint
```

The default production build still uses only `index.html`. A standalone fixture build
can be made without modifying the production Vite configuration:

```sh
node --input-type=module -e 'import {build} from "vite"; await build({build:{outDir:"/tmp/chronicler-combined-preview",rollupOptions:{input:"combined-inspection-demo.html"}}})'
```

Chromium QA checks desktop/mobile, repeated/interrupted turn and selection flows,
lossless event/sample pagination, keyboard slider/select/disclosures/page boundaries,
and document overflow. These bounded examples do not qualify accepted M61b scale or
performance, Firefox/WebKit, screen readers, contrast, production map mounting, or
general entity-ID filtering. Existing production chunk-size warning remains.
