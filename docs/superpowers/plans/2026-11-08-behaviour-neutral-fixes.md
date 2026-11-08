# Behaviour-Neutral Fixes — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** land FIX-1 to FIX-7, FIX-9 and FIX-10 without changing the outcome of any valid run.
**Architecture:** small local edits; unpinned files first; pinned files only after PIN-1.
**Tech stack:** Python 3.13 (`.venv/bin/python`), pytest, Rust 1.85 (cargo in `chronicler-agents`).
**Prerequisites:** PRs 1-4 none. PR 5 needs PIN-1 (DEC-1 option A) merged, or an exact-inverse layer for each of `live.py`, `simulation.py`, `agent_bridge.py` (see `scripts/testing/reviewed_main_witness.py` and `livelihoods_layer_tool.py`). Spec: `docs/superpowers/specs/2026-11-08-behaviour-neutral-fixes-design.md`. Before any PR: `git fetch`, branch from `main`, run `.venv/bin/python scripts/refactor_preflight.py <files>`.

## File map
| File | Change | PR |
|---|---|---|
| `tuning/m53_baseline.yaml`, `m53_pass1_all.yaml`, `m53a_frozen.yaml` | `git mv` to `docs/validation/m53/` | 1 |
| `scripts/m53_baseline.py:141`, `README.md:261` | new path, new wording | 1 |
| `tests/test_tuning.py` (~211) | add clean-load test | 1 |
| `src/chronicler/historiography.py:474-501`, `languages.py:398-424` | `atomic_write_text` | 1 |
| `tests/test_historiography.py` (~611) | failure leaves no temp | 1 |
| `tests/test_food_accounting.py` (~57) | capture keeps residual 0 | 1 |
| `src/chronicler/livelihoods.py:707-955` | `_on` gates, generic mode loop | 2 |
| `tests/test_livelihoods_wiring.py` | orphan, saved, differential tests | 2 |
| `src/chronicler/llm.py`, `tests/test_llm.py` | timeout, truncation, budget, deadline | 3 |
| `chronicler-agents/src/wealth_transfer.rs`, `provisioning.rs`, `formation.rs`, `movements.rs`, `politics.rs`, `behavior.rs` | `Err` and comparators | 4 |
| `src/chronicler/live.py` | FIX-1, FIX-10 | 5 |
| `src/chronicler/utils.py`, `simulation.py`, `agent_bridge.py` | FIX-3 | 5 |
| `tests/test_live.py`, `test_agent_bridge.py`, `test_agents_off_determinism.py` | new cases | 5 |

