# Ecology/goods integration (PR #11) reconciled onto the continuation

Branch `integrate/ecology-goods` merges PR #11
(`origin/fix/ecology-goods-integration`, head
`9fd291da871c5c84912185ff0e7cb03b44340af4`) into the continuation head
`837a44fd19dcfbd99edf2a629371f7c0c7ce7e69` with a merge commit; PR #11's
history is not rebased. PR #11 was written against `f0ffbd2`, before the
default-off fishery stock and mutual-aid work, so five files conflicted and
two more (`ffi/mod.rs`, `ffi/schema.rs`) merged textually but not semantically.
PR #11's own design notes remain in
[economy-coupling.md](../validation/economy-coupling.md).

PR #11 stays **default-on** in agent modes: the subset gate passes and the
comparator reports no regression (see Verification). Off-mode is unchanged.

## Resulting turn contract (agent modes)

Phase 2, in order:

1. Lagged mutual-aid dispatch (when enabled) moves existing stock observed at
   N-1. It reads stocks and native commitments, never yields.
2. `refresh_resource_yields` publishes the non-depleting harvest preview for
   this turn's season, climate, ecology, suspensions and mineral reserves.
3. The economy batch is packed: per-slot `resource_yield_{0,1,2}` from
   `fisheries.economy_yield()` (the preview; for fish slots with the experiment
   enabled, times the lagged catch ratio) and, only when the fishery experiment
   is enabled, nullable `fishery_catch_budget_{0,1,2}`.
4. Native (or oracle) economy: farmer labor splits equally across occupied
   valid slots, each fish slot's allocated output is capped by its budget,
   then PR #11's inventory-based trade, prices and stock lifecycle run.
5. Mutual-aid observation of this turn's food sufficiency.

Phase 9: ecology tick (minerals extracted once), fishery feedback, famine
using **this** turn's `economy_result`, soil floor/counters/succession, the
native post-pass patch (now a non-depleting refresh), then the fishery catch
patch so native agents see the actual catch.

## Conflict decisions

**Economy Arrow input** (`economy.py`, `ffi/mod.rs`, `ffi/schema.rs`). The
base emitted `resource_effective_yield_0` (from `economy_yield`) plus a single
`fishery_catch_budget`; PR #11's reader expects `resource_yield_0..2`. Both now
agree on PR #11's per-slot schema. `economy_yield(world, region, slot)` reads
the realized preview instead of permanent effective yields and keeps the
lagged fish catch ratio. The single budget column became per-slot
`fishery_catch_budget_{slot}` because PR #11 makes secondary slots produce, so
secondary fish catch now becomes goods and must be bounded too. The FFI keeps
the base's validation (finite, nonnegative, fish slot only) per slot.

**Production** (`economy.py`, `economy.rs`). The base capped the slot-0
per-worker yield at `budget / farmers`. With labor split, the cap is applied
to each slot's allocated output instead: `min(yield * farmers / occupied,
cap)`, via `compute_allocated_production(..., production_caps=...)` in Python
and `EconomyRegionInput::production_caps: [Option<f32>; 3]` in Rust. A capped
(or exhausted) fishery keeps its labor share; spare labor is not reassigned,
matching PR #11's rule for suspended or zero-yield slots.

**Fishing effort** (`experimental/fisheries.py`). The base treated *all*
farmers as fishing effort. With labor split, that would deplete biomass for
labor the economy assigns to other resources and then discard the excess
catch. Effort is now `farmers / occupied slots`. This changes the default-off
experiment only for multi-slot fish regions. Single-slot fixtures are
unchanged.

**ecology.py.** Both sides kept: fishery feedback runs before the famine
check, the stale-extension preflight runs before a native tick, and
`economy_result` reaches both the Python and Rust famine checks. In agent
modes, famine is now PR #11's food-sufficiency test, which already includes
the catch cap. Aggregate mode keeps yield-based famine, where the fishery
still lowers yields.

**simulation.py.** Mutual-aid dispatch comes first (it is lagged and moves
stock), then the harvest preview, so the preview sits immediately before
batch packing as PR #11 documents. The two are independent, so the order
changes no values. Phase 9 passes `economy_result`.

**Merchant departure** (`merchant.rs`). Both sides fixed reservations that
outlive economy consumption. The base canceled a whole trip when
`stock - debits < qty`, gated on `DeliveryBuffer.physical_stock`. PR #11
revalidated in `depart_merchant` and shrank the cargo, but did so in shadow
mode too. The combined design keeps PR #11's in-function revalidation:
release the trip's own reservation, cap it at `stock - other reservations -
pending debits`, depart partially or cancel. It is gated on the base's
`physical_stock`, so shadow cargo stays virtual. Partial cargo matches how
reservations are already made (`avail.min(intent)`), and each call leaves
`reserved + debits <= stock`. All tests from both sides pass. The base
hybrid-recheck test now expects partial departures (`min(reserved,
remaining)`), and PR #11's three tests use physical buffers.

**Conservation test.** PR #11 replaced "exports == imports per category"
with `sum(exports) - sum(imports) == transit_loss`. This is correct and
stricter. Category imports are now *delivered* quantities, decomposed per
good from the same final route flows and origin inventory mix that produce
the per-good stock flows. Transit loss is booked once, on that final
decomposition, in both Python and Rust. Per-good shipments never exceed
inventory, because each category flow is bounded by `available - demand` and
split by inventory share. The randomized 12-seed slot/stock fixture also
checks the full stock balance (`< 1e-8`) and zero floor clamps. The old
identity only held because imports were booked before decay.

**Native post-pass re-depletion (fixed).** `apply_region_postpass_patch`
recomputed yields with the depleting `compute_yields`, extracting minerals a
second time whenever Python changed soil, water, forest, terrain or capacity.
Recomputation now uses `ecology::refresh_yields` (the same formula, no
extraction), mirroring Python's `deplete_reserves=False`. A Rust FFI test
runs the real tick and patch path and fails on the old behavior.

## Considered and rejected

Multiplying the preview by persistent degradation (`effective / base`) would
restore the pre-PR coupling from overextraction to goods. However,
`scenario.py` adds river fish slots and specialized resources with base
yields and no effective yields (a pre-existing inconsistency), and the factor
would silently zero those slots. Overextraction also needs `pop//5 > 200 *
yield`, which default worlds essentially never reach. PR #11's
preview-only input is kept, and degradation is listed as a gap.

## Fixture and script adaptations

- `test_fishery_experiment.py`: new column names, realized fixture yields, a
  multi-slot native cap test that checks Python/Rust parity, rejection of a
  budget on a non-fish slot, an effort-share test, and a Python per-slot cap
  test.
- `qualify_third_wave.py`: its independent production oracle is per slot,
  with per-slot budgets.
- `validate_fishery_recovery.py`: previews before Phase 2 (falls back for
  pre-integration sources).
- `economy_coupling_experiment.py`: harvest expectation uses `economy_yield`.
- `mutual_aid_adversarial.py` and its test: there is no ecology tick, so the
  scripted crop also sets the realized yield. Under integrated trade, merchant
  cargo relieved the 20-person Mine before aid was needed, so the Mine has 30
  people to keep the stress, blocked-dispatch, aid, recovery and re-stress
  sequence. Re-stress is now asserted structurally, and the funded reactivation
  turn is 14 (was 12). Integrated trade leaves the donor more grain, so sends
  are need-bound. The test now checks that every send is funded only from stock
  net of live cargo and the donor reserve. Deterministic reserve-binding
  coverage remains in `test_mutual_aid.py`.

Dated evidence describes what it tested and is not rewritten. The fishery
interface manifest (`resource_effective_yield_0`, single budget, primary slot
only), the 40-turn recovery numbers and the mutual-aid adversarial evidence
JSON predate this integration.

## Verification (this branch)

Code commit `1e4dc803553099f5646bba54f5bf39cdfa822ad9`; the commit that adds
this note changes documentation only. Linux, Python 3.13 worktree venv, fresh
`maturin develop --release` build from that commit into the same venv (real
compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator`). All
generated runs are outside the repository.

