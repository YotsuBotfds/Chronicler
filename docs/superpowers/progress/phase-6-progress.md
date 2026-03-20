# Phase 6 Progress — Living Society

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-03-19 (M47 Tier A + M47a + M47b-prep merged)

---

## Merged Milestones

### M36: Cultural Identity — merged, sticky flag fixed

- `_culture_investment_active` sticky flag fixed in `da0cb2d`. Pattern: read into local before return, clear attribute, use local in batch. Dead cleanup code after return deleted.

### M38a: Temples & Clergy Faction — merged

- `a199c40` — tithe truncated to int
- `0bee24e` — temple conquest lifecycle wired into production code

### M38b: Schisms, Pilgrimages & Persecution — merged (`67f1353`)

- All Phoebe review items (B-1 through G-4) resolved in implementation.
- Rust test RegionState initializers updated for M38b fields (`58f868d`, `3ebb62b`).
- Secession modifier and `--agents=off` compatibility verified (`9431276`).

### M39: Family & Lineage — merged

- Dynasty detection, extinction, and split wired into AgentBridge (`a235e68`).
- Dynasty context added to narrative prompt (`9e4b20c`).
- Dynasty integration test added (`20c9835`).
- Design decisions: inherit at birth (drift handles assimilation), parent-child only (no grandparent chain), purely narrative (dynasty_id is hook for future mechanics), Rust owns `parent_id` / Python owns dynasty logic.

### M40: Social Networks — merged

- 18 commits on `feat/m40-social-networks`. 79 tests passing.
- Rust `SocialGraph` with `SocialEdge` types + Arrow FFI (`get_social_edges` / `replace_social_edges`).
- Five formation functions: rivalry, mentorship (rewritten from leader-based to agent-source peers), marriage, exile bond (new), co-religionist (new).
- `dissolve_edges()` with death + belief-divergence rules.
- `form_and_sync_relationships()` coordinator in Phase 10.
- Named character scoring activated in `curate()` (`main.py` + `live.py`).
- Relationship context wired into narration pipeline.
- `character_relationships` removed from `WorldState`, `dissolve_dead_relationships` dead code removed.
- `origin_region` on `GreatPerson`, `relationships` on `AgentContext`.

### M41: Wealth & Class Stratification — merged

- Per-agent `wealth: f32` in Rust SoA pool. Multiplicative decay, MAX_WEALTH clamp.
- Binary `is_extractive()` dispatch for farmer/miner income (replaced by M42 modifier).
- Gini computed Python-side, one-turn lag. Class tension as 4th non-ecological penalty (priority-clamped under 0.40 cap).
- `conquered_this_turn` transient signal for soldier conquest bonus.
- Treasury tax, tithe swap deferred to M42 — now landed.

### M42: Goods Production & Trade — merged

- 5 commits on `m42-goods-production-trade` branch. 42 economy unit tests, 188 Rust tests passing.
- New `economy.py`: 3 categories (Food, Raw Material, Luxury), two-pass pricing (pre-trade for margins, post-trade for signals), log-dampened margin-weighted pro-rata trade allocation.
- Four RegionState FFI signals: `farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`.
- One CivSignals field: `priest_tithe_share`.
- Rust wealth tick: farmer = `BASE_FARMER_INCOME × modifier × yield`, merchant = `merchant_trade_income`, priest = `PRIEST_INCOME + priest_tithe_share`.
- Satisfaction: `food_sufficiency` penalty outside 0.40 cap, `merchant_margin` replaces `trade_route_count` term.
- M41 deferred integrations landed: treasury tax, tithe base swap, per-priest tithe share.
- `FARMER_INCOME`, `MINER_INCOME`, `MERCHANT_INCOME`, `MERCHANT_BASELINE`, `is_extractive()` removed from Rust.
- `trade_route_count` wired to actual boundary-pair counts (was hardcoded to 0).
- **Deferred:** Analytics price time series extractor (needs bundle format update). 200-seed regression (needs calibration values).

