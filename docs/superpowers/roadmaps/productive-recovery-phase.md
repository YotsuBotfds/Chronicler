# Productive recovery and household livelihoods — phase plan

Owner instruction (2026-11-05, after PR #77): make recovery work, then make income
matter for food, as consecutive checkpoints of one continuous assignment with
independent review and evidence throughout.

1. **Make recovery work.**
   - Timber supply and delivery: trace whether repair shortages come from production,
     location, existing commitments or depletion, then build a bounded response with
     real labour and ecological costs.
   - Apprenticeship and maintenance: find why people leave and separate training's
     effects from the maintenance assumptions before tuning anything. Success means
     graduates do useful work, not that a counter rises.
   - Budgets and opportunities: check whether funding binds once timber arrives, and
     whether veterans have work where they live.
2. **Make income matter for food.** Real household food retail (L6b): producer
   ownership, inventories, payments and consumption timing that agree, with particular
   care for poorer households and public relief.

The chain the simulation should be able to tell: a community needs timber, shifts
labour to obtain it, repairs a granary, pays workers, and those households can buy food.
The tradeoffs stay visible: less farm labour, forest pressure, scarce budgets and
families priced out.

Terms carried over from the previous owner instruction:
- branches, commits, PRs and gated merges after independent review and green CI;
- no direct push to `main`, no unrelated merges, no bypassed protections;
- new behaviour opt-in and off by default, with feature-off identity to `main`;
- no default promotion, and no 200-seed or procedural qualification gates without
  asking. Bounded screens, including procedural worlds, are in scope;
- no purchases, deployments, credential or sharing changes.

## 0. Seeds

| Use | Template (8 regions, 4 civs) | Procedural (32 × 10) |
| --- | --- | --- |
| Development, inspected freely | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 |
| Development, viewer QA batches only | 12, 13, 14 | — |
| Timing pilot (this phase) | 5 | 19 |
| Held cohort, checkpoint 1 (recovery) | 701–706 | 801–806 |
| Held cohort, checkpoint 2 (retail) | 711–716 | 811–816 |
| Held cohort, checkpoint 3 (integrated chain) | 721–726 | 821–826 |
| Never run (earlier held cohorts and pilot) | 2, 101–106, 301–306, 501–506 | 201–206, 401–406, 601–606 |

Seed numbers are per stratum: procedural 302 and 303 are development worlds, while
template 301–306 were the sprint-2 held cohort. The checkpoint-1 viewer QA (PL5a) first ran
its Batch Lab check on template seeds 1–3, which includes the previous phase's pilot seed 2;
it was a viewer check whose outcomes were never read, and the script now uses 12–14.

## 1. Diagnosis (PL0)

Four read-only lanes on `main` `1ec0876e`, native `6c675042…`, development worlds only.

- **D1 timber trace** (36 runs: 12 development worlds × base, `--timber-stock`,
  `--clearing-protection`; instrumented runs byte-identical to plain runs; the rebuilt
  native timber balance closes per region and tick; scratch tables in the lane's
  `tables_*.md`).
  - *Order of operations.* RS2 holds free timber in Phase 2 before the native tick, so
    it only ever uses stock left by the previous tick. That tick's output first goes to
    crafts, decay and the per-region stock cap (2.5 × population), then ships and
    conquest, then merchant reservations. Merchants carry one load one hop a turn, and
    RS2's need is not market demand.
  - *Causes of the 17,571 `no_timber` stalled project-turns* (98% of all stalls):
    - production 63%. In 54% the civ has **no timber slot at all**; in 8% its forests are
      healthy but nobody works them;
    - depletion 19% (forest cover lost to clearing on the slots people work; the L3
      stock binds in only 0–12% of timber-slot region-turns);
    - location 9% (18% at looser thresholds);
    - consumed by other sinks 6%.
    Production is the largest cause in 12 of 12 worlds and under every arm and threshold.
  - *Scale.* After turn 50 the whole world produced 0–378 timber against 290–885 of
    wear on open granary projects, in every base world. Granaries need 40 timber per
    unit of condition (`grain_storage.py` rules, pinned).
  - *Labour.* The food-first floor binds in 38–100% of worked timber-slot region-turns,
    but 74–100% of stalled regions have no timber slot. Moving one farmer from food to
    timber gains 0.19–0.75 timber and loses 0.27–1.02 food.
  - *RS5 exposes location.* With protection, output doubles, but RS2's timber use rises
    37% and stalls fall 5%; up to 1,650 timber per world is discarded at the stock cap in
    forest regions while the same civs' granaries stall.
  - *Candidates* (single-turn ceilings at the stalls). A labour signal on the region's own
    slot or reserving timber ahead of other sinks supplies the full want in ≤ 2%. A paid
    civ-internal haul: 0–15% (0–28% with RS5). Named woodcutters on the civ's best slot
    plus the haul: 0–37%. Buying timber in coin (as ships do) would create timber from
    nothing and is rejected.
- **D2 apprenticeship exits and wear attribution** (84 runs, 7 arms × 12 development
  worlds, 0.35 core-hours; tables in the lane's scratch `tables.md`).
  - *Why people leave.* Attendance requires presence in the site's **city**, and city
    membership is re-derived from grid position every tick (`tick.rs:2149-2167`), so
    24–27% of a workshop city's adults leave the city each turn while staying in the
    region. The rate is the same for crew, apprentices and qualified people;
    apprenticeship does not cause leaving.
    - Endings (template / procedural): migrated 42% / 38%, departed 22% / 25%, died
      10% / 12%, dropout 7% / 7%, completed 3% / 1%. 62–65% end after 1–2 attended turns.
    - Missed turns: away from the city 61–65%, no qualified person on the crew 31–32%.
    - Even with a mentor present every turn, only 6–7% of city entries could reach 10
      present turns.
  - *Wear is the maintenance assumption, not training.* `W_operate` has zero wear on
    operating turns (`workshops.py:282-286`); RS1 adds `OPERATING_WEAR` 0.02.
    TR − W lump repairs +11.7 / +15.5 split into operating wear +15.5 / +17.2, qualified
    upkeep −4.2 / −2.3, seats +0.7 / +1.0, training −0.3 / −0.3. With the wear at zero,
    training changes repairs in 0 of 12 worlds.
  - *Useful work.* 15 and 5 graduates from 538 and 464 enrolments; aboard 4.2% / 0.9% of
    operating site-turns; 1.8% / 0.5% of the wear offset. 70–83% of operating
    site-turns have nobody qualified on the crew; 80% of qualifications end in death
    within the run. The qualification gates only upkeep and mentoring.
  - *Implications.* Make operating wear a workshop maintenance assumption the reference
    arm can carry; count attendance by presence in the site's region; make progress
    portable and gap-tolerant; train on the job. Lowering `COMPLETION_TURNS` or raising
    `MAX_GAP` would only raise the counter.
- **D3 budgets after timber; veteran opportunities** (140 runs, 10 arms × 14
  development worlds). The timber override (`ghost`) grants timber to RS2 alone and
  restores the physical stock every other user sees; a naive patch of `_free_timber`
  leaks (RS2 held timber it did not have and overdrew the stock), so every conclusion
  uses the ghost arms.
  - *With timber ample*, granary mean condition rises +0.39 / +0.41 (14 of 14 worlds)
    and workshops +0.32 / +0.28. RS2 then needs 1.4 (template) and 3.8 (procedural)
    timber per turn per world beyond the real free stock.
  - *Without L9, money mostly does not bind*: coins are short on 17–23% of the
    remaining stalls, mainly in poor civs.
  - *With L9 (`--local-budgets`), the repairs envelope binds* (`no_envelope` on 88–93%
    of stalls). The cause is valuation, not budget size: an empty granary, or a
    workshop still above the 0.5 operating gate, relieves nothing, so 64–67% of
    repairs proposals are refused `no_support`. L9's own fixed-shares control raises
    workshop condition 0.345 → 0.857 (template) and 0.284 → 0.705 (procedural).
  - *Workshop repair labour.* Candidates must be adult urban farmers of the site's
    city, about 3.3 per site; candidates are short on 70–78% of workshop project-turns.
  - *Granary projects in empty regions* read as `no_labor` (63% / 31% of granary
    project-turns): RS2 opens and keeps projects where the native farm labour is 0.
  - *Veterans.* 50% / 59% never have an opening in their residence region during their
    eligibility window; another 30–31% have one but are ineligible (about 40% are
    still Soldiers; others are rural, minors, or under another ruler). No eligible
    veteran went unplaced under priority. 23–36% of veteran-turns are in forested
    regions with no workshop site. The null is opportunity first, then no contention.
  - *Coins* are 95% granary material charges; repair wages are tiny, and granary
    labour is anonymous and unpaid.
- **D4 household food retail design (option R)**: the full design, with measurements on
  15 development worlds, is [household-retail-design.md](../../integration/household-retail-design.md).
  Its numbers come from a first-order shadow that replays retail on feature-off runs
  without feedback; they choose the boundary and the relief default and are not
  effect estimates.
  - Owners' households would eat 70–74% of food from their own title; 21–25% is
    bought. Ration price at the clamped economy price: median 0.35–0.52 wealth.
  - At that price farmers' sales are 1.1–1.5× the model farm income they lose; a
    cost-based price would cut farm income by 55–60%.
  - Exposure is structural: 30–36% of children live in an L2 household with no adult
    in the region. Without relief 4.7–5.1% of household-turns fall below their
    free-allocation share for lack of cash; the relief default below brings that to
    0.7–0.9%.
  - RS4 remittances equal 16–22% of what households spend on food; L6a and RS2 wages
    about 0.5%. The chain "pay workers, those households buy food" therefore needs
    paid, named recovery work at a larger scale than today's wage channels.

## 2. Packages

Every package is a livelihoods switch with a cost-retaining or record-only control,
appended to `LIVELIHOODS_SWITCHES`, off by default, requiring `--agents hybrid`.

| Id | Switch (modes; first = default when on) | Mechanism | Checkpoint |
| --- | --- | --- | --- |
| PL0 | — | Diagnosis, plan, board, seams, switch registry (lead) | 1 |
| PL1 | `--timber-supply` (`supply`, `cost_only`) | Named, paid woodcutting crews from the community that needs timber, cutting at a forest of its civ and carrying the timber home | 1 |
| PL2 | `--operating-wear`; RS1 rules version 2 | Operating wear as a workshop maintenance assumption the reference arm can carry; apprenticeship retention by region, portable progress, training on the job | 1 |
| PL3 | `--recovery-crews` (`paid`, `unpaid`); `--maintenance-obligation` (`reserve`, `reserve_only`) | Named, paid recovery crews from the region (veterans among them); L9 maintenance valued before failure | 1 |
| PL4 | `--household-retail` (`retail`, `no_relief`, `free_exchange`, `record_only`) | Producer title of new harvest, owned food, paid provisioning, income replacement, relief | 2 |
| PL5 | — | The integrated chain, viewer panels, Batch Lab and live options, browser QA | 3 |
| PL6 | — | Examples and preregistered held screens per checkpoint; handoff | 1–3 |

### PL1 timber supply (`--timber-supply`)

Grounded in D1 and D3: production, not placement, is short, so a response must add
harvest where forest stands and carry it to the repairs. The labour cost lands on the
community that needs the timber, and the harvest goes through the forest's own
accounts.

- **Requires** `--agents hybrid`, `--repair-projects` and `--timber-stock` (L3). L3 is
  the ecological account: without it a harvest debits nothing, since the base model
  has no harvest-driven cover loss.
- **Need.** Each turn, per civ, the timber its open RS2 projects could use at their
  per-turn caps beyond the free timber, the earmarked store and the timber already in
  transit or being cut.
- **Expeditions.** A named crew of adults resident in the needing asset's region
  (veterans first among the eligible, through RS3's priority ids; farmers and other
  non-enlisted occupations) travels to a forest. The forest is a timber slot of a
  region the civ controls, or an uncontrolled region, never another civ's, within a
  declared number of hops. The crew cuts for a declared number of turns and carries
  the timber home. Each turn of the expedition the crew is reserved in the work
  registry (`repair` category), paid `repair_wage` from the controller's treasury,
  and has its paid share withheld from ordinary income.
- **Native seam** (pinned `economy.rs`, `ffi/mod.rs`; lead witness layers). Two
  optional per-region columns, absent → every output's bits unchanged:
  - `woodcut_labor_away`: headcount farm labour removed from the crew's home region
    (as `granary_work_requested` removes it), with the delivered amount returned.
  - `woodcut_labor`: headcount added to the forest region's timber slot on its own
    labour curve. The crew's output is the marginal harvest, reported as
    `woodcut_output`. It counts in the slot's output, so the L3 extraction account
    debits it, but it does not enter that region's stockpile.
- **Cargo and store.** Cut timber travels home with transit decay per hop and is
  credited to an RS2-earmarked store in the asset's region. RS2 reads it as free
  timber ahead of the stockpile, and nothing else can take it. Timber left in the store
  when the region has no open project is released to the stockpile, recorded.
- **Ecological guard, declared.** No expedition cuts a stand whose L3 stock is below a
  declared share of its capacity; the refusal is recorded `forest_depleted`.
- **`cost_only` control.** The same expeditions, crews, travel, wages and home labour
  removal, but no cutting labour is applied, so no timber is produced and no stock is
  debited.
- **Records.** Need, expeditions by state and stage, cargo cut, lost in transit and
  delivered, wages, home farm labour removed, forest stock before and after, refusals
  with reasons (`no_forest`, `forest_depleted`, `no_crew`, `no_coins`, `too_far`).

### PL3 budgets and opportunities

Grounded in D3.

- **`--recovery-crews`** (`paid`, `unpaid`; requires `--repair-projects`).
  - RS2 granary work is done by a named crew of adult farmers resident in the granary's
    region. Their farm time is the labour the native step already removes, now with
    identities, reserved in the `repair` category. In `paid` mode the granary's
    existing coins per work, which today leave the economy as a material charge, are
    paid to that crew as `repair_wage` by stable id, so no new money is created.
    `unpaid` keeps the same crews, the same charge and the sink: it isolates the
    wage channel to households.
  - The workshop repair crew pool widens from the site's city to adult farmers of the
    site's region, and admits adult RS3 veterans of any non-enlisted occupation, with
    their paid share withheld.
  - RS3 veterans are eligible for woodcutting crews (PL1) on the same terms.
- **RS2 correction (unconditional while RS2 is on).** A granary project is not opened,
  and an open one is suspended, while its region's farm labour is zero, recorded
  `no_people`. This removes the empty-region artifact D3 found.
- **`--maintenance-obligation`** (`reserve`, `reserve_only`; requires
  `--local-budgets` and `--repair-projects`). Before L9 bargains, each civ reserves a
  bounded maintenance obligation, through L9's existing `obligations` path, equal to
  RS2's planned per-turn charges for its open projects, capped at a declared share of
  the budget. `reserve_only` makes the same reservation but leaves RS2 limited to its
  bargained envelope, with the unspent reservation returned. It shows the crowding-out
  cost without the repair benefit.

### PL2 apprenticeship retention and the maintenance assumption

Grounded in D2; no constant is changed to raise a counter.

- **`--operating-wear`** (new, requires `--workshops` in `operate`). Funded operating
  sites lose `OPERATING_WEAR` (0.02, moved unchanged from RS1) per turn, offset only by
  qualified upkeep. RS1 keeps implying it, so RS1 runs keep the same wear; `--workshops
  --operating-wear` without RS1 is the reference arm `W_wear` that the held screens
  lacked. (Review B: RS1 trajectories do change under the version-2 rules below;
  `--apprenticeship-rules 1` reproduces version 1 byte for byte.)
- **RS1 rules version 2** (`train` and `no_qualification` both).
  - Attendance counts presence in the site's **region** (the community RS1 already
    names), not the positional city box.
  - Progress is portable: a migrant continues at an operating site of the new region;
    missed turns pause progress and only a long absence (declared) ends it. The
    consecutive-miss dropout goes.
  - Training on the job: the apprentice works on the crew, and a turn counts when a
    qualified member is aboard. Exclusive pre-crew seats, which displaced about 170
    crew-turns per world, go.
  - The lane may propose an age rule for who is taken on, justified by the D2 finding
    that 80% of qualifications end in death within the run, not by held outcomes.
  - Version 1 checkpoints either resume under the rules they recorded or are refused
    visibly; nothing changes silently.
- **Success measure** against `no_qualification` under the shared wear: graduate
  crew-turns on operating sites and operating site-turns covered by a qualified
  member (primary); upkeep offset, full-offset site-turns and repairs (secondary);
  qualifications by both routes so crowding out shows.

### PL4 household food retail (lead decisions on the D4 design)

1. Build option R now, as designed, off by default.
2. Boundary `--household-retail-boundary`: `market` (each civ's capital region at the
   turn it first qualifies, sticky until the region has no controller; default),
   `paid_work` (regions that have had an open L6a firm or a paid recovery crew,
   sticky), `all` (stress).
3. Fair-share round, then the open round; owners never eat beyond the fair share while
   a paying neighbour is below it.
4. Price: the economy's post-trade food price clamped to [0.5, 3.0] × 0.5 per ration.
   No cost-rule arm in this phase.
5. Relief default: commons and granary release always free, θ = 0.9, means-tested free
   pool, child-only households pay from their own wealth. Ruler relief purchases are
   deferred.
6. A dead owner's claim passes to the spouse, else equally to living children in the
   region, else to the commons; deterministic, conserving, and checked against the
   native estate rule on the real extension. Any disagreement is documented.
7. Merchants load commons only in this phase; the foregone exports are recorded.
8. Granary procurement buys owners' unsold grain through one pinned seam and pays
   them by id.
9. Conquest destroys the conquest share of owned stock; occupation and siege
   requisitions of owned stock are a declared limit, counted.
10. Child farmers hold their own title by id.
11. Evidence bar: feature-off identity, exact resume, development screens of every mode
    × boundary, then a fresh held cohort before any claim.

**FFI contract (binding on both retail lanes; changes go through the lead).** Food
in milli-food (1000 = one food unit = two rations), money in milli-units.

- Economy region batch, optional Float32 input columns present only when retail is
  on: `retail_title_share` (θ; null = not a pilot region) and
  `retail_owned_{grain,fish,salt,botanicals,exotic}` (owned stock at opening, food
  units). Result columns appended only when those inputs exist:
  `retail_titled_<good>`, `retail_owned_close_<good>`, `retail_owned_decay_<good>`,
  `retail_owned_overflow_<good>`, `commons_consumed`, `commons_sufficiency`. Absent
  inputs leave every existing output's bits unchanged.
- `set_household_retail(source_turn: u32, mode: u8, regions: Vec<(u16, i64, f64)>,
  claims: Vec<(u32, u16, i64)>)`: regions are (region, price in milli per ration,
  free rations from the commons draw-down and release); claims are (owner id, region,
  milli-food). Mode 0 retail, 1 no_relief, 2 free_exchange. Validates before
  mutation; refuses a pending install. `cancel_household_retail() -> bool`.
- `take_household_retail_frame() -> Option<(u32, Vec<String>, Vec<Vec<f64>>,
  Vec<(u32, u16, i64, i64)>, Vec<(u32, i64, i64, i64)>, Vec<(u32, u16, u32, f32, f32, u8)>,
  usize)>`: source turn, region column names and rows, claim rows (owner, region,
  own-eaten milli-food, sold milli-food), money rows (id, paid, credited, refunded),
  a bounded person sample (id, region, household key, ration, fair share, status 0
  fed, 1 priced out, 2 offer short) and the sample rows dropped. Taken once.
- `install_retail_income(turn: u32, regions: Vec<u16>)`, `cancel_retail_income() ->
  bool`, `take_retail_income_receipt() -> Option<(u32, Vec<(u32, f32)>)>`: the wealth
  phase records and zeroes the remaining ordinary farm income of pilot farmers.
- Transfer purposes appended: `food_purchase` (5), `food_procurement` (6).

## 3. Ownership

| Lane | Owns (may edit) | Reads, or edits only through a named seam |
| --- | --- | --- |
| Lead / integration | `simulation.py`, `livelihoods*.py` registry conflicts, `batch_manifest.py`, `tuning.py`, witness layers, test enrollment and manifests, board, ledgers | — |
| PL1 timber | `timber_supply*.py`; the PL1 seam in `repair_projects.py` (`_free_timber` and holds read the store); `economy.rs` and the economy columns in `ffi/mod.rs` (minimal, listed for witness layers); the L3 read seam in `timber_stock.py` | RS2, RS3 APIs |
| PL2 wear and RS1 | `operating_wear` registration, `apprenticeship*.py`, the operating-wear seam in `workshops.py` | payroll, registry |
| PL3 crews and funding | `recovery_crews*.py`, `maintenance_obligation*.py`, the crew sections of `repair_projects.py`, the `obligations` seam in `local_budgets.py` | RS3 APIs |
| PL4 retail native | `economy.rs` retail columns, `provisioning.rs`, `tick.rs`, `pool.rs`, `wealth_transfer.rs`, the retail methods in `ffi/mod.rs` | the FFI contract above |
| PL4 retail Python | `household_retail*.py`, `food_allocation.py` seam, `feature_catalog.py` row, the procurement seam in `grain_reserves.py` | the FFI contract above |

Each lane registers its own switch with append-only edits to the registry lists, and
the lead resolves the merge. Pinned edits are kept minimal and listed in the lane's
handoff, and the lead records the witness layers.

## 4. Obligations for every package

- Tests that fail on wrong behaviour, with real-native cases wherever native code runs.
- Adversarial lifecycle cases: death, migration, return, remobilisation, controller
  change, site closure, slot reuse, pool reset.
- Money and material closure every turn: no double spend, no double-paid time, no
  timber or food from nothing.
- Failed-tick rollback, duplicate and stale receipts, and exact checkpoint/resume in
  the middle of live expeditions, crews, claims and ledgers.
- Correct enrollment: offline chunks with headroom, or the native shard manifest.
- Strict viewer readers, where missing data is unknown rather than zero.
- An integration page in `docs/integration/` for each package.
- Feature-off identity against `main` with the correct extensions and checkout roots.
- Declared constants are named as declared; nothing is tuned on held worlds.

## 5. Checkpoints

1. **Recovery** (PL0–PL3): PR from `claude/productive-recovery`, with independent
   review, identity, development examples and a preregistered held screen on cohort 1.
2. **Household food retail** (PL4): its own PR after checkpoint 1 merges, with
   independent review, identity, development screens of every mode × boundary and a
   held screen on cohort 2.
3. **The integrated chain** (PL5, PL6): viewer, options, browser QA, the chain screen
   on cohort 3, and the handoff.

Not in this phase: the 200-seed and procedural qualification gates, default
promotion, infrastructure repair, new combat events, and cross-civ timber trade.

## 6. Status (2026-11-06): checkpoint 1

PL0–PL3 are integrated on `claude/productive-recovery` with witness layers `pl2`, `pl1`,
`pl3` and `pl2b`; the checkpoint-1 viewer (PL5a) is merged; PL4 waits for checkpoint 2.

| Package | Switch (modes) | Lane, then review fixes | Page |
| --- | --- | --- | --- |
| PL1 timber supply | `--timber-supply` (`supply`, `cost_only`) | `claude/pl1-timber`, `claude/pl1-fixes` | `docs/integration/timber-supply.md` |
| PL2 wear and RS1 v2 | `--operating-wear`; `--apprenticeship-rules` (`2`, `1`) | `claude/pl2-apprenticeship`, `claude/pl2-fixes` | `docs/integration/operating-wear.md`, `apprenticeship.md` |
| PL3 crews and funding | `--recovery-crews` (`paid`, `unpaid`); `--maintenance-obligation` (`reserve`, `reserve_only`) | `claude/pl3-crews`, `claude/pl3-fixes` | `docs/integration/recovery-crews.md`, `maintenance-obligation.md` |
| PL5a viewer | none (panels, readers, options) | `claude/pl5a-viewer` | `docs/integration/feature-options.md` |
| PL6a screens | none | `claude/pl6a-screens` | `docs/superpowers/progress/productive-recovery-screens-cp1.md` |

Review, verification and held results are summarized in `docs/CONTINUATION.md` and the
screens page. Merging does not qualify any of it scientifically.

## 7. Status (2026-11-06): checkpoint 2

Checkpoint 1 merged as #78 (`dde5c004`, record #79). PL4 household retail is integrated on
`claude/household-retail` with witness layer `pl4`, the retail viewer (PL5b) and the
checkpoint-2 screens (PL6c, cohort 2, frozen before running). The lead's PL4 decisions in
section 2 hold, with these refinements from review:

- Owned stock carried into a turn decays and the storage cap applies to both pools (commons
  net of merchant departures) at opening, so the fair share `cf` is reachable at 0.7.
- A dead owner's claim is withheld whole for the heirs (status `withheld_dead`), never sold.
- Named crews (PL1 woodcutters, PL3 granary and workshop crews) receive title only for the
  farm time they gave: `w = max(0, u(1 − h) − r)`.
- `paid_work` reads L6a firms, RS2 workshop wages, PL3 granary crews and PL1 home regions.

Results and limits: `docs/CONTINUATION.md` and
`docs/superpowers/progress/productive-recovery-screens-cp2.md`.

