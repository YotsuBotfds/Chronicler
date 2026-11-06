# Productive recovery, checkpoint 3: preregistered held screens (PL6d)

Status: **FROZEN** by the lead on 2026-11-06, before any held run, with the runner at
`df21cb43` (branch `claude/productive-recovery-cp3`). The simulation source (`src/`,
`chronicler-agents/`) is identical to `main` `96c20439`, and the native extension
`101a4cd5…` (`~/.venvs/native-hrn2`) was built from `478f2dca`, whose Rust equals `main`'s.
Code may change between this freeze and the held run only to fix a defect, listed as an
amendment; no arm, outcome or parameter may change in response to held outcomes.

**Pilot on the frozen source.** Rerun on `df21cb43` after the lead decisions and the review
fixes: 12 runs, 0 failed, every outcome extracted (`check --checkpoint 3 --cohort pilot`
passes); 156 s of simulation and 28 s of extraction, 94.7 s of wall time at 2 concurrent
processes on the shared machine; projected held run 0.306 core-hours for 72 runs. The
pilot's outcomes were not read for any other decision.

Drafted by lane PL6d (below); the lead's decisions and the review's fixes are recorded in
"Lead decisions" and "Amendments".

Drafted on `claude/pl6d-chain` from `claude/household-retail` `12ad9a1e`. This lane changes
no simulation, Rust or viewer file: `src/` and `chronicler-agents/` equal `12ad9a1e`, and the
native extension `101a4cd5…` (`~/.venvs/native-hrn2`) matches that Rust. No held seed was run.

## Purpose and limits

These are bounded screens on default-off experimental source, not qualification. They ask
whether the phase's chain holds together on fresh worlds: a community needs timber (RS2
stalls `no_timber`), shifts labour to obtain it (PL1 timber supply), repairs its granary
with a named, paid crew (PL3 recovery crews), and those households can buy food (PL4
household retail at the `paid_work` boundary), with RS4 remittances as the other household
cash channel. Each link is tested against a control that removes it, and the tradeoffs are
reported beside it: less farm labour, forest pressure, scarce budgets and families priced
out.

- The 200-seed and procedural qualification gates are out of scope and stay unrun.
- No switch is promoted to a default, and no constant is tuned on these worlds.
- Six worlds per stratum support means, ranges and sign counts, not significance tests.
- Trajectories diverge once any switch spends differently, so population, treasury and the
  cross-arm food measures are reported but not attributed to a mechanism.
- The `paid_work` boundary depends on wages, so the arms price food in different regions
  (coverage, below). Every cross-arm retail measure is read with its coverage beside it.

## Units

The independent units are **worlds** (seeds), never agents, households, regions or turns.
Every arm runs once on every held world, and each arm is compared with its declared control
on the same world. Results are reported per stratum: template (8 regions, 4 civs) and
procedural (32 regions, 10 civs).

## Source and budget

- **Source.** The checkpoint-3 integration branch at the commit the lead records when
  freezing, and a native extension built from that commit's Rust into the interpreter that
  runs the screen. The runner writes the source commit (and whether the tree is dirty), the
  imported `chronicler` path, the extension path and SHA-256, and the interpreter to
  `source.txt`, after checking that runs import the checkout's own `src`.
- **Budget.** At most **2.0 core-hours** in total, at most **3 concurrent processes**, and at
  most **6 GiB of transient disk**. Raw outputs are deleted after extraction; `--keep-first`
  keeps the first world of each stratum outside the repository. The timing pilot projects
  the held run below.
- **Environment.** `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1`, the checkout's
  `src` on `PYTHONPATH` (shared `_run_env`).
- **Command.** `python scripts/productive_recovery_screens.py run OUT --checkpoint 3 --cohort
  held --jobs 3`, then `report OUT/metrics.jsonl --checkpoint 3` and `check --checkpoint 3
  --metrics OUT/metrics.jsonl --cohort held`.

## Seeds

