# Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Seed + scenario + turn count → complete chronicle with wars, famines, cultural renaissances, political collapses, and tech advancement — all emerging from interacting systems, not scripted events.

**Hardware:** 9950X (16C/32T, 192GB DDR5) for simulation, 4090 (24GB VRAM) via LM Studio for local LLM inference. CPU and GPU workloads are fully decoupled. Currently running Qwen 3 235B (A22B MoE) locally at 2-3 tk/s — adequate for batch narration, too slow for live mode demos.

**Codebase:** ~21,000 lines across 53 Python files. ~7,000 lines Rust (chronicler-agents crate). React/TypeScript viewer (~5,300 lines) with WebSocket live mode. All simulation is pure Python — the LLM only narrates, never decides. Rust handles agent-level computation via Arrow FFI.

**API narration planned:** Phase 6 (M44) will wire Claude Sonnet 4.6 via API for curated moment narration.

---

## Architecture

### 10-Phase Turn Loop + Agent Tick

```
Phase  1: Environment (climate, conditions, terrain transitions)
Phase  2: Economy (trade routes, income, tribute, treasury)
Phase  3: Politics (governing costs, vassal checks, congress, secession)
Phase  4: Military (maintenance, war costs, mercenaries)
Phase  5: Diplomacy (disposition drift, federation checks, peace)
Phase  6: Culture (prestige, value drift, assimilation, movements)
Phase  7: Tech (advancement rolls, focus selection, focus effects)
Phase  8: Action selection + resolution (action engine)
Phase  9: Ecology (soil/water/forest tick, terrain transitions, famine checks)
--- Agent tick (between Phase 9 and 10) ---
  StatAccumulator routes Phases 1-9 mutations by category (keep/guard/signal)
  Rust tick: wealth → satisfaction → decisions → migration → occupation → loyalty → demographics
  Write-back: agent aggregates overwrite civ stats in hybrid mode
  Promotions: named character detection → GreatPerson creation
  Event detection: agent events (rebellion, migration, etc.) → curator pipeline
Phase 10: Consequences (emergence, factions, succession, named events, snapshot)
  Phase 10 guards: acc=None in aggregate mode (direct mutations); acc passed in hybrid mode
```

Each phase reads/mutates a shared `WorldState`. Pydantic models throughout (`validate_assignment=False` — direct mutations).

### Python Key Files (src/chronicler/)

| File | Role |
|------|------|
| `simulation.py` | Core turn loop, all 10 phases, StatAccumulator integration |
| `politics.py` | Governing costs, secession, federation, vassals, proxy wars, twilight, congress |
| `main.py` | CLI entry point, `--agents` flag, argument parsing, run orchestration |
| `action_engine.py` | Action selection with weight modifiers (11 ActionTypes), accumulator routing |
| `emergence.py` | Black swans, severity multiplier, pandemics, terrain succession |
| `analytics.py` | Post-processing extractors, anomaly detection, delta reports |
| `economy.py` | M42 goods production, trade flow, supply-demand pricing, FFI signal derivation |
| `agent_bridge.py` | Rust↔Python bridge, shock/demand signals, write-back, event aggregation |
| `factions.py` | Four factions (military/merchant/cultural/clergy), power struggles |
| `ecology.py` | Coupled soil/water/forest, climate-driven drought, rewilding |
| `accumulator.py` | StatAccumulator class with category routing |
| `models.py` | All Pydantic models |
| `curator.py` | Event selection, causal linking, clustering, role assignment |
| `narrative.py` | NarrativeEngine, era register, NarrationContext, LLM client wrappers |
| `dynasties.py` | Dynasty detection, tracking, extinction/split events (M39) |
| `relationships.py` | Social edge formation/dissolution, coordinator, hostage mechanics (M40) |
| `religion.py` | Faith generation, belief aggregation, schisms, persecution, pilgrimages (M37-M38b) |
| `world_gen.py` | Initial world generation, stockpile initialization |
| `resources.py` | Resource system, terrain probabilities, trade route queries, seasons |
| `climate.py` | Climate cycles, natural disasters, migration |
| `infrastructure.py` | Infrastructure lifecycle (temples, etc.), build/tick/destroy |
| `great_persons.py` | GreatPerson generation, lifecycle, modifier registry |
| `live.py` | WebSocket live mode server for real-time viewer |
| `shadow.py` | Shadow mode: Arrow IPC logger for agent-vs-aggregate comparison |
| `bundle.py` | Bundle assembly |

### Rust Crate (chronicler-agents/src/)

