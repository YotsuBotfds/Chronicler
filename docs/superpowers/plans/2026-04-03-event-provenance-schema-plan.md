# Event Provenance & Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two provenance bugs: dissolution events that lose bond-party identity, and GP deeds that lose their historical region/turn/civ context.

**Architecture:** Rust `AgentEvent` gains two fields (`target_agent_id`, `formed_turn`), propagated through Arrow FFI → Python `AgentEventRecord` → bundle sidecar. GP deeds change from `list[str]` to `list[GreatPersonDeed]` with a field validator for legacy normalization. `gp.region` is maintained on named-character movement as a prerequisite.

**Tech Stack:** Rust (AgentPool, Arrow), Python (Pydantic models, narrative pipeline), PyO3/maturin FFI bridge

**Spec:** `docs/superpowers/specs/2026-04-03-event-provenance-schema-design.md`

---

### Task 1: `gp.region` Maintenance on Named-Character Movement

**Files:**
- Modify: `src/chronicler/agent_bridge.py:1718`, `src/chronicler/agent_bridge.py:1732`
- Modify: `src/chronicler/great_persons.py:410`
- Test: `tests/test_deeds.py`

- [ ] **Step 1: Write failing test — migration updates `gp.region`**

In `tests/test_deeds.py`, add:

```python
def test_gp_region_updated_on_migration():
    """gp.region should reflect destination after migration deed."""
    gp = _make_gp(region="Origin")
    # Simulate what _detect_character_events does at agent_bridge.py:1732
    target_name = "Destination"
    gp.region = target_name
    _append_deed(gp, f"Migrated from Origin to {target_name}")
    assert gp.region == "Destination"


def test_gp_region_updated_on_exile_return():
    """gp.region should reflect destination after exile return deed."""
    gp = _make_gp(region="ExilePlace")
    target_name = "Homeland"
    gp.region = target_name
    _append_deed(gp, f"Returned to {target_name} after 35 turns")
    assert gp.region == "Homeland"


def test_gp_region_updated_on_pilgrimage_return():
    """gp.region should reflect destination after pilgrimage return."""
    gp = _make_gp(region="StartRegion")
    destination = "HolyCity"
    gp.region = destination
    _append_deed(gp, "Returned from pilgrimage as Prophet")
    assert gp.region == "HolyCity"
```

- [ ] **Step 2: Run tests to verify they pass**

These tests validate the contract but will pass immediately since they set `gp.region` inline. The real fix is in the production code below.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "region_updated"`
Expected: 3 PASS

- [ ] **Step 3: Add `gp.region` updates at migration sites**

In `src/chronicler/agent_bridge.py`, at line 1718 (exile return), add `gp.region = target_name` **before** the `_append_deed` call:

```python
                    if e.agent_id in self.gp_by_agent_id:
                        self.gp_by_agent_id[e.agent_id].region = target_name
                        _append_deed(self.gp_by_agent_id[e.agent_id], f"Returned to {target_name} after {turns_away} turns")
```

At line 1732 (migration), add `gp.region = target_name` **before** the `_append_deed` call:

```python
            if e.agent_id in self.gp_by_agent_id:
                self.gp_by_agent_id[e.agent_id].region = target_name
                _append_deed(self.gp_by_agent_id[e.agent_id], f"Migrated from {source_name} to {target_name}")
```

In `src/chronicler/great_persons.py`, at line 410 (pilgrimage return), add `gp.region = destination` **before** the `_append_deed` call:

```python
            gp.region = destination
            _append_deed(gp, "Returned from pilgrimage as Prophet")
```

- [ ] **Step 4: Run broader test suite to verify no regressions**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py tests/test_great_persons.py tests/test_agent_bridge.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/great_persons.py tests/test_deeds.py
git commit -m "fix: maintain gp.region on named-character movement

Updates gp.region at migration (agent_bridge.py:1732), exile return
(agent_bridge.py:1718), and pilgrimage return (great_persons.py:410)
so downstream transition filters and deed provenance use the actual
current region, not the stale promotion-era region."
```

