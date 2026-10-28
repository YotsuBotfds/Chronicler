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
the recorded pre-intervention boundary at source `start - 1`; unknown/missing
lineage blocks comparison. Later cycle outcomes are not required to match.
No-op labels also require compatible recorded research history. Derived mode
must never enter `controls_for_state` or its control setter.

Verification uses the producer's literal source-0 mechanical summary plus small
adversarial reader fixtures: unsupported metadata, future actual dates, planned
future deadlines, legacy unknowns, pauses, immutable membership, capacity
conservation, late resolution coverage, actual allocation identity and contrast
lineage. No cohort simulation or efficacy qualification is part of this task.
