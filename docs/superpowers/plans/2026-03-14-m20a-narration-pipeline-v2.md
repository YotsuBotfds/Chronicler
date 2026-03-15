# M20a: Narration Pipeline v2 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-turn LLM narration with a three-phase pipeline (Simulate → Curate → Narrate) that selects the most narratively important moments and narrates them with full before/after context.

**Architecture:** New `curator.py` module scores and selects ~50 moments from a completed simulation's event timeline using heuristic scoring, causal linking, and cluster detection. `NarrativeEngine.narrate_batch()` narrates each selected moment with full history context. Bundle format changes from `dict[str, str]` to `list[ChronicleEntry]` (sparse). Viewer gets segmented timeline with role-colored narrated segments and collapsible mechanical gaps.

**Tech Stack:** Python 3.12 (Pydantic models, pure Python curator), TypeScript/React (viewer components), LM Studio OpenAI-compatible API (batch narration)

**Spec:** `docs/superpowers/specs/2026-03-14-m20a-narration-pipeline-v2-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/chronicler/curator.py` | Event selection: base scoring, causal linking, clustering, role assignment, gap summaries, degenerate path |
| `tests/test_curator.py` | All curator unit tests |
| `tests/test_batch_narration.py` | Batch narration context construction, integration tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/chronicler/models.py` | Add `NarrativeRole`, `CausalLink`, `GapSummary`, `NarrativeMoment`, `CivThematicContext`, `NarrationContext`, new `ChronicleEntry` (Pydantic) |
| `src/chronicler/chronicle.py` | Remove old `ChronicleEntry` dataclass, update `compile_chronicle()` for sparse output with gap summaries |
| `src/chronicler/bundle.py` | Update `assemble_bundle()` to serialize new `ChronicleEntry` list + `GapSummary` list |
| `src/chronicler/narrative.py` | Add `narrate_batch()`, `build_before_summary()`, `build_after_summary()`, role instruction mapping |
| `src/chronicler/main.py` | Add `--narrate` flag for post-hoc narration, skip ChronicleEntry loop in simulate-only, update bundle assembly |
| `src/chronicler/live.py` | Add `narrate_range` WebSocket handler |
| `viewer/src/types.ts` | Add `ChronicleEntry`, `GapSummary`, `CausalLink` interfaces, `BundleChronicle` union, `isLegacyBundle()` |
| `viewer/src/components/TimelineScrubber.tsx` | Rewrite: segmented bar with role colors, causal overlay, "narrate this" button |
| `viewer/src/components/ChroniclePanel.tsx` | Rewrite: context-dependent rendering based on focused segment type |
| `viewer/src/hooks/useLiveConnection.ts` | Add `narrate_range` / `narration_complete` message handlers |
| `tests/test_chronicle.py` | Update for new `ChronicleEntry` model |
| `tests/test_bundle.py` | Update for new bundle format |

---

## Chunk 1: Data Models & ChronicleEntry Migration

### Task 1: Add New Data Models to `models.py`

**Files:**
- Modify: `src/chronicler/models.py` (add after line 427, after `TurnSnapshot`)
- Test: `tests/test_models.py`

- [ ] **Step 1: Write tests for new models**

```python
# tests/test_models.py — append to existing file

from chronicler.models import (
    NarrativeRole, CausalLink, GapSummary, NarrativeMoment,
    CivThematicContext,
)


def test_narrative_role_values():
    assert NarrativeRole.INCITING == "inciting"
    assert NarrativeRole.ESCALATION == "escalation"
    assert NarrativeRole.CLIMAX == "climax"
    assert NarrativeRole.RESOLUTION == "resolution"
    assert NarrativeRole.CODA == "coda"


def test_causal_link_creation():
    link = CausalLink(
        cause_turn=10, cause_event_type="drought",
        effect_turn=18, effect_event_type="famine",
        pattern="drought→famine",
    )
    assert link.cause_turn == 10
    assert link.pattern == "drought→famine"


def test_gap_summary_stat_deltas_shape():
    gap = GapSummary(
        turn_range=(10, 30), event_count=15,
        top_event_type="war",
        stat_deltas={"Vrashni": {"population": -20, "military": 5, "stability": -12}},
        territory_changes=3,
    )
    assert gap.stat_deltas["Vrashni"]["population"] == -20
    assert gap.turn_range == (10, 30)


def test_narrative_moment_creation():
    from chronicler.models import Event
    event = Event(turn=10, event_type="war", actors=["Vrashni"], description="test")
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(8, 12),
        events=[event], named_events=[], score=15.0,
        causal_links=[], narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=3.0,
    )
    assert moment.anchor_turn == 10
    assert moment.narrative_role == NarrativeRole.CLIMAX
    assert moment.bonus_applied == 3.0


def test_civ_thematic_context():
    ctx = CivThematicContext(
        name="Vrashni", trait="aggressive",
        domains=["maritime", "mysticism"],
        dominant_terrain="coast", tech_era="classical",
        active_named_events=["The Battle of Tidecrest"],
    )
    assert ctx.active_tech_focus is None  # M21 default
    assert ctx.domains == ["maritime", "mysticism"]


def test_causal_link_round_trip():
    link = CausalLink(
        cause_turn=10, cause_event_type="drought",
        effect_turn=18, effect_event_type="famine",
        pattern="drought→famine",
    )
    data = link.model_dump()
    restored = CausalLink.model_validate(data)
    assert restored == link


def test_gap_summary_round_trip():
    gap = GapSummary(
        turn_range=(10, 30), event_count=15,
        top_event_type="war",
        stat_deltas={"Vrashni": {"population": -20}},
        territory_changes=3,
    )
    data = gap.model_dump()
    restored = GapSummary.model_validate(data)
    assert restored == gap
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py::test_narrative_role_values -v`
Expected: FAIL with `ImportError: cannot import name 'NarrativeRole'`

- [ ] **Step 3: Add models to `models.py`**

Add after `TurnSnapshot` class (after line 427 in `src/chronicler/models.py`):

```python
# --- M20a: Narration Pipeline v2 models ---

class NarrativeRole(str, Enum):
    """Narrative arc position for a curated moment."""
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"


class CausalLink(BaseModel):
    """Connection between a cause event and its effect."""
    cause_turn: int
    cause_event_type: str
    effect_turn: int
    effect_event_type: str
    pattern: str  # e.g., "drought→famine"


class GapSummary(BaseModel):
    """Mechanical summary of unnarrated turns between curated moments."""
    turn_range: tuple[int, int]  # inclusive
    event_count: int
    top_event_type: str
    stat_deltas: dict[str, dict[str, int]]  # {civ_name: {stat_name: delta}}
    territory_changes: int


class CivThematicContext(BaseModel):
    """Per-civ thematic data for narrator prompts."""
    name: str
    trait: str
    domains: list[str]
    dominant_terrain: str
    tech_era: str
    active_tech_focus: str | None = None
    active_named_events: list[str] = Field(default_factory=list)


class NarrativeMoment(BaseModel):
    """Curator output: a selected narratively important moment."""
    anchor_turn: int
    turn_range: tuple[int, int]  # inclusive
    events: list[Event]
    named_events: list[NamedEvent]
    score: float
    causal_links: list[CausalLink]
    narrative_role: NarrativeRole
    bonus_applied: float  # internal, not serialized to bundle


class NarrationContext(BaseModel):
    """Per-moment LLM context for batch narration."""
    moment: NarrativeMoment
    snapshot: TurnSnapshot
    before_summary: str
    after_summary: str
    role_instruction: str
    causes: list[str]
    consequences: list[str]
    previous_prose: str | None
    civ_context: dict[str, CivThematicContext]
```

Also add `NarrativeRole` to the `Enum` import at the top of the file (it already imports `Enum` for `TechEra`, `Disposition`, etc.).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -k "narrative_role or causal_link or gap_summary or narrative_moment or civ_thematic" -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat(m20a): add narration pipeline data models"
```

---

### Task 2: Migrate `ChronicleEntry` to Pydantic

**Files:**
- Modify: `src/chronicler/models.py` (add new `ChronicleEntry`)
- Modify: `src/chronicler/chronicle.py:11-15` (remove old dataclass)
- Modify: `src/chronicler/bundle.py:9,33` (update import + access)
- Modify: `src/chronicler/main.py:277-280` (update construction)
- Test: `tests/test_chronicle.py`, `tests/test_bundle.py`

- [ ] **Step 1: Write test for new ChronicleEntry**

```python
# tests/test_chronicle.py — add to existing file

from chronicler.models import (
    ChronicleEntry, NarrativeRole, CausalLink, Event, NamedEvent,
)


def test_new_chronicle_entry_creation():
    entry = ChronicleEntry(
        turn=50, covers_turns=(45, 55),
        events=[Event(turn=50, event_type="war", actors=["A"], description="test")],
        named_events=[], narrative="The armies clashed at dawn.",
        importance=8.5, narrative_role=NarrativeRole.CLIMAX,
        causal_links=[],
    )
    assert entry.turn == 50
    assert entry.narrative == "The armies clashed at dawn."
    assert entry.narrative_role == NarrativeRole.CLIMAX


def test_chronicle_entry_round_trip():
    entry = ChronicleEntry(
        turn=50, covers_turns=(45, 55),
        events=[], named_events=[],
        narrative="test", importance=5.0,
        narrative_role=NarrativeRole.RESOLUTION,
        causal_links=[CausalLink(
            cause_turn=40, cause_event_type="drought",
            effect_turn=50, effect_event_type="famine",
            pattern="drought→famine",
        )],
    )
    data = entry.model_dump()
    restored = ChronicleEntry.model_validate(data)
    assert restored == entry
    assert restored.narrative_role == NarrativeRole.RESOLUTION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chronicle.py::test_new_chronicle_entry_creation -v`
Expected: FAIL with `ImportError: cannot import name 'ChronicleEntry' from 'chronicler.models'`

- [ ] **Step 3: Add `ChronicleEntry` to `models.py`**

Add after `NarrativeMoment` in `src/chronicler/models.py`:

```python
class ChronicleEntry(BaseModel):
    """A narrated chronicle entry covering a range of turns."""
    turn: int  # anchor turn
    covers_turns: tuple[int, int]  # inclusive range
    events: list[Event]
    named_events: list[NamedEvent]
    narrative: str  # LLM prose or mechanical fallback
    importance: float
    narrative_role: NarrativeRole
    causal_links: list[CausalLink]
```

