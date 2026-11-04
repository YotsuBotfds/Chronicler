# Compiled named-context API measurement — source only

This separate701-based experiment measures the existing native
`get_agent_context_batch` against the three scalar context getters. It changes no
product caller, native source, simulation default or checkpoint format. All new
contracts, builds and measurements are UNRUN at this source freeze. Local
native/build/World execution and the installed-API protocol remain held.

## The source question

Hybrid named-character sync currently reads memories, needs and relationships
for each active GreatPerson with a nonnull agent ID, in civilization/person
order (`agent_bridge.py`, the sync immediately before sidecar sampling). Each
scalar getter locates the agent by scanning pool slots. The existing additive
batch API sorts/deduplicates requested IDs locally, scans allocated slots once
with binary searches, and restores input order and duplicates. Its current
implementation scans every allocated slot even after finding all requests.

This is a named-record lookup question, not a demonstrated per-region
`O(regions × agents)` context builder. The normal registry caps living named
characters at50; imported/custom records need not obey that cap. Both paths
remain linear in allocated pool capacity under the normal cap, with different
scan/crossing constants. Early-slot small requests can favor the scalar path.
No existing whole-turn timing result transfers to this source.

## Fixed conditions and work before timing

The first method has21 conditions, each with three interleaved trial pairs and
20,000 requested context records per helper per trial:

- 18 empty-memory/empty-bond cases: allocated slots512/8,192/65,536, request
  vectors of1/50 IDs, and prefix/spread/missing layouts.
- 3 populated-bond cases:8,192 slots, spread vectors of1/10/50 IDs, each queried
  live agent holding eight directed friend bonds. Memories remain empty.

Layouts use actual snapshot slot order, not sorted agent IDs. Prefix requests
take the first slots; a one-ID spread selects the middle slot, while larger
spread vectors include both endpoints. Missing requests use distinct absent
uint32 IDs. No adaptive case selection or repetition tuning occurs. The scalar
reference performs three bound method reads per requested record; the batch
side reads the same vector per repetition. Both include the same small checksum
consumer. Python GreatPerson decoding/assignment is deliberately unmeasured.

For the declared matrix, a conservative full-scan upper bound is
**84,602,880,000 scalar slot visits**. The batch side executes
**14,180,966,400 slot-loop visits**, plus binary-search, sorting, conversion and
consumer work. These are source operation bounds, not retired instructions or
a prediction that the job will fit. Prefix scalar scans usually stop sooner.
The bounds exclude untimed initialization, parity checks and200-record warmups.
This is materially less work than a54-condition/six-pair/50k-record sweep.

Each fixture is created through the actual compiled `AgentSimulator` and
`set_region_state` in exact scale mode. It initializes agents without a World or
physics tick. Populated-bond fixtures use existing `apply_relationship_ops`.
No promotions or actual named-character synchronization are run; selected
ordinary agent IDs exercise the same context API. Requested rows are compared
with actual scalar output before/after timing, including ordered f64 bit
representations. An untimed duplicate/missing control checks independent memory
lists. The existing native contract module retains broader boundary coverage;
this benchmark is not a substitute for its own source-bound test evidence.

## Clock and failure evidence

Every timed helper invocation retains all four wall/process-CPU endpoints,
deltas, checksum, case/trial/helper order and numerical acceptance. Each row is
flushed before acceptance can affect the result. First helper order alternates
by case and trial. All three planned pairs remain; zero/nonpositive clocks or
checksum mismatches refuse that condition's numerical summaries without retry.
A helper exception is journaled before aborting; the failed condition and all
remaining `not_run` conditions remain in the result. External termination leaves
the prewritten plan/partial journal and owner exit evidence, not a fabricated
completed result. The plan is also retained before the build starts.

For complete conditions, medians and original-scalar/batch ratios are reported.
Ratios below1 and positive batch wall changes explicitly expose regressions.
`complete` means the registered measurements and parity checks completed; it is
not an optimization-adoption decision. No elapsed clocks are synthesized or
rerun to replace a negative first attempt.

## Hosted execution and publication seam

The default script invocation is disabled and imports no native runtime.
`--plan-only` is explicit metadata output. Actual measurement uses
`--record-build` followed by `--execute` in the separate manual hosted workflow.
The workflow builds its own release locked wheel into fresh private directories,
installs it into the locked Python environment and links the installed ELF to
that wheel with the existing lower-level `native_wheel_receipt` helper. Actual
Git source/tree, native tree09ec, script/workflow/helper/lock hashes, toolchain
version records, Python/platform, thread settings and GitHub identities remain
separate recorded facts. No standard native-shard job identity is spoofed.
This establishes an own-build link, not reproducible-build certification.

The build has a separate40-minute step limit inside a60-minute job. It is
outside the comparison limits. The comparison alone has600 wall seconds,
540 CPU seconds,2GiB address space and one allowed CPU. It checks its actual
affinity and process limits before loading fixtures. These bounds do not prove
available host memory, a successful run or a measured whole-attempt RSS.
Wall-time termination uses immediate KILL at600 seconds, without an extra
termination grace period; the owner retains the actual exit status, including137.
All source/identity/resource failures remain failures; no automatic cap increase
or same-source retry is supplied. First-attempt checks reject run attempts>1.

A new dispatch-only workflow may not be available before it reaches default,
and main remains untouched. Therefore source-only publication uses
`lead/named-context-benchmark-source-20261030`. The first separately approved
hosted experiment is a normal push of that reviewed commit to the exact
`lead/named-context-benchmark-run-20261030` ref, which is the only push trigger.
That second push is an execution action, not mere source publication. A future
manual dispatch, if supported by the workflow catalog, is restricted to the
same run ref; it supplies no autonomous retry authorization. Existing
`tests.yml` stays unchanged and can run ordinary CI on the source branch.

Structured evidence has a2MiB body ceiling including the serialized owner
receipt, with a512KiB per-file ceiling. An overflow retains only bounded owner
refusal metadata. The own wheel is a separate at-most16MiB file, retained even
if the comparison fails after build identity succeeds. Actual artifact ZIP
sizes are not preclaimed. Numerical,
setup, identity and transport refusals stay distinguishable, with the owner
receipt retained on failure. These hosted output caps authorize no local
wheel/ELF download, probe or installed-API execution. Runtime artifacts stay
outside Git. The source contains only this tool, its pure fake contracts,
workflow, documentation and one appended offline chunk with the existing
110-second limit. The offline report additionally pins the benchmark script
imported by those fake contracts; all previous source-pin entries remain.

No current native/World acquisition, full Python synchronization, trajectory,
RNG/checkpoint continuation, population capacity, scientific efficacy or
whole-turn speed claim follows from source readiness or a future kernel ratio.
