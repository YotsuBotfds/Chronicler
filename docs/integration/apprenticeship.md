# Workshop apprenticeship and skill continuity (RS1, `--apprenticeship`, default off)

Recovery-skills phase, package RS1
([phase plan](../superpowers/roadmaps/recovery-skills-phase.md), section "RS1").
This page records what the package implements, what it does not, and its evidence.
Merging it does not qualify it scientifically.

> **Rules version 2 (PL2, 2026-11-05).** Every new RS1 state now runs
> [RS1 rules version 2](#rs1-rules-version-2-pl2): attendance by region, portable
> progress that pauses and ends only after a long absence, and training on the job.
> The sections up to "Limits and open work" describe **version 1**, which a state saved
> before PL2 (an exact checkpoint or a state file) keeps and resumes under, unchanged.
> The operating wear is now the [`--operating-wear`](operating-wear.md) assumption,
> which `--apprenticeship` implies.

Enable with `--agents hybrid --workshops --apprenticeship` (`--workshops` must be in
`operate` mode, its default). `--apprenticeship-mode` chooses `train` (the default)
or `no_qualification`, the cost-retaining control. A world that never enabled the
switch has no container, snapshot key, checkpoint flag or manifest entry, and its
output is byte-identical to the parent commit (checked below). `--no-apprenticeship`
ends open apprenticeships (reason `disabled`) and keeps every qualification. The
mode cannot change while an apprenticeship is open.

## Why a qualification record

The phase audit found that occupation skill cannot say who can keep a workshop:
it rises by 0.05 a turn in a person's current trade whether or not they work, it
never decays, farmer skill feeds no capacity, and L5 completion adds 0.25 to a
number already near its cap. RS1 therefore keeps an explicit **workshop
qualification** per stable native id:

`{agent_id, earned_turn, site, settlement_id, region, via}` with `via` = `service`
or `apprenticeship`.

- It never reads or writes `pool.skills`.
- It is held for life and travels with the person. `site`, `settlement_id` and
  `region` say where it was earned; `seen_region`/`seen_settlement` say where the
  holder lived at the end of the latest tick. A migrant is qualified wherever they
  live and can be on that city's crew.
- A death retires the record (`retired`, dated, reason `died`).
- `qualified_ids(world, region)` (the cross-lane API RS2 repair crews use) returns
  the living qualified ids resident in `region`, ascending. Before this turn's agent
  tick it reads this turn's start-of-turn native snapshot; otherwise the last
  observed residence. It returns `[]` while the switch is inactive.

### How qualifications are earned

- **Service.** A crew member of an *operating* site (funded, built, in condition,
  with crew, so that its work replaced the craft ceiling that turn) serves one
  crew-turn, counted from the actual planned crew. `SERVICE_TURNS` crew-turns at any
  site earn a `service` qualification at the site where the last one was served.
  Service accrues in **both** modes: it is how the first mentors appear, with no
  external grant. Construction, unfunded and worn turns are not service.
- **Apprenticeship.** `COMPLETION_TURNS` attended turns earn an `apprenticeship`
  qualification in `train` mode only.

## What the qualification enables

The qualification gates real upkeep work against real wear.

- With the switch on (both modes), every funded **operating** site wears
  `OPERATING_WEAR` a turn through the RS0 `_operating_wear` seam. (Without the
  switch, L1 condition wears only while a site is unfunded.)
- **Upkeep.** Qualified members of that turn's crew each spend up to
  `UPKEEP_SHARE` of their crew time on upkeep, only as much as the turn's wear
  needs. One unit of upkeep work (one person's whole turn) offsets
  `WEAR_PER_UPKEEP_WORK` of condition. The offset is therefore at most the wear,
  and condition stays in [0, 1]. At a rank-1 city (`d` = 0.2) one qualified crew
  member offsets half the wear and two offset all of it.
- **Teaching.** A mentor spends `TEACH_SHARE` of their crew time per apprentice
  taught.
- **Crew time is counted once.** Upkeep and teaching come out of the crew's
  diverted time. The craft work allocated, and so the craft ceiling
  (`K_RAW_PER_WORK × work`), is the crew's diverted time less upkeep and teaching
  (the workshops `_crew_maintenance` seam). Every receipt satisfies
  `crew_work = craft_work + upkeep_work + teaching_work`. The crew's registry
  reservation and any L6a wage are unchanged: they cover the whole crew time once.
- **Worn sites stop.** A site with nobody qualified on its crew wears down. Below
  `workshops.OPERATE_CONDITION` (0.5) it cannot operate until repaired: by RS2 when
  that is on (the RS0 `legacy_workshop_repair_allowed` gate), otherwise by the
  existing L1 lump (`REPAIR_COST`, condition back to 1.0). RS1 never repairs.
- **Crew order.** While the switch is active the native crew planner lists this
  turn's living qualified ids first, then any RS3 veterans, then ascending id
  (`workshops._crew_priority`). A qualified resident is on the crew whenever the
  site's crew cap allows.

## Mentors and apprentices

- **Before the crews are planned** (`workshops._before_crews`), two read-only
  passes of the native crew planner (`plan_workshop_crews` without a turn, with
  this turn's requests) find, per site:
  - the qualified people who will be on this turn's crew: the first
    `max_workers` eligible qualified ids (the mentors);
  - the eligible non-qualified residents.
- **Apprentices** are living adult (age ≥ 20) urban Farmers resident in the site's
  settlement and region, not on a merchant trip or an army roster, not holding
  other work this turn (registry, rural health care, teaching plan) and not
  qualified. That is the crew pool's predicate with the planner's own exclusions.
  Veterans come first (`veteran_reintegration.priority_ids`: RS3's eligible
  open veterans in priority mode, none in its `record_only` control), then
  ascending id. Every seat reserved in a turn is reported with
  `note_outcome(world, id, "placed:apprentice", turn=..., detail={site, region,
  attended})`, whether or not priority seated the person; RS3 keeps only ids
  with an open veteran record, so a veteran apprentice is placed (one spell over
  consecutive seated turns, never "waiting") in either RS3 mode. Review A,
  2026-11-05: before this, only a new seat flagged through priority was
  reported.
- **Seats.** Each predicted mentor teaches up to `PER_MENTOR`; a site holds at most
  `PER_SITE` open apprenticeships, including apprentices away or unavailable this
  turn. Continuing apprentices keep their seats first, in enrolment order; new
  ones fill what remains. A site that cannot operate (building, or worn without
  an allowed repair) seats nobody.
- **Reservation.** Seated apprentices are reserved in the shared work registry
  (category 2, `apprentice`) for `APPRENTICE_FRACTION` of the turn **before** the
  crew planner runs, so the crew excludes them. The call is all or none; if it is
  refused, seats are reserved one by one and only the refused seat is lost
  (`reservation_refused` or `seat_refused`).
- **Teaching.** After funding is planned, each actual qualified crew member
  (mentor), in crew order, is assigned up to `PER_MENTOR` seated apprentices in
  seat order.

## Costs

- **Forgone income.** An apprentice who is taught gives up `APPRENTICE_FRACTION` of
  their ordinary occupational income through the shared paid-work seam
  (`extend_paid_work` in `finish_phase2`; L6a payroll's `install_paid_work` comes
  first). The amount withheld comes from the shared receipt after the tick
  (`livelihoods.paid_work_receipt`). Nobody has two pending shares: apprentices are
  never on a crew, and the native call refuses a second share.
- **Stipend.** With `--workshop-payroll` (mode not `unpaid_labor`), the site's firm
  pays each attending apprentice `STIPEND_PER_WORK × APPRENTICE_FRACTION`
  milli-units from its cash in Phase 10, after that turn's wages. It is paid by
  stable id under transfer purpose 2 (`apprentice_stipend`), once per turn and
  site (`workshop_payroll.pay_from_firm`). Short cash is shared pro rata (largest
  remainder, ties by id) and is not owed. What a wealth ceiling refuses, or a dead
  id cannot take, stays in cash. The firm's closure includes `totals["stipends"]`
  and the receipt's optional `stipends`
  ([workshop finance](workshop-finance.md#typed-transfers-and-closure)).
- **Unpaid otherwise.** Without payroll, without a firm at the site, or under
  `unpaid_labor`, the time is unpaid: the cost is the forgone income alone
  (stipend status `no_payroll`, `no_firm` or `unpaid_labor`).
- **Mentors.** The mentor's teaching share comes out of their crew work, which is
  paid once as crew time (never twice).
- **Treasury.** RS1 charges no treasury. More frequent L1 lump repairs (or RS2
  projects) are the site's own costs of the added wear.

## Attendance, interruptions and endings

- **A turn counts** only if the apprentice was reserved, the site operated, a
  mentor on its crew taught them, and they survived the tick.
- **Interruptions.** Any other turn of an open apprenticeship is an interruption,
  with one reason:
  - `unavailable`: on a trip or holding other work;
  - `no_mentor`;
  - `site_not_operating`;
  - `reservation_refused`;
  - `away`: outside the city but still in the region. Settlement membership is
    positional (the city's grid cells), so leaving the city is an interruption,
    not an immediate ending.
- **Dropout.** More than `MAX_GAP` interruptions in a row end the apprenticeship as
  `dropout`, or as `departed` when the last interruption was `away`.
- **Dated endings** (`archive`, latest 64): `completed`, `dropout`, `died` (before
  the turn, or later in the tick, when that turn does not count), `migrated`
  (another region), `departed`, `occupation_changed`, `site_closed`, `remobilised`
  (on an army roster), `pool_reset`, `disabled`, and `service_qualified` (an
  unseated apprentice drafted onto the crew who qualified by service).
- **Conquest does not end an apprenticeship.** A site's condition, arrears and firm
  belong to the asset and follow it through a change of controller (L1/L6a), and
  teaching is between people at the site. So apprenticeships continue under the new
  ruler, and a dated `conquest` event names the open apprentices with the old and
  new controller. A city that falls closes its site, which ends the site's
  apprenticeships as `site_closed`.
- **Control.** `no_qualification` keeps every seat, reservation, withheld income,
  stipend, mentor time, upkeep and wear, and records completions with
  `granted: false`. Until the first completion the two modes produce identical
  worlds (a native test checks this).

## Continuity

Each turn and open site records:

- `qualified_present`: qualified people living in the site's city (settlement and
  region), who can be on its crew;
- `qualified_in_region`: qualified people living anywhere in the site's region,
  its community (one site per region);
- `qualified_on_crew` and `mentors`.

Separately, `continuity` holds the totals:

- qualified people alive anywhere (retained by people);
- those in workshop regions and in workshop cities;
- those on crews;
- those elsewhere;
- the sites with nobody qualified in their region (unmet).

A dated `teaching_lost` event fires when a site whose region had a qualified
person has none. It names where each one went (`died` or `region:<index>`) and how
many still hold their record. `teaching_restored` fires when one returns or
qualifies.

## Identity, timing and bounds

- **Identities.** Stable native ids only. Region and civilization identities are
  indices in `world.regions` and `world.civilizations`.
- **No randomness.** No RNG is drawn.
- **Dated observations.** `snapshot.livelihoods.apprenticeship` (schema 1, stage
  `RS1`) is dated by `source_turn`. `receipts` and `continuity` are `null` when no
  pass completed in the source turn (unknown, not zero).
- **Bounds:**
  - 512 held qualifications (a grant beyond it is refused and counted);
  - 64 retired records;
  - 256 service-progress records (the least recently seen is evicted and
    counted);
  - `PER_SITE` open apprenticeships per site;
  - 64 archived apprenticeships;
  - 64 events;
  - one frame;
  - counters from a fixed key set.
- **Exactly once.**
  - A turn's decisions stay pending (never checkpointed) until Phase 10.
  - A failed Phase 2 or agent tick cancels the paid-work extension and
    changes nothing persisted (`rollback_phase2`, `rollback_agent_tick`).
  - `last_settled_turn` refuses to settle a turn twice.
  - The native transfer key refuses a second stipend for the same turn and site.
  - The registry rows of a failed turn are dropped by the next turn's first
    reservation, as for workshop crews.
- **Pool reset.** `on_pool_reset` (a rebuilt native pool) retires every
  qualification, clears service progress and ends every apprenticeship, all with
  reason `pool_reset`. It emits no `teaching_lost`: nobody left; the ids changed
  meaning.

## Declared parameters (modeling choices, not calibrated)

| Constant | Value | Meaning |
| --- | --- | --- |
| `SERVICE_TURNS` | 12 | operating crew-turns that earn a service qualification |
| `OPERATING_WEAR` | 0.02 | condition an operating funded site loses per turn |
| `UPKEEP_SHARE` | 0.25 | most of a qualified crew member's crew time spent on upkeep |
| `WEAR_PER_UPKEEP_WORK` | 0.2 | condition one unit of upkeep work offsets |
| `TEACH_SHARE` | 0.2 | share of a mentor's crew time per apprentice taught |
| `PER_MENTOR` | 2 | apprentices one mentor teaches |
| `PER_SITE` | 4 | open apprenticeships per site |
| `APPRENTICE_FRACTION` | 0.5 | share of an apprentice's turn reserved and withheld |
| `MAX_GAP` | 4 | consecutive interruptions tolerated |
| `COMPLETION_TURNS` | 10 | attended turns to complete |
| `STIPEND_PER_WORK` | 250 | stipend per unit of attended time, milli-units (half the L6a wage) |

None was tuned on any world. With 0.02 wear an unqualified operating site reaches
the 0.5 operating floor in 25 turns.

## Viewer

The strict reader `viewer/src/lib/apprenticeship.ts` (`readApprenticeship`) tells
an **absent** record from a **malformed** one (it gives the reason). It rejects:

- a misdated observation;
- an apprentice who is also on the crew;
- a mentor who is not a qualified crew member;
- more apprentices taught than mentors can teach;
- wear or crew time that does not close;
- a qualified person still apprenticed;
- an open record past completion or gap;
- continuity totals that do not add up;
- a control completion that was granted.

The panel `viewer/src/components/systems/Apprenticeship.tsx` is not mounted; the
lead mounts it. It shows:

- the funnel;
- continuity (retained by people versus community capacity, and the unmet sites);
- per site: condition, wear and upkeep, the qualified people in the city and on
  the crew, the named mentors and apprentices with their outcome and income given
  up, and stipends;
- the open apprenticeships;
- recent endings with reasons and dates;
- the qualified people and where they live;
- the continuity events.

Values are dated to the selected snapshot. `viewer/src/lib/workshopFinance.ts` now
closes firm cash with stipends and accepts the `stipend` money kind.

## Evidence

### Tests

- `tests/test_apprenticeship.py` (offline; oracle chunk `recovery-skills`) uses a
  native stand-in with the planner, registry, paid-work and transfer contracts,
  driven through the real livelihoods hooks. It covers:
  - service counts only operating crew-turns, in both modes;
  - the qualification travels with a migrant and is retired at death;
  - wear, the bounded upkeep offset and exact crew-time accounting
    (`craft + upkeep + teaching = crew`, ceiling `= K × craft`);
  - a worn site stops until the lump or RS2 repairs it;
  - seat capacity, the qualified-first crew and apprentices never on a crew;
  - registry and paid work hold each person once;
  - veterans first, with `note_outcome`;
  - completion grants in train and not in the control, with identical attendance,
    income and wear;
  - interruptions, dropout, away and departed;
  - every ending with its date, and conquest continuing;
  - an apprentice who moves into another site's crew;
  - pool reset;
  - `teaching_lost` and `teaching_restored`;
  - disable;
  - the bounds;
  - a refused seat;
  - stipends once from firm cash after wages with exact closure, short cash, no
    firm and `unpaid_labor`;
  - a failed tick and a failed Phase 2 change nothing;
  - hooks apply once;
  - a JSON and pickle resume inside live apprenticeships equals the straight run;
  - the dated snapshot;
  - feature-off worlds have no state.
- `tests/test_apprenticeship_native.py` (real extension, template seed 7, 8 regions)
  covers:
  - the compiled extension and its methods;
  - on a live pool, every seated apprentice is an eligible resident holding only
    an apprentice reservation and never on a crew, with no registry conflicts;
  - the extension rows are within the reservations;
  - receipts close (crew time, wear bounds, ceiling `= K × craft`);
  - the control equals train until the first completion (turn 73);
  - an exact checkpoint at turn 52, inside live apprenticeships, resumes byte for
    byte (history, world state and `state.json`);
  - **constructed** (labelled): firms opened without an academy order and given a
    test-only cash top-up pay wages and stipends that move real native wealth
    exactly once per key, with every firm closing.
- RS0 tests (`tests/test_recovery_skills_wiring.py`,
  `tests/test_recovery_skills_native.py`) now treat apprenticeship as landed, not as
  an inert stub.

### Feature-off identity

Native extension `9277341a…` (RS0). Runs with the parent `52711f27` and with this
branch: template seed 7 (8 regions, 4 civs, 60 turns) with `--workshops`; the same
with `--workshops --workshop-payroll --scholarship --techniques --academy-services`;
and seed 11 with no livelihoods switch. In
all three, `state.json` was byte-identical, and the bundles differed only in
`metadata.generated_at`.

### Development measurement (natural activation; not evidence of an effect)

80 turns, native extension `9277341a…`, `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`.
Arms: `--workshops` alone (off), `--apprenticeship` (train) and
`--apprenticeship-mode no_qualification` (control). These are development worlds,
not the held seeds (501–506, 601–606).

| World | Arm | Operating site-turns | Mean / min condition | Lump repairs | Service qualif. | Enrolled | Attended turns | Completions (granted) | Upkeep offset / wear | Site-turns without a qualified person in the region |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| template 7 (8r/4c) | off | 185 | 0.984 / 0.95 | 0 | — | — | — | — | — | — |
| | train | 201 | 0.793 / 0.49 | 5 | 12 | 33 | 100 | 2 (2) | 0.69 / 4.02 | 184 / 241 |
| | control | 201 | 0.793 / 0.49 | 5 | 13 | 33 | 100 | 2 (0) | 0.69 / 4.02 | 184 / 241 |
| template 3 (8r/4c) | off | 167 | 1.000 / 1.00 | 0 | — | — | — | — | — | — |
| | train | 165 | 0.775 / 0.50 | 4 | 12 | 34 | 79 | 1 (1) | 0.70 / 3.30 | 111 / 196 |
| | control | 165 | 0.775 / 0.50 | 4 | 12 | 34 | 79 | 1 (0) | 0.70 / 3.30 | 111 / 196 |
| procedural 21 (32r/10c) | off | 158 | 0.838 / 0.00 | 1 | — | — | — | — | — | — |
| | train | 143 | 0.766 / 0.00 | 6 | 4 | 7 | 12 | 0 | 0.10 / 2.86 | 239 / 256 |
| | control | 143 | 0.766 / 0.00 | 6 | 4 | 7 | 12 | 0 | 0.10 / 2.86 | 239 / 256 |

Activation funnel:

- Sites operate from turn 22.
- The first service qualification comes at turn 40 (template 7), 46 (template 3)
  and 53 (procedural).
- The first apprentice is seated one turn later.
- The first completion comes at turn 73–74 in the template worlds; there is none
  in procedural 21 within 80 turns.

Most apprenticeships end by migration: 16 of 33 in template 7 and 21 of 34 in
template 3. Interruptions are mostly `away` and `no_mentor`.

What this shows:

- **The switch costs condition.** Its wear costs sites condition and more lump
  repairs (4–6 against 0–1). The few qualified people offset about a sixth of the
  wear (template) and a thirtieth (procedural), because crews churn and qualified
  people move away.
- **Train and control barely differ within 80 turns.** Completions come too late
  for the train arm's extra qualifications to matter: the first divergence is a
  single service qualification in template 7.
- **This is a working mechanism with a weak natural result at these horizons.**
  Longer horizons and the preregistered RS7 screens are where an effect could
  show.

Reproduce one arm (any directory):

```sh
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 python -m chronicler.main --seed 7 --turns 80 \
  --civs 4 --regions 8 --agents hybrid --simulate-only --output out/chronicle.md \
  --state out/state.json --workshops --apprenticeship [--apprenticeship-mode no_qualification]
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 python -m chronicler.main --seed 21 --turns 80 \
  --worldgen procedural --regions 32 --civs 10 --agents hybrid --simulate-only \
  --output out/chronicle.md --state out/state.json --workshops --apprenticeship
```

## Limits and open work

- **Time scale.** At the declared constants, completions take 30 or more turns
  after a site opens, and migration ends most apprenticeships first. Nothing was
  tuned.
- **Presence is positional.** Settlement membership follows grid position, so
  presence in the city flickers. Region-level continuity and the `away`
  interruption absorb this, but crews still churn.
- **No new combat damage.** War damage to sites is RS2's (`repair_projects`).
- **Veteran priority is weak in practice.** Qualified people come first on
  workshop crews (`_crew_priority`), so the planner sees veterans only after
  every living qualified id; at most a few veterans per world were enrolled in
  the development worlds.
- **Stipends need a firm.** In the measured worlds no academy order opened a firm,
  so stipends were never paid naturally; only the constructed test pays them.
- **Not run:** the RS7 held screens, and the 200-seed and procedural qualification
  gates.

## RS1 rules version 2 (PL2)

Productive-recovery phase, package PL2
([phase plan](../superpowers/roadmaps/productive-recovery-phase.md), sections 1 "D2"
and 2 "PL2"). Version 2 applies to `train` and `no_qualification` alike. It is the
rules version of every new state.

### Why

The D2 diagnosis (84 runs on 12 development worlds) found:

- **People leave because of the city box, not because of apprenticeship.** Attendance
  required presence in the site's *city*, and city membership is re-derived from grid
  position every tick, so 24–27% of a workshop city's adults leave the box each turn
  while staying in the region. The rate is the same for crew, apprentices and qualified
  people.
- **Endings** (template / procedural): migrated 42% / 38%, departed 22% / 25%, died
  10% / 12%, dropout 7% / 7%, completed 3% / 1%.
- **The exclusive seat displaced crew.** It was reserved before the crew planner, which
  displaced about 170 crew-turns per world.
- **Graduates did almost no useful work.** They were aboard 4.2% / 0.9% of operating
  site-turns, and 80% of qualifications ended in death within the run.
- **The extra repairs were the wear.** They came from the maintenance assumption, not
  from training; that assumption is now [`--operating-wear`](operating-wear.md).

No constant changed to raise a counter. `COMPLETION_TURNS` (10 attended turns) keeps
its meaning. `MAX_GAP` (4) keeps its value with a version-2 meaning, below.

### Rules version, checkpoints and serialization

- `ApprenticeshipState.schema_version` is the rules version (`rules_version`).
  - A new state gets `apprenticeship.RULES_VERSION` (2).
  - A state saved before PL2 carries 1. It resumes under the version-1 rules,
    unchanged, from an exact checkpoint (pickle) or a state file (JSON).
- Version-1 records serialize exactly as before. Every field version 2 added is `None`
  in them and omitted from every dump.
- Pickles written before PL2 lack those fields. `__setstate__` restores them as `None`
  (`tests/test_apprenticeship_v2.py`).
- The snapshot of a version-1 state is schema 1 with the same keys. A version-2 state
  writes schema 2 with `rules_version: 2`.
- Validation refuses a version-1 state carrying version-2 records, and an unknown
  version.
- No option selects the rules, so a resume has nothing to override and nothing changes
  silently. The existing RS1 tests pin version 1 to keep that path tested
  (`tests/test_apprenticeship.py`, `tests/test_apprenticeship_native.py`, including the
  exact native checkpoint resume).

### The rules

1. **Crews stay as planned.** The native planner draws adult urban farmers of the
   site's city (`workshop_work.rs` `plan_crews_with_priority`, about lines 212–231). Its
   order is unchanged: qualified first (`_crew_priority`), then RS3 veterans, then
   ascending id. Nobody is reserved before it, so apprentices never displace crew.
2. **Presence is by region.** An open apprenticeship is present when the apprentice
   lives in the region of an open site, inside the city box or not.
   - **Portable progress.** A migrant who now lives in another open site's region
     transfers to that site, with progress kept (`transfers`, `transferred_from`).
   - A site holds at most `PER_SITE` apprenticeships. A move is accepted only into room
     that exists when it is decided; moves are decided in enrolment order, so no site
     ever exceeds `PER_SITE`. Otherwise the turn is missed as `no_room`.
3. **Training on the job.** The native crew cannot include anyone outside the city box,
   so the closest Python-only rule is this. At an operating site, after its crew was
   planned (`crew_maintenance`), each present apprentice is **aboard** in one of two
   ways:
   - **`crew`**: they are on the planned crew and train on crew time. Nothing more is
     reserved or withheld, and no stipend is paid. Their time is crew time, paid once
     (an L6a wage when payroll is on). They also accrue service crew-turns.
   - **`attached`**: they live in the region but are not on the crew (outside the city
     box, or not picked). They are reserved in the work registry (category 2) for
     `APPRENTICE_FRACTION` after the crew was planned. That share of their ordinary
     income is withheld (`extend_paid_work`), and with L6a their firm stipend is paid
     from cash as in version 1. Attached time adds no craft work, and attached
     apprentices accrue no service.
   - **When a turn counts.** Teaching capacity is `PER_MENTOR` per qualified member of
     this turn's crew. A turn counts when the site operated, the apprentice was aboard,
     a qualified crew member taught them (`TEACH_SHARE` of the mentor's crew time,
     taken from craft work), and they survived the tick.
   - **Who is taught first.** Continuing apprentices come first, in enrolment order;
     transfers come after the site's own apprentices. New apprentices fill what remains,
     up to `PER_SITE` open.
4. **Missed turns pause progress.** The reasons are:
   - `no_mentor`, `unavailable` (a trip, or other work in the registry),
     `reservation_refused` and `site_not_operating`, which pause progress and never end
     it;
   - `absent` (no open site in the apprentice's region) and `no_room`, which pause it
     too but count toward a long absence.
5. **Long absence.** More than `MAX_GAP` consecutive absent turns end the apprenticeship
   as `long_absence`. The consecutive-miss dropout and the `away`/`departed`/`migrated`
   endings of version 1 are gone. When a site closes, its apprentices become absent
   (shown in `detached`) until they reach another site's region or the long absence ends
   them.
6. **Other endings stay.** `died` (before the turn, or in the tick, when that turn does
   not count), `occupation_changed`, `remobilised`, `service_qualified` (a crew
   apprentice who reaches `SERVICE_TURNS` first), `completed`, `pool_reset` and
   `disabled`.
7. **A change of controller** does not end an apprenticeship, as in version 1.
8. **Who is taken on.** New apprentices are adult farmers of the site's region, not
   qualified, not apprenticed, not enlisted, and not travelling or holding work. The
   order is:
   - RS3 veterans (`priority_ids`);
   - then members of this turn's crew, because the qualification is used only on the
     crew (upkeep and teaching);
   - then the region's other residents, attached;
   - youngest first within each group.

   **The age rule.** Nobody older than `max_entry_age() = AGE_ELDER − COMPLETION_TURNS`
   (50) is taken on. They would reach `AGE_ELDER` (60) before completing, and elder
   mortality is 0.016 a turn against 0.0025 for adults (`agent.rs`). D2 found 80% of
   qualifications ending in death within the run. The rule rests on that finding and
   the mortality bands, not on held outcomes.
9. **The control.** `no_qualification` keeps every seat, attachment, crew time, stipend,
   withheld income and record. It grants no qualification at completion. Its graduates
   stay unqualified and can still qualify by service, so crowding out between the two
   routes shows.

Interactions:

- **RS2.** `seated_mentors` keeps the mentors that the present continuing apprentices
  rely on off repair crews. RS2 can draw a continuing apprentice who lives in the city
  onto a repair crew; that turn is `unavailable` and pauses progress.
- **RS3.** Every apprentice aboard in a turn is reported to RS3 with `note_outcome`.
- **Wear, upkeep, service and the qualification** are as in version 1.

### Useful-work records (version 2)

Per operating site-turn (`receipts[]`):

- `qualified_on_crew`;
- `graduates_on_crew` (people who completed an apprenticeship, in either mode, on the
  crew);
- `covered` (at least one qualified crew member);
- `full_offset` (the wear was fully offset);
- `offset_by_via` (the upkeep offset delivered by `apprenticeship` and by `service`
  qualifications; attributed in crew order, each member giving up to `UPKEEP_SHARE`);
- `offset_by_graduates`.

`graduates` lists every living person who completed, with `granted`, crew-turns and
upkeep since. Each seat has `aboard` and `transferred_from`. Each record has `absent`,
`first_site`, `entry_age`, `transfers`, `on_crew` and `attached`.

The counters add:

- `graduate_crew_turns`, `covered_site_turns`, `full_offset_site_turns` and
  `qualified_crew_turns`;
- `upkeep_offset_apprenticeship`, `upkeep_offset_service` and
  `upkeep_offset_graduates`;
- `graduates`, `graduates_died` and `graduates_refused_cap`;
- `transferred`, `apprentice_turns_on_crew` and `apprentice_turns_attached`;
- `miss_absent`, `miss_no_room` and `end_long_absence`.

The success measure in the plan is graduate crew-turns on operating sites and operating
site-turns covered by a qualified member, TR against NQ under the shared wear.

### Declared parameters (version 2)

| Constant | Value | Version-2 meaning |
| --- | --- | --- |
| `MAX_GAP` | 4 (unchanged) | consecutive *absent* turns tolerated; one more ends it (`long_absence`); other misses pause |
| `COMPLETION_TURNS` | 10 (unchanged) | attended turns to complete |
| `max_entry_age()` | 50 (derived) | `AGE_ELDER − COMPLETION_TURNS` |
| all others | unchanged | as in the version-1 table |

### Tests

- `tests/test_apprenticeship_v2.py` (offline, oracle chunk `recovery-skills`) covers:
  - region residents outside the city attend attached, without displacing the crew,
    with the reservation and withheld income checked;
  - on-the-job counting with and without a mentor aboard, and pause;
  - capacity;
  - a migrant transferring;
  - absence and return, and the long absence;
  - `no_room`;
  - unavailable turns pausing;
  - death, occupation, army and death in the tick;
  - site closure, then transfer or long absence;
  - a change of controller;
  - the age rule and the crew-first order, and veterans first;
  - completion in both modes with the useful-work records and graduates;
  - stipends for attached time only;
  - a failed tick;
  - `seated_mentors`;
  - exact JSON and pickle round trips inside live apprenticeships;
  - a version-1 state (and an emulated pre-PL2 pickle) resuming under version 1 and
    serializing exactly as before;
  - inconsistent versions refused;
  - the dated snapshot;
  - feature-off worlds have no state.
- `tests/test_apprenticeship_v2_native.py` (real extension, template seed 7, 72 turns)
  covers:
  - every taught apprentice is a living adult farmer of the site's region holding
    exactly one commitment (its crew reservation, or an apprentice reservation of 0.5),
    with no conflicts;
  - apprentices complete (turns 66, 67 and 70) with attended turns while living in the
    region outside the city box, and with transfers;
  - crew time and wear close;
  - an exact checkpoint at turn 62, inside live attached apprenticeships with
    `--operating-wear`, resumes byte for byte;
  - `W_wear` against `W_operate`;
  - the switch adds only records to an RS1 run.

### Development worlds (PL2)

200 turns on 12 development worlds (template 3, 7, 9, 11, 23 and 42; procedural 32 × 10
worlds 7, 11, 13, 17, 21 and 31: the D2 set), one run per arm and world. The base
flags, as in D2, are `--grain-reserves --public-grain-shipments --scholarship
--techniques --academy-services --grain-storage --workshops`. Run with
`PYTHONHASHSEED=0 RAYON_NUM_THREADS=1` on native extension `6c675042…` and source
`6b32fd26` plus this documentation.

The version-1 arms (NQ v1, TR v1) run this source with a version-1 state (the rules a
pre-PL2 checkpoint resumes under). Its results equal D2's on `main`: TR v1 has 538 and
464 enrolments with 15 and 5 completions, exactly D2's figures. These are development
worlds, so they are evidence about the mechanism, not of an effect. Sums over the six
worlds of each stratum.

| Arm | Stratum | Operating site-turns | Lump repairs | Mean condition | Covered by a qualified member | Graduate crew-turns | Site-turns with a graduate aboard | Completions (granted) | Qualified by service / apprenticeship | Upkeep offset / wear | Full-offset site-turns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W_operate | template | 2554 | 3 | 0.956 | — | — | — | — | — | 0 / 0 | — |
| W_wear | template | 2531 | 96 | 0.766 | 0 | — | — | — | — | 0 / 50.6 | 0 |
| NQ v2 | template | 2441 | 71 | 0.763 | 728 (29.8%) | 336 | 279 (11.4%) | 72 (0) | 208 / 0 | 9.8 / 48.8 | 209 |
| TR v2 | template | 2472 | 67 | 0.769 | 818 (33.1%) | 328 | 282 (11.4%) | 80 (80) | 166 / 80 | 11.3 / 49.4 | 252 |
| NQ v1 | template | 2504 | 75 | 0.757 | 703 (28.1%) | 13 | 13 (0.5%) | 7 (0) | 162 / 0 | 9.4 / 50.1 | — |
| TR v1 | template | 2534 | 73 | 0.757 | 771 (30.4%) | 114 | 106 (4.2%) | 15 (15) | 156 / 15 | 10.4 / 50.7 | — |
| W_operate | procedural | 3139 | 18 | 0.912 | — | — | — | — | — | 0 / 0 | — |
| W_wear | procedural | 3169 | 121 | 0.732 | 0 | — | — | — | — | 0 / 63.4 | 0 |
| NQ v2 | procedural | 2939 | 97 | 0.727 | 673 (22.9%) | 132 | 117 (4.0%) | 43 (0) | 200 / 0 | 9.6 / 58.8 | 197 |
| TR v2 | procedural | 3156 | 93 | 0.735 | 936 (29.7%) | 363 | 275 (8.7%) | 81 (81) | 204 / 81 | 14.4 / 63.1 | 393 |
| NQ v1 | procedural | 3395 | 113 | 0.722 | 679 (20.0%) | 57 | 51 (1.5%) | 8 (0) | 172 / 0 | 9.1 / 67.9 | — |
| TR v1 | procedural | 3278 | 111 | 0.719 | 568 (17.3%) | 40 | 31 (0.9%) | 5 (5) | 158 / 5 | 7.6 / 65.6 | — |

Notes on the columns:

- *Graduate crew-turns* are crew-turns on operating sites by people who completed an
  apprenticeship in an earlier turn, granted or not.
- *Full-offset* site-turns are recorded only by version 2; the version-1 cells are not
  measured.
- **Upkeep offset by route** (version 2): TR v2 apprenticeship qualifications delivered
  3.1 / 3.0 (template / procedural) of 11.3 / 14.4. NQ v2 graduates delivered 1.4 / 0.4,
  after qualifying by service.

Endings of every apprenticeship enrolled, by reason, and attended turns at the end
(still open at turn 200 included):

| Arm | Stratum | Enrolled | Completed | Long absence | Migrated | Departed | Dropout | Died | Occupation changed | Service qualified | Other | Open | Attended 1–2 | 3–5 | 6–9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ v2 | template | 350 | 20.6% | 24.0% | — | — | — | 9.1% | 25.1% | 12.3% | 0.6% | 8.3% | 28.6% | 34.3% | 15.1% | 20.6% |
| TR v2 | template | 382 | 20.9% | 20.9% | — | — | — | 10.5% | 24.3% | 11.5% | 0.0% | 11.8% | 29.3% | 28.8% | 19.1% | 20.9% |
| NQ v1 | template | 512 | 1.4% | — | 45.1% | 20.5% | 8.2% | 9.2% | 8.4% | 3.1% | 0.6% | 3.5% | 64.8% | 23.6% | 7.2% | 1.4% |
| TR v1 | template | 538 | 2.8% | — | 42.4% | 22.3% | 7.1% | 10.2% | 8.2% | 3.2% | 0.6% | 3.3% | 61.5% | 24.5% | 8.6% | 2.8% |
| NQ v2 | procedural | 370 | 11.6% | 37.6% | — | — | — | 15.7% | 15.1% | 11.4% | 0.8% | 7.8% | 41.4% | 27.3% | 18.1% | 11.6% |
| TR v2 | procedural | 485 | 16.7% | 37.3% | — | — | — | 14.2% | 17.1% | 8.2% | 0.2% | 6.2% | 34.0% | 27.4% | 20.2% | 16.7% |
| NQ v1 | procedural | 512 | 1.6% | — | 38.7% | 26.0% | 7.4% | 9.6% | 9.2% | 3.3% | 1.2% | 3.1% | 63.1% | 23.8% | 6.1% | 1.6% |
| TR v1 | procedural | 464 | 1.1% | — | 37.9% | 25.2% | 7.1% | 11.6% | 9.3% | 3.9% | 1.5% | 2.4% | 65.1% | 22.6% | 4.1% | 1.1% |

In the table above:

- "Other" is `site_closed` and `remobilised`.
- 1–7% of records ended with 0 attended turns (death in the first tick); they are
  omitted from the attended columns.
- **Transfers between sites** (version 2): 201 / 240 template and 85 / 97 procedural
  (NQ / TR).
- **Attended turns on the crew / attached**: NQ v2 731 / 978 and TR v2 768 / 1141
  (template); NQ v2 708 / 821 and TR v2 1011 / 1269 (procedural).

What this shows (development worlds; a held screen is the evidence):

- **The maintenance assumption is most of the repairs.** `W_wear` − `W_operate` is
  +93 / +103 lump repairs and −0.19 / −0.18 mean condition.
- **Training against the control.** Under the shared wear, TR v2 needs 4 / 4 fewer
  repairs than NQ v2. This is the comparison training is judged by.
- **Region attendance and portable progress retain apprentices.** Completions rise
  from 1–3% of enrolments (version 1) to 12–21% (version 2), and endings after 1–2
  attended turns fall from 62–65% to 29–41%. The `migrated` and `departed` endings
  (63–66% in version 1) are replaced by the long absence, at 21–24% template and 37%
  procedural.
- **Graduates do more useful work in version 2.** In TR v2 they are aboard 11.4% /
  8.7% of operating site-turns (TR v1: 4.2% / 0.9%), with 328 / 363 graduate crew-turns
  (TR v1: 114 / 40).
- **The primary measure against NQ v2 under the shared wear.** Covered site-turns are
  33.1% against 29.8% (template) and 29.7% against 22.9% (procedural). Graduate
  crew-turns are 328 against 336 (template) and 363 against 132 (procedural).
  - In template worlds NQ graduates stay on the crew about as often but cannot keep the
    site.
  - Full-offset site-turns are 252 / 393 against 209 / 197.
  - **Crowding out.** Service qualifications fall from 208 to 166 (template) as
    graduates qualify by apprenticeship instead; procedural service qualifications are
    unchanged (200 / 204).
- **Occupation change is now the largest single ending in template worlds** (24–25%).
  The native occupation model moves farmers to other trades, and both arms show it.
  Nothing was tuned.

Reproduce one arm (any directory; drop `--apprenticeship …` for `W_operate`, add
`--operating-wear` alone for `W_wear`):

```sh
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 python -m chronicler.main --seed 7 --turns 200 \
  --agents hybrid --simulate-only --grain-reserves --public-grain-shipments --scholarship \
  --techniques --academy-services --grain-storage --workshops --apprenticeship \
  [--apprenticeship-mode no_qualification] --output out/chronicle.md --state out/state.json
```

Feature-off and version-1 identity (`6b32fd26` against the phase head `bec63b5b`,
each importing its own `src`, native `6c675042…`):

- 7 cases, 82 files, 0 differences (bundles compared without `metadata.generated_at`):
  - template seeds 7 and 11 with no switch;
  - seed 7 with `--workshops`;
  - seed 7 with `--workshops --workshop-payroll --scholarship --techniques
    --academy-services`;
  - procedural seed 21 with the base flags and `--workshops`;
  - RS1 version 1 on template 7 (90 turns, against the base's RS1);
  - RS1 version 1 on procedural 21 (`no_qualification` with payroll).

### Limits (version 2)

- **The crew is still the city box.** Natively only city residents can be on a crew,
  so a graduate who lives outside the box cannot do upkeep or teach until they live in
  it again. A crew pool drawn from the region would need a native change, which this
  lane did not make.
- **The viewer reads schema 1 only.** `viewer/src/lib/apprenticeship.ts` reports a
  version-2 record as malformed, never misread; PL5 adds a version-2 reader.
- **No fresh version-1 run from the command line.** The rules have no CLI option, so
  version 1 is reached only through a saved state (or a test that sets
  `RULES_VERSION`).
- **The age rule and the crew-first order** are part of version 2, not separate
  switches.
- **Not run:** held screens, and the 200-seed and procedural qualification gates.
