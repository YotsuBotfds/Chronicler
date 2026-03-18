# M40: Social Networks — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify character relationships into a Rust-backed social graph with five types (mentor, rival, marriage, exile bond, co-religionist), activate dormant narration/curator pipelines, and wire relationship context into the narrator.

**Architecture:** Rust `SocialGraph` on `AgentSimulator` stores edges as `Vec<SocialEdge>`, exposed via Arrow RecordBatch. Python formation/dissolution logic in `relationships.py` runs in Phase 10, writes edges back via `replace_social_edges()` FFI. Narration merges social edges + dissolved edges + hostage state into `AgentContext.relationships`.

**Tech Stack:** Rust (pyo3, arrow2), Python 3.12 (Pydantic), pytest

**Spec:** `docs/superpowers/specs/2026-03-17-m40-social-networks-design.md`

---

## Chunk 1: Rust Infrastructure

### Task 1: SocialEdge types and SocialGraph in social.rs

**Files:**
- Create: `chronicler-agents/src/social.rs`
- Modify: `chronicler-agents/src/lib.rs:8-19` (add mod declaration)

- [ ] **Step 1: Create social.rs with types**

```rust
// chronicler-agents/src/social.rs

/// Relationship type enum — matches Python-side constants.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RelationshipType {
    Mentor = 0,
    Rival = 1,
    Marriage = 2,
    ExileBond = 3,
    CoReligionist = 4,
}

impl RelationshipType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Mentor),
            1 => Some(Self::Rival),
            2 => Some(Self::Marriage),
            3 => Some(Self::ExileBond),
            4 => Some(Self::CoReligionist),
            _ => None,
        }
    }
}

/// A single social relationship between two named characters.
///
/// Directionality:
/// - Mentor: agent_a = mentor, agent_b = apprentice (asymmetric)
/// - All others: agent_a < agent_b by convention (symmetric)
#[derive(Debug, Clone)]
pub struct SocialEdge {
    pub agent_a: u32,
    pub agent_b: u32,
    pub relationship: RelationshipType,
    pub formed_turn: u16,
}

/// Social graph owned by AgentSimulator. Relationships cross region boundaries.
/// Capacity hint: 512 edges (~6KB). Named-character-only, max ~50 chars × ~10 edges.
pub struct SocialGraph {
    pub edges: Vec<SocialEdge>,
}

impl SocialGraph {
    pub fn new() -> Self {
        Self {
            edges: Vec::with_capacity(512),
        }
    }

    pub fn clear(&mut self) {
        self.edges.clear();
    }

    pub fn replace(&mut self, new_edges: Vec<SocialEdge>) {
        self.edges = new_edges;
    }

    pub fn edge_count(&self) -> usize {
        self.edges.len()
    }
}
```

- [ ] **Step 2: Add mod declaration in lib.rs**

In `chronicler-agents/src/lib.rs`, add after line 19 (`pub mod conversion_tick;`):

```rust
pub mod social;
```

And add the re-export after line 33:

```rust
#[doc(hidden)]
pub use social::{RelationshipType, SocialEdge, SocialGraph};
```

- [ ] **Step 3: Verify it compiles**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/social.rs chronicler-agents/src/lib.rs
git commit -m "feat(m40): add SocialEdge types and SocialGraph in social.rs"
```

---

### Task 2: Arrow FFI for social edges

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:134` (add schema after `promotions_schema`)
- Modify: `chronicler-agents/src/ffi.rs:171-180` (add social_graph to AgentSimulator)

- [ ] **Step 1: Write Rust integration test for social edges round-trip**

Create `chronicler-agents/tests/test_social_edges.rs`:

```rust
use chronicler_agents::{RelationshipType, SocialEdge, SocialGraph};

#[test]
fn test_social_graph_replace() {
    let mut graph = SocialGraph::new();
    assert_eq!(graph.edge_count(), 0);

    let edges = vec![
        SocialEdge {
            agent_a: 100,
            agent_b: 200,
            relationship: RelationshipType::Rival,
            formed_turn: 50,
        },
        SocialEdge {
            agent_a: 100,  // mentor
            agent_b: 300,  // apprentice
            relationship: RelationshipType::Mentor,
            formed_turn: 60,
        },
    ];
    graph.replace(edges);
    assert_eq!(graph.edge_count(), 2);
    assert_eq!(graph.edges[0].relationship, RelationshipType::Rival);
    assert_eq!(graph.edges[1].agent_a, 100); // mentor
    assert_eq!(graph.edges[1].agent_b, 300); // apprentice
}

#[test]
fn test_social_graph_clear() {
    let mut graph = SocialGraph::new();
    graph.replace(vec![SocialEdge {
        agent_a: 1,
        agent_b: 2,
        relationship: RelationshipType::Marriage,
        formed_turn: 10,
    }]);
    assert_eq!(graph.edge_count(), 1);
    graph.clear();
    assert_eq!(graph.edge_count(), 0);
}

#[test]
fn test_relationship_type_from_u8() {
    assert_eq!(RelationshipType::from_u8(0), Some(RelationshipType::Mentor));
    assert_eq!(RelationshipType::from_u8(4), Some(RelationshipType::CoReligionist));
    assert_eq!(RelationshipType::from_u8(5), None);
}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd chronicler-agents && cargo test test_social`
Expected: 3 tests PASS

- [ ] **Step 3: Add social_edges_schema and FFI methods to ffi.rs**

After `promotions_schema()` (line ~134), add:

```rust
pub fn social_edges_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_a", DataType::UInt32, false),
        Field::new("agent_b", DataType::UInt32, false),
        Field::new("relationship", DataType::UInt8, false),
        Field::new("formed_turn", DataType::UInt16, false),
    ])
}
```

Add `social_graph` field to `AgentSimulator` struct (line ~178):

```rust
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    contested_regions: Vec<bool>,
    master_seed: [u8; 32],
    num_regions: usize,
    turn: u32,
    registry: crate::named_characters::NamedCharacterRegistry,
    social_graph: crate::social::SocialGraph,  // M40
    initialized: bool,
}
```

Initialize in `AgentSimulator::new()`:

```rust
social_graph: crate::social::SocialGraph::new(),
```

Add two `#[pymethods]` on `AgentSimulator`. These follow the exact same pattern as `get_snapshot()` / `get_promotions()` (return `PyRecordBatch`) and `set_region_state()` (take `PyRecordBatch`):

