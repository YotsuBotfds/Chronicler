# Household food purchases (L6b): design and feasibility

Design note for the sprint-2 finance lane
([plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md)). No code accompanies it.
It builds on L2 food allocation ([food-allocation](food-allocation.md)), public
granaries ([grain-reserves](grain-reserves.md)) and L6a payroll
([workshop-finance](workshop-finance.md)). Source base:
`claude/livelihoods-sprint2` at `60b63f25`.

Roadmap requirement: households buy food inside a declared pilot boundary, with actual
cash and actual stock. The note must name the custodian and title of the food before
any payment, and must not invent a private seller from a price signal. L2's free
allocation and relief must stay available. Each payer is debited, each recipient
credited, and any unapplied amount is kept. A household that splits and rejoins must
not create money. If general retail is too large, household purchases stay open; they
must not be replaced by a wealth threshold.

**Verdict: LEAVE OPEN** (last section). The only food with an explicit owner today is
public granary grain. Measured on the development worlds, it holds unsold grain while
people are short in 1–13% of short region-turns, enough for 1–5% of the shortfall. A shop selling that grain would
be bounded but would barely activate. Real household purchases need producer
ownership of new harvest inside the native economy, and that is general retail. One
bounded fallback (option G) is specified in enough detail to build if the lead wants
a demonstrator.

## 1. Where food sits today, and who owns it

| Food | Owner | Where it is eaten |
| --- | --- | --- |
| Region's market stock (all food goods) | **Nobody.** Shared regional inventory with no producer title. Farmer and merchant incomes are model-provided signals, not sale revenue ([source audit](public-workshop-source-audit.md), "Cash and ownership are separate"). | Inside the Phase 2 native economy tick (`economy.rs`, step 3: drawn proportionally up to demand, before any Python code runs). L2 then decides **who** eats that withdrawal; the stock is already gone. |
| Public granary grain | **The keeper civilization.** It bought the grain with treasury money (`BOUGHT` flows), captured it by conquest (`CAPTURED`), or the grain went back to the market when no ruler remained (`ABANDONED`). | Free release in Phase 2 (`open_granaries`), up to sufficiency 1 when the granary is full, or to the famine line (0.6) when it is low. |
| Convoy cargo (L4) | Buyer civilization, in transit | Delivered into a granary, then as above. |
| Academy materials, L6a firm wares | Academy or firm | Crafts, not food. |

