# Audit A4: merchants and owned cargo (title, custody, settlement, timber-poor supply)

Design-audit lane for Program A4 of the connected-world program, 2026-11-06. Read-only.

- **Sources read.** `/home/user/Chronicler` at `main` `8286804c` (quarantine modes, watershed
  `record_only`, screen runner). The Rust tree there is identical to the reference `8abc1acb`
  (`git diff --stat 8abc1acb 8286804c -- chronicler-agents` is empty), so `chronicler-agents`
  line numbers hold for both. `money.py`, the A3 purpose append and workshop economics are read
  in `/home/user/wt/a3-workshops` (`claude/cw-a3-workshop-economics`, `1073229b`). Retail rules
  v2 (A5) and the ledger are read in `/home/user/wt/s1` (`claude/cw-s1-accounting`; integration
  in progress). No tracked file was edited, switched, stashed or committed anywhere; `git status`
  on `main` was clean before and after.
- **Binding inputs.** The program brief (A4). AUDIT-A1-A2 §0, §1, §3.3, §5, §7: `wealth` is the
  one spendable balance; new payers go through `money.py`; model income is replaced, not stacked
  (merchant income becomes margins paid by buyers). AUDIT-A3: A3-2's owned-output column is
  batched with A4's pairwise payment into one native build. AUDIT-D §1-3 (owned stock and cargo
  through war). AUDIT-C §3 (quarantine closure and merchant routes).
- **What was run.** `scripts/refactor_preflight.py --json` on 32 candidate files (read only;
  `preflight.json`, `preflight-summary.txt`). One development run: template seed 1, 200 turns,
  8 s wall time, with an in-process read-only probe (`probe.py`, `analyze.py`,
  `run1/probe_t1.jsonl`; method in the appendix). No tests, builds, installs or other seeds.

Labels: **[code]** read in source (file:line); **[doc]** project documentation; **[dev]**
measured by this lane on the one development world (exploratory, not evidence for any screen);
**[inferred]** reasoned, not run; **[unverified]** stated, not checked.

---

## 0. Answers in brief

1. **Merchants today carry only commons goods, paid by nobody, and earn a model-created
   income** [code]. A merchant is a native agent with `Occupation::Merchant`. It reserves cargo
   from the origin's commons stockpile, departs, moves one hop a tick and delivers into the
   destination's commons. The merchant's income `merchant_trade_income` is computed per origin
   region from realized commons deliveries (delivered × positive post-trade price gap ÷ the
   origin's merchants). It is then paid at the next wealth phase to every merchant *located* in a
   region, with no payer debited (`economy.rs:2082-2129`, `tick.rs:1566-1569`; A1 row 3). Under
   household retail, owned food is never loaded (lead decision 7). Merchant imports into a pilot
   region go to the commons, where they are given away as free rations.
2. **Retail `all` stops inter-regional food trade** [dev, one world]. On template seed 1 with
   retail at the `all` boundary, native merchants delivered **0 food in 200 turns**; they moved
   20 timber, 92 ore and 7.5 wares. Default template runs deliver about 400 food per run
   (`bulk-trade-crafts.md:44`) [doc]. Meanwhile pilot food prices diverged: a pair of pilot
   regions at most two hops apart, with owned food at the cheaper end and a price gap above the
   planner's margin, existed in **160 of 200 turns** (median gap 1.39 price units, 39%
   cross-civ). A4 is therefore the only channel that could move owned food between pilot
   regions.
3. **Timber-poor worlds lack production as well as access** [code + dev]:
   - RS2's timber need never enters native raw-material demand (`economy.rs:1436-1445`).
   - Timber and ore share one category, and merchants load whichever raw good is most plentiful
     (`merchant.rs:754-786`).
   - PL1 never cuts another civ's forest (`timber-supply.md:123`).

   On template 1, PL1 refused 344 region-turns of need (1,212 timber of gap). Native merchants
   delivered 0.24 timber into those regions on those turns. Free commons timber of at least one
   unit was reachable within two merchant-graph hops in 107 of the 344 cases (77 same civ, 30
   only through other civs). Trade could cover at most about 29% of the gap (upper bound); the
   world's median free timber was 0.11.
4. **Which proxy A4 replaces.** While a merchant carries titled cargo, its whole ordinary
   occupational income (its share of `merchant_trade_income`) is withheld through the existing
   paid-work seam. That seam gives an exact receipt per person-turn (`tick.rs:1600-1601`,
   `wealth_transfer.rs:527`). Titled cargo never enters native arrivals, so the model income
   formula cannot count it (by construction). The merchant then earns only what buyers pay.
   Model income for native commons trips stays. It is declared as a remaining model share and
   the ledger shows it.
5. **Recommended design: `--titled-trade` (default off) as Python shipments carried by named
   merchants.**
   - Python keeps title and custody, like grain convoys and PL1 expeditions.
   - Each carrier is reserved under a new work category `trade`. The native planner skips
     reserved merchants, so nobody does both kinds of trip.
   - Purchases at the origin are settled pairwise, merchant → owners, by stable id.
   - At the destination the cargo becomes the merchant's retail claim. Households buy it through
     the existing native provisioning and pay the merchant by id. No new sale path is needed.
   - No randomness. No persisted native schema change.
6. **Native changes for A4-1, all in the one batched build with A3-2:**
   - `wealth_transfer::settle_pairs` with purposes `cargo_purchase` and `cargo_sale`, appended;
   - the `trade` reservation category (`workshop_work.rs`);
   - a six-line planner skip in `merchant.rs`, which is ENFORCED (`crisis_candidate`);
   - FFI `settle_pairs` in `ffi/mod.rs`, which is ENFORCED.

   Everything new on the native side is transient.
7. **Slices.**
   - **A4-1:** food between retail pilot regions, with complete declared outcomes for every event.
   - **A4-2:** war, quarantine and sea integration with A5/D4/C1 hooks.
   - **A4-3:** timber orders from PL1-refused RS2 regions, bought from commons owners (including
     other civs), delivered into PL1's earmarked store and paid from the buyer's treasury through
     escrow.
   - **A4-W:** wares, after A3-2.
   - **Evidence:** a CW5 held screen (template 771-776, procedural 871-876, reserved).

---

## 1. Merchants today (Q1)

### 1.1 Who, what and how [code]

