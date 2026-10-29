# NumPy-only preload assessment, 2026-10-29

**Screen the simpler prefix before investing further in compiled-model
fingerprinting, but limit that investment to a prospective metadata/startup
feasibility stage first.** Existing measurements suggest a modest import-only
opportunity. They do not justify commissioning the full native/world proof on
the assumption that the earlier 11.51% result will transfer.

This is a new source-only proposal, tentatively named `numpy-forkserver`, with
explicit preload `numpy`, then `numpy.random`. No backend, API/CLI choice,
runtime implementation or registration is activated. The original models-only
plan, published result, inert contracts and dependency adapters remain separate.
No new runtime import inspection, fork, world, checkpoint or native build ran.

## What the saved measurements support

Seven existing server logs were rehashed against the successful independent
reader's inventory: the metadata/correctness prerequisites and all five timed
servers. Only the five timed servers enter the summary below; the other two
remain separately labelled in the [data record](numpy-preload-existing-costs-2026-10-29.json).
Twelve old input files were checked before and after this read-only calculation.
This is not another reinspection of every simulation payload.

The old source was `d051d7c0`, timing controls `811f5153`, native binary
`fb20dbc8`, CPython 3.13.5, NumPy 2.5.4, Pydantic 2.12.5/core 2.41.5.
These are cold-server import segments inside the larger ordered prefix:
Chronicler package → NumPy → NumPy random → Pydantic → models. Fresh workers'
individual import costs were not measured separately.

| Timed pair | NumPy + random CPU, s | NumPy + random wall, s | Entire explicit prefix wall, s | Fresh eight-job batch wall, s |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.06490 | 0.07136 | 0.49383 | 27.04880 |
| 1 | 0.07312 | 0.07410 | 0.41339 | 30.44984 |
| 2 | 0.06730 | 0.06857 | 0.45553 | 27.30391 |
| 3 | 0.08002 | 0.08180 | 0.51534 | 27.85042 |
| 4 | 0.05650 | 0.05739 | 1.38476 | 25.32633 |

The combined NumPy segment's median is **0.06730 CPU / 0.07136 wall seconds**;
ranges are 0.05650–0.08002 CPU and 0.05739–0.08180 wall. Keep the final pair's
large models-import interval; do not drop it or treat import segments as
independent scientific samples. The medians of the five individual NumPy-share
fractions put it near 15% of the explicit full-prefix import time.

For orientation only, if eight fresh imports cost the same as those measured
server segments, replacing them with one would avoid `7 × segment`:
**0.4711 CPU / 0.4995 wall seconds** at the segment medians. Using each pair's
own fresh whole-batch denominator gives median fractions **1.686% CPU /
1.758% wall**, with wall fractions 1.586–2.056%.

That arithmetic is neither a measured gain nor a strict upper bound. Import
order/cache context, a different prefix, new guards, process bootstrap,
controller/server/tracker startup and cleanup all matter. A useful accounting
model is `avoided repeated NumPy imports + other avoided bootstrap − new
backend overhead`; the latter two terms are unmeasured for this candidate.
Do not multiply 11.51% by an import share and label the result a prediction.

The later descriptive inspection used the same NumPy version and matching
package-init/primary-core hashes, but Pydantic 2.14.1/core 2.50.1 and newer
Chronicler source. It did not time these import segments. It supplies no new
NumPy-only performance sample or correction factor.

## Why it is simpler, and what remains

No Chronicler, Pydantic or models exist in the shared server. Children create
their own model classes, lazy research metadata and compiled schemas after
forking. That removes the 159-class Chronicler fingerprint plus dependency-
adapter problem from
the shared boundary. NumPy still imports compiled code, global state, locks,
configuration and RNG machinery; the smaller prefix is not stateless or
automatically fork-safe.

Use detached stdlib-only controller/preload/child-bootstrap modules. Even
`import chronicler.ablation_launch` executes the package initializer and is
therefore forbidden before the fork. Let the API validate in its own process,
then pass primitive IDs, paths and unchanged existing argv to the detached
controls. Replace multiprocessing's default preload list so the caller's
`__main__` cannot be imported into the server.

The import-order trap is concrete: `chronicler.__init__` normally sets
`OPENBLAS_THREAD_TIMEOUT=16` before NumPy loads. With NumPy first, setting that
environment string later in the child does not establish that NumPy initialized
under it. Require the saved effective thread environment, timeout, all caps,
hash seed and registered affinity **before the first NumPy import**. Generate
matching parents prospectively; never repair a header or silently override a
saved setting. Mere eventual environment-string equality is insufficient.

