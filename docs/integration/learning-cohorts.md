# Named learners at academies (L5, `--learning-cohorts`, default off)

Sprint 2 of the livelihoods/commons plan
([plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md)). This page
records what the package implements, what it does not, and its evidence.

Enable with `--agents hybrid --cities --scholarship --techniques
--academy-services --learning-cohorts`. `--learning-cohort-mode` chooses
`learn` (the default) or `no_learning`, the cost-retaining control. The
switch is refused without `--agents hybrid` or without academy services. A
world that never enabled it has no container, snapshot key, checkpoint flag
or manifest entry. While academy services are paused the package is dormant.
`--no-learning-cohorts` closes open cohorts (reason `disabled`). The mode
cannot change while a cohort is open.

## What it extends

Academy services ([candidate](academy-services-candidate.md)) buy crafts into
an academy's custody and reserve real Scholars' ordinary work. One delivered
Scholar work unit serves eight *learner-equivalents* and uses one paid craft
each. Delivered service scales the academy's regional technique-adoption
increment in the next turn. Nobody in particular learns anything.

L5 puts named people in some of those seats. Teaching still happens only as
academy services deliver it, and supplies are still bought and used only by
academy services. L5 never buys, spends or invents a craft or a teacher. Its
learners occupy part of the delivered learner-equivalents. The regional
technique effect is unchanged: individual learning and regional practice
stay separate.

## Learning outcome and its consumers

A course teaches the trade the learner practises when they enrol. Completion
raises their skill in that occupation (`AgentPool.skills[slot * 5 +
occupation]`) by `COMPLETION_GAIN`, never above 1. The skill belongs to the
person. It goes with them when they migrate, and counts for whichever
civilization controls the region where they live.

The existing native consumers then read that skill. L5 adds no new consumer:

- **Civ capacity.** The hybrid write-back sets each civilization's military,
  economy and culture from the active skill of its soldiers, merchants,
  scholars and priests (`AgentPool::compute_aggregates`). Farmers' skill is
  not part of it.
- **Purpose need.** Purpose is restored in proportion to the skill of the
  person's current occupation (`needs.rs`), for every occupation.
- **Promotion gate.** A person whose skill stays above 0.9 for 20 turns
  becomes a named-character candidate (`named_characters.rs`).

Ordinary practice also raises the current occupation's skill by 0.05 a turn,
up to 1. A course therefore brings capability forward: a graduate reaches a
given skill earlier. It does not raise the ceiling, and its effect fades as
practice catches up. A graduate who switches occupation keeps the learned
skill in the old trade. The existing switch rule floors the new trade's skill
at 0.3 and keeps any higher value, so the learned skill matters again if they
switch back.

## Cohorts

- **Identity and bounds.** There is at most one open cohort per live academy
  incarnation, which is identified by seat index, region, founder, founding
  turn and name (the academy-services binding). There are at most
  `MAX_COHORTS` (8) open cohorts in all, each with at most `MAX_LEARNERS` (8)
  members. `cohort_id` is a counter and is never reused. Up to 16 closed
  cohorts are archived and the last 32 completions are kept. Lifetime totals
  are scalar counters.
- **Formation.** A cohort forms at a live academy that holds paid supplies
  for at least one learner (`CRAFTS_PER_LEARNER`) and has at least
  `MIN_COHORT` (2) eligible people. Cohorts are finite: nobody joins after
  formation.
- **Eligibility.** The native planner `AgentSimulator.plan_learners`
  (`chronicler-agents/src/learning_work.rs`) makes one read-only pass over the
  pool. A recruit must be:
  - alive and an adult (`AGE_ADULT`);
  - not a Scholar (Scholars teach);
  - resident in the academy's region;
  - not on a merchant trip and not on an army roster;
  - not already holding work this turn: in the shared work registry
    (workshop crews), in rural health care (`health_work_loss` > 0) or in a
    pending teaching plan;
  - not already in another cohort;
  - left with room to learn: current-occupation skill at most
    `ELIGIBLE_SKILL_MAX` (0.75).

  Recruits are ordered by lowest current skill, then stable id. Every
  exclusion is counted under its reason.
