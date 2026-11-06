# Connected-world CW4: preregistered held screen for quarantine rules (slice C1)

Status: FROZEN at `8c8feb412be2e216e2f0ca8107b46e1aead7abf3` (the screen module, extractors and simulation source after Amendment 1; the lead gave the go-ahead for the held run)

Written 2026-11-06 by the C1 lane on branch `claude/cw-cw4-screen` (main `1d4141d7` merged into
the C1 line at `be601a09`; the screen declared at `d8678f06`, first frozen there, and amended
before any held run at `8c8feb41`, Amendment 1 below). The native extension is the
shared build `101a4cd5b928b14f43539f925fa565036b94e38d91b9698071c80fa3656e0df3`; C1 changed no
Rust. No held seed (template 761-766, procedural 861-866) has been run. Code may change before
the held run only to fix a defect, recorded as an amendment below with a new pilot; no arm,
outcome, window or parameter changes in response to held outcomes.

Compute ceiling: 0.5 core-hours

Primary outcomes: cw4_world_arrivals, cw4_world_death_rate

## Purpose and limits

AUDIT-C section 7, test 7: does a quarantine that really closes trade (`--quarantine-mode
closure`) change epidemic exposure and mortality of the states that close, against the same
decisions and costs with nothing closed (`cost_only`), and what does it cost them and their
partners? The legacy multiplier rule and no quarantine are carried as references.

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip
  enumeration, not significance tests.
