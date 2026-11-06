# Productive recovery, checkpoint 2: preregistered held screens (PL6c)

Status: **FROZEN** by the lead on 2026-11-06, before any held run, on simulation source
`78cf2efd` (branch `claude/household-retail`) with native extension `b1910b94…` (built from
`3ed75f22`; the Rust is unchanged since). Code may change between this freeze and the held
run only to fix a defect, listed as an amendment; no arm, outcome or parameter may change in
response to held outcomes.

**Pilot on the frozen source.** Rerun on `78cf2efd` after the review fixes: 16 runs, 0
failed, every outcome extracted; 175 s of simulation and 36 s of extraction at 2 concurrent
processes; all 17 identity outcomes (`R_rec − L2`) exactly zero on both worlds. The pilot's
outcomes were not read for any other decision.

## Purpose and limits

These are bounded screens on default-off experimental source, not qualification. They
ask whether household food retail (PL4, `--household-retail`) changes who eats in its
pilot regions on fresh worlds, and what it costs and pays, against three controls:
`free_exchange` (the same ownership and timing without cash), `no_relief` (without the
tithe and the means test), and L2 alone (the reference). `record_only` is an identity
control: its trajectory must equal L2's.

- The 200-seed and procedural qualification gates are out of scope and stay unrun.
- No switch is promoted to a default, and no constant is tuned on these worlds.
- Six worlds per stratum support means, ranges and sign counts, not significance tests.
- Trajectories diverge once retail changes who eats, earns or dies, so population,
  treasury and the cross-arm food measures are reported but not attributed to a
  mechanism.

## Units

The independent units are **worlds** (seeds), never agents, households, regions or
turns. Every arm runs once on every held world, and each arm is compared with its
declared control on the same world. Results are reported per stratum: template
(8 regions, 4 civs) and procedural (32 regions, 10 civs).

## Source and budget (proposal)

- **Source.** `claude/household-retail` (or the checkpoint-2 integration branch) at the
  commit the lead records when freezing, and a native extension built from that
  commit's Rust into the interpreter that runs the screen. The runner writes the source
  commit (and whether the tree is dirty), the imported `chronicler` path, the extension
  path and SHA-256, and the interpreter to `source.txt`, after checking that runs import
  the checkout's own `src`.
- **Budget.** At most **2.0 core-hours** in total, at most **3 concurrent processes**,
  and at most **6 GiB of transient disk**. Raw outputs are deleted after extraction;
  `--keep-first` keeps the first world of each stratum outside the repository. The
  timing pilot projects the held run below.
- **Environment.** `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1`, the
  checkout's `src` on `PYTHONPATH` (shared `_run_env`).
- **Command.** `python scripts/productive_recovery_screens.py run OUT --checkpoint 2
  --cohort held --jobs 3`, then `report OUT/metrics.jsonl --checkpoint 2` and `check
  --checkpoint 2 --metrics OUT/metrics.jsonl --cohort held`.

## Seeds

| Use | Template (8 × 4) | Procedural (32 × 10) |
| --- | --- | --- |
| Timing pilot (this phase; shared with checkpoint 1) | 5 | 19 |
| **Held cohort, checkpoint 2** | **711–716** | **811–816** |
| Held cohort, checkpoint 1 (run on 2026-11-06; never again) | 701–706 | 801–806 |
| Reserved for checkpoint 3 (never run here) | 721–726 | 821–826 |
| Earlier held cohorts and pilots (never run) | 2, 101–106, 301–306, 501–506 | 201–206, 401–406, 601–606 |
| Development (inspected freely) | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 |

Seed numbers are per stratum. `check_seeds(CP2)` (run before every `run` and by
`tests/test_productive_recovery_screens_cp2.py`) asserts, per stratum, that the pilot
and held seeds are disjoint from every earlier cohort and pilot (including those the
sprint 1–3 runner declares and checkpoint 1's held cohort, which must be listed as never
run), from checkpoint 3's reserved cohort, from the development worlds and from each
other.

## Arms

