# Phase 6 Progress — Living Society

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-03-18 (M43a session)

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

---

## Ready for Spec

### M43b: Supply Shock Detection, Trade Dependency & Raider Incentive

- Split from M43 during M43a brainstorm (calibration isolation).
- Builds on M43a's stockpile infrastructure.
- Scope: `ShockEvent` detection for curator (narration-only, no mechanical state), trade dependency classification (>60% food import), raider WAR utility modifier from stockpile levels.
- Emergent shock propagation via price/stockpile dynamics (no explicit attenuation constant). M43b validates ~50% attenuation target.
- Raider mechanic touches action engine weight system (combined cap 2.5×) — needs focused integration testing.
- ~4 calibration constants: `SHOCK_THRESHOLD`, `TRADE_DEPENDENCY_THRESHOLD`, `RAIDER_STOCKPILE_THRESHOLD`, `RAIDER_UTILITY_MODIFIER`.

---

## Known Gotchas / Deferred Items

- **Transient signal rule (CLAUDE.md):** Clear BEFORE return in builder functions. 2+ turn integration test required for every new transient signal.
- **M34 farmer-as-miner:** Resolved. M41 added `is_extractive()` dispatch; M42 replaced it with market-derived `farmer_income_modifier`.
- **M44 (API narration):** Free-floating — schedule flexibly between heavy milestones.
- **~~Viewer extensions (M46)~~ — Dropped 2026-03-17.** Phase 7 redesigns the viewer from scratch (M62). All Phase 3-6 viewer requirements preserved as inventory in Phase 7 roadmap.
- **Spec-ahead strategy:** Tier 1 spec-able: M44. Tier 2: M45.
- **M42 analytics deferred:** Price time series extractor needs bundle format update to persist `EconomyResult` prices into turn snapshots. Land when bundle schema is designed (M43 or M62).
- **M42+M43a 200-seed regression pending:** Calibration values (PER_CAPITA_FOOD, RAW_MATERIAL_PER_SOLDIER, LUXURY_PER_WEALTHY_AGENT, LUXURY_DEMAND_THRESHOLD, MERCHANT_MARGIN_NORMALIZER, TAX_RATE, BASE_FARMER_INCOME, plus M43a transport/decay/stockpile constants) need tuning before regression is meaningful.
- **M43a: `RegionStockpile` is persistent, `RegionGoods` remains transient.** CLAUDE.md note "M43 adds stockpile persistence" is now landed. `food_sufficiency` source changed from single-turn supply to pre-consumption stockpile.
- **M43a: `resource_effective_yields` not `resource_yields`.** `compute_economy()` line 595 was referencing `region.resource_yields[0]` (a property that may not exist on all Region instances). Fixed to `region.resource_effective_yields[0]` during implementation.
- **M43a: Salt preservation denominator excludes salt.** `total_food` in `apply_storage_decay()` uses `FOOD_GOODS if g != "salt"`. Salt doesn't preserve itself.
- **M43a: Per-good import decomposition assumes single resource slot.** Inline comment documents M41 Decision 14 dependency. Multi-slot milestone would need broader decomposition.
- **M43a: Conquest stockpile destruction wiring untested by M43a tests.** Formula is tested; integration point covered by existing war/action tests (which now operate on stockpile-bearing regions).
- **M43a: `--agents=off` stockpile accumulation test not written.** Phoebe recommended. Low priority.
- **Phase 7 draft roadmap:** `docs/superpowers/roadmaps/chronicler-phase7-draft.md` — provisional, subject to revision as Phase 6 milestones land.
