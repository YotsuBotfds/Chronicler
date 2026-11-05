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

### A turn the civ cannot pay: recall

If the controller's projected treasury cannot pay a turn's wages (after every
bill planned earlier in Phase 2), the expedition is **recalled**, not ended:

- outbound: the crew turns back and walks the hops it has travelled;
- cutting: the cutting ends (`cut_end` `recalled`) and the crew walks home with
  its cargo;
- a crew already at home (a forest in the home region, or recalled before the
  first hop) arrives at once and delivers in that Phase 10, unpaid and
  unreserved.

Every return-leg turn the civ cannot pay is walked **unpaid** (`unpaid_turns`,
receipt `unpaid`): the members are still reserved and away, their farm labour
still leaves the home land and their ordinary income is withheld, but no wage
is paid or charged. Only those travel turns are unpaid; nobody cuts on one. A
return turn the civ can pay again is paid as usual. The launch check (the whole
expedition payable at launch) is unchanged, so recalls come from treasuries
that fell after launch.

### Lost members and endings

A dropped member leaves the crew; the expedition goes on while at least one
member remains. It ends without delivering only when:

| End | When |
| --- | --- |
| `crew_lost` | no member is left (observed in Phase 2 or after the agent tick) |
| `home_lost` | the home region changed hands or lost its controller |
| `forest_lost` | the forest fell to another civ before the crew got there (no cargo yet) |
| `pool_reset` | a rebuilt native pool: saved ids name strangers (stores are kept) |
| `switched_off` | `--no-timber-supply` |

**Cut timber never vanishes.** The cargo of an expedition that ends without
delivering is deposited in the **forest region's** stockpile as commons and
recorded `abandoned` (per expedition, a dated `deposits` row and the
`abandoned_cargo` counter). No position is tracked on the way home, so a crew
lost on the return leg also leaves its cargo at the forest. A deposit is made
after the economy's stockpile write-back (Phase 2 settlement or Phase 10); one
caused by a pool rebuild, which can be noticed after the economy batch was
packed, waits in `pending_deposits` until that turn's Phase 10. Only transit
decay is a loss. `no_coins` stays in the declared end reasons but no longer
ends an expedition.

### `cost_only`: matched per expedition, not in total

The same need, launches, crews, travel, schedule, reservations, wages, recalls
and home labour removal; `woodcut_labor` is zero, so nothing is cut, no stock is
debited and no timber is delivered.

The control is **asymmetric in total**. Because it supplies nothing, its need is
never met and it keeps launching expeditions, so over a run it pays more and
takes more labour than `supply` (see the screens below). What it matches is the
cost of **one expedition**: the same crew rule, schedule, wage, home labour
removal and recall rule, as RS5's `cost_only` matched the cost of each
protection decision rather than the run's total. Comparisons of cost should
therefore be made per expedition: every ended expedition adds its wages,
person-turns, farm labour away, unpaid turns, cut and delivery to the `ended_*`
counters, and the snapshot reports their means (`per_expedition`).

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
  and removed, delivered, lost (transit decay), abandoned (deposited as
  commons), unpaid turns, the recall turn, dated drops and history;
- `receipts` (one per worked expedition this turn: stage, crew, drops, farm
  labour away, crew labour, cut, cargo, L3 stock before and after and capacity
  while cutting, wages, income withheld, whether the turn was unpaid or
  recalled) and `ledger` (per civ wages, charge
  and prepaid): `null` without a Phase 2 that turn (unknown, not zero);
- `stores` (per region: opening, held by RS2, returned, delivered, released,
  closing) and `needs` (per region: want, free, store, in transit, gap and
  `supplied` / `expedition` / `launched` / `refused` with its reason);
- `deposits` (the frame turn's abandoned cargo: turn, expedition, region,
  timber) and `per_expedition` (means over ended expeditions: wages,
  person-turns, farm labour away, unpaid turns, cut, delivered);
