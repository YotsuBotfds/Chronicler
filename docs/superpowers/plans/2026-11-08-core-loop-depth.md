# Core-Loop Depth — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** five default-off switches (DEP-1..DEP-5) from `docs/superpowers/specs/` copy of `2026-11-08-core-loop-depth-design.md`, plus a pre-registered evaluation. **Architecture:** one new module `src/chronicler/core_depth.py` holds all logic and readers; one optional `WorldState.core_depth` field; enforced files get one-line hooks only. **Tech stack:** Python/pydantic, pytest, viewer TypeScript types.
**Prerequisites:** DEC-1/PIN-1 (or a reviewed inverse layer per enforced file); CON-1 if landed (use the registry instead of hand-editing `batch_manifest.py`); COR-6 before any DEP-2 evaluation. No simulation is run while writing the plan; section "PR 5" runs the evaluation.

## File map
| file | change |
|---|---|
| `src/chronicler/core_depth.py` (new, unpinned) | `CoreDepthState`, readers, saturation, military, famine naming, inequality |
| `src/chronicler/models.py` (enforced) | `WorldState.core_depth`; `ChronicEpisode.peak`; `CivSnapshot.regional_inequality` |
| `src/chronicler/accumulator.py` (unpinned) | saturation in `apply` |
| `src/chronicler/simulation.py` (enforced) | asabiya wrap (`:753`, `:803-808`), military hook (after `:321`) |
| `src/chronicler/provenance.py` (unpinned) | peak, famine NamedEvent at close |
| `src/chronicler/culture.py`, `named_events.py` (unpinned) | propaganda gate and name |
| `src/chronicler/main.py` (enforced), `batch_manifest.py` (enforced), `run_checkpoint.py`, `live.py`, `feature_catalog.py` | five flags and wiring |
| `src/chronicler/analytics.py`, `viewer/src/types.ts`, `viewer/src/__fixtures__/featureCatalog.json` | metric series, optional type, catalog fixture |
| `scripts/core_depth_screens.py` (new), `scripts/seed_registry.json` | evaluation harness, seed reservations |
| `tests/test_core_depth.py` (new) and listed tests | see tasks |

