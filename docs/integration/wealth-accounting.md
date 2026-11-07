# Wealth accounting (A1, `--wealth-accounting`)

An observation-only ledger of agent wealth, per region and turn. Default off;
requires `--agents hybrid`. Connected-world program, slice A1-1 (Python only:
no native change, no edit to any paying package). Design source: the A1-A2
income and wealth audit (`docs/superpowers/audits/connected-world/`, section
3.2). Code: `src/chronicler/wealth_accounting.py` and
`src/chronicler/wealth_accounting_state.py`; tests:
`tests/test_wealth_accounting.py` (offline) and
`tests/test_wealth_accounting_native.py` (compiled extension).

## Why

Native agent `wealth` (`AgentPool.wealth`, f32, clamped to [0, 100]) is the
one spendable balance every payer debits: wages, purchases, fares and
remittances all move it through keyed native transfers. It is **not
conserved cash**. Most of what enters it is created by the native model
(occupational income in the wealth phase, birth endowments) and most of what
leaves it is destroyed by the model (the 2% decay, the ceiling, estates
without heirs). No check covered it as a whole. This package makes the books
visible: it does not change them, and it never calls them conserved.

## What it observes

| When | What | Source |
| --- | --- | --- |
| Phase 2, before any Phase 2 writer (`prepare_phase2`, after every other package's) | the **opening**: each person's f32 wealth and region | the Phase 2 agent snapshot the economy reads |
| same | the **continuity check** against the previous closing | a SHA-256 of `(id, f32 wealth bits)` and of `(id, region)` in ascending id order |
| Phase 10, the last livelihoods hook (`phase10`, after granary procurement) | the **typed flows** of the turn | the packages' committed receipts, ledgers and counter deltas (below) |
| same | **withheld paid work**, attributed per package | the shared native paid-work receipt (`livelihoods.paid_work_receipt`) |
| same | the **treasury side** | the same receipts, the economy's tax and the tithe base |
| same | the **closing** (after every payer) | a fresh `get_snapshot()` |

No agent-tick hook is registered, so the post-tick snapshot hand-over to
Phase 10 is unchanged. Nothing here draws a random number, writes wealth, a
treasury or another package's state.

## The identity and how to read the residual

Per region `r` and for the world, in wealth units:

```
close_r - open_r = (migration_in_r - migration_out_r)
                 + (typed_in_milli_r - typed_out_milli_r) / 1000
                 + native_model_r
```

- `open`/`close`: sums of the f32 balances (in f64) of the people resident in
  `r` at the opening and at the closing.
- `migration`: the **closing** balances of people whose region changed during
  the turn. A mover's own change during the turn stays with the region they
  left (where Phase 2 wages were recorded); the world sum of migration is
  exactly zero.
- People alive at the opening and not at the closing (`deaths`, their opening
  balances `deaths_open`) and people born during the turn (`births`,
  `births_close`) are attributed to their opening and closing region; their
  counts and balances are reported, not itemized as flows (an estate that
  reached an heir is inside the heir's change).
- `typed`: located typed flows (below).
- `native_model`: **the residual, labelled, not itemized in slice 1** -
  occupational income net of withheld shares, decay, the wealth ceiling,
  birth endowments, estates without heirs and inheritance overflow, plus the
  f32 rounding of typed transfers (audit D4, in the world residual too). **Per
  region it also holds every unlocated typed flow** (`unlocated_in_milli`,
  `unlocated_out_milli`: granary procurement, L7 fares beyond the kept sample,
  domestic credit, wages of PL3 receipts dropped by its row cap) and typed
  flows a package recorded in another region than the payee's opening region,
  so a region's residual is not model-only while unlocated flows are non-zero.
  The record's own label says so.

World: `close - open = typed_net_milli / 1000 + native_model`, with
`typed_net_milli` including the `unlocated` flows (a package that records no
region per payment). So `sum(native_model_r) = native_model +
unlocated_net / 1000` (plus nothing else: `unplaced_agents`, people outside
`0..len(world.regions)`, is reported and is 0 on every world checked).

Read it this way: `typed` is what packages moved between named payers and
payees; `native_model` is what the native model created or destroyed. A
large positive `native_model` is model income outrunning decay; a turn whose
`native_model` jumps without a typed flow is a model event (a conquest bonus,
a death without heirs). Slice 2 (a native observer) will itemize it.

## Typed flows, created money and sinks

| Channel | Payer -> payee | Read from | Region | Closure re-checked |
| --- | --- | --- | --- | --- |
| `workshop_wage` | L6a firm cash -> crew | `workshop_payroll.frame` (`wages_paid`) | firm region | firm cash: open + sales - wages - stipends - distributions - write-offs = close |
| `apprentice_stipend` | L6a firm cash -> RS1 apprentice | the firm receipts' `stipends` | firm region | (inside the firm-cash closure) |
| `repair_wage` | treasury -> RS2 workshop repair crew | RS2 `receipts`, `ledger` | project region | charged x 1000 + prepaid before = coin costs + wages + prepaid after; ledger wages = receipt wages |
| `granary_crew_wage` | treasury granary coins -> PL3 granary crew | PL3 `ledger`, `receipts` | granary region | coins = wages + sunk (paid and `unpaid`); wages + residual = due |
| `woodcut_wage` | treasury -> PL1 crew | PL1 `receipts`, `ledger` | home region | charged x 1000 + prepaid before = wages + prepaid after; ledger = receipts |
| `food_procurement` | treasury -> owners of procured grain (L6b) | retail `money` (`procurement_*`) | unlocated | owed = credited + residual + unpaid |
| `food_purchase` | buyers -> sellers in the tick (L6b) | retail `money`, `frame[].provisioning` | pilot region | paid = credited + refunded; household net = 0 |
| `remittance` | sender -> recipient, fee to the courier sink (RS4) | RS4 `totals`, `regions` | host (out), origin (in) | debited = credited + fee; sent = debited + refunded |
| `relocation_fare` | movers -> travel sink (L7) | the `fare_debited_milli` counter delta; the kept household sample for regions | from region (sample), rest unlocated | due - assistance = debited + residual + not charged; travel sink = fares + assistance coins x 1000 |
| `domestic_credit` | treasury <-> merchants, net applied | `domestic_credit.merchant_applied` delta, rounded to whole milli-units (the sub-milli rest of the f32 change stays in `native_model`) | unlocated | (its own books: `CHRONICLER_CHECK_RESOURCES=1`) |
| `wares_purchase` (A3, [workshop economics](workshop-economics.md)) | households -> workshop firm cash | the payment seam's register (`money.flows_for_turn`) | firm region | households debited = firm credited (A3 receipts); capital and input flows = the receipts; inputs to treasuries = units x 1000 + carry change |

Every typed amount is a whole milli-unit. `typed_complete` means **every known
channel** of an active package had this turn's record. A payer this module
does not know cannot pass unnoticed. `wealth_accounting_state.WEALTH_WRITERS`
registers every **payer path** - module, enclosing function, native writer
(`transfer_wealth`, `remit_wealth`, `apply_merchant_transfers`,
`set_household_retail`, `install_paid_work`, `extend_paid_work`,
`install_retail_income`, `reserve_learning_attendance`,
`prepare_teaching_work`, `prepare_health_work`) or routing helper, and the
purpose and batch arguments as written - with its number of call sites and the
channel the ledger reads it as. `WEALTH_ROUTERS` declares helpers that route a
payment for a caller-chosen purpose (`workshop_payroll.pay_from_firm`, and
A3's `money._native_transfer`, through which `money.pay` routes every
agent-wealth line; `MONEY_PURPOSE_CHANNELS` lists the purposes the seam may
move agent wealth for, and `money` refuses any other at run time) with the
channels they may carry; each call of a router
is a path of its own, and a writer call that takes its purpose or batch from a
parameter of an undeclared function fails. `WEALTH_WRITER_REFERENCES` lists the
only other references to a writer's name (the name strings packages use to
check the extension has a method). `tests/test_wealth_accounting.py` walks
`src/` and fails closed: an unregistered path, a changed call-site count, a
new purpose or batch, a `getattr` or bound-method alias, or a name in a string
fails, as does a stale row. A new payer path adds one row (and its channel). A
native test also fails when `AgentSimulator.wealth_transfer_purposes()` grows
past `KNOWN_PURPOSES`. Not seen by the walk: a writer name assembled from
pieces at run time.

Created or destroyed, recorded beside the typed flows (`frame.treasury`):

- `created.treasury_tax`: the 5% treasury tax on merchant wealth, in whole
  units, reproduced exactly from `economy_result.treasury_tax` and the
  fractional carry read at the opening. **Credited to the treasury, debited
  from nobody** (audit D3).
- `tithe` (not in `created`): `potential` is `int(TITHE_RATE x tithe base)`
  per civilization with regions - an **upper bound, not created money**;
  `at_threshold_after_tick` is the part of civilizations whose clergy influence
  is at the faction threshold after the faction tick (`approximate: true`: the
  tick tests the threshold before it normalizes influence); `collected` is
  **None**. What is collected is credited to the treasury and debited from
  nobody (audit D3). On the development worlds below the approximate collected
  part is 39% and 14% of the potential.
- `to_households_milli`: wages and procurement credits paid from treasuries;
  `firm_cash`: treasury purchases into L6a firm cash and what firm cash paid
  out; `charged`: whole treasury units charged by RS2, PL1 and L7 assistance;
  `sinks_milli`: RS2 granary coins not paid to PL3 crews, PL3 ceiling
  residuals, the remittance fee, fares and assistance to the travel sink,
  procurement credits refused by a ceiling. `by_civ` repeats them per
  civilization where the package records one.
- `firm_economics` (only while A3 is active; with A3 off a record differs
  from one built before A3 only in the declared channel list,
  `parameters.channels`, which ends with `wares_purchase`): owner capital paid into firm cash, input purchases to rulers
  (whole units and the carried sub-unit change) or to the `unowned_commons`
  sink, household sales, the firms' cash at open and close and the owner's
  building subsidy (firm sites from the A3 receipts, firm-less sites from the
  counter delta). With A3 on, the L6a firm-cash closure adds capital,
  household sales and inputs.

Withheld income (`frame.withheld`) moves no money: it is the ordinary income
the wealth phase did not create because the person did paid work. Each
receipt row is attributed to the package that installed it - L6a crews, RS1
attached apprentices (version-2 crew members are L6a crew), PL3 granary crews,
PL3 workshop crews (RS2's workshop crews drawn from PL3's widened pool), RS2
workshop crews without PL3, PL1 woodcutters - and checked against each
package's own counter (`package_total`, `matches`; RS2's counter covers PL3's
workshop crews). While PL3 is active every RS2 workshop crew is a PL3
workshop crew, so a member only RS2 names was on a PL3 receipt dropped by its
64-row cap: such rows are counted in `unattributed_rows` and
`unattributed_pl3_dropped_rows`, never credited to RS2. `unattributed_rows`
and `conflicts` are 0 on every world checked. `retail_income_replaced` is
L6b's replaced farm income (also no money), shown whenever retail is active,
with or without a paid-work package (`paid_work_active` false: the paid-work
fields are null, not zero; `retail_income_replaced` null: retail off or not
observed this turn). L5 learning attendance, academy teaching and rural health
work withhold income too; they are registered (`withheld_learning`,
`withheld_teaching`, `withheld_health`) but not itemized in slice 1, so their
shares stay in `native_model`.

