# M20b: Batch Runner GUI — Implementation Instructions

**For:** Cici (builder persona)
**Reviewed by:** Phoebe (architectural reviewer)
**Date:** 2026-03-14
**Prerequisites:** M19 (analytics), M19b (tuning pass), M20a (narration pipeline v2) — all landed

---

## What You're Building

A `BatchPanel` React component in the M12c setup lobby that wraps the existing CLI batch/analytics tooling in a visual interface. This is **presentation-only** — no new Python analytics logic. The backend is a thin API layer over `run_batch()` and the analytics pipeline.

The goal: replace the `chronicler --seed-range 1-200 --turns 500 --simulate-only --parallel --tuning tuning.yaml` → `chronicler --analyze ./batch_1` CLI workflow with a single browser tab.

---

## Architecture

### Backend (Python — thin API layer)

Add a `/api/batch` namespace to the existing `LiveServer` WebSocket protocol in `src/chronicler/live.py`. Reuse the same WebSocket connection the viewer already establishes — no new server process.

**New WebSocket message types:**

```
Client → Server:
  { "type": "batch_start", "config": {
      "seed_start": int,
      "seed_count": int,
      "turns": int,
      "simulate_only": bool,  // default true
      "parallel": bool,       // default true
      "workers": int | null,  // null = auto (cpu_count - 1)
      "tuning_overrides": dict[str, float] | null  // flattened dot-notation keys
  }}
  { "type": "batch_cancel" }
  { "type": "batch_load_report", "path": string }  // load existing batch_report.json

Server → Client:
  { "type": "batch_progress", "completed": int, "total": int, "current_seed": int }
  { "type": "batch_complete", "report": <batch_report.json contents> }
  { "type": "batch_error", "message": string }
  { "type": "batch_report_loaded", "report": <batch_report.json contents> }
```

**Implementation notes:**
- Run batch in a background thread (same pattern as simulation thread in LiveServer)
- Pipe per-seed completion events to `batch_progress` messages via the snapshot_queue
- After batch completes, run analytics automatically and send the full `batch_report.json` as `batch_complete`
- `tuning_overrides` bypasses YAML entirely — the GUI sends flattened key-value pairs directly, which get set on `WorldState.tuning_overrides` per-run. This avoids file I/O race conditions (the bug from M19b iteration 4).
- Cancel support: set a threading.Event that `_run_single_no_llm` checks between seeds

**Files to modify:**
- `src/chronicler/live.py` — add batch message handlers (~80-100 lines)
- `src/chronicler/batch.py` — add progress callback parameter to `run_batch()`, cancel event check (~20 lines)

### Frontend (TypeScript/React)

**New files:**
- `viewer/src/components/BatchPanel.tsx` — main batch runner component
- `viewer/src/components/BatchAnalytics.tsx` — analytics visualization (charts, tables, anomalies)
- `viewer/src/components/BatchCompare.tsx` — side-by-side report comparison
- `viewer/src/hooks/useBatchConnection.ts` — WebSocket batch message handling

**Modified files:**
- `viewer/src/components/SetupLobby.tsx` — add tab navigation: "Single Run" | "Batch Run"
- `viewer/src/types.ts` — add BatchReport, BatchConfig, AnomalyFlag types

---

## Component Specs

### SetupLobby.tsx Changes

Add a tab bar at the top of the sidebar. Current lobby becomes the "Single Run" tab. New "Batch Run" tab renders `<BatchPanel />`. Tab state is local — no URL routing needed.

```tsx
const [tab, setTab] = useState<"single" | "batch">("single");
```

The sidebar header, error banner, and preview panel are shared. Only the form section switches between SingleRunForm (extracted from current code) and BatchPanel.

### BatchPanel.tsx

**Configuration section (sidebar):**

| Field | Type | Default | Maps to |
|-------|------|---------|---------|
| Start Seed | number input | 1 | `config.seed_start` |
| Seed Count | number input | 200 | `config.seed_count` |
| Turns | number input | 500 | `config.turns` |
| Workers | number input (0=auto) | 0 | `config.workers` |
| Simulate Only | checkbox | checked | `config.simulate_only` |

**Tuning overrides section (collapsible, below config):**

Group the 23 tuning keys by category. Each key renders as a labeled number input with the baked default as placeholder. Only non-empty overrides get sent.

Categories and keys (from `tuning.py` KNOWN_OVERRIDES):

