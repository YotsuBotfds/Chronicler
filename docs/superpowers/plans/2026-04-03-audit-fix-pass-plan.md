# Audit Fix Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 confirmed blockers (B1, B3, B6) and 2 confirmed behavioral warnings (W17, W10) from the 2026-04-03 cross-cutting audit.

**Architecture:** Five independent fixes, each with a code change and a regression test. No fix depends on another. Python fixes (B1, B3, W17, W10) modify `src/chronicler/` and `tests/`. Rust fix (B6) modifies `chronicler-agents/src/` and `chronicler-agents/tests/`.

**Tech Stack:** Python 3.14 + Pydantic, Rust + PyO3/ChaCha8Rng, pytest, cargo nextest

**Spec:** `docs/superpowers/specs/2026-04-03-audit-fix-pass-design.md`

---

### Task 1: B1 — Fix holy-war clergy bonus (conquest_conversion_active consumed before factions)

**Files:**
- Modify: `src/chronicler/religion.py:299-301` — remove the clear
- Modify: `src/chronicler/religion.py:241` — update docstring
- Test: `tests/test_factions.py` — add phase-order regression

- [ ] **Step 1: Write the failing test**

Add to `tests/test_factions.py`:

```python
from chronicler.factions import tick_factions, EVT_HOLY_WAR_WON
from chronicler.religion import compute_conversion_signals


class TestHolyWarClergyBoost:
    """B1: conquest_conversion_active must survive compute_conversion_signals
    so tick_factions can read it for the EVT_HOLY_WAR_WON clergy boost."""

    def test_clergy_boost_fires_after_conversion_signals(self, make_world):
        world = make_world(num_civs=2)
        civ0 = world.civilizations[0]

        # Set up a war-win event on the current turn
        world.events_timeline.append(Event(
            turn=world.turn,
            event_type="war",
            actors=[civ0.name, world.civilizations[1].name],
            description=f"{civ0.name} vs {world.civilizations[1].name}: attacker_wins",
            importance=8,
        ))

        # Set conquest_conversion_active on a region civ0 controls
        region_map = {r.name: r for r in world.regions}
        target_region = region_map[civ0.regions[0]]
        target_region.conquest_conversion_active = True

        # Record clergy influence before
        clergy_before = civ0.factions.influence[FactionType.CLERGY]

        # Phase 10 order: compute_conversion_signals THEN tick_factions
        compute_conversion_signals(
            world.regions,
            {},  # majority_beliefs — empty is fine for this test
            world.belief_registry if world.belief_registry else [],
            None,  # snapshot — None skips priest counting
        )
        tick_factions(world)

        # The clergy boost should have fired despite conversion_signals running first
        assert civ0.factions.influence[FactionType.CLERGY] == pytest.approx(
            clergy_before + EVT_HOLY_WAR_WON
        ), "EVT_HOLY_WAR_WON clergy boost did not fire after compute_conversion_signals"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_factions.py::TestHolyWarClergyBoost::test_clergy_boost_fires_after_conversion_signals -v`
Expected: FAIL — `compute_conversion_signals` clears the flag at religion.py:301 before `tick_factions` reads it, so clergy influence does not increase.

- [ ] **Step 3: Remove the flag clear from religion.py**

In `src/chronicler/religion.py`, remove line 301 (`region.conquest_conversion_active = False`). The block at lines 298-301 becomes:

```python
    for region_idx, region in enumerate(regions):
        # One-shot conquest flag — read (cleared at turn start by simulation.py)
        conquest_active = region.conquest_conversion_active

        majority_faith = majority_beliefs.get(region_idx, 0xFF)
```

- [ ] **Step 4: Update the stale docstring**

In `src/chronicler/religion.py`, update the docstring at line 241 from:

```python
    - Reads and clears the one-shot ``conquest_conversion_active`` flag.
```

to:

```python
    - Reads the one-shot ``conquest_conversion_active`` flag (cleared at turn
      start by ``run_turn()`` in simulation.py, not here).
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_factions.py::TestHolyWarClergyBoost -v`
Expected: PASS

