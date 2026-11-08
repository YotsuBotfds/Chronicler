## 01 Turn loop and orchestration
**Map**
- `simulation.py` (2778 lines) owns `run_turn_result` (1891-2772, 882 lines), the per-phase functions and the accumulator flushes. `run_turn` (1865) is a thin wrapper.
- `main.py` (2824 lines) is the CLI: `execute_run` (549-1573, 1025 lines), `_configure_run` (396 lines), `_build_parser` (83 `add_argument` calls), `run_chronicle` (2013, legacy wrapper used by tests/test_e2e.py and tests/test_main.py).
- `action_engine.py` (1426): `ActionEngine.compute_weights` (1164-1372) is the weight chain; `_ContributorBuckets` (1036-1080) and `BUCKET_CEILINGS` (1031-1036).
- `accumulator.py` (213): `StatAccumulator` with five routing categories, `apply`, `apply_keep` (watermark), `to_shock_signals`, `to_demand_signals`.
- `events.py` (734), `utils.py` (290), `types.py` (27), `validate.py` (85, facade over validation CLI), `cpu_budget.py` (86), `__init__.py` (11).
- About 29 `_X_on(world)` gates and 128 function-local `from chronicler...` imports in `simulation.py` wire experimental systems into the loop.

**Findings**
1. [high] fragile: `except BaseException` at `simulation.py:2134` and `simulation.py:2326` catches KeyboardInterrupt and SystemExit along with real failures. The 2326 handler resets teaching work and does not log. The re-raise was not verified. Action: catch `Exception`, or re-raise after rollback, and log.
2. [med] bug/fragile: `simulation.py:2585-2588` swallows any `get_snapshot()` failure as `snap = None` with no log. Belief data is then computed from no snapshot. Action: log, or fail the turn in hybrid mode.
3. [med] fragile: `events.py:355` `except Exception: routes = []` is a "defensive for partial test worlds" fallback that also runs in production. Failures in trade-route lookup become silent empty routes. Action: narrow to the test-world case, or raise.
4. [med] fragile: `main.py:356` and `main.py:374` turn ImportError into `None` for the ecology and politics runtimes. A missing native module quietly changes the runtime path. Action: fail loudly in agent modes; keep the fallback only for `--agents=off`.
5. [med] complexity: the feature wiring in `run_turn_result` is copy-pasted. Each system is `if _X_on(world): from chronicler.X import tick_X; _emit(tick_X(world, acc=acc, agent_bridge=agent_bridge))`. Examples: maritime, nomads, campaigns, diplomacy, gp_agendas, cities, agent_movements, guilds, scholarship, grain_reserves, ritual_gatherings (2442-2550). Livelihoods has three hooks, each with its own `getattr(world,"livelihoods")` check (2283, 2335, 2526, 2535). Proposal: a phase registry of `(slot, gate, module, entry, kwargs)` executed in the existing explicit order, with the order kept in one table so RNG and flush placement stay visible. Keep explicit ordering; do not sort by name.
6. [med] complexity: `apply_keep()` runs three times (`simulation.py:2362`, `2557`, `2663`) with the watermark as the only guard. Its correctness depends on the third flush running after tech regression. Action: document the flush contract in one place and test that a keep change added after a flush is applied exactly once.
7. [med] complexity: about 40 dual-path sites use `if acc is not None: acc.add(...) else: <direct write>` (for example `simulation.py:324-353`, `446-450`, `1478-1487`, `action_engine.py:165-170`, `835-890`, `958`). Intentional, but a helper `_route(acc, civ_idx, civ, stat, delta, category)` that falls back to a direct write would remove most of it. Risk: aggregate-mode bit identity must be preserved (see 2.5x clamp semantics and `clamp` behaviour).
8. [med] bug/unverified: `apply_asabiya_dynamics` (`simulation.py:762-835`, called at 1458) and the region asabiya writes (757, 810) mutate `civ.asabiya` and regional asabiya directly. The accumulator docstring lists asabiya as a `keep` stat, but nothing routes it through `acc`. Whether this is intended is unverified. Action: either route it as keep or document the exemption.
9. [med] correctness, action_engine: the final absolute cap `max_allowed = base * K_WEIGHT_CAP` (`action_engine.py:1365-1370`, base 0.2 from line 46) applies to all modifiers, including the late ones (governance, finance, diplomacy, nomads, holy war, raider, aggression, war-weariness, peace, mule). None bypasses it. The contributor-bucket ceilings (trait 2.0, situational 2.5, tech_focus 1.5, faction 1.5) are enforced only when governance is on (`_ContributorBuckets.enabled`, 1036-1041). Without governance the buckets are inert, so the same world config gives different effective ceilings. The comments say finance, diplomacy and nomads are "pre-clamped" to 1.25x or 1.5x, but no clamp is inside the bucket code and the clamp must live in each `weight_modifiers` (unverified, not read).
10. [low] duplication: `StatAccumulator.apply` (145-156) and `apply_keep` (158-180) contain the same clamp/setattr body. Extract `_apply_change`. About 12 lines saved.
11. [low] dead-code (partly): `accumulator.DEMAND_SCALE_FACTOR = 1.0` (62, used once at 211) is a no-op multiplier. `events.roll_for_event` and `apply_probability_cascade` (`events.py:206-260`) are marked "no longer used by the turn loop". Grep: only `tests/test_events.py:4-46` uses them.
12. [low] legacy: `main.py:2099` and `2622` keep `--llm-actions` as a deprecated ignored flag. Removing it breaks old command lines, so keep it. `run_chronicle` (`main.py:2013`) is a legacy wrapper used only by tests.
13. [low] docs: comments carry fix tickets ("H-20 fix", "W10 fix", "C-1 fix", "T1-3", "M-AF1 #1") and phase labels drift. Governance is described as "Phase 8" but runs inside Phase 10 (1568). Phase 3b and the agent tick between 9 and 10 are unnumbered. Action: a single phase table in the module docstring.
14. [low] perf: `halve_positive_deltas` (`accumulator.py:107-143`) rescans the change list per stat. Fine at current sizes.
15. [low] test-gap: the `except` blocks above have no tests that inject failure (`BaseException`, `get_snapshot` raising). Unverified beyond grep.

