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
Both roles close each end-window CPU/wall measurement before the population
read/context work; only cProfile.disable differs.
Profile self/cumulative CPU, boundary CPU/wall, complete-run clocks and proof
clocks stay distinct; no residual is presented as an independently measured
phase. Fixed callback/enable/disable overhead is part of the observation.
Native calls remain opaque. Plain and profiled roles both use this common
passive boundary/scaling caller; their proof isolates cProfile activation, not
a separate bare-CLI/no-boundary baseline. Common observer cache conditioning
and profiling bias remain limitations. No phase share, benchmark speedup or
scaling law is claimed.

Both roles make the same five population reads at turns 8,16,88,96,97, after
profiling is disabled and before it is enabled. Exact090
`AgentSimulator.get_region_populations(&self)` delegates to
`AgentPool.region_populations(&self, num_regions)`, which only reads capacity,
liveness and region IDs into fresh local counters/Arrow builders. It does not
write a cache, simulator state or RNG. The bounded table records actual alive
counts in registered regions, separately from aggregate region populations;
out-of-domain agents are not included in that native getter's sum. Extinction
is retained. There are 30 extra observer boundary reads plus six final restored-state
reads, not extra physics ticks or a count of all native getter calls in a run.
The existing simulation already uses this getter. The final getter additionally checks native
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
Mutable bytearrays are memoized, including shared-buffer identity. Qualified concrete Path types are retained, even when their strings match.
Own slot declarations are inspected per class; hidden/redeclared storage names
refuse, while ordinary inherited physical slots remain supported. Unknown
stateful container/Path/Random subclasses refuse; the explicit exact
Counter/OrderedDict/defaultdict/ordinary containers retain supported extra
state. Decoded project/dataclass objects are read directly through actual
dictionaries/slots, not an omitting reducer. RNG equality validates the full
actual state and preserves signed zero in both Gaussian cache fields.

The NumPy handler accepts only the exact admitted ndarray and a fixed set of
immutable scalar classes. Subclasses, object/structured/metadata dtypes,
indirect/noncontiguous base buffers and unknown storage refuse. Supported
arrays retain dtype, shape, strides, all flag bits, content, base-buffer graph
and relative data offset. A base-less array must own its storage; external
unanchored nonowning arrays refuse; memoryviews retain their format/shape/strides/readonly
state and actual backing object. Zero-element byte views derive relative
offsets outside timing; raw addresses never enter records. This handler has
only synthetic metadata coverage, not a real NumPy execution claim.
Unknown types refuse, with no repr/object-ID fallback. Unsupported state in a
genuine run is a failed observer proof, not permission to exclude it.

The sole identity treatment is grounded in `run_checkpoint._markers` and
`_rebind_markers`: require the exact Boolean marker
`{'war_roster_bound': True}`, one unambiguous actual world marker storage, and
its raw integer equal to `id(real_bridge._sim)`, with that simulator exactly the admitted
compiled AgentSimulator class. Only that field is fingerprinted
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
first World. The project imports must come from a separate exact090 producer
checkout: this new control commit has a different Git SHA even though its
package/native trees are unchanged, and cannot serve as the090 runtime root. Exact090 package digest is
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

The original 9e933ee6 Stage 1 source remains preserved and independently
rejected before any actual run: its plain clock included the end getter while
the profiled clock excluded it, and its accepted fingerprint/RNG domain lost
some alias/layout/signed-zero semantics. A new advancing-clock regression
first failed on the exact parent source (108/216 fake seconds instead of8/16).
The corrected successor closes both clocks first and tightens the accepted
domain without adding any output exclusions.

The further 691386e6 closed-domain refresh remains preserved: identical text
for distinct concrete Path types, hidden same-name base slots and unanchored
base-less ndarray storage now have explicit barriers. Four new cases first
produced three intended parent failures plus one inherited-slot pass.

Final corrected Stage 1 pure qualification is 86 fake/metadata cases passing in a guarded
Python 3.13.5 process. No project/native/NumPy module, factory, network or child
process was used. Prior 42-, 44- and53-case source boundaries, independent rejection, the
new one-case parent reproduction and all receipts remain retained. These tests cover boundary ordering, actual-count table bounds,
RNG metadata/replay, marker rejection, reference/cycle/private/cache/native
fingerprinting and unchanged comparator invocation. They do not qualify real
cProfile timing, serialization of genuine worlds or observer equivalence.
Independent source review and a separate root decision precede any hosted run.
