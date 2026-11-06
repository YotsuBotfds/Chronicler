# Household food retail (L6b, `--household-retail`, default off)

Package PL4 of the phase "productive recovery and household livelihoods"
([plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2, with the
lead's decisions and the binding FFI contract). Design and measurements:
[household-retail-design.md](household-retail-design.md). Requires `--agents hybrid`
and `--food-allocation` (L2, [food-allocation.md](food-allocation.md)).

This page has three parts: **Python** and **Accounting** (lane PL4-python) and
**Native** (lane PL4-native). Both lanes are integrated on `claude/household-retail`
(checkpoint 2); the lead's integration notes and review fixes are recorded there and in
the phase plan.

## Python

Modules: `chronicler/household_retail.py` (hooks, rules, checks) and
`chronicler/household_retail_state.py` (persisted data).

### Switch

- `--household-retail` (default off), appended to `LIVELIHOODS_SWITCHES` after
  `food_allocation` (so L2's hooks run first in every phase).
- `--household-retail-mode`: `retail` (default), `no_relief`, `free_exchange`,
  `record_only`.
- `--household-retail-boundary`: `market` (default), `paid_work`, `all`.
- Prerequisites (`livelihoods._check_prerequisites`, `feature_catalog.REQUIREMENTS`):
  `--agents hybrid` and `--food-allocation` (given or saved). The three keys are in
  `batch_manifest.SIMULATION_ARG_KEYS` and are omitted from a manifest when unset, so
  feature-off manifests keep their bytes. A mode or boundary given without the switch
  is ignored (the existing livelihoods limit); an exact resume refuses one that
  conflicts with the checkpoint (`livelihoods_resume_conflicts`).
- A saved, enabled switch is checked too. A resume that turns `--food-allocation` off,
  or runs outside `--agents hybrid`, is refused with a message naming
  `--no-household-retail`. Passing it closes every claim to its region's commons, with
  a dated `switch_off` record per region, so no claim, owned food or pilot region drops
  out unseen.

### State

`world.livelihoods.household_retail` (absent until the switch is first enabled,
`exclude_if=None` as every livelihoods sub-state):

- `regions`: one `RetailRegion` per open pilot region (ascending index): `goods`
  (milli-food per good in the order grain, fish, salt, botanicals, exotic) and `claims`
  (`{stable id: milli-food}`, positive entries only, ascending id), with
  `sum(claims) == sum(goods)` always; `opened_turn`, `reason`, lifetime flow totals.
- Exactly-once guards: `last_title_turn`, `last_settled_turn`, `last_procured_turn`.
- One completed-turn frame (`frame_turn`, one `RegionFrame` per pilot region touched
  this turn, money and income totals, a 24-person sample), a rolling dated record log
  (the last 64 records: openings, closures, war losses, inheritance, escheat, pool
  resets, refusals) and fixed-key counters.
- A claims cap of 4096 entries over the world. A farmer or heir who would need a new
  entry beyond it is refused (`claims_refused`); that share goes to the commons.
- A transient `_turn` (books, installs, spouse reads, procurement records) that is never
  pickled and is empty at every turn boundary.

Owned food is never in `region.stockpile`: that is the commons.

### One turn

| Where | Hook | What Python does |
| --- | --- | --- |
| Phase 2, before the economy | `prepare_phase2` | Boundary update: a pilot region without a controller closes (holdings to the commons, `pilot_closed`); newly qualifying regions open. A conquest since the last agent tick takes its share of owned stock. Commons written after the region batch was built (closure, pool reset) are patched into its `stockpile_<good>` columns. Title weights from the Phase 2 snapshot. Unless `record_only`, and only when a pilot region exists, appends `retail_title_share` (θ; null outside the pilot) and `retail_owned_<good>` (owned stock / 1000). |
| Phase 2, after the economy | `finish_phase2` | Checks the pilot region's native food ledger and the title weights against the farm labour after named crews. Title, once per turn: each good's `retail_titled_<good>` (to the nearest milli-food) split over the region's Phase 2 farmers by largest remainder, ties by ascending id. Then the native owned decay and overflow per good, applied to claims pro rata. Untitled and refused shares decay with the pool and then go to the commons. Records each pilot region's controller. |
| Before the agent tick | `before_agent_tick` | Conquest loss for a pilot region conquered since Phase 2. Spouse of every owner (`get_agent_relationships`, one call per owner). Installs `set_household_retail(turn, mode, regions, claims)` and, except in `free_exchange`, `install_retail_income(turn, regions)`. |
| After the agent tick | `after_agent_tick` | Takes the frame and income receipt once, refuses a stale, repeated or partial pair, checks the frame, debits own-eaten and sold food from the claims, records money, then settles dead owners' claims. |
| Phase 10 | (seam in `tick_grain_reserves`) | Owners' grain sold to their ruler's granaries is debited from claims as it is bought. |
| Phase 10 | `phase10` | Credits those owners once (`transfer_wealth`, purpose 6), records merchant food departures and the owned food merchants could not load, then closes the turn's frame. |
| Failure | `rollback_phase2`, `rollback_agent_tick` | Drops the Phase 2 plan; cancels the retail and income installs the tick never took. |
| Rebuilt pool | `on_pool_reset` | Closes every claim to its region's commons, dated (the regions stay in the pilot). |

L2's seam (`food_allocation.after_agent_tick`): regions that retail provisioned this
tick are left out of L2's closure check, totals, rows and sample; retail's own frame
closes them. With retail off, or in `record_only`, the set is empty and L2 is unchanged.

### Pilot boundary

Sticky: a region leaves only when it has no controller, when the switch goes off, or
when the mode becomes `record_only` (the last two close every holding to the commons at
configuration, recorded `switch_off`).

- `market`: each ruling civilization's `capital_region`, when the civ controls it, from
  the turn it first qualifies.
- `paid_work`: regions where paid work has been done, read from each lane's last
  committed frame:
  - an open L6a firm (`workshop_payroll.firms`);
  - a repair crew paid in RS2's receipts (`repair_projects.receipts`, `wages_milli > 0`);
  - a paid PL3 granary crew (`recovery_crews.receipts`, `kind == "granary"`,
    `wages_milli > 0`);
  - the home region of a paid PL1 woodcutting crew (`timber_supply.receipts`,
    `wages_milli > 0`).
- `all`: every region whose controller rules at least one region.

### Title weights

For an alive farmer (`occupation == 0`) of a pilot region in the Phase 2 snapshot:
`w = max(0, u × (1 − h) − r)` in integer micro-units.

- `u` is `cities.URBAN_FARM_LABOR[rank]` when the farmer's settlement is a city of that
  region, else 1.
- `h` is this turn's health work loss from the health plan (`world.health_care._prepared`,
  prepared just before): the impairment for an eligible patient (adult rural farmer, not
  enlisted), the care fraction for a caregiver.
- `r` is the farm time the person gave a named crew this turn. It is paid as a wage, so
  it is never also titled. It is read from the packages' staged receipts:
  - a PL1 woodcutter: their farm share `u`, scaled by the woodcut labour the economy
    actually removed from that home region;
  - a PL3 granary crew member: their worked share of the delivered storage work;
  - a PL3 workshop crew member: the farm time removed through `farm_labor_factor`.

Every turn, per pilot region, `Σ (u (1 − h) − r)` must equal `farmers ×
farm_labor_factor − health loss − named granary work − woodcut labour removed`. Named
woodcut requests must equal the crews' farm shares, and named granary time may not
exceed the storage work delivered. Anything else is refused. Anonymous storage work (RS2
without crews, grain storage) shrinks every title equally.

Children hold their own title. Opening stock, merchant imports, convoy and granary grain
stay commons.

### Price and free rations

- Price, milli-units per ration: `floor(clamp(market_prices[food], 0.5, 3.0) ×
  per-capita food × 1000)`. `free_exchange` installs 0.
- Free rations: `(commons_consumed + this turn's granary release) / per-capita food`.
- θ = 0.9 (`retail`, `free_exchange`), 1 (`no_relief`). Native modes: retail 0,
  no_relief 1, free_exchange 2.

### Lifecycles

- **Death.** After the tick, an owner not in the post-tick snapshot passes each claim
  to the spouse read before the tick, if alive; else equally to the living children
  (either parent id) in the claim's region, largest remainder, ascending id; else to
  that region's commons (`escheat`). An heir beyond the claims cap is refused and that
  share escheats. A claim whose owner died in the tick before provisioning (phase 0.0
  deaths) is withheld whole by the native step, so the heirs receive all of it. It
  stays in `offered_milli`, is neither sold nor eaten (its claim row reads `(owner,
  region, 0, 0)`), and counts in `unsold_milli` and in `withheld_dead_claims` /
  `withheld_dead_milli`. Settlement checks those two columns exactly: exactly
  `withheld_dead_claims` of the zero rows of owners dead after the tick must sum to
  exactly `withheld_dead_milli`. It cannot require all of them, because natural deaths
  come after phase 0.7, so an owner dead after the tick may have been alive to sell.
  - Native estate order (`household.rs`): spouse first, then dependants anywhere, then
    all children anywhere. Python follows lead decision 6: children in the claim's
    region only, all ages, equally. The spouse case agrees. Child cases can differ;
    `tests/test_household_retail_native.py` counts them.
- **Migration.** The claim stays in the origin's pool. The owner sells it wherever they
  live and eats from it only when present.
- **Household split, rejoin, remarriage.** Claims are personal; households are never
  stored, so nothing is created or lost.
- **Conquest.** `v − floor(v × CONQUEST_STOCKPILE_SURVIVAL)` of each owned good is
  destroyed (`war_loss`), claims pro rata, once per conquest event. The event is the
  region's `last_conquered_turn`, set by `action_engine.apply_region_conquest` (the path
  that destroys market stock, annexed occupations included), when it is newer than the
  last loss applied. It is checked before the economy and before the agent tick, so a
  conquest in any phase is applied before the next sale. A change of controller without
  a conquest (peaceful transfer, abandonment) destroys nothing. Occupation and siege requisitions do not
  reach owned stock (declared limit, counted in `requisition_exempt_region_turns`).
- **Pool reset.** Every claim to the commons, dated.

### Merchants, procurement and the controls

- **Merchants** load only commons (lead decision 7). Owned food is never in
  `region.stockpile`, so no merchant carries or pays for it. Each pilot region-turn
  records `merchant_food_departing` (the food merchants committed to loads and departures
  from the commons, from the native commitments procurement reads) and
  `owned_food_unloadable_milli` (the owned food they could not load). The foregone
  departures are at most the latter.
- **Foreign purchases and public grain shipments** buy commons only. Owners' grain is
  sold only to their own ruler's granaries. A foreign buyer pays the seller's ruler as
  before (`finance.transfer`); owners neither lose grain nor are paid.
- **`free_exchange`.** Buyers are not charged: Python installs price 0, the native runs
  mode 2 at price 0, and Python refuses a frame that moved money. Farm income is kept.
  Granaries still buy owners' grain as in `retail`, but procured owner grain is not paid
  for: the treasury's cost goes to the old sink ("producers outside the treasury
  accounts"), exactly as with retail off, and is counted as `procurement_unpaid_milli`.

### Granary procurement (pinned seam in `grain_reserves.py`)

- A pilot market's sellable surplus counts commons plus owned grain (only grain: owned
  fish, salt, botanicals and exotic do not count towards the market's keep).
- The owned part of that surplus is sold only to the owners' own ruler. A domestic
  purchase takes it first, pro rata to claims, in whole milli-food rounded up. Exactly
  that milli-food leaves the owned pool: the purchase takes it, and a sub-milli excess
  over the purchase goes into the market's commons, so nothing is lost or made. A
  foreign purchase or public grain shipment takes only the commons part.
- The treasury pays as before. In Phase 10 each such flow's owners' share,
  `floor(cost × 1000 × owned sent / sent)`, is credited to them by id in one
  `transfer_wealth(turn, 6, 0, rows)` call. The rest of the cost, and any residual the
  wealth ceiling refuses, stays with the old sink ("producers outside the treasury
  accounts").
- `free_exchange` sells the same grain but credits nobody (`procurement_unpaid_milli`).
- The resource ledger's market term (`CHRONICLER_CHECK_RESOURCES`) adds owned grain
  sold to the market's own drop.

### Modes

| Mode | Title | Install | Income | Procurement |
| --- | --- | --- | --- | --- |
| `retail` | θ = 0.9 | priced | replaced | owners paid |
| `no_relief` | θ = 1 | priced, native mode 1 | replaced | owners paid |
| `free_exchange` | θ = 0.9 | price 0, native mode 2 | kept | owners unpaid |
| `record_only` | none | none | kept | none |

`record_only` keeps the boundary and records what retail would do per pilot region:
the would-be title (θ × the production ledger's food output), its owners, and the
price. It holds no food, appends no columns and calls no retail method. The world's
trajectory equals L2 alone; the offline test compares the full world dump and the
stand-in pool.

### Frame columns this lane proposes

The contract fixes the provisioning frame's shape, not its region column names.
Python requires these (`household_retail.FRAME_COLUMNS`) and refuses a frame without
them:

`region`, `price_milli`, `free_rations`, `free_given`, `free_unallocated`,
`offered_milli`, `own_eaten_milli`, `sold_milli`, `unsold_milli`, `paid_milli`,
`credited_milli`, `refunded_milli`, `rations` (sum of person rations), `persons`,
`priced_out_persons`, `offer_short_persons`, `withheld_dead_claims`,
`withheld_dead_milli`.

Other columns are kept in the frame as given. The frame must also carry one claim row
for every installed claim.

### Snapshot

`livelihoods.household_retail` (stage `L6b`) for the completed turn: per pilot region
`open_milli`, `close_milli`, `goods_close`, owners, flows, commons by reason, price,
free rations, the native Phase 2 columns and provisioning row, income replaced (and
rows) for its farmers, merchant food departing and owned food unloadable, plus money,
income,
the sample, the log, counters and parameters. A turn without a frame reads `None`
(unknown, not zero).

## Accounting

Units: food in integer milli-food (1000 = one food unit = two rations); money in
integer milli-units (1000 = one wealth unit = one treasury unit). Native f32 quantities
are converted to the nearest milli. Python's books are authoritative and are re-sent
every turn, so f32 differences do not accumulate.

Raised on failure (`RetailAccountingError`, a `RuntimeError`):

- **`check_region`** after every mutation, per pilot region and good: `close = open +
  titled − own_eaten − sold − procured − decay − overflow − war_loss − to_commons`.
  Also `sum(claims) == sum(goods)`, and nothing is negative.
- **`check_owner`**, per owner, untitled and refused shares included: `claim_close =
  claim_open + titled − own_eaten − sold − procured − decay − overflow − war_loss −
  to_commons + inherited_in − inherited_out`. Every flow moves claims and goods by the
  same total, and inheritance conserves claims.
- **Native Phase 2**, per good: `owned_close = owned_open + titled − decay − overflow`
  (f32 tolerance). Python's owned stock agrees with the native close within 3 milli
  plus 2·10⁻⁵ relative.
- **Native food ledger**, per pilot region:
  - `closing = opening + produced + transport_net − craft_input + clamp − consumed −
    storage_loss − cap_overflow`;
  - `opening` equals the commons sent plus the owned stock sent;
  - `closing` equals the commons returned plus the owned close;
  - all within 10⁻⁵ relative; skipped when the extension exports no ledger.
- **Title weights**: equal to the farm labour after named crews (see Title weights).
- **Provisioning**, per region:
  - `free_given + free_unallocated = free_rations`, and `free_rations` equals the
    install;
  - `own_eaten + sold = offered − unsold`;
  - `offered` equals the installed claims;
  - `withheld_dead_milli ≤ unsold`, and exactly `withheld_dead_claims` of the zero
    claim rows of owners dead after the tick sum to exactly `withheld_dead_milli`;
  - the claim rows sum to the region's `own_eaten` and `sold`;
  - `sum(person rations) = free_given + (own_eaten + sold) / ration`, each ration at
    most 1.
- **Claim rows.** There is exactly one per installed claim, and `own + sold` does not
  exceed it.
- **Money.** Per row, `paid`, `credited` and `refunded` are nonnegative and `refunded ≤
  paid`. `Σ paid = Σ credited + Σ refunded`, per region and over the rows, and the two
  totals agree. `free_exchange` moves no money. Per region, `sold × price ≤ paid ×
  ration ≤ sold × price + buying_households × ration`: each buying household pays
  `ceil(bought × price / ration)`.
- **Income.** The receipt is of this turn, with unique ids and finite, nonnegative
  amounts.
- **Procurement.** Each recorded take matches a `BOUGHT` flow of its source with
  `seller == buyer`. `Σ owner credits = Σ owners' shares`. Each native transfer row
  satisfies `applied + residual = requested`.

Exactly once:

- **Title.** `last_title_turn`, refused on a repeat.
- **Provisioning.** The frame and income receipt are taken once and must name this
  turn. `last_settled_turn` refuses a second settlement. A pending frame without its
  income receipt, or the reverse, is refused. Installs the tick never took are
  cancelled and counted (`turns_not_taken`).
- **Procurement.** `last_procured_turn`, plus the native `(turn, purpose, batch)` key.
- Nothing is pending at a turn boundary.

Python cannot see, and leaves to the native lane:

- that no pilot farmer has both replaced and ordinary farm income;
- per-person cash limits (`priced_out`);
- the fair-share and open rounds;
- that a buyer never goes below zero (Python checks only the totals).

### Pinned edits (lead witness layers)

- `src/chronicler/grain_reserves.py`: the procurement seam and the resource ledger's
  market term.
- `src/chronicler/economy.py`: `EconomyResult.household_retail`, and
  `reconstruct_economy_result` keeping the `retail_*`, `commons_consumed` and
  `commons_sufficiency` result columns. Without this, Python cannot read the contract's
  result columns.
- `src/chronicler/batch_manifest.py`: the three keys in `SIMULATION_ARG_KEYS` and in
  `simulation_config`'s omit-when-unset list.
- `tests/test_batch_manifest.py`: the three keys.

### Tests

- `tests/test_household_retail.py` (offline, chunk `household-retail`): a stand-in
  native implements the contract with simple rules.
- `tests/test_household_retail_native.py` (native shard 1): gated rather than skipped.
  It collects only an all-or-none check of the retail methods until they exist, and
  the integration tests once they do. `CHRONICLER_REQUIRE_RETAIL_NATIVE=1` makes their
  absence a failure.

## Native

### Build identity

- Source: `claude/hr-native-cap` at `3ed75f22` (the combined opening cap on top of
  `claude/household-retail` `4fac1537`). The Rust tree is unchanged after that commit
  (later commits touch tests and this page).
- Extension built with `/home/user/wt/tools/build_native.sh` into `~/.venvs/native-hrn`
  (CPython 3.13, release, `--locked`), checked by `check_python_env.py --expect
  native`: compiled submodule, real `AgentSimulator`, `EcologySimulator`,
  `PoliticsSimulator`.
- `chronicler_agents.cpython-313-x86_64-linux-gnu.so` SHA-256
  `b1910b948b07c3ab6bec8387552e99fbc72615b5fa31a0289c8698d8c85f9c6c`.
- Earlier builds:
  - `claude/hr-native-review` `4ae0ca8a` (`b8a09339…`): only the carried owned stock was
    cut at opening, so owned plus commons could exceed the cap;
  - `claude/hr-native-fix` `6a4fe37e` (`66cd5a7e…`): owned stock decayed after
    sufficiency;
  - the merge `2a962374` (`220f8421…`): dead owners' food sold;
  - the lane branch at `81d9743b` (`eda66ae8…`) and `a7436b65` (`3f248402…`).

### Deviations from the written contract

The contract is implemented as written, with these resolved gaps:

1. **Split unit.** A short offer is split by largest remainder in **milli-food**, not
   milli-rations. A milli-ration is half a milli-food, and claims are integer
   milli-food, so a milli-ration split could not be debited from them exactly.
2. **Ration size.** Milli-food per ration is the economy's `per_capita_food` × 1000
   (`economy.per_capita_food` is tunable). At the default 0.5 this is 500, the
   contract's "1000 milli-food = one food unit = two rations". Every region row reports
   `milli_food_per_ration`.
3. **L2 is required in the tick.** The install carries no Phase 2 alive counts or L2
   regime, so the step reads L2's `ProvisionConfig` for the same tick. The tick refuses
   (unchanged, `ValueError`) a retail install whose `source_turn` is not the tick's turn,
   or without an L2 allocation installed for that turn. It also refuses an income
   install for another turn, and (review D, m3) an income install whose regions are not
   pilot regions of the retail install (any region when no retail install is pending),
   except under `free_exchange`.
4. **Dead owners (lead decision, 2026-11-06).** A claim whose owner is no longer
   alive at phase 0.7 (catastrophe or targeted deaths after Phase 2) is **withheld**:
   neither offered nor eaten. It stays whole, so Python's settlement passes it to the
   spouse, then the living children in the region, then the commons. Recorded per region
   as `withheld_dead_claims` and `withheld_dead_milli` (part of `unsold_milli`). Before
   this change (`2a962374`) such a claim was sold and the payment refunded to the
   buyers (`refused_dead_milli`, now removed), so buyers ate it for free.
5. **Ceiling room.** A seller's room below `MAX_WEALTH` is measured before the tick's
   purchases. A person who both buys (in one region) and sells (in another) therefore
   gets no extra room from their own payment. This removes a refund/credit circularity
   and keeps every refund within what the buyer paid.
6. **Key consumed.** The in-tick settlement consumes the wealth-transfer key
   `(turn, food_purchase, batch 0)`; a replay `transfer_wealth(turn, 5, 0, …)` is
   refused. The settlement itself refuses a key already consumed for the turn (or a
   later one), and so does the tick before anything changes (review D, m2), unless the
   mode pays nothing (`free_exchange`). Procurement (purpose 6) is untouched;
   PL4-python pays it through `transfer_wealth`.
7. **Frame column names** are this lane's (the contract fixes only the tuple shape).
   They match PL4-python's `FRAME_COLUMNS`.
8. **`free_exchange`.** Mode 2 ignores the installed price: it runs at price 0 and
   records the installed one as `price_quoted_milli`.

The design's §5.1 named the outputs `retail_owned_<good>`, `retail_owned_decay` and
`retail_owned_overflow`. The binding contract's per-good names are used instead
(`retail_owned_close_<good>`, `retail_owned_decay_<good>`, `retail_owned_overflow_<good>`).
The design's food list is correct: grain, fish, salt, botanicals and exotic are exactly
`economy::IS_FOOD` (`RETAIL_FOOD_SLOTS`, checked by a test), in goods order.

### N1: economy (`economy.rs`, `ffi/mod.rs` `tick_economy`)

**Inputs** (economy region batch, all six Float32 columns or none):

| Column | Meaning |
| --- | --- |
| `retail_title_share` | θ in [0, 1]; null means not a pilot region |
| `retail_owned_<good>` for grain, fish, salt, botanicals, exotic | owned stock at opening, food units (milli ÷ 1000); finite and ≥ 0 in a pilot row; null or 0 elsewhere |

Refused before any change (`ValueError`): some but not all six columns, a non-Float32
column, θ outside [0, 1] or non-finite, a null, negative or non-finite owned value in a
pilot row, owned food in a non-pilot row, and any retail column outside the hybrid
economy (`set_hybrid_economy_mode(False)`; the core also asserts this). The parsing sits
after the L3 timber-cap columns, before any simulator mutation.

**Arithmetic in a pilot region** (`tick_economy_core_with_retail`; non-pilot regions
and absent inputs execute none of it):

- Opening (review D, B1): **before** sufficiency, the owned stock carried into the turn
  (`owned_open`, last turn's unsold) decays, and the per-good storage cap
  (`2.5 × storage_population`) is enforced once on both pools together
  (`RetailOpening`).
  - Salt preserves at the effective rate of the food on hand at opening (commons plus
    owned).
  - Where the commons plus the carried owned stock of a food good exceed the cap, both
    are cut pro rata to it: each keeps `pool × cap / (commons + carried)`.
    - The owned share of the overflow is `retail_owned_overflow_<good>`.
    - The commons share is in the ledger's cap-overflow term.
    - This applies in a pilot region even with nothing owned, so commons above the cap
      at opening are cut before consumption there, where a region without retail cuts
      them at close.
  - The commons are capped again at close, alone, as in every region.
  - This turn's title is not decayed or capped before it can be eaten. Like the commons,
    which decay only on what is left after consumption, owned food decays only on what
    was left unsold.
  - The cap therefore holds both pools together **at opening**. Between Phase 2 close
    and the next opening, a pilot region may hold up to one turn's harvest above the
    cap: this turn's title, plus the commons' growth since the opening cut (themselves
    capped at close). Phase 10 procurement or a conquest can reach that stock.
- Phase A: the commons and the carried owned stock after the opening (decay and cap)
  are food `available`, so pre- and post-trade prices, `market_supply_food` and the farmer income
  modifier see all food on hand. The oracle shadow's food on hand also includes it.
- Step 1: `titled[g] = production[g] × θ` for each food good. The commons accumulate
  `production − titled` (plus net mobility, minus craft input, clamped as before).
  `owned = carried + titled`.
- Step 2: `food_sufficiency = (commons + owned) / demand`, clamped 0–2
  (availability). `commons_sufficiency` is the same over the commons alone. Sufficiency,
  and so `cf`, counts exactly the owned food offered at 0.7 (`owned_close`).
- Step 3: the draw-down takes the commons only (`commons_consumed`, equal to
  `food_consumed`).
- Steps 4 and 5: the commons decay (salt preservation over commons plus owned on hand)
  and are capped, exactly as in a region without retail. Owned stock is not touched
  again this turn.
- Food ledger: opening and closing include owned stock. Storage loss and cap overflow
  include the owned decay and both opening overflows. The ten-term balance still closes.
  The opening losses precede `food_pre_consumption`, so in a pilot region
  `pre_consumption = opening + produced + transport − craft + clamp − owned decay −
  owned overflow − commons opening overflow`.
- With nothing withheld, the free food and the owned food on offer cover `cf` for
  everyone alive (`free_living + offered ÷ ration ≥ cf × persons`, within Python's
  whole-milli rounding).
- `stockpile_<good>` and the observability `stockpile_food` are the commons only.

**Outputs** (appended to the region result batch only when the inputs were present;
null for non-pilot rows):

| Column | Type | Meaning (food units) |
| --- | --- | --- |
| `retail_titled_<good>` | Float32 | θ × this turn's production of the good |
| `retail_owned_close_<good>` | Float32 | owned stock after decay and cap |
| `retail_owned_decay_<good>` | Float32 | storage decay of the carried owned stock, at opening (before sufficiency) |
| `retail_owned_overflow_<good>` | Float32 | the carried owned stock's share of the combined cap overflow at opening (the commons share is in the ledger's cap term) |
| `commons_consumed` | Float64 | the draw-down, all from the commons (= `food_consumed`) |
| `commons_sufficiency` | Float32 | pre-consumption commons ÷ demand, clamped 0–2 |

Identity: `owned_close = owned_open + titled − owned_decay − owned_overflow` per good
(f32). Order: 20 per-good columns (titled, owned_close, owned_decay, owned_overflow,
each for grain, fish, salt, botanicals, exotic), then `commons_consumed` and
`commons_sufficiency`.

### N2: provisioning and wealth

**FFI** (`AgentSimulator`; food in milli-food, money in milli-units):

```text
set_household_retail(source_turn: u32, mode: u8, regions: Vec<(u16, i64, f64)>,
                     claims: Vec<(u32, u16, i64)>) -> None
cancel_household_retail() -> bool
take_household_retail_frame() -> Option<(u32, Vec<String>, Vec<Vec<f64>>,
    Vec<(u32, u16, i64, i64)>, Vec<(u32, i64, i64, i64)>,
    Vec<(u32, u16, u32, f32, f32, u8)>, usize)>
install_retail_income(turn: u32, regions: Vec<u16>) -> None
cancel_retail_income() -> bool
take_retail_income_receipt() -> Option<(u32, Vec<(u32, f32)>)>
wealth_transfer_purposes()[5] == "food_purchase", [6] == "food_procurement"
```

- `regions`: (pilot region, price in milli-units per ration, free rations from the
  commons draw-down and the release, for the Phase 2 population).
- `claims`: (owner stable id, pilot region, milli-food), at most one per
  (owner, region).
- Modes: 0 `retail`, 1 `no_relief`, 2 `free_exchange`.
- `set_household_retail` validates everything before any change. It refuses a pending
  install, a mode above 2, a region out of range or repeated, a price outside
  0..=10⁹, non-finite or negative free rations (at most 10⁹), owner id 0, a claim outside
  the listed regions, a negative claim (at most 10¹²), a repeated (owner, region) and
  more than 2²⁰ claims. Installing drops an untaken frame.
- `install_retail_income` refuses a pending install, a region out of range and a
  repeated region. Installing drops an untaken receipt.
- Every frame and receipt is taken once and carries its source turn.

**Phase 0.5** (`wealth_tick`): for an alive `Occupation::Farmer` in a listed region, the
ordinary farm income left after the teaching, learning and paid-work deductions is set
to zero; health loss then multiplies zero.
- The receipt records the income the farmer would actually have received: that
  remainder after this turn's health loss, `income × (1 − loss)` (review D, m1). Health
  loss also reduces the farmer's title, through the title weights.
- The receipt has one row per such farmer, including zero rows: `(id, replaced)` in
  slot order.
- Non-farmers and other regions are unchanged, and so is the L6a paid-work receipt.
  The care observer's pre-health base income reads the zero.

**Phase 0.7** (`provisioning::retail`, right after L2's allocation, before L7's ration
observation and needs). Per pilot region:

- Households are derived as L2 derives them; people are sorted by id. A claim whose
  owner is not alive (stable-id guard against slot reuse) is *withheld* and takes no
  part in the rounds. A living owner's claim is *present* when the owner is in the
  region; otherwise it is only for sale.
- `cf = min(1, regional sufficiency)`. Payers are a household's adults, or with no adult
  its members. Cash is the payers' wealth in whole milli. A household can afford
  `floor(cash × ration / price)` milli-food (unlimited at price 0).

1. **Free pool.** The living's share is `free × min(N, N2) / N2`; the rest is
   unallocated, as in L2.
   - Modes 0 and 2: a household is means-tested when its gap to `cf` after its own food
     (projected children first) exceeds what its cash buys. Its members are
     water-filled first, each to `cf` counting that own food. Then everyone is
     water-filled the same way, then to one ration.
   - Mode 1: L2's configured regime (equal, floor_means, targeted_relief, with L2's floor,
     target share and pre-release split) on the free pool, with no means test.
2. **Fair-share round, own food.** Each household eats its present claims up to `cf` per
   member, children first. Claims are debited pro rata to what remains (largest
   remainder, ties by owner id).
3. **Fair-share round, purchases.** Demand is the members' gap to `cf`, limited by what
   the household's cash still buys; a household limited here is *cash-limited*.
   - A short offer is split pro rata to demand (largest remainder in milli-food, ties
     by household key).
   - Otherwise sellers sell pro rata to their remaining claims (ties by owner id).
   - Bought food goes to children first.
4. **Open round.** Own food, then purchases (same rules), up to one ration.
5. **Rations** (free + (own + bought) ÷ ration) go to `food_access` for every pilot
   person. A ration within one milli-food of a full ration is full (the fed tolerance;
   review D, M1). A full ration reads the regional signal where the region is not short
   (abundance kept) and 1.0 in a short region. Anyone below reads their ration. People
   outside the pilot regions keep L2's rations and ids bit for bit.

Statuses, in order:
- **0 fed:** within one milli-food of `cf`;
- **1 priced out:** the household's fair-share purchases were cash-limited (this takes
  precedence when the offer was short too);
- **3 withheld dead:** a dead owner's claim was withheld in the region (the one
  remaining way a fair share can be out of reach);