- **Availability each turn.** The planner runs immediately before the native
  agent tick, after Phase 2 health work and workshop crews are in the
  registry. It reports each active member's status:
  - dead: the member exits (`died`);
  - in another region: exits (`migrated`). Completed learning has already
    gone with them; unfinished progress does not;
  - in another occupation, or a Scholar: exits (`occupation_changed`);
  - on a trip, enlisted or holding other work: misses the session. After
    `ABSENCE_LIMIT` (3) consecutive misses the member exits (`absent`).

  Care, travel and army service exclude a person only through those
  mechanisms' own records of that person. Nothing else is invented.
- **Reservation.** Available members are reserved in the work registry
  (category 1, learning) for `ATTENDANCE_FRACTION` (0.5) of the turn, with
  `AgentSimulator.reserve_learning_attendance`. The call is all or none. It
  refuses anyone already holding work, and the native tick refuses any
  overlap.
- **Seats come only from delivered teaching.** In the native wealth phase,
  delivered Scholar work per region is computed exactly as the wealth loop
  delivers it: a live Scholar with the same id and region, capped by existing
  health work. Each delivered unit seats `LEARNERS_PER_SCHOLAR` (8) learners,
  in enrolment order. With no teacher, no supplies, unpaid upkeep or too
  little teaching for one seat, there is no seat. After the tick, Python
  checks the native seats against the same turn's academy-services teaching
  receipt and refuses any mismatch.
- **Attendance costs time.** A seated learner's ordinary occupational income
  for the turn is reduced by the attended fraction. The native wealth phase
  applies this after the teaching deduction and before rural health care,
  like `health_work_loss`. The receipt records the income and the amount
  withheld. An unseated learner keeps their income and makes no progress. A
  learner whose income is zero (for example a merchant with no trade income)
  attends at no money cost.
- **Progress and completion.** Each seated turn is one attended session. At
  `SESSIONS_TO_COMPLETE` (4) sessions the member completes. In `learn` mode
  the skill is granted after the tick (`grant_learning_skill`), and consumers
  read it from the next native tick. A member who attended their last
  session but died later in the same tick exits (`died`) without a grant.
- **Closure.**
  - A cohort with no session for `STALL_LIMIT` (6) turns closes (`stalled`).
  - A cohort whose academy falls or is replaced closes (`academy_lost`). The
    successor academy forms its own cohort, and progress is not carried over.
  - A cohort with no active member left closes (`finished`).
- **Why no session.** Each cohort-turn without a session records one reason,
  taken from the same turn's teaching receipt: `no_available_member`,
  `upkeep_unmet`, `no_supplies`, `no_teacher`, `too_little_teaching`,
  `members_absent` or `services_unknown`.

### No-learning control

`--learning-cohort-mode no_learning` keeps everything above: formation,
reservation, seats, withheld income, the academy's teaching and supply use,
and completions. It only stops the grant (`grant_learning_skill` with gain 0
reads the skill and changes nothing). Until the first completion the two
modes produce identical worlds and native states. Turning academy services
off is not this control: it restores the legacy unmetered technique
adoption.

### Timing, identity and observations

`snapshot.livelihoods.learning_cohorts` (schema 1, stage `L5`) includes:

- the open cohorts with their members;
- the archived cohorts, summarized;
- the recent graduates (skill before and after);
- the lifetime counters and the declared parameters;
- `receipts`: one row per cohort for `source_turn`. It is `null`, meaning
  unknown and not zero, when no cohort turn completed in that turn.

No randomness is drawn. The native attendance plan is transient, never
checkpointed, and taken once after the tick; Python state holds no pending
work across a turn boundary. If the agent tick (or a livelihoods before-tick
hook) raises, `livelihoods.wrap_agent_tick` calls each package's
`rollback_agent_tick`: the unconsumed attendance and its registry rows are
cancelled, as academy services cancel their teaching reservation, and the
paid-work share, fare policy and food allocation are disarmed. A failed
kernel is still not rolled back (added after the R1 review on 2026-11-05).

All parameters are declared modeling choices, not calibrated:
`ATTENDANCE_FRACTION`, `SESSIONS_TO_COMPLETE`, `COMPLETION_GAIN`,
`ELIGIBLE_SKILL_MAX`, `MIN_COHORT`, `ABSENCE_LIMIT`, `STALL_LIMIT`,
`MAX_LEARNERS` and `MAX_COHORTS`.

