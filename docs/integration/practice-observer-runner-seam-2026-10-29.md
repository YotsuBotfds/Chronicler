# Explicit practice observer in the production runner

`execute_run(..., practice_observer=observer)` accepts a caller-owned
`PracticeGrowthObserver`. The parameter is keyword-only and defaults to `None`.
Omission and explicit `None` retain the original turn call and arguments.
Neither path imports or constructs an observer.

When supplied, the observer's `run_turn_result` owns one normal turn inside
the runner's existing SIGINT-deferral context. The runner hands the unchanged
`TurnResult` back to its normal observation, snapshot, memory and checkpoint
processing. It neither retries physics after an exception nor falls back to
a second unobserved turn. The observer already isolates its own reporting
failures; physics errors and cancellation retain their original propagation.

The caller owns observation configuration, reads and closure. The runner does
not attach the handle to the World, RunState, run configuration or checkpoint,
and does not close it automatically. There is no CLI flag, automatic writer,
callback or default activation. An existing caller-owned `turn_boundary`
object may read the latest frame after the normal checkpoint/reflection
boundary, using `expected_source_turn=world.turn - 1`. A later runner error can
prevent that boundary from being reached; it does not turn missing evidence
into a zero or justify replaying the turn.

This seam does not change the observer's clocks. A captured committed value
belongs to the Phase 4 technique-table commit; full-turn and runner completion
occur later. It estimates neither a counterfactual paid gain nor welfare.
See the [observer API and limits](practice-growth-observer-2026-10-29.md).

Focused guarded validation passes 91 cases: the existing 65 observer cases
and 26 runner surrogate cases. They check omitted/None/provided dispatch,
exact arguments and result identity, one-call ownership, exception and
cancellation propagation, and actual deferral logic with fake signal/thread
namespaces. No OS handler, real signal, thread or World is created by those
new tests. The unchanged 110-second offline chunk now includes both pure files.

The complete default `main.py` AST equals qualified parent `1205b6e4` after
removing only the two observer parameters and selecting the two original
identity-based None branches. Serialization explicitly uses CPython 3.13
`ast.dump(annotate_fields=True, include_attributes=False, indent=None,
show_empty=True)`. Production docstrings, imports and all other AST nodes are
included unchanged. The initial 90-pass/one-failure attempt is retained: its
fixture mixed Python 3.12 and 3.13 default AST formatting. The corrected check
uses explicit canonical options and direct parent/candidate equality.

Two genuine `execute_run` cases are authored for remote full Python CI only
and remain unrun locally. A bounded paid-runtime fixture starts at turn 12
and completes ordinary turns to 14, with normal action selection and actual
public observation. Omitted and explicit-None controls compare state, raw
checkpoint history/events, allocations/debits, caller Python/NumPy RNG,
normal outputs and RunResult against observed runs. Only the existing bundle
generation timestamp is normalized; exact checkpoints are separately loaded
and checked for ordinary state/native equality and observer transience. These
cases do not substitute for a fresh natural CP60 continuation prerequisite.

This is an isolated child producer derived from qualified `1205b6e4`, whose
runtime trees match `9d5cb7e4`. New source review and hosted qualification are
pending. It is not literal `9d`, a C76 replay, a study activation, a default
promotion or a measured performance/scientific result.