| Aspect | Rule today | Evidence |
| --- | --- | --- |
| Who | Living agents with occupation Merchant (code 2). The planner takes idle merchants in (region, id) order, skipping one that delivered this tick (`trip_home_region` set). There is no work-registry exclusion. | `merchant.rs:1552-1565` |
| State | Per agent, persisted in exact checkpoints: `trip_phase` (Idle, Loading, Transit), origin, destination, good slot, `trip_cargo_qty` (f32), path and cursor, `trip_home_region`. The simulator persists the shadow ledger and delivery buffer. | `pool.rs:154-176,1869-1885`; `ffi/mod.rs:5563-5573`; `merchant.rs:2362-2379` |
| What | One good per trip, the origin's largest uncommitted **commons** stock (`RegionState.stockpile`) in the chosen category. Food goes first, to the market where it is dearest. Otherwise the best non-food category. Bulk capacity per trip by the narrowest leg: land 2, river 5, sea 10 loads. | `merchant.rs:474-487,754-786,886-945` |
| Price | Food 1 / sufficiency. Raw and luxury: demand / post-trade supply (0 without demand). Read "as if" this tick's committed cargo and the load had arrived (`MarketTally`). A load is added while it still earns `LOAD_MARGIN` = 0.25. Wares are left out of packets. | `merchant.rs:551-746` |
| Loading | Reserve at tick 0.9 of T (Loading); depart at 0.9 of T+1. Physical stock is rechecked, so a reservation shrinks or is cancelled. Departures are debited from the origin commons by the economy in Phase 2 of T+2. | `merchant.rs:1125-1170,1208-1250`; `economy.rs:1541-1546,1582-1599` |
| Transit | One hop a tick. Transit merchants are counted in their **origin's** `merchant_count` but stay physically in the transit region. | `merchant.rs:1176-1200`; `ffi/mod.rs:3564-3596` |
| Arrival | Recorded at 0.9, credited to the destination **commons** at the next Phase 2. **Transit decay is applied once per trip on arrival** (grain 0.05, fish 0.08, timber 0.01, botanicals 0.04, exotic 0.06, others 0). The merchant goes home at the end of the tick; the return leg is not simulated. | `merchant.rs:1525-1543,1266-1287`; `economy.rs:78-88,1516-1531` |
| Paid | **Nobody pays for cargo.** Loading takes commons free and delivery gives them away free. | `economy.rs:1582-1599`; A1 row 3 |
| Income | `merchant_trade_income(r)` = Σ over this Phase 2's arrivals sourced at r of `qty × (1 − decay) × max(0, p_dest − p_r)`, ÷ `merchant_count(r)`. It is paid at the next wealth phase to **every merchant located in r** (`pool.regions`), whether or not it carried anything. No payer is debited. | `economy.rs:2082-2129`; `tick.rs:1541-1569` |
| Who reads merchant wealth | Treasury tax 5% and tithe base (no merchant debited, A1 D3), priest tithe share, domestic-credit capacity, luxury demand (wealth > 10), migration wage-gap pull, satisfaction rank. | `economy.rs:2281-2285`; `ffi/mod.rs:3620-3632`; AUDIT-A1 §1.4 |

### 1.2 Disruption, losses, war and quarantine [code]

| Event | What happens to cargo | Receipt (optional `--transaction-receipts`) | Evidence |
| --- | --- | --- | --- |
| Route edge gone before departure | reservation cancelled | `CANCELLED` | `merchant.rs:1217-1225,1470-1485` |
| Route edge gone in transit | BFS replan from the current region; failing that, unwound to the origin (return credit at **full value**, no decay) | `REPLANNED` / `RETURNED` | `merchant.rs:1439-1467`; `economy.rs:1582-1599` |
| Controller change of origin, destination or current region (`controller_changed_this_turn`) | Loading cancelled; Transit unwound to the origin; the region's ledger entries cleared | `RETURNED_CONTROLLER_CHANGE` | `merchant.rs:1326-1376`; `tick.rs:606-622` |
| Merchant dies | Loading cancelled; Transit unwound to the origin | **none**: outside the instrumented loops (declared) | `merchant.rs:1302-1318`; `transaction-receipts.md` |
| Maritime sea lane | whole cargo seized with probability `sea_raid_risk` (ChaCha stream per agent, lane and turn); destroyed | `SEA_CROSSING` + loss Raid | `merchant.rs:1385-1400,1490-1520`; `maritime.py:1275-1292` |
| Blockade, war, embargo, disposition below neutral, route suspension, city cut off | the edge is absent from the graph, so replan or unwind as above | as above | `economy.py:1422-1491`; `agent_bridge.py:394-412,1497-1506` |
| Quarantine `closure` (C1, on main) | cross-border edges of closed pairs leave the **agent-tick** merchant graph; relief grain and convoys build their own graph and stay open | as above | `agent_bridge.py:404-412,1504-1505,1542-1543`; `quarantine-rules.md` |
| Occupation, siege, conquest requisition | commons food multiplied away; cargo in transit untouched unless the controller changes | — | AUDIT-D §3 |
| Spoilage or disruption loss in transit | dormant enum values; only the one-time transit decay applies | — | `merchant.rs:204-210` |

**Transaction receipts are not a title ledger.** They neither assign cargo title nor make cash
claims (`transaction_receipts.rs:1-5`). They are bounded and drop rows past the limit. Death
releases are missing from them. Every row says `financial_eligible=false` and
`cargo_title_owner=null` (`transaction-receipts.md`). A4 must keep its own exact record.

### 1.3 How retail treats merchants [code + doc]

- Merchants load commons only (lead decision 7). Owned food is never in `region.stockpile`. Per
  pilot region-turn, retail records `merchant_food_departing` and `owned_food_unloadable_milli`;
  the latter is simply all owned food (`household_retail.py:1438-1452`).
- "Opening stock, merchant imports, convoy and granary grain stay commons"
  (`household_retail.py:26`). In a pilot region the commons are free rations
  (`household-retail.md` "Price and free rations"), so imports are given away.
- Foreign purchases and public grain shipments buy commons only. Owners' grain is sold only to
  their own ruler's granaries, pro rata to claims and credited by id (purpose 6)
  (`household_retail.py:1341-1436`). **This is the precedent for buying from owners.**

---

## 2. Owned goods and what buying them would take (Q2)

### 2.1 What owners hold today

| Stock | Owner and identity | Where | Can merchants load it? | Evidence |
| --- | --- | --- | --- | --- |
| Retail owned food | persons by stable id: `RetailRegion.claims` (milli-food) with a goods vector; `Σ claims == Σ goods`; cap 4,096 claims world-wide | Python only; sent to the economy as `retail_owned_<good>` each turn | **no** | `household_retail_state.py:67,151-170`; `economy.rs:540-582,1399-1403` |
| Workshop firm inventory (A3-1) | firm id = L1 site id; at most 20 loads; 1% wear | Python only. The same tick's output passes through the commons first; A3-2's column would end that. | **no** (the commons share is loaded free) | AUDIT-A3 §4, §6; `workshop_economics.py:84-90` (A3 branch) |
| PL1 timber store | region-bound earmark for RS2 (public, not by id); no decay | Python only; RS2 reads it ahead of the stockpile | **no**, by design | `timber-supply.md:167-175`; `repair_projects.py:383-401` |
| Granary grain | civ (ruler) | Python | no; public shipments and convoys | AUDIT-D §2 |
| Commons | nobody. A3 treats the region's controller as the commons owner for paid inputs. | native stockpile | yes, free | `workshop_economics.py:36-48` (A3 branch) |

**Correction to AUDIT-A3.** That audit called A3-2's owned-output column "the owned-goods path A4
extends". The column only keeps firm wares out of the commons. Native merchants would still load
only `RegionState.stockpile`, so the column does not let them carry owned goods. A4 has to carry
owned goods itself (§5).

### 2.2 What merchants buying from owners requires

