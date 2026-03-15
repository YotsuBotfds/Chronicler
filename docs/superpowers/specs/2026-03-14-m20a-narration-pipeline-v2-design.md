# M20a: Narration Pipeline v2 — Design Spec

> Narration with full history context, not turn-by-turn isolation. The current narrator calls the LLM once per turn, in isolation. The new narrator runs after the simulation completes, selects the most narratively interesting moments, and narrates them with full before/after context. Better output, fewer LLM calls, natural use of the CPU/GPU split.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Pipeline architecture | Three-phase: Simulate (CPU) → Curate (CPU) → Narrate (GPU) | Decouples computation from narration. Simulation runs in seconds; narration runs in minutes with full history context. User inspects simulation before spending GPU time. |
| Reflections | Fixed interval, not curator-managed | Reflections provide periodic synthesis — a different purpose than moment curation. Quiet eras need a voice too; "nothing happened, the empire consolidated" is pacing, not waste. |
| Live mode | No buffered curation, curator is post-processing only | Live mode's value is turn-by-turn immediacy. A 10-turn buffer gives the curator almost nothing to work with (causal patterns use up to 20-turn windows). Users wanting curated prose from a live run re-narrate the bundle after completion. |
| Causal link depth | Pattern-specific `max_gap`, no global window | Each `CAUSAL_PATTERNS` entry already has `max_gap`. A leader_death→succession_crisis scans 1 turn; a war→collapse scans 20. Using the per-pattern value is more accurate than a global constant and simpler than multi-hop recursion. |
| Multi-hop chains | Single-hop links only; chains emerge from overlapping links | Drought→famine→secession: famine gets promoted twice (as effect of drought, as cause of secession). The arc emerges from overlapping single-hop links without recursive scanning. |
| Batch narrator location | Method on `NarrativeEngine`, not a separate class | Keeps LLM client wiring in one place. `NarrativeEngine` already owns `narrative_client`. |
| `CausalLink.bonus_applied` | On `NarrativeMoment` only, stripped from serialized `ChronicleEntry` | Scoring bonus is an internal curator implementation detail. Viewer and narrator never read it. No reason to bake it into the format contract. |
| `narrate` CLI output | Default `{stem}_narrated.json`, `--output` override | Non-destructive. The simulate-only bundle is cheap to produce but represents a specific seed/config — don't overwrite it. Lets you re-narrate with different budgets without re-simulating. |
| Live mode bundle format | Legacy dict format, unchanged | Live mode continues to produce `chronicle_entries: {turn: text}` bundles. The viewer and `useLiveConnection.ts` handle this via `isLegacyBundle()` detection. No live mode code changes. |
| `stat_deltas` excluded stats | Treasury (volatile/noisy), asabiya (float vs int type mismatch) | Tracked stats: population, military, economy, culture, stability — all `int` on `CivSnapshot`. Asabiya is `float`, would break the `dict[str, int]` inner type. Treasury fluctuates too much to produce meaningful deltas. |
| Partial narration failure | Per-moment fallback, continue batch | If LLM fails on moment N, that moment gets a mechanical fallback summary. Remaining moments continue with LLM. Progress callback still fires. Batch never aborts on individual moment failure. |
| Scope split | M20a (pipeline + viewer) / M20b (batch runner GUI) | The batch GUI depends on M19's `batch_report.json` schema. The curator pipeline has zero M19 dependency. Coupling them means M20 can't close until M19 lands, defeating the parallel dependency graph. |

---

## 1. Pipeline Architecture

### Three-Phase Flow

```python
# Phase 1: Simulate (CPU, seconds)
# Unchanged. run_turn() with narrator=lambda w, e: "" (no-op) or --simulate-only.
# All events accumulate in world.events_timeline. All snapshots in history.

# Phase 2: Curate (CPU, milliseconds)
# New curator.py module. Pure Python, no LLM.
selected = curate(events_timeline, named_events, history, budget=50, seed=world.seed)

# Phase 3: Narrate (GPU, minutes)
# NarrativeEngine.narrate_batch() with full context per moment.
entries = engine.narrate_batch(selected, history, gap_summaries)
bundle.chronicle_entries = entries  # sparse — not one per turn
```

