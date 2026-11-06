# Connected-world CW4: preregistered held screen for quarantine rules (slice C1)

Status: FROZEN at `d8678f06d653d973e5dda4beb2e0fa4cfbf746fa` (the screen module, extractors and simulation source), awaiting the lead's review before any held run

Written 2026-11-06 by the C1 lane on branch `claude/cw-cw4-screen` (main `1d4141d7` merged into
the C1 line at `be601a09`; the screen declared at `d8678f06`). The native extension is the
shared build `101a4cd5b928b14f43539f925fa565036b94e38d91b9698071c80fa3656e0df3`; C1 changed no
Rust. No held seed (template 761-766, procedural 861-866) has been run. Code may change before
the held run only to fix a defect, recorded as an amendment below with a new pilot; no arm,
outcome, window or parameter changes in response to held outcomes.

Compute ceiling: 0.266 core-hours

Primary outcomes: cw4_arrivals, cw4_deaths_closing

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
- **Identity (the extractors live in the screen module):** source `d8678f06`, dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `daeb91c108cf9896660984b506fb00e25f0da3d810373a7f5beb5e59f865fce9`; `scripts/screen_runner.py`
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

## Primary outcomes (QR - QC on each world)

1. `cw4_arrivals`: cross-polity epidemic arrivals into regions of closing civs during their
   windows (count, summed over closing civs).
2. `cw4_deaths_closing`: epidemic deaths of closing civs during their windows per 1,000 of
   their person-turns during their windows (0 when a run has no window).

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw4_arrival_rate` | arrivals per 100 window civ-turns | QR - QC |
| `cw4_window` | window civ-turns (exposure denominator) | QR - QC |
| `cw4_world_deaths` | world epidemic deaths (`deaths_total`, last) | QR - QC |
| `cw4_world_death_rate` | world epidemic deaths per 1,000 person-turns | QR - QC |
| `cw4_cost_world_deaths` | world epidemic deaths: the cost effect | QC - Q0 |
| `cw4_cost_treasury` | world treasury at the end: the cost effect | QC - Q0 |
| `cw4_legacy_arrivals` | arrivals into closing civs in their windows (QL's windows are its legacy closures) | QR - QL (the negative of QL - QR; the runner pairs an arm with a control on its chain) |
| `cw4_legacy_world_deaths` | world epidemic deaths | QR - QL |

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
bundles) passed every check on all 16 bundles (96 + 96 checks, 0 failures):

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
- one merchant-trip record per tick.

`tests/test_cw4_screen.py` covers the arms, windows, arrivals, deaths, food transport, the
rules measures, missing records and activation on constructed bundles. `check --screen CW4`
passes.

## Timing pilot (the shared pilot, on the frozen source)

`run PILOT --screen CW4 --cohort pilot --jobs 2` at `d8678f06` (clean tree): 8 runs, 0 failed,
every outcome extracted (`check --metrics ... --cohort pilot` passes); 106 s of simulation and
extraction, 54 s of wall time at 2 concurrent processes on the shared 4-core machine. Mean
seconds per run: template QL 6.2, Q0 6.1, QC 7.7, QR 8.2; procedural QL 19.1, Q0 20.6, QC 19.0,
QR 19.3. Activation: every arm activated on both pilot worlds. The pilot's `metrics.jsonl`,
`source.txt` and `report.md` are retained in `connected-world-screens-cw4/pilot/` (the held
run's `--pilot`). **Projected held run: 0.177
core-hours for 48 runs**; x1.5 = 0.2655, so the ceiling is 0.266 core-hours (under the 2.0
cap). The pilot's outcomes were not read for any decision.

## Budget and stopping rules

- **Compute ceiling 0.266 core-hours** (the line above, read by the runner), at most 3
  concurrent processes; run with `--jobs 2` because other lanes share the 4 cores. The runner
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

None.