| Use | Template (8 × 4) | Procedural (32 × 10) |
| --- | --- | --- |
| Timing pilot (this phase; shared with checkpoints 1 and 2) | 5 | 19 |
| **Held cohort, checkpoint 3** | **721–726** | **821–826** |
| Held cohort, checkpoint 2 (run on 2026-11-06; never again) | 711–716 | 811–816 |
| Held cohort, checkpoint 1 (run on 2026-11-06; never again) | 701–706 | 801–806 |
| Earlier held cohorts and pilots (never run) | 2, 101–106, 301–306, 501–506 | 201–206, 401–406, 601–606 |
| Development (inspected freely) | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 |
| Development, viewer QA batches only | 12, 13, 14 | — |

Seed numbers are per stratum. `check_seeds(CP3)` (run before every `run` and by
`tests/test_productive_recovery_screens_cp3.py`) asserts, per stratum, that the pilot and
held seeds are disjoint from every earlier cohort and pilot (including those the sprint 1–3
runner declares and the held cohorts of checkpoints 1 and 2, which must be listed as never
run), from the development worlds and from each other. No later cohort is reserved in this
phase. The checkpoint-3 held cohort is the one checkpoints 1 and 2 reserved and never ran.

## Arms

Base for every arm: `--turns 200 --agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --grain-storage
--food-allocation --workshops --operating-wear --repair-projects --timber-stock
--household-retail --household-retail-boundary paid_work`. That is checkpoint 1's recovery
reference (RS2 under the operating wear, with the L3 stock), L2 in its default
`floor_means` regime, and retail in its default `retail` mode at the `paid_work` boundary.
Procedural worlds add `--worldgen procedural --regions 32 --civs 10`. The boundary option
goes with the retail switch, so `CH_L2` drops both. `CH` below is `--timber-supply
--recovery-crews --remittances` (PL1 `supply`, PL3 `paid`, RS4 `send`).

| Arm | Flags added to the base | Control | Question |
| --- | --- | --- | --- |
| C0 | none | — | root: RS2 and retail at `paid_work`, no timber supply, no crews, no remittances |
| CH | `--timber-supply --recovery-crews --remittances` | CH_unpaid | the whole chain |
| CH_unpaid | `--timber-supply --recovery-crews --recovery-crew-mode unpaid --remittances` | C0 | the chain with the granary crews' coins sunk (no wage) |
| CH_cut | `--timber-supply --timber-supply-mode cost_only --recovery-crews --remittances` | CH | the chain without timber: the same expeditions, crews, wages and home labour, no cutting |
| CH_free | CH with `--household-retail-mode free_exchange` | CH | the chain with ownership and timing but no cash for food |
| CH_L2 | CH without `--household-retail --household-retail-boundary paid_work` | CH | the chain under L2's free allocation |

In code, `CP3.BASE` holds the flags every arm shares and each arm but `CH_L2` adds
`CP3.RETAIL` (`--household-retail --household-retail-boundary paid_work`), so C0's whole
command line is the base above. Every arm's command line parses with the real parser and
passes the livelihoods prerequisite checks, enabling exactly the packages, modes and
boundary the table names (`check_arm_flags(CP3)`, verified for all six arms). Feature-off
identity, exact resume and native parity are tested elsewhere, not as screen arms.

The outcomes below are written as the chain minus each control (`CH − CH_cut`, `CH −
CH_free`, `CH − CH_L2`). The arm table points the other way for those three, so the
report's "Shared outcomes vs each arm's control" table (population and treasury) shows
`CH_cut − CH`, `CH_free − CH` and `CH_L2 − CH`, with the opposite sign.

## Outcomes

Each outcome is a per-world paired difference (arm minus control on the same world), or the
arm's own value where no control is named. The report prints every world's value and, per
stratum, the mean, the range and the number of worlds above, below and at zero; a world
whose arm or control failed, or whose value is unknown, is listed as such (`failed`,
`unknown`, `not run`). **Primary** outcomes are marked; the rest are secondary. The
executable list is `CP3.PAIRED` in the runner (81 outcomes, 2 primary).

### Definitions

- **Pilot region-turn.** As in checkpoint 2: a region-turn whose retail frame row
  (`history[i].livelihoods.household_retail.regions`) carries a native provisioning row (the
  retail arms here all provision). Their number must equal the lifetime counter
  `pilot_region_turns`.