- **2 offer short:** otherwise.

**Payments** (`wealth_transfer::settle_food_purchases`, once per tick, not in mode 2):

- A household pays `ceil(bought × price / ration)` milli; its cash always covers this.
- Debits fall on the payers in proportion to their wealth, by largest remainder, ties
  by id. A payer never goes below zero.
- A region's payments are credited to its sellers in proportion to milli-food sold
  (ties by id), by stable id wherever they live, up to each seller's ceiling room.
- What the ceiling refuses is refunded to that region's payers in proportion to what
  they paid. Every seller is alive (a dead owner's claim is withheld); a sale by nobody
  living is a logic error (the settlement panics).
- Each person's net change is applied once.
- `paid == credited + refunded` and `refunded == refused_ceiling` exactly, per region
  and over the money rows.

**Frame.** Region rows, in `RETAIL_REGION_COLUMNS` order. Food is in milli-food, money
in milli-units, rations as fractions of one ration.

| Column | Meaning |
| --- | --- |
| `region`, `mode` | pilot region index, mode |
| `phase2_alive`, `persons`, `households`, `children` | L2's Phase 2 count; the living provisioned, their households and children |
| `sufficiency`, `fair_share` | regional sufficiency; `cf` |
| `price_quoted_milli`, `price_milli`, `milli_food_per_ration` | installed price; price charged (0 in mode 2); ration size |
| `free_rations`, `free_living`, `free_given`, `free_unallocated` | installed free rations; the living's share; placed; `free_rations − free_given` |
| `free_to_priority`, `priority_households` | free food placed in the means-tested stage; households tested in |
| `claims`, `present_claims`, `offered_milli` | claims in the region; those whose living owner is present; their total at the start, as installed |
| `withheld_dead_claims`, `withheld_dead_milli` | claims whose owner was not alive at 0.7, and their milli-food: neither offered nor eaten, part of `unsold_milli` |
| `own_eaten_milli` (`_fair_milli`, `_open_milli`) | own food eaten, total and by round |
| `sold_milli` (`_fair_milli`, `_open_milli`) | food sold, total and by round |
| `unsold_milli` | claims left after the open round |
| `demand_fair_milli`, `demand_open_milli` | cash-limited demand in each round |
| `buying_households`, `sellers` | households that bought; claims that sold |
| `paid_milli`, `credited_milli`, `refunded_milli` | money moved |
| `refused_ceiling_milli` | the cause of refunds: credits above a seller's ceiling room |
| `rations`, `fed_fair`, `full_ration`, `min_ration`, `max_ration` | person rations: sum, at `cf`, at one ration, extremes |
| `deficit` | Σ (`cf` − ration) over people not fed, = `priced_out_deficit + offer_short_deficit + withheld_dead_deficit` |
| `priced_out_households`, `_persons`, `_children`, `_deficit` | cash-limited shortfall |
| `offer_short_households`, `_persons`, `_children`, `_deficit` | shortfall without a cash cause or a withheld claim |
| `withheld_dead_households`, `_persons`, `_children`, `_deficit` | shortfall without a cash cause where a dead owner's claim was withheld (status 3) |

Other frame fields:

- **Claim rows** `(owner, region, own-eaten milli-food, sold milli-food)`: every
  installed claim, by (region, owner).
- **Money rows** `(id, paid, credited, refunded)`: every payer and seller (a dead
  seller reads zeros), ascending id. A person's net is `credited + refunded − paid`.
- **Sample** `(id, region, household key, ration, fair share, status)`: at most 256
  people, those not fed first, then the fed, each by (region, id). Then the count
  dropped.

Region identities:

- `free_given + free_unallocated = free_rations`.
- `own_eaten + sold + unsold = offered`, with `withheld_dead ≤ unsold`.
- `rations = free_given + (own_eaten + sold) / ration`.
- `fed_fair + priced_out_persons + offer_short_persons + withheld_dead_persons = persons`.
- Per claim, `own_eaten + sold ≤ claim`; a withheld claim reads `(owner, region, 0, 0)`.

L2's own frame is computed and returned unchanged for pilot regions too, including its
sample. PL4-python's seam leaves pilot regions out of L2's closure.

**Pool.** Four fields, all in the `transient { … }` list: `retail_config`,
`retail_frame`, `retail_income`, `retail_income_receipt`. There is no persisted
field, no schema-string change and no checkpoint change.

### Tests (all on this branch)

| Command | Result |
| --- | --- |
| `native_slot.sh env CARGO_TARGET_DIR=…/target-r-test CARGO_BUILD_JOBS=2 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --manifest-path chronicler-agents/Cargo.toml` | 1,303 passed, 0 failed, 2 ignored (pre-existing), 40 suites, 0 warnings (on `claude/hr-native-cap`) |
| … `--test test_household_retail_economy` (N1) | 10 passed: absent and all-null inputs keep every output's bits, non-pilot regions untouched, θ = 1 commons-only draw-down, carried owned stock in sufficiency, supply, price and oracle, opening decay (title never decayed) and the combined opening cap on both pools, review D's cap case over ten turns (every opening holds at most the cap; fails on `4fac1537`, where turn 1 opens at 10.94 against 10), ledger and world conservation, zero-production and empty regions, woodcut crews with retail, abstract path refused |
| … `--lib provisioning` (N2) | 26 passed (8 L2, 18 retail): adds review D's abundance case (a 0.9993 ration reads the signal), a household selling in the fair round and buying in the open round, cash and offer binding together (priced out), the withheld_dead status, the retail refusal on a consumed key, the tick checks of the key and the income regions |
| … `--lib wealth_transfer` | 23 passed: adds settlement once per turn and the post-health income receipt |
| … `--test test_household_retail_tick` | 4 passed: adds the `cf` invariant from the real Phase 2 split over six cases (fails on `30dc547f`: 36.98 rations on offer against a need of 38.0), and two consecutive retail ticks |
| `PYTHONPATH=src ~/.venvs/native-hrn/bin/python -m pytest tests/test_household_retail_native_ffi.py` | 6 passed; adds a 30-turn template seed 7 run, every controlled region a pilot: 98 short pilot region-turns (1,810 person-rows), none offer short, smallest margin −0.0023 rations (Python's whole-milli rounding) |
| `CHRONICLER_REQUIRE_RETAIL_NATIVE=1 … pytest tests/test_household_retail*.py` (`native-hrn`) | 91 passed, 0 failed (including the `cf` invariant on the development world and the offline opening-cap test of `_title_region`) |
| `python scripts/run_python_oracle_checks.py` (offline lane) | FAIL at chunk 6 `academy-service-contracts`: the academy witness test below (first five chunks pass); expected until the lead's witness layers |
| `pytest tests/test_native_ci_shards.py` (offline) | 210 passed, with the new module enrolled in shard 1 |

What the retail N2 tests cover:

- fair-share then open round;
- own food first within `cf`, children first;
- short-offer pro-rata split by largest remainder;
- adult payers and child-only payers;
- the wealth floor and the ceiling refund;
- a dead owner's claim is withheld whole (neither sold nor eaten, though buyers with cash want it) and a dead buyer is skipped; on `2a962374` that claim was sold;
- a reused slot is ignored;
- non-pilot regions keep L2's rations under all three regimes;
- the means test and `no_relief`;
- `free_exchange`;
- an abundant region;
- closure in a mixed world (couples, children, dead and absent owners, two pilot
  regions, all three modes);
- install validation.

The real-extension test (`tests/test_household_retail_native_ffi.py`, native shard 1)
uses template seed 7:

- Economy columns:
  - title closes per good, and the ledger closes;
  - supply includes owned food;
  - all-null inputs keep the bits of all five batches;
  - refusals happen before any change.
- The chain:
  - Python's part is played inline: title split equally over the pilot farmers, an
    absent owner's claim added, and a labelled stress of no opening commons;
  - the frame and receipt are taken once;
  - food and money close: 6,873 milli-food sold and 5,799 milli paid and credited;
  - 28 farmers' income is replaced;
  - against a control run, 219 of 223 people's wealth differs by exactly the settled
    money minus the replaced income × (1 − decay); the four excluded died or inherited.
- The purchase key is consumed, and the next tick runs neither step.
- The tick refuses retail without L2, or installs for another turn.

Existing suites run unchanged on this build, except two assertions in
`tests/test_recovery_skills_native.py` that pinned the five-purpose list (now the
seven appended codes). 374 + 28 passed:

- `test_food_allocation{,_native}`, `test_workshop_payroll{,_native}`,
  `test_remittances{,_native}`;
- `test_economy`, `test_economy_bridge`, `test_economy_coupling`, `test_economy_m43a`,
  `test_economy_m43b`, `test_economy_oracle`;
- `test_production_ledger{,_native}`, `test_food_accounting{,_native}`;
- `test_relocation_costs{,_native}`, `test_livelihoods_closure_native`;
- `test_crafts`, `test_bulk_trade`, `test_mutual_aid`;
- `test_recovery_skills_native`, `test_apprenticeship_native`,
  `test_repair_projects_native`, `test_livelihoods_work_authority_native`,
  `test_local_budgets_native`.

### Pinned edits (lead witness layers)

Edited pinned files:

- `economy.rs`: retail types, a wrapper keeping `tick_economy_core_with_granary_work`,
  and the guarded steps.
- `ffi/mod.rs`: input columns after the L3 caps, the core call, result columns appended
  after the static-schema batch, six methods, and two tick checks.
- `tick.rs`: three lines in `wealth_tick` and the 0.7 call inside L2's block.
- `pool.rs`: four transient fields.

`provisioning.rs` and `wealth_transfer.rs` carry no enforced pin. Each pinned edit is a
contiguous insertion, apart from small in-place changes in `economy.rs` steps 1, 2 and 5
and the core call and `use` line in `ffi/mod.rs`.

Seven witness tests fail until the lead adds layers. With the base versions of those
four files restored they pass (83 passed):

- `test_academy_candidate_witness::test_academy_candidate_projects_exact_reviewed_sources_and_rejects_mutations`
- `test_crisis_candidate_witness::test_candidate_projects_exact_reviewed_sources_and_rejects_mutations`
- `test_food_accounting_witness::test_food_layer_projects_exact_source_and_rejects_mutations`
- `test_health_care_policy::test_care_codec_source_binding_preserves_reviewed_native_and_python_phase_witnesses`
- `test_household_mobility_witness::test_household_candidate_projects_exact_reviewed_sources_and_rejects_mutations`
- `test_livelihoods_sprint_witness::test_projection_reaches_each_layer_parent_and_the_baseline`
- `test_livelihoods_sprint_witness::test_mutations_are_rejected_in_strict_mode_and_passed_on_otherwise`

### Integration check against PL4-python (not committed)

A scratch merge with `origin/claude/pl4-retail-python` `5a2ff552` was run against this
extension:

- Conflicts were only in `native_shards_manifest.json` and `test_native_ci_shards.py`,
  where both lanes append.
- Its `tests/test_household_retail_native.py` passed 18 of 19.
- `test_granary_procurement_pays_owners_by_id` fails: on that trajectory the pilot
  regions' owned stock stays at 0–32 food units, against a four-turn keep of 6–112, so
  no owned surplus is ever procured. This is the test's scenario expectation, not a
  native defect found here.

### Open risks

- A dead owner's food is unavailable to the hungry in the tick of the death (withheld
  for the heirs; deviation 4). The heirs can eat or sell it from the next tick.
- Means-test detail: priority members are filled to `cf` counting their projected own
  food. The free pool then reaches owners last, and owners' freed food is sold to others.
- Payment rounds up per household (at most 1 milli above `bought × price`). Sellers
  share the region's total by largest remainder.
- Owned food decays with the commons at the same salt-adjusted rate. The overflow split
  rounds in f32; Python applies the native figures to claims.
- In a pilot region, L2's frame still reports L2's rations; only the retail frame
  describes what pilot people ate.
- No checkpoint or resume test exists natively: there is no persisted state, and the
  installs are one-tick.

## Viewer (PL5b)

Lane PL5b, `claude/pl5b-retail-viewer` from `claude/household-retail` `fdc1dfbc`. The
viewer reads only `snapshot.livelihoods.household_retail`, the completed turn's copy
written by `snapshot_summary`; it never reads final-world state.

### Reader

`viewer/src/lib/householdRetail.ts`, `readHouseholdRetail(snapshot, regionCount)`:
absent, malformed (with the reason), or a dated record. It refuses a record whose
schema, stage, mode or boundary is unknown, whose `source_turn + 1` is not the
snapshot's turn, or whose θ is not 1 exactly in `no_relief`. Of the Accounting identities,
it checks those the frame carries:

- **Owned pool, per region** (totals; the frame has no per-good flows):
  `close = open + titled − own_eaten − sold − procured − decay − overflow − war_loss −
  to_commons + inherited_in − inherited_out`, `Σ goods_close = close`, owners exactly when
  there is owned food, inheritance conserves claims, `to_commons` equals its reasons, the
  title equals the Phase 2 `retail_titled_<good>` columns (within one milli a good), and
  the decay and overflow applied do not exceed what the economy reported.
- **Provisioning, per region**: the row is the region's, in the record's native mode;
  price and free rations equal the install; the claims debited equal `own_eaten_milli`
  and `sold_milli`; `free_given + free_unallocated = free_rations`; `own_eaten + sold +
  unsold = offered`; the fair-share and open rounds add up; `withheld_dead_milli ≤ unsold`;
  `rations = free_given + (own_eaten + sold) / ration`, each ration at most one;
  `fed_fair + priced_out + offer_short + withheld_dead = persons`; children and households
  within their persons; `deficit` is the sum of the three causes; `paid = credited +
  refunded`, `refunded = refused_ceiling`, and `sold × price ≤ paid × ration ≤ sold × price
  + buying_households × ration`. `free_exchange` charges nothing and prices nobody out.
- **The turn**: money rows equal the region totals and balance; granary credits close
  (`owed = credited + refused + unpaid`; `free_exchange` pays nothing, the other modes
  leave nothing unpaid) and exist exactly when owners' grain was procured; the income
  receipt equals the regions' income plus the unattributed (`free_exchange` and
  `record_only` replace none); `record_only` holds, sells and prices nothing; the person
  sample is bounded and names provisioned regions; the record log is ordered.