| Need | Present? | What A4 must add |
| --- | --- | --- |
| Price at the origin | Yes. Retail's installed price `floor(clamp(food price, 0.5, 3.0) × ration × 1000)` per ration (`household_retail.py:956-965`): what local buyers paid this turn. A3's plan price for raw inputs and its sale price for wares. | reuse: owners receive the local price |
| Who sells | Procurement's pro rata take from claims (`take_procured`, `household_retail.py:1353-1376`; `_pro_rata` and `_draw` at `:203-216`) | the same rule over each owner's offer above a keep |
| Payment, merchant → owner | **No.** `transfer` is one-sided; `remit` is purpose 4 with a courier fee and refuses parties on a merchant trip (`wealth_transfer.rs:207-252`, `:229`). `money.py` refuses agent → agent (`money.py:255`, A3 branch) and treasury → agent (`:252`). | native `settle_pairs` (pairwise, purpose argument, no fee, no trip rule) plus a `money.py` pairwise bill |
| Title at purchase | Retail `_debit` moves claims and goods by equal totals with closures (`household_retail.py:341-403`) | new flow kind `sold_merchant` (origin pool → shipment) |
| Custody in transit | **none** for owned goods | Python `Shipment` record by id (§5.4) |
| Settlement at the destination | Native provisioning sells every installed claim pro rata to what is left, crediting sellers by id wherever they live (`provisioning.rs:623-660`; `wealth_transfer.rs:320-391`). Granaries buy owners' grain too (purpose 6). | consign the cargo as the holder's claim in the destination pool (flow `consigned_in`). **No new sale path.** |
| Losses | transit decay rates; maritime lane risk; retail owned decay and cap; A5 war hooks (`on_conquest`, `on_war_loss`, S1 branch) | apply the same rates to shipments (§5.6) |
| Fees | **none exist** for cargo; route income is a model `keep` income of +2 per route per side (`simulation.py:326-345`) | none in A4-1; a toll must replace route income (open question) |
| Returns | native unwind returns full value | returned cargo becomes the holder's claim at the origin (title kept) |

---

## 3. Timber-poor regions (Q3)

### 3.1 Why template worlds stall [doc + code]

- Template worlds have one or two timber regions, so most civs have no forest of their own or of
  nobody. `no_forest` is the largest PL1 refusal in every template world, and T1 never launches
  (`timber-supply.md:550-555`).
- In checkpoint 3's held template worlds 722 and 725, no arm paid anyone for repair work. No
  region joined the `paid_work` pilot and no expedition launched: "the chain never started"
  (`productive-recovery-screens-cp3.md:410-415`). The root is timber [inferred]: RS2 projects
  that cannot hold timber pay no wages, and PL1 has no forest to send a crew to.
- **Native trade cannot target the shortage** [code]:
  - raw-material demand is `soldiers × 0.3 + crafts' raw demand` (`economy.rs:1436-1445`);
  - RS2's need never enters it;
  - timber and ore are one category;
  - `best_cargo_slot` loads the origin's largest raw slot (`merchant.rs:754-786`), so ore often
    goes instead;
  - only crafts consume raw materials. Luxuries are never consumed at all: only food (step 3)
    and wares (step 3b) are drawn down (`economy.rs:1958-2003`).
- **PL1 never takes another civ's forest** (`timber-supply.md:123`). Cross-civ timber was out of
  scope.
- **Cross-civ trade is already possible on the merchant graph** [code]: cross-civ edges exist when
  both sides are at least neutral and there is no war, embargo or route suspension
  (`economy.py:1476-1491`).

### 3.2 Measured on template seed 1 [dev; one world, 200 turns]

Flags: the CP3 base plus `--timber-supply --recovery-crews --remittances --household-retail
--household-retail-boundary all`.

| Measure | Value |
| --- | --- |
| PL1 needs refused | 344 region-turns: `no_forest` 239, `forest_depleted` 105; 254 in regions with no timber slot |
| Refused gap | 1,211.8 timber |
| RS2 | 869 stalled project-turns, 512 of them `no_timber`; timber used 22.0 |
| Native timber arrivals, world | 20.0 over the run (14.8 cross-civ) |
| … into needy regions on refused turns | **0.24** (0.19 cross-civ) |
| Raw price at refused regions | median 0.24 (mean 2.43); raw demand median 0.3; zero demand in 21% |
| Free commons timber ≥ 1 within ≤ 1 / ≤ 2 merchant-graph hops | 84 / 107 of 344 (same civ 77 / 77; only other civs 7 / 30); bare adjacency within 2 hops: 175 |
| Gap coverable by that stock (upper bound; ignores sharing between needs and turns) | ≤ 1 hop 267; ≤ 2 hops 352 (29%); other civs only 107 |
| World free timber (quartiles of turns) | 0, 0, 0.11, 7.1, 85.7 |

Reading [inferred]:

- Trade moved almost no timber to where RS2 needed it.
- About a quarter of refused need-turns had free timber within two hops, mostly **in the same
  civ**. Nothing moves commons timber between a civ's own regions except merchants guided by
  price.
- A world this poor needs harvest as well as trade: cutting rights over foreign forests (D1 or
  diplomacy), or more labour on the existing slots.
- A4-3 can connect stalls to existing stock where trade and budgets allow. It cannot create
  timber.

### 3.3 Budgets for buyers [code]

- RS2 plans coins against the projected treasury after earlier Phase 2 bills, within the L9
  `repairs` envelope when `--local-budgets` is on (`repair_projects.py:66-77`).
- RS2 pays **nothing for timber**: commons and store timber are free (`_free_timber`,
  `:383-394`).
- A timber purchase would be a new treasury bill. It must be registered as pending so later
  planners see it (`workshops._pending_storage_bills`, `money.register_pending` as AUDIT-A3
  proposed).

---

## 4. Proxy replacement (Q4)

- **Replaced.** For every turn a carrier is reserved on a shipment (from the turn after dispatch
  through arrival), its whole ordinary income is withheld. For a Merchant that is
  `region.merchant_trade_income` at its location. The mechanism is the existing paid-work seam
  (`extend_paid_work` share 1.0; `paid_work_income`, `wealth_transfer.rs:527-540`; applied at
  `tick.rs:1600-1601`). Each receipt row is (id, share, income before, deducted): an exact
  person-turn record of the model income replaced, read through `livelihoods.paid_work_receipt`
  (`livelihoods.py:626`).
- **Why nothing stacks** [code]:
  - titled cargo lives in Python and never becomes a native `ArrivalRecord`, so
    `merchant_trade_income` (`economy.rs:2109-2129`) never counts it;
  - the carrier's share of the region pool is withheld;
  - after arrival the merchant is credited only by buyers.
- **Not replaced (declared remaining model share).**
  - Other merchants' `merchant_trade_income` on native commons trips. It is also paid to merchants
    who carried nothing, and to transit merchants at the wrong region's rate (issue I1).
  - Route income to treasuries.
  - Luxury trade income on goods nobody consumes (I6).

  A later rules version could make every native load a purchase. That is out of A4-1.
- **Buyers and sellers by identity.**

  | Flow | Payer | Payee | Purpose |
  | --- | --- | --- | --- |
  | Origin purchase | carrier (stable id) | owners (stable ids, pro rata) | new `cargo_purchase`, pairwise |
  | Destination sale | households (stable ids, native provisioning) | holder (stable id) | existing `food_purchase` (5) |
  | Destination granary | destination ruler's treasury | holder | existing `food_procurement` (6) |
  | A4-3 timber | carrier → origin treasury (commons owner); destination treasury → escrow → carrier | | `cargo_purchase` / `cargo_sale` |
  | A4-W wares | carrier → firm cash; households → holder | | `cargo_purchase` / `cargo_sale` |

