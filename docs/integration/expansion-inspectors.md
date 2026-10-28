# Historical inspectors for recorded expansion systems

The viewer reads three optional observations from the simulation's existing
per-turn snapshot transport. These sections appear only when the run actually
records their field; enabling a saved world flag or retaining final state
alone does not create a historical view. No viewer control changes simulation
features or synthesises their outcomes.

| Snapshot field | Location | Recorded observations |
| --- | --- | --- |
| `harvest_forecasts` | Food | Reports, issue/delivery/expiry dates, winter target windows, predicted shortfall probability, confidence, actual preparedness targets/purchases/payments, resolved outcomes and calibration |
| `health_care` | Epidemics | Rural work-injury episodes, onsets/recoveries, lost farmer work, household-care work and recipients, recorded recovery-progress totals |
| `ritual_gatherings` | Faiths | Actual selected-local-adult attendance, historical host/faith, held/cancelled receipts, food and treasury consumed, contact units, bond attempts and schedules |

The region inspector also reads the same observations for its selected region.
Region/controller/host names come from the dated summaries; later territorial
owners and final-world data never fill gaps.

## Time and missing information

`observationAt` accepts a summary only when `source_turn` equals snapshot turn
minus one. A stale summary or a future stamp is unknown at that snapshot.
Tables use the selected snapshot, charts stop there, and missing earlier rows
stay null gaps rather than zero quantities. Before the first available row,
an existing system's section explains that its observation is unknown; a
system never recorded in the run has no section at all.

Gathering history accepts only outcomes whose occurrence turn equals their
containing summary's source turn. It does not replay an old receipt. Each mark
seeks the snapshot containing that completed occurrence, not the start of the
occurrence's simulation turn. Schedule dates are labelled plans, not future
attendance. Attendee IDs are the actual saved IDs; no character names or travel
claims are invented. Historical hosts and faith names remain the occurrence's
own recorded values across conquest and faith succession.

## Interpretation and quantities

Harvest probability predicts winter **production divided by demand before
trade/reserve releases**. It is distinct from observation completeness
(`confidence`) and from whether people actually went hungry. Pending and
withheld reports are visibly undelivered. Preparedness purchases/payments
are actual completed-turn receipts while a warning was active; they are not
estimated extra spending or avoided losses caused by the report. Grain and
treasury stay in separate columns. Unscored/cancelled assessments retain their
status rather than becoming zero errors. Calibration derives means only for
bins with recorded scored reports.

Injury/care work uses fractional worker-turns. The section identifies its rural
injury/household-care scope alongside the separate epidemic model; it does not
turn those work quantities into medical spending or disease prevalence.
Recovery progress among care recipients is an observed group total, not a
counterfactual estimate of care's benefit.

Gathering food and treasury columns are actual consumption and spending. Bond
operations are attempts, not successful new bonds. Counters count attendances,
so the same person can appear in more than one occurrence. The viewer adds no
spiritual, legitimacy or practice effects to those receipts.

## Fixtures and verification

`transport_bundle.json` includes explicit empty shape stand-ins for these
optional fields, matching the shared transport fixture builder. Its original
source run does not qualify the three features; it checks transport only.
`expansionHistory.ts` contains small explicit test observations and never
serves as a production fallback.

`harvest_forecast_observations.json` is a safe subset of an actual 13-turn native
feature run (seed 42), containing only its dated forecast summaries and the
SHA-256 of the original source bytes. It is not a complete viewer bundle.
The fixture preserves the observed six-pending → four-delivered/two-pending →
six-delivered → six-scored cycle. That short run had target increments but no
buyable surplus, so its actual purchases remain zero. A separate explicit UI
test checks positive purchase/payment columns without presenting those values
as an observed natural run.

Rebuild the forecast observation subset from a decoded run:

```sh
cd viewer
node scripts/build-harvest-observations.mjs DECODED_BUNDLE.json
```

Focused tests check source-turn boundaries, unknown historical gaps, omission
when unrecorded, actual delivery versus plans, future-outcome exclusion,
payments versus grain, gathering receipt timing, owner/faith history,
region navigation and streaming/reconnect transport. Production browser checks
use a real combined run after native feature integration; they are separate
from fixture-based component tests.

Initial focused verification: 23 viewer tests passed with one worker, including
the actual native forecast cycle; ESLint passed. Full-suite/build and combined
native browser qualification are coordinated after producer integration.