Before every actual server fork require one OS task, the closed registered
module/build inventory, unchanged NumPy configuration/RNG witnesses, unchanged
server Python RNG and private marker, and no WorldState/native simulator
instances. A detached type-safe GC classifier can check those names without
importing Chronicler. Reject attempted imports of all Chronicler,
Pydantic/pydantic-core, PyArrow and Chronicler-native families, including caught
attempts. Verify file origins as well as names; a source module loaded under an
alias is not an acceptable loophole. No numeric/simulation job runs in the server.

Keep the pre-bootstrap child `setsid` → peer-credential/birth/pidfd handshake.
Only after controller acknowledgement may that child remove its own import
guard and enter the real CLI namespace. Pin/reap the exact workers and direct
helpers, bound cancellation and descendant cleanup, and require empty owned
groups before archive/retention. Limit the proposed first lifetime to eight
sequential jobs; no parallel, longer-lived or retry/fallback path is implied.

## Prospective proof sequence

1. Freeze new controls, exact source/environment/native/build identities,
   prefix inventory expectations, resource budgets and stop criteria. Keep the
   fresh path and existing manifests unchanged; reject unsupported opt-in
   modes before native builds, parent generation or destination claims.
2. Run the separate two-child metadata isolation proof: first child privately
   mutates a marker and Python/NumPy RNG state; second must inherit a pristine
   server. Record every actual fork and successful server wait4 reap, owned
   birth, task/module/object inventory and complete final cleanup. Child Python
   at-fork entropy is descriptive, not compared with the server or other child.
3. Before creating scientific parents, use a separately frozen, bounded
   eight-job metadata/startup screen to measure all new process/guard/cleanup
   costs against fresh launches. Retain neutral/negative results. This can
   reject the idea cheaply; it cannot qualify simulation performance. Set its
   acceptance before execution, without changing the old study's criteria.
4. If the engineering opportunity survives, generate matching-source parents
   and compare fresh against this prefix over the exact production windows.
   Source review finds seeded local simulation RNGs and no direct NumPy-global
   sampling calls, but the checkpoint does not restore Python/NumPy module
   globals. Require new **unseeded** within-job RNG neutrality through imports,
   load, physics and exports; never seed actual jobs just to make equality pass.
5. Cover the registered needs/kin cases, early/late legacy checkpoints and
   finite-active/paused research archives, including actually active agent,
   ecology and politics native sections. Fix seeds/configuration/exposure
   requirements before outcomes; missing archive exposure is not replaceable
   after inspection. Include parent generation in the budget.
6. Preserve `_fork_command`, real checkpoint argument adoption and intervention
   dates. Label T loads World **T+1**, executes ticks **T+1…T+21**, finishes
   World **T+22**: **21 actual ticks, 20 measured turns**. The older benchmark's
   World 30→52 had 22 ticks and does not prove this window.
7. Compare loaded, completed and post-export typed/aliased state, raw memories
   and caches, every active native blob/schema, actual checkpoint-section
   links, all precleanup outputs/Arrow bytes and source call/settlement order.
   Keep one logical output path. Retain only the previously source-verified
   runtime-binding token if it remains applicable; any new difference stops.
8. Exercise real orchestration/reader validation and complete CI/scientific
   qualification, with original gate policies, whole-cohort checkpoint
   retirement and publication evidence. Only then run a new fixed paired
   whole-workload timing study in production descriptor order. Include all
   startup/guards/restore/physics/output/cleanup costs and all pairs.

The first three stages establish a smaller, concrete feasibility question without
claiming the original result. NumPy import reuse alone is below that old
study's 5% whole-workload bar in this illustrative arithmetic. Other startup
savings might help, but have no measurement here. Keep the initial investment
small, stop if complete guarded overhead erases it, and defer deeper compiled-
schema machinery while testing this simpler boundary. Larger worlds, more
workers and longer server lifetimes need their own evidence; there is no
simulation-tick speedup or full-gate wall-clock projection in this assessment.

Independent source/data review rehashed the twelve old inputs (1,108,167 bytes),
reconstructed all seven ordered import records and five paired calculations,
and confirmed before/after input identity. Source and data review cleared this
assessment's scope. JSON parsing and `git diff --check` pass; production,
controller, test and generic-codec files are unchanged by this document-only work.
