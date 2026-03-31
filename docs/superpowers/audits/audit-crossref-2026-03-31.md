# Audit Cross-Reference — Opus 4.6 vs GPT-5 — 2026-03-31

Two independent full-codebase audits, compared finding-by-finding.

---

## Methodology Comparison

| | Opus 4.6 | GPT-5 |
|---|---|---|
| Subagents | 22 specialized | 6 + local verification |
| Local runs | No (code-read only) | Yes (pytest, cargo, npm, clippy, lint) |
| Focus | Deep system-by-system + architecture | Correctness bugs + tooling hygiene + red surfaces |
| Strengths | Religion/culture/ecology/spatial/social deep dives, performance profiling, security | Actually running the test suites, catching hidden failures, CLI behavior audit |

**Key methodological difference:** Codex ran `pytest test` (the *other* test directory), `npm run lint`, and `cargo clippy -D warnings` — discovering hidden red surfaces that a code-read-only audit misses. Opus went deeper into simulation logic, finding religion/ecology/politics system bugs through trace analysis.

---

## AGREEMENTS (Both Audits Found)

These are the highest-confidence findings — independently discovered by both models.

| # | Finding | Opus | Codex |
|---|---------|------|-------|
| 1 | `war_start_turns` never populated — congress ignores war duration | H-1 | Blocker #3 |
| 2 | Severity multiplier sweep incomplete (plague stability, others) | M-16 | #14 |
| 3 | `ffi.rs` at ~5K lines must be split | H-8 | Redundancy #5 |
| 4 | `tick_agents()` is monolithic milestone timeline | Phoebe review | Redundancy #6 |
| 5 | `region_map` cache exists but 21-25 ad-hoc rebuilds bypass it | M-4 | Redundancy #8 |
| 6 | `run_turn` / `phase_consequences` are god orchestrators with scratch channels | Phoebe B-2 | Redundancy #3 |
| 7 | Black market leakage only checks first controlled region | Sim Finding 19 | #13 |
| 8 | Tautological regression assertions (`>= 0` in test_m36) | Test audit | Coverage #2 |
| 9 | Politics split across Python/Rust/simulation.py glue | Phoebe review | Redundancy #1-2 |
| 10 | Viewer fixture stale relative to Python bundle contract | Viewer audit | #16 |
| 11 | Progress doc internally inconsistent | Doc drift noted | Doc #1 |
| 12 | WAR→DEVELOP fallback records wrong action | Action audit (LOW) | Blocker #2 |
| 13 | `AgentBridge` is overloaded (2,225 lines) | Noted | Redundancy #4 |

---

## UNIQUE TO OPUS (Codex Did Not Find)

These come from deeper system-level trace analysis. The religion, ecology, and politics dead-wiring findings are among the highest-impact items in either audit.

### Blocking / Critical
| # | Finding | Why Codex Missed It |
|---|---------|---------------------|
| B-1 | **Positive events routed as guard-shock PENALIZE agents** — discovery, renaissance, religious movement all worsen satisfaction | Requires tracing accumulator → to_shock_signals() → Rust compute_shock_penalty chain |
| B-2 | **`replace_social_edges` positional `.unwrap()`** — process abort on bad FFI input | Narrow FFI path, only found by reading all column access patterns |
| B-3 | **Schism conversion dead-wired** — schisms create faiths but never convert agents | Requires cross-referencing religion.py → conversion_tick.rs consumer chain |
| B-4 | **Martyrdom boost never decays** — `decay_martyrdom_boosts()` exists but never called | Dead function analysis in religion.py |
| B-5 | **Martyrdom applies to ALL deaths**, not just persecution deaths | Requires reading the death filter logic |
| B-6 | **Rewilding structurally impossible** — plains forest cap (0.40) vs counter threshold (0.70) | Requires cross-referencing Python ecology.py vs Rust ecology.rs terrain caps |
| B-7 | **Federation defense unimplemented** — `trigger_federation_defense()` never called | Politics deep dive found dead code |

### High / Medium
| # | Finding |
|---|---------|
| H-2 | Vassalization is dead code — wars always absorb |
| H-3 | Governing cost stability always zero — `int(0.5)` = 0 |
| H-6 | No leader trait maps to CLERGY faction — structural disadvantage |
| H-12 | `conquest_conversion_active` persists indefinitely in --agents=off |
| M-7 | Embargoes are permanent — no expiry, decay, or removal mechanism |
| M-22 | Asabiya not sent as FFI signal — agents don't know regional solidarity |
| M-23 | Marriage scan O(E^2) with no pair-evaluation cap |
| M-21 | Ecology↔satisfaction same-turn echo loop |
| M-24 | `pending_shocks` dual-use (same-turn vs next-turn) undistinguished |
| M-25 | `civ_id` type mismatch — UInt16 schema vs u8 key |