### CLI Integration

New `narrate` subcommand for the explicit CPU/GPU split:

```bash
# Step 1: simulate (CPU only, no LLM client)
chronicler run --simulate-only --seed 42 --turns 500

# Step 2: narrate (GPU, loads simulate-only bundle)
chronicler narrate chronicle_bundle.json --budget 50
# Outputs: chronicle_bundle_narrated.json

chronicler narrate chronicle_bundle.json --budget 50 --output custom_name.json
```

The `narrate` subcommand loads a simulate-only bundle, runs the curator, runs the batch narrator, and writes the narrated bundle. This joins the existing `mode_flags` mutual exclusion check in `main.py`.

**Deserialization:** the subcommand loads the JSON bundle and reconstructs typed objects via Pydantic's `model_validate()`:
- `events_timeline` → `[Event.model_validate(e) for e in bundle["events_timeline"]]`
- `named_events` → `[NamedEvent.model_validate(e) for e in bundle["named_events"]]`
- `history` → `[TurnSnapshot.model_validate(s) for s in bundle["history"]]`
- `seed` → `bundle["metadata"]["seed"]` (needed for curator's tie-breaking and dominant power detection)
- `WorldState` is NOT reconstructed — the curator and narrator operate on the deserialized lists and metadata, not on a live world object.

**Implementer note:** The current `--simulate-only` path writes `chronicle_entries` as a dict of turn→empty-string (one entry per turn with empty text from the dummy narrator). The `ChronicleEntry` construction loop at ~line 277 in `main.py` runs even in simulate-only mode, appending entries with empty `text`. M20a changes this: skip the construction loop entirely when `--simulate-only` is set (not run with a dummy narrator), and write `chronicle_entries: []` (empty list) and `gap_summaries: []`. This requires `assemble_bundle()` to produce `list[dict]` format first — the format change in `assemble_bundle()` must land before the simulate-only path change.

### Existing Infrastructure Preserved

- `generate_chronicle()` stays for live mode (one LLM call per turn, unchanged)
- `MemoryStream` stays — memories still recorded per-turn for action selector context
- `interestingness.py` stays — run-level scoring is orthogonal to within-run curation
- Reflection generation stays at fixed interval — not curator-managed
- `event_flavor` and `narrative_style` from scenario config flow through to batch narration prompts

---

## 2. Narrative Curator (`curator.py`)

New module. Pure Python, no LLM calls. Selects the N most narratively important moments from a completed simulation's event timeline.

### Interface

```python
def curate(
    events: list[Event],
    named_events: list[NamedEvent],
    history: list[TurnSnapshot],
    budget: int = 50,
    seed: int = 0,
) -> tuple[list[NarrativeMoment], list[GapSummary]]:
    """Select the most narratively interesting moments and produce gap summaries.

    Returns (selected_moments, gap_summaries). Moments are sorted by anchor_turn.
    Gap summaries cover all turn ranges between selected moments.
    """
```

### Scoring Algorithm — Three Passes

**Pass 1: Base Scoring.** Every event gets a base score from `event.importance` (1-10).

| Bonus | Condition | Value |
|-------|-----------|-------|
| Named event | Event appears in `named_events` list (matched by turn + actors) | +3 |
| Dominant power | Event involves the run's dominant power | +2 |
| Rarity | Event type occurs fewer than 3 times in the entire run | +2 |

**Dominant power detection:** the civilization with the most cumulative region-turns across the entire run (sum of regions held at each turn across all turns in `history`). This handles runs where all civs are eliminated at the end — a civ that held 8 regions for 200 turns before collapsing is recognized over one that held 3 regions at the final snapshot. Ties broken by `hash(seed, civ.name)`.

**Pass 2: Causal Linking.** For each event E at turn T, scan forward through `CAUSAL_PATTERNS` using each pattern's `max_gap` (not a global window). Two filters:

1. **Gap filter:** effect event must be within `max_gap` turns of cause event
2. **Spatial filter:** cause and effect must share at least one actor (civ name) or region. If they share neither, the link is discarded.

The **cause** event receives the causal bonus (it's promoted because it leads to something important). The effect event keeps its own score. Both get `CausalLink` annotations. An event can receive multiple causal bonuses if it triggers multiple patterns (e.g., a war that causes both a leader_death and a collapse).

```python
CAUSAL_PATTERNS: list[tuple[str, str, int, float]] = [
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
    ("tech_advancement", "war", 10, +2),
    ("cultural_renaissance", "movement", 10, +2),
    ("discovery", "war", 15, +2),
]
```

**Pass 3: Cluster Detection and Budget Allocation.** Group events into clusters where adjacent events within `CLUSTER_MERGE_THRESHOLD` turns of each other merge into a single cluster. Each cluster's score is the sum of its top 3 member scores (not all members — prevents inflation from many low-importance events).

Select top `budget` clusters by score. For each selected cluster:
- `turn_range` spans from the earliest to latest event in the cluster
- `anchor_turn` is the turn of the highest-scoring event in the cluster (this is the turn used for snapshot lookup, before/after summary construction, and timeline positioning)

**Tunable constant:** `CLUSTER_MERGE_THRESHOLD = 5` (turns). This is a design constant that needs M19b validation — a 500-turn run with dense early events could produce oversized clusters. Flag for M19b analytics: measure median cluster size at threshold 3/5/8. Define as a module-level constant (not in `GameConfig` or `tuning.yaml` — this is narrator config, not simulation config).

### Post-Selection: Diversity Penalty

After initial selection, prevent over-representation:

- If >40% of selected moments **involve** the same civ, demote the lowest-scored moments for that civ and replace with the next-highest unselected clusters
- If >30% of selected moments are the same event type, same treatment
- Named events are exempt from demotion (they're always interesting)

**"Involve" definition:** a moment involves a civ if that civ appears as an actor in **any** event in the moment's event list. A war cluster between Vrashni and Kethani involves both civs — it counts toward both civs' representation percentages. The dominant event type of a moment is the most common `event_type` among its events.

### Post-Selection: Role Assignment

After diversity filtering, assign narrative roles based on position and score:

```python
class NarrativeRole(str, Enum):
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"
```

Assignment logic:
1. Sort moments by `anchor_turn`
2. Highest-scoring moment = `CLIMAX`
3. Moments before climax with forward causal links = `ESCALATION`
4. The first escalation moment = `INCITING` (overrides escalation)
5. Moments before climax without forward causal links = `ESCALATION` (default for pre-climax moments)
6. Moments after climax = `RESOLUTION`
7. The final moment = `CODA` (overrides resolution)

**Edge cases:**
- If the climax is the first moment chronologically: it stays `CLIMAX`. There are no pre-climax moments, so no `INCITING` or `ESCALATION` roles are assigned. All subsequent moments are `RESOLUTION`/`CODA`.
- If the climax is the last moment: it stays `CLIMAX`. The `CODA` rule does not override `CLIMAX`. All prior moments get `INCITING`/`ESCALATION`.
- If only one moment total: it is `CLIMAX`.

Roles are hints for the narrator prompt — they tell the LLM whether to build tension, release it, or reflect.

### Gap Summary Generation

Turns between selected moments produce gap summaries:

```python
class GapSummary(BaseModel):
    turn_range: tuple[int, int]              # inclusive
    event_count: int
    top_event_type: str                      # most common event type in gap
    stat_deltas: dict[str, dict[str, int]]   # outer: civ name, inner: stat name → net delta
    territory_changes: int                   # region controller changes in gap
```

`stat_deltas` shape: `{"Vrashni": {"population": -20, "military": 5, "stability": -12}, "Kethani": {...}}`. Tracked stats: population, military, economy, culture, stability. Treasury excluded (volatile, noisy). Computed by diffing `CivSnapshot` values at gap start and end turns from `history`.

### "Narrate This" — Degenerate Curator Path

When the viewer requests on-demand narration of a mechanical segment, the curator runs as a degenerate case:

- **Budget = 1** — select the single best moment from the requested turn range
- **Full timeline available** for causal link scoring (a drought at turn 35 in the range might link to a famine at turn 48 outside it)
- **Diversity penalty: skip** — one moment can't be over-represented
- **Role assignment: skip** — a single moment has no arc. Default role = `RESOLUTION` (the user chose to narrate this after the fact — it's inherently retrospective)

For `previous_prose`: use the prose from the most recent narrated segment before the requested range (the nearest `ChronicleEntry` with a lower `turn`). If no prior narrated segment exists, `previous_prose = None`.

The spec defines this explicitly because it's a special case most likely to regress during refactoring.

---

## 3. Data Models

### `NarrativeMoment` (curator output, internal)

```python
class NarrativeMoment(BaseModel):
    anchor_turn: int                         # the turn this moment centers on
    turn_range: tuple[int, int]              # inclusive range to narrate
    events: list[Event]                      # curated events within the range
    named_events: list[NamedEvent]           # named events within the range
    score: float                             # curator importance score
    causal_links: list[CausalLink]           # forward/backward connections
    narrative_role: NarrativeRole            # inciting/escalation/climax/resolution/coda
    bonus_applied: float                     # total causal bonus (internal, not serialized)
```

`bonus_applied` is for curator debugging/logging. Not serialized into the bundle.

### `CausalLink`

```python
class CausalLink(BaseModel):
    cause_turn: int
    cause_event_type: str
    effect_turn: int
    effect_event_type: str
    pattern: str                             # e.g., "drought→famine"
```

### `NarrativeRole` (str enum)

```python
class NarrativeRole(str, Enum):
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"
```

### `CivThematicContext` (for narrator prompts)

```python
class CivThematicContext(BaseModel):
    name: str
    trait: str                               # from CivSnapshot.trait (leader trait, e.g., "aggressive", "diplomatic")
    domains: list[str]                       # from Civilization.domains (e.g., ["maritime", "mysticism"])
    dominant_terrain: str                    # most common terrain type across civ's regions at anchor_turn
    tech_era: str                            # current TechEra value
    active_tech_focus: str | None = None     # M21 — None until M21 lands
    active_named_events: list[str]           # names of NamedEvents involving this civ in the narrated range
```

`dominant_terrain` is computed from the snapshot in `history` where `snapshot.turn == anchor_turn`: filter `region_control` for regions controlled by this civ, look up each region's terrain from the bundle's serialized `world_state.regions` data (terrain is static — the same across all turns). Take the mode. For the `narrate` subcommand, extract a `dict[str, str]` region→terrain map from `bundle["world_state"]["regions"]` at deserialization time — no `WorldState` reconstruction needed.

`civ_context` includes only civs that appear as actors in the moment's events — not all civs in the run. This keeps prompt size bounded.

### Updated `ChronicleEntry` (Pydantic, replaces dataclass)

```python
class ChronicleEntry(BaseModel):
    turn: int                                # anchor turn
    covers_turns: tuple[int, int]            # inclusive range
    events: list[Event]                      # curated events in range
    named_events: list[NamedEvent]           # named events in range
    narrative: str                           # LLM prose or mechanical fallback
    importance: float                        # curator score
    narrative_role: NarrativeRole            # enum value
    causal_links: list[CausalLink]           # for viewer visualization
```

**Migration notes:**
- Migrates from `@dataclass` to `BaseModel` to match every other model in the codebase
- Field rename: `text` → `narrative`. Three callsites affected:
  - `main.py` (~line 267): constructs `ChronicleEntry(turn=..., text=...)` → `ChronicleEntry(turn=..., narrative=..., ...)`
  - `bundle.py` (~line 33): accesses `entry.text` → `entry.narrative`
  - `chronicle.py` (~line 36): accesses `entry.text` → `entry.narrative`
- Field removed: `era: str | None = None`. This field is unused — no code reads `entry.era`. Removed intentionally, not an oversight.
- Import path: `ChronicleEntry` defined in `models.py` (with other Pydantic models), not `chronicle.py`. Update imports in `bundle.py` and `main.py`.
- `live.py` does not use `ChronicleEntry` directly (builds dicts), so it is not affected by the dataclass migration. It continues to produce legacy-format `{turn: text}` bundles.

---

## 4. Batch Narration

### `narrate_batch()` Method

Added to `NarrativeEngine`:

```python
class NarrativeEngine:
    # ... existing methods unchanged ...

    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: list[TurnSnapshot],
        gap_summaries: list[GapSummary],
        on_progress: Callable[[int, int, float], None] | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate all selected moments sequentially with full context.

        Sequential processing — LM Studio saturates the 4090 with one request.
        Progress callback: on_progress(completed, total, eta_seconds).
        """
```

### `NarrationContext` — Per-Moment LLM Context

Each LLM call receives a `NarrationContext`:

```python
class NarrationContext(BaseModel):
    moment: NarrativeMoment                  # the events being narrated (includes events + named_events)
    snapshot: TurnSnapshot                   # world state at anchor turn
    before_summary: str                      # mechanical: "Vrashni expanded to 5 regions..."
    after_summary: str                       # enables data-driven foreshadowing
    role_instruction: str                    # "This is an escalation moment. Build tension."
    causes: list[str]                        # "This famine was caused by the drought of turn 134"
    consequences: list[str]                  # "This will lead to the rebellion of turn 160"
    previous_prose: str | None               # last narrated moment's output, for style continuity
    civ_context: dict[str, CivThematicContext]  # per-civ thematic data for actors in this moment
```

Note: named events are accessed via `moment.named_events` — no separate field to avoid duplication.

### Before/After Summary Generation

NOT LLM calls. Mechanical templates filled from snapshot diffs:

```python
def build_before_summary(
    history: list[TurnSnapshot],
    moment: NarrativeMoment,
    prev_moment: NarrativeMoment | None,
) -> str:
    """Compare snapshots at prev_moment.anchor_turn vs moment.anchor_turn.
    Report: stat changes > 10, territory gains/losses, new conditions, era changes.
    Returns 3-5 bullet points as a single string.

    If prev_moment is None (first moment), compare against turn 1.
    """

def build_after_summary(
    history: list[TurnSnapshot],
    moment: NarrativeMoment,
    next_moment: NarrativeMoment | None,
) -> str:
    """Forward-looking. Compare moment.anchor_turn to next_moment.anchor_turn.
    Enables foreshadowing from data: 'this drought leads to famine in 8 turns.'

    If next_moment is None (last moment), compare against final turn.
    """
```

### Role Instructions

| Role | Instruction |
|------|-------------|
| `INCITING` | "Introduce the tension. Something has changed that cannot be undone." |
| `ESCALATION` | "Build on what came before. The stakes are rising." |
| `CLIMAX` | "This is the turning point. Maximum consequence, maximum drama." |
| `RESOLUTION` | "The dust settles. Show what was won and what was lost." |
| `CODA` | "Look back on what happened. Reflect on the arc of this history." |

### `previous_prose` Bootstrapping

The first narrated moment has `previous_prose = None`. The prompt template handles this:
- If `previous_prose is None` and `narrative_style` is set: use `narrative_style` as the initial voice reference
- If `previous_prose is None` and no `narrative_style`: omit the style continuity section entirely

### ETA Calculation

Progress ETA uses tokens/sec measured from the **second** completed call (the first call is often slower due to model warmup / KV cache cold start). Before the second call completes, use a conservative default of 30 tok/s for 13B models. ETA = `(total - completed) * avg_tokens_per_call / tokens_per_sec`.

### Prompt Size Budget

For 13B local models with 8K context, the per-moment prompt must stay under ~4K tokens (leaving 4K for generation). Truncation priorities if the prompt exceeds budget:

1. Drop `previous_prose` (style continuity is nice-to-have)
2. Trim `civ_context` to only the primary actor (highest event involvement)
3. Shorten `before_summary` and `after_summary` to 2 bullet points each
4. Never truncate: `moment.events`, `role_instruction`, `causes`/`consequences`

For Claude API or larger local models, no truncation needed — the full context fits easily.

### Fallback

If `narrative_client` is unavailable (no LM Studio, no API key), `narrate_batch()` returns `ChronicleEntry` objects with mechanical summaries instead of prose — same fallback pattern as existing `generate_chronicle()`.

---

## 5. Bundle Format Change

### Bundle Dict Changes

| Field | Old | New |
|-------|-----|-----|
| `chronicle_entries` | `dict[str, str]` (turn → text) | `list[dict]` (serialized `ChronicleEntry`) |
| `gap_summaries` | — | `list[dict]` (serialized `GapSummary`) |
| `era_reflections` | `dict[str, str]` | `dict[str, str]` (unchanged) |

### `assemble_bundle()` Update

The function signature adds `gap_summaries: list[GapSummary]`. The `chronicle_entries` parameter type changes from `list[ChronicleEntry]` (old dataclass) to `list[ChronicleEntry]` (new Pydantic model). Serialization uses `.model_dump()`.

### `compile_chronicle()` Update

Signature changes to accept gap summaries:

```python
def compile_chronicle(
    world_name: str,
    entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    epilogue: str | None = None,
    gap_summaries: list[GapSummary] | None = None,   # NEW, optional for backward compat
) -> str:
```

Currently iterates `ChronicleEntry` list and inserts era reflections at turn boundaries, producing a Markdown document. New version:

- Iterates `list[ChronicleEntry]` sorted by `turn`
- Inserts era reflections between entries at era boundaries (same logic)
- Inserts `[Mechanical: turns X-Y, N events]` one-liners for gap summaries between narrated entries
- Output is still a Markdown document, but sparse — not one section per turn

### Sort Order

The `chronicle_entries` list in the serialized bundle MUST be sorted by `turn` (ascending). Viewers and `compile_chronicle()` rely on insertion order without re-sorting. `gap_summaries` must also be sorted by `turn_range[0]`.

### Backward Compatibility

Old bundles have `chronicle_entries: {turn: text}`. Detection is viewer-side only:

```python
# Python: no compatibility layer needed
# Viewer:
def isLegacyBundle(entries):
    return not isinstance(entries, list)
```

- **Legacy bundles** → render as today (turn-by-turn scrollable list)
- **New bundles** → render segmented timeline
- **Live mode bundles** → live mode (`live.py`) continues to produce `chronicle_entries` in legacy dict format (`{turn: text}`). The `useLiveConnection.ts` `"turn"` message handler continues to build `chronicle_entries` as `Record<string, string>`. The viewer detects this as legacy format and renders turn-by-turn. No live mode changes except adding the `narrate_range` handler.
- No migration of old bundles. They render in legacy mode permanently.

### Simulate-Only Bundles

After M20a, `--simulate-only` writes:
- `chronicle_entries: []`
- `gap_summaries: []`
- `era_reflections: {}` (reflections require LLM calls, skipped in simulate-only)

---

## 6. Viewer — Segmented Timeline

### `TimelineScrubber` Rewrite

The current continuous track with era boundaries and named event dots becomes a segmented bar:

```
Turn  1────30  31──────45  46────────90  91───120  ...
      [prose]  [mechanic]  [prose]       [mech]
      ▼ open   ▸ 15 evts   ▼ open       ▸ 30 evts
```

### Segment Types

| Type | Source | Color | Default State | Content on Expand |
|------|--------|-------|---------------|-------------------|
| Narrated | `ChronicleEntry` | Role-colored: blue=inciting, orange=escalation, red=climax, green=resolution, gray=coda | Expanded if importance >= 8 | Full prose + event list |
| Mechanical | `GapSummary` | Muted gray | Collapsed | Event count + stat delta sparkline per civ. Click → existing EventLog view filtered to turn range |
| Era reflection | `era_reflections` | Distinct (centered text, decorative border) | Expanded | Full-width divider between segments |

### Causal Link Overlay

Optional toggle (toolbar button, off by default). Draws SVG arcs connecting causally linked moments. Each arc labeled with the pattern name ("drought→famine"). Off by default to avoid visual clutter.

### "Narrate This" Button

On mechanical segments. Sends the turn range to the backend for on-demand narration via WebSocket:

```typescript
// Client → Server
{ type: "narrate_range", start_turn: number, end_turn: number }

// Server → Client
{ type: "narration_started", start_turn: number, end_turn: number }
{ type: "narration_complete", entry: ChronicleEntry }
```

Server-side: curator runs as the degenerate path (budget=1, skip diversity/role, default role=RESOLUTION) with the full timeline for causal context. Narrator generates prose. Result inserts into the timeline, splitting the mechanical segment. Bundle updated in memory and on disk if user saves.

Reuses existing WebSocket connection. **Hidden when viewing static bundles** (file load, not live) — no server to call. Supporting static bundle narration is a future enhancement, not M20a scope.

### `ChroniclePanel` Rewrite

Context-dependent rendering based on focused segment:

- **Narrated segment focused** → prose, event list below, causal annotations in margin ("→ leads to The Siege of Meridia, turn 147")
- **Mechanical segment focused** → existing EventLog component, filtered to that turn range
- **Era reflection focused** → reflection text

### Scrubbing Behavior

- Through narrated segments → chronicle panel shows prose
- Through mechanical segments → stat graphs and territory map update (existing), chronicle panel shows "Mechanical: N events" summary
- Tick marks at narrated segment boundaries for quick navigation

### New TypeScript Types

```typescript
interface ChronicleEntry {
    turn: number;
    covers_turns: [number, number];
    events: Event[];
    named_events: NamedEvent[];
    narrative: string;
    importance: number;
    narrative_role: "inciting" | "escalation" | "climax" | "resolution" | "coda";
    causal_links: CausalLink[];
}

interface GapSummary {
    turn_range: [number, number];
    event_count: number;
    top_event_type: string;
    stat_deltas: Record<string, Record<string, number>>;  // civ → stat → delta
    territory_changes: number;
}

interface CausalLink {
    cause_turn: number;
    cause_event_type: string;
    effect_turn: number;
    effect_event_type: string;
    pattern: string;
}

// Bundle chronicle field is a union for backward compat
type BundleChronicle =
    | Record<string, string>      // legacy: turn → text
    | ChronicleEntry[];           // new: sparse entries

function isLegacyBundle(chronicle: BundleChronicle): chronicle is Record<string, string> {
    return !Array.isArray(chronicle);
}
```

---

## 7. Deliverables

### New Files

| File | Purpose | Est. Lines |
|------|---------|------------|
| `src/chronicler/curator.py` | Event selection, causal linking, cluster detection, role assignment, gap summaries, degenerate path | ~250 |

### Modified Files

| File | Change | Est. Lines |
|------|--------|------------|
| `src/chronicler/models.py` | `NarrativeMoment`, `NarrativeRole`, `CausalLink`, `GapSummary`, `CivThematicContext`, `NarrationContext` | ~60 |
| `src/chronicler/narrative.py` | `narrate_batch()`, before/after summary builders, role instruction mapping, ETA tracking | ~150 (additions) |
| `src/chronicler/chronicle.py` | `ChronicleEntry` migration to Pydantic, `compile_chronicle()` update for sparse output | ~30 (rewrite) |
| `src/chronicler/bundle.py` | `assemble_bundle()` for new format (adds `gap_summaries` param) | ~20 (update) |
| `src/chronicler/main.py` | `chronicler narrate` subcommand, pipeline orchestration, simulate-only `chronicle_entries: []` | ~40 (update) |
| `viewer/src/types.ts` | `ChronicleEntry`, `GapSummary`, `CausalLink`, `BundleChronicle` union, `isLegacyBundle()` | ~30 |
| `viewer/src/components/TimelineScrubber.tsx` | Segmented timeline with role colors, causal overlay toggle, "narrate this" button, tick marks | ~200 (rewrite) |
| `viewer/src/components/ChroniclePanel.tsx` | Context-dependent rendering (prose/events/reflection based on focused segment) | ~80 (rewrite) |
| `src/chronicler/live.py` | `narrate_range` WebSocket handler: invokes degenerate curator path, calls narrator, sends `narration_complete` response | ~30 (additions) |
| `viewer/src/hooks/useLiveConnection.ts` | `narrate_range` / `narration_complete` message types | ~15 (additions) |

### Not In Scope

- Batch runner GUI (BatchPanel, analytics display, compare mode) → M20b
- Live mode curation / turn buffering → not planned
- Multi-model routing (high-importance to Claude API, low to local) → deployment decision
- Prose quality scoring / retry on low quality → future enhancement
- "Narrate This" for static bundles (no server) → future enhancement
- Exact LLM prompt templates → implementation detail, not spec'd

---

## 8. Testing Strategy

| Test | What It Validates | Approach |
|------|-------------------|----------|
| Curator base scoring | Events get correct base scores (importance, rarity, dominant power) | Fixed seed, 20 hand-crafted events with known importance. Assert scores match expected. |
| Curator causal linking | Pattern-specific `max_gap`, spatial filtering, cause gets bonus | Hand-crafted event pairs at known turn gaps. Assert links created/not-created based on actor/region overlap and gap distance. |
| Curator cluster detection | Adjacent events merge, cluster score = top 3 members | Events at turns 10,11,12 (one cluster) and turn 50 (separate). Assert cluster boundaries and scores. |
| Curator diversity penalty | Over-represented civs/types get demoted | Budget=5, 4 moments from same civ. Assert replacement happens. Named events exempt. |
| Curator role assignment | Climax = highest score, roles ordered correctly | 5 moments with known scores. Assert role assignment matches expected. |
| Dominant power detection | Cumulative region-turns, fallback when all civs eliminated | All-dead scenario. Assert dominant power computed from history, not final snapshot. |
| Dominant power tie-break | `hash(seed, civ.name)` determinism | Two civs with identical region-turns, fixed seed. Assert consistent winner. |
| Gap summaries | Correct turn ranges, event counts, per-civ/per-stat deltas | Known event sequence + history snapshots. Assert gap boundaries align with selected moments. Assert `stat_deltas` shape is `{civ: {stat: delta}}`. |
| "Narrate This" degenerate path | Budget=1, skip diversity/role, default role=RESOLUTION | Call curator with single turn range. Assert returned moment has role=RESOLUTION, no diversity penalty applied. |
| `NarrationContext` construction | Before/after summaries, causal annotations, role instruction, `previous_prose` bootstrapping | Mock `NarrativeEngine.narrate_batch` to capture context without LLM call. Assert context fields populated correctly. Assert first moment gets `previous_prose=None`. |
| Batch narration integration | End-to-end: simulate → curate → narrate → bundle | 5-turn simulation with fixed seed. Assert bundle contains sparse `ChronicleEntry` list with correct structure. LLM call mocked to return "test prose". |
| Bundle format serialization | New `ChronicleEntry` round-trips correctly | Create → `assemble_bundle` → JSON → reload → assert fields match including `NarrativeRole` enum values. |
| Bundle backward compat | Legacy bundles still load and render | Load a `{turn: text}` dict-format bundle. Assert `isLegacyBundle()` returns true. |
| `chronicler narrate` CLI | Subcommand loads simulate-only bundle, writes `_narrated.json` | Run with `--simulate-only`, then `narrate` on output. Assert narrated file exists with populated `chronicle_entries`. |
| Compile chronicle | Sparse Markdown output with gap markers and era reflections | Known entries + gaps + reflections. Assert Markdown contains prose sections, mechanical one-liners, and reflection dividers in correct order. |

Viewer tests follow existing patterns (component tests). The spec notes what to test but does not dictate the test framework.

---

## 9. Exit Criteria

- `chronicler narrate bundle.json` produces a narrated bundle with sparse `ChronicleEntry` objects containing prose, roles, and causal links
- Curator selects ~50 moments from a 500-turn run with visible causal linking (cause events promoted before their effects)
- Diversity penalty prevents >40% same-civ or >30% same-type representation
- Role assignment produces a coherent narrative arc (inciting → escalation → climax → resolution → coda)
- Gap summaries cover all unnarrated turn ranges with correct per-civ stat deltas
- Batch narration provides full before/after context per moment with data-driven foreshadowing
- Viewer renders segmented timeline with role-colored narrated segments and collapsible mechanical segments
- "Narrate This" button on mechanical segments triggers on-demand narration via WebSocket (live mode only)
- Causal link overlay toggle draws SVG arcs between linked moments
- Legacy bundles (`{turn: text}` format) render in legacy mode unchanged
- `--simulate-only` writes `chronicle_entries: []` and `gap_summaries: []`
- All curator tests pass with deterministic seed-based assertions

### Total Estimated Scope

~630 lines new/modified Python, ~325 lines new/modified TypeScript, ~200 lines tests. No simulation logic changes. No architectural changes beyond the narration pipeline.
