# Household food retail (L6b, option R): implementation design

Design lane D4 of the phase "productive recovery and household livelihoods"
([plan](../superpowers/roadmaps/productive-recovery-phase.md)), 2026-11-05. Design and
measurement only, on `main` `1ec0876e` with native extension `6c675042…`. The
measurement scripts and raw records lived in an ephemeral session scratch directory
and are not committed; section 14 describes the method. The lead's decisions on
section 15 are recorded in the phase plan, section 2 (PL4), and override this note
where they differ.

Labels used on every claim:

- **[code]**: read in the source at `1ec0876e` (file:line).
- **[measured]**: computed from development-world runs made for this note
  (template 1, 3, 7, 9, 11, 23, 42; procedural 32×10 seeds 7, 11, 13, 17, 21,
  31, 302, 303; 200 turns), either directly or through the no-feedback shadow
  of section 14. Every shadow number is first-order: it replays option R on a
  feature-off trajectory and does not let hunger, wealth or prices feed back.
- **[inferred]**: reasoning from code and measurement, not tested.

It builds on [household-purchases-design.md](household-purchases-design.md)
(option R, LEAVE OPEN), [food-allocation.md](food-allocation.md) (L2),
[grain-reserves.md](grain-reserves.md),
[workshop-finance.md](workshop-finance.md) (L6a) and
[remittances.md](remittances.md) (RS4). Domestic credit is not touched.

---

## 0. Recommended shape in one page

1. **Switch** `--household-retail` (default off), modes `retail` (default),
   `no_relief`, `free_exchange`, `record_only`. Requires `--agents hybrid` and
   `--food-allocation` (it extends L2's provisioning step).
2. **Pilot boundary**: declared per ruler, sticky (section 2). Recommended
   default `market`: each ruling civilization's capital region, kept until that
   region loses its controller. Alternative `paid_work`: regions that have had an
   open L6a firm or a paid RS2 crew.
3. **Title**: from the first pilot turn, the titled share θ of each pilot harvest
   (food slots and foraging; θ = 0.9, the other 0.1 stays commons) belongs to the
   region's Phase 2 farmers by stable id, in proportion to their farm work. Stock
   on hand at opening, merchant imports and convoy/granary grain stay commons.
4. **Owned inventory** lives in a Python per-region ledger keyed by stable id
   (`world.livelihoods.household_retail`), never in `region.stockpile`. No
   persisted native field and no checkpoint schema change: every native addition
   is transient.
5. **Phase 2** (native economy): owned food is passed in as optional columns; it
   counts in supply, prices and food sufficiency (availability), and it decays and
   is capped with the commons; the consumption draw-down takes **only commons**.
6. **Phase 0.5** (native wealth tick): pilot farmers' model farm income is
   replaced (set to zero, recorded); their cash income is sale revenue.
7. **Phase 0.7** (native provisioning): the commons draw-down and any granary
   release are allocated free (L2, means-tested first); then a **fair-share round**
   (owners' households eat their own food, others buy, everyone up to the region's
   free-allocation share), then an **open round** up to one ration. Buyers pay from
   adults' wealth (a household with no adult from its own members'), sellers are
   credited by id, all in whole milli-units, in the tick.
