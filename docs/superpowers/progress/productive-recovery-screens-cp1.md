# Productive recovery, checkpoint 1: preregistered held screens (PL6a)

Status: **DRAFT, not frozen**. The lead freezes this file on the final checkpoint-1
source, before any held run. `scripts/productive_recovery_screens.py run --cohort held`
refuses to start until this status line reads FROZEN.

Drafted 2026-11-06 by lane PL6a on `claude/pl6a-screens` (from the phase head
`8f7a6718`). No held seed has been run by this lane.

## Purpose and limits

These are bounded screens on default-off experimental source, not qualification. They
ask whether the checkpoint-1 recovery packages (PL1 timber supply, PL2 operating wear
and RS1 rules version 2, PL3 recovery crews and the maintenance obligation) move their
declared outcomes on fresh worlds, against cost-retaining controls, and what they cost.

- The 200-seed and procedural qualification gates are out of scope and stay unrun.
- No switch is promoted to a default, and no constant is tuned on these worlds.
- Six worlds per stratum support means, ranges and sign counts, not significance tests.
- Trajectories diverge once any switch spends differently, so population and treasury
  differences are reported but not attributed to a mechanism.

## Units

The independent units are **worlds** (seeds), never agents, regions or turns. Every arm
runs once on every held world, and each arm is compared with its declared control on
the same world. Results are reported per stratum: template (8 regions, 4 civs) and
procedural (32 regions, 10 civs).

## Source and budget (proposal)

- **Source.** The phase branch `claude/productive-recovery` at the commit the lead
  records when freezing, and a native extension built from that commit's Rust into
  the interpreter that runs the screen. The runner writes the source commit (and
  whether the tree is dirty), the imported `chronicler` path, the extension path and
  SHA-256, and the interpreter to `source.txt`, after checking that runs import the
  checkout's own `src` (`livelihoods_screens.source_identity`).
- **Budget.** At most **2.0 core-hours** in total, at most **3 concurrent processes**,
  and at most **6 GiB of transient disk**. Raw outputs are deleted after extraction;
  `--keep-first` keeps the first world of each stratum outside the repository as an
  example. The timing pilot projects the held run below.
- **Environment.** `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1`, the
  checkout's `src` on `PYTHONPATH` (shared `_run_env`).
- **Command.** `python scripts/productive_recovery_screens.py run OUT --cohort held
  --jobs 3`, then `report OUT/metrics.jsonl` and `check --metrics OUT/metrics.jsonl
  --cohort held`.

## Seeds

| Use | Template (8 × 4) | Procedural (32 × 10) |
| --- | --- | --- |
| Timing pilot (this file) | 5 | 19 |
| **Held cohort, checkpoint 1** | **701–706** | **801–806** |
| Reserved for checkpoints 2 and 3 (never run here) | 711–716, 721–726 | 811–816, 821–826 |
| Earlier held cohorts and pilots (never run) | 2, 101–106, 301–306, 501–506 | 201–206, 401–406, 601–606 |
| Development (inspected freely) | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 |

Seed numbers are per stratum. `check_seeds` (run before every `run` and by
`tests/test_productive_recovery_screens.py`) asserts, per stratum, that the pilot and
held seeds are disjoint from every earlier cohort and pilot (including those the
sprint 1–3 runner declares), from the reserved cohorts, from the development worlds and
from each other.

## Arms

Base for every arm: `--turns 200 --agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --grain-storage
--workshops` (workshops in their default operate mode). Procedural worlds add
`--worldgen procedural --regions 32 --civs 10`. `RP` below is `--operating-wear
--repair-projects --timber-stock`.

| Arm | Flags added to the base | Control | Question |
| --- | --- | --- | --- |
| W | none | — | root |
| W_wear | `--operating-wear` | W | what the maintenance assumption alone does |
| TR2 | `--apprenticeship` | NQ2 | does training (RS1 v2) put qualified people on operating crews? |
| NQ2 | `--apprenticeship --apprenticeship-mode no_qualification` | W_wear | cost-retaining control: the same seats, time and wear, no qualification |
| RP | `--operating-wear --repair-projects --timber-stock` | W_wear | reference for the recovery packages: RS2 repair under the shared wear, with the L3 stock |
| TS | RP + `--timber-supply` | TS_cost | does named, paid woodcutting deliver timber that repairs granaries? |
| TS_cost | RP + `--timber-supply --timber-supply-mode cost_only` | RP | cost-retaining control: the same expeditions, crews, wages and home labour, no cutting |
| RC | RP + `--recovery-crews` | RC_unpaid | do granary coins reach named crew households as wages? |
| RC_unpaid | RP + `--recovery-crews --recovery-crew-mode unpaid` | RP | control: the same crews, charge and withholding, the coins sunk |
| L9 | RP + `--local-budgets` | RP | the penalty of bargained envelopes on repair |
| MO | L9 + `--maintenance-obligation` | MO_ro | does a reserved maintenance obligation restore condition? |
| MO_ro | L9 + `--maintenance-obligation --maintenance-obligation-mode reserve_only` | L9 | crowding-out control: the same reservation, repairs held to their envelope |
| CH | RP + `--timber-supply --recovery-crews --veteran-reintegration` | CH_rec | the recovery chain with veteran priority |
| CH_rec | CH + `--veteran-mode record_only` | RP | control: the same chain, veterans recorded without priority |

