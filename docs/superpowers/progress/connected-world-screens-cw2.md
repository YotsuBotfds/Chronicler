# Connected-world CW2: preregistered held screen for workshop economics and the owned-output rule (slices A3-1, A3-2)

Status: DRAFT, pre-freeze revision 1 (not frozen; the lead freezes it before any held run; see
"Pre-freeze revision 1" at the end). Written 2026-11-07 by the A4 lane on branch
`claude/cw-a4-titled-trade` at `21aa48cb`, revised at `a1b61760` (A3-1 merged in PR #88; A3-2, rules 2,
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

`run PILOT --screen CW2 --cohort pilot --jobs 2` on `a1b61760` (revision 1; clean tree;
`source.txt`: dirty 0, dirty-code 0; extension `43cbd22a…`): 10 runs, 0 failed, every outcome
extracted; 307 s of simulation and extraction **on a loaded machine** (load average about 7 on 4
cores from other lanes). Seconds per run (template, procedural): P 7.5, 58.5; E1 15.8, 61.4; E2
11.7, 50.6; E2f 12.2, 49.1; E2a 10.2, 30.4. E1, E2, E2f and E2a activated on both worlds.
**Projected held run: 0.512 core-hours for 60 runs** (x1.5 = 0.768). The earlier pilot on
`21aa48cb`, on a quieter machine, ran the same arms in 139 s and projected 0.232 core-hours. The
revision-1 pilot's `metrics.jsonl`, `source.txt` and `report.md` are retained in
`connected-world-screens-cw2/pilot/` (the held run's `--pilot`). The report prints the pilot's
outcomes; they were not used to choose any definition.

## Budget and stopping rules

- **Compute ceiling 1.05 core-hours** (the line above, read by the runner: the loaded
  revision-1 pilot's projection 0.512 x 2.05, so that the retained pilot passes the runner's x1.5
  check; 0.50 before revision 1, from the quieter pilot's 0.232). A pilot re-run on a quieter
  machine before the freeze may replace it, with the ceiling set again at about twice its
  projection. Run with
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
