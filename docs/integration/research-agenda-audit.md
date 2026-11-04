# Recorded research-agenda audit and comparison

Consumer work registered from `10629a01`, before implementation. This adds only
bounded read-only readers for the producer's optional
`scientific_claims.research_agendas`, schema 1 / `finite-retained-v1`. It changes
no scheduler, state, experiment control, simulation call or stored run.

Absent metadata retains the legacy reader. Present null, unknown or malformed
agenda metadata fails closed rather than silently becoming legacy. Actual
activation/opening/closure/blockage dates must be available by the section's
source turn; future deadlines and earliest-opening plans remain legitimate.
Legacy-adopted cycle zero has an observed activation roster and no inferred
historical funding deadlines. New opening membership and canonical topic
identity are immutable within continuous recorded spans; gaps break continuity.

Capacity arithmetic compares recorded used/reserved/limit quantities and the
complete dated proposition/cycle tables where supplied. Retained trial IDs and
archive totals do not expose all paid trial bodies or archived receipt rows.
`trials_resolved` is only the actual resolution source turn, never a full
historical export. Late or gapped histories cannot be upgraded to complete from
totals or a final WorldState. Paused funding remains distinct from retained
knowledge, paid work, delivery and ordinary adoption use.

Paid allocations in agenda mode identify the actual Phase 4 canonical
`claim_id`. The reader joins that ID to its dated proposition and never infers
it from recipe or end-of-turn confidence. Future actual bodies are withheld.
All rows/details/events use the existing shared audit limits.

Strict comparisons disclose mode/activity and immutable activation lineage
separately from mutable experiment controls. Compatible finite arms require
the recorded pre-intervention boundary at source `start - 1`, with a finite plan
already present; unknown/missing finite lineage blocks comparison. Later cycle outcomes are not required to match.
No-op labels also require compatible recorded research history. Derived mode
must never enter `controls_for_state` or its control setter.

Verification uses the producer's literal source-0 mechanical summary plus small
adversarial reader fixtures: unsupported metadata, future actual dates, planned
future deadlines, legacy unknowns, pauses, immutable membership, capacity
conservation, late resolution coverage, actual allocation identity and contrast
lineage. No cohort simulation or efficacy qualification is part of this task.

## Implemented reader boundary

`scientific_research_audit.py` has a pure dated mode/lineage reader and a bounded
history auditor. Known v1 metadata checks actual dates and inclusive funding
windows, immutable opening membership, append-only funding membership, immutable
closed cycles, nonoverlapping funding histories and the fixed grain protocol.
It checks used/reserved limits, complete retained ID membership, archive/core
count agreement and only the reservation inequalities observable in summaries.
It does not reconstruct recipient or parent-trial bodies from reserved counts.

Known future deadlines and earliest next-opening dates are plans. Future actual
activation/opening/closure/blockage dates withhold the metadata body. Present
unsupported metadata yields an explicit finding and `scan_complete=false`;
absence alone preserves the legacy report shape. Detail rows and cycle table
processing share the host's bounds. Output explains that paused funding can
coexist with old paid work, deliveries and ordinary paid knowledge use.

Comparator mode/activity traces and immutable activation ancestry are disclosed
outside experiment controls. The exact pre-intervention source boundary is
required for finite arms. Later cycle outcomes can differ between treatments.
No-op checks additionally require the recorded program digest to match.
An internal API can activate research after legacy Phase 4 paid in that same
source. Only at actual `enabled_turn`, with an adopted legacy cycle zero, an
unknown paid claim ID is legitimate: its row is withheld, attribution is marked
unavailable, and strict contrasts are blocked. Missing IDs elsewhere in finite
mode remain integrity issues. This exception never invents canonical identity.
Nonfinite malformed prefix data blocks its identity hash instead of crashing or
being silently normalized. The experiment setter and runtime remain unchanged.

## Focused evidence and limits

The `eec7e016` implementation check ran the agenda reader, existing science-receipt reader,
expansion audit and expansion comparator modules: **212 passed in 1.58 seconds**,
exit 0, in a one-thread Python environment with plugin autoload disabled. The
external stdout and receipt are retained under
`/workspace/chronicler-research-agenda-audit-evidence/focused-002`; qualification
receipt SHA-256 is
`ef4e307900779586942fa111ecacdf90b80cc8afe2dfafbd2e04d72ae43630b3`.
The receipt anchors the tested consumer/test/fixture bytes before and after.

The first exploratory reader run passed 122 cases and failed one test-only
expectation that `AsOf(0)` meant before source 0. The API defaults to end of that
turn; changing the fixture to `AsOf.before(0)` corrected the expectation and the
targeted case passed. Subsequent chronology/protocol hardening and independent
comparator review passed 139 cases and a broader 208-case reader selection.
The producer then confirmed the precise same-source legacy activation exception;
that follow-up and strict comparison blockers passed the final 212-case selection.
Both successful broader receipts remain retained. These are test outcomes, not
simulation performance data.

The committed source-0 JSON fixture is literal output from one producer
mechanical unit with two academies, two canonical propositions and two running
original trials. Later-date and adversarial copies test reader behavior only;
they do not assert physically realized scheduler trajectories. No runtime,
checkpoint continuation, native build, cohort, information efficacy or full
milestone gate is qualified by these reader tests.


## Strict activation boundary follow-up

Finite agenda contrasts now require known finite metadata, actual activation
identity and immutable cycle ancestry at the exact source `start - 1`. A known
legacy boundary followed by equal activation dates inside the measured window
cannot establish common pre-intervention agenda state or activation order. It
adds `agenda_activation_inside_comparison_window`; per-run descriptive records
remain visible, while strict contrast deltas are withheld. Enable the program in
the common parent before forking to obtain the required boundary evidence.
No registration override or activation-study waiver is inferred.

This rule also blocks coincidentally different same-source legacy adoption
rosters even when all paid claim IDs are known. The auditor still reads legitimate
same-source unknown legacy payments as unavailable attribution, rather than
corruption. Cycles opened after an established common finite boundary remain
possible treatment outcomes and need not match between arms.

After this focused policy change, all **52 comparator cases passed in 1.20
seconds**. Cases cover known/unknown paid IDs crossed with matching/differing
activation rosters, alongside existing compatible finite/paused histories and
later-cycle outcomes. The earlier 212-case full reader receipt remains anchored
to `eec7e016`; this follow-up is a separately tested comparator-only change.
