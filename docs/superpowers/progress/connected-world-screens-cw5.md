# Connected-world CW5: preregistered held screen for titled trade (slice A4-1)

Status: DRAFT (not frozen; the lead freezes it before any held run). Written 2026-11-07 by the A4
lane on branch `claude/cw-a4-titled-trade` at `21aa48cb` (the A4 review fixes approved at
`d5ccd4d6`, merged with `main` `bac45cb5`, plus the lead's carrier rule at `9591e280`: carriers
take no native decision while reserved). Native extension built from this branch, SHA-256
`43cbd22ac4e7e2c6a77e71781a884be5342f41aa4173ff6f43e0facf0f5e0eb0`. No held seed (template
771-776, procedural 871-876) has been run; the registry still lists both as `reserved`. Code may
change before the held run only to fix a defect, recorded as an amendment with a new pilot; no
arm, outcome, set or parameter changes in response to held outcomes.

Compute ceiling: 0.25 core-hours

Primary outcomes: cw5_food_in_deficit, cw5_shortfall_deficit, cw5_margin_vs_withheld

## Purpose and limits

Under household retail everywhere (`--household-retail-boundary all`) owned food never loads on
native merchant trips, so almost no food moves between regions (the A4 audit measured 0 food
delivered in 200 turns on a development world). Titled trade (`--titled-trade`,
[docs/integration/titled-trade.md](../../integration/titled-trade.md)) lets a merchant buy owners'
surplus food by stable id, carry it under title and sell it as its own retail claim, while the
model income it would have earned is withheld. CW5 asks: **does titled trade move food into the
regions short of it and lower their shortfall, without harming the exporters, and do the
merchants' margins replace the withheld model income rather than stack on it?**

- A bounded screen on default-off experimental source, not qualification. The 200-seed and
  procedural qualification gates stay unrun; nothing is promoted or tuned on these worlds.
- Six worlds per stratum support means, ranges, sign counts and the exact sign-flip enumeration
  (64 assignments per stratum), not significance tests.
- Hybrid worlds; template 8 regions x 4 civilizations and procedural 32 x 10; 200 turns.
- Trajectories diverge once titled trade acts (prices, migration, deaths), so every measure is a
  property of the whole trajectory, not a mechanism estimate.
- **Known model properties the results inherit** (titled-trade.md, "Declared limits"): prices
  within three hops are known at once; war does not reach cargo in transit (counted); carriers
  stay home in the native pool; food only; trips to or from non-pilot regions stay native (none
  here: every region is a pilot). Carriers take no native decision while reserved (the lead's
  decision after the review), so on development worlds no carrier was released.
- **Not built, so not an arm:** the stacking-check control (titled trade with the carriers' model
  income kept) would need a new simulation mode; the receipts already show the income is withheld
  row by row (one receipt row per carrier-turn, share 1.0, a validity check below), and the third
  primary measures the margin against it. A `record_only` titled-trade mode does not exist in
  A4-1 either. Either can be added only by amendment before the freeze.

## Units, cohorts and source

- Unit: one world (seed); each arm runs the same world. Template held 771-776, procedural held
  871-876 (the registry's CW5 reservations, checked unused by `check --screen CW5`); the shared
  timing pilot template 5 and procedural 19 (never held).
- Turns: 200; snapshot s records world turn s - 1 (`source_turn = s - 1` in every record).
- Base (every arm): `--turns 200 --agents hybrid --simulate-only --grain-reserves
  --public-grain-shipments --food-allocation --household-retail --household-retail-boundary all
  --wealth-accounting` (retail mode `retail`, rules version 2, the defaults), with the runner's
  `--worldgen procedural --regions 32 --civs 10` on the procedural stratum.
- Arms (root R):

| Arm | Flags | Control |
| --- | --- | --- |
| R | the base: retail everywhere, no titled trade | (root) |
| T | R + `--titled-trade` | R |

- Source: the runner `scripts/screen_runner.py`, the screen module
  `scripts/connected_world_screens.py` (CW5's arms, packages, sets, activation, extractor and
  outcomes), the seed registry, all identified by SHA-256 in each run's `source.txt`. Packages the
  runner checks in every snapshot: household retail (mode `retail`), titled trade (declared
  counters, only in T) and the A1 ledger.

## Region sets (fixed before treatment, identical in both arms)

From the food account of world turn 0 (snapshot 1), which titled trade cannot reach (its first
purchase is in Phase 10 of a turn, after that turn's economy; the arms are identical until then):

- **Deficit regions**: regions with demand at turn 0 whose native food production that turn was
  below their demand (`food_accounting.regions[i].native.produced < demand`, demand > 0).
- **Surplus regions**: regions with demand at turn 0 that produced at least their demand.
- Regions without demand at turn 0 (unpopulated then) are in neither set.

The extractor records the sets (`sets_digest`); on both pilot worlds they were identical in R
and T (template 5: 4 deficit, 2 surplus of 8; procedural 19: 7 deficit, 8 surplus of 32).
Turn 0 is the only turn guaranteed to precede any titled shipment; a region's status can change
later (a deficit region at turn 0 may export later), which every measure inherits.

## Activation (reported per world before any effect)

`cw5_activation(bundle, flags)`; the root R is not judged. **T acted** when at least one titled
shipment was delivered. The evidence names the shipments by outcome (delivered, returned for a
lost route or a conquered destination, returned after a carrier's release, escheated at the
holder's death) and the **region-turns with any titled shipment** (a region where a shipment was
bought, stood, moved or closed that turn) out of all region-turns. A world where T did not act is
reported as `not activated` and left out of T's comparisons, never read as zero.

## Definitions (`cw5_extract`)

- **Food into a set by trade** (`food_in_deficit`, `food_in_surplus`; food units over the run):
  titled net + native commons trade. Titled net, from every snapshot's titled-trade frame: food
  arriving in the set's regions at each closing event (delivered, returned or deposited there)
  less food bought in the set's regions at dispatch (losses in transit arrive nowhere; cargo
  aboard at turn 199 has left its origin). Native commons trade: the food account's
  `native.transport_net` summed over the set's regions and snapshots (under retail everywhere it
  is about zero in both arms). R has no titled trade, so its titled net is 0 by construction (a
  titled record in R is a problem).
