# Connected-world CW1: preregistered held screen for the wage and `paid_work` enrollment (slice S1)

Status: DRAFT (Amendment 1: P1 changed; first frozen at `81392e8b`; the pilot reruns on the amended screen module before the re-freeze)

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

Compute ceiling: 1.11 core-hours

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
- **Identity (the extractors live in the screen module):** source `81392e8b`, dirty 0;
  `scripts/connected_world_screens.py` SHA-256
  `fa7e15c7a34b5393ae1bef735f9cfa1a81ea7a95370347d5fd25a21a70241065`; `scripts/screen_runner.py`
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

`run PILOT --screen CW1 --cohort pilot --jobs 2` on `81392e8b` (clean tree): **18 runs, 0
failed, every outcome extracted** (`check --metrics ... --cohort pilot` passes); 333 s of
simulation and extraction (0.092 core-hours), 171.6 s of wall time at 2 concurrent processes
on the shared, loaded 4-core machine. Every arm activated on both pilot worlds; all 4 replays
(C and D on template 5 and procedural 19) were exact. Mean seconds per run (simulation and
extraction): template A 9.5, B 8.8, C 9.8, D 9.2, E 10.9, F 10.8, G 10.5, H 10.6, CH_noTS
9.1; procedural A 28.1, B 26.6, C 27.4, D 25.6, E 29.9, F 28.4, G 26.0, H 28.2, CH_noTS 23.6.
**Projected held run: 0.555 core-hours for 108 runs** (x1.5 = 0.833), about 17 minutes of
wall time at 2 processes. The pilot's `metrics.jsonl`, `source.txt`, `report.md`,
`derived.jsonl` and derived schedules are retained in `connected-world-screens-cw1/pilot/`
(the held run's `--pilot`). The pilot's outcomes were not read for any decision.

## Budget and stopping rules

- **Compute ceiling 1.11 core-hours** (the line above, read by the runner): the pilot
  projection (0.555) x 2, under the 2.0 cap. At most 3 concurrent processes; run with `--jobs 2` because
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
Code: `4a79b7f5` (the screen module only). REVALIDATION
