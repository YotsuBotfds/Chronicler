# Viewer Streamlining — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** delete the legacy viewer components and dead exports, add the live-message guard and dependency/lint hygiene, then extract shared validator, panel and shell primitives. **Architecture:** new unpinned `lib/` modules first; pinned files only in PR 6, after PIN-1. **Tech stack:** React 19, TypeScript 5.9, Vitest 4, ESLint 9, npm.
**Prerequisites:** none for PRs 1-5 and 7. PR 6 needs PIN-1 (DEC-1 option A). Spec: `docs/superpowers/specs/2026-11-08-viewer-streamlining-design.md`. Fetch `main` first. Export census script: `docs/superpowers/plans/2026-11-08-tools/viewer_exports.py` (run from `viewer/src`).

**Pin gate for every PR (run before editing and again before commit):**
```
.venv/bin/python scripts/refactor_preflight.py --fail-on-enforced $(git diff --name-only origin/main -- viewer) viewer/package.json
```
PRs 1-5 and 7 must exit 0. A non-zero exit means a touched file is pinned: stop, move that edit to PR 6.

## File map
| File | Change |
|---|---|
| `viewer/src/components/{ChroniclePanel,EventLog,FactionDashboard,Header,RegionMap,SetupLobby,StatGraphs,TerritoryMap,TimelineScrubber}.tsx` | delete (PR 1) |
| `viewer/src/components/__tests__/{components,SetupLobby,RegionMap}.test.tsx` | delete (PR 1) |
| `viewer/src/components/__tests__/FeatureRequests.test.tsx` | drop lines 67-86 and the line 11 import (PR 1) |
| `viewer/package.json`, `viewer/package-lock.json` | remove d3-force + types (PR 1); add esbuild devDependency, optional peer playwright (PR 3) |
| `viewer/src/lib/{colors,movements,food,faiths,apprenticeship,polity,comparisonGallery,investigationBookmarks}.ts` | delete dead exports (PR 2) |
| `viewer/src/hooks/useBundle.ts`, `lib/__tests__/transport.test.ts` | remove re-export, import from `lib/bundleFile` (PR 2) |
| `viewer/src/lib/liveMessages.ts` (+test) | new (PR 3) |
| `viewer/eslint.config.js`, `viewer/scripts/lib/playwright.mjs`, 9 `viewer/scripts/*.mjs`, `viewer/README.md` | lint scope, helper (PR 3) |
| `viewer/src/lib/{recordGuards,livelihoodRecord,download}.ts` (+tests) | new (PR 4) |
| `viewer/src/components/systems/{formatters.ts,SystemSection.tsx,SystemTable.tsx,usePaged.ts}` | new (PR 5) |
| `viewer/src/lib/{shellFeed,atlasLayout}.ts`, `bundleIndex.ts`, `bundleValidation.ts`, `components/phase75/AppShell.tsx` | extract, memo, single pass (PR 7) |
| enforced files: `hooks/useLiveConnection.ts`, `lib/historyComparison.ts`, `lib/whatIf.ts`, `lib/completedRunComparison.ts`, `lib/entityRunComparison.ts`, pinned panels and libs | PR 6 only |

## PR 1: Remove legacy components (task DEAD-1)
### Task DEAD-1: delete nine components, three tests, d3-force
- [ ] Step 1: Preflight the 9 components and 3 tests; expect no `ENFORCED`. Confirm no dynamic import: `rg -n "import\(" viewer/src/components/phase75/lazyPanels.ts viewer/src | rg -i "ChroniclePanel|EventLog|FactionDashboard|Header|RegionMap|SetupLobby|StatGraphs|TerritoryMap|TimelineScrubber"` returns nothing. Check docs: `rg -l "components/(SetupLobby|TerritoryMap|StatGraphs)" docs viewer/scripts viewer/README.md` (dated plans/specs stay as history; a current guide hit needs an edit).
- [ ] Step 2: `git rm` the nine `.tsx` files and `__tests__/components.test.tsx`, `SetupLobby.test.tsx`, `RegionMap.test.tsx`.
- [ ] Step 3: `FeatureRequests.test.tsx`: delete the `describe("the legacy setup lobby", …)` block (lines 67-86) and `import { SetupLobby } from "../SetupLobby"` (line 11). Remove any helper only that block used (`openFeatures` if unused: `rg openFeatures`).
- [ ] Step 4: `npm --prefix viewer uninstall d3-force @types/d3-force` (updates both files). Review `git diff viewer/package-lock.json`: only d3-force, @types/d3-force and d3 packages nothing else needs (recharts keeps its own d3-*).
- [ ] Step 5: Orphan sweep: from `viewer/src` run `python3 ../../docs/superpowers/plans/2026-11-08-tools/viewer_exports.py`; list newly test-only or unused symbols (expect `FACTION_COLORS`, `civChartRows`, `formatTurn`, `formatScore`, `DISPOSITION_COLORS` still used by MapViewport so keep). Delete orphans together with their tests only if no production use; otherwise leave for PR 2.
- [ ] Step 6: Verify: `npx --prefix viewer tsc --noEmit -p viewer/tsconfig.app.json` (clean), `npm --prefix viewer run test -- src/components src/lib/__tests__/civRows.test.ts` (pass; case count falls by the deleted tests only), `npm --prefix viewer run lint`, `npm --prefix viewer run build`, then `node viewer/scripts/perf-viewer.mjs sizes --build main=<old dist> --build branch=viewer/dist` (entry chunk unchanged or smaller).
- [ ] Step 7: Commit `viewer: remove unreachable legacy components and d3-force`. No CONTINUATION entry (no outcome change); add one line to the progress ledger.

