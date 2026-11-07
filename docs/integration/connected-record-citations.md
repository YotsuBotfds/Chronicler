# Exact saved-record citations

The reserved opt-in format `s28.lh.recovery_crews.receipts.0.members.0.wage_milli`
names a concrete value of a livelihoods package in snapshot 28. Array indices
are zero based and local to this saved bundle; they are not stable entity ids.
`livelihood_fact_id` builds these ids; `resolve_record_pointer` returns the
actual RFC 6901 bundle pointer, saved value and completed-turn date. Supply a
fact to a narrator only after resolving it against the bundle it describes.
No simulation or default narrator consumes this new format automatically.
Historical snapshot citations keep their original resolution behavior.

A citation resolves only if the bundle contains exactly one such snapshot,
versioned livelihoods and package containers, the package's matching T−1
source date and the exact record or field. Missing rows, ambiguous duplicate
snapshots and future/mismatched package dates are rejected even if the
snapshot itself exists. The narration audit recognizes the reserved format
before its historical snapshot-only fallback, so an invented exact record
produces `unresolved_fact`. Existing future/date checks still apply.

Existence is not semantic validation or proof of causation. Package strict
readers validate model books; prose must distinguish the saved individual
record from aggregate regional context and quote unknown or null values as
unknown. An array pointer cannot establish identity across pool rebuilding.
No paid narration is required to exercise this: the focused tests resolve
natural template-23 recovery receipts and audit explicitly labelled
constructed missing/date/future variants.
