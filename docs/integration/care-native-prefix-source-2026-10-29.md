# Care native prefix implementation — 2026-10-29

This child of qualified `46967ce6c70561e0bb7baa8dec1f1bd895ff0cd9` is
**SOURCE ONLY**. It adds dormant primitive care observation, pre-turn configuration
and immutable PyBytes export. No Rust/Python/native tests, build, native import,
World, checkpoint decode, pilot, acquisition, push or main merge ran for this
implementation. Written tests are unrun source contracts.

The closed design receipt is
`e7b8ea859b49f083158b7653eed6dbe1a40329d062cad1f3e0707e70e15f0e0b`;
its SCHEMA SHA-256 is
`54e1faccd76b7dc9ef89e3e79d9e8c4d256024440e6e9d58351f1503f65c2679`.
The original actual-site plan SHA-256 is
`768233852d75107a3bffbb110ece12b87695c013aed477463dcd4cc2eaa4070d`.
The native baseline subtree is `04866c3962ec9d5c77477fc727107a553fc1d6df`.
The qualified parent's CI receipt SHA-256 is
`b6bef07ca8e0541542f69f54894dab0dacf3d57b54b2e5f6aaa70fe335faeb89`.
Those historical results do not qualify the changed native crate.

The recorder owns one at-most-131,072-byte prefix buffer, one at-most-4,096-u64
sorted `(raw ID << 16) | physical slot` dictionary, one at-most-4,096-u32 scoped
wealth-offset table, and fixed metadata below the design's 1,024-byte allowance.
It reserves those three buffers fallibly during explicit configuration. Default
`AgentPool.health_care_observation` is `None`, with no recorder buffers. Its
explicit persistence `transient` clause resets configuration and saved prefix to
`None` on restore without changing serialized fields or schema. The logical
primitive capacity remains 181,248 bytes; allocator/export/Python overhead and
runtime resource limits have not been measured.

`configure_health_care_observation(start_turn, manifest_sha256, *, turns=32)`
requires a 32-byte immutable session digest and a window of 1 through 32 source
turns. It returns false if primitive buffer reservation fails. Configuration is
refused while work or a recorder is present; restoration permits explicit fresh
configuration. `get_health_care_observation()` returns None before a saved finish,
or on export allocation failure, and otherwise returns a fresh immutable PyBytes
copy of the saved prefix. Repeated reads neither change that saved prefix nor
read/recompute physics, reset state, drain data, hash bytes or invalidate caches.

The prefix copies real prepare inputs/results and contemporaneous allocated
slots, including dead/duplicate IDs and every active Marriage/Kin target. IDrefs
restore raw IDs; they do not impose liveness or lookup semantics. Care's actual
last-alive physical slot lookup remains unchanged, including raw ID zero. The
copy loop compares worker identity/region, patient order and initial false worked
flags before source-proven elision. It never builds an observational IdSlots,
HashMap, RandomState or RNG.

Economy hooks copy actual farmer counts, factors, branch outcome and realized
slot/forage/work values at their original sites. Wealth copies the complete
consumed-vector length and every tuple except exact `(0, +0 raw bits)` immediately
after the existing take, then copies base/charged income and each actual wealth
write. Negative zero, NaN payloads, stale IDs, dead/invalid/nonfarmer/missing slots
remain represented. Full current finish ID/region/alive columns and the single
real finish result preserve independent finish-liveness reconstruction. Original
f32 expressions, their order and the physical slot loops remain exact.

Every append and patch is bounded; shape, row, byte, equality, stage and stale
turn/window failures retain the first fault and refuse successful evidence.
Counters cannot wrap into success. Missing internal economy-output/wealth-end
boundaries also fault. Diagnostic failure does not change ordinary physics or
intercept ordinary exceptions. The saved fault body is an opaque bounded prefix.
No final frame can be complete without later Python joins, which share the same
131,072-byte final cap and remain outside this source task.

## NATIVE_PREFIX_ONLY clarification

The native export is provisional for **both regular and fault prefixes**. Header
predecessor digest, body digest and Python entry/exit fields stay zero placeholders;
COMPLETE and Python stage bits stay clear. The native declared length describes
exactly its saved bounded prefix. No custom native cryptography or dependency is
introduced. This clarifies the design's provisional API paragraph where its
closed final-header/fault-hash wording could otherwise imply native hashing.

Before retaining any `.careobs` file, the later Python owner must update the final
encoded length, compute actual SHA-256 over the full joined body with hashlib,
and bind all applicable final header fields. This also applies to tombstones:
the actual retained fault prefix must have the correct length and body hash,
ABORTED set, COMPLETE clear, and an opaque body. The final CAREOBS1 file contract,
strict decoder hashes, cap, fault priority and completeness criteria remain
unchanged. A zero-placeholder native prefix is never a complete retained frame.

## Source checks and unrun gates

The existing `health_care.rs` algorithm and HealthWork bytes are unchanged. The
whole 181-file Python package, phase callers, health state/defaults, dependencies,
workflows, native Python ownership/skip/subtest manifest and 38 offline chunks
with their 110-second bounds remain exact parent source. There are no new Python
tests or Python module owners. Marker-based restoration removes only added
production hooks, restores the one finish-return binding and removes the explicit
transient name; its external source receipt compares all four edited existing
Rust production files byte for byte with the parent. Source inspection is not a
runtime parity or schema measurement.

The new recorder module registers its Rust unit/kernel contracts; the FFI module
registers its PyO3 source contracts. They cover source-neutral defaults/restore,
real spouse/Kin preparation, stable-ID scope/cost writes, raw bit/order and
zero/duplicate semantics, row/byte/stage/window faults, and immutable exports.
They have not executed. Independent review must precede any fresh build or test
activation. This native child needs its own fresh wheel/native/source identities,
actual three-class schema observations, native contracts, full applicable CI,
recording-off/on payload/default-output/global-RNG comparisons, and separately
reviewed enabled World/continuation and held natural pilot gates. Older 23d
empty-API or 3a/38dd native observations cannot stand in for this child. No
performance, efficacy, scientific, checkpoint-byte or main-promotion claim follows.