## PR 2: Dead exports (task DEAD-4, unpinned slice)
### Task DEAD-4
- [ ] Step 1: Rerun `exports.py`; hand-review its three lists (word-match heuristic can miss re-exports and string-keyed use). Preflight every file you will touch with `--fail-on-enforced`; any pinned file (`whatIf.ts`, `completedRunComparison.ts`, `entityRunComparison.ts`, `types.ts`, `granaries.ts`, `transactions.ts`, `learningServices.ts`, `forecastDecision.ts`, `householdMobility.ts`) goes onto the PR 6 list instead.
- [ ] Step 2: Delete: `colors.ts` `factionColorDark`; `movements.ts` `movementsOf` and `reformKind`; `faiths.ts` `templeEventText`; `apprenticeship.ts` `apprenticeshipAt`; `polity.ts` `hasGovernanceRecord`; `investigationBookmarks.ts` `investigationBookmarkReference`; `food.ts` `famineSpans` (its 4 test files: `rg -l famineSpans viewer/src` — rewrite assertions to use `foodCrisisSpans` or drop them; do not weaken coverage of production code). Re-check `DEPOSIT_REASONS` (`titledTrade.ts`) and `MOVE_GROUPS` (`residenceLedger.ts`): delete only if still unreferenced.
- [ ] Step 3: Keep and annotate `/** Test seam. */` on `setDecodeWorkerFactory`, `setReferenceObjectPatches`, `clearComparisonGallery`.
- [ ] Step 4: For the internal-only value exports (99 in the first scratch run), drop `export` in unpinned files in batches by directory; `tsc` finds any miss.
- [ ] Step 5: `hooks/useBundle.ts:7` delete `export { parseBundle };` (line 7) and the unused import path if any; `lib/__tests__/transport.test.ts:6` change to `import { parseBundle } from "../bundleFile";`.
- [ ] Step 6: Verify: `tsc` as above; `npm --prefix viewer run test` (full viewer suite once, at the end of the PR; run focused files while working); lint; build.
- [ ] Step 7: Commit `viewer: remove dead exports and the useBundle parseBundle re-export`.