- [ ] **Step 4: Run tests to verify new model works**

Run: `python -m pytest tests/test_chronicle.py::test_new_chronicle_entry_creation tests/test_chronicle.py::test_chronicle_entry_round_trip -v`
Expected: PASS

- [ ] **Step 5: Update `chronicle.py` — remove old dataclass, update `compile_chronicle`**

In `src/chronicler/chronicle.py`:

1. Remove the old `ChronicleEntry` dataclass (lines 11-15)
2. Add import: `from chronicler.models import ChronicleEntry, GapSummary`
3. Update `compile_chronicle` signature and body (lines 18-43):

```python
from chronicler.models import ChronicleEntry, GapSummary


def compile_chronicle(
    world_name: str,
    entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    epilogue: str | None = None,
    gap_summaries: list[GapSummary] | None = None,
) -> str:
    """Compile chronicle entries, gap summaries, and era reflections into Markdown."""
    lines: list[str] = [f"# The Chronicle of {world_name}\n"]

    # Merge entries and gaps into a single sorted timeline
    all_items: list[tuple[int, str, str]] = []  # (turn, type, content)

    for entry in sorted(entries, key=lambda e: e.turn):
        all_items.append((entry.turn, "entry", entry.narrative))

    if gap_summaries:
        for gap in sorted(gap_summaries, key=lambda g: g.turn_range[0]):
            all_items.append((
                gap.turn_range[0], "gap",
                f"[Mechanical: turns {gap.turn_range[0]}-{gap.turn_range[1]}, "
                f"{gap.event_count} events]"
            ))

    all_items.sort(key=lambda x: x[0])

    for turn, item_type, content in all_items:
        # Insert era reflections at boundaries
        for ref_turn in sorted(era_reflections.keys()):
            if ref_turn <= turn:
                reflection = era_reflections.pop(ref_turn)
                lines.append(f"\n---\n\n{reflection}\n")

        if item_type == "entry":
            lines.append(f"\n## Turn {turn}\n\n{content}\n")
        else:
            lines.append(f"\n{content}\n")

    # Remaining era reflections
    for ref_turn in sorted(era_reflections.keys()):
        lines.append(f"\n---\n\n{era_reflections[ref_turn]}\n")

    if epilogue:
        lines.append(f"\n---\n\n## Epilogue\n\n{epilogue}\n")

    return "\n".join(lines)
```

- [ ] **Step 6: Update `bundle.py` — new import and serialization**

In `src/chronicler/bundle.py`:

1. Change import at line 9: `from chronicler.chronicle import ChronicleEntry` → `from chronicler.models import ChronicleEntry, GapSummary`
2. Update `assemble_bundle` signature (line 13-21) to add `gap_summaries` param:

```python
def assemble_bundle(
    world: WorldState,
    history: list[TurnSnapshot],
    chronicle_entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    sim_model: str,
    narrative_model: str,
    interestingness_score: float | None,
    gap_summaries: list[GapSummary] | None = None,
) -> dict[str, Any]:
```

3. Replace line 33 (`{str(entry.turn): entry.text for entry in chronicle_entries}`) with:

```python
    "chronicle_entries": [entry.model_dump() for entry in chronicle_entries],
    "gap_summaries": [gs.model_dump() for gs in (gap_summaries or [])],
```

- [ ] **Step 7: Update `main.py` — ChronicleEntry construction**

In `src/chronicler/main.py`:

1. Update import: change `from chronicler.chronicle import ChronicleEntry` to `from chronicler.models import ChronicleEntry, NarrativeRole`
2. Update the ChronicleEntry construction at ~line 277-280. The existing code:
   ```python
   chronicle_entries.append(ChronicleEntry(turn=world.turn, text=chronicle_text))
   ```
   becomes:
   ```python
   chronicle_entries.append(ChronicleEntry(
       turn=world.turn, covers_turns=(world.turn, world.turn),
       events=[], named_events=[],
       narrative=chronicle_text, importance=5.0,
       narrative_role=NarrativeRole.RESOLUTION,
       causal_links=[],
   ))
   ```
   Note: `events=[]` because `turn_events` is not defined until line 284 (after this construction). Live mode entries don't need full event lists — events are available in `events_timeline` on the bundle. This keeps live mode working — each turn gets a single-turn entry with default values.

- [ ] **Step 8: Run existing tests to verify nothing broke**

Run: `python -m pytest tests/test_chronicle.py tests/test_bundle.py tests/test_narrative.py -v`
Expected: All existing tests PASS (some may need minor updates if they construct `ChronicleEntry` with old fields)

- [ ] **Step 9: Fix any broken existing tests**

Known breakage: `test_chronicle_entries_keyed_by_turn_string` in `tests/test_bundle.py` (~line 151-164) asserts that `chronicle_entries` is a dict keyed by turn strings. This test must be updated to assert the new list format instead. Also update any other tests that construct `ChronicleEntry(turn=X, text=Y)` to use the new Pydantic model:
```python
ChronicleEntry(
    turn=X, covers_turns=(X, X), events=[], named_events=[],
    narrative=Y, importance=5.0, narrative_role=NarrativeRole.RESOLUTION,
    causal_links=[],
)
```

- [ ] **Step 10: Commit**

```bash
git add src/chronicler/models.py src/chronicler/chronicle.py src/chronicler/bundle.py src/chronicler/main.py tests/test_chronicle.py tests/test_bundle.py
git commit -m "feat(m20a): migrate ChronicleEntry to Pydantic, update bundle format"
```

---

## Chunk 2: Narrative Curator

### Task 3: Curator Base Scoring & Dominant Power

**Files:**
- Create: `src/chronicler/curator.py`
- Create: `tests/test_curator.py`

- [ ] **Step 1: Write tests for dominant power detection and base scoring**

```python
# tests/test_curator.py

from chronicler.models import Event, NamedEvent, TurnSnapshot, CivSnapshot
from chronicler.curator import (
    compute_dominant_power, compute_base_scores, CAUSAL_PATTERNS,
)


def _make_snapshot(turn: int, region_control: dict[str, str | None]) -> TurnSnapshot:
    """Helper: minimal TurnSnapshot with region control."""
    return TurnSnapshot(
        turn=turn,
        civ_stats={
            name: CivSnapshot(
                population=100, military=50, economy=50, culture=50,
                stability=50, treasury=100, asabiya=0.5,
                tech_era="classical", trait="aggressive",
                regions=[r for r, c in region_control.items() if c == name],
                leader_name="Leader", alive=True,
            )
            for name in set(c for c in region_control.values() if c)
        },
        region_control=region_control,
        relationships={},
    )


def test_dominant_power_cumulative():
    """Dominant power = most cumulative region-turns, not final snapshot."""
    history = [
        # Turns 1-3: A holds 5 regions
        _make_snapshot(1, {"r1": "A", "r2": "A", "r3": "A", "r4": "A", "r5": "A"}),
        _make_snapshot(2, {"r1": "A", "r2": "A", "r3": "A", "r4": "A", "r5": "A"}),
        _make_snapshot(3, {"r1": "A", "r2": "A", "r3": "A", "r4": "A", "r5": "A"}),
        # Turn 4: A collapses, B holds 3 regions
        _make_snapshot(4, {"r1": "B", "r2": "B", "r3": "B", "r4": None, "r5": None}),
    ]
    # A: 5*3 = 15 region-turns, B: 3*1 = 3 region-turns
    assert compute_dominant_power(history, seed=0) == "A"


def test_dominant_power_tiebreak():
    """Ties broken by hash(seed, civ.name) — deterministic."""
    history = [
        _make_snapshot(1, {"r1": "A", "r2": "B"}),
        _make_snapshot(2, {"r1": "A", "r2": "B"}),
    ]
    # A: 2 region-turns, B: 2 region-turns — tie
    result_seed0 = compute_dominant_power(history, seed=0)
    result_seed1 = compute_dominant_power(history, seed=1)
    # Both should return a valid civ, deterministically
    assert result_seed0 in ("A", "B")
    assert result_seed1 in ("A", "B")
    # Same seed → same result
    assert compute_dominant_power(history, seed=0) == result_seed0


def test_base_scoring_importance():
    """Base score starts from event.importance."""
    events = [
        Event(turn=1, event_type="war", actors=["A"], description="test", importance=8),
        Event(turn=2, event_type="trade", actors=["B"], description="test", importance=3),
    ]
    scores = compute_base_scores(events, named_events=[], dominant_power="C", seed=0)
    assert scores[0] == 8.0  # importance only, no bonuses
    assert scores[1] == 3.0


def test_base_scoring_named_event_bonus():
    """Named events get +3."""
    events = [
        Event(turn=5, event_type="war", actors=["A", "B"], description="test", importance=7),
    ]
    named = [
        NamedEvent(name="Battle of X", event_type="war", turn=5,
                   actors=["A", "B"], description="test", importance=7),
    ]
    scores = compute_base_scores(events, named_events=named, dominant_power="C", seed=0)
    assert scores[0] == 10.0  # 7 + 3 (named)


def test_base_scoring_dominant_power_bonus():
    """Events involving dominant power get +2."""
    events = [
        Event(turn=1, event_type="war", actors=["A", "B"], description="test", importance=5),
    ]
    scores = compute_base_scores(events, named_events=[], dominant_power="A", seed=0)
    assert scores[0] == 7.0  # 5 + 2 (dominant)


def test_base_scoring_rarity_bonus():
    """Event types occurring <3 times get +2."""
    events = [
        Event(turn=1, event_type="supervolcano", actors=["A"], description="test", importance=5),
        Event(turn=2, event_type="war", actors=["A"], description="test", importance=5),
        Event(turn=3, event_type="war", actors=["A"], description="test", importance=5),
        Event(turn=4, event_type="war", actors=["A"], description="test", importance=5),
    ]
    scores = compute_base_scores(events, named_events=[], dominant_power="X", seed=0)
    assert scores[0] == 7.0  # 5 + 2 (rarity: supervolcano appears once)
    assert scores[1] == 5.0  # war appears 3 times, no rarity bonus
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_curator.py::test_dominant_power_cumulative -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicler.curator'`

- [ ] **Step 3: Implement `curator.py` — dominant power + base scoring**