## Recorded limit RL7: separate granary and workshop income withholding

Class: evidence gap. Disposition (this slice): **resolved by attribution**.
`frame.withheld.recovery_crews` holds `granary`, `workshop`, PL3's own total
for the turn (the delta of its `income_replaced` counter), `difference` and
`closes`, plus PL3 receipt rows dropped by its 64-row frame cap that turn
(their members are unattributed, as above, and the split then does not close). Tested: offline (constructed) and on
template seed 7 (80 turns, both crew kinds in the same turn) and the
`hybrid_s42` 200-turn all-switch run (19 turns with both kinds); the split
closed on every turn.

## Continuity (the no-hidden-writer check)

`frame.continuity.status`:

- `exact`: the opening equals the previous closing bit for bit (every id's f32
  wealth and region): no writer between Phase 10 and the next Phase 2.
- `broken`: something wrote between them; `difference` (wealth), 
  `agents_difference`, `wealth_changed`/`region_changed` and up to 16 regions
  `[region, wealth change, people change]`. Dated in the log, totalled in
  `lifetime.discontinuity`. A keyed transfer injected between turns is
  detected (native test).
- `unchecked` with `reason`: `first_turn` (no closing yet, or the switch was
  turned on), `pool_reset` (a rebuilt pool: legacy state-file resume),
  `gap` (turns the ledger did not observe), `no_opening`.

