# M30: Agent Narrative — Spec Notes

**Date:** 2026-03-16
**Status:** Pre-spec research (Phoebe design review + codebase audit)
**Purpose:** Resolve the open design questions in the M30 roadmap section before spec writing. Covers named character system architecture, narrator integration, curator scoring, and conquest/secession edge cases.

---

## Decision 1: Merge Agent Characters into GreatPerson

**Question:** Should M30's agent-promoted named characters be a new `NamedCharacter` type or use the existing `GreatPerson` model?

**Decision: Merge.** Agent-promoted characters become `GreatPerson` instances with a new `source` field.

### Rationale

The existing `GreatPerson` model already provides:
- Full lifecycle (active → retired → dead) with deterministic lifespan
- Character relationships (rivalries, mentorships, marriages)
- Role-based modifiers (general, merchant, scientist, prophet)
- Narrator integration via `TurnSnapshot.great_persons`
- Curator scoring (folk hero events get +3.0 named event bonus)
- Serialization into chronicle bundles
- Exile/hostage handling for conquest scenarios

A parallel `NamedCharacter` registry would duplicate all of the above (~400 lines) for a system that does the same thing — tracking named individuals with histories.

### Schema Addition

```python
class GreatPerson(BaseModel):
    # ... existing fields ...
    source: str = "aggregate"  # "aggregate" (threshold-based) or "agent" (promotion-based)
    agent_id: int | None = None  # Rust pool slot ID if source="agent"
```

### Role Mapping for Agent-Promoted Characters

| Agent Promotion Trigger | GreatPerson Role | Notes |
|------------------------|------------------|-------|
| High skill (>0.9 for 20+ turns) | Matches agent occupation | Farmer→prophet (wisdom), Soldier→general, Merchant→merchant, Scholar→scientist |
| Rebellion leader | General (if soldier) or Prophet (otherwise) | Political significance maps to military or cultural domain |
| Long displacement (50+ turns) | Exile role (existing) | Already supported by GreatPerson model |
| Serial migrant (3+ moves) | Merchant | Wanderer archetype → trade/exploration domain |
| Occupation versatility (3+ switches) | Scientist | Polymath → knowledge domain |
| Loyalty flipper | General or Prophet | Defector → military/cultural depending on context |

### Cap Interaction

The roadmap's per-civ cap (max 10) and global cap (max 50) apply across both sources. An aggregate-spawned general and an agent-promoted general both count toward the same limits. This prevents character inflation — the simulation doesn't produce 50 aggregate great persons AND 50 agent characters.

**Priority when cap is reached:** Agent-promoted characters take priority over threshold-based spawns when both triggers fire in the same turn. Rationale: agent characters have richer personal histories (tracked migrations, occupation switches, loyalty flips) that produce better narrative material.

---

## Decision 2: Conquest and Secession Character Transfer

### Conquest

When a civ is conquered, its GreatPerson instances (both sources) follow the existing exile/hostage flow:

1. Active great persons become exiles: `fate = "exile"`, `captured_by = conqueror.name`
2. Some may become hostages: `is_hostage = True`, `hostage_turns` starts ticking
3. `check_exile_restoration` handles return scenarios if the civ is later restored

Agent-promoted characters in a conquered civ follow the same path. The agent's pool slot may be killed (if the agent dies in conquest) or reassigned to the conqueror's civ_affinity (if the agent survives with a loyalty flip). The GreatPerson record persists regardless — death updates `fate = "dead"`, `death_turn = current_turn`.

### Secession

When a civ fragments via `check_secession`:

1. The seceding entity gets some regions and the agents in those regions
2. Agent-promoted characters in seceding regions transfer to the new civ: `civilization = new_civ.name` (but `origin_civilization` stays the same)
3. Aggregate-spawned great persons in the parent civ stay with the parent (they're not region-bound)
4. If a seceding region contains an agent-promoted character, that character's narrative becomes "defected with the secession" — rich material

### Edge Case: Character in Contested Region

If a named character's agent is in a region that changes controller mid-war, the character's `civilization` updates to match the agent's `civ_affinity`, not the region's controller. An agent who was loyal to Civ A but is now in a Civ B-controlled region keeps their Civ A affiliation until loyalty drift flips them. The GreatPerson record tracks the agent's affiliation, not the region's politics.

---

## Decision 3: Curator Integration

### Current Curator Scoring

The curator scores events for narration inclusion using:
- Base importance (0–10 from event definition)
- Named event bonus (+3.0 for `NamedEvent` instances)
- First occurrence bonus
- Narrative clustering (events near other high-importance events get boosted)

### M30 Additions

**Agent events referencing named characters should get the named event bonus.** Currently, only `NamedEvent` objects get +3.0. Agent events are regular `Event` objects. Two options:

**Option A: Promote to NamedEvent.** When an agent event references a named character (e.g., `notable_migration` where the migrant is a GreatPerson), create a `NamedEvent` instead of `Event`. This automatically gets the +3.0 bonus.

**Option B: Add character-reference scoring.** Add a secondary scoring check: if any `Event.actors` entry matches a known GreatPerson name, add +2.0. Lower than the full named event bonus but enough to surface character moments.

**Recommendation: Option A for high-importance events, Option B for low-importance events.**

| Agent Event | Importance | Curator Treatment |
|-------------|-----------|-------------------|
| `notable_migration` (named char) | 4 → promoted to NamedEvent | +3.0 bonus → total 7.0 |
| `exile_return` (named char) | 6 → promoted to NamedEvent | +3.0 bonus → total 9.0 |
| `local_rebellion` (named leader) | 7 → promoted to NamedEvent | +3.0 bonus → total 10.0 |
| `loyalty_cascade` (includes named) | 6 → character reference bonus | +2.0 bonus → total 8.0 |
| `demographic_crisis` | 7 → no character reference | No bonus (macro event) |
| `occupation_shift` | 5 → character reference if named | +2.0 bonus → total 7.0 |

### Implementation

In `agent_events.rs` (M30), when generating events, check the `NamedCharacterRegistry` for the agent_id. If matched, set a `named_character: Option<String>` field on `AgentEvent`. The Python-side event conversion checks this field and promotes to `NamedEvent` when present.

---

## Decision 4: Narration Prompt Changes

### New Section: Agent Context Block

The narrator receives `agent_context` in `NarrationContext` (defined in M30 roadmap). The prompt needs guidance on how to use it:

```markdown
## Agent Context (when present)

You may receive an `agent_context` block containing population-level signals
from the agent simulation. Use these to flavor prose, not to invent events:

- `named_characters`: Named individuals with histories. Reference them BY NAME
  when narrating events they participated in. A migration event involving "Kael"
  should name Kael, not describe "a wandering merchant."
- `population_mood`: Overall sentiment ("content", "restless", "desperate").
  Use for atmospheric prose ("the streets were restless") but do not fabricate
  events from mood alone. Restless does not mean riots occurred unless a
  rebellion event exists.
- `displacement_fraction`: Fraction of population not in their origin region.
  High values (>0.2) suggest refugee crises worth mentioning if migration
  events support it.
- `recent_migrations`: Count of agent migrations in last 10 turns. High values
  reinforce displacement narrative.
- `dominant_occupation`: Most common occupation in affected regions. Can color
  descriptions ("a nation of soldiers" vs "a nation of scholars").
```

### New Rule: Character Continuity

```markdown
- If a named character appeared in a previous narration window, reference them
  by the same name in subsequent windows where they are active. Do not
  re-introduce them as anonymous ("a merchant") when they were already named
  ("Kael"). The reader has met them; maintain the thread.
```

This goes in the windowing strategy section, after the existing window-specific guidance.

### Interaction with Existing Prompt Patches

The two patches applied during narration prompt iteration (region name confabulation rule, great person tech sprint rule) are compatible with M30:

- **Region name confabulation rule**: Unchanged. Agent events don't change the fact that region names are world-gen artifacts.
- **Great person tech sprint rule**: Strengthened by M30. Agent-promoted characters during tech sprints are additional candidates for the "name the great persons explaining HOW the sprint happened" guidance. The rule's scope expands naturally.

### The Late-Window Turn-Number Patch (Pending from Seed 811)

The recommended but unapplied patch from the seed 811 review — reinforcing the "don't enumerate turn numbers" rule for windows 3–4 — is independent of M30 and should be applied during the next narration prompt iteration session.

---

## Decision 5: NamedCharacterRegistry Architecture

### Rust Side

```rust
pub struct NamedCharacterRegistry {
    characters: Vec<NamedCharacter>,
    agent_to_character: HashMap<u32, usize>,  // agent_id → character index
    per_civ_counts: HashMap<u8, usize>,       // civ_id → count
    global_count: usize,
}

pub struct NamedCharacter {
    pub agent_id: u32,
    pub name: String,               // procedurally generated
    pub role: u8,                   // maps to GreatPerson role
    pub civ_id: u8,
    pub origin_civ_id: u8,
    pub born_turn: u32,
    pub promotion_turn: u32,
    pub promotion_trigger: u8,      // enum: high_skill, rebellion, displacement, migration, versatility, loyalty_flip
    pub history: Vec<(u32, u8, u16)>,  // (turn, event_type, region) — compact timeline
}
```

### Promotion Check (Per Tick)

After decisions and demographics, scan alive agents for promotion triggers. O(n) scan, runs once per tick. Only agents not already in the registry are checked.

```rust
fn check_promotions(
    pool: &AgentPool,
    registry: &mut NamedCharacterRegistry,
    turn: u32,
    master_seed: [u8; 32],
) -> Vec<AgentEvent> {
    // Skip if global cap reached
    if registry.global_count >= MAX_NAMED_CHARACTERS { return vec![]; }

    let mut promotions = vec![];
    for slot in pool.alive_slots() {
        if registry.agent_to_character.contains_key(&pool.id(slot)) { continue; }
        if registry.per_civ_counts.get(&pool.civ_affinity(slot)).copied().unwrap_or(0) >= MAX_PER_CIV { continue; }

        if let Some(trigger) = check_trigger(pool, slot, turn) {
            let name = generate_name(pool.civ_affinity(slot), master_seed, turn, slot);
            let character = NamedCharacter { /* ... */ };
            registry.register(character);
            promotions.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: EVENT_NAMED_CHARACTER_PROMOTED,
                region: pool.region(slot),
                civ_affinity: pool.civ_affinity(slot),
                turn,
                target_region: 0,
            });
        }
    }
    promotions
}
```

### Python Side — Bridge to GreatPerson

When `agent_bridge.py` receives promotion events, it creates `GreatPerson` instances:

```python
def _promote_agent_to_great_person(self, event: AgentEvent, world: WorldState) -> GreatPerson:
    char_data = self._sim.get_named_character(event.agent_id)
    civ = world.civilizations[char_data.civ_id]

    gp = GreatPerson(
        name=char_data.name,
        role=ROLE_MAP[char_data.role],
        trait=generate_trait(char_data.promotion_trigger),
        civilization=civ.name,
        origin_civilization=world.civilizations[char_data.origin_civ_id].name,
        born_turn=char_data.born_turn,
        deeds=[f"Promoted via {TRIGGER_NAMES[char_data.promotion_trigger]}"],
        source="agent",
        agent_id=event.agent_id,
    )
    civ.great_persons.append(gp)
    return gp
```

### Name Generation

Use the existing cultural name pools from world-gen. Each civ has a name generator seeded by the civ's cultural template. Agent-promoted characters get names from their `origin_civ_id`'s pool (birth culture, not current affiliation). This produces culturally consistent names — a defector from Kethani still has a Kethani name.

---

## Decision 6: Agent Event Detection

The roadmap lists 8 agent event types. These are detected by comparing turn N state against turn N-1 state (or by accumulating within the tick).

### Detection Architecture

Some events are **immediate** (detected within a single tick) and some are **windowed** (require tracking state across multiple ticks).

**Immediate (detected in `behavior.rs` / `demographics.rs`):**
- `local_rebellion` — ≥5 agents rebel in a region (already an M26 event)
- `notable_migration` — named character moves regions (check registry after migration apply)

**Windowed (detected in `agent_events.rs`, new module):**

```rust
pub struct EventDetector {
    // Per-region rolling windows
    loyalty_flips: Vec<RingBuffer<(u32, u8)>>,  // (turn, count) per region
    deaths: Vec<RingBuffer<(u32, u16)>>,         // (turn, count) per region
    occ_switches: Vec<RingBuffer<(u32, u16)>>,
    scholar_departures: Vec<RingBuffer<(u32, u16)>>,
    merchant_arrivals: Vec<RingBuffer<(u32, u16)>>,
}
```

| Event | Window | Threshold | Detection |
|-------|--------|-----------|-----------|
| `loyalty_cascade` | 5 turns | ≥10 flips in one region | Sum loyalty_flips ring buffer |
| `demographic_crisis` | 10 turns | >30% population loss in region | Compare current vs 10-turns-ago count |
| `occupation_shift` | 5 turns | >25% switch in region | Sum occ_switches ring buffer |
| `economic_boom` | 20 turns | Merchant count doubles in region | Compare current vs 20-turns-ago merchant count |
| `brain_drain` | 10 turns | ≥5 scholars leave region | Sum scholar_departures ring buffer |
| `exile_return` | Immediate | Named character returns to origin_region after 30+ turns | Check registry + displacement_turn |

### Memory Cost

Ring buffers at 20-turn max window × 24 regions × 5 event types × 4 bytes = ~10KB. Negligible.

---

## Existing System Constraints M30 Must Respect

### Hard Constraints (Inviolable)

1. **GreatPerson lifespan is deterministic** — seeded by `seed + born_turn + hash(name)`, yields 20–30 turns. Agent events cannot extend lifespans.
2. **Role modifiers are domain-isolated** — general affects military, merchant affects trade, etc. No cross-domain coupling.
3. **Cooldowns are per-role, per-civ** — cannot bypass spawn limits. Agent promotions respect the same cooldowns as aggregate spawns.
4. **Active/retired/dead states are exhaustive** — no new states. Agent characters use the same lifecycle.
5. **Character relationships are event-indexed** — form/dissolve, don't persist mechanically.

### Soft Constraints (Narrative)

1. Great persons should be named in narration when explaining rapid advancement
2. Character events should cluster with other major events for narrative impact
3. Retired/dead persons remain accessible for historical reference
4. Agent-promoted characters should feel narratively distinct from aggregate great persons — their histories (migrations, occupation switches, loyalty flips) give them richer backstories

---

## Implementation Ordering

1. **NamedCharacterRegistry** — Rust-side registry with promotion triggers, name generation, history tracking
2. **EventDetector** — Windowed event detection across ticks
3. **FFI extensions** — Expose registry queries and promotion events to Python
4. **GreatPerson bridge** — Python-side promotion to GreatPerson instances
5. **Curator adjustments** — NamedEvent promotion for character-referencing events
6. **Narration prompt update** — Agent context block, character continuity rule, mood guidance
7. **Integration tests** — 500-turn run produces ≥5 named character references in chronicles
