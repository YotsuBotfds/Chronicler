# Audit A3: workshop economics (inputs, owners, customers, payroll, inventory, closure)

Design-audit lane for Program A3 of the connected-world program, 2026-11-06. Read-only on
`/home/user/wt/a1-ledger` (branch `claude/cw-a1-ledger`, head `fee5de7f`: `8abc1acb` plus the
A1 observation ledger; `git status` clean before and after). Native extension for the one probe:
`~/.venvs/chronicler-native`, `chronicler_agents…so` SHA-256 `101a4cd5b928b14f…` (the CP2/CP3
build; Rust identical to `8abc1acb`).

Binding inputs: the program brief (A3) and AUDIT-A1-A2 sections 0, 1, 3.3, 5 and 7. `wealth` is
the one spendable balance. New payers pay through one helper that validates the whole bill first.
Refused credits go back to the payer unless a named sink is declared. Paid flows replace model
income one source at a time, never stacked.

Labels: **[code]** read in source (file:line at `fee5de7f`); **[dev]** measured on one development
world by this lane (template seed 1, 200 turns; exploratory, not evidence for any screen);
**[inferred]** reasoning, not tested; **[unverified]** stated but not checked.

Scratch files in this directory: `probe.py` (in-process wrappers, no repository change),
`analyze.py`, `analyze2.py`, `run1/probe_t1.jsonl` (200 per-turn records), `preflight.json`,
`preflight2.json`, `preflight-summary.txt`.

---

## 0. Answers in brief

1. **A workshop today is two stacked packages** [code]. L1 (`--workshops`) is a public asset: the
   controller's treasury builds it, maintains it and repairs it as a disclosed sink. A named crew of
   urban farmers gives its already-diverted time. The crew's work replaces the region's craft
   ceiling. The native economy turns commons timber and ore into wares in the commons. L6a
   (`--workshop-payroll`) adds a debt-free firm keyed by the site id. The firm has cash, title to the
   *leftover* output, and one customer: academy procurement, paid from the treasury. It pays wages
   by id, owes arrears and closes after 6 insolvent turns. **Paid flows:** academy sales, wages,
   distributions and asset bills. **Model-created or free:**
   - raw inputs (never paid);
   - the people's same-tick use of the crew's output: **47.5% of firm-region output was never
     titled** [dev];
   - L1B public production with no firm (62 site-turns) [dev];
   - the owner's asset subsidy, which is not on the firm's books.

   Nothing mints money into firm cash, and no firm survival is guaranteed: `no_customer` closes
   every firm.
2. **Real non-academy demand exists but nobody pays for it** [code]. Every region's people want
   0.01 wares per head per turn (`cities.py:204,1103`). The native tick takes that from the commons
   pool free (`economy.rs:1992-2003`), and it feeds the material need (`needs.rs:449`). Merchants
   carry commons wares by price (`merchant.rs:673-678,843`). Prices are scarcity ratios:
   `1.0 × demand / max(supply, 0.1)` (`economy.rs:120,154,1448-1452,1857-1863`). Actual customers can
   come from three places without inventing demand: (a) the firm region's households, paying
   before use; (b) merchants buying for scarce markets (A4); (c) academies (existing).
3. **Prices make honest crafting loss-making in firm cities** [dev, one world]:
   - The wares price was above the raw-material price in only 12.6% of 199 operating site
     region-turns, and in 25 of 137 operating firm-turns.
   - Over the run, at L6b's price band [0.5, 3.0], the firm's output was worth 42.7 units, its raw
     inputs would cost 151.1, wages due were 33.15 and academy sales were 87.0.
   - The cause: the L1 ceiling enters raw demand even when raw goods are short, wares glut the city,
     and crafting is volume-neutral (1 raw load → 1 wares load).

   So paid inputs will close most firms unless A4 opens scarce markets or the owner changes the
   value of wares. This is the central open question (§9 Q1). I report it rather than tune it away.
4. **Labour is not double counted today** [code]. Crews take only the urban diverted share that
   `farm_labor_factor` already removed from farming. Every other named-work package uses the one
   native registry, and its planners run first or exclude holders. Drafts skip registry holders. The
   remaining issues are not duplication: idle diverted time keeps its model income, and legacy
   crafts in non-site cities are free, unnamed producers that compete with firms (§3).
5. **Recommended design** (§4): `--workshop-economics`, default off, requiring `--workshop-payroll`.
   It has no hooks of its own; payroll's hooks call it.
   - **Inputs:** prepaid. The ceiling is capped by what firm cash can buy at last turn's
     band-clamped raw price. Actual native inputs are charged to firm cash and paid to the
     controller's treasury as owner of the commons. No free inputs.
   - **Capital and opening:** one owner capital transfer at opening, with no rescue afterwards. Firms
     open without an academy order. A site without a firm produces nothing (L1B free production is
     retired under the switch).
   - **Household customers:** in Phase 10 after academy sales, at the band-clamped post-trade
     price. Buyers are debited by id through `money.py`. Paid wares go into the region's commons for
     the next turn's use.
   - **Payroll and closure:** wages, arrears and insolvency as L6a, plus an `idle` closure.
   - **Accounting:** firm-cash and inventory closures are exact in integers, with new A1 ledger
     channels. No RNG.
6. **`money.py`** (§5): `quote`/`pay` over typed accounts (`civ_treasury`, `firm_cash`,
   `agent_wealth`, `sink`) with a declared residual policy. It validates the whole bill before
   moving anything, keys each payment `(turn, purpose, batch)` exactly once, and registers every
   flow for the ledger. **Native need for A3:** append the purpose `wares_purchase` to
   `wealth_transfer.rs` (households pay through debit rows of the existing `transfer`). Pairwise
   agent-to-agent settlement is A4's need, not A3's.
7. **Slices:**
   - **A3-1:** Python plus the purpose append. No enforced pin except the lead's `batch_manifest`
     layer.
   - **A3-2 (native):** an owned-output column in `economy.rs`. It ends the free same-tick use and
     free loading of firm wares, and gives A4 its owned-goods path.
   - **CW2 held screen:** after A3-2, so household demand is not confounded by free use (§7).

