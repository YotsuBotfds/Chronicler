# Audit A1–A2: household income, wealth and the wage/enrollment question

Audit lane for Program A1–A2 of the connected-world program, 2026-11-06. Read-only on the shared
checkout `/home/user/Chronicler` (branch `claude/connected-world` at `a955e426`, whose `src/` and
`chronicler-agents/` equal the reference `8abc1acb`; the only change is the lead's plan of record).
Native extension used for runs: `~/.venvs/chronicler-native`, `chronicler_agents…so` SHA-256
`101a4cd5b928b14f…` (the checkpoint-2/3 extension; `check_python_env.py --expect native` PASS).

Labels on claims:

- **[code]** read in the source (file:line at `a955e426`).
- **[dev]** measured on development worlds only (template 7, 23; procedural 32×10 seeds 7, 21,
  31), 200 turns, by this lane. Exploratory: five worlds, no preregistration, no held seed, not
  evidence for any screen or default.
- **[inferred]** reasoning from code and measurement, not tested.
- **[unverified]** stated but not checked here.

Scratch scripts and compact outputs are in this directory (`run_a2.py`, `run_inst.py`,
`inst_child.py`, `analyze.py`, `persons.py`, `sector.py`, `x1/metrics.jsonl` (arms E–H),
`x2/metrics.jsonl` (arms A–D), `x2/openings.json` and `x2/*.schedule.json` (recorded and replayed
opening schedules), `pairs.json`, `persons.jsonl`, `sector.jsonl`, `pilot/metrics.jsonl`). Raw
bundles and the per-turn pickles (≈100 MB) were deleted after extraction; rerunning
`run_inst.py OUT CH_pw p7 U_pw p7 U_sCH p7 CH_sU p7` (≈90 s) regenerates them. Nothing in the
repository was modified. One early run wrote its raw output to an untracked `pilot/` directory
inside the checkout because of a relative path; it was moved here within a minute, the runner was
fixed to refuse non-scratch output paths, and the checkout is clean (`git status` empty).

---

## 0. Answers in brief

1. **Agent `wealth` (native `AgentPool.wealth`, f32, checkpointed) is not cash.** Over a 200-turn
   CP3-style run, conserved typed transfers (wages, procurement, net of courier fees) are only
   **2–12% of household money inflows [dev]**; the rest is model-created occupational income
   (~3,700–15,700 coins per world), balanced mainly by the 2%-per-turn decay sink
   (~4,000–13,900), plus births at 0.5 each. Taxes and tithes on merchant wealth credit the
   treasury and priests **without debiting merchants** (treasury money is partly created).
   Estates without an heir vanish uncounted. No per-turn check covers agent wealth as a whole.
2. **Every transfer a package makes is already conserved and keyed** (native
   `wealth_transfer::transfer/remit/settle_food_purchases`, `credit::apply_merchant_transfers`):
   the payer is debited (treasury whole units with prepaid remainders, firm cash, buyers' wealth,
   senders' wealth), residuals are returned and each package has a closure. What is missing is a
   **sector-level ledger** that itemizes the native model sources/sinks and ties every typed flow
   to it.
3. **Recommendation: keep `wealth` as the single spendable balance and add an opt-in,
   observation-only wealth ledger** (`--wealth-accounting`, default off): Python reads the existing
   receipts and the two per-turn agent snapshots (no edit to any payer), and a later native
   observer itemizes the in-tick model flows. Observation never changes the trajectory, so
   feature-off and feature-on outputs are identical except the new record. A separate spendable
   balance is **not** recommended now (section 3.4). Replace model income with paid flows source
   by source instead (the `retail_income` precedent), each behind its own switch, with the ledger
   showing what model share remains.
4. **A2: the money fall in checkpoint 3 is an enrollment effect, not a wage effect [dev].** With
   the `paid_work` enrollment frozen (each arm replaying the other arm's recorded region-opening
   schedule; enrollment reproduced exactly in 10 of 10 replays), the wage **raises** money credited
   to households in **5/5 worlds at both schedules** (+62 … +1,561 coins). Moving from the unpaid
   arm's enrollment to the paid arm's, with no wage, **lowers** it in 4/5 (−244 … −2,562), because
   replaced farm income rises by ~1,700–2,100 per procedural world.
5. **Food access [dev]:** with the wage held on, the larger enrollment raises priced-out
   person-turns in 5/5 worlds (+1 … +50). The wage at fixed enrollment lowers them in 5/5 at the
   smaller schedule (−2 … −23) and is mixed at the larger (3 higher, 2 lower). At the fixed `all`
   boundary the wage lowers the priced-out rate in 4/5. **The priced-out are mostly non-farm adults
   (merchants 46%, soldiers 18%, scholars 10% of 141 person-turns in the paid arm) and children
   without a co-resident parent; paid crew members are 5% of them** — they are adult farmer owners
   who sell more food than they buy. The wage reaches households that were rarely priced out.
6. **Defects (section 5):** no money is created by a package defect found here; the issues are
   unrecorded model sinks (no-heir estates, wealth-phase ceiling), a treasury source labelled as a
   tax, f32 application of integer-milli transfers, and a screen design in which the treatment
   (payment) decides enrollment. The ceiling almost never binds on these worlds (0–5
   person-turns per run).

---

## 1. Flow inventory

### 1.1 Who writes `pool.wealth`

Native writers (every assignment to `pool.wealth[..]` outside tests, found by grep over
`chronicler-agents/src/*.rs`): `tick.rs:1618/1623/1627` (wealth phase), `household.rs:80/129`
(inheritance), `pool.rs:370/441` (spawn), `pool.rs:525` (kill), `wealth_transfer.rs:158/241/245/373`
(typed transfers), `credit.rs:104` (domestic credit). Python never writes wealth directly: only
through the FFI methods `transfer_wealth` (`ffi/mod.rs:899`), `remit_wealth` (`:915`),
`apply_merchant_transfers` (`:848`), the retail installs (`set_household_retail`,
`install_retail_income`), paid-work installs (`install_paid_work`/`extend_paid_work`,
`:937-946`), and by rebuilding the pool (legacy resume).

Units: wealth is an f32 per agent; typed transfers are integer milli-units (1000 = one wealth unit
= one treasury unit, the domestic-credit equivalence), applied as
`(wealth as f64 + applied/1000) as f32` then clamped to [0, 100] (`wealth_transfer.rs:155-158`).

### 1.2 Table

"Debited?" = is the payer's balance actually reduced by what the receiver gets. Class: **C**
conserved transfer, **S** model-created source, **K** sink (destroyed), **W** withheld model income
(a source not created; no money moves), **A** ambiguous. Persisted: what an exact checkpoint keeps
(agent wealth is always in the pool checkpoint: `pool.rs:1869-1885`, `wealth` listed).

| # | Flow | Payer → receiver | Debited? | Class | Turn position | Switch / default | Modes | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | Farm income `0.30 × farmer_income_modifier × yield[0] (× farm_productivity)` | model → farmer (children included: no age test) | no payer | S | tick 0.5 wealth phase | always (agents) | hybrid/agent modes; aggregate has no agent wealth | `tick.rs:1553-1559`, `agent.rs:231`, modifier `economy.rs:2069-2079` |
| 2 | Soldier income 0.15 × (1 + at_war) + 3.0 × conquered_this_turn | model → soldiers of the civ | no | S | 0.5 | always | agents | `tick.rs:1561-1565`, `agent.rs:232-234` |
| 3 | Merchant income `merchant_trade_income` (delivered value × margin ÷ merchants of origin) | model → merchants | no; cargo is loaded from commons free | S | 0.5 (derived in Phase 2 economy) | always | hybrid path `economy.rs:2083-2125` | `tick.rs:1566-1569` |
| 4 | Scholar income 0.20 | model → scholars | no | S | 0.5 | always | agents | `tick.rs:1570-1573`, `agent.rs:236` |
| 5 | Priest income 0.20 + `priest_tithe_share` (TITHE_RATE × civ merchant wealth × food gate ÷ priests) | model → priests; base is merchants' wealth | **merchants not debited** | S (A: looks like a transfer) | 0.5 | always | agents | `tick.rs:1574-1578`, `economy.rs:2281-2285`, merchant wealth summed `ffi/mod.rs:3620-3632` |
| 6 | Teaching share of a scholar's income | — | — | W | 0.5 | `--academy-services` | hybrid | `tick.rs:1581-1593`; teaching is unpaid (`teaching_work.rs:1-2`) |
| 7 | Learner attendance share | — | — | W | 0.5 | `--learning-cohorts` (L5) | hybrid | `tick.rs:1597`, `learning_work.rs:17-21` |
| 8 | Paid-work share (L6a crews, RS1 apprentices, RS2/PL3 crews, PL1 woodcutters) withheld; receipt `(id, share, ordinary, deducted)` | — | — | W | 0.5 (armed in Phase 2/before tick) | each package | hybrid | `tick.rs:1600-1601`, `wealth_transfer.rs:392-487,527-540` |
| 9 | Retail income replacement: a pilot farmer's remaining farm income set to 0, receipt `(id, income×(1−loss))` | — | — | W | 0.5 | `--household-retail` (not `free_exchange`/`record_only`) | hybrid only | `tick.rs:1604-1605`, `wealth_transfer.rs:497-525`; installed `household_retail.py:1035` |
| 10 | Health work loss (rural impairment, caregivers) | — | — | W | 0.5 | health care state present (`health_care.health_care_active`) | hybrid | `tick.rs:1609-1614` |
| 11 | Decay `wealth × 0.02` per tick | agent → nowhere | — | K (unrecorded) | 0.5, after income | always | agents | `tick.rs:1623`, `agent.rs:230` |
| 12 | Ceiling/floor clamp [0, 100] after decay | agent → nowhere | — | K (unrecorded) | 0.5 | always | agents | `tick.rs:1627`, `agent.rs:229`; binds 0–5 person-turns/run **[dev]** |
| 13 | Birth endowment 0.5 | model → newborn | no | S (unrecorded as money) | demographics, after 0.5 | always | agents | `tick.rs:1161-1170` → `pool.rs:370,441` |
| 14 | Estate → spouse (else dependants, else all children) | deceased → heirs | yes | C | 0.0 catastrophe/targeted deaths and demographic deaths | always | agents | `household.rs:59-150`, called `tick.rs:121` |
| 14a | Estate above heir's ceiling | → nowhere | — | K (counted, f32 `inheritance_wealth_lost`) | same | always | agents | `household.rs:80-84,129-133`; exported `ffi/mod.rs:2536` |
| 14b | Estate with no living spouse or child | → nowhere (`kill` zeroes it) | — | **K (uncounted)** | same | always | agents | `household.rs:66-70,111-114`, `pool.rs:521-525` |
| 15 | Migration / merchant trip | wealth travels with the person | n/a | none (region attribution only) | tick | always | agents | no writer |
| 16 | Pool rebuild (legacy JSON resume, fork rebuild) | all balances replaced by spawns at 0.5 | — | S/K discontinuity | resume | — | agents | `livelihoods.py:570-593` (`bind_native_pool`, `on_pool_reset`) |
| 17 | Treasury tax 5% × civ merchant wealth | "merchants" → treasury (keep) | **merchants not debited** | S labelled as tax (A) | Phase 2 after economy | always in hybrid | hybrid (aggregate uses Python economy `economy.py:2113`) | `economy.rs:2283`, `simulation.py:1801-1823` |
| 18 | Clergy tithe to treasury `TITHE_RATE × tithe_base` | "merchants" → treasury | **not debited** | S (A) | Phase 10 factions | clergy ≥ threshold | agents | `factions.py:424-430`, base `economy.rs:2284` |
| 19 | L6a workshop wages (purpose 0, batch = site) | firm cash → worker by id | yes (cash); ceiling refusal stays in cash | C | Phase 10 (and a Phase 2 liquidation path) | `--workshop-payroll` (needs `--workshops`, academy services) | hybrid | `workshop_payroll.py:283-292,363,649-680`; firm cash funded by academy purchases from treasury (keep) `workshop_payroll.py:32-40` |
| 20 | RS1 apprentice stipends (purpose 2, batch = site) | firm cash → apprentice | yes | C | Phase 10 after payroll | `--apprenticeship` + L6a | hybrid | `workshop_payroll.py:733-770`, `apprenticeship.py:1448-1493` |
| 21 | RS2 workshop-repair wages (purpose 3, batch 0) | treasury → crew by id | yes: treasury charged `cost + applied` in whole units, prepaid sub-unit; refused part not charged | C | Phase 2 `finish_phase2` (before the tick) | `--repair-projects` | hybrid | `repair_projects.py:1005-1018,1115-1131` |
| 22 | PL3 granary-crew wages (purpose 3, batch 1) | treasury's granary coin charge → crew by delivered share | yes; ceiling refusal **sunk**; `unpaid` mode sinks it all | C (+K residual) | Phase 2 `finish_phase2` | `--recovery-crews` (paid default) | hybrid | `recovery_crews.py:36-47,452-476`; receipt `sunk_milli` `:501` |
| 23 | RS2 granary coins without named crews | treasury → material sink | yes | K (declared) | Phase 2 | `--repair-projects` | hybrid | `recovery_crews.py:40-47` (the sink PL3 redirects) |
| 24 | PL1 woodcutting wages (purpose 3, batch 2) | treasury → crew | yes, applied + prepaid | C | Phase 2 `finish_phase2` | `--timber-supply` | hybrid | `timber_supply.py:44-50,712-734` |
| 25 | Retail food purchases (purpose 5, settled in the tick) | buyers' adults (child-only households: own) → sellers by id; refunds at seller ceiling to payers | yes; `paid = credited + refunded` exactly | C | tick 0.7 | `--household-retail` | hybrid only | `wealth_transfer.rs:317-391`, `provisioning.rs:787,827`, `tick.rs:575-586` |
| 26 | Granary procurement of owners' grain (purpose 6) | treasury (already paying the cost) → owners by id; non-owner share and refusals → "producers outside the treasury accounts" | yes (owners' share); rest K | C + K | Phase 10, after `tick_grain_reserves` | `--household-retail` retail/no_relief | hybrid | `household_retail.py:1391-1435`, seam `grain_reserves.py:558,677,923` |
| 27 | Non-pilot procurement and public grain purchases | treasury → producers outside the accounts | yes | K (pre-existing) | Phase 10 | `--grain-reserves` | all | `household-retail.md` §Granary procurement |
| 28 | RS4 remittances (purpose 4) | sender → recipient; 15% courier fee → sink; ceiling refund → sender | yes | C + K (fee, declared) | after the tick | `--remittances` | hybrid | `wealth_transfer.rs:204-253`, `remittances.py:316-330` |
| 29 | L7 relocation fare (purpose 1, negative rows); assistance | movers → travel sink; treasury → travel sink | yes | K (declared) | after tick (fare), Phase 10 (assistance) | `--relocation-costs` | hybrid | `relocation_costs.py:36-45,252-268` |
| 30 | Domestic credit: principal, interest, repayment, write-off | merchants of a region ↔ treasury; unapplied stays `merchant_due` | yes (pro rata to wealth) | C | Phase 3b finance tick | `--domestic-credit` (needs finance) | agent modes | `credit.rs:61-125`, `domestic_credit.py:645-652` |
| 31 | Guild and city purses | separate Python balances (`guild.wealth`, `city.wealth`) | — | not agent wealth | various | `--guilds`, `--cities` | all | `guilds.py:288-301`, `cities.py:615-913` |
| 32 | Own-consumed food (retail) | no money: an owner eats own title instead of free commons | — | none, but see 9 | 0.7 | retail | hybrid | `household-retail.md` §Phase 0.7 |

Persisted state besides `pool.wealth`: package books are Python state in `world.livelihoods.*`
(firm cash, owed wages, RS2/PL1 `prepaid` remainders, PL3 ledgers, RS4 frame, L6b claims and
counters, domestic-credit lines and `merchant_due`). Every native install, receipt and the
transfer key log are transient (`pool.rs:1882-1885`, `wealth_transfer.rs:41-44`); exact
checkpoints are taken between turns when none is pending.

### 1.3 Money turn order (one turn, hybrid)

| Order | Point | Wealth writers |
|---|---|---|
| 1 | Phase 2, before the economy | `prepare_phase2` hooks (retail boundary, title weights). **The Phase 2 agent snapshot is the clean opening balance** (state after the previous turn's Phase 10). |
| 2 | Phase 2, after the economy (`finish_phase2`) | RS2 workshop wages (3/0), PL3 granary wages (3/1), PL1 wages (3/2); paid-work shares armed; L6a Phase-2 liquidation wages |
| 3 | Phase 2 (`apply_automatic_effects` area) | treasury tax (no agent writer) |
| 4 | Phase 3b finance | domestic credit merchant transfers |
| 5 | Agent tick 0.0 | catastrophe/targeted deaths: estates |
| 6 | Agent tick 0.5 | income (with withheld shares and retail replacement), decay, clamp |
| 7 | Agent tick 0.7 | retail food purchases settle |
| 8 | Agent tick, demographics | natural deaths (estates), births (0.5) |
| 9 | `after_agent_tick` hooks | L7 fares, RS4 remittances (the held post-tick batch is discarded, `livelihoods.py:677-683`) |
| 10 | Phase 10 capture | `_capture_agent_snapshot` (`simulation.py:2398`) — post-tick balance |
| 11 | Phase 10 livelihoods | L6a wages, RS1 stipends, procurement credits (after `tick_grain_reserves`), L7 assistance (treasury only) |
| 12 | next turn's step 1 | must equal step 10 + step 11 exactly (no other writer in between) **[code; check proposed in §6]** |

### 1.4 Readers that use wealth as status (changing its semantics would perturb them)

| Reader | Uses | Evidence |
|---|---|---|
| Satisfaction: class tension `gini × (1 − wealth percentile) × weight` | per-civ rank and Gini | `satisfaction.rs:236-238`; Gini from snapshot `agent_bridge.py:1347-1372` → signals `signals.rs:244` |
| Material need restoration | wealth percentile × deficit | `needs.rs:431-444` |
| Prosperity memory | wealth > 3.0 | `tick.rs:676-688`, `agent.rs:283` |
| Migration: household effective wealth damps married movers | level | `behavior.rs:1060-1072`, `household.rs:186` |
| Migration: wage-gap pull (peer mean wealth there ÷ here, farmers and merchants) | level | `behavior.rs:557-608`, `migration_drivers.rs:426` |
| Rival bond formation (wealth proximity < 50) | level | `formation.rs:204` |
| Luxury demand (agents above 10.0) | level | `ffi/mod.rs:3575`, `economy.rs:1440` |
| Treasury tax, tithe base, priest income | merchant wealth level | `economy.rs:2281-2285` |
| Finance creditor wealth, domestic-credit capacity and lending | merchant wealth level | `finance.py:744-752`, `credit.rs:51-58` |
| L2 means-tested allocation (`floor_means`) | household wealth | `provisioning.rs:266` |
| Retail cash limits | adults' wealth in whole milli | `provisioning.rs:787,827` |
| L7 fare affordability | liquid milli | `relocation.rs:212` |
| RS4 amount `10% × (w − 2.0)`, cap 1.0 | level | `docs/integration/remittances.md` §Remittances |
| Governance stress, elite metrics, narration (Gini) | level/rank | `governance_runtime.py:632,1318`, `elite_metrics.py:230`, `narrative.py:1268` |

Rank readers (satisfaction, needs) are invariant to uniform scaling but not to regional
redistribution: a retail pilot region drains relative to the rest of its civ, so its residents'
percentiles fall **[inferred]**.

---

## 2. Classification and existing checks

### 2.1 Classification summary

- **Conserved transfers (payer debited, residual returned or explicitly kept):** 14, 19, 20, 21,
  22 (paid part), 24, 25, 26 (owners' share), 28 (net of fee), 30.
- **Model-created sources:** 1–5, 13, 17, 18 (17 and 18 look like transfers but debit no one), 16
  on a rebuild.
- **Sinks:** 11 and 12 (unrecorded), 14a (counted), 14b (**uncounted**), 22 residual / unpaid
  mode, 23, 26 rest, 27, 28 fee, 29, sub-unit write-offs (L6a closure, RS2/PL1 prepaid on switch
  off or loss of regions).
- **Withheld income (no money moves):** 6–10. These matter because the CP3 "money credited
  (gross)" measure subtracts 9 but not 6–8, and PL3's counter mixes granary and workshop crews.
- **Ambiguous:** 5, 17, 18 (labelled tithe/tax, behave as sources); 3 (merchants paid by no one for
  goods moved free of charge — A4 must replace this proxy rather than add to it).

Scale **[dev]** (paid arm `CH_pw`, 200 turns, from per-turn snapshots; decay estimated as
`Σ_t W_t × 0.02/0.98`, model income as the residual + decay − births × 0.5, so it is net of
estate and ceiling sinks):

| World | ΔW over run | typed net (wages + procurement − fees) | births × 0.5 | est. decay | est. model income | income replaced by retail | retail purchases |
|---|---|---|---|---|---|---|---|
| t23 | +425 | +510 | 175 | 3,980 | 3,721 | 2,154 | 1,843 |
| t7 | +736 | +113 | 285 | 5,491 | 5,830 | 1,906 | 2,126 |
| p7 | +2,368 | +782 | 901 | 11,696 | 12,382 | 3,386 | 4,430 |
| p21 | +3,450 | +701 | 731 | 12,655 | 14,673 | 4,138 | 3,473 |
| p31 | +4,444 | +1,542 | 1,086 | 13,928 | 15,744 | 5,318 | 5,673 |

Typed transfers are 2–12% of inflows; wealth is a model balance with declared sources and an
exponential sink, not money.

### 2.2 Existing checks

| Check | Covers | Does not cover |
|---|---|---|
| `CHRONICLER_CHECK_RESOURCES=1` (`production_ledger.resource_check_enabled`) | goods: production ledger (`production_ledger.py:1-26`), granary resource ledger incl. owned grain sold (`grain_reserves.py:923`), convoys; **money only for domestic credit**: claims, payments, purses, `merchant_due` and the merchants' applied wealth change (`domestic_credit.py:705-723`) | agent wealth as a whole; any other payer |
| Native `ConservationSummary` | goods production, transit, consumption, storage, cap, woodcut outflow (`economy.rs:385-398`) | money |
| `transaction_receipts.rs` | merchant mobility observations; "neither assigns cargo title nor makes cash/insurance claims" (`transaction_receipts.rs:1-5`) | money |
| `food_accounting` | regional food after relief | money |
| Package closures (always on, raise) | L6a firm cash `cash = sales − wages − distributions − write-offs` (`workshop_payroll.py:66-71`); RS2 `charged×1000 + prepaid_before = cost + applied + prepaid_after` (`repair_projects.py:93-98`); PL1 same form + `applied + residual = due` (`timber_supply.py:90-92`); PL3 ledger (`recovery_crews.py:65-68`, `check_ledger`); RS4 `debited = credited + fee`, `sent = debited + refunded` (`remittances.md` §Accounting); L6b money rows `paid = credited + refunded`, per-region and procurement closures (`household-retail.md` §Accounting); L7 fare residuals | the native model flows, the turn as a whole, cross-package attribution |
| Native transfer key log | each `(turn, purpose, batch)` applied once (`wealth_transfer.rs:139,219,319`) | — |
| Viewer readers | per-record identities (e.g. `householdRetail.ts`) | sector totals |

---

## 3. Recommended accounting design

### 3.1 Answer to the A1 question

The existing wealth field **can** support honest accounting — sources and sinks explained, typed
flows conserved and attributed — **if** its model sources and sinks are itemized and labelled. It
**cannot** be called conserved cash: ~90–98% of its inflow is model-created and the largest
outflow is an unrecorded 2% decay **[dev]**. A separate spendable balance is not needed for the
downstream programs, because their payments (wages, purchases, fees, procurement) already debit an
explicit payer through typed transfers; what they need is one ledger that proves it per purpose and
shows what model share remains.

### 3.2 Design: `--wealth-accounting` (observation only)

- **Switch**: `--wealth-accounting` (livelihoods switch, default off, no modes in slice 1; a later
  `strict` raises on an unexplained residual). Appended **last** to `LIVELIHOODS_SWITCHES`
  (`livelihoods_state.py:44-51`) so its hooks run after every payer in every phase; registered in
  `feature_catalog.REQUIREMENTS` as `(_HYBRID,)`; `batch_manifest.SIMULATION_ARG_KEYS` with
  omit-when-unset (so feature-off manifests keep their bytes; `batch_manifest.py` is witness-pinned:
  the lead adds the layer). Refused outside `--agents hybrid`, at startup and on resume.
- **State** (`world.livelihoods.wealth_accounting`, `exclude_if=None`, absent until enabled):
  - `opening`: per region f64 sum and count of the last Phase 2 snapshot, world total, `turn`,
    pool binding id (`livelihoods._pool_sim`);
  - lifetime totals per channel (milli for typed flows, f64 for native ones);
  - the completed-turn frame (per region × channel rows, sector totals, residuals), a 64-entry
    dated log (pool reset, refused continuity, unexplained residual), fixed-key counters.
  - Transient `_turn` (never pickled) holding this turn's collected receipts.
- **Seams (slice 1: Python only, no edit to any payer, no native change):**
  1. `prepare_phase2(world, region_input, agent_bridge, snapshot)`: read the Phase 2 snapshot
     (`agent_bridge.get_snapshot()` at the start of Phase 2, `simulation.py:2029`; `id`, `region`,
     `occupation`, `wealth`) as the opening; check it equals the previous turn's
     closing exactly per id (f32 bits) — the **no hidden writer** check (§1.3 row 12).
  2. `phase10` (last hook): collect this turn's typed flows from the packages' committed records
     and receipts: RS2 receipts (`wages_milli`, `wage_residual_milli`, `coin_cost_milli`), PL3
     receipts (member `wage_milli`, `sunk_milli`), PL1 receipts, L6a receipt
     (`MoneyTransfer` rows, cash close), RS1 seats (`stipend_paid`), RS4 frame (credited, fee,
     refunded, per region), L7 groups (paid, residual), L6b (`state.money`: paid, credited,
     refunded; procurement credited/residual), domestic credit totals (applied merchant flows), and
     the paid-work receipt via `livelihoods.paid_work_receipt` (shared, `livelihoods.py:596-620`) —
     attributing each row to its installing package by id (one paid share per person per turn,
     `wealth_transfer.rs:453`), which **splits PL3's withheld income into granary and workshop
     crews** (recorded limit).
  3. Read a closing snapshot (`get_snapshot()` once, after every payer) and form, per region and
     for the world: `close − open = typed_in − typed_out + native_model` where `native_model` is
     labelled "native model flows: occupational income net of withheld shares, decay, ceiling,
     births, estates without heirs, inheritance overflow (not itemized in slice 1)". Treasury-side
     counterparts are recorded beside it (wages paid from treasury vs created treasury tax and
     tithe), so the sector table shows how much of the treasury that pays wages was itself created.
  4. `on_pool_reset`: record a discontinuity and restart the opening (never carry balances across
     a rebuilt pool).
- **Slice 2 (native observer, needs a native build and witness layers for `tick.rs`, `pool.rs`,
  `household.rs`, `ffi/mod.rs`, all ENFORCED by `refactor_preflight.py`):** a transient
  `Option<WealthObserver>` on `AgentPool` (in the `transient {}` list, so no persist schema
  change, as retail's four fields), installed per tick and taken once, with `if let Some` hooks
  (the `CAREOBS_SOURCE` pattern already threaded through `wealth_tick`, `tick.rs:1527-1650`):
  per region × occupation gross income, each deduction (teaching, learning, paid work, retail,
  health), decay, ceiling clamp; births × 0.5; estates to spouse/children/overflow/**no heir**;
  in-tick purchase totals. Closure per tick: Σ alive after − Σ alive before (+ dead estates) =
  channels, within f32 tolerance (relative 1e-6 of gross flows). Python then replaces the slice-1
  residual by these channels and raises in `strict` mode on what remains.
- **Feature-off identity**: nothing runs when the switch is absent (no hook registered, no native
  observer installed). **Observer identity**: with the switch on, every output except the new
  record equals the switch off (slice 1 only reads; slice 2's hooks only add to an `Option`). Both
  are testable byte for byte (`turn_speed_identity` style).
- **Checkpoints**: only Python state is persisted (opening per region, lifetime totals, frame, log);
  native observer and `_turn` are transient. An exact resume continues the opening; a legacy
  resume or pool rebuild records a discontinuity. Resume with the switch turned off drops the
  state with a dated record; resume outside hybrid is refused.
- **Snapshot**: `livelihoods.wealth_accounting` (stage `A1`) for the completed turn; `None` when not
  observed (unknown, not zero), distinct from recorded zero.

### 3.3 Shared payment seam for new payers (A3, A4, B3, C2, D4)

New programs should pay through one Python helper (proposed `chronicler/money.py`,
`pay(world, sim, payer, purpose, batch, rows, residual_policy)`) that: validates the whole bill
against the payer account before moving anything (treasury projected budget incl. pending bills;
firm cash; household pairwise), charges treasuries in whole units with a prepaid remainder (the
RS2/PL1 rule), applies credits with `transfer_wealth`, and resolves residuals by a declared policy
(`return_to_payer` | `declared_sink:<name>`), emitting one typed flow record for the ledger.
Household-to-household payments other than in-tick food purchases (A4 merchants buying from
owners, care fees) need a generic pairwise native operation (remit without the fee and with a
purpose argument) — a native addition; append purposes, never renumber
(`wealth_transfer.rs:58-66`). Existing packages are not refactored onto it (witness pins and
output identity); the ledger reads their receipts instead.

### 3.4 Why not a separate spendable balance now

- Two balances that both buy things would double purchasing power unless every reader (L2 means
  test, retail cash, L7 fares, RS4 amounts, migration, satisfaction) is re-pointed — the readers in
  §1.4 — which is a default-path change for all of them.
- It needs its own rules for endowment, birth, death, inheritance, migration, rebuilds and
  checkpointing, duplicating what wealth already has.
- The program's real problem is that model sources still dominate. The honest route is to replace
  model income where a paid flow now exists (farm income → food sales already does this; next:
  merchant income → margins paid by buyers in A4; soldier pay → treasury payroll; priest income and
  tithe → debited from payers), each behind its own switch with the ledger showing the remaining
  model share. If, after those, the owner wants a closed money system, the ledger's channels are the
  specification for it.

---

## 4. A2: separating the wage from `paid_work` enrollment

### 4.1 How `paid_work` enrolls regions and why paid crews change it [code]

- Enrollment is by **whole region**: every farmer in a pilot region has farm income replaced and
  every household there buys at the region price (`household_retail.py:1035`, `tick.rs:1604`).
- `_paid_work_regions` (`household_retail.py:454-473`) reads each lane's **last committed** frame
  (so a region qualifies one turn after the first paid crew) and adds: an open L6a firm; an RS2
  receipt with `wages_milli > 0`; a **PL3 granary receipt with `wages_milli > 0`**; a PL1 home with
  `wages_milli > 0`. `_qualifying` (`:476-490`) keeps controlled, not-yet-pilot regions;
  `_update_boundary` (`:518-532`) opens them and closes only regions without a controller —
  enrollment is sticky and monotone.
- In `CH_unpaid` PL3 crews are named, reserved and withheld identically but receive no wage, so
  their receipts have `wages_milli == 0` and their regions never qualify; RS2 workshop crews and
  PL1 woodcutters are paid in both arms. **The treatment (payment) therefore decides which regions
  are treated by retail.** Granary projects are common (P7: 38 opened over the run **[dev]**), so the paid arm enrolled
  1.3–2.0× the unpaid arm's pilot region-turns on the development worlds.

### 4.2 Analysis design

Per world, CP3 base (`--turns 200 --agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --grain-storage
--food-allocation --workshops --operating-wear --repair-projects --timber-stock`, procedural adds
`--worldgen procedural --regions 32 --civs 10`). `CHAIN = --timber-supply --recovery-crews
--remittances`; `UNPAID = --timber-supply --recovery-crews --recovery-crew-mode unpaid
--remittances`.

| Arm | Flags added | Role |
|---|---|---|
| A `CH@pw` | `--household-retail --household-retail-boundary paid_work` + CHAIN | CP3 `CH`; records its opening schedule S_A |
| B `U@pw` | same + UNPAID | CP3 `CH_unpaid`; records S_B |
| C `U@S_A` | `--household-retail --household-retail-boundary schedule --household-retail-schedule S_A.json` + UNPAID | **new option**: no wage, A's enrollment |
| D `CH@S_B` | `… schedule --household-retail-schedule S_B.json` + CHAIN | **new option**: wage, B's enrollment |
| E/F `CH@all`, `U@all` | `--household-retail --household-retail-boundary all` + CHAIN / UNPAID | fixed universal cohort |
| G/H `CH@mkt`, `U@mkt` | `… boundary market` + CHAIN / UNPAID | fixed capital cohort |
| optional `F@all` | E with `--household-retail-mode free_exchange` | cash control at the fixed cohort |
| optional `CH_noTS` | CHAIN without `--timber-supply` (retail at `paid_work`) | expedition labour control (recorded limit: `CH_cut − CH_noTS`) |

Contrasts: total `A − B`; wage at fixed enrollment `A − C` (S_A) and `D − B` (S_B); enrollment
without wage `C − B`, with wage `A − D`; interaction `(A − C) − (D − B)`; fixed-cohort wage `E − F`,
`G − H`. A and B run first; S_A and S_B are frozen (hashed in the report) before C and D run; the
schedule is a function of the world and arm A/B only.

Outcomes (2–3 primary, per CP3 conventions; region set fixed per contrast):
1. **Priced-out person-turns per pilot person-turn** over the fixed set (S_A for `A − C`, S_B for
   `D − B`, all controlled regions for `E − F`), with the whole count beside it.
2. **Net money into households**: wages + remittances credited + procurement credited − income
   replaced (the ledger of §3 makes this exact rather than screen-reconstructed), and end-of-run
   mean wealth of pilot residents.
3. **Person level**: priced-out person-turns of crew households (members and co-resident children)
   versus everyone else in the set — needs the instrumentation below.
Secondary: coverage, income replaced, wages by package, withheld income by package (split),
children priced out, withheld-dead (status 3) persons, mean ration, granary condition; harm panel:
children priced out, population, treasury.

New code needed:
- `--household-retail-boundary schedule` + `--household-retail-schedule PATH` (JSON `{region:
  opening turn}`): validated (indices, turns), stored with a digest in `HouseholdRetailState` so an
  exact resume keeps it, manifest key omitted when unset, catalog entry, refused without the switch.
  `_qualifying` returns scheduled regions whose turn ≤ `world.turn` (the controller filter, sticky
  closure and reopening as today). About 40 lines plus tests.
- A persistent per-region `opened_turn` map in the retail snapshot (today openings live only in a
  64-entry rolling log) so a schedule can be read from any bundle.
- Person-level evidence (the recorded limit "purchases by person"): cohort aggregates per region-turn
  computed in Python at settlement from the native money rows, the income receipt, the native
  sample (256 rows, unfed first) and the crew receipts — crew members, their co-resident children,
  children without a co-resident adult, non-farm adults, other farm households: persons, priced
  out, paid, credited, income replaced, wages. No ids leave the snapshot.

### 4.3 Exploratory results [dev] (not a screen; 5 development worlds)

Method: arms E–H via the CLI (`run_a2.py`); arms A–D in-process (`run_inst.py`, `inst_child.py`)
with `household_retail._paid_work_regions` and `_update_boundary` wrapped to record openings and,
for C/D, to return the other arm's recorded opening schedule (no repository change). The
instrumented A on P7 reproduced the CLI run's extracted outcomes exactly (income replaced,
population, treasury, retail totals, package counters, region totals, granary). **Every replay
reproduced the source arm's per-region pilot region-turns exactly (10/10).** 40 runs + 1 pilot,
~0.25 core-hours. Outcomes from `productive_recovery_screens.metrics_row_cp3`; region set = union of
both arms' pilot regions (CP3 rule). Worlds in order t23, t7, p7, p21, p31; counts are
higher/lower/zero.

| Contrast | coverage A/B | Δ priced-out person-turns | Δ rate (×10⁻⁴) | Δ wages | Δ income replaced | Δ money credited (gross) |
|---|---|---|---|---|---|---|
| Total `CH@pw − U@pw` | .88/.66 .82/.53 .83/.41 .84/.43 .88/.61 | −8 −2 +31 +25 +43 (3/2) | −4.3 −1.0 +4.2 +2.0 +4.5 | +336 +141 +779 +596 +1431 | +171 −251 +1464 +1619 +1869 | +144 +200 −845 −1001 −770 (2/3) |
| Enrollment, no wage `U@S_A − U@pw` | same | −5 +15 +18 −15 +37 (3/2) | −2.9 +6.3 +2.0 −5.5 +3.8 | ≈0 | +197 −318 +1722 +2100 +1773 | −244 +138 −1800 −2562 −1983 (1/4) |
| Enrollment, with wage `CH@pw − CH@S_B` | same | +2 +1 +33 +48 +50 (**5/0**) | +0.9 +0.1 +4.8 +8.9 +5.7 | ≈0 | +55 −112 +1625 +2002 +1428 | −71 +27 −1948 −1980 −1634 (1/4) |
| Wage at S_A `CH@pw − U@S_A` | identical | −3 −17 +13 +40 +6 (3/2) | −1.4 −7.3 +2.2 +7.6 +0.8 | +325 +153 +795 +713 +1230 | −26 +67 −258 −481 +96 | +388 +62 +955 +1561 +1213 (**5/0**) |
| Wage at S_B `CH@S_B − U@pw` | identical | −10 −3 −2 −23 −7 (**0/5**) | −5.2 −1.1 −0.6 −6.8 −1.2 | +302 +82 +968 +745 +1360 | +116 −139 −161 −383 +441 | +215 +173 +1103 +979 +864 (**5/0**) |
| Wage at `all` `CH@all − U@all` | .97/.97 .99/.99 .92/.94 .87/.90 .92/.91 | +191 −202 −211 +28 −424 (2/3) | +115.9 −53.1 −22.2 −0.3 −35.0 (1/4) | +228 +67 +928 +953 +1053 | −600 +141 +322 +107 −487 | +778 −4 +803 +989 +2063 (4/1) |
| Wage at `market` `CH@mkt − U@mkt` | .89/.89 .85/.83 .73/.81 .71/.70 .78/.81 | −264 +8 −9 −1 +40 (2/3) | −41.7 −3.3 −3.9 +3.3 +0.7 (2/3) | +94 +57 +935 +935 +1164 | −586 +332 +597 −373 +813 | +516 −293 +456 +1584 +593 (4/1) |

Person level (arms A–D, summed over the five worlds; the native sample held every priced-out
person-turn — its totals equal the frame totals in all four arms, 141, 52, 102 and 7):

| Arm | priced-out person-turns | non-farm adults (merchant / soldier / scholar / priest) | children without a co-resident parent | crew members | other | PL3 wages | crew income replaced | crew sales / purchases |
|---|---|---|---|---|---|---|---|---|
| A `CH@pw` | 141 | 65 / 25 / 14 / 3 (76%) | 15 | 7 (5%) | 12 | 3,095 | 4,444 | 4,530 / 2,358 |
| B `U@pw` | 52 | 19 / 8 / 11 / 3 | 5 | 5 | 1 | 0 | 2,984 | 3,129 / 1,577 |
| C `U@S_A` | 102 | 54 / 11 / 8 / 7 | 7 | 9 | 6 | 0 | 4,451 | 4,725 / 1,969 |
| D `CH@S_B` | 7 | 2 / 2 / 0 / 0 | 2 | 0 | 1 | 3,136 | 3,206 | 3,098 / 1,563 |

Reading (exploratory, development-only):
- **Why money credited fell:** in procedural worlds the paid arm's wider enrollment replaces
  ~1,400–2,000 more coins of farm income per world than the unpaid arm, against ~600–1,400 more
  wages; at either frozen enrollment the wage raises money credited in every world. CP3's
  explanation holds, and the sign of the "money" outcome is set by enrollment, not by the wage.
- **Why paid work did not reliably improve food access:** (i) enrollment puts more non-farm adults
  under prices — they hold no title and must buy every ration, and their incomes are soldier pay
  (0.15/turn) or trade income that can be near zero; (ii) the wage goes to adult farmer owners, who
  sell about twice what they buy and are rarely priced out (crew members are 0–9 of 7–141
  priced-out person-turns per arm); (iii) the wage roughly offsets the crew's own replaced farm
  income (3,095 vs 4,444 in A), so it restores rather than adds; (iv) counts per world are small
  and trajectories diverge (income replaced differs by up to ±600 between arms with an identical
  boundary), so five worlds cannot resolve the wage's own effect on priced-out persons: it is
  favourable at S_B (5/5, tiny counts) and at `all` (4/5 rates), mixed at S_A and `market`.
- Under `all` the priced-out levels are an order of magnitude higher (800–1,800 per world) than at
  `paid_work` — universal enrollment exposes many more non-farm adults **[dev; composition at `all`
  not instrumented, inferred]**.

---

## 5. Defects and issues found

| # | Issue | Class | Effect | Reproduction hint |
|---|---|---|---|---|
| D1 | Estate of a deceased with no living spouse or child is destroyed by `pool.kill` and **not counted** (`household.rs:66-70,111-114`, `pool.rs:525`); only ceiling overflow is counted (`inheritance_wealth_lost`). | unrecorded sink (defect for accounting, not for physics) | money destroyed with no record | Rust unit: spawn one agent with wealth 10, no bonds, run `apply_death_batch`; Σ wealth falls 10, `household_stats.inheritance_wealth_lost` stays 0 |
| D2 | Wealth-phase ceiling clamp destroys income above `MAX_WEALTH` silently (`tick.rs:1627`). | unrecorded sink | rare: 0–5 person-turns per run **[dev]** | `test_wealth_clamped_to_max` (`tick.rs:3488`) shows it; no counter exists |
| D3 | Treasury tax 5% of merchant wealth and clergy tithe credit the treasury without debiting merchants; priests' tithe share likewise (`economy.rs:2281-2285`, `simulation.py:1801-1823`, `factions.py:424-430`). | model source labelled as a transfer (pre-existing M42) | wages paid "from the treasury" are partly funded by created money | compare Σ merchant wealth across Phase 2 (unchanged) with the treasury `keep` delta |
| D4 | Integer-milli transfers are applied to an f32 balance: `(w as f64 + a/1000) as f32` loses up to half an ulp (≈3.8·10⁻⁶ at w ∈ [64,128), i.e. ≈0.004 milli per row); receipts report the exact integer (`wealth_transfer.rs:155-158,239-246,370-374`; `credit.rs:101-105` reports the f32 change instead). | precision | an exact integer household ledger cannot be asserted against wealth; use a tolerance or the slice-2 observer | transfer 1 milli to an agent at wealth 99.9 repeatedly and compare |
| D5 | PL3 ceiling residual is sunk while RS2/PL1 refused wages are simply not charged and L6a keeps them in cash (`recovery_crews.py:44-47`, `repair_projects.py:1115-1131`, `timber_supply.py:90-92`). | inconsistent residual policy (documented per package) | tiny at these sizes | read the three receipts' `wage_residual_milli` handling |
| D6 | The `paid_work` boundary keys PL3 eligibility on `wages_milli > 0` (`household_retail.py:469`), so payment decides enrollment; CP3's `CH − CH_unpaid` mixes the two. | evidence-design defect (not code) | the CP3 wage contrast is confounded; resolved by §4.2 | §4.3 |
| D7 | RS2 and PL3 `income_replaced` counters overlap for workshop crews; PL3's counter mixes granary and workshop crews. | evidence gap (recorded limit) | cannot net withheld income per package | `repair_projects.income_replaced` vs `recovery_crews.income_replaced` |
| D8 | CP3 "money credited (gross)" subtracts retail income replacement (row 9) but not the other withheld shares (rows 6–8) and adds remittances gross. | measurement definition (declared, lead decision 3) | not a net money measure | §2.1 |

Not found: double payment (each package uses a distinct `(purpose, batch)` key: RS2 3/0, PL3 3/1,
PL1 3/2, L6a 0/site, RS1 2/site, procurement 6/0, food purchases 5/0, remittances 4/0, fares 1/0;
the key log refuses repeats); lost retail refunds (`paid = credited + refunded` exactly, refunds ≤
paid, `wealth_transfer.rs:317-391`; seller room measured before purchases); money created by any
package. Not checked: the L6a Phase-2 liquidation path end to end; domestic credit beyond its own
ledger; aggregate (`--agents off`) Python economy taxes.

Recorded-limit dispositions proposed for S1:
- **Person-level purchase evidence** (evidence gap): cohort aggregates at settlement (§4.2); the
  exploratory sample shows the native 256-row sample held every priced-out person-turn on these
  worlds.
- **PL3 withheld-income split** (evidence gap): attribute paid-work receipt rows to installing
  packages by id in the ledger (§3.2 seam 2), or two counters in PL3.
- **Expedition labour controls** (evidence gap): add arm `CH_noTS` (§4.2); no code.
- **Storage-cap timing** (pending audit A): food, not money; no money is created — owned stock
  above the cap between Phase 2 close and the next opening can be procured in Phase 10 (paid by
  the treasury, real stock) or destroyed by conquest before the opening cap removes it. Classify as
  an intentional timing boundary; add a counter of owned grain procured or lost while above the cap
  **[magnitude unverified]**.

---

## 6. Smallest first implementation slice and test plan

**Slice A1-1: `--wealth-accounting`, Python-only observation ledger + `schedule` boundary.**

Files: new `src/chronicler/wealth_accounting.py`, `wealth_accounting_state.py`; edits to
`livelihoods_state.py` (switch appended last, state field), `livelihoods.py` (prerequisites, help,
modes), `feature_catalog.py`, `batch_manifest.py` (pinned: lead layer), `household_retail.py`
(`schedule` boundary, `opened_turn` map, cohort aggregates), `household_retail_state.py`, viewer
reader later. No native change; no edit to RS2, PL1, PL3, L6a, RS1, RS4, L7 or domestic credit.

Tests (offline chunk with headroom or a new chunk; native shard for real-extension tests):
1. Feature-off identity: `turn_speed_identity` cases against `8abc1acb` and the preceding main —
   0 differences; manifest bytes unchanged.
2. Observer identity: a hybrid all-switch run with and without `--wealth-accounting` differs only
   in `livelihoods.wealth_accounting` (full world dump comparison, like retail's `record_only`).
3. No-hidden-writer: closing(t) equals opening(t+1) per id bit for bit over 30 turns on a
   development world with every payer on; a deliberately injected `transfer_wealth` between Phase 10
   and the next Phase 2 must be detected.
4. Typed-flow closure per purpose: treasury debit = credited + kept residual + declared sink, for
   RS2, PL1, PL3 (paid and unpaid), L6a, RS1, procurement, RS4 (fee), L7 (fare, assistance), food
   purchases (net zero for the household sector), domestic credit (applied vs due).
5. Withheld-income attribution: every paid-work receipt row is attributed to exactly one package;
   PL3 granary + workshop = PL3 total.
6. Checkpoint: exact resume mid-run (incl. a live expedition and a retail settlement turn) yields
   the same ledger frames as an uninterrupted run; switch turned off on resume drops state with a
   dated record; a legacy JSON resume records a pool-reset discontinuity; resume under
   `--agents off` is refused.
7. `schedule` boundary: an unknown region or negative turn is refused; replaying arm A's openings
   reproduces A's per-region pilot region-turns exactly (as the exploratory replay did 10/10);
   resume keeps the schedule and refuses a conflicting one.
8. Snapshot reader: absent, malformed, unobserved (`None`) and recorded-zero are distinct.
9. `CHRONICLER_CHECK_RESOURCES=1` all-switch procedural run passes with the ledger on.

Slice A1-2 (native observer) follows with its own extension build, Rust unit tests for each
channel (including D1's no-heir estate and D2's clamp), and the same identity tests.

---

## 7. What other programs will depend on

- **A3 workshop economics**: payroll, input purchases, customers' payments and arrears pay through
  the §3.3 seam; firm cash is an account in the ledger; withheld income attribution by package.
- **A4 merchants**: a pairwise household/merchant payment with purpose codes (native addition);
  replacing `merchant_trade_income` (row 3) rather than stacking profits; merchants are the largest
  priced-out group under retail **[dev]**, so A4 changes who can buy food.
- **A5 owned-stock lifecycle**: inheritance of owned food follows Python's rule (spouse, children in
  region) while native wealth estates follow `household.rs` (spouse, dependants anywhere, children
  anywhere) — A5 must keep both exactly-once and recorded; D1 must be counted first.
- **A6 adaptive decisions**: experienced wages and prices are per-person flows the ledger records.
- **B3 infrastructure repair, C2 care funding, D4 reconstruction**: treasury → household wages and
  fees through the seam; the ledger's treasury side shows created treasury income (D3).
- **C1 quarantine** (trade and labour costs) and **D3** (soldiers' pay, separation): soldier income
  is model-created (row 2) and conquest pays a one-shot bonus; any campaign pay must replace, not
  add.
- **E**: viewer panels read `livelihoods.wealth_accounting`; evidence runs record the ledger as a
  harm/mechanism panel (money credited, model share).
- **Lead (shared contracts)**: purpose codes (append-only), payer accounts, the turn-order rows in
  §1.3, witness layers for `batch_manifest.py` (slice 1) and `tick.rs`/`pool.rs`/`household.rs`/
  `ffi/mod.rs` (slice 2).

---

## 8. Open questions

1. Should decay be treated as the stand-in for all non-food consumption? Under retail, food is now
   paid explicitly while decay still removes 2% a turn, so pilot households arguably pay for food
   twice. A rules-versioned option could offset decay by food spending; it changes dynamics and
   needs the owner's decision.
2. Should the treasury tax and tithe debit merchants (a rules version)? It would make treasury
   money conserved but lowers merchant wealth, which feeds credit capacity, luxury demand and
   satisfaction (§1.4).
3. Which residual policy is canonical for refused credits (return to payer vs declared sink)? D5.
4. Should non-farm adults in a pilot region receive anything for food (they hold no title)? The
   exploratory data say they are three quarters of the priced-out; relief currently targets
   households by means test only.
5. Region attribution of flows for migrants (residence at the flow vs home region) — slice 1 uses
   residence at the snapshot; RS4 uses origin/destination.
6. Do children living apart from parents (L2 households of one) need a transfer path (the parent's
   wage cannot reach them unless RS4 links them)? Small numbers here (15–17 person-turns per arm).
7. Is `paid_work` still the right story boundary for screens, given D6? A fixed preregistered
   schedule or `market`/`all` with person-level cohorts answers the wage question without the
   confound; `paid_work` remains useful as the enrollment story itself.