### Performance (entire category unique to Opus)
| # | Finding |
|---|---------|
| Perf-1 | `events_timeline` unbounded growth + O(turns×C) scan in tick_factions |
| Perf-2 | `graph_distance()` rebuilds adjacency map ~72x/turn |
| Perf-3 | `get_snapshot()` full pool serialization 2-3x/turn |
| Perf-4 | `get_active_trade_routes()` O(R^2) called 3x/turn |
| Perf-5 | `civ_index()` O(C) linear scan at 58 call sites |
| Perf-6 | `partition_by_region()` called 7+x per Rust tick, most redundant |
| Perf-7 | `signals.civs.iter().find()` O(C) per agent in hot loops |

### Full Domain Audits (unique to Opus)
- Security assessment (2 medium, 5 low, clean overall)
- Pydantic model sprawl analysis (Region 49 fields, GreatPerson 40)
- Social systems (memory, needs, dynasties, relationships — all clean)
- Spatial/settlement systems (clean, marriage scan scaling concern)
- Narrative/LLM pipeline (thread_domains no-op, NarrationContext dead, no retry)
- Economy conservation law verification (sound, transport cost mismatch)
- Style/naming consistency (acc never typed, sentinel magic numbers)

---

## UNIQUE TO CODEX (Opus Did Not Find)

These come from actually running tools and auditing CLI/tooling behavior.

### Blocking / Critical
| # | Finding | Why Opus Missed It |
|---|---------|---------------------|
| C-1 | **TRADE pays out without an active route** — eligibility uses relationship, not route existence | Opus verified accumulator routing but didn't check the trade prerequisite |
| C-4 | **Zero-agent civs disappear from Rust aggregates** — stale civ stats on write-back | Requires specific knowledge of the aggregate batch edge case |
| C-5 | **Promotions FFI lacks authoritative civ identity** — reconstructs from region controller (wrong after migration/conquest) | Novel FFI contract issue, not visible from Python-side alone |

### High / Medium
| # | Finding | Why Opus Missed It |
|---|---------|---------------------|
| C-6 | **validate.py is fail-open** — always exits 0, unknown oracles silently ignored | Opus noted file size (2068 lines) but didn't audit exit behavior |
| C-7 | **`--compare` is inert** — silently falls through to normal simulation | CLI behavior audit — Opus checked flag parsing but not execution path |
| C-8 | **Hidden `test/` tree has 10 failures** — default pytest never runs it | Codex actually ran `pytest test`; Opus only analyzed `tests/` |
| C-10 | **Batch parallel silently drops LLM clients** — always uses dummy | CLI execution path audit |
| C-11 | **Resume path divergence** — execute_run vs main resume behave differently | Opus didn't compare the two resume paths |
| C-12 | **Economy oracle crashes on barren regions** — EMPTY_SLOT in slot 0 | Opus verified conservation law but not the barren edge case |
| C-15 | **Viewer lint is red** — 4 React hook/state errors | Codex ran `npm run lint`; Opus only read code |
| C-16 | **`cargo clippy -D warnings` is red** | Codex ran clippy; Opus didn't |
| C-17 | **Rust test missing `#[test]` attribute** — `test_rebel_priority_over_migrate()` | Code-level catch by Codex |
| C-18 | **Analytics CLI drift** — newer extractors not wired into `--analyze` | Opus didn't audit the analytics surface |

---

## SEVERITY DISAGREEMENTS

| Finding | Opus Rating | Codex Rating | Resolution |
|---------|-------------|--------------|------------|
| WAR→DEVELOP fallback | LOW ("unreachable") | BLOCKER ("poisons history") | **Codex is right.** Even with eligibility gating, target elimination between selection and resolution can trigger the fallback. Action history corruption affects war weariness, peace momentum, streak logic, and analytics. |
| Proxy detection sign error (Mar 29 audit) | **INCORRECT** — all 3 paths apply -5 correctly | Not mentioned | **Opus is right.** The March 29 audit's claim was wrong. My politics reviewer verified all three code paths correctly apply negative stability. This should be struck from the open P0 list. |

---

## COMBINED PRIORITY LIST (Hardening Milestone)

