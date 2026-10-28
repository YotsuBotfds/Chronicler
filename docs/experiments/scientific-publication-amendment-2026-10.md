# Prospective funded-context publication pilot

This amendment is recorded after the intact first natural execution cohort
and before implementing/testing this separate rule. The original simulation
source `d051d7c0`, registered 42–43/60-turn cohort, all ten outputs and empty
exposures remain unchanged. Its manifest SHA-256 is
`b65f193077e290f324a0ee92e191b46530032eaaebf6b525efcfbdce87d49ab5`.
That cohort recorded no cancelled trials; this amendment is motivated by a
source-level timing inconsistency, not fitted to improve its outcomes.

## Question and explicit rule

`evaluate_trial` already computes and stores the physical comparator and
treatment outputs and their full local input/context record at funding.
The next-turn completion adds measurement noise and publishes that retained
observation. The v1 completion rule nevertheless cancels publication when
the *current* context no longer matches, even when the academy and recorded
funded measurement survive. Remote results are already archived when a
recipient's present context differs, with current applicability checked
separately by policy.

Keep `current-context-v1` as the default, including old state imports. Add a
persisted, explicit source-owned `publication_rule="funded-context-v2"` option.
Only the nonlegacy rule is serialized as an additive field. Experiment
receipts must record the full resolved rule; switching it is an intervention
with the same existing parent-checkpoint/lineage requirements. It does not
enable scholarship, techniques or science, replace trial records or move
the world clock.

Under v2, a still-living academy with publication access can publish its
valid recorded funded-context measurement even after the current season,
soil/water band, grain access, technique practice or climate phase changes.
No fresh physical evaluation or hidden recipe-truth label replaces the
recorded measurement. Academy loss or absence of living regional access
still yields a retained paid cancellation. Missing/invalid funded measurement
data yields a retained paid failure. Null physical output remains a completed
uninformative result. No fee is refunded and no outcome is rerolled.

Current-context eligibility still gates policy confidence and paid adoption.
A valid archived result need not be applicable now. Actual publication time
continues to anchor receipt dates and message expiry. Withholding creates no
receipt; sham observations retain their registered comparator-centered noise
rule; local-only delivery retains its existing channel control. Existing
trial/effort costs, cadence, caps and physical functions stay fixed.

## Fixed mechanical checks

Before any new world cohort, test all four season-ending funding dates
2, 5, 8 and 11. V1 retains cancellation; v2 archives the funded-context result
without applying it in the new season. Restoring the matching original
context can use the same archived receipt, without a replacement measurement.
Also check independent soil, water, climate, grain/practice and access-loss
changes; funded-data corruption; null output; withheld/sham/local-only
controls; exact projected expenses and resumed checkpoints across publication.
Physical input/output diagnostics and all existing RNG states must remain
unchanged by publication. Version defaults and omitted legacy serialization
must be explicit tests, with the ordinary feature-off path still untouched.

The replication scheduler depends on original funding time/existence, not
its result. A separate observer-only correction will therefore cite the
original funding event as the replication-funding cause. It does not change
scheduling or the publication rule.

No new natural cohort, horizon extension, significance threshold, efficacy
claim or default activation is assigned here. A future world comparison must
register its complete population, horizon, exposure/censoring and independent
units before running; it must retain failed/cancelled/empty exposures.