---

## 1. What a workshop is today

| Aspect | Rule today | Class | Evidence |
| --- | --- | --- | --- |
| Site and identity | At most 4 open cities of rank ≥ 1, one per region, admitted by (rank, size, settlement id). Site id from the monotone persisted `next_site`, never reused. A closed city is never readmitted. | stable id | `workshops.py:154-185`, `workshops_state.py:96`, `:168-170` |
| Ownership | Public. The civ controlling the region at Phase 2 pays every asset bill. Arrears, condition and construction belong to the asset and pass to a conqueror. The L6a firm "belongs to the site", follows it through a controller change, and distributes surplus to the *current* controller. No guild, city purse or person owns anything. | — | `workshops.py:336-355,433-486`; `workshop_payroll.py:328-354`; `workshop-finance.md` "Accounts and identities" |
| Asset finance | Construction 60 in installments of 10, upkeep 3 a turn, arrears capped at 15 with 0.05 wear, repair 20 below 0.5 condition. Treasury `keep` debit after a successful tick, as a disclosed public expenditure sink (no recipient). L9 can gate funding (`workshop_funded`). | paid, to a sink | `workshops.py:83-90,300-310,351,458-461` |
| Labour | Native planner: up to 8 living adult (≥ 20) farmers resident in the site's settlement and region. Excludes trips, army rosters and registry holders, by ascending id with RS1/RS3 priority. Each gives `d × hours`, where `d = 1 − URBAN_FARM_LABOR[rank]` (0.2/0.3/0.4). | named | `workshop_work.rs:205-230`; `workshops.py:367-391`; `cities.py:194` |
| Production | Operating site: region craft ceiling replaced by `K_RAW_PER_WORK (2) × W` (not added); building, unfunded or crewless sites set it to 0. Native conversion: `Q = min(ceiling, Σ raw on hand − departures)`, pro rata over timber and ore, 1:1 into wares in the **commons** pool. | free inputs | `workshops.py:414-426`; `economy.rs:1405-1434` |
| Inputs | The region's timber and ore in `region.stockpile` (commons): last turn's stock plus this turn's harvest, less merchant departures, after grain-storage and RS2 holds by phase order. **Nobody is paid.** The farmers who harvested them already got model farm income (none in L6b pilot regions, where farm income is replaced by food sales only). | **free** | `economy.rs:1410-1427`; `workshops.md` L1B "Inputs"; AUDIT-A1-A2 §1.2 rows 1, 9 |
| Who uses the output | (1) The region's people, in the same tick, 0.01 a head, from the pool. (2) Same-tick merchant departures. (3) Storage wear and cap. (4) L6a titles `min(output, uncommitted stock, room)` after the tick. Titled 34.9 of 66.5 loads (52.5%) [dev]. | free use | `workshop_payroll.py:446-453,480-487`; `economy.rs:1992-2003` |
| Firm opening | Only around an "open order": last turn's fully informed academy procurement of the region's ruler left need and budget. Otherwise the site stays an L1B public workshop, producing into the commons (62 such site-turns) [dev]. | — | `workshop_payroll.py:428-440,565-582` |
| Customers | Academies of the region's ruler, fully informed this turn, after their own market procurement. Need `min(learners, 8 × scholars) − held`; price = the academy's procurement craft price; budget = projected treasury and the L9 `teaching_supplies` envelope. Delivered at once within the realm. | paid (treasury → firm cash) | `workshop_payroll.py:545-562,591-638`; `local-budgets.md:34` |
| Academy market purchases | Remove commons crafts and charge the treasury as a domestic fiscal sink: money destroyed, no seller. `learning_services.py` is witness-pinned. | sink | `learning_services.py:330-355` |
| Payroll | Paid-work share armed in Phase 2. The native wealth phase withholds that share of ordinary income. In Phase 10 the firm pays `500 milli × share` plus arrears, pro rata when short (largest remainder), through `transfer_wealth` purpose 0, batch = site. Ceiling refusals stay in cash. Dead workers' claims lapse. | paid | `workshop_payroll.py:268-325,456-458,666-677`; `wealth_transfer.rs:125-166` |
| Arrears | Wages owed by id (at most 16 claims), paid first from later cash; lost on overflow, liquidation or pool reset. | — | `workshop_payroll.py:292-324,506-519` |
| Unsold inventory | Up to 20 loads (title stops beyond it), 1% wear a turn (the native rate), returned to the commons at liquidation. | declared sink, give-away | `workshop_payroll.py:88-91,373-382,678-685` |
| Pressure and closure | Wages owed at turn end → hours −0.25 (floor 0.25). From the 2nd turn in a row, crew cap −2 (floor 1). After 6 in a row: liquidation and site closure `insolvent`. A solvent turn restores one step. Cash above 4 full wage bills is distributed. | no guaranteed survival | `workshop_payroll.py:686-713` |
| Wear and repair | PL2: 0.02 a turn while operating, offset only by RS1 qualified upkeep; repair by the L1 lump or RS2 (treasury-paid crew, purpose 3). | — | `workshops.py:283-297,480-483`; `operating-wear.md` |
| Books | Integer closures for cash (`cash = sales − wages − distributions − write-offs − stipends`) and inventory; typed money and material transfers, last turn only. | — | `workshop_payroll.py:228-235`; `workshop_payroll_state.py:23-41` |
| Checkpoint | Python state persisted; `_turn`, native installs, receipts and the key log are transient. Exact resume tested at turn 76 with open firms. | — | `workshop-finance.md` "Native seams", "Tests" |

**Model-created or free, versus paid.** Paid: academy sales (treasury → firm; that treasury is partly
created money, A1 D3), wages, distributions, stipends and asset bills (to a sink). Free or
model-created:

- raw inputs;
- the people's and merchants' same-tick draw on the crew's output;
- L1B free public production when there is no firm;
- the crew's model farm income for diverted time under L1B alone;
- merchant model income on wares carried out of firm cities (A1 row 3);
- the asset subsidy (about 3 units of upkeep per built turn against about 0.24 units of wages per
  firm-turn [dev]), which is not in the firm's P&L.