### Tier 1: Correctness Bugs (must fix)

| # | Finding | Source |
|---|---------|--------|
| 1 | Positive guard-shock routing penalizes agents for good events | Opus B-1 |
| 2 | TRADE pays out without active route | Codex C-1 |
| 3 | WAR→DEVELOP fallback records wrong action in history | Both |
| 4 | `war_start_turns` never populated — congress ignores war duration | Both |
| 5 | Zero-agent civs disappear from aggregates — stale stats | Codex C-4 |
| 6 | Promotions FFI lacks authoritative civ identity | Codex C-5 |
| 7 | Schism conversion dead-wired — never converts agents | Opus B-3 |
| 8 | Martyrdom boost never decays + applies to all deaths | Opus B-4, B-5 |
| 9 | Rewilding structurally impossible (cap vs threshold) | Opus B-6 |
| 10 | Federation defense unimplemented | Opus B-7 |
| 11 | Governing cost stability always zero (`int(0.5)`) | Opus H-3 |
| 12 | Severity multiplier gaps (plague stability, others) | Both |
| 13 | `replace_social_edges` positional unwrap — panic path | Opus B-2 |
| 14 | Economy oracle crash on barren regions | Codex C-12 |

### Tier 2: Validation & Tooling (must fix before trusting green)

| # | Finding | Source |
|---|---------|--------|
| 15 | validate.py fail-open (always exits 0) | Codex C-6 |
| 16 | `--compare` silently falls through | Codex C-7 |
| 17 | Hidden `test/` tree — decide: migrate or archive | Codex C-8 |
| 18 | Viewer lint red (4 React hook errors) | Codex C-15 |
| 19 | `cargo clippy -D warnings` red | Codex C-16 |
| 20 | Rust test missing `#[test]` attribute | Codex C-17 |
| 21 | `conquest_conversion_active` stale in --agents=off | Opus H-12 |

### Tier 3: Architecture (do before M60a)

| # | Finding | Source |
|---|---------|--------|
| 22 | Split `ffi.rs` (~5K lines) | Both |
| 23 | Extract `run_turn` parameters into RuntimeServices | Opus Phoebe |
| 24 | CivSignals + RegionState test builders for Rust | Opus Phoebe |
| 25 | M47d war frequency (spec + plan exist) | Opus H-7 |
| 26 | Consolidate region_map usage (21-25 ad-hoc rebuilds) | Both |

### Tier 4: Dead Code & Cleanup

| # | Finding | Source |
|---|---------|--------|
| 27 | Remove deprecated social.rs and shim | Opus M-1 |
| 28 | Delete dead political functions (federation defense, vassalization, create_exile) | Opus |
| 29 | Delete thread_domains, NarrationContext, ActionCategory | Opus |
| 30 | Clean 42 unused tuning constants, 29 dead imports | Opus |
| 31 | Update CLAUDE.md (line counts, file tables, flags) | Opus |
| 32 | Regenerate viewer fixture | Codex |
| 33 | Wire newer analytics extractors into --analyze | Codex |
| 34 | Fix batch parallel LLM client dropping | Codex |
| 35 | Fix resume path divergence | Codex |

### Tier 5: Performance (before M61b scale)

| # | Finding | Source |
|---|---------|--------|
| 36 | Cache adjacency map per turn (graph_distance 72x/turn) | Opus |
| 37 | Cache trade routes (called 3x same inputs) | Opus |
| 38 | Trim or index events_timeline | Opus |
| 39 | Pre-build CivSignals lookup array in Rust tick | Opus |
| 40 | Reduce partition_by_region calls from 7 to 2 | Opus |

---

## Audit Quality Assessment

**Opus strengths:** Deeper system-level analysis. Found all the religion/ecology/politics dead-wiring bugs that require cross-file trace analysis. Comprehensive performance profiling. Full security audit. Covered every subsystem with dedicated reviewers.

**Codex strengths:** Actually ran the tools. Found the hidden red surfaces (test/ failures, clippy, lint) that code-read-only misses. Caught CLI behavior bugs (--compare inert, batch parallel drops LLM, resume divergence). Pragmatic "can we trust the green?" framing.

**Combined:** The two audits are highly complementary. Opus found the deep simulation bugs; Codex found the tooling trust issues. Together they paint a complete picture.

**March 29 audit correction:** The proxy detection sign error (audit #4, P0) was incorrectly flagged. All three code paths correctly apply -5 stability. This should be removed from the open P0 list, reducing it from 16 to 15.
