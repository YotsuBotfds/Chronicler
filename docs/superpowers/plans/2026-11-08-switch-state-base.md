# SwitchState Base and Table-Driven build_signals — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** One mixin and shared helpers replace the per-module `_bump`, `_state`, `_lane_active`, `__setstate__`/`__getstate__` copies; `build_signals` validates through a column table. No output change.
**Architecture:** `src/chronicler/switch_state.py` (field-free `SwitchStateMixin`, `bump_counter`, `lane_active`, `sub_state_getter`, `health_holders`). Pydantic classes keep their fields and paths. Owner modules keep their private names as aliases.
**Tech stack:** Python 3.13, pydantic v2, pytest. Spec: `docs/superpowers/specs/2026-11-08-switch-state-base-design.md` (copy of the sibling spec).
**Prerequisites:** none for PR 1-4. PR 5 and PR 6 need PIN-1 (DEC-1 option A). Land after CON-1 or rebase on it (both touch `livelihoods_state.py`).

## File map
| File | Change |
|---|---|
| `src/chronicler/switch_state.py` | new |
| `tests/test_switch_state.py`, `tests/test_switch_state_pickles.py`, `tests/fixtures/state_pickles/` | new |
| `scripts/switch_state_identity.py` | new: golden pickles and summary dumps (run on base and on branch) |
| 50 unpinned `*_state.py` | base class `(SwitchStateMixin, BaseModel)`, drop `__setstate__`/`__getstate__` |
| owners of those states | `_state`/`_bump`/`_lane_active` become aliases |
| `cities.py`, `agent_movements.py` | shared `_q/_rng/_emit/_max_civs` (PR 4) |
| `adaptive_livelihoods.py` | one shuffle helper (PR 4) |
| pinned state/owner files (list in spec section 5) | PR 5 |
| `src/chronicler/agent_bridge.py` | column table (PR 6) |

## PR 1: Harness and base (tasks CON-2, step 1)
### Task CON-2.0: Golden corpus from the base commit
- [ ] Step 1: `.venv/bin/python scripts/refactor_preflight.py src/chronicler/*_state.py > $SCRATCH/preflight.txt`; record which are ENFORCED (spec section 5).
- [ ] Step 2: Write `scripts/switch_state_identity.py` with `dump DIR`: for every `*_state.py` class listed by walking `chronicler.livelihoods_state.LivelihoodsState` and the top-level `WorldState` fields: (a) build a populated instance (defaults plus two `bump`-style counter writes by direct dict assignment), (b) pickle it with the checkpoint pickler (`run_checkpoint._Pickler`), (c) also write a variant with each non-required field deleted from `__dict__` and each private attr removed (an "old pickle"), (d) record `model_dump()`, `__pydantic_private__`, `model_json_schema()` sha256 and `WorldState.model_json_schema()` sha256 (as `checkpoint_replay.py:130`). Output one pickle and one JSON per class.
- [ ] Step 3: Run it on the untouched base: `.venv/bin/python scripts/switch_state_identity.py dump tests/fixtures/state_pickles`. Commit the corpus with the script (small; keep under 1 MB, otherwise store only for the 20 classes converted in PR 2-3 and generate the rest at CI time against `main`).
- [ ] Step 4: Add `scripts/switch_state_identity.py check DIR`: loads every pickle with the checkpoint unpickler, compares dumps and private dicts, and re-pickles to compare bytes.
- [ ] Step 5: Base trees for later proofs: `git worktree add $SCRATCH/base main-at-start`; `scripts/turn_speed_identity.py run $SCRATCH/base_out --source-root $SCRATCH/base` once, reused by every PR.

### Task CON-2.1: `switch_state.py`
- [ ] Step 1: Create the module (no imports of other chronicler modules at top level):
  - `bump_counter(counters, key, amount=1, *, allowed=None, message=None, coerce=None, ndigits=None, zero=0, skip_zero=False)`: strict check first (`raise KeyError(message.format(key=key) if message else key)`), `if skip_zero and not amount: return`, `amount = coerce(amount) if coerce`, `value = counters.get(key, zero) + amount`, `counters[key] = round(value, ndigits) if ndigits is not None else value`. Add `float_only_round=True` mode for `maritime.py:416`.
  - `lane_active(world, name)` copied from `recovery_crews.py:158` using `importlib.import_module`.
  - `sub_state_getter(name)` returning `lambda world: getattr(getattr(world, "livelihoods", None), name, None)`.
  - `health_holders(world)` copied from `recovery_crews.py:226`.
  - `SwitchStateMixin` per spec section 3: `_FILL_DEFAULTS`, `_TRANSIENT`, `_BUMP`, `__setstate__`, `__getstate__` (only emit the `{**state, "__pydantic_private__": ...}` copy when a transient value is not None, exactly as `recovery_crews_state.py` does), `bump()`.
