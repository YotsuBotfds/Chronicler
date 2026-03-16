# M30: Agent Narrative — Design Spec

> Bridges agent-level simulation with chronicle prose. Agents become named
> characters with personal histories; agent-driven events enrich the narrative
> curation pipeline.

**Status:** Design approved, pending M28 oracle gate.
**Depends on:** M27 (system integration), M28 (oracle gate pass).
**Date:** 2026-03-16

---

## 1. Named Character Promotion

Agent characters are promoted to `GreatPerson` instances with `source="agent"`.
Promotion lives in the Rust `NamedCharacterRegistry` with a Python-side bridge
that creates the `GreatPerson`.

### Two-Gate Promotion

Both gates must pass:

1. **Skill gate** — `promotion_progress >= PROMOTION_DURATION_TURNS` (consecutive
   turns with skill above `PROMOTION_SKILL_THRESHOLD`).
   `[CALIBRATE: post-M28, initial 0.9 / 20]`
2. **Life-event gate** — `life_events != 0`. The agent must have participated in
   at least one qualifying event.

#### New SoA Fields in `AgentPool`

| Field                | Type      | Purpose |
|----------------------|-----------|---------|
| `life_events`        | `Vec<u8>` | Bitflag: bit 0=rebellion, 1=migration, 2=war survival, 3=loyalty flip, 4=occupation switch. Set by event handlers in `behavior.rs`/`demographics.rs`. |
| `promotion_progress` | `Vec<u8>` | Consecutive turns with skill above threshold. Resets on occupation switch or skill drop below threshold. Incremented in `tick.rs` after skill growth. |

Per-agent size: 42 → 44 bytes (still under 48, cache-line friendly).

### Bypass Triggers

Skip the skill gate, still require the life-event gate:

| Trigger               | Condition                  | CharacterRole |
|-----------------------|----------------------------|---------------|
| Rebellion leader       | Led `local_rebellion`      | General (soldier) / Prophet (other) |
| Long displacement      | 50+ turns displaced        | Exile |
| Serial migrant         | 3+ region changes          | Merchant |
| Occupation versatility | 3+ occupation switches     | Scientist |

### Caps

- Per-civ max: 10
- Global max: 50
- Agent-promoted characters take priority over aggregate `GreatPerson` spawns
  when both triggers fire on the same turn.

### Registry

Rust-side `NamedCharacterRegistry` in new module `named_characters.rs`:

```rust
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CharacterRole {
    General = 0,
    Merchant = 1,
    Scientist = 2,
    Prophet = 3,
    Exile = 4,
}

struct NamedCharacter {
    agent_id: u32,
    name: String,
    role: CharacterRole,
    civ_id: u8,
    origin_civ_id: u8,
    born_turn: u16,
    promotion_turn: u16,
    promotion_trigger: u8,
    history: Vec<(u16, u8, u16)>,  // (turn, event_type, region)
}
```

`CharacterRole` maps to `GreatPerson` roles, not agent occupations. The
promotion logic assigns role based on the trigger, not the agent's current
occupation.

Promotion check runs O(n) after demographics in `tick.rs`.

### FFI Handoff

`_sim.get_promotions()` returns a separate `RecordBatch`:

| Column        | Type  | Purpose |
|---------------|-------|---------|
| `agent_id`    | u32   | Agent identifier |
| `role`        | u8    | `CharacterRole` value |
| `trigger`     | u8    | Which promotion trigger fired |
| `skill`       | f32   | Skill at promotion time |
| `life_events` | u8    | Bitflag snapshot |
| `origin_region` | u16 | For `exile_return` tracking in Python |

Called by Python bridge after `tick()`. Bridge creates
`GreatPerson(source="agent", agent_id=...)`.

### Name Generation

Agent-promoted characters reuse the existing `_pick_name(civ, world, rng)` from
`chronicler.leaders`, same as aggregate `GreatPerson` spawns. No new naming
logic needed.

---

## 2. Event Detection & Agent Events

### Existing Events (M27 — consumer-side integration only)

These already emit `Event(source="agent")` via `agent_bridge.py::_aggregate_events()`.
M30 adds curator scoring and narrator integration, no reimplementation.

| Event              | Trigger                      | Importance |
|--------------------|------------------------------|-----------|
| `local_rebellion`  | ≥5 rebels in region          | 7 |
| `mass_migration`   | ≥8 migrations in region      | 5 |
| `loyalty_cascade`  | ≥10 affinity shifts in region | 6 |
| `demographic_crisis` | Region loses >30% pop      | 7 |
| `occupation_shift` | >25% switch in region        | 5 |