- **Region set (fixed per world and comparison).** For `CH − X` with X in `CH_unpaid`,
  `CH_free`, `CH_L2` and `C0`: the regions that had at least one pilot region-turn in **either
  arm**, summed over all 200 turns in both arms. Region identity is its index, so the set is
  stable across arms. Checkpoint 2 took the treatment arm's pilot regions because its control
  (L2) had none; here both arms have pilot regions, so the set is their union, which is
  checkpoint 1's either-arm rule for woodcutting homes and reduces to checkpoint 2's rule for
  `CH − CH_L2`. Beside it: each arm's **coverage** (its pilot region-turns in the set ÷ the
  set's region-turns) and the **regions pilot in both arms** (the intersection).
- **Priced-out person-turns** (and child-turns, deficit). Checkpoint 2's native frame columns
  `priced_out_persons`, `priced_out_children`, `priced_out_deficit`, summed per region over
  the arm's own pilot region-turns and then over the region set. Nobody is priced out outside
  a pilot region-turn (L2 allocates free food there), so over the union set this is each
  arm's whole count. **Rate**: priced-out person-turns ÷ pilot person-turns (`persons`) in
  the set. **In both arms' regions**: priced-out person-turns over the regions pilot in both
  arms (unknown when there is none).
- **Ration shortfall.** As checkpoint 2: the retail rows' `persons − rations` in pilot
  region-turns, L2's `shortfall` in the regions L2's frame lists, zero elsewhere, summed over
  the set. **Mean ration per Phase-2 person**: 1 − shortfall ÷ Phase-2 alive over the set.
- **Food shortfall after relief.** `demand × max(0, 1 − min(1, sufficiency_after_relief))`
  from each snapshot's `food_accounting.regions`, summed over a region set.
- **Mean granary condition (run mean)** and **at end**, **mean workshop condition (run
  mean)**: checkpoint 1's definitions (granaries with capacity; built open L1 sites).
- **Woodcutting home regions (CH − CH_cut).** The regions that sent a PL1 crew in either arm
  (checkpoint 1's food-cost set), over all 200 turns; and, per arm, the home region's
  shortfall share on the turns a crew was away.
- **Wages to named repair workers.** RS2 workshop-crew wages (`repair_projects.wages_milli`,
  which includes PL3's wider workshop pool), PL3 granary-crew wages
  (`recovery_crews.granary_wages_milli`) and PL1 woodcutting wages
  (`timber_supply.wages_milli`), coins.
- **Money credited to households (gross).** Wages to named repair workers + remittances
  credited to recipients (`remittances.credited_milli`) + granary procurement credited to
  owners (`household_retail.procurement_credited_milli`) − ordinary farm income replaced by
  retail (`income_replaced_total`), coins. It extends checkpoint 2's measure (procurement
  credited − income replaced) with the chain's wage and remittance channels. Household
  purchases move money between households and are not in it. It is **gross** in two ways
  (lead decision 3): remittances also move money between households, and the senders' net
  debit (credited + the courier fee, which RS4 checks equals sent − refunded) is not
  subtracted; and the named crews' ordinary income withheld for their paid shares is not
  subtracted. Both are reported beside it as their own outcomes: the senders' net debit, and
  each package's withheld-income counter (PL1 `timber_supply.income_withheld`, RS2
  `repair_projects.income_replaced`, PL3 `recovery_crews.income_replaced`). PL3's counter
  covers its granary and workshop crews together, and its workshop part overlaps RS2's, so
  the three are not summed into a net figure.
- **Counters** are lifetime counters of the last snapshot's package record. A declared
  counter absent from an enabled package's record was never incremented and is 0 (the
  sprint-3 rule).
- **Structural zero.** A package the arm's flags leave off counts 0 in a sum of channels
  (C0's woodcutting, crews and remittances; CH_L2's retail measures); the extractor has
  verified that such a package wrote no record. `free_exchange` prices nobody out and replaces
  no income by construction. A missing record of an enabled package is a failure, never zero.
- **Unknown.** A measure of an event that never happened is unknown (`None`), never 0: a
  rate without pilot persons, a minimum stock share without a cutting turn, a per-expedition
  mean without an ended expedition, a both-arms set without a region, a mean ration without
  Phase-2 people.

### CH − CH_unpaid: does the wage reach food?