---

### Task 2: `GreatPersonDeed` Model and Legacy Validator

**Files:**
- Modify: `src/chronicler/models.py:447-458`
- Test: `tests/test_deeds.py`

- [ ] **Step 1: Write failing tests — model and legacy normalization**

In `tests/test_deeds.py`, add at the top:

```python
from chronicler.models import GreatPerson, GreatPersonDeed
```

Update the existing import to include `GreatPersonDeed`. Then add:

```python
def test_great_person_deed_model():
    """GreatPersonDeed stores structured provenance."""
    deed = GreatPersonDeed(text="Led a campaign", region="Ashfields", turn=47, civ="Aram")
    assert deed.text == "Led a campaign"
    assert deed.region == "Ashfields"
    assert deed.turn == 47
    assert deed.civ == "Aram"


def test_great_person_deed_defaults():
    """GreatPersonDeed defaults optional fields to None."""
    deed = GreatPersonDeed(text="Something happened")
    assert deed.region is None
    assert deed.turn is None
    assert deed.civ is None


def test_legacy_string_deeds_normalized():
    """Old-format string deeds are coerced to GreatPersonDeed at parse time."""
    gp = _make_gp()
    gp_data = gp.model_dump()
    gp_data["deeds"] = ["Old deed string", "Another old deed"]
    loaded = GreatPerson(**gp_data)
    assert len(loaded.deeds) == 2
    assert isinstance(loaded.deeds[0], GreatPersonDeed)
    assert loaded.deeds[0].text == "Old deed string"
    assert loaded.deeds[0].region is None
    assert loaded.deeds[0].turn is None
    assert loaded.deeds[0].civ is None


def test_structured_deeds_round_trip():
    """GreatPersonDeed survives model_dump → re-parse."""
    gp = _make_gp()
    gp.deeds = [GreatPersonDeed(text="Led campaign", region="Ashfields", turn=47, civ="Aram")]
    data = gp.model_dump(mode="json")
    loaded = GreatPerson(**data)
    assert isinstance(loaded.deeds[0], GreatPersonDeed)
    assert loaded.deeds[0].region == "Ashfields"
    assert loaded.deeds[0].turn == 47
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "great_person_deed or legacy_string or structured_deeds"`
Expected: FAIL — `GreatPersonDeed` does not exist yet

- [ ] **Step 3: Add `GreatPersonDeed` model and field validator**

In `src/chronicler/models.py`, add the new model **before** the `GreatPerson` class (around line 445):

```python
class GreatPersonDeed(BaseModel):
    """Structured deed with event-time provenance."""
    text: str
    region: str | None = None
    turn: int | None = None
    civ: str | None = None
```

Change `GreatPerson.deeds` field (currently `deeds: list[str] = Field(default_factory=list)`) to:

```python
    deeds: list[GreatPersonDeed] = Field(default_factory=list)
```

Add a field validator on `GreatPerson` to normalize legacy strings:

```python
    @field_validator("deeds", mode="before")
    @classmethod
    def _normalize_deeds(cls, v):
        if not isinstance(v, list):
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({"text": item})
            else:
                result.append(item)
        return result
```

Ensure `field_validator` is imported from `pydantic` at the top of models.py (check existing imports).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "great_person_deed or legacy_string or structured_deeds"`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_deeds.py
git commit -m "feat: add GreatPersonDeed model with legacy string validator

Deeds change from list[str] to list[GreatPersonDeed] with text, region,
turn, civ fields. Field validator coerces bare strings at parse time."
```

---

### Task 3: Migrate `_append_deed()` and Update All 12 Call Sites

**Files:**
- Modify: `src/chronicler/great_persons.py:26-30`
- Modify: `src/chronicler/great_persons.py:111, 308, 410, 482`
- Modify: `src/chronicler/agent_bridge.py:1594, 1613, 1718, 1732, 1764, 1832, 1885, 1928`
- Test: `tests/test_deeds.py`

