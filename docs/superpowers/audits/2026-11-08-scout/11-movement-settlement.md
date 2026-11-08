## 11 Movements, migration, settlements and cities
**Map**
- Turn-loop wiring (`src/chronicler/simulation.py`): `tick_movements` (movements.py) always runs at :1224; `run_settlement_tick` at :2420; `tick_cities` at :2475 and `tick_agent_movements` at :2486 (both gated by `_cities_on` / `_agent_movements_on`); `update_contact_ledger` at :2731.
- `movement_branches.py` and `residence_ledger.py` have no direct caller. Their `phase10`/`read_frame`/`on_pool_reset` hooks are dispatched by `livelihoods._hooks` (livelihoods.py:1100-1104, :1251). Branch dues are booked via `wealth_accounting_state.py:189`.
- Python owns state machines (agent_movements ~2060 lines, cities ~1270, residence_ledger ~920, contact_ledger ~780, settlements ~580). Rust owns per-agent mechanics: `movements.rs` (1735; grievance, recruit, founding seeds, census), `migration_drivers.rs` (1120; pull terms, roots, bonds), `migration_closure.rs` and `relocation.rs` (gates called from `tick.rs:837,853`), `community.rs` (ties).
- Python agent movements delegate membership census and tables to native (`agent_movements.py:336-377`, `:1930-1953`).
- Migration has no Python model. Python only reads native migration events (`residence_ledger.py:293-312`).

**Findings**
1. [med] complexity / duplication: Parallel helper sets in `cities.py` and `agent_movements.py`. `_emit` bodies are identical (cities.py:323-335, agent_movements.py:403-415). `_bump`, `_q`, `_add_stat`, `_Tick`, `_Observation`, `_observe`, `_max_civs` (cities.py:904, agent_movements.py:1453) and `_rng` are near-copies. `_rng` differs only in its namespace string (cities.py:241, agent_movements.py:263). Drift risk is high because both feed the same provenance and RNG paths.
2. [med] duplication (Python/Rust): Enum mirrors are hand-kept. CREED/STAGE/END/REFORM constants are in `agent_movements_state.py:21-58` and `movements.rs:31-46`. Tuning constants are separate (`movements.rs:64-116` vs `agent_movements.py:60-130`). Only one cross-language check was found (`tests/test_agent_movements.py:370`, NO_RELIEF). Drift is unguarded.
3. [med] perf/growth: `MovementState.movements` (agent_movements_state.py:142) and `reforms` (:145) are append-only (agent_movements.py:1051, :1688, :1789). Ended movements are never removed, and `CityState.fallen` (cities_state.py:87; cities.py:559) is also append-only. Caps exist only on living movements (`MAX_LIVING=8`, agent_movements.py:83) and on per-entity history (`HISTORY_CAP=60`, agent_movements.py:201; cities.py:96).
4. [med] bounded but large: `residence_ledger` caps rows at `MAX_ROWS=262144`, events at 512 and the log at 64 (residence_ledger_state.py:101-105). `movement_branches` caps lifetime branches at 256 and never reuses them (movement_branches_state.py:13-15).
5. [low] perf: `settlements.find_connected_components` uses `queue.pop(0)` (settlements.py:58-93), which is O(n) per pop. `match_settlements_to_clusters` is a nested S×C loop (settlements.py:534-). Both are fine at current scale but scale poorly.
6. [low] perf: `cities.py:468` rebuilds a set of every city and fallen city on each turn.
7. [low] bug-risk (naming): two systems named "movement". `movements.py` (aggregate, always on, `simulation.py:1224`; `culture.py:59` imports from it) and `agent_movements.py` (opt-in). Easy to confuse in reports and tests.
8. [low] test-gap: `community_admissibility.py` (160 lines) is exercised only by `tests/test_community_admissibility.py`, `tests/test_spec_communities.py` and `scripts/run_python_oracle_checks.py`. It is pinned in `scripts/testing/native_shards_manifest.json`, so it is not dead code.
9. [low] fragile: `movement_branches` and `residence_ledger` are reached only through livelihoods hook names (`_hooks`, `livelihoods.py:1100`). A rename breaks them silently, because `_hooks` finds the module by getattr.
10. [low] dead-code: `community_anchoring.py` (71 lines) is reached from `agent_bridge.py:1257` and `live.py:1394`, so it is live. No fully dead module was found in scope.

**Simulation depth**
- Settlements are detected from a 10×10 density grid with a dense-cell threshold (settlements.py:24-29). There is no hierarchy (hamlet → town → city), no roads and no network between settlements. Adding road or corridor edges between settlement centroids would feed trade and migration.
- Urbanization is split: cities rank by resident count (`rank_for`, cities.py:257), and the urban migration pull (`migration_drivers.rs:129-134`) is separate. Linking the two so city growth draws migrants would make urbanization endogenous.
- Frontier pull exists (`migration_drivers.rs:92-102`), but no code was found that founds a settlement at a frontier destination (unverified; I did not trace `relocation.rs` in full).
- Social movement to revolt: `agent_movements._rise` (:1299) and `_secede` (:1478) are distinct from cities `_revolt` (cities.py:848). The coupling between them was not verified.

**Streamlining candidates**
| Candidate (path or symbol) | Action | Lines saved (approx) | Breaks or blocks | Risk |
|---|---|---|---|---|
| `_max_civs` in cities.py:904 and agent_movements.py:1453 | merge into one shared helper | ~5 | nothing | low |
| `_emit` in cities.py:323 and agent_movements.py:403 | extract to a shared module (keep `provenance.cite` then `observe_now` order) | ~12 | provenance event order must stay identical | low-med |
| `_bump`, `_q`, `_rng` in cities.py:237-247 and agent_movements.py:259-269 | extract with the namespace passed in | ~15 | RNG streams: the namespace strings "cities" and "agent_movements" must stay byte-identical for saved-run reproducibility | med |
| Enum and constant mirrors (`agent_movements_state.py:21-58` vs `movements.rs:31-116`) | generate Python from Rust or add a parity test | ~0 (adds a guard) | none if constants are unchanged; a generated file would be a new pinned artifact | med |
| `community_admissibility.py` (whole file) | keep; do not delete | 0 | `tests/test_community_admissibility.py`, `tests/test_spec_communities.py`, `scripts/run_python_oracle_checks.py` and `scripts/testing/native_shards_manifest.json` pin it. Removal would also break the native shard manifest. | high if removed |
| `movements.py` aggregate model vs `agent_movements.py` | merge or rename | 0 to ~150 | changes outcomes and saved bundle fields. `culture.py:59` imports from it. Not a streamlining change. | high |
| `CityState.fallen` and `MovementState.movements` pruning | prune ended records | unknown | saved-bundle and checkpoint compat for fields already in old runs; `cities.py:521` reads `fallen` for predecessor lookup | high |
| `find_connected_components` queue (settlements.py:58-93) | rewrite with `collections.deque` | ~0 (perf only) | none; component set and scan order stay the same | low |

**Confidence**
Verified by grep and reads: turn-loop call sites, the livelihoods hook dispatch, the state-model caps, the duplicated helper bodies and the pinned-test references. Inferred or unverified: the full Rust `movement_pass` logic and the `relocation.rs` frontier path, the Python/Rust constant values beyond the spot checks, and the revolt coupling. I did not run any tests or builds.