### M43a: Transport, Perishability & Stockpiles — merged

- 17 commits (`14f1eb4`..`4b7adff`). 48 M43a tests + 42 M42 tests = 120 total economy tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m43a-transport-perishability-stockpiles.md`
- `RegionStockpile` model with `dict[str, float]` goods, nested on `Region` (parallels `RegionEcology` pattern).
- Transport cost computation: terrain factors (6 terrains), river discount (0.5×), coastal discount (0.6×), winter modifier (1.5×). Pre-allocation margin reduction in `allocate_trade_flow()`.
- Per-good perishability: transit decay (post-allocation volume attrition), storage decay (per-turn with salt preservation). Salt proportional to salt-to-food ratio, capped at 50%.
- Stockpile sub-sequence in `compute_economy()` (steps 2g-2k): accumulate → food_sufficiency from pre-consumption stockpile → demand drawdown → storage decay → cap.
- `food_sufficiency` source changed from single-turn supply to pre-consumption stockpile (Decision 9). Signal value unchanged ([0.0, 2.0]), backward compatible at equilibrium.
- Conquest stockpile destruction (50% loss) in `_resolve_war_action()`.
- Stockpile initialization in `world_gen.py` (`INITIAL_BUFFER × population`).
- `extract_stockpiles()` analytics extractor.
- Conservation law: `EconomyResult.conservation` tracks production, transit_loss, consumption, storage_loss, cap_overflow. Exact global balance verified in test.
- **No Rust changes.** Entirely Python-side.
- **Key design decisions:** M43 split into M43a (infrastructure) / M43b (behavior) for calibration isolation. Emergent shock propagation via price/stockpile dynamics (no explicit shock state machine — M43b). Category-level pricing unchanged from M42; per-good tracking only for stockpile/decay.
- **Phoebe review passed.** I-1 (per-good decomposition single-slot assumption documented), I-2 (conquest integration gap noted), I-3 (import initialization clarified).

### M43b: Supply Shock Detection, Trade Dependency & Raider Incentive — merged (`f25d68c`)

- 14 commits on `feat/m43b-shock-detection` branch. 36 M43b tests, 252 total relevant tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m43b-shock-detection-trade-dependency.md`
- `EconomyTracker` class with dual EMA (α=0.33) for stockpile and import levels. Instantiated in `main.py`, persists across turns, passed to `run_turn()`.
- `detect_supply_shocks()`: delta trigger (30% drop from trailing avg) + absolute severity gate (`food_sufficiency < 0.8` for food). Non-food uses delta-only severity.
- `classify_upstream_source()`: checks import EMA drop + upstream partner stockpile drop. Returns None for local shocks or embargoes (no fallback attribution).
- 6 new `EconomyResult` fields: `imports_by_region`, `inbound_sources`, `stockpile_levels`, `import_share`, `trade_dependent`, plus `CATEGORY_GOODS` constant.
- `inbound_sources` tracking merged into existing trade flow accumulation loop (~5 lines).
- Trade dependency: `import_share = food_imports / max(food_demand, 0.1)`, threshold 0.6.
- Raider WAR modifier: scaled additive (`RAIDER_WAR_WEIGHT * min(overshoot, RAIDER_CAP)`), placed after holy war bonus, before streak-breaker and 2.5x cap. Stacks with holy war intentionally (Decision 8).
- 7 new `CAUSAL_PATTERNS` entries including `supply_shock → supply_shock` self-link for cascade chains.
- Narration: `economy_result` threaded through `narrate_batch` → `build_agent_context_for_moment()`. Early return relaxed to allow economy-source events. `build_agent_context_block()` renders trade dependency and shock context.
- `ShockContext` BaseModel, `shock_region`/`shock_category` optional fields on `Event` (structured metadata, no string parsing).
- `CivThematicContext.trade_dependency_summary` field added but population deferred — `CivThematicContext` is never constructed in current codebase (dead infrastructure).
- 2-turn transient signal test for `world._economy_result` (NB-2 from Phoebe review).
- **Phoebe implementation review:** B-1 (economy_result threading), NB-1 (CivThematicContext deferral documented), NB-2 (transient test added). All resolved in `2b22be3`.
- **No Rust changes.** Entirely Python-side.
- **Calibration constants:** `SHOCK_DELTA_THRESHOLD=0.30`, `SHOCK_SEVERITY_FLOOR=0.8`, `TRADE_DEPENDENCY_THRESHOLD=0.6`, `RAIDER_THRESHOLD=200.0` [CALIBRATE], `RAIDER_WAR_WEIGHT=0.15`, `RAIDER_CAP=2.0`. All `[CALIBRATE]` for M47.

