# Repair projects (RS2, `--repair-projects`, default off)

Recovery-skills phase, package RS2
([phase plan](../superpowers/roadmaps/recovery-skills-phase.md), section RS2).
This page records what the package implements, what it does not, and its
evidence. Nothing here is calibrated or scientifically qualified.

Enable with `--agents hybrid --repair-projects` and `--workshops` or
`--grain-storage` (granary storage needs `--grain-reserves`).
`--repair-mode` chooses `repair` (the default) or `cost_only`, the
cost-retaining control. Workshop sites are repaired only while workshops run
in `operate` mode; with workshops in `observe` or `cost_only` mode RS2
repairs granaries only and the L1 lump repair stays as it was. A world that
never enabled the switch has no container, snapshot key, checkpoint flag or
manifest entry. `--no-repair-projects` abandons open projects (reason
`switched_off`).

## What it replaces

- **Workshops (L1).** A site's condition wears only while it is unfunded
  (0.05 a turn), or by RS1 operating wear. Below `OPERATE_CONDITION` (0.5)
  the site does not operate until it is repaired. Before RS2, a 20-coin lump
  with no labour and no materials reset condition to 1.0 (`workshops._bill`
  and `_settle`). With RS2 owning workshop repair,
  `repair_projects.legacy_workshop_repair_allowed` returns False, so the
  lump is never billed. Project work is the only thing that moves a site's
  condition.
- **Granaries (grain storage).** Condition wears 0.01 a tick. Under the
  `maintain` policy a 4-work batch adds 0.10, capped at 1.0; the request is
  `min(budget, remaining batch, free timber, treasury / 2)`, delivered as
  anonymous farmer-equivalent work removed from farm labour. Coins were
  rounded up per region, zero-capacity granaries still asked for work, and a
  batch landing near the cap wasted its excess. RS2 keeps the channel and
  the rates, and replaces the batch with a project sized to the deficit.

War never damaged either asset before RS2.

## Projects

- **Opening (Phase 10, before the granaries' own tick and before the L9
  decision of the same Phase 10).** A project opens for an asset whose
  condition is below `OPEN_BELOW` (cause `wear`), or which carries an
  unrepaired war-damage record and any deficit (cause `war`, reconstruction).
  The region must have a controlling civilization with regions (it is billed).
  One open project per asset.
- **Scope.** The actual deficit at opening, `(1 - condition) x
  WORK_PER_CONDITION` work units: 40 for a granary (the storage channel's own
  4 work per 0.1) and 8 for a workshop. Each delivered unit credits
  `1 / WORK_PER_CONDITION` condition pro rata. Wear continues while a project
  runs, so the credit never reaches beyond the 1.0 cap (a `cap_waste` counter
  records any excess; the measurements below never had one). War damage to an
  asset with an open project adds the damage's deficit to its scope and makes
  it a reconstruction.
- **Completion.** When the scope has been delivered (within 1e-6 work, the
  f32 resolution of native work requests). The asset keeps wearing; a new
  project opens when it falls below `OPEN_BELOW` again.
- **Controller change.** The project belongs to the asset, as L1 arrears do:
  a conqueror inherits it (a dated `controller` note), pays for further work,
  and delivered work stays credited. A region left without a controller
  abandons the project (`no_controller`); a closed asset (the workshop site
  closed, storage switched off, workshops out of `operate` mode) abandons it
  (`asset_closed`).
- **Stalls.** A turn without delivered work is a stall, with its reasons:
  `no_timber`, `no_coins`, `no_labor`, `no_envelope`. A workshop crew without
  a qualified member works at `UNQUALIFIED_RATE`; that is recorded as
  `unqualified` among the limits of a turn, never as the reason for a stall.

## Granary labour: the storage channel

- `grain_storage` gains one guarded seam. A region with an open granary
  project has its ordinary storage request (maintain or expand) suspended for
  the turn (`StorageWorkPlan.suspended`), and the native work delivered there
  is the project's, not storage's. Nothing is planned, done or paid twice.
  With the switch off the seam returns an empty set and storage runs exactly
  as before.
