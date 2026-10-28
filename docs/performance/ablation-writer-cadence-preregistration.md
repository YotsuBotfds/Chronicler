# Read-only ablation writer-cadence investigation

Registered before any diagnostic run, 2026-10-28. No production implementation
changes are authorized by this document. The completed lean-output measurement
left periodic world/memory writers active; their remaining cost is a separate
question from the already measured post-run export change.

## Diagnostic controls

Reuse the genuine combined five-system checkpoint at completed turn 30 from
frozen `d051d7c0`, matching native receipt release `fb20dbc8…`, and continue each
control to completion 60. Seed, all saved feature controls, exact native state,
reflection interval, final-turn settlement detection and every simulation/RNG
call remain common. All controls use the same `needs` decision ablation from
source turn 30, so this is an output-policy comparison rather than a new causal
assessment of any feature.

Compare the existing options only:

1. Full ordinary output with the default state cadence of 10.
2. Existing lean ablation output with cadence 10.
3. Existing lean ablation output with `--state-every 61`, above the completed
   horizon. This suppresses intermediate legacy state saves and extra memory
   rewrites; the final memory save remains active. It does not suppress runtime
   memories/history, reflections, final sidecars, periodic validation sidecars or
   any simulation operation.

The cadence option is already output-only and freely overridable at exact
resume. This probe does not adopt it for the orchestrator, change a scientific
window/sample count, drop a turn or alter the 110-second offline chunks.
Interactive pauses, quit callbacks and newly requested exact checkpoints are
outside this control. Checkpoint-origin/state semantics still require explicit
review before a future profile may suppress writes generally.

## Proof and profiling boundaries

First run each control with a read-only end-of-turn observer, after memory,
reflections and ordinary writers. Compare every boundary's complete persisted
WorldState, private contact/hazard/artifact signals, authoritative archive states,
complete native checkpoint bytes, memory entries/reflections, history and pending
injections. Compare final state again after finalization. Do not invoke memory
JSON encoding in the observer: it would populate the cache whose differences are
under investigation. Record cache sizes/signatures separately and treat them as
cache differences, not independent proof that exact Python checkpoint payloads
are identical. If a carried authoritative value differs, stop this candidate.

Compare raw agent-event schema/bytes and the retained compressed events and
four-field fork receipt. Check completed turn and the final settlement call.
A mode may omit different output files, but it may not manufacture data or erase
an incomplete/failing run. All destinations are new and evidence is outside Git.

Then profile uninstrumented repeats of these controls separately. Correctness
observers must not inflate the measured simulation share. Attribute current
worker costs to exact restore/imports, simulation, memory/state writers,
validation sidecars and final exports. Profile import cost separately if useful.
These are diagnostic profiles under qualification load, not clean performance
benchmarks, and they establish no speedup claim. Before any implementation,
choose the narrowest mechanism justified by the measured call graph and document
its effect on encoding caches and future checkpoint continuation. A full paired
benchmark and broader correctness controls would remain separate work.

The frozen source, compiled extension, parent-checkpoint digest/header, exact
commands, controls, profiler overhead/limitations, call counts, output inventories,
completion/failure states and any counterexamples must be retained. CPU execution
waits until the lead's qualification budget has a free slot.

## Source inspection before CPU profiling

`MemoryStream.json_text()` populates `_encoded`; the class currently has no
checkpoint reducer that drops this derived cache. The exact checkpoint pickler
therefore carries it. Changing writer cadence can change intermediate Python
payload bytes even when entries/reflections and the native simulation match.
Do not equate unchanged WorldState JSON with complete checkpoint-byte identity.
A later continuation test must establish the relevant promise, or a future
worker profile must explicitly exclude new checkpoint/callback paths. The final
mandatory memory save may rebuild the same cache, which does not establish its
identity at earlier boundaries.

Another candidate is public procurement: each foreign successful purchase calls
`finance.transfer`, constructs `_Book`, and recomputes `_projections` over pending
keep changes. This can revisit an expanding accumulator for every purchase. A
phase-local book could avoid the repeated scans, but it must preserve each
ordered clamped/integer debit, foreign credit, domestic sink and finance specie
movement. Current receipt instrumentation already reuses opening projections;
it does not optimize the authoritative purchase kernel. Profiling must establish
whether that kernel matters before any refactor.

The full Rust qualification also measured a workflow constraint: its warm debug
cache was 1.7 GiB, but the complete copied test target expanded to 8.3 GiB and was
removed after completion to preserve active gate capacity. A future build-profile
or target-lifecycle study could retain all tests while reducing debug-artifact
cost; no such change was applied to the completed qualification.

Actual diagnostic/profiling runs remain pending. The lead subsequently held all
new build/probe jobs during disk recovery. These are source-based hypotheses,
not measured CPU shares or implemented optimizations.

## Resumed diagnostic protocol

The lead released one sequential CPU slot after disk recovery. Before launching
the correctness runs, extend the observational proof with one exact checkpoint
at completed turn 40 in each control. The observer requests this save after the
ordinary writer/reflection boundary; it never forces a memory JSON save. Each
new checkpoint is then genuinely restored and continued 40→60 with its original
control. Compare continuation boundaries 41–60 and final state with the direct
30→60 run. Keep raw Python/native section hashes, the memory subgraph's actual
pickle bytes, and memory-cache contents separate from physical equivalence.
Checkpoint paths and output-policy metadata may independently differ, so whole
Python-section differences alone cannot be attributed to the memory cache.

A cache-only serialized difference is still a counterexample to strict carried
Python checkpoint equivalence; do not waive it or adopt cadence suppression on
the strength of physical equality. Existing-option profiling may continue after
a successful physical/continuation check solely to diagnose costs, with that
failed stronger promise stated explicitly. Any authoritative or continuation
divergence stops profiling. All profiler workers omit the correctness observer
and the extra turn-40 checkpoint. Only one profiled repeat per control is planned
under two active scholarship workers and potentially the lead's other bounded
lane; no statistical timing or speedup conclusion follows.