**No minted firm revenue and no guaranteed demand:** the `no_customer` mode closed 3 of 3 firms in
L6a's dev runs.

---

## 2. Demand: who wants workshop output and at what price

### 2.1 Mechanisms [code]

- **Households (native, unpaid).** `craft_demand = 0.01 × region agents`, for every region,
  children included (`cities.py:204,1103`).
  - Phase A adds the demand to the wares category (`economy.rs:1437-1442`).
  - Step 3b takes `min(demand, stock)` from the commons wares pool (`:1992-2003`).
  - Sufficiency `stock / demand` (clamped to [0, 2]) restores the material need, at a rate of
    `0.006 × min(1, sufficiency) × deficit` (`needs.rs:449`, `agent.rs:362`).

  Use is a **regional aggregate**. There is no per-person wares purchase or consumption anywhere.
- **Merchants (native, model-paid).** Wares travel by price like any good but are not advertised
  in trade packets (`merchant.rs:673-678,843`). Cargo is loaded from the commons free of charge. The
  merchant's income on delivery is model-created (A1 row 3; `economy.rs:2083-2125`).
- **The state.** Academy procurement (above) is the only public purchaser of crafts. No RS2, PL1,
  granary or BUILD path buys wares (grep of `"crafts"` in `src/chronicler`). Guild and city purses
  are separate Python balances with no wares demand.
- **Other civilizations.** Only through merchants. No cross-civ procurement of wares exists.
- **Prices.** Pre-trade price is `base_price (1.0) × demand / max(available, 0.1)`. Post-trade
  price is `demand / max(available − exports + imports, 0.1)`. These are per category, and the
  academy and L6a treat them as coins per load (`economy.rs:120,154,1448-1452,1857-1863`). City
  crafts can work `0.1 × civilians` raw loads (`cities.py:197,1120`), about 10× the people's
  0.01-a-head demand, so cities glut and the rest of the world is short (bulk-trade-crafts §3:
  city sufficiency 0.92-1.37, elsewhere 0.21-0.27).

### 2.2 Measured [dev] (template seed 1, 200 turns, L6a's dev flags; `run1/probe_t1.jsonl`)

The probe reproduces L6a's published seed-1 row exactly: 2 firms, sales 98 units in 33 sales,
titled 34.9, delivered 33.6, wages 33.15 due / 32.92 paid, distributed 63, lapsed 0.23. It is
therefore faithful to source.

| Region-turns | n | wares price median / mean | raw price median / mean | wares price > raw price | people's demand / turn | craft output / turn | sufficiency median |
| --- | --- | --- | --- | --- | --- | --- | --- |
| operating site regions | 199 | 0.487 / 1.147 | 2.75 / 9.70 | **12.6%** | 0.375 | 0.639 | 2.0 |
| other city region-turns (mostly sites while building) | 60 | 4.10 / 3.69 | 0.337 / 1.86 | 83% | 0.41 | 0 | 0.0 |
| non-city regions | 1341 | 0.40 / 1.17 | 0.0 / 0.73 | 51% | 0.13 | 0 | 0.0 |

Per operating firm-turn (137):

- output 66.5 loads from 66.5 raw loads (1:1); titled 34.9 (52.5%);
- people's demand in firm regions 52.3 loads;
- wares price above raw price in 25 of 137 turns;
- **at the L6b band [0.5, 3.0]:** output value 42.7, input cost 151.1, wages due 33.15, academy
  sales 87.0 units;
- household demand at band prices 75.9 at most;
- academy sales happen on turns when the firm city's own wares price is high: median implied
  price 3.40 against 3.30 for the city, against 0.85 for the city over all turns.

A static recomputation of the proposed Phase-10 household sale on this trajectory: a gap on 143 of
152 firm-turns, 54.1 loads in all, 35.5 meetable from inventory, about 40 units [dev, inferred; the
trajectory would differ].

Reading:

- **The firm's own ceiling inflates the raw price it would pay.** L1 puts `K × W` (up to 4.8) into
  raw demand whether or not the raw goods exist, so supply sits near the 0.1 floor [code + dev].
- **Its output gluts the city.** Local value added is negative in about 82-87% of operating turns
  [dev, one world].
- **Under A3's prepaid ceiling the price should fall.** Raw demand becomes what the firm can pay
  for, so the spike should shrink [inferred]. The A3 screen must measure this, not assume it.
- **Where actual customers come from without invented demand:**
  - local households, who must pay before use and are free riders today;
  - scarce markets reached by merchants: other cities while their crafts idle (median price 4.1)
    and wares-short non-city regions. This needs A4 title through transport;
  - academies.

  Nothing else in source wants wares.

---

## 3. Labour: sources and double counting [code]

| Work consumer | Who | Time source | How exclusion from workshop crews holds | Evidence |
| --- | --- | --- | --- | --- |
| Farming | all farmers | farm share; urban farmers farm `URBAN_FARM_LABOR[rank]` | The crew uses only the diverted `1 − u`, which `farm_labor_factor` already removed. L6b title weights `u_i(1 − h_i) − r_i` exclude it. | `workshops.py:20-23`; `household_retail.py:575-604` |
| RS2 repair crews, PL3 workshop pool | named | registry `repair` | reserved before the L1 planner (`_before_repair_crews`) | `workshops.py:238-243,371-372`; `repair_projects.py:599,664` |
| PL3 granary crews | named | registry `repair`; storage work | planner excludes registry holders | `recovery_crews.py:239-247,412` |
| PL1 woodcutters | named, whole turn | registry `repair` in `reserve_first`; farm share via `woodcut_labor_away` | `reserve_first` runs before every `prepare_phase2` | `timber_supply.py:34-50,557-560`; `livelihoods.py:646-655` |
| RS1 apprentices and mentors | named | registry `apprentice`; mentors' upkeep and teaching time | taken out of `W` (`_crew_maintenance`); stipends from firm cash after wages | `workshops.py:270-280,410-413`; `workshop_payroll.py:733-788` |
| Academy teaching | scholars (not farmers) | registry | disjoint occupation; registry holders excluded | `workshops.md` L1A item 2 |
| L5 learners | named | `reserve_work` refuses holders | registry | `learning_cohorts.py:37-48` |
| Rural health work | farmers outside cities | `health_work_loss` | planned after health; urban farmers are not health-eligible | `workshops.md` L1A; source audit "Rural health work" |
| Army drafts | soldiers drafted | — | drafts skip registry holders | `workshops.md` R1 |
| Native tick | — | — | refuses to run if anyone holds more than one commitment | `workshops.md` L1A item 2 |