- **Ledger (A1).** New channels `cargo_purchase` and `cargo_sale` (household side). Withheld
  income is attributed to package `titled_trade` (`WITHHELD_PACKAGES`). Sales stay in
  `food_purchase` and `food_procurement`; A4's own frame splits the holder credits by shipment.
  Registry rows to add, all append-only: `WEALTH_WRITER_METHODS` (`settle_pairs`),
  `WEALTH_ROUTERS` (`_native_pairs`), `WEALTH_WRITERS`, `MONEY_PURPOSE_CHANNELS`, `MONEY_BILLS`,
  `KNOWN_PURPOSES`, `money.MONEY_BOOKS` (`wealth_accounting_state.py:34-175`, A3 branch).
  The registry fails closed, so a missing row fails the guard test.

---

## 5. Design proposal: `--titled-trade` (default off)

### 5.1 Architecture choice

| Option | Custody | Native change | Verdict |
| --- | --- | --- | --- |
| **P. Python shipments with named carriers** (grain-convoy custody + PL1 crew handling) | Python `Shipment` by id: holders, position, path, cargo in integer milli | `settle_pairs` + purposes; `trade` category; planner skip (about 6 lines in `merchant.rs`); FFI | **Recommended.** Exact integer books; persisted in Python, so no native schema change; outcomes exactly once (convoy precedent); A5/D4/C1 hooks in Python. |
| N. Native titled trips (owned offers visible to the planner, a title flag per trip, a separate owned stream out of the delivery buffer) | native trip fields + a Python title overlay | Planner availability and title marking, a split delivery buffer, an exact unbounded titled-event frame, and either a persisted pool column (checkpoint schema change) or a per-turn re-installed title list. Touches `merchant.rs`, `economy.rs`, `ffi/mod.rs`, perhaps `pool.rs` and `tick.rs`, all ENFORCED. f32 cargo against integer books. | Heavier and riskier. Its advantages (carriers really move, so knowledge and contact follow; one planner and tally) are a later unification once P has shown the economics. |
| H. Settle native commons trips (buy from the origin's commons owner, sell to the destination's) | native trip | none for title, but the destination needs a buyer | Rejected. Outside retail pilots nobody pays for commons food, so the "buyer" would be a treasury acting as market maker: an invented purchaser. |

**Carrier semantics under P** (the PL1 boundary, declared). The carrier stays at home in the
native pool, exactly as PL1 crews do. A `trade` reservation keeps the native planner and every
other package's planner off it. Its ordinary income is withheld, and it does no native trade.
It still eats at home, and native migration, enlistment, occupation switching and death can
reach it. These are observed and handled (§5.6).

### 5.2 Switch, modes, prerequisites

- `--titled-trade` (livelihoods switch). It is inserted in `LIVELIHOODS_SWITCHES` after
  `household_retail` and `workshop_economics` and **before** `wealth_accounting`, so the ledger
  stays last (`livelihoods_state.py`, A3 branch; lead decision). Default off.
- `--titled-trade-mode`, append-only:
  - `trade` (default);
  - `record_only`: plans and records would-be shipments, buys and moves nothing; the trajectory
    must equal the switch off apart from its record.
- `--titled-trade-goods`, append-only per slice: `food` (A4-1); `timber` (A4-3); `wares` (A4-W).
- **Requires** `--agents hybrid` and `--household-retail` in mode `retail` or `no_relief`.
  `free_exchange` moves no money and `record_only` holds no food, so both are refused.
  - `timber` also requires `--timber-supply` and its prerequisites.
  - `wares` requires `--workshop-economics` and the A3-2 column.
  - Refused at startup and on resume, with a `--no-titled-trade` hint.
- Registration: `feature_catalog.REQUIREMENTS` `(_HYBRID, _feature("household_retail"))`;
  `batch_manifest.SIMULATION_ARG_KEYS`, omitted while unset (ENFORCED file: lead inverse layer);
  `livelihoods_resume_conflicts` refuses toggling it or changing its mode on an exact resume.
- `--no-titled-trade`: every live shipment ends `switched_off`. Its cargo becomes the holders'
  claim in the origin pool when that region is still a pilot, else commons there, dated.

### 5.3 Scope rule (A4-1)

- **Origins:** pilot regions whose owners hold food.
- **Destinations:** pilot regions with residents.
- Trips to or from non-pilot regions stay legacy native commons trips. Under `all`, nearly every
  controlled region is a pilot; uncontrolled regions are not on the merchant graph.
- Shipments buy **owned food only**. Commons food in a pilot region is the free-ration pool, and
  selling it for export would be an invented commons-owner sale.

### 5.4 State and identity (Python only; checkpointed)

`world.livelihoods.titled_trade` (`TitledTradeState`, schema 1, `exclude_if=None`, absent until
enabled):

- `enabled`, `mode`, `goods`.
- `next_shipment`: monotone, persisted, never reused. The shipment id is Program E's `shipment`
  entity.
- `shipments` (live, at most `MAX_SHIPMENTS` = 64, ascending id) and `closed` (the last 32).
- `book`: `money.MoneyBook` (settled keys, carry, flows).
- `frame` (completed turn, `frame_turn`), `counters` (fixed keys, lifetime), `log` (64 dated),
  `parameters`.
- Transient `_turn`: carriers' spouses read before the tick, this turn's events, and the retail
  money rows of holders.

`Shipment`:

- identity and route: `id`, `goods` (`food`), `carrier` (stable id, or None once released),
  `holders` `{stable id: share micro}` (title; the carrier at dispatch), `origin`, `dest`,
  `path`, `cursor`, `current`, `controllers_at_dispatch` (origin, dest);
- status: one of dispatched, moving, returning, arrived, returned, stranded, ended;
- dates: `dispatched_turn`, `last_moved_turn`;
- cargo and money: `cargo` (milli per retail good), `cargo_open`, `cost_milli`, `price_origin`,
  `price_dest_expected`;
- outcome: `losses` {transit_decay, sea_loss, war_loss}, `delivered`, `returned`, `deposited`,
  `outcome`, `closed_turn`, `war_exempt_turns`;
- `history` (at most 16 dated events: replanned, turned_back, carrier_released and why, estate).

Retail additions:

- `FLOW_KINDS` and `FLOW_SIGNS` append `sold_merchant` (−), `consigned_in` (+) and
  `returned_in` (+), after A5's `cap_overflow`. Flows are recorded only when nonzero, so dumps
  without A4 keep their bytes.
- Holders' claims are ordinary claims and count towards `MAX_CLAIMS`.
- A4's counters live in A4's state, not retail's.

### 5.5 Turn order (rows for the lead's single table)

| Order | Point | A4 action |
| --- | --- | --- |
| 1 | Phase 2 `reserve_first` (before every `prepare_phase2`) | Re-reserve each live shipment's carrier: `reserve_work(turn, TRADE, [(id, 1.0)])`. A carrier dead, absent, on an army roster, no longer a Merchant, or (an invariant violation) on a native trip is released: the shipment continues "consigned", without withholding. |
| 2 | Phase 2 `finish_phase2`, after L6a's install and RS2/PL1/PL3's extends | `extend_paid_work(turn, carriers, 1.0)` |
| 3 | tick 0.5 | carriers' ordinary income withheld (receipt) |
| 4 | tick 0.7 | native provisioning sells holders' claims at destinations and returns (purpose 5, credited by id) |
| 5 | tick 0.9 | the native planner skips `trade` holders (N4) |
| 6 | retail `after_agent_tick` | Retail settles. A seam hands A4 the per-id money rows of registered holders (P&L by shipment). A4 settles carrier deaths (estate, §5.6). |
| 7 | Phase 10 `tick_grain_reserves` seam | granaries procure owners' grain first, holders' claims included |
| 8 | retail `phase10`: a guarded A4 seam **before the frame closes** (so A4's flows are in retail's books for the turn) | (a) advance live shipments one edge (§5.6); (b) arrivals: decay, then consign as holders' claims (`consigned_in`); returns: `returned_in`; (c) plan and dispatch (§5.7): pro rata take (`sold_merchant`), `settle_pairs(turn, cargo_purchase, batch=origin, rows)`, create the shipment; (d) record shipment hops as trade-channel contact (`contact_ledger.record_shipment_hops`, new, unpinned) |
| 9 | Phase 10, last | the A1 ledger reads the money book, paid-work attribution and channels |

