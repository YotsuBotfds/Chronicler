# Connected-world CW1: preregistered held screen for the wage and `paid_work` enrollment (slice S1)

Status: FROZEN at `4a79b7f55f794f78d31eb772bf950356df4c83cb` (Amendment 1, the lead's review; first frozen at `81392e8b`: the screen module, runner, extractors and simulation source the re-validation and the rerun timing pilot ran on)

Written 2026-11-06 by the S1 lane on branch `claude/cw-s1-accounting` (the S1 integration of
A1 wealth accounting and A2R retail cohorts, with `main` `8286804c` merged). The native
extension is the shared build
`101a4cd5b928b14f43539f925fa565036b94e38d91b9698071c80fa3656e0df3`; S1 changed no Rust. No held
seed (template 731-736, procedural 831-836) has been run. Code may change before the held run
only to fix a defect, recorded as an amendment below with a new pilot; no arm, outcome,
region set or parameter changes in response to held outcomes.

The S1 integration review's fixes landed before the freeze (`52b5730e`-`41f99b48`): the
schedule option's help, the viewer's schedule wording, a runner test's path rule, and the RL4
cut counting the commons net of merchants' committed grain, as the native cap does. That last
change can alter a retail-v2 world only where merchants hold committed grain in a market above
its cap; a 120-turn probe (procedural 13, boundary `all`, the CP3 base and chain, grain convoys,
the ledger) before and after it was byte-identical apart from the bundle's timestamp (81 cut
frames, none with committed grain).

Compute ceiling: 1.46 core-hours

Primary outcomes: cw1_p1_wage_money, cw1_p2_enrollment_money, cw1_p3_wage_priced_out

## Purpose and limits

AUDIT-A1-A2 section 4: under the `paid_work` boundary a region enrolls in retail one turn
after its first paid crew, so in checkpoint 3 the treatment (paying PL3 granary crews) also
decided which regions were priced (paid enrollment was 1.3-2.0x the unpaid arm's on the
development worlds). CW1 separates the two: **the wage at a fixed enrollment** (A - C, the
same pilot schedule with and without the wage) and **the enrollment without the wage** (C -
B, A's schedule against B's own, both unpaid), with the money households receive measured by
the A1 ledger's typed channels rather than reconstructed.

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip
  enumeration, not significance tests.
- Hybrid worlds only. Trajectories diverge once the wage changes treasuries and households
  (different wars, migrations, later projects), so every measure is a property of the whole
  trajectory, not a mechanism estimate. A replay holds enrollment fixed only where the
  replaying world still controls the scheduled region (the schedule boundary keeps the
  controller filter): a world whose replay is not exact is reported as not activated.
- **Prediction (development worlds, AUDIT-A1-A2 section 4.3, inferred):** at a fixed
  enrollment the wage raises money credited to households (5 of 5 development worlds at
  either schedule); enrollment without the wage lowers it in procedural worlds (more farm
  income replaced); the wage's effect on priced-out persons is small and mixed, because the
  wage reaches adult farm owners, who are rarely priced out, while enrollment exposes
  non-farm adults and children without a co-resident adult. A null result is a result.

## Units, cohorts and source

- **Units:** worlds (seeds). Every arm runs once on every world and is compared with its
  declared control on the same world, per stratum: template (8 regions, 4 civs) and
  procedural (32 regions, 10 civs, `--worldgen procedural --regions 32 --civs 10`).
- **Held cohort:** template 731-736, procedural 831-836 (`scripts/seed_registry.json`,
  reserved for CW1; the runner refuses any other seed). **Timing pilot:** the shared pilot,
  template 5 and procedural 19 (never evidence).
