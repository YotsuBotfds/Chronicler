# Harvest assessments: first-slice pre-registration

Registered before implementation/parameter fitting on base `5b5252ed`, 2026-10-29.
The feature is default off. This is a proposal being implemented, not a claim
of behavioral efficacy or full scientific qualification.

## Causal claim and scope

Capital harvest assessors observe present and past local food production per
head. A dated, noisy estimate of the same year's winter production shortfall
travels to a granary through the previous completed turn's contact topology.
Only a delivered warning can raise its temporary target; ordinary procurement
then pays for available grain within its existing budget, route, commitment,
transit and storage constraints. No food, treasury or yield is granted.

`--harvest-forecasts` requires grain reserves and an agent-backed goods economy.
Enabling an incompatible configuration fails explicitly. Forecasts concern
local food production/demand, not realized hunger after trade and reserve
release. Calibration and preparedness expenditures are separate records.

No future climate/hazard hash, future world state, flood forecast, native
information-packet relabeling, new per-agent column or automatic feature
promotion is part of this slice.

## Frozen initial rule

- One assessor per living civilization's owned capital. Keep at most six
  present/past observations per region; at least three are needed to publish.
- Normalize each measured food harvest/demand ratio by the current public
  grain seasonal multiplier, capped at four. At summer close (step 5 of the
  existing 12-turn year), the mean normalized signal times winter's public
  grain multiplier estimates winter production/demand. This deliberately
  imperfect model does not pretend every food good follows grain seasonality.
- Estimate probability of mean winter production/demand below 0.6 as
  `clamp(0.5 + 0.5 * (0.6 - predicted_ratio) / 0.6 + noise, 0.05, 0.95)`.
  Noise is uniform on [-0.15, 0.15], drawn once from a separate namespaced
  stream keyed by seed, issuing turn and source region. Confidence is
  observation completeness (`observations / 6`), not probability of truth.
- Winter's evaluation window is steps 9, 10 and 11. Report expiry is step 11;
  all three measured outcomes are required for a scored result. Missing
  measurements are unscored, not evidence that shortage was absent.
- Local reports arrive after one turn; reports over an existing positive
  contact edge arrive after two. There is at most one active report per
  recipient region. Choose confidence, then shorter delay, then source index;
  do not select the most alarming forecast. Ownership changes cancel receipt
  by the previous ruler. Contact routes are fixed at issue, never backdated.
- A delivered report with probability >= 0.6 adds
  `2 * probability * confidence` turns of current food demand to the normal
  target, capped at two extra turns and at six total target turns. Rebuild it
  from the normal target every turn; it never compounds or changes harvest
  observation means. The increment ends at expiry/cancellation.
- Preserve only one active report per region plus 128 recent outcomes and
  cumulative calibration bins/counters. Never retain per-agent medical,
  attendance or forecasting histories.

## Tests and planned experiment

Development controls: normal delivery; withheld delivery (same forecasts and
calibration, no action); forecast signals shuffled among issuers within the
same publication turn; zero-noise comparison. A delivered warning must precede
target changes, purchases and winter observations. Costs in the snapshot are
actual purchases during warnings, not an estimate of causal excess purchases
or avoided losses.

Qualification, after freezing this implementation: paired normal/withheld
worlds with identical exogenous climate vectors, plus shuffled and no-noise
controls, using a development subset and later held-out template/procedural
cohorts. Primary efficacy outcome is the seed-clustered difference in severe
hunger person-turns in the registered winter windows. Report Brier error versus
seasonal climatology, false alarms, treasury purchases, spoilage and unmet
targets separately. Do not select episodes based on treatment-induced famine
or tune against the held-out cohort. A null/inconclusive result stays such.

Required mechanical evidence: flag-off output/RNG identity; same-turn rejection;
expiry and ownership cancellation; deterministic contact choice and queue;
stock/treasury/resource conservation; no future-state access; exact continuation
before issue, during transit and after preparedness; serial/thread determinism.
Target runtime is O(regions + contact edges) per turn with sparse annual issue,
no extra native exports, no agent-pair scans, and proposed <=2% paired whole-turn
CPU overhead before promotion. No such speed or efficacy is assumed in advance.