- **Lifetime**: `paid = credited + refunded`.

It cannot check the per-good pool, per-owner claims, the native food ledger, the price
formula or the per-person cash limits; Python and the native lane check those.

Missing data is unknown, never zero. `regions` null (with `money`, `income`, `sample`
and `sample_dropped`; a partial blank is refused) reads "not recorded … unknown, not
zero". A region without a provisioning row (it left the pilot before the install, or the
tick took no install) reads "not provisioned": its people were fed by L2's rule and are in
the food allocation section. A flow the writer leaves out is zero only because the closing
identity holds without it. Lifetime counters the writer has never bumped read zero.

### Panel

`viewer/src/components/systems/HouseholdRetail.tsx`, on the Livelihoods tab after Food
allocation, headed `Household retail · snapshot N`, its first note naming simulation turn
N − 1. In this order:

1. The mode, labelled plainly (`retail`; `no_relief (what relief protects)`;
   `free_exchange (ownership without cash)`; `record_only (identity control, nothing
   applied)`), the boundary (`market`, `paid_work` with its four sources, `all`), θ and the
   commons share, the price band and the claims cap.
2. **People below their fair share**, first: persons and children provisioned, then each
   cause someone was short of (priced out, offer short, withheld for heirs) as children,
   persons and households with the deficit in rations, and "Nobody was …" for the others.
   A table per region with someone short (a column per cause present), and the person
   sample of those not fed (bounded at 24; the region counts are complete).
