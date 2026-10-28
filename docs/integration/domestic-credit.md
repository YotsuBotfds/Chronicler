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

Runs checked with `CHRONICLER_CHECK_RESOURCES=1`, every tick balanced (the
production ledger's own checks ran alongside): 20 template worlds (seeds
42-61 x 300 turns) and 20 procedural 32 x 10 worlds (seeds 42-61 x 200
turns), hybrid, switch on; their final states are byte-identical to the
unchecked runs of the same seeds (40 of 40), so the checks only read. The
native test (60 turns, twice) and the guarded-lane tests run with the
checks too, and a book with one claim changed by a unit fails them
(`test_the_ledger_balances_over_a_run_and_catches_a_broken_book`).

A first checked batch stopped three template worlds on the overdraft check
("merchants asked for 1.9e-06 holding -0.0", turns 86, 207 and 209): a debit
residual of f32 rounding, carried in the due of a region whose merchants
had since left, was counted as a request this tick. The check now applies
to regions that lent this tick and allows the carried residual (`2a08828`;
the check is not run without the environment variable, so no simulation
output changed).

Over those runs the books close as designed: in the procedural worlds the
merchants lent 3,535 a run and were paid 2,299 of interest and 2,750 of
principal; what reached their wealth plus what is still due equals those
flows to within 1e-6 at every turn, with 10.7 still due at the end (credits
waiting for merchants to return to a region).

Environment for every run in this note: Linux, Python 3.13.17,
`PYTHONHASHSEED=0`, one virtualenv per tree with a release extension built
fresh (`maturin develop --release --locked`, its own `CARGO_TARGET_DIR`;
compiled `chronicler_agents.chronicler_agents`, `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` real classes). `main` `ac74e5a`
from an exported tree: extension SHA-256 `8497d374...3d50`. Branch frozen
tree `2a08828` (identity, checkpoints, checked runs, gates; `c46e004` for
the paired probe, which differs only in the ledger check):
`3da1ee1f...dad0b`.

## 5. Switch off: byte-identical to `main`

`scripts/turn_speed_identity.py`, the 9-case matrix (`--agents off` 300
turns seeds 42 and 7, hybrid 200 turns seeds 42, 7 and 1234 with and
without sidecars, procedural 48 x 10 hybrid and off, the 22k and 52k agent
worlds), main's exported tree and extension against the frozen branch tree
and its extension:

| branch run | files compared | differences |
| --- | ---: | ---: |
| no flag (default off) | 399 | 0 |
| explicit `--no-domestic-credit` | 399 | 0 |

The same result on `c46e004`, before the ledger-check change. With the
switch off no domestic-credit code runs (`test_domestic_credit_never_runs_while_off`),
the region batch carries no `creditor_grievance` column (Rust reads 0 and
adds no penalty: the term is skipped at grievance 0), the world, bundle and
checkpoint omit the state (`tests/test_serialization_dormant_fields.py`),
and the finance snapshot has no `domestic_credit` key. The native state
schema gains `creditor_grievance`, so a native checkpoint written by `main`
is refused by this build with a clear error (as with every native schema
change).

## 6. Checkpoints with the switch on

`scripts/checkpoint_identity.py` with `--cli-arg=--domestic-credit`, the
frozen tree: one straight run with a checkpoint at every resume turn, one
without checkpoints, and a resume from every checkpoint; every file each
resumed run writes compared byte for byte with the straight run.

| case | turns | resume points | files compared | differences |
| --- | ---: | ---: | ---: | ---: |
| `hybrid_s42` (template, sidecars) | 60 | 59 (every turn) | 1,780 | 0 |
| `proc32_hybrid_s11` (procedural 32 x 8, sidecars) | 40 | 39 (every turn) | 1,176 | 0 |
| `hybrid_s42_long` (template, sidecars; two defaults and a lapse) | 200 | 19 (the spread) | 1,616 | 0 |
| `shadow_s42` | 40 | 39 (every turn) | 429 | 0 |
| `demographics_s42` | 40 | 39 (every turn) | 351 | 0 |