A shipment dispatched in Phase 10 of T moves its first edge in Phase 10 of T+1. It arrives in
Phase 10 of T+h and is first sold in the tick of T+h+1. The carrier is reserved for T+1 … T+h,
one turn per hop; like native merchants it "returns" home at once. Native one-hop latency is
similar: reserve at T, depart and arrive at T+1, credited at Phase 2 of T+2.

### 5.6 Rules: movement, outcomes, carrier lifecycle (no RNG)

- **Graph.** The agent-tick composition, rebuilt at A4's Phase 10 step:
  `economy.build_merchant_route_graph` → `maritime.merchant_route_graph` →
  `agent_bridge._city_route_graph` → `_quarantine_route_graph` (`agent_bridge.py:1497-1506`).
  A4 reads these helpers and does not edit the bridge. Quarantine closures therefore block
  shipments, and relief convoys stay open (C1 decision).
- **Move.** One edge per turn (native: one hop a tick). `MAX_HOPS` = 3, declared (PL1 uses 2;
  native merchants plan over the whole graph).

| Situation | Outcome | Book |
| --- | --- | --- |
| Next edge present | advance; on a sea lane with `sea_raid_risk > 0`, lose `floor(v × risk)` per good (deterministic expected loss in place of the native draw) | `sea_loss` |
| Next edge gone | BFS replan to the destination within `MAX_HOPS`; else turn back on the shortest path to the origin; else wait up to `WAIT_TURNS` = 2 (convoy precedent), then strand | event; strand below |
| Origin or destination controller changed since dispatch, or the destination left the pilot | turn back (native-consistent: `conquest_unwind` returns cargo whole) | event |
| Current region conquered, besieged or occupied | **A4-1: no loss**, counted `war_exempt_turns` (as retail v1 counted `requisition_exempt_region_turns`). A4-2 applies the A5 share. | counter |
| Arrival | transit decay once, `floor(v × TRANSIT_DECAY[g])` per good (`economy.rs:78-88`); rest consigned to holders' claims pro rata to shares (largest remainder, ties by id); a share beyond the claims cap goes to the destination's commons `claims_refused` | `transit_decay`, `consigned_in` |
| Returned to origin | full value (native returns do not decay), the holders' claims in the origin pool | `returned_in` |
| Stranded | holders' claims if standing in a pilot region; else commons there (title lost, dated; PL1 deposit and A5 `pilot_closed` precedents) | `deposited` |
| Pool rebuilt (legacy resume, fork) | every live shipment ends `pool_reset`: cargo to the origin's commons, dated (retail precedent) | `deposited` |

- **Carrier lifecycle.** Observed in retail's `after_agent_tick` (post-tick snapshot) and again
  at Phase 10.
  - **Death:** title passes to the spouse read before the tick, if alive. Otherwise it goes
    equally to living children anywhere (largest remainder, ascending id), as the native
    estate order does (`household.rs`). With no heir, it escheats at arrival to the destination's
    commons. Retail uses only children in the claim's region; a shipment has no region, so the
    native order is proposed (A5 decision).
  - **Migration, enlistment, occupation switch:** the carrier is released and the holder keeps
    title; the shipment continues consigned.
  - Withholding applies only while a carrier is reserved.

### 5.7 Rules: planning and purchase (A4-1, food)

For each pilot origin `o` (ascending) and each eligible carrier there (ascending id):

- **Eligible carrier:** an adult living Merchant resident in `o`. It must not be on a native
  trip (`trip_agent_ids`), not on an army roster, holding no work this turn, not already a
  carrier, and must have wealth above its reserve.
- **Destinations:** pilot regions with residents, within `MAX_HOPS` on the graph; the shortest
  path, ties to the lower region. Prices are known for markets within range (declared, like the
  native bootstrap without packets; A6 brings dated information).
- **Price function:** `p(r, Δ) = clamp(1 / (s_r + Δ / D_r), 0.5, 3.0)`, from this turn's food
  sufficiency `s_r` and food demand `D_r` (`economy_result`). It is retail's price before
  rounding, read as if `Δ` food units had moved. It includes a Python tally of live shipments
  and of this Phase 10's earlier plans (the native `MarketTally` rule).
- **Quantity:** the largest `q` (bisection, as `merchant::plan_load`) such that
  `p(d, +q)·(1 − d̄) − p(o, −q) ≥ LOAD_MARGIN` (0.25). `d̄` is the decay of the origin's goods
  mix. `q` is capped by:
  - the path capacity: land 2, river 5, sea 10 food units, the narrowest leg (`merchant.rs:474-480`);
  - the owners' offer, `Σ max(0, claim_i − OWNER_KEEP)` with `OWNER_KEEP` = 1,000 milli-food (one
    turn's two rations; declared harm limit);
  - the carrier's cash after `RESERVE` (6 rations at the home price).

  `q < MIN_CARGO` (10 milli) is no trip. The destination with the largest trapezoid margin wins,
  ties to the lower region.
- **Purchase (title passes now):**
  - each owner's take is pro rata to the offer (largest remainder, ties by id);
  - goods are pro rata to the pool's goods (`_draw`);
  - each owner is paid `ceil(q_i × price_origin / 500)` milli;
  - one `money.pay` pairwise bill, merchant → owners, purpose `cargo_purchase`, batch = origin.
  The whole bill is validated first against one fresh wealth read. A LIMITED payer row raises
  (a stale read). A seller ceiling refusal returns to the merchant (`return_to_payer`).
- **Owners' agency.** Owners sell like procurement sellers (passively, pro rata), at the price
  their neighbours paid. This is a declared modelling choice.

### 5.8 Native changes (precise; one batched build with A3-2 and D4's purpose)