Only granary grain is food with both an owner and a real recipient for payment (the
keeper's treasury). Everything people eat each turn is shared stock. The native
economy draws it down before any household could pay.

## 2. Measured feasibility (development seeds 1–3, 200 turns)

Flags: `--agents hybrid --grain-reserves --public-grain-shipments --food-allocation
--food-allocation-regime equal`, recorded right after `open_granaries`. Ration price is
the economy's food price times `PER_CAPITA_FOOD` (0.5), with one treasury unit counted
as one wealth unit.

| Seed | Short region-turns after release | Shortfall (rations) | Region-turns where the granary still held grain while short | Rations that grain could cover | Release region-turns | Rations released above the famine line |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 830 | 7558 | 6 | 69 | 7 | 0 |
| 2 | 502 | 4597 | 14 | 61 | 7 | 15 |
| 3 | 500 | 5038 | 66 | 268 | 13 | 45 |

- **Prices and savings.** The median ration price in short regions is 0.8–1.3 wealth
  units, the median adult wealth 9–19. Top-ups are affordable for a few turns.
- **Full retail is not affordable.** A farmer's ordinary income is about `0.3 × price
  modifier` a turn and a ration costs `0.5 × price`, so a farmer's whole income buys
  about 0.6 rations, and children earn nothing. Charging households for **all** food
  at the market price would starve them, unless producers received the payments in
  place of their model-provided income. That requires producer title.
- **The granary is a minor source.** Scarcity is common, but granaries hold little
  grain while people are short. A granary rarely keeps a reserve when the harvest is
  steady, and a full granary releases up to sufficiency 1. Sellable granary grain is
  about 1–5% of the shortfall.

## 3. Options considered

### Option R: general food retail in a pilot region (the real L6b)

Example boundary: regions with an open L6a firm, or one market region per civ.

1. **Title.** New harvest in the pilot region would belong to the farmers who grew
   it, by stable id, in proportion to their farm work. Stock existing when the pilot
   opens stays a shared commons.
2. **Consumption.** The native economy would stop eating owned food in Phase 2.
   Provisioning (phase 0.7) would then:
   - allocate shared stock and relief for free under the L2 rule;
   - sell owned food to households, paid from the adult members' wealth, credited to
     the producers by id;
   - replace the producers' model-provided farm income share, as L6a does for crew.
3. **New state.** Unsold owned food would need a per-agent food inventory (persisted,
   so a checkpoint schema change) with wear, inheritance, conquest and migration rules.
   Merchant departures and grain procurement would have to buy from owners instead of
   the commons.

Rough size:

- **Native:** `economy.rs` (lead-owned) for consumption and departures, `pool.rs` for a
  persisted per-agent food field, `provisioning.rs`, `tick.rs` (income replacement for
  every pilot farmer) and `ffi`; roughly 700–1000 lines.
- **Python:** about 600 lines.
- **Tests:** about 800 lines.
- **Behaviour:** every food consumer in the pilot regions (famine labels, mortality,
  migration, satisfaction) changes, so the held-cohort gate would be needed before any
  claim.

The hard parts (title, consumption timing, income replacement, owned inventory) do not
shrink with the size of the boundary. **Not bounded for this sprint.**

### Option G: paid top-up from public granaries (bounded fallback)

1. **Boundary.** Regions with a granary whose keeper controls them. Requires
   `--grain-reserves` and `--food-allocation` with regime `equal` or
   `targeted_relief`. `floor_means` is refused: it already weights food by means
   without debiting anyone, which would give wealth a second, unpaid channel.
2. **Owner and title.** The keeper civilization owns the granary grain. Its opening
   endowment is the grain the granary holds on the first pilot turn, which was already
   bought or captured under recorded flows. New harvest stays shared market stock. It
   enters the keeper's title only through existing granary procurement, which is paid.
   Nothing else is ever owned.
3. **Relief stays.** L2's free allocation of shared market food is unchanged, and the
   granary's free release up to the famine line is unchanged. Cash failure therefore
   never removes food that would have been free.
4. **Offer.**
   - **Quantity:** the grain still held after this turn's release, up to the shortfall
     to sufficiency 1. A variant (G2) would convert release above the famine line into
     an offer; that changes relief policy, so it would ship as an arm, not as the
     default.
   - **Price:** the food price granary procurement already uses (`_food_price`, demand
     over supply), times `PER_CAPITA_FOOD` per ration, in milli-units.
   - **Units:** 1000 milli-units are one treasury unit and one wealth unit, as in L6a
     and domestic credit.
   - The price is that of a real public seller selling its own grain, not a private
     seller made up from the price signal.
5. **Purchase (native, phase 0.7, inside `provisioning::allocate`, after the rule).**
   - In each offer region, households (derived as L2 derives them) with members below
     one ration bid for their members' shortfall.
   - Each household pays from its adult members' own wealth, in proportion to each
     adult's wealth, in whole milli-units, never below zero.
   - When the offer is smaller than demand, it is split in proportion to demand
     (largest remainder, ties by household key).
   - Bought rations top up the members' rations, children first, up to one ration
     each.
   - Debits go by stable id through the same rules as L6a `transfer`; any amount that
     cannot be applied is returned.
   - Receipts, taken once: per region the quantity sold and money collected; per
     household the amount paid, rations bought, and the shortfall that remained unpaid.
6. **Settlement (Python, after the tick).**
   - The sold grain (`rations × PER_CAPITA_FOOD`) leaves the granary as a new `SOLD`
     reserve flow. This is an append-only flow kind, with its term added to the
     reserve ledger's granary balance.
   - Collected money enters the keeper's **custodian till** (milli-units, persisted).
   - In Phase 10 the till credits the keeper's treasury in whole units (`keep`), before
     the reserve ledger's purchase window opens; the sub-unit remainder stays in the
     till.
   - Unsold offer stays in the granary.
   - On conquest the till follows the granary to the new keeper, as its grain does
     (`CAPTURED`). If the region falls with no ruler, the till is written off to a
     named sink.
7. **Native vs Python.** The native side does the matching and the wealth debits. It
   is the only place where the current ration, the current wealth and the current
   household keys exist together after the turn's earlier deaths. Python sets the
   offers, settles the granary and the till, and owns the accounting.
8. **Exactly once and checkpoints.**
   - The offer is a one-tick config, like L2's allocation: taken by the tick and
     cancelled by Python if not taken.
   - Receipts are taken once and carry the source turn. Python refuses a stale or
     repeated receipt and records the last settled turn.
   - Nothing is pending at a turn boundary, and the till is persisted state.
   - Households are never stored and hold no balance; every payment is an
     individual's wealth by stable id. A split or rejoin therefore cannot create
     money.
9. **Accounts that must close.**
   - Per keeper: `till_close = till_open + collected − credited − written off`.
   - Per granary: the existing ledger plus `SOLD`.
   - Per region: `sold ≤ offer`, `Σ paid = collected`.
   - Per person: `ration ≤ 1`, `paid ≤ wealth before`.
10. **Controls.**
    - Purchases off: identical trajectory to L2 alone (identity).
    - Offer present but price above everyone's means (no cash): identical to off,
      plus zero-sale receipts.
    - G2, release above the famine line sold instead of given.
    - Cash-only without relief (all release sold): this needs the release hook in
      `grain_reserves.py` and shows what relief protects.
11. **Acceptance tests.**
    - Offline: till and granary closure; partial fills at the wealth floor; pro-rata
      split of a short offer; children topped up first; refusal of `floor_means`; a
      split or rejoin creating no money; conquest moving the till; no ruler writing
      the till off; a stale or duplicate receipt refused; exact pickle round trip.
    - Rust: matching and debits, a dead person (no debit, share unsold), a reused
      slot, an empty or zero offer, the wealth floor, and the next tick unaffected.
    - Native: a constructed offer region (as the L4 convoy tests do) where purchases
      move wealth, ration, granary and treasury exactly once; inheritance of
      post-purchase wealth through the native estate rules; L6a wages raising the
      ability to buy; a payroll firm in arrears lowering it; exact checkpoint resume;
      identity with purchases off; `CHRONICLER_CHECK_RESOURCES=1` passing.
12. **Size.**
    - **Native:** `provisioning.rs` purchase step, about 150 lines plus 6 unit tests;
      `pool.rs`, two transient fields; `ffi/mod.rs`, two methods (`set_food_offers`,
      `take_food_purchase_frame`); `tick.rs`, none, since the step runs inside the
      existing allocation. No change to the persisted layout.
    - **Python:** a new `household_purchases.py` and its state module, about 350
      lines; livelihoods switch hooks as in L6a.
    - **Pinned-file hooks (need lead witness layers):** `grain_reserves_state.py`
      (`SOLD` flow kind) and `grain_reserves.py` (one ledger term, plus the release
      split only for the G2 and cash-only arms).
    - **Viewer:** a reader and a component.
    - **Tests:** about 500 lines.
    - **Total:** about 1.5 lane-days, with one native build.

## 4. Verdict: LEAVE OPEN

The roadmap's L6b is household food purchase, which is general retail. It is not
bounded here. Option G is bounded and honest, but would barely activate:

1. **Real purchases need producer title (option R).** Payment can only reach a real
   recipient if owned food is not eaten in the Phase 2 native economy before anyone
   can pay. That means:
   - changing `economy.rs` consumption and merchant departures;
   - persisting per-agent food holdings (a checkpoint schema change);
   - replacing model-provided farm income for every pilot producer.

   None of that shrinks with a smaller boundary, and the change reaches every food
   consumer in the region.
2. **Option G is the only bounded design, and it is nearly inert.** On the
   development worlds, sellable granary grain covers about 60–270 rations per world
   against 4600–7600 short rations, in 6–66 region-turns. A purchase market of that
   size would not let us test whether cash pressure reaches food access. It would
   also need pinned edits to `grain_reserves`, and it mainly lets wealthier households
   buy the reserve held back for famine. That is a distributional effect we have no
   case for making the default.
3. **No threshold stand-in.** Per the roadmap, purchases are not replaced by a wealth
   threshold. L2's means-weighted allocation stays a declared nonmarket rule.

What would be needed to build L6b for real:

1. **Producer title.** A native producer title for new harvest in a pilot boundary,
   and a consumption step that serves owned food only through provisioning (a
   lead-owned `economy.rs` change).
2. **Food inventory.** A persisted per-agent food inventory with wear, inheritance,
   migration and conquest rules.
3. **Income replacement.** Producers' model-provided farm income replaced by sale
   revenue, using the L6a mechanism.
4. **Merchants.** Merchant and granary purchases that pay owners instead of drawing on
   the commons.
5. **Qualification.** Held-cohort evidence, because every food consumer in the pilot
   regions changes.

If the lead wants a demonstrator anyway, option G is specified in section 3 and can be
built as described, as a default-off arm with the counts above disclosed.