8. **Price**: the economy's own post-trade food price, clamped to the farm-earnings
   band [0.5, 3.0] (the farmer income modifier's floor and cap), times the
   per-capita ration (0.5). Measured median 0.35–0.52 wealth per ration.
9. **Merchants** load only commons (they cannot see owned food). **Granary
   procurement** buys owners' unsold grain through one pinned seam and pays them
   by id.
10. **Relief default**: L2 free allocation of all commons, granary release always
    free, a 10% harvest share kept commons, means-tested ordering, child-only
    households paying from their own wealth. Measured effect: cash-limited
    households below their free-allocation share fall from 4.7% to 0.7–0.9% of
    household-turns (section 9).

What the numbers decide: retail touches about a quarter of the food (owners'
households eat ~70% of it themselves); farm income replacement at the economy price
pays farmers 1.1–1.3× what they lose; the people at risk are mostly children
without an adult in the region and a thin tail of poor non-farm households. RS4
remittances equal 16–22% of what pilot households spend on food and cut
cash shortfall by about a seventh (a fifth to a quarter in firm regions); L6a and RS2 wages are
about 0.5% of food spending on these worlds, too small to change food access until
paid public work scales up (section 9.1).

---

## 1. Measured baseline

Base arm: `--agents hybrid --grain-reserves --public-grain-shipments --food-allocation
--food-allocation-regime equal`. All-switch arm adds `--scholarship --techniques
--academy-services --grain-storage --workshops --workshop-payroll --repair-projects
--remittances`. Person-turn weighted, controlled populated regions, turns 20–199
unless stated. **[measured]**

| Quantity | Template (7 worlds) | Procedural (8 worlds) |
| --- | --- | --- |
| Alive persons per world at turn 199 (8 / 32 regions) | 108–196 | 424–742 |
| Farmers among persons | 52% | 54% |
| Children among farmers (age < 20, occupation Farmer) | 43% | 48% |
| Food produced per farmer (median region-turn) | 0.53–0.90 food (1.1–1.8 rations) | 0.76–0.92 food |
| Model farm income per farmer per turn (median) | 0.22–0.28 | 0.18–0.25 |
| Short person-turns (post-release sufficiency < 1), by world | 25–67% | 22–54% |
| Closing food stock in turns of demand (median) | 0–0.6 | 0–0.9 |
| Ration price, economy (clamped) p10 / p50 / p90 | 0.25 / 0.52 / 1.50 | 0.25 / 0.35 / 1.07 |
| Ration price, cost rule p10 / p50 / p90 | 0.05 / 0.14 / 0.49 | 0.04 / 0.10 / 0.33 |
| Procurement grain taken from markets ÷ food harvest | 1.9% (0.4% all-switch) | 1.1% (0.4%) |

Purchasing power, `cover` = adults' post-tick wealth ÷ (members × ration price),
i.e. turns of full rations the household's cash buys (every 5th turn): **[measured]**

| Households | Share of persons | cover p10 / p50 | cover < 1 turn |
| --- | --- | --- | --- |
| with an adult farmer | — | 3.3–3.5 / 11.4–11.9 | 0.6–0.8% |
| non-farm, with an adult | — | 4.7–4.8 / 19–20 | 0.1–0.3% |
| **child-only** (no living adult parent in the region: L2's household of one) | **8.6% tpl, 11.6% proc** (30% / 36% of all children) | no adult wealth; own wealth median 1.5–1.9 | 100% by the adult-payer rule |

So, with cash alone, almost every household that contains an adult can buy a turn
or more of food at the economy price. The exposed group is structural: children
whose L2 household has no adult (orphans and children whose parents live
elsewhere). The economy counts most of them as farmers and pays them farm income
(`tick.rs:1545-1552` does not test age) **[code]**, so they hold some wealth.

---

## 2. Pilot boundary

The hard parts (title, consumption timing, income replacement, owned inventory) do
not shrink with the boundary **[inferred, as the earlier note found]**; the
boundary only bounds where behaviour changes and how much evidence is needed.

| Boundary | Person-turns covered (of all controlled) | Present in | Cash-limited hh below fair share, adults pay | … child-only households pay too | … with the relief default |
| --- | --- | --- | --- | --- | --- |
| all controlled regions | 100% | every world | 7.7% tpl / 8.2% proc | 4.7% / 4.5% | 1.0% / 0.7% |
| capital region per civ | 45% tpl / 43% proc | every world | 5.9% / 6.9% | not run | not run |
| regions with an open L6a firm (sticky) | 22% tpl / 7% proc | 7 / 7 tpl, 6 / 8 proc | 5.3% / 5.6% | 2.6% / 1.8% | 0.2% / 0.1% |
| firm or paid RS2 crew (sticky) | 22% tpl / 10% proc | 7 / 7, 7 / 8 | 5.3% / 5.4% | not run | not run |

**[measured]** (all-switch arm; shadow from turn 20; share of household-turns).

Recommendation (**[inferred]**): `--household-retail-boundary market` (default):
each civilization's capital region at the turn it first qualifies, sticky until the
region has no controller. It exists in every world independent of other switches,
covers a market town, and is large enough to measure. Offer `paid_work` (regions
that have had an open L6a firm or a paid RS2 crew, sticky) as the phase-story
boundary for screens, since that is where wages exist. `all` is a stress mode, not
a default. A region that leaves the pilot (no controller; switch off) closes: its
holdings return to its commons (flow `pilot_closed`) and farm income is restored
from the next turn. Conquest alone does not remove a region (sticky), so title is
not destroyed by a change of ruler.

---

## 3. Title

### 3.1 New harvest **[code + design]**

- What is titled: this turn's food production in a pilot region, per food good:
  food-slot output after catch caps and foraging, i.e. the `per_good_production`
  of grain, fish, salt, botanicals and exotic computed in Phase A
  (`economy.rs:1093-1111`). θ of each good is titled, 1 − θ stays commons
  (recommended θ = 0.9; section 9).
- Who: every agent the economy counted as farm labour, i.e. alive `Occupation::Farmer`
  in the region at Phase 2 (`ffi/mod.rs:3401-3437`), children included (they are
  43–48% of farmers **[measured]**). The Phase 2 snapshot Python already holds
  (`simulation.py:2029`, the one L2 uses, `food_allocation.py:61-73`) is that
  population; no new snapshot is requested.
- Weights, "in proportion to their farm work on food slots": the economy splits one
  labour budget equally over a region's farmers' slots, so food work per farmer is
  `w_i = u_i × (1 − h_i)`, where `u_i = URBAN_FARM_LABOR[rank]` for a farmer living
  in a city settlement and 1 otherwise (`cities.py:194`, `:1119`, the same terms
  that build `farm_labor_factor`), and `h_i` is that person's health work loss
  (the Python-authoritative health plan; `ffi/mod.rs:3489-3506` applies it). Σ w_i
  reproduces the economy's headcount labour exactly. Granary work
  (`granary_work_requested`, `economy.rs:1062-1064`) is anonymous regional labour,
  so it shrinks everyone's title equally. L1/L6a/RS2 crews work the city's
  diverted share, which `u_i` already removes, so a crew member's title equals
  any other city farmer's. A future named granary crew (a reservation category
  declared "farm time") would enter as `(1 − r_i)`; that is the phase story's
  visible tradeoff (labour shifted to timber or repairs → smaller own harvest →
  food must be bought with the wage).
- How it is recorded: native returns `retail_titled_<good>` per region (section 5);
  Python splits each good's titled milli-food over the weights by largest remainder,
  ties by ascending id, and credits the owners' claims in `finish_phase2`
  (stamp `title_turn`). An owner who is dead by then (impossible on the current
  turn order: no deaths between Phase 2 and `finish_phase2` **[code]**) would fail
  closed (raise).

### 3.2 Stock at opening, imports, fish, foraging, convoys

| Food | Title | Why |
| --- | --- | --- |
| Region stock on hand on the first pilot turn | **commons** | it was produced under the old rules; nobody paid for it |
| Fish | titled like grain | fishers are the same Farmer agents working a food slot (`economy.rs:1100-1111`) |
| Foraged grain | titled like grain | foraging is farm labour on barren land (`economy.rs:1093-1098`) |
| Merchant imports (hybrid deliveries) | **commons** | the merchant's income stays the model signal (`economy.rs:1719-1805`); no merchant title exists (bounded rule, section 8) |
| Mutual aid and convoy/granary grain | commons / keeper's granary as today | public flows; granary release is always free (section 9) |
| Abandoned granary grain | commons | as today (`grain_reserves.md` section 2) |

Measured consequence (shadow, θ = 1): the commons share of what people eat is 57%
(tpl) / 79% (proc) on the opening turn and falls below 5% (tpl) after 2 turns and
10% (proc) after 4–5 turns; in the steady state commons and release are 5–6% of food
eaten, owned food 94–95% (owners' households eat 70–74% of all food from their own
title, 21–25% is bought) **[measured]**. With θ = 0.9 the free share is 14–15% and
bought 22–23%.

---

## 4. Owned inventory

### 4.1 Where it lives: Python ledger, not the pool

Recommendation: `HouseholdRetailState.regions[r]` holds, for a pilot region `r`:

- `goods`: owned stock per food good, in integer milli-food (5 values);
- `claims`: `{owner stable id: milli-food}` with Σ claims = Σ goods exactly;
- `spouse`: transient pre-tick spouse ids of owners (for inheritance, 4.3).

A per-agent persisted pool field was rejected:

- `pool.rs` persists every listed field in declaration order
  (`pool.rs:1858-1874`) **[code]**, so a new field changes every feature-off
  checkpoint's bytes and needs a schema version and an import path for old
  checkpoints;
- food bound to the person would migrate with them (physically wrong), and slot
  reuse and death would need native rules duplicated for food.

The ledger is pickled with the world in exact checkpoints, exists only when the
switch was ever on (`livelihoods_state.py:47-63` pattern, `exclude_if=_is_none`),
and needs no native persistence: every native addition below is a one-tick
transient listed in the pool's `transient { … }` set. **Checkpoint schema impact:
none native; one new optional Python sub-state.** **[code + inferred]**

Pooled composition with scalar claims: owners in a region hold claims on one owned
pool with one good mix. Sales and own consumption draw goods proportionally (as the
economy's draw-down does, `economy.rs:1626-1643`); decay reduces all claims pro
rata. Per-owner good mixes were rejected (×5 state, no behavioural use).

Size: one entry per titled farmer of a pilot region; measured pilot farmers are
tens per region (template worlds hold 108–196 people) **[measured]**. Cap the
ledger at 4096 claims per world; a farmer beyond it is not titled (counter
`claims_refused`) and their share stays commons.

### 4.2 Decay and the storage cap

Native, in the same tick as the commons (section 5): owned stock decays at the
region's effective per-good rate (salt preservation computed over commons + owned),
and the per-good cap (`2.5 × storage_population`, `economy.rs:1689-1697`) applies
to commons + owned, overflow split pro rata. Python applies the native-reported
owned decay and overflow per good to claims pro rata (largest remainder).
Measured shadow losses: decay 3–4.5% and cap overflow 4–7% of titled food
(procedural surplus regions); merchant departures that commons could not have
supplied 2% (0.7–0.8% with θ = 0.9) **[measured]**.

### 4.3 Lifecycles (all by stable id)

| Event | Rule |
| --- | --- |
| Death | Claim passes like native wealth (`household.rs:59-140`): to the spouse if alive, else equally to living children (largest remainder, ascending id), else to the region's commons (`escheat`). Python reads owners' spouses with `get_agent_relationships` before the tick (one call per owner) and children from post-tick parent ids. Exact alternative (lead decision 6): a transient native inheritance receipt from `household_death_transfer`. |
| Migration | The claim stays in the origin's pool; the owner remains a seller by id (credited wherever they live) but cannot eat it unless present. No food travels. |
| Household split / rejoin / remarriage | Claims are individual; household own-food access is derived each turn from its present members' claims (L2 households, `provisioning.rs:193-236`). Nothing is stored per household, so a split cannot create food or money. |
| Slot reuse | Native ids are never reused (`next_id` persisted, `pool.rs:1858-1871`); every native lookup guards `pool.ids[slot] == id` (`provisioning.rs:144-150` pattern). |
| Conquest | A pilot region whose controller changed loses the conquest share of owned stock (half, the share a conquest destroys of every market stock; `grain_reserves.md` section 2), recorded `war_loss`, detected in `before_agent_tick` against the controller recorded at `finish_phase2`. Occupation (20%) and siege (15%) requisitions are **not** applied to owned stock in v1 (declared limit; counter of pilot region-turns under occupation or siege). |
| No ruler / switch off / pool reset | Region leaves the pilot: holdings → commons (`pilot_closed`); `on_pool_reset` closes every claim to commons, dated (`livelihoods.py:445-468`). |

---

## 5. Consumption timing

### 5.1 Phase 2: owned food is excluded from the native draw-down

Today the economy adds the turn's production to the region's shared stock
(`economy.rs:1585-1614`), derives sufficiency from it (`:1616-1624`) and draws demand
proportionally from every food good (`:1626-1643`) before any Python runs
**[code]**. Change (all gated on optional input columns, absent → no new arithmetic,
the `test_without_the_city_inputs_every_output_keeps_its_bits` precedent at
`economy.rs:2248`):

| Step | Pilot region behaviour |
| --- | --- |
| Inputs (`ffi/mod.rs` `tick_economy`, like `granary_work_requested` at `:3200-3211`) | `retail_title_share` (θ, f32) and `retail_owned_<good>` (5 f32, Python's milli totals ÷ 1000) |
| Phase A available / prices (`economy.rs:1113-1116`, `:1160-1165`) | owned stock is added to food `available`, so pre- and post-trade prices see all food on hand |
| Step 1 accumulate | commons += (1 − θ) × food production (+ net mobility, − craft input as today); owned += θ × food production |
| Step 2 sufficiency | `(commons + owned) / demand`, clamp 0–2: **availability**, so every regional consumer (granary release, supply-shock tracker, mutual aid, migration, famine labels, epidemics, tithe gate) keeps its meaning |
| Step 3 consume | draw-down from **commons only**, up to demand; reported as `commons_consumed` |
| Steps 4–5 decay, cap | both pools, as 4.2; owned closing, decay and overflow reported |
| Food ledger | for pilot regions the ten native ledger terms describe all food in the region (opening and closing include owned stock), so `food_accounting`'s native balance (`food_accounting.py:52-54`) still closes; owned food eaten later at phase 0.7 is a separately labelled flow, like the granary release |

New result columns (appended only when the inputs were present):
`retail_titled_<good>`, `retail_owned_<good>`, `retail_owned_decay`,
`retail_owned_overflow`, `commons_consumed`, `commons_sufficiency`.
Python's `region.stockpile` keeps the **commons only**; merchants, mutual aid and
procurement, which read it, therefore cannot take owned food (section 8).

### 5.2 Phase 0.7: provisioning sells owned food

The tick already takes L2's one-tick config at phase 0.7, after catastrophe and
targeted deaths and after the 0.5 wealth phase (`tick.rs:562-583`) **[code]**. A
second one-tick config, `RetailConfig` (`set_household_retail`, validated before
mutation like `set_food_allocation`, `ffi/mod.rs:492-503`), is taken right after
L2's allocation. Per pilot region it carries: price (milli per ration), free rations
(`commons_consumed / 0.5 + release / 0.5`; the living's share as in L2, the share of
people who died after Phase 2 recorded unallocated), and the owners' claims `[(id,
region, milli-food)]`. Non-pilot regions keep L2 exactly.

Per pilot region, households as L2 derives them (`provisioning.rs:193-236`),
people sorted by id, `cf = min(1, regional sufficiency)` (the ration everyone would
eat under equal free allocation):

1. **Free pool** (commons draw-down + release): first to households whose need to
   `cf` after their own food exceeds what their cash buys at the price
   (means-tested), up to `cf` each; the rest water-filled to `cf`, then to 1.
   (`no_relief` mode: L2's configured regime on the free pool, no means test.)
2. **Fair-share round, own food**: each household eats its present members' claims,
   children first, up to `cf` per member.
3. **Fair-share round, purchases**: each household's demand is its members' gap to
   `cf`, limited by cash ÷ price. If demand exceeds the region's remaining offer,
   it is split pro rata to demand (largest remainder in milli-rations, ties by
   household key); if the offer exceeds demand, sellers sell pro rata to their
   remaining claims (ties by id). Bought food goes to children first.
4. **Open round**: own food, then purchases, up to one ration.
5. **Rations**: written to `food_access` for every pilot person (pilot regions are
   always "allocated", even at sufficiency ≥ 1); a person at a full ration reads the
   regional signal (keeps abundance), anyone below reads their ration
   (`provisioning.rs:144-150` semantics otherwise unchanged).

Why the fair-share round: measured, letting owners' households eat to a full ration
first leaves **17% (tpl) / 9% (proc) of household-turns below their free-allocation
share with cash in hand**, a deficit of 0.033 / 0.018 rations per person-turn, larger
than the whole cash effect (0.017). With the fair-share round that non-cash
shortfall falls to 0.3–0.4% (0.001 rations per person-turn) **[measured]**. In a
scarce region everyone who can pay therefore eats exactly the free-allocation share;
only cash can push someone below it, and that is recorded.

### 5.3 Payment

- Buyers: the household's adults pay in proportion to their wealth, whole milli,
  never below zero (`wealth_transfer.rs:97-145` semantics); a household with no
  adult pays from its own members' wealth (child-only households; section 9).
- Sellers: credited by stable id, wherever they live; a credit above `MAX_WEALTH`
  is refunded to the buyers pro rata (food still delivered; counter
  `ceiling_refunds`).
- Applied natively inside phase 0.7, so needs (0.75) and everything later read
  post-purchase wealth; Σ debits = Σ credits + refunds exactly in integers.
  Wealth percentiles were computed at 0.5 and stay pre-purchase for the turn
  (declared, as for L6a wages).
- Purpose code appended to `wealth_transfer::PURPOSES` (`wealth_transfer.rs:47`):
  `food_purchase` (5), `food_procurement` (6). Append only.

### 5.4 Owners eat their own food first, within the fair share

Own food is household-pooled: any present member's claim feeds the household,
children first; the claim debited is pro rata to the members' claims. An absent
owner's claim is only for sale. **[design]**

---

## 6. Prices

Recommended rule: **ask = economy food price, clamped to [0.5, 3.0], × 0.5 per
ration**, in whole milli-units per ration (floor).

- It is the economy's own post-trade food price, demand over supply
  (`economy.rs:1561-1569`, exported as `market_price_food`), the price merchants and
  granary procurement already use (`grain_reserves.py:231-237`) **[code]**. With
  owned stock in supply (5.1) it prices all food on hand.
- The band is the one the economy already applies to farm earnings
  (`farmer_income_modifier` floor 0.5 and cap 3.0, `economy.rs:1707-1716`,
  `EconomyConfig` defaults `:152-177`) **[code]**. Unclamped, demand over a supply
  floored at 0.1 reaches tens of units in famine regions, pricing out the few
  rations sold.
- The seller is real (owners with title), so this is not an invented seller from a
  price signal.
- Measured: median 0.52 (tpl) / 0.35 (proc), p90 1.50 / 1.07 per ration; at this
  price farmers' sale revenue is **1.21× (tpl) / 1.47× (proc)** the model farm
  income they lose (θ = 1; 1.11 / 1.34 at θ = 0.9) **[measured]**.

Rejected as default, kept as an arm: the **cost rule** (price at which selling the
whole titled harvest repays the model farm income per farmer). Median ration 0.10–0.14;
it nearly removes cash shortfall (0.3% of household-turns) but farmers recover only
0.41–0.47 of their replaced income **[measured]**, so income replacement would be a
large farm-income cut.

---

## 7. Income replacement

Where farm income is computed: the wealth phase, `tick.rs:1545-1552`:
`BASE_FARMER_INCOME × region.farmer_income_modifier × resource_yields[0] ×
farm_productivity`, with `farmer_income_modifier` derived in the economy from the
production-weighted demand ÷ supply (`economy.rs:1703-1716`) **[code]**. It runs at
0.5 in the same tick that sells at 0.7 (`tick.rs:562-583`).

Rule: a one-tick `RetailIncome { turn, pilot regions }` (transient,
`install_retail_income`) is consumed by the wealth phase. For an `Occupation::Farmer`
in a pilot region, after the teaching, learning and L6a paid-work deductions
(`tick.rs:1574-1594`) the remaining ordinary farm income is recorded and set to zero;
health loss then multiplies zero. Receipt `(id, replaced)` taken once by Python.
Cash income from farming is then exactly sale revenue (household purchases and
procurement), never both: no double income. Non-farm incomes are unchanged.

L6a interplay: a crew member's paid-work share is already withheld before this step
(`paid_work_income`, `wealth_transfer.rs:328`); retail withholds the rest. The wage is
paid as today. **[code + design]**

Measured shadow cash effect on farm households: fewer than 4% of farm household-turns
hold less than one turn of rations in cash over shadow turns 20–199 (3.1–3.5%,
against 0.6–0.8% measured without retail) **[measured]**; the farm sector gains in aggregate at the
economy price (section 6) and loses in surplus regions where little sells
**[inferred from the price/volume split]**.

---

## 8. Merchants and granaries

**Merchants (bounded rule, recommended for v1).** Merchants load from the synced
`regions[origin].stockpile` (`merchant.rs:35-53`, `:752-776`) **[code]**. With owned
food outside `region.stockpile`, pilot merchants carry only commons; no `merchant.rs`
change. Measured cost: departures the commons could not have supplied are 2% of the
titled harvest (0.7–0.8% at θ = 0.9), against world food departures of 2.2–2.8% of
demand on `main` (`grain-reserves.md` section 1) **[measured]**. Recorded: pilot food
departures per turn. A real rule (merchant pays owners at the origin price at
loading) needs `merchant.rs` (pinned), the delivery buffer and a payment at 0.9:
about 250 native lines; deferred (lead decision 7).

**Granary procurement (recommended: buy from owners).** Procurement sells only grain
beyond merchants' commitments and four turns of demand from `region.stockpile`
(`grain_reserves.py:552-561`) **[code]**; in a pilot market that would be commons
only, so owners' surplus would never be procured and would be destroyed by the cap
(4–7% of titled food, above). One seam in `grain_reserves.py` (pinned):
`procurement_supply(world, rid)` returns owners' unsold grain; the market's sellable
surplus is computed over commons + owned grain; grain taken from a pilot market comes
first from owners, pro rata to claims; the purchase cost the treasury already pays
(`keep`) is credited to those owners by id (`transfer_wealth`, purpose 6) instead of
"producers outside the treasury accounts". Settled in `livelihoods.phase10` from the
turn's `BOUGHT` flows (`source`, `sent`, `cost`), once. The resource ledger's market
term (CHRONICLER_CHECK_RESOURCES) must count owned grain sold. Measured scale:
procurement takes 0.4–1.9% of harvest from markets **[measured]**, so this mainly
matters to farmers in surplus pilot regions.

**Granary release** stays free and is never sold (section 9).

**Every other reader of `region.stockpile` sees commons only** **[code + inferred]**.
Modules that read market food at `1ec0876e`: `mutual_aid.py` (donors),
`grain_reserves.py` and `public_grain_shipments.py`/`grain_convoys.py` (domestic and
foreign purchases, both through the procurement surplus list, so the one seam above
covers them), `ritual_gatherings.py` (surplus grain), `war/occupation.py`
(requisitions), `action_engine.py` (conquest destruction), `maritime.py`, the
supply-shock tracker (`simulation.py:2153-2170`, `economy.detect_supply_shocks`) and
the viewer's stock columns. In a pilot region they all see a smaller food stock than
on `main`. Food supply shocks are gated on sufficiency (availability), so the
opening drop alone does not raise one (`economy.py:327-336`); the viewer must show
owned stock beside the commons; the others are declared consequences, listed in the
switch's documentation, not fixed in v1.

---

## 9. Relief and poorer households

Constraint: nobody may fall below what free allocation would have given (`cf`)
without a visible, recorded cause. With the fair-share round the cause is almost
always cash (5.2), recorded as `priced_out`; the residual 0.3–0.4% of household-turns
short for other reasons (a short offer) is recorded as `offer_short`.

Priced out without relief (fair share, no tithe, no means test, release sold):
5.1% of household-turns, about 4% of pilot persons each turn (7.4 of 170 per
template world-turn, 21 of 544 per procedural world-turn); 8.0–8.7% of
household-turns if child-only households cannot pay **[measured]**.

Measured (shadow, every controlled region piloted, fair-share round; share of
household-turns below `cf` because cash ran out; children below `cf`; cash deficit
in rations per person-turn) **[measured]**:

| Arm | tpl households | proc households | children (tpl / proc) | deficit (tpl / proc) | Notes |
| --- | --- | --- | --- | --- | --- |
| owners eat to one ration first (no fair share) | 3.4% cash **+ 17% non-cash** | 3.9% **+ 9%** | 5.0% / 3.7% | 0.012+0.033 / 0.013+0.018 | the title shift dominates |
| fair share, adults pay (child-only households cannot) | 7.5% | 8.3% | 6.9% / 8.6% | 0.029 / 0.033 | 37% / 50% of those persons are in child-only households |
| **fair share, child-only households pay from own wealth** (L2 relief only) | 4.7% | 4.7% | 1.5% / 1.9% | 0.017 / 0.017 | 6.7 of 170 / 19.5 of 544 persons per world-turn |
| no relief (release sold too) | 5.1% | 5.1% | 1.7% / 2.1% | 0.019 / 0.018 | what the free release protects: +0.4 points |
| + means-tested free pool | 4.1% | 3.7% | 1.3% / 1.5% | 0.015 / 0.013 | commons is only ~5% of food |
| + 10% of harvest kept commons (equal) | 3.9% | 3.8% | 1.3% / 1.7% | 0.013 / 0.012 | |
| **+ 10% commons + means test (recommended)** | **0.9%** | **0.7%** | **0.3% / 0.4%** | **0.0014 / 0.0013** | 1.3 / 3.1 persons per world-turn |
| + 20% commons + means test | 0.1% | 0.1% | 0.2% / 0.3% | 0.0002 / 0.0003 | farm revenue 1.00 / 1.20 of replaced |
| ruler buys for the priced out (10% of treasury above 20) | 0.5% | 0.7% | 0.2% / 0.4% | 0.002 / 0.002 | 1.5 / 3.7 treasury units per world-turn |
| 10% commons + means test + ruler purchase | 0.1% | 0.1% | 0.2% / 0.2% | 0.0001 / 0.0003 | 0.1 / 0.3 units per world-turn |
| cost-rule price (no tithe) | 0.3% | 0.3% | 0.4% / 0.3% | 0.001 / 0.001 | farmers keep 0.41 / 0.47 of income |

Options evaluated:

- **L2's free allocation of commons kept intact**: yes, always (default and every
  mode). Commons is small after opening (5–6% of food), so on its own it protects
  little.
- **Granary releases stay free**: yes, always. Selling the release adds only ~0.4
  points of cash shortfall, and selling it would need the pinned release hook in
  `grain_reserves.py` and would let wealth buy the famine reserve (the earlier
  note's objection to option G2).
- **Relief floor funded by a harvest share kept commons (tithe)**: the effective
  lever when combined with means testing; 10% gives ~5× less cash shortfall at a
  ~0.1 drop in farmers' revenue ratio.
- **Means-tested entitlement**: on its own weak (little commons to target), strong
  with the tithe.
- **Ruler relief purchase**: effective and pays farmers, but costs treasury every
  turn; offer as an arm, and as the L9 relief envelope's use when `--local-budgets`
  is on (lead decision 5).
- **Child-only households pay from their own wealth**: removes most of the child
  exposure (children below `cf` 6.9–8.6% → 1.5–1.9%). These are L2's households of
  one; the native economy already pays them farm income and orphans inherit
  (`household.rs:111-140`) **[code]**.

### 9.1 What wages and remittances add **[measured]**

All-switch arm (`--workshops --workshop-payroll --repair-projects --remittances` with
academies and grain storage), pilot residents, turns 20–199:

| Source | Template (7 worlds) | Procedural (8 worlds) | Per person-turn (tpl / proc) |
| --- | --- | --- | --- |
| L6a wages paid to agents | 103 units | 105 units | 0.0005 / 0.0001 |
| RS2 workshop-repair crew wages | 0 | 26 | 0 / 0.00003 |
| RS4 remittances credited | 4,746 | 11,793 | 0.023 / 0.015 |
| Household food payments (shadow, `R_fair_cp`) | — | — | 0.103 / 0.092 |

Removing those credits from measured incomes (shadow arm `no_transfers`) raises the
persons in cash-limited households below `cf` from 40 to 47 (tpl) and 34 to 38 (proc)
per 1,000 person-turns over all regions, and from 22 to 30 (tpl) and 14 to 17 (proc)
in firm regions. Under the relief default the same comparison is 8.6 → 10.5 and
5.7 → 7.2 (all regions), 1.5 → 3.2 and 0.9 → 1.3 (firm regions). So money from
outside the household does change who can buy food, and almost all of it is RS4.
L6a firms are few and small (0.5 a full work-turn, crews of up to eight, firms
from about turn 70), and RS2 granary labour is anonymous and unpaid
(`repair-projects.md`, "Granary labour") **[code]**. The phase story's link
"repair a granary, pay workers, those households buy food" therefore needs paid,
named granary or timber work at a larger scale than today's wage channels before it
can show in food access; option R provides the market for that link, it does not
create the wages.

### 9.2 Default and controls

**Default (recommended):** commons free (L2), release free, θ = 0.9 (10% commons),
means-tested free pool, fair-share round, child-only households pay from their own
wealth. Declared, not calibrated.

**Controls (modes):**

| Mode | Title, income replacement | Purchases | Relief | Shows |
| --- | --- | --- | --- | --- |
| `retail` (default) | yes | priced | default | the mechanism |
| `no_relief` | yes, θ = 1 | priced | L2 regime on commons, no means test | what the tithe and means test protect |
| `free_exchange` | title yes, farm income **kept** | same rounds at price 0 (no payment) | default | ownership and timing without cash: `retail` − `free_exchange` isolates what payment and income replacement do |
| `record_only` | computed in Python, not applied | dry run returns would-be receipts | — | identity: trajectory must equal L2 alone |

Plus `--food-allocation` off (refused: retail requires L2) and the boundary choice.
`record_only` and L2 alone must be identical byte for byte (test). Visible records
per pilot region-turn: priced-out households, persons and children, their deficit,
offer shortfalls, free given, own eaten, sold, paid, refunds, title, income
replaced, unsold stock, decay and overflow, war loss.

---

## 10. Accounting, exactly-once, stale receipts

Units: food in integer milli-food in Python (1000 = one food unit = two rations);
money in integer milli-units (1000 = one wealth unit = one treasury unit, the L6a and
domestic-credit equivalence). Native f32 food and wealth match the books within
f32 tolerance (the L6a precedent, 2·10⁻⁵ per transfer).

Identities, all raised on failure (`check_region`, `check_owner`):

```
owned pool, per region and good (milli-food):
  close = open + titled − own_eaten − sold − procured − decay − overflow − war_loss − closed_out
per owner:
  claim_close = claim_open + titled_i − own_eaten_i − sold_i − procured_i − decay_i − overflow_i
                − war_i ± inherited_i − escheat_i
  Σ claims = Σ goods
native Phase 2 (pilot), food units:
  opening(commons+owned) + produced + transport_net − craft_input + clamp
    − commons_consumed − storage_loss − cap_overflow = closing(commons+owned)
  owned_close = owned_open + titled − owned_decay − owned_overflow
provisioning, per pilot region (rations):
  free_given + free_unallocated = free_rations
  own_eaten + sold = offered − unsold
  Σ person rations = free_given + own_eaten + sold;  0 ≤ ration ≤ 1
money, per region (milli):
  Σ buyer debits = Σ seller credits + Σ ceiling refunds = paid
  per person: paid_i ≤ wealth_before_i (never negative)
  procurement: Σ owner credits + commons share = cost × 1000 per BOUGHT flow
  income: Σ replaced recorded = Σ (receipt rows); no pilot farmer has replaced > 0 and ordinary farm income > 0
per person: cash-limited ⇒ recorded priced_out; ration < cf ∧ ¬cash-limited ⇒ recorded offer_short
```

Exactly once:

- `RetailConfig` and `RetailIncome` are one-tick installs, taken by the tick
  (`take()`), cancelled in `rollback_agent_tick` (`livelihoods.py:522-555`).
- Receipts (`take_household_retail_frame`, `take_retail_income_receipt`) are taken
  once and carry `source_turn`; Python refuses a receipt whose turn ≠ `world.turn` or
  ≤ `last_settled_turn` (persisted), and a repeated title for `title_turn`.
- Procurement credits use the `wealth_transfer` key log (`(turn, 6, batch)`,
  `wealth_transfer.rs:111`) and Python's `last_procured_turn`.
- Nothing is pending at a turn boundary; the ledger is the only persisted state.

---

## 11. Switch, persistence and identity

- CLI and registry: `household_retail` appended to `LIVELIHOODS_SWITCHES`
  (`livelihoods_state.py:33-37`) and `LIVELIHOODS_ARG_KEYS` /
  `LIVELIHOODS_CHOICES` (`livelihoods.py:59-89`) with `household_retail_mode` and
  `household_retail_boundary`; prerequisites in `_check_prerequisites`
  (`livelihoods.py:286-342`): hybrid and `--food-allocation`; `feature_catalog.REQUIREMENTS`
  row (`feature_catalog.py:94-114`); `batch_manifest.SIMULATION_ARG_KEYS` lists the three
  keys (`batch_manifest.py:56-136`, hardcoded, pinned).
- Hooks (existing protocol, `livelihoods.py:37-54`): `prepare_phase2` (columns),
  `finish_phase2` (title, decay), `before_agent_tick` (conquest loss, offers, prices,
  spouses, installs), `after_agent_tick` (receipts, settlement, deaths),
  `rollback_*`, `phase10` (procurement credits), `on_pool_reset`,
  `snapshot_summary`.
- Order inside a turn: L2's `before_agent_tick` installs first (switch order:
  `food_allocation` precedes `household_retail`).
- Feature off: no state, no columns, no install, no snapshot key: byte-identical by
  construction; prove with `turn_speed_identity` (9 cases, 399 files). Exact resume:
  `checkpoint_identity` all-switch case with the new switch.

---

## 12. Implementation plan

### 12.1 Lanes

| Lane | Files | Pinned (lead witness layer) | Size (approx.) |
| --- | --- | --- | --- |
| **N1 native economy** | `economy.rs` (inputs struct, Phase A/C supply, steps 1–5, outputs), `ffi/mod.rs` (`tick_economy` optional columns and result columns), `ffi/schema.rs` only if result columns are added to the static schema (prefer appending dynamically) | economy.rs, ffi/mod.rs, (schema.rs) | 150 + 120 lines; Rust tests 250 |
| **N2 native provisioning and wealth** | `provisioning.rs` (retail step, matching, payments, receipts), `tick.rs` (0.5 replacement call, 0.7 take), `pool.rs` (four transient fields, transient list), `wealth_transfer.rs` (two purposes, in-tick paired transfer helper), `ffi/mod.rs` (`set_household_retail`, `cancel_…`, `take_household_retail_frame`, `install_retail_income`, `take_retail_income_receipt`) | tick.rs, pool.rs, ffi/mod.rs (provisioning.rs and wealth_transfer.rs carry no enforced pin) | 350 + 40 + 20 + 60 + 120; Rust tests 400 |
| **P1 Python state and settlement** | new `household_retail.py`, `household_retail_state.py`; `livelihoods.py`, `livelihoods_state.py` (registry), `food_allocation.py` (skip pilot regions in its closure check, or pass them through), `feature_catalog.py` | none of these | 650 + 180 + 40 + 20 + 5; offline tests 700 |
| **P2 Python pinned seams** | `grain_reserves.py` (procurement seam + ledger term), `batch_manifest.py` (3 arg keys) | both | 40 + 3 |
| **V viewer** | `viewer/src/lib/householdRetail.ts` (strict reader refusing records that do not close), `components/systems/HouseholdRetail.tsx`, mounting in the Livelihoods panel (lead-owned) | mounting file if pinned | 250 + 200; vitest 150 |
| **Lead** | witness layers for every pinned edit; shard manifest and `run_python_oracle_checks.py` CHUNKS enrollment; `tests/test_native_ci_shards.py` additions | — | — |

Preflight on 2026-11-05 (`scripts/refactor_preflight.py`)
**[measured]**: enforced source-witness pins on `economy.rs` (4 fixtures),
`tick.rs` (7), `pool.rs` (6), `ffi/mod.rs` (13), `ffi/schema.rs` (3), `merchant.rs`
(1), `household.rs` (1), `lib.rs` (6), `grain_reserves.py` (8),
`grain_reserves_state.py` (4), `economy.py` (3), `simulation.py` (11),
`agent_bridge.py` (3), `batch_manifest.py` (13), `main.py` (9),
`food_accounting.py`; none on `provisioning.rs`, `wealth_transfer.rs`,
`livelihoods.py`, `livelihoods_state.py`, `food_allocation.py`,
`feature_catalog.py`, `mutual_aid.py`, `local_budgets.py`, `workshop_payroll.py`,
`remittances.py`, `repair_projects.py`. The design keeps the retail step inside
`provisioning.rs` (no new module, so no `lib.rs` edit) and needs no edit to
`simulation.py`, `agent_bridge.py`, `merchant.rs`, `household.rs`, `economy.py` or
`food_accounting.py`.

### 12.2 Tests

- **Rust (N1)**: absent columns keep every output's bits; θ = 1 commons-only
  draw-down; owned counts in sufficiency and price; decay and cap split; food ledger
  closes with owned stock; zero-production and empty regions.
- **Rust (N2)**: fair-share then open round; own food first within cf; short offer
  split pro rata with largest remainder; children first; adult payers and child-only
  payers; wealth floor and ceiling refund; absent (dead after Phase 2) owner sells,
  dead buyer is skipped; reused slot ignored; non-pilot regions equal L2's
  allocation; income replacement consumed once after paid work; next tick
  unaffected; receipts close.
- **Python offline (stand-in native)**: title by weights and largest remainder;
  opening stock stays commons; imports commons; claims close per owner and region;
  death to spouse, children, commons; migration keeps claims; split and rejoin
  create nothing; conquest loss; pilot closure; pool reset; stale, repeated and
  wrong-turn receipts refused; procurement credits once; modes; exact pickle and
  JSON round trip; `record_only` equal to L2.
- **Native (real extension)**: a constructed pilot region where title, sale, payment,
  ration and income replacement move exactly once and close; L6a wages raising
  purchases; RS4 remittance raising a recipient's purchase; procurement paying owners;
  exact checkpoint resume mid-pilot; feature-off identity; `record_only` identity;
  `CHRONICLER_CHECK_RESOURCES=1`.
- **Viewer**: reader refuses non-closing records; component renders; lint, build.

### 12.3 Order of work

1. Lead decisions (section 15).
2. N1 economy split with its identity test; one native build.
3. N2 provisioning step and income replacement; second build.
4. P1 against a stand-in in parallel with N1/N2 (the FFI shapes are fixed here);
   then wire to the real extension.
5. P2 pinned seams (procurement, manifest keys) with lead witness layers.
6. Native tests, feature-off identity, checkpoint identity.
7. V viewer.
8. Development-world screens of every mode × boundary; then the preregistered held
   cohort before any claim.

Estimated total: ~1,100 native lines, ~1,000 Python lines, ~1,500 test lines, two
native builds; 4–5 lane-days plus lead witness and evidence work **[inferred]**.

---

## 13. Risks and hard parts

1. **Every food consumer in a pilot region changes** (needs, satisfaction,
   mortality, fertility via individual rations; wealth via payments and income).
   Held-cohort evidence is required before any claim.
2. **Regional signal vs individual access.** Regional sufficiency stays availability,
   so a "dearth amid stores" (owned food unaffordable) is not a famine label, and
   migration, famine memory and granary release do not react to it. It must be
   reported (`priced_out`), and a retail-aware famine label is out of scope.
3. **Native economy edit** (`economy.rs`) in the lead-owned core: the off path must
   be untouched bit for bit; the abstract (non-hybrid) path is refused.
4. **f32 vs milli books** for owned stock and wealth: Python is authoritative in
   integers; native totals agree within tolerance; drift must not accumulate (Python
   re-sends its totals every turn).
5. **Inheritance mirror**: Python's spouse/children rule may disagree with native
   estate handling in rare same-tick deaths; the exact fix is a native receipt.
6. **Merchants**: the bounded rule removes pilot exports of owned food (≈2% of the
   titled harvest; neighbours lose some imports).
7. **Procurement seam** touches the granary resource ledger (pinned).
8. **Wealth percentiles** are computed before purchases (0.5); Phase 10 reads
   post-tick wealth (purchases are inside the tick, so the earlier "Phase 10 reads
   pre-after-hook wealth" defect does not apply).
9. **Child farmers own food** (43–48% of farmers): faithful to the economy's labour
   count but may surprise readers; documented.
10. **Interactions**: L7 fares and household mobility read wealth after 0.7
    (purchases reduce move liquidity — a visible tradeoff); domestic credit's
    merchant lenders and L9 envelopes see different wealth and treasury.
11. **Invisible owned stock**: mutual aid, ritual gatherings, requisitions and the
    supply-shock tracker read commons only in pilot regions (section 8).
12. **Shadow limits**: no feedback, households derived from post-tick rows, income
    estimated from wealth differences, cap approximated at five turns of demand; the
    numbers set the boundary and the default, they are not effect estimates.

---

## 14. Measurement method and limits

Runs (one process at a time): `run_all.sh` drives `driver.py`, which runs
`chronicler.main` in-process with read-only wrappers around
`economy.build_economy_region_input_batch`, `economy.reconstruct_economy_result`,
`food_allocation.prepare_phase2/before_agent_tick/after_agent_tick`,
`simulation._capture_agent_snapshot` (plus `get_agent_relationships` for spouses) and
`main.run_turn_result`. Each wrapper calls the original and only reads. Output:
`runs/<arm>_<kind>_<seed>/rec.pkl.gz` (template runs ~9 s, procedural ~25 s).

Analyses: `describe.py` and `pp.py` (measured distributions), `shadow.py` (per-agent
no-feedback shadow: Phase 2 population = previous post-tick rows; title equal per
farmer; commons = opening stock + (1 − θ) harvest + net mobility; measured income =
`w_t / 0.98 − w_{t−1}` minus replaced farm income; fair-share rounds; payments;
decay at the measured effective rate; cap at five turns of demand; dead owners to
spouse else commons), `analyze.py`, `table.py`. `shadow_{base,all}.json` hold the adult-payer arms and
all four boundaries; `shadow2_{base,all}.json` the child-pay arms (all regions and
firm regions) quoted as the recommendation. The first file came from an earlier `ARMS` list in
`analyze.py` over the same shadow code (the child-pay flag defaults off; `R_fair` is
identical in both files). Reproduce with `./run_all.sh t1 … p303`
(and `ARM=base`), then `python analyze.py base|all` and `python table.py <set> <keys> [2]`. Counterfactual `cf` = each person's measured L2-equal ration, `min(1,
post-release sufficiency)`.

What is not measured: feedback of hunger and wealth on deaths, births, migration and
prices; procurement from owners; conquest losses; the held cohort.

---

## 15. Decisions the lead must make

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Build option R now, or keep L6b open | Build, with the default below: measured exposure is bounded and attributable. Pair it with a paid, named public-work lane if the phase must show wages reaching food (today's L6a/RS2 wages are ~0.5% of food spending) |
| 2 | Pilot boundary | `market` (capital per civ, sticky) default; `paid_work` for phase-story screens; `all` as stress mode |
| 3 | Own consumption rule | Fair-share round then open round (not owners-first: that shifts 9–17% of households below their free share without a cash cause) |
| 4 | Price | Economy food price clamped to [0.5, 3.0] × 0.5 per ration; cost rule only as an arm |
| 5 | Relief default | Commons and release free, θ = 0.9, means test, child-only households pay from own wealth; ruler relief purchase as an arm, and as the L9 relief envelope's use when `--local-budgets` is on |
| 6 | Death of an owner | Python mirror of native estate order in v1; add a transient native inheritance receipt if the lead wants exactness |
| 7 | Merchants | Commons-only loading in v1 (≈2% of titled harvest foregone as exports); merchant purchase from owners deferred |
| 8 | Granary procurement from owners | Yes, via one pinned seam in `grain_reserves.py` |
| 9 | Occupation and siege requisition of owned stock | Not in v1 (declared limit, counted); conquest loss yes |
| 10 | Who holds child farmers' title | The child, by stable id (households are never stored) |
| 11 | Payment for child-only households | From their own members' wealth |
| 12 | Evidence bar | Feature-off identity, exact resume, dev screens of every mode × boundary, then the held cohort before any claim |
