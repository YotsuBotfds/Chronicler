# Needs-sidecar decode reuse — source only, 2026-10-30

This child of829 removes the bridge's second full needs decode only when the
already-loaded compiled simulator's original owned getter supplied the batch.
All code, tests and runtime/performance qualification against this child are
UNRUN. There is no native import, build, World/tick or benchmark in preparation.
The public SidecarWriter.write_needs_snapshot API still returns None.

## The duplicated work and bounded contract

AgentBridge._write_sidecar_snapshot calls get_all_needs, lets SidecarWriter
decode/write/buffer its columns, then decodes those same columns for aggregates.
The native getter constructs fresh arrays for all14 fields: agent_id; safety,
autonomy,social,spiritual,material,purpose; civ_affinity,region,occupation;
satisfaction,boldness,ambition,loyalty_trait. Actual affinity is UInt8 (the Rust
comment's UInt16 is stale). No Rust source, schema, field order, sampling rate,
output policy or aggregate arithmetic is changed.

The optimization shares the first decoded column dictionary after the needs
JSON and every buffered row have been written successfully. It removes a
second14N-value boxing pass; it does not remove the first decode, JSON/Arrow
serialization, row dictionaries or any field. The dictionary is call-local;
no cache, World/bridge/checkpoint field or persistent writer state is added.
Memory/time benefit and fastpath activation remain unmeasured.

## Honest native ownership, not an Arrow-type claim

Arrow CData does not communicate external buffer mutability. An imported
PyArrow wrapper can report a read-only buffer while a foreign Python bytearray
still aliases it. The initial unexecuted draft's generic immutable-Arrow
admission was discarded before source freeze; no runtime result was produced.
Neither PyArrow nor arro3 wrapper identity alone admits this optimization.

The bridge captures self._sim and its get_all_needs attribute once, in the old
lookup/call order, and calls it once. After the call, its O(1) metadata check
requires the already-loaded chronicler_agents.chronicler_agents ModuleType,
its exact ExtensionFileLoader/spec identities, the exact exported AgentSimulator
class, its own C method descriptor and the original self-bound builtin callee,
with no instance override. No native import or extra native getter call occurs.
The unchanged Rust getter copies pool values into fresh owned Arrow builders;
other pool operations cannot mutate the returned arrays. This is an honest
source-bound native producer contract, not a sandbox against malicious C code
or forged module metadata. A source/platform that fails recognition keeps the
compatibility path; the planned native test must actually prove recognition.

Only exact AgentBridge with its stock polity resolver and exact SidecarWriter
with its stock public/private methods can reuse data. Subclasses, instance/class
method overrides, foreign/fake producers and arbitrary Arrow/CData use the old
writer-call followed by the old bridge decode. A custom resolver can observe
boxed-value/list identity, so it too forces compatibility. No input metadata,
column or row is inspected just to admit arbitrary foreign batches.

## Write/failure and public API preservation

The original writer decode, compact JSON, key/column order and row append body
moves intact into one private method, followed only by return data. Its public
wrapper calls the captured stock body and ignores that return, preserving None.
Calling the stock unbound body also preserves old subclasses or instances with
a coincidental new-private-method name; that name was never a public hook.
Existing public method overrides still run normally through compatibility.

The writer must finish JSON and every append before data reaches aggregation.
Write/partial-append errors propagate to the same original needs exception
handler; later aggregate conversion failures leave successful needs JSON and
rows intact. Stateful duck decoders still run twice, including successful write
followed by a changed second result or second-decode failure. Failure caused
solely by the redundant allocation being removed is not recreated artificially.
The bridge's sum order, float conversions, rounding, grouping and downstream
aggregate/community code remain byte-exact.

## Prospective checks and source witnesses

Eighteen pure cases append to the existing test_turn_artifact_views module,
which already belongs to native owner0 and the existing offline core chunk.
They use genuinely immutable bytes-backed14-column PyArrow/arro3 batches,
including empty input, UInt8 affinity, signed zeros and raw signed NaN payloads.
They compare the old bridge pylist route with writer decoding by Python types
and float64 bits, public None, all buffered columns/order, exact JSON and
canonical Arrow bytes. Foreign full-bridge cases check single getter lookup,
mutable external-buffer changes between write/decode, public/private collisions,
subclass/override behavior, stateful changed/failing second decodes and aggregate
failure after a successful needs write. No pure case pretends to activate native.

One native-only case appends to the existing test_agent_bridge owner. It creates
four agents with the existing native region setter, without World creation or
a tick, then runs the full writer/bridge path against the actual compiled getter.
It must observe true descriptor recognition, exactly14 fewer bridge column
decodes for the stock candidate, exact complete buffered-state/JSON/Arrow output
parity and original behavior for writer/private/resolver/bridge overrides.
Ordinary offline selection does not include that native-only module. Both test
suffixes and all existing case bodies/order remain preserved.

Changing the full bridge file requires exactly one deliberate current SHA pin
rebind in test_health_care_policy. All ten care marker bodies, care mechanics,
other nine pinned files/assertions and historical SOURCE_BINDINGS stay exact829.
No source assertion is removed. Next staging must also retain ef716's separately
reviewed current FFI pin rather than choose one whole care file over the other.

Existing owners/chunks/dependencies/workflows/defaults/native tree remain exact
829. All new case counts are prospective: views30+18=48, native-owner addition1;
no test/collection/native/World/build/benchmark/push/CI was executed by author.
Source is a small overlay, borrowed exact provider compositions and independent
compressed Git objects, not another full export. Focused tests, different source
review, fresh native CI and a separately reviewed performance method remain
required before any throughput or output-equivalence claim.

## First native fixture failure and observer teardown correction

The first ccc9 Tests run41015577534/1 used a fresh own-source wheel. Native
owner0 failed only the new needs-sidecar activation case. Its JUnit records
setup PASS, call FAIL and teardown PASS. At test_agent_bridge.py1827 the test
tried to pickle a deliberately installed private-instance lambda in the
writer's complete __getstate__ result. The final ownership and14-decode
assertions were not reached, so the native optimization is still unqualified.

The public-instance spy and private-instance sentinel also introduce test-only
instance keys that would make cross-variant state differ. This test-only child
preserves both exact original assignments, all eight modes, real-write order,
expected observer calls and public return behavior. It first establishes each
injected key was absent, captures the exact injected object, and asserts that
same object remains after the actual write. It then removes only those two
known observer keys before the existing complete production-data snapshot.
Every remaining state field, row/buffer, final JSON/Arrow file, ownership claim
and14-decode comparison stays in the original assertion. No field category,
private namespace or callable is filtered from production data.

All product/native code, the current care bridge/FFI witnesses, all other test
bodies, ownership/chunk membership and dependencies/workflows are unchanged.
The prior49 pure/care passes and the first native failure remain preserved;
they do not qualify this child. The corrected native case, fresh CI and actual
fastpath/parity claims are UNRUN. No Native/World/tick/build/test ran to author
this source repair.
