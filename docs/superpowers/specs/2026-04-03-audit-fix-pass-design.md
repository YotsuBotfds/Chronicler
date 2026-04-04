# 2026-04-03 Audit Fix Pass — Design Spec

> Fixes 3 confirmed blockers and 2 confirmed behavioral warnings from the 2026-04-03 10-agent cross-cutting audit. Minimum regression tests to prove each fix. Deferred appendix for hygiene follow-up.

---

## Fix 1: B1 — Holy-war clergy bonus dead in agent modes

### Problem

`compute_conversion_signals()` (religion.py:299-301) reads AND clears `conquest_conversion_active` before `tick_factions()` (factions.py:318-323) reads the same flag. The `EVT_HOLY_WAR_WON` clergy influence boost never fires in agent-backed modes. In `--agents=off`, the religion block is skipped (no `_agent_snapshot` at simulation.py:1004), so the flag survives to factions — off-mode is unaffected.

### Fix

Remove `region.conquest_conversion_active = False` from religion.py:301. The flag is already unconditionally reset at turn start by simulation.py:1564. Religion reads the flag at line 299 to decide conversion behavior — it does not need to own the lifecycle clear. Both `compute_conversion_signals` and `tick_factions` see the flag within Phase 10, and the turn-start clear handles cleanup.

Also update the stale "reads and clears" docstring/comment at religion.py:241 to reflect that the function reads but does not clear the flag.

### Test

One phase-order regression test in `test_factions.py`: set `conquest_conversion_active=True` on a region controlled by a war-winning civ, call `compute_conversion_signals` then `tick_factions` in Phase 10 order, assert clergy influence increased by `EVT_HOLY_WAR_WON`. The existing turn-start cleanup test at test_simulation.py:1119 already covers lifecycle cleanup.

### Files touched

- `src/chronicler/religion.py` — remove line 301 clear, update docstring at ~line 241
- `tests/test_factions.py` — add phase-order regression test

---

## Fix 2: B3 — Asabiya collapse missing severity multiplier

### Problem

simulation.py:1189-1190 halves military/economy via `civ.military // 2` with no `get_severity_multiplier()` call. Every other negative stat site (~30) applies severity. Violates the cross-cutting rule at CLAUDE.md: "All negative stat changes go through M18 severity multiplier (except treasury, ecology)."

### Fix

Add `mult = get_severity_multiplier(civ, world)` before the collapse computation. Scale the loss from the current `// 2` baseline, preserving exact behavior at `mult=1.0` for odd values:

```python
mult = get_severity_multiplier(civ, world)
base_mil_target = clamp(civ.military // 2, STAT_FLOOR["military"], 100)
base_eco_target = clamp(civ.economy // 2, STAT_FLOOR["economy"], 100)
mil_loss = int((civ.military - base_mil_target) * mult)
eco_loss = int((civ.economy - base_eco_target) * mult)
collapsed_military = clamp(civ.military - mil_loss, STAT_FLOOR["military"], 100)
collapsed_economy = clamp(civ.economy - eco_loss, STAT_FLOOR["economy"], 100)
```

At `mult=1.0`, loss equals `civ.military - base_mil_target` which preserves the current collapsed target exactly (floor-half target, ceil-half loss for odd values). At `mult > 1.0` (high world stress, the default live range per emergence.py:112), loss exceeds the current collapse result — the collapse hits harder under stress. At `mult < 1.0` (only reachable via tuning override), loss is softened.

Both the accumulator path (`guard-shock`) and the direct-mutation path (`else` branch) use the same computed `collapsed_military`/`collapsed_economy` values.

### Test

Primary test in `test_severity.py`: trigger asabiya collapse with `mult > 1.0` (e.g., high `civ_stress`), assert the collapsed stat is lower than the current collapse result (`military // 2`). Secondary: same collapse with `mult = 1.0` (zero `civ_stress`), assert collapsed stat matches current `military // 2` target exactly for both even and odd input values.

### Files touched

- `src/chronicler/simulation.py` — ~lines 1189-1196
- `tests/test_severity.py` — add collapse severity regression

---

## Fix 3: B6 — Spatial arithmetic stream collisions

### Problem

`migration_reset_position` (spatial.rs:691-696) and `newborn_position` (spatial.rs:723-728) compute ChaCha8 streams as `agent_id * 1000 + region_id * 100 + turn + OFFSET` — arithmetic, not the bit-packed formula documented at agent.rs:92. Collisions are easy to construct (e.g., `1*1000 + 10*100 + 0 + 2000 == 2*1000 + 0*100 + 0 + 2000`). Both functions share `SPATIAL_POSITION_STREAM_OFFSET = 2000` with no disambiguation.

