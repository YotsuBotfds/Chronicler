# Additive native named-character context reader

This source-only child starts from exact `23d4d246`. It adds
`AgentSimulator.get_agent_context_batch(agent_ids)` and native regression
source. Every existing getter and every Python source file remain unchanged.
The bridge still uses its original three scalar reads per active agent-backed
GreatPerson. No simulation behavior, default, option or checkpoint field changes.

Hybrid named-character sync currently calls memory, needs and relationship
getters in that order for each active GreatPerson. All three locate the same
live agent with a linear pool scan. Normal native promotion caps living named
characters at 50 globally and 10 per civ, so this is at most 150 scans/crossings
per turn under that registry contract. Imported/custom Python records are not
assumed to obey that cap. Whether this is a meaningful wall-clock hotspot is
unmeasured; no optimization gain or larger supported world is claimed.

## Read contract

The new method takes a sequence extracted by PyO3 as `Vec<u32>` and returns a
Python list of `(agent_id, memories, needs, relationships)` tuples. Each input
has one output in the same order; duplicates remain duplicates with independent
returned lists. The three payloads use the scalar getters' exact tuple field
orders, bounded native store order and f32 conversion.

A sorted, deduplicated local query vector finds matching slots in one ascending
pool pass. The first live duplicate ID wins. No dense ID-sized table, randomized
map, Arrow batch, registry index, lasting cache or simulator field is added.
Storage is proportional to the number of requested IDs, even for `u32::MAX`.
The slot-resolution work is one A-slot pass plus `O(A log U + P log U)` searches,
where P is input length and U its unique ID count. Empty input does not visit
pool vectors. This structural description is not a measured speedup.

| Case | Memories | Needs | Relationships |
| --- | --- | --- | --- |
| Live agent | Memory tuple list | Six-float tuple | Relationship tuple list |
| Unknown/dead agent | `[]` | `None` | `None` |
| Live agent with empty stores | `[]` | Six-float tuple | `[]` |
| Manually constructed live ID zero | Its memory list | Its needs tuple | `None` |

The zero-ID distinction preserves the original methods: memory/needs scans do
not special-case zero, while `find_slot_by_id(0)` refuses relationship lookup.
Normal spawning begins at one. An earlier dead duplicate does not hide a later
live slot, and a reused slot supplies no context for its former ID.

The new vector argument is fully converted before its method body runs. A bool
is accepted by PyO3's u32 conversion as 0/1; negative/out-of-range IDs should
raise OverflowError, and non-indexable values should raise TypeError. An
object's `__index__` can run during conversion. These boundary predictions and
written tests are **unrun** for this source. They do not claim equivalent error
or partial-write timing to three scalar calls interleaved with Python writes.
Existing scalar API behavior stays unchanged.

## Written native contracts — all unrun

The new [Rust test module](../../chronicler-agents/src/ffi/agent_context_tests.rs)
contains ten test functions:

- `context_batch_empty_does_not_visit_pool_vectors`: empty input against a
  deliberately incomplete pool catches accidental lookup construction/scans.
- `context_batch_keeps_input_order_duplicates_and_missing_shapes`: compares
  complete rows with all three actual existing scalar getters and distinguishes
  missing from live empty stores.
- `context_batch_chooses_first_live_duplicate_pool_id`: dead earlier slot,
  different live duplicate payloads, then death of the first live duplicate.
- `context_batch_preserves_zero_id_scalar_split`: live/dead zero-ID edge case.
- `context_batch_sparse_high_ids_and_slot_reuse_are_fresh_each_call`: high IDs,
  `u32::MAX`, missing IDs, death, freed-slot reuse and new occupant identity.
- `context_batch_all_store_positions_legacy_bits_and_bond_codes_match`: eight
  memory/bond positions, all 256 legacy bit masks, negative sentiment/intensity,
  all eight stored bond codes and independent duplicate result lists.
- `context_batch_needs_match_raw_float_bits`: six-field order, negative zero,
  subnormals, infinities and NaN payloads compared by native f32 bits.
- `context_batch_reads_preserve_native_state_schemas_and_snapshot_arcs`:
  repeated/empty reads retain complete native persisted bytes, master seed/turn,
  prepared health rows/losses, three schema descriptions and exact held Arrow
  schema/array Arc identities; an unstepped native decode gets the same results.
- `context_batch_python_boundary_types_and_scalar_float_conversion_match`:
  actual compiled PyO3 dispatch, Python list/tuple/int/bool types, independent
  duplicate lists, bool/index-object inputs and f64 bits against scalar output.
- `context_batch_python_boundary_rejects_bad_ids_before_native_mutation`:
  compiled PyO3 dispatch for invalid IDs/containers, a valid tuple sequence,
  `u32::MAX`, expected exception classes and unchanged persisted bytes.

The last two tests explicitly initialize/attach the embedded Python interpreter
inside the Rust test executable. They are not mock-conversion tests or installed
extension-origin proofs. No such interpreter, native test, native decode, build,
World, checkpoint, collection or timing was executed during source preparation.
No claim about process-global or Rust TLS random state follows from byte tests.

## Remaining gates

This source needs independent review and a fresh identified native build plus
focused/full CI before it earns compiled API qualification. Existing parent
care CI and historical default-output identity results keep their own scopes.
No prior pass is relabeled as a pass for this source.

Python wiring is a separate future child. It must preserve the existing sync
boundary, civ/GreatPerson order, active/None filters, duplicate records, memory
decoder and memory -> needs -> bonds assignments. Missing memory clears its
Python cache; missing needs/bonds leave their prior values. The promotion mule
memory query stays scalar at its original time. Noncanonical records/IDs,
bool/overflow/index objects and old extensions need the entire old loop so
conversion failure timing and earlier successful writes remain unchanged.

Before any production switch, require a new registered exact ordinary-output,
native-state, Python/NumPy RNG and checkpoint-continuation comparison. A timing
screen needs frozen workload/thresholds, both compiled source identities,
interleaved complete clocks, tiny-world checks and no same-source retries.
The separately owned current passive profile should first establish whether
the named-character work is material. No Python fast path, performance screen,
trajectory gate, scientific result, adoption, branch promotion or main merge
is included here. Mass polity mutation batching remains a separate design.
