# L3: renewable harvestable timber stock (2026-11-05)

Sprint 1 lane L3 ([plan](../superpowers/roadmaps/livelihoods-commons-sprint1.md)).
`--timber-stock` (default off; requires an agent-backed economy: `hybrid`,
`shadow` or `demographics-only`) gives every region slot whose resource is
timber an explicit harvestable stock. The realized timber harvest is debited
from it, it regrows over declared turns under forest cover and water, and the
harvest cannot exceed it. It closes the production ledger's open item "Timber
takes no forest cover" ([production-ledger.md](production-ledger.md) section
12) without touching forest cover: cover stays population, climate and fire
driven; the stock is a separate account of harvestable wood on that cover.
Grazing is out of scope for this landing.

Code: `src/chronicler/timber_stock.py`, `src/chronicler/timber_stock_state.py`;
native column `timber_harvest_cap_{slot}` in `chronicler-agents/src/ffi/mod.rs`
(lead, L1A landing `ba3ca22`). Viewer: `viewer/src/lib/timberStock.ts`,
`viewer/src/components/systems/TimberStock.tsx` (not yet mounted). Tests:
`tests/test_timber_stock.py` (offline-safe), `tests/test_timber_stock_native.py`
(real extension), `viewer/src/lib/__tests__/timberStock.test.ts`,
`viewer/src/components/systems/__tests__/TimberStock.test.tsx`.

## 1. State and units

`WorldState.livelihoods.timber_stock` (`TimberStockState`, schema 1):

| Field | Meaning |
| --- | --- |
| `enabled` | the switch; disabling freezes stocks, re-enabling resumes them |
| `stocks` | `(region_id, slot, stock)` per timber slot, sorted; `region_id` is the index in `world.regions` |
| `ledger_turn`, `ledger` | the last settled turn and its per-slot accounts |
| `totals` | cumulative flows and binding count since enabling |

Stocks are in **timber goods**, the units `EconomyResult.slot_output` reports.
A private, never serialized `_offered` holds, within one Phase 2 only, the caps
prepare offered and whether a harvest was possible; finish and rollback clear
it. Pickles from the interface stub (schema 1 with `enabled` only) backfill
every new field.

## 2. Capacity, regrowth and declared parameters

All three parameters are **fixed modeling choices, not calibrations**. They
were not tuned on any run (section 6 found no dramatic collapse).

- Reference harvest `H = base_yield x RAW_REFERENCE_DENSITY (0.33) x
  carrying_capacity`: the economy's woodland-curve reference crew at the
  healthy woodland cover (0.9, `TERRAIN_ECOLOGY_DEFAULTS["forest"]`), whose
  effective labour equals its headcount, times the slot's mean goods yield on
  healthy land (`goods_per_worker` normalizes to the base yield). The temporary
  `capacity_modifier` (drought 0.5, flood 0.85) is left out so a drought does
  not fell the stand.