| # | File | Change | Pin |
| --- | --- | --- | --- |
| N1 | `wealth_transfer.rs` | `pub fn settle_pairs(pool, turn, purpose, batch, rows: &[(u32, u32, i64)]) -> Result<Vec<PairRow>, &'static str>`. Validation before any change: `purpose ∈ PAIRWISE` (`cargo_purchase`, `cargo_sale`); payer ≠ payee; no duplicate (payer, payee); `0 < amount ≤ MAX_ROW_MILLIS`; key `(turn, purpose, batch)` not in `wealth_transfer_log`. Each row in order: either party dead or unknown → ABSENT, nothing moves; else `sent = min(amount, floor_millis(w_payer))`, `credited = min(sent, floor_millis(MAX_WEALTH − w_payee))`, `refunded = sent − credited` (stays with the payer). The payer loses `credited`; LIMITED when `sent < amount` or `refunded > 0`. **No trip rule:** title-based remote payment, as retail settlement. Logs the key. `PairRow {payer, payee, requested, sent, credited, refunded, status}`. | unpinned (reference only) |
| N2 | `wealth_transfer.rs` | `PURPOSES` append `cargo_purchase` and `cargo_sale` after A3's `wares_purchase` (7). Codes are fixed by the lead with D4's `restitution` (AUDIT-D §7.2), e.g. 8, 9, 10. | unpinned; test expectations `test_recovery_skills_native.py:30`, `test_household_retail_native_ffi.py:97`, `test_money.py`, ledger `KNOWN_PURPOSES` |
| N3 | `workshop_work.rs` | `RESERVATION_CATEGORIES` append `trade` (4); update the Rust test at `:347` | unpinned |
| N4 | `merchant.rs` | In `merchant_mobility_phase_at`'s planner selection (`:1558-1565`), build once the set of ids with a `trade` reservation for `turn` from `pool.work_reservations` and skip them. With no `trade` rows the set is empty, so behaviour is bit-identical. | **ENFORCED** (`crisis_candidate_source_inverse.json`) |
| N5 | `ffi/mod.rs` | `#[pymethod] settle_pairs(turn, purpose, batch, rows: Vec<(u32, u32, i64)>) -> Vec<(u32, u32, i64, i64, i64, i64, u8)>`; drops `snapshot_cache` when anything moved (as `remit_wealth`, `:915-922`). `reserve_work` already takes a category index. | **ENFORCED** (15 layers) |
| A3-2 | `economy.rs`, `ffi/mod.rs` | A3's `workshop_owned_crafts` column (AUDIT-A3 §6) | ENFORCED (6, 15) |

- **No persisted native state.** Reservations, the pending paid work and the key log are
  transient (`pool.rs:1882-1885`). The checkpoint schema is unchanged. Extension identity changes
  once for the whole batch.
- **Feature-off identity of the new extension.** `settle_pairs` is never called. No `trade` row
  exists, so the planner is identical. The appended purposes change only
  `wealth_transfer_purposes()`. Check with `turn_speed_identity` (9 cases) against `8abc1acb`
  and the preceding main, each with its own extension.
- **Not needed:** `tick.rs`, `pool.rs`, `economy.rs` (beyond A3-2), `transaction_receipts.rs`,
  `schema.rs`.

### 5.9 Python files and pins (preflight, read only; `preflight-summary.txt`)

- **New:** `titled_trade.py`, `titled_trade_state.py`, `tests/test_titled_trade.py` (a new
  offline chunk in `scripts/run_python_oracle_checks.py`), and `tests/test_titled_trade_native.py`
  (enrolled in `scripts/testing/native_shards_manifest.json`).
- **Edited, reference only (no enforced pin):**
  - `household_retail.py` and `_state.py`: seams `sell_to_merchant`, `consign`, holders' money
    rows, the phase10 call and the flow kinds;
  - `money.py`: pairwise bill kind, `_native_pairs` router, `MONEY_BOOKS`; for A4-3 an `escrow`
    account kind;
  - `wealth_accounting.py` and `_state.py`: channels and registry rows;
  - `livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py`;
  - `contact_ledger.py`: `record_shipment_hops`;
  - `action_engine.py` and `war/occupation.py`: A4-2 hook calls beside retail's;
  - `repair_projects.py` and `timber_supply.py`: the A4-3 store and need seams;
  - `wealth_transfer.rs`, `workshop_work.rs`.
- **ENFORCED:**
  - `batch_manifest.py` (20 layers): the manifest keys, the lead's inverse layer;
  - `merchant.rs` and `ffi/mod.rs` (N4, N5);
  - `economy.rs` (A3-2).
  - Read only, not edited: `agent_bridge.py` (4), `economy.py` (5), `simulation.py` (11),
    `grain_reserves.py` (9), `transaction_receipts.py` and `transaction_receipts.rs` (1 each).
- **The viewer:** a `titledTrade.ts` reader and panel; a "shipment" entity in the chain view.

### 5.10 Checkpoints and resume

- Only Python state is persisted. Native installs, receipts and reservations are transient.
- An exact resume mid-shipment continues the same shipments. `book.settled` and the native key log
  refuse a repeated `(turn, cargo_purchase, origin)`.
- A legacy JSON resume or pool rebuild ends every shipment `pool_reset` (title bound to ids that
  a rebuilt pool reuses).
- Resume refusals: saved A4 outside hybrid; retail off or in `free_exchange`/`record_only`;
  toggling the switch or its mode. A pickled world without the field loads (`getattr` default).

### 5.11 Invariants (each raises)

1. **Goods close.**
   - Per retail good: `Σ pools + Σ live cargo` changes only by retail flows and A4 losses or
     deposits.
   - `sold_merchant` = new cargo.
   - `consigned_in + returned_in` = delivered + returned.
   - Per shipment: `cargo_open = transit_decay + sea_loss + war_loss + delivered + returned +
     deposited` at close, with exactly one terminal outcome.
2. **Money closes.**
   - Per pairwise row: `requested ≥ sent = credited + refunded`, and the payer's net loss =
     `credited`.
   - No LIMITED payer row in a purchase.
   - Bill total = Σ `ceil(q_i × p / 500)`.
   - Nothing is minted; f32 application within A1 D4 tolerance.
3. **Exactly once.**
   - `(turn, purpose, batch)` once, both natively and in `book.settled`.
   - A shipment moves at most once per turn (`last_moved_turn`).
   - Ids are monotone.
   - One terminal outcome per shipment.
4. **No double duty.** Every reserved carrier is a living Merchant and in no
   `trip_agent_ids()` result at `reserve_first` or Phase 10. It holds exactly one `trade`
   reservation and one paid share.
5. **No stacking.** Every carrier-turn has a paid-work receipt row with share 1.0 attributed to
   `titled_trade`. A4 cargo never appears in `get_pending_arrivals`.
6. **Retail.** `check_region` and `check_owner` hold with the new kinds. Holders' claims stay
   under `MAX_CLAIMS`.
7. **Ledger.** A1's world and region identity holds with the new channels; continuity `exact`.

### 5.12 Test plan

- **Rust:**
  - `settle_pairs`: validation before mutation (bad purpose, payer = payee, duplicate pair,
    range, repeated key); payer limited at zero; payee ceiling refund; ABSENT; parties on trips
    allowed; conservation per row;
  - the category list;
  - planner skip: a reserved idle merchant is not planned and an unreserved one is; with no
    `trade` rows, stats and pool are bit-identical to before.
- **Offline (stand-in native; a new chunk, 110 s limit kept):**
  - the price function and bisection (gap ≥ margin, capacity, cash reserve, `OWNER_KEEP`, tally
    herding);
  - pro rata purchase and payment rows;
  - movement: advance, replan, turn back, wait, strand;
  - sea expected loss; decay at arrival only; returns at full value;
  - consign and claims-cap refusal;
  - carrier death (spouse, children, escheat), migration, enlistment, occupation switch;
  - `record_only` identity with the switch off;
  - pool reset; switch off;
  - resume conflicts; invalid combinations (no retail, `free_exchange`, retail `record_only`,
    non-hybrid);
  - JSON and pickle round trips with live shipments.
