# Livelihoods sprint 2: preregistered screens (L11)

Written 2026-11-05, before any held-cohort run. These are bounded screens of a default-off
experimental source, not powered scientific validation. The 200-seed and procedural
qualification gates remain out of scope and unrun. The independent units are worlds
(seeds), not agents or turns.

Any change to the arms, outcomes or analysis after this file is committed is recorded below
as a dated amendment with its reason, and only before the first held run.

## Fixed source and budget

- Source: the sprint-2 integration branch at the commit recorded with the results, with the
  native extension built from that same commit (SHA-256 recorded). L7 must have landed; if it
  has not, its three arms and the relocation flag in `ALL` are reported as not run.
- Budget, frozen in the sprint-2 plan: 2.0 core-hours in total, at most 3 concurrent
  processes, ≤ 6 GiB transient disk. Raw outputs are deleted after metric extraction; one
  example world per stratum is kept outside the repository.
- Timing pilot: 36 runs on development worlds (template seed 2; procedural 32×10 seed 7, which is
  not in any held cohort) averaged 7.6 s (template) and 23.4 s (procedural). That projects the
  252 held runs at about 1.1 core-hours. The pilot recorded per-package metrics, but they were
  not used to choose arms, outcomes or parameters. The pilot did find one defect: L9's relief
  settlement counted L4 convoy spending twice and raised in the procedural world. It was fixed
  with a regression test before this file was written.
- Development cohort, inspected freely: template seeds 1–3 (and procedural seed 7 for
  robustness only).
- Held cohort, frozen in the sprint-2 plan: template (8 regions, 4 civs) seeds 301–306 and
  procedural (32 regions, 10 civs) seeds 401–406. Hybrid agents, 200 turns.
- Common base for every arm: `--grain-reserves --public-grain-shipments --scholarship
  --techniques --academy-services --grain-storage`, so one off arm is the root control.
- If the budget runs out, unfinished strata are reported as incomplete, never dropped
  silently.

## Arms

Each arm is compared with its declared control arm on the same world
(`scripts/livelihoods_screens.py`, `ARMS2`).

| Arm | Flags added to the base | Control | Question |
| --- | --- | --- | --- |
| off | none | — | root control |
| D1_workshops | `--workshops` | off | L1 downstream: do workshop crafts reach academy supplies and teaching? |
| L5_learn | `--learning-cohorts` | off | do named learners form, attend and complete? |
| L5_no_learning | `--learning-cohorts --learning-cohort-mode no_learning` | off | cost-retaining control for L5 (compare with L5_learn) |
| L6_paid | `--workshops --workshop-payroll` | D1_workshops | does a demand-backed job help its crew? |
| L6_unpaid_labor | `... --workshop-payroll-mode unpaid_labor` | D1_workshops | ablation: income share replaced, no wage |
| L6_no_customer | `... --workshop-payroll-mode no_customer` | D1_workshops | no customer: arrears, hours, layoffs, closure |
| T_timber | `--timber-stock` | off | reference for L8 |
| L8_enforced | `--timber-stock --commons-rules` | T_timber | does a paid rule protect the stand, and at what cost? |
| L8_cost_only | `... --commons-rule-mode cost_only` | T_timber | ablation: adoption and payment, no cap |
| I_timber_work | `--timber-stock --workshops` | D1_workshops | reference for the commons × workshop interaction |
| I_commons_work | `--timber-stock --workshops --commons-rules` | I_timber_work | commons rules × workshop timber demand |
| W_services | `--workshops --food-allocation --food-allocation-regime targeted_relief` | off | reference for L9 (its services, with targeted relief) |
| L9_bargained | W_services + `--local-budgets` | W_services | budgets × relief and maintenance |
| L9_fixed_shares | W_services + `--local-budgets --local-budget-mode fixed_shares` | W_services | control: same budget, fixed shares, no response |
| F_food | `--food-allocation` | off | reference for L7 |
| L7_liquidity_only | `--food-allocation --relocation-costs --relocation-mode liquidity_only` | F_food | liquidity restriction alone |
| L7_paid | `... --relocation-mode paid` | L7_liquidity_only | actual fare paid on applied moves |
| L7_assisted | `... --relocation-mode assisted` | L7_liquidity_only | funded receiving assistance |
| I_learn_pay | `--workshops --workshop-payroll --learning-cohorts` | L6_paid | learning × workshop payroll |
| ALL | every sprint-2 switch on (relocation at its default mode) plus convoys | off | all-switches cohort |

The L2 `equal` regime and feature-off identity are tested elsewhere (native tests and
`turn_speed_identity`), not as screen arms.

## Outcomes (per world, against the arm's control on the same world)

