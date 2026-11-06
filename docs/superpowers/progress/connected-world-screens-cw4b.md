# Connected-world CW4b: preregistered held screen for the migration channel of quarantine closure (slice C1b)

Status: FROZEN at `a732382e400d49f6aad4189725979587699ae139` (the screen module, extractors, seed registry and simulation source, unchanged by Amendment 1; the pilot below ran on it, clean tree), with this page frozen as amended by Amendment 1 (compute ceiling 0.5 core-hours) before any held run; the lead approved the screen and gave the go-ahead for the held run (2026-11-06)

Written 2026-11-06 by the C1b lane on branch `claude/cw-c1b-migration` (from `main` `8286804c`;
C1b at `c7242983`, approved; the bounded refusal memory at `ea8a4657`; the screen declared at
`a732382e`). Native extension: the lane's build of that source, SHA-256
`e724072d7888888ede86acccb8db745c219c445fd47644ec9abe8ed5493e865b`. No held seed (template
3101-3106, procedural 3201-3206) has been run. Code may change before the held run only to fix a
defect, recorded as an amendment below with a new pilot; no arm, outcome, window or parameter
changes in response to held outcomes.

Compute ceiling: 0.5 core-hours

Primary outcomes: cw4b_world_arrivals, cw4b_world_death_rate

## Purpose and limits

CW4 found both of its primaries null: a trade-only closure (`--quarantine-mode closure`) did not
change cross-polity epidemic arrivals or world epidemic deaths against the same decisions and
costs with nothing closed (`cost_only`), in hybrid worlds where migrants carry most cross-polity
contact. C1b closes the migration channel too (`--quarantine-channels trade,migration`:
docs/integration/quarantine-rules.md, "Migration closure (C1b)"). CW4b asks: does a closure of
trade and migration change world-level epidemic exposure and mortality against `cost_only`, how
much does the migration channel add to the trade closure, and what does it cost (refused
migrants, flight and hunger, food, population, treasury, partners, trade)?

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip
  enumeration, not significance tests.
- Hybrid worlds only. The migration channel is accepted only where the native pool owns the
  population (hybrid, demographics-only).
