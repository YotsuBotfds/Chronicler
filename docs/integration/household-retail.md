# Household food retail (L6b, `--household-retail`, default off)

Package PL4 of the phase "productive recovery and household livelihoods"
([plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2, with the
lead's decisions and the binding FFI contract). Design and measurements:
[household-retail-design.md](household-retail-design.md). Requires `--agents hybrid`
and `--food-allocation` (L2, [food-allocation.md](food-allocation.md)).

This page has three parts: **Python** and **Accounting** (lane PL4-python) and
**Native** (lane PL4-native). Until both lanes are integrated, the Python package runs
only against a stand-in native in the offline tests; a real run with the switch on
refuses to install without the native retail methods.

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
| Phase 2, before the economy | `prepare_phase2` | Boundary update: a pilot region without a controller closes (holdings to the commons, `pilot_closed`); newly qualifying regions open. Commons written after the region batch was built (closure, pool reset) are patched into its `stockpile_<good>` columns. Title weights from the Phase 2 snapshot. Unless `record_only`, and only when a pilot region exists, appends `retail_title_share` (θ; null outside the pilot) and `retail_owned_<good>` (owned stock / 1000). |
| Phase 2, after the economy | `finish_phase2` | Title, once per turn: each good's `retail_titled_<good>` (to the nearest milli-food) split over the region's Phase 2 farmers by largest remainder, ties by ascending id. Then the native owned decay and overflow per good, applied to claims pro rata. Untitled and refused shares decay with the pool and then go to the commons. Records each pilot region's controller. |
| Before the agent tick | `before_agent_tick` | Conquest loss for a pilot region whose controller changed since Phase 2. Spouse of every owner (`get_agent_relationships`, one call per owner). Installs `set_household_retail(turn, mode, regions, claims)` and, except in `free_exchange`, `install_retail_income(turn, regions)`. |
| After the agent tick | `after_agent_tick` | Takes the frame and income receipt once, refuses a stale, repeated or partial pair, checks the frame, debits own-eaten and sold food from the claims, records money, then settles dead owners' claims. |
| Phase 10 | (seam in `tick_grain_reserves`) | Owners' grain sold to their ruler's granaries is debited from claims as it is bought. |
| Phase 10 | `phase10` | Credits those owners once (`transfer_wealth`, purpose 6), then closes the turn's frame. |
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
- `paid_work`: regions with an open L6a firm (`workshop_payroll.firms`) or a repair crew
  paid in RS2's last frame (`repair_projects.receipts` with `wages_milli > 0`; PL3's paid
  recovery crews pay through those receipts).
- `all`: every region whose controller rules at least one region.

### Title weights

For an alive farmer (`occupation == 0`) of a pilot region in the Phase 2 snapshot:
`w = u × (1 − h)` in integer micro-units. `u` is `cities.URBAN_FARM_LABOR[rank]` when
the farmer's settlement is a city of that region, else 1. `h` is this turn's health work
loss from the health plan (`world.health_care._prepared`, prepared just before):
the impairment for an eligible patient (adult rural farmer, not enlisted), the care
fraction for a caregiver. Children hold their own title. Opening stock, merchant
imports, convoy and granary grain stay commons.

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
  share escheats. A dead owner's claim is still offered in the tick that killed them.
  - Native estate order (`household.rs`): spouse first, then dependants anywhere, then
    all children anywhere. Python follows lead decision 6: children in the claim's
    region only, all ages, equally. The spouse case agrees. Child cases can differ;
    `tests/test_household_retail_native.py` counts them.
- **Migration.** The claim stays in the origin's pool. The owner sells it wherever they
  live and eats from it only when present.
- **Household split, rejoin, remarriage.** Claims are personal; households are never
  stored, so nothing is created or lost.
- **Conquest.** `v − floor(v × CONQUEST_STOCKPILE_SURVIVAL)` of each owned good is
  destroyed (`war_loss`), claims pro rata. Occupation and siege requisitions do not
  reach owned stock (declared limit, counted in `requisition_exempt_region_turns`).
- **Pool reset.** Every claim to the commons, dated.

### Granary procurement (pinned seam in `grain_reserves.py`)

- A pilot market's sellable surplus counts commons plus owned grain (only grain: owned
  fish, salt, botanicals and exotic do not count towards the market's keep).
- The owned part of that surplus is sold only to the owners' own ruler. A domestic
  purchase takes it first, pro rata to claims, in whole milli-food rounded up. A
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
`priced_out_persons`, `offer_short_persons`.

Other columns are kept in the frame as given.

### Snapshot

`livelihoods.household_retail` (stage `L6b`) for the completed turn: per pilot region
`open_milli`, `close_milli`, `goods_close`, owners, flows, commons by reason, price,
free rations, the native Phase 2 columns and provisioning row, plus money, income,
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
- **Provisioning**, per region:
  - `free_given + free_unallocated = free_rations`, and `free_rations` equals the
    install;
  - `own_eaten + sold = offered − unsold`;
  - `offered` equals the installed claims;
  - the claim rows sum to the region's `own_eaten` and `sold`;
  - `sum(person rations) = free_given + (own_eaten + sold) / ration`, each ration at
    most 1.
- **Claim rows.** Each names an installed claim once, and `own + sold` does not exceed
  it.
- **Money.** Per row, `paid`, `credited` and `refunded` are nonnegative and `refunded ≤
  paid`. `Σ paid = Σ credited + Σ refunded`, per region and over the rows, and the two
  totals agree. `free_exchange` moves no money.
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
