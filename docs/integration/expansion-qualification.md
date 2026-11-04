# Expansion qualification plan

Status: development plan for the default-off health/care, harvest-forecast and
ritual-gathering slices. This document does not report completed feature gates
or promote an experiment. The reference source before these slices is
`5b5252ed`; each actual test/run needs its own immutable source identity.

## Entry-point and persistence contract

`tests/test_expansion_feature_wiring.py` exercises the real parser, configuration,
manifest, world/checkpoint and transport paths. Native construction is replaced
at its boundary in configuration tests; this is not native execution evidence.

| Request | Fresh world | Loaded world |
| --- | --- | --- |
| Omitted (`None`) | All three experiments stay off | Preserve the saved state, dormant when its runtime/dependencies are unavailable |
| Explicit enable | Create state after checking the requested mode/dependencies | Preserve existing state or create it, but reject an invalid requested configuration |
| Explicit disable | Stay off | Clear the state, even if the requested mode would not support enabling it |

Health/care and gatherings require hybrid mode for explicit opt-in. Forecasts
require an agent-backed goods economy, grain reserves and the contact ledger.
Mode validation must precede native construction, using the requested mode;
fresh worlds have not necessarily had `world.agent_mode` assigned yet. A saved
hybrid experiment resumed with agents off must actually be dormant rather than
reading a stale saved mode.

The requested tri-state belongs in simulation manifests. Effective enabled
state belongs in checkpoint headers. An exact resume adopts saved switches
when omitted and rejects an explicitly conflicting switch. Batch Lab validates
booleans/null without accepting `1`, `0` or truthy strings. Its worker forwards
CLI defaults and explicit overrides. Single, batch, live, subset/full gate and
determinism paths must carry the same intent; existing ablation forks inherit
it through the saved run configuration.

Every new snapshot field is optional, omitted while inactive and named in the
shared transport contract. Static, streamed and reconnect histories retain the
same fields. Older rows remain unknown; final-world state cannot backfill them.
Snapshots labelled T describe completed source turn T-1. Readers and summaries
must not initialise state, consume a queue or repeat stale receipts.

## Controlled mechanisms before population gates

| Slice | Fixed exposure/control | Required result and failure probes |
| --- | --- | --- |
| Health/care | Inject the same patient cohort, disable new injuries, compare care with no care | Care costs productive time and increases recovery progress. One caregiver cannot supply multiple full allocations. Dead, absent, enlisted, travelling, urban/craft and impaired workers cannot provide free eligible rural work/care. Consumption still counts living people. |
| Forecasts | Same registered assessments under normal delivery, withheld delivery and deterministic within-cycle shuffle | Delivery precedes target changes and purchases. Withheld reports cannot alter targets. Actual treasury/surplus/routes bound purchases; targets do not compound. Record false-alarm costs and spoilage. |
| Gatherings | Identical eligible attendance/costs with contact and bonds both on, each off, or both off | Cancellation spends nothing and adds no exposure/bonds. Costs persist in every held-gathering arm. Only actual present arrivals generate cross-region gathering contact; existing protected bonds are not displaced. |

Freeze thresholds, noise, work fractions, cadence and eligibility before the
held-out cohort. Controlled fixtures establish arithmetic and the intended
mechanism, not natural prevalence, historical realism or population benefit.
Do not select the cohort using a treatment-induced outcome.

Forecast scoring needs a precise interpretation: realized production divided
by food demand can itself change through preparedness's effects on survival,
labor and population. Its Brier score is a score of realized adequacy under
that policy, not proof of prediction of a treatment-invariant physical hazard.
Report climate-shock vector equality separately. Existing granary procurement
while a warning is active is an observed receipt; causal additional procurement
requires a paired control.

For health, keep lost work at the region where work was performed and current
episodes at the surviving person's current region. Censor recovery at death.
For gatherings, distinguish attempted relationship updates from accepted native
updates unless the FFI supplies a success count. Copied/decayed contact from an
earlier turn is not another physical gathering.

## Exactness and boundary probes

- Feature-off: compare no flags and three explicit disables with the reference
  across off/hybrid, template/procedural and dense-agent workloads. Compare
  both Python-only changes using an identified compatible binary and old/new
  native binaries with the new native inputs disabled. Preserve event ordering,
  random streams, numeric bits and output schemas.
