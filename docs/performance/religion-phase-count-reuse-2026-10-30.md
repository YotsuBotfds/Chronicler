# Religion phase count reuse — source-only candidate, 2026-10-30

This isolated child of829 reuses only the successful `region` / `belief !=255`
grouping demanded by majority, persecution and schism. The exact same
turn-local AgentRows and historical batch reach all three consumers. They read
counts without mutating them; live ruler/faith/registry policy remains outside
the cache. The existing civ-affinity grouping and simulation's255-inclusive
region distribution remain unchanged and separate.

The first request keeps filter-before-grouping row order and freezes the result
as ordered immutable tuples on that view. Later requests return fresh dicts and
Counters. Thus callers retain their mutable/private return contract without
repeating the N-row mask and ordered grouping. For U occupied region/faith pairs,
first demand adds O(U) tuple allocation; each later demand costs O(U) defensive
copies. Every AgentRows also gains one empty private list. One-demand/small-map
regressions and allocation costs must be retained in a later fixed benchmark;
no whole-turn speedup or memory saving is established.

## Trusted Arrow boundary

Caching requires exact AgentRows, actual immutable Arrow data, and exact1D
integer/equal-length NumPy columns. Known pyarrow.RecordBatch and runtime
arro3.core.RecordBatch are admitted by class identity. The pinned native
pyo3-arrow0.17.0 returns a raw statically-linked PyRecordBatch, which need not be
the runtime arro3 class: its source declares a frozen C RecordBatch class.
For that source-owned family, admission additionally requires exact metaclass
`type`, object base, the declared module/name and owned exact C method descriptors
for `__arrow_c_array__` and `column` whose `__objclass__` is the actual batch type.
No exporter or instance metadata getter is called by this check. Python spoofs,
borrowed descriptors, subclasses, mutable numeric ducks and unsupported arrays
keep original grouping/fallback behavior. This is the trusted Arrow contract,
not attestation against arbitrary malicious compiled extensions or externally
mutated Arrow backing buffers.

The57,124-byte public crate matched the exact Cargo.lock SHA256 and was inspected
in RAM without extraction/import/execution. Only a small provenance/excerpt
record is retained outside Git. Native Rust, bridge, simulation, care witnesses,
Arrow/World/checkpoint schemas, experiments, defaults, workflows and dependencies
are unchanged. All public `_check_agent_rows`, empty/capacity gates, successful
column decode behavior, scalar/null errors, event order and RNG behavior remain.
None/errors/noninteger summaries are never retained.

## Verification remains prospective

The old turn-view test file is an exact raw prefix, with18 new pure cases.
They exercise all three real consumers, full state/private/input/RNG parity,
actual pyarrow/arro3 frames,255-first-appearance outer/inner order, caller mutation,
live policy changes, different fields/views/stamps, lazy missing/error retry,
all255 results and mutable duck/spoof/subclass fallbacks. The filtered order
for `(region,belief)=(0,255),(1,2),(0,1)` is1,0; deriving it by dropping255 from
the full map would wrongly yield0,1.

The native decision-delivery test file retains its full old prefix and adds one
existing-owner contract: a tiny two-region actual AgentSimulator with initial
faiths0/1 returns a RAW snapshot; three majority queries must group once and
match the uncached output while checkpoint bytes remain unchanged. It performs
no tick, World generation, normalization or restore. Only a future fresh-wheel
hosted CI may execute that case. Actual raw-native cache activation is UNRUN
and must pass before a meaningful native-hotpath claim.

Suggested ordinary local focus is131 cases: whole views48, religion22,
persecution31 and schisms30, under the existing110wall/30CPU/512MiBAS/oneCPU
Python oracle guard. Existing views owner0/core selection supplies18 new offline
cases; the one native test stays owner1 and adds one no-Rust skip. No manifest,
owner, chunk, selector or cap changes are made. All candidate tests/build/CI,
performance measurements and scientific gates remain UNRUN. Source review,
future focused execution and publication decisions are separate.
