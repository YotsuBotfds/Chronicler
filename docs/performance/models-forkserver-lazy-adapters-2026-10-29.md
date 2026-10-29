# Lazy metadata storage adapters, 2026-10-29

This isolated source-only continuation of the
[generic codec foundation](models-forkserver-codec-foundation-2026-10-29.md)
implements three narrow dependency storage views. There is no preloader,
controller, metadata-fork execution, backend activation or production change.
The original package remains byte-identical to stage 1 at `9848e7da`.

The helper imports no Pydantic code. It binds only the two already-loaded,
exact module objects and three exact classes, with bounded source hashing,
initial path/class identity checks and original descriptor provenance.
Closed source pins target the observed Pydantic **2.14.1** environment;
a different version/source must refuse pending a separate reviewed policy.

| Type | Implemented access | Admission boundary |
| --- | --- | --- |
| `MockCoreSchema` | Four owned member cells: `_error_message`, `_code`, `_attempt_rebuild`, `_built_memo` | A live storage view only; no inherited-base codec admission |
| `MockValSer` | Four owned member cells: `_error_message`, `_code`, `_val_or_ser`, `_attempt_rebuild` | A live storage view only; no inherited-base codec admission |
| `LazyClassAttribute` | Entire original instance dictionary, including absent/present cached `value` | Exact source-pinned direct-object dictionary rule, requiring dependency class roots in a future guard |

Mock access uses only verified C member descriptors with matching original
names and owners. Missing, remapped, deleted, foreign or uninitialized cells
refuse. It never calls Mapping truth/length/iteration/item APIs, attribute
probing, rebuild, descriptor `__get__`, cached `.value`, schema generation or
signature inspection. The lazy dictionary uses its original builtin storage
descriptor. Unknown, subclass and compiled-instance types remain refused.

Views preserve original references and aliases, including `_built_memo=None`
versus a real memo and absent versus populated lazy cache entries. They are
**live views**, not historical snapshots. The later caller must encode them
immediately under a qualified single-thread/source/resource boundary, preserving
their original-object memo links. The mock views are not yet integrated into
the graph encoder. Returning a view does not prove inherited or compiled state.

The companion `dependency_class_roots` exposes all three wrapper class
dictionaries for the same fingerprint. Source bytes alone do not prove loaded
method origin or reveal an in-memory monkeypatch. Class roots are mandatory
alongside instance storage; their unsupported contents still refuse in the
generic encoder. Supplying only the lazy instance rule is not a qualified
template guard. No current orchestration invokes any of these helpers.

## Compiled schema policy remains unresolved

The saved descriptive inspection observed 129 each of compiled
`SchemaValidator` and `SchemaSerializer` instances. These counts do not prove
complete ownership links. Binary identity, object identity and an owning
`__pydantic_core_schema__`/`model_config` are useful bindings, but they do not
expose the Rust graphs or establish immutable internal state. Model construction
also computes a distinct `core_config` before constructing these objects.
This helper does not replace that missing constructor record with model config.

Compiled instances remain unsupported. Repr, reduction/pickle, validation or
serialization methods are not snapshot shortcuts. A future source-matched core
review and bounded, independently reviewed isolation/state policy are required;
there is no opaque mutable-content fallback. This boundary applies even if all
Python wrapper tests pass.

Relevant descriptive environment pins:

- `_mock_val_ser.py`: `56a6ec20e81e9e841088cf8db05325f6e63b8ad8094ae3cda5754a698ec0d293`
- `_utils.py`: `23de5935186553e9bc579a6a0594ab3f6b0c20d63e8b0e5a6dc3d451185a0678`
- `_model_construction.py`: `e9f8b178522454c24ff04b3d7b734665b20b9e3b6ed4c9b5d7d5fe5ad019cee3`
- Core 2.50.1 binary: `47433ba05547232202c47b70a3de1b37bdb4d6efd624508f4d7a42ef5f4bc1eb`

Only the first two source pins participate in this helper's narrow binding
checks. The latter pins are descriptive references, not compiled admission.

## Validation

Fourteen pure synthetic cases exercise preserved aliases/cache states, poisoned
lazy methods, actual-module/source/path/class drift, complete original owned
slots, method rebinding, unknown compiled-like types and incomplete bindings.
Fixtures replace the source/module pins within the test process; they do not
qualify real Pydantic runtime execution. An independent source reviewer cleared
the owned-storage scope and separately reviewed the installed dependency source.
The complete modified guarded validation-tooling selection passed **340 tests
in 8.29 seconds**, including those 14 cases, under the real 110-second timeout
and unchanged lane limit. Guard PASS, zero `chronicler_agents` imports/modules or blocked
I/O; existing broader tests made 61 calls each to the ecology/politics Python
oracle factories. Generic codec and producer bytes remain unchanged.
No new runtime dependency inspection, metadata fork, world/checkpoint operation
or native build was performed for this work.
