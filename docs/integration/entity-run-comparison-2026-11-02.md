# Per-entity completed-run comparison

`EntityRunComparison` adds a descriptive region/civilization table to two already
loaded `CompletedRun` inputs. It uses `readEntityTurn` and `compareReadings` for
exact selected-turn metrics. It does not change existing run comparison,
serialization, simulation or source readers.

## Matching contract

Index matching is available only when both `metadata.what_if` manifests pass the
existing manifest reader, have opposite baseline/intervention arms, the same
request, seed, checkpoint turn, horizon, mode and intervention, and agree with
both bundle seeds. Both headers must be exact at the declared checkpoint turn
and seed, with a common SHA-256. Source package digests must be valid and equal;
source/native/header identities and world summaries must agree. Native identity
must explicitly record absence or a valid found-binary digest. Any included
`current_identity` must agree with checkpoint package/native identity. World
region counts must match both inputs, civilization counts must fit both inputs,
and checkpoint entity prefixes must have compatible names/order.

These are consistency checks on recorded metadata. The viewer does not reopen or
independently authenticate checkpoint bytes. The table states this limit. No
experimental qualification follows solely from matching metadata.

Regions retain their verified checkpoint indices. Only the civilization prefix
already present at the common checkpoint has shared identity: new civilizations
appended separately after the fork remain separate/unmatched even when their
names and new indices coincide. Duplicate legacy world names cannot support a
numeric name-keyed reading. Compatible metadata therefore does not override an
ambiguous snapshot key or invent a historical alias.

Other inputs, including old files and insufficient/conflicting pair metadata,
match unique observed names with an explicit **identity unverified** warning.
Equal seeds or array positions do not establish a shared entity. If matching
names occupy different world indices, that fact remains visible and generates a
warning. The reader resolves each input's own regional array index, never the
other input's index. Mismatched names remain unmatched; ambiguous names cannot
produce a difference. Old historical civilization names without a world index
can retain their actual name-keyed snapshot values, with unverified identity.
Historical regional names without an unambiguous world index remain unknown.

## Observations and interpretation

Entity discovery uses only unambiguous snapshots through selected turn T. It
never lists future founders from final-world arrays. The selected numeric values
require an exact snapshot at T and, for civilizations, the actual row at T.
Gaps, ambiguous turns, shorter tails, omitted/pruned rows and absent or unsupported
regional model observations remain unknown. No final-world value or prior row
fills a gap. Recorded landless/fallen rows retain their actual values; the
writer's `alive=false` flag does not prove permanent extinction. Consequently
per-entity rows need not sum to aggregate landholding-only run metrics.

Civilizations offer population, controlled regions, unweighted food/need,
population-weighted food/need, treasury and outstanding debt. Regions offer the
completed regional model population and food/need. Existing source notes and
weighted-food denominator coverage are preserved. Ambiguous controlled-region
names prevent food/territory readings rather than selecting the first region.
Model population and native alive counts are not interchanged. No civilization
allocation is used to estimate an absent regional population.

The table shows both raw values, right-minus-left and relative change against
`abs(left)`. A zero left baseline has no percentage; non-finite differences stay
unknown. Ordering uses a single chosen measure's higher or lower difference, with
unknown differences last. Food/debt direction notes describe their units and
limits. No metric is promoted to an overall benefit, winner or opaque score.

## Mount and pure export API

```tsx
<EntityRunComparison left={leftRun} right={rightRun} turn={comparisonTurn} />
```

Each input is the existing `CompletedRun`. Kind, measure and ordering controls
keep the selected comparison turn. The table initially shows 20 entities and
reveals more with a native button. Scoped CSS keeps wide tables inside an
internal horizontal scroll container and stacks controls on narrow screens.

The pure helper is:

```ts
compareEntityRuns(left, right, turn, kind = "civilization", measure = "population")
orderEntityRunRows(summary.rows, "higher" | "lower" | "name")
```

The result is JSON ready: selected measure/turn, matching mode and sanitized
checkpoint/package digest/count evidence, raw per-side values/status/source
notes, differences, coverage counts, warnings and limits. It contains no raw
world, source header, file label, local checkpoint path or private output path.
Integration can append a bounded selection of rows to existing JSON/Markdown
exports. The helper consumes `readWhatIfManifest` generically; matching does not
assume a stability-only intervention schema.

## Verification boundary

Focused tests cover provenance conflicts, changed indices, reordered prefixes,
post-fork births, future exclusion, source metric values, weighted-food coverage,
landless records, older regional unknowns, missing tails/rows, duplicate names and
turns, zero/non-finite percentages, pure export privacy, ordering and bounded
accessible controls. Node20.19.0 focused tests, TypeScript and viewer lint are
recorded under `/workspace/shared/chronicler-multiwave-evidence/entity-comparison`.
Root owns App/CompletedRunCompare mounting, combined production checks and actual
phone/desktop browser qualification. No backend, native or default behavior
changes are included.