## Record (`snapshot.livelihoods.wealth_accounting`)

Stage `A1`, `schema_version` 1, dated by `source_turn` (the completed turn):

```
{schema_version, stage: "A1", source_turn,
 units: {balance: "wealth_units", typed: "milli_units", treasury: "treasury_units", milli: 1000},
 frame: null | {
   turn, continuity: {status, reason, previous_close_turn, [wealth_changed, region_changed,
                      difference, agents_difference, regions, regions_dropped]},
   typed_complete,
   world: {open, close, delta, agents_open, agents_close, births, births_close, deaths,
           deaths_open, moved, moved_close, typed_in_milli, typed_out_milli, typed_net_milli,
           unlocated_in_milli, unlocated_out_milli, native_model, unplaced_agents},
   regions: [{region, open, close, agents_open, agents_close, migration_in, migration_out,
              births, births_close, deaths, deaths_open, typed_in_milli, typed_out_milli,
              native_model}],                       # regions with people or flows
   typed: [{channel, package, payer, observed, in_milli, out_milli,
            unlocated_in_milli, unlocated_out_milli}],  # active channels, declaration order
   closures: [{channel, check, lhs, rhs, closes}],
   withheld: null | {paid_work_active, rows, deducted, packages: [{package, rows, deducted,
                     ordinary, package_total, matches}], unattributed_rows,
                     unattributed_pl3_dropped_rows, unattributed_deducted, conflicts,
                     recovery_crews: null | {granary, workshop, total, difference, closes,
                     rows_dropped}, retail_active, retail_income_replaced},
   treasury: {created: {treasury_tax},
              tithe: {potential, at_threshold_after_tick, approximate: true, collected: null},
              to_households_milli, firm_cash, charged, sinks_milli, by_civ: [...]}},
 lifetime: {...}, counters: {...}, log: [{turn, kind, detail}], log_dropped,
 labels: {...}, parameters: {...}}
```