### M44: API Narration Pipeline — merged (`dce271c`)

- 8 commits on `feat/m44-api-narration` branch. 15 new tests, all passing.
- **Spec:** `docs/superpowers/specs/2026-03-18-m44-api-narration-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m44-api-narration.md`
- `--narrator api|local` CLI argument with validation (5 conflict checks above `_run_narrate()` early return).
- `create_clients()` gains `narrator` parameter — returns `AnthropicClient` when `"api"`.
- `AnthropicClient` token tracking: 3 accumulators (`total_input_tokens`, `total_output_tokens`, `call_count`), console summary, bundle metadata (`narrator_mode`, `api_input_tokens`, `api_output_tokens`).
- `execute_run()` API path: noop per-turn narrator (extends existing `_simulate_only` pattern), reflections gated off entirely (`not _api_mode and should_reflect(...)`), post-loop curator + `narrate_batch()` before `agent_bridge.close()`.
- `gap_summaries` threaded to both `compile_chronicle()` and `assemble_bundle()`.
- First-failure warning in `narrate_batch()` — `logger.warning` on first exception per call, per-call local variable (not instance attr).
- Bug fix: `_run_narrate()` reads `events_timeline` key from bundles (was `events`, which didn't match `assemble_bundle()`'s output key).
- Pre-existing test mock fixed: `test_complete_calls_anthropic_api` now includes `usage` fields (prevents MagicMock `__radd__` corruption of accumulators).
- **Phoebe implementation review passed.** NB-1 (batch token bleed across seeds — low urgency edge case), NB-2 (usage mock — fixed in `a559c2b`).
- **No Rust changes.** Entirely Python-side. No simulation determinism impact.
- **M44 deliverables still pending:** ERA_REGISTER A/B experiment (pre-implementation, 4 conditions), 20-seed quality comparison (post-implementation, controlled pipeline). Both are manual evaluation tasks.

### M45: Character Arc Tracking — merged (`6c997f3`)

- 10 commits on M45 implementation. Arc classifier with 8 archetypes, deeds population at 9 mutation points, curator scoring (+1.5 arc, +2.5 completion), arc summaries via API follow-up calls, dead character filter relaxed.
- **Spec:** `docs/superpowers/specs/` (M45 spec)
- **Plan:** `docs/superpowers/plans/` (M45 plan)

### M47: Phase 6 Tuning Pass — Tier A + M47a + M47b-prep merged (`d99b178`)