```python
# src/chronicler/curator.py
"""Narrative curator: selects the most important moments from a simulation."""

from __future__ import annotations

from collections import Counter

from chronicler.models import (
    CausalLink, Event, GapSummary, NamedEvent, NarrativeMoment,
    NarrativeRole, TurnSnapshot,
)

# --- Constants ---

CLUSTER_MERGE_THRESHOLD = 5  # turns; tunable, flagged for M19b validation

CAUSAL_PATTERNS: list[tuple[str, str, int, float]] = [
    # (cause_type, effect_type, max_gap, bonus)
    ("drought", "famine", 10, 3.0),
    ("drought", "migration", 15, 2.0),
    ("famine", "rebellion", 10, 3.0),
    ("famine", "secession", 15, 3.0),
    ("war", "collapse", 20, 4.0),
    ("war", "leader_death", 5, 2.0),
    ("leader_death", "succession_crisis", 1, 3.0),
    ("succession_crisis", "coup", 5, 3.0),
    ("plague", "famine", 10, 2.0),
    ("embargo", "rebellion", 15, 2.0),
    ("tech_advancement", "war", 10, 2.0),
    ("cultural_renaissance", "movement", 10, 2.0),
    ("discovery", "war", 15, 2.0),
]


def compute_dominant_power(history: list[TurnSnapshot], seed: int) -> str:
    """Find the civ with the most cumulative region-turns.

    Handles runs where all civs are eliminated — looks at entire history,
    not just final snapshot. Ties broken by hash(seed, civ_name).
    """
    region_turns: Counter[str] = Counter()
    for snapshot in history:
        for _region, controller in snapshot.region_control.items():
            if controller:
                region_turns[controller] += 1

    if not region_turns:
        return ""

    max_count = max(region_turns.values())
    tied = [name for name, count in region_turns.items() if count == max_count]
    if len(tied) == 1:
        return tied[0]
    # Deterministic tiebreak
    return min(tied, key=lambda name: hash((seed, name)))


def compute_base_scores(
    events: list[Event],
    named_events: list[NamedEvent],
    dominant_power: str,
    seed: int,
) -> list[float]:
    """Pass 1: Base scoring. Returns parallel list of scores for each event."""
    # Count event type frequencies for rarity bonus
    type_counts: Counter[str] = Counter(e.event_type for e in events)

    # Build named event lookup: (turn, frozenset(actors)) → True
    named_lookup: set[tuple[int, frozenset[str]]] = {
        (ne.turn, frozenset(ne.actors)) for ne in named_events
    }

    scores: list[float] = []
    for event in events:
        score = float(event.importance)

        # Named event bonus: +3
        if (event.turn, frozenset(event.actors)) in named_lookup:
            score += 3.0

        # Dominant power bonus: +2
        if dominant_power and dominant_power in event.actors:
            score += 2.0

        # Rarity bonus: +2 if type occurs fewer than 3 times
        if type_counts[event.event_type] < 3:
            score += 2.0

        scores.append(score)

    return scores
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_curator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m20a): curator base scoring and dominant power detection"
```

---

### Task 4: Curator Causal Linking

**Files:**
- Modify: `src/chronicler/curator.py`
- Modify: `tests/test_curator.py`

- [ ] **Step 1: Write tests for causal linking**

```python
# tests/test_curator.py — append

from chronicler.curator import compute_causal_links


def test_causal_link_within_max_gap():
    """drought at turn 5 → famine at turn 12 (gap=7, max_gap=10): linked."""
    events = [
        Event(turn=5, event_type="drought", actors=["A"], description="d"),
        Event(turn=12, event_type="famine", actors=["A"], description="f"),
    ]
    scores = [5.0, 5.0]
    links = compute_causal_links(events, scores)
    assert len(links) == 1
    assert links[0].pattern == "drought→famine"
    assert scores[0] == 8.0  # 5 + 3 (drought→famine bonus)
    assert scores[1] == 5.0  # effect keeps its score


def test_causal_link_beyond_max_gap():
    """drought at turn 5 → famine at turn 20 (gap=15, max_gap=10): NOT linked."""
    events = [
        Event(turn=5, event_type="drought", actors=["A"], description="d"),
        Event(turn=20, event_type="famine", actors=["A"], description="f"),
    ]
    scores = [5.0, 5.0]
    links = compute_causal_links(events, scores)
    assert len(links) == 0
    assert scores[0] == 5.0  # no bonus


def test_causal_link_spatial_filter():
    """Events must share an actor or region. No shared actor → no link."""
    events = [
        Event(turn=5, event_type="drought", actors=["A"], description="d"),
        Event(turn=12, event_type="famine", actors=["B"], description="f"),
    ]
    scores = [5.0, 5.0]
    links = compute_causal_links(events, scores)
    assert len(links) == 0  # different actors, no link


def test_causal_link_multiple_bonuses():
    """A war can cause both leader_death and collapse — gets both bonuses."""
    events = [
        Event(turn=10, event_type="war", actors=["A", "B"], description="w"),
        Event(turn=13, event_type="leader_death", actors=["A"], description="ld"),
        Event(turn=25, event_type="collapse", actors=["A"], description="c"),
    ]
    scores = [5.0, 5.0, 5.0]
    links = compute_causal_links(events, scores)
    # war→leader_death (gap=3, max=5) and war→collapse (gap=15, max=20)
    assert len(links) == 2
    assert scores[0] == 11.0  # 5 + 2 (leader_death) + 4 (collapse)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_curator.py::test_causal_link_within_max_gap -v`
Expected: FAIL with `ImportError: cannot import name 'compute_causal_links'`

- [ ] **Step 3: Implement causal linking**

Add to `src/chronicler/curator.py`:

```python
def compute_causal_links(
    events: list[Event],
    scores: list[float],
) -> list[CausalLink]:
    """Pass 2: Causal linking. Mutates scores in place (adds bonuses to causes).

    For each event, scan forward through CAUSAL_PATTERNS using each pattern's
    max_gap. Spatial filter: cause and effect must share an actor.
    Returns list of all discovered CausalLinks.
    """
    links: list[CausalLink] = []

    for i, cause in enumerate(events):
        for cause_type, effect_type, max_gap, bonus in CAUSAL_PATTERNS:
            if cause.event_type != cause_type:
                continue

            for j in range(i + 1, len(events)):
                effect = events[j]
                gap = effect.turn - cause.turn
                if gap > max_gap:
                    # Events are sorted by turn; once we exceed max_gap,
                    # no later event for this pattern can match
                    break
                if gap < 0:
                    continue

                if effect.event_type != effect_type:
                    continue

                # Spatial filter: must share at least one actor.
                # Note: Event model has no `region` field, so we filter
                # by actor overlap only. The spec says "actor or region" but
                # region is only on NamedEvent — actor-only is the practical filter.
                if not (set(cause.actors) & set(effect.actors)):
                    continue

                # Link found
                scores[i] += bonus
                links.append(CausalLink(
                    cause_turn=cause.turn,
                    cause_event_type=cause.event_type,
                    effect_turn=effect.turn,
                    effect_event_type=effect.event_type,
                    pattern=f"{cause_type}→{effect_type}",
                ))

    return links
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_curator.py -k "causal_link" -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m20a): curator causal linking with pattern-specific max_gap"
```

---

### Task 5: Curator Clustering, Selection, Diversity, Roles

**Files:**
- Modify: `src/chronicler/curator.py`
- Modify: `tests/test_curator.py`

- [ ] **Step 1: Write tests for clustering, diversity, and role assignment**

```python
# tests/test_curator.py — append


def test_cluster_merge_within_threshold():
    """Events within CLUSTER_MERGE_THRESHOLD turns merge into one cluster."""
    events = [
        Event(turn=10, event_type="war", actors=["A"], description="t", importance=8),
        Event(turn=11, event_type="famine", actors=["A"], description="t", importance=7),
        Event(turn=12, event_type="migration", actors=["A"], description="t", importance=6),
        Event(turn=50, event_type="war", actors=["B"], description="t", importance=9),
    ]
    scores = [8.0, 7.0, 6.0, 9.0]
    clusters = build_clusters(events, scores)
    assert len(clusters) == 2
    # First cluster: turns 10-12
    assert clusters[0]["turn_range"] == (10, 12)
    # Cluster score = sum of top 3: 8+7+6 = 21
    assert clusters[0]["score"] == 21.0
    # Second cluster: turn 50
    assert clusters[1]["turn_range"] == (50, 50)
    assert clusters[1]["score"] == 9.0


def test_cluster_anchor_turn():
    """anchor_turn = turn of highest-scoring event in cluster."""
    events = [
        Event(turn=10, event_type="war", actors=["A"], description="t", importance=5),
        Event(turn=12, event_type="famine", actors=["A"], description="t", importance=9),
    ]
    scores = [5.0, 9.0]
    clusters = build_clusters(events, scores)
    assert clusters[0]["anchor_turn"] == 12  # highest score in cluster


def test_diversity_penalty_civ():
    """If >40% of moments involve same civ, demote lowest-scored."""
    from chronicler.curator import apply_diversity_penalty
    # 5 moments, 4 from civ A — exceeds 40% threshold
    moments = [
        NarrativeMoment(anchor_turn=i*10, turn_range=(i*10, i*10),
                        events=[Event(turn=i*10, event_type="war",
                                     actors=["A"], description="t", importance=5)],
                        named_events=[], score=10.0 - i,
                        causal_links=[], narrative_role=NarrativeRole.ESCALATION,
                        bonus_applied=0)
        for i in range(4)
    ] + [
        NarrativeMoment(anchor_turn=50, turn_range=(50, 50),
                        events=[Event(turn=50, event_type="trade",
                                     actors=["B"], description="t", importance=5)],
                        named_events=[], score=3.0,
                        causal_links=[], narrative_role=NarrativeRole.ESCALATION,
                        bonus_applied=0)
    ]
    # Unselected pool with a B moment
    unselected = [
        NarrativeMoment(anchor_turn=60, turn_range=(60, 60),
                        events=[Event(turn=60, event_type="trade",
                                     actors=["B"], description="t", importance=5)],
                        named_events=[], score=2.0,
                        causal_links=[], narrative_role=NarrativeRole.ESCALATION,
                        bonus_applied=0)
    ]
    result = apply_diversity_penalty(moments, unselected)
    # A had 4/5=80%, should be reduced. At least one A moment replaced.
    a_count = sum(1 for m in result if "A" in m.events[0].actors)
    assert a_count <= 2  # 40% of 5 = 2


def test_role_assignment_basic():
    """Highest score = CLIMAX, before = ESCALATION, first = INCITING, after = RESOLUTION, last = CODA."""
    from chronicler.curator import assign_roles
    moments = [
        NarrativeMoment(anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
                        score=5.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
        NarrativeMoment(anchor_turn=30, turn_range=(30, 30), events=[], named_events=[],
                        score=15.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
        NarrativeMoment(anchor_turn=50, turn_range=(50, 50), events=[], named_events=[],
                        score=8.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
        NarrativeMoment(anchor_turn=70, turn_range=(70, 70), events=[], named_events=[],
                        score=4.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
    ]
    assign_roles(moments)
    assert moments[0].narrative_role == NarrativeRole.INCITING  # first pre-climax
    assert moments[1].narrative_role == NarrativeRole.CLIMAX    # highest score
    assert moments[2].narrative_role == NarrativeRole.RESOLUTION
    assert moments[3].narrative_role == NarrativeRole.CODA      # last


def test_role_assignment_climax_first():
    """Edge case: climax is the first moment."""
    from chronicler.curator import assign_roles
    moments = [
        NarrativeMoment(anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
                        score=20.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
        NarrativeMoment(anchor_turn=30, turn_range=(30, 30), events=[], named_events=[],
                        score=5.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
    ]
    assign_roles(moments)
    assert moments[0].narrative_role == NarrativeRole.CLIMAX
    assert moments[1].narrative_role == NarrativeRole.CODA  # last and only post-climax


def test_role_assignment_single_moment():
    """Edge case: only one moment — it's CLIMAX."""
    from chronicler.curator import assign_roles
    moments = [
        NarrativeMoment(anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
                        score=5.0, causal_links=[], narrative_role=NarrativeRole.ESCALATION, bonus_applied=0),
    ]
    assign_roles(moments)
    assert moments[0].narrative_role == NarrativeRole.CLIMAX
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_curator.py::test_cluster_merge_within_threshold -v`
Expected: FAIL with `ImportError: cannot import name 'build_clusters'`

