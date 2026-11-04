# Expansion runner optional policy receipts

The external expansion runner previously required `controls_after` to have
exactly the historical `CONTROL_FIELDS` keys. The producer also emits
`preparation_policy` for forecast experiments and `care_policy` for care
experiments when explicitly requested or inherited from an enabled parent.
Consequently a valid completed worker's receipt could be rejected by the
consumer. This is a source compatibility defect; no genuine World failure
was observed.

An additive pure `receipt_control_policy(feature)` descriptor now exposes the
source's optional receipt key and its closed values, with the omitted legacy
value first. It describes receipt fields rather than all accepted request
controls. In particular, science `research_enabled` remains separate
`research_policy` metadata. Receipt generation, simulation policies, required
control tuples, checkpoint/state formats and comparison rules are unchanged.

The runner requires the exact old fields plus the applicable optional key in
both before/after dictionaries. An explicit policy request, including return
to `fixed` or `spouse`, must appear in both dictionaries and match the after
value. Without a request, an included policy must be a valid inherited
nonlegacy value and remain unchanged. Legacy omission remains valid. A fork's
before-policy is also compared with its trusted common parent's after-policy,
normalizing legacy omission only in detached comparisons. This independent
binding rejects an inherited enabled policy omitted on both sides. Unknown or
missing fields, asymmetric policy fields, invalid types/values, requested-value
mismatches and unrequested changes fail closed. Older sources lacking the
descriptor retain their historical exact receipt shape and cannot supply or
request unsupported optional policy fields.

The existing runner test module owns 71 new pure cases. They import the
stdlib runner dynamically, read descriptor/getter AST literals and fabricate
worker bundles/identity receipts; they never call `_load_source`, import
simulation/native/NumPy modules or start a real child. The frozen selected
run passed 71 cases, zero failures/errors/skips, with unchanged source hashes
and zero guarded import/process/network events. Bounds were one CPU, 40 wall
seconds, 30 CPU seconds, 512 MiB address space, 128 KiB log and 4 MiB fixture
files. The exact unmodified `3a2a671477be849dd1b26c000d501304b8c684e9`
consumer also reproduced its expected rejection for two fabricated successful
workers, one per policy; those negatives remain separate evidence.

Both the offline `expansion-experiments` chunk and native ownership already
include this whole test module. Their registries, 38 offline chunks,
110-second limit, 303 native module owners and existing subtest/skip seals
are unchanged. Only the new selected pure cases ran here. The old module
selection, full offline/native/no-Rust CI, genuine enabled Worlds/checkpoints,
default-output/RNG behavior, science, performance and policy adoption remain
unqualified for this child. Source/root review and integration are separate;
there is no push, main merge or trial activation in this change.