Base for every arm: `--turns 200 --agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --grain-storage
--food-allocation` (L2 in its default `floor_means` regime; retail requires it).
Procedural worlds add `--worldgen procedural --regions 32 --civs 10`. The default
boundary is `market` (each ruling civilization's capital region, sticky).

| Arm | Flags added to the base | Control | Question |
| --- | --- | --- | --- |
| L2 | none | — | root: L2 food allocation alone |
| R_rec | `--household-retail --household-retail-mode record_only` | L2 | identity: retail recorded, nothing applied |
| R | `--household-retail` | R_free | what payment and income replacement do to who eats |
| R_free | `--household-retail --household-retail-mode free_exchange` | L2 | ownership and timing without cash |
| R_norelief | `--household-retail --household-retail-mode no_relief` | R | what the tithe and the means test protect |
| R_all | `--household-retail --household-retail-boundary all` | R_all_free | R under stress: every controlled region a pilot |
| R_all_free | `--household-retail --household-retail-mode free_exchange --household-retail-boundary all` | L2 | R_free under stress |
| R_all_norelief | `--household-retail --household-retail-mode no_relief --household-retail-boundary all` | R_all | R_norelief under stress |

Every arm's command line parses with the real parser and passes the livelihoods
prerequisite checks, enabling exactly the packages, modes and boundary the table names
(`check_arm_flags(CP2)`). Feature-off identity, exact resume and native parity are tested
elsewhere, not as screen arms.

## Outcomes

Each outcome is a per-world paired difference (arm minus control on the same world), or
the arm's own value where no control is named. The report prints every world's value
and, per stratum, the mean, the range and the number of worlds above, below and at zero;
a world whose arm or control failed, or whose value is unknown, is listed as such
(`failed`, `unknown`, `not run`). **Primary** outcomes are marked; the rest are
secondary. The executable list is `CP2.PAIRED` in the runner (76 outcomes, 17 of them
the identity control).

### Definitions

- **Pilot region-turn.** A region-turn whose retail frame row
  (`history[i].livelihoods.household_retail.regions`) carries a native provisioning row
  (`retail`, `no_relief`, `free_exchange`) or a would-be record (`record_only`). A row
  for a region that closed that turn carries neither and is not one. Their number must
  equal the lifetime counter `pilot_region_turns`.
- **Priced-out person-turns.** The sum, over the arm's own pilot region-turns, of the
  native frame column `priced_out_persons`: people below the fair share `cf` whose
  household's fair-share purchases were limited by cash (native status 1, which takes
  precedence when the offer was short too). **Child-turns**: `priced_out_children`.
  **Deficit**: `priced_out_deficit`, the sum of `cf` − ration over those people, in
  rations.
- **Offer-short** and **withheld-dead person-turns**: `offer_short_persons` (status 2)
  and `withheld_dead_persons` (status 3: a dead owner's claim was withheld).
- **Mean ration of pilot persons.** Person rations over person-turns (`rations` ÷
  `persons`) over the arm's own pilot region-turns; pilot person-turns are reported
  beside it as the denominator.
- **Region set (comparisons with L2).** The treatment arm's pilot regions (every region
  with at least one pilot region-turn), summed over all 200 turns in both the arm and L2,
  as checkpoint 1 compared woodcutting arms on fixed region sets. Region identity is its
  index, so the set is stable across arms. The share of the set's region-turns that were
  pilot turns in the treatment arm is reported (`coverage`).
- **Food shortfall after relief.** As checkpoint 1: `demand × max(0, 1 − min(1,
  sufficiency_after_relief))` from each snapshot's `food_accounting.regions`, summed over
  the region set. In a pilot region this sufficiency counts owned food on hand (the
  native economy's availability), so it measures food in the region, not what people
  ate.
- **Ration shortfall.** The sum over provisioned people of 1 − ration, in rations: the
  retail rows' `persons − rations` in pilot region-turns, L2's `shortfall` in the
  regions L2's frame lists, and zero elsewhere (L2 lists only scarce regions; everyone
  in the others has a full ration). Exact in every arm; this is the cross-arm measure of
  what people ate.