- [ ] **Step 3: Implement clustering, diversity, and role assignment**

Add to `src/chronicler/curator.py`:

```python
def build_clusters(
    events: list[Event],
    scores: list[float],
) -> list[dict]:
    """Pass 3: Group events into clusters within CLUSTER_MERGE_THRESHOLD turns.

    Returns list of cluster dicts with keys: turn_range, anchor_turn, score,
    event_indices (indices into the events list).
    """
    if not events:
        return []

    # Sort events by turn (preserve original indices)
    indexed = sorted(enumerate(events), key=lambda x: x[1].turn)

    clusters: list[dict] = []
    current: list[int] = [indexed[0][0]]
    current_max_turn = indexed[0][1].turn

    for idx, event in indexed[1:]:
        if event.turn - current_max_turn <= CLUSTER_MERGE_THRESHOLD:
            current.append(idx)
            current_max_turn = event.turn
        else:
            clusters.append(_finalize_cluster(current, events, scores))
            current = [idx]
            current_max_turn = event.turn

    clusters.append(_finalize_cluster(current, events, scores))
    return clusters


def _finalize_cluster(
    indices: list[int],
    events: list[Event],
    scores: list[float],
) -> dict:
    """Build cluster dict from event indices. Score = sum of top 3."""
    member_scores = sorted([scores[i] for i in indices], reverse=True)
    cluster_score = sum(member_scores[:3])
    turns = [events[i].turn for i in indices]
    # anchor = turn of highest-scoring event
    best_idx = max(indices, key=lambda i: scores[i])
    return {
        "turn_range": (min(turns), max(turns)),
        "anchor_turn": events[best_idx].turn,
        "score": cluster_score,
        "event_indices": indices,
    }


def apply_diversity_penalty(
    selected: list[NarrativeMoment],
    unselected: list[NarrativeMoment],
) -> list[NarrativeMoment]:
    """Demote over-represented civs/types, replace with unselected moments.

    - >40% same civ: demote lowest-scored moments for that civ
    - >30% same event type: same treatment
    - Named events are exempt from demotion
    """
    result = list(selected)
    pool = sorted(unselected, key=lambda m: m.score, reverse=True)

    for _ in range(3):  # iterate to convergence
        changed = False

        # Check civ representation (per-moment, not per-event)
        # A moment "involves" a civ if that civ appears as an actor in any event
        civ_counts: Counter[str] = Counter()
        for m in result:
            involved_civs = {a for e in m.events for a in e.actors}
            for civ in involved_civs:
                civ_counts[civ] += 1  # +1 per moment, not per event

        threshold_civ = len(result) * 0.4
        for civ, count in civ_counts.items():
            while count > threshold_civ and pool:
                # Find lowest-scored moment involving this civ (not named)
                demotable = [
                    (i, m) for i, m in enumerate(result)
                    if civ in {a for e in m.events for a in e.actors}
                    and not m.named_events
                ]
                if not demotable:
                    break
                demotable.sort(key=lambda x: x[1].score)
                idx, removed = demotable[0]
                replacement = pool.pop(0)
                result[idx] = replacement
                count -= 1
                changed = True

        # Check event type representation
        type_counts: Counter[str] = Counter()
        for m in result:
            dominant_type = Counter(e.event_type for e in m.events).most_common(1)
            if dominant_type:
                type_counts[dominant_type[0][0]] += 1

        threshold_type = len(result) * 0.3
        for etype, count in type_counts.items():
            while count > threshold_type and pool:
                demotable = [
                    (i, m) for i, m in enumerate(result)
                    if Counter(e.event_type for e in m.events).most_common(1)[0][0] == etype
                    and not m.named_events
                ]
                if not demotable:
                    break
                demotable.sort(key=lambda x: x[1].score)
                idx, removed = demotable[0]
                replacement = pool.pop(0)
                result[idx] = replacement
                count -= 1
                changed = True

        if not changed:
            break

    return result


def assign_roles(moments: list[NarrativeMoment]) -> None:
    """Assign narrative roles in place based on position and score.

    Highest score = CLIMAX. Before climax = ESCALATION (first = INCITING).
    After climax = RESOLUTION (last = CODA). Single moment = CLIMAX.
    """
    if not moments:
        return
    if len(moments) == 1:
        moments[0].narrative_role = NarrativeRole.CLIMAX
        return

    moments.sort(key=lambda m: m.anchor_turn)
    climax = max(moments, key=lambda m: m.score)
    climax_idx = moments.index(climax)

    for i, m in enumerate(moments):
        if m is climax:
            m.narrative_role = NarrativeRole.CLIMAX
        elif i < climax_idx:
            m.narrative_role = NarrativeRole.ESCALATION
        else:
            m.narrative_role = NarrativeRole.RESOLUTION

    # First pre-climax moment = INCITING
    if climax_idx > 0:
        moments[0].narrative_role = NarrativeRole.INCITING

    # Last moment = CODA (unless it's the climax)
    if moments[-1] is not climax:
        moments[-1].narrative_role = NarrativeRole.CODA
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_curator.py -k "cluster or diversity or role_assignment" -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m20a): curator clustering, diversity penalty, and role assignment"
```

---

### Task 6: Curator Gap Summaries & Top-Level `curate()` Function

**Files:**
- Modify: `src/chronicler/curator.py`
- Modify: `tests/test_curator.py`

- [ ] **Step 1: Write tests for gap summaries and the main `curate()` function**

```python
# tests/test_curator.py — append

from chronicler.curator import build_gap_summaries, curate


def test_gap_summary_between_moments():
    """Gap summaries cover turns between selected moments."""
    events = [
        Event(turn=15, event_type="trade", actors=["A"], description="t", importance=3),
        Event(turn=20, event_type="war", actors=["B"], description="t", importance=3),
    ]
    moments = [
        NarrativeMoment(anchor_turn=10, turn_range=(8, 12), events=[], named_events=[],
                        score=10, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0),
        NarrativeMoment(anchor_turn=30, turn_range=(28, 32), events=[], named_events=[],
                        score=8, causal_links=[], narrative_role=NarrativeRole.RESOLUTION, bonus_applied=0),
    ]
    history = [
        _make_snapshot(12, {"r1": "A", "r2": "B"}),
        _make_snapshot(28, {"r1": "A", "r2": "A"}),  # A gained r2
    ]
    gaps = build_gap_summaries(moments, events, history)
    assert len(gaps) == 1
    assert gaps[0].turn_range == (13, 27)
    assert gaps[0].event_count == 2  # events at turn 15, 20
    assert gaps[0].territory_changes == 1  # r2: B→A


def test_gap_summary_stat_deltas():
    """stat_deltas computed from CivSnapshot diffs."""
    history = [
        _make_snapshot(12, {"r1": "A"}),  # default: pop=100, mil=50
    ]
    # Modify the second snapshot to have different stats
    snap2 = _make_snapshot(28, {"r1": "A"})
    snap2.civ_stats["A"].population = 80
    snap2.civ_stats["A"].military = 60
    history.append(snap2)

    moments = [
        NarrativeMoment(anchor_turn=10, turn_range=(8, 12), events=[], named_events=[],
                        score=10, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0),
        NarrativeMoment(anchor_turn=30, turn_range=(28, 32), events=[], named_events=[],
                        score=8, causal_links=[], narrative_role=NarrativeRole.RESOLUTION, bonus_applied=0),
    ]
    gaps = build_gap_summaries(moments, [], history)
    assert gaps[0].stat_deltas["A"]["population"] == -20
    assert gaps[0].stat_deltas["A"]["military"] == 10


def test_curate_end_to_end():
    """Top-level curate() produces moments and gap summaries."""
    events = [
        Event(turn=i, event_type="war" if i % 10 == 0 else "trade",
              actors=["A"], description="t", importance=8 if i % 10 == 0 else 3)
        for i in range(1, 51)
    ]
    history = [_make_snapshot(i, {"r1": "A", "r2": "B"}) for i in range(1, 51)]
    moments, gaps = curate(events, named_events=[], history=history, budget=3, seed=42)

    assert len(moments) <= 3
    assert all(isinstance(m, NarrativeMoment) for m in moments)
    assert all(isinstance(g, GapSummary) for g in gaps)
    # Moments should be sorted by anchor_turn
    assert moments == sorted(moments, key=lambda m: m.anchor_turn)
    # One of the moments should be CLIMAX
    assert any(m.narrative_role == NarrativeRole.CLIMAX for m in moments)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_curator.py::test_gap_summary_between_moments -v`
Expected: FAIL with `ImportError: cannot import name 'build_gap_summaries'`

- [ ] **Step 3: Implement gap summaries and `curate()`**