### New Events (M30)

| Event              | Trigger | Importance | Detection |
|--------------------|---------|-----------|-----------|
| `notable_migration` | Named character moves regions | 4 | Python bridge, immediate |
| `economic_boom`    | ≥10 `occupation_switch` events *to* merchant in region over 20 turns | 5 | Python bridge, `_event_window` `[CALIBRATE: post-M28, initial 10]` |
| `brain_drain`      | ≥5 scholars leave region (migration where occ == scholar) | 5 | Python bridge, `_event_window` `[CALIBRATE: post-M28]` |
| `exile_return`     | Named char returns to `origin_region` after 30+ turns | 6 | Python bridge, immediate |

**Key decision:** `economic_boom` is event-based (count occupation switches *to*
merchant), not stat-based (merchant population over time). This fits the existing
`_event_window` deque — no new ring buffers needed.

### Where Detection Lives

- `notable_migration` and `exile_return` require named character knowledge →
  detected in Python bridge after promotions are processed.
- `economic_boom` and `brain_drain` are count-based → fit into
  `_aggregate_events()` alongside existing M27 events, using the same
  `_event_window` deque.

**No Rust-side ring buffers.** The spec notes proposed ~10KB of Rust ring
buffers, but all windowed detection uses the existing Python `_event_window`.

### Processing Order

After `tick()` returns to Python:

1. `get_promotions()` → create `GreatPerson` instances, update `named_agents` dict
2. `_convert_events()` → parse raw agent events; cross-reference death events
   against `named_agents` for death transitions
3. Check migration events against named character registry → emit
   `notable_migration`, `exile_return` with `actors` set
4. `_aggregate_events(world, named_agents)` → windowed detection, populates
   `actors` via registry lookup

Promotion before migration detection ensures a character promoted and migrated
on the same tick is correctly detected as `notable_migration`.

---

## 3. Curator Integration

### Scoring

The curator (`curator.py::compute_base_scores`) adds one new bonus:

| Condition | Bonus |
|-----------|-------|
| Agent event references named character in `actors` | +2.0 (max once per event) `[CALIBRATE: post-M28]` |

`NamedEvent` promotion (+3.0) uses the existing mechanism, source-agnostic.

### Saturation Guard

An event receives at most one +2.0 character-reference bonus regardless of how
many named characters are involved. Prevents regions with many named characters
from always dominating curator output.

`[CALIBRATE: post-M28 — reduce to +1.0 or add per-turn character-event budget
if character events dominate]`

### Actor Population

The Python bridge maintains `named_agents: dict[int, str]` (agent_id →
character name), built during promotion processing (step 1 of processing order).

- Events created directly by the bridge (`notable_migration`, `exile_return`)
  set `actors` at creation time.
- `_aggregate_events(world, named_agents)` cross-references involved agent IDs
  against the dict when building summary events.

One dict lookup per raw agent event involved in a summary. Dict is ≤50 entries
(global cap). Negligible cost.

### No Special NamedEvent Handling

Existing `NamedEvent` promotion logic applies to agent events the same way it
applies to aggregate events. The `source="agent"` field is already on the event;
the curator is source-agnostic.

---

## 4. Narration & Character Continuity

### AgentContext

New dataclass added to `models.py`:

```python
@dataclass
class AgentContext:
    named_characters: list[dict]  # see schema below
    population_mood: str          # "desperate", "restless", "content"
    displacement_fraction: float  # 0.0-1.0
```

Added as `agent_context: AgentContext | None = None` on `NarrationContext`.
When `None`, the narrator prompt is unchanged from baseline.

### Named Character Schema (Enriched)

```python
{
    "name": "Kiran",
    "role": "General",
    "civ": "Aram",
    "origin_civ": "Bora",
    "status": "active",          # active / exiled / dead
    "recent_history": [          # last 2-3 events, most recent first
        {"turn": 195, "event": "migration", "region": "Aram"},
        {"turn": 180, "event": "rebellion", "region": "Bora"},
    ]
}
```

History pulled from `GreatPerson.deeds` (maps from Rust registry's
`history Vec`), truncated to 3 most recent entries. At ~20 tokens per character
with history, 10 characters per moment = ~200 tokens.

### Population Mood Precedence

Worst wins:

| Priority | Mood        | Triggers |
|----------|-------------|----------|
| 1 (highest) | `desperate` | `local_rebellion`, `demographic_crisis` |
| 2        | `restless`  | `loyalty_cascade`, `brain_drain`, `occupation_shift` |
| 3 (default) | `content` | No negative agent events |