| File | Role |
|------|------|
| `lib.rs` | Module exports |
| `agent.rs` | Constants, Occupation enum, `STREAM_OFFSETS` RNG registry |
| `pool.rs` | SoA AgentPool with free-list arena |
| `ffi.rs` | PyO3 bindings, AgentSimulator, Arrow RecordBatch I/O |
| `region.rs` | RegionState struct |
| `tick.rs` | Multi-phase tick orchestration, wealth_tick (M41) |
| `satisfaction.rs` | SatisfactionInputs struct, branchless satisfaction formula with shock/demand/culture/religion/wealth/food/merchant terms |
| `behavior.rs` | Decision model: utility-based selection with personality modifiers |
| `demographics.rs` | Age-dependent mortality, ecology-sensitive fertility |
| `named_characters.rs` | Named character promotion tracking |
| `conversion_tick.rs` | Belief conversion per-agent rolls |
| `culture_tick.rs` | Cultural drift per-agent |
| `signals.rs` | CivSignals/TickSignals parsing from Arrow columns |
| `social.rs` | SocialGraph, SocialEdge, RelationshipType for named character relationships (M40) |

### ActionType Enum (models.py)

11 action types — **use these exact names, not invented aliases:**

```
EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR, BUILD,
EMBARGO, MOVE_CAPITAL, FUND_INSTABILITY, EXPLORE, INVEST_CULTURE
```

### StatAccumulator (accumulator.py)

5 routing categories at call site, plus `civ_idx` parameter on every call:
- `keep`: apply directly in all modes (treasury, asabiya, prestige)
- `guard`: skip in agent mode — agents produce emergently
- `guard-action`: action engine outcomes → DemandSignals
- `guard-shock`: phase-generated shocks (leader events, vassalage, proxy wars, cultural milestones) → ShockSignals
- `signal`: external shocks → ShockSignals

### Bundle & Feature Flags

**Bundle:** `chronicle_bundle.json` — `world_state`, `history`, `events_timeline`, `named_events`, `chronicle_entries`, `gap_summaries`, `era_reflections`, `metadata` (includes `bundle_version`).

**Flags:** `--agents=off|demographics-only|shadow|hybrid` + `--agent-narrative` + `--narrator=local|api`

### Data Model Gotchas

- `civ.regions` is `list[str]` (names), not `list[Region]` — resolve via `region_map`
- `Region` has no `region_id` field — use index into `world.regions`
- `Civilization` has no `id` field — use index into `world.civilizations`
- `Civilization` has no `alive` field — check `len(civ.regions) > 0`
- `GreatPerson` has no agent-pool fields (belief, occupation, etc.) — lookup via snapshot by `agent_id`
- `GreatPerson.born_turn` is the promotion turn (set to `world.turn` in `_process_promotions`), not the agent's actual birth turn
- `AgentPool.next_id` starts at 1, not 0 — `PARENT_NONE = 0` is the sentinel for no parent (M39)
- `build_region_batch()` return-then-cleanup is dead code — clear transient state BEFORE the return
- `world._conquered_this_turn` is transient `set[int]` — set in `_resolve_war()`, cleared in `simulation.py` before bridge tick
- `AgentBridge._gini_by_civ` implements one-turn lag — Gini from turn N's snapshot feeds turn N+1's signals
- `compute_satisfaction_with_culture` takes `SatisfactionInputs` struct — M42+ adds fields to struct, not positional params

---

## Cross-Cutting Rules

- All negative stat changes go through M18 severity multiplier (except treasury, ecology)
- Combined action weight multiplier cap at 2.5x (traditions x tech focus x factions)
- Each milestone: run 200 seeds before/after, compare distributions, check for regressions
- `--agents=off` produces Phase 4 bit-identical output (regression test)
- Phase 10 receives `acc=None` in aggregate mode
- Bundle format: consumer code doesn't know if stats came from agents or aggregates
- Transient signals crossing FFI (one-turn flags, phase-to-phase signals): clear BEFORE the return in the builder function. Every new transient signal requires a 2+ turn integration test verifying the value resets after consumption.
- Non-ecological satisfaction penalties capped at -0.40 total (cultural + religious + persecution + class tension = budget). Flat clamp, no proportional scaling. Priority clamping: three core terms first, class tension takes remainder. [Decision 10]
- RNG stream offsets registered in `agent.rs` `STREAM_OFFSETS` block — any new RNG source needs a unique offset [Decision 11]
- Religion is a fourth faction (clergy), not a value dimension — regression baseline required before wiring [Decision 9]
- Milestone ordering: environment → culture → religion → family (each system needs the prior substrate) [Decision 7]
- Wealth per-agent (`f32` SoA in Rust pool): accumulation by occupation, multiplicative decay, MAX_WEALTH clamp. Per-civ Gini from Python snapshot → class tension penalty in satisfaction (priority-clamped under 0.40 cap).
- Goods economy (M42): `economy.py` computes production/demand/two-pass pricing/trade flow per turn. Four RegionState FFI signals (`farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`) + one CivSignals field (`priest_tithe_share`). Farmer income = `BASE_FARMER_INCOME × modifier × yield` (replaces `is_extractive()` dispatch). Merchant income = `merchant_trade_income` (arbitrage-driven, replaces static `MERCHANT_BASELINE`). `food_sufficiency` penalty is outside the 0.40 non-ecological cap (material condition, not social). Log-dampened margin weighting in trade allocation prevents extreme price concentration. Treasury tax + tithe base swap landed (M41 deferred integrations).
- `RegionGoods` is transient — not persisted on world state. M43 adds stockpile persistence.
- `FOOD_TYPES`/`is_food()` in `models.py`/`satisfaction.rs` are unchanged — goods-level category mapping (including SALT as food) lives only in `economy.py`'s `map_resource_to_category()`.
- `conquered_this_turn` fires for WAR conquest only, not EXPAND (peaceful settlement). [M41 Decision]