3. **Owned food** per pilot region: open → close (owners); the title with what was titled
   but kept commons and the derived commons share (1 − θ of the harvest); own food eaten,
   sold, unsold; free food given of the free rations; decay and overflow; sold to
   granaries and conquest loss; to commons by reason (no heir, left the pilot, claims cap,
   no farmer, pool rebuilt); inherited. A region that joined or left this turn says so.
4. **Food money** per pilot region: price a ration ("not charged" in `free_exchange`);
   paid, credited, refunded; farm income replaced with its farmers ("kept" in
   `free_exchange`); merchants' commons food and the owned food they could not load,
   labelled as an upper bound on foregone departures, not a measured loss.
5. Granary purchases of owners' grain and their credits; the turn's records (openings,
   closures, conquest losses, inheritance, escheat, pool resets); lifetime totals; recent
   pilot records.

`record_only` shows the would-be title, owners of farmers, the untitled share and the
would-be price instead of tables 2–4.

### Options

`--household-retail`, `--household-retail-mode` and `--household-retail-boundary` come
from the served `feature_catalog` (no viewer or `live.py` code is specific to them), off
by default, disabled until `--food-allocation` (and hybrid agents in Batch Lab), modes
hidden until the switch is on, defaults not sent. `viewer/src/__fixtures__/featureCatalog.json`
is regenerated from this branch. The boundary's help now names all four `paid_work`
sources (`livelihoods._HELP`; it named only firms and repair crews).
`tests/test_feature_catalog.py::test_household_retail_is_offered_and_forwarded_with_its_options`
checks a live start (namespace, world mode and boundary, manifest) and a Batch Lab
request (namespace and manifest), and the refusal without `--food-allocation`.