## PR 3: Tooling and live-message guard module (task FIX-8, unpinned slice)
### Task FIX-8
- [ ] Step 1: `lib/liveMessages.ts` with `parseLiveTurn(msg: unknown)` and `parseLiveInit(msg: unknown)` per spec section 3; reuse `isRecord` from `bundleValidation.ts:6`. Table-driven test `lib/__tests__/liveMessages.test.ts`: non-record, missing/NaN/negative/float `turn`, `civ_stats` array, `events` string, init with `world_state` missing arrays, a valid message built from `__fixtures__/transport_bundle.json` rows (must accept).
- [ ] Step 2: eslint: in `viewer/eslint.config.js` add after the first block `{ files: ['scripts/**/*.mjs'], extends: [js.configs.recommended], languageOptions: { ecmaVersion: 2022, sourceType: 'module', globals: globals.node } }`. Run `npm --prefix viewer run lint`; fix findings or add narrow `// eslint-disable-next-line` with a reason. If more than about 30 findings, narrow the glob to `scripts/validate-connected-records.mjs` and `scripts/lib/*.mjs` and note the rest.
- [ ] Step 3: esbuild: `npm --prefix viewer install --save-dev esbuild@^0.28.2 --package-lock-only`; `git diff viewer/package-lock.json` must change only the root `devDependencies` block (the installed 0.28.2 entry stays).
- [ ] Step 4: playwright: create `viewer/scripts/lib/playwright.mjs` exporting `loadPlaywright()` that does `createRequire(import.meta.url)("playwright")` in try/catch and throws the install hint. Replace the nine `require("playwright")` call sites (`perf-viewer.mjs:504`, `qa-connected-world.mjs:68`, `qa-household-retail.mjs:918`, `qa-live-checkpoint.mjs:42`, `qa-productive-recovery.mjs:892`, `qa-recovery-chain.mjs:652`, `qa-recovery-skills.mjs:837`, `qa-shell-journeys.mjs:233`, `viewer-equivalence.mjs:214`). In `package.json` add `"peerDependencies": {"playwright": ">=1.40"}` and `"peerDependenciesMeta": {"playwright": {"optional": true}}` (declares without installing; confirm `npm ci --dry-run` in the cloud container adds no second playwright). Document in `viewer/README.md` next to the QA section (line 29): "needs Playwright; cloud containers have it globally".
- [ ] Step 5: Verify: new test file, `lint`, `tsc`, `node --check viewer/scripts/*.mjs`, `node viewer/scripts/perf-viewer.mjs --help` or the script's usage path prints without a Playwright error (do not run browsers).
- [ ] Step 6: Commit `viewer: live-message guard module, lint scope, esbuild and playwright declarations`. The guard is not wired until PR 6.

## PR 4: Shared record guards, readers, download (task CON-9, lib slice)
### Task CON-9a
- [ ] Step 1: Create `lib/recordGuards.ts`: `isRecord`, `finite`, `amount` (finite ≥ 0), `integer(x, min=0)` (finite && isInteger, with min), `count` (`Number.isInteger(x) && x >= 0`), `safeCount`, `safeInteger(x, min=0)`. Test every variant against `2**53`, `1e300`, `NaN`, `-0`, `"1"`, `[]`, `null`.
- [ ] Step 2: Inventory with a script: for each `lib/*.ts` that defines a local guard, record its body text, whether the file is enforced (`refactor_preflight.py --json`, level `enforced`) and which shared variant it maps to. Output `/tmp/guards.tsv`. Migrate only unenforced files, one directory-sized commit at a time; replace the local definition with an import under the same local name (`import { count, finite } from "./recordGuards"`) so call sites do not change. Bodies that match no variant stay local and get listed in the PR description.
- [ ] Step 3: `lib/livelihoodRecord.ts`: `readLivelihoodRecord(snapshot, key)` doing only the envelope (see spec). Migrate unenforced `*At` readers (`workshops.ts`, `timberStock.ts` first); each reader's source-turn check stays inline. Per-reader tests must pass unchanged.
- [ ] Step 4: `lib/download.ts` `downloadText(name, text, mime)`; use it in `components/InvestigationPacket.tsx:10-17` only.
- [ ] Step 5: Verify: `npm --prefix viewer run test -- src/lib` (all pass with unchanged expectations — any edited expectation means a variant changed: stop), `tsc`, lint, build.
- [ ] Step 6: Commit `viewer: shared record guards, livelihood reader envelope, download helper`.

## PR 5: Systems panel primitives (task CON-9b)
- [ ] Step 1: Create `components/systems/formatters.ts` (`show`, `percent`, `words`, `notObserved`) by copying the most common local bodies (`rg -n "const show\b" viewer/src/components | sort | uniq -c`); test against the existing outputs of the three pilot panels.
- [ ] Step 2: `SystemSection({title, note, emptyText, children})`, `SystemTable` (wraps `systems-table-wrap`), `usePaged(rows, size)` returning `{shown, more, showMore}`. Class names unchanged so CSS is untouched.
- [ ] Step 3: Pilot on three unenforced panels (choose by `--fail-on-enforced`); run their tests and `AppShell.systems.test.tsx`. Then migrate unenforced panels in batches of about 10; stop when marginal benefit drops.
- [ ] Step 4: Verify: `npm --prefix viewer run test -- src/components/systems src/components/phase75/__tests__/AppShell.systems.test.tsx`, lint, build, and snapshot the rendered DOM of two panels before/after in a scratch test (`container.innerHTML` equality).
- [ ] Step 5: Commit `viewer: systems section, table, paging and formatter primitives`.

