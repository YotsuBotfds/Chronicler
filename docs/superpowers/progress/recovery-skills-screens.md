# Recovery skills: preregistered screens (RS7, sprint 3)

Written 2026-11-05, before any held-cohort run. These are bounded screens of default-off
experimental source, not powered scientific validation. The 200-seed and procedural
qualification gates remain out of scope and unrun. The independent units are worlds (seeds),
not agents or turns.

Any change to the arms, outcomes or analysis after this file is committed is recorded below
as a dated amendment with its reason, and only before the first held run.

## Fixed source and budget

- **Source.** The phase branch `claude/recovery-skills` at the commit recorded with the
  results, and the native extension built from that same commit. The runner writes both to
  `source.txt`, after checking that the runs import that checkout's `src`. Code may change
  between this file and the held run only to fix defects found by review or by the pilot.
  Each such fix is listed as an amendment, and none may change an arm, an outcome or a
  parameter in response to held outcomes, since none have been seen.
- **Budget, frozen here.** 2.0 core-hours in total, at most 3 concurrent processes, and ≤ 6 GiB
  of transient disk. Raw outputs are deleted after metric extraction; one example world per
  stratum is kept outside the repository.
- **Timing pilot.** One run of every arm on two development worlds: template seed 2 and
  procedural 32×10 seed 7. Neither is in any held cohort. It is used only to set the budget
  and to find defects; its outcomes were not used to choose arms, outcomes or parameters.
  - Run on `89e423cf` with native `6c675042…`, 2 concurrent processes, while three review
    agents shared the 4-core machine, so the timings are pessimistic.
  - All 38 runs succeeded and every outcome extracted. Template runs averaged 7.4 s (max
    8.8) and procedural 20.9 s (max 23.5).
  - That projects the 228 held runs at about 0.90 core-hours.
  - The pilot found no defect. One development-world observation is recorded because it
    explains a likely null; it changed nothing. In template seed 2, RS2 opened 5 granary projects (3 after war damage, 2 for wear),
    but every one of its 938 stalled project-turns was stalled for want of timber (the
    region's stockpile), so no repair work was delivered. The RS2 lane measured the same
    (89–100% of stalls).
- **Development cohort, inspected freely.** These are the worlds the lanes and the lead used
  while building:
  - template seeds 3, 7, 9, 11, 23 and 42;
  - procedural seeds 7, 11, 13, 17, 21, 31, 302 and 303.
- **Held cohort, fresh.** Template (8 regions, 4 civs) seeds 501–506 and procedural (32
  regions, 10 civs) seeds 601–606. Hybrid agents, 200 turns. No earlier sprint, lane or pilot
  ran these seeds; `tests/test_recovery_skills_wiring.py` checks they are disjoint from
  sprints 1–2 and the pilot.
- **Common base for every arm.** `--grain-reserves --public-grain-shipments --scholarship
  --techniques --academy-services --grain-storage`, so one off arm is the root control.
  Workshops, where an arm enables them, run in their default operate mode.
- **Incomplete runs.** If the budget runs out, unfinished strata are reported as incomplete,
  never silently dropped.

## Arms

Each arm is compared with its declared control arm on the same world
(`scripts/livelihoods_screens.py`, `ARMS3`). The primary comparison for each package uses its
cost-retaining control: `no_qualification`, `cost_only` or `record_only`. The control keeps
the package's costs, reservations and records but withholds its effect.

| Arm | Flags added to the base | Control | Question |
| --- | --- | --- | --- |
| off | none | — | root control |
| W_operate | `--workshops` | off | reference for RS1–RS3 (operate-mode workshops) |
| RS1_train | `--workshops --apprenticeship` | RS1_no_qualification | do mentors train apprentices who qualify, and does qualified upkeep keep sites operating? |
| RS1_no_qualification | `... --apprenticeship-mode no_qualification` | W_operate | cost-retaining control: same seats, time and stipends, no qualification granted |
| RS2_repair | `--workshops --repair-projects` | RS2_cost_only | do paid projects restore granaries and workshop sites? |
| RS2_cost_only | `... --repair-mode cost_only` | W_operate | cost-retaining control: same crews, wages and timber, condition unchanged |
| RS2_no_war_damage | RS2_repair with tuning `repair_projects.war_damage: 0` | RS2_repair | ablation: no damage records at real war events |
| RS3_priority | `--workshops --veteran-reintegration` | RS3_record_only | does priority access place released soldiers in work? |
| RS3_record_only | `... --veteran-mode record_only` | W_operate | control: the same records, no priority |
| RS4_send | `--remittances` | RS4_record_only | do settled migrants send bounded support home along real bonds? |
| RS4_record_only | `--remittances --remittance-mode record_only` | off | control: the same ledger and amounts, nothing sent |
| RS5_enforced | `--clearing-protection` | RS5_cost_only | does a funded protection keep forest cover from clearing, and at what cost? |
| RS5_cost_only | `--clearing-protection --clearing-protection-mode cost_only` | off | cost-retaining control: adoption and payment, clearing unchanged |
| T_commons | `--timber-stock --commons-rules` | off | reference for clearing × commons |
| I_clearing_commons | T_commons + `--clearing-protection` | T_commons | interaction: clearing protection × commons rules |
| I_appr_repair | RS1_train + `--repair-projects` | RS2_repair | interaction: apprenticeship × repair (qualified repairers) |
| I_vet_appr | RS1_train + `--veteran-reintegration` | RS1_train | interaction: veterans × apprenticeship |
| I_repair_budgets | RS2_repair + `--local-budgets` | RS2_repair | interaction: repair × local budget envelopes |
| ALL3 | every RS switch on | off | all recovery-skills switches together |

Feature-off identity, exact checkpoint/resume and Python/Rust clearing parity are tested
elsewhere (`turn_speed_identity`, `checkpoint_identity`, native tests), not as screen arms.

## Outcomes (per world, against the arm's control on the same world)

The report's preregistered table is `PAIRED3` in `scripts/livelihoods_screens.py`. It prints
every world's value with the stratum's mean, range and sign counts (>0 / <0 / =0). Worlds
whose arm or control failed, or whose outcome is unknown, are listed as such.

- **RS1.**
  - People qualified through apprenticeship, upkeep offset, mean workshop condition at the
    end and operating site-turns, each train against no_qualification.
  - Enrolled apprentices, completions and income forgone (train alone).
  - Adverse:
    - lump repairs and end condition against W_operate (the switch adds operating wear);
    - income forgone without completion.
- **RS2.**
  - Granary condition and capacity at the end, workshop condition at the end and operating
    site-turns, each repair against cost_only.
  - Granary condition against W_operate (the legacy maintain request).
  - Coins charged, timber used and stalled project-turns (repair alone).
  - War damages recorded and granary condition, repair against no_war_damage.
- **RS3.** People placed and placements, priority against record_only; veterans captured and
  waiting veteran-turns (priority alone).
- **RS4.**
  - Wealth credited to recipients and courier fees, send against record_only. The fees leave
    the economy: an adverse outcome, always reported.
  - The linked share of eligible sender-turns.
- **RS5.**
  - Mean forest cover at the end, enforced against cost_only and against off.
  - Coins charged, enforced against cost_only. These should be similar, since the control
    retains the cost.
  - Cover not cleared and protections adopted.
- **Interactions.**
  - apprenticeship × repair: qualified repair-crew turns and workshop condition;
  - veterans × apprenticeship: veterans enrolled and apprentice placements;
  - repair × budgets: granary condition, and projects stalled for want of an envelope;
  - clearing × commons: forest cover and timber extraction.
- **Shared outcomes.** Final total population and total treasury, as the mean of the
  per-world paired difference with its range over worlds.
- **Activation funnels.** Every declared counter of each package (`OUTCOMES3`), as the mean
  per world with its range and the number of worlds where it is zero. Null activation is
  reported, not hidden.

## Extractor validation

- Every outcome name is checked against the counters its package declares in source
  (`COUNTERS`, or `COUNTER_KEYS` for RS5). For RS2 the names are composed from its
  enumerations, and `_bump` refuses any other name.
- A run fails visibly (rc 3, with the reason in the report) when any of these holds:
  - an enabled package has no record in the last snapshot;
  - the record is not for the completed turn;
  - the record is in another mode;
  - the record carries an undeclared or non-numeric counter;
  - a package the arm leaves off wrote a record;
  - forest cover is missing for a region;
  - a workshop arm has no final sites.
- A workshop arm with no built site reports its condition as unknown, not zero.
- Constructed-bundle tests are in `tests/test_recovery_skills_wiring.py`.

## Stopping rules

- Every arm runs once per held world.
- Nothing is tuned after held outcomes are inspected.
- A run that raises, or fails extraction, is recorded as failed with its error and is not
  rerun silently.
- A failure in the held runs is a finding, investigated and reported. A fix would need a new
  held cohort to be evaluated.
- No significance claims. With six worlds per stratum, results are means, ranges and sign
  counts.

## Amendments

**2026-11-05, before any held run: defect fixes from the independent reviews.**
No arm, control, outcome, cohort, parameter or budget changed. The fixed
source can change feature-on trajectories, so the held run uses the source
after these fixes (recorded in `source.txt`). Each fix has a regression test
that fails on the previous code.

- **Phase 10 wealth after livelihoods after-hooks** (`414d9063`, layer `rv1`;
  review B, major; predates the phase). The post-tick batch is dropped once
  the hooks have moved wealth, so Phase 10 readers see wages, fares, stipends
  and remittances. This affects RS4_send, ALL3 and every arm with workshops.
- **Veteran apprentices in both RS3 modes** (`84ac1795`; review A, major).
  This affects I_vet_appr, ALL3 and the RS3 placement outcomes when
  apprenticeship is on.
- **RS5 planning precision and decision log** (`eecf3169`, layer `rv2`;
  review B, minor). Default tuning is unaffected in precision.
- **RS2 seizures, timber-supported worker-turns, open-record veterans, L9
  stake for shut sites, and seated mentors** (`59cf09a7`, `64962ad5`; review
  C).
  - `64962ad5` adds one declared, uncalibrated parameter, set as part of the
    defect fix and not from any outcome: a last partial repairer is hired
    only when the free timber supports at least `MIN_WORKER_TIMBER = 0.5` of
    their turn. The first fix's whole-turn rule left the RS2 native test world
    with no workshop repair at all.
  - The same commit makes the granary resource-ledger check (layer `rv3`) use
    the spoilage rate recorded at spoilage. That is check-only, with no
    outcome change.

## Results (held cohort, run 2026-11-05)

Artifacts in the repository:
- per-world metrics: `recovery-skills-screens/metrics.jsonl`, one row per arm and world;
- the generated report, with every world's value for each preregistered outcome:
  `recovery-skills-screens/report.md`;
- source identity: `recovery-skills-screens/source.txt`.

Re-summarize with `scripts/livelihoods_screens.py report ... --sprint 3`. The fixed seeds
reproduce the raw bundles.

- **Run.**
  - Source `a4adfde6` and native extension `6c675042…`.
  - 228 runs, 0 failed, and every outcome extracted (no rc 3). That took 0.86 of the 2.0
    core-hours, 20 minutes of wall time.
  - Every arm ran once per held world. Nothing was tuned or rerun.
- **Units.** Six worlds per stratum: t = template 8×4 (501–506) and p = procedural 32×10
  (601–606). Results are the mean over worlds, the range, and the counts of worlds above,
  below and at zero. These are screens, not significance tests.
- **Shared outcomes.** Population and treasury differences between arms (report, first
  table) are wide and of mixed sign in almost every comparison. Trajectories diverge
  once any switch acts, so these differences are not attributed to a mechanism.
  - Exactly zero differences confirm the controls: RS4_record_only = off, RS3_record_only
    = W_operate, and RS3_priority = RS3_record_only in all 12 worlds.

### Findings by package

- **RS1 apprenticeship.** It activates everywhere, but few apprentices finish, and the
  package's own wear makes workshops worse.
  - Per world: 88 apprentices enrolled in each stratum (6/6 worlds), about 210–220
    apprentice-turns attended, and 11 units of income forgone.
  - Completions, which equal new qualifications (train against no_qualification): 3.3 per
    world in t (3/6 worlds, range 0–14) and 0.8 in p (2/6, range 0–3).
  - Upkeep offset and end condition against no_qualification: near zero, and 0 in 4/6
    worlds per stratum. In p the end condition is lower in 2 worlds (−0.12, −0.23).
  - **Adverse:**
    - Against W_operate, operating wear added 10.5 lump repairs per world in t and 13.5 in
      p (6/6 each).
    - Mean workshop condition at the end fell by 0.35 in t (6/6) and 0.15 in p (5/6).
    - The income forgone mostly bought no completion.
  - Endings are dominated by migration (35 and 40 per world).
- **RS2 repair projects.** Granaries recover a little, timber is the binding constraint,
  and workshop repair is mixed.
  - Granary condition at the end, repair against cost_only: +0.030 in t (4/6 above, 2 at
    zero) and +0.079 in p (6/6). The same values hold against W_operate (the legacy
    maintain request).
  - Granary capacity at the end: no difference (0 in 12/12).
  - Workshop condition at the end: −0.08 in t (one world −0.46, five at zero) and +0.19 in
    p (5/6 above).
  - Operating site-turns: −87 in t (2 worlds −358 and −230) and +128 in p (5/6 above).
  - Coins charged: 181 per world in t and 708 in p. Timber used: 90 and 354.
  - **Stalls:** 963 project-turns per world in t and 1,938 in p, with 99% for want of
    timber.
  - War damage records (repair against no_war_damage): +1.8 in t and +5.2 in p. Removing
    them barely changes granary condition (−0.010 in t, −0.016 in p, mixed).
  - Named repair crews are rare without RS1: 0.2 person-turns per world in t and 38 in p.
- **RS3 veteran reintegration.** Veterans are captured in quantity, but priority changes
  almost nothing. This is a null.
  - Captured per world: 29 in t and 113 in p.
  - Waiting veteran-turns: 244 in t and 848 in p, mostly with no workshop site in their
    region.
  - People placed, priority against record_only: +0.5 in t (one world, +3) and +0.17 in p
    (one world, +1). Population and treasury are identical between the two modes in every
    world.
- **RS4 remittances.** It moves real money every turn along about 14–21% of eligible links,
  and a sixth of it leaves the economy as fees.
  - Credited to recipients at home, send against record_only: 926 wealth units per world
    in t and 1,161 in p (6/6 each).
  - **Adverse:** courier fees leaving the economy were 163 and 204 per world.
  - The linked share of eligible sender-turns was 0.21 in t and 0.14 in p. Most eligible
    senders had no partner left at home.
  - Rows: 99.8% applied; a few were limited by the recipient's ceiling; none were absent.
- **RS5 clearing protection.** Protected regions keep more forest, at a stated cost.
  - Mean forest cover at the end, enforced against cost_only: +0.025 in t and +0.057 in p
    (5/6 above in each stratum).
  - Against off: +0.013 in t (3/3 split) and +0.052 in p (5/6 above).
  - Coins charged, enforced against cost_only: 468 per world in t and 1,305 in p. This is
    expected, because cost_only pays only while clearing is active and clearing differs
    once protection holds cover.
  - Cover not cleared: 5.7 in t and 17.7 in p. Adoptions: 9.5 and 29 per world.
- **Interactions.**
  - *Apprenticeship × repair*, against RS2_repair:
    - qualified repair-crew turns: +2.2 in t and +0.3 in p (mostly zero);
    - workshop condition at the end: −0.44 in t (6/6 below) and −0.32 in p (5/6 below).
      RS1's wear outruns timber-limited repair.
  - *Veterans × apprenticeship*: veterans enrolled +1.3 in p (3/6) and 0 in t; apprentice
    placements recorded +2.0 in p (3/6).
  - *Repair × budgets*:
    - granary condition is unchanged (−0.005 in t, −0.004 in p, mixed);
    - 1,129 (t) and 2,374 (p) project-turns per world were stalled for want of an L9
      repairs envelope. Under the bargained budget, repairs rarely win.
  - *Clearing × commons*, against T_commons:
    - forest cover +0.026 in t (3/3 split) and +0.040 in p (5/6 above);
    - timber extraction +215 in t and +1,107 in p (6/6 each), because more standing
      forest is cut under the commons rule.
- **ALL3 against off.**
  - Population: +0.2 in t and +39 in p, mixed.
  - Treasury: −545 in t and −387 in p, mixed.
  - Every package activated in every world, except RS1 completions, which were 0 in t and
    0.3 in p.

### What this does and does not show

- The mechanisms run, account exactly and behave as declared on fresh worlds.
- In these short, bounded screens:
  - RS2 and RS5 move their primary physical outcomes, granary condition and forest cover,
    in the expected direction in most worlds.
  - RS4 moves real support to kin and costs a disclosed fee.
  - RS1 and RS3 are mostly nulls. RS1 also has a consistent adverse cost from its added
    operating wear.
- Nothing here qualifies any switch for default use.
- No parameter was tuned on these worlds. The constants remain declared and uncalibrated.
