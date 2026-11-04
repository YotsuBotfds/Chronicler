# Opt-in models-only ablation backend — plan for review, 2026-10-29

Status: source-reviewed proposal against
`c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`. No runtime code, new worlds or
production activation are authorized by this document. The
[11.51% median wall-cost result](models-forkserver-timing-results-2026-10-29.md)
qualifies a guarded d051/fb20 fixture, not this implementation. Root review comes
before runtime changes and a new frozen registration before world execution.

## The first deliverable

Add an explicitly selected models-only fresh-child backend to ablation launch,
keeping `fresh` as the default. Initial eligibility is Linux/CPython 3.13 with
the required pidfd/wait4 primitives, one worker and lean ablation output. Reject
unsupported opt-in configurations before claiming output directories; do not
silently reduce requested workers, change output policy or fall back after a
guard refusal. Initially support the proved needs/kin-roots arms only: placebo
and community_anchor need their own prospectively registered cases. Gate-runner
admission must reject unsupported combinations before native builds or parent
generation as well. Other platforms, arms and modes keep the existing fresh path.

Proposed API/CLI surfaces:

- `run_ablation_arms(..., launch_backend="fresh")` in
  `src/chronicler/ablation_arms.py`.
- `--launch-backend fresh|models-forkserver` on its standalone CLI.
- An explicit `--ablation-launch-backend` forwarding option in
  `scripts/m53b_run_validation.py`, after the API is qualified. Omission adds
  no new launch argument or physics configuration key.

These names are implementation proposals. The backend is workflow metadata,
not a simulation feature or a reason to change oracle methods, fork design,
seeds, horizons or thresholds. Keep default manifest/configuration shape and
import behavior unchanged. An opt-in companion execution receipt can bind the
ordinary manifest SHA to backend, source/native/environment, batch membership,
owned cleanup and failure status without inserting backend state into a world
or checkpoint. Validators must still consume the unchanged scientific inputs.

## Current source seams and differences

`run_ablation_arms` builds jobs in seed → fork turn → arm order, calls
`_fork_command`, launches fresh CLIs through its ThreadPoolExecutor, validates
outputs with `_keep_fork_outputs`, then sorts scientific records for the final
manifest. Parent checkpoints retire only after every fork succeeds. Preserve
those semantics and the duplicate-arm rejection added since d051.

`models.py`, `batch.py` and `run_checkpoint.py` themselves are byte-unchanged
between d051 and c76. Their transitive types are not: `ScholarshipState`,
`ScientificClaimsState`, proposal/message and adoption rows now use
`LazyResearchModel` and the new `scientific_research_state` classes. The actual
permitted preload module graph and model/template fingerprint need a fresh
metadata proof; copying the old five-name prefix does not qualify its imports.

Current main also adopts retained finite-research enabled/paused state in
`_adopt_checkpoint_args`, records effective configuration and declares policy
interventions separately. `_fork_ablation` owns the native term/date changes
and existing fork receipt. Preserve the real CLI adoption path; a hand-built
Namespace calling `execute_run` directly can skip those rules. The current
opt-in relationship-stat key ordering is another source correction, not a
normalization to borrow from the old benchmark.

Changed/added package files change `package_digest`, including backend files
that are dormant by default. Parents must be produced under the final frozen
implementation source and matching native/interpreter/package/thread settings.
Old d051 checkpoints remain incompatible. Never patch their identity headers,
allow a mismatch, or attach saved IDs to a freshly created substitute pool.

The clock also differs from the benchmark: its CP World 30 → 52 had 22 ticks.
Production fork label T loads World T+1 and ends at T+22: **21 actual ticks,
20 measured**. Pass `_fork_command`'s existing argv unchanged. Keep ordinary
seed/fork/arm order; do not reorder production into benchmark ABBA+BAAB order.

## Process boundary and bounded lifetime

Use a new dedicated stdlib-only controller entry, launched separately from
the API/gate caller. Do not create the forkserver context inside the current
ThreadPoolExecutor or a caller whose `__main__` may already import main/native
code. Multiprocessing bootstrap can re-import that caller before a target
function's ownership handshake. The frozen prototype avoided this with its
separate controller and explicit preload list excluding `__main__`.

Import this backend lazily after explicit selection. Neither the controller nor
its bootstrap should construct a world or native runtime. Pass only opaque
job IDs, existing argv, paths and immutable identity descriptors. The default
fresh branch must not import multiprocessing/preload code or change its launch,
output, cleanup or error behavior.

One experimental controller handles **at most eight sequential jobs**, starting
a new models-only server and tracker per batch and stopping both before the next
batch. A partial final batch is permitted only after its own coverage checks;
its startup cost stays included. No process handles a second mutated world,
and no server carries runtime/native state between children. Longer server
lifetimes or concurrent children require a new study.

Before every actual server fork require the real task count to be one; no
main/Arrow/native module family; no WorldState/native instance; and unchanged
model/class mutable content, template globals and Python/NumPy RNG bytes. The
current transitive research types belong in that fingerprint. Preserve the
type-safe GC inspection rather than calling arbitrary descriptors.

