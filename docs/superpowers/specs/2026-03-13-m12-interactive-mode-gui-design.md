# M12: Interactive Mode GUI — Design Spec

> Live simulation dashboard + intervention panel. Connects the M11 viewer to a running simulation via WebSocket. Scenario editor deferred — the schema changes significantly across Phase 3 milestones.

## Scope

**In scope (M12a + M12b):**
- WebSocket server embedded in the chronicler process
- Live turn-by-turn streaming to the viewer
- Intervention panel: event injection, stat override, fork, continue, quit
- Pending actions queue with staged/sent distinction
- Follow mode for auto-advancing the timeline
- Speed control (simulation pacing)
- Auto-reconnection with exponential backoff

**Out of scope (deferred):**
- Scenario editor (M12c from Phase 2 roadmap) — schema will change across M13-M18
- E2E browser tests — Phase 3 territory
- Multi-client support — single viewer connection

---

## Architecture & Threading Model

### CLI Flag

`--live` — mutually exclusive with `--interactive`, `--batch`, `--fork`.

`--live-port <int>` — WebSocket server port (default: 8765).

### Three Threads

1. **Main thread** — runs the synchronous simulation loop via `execute_run()`, unchanged. The `on_pause` callback blocks on `command_queue.get()` instead of `input()`.
2. **WebSocket thread** — daemon thread (`thread.daemon = True`) running `asyncio.run(serve())`. Handles client connections, forwards received commands to `command_queue`, broadcasts turn snapshots from `snapshot_queue`.
3. **Vite dev server** — user starts separately (`cd viewer && npm run dev`). No change to how the viewer is served.

The daemon thread ensures the process exits cleanly on Ctrl-C or simulation crash — no hanging event loops.

### Shared State (Thread-Safe)

- `snapshot_queue: queue.Queue[dict]` — simulation puts turn snapshots + events after each turn. WebSocket thread drains and broadcasts.
- `command_queue: queue.Queue[dict]` — WebSocket thread puts parsed commands from the viewer. Simulation's `on_pause` blocks on `get()`.
- `status_queue: queue.Queue[dict]` — simulation puts status messages (`paused`, `ack`, `forked`, `completed`, `error`). WebSocket thread drains and sends to viewer. This is the delivery mechanism for all server-initiated messages during a pause — `live_pause()` is a closure that captures `status_queue` and puts `ack`/`forked`/`error` responses directly onto it as it processes each command.
- `quit_event: threading.Event` — WebSocket thread sets this when a `quit` message arrives. The simulation loop checks `quit_event.is_set()` after each turn to support graceful mid-run quit. This is necessary because `command_queue` is only read at pause boundaries.
- `speed: float` — shared mutable float protected by `threading.Lock`. Default 1.0. WebSocket thread updates it on `speed` messages. Simulation loop reads it each turn to determine `time.sleep(1.0 / speed)` delay. Lock contention is negligible — one read and at most one write per turn.

### New Module: `src/chronicler/live.py`

Contains:
- `LiveServer` class — wraps the WebSocket server, queues, and thread management.
- `live_pause()` — the `on_pause` callback replacing `interactive_pause()` for live mode.
- `run_live()` — analogous to `run_interactive()`, wires up the server and calls `execute_run()`.

### Startup Sequence

1. `--live` flag triggers `run_live(args, ...)`.
2. `LiveServer` starts WebSocket daemon thread, prints `Live server ready on ws://localhost:8765`.
3. Simulation begins. Each turn: snapshot pushed to `snapshot_queue`. Simulation sleeps `1.0 / speed` between turns (default speed: 1.0).
4. At era boundaries: `live_pause()` sends a `paused` status, blocks on `command_queue.get()`.
5. Viewer connects, receives snapshots, shows intervention UI at pause, sends commands.
6. On simulation complete: sends `completed` status, server shuts down.

### Minimal Changes to `execute_run()`

`execute_run()` already accepts `on_pause`, `pending_injections`, and `pause_every`. The live mode provides different implementations of these callbacks.

Two small additions:

1. **`on_turn` callback** (optional, default `None`): called after each turn's snapshot is captured and appended to `history`, before `on_pause`. Signature: `on_turn(snapshot: TurnSnapshot, chronicle_text: str, events: list[Event], named_events: list[NamedEvent]) -> None`. The live mode uses this to push turn data to `snapshot_queue`. Non-live modes ignore it. This is the cleanest injection point — it avoids the live server needing access to internals of the simulation loop.