- **Food shortfall share after relief** (`shortfall_deficit`, `_surplus`, `_all`): over every
  snapshot and the set's regions with demand, `sum(demand x max(0, 1 - min(1, sufficiency after
  relief))) / sum(demand)` (the CW3 rule; the harm panel's food shortfall as a share of demand,
  restricted to the set). `food_met_*`: the demand-weighted mean of `min(1, sufficiency)`.
- **Retail in the sets**: mean retail price (milli-units per ration) and priced-out person-turns
  over the set's retail frames.
- **Merchants' margin against the withheld income** (`holder_net_vs_withheld`, T): titled trade's
  counters at the end, `(cargo sales credited - owners paid) / 1000 - income withheld / 1e6`
  (wealth units): what holders realized selling delivered cargo, less what they paid the owners,
  less the model income withheld from them while they carried. Positive: the margins more than
  replace the income they gave up; negative: they do not.
- **Shipments by outcome and cause**, owners' receipts (paid for their surplus), food decayed in
  transit, households' food purchases credited to sellers (retail counter), the destination and
  origin regions' shortfall share (T alone; post-treatment selection), the commons at the end
  (region stockpiles of the five retail goods in the final world state).

**Validity checks (a breach is a problem that fails the run, rc 3, never a value):** every
shipment's cargo closes in every snapshot (`sum(cargo_open) = aboard + losses + delivered +
returned + deposited`); one paid-work receipt row per carrier-turn (`receipt_rows =
carrier_turns`); every A1 ledger closure true on every observed frame (including the measured
`cargo_purchase` closures); titled trade recorded only in T and dated s - 1 (the runner's package
check); the turn-0 food account present. Structural `None`: titled measures in R. A missing
measure is a problem, never a zero.

## Primary outcomes

1. `cw5_food_in_deficit` (T - R): food into the deficit regions by trade over the run (the
   channel, net of what titled trade buys there and of any native trade it displaces).
2. `cw5_shortfall_deficit` (T - R): the deficit regions' food shortfall share after relief (the
   welfare question).
3. `cw5_margin_vs_withheld` (T alone; no control: the model income is not recorded by occupation
   in R): merchants' realized margin less the model income withheld (replacement, not stacking).

Signs are not forced. Prediction (inferred from development worlds, never evidence): titled
trade moves food out of turn-0 surplus regions, the deficit regions' shortfall share falls a
little, and margins exceed the withheld income.

## Secondary outcomes

- Channel and selection: titled food delivered into the deficit regions and titled net (T);
  native commons trade into them (T - R); their `min(1, sufficiency)`, priced-out person-turns and
  retail price (T - R); the destination regions' shortfall share (T; selection).
- The exporters (harm): the surplus regions' shortfall share, retail price, priced-out
  person-turns and food into them by trade (T - R); the origin regions' shortfall share (T;
  selection); all regions' shortfall share (T - R).
- Shipments by outcome and cause (T): bought, delivered, returned after a release, returned for
  a lost route, returned for a conquered destination, escheated; region-turns with a titled
  shipment.
- Money (T): merchants' margin and the income withheld separately; owners paid; households' food
  purchases credited to sellers (T - R); food lost to transit decay.

## Harm panel

The runner's fixed panel beside T - R: population and treasury at the end, food shortfall after
relief over the run, priced-out persons and children (household retail is on), epidemic deaths,
agents migrating between regions, the wealth Gini at the end; the timber stand reads `not
recorded` (the timber stock is off); deaths by famine and by war need slice extractors
(`requires slice extractor`). The screen adds T - R rows for the commons food at the end (the
commons drawdown), the world food shortfall, priced-out persons, treasury, the mean stability of
living civilizations at the end and population; the exporters' shortfall and prices and the
shipments returned by cause are listed above.

## Analysis plan

`report` prints activation per world first, then each outcome per stratum: the per-world values,
mean [min, max], sign counts and, for a contrast, the exact sign-flip enumeration of the mean
over the activated worlds (2^6 assignments per stratum). Strata are reported separately and not
pooled. A primary is read as consistent when its sign agrees on at least 5 of 6 worlds in a
stratum and the sign-flip share is at most 4/64; anything else is read as no consistent effect.
Secondaries and harms are descriptive. The procedural and template strata may disagree; both are
reported.

## Extractor validation (the shared pilot, before the freeze)

- Offline tests `tests/test_cw5_screen.py` (oracle chunk `connected-world-e`): the arms and
  primaries; the sets from world turn 0 (and a misdated account as a problem); titled food into
  and out of the sets, the native net, the margin, prices and priced-out persons, the commons and
  the region-turns on a constructed bundle; R's titled flows zero by construction and a titled
  record in R a problem; the validity checks (cargo not closing, receipt rows, a failed ledger
  closure); activation.
- On the pilot bundles (template 5 and procedural 19, both arms, source `14012038`): every outcome
  extracted, no problem; the sets identical in R and T on both worlds; an independent
  recomputation from the four kept bundles, not importing the screen module, matched the
  extractor on the deficit shortfall share, food into the deficit regions and the margin less the
  withheld income on every run (to the printed precision, 9 and 6 decimals). The raw runs were
  then deleted.
- `check --screen CW5` passes; `check --screen CW5 --metrics PILOT/metrics.jsonl --cohort pilot`
  passes (4 runs complete, every outcome extracted).

## Timing pilot (the shared pilot)

`run PILOT --screen CW5 --cohort pilot --jobs 2` on `21aa48cb` (clean tree; `source.txt`: dirty 0,
dirty-code 0; extension `43cbd22a…`): 4 runs, 0 failed, every outcome extracted; 67 s of
simulation and extraction. Seconds per run: R template 8.8, procedural 21.8; T template 9.7,
procedural 26.5. T activated on both worlds (template 5: 111 shipments, titled shipments in 196 of
1,600 region-turns; procedural 19: 660 shipments, 1,277 of 6,400). **Projected held run: 0.111
core-hours for 24 runs** (x1.5 = 0.167). The pilot's `metrics.jsonl`, `source.txt` and
`report.md` are retained in `connected-world-screens-cw5/pilot/` (the held run's `--pilot`). The
report prints the pilot's outcomes; they were not used to choose any definition (the sets,
measures and primaries were fixed before the first pilot run; that run's code differed only in
the CW2 part of the screen module).

## Budget and stopping rules

- **Compute ceiling 0.25 core-hours** (the line above, read by the runner: the pilot projection
  0.111 x 2.25, leaving room for runs about 1.5 times slower on a loaded machine). Run with
  `--jobs 2` (other lanes share the 4 cores). The runner refuses a held run whose pilot
  projection x 1.5 exceeds the ceiling and starts no run that would pass it; runs not started are
  reported as `not run` (exit code 4), never as zeros. Raising the ceiling needs the lead's
  amendment before any held outcome is read.
- At most 2 GiB of transient disk; raw run outputs are deleted after extraction.
- A failed run is reported as failed with its reason and is not replaced by another seed; a held
  run that needs new worlds uses the program reserve through the lead (`--cohort reserve`).
- After the held run: `report` (retained with `metrics.jsonl`, `source.txt`, `held-run.json` under
  `connected-world-screens-cw5/`), `check --metrics`, and `mark-run`, whose registry change is
  committed with the results.

## Program E: one reproducible titled shipment

Development world template 1 (a registered development world, never held), source `9591e280` or
later, extension `43cbd22a…`:

```
python -m chronicler.main --seed 1 --turns 90 --agents hybrid --simulate-only --grain-reserves \
  --public-grain-shipments --food-allocation --household-retail --household-retail-boundary all \
  --titled-trade --wealth-accounting --output OUT/chronicle.md --state OUT/state.json
```

- **Purchase -> transit -> sale (shipment 14):** in world turn 73 (snapshot 74) merchant 21 bought
  2.000 food units (grain and botanicals) from 12 owners in Crystalfen Marsh for 1.000 at 250
  milli per ration, each owner paid by id; carried it (reserved, its model income withheld: 0.020
  over 3 carrier-turns) through Obsidian Shore and Ashara Desert to Stormbreak Cliffs, arriving in
  world turn 76 with 0.087 lost to transit decay and 1.913 delivered as its own retail claim; the
  destination's households bought 1.868 of it in world turn 77, credited 2.053 to merchant 21
  (an exact attribution).
- **Purchase -> transit -> return (shipment 28):** in world turn 83 the same merchant bought
  1.457 food units from 4 owners in Crystalfen Marsh for 0.729; after two hops the route to
  Stormbreak Cliffs was lost (world turn 86) and the cargo returned to the origin at full value as
  its claim there (outcome `returned`, cause `route_lost`).