- [ ] Step 2: `tests/test_switch_state.py`: one test per `_bump` variant in spec section 2, comparing against a verbatim copy of the old function, with ints, floats, unknown keys, zero; `lane_active` truth table with a world stub; mixin `__setstate__` on a toy model for each `_FILL_DEFAULTS` mode.
- [ ] Step 3: Verify: `.venv/bin/python -m pytest tests/test_switch_state.py -q` passes.
- [ ] Step 4: Commit: "Add SwitchStateMixin and shared switch helpers (CON-2)".

## PR 2: Unpinned owners without state changes (CON-2 helpers only)
### Task CON-2.2: `_lane_active`, `_health_holders`, `_state`
- [ ] Step 1: Preflight each file below (all reference-only). In `workshops.py:232`, `recovery_crews.py:158`, `repair_projects.py:292`, `timber_supply.py:247`, `labour_reservations.py:42` replace the body with `_lane_active = switch_state.lane_active`; keep the name (`operating_wear.py:79,147` imports it). Remove now-unused `import_module` imports (`ruff`/`pyflakes`).
- [ ] Step 2: `apprenticeship.py:1191` and `recovery_crews.py:226`: `_health_holders = switch_state.health_holders` (leave `labour_reservations.health_rows` alone).
- [ ] Step 3: Replace the two-line `_state` in the 39 owner modules with `_state = sub_state_getter("<name>")`, converting only the ones whose body is the exact `livelihoods` lookup (use a script that matches the AST and lists skipped files; do not touch `checkpoint_replay._state`, `gp_agendas._state_cause`).
- [ ] Step 4: Verify: `.venv/bin/python -m pytest tests/test_workshops.py tests/test_recovery_crews.py tests/test_repair_projects.py tests/test_timber_supply.py tests/test_apprenticeship.py tests/test_operating_wear.py tests/test_labour_reservations.py -q` (names: use `ls tests | grep` if one differs); then `scripts/run_python_oracle_checks.py`; then `scripts/turn_speed_identity.py run $SCRATCH/new_out` and `compare $SCRATCH/base_out $SCRATCH/new_out` (expected: all 9 cases identical).
- [ ] Step 5: Commit: "Share lane_active, health_holders and sub-state getters (CON-2)".

## PR 3: Counters and mixin on unpinned states (CON-2)
Split into batches of about 8 modules; each batch is its own commit with its own proof.
### Task CON-2.3: Batch order
- [ ] Batch A (strict plain, simplest): recovery_crews, timber_supply, repair_projects, maintenance_obligation, infrastructure_condition, wealth_accounting, residence_ledger, attribution_records.
- [ ] Batch B (strict int-coerce): guild_leagues, household_retail, reform_services, relocation_costs, remittances, titled_trade, workshop_economics, war_requisition, veteran_reintegration, timber_orders.
- [ ] Batch C (lax or rounding): workshops, workshop_payroll, adaptive_livelihoods, learning_cohorts, movement_branches, operating_wear, apprenticeship, local_budgets, epidemic_care, clearing_protection, commons_rules, ritual_gatherings, maritime, public_health, food_allocation, harvest_cover, war_consequences, grain_convoys, watershed.
- [ ] Batch D (set aside last): `livelihoods_state.py` (switch-list fill; keep `_FILL_DEFAULTS = LIVELIHOODS_SWITCHES`), `cities`, `agent_movements`, `guilds`, `nomads`.
### Task CON-2.4: Per-module conversion recipe (repeat for each module in the batch)
- [ ] Step 1: Preflight the state file and owner; STOP if ENFORCED.
- [ ] Step 2: In `<name>_state.py`: `class X(SwitchStateMixin, BaseModel)`; delete `__setstate__`/`__getstate__`; set `_FILL_DEFAULTS` (True if the old one iterated `model_fields`, the tuple of names if it used `setdefault`, False if none existed), `_TRANSIENT = ("_turn",)` from the old getstate, and `_BUMP = {...}` from the old `_bump`. Do not touch any field, default factory, docstring or order.
- [ ] Step 3: In `<name>.py`: `def _bump(state, key, amount=1): state.bump(key, amount)` keeping the signature (including the `(counters, key, amount)` form of `clearing_protection.py:371` and `commons_rules.py:404`, which call `bump_counter` directly). If a module's `_bump` body does not match any variant (`diplomacy`, `public_health`), leave it.
- [ ] Step 4: Batch proof: `.venv/bin/python scripts/switch_state_identity.py check tests/fixtures/state_pickles` (all classes: dumps, privates, schema digests, repickled bytes equal); `pytest tests/test_state_checkpoints.py tests/test_run_checkpoint.py tests/test_checkpoint_replay.py tests/test_switch_state_pickles.py` plus each converted module's own test file; `scripts/turn_speed_identity.py run/compare` as in PR 2 with the feature switches on: add `--cli-arg --recovery-crews` style args per batch (see `scripts/livelihoods_screens.py` for the enable flags) and compare against a base run with the same args; `snapshot_summary` text diff in the identity script `dump` mode on a 60-turn run.
- [ ] Step 5: Commit per batch: "Use SwitchStateMixin in <batch> (CON-2)".
- [ ] Step 6: End of PR: `scripts/run_python_oracle_checks.py`. Expected: all chunks pass within 110 s (do not raise the limit).