- **Mean ration per Phase-2 person.** 1 − ration shortfall ÷ Phase-2 alive
  (`food_accounting.regions[].native_count`), over the region set. This replaces "mean
  pilot ration" in comparisons with L2, because L2's frame does not record the people in
  the regions it leaves out. People who died between Phase 2 and provisioning are in the
  denominator but not in the shortfall, in both arms alike.
- **Owners' sale revenue.** Household purchases credited to owners plus granary
  procurement credited to owners (`credited_milli + procurement_credited_milli`, coins).
  Owners are the titled farmers and their heirs. **Income replaced**: the snapshot's
  `income_replaced_total` (ordinary farm income the wealth phase zeroed), coins. Their
  ratio is reported per world.
- **Money into households.** Procurement credited minus income replaced, coins.
  Household purchases move money between households (`paid = credited + refunded` per
  region), so they do not change the households' total.
- **Structural zero.** L2 has no retail record and R_rec provisions nothing: their
  priced-out, revenue, income-replaced and owned-food values are 0. The extractor has
  verified that L2 wrote no retail record and that R_rec's frames carry no provisioning
  row. A missing record of an enabled package is a failure, never zero.
- **Unknown.** A measure of an event that never happened is unknown (`None`), never 0:
  a mean ration without pilot persons, a revenue ratio without income replaced, a region
  set without Phase-2 people.

### R − R_free: payment and income replacement

- **Primary:** priced-out person-turns in the pilot regions.
- Priced-out child-turns; priced-out deficit (rations); offer-short and withheld-dead
  person-turns; mean ration of pilot persons; pilot person-turns.
- `free_exchange` installs price 0, so its priced-out count is zero by construction; the
  difference is R's own count, reported against the control that keeps the title, the
  rounds and the timing.

### R_norelief − R: what relief protects

- **Primary:** priced-out person-turns.
- Priced-out child-turns; priced-out deficit.

### R − L2: retail against L2 alone

No primary outcome is proposed (see open questions).

- Food shortfall after relief, ration shortfall and mean ration per Phase-2 person, over
  R's pilot regions; final population; final treasury; mean civilization wealth Gini at
  the end; net food transport into R's pilot regions (`food_accounting` `transport_net`).
- R alone (zero in L2 by construction): coverage of the region set; owners' sale revenue,
  with household purchases and procurement separately; income replaced; revenue ÷ income
  replaced; money into households.
- **Merchant food departures foregone (a bound).** R alone: the owned food merchants
  could not load (`owned_food_unloadable_milli`), summed over pilot region-turns. The
  source declares the foregone departures at most this each turn; summed over turns it
  counts stock carried over again, so it is a loose upper bound. Beside it, the commons
  food merchants committed from the pilot regions, R − R_rec: R_rec reproduces L2's
  trajectory and records departures, which L2 does not; the two arms' pilot sets can
  differ as their trajectories do.

### R_free − L2: ownership and timing without cash

- Food shortfall after relief, ration shortfall and mean ration per Phase-2 person over
  R_free's pilot regions; final population.

### R_rec − L2: the identity control

Every one of these 17 outcomes must be **zero in every world**; the report lists any
nonzero or unknown value under "Identity control" as a failure of the control.

- Whether the trajectory differs: SHA-256 of the whole history and final world state
  with the retail records removed (`trajectory_digest`), 1 if R_rec's differs from
  L2's, else 0.
- Food shortfall after relief, mean ration per Phase-2 person, ration shortfall and net
  food transport, over R_rec's pilot regions; population; treasury; wealth Gini.
- Priced-out person-turns, child-turns and deficit; offer-short and withheld-dead
  person-turns; owners' sale revenue; income replaced; money into households; owned food
  merchants could not load.

Proposed rule: an identity failure is a finding, investigated and reported; while it
stands, the comparisons with L2 are reported but not interpreted.

### The all-boundary arms (stress)