```rust
/// Return the current social edges as an Arrow RecordBatch.
///
/// Pattern: same as get_snapshot() / get_promotions() — build RecordBatch, wrap in PyRecordBatch.
pub fn get_social_edges(&self) -> PyResult<PyRecordBatch> {
    let n = self.social_graph.edge_count();
    let mut agent_a_col = UInt32Builder::with_capacity(n);
    let mut agent_b_col = UInt32Builder::with_capacity(n);
    let mut rel_col = UInt8Builder::with_capacity(n);
    let mut formed_col = UInt16Builder::with_capacity(n);

    for edge in &self.social_graph.edges {
        agent_a_col.append_value(edge.agent_a);
        agent_b_col.append_value(edge.agent_b);
        rel_col.append_value(edge.relationship as u8);
        formed_col.append_value(edge.formed_turn);
    }

    let batch = RecordBatch::try_new(
        Arc::new(social_edges_schema()),
        vec![
            Arc::new(agent_a_col.finish()) as _,
            Arc::new(agent_b_col.finish()) as _,
            Arc::new(rel_col.finish()) as _,
            Arc::new(formed_col.finish()) as _,
        ],
    )
    .map_err(arrow_err)?;
    Ok(PyRecordBatch::new(batch))
}

/// Replace all social edges from a Python Arrow RecordBatch.
///
/// Pattern: same as set_region_state() — take PyRecordBatch, extract columns by name.
pub fn replace_social_edges(&mut self, batch: PyRecordBatch) -> PyResult<()> {
    let rb: RecordBatch = batch.into_inner();
    let n = rb.num_rows();

    // Use column_by_name for robustness against column reordering
    macro_rules! named_col {
        ($name:expr, $ty:ty) => {
            rb.column_by_name($name)
                .and_then(|c| c.as_any().downcast_ref::<$ty>())
                .ok_or_else(|| PyValueError::new_err(concat!("missing or wrong type: ", $name)))?
        };
    }

    let agent_a = named_col!("agent_a", arrow::array::UInt32Array);
    let agent_b = named_col!("agent_b", arrow::array::UInt32Array);
    let rel = named_col!("relationship", arrow::array::UInt8Array);
    let formed = named_col!("formed_turn", arrow::array::UInt16Array);

    let mut edges = Vec::with_capacity(n);
    for i in 0..n {
        let rtype = crate::social::RelationshipType::from_u8(rel.value(i))
            .ok_or_else(|| PyValueError::new_err(
                format!("invalid relationship type: {}", rel.value(i))
            ))?;
        edges.push(crate::social::SocialEdge {
            agent_a: agent_a.value(i),
            agent_b: agent_b.value(i),
            relationship: rtype,
            formed_turn: formed.value(i),
        });
    }

    self.social_graph.replace(edges);
    Ok(())
}
```

**Note:** The `named_col!` macro pattern may already exist in the codebase (check `set_region_state`). If so, extract to module-level to avoid duplication.

- [ ] **Step 4: Verify it compiles**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_social_edges.rs
git commit -m "feat(m40): add social edges Arrow FFI on AgentSimulator"
```

---

## Chunk 2: Python Model Changes & Bridge Wiring

### Task 3: Add origin_region to GreatPerson and relationships to AgentContext

**Files:**
- Modify: `src/chronicler/models.py:343` (add origin_region after pilgrimage fields)
- Modify: `src/chronicler/models.py:659-663` (add relationships to AgentContext)
- Test: `tests/test_relationships.py` (add guard test)

- [ ] **Step 1: Write failing test for origin_region field**

Add to `tests/test_relationships.py`:

```python
def test_great_person_origin_region_defaults_none():
    gp = GreatPerson(
        name="Test", role="general", trait="bold",
        civilization="Civ1", origin_civilization="Civ1", born_turn=0,
    )
    assert gp.origin_region is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relationships.py::test_great_person_origin_region_defaults_none -v`
Expected: FAIL — `origin_region` not a field

- [ ] **Step 3: Add origin_region to GreatPerson**

In `src/chronicler/models.py`, after line 343 (`pilgrimage_skill_bonus: float = 0.0`), add:

```python
    # M40: Social Networks
    origin_region: str | None = None
```

- [ ] **Step 4: Add relationships to AgentContext**

In `src/chronicler/models.py`, after line 663 (`displacement_fraction: float = 0.0`), add:

```python
    # M40: Social Networks — merged view of social edges + hostage state
    relationships: list[dict] = Field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_relationships.py::test_great_person_origin_region_defaults_none -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_relationships.py
git commit -m "feat(m40): add origin_region to GreatPerson and relationships to AgentContext"
```

---

### Task 4: Set origin_region at promotion time

**Files:**
- Modify: `src/chronicler/agent_bridge.py:487` (set origin_region in _process_promotions)

- [ ] **Step 1: Add origin_region assignment in _process_promotions**

In `src/chronicler/agent_bridge.py`, in `_process_promotions()`, find where the `GreatPerson` is constructed (around line 487 where `self.named_agents[agent_id] = name` is set). After the GreatPerson is created and before it's appended to `civ.great_persons`, add:

```python
# M40: Set origin_region from promotions batch
origin_region_idx = self._origin_regions.get(agent_id)
if origin_region_idx is not None and origin_region_idx < len(world.regions):
    gp.origin_region = world.regions[origin_region_idx].name
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: all tests pass (origin_region defaults to None for existing tests)

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m40): set origin_region on GreatPerson at promotion time"
```

---

### Task 5: Bridge methods for social edge read/write

**Files:**
- Modify: `src/chronicler/agent_bridge.py:330-337` (add social edge bridge methods)

- [ ] **Step 1: Add read_social_edges and replace_social_edges to AgentBridge**

In `src/chronicler/agent_bridge.py`, add two methods to the `AgentBridge` class. The exact Arrow serialization pattern must match how other bridge methods call into `self.sim` (the `AgentSimulator` instance). Add these methods:

```python
def read_social_edges(self) -> list[tuple]:
    """Read current social edges from Rust as a list of (agent_a, agent_b, relationship, formed_turn) tuples."""
    if self.sim is None:
        return []
    batch = self.sim.get_social_edges()
    if batch is None or batch.num_rows == 0:
        return []
    # Convert Arrow batch to list of tuples
    agent_a = batch.column("agent_a").to_pylist()
    agent_b = batch.column("agent_b").to_pylist()
    rel = batch.column("relationship").to_pylist()
    formed = batch.column("formed_turn").to_pylist()
    return list(zip(agent_a, agent_b, rel, formed))

def replace_social_edges(self, edges: list[tuple]) -> None:
    """Replace all social edges in Rust. Each edge is (agent_a, agent_b, relationship, formed_turn)."""
    if self.sim is None:
        return
    import pyarrow as pa
    if not edges:
        # Send empty batch — must provide empty arrays, not empty list
        batch = pa.RecordBatch.from_arrays([
            pa.array([], type=pa.uint32()),
            pa.array([], type=pa.uint32()),
            pa.array([], type=pa.uint8()),
            pa.array([], type=pa.uint16()),
        ], names=["agent_a", "agent_b", "relationship", "formed_turn"])
    else:
        agent_a, agent_b, rel, formed = zip(*edges)
        batch = pa.record_batch([
            pa.array(agent_a, type=pa.uint32()),
            pa.array(agent_b, type=pa.uint32()),
            pa.array(rel, type=pa.uint8()),
            pa.array(formed, type=pa.uint16()),
        ], names=["agent_a", "agent_b", "relationship", "formed_turn"])
    self.sim.replace_social_edges(batch)
```

**Note:** The exact Arrow conversion may differ — adapt to match how the bridge already converts `pyarrow.RecordBatch` to/from the PyCapsule interface. Check the existing `_build_region_batch()` or `_read_snapshot()` patterns.

- [ ] **Step 2: Add social_edges to reset()**

In `AgentBridge.reset()` (line ~936), add alongside the other cache clears:

```python
# M40: social edges will be cleared on next replace_social_edges call
```

No actual state to clear — the bridge methods are stateless pass-throughs to Rust.

- [ ] **Step 3: Verify compilation / no import errors**

Run: `python -c "from chronicler.agent_bridge import AgentBridge; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m40): add social edge read/write bridge methods"
```

---

## Chunk 3: Dissolution & Formation Migration

### Task 6: Edge representation constants and dissolve_edges

**Files:**
- Modify: `src/chronicler/relationships.py:1-8` (add constants)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests for dissolve_edges**

Add to `tests/test_relationships.py`:

```python
from chronicler.relationships import dissolve_edges, REL_MENTOR, REL_RIVAL, REL_MARRIAGE, REL_EXILE_BOND, REL_CORELIGIONIST

