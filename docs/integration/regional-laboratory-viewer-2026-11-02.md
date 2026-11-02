# Regional observations and inspection prompts

This additive viewer slice reads `TurnSnapshot.regional_population` schema 1
inside bundle version 6 / transport version 1. Completed model `Region.population`
is distinct from completed native `agent_counts`, especially in shadow and
`demographics-only` runs. Arrays follow stable `world.regions` indices; controller
IDs follow stable `world.civilizations` indices. The strict optional reader checks
the clocks, lengths, integer counts, source names and nullable native/weight
contracts. Missing, malformed or future-version records read as unknown without
making an otherwise supported historical bundle unreadable. No civilization
population is allocated across regions and no final-world count fills a gap.

Region history offers model population, native agents alive and food / need.
What changed compares exact endpoints and keeps provenance/coverage notes for
both endpoints. Completed-run comparison adds all-region model/native totals and
a population-weighted food trajectory alongside the observed regional mean.
The weighted measure uses actual Phase 2 entry agent weights and ownership only;
completed counts and completed owners never substitute. Unknown food ratios are
excluded from the denominator, whose observed/eligible agent counts and regional
coverage are shown and exported. Missing weights or zero denominator is unknown.
Civilization weighted food selects Phase 2 controllers even after conquest;
its existing unweighted regional mean still describes completed controlled regions.

## Mount and selection API

Root App/AppShell integration owns the mount. Import `WhereToLook` from
`viewer/src/components/WhereToLook.tsx` and supply:

```tsx
<WhereToLook bundle={bundle} currentTurn={currentTurn}
  onInspectEntity={(entity) => { /* select entity and open history inspector */ }} />
```

`entity` is `HistoryEntity` from `lib/historyComparison`:
`{kind: "region" | "civilization", name: string}`. The callback should select the
entity and open the existing history view without seeking. Existing history
controls preserve local choices: remount `RegionHistoryInspector` with a key
including the requested entity when opening from a prompt, so that its initial
region/civilization selection is applied. CSS is imported by the component.
No App, AppShell, live connection or intervention panel is changed in this slice.

## Conditions and limits

Prompts require an exact, unambiguous selected-turn snapshot. Food distress is a
recorded ratio below 1. Sharp population change is at least 20% between the
stated nearest earlier unambiguous endpoint and selected endpoint with a positive
earlier model count. The window and both model source/mode labels are explicit;
no percentage is inferred for zero, new or unknown baselines. Debt trouble uses
positive arrears/shortfall or debt service exceeding nonnegative revenue with
positive debt. Migration uses completed-tick native agent flows, which do not
establish forced displacement. Recovery requires source-dated positive regional
health-care recoveries. Institutional prompts require recorded governance funding
below 1 or the simulation's political stress crisis flag.

Conditions for an entity are grouped; the first eight entities are shown in
stable recorded-region/civilization order with an explicit total and Show more.
There is no overall score, prediction, causal interpretation or background alert
feed. Missing coverage is stated; no matching conditions is not evidence of
well-being. Earliest, absent, new and fallen observations are not backfilled.
The implementation uses recorded fields only and cannot classify every possible
institutional or displacement event.

## Verification

Node 20.19.0, existing shared dependencies and no install/lockfile changes.
Affected viewer tests: 11 files / 118 tests passed. App TypeScript and full viewer
lint passed. `git diff --check` passed. Logs are recorded in the external
`/workspace/shared/chronicler-world-lab-evidence/viewer` evidence directory.
The root integration owns the complete viewer suite, build and browser checks.
This source slice does not qualify Python/native execution or scientific gates.
