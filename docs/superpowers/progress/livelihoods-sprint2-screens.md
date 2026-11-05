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

## Amendments

None yet.