Every arm's command line parses with the real parser and passes the livelihoods
prerequisite checks, enabling exactly the packages and modes the table names
(`check_arm_flags`). Feature-off identity, exact resume and native parity are tested
elsewhere, not as screen arms.

## Outcomes

Each outcome is a per-world paired difference (arm minus control on the same world), or
the arm's own value where no control is named. The report prints every world's value
and, per stratum, the mean, the range and the number of worlds above, below and at zero;
a world whose arm or control failed, or whose value is unknown, is listed as such
(`failed`, `unknown`, `not run`). **Primary** outcomes are marked; the rest are
secondary. The executable list is `PAIRED` in the runner.

### Definitions

- **Mean granary condition (run mean).** For each of the 200 completed turns, the mean
  condition of the granaries with capacity above zero (`history[i].grain_reserves.storage`);
  then the mean over turns that had one. The end-of-run value (the final world state,
  the sprint-3 measure) is reported as secondary. The development lanes (D3, PL1, PL3)
  reported the run mean.
- **Mean workshop condition (run mean).** The same over built open L1 sites (`status`
  open, `asset` not `building`), from each snapshot's `livelihoods.workshops.sites`.
- **Lump repairs.** Workshop receipts that paid the L1 lump repair, over all snapshots.
- **Operating site-turns.** Workshop receipts with a craft ceiling (shared metrics).
- **Counters** are lifetime counters of the last snapshot's package record. A declared
  counter absent from an enabled package's record was never incremented and is 0, since
  every record starts empty when its switch is enabled (the sprint-3 rule).
- **Stalled project-turns for a reason** (`repair_projects.stalled_no_timber`,
  `stalled_no_envelope`, …) count the stalled project-turns whose reasons include that
  reason; one stall can carry several (`repair_projects.py`, the receipt loop). They
  are not the primary-reason counts the PL3 page tabulates.
- **Structural zero.** Where an outcome sums wage channels (CH − RP) or the control
  lacks the package (timber delivered in RP), a package the arm's flags leave off counts
  0; the extractor has verified that such a package wrote no record. A missing record of
  an enabled package is a failure, never zero.
- **Unknown.** A measure of an event that never happened is unknown (`None`), never 0:
  no granary with capacity, no built site, no cutting turn (minimum stock share), no
  ended expedition (per-expedition means), no farmer-turn away (home shortfall share),
  no operating site-turn (covered share).

### W_wear − W: the maintenance assumption

- **Primary:** lump repairs.
- Mean workshop condition (run mean and at end); operating site-turns.

### TR2 − NQ2: training under the shared wear (RS1 rules version 2)

- **Primary:** the share of operating site-turns covered by a qualified crew member
  (`apprenticeship.covered_site_turns / operating_site_turns`).
- Graduate crew-turns; completions; lump repairs; upkeep offset; full-offset site-turns;
  qualifications through apprenticeship and through service (crowding out between the
  routes); mean workshop condition.
- NQ2 − W_wear: lump repairs and workshop condition (seats and attachment under the
  same wear; expected near zero).

### TS − TS_cost: timber supply

- **Primary:** mean granary condition (run mean).
- Granary condition at end; RS2 `no_timber` stalled project-turns; RS2 timber used;
  timber cut and delivered; transit loss; abandoned cargo (deposited at the forest);
  L3 extraction; the minimum L3 stock share after a cutting turn (also TS alone, the
  ecological guard); home farm labour away (farmer-turns); woodcutting wages; expeditions
  launched; wages, person-turns and farmer-turns away per ended expedition (the
  comparison the control matches; `cost_only` launches more in total by design).
- **Food cost** (below): TS − TS_cost, TS_cost − RP and TS − RP, and the home-region
  shortfall share on away turns (TS and TS_cost alone).