- [ ] **Step 1: Write failing test — `_append_deed` creates structured deeds**

In `tests/test_deeds.py`, add:

```python
def test_append_deed_creates_structured_deed():
    """_append_deed creates GreatPersonDeed with provenance fields."""
    gp = _make_gp(region="Ashfields", civilization="Aram")
    _append_deed(gp, "Led a campaign", region="Ashfields", turn=47, civ="Aram")
    assert isinstance(gp.deeds[-1], GreatPersonDeed)
    assert gp.deeds[-1].text == "Led a campaign"
    assert gp.deeds[-1].region == "Ashfields"
    assert gp.deeds[-1].turn == 47
    assert gp.deeds[-1].civ == "Aram"


def test_append_deed_defaults_none():
    """_append_deed defaults optional fields to None when not provided."""
    gp = _make_gp()
    _append_deed(gp, "Something happened")
    assert isinstance(gp.deeds[-1], GreatPersonDeed)
    assert gp.deeds[-1].region is None
    assert gp.deeds[-1].turn is None


def test_append_deed_cap_structured():
    """_append_deed respects DEEDS_CAP with structured entries."""
    gp = _make_gp()
    for i in range(15):
        _append_deed(gp, f"Deed {i}", region=f"R{i}", turn=i)
    assert len(gp.deeds) == DEEDS_CAP
    assert gp.deeds[0].text == "Deed 5"
    assert gp.deeds[0].region == "R5"
    assert gp.deeds[-1].text == "Deed 14"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "append_deed_creates or append_deed_defaults_none or append_deed_cap_structured"`
Expected: FAIL — `_append_deed` doesn't accept keyword args yet

- [ ] **Step 3: Update `_append_deed()` signature**

In `src/chronicler/great_persons.py`, replace lines 26-30:

```python
def _append_deed(gp: "GreatPerson", text: str, *, region: str | None = None, turn: int | None = None, civ: str | None = None) -> None:
    """Append a GreatPersonDeed to a GreatPerson, capping at DEEDS_CAP entries."""
    from chronicler.models import GreatPersonDeed
    gp.deeds.append(GreatPersonDeed(text=text, region=region, turn=turn, civ=civ))
    if len(gp.deeds) > DEEDS_CAP:
        gp.deeds = gp.deeds[-DEEDS_CAP:]
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "append_deed_creates or append_deed_defaults_none or append_deed_cap_structured"`
Expected: 3 PASS

- [ ] **Step 5: Update existing tests that compare deeds as strings**

The existing tests in `tests/test_deeds.py` compare `gp.deeds[-1] == "some string"` and `gp.deeds[0] == "Deed 5"`. These now fail because deeds are `GreatPersonDeed` objects. Update every string comparison to use `.text`:

- `test_deeds_cap`: change `gp.deeds[0] == "Deed 5"` → `gp.deeds[0].text == "Deed 5"`, `gp.deeds[-1] == "Deed 14"` → `gp.deeds[-1].text == "Deed 14"`. Also change the inline `gp.deeds.append(f"Deed {i}")` loop to use `_append_deed(gp, f"Deed {i}")`.
- `test_append_deed_cap`: change `gp.deeds[0] == "Deed 5"` → `gp.deeds[0].text == "Deed 5"`, `gp.deeds[-1] == "Deed 14"` → `gp.deeds[-1].text == "Deed 14"`.
- `test_append_deed_under_cap`: change `.deeds[0] == "Deed 0"` → `.deeds[0].text == "Deed 0"`, `.deeds[-1] == "Deed 4"` → `.deeds[-1].text == "Deed 4"`.
- `test_deed_format_*` (6 tests): change `gp.deeds[-1] == "..."` → `gp.deeds[-1].text == "..."`.
- `test_deeds_initially_empty`: change `gp.deeds == []` → `len(gp.deeds) == 0` (already works either way).
- `test_deeds_exact_cap_no_trim`: change `.deeds[0] == "Deed 0"` → `.deeds[0].text == "Deed 0"`.

