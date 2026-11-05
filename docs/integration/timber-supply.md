# Timber supply (PL1, `--timber-supply`, default off)

Productive-recovery phase, package PL1
([phase plan](../superpowers/roadmaps/productive-recovery-phase.md), section 2
"PL1 timber supply"). This page records what the package implements, the two
design decisions the lane was asked to make, the native seam, the evidence and
the open risks. Nothing here is calibrated or scientifically qualified, and
nothing was run on a held seed.

Enable with `--agents hybrid --repair-projects --timber-stock --timber-supply`
(RS2 itself needs `--workshops` or `--grain-storage`, and grain storage needs
`--grain-reserves`). `--timber-supply-mode` chooses `supply` (the default) or
`cost_only`, the cost-retaining control. A world that never enabled the switch
has no sub-state, snapshot key, checkpoint flag, manifest entry or native
column. `--no-timber-supply` abandons live expeditions and releases every store
to its region's stockpile.

Code: `src/chronicler/timber_supply.py`, `src/chronicler/timber_supply_state.py`;
seams in `repair_projects.py` (the store), `timber_stock.py` (`stand`,
`settled_accounts`), `economy.py` (the result columns) and the native
`economy.rs` / `ffi/mod.rs` (the woodcut columns).

## Why

The PL0 diagnosis D1 found that RS2's `no_timber` stalls (98% of all stalls) are
caused by production, not placement: in 54% the civ has no timber slot at all,
in 8% its forests are healthy but nobody works them. D3 found that with timber
ample, granary condition rises in 14 of 14 worlds, and that RS2 then needs about
1.4 (template) and 3.8 (procedural) timber a turn per world beyond the free
stock. PL1 adds harvest where forest stands and carries it to the repairs, with
its labour cost on the community that needs the timber and its harvest through
the forest's own L3 account.

## Two decisions

### 1. Reserving and paying people who work away from home

The crew stays in the native pool at home: no agent moves, no residence
changes, no new native state. Only the home economy loses their labour:

- **Reservation.** Each turn of the expedition, in Phase 2, each member is
  reserved for the whole turn (`reserve_work(turn, 3, [(id, 1.0)])`, category
  `repair`) after every earlier work consumer of the turn (L1 crews, RS1 seats,
  RS2 crews, health care, teaching). The registry is region-blind, so the
  reservation needs no notion of where the work is done. A member who already
  holds work that turn leaves the crew (`other_work`); reservations are made
  one member at a time, so one refusal does not cost the others theirs.
- **Pay.** Wages are paid by stable id through `transfer_wealth` (purpose 3
  `repair_wage`, batch `WAGE_BATCH` = 1; RS2 pays batch 0), which is also
  region-blind. The same share (1.0) is armed with `extend_paid_work`, so the
  next wealth phase withholds that share of ordinary income and the wage
  replaces it. The treasury pays whole units once per civ and turn, with the
  sub-unit remainder prepaid, as RS2 does.
- **Home labour.** The crew's farmers' farm labour is sent as headcount in the
  native column `woodcut_labor_away` of the **home** region: 1 for a rural
  farmer, `URBAN_FARM_LABOR[rank]` for a farmer living in a city of the region
  (exactly what `cities.economy_columns` counted for them), 0 for a merchant,
  scholar or priest. The economy removes at most the region's farm labour
  (after the city and care adjustments, before granary work) and returns what
  it removed (`woodcut_labor_away_delivered`).
- **Forest labour.** The crew's headcount goes in the native column
  `woodcut_labor` of the **forest** region, which no resident's count or income
  sees; only the slot's output changes.
- **What the pool still sees.** Because the people stay at home, the native
  agent tick can still move, kill or enlist them. Every Phase 2 and every
  post-tick Phase 10 checks each member against the snapshot: absent (`died`),
  resident elsewhere (`migrated`), Soldier or on an army roster (`enlisted`),
  away on a merchant trip (`on_trip`). A dropped member is dated on the
  expedition. Members reserved in Phase 2 cannot be drafted in Phase 5
  (`select_recruits` skips registry holders).

