# M20 Narrative Curator — Design Sketch

> Pre-spec design sketch for the M20 narration pipeline v2. Independent of M18.
> Reference this when writing the full M20 spec.

---

## Current State

The narrator makes one LLM call per turn via a `Narrator = Callable[[WorldState, list[Event]], str]` callback inside `run_turn()`. Each call gets the current world state + that turn's events, with recent named events (last 5) and leader rivalries injected into the prompt. Output is stored as `{turn: text}` in the bundle. Reflections are generated every N turns as era summaries.

Problems with this approach: no knowledge of future events (can't foreshadow), no narrative arc across turns (each entry is isolated), LLM called 500 times for a 500-turn run (expensive, slow), and every turn gets equal narrative weight regardless of importance.

---

## Architecture: Three-Phase Pipeline

### Phase 1: Simulate (CPU, seconds)

No change to `run_turn`. The simulation runs to completion with `narrator=lambda w, e: ""` (no-op narrator). All events accumulate in `world.events_timeline`. All snapshots accumulate in history. This is the existing `--simulate-only` path.

### Phase 2: Curate (CPU, milliseconds)

New `curator.py` module. Pure Python, no LLM. Selects the N most narratively important moments from the full event timeline.

### Phase 3: Narrate (GPU, minutes)

Batch narration. Each selected moment gets one LLM call with full before/after context. 40-60 calls instead of 500.

---

## Curator Design

### Input

```python
def curate(
    events: list[Event],
    named_events: list[NamedEvent],
    history: list[TurnSnapshot],
    budget: int = 50,
    seed: int = 0,
) -> list[NarrativeMoment]:
```

### Output: NarrativeMoment

```python
class NarrativeMoment(BaseModel):
    anchor_turn: int                    # the turn this moment centers on
    turn_range: tuple[int, int]         # inclusive range to narrate (e.g., 134-147)
    events: list[Event]                 # curated events within the range
    named_events: list[NamedEvent]      # named events within the range
    score: float                        # curator importance score
    causal_links: list[CausalLink]      # forward/backward event connections
    narrative_role: str                 # "inciting", "escalation", "climax", "resolution", "coda"
```

### Scoring Algorithm

Three passes over the event timeline:

**Pass 1: Base Scoring.** Every event gets a base score from `event.importance` (1-10). Named events get +3. Events involving the run's eventual dominant power get +2. Events of types that occur fewer than 3 times in the run get +2 (rare events are interesting).

**Pass 2: Causal Linking.** Forward scan. For each event E at turn T, check events in turns T+1 through T+20 for causal connections:

```python
CAUSAL_PATTERNS = [
    # (cause_type, effect_type, max_gap, bonus)
    ("drought", "famine", 10, +3),
    ("drought", "migration", 15, +2),
    ("famine", "rebellion", 10, +3),
    ("famine", "secession", 15, +3),
    ("war", "collapse", 20, +4),
    ("war", "leader_death", 5, +2),
    ("leader_death", "succession_crisis", 1, +3),
    ("succession_crisis", "coup", 5, +3),
    ("plague", "famine", 10, +2),
    ("embargo", "rebellion", 15, +2),
    ("tech_advancement", "war", 10, +2),         # new tech enables aggression
    ("cultural_renaissance", "movement", 10, +2), # cultural boom spawns ideology
    ("discovery", "war", 15, +2),                 # resource discovery triggers conflict
]
```

Spatial linking: if cause and effect share an actor (civ name) or region, the causal bonus is applied. If they share neither, the link is discarded. This prevents spurious connections between unrelated events.

The cause event receives the causal bonus (it's promoted because it *leads to* something important). The effect event keeps its own score. Both are marked as causally linked.

**Pass 3: Cluster Detection and Budget Allocation.** Group events into clusters where adjacent events within 5 turns of each other merge into a single cluster. Each cluster's score is the sum of its top 3 member scores (not all members — prevents inflation from many low-importance events).

Select top `budget` clusters by score. For each selected cluster, the `turn_range` spans from the earliest to latest event in the cluster.

### Narrative Role Assignment

After selection, assign roles based on position and score:

```python
def assign_roles(moments: list[NarrativeMoment]) -> None:
    # Sort by anchor_turn
    moments.sort(key=lambda m: m.anchor_turn)

    # The highest-scoring moment is the climax
    climax = max(moments, key=lambda m: m.score)
    climax.narrative_role = "climax"

    # Moments before climax with causal links forward are "escalation"
    # The first escalation moment is "inciting"
    # Moments after climax are "resolution"
    # The final moment is "coda"
```

Roles are hints for the narrator prompt — they tell the LLM whether to build tension, release it, or reflect.

### Diversity Penalty

After initial selection, apply a diversity penalty to prevent the curator from over-representing a single civ or event type:

- If >40% of selected moments involve the same civ, demote the lowest-scored moments for that civ and replace with the next-highest unselected moments
- If >30% of selected moments are the same event type, same treatment
- Named events are exempt from demotion (they're always interesting)

### Gap Handling

Turns between selected moments are "mechanical gaps." The curator doesn't narrate them, but it produces a gap summary for each:

```python
class GapSummary(BaseModel):
    turn_range: tuple[int, int]
    event_count: int
    top_event_type: str          # most common event type in gap
    stat_deltas: dict[str, int]  # net change per civ across gap (pop, mil, etc.)
    territory_changes: int       # number of region controller changes
```

Gap summaries feed the viewer's mechanical segment display and the narrator's context (so narrated moments know what happened "off-screen").

---

## Narration Context Window

Each LLM call for a `NarrativeMoment` receives:

```python
class NarrationContext(BaseModel):
    # The moment being narrated
    moment: NarrativeMoment

    # World state at the anchor turn
    snapshot: TurnSnapshot

    # Compressed before-context (previous 20 turns or previous narrated moment)
    before_summary: str    # mechanical: "Vrashni expanded to 5 regions, Kethani
                           # lost a war, stability declined from 45 to 22"

    # Compressed after-context (next 20 turns or next narrated moment)
    after_summary: str     # enables foreshadowing: "This drought will lead to
                           # the secession of the northern provinces in 13 turns"

    # Narrative role instruction
    role_instruction: str  # "This is an escalation moment. Build tension."

    # Causal context
    causes: list[str]      # "This famine was caused by the drought of turn 134"
    consequences: list[str] # "This will lead to the rebellion of turn 160"

    # Named events in range (for proper names)
    named_events: list[NamedEvent]

    # Recent prose (last narrated moment's output, for style continuity)
    previous_prose: str | None

    # Civ domains and values (for thematic threading)
    civ_context: dict[str, CivThematicContext]
```

### Before/After Summary Generation

These are NOT LLM calls. They're mechanical templates filled from snapshots:

```python
def build_before_summary(history, moment, prev_moment) -> str:
    """
    Compare snapshot at prev_moment.anchor_turn to snapshot at moment.anchor_turn.
    Report: stat changes > 10, territory gains/losses, new conditions, era changes.
    Returns 3-5 bullet points as a single string.
    """
```

The after-summary is the same but forward-looking. Since we have the full history, we can tell the narrator "this drought leads to famine in 8 turns" — real foreshadowing from data, not LLM hallucination.

---

## Bundle Format Change

```python
class ChronicleEntry(BaseModel):
    turn: int                          # anchor turn
    covers_turns: tuple[int, int]      # inclusive range
    events: list[Event]                # curated events
    named_events: list[NamedEvent]     # named events in range
    narrative: str                     # LLM output
    importance: float                  # curator score
    narrative_role: str                # inciting/escalation/climax/resolution/coda
    causal_links: list[CausalLink]     # for viewer visualization
```

Bundle changes:
- `chronicle_entries` becomes `list[ChronicleEntry]` (was `dict[str, str]`)
- `gap_summaries` added: `list[GapSummary]` for mechanical segments
- `era_reflections` stay as-is (they're orthogonal — chapter breaks between narrated moments)

### Backward Compatibility

Old bundles have `chronicle_entries: {turn: text}`. The viewer detects the format:
- If dict → legacy mode (render every turn as text)
- If list of `ChronicleEntry` → new mode (segmented timeline)

---

## LM Studio Batch Integration

```python
class BatchNarrator:
    def __init__(self, client: LLMClient, concurrency: int = 1):
        self.client = client
        self.concurrency = concurrency  # 1 for LM Studio (saturates GPU)

    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: list[TurnSnapshot],
        gap_summaries: list[GapSummary],
    ) -> list[ChronicleEntry]:
        """
        Sequential narration with progress bar.
        Each moment gets one LLM call with full context.

        At ~40 tok/s with 13B model:
          50 moments × ~500 output tokens = ~25,000 tokens
          ~10 minutes total
        """
```

Progress reporting via callback: `on_progress(completed: int, total: int, eta_seconds: float)`.

---

## Viewer Changes

### Segmented Timeline

The `TimelineScrubber` component changes from a continuous track to a segmented bar:

```
Turn  1────30  31──────45  46────────90  91───120  ...
      [prose]  [mechanic]  [prose]       [mech]
      ▼ open   ▸ 15 evts   ▼ open       ▸ 30 evts
```

- **Narrated segments** (ChronicleEntry): colored by `narrative_role` (blue=inciting, orange=escalation, red=climax, green=resolution, gray=coda). Click to expand prose. Default expanded for importance ≥ 8.
- **Mechanical segments** (GapSummary): collapsed single row. Shows event count + stat delta sparkline. Click to expand into existing event log view.
- **Causal links**: optional overlay lines connecting causally linked moments.

### "Narrate This" Button

On mechanical segments. Sends the turn range to the batch narrator. Result inserts into the bundle; viewer updates in place. This lets the user selectively narrate interesting gaps the curator missed.

### Era Reflections

Rendered as full-width dividers between segments, same as today but visually distinct (centered text, decorative borders). They mark "chapters" — natural breaks in the chronicle.

### Chronicle Panel

Replaces the scrollable turn-by-turn list. Now shows:
- Selected moment's prose (if narrated segment focused)
- Event log (if mechanical segment focused)
- Causal link annotations in margins ("→ leads to The Siege of Meridia, turn 147")

---

## Existing Infrastructure Preserved

- `NarrativeEngine` class stays. Gets a new `narrate_batch()` method alongside existing `generate_chronicle()`.
- `MemoryStream` stays. Memories are still recorded per-turn for the action selector's context.
- `interestingness.py` stays. Run-level scoring is orthogonal to within-run curation.
- `compile_chronicle()` updated to work with `list[ChronicleEntry]` instead of `list[ChronicleEntry(turn, text)]`.
- Reflection generation stays. Reflections are triggered by turn interval, not by the narrator.

---

## Batch Runner GUI (M12c Setup Lobby Extension)

The M12c setup lobby already provides run configuration via browser. M20 adds a **Batch Run** tab that wraps M19's CLI tooling (`run_batch`, `analyze_batch`) in a visual interface.

### Batch Configuration Panel

```
┌─────────────────────────────────────────────────┐
│  🔬 Batch Run                                    │
│                                                   │
│  Seed range: [1] to [200]        Turns: [500]    │
│  Workers: [auto]   ☑ Simulate only               │
│                                                   │
│  Tuning: [default] ▾   [Edit YAML...]            │
│                                                   │
│  [▶ Run Batch]              Progress: ████░ 142/200│
└─────────────────────────────────────────────────┘
```

Maps directly to CLI flags: `--seed-range`, `--turns`, `--parallel`, `--simulate-only`, `--tuning`.

### Analytics Display

After batch completes, renders `batch_report.json` inline:

- **Stability chart**: sparkline per checkpoint turn (50/100/200/500), median + 25th/75th percentile bands
- **Firing rate table**: sortable by event type, showing count, % of runs, median turn, with heat-map coloring
- **Anomaly panel**: degenerate pattern flags from `anomaly_detector`, color-coded (red = critical, yellow = warning)
- **Never-fire list**: mechanics that triggered in 0 runs, with suggested diagnostic
- **System cards**: collapsible per-system metric summary (one card per M13-M18 extractor)

### Compare Mode

Load two `batch_report.json` files (e.g., baseline vs. tuned). Side-by-side distributions with green/red diff highlighting for improved/degraded metrics. Useful for M19b tuning iterations.

### Architecture

- **Backend**: thin endpoint wrapping `run_batch()` and `analyze_batch()` — no new analytics logic
- **Frontend**: `BatchPanel` React component consuming `batch_report.json` schema
- **Progress**: WebSocket events for per-seed completion (reuses live mode socket)
- **Charts**: recharts (already a viewer dependency) for stability sparklines and distribution plots

### Scope Boundary

The batch GUI is a testing accelerator. M19b tuning can proceed CLI-only. The GUI makes iterative tuning faster and more visual — it's viewer work, which is why it lives in M20.

---

## What This Sketch Does NOT Cover

- **Exact LLM prompt templates.** These depend on which model (13B local vs Claude API) and the prompt engineering iteration. The sketch defines what context is available; the spec defines how to present it.
- **"Narrate This" WebSocket protocol.** The viewer-to-server protocol for on-demand narration is a spec detail.
- **Prose quality scoring.** Whether to score LLM output and retry on low quality is a spec decision. The architecture supports it (just re-call with adjusted prompt) but doesn't mandate it.
- **Multi-model routing.** Whether high-importance moments go to Claude API while low-importance ones go to local LM Studio is a deployment decision, not an architecture one.

---

## Open Design Questions

1. **Should reflections also go through the curator?** Currently reflections fire every N turns regardless of narrative importance. The curator could suppress reflections in uninteresting eras and promote them in eventful ones. Tradeoff: reflections as fixed chapter breaks (simple, predictable) vs. reflections as curator-selected (better pacing, more complex).

> **Phoebe answer: No — keep reflections as fixed chapter breaks.** Reflections serve a structural role: the reader's breathing room between narrative clusters. Suppressing reflections in quiet eras creates a gap that feels like missing content, not deliberate pacing. The curator handles narrative density; reflections handle rhythm. Let them be orthogonal.
>
> One concession worth implementing: the curator can flag reflection intervals where nothing meaningful happened (all stat deltas < 5, no events above importance 4). The reflection prompt template can then acknowledge the quiet — "The long peace between..." — rather than straining to dramatize a non-event. That's a prompt template change, not a curator architecture change.

2. **Should the curator run incrementally for live mode?** Live mode (WebSocket) currently narrates every turn. With the curator, live mode could buffer 10-20 turns, curate, then narrate the interesting ones. Tradeoff: latency (user waits 10-20 turns for prose) vs. quality (curator can link causes to effects).

> **Phoebe answer: Not in M20. Revisit in Phase 5.** Buffered curation fundamentally changes the live mode contract. Live mode is "watch history unfold turn by turn" — immediacy is the point. Buffering turns it into "wait, then get a curated summary," which is a different product.
>
> Better path: live mode keeps turn-by-turn narration (existing behavior). The curator runs as a post-processing pass when the run completes. The viewer offers a "curated view" toggle after the run finishes, so the user gets both: real-time narration during the run, curated re-read afterward.
>
> If buffered live curation is worth revisiting later, it needs its own UX design — progress indicators, "curating..." state, preview of buffered events. That's Phase 5 scope.

3. **Causal link depth.** The sketch uses a 20-turn forward window. Longer windows catch more connections but are slower and may produce spurious links. The right window size depends on game pacing, which M19b will establish.

> **Phoebe answer: Start at 20, parameterize, validate with M19b analytics.** 20 turns is reasonable based on Phase 3 event pacing — most cause-effect chains (drought → famine → secession) resolve within 15 turns.
>
> The spec should expose it as a curator constant: `CAUSAL_WINDOW = 20`, overridable via M19's tuning YAML. M19b can run the curator on 200 batch results with window=10, 20, 30 and compare link yield. If window=20 catches 95% of the links window=30 does, 20 is correct. If window=10 catches 90%, drop to 10 for speed.
>
> The spatial filter (shared actor or region) already mitigates spurious links, but wider windows increase false positive candidates before filtering. 20 is conservative enough to ship.
