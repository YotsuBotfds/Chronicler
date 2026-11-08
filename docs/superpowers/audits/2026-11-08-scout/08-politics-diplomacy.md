## 08 Politics, diplomacy, factions, institutions
**Map**
- `politics.py` (1906 lines) is the Phase 10 consequence layer: secession, capital loss, vassal rebellion, federations, proxy wars, congress, restoration, twilight absorption, long peace, balance of power. `simulation.py:527-549` calls the Python-only steps (governing costs, tribute, proxy wars, exile, balance of power, fallen empire, twilight, long peace) in every mode. `simulation.py:1426-1456` then picks the collapse-family runner.
- Rust `chronicler-agents/src/politics.rs` (3810 lines) is an 11-step pass (`run_politics_pass`, politics.rs:3037). Steps: capital loss, secession, allied turns, vassal rebellion, federation formation/dissolution, proxy detection, restoration, twilight absorption, decline tracking, forced collapse.
- Routing (verified):
  - Agent modes (shadow/hybrid/demographics-only): `simulation.py:2445-2448` uses `agent_bridge._sim`, which calls `tick_politics` through `politics_bridge.call_rust_politics` (`politics_bridge.py:1791`).
  - `--agents=off` with the native module: `main.py:1933-1935` and `main.py:360-372` build a standalone `PoliticsSimulator`.
  - No native module (ImportError), or tests: `politics_runtime` is None and `simulation.py:1441-1455` runs the Python oracle.
- Action weights: `action_engine.py:1218-1290` composes trait, tech-focus, faction, governance, finance, diplomacy, nomad and holy-war multipliers. Each contributor bucket is capped via `_ContributorBuckets` (`action_engine.py:1039-1071`).
- Diplomacy (`diplomacy.py`, 1953 lines, plus `diplomacy_state.py`, 107 lines): grievance/goodwill memories, treaties (trade pact, protecting, tribute), war joining, embargoes, a vassal ladder (`_ladder_tick`, `diplomacy.py:1487`), and tribute.
- Factions/succession: `factions.py` (804 lines) holds the influence model and power struggles. `succession.py` (351 lines) holds the crisis state machine. `compute_crisis_probability` (`succession.py:31-78`) multiplies about ten factors and clamps to [0.05, 0.40].
- Institutions and governance: `institutions.py` (603), `governance_capital.py` (477), `elite_metrics*.py`, `intelligence.py` (228). Used through `governance_runtime`, and `governance_kernel_harness` for the kernel tests.
- `emergence.py` (1088 lines): black swans, environment events, tech regression, stress computation.

**Findings**
1. [med, duplication] Two implementations of the same 11-step rules. Rust step 11 (politics.rs:2888-3025) is computed, then discarded when Python is authoritative: `simulation.py:1436` filters out `op[0] == 11`, and the Python collapse block at `simulation.py:1466-1492` applies the effect. Drift risk is real: the thresholds in that block (asabiya<0.1, stability<=20) are not verified against the Rust body. Suggested action: either delete Rust step 11 and its output path, or make Rust authoritative and delete the Python copy.
2. [med, fragile] Defaults for the same tuning keys live in three places: `politics.py:194,201` (inline `get_override(..., 5)` and `(..., 10)`), `politics_bridge.py` `configure_politics_runtime` (about line 1497), and `PoliticsConfig::default` (politics.rs:281). Suggested action: keep one default table in `tuning.py` and read it from all three.
3. [med, magic-numbers] Unnamed literals in politics.py: secession probability divisor `/100` (line 205), breakaway fraction `ceil(len/3)` (250), score weights `0.7/0.3` (246), new-civ stability 40 and asabiya 0.7 (312, 320, 328), and thresholds at lines 524 (`stability <= 40`), 1178 (`stability >= 20`), 1746 (`military > 60`). Only the first is tunable through `K_` keys. Suggested action: move to tuning or a named constants block, with the same values.
4. [med, fragile] `emergence.py:226` seeds the black-swan RNG as `random.Random(seed + world.turn * 997)`. Everywhere else uses `stable_hash_int`, which the Rust side mirrors. Changing this is a replay-breaking change, so it needs a deliberate decision. `emergence.py:769-770` takes `max(matching_probs)` across independent regression triggers, which is a modelling choice rather than a combination rule.
5. [med, sim-depth] `succession.py:31-78`: the probability is a product of about ten multipliers and then clamped to [0.05, 0.40]. The clamp hides the interaction, and `region_factor = len(regions)/5` grows linearly. This is hard to tune and hard to explain.
6. [low, dead-code] `simulation.py:768` defines `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD = 0.04  # noqa: F841`. Grep over `src/`, `tests/`, `scripts/` and `chronicler-agents/src/` finds no other use.
7. [low, test-gap] `politics.py:714` (`_would_exit_federation`) and `politics.py:1482` (`best_twilight_absorber`) have no direct tests. They are used only inside politics.py.
8. [low, duplication] `politics.py:281-284` rebuilds a local `_VALUE_POOL` list on every secession. A module constant would do.
9. [med, duplication] Python-only steps run in every mode (`simulation.py:527-549`), while the Rust pass covers only the collapse family. So a single politics turn splits across two runtimes, and the boundary is not documented in one place. Suggested action: write the boundary into the politics docs and add a parity test that checks the split.
10. [low, perf] `diplomacy.py:975-1013` `weight_modifiers` scans `_living(world)` and calls `grievance`, `treaties_between_any` and `_threat` for each civ every turn. Not profiled; unverified.
11. [low, docs] The `politics.rs` header (line 4) cites `simulation.py:1020-1041` for the forced collapse. That range is now the Python collapse at about 1466-1492. Stale line references.