2. **`quit_check` callback** (optional, default `None`): called after each turn, returns `bool`. If it returns `True`, the simulation breaks out of the loop gracefully (same as `on_pause` returning `False`). The live mode passes `lambda: quit_event.is_set()`.

Both are backward-compatible — existing callers pass nothing and behavior is unchanged.

### Thread Safety Note

`live_pause()` runs on the main thread (called from `execute_run()`), so modifying `world` state via `set` commands is safe — the simulation loop is blocked at that point. Never apply `set` from the WebSocket thread directly.

### Dependency

`websockets` — pure Python, ~2000 LOC, no C extensions.

---

## WebSocket Protocol

All messages are JSON. Every message has a `type` field. Server-to-client and client-to-server are distinct message sets.

### Server -> Client Messages

**`init`** — sent once on connection. Provides the full accumulated state so a late-connecting viewer can render the complete timeline, sparklines, event dots, and chronicle text. The shape mirrors `chronicle_bundle.json` so the `useLiveConnection` hook can directly construct a `ChronicleBundle` from it:

```json
{
  "type": "init",
  "total_turns": 50,
  "pause_every": 10,
  "current_turn": 20,
  "world_state": { "...full WorldState serialization matching bundle's world_state field..." },
  "history": [ "...full array of TurnSnapshot-shaped objects for turns 1-20..." ],
  "chronicle_entries": { "1": "The world began...", "2": "Tensions rose...", "...": "..." },
  "events_timeline": [ "...all Event objects accumulated so far..." ],
  "named_events": [ "...all NamedEvent objects accumulated so far..." ],
  "era_reflections": { "10": "## Era: Turns 1-10\n\n...", "20": "## Era: Turns 11-20\n\n..." },
  "metadata": { "seed": 42, "sim_model": "local", "narrative_model": "local" },
  "speed": 5.0
}
```

**`world_state`** is the full `WorldState` serialization (same as the `world_state` field in `chronicle_bundle.json`). This gives the viewer access to civilizations (leaders, traits, domains, values, tech eras), regions (terrain, coordinates, controllers), relationships, and all other world data that downstream components need. No separate `world_name`, `civs`, or `regions` fields — they're all inside `world_state`.

**`speed`** is the current simulation speed (from the lock-protected shared float). On reconnect, the viewer's speed control reflects the actual simulation pace immediately rather than defaulting to 1x.

**`chronicle_entries` is a `Record<string, string>`** (turn number as string key -> text), matching the existing bundle format in `bundle.py` and the viewer's `Bundle` type. The `useLiveConnection` hook converts each `turn` message's `chronicle_text` into this format: `entries[String(turn)] = chronicle_text`.

**`init` size for long runs:** For a 500-turn run with 10 civs, `init` may be several megabytes. The `websockets` library default max message size (1MB in newer versions) may need to be increased via `max_size` parameter on the server. This is a configuration detail, not an architecture concern.

The server should also configure periodic WebSocket pings (e.g., every 20 seconds) so that stale connections are detected promptly rather than waiting for the OS TCP timeout. The `websockets` library supports this via the `ping_interval` parameter.

**`turn`** — sent after each turn completes:

```json
{
  "type": "turn",
  "turn": 14,
  "civ_stats": { "Kethani Empire": { "population": 7, "military": 5, "...": "..." } },
  "region_control": { "Iron Peaks": "Kethani Empire" },
  "relationships": { "Kethani Empire": { "Dorrathi Clans": { "disposition": "hostile" } } },
  "events": [{ "turn": 14, "event_type": "war", "description": "...", "importance": 7, "actors": ["..."] }],
  "named_events": [{ "turn": 14, "name": "The Siege of Iron Peaks", "event_type": "battle", "region": "Iron Peaks" }],
  "chronicle_text": "The Kethani legions marched..."
}
```

Both `events` (timeline events) and `named_events` (battles, treaties, cultural works) are included separately. The viewer's scrubber and stat graphs use named events for adaptive event dots and reference lines.

**Note on `on_turn` implementation:** The `named_events` parameter requires computing the delta — named events added this turn — since `world.named_events` is cumulative. The implementer should capture `len(world.named_events)` before `run_turn()` and slice afterward to extract new entries for that turn.

**`paused`** — sent at era boundaries when simulation blocks:

```json
{
  "type": "paused",
  "turn": 20,
  "reason": "era_boundary",
  "valid_commands": ["continue", "inject", "set", "fork", "quit"],
  "injectable_events": ["plague", "famine", "migration", "..."],
  "settable_stats": ["population", "military", "economy", "culture", "stability", "treasury"],
  "civs": ["Kethani Empire", "Dorrathi Clans"]
}
```