- Hybrid worlds only (the program's main mode). C1 closes trade only; migrants, armies,
  hostages, pilgrims and relief grain stay open (docs/integration/quarantine-rules.md), and in
  hybrid worlds migrants carried most cross-polity arrivals in the one pilot world of the
  audit. **Prediction (inferred, AUDIT-C section 7):** QR differs little from QC in hybrid
  worlds until migration closure (C1b) exists. A null result is a result, not a failure.
- Trajectories diverge once QR closes a route (different trade, actions, wars, later
  outbreaks and later decisions), so every measure after the first closure is a property of
  the whole trajectory, not a mechanism estimate.

## Units, cohorts and source

- **Units:** worlds (seeds). Every arm runs once on every world and is compared with its
  declared control on the same world, per stratum: template (8 regions, 4 civs) and
  procedural (32 regions, 10 civs, `--worldgen procedural --regions 32 --civs 10`).
- **Held cohort:** template 761-766, procedural 861-866 (`scripts/seed_registry.json`,
  reserved for CW4; the runner refuses any other seed). **Timing pilot:** the shared pilot,
  template 5 and procedural 19 (never evidence).
- **Base flags (every arm):** `--turns 200 --agents hybrid --simulate-only`; epidemiology and
  the contact ledger at their defaults (on for new worlds); every other switch at its default.
- **Arms** (one control chain QR -> QC -> Q0 -> QL; root QL):

  | Arm | Flags | Control |
  | --- | --- | --- |
  | QL | none (the legacy multiplier rule, the option omitted) | root |
  | Q0 | `--quarantine-mode none` | QL |
  | QC | `--quarantine-mode cost_only` | Q0 |
  | QR | `--quarantine-mode closure` | QC |

- **Runner:** `scripts/connected_world_screens.py` on `scripts/screen_runner.py` (lane E1).
  Command, once the lead agrees: `PYTHONPATH=<checkout>/src <native python>
  scripts/connected_world_screens.py run OUT --screen CW4 --cohort held --pilot
  PILOT/metrics.jsonl --jobs 2`, then `report`, `check --metrics ... --cohort held` and
  `mark-run`.
- **Identity (the extractors live in the screen module):** source `8c8feb41`, dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `a84fc211c80b6f3d97f4a6983a49d2fcd6c330b088af1440dea042a67d496d0c`; `scripts/screen_runner.py`
  `413301768935f70c8d1f79ef4309455775d3ef8d9133aa0a2f440e4143bf1164`; registry content
  `dc16f3c3b366699029de253da0a04d90394530b002ba3203b0e29b17ef7a98f8`; native extension
  `101a4cd5…`. A held run whose `source.txt` differs in any of these (apart from the
  preregistration line the runner adds) is not this screen.

## Activation (reported per world before any effect)

- **QC, QR:** activated when at least one closure (declared, in QC) opened over the run: the
  last snapshot's `epidemics.quarantine_rules.totals.closures_opened > 0`; unknown when the
  record is missing.
- **Q0:** acts by deciding nothing; activated when any snapshot reports an outbreak
  (`epidemics.active` non-empty).
- **QL:** the root.
- A world where an arm did not activate is shown as `not activated` and left out of that
  comparison's summaries, never counted as zero.

## Definitions

Turns are world turns w. The snapshot labelled s records world turn w = s - 1: its epidemic
tick, decisions and reports (`epidemics.quarantine_rules.receipt.turn` and
`food_accounting.source_turn` equal s - 1, checked on every development bundle).

- **Closing civ and closing turn.** Civ c closes at world turn w when c is listed in
  `history[s].epidemics.quarantine` (s = w + 1): closing in QR, declared in QC, closing under
  the legacy rule in QL, never in Q0.
- **Window.** Civ c's window is every world turn u with w + 1 <= u <= w + 1 + k for some
  closing turn w of c, with **k = 10**, cut at the run's last turn: the turns whose imports the
  closure, or its dated lag, can reach (a closure decided at w acts on journeys of w and on
  imports from w + 1). Each arm uses its own closing turns: the decision rule is identical in
  QC and QR, so their windows match until the trajectories diverge, and the window size is
  reported (`cw4_window`).
- **Cross-polity arrival.** An `epidemic_arrival` event with two distinct actors: the target
  region's controller when the pathogen arrived, then the source region's controller.
  Arrivals within one polity, from or into an uncontrolled region, are not cross-polity. An
  arrival is recorded with the onset report of the outbreak it caused (an import that never
  became a reported outbreak is not recorded).
- **Epidemic deaths of a civ at w.** The deaths of the reported outbreaks
  (`epidemics.active[*].deaths`) in regions the civ controls at the end of w
  (`region_control`). Deaths in outbreaks below the reporting threshold are recorded only in
  the world total (`epidemics.deaths`); on the development worlds the reported outbreaks held
  80-90% of all epidemic deaths (`reported_death_share`, kept per run).
- **Person-turns of a civ at w:** `civ_stats[c].population` at the end of w.
- **World person-turns:** the sum over world turns of `regional_population.counts` (every
  region, controlled or not, at the end of the turn; `source_turn` = w, checked).
- **All epidemic deaths at w:** `epidemics.deaths` of the snapshot of w, reported outbreaks or
  not; the extractor checks that they sum to the last `deaths_total` (a mismatch is a missing
  outcome).

## Primary outcomes (QR - QC on each world; whole run, world level)

Neither primary conditions on any arm's own closures (Amendment 1).

1. `cw4_world_arrivals`: cross-polity epidemic arrivals over the whole run, world total
   (`events_timeline` events `epidemic_arrival` with two distinct actors).
2. `cw4_world_death_rate`: all epidemic deaths over the whole run per 1,000 world
   person-turns (`sum(history[*].epidemics.deaths)`, equal to the last
   `epidemics.deaths_total`, over `sum(history[*].regional_population.counts)`).

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw4_world_arrival_rate` | cross-polity arrivals per 1,000 region-turns (regions x turns, from `regional_population.counts`) | QR - QC |
| `cw4_world_deaths` | world epidemic deaths, count (`deaths_total`, last) | QR - QC |
| `cw4_sel_arrivals` | arrivals into regions of closing civs during their windows: **conditioned on each arm's own closures (selection)** | QR - QC |
| `cw4_sel_deaths` | epidemic deaths (reported outbreaks) of closing civs during their windows per 1,000 of their person-turns there: **selection** | QR - QC |
| `cw4_sel_arrival_rate` | window arrivals per 100 window civ-turns: **selection** | QR - QC |
| `cw4_sel_window` | window civ-turns (exposure denominator): **selection** | QR - QC |
| `cw4_cost_world_deaths` | world epidemic deaths per 1,000 person-turns: the cost effect | QC - Q0 |
| `cw4_cost_world_arrivals` | cross-polity arrivals, world: the cost effect | QC - Q0 |
| `cw4_cost_treasury` | world treasury at the end: the cost effect | QC - Q0 |
| `cw4_legacy_world_arrivals` | cross-polity arrivals, world | QR - QL (the negative of QL - QR; the runner pairs an arm with a control on its chain) |
| `cw4_legacy_world_death_rate` | world epidemic deaths per 1,000 person-turns | QR - QL |

## Harm panel

The runner's fixed panel (population, treasury, food shortfall after relief, priced-out
persons and children (not recorded: retail off), famine and war deaths (no bundle field:
"requires slice extractor"), epidemic deaths, out-migration, wealth Gini, forest stand (not
recorded: timber stock off)) beside every comparison QR - QC, QC - Q0, Q0 - QL and QR - QL;
plus C's trade and fiscal harms as secondary outcomes:

| Id | Harm | Comparison | Source |
| --- | --- | --- | --- |
| `cw4_h_forgone` | route income forgone, both sides | QR alone (structurally 0 in QC: nothing closes) | rules `totals.forgone_income` |
| `cw4_h_food` | net food transport into closing civs' regions in their windows | QR - QC | `food_accounting.regions[*].native.transport_net`, summed over the civ's regions (cross-border net inflow plus internal transit losses; **food imports by origin are not recorded**, so this is the recorded proxy) |
| `cw4_h_replans` | merchant disruption replans, world | QR - QC | `metadata.merchant_trip_stats[*].disruption_replans` (world-wide, not attributable to closures) |
| `cw4_h_unwinds` | merchant unwinds, world | QR - QC | `metadata.merchant_trip_stats[*].unwind_count` |
| `cw4_h_treasury` | closing civs' treasury at the end | QR - QC | `civ_stats` of every civ that ever closed |
| `cw4_h_stability` | closing civs' mean stability in their windows | QR - QC | `civ_stats[*].stability` |
| `cw4_h_partner_population`, `cw4_h_partner_treasury` | partner civs (closed against at any decision) at the end: the externality | QR - QC | rules `closures[*].target`, `civ_stats` |
| `cw4_h_leaked` | deliveries that still crossed a closed pair | QR alone | rules `totals.leaked_deliveries` |
| `cw4_h_enforcement` | enforcement paid | QR - QC | rules `totals.enforcement_paid` |

Also kept per row (not outcomes): closing and partner civ counts, closures opened, closed
pair-turns, route-turns removed, merchant edges cut, stalled trips, reported death share.

**Structural zeros versus unknowns.** Q0 has no closing civ, so its window measures are
structural zeros (and are not used in any comparison with Q0). QL keeps no rules record, so
the rules measures are `None` there (not recorded), never zero; `leaked_deliveries` is `None`
in QC (nothing closes). A missing epidemics, quarantine, region-control, civ-stats or
merchant-stats record, a rules record in QL, a missing one under a new mode, or a mode other
than the arm's is a missing outcome: the run fails (rc 3) and is reported as failed.

## Extractor validation (development worlds only, before any pilot)

Development runs of all four arms, `--cohort dev`: template 7 and procedural 11 at 100 turns,
template 42 and procedural 31 at 200 turns (`--keep-first`). An independent checker
(outside the repository, `/home/user/evidence/cw4/validate/validate_cw4.py`, reading the raw
bundles) passed every check on all 16 bundles (192 checks, 0 failures; rerun on the amended
extractor at `8c8feb41` with the primaries' checks added: 240 checks, 0 failures):

- snapshot s records world turn s - 1 (receipt turn and food-accounting source turn);
- every cross-polity arrival's target actor is the region's controller at the end of its turn
  (1,722 of 1,724), or at its start when the region changed hands during the turn (2); 2,536
  arrivals in all;
- every arrival coincides with an onset report of the same region, pathogen and turn;
- the per-turn epidemic deaths sum to `deaths_total`; reported deaths never exceed the turn's
  deaths (reported share 0.80-0.90);
- in QC and QR the quarantine list equals the civs that paid enforcement every turn;
  `closures_opened` equals the distinct closure ids seen; forgone income and leaked
  deliveries equal the sums of the per-turn receipts;
- Q0 closes nothing; QL keeps no rules record;
- windows and arrivals recomputed directly from the raw lists equal the extractor's;
- one merchant-trip record per tick;
- (Amendment 1) the world arrivals equal the raw count of cross-polity arrivals;
  `regional_population.source_turn` = s - 1 in every snapshot; the world death rate equals
  1,000 x `deaths_total` / the sum of the regional counts (the regional counts and the civ
  populations differ by under 0.4% of person-turns on these worlds: uncontrolled regions and
  the civ population's own timing).

`tests/test_cw4_screen.py` covers the arms, windows, arrivals, deaths, food transport, the
rules measures, missing records and activation on constructed bundles. `check --screen CW4`
passes.

## Timing pilot (the shared pilot, on the frozen source)

Rerun after Amendment 1 on `8c8feb41` (clean tree; the first pilot at `d8678f06` was refused by
the changed screen module and is superseded): `run PILOT --screen CW4 --cohort pilot --jobs 2`,
8 runs, 0 failed, every outcome extracted (`check --metrics ... --cohort pilot` passes); 105 s of
simulation and extraction at 2 concurrent processes on the shared, loaded 4-core machine. Mean
seconds per run: template QL 7.0, Q0 7.1, QC 7.1, QR 7.1; procedural QL 17.9, Q0 17.8, QC 21.0,
QR 20.4. Every arm activated on both pilot worlds. **Projected held run: 0.176 core-hours for
48 runs** (x1.5 = 0.264). The pilot's `metrics.jsonl`, `source.txt` and `report.md` are
retained in `connected-world-screens-cw4/pilot/` (the held run's `--pilot`). The pilot's
outcomes were not read for any decision.

## Budget and stopping rules

- **Compute ceiling 0.5 core-hours** (the line above, read by the runner; the lead's
  Amendment 1, under the 2.0 cap), at most 3 concurrent processes; run with `--jobs 2`
  because other lanes share the 4 cores. The runner
  refuses a held run whose pilot projection x1.5 exceeds the ceiling and starts no run that
  would pass it; runs not started are reported as `not run` (exit code 4), never as zeros.
  Held worlds slower than the pilot can therefore stop the run early; the stop is reported,
  and raising the ceiling needs the lead's amendment before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction
  (`--keep-first` keeps one world per stratum outside the repository for diagnosis).
- A failed run is reported as failed with its reason and is not replaced by another seed; a
  held-run failure that needs new worlds uses the program reserve through the lead
  (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `held-run.json`
  under `docs/superpowers/progress/connected-world-screens-cw4/`), `check --metrics`, and
  `mark-run`, whose registry change is committed with the results.

## Amendments

**Amendment 1 (before any held run), 2026-11-06, the lead's review.**

1. *Primaries must not condition on post-treatment variables.* Each arm's closure windows
   follow that arm's own trajectory (QR's closures can suppress later reports and so shrink
   its own windows), so window-restricted measures compare different selections. The
   primaries are replaced by whole-run, world-level outcomes, QR - QC: `cw4_world_arrivals`
   (every cross-polity arrival of the run; its rate per 1,000 region-turns is a secondary) and
   `cw4_world_death_rate` (all epidemic deaths, `epidemics.deaths` summed, over the world's
   person-turns from `regional_population.counts`). The former primaries `cw4_arrivals` and
   `cw4_deaths_closing` become the secondaries `cw4_sel_arrivals` and `cw4_sel_deaths`, with
   the window rate and size, labelled "conditioned on each arm's own closures (selection)".
   The cost effect (QC - Q0) and the legacy comparison (QR - QL) now use the world measures.
2. *Compute ceiling 0.5 core-hours* (was 0.266, the first pilot's projection x1.5): the pilot
   was measured on a heavily loaded shared machine; 0.5 stays well under the 2.0 cap. At most
   3 processes; run with `--jobs 2`.

The screen module changed (new SHA-256 above), so the pilot was rerun on `8c8feb41`. No held
seed had been run, and no held outcome was seen.

## Results (held run, 2026-11-06)

Read after the run; nothing below changed an arm, outcome or parameter, and no held seed was
rerun. Full report: `connected-world-screens-cw4/held/report.md` (every per-world value of
every outcome and harm), with `metrics.jsonl`, `source.txt` and `held-run.json` beside it.

**Run.** `run HELD --screen CW4 --cohort held --pilot .../pilot/metrics.jsonl --jobs 2
--keep-first` on source `14c3b90f` (the frozen code `8c8feb41` plus this page's Amendment 1
commit; dirty 0), started 19:41:03Z, finished 19:45:41Z: **48 runs, 0 failed, complete, every
outcome extracted**; **0.153 core-hours** of simulation and extraction (ceiling 0.5; the pilot
projected 0.176), 278 s of wall time at 2 processes. `check --cohort held` passes; `mark-run`
recorded `cw4-held-t` and `cw4-held-p` as run (48 rows, complete) in
`scripts/seed_registry.json`. Identities: run digest `158fbeb0…`; native `101a4cd5…`; runner
`41330176…`; screen module `a84fc211…`; registry content `dc16f3c3…`; preregistration
`deecbaa9…` (this page as frozen). Mean seconds per run: template 5.9-6.1, procedural 16.4-17.5.

**Activation (before any effect).** Q0, QC and QR activated on 6 of 6 worlds in both strata.
On template 763 QR opened 59 closures but no closed pair had a route or merchant edge between
them (0 route-turns, 0 edges removed), so QR's world equals QC's there and every QR - QC
difference is a recorded exact 0.

### Primary outcomes (QR - QC, whole run, world level)

| Outcome | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign flips at least as extreme (of 64) |
| --- | --- | --- | --- | --- | --- |
| `cw4_world_arrivals` | template | 761 -9, 762 -2, 763 0, 764 +12, 765 +5, 766 -1 | +0.83 [-9, +12] | 2 / 3 / 1 | 52 (means ±4.83) |
| `cw4_world_arrivals` | procedural | 861 +11, 862 -48, 863 -7, 864 +62, 865 -7, 866 -8 | +0.50 [-48, +62] | 2 / 4 / 0 | 64 (means ±23.8) |
| `cw4_world_death_rate` (per 1,000 person-turns) | template | -0.146, -0.095, 0, +0.543, -1.199, -0.341 | -0.207 [-1.199, +0.543] | 1 / 4 / 1 | 32 (means ±0.387) |
| `cw4_world_death_rate` | procedural | +0.146, -3.473, +0.248, +3.549, -5.609, -3.605 | -1.457 [-5.609, +3.549] | 3 / 3 / 0 | 30 (means ±2.77) |

**Both primaries are nulls in both strata**: no consistent sign, and the observed means sit in
the middle of their sign-flip distributions. This matches the preregistered prediction (C1
closes trade only; migrants stay open, and in these hybrid worlds a closure is weaker and
slower than the legacy multiplier).

### Secondary outcomes (means per stratum; template / procedural)

- World arrivals per 1,000 region-turns (QR - QC): +0.52 / +0.08 (null, as P1).
- World epidemic deaths, count (QR - QC): -5.7 [-29, +18], 1/4/1 / -96.3 [-313, +219], 3/3/0
  (sign-flip 28 and 20 of 64): mixed.
- Selection-conditioned (each arm's own closures): window arrivals -6.8 (0/4/2) / -36.5
  (2/4/0), 8 of 64 each; window deaths per 1,000 person-turns -0.83 (1/4/1) / -1.85 (2/4/0);
  but the windows themselves shrink under QR, -38.8 / -223 civ-turns (QR closes fewer and
  shorter times, partly because its closures change later reports). These compare different
  selections and are not effects.
- Cost effect (QC - Q0): world death rate +0.49 [0, +1.28], 4/0/2, 8 of 64 / -0.81 [-5.09,
  +1.20], 3/3/0; world arrivals +2.5 / -3.7; world treasury +81 / -150: no consistent cost
  effect (on template 761 the declared quarantines changed only the treasury, and on 762 no
  recorded outcome at all).
- Legacy comparison (QR - QL, the negative of QL - QR): world arrivals +12.8 [0, +21], 5/0/1,
  4 of 64 / +8.5 [-64, +75], 5/1/0, 34 of 64; world death rate +0.53, 4/2/0 / -0.70, 2/4/0.
  Descriptively, the legacy multiplier world had fewer recorded cross-polity arrivals than the
  real closure, most clearly in template worlds; deaths are mixed.

### Harms

C's trade and fiscal harms (QR - QC unless QR alone):

- Route income forgone, both sides (QR alone): 519 [0, 1,260] / 1,769 [704, 3,636] treasury.
- Merchant unwinds (world): +17.5 [0, +62], 4/0/2 / +92.2 [+30, +152], 6/0/0 (2 of 64);
  disruption replans: -0.17 (5 of 6 zero) / +23.7 [+5, +52], 6/0/0 (2 of 64).
- Deliveries still crossing a closed pair (QR alone): 8 [0, 19] / 60.5 [28, 87] per run.
- Enforcement paid: -65 / -314 (QR decided fewer closures than QC after the trajectories split).
- Net food transport into closing civs' windows, closing civs' treasury and stability, partner
  civs' population and treasury: mixed signs, no consistent difference (report).

Fixed harm panel, QR - QC:

- Food shortfall after relief over the run: +259.5 [-103, +692], 3/2/1 / +1,044 [-2,693, +3,328],
  5/1/0 (16 and 18 of 64): more shortfall under closure in most worlds.
- Agents migrating between regions: +106 [0, +366], 5/0/1 (4 of 64) / +1,437 [-956, +4,218],
  5/1/0 (8 of 64): more migration under closure.
- Epidemic deaths: as the secondary above.
- Population and treasury at the end, wealth Gini: mixed.
- Not recorded in these runs: priced-out persons and children (retail off), forest stand
  (timber stock off).
- No bundle field: famine and war deaths ("requires slice extractor", owners named in the
  runner).

The Q0 - QL, QC - Q0 and QR - QL rows of the panel are in the report. No world failed, none
was incomplete, and no outcome was missing.
