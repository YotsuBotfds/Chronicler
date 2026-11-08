## 20 Rust agent core (tick, pool, needs, satisfaction, behaviour, demographics)
**Map**
- `chronicler-agents/src/tick.rs` (3828 lines) is the turn orchestrator. `tick_agents` (1525) wraps `try_tick_agents` (267), which dispatches to the single body `try_tick_agents_with_movements_observer` (498-1523). The FFI (`ffi/mod.rs:2006, 2014, 2021`) calls the mobility-gate, delivery and movements variants.
- Phase order in the body: catastrophe/targeted deaths (527) → memory decay and skill growth (554-571) → wealth (576) → provisioning/retail (589-599) → needs (606) → relationships (613) → merchants (620-648) → knowledge and movements (653-661) → satisfaction (666-667) → decisions per region via rayon (738-787) → household consolidation, closure, gate (800-857) → sequential apply (869-960) → migration reset and spatial drift (968-993) → battle/conquest intents (1000-1088) → demographics per region via rayon (1095-1122) → sequential death and birth apply (1187-1309) → death cleanup, culture, conversion (1316-1377) → memory write, marriage, formation (1441-1472).
- `pool.rs` (1901 lines) is an SoA pool of about 70 `Vec` columns with a LIFO free list (`try_spawn` 340, `kill` 537). `sort.rs`, `spatial.rs` (1976) and `persist.rs` (576) sit alongside.
- `needs.rs` (1271) holds six needs (safety, material, social, spiritual, autonomy, purpose). `satisfaction.rs` (1025) combines resource, trade, shock, cultural and religious terms. `behavior.rs` (~1400) has Gumbel-argmax choice over rebel, migrate and switch utilities. `demographics.rs` holds mortality, fertility and hunger.
- Roughly 9.7k lines in the named source set; tests are in `tests/*.rs` and in `#[cfg(test)]` modules.

**Findings**
1. [med] fragile: u16 turn truncation with inconsistent handling. `formation.rs:661, 809, 1519` and `knowledge.rs:1159` and `tick.rs:1448` use `turn as u16` (wraps). `relationships.rs:353` saturates at `u16::MAX`. Packet ordering (`knowledge.rs:289, 369, 419`) and the stored `source_turn` compare u16 values, so ordering breaks after 65535 turns. Whether a run reaches that horizon is unverified. Action: one u32 or saturating timestamp helper, used everywhere.
2. [med] perf: `IdSlots::new` (`pool.rs:29-42`) allocates a `max_id+1` u32 table on each call. Ids come from `next_id` (`pool.rs:354`), so `max_id` tracks lifetime births, not live population, up to a fallback at `16*cap + 2^20`. It is built at least three times per tick (`tick.rs:64` via `build_death_apply_context` at 535 and 1159, and `tick.rs:717`). Action: keep a persistent id→slot index updated in `try_spawn` and `kill`.
3. [med] perf: per-tick O(capacity) allocations: `alive_slots` (`tick.rs:551`), `post_alive` (1316), `partition_by_region` twice (1000, 1344), `pre_conversion_bits` (1362), `signals.build_index()` twice (1094, 1345). Action: a reusable scratch struct for these buffers.
4. [med] complexity: `try_tick_agents_with_movements_observer` is about 1000 lines with about 20 parameters, several `Option` flags (merchant_state, delivery, gate, observer) and manual `original_actions` snapshots (816-857). Action: extract named phases with a context struct. Behaviour is pinned by the in-file tests (`tick.rs:2290-3470`).
5. [med] duplication: `try_spawn` writes every column twice, once in the reuse branch (`pool.rs:360-428`) and once in the grow branch (431-499). Any new column must be added in both or it silently keeps stale data. Action: one init helper, or reset-then-push.
6. [med] fragile: `kill()` (`pool.rs:537-557`) says it zeroes key fields to prevent stale-data leaks. It leaves needs, memory, relationship targets, trip state, x/y and `movement_ids` (partly) untouched. Safety depends on every reader checking `is_alive` first (`tick.rs:1503` does). Action: fix the comment, or zero the columns.
7. [low] dead-code: `behavior.rs:1275-1398` `evaluate_region_decisions_v1` is `#[cfg(test)] #[allow(dead_code)]` and has no callers. grep for the name gives only its definition and the header comment.
8. [low] dead-code: `sort.rs:67` `sort_by_region` is used only by `benches/cache_bench.rs:139, 157`.
9. [low] perf/profiling: `spatial.rs:1365-1372` computes `sorted_iteration_order` and discards it. This is opt-in via `TickOptions::profile_spatial_sort` (`scale.rs:61`), set through FFI `set_spatial_sort_profiling` (`ffi/mod.rs:1147-1156`). It feeds the `sort_time_us` diagnostic key, which `tests/test_rust_turn_speed.py:21` asserts.
10. [low] dead-code: `satisfaction.rs:36, 43` `resource_satisfaction` and `trade_satisfaction` have callers only in the `#[cfg(test)]` module (lines 613-638).
11. [low] fragile: `tick.rs:897, 919` `let _ = old_occ;` and `tick.rs:1509-1511` repeat the `food_access` clears from 586-588. Minor noise.
12. [low] panic path: `pool.rs:531` `spawn()` and `tick.rs:1550` `tick_agents` use `.expect(AGENT_POOL_EXHAUSTED)`. This is reachable only on u32 id exhaustion, but it panics across the FFI. Unwraps in `tick.rs` from 2301 onward are inside tests. No unwrap appears in the production tick body.
13. [low] docs: `agent.rs:96-144` has about 10 `#[allow(dead_code)]` reserved RNG offsets. These protect the stream registry against collisions, so keep them.