Add to `src/chronicler/curator.py`:

```python
_TRACKED_STATS = ("population", "military", "economy", "culture", "stability")


def build_gap_summaries(
    moments: list[NarrativeMoment],
    events: list[Event],
    history: list[TurnSnapshot],
) -> list[GapSummary]:
    """Build gap summaries for turns between selected moments."""
    if not moments:
        return []

    sorted_moments = sorted(moments, key=lambda m: m.anchor_turn)
    gaps: list[GapSummary] = []

    # Helper: find snapshot closest to a turn
    snap_by_turn = {s.turn: s for s in history}

    def _find_snap(turn: int) -> TurnSnapshot | None:
        if turn in snap_by_turn:
            return snap_by_turn[turn]
        # Find nearest
        closest = min(snap_by_turn.keys(), key=lambda t: abs(t - turn), default=None)
        return snap_by_turn.get(closest) if closest is not None else None

    for i in range(len(sorted_moments) - 1):
        gap_start = sorted_moments[i].turn_range[1] + 1
        gap_end = sorted_moments[i + 1].turn_range[0] - 1
        if gap_start > gap_end:
            continue

        gap_events = [e for e in events if gap_start <= e.turn <= gap_end]
        event_types = Counter(e.event_type for e in gap_events)
        top_type = event_types.most_common(1)[0][0] if event_types else ""

        # Stat deltas
        snap_start = _find_snap(gap_start)
        snap_end = _find_snap(gap_end)
        stat_deltas: dict[str, dict[str, int]] = {}
        territory_changes = 0

        if snap_start and snap_end:
            all_civs = set(snap_start.civ_stats.keys()) | set(snap_end.civ_stats.keys())
            for civ in all_civs:
                if civ in snap_start.civ_stats and civ in snap_end.civ_stats:
                    s0 = snap_start.civ_stats[civ]
                    s1 = snap_end.civ_stats[civ]
                    deltas = {}
                    for stat in _TRACKED_STATS:
                        delta = getattr(s1, stat) - getattr(s0, stat)
                        if delta != 0:
                            deltas[stat] = delta
                    if deltas:
                        stat_deltas[civ] = deltas

            # Territory changes
            for region in snap_start.region_control:
                c0 = snap_start.region_control.get(region)
                c1 = snap_end.region_control.get(region)
                if c0 != c1:
                    territory_changes += 1

        gaps.append(GapSummary(
            turn_range=(gap_start, gap_end),
            event_count=len(gap_events),
            top_event_type=top_type,
            stat_deltas=stat_deltas,
            territory_changes=territory_changes,
        ))

    return gaps


def curate(
    events: list[Event],
    named_events: list[NamedEvent],
    history: list[TurnSnapshot],
    budget: int = 50,
    seed: int = 0,
) -> tuple[list[NarrativeMoment], list[GapSummary]]:
    """Select the most narratively interesting moments and produce gap summaries.

    Three-pass algorithm:
    1. Base scoring (importance + named/dominant/rarity bonuses)
    2. Causal linking (pattern-specific max_gap, spatial filter)
    3. Cluster detection and budget allocation

    Then: diversity penalty, role assignment, gap summary generation.
    """
    if not events:
        return [], []

    # Sort events by turn for all passes
    events_sorted = sorted(events, key=lambda e: e.turn)

    # Pass 1: Base scoring
    dominant = compute_dominant_power(history, seed)
    scores = compute_base_scores(events_sorted, named_events, dominant, seed)

    # Pass 2: Causal linking
    all_links = compute_causal_links(events_sorted, scores)

    # Pass 3: Clustering
    clusters = build_clusters(events_sorted, scores)
    clusters.sort(key=lambda c: c["score"], reverse=True)

    # Select top budget clusters
    selected_clusters = clusters[:budget]
    unselected_clusters = clusters[budget:]

    # Build NarrativeMoments from selected clusters
    def _cluster_to_moment(cluster: dict) -> NarrativeMoment:
        indices = cluster["event_indices"]
        moment_events = [events_sorted[i] for i in indices]
        moment_named = [
            ne for ne in named_events
            if cluster["turn_range"][0] <= ne.turn <= cluster["turn_range"][1]
        ]
        # Collect causal links for events in this cluster
        moment_links = [
            link for link in all_links
            if any(events_sorted[i].turn == link.cause_turn for i in indices)
            or any(events_sorted[i].turn == link.effect_turn for i in indices)
        ]
        bonus = sum(scores[i] - float(events_sorted[i].importance) for i in indices)
        return NarrativeMoment(
            anchor_turn=cluster["anchor_turn"],
            turn_range=cluster["turn_range"],
            events=moment_events,
            named_events=moment_named,
            score=cluster["score"],
            causal_links=moment_links,
            narrative_role=NarrativeRole.ESCALATION,  # placeholder, assigned later
            bonus_applied=max(0, bonus),
        )

    selected = [_cluster_to_moment(c) for c in selected_clusters]
    unselected = [_cluster_to_moment(c) for c in unselected_clusters]

    # Diversity penalty
    selected = apply_diversity_penalty(selected, unselected)

    # Role assignment
    assign_roles(selected)

    # Sort by anchor_turn
    selected.sort(key=lambda m: m.anchor_turn)

    # Gap summaries
    gaps = build_gap_summaries(selected, events_sorted, history)

    return selected, gaps
```

- [ ] **Step 4: Run all curator tests**

Run: `python -m pytest tests/test_curator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m20a): curator gap summaries and top-level curate() function"
```

---

### Task 7: Curator Degenerate Path ("Narrate This")

**Files:**
- Modify: `src/chronicler/curator.py`
- Modify: `tests/test_curator.py`

- [ ] **Step 1: Write test for degenerate curator path**

```python
# tests/test_curator.py — append

def test_curate_degenerate_narrate_this():
    """Budget=1 path: no diversity, no role assignment, default RESOLUTION."""
    events = [
        Event(turn=20, event_type="war", actors=["A"], description="t", importance=9),
        Event(turn=22, event_type="famine", actors=["A"], description="t", importance=6),
        Event(turn=25, event_type="trade", actors=["B"], description="t", importance=3),
    ]
    history = [_make_snapshot(i, {"r1": "A", "r2": "B"}) for i in range(15, 35)]
    moments, gaps = curate(events, named_events=[], history=history, budget=1, seed=0)

    assert len(moments) == 1
    assert moments[0].narrative_role == NarrativeRole.RESOLUTION  # degenerate default
    assert moments[0].anchor_turn == 20  # highest-scoring event
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_curator.py::test_curate_degenerate_narrate_this -v`
Expected: FAIL — role will be CLIMAX (since single moment defaults to CLIMAX in current `assign_roles`)

- [ ] **Step 3: Update `curate()` to handle budget=1 degenerate path**

In `src/chronicler/curator.py`, modify the end of `curate()`:

```python
    # Diversity penalty (skip for budget=1 — degenerate "Narrate This" path)
    if budget > 1:
        selected = apply_diversity_penalty(selected, unselected)
        assign_roles(selected)
    else:
        # Degenerate path: default role = RESOLUTION
        for m in selected:
            m.narrative_role = NarrativeRole.RESOLUTION
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_curator.py::test_curate_degenerate_narrate_this -v`
Expected: PASS

- [ ] **Step 5: Run all curator tests to verify no regressions**

Run: `python -m pytest tests/test_curator.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/curator.py tests/test_curator.py
git commit -m "feat(m20a): curator degenerate path for on-demand narration"
```

---

## Chunk 3: Batch Narration & CLI Integration

### Task 8: Before/After Summaries and `NarrationContext`

**Files:**
- Modify: `src/chronicler/narrative.py`
- Create: `tests/test_batch_narration.py`

- [ ] **Step 1: Write tests for before/after summary generation**

```python
# tests/test_batch_narration.py

from chronicler.models import (
    TurnSnapshot, CivSnapshot, NarrativeMoment, NarrativeRole,
    Event, CausalLink,
)
from chronicler.narrative import build_before_summary, build_after_summary


def _make_snap(turn: int, civ: str, pop: int, mil: int, stab: int,
               regions: list[str]) -> TurnSnapshot:
    return TurnSnapshot(
        turn=turn,
        civ_stats={civ: CivSnapshot(
            population=pop, military=mil, economy=50, culture=50,
            stability=stab, treasury=100, asabiya=0.5,
            tech_era="CLASSICAL", trait="aggressive",
            regions=regions, leader_name="Leader", alive=True,
        )},
        region_control={r: civ for r in regions},
        relationships={},
    )


def test_before_summary_reports_stat_changes():
    """Before summary reports stat changes > 10."""
    history = [
        _make_snap(1, "A", pop=100, mil=50, stab=50, regions=["r1"]),
        _make_snap(10, "A", pop=80, mil=70, stab=30, regions=["r1", "r2"]),
    ]
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
    )
    summary = build_before_summary(history, moment, prev_moment=None)
    assert "population" in summary.lower() or "pop" in summary.lower()
    assert "military" in summary.lower() or "mil" in summary.lower()
    assert len(summary) > 0


def test_after_summary_enables_foreshadowing():
    """After summary looks forward from current moment."""
    history = [
        _make_snap(10, "A", pop=100, mil=50, stab=50, regions=["r1"]),
        _make_snap(30, "A", pop=50, mil=30, stab=10, regions=["r1"]),
    ]
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
    )
    next_moment = NarrativeMoment(
        anchor_turn=30, turn_range=(30, 30), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.RESOLUTION, bonus_applied=0,
    )
    summary = build_after_summary(history, moment, next_moment)
    assert len(summary) > 0


def test_before_summary_first_moment():
    """First moment (prev_moment=None) compares against turn 1."""
    history = [
        _make_snap(1, "A", pop=100, mil=50, stab=50, regions=["r1"]),
        _make_snap(10, "A", pop=60, mil=80, stab=20, regions=["r1"]),
    ]
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(10, 10), events=[], named_events=[],
        score=5.0, causal_links=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
    )
    summary = build_before_summary(history, moment, prev_moment=None)
    assert len(summary) > 0  # should produce output even without prev_moment
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_batch_narration.py::test_before_summary_reports_stat_changes -v`
Expected: FAIL with `ImportError: cannot import name 'build_before_summary'`

- [ ] **Step 3: Implement before/after summary builders**

Add to `src/chronicler/narrative.py` (after existing functions, before `NarrativeEngine` class):

