# Domestic credit through real lenders (`--domestic-credit`, 2026-10)

Branch `feat/domestic-credit` from `main` `ac74e5a` (PR #62, community
anchoring). Code: `src/chronicler/domestic_credit.py` (behaviour),
`src/chronicler/domestic_credit_state.py` (persisted state), hooks in
`finance.py` (Phase 3b and its snapshot), `guilds.py` / `guilds_state.py`
(a new threat and history kinds), `cities_state.py` (history kinds),
`agent_movements.py` (the guild movement's cause), `agent_bridge.py` (a
region column), `simulation.py`, `models.py`, `main.py`, `live.py`,
`run_checkpoint.py`, `batch_manifest.py`, `analytics.py`,
`scripts/m53b_run_validation.py`; native
`chronicler-agents/src/credit.rs` (merchant wealth), a satisfaction term in
`satisfaction.rs` / `tick.rs` and a region field in `region.rs` /
`ffi/mod.rs`. Probe: `scripts/domestic_credit_probe.py`. Tests:
`tests/test_domestic_credit.py` (guarded lane chunk `domestic-credit`),
`tests/test_domestic_credit_native.py`, Rust unit tests in `credit.rs` and
`satisfaction.rs`.

**Status: default off** (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`). With the
switch off every output is byte-identical to `main`
([identity](#5-switch-off-byte-identical-to-main)).

**Second pass (2026-10-28, [section 13](#13-second-pass-2026-10-28-featdomestic-credit-2)):**
lenders lend no new money that would raise the borrower's interest due
above half its revenue, and while the agent pool's wealth builds up from
its cold start the realm's abstract merchant houses lend finance's revenue
term again, fading as `0.98 ** turn`; no war reserve, no purse ceiling.
Early credit is restored and the ceiling treadmill is gone; still default
off (13.7). Sections 1-12 below are PR #63's; what the second pass
supersedes is marked there.

## Result

| | |
| --- | --- |
| switch off against `main` `ac74e5a` (9-case matrix) | 399 files, 0 differences (default and `--no-domestic-credit`) |
| switch on, exact resume (5 cases, every turn or the spread) | 195 resume points, 5,352 files, 0 differences |
| credit ledger (`CHRONICLER_CHECK_RESOURCES=1`), 40 worlds | every tick balanced; outputs equal the unchecked runs |
| template full gate (200 x 500) with the switch | PASS strict; EXPLORATORY, NO REGRESSION against main |
| procedural full gate (100 x 300) with the switch | PASS strict; EXPLORATORY, NO REGRESSION against main |
| early domestic loans (first 30 turns) | -48% to -63% |
| merchant wealth (mean over the run) | +5% to +26% |
| procedural worlds | domestic issuance +64% to +102%, foreign -22% to -31%, defaults -23% to -28% |
| template worlds | the foreign share of credit +0.13 to +0.17 |
| all-agent wealth Gini | +0.007 to +0.009 |
| satisfaction, migration, rebellion | no detectable change (merchant satisfaction -0.009) |
| pre-registration | 1a, 3, 5, 7 held; 6 mostly; 1b, 4 did not; 2 held in template worlds only |
| open | a debt treadmill in a few worlds (cities' purses grow from interest without a ceiling); early-game credit; war chests |

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
*(Superseded in part, 2026-10-28: that term lends again while the agent
pool's wealth builds up from its cold start, and every domestic loan is
limited by the borrower's room; [13.2](#132-design).)*

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
| `SERVICE_SHARE` (second pass) | 0.5 | no new domestic money that would raise the borrower's interest due (all its lines) above this share of its smoothed revenue | [CALIBRATE]; about half of revenue in interest is where early modern domestic creditors stopped financing crowns (13.2) |
| `COLD_START_DECAY` (second pass) | 0.02 | the cold-start houses lend finance's revenue term times `(1 - this) ** turn` | = the native agents' `WEALTH_DECAY` (tested): the share of the pool's equilibrium wealth not yet accumulated |

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

### 7.1 How it held

| | prediction | outcome |
| --- | --- | --- |
| 1a | early domestic loans fall by over a third | **held**: -63% template, -48% procedural |
| 1b | whole-run domestic issuance within +-40% | **did not hold**: +60% (template 300), -8% (template 500), +64% (procedural 200), +102% (procedural 300); richer lenders keep lending (8) |
| 2 | the foreign share rises | **held in template worlds** (+0.13 to +0.17), **reversed in procedural worlds** (-0.18, -0.25: domestic credit replaces foreign) |
| 3 | merchant wealth +5% or more | **held**: +14%, +5% (+7% over 40 seeds), +18%, +26% |
| 4 | merchant wealth concentrates (Gini of merchants, Gini over regions) | **did not hold as stated**: neither moves on average; the all-agent Gini rises (+0.007 to +0.009) and procedural merchants' Gini within civs (+0.007 to +0.009) |
| 5 | defaults, debasements, fiscal strain, PSI crises within +-30% | **held**, at the edge for template defaults at 300 turns (+31%, 1.2 SE); procedural defaults -23% to -28% |
| 6 | merchant satisfaction within +-0.01; satisfaction +-0.005, migration and rebellion +-5% | **mostly held**: merchant satisfaction -0.009 over 40 template worlds (2.2 SE), -0.011 over 20; satisfaction within, latest satisfaction -0.006 in the template gate; migration within; rebellion +7.9% (template gate) and -6.4% (procedural gate), not an effect in 40 paired worlds (-4.1%, SE 11.5%) |
| 7 | both gates pass, no newly failing required gate | **held** (9) |

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
*(Fixed in the second pass by the borrower's room, [13.2](#132-design).)*

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
2), run on this machine by a parallel session the same day (package digest
`e4039e6d...9c9c` and extension `8497d374...3d50`, those of this branch's
`main` tree; PASS strict). It replaces the re-scored design-1 report of the
ablation-oracles work, so needs method 8 and cohort method 5 score both
sides. Procedural: the design-2 full gate of `main` `ac74e5a` from the
community-anchoring work (its switch off).

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
mean sampled agents times turns, from the runs' `agent_events.arrow` and
the probe's agent counts). Off
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

**PASS strict; EXPLORATORY, NO REGRESSION** against main
(5,294 s). Every required oracle passes, as on main; this time the needs
ablation's six pairings all pass too.

| | main `ac74e5a` | `--domestic-credit` | change |
| --- | ---: | ---: | ---: |
| satisfaction mean | 0.5667 | 0.5679 | +0.0012 |
| latest satisfaction mean (last 60 turns) | 0.5741 | 0.5734 | -0.0007 |
| migration per agent-turn | 0.07555 | 0.07589 | +0.5% |
| rebellion per agent-turn | 0.03863 | 0.03615 | -6.4% |
| final Gini within 0.30-0.70 (share of civs) | 0.910 | 0.877 | -0.033 |
| occupation violations | 0.0019 | 0.0021 | |
| final living population (mean per world) | 540.7 | 534.3 | -1.2% |
| extinct worlds | 0 | 0 | |

Informational: needs ablation pairings autonomy 1.348 (main 1.440), social
1.177 (1.167), purpose 1.292 (1.280), material 1.135 (1.119), safety 1.161
[1.060, 1.263] (1.132 [1.049, 1.215]), spiritual 1.224 (1.222), all PASS;
the kin-roots cohort ablation fails on both sides (0.993 against 0.992).
Rebellion moves the other way here (-6.4%), as the paired template worlds
did: no effect of the switch on rebellion is detectable in either world
type. The share of civs whose final wealth Gini lies within 0.30-0.70 falls
here (0.910 -> 0.877) and rose in the template gate (0.852 -> 0.869); the
regression check asks for 0.20.

### Credit in the gate worlds

`domestic_credit_probe.py summarize` over each gate's batch, per world
(switch on only: main's gate batches are not kept, so the paired worlds of
8 carry the comparison).

| per world | template (200 x 500) | procedural (100 x 300) |
| --- | ---: | ---: |
| domestic loans before turn 30 | 1.5 | 5.9 |
| domestic issued / foreign issued | 959 / 578 | 8,393 / 6,512 |
| lent by merchants / cities / guilds | 704 / 241 / 15 | 6,295 / 2,012 / 86 |
| interest paid to merchants / cities | 446 / 184 | 4,709 / 1,538 |
| written off on merchants / cities / guilds | 44 / 12 / 0.9 | 684 / 190 / 12 |
| lapsed (fallen cities and guilds) | 1.3 | 36 |
| defaults that hit lenders | 0.87 (71 of 200 worlds) | 7.9 (99 of 100) |
| guild movements after a default | 0.075 (14 worlds) | 0.84 (46 worlds) |
| merchant region-turns with grievance | 83 | 967 |
| merchant credits still due at the end | 2.0 (max 241) | 60 (max 765) |
| debt / revenue, mean over civ-turns | 0.23 | 1.02 |

Credits still due are payments to the merchants of regions that have none
at the moment, or whose merchants are all at the wealth ceiling (they are
sent again each turn); one procedural world ends with 765 owed.

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
* **The abstract revenue-times-influence term is gone.** *(Superseded:
  it returns for the pool's cold start only, [13.2](#132-design).)* Only real wealth
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

1. Both full gates pass strict with the switch on and no newly failing
   required gate against main reports of the same fork design (9); they
   should be rerun on whatever calibration the decisions below lead to.
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

   *(Items 2 and 3 are decided in the second pass, [13.6](#136-decisions):
   a cold-start abstract lender; lenders refuse money the borrower cannot
   service; no war reserve and no purse ceiling. Item 1 is rerun there.)*
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

## 13. Second pass (2026-10-28, `feat/domestic-credit-2`)

Branch `feat/domestic-credit-2` from `main` `25854db` (PR #64; the
simulation is PR #63's). Code: `domestic_credit.py` (the borrower's room,
the cold-start houses), `domestic_credit_state.py` (a lender kind appended),
`scripts/domestic_credit_probe.py` (borrowing calls, early issuance, purses,
heavy-debt stretches, all-agent satisfaction), tests in
`tests/test_domestic_credit.py`. No native change, no new switch: all of it
runs only with `--domestic-credit`. Sections 1-12 are PR #63's and stand,
except where marked superseded; 11.2 (2) and (3) are decided here.

### 13.1 What was measured first

Runs of `main` with the switch off and on (PR #63's behaviour), with this
branch's probe (it only reads), hybrid, `PYTHONHASHSEED=0`.

**The treadmill.** The four template gate worlds whose cities received over
1,000 of interest (seeds 101, 177, 209, 125; 500 turns), per run:

| | switch off | PR #63 |
| --- | ---: | ---: |
| domestic interest paid | 1,292 | 12,030 |
| interest received by cities | 0 | 5,704 |
| largest city purse (mean of the four) | 92 | 873 (2,209 in seed 101) |
| longest stretch of a civ at 8+ turns of revenue owed | 22 | 67 (158 in seed 101) |
| civ-turns paying half the revenue or more in interest | 35 | 179 |

In seed 101 Thornwall borrows 44-75 every turn from turn 175 to 500, almost
all of it at peace: it borrows back its amortization and pays the interest
from revenue. At finance's debt ceiling (10 turns of revenue) the domestic
rate is about 7% (4% + 0.3 points per turn of revenue owed), so interest
alone takes about 70% of revenue and amortization another 50%; the state can
service its debt only by borrowing again. The abstract class stopped
lending when its formula (a fixed multiple of revenue and smoothed merchant
wealth) was used up, and the state defaulted. Real lenders' offers grow
with the interest they are paid, so they never stop.

**Who holds wealth early.** Agent wealth by occupation (agents by civ
affinity), template seeds 42-51 and procedural 32 x 10 seeds 42-46, main
with the switch off, mean per living civ (template / procedural):

| turn | agents' wealth | farmers | scholars | soldiers | merchants | priests | merchants' share of agents | main's capacity | of it, the revenue term | half the merchants' wealth |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 107 / 103 | 44% / 45% | 17% / 18% | 14% / 14% | 14% / 12% | 10% / 12% | 15% / 14% | 25 / 25 | 82% / 83% | 7 / 6 |
| 30 | 257 / 265 | 37% / 38% | 17% / 16% | 15% / 16% | 16% / 15% | 15% / 15% | 15% / 14% | 42 / 45 | 64% / 66% | 20 / 20 |
| 60 | 403 / 445 | 36% / 33% | 20% / 19% | 17% / 17% | 15% / 17% | 11% / 14% | 13% / 13% | 84 / 70 | 64% / 53% | 32 / 38 |

Main's capacity is the abstract class's formula before what it is owed.
Every agent starts with 0.5 wealth (`STARTING_WEALTH`) and closes 2% of
the gap to its equilibrium a turn (`WEALTH_DECAY`), so the pool's wealth is
still building up for a hundred turns. Merchants are not few: they are
13-15% of agents and hold 12-17% of the pool's wealth from turn 10 on, as
later. What young realms lack is not merchants but accumulated wealth of
any kind, and what main's abstract class lent early was mostly its revenue
term (82% of its capacity at turn 10).

**War borrowing.** Each borrowing call of the fiscal tick, with what it
would have asked at peace (obligations plus a turn of upkeep and the
buffer); the rest is the war chest (finance keeps a belligerent's treasury
at its full reserve target, eight turns of revenue):

| | switch off | PR #63 |
| --- | ---: | ---: |
| template 42-61 x 300: share of domestic issuance raised at war (war chest) | 0.66 (0.65) | 0.43 (0.42) |
| template: domestic issued at war, per run | 236 | 266 (+29, SE 68) |
| procedural 42-51 x 200: share raised at war | 0.74 | 0.73 |
| procedural: domestic issued at war, per run | 2,040 | 2,526 (+486, SE 585) |
| the four treadmill worlds: domestic issued at war (share) | 1,856 (0.58) | 5,752 (0.55) |

Most domestic credit is war credit with the switch off and on alike, and
nearly all of it is the war chest rather than unpaid obligations. PR #63
does not make credit more war-driven; it raises war borrowing only in the
treadmill worlds, where it raises all borrowing.

### 13.2 Design

**The borrower's room (problem 1).** Domestic lenders lend no new money that
would raise the borrower's interest due, on all its lines (domestic and
foreign, at their current rates), above `SERVICE_SHARE` = 0.5 of its
smoothed revenue:

    room = floor((SERVICE_SHARE x revenue_ema - interest due) / domestic rate now)
    domestic capacity = min(sum of the lenders' offers, room)

and the loan is split among the lenders pro rata to their offers, as
before. Why:

* Lenders ration credit by what the borrower can carry, not only by what
  they hold: a lender asks whether the borrower's revenue covers the
  interest, and past some burden a higher rate only raises the chance of
  default, so lenders refuse rather than charge more. PR #63's offers
  depend on the lenders' assets alone; this is the missing borrower side.
  It does what the abstract class's revenue-scaled formula did
  implicitly, without lending from nowhere.
* Half of revenue in interest is the order at which early modern domestic
  creditors stopped financing crowns (France in the 1780s, with debt
  service about half of royal revenue; Castile, whose juros came to absorb
  the revenues assigned to them before its suspensions of payment), and
  the upper end of what states carried for long. In finance's terms it
  binds at about 7.9 turns of revenue owed at base rates (about 5 with a
  fresh default's premium), below the 10-turn ceiling, so ordinary borrowing is
  untouched and the tail is cut.
* Interest, not interest plus amortization: finance amortizes every line
  over 20 turns and re-amortizes it on every advance, so rolling principal
  over is ordinary refinancing; the burden is the interest. Counting
  amortization at the same share would bind at about 4.8 turns of revenue
  and cut ordinary credit.
* At the limit lenders refinance no more than the borrower repays: the
  state pays the rest of its service from revenue, deleverages, or falls
  into arrears, and finance's default rule takes over as it did against
  the abstract class.
* Foreign lenders are finance's, unchanged (switch off and on): a state
  refused at home may still borrow abroad, as on main.

Not chosen: **rates rising with the lender's exposure** (finance keeps one
blended line per borrower and lender class; a funder-dependent rate would
pay more interest to the most exposed, richest lenders and feed the purses;
the borrower's rate already rises with its debt), and **a ceiling on civic
purses** (purses already lose 2% a turn, so a purse settles at fifty turns
of its income; they grew because a state paid 60-70% of its revenue to its
cities for 320 turns. With the room that income is bounded by the
borrower's revenue. A ceiling would cap the symptom and also change sack
plunder and free-city treasuries, which take half the purse).

**Cold-start houses (problem 2).** The abstract creditor class lends again,
as the realm's merchant houses (lender kind `houses`, key = the borrower's
civ index), only while the pool's wealth builds up:

    houses' offer = floor((1 - COLD_START_DECAY) ** turn x DOMESTIC_REVENUE_TURNS
                          x revenue_ema x merchant influence x trust x credit factors - their claims)

`COLD_START_DECAY` = 0.02 is the native `WEALTH_DECAY` (a test reads
`agent.rs`): `0.98 ** t` is the share of the pool's equilibrium wealth not
yet accumulated at turn t (82% at turn 10, 55% at 30, 13% at 100, 2% at
200). So early in a run domestic capacity is about main's (the real lenders
hold about what main's wealth term counted, the houses lend its revenue
term), and it passes to the real lenders at the rate their wealth appears.
Capped: never more than main's revenue term. The clock is the world's turn,
not the civ's age: a state founded at turn 200 (a secession, a free city)
inherits agents with 200 turns of wealth. The houses are serviced and
written down pro rata like any funder; what they are paid leaves into the
finance ledger (as the abstract class's receipts and `legacy` lines do); a
default on them raises no grievance and no history entry (nobody in the
pool lost); events name them "its merchant houses".

Not chosen: **other wealthy agents lending**. Every occupation is
cold-started alike, so other lenders would raise credit at every horizon
rather than restore early credit: priests hold about as much as merchants
(10-15% of the pool's wealth), so temples would double the lending base at
turn 10 and at turn 300 alike, and all agents would multiply it about six
times. Farmers, the largest holders (33-45%), are the peasantry (the pool
has no landholding occupation), and agent wealth drives occupational choice
(peer wealth), household formation and prosperity memories, so lending
their savings would reach food production. The cost of the houses: early in
a run part of domestic credit is again lent by nobody in the pool, for a
bounded time.

**War chests (problem 3): not changed.** The evidence (13.1) does not
support taking part of a region's merchant wealth out of wartime lending:
the war share of domestic credit is the same or lower with the switch, the
amount raised at war moves within noise outside the treadmill worlds, and
there the room bounds it. War was the main purpose of public borrowing from
merchants; a reserve held back from belligerents would cut wartime credit
below what main's abstract class supplied. Whether a belligerent should
borrow to hold an idle reserve at all is finance's rule (on by default, with
the switch off too) and outside this switch.

**The merchant tax (problem 4, not fixed here).** Revenue includes the
merchant tax (5% of merchant wealth a turn), which is not debited from the
agents. The room and the houses' term are shares of revenue, so richer
merchants widen the room through a tax they never pay, and interest paid to
merchants raises the tax base. Debiting the tax would lower merchant wealth
(and the merchants' offers) and leave revenue as it is: the room would then
be read from revenue actually collected. Fixing it changes the switch-off
path (it is the goods economy's tax) and is a separate correction.

**Contracts.** No random draws; fixed orders (the houses come after the
cities in the lender list). `KIND_NAMES` gains `houses` at the end (index 4;
the ledger's totals gain `<flow>_houses`, set to 0 on books saved before;
tested). Nothing is added to the region batch or the native pool, so the
native state schema is unchanged. The ledger checks the houses like every
kind (claims, flows, finance's counters); their receipts reach no purse or
due. With the switch off none of this runs.

### 13.3 Pre-registration

Written and committed before any confirmatory run or gate. Development
runs of this code seen before it: the four treadmill worlds (500 turns),
procedural 32 x 10 seeds 42-51 x 200 turns, template seeds 282-301 x 300
turns (all three arms), and smoke runs. The confirmatory sets are new:
paired template seeds 42-81 x 500 turns and procedural 32 x 10 seeds 52-71
x 300 turns, each with three arms (the switch off on `main`, which is
byte-identical to this branch's switch off; PR #63, `main` with the switch;
this branch with the switch), and the two full gates (template 200 x 500,
procedural 100 x 300, `--domestic-credit --exploratory-comparison`) against
main's full reports. Predictions, this branch against the switch off unless
said:

1. **Treadmill.** (a) Template gate: at most 1 world whose cities receive
   over 1,000 of interest (PR #63: 4 of 200), and the largest city purse
   below 500 (PR #63: 2,209). (b) Interest received by cities per world in
   both gates less than half PR #63's (template 184, procedural 1,538).
   (c) Paired: domestic interest paid less than a third of the way from off
   to PR #63 (new - off < (PR #63 - off) / 3); worlds with a civ at 8+
   turns of revenue owed for 50+ consecutive turns no more than with the
   switch off, plus one.
2. **Early credit.** Domestic issuance before turn 30 within +-20% of the
   switch off in both paired sets (PR #63: about -63%), before turn 60
   within +-25%. Domestic loan events before turn 30 per gate world at least
   2.5 template and 9 procedural (PR #63's gates: 1.5 and 5.9). The houses
   fund under a quarter of all domestic lending over a run.
3. **Whole-run credit.** Domestic issuance within +-30% of the switch off in
   template worlds; in procedural worlds below PR #63's (which doubled it
   at 300 turns), within -10% to +50% of the switch off.
4. **Defaults and fiscal crises.** Defaults, debasements, fiscal-strain
   onsets and PSI crises within +-30% of the switch off; procedural
   defaults above PR #63's (PR #63: -23% to -28%).
5. **Merchant wealth.** Mean over the run between -5% and +15% of the switch
   off, and below PR #63's gain in procedural worlds (PR #63: +26% at 300
   turns).
6. **Agents** (paired). All-agent satisfaction within +-0.005, merchant
   satisfaction within +-0.01, all-agent wealth Gini within +-0.01 of the
   switch off; migration, rebellion and occupation switches per agent-turn
   not different from the switch off by more than two standard errors of
   the paired difference; and against PR #63 the all-agent Gini no higher.
7. **War.** The share of domestic issuance raised at war within +-0.15 of
   the switch off.
8. **Foreign share** of issuance within +-0.10 of the switch off in both
   world types (PR #63: +0.17 template, -0.25 procedural).
9. **Gates.** Both full gates PASS strict, and the exploratory comparisons
   against main's full reports show no newly failing required gate (cohort
   method 6 and community method 2 report `rebaseline_required` against
   those older reports, as expected).

### 13.4 Identity, resume and conservation

Environment: Linux, Python 3.13.17, `PYTHONHASHSEED=0`, one virtualenv
per tree outside the checkout, each with a release extension built fresh
(`maturin develop --release --locked`, its own `CARGO_TARGET_DIR`), the
compiled `chronicler_agents.chronicler_agents` and the real
`AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` classes
verified. `main` `25854db` from an exported tree; the branch's frozen tree
`004907f` (the pre-registration commit; every later commit changes tests,
the probe or documentation only). Both extensions have SHA-256
`3da1ee1f...dad0b` (no Rust change), as PR #63's branch build had.

| | |
| --- | --- |
| switch off against `main` (`scripts/turn_speed_identity.py`, 9-case matrix) | no flag: 399 files, 0 differences; explicit `--no-domestic-credit`: 399 files, 0 differences |
| switch on, exact resume (`scripts/checkpoint_identity.py --cli-arg=--domestic-credit`) | `hybrid_s42` 60 turns, 59 resume points, 1,780 files; `proc32_hybrid_s11` 40 turns, 39 points, 1,176 files (a default at turn 32 on the houses and the merchants of a region); `hybrid_s42_long` 200 turns, 19 points, 1,616 files (a default at turn 77): 117 resume points, 4,572 files, 0 differences; writing checkpoints changes nothing |
| credit ledger checked every tick (`CHRONICLER_CHECK_RESOURCES=1`) | template seeds 42-61 x 300 and procedural 32 x 10 seeds 42-61 x 200: 40 of 40 runs balanced; their final states are byte-identical to unchecked runs of the same seeds (40 of 40) |

After the gates the branch was merged with `main` `c2ef6af` (PRs #65 and
#66, live and interactive checkpoints; no simulation file, no Rust). The
merged head `1eb4478` against `c2ef6af` with the switch off: 399 files, 0
differences (no flag and explicit `--no-domestic-credit`); against the
frozen tree `004907f` with the switch on, the six hybrid cases of the
matrix: 366 files, 0 differences. So the gates and paired worlds below
describe the merged head's simulation.

Every resume case lends from merchants, cities and houses; the straight
runs equal the runs without checkpoints. Over the checked runs, per run:
template, merchants lent 241, cities 46, guilds 4, the houses 77 (21% of
domestic lending at 300 turns); procedural, merchants 2,386, cities 492,
guilds 26, the houses 384 (12%).

### 13.5 Results

**Paired worlds** (`scripts/domestic_credit_probe.py`, the frozen tree's
copy for the runs, summarized again with the current probe, which adds
read-only measures; means per run, SE of the paired difference). Arms:
the switch off (`main`), PR #63 (`main` with the switch), this branch with
the switch. Template seeds 42-81 x 500 turns:

| measure | off | PR #63 | this branch | PR #63 - off (SE) | branch - off (SE) |
| --- | ---: | ---: | ---: | ---: | ---: |
| domestic issued before turn 30 | 109 | 40 | 102 | **-69** (7) | -8 (5) |
| domestic issued before turn 60 | 142 | 121 | 152 | -20 (17) | +10 (12) |
| domestic loans before turn 30 | 3.55 | 1.6 | 3.5 | **-1.95** (0.25) | -0.05 (0.18) |
| domestic issued | 602 | 747 | 627 | +145 (196) | +25 (156) |
| foreign issued | 425 | 559 | 586 | +133 (134) | +161 (152) |
| foreign share of issuance | 0.40 | 0.55 | 0.40 | **+0.14** (0.04) | -0.00 (0.04) |
| domestic interest paid | 252 | 496 | 277 | +244 (189) | +25 (69) |
| interest received by cities | 0 | 63 | 35 | | |
| the houses' part of domestic lending | | | 68 (11%) | | |
| largest city purse | 89 | 99 | 95 | +9 (7) | +6 (7) |
| worlds: a civ at 8+ turns of revenue owed for 50+ turns | 0 | 1 | 0 | | |
| worlds: a civ paying 40%+ of revenue in interest for 50+ turns | 0 | 1 | 1 | | |
| defaults / debasements | 1.15 / 1.23 | 1.18 / 1.35 | 1.35 / 1.23 | +0.03 / +0.13 | +0.20 (0.21) / 0 |
| fiscal-strain onsets / PSI crises | 5.75 / 1.55 | 6.3 / 1.48 | 6.6 / 1.83 | +0.55 / -0.08 | +0.85 (1.28) / +0.28 (0.46) |
| share of domestic issuance at war | 0.71 | 0.49 | 0.61 | **-0.19** (0.08) | -0.09 (0.06) |
| merchant wealth, mean | 374 | 401 | 389 | +27 (+7%) (14) | +15 (+4%) (9) |
| satisfaction, mean | 0.6209 | 0.6130 | 0.6198 | **-0.0079** (0.0028) | -0.0010 (0.0033) |
| merchant satisfaction, mean | 0.4416 | 0.4330 | 0.4385 | **-0.0086** (0.0039) | -0.0031 (0.0050) |
| Gini of all agents' wealth, mean | 0.6186 | 0.6257 | 0.6235 | **+0.0071** (0.0031) | +0.0049 (0.0029) |
| written off on merchants | 0 | 24 | 12 | | |
| population at the end / polities alive | 184 / 2.90 | 184 / 2.93 | 185 / 2.95 | | |

Procedural 32 x 10, seeds 52-71 x 300 turns:

| measure | off | PR #63 | this branch | PR #63 - off (SE) | branch - off (SE) |
| --- | ---: | ---: | ---: | ---: | ---: |
| domestic issued before turn 30 | 467 | 153 | 406 | **-314** (23) | **-61** (18) |
| domestic issued before turn 60 | 769 | 555 | 832 | **-214** (78) | +62 (85) |
| domestic loans before turn 30 | 11.8 | 5.75 | 11.3 | **-6.05** (0.68) | -0.5 (0.55) |
| domestic issued | 4,159 | 9,544 | 5,571 | **+5,385** (865) | **+1,413** (588) |
| foreign issued | 6,790 | 6,986 | 9,211 | +196 (972) | +2,421 (1,330) |
| foreign share of issuance | 0.60 | 0.40 | 0.61 | **-0.19** (0.04) | +0.01 (0.03) |
| domestic interest paid | 2,136 | 7,256 | 3,650 | **+5,120** (876) | **+1,514** (485) |
| interest received by cities | 0 | 1,724 | 767 | | |
| the houses' part of domestic lending | | | 401 (7%) | | |
| largest city purse | 81 | 319 | 191 | **+238** (43) | **+110** (26) |
| worlds: a civ at 8+ turns of revenue owed for 50+ turns | 0 | 2 | 0 | | |
| worlds: a civ paying 40%+ of revenue in interest for 50+ turns | 0 | 10 | 1 | | |
| worlds whose cities received over 1,000 of interest | 0 | 14 | 5 | | |
| defaults / debasements | 8.6 / 5.75 | 9.3 / 6.35 | 9.3 / 5.3 | +0.7 (1.35) / +0.6 | +0.7 (1.14) / -0.45 (0.68) |
| fiscal-strain onsets / PSI crises | 25.0 / 7.65 | 27.7 / 8.55 | 24.5 / 7.7 | +2.65 / +0.9 | -0.55 (2.5) / +0.05 (1.0) |
| written off on merchants / cities | 0 | 806 / 193 | 195 / 43 | | |
| share of domestic issuance at war | 0.75 | 0.57 | 0.66 | **-0.18** (0.05) | **-0.09** (0.04) |
| merchant wealth, mean | 962 | 1,225 | 1,086 | **+264 (+27%)** (59) | **+125 (+13%)** (44) |
| satisfaction, mean | 0.555 | 0.560 | 0.563 | +0.005 (0.006) | +0.008 (0.006) |
| merchant satisfaction, mean | 0.368 | 0.375 | 0.379 | +0.007 (0.008) | +0.012 (0.008) |
| Gini of all agents' wealth, mean | 0.600 | 0.607 | 0.602 | **+0.007** (0.003) | +0.002 (0.003) |
| population at the end / polities alive | 537 / 8.0 | 534 / 8.9 | 533 / 8.55 | -3 / **+0.9** (0.29) | -4 / +0.55 (0.40) |

Agent rates per agent-turn, counted as the regression oracle counts them
(the runs' `agent_events.arrow` over the probe's agent counts):

| per agent-turn | template off | PR #63 - off | branch - off | procedural off | PR #63 - off | branch - off |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| migration | 0.06145 | -0.3% (SE 2.0%) | -1.9% (1.9%) | 0.07699 | -0.1% (1.8%) | **-3.7% (1.6%)** |
| rebellion | 0.03112 | -4.1% (11.5%) | -14.5% (9.4%) | 0.03619 | -14.9% (12.1%) | -18.6% (13.9%) |
| occupation switches | 0.04749 | +1.1% (1.7%) | +0.9% (2.5%) | 0.03761 | +2.2% (1.6%) | +0.2% (1.6%) |

The off and PR #63 arms of the template set reproduce PR #63's own 40
paired worlds exactly (migration 0.06145 and 0.06129, rebellion 0.03112
and 0.02984, section 9).

What it does. Early credit is back: domestic issuance before turn 30 is
within 7-13% of the switch off (PR #63: about -65%), and the houses fund
7-11% of all domestic lending over a run. In template worlds the switch now
changes credit little over a run: domestic issuance +4%, domestic interest
+10%, the foreign share unchanged (PR #63: +0.14), merchant wealth +4%.
Procedural worlds still lend more at home (+34%, PR #63 +129%) and borrow
more abroad too (+36%, 1.8 SE): a state refused at home by the room turns
to foreign lenders, which finance does not limit by the borrower's
interest. Lenders lose much less in defaults (procedural write-offs on
merchants 195 against PR #63's 806): they no longer lend past what the
borrower can service. The ceiling treadmill is gone: no world
in either set (nor in either gate) has a civ at eight or more turns of
revenue owed for 50 turns. What remains is a borrower at the room (13.6).

**Gates** (`scripts/m53b_run_validation.py --profile full
--require-strict-regression --exploratory-comparison --domestic-credit`,
the frozen tree and its extension, three workers, one full gate on the
machine at a time). Baselines: main's template full report (`ac74e5a`,
the simulation unchanged since; spec-communities `main-t-full`) and
main's procedural full report (community-anchoring `p-full-off2`).

Template full (200 seeds x 500 turns): **PASS strict; EXPLORATORY, NO
REGRESSION** against main (4,008 s). Every required oracle passes (arcs,
artifacts strict, cohort, community, era, needs, regression strict), as on
main; cohort method 6 and community method 2 against main's methods 5 and
1 are reported as method changes (`rebaseline_required`), as expected.

| | main | PR #63 | this branch | branch - main |
| --- | ---: | ---: | ---: | ---: |
| satisfaction mean | 0.6212 | 0.6173 | 0.6180 | -0.0032 |
| latest satisfaction mean (last 60 turns) | 0.6330 | 0.6267 | 0.6276 | -0.0055 |
| migration per agent-turn | 0.06340 | 0.06313 | 0.06312 | -0.4% |
| rebellion per agent-turn | 0.03295 | 0.03555 | 0.03471 | +5.3% |
| final Gini within 0.30-0.70 (share of civs) | 0.852 | 0.869 | 0.827 | -0.025 |
| occupation violations | 0.0012 | 0.0013 | 0.0014 | |
| final living population (mean per world) | 185.3 | 181.8 | 184.7 | -0.3% |
| era: silent collapses / collapse episodes | 1 / 4,666 | 0 / 4,595 | 0 / 4,675 | |
| arcs: seeds with three types | 151 | 164 | 163 | |
| artifacts per civ per 100 turns | 1.85 | 1.87 | 1.85 | |
| extinct worlds | 0 | 0 | 0 | |

Informational: the needs ablation's six pairings all pass (safety 1.218
[0.966, 1.471], PR #63's gate 1.071 [0.877, 1.266]); the kin-roots cohort
ablation fails, as on main (0.998). The paired worlds put the gate's
movements in proportion: satisfaction -0.001 (SE 0.003) and rebellion
-14.5% (SE 9.4%) in 40 paired worlds, so the gate's -0.0055 and +5.3% are
the spread of single worlds.

Procedural full (100 seeds x 300 turns, 32 regions x 10 civs): **PASS
strict; EXPLORATORY, NO REGRESSION** against main (5,949 s). Every required
oracle passes, as on main; cohort and community report method changes
(`rebaseline_required`), as expected.

| | main | PR #63 | this branch | branch - main |
| --- | ---: | ---: | ---: | ---: |
| satisfaction mean | 0.5667 | 0.5679 | 0.5706 | +0.0039 |
| latest satisfaction mean (last 60 turns) | 0.5741 | 0.5734 | 0.5760 | +0.0019 |
| migration per agent-turn | 0.07555 | 0.07589 | 0.07554 | -0.0% |
| rebellion per agent-turn | 0.03863 | 0.03615 | 0.03574 | -7.5% |
| final Gini within 0.30-0.70 (share of civs) | 0.910 | 0.877 | 0.892 | -0.018 |
| occupation violations | 0.0019 | 0.0021 | 0.0018 | |
| final living population (mean per world) | 540.7 | 534.3 | 537.5 | -0.6% |
| era: silent collapses / collapse episodes | 1 / 4,431 | 0 / 4,441 | 0 / 4,354 | |
| arcs: seeds with three types | 97 | 97 | 100 | |
| artifacts per civ per 100 turns | 2.50 | 2.44 | 2.38 | |
| extinct worlds | 0 | 0 | 0 | |

Informational: the needs ablation's six pairings all pass (safety 1.232
[1.141, 1.323]; main 1.132 [1.049, 1.215]); the kin-roots cohort ablation
fails, as on main (0.990). The paired procedural worlds' migration -3.7%
(2.3 SE) does not appear in the gate (0.07554 against main's 0.07555 over
100 worlds), and satisfaction reads +0.004 there against +0.008 paired.

Credit in the gate worlds (`domestic_credit_probe.py summarize` over each
batch; main's gate batches are not kept, so the paired worlds carry the
comparison with the switch off):

| per world | template, PR #63 | template, branch | procedural, PR #63 | procedural, branch |
| --- | ---: | ---: | ---: | ---: |
| domestic loans before turn 30 | 1.5 | 3.66 | 5.9 | 11.34 |
| domestic issued / foreign issued | 959 / 578 | 908 / 614 | 8,393 / 6,512 | 6,122 / 9,051 |
| lent by merchants / cities / guilds / houses | 704 / 241 / 15 / - | 630 / 193 / 12 / 72 | 6,295 / 2,012 / 86 / - | 4,405 / 1,251 / 67 / 399 |
| interest paid to merchants / cities / houses | 446 / 184 / - | 351 / 114 / 24 | 4,709 / 1,538 / - | 3,018 / 855 / 159 |
| written off on merchants / cities | 44 / 12 | 19 / 4 | 684 / 190 | 208 / 45 |
| defaults that hit lenders | 0.87 | 0.80 | 7.9 | 6.74 |
| guild movements after a default (worlds) | 0.075 (14) | 0.04 (9) | 0.84 (46) | 0.56 (39) |
| merchant credits still due at the end (max) | 2.0 (241) | 0.8 (24) | 60 (765) | 33 (293) |
| worlds whose cities received over 1,000 of interest | 4 | 5 | 55 | 30 |
| largest city purse | 2,209 (seed 101) | 610 | | 875 |
| worlds: 8+ turns of revenue owed for 50+ turns | | 0 (longest 33) | | 0 (longest 39) |
| worlds: 40%+ of revenue in interest for 50+ turns | | 4 (longest 97) | | 14 (longest 94) |

(PR #63's gate batches are deleted; its census kept the rows shown, and
seed 101's purse is from a rerun of `main` with the switch. Its four
treadmill worlds in this branch's gate: domestic interest 169, 964, 605 and
1,482 a run against 24,157, 12,546, 5,002 and 6,398.)

**Pre-registration (13.3), how it held:**

| | prediction | outcome |
| --- | --- | --- |
| 1a | template gate: at most 1 world with cities paid over 1,000; largest purse below 500 | **did not hold**: 5 worlds; largest purse 610 (PR #63: 4; 2,209) |
| 1b | cities' interest per gate world below half PR #63's | **did not hold**: -38% template (114 against 184), -44% procedural (855 against 1,538) |
| 1c | paired domestic interest less than a third of the way to PR #63; heavy-debt 50+ worlds no more than off + 1 | **held**: +25 against +244 (template), +1,514 against +5,120 (procedural); 0 heavy-debt worlds in both sets |
| 2 | early issuance within +-20% (turn 30), +-25% (turn 60); gate loans before turn 30 at least 2.5 and 9; houses under a quarter | **held**: -7%, -13%; +7%, +8%; 3.66 and 11.34; 7-11% (21% in the 300-turn checked runs) |
| 3 | whole-run domestic issuance within +-30% (template), -10% to +50% and below PR #63's (procedural) | **held**: +4%; +34% (PR #63 +129%) |
| 4 | defaults, debasements, fiscal strain, PSI crises within +-30%; procedural defaults above PR #63's | **held** except the last: within +-18% everywhere; procedural defaults equal PR #63's (9.3 and 9.3; in this seed set PR #63 does not lower them) |
| 5 | merchant wealth -5% to +15%, below PR #63's procedural gain | **held**: +4%, +13% (PR #63 +7%, +27%) |
| 6 | satisfaction +-0.005, merchant satisfaction +-0.01, Gini +-0.01; rates within 2 SE; Gini no higher than PR #63's | **held in template worlds; partly in procedural**: satisfaction +0.008 (1.2 SE) and merchant satisfaction +0.012 (1.4 SE) outside their ranges, though not different from zero; migration -3.7% (2.3 SE) |
| 7 | war share within +-0.15 | **held**: -0.09, -0.09 |
| 8 | foreign share within +-0.10 | **held**: -0.00, +0.01 |
| 9 | both gates PASS strict, no newly failing required gate | **held**: template and procedural PASS strict, EXPLORATORY NO REGRESSION; cohort method 6 and community method 2 `rebaseline_required`, as expected |

1a and 1b were predicted from the four treadmill worlds, which in the
development runs happened not to rebuild their debt (their histories
diverge); across 200 worlds the count of cities paid over 1,000 measures
the volume of civic lending rather than the ceiling treadmill, and the
room does not stop a borrower from staying at the room for a long time
with its cities as the main lenders (13.6).

### 13.6 Decisions

**Made here.**

* **The borrower's room** (problem 1): domestic lenders lend nothing that
  would raise the borrower's interest due above half its revenue. It
  removes the ceiling treadmill (a civ at eight or more turns of revenue
  owed for 50+ turns: PR #63's seed 101 for 158 turns; none here in 300
  gate worlds and 60 paired worlds) and bounds how much a state pays its
  lenders. It does not end every long debt: a state at the room whose
  revenue covers its interest is refinanced as it repays and can stay
  there (template seed 110: Dorrathi Clans owes 600-760, 6.6-8.2 turns of
  revenue, for about 150 turns, paying 42-48% of its revenue in interest,
  never defaulting). That is a perpetual debt of the early modern kind,
  serviced from revenue; finance defaults only on unpaid service, and a
  lender paid in full has no reason to refuse. Such stretches (40%+ of
  revenue in interest for 50+ turns) occur in 4 of 200 template and 14 of
  100 procedural gate worlds, up to 97 turns.
* **No ceiling on purses, no exposure-dependent rates** (13.2). The room
  bounds the interest; it does not bound who receives it. Within one
  borrower's line, cities' offers grow with their purses (which have no
  ceiling) while merchants are capped at 100 an agent and decay, so at the
  room cities take a growing share of each refinancing (template seed 193:
  Ashkari's claims held by cities 132 -> 273 while its merchants' fell 431
  -> 136; seed 110: Thornwood Settlement 2's claims 189 -> 441, its purse 58
  -> 419). Purses stay far below PR #63's (template gate largest 610
  against 2,209; procedural paired median of the largest purse 159
  against 274, off 73) but above the switch off. This is the one
  accumulation the second pass leaves; it is decision 13.7 (1).
* **Cold-start houses** (problem 2) rather than other wealthy agents: 13.2.
  They fund 7-11% of domestic lending over a run; by turn 200 they offer
  2% of their initial term.
* **No war reserve** (problem 3): the evidence does not support it (13.1;
  the war share of domestic credit is 0.61-0.66 with this branch against
  0.71-0.75 off).
* **The merchant tax** (problem 4) is left as it is; its interaction is in
  13.2.

### 13.7 Promotion

**Recommendation: not yet.** The switch makes the realm's domestic
creditors real and keeps their books exactly, both full gates pass, early
credit and the ceiling treadmill are fixed, and in template worlds its
fiscal footprint is now small (domestic issuance +4%, interest +10%,
merchant wealth +4%, agents' satisfaction, migration and rebellion within
their spread). Three things should come first:

1. **Civic lenders.** Decide how a city's or guild's interest income
   leaves its purse: either the purse passes interest through to the
   burghers who fund it (the merchants of its region, whose wealth is
   capped and decays), as communes lending to their lords did, or the
   purse has a ceiling as agent wealth does. Purses feed sack plunder and
   free-city treasuries (half the purse each), so their size is not only
   bookkeeping.
2. **The merchant tax** (11.2 (4)). With the switch, interest paid to
   merchants raises the base of a tax the agents never pay, and the room
   and the houses' term are shares of that revenue. Debit it (a switch-off
   change of the goods economy, with its own gates) or decide it stays.
3. **A second look at procedural agents**: migration -3.7% (2.3 SE) and
   merchant satisfaction +0.012 (1.4 SE) in 20 paired procedural worlds;
   the procedural gate reads migration at main's level (0.07554 against
   0.07555) and satisfaction +0.004, so neither is established. Rerun on
   40 paired procedural worlds with whatever 1 and 2 change.

**Evidence a promotion PR needs** (the repo's rule: a documented 200-seed
before/after full gate, as `defaults-wave8.md` and
`techniques-default.md` did):

* the flip alone (`DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, CLI help, live
  comments, a new-world default test; the benchmark pins and frozen
  oracle fixtures pinned to the switch off so they replay the same
  worlds), on a tree whose calibration is final;