**`injectable_events` is derived at runtime**, not hardcoded. Add a `get_injectable_event_types() -> list[str]` function to `simulation.py` that returns `sorted(DEFAULT_EVENT_PROBABILITIES.keys())`. Both `live.py` and `interactive.py` call this instead of independently importing `DEFAULT_EVENT_PROBABILITIES`. As Phase 3 adds new event types (proxy war, embargo, natural disaster), the list grows automatically.

**`ack`** — acknowledgment after a command is processed. Named `ack` (not `resumed`) because the simulation does NOT resume after `inject`/`set`/`fork` — it stays paused. Only `continue` causes actual resumption:

```json
{
  "type": "ack",
  "command": "inject",
  "detail": "Queued plague -> Kethani Empire",
  "still_paused": true
}
```

For `set` commands, the response includes the new value so the viewer can patch the latest snapshot immediately. Note: `set` applies to `world` state directly (safe because `live_pause()` runs on the main thread while the simulation is blocked), but the turn snapshot already captured for the current turn still shows the old value. The viewer patches its local copy of the latest snapshot using the `civ`/`stat`/`value` fields:

```json
{
  "type": "ack",
  "command": "set",
  "detail": "Set Kethani Empire.military = 9",
  "still_paused": true,
  "civ": "Kethani Empire",
  "stat": "military",
  "value": 9
}
```

For `continue`, `still_paused` is `false` — this is what the viewer uses to clear the `paused` state:

```json
{
  "type": "ack",
  "command": "continue",
  "detail": "Simulation resumed",
  "still_paused": false
}
```

**`forked`** — response to a fork command. Includes the save path and a CLI command the user can copy to run the fork:

```json
{
  "type": "forked",
  "save_path": "output/fork_save_t20",
  "cli_hint": "python -m chronicler --fork output/fork_save_t20/state.json --seed 999 --turns 50"
}
```

**`completed`** — simulation finished:

```json
{
  "type": "completed",
  "total_turns": 50,
  "bundle_path": "output/chronicle_bundle.json"
}
```

**`error`** — validation errors on commands:

```json
{
  "type": "error",
  "message": "Civ 'Foo' not found. Valid civs: [...]"
}
```

### Client -> Server Messages

```json
{ "type": "continue" }
{ "type": "inject", "event_type": "plague", "civ": "Kethani Empire" }
{ "type": "set", "civ": "Kethani Empire", "stat": "military", "value": 9 }
{ "type": "fork" }
{ "type": "quit" }
{ "type": "speed", "value": 5.0 }
```

### Protocol Rules

1. **Commands only while paused.** Commands sent while the simulation is running get an `error` response: `"Simulation is running. Wait for pause."` Exception: `quit` and `speed` are always accepted. `quit` while running sets `quit_event`, which the simulation checks after completing the current turn — the turn finishes, bundle is written, `completed` is sent. No mid-turn abort.
2. **Multiple commands per pause.** The viewer can send several `inject`/`set` commands before sending `continue`. Each gets an `ack` response with `still_paused: true`. `set` applies immediately to world state. `inject` queues for next turn. The simulation only unblocks when it receives `continue` (which sends `ack` with `still_paused: false`) or `quit`.
3. **Single client.** Only one viewer connection at a time. Second connection gets an `error` and is closed.
4. **Reconnection.** If a client disconnects and reconnects, it receives an `init` with full history up to `current_turn`. If the simulation is paused, it also gets a `paused` message immediately after `init`.

---

## Viewer Changes

### Mode Detection

On mount, the viewer checks for a `ws` query param:
- `?ws=ws://localhost:8765` -> **live mode**, connect to WebSocket.
- No `ws` param -> **static mode**, load `chronicle_bundle.json` as today.

The `--live` CLI output prints the full viewer URL: `Open viewer: http://localhost:5173?ws=ws://localhost:8765`

### New Hook: `useLiveConnection`

Replaces `useBundle` when in live mode. Manages the WebSocket lifecycle:

```typescript
useLiveConnection(wsUrl: string) -> {
  bundle: ChronicleBundle | null,    // accumulated state, same shape as static bundle
  connected: boolean,
  paused: boolean,
  pauseContext: PauseContext | null,  // valid_commands, injectable_events, settable_stats, civs
  error: string | null,
  sendCommand: (cmd: Command) => void,
  speed: number,
  setSpeed: (s: number) => void,
}
```