- Enabled resume: save just before and after health preparation/episode progress,
  report publication/delivery/expiry, and a due/cancelled gathering. Compare all
  emitted files against uninterrupted runs, not merely the final population.
  Exact checkpoints occur at supported turn boundaries; derived inputs must be
  rebuildable there and cannot retain stale slots after restore.
- Multi-turn reset: no work deduction, care assignment, purchase receipt,
  gathering inflow or relationship attempt may leak into an unrelated turn.
  Repeat calls to receipt readers must be read-only and copies must be isolated.
- Determinism: mix fractional care and impairment in the same region, reorder
  input rows, change process hash seed and vary native thread count. Unordered
  map traversal cannot choose floating-point accumulation order.
- Lifecycle: death and slot reuse, occupation switch, enlistment, migration,
  spouse departure, conquest, city loss, faith-slot recycling, report expiry
  and missing observations. A missing value is not a zero or a false report.
- Accounting: productive + impaired + care time is bounded by available time;
  each corresponding income deduction occurs once. Forecast procurement uses
  the existing reserve ledger. Gathering consumption has its own food/expense
  receipt after the reserve-ledger interval and excludes committed merchant cargo.

## Gate ladder and execution budget

Run focused tests and the bounded offline lane first. Keep the existing
110-second per-chunk limit; add/split chunks rather than extending it. Then
build the native source once into an isolated environment, verify the real
compiled simulator classes, and retain source, toolchain, wheel and installed
extension hashes. Do not replace a binary during an active run.

Qualification proceeds from enabled small-world probes and exact continuation,
to development subsets, to frozen held-out template/procedural cohorts. Each
feature needs its own evidence before a combined all-on run can be interpreted;
a successful combined run cannot identify which feature produced a benefit.
Full regression gates and the controlled causal arms answer different questions.

The existing gate entrypoints, once the feature forwarding is integrated, are:

```sh
# Baseline and candidate use distinct fresh output roots and frozen sources.
python scripts/m53b_run_validation.py --profile subset --parallel 1 \
    --output-root OUTPUT_ROOT --health-care
python scripts/m53b_run_validation.py --profile subset --parallel 1 \
    --output-root OUTPUT_ROOT --harvest-forecasts --grain-reserves --contact-ledger
python scripts/m53b_run_validation.py --profile subset --parallel 1 \
    --output-root OUTPUT_ROOT --ritual-gatherings

# Full profiles retain their documented seed counts/horizons.
python scripts/m53b_run_validation.py --profile full --parallel 3 \
    --output-root OUTPUT_ROOT FEATURE_FLAGS
python scripts/m53b_run_validation.py --profile full --worldgen procedural \
    --parallel 3 --output-root OUTPUT_ROOT FEATURE_FLAGS
```

`OUTPUT_ROOT` and `FEATURE_FLAGS` are placeholders, not literal paths/flags.
Template full is 200 seeds × 500 turns; procedural full is 100 × 300.
The default existing need/kin ablation arms must be recorded as such; they do
not replace the new systems' causal controls. Compare reports with different
feature configurations only as explicitly exploratory comparisons. Keep strict
per-profile regression adjudication and unchanged oracle thresholds.

Historical cost guidance, **not a fresh estimate for this source**:
[procedural gates](procedural-gates.md) measured a procedural full at roughly
45 minutes on three shared workers, 2.5 GB peak validation memory and about
5 GB unpruned output; its subset was about eight minutes on two workers.
[Existing ablations](ablation-oracles.md) document another 23–28 minutes for
template full and about 45 minutes for procedural full's two arms. New systems,
the turn-index optimization and host contention can change those costs.

On this four-CPU-equivalent host, coordinate one optimized native build and
heavy benchmark/gate jobs through the lead. Many agents can inspect/write code
concurrently; that does not create CPU or memory capacity. Retain immutable run
receipts, failures and inconclusive results outside Git. Do not reduce seeds,
horizons, failed observations or control arms to obtain a passing claim.

Measure default and dense-agent CPU/wall time, memory, checkpoint size/time,
output bytes and event volume. The roadmap's proposed two-percent whole-turn
overhead target at a declared pilot cap is an acceptance proposal, not a measured
result. A missed budget calls for profiling or an explicit scope decision.