* template full gate (200 x 500) of `main` and of the branch with no
  flags, the same seeds, both PASS strict, and a non-exploratory
  comparison with no newly failing required gate (oracle method changes
  re-baselined first, so that cohort and community compare);
* the same for the procedural full gate (100 x 300, `--worldgen
  procedural`);
* identity: the branch with an explicit `--no-domestic-credit` against
  `main` with no flags (9-case matrix, 0 differences), and a save written
  before the flip resumed with its setting kept;
* exact resume and the checked ledger with the new default (as 13.4);
* the paired probes rerun (40 template x 500, 40 procedural x 300) with
  agent rates, against the pre-registered ranges of the change that is
  promoted;
* the viewer showing who holds a realm's debt (11.2 (5)), or a decision
  that it is not needed for the default.

### 13.8 Tests and lanes

`tests/test_domestic_credit.py` adds: the borrower's room (its formula,
capacity the lesser of the offers and the room, no money at half the
revenue in interest, no domestic issue in a fiscal tick there); the houses
(their faded offer, less their claims, named in the event, receipts into
the ledger only, gone by turn 400); a default on the houses raising no
grievance; the cold-start decay read from `agent.rs`; books saved before
the second pass gaining the `houses` totals; and the probe's measures on
synthetic snapshots. The real-lender test of PR #63 runs past the cold
start. `tests/test_domestic_credit_native.py`'s hybrid run now checks that
loans name real lenders and that the houses lend early.

| Lane | Result |
| --- | --- |
| `python scripts/run_python_oracle_checks.py` (no-Rust interpreter) | PASS, 14 chunks: 2,786 passed, 59 skipped (chunk `domestic-credit` 32 tests, 1.2 s); merged head: PASS, 16 chunks, 2,827 passed, 63 skipped |
| `pytest -m "not slow"` (release extension) | 6,813 passed, 3 skipped, 15 deselected before the merge; merged head 6,840 passed, 3 skipped, 15 deselected (an earlier run on the frozen tree failed one native test that filtered out loans naming the houses, fixed in the test) |
| `cargo test --locked` (`CARGO_PROFILE_TEST_DEBUG=0`) | 1,076 passed, 0 failed, 2 ignored |