Every case lends and is paid; `hybrid_s42_long`, `proc32_hybrid_s11` and
`demographics_s42` also default on their lenders within their turns; the
straight runs equal the runs without checkpoints. The native
tests resume a 40-turn hybrid run at turns 15 and 30 the same way.

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

`scripts/domestic_credit_probe.py`, the frozen tree (`c46e004`; later
commits change the ledger check and documentation only), hybrid, paired by
seed with the switch off (byte-identical to `main`) and on. Template:
seeds 42-61 x 300 turns; procedural 32 regions x 10 civs: seeds 42-61 x
200 turns. Merchant measures are read from the native pool every tenth turn
after the agent tick and averaged over the run ("mean") or taken at the
last sample ("end"); the rest is from the bundles and final states. Means
per run; SE of the paired difference.

| measure | template off | on | on - off (SE) | procedural off | on | on - off (SE) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| domestic loans before turn 30 | 3.8 | 1.4 | **-2.4** (0.32) | 11.45 | 5.95 | **-5.5** (0.69) |
| domestic loan events | 5.3 | 3.75 | -1.55 (0.46) | 25.1 | 22.6 | -2.5 (2.0) |
| domestic issued | 317 | 507 | **+190** (91) | 2,666 | 4,383 | **+1,717** (528) |
| foreign issued | 263 | 400 | +137 (84) | 4,435 | 3,437 | **-998** (479) |
| foreign share of issuance | 0.42 | 0.55 | +0.13 (0.07) | 0.62 | 0.44 | **-0.18** (0.03) |
| domestic interest paid | 125 | 313 | +188 (90) | 1,330 | 2,820 | **+1,490** (454) |
| debt / revenue, mean over civ-turns | 0.19 | 0.27 | +0.08 (0.04) | 0.88 | 0.85 | -0.04 (0.09) |
| defaults | 0.65 | 0.85 | +0.20 (0.17) | 7.7 | 5.55 | **-2.15** (0.90) |
| debasements | 0.85 | 1.00 | +0.15 (0.22) | 6.1 | 4.45 | -1.65 (0.87) |
| fiscal-strain onsets | 3.8 | 4.95 | +1.15 (1.48) | 20.1 | 17.1 | -3.0 (1.7) |
| PSI crises (of them fiscal distress) | 0.85 (0.10) | 1.05 (0.15) | +0.20 (0.25) | 4.35 (1.8) | 4.95 (1.6) | +0.60 (0.64) |
| revolts | 1.45 | 1.15 | -0.30 (0.60) | 8.75 | 7.65 | -1.1 (1.2) |
| merchant wealth, mean | 334 | 379 | **+45 (+14%)** (19) | 886 | 1,043 | **+157 (+18%)** (38) |
| merchant wealth, end | 425 | 473 | +48 (50) | 1,297 | 1,621 | +324 (111) |
| merchants (agents), mean | 25.3 | 26.3 | +1.0 (0.8) | 78.8 | 80.0 | +1.2 (1.4) |
| merchant satisfaction, mean | 0.424 | 0.415 | -0.008 (0.006) | 0.376 | 0.376 | +0.000 (0.005) |
| Gini of merchants' wealth, mean | 0.508 | 0.511 | +0.003 (0.005) | 0.488 | 0.487 | -0.001 (0.004) |
| Gini of merchants' wealth within civs, mean | 0.439 | 0.446 | +0.007 (0.007) | 0.409 | 0.418 | **+0.009** (0.003) |
| Gini of all agents' wealth, mean | 0.596 | 0.605 | **+0.009** (0.004) | 0.570 | 0.572 | +0.002 (0.002) |
| Gini of merchant wealth over regions, mean / end | 0.384 / 0.371 | 0.390 / 0.400 | +0.006 / +0.029 | 0.462 / 0.438 | 0.452 / 0.479 | -0.010 / +0.042 (0.021) |
| richest region's share of merchant wealth, end | 0.43 | 0.46 | +0.03 (0.04) | 0.15 | 0.17 | +0.02 (0.01) |
| guild movements raised by a default | 0 | 0.05 | | 0 | 0.40 | |
| polities alive at the end | 3.0 | 2.95 | -0.05 (0.09) | 8.7 | 8.95 | +0.25 (0.30) |

