# Chronicler Audit Verification - 2026-04-04

This is a verification rewrite of the earlier `4-4-26opusaudit.md` draft. It keeps only claims I could confirm against the live repo after the 2026-04-03 remediation pass, drops stale or spec-inconsistent findings, and calls out the remaining work that can be split into parallel lanes.

## Verification Scope

- Checked current source in `src/chronicler/`, `chronicler-agents/src/`, relevant tests, and `docs/superpowers/progress/phase-6-progress.md`.
- Focused checks run:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_m59a_knowledge.py::test_knowledge_deterministic_cross_process tests/test_emergence.py::TestPandemic::test_isolated_civ_not_infected tests/test_factions.py::TestTickFactions::test_tithe_routes_through_accumulator_keep_in_agent_mode`

## Summary

- The original draft overstates current repo risk. Several headline items are already fixed, were never bugs under the documented design, or need a narrower claim than the original wording.
- The live repo still has a small set of real issues, mostly in hybrid-mode accumulator coverage and cross-module consistency.
- I am not carrying forward the original count estimates (`~20 blocking`, `~60 warning`, etc.) because I did not re-verify them one by one.

## Dropped Or Downgraded Original Claims

| Original claim | Verdict | Why |
| --- | --- | --- |
| "Double-count tithe" | Dropped | The current design intentionally has two consumers of merchant-derived tithe data: Python treasury flow via `tithe_base` and Rust priest wealth via `priest_tithe_share`. This is documented in `docs/superpowers/roadmaps/chronicler-phase6-roadmap.md` and `docs/superpowers/specs/2026-03-17-m42-goods-production-trade-design.md`, and the focused tithe regression check passed. |
| "All regions collapse to (0,0), adjacency is non-deterministic" | Downgraded | `world_gen.py` still leaves `Region.x/y` unset, and `adjacency.py` falls back to `0.0`, but that is a spatial-semantics problem rather than a demonstrated RNG nondeterminism bug on current head. |
| "Knowledge packet RNG is blocking nondeterminism today" | Downgraded | `knowledge.rs` still bypasses `set_stream()`, but `tests/test_m59a_knowledge.py::test_knowledge_deterministic_cross_process` passed. The verified issue is stream-discipline drift, not a reproduced determinism break. |
| "No panic recovery anywhere" | Downgraded | I did not find an explicit `catch_unwind` wrapper around the Rust tick path, but the bridge now routes ordinary tick failures through `Result -> PyRuntimeError`, and the blanket original wording no longer matches the post-remediation state described in the progress log. |
| "Large batch of signal vs guard-shock misroutes are blocking" | Dropped as a top-line item | Some cited sites were already fixed, and several surviving `signal` vs `guard-shock` distinctions currently converge through the same shock path. This still deserves cleanup, but not the original severity language. |

## Verified Current Findings

| ID | Severity | Location | Verified finding |
| --- | --- | --- | --- |
| V1 | High | `src/chronicler/tech.py:126-140` | `apply_era_bonus()` and `remove_era_bonus()` still direct-mutate civ stats. `check_tech_advancement()` can spend treasury through the accumulator, then apply military/economy/culture bonuses outside it, so hybrid write-back can overwrite the bonus. |
| V2 | High | `src/chronicler/main.py:321-326`, `src/chronicler/simulation.py:909-937` | Pre-turn injected events are still applied before `run_turn()` creates the turn accumulator. Drought and plague injections therefore bypass the normal hybrid bookkeeping, and plague still mutates regional population directly. |
| V3 | High | `src/chronicler/politics.py:1040-1188`, `src/chronicler/succession.py:324-334` | Restoration paths still mutate civ stats directly with no accumulator path. This is the same class of hybrid visibility problem as era bonuses and injected events. |
| V4 | Medium | `src/chronicler/ecology.py:126-139` | Famine computes `mult = get_severity_multiplier(...)` but only applies it to stability. Population loss still uses the unscaled base drain. |
| V5 | Medium | `chronicler-agents/src/demographics.rs:69-100` | Fertility still uses soil only (`0.5 + soil * 0.5`) even though ecology stress and the legacy oracle both treat water as part of the reproductive environment. Fertility and mortality are still using different ecology assumptions. |
| V6 | Medium | `src/chronicler/emergence.py:368-388` | Pandemic spread still checks trade connectivity against the set of all infected controllers, not the source region's controller. Spread is therefore broader than "infected region -> trade-connected neighbor" semantics. |
| V7 | Medium | `src/chronicler/world_gen.py:75-100`, `src/chronicler/adjacency.py:100-139` | Generated regions still have no coordinates, while adjacency's k-nearest fill uses Euclidean distance with `None -> 0.0`. The graph is reproducible, but it is not spatially meaningful. |
| V8 | Medium | `src/chronicler/great_persons.py:38-59` | `ROLE_MODIFIERS` and `get_modifiers()` still have no consumers. The modifier registry remains inert. |
| V9 | Low | `chronicler-agents/src/ffi/mod.rs:541-552` | Initial spawn still uses legacy `region_id * 1000 + OFFSET` stream assignment for personality and age instead of the packed stream scheme used elsewhere. |
| V10 | Low | `chronicler-agents/src/knowledge.rs:572-588` | Knowledge transmission still derives RNG by XORing seed bytes instead of using `set_stream()`. This is a discipline and maintainability gap more than a reproduced determinism failure. |
| V11 | Low | `chronicler-agents/src/ffi/mod.rs:1041-1137` | The deprecated `replace_social_edges()` shim still diffs hash sets in arbitrary order and reads columns by index. It remains a cleanup target while the compatibility layer exists. |

## Claims Intentionally Not Carried Forward

- I did not keep the original crash-specific wording for `check_restoration()`. I confirmed the direct-mutation accumulator gap, but I did not reproduce the claimed `ValueError` path on current head.
- I did not keep the original blanket severity totals or the "Top 12" ranking. Too many of those items were stale, partially true, or needed tighter wording after the 2026-04-03 remediation pass.

## Parallelism Opportunities

### Lane A: Hybrid accumulator hardening

- Files: `src/chronicler/tech.py`, `src/chronicler/main.py`, `src/chronicler/simulation.py`, `src/chronicler/politics.py`, `src/chronicler/succession.py`
- Deliverable: acc-aware wrappers plus regression tests for hybrid write-back preservation
- Split:
  - A1: era bonus routing
  - A2: injected-event routing
  - A3: restoration and exile restoration routing

### Lane B: Ecology and black-swan semantics

- Files: `src/chronicler/ecology.py`, `src/chronicler/emergence.py`, `chronicler-agents/src/demographics.rs`
- Deliverable: severity-scaled famine drain, water-aware fertility, source-controller pandemic gating, matching tests
- Coupling: low; Python and Rust changes are mostly independent until the final parity pass

### Lane C: Spatial semantics and dormant content

- Files: `src/chronicler/world_gen.py`, `src/chronicler/adjacency.py`, `src/chronicler/great_persons.py`
- Deliverable: deterministic coordinates or an explicit non-spatial adjacency rule, plus either wiring or removing GP modifiers
- Coupling: independent of Lanes A, B, and D

### Lane D: Rust RNG and compatibility cleanup

- Files: `chronicler-agents/src/ffi/mod.rs`, `chronicler-agents/src/knowledge.rs`, relationship shim tests
- Deliverable: unified stream discipline, explicit determinism tests, and eventual removal or hardening of `replace_social_edges()`
- Coupling: independent, but should finish with a cross-process determinism run

## Suggested Validation After Fixes

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_simulation.py tests/test_politics.py tests/test_succession.py tests/test_tech.py`
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_emergence.py tests/test_agent_bridge.py tests/test_factions.py`
- `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
- Add missing regression tests for hybrid era bonus visibility, injected-event accumulator routing, water-aware fertility, and packet-level knowledge determinism if Lane D changes RNG logic.
