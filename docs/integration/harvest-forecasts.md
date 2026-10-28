# Delayed harvest assessments

`--harvest-forecasts` is a default-off production experiment. An explicit
request needs `--grain-reserves`, `--contact-ledger` and an agent-backed goods
economy. It never enables those prerequisites automatically. An omitted flag
preserves a saved setting, dormant while a prerequisite is inactive. The
rule was registered before implementation in
[the pre-registration](harvest-forecasts-preregistration.md); no parameters
were fitted to the development fixture or its outcomes.

## Observation, delivery and action

At each living realm's owned capital, assessors use up to six recent measured
local food-production/demand ratios. The public grain seasonal multiplier
normalizes those observations. At summer close (step 5 of the existing
12-turn year), at least three observations support a noisy estimate of winter
production adequacy. Current and past measurements and public seasonal timing
are its only inputs. It never reads a future climate phase, harvest shock,
disaster roll, market inventory or agent decision. The grain-only seasonal
model is intentionally imperfect for fish and other foods.

Each report has a stable ID, source and recipient region, frozen recipient
ruler/name, issue/due/expiry dates, probability, observation-completeness
confidence and a predicted production/demand ratio. Confidence is not a second
probability estimate. A local report arrives one turn later; a report over a
positive contact edge arrives two turns later. Issue uses the prior completed
turn's contact ledger, before this turn's contact flush; removing contact
after issue does not rewrite its scheduled arrival. A recipient holds at most
one active report. Selection favors confidence, then shorter delay, then
source index, rather than the most alarming prediction.

Delivery can never occur on the issue turn. The recipient's ruler changing
before expiry cancels its report. Reports expire after step 11; three winter
production measurements (steps 9, 10, 11) are scored at the following tick.
An incomplete window is unscored. Repeating a tick does not duplicate the
queue/observations; a reversed world turn is rejected explicitly.

A delivered risk of at least 0.6 temporarily raises the granary's normal
target by up to two turns of current food demand, using only remaining
headroom below six turns. An existing base above that cap is preserved,
never reduced by a warning. The usual harvest EMA and target are computed first; the
increment is rebuilt from that base each turn, never compounded. Existing
granary procurement then decides whether it can buy: real treasury, surplus
beyond local needs, merchant commitments, route permissions, budget limits,
transit loss and spoilage all still apply. A warning can leave its target
unfilled. Before Phase 2 release uses last turn's target, expired, cancelled,
disabled or dormant extra targets are removed. Disabling the feature removes
its known previous target increment before dropping its state.

No new Rust packet kind, agent column, climate draw or yield multiplier is
introduced. Observation noise has its own deterministic stream under
`harvest_forecasts.observation`, keyed by seed, issuing turn and source region.
Existing RNG streams do not advance.

## Records and interpretation

Readable simulation events form a causal chain:

- `harvest_forecast_issued`: date, probability, future delivery date;
- `harvest_forecast_delivered`: actual delivery, citing issue;
- `harvest_preparedness`: actual paid granary purchases during a warning,
  citing delivery, only when there is a real payment;
- `harvest_forecast_resolved`: observed production ratio, incomplete window
  or cancellation, citing the report/delivery.

The world persists bounded observer histories, one report per recipient,
128 recent outcomes, cumulative counters and five probability bins. The
completed-turn snapshot uses `source_turn = world.turn - 1`. It exports dated
`reports`, `outcomes`, current-turn `preparedness`, `counters` and `calibration`.
Names belong to the recorded event/report, not a later territorial lookup.
Snapshot dictionaries detach from the mutable runtime. Old bundles and
inactive features have no forecast summary; readers must not substitute final
world state for absent historical data.

`bought_during_warning` and `paid_during_warning` are actual purchases made
while that region's warning raised its target, including any demand its
normal target also had. They are not a counterfactual allocation of additional
purchases or avoided losses. Reports score **realized winter local food
production/demand**, before trade and reserve release enter food sufficiency.
That ratio is still policy-sensitive: survival can change labor and demand.
Its Brier score is therefore arm-specific realized-outcome calibration, not a
pure exogenous-climate hazard score. Weather exogeneity is checked separately.

