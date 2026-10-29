# Causal treatment delivery: next discriminator

Read-only source diagnosis, 2026-10-29. This supplements the existing
`causal-template-diagnostic-2026-10-28.md`; no original report, threshold,
sample, world, parameter or gate was changed or rescored. Historical numeric
results remain scoped to sources cb9/5b5252 and native 43243cb0. Source facts
below were checked against d028, whose crate tree is a4703ef4.

## Kin roots do not act on every migration reason

`Mobility::drop_relationship_roots` removes marriage and home-bond roots.
Those roots subtract from voluntary pulls inside destination choice; they do
not subtract from distress, need, persecution or memory migration utility.
Dependants, travelling merchants, displaced agents, absent internal neighbours
and inadmissible destinations can also prevent a voluntary decision. Holding
community membership alone does not prove delivery of this treatment.

This permits an exact structural negative control: a fixed predecision state
with no admissible voluntary pull must have identical immediate decisions and
random-stream consumption in plain and kin-root arms. Give the same state an
admissible wage/frontier pull to test delivery separately. Preserve the existing
20-tick endpoint and report this as a mechanism diagnostic, not a new gate.

There is a useful scale check, not a prediction of the full endpoint. With
unchanged destination, both action gates open, unchanged other logits and a
fixed predecision state, relationship roots can change the migration logit by
at most 0.06 before household damping (0.02 marriage plus 0.04 capped home bonds).
At temperature 0.3 the ideal continuous-Gumbel model's largest possible relative
probability reduction for such a shift is `1 - exp(-0.06 / 0.3)`, about 18.1%.
Two home-bond units without marriage give at most about 12.5%; marriage alone
gives about 6.4%. Equal positive spouse/personal wealth applies a further factor
`0.88 / 2**1.20`, so even the full 0.06 shift becomes about 0.023, corresponding
to at most about 7.4% under those assumptions. These are conditional analytical
scenarios, not finite-precision bounds on the implemented RNG or on migration
counts. Destination/gate changes, household following and later feedback break
those assumptions. They motivate measuring those channels rather than raising
coefficients to hit a cohort-wide 15% target.

## A fork-low need can be restored before the first treated decision

The sidecar cohort is selected at fork T. The next native tick updates wealth,
settlement assignment, need decay/restoration, relationship drift and merchant
mobility before decision evaluation. A low recorded need therefore does not
guarantee a nonzero corresponding need modifier at the first treated decision.

For a rural, neutral-boldness agent at peace in an uncontested, healthy region
with food sufficiency 1 and no new shock, recorded safety 0.29 becomes:

    (0.29 - 0.04) + (0.025 + 0.032 + 0.028 + 0.022) * 0.75 = 0.33025

That already exceeds the 0.30 behavioral threshold. The original intention-to-
treat cohort definition remains valid, but actual channel exposure can wash out
before a decision. The joint `needs` arm also removes all need terms and the
autonomy loyalty factor; it is not a selective safety-only intervention.

## What can and cannot be recovered without new worlds

Retained needs sidecars contain need levels, region, occupation, satisfaction
and traits; they omit age, displacement cooldown, trip phase and wealth. The
relationship table contains bonds/sentiments. These files cannot alone certify
predecision mobility eligibility, household damping or actual treatment dose.
Do not infer those missing quantities from membership, event labels or prose.

The existing native `get_migration_driver_stats` is a bounded read-only starting
point: it reports evaluated/decided counts, pre-root gates, chosen-target open
pulls, voluntary age bands and household followers. Production Python does not
currently persist it. Its positive migration-budget shares explicitly omit
dampers, and `gate - open` also includes target-choice/hysteresis effects, so
neither is an exact counterfactual root dose.

A prospective tiny diagnostic should retain stable agent ID and source tick,
post-update need modifiers, alive/idle/cooldown/age eligibility, gross/net pull,
chosen target, household factor, four gated action logits and final decider/
follower role. Fixed-state plain/ablated logit comparison before any draws can
separate absent delivery, within-state probability shifts, gate/target changes
and later catch-up. The diagnostic must add no RNG draws or persistent runtime
state and must not replace the registered full cohort or choose favorable
exposures after outcomes. No such diagnostic or new simulation was run here.

The separately isolated near-zero household-wealth correction addresses a
source counterexample, not an explanation of these historical ratios. See
`../integration/household-migration-wealth-floor.md`.