## PR 6: Pinned slice (needs PIN-1; tasks FIX-8, DEAD-4, CON-9)
- [ ] Step 1: Confirm PIN-1 merged; rerun the pin gate (it should now pass or the files are marked historical). If PIN-1 chose option B, write a reviewed inverse layer per file via `scripts/testing/reviewed_main_witness.py` or drop this PR.
- [ ] Step 2: `useLiveConnection.ts:258-300`: type `msg` as `unknown`; call `parseLiveTurn` for `case "turn"` and `parseLiveInit` for the running branch; on `{ok:false}` warn and `break`. Add tests to `hooks/__tests__/useLiveConnection.test.ts`: malformed turn leaves `bundle.history.length` unchanged; valid turn behaves as before (existing tests `:163`, `:211`, `:250`, `:289` stay unchanged and pass).
- [ ] Step 3: Delete `whatIf.ts` `recipePreparedMismatch` (+test), drop internal-only exports in `completedRunComparison.ts`, `entityRunComparison.ts`.
- [ ] Step 4: `historyComparison.ts:25-27` `exactSnapshot` delegates to `snapshotAtTurn` (from PR 7; sequence this step after it).
- [ ] Step 5: Migrate pinned libs to `recordGuards`/`readLivelihoodRecord` and pinned panels to the PR 5 primitives, `CompletedRunCompare.tsx:115` and `WhatIfPanel.tsx:86` to `downloadText`. Smallest diffs first.
- [ ] Step 6: Verify: focused tests per file, full `npm --prefix viewer run test`, lint, build, `scripts/run_python_oracle_checks.py` (the witness tests must not regress or must be the ones PIN-1 retired).
- [ ] Step 7: Ledger: CONTINUATION line for the live-message hardening ("malformed turn/init messages are dropped instead of recorded as turn 0"); commit `viewer: validate live WebSocket messages`.

## PR 7: AppShell extraction, memoisation, single validation pass (task CON-9c)
- [ ] Step 1: Baseline: `npm --prefix viewer run test -- src/components/phase75` and, with a production build, `node viewer/scripts/perf-viewer.mjs run --build main=<dist> --bundle guard=<file> --runs 5 --out /tmp/before.json` (needs the shared Playwright; coordinate CPU).
- [ ] Step 2: Move `AppShell.tsx:127-492` pure helpers into `lib/shellFeed.ts` and `lib/atlasLayout.ts` (exported, same signatures); keep types local to the new files. Add direct unit tests that reuse the existing cases from `AppShell.helpers.test.ts`.
- [ ] Step 3: Add `snapshotAtTurn(history, turn)` to `lib/bundleIndex.ts` (WeakMap on the history array → `Map<number, TurnSnapshot[]>`; return the row only when exactly one). Test duplicate turns → null, missing → null. Use at `AppShell.tsx:696`, `:726`. Do not edit `historyComparison.ts`.
- [ ] Step 4: Wrap in `useMemo`: `buildChronicleFeed` (:665) `[bundle, currentTurn]`; `buildCivilizationViews` (:656) `[bundle, currentSnapshot]`; `computeAtlasLayout` (:712) `[atlasRegions, regionControllers, atlasFrame]`; `buildEventFeed` (:749) `[bundle?.events_timeline, currentTurn, selectedEntity, observationSourceTurn]`. Note `regionControllers` must itself be stable: memoise it first.
- [ ] Step 5: `bundleValidation.ts`: merge the duplicate history/event walks (`:146-174`, `:181-186` vs `:213-224`) into one pass that records the first structural error and the first viewable error and returns structural first. Confirm `bundleFile.ts:96-100` really runs structure before viewable. Add the order test from the spec.
- [ ] Step 6: Verify: phase75 tests, `useBundleMalformed.test.ts`, `bundleValidation` tests, lint, build; rerun the perf command to `/tmp/after.json` and compare scrub times and load times (expect no regression; report numbers, do not claim a speedup without them); `node viewer/scripts/viewer-equivalence.mjs` for DOM equality.
- [ ] Step 7: Commit `viewer: extract shell helpers, memoise per-render work, single validation pass`.

## Done when
- [ ] The nine legacy components, three test files and `d3-force` are gone; `tsc`, `lint`, `build` and the full viewer suite pass.
- [ ] No test-only or no-consumer value export remains except annotated seams; the lists are reproducible by `exports.py`.
- [ ] Live `init`/`turn` messages are validated (PR 6) and a malformed `turn` no longer appends a row.
- [ ] `esbuild` is declared; Playwright is documented and optional-peer declared with no second install; `.mjs` scripts are linted.
- [ ] Shared guards replace local copies with no accepted-value change in any existing test.
- [ ] AppShell helpers live in `lib/`; four per-render computations are memoised with before/after perf numbers recorded.
- [ ] No pinned hash was rewritten; every PR's pin gate passed.
