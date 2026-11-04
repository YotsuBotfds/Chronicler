# Native applied-move provenance — 2026-10-29

This native-only Stage 2 extends the bounded decision observer from exact
`e99c0fd52f3839ba89dc0c65bf217542e42acbc4`, whose six standard jobs passed in
[run 40813775699](https://github.com/YotsuBotfds/Chronicler/actions/runs/40813775699).
The producing Stage 1 branch remains frozen at e99. This separate
`lead/decision-delivery-applied-moves-20261029` branch adds observations and
contracts; it changes no physical coefficient, threshold, gate or RNG stream.
It does not include the separate native tick-index-reuse work.

## API and lifecycle

The existing four positional arguments to `configure_decision_delivery` remain
valid. The new row limit is keyword-only:

```python
sim.configure_decision_delivery(True, 4096, 16384, None, max_move_rows=16384)
header, move_rows = sim.get_decision_delivery_move_frame()
```

`max_move_rows` must be 1–65,536 when enabled. Move capture uses the same
explicit sorted stable-ID selection (`None` means all, `[]` means none), but
its population and budget are independent of retained Stage 1 rows. Both
move rows and tracked origins are bounded by this limit. No diagnostic
tracking `HashMap` or `HashSet` is created: the transient origin map is a
bounded `BTreeMap` keyed by actual pending bucket and stable agent ID.

The existing `get_decision_delivery_frame()` still returns three batches with
its existing version-1 schemas. Its applied-provenance flag continues to
describe that incomplete Stage 1 view. Only the new move getter returns the
version-2 move header and move rows. The new header is authoritative for
Stage 2 capture completion; it still states that counterfactual marginals
are not computed.

Both getters are non-draining. Successful reconfiguration, disabling and the
start of an accepted native tick clear the old shared frame. Signal parsing
failure therefore cannot publish a prior turn's move frame. Python argument
conversion rejected before Rust tick entry does not execute that clear.
New frames publish only after successful native execution and event packing.
Configuration and frame remain excluded from checkpoint payload **and schema**;
a restored simulator starts disabled and empty. The recorded old schema
fingerprint stays `dcf0c34097c88451`. Restores in these contracts use the same
new build; no old checkpoint is relabelled or rebound to a new binary.

## Actual operations

Rows preserve deterministic operation order. `operation_ordinal` counts all
visits to the enabled native hooks, including unselected visits; gaps in an
explicit selection are expected. The bounded rows are a deterministic prefix,
not a probability sample. Counts refer to operations, not independent agents.

| Operation | Code | Capture boundary |
| --- | ---: | --- |
| Own proposal | 1 | Actual pending migrations before household consolidation |
| Replacement removal | 2 | Each exact proposal removed by the existing retain |
| Follower write | 3 | Actual spouse/dependent replacement push |
| Cancelled existing proposal | 4 | Each exact migration removed by the selected rejection branch |
| Blocked nonproposer | 5 | Retain proves that a would-be follower currently has no proposal |
| Dedup removal | 6 | Exact earlier tuple discarded by the existing reverse dedup scan |
| Applied move | 7 | Immediately after the actual migration event push |

Roles are own/household lead (0), spouse (1), dependent (2), or unknown (255).
For removals/cancellations/blocked operations the role describes the current
household operation, not an invented earlier decision. Applied rows use the
actual surviving proposal's tracked origin. The actual lower **slot** selects
the lead when both spouses propose a move; the hook copies its current stable
ID. Minimum agent ID is wrong after kill/spawn slot reuse.

Same-target spouse proposals are still removed and rewritten as followers,
as production consolidation already does. Each removed proposal is retained
separately. The follower row's `prior_proposal_count` and optional last
`prior_from_region`/`prior_to_region` come from that exact retain traversal.
`prior_count_valid` distinguishes directly observed presence/absence from an
uncomputed prior. These fields describe the current proposal immediately
before replacement, not whether the agent ever independently proposed a move.
Initial own proposals have their separate operation-1 records; a truncated
prefix must not be used to invent missing initial decisions.

Rebellion retains its original precedence over catastrophe. Cancelled rows
contain the actual removed tuple; `rejected_to_region` separately preserves
the household lead's rejected target, which may differ from a child's prior
target. Rebellion also records the actual trailing-spouse trigger ID. Blocked
nonproposers have no removed proposal and are not counted as cancelled movers.

Shared dependants can be rewritten by successive households. The last actual
write sets the eventual origin. A dedup-removal observation describes an older
discarded tuple and never erases the surviving origin. An applied row must
match the tracked bucket, agent ID and exact from/to tuple; a missing or
ambiguous origin remains unknown and makes complete provenance false.

The `applied` column is true only for operation 7. Its nullable
`native_event_ordinal` is a **zero-based index in the unchanged full native
event batch returned by tick()**, including preceding nonmigration events.
It is never a Python world-event ID or an index into filtered migration events.
The existing `migration_driver` positive-term label is copied separately from
the event; it is not the household cause or a counterfactual winner.

## Limits and completeness

The new header keeps separate all-operation, selected-operation, dropped-row,
tracking-admission, peak-origin, missing-origin and per-operation counters.
Initial tracking is bounded even when all agents are selected and many propose
moves. Stage 1 agent/candidate truncation does not limit or define this ledger.

`applied_move_provenance_complete` is true only after successful full capture
with no selected operation-row loss, tracking-admission loss or missing applied
origin. A successful empty or absent-ID selection may be complete with zero
selected rows; that does not establish that requested IDs were alive or
evaluated. Missing/failed/reset frames are not complete. A capped prefix can
omit later applied rows; continued bounded tracking does not recover those
omitted records. Such a frame establishes no population rate or complete
movement outcome.

The ordinary path instantiates a zero-sized no-op sink. Its own-proposal scan
is behind a compile-time enabled constant; hooks remain inside the existing
retain/push/application traversals. Original set construction, slot sorting,
predicates, statistics, physical writes and event ordering are preserved.
This source structure is not a measured speed claim.

## Verification boundary

New source contracts cover genuine kill/spawn/reused-slot marriage leadership,
same-target spouse replacement, all replaced proposals and their last target,
rebellion precedence, cancelled proposals versus blocked followers, catastrophe,
shared-dependent overwrites, reverse dedup, bounded tracking/row truncation,
unknown origin, empty selection, actual full-event ordinal linkage and
end-to-end consolidation/application provenance. Household fixtures compare
all pending fields, pool bytes and household statistics in ordinary, enabled
and disabled-panic-sink paths. Existing full-tick events/state and RNG contracts
remain in the suite.

Seven new compiled Python cases (six functions, one two-case parameterization)
use two direct Arrow regions with 40 initial agents. They require actual native
migrations and verify unchanged old positional/three-batch/schema contracts,
new source-turn/ablation/event linkage, on/off future state/checkpoint equality,
independent caps, explicit empty/missing-ID selections, same-build restore,
non-draining reads, failed-tick clearing and disable/reset. They explicitly skip
without native; a present extension lacking the new API fails as stale.

At source preparation only Python AST parsing and `git diff --check` ran.
No local native build/import, pytest, pool, world or replay was launched. All
new contracts remain unrun until frozen-source independent/root review and
fresh remote CI. Stage 1 e99 qualification does not qualify this new branch.
There is no new full-population gate, old/new default-output comparison,
large-world parity, performance or causal-outcome claim. Python writer, CLI
and experiment-harness integration remain outside this native-only stage.
