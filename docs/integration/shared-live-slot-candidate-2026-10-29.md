# Shared live-slot integration candidate

This separate source candidate combines two independently scoped changes on
top of published review consolidation `851c31ab`. Main and that published
review ref remain unchanged.

* Native source `6dccc6250218145f4e978351a20e068a632fd8c2`, based on qualified
  `cbf6e368`, reuses the tick's existing ascending live membership in skill,
  needs and knowledge passes. Only three Rust files change. The current native
  crate is `6503ceebc4efdcd3c4f51b0058c4e562fd94b5a6`; no previously built
  extension qualifies these bytes. [Source details](../performance/native-alive-slot-reuse-2026-10-29.md).
* Test source `8fea69df0d031870617a40500bf92fb5d7995e25` replaces a receive
  waiting for an absent completion message with a bounded thread-owned event.
  All twelve original assertions, the empty spy result and five-second failure
  bound remain. One guarded old/new target pair passed, with forbidden-operation
  counters zero and source pins unchanged. [Focused qualification](../performance/ci-live-narration-invocation-2026-10-29.md).

The first native source `b2d6f3f5` remains preserved. Root review caught two
unqualified constants in its new skill test; the child qualifies their names
without changing production bodies. No failed compiler run is claimed: no
Rust toolchain is available locally. Two new Rust regressions and all native
compilation/testing remain unrun at this source checkpoint. Source-token
checks establish a narrow textual transform, not Rust type or borrow validity.

The native patch removes two capacity-wide live filtering passes and two
temporary index vectors. The skill loop traverses the same live slots in the
same order. Region, wealth, sentiment and packet fields remain fresh reads;
lookup construction, sparse fallback, empty-phase handling and demographic
boundaries stay in their original order. These are structural counts. No wall,
CPU, RSS or simulation speed improvement is measured.

After independent source review, this combined candidate requires a fresh
native build and all six unchanged CI selections. The exact C76-to95 default
export result belongs to its original sources; it does not qualify this new
crate or checkpoint/RNG state. A new default-output comparison and any measured
performance or scientific claim remain separate work. The wealth correction,
research recorder/driver and CI-sharding prototype are separate branches.
