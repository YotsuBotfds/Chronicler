# M11: Visualization / GUI — Design Spec

> Web-based chronicle viewer. Reads `chronicle_bundle.json`, no backend required. All four sub-milestones (Chronicle Viewer, Faction Dashboard, Territory Map, Stat Graphs) ship as one integrated artifact — they share layout, navigation, and data loading. The timeline scrubber drives all panels.

## Dependencies

- M7 (Simulation Depth) — richer events, named events, tech progression, leader dynamics
- M10 (Workflow Features) — batch output, fork provenance, interestingness scoring

## Architecture Overview

Two deliverables:

1. **Python-side changes** — per-turn snapshot capture + bundle assembly (prerequisite for everything else)
2. **React viewer app** — static client-side SPA in `viewer/` directory, reads `chronicle_bundle.json`

No coupling between the viewer and the Python simulation beyond the JSON bundle format. The bundle is the contract.

---

## Part 1: Python-Side Changes

### 1.1 Snapshot Models

Add to `models.py`:

```python
class CivSnapshot(BaseModel):
    population: int
    military: int
    economy: int
    culture: int
    stability: int
    treasury: int
    asabiya: float
    tech_era: TechEra
    trait: str           # leader trait — tracks trait evolution over time
    regions: list[str]
    leader_name: str
    alive: bool          # explicit flag; dead civs stay in every snapshot with final stats frozen

class TurnSnapshot(BaseModel):
    turn: int
    civ_stats: dict[str, CivSnapshot]  # keyed by civ name
    region_control: dict[str, str | None]  # region name → controller name or None
```

**Key rules:**
- Every civilization appears in every snapshot, even after absorption. Dead civs have `alive: false` with their final stats preserved (not zeroed).
- The death-turn snapshot must capture `alive: false` with the civ's final non-zero stats. Snapshot capture happens *after* simulation but *before* any post-death cleanup.

### 1.2 Snapshot Capture

In `execute_run`, after each turn's simulation phase completes (after consequences, before chronicle generation):

```python
snapshot = TurnSnapshot(
    turn=world.turn,
    civ_stats={
        civ.name: CivSnapshot(
            population=civ.population,
            military=civ.military,
            economy=civ.economy,
            culture=civ.culture,
            stability=civ.stability,
            treasury=civ.treasury,
            asabiya=civ.asabiya,
            tech_era=civ.tech_era,
            trait=civ.leader.trait,
            regions=list(civ.regions),
            leader_name=civ.leader.name,
            alive=civ.population > 0,  # or whatever the absorption condition is
        )
        for civ in world.civilizations
    },
    region_control={
        region.name: region.controller
        for region in world.regions
    },
)
history.append(snapshot)
```

Snapshots accumulate in a local list within `execute_run`. They are **never** written to the crash-recovery `state.json`.

### 1.3 Bundle Assembly

At the end of a completed run (after chronicle compilation), write `chronicle_bundle.json` alongside the existing `state.json` and `chronicle.md`:

```json
{
  "world_state": { ... },
  "history": [ ... ],
  "chronicle_entries": { "1": "prose...", "2": "prose...", ... },
  "era_reflections": { "10": "## Era: Turns 1–10\n\n...", ... },
  "metadata": {
    "seed": 42,
    "total_turns": 100,
    "generated_at": "2026-03-13T14:30:00Z",
    "model_name": "LFM2-24B",
    "scenario_name": "post_collapse_minnesota"
  }
}
```

**Key rules:**
- `world_state` is the full final WorldState (same content as `state.json`).
- `history` is the list of `TurnSnapshot` objects.
- `chronicle_entries` is keyed by turn number (string). Values are the raw prose strings from `execute_run`'s `chronicle_entries` dict.
- `era_reflections` is keyed by the turn number at which the reflection was generated.
- `metadata.model_name` comes from the LLM client configuration at runtime.
- `metadata.scenario_name` comes from `world.scenario_name` (may be null).
- Bundle is written **once** at completion. Not written on early termination or crash.
- Existing outputs unchanged: `state.json` (crash-recovery checkpoint, overwritten each turn, no history) and `chronicle.md` (standalone readable prose) continue to be written exactly as before.

### 1.4 Region Coordinates

Add optional normalized coordinates to `RegionOverride` in `scenario.py`:

```python
class RegionOverride(BaseModel):
    # ... existing fields ...
    x: float | None = None  # 0.0–1.0 normalized horizontal position
    y: float | None = None  # 0.0–1.0 normalized vertical position
```

Propagate to `Region` in `models.py`:

```python
class Region(BaseModel):
    # ... existing fields ...
    x: float | None = None
    y: float | None = None
```

