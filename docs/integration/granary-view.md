# Public granary history and viewer

The Food tab now reads a per-turn public-granary record, including stocks,
targets, received procurement, releases, storage spoilage, seizures,
abandonment and recorded keepers. The simulation's existing
`--grain-reserves` switch remains default off. This work changes observation
and display only; it does not change procurement, release, ownership or any
other simulation decision.

## Record and timing

`history[n].grain_reserves` is optional, like the other system summaries.
`grain_reserves.snapshot_summary(world)` reads the completed turn without
calling the mutating `_ensure` helper, drawing randomness, rounding floats,
clearing signals or retaining references to mutable model data. The main
snapshot builder calls it only while `grain_reserves_active(world)` is true.
Disabled granaries and a saved granary setting dormant under `--agents off`
add no field to a snapshot.

A snapshot at turn T records state after simulation turn T-1. Its explicit
`source_turn` is T-1; flows are included only when the state's `flows_turn`
matches it, so stale movements cannot repeat in a later snapshot.

The summary contains:

- `source_turn`: the completed simulation turn.
- `granaries`: one row per existing granary, in region order: `region`
  (index), `region_name`, recorded `owner` (civ index, -1 without a keeper),
  `owner_name`, territorial `controller`, `grain`, `target` and `observed`
  (number of harvest observations). Uninitialised granaries are not invented.
- `flows`: copied `ReserveFlow` fields, with `kind` as a readable name and
  snapshot `buyer_name`/`seller_name`. Procurement `amount` is received grain;
  `sent` is grain leaving the market and `cost` is treasury paid. Release
  `before`/`after` are the recorded food sufficiencies.
- `counters`: copied cumulative counters, for downstream historical readers.

The keeper is taken from the granary state, not inferred from the controller.
An ownership change during a turn can leave them different until the next
Phase 2 settlement; the viewer labels both. Captures record a change of keeper
without treating the captured stock as newly procured grain.

## Viewer and compatibility

The Food tab is available when a bundle records granaries even if it has no
mutual-aid food summary. The granary section shows totals, a region selector,
stock/target and procurement/release/spoilage charts, keeper strips, a region
table and the completed turn's individual movements. Region and keeper links
use the shell's existing inspection/navigation callbacks. Procurement shows
source markets, sellers, received/sent grain, transit losses and payments;
releases show food sufficiency before and after.

Tables read only the selected snapshot. Charts and keeper strips stop there;
missing old records are gaps, never inferred zeroes or final-world stocks.
Before the first recorded summary the viewer says ownership and stocks are
unknown. Older bundles with no summaries show a short explanation rather than
reading their end-of-run `world_state.grain_reserves`. A target without any
harvest observations is labelled `Not observed` in the region table.

The shared `transport_contract.json` names the new optional summary, so static
files, Batch Lab, streaming turns and reconnects carry the same data. Both
languages' transport tests continue to read the shared fixture. Its granary
entry is an explicitly empty shape stand-in, like its existing agent-only
food/migration stand-ins; nonempty granary stocks and flows have separate
Python and viewer tests.

## Debt-holders integration

This branch also carries the five new commits from PR #68. Review found no
simulation-conservation or default-off blocker. Two historical-display
follow-ups preserve unknown values when an explicitly allowed source-mismatch
resume joins older snapshots without named holders to newer ones: per-lender
allocations and cumulative write-offs remain unknown in the older rows, and
an unknown interval is not attributed as a new write-off on its first named
observation. Before the first finance snapshot the panel says there is no
record rather than claiming no debt.

## Validation

- Focused Python granary, historical-transport and domestic-credit suites:
  99 passed, 2 native tests deselected before the native build was available.
- Source cb9fe70c against this implementation, seed 42, 15 turns, agents off:
  all 9 output files match, with only bundle `generated_at` normalised.
- Fresh frozen-cb9fe70c native extension: both granary native tests pass,
  including the 60-turn hybrid resource ledger and final stock/snapshot
  parity. Seed 42, 35 hybrid turns with grain reserves enabled, base versus
  this implementation: 10 files match after decoding the bundles and removing
  only the 35 new summaries and `generated_at`. State, agent events and every
  other file match byte for byte. Native extension SHA-256:
  `43243cb026c6a6a141d15a5df743c96f8aca05c6bdc7c5ce1adbda8e31a6afd5`.
- Tests cover read-only/copy isolation, stale flow suppression, ownership
  versus control, disabled/dormant field omission, v6/static/live/Batch Lab/
  reconnect preservation, unknown historical gaps and as-of-turn rendering.
- Focused viewer history, transport and component checks: 25 passed. The first
  full run hit the existing 5-second timeout in exhaustive index comparisons
  under host contention. Those comparisons now run in bounded turn ranges,
  preserving their entire domains, assertions and the default timeout; see
  [viewer parity checks](../performance/viewer-parity-tests.md). The full
  viewer subsequently passed 621 tests across 60 files. Integrated index
  checks passed 168 tests; lint and the TypeScript/Vite production build passed.
- Production-browser smoke with Chromium at 1440 px and 390 px verified real
  35-turn hybrid granary data while scrubbing turns 1, 18, 35 and back to 2.
  Stocks, targets and keepers matched each selected snapshot. Missing records
  remained unknown, and legacy bundles never used final-world granaries as
  history. No console/page errors or horizontal page overflow; narrow tables
  scroll within their containers.

No calibration gate is claimed by these observation-only changes.