- [ ] **Step 6: Run broader faction + religion tests**

Run: `python -m pytest tests/test_factions.py tests/test_religion.py -v`
Expected: all pass, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/religion.py tests/test_factions.py
git commit -m "fix(B1): holy-war clergy bonus survives compute_conversion_signals

conquest_conversion_active is no longer cleared inside
compute_conversion_signals — the turn-start clear in run_turn()
owns the lifecycle. tick_factions now sees the flag and fires
EVT_HOLY_WAR_WON correctly in agent-backed modes."
```

---

### Task 2: B3 — Apply severity multiplier to asabiya collapse

**Files:**
- Modify: `src/chronicler/simulation.py:1189-1196` — add severity scaling
- Test: `tests/test_severity.py` — add collapse regression

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_severity.py`:

```python
class TestSeverityAtCollapsesite:
    """B3: asabiya collapse must apply get_severity_multiplier to military/economy halving."""

    def test_collapse_uses_severity_at_mult_1(self, make_world):
        """At mult=1.0 (zero stress), collapsed stats match current military // 2."""
        world = make_world(num_civs=2)
        civ = world.civilizations[0]
        # Ensure zero stress → mult=1.0
        civ.civ_stress = 0
        civ.military = 61  # odd value to test floor-half target
        civ.economy = 60   # even value
        civ.asabiya = 0.05
        civ.stability = 15
        # Need >1 region for collapse to trigger
        extra = Region(name="extra_r", terrain="plains",
                       carrying_capacity=60, resources="fertile",
                       controller=civ.name)
        world.regions.append(extra)
        civ.regions.append("extra_r")

        from chronicler.simulation import phase_consequences
        phase_consequences(world, acc=None)

        # At mult=1.0, result should match current // 2 targets
        assert civ.military == clamp(61 // 2, STAT_FLOOR["military"], 100)
        assert civ.economy == clamp(60 // 2, STAT_FLOOR["economy"], 100)

    def test_collapse_severity_amplifies_loss(self, stressed_world):
        """At mult>1.0 (high stress), collapsed stats are lower than // 2 baseline."""
        world = stressed_world
        civ = world.civilizations[0]
        civ.military = 60
        civ.economy = 60
        civ.asabiya = 0.05
        civ.stability = 15
        # stressed_world already has >1 region and high civ_stress

        baseline_target = clamp(60 // 2, STAT_FLOOR["military"], 100)  # 30

        from chronicler.simulation import phase_consequences
        phase_consequences(world, acc=None)

        # With mult > 1.0, the collapsed stat should be LOWER than baseline
        assert civ.military < baseline_target, (
            f"Collapse with severity mult>1.0 should produce military below {baseline_target}, "
            f"got {civ.military}"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_severity.py::TestSeverityAtCollapsesite -v`
Expected: `test_collapse_severity_amplifies_loss` FAILS — current code does not apply severity, so military == 30 which is not < 30.

- [ ] **Step 3: Apply severity multiplier to collapse path**

In `src/chronicler/simulation.py`, replace lines 1189-1196:

```python
                collapsed_military = clamp(civ.military // 2, STAT_FLOOR["military"], 100)
                collapsed_economy = clamp(civ.economy // 2, STAT_FLOOR["economy"], 100)
                if acc is not None:
                    acc.add(civ_idx, civ, "military", collapsed_military - civ.military, "guard-shock")
                    acc.add(civ_idx, civ, "economy", collapsed_economy - civ.economy, "guard-shock")
                else:
                    civ.military = collapsed_military
                    civ.economy = collapsed_economy
```

with:

```python
                mult = get_severity_multiplier(civ, world)
                base_mil_target = clamp(civ.military // 2, STAT_FLOOR["military"], 100)
                base_eco_target = clamp(civ.economy // 2, STAT_FLOOR["economy"], 100)
                mil_loss = int((civ.military - base_mil_target) * mult)
                eco_loss = int((civ.economy - base_eco_target) * mult)
                collapsed_military = clamp(civ.military - mil_loss, STAT_FLOOR["military"], 100)
                collapsed_economy = clamp(civ.economy - eco_loss, STAT_FLOOR["economy"], 100)
                if acc is not None:
                    acc.add(civ_idx, civ, "military", collapsed_military - civ.military, "guard-shock")
                    acc.add(civ_idx, civ, "economy", collapsed_economy - civ.economy, "guard-shock")
                else:
                    civ.military = collapsed_military
                    civ.economy = collapsed_economy
```

Ensure `get_severity_multiplier` is imported at the top of `simulation.py`. Check existing imports — it is already imported from `chronicler.emergence` (search for `get_severity_multiplier` in the file's import block).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_severity.py::TestSeverityAtCollapsesite -v`
Expected: PASS

- [ ] **Step 5: Run broader simulation + severity tests**

Run: `python -m pytest tests/test_severity.py tests/test_simulation.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_severity.py
git commit -m "fix(B3): apply severity multiplier to asabiya collapse

Collapse military/economy halving now scales by
get_severity_multiplier(). At mult=1.0 (zero stress), behavior
is identical to the prior // 2 baseline. At mult>1.0 (high
world stress), the collapse hits harder."
```

---

### Task 3: B6 — Fix spatial RNG stream collisions (Rust)

**Files:**
- Modify: `chronicler-agents/src/spatial.rs:691-697, 723-728` — add helpers, update both functions
- Modify: `chronicler-agents/src/agent.rs:112-114` — register new offset
- Modify: `chronicler-agents/src/agent.rs:454-482` — add offset to uniqueness test
- Test: `chronicler-agents/tests/test_spatial_streams.rs` — new test file

- [ ] **Step 1: Register NEWBORN_POSITION_STREAM_OFFSET in agent.rs**

In `chronicler-agents/src/agent.rs`, after line 114 (`pub const SPATIAL_POSITION_STREAM_OFFSET: u64 = 2000;`), add:

```rust
// M55a audit fix: separate stream for newborn placement vs migration placement
pub const NEWBORN_POSITION_STREAM_OFFSET: u64 = 2100;
```

- [ ] **Step 2: Add NEWBORN_POSITION_STREAM_OFFSET to the uniqueness test**

In `chronicler-agents/src/agent.rs`, in the `test_stream_offsets_no_collision` test (line 454), add `NEWBORN_POSITION_STREAM_OFFSET` to the `offsets` array:

```rust
    #[test]
    fn test_stream_offsets_no_collision() {
        let offsets = [
            DECISION_STREAM_OFFSET,
            DEMOGRAPHICS_STREAM_OFFSET,
            MIGRATION_STREAM_OFFSET,
            CULTURE_DRIFT_STREAM_OFFSET,
            CONVERSION_STREAM_OFFSET,
            PERSONALITY_STREAM_OFFSET,
            GOODS_ALLOC_STREAM_OFFSET,
            MEMORY_STREAM_OFFSET,
            SCHISM_CONVERSION_STREAM_OFFSET, // 1000
            MULE_STREAM_OFFSET,
            RELATIONSHIP_STREAM_OFFSET,
            INITIAL_AGE_STREAM_OFFSET,       // 1400
            SPATIAL_POSITION_STREAM_OFFSET,  // 2000
            NEWBORN_POSITION_STREAM_OFFSET,  // 2100
            MARRIAGE_STREAM_OFFSET,          // 1600
            MERCHANT_ROUTE_STREAM_OFFSET,    // 1700
            KNOWLEDGE_STREAM_OFFSET,         // 1800
        ];
        // All offsets must be distinct
        for i in 0..offsets.len() {
            for j in (i + 1)..offsets.len() {
                assert_ne!(
                    offsets[i], offsets[j],
                    "Stream offset collision: index {} and {} both equal {}",
                    i, j, offsets[i]
                );
            }
        }
    }
```

- [ ] **Step 3: Add spatial_seed and spatial_stream helpers to spatial.rs**

In `chronicler-agents/src/spatial.rs`, add these helpers after the existing imports (after line 5):

```rust
use crate::agent::{SPATIAL_POSITION_STREAM_OFFSET, NEWBORN_POSITION_STREAM_OFFSET};
use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// Derive a per-agent spatial seed from the master seed and agent id.
/// XORs agent_id bytes into the first 4 bytes of a copy of master_seed,
/// producing a distinct seed per agent while preserving the remaining
/// 28 bytes of entropy.
#[inline]
pub(crate) fn spatial_seed(master_seed: &[u8; 32], agent_id: u32) -> [u8; 32] {
    let mut seed = *master_seed;
    let id_bytes = agent_id.to_le_bytes();
    seed[0] ^= id_bytes[0];
    seed[1] ^= id_bytes[1];
    seed[2] ^= id_bytes[2];
    seed[3] ^= id_bytes[3];
    seed
}

/// Standard packed stream ID for spatial RNG, matching conversion_stream/culture_stream.
#[inline]
pub(crate) fn spatial_stream(region_id: u16, turn: u32, offset: u64) -> u64 {
    debug_assert!(offset <= u16::MAX as u64, "stream offset exceeds packed RNG stream range");
    ((region_id as u64) << 48) | ((turn as u64) << 16) | offset
}
```

Note: check the existing imports in spatial.rs. It already imports `use rand::Rng;`, `use rand::SeedableRng;`, and `use rand_chacha::ChaCha8Rng;` (they must be present since the functions already use these types). If any of these imports already exist, do not duplicate them. Only add the missing ones.

- [ ] **Step 4: Update migration_reset_position to use helpers**

In `chronicler-agents/src/spatial.rs`, replace lines 691-697:

```rust
    let mut rng = ChaCha8Rng::from_seed(*master_seed);
    rng.set_stream(
        agent_id as u64 * 1000
            + dest_region_id as u64 * 100
            + turn as u64
            + SPATIAL_POSITION_STREAM_OFFSET,
    );
```

with:

```rust
    let seed = spatial_seed(master_seed, agent_id);
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(spatial_stream(dest_region_id, turn, SPATIAL_POSITION_STREAM_OFFSET));
```

- [ ] **Step 5: Update newborn_position to use helpers with new offset**

In `chronicler-agents/src/spatial.rs`, replace lines 723-728:

```rust
    let mut rng = ChaCha8Rng::from_seed(*master_seed);
    rng.set_stream(
        child_id as u64 * 1000
            + region_id as u64 * 100
            + turn as u64
            + SPATIAL_POSITION_STREAM_OFFSET,
    );
```

with:

```rust
    let seed = spatial_seed(master_seed, child_id);
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(spatial_stream(region_id, turn, NEWBORN_POSITION_STREAM_OFFSET));
```

- [ ] **Step 6: Verify Rust compiles**

Run: `cargo check --manifest-path chronicler-agents/Cargo.toml`
Expected: compiles without errors.

- [ ] **Step 7: Write the stream collision regression test**

Create `chronicler-agents/tests/test_spatial_streams.rs`:

```rust
//! B6 regression: spatial RNG streams must not collide across agents or
//! between migration and newborn placement.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

// Re-derive the helpers here since they are pub(crate) in spatial.rs.
// This tests the algorithm independently of the production code.

fn spatial_seed(master_seed: &[u8; 32], agent_id: u32) -> [u8; 32] {
    let mut seed = *master_seed;
    let id_bytes = agent_id.to_le_bytes();
    seed[0] ^= id_bytes[0];
    seed[1] ^= id_bytes[1];
    seed[2] ^= id_bytes[2];
    seed[3] ^= id_bytes[3];
    seed
}

fn spatial_stream(region_id: u16, turn: u32, offset: u64) -> u64 {
    ((region_id as u64) << 48) | ((turn as u64) << 16) | offset
}

fn jitter_pair(seed: [u8; 32], stream: u64) -> (f32, f32) {
    let mut rng = ChaCha8Rng::from_seed(seed);
    rng.set_stream(stream);
    (rng.gen::<f32>(), rng.gen::<f32>())
}

#[test]
fn test_formerly_colliding_triples_produce_distinct_jitter() {
    // Under old arithmetic: agent_id=1, region_id=10, turn=0 would collide
    // with agent_id=2, region_id=0, turn=0 (both sum to 2000 + offset).
    let master = [42u8; 32];
    let offset = 2000u64;

    let seed_a = spatial_seed(&master, 1);
    let seed_b = spatial_seed(&master, 2);
    // Seeds must differ (different agent_id XOR)
    assert_ne!(seed_a, seed_b, "spatial_seed must produce distinct seeds for distinct agent_ids");

    let stream_a = spatial_stream(10, 0, offset);
    let stream_b = spatial_stream(0, 0, offset);

    let jitter_a = jitter_pair(seed_a, stream_a);
    let jitter_b = jitter_pair(seed_b, stream_b);
    assert_ne!(jitter_a, jitter_b, "Formerly colliding triples must produce distinct jitter");
}

#[test]
fn test_migration_and_newborn_produce_distinct_jitter() {
    // Same agent_id, same region, same turn — different offsets.
    let master = [42u8; 32];
    let agent_id = 100u32;
    let region_id = 5u16;
    let turn = 10u32;

    let seed = spatial_seed(&master, agent_id);
    let migration_stream = spatial_stream(region_id, turn, 2000); // SPATIAL_POSITION_STREAM_OFFSET
    let newborn_stream = spatial_stream(region_id, turn, 2100);   // NEWBORN_POSITION_STREAM_OFFSET

    assert_ne!(migration_stream, newborn_stream, "Migration and newborn streams must differ");

    let jitter_m = jitter_pair(seed, migration_stream);
    let jitter_n = jitter_pair(seed, newborn_stream);
    assert_ne!(jitter_m, jitter_n, "Migration and newborn jitter must differ");
}

#[test]
fn test_same_inputs_produce_identical_jitter() {
    // Determinism: identical inputs → identical outputs.
    let master = [42u8; 32];
    let agent_id = 7u32;
    let region_id = 3u16;
    let turn = 5u32;
    let offset = 2000u64;

    let seed = spatial_seed(&master, agent_id);
    let stream = spatial_stream(region_id, turn, offset);

    let jitter_1 = jitter_pair(seed, stream);
    let jitter_2 = jitter_pair(seed, stream);
    assert_eq!(jitter_1, jitter_2, "Same inputs must produce identical jitter");
}
```

- [ ] **Step 8: Run tests**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml -E "test(spatial_stream) | test(stream_offsets)"`
Expected: all pass (3 new spatial stream tests + existing offset uniqueness test with the new entry).

- [ ] **Step 9: Run full Rust test suite**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
Expected: all pass. Some existing determinism tests may produce different outputs since the RNG streams changed — if any `determinism.rs` tests fail with changed values, that is expected (the old values were produced by colliding streams). Update the expected values in those tests.

- [ ] **Step 10: Rebuild Python extension and run Python bridge tests**

Run:
```bash
cd chronicler-agents && ..\.venv\Scripts\python.exe -m maturin develop --release && cd ..
.\.venv\Scripts\python.exe -m pytest tests/test_agent_bridge.py -q
```
Expected: all pass. The spatial change affects agent positions but not the bridge contract.

- [ ] **Step 11: Commit**

```bash
git add chronicler-agents/src/spatial.rs chronicler-agents/src/agent.rs chronicler-agents/tests/test_spatial_streams.rs
git commit -m "fix(B6): spatial RNG uses bit-packed streams + per-agent seed

migration_reset_position and newborn_position now use
spatial_seed() (agent_id XOR into master seed) + spatial_stream()
(packed region/turn/offset). Registers NEWBORN_POSITION_STREAM_OFFSET
= 2100 to disambiguate migration from birth placement. Eliminates
arithmetic stream collisions at high agent counts."
```

---

### Task 4: W17 — Cap grudge WAR weight accumulation

**Files:**
- Modify: `src/chronicler/tuning.py` — register K_GRUDGE_CAP
- Modify: `src/chronicler/action_engine.py:962-971` — replace grudge loop with capped helper
- Test: `tests/test_action_engine.py` — grudge cap ratio test

- [ ] **Step 1: Register K_GRUDGE_CAP in tuning.py**

In `src/chronicler/tuning.py`, add after the existing action weight keys (near line 213, after `K_RIVAL_WAR_BOOST`):

```python
K_GRUDGE_CAP = "action.grudge_war_cap"
```

Also add `K_GRUDGE_CAP` to the `_ALL_KEYS` tuple (search for `K_RIVAL_WAR_BOOST` in `_ALL_KEYS` and add `K_GRUDGE_CAP` adjacent to it).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_action_engine.py`:

```python
from chronicler.tuning import K_GRUDGE_CAP


class TestGrudgeCap:
    """W17: grudge WAR weight accumulation must be capped."""

    def test_three_grudges_capped_at_2x(self, make_world):
        world = make_world(num_civs=4)
        civ = world.civilizations[0]
        civ.military = 50
        civ.economy = 50
        civ.stability = 50
        civ.leader = Leader(name="TestLeader", trait="balanced")
        # Clear rival so rival_boost doesn't interfere
        civ.leader.rival_civ = None
        # No traditions, no tech focus — isolate grudges
        civ.traditions = []
        # Ensure WAR is eligible (need a hostile neighbor)
        other = world.civilizations[1]
        world.relationships[civ.name] = {}
        for i, target_civ in enumerate(world.civilizations[1:], 1):
            world.relationships[civ.name][target_civ.name] = Relationship(
                disposition=Disposition.HOSTILE)

        # Three max-intensity grudges against hostile neighbors
        civ.leader.grudges = [
            {"rival_civ": world.civilizations[1].name, "intensity": 1.0},
            {"rival_civ": world.civilizations[2].name, "intensity": 1.0},
            {"rival_civ": world.civilizations[3].name, "intensity": 1.0},
        ]

        from chronicler.action_engine import ActionEngine
        engine = ActionEngine(world)
        weights = engine.compute_weights(civ)

        base_weight = 0.2  # ACTION_WEIGHT_BASE
        grudge_cap = 2.0   # K_GRUDGE_CAP default

        # Without the cap, 3 grudges at intensity=1.0 would give 1.5^3 = 3.375x
        # With the cap at 2.0, WAR weight from grudges alone <= base * 2.0
        # (other modifiers may still apply after grudges, but grudge contribution is capped)
        # The test checks that WAR doesn't reach the uncapped value
        uncapped_war = base_weight * 3.375  # 0.675

        assert weights[ActionType.WAR] < uncapped_war, (
            f"WAR weight {weights[ActionType.WAR]:.4f} should be below uncapped "
            f"{uncapped_war:.4f} — grudge cap not applied"
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_action_engine.py::TestGrudgeCap -v`
Expected: FAIL — current code applies 3.375x uncapped.

- [ ] **Step 4: Add _grudge_war_multiplier helper and replace the grudge loop**

In `src/chronicler/action_engine.py`, add the helper function before `compute_weights` (near line 920):

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

Then replace the grudge loop in `compute_weights` (lines 962-971). The current code:

```python
        # Grudge bias: each high-intensity grudge boosts WAR weight toward the rival civ
        if civ.leader.grudges and weights[ActionType.WAR] > 0:
            for grudge in civ.leader.grudges:
                intensity = grudge.get("intensity", 0.0)
                if intensity >= 0.5:
                    # Check whether the grudge target is still a hostile neighbor
                    rival_civ = grudge.get("rival_civ")
                    if rival_civ and civ.name in self.world.relationships:
                        rel = self.world.relationships[civ.name].get(rival_civ)
                        if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                            weights[ActionType.WAR] *= (1.0 + intensity * 0.5)
```

becomes:

```python
        # Grudge bias: accumulated grudge boost on WAR, capped at K_GRUDGE_CAP
        if civ.leader.grudges and weights[ActionType.WAR] > 0:
            # Filter to grudges targeting hostile/suspicious neighbors
            active_grudges = []
            for grudge in civ.leader.grudges:
                rival_civ = grudge.get("rival_civ")
                if rival_civ and civ.name in self.world.relationships:
                    rel = self.world.relationships[civ.name].get(rival_civ)
                    if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                        active_grudges.append(grudge)
            grudge_cap = get_override(self.world, K_GRUDGE_CAP, 2.0)
            weights[ActionType.WAR] *= _grudge_war_multiplier(active_grudges, grudge_cap)
```

Add `K_GRUDGE_CAP` to the import from `chronicler.tuning` at the top of the file.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_action_engine.py::TestGrudgeCap -v`
Expected: PASS

- [ ] **Step 6: Run broader action engine tests**

Run: `python -m pytest tests/test_action_engine.py tests/test_weight_cap.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/tuning.py tests/test_action_engine.py
git commit -m "fix(W17): cap grudge WAR weight accumulation at K_GRUDGE_CAP

Grudge multiplier product is now capped at 2.0x (tunable via
K_GRUDGE_CAP). Previously 3 max-intensity grudges produced 3.375x,
saturating the weight cap and making other modifiers ineffective."
```

---

### Task 5: W10 — Clear _dead_agents_this_turn at turn start

**Files:**
- Modify: `src/chronicler/simulation.py:~1571` — add turn-start clear
- Test: `tests/test_simulation.py` — monkeypatch assertion

- [ ] **Step 1: Write the failing test**

Add to `tests/test_simulation.py`:

```python
class TestDeadAgentsTransientClear:
    """W10: _dead_agents_this_turn must be [] before Phase 1 begins."""

    def test_dead_agents_cleared_before_phase_1(self, make_world, monkeypatch):
        world = make_world(num_civs=2)
        # Plant stale data to simulate a prior turn's leftover
        world._dead_agents_this_turn = [{"agent_id": 999, "event_type": "death"}]

        captured = {}

        original_phase_env = phase_environment

        def checking_phase_env(w, **kwargs):
            captured["dead_agents"] = getattr(w, '_dead_agents_this_turn', None)
            return original_phase_env(w, **kwargs)

        monkeypatch.setattr(
            "chronicler.simulation.phase_environment", checking_phase_env
        )
        run_turn(world, seed=42)

        assert captured["dead_agents"] == [], (
            f"_dead_agents_this_turn should be [] before Phase 1, "
            f"got {captured['dead_agents']}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_simulation.py::TestDeadAgentsTransientClear -v`
Expected: FAIL — the stale list persists into Phase 1.

- [ ] **Step 3: Add the turn-start clear**

In `src/chronicler/simulation.py`, after the existing turn-start clear at line 1571 (`world._conquered_this_turn = set()`), add:

```python
    # W10 fix: Clear dead-agents transient so a failed tick_agents on the
    # prior turn does not cause spurious martyrdom boosts.
    world._dead_agents_this_turn = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_simulation.py::TestDeadAgentsTransientClear -v`
Expected: PASS

- [ ] **Step 5: Run broader simulation tests**

Run: `python -m pytest tests/test_simulation.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "fix(W10): clear _dead_agents_this_turn at turn start

Prevents stale martyrdom boosts if tick_agents raises before
overwriting the list. Cleared alongside _conquered_this_turn
in run_turn's turn-start init block."
```

---

### Task 6: Final validation

- [ ] **Step 1: Run full Python test suite**

Run: `python -m pytest -q`
Expected: all pass (2541+ passed, 4 skipped).

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
Expected: all pass (809+ passed, 2 skipped).

- [ ] **Step 3: Push all commits**

Run: `git push`