### 2. A region with several timber slots

The crew works the region's **first timber slot** (lowest slot index). The
native kernel applies the column to that slot only (`economy::woodcut_slot`),
and Python plans, guards and accounts with the same rule. Other timber slots of
the region are untouched. No development world has a region with a second
timber slot at generation (template 1, 3, 7, 9, 11, 23, 42; procedural 7, 11,
13, 17, 21, 31, 302, 303: 0 such regions); a slot that changes type mid-run ends
the cutting (`forest_lost`). Splitting the crew across slots would need a slot
index column and was not worth a third column for a case that does not occur.

## Mechanism

### Need (Phase 10, after RS2 opened this turn's projects)

For each region with open RS2 projects of a controlling civ:

- **want**: what the projects could use in one turn at their per-turn caps:
  a granary's `GRANARY_WORK_PER_TURN` (4) work, a workshop's `MAX_CREW` (4)
  repairers at its diverted share and rate (1 with RS1 active, else RS2's
  `UNQUALIFIED_RATE`), each capped at the project's remaining work, times its
  timber rate;
- **free**: the timber RS2 sees (`_free_timber`: stockpile less merchant
  commitments, plus the store);
- **in transit**: the cargo of the region's live expeditions after the way
  home's decay;
- **gap** = want - free - in transit.

A gap of at least `MIN_GAP` (0.5) without a live expedition for the region
launches one, or is refused with the first failing check:

