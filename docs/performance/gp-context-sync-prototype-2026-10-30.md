# GP context sync prototype

The normal hybrid loop remains byte-exact to staging004. This private candidate
does not replace it, add a user flag, change a schema or store a World/Native
cache. Every check against this candidate is UNRUN. Its intended activation is
one later reviewed call site after functional and complete Python-sync evidence;
getter-only timing does not justify that activation.

The current loop reads memories, needs and bonds separately for each active GP
with an agent ID, after promotion/death/dynasty handling and before sidecars.
The compiled batch API has no production caller. Its frozen paired benchmark
has 11 batch-wall gains and 10 regressions across 21 synthetic conditions; that
does not measure this Python loop or supply an adoption crossover.

## Exact fallback and bounded candidate

`chronicler._gp_context_sync` provides an exact extracted scalar-loop reference
and an explicitly called batch prototype. The reference's declared code object
uses the original bridge module globals through `FunctionType`, preserving
per-occurrence memory-helper lookups and ordinary monkeypatch behavior without
adding a wrapper call for each GP. No input source is evaluated. Existing
`AgentBridge.tick_agents` and all normal production imports remain unchanged.

Admission requires the already-loaded genuine compiled class, original four
owned C descriptors and bound receivers; it does not import Native or probe a
foreign batch getter. It also requires stock Bridge/World/Civ/GP access and
Pydantic assignment machinery. Relevant Python function origins are checked so
ordinary wrappers installed before this module loads do not become trusted
merely by being captured. This is compatibility checking, not adversarial C or
Python code attestation. Arbitrary modified Pydantic internals are unsupported.

Only the three overwritten GP context values are traversed for plain builtin
contents, under fixed 512-node/16-depth limits with cycle refusal. Private and
extra GP metadata is not projected out. IDs must be exact integers in the U32
range; bool/subclasses/invalid IDs and more than 50 requested occurrences choose
the original scalar path before any batch read or GP mutation. Fifty is a
bounded allocation scope, not a measured speed threshold. Foreign containers,
models, setters, getters and helper overrides retain scalar order and failures.

The batch keeps occurrence order and duplicate IDs. Converted lists and
dictionaries are independent per occurrence. It preserves the existing decoder
for five/six-field memories, legacy flags, signed values, needs float bits and
conditional writes. Missing/dead IDs clear memories but leave old needs/bonds;
zero can provide memories/needs but never bonds. Inactive and None-ID entries
stay untouched; no extra alive/source filter is added. Return behavior, sidecar
position, RNG and Native persistence are unchanged by the proposed reads.

Batch row count, identity/order and primitive shapes are checked before any GP
assignment. Valid rows then use the existing ordered memory/needs/bond writes.
Bulk prefetch can raise an allocation/conversion error before the old loop's
partial progress. The candidate does not hide that difference, swallow the
exception or retry scalar after it. Default promotion requires explicit review
of that eligible-path failure boundary; universal exhaustion equivalence is not
claimed. Actual allocation bytes and natural workload frequencies are unknown.

## Required evidence and next activation

Pure contracts cover foreign getter traces and partial failures, changing ID
properties, invalid later IDs, pre-import wrappers, unsupported Pydantic handlers
and metadata, bounded context traversal, complete legacy/float conversion,
independent containers and repeated GP occurrences. One additional guarded
chunk retains all 43 prior chunks, their selectors and the 110-second cap.
The new contract filename is outside default pytest discovery; existing 305
native owner mappings stay unchanged.

Real-Native cases extend `tests/test_agent_bridge.py` in owner0. They compare
complete GP values/private/extras/fields-set/alias topology, Native checkpoint
bytes/schema and global RNG states against scalar. Passive C-call tracing,
restored on every exit, witnesses one batch versus three scalar calls per
eligible GP without replacing the original methods. One explicitly declared
Native-only setup tick creates a dead-ID case; no Python World turn is run.
Ordinary zero is a missing-ID control, not a fabricated live zero. Legacy store
positions/flags, float bits and live-zero details remain separate Rust and pure
contracts unless an actual fixture demonstrates them. All new cases are UNRUN.

The prospective `named-gp-sync-v1` study compares the real private helper against
the closed old-loop reference on the same frozen source and admitted binary.
It includes ownership checks, conversions and Pydantic writes in timed work.
Fixed N=512/8192/65536, P=0/1/2/5/10/25/50 and prefix/spread/half-missing layouts
(one P0 control each), six all-missing P1/50 cases and six fixed post-tick spread
cases give 69 conditions. Include inactive/None-ID controls, three counterbalanced
pairs, 414 fresh serial workers, 256 sync calls and two fixed warmups per worker.
Existing public APIs prepare payloads outside clocks; record actual store/alive
counts, with no fabricated populated slots or seed retries. Wall is primary;
CPU zeros remain visible diagnostics with undefined ratios. No calibration or
P threshold is selected from the old benchmark or this unrun proposal.

Before activation, freeze statistical/output limits and a fresh resource grant:
prospective 600 wall/540 joint CPU seconds, one CPU and 2 GiB application address
space with per-worker reserves. Fit is unknown; retain failures and not-attempted
roles without shortening work or lifting caps. A later crossover policy needs
its own frozen variant and validation. Only subsequent matched ordinary
whole-turn evidence can establish simulation throughput. No publication, first
Native execution, performance run or production activation follows from this
source packet alone.

## Corrective source child

The first independent full-source review blocked three guard issues: a top-level-only qualname check rejected the genuine `AgentBridge.tick_agents`; raw-dictionary collection missed effective read-field descriptors; and ordinary class lookup could invoke a foreign `tick_agents.__get__` before fallback. The corrective child resolves only relevant guard/field owners through raw class/MRO dictionaries, then checks the actual class-method qualname. Relevant field reads are World.civilizations, Civilization.great_persons and GreatPerson.active/agent_id; any effective class member on them selects scalar without evaluating it. Existing context writes and assignment handlers are guarded through the same static mechanism. Bridge metadata, Pydantic accessor/config/handler machinery and memory-record metadata are checked without foreign descriptor or equality calls; exact metaclass `type` supplies its own fixed qualname metadata. Rebinding the Pydantic field-handler map also selects scalar. This is a small compatibility gate, not generic descriptor or adversarial-code attestation.

All44 original pure cases and both original Native cases remain byte-exact. Twenty-two new pure cases exercise positive stock-class admission, pre/post-import read-field fallback traces, tick descriptors that return the old method or raise, actual guard metadata descriptors and handler-map rebinding. The positive pure control explicitly injects a Python API seam only; it does not counterfeit or qualify compiled C provenance. Actual Native admission/state equivalence still requires the two unchanged guarded cases. No Native/PyArrow objects or performance experiment is created by these new cases. All68 prospective cases are authored UNRUN.

The production bridge/scalar loop, exact scalar reference/global binding, native tree, care pins, default routes, flags,43 earlier chunks plus the existing44th prototype chunk,110-second caps and305 native owner registry remain unchanged. There is no performance threshold, activation or new runtime grant.