- **Base flags (every arm):** checkpoint 3's base, `--turns 200 --agents hybrid
  --simulate-only --grain-reserves --public-grain-shipments --scholarship --techniques
  --academy-services --grain-storage --food-allocation --workshops --operating-wear
  --repair-projects --timber-stock` (`productive_recovery_screens.CP3.BASE`), then
  `--household-retail --household-retail-rules 2` (retail rules version 2 in every arm) and
  `--wealth-accounting` (the A1 ledger, an observer: it changes no byte of the simulation,
  verified on S1 by the observer identity, 205 files, 0 differences).
- `CHAIN = --timber-supply --recovery-crews --remittances`; `UNPAID = --timber-supply
  --recovery-crews --recovery-crew-mode unpaid --remittances` (PL3 granary crews named,
  reserved and withheld identically but paid nothing; PL1 woodcutters and RS2 workshop crews
  are paid in both).
- **Arms** (root B; each arm's control in the last column):

  | Arm | Label | Flags after the base | Control |
  | --- | --- | --- | --- |
  | A | `CH@pw` | `--household-retail-boundary paid_work` + CHAIN | C |
  | B | `U@pw` | `--household-retail-boundary paid_work` + UNPAID | root |
  | C | `U@S_A` | `--household-retail-boundary schedule --household-retail-schedule S_A` + UNPAID | B |
  | D | `CH@S_B` | `--household-retail-boundary schedule --household-retail-schedule S_B` + CHAIN | B |
  | E | `CH@all` | `--household-retail-boundary all` + CHAIN | F |
  | F | `U@all` | `--household-retail-boundary all` + UNPAID | B |
  | G | `CH@mkt` | `--household-retail-boundary market` + CHAIN | H |
  | H | `U@mkt` | `--household-retail-boundary market` + UNPAID | B |
  | CH_noTS | CHAIN without timber supply | `--household-retail-boundary paid_work --recovery-crews --remittances` | A |

- **Runner:** `scripts/connected_world_screens.py` on `scripts/screen_runner.py`. Command,
  once the lead agrees: `PYTHONPATH=<checkout>/src <native python>
  scripts/connected_world_screens.py run OUT --screen CW1 --cohort held --pilot
  docs/superpowers/progress/connected-world-screens-cw1/pilot/metrics.jsonl --jobs 2`, then
  `report`, `check --metrics ... --cohort held` and `mark-run`.
- **Identity (the extractors live in the screen module; Amendment 1):** source `4a79b7f5`
  (code; the pilot ran on `9a9a050a`, which differs only in this page), dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `833c48cff8c9af33e7849370fce1a5cea4a2451db6781dd0b13dc1791040883a`; `scripts/screen_runner.py`
  `891b65475a07bb62e8108a693957569e68558b42e182a187528633e1baf0e4f5`; registry content
  `dc16f3c3b366699029de253da0a04d90394530b002ba3203b0e29b17ef7a98f8`; native extension
  `101a4cd5…`. A held run whose
  `source.txt` differs in any of these (apart from the source revision outside the code and
  the preregistration line the runner adds) is not this screen.

## The two phases: frozen schedules

S_A and S_B are functions of the world and of arm A or B only. The runner (`SR.Derived`,
added by S1 to E1's runner; docs/integration/connected-world-screens.md section 2) runs A and
B first on each world. From each one's bundle it extracts the arm's **exact pilot
intervals** (`household_retail.extract_schedule`: the last retail record's `intervals`,
checked against every completed-turn frame and against `opened_turn`; an approximate,
frame-derived schedule is refused), writes them as the canonical schedule JSON
(`{"<region>": [[open, close], ..., [open, null]]}`, compact, ascending region) read-only to
`OUT/derived/S_A-<world>.json`, and records its SHA-256 in A's row, `OUT/derived.jsonl`,
`source.txt` and the held-run ledger (`output/held-runs/ledger.jsonl`) **before C or D
starts on that world**. C's and D's command lines name the frozen file; the runner hashes it
again before each run, and the replaying run records the schedule's digest in its own retail
state (`schedule.sha256`), which the extractor compares with the file. A failed A or B fails
C or D on that world (not run).

## Activation and validity (reported per world before any effect)

- **A, D, E, G, CH_noTS (paid):** activated when the arm enrolled (`pilot_region_turns > 0`)
  and paid granary crew wages over the run (the ledger's `granary_crew_wage` channel > 0).
- **C, F, H (unpaid):** activated when the arm enrolled and paid **no** granary crew wage.
- **C, D (schedule):** also require an **exact replay**: the intervals the run recorded equal
  the schedule it was given, region by region, and their digest equals the schedule's.
- **B:** the root (its enrollment is shown in the validity table and is D's schedule).
- A comparison needs its arm **and its control** activated (unless the control is the root;
  `control_activation`), so A - C needs C's exact replay and D - B needs D's. A world where
  either did not act is shown as `not activated` and left out of that comparison, never
  counted as zero.
- The screen's validity table lists per world and arm: regions in the set, pilot region-turns,
  granary crew and woodcut wages, unlocated wages and remittances, and the schedules made or
  replayed with their digests and the replay result.

## Definitions

Money is in wealth units (the native balance; the ledger's milli-units / 1000). A snapshot
labelled s records completed turn s - 1; the retail record, the ledger record and the ledger
frame must all carry that turn (else the run fails). Sums run over every snapshot of the
200-turn run.

- **Region set of an arm.** For C and D: the regions their schedule names (S_A, S_B). For
  every other arm: every region it ever enrolled (its recorded intervals). Because C replays
  S_A exactly (activation), A's set and C's set are both S_A, and D's and B's are both S_B.
- **Money credited to households (P1, over a region set R; Amendment 1):**

  ```
  money_set(R) = sum_s sum_{r in R} ( WA.frame.regions[r].typed_in_milli
                                      - round(HR.regions[r].provisioning.credited_milli) ) / 1000
                 - sum_s sum_{r in R} HR.regions[r].income_replaced
  ```

  `WA` is `history[s].livelihoods.wealth_accounting`, `HR` is
  `history[s].livelihoods.household_retail`. The ledger locates each typed inflow in the
  payee's region; a region's located inflow less its retail sales (the `food_purchase`
  credit the ledger locates there from the same provisioning row) is exactly the wages
  (`workshop_wage`, `apprentice_stipend`, `repair_wage`, `granary_crew_wage`, `woodcut_wage`)
  and remittances credited there. Procurement credits are left out (Amendment 1): the ledger
  does not locate them, and an owner who moved away keeps the claim, so some reach households
  outside R; procurement credited is a world secondary. Farm income replaced is L6b's
  per region (no money moves). The extractor checks, every turn, that the located inflows
  less retail sales equal the ledger's located non-sale channels, that no region's inflow is
  below its sales, and that the frames' income replaced equals the ledger's
  `withheld.retail_income_replaced`; wages or remittances the ledger could not locate (PL3
  receipts dropped by a row cap) are kept per run (`money_unlocated`, shown in the validity
  table).
- **Money credited to households, world (P2 and the world comparisons):**

  ```
  money_world = sum_s [ sum_{c in wage channels} WA.frame.typed[c].in_milli
                        + WA.frame.typed[remittance].in_milli
                        + WA.frame.typed[food_procurement].in_milli ] / 1000
                - sum_s WA.frame.withheld.retail_income_replaced
  ```

  Wages + remittances credited + procurement credited - farm income replaced, every region.
- **Pilot person-turn:** a person provisioned in a pilot region-turn
  (`provisioning.persons`). **Priced-out rate over R:** `sum provisioning.priced_out_persons
  / sum provisioning.persons` over R's provisioned region-turns (a region-turn without a
  provisioning row is unobserved and left out of both). Only pilot regions price anyone out.
- **Mean ration:** `sum provisioning.rations / sum provisioning.persons` over R.
- **Coverage:** pilot region-turns (`counters.pilot_region_turns`) per region-turn
  (regions x turns).
- **RL5 household groups** (A2R; per provisioned region-turn, exact or null): crew
  households (`crew` + `crew_children`: crew members and their co-resident children),
  non-farm adults (`nonfarm_adults`), children without a co-resident adult
  (`children_alone`). A group's **rate** is its priced-out person-turns over its person-turns
  on the region-turns where both are exact (a region-turn where someone died before
  provisioning has unknown group persons: left out, counted per run, never zero); its
  **count** is its priced-out person-turns (unknown when any is null). The groups' priced-out
  persons must sum to the provisioning row's when all are exact (else the run fails).

## Primary outcomes

1. `cw1_p1_wage_money`: money credited to households over S_A (wages and remittances located
   there, less farm income replaced there), **A - C** (the wage at A's enrollment).
2. `cw1_p2_enrollment_money`: money credited to households, world, **C - B** (A's enrollment
   against B's own, no wage).
3. `cw1_p3_wage_priced_out`: priced-out person-turns per pilot person-turn over S_A, **A -
   C**.

Region sets. P1 and P3 hold enrollment fixed (C replays S_A exactly), so they are read over
S_A: money credited outside it (remittances into never-enrolled regions, wages paid in a
region before it opens) and procurement credits (Amendment 1) are left out of P1 and reported
in the world version (`cw1_sa_money_world`, with procurement) and `cw1_sa_procurement`. P2
compares two different enrollments; a region-restricted measure
would condition on B's own enrollment, so P2 is the world total (every household's receipts;
farm income is replaced only in pilot regions, so the difference is the extra enrollment's
replaced income plus any change in wages, remittances and procurement anywhere).

## Secondary outcomes

| Id | Measure | Comparison |
| --- | --- | --- |
| `cw1_sa_money_world` | money credited, world | A - C |
| `cw1_sa_wages`, `cw1_sa_granary_wages`, `cw1_sa_remittances`, `cw1_sa_procurement` | the money terms, world: wages (all channels), granary crew wages, remittances, procurement credited | A - C |
| `cw1_sa_income_replaced` | farm income replaced over S_A | A - C |
| `cw1_sa_priced_out`, `cw1_sa_ration` | priced-out person-turns; mean ration over S_A | A - C |
| `cw1_sb_money`, `cw1_sb_priced_out` | money credited over S_B; priced-out rate over S_B (the wage at B's enrollment) | D - B |
| `cw1_interaction_money`, `cw1_interaction_priced_out` | (A - C) - (D - B): the wage at S_A against the wage at S_B, each over its own schedule's set | difference of differences |
| `cw1_all_money`, `cw1_all_priced_out`, `cw1_all_ration` | money credited, world; priced-out rate and mean ration over each arm's own enrollment (the wage at the fixed universal cohort) | E - F |
| `cw1_mkt_money`, `cw1_mkt_priced_out` | the same at the fixed capital cohort | G - H |
| `cw1_total_money`, `cw1_total_priced_out` | the total effect (checkpoint 3's `CH - CH_unpaid`), money world; priced-out rate over each arm's own enrollment | A - B |
| `cw1_coverage_enrollment`, `cw1_coverage_total` | coverage | C - B, A - B |
| `cw1_enrollment_priced_out`, `cw1_enrollment_income_replaced` | priced-out person-turns; farm income replaced, world | C - B |
| `cw1_rl5_sa_<group>_rate` (crew, nonfarm, children_alone) | RL5 group priced-out rates | A - C |
| `cw1_rl5_sb_<group>_rate` | RL5 group priced-out rates | D - B |
| `cw1_rl5_sa_<group>_count` | RL5 group priced-out person-turns | A - C |
| `cw1_nots_money`, `cw1_nots_priced_out`, `cw1_nots_coverage` | RL6, the expedition-labour control: money world, priced-out rate (own enrollment), coverage | CH_noTS - A (the negative of CH - CH_noTS; the runner pairs an arm with a control on its chain) |

Also kept per row (not outcomes): the region set, pilot region-turns, every wage channel,
income replaced (world and set), located inflows in the set, unlocated wages and remittances,
unobserved and unprovisioned turns, RL5 unknown region-turns, the ledger's continuity, failed
closures and incomplete turns, and the replay record (given, recorded and file digests,
differing regions).

## Harm panel

The runner's fixed panel beside every comparison (each arm against its declared control, and
A - B, C - B as outcomes declare): population, treasury, food shortfall after relief,
priced-out persons and children, epidemic deaths, out-migration, wealth Gini, forest stand;
famine and war deaths read "requires slice extractor" (no bundle field). With
`control_activation` a harm pair also needs both arms activated.

**Structural zeros versus unknowns.** Unpaid arms pay no granary wage (a structural zero,
checked by activation). A region-turn without a provisioning row, a ledger frame that is
null, and an RL5 group with null persons are unknown, never zero. A ledger frame missing beside
retail frames, an incomplete typed record, a retail record not in rules 2 or not in the arm's
boundary, mismatched turns, missing RL5 cohorts, or any of the identities above failing is a
missing outcome: the run fails (rc 3) and is reported as failed.

## Extractor validation (development worlds only, before any pilot)

**Record run, on the frozen code.** `run DEV --screen CW1 --cohort dev --worlds
t1,t3,t7,t9,t11,t23,t42,p7,p11,p13,p17,p21,p31 --jobs 2 --keep-first` at 200 turns on
`81392e8b` (dirty 0; screen module `fa7e15c7…`, runner `891b6547…`): **117 runs, 0 failed,
every outcome extracted**, 0.564 core-hours, 1,025 s of wall time.

- **Activation.** Template 9 had no granary project in any arm (no PL3 wage), so A, C, D, E,
  G and CH_noTS are not activated there; on template 1 B enrolled no region, so S_B is empty
  and D is not activated. Every other arm activated on every world (A 12/13, C 12/13, D
  11/13, E 12/13, F 13/13, G 12/13, H 13/13, CH_noTS 12/13).
- **Replays.** All 26 schedule replays (C and D on 13 worlds) were exact; A and C had equal
  pilot region-turns on 13 of 13 worlds.
- **Ledger.** On every run: no unobserved ledger or retail turn, no unprovisioned frame, no
  broken continuity, no failed closure, no incomplete typed turn, and no wage or remittance
  the ledger could not locate (`money_unlocated` 0), so P1's set restriction lost nothing.
  The per-turn identities in the extractor (located inflows less sales equal the non-sale
  located channels; frames' income replaced equals the ledger's; RL5 groups sum to the
  provisioning row) held on every turn of every run.
- **RL5.** 11.4% of provisioned region-turns have unknown group persons (someone died before
  provisioning); the group rates leave them out and count them per run.

**Independent check.** A checker outside the repository
(`/home/user/evidence/s1/cw1/validate/validate_cw1.py`) read the 18 kept raw bundles
(procedural 7 and template 1, every arm) and recomputed the measures from the packages' own
records, not from the ledger: **46,505 checks, 0 failures.**
- `money_world` and `money_set` from PL3 granary, RS2 and PL1 receipts, RS4 regions and
  totals, retail procurement credits and income replaced equal the extractor's
  ledger-based values (relative 1e-6).
- Priced-out persons, persons and rations equal the frames'. The retail sample's priced-out
  rows equal the frames' on every turn whose whole sample the snapshot kept.
- The RL5 counts and partition match. Unpaid arms paid no granary wage. The frames' count
  equals `pilot_region_turns`. Every turn carries the snapshot's dated turn, rules 2 and the
  arm's boundary, and CH_noTS records no timber supply.
- Each derived schedule's bytes are the canonical JSON of its source's final intervals, with
  the recorded SHA-256, which C's and D's records carry as `schedule.sha256`.
- **Replay, region by region and turn by turn:** C's pilot regions equal A's on every turn
  (p7 2,411, t1 534 region-turns), and D's equal B's (p7 1,240; t1 0).

**An earlier exploratory pass** on `1ec40cc2` (not a record: the S1 review fixes were edited
into `src/` while it ran) found one defect, fixed before the record run in `e8a86af7`: each
frame's income replaced and the world total are rounded to 1e-6 apiece, and the cross-check's
1e-6 tolerance failed 4 runs. The pass also showed the source-failure path: A failed on t42,
so C t42 was not run (`not run: derived S_A for t42 is unavailable`).

`tests/test_cw1_screen.py` (24 tests) covers the declaration, the derived declarations, every
formula on constructed bundles, eight refusals of inconsistent records, unknown RL5 persons,
activation, schedule making and replay, and the runner's two phases with a fake runtime: the
order, the frozen files and their digests in `derived.jsonl`, `source.txt`, the rows and the
held-run ledger, a failed source, an inexact replay, `--arms` without the source, resume,
and a changed file. `check --screen CW1` passes.

## Timing pilot (the shared pilot, on the frozen source)

Rerun after Amendment 1 on `9a9a050a` (the amended code `4a79b7f5` plus this page; clean tree;
the first pilot, on `81392e8b`, is refused by the changed screen module and is superseded):
`run PILOT --screen CW1 --cohort pilot --jobs 2`, **18 runs, 0 failed, every outcome
extracted** (`check --metrics ... --cohort pilot` passes); 438 s of simulation and extraction
(0.122 core-hours), 224.2 s of wall time at 2 concurrent processes on the shared 4-core
machine, more loaded than for the first pilot (333 s). Every arm activated on both pilot
worlds; all 4 replays were exact. Mean seconds per run (simulation and extraction): template A
14.0, B 15.9, C 11.8, D 9.5, E 10.0, F 10.5, G 10.3, H 10.2, CH_noTS 8.5; procedural A 41.5,
B 34.4, C 44.0, D 35.8, E 41.4, F 33.9, G 38.4, H 34.9, CH_noTS 32.8. **Projected held run:
0.730 core-hours for 108 runs** (x1.5 = 1.095). The pilot's `metrics.jsonl`, `source.txt`,
`report.md`, `derived.jsonl` and derived schedules are retained in
`connected-world-screens-cw1/pilot/` (the held run's `--pilot`). The pilot's outcomes were not
read for any decision.

## Budget and stopping rules

- **Compute ceiling 1.46 core-hours** (the line above, read by the runner): the rerun pilot's
  projection (0.730) x 2, under the 2.0 cap (Amendment 1; first 1.11, from the superseded
  pilot's 0.555). At most 3 concurrent processes; run with `--jobs 2` because
  other lanes share the 4 cores. The runner refuses a held run whose pilot projection x 1.5
  exceeds the ceiling and starts no run that would pass it; runs not started are reported as
  `not run` (exit code 4), never as zeros. Raising the ceiling needs the lead's amendment
  before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction
  (`--keep-first` keeps one world per stratum outside the repository for diagnosis).
- A failed run is reported as failed with its reason and is not replaced by another seed; a
  held-run failure that needs new worlds uses the program reserve through the lead
  (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `derived.jsonl`
  and the derived schedules, and `held-run.json` under
  `docs/superpowers/progress/connected-world-screens-cw1/`), `check --metrics`, and
  `mark-run`, whose registry change is committed with the results.

## Amendments

**Amendment 1 (before any held run), 2026-11-06, the lead's review.** P1 was read over S_A but
added the world's procurement credits (`typed[food_procurement].in_milli`), which is
consistent only if every credit reaches a household in the set. **Check** (development worlds
only, arms A and C on all 13 worlds, 200 turns, the frozen source; outside the repository,
`/home/user/evidence/s1/cw1/validate/procurement_regions.py` wraps
`household_retail._credit_procurement` in-process and records each credited owner's region
from the agent snapshot at the credit; its totals equal the native receipts and the ledger's
channel on every run): every procured grain's source region was in the set (0 of 13,640
credit rows outside), but owners who had moved away keep their claims, so credits reached
households outside the set: 6.1% of A's procurement credits (747 of 6,994 rows; on 7 of 13
worlds, up to 18.5% on procedural 17) and 4.7% of C's (601 of 6,646 rows; 6 worlds, up to
14.1%). The condition does not hold, so **P1 leaves procurement out**, as do `cw1_sb_money`
and `cw1_interaction_money`, which read the same measure (the formula above); procurement
credited stays a world secondary (`cw1_sa_procurement`) and is still in `money_world` (P2).
Code: `4a79b7f5` (the screen module only).

*Re-validation* on `4a79b7f5` (development worlds procedural 13 and template 23, chosen because
they had procurement credits outside the set; 200 turns, every arm, `--keep-first`): 18 runs,
0 failed, every arm activated, 4 of 4 replays exact; the independent checker (its `money_set`
also without procurement) passed 49,685 checks with 0 failures, and `tests/test_cw1_screen.py`
was updated to the new formula. The other definitions, the arms and the extractor's checks are
unchanged, so the 13-world record run above stands for them (its P1 values used the old
formula).

*Pilot and ceiling.* The screen module changed (SHA-256 `833c48cf…`), so the pilot was rerun
(above) and the ceiling recomputed by the same rule: the rerun pilot's projection x 2, 1.46
core-hours (the machine was busier than for the first pilot). No held seed had been run, and
no held outcome was seen.

## Results (held run, 2026-11-06)

Read after the run; nothing below changed an arm, outcome or parameter, and no held seed was
rerun. Full report: `connected-world-screens-cw1/held/report.md` (every per-world value of
every outcome and harm, the activation and validity tables), with `metrics.jsonl`,
`source.txt`, `held-run.json`, `derived.jsonl` and the 24 frozen schedules beside it.

**Run.** `run HELD --screen CW1 --cohort held --pilot .../pilot/metrics.jsonl --jobs 2
--keep-first` on source `2353ac0a` (the frozen code `4a79b7f5` plus this page's re-freeze
and the rerun pilot's files; dirty 0). Started 22:24:53Z, finished 22:42:34Z: **108 runs, 0
failed, complete, every outcome extracted**; **0.584 core-hours** of simulation and
extraction (ceiling 1.46; the pilot projected 0.730), 1,061 s of wall time at 2 processes.
`check --cohort held` passes; `mark-run` recorded `cw1-held-t` and `cw1-held-p` as run (108
rows, complete) in `scripts/seed_registry.json`. Identities: run digest `1be6247d…`; native
`101a4cd5…`; runner `891b6547…`; screen module `833c48cf…`; registry content `dc16f3c3…`;
preregistration `81701ebf…` (this page as re-frozen, before this section). Mean seconds per
run: template 10.1, procedural 28.8.

**Activation and validity (before any effect).**
- A, C, D, E, G and CH_noTS activated on 5 of 6 template worlds and 6 of 6 procedural; F and H
  on 12 of 12. **Template 734 had no paid work of any kind** (no granary project, no
  woodcutting crew): A and B enrolled no region, S_A and S_B are empty, and no arm paid a
  granary wage, so every comparison involving a paid arm or C or D leaves it out (template n =
  5).
- **All 24 schedule replays were exact** (C and D on 12 worlds), and A and C had equal pilot
  region-turns on 12 of 12 worlds. A enrolled 1.4-1.8 times B's pilot region-turns on template
  worlds and 1.6-3.4 times on procedural (coverage A 0.51-0.66 against B 0.29-0.44 template,
  0.38-0.49 against 0.14-0.25 procedural): payment decided enrollment, as the audit found.
- The ledger observed every turn of every run: no broken continuity, failed closure or
  incomplete typed turn, and no wage or remittance it could not locate (P1 lost nothing to the
  set restriction). 12.3% of provisioned region-turns have unknown RL5 group persons.

### Primary outcomes

| Outcome | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign flips at least as extreme |
| --- | --- | --- | --- | --- | --- |
| `cw1_p1_wage_money` | t | 731 +264.6, 732 -138.6, 733 +120.5, 734 not activated, 735 +320.4, 736 +282.9 | +170 [-138.6, +320.4] | 4 / 1 / 0 | 6 of 32 (means ±225.4) |
| `cw1_p1_wage_money` | p | 831 +486.1, 832 +645.4, 833 +774.4, 834 +922.4, 835 +1015, 836 +775.4 | +769.7 [+486.1, +1015] | 6 / 0 / 0 | 2 of 64 (means ±769.7) |
| `cw1_p2_enrollment_money` | t | 731 -500.7, 732 -616.1, 733 -346, 734 not activated, 735 -917.7, 736 -636.2 | -603.3 [-917.7, -346] | 0 / 5 / 0 | 2 of 32 (means ±603.3) |
| `cw1_p2_enrollment_money` | p | 831 -1666, 832 -1655, 833 -2574, 834 -4367, 835 -1079, 836 -1564 | -2151 [-4367, -1079] | 0 / 6 / 0 | 2 of 64 (means ±2151) |
| `cw1_p3_wage_priced_out` | t | 731 +3.606e-05, 732 +0.002916, 733 -0.0001044, 734 not activated, 735 -0.0003302, 736 -0.0001539 | +0.0004727 [-0.0003302, +0.002916] | 2 / 3 / 0 | 30 of 32 (means ±0.0007081) |
| `cw1_p3_wage_priced_out` | p | 831 +0.0001766, 832 +0.0002324, 833 -0.0008161, 834 +0.004158, 835 -0.0004539, 836 -9.782e-05 | +0.0005331 [-0.0008161, +0.004158] | 3 / 3 / 0 | 52 of 64 (means ±0.0009891) |

- **P1, the wage at A's enrollment:** money credited to households over S_A rose in every
  procedural world (+486 to +1,015 wealth units over 200 turns; none of the 64 sign
  assignments is more extreme) and in 4 of 5 template worlds (mean +170; 732 -139). The
  granary wages themselves (`cw1_sa_granary_wages`, +169 template, +885 procedural) account
  for most of it; farm income replaced over S_A moved both ways.
- **P2, A's enrollment without the wage:** money credited to households fell in every world
  (template -603, procedural -2,151; each the most extreme assignment): the larger enrollment
  replaced more farm income (`cw1_enrollment_income_replaced` +358 template, +1,848
  procedural) and paid nothing for it.
- **P3, the wage and priced-out persons at A's enrollment:** no consistent effect: 2 higher and
  3 lower template worlds, 3 and 3 procedural; the means (+0.00047 and +0.00053 per pilot
  person-turn) come from one world each (732, 834); 30 of 32 and 52 of 64 sign assignments are
  at least as extreme.

### Secondary outcomes

Each cell: the mean [min, max] of the per-world differences, the count above / below /
at zero, and how many sign assignments are at least as extreme (n < 6: worlds left out as not
activated or unknown, named in the report).

| Outcome | Comparison | Template: mean [min, max] +/-/0, sign flips | Procedural |
| --- | --- | --- | --- |
| `cw1_sa_money_world` | A - C | +173.8 [-166.6, +321.6] 4/1/0, 4/32 (n=5) | +761.6 [+389.6, +1074] 6/0/0, 2/64 |
| `cw1_sa_wages` | A - C | +151 [+83.71, +217.9] 5/0/0, 2/32 (n=5) | +876.9 [+344.1, +1302] 6/0/0, 2/64 |
| `cw1_sa_granary_wages` | A - C | +168.9 [+93.36, +244] 5/0/0, 2/32 (n=5) | +884.7 [+425, +1279] 6/0/0, 2/64 |
| `cw1_sa_remittances` | A - C | +21.55 [-17.13, +48.23] 4/1/0, 6/32 (n=5) | +86.78 [-50.98, +324] 4/2/0, 18/64 |
| `cw1_sa_procurement` | A - C | -3.8 [-11, +2] 2/3/0, 8/32 (n=5) | -2.667 [-16, +4] 2/4/0, 38/64 |
| `cw1_sa_income_replaced` | A - C | -5.046 [-210.1, +287.5] 2/3/0, 32/32 (n=5) | +199.4 [-565, +885.8] 5/1/0, 22/64 |
| `cw1_sa_priced_out` | A - C | +12 [-11, +76] 2/3/0, 30/32 (n=5) | +47.33 [-52, +344] 3/3/0, 52/64 |
| `cw1_sa_ration` | A - C | -0.01264 [-0.02921, +0.003902] 1/4/0, 6/32 (n=5) | -0.01077 [-0.0258, +0.0008261] 1/5/0, 4/64 |
| `cw1_sb_money` | D - B | +255 [+153.8, +443.7] 5/0/0, 2/32 (n=5) | +772.1 [+142.8, +1515] 6/0/0, 2/64 |
| `cw1_sb_priced_out` | D - B | -7.538e-05 [-0.0008186, +0.0002764] 2/1/2, 32/32 (n=5) | -1.559e-06 [-0.0001304, +0.000171] 3/2/1, 64/64 |
| `cw1_interaction_money` | A - C - (D - B) | -85.06 [-292.4, +78.39] 1/4/0, 8/32 (n=5) | -2.344 [-740.1, +779.6] 3/3/0, 64/64 |
| `cw1_interaction_priced_out` | A - C - (D - B) | +0.000548 [-0.0004303, +0.002916] 2/3/0, 22/32 (n=5) | +0.0005347 [-0.0009872, +0.004158] 3/3/0, 46/64 |
| `cw1_all_money` | E - F | +381.7 [+54.11, +711] 5/0/0, 2/32 (n=5) | +1080 [+208.6, +1978] 6/0/0, 2/64 |
| `cw1_all_priced_out` | E - F | -0.001448 [-0.003624, +0.0008178] 1/4/0, 6/32 (n=5) | -0.00339 [-0.007464, -0.00061] 0/6/0, 2/64 |
| `cw1_all_ration` | E - F | +0.01072 [-0.005736, +0.03329] 4/1/0, 6/32 (n=5) | +0.003682 [-0.009076, +0.01375] 4/2/0, 20/64 |
| `cw1_mkt_money` | G - H | +235.8 [-215.4, +582] 4/1/0, 8/32 (n=5) | +879.3 [+226.5, +1880] 6/0/0, 2/64 |
| `cw1_mkt_priced_out` | G - H | -0.0002621 [-0.002968, +0.001543] 3/2/0, 28/32 (n=5) | -0.000336 [-0.001376, +0.0007029] 2/4/0, 20/64 |
| `cw1_total_money` | A - B | -429.6 [-782.7, -176] 0/5/0, 2/32 (n=5) | -1389 [-3452, -4.283] 0/6/0, 2/64 |
| `cw1_total_priced_out` | A - B | +0.0004146 [-0.0009879, +0.002995] 3/1/1, 20/32 (n=5) | +0.001209 [-4.779e-05, +0.005055] 5/1/0, 4/64 |
| `cw1_coverage_enrollment` | C - B | +0.2269 [+0.1506, +0.2725] 5/0/0, 2/32 (n=5) | +0.1952 [+0.1498, +0.347] 6/0/0, 2/64 |
| `cw1_coverage_total` | A - B | +0.2269 [+0.1506, +0.2725] 5/0/0, 2/32 (n=5) | +0.1952 [+0.1498, +0.347] 6/0/0, 2/64 |
| `cw1_enrollment_priced_out` | C - B | +1.8 [+0, +4] 3/0/2, 8/32 (n=5) | +50.83 [+4, +155] 6/0/0, 2/64 |
| `cw1_enrollment_income_replaced` | C - B | +357.6 [+169.2, +694.3] 5/0/0, 2/32 (n=5) | +1848 [+1094, +3999] 6/0/0, 2/64 |
| `cw1_rl5_sa_crew_rate` | A - C | +0 [+0, +0] 0/0/5, 32/32 (n=5) | +0 [+0, +0] 0/0/6, 64/64 |
| `cw1_rl5_sa_nonfarm_rate` | A - C | +0.001184 [-0.001005, +0.007304] 2/3/0, 30/32 (n=5) | +0.001189 [-0.002243, +0.009633] 4/2/0, 50/64 |
| `cw1_rl5_sa_children_alone_rate` | A - C | -0.0003364 [-0.001511, +0.0004455] 2/2/1, 16/32 (n=5) | -1.618e-05 [-0.001262, +0.0007994] 3/2/1, 56/64 |
| `cw1_rl5_sb_crew_rate` | D - B | +0 [+0, +0] 0/0/5, 32/32 (n=5) | -7.46e-05 [-0.0004476, +0] 0/1/5, 64/64 |
| `cw1_rl5_sb_nonfarm_rate` | D - B | -0.0002653 [-0.002217, +0.0007499] 2/1/2, 32/32 (n=5) | -9.153e-05 [-0.0006657, +0.0004677] 3/2/1, 48/64 |
| `cw1_rl5_sb_children_alone_rate` | D - B | +0.0005205 [+0, +0.001838] 2/0/3, 16/32 (n=5) | +0.0003122 [-0.0004502, +0.001486] 3/1/2, 24/64 |
| `cw1_rl5_sa_crew_count` | A - C | +0 [+0, +0] 0/0/5, 32/32 (n=5) | +0 [+0, +0] 0/0/5, 32/32 (n=5) |
| `cw1_rl5_sa_nonfarm_count` | A - C | +11.8 [-11, +72] 2/2/1, 28/32 (n=5) | +49.8 [-55, +324] 3/2/0, 26/32 (n=5) |
| `cw1_rl5_sa_children_alone_count` | A - C | -0.4 [-2, +1] 1/2/2, 24/32 (n=5) | +2.6 [-8, +12] 3/2/0, 18/32 (n=5) |
| `cw1_nots_money` | CH_noTS - A | +113.2 [-203.4, +374.1] 3/2/0, 12/32 (n=5) | -778.4 [-1941, -43.26] 0/6/0, 2/64 |
| `cw1_nots_priced_out` | CH_noTS - A | -0.0002215 [-0.002922, +0.0009893] 3/2/0, 30/32 (n=5) | -0.000416 [-0.003456, +0.0008305] 3/3/0, 54/64 |
| `cw1_nots_coverage` | CH_noTS - A | -0.05838 [-0.1362, +0] 0/3/2, 8/32 (n=5) | +0.009922 [-0.002187, +0.02578] 4/1/1, 8/64 |

- **RL5 groups:** crew households (members and co-resident children) were priced out once in
  the whole held run (B, procedural 832: 1 person-turn) and never in A, C or D; the A - C
  difference in priced-out persons is carried by non-farm adults (count +11.8 template, +49.8
  procedural, mixed signs); children without a co-resident adult changed little (A - C -2 to
  +1 template, -8 to +12 procedural person-turns). C's RL5 counts on procedural 832 are unknown
  (not zero): the native sample did not hold every priced-out person there.
- **The wage at fixed cohorts:** at `all` (E - F) the wage raised money credited in every world
  and lowered the priced-out rate in every procedural world (0/6) and 4 of 5 template; at
  `market` (G - H) money rose in 10 of 11 worlds, priced-out mixed.
- **The total checkpoint-3 contrast (A - B)** lowered money credited in every world, as
  checkpoint 3 reported: the enrollment effect (P2) outweighs the wage (P1).
- **RL6, the expedition-labour control (CH_noTS - A, the negative of CH - CH_noTS):** without
  the timber supply, money credited fell in every procedural world (-778 mean; woodcutting
  wages are gone) and was mixed in template worlds (+113 mean, 3/2); priced-out rate mixed;
  coverage changed little (CH_noTS enrolls without woodcutters' homes).

### Harm panel

Beside each comparison the screen names (A - C, C - B, D - B, E - F, G - H, CH_noTS - A and
A - B; every other declared pair is in the report). Famine and war deaths have no bundle field
("requires slice extractor", the program's recorded gap), never zero.

| Comparison | Harm | Template | Procedural |
| --- | --- | --- | --- |
| A - C | population | -8.4 [-47, +42] 2/3/0, 20/32 (n=5) | -21.17 [-106, +92] 3/3/0, 32/64 |
| A - C | treasury | +18.4 [-283, +835] 1/4/0, 32/32 (n=5) | +181.7 [-1805, +1628] 4/2/0, 50/64 |
| A - C | food_shortfall | +86.95 [-443, +592.7] 3/2/0, 20/32 (n=5) | +427.9 [-561.1, +1405] 4/2/0, 12/64 |
| A - C | priced_out_persons | +12 [-11, +76] 2/3/0, 30/32 (n=5) | +47.33 [-52, +344] 3/3/0, 52/64 |
| A - C | priced_out_children | +0.2 [-2, +3] 2/2/1, 32/32 (n=5) | +1.833 [-7, +16] 3/3/0, 46/64 |
| A - C | deaths_famine | requires slice extractor | requires slice extractor |
| A - C | deaths_epidemic | +10.6 [-8, +44] 2/3/0, 16/32 (n=5) | +21.33 [-304, +354] 3/3/0, 52/64 |
| A - C | deaths_war | requires slice extractor | requires slice extractor |
| A - C | out_migration | +39.4 [-132, +356] 2/3/0, 26/32 (n=5) | +476.3 [-181, +1262] 4/2/0, 14/64 |
| A - C | wealth_gini | +0.02172 [-0.008862, +0.05423] 4/1/0, 4/32 (n=5) | -0.05908 [-0.1705, +0.0587] 2/4/0, 14/64 |
| A - C | forest_stand | -0.03289 [-0.2535, +0.08265] 3/2/0, 28/32 (n=5) | -0.09235 [-0.1859, -0.0311] 0/6/0, 2/64 |
| C - B | population | -8.6 [-24, +7] 2/3/0, 10/32 (n=5) | -40.83 [-151, +90] 2/4/0, 20/64 |
| C - B | treasury | +0.4 [-497, +587] 1/4/0, 32/32 (n=5) | -988 [-1943, -70] 0/6/0, 2/64 |
| C - B | food_shortfall | -461.2 [-1048, -127.2] 0/5/0, 2/32 (n=5) | -664.3 [-1440, +231.7] 1/5/0, 6/64 |
| C - B | priced_out_persons | +1.8 [+0, +4] 3/0/2, 8/32 (n=5) | +50.83 [+4, +155] 6/0/0, 2/64 |
| C - B | priced_out_children | +0.8 [+0, +2] 3/0/2, 8/32 (n=5) | +8.333 [+0, +17] 5/0/1, 4/64 |
| C - B | deaths_famine | requires slice extractor | requires slice extractor |
| C - B | deaths_epidemic | -21.6 [-117, +82] 2/3/0, 20/32 (n=5) | -43.17 [-184, +109] 2/4/0, 24/64 |
| C - B | deaths_war | requires slice extractor | requires slice extractor |
| C - B | out_migration | -310.2 [-408, -224] 0/5/0, 2/32 (n=5) | -778.5 [-1512, -121] 0/6/0, 2/64 |
| C - B | wealth_gini | -0.05888 [-0.2014, +0.01069] 1/4/0, 10/32 (n=5) | -0.0183 [-0.1767, +0.09997] 3/3/0, 46/64 |
| C - B | forest_stand | +0.01029 [-0.09111, +0.1442] 3/2/0, 26/32 (n=5) | +0.02038 [-0.1264, +0.1501] 4/2/0, 38/64 |
| D - B | population | -10.2 [-50, +34] 1/4/0, 16/32 (n=5) | -6.667 [-109, +136] 3/3/0, 58/64 |
| D - B | treasury | +124.8 [-609, +1242] 2/3/0, 26/32 (n=5) | -980.5 [-3124, +611] 2/4/0, 14/64 |
| D - B | food_shortfall | -504.2 [-1331, +299.1] 1/4/0, 4/32 (n=5) | -152.4 [-1341, +1260] 3/3/0, 50/64 |
| D - B | priced_out_persons | -1.2 [-15, +5] 2/1/2, 32/32 (n=5) | -0.5 [-6, +6] 2/2/2, 64/64 |
| D - B | priced_out_children | +0.6 [+0, +3] 1/0/4, 32/32 (n=5) | +1 [-1, +5] 3/1/2, 32/64 |
| D - B | deaths_famine | requires slice extractor | requires slice extractor |
| D - B | deaths_epidemic | +6.6 [-51, +51] 3/2/0, 26/32 (n=5) | +1.333 [-258, +209] 4/2/0, 60/64 |
| D - B | deaths_war | requires slice extractor | requires slice extractor |
| D - B | out_migration | -303.6 [-893, +12] 1/4/0, 4/32 (n=5) | -391.3 [-1213, +688] 2/4/0, 18/64 |
| D - B | wealth_gini | +0.01519 [-0.07578, +0.06322] 3/2/0, 20/32 (n=5) | -0.0342 [-0.1744, +0.0836] 3/3/0, 30/64 |
| D - B | forest_stand | -0.01386 [-0.1139, +0.06877] 2/3/0, 22/32 (n=5) | +0.007573 [-0.2188, +0.1845] 2/4/0, 64/64 |
| E - F | population | -26.8 [-57, -4] 0/5/0, 2/32 (n=5) | -13 [-86, +42] 3/3/0, 40/64 |
| E - F | treasury | -160.2 [-453, +248] 1/4/0, 10/32 (n=5) | -513.8 [-2690, +1443] 1/5/0, 22/64 |
| E - F | food_shortfall | -401.5 [-1049, -1.799] 0/5/0, 2/32 (n=5) | -389.2 [-1756, +480.7] 3/3/0, 24/64 |
| E - F | priced_out_persons | -89.6 [-219, +30] 1/4/0, 6/32 (n=5) | -396.7 [-981, -9] 0/6/0, 2/64 |
| E - F | priced_out_children | +0.2 [-25, +19] 3/2/0, 32/32 (n=5) | -22.67 [-79, +10] 1/4/1, 8/64 |
| E - F | deaths_famine | requires slice extractor | requires slice extractor |
| E - F | deaths_epidemic | -9 [-33, +24] 1/4/0, 14/32 (n=5) | +27.33 [-181, +241] 4/2/0, 48/64 |
| E - F | deaths_war | requires slice extractor | requires slice extractor |
| E - F | out_migration | -448.6 [-854, +67] 1/4/0, 6/32 (n=5) | -271.5 [-2032, +1271] 3/3/0, 38/64 |
| E - F | wealth_gini | -0.03027 [-0.1416, +0.08132] 1/4/0, 14/32 (n=5) | -0.01227 [-0.1236, +0.1151] 2/4/0, 46/64 |
| E - F | forest_stand | +0.2398 [-0.04421, +0.8433] 3/2/0, 14/32 (n=5) | -0.03715 [-0.112, +0.0611] 2/4/0, 14/64 |
| G - H | population | -0.4 [-21, +34] 2/3/0, 32/32 (n=5) | -47.33 [-229, +37] 2/4/0, 26/64 |
| G - H | treasury | -108.8 [-1000, +534] 2/3/0, 24/32 (n=5) | +161.5 [-1041, +2063] 3/3/0, 52/64 |
| G - H | food_shortfall | +20.48 [-248.5, +193] 3/2/0, 28/32 (n=5) | -85.67 [-1642, +1375] 3/3/0, 44/64 |
| G - H | priced_out_persons | +18.2 [-34, +63] 4/1/0, 10/32 (n=5) | -29.17 [-88, +8] 3/3/0, 16/64 |
| G - H | priced_out_children | -2.6 [-8, +0] 0/4/1, 4/32 (n=5) | -2.5 [-16, +11] 2/4/0, 38/64 |
| G - H | deaths_famine | requires slice extractor | requires slice extractor |
| G - H | deaths_epidemic | -8.4 [-55, +108] 1/4/0, 28/32 (n=5) | +63.67 [-157, +238] 5/1/0, 18/64 |
| G - H | deaths_war | requires slice extractor | requires slice extractor |
| G - H | out_migration | +174.2 [-159, +778] 3/2/0, 12/32 (n=5) | +347.3 [-1335, +1121] 4/2/0, 24/64 |
| G - H | wealth_gini | -0.02679 [-0.1525, +0.05822] 1/4/0, 18/32 (n=5) | +0.0493 [-0.05185, +0.09195] 5/1/0, 6/64 |
| G - H | forest_stand | -0.01211 [-0.04509, +0.03959] 2/3/0, 18/32 (n=5) | -0.06025 [-0.3123, +0.2133] 3/3/0, 32/64 |
| CH_noTS - A | population | +17.8 [-30, +68] 3/2/0, 14/32 (n=5) | -19.5 [-212, +166] 2/4/0, 48/64 |
| CH_noTS - A | treasury | +156.2 [-388, +872] 3/2/0, 22/32 (n=5) | +159 [-2357, +4716] 2/4/0, 58/64 |
| CH_noTS - A | food_shortfall | +225.4 [-465.3, +968.7] 2/3/0, 16/32 (n=5) | +123 [-1128, +2545] 3/3/0, 54/64 |
| CH_noTS - A | priced_out_persons | -4.4 [-76, +30] 3/2/0, 30/32 (n=5) | -28.33 [-278, +97] 3/3/0, 52/64 |
| CH_noTS - A | priced_out_children | -0.4 [-2, +1] 2/2/1, 24/32 (n=5) | +0.3333 [-10, +7] 4/2/0, 58/64 |
| CH_noTS - A | deaths_famine | requires slice extractor | requires slice extractor |
| CH_noTS - A | deaths_epidemic | +22.6 [-21, +90] 3/2/0, 12/32 (n=5) | -11.33 [-192, +340] 2/4/0, 58/64 |
| CH_noTS - A | deaths_war | requires slice extractor | requires slice extractor |
| CH_noTS - A | out_migration | +349.2 [-65, +627] 3/2/0, 8/32 (n=5) | +200.5 [-998, +2103] 3/3/0, 48/64 |
| CH_noTS - A | wealth_gini | -0.06415 [-0.2885, +0.0206] 1/4/0, 8/32 (n=5) | -0.01731 [-0.1627, +0.1197] 3/3/0, 48/64 |
| CH_noTS - A | forest_stand | +0.1236 [-0.3685, +0.91] 3/2/0, 22/32 (n=5) | -0.005129 [-0.1104, +0.04716] 4/2/0, 58/64 |
| A - B | population | -17 [-57, +25] 2/3/0, 12/32 (n=5) | -62 [-220, +53] 3/3/0, 22/64 |
| A - B | treasury | +18.8 [-752, +800] 2/3/0, 30/32 (n=5) | -806.3 [-3020, +554] 3/3/0, 24/64 |
| A - B | food_shortfall | -374.3 [-937.6, +51.64] 2/3/0, 8/32 (n=5) | -236.5 [-1128, +569.7] 3/3/0, 28/64 |
| A - B | priced_out_persons | +13.8 [-11, +78] 3/1/1, 20/32 (n=5) | +98.17 [+4, +420] 6/0/0, 2/64 |
| A - B | priced_out_children | +1 [+0, +4] 2/0/3, 16/32 (n=5) | +10.17 [-1, +27] 4/1/1, 8/64 |
| A - B | deaths_famine | requires slice extractor | requires slice extractor |
| A - B | deaths_epidemic | -11 [-73, +81] 2/3/0, 22/32 (n=5) | -21.83 [-195, +259] 2/4/0, 54/64 |
| A - B | deaths_war | requires slice extractor | requires slice extractor |
| A - B | out_migration | -270.8 [-528, -52] 0/5/0, 2/32 (n=5) | -302.2 [-1693, +1141] 2/4/0, 28/64 |
| A - B | wealth_gini | -0.03717 [-0.1865, +0.02789] 3/2/0, 18/32 (n=5) | -0.07738 [-0.3472, +0.05402] 2/4/0, 22/64 |
| A - B | forest_stand | -0.0226 [-0.1093, +0.009857] 2/3/0, 16/32 (n=5) | -0.07197 [-0.2069, +0.0433] 1/5/0, 6/64 |

Readings, descriptive only: at A's enrollment the wage left population, treasury, food
shortfall and epidemic deaths mixed; procedural forest stand fell in every world (-0.09 of
capacity: the paid arm cut more timber). A's larger enrollment without the wage (C - B) cut
out-migration in every world and food shortfall in 5 of 5 template and 5 of 6 procedural worlds,
but priced more people out in every procedural world (+51 person-turns) and drained procedural
treasuries (0/6). Trajectories diverge after the first wage or enrollment difference, so none
of this is a mechanism estimate.

**Failures and nulls.** No run failed. Not-activated worlds (template 734 for every
comparison with a paid arm or with C or D) are left out, never counted as zero; RL5 counts
unknown on one procedural world (C, 832) are left out; famine and war deaths remain unrecorded.
