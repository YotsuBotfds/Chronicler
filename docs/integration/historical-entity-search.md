# Historical entity search — viewer handoff

This additive viewer component searches recorded names through the selected
turn. It does not seek when inspecting. The AppShell mount and combined browser
checks belong to the integration branch; this slice changes no existing reader,
AppShell, backend, serialization or dependency lock.

## Mount contract

```tsx
<HistoricalSearch
  bundle={bundle}
  currentTurn={currentTurn}
  onInspect={(result) => { /* open details; mapEntity can open name-based history */ }}
  onViewRecordedTurn={(result) => { /* explicitly seek result.turn if non-null */ }}
/>
```

`HistoricalSearchResult`, exported from `viewer/src/lib/historicalSearch.ts`,
contains `kind`, `identity`, `name`, `turn`, `sourceRef`, first/last recorded turns,
`status`, `aliases`, optional `ambiguity`, and optional `mapEntity`. The latter
is `{kind: "region" | "civilization", name}` and is only supplied for an
unambiguous historical observation. Inspect must preserve the selected turn.
`onViewRecordedTurn` is optional; only its separate button requests a seek.
Source references are bundle JSON pointers, never local paths or navigation URLs.

`identity` is `{namespace, index}` or null. Region/civilization indices refer to
their world arrays. City IDs are recorded settlement IDs; learning seats and
guilds have explicitly documented world-list IDs (`types.ts`,
`docs/integration/scholarship.md`, `docs/integration/guilds.md`). Names are labels,
not IDs. Duplicate legacy canonical names cannot be safely mapped to name-based
history. Static duplicate regions retain their real indices, unknown dated
coverage, and an ambiguity label. Civilization names with repeated/no matching
world records have null identity. Duplicate institution IDs within a snapshot
remain separate unresolved source observations.

## Evidence boundaries

- Only unique snapshot turns at or before the selected turn are read; duplicated
  snapshot turns are excluded and counted. Source array order/pointers remain
  intact even when observations arrive out of order.
- Static region names may identify map locations before their first observation;
  historical presence and ownership remain explicitly unknown. No final owner,
  population, leader, city or institution state supplies historical values.
- Civilization names originate in dated `civ_stats`; a final later-founded realm
  is absent before its recorded observations. Fallen rows remain searchable;
  subsequent missing rows are gaps, not inferred extinction dates.
- Cities, seats and guilds originate in their dated snapshot arrays. Earlier
  observed names under the same recorded ID can match, with dated source refs.
  First/last observed dates are not foundation/lifetime claims.
- Snapshot named actors have no stable person IDs. Search retains the most recent
  200 individual leader/great-person observations, counts all observed rows, and
  never joins repeated names into a life history or aliases. A repeated display
  name may represent different people. Earlier actor observations beyond the
  disclosed bound are not searched.
- Language aliases use explicit numeric region/civ references and dated word
  forms only. `languages._Turn.t = world.turn - 1`: source tick T is visible from
  completed snapshot T+1. Alias `turn` uses snapshot visibility; optional
  `sourceTurn` preserves the original tick. Undated final tails, language names,
  person-name tables and future forms are excluded. Missing alias coverage stays
  unknown. Events are not mined for entity identities.
- The index rebuilds for the selected bundle/turn, queries debounce 160 ms and
  rendered results cap at 30. Type and name filters narrow the list. Native
  inputs/buttons/select/details support keyboard use; controls have 44px minimum
  height and scoped, wrapping dark styles. No platform search or URL navigation
  is added.

## Focused verification

On Node 20.19.0, using the existing shared dependencies without installing or
changing locks:

- Two new focused files: 19 tests passed. Regressions include sparse/older data,
  extinct records, duplicate names/IDs, namespace identity, individual repeated
  actors, bounded coverage, out-of-order source pointers, debounce/rewind,
  inspect versus explicit seek, dated alias clocks and future-secret names.
- Full viewer lint, TypeScript project build and Vite production build passed.
  The production entry is unchanged here; AppShell mounting remains integration
  work. No full viewer suite or browser qualification is claimed by this slice.
- External logs: `/workspace/shared/chronicler-multiwave-evidence/historical-search/`.
  No generated evidence or machine environment is committed.