`apply_scenario` copies `x`/`y` from `RegionOverride` to `Region` when present. The viewer's force-directed layout ignores these when absent, pins nodes to the specified position when present. Coordinates are resolution-independent — the viewer scales them to whatever container size it renders in.

---

## Part 2: React Viewer App

### 2.1 Tech Stack

- **Vite** — build tooling
- **TypeScript** — interfaces generated from Pydantic models (bundle format is single source of truth)
- **React 18** — UI framework
- **Tailwind CSS** — utility-first styling (conditional coloring for faction colors, era highlights, stat thresholds, alive/dead states)
- **Recharts** — stat line graphs
- **d3-force** — territory map node layout (lightweight, not full D3)
- **Vitest + React Testing Library** — tests

### 2.2 Directory Structure

```
viewer/
  src/
    App.tsx
    types.ts                # TS interfaces mirroring Pydantic models + Bundle type
    hooks/
      useBundle.ts          # file loading, parsing, validation → typed Bundle
      useTimeline.ts        # currentTurn, playing, speed, play/pause/seek controls
    components/
      Layout.tsx            # header + scrubber + two-column body
      Header.tsx            # world name, scenario, seed, turns, model, turn counter, dark/light toggle
      TimelineScrubber.tsx  # horizontal full-width scrubber below header
      ChroniclePanel.tsx    # rendered prose synced to timeline
      EventLog.tsx          # filterable event table with jump-to-turn
      FactionDashboard.tsx  # faction cards with sparklines
      RelationshipMatrix.tsx # disposition overlay on territory map
      TerritoryMap.tsx      # d3-force node graph
      StatGraphs.tsx        # Recharts line charts with event markers
    lib/
      colors.ts             # deterministic faction color from civ name hash
      format.ts             # number/era/disposition formatters
  public/
  index.html
  tailwind.config.ts
  vite.config.ts
  tsconfig.json
  package.json
```

### 2.3 Data Flow

1. User opens viewer → drag-and-drop or file picker loads `chronicle_bundle.json`
2. `useBundle` parses JSON, validates required keys, returns typed `Bundle` object (or error state)
3. `useTimeline` manages: `currentTurn` (number), `playing` (boolean), `speed` (turns per second: 1, 2, 5, 10). Exposes `seek(turn)`, `play()`, `pause()`, `setSpeed(n)`.
4. Every panel receives `bundle` + timeline state and renders the appropriate slice
5. No backend, no API calls. `npm run build` → self-contained `dist/`

### 2.4 Layout

**Header** (full width, fixed):
- Left: World name, scenario name (if any), "Turn 47 / 100"
- Right: Seed, model name, dark/light toggle

**Timeline Scrubber** (full width, below header):
- Horizontal bar with turn markers. Era boundaries as labeled dividers.
  - Era boundaries are **global**: marked at the turn when the *first* civ reaches that era.
  - Per-civ era is shown on individual faction cards, not on the scrubber.
- Drag to seek, click to jump.
- Play/pause button, speed selector (1x, 2x, 5x, 10x turns per second).
- Named event dots on the bar — **adaptive density**: show the top N events by importance that fit without overlapping, rather than a hard importance threshold. Keeps the scrubber useful at any run length (20 turns or 500). Hover for tooltip with event name + turn.
- Current turn number displayed on the scrubber thumb.

**Body** (two columns below scrubber):

**Left column (~35%)** — text-heavy:
- **Chronicle tab**: Rendered markdown for the current turn's entry. Auto-scrolls to current turn on scrub. Era reflections shown inline at their boundary turns.
- **Event Log tab**: Table of all events. Columns: turn, type, actors, importance. Filterable by type, civilization, importance threshold. Click a row → scrubber jumps to that turn.

**Right column (~65%)** — visual/data, stacked vertically:
- **Faction Dashboard** (top): One card per civilization.
  - Shows: name, leader name + trait, tech era badge, domains, values.
  - Dead civs: muted card with "Absorbed turn X" label and final stats.
  - Sparklines for all 7 stats (population, military, economy, culture, stability, treasury, asabiya).
  - **Sparklines always show full run history** (all turns, not truncated to current turn). Vertical marker at the current scrubber position. This lets the user see "where is this civ headed" while scrubbing.
- **Territory Map** (middle): D3-force node graph.
  - Regions as circles, sized by `carrying_capacity`, colored by controlling faction. Uncontrolled = gray.
  - Default edges: adjacency (inferred or from scenario coordinates).
  - **Relationship matrix toggle**: switches edge rendering from adjacency to diplomatic disposition between factions. Edge color follows the disposition enum: red (hostile), yellow (suspicious), gray (neutral), green (friendly), blue (allied).
  - Click a region node: tooltip with terrain, resources, carrying capacity, control history (list of controller changes with turn numbers).
  - When scenario provides `x`/`y` coordinates: nodes pinned to those positions. Otherwise: force-directed layout.
  - Animated during playback: nodes recolor as control changes between turns.
