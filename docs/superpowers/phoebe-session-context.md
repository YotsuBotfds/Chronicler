# Phoebe Session Context — Chronicler Project

> Read this file at the start of every Phoebe session. It captures architectural state, design decisions, and current progress so you can pick up without re-reading the entire codebase.
>
> **Last updated:** 2026-03-16 (M27-M29 merged. M30 in progress. M31 deferred to Phase 6 M47. Phase 6 roadmap expanded to 16 milestones with environment, religion, and supply chain systems.)

---

## What Is Chronicler

A Python CLI that generates entire civilization histories through deterministic simulation + LLM narration. Seed + scenario + turn count → complete chronicle with wars, famines, cultural renaissances, political collapses, and tech advancement — all emerging from interacting systems, not scripted events.

**Hardware:** 9950X (16C/32T, 192GB DDR5) for simulation, 4090 (24GB VRAM) via LM Studio for local LLM inference. CPU and GPU workloads are fully decoupled. Currently running Qwen 3 235B (A22B MoE) locally at 2-3 tk/s — adequate for batch narration, too slow for live mode demos.

**Codebase:** ~16,000+ lines across 50+ Python files. ~2,000 lines Rust (chronicler-agents crate). React/TypeScript viewer (~3,600 lines) with WebSocket live mode. All simulation is pure Python — the LLM only narrates, never decides. Rust handles agent-level computation via Arrow FFI.

**API narration planned:** Phase 6 (M38) will wire Claude Sonnet 4.6 via API for curated moment narration.

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
  Rust tick: satisfaction → decisions → migration → occupation → loyalty → demographics
  Write-back: agent aggregates overwrite civ stats in hybrid mode
  Promotions: named character detection → GreatPerson creation
  Event detection: agent events (rebellion, migration, etc.) → curator pipeline
Phase 10: Consequences (emergence, factions, succession, named events, snapshot)
  Phase 10 guards: acc=None in aggregate mode (direct mutations); acc passed in hybrid mode
