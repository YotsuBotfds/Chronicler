# Phase 6+7 Progress — Living Society + Depth Track

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-03-20 (M50b merged to main)

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

### M48: Agent Memory — merged (`136c93e`)

- 14 commits on `feat/m48-agent-memory` branch (12 implementation + 1 Phoebe fix + 1 test gap fill). 241 Rust tests, 48+ Python tests.
- **Spec:** `docs/superpowers/specs/2026-03-19-m48-agent-memory-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-19-m48-agent-memory.md`
- **Phoebe reviews:** Plan review (5 blocking fixes pre-implementation), implementation review (1 blocking fix: conquest source_civ), final pass (clean).
- **Rust (chronicler-agents):**
  - `memory.rs` (new, 389 lines): MemoryEventType enum (14 types), MemoryIntent, gate bits, decay hot path (integer-only), eviction (min-intensity), half-life conversion, compute_memory_satisfaction_score(), compute_memory_utility_modifiers(), agents_share_memory() (M50 interface), write_all_memories(), clear_memory_gates().
  - `pool.rs`: 7 SoA memory fields (50 bytes/agent). Zero-init in both spawn branches.
  - `agent.rs`: ~45 calibration constants ([CALIBRATE M53]), 2 STREAM_OFFSETS reserved (900, 1300).
  - `tick.rs`: Memory decay first, 11 intent collection sites across all tick phases, parent-to-child reverse index for DEATH_OF_KIN, consolidated write last.
  - `satisfaction.rs`: `memory_score` field on SatisfactionInputs, 5th-priority penalty clamping inside 0.40 cap.
  - `behavior.rs`: Memory utility modifiers wired into evaluate_region_decisions() (7 event types → rebel/migrate/switch/stay).
  - `region.rs`: 3 transient boolean fields (controller_changed_this_turn, war_won_this_turn, seceded_this_turn).
  - `ffi.rs`: 3 signal columns parsed (both init + update branches), get_agent_memories() pymethod.
- **Python:**
  - `models.py`: 4 GreatPerson fields (mule, mule_memory_event_type, utility_overrides, memories).
  - `agent_bridge.py`: 3 transient signal columns in build_region_batch() with clear-before-return, Mule detection in _process_promotions() (7% probability, 9 event mappings), memory sync per tick.
  - `action_engine.py`: get_mule_factor() with 25-turn window + 10-turn fade, Mule weight loop (after peace dividend, before streak-breaker, before 2.5x cap), 0.1x suppression floor.
  - `politics.py`: _seceded_this_turn signal in check_secession().
  - `narrative.py`: MEMORY_DESCRIPTIONS (12 templates), render_memory() with vivid/fading descriptors, Mule context rendering.
