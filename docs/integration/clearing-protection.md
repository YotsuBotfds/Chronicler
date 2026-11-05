# RS5: funded protection of forest cover against clearing (2026-11-05)

Phase "Recovery, skills and resilient local economies", lane RS5.
`--clearing-protection` (modes `enforced`, the default when on, and `cost_only`)
is off by default. When it is on, a region's controller can pay wardens to suspend
**population-driven** forest clearing. The protection is applied where the
authoritative ecology tick decides on clearing. It is never a later restoration of
cover that downstream systems have already read. It works in every ecology path:
native `AgentSimulator` (agent modes), native `EcologySimulator` (`--agents off`
with an extension) and the pure-Python fallback (no extension). Merging this
does not qualify it scientifically.

Code: `src/chronicler/clearing_protection.py`,
`src/chronicler/clearing_protection_state.py`; native
`chronicler-agents/src/ecology.rs` (`tick_forest_controlled_protected`),
`chronicler-agents/src/ffi/batch.rs` (`clearing_protection_column`, the
receipt columns), `chronicler-agents/src/region.rs`
(`RegionState::clearing_protection`), both `set_region_state` paths
(`ffi/ecology_sim.rs`, `ffi/mod.rs`); Python fallback `ecology._tick_forest`.
Tests: `chronicler-agents/tests/test_clearing_protection.rs`,
`tests/test_clearing_protection.py` (offline),
`tests/test_clearing_protection_parity.py` (real extension).

## 1. Audit facts the design rests on

These were checked on `456492e6`.

- Clearing removes a flat `ecology.forest_clearing_rate` (0.02) of cover from a
  **controlled** region whose population is above
  `ecology.forest_pop_ratio` (0.5) of its carrying capacity. Uncontrolled
  regions never clear. Regrowth is blocked while the population is above that
  threshold. A protection can therefore freeze cover against clearing, but it
  cannot restore cover.
- Native `ecology.rs` is authoritative whenever an extension exists. Agent modes
  use the `AgentSimulator`; off mode uses the `EcologySimulator`
  (`main._create_ecology_runtime`, `simulation.py` Phase 9). Python
  `ecology._tick_ecology_python` is the fallback without an extension.
- Cooling damage (Phase 9), wildfire (`climate.check_disasters`, Phase 1),
  supervolcanoes (`emergence._apply_supervolcano`) and succession
  (`emergence.tick_terrain_succession`) are separate cover changes. This
  package leaves all of them untouched.
- The L3 timber account's `cleared` (`timber_stock.py`) lumps every cover-loss
  cause together (clearing, cooling, wildfire, succession).

## 2. Mechanism

- **Column.** The optional Float32 region-batch column `clearing_protection` holds
  one value p in [0, 1] per region index.
  - `agent_bridge.build_region_batch` appends it only while a plan for this turn
    awaits the ecology tick, which means only while the switch is on.
  - Both native `set_region_state` paths parse it through one validator. The
    validator refuses another type, a null, a non-finite value or a value outside
    [0, 1], and it does so before any region state changes.
  - The value sets the transient `RegionState::clearing_protection` (`Option<f32>`).
    This field is declared `transient` in `persist_struct!`, so it is absent from
    the checkpoint payload and the schema fingerprint, and the checkpoint layout
    does not change. Every batch resets it (absent = `None`), and the ecology tick
    consumes (`take`s) it.
- **Decision point.** `tick_forest_controlled_protected` removes
  `forest_clearing x (1 - p)`. `None` takes the old code path: the flat loss, bit
  for bit. The Python fallback (`_tick_forest(..., protection=p)`) uses the same
  formula in float64.