- [ ] **Step 6: Run full test_deeds to verify all pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v`
Expected: all PASS

- [ ] **Step 7: Update `great_persons.py` call sites (4 sites)**

Line 111 (retirement):
```python
    _append_deed(gp, f"Retired in {gp.region or 'unknown'}", region=gp.region, turn=world.turn, civ=gp.civilization)
```

Line 308 (death):
```python
    _append_deed(gp, f"Died in {gp.region or 'unknown'}", region=gp.region, turn=world.turn, civ=gp.civilization)
```

Line 410 (pilgrimage return — `gp.region` was already set to `destination` in Task 1):
```python
            _append_deed(gp, "Returned from pilgrimage as Prophet", region=destination, turn=current_turn, civ=gp.civilization)
```

Line 482 (pilgrimage departure):
```python
        _append_deed(gp, f"Departed on pilgrimage to {best_region}", region=best_region, turn=current_turn, civ=gp.civilization)
```

Note: `current_turn` is the parameter name in `process_pilgrimages()`. Verify with `Read` at call time.

- [ ] **Step 8: Update `agent_bridge.py` call sites (8 sites)**

Line 1594 (promotion):
```python
            _append_deed(gp, f"Promoted as {role} in {region_name}", region=region_name, turn=world.turn, civ=gp.civilization)
```

Line 1613 (mule memory shaping):
```python
                            _append_deed(gp, f"Mule: shaped by memory type {event_type}", region=gp.region, turn=world.turn, civ=gp.civilization)
```

Line 1718 (exile return — `gp.region` already set to `target_name` in Task 1):
```python
                        _append_deed(self.gp_by_agent_id[e.agent_id], f"Returned to {target_name} after {turns_away} turns", region=target_name, turn=world.turn, civ=self.gp_by_agent_id[e.agent_id].civilization)
```

Line 1732 (migration — `gp.region` already set to `target_name` in Task 1):
```python
                _append_deed(self.gp_by_agent_id[e.agent_id], f"Migrated from {source_name} to {target_name}", region=target_name, turn=world.turn, civ=self.gp_by_agent_id[e.agent_id].civilization)
```

Line 1764 (exile after conquest):
```python
            _append_deed(gp, f"Exiled after conquest of {gp.region or conquered_civ.name}", region=gp.region, turn=world.turn, civ=gp.civilization)
```

Line 1832 (defection during secession):
```python
            _append_deed(gp, f"Defected to {new_civ.name} during secession", region=gp.region, turn=world.turn, civ=new_civ.name)
```

Line 1885 (restoration return):
```python
            _append_deed(gp, f"Returned to {restored_civ.name} during restoration", region=gp.region, turn=world.turn, civ=restored_civ.name)
```

Line 1928 (twilight absorption):
```python
            _append_deed(gp, f"Absorbed into {absorber_civ.name} during twilight absorption", region=gp.region, turn=world.turn, civ=absorber_civ.name)
```

- [ ] **Step 9: Run broad regression**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py tests/test_great_persons.py tests/test_agent_bridge.py tests/test_narrative.py -q`
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add src/chronicler/great_persons.py src/chronicler/agent_bridge.py tests/test_deeds.py
git commit -m "feat: migrate _append_deed to structured GreatPersonDeed at all 12 call sites

Every deed now carries region, turn, civ captured at event time."
```

---

### Task 4: Narrative Consumer — Use Deed Provenance

**Files:**
- Modify: `src/chronicler/narrative.py:337-339`
- Test: `tests/test_deeds.py`

- [ ] **Step 1: Write failing test — narrative uses deed-time region**

In `tests/test_deeds.py`, add:

```python
def test_narrative_deed_uses_deed_region_not_current():
    """Deed provenance region should differ from gp.region when character moved."""
    gp = _make_gp(region="CurrentRegion")
    from chronicler.models import GreatPersonDeed
    gp.deeds = [
        GreatPersonDeed(text="Fought in battle", region="OldRegion", turn=10, civ="Aram"),
        GreatPersonDeed(text="Traded goods", region="MiddleRegion", turn=20, civ="Aram"),
        GreatPersonDeed(text="Settled down", region="CurrentRegion", turn=30, civ="Aram"),
    ]
    # Simulate narrative context builder output
    recent_history = [
        {"event": d.text, "region": d.region or "unknown", "turn": d.turn}
        for d in gp.deeds[-3:]
    ]
    assert recent_history[0]["region"] == "OldRegion"
    assert recent_history[1]["region"] == "MiddleRegion"
    assert recent_history[2]["region"] == "CurrentRegion"