- `pytest -m "not slow" -n 2`: 5023 passed, 3 skipped (base 4954/3). Slow
  tests: 7 passed, 3 skipped. Two skips are unconditional; the m36
  `invest_culture` data skip also occurs at base.
- `cargo test`: 835 passed, 2 ignored (base 821/2).
- Subset gate (20 seeds x 200 turns, hybrid, `--parallel 2`): PASS, identical
  across two runs. Required oracles (baseline in parentheses):
  - community: PASS, 20/20 qualifying (20/20).
  - needs: PASS, 15 seeds with expected sign (16), median effect 0.547
    (0.425); 12 seeds required.
  - cohort: PASS, 20/20 (20/20), median effect 1.112 (1.025).

  Arcs and era PASS, artifacts PARTIAL, determinism SKIP, regression FAIL
  (`terminal_population_extinction`): all as in the baseline.
  `validation_compare` against the 837a44f baseline: exit 0,
  `regression_detected: false`, no oracle status changes, no new required
  failures. Strict regression checks added `occupation` and removed
  `latest_satisfaction_mean` and `migration_rate_per_agent_turn`.
- `economy_hybrid_smoke.py` (seeds 0, 1, 42 x 30 turns): zero floor clamps,
  max ledger residual 7.7e-6, exact repeat.
- 200-turn hybrid runs: fishery on (seed 42), mutual aid on (seed 42), and
  both (seed 43) all completed. Fish stocks were drawn down (0.956 and
  0.853). Neither aid run fired a transfer; the base also fires none for
  seed 42.

## Behavior drift and remaining gaps

- Food per farmer on generated worlds falls to about 61% of the old
  single-slot input (labor split plus realized seasonal yields). Fewer
  controlled regions have no food output (88 vs 152 of 488 region-turns).
  Civ samples with a farmer share above 70% rose from 12 of 3703 (0.32%) to 37
  of 3509 (1.05%, limit 1.0%), mostly in turns 0 to 49. The regression
  oracle's `occupation` check now fails both strict and calibrated floors. If
  the separate extinction fix makes regression pass, this becomes the
  blocking check.
- Strict `latest_satisfaction_mean` (0.420 to 0.464) and
  `migration_rate_per_agent_turn` (0.049 to 0.060) now pass.
- Agent-mode famine events rose about 60% (2993 to 4792 over the subset)
  because famine now means sufficiency below 1. Supply shocks rose about 53%,
  and secessions went from 41 to 56.
- Extinction is pre-existing and slightly worse: 17 of 20 seeds end at zero
  population (baseline 15), and mean civ population at turn 199 is 10.7 (14.9
  at baseline), although turns 25 to 100 are higher.
- Persistent overextraction degradation no longer reaches goods production
  (see Considered and rejected). Fixing `scenario.py` to initialize effective
  yields is a prerequisite for reintroducing it.
- Labor allocation is an equal split. A food-first or value-weighted split,
  plus PR #11's recommended balance sweep, are open calibration work.