### Narrator Prompt Addition

When `agent_context` is present:

```
## Agent Context
Population mood: {mood}
Displacement: {fraction}% of population displaced

Named characters present:
- General Kiran (soldier, Aram, originally Bora) [active]:
  Led rebellion in Bora (turn 180); Migrated to Aram (turn 195)
- Scholar Vesh (scholar, Aram) [active]:
  Occupation switch in Aram (turn 210)

Guidelines:
- Refer to named characters BY NAME — do not anonymize or rename them
- Use their recent history for callbacks ("Kiran, who had fled Bora...")
- Use population mood to set atmospheric tone
- If displacement > 10%, weave refugee/exile themes
```

### Character Continuity Rule

Standing narrator instruction:

> "When a named character has appeared in previous chronicle entries, maintain
> their name and identity. Do not re-introduce them or invent backstory that
> contradicts their listed history. The named characters list is authoritative."

Works because `previous_prose` is already part of `NarrationContext`. The named
characters list serves as ground truth when the LLM's context window doesn't
reach back far enough.

### Who Builds AgentContext

The narrative pipeline (`narrative.py`) constructs `AgentContext` when the moment
contains agent-source events:

- Named characters: from `GreatPerson` registry, filtered to characters active
  in the moment's region/civ, enriched with recent history
- Population mood: derived from the moment's agent events using precedence table
- Displacement fraction: computed by `AgentBridge` during step 1 of the
  processing order — count agents with `displacement_turn > 0` divided by total
  alive agents in the region. Stored on `AgentBridge` as
  `displacement_by_region: dict[int, float]` and read by the narrative pipeline.
  No `world.agent_stats` dependency.

---

## 5. GreatPerson Lifecycle Transitions

### FFI Addition

`_sim.set_agent_civ(agent_id: u32, new_civ_id: u8)` — forces `civ_affinity` on
a specific agent in the Rust pool. At most 10 calls per event (per-civ cap).
Added to `ffi.rs`.

### On Conquest

Named characters belonging to the conquered civ:

- **In conquered region:** `fate="exile"`, `captured_by=conqueror.name`. Enter
  existing exile/hostage flow.
  FFI: `set_agent_civ(agent_id, conqueror_civ_id)`.
- **Previously migrated to surviving-civ territory (refugee):**
  `fate="exile"`, `captured_by` NOT set (displaced, not captured). Retain
  current region.
  FFI: `set_agent_civ(agent_id, host_civ_id)`.

### On Secession

Named characters in the seceding region:

- `civilization = new_civ.name`
- `origin_civilization` stays unchanged (preserves identity)
- Emit event: `"{name} defected with the secession of {region}"`
- FFI: `set_agent_civ(agent_id, new_civ_id)`

### On Death

Agent death events (type 0 in `EVENT_TYPE_MAP`) are cross-referenced against
`named_agents` during step 2 (`_convert_events`):

- `GreatPerson`: `alive=False`, `fate="dead"`, `death_turn=world.turn`
- Emit agent event with character name in `actors` (gets +2.0 curator bonus)
- **Death overrides exile:** exiled character dies → `fate="dead"` replaces
  `"exile"`, death narrative references exile status

### Processing Point

All transitions happen in the Python turn loop after `agent_bridge.tick()`:

1. Promotions (processing order step 1)
2. Death transitions (during step 2, `_convert_events`)
3. Conquest/secession transitions (after world state updates for the turn)
4. Event detection (steps 3-4)

---

## 6. Data Model Changes

### Rust — `AgentPool` (pool.rs)

| Field                | Type      | Purpose |
|----------------------|-----------|---------|
| `life_events`        | `Vec<u8>` | Bitflag for qualifying events |
| `promotion_progress` | `Vec<u8>` | Consecutive turns above skill threshold |

### Rust — `NamedCharacterRegistry` (new module)

`CharacterRole` enum (u8): General, Merchant, Scientist, Prophet, Exile.

`NamedCharacter` struct: agent_id, name, role, civ_id, origin_civ_id,
born_turn, promotion_turn, promotion_trigger, history Vec.

### Rust — FFI (ffi.rs)

| Method            | Signature                         | Purpose |
|-------------------|-----------------------------------|---------|
| `get_promotions()` | `→ RecordBatch`                  | Promotion candidates with schema: agent_id, role, trigger, skill, life_events, origin_region |
| `set_agent_civ()`  | `(agent_id: u32, new_civ_id: u8)` | Force civ_affinity sync |

### Python — `GreatPerson` (models.py)