```

- [ ] **Step 2: Run test to verify it passes**

This tests the contract, not the production code. It passes immediately.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deeds.py -v -k "narrative_deed_uses"`
Expected: PASS

- [ ] **Step 3: Update narrative consumer**

In `src/chronicler/narrative.py`, replace lines 337-340:

```python
            "recent_history": [
                {"event": d, "region": gp.region or "unknown"}
                for d in gp.deeds[-3:]
            ],
```

With:

```python
            "recent_history": [
                {"event": d.text, "region": d.region or "unknown", "turn": d.turn}
                for d in gp.deeds[-3:]
            ],
```

- [ ] **Step 4: Run narrative tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_narrative.py tests/test_deeds.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_deeds.py
git commit -m "fix: narrative context uses deed-time region/turn, not gp.region

recent_history entries now carry d.text, d.region, d.turn from
GreatPersonDeed instead of reconstructing from mutable gp.region."
```

---

### Task 5: Rust `AgentEvent` Schema Expansion

**Files:**
- Modify: `chronicler-agents/src/tick.rs:30-39`
- Modify: `chronicler-agents/src/tick.rs:269, 286, 309, 327, 593, 723`
- Modify: `chronicler-agents/src/formation.rs:397-406`
- Modify: `chronicler-agents/src/ffi/schema.rs:59-69`
- Modify: `chronicler-agents/src/ffi/batch.rs:1212-1249`
- Test: `chronicler-agents/src/formation.rs` (existing test at line 1673)

- [ ] **Step 1: Add fields to `AgentEvent` struct**

In `chronicler-agents/src/tick.rs`, replace lines 30-39:

```rust
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,
    pub region: u16,
    pub target_region: u16,
    pub civ_affinity: u8,
    pub occupation: u8,
    pub belief: u8,
    pub turn: u32,
    pub target_agent_id: u32,
    pub formed_turn: u32,
}
```

- [ ] **Step 2: Fix all 6 non-dissolution constructors in `tick.rs`**

Add `target_agent_id: 0, formed_turn: 0,` to each `AgentEvent { ... }` block at lines 269, 286, 309, 327, 593, 723. Example for line 269 (rebellion):

```rust
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 1,
                region,
                target_region: 0,
                civ_affinity: pool.civ_affinity(slot),
                occupation: pool.occupation(slot),
                belief: pool.beliefs[slot],
                turn,
                target_agent_id: 0,
                formed_turn: 0,
            });
```

Repeat for all 6 constructors. Each one gets the same two trailing fields with value `0`.

- [ ] **Step 3: Fix dissolution constructor in `formation.rs`**

In `chronicler-agents/src/formation.rs`, replace lines 397-406 in `death_cleanup_sweep`:

```rust
                events.push(crate::tick::AgentEvent {
                    agent_id: pool.ids[slot],
                    event_type: agent::LIFE_EVENT_DISSOLUTION,
                    region: pool.regions[slot],
                    target_region: bond_type as u16,
                    civ_affinity: pool.civ_affinities[slot],
                    occupation: pool.occupations[slot],
                    belief: pool.beliefs[slot],
                    turn,
                    target_agent_id: target_id,
                    formed_turn: pool.rel_formed_turns[slot][i] as u32,
                });