- The project requests `min(GRANARY_WORK_PER_TURN = 4, remaining scope, free
  timber, coins, envelope)` in the `granary_work_requested` column. The
  native economy delivers at most the region's farmer labour and removes it
  from farming, as for storage.
- Zero-capacity granaries get no project (they appear as unmet needs).
- One timber and `COINS_PER_WORK` (2) coins per delivered unit, the storage
  rule. The coins are an existing public-works sink; the labour stays
  anonymous and earns no wage.

## Workshop labour: a named crew

- Placement. In `workshops.prepare_phase2`, right after the RS1 seats and
  before the L1 crew planner, the new seam `workshops._before_repair_crews`
  calls `repair_projects.before_crews`. It asks the native planner
  (`plan_workshop_crews` without a turn: read-only) for the site's eligible
  people: living adult farmers resident in the site's settlement and region,
  not on a trip, not enlisted, without health or teaching work. It drops
  anyone already holding a registry reservation this turn (RS1 apprentices).
  It then reserves at most `MAX_CREW` (4) of them under registry category
  `repair` (`reserve_work`, all or none). The L1 planner then excludes them,
  so a repairer is never also crew, an apprentice, a learner, a carer or a
  teacher, and the native tick refuses any overlap.
- Order. Qualified people come first (`apprenticeship.qualified_ids` while
  RS1 is active), qualified veterans first among them, then veterans
  (`veteran_reintegration.priority_ids` while RS3 is active), then everyone
  else by ascending id. A placed veteran is reported with
  `veteran_reintegration.note_outcome(..., "placed:repair")` after the work
  is done.
