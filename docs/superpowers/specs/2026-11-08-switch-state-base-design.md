# SwitchState Base and Table-Driven build_signals — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** CON-2, CON-10 (plus CON-13, CON-14 below)
> **Depends on:** DEC-1 (D1 option A, via PIN-1) for the pinned batches and for CON-10; CON-1 (switch registry) should land first or in parallel (it also touches `LIVELIHOODS_SWITCHES`)
> **Feeds:** CON-12 (family merges), CON-5 (the column table can later feed the Rust schema check)
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scouts 03, 06, 07, 11)

## 1. Goal and scope
Remove the copy-pasted switch-state boilerplate without changing a single serialized byte, RNG draw or error string.
- **In:** a new tiny module `src/chronicler/switch_state.py` with a field-free `SwitchStateMixin`, shared helpers (`bump_counter`, `lane_active`, `health_holders`, `civ_of_region`), and conversion of the `*_state.py` classes and their owners, batch by batch. CON-10: `agent_bridge.build_signals` per-column validation becomes a column table.
- **Out:** the public `set_<name>_enabled` / `<name>_active` names (dispatched via `getattr` at `src/chronicler/livelihoods.py:~980-1103`, `_CHOICE_FIELDS` at `:~1000`), `LIVELIHOODS_SWITCHES` (`livelihoods_state.py:76-84`), every field, field order, default factory and class module path. No `BaseModel` base swap. No behaviour change. The `set_*_enabled` bodies differ in validation rules and stay hand-written.

## 2. Current behaviour (verified)
- **State classes are pydantic `BaseModel`s** (58 of 59 `*_state.py` files; `apprenticeship_state.py:326` uses a `_Record` base; `scholarship_state.py:82` and `scientific_claims_state.py:142` use `LazyResearchModel`). 39 files declare `enabled: bool`, 28 declare `mode`, 45 declare `counters: dict[...]`.
- **`counters` defaults differ and are observable.** Some start `{}` and fill lazily (`recovery_crews_state.py:136`, `workshops_state.py:99`); others prefill every key in declaration order (`commons_rules_state.py:136`, `cities_state.py:90`, `grain_reserves_state.py:84`). Value types differ (`0` vs `0.0`, `int | float`). `snapshot_summary` dumps these dicts, so key order and int-vs-float type are part of the output.
- **`_bump`: 38 modules, about 26 distinct bodies.** Verified groups: `round(x + n, 4)` unstrict (agent_movements, cities, guilds, nomads, scholarship); strict `KeyError(key)` plus `int(amount)` (guild_leagues, household_retail, reform_services, relocation_costs, remittances); strict plain (apprenticeship, learning_cohorts, movement_branches, operating_wear); unstrict on a bare `counters` dict (`clearing_protection.py:371`, `commons_rules.py:404`). Singletons: `maritime.py:416` rounds only floats; `veteran_reintegration.py` skips zero; `epidemic_care.py` rounds to 6; `local_budgets.py:158` rounds to 6; `ritual_gatherings.py:65` rounds to 9; `public_health.py:79` writes `state.totals`; `diplomacy.py:256` writes `state.counts`; `grain_reserves.py:222` uses `0.0`. KeyError messages differ per module (`undeclared timber-supply counter 'x'`, bare `key`, ...).
- **`_state(world)`: 39 modules**, the same two-line lookup `getattr(world.livelihoods, "<name>", None)` (e.g. `workshops.py:117`, `recovery_crews.py:120`); a few spell it `getattr(getattr(world, "livelihoods", None), name, None)` (`adaptive_livelihoods.py:23`).
- **`__setstate__`: 29 `*_state.py` files; `__getstate__`: 21.** Three forms: fill every missing field from `model_fields` plus default private attrs (`recovery_crews_state.py:~150`, `timber_supply_state.py:285`), `setdefault` only the private attrs (`commons_rules_state.py:149`), or `setdefault` a named list (`livelihoods_state.py:147`). Others (e.g. `workshops_state.py`, `local_budgets_state.py`) have none and rely on pydantic's default restore, which does NOT fill missing fields.
- **`_lane_active(world, name)`** is byte-identical in `recovery_crews.py:158`, `workshops.py:232`, `repair_projects.py:292`, `timber_supply.py:247`, `labour_reservations.py:42`; `operating_wear.py:79,147` imports the `workshops` copy. `_health_holders` is identical in `recovery_crews.py:226` and `apprenticeship.py:1191` (a third near-copy `health_rows`, `labour_reservations.py:~50`, returns two sets and is not a merge target).
- **`_controller`: 9 copies in two semantics.** `commons_rules.py:254`, `clearing_protection.py:147` use `world.civ_index_map.get(name, -1)`; `timber_orders.py:76` scans `world.civilizations` for the first name match, `-1` default; the others return `int | None` or differ in the None case (`apprenticeship.py:325`, `workshop_economics.py:276`, `workshop_payroll.py:192`). Not identical: do not merge blindly (CON-14).
- **cities/agent_movements twins:** `_q`, `_rng`, `_bump` (`cities.py:237-247`, `agent_movements.py:259-269`; `_rng` differs only by the namespace string `"cities"` vs `"agent_movements"`), `_emit` (`cities.py:323` vs `agent_movements.py:403`; the cities copy has a comment line only), `_max_civs` (`cities.py:904`, `agent_movements.py:1453`). Audit claims verified.
- **Shuffle blocks** `adaptive_livelihoods.py:~316-330` and `~359-376` are the same permutation code, one over `rows`, one over `personal`. Both bump `unshuffled`.
- **`build_signals`** (`agent_bridge.py:899-1057`): per civ it validates 4 faction columns, 4 shock, 5 demand, 3 mean-personality, gini, tithe, in that order, then 2 multipliers after the loop, each through `_validated_civ_signal` (`:344`). Demand values are read lazily (`d[0]`..`d[4]`, so a short list raises `IndexError` mid-row). Tests pin messages `gini_coefficient`, `faction_military`, `priest_tithe_share` (`tests/test_agent_bridge.py:179-208`). The record-batch column order and `pa` types (`:1013-1038`) must match `chronicler-agents/src/ffi/schema.rs` (e.g. `:251`).
- **Checkpoint mechanics:** `run_checkpoint.py:329-420` pickles the world; the unpickler admits any `chronicler.*` class by qualified name (`:394-408`), so class paths must stay importable. `checkpoint_replay.py:130` digests `WorldState.model_json_schema()`, so a field, alias or docstring change shows up there.

