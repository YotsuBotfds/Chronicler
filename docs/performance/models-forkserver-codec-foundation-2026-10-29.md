# Strict metadata codec foundation, 2026-10-29

This isolated engineering branch adds a generic metadata graph encoder for
the [inactive metadata design](models-forkserver-metadata-design-2026-10-29.md).
It adds no preloader, controller, production dispatch or executable proof.
The stage-1 backend continues to refuse before claiming any destination.
Producer Python/Rust files remain byte-identical to `9848e7da`.

`scripts/forkserver_template_codec.py` encodes primitive types, exact float
bits, container order, aliases/cycles, function defaults/closures/annotations,
known code fields and explicit reviewed object storage. Its class/module
identity tokens refer to one process and its unchanged fork descendants;
they are not equivalence claims across interpreters or source revisions.
Registered module and local-class namespaces are separate roots. Builtins
namespace contents are excluded; this is not a witness of every interpreter
or dependency-library global.

There is no repr, pickle or opaque mutable-content fallback. Unknown values
refuse. Generic mapping proxies refuse because they may wrap arbitrary Python
mappings; only the builtin type descriptor establishes a real class-dictionary
view before its controlled projection. Class/module keys are validated before
lookups can invoke a custom equality hook. Exact type dispatch bypasses custom
metaclass equality/hash/attribute hooks.

Storage rules name an exact source-reviewed class and every slot/dictionary
cell. They are not automatic approval of arbitrary C-extension objects.
The current foundation admits direct-object layouts and direct tuple subtypes
with explicit tuple contents. Other inherited storage needs a dedicated reviewed
adapter. Shadowed, remapped, foreign or missing slot descriptors refuse;
literal slot declarations and private-name mangling must match the original
builtin descriptors. Rules use those descriptors directly rather than invoking
user properties. Node, depth, scalar, container, projection, class-MRO and byte
bounds apply. Code fields/constants enter the bounded graph without marshalling
an unbounded constant blob first.

The byte limit bounds returned encoded artifacts. Input graph reservations
also bound traversal, but JSON escaping can expand the temporary serialization
by a bounded constant factor before its final size check. This is not a hard
RSS allocation cap; a later supervisor still needs independent memory floors
and whole-process resource accounting.

## Descriptive dependency inspection

One separate fresh-process metadata inspection informed this implementation.
It used the clean detached producer `9848e7daa93d075f05a01201aba85233f5baf540`,
package digest `0eab6d514c5fc7fda0c0180d52c48bbad126598c3288477f86ab2eeb742a72d3`,
Python 3.13.5, CPU 1, hash seed zero and numerical thread caps one. Its fixed
limits were 30 CPU seconds, 45 wall seconds and 32 MiB evidence, with forbidden
runtime imports/process launches blocked. The observed prefix matched the 25
static Chronicler modules; each step had one OS task and zero WorldState/native
instances. It observed 16,079 descriptor-graph objects across 67 types, with no
forbidden import or launch attempts.

The report is 80,252 bytes, SHA-256
`0d2cf97eb60a14c1ec12354199e1924b96bbe119490e47c386f74df75c0b14c7`.
Its pre-finalization cost was 0.865737 CPU/0.821303 wall seconds; the external
shell recorded 0.946 seconds. These are descriptive import costs, not a
performance study or whole-proof cost. The raw report remains external with
the control/source/environment hashes. A launcher preparation failure caused
by absent `/usr/bin/time` is also retained; no inspection process started in
that attempt. The completed invocation used the shell's timing builtin.

The useful finding was that Civilization retains Pydantic `MockCoreSchema`
and `MockValSer`, alongside lazy class attributes. Repr/schema/property access
can trigger rebuilding. Exact source-verified storage adapters must inspect
their cells without invoking those hooks. Compiled schema objects, ABC caches,
typing internals and other dependency types remain unsupported here. No claim
is made that the current codec can encode the entire inspected prefix.

## Validation and remaining boundary

Pure adversarial cases exercise type/float/alias fidelity; content mutations;
unknown objects; poisoned repr/pickle/properties/metaclasses; generic proxies;
ambiguous storage, slot remapping/deletion; namespace-key collisions; large
constants; and resource bounds. Source review identified and fixed these
generic gaps before any runtime integration. An initial CPython descriptor-kind
assumption failed the focused test and was retained before correction.

The final modified guarded validation-tooling selection passed **326 tests
in 7.23 seconds**, including all **30 codec cases**, under a real 110-second
external timeout and the unchanged lane limit. Guard state PASS; zero loaded
native modules, native import attempts or blocked I/O. Existing broader tests
made 61 calls each to the guarded ecology and politics Python oracle factories.
The independent codec source reviewer cleared this strict generic scope after
the adversarial layout/hook corrections; JSON/diff checks and unchanged producer
package bytes were verified separately. Earlier passing test runs remain
scoped to their earlier source and do not substitute for this final result.

No metadata server fork, checkpoint read/restore, study world, simulation tick,
native build or backend execution ran. Current-source two-child isolation,
actual dependency adapters, process ownership/cancellation/accounting and full
native continuation remain pending. The earlier timing result does not
qualify this code or predict a new speedup. Any later proof still requires
the final executable source/control/environment freeze and root review.
