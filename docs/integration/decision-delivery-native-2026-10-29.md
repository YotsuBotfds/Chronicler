# Native decision delivery, Stage 1 — 2026-10-29

This source adds default-off, bounded observations at the native decision
boundary. It is prospective tooling for the full-cohort needs/kin findings;
it changes no coefficient, threshold, gate, population or causal target. The
branch starts from review `82b3699b8fc75ca3ffcc7f3565f48a9c93d2e883`, with
native crate source `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`. The earlier
diagnostic branch remains at `7716ccf63a18394702f3539c11d34fe21316f2de`.
The separately qualified intentional wealth-floor correction is not included.

## Native API and lifetime

`AgentSimulator.configure_decision_delivery(enabled, max_agent_rows=4096,
max_candidate_rows=16384, selected_agent_ids=None)` configures the next ticks.
Each limit must be 1–65,536. Explicit stable agent IDs must be sorted, unique
and at most 65,536 entries; `None` selects all alive agents, while `[]` selects
none. Configuration and frame are transient: they are absent from checkpoint
payload and schema, and a restored simulator starts disabled without a frame.
The old recorded AgentSimulator schema fingerprint remains `dcf0c34097c88451`.

`get_decision_delivery_frame()` returns three separate Arrow batches:
one header row, decision rows and destination-candidate rows. Repeated reads
do not drain the frame or change the pool. Configuring or disabling clears the
frame. A native `tick()` clears the prior frame before initialization checks
and fallible signal parsing, and publishes a new frame only after native
execution and event packing succeed. Enabled without a successful frame has a
null `source_turn`; this differs from a successful empty selected frame.

The frame's `source_turn` is the incoming native tick argument used for the
actual decision RNG stream and ablation mask. Python passes `world.turn` and
increments it later in `run_turn`; this API does not shift the clock. Header
`active_ablation` is the mask active at that source turn, including before a
configured ablation start. Region values are actual region indices and IDs
are copied stable pool IDs, not pool slots.

## Captured values and validity

Decision rows include alive-trip/evaluated status, age, occupation,
displacement, mobility eligibility, actual need inputs, raw needs additions
immediately before their caps, capped additions immediately after, actual
migration utility stages, pooled/personal wealth and the applied factor,
community anchor, four utilities passed to Gumbel choice, selected action and
destination, and the observed negative loyalty-drift factor/magnitude. Flags
distinguish skipped computation from an actual zero, including a computed
zero community anchor and an implicit wealth factor of one. The loyalty flag
means a negative drift was computed; the subsequent proposal can be a civ
flip. `needs_migration_applied` means the capped addition was inserted before
the later migration destination/utility gate; it does not mean a move occurred.
Displaced agents still compute needs but do not insert their migration term.
An active needs ablation skips this helper rather than inventing a raw dose.

Destination rows exist only after the actual adjacency/crowding guards. They
copy gross and post-roots voluntary channels, the actual post-roots total,
hysteresis predicate and retained pull, region/river/pre-news scores, and
whether this candidate became best at its iteration. That last flag is not a
claim that it remained the final destination. Ineligible mobility leaves
voluntary channels uncomputed, distinguished by `mobility_eligible=false`.
The kin-roots ablation drops relationship roots from voluntary mobility; it
does not remove all kin, pooled wealth, age roots or household followers.

Every observed f32 is exported as its original UInt32 bits. Infinity is a
valid utility value; no diagnostic subtracts infinities or reconstructs raw
accumulation. The existing needs migration budget orders its component array
as safety/material/spiritual/social, while actual utility accumulation is
safety/material/social/spiritual. A regression fixes a discriminating fixture
at raw bits `0x3f224dd3` versus array-sum bits `0x3f224dd4`. The observer copies
the actual helper value and preserves the original arithmetic order.

## Bounded capture and scope

Limits are divided into fixed per-region quotas before parallel decisions.
Rows retain original agent/candidate iteration order, are merged in region
order, and never sort or reschedule simulation work. Header counters distinguish
all alive agents, selected alive agents, trips, evaluated/displaced/mobility
populations, all admissible destination visits and dropped selected rows.
Requested explicit IDs can be dead or absent; requested count is not a count
of observed decisions. Candidate rows whose selected agent row was omitted
are counted as dropped. Quotas may leave capacity unused in other regions.
Deterministic capped prefixes are not a probability sample and establish no
population rate. `decision_capture_complete` means no selected Stage 1 rows
were dropped, not complete causal or final-movement provenance.

This stage observes decisions before household consolidation. It does not
trace final application, cancellation, household follower origin, retirement
or recovery. Header `applied_move_provenance_complete` is always false. It
also does not recompute leave-one-out utility/target winners or counterfactual
marginals; `counterfactual_marginals_computed` is always false. Local raw/capped
and sequential stages must not be presented as a counterfactual effect.
Python bridge capture, writers, CLI, experiment harness and applied-movement
provenance remain future stages.

## Verification boundary

The disabled path dispatches to a monomorphized zero-sized no-op observer;
capture-only reads are behind compile-time observer constants. Enabled region
observers own bounded vectors without shared capture locks. This structure is
not a measured speed claim.

New Rust contracts cover bitwise needs parity and cap shadowing, actual
roots/pull capture, decision/RNG/read-only-pool parity, displacement, complete
tick events/pool/statistics parity, one-versus-two-worker frame identity,
quota bounds, validity and checkpoint transience. Five real compiled Python
API contracts use two direct Arrow regions and tiny fresh agent populations,
without a world generator. They verify configuration, actual-turn/ablation
capture, on/off events/snapshot/checkpoint equality, non-draining reads,
selection/truncation, disable/reset, same-new-build persistence and stale-frame
clearing on rejected signal parsing. No-native environments explicitly skip;
a present compiled extension missing the new API fails.

Only source checks were performed while preparing this commit: Python AST
parsing and `git diff --check`. No local native build, native import, pytest,
thread pool, world, replay or scientific rerun was performed. Independent
frozen-source review precedes a fresh remote native build and tests. These
unrun contracts are not CI qualification, output parity proof or a new
scientific outcome. Full gates retain their original `2f9d618b`/`d0281e5f`
sources and native `06db5e19` identity.