```

Each phase reads/mutates a shared `WorldState`. Pydantic models throughout (`validate_assignment=False` — direct mutations).

### Key Files

| File | Lines | Role |
|------|-------|------|
| `simulation.py` | ~1,400 | Core turn loop, all 10 phases, StatAccumulator integration (M27) |
| `politics.py` | ~1,200 | Governing costs, secession, federation, vassals, proxy wars, twilight, congress |
| `main.py` | ~730 | CLI entry point, `--agents` flag (M28), argument parsing, run orchestration |
| `action_engine.py` | ~750 | Action selection with weight modifiers (11 ActionTypes), accumulator routing |
| `emergence.py` | ~680 | Black swans, severity multiplier, pandemics, terrain succession |
| `analytics.py` | ~1,500 | M19: post-processing extractors, anomaly detection, delta reports |
| `agent_bridge.py` | ~400 | M27: Rust↔Python bridge, shock/demand signals, write-back, event aggregation |
| `factions.py` | ~580 | M22: three factions (military/merchant/cultural), power struggles |
| `ecology.py` | ~430 | M23: coupled soil/water/forest, climate-driven drought, rewilding |
| `accumulator.py` | ~120 | M27: StatAccumulator class with category routing |
| `demand_signals.py` | ~35 | M27: DemandSignalManager with 3-turn linear decay |
| `shadow_oracle.py` | ~140 | M26/M28: oracle comparison, `compare_distributions()` extracted for reuse |
| `models.py` | ~500 | All Pydantic models (Civilization has no `id` field — use index into world.civilizations) |
| `curator.py` | ~250 | M20a: event selection, causal linking, clustering, role assignment |
| `narrative.py` | ~630 | NarrativeEngine, era register, NarrationContext, LLM client wrappers |
| `bundle.py` | ~110 | Bundle assembly (includes `bundle_version: 1`, agent event records) |

### ActionType Enum (models.py)

11 action types — **use these exact names, not invented aliases:**

```
EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR, BUILD,
EMBARGO, MOVE_CAPITAL, FUND_INSTABILITY, EXPLORE, INVEST_CULTURE
```

### Bundle Format

`chronicle_bundle.json` is the interchange format containing: `world_state`, `history` (TurnSnapshot[]), `events_timeline`, `named_events`, `chronicle_entries`, `gap_summaries`, `era_reflections`, `metadata` (includes `bundle_version`).

M31 will bump to `bundle_version: 2` (agent named characters + agent events).

### Feature Flags

`--agents=off|demographics-only|shadow|hybrid` + `--agent-narrative` + `--narrator=local|api`

---

## Milestone History

### Phases 1-2 (M1-M12): Core
Core simulation loop, action engine, basic narration, React/TS viewer, WebSocket live mode, setup lobby (M12c).

### Phase 3 (M13-M18): Material Depth
- **M13** — Resource economics: trade routes, embargoes, treasury, specialization
- **M14** — Politics: secession, federations, vassals, proxy wars, mercenaries, twilight
- **M15** — Living world: climate phases, migration, disasters, infrastructure
- **M16** — Memetic warfare: ideological movements, propaganda, cultural assimilation
- **M17** — Great persons: character dynamics, rivalries, hostages, folk heroes, traditions
- **M18** — Emergence: black swans, severity multiplier, pandemics, stress index

### Phase 4 (M19-M24): Validation & Architecture — COMPLETE

#### M19 — Simulation Analytics
Post-processing analytics pipeline. 8 extractors, anomaly detection, delta reports.

#### M19b — Phase 3 Tuning Pass
11 iterations across 200x500. Key structural fixes: stability recovery, culture-based regression resistance, 7 missing Event emissions.

#### M20a — Narration Pipeline v2
Three-phase pipeline: Simulate → Curate → Narrate. Curator: 3-pass scoring, causal linking, clustering, diversity, roles.

#### M21 — Tech Specialization
3 focuses per era. Terrain/resource multipliers. Focus effects modify action weights and stat bonuses.

#### M22 — Factions & Succession
Three factions with influence normalization (0.10 floor). Power struggles. Faction-weighted succession candidates.

#### M23 — Coupled Ecology
Soil/water/forest_cover replacing single fertility float. Climate-driven drought, rewilding mechanics.

#### M24 — Information Asymmetry
Perception layer: `compute_accuracy()` from relationships. Gaussian noise with deterministic seeding.

#### M19b Post-M24 Tuning Pass (Third Pass) — CONVERGED
12 iterations of ecology + faction constant tuning.

#### Phase 4 Deferred Items
- M20b — Batch Runner GUI (instructions written, not started)
- Viewer extensions (M21-M24): tech focus badge, faction influence bar, ecology hover, intel indicator (~300 lines TS) — deferred to Phase 6 M40

---

## Phase 5: Agent-Based Population Model — NEARING COMPLETION

**Roadmap:** `docs/superpowers/roadmaps/chronicler-phase5-roadmap.md`

### Summary
Rust crate (`chronicler-agents`) providing agent-based population simulation. Agents have occupation, satisfaction, loyalty, skill, age. Decisions: rebel → migrate → switch occupation → loyalty drift. Demographics: age-dependent mortality, satisfaction-influenced fertility.

### Key Design Decisions (Locked)
1. Agent count scales to carrying capacity (floor 20, cap 500 per region, ~3K-6K total)
2. FFI via Apache Arrow (pyo3-arrow with PyCapsule Interface)
3. No agent personality in Phase 5 (defer to Phase 6)
4. Demographic birth/death model (age-dependent, ecology-sensitive)
5. Viewer stays at civ level in Phase 5 (defer to Phase 6 M40)
6. Crate name: `chronicler-agents`

### Milestones
| Milestone | Name | Status |
|-----------|------|--------|
| M25 | Rust Core + Arrow Bridge | **SHIPPED.** 15 commits, 16 Rust + 46 Python tests, ~174us benchmark. |
| M26 | Agent Behavior + Shadow Oracle | **MERGED.** 14 commits, 69 Rust + 6 Python test classes. |
| M27 | System Integration | **MERGED.** 15 tasks, StatAccumulator routing 76+ mutations, shock/demand signals, Phase 10 guards. Phase 10 acc bug fixed (pass acc=None in aggregate mode). |
| M28 | Oracle Gate | **MERGED.** 5 tasks, `--agents` CLI flag, `compare_distributions()` extracted, batch orchestration, adapter + reports. anderson_ksamp + NaN fixes applied. |
| M29 | Scale & Performance | **MERGED.** Phase A complete (7 commits). Profiling infrastructure, satisfaction parallelization, benchmarks. All targets met with 27-47x headroom. Phase B deferred — no profiling justification. |
| M30 | Agent Narrative | **IN PROGRESS.** 16 tasks across 5 chunks. Spec + plan written. Promotion, events, curator, narrator, lifecycle. |
| ~~M31~~ | ~~Agent Tuning Pass~~ | **DEFERRED.** Folded into Phase 6 M47 (full-system calibration). All M30 thresholds recalibrated alongside 25+ Phase 6 constants. |

### M27: Merged — Key Architecture

**StatAccumulator** — replaces all 76 direct stat mutations. Five categories at call site:
- `keep` (16): apply directly in all modes (treasury, asabiya, prestige)
- `guard` (24): skip in agent mode — agents produce emergently
- `guard-action` (5-6): action engine outcomes → DemandSignals
- `signal` (22): external shocks → ShockSignals
- `civ_idx` parameter (int index into world.civilizations)

**ShockSignals** — normalized to [-1.0, +1.0]. Four FFI columns: `shock_{stability,economy,military,culture}`.

**DemandSignals** — 3-turn linear decay. Five FFI columns: `demand_shift_{farmer,soldier,merchant,scholar,priest}`.

**Key fix:** Phase 10 in aggregate mode must receive `acc=None` (not the StatAccumulator). Otherwise Phase 10 mutations are recorded but never applied. Fixed in commit `01e6f14`.

### M28: Merged — Key Details

- `compare_distributions()` extracted from `shadow_oracle_report()` as reusable function
- `--agents` CLI flag with choices: off, demographics-only, shadow, hybrid
- Data adapter: bundle JSON → columnar dict for oracle comparison
- Batch orchestration: parallel subprocess runs, `--aggregate-dir` for retry workflow
- Fixes applied: anderson_ksamp named result API, NaN guard in JSON report

### M29: Plan Details

**Spec:** `docs/superpowers/specs/2026-03-15-m29-scale-performance-design.md`
**Plan:** `docs/superpowers/plans/2026-03-16-m29-scale-performance.md`

- Phase A: Profiling infrastructure (benchmark matrix, flamegraph harness, macro regression gate) + satisfaction parallelization (per-region rayon) + profile-driven investigations (Arrow FFI, cache efficiency, compaction)
- Phase B: SIMD verification (`cargo asm`), decision short-circuit tuning
- Performance targets: 6K/24 < 3ms tick / < 3s 500-turn; 10K/24 < 5ms tick / < 6s 500-turn
- Collect-then-apply pattern for parallel satisfaction (avoids `unsafe`)
- Compaction contingent on >15% cache-miss degradation in packed-vs-scattered benchmark

### M30: Design Spec Details

**Spec:** `docs/superpowers/specs/2026-03-16-m30-agent-narrative-design.md`

**Named Character Promotion:**
- Two-gate system: skill gate (`promotion_progress >= DURATION` [CALIBRATE]) + life-event gate (`life_events != 0`)
- 4 bypass triggers: rebellion leader → General, 50+ turns displaced → Exile, 3+ migrations → Merchant, 3+ occ switches → Scientist
- New SoA fields: `life_events: u8` (bitflag), `promotion_progress: u8`
- `CharacterRole` enum (separate from `Occupation`)
- Promotion via separate `get_promotions()` RecordBatch (not AgentEvent)
- `set_agent_civ(agent_id, new_civ_id)` FFI method for conquest/secession sync

**Processing Order (Python bridge after tick):**
1. `get_promotions()` → create GreatPerson, update `named_agents: dict[int, str]`
2. `_convert_events()` → parse raw agent events
3. Check migrations against registry → `notable_migration`, `exile_return`
4. `_aggregate_events(world, named_agents)` → windowed detection, populate `actors`

**New Events:** `notable_migration` (importance 4), `economic_boom` (5, event-based), `brain_drain` (5), `exile_return` (6)

**Curator:** +2.0 character-reference bonus (max once per event, saturation guard) [CALIBRATE]

**Narration:** `AgentContext` with enriched character history (2-3 recent events), mood precedence (desperate > restless > content), character continuity rule

**Lifecycle:** Conquest → exile/refugee distinction. Secession → transfer + origin preserved + `set_agent_civ`. Death → overrides exile fate.

### Rust Crate Architecture (chronicler-agents)

| File | Role |
|------|------|
| `lib.rs` | Module exports |
| `agent.rs` | Constants, Occupation enum |
| `pool.rs` | SoA AgentPool with free-list arena |
| `ffi.rs` | PyO3 bindings, AgentSimulator, Arrow RecordBatch I/O |
| `region.rs` | RegionState struct |
| `tick.rs` | 5-phase tick orchestration (skill → satisfaction → stats → decisions → demographics) |
| `satisfaction.rs` | Branchless satisfaction formula with shock/demand terms (M27) |
| `behavior.rs` | Decision model: rebel → migrate → switch → drift |
| `demographics.rs` | Age-dependent mortality, ecology-sensitive fertility |
| `signals.rs` | CivSignals/TickSignals parsing from Arrow, shock/demand columns (M27) |

**Per-agent size:** ~44 bytes (42 base + 2 M30 fields). SoA layout, cache-friendly.
**`tick_agents` signature:** `(&mut AgentPool, &[RegionState], &TickSignals, [u8; 32], u32) -> Vec<AgentEvent>`

---

## Phase 6: Living Society — DRAFT

**Roadmap:** `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md` (draft, pending review)

**Theme:** Transform agents from isolated actors into members of a society living in a material world — environment, personality, culture, religion, family, social networks, wealth, supply chains, API narration, full viewer integration.

### Milestones
| Milestone | Name | Track | Est. Days |
|-----------|------|-------|-----------|
| M32 | Utility-Based Decisions | Agent Depth | 5-7 |
| M33 | Agent Personality | Agent Depth | 4-6 |
| M34 | Regional Resources & Seasons | Material World | 5-7 |
| M35 | Rivers, Disease & Depletion | Material World | 5-7 |
| M36 | Cultural Identity | Agent Depth | 5-7 |
| M37 | Belief Systems & Conversion | Religion | 5-7 |
| M38 | Religious Institutions & Schisms | Religion | 5-7 |
| M39 | Family & Lineage | Social Fabric | 4-6 |
| M40 | Social Networks | Social Fabric | 4-6 |
| M41 | Wealth & Markets | Economic Depth | 5-7 |
| M42 | Goods Production & Trade | Supply Chain | 5-7 |
| M43 | Transport, Perishability & Shocks | Supply Chain | 5-7 |
| M44 | API Narration Pipeline | Narration | 3-4 |
| M45 | Character Arc Tracking | Narration | 4-5 |
| M46 | Full Viewer Integration | Presentation | 7-9 |
| M47 | Phase 6 Tuning Pass | — | 4-6 |

**Per-agent memory budget:** 44 bytes (Phase 5) → ~68 bytes (Phase 6: +12 personality, +3 cultural values, +1 belief, +4 parent_id, +4 wealth).

**Validation shift:** Phase 5 oracle validated "do agents match aggregate." Phase 6 shifts to internal consistency — bold agents rebel more, cultural values cluster geographically, religious dynamics correlate with doctrine, wealth follows log-normal distribution, supply shocks propagate realistically, neutral-personality agents approximate Phase 5 behavior.

---

## Cross-Cutting Rules

- All negative stat changes go through M18 severity multiplier (except treasury, ecology)
- Combined action weight multiplier cap at 2.5x (traditions x tech focus x factions)
- Each milestone: run 200 seeds before/after, compare distributions, check for regressions
- `--agents=off` produces Phase 4 bit-identical output (regression test)
- Phase 10 receives `acc=None` in aggregate mode (M27 fix)
- Bundle format: consumer code doesn't know if stats came from agents or aggregates

---

## Session Workflow

- **Phoebe** reviews architecture, specs, and plans. Catches misalignments before implementation.
- **Cici** designs, specs, plans, and implements. Runs on Opus 4.6 with 1M context.
- Phoebe reviews Cici's outputs before implementation starts.
- Implementation plans are written AFTER prerequisite milestones land (so line references are accurate).
- Tuning iterations flag Tate for approval before applying changes and when structural conflicts arise.

---

## Key File Locations

| Path | Contents |
|------|----------|
| `src/chronicler/` | All Python source |
| `chronicler-agents/src/` | Rust agent crate |
| `chronicler-agents/benches/` | Criterion benchmarks |
| `viewer/` | React/TS viewer app (~3,600 lines) |
| `tests/` | Python test suite |
| `chronicler-agents/tests/` | Rust integration tests |
| `scripts/run_oracle_gate.py` | M28 oracle gate batch script |
| `docs/superpowers/specs/` | Design specs |
| `docs/superpowers/plans/` | Implementation plans |
| `docs/superpowers/roadmaps/` | Phase 2-6 roadmaps |
| `docs/superpowers/phoebe-session-context.md` | This file |