- **Stat Graphs** (bottom): Recharts line chart.
  - One line per civ, colored by faction color.
  - Stat selector dropdown. **Default: asabiya** (the signature mechanic — Ibn Khaldun thesis made visible).
  - Vertical event markers for high-importance events (adaptive, same logic as scrubber dots).
  - Vertical line at current scrubber position.
  - Comparison mode: checkbox to overlay two stats on dual Y-axes.

### 2.5 Faction Colors

Deterministic assignment: hash the civilization name to a hue, fixed saturation/lightness. Same civ always gets the same color across runs. Ensures visual consistency without requiring scenario authors to specify colors.

### 2.6 Dark/Light Mode

Toggle in header. Default: dark (fits the mythic tone of the chronicles). Tailwind's `dark:` variant classes.

---

## Part 3: Testing

### 3.1 Python-Side Tests

- **Snapshot model tests**: `CivSnapshot` and `TurnSnapshot` construction + serialization round-trip.
- **Snapshot capture test**: Run 5 turns, verify `history` list has 5 entries with correct civ stats at each turn.
- **Dead civ boundary test**: Run a scenario where a civ gets absorbed. Verify:
  - The death-turn snapshot has `alive: false` AND non-zero final stats (not zeroed).
  - All subsequent snapshots include the dead civ with `alive: false` and frozen stats.
- **Bundle assembly test**: Verify `chronicle_bundle.json` contains all required top-level keys (`world_state`, `history`, `chronicle_entries`, `era_reflections`, `metadata`).
- **Bundle not written on crash**: Verify bundle is only written on completed runs, not on crash-recovery saves or early termination.
- **Bundle size sanity test**: Run 500 turns with 5 civs, write the bundle, assert file size < 5MB. Guards against bloat from redundant serialization.
- **Region coordinates test**: Verify `x`/`y` propagate from `RegionOverride` through `apply_scenario` to `Region` model and into the bundle.
- **Existing tests untouched**: `state.json` and `chronicle.md` output unchanged. All prior tests pass without modification.

### 3.2 Viewer Tests (Vitest + React Testing Library)

- **`useBundle`**: Loads a fixture bundle JSON, returns typed object. Rejects malformed JSON with error state.
- **`useTimeline`**: Scrub to turn N → `currentTurn` updates. Play/pause toggles `playing`. Speed changes propagate.
- **Component rendering**: Each panel renders without crashing given a fixture bundle. Faction cards show correct count. Stat graph renders SVG. Territory map renders correct number of region nodes.
- **No E2E/browser tests** in M11 scope — M12 territory.

**Fixture rule**: The fixture bundle used by Vitest is **generated by the Python side** (run chronicler → capture output), not hand-written. Single source of truth. A script or test generates the fixture and commits it. This prevents fixture drift from the actual bundle format.

### 3.3 Integration Test

Run the chronicler for 10 turns with a test scenario → verify `chronicle_bundle.json` is written → load it into `useBundle` hook → confirm it parses without error. This is the Python→viewer contract test.

### 3.4 Manual Smoke Test Criteria

- App loads a sample bundle
- Timeline navigation works (scrub, play, pause)
- Faction cards render with sparklines
- At least one stat graph displays correctly
- Territory map shows colored nodes
- Dark/light mode toggles

---

## Scope Boundaries

**In scope:**
- Read-only viewer consuming `chronicle_bundle.json`
- All four panels: chronicle, faction dashboard, territory map, stat graphs
- Python-side snapshot capture + bundle assembly
- Optional region coordinates in scenario configs

**Out of scope (M12):**
- Live simulation connection (WebSocket/polling)
- Intervention panel (event injection, stat override)
- Scenario editor
- E2E browser tests

**Out of scope (future):**
- Custom faction color overrides in scenario configs
- Batch run comparison view (loading multiple bundles side-by-side)
- Export/share functionality

---

## Internal Ordering

1. **Python: snapshot capture + bundle assembly** — models, capture in execute_run, bundle writer. Prerequisite for everything.
2. **Viewer shell + data loading** — Vite scaffold, TypeScript types, useBundle, useTimeline, Layout, Header, TimelineScrubber.
3. **Chronicle panel + Faction dashboard + Event log** — text-heavy, straightforward rendering.
4. **Territory map + Stat graphs + Relationship matrix** — d3-force, Recharts, more visual.