The same outcomes, none primary: `R_all − R_all_free` and `R_all_norelief − R_all` as
above; `R_all − L2` and `R_all_free − L2` over their own pilot regions (nearly every
controlled region), with R_all's revenue, income, money and owned-food values alone.

### Shared outcomes and funnels

- Final total population and treasury, arm minus control, mean and range per stratum.
- Every household retail lifetime counter (`CP2.OUTCOMES`), per arm: mean per world with
  range and the number of worlds at zero. Null activation is reported, not hidden.

### Quantities the snapshot does not hold

- **Mean adult wealth in pilot regions.** No per-person or per-region wealth is
  recorded: the retail sample holds rations and statuses, the money rows are aggregated
  to totals before the snapshot, and the final world state holds no agents. The closest
  declared measures are reported instead: treasury and mean civilization wealth Gini
  (`civ_stats.gini`, whole civilizations), R − L2, and money into households (R). A
  direct measure would need a new snapshot field (simulation code; not added here).
- **L2's mean ration in a region it does not list.** Replaced by the ration shortfall and
  the mean ration per Phase-2 person (above).
- **L2's merchant departures.** Recorded only by retail frames; R_rec stands in.

## Extractor validation

- `check_extractor(CP2)` (before every run and in the tests): every counter read is in
  `household_retail_state.COUNTERS`; every frame column read is in the Rust
  `RETAIL_REGION_COLUMNS` or `REGION_COLUMNS` of `chronicler-agents/src/provisioning.rs`;
  every frame field read is a `RegionFrame` field; every food-accounting field read is
  declared; the retail modes are the four the screen knows; both packages are livelihoods
  switches whose mode (and boundary) options and defaults match the registry, and every
  registered choice of a package is checked; every arm's flags are known; every control
  exists and the controls form a tree rooted at L2; every comparison in `CP2.PAIRED` is
  declared (the arm table plus R − L2, R_all − L2 and R − R_rec).
- A run is a **visible failure** (rc 3, the run and the reasons named in `metrics.jsonl`,
  on the console and in the report; `run` and `check --metrics` exit with code 3) when:
  - the run does not have one snapshot per turn 1..200;
  - the last snapshot does not hold exactly the packages the arm enables, or a package's
    record is not for the completed turn, is in another mode, regime or boundary, or
    carries an undeclared or non-numeric counter;
  - any snapshot lacks a complete food accounting row per region (demand, sufficiency
    after relief, transport and the Phase-2 count), L2's frame, or (retail arms) the
    retail frame for its source turn, or a frame row is malformed;
  - a provisioned pilot region is also in L2's frame that turn, or a record_only row
    carries provisioning;
  - the frames' pilot region-turns, or their sums of priced-out and offer-short persons,
    own-eaten and sold food and money paid, credited and refunded, differ from the
    lifetime counters (a frame missing for a pilot region-turn);
  - the retail record has no `income_replaced_total`, an alive civilization has no wealth
    Gini, or the bundle cannot be read.
- A simulation that exits non-zero is a failed run (its rc and stderr recorded).
- Constructed-bundle tests: `tests/test_productive_recovery_screens_cp2.py` (oracle chunk
  `household-retail`, native shard 0).

## Incomplete runs and stopping rules

- Every arm runs once per held world. Nothing is tuned after held outcomes are seen.
- If the budget runs out, or a process is killed (a container restart), the unfinished
  arms and worlds are reported as **incomplete** (`report` lists each `not run`; `check
  --metrics` fails), never silently dropped. Finishing them later on the same frozen
  source and extension is allowed only if no report of the held outcomes has been read:
  `run --checkpoint 2 --resume` in the same output directory runs only the arms and
  worlds without a row, refuses another source commit, `chronicler` path, extension,
  interpreter or checkpoint, and never repeats a recorded run. The restart is recorded as
  an amendment.
- A run that raises or fails extraction is recorded as failed with its error and is not
  rerun silently. A failure in the held runs is a finding, investigated and reported; a
  fix would need a new held cohort to be evaluated.
- No significance claims.

## Timing pilot