States a reader must keep apart (`wealth_accounting.record_status`, the
reference for viewer and analysis readers):

- **absent**: no record - the switch was never on, or is off in that turn;
- **malformed**: a record that is not this shape;
- **unobserved**: `frame` is null - the turn had no opening or no closing
  (unknown, not zero);
- **observed**: a frame; its zeros are recorded zeros. Inside a frame,
  `withheld` is null when neither a paid-work package nor retail is active, its
  paid-work fields are null when no paid-work package is active (not zero), a
  typed row with `observed: false` is an active package without this turn's
  frame (`typed_complete` is then false), and `tithe.collected` is always null.
  A failed closure (including "located flows do not exceed the package's
  total", whose unlocated flow is then negative) is shown on an observed
  frame, never read as malformed.

The viewer reads the record in `viewer/src/lib/wealthAccounting.ts`
(`readWealthAccounting`: absent, malformed with its reason, unobserved,
observed) and shows it in the Livelihoods panel
(`viewer/src/components/systems/WealthAccounting.tsx`).

## Checkpoints, resume and switches

Persisted: the last closing (digests, total, one sum and count per region),
the frame, lifetime totals, counters and the 64-entry log. The opening arrays
and counter baselines are transient within a turn (checkpoints are taken
between turns). An exact resume continues the check (`exact` at the first
resumed opening). A legacy state-file resume rebuilds the pool: the closing is
dropped with a dated `pool_reset` record and the next opening is `unchecked`.
`--no-wealth-accounting` on a resume ends it with a dated `switched_off`
record and drops the closing and frame (lifetime totals and the log are
kept); turning it on again starts `unchecked`. Outside `--agents hybrid` it is
refused at startup; a saved world with it on is refused on a non-hybrid
resume until `--no-wealth-accounting` is given; an exact resume refuses a
different agent mode (`--agents off`, the parser default, reads as not given
and continues the checkpoint's hybrid run).

Registered in `feature_catalog.REQUIREMENTS` (`--agents hybrid`), in
`batch_manifest.SIMULATION_ARG_KEYS` and omitted from manifests when unset.

## Identity guarantees (verified)

- Feature-off identity: `turn_speed_identity.py` 9 cases, 399 files, 0
  differences against `8abc1acb` (the original reference and the preceding
  `main`), each side with its own exported tree and extension; the explicit
  `--no-wealth-accounting` on `hybrid_s42` and `proc48_hybrid_s42`: 203 files,
  0 differences.
- Observer identity: with the switch on, every output except this record equals
  the switch off - six hybrid matrix cases (366 files) and the two all-switch
  cases (205 files) with only `wealth_accounting` removed: 0 differences; the
  raw comparison differs only in `chronicle_bundle.json` and `state.json`.

## Limits (slice 1)

- `native_model` is a residual, not itemized; slice 2 (a transient native
  observer, witness layers for `tick.rs`, `pool.rs`, `household.rs`,
  `ffi/mod.rs`) will split it into income by occupation, each withheld share,
  decay, the ceiling, births, and estates to spouse, children, overflow and no
  heir (audit D1, D2), and add a `strict` mode.
- Unlocated: granary procurement credits, L7 fares beyond the 64 kept
  households, domestic credit (net per turn only; signs within a turn cancel).
- The PL3 frame keeps 64 receipts; members of dropped receipts are
  unattributed (`unattributed_pl3_dropped_rows`, `rows_dropped`; 0 on every
  world checked).
- Typed transfers are integer milli-units applied to f32 balances (audit D4):
  the per-row rounding lands in `native_model`.
- The collected tithe is not observed; `at_threshold_after_tick` approximates
  it from the influence after the faction tick (see above).
- Development measurements only (below); no screen, no held seed.

## Evidence (development worlds, not a screen)

Development-only, 2026-11-06, source `4cdd2b45` (the ledger) on the
checkpoint-2/3 extension `101a4cd5...` (Rust identical to `8abc1acb`); no
preregistration, no held seed. Flags: the checkpoint-3 chain
(`--grain-reserves --public-grain-shipments --scholarship --techniques
--academy-services --grain-storage --food-allocation --workshops
--operating-wear --repair-projects --timber-stock --household-retail
--household-retail-boundary=paid_work --timber-supply --recovery-crews
--remittances`) plus `--wealth-accounting`, 200 turns; procedural 32 x 10.

| World | open (t0) -> close (t199) | sum of deltas | typed in / out (units) | typed net | native model | births / deaths (balances) |
| --- | --- | --- | --- | --- | --- | --- |
| template 23 | 98.0 -> 544.9 | +446.9 | 3,060.1 / 2,550.1 | +510.0 | -63.1 | 351 (175.5) / 461 (4,139.3) |
| procedural 7 | 236.0 -> 2,658.1 | +2,422.1 | 6,709.6 / 5,928.1 | +781.5 | +1,640.6 | 1,823 (912.7) / 1,925 (14,276.2) |

Typed flows by channel (units, in / out): template 23 - food purchases
1,843.4 / 1,843.4, remittances 601.2 / 706.7 (fee 105.5), PL3 granary wages
352.7, PL1 woodcut wages 202.5, RS2 workshop repair wages 36.3, procurement
24.0 (unlocated); procedural 7 - purchases 4,430.4 / 4,430.4, remittances
1,274.4 / 1,497.8 (fee 223.4), PL3 granary wages 694.2, PL1 260.0, RS2 42.7,
procurement 8.0. Withheld (no money): PL1 104.3 / 162.0, PL3 granary 34.6 /
47.8, PL3 workshop 11.7 / 6.3 (both kinds in the same turn on 64 / 51 turns).

Treasury side: created treasury tax 1,474 / 3,110 units, against 615.5 /
1,004.9 units paid from treasuries to households (RS2, PL3, PL1 wages and
procurement) and 593 / 1,001 units charged by RS2 and PL1. The clergy tithe's
potential was 1,287 / 4,386 units, of which about 502 / 627 fell to
civilizations whose clergy was at the threshold after the faction tick
(approximate collected tithe, also debited from nobody); an earlier draft of
this page reported the potential as created money. Retail replaced 2,154.4 /
3,386.3 units of farm income (withheld, no money), equal to the audit's figure
for its `CH_pw` arm. The audit's independent estimates for the same flags (its
`CH_pw` arm, section 2.1) were a change of +425 and +2,368 with typed net
+510 and +782.

Every turn of both worlds: continuity `exact` after the first, every closure
held, no unattributed or doubly named paid-work row, the RL7 split closed.
Verification of this slice (identities above; resume): `checkpoint_identity`
with these flags `hybrid_s42_long` PASS at 19 resume points and
`proc32_hybrid_s11` PASS at all 39 (twelve inside a live woodcutting
expedition, 17 after a retail settlement turn, granary crews working at 20 of
them). Overhead on the all-switch `hybrid_s42` case: wall time unchanged
within noise, bundle 8.0 -> 8.6 MB over 200 turns.
