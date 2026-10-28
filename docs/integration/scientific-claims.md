# Contextual scientific claims pilot

This experimental system defaults off. `--scientific-claims` requires
`--scholarship --techniques`; saved state stays dormant without both hosts.
The prospective contract is
[`docs/experiments/scientific-claims-2026-10.md`](../experiments/scientific-claims-2026-10.md),
committed before implementation outcome runs. Its parameters were not tuned
to population or historical outcomes.

## Production path and physical boundary

The existing scholarship Phase 10 updates academies first, then calls
`tick_scientific_claims`. The first eligible registered academy proposes two
contextual grain-benefit claims, for irrigation and masonry. Each costs two
actual treasury units to test, with a twenty-unit treasury floor. A funded
trial is retained even if it fails or its academy/context disappears before
measurement. There are at most two original trials and two replications in
this slice. A different academy must receive the proposal and wait at least
twelve turns to replicate; that choice does not inspect the original result.

The controlled evaluator uses the current physical harvest calculation and
the existing allocated-production kernel on a fixed four-worker grain plot.
It copies only the tested region, a region-reference list and its sparse
local technique rows. It never forks a full world, allocates real workers,
depletes reserves, changes an existing RNG stream or creates harvest goods.
The treasury payment buys an experimental service; trial outputs are
measurements, not a second production ledger. Tests compare complete world
serialization, original world/cache identities, reserve-bearing region
fields and Python/NumPy RNG states around the evaluator.

Noisy measurements, rather than a recipe-validity label, determine support.
In noiseless fixtures irrigation has its canonical 5% grain-yield effect;
masonry has zero grain-yield effect while retaining all its normal
construction uses. A zero-yield plot supplies no evidence.

## Institutional information and paid adoption

Proposals and results travel only across adjacent registered academy
regions, one hop per turn, at most three hops, with a six-turn publication
lifetime. Delivery never creates a trial. Confidence reads only received
informative observations. Source signatures deduplicate aliases; a shared
climate-cluster/year/protocol group contributes at most one unit of evidence.
Distinct dependent observations average within that unit. Records include
the source signature, method, environmental block, parent trial and dates.

Evidence applies only in the claimed grain, soil/water quarter-bands,
season and climate phase, with sedentary farming and existing local practice.
It does not imply a universal technique benefit. On every sixth turn an
applicable academy can pay one treasury unit for a fixed adoption allowance,
split by confidence. The total extra rate is at most 0.01 per region.
`techniques._update_practice` applies it inside its existing logistic growth,
prerequisite, suitability, workforce-shortfall and disruption gates. At zero
practice it cannot invent a technique, and above the suitability cap it
cannot turn decay into growth. No belief is read by the yield functions.

Both experiment and effort payments use exact projected treasury and `keep`
mutations. Same-turn guards prevent duplicate debits. Effort allocation rows
carry the whole seat payment on the first row and zero on its other rows;
their sum matches the actual paid expense.

## Controls and historical records

The persisted `withhold_information` control preserves proposals, funded
testing and effort budgets while removing outcome receipts and policy use.
`uninformative_tests` preserves physical diagnostics and costs but gives
observations zero weight. `transmission_enabled=False` retains own evidence
and blocks remote protocols/results. A fixed-eligibility fixture checks that
withheld and uninformative arms have the same trial schedule and treasury
expenses as the informed arm. Geographic or later physical/treasury changes
can alter spending in world runs; those arms are not automatically matched.

`snapshot_summary` requires `last_tick_turn == world.turn - 1`; stale or
future state returns no historical summary. It records `source_turn`,
cumulative counts/expenses, two immutable contextual proposition summaries,
at most forty copied current belief rows with institutional names, confidence,
dependence-group counts and last evidence dates, and current paid allocations.
Only trials resolved in that completed turn appear in `trials_resolved`;
the snapshot does not repeat every lifetime trial record each turn.

## Verification and limits

Focused mechanical tests cover the physical evaluator, all controls,
transmission dates/topology, failed/cancelled/null trials, dependency/source
deduplication, exact projected expenses, technique gates, complete-turn hook
execution and exact checkpoint continuation while paid trials/messages are
pending. The integration fixture holds an eligible context long enough for
the twelve-turn replication and adoption cadence. Natural environmental
change can instead remove eligibility; no universal transfer is substituted.

State ceilings remain twenty academy IDs, twenty claim slots and forty trial
slots, with bounded receipts/messages and no per-agent belief columns. This
first pilot uses two claim slots and four trials. A cohort performs at most
eight physical evaluations, each copying one region and its sparse local
practice. Historical belief work is bounded by the cohort, not population.
No measured speedup or world-outcome benefit is asserted here. Scientific
qualification, parameter fitting, broader sectors, new academies/cohorts and
default activation require separately preregistered paired world runs.