```python
from chronicler.models import (
    NarrativeMoment, NarrationContext, NarrativeRole,
    GapSummary, CausalLink, CivThematicContext, ChronicleEntry,
    TurnSnapshot,
)

_SUMMARY_STATS = ("population", "military", "economy", "culture", "stability")
_STAT_THRESHOLD = 10  # only report changes > this


def build_before_summary(
    history: list[TurnSnapshot],
    moment: NarrativeMoment,
    prev_moment: NarrativeMoment | None,
) -> str:
    """Mechanical before-context: stat changes, territory, conditions."""
    snap_by_turn = {s.turn: s for s in history}

    ref_turn = prev_moment.anchor_turn if prev_moment else min(snap_by_turn.keys(), default=1)
    ref_snap = snap_by_turn.get(ref_turn)
    cur_snap = snap_by_turn.get(moment.anchor_turn)

    if not ref_snap or not cur_snap:
        return ""

    bullets: list[str] = []
    for civ in cur_snap.civ_stats:
        if civ not in ref_snap.civ_stats:
            bullets.append(f"- {civ} emerged")
            continue
        s0 = ref_snap.civ_stats[civ]
        s1 = cur_snap.civ_stats[civ]
        changes = []
        for stat in _SUMMARY_STATS:
            delta = getattr(s1, stat) - getattr(s0, stat)
            if abs(delta) > _STAT_THRESHOLD:
                direction = "rose" if delta > 0 else "fell"
                changes.append(f"{stat} {direction} from {getattr(s0, stat)} to {getattr(s1, stat)}")
        # Territory changes
        old_regions = set(s0.regions)
        new_regions = set(s1.regions)
        gained = new_regions - old_regions
        lost = old_regions - new_regions
        if gained:
            changes.append(f"gained {len(gained)} region(s)")
        if lost:
            changes.append(f"lost {len(lost)} region(s)")
        if changes:
            bullets.append(f"- {civ}: {', '.join(changes)}")

    return "\n".join(bullets[:5])  # cap at 5 bullet points


def build_after_summary(
    history: list[TurnSnapshot],
    moment: NarrativeMoment,
    next_moment: NarrativeMoment | None,
) -> str:
    """Mechanical after-context for foreshadowing."""
    snap_by_turn = {s.turn: s for s in history}

    ref_turn = next_moment.anchor_turn if next_moment else max(snap_by_turn.keys(), default=moment.anchor_turn)
    ref_snap = snap_by_turn.get(ref_turn)
    cur_snap = snap_by_turn.get(moment.anchor_turn)

    if not ref_snap or not cur_snap:
        return ""

    bullets: list[str] = []
    for civ in cur_snap.civ_stats:
        if civ not in ref_snap.civ_stats:
            bullets.append(f"- {civ} will disappear")
            continue
        s0 = cur_snap.civ_stats[civ]
        s1 = ref_snap.civ_stats[civ]
        changes = []
        for stat in _SUMMARY_STATS:
            delta = getattr(s1, stat) - getattr(s0, stat)
            if abs(delta) > _STAT_THRESHOLD:
                direction = "will rise" if delta > 0 else "will fall"
                changes.append(f"{stat} {direction} to {getattr(s1, stat)}")
        if changes:
            bullets.append(f"- {civ}: {', '.join(changes)}")

    return "\n".join(bullets[:5])


ROLE_INSTRUCTIONS: dict[NarrativeRole, str] = {
    NarrativeRole.INCITING: "Introduce the tension. Something has changed that cannot be undone.",
    NarrativeRole.ESCALATION: "Build on what came before. The stakes are rising.",
    NarrativeRole.CLIMAX: "This is the turning point. Maximum consequence, maximum drama.",
    NarrativeRole.RESOLUTION: "The dust settles. Show what was won and what was lost.",
    NarrativeRole.CODA: "Look back on what happened. Reflect on the arc of this history.",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_batch_narration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_batch_narration.py
git commit -m "feat(m20a): before/after summary builders and role instructions"
```

---

### Task 9: `narrate_batch()` Method

**Files:**
- Modify: `src/chronicler/narrative.py`
- Modify: `tests/test_batch_narration.py`

- [ ] **Step 1: Write test for `narrate_batch()`**

```python
# tests/test_batch_narration.py — append

from unittest.mock import MagicMock
from chronicler.narrative import NarrativeEngine


def test_narrate_batch_produces_chronicle_entries():
    """narrate_batch returns ChronicleEntry list with prose from LLM."""
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.return_value = "The war began at dawn."

    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)

    moments = [
        NarrativeMoment(
            anchor_turn=10, turn_range=(8, 12),
            events=[Event(turn=10, event_type="war", actors=["A"], description="t", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        ),
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 15)]
    gaps = []

    entries = engine.narrate_batch(moments, history, gaps)
    assert len(entries) == 1
    assert entries[0].narrative == "The war began at dawn."
    assert entries[0].turn == 10
    assert entries[0].narrative_role == NarrativeRole.CLIMAX
    assert entries[0].covers_turns == (8, 12)


def test_narrate_batch_fallback_on_error():
    """If LLM fails on a moment, that moment gets mechanical fallback."""
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.side_effect = Exception("LLM unavailable")

    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)

    moments = [
        NarrativeMoment(
            anchor_turn=10, turn_range=(10, 10),
            events=[Event(turn=10, event_type="war", actors=["A"], description="battle", importance=8)],
            named_events=[], score=10.0, causal_links=[],
            narrative_role=NarrativeRole.CLIMAX, bonus_applied=0,
        ),
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 15)]

    entries = engine.narrate_batch(moments, history, [])
    assert len(entries) == 1
    assert entries[0].narrative  # should have fallback text, not empty
    assert entries[0].turn == 10


def test_narrate_batch_progress_callback():
    """Progress callback fires for each moment."""
    mock_client = MagicMock()
    mock_client.model = "test-model"
    mock_client.complete.return_value = "Prose."

    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)

    moments = [
        NarrativeMoment(
            anchor_turn=i*10, turn_range=(i*10, i*10),
            events=[Event(turn=i*10, event_type="war", actors=["A"], description="t", importance=5)],
            named_events=[], score=5.0, causal_links=[],
            narrative_role=NarrativeRole.ESCALATION, bonus_applied=0,
        )
        for i in range(1, 4)
    ]
    history = [_make_snap(i, "A", 100, 50, 50, ["r1"]) for i in range(1, 35)]

    progress_calls = []
    entries = engine.narrate_batch(
        moments, history, [],
        on_progress=lambda completed, total, eta: progress_calls.append((completed, total)),
    )
    assert len(entries) == 3
    assert len(progress_calls) == 3
    assert progress_calls[-1] == (3, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_batch_narration.py::test_narrate_batch_produces_chronicle_entries -v`
Expected: FAIL with `AttributeError: 'NarrativeEngine' object has no attribute 'narrate_batch'`

- [ ] **Step 3: Implement `narrate_batch()` on `NarrativeEngine`**

Add to the `NarrativeEngine` class in `src/chronicler/narrative.py`:

```python
    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: list[TurnSnapshot],
        gap_summaries: list[GapSummary],
        on_progress: Callable[[int, int, float], None] | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate all selected moments sequentially with full context.

        Sequential processing — LM Studio saturates the GPU with one request.
        Per-moment fallback on LLM failure (mechanical summary, batch continues).
        """
        from time import time

        entries: list[ChronicleEntry] = []
        total = len(moments)
        tokens_per_sec = 30.0  # conservative default for 13B
        call_times: list[float] = []

        previous_prose: str | None = None

        for i, moment in enumerate(moments):
            # Build context
            prev_moment = moments[i - 1] if i > 0 else None
            next_moment = moments[i + 1] if i < total - 1 else None

            before = build_before_summary(history, moment, prev_moment)
            after = build_after_summary(history, moment, next_moment)
            role_inst = ROLE_INSTRUCTIONS.get(moment.narrative_role, "")

            causes = [
                f"Caused by {link.cause_event_type} at turn {link.cause_turn}"
                for link in moment.causal_links
                if link.effect_turn >= moment.turn_range[0]
                and link.effect_turn <= moment.turn_range[1]
                and link.cause_turn < moment.turn_range[0]
            ]
            consequences = [
                f"Will lead to {link.effect_event_type} at turn {link.effect_turn}"
                for link in moment.causal_links
                if link.cause_turn >= moment.turn_range[0]
                and link.cause_turn <= moment.turn_range[1]
                and link.effect_turn > moment.turn_range[1]
            ]

            # Build prompt
            event_lines = "\n".join(
                f"- Turn {e.turn}: {e.event_type} — {e.description}"
                for e in moment.events
            )
            named_lines = "\n".join(
                f"- {ne.name} (turn {ne.turn}): {ne.description}"
                for ne in moment.named_events
            )
            cause_lines = "\n".join(f"- {c}" for c in causes)
            consequence_lines = "\n".join(f"- {c}" for c in consequences)

            prompt_parts = [
                f"NARRATIVE ROLE: {role_inst}",
                f"\nEVENTS (turns {moment.turn_range[0]}-{moment.turn_range[1]}):\n{event_lines}",
            ]
            if named_lines:
                prompt_parts.append(f"\nNAMED EVENTS:\n{named_lines}")
            if before:
                prompt_parts.append(f"\nBEFORE (context):\n{before}")
            if after:
                prompt_parts.append(f"\nAFTER (foreshadowing):\n{after}")
            if cause_lines:
                prompt_parts.append(f"\nCAUSES:\n{cause_lines}")
            if consequence_lines:
                prompt_parts.append(f"\nCONSEQUENCES:\n{consequence_lines}")
            if previous_prose:
                prompt_parts.append(
                    f"\nPREVIOUS ENTRY (match this style):\n{previous_prose[:500]}"
                )

            prompt = "\n".join(prompt_parts)

            system = (
                "You are a literary historian chronicling a civilization simulation. "
                "Write 3-5 paragraphs of prose. No game mechanics terminology. "
                "Use the role instruction to set the tone."
            )
            if self.narrative_style:
                system += f"\n\nNARRATIVE STYLE: {self.narrative_style}"

            # Narrate with fallback
            start = time()
            try:
                narrative = self.narrative_client.complete(
                    prompt, max_tokens=1000, system=system,
                )
            except Exception:
                # Mechanical fallback
                narrative = f"[Turns {moment.turn_range[0]}-{moment.turn_range[1]}] " + \
                    "; ".join(e.description for e in moment.events[:5])
            elapsed = time() - start
            call_times.append(elapsed)

            previous_prose = narrative

            entries.append(ChronicleEntry(
                turn=moment.anchor_turn,
                covers_turns=moment.turn_range,
                events=moment.events,
                named_events=moment.named_events,
                narrative=narrative,
                importance=moment.score,
                narrative_role=moment.narrative_role,
                causal_links=moment.causal_links,
            ))

            # Progress callback
            if on_progress:
                # ETA from second call onward
                if len(call_times) >= 2:
                    avg_time = sum(call_times[1:]) / len(call_times[1:])
                else:
                    avg_time = call_times[0] if call_times else 10.0
                remaining = total - (i + 1)
                eta = remaining * avg_time
                on_progress(i + 1, total, eta)

        return entries
```

