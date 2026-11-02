# City institutional history — selected-turn viewer contract

The city history widget extends the existing Cities panel's data contracts with
exact selected-turn coverage, endpoint comparisons and traceable lifecycle
records. It is the first supported institution type. Learning-seat and guild
lifecycles are explicitly not covered by this widget; their existing panels
remain available. No export, simulation, backend or shared reader is changed.

## Mount and selection

```tsx
<InstitutionHistory
  bundle={bundle}
  currentTurn={currentTurn}
  selection={searchResult}
  onInspectRelated={(entity) => { /* inspect region/civilization, preserving turn */ }}
  onSelectEvent={(event) => { /* inspect this recorded event */ }}
  onViewRecordedTurn={(turn) => { /* deliberate seek */ }}
/>
```

Only `bundle`, `currentTurn` and nullable `selection` are required. Selection
uses `Pick<HistoricalSearchResult, "kind" | "identity" | "sourceRef">`. Supported
selection is `kind: "city"`, `identity: {namespace: "city", index: settlementId}`.
Null/unsupported/unresolved selections get an explicit empty state; a source
pointer or display name never substitutes for identity. The history model
recomputes its own name from snapshots through the selected turn, so stale
search display names are not carried into this widget. Integrators should also
clear stale selection when changing worlds.

Inspection callbacks do not request a timeline change. `onViewRecordedTurn`
belongs to separately labeled snapshot buttons. The model and component export
their TypeScript contracts from `lib/institutionHistory.ts` and
`components/InstitutionHistory.tsx`.

## Audit and supported evidence

The existing `lib/cities.ts`, `lib/learning.ts`, `lib/guilds.ts`, Cities and
Learning panels, `types.ts`, and backend city/scholarship/guild export contracts
were inspected first. Cities supply the strongest first useful scope:

- `history[n].cities.cities[]`: explicit settlement ID, dated name, region,
  lord, rank, residents, civic purse, charter, unrest, satisfaction and optional
  wares. Cities are absent from living lists after a fall. A missing city
  subsystem is different from a recorded empty list.
- `world_state.cities.cities/fallen[].history`: tuples of source tick, moment
  kind and backend event reference, joined only by explicit settlement ID.
  `_note` caps history at 60 entries while preserving founding. Other missing
  moments cannot be reconstructed as a complete lifetime.
- `cities._emit`, `_note`, `_found` and `_fall` use the running tick's
  `world.turn`; snapshot capture uses the incremented completed world turn.
  Thus history/event tick T is visible only at snapshot T+1. Explicit tuple
  dates are retained alongside displayed completed snapshot dates.
- `set_cities_enabled` can discard and recreate city state. Even one settlement
  ID observed on both sides of a gap does not prove uninterrupted institutional
  survival, rebuilding, restoration or a city moving site. The model does not
  join different IDs with the same name. Snapshot region/name changes are
  labeled recorded endpoint changes, with no resiting/restoration claim.

Only the matching final record's ID and timestamped history tuples are used.
Final record names, region, lord, peaks, charter, founded/fallen dates and fall
causes are never historical fallbacks. Founding/fall moments therefore require
an explicit dated tuple, not a first/last snapshot or a standalone final field.
The current title comes from the latest unambiguous observed city row through
the selected turn, or `City N (name unknown)` if there is no dated name.

Every retained moment preserves its original JSON pointer. Its event is attached
only when the event ID is globally unique and its source tick equals the tuple
tick. Missing, repeated or wrong-clock event references stay unresolved; no
event is guessed by display name, region or temporal proximity. Event text is
the backend's account, not an inferred explanation of every nearby metric.

## Coverage and comparisons

The exact selected snapshot supplies the displayed values and relationships.
There is no latest-row fallback. Duplicate snapshot turns and duplicate city IDs
yield ambiguous values. Missing subsystem rows, ID absence and sparse missing
snapshots stay distinct. Older bundles without optional city data show unknowns.
Only exact selected rows can offer related region/lord inspection links, and
the associated names must resolve unambiguously; lord links also require that
selected snapshot's civilization row. Final-world ownership is unused.

Comparisons use consecutive unambiguous observed endpoint rows of the same
settlement ID, preserve each field's source pointer, and state the exact window.
Sparse endpoints do not establish when a change occurred or institutional
continuity between them. Unknown optional values do not turn into measured
zeros or deltas. Rank/charter labels reuse the existing city helpers. Changes
in ownership, residents, purse or wares are observations, not causal benefits;
an increase does not establish recovery. Recorded falls do not by themselves
establish physical destruction. First/last observed dates are never relabeled
foundation/destruction dates.

Initial lists show eight recent entries each with a native reveal button.
Source details use native keyboard-operable disclosure controls. Scoped dark
styles wrap content and use 44px controls for phone layouts; no navigation URL
or private filesystem path is exposed.

## Checks and limits

Node 20.19.0 with existing shared viewer dependencies, no installs or lock edits:

- 20 new model/component tests pass; 39 including the earlier search checks.
  Cases include future-secret final fields/moments/events, same-tick visibility,
  sparse/missing/pruned data, duplicate IDs/snapshots/final records/event IDs,
  rename and region changes, same-name/different-ID separation, reappearance
  ambiguity, optional unknowns, rewind, independent inspect/seek and bounded UI.
- Full viewer lint, TypeScript and production build pass. AppShell mounting,
  broader viewer checks and actual phone/browser review belong to integration.
- External evidence is under
  `/workspace/shared/chronicler-multiwave-evidence/institution-history/`.

No claim of complete institutional history across resets or missing records,
all institution types, backend causal effects or generalized restoration is made.
