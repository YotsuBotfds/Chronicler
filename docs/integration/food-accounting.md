# Recorded food consumption and relief

`TurnSnapshot.food_accounting` is an additive **schema_version1** observation
inside existing bundle6 history. Older bundles/native outputs stay unknown;
there is no mass-consumption fallback from stock changes or civilization totals.
This is observation, not a new food-allocation economy.

Each record stamps source tick N and completed snapshot N+1. Region IDs are
world-array indices; model population and actual alive native counts are copied
at Phase2 entry, before subsequent deaths, births, migration and conquest.

## Two different calculations

- The native kernel works in **model food goods**, using its configured per
  capita demand (default0.5 per alive native agent). It consumes regional food
  proportionally to available goods. Pre-consumption sufficiency is stock /
  max(demand,0.1), clamped0–2. It is not consumed quantity, calories, a meal count
  or proof of household purchasing access. Native wealth does not gate this
  regional drawdown; household coping remains a separate roadmap milestone.
- Python public granaries run **after** that native drawdown. Their release
  lowers reserve stock and raises the sufficiency signal; the model treats it
  as directly eaten. It is separately labeled, never inserted into native
  consumption or counted twice as a native import. Opening/release/spoilage/
  abandonment/captured custody/remaining reserve retain their own balance.
- Aggregate mode does not run this native goods kernel. Its yield-based food
  crisis checks do not establish available/received/consumed goods totals;
  the native ledger/demand remain null rather than fabricated zeroes.

Native ledger quantities: opening, produced, transport_net, craft_input,
clamp_correction, pre_consumption, consumed, storage_loss, cap_overflow, closing,
demand and pre-relief sufficiency. In hybrid mode transport_net is imports plus
returns minus departures; in other backed modes it is abstract imports minus
exports. These are different models. Purchase/dispatch/arrival receipts remain
in the existing Transactions/Granaries inspectors; a purchase is not another
quantity to add to delivery or consumption.

Native balance: opening + produced + transport_net − craft_input +
clamp_correction − consumed − storage_loss − cap_overflow = closing.
Residual/tolerance disclose f32 component arithmetic; no stock operation was
reordered to manufacture exact equality. A positive clamp correction is an
artificial source diagnosing an overdraw, not food production or a physical sink.

Public Phase2 balance: opening − released − spoiled − abandoned = after_open.
Capture changes custody, not total goods. Abandoned public grain reaches the
market after native consumption, so it is not retrospectively a native meal.
Later Phase10 procurement records its actual initial/remaining budget and spent
coins. A zero budget is a funding boundary, not by itself proof of a region's
shortage cause; target/supply/routes must also be inspected. Pending paid public
cargo remains distinct from market/reserve stocks and becomes releasable only
after its recorded arrival boundary. Private mobility's buffered deliveries are
read/decayed once in the following Phase2, not before travel.

## Verification and limits

- Controlled real-native empty/short/abundant inputs, public release, real
  merchant arrival/drain, zero merchant wealth and observer neutrality:7 tests.
  Zero merchant wealth tests regional drawdown, not universal household access.
- Actual8-turn hybrid run, checkpoint4→8, complete food histories and final
  world match. All regional balances are within recorded tolerances.
- Baseline/current8-turn pairs at seed42 in off/hybrid/shadow/demographics-only:
  decisions, RNG traces, all24 backed-mode native states, complete world and39
  existing artifacts match after removing only new food_accounting observations
  and fixing generated timestamp. Grain reserves/receipts are enabled only in
  supported backed modes. Exported bytes intentionally change for the new field.
- Combined focused Python/native/compatibility/transport checks:502 passed,
  one existing skip. New bounded offline chunk9 passed with no native imports,
  sockets or child processes. Existing immutable source pins remain unchanged;
  the exact reviewed food-layer inverse is source evidence, not runtime parity.
- Full Rust:1,181 passed, two existing ignored. Viewer broad pass1,115/102 files,
  followed by4 focused checks for small nonzero balances; lint/build pass.
- Actual production Chromium desktop and390px: real new/legacy files, selected
  turns1/8/6, region selection, precise fields/unknowns and keyboard table scroll.
  A real8-turn example with deliberately constructed initial stocks/cash shows
  native1.5275 vs public2.4725 in its first region, with procurement0/0/0.
  This is not a naturally generated balance claim or a calibrated policy result.

Evidence: `/workspace/shared/chronicler-crisis/m1-food`, `m1-native`, `m1-viewer`.
The source/native build, test receipts, actual output/checkpoints, retained failed
fixture/harness attempts and restored-off-mode controls are kept there. Matching
baseline and M1 native environments are separate and never replaced under tests.
Full combined CI and the program recovery index are recorded at each source
checkpoint in the [roadmap](crisis-recovery-roadmap.md); M3+ is not complete.