| Refusal | Meaning |
| --- | --- |
| `no_forest` | no timber slot in a region the civ controls or nobody controls (never another civ's) is reachable on the region graph (`Region.adjacencies`, sea lanes included) |
| `too_far` | none within `MAX_HOPS` hops |
| `forest_depleted` | every one in range has an L3 stock below `GUARD_SHARE` of its effective capacity |
| `forest_busy` | every healthy one in range is already being cut (one expedition per forest) |
| `no_crew` | nobody in the home region is eligible |
| `no_coins` | the projected treasury cannot pay the whole expedition at full crew plus the civ's other live expeditions' remaining wages |

`forest_busy` is not in the plan's list; it is the honest reason when the only
healthy forest is taken, and it keeps two crews off one stand.

The forest chosen is the in-range healthy free one with the fewest hops, then
the larger standing stock, then the lower region index.

### Who goes

At most `CREW_CAP` living adults (age at least 20) resident in the home region,
of any occupation but Soldier, not on an army roster, not on a merchant trip and
not on another crew: eligible RS3 veterans first
(`veteran_reintegration.priority_ids`; none in RS3's `record_only`), then by
ascending stable id. Veterans on a crew (by open RS3 record) are noted
`placed:repair` with `{expedition, region, forest}` for each turn they worked.

### Schedule, cutting and cargo

- **Legs.** `outbound`: one turn per hop. `cutting`: `CUT_TURNS` turns.
  `returning`: one turn per hop. A forest in the home region has neither
  travel leg. Every leg is paid, reserved and takes the home labour; only
  `cutting` in `supply` mode sends `woodcut_labor`.
- **Guard.** Before each cutting turn: a stand below `GUARD_SHARE` of capacity
  (`forest_depleted`) or a forest that fell to another civ or stopped being
  timber (`forest_lost`) ends the cutting, and the crew turns home with what it
  has cut. A forest lost before the crew got there abandons the expedition.
- **Cargo.** The crew's marginal harvest (`woodcut_output`) is taken on board
  after each cutting turn. On arrival (Phase 10, after the crew is observed)
  the cargo loses the economy's timber transit decay (0.01) per hop and is
  credited to the home region's store.

### The store and RS2

- RS2's `_free_timber` reads the store ahead of the stockpile
  (`max(0, stock - committed) + store - held`; the old expression exactly
  when the store is empty or the switch is off).
- RS2's holds (before the native economy) take from the store first, the rest
  from the stockpile and its packed column; unused held timber is returned to
  the stockpile first (its part of the hold), then to the store (the store was
  used first); a failed Phase 2 puts each part back where it came from.
- The store is not in the native stockpile, so merchants, crafts, the stock cap
  and conquest never see it: nothing else can take it. It does not decay (a
  declared simplification; it is short-lived).
- Timber left in a region without an open RS2 project at Phase 10 is released
  to the region's stockpile, recorded (`released`, store row).

### Endings

Delivered; or abandoned with the cargo lost: `crew_lost` (no member left),
`no_coins` (a turn's wages cannot be paid), `home_lost` (the home region
changed hands or lost its controller), `forest_lost` (before arrival),
`pool_reset` (a rebuilt native pool: saved ids name strangers; stores are kept)
and `switched_off`.

### `cost_only`

The same need, launches, crews, travel, schedule, reservations, wages and home
labour removal; `woodcut_labor` is zero, so nothing is cut, no stock is debited
and no timber is delivered. Because it supplies nothing, its need persists and
it keeps launching expeditions: it is the cost of the mechanism without its
benefit.

## Native seam (`economy.rs`, `ffi/mod.rs`)

- Two optional Float32 region columns, both or neither, non-null, finite and at
  least zero, validated before any simulator mutation:
  `woodcut_labor_away` (headcount farm labour away from the region's land) and
  `woodcut_labor` (headcount on the region's first timber slot; refused on a
  region without one).
- `tick_economy_core_with_granary_work` is now a wrapper of
  `tick_economy_core_with_woodcut(..., None)`; `None` and all-zero columns give
  bit-identical outputs.
- Away labour is removed from `headcount_labor` before granary work:
  `delivered = min(request, headcount)`.
- The crew's effective labour on the slot:
  - with `slot_curves` (`split_labor_on_slot_curves`): the slot's own curve at
    the residents' headcount on the slot (the food-first split, recomputed)
    plus the crew: `E_slot(h + c)`;
  - without (the linear path, the farm curve on all farm labour): the residents'
    effective labour on the slot plus the crew's marginal effective labour on
    the region's curve, `E(H + c) - E(H)` (constant returns without a curve).
- `woodcut_output` = the slot's total with the crew (under its production cap:
  the L3 cap, tightened by L8, shared with the residents, who take theirs first)
  less the residents' output. The slot's `slot_output` is the total, so L3's
  `finish_phase2` debits the crew's harvest from the stock. `per_good_production`
  and the category production keep the residents' output only: the harvest never
  enters the forest's stockpile, prices or farm income.
- `ConservationSummary.production` includes the harvest (it is slot output; the
  production ledger's check still holds), and a new `woodcut_outflow` carries it
  out, so production - woodcut_outflow is what was stocked.
- Result columns `woodcut_labor_away_delivered`, `woodcut_output` (region batch)
  and `woodcut_outflow` (conservation batch) are appended only when the inputs
  were present.
- The work-injury proxy (`health_work.worked`) and `realized_extraction` read
  `slot_output` as before; timber is not a depletable resource in the ecology,
  so the latter changes nothing.

## Declared constants (uncalibrated; none tuned)

| Name | Value | Reason |
| --- | --- | --- |
| `CREW_CAP` | 4 | RS2's `MAX_CREW`, the named repair crew size the phase already declares |
| `MAX_HOPS` | 2 | a hop is a turn each way (a merchant carries one load one hop a turn); the longest expedition is 2 x 2 + 3 = 7 turns, under a third of a year of travel |
| `CUT_TURNS` | 3 | one season (a turn is a month) |
| `GUARD_SHARE` | 0.5 | L3's logistic regrowth peaks at (1 - `SEED_FRACTION`) / 2 = 0.475 of capacity; below about half a further cut slows the stand's own recovery |
| `MIN_GAP` | 0.5 | RS2's `MIN_WORKER_TIMBER`: half a turn of one repairer's timber |
| `SHARE` | 1.0 | the expedition takes the whole turn |
| wage | 500 milli per person-turn | RS2's `WAGE_PER_WORK` (L6a's rate) for the whole turn |
| transit decay | 0.01 per hop | the economy's `TRANSIT_DECAY["timber"]` |

## Records (`snapshot.livelihoods.timber_supply`, schema 1, stage `PL1`)

Copied completed-turn observations dated by `source_turn`:

- `expeditions` (live) and `closed` (the last 32): home, forest, slot, hops,
  stage, crew (launched and current), veterans, need, cargo, cut, cut turns and
  why cutting ended, person-turns, wages, income withheld, farm labour asked
  and removed, delivered, lost, dated drops and history;
- `receipts` (one per worked expedition this turn: stage, crew, drops, farm
  labour away, crew labour, cut, cargo, L3 stock before and after and capacity
  while cutting, wages, income withheld) and `ledger` (per civ wages, charge
  and prepaid): `null` without a Phase 2 that turn (unknown, not zero);
- `stores` (per region: opening, held by RS2, returned, delivered, released,
  closing) and `needs` (per region: want, free, store, in transit, gap and
  `supplied` / `expedition` / `launched` / `refused` with its reason);
- `store`, `prepaid`, `counters` (lifetime: need, launches, refusals and
  abandonments by reason, drops by reason, cut, lost, delivered, released, wages,
  income withheld, home labour, crew labour, crew-turns by stage) and
  `parameters`.

## Closure (checked every turn, raises before committing)

- Per civ: `charged x 1000 + prepaid_before == wages_applied + prepaid_after`,
  `wages_applied + residual == wages_due`, balances in [0, 1000).
- Per expedition: `cut == cargo + delivered + lost`.
- Per store region: `opening - held + returned + delivered - released == closing`.
- The economy's `woodcut_output` is non-zero only where a crew cut, and
  `woodcut_labor_away_delivered` never exceeds the request.
- A turn settles once; the wages' `(turn, purpose, batch)` key applies once; a
  failed Phase 2 charges nothing and puts store holds back; a failed agent tick
  cancels the paid share; the turn in flight is never pickled.

## Lifecycle within a turn

1. Phase 2: L3 offers its caps; RS2 plans and holds timber (the store first);
   PL1 re-checks each live expedition, reserves its crew, plans its wages and
   appends the woodcut columns (only when a crew works).
2. The native economy runs.
3. L3 settles the stand (its extraction includes the crew's harvest); RS2 pays
   and returns unused timber (stockpile part first); PL1 validates the woodcut
   results, pays once, takes the harvest on board, advances the schedule and
   arms the paid share; veterans are noted.
4. The agent tick runs; the shared paid-work receipt gives the income withheld.
5. Phase 10 (before reserves, after RS2's lifecycle): crews observed, arrivals
   delivered to the store, stores without a project released, need planned and
   expeditions launched. Phase 10: the frame is dated.

## Files and seams

- Owned: `timber_supply.py`, `timber_supply_state.py`,
  `tests/test_timber_supply.py`, `tests/test_timber_supply_native.py`.
- Seams, each inert with the switch off:
  - `repair_projects.py`: `_free_timber` reads the store; the hold, return and
    rollback loops take and give back the store's part (`_store`,
    `_take_store`, `_return_store`, `_restore_store`, `_Turn.store_holds`);
  - `timber_stock.py`: read-only `stand` and `settled_accounts`;
  - `economy.py` (**pinned**): `EconomyResult.woodcut_labor_away_delivered`,
    `woodcut_output` and `conservation["woodcut_outflow"]`, read only when the
    result columns exist;
  - `chronicler-agents/src/economy.rs` and `ffi/mod.rs` (**pinned**): above.
- Registry (append only): `LIVELIHOODS_SWITCHES`, `LivelihoodsState`,
  `livelihoods.py` (choices, arg keys, help, prerequisite, choice field),
  `feature_catalog.REQUIREMENTS`, `batch_manifest.SIMULATION_ARG_KEYS` and its
  omit-when-unset tuple (**pinned**), `tests/test_batch_manifest.py`
  (**pinned**).
- `tests/test_recovery_skills_wiring.py`: its "RS switches are last" slices are
  now position-based (`[9:14]`, `[8:13]`, `[17:27]`) so later phases can append.
- `timber_supply.pending_bills(world)` exposes this Phase 2's planned wages for
  planners that run after PL1; nothing reads it yet.

## Evidence

### Native build

- Extension SHA-256 `fdcb0ca0f5d2c4ea2326579b1ce4ce55d647735928ea9900b9ff2d2d20f082db`, built with
  `/home/user/wt/tools/build_native.sh` from the Rust of `7c16e9ce` (no Rust file
  changed after it), into `~/.venvs/native-pl1` (Python 3.13, Linux). The phase
  head's extension is `6c675042…`.
- `check_python_env.py --expect native`: PASS (compiled submodule and classes).

### Tests

| Command | Result |
| --- | --- |
| `cargo test --locked --manifest-path chronicler-agents/Cargo.toml --lib woodcut` | 9 passed |
| full `cargo test --locked` (debug info off: `CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0`) | 38 suites, 1,264 passed, 0 failed, 2 ignored |
| `pytest tests/test_timber_supply.py` (offline, stand-in native) | 36 passed, 0.4 s |
| `pytest tests/test_timber_supply_native.py` (real extension `fdcb0ca0…`) | 4 passed, 5 s |
| `pytest` RS2, L3, L8, wiring, catalog, manifest, shard modules | all pass |
| `scripts/run_python_oracle_checks.py` | FAIL, stopping at the first chunk holding a witness test (expected, below) |
| every lane chunk run the same way without stopping (a scratch driver: the runner's command, guard and 110 s limit per chunk) | 61 chunks, guard PASS in all; 6,341 passed, 69 skipped; the only failures are the 9 witness tests below (8 chunks); the new `timber-supply` chunk 36 passed in 2 s; slowest chunk 52.7 s |

Rust (`economy::woodcut_tests`, `ffi::tests::woodcut_ffi_*`):

- absent and all-zero columns keep every region, civ, observability and
  conservation output bit for bit, on both labour paths, with and without
  granary work; at the FFI the appended columns are the only difference and the
  pool's exact checkpoint encoding is unchanged;
- away labour is delivered up to the headcount; five away is bit-identical to
  seven farmers at home; the crew leaves before granary work;
- the marginal harvest on the slot-curve path (`E(h + c) - E(h)` on the forest's
  curve), on the linear path (`E(H + c) - E(H)` of the farm curve) and on an
  uninhabited forest;
- an L3 cap shared with the residents: the crew takes what the cap leaves, nothing
  when the residents reach it;
- the harvest is in `slot_output` but the forest's stockpile, prices, food ledger
  and farm signals are bit-identical to the run without the crew;
- conservation: `woodcut_outflow` is the sum of `woodcut_output`, production less
  the outflow is the crew-free production, and every other flow is unchanged;
- invalid inputs (one column alone, crew without a timber slot, negative, NaN,
  null, Float64) are refused before any mutation.

Offline (`tests/test_timber_supply.py`): feature off (no state, column, snapshot
key or flag; RS2's old expression); prerequisites and modes; the need row and a
named crew of eligible residents; veterans first and noted; every refusal
(`no_forest` including another civ's forest and an unreachable one, `too_far`,
`forest_depleted`, `forest_busy`, `no_crew`, `no_coins`); an uncontrolled forest;
reservation, keyed wages, withholding and the whole-unit charge with the prepaid
half unit; a city farmer's share; the full schedule with decay into the store and
RS2's hold from the store first; stockpile-first returns; release without a
project; `cost_only`; the guard ending the cutting; death, migration, enlistment,
an army roster, a merchant trip and other work; cargo lost with the crew; the
asset completing mid-expedition; forest and home controller change; the forest
lost before arrival; pool reset; switching off; a failed economy tick and a failed
agent tick; duplicate, stale and misplaced results; closure refusals; the wage
ceiling; dated and unknown snapshots; exact JSON and pickle round trips; a resume
from a pickle equal to the uninterrupted run.

Real extension (`tests/test_timber_supply_native.py`):

- template seed 3, 60 turns, `CHRONICLER_CHECK_RESOURCES=1`: every crew member
  holds a category-3 whole-turn reservation and is a resident adult non-soldier of
  the home region, with no registry conflicts; every wage transfer moves real
  wealth once (a repeated key is refused); `woodcut_outflow` equals the sum of
  `woodcut_output`; the L3 extraction of each cut slot is the economy's slot output
  and includes the cut; wages, stores and expeditions close; RS2 held timber from
  the store;
- a constructed world with an uninhabited forest one hop away: each cutting
  turn's L3 extraction equals the crew's harvest exactly, the stock moves by
  exactly that, delivery is the cut times 0.99, and RS2 holds from the store the
  next turn;
- the same world in `cost_only`: the first expedition's stages, crews, farm
  labour and wages match `supply`; nothing is cut, extracted or stored;
- exact checkpoint resume at turn 52 of template seed 3 inside a live
  expedition: history, world state and `state.json` byte-identical.

### Feature-off identity

`scripts/turn_speed_identity.py`, phase head `bec63b5b` with `6c675042…`
against `7c16e9ce` with `fdcb0ca0…` (each side's `src` exported with `git
archive`, the imported tree and extension recorded in each `which.txt`):

- cases `hybrid_s42`, `hybrid_s7`, `proc48_hybrid_s42`, `off_s42`: 323 files, 0
  differences;
- `hybrid_s42`, `proc48_hybrid_s42` with every prerequisite on and the switch off
  (`--grain-reserves --public-grain-shipments --grain-storage --workshops
  --repair-projects --timber-stock`): 205 files, 0 differences.

The commit after `7c16e9ce` changed tests, enrollment and `pending_bills` only.
Template seed 1 with the switch on never launched an expedition, and its whole
history and world state equal the run without the switch (apart from the
package's own key).

### Development worlds (natural, 200 turns)

Arms: `base` (prerequisites only), `supply`, `cost_only`, each with
`--agents hybrid --simulate-only --grain-reserves --public-grain-shipments
--grain-storage --workshops --repair-projects --timber-stock`
(`PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`; procedural worlds `--worldgen procedural
--regions 32 --civs 10`). Single worlds: trajectories diverge once spending
differs, so differences between arms are not effect estimates.

| World | Launched (delivered) supply / cost only | Cut, delivered, lost, released (supply) | RS2 used from store | Wages, coins: supply / cost only | Farmer-turns away (supply) | RS2 `no_timber` stalls: base / supply / cost only | RS2 timber used: base / supply / cost only | Granary mean condition: base / supply / cost only | L3 extraction: base / supply / cost only |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | 0 / 0 | none | 0 | 0 / 0 | 0 | 790 / 790 / 790 | 40.8 / 40.8 / 40.8 | 0.301 / 0.301 / 0.301 | 70.6 (all) |
| T3 | 10 (9) / 19 (13) | 15.8, 15.1, 0.7, 0 | 15.1 | 39.5 / 75.0 | 40 | 738 / 797 / 826 | 106.2 / 97.7 / 88.1 | 0.383 / 0.366 / 0.370 | 316.5 / 303.0 / 295.3 |
| T11 | 8 (8) / 20 (19) | 18.2, 18.2, 0, 1.9 | 16.3 | 32.5 / 72.0 | 34 | 1,043 / 775 / 885 | 94.1 / 101.7 / 90.0 | 0.342 / 0.363 / 0.333 | 245.7 / 273.8 / 247.0 |
| T23 | 32 (18) / 46 (23) | 209.6, 158.8, 38.5, 70.1 | 88.8 | 171.7 / 213.0 | 162 | 655 / 547 / 670 | 118.5 / 209.5 / 116.9 | 0.368 / 0.526 / 0.386 | 131.7 / 350.4 / 126.0 |
| P7 | 43 (28) / 68 (48) | 120.3, 105.0, 15.3, 18.9 | 84.8 | 262.0 / 369.0 | 243 | 1,885 / 1,859 / 2,083 | 350.1 / 426.9 / 307.7 | 0.454 / 0.488 / 0.417 | 677.5 / 898.7 / 706.2 |
| P13 | 37 (26) / 40 (25) | 135.6, 112.3, 23.3, 77.1 | 35.2 | 207.5 / 237.5 | 200 | 2,163 / 1,958 / 2,263 | 425.4 / 449.2 / 469.7 | 0.399 / 0.454 / 0.448 | 1,442.0 / 1,360.4 / 1,454.2 |
| P21 | 64 (42) / 75 (50) | 399.4, 309.8, 85.9, 109.0 | 200.8 | 380.5 / 448.0 | 262 | 2,140 / 1,781 / 1,703 | 293.9 / 489.7 / 379.6 | 0.386 / 0.531 / 0.469 | 724.7 / 1,116.0 / 817.9 |
| P31 | 50 (25) / 55 (37) | 266.4, 157.5, 104.7, 30.0 | 127.5 | 281.5 / 335.0 | 252 | 2,449 / 2,377 / 2,400 | 306.9 / 381.3 / 303.8 | 0.327 / 0.401 / 0.348 | 519.0 / 896.8 / 728.1 |

- **Where it acts.** Template worlds have one or two timber regions, so most
  civs have no forest of their own or of nobody: `no_forest` is the largest
  refusal in every template world (291-714 region-turns) and T1 never launches
  (`no_forest` 714, `forest_depleted` 122: its one forest is cleared below the
  guard). Procedural worlds refuse mostly `no_forest`, `too_far` (P21 484, P31
  826) and `forest_depleted` (P13 1,517). Cross-civ timber is out of scope.
- **Timber delivered.** 15-310 timber per world over 200 turns in `supply`, 0 in
  `cost_only`. Crews cut 0.2-1.3 timber per person-turn while cutting (D1's
  single-farmer gain was 0.19-0.75). RS2's timber use rises over `base` in six
  of seven acting worlds (not T3; T23 118.5 to 209.5, P21 293.9 to 489.7) and
  over `cost_only` in six of seven (not P13).
- **RS2 stalls and condition.** `no_timber` stalls fall below `cost_only` in six
  of seven acting worlds (not P21) and mean granary condition is above
  `cost_only` in six of seven (not T3, 0.366 against 0.370); the largest gains
  are T23 (0.386 to 0.526) and P21 (0.469 to 0.531). The granaries still end
  worn in most worlds: timber is one of several limits (coins, labour, war).
- **Losses.** Transit decay costs 1-3 timber per world. Most of the "lost"
  column is the cargo of expeditions that ended without delivering: crews lost
  to migration, death, enlistment or trips (`crew_lost`, T23 36.0, P21 69.0) and
  turns the treasury could not pay (`no_coins`, P31 14 expeditions, 76.2). Crew
  churn is high because the people stay in the pool at home: 12-144 member drops
  per world in `supply`, `migrated` the most common reason.
- **Home food cost (inferred, not measured).** 34-262 farmer-turns left the home
  land in `supply` (40-358 in `cost_only`, which keeps launching). At D1's
  0.27-1.02 food lost per farmer moved off food, that is about 9-267 food per
  world over 200 turns, against 11,000-65,000 food produced in the world. The
  bundle does not separate the counterfactual harvest, so no direct number is
  claimed.
- **L3 stock.** Expeditions add to the stands' extraction (T23 131.7 to 350.4, P31
  519.0 to 896.8). The guard holds: the lowest stock share after any cutting turn
  is 0.51-0.78 of capacity, and `forest_depleted` refuses or ends cutting below
  half.
- **Wages.** 32.5-380.5 coins per world over 200 turns in `supply` (500 milli a
  person-turn), more in `cost_only` (72-448), which pays for expeditions that
  supply nothing.

Driver and summary scripts were kept outside the repository (scratch); the
commands are the arms above.

## Pinned edits (witness layers for the lead)

| File | Edit | Witness tests that now fail |
| --- | --- | --- |
| `chronicler-agents/src/economy.rs` | `WoodcutInput`, `woodcut_slot`, `woodcut_slot_labor`, the `tick_economy_core_with_woodcut` wrapper split, two result fields, `ConservationSummary.woodcut_outflow`, tests | academy, crisis, food-accounting, livelihoods L1A layers |
| `chronicler-agents/src/ffi/mod.rs` | parse the two columns, the timber-slot check, call the woodcut core, append the result and conservation columns, tests | academy, crisis, food-accounting, household, L1A, L2, L5, L6, L7, RS0, RS4, RS5, S1R layers |
| `src/chronicler/economy.py` | two `EconomyResult` fields and their parse, `conservation["woodcut_outflow"]` | academy, crisis, food-accounting layers |
| `src/chronicler/batch_manifest.py` | two `SIMULATION_ARG_KEYS` and the omit-when-unset tuple | academy, crisis, household, information, L0, L5-L9, RS0, public grain shipments layers |
| `tests/test_batch_manifest.py` | the expected key set | L0, L5-L9, RS0 layers |

Failing witness tests (9, all from these edits; no fixture was touched):
`test_academy_candidate_witness::test_academy_candidate_projects_exact_reviewed_sources_and_rejects_mutations`,
`test_crisis_candidate_witness::test_candidate_projects_exact_reviewed_sources_and_rejects_mutations`,
`test_food_accounting_witness::test_food_layer_projects_exact_source_and_rejects_mutations`,
`test_household_mobility_witness::test_household_candidate_projects_exact_reviewed_sources_and_rejects_mutations`,
`test_information_candidate_witness::test_information_candidate_projects_exact_reviewed_sources_and_rejects_mutations`,
`test_livelihoods_sprint_witness::test_projection_reaches_each_layer_parent_and_the_baseline`,
`test_livelihoods_sprint_witness::test_mutations_are_rejected_in_strict_mode_and_passed_on_otherwise`,
`test_public_grain_shipments::test_composition_inverse_is_literal_complete_and_refuses_unrelated_edits`,
`test_health_care_policy::test_care_codec_source_binding_preserves_reviewed_native_and_python_phase_witnesses`.

## Limits and open risks

- **Cargo lost on abandonment.** An expedition that ends without delivering
  loses its whole cargo; in P31, P21 and T23 that is 39%, 22% and 18% of the cut.
  A partial delivery (the members left carry it home) or wages paid as far as
  the treasury allows would change this; neither is built.
- **Crew churn.** The crew stays in the pool at home, so native migration,
  death, drafting between reservations and trips take members away mid-trip.
  That is honest about the model, and it makes expeditions fragile.
- **Placement order.** PL1 reserves after the workshop, RS1 and RS2 planners, so
  an L1 crew can take an expedition member who is in a workshop city that turn
  (`other_work`, up to 58 drops per world). Reserving earlier needs a seam in
  `workshops.py` or `repair_projects.before_crews`, not done.
- **Wages outside L9 and later planners.** Expedition wages are not under the L9
  `repairs` envelope, and planners that run after PL1 in Phase 2 do not see them
  yet (`pending_bills` is provided for the lead to wire).
- **Not modelled.** The crew's city craft time; storage decay of the store; a
  second timber slot in a region; the work-injury proxy of the forest region
  (the crew's harvest marks it worked).
- **`cost_only` keeps launching.** It supplies nothing, so its need persists; its
  costs are therefore larger than `supply`'s, by design of the control.
- **Viewer.** No reader or panel (PL5).
- No held seed, 200-seed or procedural qualification gate was run.