```
Stability Drains:
  stability.drain.drought_immediate      (default: 3)
  stability.drain.drought_ongoing        (default: 2)
  stability.drain.plague_immediate       (default: 3)
  stability.drain.famine_immediate       (default: 3)
  stability.drain.war_cost               (default: 2)
  stability.drain.governing_per_distance (default: 0.5)
  stability.drain.condition_ongoing      (default: 1)
  stability.drain.rebellion              (default: 4)
  stability.drain.leader_death           (default: 4)
  stability.drain.border_incident        (default: 2)
  stability.drain.religious_movement     (default: 4)
  stability.drain.migration              (default: 4)
  stability.drain.twilight               (default: 5)

Stability Recovery:
  stability.recovery_per_turn            (default: 20)

Fertility:
  fertility.degradation_rate             (default: 0.005)
  fertility.recovery_rate                (default: 0.05)
  fertility.famine_threshold             (default: 0.05)

Military:
  military.maintenance_free_threshold    (default: 3)

Emergence:
  emergence.black_swan_base_probability  (default: 0.015)
  emergence.black_swan_cooldown_turns    (default: 50)

Regression:
  regression.capital_collapse_probability   (default: 0.3)
  regression.entered_twilight_probability   (default: 0.5)
  regression.black_swan_stressed_probability (default: 0.2)
```

**Run button:** Green "Run Batch" button. During run, shows progress bar (completed/total seeds) and "Cancel" button. After completion, automatically switches to analytics view.

**State machine:**
```
idle → running → complete
  ↑       |         |
  |       v         |
  +--- cancelled <--+
  +--- error <------+
```

### BatchAnalytics.tsx

Renders a `BatchReport` object. Used both after a fresh batch run and when loading a saved report.

**Sections (top to bottom in the preview panel):**

1. **Summary header:** seed range, turns, run count, timestamp
2. **Stability chart:** recharts `<AreaChart>` with median line + p25/p75 band per checkpoint. X-axis = checkpoint turns, Y-axis = stability 0-100. Use red/yellow/green zones (0-20 red, 20-40 yellow, 40+ green).
3. **Event firing rates table:** sortable `<table>` with columns: Event Type, Firing Rate (%), Median Turn, Q25-Q75 range. Color-code: 0% = red row, <10% = yellow, 10-90% = normal, >95% = orange (near-universal). Use the `event_firing_rates` object from the report.
4. **Anomaly panel:** color-coded cards. CRITICAL = red border, WARNING = yellow border, INFO = gray border. Show category, message. If no anomalies, show green "No degenerate patterns detected" banner.
5. **System cards:** collapsible accordion, one per system key in the report (stability, resources, politics, climate, memetic, great_persons, emergence, general). Each card shows the raw metrics for that system in a readable format. These are the detailed drill-down — most users will look at the summary + anomalies first.

**Chart library:** recharts (already a viewer dependency). Use `<AreaChart>`, `<BarChart>`, `<Tooltip>`, `<ResponsiveContainer>`.

### BatchCompare.tsx

Two-column layout. Each column holds a `BatchAnalytics` view. Between them, a diff summary panel highlighting:

- Stability median changes per checkpoint (green arrow up / red arrow down + delta)
- Firing rate changes (gained mechanics in green, lost in red, changed in yellow)
- New/resolved anomalies

**Loading:** "Load Report" buttons above each column. Accept `batch_report.json` via file picker or drag-drop. Fresh batch results auto-populate the right column.

### TypeScript Types

Add to `viewer/src/types.ts`:

```typescript
interface BatchConfig {
  seed_start: number;
  seed_count: number;
  turns: number;
  simulate_only: boolean;
  parallel: boolean;
  workers: number | null;
  tuning_overrides: Record<string, number> | null;
}

interface BatchReport {
  metadata: {
    run_timestamp: string;
    batch_dir: string;
    bundle_count: number;
    min_total_turns: number;
    checkpoints: number[];
  };
  stability: {
    percentiles_by_turn: Record<string, PercentileData>;
    zero_rate_by_turn: Record<string, number>;
  };
  resources: Record<string, unknown>;
  politics: Record<string, unknown>;
  climate: Record<string, unknown>;
  memetic: Record<string, unknown>;
  great_persons: Record<string, unknown>;
  emergence: Record<string, unknown>;
  general: Record<string, unknown>;
  event_firing_rates: Record<string, FiringRateEntry>;
  anomalies: AnomalyFlag[];
}

interface PercentileData {
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

interface FiringRateEntry {
  count: number;
  fraction: number;
  median_turn: number | null;
  q25_turn: number | null;
  q75_turn: number | null;
}

interface AnomalyFlag {
  severity: "CRITICAL" | "WARNING" | "INFO";
  category: string;
  message: string;
}
```

---

## Implementation Order

### Chunk 1: Backend batch WebSocket (~100 lines Python)
1. Add `batch_start`, `batch_cancel`, `batch_load_report` handlers to `LiveServer._handle_message()`
2. Add progress callback to `run_batch()` in `batch.py`
3. Wire analytics auto-run after batch completion
4. Test: send `batch_start` via wscat, verify `batch_progress` and `batch_complete` messages

### Chunk 2: BatchPanel + SetupLobby tabs (~200 lines TSX)
1. Extract current SetupLobby form into `SingleRunForm` component
2. Add tab navigation to SetupLobby
3. Build BatchPanel with config form + tuning overrides
4. Wire to WebSocket via `useBatchConnection` hook
5. Test: configure and launch a batch from the browser, see progress bar