Note: The `NarrativeEngine` class needs access to `narrative_style`. Check if `self.narrative_style` exists or if it's stored differently. The existing `__init__` takes `narrative_style: str | None = None`. Store it as `self.narrative_style = narrative_style` if not already done.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_batch_narration.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_batch_narration.py
git commit -m "feat(m20a): narrate_batch() with full context and per-moment fallback"
```

---

### Task 10: Bundle Format Update, `compile_chronicle`, and `narrate` CLI

**Files:**
- Modify: `src/chronicler/bundle.py`
- Modify: `src/chronicler/chronicle.py`
- Modify: `src/chronicler/main.py`
- Modify: `tests/test_bundle.py`

- [ ] **Step 1: Write test for new bundle format round-trip**

```python
# tests/test_bundle.py — add

from chronicler.models import (
    ChronicleEntry, NarrativeRole, CausalLink, GapSummary, Event,
)
import json


def test_new_bundle_format_chronicle_entries():
    """chronicle_entries serializes as list of dicts, not dict of strings."""
    entry = ChronicleEntry(
        turn=10, covers_turns=(8, 12),
        events=[Event(turn=10, event_type="war", actors=["A"], description="t", importance=8)],
        named_events=[], narrative="Prose here.",
        importance=8.0, narrative_role=NarrativeRole.CLIMAX,
        causal_links=[],
    )
    gap = GapSummary(
        turn_range=(13, 20), event_count=5, top_event_type="trade",
        stat_deltas={"A": {"population": -10}}, territory_changes=1,
    )

    # Simulate what assemble_bundle produces
    data = {
        "chronicle_entries": [entry.model_dump()],
        "gap_summaries": [gap.model_dump()],
    }
    raw = json.dumps(data)
    loaded = json.loads(raw)

    # Verify list format
    assert isinstance(loaded["chronicle_entries"], list)
    assert len(loaded["chronicle_entries"]) == 1
    restored = ChronicleEntry.model_validate(loaded["chronicle_entries"][0])
    assert restored.narrative == "Prose here."
    assert restored.narrative_role == NarrativeRole.CLIMAX

    restored_gap = GapSummary.model_validate(loaded["gap_summaries"][0])
    assert restored_gap.event_count == 5


def test_legacy_bundle_detection():
    """Legacy bundles have chronicle_entries as dict, new as list."""
    legacy = {"chronicle_entries": {"1": "text", "2": "more text"}}
    new = {"chronicle_entries": [{"turn": 1, "narrative": "text"}]}

    assert not isinstance(legacy["chronicle_entries"], list)  # legacy
    assert isinstance(new["chronicle_entries"], list)          # new
```

- [ ] **Step 2: Run tests to verify they pass** (these test the format, not the function)

Run: `python -m pytest tests/test_bundle.py -k "new_bundle_format or legacy_bundle" -v`
Expected: PASS (pure data tests)

- [ ] **Step 3: Update `main.py` — add `--narrate` flag and skip ChronicleEntry loop in simulate-only**

In `src/chronicler/main.py`, add narrate flags to `_build_parser()` (~line 508-559). The parser is a flat `ArgumentParser` with no subparsers, so add flags:

```python
# In _build_parser(), add alongside other mode flags:
parser.add_argument("--narrate", type=Path, default=None,
                    help="Narrate a simulate-only bundle (path to JSON)")
parser.add_argument("--budget", type=int, default=50,
                    help="Number of moments to narrate (used with --narrate)")
parser.add_argument("--narrate-output", type=Path, default=None,
                    help="Output path for narrated bundle (default: {stem}_narrated.json)")
```

Add `--narrate` to the mode_flags mutual exclusion check (~line 567-583):

```python
# Add "narrate" to the list of mode flags
mode_flags = [f for f in ["batch", "fork", "interactive", "live", "resume", "analyze", "narrate"]
              if getattr(args, f, None)]
```

Add the narrate dispatch in `main()`, before the normal run path:

```python
if args.narrate:
    _run_narrate(args)
    return
```

Add the narrate dispatch function:

```python
def _run_narrate(args) -> None:
    """Load a simulate-only bundle, curate, narrate, write output."""
    import json
    from chronicler.curator import curate
    from chronicler.models import Event, NamedEvent, TurnSnapshot, ChronicleEntry
    from chronicler.narrative import NarrativeEngine
    from chronicler.llm import create_clients

    bundle_path = args.narrate
    with open(bundle_path) as f:
        bundle = json.load(f)

    events = [Event.model_validate(e) for e in bundle["events_timeline"]]
    named_events = [NamedEvent.model_validate(e) for e in bundle["named_events"]]
    history = [TurnSnapshot.model_validate(s) for s in bundle["history"]]
    seed = bundle["metadata"]["seed"]

    # Curate
    moments, gaps = curate(events, named_events, history, budget=args.budget, seed=seed)

    # Narrate
    _, narrative_client = create_clients()
    engine = NarrativeEngine(
        sim_client=narrative_client, narrative_client=narrative_client,
    )
    entries = engine.narrate_batch(moments, history, gaps,
                                   on_progress=lambda c, t, e: print(f"  [{c}/{t}] ETA: {e:.0f}s"))

    # Write narrated bundle
    bundle["chronicle_entries"] = [e.model_dump() for e in entries]
    bundle["gap_summaries"] = [g.model_dump() for g in gaps]

    output = args.narrate_output or bundle_path.with_stem(bundle_path.stem + "_narrated")
    with open(output, "w") as f:
        json.dump(bundle, f, indent=2, default=str)

    print(f"Narrated bundle written to {output}")
```

Also update the simulate-only path in `execute_run()` to skip the ChronicleEntry construction loop when `--simulate-only` is set. Find the ChronicleEntry append (~line 277-280) and wrap it:

```python
if not simulate_only:
    chronicle_entries.append(ChronicleEntry(
        turn=world.turn, covers_turns=(world.turn, world.turn),
        events=turn_events, named_events=[],
        narrative=chronicle_text, importance=5.0,
        narrative_role=NarrativeRole.RESOLUTION,
        causal_links=[],
    ))
```

- [ ] **Step 4: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py src/chronicler/bundle.py src/chronicler/chronicle.py tests/test_bundle.py
git commit -m "feat(m20a): narrate CLI subcommand, bundle format update, simulate-only fix"
```

---

## Chunk 4: Viewer Updates

### Task 11: TypeScript Types and Legacy Detection

**Files:**
- Modify: `viewer/src/types.ts`

- [ ] **Step 1: Add new TypeScript interfaces**

At the end of `viewer/src/types.ts` (after existing interfaces), add:

```typescript
// --- M20a: Narration Pipeline v2 types ---

export interface NewChronicleEntry {
    turn: number;
    covers_turns: [number, number];
    events: Event[];
    named_events: NamedEvent[];
    narrative: string;
    importance: number;
    narrative_role: "inciting" | "escalation" | "climax" | "resolution" | "coda";
    causal_links: CausalLink[];
}

export interface GapSummary {
    turn_range: [number, number];
    event_count: number;
    top_event_type: string;
    stat_deltas: Record<string, Record<string, number>>;
    territory_changes: number;
}

export interface CausalLink {
    cause_turn: number;
    cause_event_type: string;
    effect_turn: number;
    effect_event_type: string;
    pattern: string;
}

export type BundleChronicle =
    | Record<string, string>       // legacy: turn → text
    | NewChronicleEntry[];         // new: sparse entries

export function isLegacyBundle(
    chronicle: BundleChronicle
): chronicle is Record<string, string> {
    return !Array.isArray(chronicle);
}
```

Note: named `NewChronicleEntry` to avoid conflicts with any existing TS type. Can rename later when old references are cleaned up.

- [ ] **Step 2: Update `Bundle` interface** (at line 162)

Change the `chronicle_entries` field in the `Bundle` interface:

```typescript
chronicle_entries: BundleChronicle;  // was Record<string, string>
gap_summaries?: GapSummary[];       // new
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd viewer && npx tsc --noEmit`
Expected: Compilation succeeds (or shows only pre-existing errors)

- [ ] **Step 4: Commit**

```bash
git add viewer/src/types.ts
git commit -m "feat(m20a): viewer TypeScript types for narration pipeline v2"
```

---

### Task 12: Segmented Timeline (`TimelineScrubber`)

**Files:**
- Modify: `viewer/src/components/TimelineScrubber.tsx`

- [ ] **Step 1: Update `TimelineScrubber` props**

Update the props interface to accept the new bundle types:

```typescript
import { NewChronicleEntry, GapSummary, CausalLink, BundleChronicle, isLegacyBundle } from '../types';

interface TimelineScrubberProps {
    currentTurn: number;
    maxTurn: number;
    playing: boolean;
    speed: number;
    history: TurnSnapshot[];
    namedEvents: NamedEvent[];
    chronicleEntries: BundleChronicle;
    gapSummaries?: GapSummary[];
    onSeek: (turn: number) => void;
    onPlay: () => void;
    onPause: () => void;
    onSetSpeed: (speed: number) => void;
    followMode?: boolean;
    onToggleFollowMode?: () => void;
    onNarrateRange?: (startTurn: number, endTurn: number) => void;
    showCausalLinks?: boolean;
}
```

- [ ] **Step 2: Implement segmented timeline rendering**

The component should:
1. Check `isLegacyBundle(chronicleEntries)` — if legacy, render the existing continuous timeline
2. If new format, render segments:
   - Narrated segments from `NewChronicleEntry[]`, colored by `narrative_role`
   - Mechanical segments from `GapSummary[]`, gray
   - Era reflections as dividers

Role colors:
```typescript
const ROLE_COLORS: Record<string, string> = {
    inciting: '#3b82f6',    // blue
    escalation: '#f97316',  // orange
    climax: '#ef4444',      // red
    resolution: '#22c55e',  // green
    coda: '#9ca3af',        // gray
};
```