No double counting was found. Three issues remain, none of them duplication:

- **(i) Idle diverted time keeps its model income** (pre-existing). Non-crew urban farmers in a site
  region have diverted time that does nothing, while their full model farm income continues
  (`workshops.md` "Unused diverted time is not silently returned to farms").
- **(ii) Legacy crafts outside site regions** work 0.1 raw load per civilian, non-farmers and
  children included, with free inputs (`cities.py:1120`). They are a free, unnamed producer whose
  wares compete with firms through merchants. Classify this as an intentional boundary of A3.
- **(iii) C1's proposed border guards** take farm time through `farm_labor_factor` (AUDIT-C C1.2).
  They must not draw on the urban diverted share crews use. That is a coordination item.

A3 changes labour only through *production-planned employment*: the firm requests crew time its
prepaid inputs can occupy (§4.3).

---

## 4. Design proposal: `--workshop-economics` (default off)

### 4.1 Switch, modes and registry

- `--workshop-economics` (livelihoods switch). Modes (`--workshop-economics-mode`, declaration
  order, append only):
  - `market` (default);
  - `free_inputs`: the cost control; inputs are planned and recorded but charged at 0;
  - `academy_only`: no household customers; isolates non-academy demand.
- Requires `--workshop-payroll` (so `--workshops` operate, `--agents hybrid`). Any payroll mode is
  accepted: `no_customer` is the constructed demand collapse and `unpaid_labor` a labour control.
  It does **not** require academy services.
- Refused outside hybrid, without payroll, or with workshops in `observe`/`cost_only`, at startup
  and on resume. Adding or dropping it on an exact resume is refused
  (`livelihoods_resume_conflicts`). `--no-workshop-economics` liquidates every A3 firm with a dated
  reason `switched_off`.
- Registered in `feature_catalog.REQUIREMENTS` as `(_HYBRID, _feature("workshop_payroll"))` and in
  `batch_manifest.SIMULATION_ARG_KEYS`, omitted while unset. `batch_manifest.py` is ENFORCED, so the
  lead adds an inverse-witness layer as for `cwa1`.
- **No hooks of its own.** `workshop_payroll`'s and `workshops`' hooks call it through RS0-style
  guarded seams (`_lane_active(world, "workshop_economics")`). Its effects therefore run at payroll's
  position (7th), before L9 settlement, RS1 stipends, L6b and the A1 ledger. The module is
  inserted in `LIVELIHOODS_SWITCHES` **before** `wealth_accounting`, so the ledger stays last. This
  is the lead's decision. Insertion changes nothing in worlds without the container (feature-off
  identity) [inferred; verify with `turn_speed_identity`].

### 4.2 State (Python only; checkpointed)

- `WorkshopFirm` gains optional fields (`exclude_if=None`, so L6a dumps are unchanged):
  - `capital` (milli received);
  - `input_price_milli` and `input_price_turn` (the last observed band-clamped raw price);
  - `idle_run`;
  - `totals` keys `capital`, `inputs`, `household_sales`.

  The cash identity extends to:

  ```
  cash = capital + sales + household_sales − inputs − wages − stipends − distributed − written_off
  ```

  Absent keys read 0, so `check_firm` is unchanged for L6a.
- `world.livelihoods.workshop_economics` (`WorkshopEconomicsState`, schema 1):
  - `mode`, `enabled`;
  - the completed-turn `frame` (A3 receipts, at most 4 + 8 closed firms);
  - `flows` (typed money and material, at most 512, last turn);
  - `counters` (fixed keys), `parameters`, a 64-entry dated `log`;
  - `settled` `{(purpose, batch): turn}` (exactly once across exact resumes);
  - transient `_turn`.
- The firm id is the L1 site id (monotone, never reused). This is Program E's `firm` entity.

### 4.3 Turn order (rows for the lead's single table)

