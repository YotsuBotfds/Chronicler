# Household food retail (L6b, `--household-retail`, default off)

Package PL4 of the phase "productive recovery and household livelihoods"
([plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2: the lead's
decisions and the binding FFI contract). Design and measurements:
[household-retail-design.md](household-retail-design.md). The Python and Accounting
sections belong to lane PL4-python; this page's **Native** section is lane PL4-native's
(branch `claude/pl4-retail-native`) and is meant to sit beside them.

## Native

### Build identity

- Source: `claude/pl4-retail-native` at `81d9743b`. The Rust tree is unchanged after
  that commit (later commits touch only this page).
- Extension built with `/home/user/wt/tools/build_native.sh` into `~/.venvs/native-pl4`
  (CPython 3.13, release, `--locked`), checked by `check_python_env.py --expect
  native`: compiled submodule, real `AgentSimulator`, `EcologySimulator`,
  `PoliticsSimulator`.
- `chronicler_agents.cpython-313-x86_64-linux-gnu.so` SHA-256
  `eda66ae888cac32dba5fe3e806d84afb168324ddaeb5c0f742518140d157c0d5`.
  An earlier build at `a7436b65` (`3f248402…`) differs only in the frame's column names.

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
   install for another turn.
4. **Dead sellers.** An owner who died after Phase 2 still sells. The credit has no
   living holder, so it is refunded to that region's buyers, like a ceiling refusal
   (`refused_dead_milli`). The food is delivered; the estate gets no revenue. If the lead
   wants estates paid, a seller-credit receipt or an estate row is needed.
5. **Ceiling room.** A seller's room below `MAX_WEALTH` is measured before the tick's
   purchases. A person who both buys (in one region) and sells (in another) therefore
   gets no extra room from their own payment. This removes a refund/credit circularity
   and keeps every refund within what the buyer paid.
6. **Key consumed.** The in-tick settlement consumes the wealth-transfer key
   `(turn, food_purchase, batch 0)`; a replay `transfer_wealth(turn, 5, 0, …)` is
   refused. Procurement (purpose 6) is untouched; PL4-python pays it through
   `transfer_wealth`.
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

- Phase A: owned food is added to food `available`, so pre- and post-trade prices,
  `market_supply_food` and the farmer income modifier see all food on hand. The oracle
  shadow's food on hand also includes it.
- Step 1: `titled[g] = production[g] × θ` for each food good. The commons accumulate
  `production − titled` (plus net mobility, minus craft input, clamped as before).
  `owned = owned_open + titled`.
- Step 2: `food_sufficiency = (commons + owned) / demand`, clamped 0–2
  (availability). `commons_sufficiency` is the same over the commons alone.
- Step 3: the draw-down takes the commons only (`commons_consumed`, equal to
  `food_consumed`).
- Step 4: salt preservation is computed over commons + owned. Owned stock decays at
  the same effective rate as the commons.
- Step 5: the per-good cap (`2.5 × storage_population`) holds commons + owned. The
  overflow is split pro rata: owned keeps `owned × cap / total`, commons the rest.
- Food ledger: opening and closing include owned stock. Storage loss and cap overflow
  include owned decay and overflow. The ten-term balance still closes.
- `stockpile_<good>` and the observability `stockpile_food` are the commons only.

**Outputs** (appended to the region result batch only when the inputs were present;
null for non-pilot rows):

| Column | Type | Meaning (food units) |
| --- | --- | --- |
| `retail_titled_<good>` | Float32 | θ × this turn's production of the good |
| `retail_owned_close_<good>` | Float32 | owned stock after decay and cap |
| `retail_owned_decay_<good>` | Float32 | owned storage decay |
| `retail_owned_overflow_<good>` | Float32 | owned share of the cap overflow |
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
ordinary farm income left after the teaching, learning and paid-work deductions is
recorded and set to zero; health loss then multiplies zero. The receipt has one row per
such farmer, including zero rows: `(id, replaced)` in slot order. Non-farmers and
other regions are unchanged. The L6a paid-work receipt is unchanged. The care
observer's pre-health base income reads the zero.

**Phase 0.7** (`provisioning::retail`, right after L2's allocation, before L7's ration
observation and needs). Per pilot region:

- Households are derived as L2 derives them; people are sorted by id. A claim is
  *present* when its owner is alive in the region (stable-id guard against slot reuse);
  otherwise it is only for sale.
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
   person. A person at a full ration reads the regional signal where the region is not
   short (abundance kept) and 1.0 in a short region. Anyone below reads their ration.
   People outside the pilot regions keep L2's rations and ids bit for bit.

Statuses: *fed* when within one milli-food of `cf`; otherwise *priced out* if the
household was cash-limited, else *offer short*.

**Payments** (`wealth_transfer::settle_food_purchases`, once per tick, not in mode 2):

- A household pays `ceil(bought × price / ration)` milli; its cash always covers this.
- Debits fall on the payers in proportion to their wealth, by largest remainder, ties
  by id. A payer never goes below zero.
- A region's payments are credited to its sellers in proportion to milli-food sold
  (ties by id), by stable id wherever they live, up to each seller's ceiling room.
- What the ceiling refuses, and all of a dead seller's credit, is refunded to that
  region's payers in proportion to what they paid.
- Each person's net change is applied once.
- `paid == credited + refunded` and `refunded == refused_ceiling + refused_dead`
  exactly, per region and over the money rows.

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
| `claims`, `present_claims`, `offered_milli` | claims in the region; those whose owner is present; their total at the start |
| `own_eaten_milli` (`_fair_milli`, `_open_milli`) | own food eaten, total and by round |
| `sold_milli` (`_fair_milli`, `_open_milli`) | food sold, total and by round |
| `unsold_milli` | claims left after the open round |
| `demand_fair_milli`, `demand_open_milli` | cash-limited demand in each round |
| `buying_households`, `sellers` | households that bought; claims that sold |
| `paid_milli`, `credited_milli`, `refunded_milli` | money moved |
| `refused_ceiling_milli`, `refused_dead_milli` | the two causes of refunds |
| `rations`, `fed_fair`, `full_ration`, `min_ration`, `max_ration` | person rations: sum, at `cf`, at one ration, extremes |
| `deficit` | Σ (`cf` − ration) over people not fed, = `priced_out_deficit + offer_short_deficit` |
| `priced_out_households`, `_persons`, `_children`, `_deficit` | cash-limited shortfall |
| `offer_short_households`, `_persons`, `_children`, `_deficit` | shortfall without a cash cause |

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
- `own_eaten + sold + unsold = offered`.
- `rations = free_given + (own_eaten + sold) / ration`.
- `fed_fair + priced_out_persons + offer_short_persons = persons`.
- Per claim, `own_eaten + sold ≤ claim`.

L2's own frame is computed and returned unchanged for pilot regions too, including its
sample. PL4-python's seam leaves pilot regions out of L2's closure.

**Pool.** Four fields, all in the `transient { … }` list: `retail_config`,
`retail_frame`, `retail_income`, `retail_income_receipt`. There is no persisted
field, no schema-string change and no checkpoint change.

### Tests (all on this branch)

| Command | Result |
| --- | --- |
| `native_slot.sh env CARGO_TARGET_DIR=…/target-r-test CARGO_BUILD_JOBS=2 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --manifest-path chronicler-agents/Cargo.toml` | 1,282 passed, 0 failed, 2 ignored (pre-existing), 40 suites, 0 warnings |
| … `--test test_household_retail_economy` (N1) | 8 passed: absent and all-null inputs keep every output's bits (all five outputs, hybrid deliveries, cap, oracle), non-pilot regions untouched, θ = 1 commons-only draw-down, owned food in sufficiency, supply, price and oracle, salt across pools, pro-rata cap, ledger and world conservation with owned stock, zero-production and empty regions, abstract path refused |
| … `--lib provisioning` (N2) | 21 passed (8 L2, 13 retail) |
| … `--lib wealth_transfer` | 20 passed (largest remainder, settlement with ceiling and dead-seller refunds, income replacement after paid work consumed once, next phase ordinary, installs refused) |
| … `--test test_household_retail_tick` | 2 passed: the tick consumes both installs once; next tick runs neither; empty installs leave the tick bit-identical |
| `PYTHONPATH=src ~/.venvs/native-pl4/bin/python -m pytest tests/test_household_retail_native_ffi.py` | 4 passed |
| `python scripts/run_python_oracle_checks.py` (offline lane) | FAIL at chunk 6 `academy-service-contracts`: the academy witness test below (first five chunks pass); expected until the lead's witness layers |
| `pytest tests/test_native_ci_shards.py` (offline) | 210 passed, with the new module enrolled in shard 1 |

What the retail N2 tests cover:

- fair-share then open round;
- own food first within `cf`, children first;
- short-offer pro-rata split by largest remainder;
- adult payers and child-only payers;
- the wealth floor and the ceiling refund;
- a dead owner sells and a dead buyer is skipped;
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

- Dead sellers' revenue goes back to buyers, not to the estate (deviation 4).
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