- **Primary:** priced-out person-turns per pilot person-turn in the pilot regions of either
  arm (lead decision 1).
- Priced-out person-turns (the whole count) and child-turns and deficit; priced-out
  person-turns in the regions pilot in both arms; pilot person-turns; pilot region-turns in
  the set, and each arm's coverage; ration shortfall and mean ration per Phase-2 person over
  the set.
- Granary-crew wages paid to named members; granary coins sunk; wages to named repair
  workers; remittances credited; procurement credited; ordinary farm income replaced; money
  credited to households (gross); the ordinary income withheld for PL3 crews', RS2 workshop
  crews' and PL1 woodcutters' paid shares; remittance senders' net debit; granary mean
  condition (run mean; expected nearly unchanged, as checkpoint 1 found for RC − RC_unpaid).
- **Reading it.** Under `paid_work` a region joins the pilot when a crew is paid there, so
  `CH`'s paid granary crews bring regions under retail prices that `CH_unpaid` leaves under
  L2. The whole count therefore mixes more people facing prices (coverage) with the wage's
  effect on those who do; the rate divides by the people facing prices, and the both-arms set
  compares like regions. The rate still carries a composition effect: the regions the wage
  adds hold the paid crews' households, so a lower rate there is partly the wage reaching
  those households and partly who was added. The whole count, the both-arms set and each
  arm's coverage are read beside it.

### CH − CH_cut: does timber matter?

- **Primary:** mean granary condition (run mean).
- Granary condition at end; workshop mean condition; timber delivered and cut; RS2
  `no_timber` stalled project-turns (any-reason counts, as checkpoint 1); RS2 timber used; L3
  extraction; the minimum L3 stock share after a cutting turn (difference, and CH alone: the
  ecological guard); home farm labour away (farmer-turns); food shortfall after relief in the
  woodcutting home regions of either arm; the home-region shortfall share on away turns (CH
  and CH_cut alone); woodcutting wages; expeditions launched; farmer-turns away per ended
  expedition (the comparison `cost_only` matches; it launches more in total by design).

### CH − CH_free: cash pressure with the whole chain on

- Priced-out person-turns and child-turns (zero in `free_exchange` by construction); ration
  shortfall and mean ration per Phase-2 person; pilot region-turns in the set (coverage).

### CH − CH_L2: retail against free allocation, with the chain

- Ration shortfall over CH's pilot regions (the set reduces to them); population; food
  shortfall after relief and mean ration per Phase-2 person over the set; CH's coverage of its
  own pilot regions. No primary (lead decision 2).

### CH − C0: the chain's total

- Granary mean condition (run mean); priced-out person-turns and ration shortfall over the
  pilot regions of either arm; pilot region-turns in the set; wages to named repair workers;
  money credited to households (gross); population. C0's pilot regions come only from RS2 workshop wages,
  so coverage differs most here.

### Coverage per arm and shared outcomes

- Every arm alone: its pilot region-turns and its number of pilot regions (zero in CH_L2).
- Every fixed region set (`CH − CH_unpaid`, `CH − CH_free`, `CH − CH_L2`, `CH − C0`): its
  number of regions and the number of regions pilot in both arms; both arms' coverage of
  the set (CH alone for `CH − CH_L2`, where L2 has none). Added by the lead after the
  independent review found the sizes computed but not reported.
- Final total population and treasury, arm minus control, mean and range per stratum.
- Every counter in `CP3.OUTCOMES` (household retail, RS2, PL1, PL3, RS4), per arm: mean per
  world with range and the number of worlds at zero. Null activation is reported, not hidden.

### Quantities the snapshot does not hold

- **Purchases by person.** The native money rows (id, paid, credited, refunded) are summed
  to totals before the snapshot. Per region the frame keeps purchases (`paid_milli`); by
  stable id only the 24-person sample's ration and status are kept. Whether a named crew's
  household bought food is therefore measured by region, not by id (see the chain examples in
  `productive-recovery-examples.md`).
- **The split of PL3's withheld income** between granary and workshop crews (one counter),
  and the counterfactual harvest of the crews' farm time (checkpoint 1's limit).
- **Remittances by region.** RS4's frame has per-region inflows, but the screen reads
  counters only for money; remittances into the pilot regions are not separated.