---

## Session Workflow

- **Phoebe** reviews architecture, specs, and plans. Catches misalignments before implementation. Available as a subagent (`.claude/agents/phoebe.md`). Invoke via `/init-phoebe`.
- **Cici** designs, specs, plans, and implements. Runs on Opus 4.6 with 1M context. Invoke via `/init-cici`.
- Phoebe reviews Cici's outputs before implementation starts.
- Implementation plans are written AFTER prerequisite milestones land (so line references are accurate).
- Tuning iterations flag Tate for approval before applying changes and when structural conflicts arise.

**Session start:** Read `docs/superpowers/progress/phase-6-progress.md` before starting implementation work. It has the current milestone status, active decisions, and known gotchas that CLAUDE.md doesn't repeat.

**Session end:** Before ending an implementation session, update `phase-6-progress.md` with what was completed, what's unfinished, and any new gotchas. Use `/end-session` to automate this.

**Session discipline:** Keep sessions under 300k tokens. Performance degrades at higher context. Prefer frequent focused sessions with good handoff documentation over long marathon sessions. When a session is getting long, prioritize updating progress docs over squeezing in one more feature.

**Milestone completion:** After implementation is complete and tests pass, run the 200-seed regression comparison before marking the milestone done. Dispatch regression runs as background agents when possible to avoid blocking implementation work.

---

## Tooling

**Rust testing:** Use `cargo nextest run` instead of `cargo test` for all Rust test runs. Faster parallel execution, better output, flaky test detection. Installed at `.cargo/bin/cargo-nextest`.

**Rust diagnostics (use when relevant):**
- `cargo machete` — detect unused dependencies in Cargo.toml. Run after adding/removing crates.
- `cargo expand` — view expanded PyO3 macro output. Use when debugging FFI bindings.
- `cargo flamegraph` — generate flamegraphs. Use when profiling tick performance or investigating hot paths.

**Python testing:** `pytest` with standard conventions. Tests in `tests/`.

**LSP plugins active:** rust-analyzer (Rust type info + diagnostics), typescript-lsp (viewer TS/React diagnostics). These provide type information without reading entire files — use them.

**Hooks (automatic):** Rust files auto-formatted on edit. `cargo check` runs after `.rs` edits (catches type errors immediately). Clippy + nextest run before git commits.

**Subagents:** Use the Phoebe agent (`.claude/agents/phoebe.md`) for design reviews — runs in a separate context window, doesn't burn main session tokens. Dispatch review-heavy or research-heavy work to subagents to keep the main context lean.

**Subagent dispatch checklist:** When spawning implementation subagents, include this in their prompt:
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially treasury/tithe/population fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.

---

## Current Focus

Phase 6 — Living Society. Roadmap: `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md`

**Merged through:** M43a (Transport, Perishability & Stockpiles) — implemented, Phoebe review complete. Stockpile persistence landed. Conservation law verified. 200-seed regression pending calibration (M42+M43a combined).
**Ready for implementation:** M43b (Supply Shock Detection, Trade Dependency & Raider Incentive) — spec reviewed.
**Next:** M44 (API narration, free-floating), M45 (Character Arcs), M47 (Tuning Pass).
**See:** `docs/superpowers/progress/phase-6-progress.md`

---

## References

| Path | Contents |
|------|----------|
| `docs/superpowers/roadmaps/` | Phase 2-7 roadmaps (Phase 7 is provisional draft) |
| `docs/superpowers/specs/` | Design specs (per-milestone) |
| `docs/superpowers/plans/` | Implementation plans (per-milestone) |
| `docs/superpowers/progress/phase-6-progress.md` | Active Phase 6 decisions and gotchas |
| `src/chronicler/` | All Python source |
| `chronicler-agents/src/` | Rust agent crate |
| `viewer/` | React/TS viewer app |
| `tests/` | Python test suite |
| `chronicler-agents/tests/` | Rust integration tests |
