# Economy Depth and Measurement — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** Close the tax/tithe/margin money legs behind a default-off switch, measure household food access, add feature profiles, harden validation, and finish screen-runner scope.
**Architecture:** New modules plus thin hooks; the money seam (`money.py`) already supports collections and pairwise bills, so no Rust change in v1. Spec: `docs/superpowers/specs/2026-11-08-economy-depth-and-measurement-design.md`.
**Tech stack:** Python 3.13, pydantic state modules, pytest, GitHub Actions, TypeScript viewer reader.
**Prerequisites:** PR 1 and PR 5 and PR 6 have none. PR 2 (DEP-6) and PR 4 (DEP-8) need PIN-1 (or a reviewed inverse layer) because they edit `simulation.py`, `main.py`, `batch_manifest.py`. PR 3 (DEP-7) needs none. The hash-seed CI step in PR 1 needs COR-1 merged first (step 6 is conditional).

Preflight command (every PR, every touched file): `.venv/bin/python scripts/refactor_preflight.py <paths>`; record the verdict in the PR body.

## File map
| File | Change |
|---|---|
| `scripts/check_seed_registry.py` (new) | gate-range and development-reuse checks |
| `scripts/m53b_run_validation.py` | call the check; `--hash-seed` (default 0) |
| `src/chronicler/validation_multiplicity.py` (new) | `holm_adjust` |
| `src/chronicler/validation_io.py` | report `holm_p` beside `sign_test_p` (~2159); `best_of` docstring |
| `.github/workflows/hashseed-sweep.yml`, `regression-smoke.yml` (new) | CI |
| `tests/test_batch_parallel_real.py` etc. (new) | see steps |
| `src/chronicler/closed_money.py`, `closed_money_state.py` (new) | DEP-6 |
| `simulation.py` (~2188), `factions.py` (~425), `agent_bridge.py` (~1003), `wealth_accounting.py`, `feature_catalog.py`, `main.py` | hooks |
| `src/chronicler/household_access.py` (+`_state`), `analytics.py`, `viewer/src/lib/householdAccess.ts` | DEP-7 |
| `src/chronicler/feature_profiles.py` (new), `main.py`, `batch_manifest.py` | DEP-8 |
| `tests/test_screen_frozen_evidence.py` (new), `docs/` | CON-8 |