## 3. Design
### CON-2: `switch_state.py`
```python
class SwitchStateMixin:                      # plain class, NO fields, listed FIRST in bases
    _FILL_DEFAULTS: ClassVar[bool | tuple[str, ...]] = False   # False | True (all fields) | names
    def __setstate__(self, state):
        super().__setstate__(state)
        <fill model_fields per _FILL_DEFAULTS, exactly as recovery_crews_state does>
        <fill every private attr missing from __pydantic_private__ with its declared default>
    def bump(self, key, amount=1): bump_counter(self.counters, key, amount, **type(self)._BUMP)
```
`class RecoveryCrewsState(SwitchStateMixin, BaseModel)` keeps pydantic fields, so JSON schema, `__pydantic_fields_set__`, pickle payload and module path do not change. The mixin adds no annotations, so `model_json_schema()` is unchanged (verified by test, section 7). Class-level `_BUMP = dict(allowed=COUNTERS, label="timber-supply", repr_key=True, coerce=int, ndigits=None)` reproduces each variant. `bump_counter(counters, key, amount, *, allowed=None, message=None, coerce=None, ndigits=None, zero=0, skip_zero=False)` encodes the groups of section 2; unknown variants stay local and are listed in the conversion table, not forced in.
- `__getstate__` (clear transient privates) becomes `_TRANSIENT: ClassVar[tuple[str,...]]` handled in the mixin, preserving `state = {**state, "__pydantic_private__": {...}}` shape (the 21 existing forms differ only in which names they clear).
- **Opt-in fill is mandatory.** Classes with no `__setstate__` today must NOT gain fill-defaults (that would silently change loading of old pickles; it is a possible correction, CON-13, separate PR). The mixin is applied with `_FILL_DEFAULTS` equal to the existing behaviour.
- Owner modules: `_state(world)` becomes `_state = switch_state.sub_state_getter("<name>")`; `_bump` becomes `def _bump(state, key, amount=1): state.bump(key, amount)` or a `functools.partial`, keeping the module-level names (7 test files call `_bump`; `from chronicler.workshops import _lane_active` is used at `operating_wear.py:79,147`). `_lane_active = switch_state.lane_active` in each of the five modules; `_health_holders` is imported from `recovery_crews` by `apprenticeship` (no cycle: check, else put it in `switch_state`).
- **CON-13:** optional later correction, fill defaults for the ~16 classes without `__setstate__`.
- **CON-14:** shuffle helper in `adaptive_livelihoods.py` (`_shuffle_rows(world, state, homes, rows)`); `_controller` helpers: unify only the five bodies proven identical (civ_index_map copies), after a duplicate-civ-name probe on `world.civ_index_map`; and a `cities`/`agent_movements` shared `_q/_rng/_emit/_max_civs` in `src/chronicler/settlement_util.py` with `_rng(namespace)` taking the namespace.

