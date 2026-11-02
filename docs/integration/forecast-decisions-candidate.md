# Delayed reports and recorded procurement decisions

M6 is **partially covered**. Delayed information changes an actual procurement
decision in a constructed development case, with exact continuation and a
working inspector. The required harmful misleading-information case has not
been demonstrated. The integrated crisis suite and independent evaluation are
still ahead; no policy or scientific promotion follows from these examples.

Use the existing harvest forecasts with grain reserves and contact ledger.
`--harvest-report-delay N` adds0–12 turns to reports issued subsequently, default
zero. It preserves reports already in transit and their original expiry/target
window. Existing supported forecast modes remain supported; the physical native
controls below ran hybrid. Saved settings persist while dormant with agents off;
exact resume refuses a changed delay. Forecasts remain off by default.

## Information and accounting contract

The forecaster still uses the previous/current measured production observations
and known seasonality. At issue it freezes a version1 estimator-construction
record: actual origin region, reported issuer, ordered observation dates/ratios,
season factor, threshold, exact existing noise draw, policy and original claim.
Shuffle retains the actual estimate origin separately from the reported issuer.
Legacy construction remains unknown. This construction record is separate from
what the receiving decision-maker knows and is never added to the decision inputs.

At the real Phase10 purchase boundary, a version1
`harvest_forecasts.procurement_decisions` child freezes sourceN/availabilityN+1,
mode and units, then-known eligible **received** reports with original claim and
issue/planned/actual delivery/expiry dates, granary keeper and current controller,
known stock, Phase2 demand, pending paid inbound and actual opening treasury budget.
The target before preparedness, requested target and storage-feasible target stay
separate. A reduction requires the actual same-turn storage receipt and live cap;
the observer does not weaken the cap or the forecast to reconcile its record.

After procurement, the same capture records actual new purchase receipts, newly
committed paid cargo and coins paid. Grain amounts are net model food-goods units,
not calories or a household meal. Paid cargo is not available reserve stock and
is not paid again on arrival. Failed attempts are unrecorded, not zero. Purchases
made during a warning are not automatically extra purchases caused by that warning.
Physical stock/offer constraints continue to use the existing procurement model;
this is not a complete model of political knowledge or market search.

The existing Harvest inspector shows actor-known inputs and dates, requested
versus feasible targets and actual costs/flows. Estimator construction is a
separately labeled expansion; pending reports never appear as received decision
inputs. Selected snapshotT uses sourceT−1. Old/malformed/stale/future detail remains
unknown while the existing report view stays usable. Named scrollers work with
keyboard controls at390px, and event/region navigation preserves the selected turn.

## Actual evidence and limits

The original declared fixed-seed finite four-region/two-ruler control generated
and delivered reports but bought no warning-period grain: its markets did not
admit the existing four-turn-surplus procurement gate. That null is retained.
A separately declared development fixture, designed **after** that null, adds
finite grain150+salt150 and fertile/watered source markets at the same seed42.
It is a positive mechanism control, not a held-out replication or seed sweep.

Normal delivery0 bought50.719 net grain for six coins while eligible warning
reports were present; delay3/12 and withhold bought none under warnings. Timely
and delayed delivery dates differ6 versus9; delay12 arrives beyond original
expiry and is never used. Shuffled probabilities genuinely differ but its paid
purchase total matches normal. Food sufficiencies through turn11 match in these
controls: no avoided hunger, wasted preparation or food-harm claim is supported.
Ordinary purchases can occur without a warning; the retained first assertion
mistakenly assumed otherwise and was corrected to the actual intended boundary.

Four actual native tests validate those controls, current market-surplus and
private-commitment eligibility, actual storage caps and an eight-turn exact
continuation from a pending-report checkpoint. Captured decisions, world, native
state and Python RNG match after resume. The matching unchanged native Rust tree
is `543df3bb74804c71cf16046a7cac8f43ea9bfe45`; compiled extension SHA-256
`d15cb4c3f7e71778ce9127688486aba85a01459c344dcbb3dfd8e3331e824b8d`.
M6 changes no Rust source and reuses that verified build without replacing it.

A14-turn parent/current normal-delay0 pair retains initial native identity,
world, prior artifacts, actions, per-turn native-state hashes, Python RNG and
primitive traces after removing only the new construction/decision observations.
Complete unnormalized outputs are retained; raw native bytes were hashed rather
than stored in that parity artifact. Two serializer failures after completed
baseline runs remain recorded. This proves a bounded observer check, not efficacy.

Focused source/compatibility checks passed539 and61 subtests, independently of
runtime evidence. Guarded contracts/metadata passed240 without native imports or
blocked IO. The viewer passed1,137 broad tests before the final metadata-corruption
guard; seven focused final checks, lint/build and actual desktop/390px journeys
pass. Real normal/delayed/legacy/shuffle bundles agree with source targets, dates,
budgets and payments. A final valid-producer browser check also passed after the
guard. Broader combined CI is recorded in the roadmap, not inferred here.

## Reproduce and inspect

With locked dependencies and matching native source:

```bash
PYTHONHASHSEED=0 python -m chronicler.main --seed 42 --turns 14 --agents hybrid \
  --grain-reserves --contact-ledger --harvest-forecasts --harvest-report-delay 3 \
  --simulate-only --checkpoint-every 3 --output output/reports/chronicle.md \
  --state output/reports/state.json
cd viewer
npm run dev
```

An ordinary generated world need not admit warning procurement. The explicitly
constructed working examples and saved checkpoints are in
`/workspace/shared/chronicler-crisis/m6-forecast/examples/{delay-0,delay-3,delay-12}`;
`shuffle` uses the existing controlled corruption policy, and `legacy` was newly
generated by the real older producer. Their manifests preserve those distinctions.
Load the bundle, open Granaries/Harvest forecasts, and compare snapshots6/7/8/10/13.
These outputs, original nulls, source identities, exact commands and failures
remain outside Git for owner-only backup.