At the gates' horizons (added after the pre-registration, same seeds and
measures; template 500 turns, procedural 300 turns; the frozen tree
`2a08828`):

| measure | template off | on | on - off (SE) | procedural off | on | on - off (SE) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| domestic loans before turn 30 | 3.8 | 1.4 | **-2.4** (0.32) | 11.45 | 5.95 | **-5.5** (0.69) |
| domestic issued | 723 | 664 | -59 (199) | 4,752 | 9,604 | **+4,852** (1,170) |
| foreign issued | 441 | 441 | +0 (141) | 8,193 | 5,663 | **-2,530** (1,010) |
| foreign share of issuance | 0.37 | 0.53 | **+0.17** (0.07) | 0.63 | 0.38 | **-0.25** (0.04) |
| domestic interest paid | 311 | 372 | +61 (88) | 2,605 | 7,103 | **+4,498** (1,150) |
| debt / revenue, mean | 0.18 | 0.19 | +0.02 (0.03) | 0.94 | 1.00 | +0.06 (0.11) |
| defaults | 0.80 | 0.95 | +0.15 (0.23) | 10.2 | 7.9 | -2.3 (1.3) |
| debasements | 0.85 | 1.00 | +0.15 (0.22) | 6.65 | 5.5 | -1.15 (1.06) |
| fiscal-strain onsets | 6.05 | 6.3 | +0.25 (2.7) | 25.7 | 25.3 | -0.4 (3.0) |
| PSI crises (of them fiscal distress) | 1.5 (0.15) | 1.55 (0.15) | +0.05 (0.25) | 7.35 (2.75) | 8.05 (2.25) | +0.7 (0.78) |
| revolts | 2.95 | 1.9 | -1.05 (0.92) | 16.0 | 16.0 | 0.0 (2.1) |
| merchant wealth, mean | 373 | 392 | +19 (+5%) (21) | 997 | 1,255 | **+258 (+26%)** (57) |
| merchant satisfaction, mean | 0.441 | 0.431 | **-0.011** (0.005) | 0.383 | 0.378 | -0.005 (0.007) |
| Gini of merchants' wealth, mean | 0.531 | 0.533 | +0.002 (0.006) | 0.516 | 0.512 | -0.003 (0.003) |
| Gini of merchants' wealth within civs, mean | 0.472 | 0.471 | -0.000 (0.008) | 0.439 | 0.446 | **+0.007** (0.003) |
| Gini of all agents' wealth, mean | 0.621 | 0.629 | +0.008 (0.006) | 0.597 | 0.604 | **+0.007** (0.003) |
| Gini of merchant wealth over regions, mean | 0.376 | 0.388 | +0.012 (0.007) | 0.468 | 0.458 | -0.010 (0.005) |
| polities alive at the end | 2.9 | 2.8 | -0.1 (0.12) | 7.95 | 8.6 | **+0.65** (0.26) |
| population at the end | 185 | 186 | +1 (8) | 600 | 551 | -50 (27) |

Who lent (switch on, per run): template merchants 441, cities 62, guilds
3.7; procedural merchants 3,535, cities 804, guilds 45 (merchants 81-87%,
cities 12-18%, guilds under 1%). Of what they lent, procedural lenders
received 2,820 of interest, were repaid 3,371 and lost 492 in defaults, 4
with fallen borrowers and 10 in lapses; 5.0 defaults a run hit lenders and
merchants of some region held a grievance in 632 region-turns a run.