- Refused migrants stay home (the lead's decision: refusal, not diversion), so the closure can
  shift epidemic and famine exposure to the refusing regions. Trajectories diverge once a
  closure acts, so every measure after the first closure is a property of the whole trajectory,
  not a mechanism estimate.
- **Prediction (inferred, not tested here):** fewer cross-polity arrivals under QRM than under
  QC and QR. The development worlds (inspected freely, never evidence) pointed that way at 100
  turns; the effect on the death rate is uncertain because refused migrants stay in famine and
  epidemic regions. A null result is a result, not a failure.

## Units, cohorts and source

- **Units:** worlds (seeds). Every arm runs once on every world and is compared with its
  declared control on the same world, per stratum: template (8 regions, 4 civs) and
  procedural (32 regions, 10 civs, `--worldgen procedural --regions 32 --civs 10`).
- **Held cohort (new, reserved for CW4b):** template 3101-3106, procedural 3201-3206
  (`scripts/seed_registry.json` entries `cw4b-held-t` and `cw4b-held-p`, status `reserved`).
  The lead verified these numbers appear nowhere as seeds; a targeted repository scan (seed keys,
  `--seed` values, seed lists and ranges) found them only in the registry and the screen module,
  and `check --screen CW4b` (the runner's `check_seeds`: the registry reservation, no other entry,
  no gate range, not 1000-1999, no development world, no duplicate, not run) passes. **Timing
  pilot:** the shared pilot, template 5 and procedural 19 (never evidence).
- **Base flags (every arm):** `--turns 200 --agents hybrid --simulate-only`; epidemiology and
  the contact ledger at their defaults (on for new worlds); every other switch at its default.
- **Arms** (one control chain QRM -> QR -> QC; root QC):

  | Arm | Flags | Control |
  | --- | --- | --- |
  | QC | `--quarantine-mode cost_only` (the closure decisions and enforcement cost, nothing closed) | root |
  | QR | `--quarantine-mode closure` (trade closed; the default channel) | QC |
  | QRM | `--quarantine-mode closure --quarantine-channels trade,migration` | QR |

- **Runner:** `scripts/connected_world_screens.py` on `scripts/screen_runner.py` (lane E1).
  Command, once the lead agrees: `PYTHONPATH=<checkout>/src <native python>
  scripts/connected_world_screens.py run OUT --screen CW4b --cohort held --pilot
  docs/superpowers/progress/connected-world-screens-cw4b/pilot/metrics.jsonl --jobs 2`, then
  `report`, `check --metrics ... --cohort held` and `mark-run`.
- **Identity (the extractors live in the screen module):** source `a732382e`, dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `3567a33ba0b1407616808d52226e584782c7c4c16a4f7bac50336542891e753b`; `scripts/screen_runner.py`
  `413301768935f70c8d1f79ef4309455775d3ef8d9133aa0a2f440e4143bf1164`; registry content
  `a703a8502cb688181662d323ff482822a3fec6df292d23ebccc42f05751b2cfe`; native extension
  `e724072d…`. A held run whose `source.txt` differs in any of these (apart from the
  preregistration line the runner adds) is not this screen; in particular the held run needs
  this screen module byte for byte (a later change to it, for another screen, needs a new pilot
  and an amendment).

## Activation (reported per world before any effect)

- **QR:** activated when at least one closure opened over the run (the last snapshot's
  `epidemics.quarantine_rules.totals.closures_opened > 0`); unknown when the record is missing.
- **QRM:** activated when at least one closure opened **and** at least one migrant was refused
  (`totals.migrants_blocked > 0`): both of its channels acted; unknown when either total is
  missing.
- **QC:** the root (the runner does not judge it); its closures are declared, not restricting.
- A world where an arm did not activate is shown as `not activated` and left out of that
  comparison's summaries, never counted as zero.

## Definitions

CW4's definitions apply unchanged (its validated extractor, `cw4_extract`, supplies them): the
dating (snapshot s records world turn s - 1), closing civs and turns
(`history[s].epidemics.quarantine`), windows (k = 10), cross-polity arrivals (an
`epidemic_arrival` with two distinct actors), epidemic deaths (reported outbreaks by civ;
`epidemics.deaths` for the world, summing to the last `deaths_total`), civ and world person-turns
(`civ_stats[c].population`; `regional_population.counts`). Added for CW4b (`cw4b_extract`):

- **Channels.** Every snapshot's rules record carries the arm's channels: `[]` in QC, `["trade"]`
  in QR, `["trade", "migration"]` in QRM; anything else is a missing outcome.
- **Refusals** (QRM): migrants refused at a closed border, summed over ticks
  (`totals.migrants_blocked`; person-ticks: an agent refused on k ticks counts k times). The
  extractor checks that the per-snapshot receipts (`receipt.migrants_blocked`, each observed,
  never null) sum to the total and that each receipt's refusal rows sum to its count.
- **Refusal spells** (`totals.migrants_refusal_spells`): an agent refused on consecutive ticks
  counts once per unbroken spell (between the distinct persons refused and the refusals).
- **Flight** (`totals.migrants_blocked_flight`): refusals whose driver is persecution, famine,
  battle, conquest or persecution memory, or the safety need; it **excludes** hunger-driven
  moves. **Hunger-driven** (`totals.migrants_blocked_hunger`): food opportunity and material need.
  Drivers are each refused move's dominant term (a household follower takes its lead's), so both
  are lower bounds of the moves those motives contributed to.
- Outside QRM the migration measures are `None` (not recorded), never zero; a migration total in
  QC or QR is a missing outcome.

## Primary outcomes (QRM - QC on each world; whole run, world level)

Neither conditions on any arm's own closures.

