# Chronicler Viewer

Open a local legacy `chronicle_bundle.json` with **Open Existing** (any bundle
version; version 6 is decoded on load by `src/lib/bundleCodec.ts`). Expand
**Inspect region history** to filter exported region observations and events by
turn, region, and metric, with original-file identity and missing-data labels.
See [the inspector guide](../docs/viewer/experiment-inspector.md) for evidence semantics,
the deterministic fixture, and local browser QA. The panel is closed by default
and limited to static artifacts.

Bundles that record the simulation systems (epidemics, food, wars, finance,
diplomacy, techniques, maritime, nomads, agendas, governance, contact) also
get a **Simulation systems** panel below the map with one tab per recorded
system, a **Map layer** row (food, epidemics, wars, migration, techniques,
sea) and per-region food, war, epidemic and technique rows in the inspector;
bundles without them get none of these. See
[viewer-systems.md](../docs/integration/viewer-systems.md).

The **Finance** tab also shows who holds each realm's debt. A bundle written
with `--domestic-credit` names the lenders (foreign civilizations, merchants
by region, cities and guilds) with rates, interest due and write-offs; a
default bundle shows the domestic creditor class and foreign debt as totals.
See [domestic-credit.md](../docs/integration/domestic-credit.md), section 14.

## Live checkpoint browser QA (opt-in, not CI)

`scripts/qa-live-checkpoint.mjs` drives the live pause panel's **Save
checkpoint** and `--live --resume` in headless Chromium (Playwright,
`require("playwright")`). Start the viewer (`npm run dev`, or `npm run build`
and `npm run preview`), then from `viewer/`:

```sh
PYTHONPATH=../src node scripts/qa-live-checkpoint.mjs --python <python with chronicler's dependencies> \
    [--viewer http://localhost:5173] [--agents off] [--out DIR]
```

It starts its own `--live --simulate-only` sessions (stopped by their PIDs),
launches a 20-turn world from the setup form, saves a checkpoint at the pause
at turn 5, resumes it with `--live --resume`, checks the resumed viewer's
history and pause, and checks that a stale or missing session token is
refused. Screenshots, logs and `report.json` go to `--out`. See
[checkpoint-continuation.md](../docs/integration/checkpoint-continuation.md),
section 11.

## Commands

From `viewer/`, with Node.js 20.19+ or 22.12+ (CI uses 20.19.0):

```sh
npm ci                        # install the locked toolchain
npm run dev                   # Vite dev server
npm test -- --maxWorkers=2    # Vitest
npm run lint                  # ESLint
npm run build                 # tsc -b && vite build
npm run preview               # serve the production build
```

## Entry pages

`index.html` is the viewer. Three isolated demonstration pages use synthetic
fixtures only and never load production data:

| Page | Entry | Guide |
| --- | --- | --- |
| `combined-inspection-demo.html` | `src/demos/combinedInspectionMain.tsx` | [combined preview](../docs/viewer/combined-inspection-preview.md) |
| `event-ledger-demo.html` | `src/demos/EventLedgerDemo.tsx` | [event ledger](../docs/viewer/event-ledger-verification.md) |
| `settlement-inspector-demo.html` | `src/components/phase75/__demo__/SettlementInspectorDemo.tsx` | [settlement inspector](../docs/viewer/settlement-inspector.md) |

## Scripts

Opt-in tools in `scripts/`; none run in CI.

| Script | Purpose |
| --- | --- |
| `qa-live-checkpoint.mjs` | Live checkpoint browser QA (above). |
| `qa_region_history.py`, `qa_settlement_inspector.py`, `qa_event_ledger.py`, `qa_combined_inspection.py`, `qa_combined_accessibility.py` | Browser QA for the inspectors and demo pages; see the guides in [`docs/viewer/`](../docs/viewer/). |
| `perf-viewer.mjs`, `viewer-equivalence.mjs` | Performance measurements and rendered-DOM equivalence of two builds ([viewer performance](../docs/performance/viewer-2026-10.md)). |
| `qa-shell-journeys.mjs` | Desktop and phone journeys through the shell (load and switch worlds, select, rewind, cancel the compare dialog) on one build, or two builds compared step by step: DOM, ARIA snapshot, roles, screenshots and console. `--build a=DIR [--build b=DIR] --bundle FILE --bundle FILE --out DIR`. |
| `qa-recovery-skills.mjs` | Recovery-skills browser QA at desktop and phone width: the five Livelihoods panels dated to the slider's turn on real bundles, older bundles and a constructed missing-data variant (unknown, never zero), the live setup options and prerequisites, Save checkpoint, `--live --resume` and Fork, and Batch Lab cancellation. Needs a Python that imports `chronicler` and the native extension; usage in the script's docstring. |
| `build-harvest-observations.mjs` | Copy dated forecast observations from a decoded run into `src/__fixtures__/harvest_forecast_observations.json` unless given OUTPUT ([expansion inspectors](../docs/integration/expansion-inspectors.md)). |
| `build-transaction-observations.py` | Copy transaction summaries with source labels and hashes into `src/__fixtures__/transaction_observations.json` unless given `--output` ([transactions view](../docs/integration/transactions-view.md)). |

[scripts/README.md](../scripts/README.md#bundles-and-viewer-fixtures) lists
the generator of each JSON fixture in `src/__fixtures__/`, and the fixtures
without one. Regenerate a fixture only deliberately and review its diff.
