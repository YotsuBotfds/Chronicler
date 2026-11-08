## 03 Python-Rust agent bridge (agent-bridge)
**Map**
- `agent_bridge.py` (3241 lines): `AgentBridge` class (1214-3240, about 2000 lines) wraps the Rust `AgentSimulator`. Module builders: `build_region_batch` (458-833), `build_signals` (899-1057), `build_settlement_batch` (851), and `configure_*_runtime` (1058-1213).
- Turn-loop hooks: `simulation.py:2265` calls `sync_regions`, then ecology (2270 off-mode `build_region_batch`), then `tick_agents` (2354/2363). `simulation.py:1985-1987` resets `_dead_agents_this_turn`.
- `bridge_contract.py` (115 lines): 24-field snapshot schema mirror, opt-in validator. Only `ffi/schema.rs::snapshot_schema` (10-38) is the producer.
- `ffi_constants.py` (129 lines): terrain, cultural-value, bond-type and capacity constants; no runtime Rust import.
- `politics_bridge.py` (1840), `sidecar.py` (577), `decision_delivery.py` (251), `shadow.py` (114), `shadow_oracle.py` (174).
- Rust side: `ffi/mod.rs` (5855 lines) parses region/civ batches at 1164-1523 and 1898-2024; `signals.rs` (parse_civ_signals 131-199, contested 289-300).

**Findings**
1. [med] bug. Transient region flags are cleared in two places with different lists. Agent modes clear inside `build_region_batch` (agent_bridge.py:544-571). Agent-off clears inside `simulation.py:2381-2387`, which omits `_raided_this_turn` (set at nomads.py:1163) and `_catastrophe_deaths_this_turn` (staged by utils.py:86-87). With no `ecology_runtime` those two never clear. Only `build_region_batch` reads them, so the effect is latent (first agent-mode sync after an off-mode run). Action: one `clear_region_transients(world)` helper called from both sites.
2. [med] unverified. Clear timing across functions. In agent modes a flag set after `sync_regions` (simulation.py:2265) is consumed at the next turn's sync. Set sites include battles.py:278, occupation.py:83, politics.py:379/460 and nomads.py:1163. No test found that pins this ordering. Action: add a two-turn consume/reset test as AGENTS.md requires for bridge signals.
3. [low] fragile. `build_region_batch` is also called in `AgentBridge.__init__` priming (agent_bridge.py:1272), which consumes one-turn flags before turn 1. Harmless today, but it is a second consumer outside the turn loop.
4. [med] duplication. Constant mirrors have no single source. `TERRAIN_MAP` (ffi_constants.py:16-28) mirrors `region.rs:7-11`. `BOND_TYPES` (ffi_constants.py:51-68) mirrors `relationships.rs:7-18`, with `is_positive_valence` (relationships.rs:47-48) hand-coded as `0|2|3|4|5|6` and `POSITIVE_VALENCE_BONDS` (ffi_constants.py:70) matching. `VALUE_EMPTY=0xFF` (ffi_constants.py:43) mirrors `agent.rs:193`. Parity is claimed for bond types only (test_bond_types.py per the ffi_constants comment, not opened). Terrain and cultural-value parity: unverified. `FACTION_MAP` (agent_bridge.py:88) has 5 entries including burgher; Rust dominant_faction parsing not checked.
5. [low] dead-ish. Snapshot `ambition` (schema.rs:65; bridge_contract.py:65) is read by no runtime Python consumer (grep: only bridge_contract.py and validation_io.py). It is part of the pinned 24-field contract, so it must not be removed.
6. [low] Columns sent vs read. I compared the civ-signal batch (agent_bridge.py:1011-1057 keys) with `parse_civ_signals` (signals.rs:131-199). Every sent column is read. Region batch: all 71 string keys (agent_bridge.py:458-833) occur in Rust, including `is_contested` (mod.rs:1234). Events schema `migration_driver` is read (agent_bridge.py:152).
7. [low] complexity. `build_signals` (899-1057, about 160 lines) writes each shock, demand and personality column out by hand with the same `_validated_civ_signal` pattern. A table of (name, source, bounds) would remove about 50 lines.
8. [med] complexity. Largest functions: `build_region_batch` 458-833 (about 375 lines), `_write_sidecar_snapshot` 1858-2088 (about 230), `_process_tick_results` 1641-1826 (about 185), `_aggregate_event_summaries` 2763-2948 (about 185), `__init__` 1215-1311 (about 96).
9. [med] test-gap. `tests/test_religion.py:577-614` checks clearing only through `build_region_batch`. No test covers the agent-off clear block or the raided/catastrophe fields.
10. [low] unverified. Native-missing behaviour: `_load_agent_simulator_class` (agent_bridge.py:35) and version-mismatch handling were not read. Not verified.
11. [low] sim-depth or docs. Shadow mode is wired into the CLI (main.py:784, 1891-1896) and has `tests/test_shadow_oracle.py`. It is not abandoned in code. Whether it is used scientifically is unverified.

**Simulation depth**
- Off-mode ecology reads `build_region_batch` but has no transient-state contract. Making the one-turn signals explicit per mode would let off-mode and agent-mode share ecology inputs.
- Religion and politics flags (`schism_convert_*`, `_seceded_this_turn`) are one-turn only and carry no decay. Richer multi-turn memory would need the bridge's consume/reset discipline extended to them.
- Civ signals are fixed-width per civ (shocks, demand, personality). Adding per-faction or per-region signal families would follow the existing `_validated_civ_signal` pattern.

**Streamlining candidates**
| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `build_signals` per-column validation (agent_bridge.py:899-1057) | rewrite as table-driven loop over (name, source, bounds) | ~50 | error strings pinned by test_agent_bridge.py:182-208 (keep messages) | low |
| Transient clears: agent_bridge.py:544-571 and simulation.py:2381-2387 | extract `clear_region_transients(world)`, call from both sites, add raided/catastrophe to the off-mode path | ~8 net (fixes item 1) | none for CLI; tests/test_religion.py:601 pins the agent-mode clear | med |
| `build_region_batch` (agent_bridge.py:458-833) | extract per-group helpers (ecology, politics, religion, memory) | ~0 (complexity only) | test_agent_bridge.py:821-916 and test_economy_bridge.py:384 call it directly; keep signature | med |
| Constant mirrors (ffi_constants.py vs region.rs, relationships.rs) | generate or parity-test from one source | ~0 (safety) | test_bond_types.py must stay green | low |
| Snapshot `ambition` (bridge_contract.py:65) | do NOT delete | 0 | pinned native 24-field schema (schema.rs:65) and validation_io | high if removed |