- Reference capacity `K = REFERENCE_CREWS_AT_MSY x 4H / (r (1 + a)^2)`: the
  stock's maximum sustained yield `r K (1 + a)^2 / 4` equals the reference
  crew's harvest. **`REFERENCE_CREWS_AT_MSY = 1.0`**: the reference crew is
  sustainable; larger crews (the curve yields up to twice the reference
  labour's output) deplete the stock. Template stands: K about 1,600-2,400
  goods, H about 13-20 goods a turn.
- Effective capacity `K_eff = K x forest_cover / 0.9`: linear in cover (the
  standing wood), although cover enters the harvest twice (yield and woodland
  curve), so a thin forest holds more stock per unit of harvest.
- Regrowth `R = r (S + a K_eff)(1 - S / K_eff)`, never past `K_eff`, zero while
  `water < ecology.forest_regrowth_water_gate` (0.3), the gate forest cover
  regrowth uses. Population pressure does not gate it (clearing already
  removes cover). **`REGROWTH_RATE r = 0.03`** a turn (a turn is a month):
  the time scale of forest cover regrowth (+0.01 cover a turn, about 90 turns
  from bare ground), not real forestry; a stand cut to nothing is back to 90%
  of capacity in about 167 idle turns, one cut to half in about 68.
  **`SEED_FRACTION a = 0.05`**: seedlings and coppice; without it a
  harvested-out logistic stock never regrows.
- Initial stock: `K_eff` at enable (the cover-implied level). A slot that later
  becomes timber opens at its `K_eff`; that opening is not a flow.

## 3. Phase 2 hooks and the ledger

`prepare_phase2` (after the city columns, before the native tick) appends
`timber_harvest_cap_{0,1,2}`: Float32, the largest float32 not above
`min(S, K_eff)` on timber slots, null elsewhere. It validates that the batch
rows follow `world.regions` and that its `resource_type_{slot}` columns match,
refuses pre-existing cap columns, charges nothing and changes no stock. It
records whether a harvest was possible on each timber slot: the batch's goods
yield is positive and the Phase 2 agent snapshot has farmers (occupation 0)
in the region, the pool the kernel derives labour from.

The native kernel (lead, `ffi/mod.rs`) takes the cap only where
`resource_types[slot] == 1`, combines it as a minimum with any other
production cap, applies it after the labour split (`min(output, cap)` in
float32) and raises `invalid timber harvest cap` on a non-finite, negative or
non-timber value.

`finish_phase2` (after native success and storage settlement, before public
granaries) settles each slot, in this order:

1. `cleared = max(0, S - K_eff)`: timber on cover lost since the last
   settlement (Phase 9 clearing and cooling, Phase 1 wildfire, succession).
   It precedes the harvest, and the cap already excludes it.
2. `extraction`: `slot_output[region][slot]`, exact. Above the cap it raises
   (an extension that ignores the column). A missing slot output raises.
3. `regrowth` on what is left.
4. `removed`: the stock of a slot that is no longer timber.

`stock = opening - cleared - (extraction - overdraft) + regrowth - removed`
is checked for every slot every turn (relative tolerance 1e-9) together with
`extraction <= cap` and `stock <= K_eff`; a violation raises before anything
is committed. Each unit of wood leaves through exactly one path. A turn is
settled once (a second settlement raises), the caps finish recomputes must
equal those offered, and the commit is atomic. Nothing else changes: forest
cover, soil, yields and every other world field are untouched; no RNG is
drawn; no events are emitted; `acc` is not used.

`capped` (per row): with a positive cap, whether the output reached it; with
a zero cap (nothing standing), whether a harvest was possible (above); None
when not enforced or when possibility was not observed.

## 4. Cost-retaining ablation control

Tuning `livelihoods.timber.enforce_cap: 0` keeps the switch, the accounting,
the columns (all null) and the observation, but applies no cap. Extraction
beyond the stock is recorded as `overdraft` (part of `extraction`), and the
stock floors at zero. The outcome equals a run without the stock (section 6).
Any nonzero value enforces. The key is not yet in `tuning.KNOWN_OVERRIDES`, so
`load_tuning` warns "Unknown tuning key" (registration is a lead patch).

```yaml
livelihoods:
  timber:
    enforce_cap: 0
```

## 5. Observation

`snapshot.livelihoods.timber_stock`, only while active: `schema_version` 1,
`units` `timber_goods`, `source_turn` (the settled Phase 2), `completed_turn`
(= snapshot turn = source + 1), `enforce_cap`, `parameters`, `observed`,
`regions` (one row per timber slot: `region_id`, `slot`, `opening`,
`cleared`, `extraction`, `overdraft`, `regrowth`, `removed`, `stock`,
`capacity`, `cap`, `capped`, `water_gate_open`) and `totals` (sums plus
`slots`, `capped_slots`). When no account was settled in the source turn
`observed` is false and `regions`/`totals` are null, never zero. Bounded by
three rows per region.

The viewer reader `timberStockAt(snapshot, regionCount)` is strict: null for
an absent, foreign-schema, misdated or malformed record, duplicate or
out-of-range rows, an unclosed ledger, extraction above the cap, overdraft
under enforcement or a cap under the ablation. It accepted all 1,000 records
of the runs below. `TimberStock` renders totals, per-slot accounts, the
ablation label and unknown turns.

## 6. Evidence (development cohort only)

Linux container, Python 3.13, `PYTHONHASHSEED=0`; native venv
`~/.venvs/chronicler-native-l3` (extension SHA-256
`1dc671fb...2ed49`, built by the lead from `ba3ca22`; editable source this
branch). Template seeds 1-3, 200 turns, `--agents hybrid`, arms off / on /
ablation (6-10 s a run, two at a time). Held seeds 101-106 and 201-206 were
not run.

| Seed, slot | K0 | Extraction (sum, mean, max) | Regrowth | Cleared | Cap bound (on) | Ablation overdraft | Stock / capacity at 199 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1, Thornwood (5,0) | 1,599 | 67.3, 0.34, 6.4 | 342.6 | 1,554.0 | 1 turn (zero cap) | 0.0011 in 1 turn | 320 / 870 |
| 2, Mistwood (5,0), no harvest (population 0 at start and end) | 2,257 | 0 | 1,112.9 | 2,186.1 | 0 | 0 | 1,184 / 1,555 |
| 3, Thornwood (0,0) | 2,381 | 110.8, 0.55, 7.5 | 314.8 | 2,575.7 | 0 | 0 | 9 / 503 |
| 3, Mistwood (2,0) | 2,021 | 185.1, 0.93, 16.7 | 19.0 | 1,855.1 | 10 turns (zero caps) | 0.146 in 7 turns | 0 / 0 |

- **Cover loss dominates.** Population clearing (-0.02 cover a turn above half
  the carrying capacity), cooling and wildfire (-0.3) take populated stands'
  capacity below a tenth of its start in 26-92 turns and to zero at least once
  (first at turn 30 in seeds 1 and 3); cleared timber is 10-23 times the
  extraction. Template timber extraction is small: timber-only regions keep
  the food-first floor share of farmers (a quarter of an equal share).
- **Natural binding is rare and only at zero caps**: after cover collapses
  and regrows, the stock lags the cover-scaled capacity from near zero and the
  little timber labour that remains finds nothing standing. Seed 1 binds once
  (turn 51), seed 3 ten times (from turn 60).
- **Identity.** The ablation's bundle equals the off arm's for all three seeds
  (history, world state and every non-livelihoods field; the tuning
  overrides and the livelihoods record excluded). The on arm equals off for
  seed 2 and until the first binding for seeds 1 and 3 (first differing
  snapshots 52 and 61); 0.001 goods withheld then diverges the trajectory.
- No dramatic collapse appeared, so no parameter was tuned.

**Constructed scenario (not a natural trajectory): "timber labour boom".**
A workshop boom cannot by itself hit timber in this economy: extraction is
the farmer labour split (food-first, then equal) times the yield, and craft
demand draws on the regional stockpile, not on labour. The constructed run
therefore raises timber labour directly: template seed 1, Thornwood given a
grain slot of base yield 9.0 (food covered, so the timber slot keeps about
half the farmers), all cover loss off (clearing, cooling and wildfire cover
loss tuned to 0: a protected woodland), the grain slot removed at turn 120
(timber labour back to the floor share). Driver script kept outside the
repository.

| Stand at start | Arm | Turns 0-119: extraction, regrowth, cap bound | Turns 120-199: extraction, regrowth, cap bound | Stock at 120 / 199 (capacity 1,599-1,687) |
| --- | --- | --- | --- | --- |
| full | on = ablation | 694.4, 465.3, 0 | 181.7, 331.6, 0 | 1,359 / 1,519 |
| cut to 5% | on | 357.7, 287.2, 36 (26 positive caps) | 83.5, 265.3, 5 | 0 / 191 |
| cut to 5% | ablation | 694.4 (overdraft 355.6 in 36 turns) | 181.7 (overdraft 36.7 in 25 turns) | 0 / 5 |

A full stand under the boom (mean harvest about 5.8 a turn including wildfire
suspensions, below the 13.2 sustained yield) dips to 79% of capacity and
recovers after the boom. A cut-over stand stays trapped near zero while the
boom lasts (the harvest takes the seedling regrowth), halving timber output
against the ablation, and recovers slowly once pressure falls (11% of
capacity 80 turns later, the floor-share harvest still taking part of the
regrowth).

## 7. Checks run

- `tests/test_timber_stock.py`: 19 passed (offline guard receipt PASS, with
  the sprint wiring and witness modules: 27 passed).
- `tests/test_timber_stock_native.py`: 3 passed on the native venv above.
- Viewer: the two test files, 7 passed; `npm run lint` and `npm run build`
  pass.
- Bounded offline lane (`scripts/run_python_oracle_checks.py`) on this source:
  PASS, 57 of 57 chunks, 6,034 passed, 69 skipped, 242 s. The timber modules
  are not yet in a chunk (lead enrollment).

Not run: the 200-seed gate, procedural or held cohorts, shadow and
demographics-only modes, other platforms.

## 8. Open items

- Lead patches (files outside this lane): register
  `livelihoods.timber.enforce_cap` in `tuning.KNOWN_OVERRIDES`; enroll the two
  test modules in `native_shards_manifest.json`, `tests/test_native_ci_shards.py`
  and an offline `CHUNKS` slot (the offline module runs in under a second);
  mount `TimberStock` and add the record type to `viewer/src/types.ts`.
- The production ledger (`production_ledger.py`) does not yet report timber
  as a stock kind; the stock's own ledger closes every turn.
- Timber extraction does not respond to demand or prices; a demand channel
  (for example a workshop boom) needs a labour allocation change, not this
  stock.
- Clearing destroys timber rather than yielding it; whether cleared wood
  should become goods is a separate design decision.