### CON-10: table-driven `build_signals`
```python
_CIV_COLUMNS: tuple[_Col, ...] = (_Col("faction_military", lambda c: c.fac_mil, 0.0, 1.0), ...)
```
`_Col(name, fetch, minimum, maximum, default_clamp)` with a lazy `fetch(ctx)` where `ctx` carries `civ, i, shock, demand, personality, gini, tithe`. The loop `for col in _CIV_COLUMNS: out[col.name].append(_validated_civ_signal(i, col.name, col.fetch(ctx), minimum=..., maximum=...))` keeps the original order (military, merchant, cultural, clergy, 4 shocks, 5 demands, 3 means, gini, tithe) and the lazy reads, so the first failing column, its message and any `IndexError`/`AttributeError` are unchanged. `civ_personality_mean` is computed once per civ before the mean columns, as now. Multipliers stay after the loop. Non-validated columns (`stability`, `is_at_war`, `dominant_faction`, `conquered_this_turn`) and the two broadcast multiplier columns stay explicit. The record-batch is assembled from a `(name, pa type)` list in the same order. A test asserts `batch.schema` equals the pre-change schema field for field.

## 4. Compatibility
Pickles, dumps and checkpoints must be byte-identical: class qualnames unchanged, no new fields, `__getstate__`/`__setstate__` results identical per class (golden pickles, section 7). `model_json_schema` digest unchanged. CLI flags, viewer and import paths unchanged.

## 5. Pins and preflight (run `refactor_preflight.py` for each file; results below)
- **Enforced (7-31 witnesses; needs PIN-1/D1 option A or an inverse layer):** `agent_bridge.py` (7), `grain_reserves.py` (9) and `grain_reserves_state.py` (4), `grain_storage.py`/`_state`, `harvest_forecasts.py`/`_state`, `household_mobility_state.py`, `learning_services.py`/`_state`, `public_grain_shipments.py`/`_state`, `scholarship.py`/`_state`, `transaction_receipts.py`/`_state`, `models.py` (5).
- **Unpinned (reference-only):** the other 50 `*_state.py` files, `livelihoods_state.py`, `livelihoods.py`, `cities*.py`, `agent_movements*.py`, `workshops*.py`, `recovery_crews*.py`, `timber_*.py`, `commons_rules*.py`, `adaptive_livelihoods*.py`, `apprenticeship*.py`.
- Plan: PR 1-4 touch only unpinned files. PR 5 (pinned state/owner files) and PR 6 (`agent_bridge.py`) are blocked on PIN-1; do not run them under option B.

## 6. Classification
Behaviour-preserving refactor. Proof per batch: (a) golden-pickle round trip, (b) `snapshot_summary` byte equality on a scripted multi-turn run, (c) `scripts/turn_speed_identity.py run/compare` against the base tree, (d) focused module tests, (e) the oracle lane.

## 7. Tests
- New `tests/test_switch_state.py`: `bump_counter` variant matrix versus verbatim copies of the old bodies (including error type/message); `lane_active` truth table; `model_json_schema()` equal for every converted class versus a stored digest; mixin `__setstate__` over a pickle missing one field, one private attr.
- New `tests/test_switch_state_pickles.py` + `tests/fixtures/state_pickles/*.pkl`: for each converted class a pickle generated on the base commit; loading yields `model_dump()` and `__pydantic_private__` equal to the stored expectation; re-pickling yields identical bytes.
- `tests/test_agent_bridge.py`: add column-schema equality and a first-failure-order test (two bad columns in one civ).
- Existing: `test_state_checkpoints.py`, `test_run_checkpoint.py`, `test_checkpoint_replay.py`, per-module tests.

## 8. Risks, open questions, rollback
- Metaclass/MRO: a plain mixin before `BaseModel` is safe in pydantic v2, but `__setstate__`'s `super()` must reach `BaseModel`; test on `LazyResearchModel` and `_Record` bases separately.
- `PrivateAttr` defaults may be non-`None`; the generic fill must be compared per class with the old literals (test).
- Saving is modest in lines; keep a class unconverted if it needs a special case.
- Rollback: each PR is independent and revertable. Open: whether CON-1 changes `LIVELIHOODS_SWITCHES` first.

## 9. Size
About 150 lines added (`switch_state.py` plus tests ~350), roughly 700-900 removed across 55 modules, 3 lines each owner converted. Six PRs.