- **Key design decisions:** Consolidated write phase (no same-turn feedback), conquest source_civ = conquering civ (not agent's own), memory inside 0.40 cap as 5th priority, multiplicative Mule boost.
- **Phoebe observations (non-blocking):** Promotion intent deferred (Python-side, no Rust write path), Victory memories not civ-filtered (minor — losers in region also get Victory), `default_decay_factor()` recomputes powf/ln per write (cold-path acceptable).

### M49: Needs System — merged (`ae05b92`)

- 8 commits on `feat/m49-needs-system` branch. 268 Rust tests, 6 Python tests, all passing.
- **Spec:** `docs/superpowers/specs/2026-03-20-m49-needs-system-design.md` (658 lines, 13 sections)
- **Plan:** `docs/superpowers/plans/2026-03-20-m49-needs-system.md` (1056 lines, 8 tasks)
- **Brainstorming:** 5 design questions, each individually Phoebe-reviewed + holistic cross-decision review. 3 blocking issues found and resolved in holistic review (utility stacking cap, needs-as-independent-trigger, missing architectural decisions).
- **Rust (chronicler-agents):**
  - `needs.rs` (new): NeedUtilityModifiers struct, decay_needs (linear subtraction), restore_needs (proportional to deficit), clamp_needs, update_needs entry point, compute_need_utility_modifiers (threshold-gated), social_restoration pre-M50 proxy.
  - `pool.rs`: 6 SoA f32 fields (24 bytes/agent). Spawn at STARTING_NEED=0.5 in both branches.
  - `agent.rs`: 37 calibration constants ([CALIBRATE M53]) — 6 decay, 6 threshold, 6 weight, 16 restoration, 3 infrastructure.
  - `tick.rs`: `update_needs()` inserted between wealth_tick and update_satisfaction (step 0.75).
  - `behavior.rs`: `personality_modifier` made `pub`. Need utility modifiers wired after M48 memory modifiers, before NEG_INFINITY gates. Per-channel NEEDS_MODIFIER_CAP=0.30. Autonomy deficit accelerates loyalty drift (multiplier on negative drift only).
  - `ffi.rs`: `get_agent_needs(agent_id)` pymethod returning `Option<(f32,f32,f32,f32,f32,f32)>`.
- **Python:**
  - `models.py`: `GreatPerson.needs: Optional[dict] = None` (None in aggregate mode — no serialization diff).
  - `agent_bridge.py`: Needs sync in hybrid branch after memory sync. 6-tuple → named dict.
  - `narrative.py`: NEED_DESCRIPTIONS (6 templates), render_needs() with LOW/satisfied labels, wired into build_agent_context_for_moment + build_agent_context_block.
- **Key design decisions:** 6 needs (sharp Safety/Autonomy split), hybrid restoration (binary for bools, proportional for f32s), uniform linear decay, per-agent restoration conditions for diversity, threshold-gated utility modifiers `(THRESHOLD - need).max(0) * WEIGHT`, needs can independently trigger rebellion (explicit decision), needs-only cap 0.30 (does not retroactively affect M38b/M48), Autonomy uses civ_affinity (political, not ethnic), memory-needs coupling deferred to M53.
- **M53 calibration flags (10):** persecution triple-stacking, famine double-counting, needs-only rebellion rate (<5%), need activation fraction (peacetime 10-20%, crisis 40-70%), migration sloshing, sawtooth oscillation, duty cycle per need, social proxy adequacy, negative modifier trapping, Autonomy assimilation loop.

### M50a: Relationship Substrate — merged (`a4d68f8`)

- 12 commits on `feat/m50a-relationship-substrate` branch + 2 Phoebe fix commits.
- **Spec:** `docs/superpowers/specs/2026-03-20-m50a-relationship-substrate-design.md`
- **Rust (chronicler-agents):**
  - `relationships.rs` (new): BondType enum (Mentor=0..Grudge=7), SoA helpers (find_relationship, write_rel, swap_remove_rel, find_evictable, upsert_directed, upsert_symmetric), is_protected/is_positive_valence predicates.
  - `pool.rs`: 5 SoA relationship fields (65 bytes/agent). Sentinel init (bond_types = [255; 8]).
  - `tick.rs`: Kin auto-formation at birth (form_kin_bond), sentiment drift at phase 0.8, stale-parent-slot fix (ids check in birth loop).
  - `ffi.rs`: apply_relationship_ops (4 op types via Arrow batch), get_agent_relationships (per-agent FFI), get_social_edges (M40 projection), replace_social_edges (deprecated shim with diff-based translation), kin_bond_failures counter with PyO3 getter.
  - `agent.rs`: 8 drift/kin constants, RELATIONSHIP_STREAM_OFFSET=1100 registered in collision test.
- **Python:**
  - `models.py`: `GreatPerson.agent_bonds: Optional[list] = None`
  - `agent_bridge.py`: apply_relationship_ops wrapper, agent_bonds sync in per-GP loop.
- **Key design decisions:** Single truth source (per-agent SoA, not SocialGraph). M40 `get_social_edges()` is a projection, `replace_social_edges()` is a deprecated diff-based shim. Kin-only Rust-native formation; all other formation via Python ops (transitional — M50b changes this). UpsertSymmetric(Kin) explicitly blocked. `formed_turn` preserved on re-upsert.

### M50b: Relationship Emergence & Cohorts — merged (`50301ea`)

- 12 commits on `feat/m50b-relationship-emergence` branch (8 implementation + 3 review fixes + 1 spec/plan docs). 376 Rust tests, 17/18 Python narrative tests (1 pre-existing failure).
- **Spec:** `docs/superpowers/specs/2026-03-20-m50b-relationship-emergence-cohorts-design.md` (Phoebe-reviewed, 2 passes)
- **Plan:** `docs/superpowers/plans/2026-03-20-m50b-relationship-emergence-cohorts.md`
- **Phoebe implementation review passed.** B-1 (death dissolution counter) and B-2 (char_names scope) fixed. User review found 3 additional issues: `since_turn` key mismatch, dissolved edges dropped in M50b path, directed capacity prefilter — all fixed.
- **Rust (chronicler-agents):**
  - `formation.rs` (new, ~1600 lines): `cultural_similarity()`, `compatibility_score()`, 6 per-type gate functions, `FormationCandidate`/`FormationStats` structs, `formation_scan()` with staggered cadence (hash-based shuffle, pair iteration, early rejection cascade, triadic closure, per-agent/per-region budgeting), `death_cleanup_sweep()`, `belief_divergence_cleanup()`, `mix_hash()`, `has_shared_positive_contact()`, `build_belief_census()`, `evaluate_pair()` (returns Vec for multi-bond-per-pair), `attempt_bond()`.
  - `tick.rs`: Death cleanup at phase 5.1 (post-demographics), formation scan at phase 8 (last operation before return). Return type changed to 3-tuple `(Vec<AgentEvent>, u32, FormationStats)`.
  - `ffi.rs`: `get_relationship_stats()` (19 keys: 5 formation counters + 1 kin delta + 4 distribution metrics + 8 bond_type_counts + 1 death dissolution), `get_all_relationships()` (Arrow RecordBatch bulk export).
  - `agent.rs`: 27 formation constants + `LIFE_EVENT_DISSOLUTION: u8 = 6`.
  - `pool.rs`: `synthesis_budget: Vec<u8>` dormant field (1 byte/agent).
  - `memory.rs`: `agents_share_memory_with_valence()` (signed intensities for Grudge gate).
  - `needs.rs`: Social-need blend `(1-α)*proxy + α*bond_factor` with `SOCIAL_BLEND_ALPHA=0.0` (early return, zero perf cost).
  - `tests/test_m50b_formation.rs`: 14 integration tests (staggered scheduling, friend formation, cap enforcement, determinism, transient signal 2-turn test, death cleanup, belief divergence).
- **Python:**
  - `agent_bridge.py`: `rust_owns_formation = True`, dissolution event collection (event_type=6 → `dissolved_edges_by_turn`).
  - `simulation.py`: `form_and_sync_relationships()` gated off when `rust_owns_formation`.
  - `main.py`: `--relationship-stats` CLI flag (parsed but not wired to consumer).
  - `narrative.py`: `rel_type_names` widened for Kin/Friend/Grudge, M50b bond source swap from `gp.agent_bonds` with sentiment descriptors (deep/strong/mild/fading), unnamed target filtering, dissolved edges consumed in M50b path.
  - `analytics.py`: `extract_relationship_metrics()` extractor.
- **Key design decisions:** Deterministic formation (no RNG consumed, stream offset 1100 reserved for M53 probabilistic). Multi-bond-per-pair (Friend + CoReligionist can form simultaneously). Directed bonds only need source-side capacity. Formation scan uses post-demographics alive_slots. `evaluate_pair()` returns Vec (all eligible types), not Option (first match). Dissolution events carry bond_type in `target_region` field (dead target's agent_id unavailable — O-3 deferred).
- **Phoebe observations (non-blocking):** O-1 (`check_friend` evaluates compatibility before shared memory — negligible cost difference), O-2 (`id_to_slot` rebuilt per-region instead of hoisted — minor perf), O-3 (dissolution events lack dead target's agent_id — known plan issue #2), O-4 (`--relationship-stats` flag not wired to consumer — deferred).

---

## In Progress

### M51: Multi-Generational Memory — spec + plan complete, ready for implementation

- **Spec:** `docs/superpowers/specs/2026-03-20-m51-multi-generational-memory-design.md` (Phoebe-reviewed 2 passes + user review 1 pass, all fixes applied)
- **Plan:** `docs/superpowers/plans/2026-03-20-m51-multi-generational-memory.md` (Phoebe-reviewed 1 pass + user review 1 pass, all fixes applied)
- **Commits this session (design only, no implementation):**
  - `185edd3` — M51 design spec
  - `71b3f51` — Phoebe review fixes (2 blocking + 4 non-blocking)
  - `8cbb49d` — User review fixes (GP title stripping, name registry separation, missing secession site)
  - `ed5ff02` — Implementation plan (14 tasks)
  - `36e01a4` — User review plan fixes (5 issues: legitimacy timing, structured base_name, agent_id retirement, dead ancestral_memories field, Civilization test construction)
- **Two tracks:** Track A (Rust legacy memory transfer, 6 tasks) and Track B (Python succession scoring + regnal numbering, 8 tasks). Tracks are independent — can be parallelized.
- **Key design decisions this session:**
  - Legacy memories preserve original event_type (Famine, Battle, etc.) — `MemoryEventType::Legacy` (14) is NOT used as event_type. Legacy status tracked via `memory_is_legacy: Vec<u8>` bitmask (1 byte/agent).
  - Option A for buffer interaction: legacy memories compete in regular ring buffer, no reserved slots or protection windows. Tuning levers: `LEGACY_HALF_LIFE` (100 turns), `LEGACY_MIN_INTENSITY` (post-halving threshold).
  - Succession scoring scoped to incumbent ruling line only (not any living dynasty). Additive weight on GP candidates (0.15 direct heir, 0.08 same dynasty).
  - Regnal numbering is per-civ, stored at succession time on Leader. `_pick_regnal_name()` is a new function independent of `_pick_name()` and `world.used_leader_names`.
  - GP base_name stored structurally on GreatPerson at promotion time — no display-name reverse-parsing. `_pick_name()` returns `(full_name, base_name)` tuple.
  - Legitimacy captured BEFORE leader swap in `resolve_crisis_with_factions()`.
  - GP retirement uses `agent_id` (stable key), not name string match.
- **Next session:** Choose execution approach (subagent-driven vs inline) and begin implementation.

---

## Ready for Implementation

**Next steps:**
- M51 implementation (spec + plan ready, 14 tasks)
- M48+M49+M50 200-seed regression deferred to M53 — memory + needs + relationships are uncalibrated
- M53 calibration pass (~125+ Rust constants across M48+M49+M50+M51, tiered strategy in M49 spec Section 9)
- ERA_REGISTER A/B experiment (manual, deferred from M44)

---

## Known Gotchas / Deferred Items

- **Transient signal rule (CLAUDE.md):** Clear BEFORE return in builder functions. 2+ turn integration test required for every new transient signal.
- **M51: `MemoryEventType::Legacy` (14) is vestigial.** Legacy memories preserve original event_type and use `memory_is_legacy` bitmask instead. The `default_decay_factor(14)` match arm in memory.rs is dead code — add a comment during implementation noting this.
- **M51: `_pick_name()` stays unchanged (returns `str`).** New `_pick_base_name()` extracts the name-selection core. `_pick_name()` optionally refactored to call `_pick_base_name()` internally, but return type stays `str`. `strip_title()` used as transitional fallback for existing display names. `gp.base_name` set at promotion time via `strip_title(gp.name)`.
- **M51: world_gen.py leader construction ordering.** The Leader is constructed inline inside the Civilization constructor (line 143). `_pick_regnal_name()` requires a Civilization object. Restructure: construct Civ with placeholder leader, then replace via `_pick_regnal_name()`.
- **M51: GP ascension phantom regnal counter.** When a GP wins succession, `generate_successor()` already called `_pick_regnal_name()` and incremented the counter for a name that won't be used. The GP block must undo this phantom increment before computing the GP's own ordinal.
- **M51: Legitimacy scoring only activates for GP-sourced rulers.** If most successions produce abstract/external candidates, `civ.leader.agent_id` is None and dynasty scoring is inert. M53 should measure activation rate — if < 20%, system is decorative.
- **M51: Legacy + persecution stacking.** Legacy persecution memories add to M38b + M48 + M49 triple-stacking concern. Monitor total rebel modifier budget in M53.
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
- **~~M48 spec: `_detect_character_events` referenced but doesn't exist by that name.~~** Resolved — memory sync placed in tick() hybrid branch loop, after events processed.
- **~~M48 spec: Phase 7 roadmap text outdated.~~** Resolved — spec Section 10 documents 5 divergences.
- **M48: Promotion intent not generated.** `MemoryEventType::Promotion` has constants and decay factor but no intent collection in tick.rs. Promotion happens Python-side in `_process_promotions()`. No Rust-to-Python memory write path exists. Wire when character arc system needs it.
- **M48: Victory memories not civ-filtered.** `war_won_this_turn` is a bare boolean on RegionState. ALL soldiers in the region get Victory memories, including losing side. Fix requires `war_winning_civ: u8` field on RegionState + civ filtering in tick.rs intent collection.
- **M48: `default_decay_factor()` recomputes `factor_from_half_life()` per write.** Cold-path (thousands/turn, not millions). Could be lazy-static lookup table if memory write volume increases.
- **M48: `build_agent_context_for_moment()` new params not wired in batch path.** `civ_names`/`world_turn` params default to None/0 for backward compatibility. Memory/Mule context populated when callers pass those params. `_prepare_narration_prompts` does not wire them yet.
- **M49: Persecution triple-stacking.** M38b direct boost (0.30) + M48 memory boost (~0.10) + M49 Autonomy need boost (up to 0.24) all push rebel/migrate. Total can reach ~0.64 additive on rebel. M53 priority calibration target.
- **M49: `_NEED_THRESHOLDS` in narrative.py must stay synced with agent.rs constants.** Both files define threshold values (0.3, 0.25, 0.35). No compile-time enforcement. If thresholds change in M53 calibration, update both.
- **~~M49: Social need pre-M50 proxy.~~** Resolved in M50b. `social_restoration()` now has blend formula `(1-α)*proxy + α*bond_factor`. Alpha=0.0 at ship; M53 ramps.
- **M50b: Dissolution events lack dead target's agent_id.** `AgentEvent.target_region` is repurposed for bond_type; dead agent's ID is not carried. Python stores `(agent_id, 0, bond_type, turn)` with 0 as placeholder. Narration can say "a bond was severed" but not "between X and Y." Fix requires adding `target_agent_id: u32` field to AgentEvent. Deferred — not blocking until M53b needs dissolution trace data.
- **M50b: `--relationship-stats` flag parsed but not wired.** CLI flag exists, FFI `get_relationship_stats()` exists, analytics extractor expects `metadata["relationship_stats"]`. No Python-side call site invokes the FFI method or stores the metadata. Distribution metrics are always computed (cheap at current agent counts). Wire when approaching 200K+ agents or for M53 calibration.
- **M50b: `id_to_slot` HashMap rebuilt per-region.** Spec says build pool-wide map once per cadence tick. Implementation rebuilds from `alive_slots` inside the region loop. Correct behavior, minor perf waste (~100K unnecessary hash insertions per tick with 50K agents). Hoist above region loop if formation scan shows in profiles.
- **M50b: `check_friend` evaluates compatibility before shared memory.** Spec cascade puts expensive checks last. At current memory slot counts (5 max), cost difference is negligible. Low priority.
- **M49: Phase 7 roadmap estimates ~24 M49 constants.** Actual count is 37. Update roadmap when next editing it.
- **M49: Material equilibrium sensitive to wealth percentile assumptions.** Spec equilibrium table assumes "median wealth" restoration rate that may be optimistic. Verify numerically in M53 Tier 3 calibration.