## Extractor validation

- `check_extractor(CP3)` (before every run and in the tests): every counter read is in its
  package's `COUNTERS` (household retail, RS2, PL1, PL3, RS4); every retail frame column read
  is in the Rust `RETAIL_REGION_COLUMNS` or `REGION_COLUMNS`, and the per-region retail sums
  are among the validated frame sums; every frame field is a `RegionFrame` field; every
  food-accounting field is declared; every record field the checkpoint-3 measures read
  (granary assets, workshop sites and receipts, woodcutting receipts, food rows) is a field
  of its model and the stage it matches is declared; the retail modes are the four the screen
  knows; every package is a livelihoods switch whose mode option and default match the
  registry, and every registered choice of every package (the registry's choice-field map) is
  checked as its mode or an option, recorded under the attribute the screen reads; every
  arm's flags are known; every control exists and the controls form a tree rooted at C0;
  every comparison in `CP3.PAIRED` is declared (the arm table plus `CH − CH_cut`, `CH −
  CH_free`, `CH − CH_L2` and `CH − C0`).
- A run is a **visible failure** (rc 3, the run and the reasons named in `metrics.jsonl`, on
  the console and in the report; `run` and `check --metrics` exit with code 3) when:
  - the run does not have one snapshot per turn 1..200;
  - the last snapshot does not hold exactly the packages the arm enables, or a package's
    record is not for the completed turn, is in another mode, regime or boundary, or (for the
    packages whose counters the screen reads: household retail, RS2, PL1, PL3 and RS4) carries
    an undeclared or non-numeric counter. The counters of L2, the workshops, the operating
    wear and L3 are not read and not validated;
  - any snapshot lacks a complete food accounting row per region, L2's frame, (retail arms)
    the retail frame for its source turn, the granaries, the workshop sites or receipts,
    (woodcutting arms) the woodcutting receipts, or L3's totals, or a row is malformed;
  - a provisioned pilot region is also in L2's frame that turn, or an arm without retail
    records it;
  - the frames' pilot region-turns, or their sums of priced-out and offer-short persons,
    own-eaten and sold food and money paid, credited and refunded, differ from the lifetime
    counters;
  - the retail record has no `income_replaced_total`, an alive civilization has no wealth
    Gini, a woodcutting receipt with farm labour away (`away_delivered > 0`) names no food
    accounting row for its home (checkpoint 1's rule; other receipts are not looked up), or
    the bundle cannot be read.
- A simulation that exits non-zero is a failed run (its rc and stderr recorded).
- Constructed-bundle tests: `tests/test_productive_recovery_screens_cp3.py` (oracle chunk
  `household-retail`, native shard 0).

## Incomplete runs and stopping rules

- Every arm runs once per held world. Nothing is tuned after held outcomes are seen.
- If the budget runs out, or a process is killed (a container restart), the unfinished arms
  and worlds are reported as **incomplete** (`report` lists each `not run`; `check
  --metrics` fails), never silently dropped. Finishing them later on the same frozen source
  and extension is allowed only if no report of the held outcomes has been read: `run
  --checkpoint 3 --resume` in the same output directory runs only the arms and worlds without
  a row, refuses another source commit, `chronicler` path, extension, interpreter or
  checkpoint, and never repeats a recorded run. The restart is recorded as an amendment.
- A run that raises or fails extraction is recorded as failed with its error and is not
  rerun silently. A failure in the held runs is a finding, investigated and reported; a fix
  would need a new held cohort to be evaluated.
- No significance claims.

## Timing pilot

One run of every arm on the two pilot worlds (template 5, procedural 19), at most 2
concurrent processes, to set the budget and find defects. Its outcomes are not used to
choose arms, outcomes or parameters.

- **Run** 2026-11-06 (04:36:33–04:38:08 UTC) by PL6d on `ad0e4dcf` (`src` and
  `chronicler-agents` identical to `claude/household-retail` `12ad9a1e`; later commits change
  only the examples finder, tests and documentation, not the runner), native extension `101a4cd5…`
  (`~/.venvs/native-hrn2`, matching this branch's Rust), CPython 3.13, 2 concurrent processes
  on a shared 4-core machine. The pilot's metrics and report are kept outside the repository.
- **All 12 runs succeeded and every outcome extracted** (no rc 3; `check --checkpoint 3
  --metrics --cohort pilot` passes). In every retail arm the frames' pilot region-turns and
  their priced-out, offer-short, food and money sums equal the lifetime counters. The
  controls behave as declared on both worlds: `CH_cut` delivered no timber, `CH_unpaid` paid
  no granary wages, `CH_free` priced nobody out and replaced no income, `CH_L2` wrote no
  retail record and C0 no woodcutting, crew or remittance record. Every package of every arm
  was active.
- **Seconds per run** (simulation, then extraction in the runner process): template 6.9 on
  average (6.4–7.6) plus 1.5 (1.0–1.9); procedural 18.5 (15.6–21.1) plus 3.4 (2.8–3.8).
  152 s of simulation and 30 s of extraction in total, 96 s of wall time. `CH` is the slowest
  arm (procedural 21.1 s against C0's 15.6 s).
- **Projection for the held cohort** (72 runs): **0.30 core-hours** of the 2.0 proposed,
  roughly 6 minutes of wall time at 3 concurrent processes. Disk: a procedural `CH` run on
  development world 31 leaves 33 MB (22 MB bundle) before deletion, under 0.1 GiB at 3
  concurrent; one procedural extraction peaks near 380 MB of memory. `metrics.jsonl` holds
  about 7 KB per run (per-region arrays for the fixed region sets).
- **Defects found:** one in the extractor before the pilot, none in the simulation. On a
  constructed bundle a snapshot without L3 totals read as no extraction in the shared metrics
  (only a missing record failed). The checkpoint-3 extractor now names it (`timber_stock:
  totals missing at turns […]`); every real snapshot carries totals.
- **Definitional point found while checking the report, recorded as open question 1 (settled
  by lead decision 1), not changed by the lane:** as the design anticipated, the arms' coverage differs (on the pilot worlds CH had
  more pilot region-turns than CH_unpaid and several times C0's). The either-arm sets, the
  both-arms set and the rate were defined before the pilot.
- The lane read the pilot report while checking for defects and changed no arm, outcome,
  parameter or budget in response.

## Amendments

Before the freeze (2026-11-06, lead), from the independent review of the runner
(no blocker; no screen outcome changed on the pilot or development bundles):

- `--resume` now also refuses a directory whose recorded run header (`source.txt`) names
  another checkpoint or cohort, so a run killed before its first row cannot be continued as
  another screen (the check read rows only).
- Every fixed region set's size, its regions pilot in both arms and both arms' coverage are
  reported (they were computed but not printed for `CH − CH_free` and `CH − C0`): 81
  outcomes.
- Two rc-3 rules are stated as the code applies them: counters are validated for the
  packages the screen reads, and the woodcutting home check covers receipts with farm labour
  away.

After the freeze: none. Any later change to the arms, outcomes, analysis or budget is
recorded here as a dated amendment with its reason, and only before the first held run.

## Lead decisions (2026-11-06, before the freeze)

The lane's six open questions, settled by the lead on the checkpoint-3 integration branch
(`claude/productive-recovery-cp3`), before any held run. The pilot was rerun on the final
source after them (Timing pilot, below).

1. **The primary for `CH − CH_unpaid` is the rate**: priced-out person-turns per pilot
   person-turn in the pilot regions of either arm. The question is whether the wage reaches
   food for the people who face prices; the whole count also counts the people the paid
   crews bring under prices, which is the `paid_work` boundary's coverage, not the wage's
   effect on those households. The whole count, the both-arms set and the coverage stay as
   secondaries, and the rate's own composition effect is stated where it is read.
2. **No primary for `CH − CH_L2`.** Checkpoint 2 already made retail against L2 primary
   (`R − L2` ration shortfall); two primaries keep this screen about the chain's links.
3. **Money stays gross and is renamed** "money credited to households (gross)". The crews'
   withheld ordinary income is reported beside it as three counters (PL1, RS2, PL3), not
   subtracted, because PL3's counter does not split its granary and workshop crews and its
   workshop part overlaps RS2's; a sum would double-count. The remittance senders' net debit
   (credited + fee) is a new secondary, so the wage-against-withheld and
   credited-against-debited comparisons can be read from the report.
4. **The union rule is kept**: it reduces to checkpoint 2's rule when the control has no
   pilot region and is checkpoint 1's either-arm rule otherwise.
5. **No identity control.** Checkpoint 2's held identity control (`R_rec − L2`, exact in
   12/12 worlds) covered retail's `record_only` mode, and feature-off identity and exact
   resume of the integrated source are checked with the repository's identity tools before
   the merge, not as a screen arm.
6. **Merged first**: the runner, its tests and this file are on the integration branch
   (merged with `main` `96c20439`) before the freeze, and the frozen commit is recorded below.

## Results (held cohort 3, 2026-11-06)

Run on the frozen source from a separate worktree at the freeze commit `5dd03207` (simulation
source identical to `main` `96c20439`), native `101a4cd5…`, 3 concurrent processes: **72
runs, 0 failed, every outcome extracted** (`check --checkpoint 3 --cohort held` passes), 932 s
of simulation and 243 s of extraction (**0.33 of the 2.0 core-hours**), 403.5 s of wall time.
Nothing was rerun or resumed. Evidence: [`metrics.jsonl`, `report.md`,
`source.txt`](productive-recovery-screens-cp3/).

Each line gives the mean per world, its range, and worlds above / below / at zero, template
(t, 721–726) then procedural (p, 821–826). A world is unknown where a measure has no event
(listed in the report). In template worlds 722 and 725 no arm paid anyone for repair work,
so no region joined the `paid_work` pilot and no expedition launched: the chain never
started there (as in checkpoint 1, template worlds remain timber-poor). Most template
outcomes are therefore zero in two worlds.

**Does timber matter?** (`CH − CH_cut`: the same expeditions, crews, wages and labour away,
without cutting.)
- **Primary, granary mean condition (run mean): +0.028 t [0, +0.090] (4/0/2), +0.075 p
  [−0.026, +0.188] (5/1/0).** At the end: +0.017 t (mixed), +0.088 p (5/1/0). Workshop mean
  condition +0.042 t (3/1/2), +0.120 p (5/1/0).
- Timber delivered +18.9 t (4/0/2), +225 p (6/0/0); RS2 used +22.8 t, +164 p; `no_timber`
  stalled project-turns −102 t (1/3/2), −278 p (0/6/0). Completed repairs rose from 5.5 to
  8.5 t and from 22.8 to 43.0 p per world.
- **Most stalls still lack timber**: CH still has 937 t and 1,654 p `no_timber` project-turns
  per world (76–78% of its stalls). Expeditions were refused for no forest of the civ 520 t
  and 784 p times per world, and for a depleted forest 111 t and 364 p times.

**Does the wage reach food?** (`CH − CH_unpaid`: the granary crews' coins paid or sunk.)
- **Primary, priced-out person-turns per pilot person-turn: +0.00025 t [0, +0.00072] (3/0/1,
  2 unknown), −0.0029 p [−0.0187, +0.00058] (5/1/0).** The procedural mean is one world (824,
  −0.0187); the other five are higher under `CH`. Paying the crews did **not** lower the
  rate at which people facing prices were priced out; in most worlds it was slightly higher.
  The rates are small in both arms (pooled over worlds, `CH` 2.4 × 10⁻⁴ t and 5.6 × 10⁻⁴ p).
- Whole count +3.8 t (3/0/3), −67.7 p (5/1/0); in the regions pilot in both arms +1.8 t
  (2/0/2), −86.2 p (5/1/0); children +0.3 t, +3.5 p (mixed). Ration shortfall and mean ration
  are mixed (−3.2 t, +106 p rations; ±0.005).
- **Coverage moved most**: wages put more regions under prices, so `CH` covered 0.82 t and
  0.83 p of the set's region-turns against 0.46 and 0.51 for `CH_unpaid` (pilot person-turns
  +5,763 t, +27,840 p).
- **Money**: wages to named repair workers +122 t (4/0/2), +790 p (6/0/0) coins per world, of
  which granary-crew wages +127 t, +805 p. The crews' withheld ordinary income is far smaller
  (in `CH`, PL1 23 t / 133 p, PL3 13 t / 92 p, RS2 2 t / 8 p coins per world, PL3 and RS2
  overlapping), so the paid workers' households gain. But the wider pilot replaced more farm
  income (+448 t, +2,059 p coins), and **money credited to households (gross) fell −353 t
  (1/3/2), −1,153 p (1/5/0)**. Remittances changed little (−29 t, +103 p, mixed).
- Granary mean condition ±0.02 (mixed), as checkpoint 1 found for paid against unpaid crews.

**Cash pressure with the whole chain on** (`CH − CH_free`): priced-out person-turns +3.8 t
(3/0/3), **+34.3 p [+9, +97] (6/0/0)**, children +0.3 t, +6.5 p (4/0/2); ration shortfall
+306 t (2/2/2), +633 p (5/1/0); mean ration −0.011 t, −0.004 p (1/5/0 p). Fewer than at
checkpoint 2's `market` boundary (+452 t, +339 p against `R_free`): at `paid_work` prices
apply where households have wages, and relief stays on.

**Retail against free allocation** (`CH − CH_L2`, over CH's pilot regions): ration shortfall
+162 t (3/1/2), −1,140 p (2/4/0); food shortfall after relief +78 t, −587 p; population −4 t,
−2.7 p; all mixed, **a null**, as at checkpoint 2.

**The chain's total** (`CH − C0`): granary mean condition +0.023 t (4/1/1), +0.033 p (4/2/0);
wages to named workers +159 t, +1,076 p (6/0/0 p); priced-out person-turns +3.8 t, +33.3 p
(6/0/0 p); ration shortfall +219 t, −476 p (mixed); money credited (gross) +141 t (4/2/0),
−1,053 p (2/4/0); population −11.7 t (1/5/0), +17.2 p (4/2/0). `C0`'s pilot covered only 0.25 t
and 0.19 p of the set's region-turns (RS2 workshop wages alone).

**Tradeoffs.**
- *Farm labour*: `CH` crews were away 32 t and 247 p farmer-turns per world. Against
  `CH_cut`, which takes the same labour by design (it launches more: −8.8 t, −42.3 p
  expeditions), the woodcutting homes' food shortfall after relief is a null (−0.15 t
  (2/2/2), +54.6 p (3/3/0)); the home-region shortfall share on away turns is 0.37 t and
  0.18 p in `CH`, 0.36 t and 0.17 p in `CH_cut`. No food cost of the cutting itself is
  detectable. The labour cost is in both arms and is not separated from a no-expedition arm
  here; checkpoint 1's `TS_cost − RP` was also a null (+36 t, +21 p food), which is not
  evidence that the labour cost is zero.
- *Forest pressure*: L3 extraction +41 t (4/0/2), +212 p (5/1/0). The lowest stand share
  after a `CH` cutting turn is 0.86 t [0.72, 1.00] and **0.58 p [0.51, 0.70]**: procedural
  stands fall to about half of capacity, above the guard. Against `CH_cut`'s stands (no
  cutting) the minimum is +0.13 t (4/0/0) and −0.003 p (3/3/0).
- *Scarce budgets*: RS2 projects stalled for coins 48 t and 237 p project-turns per world in
  `CH` (fewer than `CH_cut`'s 50 t and 364 p); expeditions refused for coins 0.2 t and 17.8 p.
  Timber, not coins, remains the binding constraint.
- *Families priced out*: priced out in every procedural world (above). Under `CH`, 34.3 p
  person-turns per world, 6.5 of them children; 3.8 t.

**What this does and does not show.** On fresh worlds every link of the chain occurs where
the chain starts (4 of 6 template worlds, 6 of 6 procedural): communities short of timber
send paid crews, cut and carry timber, and repair granaries and workshops measurably better
than the same crews without cutting; the crews and woodcutters are paid by id, and their
households gain far more than the ordinary income they give up. **What the screen does not
find is the last link at the community scale**: at the `paid_work` boundary the wage brings
more households under prices, the model farm income retail replaces outweighs the wages
paid, and the rate of people priced out does not fall. Families are priced out in small
numbers in every procedural world, children among them. Template worlds stay timber-poor.
These are bounded screens on six worlds per stratum, not qualification; no default is
promoted and no constant was tuned.