- **Native (real extension, development world):**
  - wealth before and after each pairwise row;
  - carriers never planned natively;
  - paid-work rows of carriers;
  - exact checkpoint resume at (a) a turn with live shipments and holders' claims at a
    destination, (b) the turn before an arrival, (c) the turn before a carrier's death equals a
    straight run;
  - A1 ledger closure with A4 channels;
  - `CHRONICLER_CHECK_RESOURCES=1`.
- **Identity:**
  - feature-off `turn_speed_identity` against `8abc1acb` and the preceding main;
  - the new extension with every feature off equals the old one;
  - `checkpoint_identity` `hybrid_s42_long` and `proc32_hybrid_s11` with A4 and retail `all` on.
- **Viewer:**
  - the A4 reader keeps absent, malformed, unobserved (null frame) and recorded zero distinct;
  - lint and build.

### 5.13 Slices

- **A4-1 (Python + the batched native build):** everything in §5.2-5.12 for `food`. Declared
  limits:
  - war does not reach cargo in transit (counted);
  - prices are omniscient within `MAX_HOPS`;
  - carriers stay home natively;
  - no fees;
  - non-pilot trade stays legacy.
- **A4-2 (losses, seizures, returns with A5/D4/C1):**
  - `titled_trade.on_conquest(world, region, attacker, defender, via)` and
    `on_war_loss(world, region, survival, cause, actor)`, called beside retail's hooks
    (`action_engine.py` and `war/occupation.py` on the S1 branch). Cargo standing in the region
    loses `v − floor(v × survival)` per good once per event, recording cause, actor and victim.
  - Under D4 `--war-requisition transfer` the taken share feeds army rations. The minted refill
    falls by the same amount, and holders are recorded as victims for restitution.
  - Capture by an enemy holder of the next region (the convoy `hostile_holder` precedent; captor
    and title decided with D4).
  - C1: closure waits and turn-backs, plus a forgone-margin receipt per closed pair for C1's
    cost record.
  - Fees only if the owner decides a toll replaces route income.
- **A4-3 (timber-poor supply; requires `--timber-supply`):**
  - **Orders:** for each region whose PL1 need was refused (`no_forest`, `too_far`,
    `forest_depleted`, `forest_busy`), the gap net of live PL1 and A4 timber in transit.
  - **Supply:** shipments carried by merchants resident at origins with free commons timber
    (stock less native commitments, RS2 holds and the origin's own RS2 want), any civ the graph
    connects. Bought from the **origin's controller treasury** (A3's commons-owner rule) at
    A3's plan price; a merchant → treasury collection, `cargo_purchase`.
  - **Delivery** into the destination's **PL1 store**, so RS2 reads it first and merchants,
    crafts, the cap and conquest never see it.
  - **Payment:** the destination treasury puts the order price into a Python `escrow` account at
    dispatch, as a pending bill within the L9 `repairs` envelope. It is released to the carrier
    per delivered unit (`cargo_sale` credit rows) and the rest is refunded for losses or returns.
  - **Order price** (declared): the origin plan price ÷ (1 − 0.01 per hop) × (1 + `FREIGHT` per
    hop), since RS2 demand is not priced natively.
  - On template 1, at most about 29% of the refused gap was within reach [dev, upper bound].
- **A4-W (wares, after A3-2):**
  - merchants buy firm inventory (merchant → firm cash, `cargo_purchase`) at A3's sale price;
  - they sell at the destination by A3's Phase-10 household rule with the holder as seller
    (households → holder pairwise, `cargo_sale`); delivered into the commons for the next tick;
  - an unsold lot stays with the holder (1% wear) or returns.

### 5.14 Evidence plan (CW5)

- **Cohort.** CW5, shared S4: template 771-776, procedural 871-876 (`connected_world_screens.py:47`,
  RESERVED). Timing pilot on the shared seeds 5 and 19. The arms are preregistered within CW5's
  freeze. Extractors are validated on a development world first.
- **Base** (200 turns): `--agents hybrid --food-allocation --household-retail
  --household-retail-boundary all --grain-reserves --public-grain-shipments --wealth-accounting`,
  with retail rules v2 when A5 is merged.
- **Arms:**
  - `R0`: base;
  - `TT`: `--titled-trade`;
  - `TT_rec`: `--titled-trade-mode record_only`. It must equal `R0` except for its record, and
    gives activation with no effect.
  - If A4-3 lands before the freeze: `C` = base plus the CP3 chain (`--grain-storage --workshops
    --operating-wear --repair-projects --timber-stock --timber-supply --recovery-crews`) and
    `C_TT3` = `C --titled-trade --titled-trade-goods food,timber`.
- **Primary outcomes** (2-3, signs not forced):
  1. **Food access:** priced-out person-turns per pilot person-turn (`TT − R0`), with exporters
     and importers reported separately.
  2. **Merchant livelihoods:** merchants' net money (realized holder credits − purchases − model
     income withheld; A1 channels) and the merchants' priced-out rate (the A2 link).
  3. (A4-3 arm) RS2 `no_timber` stalled project-turns and granary mean condition in PL1-refused
     regions (`C_TT3 − C`).
