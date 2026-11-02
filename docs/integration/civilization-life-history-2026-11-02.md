# Recorded civilization life history

The optional `CivilizationHistory` panel adds a bounded sequence of exact
civilization observations and explicitly attributed event records. It does not
reconstruct a narrative or change simulation, bundle exports or existing readers.

## Identity and source audit

Civilization identity is its index in `world_state.civilizations`. Python retains
civilization records in that array (`snapshot_pruning.py`). Secession appends a
new object (`politics.py:check_secession`); realm restoration first searches for
an existing landless object and reuses its index, appending only if none exists
(`politics.py:check_restoration`). The exported legacy snapshot/event keys are
names, not identity IDs. The panel matches a key only when exactly one world
civilization has that name. Ambiguous names and unrecorded aliases remain
unknown; no rename is interpreted as a successor or conquest.

`civRows.civRowAt` deliberately supports last-observed display, while
`civDisplayRow` and `buildCivilizationViews` synthesize fallen display state after
rows disappear. Those display states are not evidence for this sequence. The new
reader consumes exact `history[n].civ_stats` rows and reuses the existing
array-keyed actor/event selection indexes in `bundleIndex`; it adds no new cache
or bundle framework.

Version-5 pruning retains the final landless row, then may omit subsequent dead
rows; governments in exile remain recorded. `pruned_civ_stats` stores omitted
changes for Python restoration, but the viewer intentionally does not reconstruct
it. A missing row can therefore establish neither a value nor a precise life
transition. The snapshot writer's `alive` flag is `len(civ.regions) > 0`, not proof
of permanent extinction. The UI labels the recorded flag and explains this limit.

An event's tick T is displayed at completed turn T+1. The panel includes only
actor-attributed events through tick selectedTurn−1, including separately stored
`named_events` (some coups have only that source). Named events are not converted
into invented timeline events. The existing event inspector is offered only for
an actual timeline event whose selection key is unique. Event types and original
descriptions are preserved. In particular, `restoration` also describes an
individual ruler returning to power (`succession.py`), so that type alone cannot
establish a realm's new identity or original/successor relationship.

Only explicit `secession` events currently establish lineage: the Python producer
records actors as parent, child. Both names must map to distinct, unique world
indices, both must have exact rows at that event's completed turn, and its event
selection key must be unique. All other predecessor/successor relationships stay
unknown. Neither first observation nor `world_state.founded_turn` establishes a
historical foundation; that field can be overwritten during restoration.

## Selection and mounting

```tsx
<CivilizationHistory
  bundle={bundle}
  currentTurn={currentTurn}
  civilizationIndex={worldCivilizationIndex}
  onSeek={onSeek} // optional; called only by explicit View turn
  onInspectEvent={onInspectEvent} // optional; actual unique timeline Event
  onInspectRegion={(regionIndex, name) => inspectRegion(regionIndex, name)} // optional
/>
```

The helper is `civilizationHistory(bundle, currentTurn, civilizationIndex)`.
Invalid/ambiguous identities or identities without bounded evidence expose no
final-world name or values. Historical values, leader names, regions and alive
flags come only from exact rows. Duplicate snapshot turns are ambiguous. A gap at
the selected turn stays unknown even when an earlier observation exists.

The sequence groups observations and events by completed date, in chronological
order. It initially shows the latest 20 matching dates, with an explicit earlier
page control; each date initially shows six events, with a separate reveal control.
Filters show all dates, recorded events, observed changes/first observation, or
missing rows. Changes compare dated observations and state the interval; they do
not assign a cause or reconstruct intermediate states. Region inspection is
available only for an unambiguous world region name/index. Source paths or dated
event pointers remain visible. Filtering, revealing and inspection preserve the
selected turn. Only a row's explicit **View turn** button invokes `onSeek`, and
only for an exact recorded civilization row.

## Qualification boundary

Focused helper/component tests cover sparse and pruned rows, future exclusion,
first observations, leader-name changes, restoration ambiguity, explicit lineage,
duplicate names/turns/event keys, named events, source pointers, pagination and
inspection without seeking. Node20.19.0 source tests, lint and type checks are
recorded externally under
`/workspace/shared/chronicler-multiwave-evidence/civilization-history`.
App mounting, combined viewer tests and actual browser qualification are owned by
the integration checkout. No simulation or scientific qualification is claimed.