### Tests and fixtures

- `viewer/src/__fixtures__/household_retail_natural_records.json`: eight records written
  by this branch with the extension `b8a09339…` (development seeds; commands in its
  `note`): template 7 in each mode, template 11 boundary `all`, procedural 13 (a conquest
  loss), template 7 `paid_work` with crews, and before any paid work.
- `viewer/src/lib/__tests__/householdRetail.test.ts`: every natural record reads; each
  identity above is refused when broken; blanked frames read unknown; constructed
  records (labelled) with a refund, an offer shortfall and a pilot closure read.
- `viewer/src/components/systems/__tests__/HouseholdRetail.test.tsx`, and household
  retail cases in `featureCatalog.test.ts` and `FeatureOptions.test.tsx`.

### Browser QA

`viewer/scripts/qa-household-retail.mjs` (opt-in; Playwright and Chromium): the panel
at 1440 and 390 px over real bundles, each stop checked against the turn's record read
with `chronicler.bundle_codec`; old bundles without the key; a constructed variant with
absent, malformed, blanked and null records, rewound through; a live session with the
setup options, pause, rewind, checkpoint, resume and fork; Batch Lab options and
cancellation. Batch Lab runs consecutive seeds from its start seed and stops only
between seeds; no two template development seeds are consecutive, so the QA cancels a
one-seed batch (template 7) and records the manifest's status (`complete`) rather than
requiring `cancelled`.

Run on 2026-11-06 (production build of this branch, extension `b8a09339…`), with the
seven development bundles of the fixture's runs as `--bundle` and two old bundles
(template 7 with `--food-allocation`, one written by `main` `573f14e5` and one by this
branch without the switch): bundles 713/713, old 194/194, live 71/71, batch 15/15
checks, no console or page errors. The live world (template 7, boundary `all`) had seven
pilot regions at turn 5; the resumed session matched the paused one there. The fork
(`--seed 9`) rebuilt the native pool, and its panel shows the dated `pool_reset` records
of turn 5. The batch manifest recorded `food_allocation`, `household_retail`,
`free_exchange` and `paid_work` for seed 7 only, status `complete`.
