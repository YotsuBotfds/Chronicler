# Domestic credit through real lenders (`--domestic-credit`, 2026-10)

Branch `feat/domestic-credit` from `main` `ac74e5a` (PR #62, community
anchoring). Code: `src/chronicler/domestic_credit.py` (behaviour),
`src/chronicler/domestic_credit_state.py` (persisted state), hooks in
`finance.py` (Phase 3b), `guilds.py` (a new threat), `agent_bridge.py`
(a region column), `main.py`, `live.py`, `run_checkpoint.py`,
`batch_manifest.py`, `scripts/m53b_run_validation.py`; native
`chronicler-agents/src/credit.rs` (merchant wealth), a satisfaction term in
`satisfaction.rs` / `tick.rs` and a region field in `region.rs` /
`ffi/mod.rs`. Probe: `scripts/domestic_credit_probe.py`. Tests:
`tests/test_domestic_credit.py` (guarded lane chunk `domestic-credit`),
`tests/test_domestic_credit_native.py`, Rust unit tests in `credit.rs` and
`satisfaction.rs`.

**Status: default off** (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`). With the
switch off every output is byte-identical to `main`
([identity](#5-switch-off-byte-identical-to-main)).

## 1. Why

With `--finance` (on by default since the 2026-10 all-on gate) a state short
of money borrows first at home, from `finance.DOMESTIC` (-1), "the
merchant/elite creditor class". That class is abstract
(`docs/integration/money-credit.md`, Lenders):

* it lends up to half the smoothed merchant wealth of the civ (the goods
  economy's tax base, by agent affinity) plus three turns of revenue times
  merchant faction influence, times domestic trust and the credit factors
  of techniques, great merchants' vows and chartered cities, less what it
  is already owed;
* the principal comes from nowhere: no agent, guild or city is poorer for
  lending;
* interest and repayments leave the treasury into the finance ledger only;
* a default's write-off is lost by nobody in particular; its domestic
  consequences (domestic trust halved, economy -3, merchant influence
  -0.05) fall on the realm as a whole.

money-credit.md's follow-ups list "credit merchant agents with domestic
interest through a bridge signal". This branch makes the actual holders of
wealth the lenders, and makes every unit of principal, interest, repayment
and loss land on them.

How much the abstract class lent from wealth that exists: in seed 42 (hybrid,
200 turns, main), at turn 20 the abstract capacity of Ashkari Nomads was 43,
of which 5.75 came from merchant wealth (EMA 11.5) and 37.5 from the
revenue-times-influence term; by turn 120 Kethani Empire's capacity was 232
against 229 of smoothed merchant wealth, 180 of merchant agents' wealth in
its regions, a civic purse of 38 and guild purses of 6. Early in a run most
domestic credit was lent by nobody.

## 2. Design

### 2.1 Who lends

For a borrowing civ, three kinds of lender in its own regions:

| lender | key | wealth it lends from |
| --- | --- | --- |
| the **merchants** of a region | region index | the merchant agents whose home is the region (where they stand, or for a merchant on a trip the region it set out from), read from the live native pool (`AgentSimulator.merchant_wealth_by_region`), plus what the books still owe them (`merchant_due`); only where at least one merchant lives |
| a **guild** (`guilds.py`) | index in `GuildState.guilds` | its purse (`Guild.wealth`), when its city's lord is the borrower |
| a **city** (`cities.py`) | `settlement_id` | its civic purse (`City.wealth`), when the city's lord is the borrower |

A lender's assets are its wealth plus its outstanding claims (on any
borrower). It offers

    offer = floor(share x (wealth + claims) - claims),   share = min(MAX_LEND_SHARE, LEND_SHARE x trust x factors)

where `trust` is the borrower's domestic trust and `factors` the product of
the existing credit factors (techniques' banking, great merchants'
`lend_to_crown` vows, chartered cities), the same factors that multiplied
the abstract capacity. With `LEND_SHARE` 0.5 and no claims this is main's
`DOMESTIC_WEALTH_SHARE`; with claims it is main's "less what it is already
owed". However deep credit runs, `share` stays at most 0.75: a lender
always keeps a quarter of its wealth (`offer <= share x wealth`). The
domestic capacity is the sum of the offers; a borrower excluded after a
default still gets a quarter of it (`EXCLUDED_DOMESTIC_SHARE`, unchanged).
The abstract revenue-times-influence part is gone: only real wealth lends.

The finance tick asks for what it asked before (`_borrow`'s gap); the loan
is split among the lenders pro rata to their offers, in whole units
(largest remainder, ties to the earlier lender: merchants by region index,
then guilds by index, then cities by settlement id), so no lender lends
more than it offered. Rate, term, the one line per borrower and lender and
`MIN_LOAN` are finance's. A credit line (`CreditLine`, keyed by the
`finance.Loan`'s `loan_id`) records each funder's claim (`Funder`: kind,
key, principal); the claims always add up to the loan's principal.

### 2.2 Cash flows

| flow | borrower (treasury, `keep`) | funders |
| --- | --- | --- |
| a loan | + principal | each pays its part from its wealth; its claim rises by it |
| interest paid | - interest | split pro rata to the claims and paid to them |
| principal paid (amortization or prepayment) | - principal | split pro rata to the claims, paid to them; the claims fall by it |
| unpaid interest | (capitalized into the loan) | split pro rata into the claims |
| default haircut | (debt written down) | the claims are written down pro rata: the losses land on them |
| the borrower falls | (lines lost) | every claim is lost |
| a lender falls (a city falls, a guild dissolves) | the borrower owes that claim no more | the claim lapses (`debt_written_off` event) |

Guild and city purses change at once (they are Python state, stored to four
decimals as their modules store them). Merchant flows are added to the
region's `merchant_due` and, at the end of the fiscal tick, sent to the
native pool: `AgentSimulator.apply_merchant_transfers(region_ids, amounts)`
takes a debit from the region's merchants pro rata to their wealth (never
below zero) and gives a credit pro rata to their wealth (equal shares when
none holds any), never above `MAX_WEALTH` (100), the rest pro rata to the
room left; it returns, per region, the change actually made (the sum of
every agent's new minus old wealth, in f64). Whatever was not applied (no
merchants there now, every one at the ceiling) stays due and is sent again
next turn; the merchants of a region whose due is positive can lend it.

Because a debit never exceeds what was offered (at most three quarters of
the merchants' live wealth), a debit is always applied in full; only
credits wait.

### 2.3 The bridge signal

The signal is the per-region due, persisted on `DomesticCreditState`, so
nothing transient crosses a turn: the Phase 3b tick builds the transfer
batch from it, calls the native method once, and lowers the due by exactly
what the pool reports applied. The native side keeps no state between
calls (a call moves wealth once and reports it). Tests: a due is sent once
a tick and cleared when applied; a credit to a region without merchants is
carried and applied when they return; a tick with nothing due sends
nothing; an empty native call changes nothing; a debit and the credit back
are exact (`test_merchant_due_is_sent_once_and_carried_when_it_cannot_be_applied`,
`test_merchant_wealth_is_read_and_moved_exactly_once`, the Rust
`a_call_moves_wealth_once_and_keeps_no_state`).

The merchants' grievance travels as an optional region-batch column,
`creditor_grievance` (f32, 0..1), recomputed from persisted state for
every batch like `city_pull` (not consumed; it decays once a turn in the
fiscal tick). Without the column Rust reads 0.

### 2.4 Consequences

A default keeps finance's domestic consequences (domestic trust halved,
economy -3 as a `signal`, merchant influence -0.05) and adds, from who
lost:

* **Merchants.** The losing region's merchants gain grievance
  `min(0.5, loss / assets)` (assets before the loss), capped at 1, decaying
  5% a turn (half-life about 13.5 turns), forgotten below 0.001. In the
  native satisfaction it costs a merchant there up to
  `CREDITOR_GRIEVANCE_WEIGHT` = 0.10 at full grievance, inside the social
  penalty cap (`PENALTY_CAP` 0.40, with persecution and the cultural and
  religious terms; the memory term takes what is left), so it lowers
  merchants' loyalty, raises their migration and rebellion the way any
  lost satisfaction does, and never stacks past the cap. Other occupations
  ignore it.
* **Cities.** A losing city's grievance rises `min(0.3, loss / assets)`
  (its existing grievance: capped at 1, decaying 4% a turn, added to its
  unrest target, so a heavy loss can bring the urban revolt closer).
* **Guilds and cities that lost at least a tenth of their assets** record
  the repudiation in their history (kind `repudiated`, citing the
  `state_default`); for a guild it is a threat to its privileges (threat
  `default`, appended to `guilds_state.THREAT_NAMES`), which may raise a
  guild movement "after the crown repudiated its loans" exactly as the
  other threats do (chance 0.5, the existing guards).
* **Wealth.** Interest no longer vanishes: it is paid to the lenders. The
  merchants of the regions that lend most accumulate it.

No action-weight bucket is added or changed; the finance bucket and the
global cap are untouched.

### 2.5 Provenance and narration

`loan_taken` of a domestic loan names its funders, largest first ("Thornwall
Confederacy borrows 39 from the merchants of Thornwood (17), the merchants
of Verdant Plains (14), the city of Verdant Plains Settlement 1 (6) and
others at 4.0%") and carries the main lending region in `region`; its
actors stay the borrower alone (great merchants' `lend_to_crown` agendas
complete on a domestic `loan_taken` whose actors are the civ). A city or
guild that funded a material loan notes it in its history (`loan`, citing
the event). `state_default` names the domestic losers in the same way,
and the repudiated cities and guilds cite it. A fallen borrower's
`debt_written_off` names the lenders that lost; a lapsed claim's names the
fallen lender and cites its fall.

### 2.6 Contracts

* **Determinism.** No random draws. Fixed orders (regions, guilds, cities
  by index); integer splits; the native transfer iterates slots in order.
* **Accumulator.** Treasury changes are finance's `keep` entries
  (unchanged code). The economy and stability consequences of a default
  are finance's `signal`s. The merchants' grievance acts in the native
  satisfaction, the cities' grievance in the city tick.
* **Enums and tuples.** None reordered. Appended: guild threat `default`;
  history kinds `loan`, `repudiated` for guilds and cities. The native
  `RegionState` gains `creditor_grievance` at the end (persisted in the
  exact checkpoint, so the native state schema fingerprint changes).
* **Transient signals.** None crosses a turn (2.3).
* **Identity.** Regions by index, civilizations by index, guilds by index,
  cities by `settlement_id`. Nothing keys on names.

### 2.7 Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--domestic-credit` / `--no-domestic-credit` (`None` = default or saved) |
| World field | `WorldState.domestic_credit: DomesticCreditState \| None` (presence = on; omitted while `None`) |
| Default | off for new worlds (CLI, batch, live); resumed, forked and supplied worlds keep their setting |
| Requirements | an explicit `--domestic-credit` needs `--finance` and an agent pool (`--agents hybrid`, `shadow` or `demographics-only`); a saved setting under `--agents off` keeps its books (guilds and cities lend if the world has them; merchants, without a pool, lend nothing and what is owed to them stays due) |
| Gate runner | `scripts/m53b_run_validation.py --domestic-credit` forwards the flag to every agent-mode run (not the aggregate determinism pair) and records it in `run_manifest.json` |
| Batch manifest | `domestic_credit` in `SIMULATION_ARG_KEYS` |
| Checkpoints | `feature_flags()["domestic_credit"]`; a resume adopts the saved value and refuses a different one |
| Snapshot | `TurnSnapshot.finance["domestic_credit"]` (claims by kind of lender, by borrower, merchants' grievance by region, the due); absent without the switch, so the transport contract is unchanged |
| Analytics | `analytics.generate_report` adds a `domestic_credit` section when bundles carry it |

Lines lent before the switch was turned on (a resumed world) belong to the
abstract class (kind `legacy`): they are serviced as before, their
receipts leave into the ledger, and the claims still add up.

## 3. Parameters ([CALIBRATE])

| Name | Value | Meaning | Note |
| --- | ---: | --- | --- |
| `LEND_SHARE` | 0.5 | share of assets (wealth + claims) lent at full trust, less claims | = finance's `DOMESTIC_WEALTH_SHARE`; [CALIBRATE] against the share of merchant wealth historical lenders tied up in public debt |
| `MAX_LEND_SHARE` | 0.75 | ceiling whatever the credit factors (a quarter kept) | [CALIBRATE] |
| `MIN_FUNDING` | 1 | a smaller offer lends nothing | whole units |
| `GRIEVANCE_PER_LOSS` | 1.0 | merchants' grievance per unit of loss over assets | [CALIBRATE] |
| `GRIEVANCE_STEP` | 0.5 | at most per default | [CALIBRATE] |
| `GRIEVANCE_DECAY` | 0.95 | per turn | [CALIBRATE]; cities use their own 0.96 |
| `GRIEVANCE_FLOOR` | 0.001 | forgotten below | |
| `CITY_GRIEVANCE_STEP` | 0.3 | a city's grievance per default, at most | [CALIBRATE]; a guild levy adds 0.1, a sack 0.3 |
| `THREAT_SHARE` | 0.1 | loss share of assets that is a guild threat / history entry | [CALIBRATE] |
| `CREDITOR_GRIEVANCE_WEIGHT` (Rust) | 0.10 | merchant satisfaction lost at full grievance | [CALIBRATE]; persecution's weight is 0.09 per unit of intensity |
| `EVENT_LENDERS` | 3 | lenders named in an event | |

## 4. Conservation: the credit ledger

`CHRONICLER_CHECK_RESOURCES=1` (the production ledger's switch) checks every
fiscal tick (`domestic_credit._Ledger`, `AssertionError("credit ledger does
not balance ...")`):

* every domestic loan has a line whose claims add up to its principal, in
  whole units, and a settled line holds nothing;
* per kind of lender: claims after = claims before + lent + capitalized -
  repaid - written off - lost - lapsed, exactly;
* finance's own counters agree: domestic principal issued and domestic
  interest this tick equal what the lenders lent and received, and the
  interest, principal, capitalization and haircut finance passed are
  exactly what was split among the funders;
* every guild and city purse moved by exactly what it lent and was paid;
  every region's merchant due by its merchants' flows; no region's
  merchants were asked for more than they hold;
* the native pool's merchant wealth (read before and after the call)
  changed by exactly what it reported applied, region by region;
* cumulatively, the merchants' flows (interest + repaid - lent) equal what
  reached their wealth plus what is still due.

Results: [pending].

## 5. Switch off: byte-identical to `main`

[pending]

## 6. Checkpoints with the switch on

[pending]

## 7. Pre-registration

Written before any gate or paired comparison ran; the only switch-on run
seen was the seed-42 smoke run (200 turns), in which domestic issuance was
542 against main's 371 (one seed, chaotic divergence). Expected directions,
switch on against main (or the switch off, byte-identical), for the paired
probe (template seeds 42-61 x 300 turns, procedural 32 x 10 seeds 42-61 x
200 turns) and the full gates (template 200 x 500, procedural 100 x 300):

1. **Early domestic credit falls.** Real lenders start poor (an agent
   starts with 0.5 wealth): domestic loans in the first 30 turns fall by
   more than a third. Over the whole run domestic issuance moves less
   (merchant wealth grows; claims stay in the assets): within +-40%, no
   direction predicted.
2. **The foreign share of issuance rises** (foreign / (domestic + foreign)
   issued).
3. **Merchant wealth rises.** Interest is paid to merchants instead of
   vanishing, and principal on loan escapes the agents' 2% wealth decay:
   the mean merchant wealth over sampled turns rises by 5% or more.
4. **Merchant wealth concentrates.** Credits go pro rata to wealth and to
   the regions that lent: the Gini of merchant agents' wealth and its Gini
   over regions rise (any size).
5. **Defaults and fiscal crises move little.** Defaults, debasements,
   fiscal-strain onsets and PSI crises within +-30%, direction not
   predicted.
6. **Agents barely notice.** Mean merchant satisfaction within +-0.01;
   all-agent satisfaction, migration and rebellion within the run-to-run
   spread of the gate comparisons (satisfaction +-0.005, migration and
   rebellion rates +-5% relative).
7. **Gates.** Every required oracle passes in both full gates, and the
   exploratory comparisons against main's full reports show no newly
   failing required gate.

## 8. What it does (paired worlds)

[pending]

## 9. Gates with the switch on

[pending]

## 10. Worked examples

[pending]

## 11. Decisions

[pending]