## Evidence

All checks below ran on 2026-11-05 on the branch source in a 4-core cloud
container with Python 3.13 and the native extension built fresh from it.

### Tests

- **Rust** (`cargo test --locked --lib learning_work`), 8 tests:
  - recruitment order and every exclusion, counted by reason;
  - member status: dead, elsewhere, trip, army, other work;
  - refusals: invalid requests, duplicate membership, a pending plan,
    invalid rows (all or none);
  - seats only from delivered teaching: half a Scholar-day seats four of
    six learners, and the cost is the attended share of income;
  - no teaching means no seat and no cost;
  - a learner who died before the wealth phase is absent; cancel releases
    the registry;
  - grants are capped and travel with the agent; a zero gain only reads;
  - a migrant graduate's skill counts in the new controller's military
    aggregate (`compute_aggregates`).

  The affected modules (`workshop_work`, `teaching_work`, `health_care`,
  `tick::`, `pool::`, `ffi::`, `persist`) and the whole lib unit suite
  (682 tests, then 683 with the migrant test) pass.
- **Offline** (`tests/test_learning_cohorts.py`), 15 tests. A small fake
  implements the native rules. The tests cover:
  - prerequisites, and dormancy while services are paused;
  - matched staff and supplies through to a completed capability;
  - the no-learning control: equal costs, no capability change;
  - no supplies, no teacher, unmet upkeep, too little teaching and absent
    members;
  - no student time, and exit after three absences;
  - an interrupted cohort: death, migration, occupation change, and death
    after the last session;
  - an academy lost and replaced: progress is not carried over;
  - stall, and the formation supply threshold;
  - exact pickle and JSON round trips, dated snapshots, and unknown that
    is not zero;
  - disable and mode switching, the bounded archive and never-reused ids;
  - append-only codes.

  They pass under the bounded lane's offline guard (guard state PASS, no
  native module loaded).
