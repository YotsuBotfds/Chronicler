# Money, credit and public finance

Branch `feat/money-credit`, based on `integrate/wave-2` at `db26681` (PR #18:
goods economy, live governance with the PSI, the contact ledger, campaign
warfare, causal provenance, fisheries and mutual aid). Code:
`src/chronicler/finance.py`; hooks in `simulation.py` (Phase 3b and end of
turn), `governance_runtime.py` (PSI), `action_engine.py` (weight bucket),
`provenance.py` (keys and episodes), `models.py`, `main.py`, `live.py`.

**Status: default on** for new worlds since the 2026-10 all-on full gate
(`docs/integration/wave3-defaults.md`). The setting is saved on the world
(`WorldState.finance`); `--no-finance` turns it off. With the switch
off no finance code runs and every output is byte-identical to `db26681`
([identity](#flag-off-identity)). The default is to be decided after the
food-balance work lands and a full gate runs.

## Why

The ideation found idle treasuries piling up (11-15K per civ) while the
economy stat sat at 95+ in a quarter to half of all civ-turns (two thirds in
the 200-turn subset below), and nothing in the simulation borrowed, lent,
defaulted or inflated.

**What fills and drains the treasury at the base.** Every treasury change
recorded by the accumulator in seed 42 (hybrid, 200 turns, 4 civs), summed by
emitting function:

| Inflow | Total | Outflow | Total |
| --- | ---: | --- | ---: |
| prestige trade bonus (`culture.tick_prestige`, prestige // 5) | 16,414 | DEVELOP action | 3,772 |
| base production income (`economy // 5 + 2 * regions`) | 12,090 | governing costs (size and distance) | 2,358 |
| Phase 2 route trade income and specialization bonus | 3,490 | institution enforcement (governance) | 1,896 |
| goods-economy merchant tax (5% of merchant wealth) | 3,016 | military maintenance, war costs, mercenaries (Phase 2) | 1,510 |
| campaign plunder, requisition, tithes | 17 | INVEST_CULTURE, counter-propaganda | 1,384 |
| | | BUILD | 804 |
| | | proxy wars, MOVE_CAPITAL, FUND_INSTABILITY, campaign spending, hostages | 1,207 |
| **total** | **35,027** | **total** | **12,931** |

Income outran spending almost three to one, and every recurring cost is
fixed in size (no cost grows with revenue), so treasuries grew without bound:
6K per civ by turn 200 in seed 42, a mean of 9.1K over the 20-seed subset and
30K by turn 500 (table below). Nothing spends a surplus: past the
affordability checks of building, developing and technology, a hoard only
switches on the `treasury >= 200` EXPAND/TRADE weight boost and dominates the
COMMERCE/BANKING tech-focus scores (`treasury * 0.1` / `0.15`).

**The PSI stub.** `governance_runtime._advance_psi` feeds the state fiscal
distress sub-index with `governance_stress.sfd_raw(governing_cost, treasury,
enforcement_cost, legitimacy)`: governing cost over treasury, the roadmap D5
stand-in "until M66 introduces explicit debt tracking" (`state_debt` "doesn't
exist yet"). With treasuries in the thousands it read near zero for every
mature civ, so fiscal distress could only drive a crisis in the first decades.

## What it does

### State

`WorldState.finance: FinanceState | None` (presence = on). Civilization
identity is its index in `world.civilizations` and region identity its index in
`world.regions`; nothing keys on names.

| Field | Contents |
| --- | --- |
| `civs[i]` (`CivFinance`) | smoothed revenue, price index and target, inflation, coin fineness, creditor-class wealth, credit premium, default memory, domestic trust, arrears, grace and exclusion turns, creditor grievance toward defaulted debtors (by civ index), fiscal stress, last tick's accounts, cumulative accounts |
| `loans` (`Loan`) | one credit line per (borrower, lender): principal, principal at the last (re)scheduling, per-turn rate, term, fractional interest carry, capitalized interest, the id of its `loan_taken` event. `lender` is a civ index or `DOMESTIC` (-1), the merchant/elite creditor class |
| `region_specie`, `region_output`, `region_occupier` | specie held in each region, its smoothed real output, its last occupier (civ index or -1) |
| `totals` | world ledger: issued (domestic, foreign), repaid principal, interest (domestic, foreign), capitalized, written off, seigniorage, royal bullion |

### Fiscal tick (Phase 3b)

`finance.tick_finance` runs right after Phase 3 production, when every
ordinary income of the turn is in the accumulator. All treasury changes are
`keep` entries, like tax and trade income, written through a projection that
mirrors `StatAccumulator.apply` (each change floored at zero), so a payment
is never larger than what the treasury will hold when it is applied.

1. **Revenue.** The sum of this turn's positive `keep` treasury changes
   (production, prestige, trade, tax, tribute, institutions), plus its ad
   valorem share `TAX_INDEXATION = 0.75` times `(P - 1)`: nominal revenue
   follows prices, partly. Smoothed (`REVENUE_EMA_ALPHA = 0.2`). The crown's
   share of last turn's new bullion is paid in.
2. **Obligations.** Upkeep at current prices, `P * (0.15 * military + 1.0 *
   regions + 1.0 * population / 100)`, and debt service on every line:
   interest `principal * rate` (fractions carried) plus amortization
   `ceil(original / term)`.
3. **Financing.** When the treasury would not cover obligations plus one
   turn of upkeep (or, at war, the full reserve target: wars are fought on
   credit), the state borrows the gap plus three turns of upkeep: first from
   its merchant houses, then from foreign lenders. Still short of its
   obligations for a second turn, with a shortfall of at least a quarter of
   them, it **debases**.
4. **Payment.** Upkeep first, then service, oldest line first. Unpaid interest
   is capitalized into the principal. Unpaid upkeep costs 2 military (`guard`)
   and 2 stability (`signal`).
5. **Arrears and default.** A turn with at least a quarter of its obligations
   unpaid is a turn of arrears; after `ARREARS_LIMIT = 2` such turns, with
   service unpaid and debt of at least a turn of revenue (smaller debts roll
   over), outside an 8-turn grace period after the last restructuring, the
   state **defaults**.
6. **Surplus.** An indebted state at peace that did not borrow this turn
   repays its dearest line from above half its reserve target; then the
   **court** spends `0.3 * revenue * (1 + 0.5 * conspicuous consumption)`
   (the governance EMP ratchet), scaled down while the reserve is short, while
   debts are owed and at war, plus 8% of any surplus above the reserve target
   (8 turns of revenue, and at least 1.5x the next tech advance).
7. **Consequences** of last turn's inflation above 3% a turn: up to 4
   stability (`signal`).
8. **Fiscal stress**: debt over ten turns of revenue, plus service over
   revenue, plus the deficit (all recorded spending, upkeep and service
   against revenue), plus 0.5 in arrears, plus a decaying 1.0 after a
   default, plus ten times smoothed inflation; capped at 4.

### Lenders

* **Domestic.** The merchant/elite creditor class lends up to half the
  smoothed merchant wealth plus three turns of revenue times merchant faction
  influence, times domestic trust, less what it is already owed. Merchant
  wealth is the goods economy's own tax base (`EconomyResult.treasury_tax /
  TAX_RATE`, the per-civ merchant agent wealth the Rust economy reports); with
  `--agents off` it is `1.5 * economy * regions`. Rate 4% a turn plus 0.3% per
  turn of revenue already owed, plus the credit premium and smoothed inflation
  (capped at 25%).
* **Foreign.** A civ with no debt and no arrears lends half of what it holds
  above the larger of half its reserve target and four turns of its
  obligations, less the obligations it has yet to pay. A borrower takes the
  best of the living civs it is not at war with, that are not hostile toward
  it, that it has contact with (contact-ledger `civ_contact` over all flow
  channels; neighbours when the ledger is off) and that hold no grievance of
  0.5 or more against it, scored by room times contact. Base rate 6%. A
  quarter of the principal (and of its service) moves as specie.

### Default

Half of every line is written off (80% if the last default is still
remembered), the rest is rescheduled over 20 turns at the plain base rate.
Stability -10 (`signal`), ruler legitimacy -0.1 (governance), credit premium
+4 points (decays 3% a turn), default memory +1 (shrinks the debt ceiling of
ten turns of revenue). Domestic creditors: domestic trust halved, economy -3
(`signal`), merchant influence -0.05. Foreign creditors: grievance `0.5 +
min(1, loss / 5 turns of the lender's revenue)` (decays 3% a turn), and the
lender's disposition toward the debtor drops one step. Foreign lenders shun
the defaulter for 15 turns per default (up to three); its merchant houses
offer only a quarter of their capacity meanwhile. Debts of a fallen borrower
are lost, and debts owed to a fallen lender lapse (`debt_written_off`).

### Money and prices

Per region, specie `S_r` and smoothed real output `Y_r = population * (0.5 +
economy / 100)` (5% EMA). New output is monetized at once (commerce brings
coin with the goods); when output falls, 80% of its coin leaves with it and
the rest becomes excess specie. Then:

* **Minting.** A precious-metal slot of a populated, controlled region mints
  `12 * effective yield * reserves` silver a turn; the crown takes 20%, paid
  into the treasury at the next fiscal tick.
* **Sack.** A region newly occupied loses a quarter of its specie to the
  occupier's capital (detected from `Region.occupied_by`, consumed once).
* **Price-specie flow.** Every region's specie closes 4% of its gap to the
  money demand of its output (`6 * Y_r`) a turn (Hume).
* **Price index.** A civ's target price is `(S / 6Y) ^ 0.5 / fineness` over
  its regions (half of excess specie is absorbed by velocity); the index
  closes 10% of the gap a turn (sticky prices), clamped to [0.25, 25].

So a large inflow (sack loot, a new silver mine, a foreign loan) lifts prices
over decades and the specie flow wears it down again: a slow price
revolution. **Debasement** cuts fineness by 15% (cooldown 15 turns, floor
25%): prices rise toward `1 / fineness` over about 20 turns and stay there
(the unit of account changed), the crown keeps half the nominal coin added by
the recoinage (it only debases if that raises at least a turn of revenue),
credit premium +1 point,
stability -2, merchant influence -0.02. Domestic debt is nominal, so inflation
erodes it in real terms while revenue follows prices for three quarters.

### Consumers

* **PSI `state_debt`.** With finance on, `_advance_psi` takes the raw SFD from
  `finance.psi_fiscal_distress`: `0.04 * fiscal stress * (1 + enforcement /
  revenue * (1 - institutional legitimacy))`. 0.04 is the governance
  `sfd_reference`, so a fiscal stress of 1 is an "elevated" sub-index. This
  replaces the governing-cost/treasury proxy; a debt-free, balanced polity is
  neutral.
* **Action weights.** `finance_weight_modifiers` is a contributor bucket
  placed after the governance bucket and clamped to `[1/1.25, 1.25]` before
  the global 2.5x cap. Creditor leverage, per unit of foreign debt over ten
  turns of revenue (up to 1.5): WAR -15%, TRADE +15%, DIPLOMACY +7.5%.
  Austerity at fiscal stress 1 or more (up to 2): BUILD -10% and DEVELOP -5%
  per unit. A creditor's grievance toward a living defaulter (up to 1.5): WAR
  and EMBARGO +20% per unit. Weights do not pick war targets, which must be
  hostile or suspicious; the one-step disposition drop on default moves the
  defaulter toward that.
* **Provenance.** `loan_taken` (opening a line, or a material advance) cites
  what drained the treasury: the civ's wars, a recent revolt, civil war or
  plague, its latest famine, occupations of its regions. `debasement` cites
  the same. `state_default` cites the credit lines it repudiates.
  `debt_written_off` cites the line and the lender's fall. `state_default`,
  `debasement` and `fiscal_strain` register the debtor's `fiscal` key, so a
  PSI crisis driven by fiscal distress cites them. `fiscal_strain` (fiscal
  stress of 1 or more) and `price_inflation` (2% a turn or more) are chronic
  conditions reported at the capital, folded into one episode each with a
  closing `fiscal_strain_ended` / `price_inflation_ended` event.

### API for diplomacy (tribute, indemnities, inter-state loans)

```python
from chronicler import finance
finance.transfer(world, payer_idx, payee_idx, amount, acc=acc)        # -> amount paid
finance.extend_loan(world, lender_idx, borrower_idx, principal, acc=acc,
                    rate=None, term=None)                              # -> Loan | None
finance.outstanding_debt(world, borrower_idx, lender_idx=None)
finance.foreign_debt(world, borrower_idx)
finance.creditor_claims(world, lender_idx)   # {borrower_idx: principal}; DOMESTIC = -1
finance.price_index(world, civ_idx)
```

`transfer` pays at most the payer's projected treasury (`keep` entries) and,
with finance on, moves the specie too, so tribute moves prices. It works with
finance off (treasury only). `extend_loan` books the loan on the borrower's
credit line with that lender; the borrower's fiscal tick services it. Tribute
itself is not built here.

## Contracts

* **Determinism.** No random draws at all: fixed iteration by civ and region
  index, integer treasury flows with persisted fractional carries.
* **Accumulator.** Treasury changes are `keep` (as tax and trade income);
  stability and economy consequences `signal` (they reach agents as shocks in
  hybrid); unpaid-troop desertion `guard` (agents own military in hybrid).
* **Enums.** None added or reordered.
* **Transient signals.** None: every tick input is persisted state or this
  turn's accumulator. Amounts carried between turns (crown bullion, upkeep
  and interest fractions, the last occupier) are persisted and consumed
  once; tests check the sack and the bullion are not applied twice.
* **Caps.** The finance bucket is pre-clamped and the global cap is untouched.

## Switch, defaults, persistence

| Surface | Value |
| --- | --- |
| CLI | `--finance` / `--no-finance` (`BooleanOptionalAction`, `None` = default or saved) |
| World field | `WorldState.finance: FinanceState \| None` (presence = on) |
| Default | **on** for worlds created by `execute_run`, batch and the live server (`finance.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, since the all-on full gate in `wave3-defaults.md`); `--no-finance` opts out; resumed, forked and supplied worlds keep their setting |
| Gate runner | `scripts/m53b_run_validation.py --finance` forwards the flag to every run and records it in `run_manifest.json` |
| Serialization | `None` is omitted from `state.json` and bundle `world_state`; `TurnSnapshot.finance` (per living civ: debt, foreign debt, revenue, upkeep, court, service, interest, borrowed, shortfall, price index, inflation, fineness, fiscal stress, arrears, defaults, debasements, premium) is omitted while `None` |
| Analytics | `analytics.generate_report` adds a `finance` section when bundles carry it |

Old saves and bundles load unchanged (`finance` absent = off). A save with
outstanding loans resumes bit-identically (tested).

## Verification

All evidence below was produced on Linux, Python 3.13, with a fresh
`maturin develop --release` build of the unchanged Rust tree, on the code of
`56b9708` (later commits change documentation only).

### Tests

`tests/test_finance.py` (23 tests): debt-ledger balance over a full run
(outstanding principal = issued + capitalized - repaid - written off, and the
per-civ accounts agree); foreign service netting out exactly across all
treasuries; `transfer` (pays at most the treasury, moves the same specie both
sides, works with finance off); the interest and amortization schedule (exact
interest with carries, principal path); capitalization of unpaid interest;
prepayment of the dearest line first; default after material arrears
(haircut, rescheduling, stability, legitimacy, premium, grievance,
disposition, exclusion, grace); small debts rolled over; debasement (gain,
fineness, cooldown, unchanged silver, prices rising monotonically and slowly
to `1 / fineness`, inflation decaying, the price-inflation report); a sack and
crown bullion each consumed exactly once; save/load resume identity with
outstanding loans; determinism; no transient state; feature-off dormancy (the
finance entry points are forbidden while off); dormant serialization and old
saves; the PSI input; the clamped, directional weight bucket; provenance
chains (loan cites the war, default cites the lines and registers the fiscal
key); the CLI flag, the new-world default, resume, bundle history and
analytics; gate-runner forwarding; native hybrid determinism with creditor
wealth read from the economy.

| Lane | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (native venv) | **5,520 passed, 3 skipped** (base: 5,497 passed, 3 skipped; +23 finance tests) |
| `pytest -m "not slow" -n 2` (venv without `chronicler_agents`) | **5,321 passed, 188 skipped** (native-only tests skip) |
| No-Rust simulation (`--agents off --finance`, seed 42, 200 turns) | runs: 31 loans (10 foreign), 2 defaults, 2 debasements, prices 0.74-1.51, all four civs alive |
| `python scripts/run_python_oracle_checks.py` | **1,596 passed, 3 skipped, 2 deselected**, with PR #19's one-line guard fix applied locally (not committed) |

### Flag-off identity

`scripts/finance_identity.py compare` (adapted from
`scripts/epidemiology_identity.py`). Base `db26681` (source exported and put
on `PYTHONPATH`) against this branch with no flag and with an explicit
`--no-finance`, same interpreter and native build, `PYTHONHASHSEED=0`:
`--agents hybrid` 200 turns and `--agents off` 300 turns, seeds 42, 7 and
1234. Every file (`state.json`, `chronicle.md`, `memories_*.json`,
`agent_events.arrow`, `chronicle_bundle.json` minus `metadata.generated_at`):
**45 files compared, 0 differences** for both, on `56b9708`. The in-suite
frozen golden fixtures (`tests/fixtures/performance/`,
`test_performance_equivalence`, `test_governance_dormancy`,
`test_turn_artifact_lifecycle`) pass unchanged.

### Subset gate (20 hybrid seeds x 200 turns, `--parallel 2`)

| Run | Gate | `validation_compare` | satisfaction mean | latest satisfaction | migration rate | regression oracle (informational) |
| --- | --- | --- | --- | --- | --- | --- |
| base `db26681`, seeds 42-61 | PASS | n/a | 0.4813 | 0.4544 | 0.0505 | FAIL: civ_survival |
| `--finance`, seeds 42-61 | PASS | **NO REGRESSION** vs base | 0.4768 | 0.4326 | 0.0501 | FAIL: civ_survival (+ strict latest satisfaction; calibrated floor passes) |
| branch flag off, seeds 62-81 | PASS | n/a | 0.4978 | 0.4849 | 0.0485 | FAIL: civ_survival (+ strict migration) |
| `--finance`, seeds 62-81 | PASS | **NO REGRESSION** vs flag off | 0.4936 | 0.4829 | 0.0517 | FAIL: civ_survival |

The seeds 42-61 baseline is the validation report of the wave-2 integration
gate at `db26681` (same source and Rust tree; the branch with finance off is
byte-identical to it). Seeds 62-81 compare against this branch with finance
off. All oracle statuses match their baseline in seeds 42-61 (arcs, cohort,
community, era, needs PASS; artifacts PARTIAL; determinism SKIP; regression
FAIL as on base). Satisfaction is 0.004 lower in both seed sets; the 0.022
drop of latest satisfaction in the first set shrinks to 0.002 in the second,
so most of it is run-to-run divergence. Finance's own stability penalties are
rare (a shortfall in 1.2% of civ-turns, inflation above 3% a turn in 5 of
13,036 civ-turns).

**Era oracle, seeds 62-81: PASS -> FAIL (5 of 20 "silent collapse" seeds; 1
of 20 in seeds 42-61, still a PASS).** Era is informational in the subset
profile but required in the full profile, so this matters for the default
decision. The oracle calls a seed silent when some civ's population falls 30%
below its peak with no inflection point of *any civ's* population, treasury,
stability, territory or prestige series between five turns before the peak
and five after the trough. At the base about three quarters of all
inflections come from treasury series (seeds 42-61: 924 of 1,264; seeds 62-81:
881 of 1,208), which jump with hoarded windfalls and large purchases; finance
makes treasuries homeostatic (165 and 181 treasury inflections). The
"silent" cases in seeds 62-81 are slow declines over 22 to 75 turns (for
example Kethani Empire in seed 69, 132 people at t100 to 75 at t163). Such
declines are as common with finance off (17 declines of 30% or more in these
five seeds either way); off, every one is covered, mostly by some other civ's
treasury jump. A fix belongs in the oracle (per-civ inflections, or fiscal
series such as debt among the signals), not in finance; it is not made here.

### On/off numbers (per run means or totals over 20 runs, 200 turns, hybrid)

| Metric | off 42-61 | **on 42-61** | off 62-81 | **on 62-81** |
| --- | ---: | ---: | ---: | ---: |
| treasury, median over living civ-turns | 2,794 | **492** | 2,621 | **461** |
| treasury, 90th percentile | 7,764 | **1,051** | 8,182 | **919** |
| treasury at turn 200, mean | 9,082 | **998** | 9,198 | **858** |
| treasury, largest | 15,444 | **1,776** | 16,484 | **1,993** |
| civ-turns with economy >= 95 | 66.8% | 69.8% | 68.8% | 67.4% |
| loans (foreign) | 0 | **138 (62)** | 0 | **145 (68)** |
| runs with loans | 0 | 18 | 0 | 17 |
| defaults (runs) | 0 | **12 (3)** | 0 | **25 (7)** |
| debasements (runs) | 0 | **16 (6)** | 0 | **31 (7)** |
| fiscal-strain / price-inflation episodes | 0 / 0 | 42 / 12 | 0 / 0 | 60 / 15 |
| debt / revenue: 90th pct (mean of runs), max | 0, 0 | 0.49, 11.5 | 0, 0 | 0.42, 13.6 |
| share of civ-turns in debt (run mean) | 0 | 9.1% | 0 | 10.6% |
| price index range | 1.00 | **0.88-3.75** | 1.00 | **0.86-3.82** |
| PSI mean / max | 1.40 / 12.6 | 1.29 / 17.1 | 1.29 / 15.9 | 1.09 / 15.1 |
| PSI crises | 51 | 58 | 50 | 50 |
| revolts / civil wars | 218 / 0 | 197 / 1 | 198 / 2 | 152 / 1 |
| polities alive at turn 200 (mean) | 3.05 | 3.00 | 3.15 | 3.15 |
| population at turn 200 (mean) | 393 | 378 | 387 | 407 |
| extinct worlds | 0 | **0** | 0 | **0** |

500 turns (hybrid, seeds 42-45, 4 runs):

| Metric | off | **on** |
| --- | ---: | ---: |
| treasury, median over living civ-turns | 11,897 | **786** |
| treasury, 90th percentile | 26,632 | **1,246** |
| treasury at turn 500, mean | 30,285 | **1,211** |
| treasury, largest | 39,913 | **2,811** |
| loans (foreign), runs with loans | 0 | 42 (23), 2 of 4 |
| defaults / debasements (runs) | 0 / 0 | 8 / 9 (both in 1 run) |
| debt / revenue max | 0 | 9.5 |
| price index range | 1.00 | 0.94-3.79 |
| PSI mean, crises, revolts | 1.56, 15, 155 | 1.57, 25, 159 |
| polities alive at turn 500 (mean), population | 3.25, 455 | 3.00, 444 |
| extinct worlds | 0 | **0** |
| tech advances | 56 | 84 |

Late in long runs revenue outgrows every cost, so rich states borrow mainly
for war (the war chest) and the court absorbs the rest; credit stays busy
where famine and war keep a polity poor. Per-run numbers for every table
come from `scripts/finance_census.py <batch dirs> --json <file>`.

## Seed-42 fiscal stories

Subset seed 42, hybrid, 200 turns, `--finance` (the gate run). Every arrow is
a recorded `causes` link (effect cites cause), read from the bundle.

**1. Thornwall Confederacy: famine debts, a vanished creditor and the
debasement trap.** A food supply shock in Iron Peaks (t19) becomes famine
(t26), and Thornwall borrows from its merchant houses (t29, 22 at 5.7%,
citing the famine and a plague) and then from the Selurian Republic (t35, 41
at 8.4%). Its fiscal crisis opens at t31 and lasts 61 turns. By t50 it owes
405 (321 abroad), fiscal stress 3.6. The Selurian Republic is absorbed (t50):
"With Selurian Republic gone, the 321 Thornwall Confederacy owed it lapses"
(t51, citing the loan). Still unable to pay its own merchants, it debases to
72% silver (t54) and defaults on them (t58, repudiating 45). Four turns later
"Thornwall Confederacy enters an age of troubles (fiscal distress)" (t62, the
PSI crisis cites the default; PSI 0.4 at t30, 3.4 at t70), and revolts follow
(t68, t72, both citing the crisis). A debasement at t69 cites the revolt; the
price inflation it starts (t70, index 1.38) cites the debasement. Readmitted
to credit, Thornwall borrows from Ashkari and Kethani (t96, t101) and its
merchants (t106), defaults again (t121, repudiating 301 to Ashkari Nomads,
Kethani Empire and its merchant houses; cites the three loans and the latest
famine), and enters a second fiscal-distress PSI crisis (t126). By t199 it has
defaulted six times and debased eight, to 27% silver, with prices at 3.7x.

    t19 supply shock Iron Peaks -> t26 famine -> t29 loan (merchant houses)
        -> t58 state_default -> t62 psi_crisis (fiscal distress) -> t68, t72 revolt
                                                         -> t69 debasement -> t70 price_inflation
    t31 famine -> t35 loan (Selurian Republic) -> t51 debt_written_off (lender absorbed)

**2. Kethani Empire: a lost war of tribute, paid off.** Kethani goes to war
with Thornwall seeking tribute (t0) and borrows from its merchant houses the
next turn (t1, citing the declaration). Revenue collapses from 23 to 6 by
t10, the treasury to 8, and a fiscal crisis opens (t8, citing the loan, the
war, a plague and a famine). Ashkari Nomads lends 42 at 6.6% (t11, citing the
war). Kethani accepts defeat and pays 3 in reparations (t12). Famine keeps it
borrowing, from the Selurian Republic (t19-t29) and its merchants (t27): a
second fiscal crisis (t27-t39) peaks at 80 owed (48 abroad) at t30. Without a
default or a debasement it repays: 5 owed at t50, debt-free by t60, with
revenue back to 51.

    t0 war_declared (tribute) -> t1 loan (merchant houses) -> t8 fiscal_strain
                              -> t11 loan (Ashkari Nomads)
    t18 famine -> t19, t21 loans (Selurian Republic) -> t27 fiscal_strain

**3. A creditor's war chest.** Ashkari Nomads, debt-free and in contact with
both, is the lender of choice for Kethani's war (t11) and Thornwall's famine
years (t96, t180: 171 at 10.6%); its claims on Thornwall are written down at
each default (t121, t188, t196), and the grievance it holds raises its WAR and
EMBARGO weights while Thornwall lives.

## Effects on other systems

Measured over the same 2 x 20 runs (off -> on); single-seed outcomes diverge
chaotically, so only consistent shifts are read as effects.

* **Governance.** Institution enforcement goes unpaid more often
  (`fiscal_crisis` 12 -> 47 and 22 -> 92): enforcement is paid in Phase 2 from
  last turn's treasury, which no longer holds thousands. The PSI now moves
  with debt: Thornwall's PSI rises from 0.4 to 3.4 through its defaults (seed
  42), while debt-free polities lose the early-game fiscal-distress readings
  the governing-cost/treasury proxy produced, so mean PSI falls (1.40 -> 1.29,
  1.29 -> 1.09). PSI crises stay level (51 -> 58, 50 -> 50); revolts fall
  (218 -> 197, 198 -> 152). Neglect repeals and enforcement lapses now cite
  defaults through the fiscal key.
* **Action mix.** TRADE actions fall (628 -> 535, 736 -> 493): fewer civ-turns
  clear the `treasury >= 200` TRADE/EXPAND boost, and TRADE needs bronze-age
  tech, which some runs reach later. Mercenary companies (526 -> 430,
  542 -> 608), EXPAND and DEVELOP move both ways. COMMERCE/BANKING tech
  focus loses its treasury-driven score (9 of 27 -> 5 of 33 focus choices;
  26 of 55 -> 12 of 38).
* **Technology.** 96 -> 110 and 139 -> 88 advances. With finance a civ saves
  for each advance (the reserve target is at least 1.5x the next cost)
  instead of buying several eras in consecutive turns from a hoard; the
  largest drops (seed 71: 10 -> 0, seed 79: 12 -> 0) are runs in which no civ
  ever held the ore and timber regions the first advance requires, a
  territorial divergence rather than a treasury gate.
* **Wars** 29 -> 29 and 25 -> 28 declared; embargoes 82 -> 76 and 98 -> 119.
  The weight bucket damps debtors' WAR and raises a burned creditor's WAR and
  EMBARGO, but at these rates of default the counts are within divergence.
* **Economy** saturation (economy >= 95 in two thirds of civ-turns) is
  unchanged: the economy stat is agent-derived in hybrid and finance does not
  touch it.
* **Food, ecology, agents, Rust:** unchanged code. Finance reads merchant
  wealth from the economy result and region yields, and never writes them.
* **Bundles and saves** grow by the finance summaries (seed 42 bundle
  4.9 -> 5.5 MB).

## What was cut

* **Per-good prices.** One price index per civ; the Rust goods economy's
  prices are untouched (as asked).
* **Tribute, indemnities, treaties.** Not built (diplomacy's scope). The
  `transfer` / `extend_loan` API is ready; existing tribute, peace-treaty
  payments and occupation plunder move treasury but not specie (only the sack
  of a newly occupied region moves coin).
* **Domestic creditors' agent wealth.** Interest and repayments to the
  merchant houses leave the treasury into the finance ledger only; merchant
  agents' wealth in the native pool is not credited (no FFI change).
* **Inflation and wages.** Inflation costs stability and erodes debts but does
  not feed agent wages, satisfaction or the PSI's popular-immiseration input.
* **Exchange rates.** All treasuries count in one unit; fineness affects
  prices and specie flows, not the value of foreign debts.
* **Currency reform.** Fineness is never restored; a debased coinage stays
  debased.
* **Ruler policy.** Borrow, debase and default follow fixed rules; leader
  traits and factions do not choose among them.
* **Demobilization.** Unpaid troops desert through a `guard` change, which is
  inert in hybrid (agents own military).
* **War aims.** Creditor grievance acts through action weights and
  disposition; war-target selection is unchanged.
* **Calibration.** Parameters are illustrative calibrations from 20-seed
  subset batches (and 4 x 500-turn runs), not fitted against the 200-seed gate.

## Follow-ups

* Decide the era-oracle treatment of slow declines before a full gate with
  finance on (above).
* Re-run the subset and full gates after the food-balance work lands: famine
  drives most deficits in hybrid worlds (seed 42's loans cite famine).
* Diplomacy: route tribute and indemnities through `finance.transfer`, and
  consider loans as treaty terms (`finance.extend_loan`).
* Optional: credit merchant agents with domestic interest through a bridge
  signal (done behind `--domestic-credit`, default off: merchants, guilds
  and cities fund domestic loans and bear their losses;
  [domestic-credit.md](domestic-credit.md)); inflation into the MMP; a
  recoinage reform.

## The merchant tax (2026-10-28, `fix/merchant-tax`)

Branch `fix/merchant-tax` from `main` `cb9fe70` (PR #67). PRs #63 and #67
noted that "the merchant tax is not debited from agent wealth, so richer
merchants create more revenue" (`domestic-credit.md`, 11.2 (4) and 13.2,
problem 4). This section traces it, gives the verdict, and describes the
correction, its pre-registration and its results. It is a **correction
of default behaviour**, not an optimization: every agent-mode run changes.

### Trace (`main` `cb9fe70`)

1. **Assessment (native).** `AgentSimulator::tick_economy`
   (`chronicler-agents/src/ffi/mod.rs:2520`) sums, per civ that controls a
   region, the wealth of every living merchant agent of its affinity, in
   f32, wherever the agent stands (`ffi/mod.rs:2795-2829`, the live pool's
   `wealth`). `tick_economy_core` assesses `treasury_tax = tax_rate * mw`
   (`economy.rs:1848`; `tax_rate` 0.05, `economy.rs:163`; Python
   `economy.TAX_RATE`, `economy.py:40`) and the tick packs it in the civ
   result batch (`ffi/mod.rs:2983`). The same sum, times a food gate, is
   the tithe base (`economy.rs:1842-1850`).
2. **Into the treasury.** `reconstruct_economy_result` reads it into
   `EconomyResult.treasury_tax` (`economy.py:1594-1601`).
   `simulation._apply_treasury_tax_from_economy` (`simulation.py:1799-1821`,
   called in Phase 2 at `simulation.py:2105`) adds `int(tax + carry)` to
   the civ's treasury as a `keep` change and carries the fraction
   (`world._treasury_tax_carry`). This happens in every agent mode
   (hybrid, shadow, demographics-only); `--agents off` has no economy
   result and no tax.
3. **Who reads it.** Finance counts it as revenue (every positive `keep`
   treasury change, `finance._turn_revenue`, `finance.py:383`, used at
   `finance.py:1036`). So it feeds the revenue EMA, the reserve target, the
   debt ceiling, the court and, with `--domestic-credit`, the borrower's
   room and the cold-start houses. Finance also reads it back as the
   creditor class's wealth, `treasury_tax / TAX_RATE`
   (`finance._merchant_wealth_now`, `finance.py:649-657`).
4. **Who pays it: nobody.** Agent wealth is written only by the wealth
   tick (income, 2% decay, clamp to 0..100; `tick.rs:1351-1354`; a
   merchant's income is `region.merchant_trade_income`, `tick.rs:1338`),
   by inheritance (`household.rs:76`, `125`), by domestic credit's
   transfers (`credit.rs:104`, `131`, only with that switch) and by spawn
   and death (`pool.rs`). None of them is told of the tax, and
   `tick_economy` writes no agent wealth. The Python oracle
   (`economy.py:2060`) assesses the same tax from a snapshot; it is a test
   surface, not a production path.
5. **The tithe has the same shape** (not changed here). The clergy's tithe
   pays `int(TITHE_RATE * tithe_base)` (`TITHE_RATE` 0.10,
   `factions.py:35`) into the treasury when the clergy's influence is at
   least 0.15 (`factions.py:426`), and every priest's income gains
   `TITHE_RATE * tithe_base / priests` (`tick.rs:1347`). The base is the
   same merchant wealth, and neither payment is debited from the merchants.

Measured on `main` (the probe below; template seeds 900-919 x 300 turns
and procedural 32 x 10 seeds 900-909 x 200, hybrid; the probe only
reads): the tax paid into the treasuries 4,957 and 7,006 a run, 8.1% and
7.8% of revenue. The merchants earned an estimated 673 and 1,469 a run as
merchants (each region's per-merchant trade income times the merchants
standing there), so the treasuries were paid 7.4 and 4.8 times what the
merchants earned, while the merchants' wealth was untouched. Merchants
hold more than they earn because agents carry their wealth across
occupations (about 5% of agents switch a turn), and the tax took 5% of
that stock every turn it was held.

### Verdict: money creation

The base is a stock that was credited to agents and is never debited.
This is not an abstraction of a levy on flows that never reached the
agents. The tax is computed from `pool.wealth`, the same wealth the
merchants keep, bequeath, carry into other occupations and, under
`--domestic-credit`, lend. Each turn the treasury is credited 5% of that
stock and the stock does not change. So a unit of wealth held by merchants
for its whole life (2% decay) pays about 2.5 units of revenue and is still
there. With `--domestic-credit`, where merchant wealth and treasuries
exchange money under an exact ledger, interest paid to merchants comes
back to the treasury about 2.5 times over as tax.

### Correction

* **Native debit, same tick, same base.** `tick_economy` gains
  `debit_merchant_tax` (default true). The merchants that make up the
  assessment (living, merchant, affinity of a civ that controls a region)
  each pay `tax_rate` of their own wealth: `new = old * (1 - rate)` in f32
  (`chronicler-agents/src/tax.rs`, `plan_merchant_tax`). Per civ the tick
  reports what they paid, the sum of `old - new` in f64, as the civ result
  column `tax_collected` (Float64). The new wealth is written only after
  every result batch is packed (`apply_merchant_tax`), so a failed tick
  changes nothing (as with the delivery buffer), and the snapshot cache is
  dropped. The call keeps no state: nothing crosses a turn and nothing is
  checkpointed. No random draws; slots in order.
* **The treasury is paid what was paid.** `reconstruct_economy_result(...,
  tax_debited=True)` reads `tax_collected` into
  `EconomyResult.tax_collected` and refuses an extension that does not
  report it. `_apply_treasury_tax_from_economy` pays the treasury from it
  (whole units, the fraction carried as before) and keeps the carry of a
  civ not taxed this turn. So per civ and tick, `credited + carry after -
  carry before = paid`. `treasury_tax` stays the assessment, the tax base
  finance reads (`treasury_tax / TAX_RATE`: the merchants' wealth before
  they pay).
* **Restore key.** `economy.merchant_tax_debited` (tuning, default 1). At
  0 the tick is called with `debit_merchant_tax=False` and the treasury is
  paid the assessment, as before: byte-identical to `main` (below). Like
  the production ledger's keys, it is for comparisons and for reproducing
  earlier runs.
* **`--agents off`**: unchanged (no merchant agents, no tax). **Shadow and
  demographics-only** modes tick the economy and credit the tax; their
  merchants now pay it too.
* **Domestic credit.** Its fiscal tick (Phase 3b) reads the merchants'
  wealth after they paid (`merchant_wealth_by_region`), so merchants lend
  from what they hold. Its room and the houses' term are shares of
  revenue, which no longer includes tax nobody paid. Its ledger is
  unchanged and must still balance.
* **Contracts.** Treasury changes stay `keep`. No accumulator category,
  enum, action-weight bucket or cap changes. No native state is added
  (the state schema is unchanged). The tithe is not changed.
* **Ledger.** `CHRONICLER_CHECK_RESOURCES=1` adds
  `chronicler.merchant_tax.TaxLedger`. It reads the pool's merchant wealth
  by civ affinity (`AgentSimulator.merchant_wealth_by_civ`, read only)
  before and after the economy tick. Per civ it checks that the merchants'
  wealth fell by exactly what the tick reports paid (1e-9 relative) and
  that nobody else's changed (under the restore key, nobody's). It checks
  that what was paid is the rate of their wealth and agrees with the
  assessment (1e-5 relative, f32 products), and that `credited + carry
  change = paid` (1e-9). A broken book raises `AssertionError("merchant
  tax ledger does not balance ...")`.
* **Probe.** `scripts/merchant_tax_probe.py` (`run`, `summarize`,
  `compare`) extends `domestic_credit_probe.py`. Per turn it records the
  assessment, the payment, the credit, the tithe base, the tithe to the
  treasuries and the merchants' trade income. It also records occupation
  shares and wealth, treasury, revenue, and agent rates per agent-turn. It
  only reads: a probe run's final state equals a plain run's (both trees,
  template seed 900 x 300).

### Pre-registration

Written and committed before any gate of the branch and before any run of
the confirmatory sets. Development runs seen before it, all on seeds
disjoint from the confirmatory ones: template seeds 900-919 x 300 turns
(`main` and the branch, and both with `--domestic-credit`), procedural
32 x 10 seeds 900-909 x 200 (`main` and the branch), the tests, smoke runs,
and the scholarship test's worlds (seeds 7, 11, 42, 1234, 2024 x 120
turns). Fresh `main` full gates of `cb9fe70` were started before this was
written; they measure `main` only.

Development results (branch - `main`, paired, with SE): template merchant
wealth -54% (SE 4%), tax paid -55%, revenue -6.1% (2.6%), treasury -7.5%
(3.9%), all-agent Gini -0.051 (0.004), satisfaction +0.008 (0.006),
defaults -0.25 (0.25), migration +0.1% (3%), rebellion +4.6% (15%);
procedural merchant wealth -50% (5%), revenue -1.4% (2.2%), Gini -0.039
(0.005), migration -3.7% (2.9%), rebellion -13% (9%). Per-agent wealth
fell in every occupation (farmers -19% to -25%, merchants -52% to -54%).

Confirmatory sets: paired `main` against the branch's frozen tree,
template seeds 42-81 x 500 and procedural 32 x 10 seeds 42-61 x 300 in the
default configuration, and template 42-81 x 500 with `--domestic-credit`
in both arms; the checked runs; both full gates. Predictions, branch
against `main`, paired means over the run unless said:

1. **Merchant wealth** (the pool's total, probe): template -45% to -65%,
   procedural -40% to -60%.
2. **The tax** paid into the treasuries: -45% to -65% in both sets; its
   share of revenue falls from about 8% to 3-5%.
3. **The tithe** (its base, and what reaches treasuries): -40% to -70%.
4. **Every occupation's wealth falls** (per agent): farmers -10% to -35%,
   soldiers and scholars -20% to -45%, priests -25% to -50%, merchants
   -45% to -65%.
5. **All-agent wealth Gini**: -0.025 to -0.07 in both sets. In the gates,
   the share of civs whose final Gini is within 0.30-0.70 is not lower
   than `main`'s by more than 0.02.
6. **Revenue** per living civ-turn: template -3% to -10%, procedural -6%
   to +2%. **Treasury**: template -2% to -12%, procedural within +-10%.
7. **Fiscal crises**: defaults, debasements, fiscal-strain onsets and PSI
   crises within +-30% of `main` in both sets; template foreign issuance
   not more than 10% above `main`'s.
8. **Satisfaction** (all agents): 0 to +0.015 (less inequality); merchants'
   satisfaction within +-0.02.
9. **Occupations**: each occupation's share of agents within +-0.005
   (absolute); occupation switches per agent-turn not different by more
   than two standard errors of the paired difference.
10. **Migration and rebellion** per agent-turn: not different by more than
    two standard errors of the paired difference.
11. **Population** at the end, and polities alive, within +-5%.
12. **Domestic credit** (both arms with the switch): merchants lend less
    (-10% to -50%) and cities more; the foreign share of issuance rises by
    0.02 to 0.15; the Gini as in 5.
13. **Conservation**: every tick balanced in every checked run (template
    42-61 x 300 and procedural 42-61 x 200, default and with
    `--domestic-credit`: 80 runs), the credit ledger included; their final
    states byte-identical to unchecked runs.
14. **Identity**: the restore key against `main` (9-case matrix): 0
    differences. The default against `main`: the three `--agents off`
    cases identical, every hybrid case different.
15. **Gates**: template full (200 x 500) and procedural full (100 x 300)
    PASS strict, and the strict comparisons against fresh `main` full
    gates of `cb9fe70` (same oracle methods, nothing to rebaseline) show
    NO REGRESSION.