## PR 1: Shell and DEP-5 (tasks DEP-5; shell for DEP-1..4)
### Task DEP-5: regional inequality metric
- [ ] Step 1: Preflight: `.venv/bin/python scripts/refactor_preflight.py src/chronicler/models.py src/chronicler/main.py src/chronicler/batch_manifest.py src/chronicler/run_checkpoint.py src/chronicler/live.py src/chronicler/feature_catalog.py src/chronicler/accumulator.py`. Record enforced counts (models 5, main 9, batch_manifest 31). If PIN-1 has not landed, create the exact-inverse layers first with `scripts/testing/reviewed_main_witness.py` as the model.
- [ ] Step 2: Create `core_depth.py`: `class CoreDepthState(BaseModel)` with `saturation, military, famine, named, inequality: bool = False` and `params: dict[str, float] = {}`; readers `saturation_enabled(world)` etc. using `getattr(world, "core_depth", None)`; `set_core_depth(world, **flags)`.
- [ ] Step 3: `models.py`: `WorldState.core_depth: CoreDepthState | None = Field(default=None, exclude_if=_is_none)` near `capacity_aware_refugees` (`:1225`); `CivSnapshot.regional_inequality: float | None = Field(default=None, exclude_if=_is_none)` after `gini` (`:1387`). Import cycle: define `CoreDepthState` in `models.py` and re-export from `core_depth.py` if needed.
- [ ] Step 4: `core_depth.regional_inequality(world, civ)`: for the civ's regions with population > 0, compute per-head yield with `ecology.aggregate_food_yield(region, yields, climate_phase, subsistence_base, world) * economy.aggregate_farm_productivity(world, region)`; yields from the same source `ecology._check_famine_yield` receives (read `ecology.py:1171-1190` to find it; if unavailable at snapshot time, store a per-turn `{region: yield}` dict on the module-level result of the turn, not on the world). Population-weighted Gini; `None` for fewer than two regions. Pure function, no RNG, no mutation.
- [ ] Step 5: `main.py:980` snapshot builder: pass `regional_inequality=core_depth.regional_inequality(world, civ) if inequality_enabled(world) else None`. Leave `gini` untouched (`validation_regression.py:453` averages it).
- [ ] Step 6: Flags (all five now, shell): `main.py:2270` pattern `--stat-saturation`, `--military-stock`, `--famine-episodes`, `--named-event-balance`, `--regional-inequality` (`BooleanOptionalAction`, `default=None`); `_configure_run` block after `main.py:1624-1627` calling `set_core_depth`; refuse `--military-stock` when `world.agent_mode == "hybrid"` or `"demographics-only"` (copy the refusal helper from `expansion_features.py:101`); add the five keys to `batch_manifest.SIMULATION_ARG_KEYS` (next to `capacity_aware_refugees`, `:90`), `run_checkpoint.py:291` block, `live.py:337/585/1400/1531` pass-through, and `FEATURE_GROUPS["Core depth"]` in `feature_catalog.py:85` with help text.
- [ ] Step 7: Viewer: add `regional_inequality?: number` to the civ snapshot type in `viewer/src/types.ts`; regenerate the catalog fixture the way `tests/test_feature_catalog.py:756` documents; add additive entries only.
- [ ] Step 8: Analytics: in `analytics.py` beside `extract_gini_trajectory` (`:1799`) add `extract_regional_inequality_trajectory` and register it next to `"gini"` (`:1378`); omit the key when no snapshot has the field.
- [ ] Step 9: Tests: `tests/test_core_depth.py` (Gini of equal yields is 0, of a skewed pair known value, None for one region, off-mode snapshot JSON has no key).
- [ ] Step 10: Verify: `.venv/bin/python -m pytest tests/test_core_depth.py tests/test_feature_matrix.py tests/test_feature_catalog.py tests/test_batch_manifest.py -q` (all pass; `test_existing_catalog_output_is_byte_identical` untouched); `npm --prefix viewer run test -- types` ; `npm --prefix viewer run lint`; `npm --prefix viewer run build`; `scripts/turn_speed_identity.py run` then `compare` against the pre-change run (all cases identical, switches off); `scripts/run_python_oracle_checks.py` (PASS, no limit change).
- [ ] Step 11: Ledger: CONTINUATION entry "added default-off core-depth switches (shell + DEP-5)"; commit `Add core-depth switch shell and regional inequality metric` with the attribution lines from the session reminder.

## PR 2: DEP-1 saturation
### Task DEP-1
- [ ] Step 1: Preflight `src/chronicler/simulation.py src/chronicler/accumulator.py`; confirm the inverse layer (PIN-1 or reviewed layer) exists for `simulation.py` before editing.
- [ ] Step 2: `core_depth.py`: `saturate_int_gain(world, stat, current, delta)` implementing `g(s)=1 (s<=K) else ((C-s)/(C-K))**p`, `eff=min(int(delta*g), C-current)`, only for `delta>0` and `stat in {"culture","economy"}`; params from `get_override(world, "depth.saturation.knee", 60)`, `.power`, add the keys to `tuning.py` constants following `K_*` style (check validation in `tuning.py` for unknown-key rules).
- [ ] Step 3: `accumulator.py` `apply` (`:145-159`): before `new_val = current + c.delta`, `delta = saturate_int_gain(...) if saturation_enabled(world) else c.delta` (fast path: one `getattr` outside the loop). Do not change `apply_keep` (culture/economy are not `keep`) or `add`.
- [ ] Step 4: Asabiya: `core_depth.saturate_asabiya_gain(world, s, delta)` = `delta*min(1,(1-s)/(1-knee))` for `delta>0`. Wrap in `_apply_asabiya_to_regions` (`simulation.py:753-759`, per region) and the folk-hero term (`:803-808`, `folk_bonus*0.1`). One-line edits.
- [ ] Step 5: Optional upkeep arm: in the DEP-2 turn hook (PR 3) add `acc.add(civ_idx, civ, stat, -upkeep, "guard")` for culture/economy above 90 when `depth.saturation.upkeep > 0` (default 0). Leave until PR 3.
- [ ] Step 6: Tests in `tests/test_core_depth.py`: table of (current, delta, eff); negative deltas unchanged; off-mode `apply` identical on a random change list; hybrid `apply_keep` path unaffected; a 100-turn aggregate world with only DEVELOP shows culture < 100 under the switch; `max_precap_weight` and `K_WEIGHT_CAP` clamp untouched (assert the engine constants).
- [ ] Step 7: Verify: `.venv/bin/python -m pytest tests/test_core_depth.py tests/test_accumulator.py tests/test_acc_hardening.py tests/test_action_engine.py -q`; `scripts/turn_speed_identity.py run/compare` (off-mode identical); oracle lane PASS.
- [ ] Step 8: Ledger + commit `Add default-off stat saturation (culture, economy, asabiya)`.