- TS_cost − RP: mean granary condition (the expeditions' cost without timber).

#### The food-cost outcome

**Measure.** Food shortfall after public relief, in food units, summed over the 200
turns in a fixed set of regions per world:

    shortfall(region, turn) = demand × max(0, 1 − min(1, sufficiency_after_relief))

read from each snapshot's `food_accounting.regions` (native demand and the sufficiency
after granary release). The region set is:

- TS − TS_cost: the regions that sent a woodcutting crew in either arm;
- TS_cost − RP: the regions TS_cost's crews came from (the expeditions' food cost
  without the timber they would bring);
- TS − RP: the regions TS's crews came from (the net of cost and benefit).

Descriptive, per arm: the shortfall share (shortfall ÷ demand) of the crews' home
regions on exactly the turns their farm labour was away (receipt `away_delivered` > 0,
matched to the food row of the same source turn), with the count of such cells.

**Why this measure.**

- The bundle has no counterfactual harvest, so the food a crew would have grown cannot
  be read from one run; PL1's own page claims no direct number for that reason. The
  food the removed labour cost is visible only where it lands: as unmet food demand in
  the communities that sent the crews.
- `food_accounting` is the model's own region-turn food ledger, dated by the same source
  turn as the woodcutting receipts, present in every hybrid snapshot and validated by
  the extractor in every run. It measures what people lacked after the market and
  public relief, which is the household-facing quantity checkpoint 2 builds on, and it
  includes granary release, through which repaired granaries act on food.
- A fixed region set per world compares both arms on the same communities over the
  same turns, so the comparison does not change its denominator with the number of
  expeditions (which differs by design between `supply` and `cost_only`).
- TS − TS_cost cannot isolate the labour cost, because the control keeps the same
  per-expedition labour removal; that is why TS_cost − RP (cost without benefit) and
  TS − RP (net) are reported beside it.

**Limits.** Region identity is its index, so the set is stable across arms, but
trajectories diverge and the run-long sum includes turns without crews; D1's marginal
product (0.27–1.02 food per farmer moved) bounds the direct cost at about one food per
farmer-turn away, which is small against regional demand. A null here is not evidence
that the labour cost is zero.

### RC − RC_unpaid: the wage channel to households

- **Primary:** granary-crew wages paid to named members (`recovery_crews.granary_wages_milli`,
  coins).
- Granary coins sunk; RS2 workshop-crew wages (paid in both modes); mean granary
  condition (run mean and at end; expected nearly unchanged); veterans placed on
  recovery crews.
- RC_unpaid − RP: granary and workshop condition (the named crews' labour limit and the
  wider workshop pool).
- Note: RC has no `--veteran-reintegration`, so veterans placed on its crews are
  structurally 0; veterans are measured in CH − CH_rec.

### MO − MO_ro: the maintenance obligation

- **Primary:** mean workshop condition and mean granary condition (run means).
- Reserved, used and returned coins; RS2 `no_envelope` stalled project-turns; the other
  L9 envelopes awarded (all services but `repairs`, summed over the dated decision
  frames).
- MO_ro − L9: the other envelopes awarded in total and for workshops, granaries and
  relief (the crowding-out cost itself), and mean granary condition (expected near
  zero).

### L9 − RP: the L9 penalty

- Mean workshop and granary condition (run means); RS2 `no_envelope` stalls (L9 alone).

### CH − CH_rec and CH − RP: the recovery chain

- CH − CH_rec. **Primary:** veteran placements (`veteran_reintegration.placements`).
  People placed; repair placements.
- CH − RP. **Primary:** mean granary condition (run mean). Wages to named repair
  workers (RS2 workshop crews, PL3 granary crews and PL1 woodcutters, coins); timber
  delivered.
- CH_rec − RP: mean granary condition.

### Shared outcomes and funnels

- Final total population and treasury, arm minus control, mean and range per stratum.
- Every counter the report reads (`OUTCOMES`), per arm and package: mean per world with
  range and the number of worlds at zero, and L9 awards by service. Null activation is
  reported, not hidden.

## Extractor validation

- `check_extractor` (before every run and in the tests): every counter read is declared
  in its package's `COUNTERS` in the source; every package is a livelihoods switch whose
  mode option and default match the registry; every arm's flags are known; every
  control exists and the controls form a tree rooted at W; every comparison in `PAIRED`
  is declared.
