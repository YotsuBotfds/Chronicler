# Spec C: Event Provenance & Schema

**Date:** 2026-04-03
**Scope:** Dissolution event schema expansion + GP deed provenance tracking
**Contract boundary:** Rust AgentEvent struct, Arrow FFI schema, Python AgentEventRecord, GreatPerson model, bundle sidecar

---

## Motivation

Two classes of historical data are currently reconstructed from mutable current state instead of being captured at event time:

1. **Dissolution events** lose the other bond party (`agent_b` hardcoded to 0) and the bond's formation turn (overwritten with the dissolution turn), because the Rust `AgentEvent` struct lacks fields for them.
2. **GP deeds** attribute all historical actions to the character's current region, because deeds are stored as bare strings with no structured provenance.

Both problems share a root cause: the event record didn't carry enough context at creation time, so consumers reconstruct it from state that has since changed.

---

## Section 1: Dissolution Event Schema Expansion

### Problem

`AgentEvent` (`chronicler-agents/src/tick.rs:30`) has 8 fields. Dissolution events need two that don't exist:

- **`target_agent_id`** — who was the other party in the dissolved bond
- **`formed_turn`** — when the bond originally formed

Currently, `agent_bridge.py:1103-1112` hardcodes `agent_b=0` and uses the dissolution turn as `formed_turn`, making dissolved relationships unidentifiable in narration.

### Design

Add two fields to `AgentEvent`:

```rust
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,
    pub region: u16,
    pub target_region: u16,      // overloaded: bond_type for dissolution (preserved)
    pub civ_affinity: u8,
    pub occupation: u8,
    pub belief: u8,
    pub turn: u32,
    pub target_agent_id: u32,    // NEW — other bond party (0 = N/A)
    pub formed_turn: u32,        // NEW — bond origin turn (0 = N/A)
}
```

### Constraints

- **Sentinel:** `target_agent_id=0` is safe — `AgentPool.next_id` starts at 1 (`pool.rs:179`), and `PARENT_NONE = 0` is already the no-parent sentinel.
- **Precision:** `formed_turn` is widened from `u16` source (`pool.rel_formed_turns` at `pool.rs:77`). Precision ceiling at 65,535 turns. Acceptable for current run lengths. Widening pool storage to `u32` is a separate concern if runs ever exceed that limit.
- **`target_region` stays overloaded** as `bond_type` for dissolution events. This is the existing convention; expanding it is out of scope.
- **Non-dissolution events** emit `target_agent_id: 0, formed_turn: 0`. Every `AgentEvent { ... }` constructor must include the new fields.

### Accepted Limitation: Asymmetric Mentor Bonds

`death_cleanup_sweep` (`formation.rs:382`) only scans alive slots. If a mentor dies and only the mentor held the bond edge, no dissolution event fires for that relationship. This is accepted for this spec. Follow-up only if narration needs symmetric dissolution coverage.

### Touch Points

**Rust (7 constructors + 2 schema sites):**

| File | Line | Change |
|------|------|--------|
| `tick.rs` | 30-39 | Add `target_agent_id: u32` and `formed_turn: u32` to struct |
| `tick.rs` | 269, 286, 309, 327, 593, 723 | Set `target_agent_id: 0, formed_turn: 0` on all 6 non-dissolution constructors |
| `formation.rs` | 397-406 | Read `pool.rel_target_ids[slot][i]` → `target_agent_id`, read `pool.rel_formed_turns[slot][i] as u32` → `formed_turn` |
| `ffi/schema.rs` | 59-69 | Add `Field::new("target_agent_id", DataType::UInt32, false)` and `Field::new("formed_turn", DataType::UInt32, false)` |
| `ffi/batch.rs` | 1212-1249 | Add `UInt32Builder` for both new columns in `events_to_batch()` |

**Python (3 sites):**

| File | Line | Change |
|------|------|--------|
| `models.py` | 627 | Add `target_agent_id: int = 0` and `formed_turn: int = 0` to `AgentEventRecord` |
| `agent_bridge.py` | 1481-1497 | `_convert_events()` reads `target_agent_id` and `formed_turn` columns (with fallback if absent) |
| `agent_bridge.py` | 1103-1112 | Build dissolution tuple from real fields: `(e.agent_id, e.target_agent_id, e.target_region, e.formed_turn)` |

**Bundle sidecar:**

| File | Line | Change |
|------|------|--------|
| `bundle.py` | 105-114 | Add `target_agent_id` (uint32) and `formed_turn` (uint32) columns to `write_agent_events_arrow()` |

### Compatibility

The in-process Arrow FFI schema (`events_schema()`) is rebuilt every run — no migration needed. The persisted `agent_events.arrow` sidecar gains two columns; old sidecars read by consumers that expect the new columns should handle missing columns gracefully (the same pattern `_convert_events` already uses for `belief`).