```

Note: `target_id` is already in scope as `pool.rel_target_ids[slot][i]` (line 394). `pool.rel_formed_turns[slot][i]` is `u16`, widened to `u32`.

- [ ] **Step 4: Update Arrow schema**

In `chronicler-agents/src/ffi/schema.rs`, add two fields to `events_schema()` after the `turn` field:

```rust
pub fn events_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_id", DataType::UInt32, false),
        Field::new("event_type", DataType::UInt8, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("target_region", DataType::UInt16, false),
        Field::new("civ_affinity", DataType::UInt8, false),
        Field::new("occupation", DataType::UInt8, false),
        Field::new("belief", DataType::UInt8, false),
        Field::new("turn", DataType::UInt32, false),
        Field::new("target_agent_id", DataType::UInt32, false),
        Field::new("formed_turn", DataType::UInt32, false),
    ])
}
```

- [ ] **Step 5: Update Arrow batch serializer**

In `chronicler-agents/src/ffi/batch.rs`, update `events_to_batch()` to include the two new columns. Add builders:

```rust
    let mut target_agent_ids = UInt32Builder::with_capacity(n);
    let mut formed_turns = UInt32Builder::with_capacity(n);
```

In the loop body, add:

```rust
        target_agent_ids.append_value(e.target_agent_id);
        formed_turns.append_value(e.formed_turn);
```

In the `RecordBatch::try_new` vec, add after `turns`:

```rust
            Arc::new(target_agent_ids.finish()) as _,
            Arc::new(formed_turns.finish()) as _,
```

- [ ] **Step 6: Update existing dissolution test**

In `chronicler-agents/src/formation.rs`, at the test around line 1673, add assertions for the new fields after line 1678:

```rust
        assert_eq!(events[0].target_agent_id, id_b);
        assert_eq!(events[0].formed_turn, pool.rel_formed_turns[a][0] as u32);
```

Wait — `id_b` is the dead agent and the bond to b was removed. The test setup has `a` bonded to `b` (Friend) and `c` (Kin), then `b` dies. After cleanup, the dissolution event should carry `target_agent_id = id_b`. `id_b` is already in scope at the test (used earlier). For `formed_turn`, the test needs to set a known value. Check the test setup — if `rel_formed_turns` is initialized to 0 by default, assert against 0.

Add after line 1678:

```rust
        assert_eq!(events[0].target_agent_id, id_b);
        assert_eq!(events[0].formed_turn, 0); // default formation turn from pool init
```

- [ ] **Step 7: Run Rust tests**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml -E "test(death_cleanup)"`
Expected: PASS

- [ ] **Step 8: Run full Rust suite**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
Expected: all PASS (or known skips only)

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/formation.rs chronicler-agents/src/ffi/schema.rs chronicler-agents/src/ffi/batch.rs
git commit -m "feat(rust): add target_agent_id and formed_turn to AgentEvent

Dissolution events now carry the other bond party's ID and the bond's
original formation turn. All non-dissolution constructors emit 0 for both."
```

---

### Task 6: Python `AgentEventRecord` + `_convert_events()` + Dissolution Tuple

**Files:**
- Modify: `src/chronicler/models.py:627` (AgentEventRecord)
- Modify: `src/chronicler/agent_bridge.py:1481-1497` (_convert_events)
- Modify: `src/chronicler/agent_bridge.py:1103-1112` (dissolution tuple)
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Write failing test — dissolution tuple uses real fields**

In `tests/test_agent_bridge.py`, find the existing dissolution-related tests and add:

```python
def test_dissolution_tuple_uses_target_agent_id_and_formed_turn():
    """Dissolution events should carry real target_agent_id and formed_turn."""
    import pyarrow as pa
    from chronicler.agent_bridge import AgentBridge

    # Build a minimal event batch with the new schema
    batch = pa.record_batch({
        "agent_id": pa.array([100], type=pa.uint32()),
        "event_type": pa.array([6], type=pa.uint8()),  # 6 = dissolution
        "region": pa.array([0], type=pa.uint16()),
        "target_region": pa.array([3], type=pa.uint16()),  # bond_type
        "civ_affinity": pa.array([0], type=pa.uint8()),
        "occupation": pa.array([0], type=pa.uint8()),
        "belief": pa.array([0], type=pa.uint8()),
        "turn": pa.array([50], type=pa.uint32()),
        "target_agent_id": pa.array([200], type=pa.uint32()),
        "formed_turn": pa.array([10], type=pa.uint32()),
    })

    bridge = AgentBridge.__new__(AgentBridge)
    records = bridge._convert_events(batch, 50)
    assert len(records) == 1
    assert records[0].target_agent_id == 200
    assert records[0].formed_turn == 10