| Order | Point | A3 action |
| --- | --- | --- |
| 1 | Phase 2, `workshops.prepare_phase2` → `_crew_terms` | Payroll's `crew_terms` returns (cap, hours) **limited by prepaid inputs**: `W_max = R / K`, with `R = floor(B / p_in)` and `B = max(0, cash − owed − this turn's wage bill at those terms)`. `p_in` is last turn's band-clamped post-trade raw price of the region (persisted). If `p_in` is unknown, R = 0 (unknown, not zero, recorded). |
| 2 | same, ceiling | New seam `_firm_input_cap(world, site)` → `ceiling = min(K × W, R)`. A selected site **without a firm** gets ceiling 0 under A3, so there is no free-input L1B production. |
| 3 | native economy | unchanged (A3-1) |
| 4 | Phase 2 finish (workshops, then payroll) | Asset bill as today. Payroll titles (L6a rule, A3-1). Input charge = `ceil(Σ native craft_input[timber, ore] × p_in)`, which is ≤ B by construction. Paid firm cash → controller treasury (`keep`) through `money.pay(purpose="firm_input_purchase")`. No native purpose is needed because both accounts are Python. The paid-work share is armed. Closed sites are liquidated. |
| 5 | agent tick | wealth phase withholds the crew's share (unchanged) |
| 6 | Phase 10: academy procurement (pinned), granaries, then payroll `phase10` | (a) Academy sales (unchanged). (b) **Household sales** (mode `market`). (c) Wages owed and due (unchanged). (d) Inventory wear. (e) Insolvency, hours, layoffs, `insolvent` closure, and the new `idle` closure. (f) Distribution above the reserve, now `RESERVE_TURNS × (wage bill + input bill at full crew)`. (g) **Opening:** an operating site with no firm opens one if the controller's projected treasury covers `CAPITAL`; `money.pay(purpose="firm_capital")` moves it treasury → firm cash, **once per firm**. Production starts next turn. |
| 7 | Phase 10, last hook | the A1 ledger reads the `money` register (new channels, §4.7) |

**Household sale rule** (Phase 10 (b); no RNG; ascending id):

- Gap: `G = max(0, 0.01 × living residents − (region commons crafts − merchant commitments))`.
  Residents are read from the post-tick snapshot, with the same counting rule as
  `cities.economy_columns`. Free commons wares are used first.
- Quantity: `Q = min(inventory, G)`, in milli-loads.
- Price: `p_out = band(this turn's post-trade craft price)`, in milli per load.
- Each resident is offered an equal share of Q (largest remainder). Each pays
  `ceil(q_i × p_out / 1000)` milli, reduced to what their own snapshot wealth covers. Those who
  cannot pay are counted as `priced_out`.
- Payment: one `money.pay` collection, `agent_wealth` debits → `firm_cash`, purpose
  `wares_purchase` (native code 7, appended), batch = firm id.
- Delivery: exactly the paid quantity moves from inventory into `region.stockpile["crafts"]` and is
  used by the next turn's native step 3b. Paid equals delivered; there are no refunds.

Bought wares the next tick does not use (when imports arrive first) remain commons. This is a
declared limit, counted as a static upper bound.

### 4.4 Price and payee rules (declared, not calibrated)

| Parameter | Value | Reason |
| --- | --- | --- |
| price band | [0.5, 3.0] | the L6b precedent (`household_retail.py:82-83`); avoids the 0.1 supply-floor spikes |
| input payee | the region's controller treasury (owner of the commons) | the only real account that owns commons raw goods today. Producers by id need raw-goods title and replacement of their model farm income (A3-3, with A5 and L6b) |
| `CAPITAL` | 4 × (full-crew wage bill + input bill at band cap) | covers the first turns of prepaid inputs; returned through distribution and liquidation; never repeated |
| `IDLE_CLOSE_AFTER` | 6 | no production, no sale and cash below one minimum bill for 6 turns in a row → `idle` liquidation (otherwise a firm that cannot buy inputs is a zombie with no wages owed) |
| `K_RAW_PER_WORK`, `WAGE_PER_WORK`, `INVENTORY_CAP`, `WARES_WEAR`, hours and layoff steps | L1 and L6a values | unchanged |

### 4.5 What A3 replaces, never stacks

| Model element today | Under A3 | Note |
| --- | --- | --- |
| The crew's ordinary income share | wages (L6a withheld share) | unchanged |
| L1B free public production (commons output from free inputs) at sites without a firm | none: ceiling 0 without a firm | removes a free-input producer |
| Free use of firm-held wares by the region | paid purchases from inventory | A3-1 partial (the same tick's output still passes through the pool); A3-2 complete |
| Free commons raw inputs | paid to the commons owner | no new household income |
| Merchant model income on wares from firm cities | A3-2 stops free loading of firm wares; A4 replaces it with realized margins | not stacked |

The only credits to households remain wages. Household spending on wares, input payments and
capital are transfers between named accounts.

### 4.6 Demand-collapse cases (natural, each recorded with its cause per firm-turn)

Every firm-turn with no sale records `customer_absent` reasons from a fixed, append-only list:
`no_academy`, `academy_full`, `commons_covers`, `households_cannot_pay`, `no_controller`,
`depopulated`, `quarantine`, `market_closed`.

- **War:** conquest changes the owner and the academy customer (the firm follows the site). City
  fall or region change → liquidation (inventory to the commons, cash to the controller, owed wages
  written off). Firm inventory and cash under siege, occupation and requisition belong to A5/D4.
- **Epidemic and depopulation:** demand falls with residents, and crew deaths lapse claims. Both
  register as `depopulated` when the region's residents fall by at least 25% over 10 turns.
- **Quarantine (C1):** closed cross-border merchant edges affect raw imports and exports (A4 era).
  A3 exposes `customer_access(world, region, kind) -> bool | reason`, which C1 can veto; slice 1
  implements none.
- **Commons competition:** imports or legacy wares cover demand (`commons_covers`).
- **Input collapse:** timber exhaustion (L3), RS2/PL1 holds or high raw prices leave R = 0, which
  leads to `idle` closure.
- **Constructed control:** payroll `no_customer`.

### 4.7 Records and ledger

`snapshot.livelihoods.workshop_economics` (stage `A3`, schema 1, `source_turn`):

```
{schema_version, stage: "A3", mode, source_turn,
 units: {money: "milli_treasury_units", wares: "milli_loads", milli: 1000},
 firms: [{firm, region, settlement_id, owner, opened_turn, status, capital, cash, inventory,
          owed, idle_run, insolvent_run, closed_turn, closed_reason}],
 receipts: null | [{turn, firm, region, owner,
   inputs: {price_milli, price_turn, budget_milli, ceiling, used: {timber, ore}, charged_milli,
            payee: ["civ_treasury", civ] | null, unknown_reason},
   produced, titled, free_use_upper_bound,
   sales: [{customer: ["academy", seat] | ["households", region], quantity, price_milli, paid}],
   households: {residents, demand, commons, gap, offered, bought, paid, buyers, priced_out},
   customer_absent: [reason...], capital_in, wages_due, wages_paid, owed_after, worn, returned,
   distributed, written_off, cash_open, cash_close, inventory_open, inventory_close,
   owner_asset_spend, event}],
 flows: null | {money: [...], materials: [...]},
 counters: {...}, log: [...], parameters: {...}}
```

- Readers keep **absent**, **malformed**, **unobserved** (`receipts: null`) and **recorded zero**
  distinct (`wealth_accounting.record_status` reference).
- L6a payroll records keep their shape. New money kinds (`capital`, `input_purchase`,
  `household_sale`) and material kinds (`household_delivery`, `free_use`) are appended to the kind
  tuples. `viewer/src/lib/workshopFinance.ts` must accept them in its closure, or it will refuse A3
  runs. That reader change ships with A3-1.
- `owner_asset_spend` shows the subsidy the firm's books exclude.
- A1 ledger: new channels `wares_purchase` (households → firm cash; household out),
  `firm_input_purchase` and `firm_capital` (firm ↔ treasury; treasury side). The `firm_cash`
  closure in `wealth_accounting._payroll` (`:374-407`) is extended. It reads the `money.py`
  register instead of guessing.

### 4.8 Invariants (each raises)

1. **Firm cash closes.** It closes exactly in integers (§4.2) and is ≥ 0. The only credits are
   `capital` (once per firm) and sales. **No rescue:** any other credit kind raises.
2. **Inventory closes.** `produced/titled − sold − worn − returned`, with 0 ≤ inventory ≤ cap.
3. **No free inputs.** In a firm region on an operating turn: native input ≤ ceiling ≤ R, and
   `charged = ceil(input × p_in) ≤ B`. Native conversion in a site region with no firm is 0.
4. **Household sales close.** Σ applied debits = firm cash credit; delivered = Σ q_i paid;
   `charged_i = ceil(q_i × p_out / 1000)`; nothing is delivered without payment.
5. **One paid share per person.** One paid-work share per person per turn. Crew ⊂ registry
   workshop holders. Crew time ≤ diverted share.
6. **Exactly once.** Each `(turn, purpose, batch)` settles once (native key log plus persisted
   `settled`). Stale frames read as null.
7. **Ledger closure.** The A1 ledger's world and per-region identity holds with the new channels;
   continuity stays `exact`.

### 4.9 Pinned files at risk (`refactor_preflight.py`, read-only; `preflight-summary.txt`)

- **References only:** `workshops.py`, `workshops_state.py`, `workshop_payroll.py`,
  `workshop_payroll_state.py`, `livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py`,
  `wealth_accounting.py`, `cities.py`, `local_budgets.py`, `household_retail.py`,
  `wealth_transfer.rs`, `workshop_work.rs`, `provisioning.rs`, `needs.rs`.
- **ENFORCED:**
  - `batch_manifest.py` (19; the lead's layer for the manifest key);
  - `learning_services.py` (1; read only, never edited);
  - `simulation.py` (11; not needed: the hooks exist);
  - `economy.py` (5; not needed in A3-1);
  - `economy.rs` (6), `ffi/mod.rs` (15) and `ffi/schema.rs` (3) (A3-2 only);
  - `ffi/batch.rs` (1), `lib.rs` (6), `tick.rs` (8), `merchant.rs` (1) and `agent_bridge.py` (3)
    (not needed).
- **Behavioural expectations to update with the purpose append (not hash pins):**
  `tests/test_recovery_skills_native.py:30` (exact list) and
  `tests/test_household_retail_native_ffi.py:97` (`purposes[5:]`). New native test files need
  native shard manifest enrollment.

### 4.10 Test plan

- **Feature-off identity.** `turn_speed_identity` 9 cases against `8abc1acb` and the preceding
  `main`, each with its own extension; the new extension differs only by the appended purpose.
  `--no-workshop-economics` explicit: 0 differences.
- **L6a identity.** `--workshop-payroll` without A3 on the new extension equals the old extension,
  in history, world and state.
- **Offline (native stand-in; a new chunk or one with headroom; 110 s limit kept):**
  - prepaid ceiling bounds (no cash, no input; half the budget gives half the ceiling);
  - unknown price → R = 0, recorded;
  - charge ≤ budget; capital once; refused opening when the treasury is short;
  - household split, limits, priced-out count, commons-first, paid = delivered;
  - `academy_only` and `free_inputs` modes;
  - `idle`, `insolvent`, `city_fell`, `region_changed` and `switched_off` liquidations;
  - conquest moving the owner and customer;
  - ledger channel closures; JSON and pickle round trips at a mid-arrears turn;
  - invalid combinations (no payroll, observe/cost_only, non-hybrid, resume toggles).
- **Native (real extension, development world):**
  - every `wares_purchase` debit checked against wealth before and after; repeated key refused;
  - input charge equals native `craft_input × p_in`;
  - no native craft output in a site region without a firm;
  - exact checkpoint resume at (a) a live payroll turn with arrears and inventory, (b) the turn
    before an `insolvent` or `idle` closure (closes on the same turn with identical liquidation),
    and (c) the turn before an opening (capital).
- **All switches.** `checkpoint_identity` `hybrid_s42_long` and `proc32_hybrid_s11` with A3 on
  (plus L6b, RS1, RS2, PL2, L9, A1), with resume points inside arrears and on a closure turn.
- **Resources check.** `CHRONICLER_CHECK_RESOURCES=1` all-switch procedural run.
- **Viewer.** The A3 reader (absent / malformed / unobserved / zero); the L6a reader accepting A3
  kinds; lint and build.

---

## 5. The `money.py` seam (shared: A3, A4, B3, C2, D4)

```python
# src/chronicler/money.py — Python; no RNG; integer milli; deterministic order.
PURPOSES: dict[str, int]   # registered name -> native code (append-only); verified once against
                           # sim.wealth_transfer_purposes(); Python-only purposes (treasury <-> firm)
                           # have code None and never reach native.
ACCOUNT_KINDS = ("civ_treasury", "firm_cash", "agent_wealth", "sink")

@dataclass(frozen=True)
class Account:  kind: str; ident: int | str          # civ index | firm id | stable agent id | sink name

@dataclass(frozen=True)
class Bill:
    purpose: str; batch: int; phase: str
    payer: Account | None          # one payer -> many payees (payment)  ... or
    payee: Account | None          # many payers -> one payee (collection: agent debits)
    lines: tuple[tuple[Account, int], ...]   # counterparty, milli > 0, unique, ascending
    whole: bool = True             # payment: all-or-nothing against the payer; collection: per line
    residual: str = "return_to_payer"        # or "sink:<declared name>"

def quote(world, sim, bill, *, acc, book) -> Quote      # validate + compute; moves nothing
def pay(world, sim, bill, *, acc, book) -> Receipt      # validate the whole bill, then move
```

- **Validation before any move.**
  - purpose registered; amounts integer and positive; counterparties unique; `(turn, purpose,
    batch)` not in `book.settled`;
  - payer coverage:
    - `civ_treasury`: `_treasury_budget(world, civ, acc)` less registered pending bills ≥ the whole
      units needed. A shared `register_pending(civ, units)` replaces the ad hoc
      `_pending_storage_bills` composition for new payers.
    - `firm_cash`: cash ≥ total.
    - `agent_wealth` collections: each line is limited to `floor(wealth × 1000)` from one snapshot
      read.
- **Moves.**
  - Treasury debits: whole units through `acc.add(..., "keep")`, with the sub-unit remainder
    prepaid in `book.prepaid[(civ, purpose)]` (the RS2/PL1 rule).
  - Agent credits: `sim.transfer_wealth(turn, code, batch, +rows)`; agent debits: the same call
    with negative rows.
  - Firm cash: adjusted by the applied amounts. Treasury credits: whole units, with the sub-unit
    remainder following `residual`.
- **Residuals.** Ceiling refusals and absent ids: `return_to_payer` (firm cash not debited;
  treasury carries it as prepaid or not charged), or a declared sink (the PL3 precedent).
  Collections create no residual: what a buyer cannot pay is simply not bought.
- **Receipt and register.** The receipt carries per line `(requested, applied, residual, status)`,
  totals, units charged, prepaid before and after, and the sink. It is appended to a transient
  per-turn register the A1 ledger reads (channel = purpose). The package keeps its own frame.
  `book` (`settled`, `prepaid`) lives in the calling package's persisted state, so exact resume
  refuses repeats.
- **Native additions.**
  - **A3:** append `"wares_purchase"` (7) to `wealth_transfer::PURPOSES`. No new function: a
    household → firm payment is a set of debit rows of the existing `transfer`
    (`wealth_transfer.rs:125-166`, debits limited at zero). A firm → household payment is credit
    rows (exists).
  - **A3-3 producers payee:** `"firm_input_sale"`.
  - **A4:** a generic pairwise `settle_pairs(turn, purpose, batch, [(payer, payee, amount)])` for
    merchant ↔ household. This is `remit` without the fee and trip rules, with a purpose argument.
  - The lead should batch purpose appends across programs (A3 `wares_purchase`, D4 `restitution`
    per AUDIT-D, A4) into one native build, to change extension identity once.
  - Existing packages are not refactored onto the seam (witness pins and output identity).

---

## 6. Slices and dependencies

**A3-1 (Python plus one purpose append; smallest honest slice).**

- **Scope:** `money.py`; `--workshop-economics` with modes; prepaid inputs paid to the commons
  owner; owner capital; opening without an academy order; no L1B free production under A3;
  household customers (Phase 10, for the next turn's use); `idle` closure; demand-absence reasons;
  A1 ledger channels; the viewer reader; tests (§4.10).
- **Files:** new `money.py`, `workshop_economics.py`, `workshop_economics_state.py`; edits to
  `workshop_payroll.py`, `workshop_payroll_state.py`, `workshops.py` (two guarded seams),
  `livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py`, `wealth_accounting.py`;
  `batch_manifest.py` (lead layer); `wealth_transfer.rs` (one line plus a Rust test); two Python
  test expectations; the viewer.
- **Declared limits:**
  - the same tick's output still passes through the commons, so the share of demand not bought
    and same-tick merchant departures draw on it free (`free_use_upper_bound`);
  - per-person buyers (no household adults paying for children);
  - academies still delivered realm-wide without transport.
- **Optional split:** `money.py` plus the purpose append as A3-0 (no behaviour change) before A3-1.

**A3-2 (native owned output).**

- An optional nullable Float32 column `workshop_owned_crafts` (null = legacy region). When set:
  - this region's crafted output is not added to the commons pool (reported in `craft_output`;
    Python adds it to inventory exactly);
  - the firm's stock at opening counts in wares availability for prices only;
  - the native conservation summary gets an owner-transfer outflow.
- This mirrors L6b's `retail_owned_*` plumbing (`ffi/mod.rs:3494-3530`, `economy.rs:1256-1260,1399`).
- Effects: free same-tick use and free merchant loading of firm wares end; the custodian title
  retires under A3. Optionally households buy in Phase 2 for same-tick use.
- Witness layers for `economy.rs` and `ffi/mod.rs` (ENFORCED); a native build; identity: the
  column absent ⇒ bytes unchanged.
- This is the owned-goods path A4 extends.

**A3-3 (later):** input payee = producers by id where raw-goods title exists (extend L6b title to
timber and ore slots in pilot regions, whose farmers' model farm income is already replaced),
purpose `firm_input_sale`.

**Dependencies.**

- **A4 (merchants):** the main value channel given §2.2. Merchants buy owned wares at the origin
  (debit merchant rows into firm cash), carry them with title (A3-2's native path) and sell at the
  destination. Merchant model income on that cargo is replaced by the realized margin. Merchants
  also deliver raw inputs to firms (A4 sellers). The pairwise native op belongs to A4.
- **B3 (repair):** workshop-asset repair stays treasury-paid (RS2). Timber and registry contention
  with infrastructure repair; placement order in Phase 2 (`reserve_first`, then planners) must
  include B3's kinds (AUDIT-B §9). B3 must not add unclassified coin sinks.
- **C1 (quarantine):** cross-border edge closure affects firm imports and exports only once A4
  exists. A3 provides the `customer_access` veto seam and the `quarantine` absence reason. C1's
  guards must not draw on the urban diverted share.
- **D4:** requisition, restitution and reconstruction must reach firm inventory and cash (owned
  stock), and workshop assets (RS2 war damage), exactly once. Purpose append coordination.
- **A5:** firm inventory is owned stock. Siege, occupation, conquest (today the firm keeps
  everything and follows the site), death of the owner civ, and repeated same-turn transitions need
  A5's exactly-once rules.
- **A1:** firm cash as a ledger account; the new channels. **E:** firm entity = site id; viewer
  readers.

---

## 7. Evidence plan (CW2)

Cohort per AUDIT-E §5.4: template **741-746**, procedural **841-846** (32×10), RESERVED, shared
with A5. Timing pilot on the shared seeds 5 and 19. Run CW2 **after A3-2**: under A3-1, household
demand is confounded by free use of the same tick's output. A3-1 gets development-world mechanism
checks and identity and checkpoint tests only.

- **Base** (200 turns): `--agents hybrid --scholarship --techniques --academy-services --workshops
  --workshop-payroll --grain-reserves --public-grain-shipments --wealth-accounting`.
- **Arms:**
  - `P`: L6a status quo;
  - `E`: `--workshop-economics`;
  - `E_free`: mode `free_inputs`;
  - `E_acad`: mode `academy_only`;
  - `E_nc`: `E` with `--workshop-payroll-mode no_customer` (constructed collapse; activation and
    harm only);
  - secondary `E_noA`: `E` without academy services (non-academy-only worlds).

  60 primary runs at about 7 s (template, measured) to under a minute (procedural, unmeasured):
  under 0.3 core-hours.
- **Primary outcomes** (2-3, preregistered, signs not forced):
  1. **Firm viability:** open firm-turns per operating site-turn, and closures by reason by turn
     200. Contrasts `E − P` and `E − E_free` (the input cost).
  2. **Paid non-academy demand:** household `wares_purchase` milli and its share of firm revenue
     (`E − E_acad`), with crews' wages net of income replaced (A1 channels).
  3. **Wares access:** priced-out-of-wares person-turns and craft sufficiency in firm regions, and
     sufficiency in non-city regions (the export harm before A4).
- **Fixed harm panel:** population; owner treasury net (capital + asset spend − distributions −
  input receipts); material need and satisfaction; merchant income and wares delivered by
  merchants; food priced-out (if L6b is on); the A1 model share.
- **Activation checks (per world, before reading outcomes):**
  - at least one firm opened, one input charge and one household sale;
  - every ledger closure true and continuity `exact`;
  - no native craft output in a firm-less site region;
  - the identity control exact.

  Worlds without a firm are reported as inactive, never dropped. Natural demand-collapse events
  are counted by cause. Extractors are validated on a development world before the freeze; source,
  extension and schema identities are recorded.

---

## 8. Defects and issues found

| # | Issue | Class | Evidence |
| --- | --- | --- | --- |
| W1 | L6a custodian rule: the region's people and same-tick departures draw on the crew's output before title; 31.6 of 66.5 loads were never titled. | intentional boundary (documented); a free-use leak for A3 | `workshop_payroll.py:446-453` [dev] |
| W2 | Raw inputs are never paid (L1B and L6a). | missing capability (A3's target) | `economy.rs:1410-1431` |
| W3 | The L1 ceiling enters raw demand even when raw goods are short, so the raw price at firm cities hits the 0.1-floor spikes (mean 9.7). | model property; evidence gap for A3 pricing | `economy.rs:1443-1452`, `workshops.py:414-426` [dev] |
| W4 | Volume-neutral crafts with a common base price: crafting adds no value at balance, and wares beat raw in 12.6% of operating site region-turns. | owner-level modelling question | `economy.rs:1422-1429` [dev] |
| W5 | Firms open only around an academy order; worlds without academies have no firm (L6a seed 2). | missing capability (non-academy demand) | `workshop_payroll.py:428-440` |
| W6 | L1B production without a firm draws free inputs into the commons (62 site-turns). | free-input producer | counters [dev] |
| W7 | Asset construction, upkeep and repair are not on the firm's books (a public subsidy). | declared; record it | `workshops.py:433-486` |
| W8 | Firm inventory sits outside A5's owned-stock rules (conquest leaves it whole). | A5 dependency | `workshop_payroll.py:363-391` |
| W9 | Legacy crafts outside site regions: unnamed labour (including children and non-farmers) and free inputs, competing with firms. | intentional boundary | `cities.py:1120` |
| W10 | The `wealth_accounting` firm-cash closure hard-codes L6a's kinds; A3 kinds would fail it (correctly) until extended. | integration item | `wealth_accounting.py:394-407` |

No money is created in firm accounts; L6a closures held on every turn of the probe (its own checks
raise).

---

## 9. Open questions (owner or lead)

1. **Input and output price rule.** The recommendation is native post-trade prices band-clamped
   (L6b precedent), with the `free_inputs` control. Under current prices most firms will close.
   Should the owner consider a wares-value calibration or rules version, or accept closure as the
   honest result until A4?
2. **Input payee.** The commons owner (controller) now, producers later (A3-3). Confirm.
3. **Asset costs.** Keep the owner paying (public enterprise, subsidy recorded), or charge the firm
   rent or upkeep under a mode?
4. **Capital.** Size and the one-time rule; whether a conqueror inherits the firm (today: yes,
   distributions follow the controller).
5. **Buyer unit.** Per person (slice 1) or L2 households with adults paying for children.
6. **Retire L1B public production under A3** (no firm, no output): confirm.
7. **Switch placement.** A hookless module inserted before `wealth_accounting` (lead).
8. **Purpose appends.** One coordinated native build (A3, D4, A4).
9. **Screen timing.** CW2 after A3-2 (recommended), or A3-1 with leak counters as secondary.

---

## Appendix: probe method

- Command, from this directory:
  `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1 PYTHONPATH=/home/user/wt/a1-ledger/src
  ~/.venvs/chronicler-native/bin/python probe.py run1/probe_t1.jsonl -- --seed 1 --turns 200
  --agents hybrid --grain-reserves --public-grain-shipments --scholarship --techniques
  --academy-services --workshops --workshop-payroll --simulate-only --output run1/chronicle.md
  --state run1/state.json`
- Wall time 7 s. One run, a development seed (template 1). Module paths verified to the checkout;
  extension `101a4cd5…`.
- The wrappers only read state: `workshops.prepare_phase2`, `workshop_payroll.finish_phase2` and
  `workshop_payroll.phase10`.
- The output reproduces `workshop-finance.md`'s seed-1 paid row exactly. Analyses: `analyze.py`,
  `analyze2.py`, and the inline computations recorded in §2.2.