- 1 commit, 36 files changed, 835 insertions, 225 deletions. 532 Python tests pass, 188 Rust tests pass, 2 pre-existing failures.
- **Spec:** `docs/superpowers/specs/2026-03-19-m47-tuning-pass-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-19-m47-tuning-pass.md`
- **Tier A:** Civ-removal fix — `world.civilizations.remove(civ)` deleted from `check_twilight_absorption()`. Dead civs stay in list (`len(regions)==0` convention). Dead-civ guards at 13 critical loop sites + `_write_back()`.
- **M47a consumer wiring:** 8 multipliers wired (all default 1.0, no behavioral change). Python: K_AGGRESSION_BIAS (action_engine), K_TRADE_FRICTION (economy `friction_multiplier` param), K_RESOURCE_ABUNDANCE (ecology yields), K_SECESSION_LIKELIHOOD (politics prob), K_TECH_DIFFUSION_RATE (tech cost division). Rust FFI: `cultural_drift_multiplier` and `religion_intensity_multiplier` as CivSignals fields, wired in culture_tick.rs/conversion_tick.rs via tick.rs lookup.
- **M47a severity cap:** `get_severity_multiplier(civ, world)` composes base × tuning, capped at 2.0. 11 existing call sites updated to pass `world`. `world` param is optional (defaults to base-only for backward compat).
- **M47a severity fix:** 25 missing severity sites fixed across 9 files (politics 11, simulation 4, action_engine 3, leaders 2, climate/culture/ecology/emergence/succession 1 each). 7 new tests in `tests/test_severity.py`.
- **M47a tatonnement:** 3-pass Walrasian price iteration in `compute_economy()`. Damping=0.2, per-pass clamp [0.5, 2.0], convergence threshold 0.01. All [CALIBRATE] for M47c.
- **M47a Pydantic cleanup:** Removed misleading `ge=/le=` Field constraints from `models.py` (silently ignored with `validate_assignment=False`). Tests expecting validation-time rejection removed.
- **M47b-prep:** Gini on CivSnapshot (populated from `AgentBridge._gini_by_civ` via `enumerate` index). `CivThematicContext` deleted (dead infrastructure). `NarrationContext.civ_context` field removed. `region_map` cached property on WorldState via `PrivateAttr` (inline replacements deferred). 9 analytics extractors added.
- **Multiplier validation:** `load_tuning()` rejects multiplier values ≤ 0.
- **Bit-identical:** `--agents=off` determinism verified at default multipliers.
- **Python-side consumers also wired:** `culture.py` (drift), `religion.py` (conversion rate, schism threshold inverse scaling with 0.10 floor, persecution intensity).

---

## Ready for Implementation

### M47b-run: 200-Seed Health Check — not yet run

Task 12 from the plan. Determinism gate passed. Needs:
1. Run `--seed-range 1-200 --turns 500 --civs 4 --regions 8 --agents hybrid --simulate-only --batch 200`
2. Apply extractors, compare against spec criteria table
3. Generate health check report

### M47c: Calibration + Narrative — 3-day time-box

All multiplier consumers and extractors are wired. M47c tunes actual values.

### Session Handoff (2026-03-19 — M47 implementation session)

**Uncommitted from prior sessions (still present):**
- `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md` — M44/M47 enrichment notes, M46 dropped
- `docs/superpowers/specs/2026-03-17-m39-parentage-dynasties-design.md` — minor edit
- `src/chronicler/live.py` — minor edit

**Hanging test investigation (for next agent):**
- `tests/test_bundle.py::TestBundleSize::test_500_turn_bundle_under_5mb` hangs with M47 changes. On clean tree it completes in <1s. The test runs `execute_run(args)` with 5 civs, 10 regions, 500 turns. Benchmark shows 1ms/turn for the simulation loop alone, so the simulation isn't slow. The hang is likely in `execute_run`'s narration/reflection path — possibly `create_clients()` trying to connect to local LLM (LM Studio), or the reflection interval triggering LLM calls. The tatonnement adds ~3x economy cost but benchmarks show that's still sub-ms. Suspect the issue is in the `execute_run` code path around narration/reflection that the test doesn't mock out, and some M47 change (possibly the `Civilization` default field changes removing `Field(ge=0, le=1000)` for `population`) triggers a different code path. `test_m36_regression.py` and `test_main.py` also hang — same pattern (full `execute_run` integration tests). Recommendation: check if the `population: int = 0` default change (was `Field(ge=0, le=1000)`) causes `Civilization()` construction to fail somewhere that previously got a validation error, or if removing the `carrying_capacity` Field constraint breaks Region construction in test fixtures.