**How credit changes.** Early, domestic credit falls by half or more in
every arm, as real lenders start poor (an agent starts with 0.5 wealth; the
abstract class lent mostly its revenue-times-influence term). Later the
merchants are the richer for it: interest no longer vanishes, and principal
on loan escapes the agents' 2% wealth decay, so merchant wealth is higher
from about turn 50 on (it is 12% lower around turn 30, when the first loans
take their cash): +14% and +5% over 300 and 500 template turns, +18% and
+26% over 200 and 300 procedural turns. Richer lenders offer more:
procedural domestic issuance rises by 64% (200 turns) and doubles (300
turns) and replaces foreign credit (foreign issuance -22% and -31%, its
share 0.62 -> 0.44 and 0.63 -> 0.38), with defaults and debasements about a
quarter lower. In template worlds (four civs, 25 merchants) the effect on
issuance is horizon-dependent (+60% at 300 turns, -8% at 500, both within
the chaotic spread of single worlds) while the foreign share rises (+0.13,
+0.17): the four civs borrow abroad what their few merchants cannot lend.
Rich merchants also fund the war chest: a belligerent borrows to keep its
full reserve target, and where the abstract class was capped by its formula
the merchants of a trading region now lend 100 and more at once (template
seed 53: Dorrathi Clans borrows 130 and then 109 from the merchants of
Sapphire Coast within five turns of a war). Fiscal-strain onsets, PSI
crises and revolts do not move beyond their spread in any arm.

**A debt treadmill in a few worlds.** Domestic lenders' assets now grow
with the interest they are paid, so their offers do not run out as a
state's debt rises: a state at finance's debt ceiling (ten turns of
revenue) can roll its debt over indefinitely, borrowing back each turn
the amortization it pays and paying the interest from revenue, where the
abstract class's capacity (its formula less what it was owed) ran out,
the state fell into arrears and defaulted. Template seed 101 (500 turns,
the gate world): after a war at turn 170 Thornwall Confederacy owes
700-1,340 for the last 320 turns (9-10 turns of its revenue), pays 75-92
of interest a turn on a revenue of 110-140, holds no treasury, spends
nothing on its court and never defaults; its cities hold most of the
claims (1,062 of 1,225 at turn 476) and their purses grow from tens to
2,163 (Amber Valley Settlement 1). On `main` the same Thornwall is
debt-free from turn 100 and hoards 2,000. Such worlds are few: city
interest above 1,000 in 4 of the template gate's 200 worlds; worlds
whose debt averages more than a turn of revenue are as common with the
switch as without (procedural 300 turns: 8 against 9 of 20; template
gate: 8 of 200). Purses, unlike agent wealth (capped at 100 an agent),
have no ceiling, so it is cities and guilds that grow without bound. Not
changed here; it is decision 11.2 (3).

**How wealth moves.** Merchant wealth grows; its distribution moves little.
The Gini of all agents' wealth rises by 0.007-0.009 (the merchants pulling
ahead of the other occupations; 2.2 SE template 300, 2.5 SE procedural 300,
smaller elsewhere), the Gini of merchants' wealth within each civ by 0.007-0.009
in procedural worlds (2.4-2.6 SE). The world Gini of merchants' wealth does
not move. Over regions, concentration does not change on average (region
Gini +0.012 template 500, -0.010 procedural); the richest region's share and
the region Gini at single end turns move both ways. Merchants' mean
satisfaction moves -0.011 (template 500, 2 SE), -0.008, -0.005 and 0.000;
single late turns of the template probe read -0.03 to -0.07 (turns
270-300), within the turn-to-turn swing of +-0.03 the series shows
throughout. More procedural polities survive 300 turns (8.6 against 7.95,
2.5 SE) and their worlds end with 8% fewer people (1.8 SE).

## 9. Gates with the switch on

`scripts/m53b_run_validation.py --profile full --require-strict-regression
--exploratory-comparison --domestic-credit`, the frozen tree `2a08828` and
its extension, three workers, one full gate on the machine at a time. The
comparisons are exploratory (the simulation configuration differs), so NO
REGRESSION means no required gate newly fails, not that the distributions
match.