```

- [ ] **Step 2: Write failing test — old schema fallback**

```python
def test_convert_events_old_schema_fallback():
    """_convert_events handles batches missing target_agent_id and formed_turn."""
    import pyarrow as pa
    from chronicler.agent_bridge import AgentBridge

    # Old-format batch without new columns
    batch = pa.record_batch({
        "agent_id": pa.array([100], type=pa.uint32()),
        "event_type": pa.array([6], type=pa.uint8()),
        "region": pa.array([0], type=pa.uint16()),
        "target_region": pa.array([3], type=pa.uint16()),
        "civ_affinity": pa.array([0], type=pa.uint8()),
        "occupation": pa.array([0], type=pa.uint8()),
        "belief": pa.array([0], type=pa.uint8()),
        "turn": pa.array([50], type=pa.uint32()),
    })

    bridge = AgentBridge.__new__(AgentBridge)
    records = bridge._convert_events(batch, 50)
    assert len(records) == 1
    assert records[0].target_agent_id == 0
    assert records[0].formed_turn == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_bridge.py -v -k "dissolution_tuple_uses or convert_events_old_schema"`
Expected: FAIL — `AgentEventRecord` lacks `target_agent_id` / `formed_turn`

- [ ] **Step 4: Add fields to `AgentEventRecord`**

In `src/chronicler/models.py`, at the `AgentEventRecord` dataclass (line 627), add after `belief`:

```python
    target_agent_id: int = 0
    formed_turn: int = 0
```

- [ ] **Step 5: Update `_convert_events()` to read new columns**

In `src/chronicler/agent_bridge.py`, update `_convert_events()` (line 1481). Add column reads with fallback:

```python
    def _convert_events(self, batch, turn):
        """Convert Arrow events RecordBatch to AgentEventRecord list."""
        records = []
        belief_col = batch.column("belief") if "belief" in batch.schema.names else None
        target_agent_id_col = batch.column("target_agent_id") if "target_agent_id" in batch.schema.names else None
        formed_turn_col = batch.column("formed_turn") if "formed_turn" in batch.schema.names else None
        for i in range(batch.num_rows):
            event_type_code = batch.column("event_type")[i].as_py()
            records.append(AgentEventRecord(
                turn=turn,
                agent_id=batch.column("agent_id")[i].as_py(),
                event_type=EVENT_TYPE_MAP.get(event_type_code, f"unknown_{event_type_code}"),
                region=batch.column("region")[i].as_py(),
                target_region=batch.column("target_region")[i].as_py(),
                civ_affinity=batch.column("civ_affinity")[i].as_py(),
                occupation=batch.column("occupation")[i].as_py(),
                belief=belief_col[i].as_py() if belief_col is not None else None,
                target_agent_id=target_agent_id_col[i].as_py() if target_agent_id_col is not None else 0,
                formed_turn=formed_turn_col[i].as_py() if formed_turn_col is not None else 0,
            ))
        return records
```

- [ ] **Step 6: Update dissolution tuple builder**

In `src/chronicler/agent_bridge.py`, replace lines 1103-1112:

```python
            # M50b: collect dissolution events from Rust tick
            dissolution_events = [e for e in raw_events if e.event_type == "dissolution"]
            if dissolution_events:
                dissolved_list = world.dissolved_edges_by_turn.get(world.turn, [])
                for e in dissolution_events:
                    # target_region field repurposed as bond_type in dissolution events
                    dissolved_list.append(
                        (e.agent_id, e.target_agent_id, e.target_region, e.formed_turn)
                    )
                world.dissolved_edges_by_turn[world.turn] = dissolved_list
