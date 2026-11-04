# Draft arc event-type projection — 2026-10-29

Status: isolated, unqualified draft. No local execution environment is available.
Tests below are proposed checks, not recorded passes. No workflow was activated,
no worlds ran, and no timing or whole-simulation speedup is claimed.

## Observed turn path and repeated work

Frozen base: d0281e5f57c508f27cea1676f36e0e6ed1225c9d.

At src/chronicler/simulation.py lines 2540 and 2550, the consequence phase
classifies each current great person and each person who died this turn, after
committing events and before snapshot capture. It passes the existing per-actor
history bucket. classify_arc still filters that bucket by the character's current
name, then its private archetype checks repeatedly create generators and read
Event.event_type. The predicates use five type-membership tests and the
multiplicity of notable_migration; none uses event turn, event identity or order.

The draft projects the filtered local list directly to event-type strings once.
The same private checks use string membership and count. Their order, condition
counts and complete/partial tie selection remain unchanged. The public
classify_arc signature is unchanged; its private helpers now consume that local
type list. Existing module consumers use the public classifier.

This removes repeated attribute lookups and generator creation by construction.
It is not evidence that an entire workload is faster; projection costs and actual
character histories must be included in a later measurement.

## State, history and compatibility boundaries

There is no persistent cache, new WorldState/model field, history-index change,
RNG draw, serialization change or altered turn-loop scheduling. Every call
recomputes its projection from the supplied event references.

The actor filter remains important: HistoryIndex's append cursor detects replaced
lists, truncation and replaced tails, but an in-place actor removal can leave a
reference in an old actor bucket. Filtering that reference again preserves the
existing classifier's result. This draft does not expand the index's invalidation
contract or fix unsupported in-place actor additions.

Duplicate actors do not multiply one event. Duplicate event-list entries still
multiply migration counts. Unknown and differently cased types remain literal
nonmatches. Negative and future event turns remain included exactly as before;
the classifier does not introduce a time window or change an intended policy.

## Proposed verification

tests/test_arc_event_types.py compares the current public classifier against the
complete frozen d028 source in tests/fixtures/performance/arcs_d0281e5f.py.txt.
The reference's Git blob is 87f38c36f85f514e0dc409864afaa700fd7fcc25.
Only source-checkout CRLF is converted to LF when checking/compiling that textual
fixture; no simulation output is normalized.

The proposed checks cover all 32 combinations of the five relevant boolean
event predicates, migration counts zero through four, living/dead careers at
19/20/34/35 turns, both traits and roles, mixed complete/partial precedence,
first-matching dynasty behavior, long histories dominated by irrelevant types,
unrelated actors, duplicate entries/actors, current-name changes, negative/future
turns, same-list appends/rewrites, actor-bucket removal and detected cursor resets.

Input model JSON and raw pickle, dynasty records and Python/NumPy RNG states must
remain unchanged. A separate operation-count fixture checks one event_type read
per matching event and none for unrelated actors. That count is not wall time.

A new bounded offline chunk selects the new test file with the unchanged
110-second limit. Existing arc tests, the complete offline lane and appropriate
full Python checks must also pass. Any claimed end-to-end output parity needs
its own exact-source run; older d028 default-output evidence does not qualify
this draft. Measure only after parity clears, retaining neutral or negative
performance results and including short as well as long histories.
