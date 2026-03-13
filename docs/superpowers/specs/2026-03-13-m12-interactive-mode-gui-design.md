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

### Shared State (Thread-Safe Queues)

- `snapshot_queue: queue.Queue[dict]` — simulation puts turn snapshots + events after each turn. WebSocket thread drains and broadcasts.
- `command_queue: queue.Queue[dict]` — WebSocket thread puts parsed commands from the viewer. Simulation's `on_pause` blocks on `get()`.
- `status_queue: queue.Queue[dict]` — simulation puts status messages (started, paused, completed, error). WebSocket thread forwards to viewer.

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

### No Changes to `execute_run()`

It already accepts `on_pause`, `pending_injections`, and `pause_every`. The live mode provides different implementations of these callbacks.

### Dependency

`websockets` — pure Python, ~2000 LOC, no C extensions.

---

## WebSocket Protocol

All messages are JSON. Every message has a `type` field. Server-to-client and client-to-server are distinct message sets.

### Server -> Client Messages

**`init`** — sent once on connection. Provides full accumulated state so a late-connecting viewer can render the complete timeline:

```json
{
  "type": "init",
  "world_name": "Ashkari Dominion",
  "total_turns": 50,
  "pause_every": 10,
  "civs": ["Kethani Empire", "Dorrathi Clans"],
  "regions": [{"name": "Iron Peaks", "terrain": "mountains", "x": 3.2, "y": 7.1}],
  "current_turn": 20,
  "history": [ ...full array of TurnSnapshot-shaped objects for turns 1-20... ],
  "chronicle_entries": [ ...full array of {turn, text} for turns 1-20... ]
}
```

The `history` and `chronicle_entries` arrays are the same data accumulated in `execute_run`'s `history` list and `chronicle_entries` list.

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

**`paused`** — sent at era boundaries when simulation blocks:

```json
{
  "type": "paused",
  "turn": 20,
  "reason": "era_boundary",
  "valid_commands": ["continue", "inject", "set", "fork", "quit"],
  "injectable_events": ["plague", "famine", "migration"],
  "settable_stats": ["population", "military", "economy", "culture", "stability", "treasury"],
  "civs": ["Kethani Empire", "Dorrathi Clans"]
}
```

**`resumed`** — acknowledgment after a command is processed:

```json
{
  "type": "resumed",
  "after_command": "inject",
  "detail": "Queued plague -> Kethani Empire"
}
```

For `set` commands, `detail` includes the new value so the viewer can update immediately:

```json
{
  "type": "resumed",
  "after_command": "set",
  "detail": "Set Kethani Empire.military = 9",
  "civ": "Kethani Empire",
  "stat": "military",
  "value": 9
}
```

**`forked`** — response to a fork command:

```json
{
  "type": "forked",
  "save_path": "output/fork_save_t20"
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

1. **Commands only while paused.** Commands sent while the simulation is running get an `error` response: `"Simulation is running. Wait for pause."` Exception: `quit` and `speed` are always accepted.
2. **Multiple commands per pause.** The viewer can send several `inject`/`set` commands before sending `continue`. Each gets a `resumed` acknowledgment. `set` applies immediately to world state. `inject` queues for next turn. The simulation only unblocks when it receives `continue` or `quit`.
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

As `turn` messages arrive, the hook appends to internal `history` and `chronicle_entries` arrays, building a `ChronicleBundle`-shaped object incrementally. On `init`, it seeds with the full history. All downstream components receive the same `ChronicleBundle` type — they don't know whether data came from a file or a WebSocket.

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

### Speed Control

Added to the `Header` component next to existing play/pause controls. In static mode it controls playback speed (existing behavior). In live mode it sends a `speed` message to the simulation. Same UI element, different effect based on mode.

### New Component: `InterventionPanel`

Renders as a modal overlay when `paused === true`. Not a permanent layout element.

**Contents:**
- **Event injection**: dropdown of `pauseContext.injectable_events` + dropdown of `pauseContext.civs` + "Inject" button.
- **Stat override**: dropdown of civs, dropdown of stats, number input, "Set" button. On successful `set`, the current-turn display updates immediately (the `resumed` response carries the new value, hook patches the latest snapshot).
- **Pending actions queue**: list of staged and sent commands.
  - **Staged** (not yet sent to server): removable via X button. These are `inject` commands assembled in the UI but not yet dispatched.
  - **Sent** (acknowledged by server): not removable, shown with a checkmark. `set` commands move to "sent" immediately since they apply to world state on acknowledgment. `inject` commands move to "sent" on acknowledgment but are queued for next turn.
- **Fork button**: saves state, shows the fork path from the `forked` response.
- **Continue button**: prominent, resumes simulation. Sends any remaining staged commands, then sends `continue`.
- **Quit button**: secondary/danger style, stops simulation.

---

## Testing Strategy

### Python-side: `tests/test_live.py` (Unit)

Queue protocol tests — no actual WebSocket connections:

- `live_pause` puts a `paused` message on `status_queue`, blocks on `command_queue.get()`, returns `True` for `continue`, `False` for `quit`.
- Command validation: `inject` with invalid civ name -> error dict. `set` with out-of-range value -> error dict. `set` applies immediately to world state. `inject` appends to `pending_injections`.
- Speed control: `speed` message updates the delay value.
- Snapshot serialization: `TurnSnapshot` + events + named_events + chronicle_text serialize to expected JSON shape.
- Lifecycle: `LiveServer.start()` and `LiveServer.stop()` don't hang, daemon thread exits cleanly.

### Python-side: `tests/test_live_integration.py` (Integration)

Actual WebSocket connections using `websockets` client:

- **Connect and receive init**: start `LiveServer`, connect, assert `init` message with expected fields.
- **Turn streaming**: run 5 turns, assert 5 `turn` messages with incrementing turn numbers.
- **Pause and command round-trip**: `pause_every=3`, run until pause, assert `paused` message, send `continue`, assert next `turn` arrives.
- **Inject round-trip**: at pause, send `inject`, assert `resumed` acknowledgment, send `continue`, assert injected event appears in next turn's events.
- **Set round-trip**: at pause, send `set`, assert `resumed` includes new value, assert civ stat changed in subsequent turn snapshots.
- **Fork round-trip**: at pause, send `fork`, assert `forked` response with path, assert fork directory exists on disk.
- **Quit while paused**: send `quit`, assert `completed` message, assert chronicle file written.
- **Quit while running (graceful shutdown)**: send `quit` during turn execution, assert current turn completes, `completed` message sent, `chronicle_bundle.json` written with all turns completed so far. Quit at turn 23 of 50 -> bundle with 23 turns of history.
- **Reconnection**: connect, receive turns, disconnect, reconnect, assert `init` contains full history up to current turn. If paused, also receives `paused` immediately after `init`.
- **Single client enforcement**: connect client A, connect client B, assert client B gets error and is closed.
- **Commands while running rejected**: send `inject` while not paused, assert `error` response.

All integration tests: short runs (5-10 turns, 2 civs, 3 regions), deterministic seed, no LLM actions.

### Viewer-side: Vitest

**`useLiveConnection.test.ts`** — mock WebSocket:

- `init` received -> `bundle` non-null, `connected` true.
- `turn` received -> `bundle.history` grows by one, chronicle text appends.
- `paused` received -> `paused` true, `pauseContext` populated.
- `sendCommand('continue')` -> `paused` becomes false after `resumed`.
- `error` received -> `error` state populated.
- WebSocket close -> `connected` false, reconnect attempts begin.
- Reconnect succeeds -> `init` with history patches bundle.

**`InterventionPanel.test.tsx`** — component smoke tests:

- Renders when `paused` true, hidden when false.
- Event injection: select type + civ, click Inject, `sendCommand` called with correct payload.
- Stat override: select civ + stat, enter value, click Set, `sendCommand` called.
- Pending queue: inject two events, both appear as staged. Click remove on one, it disappears. Click Continue, remaining staged commands sent, then `continue` sent.
- Sent commands not removable: inject, receive `resumed`, assert item shows checkmark and no remove button.
- Fork button calls `sendCommand({ type: 'fork' })`.
- Quit button calls `sendCommand({ type: 'quit' })`.

**Follow mode tests** (in `useTimeline.test.ts`):

- Follow mode on: new turns auto-advance `currentTurn`.
- User scrubs backward: follow mode disables, new turns don't move `currentTurn`.
- User scrubs to latest: follow mode re-enables.

### Not Tested

- No E2E browser tests (Playwright/Cypress).
- No load/performance tests.