- A run is a **visible failure** (rc 3, the run and the reasons named in `metrics.jsonl`,
  on the console and in the report; `run` and `check --metrics` exit with code 3) when:
  - the run does not have one snapshot per turn 1..200;
  - the last snapshot does not hold exactly the packages the arm enables;
  - an enabled package's record is missing, is not for the completed turn, is in another
    mode, or carries an undeclared or non-numeric counter;
  - any snapshot lacks the granaries, the workshop sites or receipts, a complete food
    accounting row per region, the woodcutting receipts (TS arms) or the L9 decisions
    (L9 arms), or an L9 award names no declared service;
  - the L3 arm has no stock totals, or the bundle cannot be read.
- A simulation that exits non-zero is a failed run (its rc and stderr recorded).
- Constructed-bundle tests: `tests/test_productive_recovery_screens.py` (oracle chunk
  `productive-recovery-pl3`).

## Incomplete runs and stopping rules

- Every arm runs once per held world. Nothing is tuned after held outcomes are seen.
- If the budget runs out, or a process is killed (a container restart), the unfinished
  arms and worlds are reported as **incomplete** (`report` lists each `not run`; `check
  --metrics` fails), never silently dropped. Finishing them later on the same frozen
  source and extension is allowed only if no report of the held outcomes has been read:
  `run --resume` in the same output directory runs only the arms and worlds without a
  row, refuses another source commit, `chronicler` path, extension or interpreter, and
  never repeats a recorded run. The restart is recorded as an amendment.
- A run that raises or fails extraction is recorded as failed with its error and is not
  rerun silently. A failure in the held runs is a finding, investigated and reported; a
  fix would need a new held cohort to be evaluated.
- No significance claims.

## Timing pilot

One run of every arm on the two pilot worlds (template 5, procedural 19), at most 2
concurrent processes, to set the budget and find defects. Its outcomes are not used to
choose arms, outcomes or parameters.

- **Run** 2026-11-06 by PL6a on `3124421a` (`src` identical to the phase head
  `8f7a6718`; later commits change only the runner's resume and timing bookkeeping),
  native extension `fdcb0ca0…` (`~/.venvs/native-pl1`, built from the Rust of
  `7c16e9ce`; no Rust file changed since), CPython 3.13, 2 concurrent processes on a
  shared 4-core machine. The pilot's metrics are kept outside the repository.
- **All 28 runs succeeded and every outcome extracted** (no rc 3; `check --metrics
  --cohort pilot` passes). The cost-retaining controls behave as declared on both
  worlds: `TS_cost` cut and delivered nothing, `RC_unpaid` paid no granary wages and
  sank the same order of coins, `MO_ro` used none of its reservation and returned all
  of it, and `W_wear`'s lump repairs equal `operating_wear.repairs`.
- **Seconds per run** (simulation): template 7.1 on average (5.9–9.4), procedural 19.1
  (17.7–21.5); 367 s in total, 227 s of wall time. Extraction runs in the runner process
  and was timed separately on development worlds: 1.2–1.3 s (template), 3.6 s
  (procedural).
- **Projection for the held cohort** (168 runs): 0.61 core-hours of simulation plus
  0.11 of extraction, about **0.73 core-hours** of the 2.0 proposed, roughly 15–20
  minutes of wall time at 3 concurrent processes. Transient disk is under 30 MB per
  procedural run (8 MB template), well under 1 GiB at 3 concurrent.
- **Defects found:** none in the runner, the extractor or the simulation. Two
  definitional points were found while checking the funnels and are recorded under
  open questions, not changed: RS2's `stalled_<reason>` counters count every reason of
  a stalled turn (not only the primary reason the PL3 page tabulates), and RC's veteran
  outcome is structurally 0 without RS3.
- The lane read the pilot report while checking for defects and changed no arm,
  outcome, parameter or budget in response.

## Amendments

None yet. Any change to the arms, outcomes, analysis or budget after the lead freezes
this file is recorded here as a dated amendment with its reason, and only before the
first held run.

## Open questions for the lead

- Primary condition measures use the run mean; sprint 3 used the end-of-run value. Both
  are reported; confirm which is primary before freezing.
- RC carries no `--veteran-reintegration`, so its veteran outcome is structurally 0
  (0 in both pilot worlds, as expected). Add RS3 to RC and RC_unpaid, or drop that
  outcome; veterans are measured in CH − CH_rec either way.
- `no_envelope` and `no_timber` stalls are any-reason counts (above). If the
  primary-reason count is wanted for comparison with the PL3 page, it can be derived
  from the dated RS2 receipts; decide before freezing.
- The food-cost outcome (above) is this lane's proposal.
- A held run interrupted by a container restart can be finished with `run --resume` on
  the same source and extension (the incomplete-run rule above); confirm that rule.
- The held run should use an extension built from the frozen commit's Rust; the pilot
  used `fdcb0ca0…` (PL1's build). Any later Rust change needs a fresh build.