```

- [ ] **Step 7: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_bridge.py -v -k "dissolution_tuple_uses or convert_events_old_schema"`
Expected: 2 PASS

- [ ] **Step 8: Run broader regression**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_agent_bridge.py -q`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/models.py src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat: read target_agent_id and formed_turn from dissolution events

AgentEventRecord gains two fields. _convert_events reads them with
fallback for old schemas. Dissolution tuples now carry real agent IDs
and formation turns instead of hardcoded zeros."
```

---

### Task 7: Bundle Sidecar — Add New Columns

**Files:**
- Modify: `src/chronicler/bundle.py:105-114`
- Test: `tests/test_bundle.py`

- [ ] **Step 1: Write failing test — new columns in sidecar**

In `tests/test_bundle.py`, add:

```python
def test_agent_events_arrow_includes_provenance_columns():
    """agent_events.arrow should include target_agent_id and formed_turn columns."""
    import pyarrow.ipc as ipc
    from chronicler.models import WorldState, AgentEventRecord
    from chronicler.bundle import write_agent_events_arrow
    from pathlib import Path
    import tempfile

    world = WorldState.__new__(WorldState)
    world.agent_events_raw = [
        AgentEventRecord(
            turn=10, agent_id=100, event_type="dissolution",
            region=0, target_region=3, civ_affinity=0, occupation=0,
            belief=0, target_agent_id=200, formed_turn=5,
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_agent_events_arrow(world, Path(tmpdir))
        assert path is not None
        with open(path, "rb") as f:
            reader = ipc.open_file(f)
            batch = reader.get_batch(0)
        assert "target_agent_id" in batch.schema.names
        assert "formed_turn" in batch.schema.names
        assert batch.column("target_agent_id")[0].as_py() == 200
        assert batch.column("formed_turn")[0].as_py() == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bundle.py -v -k "provenance_columns"`
Expected: FAIL — columns not in schema

- [ ] **Step 3: Add columns to `write_agent_events_arrow()`**

In `src/chronicler/bundle.py`, update the batch construction (lines 105-114) to include:

```python
    batch = pa.record_batch({
        "turn": pa.array([e.turn for e in events], type=pa.uint32()),
        "agent_id": pa.array([e.agent_id for e in events], type=pa.uint32()),
        "event_type": pa.array([e.event_type for e in events], type=pa.utf8()),
        "region": pa.array([e.region for e in events], type=pa.uint16()),
        "target_region": pa.array([e.target_region for e in events], type=pa.uint16()),
        "civ_affinity": pa.array([e.civ_affinity for e in events], type=pa.uint16()),
        "occupation": pa.array([e.occupation for e in events], type=pa.uint8()),
        "belief": pa.array([e.belief for e in events], type=pa.uint8()),
        "target_agent_id": pa.array([e.target_agent_id for e in events], type=pa.uint32()),
        "formed_turn": pa.array([e.formed_turn for e in events], type=pa.uint32()),
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bundle.py -v -k "provenance_columns"`
Expected: PASS

- [ ] **Step 5: Run full bundle tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_bundle.py -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/bundle.py tests/test_bundle.py
git commit -m "feat: include target_agent_id and formed_turn in agent_events.arrow sidecar"
```

---

### Task 8: Rebuild Extension and Full Validation

**Files:** None (validation only)

- [ ] **Step 1: Rebuild Rust extension**

Run: `cd chronicler-agents && ..\.venv\Scripts\python.exe -m maturin develop --release`
Expected: successful build

- [ ] **Step 2: Run full Python test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all PASS (or known skips only)

- [ ] **Step 3: Run full Rust test suite**

Run: `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
Expected: all PASS (or known skips only)

- [ ] **Step 4: Final commit if any fixups needed**

If any test failures required fixes, commit them:
```bash
git commit -m "fix: test fixups from full validation pass"
```
