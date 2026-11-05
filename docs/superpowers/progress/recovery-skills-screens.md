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
- **RS2 seizures, whole worker-turns, open-record veterans, L9 stake for
  shut sites, and seated mentors** (`59cf09a7`; review C).