**Baselines.** Template: a fresh full gate of `main` `ac74e5a` (fork design
2) run on this machine by the parallel session (`spec-communities`
`main-t-full`: package digest `e4039e6d...9c9c` and extension `8497d374...3d50`,
the same as this branch's `main` tree; PASS strict, its reports copied to
`reports/baselines/`). It replaces the re-scored design-1 report suggested
for an exploratory comparison, so needs method 8 and cohort method 5 score
both sides. Procedural: `main` `ac74e5a` at design 2, community-anchoring's
`p-full-off2`.

### Template full (200 seeds x 500 turns)

**PASS strict; EXPLORATORY, NO REGRESSION** against main (3,220 s). Every
required oracle passes (arcs, artifacts strict, cohort, community, era,
needs, regression strict), as on main.

| | main `ac74e5a` | `--domestic-credit` | change |
| --- | ---: | ---: | ---: |
| satisfaction mean | 0.6212 | 0.6173 | -0.0038 |
| latest satisfaction mean (last 60 turns) | 0.6330 | 0.6267 | -0.0063 |
| migration per agent-turn | 0.06340 | 0.06313 | -0.4% |
| rebellion per agent-turn | 0.03295 | 0.03555 | +7.9% |
| final Gini within 0.30-0.70 (share of civs) | 0.852 | 0.869 | +0.017 |
| occupation violations | 0.0012 | 0.0013 | |
| final living population (mean per world) | 185.3 | 181.8 | -1.9% |
| extinct worlds | 0 | 0 | |

Informational (causal evidence, not yet required): the needs ablation's
safety pairing reads 1.071 [0.877, 1.266] (FAIL: its interval reaches 1)
against main's 1.230 [1.035, 1.424]; the other pairings match main's
(autonomy 1.372 against 1.469, social 1.117 / 1.121, purpose 1.277 / 1.276,
material 1.113 / 1.144, spiritual 1.210 / 1.197). The safety pairing is the
low-power one in template worlds (power 0.66, community-anchoring.md); the
two estimates differ by about one standard error of their difference and
domestic credit does not touch the safety need, so this is the oracle's
sampling, not the feature. The kin-roots cohort ablation fails on both
sides (0.9915 against 0.9884), as on main.

Rebellion per agent-turn reads +7.9% and the latest satisfaction -0.006,
beyond the pre-registered +-5% and +-0.005. The two gates ran the same
seeds, but single worlds diverge chaotically, so a paired check was run
after the gate: 40 template seeds (42-81) x 500 turns, off and on, the
rates counted as the regression oracle counts them (agent events over the
mean sampled agents times turns; `rates.py` in the run directory). Off
reads 0.0611 migration and 0.0311 rebellion, close to main's gate values.

| per agent-turn (40 paired worlds, 500 turns) | off | on | on - off (SE) |
| --- | ---: | ---: | ---: |
| migration | 0.06145 | 0.06129 | -0.3% (2.0%) |
| rebellion | 0.03112 | 0.02984 | -4.1% (11.5%) |
| occupation switches | 0.04749 | 0.04800 | +1.1% (1.7%) |
| merchant satisfaction (mean of samples) | 0.4416 | 0.4330 | -0.0086 (0.0039) |
| Gini of all agents' wealth (mean of samples) | 0.6186 | 0.6257 | +0.0071 (0.0031) |

Rebellion is concentrated in a minority of worlds, so its paired standard
error is 11% of its level: the gate's +7.9% (about 1.6 of its own standard
errors) is not an effect the switch has, and the paired worlds read -4.1%.
What the switch does to agents is small and shows in the paired worlds:
merchants' satisfaction about -0.009 (2.2 SE) and the all-agent wealth Gini
+0.007 (2.3 SE), as the shorter probes found.

### Procedural full (100 seeds x 300 turns, 32 regions x 10 civs)

PROCEDURAL_RESULTS

## 10. Worked examples

Template seed 42, hybrid, 200 turns, `--domestic-credit` (the frozen
tree's checkpoint-identity run `hybrid_s42_long`, identical to the smoke
run). Every arrow is a recorded `causes` link, read from the bundle; the
claims and the grievance are the snapshot's `finance["domestic_credit"]`.