The child establishes its owned session/PID birth identity before staging or
runtime imports. It then enters the existing `chronicler.main` CLI namespace
using the actual argv, exact checkpoint loader and source-owned intervention
logic. Production code does not need the benchmark's profiling hook/witness
wrappers. Each child exits after one job; no live loaded envelope crosses an
IPC boundary. Every active native section is restored by the original loader.

Saved thread settings remain authoritative. A server safety requirement does
not justify rewriting them or temporarily hiding a cap. If an old parent cannot
support a safe one-thread prefix under its exact environment, refuse that input;
prospectively generate compatible parents instead. The backend must not silently
change the interpreter, native module, schema or environment after admission.

The controller pins ownership with pidfds/birth/session checks, verifies exit
and reaps each child before another job or any archive/cleanup operation.
Guard failure, child failure, cancellation, timeout or uncertain cleanup fails
the opt-in run and retains completed, failed and unattempted job status. No
automatic fresh fallback or selective retry. Do not signal an unknown PID.

Return successful opaque results to the existing output-validation path only
after all owned writers are absent. Keep `_keep_fork_outputs`'s receipt checks,
compression and final two-file retention. Run that postprocessing in the existing
API process after the bounded controller batch exits, or a separately qualified
postprocessing process, never in the stdlib-only controller/server:
`_compress_events` imports PyArrow and pruning deletes outputs. Parent checkpoint retirement remains
the existing whole-cohort success decision, not an eight-job-batch decision.
No new raw-evidence deletion or general retention API is part of this backend.

## Proof sequence before promotion

Each stage freezes its source, controls, exposure, resource budget and stop
criteria before execution. The proposed cases below are a review plan, not a
preregistered execution lease; no new world has run for this plan.

| Stage | Concrete deliverable | Required evidence |
| --- | --- | --- |
| 1. Contracts and default path | Lazy opt-in dispatch, strict argument validation and opaque job/result schema | Existing fresh tests pass; blocked-backend-import probe proves omitted selection cannot load it; unsupported parallel/output/platform choices fail before destination claim; complete/disjoint job coverage and failure/cancelled status cannot become success |
| 2. Metadata only | Same final-source preload/controller with two real isolation forks and zero worlds | Actual one-thread template, correct transitive module/type inventory, private first-child mutations, pristine second child, exact wait4/PID set, child bootstrap ownership, guards on every actual fork, bounded cleanup and final identity |
| 3. Exact current-state/full-window proof | New matching-source checkpoints; fresh and server continuations on complete production windows | Complete typed/aliased Python and raw MemoryStream/cache bytes/identities, all active native sections/schema, global RNG neutrality, three strict boundaries and actual checkpoint-section links, full precleanup outputs and native/cache call order |
| 4. Ordinary orchestration | Exercise the real `run_ablation_arms` plus gate forwarding, then the existing reader | Same default argv, clocks, seed/fork/arm order, exact two retained files, complete manifests, checkpoint retirement only after whole-cohort success; `validation_ablation.load_ablation_arms` verifies every historical prefix and all 20 measured turns |
| 5. Milestone/default-source qualification | Required full Python/native/Rust/viewer lanes and full template/procedural before/after gates | Default fresh behavior and enabled backend remain source-scoped; unchanged oracle policies and complete original decisions/comparisons; missing/incomparable/rebaseline evidence cannot qualify |
| 6. Current workload timing | New fixed paired study in actual production descriptor order | Whole-batch startup/guards/restore/physics/outputs/cleanup included; at most eight jobs/server; retain neutral/negative results; the old 11.51% result is not the new performance baseline |

For stage 3, a concrete initial proposal is eight logical cases, each run once
through fresh and once through one eight-child server batch: two arms at an
early and late legacy checkpoint, plus two arms at a finite-active checkpoint
and a finite-paused checkpoint retaining a nonempty archive. Checkpoints at
production labels 100/200 are candidates, with their exact T+1/T+22 clocks.
Produce them through current source-owned configuration and, for pause, the
declared experiment-fork seam. Controlled institution setup must be labelled
controlled; this is an isolation test, not a natural efficacy study.

The registration must specify actual parents/seeds, generation work, endpoints,
native section sets and resource budget rather than counting only the sixteen
continuations. Include the actually supported all-active-native configuration;
the old agent-only proof cannot cover ecology/politics pools by implication.
Require nonempty relevant research archive/host lineage for the active/paused
cases or report unavailable exposure. Do not replace empty cases after seeing
outcomes. If more input families are exposed by the first implementation, add
their proof cases prospectively or keep those configurations unsupported.

Use one common logical output path for paired proof jobs, archiving only after
verified writer exit, so no path normalization is introduced. Keep loaded,
completed and post-export boundaries distinct and preserve state-write cadence.
The sole validated runtime-binding token may be retained from the earlier proof;
any newly unexplained difference stops the study. Full-output mode, parallel
children, new native kinds, larger/different worlds and wider server lifetimes
need their own applicable proof and performance scope.

The first rollout remains an explicit experimental choice. Default promotion
is a later source-qualified decision; no benchmark percentage changes a gate,
funds a science claim or proves that a larger simulation is faster.