- **Fixed harm panel:**
  - population; famine region-turns; children priced out; exporters' priced-out;
  - food destroyed (transit decay, sea loss, unsold claims' decay);
  - treasury, including the created tax on merchant wealth (A1 D3);
  - merchant Gini and satisfaction; merchant migration;
  - epidemic deaths and trade-channel contact; the A1 model share.
- **Activation per world, before reading outcomes:**
  - at least one shipment dispatched, one sold and one returned or stranded;
  - every retail, ledger and shipment closure true;
  - carriers never on native trips;
  - `TT_rec ≡ R0`.

  Inactive worlds are reported, never dropped.
- **Compute.** 8 s per template run measured here (retail `all` + chain); procedural not
  measured. 12 worlds × 3-5 arms ≈ 36-60 runs, under one core-hour [inferred]. The ceiling is
  set from the timing pilot.
- **Dev expectation (template 1)** [dev, inferred]: pairs with a profitable gap in 160/200
  turns. Of 249 origin-turns with a pair, 190 had a merchant holding at least 1 wealth unit. So
  A4-1 should activate on at least some template worlds; volumes are small (owned food per
  stocked pilot median 8.8 food units).

---

## 6. Risks (Q6)

1. **Goods counted twice between commons and owned stock.**
   - Cargo leaves the origin pool inside retail's Phase 10 books, before the next Phase 2. It is
     never in the commons, nor in two pools.
   - Native merchants still cannot load owned food.
   - Holders' claims reach prices once, through `retail_owned_*`.
   - Timber goes into the earmarked store. The origin buys only free commons timber (less native
     commitments, RS2 holds and its own RS2 want).
   - The A3-2 column is needed before wares, or firm output keeps leaking into the commons.
2. **Money created.**
   - None by construction: pairwise rows are conserved, refusals return to the payer, and A4-3
     escrow closes. f32 application is within A1 D4.
   - Watch the **created** treasury tax and tithe on merchant wealth (A1 D3). It grows if
     merchants get richer.
   - Withheld model income lowers created money.
3. **What merchant wealth means.** Merchants become traders who need capital.
   - Poor merchants cannot trade.
   - Cash is tied up in cargo during shipments: carriers could be priced out at home. `RESERVE`
     mitigates.
   - Margins can be negative.
   - Withheld model income could exceed realized margins, the same shape as A2's wage result.
   - Merchants were 46% of priced-out person-turns at `paid_work` (A2 §4.3). On template 1 under
     `all` their model income was about 24.6 over 200 turns, because no food moved [dev]. A4
     changes who can buy food.
   - Every reader of merchant wealth shifts: tax, tithe, priest income, credit capacity, luxury
     demand, migration pull, satisfaction rank (AUDIT-A1 §1.4).
4. **Exports.** Higher origin prices price out non-owners at the origin. `OWNER_KEEP` protects
   only owners' own next rations. The harm panel splits exporters from importers. Under `all`, A4
   is the only inter-regional food channel, so effects can be large.
5. **Quarantine (C1).**
   - Shipments must use the closed agent-tick graph, not the grain graph.
   - Their hops must be recorded as trade contact. Otherwise A4 trade carries no disease, closure
     costs caravans nothing epidemiologically, and C outcomes are biased.
   - A4's lost margins and C1's forgone route income are different quantities and must not be
     summed as one cost.
6. **War.**
   - In A4-1, shipments are a war-loss loophole compared with A5 v2 owned stock (declared and
     counted; fixed in A4-2).
   - D4's requisition must take shipments at the same events, exactly once.
   - Two conquests in one turn: shipments turn back once (idempotent by `last_moved_turn`).
7. **The carrier boundary** (PL1's). No physical movement, so no packets or contact from the
   person, and food demand stays at home. Native migration, enlistment or an occupation switch
   mid-shipment releases the carrier.
8. **Native planner skip.** Carriers withdraw from native trade, so native commons trade changes
   (feature-on only).
9. **Omniscience.** Destination prices are known within `MAX_HOPS` (declared; A6).
10. **Claims cap** (4,096 world-wide). Holders add claims in many regions. Template 1 peaked at 81
    [dev]; procedural worlds were not measured.
11. **Timing.** Shipments move in Phase 10, native merchants at 0.9. The graph state is unchanged
    between them [inferred; test].

---

## 7. Issues found

| # | Issue | Class | Evidence |
| --- | --- | --- | --- |
| I1 | `merchant_trade_income` is computed per origin with transit merchants counted at their origin (`ffi/mod.rs:3564-3596`), but paid by **current** region at 0.5 (`tick.rs:1541-1569`). Transit merchants get the region they pass through's per-merchant rate and dilute their origin's. The paid total differs from the computed pool. | model-accounting inconsistency (default path; record, do not fix; the A1 ledger should itemize computed against paid) | code |
| I2 | Merchant income is paid to every merchant located in a region whether or not it carried anything, and debits nobody | model source (A1 row 3) | `tick.rs:1566-1569` |
| I3 | Death-in-transit unwinds write no receipt; receipts are bounded | declared boundary; A4 must not use receipts for title | `merchant.rs:1302-1318` |
| I4 | RS2 timber need is absent from raw demand; timber and ore share a category; the planner loads the largest raw slot | model property; A4-3's target | `economy.rs:1436-1445`; `merchant.rs:754-786` |
| I5 | Under retail `all`, native food arrivals were 0 over 200 turns (template 1), against about 400 per run by default | intentional boundary (lead decision 7) with a large effect; A4-1's target | [dev]; `bulk-trade-crafts.md:44` |
| I6 | Luxury (precious) is never consumed, yet luxury deliveries earn merchant income | model property | `economy.rs:1958-2003`, `:2109-2129` |
| I7 | Spoilage and disruption losses are dormant; cargo decays once on arrival | known | `merchant.rs:204-210` |
| I8 | AUDIT-A3's statement that A3-2 gives "A4 its owned-goods path" | correction (§2.1) | `merchant.rs:754-786` |
| I9 | `money.py` refuses agent → agent and treasury → agent payments; `remit` refuses parties on trips | design gap for A4 | `money.py:248-255` (A3); `wealth_transfer.rs:229` |

---

## 8. Open questions (lead or owner)

1. **Architecture.** P (Python shipments, native planner skip) or N (native titled trips)?
   Recommended: P now, N as a later unification.
2. **Scope.** A4 only between retail pilot regions, with non-pilot trade staying legacy and its
   model income declared? Should evaluation fix the boundary at `all` (or A2R `schedule`)?
3. **Owners' agency.** Pro rata sale above `OWNER_KEEP` at the local price (the procurement
   precedent), or a reservation price?
4. **War in A4-1.** Return without loss (counted) until A4-2, or adopt the A5 share at once?
5. **Carrier estate order.** Spouse, then children anywhere, then escheat at arrival (the native
   order), or retail's children-in-region rule?
6. **Fees.** No toll exists. Any toll must replace the model route income (+2 per route per side)
   rather than stack on it. Wanted?
7. **A4-3 price and payment.** Cost-plus freight with escrow at dispatch, or the destination
   raw price paid on delivery?
8. **Native batch composition and purpose codes.** `wares_purchase` 7 (A3, on its branch),
   `cargo_purchase`, `cargo_sale`, `restitution` (D4); the `trade` category; the `merchant.rs`
   skip; the A3-2 column. Witness layers for `merchant.rs`, `ffi/mod.rs`, `economy.rs` and
   `batch_manifest.py`.
9. **Merchant capital.** Should domestic credit finance cargo later?
10. **I1 disposition.** Record only, or a rules version?

---

## 9. Not verified here

- That the probe left the trajectory unchanged. It only reads state; no comparison run was made.
- The counterfactual for I5 on template 1 without retail: not run. The 400-per-run figure is the
  template mean from `bulk-trade-crafts.md`.
- Procedural-world magnitudes: merchants, claims, price gaps, timber reach.
- That the `turn` the native mobility phase sees equals the reservation turn Python passes
  [inferred from the tick wiring; to be tested with N4].
- That every pair counted in §3.2 had buyers who could pay. The pair count ignores destination
  cash.
- That `household.rs`'s estate order is exactly spouse, then dependants, then children (taken
  from AUDIT-D §1.2).

---

## Appendix: probe method

- **Command**, from this directory:
  `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1 PYTHONPATH=/home/user/Chronicler/src
  ~/.venvs/chronicler-native/bin/python probe.py run1/probe_t1.jsonl -- --seed 1 --turns 200
  --agents hybrid --simulate-only --grain-reserves --public-grain-shipments --scholarship
  --techniques --academy-services --grain-storage --food-allocation --workshops --operating-wear
  --repair-projects --timber-stock --timber-supply --recovery-crews --remittances
  --household-retail --household-retail-boundary all --output run1/chronicle.md
  --state run1/state.json`
- **Environment.** Module path verified as `/home/user/Chronicler/src/chronicler`. Extension
  `chronicler_agents…so` SHA-256 `101a4cd5b928b14f…`; Rust identical to `8abc1acb` and
  `8286804c`. Wall time 8 s, 200 records.
- **Wrappers** (this process only, reading state):
  - `timber_supply.prepare_phase2`: the economy tick's pending arrivals via
    `get_pending_arrivals`;
  - `timber_supply.phase10` (after the original):
    - PL1's refused needs;
    - free commons timber (`read_stockpile_commitments`) reachable on the agent-tick graph
      composition and on bare adjacency;
    - raw price and demand;
    - merchants per region from the snapshot;
    - the model income from `economy_result.merchant_trade_incomes`, approximated by
      merchants' positions at the Phase 10 snapshot;
    - retail pilots: band-clamped food price, owned food, claims, and pilot pairs.
- **Analysis:** `analyze.py run1/probe_t1.jsonl`, plus the inline computations recorded in §3.2
  and §5.14.
