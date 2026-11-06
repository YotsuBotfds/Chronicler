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