Each narrated segment is a clickable block. Mechanical segments show event count and a "Narrate This" button (only when `onNarrateRange` prop is provided — hidden for static bundles).

- [ ] **Step 3: Add causal link overlay**

When `showCausalLinks` is true and entries are new format, render SVG arcs between causally linked segments. Each arc labeled with `link.pattern`.

- [ ] **Step 4: Verify renders correctly**

Run: `cd viewer && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add viewer/src/components/TimelineScrubber.tsx
git commit -m "feat(m20a): segmented timeline with role colors and causal overlay"
```

---

### Task 13: Chronicle Panel Rewrite

**Files:**
- Modify: `viewer/src/components/ChroniclePanel.tsx`

- [ ] **Step 1: Update `ChroniclePanel` to handle both formats**

```typescript
import { BundleChronicle, isLegacyBundle, NewChronicleEntry, GapSummary } from '../types';

interface ChroniclePanelProps {
    chronicleEntries: BundleChronicle;
    gapSummaries?: GapSummary[];
    eraReflections: Record<string, string>;
    currentTurn: number;
    maxTurn: number;
    focusedSegment?: { type: 'narrated' | 'mechanical' | 'reflection'; index: number } | null;
}
```

- [ ] **Step 2: Implement context-dependent rendering**

The component should:
1. If `isLegacyBundle()` → render existing turn-by-turn text list (preserve current behavior)
2. If new format + narrated segment focused → show prose + event list + causal annotations
3. If new format + mechanical segment focused → show `EventLog` filtered to turn range
4. If new format + era reflection focused → show reflection text

- [ ] **Step 3: Verify renders correctly**

Run: `cd viewer && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add viewer/src/components/ChroniclePanel.tsx
git commit -m "feat(m20a): context-dependent chronicle panel with legacy fallback"
```

---

### Task 14: "Narrate This" WebSocket Integration

**Files:**
- Modify: `src/chronicler/live.py`
- Modify: `viewer/src/hooks/useLiveConnection.ts`

- [ ] **Step 1: Add `narrate_range` handler to `live.py`**

In the WebSocket message handler (~line 130-158 in `LiveServer._serve`), add a new case **before** the "Other commands only accepted while paused" guard (line 150), alongside `speed` and `quit` which are always accepted:

```python
                    if msg_type == "narrate_range":
                        # Always accepted (not a simulation command)
                        start_turn = msg.get("start_turn")
                        end_turn = msg.get("end_turn")
                        await websocket.send(json.dumps({
                            "type": "narration_started",
                            "start_turn": start_turn, "end_turn": end_turn,
                        }))

                        # Data lives in self._init_data (accumulated turn data)
                        from chronicler.models import Event, NamedEvent, TurnSnapshot
                        from chronicler.curator import curate
                        from chronicler.narrative import NarrativeEngine
                        from chronicler.llm import create_clients

                        all_events = [
                            Event.model_validate(e)
                            for e in self._init_data.get("events_timeline", [])
                        ]
                        all_named = [
                            NamedEvent.model_validate(e)
                            for e in self._init_data.get("named_events", [])
                        ]
                        all_history = [
                            TurnSnapshot.model_validate(s)
                            for s in self._init_data.get("history", [])
                        ]
                        seed = self._init_data.get("metadata", {}).get("seed", 0)

                        range_events = [
                            e for e in all_events
                            if start_turn <= e.turn <= end_turn
                        ]
                        moments, _ = curate(
                            range_events, all_named, all_history,
                            budget=1, seed=seed,
                        )
                        if moments:
                            _, narrative_client = create_clients()
                            engine = NarrativeEngine(
                                sim_client=narrative_client,
                                narrative_client=narrative_client,
                            )
                            entries = engine.narrate_batch(moments, all_history, [])
                            if entries:
                                await websocket.send(json.dumps({
                                    "type": "narration_complete",
                                    "entry": entries[0].model_dump(),
                                }))
                        continue
```

**Architecture note:** `LiveServer` stores all accumulated data in `self._init_data` (a dict, not typed objects). Events are at `self._init_data["events_timeline"]`, named events at `self._init_data["named_events"]`, history at `self._init_data["history"]`. The handler deserializes these on-the-fly. The `NarrativeEngine` is created per-request since it doesn't persist on `LiveServer`.

- [ ] **Step 2: Add `narrate_range` message handler to `useLiveConnection.ts`**

In the message handler switch (~line 96-209), add cases:

```typescript
case "narration_started":
    // Optional: could show a loading indicator
    break;

case "narration_complete":
    // Insert narrated entry into the chronicle
    if (msg.entry) {
        // Update chronicle_entries if it's new format
        // This will be handled by the parent component's state update
        dispatch({ type: 'NARRATION_COMPLETE', entry: msg.entry });
    }
    break;
```

- [ ] **Step 3: Verify TypeScript compiles and Python tests pass**

Run: `cd viewer && npx tsc --noEmit` and `python -m pytest tests/test_live.py -v`
Expected: Both succeed

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/live.py viewer/src/hooks/useLiveConnection.ts
git commit -m "feat(m20a): narrate-this WebSocket handler for on-demand narration"
```

---

## Chunk 5: Integration Testing

### Task 15: End-to-End Integration Test

**Files:**
- Modify: `tests/test_batch_narration.py`

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_batch_narration.py — append

from unittest.mock import MagicMock, patch
from chronicler.curator import curate
from chronicler.models import ChronicleEntry, GapSummary, NarrativeRole
import json


def test_end_to_end_simulate_curate_narrate():
    """Full pipeline: curate hand-crafted events → narrate → verify bundle."""
    # Use hand-crafted events and history (no real simulation needed)
    # Build minimal world (reuse existing test fixtures if available)
    # For this test, we'll use hand-crafted events and history
    events = [
        Event(turn=1, event_type="drought", actors=["A"], description="drought hits", importance=7),
        Event(turn=3, event_type="war", actors=["A", "B"], description="war begins", importance=9),
        Event(turn=5, event_type="famine", actors=["A"], description="famine", importance=8),
        Event(turn=7, event_type="trade", actors=["B"], description="trade", importance=3),
        Event(turn=9, event_type="collapse", actors=["A"], description="collapse", importance=10),
    ]
    history = [_make_snap(i, "A", 100 - i*5, 50, 50 - i*3, ["r1"]) for i in range(1, 11)]

    # Curate
    moments, gaps = curate(events, named_events=[], history=history, budget=3, seed=42)

    assert len(moments) <= 3
    assert all(isinstance(m.narrative_role, NarrativeRole) for m in moments)

    # Narrate with mock LLM
    mock_client = MagicMock()
    mock_client.model = "test"
    mock_client.complete.return_value = "Chronicle prose."
    engine = NarrativeEngine(sim_client=mock_client, narrative_client=mock_client)

    entries = engine.narrate_batch(moments, history, gaps)

    assert len(entries) == len(moments)
    assert all(isinstance(e, ChronicleEntry) for e in entries)
    assert all(e.narrative == "Chronicle prose." for e in entries)

    # Verify bundle format
    bundle_data = {
        "chronicle_entries": [e.model_dump() for e in entries],
        "gap_summaries": [g.model_dump() for g in gaps],
    }
    raw = json.dumps(bundle_data, default=str)
    loaded = json.loads(raw)

    assert isinstance(loaded["chronicle_entries"], list)
    for entry_data in loaded["chronicle_entries"]:
        restored = ChronicleEntry.model_validate(entry_data)
        assert restored.narrative_role in list(NarrativeRole)

    # Verify gaps + entries cover the full timeline
    all_turns = set()
    for e in entries:
        for t in range(e.covers_turns[0], e.covers_turns[1] + 1):
            all_turns.add(t)
    for g in gaps:
        for t in range(g.turn_range[0], g.turn_range[1] + 1):
            all_turns.add(t)
    # Not all turns need to be covered (gaps only exist between moments),
    # but no turn should appear in both a moment and a gap
    moment_turns = set()
    for e in entries:
        for t in range(e.covers_turns[0], e.covers_turns[1] + 1):
            moment_turns.add(t)
    gap_turns = set()
    for g in gaps:
        for t in range(g.turn_range[0], g.turn_range[1] + 1):
            gap_turns.add(t)
    assert not (moment_turns & gap_turns), "Moment and gap turns should not overlap"
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/test_batch_narration.py::test_end_to_end_simulate_curate_narrate -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_batch_narration.py
git commit -m "test(m20a): end-to-end integration test for narration pipeline"
```

---

## Task Summary

| Task | Component | Files | Est. Lines |
|------|-----------|-------|------------|
| 1 | Data models | `models.py`, `test_models.py` | ~90 |
| 2 | ChronicleEntry migration | `models.py`, `chronicle.py`, `bundle.py`, `main.py` | ~80 |
| 3 | Curator base scoring | `curator.py`, `test_curator.py` | ~100 |
| 4 | Curator causal linking | `curator.py`, `test_curator.py` | ~60 |
| 5 | Curator clustering/diversity/roles | `curator.py`, `test_curator.py` | ~150 |
| 6 | Curator gaps + `curate()` | `curator.py`, `test_curator.py` | ~120 |
| 7 | Curator degenerate path | `curator.py`, `test_curator.py` | ~20 |
| 8 | Before/after summaries | `narrative.py`, `test_batch_narration.py` | ~100 |
| 9 | `narrate_batch()` | `narrative.py`, `test_batch_narration.py` | ~130 |
| 10 | Bundle + CLI | `bundle.py`, `chronicle.py`, `main.py` | ~80 |
| 11 | Viewer types | `types.ts` | ~40 |
| 12 | Segmented timeline | `TimelineScrubber.tsx` | ~200 |
| 13 | Chronicle panel | `ChroniclePanel.tsx` | ~80 |
| 14 | "Narrate This" WebSocket | `live.py`, `useLiveConnection.ts` | ~45 |
| 15 | Integration test | `test_batch_narration.py` | ~50 |
| **Total** | | | **~1,345** |

## Parallelism

Tasks that can run in parallel (no shared state):
- **Tasks 3-7** (curator) are sequential within themselves but independent of Tasks 8-10
- **Tasks 11-13** (viewer) are independent of Python work and can run in parallel with Tasks 8-10
- **Task 14** depends on Tasks 11 and the Python curator (Task 7)
- **Task 15** depends on all other tasks
