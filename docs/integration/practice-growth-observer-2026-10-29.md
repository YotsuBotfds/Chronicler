# Explicit practice-growth observations

This Python-only candidate starts from `45e1b939`, preserving qualified
`95f73a74` and frozen C76. It observes the existing technique kernel; it changes
no allowance, payment rule, decision, study registration or native source.

```python
from chronicler.practice_growth import PracticeGrowthObserver

observer = PracticeGrowthObserver([(4, "irrigation"), (4, "masonry")])
source_turn = world.turn
normal_text = observer.run_turn(world, action_selector, narrator, seed=world.seed)
readout = observer.read_latest(expected_source_turn=source_turn)
observer.close()
```

`run_phase(world, acc=None)` calls the existing Phase-4 owner once.
`run_turn_result(...)` calls the ordinary synchronous turn owner once and
returns its unchanged `TurnResult`; `run_turn(...)` exposes its chronicle text.
These are explicit alternate entry points for a caller already owning the
phase/turn loop. No CLI, callback, file writer or automatic history is added.
The default owners import no observer module and attach no observer or
configuration to World, bridge, RunState or checkpoint. An observer itself
refuses pickling; reconstruct it explicitly after restore.

Each invocation invalidates the previous frame before fallible preparation.
A phase frame is published only after the normal technique tick returns;
a turn frame waits for the whole normal turn result. Existing physics errors
and cancellation propagate without rollback and leave no current frame, even
when a later phase fails after technique commit. Reporting failures produce a
fixed unavailable reason and leave normal return values and physics intact.

Selections are explicit, unique `(region index, existing recipe key)` pairs,
in deterministic region/registry order. At most 64 rows are admitted. The
default 64-KiB ceiling measures the compact JSON encoding of row data, checked
before publication; it is not a process-RSS or total-Python-object-size claim.
Limits may be reduced, not expanded. A byte-limit refusal retains no row
payload. Empty selection, unobserved phase, unavailable capture and a genuine
computed zero are distinct. Caller-retained older readouts are outside the
collector's one-latest-frame ownership.

Each observed kernel row preserves the actual pre-practice, suitability
reference cap, prerequisite/population/support/disruption values, ordinary
growth, the **actual paid RHS**, total growth, post-learning forgetting and
diffusion, pre-clip sum, [0,1]-clipped value, six-decimal rounded value and drop
status. The existing expressions are evaluated once in their original operand
order. The paid RHS is not reconstructed by subtracting two growth values.
Python floats remain unrounded in the readout; callers can use `float.hex()`
to retain their exact bits.

Selected final values are read from the existing practice dictionary when
`st.rows` commits, after scholar carries/invention and before normal return.
This requires no extra full-row copy. A kernel row that never reaches its
main assignment remains `kernel=None` / `kernel_status="unobserved"`; an empty
population's separate fade path, missing source or missing region is not
invented as zero or given an unobserved gate reason. A final value may still
exist, for example after scholar carries. A dropped row is absent rather
than a stored zero. `paid_status` distinguishes blocked prerequisites,
missing supplied effort, blocked headroom, evaluated zero and evaluated RHS.

Allowance presence/value is read from the actual grant dictionary. Current
allocation rows expose seat/share/confidence, per-row bookkeeping payment,
the total bookkeeping payment for that seat/region group, and optional event
ID. Group totals repeat on both recipes: deduplicate by source/seat/region
before summing. `paid=0` on masonry can accompany both a positive allowance
and a positive paid RHS. An unchanged repeat payment can have an empty event
ID. Old allocation rows are not attributed to the current source. These are
allocation/debit bookkeeping observations, not an independent treasury-ledger
receipt or an attribution of net treasury change; a caller-owned accumulator
may still await its ordinary flush when only the phase API is used.

An allowance, evaluated RHS, kernel net change, final committed change and
causal effect are different quantities. Forgetting/diffusion, saturation,
floating addition, clipping, six-decimal rounding and later phase work can
separate them. The observer computes no counterfactual and measures no causal
production or welfare effect. The eight previously retained natural-study
allowances are not retroactively instrumented, replayed or requalified.

Focused validation passes 64 guarded tests on the actual scalar kernel with
tiny SimpleNamespace/TechniqueState/ScholarshipState surrogates. It covers
bit-exact state/RNG, one allocation call, paid-zero bookkeeping, actual scholar
carries, blocked/zero/unobserved paths, Python half-even/up/down rounding,
clipping/drop, reporter faults, stale attempts, bounds and transience. No
ordinary World, local native runtime, build or study was executed. Full normal
turn dispatch is checked with a surrogate owner and source equivalence;
fresh remote integration qualification remains separate.

Two ordinary-World cases are authored for remote full CI only, reusing the
existing scientific-claims paid-runtime fixture. Phase and fourteen-turn
comparisons require real allocations/positive paid RHS and identical normal
state, events, treasury/debits and caller Python/NumPy RNG. They have not been
run locally and are excluded from the bounded offline chunk.