- **Native** (`tests/test_learning_cohorts_native.py`), 9 tests on the real
  extension:
  - **Exact cost.** Against an identical native control, half a Scholar-day
    seats four of six learners. Each seated learner's wealth is lower by
    exactly `charged × 0.98` (the withheld income after the model's decay);
    the two unseated learners' wealth is unchanged. The tick refuses an
    attendance prepared for another turn, and the registry holds the
    learners under category 1.
  - **Civ capacity consumer.** Granting 0.25 to eight soldiers raises their
    civilization's military aggregate and changes no other civilization; a
    zero gain changes nothing.
  - **Learn against no-learning.** On the declared-academy world:
    - worlds, native states and every cost counter are identical through
      turn 3;
    - completion falls in turn 4; graduates' skill is the skill before plus
      0.25 in learn mode and unchanged in the control;
    - two turns later, graduates still practising the learned trade have
      higher skill and a higher purpose need;
    - graduates who had moved to another region keep the extra skill.
  - **No teacher.** Every Scholar dies at the start of the tick: teaching is
    requested but not delivered, nobody has a seat, nothing is charged, and
    the reason is `no_teacher`.
  - **No student time.** Another consumer holds every member: nobody is
    reserved, nothing is charged, and the reason is `no_available_member`.
  - **Interruption.** A member killed mid-course is absent, then exits as
    `died`; the others continue.
  - **Replacement school.** A declared fall and refounding closes the cohort
    as `academy_lost`, and a new cohort with a new id starts at the new
    academy.
  - **Exact resume.** A checkpoint with an open cohort resumes exactly: world
    JSON, native state and Python RNG are equal after three more turns,
    including a completion.
  - **Feature off and dormant.** An absent switch and `--no-learning-cohorts`
    give identical bundles. With the switch on, a world that never forms a
    cohort has an identical history apart from the new key.

  Related suites also pass: academy services, workshops (one work
  commitment alongside health care and teaching), food allocation, Batch
  Lab academy and what-if academy (38 tests in all). The module skips
  cleanly without the extension.
- **Viewer.** `src/lib/__tests__/learningCohorts.test.ts` (4 tests) and
  `src/components/systems/__tests__/LearningCohorts.test.tsx` (2 tests) pass;
  lint and build pass. The full suite ran on a heavily shared container:
  1,222 of 1,224 passed. The two failures were AppShell timing tests that
  do not import these files, and both passed when rerun alone. The reader
  and component are not mounted; the lead mounts them in `LivelihoodsPanel`.

### Feature-off identity against the sprint-2 base

Two runs of template seed 1, with cities, scholarship, techniques and
academy services, were compared byte for byte (bundle without
`metadata.generated_at`):

- the base source (`0cc62442`) with its own freshly built extension;
- the branch source with its extension and the switch off.

The bundles are identical over 200 turns, a span that includes the seed's
academy teaching turns. They are also identical over 60 turns with
`--workshops --food-allocation`, where the livelihoods container exists and
L5 is off.

### Development funnel (template seeds 1–3, 200 turns)

Run with `scripts/learning_cohorts_funnel.py run OUT --seeds 1,2,3` (arms:
services only, learn, no learning). Worlds are the units.

| Stage | Seed 1 | Seed 2 | Seed 3 |
| --- | --- | --- | --- |
| Academies founded | 2 | 1 | 2 |
| Live academy-turns | 96 | 26 | 13 |
| Academy-turns with a supply purchase | 3 | 0 | 0 |
| Academy-turns with delivered teaching | 5 | 0 | 0 |
| Cohorts formed | 0 | 0 | 0 |
| Learners attending, completions, capability changes | 0 | 0 | 0 |
| Downstream effect (learn against no learning) | none: identical | none: identical | none: identical |

The bottleneck is the academy's paid supplies, not eligibility. A per-turn
diagnosis of seed 1's region-1 academy (turns 166–199) found 1 to 11 adults
with room to learn among 18 to 36. The academy held at most 1.1 crafts, and
only in turns where at most one person was eligible, so the two conditions
never met.

In all three worlds, with the switch on and no cohort formed, the history
equals the services-only arm (apart from the new key) for all 200 turns.
These template economies are too small for academy services to buy
supplies regularly. The held cohort was not run.

### Constructed control (declared academy)

`scripts/learning_cohorts_funnel.py constructed --turns 30` replays the
native tests' declared-academy world in both modes. It demonstrates the
mechanism; it is not a natural-world result.

| | learn | no learning |
| --- | --- | --- |
| Cohorts formed | 6 | 6 |
| Learners enrolled | 38 | 47 |
| Sessions (teacher and supplies delivered) | 26 | 26 |
| Learner-turns attended | 117 | 142 |
| Income withheld | 17.89 | 18.09 |
| Supplies occupied | 117 | 142 |
| Completions | 26 | 28 |
| Capability changes (skill granted) | 26 (5.95) | 0 (0) |
| Exits | 1 died, 8 migrated, 3 occupation changed | 7 migrated, 4 occupation changed |

- Completion first falls in turn 4. The arms are identical until then; after
  it they diverge, so later counts differ for that reason.
- The graduates' mean purpose need is higher in the learn arm from the
  next turn: +0.0021 in turn 5, rising to about +0.02 by turns 25–28.
- The world state outside the cohort record first differs in turn 11, when
  the changed needs begin to change decisions.
- Most graduates in this world were farmers, so the civ capacity consumer
  is shown by the direct grant test, not by this run.


## Limits and open questions

- Natural activation is limited by academy services, not by L5. In the
  development worlds, academies are few and rarely hold paid supplies, so
  few cohorts form. Constructed controls show the mechanism; the
  development worlds show how rarely the prerequisites meet.
- The learned trade is the one practised at enrolment. Because skill growth
  saturates, the benefit is a head start, largest for recent occupation
  switchers. The civ capacity consumer reads only soldiers', merchants',
  scholars' and priests' skill. Farmers' skill reaches only purpose and the
  promotion gate.
- Seats go to members in enrolment order, so under scarcity earlier members
  progress first. Members without a seat stay present at no cost.
- There are no wages, fees or tuition. The academy's supplies are paid by its
  patron through academy services. The learner's cost is forgone income.
- Batch Lab and live new-world setup do not expose the switch; the CLI and
  the gate runner do.
- The opt-in health-care observation's "pre-health base income" is copied
  after the attendance deduction (as it already is after teaching income), so
  with `--learning-cohorts` or `--workshop-payroll` it reports income net of
  those work commitments.