As `turn` messages arrive, the hook appends to internal `history` array and converts `chronicle_text` into the `Record<string, string>` format (keyed by turn number as string), building a `ChronicleBundle`-shaped object incrementally. It also accumulates `events_timeline`, `named_events`, and `era_reflections`. On `init`, it seeds with the full state. All downstream components receive the same `ChronicleBundle` type — they don't know whether data came from a file or a WebSocket.

The hook clears `paused` state only when it receives an `ack` with `still_paused: false` (i.e., after a `continue` command). `ack` responses for `inject`/`set`/`fork` keep `paused: true`.

**Auto-reconnect:** On WebSocket close, the hook attempts reconnection with exponential backoff (1s, 2s, 4s, cap 10s). On reconnect, `init` provides full history and the bundle is patched. A "Reconnecting..." indicator appears in the header.

### App.tsx Changes

```typescript
const wsUrl = new URLSearchParams(location.search).get('ws')
const liveConn = wsUrl ? useLiveConnection(wsUrl) : null
const staticBundle = !wsUrl ? useBundle('chronicle_bundle.json') : null
const bundle = liveConn?.bundle ?? staticBundle?.bundle
```

Everything downstream receives `bundle` and works identically. The only addition is rendering the `InterventionPanel` when `liveConn?.paused` is true.

### Existing Component Changes

- **TimelineScrubber** — no changes. Turn count grows dynamically in live mode.
- **ChroniclePanel** — no changes. New entries append and auto-scroll.
- **FactionDashboard** — no changes. Sparklines extend as data arrives.
- **StatGraphs** — no changes. Lines extend rightward.
- **TerritoryMap** — no changes. Colors update based on `currentTurn`.
- **EventLog** — no changes. New events appear in the list.
- **Header** — minor change: show a connection indicator ("Live" badge, green dot) when in live mode. Show "Paused at turn N" when paused. Show "Reconnecting..." during reconnection.

### Follow Mode

Added to `useTimeline` (or as a companion to it):

- **Enabled by default** in live mode. New turns auto-advance `currentTurn` to the latest.
- **Disabled** when the user manually scrubs backward to review history. New turns do not yank the view forward.
- **Re-enabled** when the user scrubs to the latest turn or clicks a "Follow" toggle button on the scrubber.
- **Pause modal is independent of follow mode.** When the simulation pauses, the `InterventionPanel` appears regardless of whether follow mode is on or off. Interventions are time-critical — the user needs to see the pause even if they're reviewing turn 5 while the simulation paused at turn 20.

### Speed Control

Added to the `Header` component next to existing play/pause controls. Two independent concerns:

- **In live mode**: sends a `speed` message to the simulation server, controlling how fast turns execute (server-side pacing via `time.sleep(1.0 / speed)`).
- **In static mode**: controls local playback speed through recorded turns (existing behavior, client-side only).
- **In live mode with follow off**: the user is reviewing past history locally. The speed control affects server-side simulation speed only. Local history scrubbing/playback uses the existing `useTimeline` play/pause/speed mechanism independently. These are separate — the user might want the simulation running at 5x while they slowly review turn 12.

### New Component: `InterventionPanel`

Renders as a modal overlay when `paused === true`. Not a permanent layout element.

**Contents:**
- **Event injection**: dropdown of `pauseContext.injectable_events` + dropdown of `pauseContext.civs` + "Inject" button.
- **Stat override**: dropdown of civs, dropdown of stats, number input, "Set" button. On successful `set`, the current-turn display updates immediately (the `ack` response carries the new value, hook patches the latest snapshot).
- **Pending actions queue**: list of staged and sent commands.
  - **Staged** (not yet sent to server): removable via X button. These are `inject` commands assembled in the UI but not yet dispatched.
  - **Sent** (acknowledged by server): not removable, shown with a checkmark. `set` commands move to "sent" immediately since they apply to world state on acknowledgment. `inject` commands move to "sent" on acknowledgment but are queued for next turn.
- **Fork button**: saves state, shows the fork path and a copyable CLI command from the `forked` response.
- **Continue button**: prominent, resumes simulation. Sends any remaining staged commands, then sends `continue`.
- **Quit button**: secondary/danger style, stops simulation.

---

## Testing Strategy

### Python-side: `tests/test_live.py` (Unit)

Queue protocol tests — no actual WebSocket connections:

- `live_pause` puts a `paused` message on `status_queue`, blocks on `command_queue.get()`, returns `True` for `continue`, `False` for `quit`.
- `live_pause` puts `ack` messages on `status_queue` for each `inject`/`set`/`fork` command, with `still_paused: true`. `ack` for `continue` has `still_paused: false`.
- Command validation: `inject` with invalid civ name -> error dict on `status_queue`. `set` with out-of-range value -> error dict. `set` applies immediately to world state. `inject` appends to `pending_injections`.
- Speed control: `speed` message updates the lock-protected shared float.
- `quit_event`: setting it causes `quit_check()` to return `True`.
- Snapshot serialization: `TurnSnapshot` + events + named_events + chronicle_text serialize to expected JSON shape.
- Lifecycle: `LiveServer.start()` and `LiveServer.stop()` don't hang, daemon thread exits cleanly.

### Python-side: `tests/test_live_integration.py` (Integration)

Actual WebSocket connections using `websockets` client:

- **Connect and receive init**: start `LiveServer`, connect, assert `init` message with `world_state`, `history`, `chronicle_entries`, `events_timeline`, `named_events`, `era_reflections`, `metadata`.
- **Turn streaming**: run 5 turns, assert 5 `turn` messages with incrementing turn numbers.
- **Pause and command round-trip**: `pause_every=3`, run until pause, assert `paused` message, send `continue`, assert next `turn` arrives.
- **Inject round-trip**: at pause, send `inject`, assert `ack` with `still_paused: true`, send `continue`, assert `ack` with `still_paused: false`, assert injected event appears in next turn's events.
- **Set round-trip**: at pause, send `set`, assert `ack` includes `civ`/`stat`/`value` and `still_paused: true`, assert civ stat changed in subsequent turn snapshots.
- **Fork round-trip**: at pause, send `fork`, assert `forked` response with `save_path` and `cli_hint`, assert fork directory exists on disk.
- **Quit while paused**: send `quit`, assert `completed` message, assert chronicle file and bundle written.
- **Quit while running (graceful shutdown)**: send `quit` during turn execution, assert `quit_event` is set, current turn completes, `completed` message sent, `chronicle_bundle.json` written with all turns completed so far. Quit at turn 23 of 50 -> bundle with 23 turns of history, not a crash.
- **Reconnection**: connect, receive turns, disconnect, reconnect, assert `init` contains full history up to current turn. If paused, also receives `paused` immediately after `init`.
- **Single client enforcement**: connect client A, connect client B, assert client B gets error and is closed.
- **Commands while running rejected**: send `inject` while not paused, assert `error` response.

All integration tests: short runs (5-10 turns, 2 civs, 3 regions), deterministic seed, no LLM actions.

### Viewer-side: Vitest

**`useLiveConnection.test.ts`** — mock WebSocket:

- `init` received -> `bundle` non-null with `world_state`, `chronicle_entries` as `Record<string, string>`, `events_timeline`, `named_events`, `era_reflections`, `metadata` all populated. `connected` true.
- `turn` received -> `bundle.history` grows by one, `chronicle_entries[turn]` added, `events_timeline` and `named_events` extended.
- `paused` received -> `paused` true, `pauseContext` populated.
- `sendCommand('inject')` -> `paused` stays true after `ack` with `still_paused: true`.
- `sendCommand('continue')` -> `paused` becomes false after `ack` with `still_paused: false`.
- `ack` for `set` -> latest snapshot patched with new `civ`/`stat`/`value`.
- `error` received -> `error` state populated.
- WebSocket close -> `connected` false, reconnect attempts begin.
- Reconnect succeeds -> `init` with history patches bundle.

**`InterventionPanel.test.tsx`** — component smoke tests:

- Renders when `paused` true, hidden when false.
- Event injection: select type + civ, click Inject, `sendCommand` called with correct payload.
- Stat override: select civ + stat, enter value, click Set, `sendCommand` called.
- Pending queue: inject two events, both appear as staged. Click remove on one, it disappears. Click Continue, remaining staged commands sent, then `continue` sent.
- Sent commands not removable: inject, receive `ack`, assert item shows checkmark and no remove button.
- Already-sent not removable: inject an event, get `ack`, try to remove from queue — assert it remains (cannot undo a sent command, especially `set` which already mutated world state).
- Fork button calls `sendCommand({ type: 'fork' })`.
- Quit button calls `sendCommand({ type: 'quit' })`.

**Follow mode tests** (in `useTimeline.test.ts`):

- Follow mode on: new turns auto-advance `currentTurn`.
- User scrubs backward: follow mode disables, new turns don't move `currentTurn`.
- User scrubs to latest: follow mode re-enables.

### Not Tested

- No E2E browser tests (Playwright/Cypress).
- No load/performance tests.
