# Connected-world CW5: preregistered held screen for titled trade (slice A4-1)

Status: DRAFT, pre-freeze revision 2 (not frozen; the lead freezes it before any held run; see
"Pre-freeze revision 1" and "Pre-freeze revision 2" at the end). Written 2026-11-07 by the A4
lane on branch `claude/cw-a4-titled-trade` at `21aa48cb`, revised at `a1b61760` and `99d48901` (the A4 review fixes approved at
`d5ccd4d6`, merged with `main` `bac45cb5`, plus the lead's carrier rule at `9591e280`: carriers
take no native decision while reserved). Native extension built from this branch, SHA-256
`43cbd22ac4e7e2c6a77e71781a884be5342f41aa4173ff6f43e0facf0f5e0eb0`. No held seed (template
771-776, procedural 871-876) has been run; the registry still lists both as `reserved`. Code may
change before the held run only to fix a defect, recorded as an amendment with a new pilot; no
arm, outcome, set or parameter changes in response to held outcomes.

Compute ceiling: 0.65 core-hours

Primary outcomes: cw5_food_in_deficit, cw5_shortfall_deficit

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

Pre-freeze revision 2 (the lead's decision). **Per world, a pre-treatment window: world turns 0 ..
min(19, f - 1)**, f being T's first titled purchase turn on that world (no purchase: 0-19). T
equals R until f, so the window is pre-treatment by construction. Classified **relatively**:

- each region's demand-weighted production ratio over the window, `sum produced / sum demand`
  (`food_accounting.regions[i].native`), against the world's ratio over the window;
- **deficit regions**: ratio below the world's; **surplus regions**: at or above it;
- regions without demand throughout the window are in neither set.

**Minimum window 5 turns:** a world with f < 5 is left out of every set-based outcome (primaries
included) and listed, never imputed. **Pairing:** one run's extraction cannot see the other arm,
so the extractor keeps per-region vectors (the window's per-turn production and demand; the run's
shortfall terms, native and titled trade, retail prices and priced-out persons) and the report
pairs R's and T's rows of each world (`cw5_pair`, called from the report's window table): it
computes R's sets over T's window, fills the set-based measures of both rows from those sets, and
checks as validation that R's and T's window records are identical (the per-turn vectors and the
sets; a world where they differ is excluded and listed). Classification never uses R's realised
production after the window.

**Sensitivity lines (never primary):** the turn-0 sets (production below demand at world turn 0;
`cw5_t0_*`), and R's whole-run region-level ratio applied to both arms (`cw5_rr_*`). The latter
selects regions on R's realised production over the run, so regression to the mean can make T
look better there than it is: it is reported only beside the window sets.

## Activation (reported per world before any effect)

`cw5_activation(bundle, flags)`; the root R is not judged. **T acted** when at least one titled
shipment was delivered. The evidence names the shipments by outcome (delivered, returned for a
lost route or a conquered destination, returned after a carrier's release, escheated at the
holder's death) and the **region-turns with any titled shipment** (a region where a shipment was
bought, stood, moved or closed that turn) out of all region-turns, and T's first purchase turn f
(which ends the world's window). A world where T did not act is
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
- **Merchants' accounting balance on titled cargo** (`holder_balance`, T; a secondary since
  revision 1): `(cargo sales credited - owners paid) / 1000 - income withheld / 1e6` (the
  realized margin less the withheld model income, `holder_net_vs_withheld`) **plus the titled
  food the merchants still hold, at its purchase cost**: food returned to the origins (each closed
  shipment's returned food at that shipment's cost per milli-food), cargo aboard at the end
  (each live shipment at its own cost) and delivered food still unsold at the end (the last
  record's lots, at the run's mean purchase cost per milli-food). Escheated, deposited and lost
  food carries no value. Returned food sold later at the origin is valued at cost, not at its
  sale price (retail does not attribute those sales to the shipment).
- **Shipments by outcome and cause**, owners' receipts (paid for their surplus), food decayed in
  transit, households' food purchases credited to sellers (retail counter), the destination and
  origin regions' shortfall share (T alone; post-treatment selection), the commons at the end
  (region stockpiles of the five retail goods in the final world state).

**Validity checks (a breach is a problem that fails the run, rc 3, never a value):** a complete
food account in every snapshot (revision 1: a missing one was read as zero trade before); every
shipment's cargo closes in every snapshot (`sum(cargo_open) = aboard + losses + delivered +
returned + deposited`); one paid-work receipt row per carrier-turn (`receipt_rows =
carrier_turns`); every A1 ledger closure true on every observed frame (including the measured
`cargo_purchase` closures); titled trade recorded only in T and dated s - 1 (the runner's package
check); the window's food accounts present. Structural `None`: titled measures in R; set-based
measures on a world excluded by the window (and before the report pairs the rows: they are
computed from the per-region vectors only then). A missing measure is a problem, never a zero.

## Primary outcomes (two since revision 1)

1. `cw5_food_in_deficit` (T - R): food into the deficit regions by trade over the run (the
   channel, net of what titled trade buys there and of any native trade it displaces).
2. `cw5_shortfall_deficit` (T - R): the deficit regions' food shortfall share after relief (the
   welfare question).

No third primary: a T - R contrast of merchants' income or wealth cannot be extracted from the
bundle (the lead accepted two primaries). No record holds money or wealth by occupation in either arm (the A1 ledger is
world-, region- and channel-level; R has no merchant money record), so the merchants' balance is
the single-arm secondary above.

Signs are not forced. Prediction (inferred from development worlds, never evidence): titled
trade moves food out of surplus regions, the deficit regions' shortfall share falls a little, and
margins exceed the withheld income.

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
- Money (T): the merchants' accounting balance (`cw5_holder_balance`, above) and its parts: the
  realized margin less the withheld income (`cw5_margin_vs_withheld`, an accounting balance, the
  third primary before revision 1), the returned food and the cargo aboard at purchase cost, the
  margin and the income withheld separately; owners paid; households' food purchases credited to
  sellers (T - R); food lost to transit decay.
- Sensitivity (T - R): food into, and the food shortfall share of, the turn-0 deficit regions.

## Harm panel

The runner's fixed panel beside T - R: population and treasury at the end, food shortfall after
relief over the run, priced-out persons and children (household retail is on), epidemic deaths,
agents migrating between regions, the wealth Gini at the end; the timber stand reads `not
recorded` (the timber stock is off); deaths by famine and by war need slice extractors
(`requires slice extractor`). The screen adds T - R rows for the commons food at the end (the
commons drawdown), the world food shortfall, priced-out persons, treasury, the mean stability of
living civilizations at the end and population; the exporters' shortfall and prices and the
shipments returned by cause are listed above. **Merchant and farmer counts at the end** (asked
for in revision 1, since carriers no longer switch occupation) are **not recorded** in any bundle
field: no record counts occupations. The nearest record, the retail frames' household cohorts
(`nonfarm_adults`: adults off any crew who are not farmers), reads `persons: null` (unknown) in a
region whenever someone there died between the Phase 2 roster and provisioning, which happened in
the last snapshot of 3 of the 4 pilot runs; so the harm is declared and not read (a record would
be needed, outside this slice). Accepted by the lead and **recorded as a missing record for a
later slice**: occupation counts per region (at least merchants and farmers) in a record both arms
carry.

## Analysis plan

`report` prints activation per world first, then each outcome per stratum: the per-world values,
mean [min, max], sign counts and, for a contrast, the exact sign-flip enumeration of the mean
over the activated worlds whose pre-treatment window is valid (2^6 assignments per stratum; a
world excluded by the window is listed in the report's window table and shown as unknown in every
set-based outcome). Strata are reported separately and not pooled. A primary is read as consistent when its sign agrees on at least 5 of 6 worlds in a
stratum and the sign-flip share is at most 4/64; anything else is read as no consistent effect.
Secondaries and harms are descriptive. The procedural and template strata may disagree; both are
reported.

## Extractor validation (the shared pilot, before the freeze)

Revision 2 (source `99d48901`):

- Offline tests `tests/test_cw5_screen.py`: the window sets over a row's vectors (a region at
  the world ratio is a surplus region); the report pairing R and T and filling the set measures
  over T's window (f = 20: turns 0-19; f = 12: turns 0-11); a world with f = 3 excluded (window of
  3 turns) while the turn-0 sensitivity line stays; differing window records excluded; the R
  whole-run sensitivity; the merchants' balance; R's titled vectors zero.
- On the four kept pilot bundles, by hand (not importing the screen module): T's first purchase
  is in world turn 18 on template 5 (window 0-17, 18 turns) and 7 on procedural 19 (window 0-6, 7
  turns); R's per-turn production and demand over each window equal T's exactly; the hand
  classification gives `D:0,5,7|S:1,2,3,4` (template 5) and `D:1,3,7,8,9,21,26,31|S:11,12,13,16,17,18,24`
  (procedural 19), the digests the report's pairing wrote into both rows; food into the deficit
  regions (T 58.0467 and R -0.0173; T -177.044 and R 0.0) and their shortfall shares (T 0.108876
  and R 0.130463; T 0.101368 and R 0.116273) equal the report's T - R values. Both worlds are valid.
  The raw runs were then deleted. `check --screen CW5 --metrics PILOT/metrics.jsonl --cohort pilot`
  passes.

Revision 1 (source `a1b61760`):

- Offline tests `tests/test_cw5_screen.py` (oracle chunk `connected-world-e`): the two primaries;
  the relative window sets (a region at the world ratio is a surplus region) and the turn-0
  sensitivity sets; an incomplete window as a problem; titled food into and out of the sets, the
  native net, the count `tt_returned` kept apart from the food `tt_returned_food`, the merchants'
  balance with cargo aboard and unsold lots at cost; a purchase inside the window invalidating the
  world's set outcomes; the report comparing R's and T's set records and marking a mismatch; a
  missing or non-numeric food account as a problem, never a zero; R's titled flows zero by
  construction; the validity checks; activation with the window purchases.
- On the pilot bundles (template 5 and procedural 19, both arms): every outcome extracted, no
  problem. An independent recomputation from the four kept bundles, not importing the screen
  module, matched the extractor on the window sets (the same digest), the purchases inside the
  window, the deficit shortfall share and food into the deficit regions on every run. The raw
  runs were then deleted.
- `check --screen CW5` passes; `check --screen CW5 --metrics PILOT/metrics.jsonl --cohort pilot`
  passes (4 runs complete, every outcome extracted).
- **Both pilot worlds fail the window check** (see "Pre-freeze revision 1").

Before revision 1 (source `14012038`, the turn-0 sets): every outcome extracted; the turn-0 sets
identical in R and T on both worlds; an independent recomputation matched.

## Timing pilot (the shared pilot)

`run PILOT --screen CW5 --cohort pilot --jobs 2` on `99d48901` (revision 2; clean tree;
`source.txt`: dirty 0, dirty-code 0; extension `43cbd22a…`): 4 runs, 0 failed, every outcome
extracted; 194 s of simulation and extraction **on a loaded machine** (load average about 10 on 4
cores from other lanes). Seconds per run: R template 24.1, procedural 65.0; T template 16.5,
procedural 88.1. T activated on both worlds; both windows valid. **Projected held run: 0.323
core-hours for 24 runs** (x1.5 = 0.484); the revision-1 pilot on a less loaded machine projected
0.126. The pilot's `metrics.jsonl`, `source.txt` and `report.md` are retained in
`connected-world-screens-cw5/pilot/` (the held run's `--pilot`). The report prints the pilot's
outcomes; they were not used to choose any definition.

## Budget and stopping rules

- **Compute ceiling 0.65 core-hours** (the line above, read by the runner: the loaded
  revision-2 pilot's projection 0.323 x 2, so that it passes the runner's x1.5 check; held runs
  will see similar shared load; 0.30 at revision 1, 0.25 before). Run with
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

## Pre-freeze revision 1 (2026-11-07, before any held run; the lead's decisions after the delta review)

The delta review approved the code at `347621e7` and asked for changes before the freeze. Made at
`a1b61760` (screen module and tests; this page):

1. **Region sets from a pre-treatment window** (world turns 0-19), classified relatively against
   the world's production ratio, with the per-world validity check (no titled purchase in the
   window; identical set records in R and T, compared by the report) and the turn-0 sets kept as a
   sensitivity line. Reason (the review): turn 0 left out regions populated by turn 20, classified
   a near-balanced region as deficit (26.91 < 27.0) that became the second-largest titled exporter,
   left the surplus set empty on template 1, and an absolute threshold does not separate regions
   when every region produces below its demand over the run.
2. **Two primaries.** No T - R merchant income or wealth can be extracted (no record holds money
   or wealth by occupation in either arm). The single-arm margin less the withheld income is an
   accounting balance, now a secondary, and completed into the merchants' balance with returned
   food, cargo aboard at the end and unsold delivered lots at purchase cost.
3. **Extractor fixes:** the shipment count `tt_returned` was overwritten by the returned food in
   units (now `tt_returned_food`, with the other counter-derived units renamed to keep them
   apart); a missing or incomplete food account in any snapshot is a problem (rc 3), never zero
   trade.
4. **Harm panel:** merchant and farmer counts at the end are not recorded (above): declared, not
   read.

**Found in the revision-1 pilot (resolved by revision 2):** both pilot
worlds **fail the window check**. On template 5 T's first titled purchase is in world turn 18 (one
purchase inside the window); on procedural 19 it is in world turn 7 (twenty purchases inside the
window), and there R's and T's window sets differ in one region (region 5). Under the rule as
written, both worlds are left out of every set-based outcome, so the primaries read `unknown` on
both; if the held worlds behave alike, the primaries could be undefined on most of them. Options
(for the lead; each needs a pre-freeze revision 2 and a new pilot): a per-world window that ends
before T's first titled purchase (identical in R and T by construction, but short where trade
starts early: 7 turns on procedural 19), or the review's fallback, R's whole-run region-level
production ratio applied to both arms. Either needs the set-based measures aggregated when the
report pairs R's and T's rows (the extractor would keep per-region vectors), because one run's
extraction cannot see the other arm.

## Pre-freeze revision 2 (2026-11-07, before any held run; the lead's decision on the window)

Made at `99d48901` (screen module and tests; this page):

1. **Per-world window** world turns 0 .. min(19, f - 1), f being T's first titled purchase turn:
   pre-treatment by construction (T equals R until f); the identity of R's and T's window records
   is kept as validation. Reason: the fixed window 0-19 failed on both pilot worlds (purchases
   from turn 18 and turn 7).
2. **Minimum window 5 turns**: a world with f < 5 is excluded from the set-based outcomes and
   listed, never imputed.
3. **Sets paired in the report**: R's sets over T's window, filled into both rows from per-region
   vectors the extractor keeps.
4. **Sensitivity lines** (never primary): the turn-0 sets and R's whole-run region-level ratio,
   with its regression-to-the-mean risk stated.
5. **Two primaries stand**; the merchant and farmer counts are recorded as a missing record for a
   later slice.
6. **Ceiling** 0.65 core-hours from the loaded revision-2 pilot.
