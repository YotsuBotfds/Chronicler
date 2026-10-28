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
The snapshot's `independent_groups` is this capped accounting count, not proof
of independent world experimental units. Harvest years have Markov
persistence and every trial shares the canonical physical evaluator. The
paired relative-output measurement cancels common physical yield scale in
this narrow kernel; broader world inference needs its own dependence design.

Evidence applies only in the claimed grain, soil/water quarter-bands,
season and climate phase, with sedentary farming and existing local practice.
It does not imply a universal technique benefit. On every sixth turn relative
to the persisted cohort start an
applicable academy can pay one treasury unit for a fixed adoption allowance,
split by confidence. The total extra rate is at most 0.01 per region.
`techniques._update_practice` applies it inside its existing logistic growth,
prerequisite, suitability, workforce-shortfall and disruption gates. At zero
practice it cannot invent a technique, and above the suitability cap it
cannot turn decay into growth. No belief is read by the yield functions.

The calendar correction was checked before world qualification with cohorts
starting at turns 0, 3, 6 and 9. Each retained paid adoption opportunities and
serialized continuation equality. The 36 focused checks passed under Python
3.13.5 with the installed native extension; this is mechanical verification,
not a population or causal-benefit gate.

Both experiment and effort payments use exact projected treasury and `keep`
mutations. Same-turn guards prevent duplicate debits. Effort allocation rows
carry the whole seat payment on the first row and zero on its other rows;
their sum matches the actual paid expense.

## Controls and historical records

The persisted `withhold_information` control preserves proposals, funded
testing and effort budgets while removing outcome receipts and policy use.
`uninformative_tests` preserves physical diagnostics and costs but centers
both sham readings on the physical comparator with independent measurement
noise. These observations use the ordinary posterior; realized beliefs can
differ without reliable treatment discrimination. The prospective amendment
and frozen measurement-only seed check distinguish this from withholding.
`transmission_enabled=False` retains own evidence
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

## Dated provenance and narration

The ordinary event timeline records `scientific_claim_proposed`,
`scientific_trial_funded`, `scientific_trial_completed`,
`scientific_trial_cancelled`, `scientific_trial_failed`,
`scientific_evidence_received` and `scientific_adoption_allocated`.
Claim/trial integer IDs remain cohort-local domain identities; ordinary event
IDs remain emission-turn/type/counter identities. A funding cites its proposal
and, for replication, the original resolved trial. Resolution cites funding;
a genuine receipt cites resolution and the sender's receipt where applicable.
Paid allocation cites the received informative records actually used, or
the proposal when no informative evidence has arrived. Withholding produces
completed records explicitly marked withheld and no evidence-receipt event.
Failed/cancelled work never fabricates a receipt.

The first paid allocation per academy is reported. A later event requires
a changed recipe set or at least five percentage points of changed share
since the last report. This threshold only limits event reporting: all actual
payments and allocations still occur and appear in snapshots. A bounded map
retains at most twenty reported splits; it is not a policy input. Ordinary
proposal/funding/completion/receipt/allocation events are routine narrator
records and share existing repeat-folding and prompt budgets.

All events carry their actual simulated turn S and belong to observation
snapshot S+1 with `source_turn=S`. Propositions add `proposed_turn` and
`event_id`; resolved trials include `funded_event_id` and their resolved
`event_id`; belief rows include the last informative receipt's event ID.
An allocation row carries an event ID only when that payment was reported.
After a dormant host resumes, an observation's actual `resolved_turn`, rather
than its planned completion, starts its message lifetime. Unknown or future
actual resolution dates cannot influence beliefs.

Narration reads at most one focused science line from the dated snapshot.
It names recorded local confidence, actual receipt dates and a paid allowance
share; it does not translate confidence into verified physical truth or
certified independent populations. Future/undated propositions and future
receipts are ignored, with no fallback to the final world.

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

The prospectively frozen measurement-only sham check (seeds 1000..1999,
retained physical inputs) observed 727 irrigation and 319 masonry supports
under informative measurements, versus 329 and 319 under sham measurements.
Sham confidence differed between the claims in 458 seeds. These figures
check the implemented measurement rule; they do not qualify independent
world outcomes. An explicit policy test changes the hidden physical grain
coefficient while keeping received observations and eligibility fixed:
confidence and paid allocation change only after new evidence arrives.

At runtime commit `35c58455`, the focused offline-guarded science, technique
and scholarship suites passed 130 tests with three expected skips. The
guard blocked native imports and observed no network or child-process
attempts. A separate feature-off probe compared frozen `8f180a03` against
`35c58455`: seeds 42 and 43, eight regions/four civilizations, sixteen
complete turns each, with scholarship and techniques enabled. All complete
serialized world states, empty-narrator chronicle text and Python RNG states
matched byte for byte, without stripping any fields. Combined output SHA-256:
`3cfef52071b2d4f4321306df896102a40b402744d30c91215a776eca8854bb27`.
The probe and both output arms are retained in the review workspace as
`/tmp/scientific-off-identity.py`, `/tmp/scientific-off-baseline.json` and
`/tmp/scientific-off-final.json`; probe SHA-256:
`e891aaa7d11d45ded2d7541ec1d9e0a8133365bd1d561f35118402faf7babfeb`.
Both arms used the shared interpreter with `PYTHONPATH=<checkout>/src` and
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`, executing that exact probe.