**Simulation depth**
- Internal politics is thin: legitimacy and succession exist (`governance_capital`, `succession`), but there is no law, bureaucracy or tax-administration layer. Taxation is `collect_tribute` (politics.py:583) and `apply_governing_costs`.
- Revolts are binary per step (`check_vassal_rebellion`, politics.py:610). Gradual revolt intensity with food or legitimacy inputs would deepen it.
- Multi-polity diplomacy has treaties, alliances and congress, but no coalition-level bargaining. The ladder in `diplomacy.py:1487` is one overlord and one vassal at a time.
- `emergence.py` is mostly weighted random triggers (black swans, regression, pandemic spread) plus scripted handlers. Little of it emerges from agent or polity interaction.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `simulation.py:768` `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | delete | 1 | None found by grep across src, tests, scripts, Rust. Not checked against `scripts/testing/native_shards_manifest.json` (unverified). No CLI flag or bundle field. | low |
| `politics.py:281-284` local `_VALUE_POOL` | extract to module constant | 0 (dedupe) | RNG draw order unchanged. No bundle impact. | low |
| Rust step 11, `politics.rs:2888-3025` (about 138 lines) | delete, or make authoritative and delete the Python copy at `simulation.py:1466-1492` | about 138 Rust, or about 27 Python | Breaks Rust tests around `politics.rs:3540` and the step-11 seq assertions. Requires a native rebuild and a shard-manifest check (unverified). Changes the 11-op contract. Historical bundles keep their collapse results; the path must stay consistent. | med-high |
| Default values for politics tuning keys (`politics.py:194,201`, `politics_bridge.py` about 1497-1520, `politics.rs:281-308`) | consolidate into one defaults table in `tuning.py` | about 30 | Behaviour unchanged if the values are equal. Breaks nothing observable. The Rust side needs a passed config, so the change crosses the FFI boundary. | low |
| Python oracle fallback, `simulation.py:1441-1455` | NOT a candidate: required for parity tests and no-native installs | 0 | Removing it breaks `test_politics_parity.py` and the no-native path. | high if attempted |
| `emergence.py:226` black-swan RNG seed `seed + turn*997` | rewrite to `stable_hash_int` | 0 | Changes every replay with black swans. Breaks historical checkpoint equality. Needs a deliberate compatibility decision. | med |

**Confidence**
Verified by grep and reading: routing in `simulation.py`, `main.py` and `politics_bridge.py`; the step lists; the dead-code and test-gap checks; the Rust step-11 filter. Inferred: the Python and Rust collapse thresholds match in content, which I did not compare line by line. Not read in depth: `institutions.py`, `governance_capital.py`, `elite_metrics*.py`, `intelligence.py`, most of `diplomacy.py` and `factions.py` beyond the weight and succession paths. Not run: no tests, no simulation.