## PR 3: DEP-2 military stock
### Task DEP-2
- [ ] Step 1: Preflight `src/chronicler/simulation.py src/chronicler/war/armies.py src/chronicler/war/common.py`. Read how a civ's war status is known: `world.war_state` (campaigns) and `world.relationships`/active war markers used by `action_engine.py:372-440`; write `civ_at_war(world, civ)` once, test it on both legacy and campaign worlds.
- [ ] Step 2: `core_depth.military_tick(world, acc)`: for each living civ `i, civ` compute `target = T_peace + T_war*at_war + 0.1*(civ.population//10)` clamped; `muster = min(ceil(rate*(target-M)), civ.treasury//cost)` if `M<target`; `decay = (M-target)//10` if `M>target`; `acc.add(i, civ, "military", +muster or -decay, "keep")` and `acc.add(i, civ, "treasury", -muster*cost, "keep")`. Integer arithmetic only; process civs in index order. Params `depth.military.*`.
- [ ] Step 3: Hook one call in `simulation.py` after the maintenance loop (`:321`): `if military_enabled(world): core_depth.military_tick(world, acc)`. Not in agent modes (flag refuses; reader also returns False when `agent_mode in ("hybrid","demographics-only")`).
- [ ] Step 4: Tests: zero-military civ at war musters up to the cap in ~5 turns; broke civ stays at 0; peace decay toward `T_peace`; deterministic repeat; refusal in hybrid; `at war` on a campaign world.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_core_depth.py tests/test_war_*.py tests/test_action_engine.py -q`; `turn_speed_identity` compare; oracle lane.
- [ ] Step 6: Ledger + commit `Add default-off military stock and mustering`.

## PR 4: DEP-3 and DEP-4
### Task DEP-3
- [ ] Step 1: Preflight `src/chronicler/provenance.py src/chronicler/models.py`.
- [ ] Step 2: `models.py:787` `ChronicEpisode.peak: float | None = Field(default=None, exclude_if=_is_none)`.
- [ ] Step 3: In `provenance._gate` (`:868-901`) when `famine_enabled(world)` and `ev.event_type in ("famine","dearth")`, set `ep.peak = max(ep.peak or 0.0, depth)` where depth comes from a new optional `Event` attribute or, to avoid a schema change, from `core_depth.last_famine_depth[(turn, region)]` written by `ecology._check_famine_yield` at `:384-395` (ecology is enforced: prefer the side-dict set from the already computed `hunger` through a one-line call only if PIN-1 landed; otherwise derive depth from `region` fields after the fact: `1 - yield/threshold` is not recoverable, so then use `ep.count` and duration only and drop `peak` from the importance rule).
- [ ] Step 4: `_close_episodes` (`:904-926`): for a closed `famine` episode meeting `duration >= 3 or count >= 2`, append `NamedEvent(event_type="famine_episode", ...)` to `world.named_events` with name from `named_events.generate_famine_name(region, onset_turn, world)` (new, uses `_seed_rng(world.seed, onset_turn, "famine:"+region)` and `deduplicate_name`).
- [ ] Step 5: Tests: synthetic episode closes into one named event; two short episodes below threshold produce none; off-mode bundle identical; provenance state without `peak` loads.
- [ ] Step 6: Verify `tests/test_causal_provenance.py tests/test_core_depth.py` pass; `turn_speed_identity` compare.
### Task DEP-4
- [ ] Step 7: `named_events.py`: `named_event_gate(world, event_type, civ_name, region_name, before, after)`; propaganda rule: crossed a multiple of `depth.named.propaganda_stride` (5) in `foreign_control_turns`, or no earlier `propaganda_campaign` NamedEvent by this civ on this region in `depth.named.propaganda_window` (10) turns, via `history_index(world)` (extend it only if no lookup exists; read `history_index.py` first).
- [ ] Step 8: `culture.py:410-418`: capture `before = target.foreign_control_turns` prior to `:399`; wrap the `world.named_events.append` in the gate; when emitting under the switch use `generate_propaganda_name(civ, target, world, world.seed)`; the returned `Event` is unchanged.
- [ ] Step 9: Tests: only crossings/windowed first campaigns emit; Event still fires every time; names unique; off-mode identical; entropy helper in `analytics` computing normalised Shannon entropy over named types (shared with PR 5).
- [ ] Step 10: Verify `tests/test_culture.py tests/test_core_depth.py tests/test_narrative*.py -q`; oracle lane.
- [ ] Step 11: Ledger + commit `Add default-off famine episodes and propaganda named-event gate`.

## PR 5: Evaluation harness (no default change)
- [ ] Step 1: Append seed reservations to `scripts/seed_registry.json` (status `reserved`, program `core-loop-depth`): template development 5001-5020, pilot 5021-5036, held 5101-5148; procedural held 5201-5224. First re-read the registry maximum (4206 at design time) and the other 12 writers' reservations; move the block up on any collision. Run `scripts/screen_runner.py` seed check.
- [ ] Step 2: `scripts/core_depth_screens.py`: arms `off, sat, mil, fam, named, ineq, all`; metrics per spec section 6, computed from decoded bundles (`decode_bundle`): civ-turn share at culture 100 / economy 100 / asabiya >= 0.99; military-0 share and P(mil>0|war) from `civ_stats` plus relationship state; war share of `action_counts`; named famine count; top named-type share and normalised entropy; share of non-None `regional_inequality`; action-share L1 shift versus `off`. Guards: survivors, collapses, treasury, `max_precap_weight`.
- [ ] Step 3: Pre-register in `docs/superpowers/progress/core-loop-depth-prereg.md`: thresholds from the spec table, pilot-before-held rule, famine-threshold sweep arms (`K_FAMINE_YIELD_THRESHOLD` 0.08/0.10/0.12 via tuning YAML, audit table only).
- [ ] Step 4: Run pilot (seeds 5021-5036, aggregate 150 turns, `--agents off`), then held only if the pilot passes: `python scripts/core_depth_screens.py --cohort pilot ...`. Hybrid 200-turn arm for DEP-1 asabiya/3/4/5 on 8 held seeds. Record outputs outside git.
- [ ] Step 5: Promotion path (separate PR, not this plan): `python scripts/m53b_run_validation.py --profile full --output-root output/m53/core-depth-after` and `--worldgen procedural --profile full`, each against a fresh baseline on the same source; DEP-2 needs an agents-off arm. Never call the gate complete unless run.
- [ ] Step 6: Ledger: CONTINUATION entry listing arms, seeds, source revision, results or "not run".

## Done when
- [ ] Every switch is default off; `turn_speed_identity` compare is identical with switches off.
- [ ] No pinned hash rewritten; PIN-1 or reviewed inverse layers cover `simulation.py`, `models.py`, `main.py`, `batch_manifest.py`.
- [ ] Old bundles and checkpoints load; new fields omitted when unset.
- [ ] `test_existing_catalog_output_is_byte_identical` unchanged and passing; viewer test, lint, build pass.
- [ ] Oracle lane passes without raising the 110-second limit.
- [ ] Seeds reserved in the registry before use; evaluation report and CONTINUATION entry written; no default promoted without the 200-seed gate.