## PR 1: Validation hygiene (task DEP-9)
### Task DEP-9: seed registry, multiplicity, best_of, smoke, real pool
- [ ] Step 1: Preflight `scripts/m53b_run_validation.py src/chronicler/validation_io.py src/chronicler/validation_oracles.py scripts/seed_registry.json src/chronicler/batch.py`. Expected: "references found", no ENFORCED line.
- [ ] Step 2: Registry check. Create `scripts/check_seed_registry.py` with `check(profile, seeds, stratum) -> list[str]`: the seed range must equal a `restricted_gate` entry (`gate200-t`: 42-241 template; procedural 42-141 per `restricted_ranges`); every entry with status `run` that intersects `restricted_ranges` must have `use` containing "development" or be the gate entry, else report it (print as warnings first; make the new test list the current offenders as an explicit allowlist so existing history does not fail). Call it at the start of `m53b_run_validation.py` for profile `full` (refuse on a mismatch, warn otherwise).
- [ ] Step 3: Read `tests/test_screen_runner.py:1066-1072` and the registry hash function `screen_runner.py:1149-1160`: `unresolved` is inside the hashed JSON only if it is in `entries`/`restricted_ranges`; it is not (the hash covers those two keys), so the stale m58b note in `unresolved` may be rewritten. Verify by running only `pytest tests/test_screen_runner.py -k registry -q` after the edit. If it fails, revert the edit.
- [ ] Step 4: Multiplicity. Create `validation_multiplicity.py::holm_adjust(pvalues: list[float]) -> list[float]` (step-down, monotone, capped at 1). In `validation_io.py` near line 2159 add `holm_p` to each pairing result using the family of the 5 `NEEDS_PAIRINGS` p-values of one snapshot method. Do not change PASS. Document the family in the function docstring.
- [ ] Step 5: best_of. Add to `run_needs_oracle_best_of` a docstring paragraph "selection-biased: re-scoring only; never a gate". Add a test in `tests/test_validate.py` (or new file) asserting `rg`-style that `validation_gate.py` and `m53b_run_validation.py` do not mention it. Do not touch `validation_oracles.py:19` or the goldens.
- [ ] Step 6: Hash-seed sweep. In `m53b_run_validation.py` `_build_env` (line ~97) read an optional `--hash-seed` (default `"0"`, so the default env is byte-identical). Add `.github/workflows/hashseed-sweep.yml` (push + dispatch): matrix `PYTHONHASHSEED: [0, 1, 2, random]`, runs `scripts/m53b_run_validation.py --profile determinism-off --hash-seed ${{ matrix.h }}` and uploads digests; a final job compares them. Only enable after COR-1 (otherwise the known `war_requisition` order makes it red): put `if: false` guard with a TODO tied to COR-1 until then.
- [ ] Step 7: Scheduled smoke. Add `.github/workflows/regression-smoke.yml` (cron nightly, plus dispatch): build the wheel as in `validation-gate.yml`, run 4 template seeds x 100 turns hybrid via `m53b_run_validation.py --profile subset --seeds 4 --turns 100` (confirm flag names with `--help` first), compare summary metrics to `tests/fixtures/regression_smoke.json` (create from one local run; record the commit and platform in the file). Measure runner minutes on the first dispatch and record in the PR; abort if over 15 minutes.
- [ ] Step 8: Real pool test. `tests/test_batch_parallel_real.py` (marker `real_process`): run `batch.py` with `--parallel 2`, 2 seeds, 5 turns, `--agents off --simulate-only`, once with `PYTHONHASHSEED=0` and once `=1` (via `subprocess`, env), assert identical `batch_summary` and result order. Because the oracle guard blocks child processes, do not add it to `scripts/run_python_oracle_checks.py` chunks; add a CI step in `hashseed-sweep.yml` that runs `pytest -m real_process`. Register the marker in `pyproject.toml`/`pytest.ini` (check where markers live).
- [ ] Step 9: Verify. `pytest tests/test_seed_registry_check.py tests/test_validation_multiplicity.py tests/test_validate.py tests/test_screen_runner.py -q`; `python scripts/run_python_oracle_checks.py`. Expected: pass; goldens unchanged (`git diff --stat tests/fixtures/validation_parity` empty); `actionlint` passes on both new workflows (the repo has `workflow-semantics.yml`).
- [ ] Step 10: Ledger. CONTINUATION entry (tooling, no outcome change). Commit message: "Validation hygiene: registry check, Holm report, hash-seed sweep, smoke regression".