## PR 1: Repository records, sidecar writes, food-accounting guard (FIX-4, FIX-5, FIX-2)
### Task FIX-4: tuning record files
- [ ] Step 1: Preflight `tuning/*.yaml scripts/m53_baseline.py README.md tests/test_tuning.py`; expect references only (docs/plans, historical).
- [ ] Step 2: `git mv tuning/m53_baseline.yaml tuning/m53_pass1_all.yaml tuning/m53a_frozen.yaml docs/validation/m53/` (create the directory). Do not edit contents. Keep `tuning/codex_m53_secession_threshold25.yaml`.
- [ ] Step 3: `scripts/m53_baseline.py:141` default becomes `docs/validation/m53/m53_baseline.yaml`. `README.md:261` becomes "Tuning override YAML (the M53 calibration gate file); frozen records are in docs/validation/m53/".
- [ ] Step 4: In `tests/test_tuning.py` after the UTF-8 test add:
  ```python
  @pytest.mark.parametrize("yaml_path", sorted(_REPO_TUNING_DIR.glob("*.yaml")), ids=lambda p: p.name)
  def test_repo_tuning_yaml_loads_without_unknown_keys(yaml_path):
      import warnings, chronicler.tuning as tuning
      with warnings.catch_warnings():
          warnings.simplefilter("error")
          tuning.load_tuning(yaml_path)
  ```
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_tuning.py -q` passes (one parametrized id remains). `rg "tuning/m53" src scripts tests` finds no reader.
### Task FIX-5: sidecar writes
- [ ] Step 1: Preflight `src/chronicler/historiography.py src/chronicler/languages.py` (references only).
- [ ] Step 2: In both `save_sidecar` replace the `if atomic: ... else: ...` tail with `atomic_write_text(path, text)`; import `from chronicler.artifact_io import atomic_write_text` at function scope. Keep the `atomic` parameter and its docstring ("accepted for compatibility; every write is atomic"). The `artifact_budget` branch is unchanged.
- [ ] Step 3: Test in `tests/test_historiography.py`: monkeypatch `os.replace` to raise `OSError`, call `H.save_sidecar(world, path, atomic=True)`, assert `ArtifactIOError` and `list(tmp_path.glob("*.tmp")) == []`. Repeat for `languages` in `tests/test_languages.py`.
- [ ] Step 4: Verify: `.venv/bin/python -m pytest tests/test_historiography.py tests/test_languages.py tests/test_checkpoint_replay.py -q`. Expected pass.
### Task FIX-2: capture guard (no source change)
- [ ] Step 1: In `tests/test_food_accounting.py` after line 57 add a test: build the world as in `test_public_relief_...`, append a `ReserveFlow(kind=CAPTURED, region=0, amount=2)` to `w.grain_reserves.flows` (set `flows_turn = w.turn`), call `capture_food_accounting`, assert `row['public']['captured'] == 2` and `balance_residual == pytest.approx(0)`. Add the comment "ownership transfer: stock unchanged, so not a residual term".
- [ ] Step 2: Verify `.venv/bin/python -m pytest tests/test_food_accounting.py -q`. Do not touch `food_accounting.py` (enforced pin).
- [ ] Step 3: Ledger: CONTINUATION note "FIX-2 audit claim not reproduced: CAPTURED moves ownership, not stock". Run `.venv/bin/python scripts/run_python_oracle_checks.py`. Commit "Fix sidecar writes; move M53 records; pin capture residual".

## PR 2: Livelihoods prerequisite checks (FIX-7)
### Task FIX-7
- [ ] Step 1: Preflight `src/chronicler/livelihoods.py` (references). List current refusal texts: `rg -n "requires --|conflicts with the saved" tests | cut -c1-160 > $SCRATCH/refusals.txt` and keep every one unchanged.
- [ ] Step 2: For each of the 17 gates in `livelihoods.py:731-801` (the `values["x"] is True` tests) change the condition to `_on(world, values, "x")`. Add helper:
  ```python
  def _refuse(values, name, message):
      saved = values[name] is not True
      text = message + (f"; this world has it on: pass --no-{name.replace('_','-')} to end it" if saved else "")
      raise (LivelihoodsRefusal if saved else ValueError)(text)
  ```
  and use it so the explicit-request message is byte-identical to today's.
- [ ] Step 3: Append before the function ends:
  ```python
  for key, (switch, field) in _CHOICE_FIELDS.items():
      given = getattr(args, key, None)
      if given is None: continue
      if not _on(world, values, switch):
          raise ValueError(f"--{key.replace('_','-')} requires --{switch.replace('_','-')}")
      sub = getattr(livelihoods_state(world), switch, None)
      if sub is not None and str(given) != str(getattr(sub, field)):
          raise ValueError(f"--{key.replace('_','-')} {given!r} conflicts with the saved world ({field}: {getattr(sub, field)!r})")
  ```
  It runs after the module `check_request` calls, so their messages win. Skip keys whose module owns the check only if a test shows a message change.
- [ ] Step 4: Tests in `tests/test_livelihoods_wiring.py`: (a) orphan `workshop_mode`, `repair_mode`, `commons_rule_mode` on a fresh world raise; (b) a saved world with `workshops` on resumed with `--agents off` raises `LivelihoodsRefusal`; (c) saved `operate` plus `workshop_mode='cost_only'` raises; (d) differential: for every catalog key with `requires`, compare the imperative pass/fail with `feature_catalog.unmet_requirements` over `agents` in `off`, `hybrid`.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_livelihoods_wiring.py tests/test_feature_catalog.py tests/test_feature_matrix.py tests/test_workshop_economics.py tests/test_residence_ledger.py tests/test_wealth_accounting.py -q`. Every failure is either a bug in the change or a test that resumes with a changed mode; list the second kind in the PR and ask the owner (spec section 8) before editing it.
- [ ] Step 6: `.venv/bin/python scripts/run_python_oracle_checks.py`. Commit "Check saved livelihoods state and orphan modes".