- **Receipts.** Per region, `ExtractionLedger` records `clearing_active` (the
  clearing fired) and `cover_not_cleared` (`forest_clearing x p`, nominal, before
  the tick's clamp).
  - They are returned as two columns appended to the ecology region batch, only when
    the input carried the column. Without the switch, the output schema is exactly
    `ecology_region_schema()`.
  - The Python fallback records the same pair.
  - `clearing_protection.observe_native` raises if an extension returns no
    receipts for a column it was sent.

## 3. Adoption, payment and endings

Planning happens in Phase 9, immediately before the region sync (hook
`before_ecology`). Settlement happens after the tick (`after_ecology`). Every
parameter is a declared modeling choice, not a calibration.

| Parameter | Value | Meaning |
| --- | --- | --- |
| `MAX_REGIONS` | 2 | protections a civilization holds at once |
| `WARDEN_COST` | 2 coins | per protected region-turn with clearing pressure |
| `PROTECTION` | 1.0 | share of clearing a fully paid protection suspends |
| `MIN_COVER` | 0.2 | "forested": the succession and deforestation-cascade threshold |
| `IDLE_LIMIT` | 12 | settled turns without clearing before a protection ends |
| `UNFUNDED_LIMIT` | 3 | consecutive clearing turns with nothing paid before it ends |

- **Eligibility.** A region is eligible when it is controlled, has cover of at least
  `MIN_COVER`, and its population is above the clearing threshold at planning time.
  Planning uses the same population and capacity the tick reads.
- **Order and adoption.**
  - Existing protections are planned first, in region order.
  - Then each civilization (by index) may adopt candidates by descending cover, then
    region index, up to `MAX_REGIONS`.
  - Adoption requires the first `WARDEN_COST` in full.
- **Bills.**
  - A protected region with pressure needs `WARDEN_COST`; one without pressure needs
    nothing.
  - Bills are planned against the projected treasury. The projection replays queued
    accumulator changes as the accumulator will apply them: `keep` changes in agent
    modes (`apply_keep`), every category with `--agents off` (`apply`), each floored
    at zero.
  - A short treasury pays what it can, and p = `PROTECTION x paid / WARDEN_COST`
    (0, 0.5 or 1).
- **Charge.** After the tick the planned payment is charged once, as accumulator
  `keep` (direct mutation without an accumulator).
  - It is charged only for region-turns whose clearing was **actually active** per
    the authoritative receipt.
  - Before committing, settlement checks that each payer still controls its region
    and that the projected treasury covers the charge; it raises otherwise.
- **Failed tick.** A tick that raises charges nothing. Its plan stays unsettled, and
  the next planning drops it (counted as `abandoned_plans`). A plan without receipts
  cannot be settled.
- **Endings** (checked at planning):
  - `controller_changed`: responsibility does not transfer. The new controller decides
    afresh in the same planning, with its own treasury and its own `MAX_REGIONS`, and
    may re-adopt the region.
  - `uncontrolled`.
  - `cover_lost`: cover is below `MIN_COVER`.
  - `idle`: no clearing for `IDLE_LIMIT` settled turns.
  - `unfunded`: nothing paid for `UNFUNDED_LIMIT` clearing turns.
- **Switch off.** Disabling the switch freezes protections and drops a pending plan:
  no column and no bills.
- **Resume.** State is exact under pickle and checkpoint resume. The plan is a private
  attribute and is never serialized.

## 4. Cost-retaining control

`--clearing-protection-mode cost_only` adopts, plans, pays and charges exactly as
`enforced` does, but it sends p = 0. The clearing is then unchanged, and its
ecology equals the switch-off ecology exactly, as the offline test shows over four
turns. Receipts record `cover_would_keep`, the cover the payment would have kept
(`forest_clearing x p_planned` when the clearing was active), with
`cover_not_cleared` 0.

## 5. Local budgets (L9)

With `--local-budgets` (hybrid with grain reserves), the warden bill sits inside the
same envelope mechanism as the L8 commons wardens.

- **Provider.** `clearing_protection.BUDGET_PROVIDER` is the registered provider.
  It is appended to `local_budgets.PROVIDERS` under service `clearing_wardens` in the
  `wardens` group it shares with L8.
- **Proposals.** In Phase 10 of turn T, the provider proposes:
  - continuing protections (divisible: a partial envelope lowers p);
  - adoption candidates under this package's rule (not divisible).

  It proposes only where the population is above the clearing threshold now. The
  claim is `clearing:<region>`.
- **Stake.** The stake is the patricians': `horizon x forest_clearing x` the
  region's timber reference harvest (`timber_stock.reference_harvest`), in the crew
  work its raw loads could supply (`workshops.K_RAW_PER_WORK`). Standing forest does
  not relieve the commons' food burden. A region without a timber slot therefore
  has no supporter under bargaining (`no_support`). It is funded only under
  `fixed_shares`.
- **Spending.** Planning in T+1 pays only `min(projected budget, envelope)`, so no
  envelope means no payment and no adoption. L9 settles the commitment in Phase 10
  from this turn's receipt.
  - `kept` when the charge met what was due. Nothing is due without active clearing.
  - Otherwise `treasury_shortfall`, `recipient_lost` (the controller changed or the
    region is uncontrolled) or `not_adopted`.
- **Contained L9 edits.** Besides the provider entry, the fixed-shares scale now
  counts a registered group's weight once, however many active providers share it.
  Before this change, L8 and RS5 together would have counted `wardens` twice. With
  the existing providers (one per group) the result is unchanged.

## 6. Ledger and observation

`snapshot.livelihoods.clearing_protection` is present only while the switch is
active. It is a copy, never live state, and carries:

- `schema_version` 1, `units`, `mode`, `source_turn`, `completed_turn`,
  `observed`;
- `parameters`: the declared values plus the ecology's effective
  `forest_clearing` and `forest_pop_ratio` (tuning overrides applied);
- `receipts`, one per protected region-turn: `region_id`, `payer`, `new`,
  `cover_before`, `cover_after`, `pressure_planned`, `required`, `envelope` (the L9
  cap, null without L9), `paid_planned`, `p_planned`, `p_applied`,
  `clearing_active`, `cover_not_cleared`, `cover_would_keep`, `charged`,
  `timber_capacity_kept`, `source` (`native` or `python`);
- `unprotected`: the same turn's controlled regions under clearing pressure at
  planning, or whose clearing fired, that had no protection. These are the unmet
  needs and the cover lost elsewhere. Each row has `region_id`, `controller`,
  `reason`, `pressure_planned`, `clearing_active`, `cover_before`, `cover_after`
  and `cleared` (the nominal clearing the tick removed, 0 when it did not fire).
  `reason` is one of:
  - `over_limit`: the ruler already held `MAX_REGIONS`;
  - `unaffordable`: the first bill or its L9 envelope could not be paid;
  - `not_forested`: cover below `MIN_COVER`;
  - `not_planned`: no pressure at planning, yet the clearing fired.

  The field was added after the first RS5 landing. A record without it reads as
  unknown, not as none.
- `decisions` of the source turn;
- `protections`;
- `counters` (the funnel).

When no Phase 9 was settled in the source turn, `observed` is false and
`receipts`, `unprotected` and `decisions` are null, not empty.

**Viewer** (not mounted; the lead mounts it in `LivelihoodsPanel`). The reader
is `viewer/src/lib/clearingProtection.ts` (`clearingProtectionAt(snapshot,
regionCount)`). It is strict: it returns null for an absent record (an older
bundle or the switch off), a foreign schema, a record dated to another snapshot,
or a malformed or inconsistent one. Examples of inconsistency:
- a bill that does not match pressure, or a payment above the bill or envelope;
- a p that does not match the payment, or a nonzero p applied in cost_only;
- a charge without active clearing;
- cover kept that differs from what the payment keeps, beyond 1e-6
  (float32 native receipts);
- receipts that differ from the protections in force;
- a new receipt without its adoption;
- an unprotected row overlapping a protected region.

`clearingSummary` sums the turn's cover kept, cover cleared in underfunded
protected regions (unknown without `forest_clearing`) and cover cleared elsewhere
(unknown without `unprotected`), plus planned, paid and charged coins.

`viewer/src/components/systems/ClearingProtection.tsx` shows, for the selected
snapshot only:
- protected regions with payer, pressure, active clearing, p (applied, and paid
  for in cost_only), cover before and after, cover kept, planned/paid/charged and
  funding (full, partial, unfunded, not due);
- cover kept against cover lost;
- unmet needs with their reasons;
- adoptions and endings with their reasons;
- the protections in force;
- the lifetime funnel. A missing counter shows as Unknown.

It also states the trade-off. The reader accepted all 240 snapshots of three
80-turn native runs (seed 3 hybrid enforced and cost_only, seed 1 native off
mode): 413 receipts, 526 unprotected rows and 30 decisions.

`timber_capacity_kept` is reported with `--timber-stock` only. It is the L3
effective capacity that the kept cover holds on the region's timber slots
(`reference_capacity x cover_not_cleared / 0.9`), which is the upper bound on
timber the next L3 settlement would otherwise have counted as `cleared`. L3's own
`cleared` still lumps every cause together. This package's receipts give the
avoided clearing part, keyed by region, without editing `timber_stock.py`.

## 7. Stated trade-off

Protection keeps standing cover, and with it:

- timber yield, which is linear in cover;
- the forest soil bonus above 0.5 cover;
- downstream water: the deforestation cascade below 0.2 cover takes water from
  downstream regions.

It forgoes the forest-to-plains succession after 50 turns below 0.2 cover, which
adds 20 carrying capacity. That cost shows in the runs below: in seed 3 the
enforced arms end with 380 capacity against 420 in cost_only.

Under persistent pressure, protection **delays** loss but does not prevent it.
Regrowth stays blocked and cooling still erodes the frozen cover. Once cover falls
below `MIN_COVER`, the protection ends and clearing resumes. In off-mode seed 3,
every region except the mountains had zero cover by turn 100 in all three arms.
That includes the two forest regions that protection kept from succession.

## 8. Evidence

All runs used Linux, Python 3.13, `PYTHONHASHSEED=0` and `RAYON_NUM_THREADS=1`,
with the branch `claude/rs5-clearing` and a native extension built from it
(SHA-256 `7e44f019…6fffb7c635`).

| Check | Command | Result |
| --- | --- | --- |
| Rust unit tests | `cargo test --locked --manifest-path chronicler-agents/Cargo.toml --test test_clearing_protection` | 6 passed |
| Full Rust suite | `cargo test --locked --manifest-path chronicler-agents/Cargo.toml` | 1241 passed, 0 failed, 2 ignored |
| Offline module (Python fallback, no extension) | `.venv/bin/python -m pytest tests/test_clearing_protection.py` | 23 passed |
| Viewer reader and panel | `npm test -- --maxWorkers=2 src/lib/__tests__/clearingProtection.test.ts src/components/systems/__tests__/ClearingProtection.test.tsx` | 9 passed; full suite 128 files, 1265 passed; `npm run lint` and `npm run build` clean |
| Native tests | `pytest tests/test_clearing_protection_parity.py` (native venv) | 21 passed |
| Related native suites | `test_ecology_bridge`, `test_ecology_parity`, `test_production_ledger_native`, `test_commons_rules_native`, `test_local_budgets_native`, `test_timber_stock_native`, `test_livelihoods_wiring`, `test_clearing_protection` | 102 passed |
| Bounded offline lane, every chunk run past failures (the runner's exact commands and guard) | `scripts/run_python_oracle_checks.py` chunks | 48 of 57 chunks pass. The 9 failures are source-witness pins only: `batch_manifest.py` (local registration), `ffi/mod.rs` and `simulation.py`. The RS5 module passes under the guard (22 of 22). Total 228 s, largest chunk 35 s of 110 s |

Feature-off identity was checked against the base `456492e6`, with the base
extension `70587268…` for the native paths. Template seed 3 ran for 60 turns on
three paths: `--agents off` without an extension, `--agents off` with the native
`EcologySimulator`, and `--agents hybrid`. On every path every output file was
byte-identical. `state.json` was identical. The bundle differs only in
`metadata.generated_at`.

**Short native runs.** The driver is
[clearing-protection-evidence/driver.py](clearing-protection-evidence/driver.py),
with metrics and source identity in
[clearing-protection-evidence/](clearing-protection-evidence/). It ran template
seeds 1-3 for 100 turns, with `--agents hybrid` and `--agents off` (native),
in three arms: switch off, `enforced` and `cost_only`. That is 18 runs, 0
failed, 46 s.

- **Money closes.** In every switch-on run, the accumulator `keep` debits booked by
  the settlement equal the receipts' charges, per civilization and turn. All
  12 runs show 0 mismatches, every receipt came from the native tick, and the
  totals are hybrid 223/84, 80/28, 426/116 and off 114/72, 140/63, 362/128
  (enforced/cost_only coins).
- **Protected against unprotected cover.** For the region-turns in which the native
  clearing fired, the mean cover change of fully paid protected regions was
  between -0.0025 and 0.0, which is cooling only. The change in forested
  unprotected regions in the same ticks was -0.020 to -0.021. Total cover not
  cleared under enforcement was 2.23, 0.80 and 4.26 (hybrid) and 1.14, 1.40 and
  3.62 (off); cost_only kept 0 while paying for 0.28 to 1.28 `cover_would_keep`.
- **Endogenous cost.** Enforced protections last longer, because cover stays at or
  above `MIN_COVER`, so they cost more. Over the six seed/mode pairs, enforced
  protection cost 1.6-3.7 times the cost_only coins.
- **Final outcomes are mixed.** Final mean cover is higher under enforcement in
  hybrid seeds 1-3 (0.112/0.106, 0.322/0.291, 0.159/0.130 against cost_only),
  lower in off seed 1 (0.049 against 0.061) and equal in off seeds 2-3. Runs
  diverge once treasuries and cover differ. Two forest regions in seed 3 escaped succession under enforcement in both
  modes. This is a development cohort only: it says nothing about effect sizes.

## 9. Limits and deviations

- **Planning moment.** Planning happens immediately before the tick, so planned
  pressure and the tick's pressure read the same state. Charging "only where
  clearing was active" protects against float32 against float64 threshold
  disagreements, and it is the rule if planning ever moves earlier.
- **Nominal receipt.** `cover_not_cleared` is the nominal `forest_clearing x p`
  before the tick's clamp. It can overstate the cover actually kept when cover was
  already within 0.02 of the floor.
- **No transfer on conquest.** Responsibility does not transfer. The protection ends
  and the new controller decides afresh (section 3).
- **Delay, not prevention.** Under persistent pressure protection delays loss but
  does not prevent it (section 7). The `cover_lost` ending is a declared choice.
- **L9 bargaining.** Regions without a timber slot are never funded under bargaining
  (section 5). The stake is a crude, declared proxy.
- **Shared seams.** Two new livelihoods protocol hooks, `before_ecology(world, acc)`
  and `after_ecology(world, acc)`, run in every agent mode. Lead-owned hunks:
  - `simulation.py`: two calls around Phase 9;
  - `livelihoods.py`: the hook fan-outs;
  - `agent_bridge.build_region_batch`: the optional column;
  - `ffi/mod.rs`: parsing and the struct field;
  - `local_budgets.py`: the provider entry and the scale dedupe.

  The switch registry entries on this branch are a local registration that RS0
  supersedes.
- **Source witnesses.** Edits to `simulation.py`, `agent_bridge.py`, `ffi/mod.rs`
  and, through the local registration, `batch_manifest.py` break their
  source-witness chains. The lead adds reviewed layers.
- **Not done.** The viewer panel is not mounted. The held screens, the 200-seed
  gate and the procedural gates were not run.