- **Activation funnels.** These are lifetime counters from the last snapshot of each package,
  and academy supply totals plus delivered teaching. For example:
  - academies founded → supplies purchased → teaching delivered → cohorts formed → sessions
    → completions → capability changes;
  - firms opened → customer firm-turns → sales → wages paid → income replaced → insolvency
    and closures;
  - eligible stands → rules adopted → paid → cap lowered → binding;
  - ruler decisions → proposals → envelopes → spent → kept or deferred → grievance
    response;
  - for L7: proposed moves → gated → applied → paid, assisted or residual → destination
    pressure.
- **Primary outcomes.**
  - D1: academy supplies purchased and teaching delivered, against off.
  - L5: completions and capability changes, learn against no_learning; the income cost of
    attendance.
  - L6: crew net income (wages paid − income replaced) for paid against unpaid_labor;
    insolvency and closures under no_customer; workshop output against D1.
  - L8: extraction and closing timber stock, enforced against cost_only (the cap's effect)
    and against T_timber; craft output in the interaction arm.
  - L9: poorer-half shortfall and granary maintenance or condition, bargained against
    fixed_shares and W_services; deferrals and grievance response.
  - L7: households moved, paid and assisted, against liquidity_only; destination pressure and
    origin relief.
- **Shared outcomes:** final total population and total treasury, reported as the mean of the
  per-world paired difference with its range over worlds.
- **Adverse outcomes, always reported:**
  - L5: income given up with no completion.
  - L6: wages written off and closures.
  - L8: production lost and grievance added with no stock gain.
  - L9: deferred promises, and the households a production-first choice leaves worse off.
  - L7: residual fares, and congestion at the destination.
  - Null activation for any package.
- **Stopping rules.** Every arm runs once per held world. Nothing is tuned after held outcomes
  are inspected. A run that raises is recorded as failed, with its error, and is not rerun
  silently. A failure in held runs is a finding, investigated and reported; a fix would need a
  new held cohort to be evaluated.
- **No significance claims.** With six worlds per stratum, results are reported as means,
  ranges and the number of worlds with the same sign.

## Results (held cohort, run 2026-11-05)

Artifacts in the repository:
- per-world metrics: `livelihoods-sprint2-screens/metrics.jsonl`, one row per arm and world;
- the generated report, including the paired table: `livelihoods-sprint2-screens/report.md`;
- source identity: `livelihoods-sprint2-screens/source.txt`.

Re-summarize with `scripts/livelihoods_screens.py report ... --sprint 2`. Raw bundles are not
committed; the fixed seeds reproduce them.

- **Run.**
  - Source `aea7972f`, native extension `70587268…`, built from the same native source.
  - 252 runs, 0 failed; 1.08 of the 2.0 core-hours.
  - Every arm ran once per held world. Nothing was tuned or rerun.
- **Units.** Six worlds per stratum: t = template 8×4, p = procedural 32×10. Results are means
  over worlds with their range and the number of worlds with each sign. These are screens, not
  significance tests.

### Findings by package

- **L1 downstream supplies (D1 against off).** Mixed by stratum.
  - Workshops raised academy supplies purchased in 5 of 6 template worlds (+22 per world,
    range −7 to +66) but lowered them in 5 of 6 procedural worlds (−16, range −146 to +98).
    Teaching delivered followed the same pattern.
  - There is no consistent downstream supply effect.
- **L5 learners.** Cohorts form, but few learners complete.
  - Per world: 5.2 cohorts (t) and 7.3 (p), and 28 and 36 learners enrolled.
  - Learners went without a seat in 98 (t) and 154 (p) learner-turns, against 17 and 15 turns
    attended. The binding constraint is delivered teaching, not supplies or learners.
  - Capability changes (learn against no_learning) occurred in 2 of 6 worlds per stratum: +1.3
    (t) and +0.5 (p) per world. Population and treasury differences are indistinguishable
    from the no-learning control.
  - Adverse: attendance cost 8.7–8.8 income per world, mostly without completion.
- **L5 × L6 (I_learn_pay against L5_learn).** Payroll-backed academy purchases raised
  completions in template worlds: +4.2 per world, 4 of 6 up (5.7 against 1.5 per world).
  Procedural worlds showed almost no change (+0.17).
- **L6 workshop payroll.**
  - Paid crews gained relative to unpaid labour in every template world (+57.8 wealth units
    per world, range +7.8 to +89.0). In procedural worlds the gain was +22.2: 4 worlds
    positive and 2 worlds with no firm.
  - Payroll lowered site-region craft output in 5 of 6 template worlds (−61 per world): unpaid
    wages cut hours, then crews, then closed firms. Procedural worlds moved the other way
    (+18; 3 up, 1 down).
  - Without a customer, firms closed insolvent in 6 of 6 template worlds (2.3 per world) and
    4 of 6 procedural worlds.
  - Adverse: even paid firms closed insolvent (2.7 per world, t) and wrote off wages
    (1.7 units per world).
- **L8 commons rules.**
  - Enforced rules cut extraction against cost_only in 5 of 6 worlds in each stratum: −16
    (t) and −91 (p) per world. Closing stock was usually higher (t 3 up / 1 down; p 4 / 2),
    as was regrowth.
  - Cover loss (about 3,050 (t) and 13,500 (p) per world) stays 10–20 times extraction, so
    harvest rules cannot protect a forest from clearing.
  - With workshops competing for timber (I_commons_work against I_timber_work), extraction
    fell in 6 of 6 template and 5 of 6 procedural worlds. Site craft output fell in 4 of 6
    template (−26) and 3 of 6 procedural worlds (−14): the predicted production cost.
  - City grievance added: 0.09 (t) and 1.7 (p) per world.
- **L9 local budgets.** Bargaining shifted the treasury from workshops to relief.
  - Site craft output fell in 12 of 12 worlds against W_services: −136 (t) and −285 (p) per
    world. In template worlds, idle site-turns rose from 2 to 88.
  - Relief reaching targeted households rose in 9 of 12 worlds (+24 (t), +35 (p) per world).
  - The poorer half's shortfall barely changed (−0.005 and −0.0004 rations per person; lower
    in 4 of 6 worlds each). This is the production-first against relief-first trade-off; the
    relief side delivers little.
  - Contested decisions were rare. Per world, the patricians' allocation won 3.8 (t) and
    8.8 (p) times and the commons' 1 and 0.3 times; most decisions were uncontested or
    empty. Grievance was raised 5 (t) and 37 (p) times and eased 20 and 67 times.
  - Fixed shares also cut workshops (11 of 12 worlds) and deferred far more: 35 against 8.5
    (t) and 124 against 46 (p), mostly `work_short`.