## PR 4: Helper de-duplication (CON-14)
### Task CON-14
- [ ] Step 1: `adaptive_livelihoods.py`: extract `_shuffle_rows(world, state, homes, rows)` from the two blocks (`:~316-330`, `:~359-376`); keep `stable_hash_int("a6_shuffle", world.turn, aid)` and the `unshuffled` bump order. Test: parameterised test calling both paths with seeded rows against stored expected output generated on base.
- [ ] Step 2: `cities.py`/`agent_movements.py`: new `src/chronicler/settlement_util.py` with `q`, `rng(namespace, world, ns, *parts)`, `emit(...)`, `max_civs()`; keep local aliases so `agent_movements._q` etc. still resolve; `_bump` for these two uses `bump_counter(..., ndigits=4)`. Preflight shows both unpinned; check `scripts/agent_movements_identity.py` and `scripts/cities_identity.py` run/compare (expected identical).
- [ ] Step 3: `_controller`: first write a probe that, on worlds with duplicate civ names or None controllers, compares the scan form (`timber_orders.py:76`) with `civ_index_map` form; unify only if equal on all sampled seeds, else leave and record why.
- [ ] Step 4: Verify with the identity scripts above and `pytest tests/test_cities.py tests/test_agent_movements.py tests/test_adaptive_livelihoods.py -q`.

## PR 5: Pinned states and owners (blocked on PIN-1)
- [ ] Step 1: Confirm PIN-1 merged (witness lane frozen). If not, stop; do not add inverse layers.
- [ ] Step 2: Convert grain_reserves, grain_storage, harvest_forecasts, household_mobility, learning_services, public_grain_shipments, scholarship (including `LazyResearchModel` base: `class ScholarshipState(SwitchStateMixin, LazyResearchModel)`; add a test that lazy-load still works), transaction_receipts, with the PR 3 recipe. Scholarship needs `scripts/scholarship_identity.py run/compare`.
- [ ] Step 3: Verify as PR 3 plus the 200-seed gate is NOT required (no behaviour change); run each module's native test file only if the oracle lane lists it.

## PR 6: Table-driven `build_signals` (CON-10, blocked on PIN-1)
### Task CON-10
- [ ] Step 1: Preflight `src/chronicler/agent_bridge.py` (ENFORCED, 7 witnesses); stop unless PIN-1 merged.
- [ ] Step 2: Before editing, capture a golden: write `scripts/signals_golden.py` that builds `build_signals` batches for `sample_world`-style worlds with shocks, demands, gini and tithe (3 variants) plus the error text for 12 injected bad values (one per column, and a world with two bad columns). Save the base output.
- [ ] Step 3: Add `_Col` and `_CIV_COLUMNS` per spec section 3 beside `_validated_civ_signal` (`agent_bridge.py:344`); replace `:926-1000` loop body keeping the order: faction x4, shock x4, demand x5, means x3, gini, tithe. Keep lazy fetch lambdas (`d[3]` read at its turn). Keep the two multipliers after the loop.
- [ ] Step 4: Build the record batch from `_SIGNAL_SCHEMA = (("civ_id", pa.uint8()), ...)` in the existing order; leave a comment pointing at `chronicler-agents/src/ffi/schema.rs` (CON-5 will generate it).
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_agent_bridge.py tests/test_agent_bridge_stat_order.py tests/test_recovery_gini_numerics.py -q`; the golden compare (batches equal via `to_pylist`, schema equal, error strings equal); `scripts/turn_speed_identity.py run/compare` (9 cases identical). Native tests (`tests/test_connected_world_native_contracts.py`) run only in the native venv.
- [ ] Step 6: Commit: "Table-driven build_signals validation (CON-10)".

## Done when
- [ ] `switch_state_identity.py check` passes for every converted class, `model_json_schema` digests unchanged.
- [ ] `turn_speed_identity.py compare` identical after each PR; `run_python_oracle_checks.py` passes.
- [ ] No pinned hash rewritten; PR 5 and 6 only after PIN-1.
- [ ] CONTINUATION entry: "CON-2/CON-10 refactor, no correction"; CON-13 (fill defaults for classes without `__setstate__`) recorded as an open correction candidate.
- [ ] Net removal of at least 600 lines recorded in the PR description.