- `store`, `prepaid`, `pending_deposits` (state only), `counters` (lifetime:
  need, launches, recalls, unpaid turns, abandoned cargo, refusals and
  abandonments by reason, drops by reason, cut, lost, delivered, released, wages,
  income withheld, home labour, crew labour, crew-turns by stage) and
  `parameters`.

## Closure (checked every turn, raises before committing)

- Per civ: `charged x 1000 + prepaid_before == wages_applied + prepaid_after`,
  `wages_applied + residual == wages_due`, balances in [0, 1000).
- Per expedition: `cut == cargo + delivered + lost + abandoned`, with `lost` the
  transit decay alone.
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
| `pytest tests/test_timber_supply.py` (offline, stand-in native) | 42 passed, 0.5 s (8 of them fail on `af745ee0`, the old destroy-the-cargo rule) |
| `pytest tests/test_timber_supply_native.py` (real extension `fdcb0ca0…`), on `308422f2` | 4 passed, 6 s |
| `pytest` RS2, L3, L8, wiring, catalog, manifest, shard modules | all pass |
| `scripts/run_python_oracle_checks.py` | FAIL, stopping at the first chunk holding a witness test (expected, below) |
| every lane chunk run the same way without stopping (a scratch driver: the runner's command, guard and 110 s limit per chunk), on `af745ee0` | 61 chunks, guard PASS in all; 6,341 passed, 69 skipped; the only failures are the 9 witness tests below (8 chunks); slowest chunk 52.7 s |
| `timber-supply` chunk on `308422f2` | 42 passed |

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
asset completing mid-expedition; forest and home controller change (the home
lost on the way: cargo deposited at the forest); the forest lost before
arrival; pool reset, and a rebuild noticed after packing (the deposit waits for
Phase 10); a whole crew dying out at each stage (outbound with nothing cut,
cutting and returning: the cargo deposited in the forest region's stockpile,
nothing lost); a partly lost crew going on and delivering; an unpayable turn
recalling the crew home with its cargo (walked unpaid: reserved, away, income
withheld, no wage), a recall on the way out turning back, and one at a home
forest arriving at once; switching off; a failed economy tick and a failed
agent tick; duplicate, stale and misplaced results; closure refusals; the wage
ceiling; dated and unknown snapshots; exact JSON and pickle round trips; a resume
from a pickle equal to the uninterrupted run.

Real extension (`tests/test_timber_supply_native.py`):

- template seed 3, 60 turns, `CHRONICLER_CHECK_RESOURCES=1`: every crew member
  holds a category-3 whole-turn reservation and is a resident adult non-soldier of
  the home region, with no registry conflicts; every wage transfer moves real
  wealth once (a repeated key is refused); `woodcut_outflow` equals the sum of
  `woodcut_output`; the L3 extraction of each cut slot is the economy's slot output
  and includes the cut; wages, stores and expeditions close, with `cut == cargo +
  delivered + lost + abandoned` and `lost` exactly the transit decay; RS2 held
  timber from the store;
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

Later commits changed tests, enrollment, `pending_bills` and (`308422f2`) the recall and deposit rules inside `timber_supply.py` and `timber_supply_state.py`, which a world without the switch never imports.
Template seed 1 with the switch on never launched an expedition, and its whole
history and world state equal the run without the switch (apart from the
package's own key).

### Development worlds (natural, 200 turns)

Arms: `base` (prerequisites only), `supply`, `cost_only`, each with
`--agents hybrid --simulate-only --grain-reserves --public-grain-shipments
--grain-storage --workshops --repair-projects --timber-stock`
(`PYTHONHASHSEED=0 RAYON_NUM_THREADS=1`; procedural worlds `--worldgen procedural
--regions 32 --civs 10`). `supply` and `cost_only` ran on `308422f2` (the recall
and deposit rules); `base` has the switch off and is unchanged since `7c16e9ce`
(identity above). Single worlds: trajectories diverge once spending differs, so
differences between arms are not effect estimates.

| World | Launched (delivered) supply / cost only | Cut, delivered, transit decay, abandoned, released (supply) | RS2 used from store | Wages, coins: supply / cost only | Farmer-turns away (supply) | RS2 `no_timber` stalls: base / supply / cost only | RS2 timber used: base / supply / cost only | Granary mean condition: base / supply / cost only | L3 extraction: base / supply / cost only |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | 0 / 0 | none | 0 | 0 / 0 | 0 | 790 / 790 / 790 | 40.8 / 40.8 / 40.8 | 0.301 / 0.301 / 0.301 | 70.6 (all) |
| T3 | 7 (5) / 19 (13) | 14.9, 14.2, 0, 0.7, 0 | 10.8 | 22.5 / 75.0 | 17 | 738 / 813 / 826 | 106.2 / 95.8 / 88.1 | 0.383 / 0.367 / 0.370 | 316.5 / 304.6 / 295.3 |
| T11 | 8 (8) / 20 (19) | 18.2, 18.2, 0, 0, 1.9 | 16.3 | 32.5 / 72.0 | 34 | 1,043 / 775 / 885 | 94.1 / 101.7 / 90.0 | 0.342 / 0.363 / 0.333 | 245.7 / 273.8 / 247.0 |
| T23 | 29 (17) / 46 (23) | 204.6, 153.4, 2.3, 48.9, 55.4 | 98.0 | 160.5 / 213.0 | 148 | 655 / 483 / 670 | 118.5 / 204.5 / 116.9 | 0.368 / 0.532 / 0.386 | 131.7 / 320.6 / 126.0 |
| P7 | 32 (28) / 67 (45) | 93.2, 84.4, 0.7, 8.1, 21.7 | 62.8 | 204.0 / 344.0 | 159 | 1,885 / 1,968 / 2,107 | 350.1 / 378.4 / 356.9 | 0.454 / 0.476 / 0.447 | 677.5 / 792.2 / 737.6 |
| P13 | 29 (24) / 48 (36) | 114.1, 100.3, 1.0, 12.9, 61.5 | 38.8 | 156.5 / 275.5 | 166 | 2,163 / 1,818 / 2,265 | 425.4 / 492.5 / 464.1 | 0.399 / 0.471 / 0.430 | 1,442.0 / 1,438.6 / 1,533.8 |
| P21 | 68 (46) / 82 (65) | 321.7, 243.5, 2.9, 67.5, 68.9 | 174.6 | 378.5 / 460.5 | 322 | 2,140 / 1,450 / 1,718 | 293.9 / 560.9 / 429.0 | 0.386 / 0.578 / 0.502 | 724.7 / 1,081.6 / 819.5 |
| P31 | 63 (44) / 72 (57) | 448.8, 344.1, 4.2, 100.5, 67.6 | 267.9 | 358.5 / 423.0 | 300 | 2,449 / 1,991 / 2,341 | 306.9 / 530.9 / 359.8 | 0.327 / 0.459 / 0.365 | 519.0 / 1,071.8 / 746.7 |

Per ended expedition (the comparison the control supports):

| World | Ended: supply / cost only | Wages, coins | Person-turns | Farmer-turns away | Cut (supply) | Delivered (supply) | Recalls / unpaid turns: supply / cost only |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T3 | 7 / 19 | 3.21 / 3.95 | 6.4 / 7.9 | 2.4 / 4.1 | 2.13 | 2.03 | 0, 0 / 0, 0 |
| T11 | 8 / 20 | 4.06 / 3.60 | 8.1 / 7.2 | 4.3 / 4.1 | 2.27 | 2.27 | 0, 0 / 0, 0 |
| T23 | 28 / 45 | 5.73 / 4.68 | 11.6 / 9.4 | 5.3 / 4.2 | 7.31 | 5.48 | 0, 0 / 0, 0 |
| P7 | 32 / 66 | 6.38 / 5.16 | 13.3 / 10.5 | 5.0 / 5.2 | 2.91 | 2.64 | 5, 5 / 2, 4 |
| P13 | 29 / 47 | 5.40 / 5.86 | 10.9 / 11.9 | 5.7 / 6.4 | 3.94 | 3.46 | 2, 1 / 5, 2 |
| P21 | 66 / 81 | 5.64 / 5.64 | 11.4 / 11.5 | 4.8 / 4.7 | 4.76 | 3.69 | 5, 4 / 7, 6 |
| P31 | 63 / 70 | 5.69 / 5.99 | 11.7 / 12.2 | 4.8 / 6.1 | 7.12 | 5.46 | 5, 8 / 7, 6 |

- **Where it acts.** Template worlds have one or two timber regions, so most
  civs have no forest of their own or of nobody: `no_forest` is the largest
  refusal in every template world and T1 never launches (`no_forest` 714,
  `forest_depleted` 122: its one forest is cleared below the guard). Procedural
  worlds refuse mostly `no_forest`, `too_far` (P21 525, P31 919) and
  `forest_depleted` (P13 1,511). Cross-civ timber is out of scope.
- **Timber delivered.** 14-344 timber per world over 200 turns in `supply`, 0 in
  `cost_only`. Crews cut 0.28-1.39 timber per person-turn while cutting (D1's
  single-farmer gain was 0.19-0.75). RS2's timber use is above `cost_only` in all
  seven acting worlds and above `base` in six (not T3).
- **RS2 stalls and condition.** `no_timber` stalls are below `cost_only` in all
  seven acting worlds, and mean granary condition is above it in six of seven
  (not T3, 0.367 against 0.370); the largest differences are T23 (0.386 to
  0.532), P31 (0.365 to 0.459) and P21 (0.502 to 0.578). The granaries still end
  worn in most worlds: timber is one of several limits (coins, labour, war).
- **No timber destroyed.** Transit decay is the only loss (0-4.2 per world). The
  cargo of expeditions whose whole crew was lost (2-20 per world) was deposited
  at the forest as commons: 0.7-100.5 timber per world, 5-22% of the cut. Under
  the old rule the same endings destroyed 18-39% of the cut. Recalls are rare
  (0-5 per world in `supply`, 0-8 unpaid return turns): the launch check already
  requires the whole expedition to be payable.
- **Crew churn.** People stay in the pool at home, so native migration, death,
  enlistment and trips take members away; `migrated` is the most common drop.
- **Home food cost (inferred, not measured).** 17-322 farmer-turns left the home
  land in `supply`. At D1's 0.27-1.02 food lost per farmer moved off food, that
  is about 5-328 food per world over 200 turns, against 11,000-65,000 food
  produced in the world. The bundle does not separate the counterfactual
  harvest, so no direct number is claimed.
- **L3 stock.** Expeditions add to the stands' extraction (T23 131.7 to 320.6, P31
  519.0 to 1,071.8). The guard holds: the lowest stock share after any cutting
  turn is 0.51-0.78 of capacity.
- **Wages and the control.** In total `cost_only` pays more (72-461 coins against
  23-379) because it keeps launching; per ended expedition the two arms cost
  about the same (3.2-6.4 coins and 6-13 person-turns), which is what the control
  matches.

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

- **Abandoned cargo stays at the forest.** A crew lost on the way home leaves
  its cargo at the forest, not where it was (no position is tracked); the
  deposit is commons in that region's stockpile, where the stock cap, crafts and
  merchants can take it like any other timber.
- **Unpaid return turns withhold ordinary income.** A recalled crew walking an
  unpaid turn is away, so its ordinary income is withheld with no wage; the
  household bears that turn. Paying nothing and withholding nothing would let
  people earn at home while away.
- **Crew churn.** The crew stays in the pool at home, so native migration,
  death, drafting between reservations and trips take members away mid-trip
  (12-174 drops per world in `supply`). That is honest about the model, and it
  makes expeditions fragile.
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
- **The control is matched per expedition, not in total.** `cost_only` supplies
  nothing, so its need persists and it launches more expeditions: its total
  cost exceeds `supply`'s. Compare costs per expedition (`per_expedition`).
- **Viewer.** No reader or panel (PL5).
- No held seed, 200-seed or procedural qualification gate was run.