| Field      | Type           | Default       |
|------------|----------------|---------------|
| `source`   | `str`          | `"aggregate"` |
| `agent_id` | `int \| None`  | `None`        |

New `fate` value: `"exile"`. The existing vocabulary is `"active"`, `"retired"`,
`"dead"`, `"ascended"`, `"ascended_to_leadership"`. M30 adds `"exile"` for
conquest transitions. Death overrides exile (`fate="dead"` replaces `"exile"`).

### Python — `NarrationContext` (models.py)

| Field           | Type                  | Default |
|-----------------|-----------------------|---------|
| `agent_context` | `AgentContext \| None` | `None`  |

### Python — `AgentContext` (new dataclass, models.py)

Fields: `named_characters` (list[dict]), `population_mood` (str),
`displacement_fraction` (float).

### Python — `AgentBridge` (agent_bridge.py)

| Change | Detail |
|--------|--------|
| `named_agents: dict[int, str]` | New instance field |
| `displacement_by_region: dict[int, float]` | Displacement fractions, computed during processing |
| `_aggregate_events()` signature | Adds `named_agents` parameter |
| Processing order | 4-step sequence per Section 2 |

### No Changes to `Event`

`source` and `actors` fields already exist. Agent events populate them.

---

## 7. Testing

### Rust Unit Tests (7)

| Test | Verifies |
|------|----------|
| `test_life_events_bitflag` | Each event type sets correct bit, bits accumulate |
| `test_promotion_progress_increments` | Increments when skill > threshold, resets on occ switch / skill drop |
| `test_promotion_two_gates` | Fires only when both gates pass |
| `test_bypass_triggers` | Each bypass trigger promotes with correct `CharacterRole` |
| `test_promotion_caps` | Per-civ (10) and global (50) caps respected, agent-promoted prioritized |
| `test_set_agent_civ` | Correctly updates `civ_affinity` in pool |
| `test_character_role_mapping` | `CharacterRole` values round-trip through FFI |

### Python Integration Tests (13)

| Test | Verifies |
|------|----------|
| `test_promotion_creates_great_person` | RecordBatch → `GreatPerson(source="agent")` |
| `test_named_agents_dict_maintained` | Dict updated on promotion, used in `_aggregate_events` |
| `test_actor_population` | Named character names in `actors` field |
| `test_notable_migration_detection` | Named character migration → event |
| `test_exile_return_detection` | Return to origin after 30+ turns → event |
| `test_economic_boom_detection` | Sufficient merchant switches → event |
| `test_brain_drain_detection` | ≥5 scholar departures → event |
| `test_death_transitions_great_person` | Death → `alive=False, fate="dead"` |
| `test_death_overrides_exile_fate` | Exiled character dies → `fate="dead"` overrides `"exile"` |
| `test_conquest_exile_transition` | Conquest → exile, `set_agent_civ` called |
| `test_conquest_refugee_not_captured` | Refugee → `captured_by` NOT set |
| `test_secession_transfer` | `civilization` updated, `origin_civilization` preserved |
| `test_processing_order` | Same-tick promote+migrate correctly detected |

### Curator Tests (3)

| Test | Verifies |
|------|----------|
| `test_character_reference_bonus` | +2.0 when named character in `actors` |
| `test_saturation_guard` | Multiple characters → still only +2.0 |
| `test_source_agnostic_named_event` | Agent events eligible for NamedEvent promotion |

### Narrator Tests (3)

| Test | Verifies |
|------|----------|
| `test_agent_context_in_prompt` | `AgentContext` → prompt includes characters with history |
| `test_no_agent_context` | `None` → prompt unchanged |
| `test_mood_precedence` | Rebellion + boom → "desperate" wins |

LLM narrative quality validated manually during M30 implementation, not via
automated tests.

---

## 8. Calibration Summary

All thresholds marked for post-M28 calibration. M28's 200-seed batch produces
real agent behavior data — the natural calibration point.

| Parameter | Initial Value | Calibration Question |
|-----------|--------------|---------------------|
| `PROMOTION_SKILL_THRESHOLD` | 0.9 | Does this produce 1-3 promotions per civ per game, or hundreds? |
| `PROMOTION_DURATION_TURNS` | 20 | Combined with growth rate 0.05/turn, how selective is this? |
| Character-reference bonus | +2.0 | Do character events dominate the curator, or blend naturally? |
| `economic_boom` merchant-switch count | 10 | What does the distribution of merchant switches look like? |
| `brain_drain` scholar departure count | 5 | Is 5 scholars leaving a region a rare event or commonplace? |