## PR 3: LLM clients (FIX-9)
### Task FIX-9
- [ ] Step 1: Preflight `src/chronicler/llm.py tests/test_llm.py`. Do not change default model ids.
- [ ] Step 2: Add `DEFAULT_TIMEOUT_S = 120.0`, `BATCH_DEADLINE_S = 86400.0`, `class LLMTruncated(RuntimeError)`, `class LLMBudgetExceeded(RuntimeError)`.
- [ ] Step 3: `LocalClient`: `OpenAI(base_url=..., api_key=..., timeout=DEFAULT_TIMEOUT_S)`. `create_clients`: `anthropic.Anthropic(timeout=DEFAULT_TIMEOUT_S, max_retries=0)`; `genai.Client(http_options=...)` (check the installed `google-genai` signature first; neither SDK is in `.venv`, install into a scratch venv or mark the kwargs unverified in the PR).
- [ ] Step 4: `AnthropicClient`/`GeminiClient.__init__` gain `max_total_tokens=None, max_calls=None`; `truncated_count = 0`. A `_check_budget()` runs at the top of `complete` and raises `LLMBudgetExceeded` when `total_input_tokens + total_output_tokens >= max_total_tokens` or `call_count >= max_calls`. After a response, `stop_reason == "max_tokens"` (Anthropic) or a MAX_TOKENS finish reason (Gemini) increments `truncated_count` and logs one warning; return the text as before.
- [ ] Step 5: `batch_complete(..., deadline_s=BATCH_DEADLINE_S, sleep=time.sleep, clock=time.monotonic)`: break the poll loop when `clock() - start > deadline_s`, print the batch id and return `[None]*len(requests)`.
- [ ] Step 6: Tests in `tests/test_llm.py` with `MagicMock` SDKs and a fake clock: timeout kwarg reaches the SDK constructor; a `max_tokens` stop bumps `truncated_count`; budget stops the third call; an endless `in_progress` batch ends at the deadline with all `None`; existing tests unchanged.
- [ ] Step 7: Verify: `.venv/bin/python -m pytest tests/test_llm.py tests/test_main.py -k "llm or Anthropic or batch or narrat" -q`. Expect pass; no network used.
- [ ] Step 8: Commit "Add LLM client timeouts, truncation counts, budget and batch deadline".

## PR 4: Rust money path and comparators (FIX-6)
### Task FIX-6
- [ ] Step 1: Preflight the six `.rs` files (references only). Build a fresh extension per `docs/DEVELOPMENT.md`; record the build identity.
- [ ] Step 2: Baseline before editing: `cargo test --locked --manifest-path chronicler-agents/Cargo.toml` and `.venv/bin/python scripts/turn_speed_identity.py run` into `$SCRATCH/before`.
- [ ] Step 3: `wealth_transfer.rs:459` `assert!(...)` becomes `if !(*amount >= 0 && *amount <= cash) { return Err("a food purchase above its payers' cash"); }`; `:475` becomes `let Some(left) = left else { return Err("a food sale by no living seller") };`. After computing `money.paid` for a region, if `money.paid > 0` and every `region.sales` weight is `<= 0`, return `Err("a food purchase with no sale")`. All three return before the pool is written (the writes start at the `updates` loop).
- [ ] Step 4: Replace the two `#[should_panic]` tests (~1184, 1195) with tests that assert `is_err()`, the message, and that `pool.wealth` and `wealth_transfer_log` equal their values before the call. Add a third for the no-sale case.
- [ ] Step 5: In each of `provisioning.rs` (275, 847), `formation.rs` (792), `movements.rs` (453, 455), `politics.rs` (1407), `behavior.rs` (91) add `fn cmp_f64(a: f64, b: f64) -> Ordering { (a + 0.0).total_cmp(&(b + 0.0)) }` (an `f32` twin where the key is `f32`) and use it. Do not use bare `total_cmp`: `-0.0` and `0.0` must stay equal so the tie-break key still applies. `behavior.rs:91` is a `max_by`; keep its direction.
- [ ] Step 6: Unit test per file: `cmp_f64(-0.0, 0.0) == Equal`, `cmp_f64(f64::NAN, 1.0)` is not `Equal` and does not panic, and a finite list sorts as before.
- [ ] Step 7: Verify: `cargo test --locked --manifest-path chronicler-agents/Cargo.toml` passes; rebuild the extension; `.venv/bin/python scripts/turn_speed_identity.py run` into `$SCRATCH/after` then `compare before after` reports identical; run the native Python tests `tests/test_household_retail_native.py tests/test_household_retail_native_ffi.py tests/test_agent_movements.py`. State in the PR that the 200-seed gate was not run and why (no outcome change intended).
- [ ] Step 8: Commit "Return Err from food settlement; total float comparators".