**Phase order** (one turn, as coded in `run_turn_result`)
| Slot | Calls |
|---|---|
| pre | drain injections (`apply_injected_event`); start-of-turn snapshots; `prune_inactive_wars`; `ensure_faiths` |
| P1 Environment | `phase_environment`; `tick_epidemics` (if on); `check_black_swans`; `check_environmental_events`; trade-route snapshot; contact/maritime `observe_phase2` (agents off) |
| P1b economy (agents on) | `dispatch_mutual_aid`; `refresh_resource_yields`; `prepare_storage_work`; Rust economy batches; `with_economy_columns` (cities) |
| P2 Automatic | `apply_automatic_effects` (infra, maintenance, trade, specialization, black market, war cost, mercs); treasury tax; `pay_dues` (cities) |
| P3 Production | `phase_production`; `tick_finance` (3b) |
| P4 Technology | `tick_techniques` or `phase_technology` |
| P5 Action | `phase_action` (ActionEngine); `tick_maritime`; `tick_nomads`; `tick_campaigns`; `update_war_frequency_accumulators` |
| P6 | `phase_cultural_milestones` |
| P7 | `phase_random_events` |
| P8 | `phase_leader_dynamics` |
| P9 Ecology | livelihoods `before_ecology`; `tick_ecology`; `finish_turn_ledger`; livelihoods `after_ecology`; `tick_agents` (learning and livelihoods wrappers); `finish_health_care`; acc flush 1 |
| between 9 and 10 | Rust agent tick (one-turn latency, documented) |
| P10 Consequences | `phase_consequences` (movements, value drift, assimilation, religion, twilight absorption, politics, `tick_factions`, great persons, governance); then `tick_diplomacy`, `tick_gp_agendas`, `tick_cities`, `tick_agent_movements`, `tick_guilds`, `tick_scholarship`, livelihoods, `tick_grain_reserves`, `tick_ritual_gatherings`; acc flush 2; shocks to `pending_shocks` |
| post | tech regression; acc flush 3; `tick_artifacts`; provenance finish; agent-sea and contact observers; population check |

**Simulation depth**
- A typed phase registry would let a new system declare its slot, gate and inputs, and make the turn order inspectable from the CLI.
- Contributor buckets could be enforced without governance, so the same weight ceilings hold in every world.
- Religion, politics and the agent tick run on a one-turn lag; making lag explicit per subsystem would enable multi-turn timing studies.
- The accumulator could record provenance per change, which would let narration cite the stat deltas that caused an outcome.

**Streamlining candidates**
| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `events.py` `roll_for_event`, `apply_probability_cascade` (206-260) | delete | ~55 | Breaks `tests/test_events.py` (imports at lines 4-5, uses at 16-46). Pin status unverified (`tests/fixtures/reference_baselines/*/src/chronicler/` holds copies of older modules). No saved-bundle field. | low |
| `main.py` `run_chronicle` (2013-~2040) | delete after porting tests to `execute_run` | ~30 | Breaks `tests/test_e2e.py:5,26,64` and `tests/test_main.py:12,152-256`. Not a CLI flag. | low |
| `accumulator.py` `apply` / `apply_keep` shared body (145-180) | merge into `_apply_change` | ~12 | None. Must keep the watermark and UNBOUNDED_STATS behaviour. | low |
| `accumulator.py` `DEMAND_SCALE_FACTOR` (62, 211) | inline 1.0 | ~2 | None (grep: only accumulator.py). | low |
| `simulation.py` dual-path `acc`/direct writes (~40 sites) | extract `_route` helper | ~80 | Touches aggregate bit-identity and historical replay; checked by reference baselines (unverified which tests pin them). | high |
| `simulation.py` feature-hook blocks in `run_turn_result` (2442-2550 and P5-P9 gates) | registry table | ~150 | Changes ordering risk; saved-bundle compat unaffected if order kept. Touches `scripts/testing/native_shards_manifest.json` pins (unverified). | high |
| `main.py` `execute_run` (1025 lines) and `_configure_run` (396) | split into stages | ~0 (restructure) | CLI flags unchanged; saved-bundle resume paths (`checkpoint_resume`, legacy-state labels at 729, 2805) must stay. | high |
| `main.py` `--llm-actions` (2099, 2622) | keep | 0 | Removing breaks old command lines. Keep as deprecated. | low |
| `simulation.py` `apply_asabiya_dynamics` direct write (762-835) | route through acc, or document | ~0 | Changes flush timing; old bundles unaffected if values equal. | med |

**Confidence**
Verified by reading code and targeted grep: phase order, gates, accumulator routing, the weight cap and bucket logic, the broad-exception scan (AST, 22 handlers), `--llm-actions` and `run_chronicle` callers. Inferred or unverified: whether the `BaseException` handlers re-raise, whether the `weight_modifiers` functions clamp, and pin status of the candidates. The repository-wide unused-name scan (`work-01/usage.py`) was stopped for CPU reasons before it finished, so dead-code claims rest on targeted greps only, not on a full sweep.