- **L7 relocation costs.**
  - Paying the fare (paid against liquidity_only) changed persons moved by −189 (t; 4 of 6
    lower) and −143 (p; 3 lower, 3 higher).
  - Assistance reduced households blocked short against paid in 11 of 12 worlds: −249 (t)
    and −611 (p).
  - Against liquidity_only, assistance moved fewer people in template worlds (−232, 6 of 6)
    and more in procedural worlds (+352, 4 of 6). The trajectories diverge, so this is not
    a per-household effect.
  - Arrivals were fed less than residents in every arm (mean ration 0.49–0.61 against
    0.54–0.67). Destinations became more crowded by about +0.10 and origins less by about
    −0.07 to −0.09 people per unit of capacity, per region-turn.
  - Fare residuals: about 1.4% of the fares due.
- **All switches (ALL against off).** Population +14.5 [+4, +24] (t, 6 of 6 positive) and
  +43.7 [−24, +110] (p). Treasury ranges span zero. This is one cohort, and no causal claim
  is made for the combination.
- **Uninformative outcome.** Granary storage condition ends at 0 in every arm, including off,
  because the base storage policy maintains nothing. The preregistered end-condition outcome
  therefore cannot discriminate. L9's granary works appear only in its envelope counters.
- **Shared outcomes.** Per arm, the paired population and treasury differences are listed in
  `report.md`. Most ranges span zero.

### What the screens do not show

- No package is qualified: the 200-seed and procedural gates were not run.
- L6b household purchases were left open and were not screened.
- The L5 capability changes are few. The template advantage of L5 × L6, the L7 assistance
  pattern and the D1 sign all differ by stratum. Each would need a larger cohort before any
  claim.

## Amendments

**2026-11-05, before any held run (independent review of the integrated source).**
No arm, control, cohort, budget or primary outcome changed. Outcome extraction and the
source changed:

- The runner looked for L7 under `relocation`; its snapshot key is `relocation_costs`, so
  L7's funnel would have been silently dropped. Corrected, with a test that every counted
  package is a livelihoods switch.
- Added extraction for outcomes this file already named:
  - L7 receiving pressure, each source turn once: destination and origin region-turns and
    their crowding change;
  - arrivals' against residents' rations;
  - L9 granary storage at the end (assets, capacity, mean condition);
  - L6 crew net income in consistent units (wages are milli-units, replaced income is in
    wealth units).
- Source fixes after the review, each with a regression test that fails on the previous
  code:
  - L6a wages are shared only among living workers; dead workers' claims lapse first.
  - L9 reserves L7 assisted-relocation assistance as an obligation inside the one budget.
  - L9 names a workshop deferral `recipient_lost` only when the site closed.
  - L8 now reads Commons Management's last settled funding ratio, found earlier the same
    day.
- The held runs use the source with these fixes; its commit and extension are recorded with
  the results.