**Thornwall Confederacy borrows from its merchants and cities, defaults on
them, and a guild rises.** Kethani Empire goes to war with Thornwall seeking
tribute (t0). Thornwall "borrows 14 from the merchants of Verdant Plains
(9) and the merchants of Thornwood (5) at 4.3%" (t11, citing the war; the
event's region is Verdant Plains, its capital and main lender), and "39
from the merchants of Thornwood (17), the merchants of Verdant Plains (14),
the city of Verdant Plains Settlement 1 (6) and others at 4.0%" (t33; both
cities note the loan in their histories; the fiscal strain of t35 cites it).
By turn 50 it owes 166 at home (merchants 127, cities 39), by turn 72 291
(merchants 155, cities 50, a guild 2) and 80 abroad: Kethani lent 40 at
9.8% in the famine and plague of t60. It defaults (t73), "repudiating 154
owed to Kethani Empire, the merchants of Verdant Plains (54), the city of
Verdant Plains Settlement 1 (16), the merchants of Iron Peaks (14) and
others" (citing the t33 and t63 loans, the plague and the famine of t70).
Its home claims are halved (merchants 84, cities 27). The merchants of
Verdant Plains hold a grievance of 0.24; three cities and two merchant
guilds record the repudiation, and the same turn "In Verdant Plains
Settlement 1, the Merchant Guild of Verdant Plains Settlement 1 takes up
its cause after the crown repudiated its loans" (the movement cites the
default). Thornwood Settlement 1 is abandoned (t75): "With the city of
Thornwood Settlement 1 gone, the 11 Thornwall Confederacy owed it lapses"
(t76, citing the city's fall and the loan). A second default (t81, the
repeat haircut of 80%: 118 repudiated) leaves 17 owed at home and raises
the merchants' grievance to 0.42; two of Thornwall's great merchants vow to
lend to the crown after the defaults (t77, t81). Thornwall is debt-free by
turn 100; the grievance has decayed to 0.17 by then and 0.06 by turn 120.

    t0 war_declared (tribute) -> t11 loan_taken (merchants of Verdant Plains, Thornwood)
    t33 loan_taken (merchants, Verdant Plains Settlement 1) -> t35 fiscal_strain
    t33, t63 loan_taken; t70 plague, famine -> t73 state_default -> t73 movement_founded (merchant guild)
    t75 city_fell (Thornwood Settlement 1), t33 loan_taken -> t76 debt_written_off (lapse)