### Fix

The standard packed layout `((region_id) << 48) | ((turn) << 16) | OFFSET` uses all 64 stream bits for `(region, turn, offset)` with no room for an agent dimension. Spatial placement needs per-agent uniqueness within the same region+turn.

Approach: keep the packed `(region, turn, offset)` stream ID for region+turn isolation, and mix `agent_id` / `child_id` into the **seed** via a small helper:

```rust
/// Derive a per-agent spatial seed from the master seed and agent id.
/// XORs agent_id bytes into the first 4 bytes of a copy of master_seed,
/// producing a distinct seed per agent while preserving the remaining
/// 28 bytes of entropy.
#[inline]
fn spatial_seed(master_seed: &[u8; 32], agent_id: u32) -> [u8; 32] {
    let mut seed = *master_seed;
    let id_bytes = agent_id.to_le_bytes();
    seed[0] ^= id_bytes[0];
    seed[1] ^= id_bytes[1];
    seed[2] ^= id_bytes[2];
    seed[3] ^= id_bytes[3];
    seed
}
```

Then both functions use:
```rust
let seed = spatial_seed(master_seed, agent_id);
let mut rng = ChaCha8Rng::from_seed(seed);
rng.set_stream(spatial_stream(region_id, turn, SPATIAL_POSITION_STREAM_OFFSET));
```

Where `spatial_stream` is the standard packed helper matching `conversion_stream`/`culture_stream`:
```rust
#[inline]
fn spatial_stream(region_id: u16, turn: u32, offset: u64) -> u64 {
    debug_assert!(offset <= u16::MAX as u64);
    ((region_id as u64) << 48) | ((turn as u64) << 16) | offset
}
```

Register `NEWBORN_POSITION_STREAM_OFFSET = 2100` in agent.rs `STREAM_OFFSETS` block to disambiguate newborn from migration placement. `newborn_position` uses the new offset; `migration_reset_position` keeps `SPATIAL_POSITION_STREAM_OFFSET = 2000`.

### Test

Add a Rust test (in `determinism.rs` or new `test_spatial_streams.rs`):
1. Two `(agent_id, region_id, turn)` triples that collide under old arithmetic — verify the derived seeds (via `spatial_seed`) are distinct and the jitter outputs differ.
2. Migration and newborn for the same agent/region/turn produce distinct jitter values (different stream offsets via `spatial_stream`).
3. Same agent/region/turn with same offset produces identical jitter output (determinism).

Test against derived seeds and jitter values, not final clamped positions — clamping can collapse distinct RNG outputs to the same coordinates at boundary values.

### Files touched

- `chronicler-agents/src/spatial.rs` — add `spatial_seed` + `spatial_stream` helpers, update both functions
- `chronicler-agents/src/agent.rs` — register `NEWBORN_POSITION_STREAM_OFFSET = 2100`
- `chronicler-agents/tests/determinism.rs` or new test file — stream collision regression

---

## Fix 4: W17 — Grudge accumulation unbounded

### Problem

action_engine.py:962-971 multiplies WAR weight per grudge: `weights[WAR] *= (1.0 + intensity * 0.5)` independently for each grudge. With 3 grudges at max intensity (reachable via `inherit_grudges` at succession), WAR gets `*= 3.375x`, saturating the weight cap and making all other modifiers (traditions, tech focus, factions, holy war) ineffective since the cap is already hit by grudges alone.

### Fix

Cap the accumulated grudge multiplier product. Extract a tiny helper for testability:

```python
def _grudge_war_multiplier(grudges: list[dict], cap: float) -> float:
    """Multiplicative WAR boost from active grudges, capped.

    Grudges are dicts with "intensity" and "rival_civ" keys
    (see Leader.grudges in models.py).
    """
    product = 1.0
    for grudge in grudges:
        intensity = grudge.get("intensity", 0.0)
        if intensity >= 0.5:
            product *= (1.0 + intensity * 0.5)
    return min(product, cap)
```

Call site replaces the per-grudge loop:
```python
grudge_cap = get_override(self.world, K_GRUDGE_CAP, 2.0)
weights[ActionType.WAR] *= _grudge_war_multiplier(civ.leader.grudges, grudge_cap)
```

Register `K_GRUDGE_CAP = 2.0` as a tuning constant in `tuning.py`. The `2.0` cap means even maximum grudge stacking leaves effective headroom: with base `0.2`, grudges push WAR to `0.4`, and traditions/tech/factions can still differentiate before the final `0.50` weight cap bites.

### Test