## PR 5: Live server and transient clears (FIX-1, FIX-10, FIX-3) — after PIN-1
### Task FIX-1
- [ ] Step 1: Preflight `src/chronicler/live.py` and confirm PIN-1 landed (the verdict must no longer list enforced witnesses) or the inverse layer is in the PR.
- [ ] Step 2: Add `_coerce_set_value(value)` returning `int | None` (catches `TypeError, ValueError, OverflowError`) and use it at `live.py:1131`. Before `live.py:1122`, reject non-`str` `stat` and `civ_name` with the existing error texts.
- [ ] Step 3: Tests in `tests/test_live.py` driving `make_live_pause` with real queues: `value` in `float('inf')`, `float('nan')`, `1e999`, `"Infinity"`, `[1]`, `{}` each produce one `error` status and keep the pause loop alive; `stat=["x"]` with a valid civ produces "Invalid stat". Verify: `.venv/bin/python -m pytest tests/test_live.py -q`.
### Task FIX-10
- [ ] Step 1: `LiveServer._start_error`; wrap `_run_loop` body in `try/except BaseException as exc: self._start_error = exc; ready.set(); raise`. `start()` raises `LiveServerStartError(str)` when `_start_error` is set or `ready.wait(5)` is False. In `run_live` (~1544) catch it, print `Live server could not start: ...` to stderr and return `None`.
- [ ] Step 2: `_scenario_file(name) -> Path`: resolve under `Path("scenarios").resolve()`, raise `ValueError("Scenario must be within scenarios/")` otherwise. Use it at `:1308` and `:1496` and in the batch config path (`:577`).
- [ ] Step 3: Wrap `resolved.read_text` plus `json.loads` plus `_validate_legacy_live_bundle` (`:761`, `:785`) in `await asyncio.to_thread(...)`; move `copy.deepcopy(self._init_data)` (`:822`) into the thread by deep-copying inside `_narrate_range_sync`'s caller helper while keeping the range check on a shallow read of `history`.
- [ ] Step 4: Tests: bind to a port held by a test socket and assert `start()` raises; a `../x.yaml` scenario is refused; `batch_load_bundle` on a 5 MB file does not block a concurrent `speed` message (use the `tests/live_session_harness.py`). Defer: reconnect-state merge, `client_lock` across `send`.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_live.py tests/test_live_integration.py tests/test_batch_websocket.py tests/test_live_checkpoints.py -q`.
### Task FIX-3
- [ ] Step 1: Preflight `utils.py simulation.py agent_bridge.py`.
- [ ] Step 2: Add `clear_region_transients(world)` to `utils.py` as in spec section 3. In `agent_bridge.py:547-571` keep the reads into locals, delete the inline clears and call the helper once after the last read. In `simulation.py:2379-2387` replace the loop with `clear_region_transients(world)`.
- [ ] Step 3: Tests: in `test_agents_off_determinism.py` run 3 off-mode turns on a seeded world with a staged catastrophe and a raided region and assert both fields are 0/False after each turn; in `test_agent_bridge.py` extend `test_catastrophe_deaths_clear_after_read` to `_raided_this_turn` over 3 builds.
- [ ] Step 4: Verify identity: `scripts/turn_speed_identity.py run` before (on `main`) and after, then `compare`; `.venv/bin/python -m pytest tests/test_agents_off_determinism.py tests/test_agent_bridge.py tests/test_needs_calibration.py tests/test_checkpoint_replay.py tests/test_live_checkpoints.py -q`; `.venv/bin/python scripts/run_python_oracle_checks.py`. If a checkpoint-bytes test fails because a private attribute value changed, record it and do not rewrite a hash.
- [ ] Step 5: Ledger: CONTINUATION entry listing FIX-1, FIX-3, FIX-10 (refusal and latent-clear fixes; no outcome change; identity cases and oracle lane run; 200-seed gate not run). Commit "Harden live commands and share the transient clear".

## Done when
- [ ] All five PRs merged in order; PRs 1-4 did not touch an enforced file.
- [ ] `scripts/run_python_oracle_checks.py`, `cargo test --locked`, and the identity compare pass on each PR.
- [ ] FIX-2 recorded as "not a bug" with its test; FIX-5 and FIX-7 owner answers recorded.
- [ ] `rg "partial_cmp.*unwrap" chronicler-agents/src` shows none in the six files; `tuning/` holds only loadable files.
- [ ] CONTINUATION updated; no pinned hash rewritten.