Determinism checks that passed (verified by reading): `region_groups.par_iter().collect()` (`tick.rs:744-757, 765-785`) and the demographics collect (1099-1121) preserve region order, so results do not depend on thread count. Per-region RNG streams are `(region<<48)|(turn<<16)|offset` (`tick.rs:747, 771, 1105`), with offsets at most 2600 (`agent.rs:94-144`), so streams are disjoint. HashMap and HashSet are used only for `get`, `entry` and `contains` (`tick.rs:64-84, 236-240, 1166-1176, 1319`), never iterated. Float sums (`tick.rs:1126-1148`) run sequentially in region order. Thread-count independence is tested at `tick.rs:2339`.

**Simulation depth**
- Needs are six scalars that decay and restore. Restoration is social (co-resident bonds, `needs.rs:244`), conquest grievance (`needs.rs:280`), and inheritance at birth (`needs.rs:563-576`). Add needs that feed back into occupation choice, not only into utility.
- Behaviour picks among rebel, migrate and switch (`behavior.rs:113-120, 509`) with a temperature-scaled Gumbel draw (`behavior.rs:88`). Agents do not learn from outcomes, and wages do not depend on local supply. A simple per-occupation price signal would give switching a real economic reason.
- Satisfaction is additive with a capped penalty (`satisfaction.rs:99`). Relationships are capped at 8 slots per agent (`pool.rs` rel_* columns). Raising the cap or adding trust/grudge decay would widen social effects.
- Demographics are per-region rate formulas (`demographics.rs:175-199`). Household effects, kin inheritance and marriage exist, but no ageing-based labour productivity or disease immunity carries across generations.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `behavior.rs:1275-1398` `evaluate_region_decisions_v1` | delete | ~124 | none found: only its definition references it; header says "preserved for regression" but no test calls it | low |
| `sort.rs:67` `sort_by_region` | delete with its bench arm | ~15 | `benches/cache_bench.rs:139, 157` | low |
| `satisfaction.rs:36-50` `resource_satisfaction`, `trade_satisfaction` | delete with their tests | ~25 | unit tests at `satisfaction.rs:613-638` only | low |
| `pool.rs:360-499` duplicated init in `try_spawn` | merge the reuse and grow branches into one column-init helper | ~65 | none for persisted layout; hot path, so run determinism tests | med |
| `spatial.rs:1365-1372` plus `sort.rs:108-115` profiling sort | delete, or keep and move behind the flag | ~10 spatial, ~8 sort | FFI `set_spatial_sort_profiling` (`ffi/mod.rs:1147-1156`), `TickOptions::profile_spatial_sort` (`scale.rs:61, 185, 231`), `sort_time_us` key, `tests/test_rust_turn_speed.py:21`; no bundle field found | med |
| `tick.rs` duplicate `food_access` clears (1509-1511) and `let _ = old_occ` (897, 919) | delete | ~5 | none | low |
| `tick.rs:498-1523` monolith | extract phases into typed structs (not a deletion) | net ~0, enables expansion | the in-file tests at `tick.rs:2290-3470` pin behaviour; no CLI flag | high |
| `persist.rs` `field_schema` | keep | 0 | used by schema fingerprint; removing it changes saved-bundle fingerprints (historical import compat) | do not delete |
| `agent.rs:96-144` reserved `#[allow(dead_code)]` offsets | keep | 0 | removing an offset can reintroduce stream collisions | do not delete |

**Confidence** Verified by reading `tick.rs` 1-1523, `pool.rs` `try_spawn`/`kill`/`IdSlots`, `persist.rs` grep, and by grep counts over `chronicler-agents/`, `tests/`, `scripts/`, `viewer/` and `src/` (fixtures excluded). Not verified: `needs.rs`, `satisfaction.rs` and `behavior.rs` bodies (outlines only); `formation.rs` and `knowledge.rs` u16 paths were checked only at the call sites; whether any run reaches turn 65535; cargo was not run.