## Controls and present evidence

Persisted experimental policies `normal`, `withhold` and `shuffle` support
mechanistic tests. Withholding leaves the report and calibration intact but
prevents delivery and preparation. Shuffling rotates the estimated signals
between capital assessors before recipient choice; it consumes no additional
random stream. A zero-noise control leaves the frozen mean model unchanged.
These controls can be set through the runtime API for registered experiments;
they are not a claim that the causal full gate already qualifies this feature.

Focused tests cover strict versus dormant configuration, delayed contact
choice, issue/delivery/expiry, ownership, no future-state access, existing RNG
identity, withhold/shuffle/no-noise controls, paid stock/treasury conservation,
empty markets, noncompounding targets, cleanup before Phase 2, detached
snapshots, JSON continuation and exact checkpoints before issue, in transit
and after preparedness. The direct native test runs the real goods simulation
for 13 turns and checks issue, delivery and scored outcomes.

The focused forecast + existing granary selection passed **51 tests**, including
the native cases. The forecast selection also passed under the existing
offline guard: **25 passed, 1 native skipped**, guard PASS. Commands:

```sh
PYTHONPATH=src:tests RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest -q tests/test_harvest_forecasts.py tests/test_grain_reserves.py
PYTHONPATH=src:tests:scripts/testing CHRONICLER_OFFLINE_GUARD_REPORT=/tmp/guard-harvest.json PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -B -m pytest -q tests/test_harvest_forecasts.py -p python_oracle_guard -p no:cacheprovider
```

A small native fixture/control run (seed 42, 13 turns, one worker) produced
six reports in each arm. Normal, shuffle and no-noise delivered six; withheld
delivered zero. Each arm scored six outcomes and their exogenous climate-shock
vectors were identical. This natural short run bought no grain during its
warnings; the controlled resource-balanced positive test separately exercises
actual purchases. Those fixtures demonstrate mechanics and usable historical
data, not calibrated probability quality, reduced famine or net benefit.

All gate, exact-continuation and runtime identities must be recorded for the
integrated source/binary. Full held-out template/procedural qualification and
the proposed runtime/efficacy thresholds in the pre-registration remain
outstanding. The implementation is O(regions + contact edges + procurement
flows), uses no new native export, and performs no agent-pair scan; a numerical
overhead claim still requires a quiet paired benchmark.


## Population/demand boundary correction, 2026-10-28

Read-only artifact inspection found a negative forecast increment in the
original `forecast-dev-40/seed_43/shuffled/chronicle_bundle.json` at snapshot
33/source turn 32, report `harvest:2:0:6` (Stormbreak Cliffs): base target
4.126938305182808, increment -1.126938305182808, final target 3.0. The economy
had measured positive demand before the region emptied; normal granary
observation then skipped the empty region and retained its base. The warning
incorrectly capped the whole target against smaller current demand. The
original failed artifact is retained; these findings do not relabel that study
as passing. New source requires a new study.

The corrected warning caps only its nonnegative addition. It cannot reduce an
existing base even if demand shrinks. Empty recipients get no preparedness
increment or paid-preparation row. When normal granary observation cannot
rebuild a target (empty region, zero demand, missing economy or unowned
granary), the module restores its known old addition before discarding that
restoration record. It does not restore a newly rebuilt ordinary base merely
because it happens to equal yesterday's raised target. Same-turn reapplication
updates the recorded addition without compounding it; disabling restores the
recorded base.

Seven new regressions cover the numerical failure, bounded demand-shrink
headroom, no empty-region payment attribution, and exact JSON continuation
through unobserved boundaries. The forecast plus existing granary selection
passed 58 tests. No baseline granary source, parameter, EMA, route, stock or
cash arithmetic changed. In particular, ordinary base-target procurement under
a stale positive economy demand remains baseline behavior; it is not counted
as empty-region forecast preparation.
