# Connected-world CW2: preregistered held screen for workshop economics and the owned-output rule (slices A3-1, A3-2)

Status: FROZEN. Frozen by the lead on 2026-11-07 after independent review of the design, extractors and revisions (review record in the program's review notes); code at `60edc6c9`; pilot at `60edc6c9`. No code change after this point except a defect fix recorded as an amendment with a new pilot.

Written 2026-11-07 by the A4 lane on branch
`claude/cw-a4-titled-trade` at `21aa48cb`, revised at `a1b61760` and `60edc6c9` (A3-1 merged in PR #88; A3-2, rules 2,
on this branch with its review fixes approved at `d5ccd4d6`, merged with `main` `bac45cb5`).
Native extension built from this branch, SHA-256
`43cbd22ac4e7e2c6a77e71781a884be5342f41aa4173ff6f43e0facf0f5e0eb0` (it honours the
`workshop_owned_crafts` column, which rules 2 requires at startup). No held seed (template
741-746, procedural 841-846) has been run; the registry still lists both as `reserved`. Code may
change before the held run only to fix a defect, recorded as an amendment with a new pilot; no
arm, outcome or parameter changes in response to held outcomes.

Compute ceiling: 1.05 core-hours

Primary outcomes: cw2_active_share, cw2_wages, cw2_wares_sold

## Purpose and limits

Workshop economics (`--workshop-economics`, [docs/integration/workshop-economics.md](../../integration/workshop-economics.md))
makes a workshop firm buy its raw inputs from the owner of the commons and sell its wares to
households as well as to academies (A3-1). Rules version 2 (A3-2) keeps the firm's output out of
the commons, so it reaches anyone only by sale, and counts the firm's own stock in the wares
supply that sets the price. CW2 asks: **do firms under these rules operate, pay households and
serve real (non-academy) demand, and at what cost to food, arrears, unsold stock, farm time,
treasuries and population?** It also reports the input cost (free inputs) and a demand collapse
(no household customers).

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip enumeration
  (64 assignments per stratum), not significance tests.
- Hybrid worlds; template 8 regions x 4 civilizations and procedural 32 x 10; 200 turns.
- Trajectories diverge once firms act, so every measure is a property of the whole trajectory.
- **Known model properties the results inherit** (workshop-economics.md): rules 2 bundles a price
  rule (the firm's stock counts in the supply that sets its price), which the development worlds
  showed lowers what households pay per load; under the L6a status quo firms open only around an
  academy order, so a world without one has no firm in P (the pilot's procedural world 19); firm
  inventory is outside A5's owned-stock rules except that liquidation hands the unsold stock to the
  commons' owner (recorded under rules 2); asset upkeep is the owner's subsidy.
- **The owned-stock lifecycle where it bears on firms** (A5 is not merged): measured through
  closures by reason (idle, insolvent, the city falling, the city missing, the region changing),
  wares handed to the owner at liquidation, unsold inventory at the end and the inputs bought.

## Units, cohorts and source

- Unit: one world (seed); each arm runs the same world. Template held 741-746, procedural held
  841-846 (the registry's CW2 reservations, checked unused by `check --screen CW2`); the shared
  timing pilot template 5 and procedural 19 (never held).
- Turns: 200; snapshot s records world turn s - 1.
- Base (every arm; the A3 audit's base): `--turns 200 --agents hybrid --simulate-only
  --grain-reserves --public-grain-shipments --scholarship --techniques --academy-services
  --workshops --workshop-payroll --wealth-accounting`, with the runner's `--worldgen procedural
  --regions 32 --civs 10` on the procedural stratum.
- Arms (root P; controls form the chain E2f, E2a -> E2 -> E1 -> P):

| Arm | Flags | Control |
| --- | --- | --- |
| P | the base: the L6a payroll status quo (no workshop economics) | (root) |
| E1 | P + `--workshop-economics` (rules 1, mode `market`: A3-1) | P |
| E2 | P + `--workshop-economics --workshop-economics-rules 2` (A3-2) | E1 |
| E2f | E2 + `--workshop-economics-mode free_inputs` (a **diagnostic cost control only; free inputs are not a supported feature**: every rule as E2, inputs recorded and not charged) | E2 |
| E2a | E2 + `--workshop-economics-mode academy_only` (the demand collapse: no household customers; academies only) | E2 |

  The demand collapse is arranged by an existing mode, not fabricated: households cannot buy
  firm wares, so firms sell only to academies. The audit's `no_customer` payroll arm (wages owed,
  nothing sold) is not used: it is a constructed collapse with no sale at all.

- Source: the runner, the screen module `scripts/connected_world_screens.py` (CW2's arms,
  packages, activation, extractor and outcomes) and the seed registry, by SHA-256 in each run's
  `source.txt`. Packages the runner checks in every snapshot: workshop payroll (mode `paid`),
  workshop economics (declared counters and mode, only in the E arms) and the A1 ledger.

## Activation (reported per world before any effect)

`cw2_activation(bundle, flags)`; the root P is not judged.

- **E1, E2**: at least one firm opened, an input was charged and households bought wares.
- **E2f** (free inputs): a firm opened, inputs were used and households bought wares.
- **E2a** (academy only): a firm opened and an input was charged (no household may buy).

The evidence names firms opened, operating firm-turns, inputs used and charged and the loads
households bought. A world where an arm did not act is `not activated` and left out of that arm's
comparisons, never read as zero.

## Definitions (`cw2_extract`)

Firms are identified by (site, opening turn) from every snapshot's payroll records (open and
closed firms). A firm's receipt exists in every turn from its opening to its closing turn.

- **Firm-turn states since opening**: the horizon is, over every firm ever opened, the turns from
  its opening to the end of the run (closed turns included). A receipt turn is **active** when the
  firm produced (`operating`) or sold (to an academy, `sold`, or to households, `household_sold`;
  payroll adds these keys only when nonzero); open and neither is **idle**; a turn after closing
  is **closed**. `active_share = active firm-turns / horizon` (undefined, `None`, on a world where
  no firm opened); the producing, selling, idle and closed shares likewise; `active_firm_turns` is
  the count (defined everywhere).
- **Closures by reason**: payroll's `FIRM_CLOSE_REASONS` (insolvent, city_fell, city_missing,
  region_changed, idle).
- **Workshop wages credited to households** (`wages_credited`, units): the A1 ledger's lifetime
  `workshop_wage_in_milli` (a recorded zero where no firm opened), checked equal to payroll's
  `wages_paid`; `household_net_income` subtracts the model income the wages replaced (the ledger's
  `withheld_workshop_payroll`).
- **Wares delivered to households by sale** (`household_delivered`, loads; E arms): workshop
  economics' `household_delivered`, checked equal to the payroll receipts' `household_sold` sum;
  what households paid and the price per load; `None` in P (L6a has no household customers; a
  household sale in P is a problem).
- **Inputs** (E arms): used and charged (bought from the commons' owner); unpaid conversions.
- **Unsold stock and arrears**: firm inventory at the end; wares handed to the owner at
  liquidation (rules 2) and returned at closure; wages due but not paid (payroll); workshop asset
  arrears at the end (the workshops' receipts).
- **Farm time diverted** to crews: the workshops' `work_realized` (work units; crews are adult
  farmers).
- Stability: the mean stability of living civilizations at the end.

**Validity checks (a breach is a problem that fails the run, rc 3, never a value):** no input
converted unpaid in mode `market`; no input charged with `free_inputs`; no household sale in
`academy_only` or without workshop economics; under rules 2 no free use, every operating firm
titles its whole output and every record is rules 2; the ledger's wages equal payroll's and the
economics deliveries equal payroll's; every A1 ledger closure true on every observed frame;
records dated s - 1 and present exactly in their arms (the runner's package checks). Rules 2 also
raises during the run unless the native economy reported its owned outflow (reconciled every
turn).

## Primary outcomes

1. `cw2_active_share` (E2 - E1): the share of firm-turns since opening that were active
   (produced or sold), idle and closed turns counting against it: whether firms under the
   owned-output rule keep operating compared with A3-1. P is not its control because the share is
   undefined where L6a opens no firm (found in extractor validation on the pilot; the E2 - P
   share and the E2 - P active firm-turn count are secondaries).
2. `cw2_wages` (E2 - P): workshop wages credited to households over the run: the money the A3
   package as it now stands pays households compared with the status quo.
3. `cw2_wares_sold` (E2 - E1; `cw2_served` before revision 1): wares sold to households over the
   run. It counts sales only: in E1 the people also draw part of the firm's output free from the
   commons before title, so E2 - E1 is partly mechanical; E1's free-use upper bound is reported
   beside it (`cw2_free_use_e1`).

Signs are not forced. Prediction (inferred from the development comparison in
workshop-economics.md, never evidence): under rules 2 households buy slightly fewer loads for
much less money, firms operate fewer turns and close idle more often.

## Secondary outcomes

- A3-1 against the status quo (E1 - P) and the E2 - P counterparts: active share (where defined),
  active firm-turns, wages, firms opened, net household income, academy sales.
- A3-2 against A3-1 (E2 - E1): wages, households' money paid and price per load, firms opened,
  firms closed idle.
- The input cost (E2f - E2): active share, firms opened, closed idle, wares sold, wages,
  treasury. **E2f is a decomposition arm: its results are never read as an option** (free inputs
  are not a supported feature; the mode exists as the lead-approved A3-1 cost control).
- E1's free-use upper bound (E1 alone): firm output the people could draw free from the commons
  before title (none in E2).
- The demand collapse (E2a - E2): active share, closed idle, wages, unsold inventory at the end,
  wares handed to the owner at liquidation.
- E2 alone: the producing, selling, idle and closed shares; closures idle, insolvent and by city
  fall; liquidation to the owner; inputs bought; owned output titled.

## Harm panel

The runner's fixed panel beside every arm against its control (E1 - P, E2 - E1, E2f - E2,
E2a - E2): population and treasury at the end, food shortfall after relief over the run, epidemic
deaths, agents migrating between regions, the wealth Gini at the end; priced-out persons and
children and the timber stand read `not recorded` (household retail and the timber stock are
off); deaths by famine and by war need slice extractors. The screen adds the CW2 panel as E2 - P
rows: food shortfall, wages due but not paid, asset arrears at the end, unsold inventory at the
end, farm time diverted, treasury, mean stability at the end and population; inputs bought from
the commons' owner (never free in E2) is an E2 row; household-turns priced out of firm wares
(the economics counter `priced_out_households`, revision 1) is an E2 - E1 and an E2 row (P has no
household customers, so nothing is recorded there).

## Analysis plan

`report` prints activation per world first, then each outcome per stratum: per-world values,
mean [min, max], sign counts and, for a contrast, the exact sign-flip enumeration over the
activated worlds (2^k per stratum). Strata are reported separately. **Reading rule (pre-freeze
clarification, the same as CW5's):** a primary is read as consistent in a stratum when its sign
agrees on at least 5 of the stratum's 6 worlds, a world where the measure is undefined (no firm
in either arm), not activated or failed counting as not agreeing, and the exact sign-flip share
over the 2^k assignments of its k valid worlds is at most 4/64 (0.0625); otherwise as no consistent
effect. So with k <= 4 valid worlds no result can read as consistent, and with k = 5 the smallest
possible share, 2/32, equals the threshold (all five valid worlds must agree). A world where a
measure is undefined is shown as such. Secondaries and harms are descriptive.

## Extractor validation (the shared pilot, before the freeze)

Revision 1 (source `a1b61760`): the offline tests cover the renamed primary, E1's free-use upper
bound and the priced-out households (and their absence in P). On the ten revision-1 pilot bundles
every outcome extracted with no problem, and an independent recomputation from kept bundles (P,
E1 and E2 on template 5; E1, E2 and E2a on procedural 19; E1 and E2a on template 5 for the new
measures), not importing the screen module, matched the extractor on the active share, the wages
(payroll receipts equal to the ledger channel), the wares sold (economics receipts), E1's
free-use upper bound (1.344 and 16.156 loads, summed from the economics receipts; 0 in E2) and the
priced-out households. The raw runs were then deleted. `check --screen CW2 --metrics PILOT/metrics.jsonl
--cohort pilot` passes (10 runs complete, every outcome extracted).

Before revision 1:

- Offline tests `tests/test_cw2_screen.py` (oracle chunk `connected-world-e`): the arms and
  primaries; firm-turn states (closed turns counted against the firm), closures, wages, net
  income, arrears and farm time on a constructed bundle; the status quo without household
  customers; absent sale keys read as none and a receipt without `operating` a problem; every
  validity check; activation by mode.
- The first pilot (source `14012038`) failed extraction on every E run: payroll adds `sold` and
  `household_sold` only when nonzero, and the extractor required them. Fixed at `21aa48cb`
  (absent reads as none); on the ten pilot bundles every outcome then extracted with no problem,
  and the payroll, economics and ledger totals agreed. P opened no firm on procedural 19, so the
  active share was undefined there: primary 1's control moved from P to E1 in the same commit,
  before the retained pilot (a measurability fix, not chosen on outcomes).
- An independent recomputation from six kept bundles (P, E1, E2 and E2a on template 5; E2 and
  E2f on procedural 19), not importing the screen module, matched the extractor: the active share
  (from firm lists and receipts), the wages (summed from payroll receipts, equal to the ledger
  channel) and the wares served (summed from the economics receipts). The raw runs were then
  deleted.
- `check --screen CW2` passes; `check --screen CW2 --metrics PILOT/metrics.jsonl --cohort pilot`
  passes (10 runs complete, every outcome extracted).

## Timing pilot (the shared pilot)

`run PILOT --screen CW2 --cohort pilot --jobs 2` on `60edc6c9` (the code frozen below; clean tree;
`source.txt`: dirty 0, dirty-code 0; extension `43cbd22a…`; runner `deb4eb57…`, screens
`5abac387…`): 10 runs, 0 failed, every outcome extracted; 136 s of simulation and extraction.
Seconds per run (template, procedural): P 6.5, 18.3; E1 7.3, 20.8; E2 7.0, 20.9; E2f 7.4, 21.6;
E2a 7.2, 18.7. E1, E2, E2f and E2a activated on both worlds. **Projected held run: 0.226
core-hours for 60 runs** (x1.5 = 0.339). `check --metrics ... --cohort pilot` passes and the
runner's `load_pilot` accepts the pilot for this code. The revision-1 pilot (`a1b61760`) ran under
a load average of about 7 and projected 0.512. The pilot's `metrics.jsonl`, `source.txt` and
`report.md` are retained in `connected-world-screens-cw2/pilot/` (the held run's `--pilot`). The
report prints the pilot's outcomes; they were not used to choose any definition.

## Budget and stopping rules

- **Compute ceiling 1.05 core-hours** (the line above, read by the runner; the documented basis,
  accepted by the lead, is kept: about twice the 0.512 core-hours the same runs projected under a
  load average of about 7, since held runs see similar shared load; the frozen pilot projects
  0.226, whose x1.5 = 0.339 passes the runner's check; 0.50 before revision 1). Run with
  `--jobs 2`. The runner refuses a held run whose pilot projection x 1.5 exceeds the ceiling and
  starts no run that would pass it; runs not started are reported as `not run` (exit code 4).
  Raising the ceiling needs the lead's amendment before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction.
- A failed run is reported as failed with its reason and is not replaced by another seed; a held
  run that needs new worlds uses the program reserve through the lead (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `held-run.json` under
  `connected-world-screens-cw2/`), `check --metrics`, and `mark-run`, committed with the results.

## Program E: one reproducible firm

Development world template 1 (a registered development world, never held), source `21aa48cb` or
later, extension `43cbd22a…` (or any build that honours the owned column):

```
python -m chronicler.main --seed 1 --turns 200 --agents hybrid --simulate-only --grain-reserves \
  --public-grain-shipments --scholarship --techniques --academy-services --workshops \
  --workshop-payroll --workshop-economics --workshop-economics-rules 2 --wealth-accounting \
  --output OUT/chronicle.md --state OUT/state.json
```

**Firm at site 0, Crystalfen Marsh (region 7):** opened in world turn 34 with 20 units of capital
from civilization 1 (plan price 0.173 per load). From turn 35 it bought raw inputs from the
commons' owner (0.208 units that turn), produced 1.2 loads, sold 0.25 loads to the region's
households for 0.073 and paid its crew 0.3 in wages. Over its life it operated 30 of 57 turns,
paid 6.319 units for inputs, titled 15.959 loads (none free-used), sold 14.35 loads to households
for 2.299, paid 4.9 in wages, distributed 11.0 to its owner's treasury and lost 1.609 loads to
wear; it closed in world turn 91 when its city fell (`closed_city_fell`).

## Pre-freeze revision 1 (2026-11-07, before any held run; the lead's decisions after the delta review)

The delta review approved the code at `347621e7` (its independent spot-check on development
template 1 matched the extractor for P, E1 and E2) and asked for changes before the freeze. Made at
`a1b61760`:

1. **The third primary is renamed** `cw2_wares_sold`, "wares sold to households" (was
   `cw2_served`): it counts sales only, and in E1 the people also draw part of the output free
   from the commons, so E2 - E1 is partly mechanical. **E1's free-use upper bound** is added as a
   secondary (`cw2_free_use_e1`; no record exposes the wares the people actually consumed free).
2. **Harm panel:** the economics counter `priced_out_households` (E2 - E1 and E2).
3. **E2f is labelled a diagnostic cost control only; free inputs are not a supported feature**
   (the CLI help of `--workshop-economics-mode` and the mode table in
   docs/integration/workshop-economics.md say so). E2f is a decomposition arm, and its results
   are never read as an option.
4. **Ceiling** 1.05 core-hours from the revision-1 pilot, which ran under load (above).

## Results (held run, 2026-11-07)

Template 741-746 and procedural 841-846, 200 turns, five arms, `run HELD --screen CW2 --cohort
held --pilot connected-world-screens-cw2/pilot/metrics.jsonl --jobs 2` on `8ae4efa4` (the frozen
code: the freeze commit `fa564161` plus CW5's held evidence and registry record, no code path;
clean tree). `mark-run` recorded both cohorts as `run` (complete). Retained in
`connected-world-screens-cw2/held/`: `metrics.jsonl`, `source.txt`, `held-run.json`, `report.md`
(every per-world cell, the sign-flip ranges and the full harm panel), `check.txt`. The runner
deleted each raw run directory after its extraction (nothing else was pruned).

**Identity.** Source `8ae4efa4365b97c3f1d2238f42040a1e0ed82765`, dirty 0, dirty-code 0; native
extension SHA-256 `43cbd22ac4e7e2c6a77e71781a884be5342f41aa4173ff6f43e0facf0f5e0eb0`; runner
`deb4eb57…`, screen module `5abac387…`, registry `f5b52a29…` (CW5's run record) and content
`a703a850…`, preregistration `436aed62…`; run identity digest `9798cd88…`. The pilot's identity
matches (its source `60edc6c9` differs only outside the code).

**Runs and failures.** 60 runs, 0 failed, missing outcomes 0; every validity check held in every
run (no input converted unpaid in `market`, no input charged with free inputs, no household sale in
`academy_only` or in P, no free use and whole titles under rules 2, ledger wages equal to payroll's
and economics deliveries equal to payroll's, every A1 ledger closure true). `check --metrics ...
--cohort held` passes (60 runs complete, every outcome extracted).

**Compute.** 951 s of simulation and extraction, **0.264 core-hours, under the 1.05 ceiling** (no
run stopped by it); 478 s wall. Seconds per run, mean (template, procedural): P 7.8, 22.8; E1 8.8,
24.9; E2 8.4, 23.4; E2f 8.5, 23.7; E2a 7.9, 22.2.

### Activation (before any effect)

E1, E2, E2f and E2a each activated on 12 of 12 worlds (6 of 6 per stratum). P is the root. The
active share is defined in E1 and E2 on every world (k = 6 for the first primary); P opened no
firm on procedural 841 and 846, so E2 - P and E1 - P shares are undefined there (secondaries).

### Primary outcomes

| Outcome | Stratum | Per world | Mean [min, max] | > 0 / < 0 | Sign-flip (of 64) | Reading (frozen rule) |
| --- | --- | --- | --- | --- | --- | --- |
| `cw2_active_share` (E2 - E1) | t | 741 +0.0296; 742 −0.0359; 743 +0.0382; 744 −0.4952; 745 +0.0850; 746 −0.0577 | −0.0727 [−0.4952, +0.0850] | 3 / 3 | 44 | no consistent effect |
| | p | 841 −0.0692; 842 +0.0859; 843 −0.1079; 844 −0.1350; 845 +0.0414; 846 −0.2780 | −0.0772 [−0.2780, +0.0859] | 2 / 4 | 14 | no consistent effect |
| `cw2_wages` (E2 - P), units | t | 741 +8.40; 742 −41.38; 743 −11.60; 744 +6.60; 745 +1.53; 746 +17.90 | −3.09 [−41.38, +17.90] | 4 / 2 | 52 | no consistent effect |
| | p | 841 +37.95; 842 −2.10; 843 −18.30; 844 +49.02; 845 +46.85; 846 +30.10 | +23.92 [−18.30, +49.02] | 4 / 2 | 8 | no consistent effect |
| `cw2_wares_sold` (E2 - E1), loads | t | 741 −8.26; 742 −29.95; 743 +1.38; 744 −78.11; 745 +15.21; 746 −6.17 | −17.65 [−78.11, +15.21] | 2 / 4 | 20 | no consistent effect |
| | p | 841 −8.08; 842 +27.21; 843 −19.10; 844 −77.20; 845 +7.86; 846 −30.39 | −16.62 [−77.20, +27.21] | 2 / 4 | 22 | no consistent effect |

Sign-flip: the share of the 2^k sign assignments whose mean is at least as far from zero as the
observed mean (descriptive, not a significance test). Beside `cw2_wares_sold`: E1's free-use upper
bound (firm output the people could draw free before title) was 4.96 [1.63, 13.65] loads
(template) and 13.66 [3.84, 35.62] (procedural), none in E2.

### Harms beside the primaries (E2 - P unless stated; mean [min, max], > 0 / < 0, sign-flip of 64)

| Harm | Template | Procedural |
| --- | --- | --- |
| Food shortfall after relief, world | −258.9 [−1105, +467.5], 2/4, 22 | −393.2 [−2131, +1100], 2/4, 32 |
| Wages due but not paid, units | −2.12 [−6.48, +0.60], 1/5, 6 | −1.11 [−3.55, +0.70], 3/3, 16 |
| Workshop asset arrears at the end | 0 on all 6 | −2.5 [−15, 0], 0/1 (5 zero) |
| Unsold firm inventory at the end, loads | +1.18 [−1.01, +8.11], 1/1 (4 zero) | +4.05 [0, +12.55], 2/0 (4 zero) |
| Farm time diverted to crews, work units | −67.0 [−185.5, −8.9], 0/6, 2 | −106.0 [−192.0, −27.9], 0/6, 2 |
| Treasury at the end | +162.7 [−898, +2414], 1/5, 64 | −251.8 [−2621, +1171], 3/3, 46 |
| Mean stability at the end | −4.42 [−19.5, +11.0], 3/3, 32 | +1.92 [−9.19, +7.20], 4/2, 34 |
| Population at the end | −27.3 [−52, −1], 0/6, 2 | −104.0 [−225, +35], 1/5, 6 |
| Epidemic deaths | +35.2 [−27, +74], 5/1, 8 | +49.2 [−105, +266], 4/2, 26 |
| Agents migrating between regions | −200.0 [−649, +296], 2/4, 20 | −676.5 [−1539, +219], 1/5, 6 |
| Wealth Gini at the end | −0.051 [−0.251, +0.204], 2/4, 24 | +0.012 [−0.134, +0.226], 3/3, 54 |
| Households priced out of firm wares (E2 - E1, and E2) | 0 on all 6 | 0 on all 6 |
| Inputs bought from the commons' owner (E2), units | 58.9 [18.6, 181.7] | 138.9 [32.0, 252.2] |

Nulls as nulls: priced-out persons and children and the timber stand are `not recorded` (household
retail and the timber stock are off); deaths by famine and by war `require a slice extractor`. The
runner's panel for every arm against its declared control (E1 - P, E2 - E1, E2f - E2, E2a - E2) is
in `held/report.md`.

### Secondary outcomes (mean [min, max], > 0 / < 0 (= 0), sign-flip)

| Outcome | Template | Procedural |
| --- | --- | --- |
| Active share, E2 - P (worlds where P opened a firm) | −0.053 [−0.555, +0.388], 2/4, 46/64 | −0.073 [−0.153, +0.032], 1/3, 6/16 (841, 846 undefined) |
| Active firm-turns, E2 - P | +58.2 [−94, +168], 4/2, 16/64 | +265.2 [+110, +333], 6/0, 2/64 |
| Active share, E1 - P | +0.019 [−0.258, +0.445], 2/4, 56/64 | −0.044 [−0.194, +0.167], 1/3, 10/16 (841, 846 undefined) |
| Wages credited, E1 - P | +9.90 [−25.57, +40.90], 4/2, 24/64 | +37.37 [−12.80, +77.62], 5/1, 4/64 |
| Wages credited, E2 - E1 | −12.99 [−34.30, +8.10], 1/5, 6/64 | −13.45 [−50.35, +20.70], 2/4, 18/64 |
| Households' money paid for wares, E2 - E1 | −21.2 [−70.0, +5.4], 1/5, 4/64 | −35.4 [−84.5, +6.3], 1/5, 4/64 |
| Price per load, E2 - E1 | −0.181 [−0.444, +0.378], 1/5, 14/64 | −0.296 [−0.397, −0.151], 0/6, 2/64 |
| Firms opened, E2 - E1 | −0.17 [−2, +1], 1/1 (4), 64/64 | −1.33 [−6, +2], 1/3 (2), 32/64 |
| Firms closed idle, E2 - E1 | +0.33 [−2, +3], 3/2 (1), 52/64 | −0.17 [−6, +2], 4/2, 64/64 |
| Net household income from firm work, E2 - P | −2.68 [−34.98, +12.92], 3/3, 52/64 | +18.80 [−22.33, +38.47], 5/1, 6/64 |
| Wares sold to academies, E2 - P, loads | −35.4 [−145.9, +4.5], 1/4 (1), 8/64 | −10.9 [−79.4, +19.1], 2/3 (1), 44/64 |
| Firms opened, E2 - P | +0.67 [−3, +3], 3/1 (2), 40/64 | +9.33 [+7, +11], 6/0, 2/64 |
| **Input cost (diagnostic; never read as an option)**: active share, E2f - E2 | +0.219 [−0.081, +0.492], 5/1, 6/64 | +0.243 [+0.057, +0.399], 6/0, 2/64 |
| Firms opened, E2f - E2 | +0.5 [−1, +2], 3/2 (1), 36/64 | −1 [−3, +2], 1/4 (1), 20/64 |
| Firms closed idle, E2f - E2 | −0.17 [−1, +2], 1/3 (2), 64/64 | −3.17 [−7, +2], 1/5, 6/64 |
| Wares sold to households, E2f - E2 | +44.6 [−4.3, +144.6], 5/1, 6/64 | +50.0 [+18.3, +84.7], 6/0, 2/64 |
| Wages credited, E2f - E2 | +31.2 [+1.7, +69.6], 6/0, 2/64 | +37.3 [+21.5, +64.0], 6/0, 2/64 |
| Treasury at the end, E2f - E2 | +153.8 [−982, +1844], 3/3, 46/64 | −362.7 [−3091, +2397], 2/4, 42/64 |
| **Demand collapse**: active share, E2a - E2 | −0.232 [−0.381, −0.022], 0/6, 2/64 | −0.180 [−0.236, −0.087], 0/6, 2/64 |
| Firms closed idle, E2a - E2 | +0.83 [0, +2], 4/0 (2), 8/64 | +3 [+1, +5], 6/0, 2/64 |
| Wages credited, E2a - E2 | −5.08 [−8.90, +0.70], 1/5, 4/64 | −13.08 [−51.15, +7.15], 1/5, 8/64 |
| Unsold inventory at the end, E2a - E2 | −2.00 [−11.97, 0], 0/1 (5), 64/64 | −1.97 [−11.95, +9.16], 1/2 (3), 48/64 |
| Wares handed to the owner at liquidation, E2a - E2 | +28.9 [+2.0, +48.4], 6/0, 2/64 | +71.6 [+44.5, +110.6], 6/0, 2/64 |

E2 alone (template; procedural): producing share 0.179 [0.100, 0.267]; 0.177 [0.132, 0.232];
selling share 0.286 [0.094, 0.414]; 0.247 [0.128, 0.345]; idle share 0.059; 0.059; closed share
0.642 [0.493, 0.834]; 0.671 [0.595, 0.783]; firms closed idle 3.3 [1, 4]; 9.5 [4, 13]; closed
insolvent 0; 0; closed when the city fell 0; 1.3 [0, 3]; wares handed to the owner at liquidation
0; 5.8 [0, 18.7] loads; owned output titled whole 63.2 [46.6, 109.9]; 133.9 [79.2, 205.4] loads.

Under the frozen rule none of the three primaries reads as consistent in either stratum.

Label note: `held/report.md` labels `cw2_cost_active` "(E2 - E2f: the input cost)", but the
outcome reads arm E2f against control E2, so its values (+0.2187 template, +0.2425 procedural) are
E2f - E2, as the secondary table above gives them. The label is in the frozen screen module and
stays as it is.

### Corrections after the independent check (2026-11-07)

Results text only; the frozen parts of this page, the code and the retained evidence are
unchanged. Added the label note on `cw2_cost_active` (the report's "(E2 - E2f)" label; the values
are E2f - E2).