**A war chest from a trading region** (template seed 53, 300 turns, the
probe's run). Dorrathi Clans' merchants of Sapphire Coast lend most of a
130 advance at t226 and 108 of 109 at t231, while Vrashni Dominion's
merchants of Sunfire Steppe and Amber Valley fund 110 at t184 and t246: in
this world 5.9 times as much is lent at home as with the abstract class,
nearly all of it in the last 120 turns, when the trading regions' merchants
had grown rich on earlier interest.

## 11. Decisions

### 11.1 Made here

* **Lenders are collective per region, not per agent.** A region's
  merchants hold one claim and are paid pro rata to their wealth when the
  money comes back. Agents die, migrate, inherit and change occupation; a
  per-agent claim would need a native column, a persisted claim ledger and
  rules for each of those. The cost: a merchant who lent and left is not
  repaid (the region's merchants are), and wealthier merchants are paid
  more. Credits that find no merchant wait in the due rather than being
  given to someone else.
* **The abstract revenue-times-influence term is gone.** Only real wealth
  lends; early domestic credit halves (8). Keeping it would leave domestic
  credit partly lent by nobody.
* **Fallen lenders' claims lapse**, as debts to a fallen foreign lender
  already do; claims of a fallen borrower are lost to the lenders.
* **Finance's domestic-default consequences are kept** (trust, economy,
  merchant influence) and the new ones are added from who lost; nothing
  else of finance changes (rates, terms, ceilings, foreign lending).
* **No action-weight bucket.** Creditors' leverage over the crown acts
  through the existing satisfaction, city and guild channels.

### 11.2 Default and promotion

The switch stays **off**. It changes fiscal dynamics materially: early
domestic credit halves, merchant wealth grows 5-26%, procedural worlds
replace a third of their foreign credit with domestic credit and default a
quarter less, and rich merchants finance war chests of 100 and more. Before
it is promoted:

1. Both full gates with the switch on should pass strict with no newly
   failing required gate against main reports of the same fork design
   (9 records the exploratory comparisons of this branch).
2. A decision on early-game credit: whether wealthy agents other than
   merchants (landholders, temples) should lend, or a capped abstract
   lender stay for the first turns, so that young states can borrow as
   before.
3. A decision on war finance and rollover (the treadmill of 8): whether
   a share of a region's merchant wealth should be off limits to a war
   chest; whether lenders should refuse new money to a borrower whose
   debt service takes more than a set share of its revenue (or rates
   rise with the share of the lenders' assets already lent), so that a
   state at the ceiling must deleverage or default as it did against the
   abstract class; and whether a city's or guild's purse should have a
   ceiling as agent wealth does.
4. The merchant tax (`economy.TAX_RATE` x merchant wealth) is not debited
   from the agents; with richer merchants it creates more revenue. Whether
   it should take from merchant wealth is a separate correction.
5. The viewer should show who holds a realm's debt (the finance snapshot
   carries it) and narration could tell creditor grievance.

### 11.3 Follow-ups

* Per-agent claims (native column) if lenders' identity matters for
  narration or migration.
* Calibrate `LEND_SHARE`, the grievance steps and
  `CREDITOR_GRIEVANCE_WEIGHT` against historical lending to states (the
  share of merchant capital tied up in public debt).
* A guild or city that lost heavily could refuse to lend for a while
  (today only the realm's domestic trust records it).

## 12. Tests and lanes

`tests/test_domestic_credit.py` (26 tests, guarded-lane chunk
`domestic-credit`): the integer split; who lends and the quarter kept; that
merchants lend only where merchants live; a loan funded pro rata from the
lenders' wealth, named in its event and noted by its city and guild;
interest and principal paid to the funders; unpaid interest capitalized
into the claims; prepayment; a default landing on the lenders with
grievance, the repudiation in the histories and the guild threat, with
finance's domestic consequences kept; grievance decaying and reaching the
region batch (absent when off); a fallen borrower's lines lost and a
fallen city's claim lapsing; the merchant due sent once a tick, carried
when it cannot be applied and applied when merchants return; the ledger
over a run and a broken book caught; a carried rounding residual not taken
for an overdraft; finance's books with the switch; legacy lines; no
domestic-credit code while off; save/load resume identity with outstanding
lines; the switch, CLI, manifest, checkpoint flags, requirements, the
new-world default and a saved setting kept; live; the gate runner's
forwarding (not to aggregate determinism runs); the snapshot summary and
metrics. A stand-in simulator implements the two native calls with
`credit.rs`'s rule.

`tests/test_domestic_credit_native.py` (4 tests, real extension): the
merchant wealth calls read and move wealth exactly once, refuse malformed
input and take nothing where no merchants live; the grievance column costs
merchants satisfaction and refuses values outside 0..1; a 60-turn hybrid
run with the switch and `CHRONICLER_CHECK_RESOURCES=1` lends, balances and
is deterministic; checkpoint resumes at turns 15 and 30 reproduce every
file. Rust: `credit.rs` (5 unit tests: home region, pro rata debit, credit
up to the ceiling, no merchants or no wealth, no state kept) and
`satisfaction.rs` (the grievance costs merchants only, inside the cap).

| Lane | Result |
| --- | --- |
| `python scripts/run_python_oracle_checks.py` (no-Rust interpreter) | PASS, 14 chunks: 2,761 passed, 59 skipped |
| `pytest -m "not slow"` (frozen tree, release extension) | 6,786 passed, 3 skipped, 15 deselected |
| `cargo test --locked` (`CARGO_PROFILE_TEST_DEBUG=0`) | 1,076 passed, 0 failed, 2 ignored |