### Chunk 3: BatchAnalytics (~250 lines TSX)
1. Stability area chart with percentile bands
2. Firing rate sortable table with color coding
3. Anomaly cards with severity colors
4. System metric accordion cards
5. Test: load a `batch_report.json` from M19b, verify all sections render

### Chunk 4: BatchCompare (~150 lines TSX)
1. Two-column layout with independent report loading
2. Diff summary panel between columns
3. Delta arrows for stability/firing rate changes
4. Test: load baseline vs final M19b reports, verify diff highlighting

### Chunk 5: Integration + Polish (~50 lines)
1. End-to-end test: launch batch from GUI → analytics display → load second report → compare
2. Error handling: batch failure, WebSocket disconnect during batch, invalid tuning values
3. Polish: loading states, empty states, responsive layout

---

## Existing Code to Reference

Read these files before starting:

| File | Why |
|------|-----|
| `src/chronicler/live.py` | WebSocket protocol, message handling pattern, thread management |
| `src/chronicler/batch.py` | `run_batch()` interface, parallel execution, tuning override passthrough |
| `src/chronicler/analytics.py` | `batch_report.json` schema, `detect_anomalies()`, `compute_event_firing_rates()` |
| `src/chronicler/tuning.py` | All 23 KNOWN_OVERRIDES with key constants, `load_tuning()`, `get_override()` |
| `viewer/src/components/SetupLobby.tsx` | Current lobby structure, styling patterns, form conventions |
| `viewer/src/hooks/useLiveConnection.ts` | WebSocket connection pattern to replicate for batch |
| `viewer/src/types.ts` | Existing type definitions, bundle format types |
| `docs/superpowers/analytics/m19b-tuning-report.md` | What the analytics output looks like — your UI should make this data visual |

---

## Design Constraints

1. **No new Python analytics code.** The GUI consumes `batch_report.json` as-is. If something is missing from the report schema, flag it — don't add extractors.
2. **Reuse the WebSocket connection.** No new server process, no REST API, no Flask/FastAPI. The LiveServer already handles viewer connections; batch is another message type on the same socket.
3. **Tuning overrides go over the wire as flattened dicts**, not YAML files. This avoids the file I/O race condition discovered in M19b iteration 4 where YAML writes hadn't flushed before ProcessPoolExecutor forked.
4. **recharts for all charts.** Already a viewer dependency. Don't add new chart libraries.
5. **Tailwind utility classes only** for styling. Match existing viewer dark theme (gray-900 background, gray-100 text, red-400 accents).
6. **The batch GUI is a testing accelerator, not a monitoring dashboard.** It runs one batch at a time. No job queue, no persistence, no history. Run → view results → adjust → run again.

---

## Exit Criteria

1. Can launch a 200-seed × 500-turn simulate-only batch from the browser
2. Progress bar updates in real-time as seeds complete
3. After completion, stability chart + firing rate table + anomaly panel render correctly
4. Can load two `batch_report.json` files and see side-by-side comparison with diff highlighting
5. Tuning overrides entered in the GUI are applied to the batch (verify by checking a bundle's `tuning_overrides` field)
6. Cancel button stops an in-progress batch
7. All existing tests still pass (986+)
8. New tests cover: WebSocket batch protocol, BatchPanel rendering, BatchAnalytics with mock report data

---

## Estimated Size

~400 lines TypeScript (BatchPanel + BatchAnalytics + BatchCompare + types + hook)
~120 lines Python (LiveServer batch handlers + batch.py progress callback)
~50 lines test code

Total: ~570 lines new code

---

## Phoebe's Notes

**On the tuning override UX:** Don't try to make the override inputs "smart" (sliders, presets, etc.) in this milestone. Plain number inputs with baked defaults as placeholders are sufficient. The user running batch tuning knows what the constants mean. Fancy UX is Phase 5 polish.

**On the compare mode:** The most valuable comparison is "what changed between two batch runs." The diff summary should answer three questions at a glance: (1) Did stability improve or degrade? (2) Did any mechanics start or stop firing? (3) Are there new anomalies? Everything else is drill-down detail.

**On WebSocket vs REST:** The design sketch mentions Flask/FastAPI as an option. Don't do that. The viewer already has a WebSocket connection to LiveServer. Adding a REST layer means a second server, CORS configuration, and port management. Keep it simple — batch is just another message type.

**On the race condition:** M19b iteration 4 discovered that writing tuning.yaml then immediately forking workers via ProcessPoolExecutor caused a race where workers read stale YAML. The fix was `sync` before batch. The GUI sidesteps this entirely by sending overrides as in-memory dicts over WebSocket — they get set on the args object directly, never touch disk. This is architecturally cleaner. Make sure `batch.py` accepts overrides as a dict parameter, not just a YAML path.
