# Current090 passive profiler — Stage 1 source only

This adds an inactive worker and observer-equivalence contract for exact
`0900f3d203cc74102809bb871a1a057ba91a951f`. It has no executable study CLI;
`EXECUTION_APPROVAL` is null and every worker entry refuses before any project
or native import. No World, profile, native build, installed-byte probe or
hosted run has qualified this source. The older 30-World/C76 timing proposals
remain held and unchanged.

The fixed schedule is seed 42, procedural worldgen, four initial civilizations,
hybrid/exact, simulate-only and validation sidecars, with ordinary feature,
reflection and ten-turn state-writing defaults. The three cases are 12 regions
with target 2,000 (plain then profiled), 12 with 20,000 (profiled then plain), and
48 with 20,000 (plain then profiled). Each generated run executes 97 turns:
six generated/stepped runs and 582 physics ticks. Starting targets are scaling
interventions, not observed agents. The old capacity/population rounding and
civilization synchronization are retained, including the pre-physics 60,000
per-region refusal. No rescaling, substitution or favorable-data stopping.

The existing caller-owned `bind/live_record/turn_end` interface closes each
turn after memory, reflection, state and scheduled checkpoint writes. The
stdlib cProfile process-CPU windows are (8,16] and (88,96], eight turns each;
only three profiled roles enable them (48 profiled ticks total). The final
97th turn, final exports and diagnostic checkpoint work are outside both
windows. The complete execute_run clock also includes setup and exports.
Profile self/cumulative CPU, boundary CPU/wall, complete-run clocks and proof
clocks stay distinct; no residual is presented as an independently measured
phase. Fixed callback/enable/disable overhead is part of the observation.
Native calls remain opaque. No phase share, benchmark speedup or scaling law
is claimed.

Both roles make the same five population reads at turns 8,16,88,96,97, after
profiling is disabled and before it is enabled. Exact090
`AgentSimulator.get_region_populations(&self)` delegates to
`AgentPool.region_populations(&self, num_regions)`, which only reads capacity,
liveness and region IDs into fresh local counters/Arrow builders. It does not
write a cache, simulator state or RNG. The bounded table records actual alive
counts in registered regions, separately from aggregate region populations;
out-of-domain agents are not included in that native getter's sum. Extinction
is retained. There are 30 such boundary reads plus six final restored-state
reads, not extra physics ticks. The final getter additionally checks native
checkpoint bytes before/after. Actual metadata remains unobserved.

The future owner must share one actual import-complete Python/NumPy global
RNG checkpoint with each paired fresh child, restoring it after identical tool,
project, decoder and native imports. The worker does not derive globals from
seed 42. It records final globals before checkpoint proof and refuses any
change after save/decode/fingerprint/population proof. Its one physics call is
never replayed on exception; profiling stops and the scaling callable restores
in nested cleanup. No simulator proxy, class replacement or package-file edit.

## Exact checkpoint and ordinary-output contract

Both roles must produce into the **same absolute ordinary output and state
paths**, sequentially. A separately reviewed owner must wait for owned
quiescence, inventory and archive the first role, then admit a fresh empty
identical logical run path. Diagnostic profiles, RNG records and checkpoints
stay outside the ordinary tree. There is no output-path normalizer. Exact090's
`output_config` carries only simulate_only, narrator, validation_sidecar,
relationship_stats, state_every and ablation_output, not file paths. Embedded
sidecar paths and RunResult.output_dir still compare literally.

The original `cities_identity.compare` and
`turn_speed_identity._raw_bundle_problems` are passed unchanged: only their
existing bundle generated_at normalization and log/run_manifest exclusions.
No faith projection, state filtering or broader exclusion is added. Stage 2
must authenticate these exact source functions before use.

Each role writes its own final checkpoint through the saved callback and uses
the strict ordinary loader. Six decodes create additional unstepped restored
objects/native instances; six generated runs is not a claim of only six World
or native objects constructed. Raw checkpoint bytes are retained per role but
are not required equal. Decoded content is fingerprinted with deterministic
reference ordinals, dictionary order, cycles, float bits, private/extras,
configuration/history/events/memory data and all native checkpoint bytes.
Memory encoder cache contents and actual entry/field identity links are kept.
Unknown types refuse, with no repr/object-ID fallback. Unsupported state in a
genuine run is a failed observer proof, not permission to exclude it.

The sole identity treatment is grounded in `run_checkpoint._markers` and
`_rebind_markers`: require the exact Boolean marker
`{'war_roster_bound': True}`, one unambiguous actual world marker storage, and
its raw integer equal to `id(real_bridge._sim)`. Only that field is fingerprinted
as a bound token. RunState.markers itself remains compared. The actual object
and raw checkpoint are never rewritten or re-saved with the token. Unknown,
unbound or duplicate marker storage refuses; if a genuine case is unbound,
root must review that evidence before any contract change. No other private,
integer, pickle or native field is dropped.

## Remaining admission and qualification

Stage 2 must compose authenticated selected C60/27f ownership plus exact44f
resource visibility; those helpers do not reside in the090 tree and are not
claimed implemented here. It must enforce negative-first/always-terminal
records, owned descendant cleanup, one setup-through-finalization deadline,
input/source/wheel expiry, actual all-three compiled classes/schemas, fresh
checkpoint paths, descriptor-safe bounded inventory and failure retention.
Actual schema references remain absent until genuine owned probes before the
first World. Exact090 package digest is
`1f1c720880e45e0e835e033da216b3deee1f755a497b8e189abaf97c2fe9f656`,
crate `803c79c8d5c024cbb8d67c58af7ffa731d79c129`, native
`14a67f283cf57dc738e05d43d7b86aeca9039821e453e70274dfc1bb42e70e8c`.
The separately qualified 2206/4854 candidate cannot satisfy these pins.

The registered prospective limits are owner 2,400 wall/1,800 measured CPU
seconds; each entire role 300 wall/240 CPU seconds, 4 GiB address space and
2 GiB observed process peak RSS. Entry floors are 12 GiB disk/4 GiB visible RAM;
running floors 3 GiB disk/1 GiB RAM. Outputs are bounded to 512 MiB per role,
3 GiB aggregate and 5,000 regular files. One actual affinity CPU/logical CPU,
all numerical/native caps 1 and hash seed 0 must be recorded and checked. All
setup/probe/proof/output costs count against owner/child budgets. Limits are
not predictions or permission to execute.

Final Stage 1 pure qualification is 53 fake/metadata cases passing in a guarded
Python 3.13.5 process. No project/native/NumPy module, factory, network or child
process was used. Prior 42- and 44-case source boundaries and receipts remain
retained. These tests cover boundary ordering, actual-count table bounds,
RNG metadata/replay, marker rejection, reference/cycle/private/cache/native
fingerprinting and unchanged comparator invocation. They do not qualify real
cProfile timing, serialization of genuine worlds or observer equivalence.
Independent source review and a separate root decision precede any hosted run.