---

## Section 2: GP Deed Provenance

### Problem

`narrative.py:337-339` renders all deeds with `gp.region` (current location). A character who fought in Region A, traded in B, and settled in C has all three deeds shown as occurring in C.

Root cause: `GreatPerson.deeds` is `list[str]` with no structured metadata. Region is baked into the prose text but not extractable as data.

### Design

**New model** on `models.py`:

```python
class GreatPersonDeed(BaseModel):
    text: str
    region: str | None = None
    turn: int | None = None    # None for legacy, not 0
    civ: str | None = None
```

**Field change:** `GreatPerson.deeds: list[str]` → `list[GreatPersonDeed]`

**Legacy normalization:** Field validator on `GreatPerson` coerces bare strings to `GreatPersonDeed(text=s)` with `region=None`, `turn=None`, `civ=None`. This runs at model parse time, catching old bundles loaded through `live.py:59` and `main.py:952` before narration ever runs. No consumer-side type checks needed.

### `_append_deed()` Signature Change

```python
def _append_deed(gp, text, *, region=None, turn=None, civ=None):
    """Append a GreatPersonDeed, capping at DEEDS_CAP entries."""
    gp.deeds.append(GreatPersonDeed(text=text, region=region, turn=turn, civ=civ))
    if len(gp.deeds) > DEEDS_CAP:
        gp.deeds = gp.deeds[-DEEDS_CAP:]
```

### Multi-Region Deeds

For deeds spanning multiple regions (migration, pilgrimage), `region` is the **primary/destination** location. The full text still carries both places ("Migrated from X to Y"), but the structured field is single-valued.

### Call Sites (12 production)

**`great_persons.py` (4 sites):**

| Line | Deed | Region source |
|------|------|---------------|
| 111 | Retirement | `gp.region` |
| 308 | Death | `gp.region` |
| 410 | Pilgrimage return | `gp.region` (current = destination) |
| 482 | Pilgrimage departure | `best_region` (destination) |

**`agent_bridge.py` (8 sites):**

| Line | Deed | Region source |
|------|------|---------------|
| 1594 | Promotion | `region_name` (from event) |
| 1613 | Mule memory shaping | `gp.region` |
| 1718 | Return after exile | `target_name` (destination) |
| 1732 | Migration | `target_name` (destination) |
| 1764 | Exile after conquest | `gp.region` |
| 1832 | Defection during secession | `gp.region` |
| 1885 | Restoration return | `gp.region` |
| 1928 | Twilight absorption | `gp.region` |

All sites already have access to the region, turn (`world.turn`), and civ (`gp.civilization`) at call time. No new data plumbing required — just pass what's locally available.

### Narrative Consumer

`narrative.py:337-339` changes from:

```python
"recent_history": [
    {"event": d, "region": gp.region or "unknown"}
    for d in gp.deeds[-3:]
],
```

To:

```python
"recent_history": [
    {"event": d.text, "region": d.region or "unknown", "turn": d.turn}
    for d in gp.deeds[-3:]
],
```

All three structured fields (`text`, `region`, `turn`) surface in the prompt record. `civ` is available on the model for future use but not rendered in the current prompt template unless narration logic opts in.

### Bundle Compatibility

Pydantic serializes `GreatPersonDeed` as a dict in `model_dump(mode="json")`. Old bundles with `list[str]` deeds are normalized by the field validator at parse time. No bundle version bump needed.

---

## Testing Strategy

### Dissolution

- **Rust unit test:** `death_cleanup_sweep` emits correct `target_agent_id` and `formed_turn` from pool relationship slots
- **Rust regression:** Existing test at `formation.rs:1673` updated to assert new fields
- **Integration test:** Dissolution event round-trips through Arrow → `_convert_events()` → `dissolved_edges_by_turn` with real agent IDs and formation turns
- **Bundle test:** `write_agent_events_arrow()` includes new columns; verify schema on read-back

### Deed Provenance

- **Model test:** `GreatPerson(deeds=["old string"])` normalizes to `GreatPersonDeed(text="old string", region=None, turn=None, civ=None)`
- **`_append_deed` test:** Creates `GreatPersonDeed` with region/turn/civ populated
- **Narrative test:** Deed context in prompt uses deed-time region, not `gp.region`
- **Cap test:** Deeds list respects `DEEDS_CAP` with structured entries

---

## Out of Scope

- Widening `pool.rel_formed_turns` from `u16` to `u32` (only needed if runs exceed 65,535 turns)
- Symmetric dissolution events for mentor-death scenarios
- Rendering `deed.civ` in narration prompts (captured for future use)
- Any changes to the `target_region` overload convention for dissolution events
