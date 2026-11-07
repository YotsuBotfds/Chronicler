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

Exact-record spans using a causal connector (`because`, `so`, `led to`) need an
explicit `record_links` provenance row with `from`/`to` fact ids, `join: "id"`,
`left_key`, `right_key`, and the shared `value`. The audit resolves both actual
objects and verifies the declared stable identity occurs in both named keys.
A regional or inferred join cannot authorize causal language and produces
`unsupported_record_cause`. This is a narrow structural safeguard, not a claim
that every same-id participation link establishes a real-world mechanism.
Default historical spans do not enter this new reserved-format check.

`scripts/connected_world_examples.py BUNDLE --output REPORT` is the read-only
finder and mechanical post-hoc story example path. It retains the first saved
row satisfying each explicit adaptation/failure/mixed observation rule across
A4-3, A6, B3, C4 and D1/D3/D4. Each example carries its exact citation, pointer,
source date, fields and provenance span; it reports unactivated categories as
`found: false`, retains constructed metadata and audits derived entries. Its
labels are observations, not treatment effects, qualification or proof of
safety. It writes no simulation fields and invokes no narrator/model. The
source run's command, source commit and extension identity must be recorded
separately; a saved bundle alone does not establish those generation facts.

Before accepting natural examples, create a receipt with the production strict
readers:

```
PYTHONPATH=src node viewer/scripts/validate-connected-records.mjs --bundle BUNDLE --python PY --out validation.json
PYTHONPATH=src PY scripts/connected_world_examples.py BUNDLE --validation validation.json --output examples.json
```

The receipt binds the exact bundle bytes and bundled reader source by SHA-256.
Only an `observed` package can supply a story fact. Absent, disabled, malformed,
unobserved or unavailable validation is listed as skipped; the finder does not
promote it into natural activation. A receipt for different bundle bytes is
rejected. Viewer development dependencies are required for the Node validation
step; unavailable validation remains an honest missing-evidence result.

Constructed saved demonstrations use the canonical optional
`metadata.constructed = {from: <64-hex source bundle SHA-256>, edits: [<nonempty edit descriptions>]}`.
The loader validates it and the viewer displays a visible "Constructed
demonstration" notice on the loaded app. Natural bundles without this explicit
marker receive no notice. Filenames, seeds and modes do not imply construction.
