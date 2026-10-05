# Renewable fishery stock experiment

This default-off experiment adds recoverable local fish biomass. It is based on
public main `edf72991cad58d6670b1f382c33d50d903a6054a`, including PR13. It has no
relationship to the private frozen candidate `b665e198`, and its evidence must
not be compared across those baselines. Checkout: `/workspace/chronicler-ecology`,
branch `experiment/ecology-fishery-stock`. No public push or merge is authorized.

## Why this is new

`ecology.py:update_depletion_feedback()` and `ecology.rs:tick_depletion_feedback()`
already include fish among depletable resources. They accumulate an extraction
streak and periodically reduce **permanent effective yields**. Both seasonal
ecology yield functions nevertheless read **base yields**. Neither stores renewable
fish biomass or replenishes it when fishing pauses. Soil/forest recovery and
finite mineral reserves do not supply this missing marine feedback. The Phase 6
roadmap's M35b resource-depletion section calls for overfishing feedback; this is
a narrow recoverable stock mechanism, not the broader Phase 8 commons system.

The experiment preserves permanent degradation state. Fish stock constrains
current seasonal catch and subsequent goods production through an explicit debit.
No fertility, mortality, migration, or informed-resupply rules are modified.
Existing downstream famine, satisfaction, income, and food-sufficiency mechanisms
may respond to lower supply.

## Mechanism and units

For each fish slot, let `s` be stock fraction, `b` base yield, `y` the existing
season/climate-adjusted potential yield, and `w` the fishing workforce:

```text
capacity = b * reserve_turns
recovery = recovery_rate * (1 - s)
available = s + recovery
effort = min(w / reference_workers, 4)
catch_units = min(y * effort, available * capacity * harvest_fraction)
harvest_fraction_of_capacity = catch_units / capacity   (zero if capacity == 0)
next_stock = available - harvest_fraction_of_capacity
actual_per_worker_yield = catch_units / effort         (potential if effort == 0)
next_economy_catch_budget = catch_units * reference_workers
```

Capacity and catch units are yield equivalents per reference workforce; the
economy budget converts these to individual worker-yield units. They are not
kilograms. Replenishment is an external biological source for an open fishery,
proportional to missing biomass. It includes recruitment/immigration in one term
and allows recovery from zero. It is not a closed-population logistic model.

The agent bridge supplies current live farmer counts before its agent tick.
Without a bridge, ecology uses the existing `population // 5` proxy. All farmers
in a region are treated as fishing effort for its fish slots; secondary-slot
labor is not allocated separately. Effort saturates at four reference workforces.
The existing economy produces goods from the primary slot only. Catch debited
from secondary fish slots can affect existing yield readers but does not become
economic food production in this experiment.

Phase 2 converts the previous catch into food subject to actual farmer counts.
Both economy paths cap production at the recorded catch budget, even if labor
changes or seasonal potential differs from permanent yield. Unconverted catch is
discarded as handling loss; it is not returned to fish stock or carried forward
as a second fish stockpile. An enabled region without a prior catch budget gets
zero production credit until its first ecology tick; existing food stockpiles
still follow their normal consumption rules.

## Interface manifest

| Surface | Fields / defaults | Phase and ownership |
|---|---|---|
| World config | `fishery_experiment.enabled=False` | Explicit opt-in, persisted in world JSON; no global tuning/default changes |
| Bounded config | `reserve_turns=8` in [2,100]; `recovery_rate=.04` in [0,.25]; `harvest_fraction=.25` in (0,.5]; `reference_workers=200` in [1,10000] | Pydantic validates load and config assignment; experimental module owns mechanism |
| Region stock | `fishery_stocks=[1,1,1]`, each finite in [0,1] | Python-owned, persisted; updated once per Phase 9 tick |
| Region ratio | `fishery_yield_ratios=[1,1,1]`, each finite in [0,1] | Persisted catch/potential ratio from previous ecology tick |
| Region catch credit | `fishery_catch_budgets=[None,None,None]`, nonnegative finite or None | Persisted previous catch; None means no prior experimental tick, interpreted as zero for enabled fish |
| Existing current yields | `resource_current_yields` | Phase 9 catch feeds existing yield-based famine and native farmer income/satisfaction; still transient/excluded from saves |
| Existing permanent yields | `resource_effective_yields` | Never overwritten by fish stock; existing irreversible degradation remains separate |
| Goods input adapter | Python `economy_yield()`; native `resource_effective_yield_0` input plus optional nullable `fishery_catch_budget` | Phase 2 reads persisted prior catch; native FFI caps its input yield using **actual** live farmer count before production. Python caps production amount before its goods ledger |
| Native catch patch | `apply_fishery_yield_patch(region_id:u16, slot:u8, yield:f32)` on both simulators | After normal Phase 9 postpass/recomputation, before native agents; validates entire batch before changing fish-slot `resource_yields` |
| Runtime preflight | Rebuilt extension must expose catch patch method | Enabled `run_turn` checks before any phase mutates state; direct ecology calls check before native tick |

