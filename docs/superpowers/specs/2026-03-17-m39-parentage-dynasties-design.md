# M39: Parentage, Inheritance & Dynasties

**Status:** Spec approved, ready for implementation planning
**Estimated effort:** 3-4 days
**Scope:** ~40 lines Rust, ~80 lines Python, ~150 lines tests
**Dependencies:** M33 (personality, merged), M36 (cultural values, merged), M37 (belief, feat branch)

---

## Design Decisions

1. **Inherit at birth, drift handles assimilation.** Children inherit parent's cultural values and belief at birth. M36 cultural drift and M37 conversion pressure apply normally from the next turn onward. No exemption flags, no override mechanics. A migrant's child starts with foreign values and assimilates at the regional drift rate. 1-turn grace period is a natural consequence of tick ordering (births in Phase 9-10, drift in next turn's Phase 6).

2. **Dead ancestors are valid dynasty founders.** Dynasty detection does not require ancestors to be alive. `parent_id` references stable agent IDs (u32, never reused), so lookback always works. "House of Kiran" is most compelling when Kiran is already dead.

3. **Earliest promoted ancestor names the dynasty.** Name is frozen at founding. No renaming if a more prestigious descendant appears later.

4. **Parent-child only (no grandparent hop).** Dynasty detection checks one hop: `parent_id in named_agents`. The skip-a-generation case (grandparent promoted, parent unremarkable, grandchild promoted) is deferred — detection reliability is poor when the intermediate parent is dead and their pool slot reused. Grandparent hop can be added in a future milestone with a persistent genealogy cache.

5. **Purely narrative for M39.** Dynasty membership confers no mechanical effects (no loyalty bonuses, no promotion advantages). `dynasty_id` on named characters is the hook for future mechanical milestones.

6. **No seeding mechanism.** Initial agents get `parent_id = 0`. First dynasties emerge around turn 50-70. This bootstrap period is intentional — early simulation is "age of heroes" (individual founders), dynasties mark the transition to "age of institutions."

7. **Architecture: Approach A.** Rust owns `parent_id` (pool field, Arrow column, promotions batch). Python owns dynasty logic (detection, events, narrative) via `named_agents` dict lookup. No new FFI functions.

8. **Importance levels (intentional divergence from roadmap).** Dynasty founded = 7, extinction = 6, split = 5. Roadmap had 6/5/5. Bumped because dynasties are rare enough (~2-5 per 500 turns) to warrant higher narrative weight.

---

## Section 1: Data Model Changes (Rust)

### AgentPool (`pool.rs`)

New field:
- `parent_ids: Vec<u32>` — agent ID of biological parent. `PARENT_NONE (0)` for initial population or unknown parent.

4 bytes/agent. At 100k agents, 400KB.

**Sentinel assertion:** `PARENT_NONE = 0`. The pool's `next_id` counter must start at 1. Implementation plan must include a verification step confirming this in `pool.rs`. If `next_id` starts at 0, the first spawned agent is indistinguishable from "no parent."

### BirthInfo (`tick.rs`)

New field:
- `parent_id: u32` — copied from `pool.ids[parent_slot]` during demographics parallel phase.

### NamedCharacter (`named_characters.rs`)

New fields:
- `parent_id: u32` — captured from `pool.parent_ids[slot]` at promotion time.
- `dynasty_id: Option<u32>` — assigned by Python-side dynasty detection. `None` until membership established.

### GreatPerson (`models.py`)

New field:
- `parent_id: int = 0` — populated from promotions batch `parent_id` column.

No changes to: personality fields, cultural value fields, belief fields, alive/free_slots, skills, or any other existing field.

---

## Section 2: Birth Path Integration (Rust)

### Demographics parallel phase (`tick.rs`, `tick_region_demographics`)

M39 changes exactly two things in the birth path:

**1. Store parent_id:**
```
parent_id = pool.ids[parent_slot]   // stable agent ID, not slot index
```
Added to `BirthInfo` alongside existing parent reads (loyalty, cultural values, belief). Same cache line neighborhood — zero additional memory access cost.

**2. Personality function swap:**
```rust
// BEFORE (M33 — spawn-style assignment):
let civ_mean = signals.personality_mean_for_civ(civ_id);
let personality = assign_personality(&mut personality_rng, civ_mean);

// AFTER (M39 — inheritance from parent):
let parent_personality = [
    pool.boldness[slot],
    pool.ambition[slot],
    pool.loyalty_trait[slot],
];
let personality = inherit_personality(&mut personality_rng, parent_personality);
```

`inherit_personality` already exists in `demographics.rs` with tighter noise (`BIRTH_PERSONALITY_NOISE = 0.15` vs spawn's `SPAWN_PERSONALITY_NOISE = 0.3`). `BirthInfo.personality` still carries the pre-computed child personality. The sequential birth-application phase is unchanged.

### World-gen spawn path

No changes. Initial agents continue using `assign_personality(rng, civ_mean)` and get `parent_id = PARENT_NONE`.

### What doesn't change

Cultural value inheritance (M36, already in birth path), belief inheritance (M37, already in birth path), loyalty inheritance, satisfaction initialization. M39 touches the birth path at exactly two points: storing `parent_id` and swapping the personality function call.

---

## Section 3: FFI / Arrow Changes

### Agent data batch (`ffi.rs`)

New column:
- `"parent_id"`: `UInt32Array`, sourced from `pool.parent_ids`

Follows existing pattern — every pool field is already exposed as an Arrow column.

### Promotions RecordBatch (`ffi.rs`, `promotions_schema`)

New column:
- `Field::new("parent_id", DataType::UInt32, false)` — read from `pool.parent_ids[slot]` in the `get_promotions()` loop.

Python receives `parent_id` on the promotions batch, stores it on the `GreatPerson` record.

### NamedCharacter.register() (`named_characters.rs`)

Add `parent_id: u32` parameter. The `get_promotions()` loop already has `slot` — read `pool.parent_ids[slot]` and pass through.

### Event batch

No changes. Dynasty events are emitted through the Python-side `events.py` pipeline, not through the Rust event batch.

---

## Section 4: Dynasty Registry & Detection (Python)

### DynastyRegistry (`dynasties.py`, new file, ~60-80 lines)

```python
@dataclass
class Dynasty:
    dynasty_id: int          # monotonic counter
    founder_id: int          # agent_id of earliest promoted ancestor (the parent)
    founder_name: str        # frozen at founding
    civ_id: int              # founding civ
    members: list[int]       # agent_ids of all promoted members
    founded_turn: int
    split_detected: bool     # one-shot flag for split event
    extinct: bool            # set when last member dies
```

### Detection — on promotion only

When Python processes the promotions batch each turn:
1. For each new promoted character, read `parent_id` from the batch.
2. Check `parent_id in named_agents` — is parent a promoted GreatPerson?
3. If yes, check if parent already has a `dynasty_id`:
   - **Yes:** Child joins existing dynasty. Assign same `dynasty_id`.
   - **No:** New dynasty founded. Founder = parent (earliest promoted ancestor). Create `Dynasty` record, assign `dynasty_id` to both parent and child.

Single dict lookup per promotion. O(1).

### Extinction — on death event processing

Death events carry `agent_id` (confirmed: `ffi.rs:640`). On processing a death:
1. Check if deceased is in `named_agents`, mark `GreatPerson.alive = False` (already done by `kill_great_person`).
2. Check if deceased belongs to any dynasty's `members`.
3. If yes: `all(not named_agents[mid].alive for mid in dynasty.members)` — if true, mark `dynasty.extinct = True`, emit extinction event.

No pool access needed. `GreatPerson.alive` is already maintained by `great_persons.py`.

Deaths are processed sequentially per turn — same-turn deaths (war, plague) resolve correctly because `kill_great_person` updates `alive` before the next death in the loop.

### Split — on promotion or civ-change

When a dynasty member's `civ_affinity` differs from another member's, and `split_detected` is False:
- Emit split event, set `split_detected = True`.
- Checked on promotion (new member might be different civ) and on civ-change events (conquest/secession).
- One-shot: flag prevents re-firing every turn members remain separated.

---

## Section 5: Dynasty Events & Narrative Integration

### Event types

| Event | Trigger | Importance | Example |
|-------|---------|------------|---------|
| Dynasty Founded | First parent-child promoted pair detected | 7 | "The House of Kiran is established as Tala, daughter of the great general Kiran, rises to prominence" |
| Dynasty Extinct | All members dead (`GreatPerson.alive = False`) | 6 | "The House of Kiran has ended — no heir remains" |
| Dynasty Split | Members span different civs, `split_detected` flips | 5 | "The House of Kiran is divided — Sera serves Ashara while her cousin holds loyalty to Verath" |

**Note:** Importance levels intentionally diverge from roadmap (6/5/5 → 7/6/5). Dynasties are rare events (~2-5 per 500-turn run) and warrant higher narrative weight.

### Narrative context enrichment (`narrative.py`)

Additive change to `build_agent_context_for_moment()`:
- When an active named character belongs to a dynasty, include dynasty metadata in the character context block:
  - Dynasty name and founder
  - Living vs. dead members (enables "last of their line" tension)
  - Split status (enables inter-civ drama)

No new narrator prompt structure. Dynasty info is folded into the existing character context block. The narrator naturally incorporates lineage context alongside faction membership and occupation.

---

## Section 6: Testing Strategy

### Tier 1 — Unit tests (Rust)

- `pool.rs`: `parent_ids` initialized to `PARENT_NONE` on spawn, set correctly on birth.
- `pool.rs`: Assert `next_id` starts at 1 (sentinel safety for `PARENT_NONE = 0`).
- `tick.rs`: `BirthInfo.parent_id` carries parent's agent ID, not slot index.
- `tick.rs`: **Path divergence test** — verify initial spawn agents get `parent_id = PARENT_NONE` AND use `assign_personality(civ_mean)`, while birth agents get `parent_id = mother.agent_id` AND use `inherit_personality(parent_personality)`. Single test covering the conditional dispatch fork.
- `demographics.rs`: `inherit_personality` produces values clustered tighter around parent than `assign_personality` around civ mean (statistical: run 1000 samples, compare variance).
- `named_characters.rs`: `parent_id` populated on `register()`, `NamedCharacter` carries correct parent ID.
- `ffi.rs`: Promotions batch includes `parent_id` column with correct values.

### Tier 1 — Unit tests (Python)

- `dynasties.py`: Dynasty founding on parent-child promotion pair.
- `dynasties.py`: Child joins existing dynasty (parent already has `dynasty_id`).
- `dynasties.py`: No dynasty when `parent_id` not in `named_agents`.
- `dynasties.py`: Extinction when all members dead.
- `dynasties.py`: Split detection when members span civs, one-shot flag prevents re-fire.

### Tier 2 — Regression (200 seeds x 200 turns)

- At least 1 dynasty founded across 200 seeds (statistical — if zero, birth/promotion pipeline is broken).
- No dynasty founded before first possible turn (~35 minimum: parent reaches promotion age + child born + child promoted).
- Parent-child relationship in every dynasty is valid (`parent_id` resolves to a real `named_agents` entry).
- No dynasty with `founder_name = ""` or missing founder.
- **`--agents=off` regression:** Verify `--agents=off` produces identical output to pre-M39. Standard regression gate for every milestone.

### Tier 3 — Characterization (500 turns)

- Target: 2-5 dynasties per run (calibration, not hard gate).
- Dynasty extinction occurs in at least some runs.
- Split events occur when civs fracture (requires war/secession in the run).
- Personality clustering: dynasty members' personality values are statistically closer to each other than to population mean (inherited noise is tighter).

**Harness floor:** Tier 2 tests require minimum 200 turns. Tier 3 tests require minimum 500 turns. A 50-turn harness sees zero dynasties and passes vacuously.

---

## Deferred / Future Work

- **Grandparent hop (skip-a-generation):** Requires persistent genealogy cache (`{agent_id: parent_id}` dict maintained from births). Deferred due to detection reliability concerns when intermediate parent is dead. Can be added as a future enhancement.
- **Mechanical dynasty effects:** Loyalty bonuses between dynasty members, promotion advantages, diplomacy modifiers. `dynasty_id` on named characters is the hook.
- **Dynasty rivalry:** Two dynasties in the same civ competing for influence. Requires faction integration.
- **Dynasty-aware succession:** Leaders from dynasties get succession bonuses. Requires `leaders.py` integration.