1. `cw4b_world_arrivals`: cross-polity epidemic arrivals over the whole run, world total.
2. `cw4b_world_death_rate`: all epidemic deaths over the whole run per 1,000 world person-turns.

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw4b_mig_world_arrivals` | cross-polity arrivals, world | QRM - QR (the migration channel's increment) |
| `cw4b_mig_world_death_rate` | world epidemic deaths per 1,000 person-turns | QRM - QR |
| `cw4b_trade_world_arrivals` | cross-polity arrivals, world | QR - QC (the trade closure alone, CW4's comparison on these worlds) |
| `cw4b_trade_world_death_rate` | world epidemic deaths per 1,000 person-turns | QR - QC |
| `cw4b_world_arrival_rate` | cross-polity arrivals per 1,000 region-turns | QRM - QC |
| `cw4b_world_deaths` | world epidemic deaths, count | QRM - QC |
| `cw4b_sel_arrivals` | arrivals into closing civs' regions in their windows: **conditioned on each arm's own closures (selection)** | QRM - QC |
| `cw4b_sel_deaths` | epidemic deaths (reported outbreaks) of closing civs in their windows per 1,000 of their person-turns: **selection** | QRM - QC |
| `cw4b_sel_window` | window civ-turns: **selection** | QRM - QC |
| `cw4b_refusals` | migrants refused (person-ticks) | QRM alone |
| `cw4b_refusal_spells` | refusal spells | QRM alone |
| `cw4b_refused_flight` | refusals of migrants fleeing war, famine or persecution (hunger excluded) | QRM alone |
| `cw4b_refused_hunger` | refusals of hunger-driven migrants | QRM alone |

## Harm panel

The runner's fixed panel (population, treasury, food shortfall after relief, priced-out persons
and children (not recorded: retail off), famine and war deaths ("requires slice extractor"),
epidemic deaths, out-migration, wealth Gini, forest stand (not recorded: timber stock off))
beside each arm against its declared control (QRM - QR, QR - QC); plus, as secondary outcomes
beside the primaries:

| Id | Harm | Comparison | Source |
| --- | --- | --- | --- |
| `cw4b_h_food_shortfall` | food shortfall after relief over the run | QRM - QC | harm panel `food_shortfall` |
| `cw4b_h_out_migration` | agents moving between regions over the run | QRM - QC | harm panel `out_migration` |
| `cw4b_h_population` | population at the end | QRM - QC | harm panel `population` |
| `cw4b_h_treasury` | treasury at the end | QRM - QC | harm panel `treasury` |
| `cw4b_h_partner_population`, `cw4b_h_partner_treasury` | partner civs (closed against at any decision) at the end | QRM - QC | rules `closures[*].target`, `civ_stats` |
| `cw4b_h_forgone` | route income forgone, both sides | QRM alone (structurally 0 in QC) | rules `totals.forgone_income` |
| `cw4b_h_forgone_trade` | route income forgone, both sides | QR alone | rules `totals.forgone_income` |
| `cw4b_h_unwinds` | merchant unwinds, world | QRM - QC | `metadata.merchant_trip_stats[*].unwind_count` |
| `cw4b_h_leaked` | deliveries still crossing a closed pair | QRM alone | rules `totals.leaked_deliveries` |
| `cw4b_h_enforcement` | enforcement paid | QRM - QC | rules `totals.enforcement_paid` |

The refused migrants themselves (refusals, spells, flight, hunger) are the channel's direct
harm (secondary outcomes above). Also kept per row (not outcomes): closing and partner civ
counts, closures opened, closed pair-turns, route-turns removed, merchant edges cut, replans,
stalled trips, turns with refusals, reported death share.

**Structural zeros versus unknowns.** The migration measures are `None` outside QRM;
`leaked_deliveries` is `None` in QC (nothing closes). A missing epidemics, quarantine,
region-control, civ-stats, merchant-stats or regional-population record, a rules record with
another mode or channels than the arm's, an unobserved migration receipt, a migration total that
disagrees with its receipts, or a missing total is a missing outcome: the run fails (rc 3) and is
reported as failed.

## Extractor validation (development worlds only, before the pilot)

Development runs of all three arms on every development world, `--cohort dev`, 200 turns:
template 1, 3, 7, 9, 11, 23, 42 and procedural 7, 11, 13, 17, 21, 31 (7 runner invocations of
world pairs with `--keep-first`, so every bundle was kept): 39 runs, 0 failed, every outcome
extracted, `check --metrics ... --cohort dev` passes for each. QR and QRM activated on all 13
worlds. An independent checker (outside the repository,
`/home/user/evidence/cw4b/validate/validate_cw4b.py`, reading the raw bundles, not importing the
screen module) passed every check on all 39 bundles (559 checks, 0 failures):

- every snapshot's rules record has the arm's mode and channels; receipt and regional-population
  dating are s - 1;
- the world arrivals equal the raw count of cross-polity arrival events; the per-turn epidemic
  deaths sum to `deaths_total` and to the extractor's value; the death rate equals 1,000 x deaths
  over the summed regional counts;
- `closures_opened` equals the distinct closure ids seen in the snapshots;
- QRM: every receipt observed; the receipts sum to the refusal total and to the extractor's
  value; the refusal rows sum to it; flight and hunger recomputed from the rows' drivers equal
  the totals and the extractor's values; the refusal spells equal the sum of the receipts' new
  spells and never exceed the refusals; every refusal row names a closure open in that snapshot;
  activation equals "a closure opened and a migrant refused";
- QC and QR: no migration total, no migration receipt field, migration measures `None`;
- **the channel acts as declared**: in QRM, 0 agent migrations (`history[*].migration`) crossed a
  pair closed at that snapshot (controllers at the end of the turn), against 9,274 in QR over
  the same 13 worlds.

`tests/test_cw4_screen.py` covers CW4b's arms, the refusal totals and their receipt checks, the
channel checks, the structural `None`s and activation on constructed bundles. `check --screen
CW4b` passes.

## Timing pilot (the shared pilot, on the frozen source)

`run PILOT --screen CW4b --cohort pilot --jobs 2` on `a732382e` (clean tree; `source.txt`: dirty
0, dirty-code 0): 6 runs, 0 failed, every outcome extracted (`check --metrics ... --cohort
pilot` passes); 71 s of simulation and extraction at 2 concurrent processes (load average about
2 on the shared 4-core machine). Mean seconds per run: template QC 6.3, QR 5.9, QRM 6.1;
procedural QC 18.2, QR 18.1, QRM 16.2. QR and QRM activated on both pilot worlds. **Projected
held run: 0.118 core-hours for 36 runs** (x1.5 = 0.177). The pilot's `metrics.jsonl`,
`source.txt` and `report.md` are retained in `connected-world-screens-cw4b/pilot/` (the held
run's `--pilot`). The report prints the pilot's outcomes; they were not read for any decision.

## Budget and stopping rules

- **Compute ceiling 0.5 core-hours** (the line above, read by the runner; the lead's
  Amendment 1, under the 2.0 cap; was 0.236, the pilot projection x 2); at most 3 concurrent
  processes; run with `--jobs 2` because other lanes share the 4 cores. The runner refuses a held run whose pilot projection x 1.5
  (0.177) exceeds the ceiling and starts no run that would pass it; runs not started are
  reported as `not run` (exit code 4), never as zeros. Held worlds slower than the pilot (the
  pilot ran on a lightly loaded machine) can therefore stop the run early; the stop is reported,
  and raising the ceiling needs the lead's amendment before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction
  (`--keep-first` keeps one world per stratum outside the repository for diagnosis).
- A failed run is reported as failed with its reason and is not replaced by another seed; a
  held-run failure that needs new worlds uses the program reserve through the lead
  (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `held-run.json`
  under `docs/superpowers/progress/connected-world-screens-cw4b/`), `check --metrics`, and
  `mark-run`, whose registry change is committed with the results.

## Amendments

**Amendment 1 (before any held run), 2026-11-06, the lead's review.** The compute ceiling is
0.5 core-hours (was 0.236, the pilot projection x 2): the pilot ran on a lightly loaded machine
and the machine is now heavily loaded by other lanes; 0.5 stays well under the 2.0 cap (the same
reasoning as CW4's Amendment 1). Nothing else changes: no arm, outcome, window, parameter, seed
or code (the screen module, extractors, registry content and native extension are those of
`a732382e`), so the pilot stays valid. No held seed had been run, and no held outcome was seen.

## Results (held run, 2026-11-06)

Read after the run; nothing below changed an arm, outcome or parameter, and no held seed was
rerun or tuned on. Full report: `connected-world-screens-cw4b/held/report.md` (every per-world
value of every outcome and harm), with `metrics.jsonl`, `source.txt` and `held-run.json`
beside it.

**Run.** `run HELD --screen CW4b --cohort held --pilot .../pilot/metrics.jsonl --jobs 2
--keep-first` on source `e89bf838` (the frozen code `a732382e` plus this page, its pilot files
and Amendment 1; `git diff --stat a732382e e89bf838` touches only those; dirty 0). Started
23:24:31Z, finished 23:27:46Z: **36 runs, 0 failed, complete, every outcome extracted**;
**0.107 core-hours** of simulation and extraction (ceiling 0.5; the pilot projected 0.118),
195 s of wall time at 2 processes. `check --cohort held` passes; `mark-run` recorded
`cw4b-held-t` and `cw4b-held-p` as run (36 rows, complete) in `scripts/seed_registry.json`.
Identities: run digest `a4f31b13…`; native `e724072d…`; runner `41330176…`; screen module
`3567a33b…`; registry content `a703a850…`; preregistration `01d3f16f…` (this page as amended).
Mean seconds per run: template 6.0-6.2, procedural 15.4-15.5.

**Activation (before any effect).** QR and QRM activated on 6 of 6 worlds in both strata (QC is
the root). QRM opened 18-83 closures per template world and 323-516 per procedural world and
refused migrants on 14-161 of 200 turns.

Uncertainty below is descriptive (six worlds per stratum): the mean, min/max, sign counts
(> 0 / < 0 / = 0) and how many of the 64 sign assignments of the per-world differences give a
mean at least as far from zero as the observed one (2 of 64 is the most extreme possible). Not
significance tests.

### Primary outcomes (QRM - QC, whole run, world level)

| Outcome | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign flips at least as extreme (of 64) |
| --- | --- | --- | --- | --- | --- |
| `cw4b_world_arrivals` | template | 3101 -14, 3102 -16, 3103 +2, 3104 +9, 3105 -5, 3106 -12 | -6.0 [-16, +9] | 2 / 4 / 0 | 12 (means ±9.67) |
| `cw4b_world_arrivals` | procedural | 3201 -49, 3202 -99, 3203 -22, 3204 -9, 3205 +34, 3206 -34 | -29.8 [-99, +34] | 1 / 5 / 0 | 12 (means ±41.2) |
| `cw4b_world_death_rate` (per 1,000 person-turns) | template | -0.827, -2.457, +0.751, -2.792, -0.175, -1.266 | -1.128 [-2.792, +0.751] | 1 / 5 / 0 | 6 (means ±1.378) |
| `cw4b_world_death_rate` | procedural | -0.187, -2.242, -0.643, -0.724, +3.870, -1.748 | -0.279 [-2.242, +3.870] | 1 / 5 / 0 | 50 (means ±1.569) |

**Both primaries lean negative but neither is consistent enough to call an effect.** Closing
trade and migration had fewer cross-polity arrivals than cost_only in 9 of 12 worlds (4 of 6
template, 5 of 6 procedural; 12 of 64 sign assignments as extreme in each stratum) and a lower
world death rate in 10 of 12 (5 of 6 in each stratum). The template death rate is the most
consistent (6 of 64); the procedural death rate is a null (50 of 64: one world, 3205, +3.87
against five small negatives). Per-world differences are large in both directions.

### The migration channel's increment (QRM - QR) and the trade closure alone (QR - QC)

| Outcome | Stratum | Mean [min, max] | >0 / <0 / =0 | Sign flips (of 64) |
| --- | --- | --- | --- | --- |
| `cw4b_mig_world_arrivals` (QRM - QR) | template | -8.67 [-16, -2] | 0 / 6 / 0 | 2 |
| `cw4b_mig_world_arrivals` | procedural | -15.8 [-57, +27] | 2 / 4 / 0 | 18 |
| `cw4b_mig_world_death_rate` (QRM - QR) | template | -0.699 [-1.535, -0.349] | 0 / 6 / 0 | 2 |
| `cw4b_mig_world_death_rate` | procedural | -0.630 [-1.883, +0.691] | 1 / 5 / 0 | 10 |
| `cw4b_trade_world_arrivals` (QR - QC) | template | +2.67 [-7, +11] | 4 / 2 / 0 | 24 |
| `cw4b_trade_world_arrivals` | procedural | -14.0 [-42, +26] | 2 / 4 / 0 | 16 |
| `cw4b_trade_world_death_rate` (QR - QC) | template | -0.429 [-2.002, +1.179] | 3 / 3 / 0 | 26 |
| `cw4b_trade_world_death_rate` | procedural | +0.351 [-1.334, +4.364] | 2 / 4 / 0 | 62 |

Against the trade closure, closing migration too lowered cross-polity arrivals and the world
death rate on every template world (both 0 / 6 / 0, the most extreme of the 64 assignments) and
on 4 and 5 of 6 procedural worlds (18 and 10 of 64); world epidemic deaths (count) fell on 6 of 6
template worlds (-22.2 [-32, -9]) and 4 of 6 procedural (-22.0 [-85, +92], 36 of 64). The trade
closure alone was again a null on these new worlds (arrivals and death rate mixed, 16-62 of 64),
replicating CW4. So the migration channel carries what difference closure makes here, most
clearly in the template stratum; in the procedural stratum the direction holds on most worlds
with wide spread.

### Other secondaries (QRM - QC; template / procedural)

- Arrivals per 1,000 region-turns: -3.75 (2/4/0, 12 of 64) / -4.66 (1/5/0, 12 of 64), as P1.
- World epidemic deaths, count: -29.2 [-121, +18] (1/5/0, 6 of 64) / -22.8 [-223, +245] (1/5/0,
  40 of 64).
- Conditioned on each arm's own closures (selection): window arrivals -5.3 (2/4/0) / -17.8
  (2/4/0); window deaths per 1,000 person-turns -0.88 (1/5/0, 30 of 64) / -1.58 (0/6/0, 2 of 64);
  but the windows differ (-19.5 / +165.8 civ-turns: QRM's closures follow its own trajectory),
  so these compare different selections and are not effects.

### Migrants refused (QRM alone)

| Stratum | Refusals (person-ticks), mean [min, max]; total | Refusal spells; total | Flight (war, famine, persecution); total | Hunger-driven (food opportunity, material need); total |
| --- | --- | --- | --- | --- |
| template | 863 [100, 2,348]; 5,179 | 688 [99, 1,805]; 4,129 | 449 [76, 1,077]; 2,694 (52%) | 310 [21, 1,147]; 1,862 (36%) |
| procedural | 2,843 [830, 4,311]; 17,059 | 2,404 [745, 3,581]; 14,423 | 1,854 [613, 2,981]; 11,126 (65%) | 421 [79, 673]; 2,528 (15%) |

Most refusals are flight from war, famine or persecution (hunger-driven moves excluded); a
large hunger-driven share in template world 3106 (1,147 of 2,348). Refusal spells are 80-85%
of the refusals: many refused agents were refused on consecutive turns while the closure lasted.

### Harms

Beside the primaries (QRM - QC):

- **Food shortfall after relief over the run: more under QRM in 10 of 12 worlds**: +625
  [-916, +1,892] (5/1/0, 12 of 64) / +914 [-2,314, +2,712] (5/1/0, 18 of 64). The trade closure
  alone (QR - QC) also raised it (+561, 5/1/0, 4 of 64 / +218, 5/1/0, 50 of 64); the migration
  channel added +64 (4/2/0, 50 of 64) / +696 (4/2/0, 16 of 64) over QR.
- Agents moving between regions: -17 (2/4/0, 58 of 64) / -1,126 (1/5/0, 4 of 64); against QR,
  fewer on 6 of 6 template worlds (-448, 2 of 64) and 5 of 6 procedural (-752, 4 of 64): the
  refused moves did not happen and were not replaced.
- Population at the end: +34 (5/1/0, 18 of 64) / +15 (4/2/0, 52 of 64); against QR +28.5
  (5/1/0) / +68.7 (5/1/0, 4 of 64). Treasury at the end: -313 (3/3/0) / +1,454 (5/1/0, 4 of 64).
- Partner civs (closed against at any decision): their population and treasury at the end
  equal (template) or nearly equal (procedural) the world totals, because every or nearly every
  civ was closed against at some decision (3-4 of 4 template, 8-10 of 10 procedural): no
  separate externality is measurable here.
- Route income forgone, both sides: QRM 376 [160, 800] / 2,982 [1,420, 4,628]; QR alone 389 /
  1,980. Merchant unwinds: +23.3 (6/0/0, 2 of 64) / +206 (6/0/0, 2 of 64). Deliveries still
  crossing a closed pair (QRM): 5 [0, 17] / 115.5 [36, 175] per run. Enforcement paid: -4.7
  (3/3/0) / +358 (4/2/0).
- Wealth Gini: mixed. Not recorded in these runs: priced-out persons and children (retail off),
  forest stand (timber stock off). No bundle field: famine and war deaths ("requires slice
  extractor"): the deaths of refused migrants who stayed in famine regions are therefore not
  separated from other deaths, which the food-shortfall harm only bounds.

No world failed, none was incomplete, and no outcome was missing. These are whole-trajectory
comparisons on six worlds per stratum: they describe the direction and spread on held worlds,
not a mechanism, and they do not license promotion (the owner's decision).