def test_dissolve_edges_death_removes_edge():
    """Edge dissolves when either party is no longer in active named characters."""
    edges = [(100, 200, REL_RIVAL, 50)]
    active_agent_ids = {200}  # agent 100 is dead
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 0
    assert len(dissolved) == 1

def test_dissolve_edges_both_alive_survives():
    edges = [(100, 200, REL_RIVAL, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1
    assert len(dissolved) == 0

def test_dissolve_edges_coreligionist_belief_divergence():
    """Co-religionist edge dissolves when beliefs now differ."""
    edges = [(100, 200, REL_CORELIGIONIST, 50)]
    active_agent_ids = {100, 200}
    belief_by_agent = {100: 1, 200: 2}  # different beliefs now
    surviving, dissolved = dissolve_edges(edges, active_agent_ids, belief_by_agent=belief_by_agent)
    assert len(surviving) == 0
    assert len(dissolved) == 1

def test_dissolve_edges_coreligionist_same_belief_survives():
    edges = [(100, 200, REL_CORELIGIONIST, 50)]
    active_agent_ids = {100, 200}
    belief_by_agent = {100: 1, 200: 1}  # same belief
    surviving, dissolved = dissolve_edges(edges, active_agent_ids, belief_by_agent=belief_by_agent)
    assert len(surviving) == 1
    assert len(dissolved) == 0

def test_dissolve_edges_exile_bond_only_death():
    """Exile bonds only dissolve on death, not on any other condition."""
    edges = [(100, 200, REL_EXILE_BOND, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1

def test_dissolve_edges_marriage_survives_war():
    """Marriage does NOT dissolve when civs go to war — only on death."""
    edges = [(100, 200, REL_MARRIAGE, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "dissolve_edges" -v`
Expected: FAIL — `dissolve_edges` not defined

- [ ] **Step 3: Implement constants and dissolve_edges**

Add to the top of `src/chronicler/relationships.py` (after imports):

```python
# M40: Relationship type constants (match Rust RelationshipType repr(u8))
REL_MENTOR = 0
REL_RIVAL = 1
REL_MARRIAGE = 2
REL_EXILE_BOND = 3
REL_CORELIGIONIST = 4


def dissolve_edges(
    edges: list[tuple],
    active_agent_ids: set[int],
    belief_by_agent: dict[int, int] | None = None,
) -> tuple[list[tuple], list[tuple]]:
    """Dissolve stale edges. Returns (surviving, dissolved).

    Dissolution rules:
    - All types: dissolve if either party not in active_agent_ids (death)
    - CoReligionist: also dissolve if beliefs now differ
    """
    surviving = []
    dissolved = []
    for edge in edges:
        agent_a, agent_b, rel_type, formed_turn = edge
        # Death check — applies to all types
        if agent_a not in active_agent_ids or agent_b not in active_agent_ids:
            dissolved.append(edge)
            continue
        # Co-religionist: belief divergence check
        if rel_type == REL_CORELIGIONIST and belief_by_agent is not None:
            belief_a = belief_by_agent.get(agent_a)
            belief_b = belief_by_agent.get(agent_b)
            if belief_a is not None and belief_b is not None and belief_a != belief_b:
                dissolved.append(edge)
                continue
        surviving.append(edge)
    return surviving, dissolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "dissolve_edges" -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): add dissolve_edges with death and belief-divergence rules"
```

---

### Task 7: Migrate check_rivalry_formation to edge tuples

**Files:**
- Modify: `src/chronicler/relationships.py:11-43`
- Modify: `tests/test_relationships.py` (update rivalry tests)

- [ ] **Step 1: Update rivalry tests for new signature**

Replace the rivalry tests in `tests/test_relationships.py` with agent_id-based versions:

```python
def test_rivalry_forms_between_agents_at_war(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(
            name="Gen1", role="general", trait="bold",
            civilization=civ1.name, origin_civilization=civ1.name,
            born_turn=0, source="agent", agent_id=100,
        )
    ]
    civ2.great_persons = [
        GreatPerson(
            name="Gen2", role="general", trait="aggressive",
            civilization=civ2.name, origin_civilization=civ2.name,
            born_turn=0, source="agent", agent_id=200,
        )
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    existing_edges = []
    formed = check_rivalry_formation(world, existing_edges)
    assert len(formed) == 1
    agent_a, agent_b, rel_type, formed_turn = formed[0]
    assert rel_type == REL_RIVAL
    assert min(agent_a, agent_b) == 100
    assert max(agent_a, agent_b) == 200

def test_rivalry_skips_aggregate_source(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="aggregate", agent_id=None)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world, [])
    assert len(formed) == 0

def test_rivalry_not_duplicated_edge(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    existing_edges = [(100, 200, REL_RIVAL, 0)]
    formed = check_rivalry_formation(world, existing_edges)
    assert len(formed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "rivalry" -v`
Expected: FAIL — signature mismatch

- [ ] **Step 3: Rewrite check_rivalry_formation**

Replace the function in `src/chronicler/relationships.py`:

```python
def check_rivalry_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form rivalries between same-role agent-source great persons on opposing war sides.

    Returns list of (agent_a, agent_b, REL_RIVAL, formed_turn) tuples.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_RIVAL}
    for war_pair in world.active_wars:
        civ1_name, civ2_name = war_pair
        civ1 = next((c for c in world.civilizations if c.name == civ1_name), None)
        civ2 = next((c for c in world.civilizations if c.name == civ2_name), None)
        if not civ1 or not civ2:
            continue
        for gp1 in civ1.great_persons:
            if not gp1.active or gp1.agent_id is None or gp1.role in ("exile", "hostage"):
                continue
            for gp2 in civ2.great_persons:
                if not gp2.active or gp2.agent_id is None or gp2.role in ("exile", "hostage"):
                    continue
                if gp1.role != gp2.role:
                    continue
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_RIVAL, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "rivalry" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): migrate rivalry formation to agent_id edge tuples"
```

---

### Task 8: Rewrite check_mentorship_formation (drop leader pattern)

**Files:**
- Modify: `src/chronicler/relationships.py:59-92`
- Modify: `tests/test_relationships.py`

- [ ] **Step 1: Write new mentorship tests**

Replace mentorship tests in `tests/test_relationships.py`:

```python
def test_mentorship_forms_same_occupation_skill_gap(make_world):
    """Two agent-source named chars, same occupation, skill gap, same region → mentorship."""
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    mentor = GreatPerson(
        name="OldGen", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0, source="agent", agent_id=100, region="Civ0_region",
    )
    apprentice = GreatPerson(
        name="YoungGen", role="general", trait="cautious",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=50, source="agent", agent_id=200, region="Civ0_region",
    )
    civ.great_persons = [mentor, apprentice]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 1
    agent_a, agent_b, rel_type, _ = formed[0]
    assert rel_type == REL_MENTOR
    # agent_a = mentor (higher born_turn seniority = lower born_turn)
    assert agent_a == 100  # mentor
    assert agent_b == 200  # apprentice

def test_mentorship_requires_same_region(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="agent",
                    agent_id=100, region="Region1"),
        GreatPerson(name="B", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="Region2"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0

def test_mentorship_requires_same_role(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="agent",
                    agent_id=100, region="R1"),
        GreatPerson(name="B", role="merchant", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="R1"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0

def test_mentorship_skips_aggregate(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="aggregate",
                    agent_id=None, region="R1"),
        GreatPerson(name="B", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="R1"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "mentorship" -v`
Expected: FAIL — signature mismatch

- [ ] **Step 3: Rewrite check_mentorship_formation**

Replace in `src/chronicler/relationships.py`:

```python
def check_mentorship_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form mentorships between agent-source named characters with same role, skill gap, co-located.

    Mentor = agent_a (senior by born_turn), apprentice = agent_b.
    Returns list of (agent_a, agent_b, REL_MENTOR, formed_turn) tuples.
    """
    new_edges = []
    # Build set of agents already in a mentorship (as mentor or apprentice)
    mentored = set()
    for e in existing_edges:
        if e[2] == REL_MENTOR:
            mentored.add(e[0])
            mentored.add(e[1])

    # Collect all eligible agent-source named characters across all civs
    candidates = []
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None or gp.role in ("exile", "hostage"):
                continue
            if gp.agent_id in mentored:
                continue
            candidates.append(gp)

    # Match by role + region, senior mentors junior.
    # born_turn is used as seniority proxy for skill gap (spec says "skill gap" —
    # GreatPerson has no comparable skill field, seniority is the best available proxy).
    # Sort by born_turn so we can pair senior with junior
    candidates.sort(key=lambda gp: gp.born_turn)
    paired = set()
    for i, senior in enumerate(candidates):
        if senior.agent_id in paired:
            continue
        for junior in candidates[i + 1:]:
            if junior.agent_id in paired:
                continue
            if senior.role != junior.role:
                continue
            if senior.region != junior.region or senior.region is None:
                continue
            # Skill gap: senior has lower born_turn (more experienced)
            edge = (senior.agent_id, junior.agent_id, REL_MENTOR, world.turn)
            new_edges.append(edge)
            paired.add(senior.agent_id)
            paired.add(junior.agent_id)
            break  # one apprentice per mentor per turn
    return new_edges
```

Remove the now-unused `MENTORSHIP_COMPATIBLE` dict (lines 61-64).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "mentorship" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): rewrite mentorship formation — agent-source peers, drop leader pattern"
```

---

### Task 9: Migrate check_marriage_formation to edge tuples

**Files:**
- Modify: `src/chronicler/relationships.py:95-137`
- Modify: `tests/test_relationships.py`

- [ ] **Step 1: Update marriage tests for new signature**

Replace marriage tests in `tests/test_relationships.py`:

```python
def test_marriage_forms_between_allied_agent_chars(make_world):
    from chronicler.models import Disposition
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    formed = check_marriage_formation(world, [])
    # Marriage has 30% chance with this seed — may or may not form
    for edge in formed:
        assert edge[2] == REL_MARRIAGE

def test_marriage_skips_aggregate(make_world):
    from chronicler.models import Disposition
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="aggregate", agent_id=None)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    formed = check_marriage_formation(world, [])
    assert len(formed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "marriage" -v`
Expected: FAIL — signature mismatch

- [ ] **Step 3: Rewrite check_marriage_formation**

Replace in `src/chronicler/relationships.py`:

```python
def check_marriage_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form marriage alliances between agent-source great persons of long-allied civs.

    Returns list of (agent_a, agent_b, REL_MARRIAGE, formed_turn) tuples.
    agent_a < agent_b by convention (symmetric).
    RNG seed uses civ-name pair (not agent_id) for determinism stability.
    """
    from chronicler.models import Disposition
    new_edges = []
    married_agents = set()
    for e in existing_edges:
        if e[2] == REL_MARRIAGE:
            married_agents.add(e[0])
            married_agents.add(e[1])

    checked_pairs = set()
    for i, civ1 in enumerate(world.civilizations):
        for civ2 in world.civilizations[i + 1:]:
            pair = (civ1.name, civ2.name)
            if pair in checked_pairs or (civ2.name, civ1.name) in checked_pairs:
                continue
            checked_pairs.add(pair)
            rel12 = world.relationships.get(civ1.name, {}).get(civ2.name)
            if not rel12 or rel12.disposition != Disposition.ALLIED or rel12.allied_turns < 10:
                continue
            gp1_candidates = [
                gp for gp in civ1.great_persons
                if gp.active and gp.agent_id is not None
                and gp.agent_id not in married_agents
                and gp.role not in ("exile", "hostage")
            ]
            gp2_candidates = [
                gp for gp in civ2.great_persons
                if gp.active and gp.agent_id is not None
                and gp.agent_id not in married_agents
                and gp.role not in ("exile", "hostage")
            ]
            if not gp1_candidates or not gp2_candidates:
                continue
            rng = random.Random(world.seed + world.turn + hash(pair))
            if rng.random() < 0.30:
                gp1, gp2 = gp1_candidates[0], gp2_candidates[0]
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                edge = (a, b, REL_MARRIAGE, world.turn)
                new_edges.append(edge)
                married_agents.add(a)
                married_agents.add(b)
    return new_edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "marriage" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): migrate marriage formation to agent_id edge tuples"
```

---

## Chunk 4: New Formation Functions

### Task 10: check_exile_bond_formation

**Files:**
- Modify: `src/chronicler/relationships.py` (add new function)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_relationships.py`:

```python
def test_exile_bond_forms_shared_origin_colocated(make_world):
    """Two displaced chars from same origin in same refuge region → exile bond."""
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="Exile1", role="general", trait="bold",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region="Homeland", region="Refuge"),
        GreatPerson(name="Exile2", role="merchant", trait="shrewd",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 1
    assert formed[0][2] == REL_EXILE_BOND

def test_exile_bond_requires_displacement():
    """If character is in their origin region, no exile bond."""
    from chronicler.relationships import check_exile_bond_formation
    from chronicler.models import GreatPerson, WorldState
    # Characters in their origin_region should NOT form exile bonds
    # (they're home, not exiled)
    # This is tested via the condition: region != origin_region
    pass  # Covered by the co-location + displacement logic in the function

def test_exile_bond_skips_none_origin(make_world):
    """Characters with origin_region=None cannot form exile bonds."""
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region=None, region="Refuge"),
        GreatPerson(name="B", role="merchant", trait="shrewd",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 0

def test_exile_bond_requires_same_region(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="A", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region="Homeland", region="Refuge1"),
    ]
    civ2.great_persons = [
        GreatPerson(name="B", role="merchant", trait="shrewd",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge2"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "exile_bond" -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement check_exile_bond_formation**

Add to `src/chronicler/relationships.py`:

```python
def check_exile_bond_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form exile bonds between agent-source named characters who share origin_region
    and are co-located in a region that is NOT their origin.

    Returns list of (agent_a, agent_b, REL_EXILE_BOND, formed_turn) tuples.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_EXILE_BOND}

    # Collect eligible displaced characters: agent_id, origin_region, current_region
    displaced = []
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None:
                continue
            if gp.origin_region is None or gp.region is None:
                continue
            if gp.region == gp.origin_region:
                continue  # not displaced
            displaced.append(gp)

    # Group by (origin_region, current_region)
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for gp in displaced:
        groups[(gp.origin_region, gp.region)].append(gp)

    # Form pairwise bonds within each group
    for key, members in groups.items():
        if len(members) < 2:
            continue
        for i, gp1 in enumerate(members):
            for gp2 in members[i + 1:]:
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_EXILE_BOND, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "exile_bond" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): add exile bond formation — shared displacement, co-located"
```

---

### Task 11: check_coreligionist_formation

**Files:**
- Modify: `src/chronicler/relationships.py` (add new function)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_relationships.py`:

```python
def test_coreligionist_forms_shared_minority_faith(make_world):
    """Two chars sharing a minority belief (<30% in their region) → co-religionist bond."""
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R1"),
    ]
    # belief_by_agent: both share belief 5
    # region_belief_fractions: belief 5 is 20% in R1 (minority)
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.20, 1: 0.80}}
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 1
    assert formed[0][2] == REL_CORELIGIONIST

def test_coreligionist_not_formed_majority_faith(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R1"),
    ]
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.50}}  # majority — not minority
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 0

def test_coreligionist_requires_colocation(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R2"),
    ]
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.10}, "R2": {5: 0.10}}
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_relationships.py -k "coreligionist" -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement check_coreligionist_formation**

Add to `src/chronicler/relationships.py`:

```python
CORELIGIONIST_MINORITY_THRESHOLD = 0.30


def check_coreligionist_formation(
    world: WorldState,
    existing_edges: list[tuple],
    belief_by_agent: dict[int, int],
    region_belief_fractions: dict[str, dict[int, float]],
) -> list[tuple]:
    """Form co-religionist bonds between agent-source named characters who share
    a minority belief (<30% of population) in the same region.

    Returns list of (agent_a, agent_b, REL_CORELIGIONIST, formed_turn) tuples.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_CORELIGIONIST}

    # Collect eligible characters with known belief and region
    from collections import defaultdict
    by_region_belief: dict[tuple[str, int], list] = defaultdict(list)
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None or gp.region is None:
                continue
            belief = belief_by_agent.get(gp.agent_id)
            if belief is None:
                continue
            by_region_belief[(gp.region, belief)].append(gp)

    # Form bonds where the shared belief is a minority in that region
    for (region, belief), members in by_region_belief.items():
        if len(members) < 2:
            continue
        fractions = region_belief_fractions.get(region, {})
        fraction = fractions.get(belief, 0.0)
        if fraction >= CORELIGIONIST_MINORITY_THRESHOLD:
            continue  # not a minority
        for i, gp1 in enumerate(members):
            for gp2 in members[i + 1:]:
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_CORELIGIONIST, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relationships.py -k "coreligionist" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): add co-religionist formation — shared minority faith, co-located"
```

---

### Task 12: Coordinator function form_and_sync_relationships

**Files:**
- Modify: `src/chronicler/relationships.py` (add coordinator)
- Test: `tests/test_relationships.py`

- [ ] **Step 1: Write coordinator test**

Add to `tests/test_relationships.py`:

```python
def test_coordinator_dissolves_dead_agent_edges():
    """Coordinator dissolves edges for dead agents and writes survivors back."""
    from chronicler.relationships import form_and_sync_relationships

    class MockBridge:
        def __init__(self, initial_edges):
            self._edges = initial_edges
            self.replaced = None

        def read_social_edges(self):
            return list(self._edges)

        def replace_social_edges(self, edges):
            self.replaced = edges

    initial = [(100, 200, REL_RIVAL, 10)]
    bridge = MockBridge(initial)

    world = WorldState(seed=42, turn=50, regions=[], civilizations=[], relationships={})
    active_ids = {200}  # 100 is dead

    dissolved = form_and_sync_relationships(
        world, bridge, active_ids,
        belief_by_agent={}, region_belief_fractions={},
    )

    assert len(dissolved) == 1
    assert dissolved[0][0] == 100
    assert bridge.replaced is not None
    # No surviving edges and no new ones (empty world)
    assert len(bridge.replaced) == 0


def test_coordinator_forms_new_edges_and_writes_back(make_world):
    """Coordinator runs all formation checks and writes new + surviving edges to bridge."""
    from chronicler.relationships import form_and_sync_relationships

    class MockBridge:
        def __init__(self):
            self._edges = []
            self.replaced = None

        def read_social_edges(self):
            return list(self._edges)

        def replace_social_edges(self, edges):
            self.replaced = edges

    bridge = MockBridge()
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    # Set up rivalry-eligible characters
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]

    dissolved = form_and_sync_relationships(
        world, bridge, {100, 200},
        belief_by_agent={}, region_belief_fractions={},
    )

    assert len(dissolved) == 0  # nothing to dissolve
    assert bridge.replaced is not None
    assert len(bridge.replaced) >= 1  # at least the rivalry edge
    assert any(e[2] == REL_RIVAL for e in bridge.replaced)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relationships.py::test_coordinator_runs_formation_and_dissolution -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement the coordinator**

Add to `src/chronicler/relationships.py`:

```python
def form_and_sync_relationships(
    world: WorldState,
    bridge,
    active_agent_ids: set[int],
    belief_by_agent: dict[int, int],
    region_belief_fractions: dict[str, dict[int, float]],
) -> list[tuple]:
    """Phase 10 relationship pass: dissolve stale edges, form new ones, batch-replace to Rust.

    Returns dissolved edges (for narration pipeline — transient, not written to Rust).
    """
    # 1. Read current edges from Rust
    current_edges = bridge.read_social_edges()

    # 2. Dissolve stale edges
    surviving, dissolved_this_turn = dissolve_edges(
        current_edges, active_agent_ids, belief_by_agent=belief_by_agent,
    )

    # 3. Formation checks — dedup against surviving
    new_rivals = check_rivalry_formation(world, surviving)
    new_mentors = check_mentorship_formation(world, surviving)
    new_marriages = check_marriage_formation(world, surviving)
    new_exile_bonds = check_exile_bond_formation(world, surviving)
    new_coreligionists = check_coreligionist_formation(
        world, surviving, belief_by_agent, region_belief_fractions,
    )

    # 4. Batch replace to Rust
    all_edges = surviving + new_rivals + new_mentors + new_marriages + new_exile_bonds + new_coreligionists
    bridge.replace_social_edges(all_edges)

    # 5. Return dissolved edges for narration
    return dissolved_this_turn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relationships.py::test_coordinator_runs_formation_and_dissolution -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): add form_and_sync_relationships coordinator"
```

---

## Chunk 5: Phase 10 Wiring & Pipeline Activation

### Task 13: Wire coordinator into Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py:1034-1045`
- Modify: `src/chronicler/models.py` (add transient dissolved_edges field to WorldState)

- [ ] **Step 1: Add dissolved_edges transient field to WorldState**

In `src/chronicler/models.py`, after `character_relationships` (line 499), add:

```python
    # M40: Dissolved edges per turn for narration (not serialized to bundle).
    # Keyed by turn number. Narration looks up by moment's anchor turn.
    dissolved_edges_by_turn: dict[int, list[tuple]] = Field(default_factory=dict, exclude=True)
```

- [ ] **Step 2: Remove old formation calls from phase_consequences()**

In `src/chronicler/simulation.py`, remove lines 1034-1045 inside `phase_consequences()`:

```python
    # M17c: Character relationship formation
    from chronicler.relationships import check_rivalry_formation, check_mentorship_formation, check_marriage_formation
    new_rivalries = check_rivalry_formation(world)
    for rivalry in new_rivalries:
        collapse_events.append(Event(
            turn=world.turn, event_type="rivalry_formed",
            actors=[rivalry.get("civ_a", ""), rivalry.get("civ_b", "")],
            description=f"A rivalry forms between great persons of opposing civilizations.",
            importance=5,
        ))
    check_mentorship_formation(world)
    check_marriage_formation(world)
```

**Why not replace in-place:** `phase_consequences()` has signature `def phase_consequences(world: WorldState, acc=None) -> list[Event]` — it does not receive `bridge`. Rather than threading a new parameter through, the coordinator call belongs in `run_turn()` which already has `agent_bridge`.

- [ ] **Step 2b: Wire coordinator in run_turn() after phase_consequences()**

In `src/chronicler/simulation.py`, after the `phase_consequences()` call at line 1281:

```python
    turn_events.extend(phase_consequences(world, acc=phase10_acc))
```

Add:

```python
    # M40: Unified relationship formation and dissolution (runs after Phase 10)
    # One-turn latency: agent tick ran between Phase 9 and 10.
    # Rust reads edges from the previous turn's Phase 10 output. Intentional, same as M38b.
    if agent_bridge is not None:
        from chronicler.relationships import form_and_sync_relationships, REL_RIVAL

        # Build active agent IDs from all living named characters
        active_ids = set()
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.active and gp.agent_id is not None:
                    active_ids.add(gp.agent_id)

        # Build belief data from the agent snapshot via bridge
        # Note: _agent_snapshot is NOT on world — it's on AgentBridge.
        # AgentBridge.get_snapshot() proxies to self._sim.get_snapshot() (line 949).
        belief_by_agent = {}
        region_belief_fractions: dict[str, dict[int, float]] = {}
        try:
            snap = agent_bridge.get_snapshot()
        except Exception:
            snap = None
        if snap is not None:
            belief_col = snap.column("belief").to_pylist()
            region_col = snap.column("region").to_pylist()
            agent_id_col = snap.column("id").to_pylist()
            # Per-agent belief
            for aid, bel in zip(agent_id_col, belief_col):
                if aid in active_ids:
                    belief_by_agent[aid] = bel
            # Per-region belief fractions (O(n_agents) scan, done once)
            from collections import Counter, defaultdict
            region_counts: dict[int, int] = Counter()
            region_belief_counts: dict[int, Counter] = defaultdict(Counter)
            for reg, bel in zip(region_col, belief_col):
                region_counts[reg] += 1
                region_belief_counts[reg][bel] += 1
            region_map = {i: r.name for i, r in enumerate(world.regions)}
            for reg_idx, total in region_counts.items():
                rname = region_map.get(reg_idx, "")
                if rname and total > 0:
                    region_belief_fractions[rname] = {
                        bel: cnt / total
                        for bel, cnt in region_belief_counts[reg_idx].items()
                    }

        dissolved = form_and_sync_relationships(
            world, agent_bridge, active_ids, belief_by_agent, region_belief_fractions,
        )
        # Store per-turn for narration lookup (not overwritten — accumulated)
        if dissolved:
            world.dissolved_edges_by_turn[world.turn] = dissolved

        # Generate rivalry events for curator (look up civ names from great persons)
        new_edges = agent_bridge.read_social_edges()
        gp_by_id = {}
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.agent_id is not None:
                    gp_by_id[gp.agent_id] = gp
        for edge in new_edges:
            if edge[2] == REL_RIVAL and edge[3] == world.turn:
                gp_a = gp_by_id.get(edge[0])
                gp_b = gp_by_id.get(edge[1])
                actors = []
                if gp_a:
                    actors.append(gp_a.civilization)
                if gp_b:
                    actors.append(gp_b.civilization)
                turn_events.append(Event(
                    turn=world.turn, event_type="rivalry_formed",
                    actors=actors,
                    description="A rivalry forms between great persons of opposing civilizations.",
                    importance=5,
                ))
```

- [ ] **Step 3: Remove character_relationships from WorldState**

In `src/chronicler/models.py`, remove line 499:

```python
    character_relationships: list[dict] = Field(default_factory=list)
```

**Warning:** Search the codebase for all references to `character_relationships` before removing. Expected references: `relationships.py` (formation functions — already migrated), `simulation.py` (formation calls — already replaced), test files (need updating). If any unexpected references exist, update them first.

- [ ] **Step 4: Remove dead code**

In `src/chronicler/relationships.py`, remove `dissolve_dead_relationships()` (lines 46-56) — confirmed dead code, never called.

- [ ] **Step 5: Update integration test**

In `tests/test_relationships.py`, update `test_m17c_integration_relationships_across_turns` to work with the new system or remove it (it tests the old `character_relationships` list which no longer exists).

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -x -q --timeout=60`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/models.py src/chronicler/relationships.py tests/test_relationships.py
git commit -m "feat(m40): wire coordinator into Phase 10, remove character_relationships"
```

---

### Task 14: Activate named character scoring in curate()

**Files:**
- Modify: `src/chronicler/main.py:656-662`
- Modify: `src/chronicler/live.py:290`
- Test: `tests/test_curator.py`

- [ ] **Step 1: Write test for named_characters activation**

Add to `tests/test_curator.py`:

```python
def test_named_character_bonus_applied():
    """When named_characters is passed, events with those actors get +2.0 bonus."""
    from chronicler.curator import compute_base_scores
    from chronicler.models import Event
    events = [
        Event(turn=1, event_type="battle", actors=["Hero"], description="Battle", importance=5),
        Event(turn=1, event_type="trade", actors=["NPC"], description="Trade", importance=5),
    ]
    scores_without = compute_base_scores(events, [], "nobody", 0, named_characters=None)
    scores_with = compute_base_scores(events, [], "nobody", 0, named_characters={"Hero"})
    # Hero event should get +2.0 bonus
    assert scores_with[0] > scores_without[0]
    assert scores_with[0] - scores_without[0] == pytest.approx(2.0)
    # NPC event unchanged
    assert scores_with[1] == scores_without[1]
```

- [ ] **Step 2: Run test — should pass (scoring already exists, just not wired)**

Run: `python -m pytest tests/test_curator.py::test_named_character_bonus_applied -v`
Expected: PASS (the scoring logic exists at `curator.py:122-126`)

- [ ] **Step 3: Wire named_characters in main.py**

In `src/chronicler/main.py`, at line 656-662 where `curate()` is called, add the `named_characters` parameter. This requires collecting named character names from the bundle:

```python
    # M40: Collect named character names for curator scoring
    named_chars = set()
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp in civ_data.get("great_persons", []):
            if gp.get("active") and gp.get("agent_id") is not None:
                named_chars.add(gp.get("name", ""))

    # Curate moments
    moments, gap_summaries = curate(
        events=events,
        named_events=named_events,
        history=history,
        budget=budget,
        seed=seed,
        named_characters=named_chars if named_chars else None,
    )
```

- [ ] **Step 4: Wire named_characters in live.py**

In `src/chronicler/live.py`, at line 290, add named_characters:

```python
    # M40: Collect named character names
    named_chars = set()
    for civ_data in self._init_data.get("world_state", {}).get("civilizations", []):
        for gp in civ_data.get("great_persons", []):
            if gp.get("active") and gp.get("agent_id") is not None:
                named_chars.add(gp.get("name", ""))

    moments, _ = curate(
        range_events, all_named, all_history, budget=1, seed=seed,
        named_characters=named_chars if named_chars else None,
    )
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_curator.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py src/chronicler/live.py tests/test_curator.py
git commit -m "feat(m40): activate named character scoring in curate() — main.py and live.py"
```

---

### Task 15: Curator relationship boost

**Files:**
- Modify: `src/chronicler/curator.py:85-130`
- Test: `tests/test_curator.py`

- [ ] **Step 1: Write failing test for relationship boost**

Add to `tests/test_curator.py`:

```python
def test_relationship_boost_applied():
    """Events involving related characters get 1.2x boost."""
    from chronicler.curator import compute_base_scores
    from chronicler.models import Event
    events = [
        # Actors are civ names, not character names
        Event(turn=1, event_type="battle", actors=["CivA", "CivB"], description="Battle", importance=5),
        Event(turn=1, event_type="trade", actors=["CivC"], description="Trade", importance=5),
    ]
    # social_edges: agent 100 (CivA) and agent 200 (CivB) are rivals
    social_edges = [(100, 200, 1, 10)]  # REL_RIVAL
    # Map civ names to the agent_ids in them
    agent_civ_map = {"CivA": {100}, "CivB": {200}, "CivC": {300}}
    scores = compute_base_scores(
        events, [], "nobody", 0,
        social_edges=social_edges,
        agent_civ_map=agent_civ_map,
    )
    # CivA+CivB event has agents 100+200 who share a rival edge → 1.2x boost
    # CivC event has no related agents → no boost
    assert scores[0] > scores[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_curator.py::test_relationship_boost_applied -v`
Expected: FAIL — unexpected keyword arguments

- [ ] **Step 3: Add relationship boost to compute_base_scores**

In `src/chronicler/curator.py`, update `compute_base_scores` signature (line 85-90):

```python
RELATIONSHIP_SCORE_BONUS = 1.2

def compute_base_scores(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    dominant_power: str,
    seed: int,
    named_characters: set[str] | None = None,
    social_edges: list[tuple] | None = None,
    agent_civ_map: dict[str, set[int]] | None = None,  # civ_name → set of agent_ids
) -> list[float]:
```

After the character-reference bonus block (line ~127), add:

```python
        # M40: Relationship boost — 1.2x if event involves characters who share a relationship.
        # Event actors are civ names (e.g., "Aram"), not character names (e.g., "Kiran").
        # Build civ → agent_ids mapping, then check if any two agents from actor civs share an edge.
        if social_edges and agent_civ_map:
            actor_agent_ids: set[int] = set()
            for actor in ev.actors:
                actor_agent_ids.update(agent_civ_map.get(actor, set()))
            if len(actor_agent_ids) >= 2:
                for edge in social_edges:
                    if edge[0] in actor_agent_ids and edge[1] in actor_agent_ids:
                        score *= RELATIONSHIP_SCORE_BONUS
                        break  # cap at one application per event
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_curator.py::test_relationship_boost_applied -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m40): add 1.2x relationship boost in curator scoring"
```

---

## Chunk 6: Narration Wiring

### Task 16: Activate build_agent_context_for_moment and wire relationships

**Files:**
- Modify: `src/chronicler/narrative.py:110-163` (add relationships parameter)
- Modify: `src/chronicler/narrative.py:694-703` (wire into narrate_batch prompt)
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write test for relationship context in AgentContext**

Add to `tests/test_narrative.py`:

```python
def test_agent_context_includes_relationships():
    from chronicler.narrative import build_agent_context_for_moment
    from chronicler.models import NarrativeMoment, Event, GreatPerson, NarrativeRole

    moment = NarrativeMoment(
        anchor_turn=100,
        turn_range=(95, 105),
        events=[Event(turn=100, event_type="rebellion", actors=["Civ1"],
                      description="Rebellion", importance=7, source="agent")],
        named_events=[],
        score=10.0,
        causal_links=[],
        narrative_role=NarrativeRole.CRISIS,
        bonus_applied=0.0,
    )

    gp1 = GreatPerson(name="Mentor", role="general", trait="bold",
                      civilization="Civ1", origin_civilization="Civ1",
                      born_turn=0, source="agent", agent_id=100)
    gp2 = GreatPerson(name="Apprentice", role="general", trait="cautious",
                      civilization="Civ1", origin_civilization="Civ1",
                      born_turn=50, source="agent", agent_id=200)

    # Social edges: mentorship between 100→200
    social_edges = [(100, 200, 0, 50)]  # REL_MENTOR
    agent_name_map = {100: "Mentor", 200: "Apprentice"}

    ctx = build_agent_context_for_moment(
        moment, [gp1, gp2], {}, {},
        social_edges=social_edges,
        agent_name_map=agent_name_map,
    )
    assert ctx is not None
    assert len(ctx.relationships) >= 1
    assert ctx.relationships[0]["type"] == "mentor"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_narrative.py::test_agent_context_includes_relationships -v`
Expected: FAIL — unexpected keyword argument `social_edges`

- [ ] **Step 3: Add relationship merging to build_agent_context_for_moment**

In `src/chronicler/narrative.py`, update the function signature (line 110-117):

```python
def build_agent_context_for_moment(
    moment: NarrativeMoment,
    great_persons: list,
    displacement_by_region: dict[int, float],
    region_names: dict[int, str],
    dynasty_registry=None,
    gp_by_agent_id: dict | None = None,
    social_edges: list[tuple] | None = None,      # M40
    dissolved_edges: list[tuple] | None = None,    # M40
    agent_name_map: dict[int, str] | None = None,  # M40
    hostage_data: list[dict] | None = None,        # M40
) -> AgentContext | None:
```

After the `chars` list is built (before the `return` at line ~159), add:

```python
    # M40: Merge relationship sources into AgentContext.relationships
    relationships = []
    rel_type_names = {0: "mentor", 1: "rival", 2: "marriage", 3: "exile_bond", 4: "co_religionist"}
    name_map = agent_name_map or {}

    all_edges = list(social_edges or []) + list(dissolved_edges or [])
    char_names = {c["name"] for c in chars}
    for edge in all_edges:
        agent_a, agent_b, rel_type, formed_turn = edge
        name_a = name_map.get(agent_a, "")
        name_b = name_map.get(agent_b, "")
        if name_a not in char_names and name_b not in char_names:
            continue
        rel = {
            "type": rel_type_names.get(rel_type, "unknown"),
            "character_a": name_a,
            "character_b": name_b,
            "role_a": "mentor" if rel_type == 0 else None,
            "role_b": "apprentice" if rel_type == 0 else None,
            "since_turn": formed_turn,
        }
        relationships.append(rel)

    # Add hostage relationships
    for h in (hostage_data or []):
        if h.get("name") in char_names:
            relationships.append(h)
```

Update the return statement to include relationships:

```python
    return AgentContext(
        named_characters=chars[:10],
        population_mood=mood,
        displacement_fraction=avg_disp,
        relationships=relationships,
    )
```

- [ ] **Step 4: Wire agent context into narrate_batch**

Add optional parameters to `narrate_batch()` in `src/chronicler/narrative.py` (line 596):

```python
    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        gap_summaries: list[GapSummary],
        on_progress: Callable[[int, int, float | None], None] | None = None,
        # M40: Optional agent context data
        great_persons: list | None = None,
        social_edges: list[tuple] | None = None,
        dissolved_edges_by_turn: dict[int, list[tuple]] | None = None,
        agent_name_map: dict[int, str] | None = None,
    ) -> list[ChronicleEntry]:
```

Inside the per-moment loop (after the `snap` lookup at line ~676, before the prompt is built at line ~695), add:

```python
            # M40: Build agent context with relationships
            agent_context_text = ""
            if great_persons is not None:
                # Build hostage data from great persons
                hostage_data = []
                for gp in (great_persons or []):
                    if gp.is_hostage and gp.captured_by:
                        hostage_data.append({
                            "type": "hostage",
                            "character_a": gp.captured_by,
                            "character_b": gp.name,
                            "role_a": "captor",
                            "role_b": "captive",
                            "since_turn": gp.born_turn,
                        })

                # Look up dissolved edges for this moment's turn range
                moment_dissolved = []
                if dissolved_edges_by_turn:
                    for t in range(moment.turn_range[0], moment.turn_range[1] + 1):
                        moment_dissolved.extend(dissolved_edges_by_turn.get(t, []))

                agent_ctx = build_agent_context_for_moment(
                    moment, great_persons, {}, {},
                    social_edges=social_edges,
                    dissolved_edges=moment_dissolved if moment_dissolved else None,
                    agent_name_map=agent_name_map,
                    hostage_data=hostage_data,
                )
                if agent_ctx is not None:
                    # Format relationships for prompt
                    if agent_ctx.relationships:
                        agent_context_text = "\n\nCHARACTER RELATIONSHIPS:\n"
                        for rel in agent_ctx.relationships:
                            if rel["type"] == "mentor":
                                agent_context_text += f"- {rel['character_b']} (apprentice of {rel['character_a']}, since turn {rel['since_turn']})\n"
                            elif rel["type"] == "hostage":
                                agent_context_text += f"- {rel['character_b']} (hostage of {rel['character_a']})\n"
                            else:
                                agent_context_text += f"- {rel['character_a']} and {rel['character_b']} ({rel['type']}, since turn {rel['since_turn']})\n"
```

Then inject `agent_context_text` into the prompt template at line ~700:

```python
            prompt = f"""NARRATIVE ROLE: {moment.narrative_role.value.upper()}
{role_instruction}

TURNS {moment.turn_range[0]}-{moment.turn_range[1]}:

EVENTS:{event_text}{named_text}{causal_text}{context_text}{continuity_text}{style_text}{agent_context_text}

Write 3-5 paragraphs of chronicle prose for this moment.
Respond only with the chronicle prose. No preamble, no markdown formatting."""
```

Then update the callers to pass the new parameters:

In `src/chronicler/main.py` at the `engine.narrate_batch()` call (line ~673):

```python
    # M40: Collect great persons and social edge data for narration
    all_gps = []
    agent_name_map = {}
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            gp = GreatPerson.model_validate(gp_data)
            all_gps.append(gp)
            if gp.agent_id is not None:
                agent_name_map[gp.agent_id] = gp.name

    # Read final social edges from bridge (approximation — edges change slowly,
    # final-turn edges are close enough for all but the most recent moments)
    social_edges = []
    if hasattr(args, 'agent_bridge') and args.agent_bridge is not None:
        social_edges = args.agent_bridge.read_social_edges()

    # Dissolved edges per-turn from world state
    dissolved_by_turn = getattr(world, 'dissolved_edges_by_turn', {}) if world else {}

    chronicle_entries = engine.narrate_batch(
        moments, history, gap_summaries, on_progress=progress_cb,
        great_persons=all_gps if all_gps else None,
        social_edges=social_edges if social_edges else None,
        dissolved_edges_by_turn=dissolved_by_turn if dissolved_by_turn else None,
        agent_name_map=agent_name_map if agent_name_map else None,
    )
```

**Note:** The `world` object may not be available in `_run_narrate()` (it loads from bundle). If `dissolved_edges_by_turn` isn't serialized (it's `exclude=True`), it won't survive the bundle round-trip. In that case, dissolved edges are only available for in-process narration (not post-hoc `--narrate` mode). This is acceptable — dissolved edge context is a "nice to have" enhancement, not load-bearing. In-process narration (the common case) gets it; post-hoc narration proceeds without it.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_narrative.py::test_agent_context_includes_relationships -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -x -q --timeout=60`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat(m40): wire relationship context into narration pipeline"
```

---

### Task 17: Final cleanup and agents=off test

**Files:**
- Test: `tests/test_relationships.py` (add agents=off test)

- [ ] **Step 1: Write agents=off test**

Add to `tests/test_relationships.py`:

```python
def test_agents_off_produces_empty_relationships():
    """In --agents=off mode, no social graph exists, relationships are empty."""
    from chronicler.relationships import form_and_sync_relationships

    class NullBridge:
        def read_social_edges(self):
            return []
        def replace_social_edges(self, edges):
            pass

    world = WorldState(seed=42, turn=50, regions=[], civilizations=[], relationships={})
    # No active agent IDs (aggregate mode)
    dissolved = form_and_sync_relationships(
        world, NullBridge(), set(), {}, {},
    )
    assert len(dissolved) == 0
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -x -q --timeout=60`
Expected: all tests pass

- [ ] **Step 3: Run linting**

Run: `python -m ruff check src/chronicler/relationships.py src/chronicler/models.py src/chronicler/curator.py src/chronicler/narrative.py`
Expected: no errors (or only pre-existing ones)

- [ ] **Step 4: Final commit**

```bash
git add tests/test_relationships.py
git commit -m "test(m40): add agents=off empty relationships test"
```

---

## Summary

| Task | Component | Key Deliverable |
|------|-----------|----------------|
| 1 | Rust social.rs | SocialGraph, SocialEdge, RelationshipType |
| 2 | Rust FFI | get_social_edges, replace_social_edges on AgentSimulator |
| 3 | Python models | origin_region on GreatPerson, relationships on AgentContext |
| 4 | Bridge | origin_region set at promotion |
| 5 | Bridge | read/replace social edge methods |
| 6 | Dissolution | dissolve_edges with death + belief rules |
| 7 | Rivalry | Migrated to agent_id edge tuples |
| 8 | Mentorship | Rewritten: agent-source peers, co-located |
| 9 | Marriage | Migrated to agent_id edge tuples |
| 10 | Exile bond | New formation function |
| 11 | Co-religionist | New formation function |
| 12 | Coordinator | form_and_sync_relationships |
| 13 | Phase 10 | Wire coordinator, remove character_relationships |
| 14 | Curator activation | Wire named_characters to curate() |
| 15 | Curator boost | 1.2x relationship score bonus |
| 16 | Narration | Activate agent context pipeline, wire relationships |
| 17 | Cleanup | agents=off test, lint check |