Test in `test_action_engine.py` as a ratio comparison: construct two identical worlds, one with 3 max-intensity grudges and one with 0 grudges, holding all other modifiers constant. Assert the grudge world's WAR weight is at most `base * K_GRUDGE_CAP` (i.e., `0.4`), not the uncapped `0.675` the old code would produce.

### Files touched

- `src/chronicler/action_engine.py` — replace grudge loop with `_grudge_war_multiplier`, add `K_GRUDGE_CAP` import
- `src/chronicler/tuning.py` — register `K_GRUDGE_CAP`
- `tests/test_action_engine.py` — ratio comparison test

---

## Fix 5: W10 — `_dead_agents_this_turn` stale on exception

### Problem

agent_bridge.py:1099 overwrites `world._dead_agents_this_turn` during `_process_tick_results()`. If `tick_agents()` raises before reaching that line, the previous turn's dead-agent list persists, and `compute_martyrdom_boosts` fires spurious martyrdom events on the next successful turn.

### Fix

Add `world._dead_agents_this_turn = []` to the turn-start initialization block in `run_turn()` (simulation.py, alongside the existing `world._conquered_this_turn = set()` reset at line 1571).

### Test

Test in `test_simulation.py`: monkeypatch `phase_environment` to assert `getattr(world, '_dead_agents_this_turn', None) == []` on entry, providing a precise "cleared before Phase 1" proof. This verifies the reset happens in the turn-start init block, not merely that the attribute is empty at end-of-turn.

### Files touched

- `src/chronicler/simulation.py` — add `world._dead_agents_this_turn = []` at turn-start init block (~line 1571)
- `tests/test_simulation.py` — turn-start transient clear assertion

---

## Deferred Appendix

Confirmed findings deferred to a separate hygiene pass. These are present in the current tree but do not change simulation behavior in normal operation.

### Semantic / docs

- EMBARGO stability drain uses "signal" instead of "guard-shock" (action_engine.py:477) — both feed `to_shock_signals()`, no behavioral difference
- Governing cost stability drain classified as "signal" instead of "guard-shock" (politics.py:92) — same
- Stale satisfaction test comment says persecution=0.15, actual is 0.09 (satisfaction.rs:739)
- CLAUDE.md Decision 10 missing urban_safety (priority 2) and memory (priority 5) in penalty budget description
- FFI docstrings say `civ_affinity: u16` but actual schema is `UInt8` (ffi/mod.rs:1510, 1584)

### Latent FFI defaults

- `controller_values` update path uses hardcoded `0xFF` default instead of preserving existing value when columns absent (ffi/mod.rs:647) — only fires if columns absent, which never happens
- `resource_suspension` update path resets to false instead of preserving (ffi/mod.rs:686) — same

### Defensive hardening

- PARENT_NONE=0 guard implicit in `_process_promotions` (agent_bridge.py:1517) and `dynasties.py:39` — latent, only fires if Rust emits agent_id=0 which it currently does not
- `accumulator.py:183` `to_shock_signals()` silently drops stats not in `STAT_TO_SHOCK_FIELD` — no current call site triggers, but validation would catch future routing errors
- Settlement transient lists use `hasattr` lazy-init (settlements.py:169) — latent if called outside `run_settlement_tick`
- `_persecuted_regions` lost on bundle load (simulation.py:1048) — latent, affects mid-run bundle resume only

### Test coverage gaps

- Region transient flags (`_controller_changed`, `_war_won`, `_seceded`) lack 2-turn integration tests
- GreatPerson promotion lifecycle tests (cap, cooldown, born_turn)
- `named_characters.rs` has zero tests
- EXPAND vs WAR `conquered_this_turn` distinction not tested
- Gini one-turn lag 2-turn verification
- Economy -> satisfaction -> migration end-to-end chain test
- Shadow mode 5-turn stat trajectory parity test
- `ffi_constants.py` has zero tests
- STREAM_OFFSETS distinctness only checked in source, not integration test
- Arrow batch column count/type contract not tested in Rust integration tests

### Hygiene

- Test mock `_make_civ()` sets `civ.id` on MagicMock (test_accumulator.py:10)
- Python RNG uses magic offsets `seed+1`, `seed+2` not `stable_hash_int` (simulation.py:150, 755)
- `politics_bridge.py:815` uses `Random(seed + turn)` without namespacing
- `live.py:1017` non-deterministic `randint` for live mode with no guard
- Stale viewer fixture contains `pending_shocks`/`agent_events_raw` (sample_bundle.json)
- Four agent-mode-only metadata keys leak mode info (main.py:778-801)
- Mule `3.0x` interaction with weight cap (action_engine.py:1044-1050) — not confirmed at described lines