One run of every arm on the two pilot worlds (template 5, procedural 19), at most 2
concurrent processes, to set the budget and find defects. Its outcomes are not used to
choose arms, outcomes or parameters.

- **Run** 2026-11-06 (03:00:40–03:02:35 UTC) by PL6c on `a6ae6141` (`src` and
  `chronicler-agents` identical to `claude/household-retail` `fdc1dfbc`; the later
  commits change only the runner, its tests, enrollment and this file), native extension
  `b8a09339…` (`~/.venvs/native-hrn`, built from `claude/hr-native-review` `4ae0ca8a`,
  whose Rust equals `fdc1dfbc`'s), CPython 3.13, 2 concurrent processes on a shared
  4-core machine. The pilot's metrics and report are kept outside the repository.
- **All 16 runs succeeded and every outcome extracted** (no rc 3; `check --checkpoint 2
  --metrics --cohort pilot` passes). In every retail arm the frames' pilot region-turns
  and their priced-out, offer-short, food and money sums equal the lifetime counters.
  The controls behave as declared on both worlds: `free_exchange` moved no money, priced
  nobody out and replaced no income; `record_only` titled, sold and settled nothing.
- **Identity control: all 17 `R_rec − L2` outcomes are zero on both worlds**, and the
  trajectory digests are identical.
- **Seconds per run** (simulation, then extraction in the runner process): template 6.7
  on average (5.9–7.3) plus 0.9 (0.7–1.0); procedural 16.5 (14.2–18.9) plus 4.1
  (3.6–4.5). 186 s of simulation and 40 s of extraction in total, 115 s of wall time.
  Retail arms run up to a third slower than L2 (procedural `R_all_norelief` 18.9 s
  against L2's 14.2 s).
- **Projection for the held cohort** (96 runs): **0.38 core-hours** of the 2.0
  proposed, roughly 8–10 minutes of wall time at 3 concurrent processes. Disk: the
  heaviest arm (`R_all_norelief`, measured on development world procedural 7) leaves
  25 MB per run (16 MB bundle) before deletion, under 0.1 GiB at 3 concurrent; one
  procedural extraction peaks near 300 MB of memory. `metrics.jsonl` holds about 3.5 KB
  per run.
- **Defects found:** none in the runner, the extractor or the simulation.
- Definitional points found while checking the report, recorded under open questions,
  not changed: the withheld-dead status is not like for like between priced arms and
  `free_exchange`; money into households is large and negative by construction; the
  owned-food bound is loose.
- The lane read the pilot report while checking for defects and changed no arm,
  outcome, parameter or budget in response.

## Amendments

- **2026-11-06, after the held run (no change to the held source).** Reviewer D's last check
  found that the opening storage cap read the commons before this tick's merchant
  departures, so in a constructed case departures could drive the cut commons negative and
  the clamp would create food. It never fired in development runs. It is fixed on the
  branch after the held run; whether held results stand for the fixed source is recorded
  below once the byte-identity check of fixed against frozen source on development worlds
  is complete.

## Lead decisions (2026-11-06, before freezing)

1. **R − L2 has a primary: the ration shortfall** over R's pilot regions, in rations (what
   people ate, exact in both arms). It asks directly whether retail makes hunger worse
   than free allocation. The food-accounting shortfall stays secondary.
2. **Wealth stand-ins are accepted** (treasury and civilization wealth Gini, R − L2; money
   into households, R). No new snapshot field is added in this checkpoint; the gap is a
   declared limit.
3. **Money into households is reported as a headline finding, not a defect.** Retail
   replaces farm income the model created with sales that only move money between
   households, so pilot households' total cash falls by about the replaced income, net of
   procurement credit. Every R − L2 outcome is read with that in mind.
4. **Withheld-dead counts are kept as secondary** and labelled not like for like (status 1
   takes precedence over status 3).
5. **The region rule is kept** (the treatment arm's pilot regions over every turn), with
   coverage reported.
6. **Departures:** the realized change in commons departures (R − R_rec) is the measure
   read; the owned-food bound stays as a labelled loose bound.
7. **No primaries under the all boundary**; those arms are the same questions under
   stress, reported descriptively, to keep the number of primaries small.
8. **Identity failure rule adopted**: a nonzero or unknown R_rec − L2 value is a finding,
   and while it stands comparisons with L2 are reported but not interpreted.
9. **Merged first**: the runner and this file are on the checkpoint-2 integration branch
   before the freeze.

## Results (held cohort 2, 2026-11-06)

Run on the frozen source from a separate worktree at `77202dd2` (simulation source as
frozen at `78cf2efd`; the later commit changed one test only), native `b1910b94…`, 3
concurrent processes: **96 runs, 0 failed, every outcome extracted**, 989 s of simulation
and 189 s of extraction (**0.33 of the 2.0 core-hours**). **All 17 identity outcomes
(`R_rec − L2`) are zero in all 12 worlds**, so the comparisons with L2 are interpretable.
Evidence: [`metrics.jsonl`, `report.md`, `source.txt`](productive-recovery-screens-cp2/).

Each line gives the mean per world, its range, and worlds above / below / at zero, template
(t, 711–716) then procedural (p, 811–816), at the default `market` boundary unless noted.

**What payment does** (`R − R_free`, ownership and timing held fixed).
- **Primary, priced-out person-turns: +452 t [+149, +1478] (6/0/0), +339 p [+162, +440]
  (6/0/0).** Children +42 t, +51 p (6/0/0 each); deficit +144 t, +106 p rations.
- Mean ration of pilot persons ±0.01 (mixed): cash pushes a minority below their fair share
  rather than lowering the average.

**What relief protects** (`R_norelief − R`: no harvest share kept commons, no means test).
- **Primary, priced-out person-turns: +1,104 t [+752, +1,786] (6/0/0), +2,832 p [+2,161,
  +4,489] (6/0/0).** Children +150 t, +411 p; deficit +630 t, +1,746 p rations. Relief
  removes most of the cash exposure the mechanism would otherwise create.

**Retail against free allocation** (`R − L2`, over R's pilot regions, all turns).
- **Primary, ration shortfall: −217 t [−1,571, +1,037] (4/2/0), +860 p [−1,904, +4,822]
  (4/2/0): a null.** Neither sign is consistent; the ranges are wide because trajectories
  diverge. Food shortfall after relief (−149 t, +376 p), mean ration (±0.008) and population
  (+11 t, −46.5 p, 1/5/0 in procedural) are mixed too. Ownership and timing alone
  (`R_free − L2`) are mixed as well (+221 t, +589 p rations).
- **Money leaves households**, as the design implies: farm income the model created is
  replaced by sales between households. Income replaced 1,715 t and 5,030 p coins per world;
  owners' sale revenue 1,715 t and 4,876 p (ratio 1.02 and 0.99); net money into households
  **−1,713 t, −5,025 p (0/6/0)**. Granary procurement credited owners only 2–6 coins per world.
- **Merchants** committed 462 t and 2,323 p less food from pilot regions (0/6/0), since they
  load commons only; net food transport into procedural pilot regions rose +423 (6/0/0).

**Under stress** (boundary `all`, every controlled region a pilot): payment adds +1,051 t and
+1,578 p priced-out person-turns (6/0/0); removing relief adds +1,719 t and +6,041 p (6/0/0);
the ration shortfall against L2 is again mixed (+98 t, +442 p); money into households
−2,232 t and −7,187 p.

**What this does and does not show.** On fresh worlds, real retail works as an accounting
system: title, owned food, purchases, payments and income replacement close every turn, and
the identity control holds exactly. Paying for food prices out a minority of people,
children among them, in every world; the default relief (a tenth of each harvest kept
commons and a means-tested free pool) removes most of that exposure; and against free
allocation the net effect on what people ate is not detectable at this size. Because farm
income the model created becomes transfers between households, pilot households lose cash
steadily; whether wages and remittances can offset that is the chain question for checkpoint
3. None of this is qualification; no default is promoted and no constant was tuned.