## PR 2: Closed money (task DEP-6)
Prerequisite: PIN-1 merged.
### Task DEP-6 stage A: tax and tithe legs
- [ ] Step 1: Preflight `src/chronicler/simulation.py src/chronicler/factions.py src/chronicler/agent_bridge.py src/chronicler/money.py src/chronicler/wealth_accounting.py src/chronicler/feature_catalog.py src/chronicler/main.py`. If an ENFORCED pin remains, stop and request PIN-1.
- [ ] Step 2: State. `closed_money_state.py`: `ClosedMoneyState(BaseModel)` with `tax_carry: dict[int,int]` (milli), `counters`, `last_frame`; follow `grain_reserves_state.py` for the `*_on(world)` helper and backfill.
- [ ] Step 3: Money seam. In `money.py` add purposes `merchant_tax`, `tithe_collection` to `PYTHON_PURPOSES`-style registration as aliases of an existing native code (`NATIVE_ALIASES`, line ~90), choosing batches disjoint from that code's users (e.g. 5_000_000 + civ). Add a seam test that the registration passes `check_book`.
- [ ] Step 4: `closed_money.py`: `collect_tax(world, agent_bridge, economy_result, acc)` reading one fresh wealth snapshot (merchants of each civ: `occupation == 2`, `civ_affinity == idx`), building one collection bill per civ (lines = `floor(TAX_RATE*wealth*1000)` milli), paying via `money.pay`, crediting `acc.add(civ_idx, civ, "treasury", whole_units, "keep")` (keep category) with sub-unit remainder in `tax_carry`.
- [ ] Step 5: Hook at `simulation.py:2188`: `if closed_money_on(world): collect_tax(...) else: _apply_treasury_tax_from_economy(...)` (existing function untouched). Clear nothing transient (none created).
- [ ] Step 6: Tithe. In `agent_bridge.py` before the `priest_tithe_share` array (~1003) call `closed_money.priest_shares(world, economy_result)` which multiplies by `closed_money.tithe_priest_fraction` (new tuning key, default 0.5, added to the tuning key set without touching pinned `tuning.py` text if possible; otherwise a `world.closed_money` field). In `factions.py` at 424-428 use `closed_money.treasury_tithe(...)` when on: debit merchants (collection bill `tithe_collection`) for `(1 - fraction) * TITHE_RATE * base` and credit exactly the applied whole units. Pass `acc` as today.
- [ ] Step 7: Identity frame. In `wealth_accounting.py` add `money_supply` to the per-turn frame (new `_Book` method next to `_titled_trade`, line ~505): `opening = sum(wealth)+sum(treasury)`, listed mint, listed burn, `closing`; `book.closure("closed_money", "tax and tithe legs net to zero", debited, credited_x1000 + carry_change)` using the existing `closure` API (`wealth_accounting.py:386`). Mint/burn table declared as a constant dict with source per entry.
- [ ] Step 8: Switch. Catalog entry `closed_money` (requires hybrid) in `feature_catalog.py`; `--closed-money/--no-closed-money` in `main.py`; refuse with `--agents off` and with checkpoints lacking the state (follow the `grain_reserves` pattern). Add to batch manifest optional keys (omitted when unset, like `batch_manifest.py:268-271`).
- [ ] Step 9: Verify. New `tests/test_closed_money.py`: (a) off: world digest equal to baseline (`scripts/turn_speed_identity.py run` then `compare` on the 9 cases, expected identical); (b) on: per turn, merchant wealth lost == treasury gained x 1000 + carry change; (c) tithe debited once (priests' signal plus treasury part == one debit); (d) multi-turn: the carry survives a checkpoint resume; (e) zero priests, zero merchants, ceiling-refused edge cases. Run `pytest tests/test_closed_money.py tests/test_money.py tests/test_wealth_accounting*.py tests/test_audit_batch_d.py -q`, then `python scripts/run_python_oracle_checks.py`. (Native runs need the venv described in `scripts/cloud_setup.sh`; do not run simulations in the writing session.)
- [ ] Step 10: Ledger. CONTINUATION entry "closed_money stage A: default-off, off identity proved, no defaults changed".
### Task DEP-6 stage B: merchant margin
- [ ] Step 11: In `closed_money.py` add `settle_margin(world, agent_bridge, economy_result)` called after `reconstruct_economy_result` (`simulation.py:2116-2120`): per origin region, pairwise `cargo_sale` bill (batch `6_000_000 + region`) from destination-region non-merchant households (weight = wealth) to the origin's merchants (equal); record `margin_unfunded`; set `economy_result.merchant_trade_incomes[region] = 0.0` for settled regions so `agent_bridge.py:730` sends zero.
- [ ] Step 12: Tests: money moved == money received (use the seam's `check_book`); buyer lacking funds limits payment; payer/payee overlap (a merchant cannot also be a payer: exclude merchants). Verify as in step 9.
### Task DEP-6 stage C (held evaluation, no code merge): register new seeds
- [ ] Step 13: Add held and pilot entries to `scripts/seed_registry.json` via the program's normal process (new `screen: "CM1"`), declare primaries (tithe/treasury leg residual; merchant wealth Gini; poorer-half shortfall per 1,000) and the equal-cost control (a fiat removal of the same total). Run through `SR.Screen`. Promotion needs the 200-seed gate (`m53b_run_validation.py --profile full`, with a before/after report): never mark complete unrun.

## PR 3: Household access (task DEP-7)
### Task DEP-7: metrics
- [ ] Step 1: Preflight `src/chronicler/food_allocation.py src/chronicler/household_retail.py src/chronicler/analytics.py src/chronicler/livelihoods.py src/chronicler/feature_catalog.py viewer/src/lib/foodAllocation.ts`.
- [ ] Step 2: Read the package contract (`livelihoods.py` ~100-110: `<name>_active`, `snapshot_summary`) and copy the registration points for `food_allocation` (`livelihoods.py:175, 257-262, 734, 937-954, 997, 1093`). Create `household_access_state.py` (counters only) and `household_access.py` with `after_agent_tick` hook placed after `food_allocation.after_agent_tick` and `household_retail.after_agent_tick`.
- [ ] Step 3: Compute from `food_allocation` state (`totals`, `regions`) and the retail frame rows: `calories_met_share`, `shortfall_depth`, `below_floor_share`, poorer/richer ratio, `priced_out_person_turns` cumulative, `priced_out_deficit`; `None` where unobserved. Do not read native internals; no Rust change. Round like `food_allocation.snapshot_summary` (6 digits).
- [ ] Step 4: Refuse enabling without `--food-allocation` (as the catalog requirement), default off.
- [ ] Step 5: Analytics: add a lazy extractor in `generate_report` (pattern of the 14 existing hooks) producing a `household_access` section only when the part exists, so default report bytes are unchanged (assert in a test).
- [ ] Step 6: Viewer: `viewer/src/lib/householdAccess.ts` reader with `absent`/`malformed`/ok statuses (copy `foodAllocation.ts` shape) and a test in `viewer/src/lib/__tests__/`.
- [ ] Step 7: Verify: `pytest tests/test_household_access.py tests/test_food_allocation*.py tests/test_analytics*.py -q`; `npm --prefix viewer run test -- householdAccess`, `npm --prefix viewer run lint`, `npm --prefix viewer run build`. Expected pass; flag-off bundle byte-identical.
- [ ] Step 8: Ledger and commit "Household access metrics (default off, observation only)". Open question for the owner: the weights of a joint food-and-care welfare primary.

## PR 4: Feature profiles (task DEP-8)
Prerequisite: PIN-1 (edits `main.py`, `batch_manifest.py`).
### Task DEP-8
- [ ] Step 1: Preflight `src/chronicler/main.py src/chronicler/batch_manifest.py src/chronicler/feature_catalog.py tests/test_feature_matrix.py`.
- [ ] Step 2: Create `feature_profiles.py`: `PROFILES` (five names). `classic`: derive every catalog bool as False and each choice setting as its default, programmatically from `feature_catalog.feature_entries()`; `new-world`: the current defaults (derive from the parser defaults and `DEFAULT_ENABLED_FOR_NEW_WORLDS` modules: write a test that proves equality with a plain no-flag parse); the other three explicit dicts of catalog keys. `expand(name) -> dict`, raising on unknown names.
- [ ] Step 3: `main.py`: add `--feature-profile` (choices from `PROFILES`); before `parse_args`, pre-parse it with `parse_known_args`, validate with `validate_features(expand(name), surface)` (surface from `feature_catalog.batch_surface` or `live_surface`, whichever matches the run), and `parser.set_defaults(**expanded)`. Explicit flags then win.
- [ ] Step 4: `batch_manifest.py`: add optional keys `feature_profile` and `feature_profile_features` to the manifest config only when set (mirror lines 268-271); do not add them to `SIMULATION_ARG_KEYS` unconditionally. Accept `feature_profile` in the batch config; the `validate_batch_features` conflict rule (`:532`) applies to the expanded keys.
- [ ] Step 5: Tests `tests/test_feature_profiles.py`: every profile passes `validate_features`; `classic` plus no other flag == a run with all `--no-X` (compare parsed namespaces); explicit `--no-governance` overrides a profile that enables it; manifest without a profile is byte-identical to before (compare with a stored manifest); unknown name errors. `tests/test_feature_matrix.py::test_existing_catalog_output_is_byte_identical` (~96) must still pass untouched.
- [ ] Step 6: Verify: `pytest tests/test_feature_profiles.py tests/test_feature_matrix.py tests/test_batch_manifest*.py tests/test_main*.py -q`; `scripts/turn_speed_identity.py run/compare` (default args identical).
- [ ] Step 7: Ledger; commit "Add --feature-profile".

## PR 5: Screen-runner scope (task CON-8)
- [ ] Step 1: Preflight `scripts/screen_runner.py scripts/productive_recovery_screens.py scripts/livelihoods_screens.py scripts/connected_world_screens.py`.
- [ ] Step 2: Re-run the AST overlap measure (shared names between `screen_runner.py` and each program file; expected 18, 6, 1) and put the table in the PR body. Do not edit any of the four scripts.
- [ ] Step 3: Add `tests/test_screen_frozen_evidence.py` pinning `sha256` of `scripts/productive_recovery_screens.py` and `scripts/livelihoods_screens.py` (compute now and paste; the test states these are frozen preregistration evidence and that a change needs a new file instead).
- [ ] Step 4: Add a state-parse test: write a minimal `metrics.jsonl`, `derived.jsonl`, `source.txt` per the layout in `screen_runner.py:1576-1680` and assert `SR.report`/identity compare read them (use the existing fixtures in `tests/test_screen_runner.py` if present; do not write to `output/`).
- [ ] Step 5: Docs: state in `docs/` (the screens page named in `docs/README.md`) that `screen_runner.py` is the one runner, and that editing it changes the `runner` hash compared between pilot and held (`screen_runner.py:1140-1160`); list unspent cohorts first.
- [ ] Step 6: Verify: `pytest tests/test_screen_runner.py tests/test_productive_recovery_screens*.py tests/test_cw*_screen.py tests/test_screen_frozen_evidence.py -q`; the registry hash asserts at `tests/test_screen_runner.py:1066-1072` unchanged.
- [ ] Step 7: Commit "Pin frozen screen scripts; document single runner".

## PR 6: Optional Rust hardening for closed money (follow-up, task DEP-6 stage D, only if the owner wants native counters)
- [ ] Step 1: After PR 2 evaluation, add native mint/burn counters in `tick.rs` wealth phase and `wealth_transfer.rs`; bump the checkpoint state version (`ffi/mod.rs:656-662`), keep an old-version reader; `cargo test` in `chronicler-agents`; rebuild into the separate venv. Not started until PR 2 results are in.

## Done when
- [ ] Every default-path identity run (`turn_speed_identity.py compare`) is identical with all new switches off.
- [ ] `run_python_oracle_checks.py` passes; viewer test, lint and build pass for DEP-7.
- [ ] DEP-6 legs net to zero per turn in tests; margin stage reported separately.
- [ ] Held evaluation (seeds registered, primaries, equal-cost control) written down; 200-seed gate not claimed unless run.
- [ ] Holm values reported, PASS unchanged; registry check, hash-seed sweep and smoke workflows pass `actionlint`.
- [ ] CONTINUATION entries added; no pinned hash rewritten.