**Next steps:**
- Diagnose and fix the 3 hanging test files
- Run M47b 200-seed health check (Task 12)
- ERA_REGISTER A/B experiment (manual, deferred from M44)
- M47c calibration pass

---

## Known Gotchas / Deferred Items

- **Transient signal rule (CLAUDE.md):** Clear BEFORE return in builder functions. 2+ turn integration test required for every new transient signal.
- **M34 farmer-as-miner:** Resolved. M41 added `is_extractive()` dispatch; M42 replaced it with market-derived `farmer_income_modifier`.
- **M44 (API narration):** Merged. ERA_REGISTER A/B experiment and 20-seed quality comparison still pending (manual evaluation tasks, not implementation).
- **~~Viewer extensions (M46)~~ — Dropped 2026-03-17.** Phase 7 redesigns the viewer from scratch (M62). All Phase 3-6 viewer requirements preserved as inventory in Phase 7 roadmap.
- **M44: Sequential batch token accumulation bleeds across seeds.** `--batch N --narrator api` shares one `AnthropicClient` across seeds; seed 2's bundle metadata shows seed 1+2 cumulative tokens. Low urgency — edge case, tokens for operator awareness not billing. Fix: reset accumulators per `execute_run()`, or snapshot deltas. Phoebe NB-1.
- **M44: `_run_narrate()` agent context still limited.** Pre-existing gap — `narrate_batch()` call in `_run_narrate()` doesn't thread `great_persons`, `social_edges`, `gini_by_civ`, `economy_result`. API and local narration both equally affected. Not M44 scope.
- **Spec-ahead strategy:** M44 merged. M45 design complete (spec doc pending).
- **M42 analytics deferred:** Price time series extractor needs bundle format update to persist `EconomyResult` prices into turn snapshots. Land when bundle schema is designed (M43 or M62).
- **M42+M43a 200-seed regression pending:** Calibration values (PER_CAPITA_FOOD, RAW_MATERIAL_PER_SOLDIER, LUXURY_PER_WEALTHY_AGENT, LUXURY_DEMAND_THRESHOLD, MERCHANT_MARGIN_NORMALIZER, TAX_RATE, BASE_FARMER_INCOME, plus M43a transport/decay/stockpile constants) need tuning before regression is meaningful.
- **M43a: `RegionStockpile` is persistent, `RegionGoods` remains transient.** CLAUDE.md note "M43 adds stockpile persistence" is now landed. `food_sufficiency` source changed from single-turn supply to pre-consumption stockpile.
- **M43a: `resource_effective_yields` not `resource_yields`.** `compute_economy()` line 595 was referencing `region.resource_yields[0]` (a property that may not exist on all Region instances). Fixed to `region.resource_effective_yields[0]` during implementation.
- **M43a: Salt preservation denominator excludes salt.** `total_food` in `apply_storage_decay()` uses `FOOD_GOODS if g != "salt"`. Salt doesn't preserve itself.
- **M43a: Per-good import decomposition assumes single resource slot.** Inline comment documents M41 Decision 14 dependency. Multi-slot milestone would need broader decomposition.
- **M43a: Conquest stockpile destruction wiring untested by M43a tests.** Formula is tested; integration point covered by existing war/action tests (which now operate on stockpile-bearing regions).
- **M43a: `--agents=off` stockpile accumulation test not written.** Phoebe recommended. Low priority.
- **Phase 7 roadmap:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — draft, M47 dependency for sequencing. Phase 8-9 horizon extracted to `chronicler-phase8-9-horizon.md`.
- **Phase 8-9 brainstorm enrichments:** Most brainstorm "new systems" are content for existing milestones, not new milestones. Disease → M55, diaspora → M50, legal systems → M63, education → M63/M64, language → M68, espionage → M71. See enrichment notes on each milestone.
- **~~Tier 1 multiplier consumers not wired~~** — Fixed in M47 (`d99b178`). All 8 consumers wired.
- **~~`--tuning` YAML loading was missing for single runs.~~** Fixed in prior uncommitted main.py, now committed.
- **~~M43b: `CivThematicContext` population deferred.~~** Deleted entirely in M47 (`d99b178`).
- **M43b: `trade_dependent_regions` not scoped to moment civs.** Phoebe O-1. The spec says filter by controller, but `build_agent_context_for_moment` lacks world access. Currently includes all trade-dependent regions. Low impact — narration context is already scoped to agent events.
- **M43b: `_get_adjacent_enemy_regions()` rebuilds region_map per call.** Phoebe O-2. Fine at current civ counts (~10). If civ count grows, cache `region_map` on `ActionEngine`.
- **M42+M43a+M43b+M44+M45+M47 200-seed health check pending.** Six milestones unvalidated. M47b extractors landed, health check run (Task 12) not yet executed. Absolute thresholds, not delta regression.
- **~~CRITICAL: Civ-removal stale-index bug.~~** Fixed in M47 Tier A (`d99b178`). Dead civs stay in list, 13 guards added.
- **~~25 severity multiplier sites missing.~~** Fixed in M47 (`d99b178`). All 25 sites now use `get_severity_multiplier(civ, world)`.
- **K_PEAK_YIELD has no consumer.** Defined in `tuning.py` but never read anywhere. No yield cap exists in `compute_resource_yields()`. K_RESOURCE_ABUNDANCE scales linearly with no upper bound. Downstream `food_sufficiency` clamp at [0, 2.0] is the effective guard.
- **~~`AgentBridge._gini_by_civ` keyed by int, not name.~~** Fixed in M47 (`d99b178`). Snapshot uses `enumerate` index.
- **M45: `gp.deeds` is defined but never populated.** The field exists on GreatPerson (models.py:334), narrative pipeline reads `gp.deeds[-3:]` (narrative.py:173), but nothing ever appends. M45 fixes this with 9 mutation points.
- **M45: `gp.region` not auto-synced from agent snapshot.** Only set at major transitions (creation, conquest, hostage release). Agent migration doesn't update GP region. Affects Wanderer classification — use `notable_migration` event count instead of region field.
- **M45: `build_agent_context_for_moment()` excludes dead characters.** Line 162 filters `if not gp.active`. Death moments (the most important arc events) don't get accumulated arc context in the prompt. M45 relaxes filter to include characters whose names appear in moment event actors.
- **M45: Character events include character name in `actors`.** Verified: `character_death` actors=[name, civ.name], `exile_return` actors=[name], `notable_migration` actors=[name], `conquest_exile` actors=[gp.name, conquered_civ, conqueror_civ]. The `gp.name in e.actors` filter works for character-specific events. Civ-level events (war, trade, rebellion) only have civ names — classifier operates on character events only.
- **Fullscale Phoebe review (2026-03-18):** CLAUDE.md line counts + file table updated, simulation.py docstring aligned, dead `derive_food_sufficiency()` removed, Phase 7 viewer scope estimate corrected.
- **M47: 3 integration test files hang after Pydantic cleanup.** `test_bundle.py::TestBundleSize::test_500_turn_bundle_under_5mb`, `test_m36_regression.py`, `test_main.py` — all run full `execute_run()` integration. Complete in <1s on clean tree, hang indefinitely with M47 changes. The simulation loop benchmarks at 1ms/turn, so tatonnement is not the cause. Suspected root cause: removing `ge=/le=` Field constraints changed default values (e.g., `population: int = 0` was `Field(ge=0, le=1000)`, `stability: int = 50` was `Field(ge=0, le=100)`) — test fixtures may rely on old default behaviors or the Civilization constructor may now accept states that trigger infinite loops in the simulation. Investigation started but not completed. See session handoff for details.
- **M47: `region_map` inline replacements deferred.** The `world.region_map` cached property is added but the ~19 inline `{r.name: r for r in world.regions}` rebuilds are NOT yet replaced. Safe — property works alongside inline rebuilds. Replace opportunistically. `invalidate_region_map()` calls not yet added at region mutation sites.