- Work. Each repairer works the city's diverted share `d = 1 -
  URBAN_FARM_LABOR[rank]` (0.2 to 0.4), as L1 crews do. A crew with a
  qualified member works at rate 1; otherwise at `UNQUALIFIED_RATE` (0.5).
  Until RS1 lands, every crew is unqualified. The crew is sized to the
  remaining scope, the region's free timber and the coins, so nobody is
  reserved for work that cannot be paid or supplied.
- Pay. Each repairer earns `round(d x WAGE_PER_WORK)` milli-units
  (`WAGE_PER_WORK` 500, the L6a rate). It is paid by stable id through
  `AgentSimulator.transfer_wealth` under purpose 3 `repair_wage`, in one batch
  per turn, from the controller's treasury. The same share `d` is installed
  with `extend_paid_work` (RS2 runs after L6a in the switch order), so the
  next wealth phase withholds that share of the person's ordinary income and
  the wage replaces it rather than adding to it. The withheld income is read
  back from the shared receipt (`livelihoods.paid_work_receipt`) into
  `income_replaced`. A wage the wealth ceiling refuses is not charged.
- Timing. Wages are paid in Phase 2 after the economy tick, with the rest of
  the repair bill, and before the agent tick. Deaths happen only in the native
  tick, so everyone paid was alive when they worked. A failed agent tick
  cancels the pending paid share (`rollback_agent_tick`); the turn is then
  abandoned.
- Materials. `WORKSHOP_TIMBER_PER_WORK` (1) timber per work unit. Workshop
  projects have no coin cost besides wages.

## Timber, coins and the L9 envelope

- **Timber.** Taken from the region's free stock: stockpile minus merchant
  commitments, minus what storage and other projects already hold. It is held
  before the native economy runs: the packed `stockpile_timber` column and the
  world stock are debited together, as storage holds timber before packing.
  The unused part is returned after the tick, and a failed tick returns all of
  it.
- **Coins, planning.** Coins are planned against the projected treasury, with
  every Phase 2 bill planned earlier taken out first:
  - before workshop repairs: the storage plan and an upper bound of every L1
    bill of the payer, so L1 upkeep comes first;
  - before granary repairs: the storage plan, the funded L1 bills, the L8
    warden bills and the workshop repairs.
- **Coins, visibility.** `workshops._pending_storage_bills` (read by the L1
  funding, L8 commons rules and L7 assistance through
  `commons_rules.pending_phase2_bills`) includes RS2's planned and not yet
  charged bills (`repair_projects.pending_bills`), so later planners never
  spend the same coins.
- **Coins, charging.** One charge per civilization per turn, after the
  economy tick (accumulator `keep`); a failed tick charges nothing.
  - Granary costs are summed exactly: each row is rounded up to the
    milli-unit, never per region to a whole unit.
  - The treasury pays whole units. The sub-unit remainder of the last unit is
    prepaid toward the civ's next repair costs (`prepaid`, below one unit per
    civ), so rounding never accumulates. It is written off, and counted
    (`prepaid_written_off_milli`), when the civ has no regions or the switch is
    turned off.
- **L9 (`--local-budgets`).** A new provider, `local_budgets.REPAIRS`
  (service and group `repairs`, fixed share 0.2 in the `fixed_shares`
  control), proposes one divisible envelope per ruler (`repairs:<civ>`). It
  covers next turn's planned work on the ruler's open projects, priced in whole
  units. Its relief:
  - commons: the granary wear relieved (extra spoilage over the horizon and the
    reserve target worn capacity cannot hold, as `granary_maintain` measures
    it);
  - patricians: crew work idle at a site shut for repair.

  All repair spending (wages and coin costs, and so the timber that work uses)
  stays within the envelope; without one a project stalls `no_envelope`. A
  granary under a project takes no `granary_*` envelope (its storage request
  is suspended). The envelope settles from RS2's ledger (spent = the civ's
  charge), keeping L9's closure (`spent <= amount`). `Decision.reserved` is
  unchanged: repairs are capped by the envelope, not reserved.
- **Cost-only control.** It reserves the same crews, pays the same wages and
  coins and holds and uses the same timber, but credits no condition.
  Projects still complete when their scope has been delivered, and reopen
  while the asset stays below the threshold.

## War damage

War damage is recorded only at existing real events. There is no new combat.

| Event | Call site | Damaged |
| --- | --- | --- |
| Region conquest | `action_engine.apply_region_conquest` | the region's granary and workshop site |
| City sack (a real plunder, after the cooldown) | `cities._sack` | the city's workshop site and its region's granary |
| Granary seizure by an occupying or besieging army | `war.occupation._requisition` (start of occupation, every siege turn), only when `seize_granary` actually took grain | the granary |

- Each hook is guarded by `world.livelihoods` and is a no-op unless RS2 is
  active. `grain_reserves.seize_granary` is not edited, so a conquest (which
  seizes grain inside `apply_region_conquest`) damages the granary once.
- Each asset takes at most one damage record per turn. A conquest followed by
  the sack of its city in the same turn is one record.
- Damage is `WAR_DAMAGE` (0.25) times the tuning key
  `repair_projects.war_damage`. The key defaults to 1; 0 disables damage, and
  is the screen ablation. Damage applies in both modes.
- Cause: `(war_key, war_start_turn)` of the war between the parties. It comes
  from the occupation record or a sieging army for seizures, and from
  `politics.war_key` of the two civs for conquests and sacks. It is resolved
  against active campaign records, wars ended this turn or last turn, and the
  aggregate `war_start_turns`. When no war is found (a revolt, an annexation
  without war) both are null.

## Consumers (unchanged)

- Granary: usable capacity `capacity x condition` and extra spoilage `0.07 x
  (1 - condition)`.
- Workshop: the L1 `OPERATE_CONDITION` gate, and RS1 wear when on.

## Declared constants (uncalibrated)

| Name | Value | Meaning |
| --- | --- | --- |
| `OPEN_BELOW` | 0.75 | condition below which a wear project opens |
| granary work per condition | 40 | `REPAIR_WORK / REPAIR_GAIN` of grain storage |
| `GRANARY_WORK_PER_TURN` | 4 | storage's `MAX_WORK_BUDGET` |
| granary timber, coins per work | 1, 2 | storage's `TIMBER_PER_WORK`, `COINS_PER_WORK` |
| `WORKSHOP_WORK_PER_CONDITION` | 8 | crew work to restore one unit of workshop condition |
| `WORKSHOP_TIMBER_PER_WORK` | 1 | timber per workshop work unit |
| `UNQUALIFIED_RATE` | 0.5 | work rate of a crew without a qualified member |
| `WAGE_PER_WORK` | 500 milli | wage per unit of paid time (L6a's rate) |
| `MAX_CREW` | 4 | most named repairers per site |
| `WAR_DAMAGE` | 0.25 | condition one real war event takes (times the tuning key) |

## Accounting and closure

Every turn and civilization (`CivLedger`, checked by
`repair_projects.check_ledger` when it is written, and by the viewer reader):

    charged x 1000 + prepaid_before == coin_cost + wages_applied + prepaid_after
    wages_applied + wage_residual == wages_due
    0 <= prepaid_before, prepaid_after < 1000;  charged <= envelope (with L9)

For each receipt, the timber held equals the timber used plus the timber
returned, and the timber used equals the work delivered times its rate.
Granary work never exceeds its request. Nothing creates people, money,
timber or condition.

## Lifecycle within a turn

1. Phase 2:
   - storage plans, skipping the suspended regions;
   - the workshop seam reserves the repair crews;
   - `repair_projects.prepare_phase2` plans granary requests and holds all the
     timber.
2. The native economy runs.
3. Storage settles its own regions. `finish_phase2` then pays once, credits
   condition (repair mode), returns unused timber and installs the paid share.
4. The agent tick runs, and the paid-work receipt is read.
5. Phase 10:
   - the lifecycle runs: abandon, inherit, open, and record unmet needs;
   - L9 settles and decides;
   - `phase10` dates the frame.

Guards against applying anything twice:

- a turn settles once (`last_settled_turn`);
- `transfer_wealth` applies a `(turn, purpose, batch)` key once;
- `rollback_phase2` returns held timber and cancels the paid share;
- the turn in flight (`_turn`) is never pickled or serialized;
- `on_pool_reset` clears each project's last crew with a dated note, since
  crews are re-planned from the live pool every turn.

## Snapshot (`livelihoods.repair_projects`, schema 1, stage `RS2`)

These fields are copied completed-turn observations, dated by `source_turn`:

- `projects` (open), `closed` (the last 16), `damages` (the last 32);
- `receipts` and `ledger`: `null` when that turn had no Phase 2 (unknown, not
  zero);
- `unmet`: assets below the threshold without a project, with the reason
  `no_controller`, `zero_capacity` or `building`;
- `suspended` (the regions whose storage request was suspended), `prepaid`,
  `counters` and `parameters`.

Each receipt names its project, kind, asset, region, payer, status, reasons,
crew, qualified and veteran members (veterans by open RS3 record), share and
rate, timber held, used and returned, wages, coins, envelope, condition before
and after, the remaining scope and the income withheld; a project's cause and
scope are on the project record. The strict viewer reader is
`viewer/src/lib/repairProjects.ts`; the panel
`viewer/src/components/systems/RepairProjects.tsx` is mounted in the
Livelihoods tab.

## Review corrections (2026-11-05)

An independent review of the integrated branch found these, each fixed with a
regression test that fails on the previous code:

- **Seizure without grain.** Every siege turn damaged the granary even when
  nothing was seized (an empty granary went from 1.0 to 0.0 in four turns);
  seizure damage now needs `seize_granary` to have taken grain.
- **Timber residue.** A ~1e-8 timber stock reserved and paid a full wage for
  ~1e-8 work. A repairer is hired only for a whole turn of work the free timber
  supports, or for all of a project's remaining work (`_timber_workers`); an
  L9 proposal must promise at least `MIN_PROPOSAL_WORK` (0.001), and an
  envelope that expected nothing never settles as kept.
- **Veteran placements.** Repairers holding an open RS3 record are noted
  `placed:repair` in both RS3 modes (`veteran_reintegration.open_record_ids`),
  not only those the priority list offered.
- **Shut sites under L9.** A built site below `OPERATE_CONDITION` whose lump
  repair RS2 owns puts nobody to work by paying upkeep, so L9's workshop
  proposal for it claims no crew work (stake 0); RS2's `repairs` proposal
  alone claims that idle work.
- **Mentors.** Mentors RS1 seated apprentices on this turn
  (`apprenticeship.seated_mentors`) are left off repair crews.

## Files and seams

- Owned: `repair_projects.py`, `repair_projects_state.py`, the tests, and the
  viewer reader and panel.
- Seams, each guarded and inert with the switch off:
  - `grain_storage.py` (pinned by the crisis-candidate source witness);
  - `workshops.py` (`_before_repair_crews`, `_pending_storage_bills`);
  - `local_budgets.py` (the `REPAIRS` provider, the `_Granary` skip and the
    snapshot share list) and `local_budgets_state.py` (`SERVICES` gains
    `repairs`);
  - `action_engine.py`, `cities.py` and `war/occupation.py` (war hooks).
- Lead-owned: `tuning.py` (`KNOWN_OVERRIDES` gains
  `repair_projects.war_damage`; pinned by the livelihoods-sprint witness).

## Evidence

### Tests

- `tests/test_repair_projects.py` (offline, 27 cases, about 0.5 s; chunk
  `recovery-skills`). It uses a constructed world and a recording simulator
  that enforces the registry's all-or-none rule, the paid-work install rules,
  keyed transfers and a wealth ceiling. It covers:
  - deficit sizing and the suspended storage channel;
  - no work beyond the cap, and completion;
  - one whole-unit charge per civ, with the prepaid remainder carried and
    written off;
  - zero-capacity granaries, and stall reasons;
  - the neglect policy, and maintain resuming after completion;
  - named crews: reserved before the L1 planner, paid by id under purpose 3,
    never also crew, with the lump disabled;
  - qualified people and veterans first, with `note_outcome`;
  - cost-only identity of costs without condition;
  - registry holders skipped, and nobody eligible;
  - controller change inherited, controller loss and asset closure abandoning;
  - switching off, and pool reset;
  - a failed economy tick charging nothing and returning timber;
  - a failed agent tick cancelling the paid share;
  - a turn settling once, and closure refusals;
  - the wage ceiling;
  - war damage once per asset and turn with war identity, scope extension,
    the occupation war and the ablation key;
  - L9 envelope limits, the proposal and the settlement, and the `_Granary`
    skip;
  - dated snapshots, JSON and pickle round trips (including an RS0 pickle);
  - feature-off storage planning;
  - workshops outside operate mode.
- `tests/test_repair_projects_native.py` (real extension, 5 cases, about 7 s):
  - template seed 11, 60 turns, `CHRONICLER_CHECK_RESOURCES=1`: every repairer
    holds a category-3 reservation with the paid share and is a resident adult
    farmer of the site; there are no registry conflicts and no L1 overlap;
    every transfer moves real wealth once; every receipt and ledger closes;
    the granaries' storage requests are suspended; seizure and conquest damage
    carry war identities; no lump repair is ever billed;
  - a constructed granary: real channel work, timber and coins, with the goods
    balance closing; a failed economy tick charges nothing and returns timber;
  - exact checkpoint and resume at turn 40, inside live projects including a
    workshop crew: history, world state and `state.json` are byte-identical;
  - cost-only with the damage ablation;
  - a rebuilt native pool clears saved crews, while an exact re-bind keeps them.
- `tests/test_recovery_skills_wiring.py` and
  `tests/test_recovery_skills_native.py`: the RS0 inertness assertions now
  exclude the landed RS2 (`LANDED`), and the legacy-gate test expects RS2 to
  shut the gate.
- Viewer: `viewer/src/lib/__tests__/repairProjects.test.ts` and
  `viewer/src/components/systems/__tests__/RepairProjects.test.tsx`.

### Feature-off identity against the parent commit

The parent commit was `52711f27` (RS0), with the same RS0 extension
(`/root/.venvs/native-rs0`). Two 60-turn runs were compared on bundle
history, world state and `state.json` bytes, and both were identical:

- template seed 11 with `--workshops --grain-reserves --grain-storage
  --grain-storage-policy maintain --grain-storage-work-budget 4
  --local-budgets`;
- procedural 32 x 10 seed 23 with `--workshops --grain-reserves
  --public-grain-shipments --scholarship --techniques --academy-services
  --grain-storage --workshop-payroll --timber-stock --commons-rules`.

### Development measurement (natural, 80 turns)

Every arm used `--agents hybrid --simulate-only --workshops --grain-reserves
--grain-storage`. The worlds were template seeds 11 and 23 (8 regions, 4
civs) and procedural 32 x 10 seed 31. The arms were:

| Arm | Flags |
| --- | --- |
| neglect | the storage default |
| maintain | `--grain-storage-policy maintain --grain-storage-work-budget 4` |
| repair | `--repair-projects` |
| repair_nodamage | `--repair-projects --tuning nodamage.yaml`, with `repair_projects: {war_damage: 0.0}` |
| cost_only | `--repair-projects --repair-mode cost_only` |

`PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`; an example command:

    python -m chronicler.main --seed 31 --worldgen procedural --regions 32 --civs 10 --turns 80 \
      --agents hybrid --simulate-only --workshops --grain-reserves --grain-storage --repair-projects \
      --output OUT/chronicle.md --state OUT/state.json

These are single worlds. Trajectories diverge once any spending differs, so
population, treasury and workshop operation differ between arms for reasons
beyond the granaries; they are not effects of the mechanism. The measurement
only shows where the mechanism activates and what binds it.

**Granary trace.** Mean condition and total usable capacity of the granaries
with positive capacity:

| Turn | Neglect | Maintain | Repair, no damage | Repair | Cost only |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.990 / 1077 | 0.990 / 1077 | 0.990 / 1077 | 0.973 / 1051 | 0.973 / 1051 |
| 20 | 0.800 / 870 | 0.877 / 964 | 0.800 / 870 | 0.583 / 673 | 0.513 / 578 |
| 40 | 0.600 / 653 | 0.765 / 833 | 0.695 / 763 | 0.455 / 535 | 0.357 / 414 |
| 60 | 0.400 / 435 | 0.605 / 659 | 0.628 / 660 | 0.320 / 371 | 0.223 / 270 |
| 80 | 0.200 / 218 | 0.462 / 506 | 0.470 / 483 | 0.224 / 232 | 0.107 / 133 |

The table is procedural seed 31. Totals over the 80 turns:

| World, arm | Work delivered | Mean condition | Mean usable capacity | Granary spoilage |
| --- | --- | --- | --- | --- |
| P31 neglect | 0 | 0.595 | 647 | 156.7 |
| P31 maintain | 384.0 (storage) | 0.740 | 810 | 62.4 |
| P31 repair, no damage | 162.3 | 0.710 | 767 | 88.3 |
| P31 repair | 151.9 | 0.476 | 542 | 41.5 |
| P31 cost only | 198.0 | 0.396 | 456 | 98.4 |
| T11 neglect / maintain / repair, no damage | 0 / 160.1 / 59.5 | 0.595 / 0.725 / 0.702 | 320 / 424 / 407 | 0 |
| T11 repair / cost only | 115.5 / 161.8 | 0.521 / 0.407 | 294 / 202 | 0 |
| T23 neglect / maintain / repair, no damage | 0 / 70.8 / 32.6 | 0.595 / 0.681 / 0.694 | 233 / 265 / 276 | 0 |
| T23 repair / cost only | 39.6 / 67.3 | 0.573 / 0.496 | 223 / 193 | 0 |

The template worlds' granaries held no grain, so their spoilage is zero.

- **Repair projects against maintain.** Without war damage, projects end
  about where `maintain` ends, with less than half its work. At turn 80 the
  condition was 0.470 against 0.462 (P31), 0.448 against 0.370 (T11) and
  0.363 against 0.330 (T23). The work was 162 against 384, 60 against 160 and
  33 against 71. Projects deliver no work until an asset falls below 0.75, so
  their mean condition is a little lower (0.710 against 0.740 in P31). They
  never work on a zero-capacity granary or beyond the cap.
- **Repair against cost only.** Both arms have the same damage, so this
  comparison isolates the credited work. Condition at turn 80 was 0.224
  against 0.107 (P31), 0.239 against 0.100 (T11) and 0.241 against 0.160
  (T23). The control spent more (401, 325 and 136 coins against 307, 235 and
  80), because its projects reopen while the asset stays worn.
- **War damage dominates where wars happen.** In P31 there were 21 damage
  records (16 seizures in siege and occupation turns, 5 conquests). With
  damage on, the repair arm ends below the no-damage arm (0.224 against
  0.470).

**Activation funnel** (repair arm; T11 / T23 / P31):

| Stage | T11 | T23 | P31 |
| --- | --- | --- | --- |
| Projects opened: wear / war | 6 / 4 | 5 / 1 | 9 / 9 |
| of them granary / workshop | 9 / 1 | 6 / 0 | 17 / 1 |
| Project-turns with work / stalled | 104 / 254 | 23 / 244 | 144 / 832 |
| Stalls: no timber / no coins / no labour | 226 / 78 / 26 | 244 / 0 / 0 | 804 / 73 / 54 |
| Completed / abandoned | 4 / 0 | 1 / 0 | 3 / 1 (asset closed) |
| Inherited by a new controller | 1 | 1 | 6 |
| Work: granary / workshop | 115.5 / 2.0 | 39.6 / 0 | 151.9 / 0.3 |
| Named repairer-turns (all unqualified) | 22 | 0 | 3 |
| Wages / coin costs / charged (coins) | 2.2 / 231.0 / 235 | 0 / 79.1 / 80 | 0.3 / 303.8 / 307 |
| Damage records: seizure / conquest / sack | 13 / 1 / 0 | 4 / 0 / 0 | 16 / 5 / 0 |
| Unmet region-turns: zero capacity / no controller | 65 / 55 | 153 / 12 | 879 / 56 |

The remaining difference between charged and costs is the prepaid balance
still held, below one unit per civ. In the first build, which rounded each
turn's charge with no carry, the same arms showed a 7-19% rounding overcharge.

**What binds.** Timber stops most project-turns: 89% of T11's stalls, all of
T23's and 97% of P31's. That matches the audit's finding that timber binds
storage maintenance. Workshop projects are rare in natural runs, because a
site wears only while unfunded and RS1 operating wear is not yet in. They
came from one conquest in T11 (a crew from turn 37) and one in P31, whose
site later closed.

### Constructed example

`test_constructed_granary_rebuild_moves_real_work_timber_and_coins`: a
3-region world, one granary at condition 0.5 and a treasury of 1,000.

- After the first tick, a project of 20.4 work opens.
- The next tick delivers 4.0 real work through the storage channel:
  - the granary's own storage request is 0;
  - 4 timber is used and 8 coins are charged;
  - condition goes from 0.49 to 0.58;
  - the full goods balance closes with that timber.

## Limits and open questions

- Workshop repair has no coin cost besides wages, so it is far cheaper than
  the 20-coin lump it replaces. Labour time (crew diverted from L1 work) and
  timber are its real costs.
- Without RS1 every crew is unqualified (rate 0.5). With RS1 the rate rises
  to 1 for a crew with a qualified member.
- A workshop crew is reserved before the funding of later Phase 2 planners is
  known. Its timber is re-checked before the tick, and a shortfall reduces the
  work but not the paid time (rare: the crew is sized to the free timber at
  the seam).
- Granary work is anonymous farm labour. The plan's "named workers" applies
  to workshop repair only, because the storage channel has no identities.
- With L9, workshop projects above `OPERATE_CONDITION` relieve no
  constituency (no crew work is idle), so they rarely receive an envelope.
- The prepaid sub-unit remainder (under one coin per civ) is written off when
  a civ has no repair costs left (no regions) or the switch is turned off: a
  disclosed sink that closes exactly, not a refund.
- Infrastructure repair, other assets and any new combat generator are out of
  scope. Nothing here was run on held seeds or through the 200-seed gate.
