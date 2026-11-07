# Connected World public-health bounded screen

Status: DRAFT. No held world has been run. Freeze only after strict extractor
tests, the integrated-source timing/activation pilot and independent review.

Compute ceiling: 0.75 core-hours

Primary outcomes: health_world_death_rate, health_world_dpi, health_world_arrivals

This screen covers C1.2 named border guards, C2 patient supplies and maintained
water service, C2 displacement exposure through guarded T-1 X1 reads, and C4
dated evidence-informed public-health decisions. It is a bounded screen, not a
procedural or 200-seed qualification, and it does not change feature defaults.

The standalone definition and strict extractor are
`scripts/cw_health_screen.py`. The shared screen runner is unchanged. Cohorts
are six template worlds (3901–3906) and six 32-region, 10-civilization procedural
worlds (4001–4006), reserved by the lead after reconciling all recovered lane
registries. The shared timing pilots are template 5 and procedural 19. No pilot
or held execution is authorized by this draft alone: the lead schedules the
integrated native runtime and the run concurrency (one or two jobs).

All three arms use hybrid simulation only, 200 turns, grain reserves/storage,
L9 local budgets, repair projects and B3 infrastructure condition, X1 residence,
food allocation and household retail rules 2, C2 care, and quarantine closure
with both trade and migration channels. The identical base supplies the
dependencies without requiring titled trade or adding another source of funds.

| Arm | Public-health effects | Report policy | Control |
| --- | --- | --- | --- |
| PC | cost_only: identical material purchases, labour and wages; no care CFR or sanitation benefit | evidence | root |
| PS | active | shuffled prevalence among contemporaneous same-pathogen source reports | PC |
| PA | active | evidence | PS (PC also an ancestor control) |

PC retains crowding exposure, paid guard requirements, dated advice and its
closure effects. Consequently PA minus PC tests the total effect of care and
sanitation protection, including subsequent changes in population, disease and
decisions. It does not isolate the guard effect. PA minus PS tests information
placement under the same effect rules. A pathogen observed at only one source
has no shuffled contrast, which must be reported as limited signal variation.

The three primary outcomes are:

1. PA minus PC whole-world epidemic deaths per 1,000 end-of-turn person-turns.
   The numerator is every epidemic death, reported or unreported, validated
   against the lifetime mortality authority. The denominator sums all regions'
   dated completed-turn population counts.
2. PA minus PC whole-world epidemic deaths per infectious person-turn, using
   every C2 tick region's infectious-person-turn observation. Pathogen splits
   must sum to their regions and region deaths to the same mortality authority.
   This is a total effect, including pathogen mix and epidemic phase changes.
   A run with no infection has an undefined denominator, never a fabricated zero.
3. PA minus PS whole-world cross-polity epidemic arrivals, the count of
   `epidemic_arrival` events with exactly two different controlled polity actors.
   Actors must resolve to stable civilization names in the saved world and the
   arrival turn must be in the completed history. Invalid names/dates fail
   extraction. Valid uncontrolled/same-polity arrivals (zero/one actor after
   the emitter's deduplication) are outside this definition.

Every enrolled world is included regardless of whether a mechanism acts.
The runner's eligibility flag means intention-to-treat enrollment here; it is
always true after strict schema validation. Actual supplied/covered care
region-turns, maintained water region-turns, displaced region-turns and staffed
guard pair-turns are separately reported diagnostics. They never select an
effect comparison. Zero activation is an honest limitation, not a null effect.

The fixed harm panel includes the runner's food shortfall, priced-out person-
and child-turns, population, treasury, migration, wealth inequality and forest
observations where those fields exist. Added health harms are actual patient
grain consumed, cash and internal grain allocations shown separately, actual
care and guard wages, each group's ordinary income withheld and farm time
removed, gross single L9 care/public-health envelopes, famine region-turns,
refused civilian/flight/hunger migration, partner routes removed and partner
income forgone. Missing required records fail extraction; optional systems
outside this screen remain explicitly not recorded in the generic harm panel.

Strict extraction checks every completed-turn source date, care capacity T-1
dates/refusals, neutral cost-only benefit factors, T-1 residence/service exposure,
finite factor bounds, real patient grain priced to its controller owner,
separate local allocations and foreign cash, care + gross supplies + guard wages
within each single L9 envelope, exact receipt sums against lifetime counters,
named full paid guard work before next-turn capacity, and delivered/unexpired
report IDs for each policy decision. The pilot must validate the actual schemas
before any held seed is spent; synthetic tests alone are insufficient.

Run the 200-turn timing/activation pilot on the final integrated source and
extension, then freeze this definition. A 100-turn length is permitted only if
the pilot shows adequate activation and full material/guard/report lifecycle
transitions by turn 100; that decision must be made, recorded and committed
before held execution, not after seeing held outcomes. The frozen runtime
projection, including the runner's 1.5 safety margin, must fit 0.75 core-hours.
The current executable length is 200. If activation is sparse, retain the
cohort/definitions and report the sparse activation; do not search held worlds.

Reproducible commands (after the lead's integrated-build scheduling):

```sh
PYTHONPATH=src python scripts/cw_health_screen.py check --screen CW-health
PYTHONPATH=src python scripts/cw_health_screen.py run /workspace/evidence/health/pilot --screen CW-health --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src python scripts/cw_health_screen.py check --screen CW-health --metrics /workspace/evidence/health/pilot/metrics.jsonl --cohort pilot
# Freeze only after pilot/schema/review evidence is recorded and committed.
PYTHONPATH=src python scripts/cw_health_screen.py run /workspace/evidence/health/held --screen CW-health --cohort held --jobs 1 --pilot /workspace/evidence/health/pilot/metrics.jsonl --keep-first
PYTHONPATH=src python scripts/cw_health_screen.py report /workspace/evidence/health/held/metrics.jsonl --screen CW-health
```

Retain compact metrics, source/extension/runner/module/registry identities,
commands, elapsed time, pilot projections and all failures, adverse outcomes,
nulls and unrun checks. Full bundles remain outside the repository. No paid
narration, deployment, restricted full gate or default promotion is included.