The goods adapter deliberately reaches the existing effective-yield **input**
used for production, instead of multiplying only a viewer/current-yield signal.
The additional catch cap makes the biomass debit a production bound. It does not
replace the persistent irreversible-degradation field with a temporary value.

Disabled runs freeze and ignore all experiment stock, ratios, and budgets. They
retain the original economy batch schema and skip native patches. Re-enabling
resumes frozen memory. During enabled ticks, a slot that is no longer fish resets
to stock=1, ratio=1, budget=None; a suspended fish slot replenishes with zero catch.
Old saves lacking these fields load disabled with full stocks. No new sidecar,
credentials, paid services, or external uploads are involved.

## Invariants and evidence

- `old_stock + recovery = next_stock + harvest`; stock stays in [0,1].
- Harvest never exceeds available biomass times the bounded harvest fraction.
- Greater effort cannot increase per-worker catch or remaining stock; greater
  stock/recovery cannot reduce catch. Rest/suspension replenishes without harvest.
- Fish changes do not debit mineral reserves, overwrite permanent yields, or
  change nonfish current yields.
- Once a catch is available, Phase 2 fish production cannot exceed its stock
  debit converted to worker-yield units (subject to float32 rounding tolerance).
- Disabled pure-Python full-turn state matches untouched public `edf7299` after
  excluding only the four additive experiment schema fields.

`tests/test_fishery_experiment.py` supplies deterministic accounting fixtures,
parameter rejection, monotonicity, reset/suspension, legacy load, JSON resume,
Python/native parity, stale-extension rejection, economy caps, and a native
counterfactual that proves farmers consume patched catch after recomputation.
It also runs a four-turn hybrid on/off smoke test. The Python resume test proves
Python ecology state continuation only: world JSON does not restore the native
agent pool, RNGs, cargo, or pending-delivery buffers.

The reproducible 12-turn no-LLM paired run is stored in
[`evidence/fishery-stock-pair.json`](evidence/fishery-stock-pair.json). Disabled
canonical state matches untouched main exactly, hash
`bb83bf05b81782ddb2e0cfd186974e88a0f565e7e6c45eb456714108447871d5`.
Enabled repeats deterministically and terminal fish stock is approximately
0.5573 versus 1.0 in the disabled control. This short fixture proves depletion
memory; its core terminal state also matches because catches have not constrained
downstream outcomes there. The separate stressed ecology/native fixtures prove
catch reduction and production constraints. No population or narrative benefit
is claimed.

Fishery stock and the catch credit are separate from goods inventory accounting.
Trades, clamp corrections, merchant cargo, and pending deliveries retain their
existing accounting. A future total-food conservation claim must include all
those buffers plus biological replenishment and discarded catch. These focused
fixtures do not establish full-world or full-hybrid conservation/continuation.

## Run and bounded validation

Enable programmatically or in a world JSON, without changing repository defaults:

```python
world.fishery_experiment.enabled = True
```

```bash
uv sync --frozen --group dev
# Build the current native extension in this same environment for native tests.
python -m maturin develop --manifest-path chronicler-agents/Cargo.toml
python -m pytest tests/test_fishery_experiment.py -q
python scripts/validate_fishery_experiment.py \
  --baseline-src /path/to/clean/edf7299/checkout/src --output /tmp/fishery-pair.json
```

The proposed 40-turn pair is now complete: fixed 800-farmer harvest on turns
0–19, then zero-farmer rest on turns 20–39. The controlled Python Phase 2 → Phase 9
fixture matches disabled behavior to untouched `edf7299` each turn, verifies
biomass and goods accounting, and resumes exactly across a turn-20 JSON reload.
Stock falls to 0.108394 after harvesting and recovers to 0.605908 after rest.
Actual food production is bounded by the prior catch credit. Famine predicates,
cooldown-limited famine events, and stockpile sufficiency are reported separately.
See the [completed validation and transfer record](2026-10-05-fishery-recovery-validation.md).

This is a phase-kernel validation with prescribed snapshots and fixture-only zero
famine population loss, not a full native simulation. No merchants or routes are
present; cargo and pending-delivery buffers are explicitly zero, while storage,
consumption, cap overflow, and floor-correction ledger terms are included.
Full hybrid continuation remains unvalidated and would require complete native
state and all runtime buffers. No parameter sweep or `b665e198` comparison occurred.

Two fresh independent reviewers were used: Tier 1 mechanism/accounting and Tier 2
native/turn-order integration. Their material findings prompted catch budgets and
early runtime preflight; the native-consumption evidence gap prompted the farmer
wealth counterfactual. Review resolution and final check counts are recorded with
the branch's validation evidence.
